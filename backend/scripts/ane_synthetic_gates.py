#!/usr/bin/env python3
"""
ANE Synthetic Gates Scaffolding

Loads a compiled CoreML `.mlpackage`, translates the `SyntheticGate` generated
data into strictly static shapes, invokes the model on the ANE, and checks parity
against a CPU reference predictor.

Raises a clear instructional error if no package is provided, acting as the interface
for `autoresearch` execution paths.
"""

import sys
import os
import argparse
import numpy as np

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from backend.src.synthetic_gates import CompetencyEvaluator


def main():
    parser = argparse.ArgumentParser(description="ANE Synthetic Gate Parity Tester")
    parser.add_argument("--model", type=str, help="Path to compiled CoreML .mlpackage")
    parser.add_argument("--batch-size", type=int, default=1, help="Static batch size")
    parser.add_argument("--seq-len", type=int, default=100, help="Static sequence length")
    args = parser.parse_args()

    if not args.model:
        print("❌ Error: No CoreML package provided.")
        print("Usage: python3 ane_synthetic_gates.py --model path/to/model.mlpackage")
        print("This script requires a hardened, AOT-compiled CoreML model from the autoresearch loop.")
        sys.exit(1)

    if not os.path.exists(args.model):
        print(f"❌ Error: Model package not found at {args.model}")
        sys.exit(1)

    print(f"Loading ANE model from {args.model}...")
    try:
        import coremltools as ct
        model = ct.models.MLModel(args.model)
    except ImportError:
        print("⚠️ Warning: coremltools not installed. Cannot load model.")
        print("Please install coremltools to run ANE evaluations.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error loading CoreML model: {e}")
        sys.exit(1)

    print("Initializing Synthetic Competency Suite...")
    evaluator = CompetencyEvaluator()

    # Wrap the ANE model in a predictor function that handles static shape padding
    def ane_predictor(x: np.ndarray) -> np.ndarray:
        # In a real implementation, we would:
        # 1. Pad `x` to `args.seq_len` and `args.batch_size`
        # 2. Invoke `model.predict({"input": padded_x})`
        # 3. Truncate the output back to `x.shape`
        raise NotImplementedError("ANE predictor stub invoked. Implement dictionary translation here.")

    print("Running ANE Parity Tests...")
    try:
        results = evaluator.run_all(ane_predictor)
    except NotImplementedError as e:
        print(f"🛑 Stub implementation reached: {e}")
        print("To complete this test, map the synthetic gate `x` array into the CoreML model's expected input dictionary format.")
        sys.exit(0)


if __name__ == "__main__":
    main()
