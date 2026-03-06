# Artifact Requirements for Milestone Validation

**Version:** 1.0
**Effective Date:** 2026-03-06
**Policy:** No milestone pass without complete artifact manifest

---

## Purpose

This document defines mandatory artifacts for each milestone category. **Verbal claims are not accepted.** All milestone validations require machine-readable artifacts with provenance metadata.

---

## Artifact Categories

### 1. Training Milestones

#### M1: Convergence (4x4 width)
**Required Artifacts:**
- [ ] `training_result.json` - Full training metrics
- [ ] `tensorboard_events.tfevents.*` - Loss curves, gradient stats
- [ ] `checkpoint_final.safetensors` - Final model weights
- [ ] `synthetic_gates_results.json` - Identity, sine gate performance
- [ ] `leaderboard_final.json` - Strategy rankings

**Validation Script:**
```bash
python3 /Users/jim/work/moneyfan/scripts/validate_milestone.py \
  --milestone M1 \
  --artifact-dir /Users/jim/work/moneyfan/results/convergence_4x4 \
  --output /Users/jim/work/moneyfan/results/convergence_4x4/validation_report.json
```

**Schema:** `/Users/jim/work/moneyfan/schemas/training_result_v1.json`

---

#### M2: HRM 24x24 Shadow Mode
**Required Artifacts:**
- [ ] `shadow_mode_config.json` - Shadow mode configuration
- [ ] `baseline_vs_hrm_daily/*.json` - Daily PnL comparisons (min 7 days)
- [ ] `scoreboard_archive/*.md` - Daily scoreboard outputs
- [ ] `veto_decisions.json` - All veto decisions with reasons
- [ ] `drawdown_monitor.json` - Drawdown tracking with kill-switch status

**Validation Script:**
```bash
python3 /Users/jim/work/curly-succotash/scripts/validate_shadow_mode.py \
  --artifact-dir /Users/jim/work/curly-succotash/logs/shadow_mode \
  --min-days 7 \
  --output /Users/jim/work/curly-succotash/logs/shadow_mode/validation_report.json
```

**Schema:** `/Users/jim/work/curly-succotash/schemas/shadow_mode_result_v1.json`

---

#### M3: HRM Synthetic Competency
**Required Artifacts:**
- [ ] `identity_gate_results.json` - Identity task performance
- [ ] `sine_gate_results.json` - Sine prediction (amplitude, phase, frequency)
- [ ] `feature_plus_1_results.json` - Single-step prediction
- [ ] `baseline_comparison.json` - HRM vs persistence/EMA/linear
- [ ] `failure_outcomes.json` - Explicit FAIL_* records

**Validation Script:**
```bash
python3 /Users/jim/work/moneyfan/scripts/validate_synthetic_gates.py \
  --artifact-dir /Users/jim/work/moneyfan/results/synthetic_gates \
  --require-baseline-beat true \
  --output /Users/jim/work/moneyfan/results/synthetic_gates/validation_report.json
```

**Schemas:**
- `/Users/jim/work/moneyfan/schemas/identity_gate_v1.json`
- `/Users/jim/work/moneyfan/schemas/sine_gate_v1.json`
- `/Users/jim/work/moneyfan/schemas/baseline_comparison_v1.json`

---

#### M4: Walk-Forward Validation
**Required Artifacts:**
- [ ] `walk_forward_folds.json` - OOS fold definitions
- [ ] `fold_*_results.json` - Individual fold results (min 5 folds)
- [ ] `cross_regime_analysis.json` - Performance by regime
- [ ] `promotion_readiness_score.json` - Composite readiness metric

**Validation Script:**
```bash
python3 /Users/jim/work/moneyfan/scripts/validate_walk_forward.py \
  --artifact-dir /Users/jim/work/moneyfan/results/walk_forward \
  --min-folds 5 \
  --output /Users/jim/work/moneyfan/results/walk_forward/validation_report.json
```

**Schema:** `/Users/jim/work/moneyfan/schemas/walk_forward_result_v1.json`

---

### 2. Integration Milestones

#### I1: Freqtrade Bridge Integration
**Required Artifacts:**
- [ ] `contract_proxy_mapping.json` - Endpoint schema mapping
- [ ] `bridge_test_responses.json` - End-to-end validation
- [ ] `load_test_results.json` - Performance under traffic
- [ ] `failure_injection_tests.json` - Rollback behavior

**Validation Script:**
```bash
python3 /Users/jim/work/freqtrade/scripts/validate_bridge.py \
  --artifact-dir /Users/jim/work/freqtrade/user_data/hrm_bridge \
  --output /Users/jim/work/freqtrade/user_data/hrm_bridge/validation_report.json
```

---

#### I2: HRM Model Serving
**Required Artifacts:**
- [ ] `model_serving_config.yaml` - Serving configuration
- [ ] `inference_latency_p99.json` - Latency metrics
- [ ] `throughput_benchmark.json` - Queries/sec
- [ ] `rollback_test_results.json` - Rollback validation

**Validation Script:**
```bash
python3 /Users/jim/work/freqtrade/scripts/validate_model_serving.py \
  --artifact-dir /Users/jim/work/freqtrade/user_data/hrm_serving \
  --latency-target-ms 100 \
  --output /Users/jim/work/freqtrade/user_data/hrm_serving/validation_report.json
```

---

#### I3: Kotlin TrikeShed Integration
**Required Artifacts:**
- [ ] `indicator_mapping_spec.md` - Python → Kotlin mapping
- [ ] `kotlin_vs_python_outputs.json` - Output validation
- [ ] `performance_benchmark.json` - Kotlin vs pandas timing
- [ ] `duckdb_cinterop_tests.json` - Native interop validation

**Validation Script:**
```bash
bash /Users/jim/work/trikeshed/scripts/validate_trikeshed.sh \
  --artifact-dir /Users/jim/work/trikeshed/results/integration \
  --output /Users/jim/work/trikeshed/results/integration/validation_report.json
```

---

### 3. Promotion Milestones

#### P1: Shadow → Veto Only
**Required Artifacts:**
- [ ] `shadow_period_summary.json` - Full shadow period metrics
- [ ] `baseline_beat_evidence.json` - Statistical significance test
- [ ] `veto_reason_analysis.json` - Veto patterns and frequencies
- [ ] `drawdown_compliance.json` - Kill-switch never triggered

**Validation Script:**
```bash
python3 /Users/jim/work/curly-succotash/scripts/validate_promotion.py \
  --from-stage shadow \
  --to-stage veto_only \
  --artifact-dir /Users/jim/work/curly-succotash/logs/promotion_p1 \
  --output /Users/jim/work/curly-succotash/logs/promotion_p1/validation_report.json
```

**Schema:** `/Users/jim/work/curly-succotash/schemas/promotion_evidence_v1.json`

---

#### P2: Veto Only → Size Capped
**Required Artifacts:**
- [ ] `veto_period_summary.json` - Full veto period metrics
- [ ] `counterfactual_displacement.json` - What HRM blocked
- [ ] `pnl_impact_analysis.json` - PnL of blocked trades
- [ ] `regime_coverage.json` - Performance across regimes

---

#### P3: Size Capped → Primary
**Required Artifacts:**
- [ ] `size_capped_period_summary.json` - Full period metrics
- [ ] `sharpe_ratio_evidence.json` - Sharpe > 1.5 statistical test
- [ ] `slippage_analysis.json` - Realistic execution costs
- [ ] `operator_runbook_archive/` - All daily runbooks

---

## Artifact Manifest Format

Every artifact directory MUST include `manifest.json`:

```json
{
  "manifest_version": "1.0",
  "milestone_id": "M2",
  "milestone_name": "HRM 24x24 Shadow Mode",
  "created_at": "2026-03-06T12:34:56Z",
  "created_by": "training_harness_v1.2.3",
  "artifacts": [
    {
      "filename": "shadow_mode_config.json",
      "sha256": "abc123...",
      "size_bytes": 1234,
      "schema_version": "1.0",
      "required": true
    }
  ],
  "validation": {
    "script": "validate_shadow_mode.py",
    "status": "PASS",
    "validated_at": "2026-03-06T12:35:00Z",
    "validator_version": "1.0.0"
  },
  "provenance": {
    "git_commit": "abc123def456...",
    "git_branch": "main",
    "config_hash": "xyz789...",
    "data_sources": ["HISTORICAL_BINANCE_VISION_ARCHIVED"],
    "exchange_targets": ["BINANCE_SPOT_MAINNET"]
  }
}
```

---

## Validation Rules

### Automatic Rejection Conditions

A milestone validation is **automatically rejected** if:

1. **Missing required artifact** - Any artifact marked `required: true` absent
2. **Schema validation failure** - Artifact does not match declared schema
3. **Checksum mismatch** - SHA256 does not match manifest
4. **Incomplete provenance** - Missing git commit, config hash, or data sources
5. **Fake numbers detected** - Loss/metrics are hardcoded or suspicious (e.g., exactly 0.0000)
6. **Insufficient data** - Less than minimum days/trades/folds

### Validation Script Requirements

All validation scripts must:

1. **Exit non-zero on failure** - `sys.exit(1)` on validation failure
2. **Produce machine-readable output** - JSON report at specified path
3. **Be idempotent** - Can be re-run with same result
4. **Support dry-run** - `--dry-run` flag for testing
5. **Log to stdout** - Human-readable progress messages

---

## Artifact Storage Locations

| Category | Base Path | Owner |
|----------|-----------|-------|
| Training | `/Users/jim/work/moneyfan/results/` | moneyfan |
| Shadow Mode | `/Users/jim/work/curly-succotash/logs/shadow_mode/` | curly-succotash |
| Integration | `/Users/jim/work/freqtrade/user_data/hrm_*/` | freqtrade |
| Kotlin | `/Users/jim/work/trikeshed/results/` | trikeshed |
| Promotion | `/Users/jim/work/curly-succotash/logs/promotion_*/` | curly-succotash |

---

## Enforcement

**Policy:** No milestone advancement without passing validation.

- Training harness will not export models without M1-M4 artifacts
- Promotion ladder will not advance without P1-P3 artifacts
- Freqtrade bridge will not serve models without I1-I2 artifacts
- TrikeShed will not replace pandas without I3 artifacts

**Audit Trail:** All validation reports are stored permanently in:
- `/Users/jim/work/curly-succotash/logs/validations/`
- Git-tracked manifest index: `coordination/runtime/artifact_manifest_index.json`

---

## Quick Reference

### Before Running Training
```bash
# 1. Verify artifact directories exist
mkdir -p /Users/jim/work/moneyfan/results/{convergence_4x4,synthetic_gates,walk_forward}

# 2. Verify schemas are available
ls /Users/jim/work/moneyfan/schemas/*.json

# 3. Verify validation scripts are executable
chmod +x /Users/jim/work/moneyfan/scripts/validate_*.py
```

### After Training Completes
```bash
# 1. Generate manifest
python3 scripts/generate_manifest.py \
  --result-dir /Users/jim/work/moneyfan/results/convergence_4x4 \
  --output /Users/jim/work/moneyfan/results/convergence_4x4/manifest.json

# 2. Run validation
python3 scripts/validate_milestone.py \
  --milestone M1 \
  --artifact-dir /Users/jim/work/moneyfan/results/convergence_4x4

# 3. Check validation status
cat /Users/jim/work/moneyfan/results/convergence_4x4/validation_report.json | jq .status
```

### Before Promotion
```bash
# 1. Verify all required artifacts present
python3 scripts/check_artifacts.py \
  --milestone P1 \
  --artifact-dir /Users/jim/work/curly-succotash/logs/promotion_p1

# 2. Run promotion validation
python3 scripts/validate_promotion.py \
  --from-stage shadow \
  --to-stage veto_only

# 3. Review validation report
cat /Users/jim/work/curly-succotash/logs/promotion_p1/validation_report.json
```

---

**REMEMBER:** If it's not in the artifact manifest, it didn't happen.
