import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from backend.src import trade_head_calibration, freqtrade_proxy


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
        try:
            validated = freqtrade_proxy.validate_trading_request(request_data)
        except ValueError:
            # Fallback for generic feature request or unknown schema
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
                "trade_head_calibration_loaded": trade_head_calibration.is_calibration_loaded(features),
                "raw_vetoed": _as_bool(features.get("raw_vetoed")),
                "raw_veto_reason": features.get("raw_veto_reason"),
                "net_effective_predicted_edge_bps": _as_float(features.get("net_effective_predicted_edge_bps"), 0.0),
                "latency_ms": 0.0,
            }

        if isinstance(validated, freqtrade_proxy.HandoffV1):
            model = validated.model
            side = validated.side.lower()
            signal = "LONG" if side == "long" else "SHORT" if side == "short" else "FLAT"
            return {
                "signal": signal,
                "confidence": model.confidence,
                "model_version": self.model_version,
                "signal_id": validated.signal_id,
                "pair": validated.pair,
                "symbol": validated.symbol or validated.pair.replace("/", ""),
                "risk_tier": validated.risk.get("risk_tier"),
                "pred_fwd_return": model.pred_fwd_return,
                "passes_edge_gate": model.passes_edge_gate,
                "trade_head_calibration_loaded": model.trade_head_calibration_loaded,
                "raw_vetoed": model.raw_vetoed,
                "raw_veto_reason": model.raw_veto_reason,
                "net_effective_predicted_edge_bps": model.net_effective_predicted_edge_bps,
                "latency_ms": 0.0,
            }

        if isinstance(validated, freqtrade_proxy.WebhookV1):
            hrm = validated.hrm
            side = validated.side.lower()
            signal = "LONG" if side == "long" else "SHORT" if side == "short" else "FLAT"
            if not hrm:
                return {"signal": "FLAT", "confidence": 0.0, "model_version": self.model_version}
                
            return {
                "signal": signal,
                "confidence": hrm.confidence,
                "model_version": self.model_version,
                "signal_id": validated.signal_id,
                "pair": validated.pair,
                "symbol": validated.pair.replace("/", ""),
                "risk_tier": getattr(hrm, "risk_tier", None),
                "pred_fwd_return": hrm.pred_fwd_return,
                "passes_edge_gate": hrm.passes_edge_gate,
                "trade_head_calibration_loaded": hrm.trade_head_calibration_loaded,
                "raw_vetoed": hrm.raw_vetoed,
                "raw_veto_reason": hrm.raw_veto_reason,
                "net_effective_predicted_edge_bps": hrm.net_effective_predicted_edge_bps,
                "latency_ms": 0.0,
            }
        
        return {"signal": "FLAT", "confidence": 0.0, "model_version": self.model_version}


class PromotionGate:
    """Controls promotion and rollback to the Freqtrade-facing model path."""

    def __init__(self, active_version: str, min_win_rate: float = 0.55, min_pnl: float = 0.0):
        self.active_version = active_version
        self.history = [active_version]
        self.provenance = {
            active_version: {
                "promoted_at": datetime.now(timezone.utc).isoformat(),
                "metrics": {"win_rate": 1.0, "pnl": 0.0},
                "status": "initial"
            }
        }
        self.min_win_rate = float(min_win_rate)
        self.min_pnl = float(min_pnl)

    def promote(self, new_version: str, metrics: Dict[str, float]) -> bool:
        """Promote when fidelity and trading evidence clear minimum thresholds."""
        if not new_version or new_version == "unknown":
            return False
        
        # Provenance tracking
        self.provenance[new_version] = {
            "promoted_at": datetime.now(timezone.utc).isoformat(),
            "metrics": metrics,
            "status": "candidate"
        }

        if metrics.get("win_rate", 0.0) > self.min_win_rate and metrics.get("pnl", 0.0) > self.min_pnl:
            self.history.append(new_version)
            self.active_version = new_version
            self.provenance[new_version]["status"] = "active"
            return True
        
        self.provenance[new_version]["status"] = "rejected"
        return False

    def rollback(self) -> Optional[str]:
        """Rollback to the previous model version."""
        if len(self.history) > 1:
            old_version = self.history.pop()
            self.active_version = self.history[-1]
            self.provenance[old_version]["status"] = "rolled_back"
            self.provenance[old_version]["rolled_back_at"] = datetime.now(timezone.utc).isoformat()
            return self.active_version
        return None


class AuditLogger:
    """Simple audit logger for model operations and trading decisions."""
    
    def __init__(self, log_dir: str = "logs/audit"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.audit_file = self.log_dir / f"audit_{datetime.now(timezone.utc).strftime('%Y%m%d')}.jsonl"

    def log_event(self, event_type: str, details: Dict[str, Any]):
        """Log an event to the audit trail."""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            **details
        }
        with open(self.audit_file, "a") as f:
            f.write(json.dumps(event) + "\n")


class FreqtradeRingAgent:
    """Integrates HRM handoff/fidelity artifacts with the Freqtrade-facing path."""

    def __init__(self, active_version: str = "v1.0.0", execute_threshold: float = 0.8, latency_target_ms: float = 100.0, audit_log_dir: str = "logs/audit"):
        self.execute_threshold = float(execute_threshold)
        self.latency_target_ms = float(latency_target_ms)
        self.gate = PromotionGate(active_version)
        self.server = HRMModelServer(self.gate.active_version)
        self.audit_logger = AuditLogger(audit_log_dir)

    def process_trading_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process handoff/webhook requests and decide whether they should trade."""
        start_time = time.time()
        prediction = self.server.predict(request_data)
        end_time = time.time()
        
        latency_ms = round((end_time - start_time) * 1000, 3)

        blocked_reason = None
        if latency_ms > self.latency_target_ms:
            blocked_reason = "latency_target_exceeded"
        elif _as_bool(prediction.get("raw_vetoed")):
            blocked_reason = str(prediction.get("raw_veto_reason") or "raw_vetoed")
        elif not _as_bool(prediction.get("passes_edge_gate", True)):
            blocked_reason = "edge_gate_failed"
        elif _as_float(prediction.get("confidence"), 0.0) < self.execute_threshold:
            blocked_reason = "low_confidence"

        result = {
            "action": "execute_trade" if blocked_reason is None else "hold",
            "blocked_reason": blocked_reason,
            "prediction": {
                **prediction,
                "latency_ms": latency_ms,
                "provenance": self.gate.provenance.get(self.gate.active_version, {})
            },
            "ring_context": {
                "active_version": self.gate.active_version,
                "execute_threshold": self.execute_threshold,
                "latency_target_ms": self.latency_target_ms,
                "request_schema": request_data.get("schema"),
            },
            "agent_latency_ms": latency_ms,
        }
        
        # Log trading decision
        self.audit_logger.log_event("trading_decision", {
            "action": result["action"],
            "blocked_reason": result["blocked_reason"],
            "model_version": self.gate.active_version,
            "signal_id": request_data.get("signal_id"),
            "pair": request_data.get("pair"),
            "latency_ms": latency_ms
        })
        
        return result

    def _artifact_to_gate_metrics(self, artifact: Dict[str, Any]) -> Dict[str, float]:
        try:
            validated = freqtrade_proxy.validate_fidelity_artifact(artifact)
        except ValueError:
            # Fallback for unknown schema
            metrics = artifact.get("metrics") if isinstance(artifact.get("metrics"), dict) else {}
            return {
                "win_rate": _as_float(metrics.get("win_rate"), 0.0),
                "pnl": _as_float(metrics.get("pnl"), 0.0),
            }

        if isinstance(validated, freqtrade_proxy.FidelityPipelineV1):
            reconcile_summary = validated.reconcile_summary
            matched = _as_float(reconcile_summary.get("dispatch_fully_reconciled"), 0.0)
            total = max(_as_float(reconcile_summary.get("dispatch_total"), 0.0), 1.0)
            fidelity_metrics = reconcile_summary.get("fidelity_metrics") if isinstance(reconcile_summary.get("fidelity_metrics"), dict) else {}
            directional_accuracy = _as_float(fidelity_metrics.get("directional_accuracy"), matched / total)
            return {
                "win_rate": directional_accuracy,
                "pnl": matched,
            }

        if isinstance(validated, freqtrade_proxy.FidelityReconciliationV1):
            summary = validated.summary
            matched = _as_float(summary.get("dispatch_fully_reconciled"), 0.0)
            total = max(_as_float(summary.get("dispatch_total"), 0.0), 1.0)
            fidelity_metrics = summary.get("fidelity_metrics") if isinstance(summary.get("fidelity_metrics"), dict) else {}
            directional_accuracy = _as_float(fidelity_metrics.get("directional_accuracy"), matched / total)
            return {
                "win_rate": directional_accuracy,
                "pnl": matched,
            }

        return {"win_rate": 0.0, "pnl": 0.0}

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

    def get_dashboard_metrics(self, limit: int = 100) -> Dict[str, Any]:
        """Retrieve degradation and performance metrics from the audit trail."""
        events = []
        if self.audit_logger.audit_file.exists():
            with open(self.audit_logger.audit_file, "r") as f:
                lines = f.readlines()
                for line in lines[-limit:]:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        if not events:
            return {"status": "no_data"}

        total = len(events)
        execute_count = sum(1 for e in events if e.get("action") == "execute_trade")
        hold_count = total - execute_count
        
        blocked_reasons = {}
        for e in events:
            reason = e.get("blocked_reason")
            if reason:
                blocked_reasons[reason] = blocked_reasons.get(reason, 0) + 1

        avg_latency = sum(e.get("latency_ms", 0) for e in events) / total
        max_latency = max(e.get("latency_ms", 0) for e in events)
        
        # Alerts for model degradation
        alerts = []
        if avg_latency > self.latency_target_ms * 0.8:
            alerts.append("HIGH_AVERAGE_LATENCY")
        if max_latency > self.latency_target_ms:
            alerts.append("LATENCY_TARGET_EXCEEDED")
        if hold_count / total > 0.5:
            alerts.append("HIGH_VETO_RATE")

        return {
            "summary": {
                "total_requests": total,
                "execution_rate": round(execute_count / total, 3),
                "veto_rate": round(hold_count / total, 3),
                "avg_latency_ms": round(avg_latency, 3),
                "max_latency_ms": round(max_latency, 3),
            },
            "blocked_reasons": blocked_reasons,
            "alerts": alerts,
            "active_version": self.gate.active_version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
