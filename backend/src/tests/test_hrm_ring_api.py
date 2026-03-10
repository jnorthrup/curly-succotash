import json
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

from backend.src import main, trade_head_calibration


@pytest.fixture(autouse=True)
def reset_ring_agent_state():
    main.reset_hrm_ring_agent(active_version="v1.0.0", execute_threshold=0.8)


@pytest.fixture
def client():
    client = TestClient(main.app)
    yield client
    client.close()


def _handoff_payload(**overrides):
    payload = {
        "schema": "moneyfan.freqtrade.handoff.v1",
        "signal_id": "sig-ring-api-1",
        "pair": "BTC/USDT",
        "symbol": "BTCUSDT",
        "side": "long",
        "risk": {"risk_tier": "normal"},
        "model": {
            "confidence": 0.91,
            "pred_fwd_return": 0.012,
            "passes_edge_gate": True,
            "trade_head_calibration_loaded": True,
            "raw_vetoed": False,
            "raw_veto_reason": None,
            "net_effective_predicted_edge_bps": 21.0,
        },
    }
    payload.update(overrides)
    return payload


def _webhook_payload(**overrides):
    payload = {
        "schema": "moneyfan.freqtrade.bridge.webhook.v1",
        "signal_id": "sig-ring-api-2",
        "pair": "ETH/USDT",
        "side": "short",
        "metadata": {
            "hrm": {
                "confidence": 0.42,
                "risk_tier": "guarded",
                "pred_fwd_return": -0.009,
                "passes_edge_gate": True,
                "trade_head_calibration_loaded": True,
                "raw_vetoed": False,
                "raw_veto_reason": None,
                "net_effective_predicted_edge_bps": 8.5,
            }
        },
    }
    payload.update(overrides)
    return payload


def test_hrm_ring_api_promotes_evaluated_artifact_and_reuses_version(client, tmp_path):
    status_before = client.get("/api/hrm/ring/status")
    assert status_before.status_code == 200
    assert status_before.json()["active_version"] == "v1.0.0"

    process_before = client.post("/api/hrm/ring/process", json=_handoff_payload())
    assert process_before.status_code == 200
    assert process_before.json()["action"] == "execute_trade"
    assert process_before.json()["ring_context"]["active_version"] == "v1.0.0"

    artifact_path = tmp_path / "fidelity_pipeline.json"
    artifact_path.write_text(
        json.dumps(
            {
                "schema": "moneyfan.freqtrade.fidelity_pipeline_run.v1",
                "model_version": "v2.0.0",
                "reconcile_summary": {
                    "dispatch_total": 4,
                    "dispatch_fully_reconciled": 3,
                    "fidelity_metrics": {
                        "directional_accuracy": 0.75,
                    },
                },
            }
        )
    )

    evaluate = client.post(
        "/api/hrm/ring/evaluate",
        json={"artifact_path": str(artifact_path)},
    )
    assert evaluate.status_code == 200
    assert evaluate.json()["promoted"] is True
    assert evaluate.json()["active_version"] == "v2.0.0"
    assert evaluate.json()["artifact_path"] == str(artifact_path)

    process_after = client.post("/api/hrm/ring/process", json=_handoff_payload())
    assert process_after.status_code == 200
    assert process_after.json()["ring_context"]["active_version"] == "v2.0.0"


def test_hrm_ring_api_holds_low_confidence_webhook_payload(client):
    response = client.post("/api/hrm/ring/process", json=_webhook_payload())

    assert response.status_code == 200
    assert response.json()["action"] == "hold"
    assert response.json()["blocked_reason"] == "low_confidence"
    assert response.json()["prediction"]["signal"] == "SHORT"
    assert response.json()["ring_context"]["request_schema"] == "moneyfan.freqtrade.bridge.webhook.v1"


def test_hrm_ring_api_rejects_missing_artifact(client, tmp_path):
    missing_artifact = tmp_path / "missing.json"

    response = client.post(
        "/api/hrm/ring/evaluate",
        json={"artifact_path": str(missing_artifact)},
    )

    assert response.status_code == 404
    assert "Artifact not found" in response.json()["detail"]


def test_hrm_ring_api_rollback_after_promotion(client, tmp_path):
    artifact_path = tmp_path / "fidelity_pipeline.json"
    artifact_path.write_text(
        json.dumps(
            {
                "schema": "moneyfan.freqtrade.fidelity_pipeline_run.v1",
                "model_version": "v2.0.0",
                "reconcile_summary": {
                    "dispatch_total": 4,
                    "dispatch_fully_reconciled": 3,
                    "fidelity_metrics": {
                        "directional_accuracy": 0.75,
                    },
                },
            }
        )
    )

    evaluate = client.post(
        "/api/hrm/ring/evaluate",
        json={"artifact_path": str(artifact_path)},
    )
    assert evaluate.status_code == 200
    assert evaluate.json()["promoted"] is True
    assert evaluate.json()["active_version"] == "v2.0.0"

    rollback = client.post("/api/hrm/ring/rollback")
    assert rollback.status_code == 200
    data = rollback.json()
    assert data["rolled_back"] is True
    assert data["active_version"] == "v1.0.0"


def test_hrm_ring_api_rollback_at_single_version(client):
    rollback = client.post("/api/hrm/ring/rollback")
    assert rollback.status_code == 200
    data = rollback.json()
    assert data["rolled_back"] is False
    assert data["active_version"] == "v1.0.0"


def test_hrm_ring_api_enforces_latency_target(client):
    # Set a very low latency target
    main.reset_hrm_ring_agent(latency_target_ms=0.0001)
    
    response = client.post("/api/hrm/ring/process", json=_handoff_payload())
    
    assert response.status_code == 200
    assert response.json()["action"] == "hold"
    assert response.json()["blocked_reason"] == "latency_target_exceeded"
    assert response.json()["ring_context"]["latency_target_ms"] == 0.0001


def test_hrm_ring_api_returns_provenance_and_logs_audit(client, tmp_path):
    # Process a request
    payload = _handoff_payload()
    response = client.post("/api/hrm/ring/process", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert "provenance" in data["prediction"]
    assert data["prediction"]["provenance"]["status"] == "initial"
    
    # Check audit log exists
    audit_files = list(Path("logs/audit").glob("audit_*.jsonl"))
    assert len(audit_files) > 0
    
    # Check audit log content
    with open(audit_files[0], "r") as f:
        log_entry = json.loads(f.readlines()[-1])
        assert log_entry["event_type"] == "trading_decision"
        assert log_entry["action"] == "execute_trade"
        assert log_entry["signal_id"] == payload["signal_id"]

    # Check dashboard
    response = client.get("/api/hrm/ring/dashboard")
    assert response.status_code == 200
    dashboard = response.json()
    assert "summary" in dashboard
    assert dashboard["summary"]["total_requests"] >= 1
    assert dashboard["summary"]["execution_rate"] > 0
