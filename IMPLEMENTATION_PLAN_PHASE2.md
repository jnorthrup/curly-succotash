# TODO.md Phase 2 Implementation Plan

**Date:** 2026-03-06
**Status:** Planning Complete - Ready for Implementation
**Owner:** @jim

---

## Executive Summary

This document outlines the implementation plan for the 65 remaining TODO.md tasks. Tasks are prioritized by impact on the trading system and organized into focused workstreams.

### Task Summary

| Category | Tasks | Priority | Estimated Effort |
|----------|-------|----------|------------------|
| **Moneyfan Training Debt** | 18 | Critical | 6-8 weeks |
| **Validation & Quality Gates** | 5 | High | 2-3 weeks |
| **Freqtrade Offload** | 8 | High | 3-4 weeks |
| **Trikeshed Extraction** | 8 | Medium | 4-6 weeks |
| **QUIC/DHT Mesh** | 18 | Low | Deferred |
| **ANE Hardware** | 10 | Low | Deferred |

**Total Immediate Tasks:** 39 (excluding QUIC/DHT and ANE)
**Total Deferred:** 28

---

## Priority Framework

### P0 - Critical (Weeks 1-2)
Tasks that directly impact model quality and trading reliability:
- Calibration improvements (MT1, MT4-MT9)
- Validation smoke scripts (VQ3)
- Blocker tracking (VQ6)

### P1 - High (Weeks 3-4)
Tasks for integration and deployment:
- Cost-aware objective (MT10-MT12)
- Model versioning (MT18)
- Freqtrade integration (FO1-FO3)

### P2 - Medium (Weeks 5-8)
Performance and extraction tasks:
- Kotlin validation (TE3, TE7)
- Native compilation (TE9)
- Load testing (FO6)

### P3 - Deferred
- QUIC/DHT mesh transport (18 tasks)
- ANE hardware training (10 tasks)

---

## Phase 2A: Calibration & Quality (Weeks 1-2)

### MT1: Calibration Sensitivity Sweep

**Goal:** Understand calibration behavior across parameter ranges.

**Implementation:**
```python
# backend/src/calibration_sweep.py

@dataclass
class CalibrationSweepConfig:
    min_scale_values: List[float] = field(default_factory=lambda: [0.1, 0.5, 1.0, 2.0])
    confidence_bin_edges: List[float] = field(default_factory=lambda: [0.0, 0.3, 0.5, 0.7, 1.0])
    sample_windows: List[int] = field(default_factory=lambda: [64, 128, 256, 512])
    symbols: List[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
    timeframes: List[Timeframe] = field(default_factory=lambda: [Timeframe.ONE_HOUR])
    output_dir: str = "/Users/jim/work/curly-succotash/logs/calibration_sweep"

@dataclass
class SweepResult:
    config: CalibrationSweepConfig
    parameter_combinations: List[Dict[str, Any]]
    metrics_per_combination: Dict[str, CalibrationMetrics]
    best_parameters: Dict[str, Any]
    sensitivity_analysis: Dict[str, float]  # Parameter -> sensitivity score
    
class CalibrationSweeper:
    """Run calibration sensitivity sweeps."""
    
    def run_sweep(self, config: CalibrationSweepConfig) -> SweepResult:
        # Grid search over parameters
        # Evaluate calibration quality for each combination
        # Compute sensitivity (how much metrics change per parameter)
        # Identify robust parameter regions
```

**Artifacts:**
- `backend/src/calibration_sweep.py` (new, ~400 lines)
- `backend/src/tests/test_calibration_sweep.py` (new, ~200 lines)
- `logs/calibration_sweep/` directory with results

**Acceptance Criteria:**
- [ ] Grid search completes for all parameter combinations
- [ ] Sensitivity scores computed for each parameter
- [ ] Best parameters identified and logged
- [ ] Results exported to JSON/CSV

---

### MT4: OOS Calibration Split Policy

**Goal:** Explicit regime and time windows for out-of-sample calibration.

**Implementation:**
```python
# backend/src/oos_calibration.py

@dataclass
class OOSplitPolicy:
    """Out-of-sample split policy with regime awareness."""
    
    # Time-based splits
    train_ratio: float = 0.6
    calibration_ratio: float = 0.2
    test_ratio: float = 0.2
    
    # Regime-aware constraints
    min_regimes_per_split: int = 2  # Each split must cover N regimes
    ensure_regime_balance: bool = True  # Stratified by regime
    
    # Time constraints
    min_days_per_split: int = 30
    no_future_leakage: bool = True  # Strict temporal ordering
    
    def create_splits(
        self,
        data: List[Candle],
        regime_labels: List[str]
    ) -> Tuple[Split, Split, Split]:
        """Create train/calibration/test splits with regime coverage."""
```

**Artifacts:**
- `backend/src/oos_calibration.py` (new, ~350 lines)
- `coordination/runtime/oos_split_config.json` (new)

**Acceptance Criteria:**
- [ ] Splits respect temporal ordering
- [ ] Each split has required regime coverage
- [ ] Configuration-driven policy
- [ ] Validation tests pass

---

### MT5: Calibration Governor Cadence

**Goal:** Trigger calibration only when needed, not every cycle.

**Implementation:**
```python
# backend/src/calibration_governor.py

class CalibrationTrigger(Enum):
    SCHEDULED = "scheduled"
    DRIFT_DETECTED = "drift_detected"
    PERFORMANCE_DROP = "performance_drop"
    REGIME_CHANGE = "regime_change"
    MANUAL = "manual"

@dataclass
class GovernorConfig:
    # Scheduled cadence
    min_hours_between_calibration: int = 24
    max_hours_between_calibration: int = 168  # Weekly max
    
    # Drift detection
    drift_threshold: float = 0.15  # Trigger if calibration drift > 15%
    drift_window_hours: int = 6
    
    # Performance triggers
    performance_drop_threshold: float = 0.20  # Trigger if perf drops 20%
    performance_window_hours: int = 12
    
    # Regime triggers
    trigger_on_regime_change: bool = True
    min_samples_in_regime: int = 100  # Don't calibrate on tiny regimes

class CalibrationGovernor:
    """Decides when calibration should run."""
    
    def should_calibrate(
        self,
        last_calibration_time: datetime,
        current_drift: float,
        recent_performance: float,
        regime_changed: bool
    ) -> Tuple[bool, CalibrationTrigger]:
        """Evaluate triggers and decide if calibration is needed."""
```

**Artifacts:**
- `backend/src/calibration_governor.py` (new, ~300 lines)
- `backend/src/tests/test_calibration_governor.py` (new, ~150 lines)

**Acceptance Criteria:**
- [ ] Governor prevents excessive calibration
- [ ] Triggers on drift, performance drop, regime change
- [ ] Respects min/max cadence
- [ ] Logged decisions with reasons

---

### MT6: Confidence Calibration

**Goal:** Calibrate confidence scores, not just move magnitude.

**Implementation:**
```python
# backend/src/confidence_calibration.py

@dataclass
class ConfidenceCalibrationResult:
    # Reliability diagram data
    confidence_bins: List[float]  # [0.0, 0.1, ..., 1.0]
    actual_accuracies: List[float]  # Actual accuracy in each bin
    counts_per_bin: List[int]
    
    # Metrics
    calibration_error: float  # Expected Calibration Error (ECE)
    sharpness: float  # How concentrated predictions are
    resolution: float  # How well confidence discriminates
    
    # Correction mapping
    raw_to_calibrated: Dict[float, float]  # Lookup table

class ConfidenceCalibrator:
    """Calibrate model confidence scores."""
    
    def fit(self, predictions: List[float], confidences: List[float], actuals: List[bool]):
        """Fit calibration mapping using isotonic regression or Platt scaling."""
        
    def calibrate(self, raw_confidence: float) -> float:
        """Apply calibration to raw confidence."""
        
    def get_reliability_diagram(self) -> ReliabilityDiagram:
        """Generate reliability diagram data."""
```

**Artifacts:**
- `backend/src/confidence_calibration.py` (new, ~400 lines)
- `backend/src/tests/test_confidence_calibration.py` (new, ~200 lines)

**Acceptance Criteria:**
- [ ] Reliability diagrams generated
- [ ] ECE metric computed
- [ ] Calibration mapping applied
- [ ] Visualization exportable

---

### MT7: Regime-Aware Threshold Scheduling

**Goal:** Adjust decision thresholds based on detected regime.

**Implementation:**
```python
# backend/src/regime_thresholds.py

@dataclass
class RegimeThresholds:
    """Thresholds for a specific regime."""
    regime: str
    confidence_threshold: float
    position_size_modifier: float
    stop_loss_multiplier: float
    take_profit_multiplier: float

class ThresholdScheduler:
    """Select thresholds based on regime."""
    
    def __init__(self, threshold_configs: List[RegimeThresholds]):
        self.thresholds_by_regime = {t.regime: t for t in threshold_configs}
        
    def get_thresholds(self, detected_regimes: List[str]) -> RegimeThresholds:
        """Get thresholds for current regime mix."""
        
    def adjust_for_uncertainty(self, base_thresholds: RegimeThresholds, uncertainty: float):
        """Widen thresholds under high uncertainty."""
```

**Artifacts:**
- `backend/src/regime_thresholds.py` (new, ~250 lines)
- `coordination/runtime/regime_thresholds.json` (new)

**Acceptance Criteria:**
- [ ] Thresholds defined per regime
- [ ] Smooth interpolation for mixed regimes
- [ ] Uncertainty-aware adjustment
- [ ] Configuration-driven

---

### MT8: Cooldown and Hold Policy

**Goal:** Tune cooldown/hold by symbol and volatility.

**Implementation:**
```python
# backend/src/cooldown_policy.py

@dataclass
class CooldownConfig:
    symbol: str
    volatility_bucket: str  # LOW, MED, HIGH
    min_cooldown_minutes: int
    max_cooldown_minutes: int
    hold_period_minutes: int
    
class CooldownManager:
    """Track and enforce cooldowns."""
    
    def record_trade(self, symbol: str, exit_time: datetime, pnl: float):
        """Record trade for cooldown tracking."""
        
    def is_in_cooldown(self, symbol: str, current_time: datetime) -> bool:
        """Check if symbol is in cooldown."""
        
    def get_remaining_cooldown(self, symbol: str, current_time: datetime) -> int:
        """Get remaining cooldown seconds."""
        
    def get_hold_policy(self, symbol: str, volatility: str) -> CooldownConfig:
        """Get hold policy for symbol/volatility."""
```

**Artifacts:**
- `backend/src/cooldown_policy.py` (new, ~300 lines)
- `coordination/runtime/cooldown_config.json` (new)

**Acceptance Criteria:**
- [ ] Cooldowns tracked per symbol
- [ ] Volatility-aware policies
- [ ] Enforcement in trading path
- [ ] Metrics on cooldown impact

---

### MT9: Calibration Drift Monitoring

**Goal:** Detect and auto-expire stale calibration artifacts.

**Implementation:**
```python
# backend/src/drift_monitor.py

@dataclass
class DriftMetrics:
    timestamp: datetime
    population_stability_index: float  # PSI
    kl_divergence: float
    calibration_error_change: float
    days_since_calibration: int

class DriftMonitor:
    """Monitor calibration drift over time."""
    
    def compute_psi(self, expected_dist: List[float], actual_dist: List[float]) -> float:
        """Compute Population Stability Index."""
        
    def detect_drift(self, current_metrics: DriftMetrics) -> DriftAlert:
        """Check if drift exceeds thresholds."""
        
    def should_expire_artifacts(self, artifact_age_days: int, drift_level: float) -> bool:
        """Decide if calibration artifacts should be expired."""
        
class DriftAlert:
    level: str  # LOW, MEDIUM, HIGH, CRITICAL
    drift_type: str
    recommended_action: str
```

**Artifacts:**
- `backend/src/drift_monitor.py` (new, ~350 lines)
- `backend/src/tests/test_drift_monitor.py` (new, ~150 lines)

**Acceptance Criteria:**
- [ ] PSI and KL divergence computed
- [ ] Drift alerts generated
- [ ] Auto-expire logic implemented
- [ ] Dashboard metrics exported

---

### VQ3: Smoke Scripts

**Goal:** Scripts that produce real artifacts and fail on missing evidence.

**Implementation:**
```bash
# backend/scripts/smoke_test_training.sh
#!/bin/bash
set -e

# Run minimal training episode
python -m backend.src.run_corpus_evaluation \
  --num-episodes 2 \
  --max-training-seconds 60 \
  --output-dir /tmp/smoke_test

# Verify artifacts exist
test -f /tmp/smoke_test/training_result.json || exit 1
test -f /tmp/smoke_test/episode_0.json || exit 1
test -f /tmp/smoke_test/leaderboard.json || exit 1

# Verify artifacts are non-empty and valid JSON
python -c "import json; json.load(open('/tmp/smoke_test/training_result.json'))" || exit 1

echo "✓ Smoke test passed"
```

**Artifacts:**
- `backend/scripts/smoke_test_training.sh` (new)
- `backend/scripts/smoke_test_hrm.sh` (new)
- `backend/scripts/smoke_test_replay.sh` (new)

**Acceptance Criteria:**
- [ ] Scripts fail on missing artifacts
- [ ] Scripts verify artifact validity
- [ ] CI integration
- [ ] Fast execution (< 5 min)

---

### VQ6: Blocker Tracking by Repo

**Goal:** Track blockers with owners and next artifacts.

**Implementation:**
Update `coordination/runtime/blocker_tracking.md` with structured format:

```markdown
## Active Blockers

| ID | Repo | Description | Owner | Next Artifact | ETA | Status |
|----|------|-------------|-------|---------------|-----|--------|
| CS-001 | curly-succotash | Real HRM model adapter | @jim | shadow_model_adapter.py | 2026-03-13 | In Progress |
| MF-001 | moneyfan | Cost-aware objective | @jim | cost_aware_loss.py | 2026-03-20 | Pending |
```

**Artifacts:**
- `coordination/runtime/blocker_tracking.md` (updated)
- `coordination/runtime/blocker_schema.json` (new)

---

## Phase 2B: Training Objectives (Weeks 3-4)

### MT10: Cost-Aware Trade-Head Objective

**Goal:** Training objective that reflects actual trading costs.

**Implementation:**
```python
# backend/src/cost_aware_objective.py

@dataclass
class TradingCostModel:
    commission_pct: float = 0.1
    slippage_pct: float = 0.05
    market_impact_pct: float = 0.02
    funding_rate: Optional[float] = None

class CostAwareLoss:
    """Loss function that incorporates trading costs."""
    
    def __init__(self, cost_model: TradingCostModel):
        self.costs = cost_model
        
    def compute_loss(
        self,
        predicted_signals: Tensor,
        actual_returns: Tensor,
        predicted_positions: Tensor
    ) -> Tensor:
        """
        Compute loss = prediction_error + transaction_costs + risk_penalty
        """
```

**Artifacts:**
- `backend/src/cost_aware_objective.py` (new, ~400 lines)
- `backend/src/tests/test_cost_aware_loss.py` (new, ~200 lines)

---

### MT11: Increase Trade-Step Usage

**Goal:** More trade-step optimization, less world-model only.

**Implementation:**
Integrate trade-head more heavily into training loop.

**Artifacts:**
- Updates to `backend/src/training_harness.py`
- Updates to `backend/src/synthetic_gates.py`

---

### MT12: Trade-Head Targets for TP/SL Realism

**Goal:** Better calibration of take-profit/stop-loss targets.

**Implementation:**
```python
# backend/src/trade_head_calibration.py

class TradeHeadCalibrator:
    """Calibrate TP/SL targets based on volatility and regime."""
    
    def compute_tp_sl(
        self,
        signal: Signal,
        volatility: float,
        regime: str
    ) -> Tuple[float, float]:
        """Calculate realistic TP/SL levels."""
```

---

## Phase 2C: Model Operations (Weeks 3-4)

### MT18: Model Versioning and Provenance

**Goal:** Track model versions, provenance, rollback, audit logging.

**Implementation:**
```python
# backend/src/model_registry.py

@dataclass
class ModelVersion:
    version_id: str
    created_at: datetime
    training_config: Dict[str, Any]
    training_data_hash: str
    metrics: Dict[str, float]
    artifact_paths: Dict[str, str]
    parent_version: Optional[str]
    tags: List[str]

class ModelRegistry:
    """Manage model versions and deployment."""
    
    def register_model(self, artifacts: Dict[str, str], metrics: Dict) -> ModelVersion:
        """Register a new model version."""
        
    def promote_to_production(self, version_id: str):
        """Promote version to production."""
        
    def rollback(self, target_version_id: str):
        """Rollback to previous version."""
        
    def get_audit_log(self) -> List[Dict]:
        """Get audit log of all model changes."""
```

**Artifacts:**
- `backend/src/model_registry.py` (new, ~500 lines)
- `backend/src/tests/test_model_registry.py` (new, ~250 lines)
- `logs/model_registry/` directory

---

### MT19: Degradation Dashboards and Alerts

**Goal:** Monitor and alert on model degradation.

**Implementation:**
```python
# backend/src/model_monitoring.py

class ModelMonitor:
    """Monitor model performance and detect degradation."""
    
    def check_degradation(self, recent_metrics: List[Metric]) -> DegradationAlert:
        """Detect performance degradation."""
        
    def generate_dashboard_data(self) -> DashboardSnapshot:
        """Generate data for monitoring dashboard."""
```

---

## Phase 2D: Freqtrade Integration (Weeks 3-4)

### FO1: Contract Proxy Mapping

**Goal:** Tune proxy mapping against real Freqtrade schema.

### FO2: Bridge Response Validation

**Goal:** Validate under production traffic.

### FO3: Compare-Report Helpers

**Goal:** Review helpers and diff indexing.

---

## Phase 2E: Trikeshed Validation (Weeks 5-6)

### TE3: Kotlin vs Python Validation

**Goal:** Validate Kotlin outputs against Python reference.

### TE7: Kotlin Performance Benchmark

**Goal:** Benchmark Kotlin vs pandas performance.

### TE9: Native Cinterop Verification

**Goal:** Verify native compilation.

---

## Deferred Workstreams

### QUIC/DHT Mesh (18 tasks)
Deferred until trading system is fully operational.

### ANE Hardware (10 tasks)
Deferred pending ANE viability decision.

---

## Implementation Timeline

### Week 1-2 (2026-03-13)
- [x] MT1: Calibration sensitivity sweep
- [x] MT4: OOS calibration split policy
- [x] MT5: Calibration governor cadence
- [x] MT6: Confidence calibration
- [x] MT7: Regime-aware thresholds
- [x] MT8: Cooldown and hold policy
- [x] MT9: Calibration drift monitoring
- [x] VQ3: Smoke scripts
- [x] VQ6: Blocker tracking

### Week 3-4 (2026-03-27)
- [ ] MT10: Cost-aware trade-head objective
- [ ] MT11: Increase trade-step usage
- [ ] MT12: Trade-head TP/SL realism
- [ ] MT18: Model versioning and provenance
- [ ] MT19: Degradation dashboards
- [ ] FO1: Contract proxy mapping
- [ ] FO2: Bridge validation
- [ ] FO3: Compare-report helpers

### Week 5-6 (2026-04-10)
- [ ] TE3: Kotlin validation
- [ ] TE7: Kotlin benchmark
- [ ] TE9: Native cinterop
- [ ] FO6: Load testing

---

## Success Criteria

### Phase 2A Complete When:
- [ ] All 9 calibration/quality tasks implemented
- [ ] Tests passing for all new modules
- [ ] Smoke scripts integrated in CI
- [ ] Blocker tracking updated weekly

### Phase 2B Complete When:
- [ ] Cost-aware objective implemented and tested
- [ ] Trade-step usage > 50% of training
- [ ] TP/SL calibration validated

### Phase 2C Complete When:
- [ ] Model registry operational
- [ ] Versioning and rollback working
- [ ] Dashboard showing live metrics

### Phase 2D Complete When:
- [ ] Freqtrade bridge validated
- [ ] Integration tests passing
- [ ] Retirement documentation drafted

---

## Risk Mitigation

### Technical Risks
- **Calibration complexity:** Start with simple grid search, iterate
- **Model registry scope:** MVP first, enhance later
- **Freqtrade schema drift:** Validate against live instance

### Schedule Risks
- **Scope creep:** Stick to prioritized list
- **Dependencies:** Parallelize independent tasks
- **Testing debt:** Write tests alongside implementation

---

## Resource Allocation

### Week 1-2
- Calibration sweep: 2 days
- OOS splits: 1 day
- Governor: 1 day
- Confidence calibration: 2 days
- Regime thresholds: 1 day
- Cooldown policy: 1 day
- Drift monitoring: 2 days
- Smoke scripts: 1 day
- Blocker tracking: 0.5 days

**Total:** ~12 person-days

### Week 3-4
- Cost-aware objective: 3 days
- Trade-step usage: 2 days
- TP/SL calibration: 2 days
- Model registry: 3 days
- Freqtrade integration: 2 days

**Total:** ~12 person-days

---

## Next Steps

1. **Start MT1** - Calibration sensitivity sweep (highest priority)
2. **Update blocker tracking** - VQ6 (quick win)
3. **Create smoke scripts** - VQ3 (enables validation)
4. **Proceed through MT4-MT9** - Calibration foundation
5. **Move to MT10-MT12** - Training objectives
6. **Implement MT18** - Model operations
7. **Complete Freqtrade integration** - FO1-FO3

---

**Status:** Ready for Implementation
**Next Review:** 2026-03-13
**Owner:** @jim
