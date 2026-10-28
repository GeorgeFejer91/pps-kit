"""The all-preset audit must not accept a shortened or same-count wrong plan."""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "validation/scripts/audit_preset_population.py"
spec = importlib.util.spec_from_file_location("preset_population_audit", SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def capture():
    rows = [{"trial_pool_index": n, "family": "audio_tactile", "soa_ms": 300,
             "duration_ms": 5000, "tactile_onset_s": 1.3} for n in [1, 2]]
    return {"design": {"study_profile_id": "fixture", "protocol": {"participants": 10}},
            "trial_pool_bake": {"total_count": 2, "preview_rows": rows},
            "block_csv_preview": {"blocks": [{"block_index": 1, "block_label": "Block 1", "trial_count": 2,
                "preview_rows": [{**row, "block_index": 1, "block_trial_index": n} for n, row in enumerate(rows, 1)]}]},
            "custom_workflow": {"ready_to_prepare": True}, "run_sequence_setup": {"experiment_structure": "single"}}


def test_full_plan_preserves_pool_identities_and_timing():
    fixture = capture()
    result = audit.checked_plan("fixture", True, fixture)
    assert result["source_trial_count"] == 2
    assert result["usable_runner_file_verified"] is False
    fixture["block_csv_preview"]["blocks"][0]["preview_rows"][1]["trial_pool_index"] = 1
    with pytest.raises(ValueError, match="preserve every pool row"):
        audit.checked_plan("fixture", True, fixture)


@pytest.mark.parametrize("change", ["truncated", "wrong_timing", "wrong_order"])
def test_rejects_cutdown_or_changed_plan(change):
    fixture = capture()
    block = fixture["block_csv_preview"]["blocks"][0]
    if change == "truncated":
        block["preview_rows"].pop()
    elif change == "wrong_timing":
        block["preview_rows"][0]["tactile_onset_s"] = 0.3
    else:
        block["preview_rows"][0]["block_trial_index"] = 2
    with pytest.raises(ValueError):
        audit.checked_plan("fixture", True, fixture)


def test_gate_success_is_not_a_usable_file_and_identity_mismatch_fails():
    fixture = capture()
    fixture["block_csv_preview"] = {}
    fixture["custom_workflow"]["ready_to_prepare"] = False
    assert audit.checked_plan("fixture", False, fixture)["status"] == "blocked_as_shipped"
    with pytest.raises(ValueError, match="Wrong captured template"):
        audit.checked_plan("different", False, fixture)
    with pytest.raises(ValueError, match="Duplicate"):
        audit.unique_by([{"id": "same"}, {"id": "same"}], "id")


def test_declared_choice_contract_must_survive_even_when_counts_match():
    fixture = capture()
    fixture["design"]["protocol"]["trial_strips"] = [{"label": "Left", "metadata": {
        "correct_response": "left", "response_choice_set": "left,right", "expected_response": "respond"}}]
    for row in fixture["block_csv_preview"]["blocks"][0]["preview_rows"]:
        row.update(row_label="Left", correct_response="left", response_choice_set="left,right", expected_response="respond")
    allowed = {"correct_response", "response_choice_set", "expected_response"}
    assert audit.saved_metadata_findings(fixture, allowed) == []
    fixture["block_csv_preview"]["blocks"][0]["preview_rows"][0].pop("correct_response")
    assert audit.saved_metadata_findings(fixture, allowed) == [{
        "row_label": "Left", "family": "audio_tactile", "field": "correct_response", "affected_rows": 1}]
