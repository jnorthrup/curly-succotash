import json
import numpy as np
import pytest

from backend.src.synthetic_gates import (
    GateResult,
    IdentityGate,
    CompetencyEvaluator,
    run_competency_check,
)


def test_gate_result_to_dict_and_types():
    result = GateResult(
        gate_name="foo",
        success=False,
        mse=0.123,
        mae=0.456,
        correlation=0.789,
        samples=42,
    )
    d = result.to_dict()
    assert d["gate_name"] == "foo"
    assert isinstance(d["mse"], float)
    assert isinstance(d["mae"], float)
    assert isinstance(d["correlation"], float)
    assert d["samples"] == 42
    assert d["metadata"] == {}


def test_correlation_zero_when_prediction_constant():
    gate = IdentityGate(threshold=1e-3)

    # predictor always returns constant value -> std(y_pred) == 0 -> correlation should be 0
    def const_pred(x):
        return np.zeros_like(x)

    res = gate.evaluate(const_pred, samples=50)
    assert res.correlation == 0.0


def test_generate_report_failure_outcomes_and_save(tmp_path):
    evaluator = CompetencyEvaluator()

    # predictor that returns zeros for every input guarantees every gate will fail
    def zero_pred(x):
        return np.zeros((x.shape[0], 1))

    results = evaluator.run_all(zero_pred)
    assert len(results) == 10

    report = evaluator.generate_report()
    assert report["all_passed"] is False
    # expect at least one of each failure category based on gate names
    outcomes = report.get("failure_outcomes", [])
    for expected in ("FAIL_ARCH", "FAIL_SCALE", "FAIL_TRANSFER"):
        assert any(expected in outcome for outcome in outcomes)

    # save the report and validate contents on disk
    path = tmp_path / "report.json"
    evaluator.save_report(str(path))
    assert path.exists()
    loaded = json.loads(path.read_text())
    assert loaded["total_count"] == len(results)


def test_run_competency_check_returns_bool_and_writes(tmp_path):
    # using a clearly failing predictor ensures the return value is False
    def bad_pred(x):
        return np.zeros((x.shape[0], 1))

    result = run_competency_check(bad_pred, output_path=str(tmp_path / "out.json"))
    assert result is False
    assert (tmp_path / "out.json").exists()

    # return type should always be a boolean even if no output_path provided
    result2 = run_competency_check(bad_pred)
    assert isinstance(result2, bool)
