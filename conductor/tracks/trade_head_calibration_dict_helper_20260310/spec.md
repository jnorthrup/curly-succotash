# Track Spec: Trade-Head Calibration `is_calibration_loaded` dict support

## Problem

The helper `is_calibration_loaded` in `backend/src/trade_head_calibration.py`
handles object instances with a `loaded` attribute and dictionary payloads by
looking for the `"trade_head_calibration_loaded"` key.  Although unit tests
exercise the class and object cases, there is no coverage for the dict code
path.  This creates a small blind spot in the ring-agent API integration tests
and leaves the behaviour unverified.

## Scope

* add a focused unit test ensuring that `is_calibration_loaded` returns `True`
  when passed a dictionary containing a truthy `"trade_head_calibration_loaded"`
  entry, and `False` otherwise.
* no production code changes are required; the existing implementation already
  handles the case correctly.
* updates to `TODO.md` or broader docs are not needed, but we will record the
  new test case in track documentation.

This is a very small slice but it serves as a valid delegation target because
it has an independent runtime (`pytest` on the single test) and a clear corpus
(the test file).

## Desired Outcome

* new assertion in `backend/src/tests/test_trade_head_calibration.py` verifying
dict handling
* `pytest` run continues to pass with 11 (or now 12) tests
* the track remains open until the delegated worker returns the changes and
verifications

## Acceptance Signals

* worker payload includes `backend/src/tests/test_trade_head_calibration.py` as a
changed file
* verification command `pytest backend/src/tests/test_trade_head_calibration.py -q`
passes
* the master inspects the diff, confirms the extra assertions, and then marks
track complete after worker result
