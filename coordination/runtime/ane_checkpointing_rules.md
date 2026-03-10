# ANE Checkpoint and Validation Rules

## Context
When performing training or long-running evaluation inferences using Apple Neural Engine (ANE) via MLX/CoreML, the compilation overhead ("compile budget") is severe. Frequent context switching or pipeline interruptions can cause out-of-memory (OOM) events within the graph compiler or result in massive throughput drops. Therefore, saving and resuming state must adhere to strict behavioral rules.

## Rule 1: AOT Compilation Only
The `coremltools` translation pass must occur strictly Ahead-of-Time (AOT), before the main training loop resumes. Checkpointing and restarting must *never* invoke just-in-time graph recompilation.

## Rule 2: Shape Invariance on Resume
A resumed checkpoint must declare the exact same `input_shapes` and `output_shapes` as the initial run (defined in `moneyfan.ane.export.v1`). If a batch size changes across a restart, the graph is invalidated and the run fails.

## Rule 3: Zero-State Offloading
If the architecture maintains internal recurrent state (e.g., KV caches for Causal Transformers), this state must be explicitly returned to CPU memory at the checkpoint boundary and serialized. The ANE graph itself must be stateless, accepting the previous hidden state as a raw input tensor on resume.

## Validation Protocol
Any `autoresearch` execution targeting ANE must implement a smoke script that:
1. Compiles the model.
2. Ingests 10 sequences.
3. Saves a checkpoint.
4. Kills the process.
5. Resumes from the checkpoint.
6. Ingests 10 more sequences.
7. Asserts that the cumulative `cpu_fallback_count` (defined in `moneyfan.ane.metrics.v1`) remains `0` across the entire lifecycle.

*Generated: 2026-03-12*
