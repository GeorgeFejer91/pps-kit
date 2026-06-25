from __future__ import annotations

import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

from peripersonal_space_toolkit.session_analysis import analyze_session_events, write_analysis_csvs
from peripersonal_space_toolkit.session_events import SessionEvent
from peripersonal_space_toolkit.session_runner import SessionRunnerController, prepare_segment_run_package
from peripersonal_space_toolkit.output_layout import output_prepared_blocks_dir
from peripersonal_space_toolkit.topup import HIT, MISSED_NEEDS_TOPUP, PENDING, TopUpLedger

sys.path.insert(0, str(Path(__file__).parent))
from test_session_runner import _segment_run_setup_fixture


def _event(event_id: int, event_type: str, unix_time: float, **payload):
    return SessionEvent(event_id=event_id, event_type=event_type, unix_time=unix_time, monotonic_time=unix_time, payload=payload)


def test_topup_ledger_tracks_hit_miss_and_ignores_late_click(tmp_path: Path):
    ledger = TopUpLedger(tmp_path, participant_id="P001", session_id="S001", min_rt_s=0.1, max_rt_s=1.0)

    ledger.observe_event(
        _event(
            1,
            "tactile_onset",
            10.0,
            trial_uid="T001",
            Trial_Type="Audio-Tactile",
            Family="audio_tactile",
            Row_Label="Inhale",
            SOA_ms=300,
            Trial_File_Path="trial.wav",
        )
    )
    ledger.observe_event(_event(2, "mouse_click", 10.25, in_target=True, during_playback=True))
    assert ledger.entries[0].status == HIT
    assert ledger.entries[0].rt_ms == 250.0

    ledger.observe_event(
        _event(
            3,
            "tactile_onset",
            20.0,
            trial_uid="T002",
            Trial_Type="Audio-Tactile",
            Family="audio_tactile",
            Row_Label="Exhale",
            SOA_ms=300,
            Trial_File_Path="trial.wav",
        )
    )
    ledger.expire_due(21.2)
    ledger.observe_event(_event(4, "mouse_click", 22.0, in_target=True, during_playback=True))
    assert ledger.entries[1].status == MISSED_NEEDS_TOPUP
    assert ledger.entries[1].click_event_id == ""

    outputs = ledger.write_outputs()
    assert outputs["topup_ledger_csv"].exists()
    assert outputs["topup_ledger_json"].exists()


def test_topup_ledger_resolves_valid_click_that_arrives_after_trial_boundary(tmp_path: Path):
    ledger = TopUpLedger(tmp_path, participant_id="P001", session_id="S001", min_rt_s=0.1, max_rt_s=3.0)

    ledger.observe_event(
        _event(
            1,
            "tactile_onset",
            10.0,
            trial_uid="T001",
            Trial_Type="Audio-Tactile",
            Family="audio_tactile",
            Row_Label="Inhale",
            SOA_ms=300,
            Trial_File_Path="trial.wav",
        )
    )
    ledger.observe_event(_event(2, "trial_start", 11.5, trial_uid="T002"))
    assert ledger.entries[0].status == PENDING

    ledger.observe_event(_event(3, "mouse_click", 12.42, in_target=True, during_playback=True))

    assert ledger.entries[0].status == HIT
    assert ledger.entries[0].click_event_id == 3
    assert round(float(ledger.entries[0].rt_ms), 3) == 2420.0
    assert ledger.entries[0].miss_reason == ""


def test_response_pairing_accepts_click_after_next_trial_start_within_response_window(tmp_path: Path):
    events = [
        _event(1, "trial_start", 10.0, trial_uid="T001"),
        _event(
            2,
            "tactile_onset",
            10.5,
            trial_uid="T001",
            Trial_Type="Audio-Tactile",
            Family="audio_tactile",
            SOA_ms=0,
        ),
        _event(3, "trial_start", 11.0, trial_uid="T002"),
        _event(4, "mouse_click", 11.0, in_target=True, during_playback=True),
    ]

    result = analyze_session_events(events)

    assert result.response_rows[0]["trial_uid"] == "T001"
    assert result.response_rows[0]["hit"] is True
    assert result.response_rows[0]["click_event_id"] == 4


def test_response_pairing_uses_four_second_window_and_first_valid_click(tmp_path: Path):
    events = [
        _event(1, "trial_start", 9.5, trial_uid="T001"),
        _event(
            2,
            "tactile_onset",
            10.0,
            trial_uid="T001",
            Trial_Type="Audio-Tactile",
            Family="audio_tactile",
            SOA_ms=0,
        ),
        _event(3, "mouse_click", 10.08, in_target=True, during_playback=True),
        _event(4, "mouse_click", 10.24, in_target=True, during_playback=True),
        _event(5, "mouse_click", 10.32, in_target=True, during_playback=True),
        _event(6, "trial_start", 19.5, trial_uid="T002"),
        _event(
            7,
            "tactile_onset",
            20.0,
            trial_uid="T002",
            Trial_Type="Audio-Tactile",
            Family="audio_tactile",
            SOA_ms=0,
        ),
        _event(8, "mouse_click", 24.0, in_target=True, during_playback=True),
        _event(9, "trial_start", 29.5, trial_uid="T003"),
        _event(
            10,
            "tactile_onset",
            30.0,
            trial_uid="T003",
            Trial_Type="Audio-Tactile",
            Family="audio_tactile",
            SOA_ms=0,
        ),
        _event(11, "mouse_click", 34.001, in_target=True, during_playback=True),
    ]

    result = analyze_session_events(events)
    by_uid = {row["trial_uid"]: row for row in result.response_rows}

    assert by_uid["T001"]["hit"] is True
    assert by_uid["T001"]["click_event_id"] == 4
    assert by_uid["T001"]["rt_ms"] == pytest.approx(240.0)
    assert by_uid["T002"]["hit"] is True
    assert by_uid["T002"]["rt_ms"] == pytest.approx(4000.0)
    assert by_uid["T003"]["hit"] is False


def test_topup_ledger_accepts_click_after_next_trial_start_within_response_window(tmp_path: Path):
    ledger = TopUpLedger(tmp_path, participant_id="P001", session_id="S001", min_rt_s=0.1, max_rt_s=3.0)

    ledger.observe_event(
        _event(
            1,
            "tactile_onset",
            10.5,
            trial_uid="T001",
            Trial_Type="Audio-Tactile",
            Family="audio_tactile",
            Row_Label="Inhale",
            SOA_ms=0,
            Trial_File_Path="trial.wav",
        )
    )
    ledger.observe_event(_event(2, "trial_start", 11.0, trial_uid="T002"))
    ledger.observe_event(_event(3, "mouse_click", 11.0, in_target=True, during_playback=True))

    assert ledger.entries[0].status == HIT
    assert ledger.entries[0].click_event_id == 3
    assert ledger.entries[0].miss_reason == ""


def test_topup_ledger_does_not_bind_topup_click_to_original_miss(tmp_path: Path):
    ledger = TopUpLedger(tmp_path, participant_id="P001", session_id="S001")

    ledger.observe_event(
        _event(
            1,
            "tactile_onset",
            10.0,
            trial_uid="ORIG",
            Trial_Type="Audio-Tactile",
            Family="audio_tactile",
            Row_Label="Inhale",
            SOA_ms=0,
            Trial_File_Path="trial.wav",
            block_number=1,
            part_number=1,
            is_topup=False,
        )
    )
    ledger.finalize_open_trials()
    assert ledger.entries[0].status == MISSED_NEEDS_TOPUP

    ledger.observe_event(
        _event(
            2,
            "tactile_onset",
            12.0,
            trial_uid="TOPUP",
            Trial_Type="Audio-Tactile",
            Family="audio_tactile",
            Row_Label="Inhale",
            SOA_ms=0,
            Trial_File_Path="trial.wav",
            block_number=2,
            part_number=1,
            is_topup=True,
            topup_role="rescue",
            source_trial_uid="ORIG",
        )
    )
    ledger.observe_event(_event(3, "mouse_click", 12.2, in_target=True, during_playback=True, block_number=2, part_number=1, is_topup=True))

    assert ledger.entries[0].status == MISSED_NEEDS_TOPUP
    assert ledger.entries[0].click_event_id == ""
    assert ledger.entries[1].status == HIT
    assert ledger.entries[1].click_event_id == 3


def test_topup_ledger_defaults_to_four_second_response_window(tmp_path: Path):
    ledger = TopUpLedger(tmp_path, participant_id="P001", session_id="S001")

    ledger.observe_event(
        _event(
            1,
            "tactile_onset",
            10.0,
            trial_uid="T001",
            Trial_Type="Audio-Tactile",
            Family="audio_tactile",
            Row_Label="Inhale",
            SOA_ms=0,
            Trial_File_Path="trial.wav",
        )
    )
    ledger.observe_event(_event(2, "mouse_click", 14.0, in_target=True, during_playback=True))
    assert ledger.entries[0].status == HIT
    assert ledger.entries[0].rt_ms == pytest.approx(4000.0)

    ledger.observe_event(
        _event(
            3,
            "tactile_onset",
            20.0,
            trial_uid="T002",
            Trial_Type="Audio-Tactile",
            Family="audio_tactile",
            Row_Label="Exhale",
            SOA_ms=0,
            Trial_File_Path="trial.wav",
        )
    )
    ledger.observe_event(_event(4, "mouse_click", 24.001, in_target=True, during_playback=True))
    ledger.expire_due(24.001)
    assert ledger.entries[1].status == MISSED_NEEDS_TOPUP
    assert ledger.entries[1].click_event_id == ""


def test_final_outcomes_use_topup_rescue_attempt():
    events = [
        {"event_id": 1, "event_type": "trial_start", "unix_time": 0.0, "monotonic_time": 0.0, "trial_uid": "ORIG"},
        {
            "event_id": 2,
            "event_type": "tactile_onset",
            "unix_time": 1.0,
            "monotonic_time": 1.0,
            "trial_uid": "ORIG",
            "Trial_Type": "Audio-Tactile",
            "Family": "audio_tactile",
            "SOA_ms": 300,
            "Respiratory_Phase": "Inhale",
        },
        {
            "event_id": 3,
            "event_type": "tactile_onset",
            "unix_time": 10.0,
            "monotonic_time": 10.0,
            "trial_uid": "TOPUP",
            "Trial_Type": "Audio-Tactile",
            "Family": "audio_tactile",
            "SOA_ms": 300,
            "Respiratory_Phase": "Inhale",
            "Is_Topup": "true",
            "Topup_Role": "rescue",
            "Source_Trial_UID": "ORIG",
        },
        {"event_id": 4, "event_type": "mouse_click", "unix_time": 10.25, "monotonic_time": 10.25, "in_target": True, "during_playback": True},
    ]
    result = analyze_session_events(events)

    assert len(result.response_rows) == 2
    assert len(result.final_outcome_rows) == 1
    final = result.final_outcome_rows[0]
    assert final["trial_uid"] == "ORIG"
    assert final["hit"] is True
    assert final["rescued_in_topup"] is True
    assert final["final_outcome_source"] == "topup_rescue"


def test_immediate_analysis_writes_sigmoid_logarithmic_and_linear_fit_outputs(tmp_path: Path):
    events = []
    event_id = 1
    for index, (soa, rt_s) in enumerate([(100, 0.34), (200, 0.30), (400, 0.24), (800, 0.20)], start=1):
        onset = index * 5.0
        events.append({"event_id": event_id, "event_type": "trial_start", "unix_time": onset - 1.0, "monotonic_time": onset - 1.0})
        event_id += 1
        events.append(
            {
                "event_id": event_id,
                "event_type": "tactile_onset",
                "unix_time": onset,
                "monotonic_time": onset,
                "trial_uid": f"T{index:03d}",
                "Trial_Type": "Audio-Tactile",
                "Family": "audio_tactile",
                "SOA_ms": soa,
                "Respiratory_Phase": "Inhale",
                "Noise_Type": "pink",
            }
        )
        event_id += 1
        events.append(
            {
                "event_id": event_id,
                "event_type": "mouse_click",
                "unix_time": onset + rt_s,
                "monotonic_time": onset + rt_s,
                "in_target": True,
                "during_playback": True,
            }
        )
        event_id += 1

    result = analyze_session_events(events)
    models = {row["model"] for row in result.model_fit_rows}
    assert {"linear", "logarithmic_decay", "sigmoid"} <= models
    outputs = write_analysis_csvs(result, tmp_path, "S001")
    assert outputs["model_fits"].exists()
    assert outputs["model_fit_comparison"].exists()
    assert outputs["final_trial_outcomes"].exists()


def test_immediate_analysis_summarizes_across_blocks_with_optional_part_pooling():
    events = []
    event_id = 1
    trials = [
        (1, 1, 100, 0.34),
        (1, 2, 100, 0.32),
        (1, 1, 200, 0.30),
        (1, 2, 200, 0.28),
        (2, 3, 100, 0.40),
        (2, 4, 100, 0.38),
        (2, 3, 200, 0.36),
        (2, 4, 200, 0.34),
    ]
    for index, (part, block, soa, rt_s) in enumerate(trials, start=1):
        onset = index * 5.0
        context = {
            "part_number": part,
            "block_number": block,
            "trial_uid": f"T{index:03d}",
            "Trial_Type": "Audio-Tactile",
            "SOA_ms": soa,
            "Respiratory_Phase": "Inhale",
            "Noise_Type": "pink",
        }
        events.append({"event_id": event_id, "event_type": "trial_start", "unix_time": onset - 1.0, "monotonic_time": onset - 1.0, **context})
        event_id += 1
        events.append({"event_id": event_id, "event_type": "tactile_onset", "unix_time": onset, "monotonic_time": onset, **context})
        event_id += 1
        events.append(
            {
                "event_id": event_id,
                "event_type": "mouse_click",
                "unix_time": onset + rt_s,
                "monotonic_time": onset + rt_s,
                "in_target": True,
                "during_playback": True,
                "part_number": part,
                "block_number": block,
            }
        )
        event_id += 1

    result = analyze_session_events(events)
    curve_rows = result.curve_rows
    separate = [row for row in curve_rows if row["aggregation_mode"] == "separate_parts"]
    pooled = [row for row in curve_rows if row["aggregation_mode"] == "pooled_parts"]

    assert {row["scope"] for row in separate} == {"Part 1 / Inhale / pink", "Part 2 / Inhale / pink"}
    assert {row["scope"] for row in pooled} == {"All parts / Inhale / pink"}
    assert all("block" not in str(row["scope"]).lower() for row in curve_rows)
    part1_100 = next(row for row in separate if row["scope"] == "Part 1 / Inhale / pink" and row["soa_ms"] == 100)
    pooled_100 = next(row for row in pooled if row["soa_ms"] == 100)
    assert part1_100["n"] == 2
    assert pooled_100["n"] == 4
    assert part1_100["sem_rt_ms"] != ""


class _TopupAwareMockAudioEngine:
    def __init__(self):
        self.played: list[str] = []
        self.recordings: list[str] = []
        self.on_tactile = None

    def play_block(self, path: str, progress_callback=None, audio_event_callback=None, block_event_schedule=None) -> bool:
        self.played.append(path)
        is_topup = "topup" in Path(path).name
        if audio_event_callback and block_event_schedule is not None:
            block_event_schedule.reset()
            for event in block_event_schedule.consume_buffer(0, 44100 * 20):
                now = time.perf_counter()
                payload = dict(event.payload)
                payload.update(
                    {
                        "event_type": event.event_type,
                        "sample_index": event.sample_index,
                        "buffer_start_sample": 0,
                        "sample_offset_in_buffer": event.sample_index,
                        "sample_rate": 44100,
                        "trigger_key": event.trigger_key,
                        "callback_perf_counter": now,
                        "stream_current_time": now,
                        "stream_output_buffer_dac_time": now,
                    }
                )
                audio_event_callback(payload)
                if is_topup and event.event_type == "tactile_onset" and self.on_tactile is not None:
                    time.sleep(0.14)
                    self.on_tactile()
        if progress_callback:
            progress_callback(0.0)
            progress_callback(0.01)
        return True

    def trigger_click(self, metadata=None, marker_gain=None) -> None:
        return None

    def start_recording(self, output_path=None) -> bool:
        self.recordings.append(str(output_path))
        return True

    def stop_recording(self, output_path=None, interrupted=False):
        return None


def test_session_runner_plays_enabled_topup_block_without_approval_callback_and_writes_final_outcomes(tmp_path: Path):
    run_manifest = _segment_run_setup_fixture(tmp_path)
    package = prepare_segment_run_package(
        run_manifest,
        "P001",
        session_root=tmp_path / "sessions",
        created_at=datetime(2026, 1, 2, 3, 4, 5),
        split_parts=False,
    )
    engine = _TopupAwareMockAudioEngine()
    controller = SessionRunnerController(package, audio_engine=engine, enable_topup=True)
    engine.on_tactile = lambda: controller.log_click(x=1, y=1)

    result = controller.run()

    assert result.completed
    assert len(engine.played) == 2
    assert Path(engine.played[1]).name == "Block_02_topup_missed_trials.wav"
    assert result.analysis_outputs["topup_ledger_csv"].exists()
    assert result.analysis_outputs["topup_block_manifest"].exists()
    assert result.analysis_outputs["topup_block_wav"].exists()
    assert result.analysis_outputs["topup_block_wav"].parent == output_prepared_blocks_dir(package.session_dir.parent) / package.session_id / "blocks"
    final_outcomes = result.analysis_outputs["final_trial_outcomes"]
    assert final_outcomes.exists()
    with final_outcomes.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert rows[0]["final_outcome_source"] == "topup_rescue"
    assert rows[0]["rescued_in_topup"] == "True"


def test_session_runner_plays_one_topup_at_end_of_each_part(tmp_path: Path):
    run_manifest = _segment_run_setup_fixture(tmp_path)
    manifest = json.loads(run_manifest.read_text(encoding="utf-8"))
    order_csv = Path(manifest["csv_path"])
    rows = list(csv.DictReader(order_csv.open(encoding="utf-8")))
    template = next(row for row in rows if row["participant_id"] == "P001")
    fieldnames = list(rows[0].keys())
    two_part_rows = []
    for phase, phase_label, phase_index in (("pre", "Part 1", 1), ("post", "Part 2", 2)):
        row = dict(template)
        row.update(
            {
                "experiment_structure": "pre_post",
                "phase": phase,
                "phase_label": phase_label,
                "phase_index": phase_index,
                "participant_block_position": 1,
                "block_label": f"{phase_label} Block 01",
            }
        )
        two_part_rows.append(row)
    with order_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(two_part_rows)
    manifest.update(
        {
            "experiment_structure": "pre_post",
            "participant_count": 1,
            "parts_per_participant": 2,
            "total_block_runs": 2,
        }
    )
    run_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    package = prepare_segment_run_package(
        run_manifest,
        "P001",
        session_root=tmp_path / "sessions",
        created_at=datetime(2026, 1, 2, 3, 4, 5),
        split_parts=False,
    )
    engine = _TopupAwareMockAudioEngine()
    controller = SessionRunnerController(
        package,
        audio_engine=engine,
        enable_topup=True,
        topup_approval_callback=lambda _summary: True,
        instruction_continue_callback=lambda _context: True,
    )
    engine.on_tactile = lambda: controller.log_click(x=1, y=1)

    result = controller.run()

    assert result.completed
    assert len(engine.played) == 4
    assert "Block_01_from" in Path(engine.played[0]).name
    assert "part1_topup" in Path(engine.played[1]).name
    assert "Block_02_from" in Path(engine.played[2]).name
    assert "part2_topup" in Path(engine.played[3]).name
    assert result.analysis_outputs["topup_block_manifest_part1"].exists()
    assert result.analysis_outputs["topup_block_manifest_part2"].exists()
    assert result.analysis_outputs["topup_block_wav_part1"].exists()
    assert result.analysis_outputs["topup_block_wav_part2"].exists()
    assert result.analysis_outputs["topup_block_wav_part1"].parent == output_prepared_blocks_dir(package.session_dir.parent) / package.session_id / "blocks"
    assert result.analysis_outputs["topup_block_wav_part2"].parent == output_prepared_blocks_dir(package.session_dir.parent) / package.session_id / "blocks"
    part1_rows = list(csv.DictReader(result.analysis_outputs["topup_block_manifest_part1"].open(encoding="utf-8")))
    part2_rows = list(csv.DictReader(result.analysis_outputs["topup_block_manifest_part2"].open(encoding="utf-8")))
    assert {row["Part_Number"] for row in part1_rows} == {"1"}
    assert {row["Part_Number"] for row in part2_rows} == {"2"}
