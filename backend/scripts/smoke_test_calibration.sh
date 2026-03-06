#!/bin/bash
#
# Smoke Test - Calibration Modules
#
# Tests calibration modules and verifies they produce valid outputs.
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
OUTPUT_DIR="${SMOKE_TEST_OUTPUT_DIR:-/tmp/smoke_test_calibration}"

echo "========================================="
echo "Smoke Test: Calibration Modules"
echo "========================================="
echo "Output directory: $OUTPUT_DIR"
echo ""

# Skip removal of system tmp to avoid Seatbelt issues
mkdir -p "$OUTPUT_DIR"

cd "$PROJECT_ROOT"

# Test calibration sweep
echo "Testing calibration sweep..."
python3 << EOF
import sys
sys.path.insert(0, '$PROJECT_ROOT')

from backend.src.calibration_sweep import CalibrationSweepConfig, CalibrationSweeper
from backend.src.models import Timeframe

config = CalibrationSweepConfig(
    min_scale_values=[0.5, 1.0],
    confidence_bin_edges=[[0.0, 0.5, 1.0]],
    sample_windows=[64],
    symbols=["BTCUSDT"],
    timeframes=[Timeframe.ONE_HOUR],
)

sweeper = CalibrationSweeper(seed=42)
result = sweeper.run_sweep(config)

assert result.total_combinations > 0, "No combinations evaluated"
assert result.best_parameters is not None, "No best parameters found"

print(f"✓ Calibration sweep: {result.total_combinations} combinations")
print(f"✓ Best ECE: {result.best_metrics.expected_calibration_error:.4f}")
EOF

# Test OOS splits
echo "Testing OOS splits..."
python3 << EOF
import sys
sys.path.insert(0, '$PROJECT_ROOT')

from datetime import datetime, timezone, timedelta
from backend.src.oos_calibration import OOSplitPolicy, OOSplitter
from backend.src.models import Candle, Timeframe
import numpy as np

# Create synthetic data
start_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
data = []
regimes = []

for i in range(300):
    candle = Candle(
        timestamp=start_time + timedelta(hours=i),
        open=100 + np.random.uniform(-5, 5),
        high=105 + np.random.uniform(-2, 2),
        low=95 + np.random.uniform(-2, 2),
        close=100 + np.random.uniform(-5, 5),
        volume=np.random.uniform(1000, 2000),
        symbol="BTCUSDT",
        timeframe=Timeframe.ONE_HOUR,
    )
    data.append(candle)
    regimes.append(f"REGIME_{i % 3}")

policy = OOSplitPolicy(min_regimes_per_split=1, min_samples_per_regime=10)
splitter = OOSplitter(policy)
result = splitter.create_splits(data, regimes)

assert result.train.n_samples > 0, "No train data"
assert result.calibration.n_samples > 0, "No calibration data"
assert result.test.n_samples > 0, "No test data"

print(f"✓ OOS splits: train={result.train.n_samples}, cal={result.calibration.n_samples}, test={result.test.n_samples}")
EOF

# Test confidence calibration
echo "Testing confidence calibration..."
python3 << EOF
import sys
sys.path.insert(0, '$PROJECT_ROOT')

from backend.src.confidence_calibration import ConfidenceCalibrator
import numpy as np

np.random.seed(42)
n_samples = 500
confidences = np.random.uniform(0, 1, n_samples)
actuals = np.random.binomial(1, confidences)

calibrator = ConfidenceCalibrator(method='isotonic')
calibrator.fit(confidences, actuals)

result = calibrator.get_calibration_result()
assert result is not None, "No calibration result"

print(f"✓ Confidence calibration: ECE before={result.calibration_error_before:.4f}, after={result.calibration_error_after:.4f}")
EOF

# Test calibration governor
echo "Testing calibration governor..."
python3 << EOF
import sys
sys.path.insert(0, '$PROJECT_ROOT')

from datetime import datetime, timezone, timedelta
from backend.src.calibration_governor import GovernorConfig, CalibrationGovernor

config = GovernorConfig(
    min_hours_between_calibration=24,
    max_hours_between_calibration=168,
    drift_threshold=0.15,
)

governor = CalibrationGovernor(config)

# Test initial calibration
decision = governor.should_calibrate(
    last_calibration_time=None,
    current_drift=0.0,
    recent_performance=1.0,
    regime_changed=False
)
assert decision.decision.value == "calibrate", "Should calibrate initially"

# Test skip (too soon)
now = datetime.now(timezone.utc)
decision = governor.should_calibrate(
    last_calibration_time=now - timedelta(hours=1),
    current_drift=0.05,
    recent_performance=0.95,
    regime_changed=False
)
assert decision.decision.value == "skip", "Should skip (too soon)"

# Test drift trigger
decision = governor.should_calibrate(
    last_calibration_time=now - timedelta(hours=48),
    current_drift=0.20,
    recent_performance=0.95,
    regime_changed=False
)
assert decision.decision.value == "calibrate", "Should calibrate (drift)"

print(f"✓ Calibration governor: All decision tests passed")
EOF

# Test calibration support modules
echo "Testing calibration support modules..."
python3 << EOF
import sys
sys.path.insert(0, '$PROJECT_ROOT')

from datetime import datetime, timezone, timedelta
from backend.src.calibration_support import (
    create_threshold_scheduler,
    create_cooldown_manager,
    create_drift_monitor,
)
import numpy as np

# Test threshold scheduler
scheduler = create_threshold_scheduler()
thresholds = scheduler.get_thresholds(["VOL_NORMAL"])
assert thresholds.confidence_threshold > 0, "Invalid threshold"
print(f"✓ Threshold scheduler: confidence={thresholds.confidence_threshold}")

# Test cooldown manager
cooldown_mgr = create_cooldown_manager()
cooldown_mgr.record_trade(
    symbol="BTCUSDT",
    entry_time=datetime.now(timezone.utc) - timedelta(hours=2),
    exit_time=datetime.now(timezone.utc),
    pnl=-100.0,
    pnl_percent=-0.01,
)
in_cooldown = cooldown_mgr.is_in_cooldown("BTCUSDT", datetime.now(timezone.utc))
print(f"✓ Cooldown manager: in_cooldown={in_cooldown}")

# Test drift monitor
drift_monitor = create_drift_monitor()
baseline = np.random.beta(2, 2, 1000)
drift_monitor.set_baseline(baseline, calibration_ece=0.05, calibration_time=datetime.now(timezone.utc))

current = np.random.beta(2.5, 2, 1000)
metrics = drift_monitor.get_metrics(current, current_ece=0.08)
assert metrics.population_stability_index >= 0, "Invalid PSI"
print(f"✓ Drift monitor: PSI={metrics.population_stability_index:.4f}")
EOF

echo ""
echo "========================================="
echo "✓ All calibration smoke tests PASSED"
echo "========================================="
echo ""

exit 0
