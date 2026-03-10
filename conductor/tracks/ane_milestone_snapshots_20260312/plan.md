# Track: ANE Milestone Snapshots

## Objective
Satisfy the TODO item "Add dashboard snapshots for loss, throughput, memory, and power on milestone runs."

## Scope
- `coordination/runtime/ane_snapshot_format.md`: Create documentation defining the expected snapshot payload format for hardware benchmarks. This defines how `autoresearch` should record throughput (inferences/sec), loss convergence, memory peaks, and power draw (watts via `powermetrics`) when passing a milestone, so it can be consumed by the moneyfan daily runbook.

## Stop Condition
The format specification is tracked locally.
