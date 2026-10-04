"""Planner JSON inventory acceptance against the existing Python owner."""
from __future__ import annotations

import csv
import json
import os
import struct
import subprocess
import wave
from pathlib import Path

from peripersonal_space_toolkit.design import default_design
from peripersonal_space_toolkit.designer_segments.registry import manifest_sha256
from peripersonal_space_toolkit.experiment_profile import (
    create_experiment_profile,
    experiment_profile_bytes,
    read_experiment_profile,
)


ROOT = Path(__file__).resolve().parents[3]


def _profile(folder: Path) -> Path:
    folder.mkdir(parents=True)
    audio = folder / "ingredient.wav"
    with wave.open(str(audio), "wb") as output:
        output.setparams((2, 2, 48_000, 0, "NONE", "not compressed"))
        output.writeframes(b"\0" * 1920)
    block = folder / "block.csv"
    with block.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=["trial_file_path"])
        writer.writeheader()
        writer.writerow({"trial_file_path": str(audio)})
    order = folder / "order.csv"
    with order.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=["block_csv_path", "block_label"])
        writer.writeheader()
        writer.writerow({"block_csv_path": str(block), "block_label": "First"})
    accepted = folder / "accepted.json"
    accepted.write_text('{"accepted": true}', encoding="utf-8")
    setup = folder / "setup.json"
    setup.write_text(json.dumps({
        "schema": "pps-experiment-run-setup.v1", "prepared": True,
        "source_segment5_manifest": str(accepted),
        "source_segment5_manifest_sha256": manifest_sha256(accepted),
        "csv_path": str(order),
    }), encoding="utf-8")
    profile = folder / "experiment.json"
    profile.write_bytes(experiment_profile_bytes(
        create_experiment_profile(default_design(), setup, source_revision=7)
    ))
    return profile


def _python_accepts(path: Path) -> bool:
    try:
        read_experiment_profile(path)
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return True


def _participant_profile(folder: Path) -> Path:
    profile_path = _profile(folder)
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    setup_path = Path(profile["run_setup_path"])
    setup = json.loads(setup_path.read_text(encoding="utf-8"))
    order_path = Path(setup["csv_path"])
    first_block = folder / "block.csv"
    second_block = folder / "second.csv"
    with second_block.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=["trial_file_path", "block_trial_index"])
        writer.writeheader()
        writer.writerows([
            {"trial_file_path": str(folder / "ingredient.wav"), "block_trial_index": 2},
            {"trial_file_path": str(folder / "ingredient.wav"), "block_trial_index": 1},
        ])
    with order_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=[
            "participant_id", "phase_index", "participant_block_position", "block_csv_path", "block_label",
        ])
        writer.writeheader()
        writer.writerows([
            {"participant_id": "P002", "phase_index": 1, "participant_block_position": 1,
             "block_csv_path": str(first_block), "block_label": "Other"},
            {"participant_id": "P001", "phase_index": 1, "participant_block_position": 2,
             "block_csv_path": str(second_block), "block_label": "Second"},
            {"participant_id": "P001", "phase_index": 1, "participant_block_position": 1,
             "block_csv_path": str(first_block), "block_label": "First"},
        ])
    setup["total_block_runs"] = 3
    setup_path.write_text(json.dumps(setup), encoding="utf-8")
    profile_path.write_bytes(experiment_profile_bytes(
        create_experiment_profile(default_design(), setup_path, source_revision=9)
    ))
    return profile_path


def test_rust_profile_inventory_matches_python_for_export_and_stale_sources(tmp_path: Path) -> None:
    valid = _profile(tmp_path / "valid")
    bom = valid.with_name("experiment-bom.json")
    bom.write_bytes(b"\xef\xbb\xbf" + valid.read_bytes())
    changed = _profile(tmp_path / "changed")
    (changed.parent / "ingredient.wav").write_bytes(b"changed")
    absent = _profile(tmp_path / "absent")
    (absent.parent / "ingredient.wav").unlink()
    stale_hash = _profile(tmp_path / "stale-hash")
    value = json.loads(stale_hash.read_text(encoding="utf-8"))
    value["files"][-1]["sha256"] = "0" * 64
    stale_hash.write_text(json.dumps(value), encoding="utf-8")
    missing_setup = _profile(tmp_path / "missing-setup")
    value = json.loads(missing_setup.read_text(encoding="utf-8"))
    value["files"] = [item for item in value["files"] if item["path"] != value["run_setup_path"]]
    missing_setup.write_text(json.dumps(value), encoding="utf-8")
    duplicate = valid.with_name("experiment-duplicate.json")
    value = json.loads(valid.read_text(encoding="utf-8"))
    value["files"].append(value["files"][0])
    duplicate.write_text(json.dumps(value), encoding="utf-8")
    wrong_schema = valid.with_name("experiment-wrong-schema.json")
    value = json.loads(valid.read_text(encoding="utf-8"))
    value["schema"] = "pps-experiment-profile.v999"
    wrong_schema.write_text(json.dumps(value), encoding="utf-8")
    paths = [valid, bom, changed, absent, stale_hash, missing_setup, duplicate, wrong_schema]
    completed = subprocess.run(
        ["cargo", "run", "--quiet", "--locked", "-p", "pps-session-package", "--example", "experiment_profile_probe"],
        cwd=ROOT, input=json.dumps({"paths": [str(path) for path in paths]}),
        text=True, capture_output=True, check=True,
    )
    rust = json.loads(completed.stdout)
    assert [row["accepted"] for row in rust] == [_python_accepts(path) for path in paths]
    assert [row["accepted"] for row in rust] == [True, True, False, False, False, False, False, False]
    assert rust[0]["ingredient_count"] == 5
    assert rust[5]["code"] == "profile_run_setup_missing"
    assert rust[6]["code"] == "profile_ingredient_invalid"
    assert rust[7]["code"] == "profile_schema_unsupported"


def test_rust_selects_existing_participant_block_order_and_rejects_profile_divergence(tmp_path: Path) -> None:
    valid = _participant_profile(tmp_path / "valid")
    tampered = valid.with_name("experiment-tampered.json")
    value = json.loads(valid.read_text(encoding="utf-8"))
    value["assembly"]["blocks"][0]["rows"][0]["trial_file_path"] = "different.wav"
    tampered.write_text(json.dumps(value), encoding="utf-8")
    unlisted = valid.with_name("experiment-unlisted.json")
    value = json.loads(valid.read_text(encoding="utf-8"))
    value["files"] = [item for item in value["files"] if Path(item["path"]).name != "ingredient.wav"]
    unlisted.write_text(json.dumps(value), encoding="utf-8")
    count_mismatch = _participant_profile(tmp_path / "count-mismatch")
    count_setup_path = Path(json.loads(count_mismatch.read_text(encoding="utf-8"))["run_setup_path"])
    count_setup = json.loads(count_setup_path.read_text(encoding="utf-8"))
    count_setup["total_block_runs"] = 99
    count_setup_path.write_text(json.dumps(count_setup), encoding="utf-8")
    count_mismatch.write_bytes(experiment_profile_bytes(
        create_experiment_profile(default_design(), count_setup_path, source_revision=10)
    ))
    cases = [
        {"profile_path": str(valid), "participant_id": "P001"},
        {"profile_path": str(valid), "participant_id": "P002"},
        {"profile_path": str(valid), "participant_id": "P999"},
        {"profile_path": str(tampered), "participant_id": "P001"},
        {"profile_path": str(unlisted), "participant_id": "P001"},
        {"profile_path": str(count_mismatch), "participant_id": "P001"},
    ]
    completed = subprocess.run(
        ["cargo", "run", "--quiet", "--locked", "-p", "pps-session-package", "--example", "experiment_plan_probe"],
        cwd=ROOT, input=json.dumps({"cases": cases}),
        text=True, capture_output=True, check=True,
    )
    rust = json.loads(completed.stdout)
    assert rust[:3] == [
        {"accepted": True, "code": "selected", "block_labels": ["First", "Second"],
         "trial_counts": [1, 2], "trial_orders": [[""], ["1", "2"]]},
        {"accepted": True, "code": "selected", "block_labels": ["Other"],
         "trial_counts": [1], "trial_orders": [[""]]},
        {"accepted": False, "code": "profile_participant_missing", "block_labels": [],
         "trial_counts": [], "trial_orders": []},
    ]
    assert [row["code"] for row in rust[3:]] == [
        "profile_plan_invalid", "profile_plan_ingredient_not_listed", "profile_plan_invalid",
    ]


def test_rust_binds_exported_trial_wav_to_exact_bytes_and_audio_hint(tmp_path: Path) -> None:
    valid = _participant_profile(tmp_path / "valid-media")
    wrong_row = _participant_profile(tmp_path / "wrong-row")
    block_path = wrong_row.parent / "block.csv"
    with block_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=["trial_file_path", "source_sha256"])
        writer.writeheader()
        writer.writerow({"trial_file_path": str(wrong_row.parent / "ingredient.wav"), "source_sha256": "0" * 64})
    setup_path = Path(json.loads(wrong_row.read_text(encoding="utf-8"))["run_setup_path"])
    wrong_row.write_bytes(experiment_profile_bytes(
        create_experiment_profile(default_design(), setup_path, source_revision=11)
    ))
    bad_hint = valid.with_name("experiment-bad-hint.json")
    value = json.loads(valid.read_text(encoding="utf-8"))
    audio = next(item for item in value["files"] if Path(item["path"]).name == "ingredient.wav")
    audio["audio"]["frames"] += 1
    bad_hint.write_bytes(experiment_profile_bytes(value))
    cases = [
        {"profile_path": str(valid), "participant_id": "P001"},
        {"profile_path": str(wrong_row), "participant_id": "P001"},
        {"profile_path": str(bad_hint), "participant_id": "P001"},
    ]
    completed = subprocess.run(
        ["cargo", "run", "--quiet", "--locked", "-p", "pps-experiment-media", "--example", "profile_media_probe"],
        cwd=ROOT, input=json.dumps({"cases": cases}),
        text=True, capture_output=True, check=True,
    )
    assert json.loads(completed.stdout) == [
        {"accepted": True, "code": "media_bound", "frames": [480], "sample_rates": [48000], "channels": [2]},
        {"accepted": False, "code": "profile_audio_row_digest_mismatch", "frames": [], "sample_rates": [], "channels": []},
        {"accepted": False, "code": "profile_audio_hint_mismatch", "frames": [], "sample_rates": [], "channels": []},
    ]


def _standard_block_profile(folder: Path, *, tactile_shape: str = "") -> Path:
    folder.mkdir(parents=True)
    target = folder / "baseline_frontal_40ms_loom.wav"
    catch = folder / "catch.wav"
    with wave.open(str(target), "wb") as output:
        output.setparams((3, 2, 44_100, 0, "NONE", "not compressed"))
        output.writeframes(b"".join(
            struct.pack("<hhh", 1000, 2000, 16000 if 2205 <= frame < 2210 else 0)
            for frame in range(4000)
        ))
    with wave.open(str(catch), "wb") as output:
        output.setparams((2, 2, 44_100, 0, "NONE", "not compressed"))
        output.writeframes(struct.pack("<hh", 3000, 4000) * 1000)
    block = folder / "block.csv"
    with block.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=[
            "block_trial_index", "family", "trial_file_path", "source_sha256",
            "looming_segment_onset_s", "tactile_onset_s", "soa_ms", "iti_ms",
            "tactile_waveform_shape", "tactile_frequency_hz", "tactile_duration_ms",
        ])
        writer.writeheader()
        writer.writerow({
            "block_trial_index": 1, "family": "audio_tactile", "trial_file_path": str(target),
            "source_sha256": manifest_sha256(target), "looming_segment_onset_s": "",
            "tactile_onset_s": "", "soa_ms": 10, "iti_ms": 10,
            "tactile_waveform_shape": tactile_shape,
            "tactile_frequency_hz": 100 if tactile_shape else "",
            "tactile_duration_ms": 10 if tactile_shape else "",
        })
        writer.writerow({
            "block_trial_index": 2, "family": "catch", "trial_file_path": str(catch),
            "source_sha256": manifest_sha256(catch), "looming_segment_onset_s": 0,
            "tactile_onset_s": "", "soa_ms": 0, "iti_ms": 0,
        })
    order = folder / "order.csv"
    with order.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=["participant_id", "block_csv_path", "block_label"])
        writer.writeheader()
        writer.writerow({"participant_id": "P001", "block_csv_path": str(block), "block_label": "First"})
    accepted = folder / "accepted.json"
    accepted.write_text('{"accepted": true}', encoding="utf-8")
    setup = folder / "setup.json"
    setup.write_text(json.dumps({
        "schema": "pps-experiment-run-setup.v1", "prepared": True,
        "source_segment5_manifest": str(accepted),
        "source_segment5_manifest_sha256": manifest_sha256(accepted),
        "csv_path": str(order), "total_block_runs": 1,
    }), encoding="utf-8")
    profile = folder / "experiment.json"
    profile.write_bytes(experiment_profile_bytes(create_experiment_profile(default_design(), setup, source_revision=12)))
    return profile


def test_standard_native_block_pcm_matches_compatibility_assembly(tmp_path: Path, monkeypatch) -> None:
    from peripersonal_space_toolkit.session_runner import _materialize_segment_block_wav

    monkeypatch.setenv("PPS_WOOJER_TACTILE_COMPENSATION_MS", "23")
    profile_path = _standard_block_profile(tmp_path / "standard")
    profile = read_experiment_profile(profile_path)
    source_block = profile["assembly"]["blocks"][0]
    python_wav = profile_path.parent / "python-block.wav"
    _materialize_segment_block_wav(
        python_wav, source_block["rows"], participant_id="P001", session_id="P001_fixture",
        part_number=1, phase="single", phase_label="Single", output_block_index=1,
        participant_block_position=1, source_block_index=1, source_block_label="First",
        source_block_csv_path=Path(source_block["source_csv_path"]),
    )
    native_wav = profile_path.parent / "native-block.wav"
    completed = subprocess.run(
        ["cargo", "run", "--quiet", "--locked", "-p", "pps-experiment-media", "--example", "profile_block_probe"],
        cwd=ROOT, input=json.dumps({
            "profile_path": str(profile_path), "participant_id": "P001", "output_path": str(native_wav),
        }), env=os.environ.copy(), text=True, capture_output=True, check=True,
    )
    assert json.loads(completed.stdout) == {
        "accepted": True, "code": "block_assembled", "frames": 5441,
        "sample_rate_hz": 44100, "channels": 3, "spans": [[0, 4441], [4441, 5441]],
    }
    with wave.open(str(python_wav), "rb") as output:
        python_pcm = output.readframes(output.getnframes())
        assert (output.getnframes(), output.getnchannels(), output.getframerate()) == (5441, 3, 44100)
    with wave.open(str(native_wav), "rb") as output:
        native_pcm = output.readframes(output.getnframes())
        assert (output.getnframes(), output.getnchannels(), output.getframerate()) == (5441, 3, 44100)
    assert native_pcm == python_pcm


def test_standard_native_block_rejects_unimplemented_tactile_transform(tmp_path: Path) -> None:
    profile_path = _standard_block_profile(tmp_path / "transform", tactile_shape="sine")
    native_wav = profile_path.parent / "unsupported-block.wav"
    completed = subprocess.run(
        ["cargo", "run", "--quiet", "--locked", "-p", "pps-experiment-media", "--example", "profile_block_probe"],
        cwd=ROOT, input=json.dumps({
            "profile_path": str(profile_path), "participant_id": "P001", "output_path": str(native_wav),
        }), text=True, capture_output=True, check=True,
    )
    assert json.loads(completed.stdout)["code"] == "profile_block_transform_unsupported"
    assert not native_wav.exists()


def test_standard_native_package_matches_v1_trial_schedule_rows(tmp_path: Path, monkeypatch) -> None:
    from peripersonal_space_toolkit.session_runner import _materialize_segment_block_wav

    monkeypatch.setenv("PPS_WOOJER_TACTILE_COMPENSATION_MS", "23")
    profile_path = _standard_block_profile(tmp_path / "package-source")
    source_block = read_experiment_profile(profile_path)["assembly"]["blocks"][0]
    python_wav = tmp_path / "python-package-block.wav"
    _, _, _, python_rows, _ = _materialize_segment_block_wav(
        python_wav, source_block["rows"], participant_id="P001", session_id="P001_fixture",
        part_number=1, phase="single", phase_label="Single", output_block_index=1,
        participant_block_position=1, source_block_index=1, source_block_label="First",
        source_block_csv_path=Path(source_block["source_csv_path"]),
    )
    native_dir = tmp_path / "P001_fixture"
    completed = subprocess.run(
        ["cargo", "run", "--quiet", "--locked", "-p", "pps-experiment-media", "--example", "profile_package_probe"],
        cwd=ROOT, input=json.dumps({
            "profile_path": str(profile_path), "participant_id": "P001", "output_dir": str(native_dir),
        }), env={**os.environ, "CARGO_INCREMENTAL": "0"}, text=True, capture_output=True, check=True,
    )
    assert json.loads(completed.stdout) == {
        "accepted": True, "code": "package_prepared", "block_count": 1, "trial_counts": [2],
    }
    with (native_dir / "blocks" / "Block_01.csv").open(newline="", encoding="utf-8") as source:
        native_rows = list(csv.DictReader(source))
    assert len(native_rows) == len(python_rows) == 2
    compared = (
        "Trial_UID", "Trial_Type", "Family", "SOA_ms", "Source_SHA256", "Trial_File_Path",
        "Source_Block_CSV_SHA256", "Duration_ms", "Trial_Duration_S", "Sample_Rate_Hz", "Channels",
        "Trial_Start_Sample", "Looming_Onset_Sample", "Tactile_Onset_Sample",
        "Tactile_Drive_Onset_Sample", "Response_Window_Onset_Sample", "Trial_End_Sample",
        "Tactile_Latency_Compensation_Requested_ms", "Tactile_Latency_Compensation_Applied_ms",
        "Tactile_Latency_Compensation_Status", "Tactile_Latency_Compensation_Applied",
        "Tactile_Latency_Compensation_Note",
    )
    for native, expected in zip(native_rows, python_rows):
        assert {key: native[key] for key in compared} == {key: str(expected[key]) for key in compared}
        assert Path(native["Source_Block_CSV_Path"]).samefile(expected["Source_Block_CSV_Path"])
        assert {
            key: native.get(key, "") for key, value in expected.items()
            if value not in ("", None) and key != "Source_Block_CSV_Path"
        } == {
            key: str(value) for key, value in expected.items()
            if value not in ("", None) and key != "Source_Block_CSV_Path"
        }
    manifest = json.loads((native_dir / "session_manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "pps-run-session.v1"
    assert manifest["execution_mode"] == "participant_block_wavs"
    assert manifest["source_run_setup_sha256"] == manifest_sha256(profile_path.parent / "setup.json")
    with wave.open(str(python_wav), "rb") as output:
        python_pcm = output.readframes(output.getnframes())
    with wave.open(str(native_dir / "blocks" / "Block_01.wav"), "rb") as output:
        assert output.readframes(output.getnframes()) == python_pcm


def test_standard_native_package_keeps_approved_multiple_block_order(tmp_path: Path) -> None:
    profile_path = _participant_profile(tmp_path / "source")
    output_dir = tmp_path / "P001_ordered"
    completed = subprocess.run(
        ["cargo", "run", "--quiet", "--locked", "-p", "pps-experiment-media", "--example", "profile_package_probe"],
        cwd=ROOT, input=json.dumps({
            "profile_path": str(profile_path), "participant_id": "P001", "output_dir": str(output_dir),
        }), env={**os.environ, "CARGO_INCREMENTAL": "0"}, text=True, capture_output=True, check=True,
    )
    assert json.loads(completed.stdout) == {
        "accepted": True, "code": "package_prepared", "block_count": 2, "trial_counts": [1, 2],
    }
    manifest = json.loads((output_dir / "session_manifest.json").read_text(encoding="utf-8"))
    assert [block["label"] for block in manifest["blocks"]] == ["First", "Second"]
    with (output_dir / "blocks" / "Block_02.csv").open(newline="", encoding="utf-8") as source:
        assert [row["block_trial_index"] for row in csv.DictReader(source)] == ["1", "2"]
