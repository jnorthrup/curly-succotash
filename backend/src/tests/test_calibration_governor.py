from datetime import datetime, timedelta, timezone

from src.calibration_governor import (
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
