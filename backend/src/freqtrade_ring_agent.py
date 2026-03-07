import json
import time
from pathlib import Path
from typing import Any, Dict, Optional


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


class HRMModelServer:
    """Serve a repo-local prediction envelope for the Freqtrade-facing path."""

    def __init__(self, model_version: str):
        self.model_version = model_version

    def predict(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize either a handoff payload or generic feature request."""
        schema = str(request_data.get("schema", "") or "")

        if schema == "moneyfan.freqtrade.handoff.v1":
            model = request_data.get("model") if isinstance(request_data.get("model"), dict) else {}
            risk = request_data.get("risk") if isinstance(request_data.get("risk"), dict) else {}
            confidence = _as_float(model.get("confidence"), 0.0)
            side = str(request_data.get("side", "") or "").lower()
            signal = "LONG" if side == "long" else "SHORT" if side == "short" else "FLAT"
            return {
                "signal": signal,
                "confidence": confidence,
                "model_version": self.model_version,
                "signal_id": request_data.get("signal_id"),
                "pair": request_data.get("pair"),
                "symbol": request_data.get("symbol"),
                "risk_tier": risk.get("risk_tier"),
                "pred_fwd_return": _as_float(model.get("pred_fwd_return"), 0.0),
                "passes_edge_gate": _as_bool(model.get("passes_edge_gate", True)),
                "trade_head_calibration_loaded": _as_bool(model.get("trade_head_calibration_loaded")),
                "raw_vetoed": _as_bool(model.get("raw_vetoed", model.get("vetoed"))),
                "raw_veto_reason": model.get("raw_veto_reason", model.get("veto_reason")),
                "net_effective_predicted_edge_bps": _as_float(model.get("net_effective_predicted_edge_bps"), 0.0),
                "latency_ms": 0.0,
            }

        if schema == "moneyfan.freqtrade.bridge.webhook.v1":
            metadata = request_data.get("metadata") if isinstance(request_data.get("metadata"), dict) else {}
            hrm = metadata.get("hrm") if isinstance(metadata.get("hrm"), dict) else {}
            side = str(request_data.get("side", "") or "").lower()
            signal = "LONG" if side == "long" else "SHORT" if side == "short" else "FLAT"
            return {
                "signal": signal,
                "confidence": _as_float(hrm.get("confidence"), 0.0),
                "model_version": self.model_version,
                "signal_id": request_data.get("signal_id"),
                "pair": request_data.get("pair"),
                "symbol": request_data.get("pair"),
                "risk_tier": hrm.get("risk_tier"),
                "pred_fwd_return": _as_float(hrm.get("pred_fwd_return"), 0.0),
                "passes_edge_gate": _as_bool(hrm.get("passes_edge_gate", True)),
                "trade_head_calibration_loaded": _as_bool(hrm.get("trade_head_calibration_loaded")),
                "raw_vetoed": _as_bool(hrm.get("raw_vetoed")),
                "raw_veto_reason": hrm.get("raw_veto_reason"),
                "net_effective_predicted_edge_bps": _as_float(hrm.get("net_effective_predicted_edge_bps"), 0.0),
                "latency_ms": 0.0,
            }

        features = request_data.get("features", {}) if isinstance(request_data.get("features"), dict) else {}
        confidence = _as_float(features.get("confidence"), 0.5)
        direction = _as_float(features.get("direction"), 0.0)
        signal = "LONG" if direction > 0 else "SHORT" if direction < 0 else "FLAT"
        return {
            "signal": signal,
            "confidence": confidence,
            "model_version": self.model_version,
            "signal_id": request_data.get("signal_id"),
            "pair": request_data.get("pair"),
            "symbol": request_data.get("symbol"),
            "risk_tier": features.get("risk_tier"),
            "pred_fwd_return": _as_float(features.get("pred_fwd_return"), 0.0),
            "passes_edge_gate": _as_bool(features.get("passes_edge_gate", True)),
            "trade_head_calibration_loaded": _as_bool(features.get("trade_head_calibration_loaded")),
            "raw_vetoed": _as_bool(features.get("raw_vetoed")),
            "raw_veto_reason": features.get("raw_veto_reason"),
            "net_effective_predicted_edge_bps": _as_float(features.get("net_effective_predicted_edge_bps"), 0.0),
            "latency_ms": 0.0,
        }


class PromotionGate:
    """Controls promotion and rollback to the Freqtrade-facing model path."""

    def __init__(self, active_version: str, min_win_rate: float = 0.55, min_pnl: float = 0.0):
        self.active_version = active_version
        self.history = [active_version]
        self.min_win_rate = float(min_win_rate)
        self.min_pnl = float(min_pnl)

    def promote(self, new_version: str, metrics: Dict[str, float]) -> bool:
        """Promote when fidelity and trading evidence clear minimum thresholds."""
        if not new_version or new_version == "unknown":
            return False
        if metrics.get("win_rate", 0.0) > self.min_win_rate and metrics.get("pnl", 0.0) > self.min_pnl:
            self.history.append(new_version)
            self.active_version = new_version
            return True
        return False

    def rollback(self) -> Optional[str]:
        """Rollback to the previous model version."""
        if len(self.history) > 1:
            self.history.pop()
            self.active_version = self.history[-1]
            return self.active_version
        return None


class FreqtradeRingAgent:
    """Integrates HRM handoff/fidelity artifacts with the Freqtrade-facing path."""

    def __init__(self, active_version: str = "v1.0.0", execute_threshold: float = 0.8):
        self.execute_threshold = float(execute_threshold)
        self.gate = PromotionGate(active_version)
        self.server = HRMModelServer(self.gate.active_version)

    def process_trading_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process handoff/webhook requests and decide whether they should trade."""
        start_time = time.time()
        prediction = self.server.predict(request_data)
        end_time = time.time()

        blocked_reason = None
        if _as_bool(prediction.get("raw_vetoed")):
            blocked_reason = str(prediction.get("raw_veto_reason") or "raw_vetoed")
        elif not _as_bool(prediction.get("passes_edge_gate", True)):
            blocked_reason = "edge_gate_failed"
        elif _as_float(prediction.get("confidence"), 0.0) < self.execute_threshold:
            blocked_reason = "low_confidence"

        return {
            "action": "execute_trade" if blocked_reason is None else "hold",
            "blocked_reason": blocked_reason,
            "prediction": {
                **prediction,
                "latency_ms": round((end_time - start_time) * 1000, 3),
            },
            "ring_context": {
                "active_version": self.gate.active_version,
                "execute_threshold": self.execute_threshold,
                "request_schema": request_data.get("schema"),
            },
            "agent_latency_ms": round((end_time - start_time) * 1000, 3),
        }

    def _artifact_to_gate_metrics(self, artifact: Dict[str, Any]) -> Dict[str, float]:
        schema = str(artifact.get("schema", "") or "")

        if schema == "moneyfan.freqtrade.fidelity_pipeline_run.v1":
            reconcile_summary = artifact.get("reconcile_summary") if isinstance(artifact.get("reconcile_summary"), dict) else {}
            matched = _as_float(reconcile_summary.get("dispatch_fully_reconciled"), 0.0)
            total = max(_as_float(reconcile_summary.get("dispatch_total"), 0.0), 1.0)
            fidelity_metrics = reconcile_summary.get("fidelity_metrics") if isinstance(reconcile_summary.get("fidelity_metrics"), dict) else {}
            directional_accuracy = _as_float(fidelity_metrics.get("directional_accuracy"), matched / total)
            return {
                "win_rate": directional_accuracy,
                "pnl": matched,
            }

        if schema == "moneyfan.hrm.freqtrade.fidelity_reconciliation.v1":
            summary = artifact.get("summary") if isinstance(artifact.get("summary"), dict) else {}
            matched = _as_float(summary.get("dispatch_fully_reconciled"), 0.0)
            total = max(_as_float(summary.get("dispatch_total"), 0.0), 1.0)
            fidelity_metrics = summary.get("fidelity_metrics") if isinstance(summary.get("fidelity_metrics"), dict) else {}
            directional_accuracy = _as_float(fidelity_metrics.get("directional_accuracy"), matched / total)
            return {
                "win_rate": directional_accuracy,
                "pnl": matched,
            }

        metrics = artifact.get("metrics") if isinstance(artifact.get("metrics"), dict) else {}
        return {
            "win_rate": _as_float(metrics.get("win_rate"), 0.0),
            "pnl": _as_float(metrics.get("pnl"), 0.0),
        }

    def _artifact_model_version(self, artifact: Dict[str, Any]) -> str:
        for key in ("model_version", "candidate_model_version", "evaluated_version"):
            value = str(artifact.get(key, "") or "").strip()
            if value:
                return value
        context = artifact.get("context") if isinstance(artifact.get("context"), dict) else {}
        value = str(context.get("model_version", "") or "").strip()
        return value or "unknown"

    def evaluate_hrm_artifact(self, artifact_path: str) -> Dict[str, Any]:
        """Evaluate HRM artifacts and promote only when fidelity evidence is strong enough."""
        with open(Path(artifact_path), "r") as f:
            artifact = json.load(f)

        metrics = self._artifact_to_gate_metrics(artifact)
        evaluated_version = self._artifact_model_version(artifact)
        promoted = self.gate.promote(evaluated_version, metrics)

        if promoted:
            self.server = HRMModelServer(self.gate.active_version)

        return {
            "artifact_schema": artifact.get("schema"),
            "evaluated_version": evaluated_version,
            "promoted": promoted,
            "active_version": self.gate.active_version,
            "gate_metrics": metrics,
        }
