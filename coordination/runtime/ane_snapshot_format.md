# ANE Hardware Milestone Snapshots

## Context
When `autoresearch` hits a milestone gate (e.g., `M1: Synthetic Competency`), it must dump a hardware performance snapshot. This proves that the model not only learned the task but can run efficiently within production boundaries on Apple Silicon.

## Expected JSON Payload
Any hardware trial submitted to `curly-succotash` for evaluation must include a `hardware_snapshot` block conforming to the following structure:

```json
{
  "schema": "moneyfan.hardware.snapshot.v1",
  "device": "Apple M2 Max",
  "framework": "mlx-0.19",
  "metrics": {
    "loss": {
      "final_training_loss": 0.042,
      "final_validation_loss": 0.048,
      "convergence_steps": 14500
    },
    "throughput": {
      "inferences_per_second": 4200.5,
      "tokens_per_second": 512000,
      "batch_size": 128
    },
    "memory": {
      "peak_unified_memory_mb": 4250,
      "ane_sram_spills": 0
    },
    "power": {
      "average_package_power_w": 18.5,
      "peak_package_power_w": 32.1,
      "ane_power_w": 4.2,
      "gpu_power_w": 11.5
    }
  }
}
```

## Measurement Protocol
1. **Throughput:** Must be measured over a sustained window of at least 60 seconds to avoid burst/cache anomalies.
2. **Power:** Should be captured via `sudo powermetrics --samplers cpu_power,gpu_power,ane_power` during the throughput measurement window.
3. **Memory:** Measured via `ps` or the MLX memory profiler at the peak of the forward/backward pass.

*Generated: 2026-03-12*
