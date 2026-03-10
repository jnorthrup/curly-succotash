# Spec

## Slice

Identify and prioritize the bounded work needed to bring sibling `../ANE` and sibling `../autoresearch` together on the existing 24-lane HRM harness before expanding beyond 24 agents.

## Repo evidence

- `coordination/config.toml` declares `hrm_swimlanes = 24` and `swimlane_contract.lane_count = 24`.
- `coordination/runtime/hrm_training_harness.json` already emits an `autoresearch_adaptation` contract.
- The same harness artifact includes an `hrm_24x24_w24` stage, but the current pair universe still resolves to 7 pairs rather than a full 24-pair width.
- `TODO.md` contains open ANE backlog items, but local `/conductor/` truth has no active track that joins ANE work to the harness or to `autoresearch`.

## Priority order

1. Treat the generated 24-lane harness as the canonical runtime anchor.
2. Define the ANE artifact contract needed to plug into that harness without inventing a separate training path.
3. Align `autoresearch` so it can iterate against ANE-compatible harness evidence instead of only the smallest convergence stage.
4. Only then describe how the harness grows beyond 24 agents or wider pair coverage.

## ANE Handoff Contract

### Harness Inputs Required by ANE

ANE execution requires the following local harness artifacts as inputs:

| Input | Path | Purpose |
|-------|------|---------|
| HRM Training Harness | `coordination/runtime/hrm_training_harness.json` | Stage definitions, pair-width targets, episode budgets, readiness gates |
| HRM Training Codex | `coordination/runtime/hrm_training_codex.md` | Human-readable training protocol and promotion ladder |
| Swimlane DSEL | `coordination/runtime/hrm_swimlanes.dsel` | 24-lane archetype configuration for Kotlin DSEL consumption |
| Swimlane JSON | `coordination/runtime/hrm_swimlanes.json` | Lane archetype JSON for Python/MLX consumption |
| Pair Universe | `coordination/runtime/binance_connectome_symbols.txt` | Active symbol set for pair-width validation |
| Strategy Risk Profiles | `coordination/runtime/strategy_risk_profiles.json` | Risk-tier mapping per lane archetype |

### Expected ANE Artifact Outputs

ANE must eventually emit evidence for the following categories before it can be treated as harness-compatible:

| Output class | Purpose |
|-------------|---------|
| CPU-vs-ANE parity evidence | Proves ANE execution preserves reference behavior on the synthetic competency tasks already named in local backlog truth |
| Throughput, memory, IO, and power measurements | Shows the ANE path is observable and comparable to the current CPU or non-ANE baseline on the harness workload |
| Checkpoint save/resume evidence | Proves ANE execution can survive restart and compile-budget constraints named in `TODO.md` |
| Harness-to-ANE adaptation surface | Identifies how the emitted HRM harness contract is translated into ANE-executable work without forking a separate training doctrine |
| Readiness verdict artifact | Records whether the ANE path is fit to become an input to `autoresearch` against the 24-lane harness |

Path conventions and exact schemas belong in sibling `../ANE` repo-local truth once that repo has its own conductor surface.

### Readiness Gates

ANE must satisfy the following gates before integration with the 24-lane harness:

**Gate 1: Synthetic parity against the existing competency suite**
- Use the same synthetic-task posture already tracked in local backlog truth: identity, sine, feature-plus, masked reconstruction, and regime or shock validation.
- ANE work must compare against a CPU or current reference path rather than claim standalone quality.

**Gate 2: Harness compatibility**
- ANE execution must consume the emitted harness stages as the source of truth.
- Any ANE adapter must preserve current stage semantics, including the presently capped `hrm_24x24_w24` width.

**Gate 3: Restart and checkpoint viability**
- ANE work must prove save, resume, and restart behavior against the compile-budget concerns already listed in `TODO.md`.

**Gate 4: Measured operational cost**
- ANE work must produce actual throughput, IO, memory, and power observations for the current 24-lane harness path.
- The evidence must be concrete enough to support the later decision of whether ANE is a sidecar, accelerator, or dead end.

### Evidence Required for Scale-Up Claims

Before claiming growth beyond 24 agents or full-width pair coverage, the following evidence must exist:

**For >24 Agents (e.g., 64-lane or 512-lane claims):**
1. `coordination/runtime/hrm_training_harness.json` and `coordination/config.toml` must actually declare the larger lane count.
2. The pair universe and lane contract must expand enough to make the larger claim real instead of synthetic.
3. At least one completed harness artifact must exist at the claimed larger width.
4. ANE-side parity and operational evidence must exist for that same larger-width claim.
5. Local conductor truth must still preserve the shadow-first and readiness-gate posture when widening.

**For Full-Width 24-Pair Coverage (e.g., `hrm_24x24_w24` at true width 24):**
1. `binance_connectome_symbols.txt` must actually support at least 24 pairs.
2. The emitted harness stage must resolve `pair_width_resolved` to 24 rather than the current cap of 7.
3. At least one completed harness or training artifact must exist at true 24-pair width.
4. ANE-side compatibility evidence must exist for that same 24-pair configuration.
5. Strategy and risk-profile artifacts must cover the real widened pair set.

**Ownership Boundary:**
- Local `coordination/` owns harness contract emission and pair-universe expansion
- `../ANE` owns ANE parity reports, throughput profiles, and readiness certificates
- `../autoresearch` owns bounded experiment iteration once ANE handoff is satisfied

## Contract requirements

- Keep ownership explicit: local `coordination/` owns the harness contract, `../ANE` owns ANE execution surfaces, and `../autoresearch` owns bounded experiment iteration.
- Do not claim full-width 24-pair training until the pair universe and emitted artifacts prove it.
- Name the first bounded deliverable as local truth for an ANE-ready harness handoff rather than broad cross-repo coding.
- Preserve the existing shadow-first and readiness-gate posture.

## Verification

- Focused conductor-truth inspection via `rg` and `sed` against the edited local `/conductor/` files.
