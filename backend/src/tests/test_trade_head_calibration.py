import pytest

from backend.src import trade_head_calibration


def test_calibrator_instantiates_and_returns_zero_cost():
    calib = trade_head_calibration.TradeHeadCalibrator()
    assert not calib.loaded
    cost = calib.compute_cost({})
    assert cost == 0.0
    # calling compute should mark the calibrator as loaded
    assert calib.loaded


def test_is_calibration_loaded_helper():
    class Dummy:
        loaded = True

    assert trade_head_calibration.is_calibration_loaded(Dummy())
    assert not trade_head_calibration.is_calibration_loaded(object())

    # dictionary payloads should be recognised as well
    assert trade_head_calibration.is_calibration_loaded({"trade_head_calibration_loaded": True})
    assert not trade_head_calibration.is_calibration_loaded({"trade_head_calibration_loaded": False})


def test_compute_cost_numeric_values():
    calib = trade_head_calibration.TradeHeadCalibrator()
    # mix of numeric and non-numeric; only numbers contribute when actual is None
    cost = calib.compute_cost({"a": -3, "b": 4.5, "c": "ignore me"})
    assert cost == pytest.approx(7.5)
    assert calib.loaded


def test_compute_cost_with_actuals():
    calib = trade_head_calibration.TradeHeadCalibrator(fee_rate=0.001)

    # 1. Correct long prediction (+2% move)
    # PnL = (1 * 0.02) - 0.002 = 0.018
    # Cost = -PnL = -0.018
    cost_win_long = calib.compute_cost({"direction": 1}, {"return": 0.02})
    assert cost_win_long == pytest.approx(-0.018)

    # 2. Incorrect long prediction (-2% move)
    # PnL = (1 * -0.02) - 0.002 = -0.022
    # Cost = -PnL = 0.022
    cost_lose_long = calib.compute_cost({"direction": 1}, {"return": -0.02})
    assert cost_lose_long == pytest.approx(0.022)

    # 3. Correct short prediction (-2% move)
    # PnL = (-1 * -0.02) - 0.002 = 0.018
    # Cost = -PnL = -0.018
    cost_win_short = calib.compute_cost({"direction": -1}, {"return": -0.02})
    assert cost_win_short == pytest.approx(-0.018)

    # 4. Incorrect short prediction (+2% move)
    # PnL = (-1 * 0.02) - 0.002 = -0.022
    # Cost = -PnL = 0.022
    cost_lose_short = calib.compute_cost({"direction": -1}, {"return": 0.02})
    assert cost_lose_short == pytest.approx(0.022)

    # 5. Neutral prediction during a big move (missed opportunity penalty)
    # Big move: 0.05. fee_rate*2 is 0.002. Penalty = 0.05 - 0.002 = 0.048
    cost_missed = calib.compute_cost({"direction": 0}, {"return": 0.05})
    assert cost_missed == pytest.approx(0.048)

    # 6. Neutral prediction during a small move (no penalty)
    # Small move: 0.001. Threshold is 0.002. Penalty = 0.0
    cost_smart_neutral = calib.compute_cost({"direction": 0}, {"return": 0.001})
    assert cost_smart_neutral == 0.0

    # 7. Invalid direction penalty
    cost_invalid = calib.compute_cost({"direction": 99}, {"return": 0.0})
    assert cost_invalid == 100.0
