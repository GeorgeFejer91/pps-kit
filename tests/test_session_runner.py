from __future__ import annotations

import csv
import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from peripersonal_space_toolkit import session_runner as session_runner_module
from peripersonal_space_toolkit.design import ProtocolSpec, default_design
from peripersonal_space_toolkit.session_runner import (
    SessionRunnerController,
    claim_prepared_session,
    load_last_experiment_pointer,
    prepare_all_segment_run_packages,
    prepare_run_package,
    prepare_segment_run_package,
    prepared_session_asset_status,
    preflight_run_package,
    record_experiment_activity,
    record_prepared_session_queue,
    segment_run_setup_participants,
)


def _compact_design():
    design = default_design()
    design.noises = design.noises[:1]
    design.protocol = ProtocolSpec(
        repetitions_per_condition=1,
        soa_values_ms=[300],
        spatial_values_cm=[100.0],
        pair_spatial_values_with_soas=True,
        auditory_motion_directions=["looming"],
        tactile_sites=["hand"],
        include_catch_trials=False,
        catch_trial_percentage=0.0,
        include_baseline_trials=False,
        respiratory_phases=["Inhale"],
        blocks=1,
        participants=1,
        random_seed=20250604,
    )
    return design


def _render_dir(tmp_path: Path) -> Path:
    render_dir = tmp_path / "rendered"
    render_dir.mkdir()
    wav_path = render_dir / "looming_pink_frontal.wav"
    data = np.zeros((441, 3), dtype=np.float32)
    sf.write(wav_path, data, 44100)
    (render_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "schema": "pps-render-manifest.v1",
                "status": "rendered_reference",
                "wav_outputs": [{"path": str(wav_path), "sha256": "test"}],
            }
        ),
        encoding="utf-8",
    )
    return render_dir


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _segment_run_setup_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    block_root = root / "5_block_csv_preview"
    run_root = root / "6_experiment_run_setup"
    block_root.mkdir(parents=True)
    run_root.mkdir(parents=True)

    target = tmp_path / "target.wav"
    catch = tmp_path / "catch.wav"
    sf.write(target, np.column_stack([np.ones(441), np.ones(441) * 0.5, np.ones(441) * 0.25]).astype(np.float32), 44100)
    sf.write(catch, np.column_stack([np.ones(220) * 0.1, np.ones(220) * 0.2]).astype(np.float32), 44100)

    block_csv = block_root / "block_01_final.csv"
    with block_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "block_trial_index",
                "family",
                "row_label",
                "noise_type",
                "soa_ms",
                "sequence_labels",
                "sequence_variant_key",
                "source_file_name",
                "trial_file_path",
                "source_sha256",
                "duration_ms",
                "duration_s",
                "looming_segment_onset_s",
                "tactile_onset_s",
                "channels",
                "tactile_channel",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "block_trial_index": 1,
                "family": "audio_tactile",
                "row_label": "Inhale",
                "noise_type": "pink",
                "soa_ms": 10,
                "sequence_labels": "Inhale | Pink",
                "sequence_variant_key": "inhale_pink",
                "source_file_name": target.name,
                "trial_file_path": str(target),
                "source_sha256": _sha256(target),
                "duration_ms": 10,
                "duration_s": 0.01,
                "looming_segment_onset_s": 0.004,
                "tactile_onset_s": 0.014,
                "channels": 3,
                "tactile_channel": 3,
            }
        )
        writer.writerow(
            {
                "block_trial_index": 2,
                "family": "catch",
                "row_label": "Exhale",
                "noise_type": "pink",
                "soa_ms": 0,
                "sequence_labels": "Exhale | Pink",
                "sequence_variant_key": "exhale_pink",
                "source_file_name": catch.name,
                "trial_file_path": str(catch),
                "source_sha256": _sha256(catch),
                "duration_ms": 5,
                "duration_s": 0.005,
                "looming_segment_onset_s": 0.0,
                "tactile_onset_s": "",
                "channels": 2,
                "tactile_channel": "",
            }
        )

    block_manifest = block_root / "block_csv_preview_manifest.json"
    block_manifest.write_text(
        json.dumps(
            {
                "schema": "pps-block-csv-preview.v1",
                "accepted": True,
                "blocks": [{"block_index": 1, "csv_path": str(block_csv), "csv_file_name": block_csv.name, "trial_count": 2}],
            }
        ),
        encoding="utf-8",
    )

    order_csv = run_root / "experiment_block_order.csv"
    with order_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "participant_id",
                "participant_index",
                "experiment_structure",
                "phase",
                "phase_label",
                "phase_index",
                "participant_block_position",
                "source_block_index",
                "block_label",
                "block_csv_file",
                "block_csv_path",
                "trial_count",
                "duration_ms",
                "sequence_seed",
            ],
        )
        writer.writeheader()
        for participant in ("P001", "P002"):
            writer.writerow(
                {
                    "participant_id": participant,
                    "participant_index": participant[-1],
                    "experiment_structure": "single",
                    "phase": "single",
                    "phase_label": "Single",
                    "phase_index": 1,
                    "participant_block_position": 1,
                    "source_block_index": 1,
                    "block_label": "Block 01",
                    "block_csv_file": block_csv.name,
                    "block_csv_path": str(block_csv),
                    "trial_count": 2,
                    "duration_ms": 15,
                    "sequence_seed": 123,
                }
            )

    run_manifest = run_root / "experiment_run_setup_manifest.json"
    run_manifest.write_text(
        json.dumps(
            {
                "schema": "pps-experiment-run-setup.v1",
                "status": "prepared",
                "prepared": True,
                "csv_path": str(order_csv),
                "experiment_structure": "single",
                "participant_count": 2,
                "parts_per_participant": 1,
                "blocks_per_part": 1,
                "total_block_runs": 2,
                "seed": 123,
                "source_segment5_manifest": str(block_manifest),
                "source_segment5_manifest_sha256": _sha256(block_manifest),
            }
        ),
        encoding="utf-8",
    )
    return run_manifest


def test_preflight_reports_missing_render_and_ready_state(tmp_path: Path):
    design = _compact_design()

    missing = preflight_run_package(design, "P001", render_dir=tmp_path / "missing")
    assert missing.participant_ready
    assert not missing.render_ready
    assert not missing.ready

    ready = preflight_run_package(design, "P001", render_dir=_render_dir(tmp_path))
    assert ready.render_ready
    assert ready.schedule_ready
    assert ready.ready
    assert ready.rendered_wavs[0].channels == 3


def test_prepare_run_package_writes_manifest_protocol_and_blocks(tmp_path: Path):
    design = _compact_design()
    package = prepare_run_package(
        design,
        "Subject 01",
        render_dir=_render_dir(tmp_path),
        session_root=tmp_path / "sessions",
        created_at=datetime(2026, 1, 2, 3, 4, 5),
    )

    assert package.participant_id == "Subject_01"
    assert package.session_dir.name == "Subject_01_20260102_030405"
    assert package.design_path.exists()
    assert package.protocol_path.exists()
    assert package.manifest_path.exists()
    assert len(package.blocks) == 1
    assert package.blocks[0].manifest_path.exists()
    assert package.blocks[0].wav_path.exists()

    manifest = json.loads(package.manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == "pps-run-session.v1"
    assert manifest["audio_route"]["channels"] == 3

    with package.blocks[0].manifest_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows
    assert rows[0]["Participant_ID"] == "Subject_01"
    assert rows[0]["Trial_Type"] == "Audio-Tactile"


def test_prepare_segment_run_package_uses_segment5_and_segment6_csvs(tmp_path: Path):
    run_manifest = _segment_run_setup_fixture(tmp_path)

    assert segment_run_setup_participants(run_manifest) == ["P001", "P002"]

    package = prepare_segment_run_package(
        run_manifest,
        "P001",
        session_root=tmp_path / "sessions",
        created_at=datetime(2026, 1, 2, 3, 4, 5),
    )

    assert package.execution_mode == "participant_block_wavs"
    assert package.participant_id == "P001"
    assert package.manifest_path.exists()
    assert len(package.blocks) == 1
    assert package.blocks[0].metadata["source_block_index"] == 1

    block_audio, sample_rate = sf.read(package.blocks[0].wav_path, always_2d=True)
    assert sample_rate == 44100
    assert block_audio.shape == (661, 3)
    assert np.max(np.abs(block_audio[441:, 2])) == pytest.approx(0.0)

    with package.blocks[0].manifest_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["Trial_Type"] for row in rows] == ["Audio-Tactile", "Catch"]
    assert rows[0]["Trial_Start_Sample"] == "0"
    assert rows[1]["Trial_Start_Sample"] == "441"
    assert rows[0]["Tactile_Onset_Sample"] == str(int(round(0.014 * sample_rate)))
    assert rows[0]["Source_Block_CSV_SHA256"]

    manifest = json.loads(package.manifest_path.read_text(encoding="utf-8"))
    assert manifest["execution_mode"] == "participant_block_wavs"
    assert manifest["source_run_setup_manifest_path"] == str(run_manifest)


def test_prepare_segment_run_package_reports_progress_and_reuses_block_cache(tmp_path: Path):
    run_manifest = _segment_run_setup_fixture(tmp_path)
    cache_root = tmp_path / "block_cache"
    first_events: list[dict[str, object]] = []
    second_events: list[dict[str, object]] = []

    first = prepare_segment_run_package(
        run_manifest,
        "P001",
        session_root=tmp_path / "sessions",
        created_at=datetime(2026, 1, 2, 3, 4, 5),
        block_cache_root=cache_root,
        progress_callback=first_events.append,
    )
    second = prepare_segment_run_package(
        run_manifest,
        "P002",
        session_root=tmp_path / "sessions",
        created_at=datetime(2026, 1, 2, 3, 4, 6),
        block_cache_root=cache_root,
        progress_callback=second_events.append,
    )

    assert first.blocks[0].metadata["block_cache_status"] == "miss_stored"
    assert second.blocks[0].metadata["block_cache_status"] == "hit"
    assert second.blocks[0].metadata["block_cache_link_mode"] in {"hardlink", "copy"}
    assert first.blocks[0].wav_path.exists()
    assert second.blocks[0].wav_path.exists()
    assert {event["phase"] for event in first_events} >= {
        "checking",
        "segment6",
        "loading_wavs",
        "assembling_block",
        "writing_manifest",
        "opening_focus_mode",
    }
    assert "block_cache_hit" in {event["phase"] for event in second_events}
    block_events = [event for event in first_events if event["phase"] in {"assembling_block", "writing_manifest"}]
    assert all(event["total"] == 1 for event in block_events)


def test_prepare_segment_run_package_rebuilds_invalid_block_cache(tmp_path: Path):
    run_manifest = _segment_run_setup_fixture(tmp_path)
    cache_root = tmp_path / "block_cache"
    first = prepare_segment_run_package(
        run_manifest,
        "P001",
        session_root=tmp_path / "sessions",
        created_at=datetime(2026, 1, 2, 3, 4, 5),
        block_cache_root=cache_root,
    )
    cache_key = str(first.blocks[0].metadata["block_cache_key"])
    cache_manifest = next(cache_root.glob(f"*/{cache_key}/block_cache_manifest.json"))
    payload = json.loads(cache_manifest.read_text(encoding="utf-8"))
    payload["version"] = "stale-cache-version"
    cache_manifest.write_text(json.dumps(payload), encoding="utf-8")

    rebuilt = prepare_segment_run_package(
        run_manifest,
        "P002",
        session_root=tmp_path / "sessions",
        created_at=datetime(2026, 1, 2, 3, 4, 6),
        block_cache_root=cache_root,
    )

    assert rebuilt.blocks[0].metadata["block_cache_status"] == "miss_stored"


def test_block_cache_link_falls_back_to_copy(tmp_path: Path, monkeypatch):
    source = tmp_path / "cached.wav"
    target = tmp_path / "session" / "block.wav"
    source.write_bytes(b"cached block")

    def fail_link(_source, _target):
        raise OSError("hardlinks unavailable")

    monkeypatch.setattr(session_runner_module.os, "link", fail_link)

    mode = session_runner_module._link_or_copy_cached_block(source, target)

    assert mode == "copy"
    assert target.read_bytes() == b"cached block"


def test_prepared_session_queue_claims_only_matching_current_setup(tmp_path: Path):
    run_manifest = _segment_run_setup_fixture(tmp_path)
    package = prepare_segment_run_package(
        run_manifest,
        "P002",
        session_root=tmp_path / "sessions",
        created_at=datetime(2026, 1, 2, 3, 4, 5),
    )
    state_root = tmp_path / "state"
    record_prepared_session_queue(
        participant_id="P002",
        run_setup_manifest_path=run_manifest,
        session_manifest_path=package.manifest_path,
        status="ready",
        state_root=state_root,
    )

    assert claim_prepared_session(run_manifest, "P002", state_root=state_root) == package.manifest_path.resolve()
    record_prepared_session_queue(
        participant_id="P002",
        run_setup_manifest_path=run_manifest,
        session_manifest_path=package.manifest_path,
        status="ready",
        state_root=state_root,
    )
    manifest_payload = json.loads(run_manifest.read_text(encoding="utf-8"))
    manifest_payload["seed"] = 999
    run_manifest.write_text(json.dumps(manifest_payload), encoding="utf-8")

    assert claim_prepared_session(run_manifest, "P002", state_root=state_root) is None
    queue = json.loads((state_root / "prepared_session_queue.v1.json").read_text(encoding="utf-8"))
    assert queue["entries"][-1]["status"] == "stale"


def test_prepared_session_asset_status_reports_ready_and_generated_packages(tmp_path: Path):
    run_manifest = _segment_run_setup_fixture(tmp_path)
    session_root = tmp_path / "sessions"
    state_root = tmp_path / "state"
    package = prepare_segment_run_package(
        run_manifest,
        "P001",
        session_root=session_root,
        created_at=datetime(2026, 1, 2, 3, 4, 5),
    )

    scanned = prepared_session_asset_status(
        run_manifest,
        "P001",
        state_root=state_root,
        session_root=session_root,
    )

    assert scanned["generated"] is True
    assert scanned["status"] == "generated"
    assert scanned["session_manifest_path"] == str(package.manifest_path.resolve())

    record_prepared_session_queue(
        participant_id="P001",
        run_setup_manifest_path=run_manifest,
        session_manifest_path=package.manifest_path,
        status="ready",
        state_root=state_root,
    )
    queued = prepared_session_asset_status(
        run_manifest,
        "P001",
        state_root=state_root,
        session_root=session_root,
    )

    assert queued["generated"] is True
    assert queued["status"] == "ready"
    assert queued["source"] == "prepared_session_queue"
    assert queued["data_collected"] is False

    with (package.session_dir / "events.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["event_id", "event_type", "unix_time", "monotonic_time", "payload_json"])
        writer.writeheader()
        writer.writerow(
            {
                "event_id": 1,
                "event_type": "session_end",
                "unix_time": "1.0",
                "monotonic_time": "1.0",
                "payload_json": json.dumps({"completed": True, "interrupted": False}),
            }
        )
    collected = prepared_session_asset_status(
        run_manifest,
        "P001",
        state_root=state_root,
        session_root=session_root,
    )

    assert collected["generated"] is True
    assert collected["data_collected"] is True
    assert collected["data_collection_status"] == "collected"
    assert collected["data_session_manifest_path"] == str(package.manifest_path.resolve())

    package.blocks[0].wav_path.unlink()
    missing = prepared_session_asset_status(
        run_manifest,
        "P001",
        state_root=state_root,
        session_root=session_root,
    )

    assert missing["generated"] is False
    assert missing["status"] == "not_generated"
    assert "missing" in missing["message"].lower()


def test_run_playback_numbering_places_topups_in_play_order():
    blocks = [
        session_runner_module.RunBlock(
            index=index,
            label=f"Block {index:02d}",
            manifest_path=Path(f"block_{index:02d}.csv"),
            wav_path=Path(f"block_{index:02d}.wav"),
            trial_count=1,
            duration_s=1.0,
            metadata={"part_number": 1 if index <= 6 else 2},
        )
        for index in range(1, 13)
    ]

    display_by_block, topup_by_part, total = session_runner_module._run_playback_numbering(
        blocks,
        include_topup_slots=True,
    )

    assert display_by_block[1] == 1
    assert display_by_block[6] == 6
    assert topup_by_part["1"] == 7
    assert display_by_block[7] == 8
    assert display_by_block[12] == 13
    assert topup_by_part["2"] == 14
    assert total == 14


def test_non_launchable_activity_does_not_overwrite_last_experiment_pointer(tmp_path: Path):
    state_root = tmp_path / "state"
    record_experiment_activity(
        "session_prepared",
        state_root=state_root,
        session_manifest_path="C:/valid/session_manifest.json",
        run_setup_manifest_path="C:/valid/experiment_run_setup_manifest.json",
        participant_id="P001",
    )
    record_experiment_activity(
        "project_edited",
        state_root=state_root,
        session_manifest_path="C:/temp/not_launchable/session_manifest.json",
        run_setup_manifest_path="C:/temp/not_launchable/experiment_run_setup_manifest.json",
        participant_id="P999",
    )

    pointer = load_last_experiment_pointer(state_root=state_root)
    assert pointer["session_manifest_path"] == "C:/valid/session_manifest.json"
    assert pointer["run_setup_manifest_path"] == "C:/valid/experiment_run_setup_manifest.json"
    assert pointer["participant_id"] == "P001"
    assert pointer["last_event_type"] == "session_prepared"
    assert len((state_root / "experiment_activity_log.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_prepare_segment_run_package_uses_segment6_order_not_filename_sort(tmp_path: Path):
    run_manifest = _segment_run_setup_fixture(tmp_path)
    project_root = run_manifest.parent.parent
    block_root = project_root / "5_block_csv_preview"
    block_01 = block_root / "block_01_final.csv"
    block_02 = block_root / "block_02_final.csv"
    block_02.write_text(block_01.read_text(encoding="utf-8"), encoding="utf-8")

    order_csv = run_manifest.parent / "experiment_block_order.csv"
    with order_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        original_rows = list(reader)
        fieldnames = list(reader.fieldnames or [])
    p001 = [dict(row) for row in original_rows if row["participant_id"] == "P001"][0]
    p002 = [dict(row) for row in original_rows if row["participant_id"] == "P002"][0]
    first = dict(p001)
    first.update(
        {
            "participant_block_position": 1,
            "source_block_index": 2,
            "block_label": "Block 02",
            "block_csv_file": block_02.name,
            "block_csv_path": str(block_02),
        }
    )
    second = dict(p001)
    second.update(
        {
            "participant_block_position": 2,
            "source_block_index": 1,
            "block_label": "Block 01",
            "block_csv_file": block_01.name,
            "block_csv_path": str(block_01),
        }
    )
    with order_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows([first, second, p002])

    manifest = json.loads(run_manifest.read_text(encoding="utf-8"))
    manifest["total_block_runs"] = 3
    run_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    package = prepare_segment_run_package(
        run_manifest,
        "P001",
        session_root=tmp_path / "sessions",
        created_at=datetime(2026, 1, 2, 3, 4, 5),
    )

    assert [block.metadata["source_block_index"] for block in package.blocks] == [2, 1]
    assert [block.wav_path.name for block in package.blocks] == [
        "Block_01_from_block_02_final.wav",
        "Block_02_from_block_01_final.wav",
    ]
    assert not list((tmp_path / "sessions").glob("P002_*"))


def test_prepare_segment_run_package_rejects_missing_participant(tmp_path: Path):
    run_manifest = _segment_run_setup_fixture(tmp_path)
    with pytest.raises(ValueError, match="P999"):
        prepare_segment_run_package(run_manifest, "P999", session_root=tmp_path / "sessions")


def test_prepare_all_segment_run_packages_generates_each_participant(tmp_path: Path):
    run_manifest = _segment_run_setup_fixture(tmp_path)
    packages = prepare_all_segment_run_packages(
        run_manifest,
        session_root=tmp_path / "sessions",
        created_at=datetime(2026, 1, 2, 3, 4, 5),
    )

    assert [package.participant_id for package in packages] == ["P001", "P002"]
    assert all(package.blocks[0].wav_path.exists() for package in packages)


def test_prepare_segment_run_package_copies_instruction_audio(tmp_path: Path):
    run_manifest = _segment_run_setup_fixture(tmp_path)
    instruction = tmp_path / "general_instruction.wav"
    sf.write(instruction, np.zeros((441, 1), dtype=np.float32), 44100)
    manifest = json.loads(run_manifest.read_text(encoding="utf-8"))
    manifest["instruction_profile"] = {
        "schema": "pps-run-instructions.v1",
        "slots": [
            {
                "slot": "before_experiment",
                "label": "General instructions",
                "enabled": True,
                "path": str(instruction),
                "continue_mode": "delay",
                "delay_s": 0.0,
            }
        ],
    }
    run_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    package = prepare_segment_run_package(
        run_manifest,
        "P001",
        session_root=tmp_path / "sessions",
        created_at=datetime(2026, 1, 2, 3, 4, 5),
    )

    slot = package.instruction_profile["slots"][0]
    copied = Path(slot["path"])
    assert copied.parent == package.session_dir / "instructions"
    assert copied.exists()
    assert copied.name == "before_experiment.wav"
    session_manifest = json.loads(package.manifest_path.read_text(encoding="utf-8"))
    assert session_manifest["instruction_profile"]["slots"][0]["path"] == str(copied)
    assert session_manifest["instruction_profile"]["slots"][0]["sha256"]


def test_prepare_segment_run_package_keeps_missing_instruction_optional(tmp_path: Path):
    run_manifest = _segment_run_setup_fixture(tmp_path)
    missing_instruction = tmp_path / "missing_instruction.wav"
    manifest = json.loads(run_manifest.read_text(encoding="utf-8"))
    manifest["instruction_profile"] = {
        "schema": "pps-run-instructions.v1",
        "slots": [
            {
                "slot": "before_experiment",
                "label": "Optional start message",
                "enabled": True,
                "required": False,
                "path": str(missing_instruction),
                "continue_mode": "delay",
                "delay_s": 0.0,
            }
        ],
    }
    run_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    package = prepare_segment_run_package(
        run_manifest,
        "P001",
        session_root=tmp_path / "sessions",
        created_at=datetime(2026, 1, 2, 3, 4, 5),
    )

    slot = package.instruction_profile["slots"][0]
    assert slot["enabled"] is True
    assert slot["required"] is False
    assert slot["path"] == str(missing_instruction)
    assert not (package.session_dir / "instructions").exists()


class _MockAudioEngine:
    def __init__(self):
        self.played: list[str] = []
        self.stopped = False
        self.paused = False
        self.click_metadata: dict[str, object] = {}
        self.marker_gain = None
        self.recordings: list[str] = []
        self.on_audio_started = None

    def play_block(self, path: str, progress_callback=None, audio_event_callback=None, block_event_schedule=None) -> bool:
        self.played.append(path)
        if audio_event_callback:
            if block_event_schedule is not None:
                block_event_schedule.reset()
                for event in block_event_schedule.consume_buffer(0, 44100 * 20):
                    payload = dict(event.payload)
                    payload.update(
                        {
                            "event_type": event.event_type,
                            "sample_index": event.sample_index,
                            "buffer_start_sample": 0,
                            "sample_offset_in_buffer": event.sample_index,
                            "sample_rate": 44100,
                            "trigger_key": event.trigger_key,
                            "callback_perf_counter": 10.0,
                            "stream_current_time": 5.0,
                            "stream_output_buffer_dac_time": 5.0,
                        }
                    )
                    audio_event_callback(payload)
                    if event.event_type == "audio_sample_zero" and self.on_audio_started:
                        self.on_audio_started()
            else:
                audio_event_callback(
                    {
                        "event_type": "audio_sample_zero",
                        "sample_index": 0,
                        "buffer_start_sample": 0,
                        "sample_offset_in_buffer": 0,
                        "sample_rate": 44100,
                        "callback_perf_counter": 10.0,
                    }
                )
                if self.on_audio_started:
                    self.on_audio_started()
            if self.click_metadata:
                audio_event_callback(
                    {
                        "event_type": "response_marker_start",
                        "sample_index": 1,
                        "buffer_start_sample": 0,
                        "sample_offset_in_buffer": 1,
                        "sample_rate": 44100,
                        "callback_perf_counter": 10.0,
                        "stream_current_time": 5.0,
                        "stream_output_buffer_dac_time": 5.0,
                        "marker_channel": 2,
                        "marker_gain": self.marker_gain,
                        **self.click_metadata,
                    }
                )
        if progress_callback:
            progress_callback(0.0)
            progress_callback(0.01)
        return not self.stopped

    def play_instruction(self, path: str, on_complete=None) -> bool:
        self.played.append(f"instruction:{path}")
        if on_complete:
            on_complete(True)
        return True

    def stop(self) -> None:
        self.stopped = True

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False

    def trigger_click(self, metadata=None, marker_gain=None) -> None:
        self.click_metadata = dict(metadata or {})
        self.marker_gain = marker_gain

    def start_recording(self, output_path=None) -> bool:
        self.recordings.append(str(output_path))
        return True

    def stop_recording(self, output_path=None, interrupted=False):
        return np.zeros((10, 3), dtype=np.float32)


def test_session_runner_controller_writes_events_and_analysis(tmp_path: Path):
    design = _compact_design()
    package = prepare_run_package(
        design,
        "P001",
        render_dir=_render_dir(tmp_path),
        session_root=tmp_path / "sessions",
        created_at=datetime(2026, 1, 2, 3, 4, 5),
    )
    engine = _MockAudioEngine()
    controller = SessionRunnerController(
        package,
        audio_engine=engine,
        runner_metadata={
            "participant_code": "P001",
            "participant_name": "Alice Example",
            "include_name_in_lsl": False,
            "age_years": "29",
            "handedness": "right",
            "gender": "female",
        },
    )
    engine.on_audio_started = lambda: controller.log_click(x=10, y=12)

    result = controller.run()

    assert result.completed
    assert engine.played == [str(package.blocks[0].wav_path)]
    assert result.events_csv.exists()
    assert result.events_xdf.exists()
    assert result.lsl_markers_csv and result.lsl_markers_csv.exists()
    assert result.lsl_markers_xdf and result.lsl_markers_xdf.exists()
    assert result.trigger_dictionary_path and result.trigger_dictionary_path.exists()
    assert result.session_metadata_path and result.session_metadata_path.exists()
    assert result.analysis_outputs["responses"].exists()
    assert result.analysis_outputs["analysis_ready_trials"].exists()
    assert result.analysis_outputs["timing_qc"].exists()
    assert result.analysis_outputs["lsl_markers"].exists()
    assert result.analysis_outputs["lsl_markers_xdf"].exists()
    assert result.analysis_outputs["trigger_dictionary"].exists()
    events_text = result.events_csv.read_text(encoding="utf-8")
    assert "session_start" in events_text
    assert "audio_sample_zero" in events_text
    assert "tactile_onset" in events_text
    assert "response_marker_start" in events_text
    local_metadata = json.loads(result.session_metadata_path.read_text(encoding="utf-8"))
    assert local_metadata["participant"]["name"] == "Alice Example"
    assert local_metadata["participant"]["participant_pseudonym"].startswith("PPS-")
    with result.lsl_markers_csv.open(newline="", encoding="utf-8") as handle:
        marker_rows = list(csv.DictReader(handle))
    session_start_payload = json.loads(next(row for row in marker_rows if row["event_type"] == "session_start")["payload_json"])
    assert "Alice Example" not in json.dumps(session_start_payload)
    assert session_start_payload["session_metadata"]["participant"]["name_redacted_for_lsl"] is True
    assert session_start_payload["session_metadata"]["participant"]["lsl_identity"].startswith("PPS-")

    qc_text = result.analysis_outputs["timing_qc"].read_text(encoding="utf-8")
    assert "marker_minus_mouse_ms" in qc_text
    assert "0.05" in events_text
    assert result.recording_paths


def test_session_runner_emits_tactile_timeline_schedule_progress(tmp_path: Path):
    run_manifest = _segment_run_setup_fixture(tmp_path)
    package = prepare_segment_run_package(
        run_manifest,
        "P001",
        session_root=tmp_path / "sessions",
        created_at=datetime(2026, 1, 2, 3, 4, 5),
    )
    engine = _MockAudioEngine()
    controller = SessionRunnerController(package, audio_engine=engine)
    progress: list[dict[str, object]] = []

    result = controller.run(progress_callback=progress.append)

    assert result.completed
    schedule_payloads = [payload for payload in progress if payload.get("ui_event") == "block_schedule"]
    assert len(schedule_payloads) == 1
    schedule = schedule_payloads[0]
    assert schedule["part_number"] == 1
    assert schedule["block_index"] == 1
    assert schedule["display_block_index"] == 1
    assert schedule["display_block_count"] == 1
    tactile_events = schedule["tactile_events"]
    assert len(tactile_events) == 1
    assert tactile_events[0]["trial_number"] == 1
    assert tactile_events[0]["family"] == "audio_tactile"
    assert tactile_events[0]["soa_ms"] == "10"
    assert tactile_events[0]["row_label"] == "Inhale"
    assert tactile_events[0]["trial_label"] == "Inhale"
    assert tactile_events[0]["clip_label"]
    trial_segments = schedule["trial_segments"]
    assert len(trial_segments) >= 1
    assert trial_segments[0]["trial_number"] == 1
    assert trial_segments[0]["trial_label"] == "Inhale"
    assert trial_segments[0]["start_s"] < trial_segments[0]["end_s"]


def test_session_runner_logs_instruction_events_without_trial_response(tmp_path: Path):
    design = _compact_design()
    package = prepare_run_package(
        design,
        "P001",
        render_dir=_render_dir(tmp_path),
        session_root=tmp_path / "sessions",
        created_at=datetime(2026, 1, 2, 3, 4, 5),
    )
    instruction = tmp_path / "before_experiment.wav"
    sf.write(instruction, np.zeros((441, 1), dtype=np.float32), 44100)
    package = replace(
        package,
        instruction_profile={
            "schema": "pps-run-instructions.v1",
            "slots": [
                {
                    "slot": "before_experiment",
                    "label": "General instructions",
                    "enabled": True,
                    "path": str(instruction),
                    "duration_s": 0.01,
                    "sample_rate": 44100,
                    "channels": 1,
                    "continue_mode": "click",
                    "button_label": "Start experiment",
                }
            ],
        },
    )
    engine = _MockAudioEngine()
    holder = {}

    def _continue_with_target_click(_context):
        holder["controller"].log_click(x=10, y=12)
        return False

    controller = SessionRunnerController(
        package,
        audio_engine=engine,
        instruction_continue_callback=_continue_with_target_click,
    )
    holder["controller"] = controller

    result = controller.run()

    assert result.completed
    assert engine.played[0] == f"instruction:{instruction}"
    events = list(csv.DictReader(result.events_csv.open(encoding="utf-8")))
    event_types = [row["event_type"] for row in events]
    assert "instruction_start" in event_types
    assert "instruction_end" in event_types
    assert "instruction_continue" in event_types
    assert "mouse_click" not in event_types
    assert "response_marker_start" not in event_types


def test_session_runner_instruction_playback_failure_is_non_blocking(tmp_path: Path):
    design = _compact_design()
    package = prepare_run_package(
        design,
        "P001",
        render_dir=_render_dir(tmp_path),
        session_root=tmp_path / "sessions",
        created_at=datetime(2026, 1, 2, 3, 4, 5),
    )
    instruction = tmp_path / "before_experiment.wav"
    sf.write(instruction, np.zeros((441, 1), dtype=np.float32), 44100)
    package = replace(
        package,
        instruction_profile={
            "schema": "pps-run-instructions.v1",
            "slots": [
                {
                    "slot": "before_experiment",
                    "label": "Optional broken instruction",
                    "enabled": True,
                    "required": False,
                    "path": str(instruction),
                    "duration_s": 0.01,
                    "sample_rate": 44100,
                    "channels": 1,
                    "continue_mode": "delay",
                    "delay_s": 0.0,
                }
            ],
        },
    )

    class FailingInstructionEngine(_MockAudioEngine):
        def play_instruction(self, path: str, on_complete=None) -> bool:
            self.played.append(f"instruction:{path}")
            if on_complete:
                on_complete(False)
            return False

    controller = SessionRunnerController(package, audio_engine=FailingInstructionEngine())

    result = controller.run()

    assert result.completed
    events = list(csv.DictReader(result.events_csv.open(encoding="utf-8")))
    event_types = [row["event_type"] for row in events]
    assert "instruction_error" in event_types
    assert "block_start" in event_types
