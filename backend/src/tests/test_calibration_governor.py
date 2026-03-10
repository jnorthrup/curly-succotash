from datetime import datetime, timedelta, timezone
import os
import time
from unittest import mock

from backend.src.calibration_governor import (
    CalibrationGovernor,
    CalibrationOutcome,
    CalibrationTrigger,
    GovernorConfig,
)


def test_initial_calibration_does_not_repeat_until_recorded():
    governor = CalibrationGovernor(GovernorConfig())
    now = datetime(2026, 3, 6, tzinfo=timezone.utc)

    first = governor.should_recalibrate(current_time=now)
    second = governor.should_recalibrate(current_time=now + timedelta(minutes=5))

    assert first.decision == CalibrationOutcome.CALIBRATE
    assert first.trigger == CalibrationTrigger.INITIAL
    assert second.decision == CalibrationOutcome.SKIP
    assert second.trigger == CalibrationTrigger.INITIAL
    assert "already triggered" in second.reason


def test_record_calibration_resets_initial_trigger_state():
    config = GovernorConfig(
        min_hours_between_calibration=24,
        max_hours_between_calibration=168,
        cooldown_after_calibration_hours=2,
        check_cadence_cycles=1,
    )
    governor = CalibrationGovernor(config)
    now = datetime(2026, 3, 6, tzinfo=timezone.utc)

    first = governor.should_recalibrate(current_time=now)
    governor.record_calibration(now)
    second = governor.should_recalibrate(current_time=now + timedelta(minutes=5))

    assert first.decision == CalibrationOutcome.CALIBRATE
    assert second.decision == CalibrationOutcome.SKIP
    assert "cooldown" in second.reason.lower()


def test_should_recalibrate_uses_stored_calibration_time():
    config = GovernorConfig(
        min_hours_between_calibration=24,
        max_hours_between_calibration=168,
        cooldown_after_calibration_hours=2,
        check_cadence_cycles=1,
    )
    governor = CalibrationGovernor(config)
    last_calibration = datetime(2026, 3, 6, tzinfo=timezone.utc)
    governor.record_calibration(last_calibration)

    decision = governor.should_recalibrate(
        current_time=last_calibration + timedelta(minutes=30),
    )

    assert governor._last_calibration_time == last_calibration
    assert decision.decision == CalibrationOutcome.SKIP
    assert "cooldown" in decision.reason.lower()


def test_drift_trigger_calibrates():
    config = GovernorConfig(drift_threshold=0.10, min_hours_between_calibration=1, max_hours_between_calibration=10, check_cadence_cycles=1)
    governor = CalibrationGovernor(config)
    last = datetime(2026, 3, 6, tzinfo=timezone.utc)
    governor.record_calibration(last)

    # drift just below threshold should skip
    decision1 = governor.should_recalibrate(
        current_time=last + timedelta(hours=2),
        drift_detected=False,
    )
    assert decision1.decision == CalibrationOutcome.SKIP

    # drift above threshold triggers calibration
    decision2 = governor.should_recalibrate(
        current_time=last + timedelta(hours=3),
        drift_detected=True,
    )
    assert decision2.decision == CalibrationOutcome.CALIBRATE
    assert decision2.trigger == CalibrationTrigger.DRIFT_DETECTED


def test_performance_drop_trigger_calibrates():
    config = GovernorConfig(performance_drop_threshold=0.20, min_hours_between_calibration=1, max_hours_between_calibration=10, check_cadence_cycles=1)
    governor = CalibrationGovernor(config)
    last = datetime(2026, 3, 6, tzinfo=timezone.utc)
    governor.record_calibration(last)

    # good performance -> skip
    decision1 = governor.should_recalibrate(
        current_time=last + timedelta(hours=2),
        performance_drop=False,
    )
    assert decision1.decision == CalibrationOutcome.SKIP

    # performance drop triggers calibration
    decision2 = governor.should_recalibrate(
        current_time=last + timedelta(hours=3),
        performance_drop=True,
    )
    assert decision2.decision == CalibrationOutcome.CALIBRATE
    assert decision2.trigger == CalibrationTrigger.PERFORMANCE_DROP


def test_scheduled_max_interval_triggers():
    config = GovernorConfig(min_hours_between_calibration=1, max_hours_between_calibration=4, check_cadence_cycles=1)
    governor = CalibrationGovernor(config)
    last = datetime(2026, 3, 6, tzinfo=timezone.utc)
    governor.record_calibration(last)

    # before max interval -> skip
    decision1 = governor.should_recalibrate(current_time=last + timedelta(hours=3))
    assert decision1.decision == CalibrationOutcome.SKIP

    # after max interval -> calibrate
    decision2 = governor.should_recalibrate(current_time=last + timedelta(hours=5))
    assert decision2.decision == CalibrationOutcome.CALIBRATE
    assert decision2.trigger == CalibrationTrigger.SCHEDULED


def test_regime_change_triggers_and_defers():
    # use min_hours_between_calibration=1 to satisfy validation
    config = GovernorConfig(trigger_on_regime_change=True, min_samples_in_regime=2, min_hours_between_calibration=1, check_cadence_cycles=1)
    governor = CalibrationGovernor(config)
    last = datetime(2026, 3, 6, tzinfo=timezone.utc)
    governor.record_calibration(last)

    # advance time past cooldown so triggers will be evaluated
    d1 = governor.should_calibrate(
        last_calibration_time=last,
        current_drift=0.0,
        recent_performance=1.0,
        regime_changed=True,
        current_regime="R1",
        samples_in_regime=1,
        current_time=last + timedelta(hours=3),
    )
    assert d1.decision == CalibrationOutcome.DEFER
    assert d1.trigger == CalibrationTrigger.REGIME_CHANGE

    # another regime change with enough samples should CALIBRATE
    d2 = governor.should_calibrate(
        last_calibration_time=last,
        current_drift=0.0,
        recent_performance=1.0,
        regime_changed=True,
        current_regime="R1",
        samples_in_regime=2,
        current_time=last + timedelta(hours=4),
    )
    assert d2.decision == CalibrationOutcome.CALIBRATE
    assert d2.trigger == CalibrationTrigger.REGIME_CHANGE




def test_artifact_fresh_returns_true_for_recent_file():
    governor = CalibrationGovernor()
    
    # Create a temporary file
    with open("temp_artifact.txt", "w") as f:
        f.write("test")
        
    # Should return True for recent file with large max_age
    assert governor.is_artifact_fresh("temp_artifact.txt", max_age_hours=1000.0)
    
    # Clean up
    os.remove("temp_artifact.txt")


def test_artifact_stale_returns_false_for_old_mtime():
    governor = CalibrationGovernor()
    
    # Create a temporary file
    with open("temp_artifact.txt", "w") as f:
        f.write("test")
        
    # Test that old mtime returns False
    with mock.patch("os.path.getmtime", return_value=time.time() - 200 * 3600):
        assert not governor.is_artifact_fresh("temp_artifact.txt", max_age_hours=168.0)
        
    # Test that missing file returns False
    os.remove("temp_artifact.txt")
    assert not governor.is_artifact_fresh("temp_artifact.txt", max_age_hours=168.0)


def test_check_cadence_cycles():
    config = GovernorConfig(
        min_hours_between_calibration=1,
        max_hours_between_calibration=168,
        check_cadence_cycles=3,
    )
    governor = CalibrationGovernor(config)
    last = datetime(2026, 3, 6, tzinfo=timezone.utc)
    governor.record_calibration(last)
    current_time = last + timedelta(hours=2)
