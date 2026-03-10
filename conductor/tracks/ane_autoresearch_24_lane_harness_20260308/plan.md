# Plan

## Phase 1: Open canonical local truth

- [x] Record a local conductor track for joining `../ANE`, `../autoresearch`, and the emitted 24-lane harness.
- [x] Write the priority order so the current 24-agent harness is the runtime anchor and growth beyond 24 stays secondary.

## Phase 2: Define the next bounded slice

- [x] Publish a local ANE handoff contract that names required harness inputs, expected artifact outputs, and readiness gates.
- [ ] Reconcile the existing `autoresearch` adaptation contract so it can target the 24-lane harness path after the ANE handoff exists.
- [x] Record the exact evidence needed before claiming scale-up beyond 24 agents or full-width pair coverage.

## Acceptance

- `conductor/tracks.md` lists an active track covering ANE + `autoresearch` on the 24-lane harness.
- The track spec names the repo evidence, priority order, ownership boundaries, and the first bounded deliverable.
- The plan leaves ANE handoff publication as the next executable slice instead of pretending the cross-repo integration already exists.

## Verification

- `rg -n "ANE \\+ autoresearch on the 24-lane harness|24-lane harness|Priority order" conductor/tracks.md conductor/tracks/ane_autoresearch_24_lane_harness_20260308/spec.md conductor/tracks/ane_autoresearch_24_lane_harness_20260308/plan.md`
- `sed -n '1,220p' conductor/tracks/ane_autoresearch_24_lane_harness_20260308/spec.md`
- `sed -n '1,220p' conductor/tracks/ane_autoresearch_24_lane_harness_20260308/plan.md`

## Blocker

- None for opening local truth. Cross-repo ANE execution remains a later slice because sibling `../ANE` still lacks repo-local conductor truth.
