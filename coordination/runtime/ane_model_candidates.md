# ANE Model Candidate Definitions

## Context
The Apple Neural Engine (ANE) provides extreme throughput/watt for static, highly predictable tensor graphs, but severely penalizes dynamic control flow, complex gather/scatter operations, and exotic activation functions. For the HRM training loop, we must constrain our model architectures to what is empirically viable on the ANE.

## Architectural Constraints (ANE Budget)
1. **Static Shapes:** All input, intermediate, and output shapes must be statically known at compile time. Variable sequence lengths require bucketed padding or truncation.
2. **Supported Operations:**
   - **Good:** `MatMul`, `Conv1D/2D`, `LayerNorm`, `ReLU`, `GELU`, `Tanh`, `Sigmoid`, element-wise arithmetic.
   - **Bad (CPU/GPU Fallback):** Complex index gathers/scatters, dynamic masking, exotic custom activations (e.g., Swish without a fast-path, custom learned activations).
3. **Memory Footprint:** Models must comfortably fit within the Unified Memory constraints without triggering swap, but more importantly, intermediate activation memory must fit within the ANE's SRAM to avoid severe bandwidth penalties.

## Viable Candidates for HRM
1. **Standard Multi-Layer Perceptrons (MLPs)**
   - *Use Case:* Processing flattened state representations or fixed-window feature vectors.
   - *Why it works:* Straightforward `MatMul` -> `BiasAdd` -> `ReLU/GELU` sequences map perfectly to the ANE tensor units.
2. **Causal Transformer Blocks (Static Masking)**
   - *Use Case:* Time-series feature extraction and attention over fixed-length lookback windows.
   - *Why it works:* If the causal mask is a static, non-learnable tensor constant, the ANE can execute the standard `QKV` projections and softmax efficiently. Dynamic or sparse attention mechanisms are non-viable.
3. **1D Convolutional Networks (TCNs)**
   - *Use Case:* Local pattern recognition across time (e.g., detecting momentum or volatility clusters).
   - *Why it works:* Native, highly optimized support for standard convolutions with fixed kernel sizes and dilations.

## Non-Viable Architectures
- **Recurrent Neural Networks (RNNs / LSTMs):** The sequential dependency forces layer-by-layer execution, defeating the ANE's massively parallel execution units. Unrolling them for static lengths is possible but often less efficient than a TCN or Transformer.
- **State Space Models (e.g., Mamba) with Dynamic Scans:** While theoretically unrollable, the cumulative sum / selective scan operations often hit unsupported op paths and fallback to GPU/CPU, ruining the throughput proposition.
- **Dynamic Graph Networks:** Any architecture that changes its connectivity based on the input data will fail the ahead-of-time compilation requirement of CoreML/ANE.

*Generated: 2026-03-12*
