#!/bin/bash
#
# Smoke Test - Training Harness
#
# Runs a minimal training episode and verifies artifacts are created.
# Fails if any artifact is missing or invalid.
#

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="${SMOKE_TEST_OUTPUT_DIR:-/tmp/smoke_test_training}"

echo "========================================="
echo "Smoke Test: Training Harness"
echo "========================================="
echo "Output directory: $OUTPUT_DIR"
echo ""

# Clean up previous run
rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

# Run minimal training episode
echo "Running training episode..."
cd "$PROJECT_ROOT"
python3 -m backend.src.run_corpus_evaluation \
  --num-episodes 2 \
  --max-training-seconds 60 \
  --output-dir "$OUTPUT_DIR" \
  --symbols BTCUSDT \
  --timeframes 1h

echo ""
echo "Verifying artifacts..."

# Verify required artifacts exist
REQUIRED_FILES=(
    "training_result.json"
    "episode_0.json"
    "leaderboard.json"
)

for file in "${REQUIRED_FILES[@]}"; do
    filepath="$OUTPUT_DIR/$file"
    if [ ! -f "$filepath" ]; then
        echo "❌ FAIL: Missing artifact: $file"
        exit 1
    fi
    echo "✓ Found: $file"
done

# Verify artifacts are valid JSON
echo ""
echo "Validating JSON..."
for file in "${REQUIRED_FILES[@]}"; do
    filepath="$OUTPUT_DIR/$file"
    if ! python3 -c "import json; json.load(open('$filepath'))" 2>/dev/null; then
        echo "❌ FAIL: Invalid JSON in $file"
        exit 1
    fi
    echo "✓ Valid JSON: $file"
done

# Verify artifact content
echo ""
echo "Validating artifact content..."
python3 << EOF
import json
import sys

# Check training result
with open("$OUTPUT_DIR/training_result.json") as f:
    result = json.load(f)
    if "episodes_completed" not in result:
        print("❌ FAIL: training_result.json missing episodes_completed")
        sys.exit(1)
    if result["episodes_completed"] < 1:
        print("❌ FAIL: No episodes completed")
        sys.exit(1)
    print(f"✓ Training result: {result['episodes_completed']} episodes")

# Check episode result
with open("$OUTPUT_DIR/episode_0.json") as f:
    episode = json.load(f)
    if "episode_num" not in episode:
        print("❌ FAIL: episode_0.json missing episode_num")
        sys.exit(1)
    print(f"✓ Episode 0: {episode.get('candles_processed', 0)} candles")

# Check leaderboard
with open("$OUTPUT_DIR/leaderboard.json") as f:
    leaderboard = json.load(f)
    if not isinstance(leaderboard, list):
        print("❌ FAIL: leaderboard.json should be a list")
        sys.exit(1)
    print(f"✓ Leaderboard: {len(leaderboard)} strategies")

print("")
print("All content validations passed!")
EOF

echo ""
echo "========================================="
echo "✓ Smoke test PASSED"
echo "========================================="
echo ""
echo "Artifacts saved to: $OUTPUT_DIR"
echo ""

# Cleanup
# rm -rf "$OUTPUT_DIR"

exit 0
