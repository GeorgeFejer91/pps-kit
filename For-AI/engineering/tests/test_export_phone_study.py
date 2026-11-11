import csv
import json
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf


TOOL = Path(__file__).resolve().parents[1] / "tooling" / "export_phone_study.py"
exporter = run_path(str(TOOL))
phone_block = exporter["phone_block"]
export_study = exporter["export_study"]


@pytest.fixture
def crossed_hand_block(tmp_path):
    rate = 8_000
    pcm = np.zeros((3_000, 3), dtype=np.int16)
    pcm[40:120, :2] = [-7, 13]
    pcm[80:160, 2] = 19
    pcm[1_040:1_120, :2] = [13, -7]
    pcm[2_080:2_160, 2] = 19
    wav = tmp_path / "block.wav"
    sf.write(wav, pcm, rate, subtype="PCM_16")
    manifest = tmp_path / "block.csv"
    common = {
        "Expected_Response": "respond",
        "Response_Rule": "choose_external_stimulus_side",
        "Response_Choice_Set": "left,right",
        "Response_Scoring_Policy": "external_side_choice_150_to_1000_ms_analysis_window",
        "Tactile_Stimulation_Modality": "electrical",
    }
    rows = [
        {**common, "Trial_Type": "Audio-Tactile", "Correct_Response": "left", "Body_Side": "right",
         "Trial_Start_Sample": 0, "Trial_End_Sample": 1_000, "Looming_Onset_Sample": 40,
         "Tactile_Onset_Sample": 80, "Tactile_Duration_ms": 10, "Response_Window_Onset_Sample": 80},
        {**common, "Trial_Type": "Auditory-Only", "Correct_Response": "right", "Body_Side": "left",
         "Trial_Start_Sample": 1_000, "Trial_End_Sample": 2_000, "Looming_Onset_Sample": 1_040,
         "Tactile_Onset_Sample": "", "Tactile_Duration_ms": 0, "Response_Window_Onset_Sample": 1_040},
        {**common, "Trial_Type": "Baseline", "Correct_Response": "right", "Body_Side": "left",
         "Trial_Start_Sample": 2_000, "Trial_End_Sample": 3_000, "Looming_Onset_Sample": "",
         "Tactile_Onset_Sample": 2_080, "Tactile_Duration_ms": 10, "Response_Window_Onset_Sample": 2_080},
    ]
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (tmp_path / "audio").mkdir()
    block = SimpleNamespace(
        index=1, label="Crossed", metadata={}, wav_path=wav, manifest_path=manifest, trial_count=3,
    )
    return block, pcm


def test_lateralization_keeps_hand_and_external_choice_distinct(crossed_hand_block, tmp_path):
    block, pcm = crossed_hand_block
    clips = {}
    trials = phone_block(block, tmp_path, clips, lateralization=True)["trials"]

    assert [(trial["tactile_hand"], trial["correct_response"]) for trial in trials] == [
        ("right", "left"), (None, "right"), ("left", "right"),
    ]
    assert [(trial["audio_onset_sample"], trial["tactile_onset_sample"],
             trial["response_anchor_sample"], trial["tactile_duration_ms"]) for trial in trials] == [
        (40, 80, 80, 10), (1_040, None, 1_040, None), (None, 2_080, 2_080, 10),
    ]
    assert all(trial["response_scoring_policy"] == "external_side_choice_150_to_1000_ms_analysis_window"
               for trial in trials)
    assert trials[2]["clip"] is None
    decoded, rate = sf.read(tmp_path / clips[trials[0]["clip"]]["file"], dtype="int16", always_2d=True)
    assert rate == 8_000
    np.testing.assert_array_equal(decoded, pcm[:1_000, :2])


def test_choice_trial_cannot_be_exported_for_the_phone_vibrator(crossed_hand_block, tmp_path):
    block, _ = crossed_hand_block
    with pytest.raises(ValueError, match="additional stimulus or response device"):
        phone_block(block, tmp_path, {})
    assert not list((tmp_path / "audio").iterdir())


def test_lateralization_requires_the_stimulated_hand(crossed_hand_block, tmp_path):
    block, _ = crossed_hand_block
    with block.manifest_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fields = reader.fieldnames
    rows[0]["Body_Side"] = ""
    with block.manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="stimulated hand"):
        phone_block(block, tmp_path, {}, lateralization=True)


def test_lateralization_pack_uses_a_separate_schema(crossed_hand_block, tmp_path, monkeypatch):
    block, _ = crossed_hand_block
    profile = "tajadura_jimenez_2009_crossed_visual_deprivation"
    design = tmp_path / "design.json"
    design.write_text(json.dumps({"study_profile_id": profile}), encoding="utf-8")
    package = SimpleNamespace(
        sibling_part_manifest_paths=[], blocks=[block], part_number=1,
        session_group_id="fixture", design_path=design, instruction_profile={},
    )
    monkeypatch.setitem(export_study.__globals__, "load_run_package", lambda _: package)

    output = tmp_path / "hardware-schedule"
    export_study(profile, tmp_path / "session_manifest.json", output, lateralization=True)
    plan = json.loads((output / "study.json").read_text(encoding="utf-8"))
    assert plan["schema"] == "pps-phone-lateralization-schedule.v1"
    assert plan["required_output"] == "independent_electrical_tactile"
    assert plan["response_choices"] == ["left", "right"]
