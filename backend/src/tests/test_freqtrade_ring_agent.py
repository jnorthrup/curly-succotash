import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.freqtrade_ring_agent import FreqtradeRingAgent


def _handoff_payload(**overrides):
    payload = {
        "schema": "moneyfan.freqtrade.handoff.v1",
        "signal_id": "sig-ring-1",
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


def test_process_trading_request_executes_handoff_with_fidelity_fields():
    agent = FreqtradeRingAgent(active_version="v1.2.3", execute_threshold=0.8)

    result = agent.process_trading_request(_handoff_payload())

    assert result["action"] == "execute_trade"
    assert result["blocked_reason"] is None
    assert result["prediction"]["signal"] == "LONG"
    assert result["prediction"]["confidence"] == 0.91
    assert result["prediction"]["signal_id"] == "sig-ring-1"
    assert result["prediction"]["pair"] == "BTC/USDT"
    assert result["prediction"]["trade_head_calibration_loaded"] is True
    assert result["ring_context"]["active_version"] == "v1.2.3"
    assert result["ring_context"]["request_schema"] == "moneyfan.freqtrade.handoff.v1"


def test_process_trading_request_holds_vetoed_payload():
    agent = FreqtradeRingAgent(active_version="v1.2.3", execute_threshold=0.8)
    payload = _handoff_payload(
        model={
            "confidence": 0.98,
            "pred_fwd_return": 0.012,
            "passes_edge_gate": True,
            "trade_head_calibration_loaded": True,
            "raw_vetoed": True,
            "raw_veto_reason": "risk_cap",
        }
    )

    result = agent.process_trading_request(payload)

    assert result["action"] == "hold"
    assert result["blocked_reason"] == "risk_cap"
    assert result["prediction"]["raw_vetoed"] is True


def test_evaluate_hrm_artifact_promotes_on_fidelity_pipeline_summary(tmp_path):
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

    agent = FreqtradeRingAgent(active_version="v1.0.0")
    result = agent.evaluate_hrm_artifact(str(artifact_path))

    assert result["artifact_schema"] == "moneyfan.freqtrade.fidelity_pipeline_run.v1"
    assert result["evaluated_version"] == "v2.0.0"
    assert result["promoted"] is True
    assert result["active_version"] == "v2.0.0"
    assert result["gate_metrics"]["win_rate"] == 0.75
    assert result["gate_metrics"]["pnl"] == 3.0


def test_evaluate_hrm_artifact_rejects_weak_reconciliation_report(tmp_path):
    artifact_path = tmp_path / "fidelity_reconciliation.json"
    artifact_path.write_text(
        json.dumps(
            {
                "schema": "moneyfan.hrm.freqtrade.fidelity_reconciliation.v1",
                "model_version": "v2.0.0",
                "summary": {
                    "dispatch_total": 5,
                    "dispatch_fully_reconciled": 0,
                    "fidelity_metrics": {
                        "directional_accuracy": 0.2,
                    },
                },
            }
        )
    )

    agent = FreqtradeRingAgent(active_version="v1.0.0")
    result = agent.evaluate_hrm_artifact(str(artifact_path))

    assert result["promoted"] is False
    assert result["active_version"] == "v1.0.0"
    assert result["gate_metrics"]["win_rate"] == 0.2
    assert result["gate_metrics"]["pnl"] == 0.0
