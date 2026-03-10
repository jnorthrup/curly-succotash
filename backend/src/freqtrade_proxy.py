"""
Freqtrade Proxy Mapping - Schema Definitions

Formalizes the contract between Freqtrade ring agents and the HRM serving path.
Provides strict validation for handoff, webhook, and fidelity artifacts.
"""

from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field, field_validator


class ModelMetadata(BaseModel):
    """HRM Model prediction metadata."""
    confidence: float = Field(..., ge=0.0, le=1.0)
    pred_fwd_return: float
    passes_edge_gate: bool = True
    trade_head_calibration_loaded: bool = False
    raw_vetoed: bool = False
    raw_veto_reason: Optional[str] = None
    net_effective_predicted_edge_bps: float = 0.0


class HandoffV1(BaseModel):
    """moneyfan.freqtrade.handoff.v1"""
    schema_: str = Field(..., alias="schema")
    signal_id: str
    pair: str
    symbol: Optional[str] = None
    side: str
    risk: Dict[str, Any] = Field(default_factory=lambda: {"risk_tier": "normal"})
    model: ModelMetadata

    @field_validator("schema_")
    @classmethod
    def validate_schema(cls, v):
        if v != "moneyfan.freqtrade.handoff.v1":
            raise ValueError(f"Invalid schema: {v}")
        return v


class WebhookV1(BaseModel):
    """moneyfan.freqtrade.bridge.webhook.v1"""
    schema_: str = Field(..., alias="schema")
    signal_id: str
    pair: str
    side: str
    metadata: Dict[str, Dict[str, Any]]

    @field_validator("schema_")
    @classmethod
    def validate_schema(cls, v):
        if v != "moneyfan.freqtrade.bridge.webhook.v1":
            raise ValueError(f"Invalid schema: {v}")
        return v
    
    @property
    def hrm(self) -> Optional[ModelMetadata]:
        hrm_data = self.metadata.get("hrm")
        if hrm_data:
            return ModelMetadata(**hrm_data)
        return None


class FidelityMetrics(BaseModel):
    """Metrics for fidelity reconciliation."""
    directional_accuracy: float = Field(..., ge=0.0, le=1.0)
    mean_absolute_error: Optional[float] = None


class FidelityPipelineV1(BaseModel):
    """moneyfan.freqtrade.fidelity_pipeline_run.v1"""
    schema_: str = Field(..., alias="schema")
    model_version: str
    reconcile_summary: Dict[str, Any]

    @field_validator("schema_")
    @classmethod
    def validate_schema(cls, v):
        if v != "moneyfan.freqtrade.fidelity_pipeline_run.v1":
            raise ValueError(f"Invalid schema: {v}")
        return v


class FidelityReconciliationV1(BaseModel):
    """moneyfan.hrm.freqtrade.fidelity_reconciliation.v1"""
    schema_: str = Field(..., alias="schema")
    model_version: str
    summary: Dict[str, Any]

    @field_validator("schema_")
    @classmethod
    def validate_schema(cls, v):
        if v != "moneyfan.hrm.freqtrade.fidelity_reconciliation.v1":
            raise ValueError(f"Invalid schema: {v}")
        return v


def validate_trading_request(data: Dict[str, Any]) -> Union[HandoffV1, WebhookV1]:
    """Validate a trading request against known schemas."""
    schema = data.get("schema")
    if schema == "moneyfan.freqtrade.handoff.v1":
        return HandoffV1(**data)
    if schema == "moneyfan.freqtrade.bridge.webhook.v1":
        return WebhookV1(**data)
    raise ValueError(f"Unsupported request schema: {schema}")


def validate_fidelity_artifact(data: Dict[str, Any]) -> Union[FidelityPipelineV1, FidelityReconciliationV1]:
    """Validate a fidelity artifact against known schemas."""
    schema = data.get("schema")
    if schema == "moneyfan.freqtrade.fidelity_pipeline_run.v1":
        return FidelityPipelineV1(**data)
    if schema == "moneyfan.hrm.freqtrade.fidelity_reconciliation.v1":
        return FidelityReconciliationV1(**data)
    raise ValueError(f"Unsupported fidelity schema: {schema}")
