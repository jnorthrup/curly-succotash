#!/bin/bash
#
# Run Calibration Sensitivity Sweep
#
# Generates a JSON and CSV report mapping min-scale, bin edges, and
# sample window sensitivity. Used to satisfy the training debt backlog.
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
OUTPUT_DIR="${CALIBRATION_SWEEP_OUTPUT_DIR:-$PROJECT_ROOT/logs/calibration_sweep}"

echo "========================================="
echo "Running Calibration Sensitivity Sweep"
echo "========================================="
echo "Output directory: $OUTPUT_DIR"
echo ""

mkdir -p "$OUTPUT_DIR"

cd "$PROJECT_ROOT"

# Run the sweep using the python module's main block
python3 -m backend.src.calibration_sweep

echo ""
echo "========================================="
echo "✓ Calibration sweep completed"
echo "========================================="
exit 0
