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


def test_build_autoresearch_adaptation_contract_points_at_harness_inputs():
    contract = coordinate.build_autoresearch_adaptation_contract(
        autoresearch_repo=Path("/tmp/autoresearch"),
        harness_json_path=Path("/tmp/hrm_training_harness.json"),
        harness_codex_path=Path("/tmp/hrm_training_codex.md"),
        swimlane_dsel_path=Path("/tmp/hrm_swimlanes.dsel"),
    )

    assert contract["status"] == "ready_when_harness_exists"
    assert contract["program_path"].endswith("/tmp/autoresearch/program.md")
    assert contract["train_entrypoint"].endswith("/tmp/autoresearch/train.py")
    assert contract["harness_inputs"]["hrm_training_harness_json"].endswith(
        "/tmp/hrm_training_harness.json"
    )
    assert contract["bounded_mutation_policy"]["fixed_surface"] == ["prepare.py"]
    assert contract["first_handoff"]["first_gate_set"] == ["M0_identity", "M1_sine"]


def test_build_autoresearch_adaptation_contract_run_setup_branch_naming():
    contract = coordinate.build_autoresearch_adaptation_contract(
        autoresearch_repo=Path("/tmp/autoresearch"),
        harness_json_path=Path("/tmp/runtime/hrm_training_harness.json"),
        harness_codex_path=Path("/tmp/runtime/hrm_training_codex.md"),
        swimlane_dsel_path=Path("/tmp/runtime/hrm_swimlanes.dsel"),
    )

    run_setup = contract["run_setup"]
    branch_policy = run_setup["branch_naming_policy"]

    assert branch_policy["pattern"] == "exp/{stage}/{theme}/{YYYYMMDD}"
    assert branch_policy["example"] == "exp/convergence_4x4/sine_wider/20260308"
    assert "branch name encodes" in branch_policy["rule"]


def test_build_autoresearch_adaptation_contract_run_setup_results_log():
    contract = coordinate.build_autoresearch_adaptation_contract(
        autoresearch_repo=Path("/tmp/autoresearch"),
        harness_json_path=Path("/tmp/runtime/hrm_training_harness.json"),
        harness_codex_path=Path("/tmp/runtime/hrm_training_codex.md"),
        swimlane_dsel_path=Path("/tmp/runtime/hrm_swimlanes.dsel"),
    )

    run_setup = contract["run_setup"]
    assert run_setup["results_log_path"].endswith("/tmp/runtime/autoresearch_results.jsonl")

    schema = run_setup["results_log_schema"]
    assert schema["format"] == "jsonl"
    assert "experiment_id" in schema["fields"]
    assert "branch" in schema["fields"]
    assert "stage" in schema["fields"]
    assert "theme" in schema["fields"]
    assert "timestamp" in schema["fields"]
    assert "metrics" in schema["fields"]
    assert "verdict" in schema["fields"]
    assert "evidence_path" in schema["fields"]


def test_build_autoresearch_adaptation_contract_run_setup_baseline_recording():
    contract = coordinate.build_autoresearch_adaptation_contract(
        autoresearch_repo=Path("/tmp/autoresearch"),
        harness_json_path=Path("/tmp/runtime/hrm_training_harness.json"),
        harness_codex_path=Path("/tmp/runtime/hrm_training_codex.md"),
        swimlane_dsel_path=Path("/tmp/runtime/hrm_swimlanes.dsel"),
    )

    run_setup = contract["run_setup"]
    baseline_policy = run_setup["baseline_recording_policy"]

    assert baseline_policy["record_baseline_on"] == "each successful stage completion in HRM harness"
    assert "validation_loss_curve.json" in baseline_policy["baseline_artifacts"]
    assert "synthetic_milestone_evidence.json" in baseline_policy["baseline_artifacts"]
    assert "stage_completion_certificate.json" in baseline_policy["baseline_artifacts"]
    assert "beat or match baseline" in baseline_policy["baseline_comparison_rule"]


def test_build_autoresearch_adaptation_contract_run_setup_commit_rollback():
    contract = coordinate.build_autoresearch_adaptation_contract(
        autoresearch_repo=Path("/tmp/autoresearch"),
        harness_json_path=Path("/tmp/runtime/hrm_training_harness.json"),
        harness_codex_path=Path("/tmp/runtime/hrm_training_codex.md"),
        swimlane_dsel_path=Path("/tmp/runtime/hrm_swimlanes.dsel"),
    )

    run_setup = contract["run_setup"]
    loop_policy = run_setup["loop_commit_rollback_policy"]

    assert "promote" in loop_policy["commit_condition"]
    assert "baseline comparison passes" in loop_policy["commit_condition"]
    assert "readiness gates" in loop_policy["commit_condition"]

    assert "rollback" in loop_policy["rollback_condition"]
    assert "validation loss degrades" in loop_policy["rollback_condition"]
    assert "readiness gate violation" in loop_policy["rollback_condition"]

    assert "merge branch to main" in loop_policy["commit_action"]
    assert "abandon branch" in loop_policy["rollback_action"]
    assert "preserve for postmortem" in loop_policy["rollback_action"]
    assert "manual review" in loop_policy["inconclusive_action"]


def test_build_kotlin_autoresearch_adaptation_contract_points_at_trikeshed_and_kilo():
    contract = coordinate.build_kotlin_autoresearch_adaptation_contract(
        trikeshed_repo=Path("/tmp/TrikeShed"),
        harness_json_path=Path("/tmp/runtime/hrm_training_harness.json"),
        harness_codex_path=Path("/tmp/runtime/hrm_training_codex.md"),
        swimlane_dsel_path=Path("/tmp/runtime/hrm_swimlanes.dsel"),
    )

    assert contract["runtime_route"] == "kilo"
    assert contract["repo_path"] == "/tmp/TrikeShed"
    assert contract["mutable_training_surface"].endswith(
        "/tmp/TrikeShed/src/posixMain/kotlin/borg/trikeshed/autoresearch/MutableAutoresearchExperiment.kt"
    )
    assert contract["first_handoff"]["source_stage"] == "convergence_4x4"
    assert contract["first_handoff"]["first_gate_set"] == ["M0_identity", "M1_sine"]


def test_build_kotlin_autoresearch_adaptation_contract_uses_dedicated_results_log():
    contract = coordinate.build_kotlin_autoresearch_adaptation_contract(
        trikeshed_repo=Path("/tmp/TrikeShed"),
        harness_json_path=Path("/tmp/runtime/hrm_training_harness.json"),
        harness_codex_path=Path("/tmp/runtime/hrm_training_codex.md"),
        swimlane_dsel_path=Path("/tmp/runtime/hrm_swimlanes.dsel"),
    )

    run_setup = contract["run_setup"]
    assert run_setup["results_log_path"].endswith("/tmp/runtime/kotlin_autoresearch_results.jsonl")
    assert run_setup["branch_naming_policy"]["example"] == "exp/convergence_4x4/native_identity/20260310"
