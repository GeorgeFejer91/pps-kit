from __future__ import annotations

import csv
import json
import os
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from peripersonal_space_toolkit import session_runner as session_runner_module
from peripersonal_space_toolkit import labrecorder_capture as labrecorder_capture_module
from peripersonal_space_toolkit.design import ProtocolSpec, default_design
from peripersonal_space_toolkit.session_runner import (
    ParticipantTrialCsvWriter,
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
from peripersonal_space_toolkit.runner_diary import find_output_diary, read_diary_entries
from peripersonal_space_toolkit.output_layout import (
    output_data_analytics_dir,
    output_prepared_blocks_dir,
    output_runner_logs_dir,
    output_shared_instructions_dir,
    output_verbose_events_dir,
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
    assert package.manifest_path.parent == output_runner_logs_dir(tmp_path / "sessions") / package.session_id
    assert package.design_path.parent == package.manifest_path.parent
    assert len(package.blocks) == 1
    assert package.blocks[0].manifest_path.exists()
    assert package.blocks[0].wav_path.exists()
    assert package.blocks[0].manifest_path.parent == output_prepared_blocks_dir(tmp_path / "sessions") / package.session_id / "blocks"
    assert not (package.session_dir / "blocks").exists()

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
    assert package.manifest_path.parent == output_runner_logs_dir(tmp_path / "sessions") / package.session_id
    assert len(package.blocks) == 1
    assert package.blocks[0].metadata["source_block_index"] == 1
    assert package.blocks[0].manifest_path.parent == output_prepared_blocks_dir(tmp_path / "sessions") / package.session_id / "blocks"

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
    assert manifest["source_run_setup_sha256"] == _sha256(run_manifest)


def test_prepare_segment_run_package_creates_prepared_blocks_under_deep_output_root(tmp_path: Path):
    run_manifest = _segment_run_setup_fixture(tmp_path)
    session_root = tmp_path / ("deep_validation_output_" + "x" * 40) / ("materialized_profile_" + "y" * 40) / ("sessions_" + "z" * 40)
    session_runner_module._mkdir(session_root)

    package = prepare_segment_run_package(
        run_manifest,
        "P001",
        session_root=session_root,
        created_at=datetime(2026, 1, 2, 3, 4, 5),
    )

    assert session_runner_module._path_exists(package.manifest_path)
    assert session_runner_module._path_exists(package.blocks[0].manifest_path)
    assert session_runner_module._path_exists(package.blocks[0].wav_path)
    assert package.blocks[0].manifest_path.parent == output_prepared_blocks_dir(session_root) / package.session_id / "blocks"


def test_prepare_segment_run_package_advances_woojer_tactile_drive_in_block_wav(tmp_path: Path):
    run_manifest = _segment_run_setup_fixture(tmp_path)
    block_csv = run_manifest.parent.parent / "5_block_csv_preview" / "block_01_final.csv"
    sample_rate = 44100
    nominal_onset_s = 0.100
    cue_duration_s = 0.100
    target = tmp_path / "target_100ms_tactile.wav"
    target_audio = np.zeros((int(round(0.250 * sample_rate)), 3), dtype=np.float32)
    target_audio[:, 0] = 0.05
    target_audio[:, 1] = 0.02
    cue_start = int(round(nominal_onset_s * sample_rate))
    cue_end = cue_start + int(round(cue_duration_s * sample_rate))
    target_audio[cue_start:cue_end, 2] = 0.25
    sf.write(target, target_audio, sample_rate)

    with block_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])
    rows[0].update(
        {
            "soa_ms": "100",
            "source_file_name": target.name,
            "trial_file_path": str(target),
            "source_sha256": _sha256(target),
            "duration_ms": "250",
            "duration_s": "0.25",
            "looming_segment_onset_s": "0.000",
            "tactile_onset_s": f"{nominal_onset_s:.3f}",
        }
    )
    with block_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    package = prepare_segment_run_package(
        run_manifest,
        "P001",
        session_root=tmp_path / "sessions",
        created_at=datetime(2026, 1, 2, 3, 4, 5),
        use_block_cache=False,
    )

    block_audio, rate = sf.read(package.blocks[0].wav_path, always_2d=True)
    assert rate == sample_rate
    tactile_active = np.flatnonzero(np.abs(block_audio[:, 2]) > 0.05)
    assert tactile_active.size > 0
    assert tactile_active[0] == pytest.approx(int(round(0.077 * sample_rate)), abs=1)

    with package.blocks[0].manifest_path.open(newline="", encoding="utf-8") as handle:
        prepared_rows = list(csv.DictReader(handle))
    prepared = prepared_rows[0]
    assert float(prepared["Tactile_Onset_S"]) == pytest.approx(0.100)
    assert int(prepared["Tactile_Onset_Sample"]) == int(round(0.100 * sample_rate))
    assert float(prepared["Tactile_Drive_Onset_S"]) == pytest.approx(0.077, abs=1 / sample_rate)
    assert int(prepared["Tactile_Drive_Onset_Sample"]) == pytest.approx(int(round(0.077 * sample_rate)), abs=1)
    assert float(prepared["Tactile_Latency_Compensation_Requested_ms"]) == pytest.approx(23.0)
    assert float(prepared["Tactile_Latency_Compensation_Applied_ms"]) == pytest.approx(23.0, abs=0.03)
    assert prepared["Tactile_Latency_Compensation_Status"] == "provisional_woojer_audio_path_not_mechanical_onset"

    manifest = json.loads(package.manifest_path.read_text(encoding="utf-8"))
    policy = manifest["timing"]["tactile_latency_compensation"]
    assert policy["compensation_ms"] == pytest.approx(23.0)
    assert policy["example_compensated_drive_onset_ms"] == pytest.approx(77.0)


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

    other_root = tmp_path / "other_sessions"
    assert claim_prepared_session(run_manifest, "P002", state_root=state_root, session_root=other_root) is None
    assert (
        claim_prepared_session(run_manifest, "P002", state_root=state_root, session_root=tmp_path / "sessions")
        == package.manifest_path.resolve()
    )
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

    other_root = tmp_path / "other_sessions"
    other_root.mkdir()
    different_output = prepared_session_asset_status(
        run_manifest,
        "P001",
        state_root=state_root,
        session_root=other_root,
    )

    assert different_output["generated"] is False
    assert different_output["status"] == "not_generated"
    assert "different output folder" in different_output["message"]

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


def test_prepared_session_status_rejects_stale_source_block_csv(tmp_path: Path):
    run_manifest = _segment_run_setup_fixture(tmp_path)
    session_root = tmp_path / "sessions"
    state_root = tmp_path / "state"
    package = prepare_segment_run_package(
        run_manifest,
        "P001",
        session_root=session_root,
        created_at=datetime(2026, 1, 2, 3, 4, 5),
    )
    record_prepared_session_queue(
        participant_id="P001",
        run_setup_manifest_path=run_manifest,
        session_manifest_path=package.manifest_path,
        status="ready",
        state_root=state_root,
    )

    block_csv = run_manifest.parent.parent / "5_block_csv_preview" / "block_01_final.csv"
    with block_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])
    rows[0]["noise_type"] = "white"
    with block_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    stale_status = prepared_session_asset_status(
        run_manifest,
        "P001",
        state_root=state_root,
        session_root=session_root,
    )

    assert stale_status["generated"] is False
    assert stale_status["status"] == "not_generated"
    assert "source CSV changed" in stale_status["message"]
    assert claim_prepared_session(run_manifest, "P001", state_root=state_root, session_root=session_root) is None
    queue = json.loads((state_root / "prepared_session_queue.v1.json").read_text(encoding="utf-8"))
    assert queue["entries"][-1]["status"] == "stale"
    assert "source CSV changed" in queue["entries"][-1]["message"]


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
    assert copied.parent == output_shared_instructions_dir(tmp_path / "sessions")
    assert copied.exists()
    assert copied.name == "before_experiment.wav"
    assert not (package.session_dir / "instructions").exists()
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


def test_participant_trial_csv_writer_classifies_hit_miss_for_tactile_and_catch(tmp_path: Path):
    package = SimpleNamespace(participant_id="P001", session_id="P001_20260102_030405", session_dir=tmp_path / "P001_20260102_030405")
    writer = ParticipantTrialCsvWriter(
        package.session_dir / f"{package.session_id}_trials.csv",
        package=package,
        participant_metadata={"age_years": "29", "gender": "female", "handedness": "right"},
    )

    def emit_trial(
        *,
        event_id: int,
        block_number: int,
        trial_number: int,
        trial_type: str,
        family: str,
        start_unix: float,
        tactile_unix: float | None = None,
        click_unix: float | None = None,
    ) -> int:
        uid = f"T{trial_number:03d}"
        base = {
            "participant_id": "P001",
            "session_id": package.session_id,
            "block_number": block_number,
            "block_label": "Block 01",
            "trial_number": trial_number,
            "trial_uid": uid,
            "trial_type": trial_type,
            "family": family,
            "row_label": "Inhale",
            "respiratory_phase": "Inhale",
            "soa_ms": "300",
            "noise_type": "pink",
        }
        writer.observe_event({"event_id": event_id, "event_type": "trial_start", "unix_time": start_unix, **base})
        event_id += 1
        if trial_type in {"Audio-Tactile", "Catch"}:
            writer.observe_event({"event_id": event_id, "event_type": "looming_onset", "unix_time": start_unix + 1.0, **base})
            event_id += 1
        if tactile_unix is not None:
            writer.observe_event({"event_id": event_id, "event_type": "tactile_onset", "unix_time": tactile_unix, **base})
            event_id += 1
        writer.observe_event({"event_id": event_id, "event_type": "response_window_onset", "unix_time": start_unix + 1.0, **base})
        event_id += 1
        if click_unix is not None:
            writer.observe_event(
                {
                    "event_id": event_id,
                    "event_type": "mouse_click",
                    "unix_time": click_unix,
                    "block_number": block_number,
                    "in_target": True,
                    "during_playback": True,
                }
            )
            event_id += 1
        writer.observe_event({"event_id": event_id, "event_type": "trial_end", "unix_time": start_unix + 6.0, **base})
        return event_id + 1

    next_event = emit_trial(
        event_id=1,
        block_number=1,
        trial_number=1,
        trial_type="Audio-Tactile",
        family="audio_tactile",
        start_unix=100.0,
        tactile_unix=103.0,
        click_unix=103.25,
    )
    next_event = emit_trial(
        event_id=next_event,
        block_number=1,
        trial_number=2,
        trial_type="Catch",
        family="catch",
        start_unix=200.0,
    )
    next_event = emit_trial(
        event_id=next_event,
        block_number=1,
        trial_number=3,
        trial_type="Catch",
        family="catch",
        start_unix=300.0,
        click_unix=302.0,
    )
    emit_trial(
        event_id=next_event,
        block_number=1,
        trial_number=4,
        trial_type="Baseline",
        family="baseline",
        start_unix=400.0,
        tactile_unix=403.0,
    )

    rows = list(csv.DictReader(writer.path.open(encoding="utf-8")))
    assert [row["outcome"] for row in rows] == ["Hit", "Hit", "Miss", "Miss"]
    assert rows[0]["rt_ms"] == "250.000"
    assert rows[0]["tactile_present"] == "true"
    assert rows[1]["catch_trial"] == "true"
    assert rows[2]["response_given"] == "true"
    assert rows[3]["stimulus_modality"] == "tactile"


class _MockAudioEngine:
    def __init__(self):
        self.played: list[str] = []
        self.stopped = False
        self.paused = False
        self.click_metadata: dict[str, object] = {}
        self.marker_gain = None
        self.recordings: list[str] = []
        self.wired_loopback_mode = "off"
        self.wired_loopback_recordings: list[str] = []
        self.on_audio_started = None
        self.progress_values = [0.0, 0.01]

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
            for value in self.progress_values:
                progress_callback(value)
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

    def set_wired_loopback_mode(self, mode) -> None:
        self.wired_loopback_mode = str(mode)

    def start_recording(self, output_path=None) -> bool:
        self.recordings.append(str(output_path))
        return True

    def stop_recording(self, output_path=None, interrupted=False):
        data = np.zeros((10, 3), dtype=np.float32)
        if output_path:
            sf.write(output_path, data, 44100)
        return data

    def start_wired_loopback_recording(self, output_path=None, mode=None, sample_rate=None) -> bool:
        self.wired_loopback_recordings.append(str(output_path))
        if mode is not None:
            self.wired_loopback_mode = str(mode)
        return True

    def stop_wired_loopback_recording(self, output_path=None, interrupted=False):
        data = np.zeros((10, 4), dtype=np.float32)
        if output_path:
            sf.write(output_path, data, 44100)
        return {"path": str(output_path or ""), "interrupted": bool(interrupted)}


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
    assert engine.played == [session_runner_module._filesystem_path(package.blocks[0].wav_path)]
    assert result.events_csv.exists()
    assert result.events_xdf.exists()
    assert result.lsl_markers_csv and result.lsl_markers_csv.exists()
    assert result.lsl_markers_xdf and result.lsl_markers_xdf.exists()
    assert result.trigger_dictionary_path and result.trigger_dictionary_path.exists()
    assert result.session_metadata_path and result.session_metadata_path.exists()
    assert result.analysis_outputs["responses"].exists()
    assert result.analysis_outputs["analysis_ready_trials"].exists()
    assert result.analysis_outputs["participant_trials"].exists()
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
    assert result.recording_paths[0].parent == package.session_dir
    assert result.recording_paths[0].name == "block_01_audio_evidence.wav"
    assert result.events_csv.parent == output_verbose_events_dir(package.session_dir.parent) / package.session_id
    assert result.lsl_markers_csv and result.lsl_markers_csv.parent == result.events_csv.parent
    assert result.trigger_dictionary_path and result.trigger_dictionary_path.parent == result.events_csv.parent
    assert result.session_metadata_path.parent == output_runner_logs_dir(package.session_dir.parent) / package.session_id
    assert result.analysis_outputs["analysis_ready_trials"].parent == output_data_analytics_dir(package.session_dir.parent) / package.session_id
    manifest_outputs = json.loads(package.manifest_path.read_text(encoding="utf-8"))["outputs"]
    assert Path(manifest_outputs["external_labrecorder_xdf"]) == package.session_dir / f"{package.session_id}_external_labrecorder.xdf"
    participant_trial_rows = list(csv.DictReader(result.analysis_outputs["participant_trials"].open(encoding="utf-8")))
    assert participant_trial_rows
    assert participant_trial_rows[0]["participant_age_years"] == "29"
    assert participant_trial_rows[0]["outcome"] in {"Hit", "Miss"}
    assert not (package.session_dir / "events.csv").exists()
    assert not (package.session_dir / "lsl_markers.csv").exists()
    assert not (package.session_dir / "trigger_dictionary.json").exists()
    assert not (package.session_dir / "session_metadata.json").exists()
    assert not (package.session_dir / "analysis").exists()
    assert sorted(path.name for path in package.session_dir.iterdir()) == [
        f"{package.session_id}_trials.csv",
        "block_01_audio_evidence.wav",
    ]
    diary = find_output_diary(package.session_dir.parent)
    assert diary is not None
    diary_entries = read_diary_entries(diary)
    diary_types = [entry["event_type"] for entry in diary_entries]
    assert "session_package_prepared" in diary_types
    assert "session_start" in diary_types
    assert "mouse_click" in diary_types
    assert "session_completed" in diary_types
    assert "Alice Example" not in diary.read_text(encoding="utf-8")


def test_session_runner_controller_handles_deep_output_root(tmp_path: Path):
    deep_root = tmp_path
    for index in range(8):
        deep_root = deep_root / f"study5_full_acceptance_deep_validation_segment_{index:02d}"
    package = prepare_run_package(
        _compact_design(),
        "P001",
        render_dir=_render_dir(tmp_path),
        session_root=deep_root,
        created_at=datetime(2026, 1, 2, 3, 4, 5),
    )
    engine = _MockAudioEngine()
    controller = SessionRunnerController(
        package,
        audio_engine=engine,
        runner_metadata={"participant_code": "P001"},
    )

    result = controller.run()

    assert result.completed
    assert session_runner_module._path_exists(result.session_metadata_path)
    assert result.session_metadata_path.parent == output_runner_logs_dir(package.session_dir.parent) / package.session_id
    assert session_runner_module._path_exists(result.analysis_outputs["participant_trials"])
    assert session_runner_module._path_exists(result.recording_paths[0])
    if os.name == "nt":
        assert engine.recordings
        assert engine.recordings[0].startswith("\\\\?\\")


def test_session_runner_wired_loopback_proxy_records_per_block_artifact(tmp_path: Path):
    package = prepare_run_package(
        _compact_design(),
        "P001",
        render_dir=_render_dir(tmp_path),
        session_root=tmp_path / "sessions",
        created_at=datetime(2026, 1, 2, 3, 4, 5),
    )
    engine = _MockAudioEngine()
    controller = SessionRunnerController(
        package,
        audio_engine=engine,
        capture_options={"wired_loopback_mode": "output4_tactile_proxy"},
    )

    result = controller.run()

    assert result.completed
    assert engine.wired_loopback_mode == "output4_tactile_proxy"
    expected_loopback_path = package.session_dir / "block_01_wired_loopback_input4.wav"
    assert engine.wired_loopback_recordings == [session_runner_module._filesystem_path(expected_loopback_path)]
    assert sorted(path.name for path in result.recording_paths) == [
        "block_01_audio_evidence.wav",
        "block_01_wired_loopback_input4.wav",
    ]
    assert (package.session_dir / "block_01_wired_loopback_input4.wav").exists()
    events_text = result.events_csv.read_text(encoding="utf-8")
    assert "wired_loopback_start" in events_text
    assert "wired_loopback_end" in events_text
    assert result.capture_options["wired_loopback_mode"] == "output4_tactile_proxy"


def test_session_runner_owned_labrecorder_starts_after_lsl_before_audio(tmp_path: Path, monkeypatch):
    package = prepare_run_package(
        _compact_design(),
        "P001",
        render_dir=_render_dir(tmp_path),
        session_root=tmp_path / "sessions",
        created_at=datetime(2026, 1, 2, 3, 4, 5),
    )
    cli = tmp_path / "LabRecorderCLI.exe"
    cli.write_text("fake", encoding="utf-8")
    order: list[str] = []

    class FakeLabRecorderCapture:
        def __init__(self, *, labrecorder_cli, xdf_path, session_id, stdout_path, stderr_path):
            self.labrecorder_cli = Path(labrecorder_cli)
            self.xdf_path = Path(xdf_path)
            self.session_id = session_id
            self.stdout_path = Path(stdout_path)
            self.stderr_path = Path(stderr_path)
            self.command = [str(self.labrecorder_cli), str(self.xdf_path), f"source_id='pps-markers-v2-{session_id}'"]

        def start(self, *, stream_timeout_s=10.0, startup_s=1.0):
            order.append("labrecorder_start")
            return {
                "enabled": True,
                "started": True,
                "pid": 123,
                "xdf_path": str(self.xdf_path),
                "labrecorder_cli": str(self.labrecorder_cli),
                "command": list(self.command),
                "lsl": {"ready": True, "found_source_ids": [f"pps-markers-v2-{self.session_id}"]},
            }

        def stop(self, *, timeout_s=8.0):
            order.append("labrecorder_stop")
            self.xdf_path.parent.mkdir(parents=True, exist_ok=True)
            self.xdf_path.write_bytes(b"fake xdf")
            self.stdout_path.parent.mkdir(parents=True, exist_ok=True)
            self.stdout_path.write_text("stopped\n", encoding="utf-8")
            self.stderr_path.write_text("", encoding="utf-8")
            return {
                "enabled": True,
                "stopped": True,
                "returncode": 0,
                "stdout_path": str(self.stdout_path),
                "stderr_path": str(self.stderr_path),
                "xdf_path": str(self.xdf_path),
                "command": list(self.command),
            }

    monkeypatch.setattr(session_runner_module, "find_labrecorder_cli", lambda _explicit=None: cli)
    monkeypatch.setattr(session_runner_module, "LabRecorderCapture", FakeLabRecorderCapture)
    monkeypatch.setattr(session_runner_module, "EXTERNAL_LABRECORDER_FINAL_MARKER_SETTLE_S", 0.0)
    engine = _MockAudioEngine()
    engine.on_audio_started = lambda: order.append("audio_playback")
    ui_events: list[str] = []
    controller = SessionRunnerController(
        package,
        audio_engine=engine,
        capture_options={"start_external_labrecorder": True, "external_labrecorder_cli": str(cli)},
    )
    controller.events.lsl = SimpleNamespace(
        status=SimpleNamespace(available=True, enabled=True, message="fake LSL active"),
        local_clock=lambda: 10.0,
        push=lambda event, marker, timestamp: None,
    )

    result = controller.run(event_callback=lambda message: ui_events.append(str(message)))

    assert result.completed
    assert order.index("labrecorder_start") < order.index("audio_playback") < order.index("labrecorder_stop")
    assert ui_events[:2] == ["external_labrecorder_started", "session_start"]
    assert result.analysis_outputs["external_labrecorder_xdf"] == package.session_dir / f"{package.session_id}_external_labrecorder.xdf"
    assert result.analysis_outputs["external_labrecorder_report"].name == "external_labrecorder_capture_report.json"
    assert f"{package.session_id}_external_labrecorder.xdf" in {path.name for path in result.recording_paths}
    events_text = result.events_csv.read_text(encoding="utf-8")
    assert "external_labrecorder_start" in events_text
    assert "external_labrecorder_stop_requested" in events_text
    capture_report = json.loads(result.analysis_outputs["external_labrecorder_report"].read_text(encoding="utf-8"))
    assert capture_report["start"]["started"] is True
    assert capture_report["stop"]["returncode"] == 0
    assert capture_report["stop"]["final_marker_settle_s"] == 0.0


def test_labrecorder_capture_uses_rcs_remote_control(tmp_path: Path, monkeypatch):
    cli = tmp_path / "LabRecorderCLI.exe"
    cli.write_text("fake", encoding="utf-8")
    gui = tmp_path / "LabRecorder.exe"
    gui.write_text("fake", encoding="utf-8")
    (tmp_path / "LabRecorder.cfg").write_text("RCSEnabled=1\nRCSPort=22345\n", encoding="utf-8")
    popen_calls: list[dict[str, object]] = []
    rcs_batches: list[list[str]] = []
    monkeypatch.setenv("QT_PLUGIN_PATH", "C:/wrong/qt/plugins")

    class FakeProcess:
        pid = 456
        returncode = None

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = 1

        def wait(self, timeout=None):
            if self.returncode is None:
                self.returncode = 0
            return self.returncode

        def kill(self):
            self.returncode = -9

    def fake_popen(args, **kwargs):
        popen_calls.append({"args": args, **kwargs})
        stdout = kwargs.get("stdout")
        if hasattr(stdout, "write"):
            stdout.write("labrecorder stdout")
            stdout.flush()
        return FakeProcess()

    monkeypatch.setattr(
        labrecorder_capture_module,
        "wait_for_runner_lsl_streams",
        lambda _session_id, timeout_s=10.0: {"ready": True, "found_source_ids": ["pps-markers-v2-P001_session"]},
    )
    monkeypatch.setattr(labrecorder_capture_module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        labrecorder_capture_module.LabRecorderCapture,
        "_wait_for_rcs",
        lambda self, timeout_s=10.0: {"ready": True, "port": 22345, "error": ""},
    )
    monkeypatch.setattr(
        labrecorder_capture_module.LabRecorderCapture,
        "_send_rcs_commands",
        lambda self, commands: rcs_batches.append(list(commands)),
    )
    monkeypatch.setattr(labrecorder_capture_module, "_wait_for_labrecorder_collection_started", lambda path, timeout_s=8.0: True)
    monkeypatch.setattr(
        labrecorder_capture_module,
        "_wait_for_file_quiet",
        lambda path, timeout_s=8.0: path.write_bytes(b"fake xdf") or True,
    )
    monkeypatch.setattr(labrecorder_capture_module, "_wait_for_labrecorder_footer", lambda path, timeout_s=8.0: True)
    monkeypatch.setattr(labrecorder_capture_module, "_close_labrecorder_windows", lambda pid: True)

    capture = labrecorder_capture_module.LabRecorderCapture(
        labrecorder_cli=cli,
        xdf_path=tmp_path / "session_external_labrecorder.xdf",
        session_id="P001_session",
        stdout_path=tmp_path / "external_labrecorder_stdout.txt",
        stderr_path=tmp_path / "external_labrecorder_stderr.txt",
    )

    started = capture.start(startup_s=0.0)
    stopped = capture.stop(timeout_s=1.0)

    assert started["started"] is True
    assert started["collection_started"] is True
    assert rcs_batches[0] == [
        "update",
        "select all",
        f"filename {{root:{str(tmp_path.resolve()).replace(chr(92), '/')}/}} {{template:session_external_labrecorder.xdf}}",
        "start",
    ]
    assert rcs_batches[1] == ["stop"]
    assert stopped["returncode"] == 0
    assert stopped["footer_observed"] is True
    assert stopped["graceful_close_sent"] is True
    assert capture.stdout_path.read_text(encoding="utf-8") == "labrecorder stdout"
    assert popen_calls[0]["args"][0] == str(gui.resolve())
    assert popen_calls[0]["cwd"] == str(cli.parent)
    assert popen_calls[0]["stdout"] is not labrecorder_capture_module.subprocess.PIPE
    assert "startupinfo" in popen_calls[0]
    child_env = popen_calls[0]["env"]
    assert isinstance(child_env, dict)
    assert child_env["PATH"].split(os.pathsep)[0] == str(tmp_path.resolve())
    assert "QT_PLUGIN_PATH" not in child_env


def test_session_runner_owned_labrecorder_requires_lsl(tmp_path: Path):
    package = prepare_run_package(
        _compact_design(),
        "P001",
        render_dir=_render_dir(tmp_path),
        session_root=tmp_path / "sessions",
        created_at=datetime(2026, 1, 2, 3, 4, 5),
    )

    with pytest.raises(ValueError, match="requires live LSL outlets"):
        SessionRunnerController(
            package,
            audio_engine=_MockAudioEngine(),
            capture_options={"enable_lsl": False, "start_external_labrecorder": True},
        )


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
    assert tactile_events[0]["trial_label"] == "Audio-tactile"
    assert tactile_events[0]["noise_type"] == "pink"
    assert tactile_events[0]["clip_label"]
    trial_segments = schedule["trial_segments"]
    assert len(trial_segments) >= 1
    assert trial_segments[0]["trial_number"] == 1
    assert trial_segments[0]["clip_label"] == "Inhale"
    assert trial_segments[0]["trial_label"] == "Audio-tactile"
    assert trial_segments[0]["noise_type"] == "pink"
    assert trial_segments[0]["start_s"] < trial_segments[0]["end_s"]


def test_session_runner_part2_transition_waits_for_button_without_instruction_slot(tmp_path: Path):
    session_dir = tmp_path / "P001_20260621_120000"
    session_dir.mkdir()
    block_paths: list[Path] = []
    blocks: list[session_runner_module.RunBlock] = []
    for part in (1, 2):
        wav_path = tmp_path / f"block_{part:02d}.wav"
        sf.write(wav_path, np.zeros((441, 3), dtype=np.float32), 44100)
        csv_path = tmp_path / f"block_{part:02d}.csv"
        csv_path.write_text(
            "\n".join(
                [
                    "Trial_Number,Trial_UID,Trial_Type,Family,Row_Label,Noise_Type,SOA_ms,Trial_Start_S,Trial_End_S,Tactile_Onset_S,Sample_Rate_Hz",
                    f"1,P{part}_T001,Audio-Tactile,audio_tactile,Inhale,pink,10,0.0,0.01,0.004,44100",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        block_paths.append(wav_path)
        blocks.append(
            session_runner_module.RunBlock(
                index=part,
                label=f"Block {part:02d}",
                manifest_path=csv_path,
                wav_path=wav_path,
                trial_count=1,
                duration_s=0.01,
                metadata={"part_number": part, "phase": f"part{part}", "phase_label": f"Part {part}", "sample_rate_hz": 44100},
            )
        )

    package = session_runner_module.RunPackage(
        participant_id="P001",
        session_id=session_dir.name,
        created_at="2026-06-21T12:00:00",
        session_dir=session_dir,
        design_path=tmp_path / "design.json",
        protocol_path=tmp_path / "protocol.csv",
        manifest_path=session_dir / "session_manifest.json",
        render_manifest_path=None,
        blocks=blocks,
        instruction_profile={"schema": "pps-run-instructions.v1", "slots": []},
    )
    package.manifest_path.write_text(json.dumps({"schema": "test"}, indent=2), encoding="utf-8")
    contexts: list[dict[str, object]] = []

    def _continue(context: dict[str, object]) -> bool:
        contexts.append(dict(context))
        return True

    engine = _MockAudioEngine()
    controller = SessionRunnerController(
        package,
        audio_engine=engine,
        capture_options={"enable_lsl": False, "write_analysis_csvs": False},
        instruction_continue_callback=_continue,
    )

    result = controller.run()

    assert result.completed
    assert engine.played == [session_runner_module._filesystem_path(path) for path in block_paths]
    assert [context["next_action"] for context in contexts] == ["next_condition"]
    assert contexts[0]["button_label"] == "Start Part 2"
    assert contexts[0]["mode"] == "button"


def test_session_runner_diary_records_interrupted_session(tmp_path: Path):
    design = _compact_design()
    package = prepare_run_package(
        design,
        "P001",
        render_dir=_render_dir(tmp_path),
        session_root=tmp_path / "sessions",
        created_at=datetime(2026, 1, 2, 3, 4, 5),
    )
    engine = _MockAudioEngine()
    engine.stopped = True
    controller = SessionRunnerController(package, audio_engine=engine)

    result = controller.run()

    assert result.completed is False
    assert result.interrupted is True
    diary = find_output_diary(package.session_dir.parent)
    assert diary is not None
    entries = read_diary_entries(diary)
    assert entries[-1]["event_type"] == "session_interrupted"
    assert entries[-1]["payload"]["completed"] is False
    assert entries[-1]["payload"]["interrupted"] is True


def test_session_runner_emits_live_topup_draft_after_response_window(tmp_path: Path):
    run_manifest = _segment_run_setup_fixture(tmp_path)
    package = prepare_segment_run_package(
        run_manifest,
        "P001",
        session_root=tmp_path / "sessions",
        created_at=datetime(2026, 1, 2, 3, 4, 5),
    )
    engine = _MockAudioEngine()
    engine.progress_values = [0.0, 4.0]
    controller = SessionRunnerController(package, audio_engine=engine, enable_topup=True)
    progress: list[dict[str, object]] = []

    result = controller.run(progress_callback=progress.append, event_callback=lambda _message: None)

    assert result.completed
    draft_payloads = [payload for payload in progress if payload.get("ui_event") == "topup_draft"]
    assert draft_payloads
    final_draft = draft_payloads[-1]
    assert final_draft["topup_enabled"] is True
    assert final_draft["missed_trial_count"] == 1
    missed = final_draft["missed_trials"][0]
    assert missed["trial_type"] == "Audio-Tactile"
    assert missed["respiratory_phase"] == "Inhale"


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
    assert engine.played[0] == f"instruction:{session_runner_module._filesystem_path(instruction)}"
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
