"""Candidate native scoring must preserve the qualified V1 analysis contract."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from peripersonal_space_toolkit import session_runner as oracle


def _minimal(row: dict[str, Any], index: int) -> dict[str, str] | None:
    if oracle._is_data_min_filler_or_debug(row):
        return None
    return {key: str(value) for key, value in oracle._data_min_row_from_rich(row, trial_number_global=index).items()}


def _python_case(case: dict[str, Any]) -> dict[str, Any]:
    row, window = case["row"], case["window"]
    trial_type = str(oracle._row_value(row, "trial_type", "Trial_Type", default="")).strip()
    family = str(oracle._row_value(row, "family", "Family", default="")).strip()
    tactile = oracle._trial_has_tactile(trial_type, family, window["tactile_onset_ns"] is not None)
    catch = oracle._trial_is_catch(trial_type, family)
    required = oracle._trial_requires_response(row, trial_type=trial_type, family=family, tactile_present=tactile, catch_trial=catch)
    # Use the real selector without creating any participant file.
    writer = object.__new__(oracle.ParticipantTrialCsvWriter)
    writer.min_rt_s, writer.max_rt_s = 0.1, 1.3
    writer._used_click_ids = set(case["used"])
    writer._clicks = [{**response, "unix_time": response["monotonic_ns"] / 1e9, "response_choice": response["choice"]} for response in case["responses"]]
    selected, valid, given = writer._select_response(
        block_number=str(oracle._row_value(row, "block_number", "block_index", "Block_Number", default="")).strip(),
        trial_start_unix=window["trial_start_ns"] / 1e9,
        response_window_unix=window["response_window_ns"] / 1e9,
        tactile_unix=(window["tactile_onset_ns"] or 0) / 1e9,
        trial_end_unix=window["trial_end_ns"] / 1e9,
        tactile_present=tactile, catch_trial=catch, response_required=required,
    )
    choice_metadata = oracle._trial_response_choice_metadata(row)
    choice = oracle._response_choice_from_click(selected, choice_metadata)
    correct = oracle._response_choice_correctness(choice, choice_metadata["correct_response"])
    choice_required = oracle._trial_requires_choice_scoring(choice_metadata)
    hit = valid and (not choice_required or correct is True) if required else not given
    anchor = window["tactile_onset_ns"] if tactile and window["tactile_onset_ns"] is not None else window["response_window_ns"]
    score = {
        "response_event_id": selected.get("event_id"), "response_given": given,
        "valid_response": valid, "response_required": required, "choice_required": choice_required,
        "response_choice": choice, "response_correct": correct, "outcome": "Hit" if hit else "Miss",
        "rt_ms": f"{(selected['monotonic_ns'] - anchor) / 1e6:.3f}" if valid else "",
    }
    return {"id": case["id"], "score": score, "minimal": _minimal({**row, **score}, 1)}


def test_native_response_scoring_and_minimal_csv_match_python() -> None:
    window = {"trial_start_ns": 100_000_000_000, "response_window_ns": 102_000_000_000,
              "tactile_onset_ns": 102_300_000_000, "trial_end_ns": 104_000_000_000}
    base = {"participant_id": "fixture", "session_id": "S1", "part_number": 2, "block_index": 1,
            "Trial_UID": "T1", "Trial_Type": "Audio-Tactile", "Row_Label": "paced inhale", "SOA_ms": "300"}

    def response(event_id: int, time_ns: int, **extras: Any) -> dict[str, Any]:
        return {"event_id": event_id, "monotonic_ns": time_ns, "block_number": "1", "in_target": True,
                "during_playback": True, "choice": "", "x": None, "y": None, **extras}

    cases: list[dict[str, Any]] = []
    def add(case_id: str, responses: list[dict[str, Any]], *, row: dict[str, Any] | None = None,
            times: dict[str, Any] | None = None, used: list[int] | None = None) -> None:
        cases.append({"id": case_id, "row": {**base, **(row or {})}, "window": {**window, **(times or {})},
                      "responses": responses, "used": used or []})

    for offset in [-1, 0, 99_999_999, 100_000_000, 100_000_001, 1_299_999_999, 1_300_000_000, 1_300_000_001]:
        add(f"boundary-{offset}", [response(1, window["tactile_onset_ns"] + offset)])
    add("none", [])
    add("first-valid-not-first-click", [response(2, 102_400_000_000), response(1, 102_399_999_999)])
    add("same-time-lowest-id", [response(5, 102_400_000_000), response(2, 102_400_000_000)])
    add("used-and-inactive", [response(1, 102_400_000_000), response(2, 102_500_000_000, in_target=False),
                              response(3, 102_600_000_000, during_playback=False), response(4, 102_700_000_000, block_number="2")], used=[1])
    for kind in ["Catch", "Audio-Only", "Auditory-Only", "Baseline", "Filler", "Debug"]:
        for given in [False, True]:
            add(f"{kind}-{given}", [response(1, 102_100_000_000)] if given else [],
                row={"Trial_Type": kind}, times={"tactile_onset_ns": None})
    for field in ["Expected_Response", "Target_Role", "Response_Rule", "Family"]:
        for decision in ["withhold", "strong", "no-go", "weak_target", "respond", "strong_go", "not_target", ""]:
            add(f"expectation-{field}-{decision}", [response(1, 102_500_000_000)], row={field: decision})
    for policy in ["mouse_x_split", "mouse_y_split", "mouse_quadrant", "vertical_mouse", ""]:
        for x, y in [(0.2, 0.2), (0.8, 0.2), (0.2, 0.8), (0.8, 0.8), (500, 100), (None, None)]:
            add(f"choice-{policy}-{x}-{y}", [response(1, 102_500_000_000, x=x, y=y)],
                row={"Response_Choice_Set": "left|right|both|none", "Correct_Response": "left",
                     "Response_Mode": "cross-modal extinction report", "Response_Scoring_Policy": policy})
    add("explicit-choice", [response(1, 102_500_000_000, choice=" LEFT SIDE ")],
        row={"Choice_Set": "left side/right side", "Correct_Choice": "left-side", "Choice_Mode": "2afc"})
    add("one-choice", [response(1, 102_500_000_000)], row={"Choice_Set": "yes", "Correct_Choice": "yes"})
    add("late-after-short-trial", [response(1, 103_600_000_000)], times={"trial_end_ns": 102_350_000_000})
    add("no-tactile-event-kind-fallback", [response(1, 102_100_000_000)], times={"tactile_onset_ns": None})
    add("topup", [response(1, 102_500_000_000)], row={"Topup_Role": "filler"})
    projections = [{"row": row, "global_index": index + 1} for index, row in enumerate([
        {}, {"Response_Given": " ", "Hit_Miss": "hit-miss", "phase": "paced EXHALE"},
        {"Participant_ID": " p,\"quoted\"\nvalue", "Part_Number": 2, "Response_Given": 0, "RT_ms": "123.456"},
        {"trial_type": "debug"}, {"family": "filler"}, {"participant_id": "", "Participant_ID": "alias"},
        {"trial_number": 0, "trial_index": 9, "response_given": False, "Response_Given": "yes"},
    ])]
    cargo = shutil.which("cargo") or str(Path.home() / ".cargo" / "bin" / ("cargo.exe" if os.name == "nt" else "cargo"))
    completed = subprocess.run([cargo, "run", "--quiet", "--locked", "-p", "pps-runner-execution", "--example", "response_probe"],
                               cwd=Path(__file__).resolve().parents[3], input=json.dumps({"cases": cases, "projections": projections}),
                               text=True, capture_output=True, timeout=120, env={**os.environ, "CARGO_TERM_COLOR": "never"}, check=False)
    assert completed.returncode == 0, completed.stderr
    actual = json.loads(completed.stdout)
    expected = {"cases": [_python_case(case) for case in cases],
                "projections": [_minimal(entry["row"], entry["global_index"]) for entry in projections]}
    assert actual == expected
