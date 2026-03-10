# ANE Kernel Support Analysis: HRM vs Stories110M

## Baseline: `Stories110M`
The `Stories110M` model is a standard autoregressive transformer. It compiles efficiently to the Apple Neural Engine (ANE) via `coremltools` because its operations map directly to highly optimized hardware kernels:
- **`MatMul`**: Dense fully-connected layers.
- **`LayerNorm`**: Standard normalization along the embedding dimension.
- **`GELU/ReLU`**: Natively supported activations.
- **`Softmax`**: Supported over fixed dimensions.
- **`Static Causal Masking`**: The attention mask is a constant upper-triangular matrix, allowing the compiler to fuse it with the pre-softmax logits.

## The HRM Workload Disconnect
The Hierarchical Risk Model (HRM) requires operations that break the standard static transformer mold, causing the ANE compiler to either fail or silently insert `CPU Fallback` nodes.

### Missing or Fallback-Prone Kernels

1. **Dynamic Causal Masking (Time-Series Holes)**
   - *Requirement:* HRM data streams often contain missing candles or irregular timestamps (handled by `GapInjectionAgent`). The attention mask must be built dynamically per-batch based on valid timestamps.
   - *ANE Status:* **Fallback**. ANE requires the mask tensor to be known at compile time. Dynamic mask generation requires boolean indexing or `scatter_nd`, which forces a CPU transition right before the attention `Softmax`, ruining throughput.

2. **Rotary Positional Embeddings (RoPE) with Variable Offsets**
   - *Requirement:* When evaluating specific trade horizons, positional embeddings must jump gaps or align with specific future prediction horizons.
   - *ANE Status:* **Fallback**. While standard static RoPE can be compiled as a constant weight multiplication, dynamic offset computation requires `gather` operations along sequence dimensions that ANE does not natively support.

3. **Custom Cost-Aware Loss Objectives**
   - *Requirement:* The trade-head calibration relies on a PnL/Fee-aware objective: `(direction * actual_return) - (2 * fee_rate)`.
   - *ANE Status:* **Unsupported for Training**. The ANE is primarily an *inference* engine. While CoreML has limited on-device training support for simple MSE/CrossEntropy, complex branching loss functions (e.g., missed opportunity penalties for neutral predictions) cannot be compiled into the backward pass.

4. **Multi-Horizon Slicing**
   - *Requirement:* The `MultiHorizonGate` forces the model to predict `feature+{1..n}`. This requires slicing the final hidden state and routing it to $N$ different linear heads.
   - *ANE Status:* **Inefficient**. `Split` and `Slice` operations are supported, but if the indices are dynamic, the ANE falls back. Even with static indices, memory layout constraints often prevent the ANE from keeping the sliced tensors in SRAM, causing a round-trip to unified memory.

## Conclusion
While the *backbone* of the HRM (the transformer or MLP feature extractor) maps to ANE kernels perfectly (like `Stories110M`), the *head* routing, *loss* calculation, and *dynamic sequence handling* do not. This reinforces the ADR decision to use MLX/GPU for training and reserve ANE strictly for frozen, static-length inference deployments.

*Generated: 2026-03-12*
