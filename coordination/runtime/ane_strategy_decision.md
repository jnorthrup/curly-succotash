# Architectural Decision Record: ANE Hardware Strategy

## Context
The project requires high-throughput hardware acceleration for the Hierarchical Risk Model (HRM). The Apple Neural Engine (ANE) provides extreme power efficiency for static tensor operations, but its utility for dynamic training loops must be evaluated against the current trading milestones.

## Decision
**The Apple Neural Engine (ANE) is officially classified as a Research Sidecar, not the primary training accelerator.**

Primary training acceleration will be provided by the Apple GPU via the MLX framework.

## Rationale
1. **Dynamic Execution Constraints:** The current trading milestones require continuous evaluation, variable-length lookbacks, and dynamic masking for the synthetic competency suite. ANE requires strict Ahead-of-Time (AOT) compilation and static shapes, resulting in severe CPU fallbacks or Out-of-Memory errors when the graph structure changes.
2. **Training Overhead:** The `coremltools` compilation pass introduces a massive latency penalty per architecture tweak. This breaks the rapid iteration cycle required for the `autoresearch` 24-lane harness.
3. **MLX Maturity:** MLX provides mature, zero-copy memory access to the GPU, natively handling dynamic shapes and complex index gathers (e.g., RoPE caches, dynamic masking) without leaving the fast-path.

## Implications for the Project
- The `autoresearch` repository will decouple its primary iteration loops from `coremltools`.
- ANE compilation is reserved strictly for *inference deployment* of hardened models (e.g., edge deployment or strict low-latency serving paths) once the model architecture is frozen.
- We will no longer block core HRM milestones on ANE kernel parity or throughput measurements.

*Generated: 2026-03-12*
