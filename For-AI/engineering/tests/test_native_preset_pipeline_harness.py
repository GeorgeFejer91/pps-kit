"""Native audit joins fail when a complete saved plan loses evidence."""
import copy
import importlib.util
from pathlib import Path
import wave

import pytest


ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "native_preset_pipeline", ROOT / "For-AI/engineering/validation/scripts/run_native_preset_pipeline.py"
)
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)


def joined_receipts():
    prepared = {"handoff_sha256": "a" * 64, "parts": [
        {"manifest_sha256": "b" * 64, "trial_count": 4, "block_count": 2,
         "blocks": [{"trial_count": 2}, {"trial_count": 2}]}]}
    executed = {"passed": True, "input_manifest_sha256": "a" * 64, "parts": [
        {"package_manifest_sha256": "b" * 64, "trial_count": 4, "block_count": 2,
         "per_block_trial_counts": [2, 2], "all_block_schedules_compiled": True,
         "all_saved_occurrences_preserved": True, "all_callback_boundaries_matched": True,
         "all_trial_response_identities_outcomes_and_rts_matched": True}]}
    return prepared, executed


@pytest.mark.parametrize("fault", ["omitted_part", "wrong_package", "short_block", "unscored_responses"])
def test_native_pipeline_rejects_incomplete_or_unjoined_execution(fault):
    prepared, executed = joined_receipts()
    pipeline.validate_execution(prepared, executed)
    broken = copy.deepcopy(executed)
    if fault == "omitted_part":
        broken["parts"] = []
    elif fault == "wrong_package":
        broken["parts"][0]["package_manifest_sha256"] = "c" * 64
    elif fault == "short_block":
        broken["parts"][0]["per_block_trial_counts"] = [2, 1]
    else:
        broken["parts"][0]["all_trial_response_identities_outcomes_and_rts_matched"] = False
    with pytest.raises(ValueError):
        pipeline.validate_execution(prepared, broken)


def test_native_pipeline_retains_exact_result_bytes_but_not_pcm(tmp_path):
    work, kept = tmp_path / "owned", tmp_path / "receipts"
    work.mkdir()
    kept.mkdir()
    raw = b'{"identity":"synthetic","unqualified":true}\n'
    (work / "result.results.json").write_bytes(raw)
    (work / "block.wav").write_bytes(b"only-owned-test-pcm")
    pipeline.retain_text_receipts(work, kept)
    assert (kept / "receipts/result.results.json").read_bytes() == raw
    assert not (kept / "receipts/block.wav").exists()
    assert (work / "block.wav").exists(), "retention does not delete before caller exits owned temporary scope"


def test_native_pipeline_disk_admission_preserves_part_and_iti_cost(tmp_path):
    cue = tmp_path / "assets/tactile/default_tactile_cue.wav"
    cue.parent.mkdir(parents=True)
    with wave.open(str(cue), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(8000)
        writer.writeframes(b"\0\0" * 800)
    captured = {"design": {"study_profile_reference_parameters": {"dashboard_run_setup": {}}},
                "block_csv_preview": {"blocks": [{"preview_rows": [
                    {"duration_s": 1, "iti_ms": "300", "row_label": "row",
                     "sequence_variant_key": "source", "family": "audio_tactile", "soa_ms": 200}]}]}}
    single = pipeline.preparation_disk_bound(captured, tmp_path)
    assert single == 128 * 1024 * 1024 + (10400 + 8000) * 12
    captured["design"]["study_profile_reference_parameters"]["dashboard_run_setup"]["experiment_structure"] = "pre_post"
    assert pipeline.preparation_disk_bound(captured, tmp_path) == 128 * 1024 * 1024 + 2 * (10400 + 8000) * 12
