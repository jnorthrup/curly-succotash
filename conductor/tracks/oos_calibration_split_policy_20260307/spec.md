# Track Spec: OOS Calibration Split Policy

## Problem

`TODO.md` still lists "Strengthen OOS calibration split policy to explicit regime and time windows" as incomplete, while this repo already contains `backend/src/oos_calibration.py` and a dedicated test module. The brownfield gap is not the absence of a module; it is the lack of repo-local Conductor truth that defines what "done" means for this slice.

## Scope

This track covers:

- the OOS calibration split policy implementation in `backend/src/oos_calibration.py`
- the corresponding tests in `backend/src/tests/test_oos_calibration.py`
- any repo-local configuration or runtime artifact wiring needed to make regime/time-window governance explicit

This track does not cover:

- broader training-objective redesign
- scheduler/automation work
- unrelated frontend changes

## Desired Outcome

- split policy inputs explicitly describe temporal bounds and regime requirements
- runtime/test behavior proves no-overlap and no-future-leakage constraints
- any new policy artifacts are serialized in a way the governance path can consume later

## Acceptance Signals

- focused OOS calibration tests pass
- the implementation exposes explicit regime/time-window configuration rather than only loose ratios
- conductor truth for this track is present locally in this repo
