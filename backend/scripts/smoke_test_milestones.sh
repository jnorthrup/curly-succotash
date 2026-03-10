#!/bin/bash
#
# Smoke Test - Milestone Artifacts
#
# Validates that all newly implemented components (calibration sweep,
# OOS curation, synthetic gates, cost-aware objective) produce 
# valid artifacts and fail if evidence is missing.
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
OUTPUT_DIR="${SMOKE_TEST_OUTPUT_DIR:-$PROJECT_ROOT/logs/smoke_test_milestones}"

echo "========================================="
echo "Smoke Test: Milestone Artifacts"
echo "========================================="
echo "Output directory: $OUTPUT_DIR"
echo ""

mkdir -p "$OUTPUT_DIR"
cd "$PROJECT_ROOT"

# 1. Run Calibration Sweep
echo "Step 1: Running Calibration Sweep..."
python3 -m backend.src.calibration_sweep > /dev/null
SWEEP_LOG=$(ls -t logs/calibration_sweep/sweep_result_*.json | head -n 1)
if [ ! -f "$SWEEP_LOG" ]; then
    echo "❌ FAIL: Calibration sweep result not found in logs/calibration_sweep/"
    exit 1
fi
echo "✓ Calibration sweep result found: $SWEEP_LOG"
cp "$SWEEP_LOG" "$OUTPUT_DIR/calibration_sweep_result.json"

# 2. Run OOS Dataset Curation
echo "Step 2: Curating OOS Dataset..."
python3 backend/scripts/curate_oos_dataset.py > /dev/null
CURATED_MANIFEST="logs/oos_validation/curated_dataset_manifest.json"
if [ ! -f "$CURATED_MANIFEST" ]; then
    echo "❌ FAIL: Curated dataset manifest not found: $CURATED_MANIFEST"
    exit 1
fi
echo "✓ OOS dataset manifest found."
cp "$CURATED_MANIFEST" "$OUTPUT_DIR/curated_dataset_manifest.json"

# 3. Run Synthetic Gates Competency Suite
echo "Step 3: Running Synthetic Gates Competency Suite..."
python3 << EOF
import sys
import os
sys.path.insert(0, '$PROJECT_ROOT')
from backend.src.synthetic_gates import CompetencyEvaluator, IdentityGate
import numpy as np

evaluator = CompetencyEvaluator()
# Use a predictor that is perfect for Identity but fails others (like zero)
def dummy_predictor(x):
    if x.shape[1] == 1: return x # Identity
    return np.zeros((x.shape[0], 1))

results = evaluator.run_all(dummy_predictor)
evaluator.save_report("$OUTPUT_DIR/synthetic_competency_report.json")
EOF

if [ ! -f "$OUTPUT_DIR/synthetic_competency_report.json" ]; then
    echo "❌ FAIL: Synthetic competency report not found."
    exit 1
fi
echo "✓ Synthetic competency report generated."

# 4. Verify Trade-Head Calibration Logic
echo "Step 4: Verifying Trade-Head Calibration Logic..."
python3 << EOF
import sys
import os
sys.path.insert(0, '$PROJECT_ROOT')
from backend.src.trade_head_calibration import TradeHeadCalibrator
import json

calibrator = TradeHeadCalibrator(fee_rate=0.001)
# Win: Direction 1, Return 0.02, Fee 0.002 -> PnL 0.018, Cost -0.018
cost = calibrator.compute_cost({"direction": 1}, {"return": 0.02})
if abs(cost - (-0.018)) > 1e-5:
    print(f"❌ FAIL: Incorrect cost calculation: {cost}")
    sys.exit(1)

# Loss: Direction 1, Return -0.02, Fee 0.002 -> PnL -0.022, Cost 0.022
cost = calibrator.compute_cost({"direction": 1}, {"return": -0.02})
if abs(cost - 0.022) > 1e-5:
    print(f"❌ FAIL: Incorrect cost calculation: {cost}")
    sys.exit(1)

# Save a sample cost artifact
with open("$OUTPUT_DIR/trade_head_cost_sample.json", "w") as f:
    json.dump({"test_cost_win": -0.018, "test_cost_loss": 0.022}, f)
EOF
echo "✓ Trade-head calibration logic verified."

# 5. Check coordination artifacts
echo "Step 5: Verifying Coordination Artifacts..."
FILES=(
    "coordination/runtime/oos_governance_policy.json"
    "coordination/runtime/mlx_smoke_profiles.json"
    "coordination/runtime/baseline_training_evidence.md"
)
for file in "${FILES[@]}"; do
    if [ ! -f "$file" ]; then
        echo "❌ FAIL: Missing coordination artifact: $file"
        exit 1
    fi
    echo "✓ Found: $file"
done

echo ""
echo "========================================="
echo "✓ ALL MILESTONE SMOKE TESTS PASSED"
echo "========================================="
echo "Artifacts preserved in: $OUTPUT_DIR"
echo ""

exit 0
