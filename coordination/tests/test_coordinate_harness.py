import importlib.util
import sys
from pathlib import Path


COORDINATE_PATH = Path(__file__).resolve().parents[1] / "coordinate.py"
SPEC = importlib.util.spec_from_file_location("coordinate_under_test", COORDINATE_PATH)
coordinate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = coordinate
SPEC.loader.exec_module(coordinate)


def test_build_stage_display_name_is_honest_when_capped():
    label = coordinate.build_stage_display_name(
        name="hrm_24x24",
        pair_width_target=24,
        resolved_pair_width=7,
        effective_width=24,
    )

    assert "capped at 7/24 pairs" in label


def test_build_stage_notes_warn_about_capped_pair_width():
    notes = coordinate.build_stage_notes(pair_width_target=24, resolved_pair_width=7)

    assert notes == [
        "pair width capped by current pair universe size; do not interpret this as a full-width stage"
    ]


def test_build_operating_posture_keeps_baseline_active_and_hrm_shadowed():
    posture = coordinate.build_operating_posture()

    assert posture["baseline_trading"]["status"] == "active_now"
    assert posture["hrm_role"]["current"] == "shadow"
    assert posture["hrm_role"]["promotion_ramp"][0] == "shadow"
    assert posture["hrm_role"]["promotion_ramp"][-1] == "primary"


def test_build_hrm_readiness_contract_has_failure_states_and_milestones():
    contract = coordinate.build_hrm_readiness_contract()

    failure_names = [row["name"] for row in contract["failure_states"]]
    milestone_names = [row["name"] for row in contract["synthetic_milestones"]]

    assert failure_names == ["FAIL_ARCH", "FAIL_SCALE", "FAIL_TRANSFER", "FAIL_TRADING"]
    assert "M0_identity" in milestone_names
    assert "M3_feature_plus_n" in milestone_names
