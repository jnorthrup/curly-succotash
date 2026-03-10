"""
Unit tests for backend/src/freqtrade_proxy.py
"""

import pytest
from pydantic import ValidationError

from backend.src.freqtrade_proxy import (
    ModelMetadata,
    HandoffV1,
    WebhookV1,
    FidelityPipelineV1,
    FidelityReconciliationV1,
    validate_trading_request,
    validate_fidelity_artifact,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

VALID_MODEL_METADATA = {
    "confidence": 0.75,
    "pred_fwd_return": 0.003,
}

VALID_HANDOFF_DATA = {
    "schema": "moneyfan.freqtrade.handoff.v1",
    "signal_id": "sig-001",
    "pair": "BTC/USDT",
    "side": "long",
    "model": VALID_MODEL_METADATA,
}

VALID_WEBHOOK_DATA = {
    "schema": "moneyfan.freqtrade.bridge.webhook.v1",
    "signal_id": "sig-002",
    "pair": "ETH/USDT",
    "side": "short",
    "metadata": {
        "hrm": {
            "confidence": 0.60,
            "pred_fwd_return": -0.002,
        }
    },
}

VALID_FIDELITY_PIPELINE_DATA = {
    "schema": "moneyfan.freqtrade.fidelity_pipeline_run.v1",
    "model_version": "v1.2.3",
    "reconcile_summary": {"n_trades": 10, "accuracy": 0.8},
}

VALID_FIDELITY_RECONCILIATION_DATA = {
    "schema": "moneyfan.hrm.freqtrade.fidelity_reconciliation.v1",
    "model_version": "v1.2.3",
    "summary": {"directional_accuracy": 0.75},
}


# ---------------------------------------------------------------------------
# Test 1: Valid HandoffV1 roundtrip
# ---------------------------------------------------------------------------

def test_handoff_v1_valid_roundtrip():
    obj = HandoffV1.model_validate(VALID_HANDOFF_DATA)
    assert obj.schema_ == "moneyfan.freqtrade.handoff.v1"
    assert obj.signal_id == "sig-001"
    assert obj.pair == "BTC/USDT"
    assert obj.side == "long"
    assert obj.model.confidence == 0.75
    # round-trip via model_dump with by_alias=True re-produces "schema" key
    dumped = obj.model_dump(by_alias=True)
    assert dumped["schema"] == "moneyfan.freqtrade.handoff.v1"


# ---------------------------------------------------------------------------
# Test 2: Confidence out of bounds raises ValidationError
# ---------------------------------------------------------------------------

def test_model_metadata_confidence_above_1_raises():
    with pytest.raises(ValidationError):
        ModelMetadata(confidence=1.5, pred_fwd_return=0.0)


def test_model_metadata_confidence_below_0_raises():
    with pytest.raises(ValidationError):
        ModelMetadata(confidence=-0.1, pred_fwd_return=0.0)


# ---------------------------------------------------------------------------
# Test 3: Wrong schema string in HandoffV1 raises ValidationError
# ---------------------------------------------------------------------------

def test_handoff_v1_wrong_schema_raises():
    bad_data = dict(VALID_HANDOFF_DATA, schema="wrong.schema")
    with pytest.raises((ValueError, ValidationError)):
        HandoffV1.model_validate(bad_data)


# ---------------------------------------------------------------------------
# Test 4: Valid WebhookV1 roundtrip
# ---------------------------------------------------------------------------

def test_webhook_v1_valid_roundtrip():
    obj = WebhookV1.model_validate(VALID_WEBHOOK_DATA)
    assert obj.schema_ == "moneyfan.freqtrade.bridge.webhook.v1"
    assert obj.signal_id == "sig-002"
    assert obj.pair == "ETH/USDT"
    assert obj.side == "short"
    dumped = obj.model_dump(by_alias=True)
    assert dumped["schema"] == "moneyfan.freqtrade.bridge.webhook.v1"


# ---------------------------------------------------------------------------
# Test 5: WebhookV1.hrm property returns ModelMetadata when hrm key present
# ---------------------------------------------------------------------------

def test_webhook_v1_hrm_property_returns_model_metadata():
    obj = WebhookV1.model_validate(VALID_WEBHOOK_DATA)
    hrm = obj.hrm
    assert hrm is not None
    assert isinstance(hrm, ModelMetadata)
    assert hrm.confidence == 0.60
    assert hrm.pred_fwd_return == -0.002


def test_webhook_v1_hrm_property_returns_none_when_absent():
    data = dict(VALID_WEBHOOK_DATA, metadata={"other": {"x": 1}})
    obj = WebhookV1.model_validate(data)
    assert obj.hrm is None


# ---------------------------------------------------------------------------
# Test 6: validate_trading_request dispatches correctly
# ---------------------------------------------------------------------------

def test_validate_trading_request_dispatches_handoff():
    result = validate_trading_request(VALID_HANDOFF_DATA)
    assert isinstance(result, HandoffV1)
    assert result.schema_ == "moneyfan.freqtrade.handoff.v1"


def test_validate_trading_request_dispatches_webhook():
    result = validate_trading_request(VALID_WEBHOOK_DATA)
    assert isinstance(result, WebhookV1)
    assert result.schema_ == "moneyfan.freqtrade.bridge.webhook.v1"


# ---------------------------------------------------------------------------
# Test 7: validate_trading_request raises ValueError for unknown schema
# ---------------------------------------------------------------------------

def test_validate_trading_request_unknown_schema_raises():
    with pytest.raises(ValueError, match="Unsupported request schema"):
        validate_trading_request({"schema": "unknown.schema"})


# ---------------------------------------------------------------------------
# Test 8: validate_fidelity_artifact dispatches correctly
# ---------------------------------------------------------------------------

def test_validate_fidelity_artifact_dispatches_pipeline():
    result = validate_fidelity_artifact(VALID_FIDELITY_PIPELINE_DATA)
    assert isinstance(result, FidelityPipelineV1)
    assert result.schema_ == "moneyfan.freqtrade.fidelity_pipeline_run.v1"
    assert result.model_version == "v1.2.3"


def test_validate_fidelity_artifact_dispatches_reconciliation():
    result = validate_fidelity_artifact(VALID_FIDELITY_RECONCILIATION_DATA)
    assert isinstance(result, FidelityReconciliationV1)
    assert result.schema_ == "moneyfan.hrm.freqtrade.fidelity_reconciliation.v1"
    assert result.model_version == "v1.2.3"


# ---------------------------------------------------------------------------
# Test 9: validate_fidelity_artifact raises ValueError for unknown schema
# ---------------------------------------------------------------------------

def test_validate_fidelity_artifact_unknown_schema_raises():
    with pytest.raises(ValueError, match="Unsupported fidelity schema"):
        validate_fidelity_artifact({"schema": "unknown.fidelity.schema"})
