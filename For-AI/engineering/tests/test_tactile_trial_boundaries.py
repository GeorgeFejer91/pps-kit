"""Reject missing/truncated cues and verify the reported Canzoneri trial clock."""

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from peripersonal_space_toolkit import dashboard_app
from peripersonal_space_toolkit.dashboard_app import DashboardController


@pytest.mark.parametrize("onset_s", [-0.7, -0.05, 2.95, 3.0, 3.6])
def test_trial_writer_rejects_cues_outside_audio_before_publishing(tmp_path, onset_s):
    source = tmp_path / "source.wav"
    output = tmp_path / "trial.wav"
    sf.write(source, np.zeros((132300, 2), dtype=np.float32), 44100)
    with pytest.raises(ValueError, match="outside the trial audio"):
        dashboard_app._write_three_channel_trial_wav(output, source, onset_s, tmp_path / "work")
    assert not output.exists()


def test_sequence_preserves_float_audio_and_complete_pcm_silence(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app.shutil, "which", lambda _name: "ffmpeg")

    def reject_stream_copy(*_args, **_kwargs):
        raise AssertionError("Mixed encodings must not reach FFmpeg stream-copy")

    monkeypatch.setattr(dashboard_app.subprocess, "run", reject_stream_copy)
    source = tmp_path / "native-float.wav"
    output = tmp_path / "sequence.wav"
    rate = 44100
    time = np.arange(rate, dtype=np.float64) / rate
    pcm = np.repeat((0.4 * np.sin(2 * np.pi * 440 * time))[:, None], 2, axis=1)
    sf.write(source, pcm, rate, subtype="FLOAT")
    duration = dashboard_app._write_variant_wav_lossless(output, [
        {"kind": "looming_stimulus", "path": str(source), "gain": 1.0},
        {"kind": "jitter", "duration_s": 0.1},
    ], tmp_path / "segments")
    actual, actual_rate = sf.read(output, always_2d=True)
    assert actual_rate == rate
    assert len(actual) == rate + 4410
    assert duration == pytest.approx(1.1)
    np.testing.assert_allclose(actual[:rate], pcm, atol=2 / 32768)
    assert not np.any(actual[rate:])


def test_canzoneri_bake_contains_early_and_late_control_cues(tmp_path):
    controller = DashboardController(
        design_path=tmp_path / "design.json",
        render_dir=tmp_path / "render",
        session_root=tmp_path / "sessions",
        import_dir=tmp_path / "imports",
        preview_dir=tmp_path / "previews",
        project_registry_root=tmp_path / "projects",
        state_root=tmp_path / "state",
    )
    controller.load_template("canzoneri_2012_dynamic_sounds", snapshot=False)
    design = controller.design
    project = controller._ensure_project_context(design)
    dashboard_app._bake_trial_sequence_variants(design, project.project_dir)
    result = dashboard_app._bake_audio_tactile_trial_files(design, project.project_dir)
    manifest = json.loads(dashboard_app._read_text_file(Path(result["manifest_path"]), encoding="utf-8"))
    assert (result["audio_tactile_count"], result["baseline_count"], result["catch_count"]) == (10, 4, 2)
    cue = dashboard_app._load_tactile_cue(44100)
    for row in manifest["files"]:
        audio, rate = sf.read(dashboard_app._soundfile_path(row["file_path"]), dtype="float32", always_2d=True)
        assert rate == 44100
        assert len(audio) == 5 * rate
        if row["family"] == "catch":
            continue
        onset = round((1 + row["soa_ms"] / 1000) * rate)
        assert row["tactile_onset_s"] == pytest.approx(onset / rate)
        assert 0 <= onset < onset + len(cue) <= len(audio)
        np.testing.assert_allclose(audio[onset:onset + len(cue), 2], cue, atol=2 / 32768)
        assert not np.any(audio[:onset, 2])
        assert not np.any(audio[onset + len(cue):, 2])
        if row["family"] in {"audio_tactile", "baseline"}:
            assert row["looming_segment_onset_s"] == 1
            assert not np.any(audio[:rate, :2])
            assert np.any(audio[rate:4 * rate, :2])
            assert not np.any(audio[4 * rate:, :2])
        if row["family"] == "baseline":
            # T0/T6 occur in silence within an otherwise audible trial.
            assert not np.any(audio[onset:onset + len(cue), :2])
    assert dashboard_app._validate_tactile_trial_manifest(manifest, design=design) == []
    baseline = next(row for row in manifest["files"] if row["family"] == "baseline")
    for invalid_onset in (-0.7, 5.0):
        baseline["tactile_onset_s"] = invalid_onset
        errors = dashboard_app._validate_tactile_trial_manifest(manifest, design=design)
        assert any("outside the trial audio" in error for error in errors)


def test_taffou_control_cues_use_sound_relative_offsets_and_retain_sound(tmp_path):
    controller = DashboardController(
        design_path=tmp_path / "design.json", render_dir=tmp_path / "render",
        session_root=tmp_path / "sessions", import_dir=tmp_path / "imports",
        preview_dir=tmp_path / "previews", project_registry_root=tmp_path / "projects",
        state_root=tmp_path / "state",
    )
    controller.load_template("taffou_2014_cynophobic_rear_looming", snapshot=False)
    design = controller.design
    project = controller._ensure_project_context(design)
    dashboard_app._bake_trial_sequence_variants(design, project.project_dir)
    result = dashboard_app._bake_audio_tactile_trial_files(design, project.project_dir)
    manifest = json.loads(dashboard_app._read_text_file(Path(result["manifest_path"]), encoding="utf-8"))
    rows = [row for row in manifest["files"] if row["family"] == "baseline"]
    assert len(rows) == 8
    assert {row["soa_ms"] for row in rows} == {-650, 3650}
    for row in rows:
        audio, rate = sf.read(dashboard_app._soundfile_path(row["file_path"]), dtype="float32", always_2d=True)
        assert row["tactile_onset_s"] == pytest.approx(1 + row["soa_ms"] / 1000)
        onset = round(row["tactile_onset_s"] * rate)
        cue = dashboard_app._load_tactile_cue(rate)
        np.testing.assert_allclose(audio[onset:onset + len(cue), 2], cue, atol=2 / 32768)
        assert not np.any(audio[onset:onset + len(cue), :2])
        assert np.any(audio[rate:4 * rate, :2])
        assert len(audio) == round(6.7 * rate)
