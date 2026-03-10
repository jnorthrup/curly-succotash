# Track: ANE Porting Scaffolding

## Objective
Satisfy the remaining ANE porting tasks ("Port the synthetic gate suite to ANE-executable training or inference checks" and "Measure ANE throughput, IO cost, and classifier overhead on candidate tasks") by scaffolding out the required scripts to serve as interfaces when `autoresearch` implements the actual CoreML graph logic.

## Scope
- `backend/scripts/ane_synthetic_gates.py`: Create a wrapper script that loads a CoreML `.mlpackage`, translates the `SyntheticGate` generated data into the required static shapes, invokes the model, and computes the MSE parity against a CPU reference.
- `backend/scripts/measure_ane_throughput.py`: Create a benchmarking stub that loops inferences over a CoreML package, calculates throughput, estimates IO latency overhead, and outputs the `moneyfan.hardware.snapshot.v1` schema.

## Stop Condition
The python scripts exist and successfully parse dummy inputs, emitting clear instructional errors that they require compiled `coremltools` packages.
