from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
import soundfile as sf

from peripersonal_space_toolkit.focus_layout import (
    focus_palette_contrast_report,
    render_focus_layout_profile,
)
from peripersonal_space_toolkit.output_layout import (
    output_metadata_dir,
    output_profile_snapshot_dir,
    output_project_state_dir,
    output_runner_logs_dir,
)
from peripersonal_space_toolkit.session_runner import RUN_PACKAGE_SCHEMA, RunBlock, RunPackage, SessionCaptureOptions, load_run_package
from peripersonal_space_toolkit.tactile_calibration.schema import (
    CALIBRATION_SCHEMA,
    CONFIRMATION_REQUIRED_CLEAN_CATCHES,
    CONFIRMATION_REQUIRED_CONSECUTIVE_HITS,
    PROTOCOL_NAME,
    VALID_RESPONSE_END_MS,
    VALID_RESPONSE_START_MS,
)


def _write_minimal_session_manifest(
    tmp_path: Path,
    *,
    participant_id: str = "P001",
    source_run_setup_manifest_path: Path | None = None,
    blocks: list[dict[str, object]] | None = None,
) -> Path:
    session_dir = tmp_path / f"{participant_id}_20260613_120000"
    session_dir.mkdir()
    manifest_path = session_dir / "session_manifest.json"
    payload = {
        "schema": RUN_PACKAGE_SCHEMA,
        "participant_id": participant_id,
        "session_id": f"{participant_id}_20260613_120000",
        "created_at": "2026-06-13T12:00:00",
        "design_path": "design.json",
        "protocol_path": "protocol_schedule.csv",
        "render_manifest_path": "",
        "execution_mode": "participant_block_wavs",
        "blocks": blocks or [],
    }
    if source_run_setup_manifest_path is not None:
        payload["source_run_setup_manifest_path"] = str(source_run_setup_manifest_path)
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def test_validation_start_gate_waits_for_ready_file(tmp_path: Path, monkeypatch):
    from peripersonal_space_toolkit import focus_app

    ready_file = tmp_path / "external_labrecorder.ready"
    records: list[dict[str, object]] = []
    state: dict[str, object] = {}
    monkeypatch.setenv("PPS_FOCUS_VALIDATION_START_READY_FILE", str(ready_file))
    monkeypatch.setenv("PPS_FOCUS_VALIDATION_START_READY_TIMEOUT_S", "10")

    assert not focus_app._validation_start_gate_ready(records, state, source="test")
    ready_file.write_text("ready\n", encoding="utf-8")
    assert focus_app._validation_start_gate_ready(records, state, source="test")

    labels = [str(record["label"]) for record in records]
    assert labels == ["start_gate_waiting", "start_gate_released"]


def test_timeline_soa_display_marks_catch_trials_not_applicable():
    from peripersonal_space_toolkit import focus_app

    catch_segment = SimpleNamespace(family="catch", trial_label="Catch", soa_ms="0")
    audio_only_segment = SimpleNamespace(family="audio_only", trial_label="Audio-only", soa_ms="0")
    tactile_segment = SimpleNamespace(family="audio_tactile", trial_label="Audio-tactile", soa_ms="300")
    missing_segment = SimpleNamespace(family="baseline", trial_label="Baseline", soa_ms="")

    assert focus_app._timeline_soa_display_label(catch_segment) == "N/A"
    assert focus_app._timeline_soa_display_label(audio_only_segment) == "N/A"
    assert focus_app._timeline_soa_display_label(tactile_segment) == "300 ms"
    assert focus_app._timeline_soa_display_label(missing_segment) == "SOA"
    assert focus_app._timeline_row_label_optional("Type") is False
    assert focus_app._timeline_row_label_optional("Noise") is False
    assert focus_app._timeline_row_label_optional("SOA") is True


def test_phone_transfer_bridge_serves_lightweight_building_block_packages(tmp_path: Path):
    from peripersonal_space_toolkit import focus_app

    wav = tmp_path / "trial.wav"
    wav.write_bytes(b"RIFF....WAVE")
    block_manifest = tmp_path / "block_01.csv"
    block_manifest.write_text(
        "\n".join(
            [
                "Trial_Number,Trial_UID,Trial_Type,Family,SOA_ms,Row_Label,Noise_Type,Trial_Start_S,Trial_Duration_S,Trial_End_S,Tactile_Onset_S,Response_Window_Onset_S,Trial_File_Path,Source_SHA256",
                f"1,trial-a,audio_tactile,audio_tactile,300,inhale,white,0.000,4.000,4.000,1.250,1.250,{wav},",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    package = RunPackage(
        participant_id="P001",
        session_id="session-001",
        created_at="2026-06-30T00:00:00Z",
        session_dir=tmp_path / "sessions" / "P001" / "session-001",
        design_path=tmp_path / "design.json",
        protocol_path=tmp_path / "protocol.json",
        manifest_path=tmp_path / "session_manifest.json",
        render_manifest_path=None,
        blocks=[
            RunBlock(
                index=1,
                label="Block 01",
                manifest_path=block_manifest,
                wav_path=tmp_path / "full_block.wav",
                trial_count=1,
                duration_s=4.0,
            )
        ],
    )
    bridge = focus_app._PhoneTransferBridge(
        packages=[package],
        transfer_id="transfer-001",
        profile_id="study5",
        participant_id="P001",
        port=8767,
    )

    listing = bridge.mobile_packages()
    package_id = listing["active_package_id"]
    manifest = bridge.mobile_package_manifest(package_id)
    assets = {asset["asset_id"]: asset for asset in manifest["assets"]}
    building_block_asset_id = manifest["blocks"][0]["trials"][0]["building_block_asset_id"]
    path, media_type = bridge.mobile_package_asset_path(package_id, building_block_asset_id)

    assert bridge.health()["mobile_runtime"]["mobile_runnable"] is True
    assert listing["packages"][0]["asset_count"] == 1
    assert manifest["asset_strategy"] == "trial_building_blocks_only"
    assert {asset["role"] for asset in manifest["assets"]} == {"trial_building_block"}
    assert "block-01-audio" not in assets
    assert path == str(wav)
    assert media_type == "audio/wav"


def test_validation_external_mouse_click_uses_helper_python(monkeypatch):
    from peripersonal_space_toolkit import focus_app

    calls: list[dict[str, object]] = []

    class FakeCompleted:
        returncode = 0
        stdout = json.dumps({"ok": True, "backend": "pynput", "x": 101, "y": 202})
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append({"command": list(command), **kwargs})
        return FakeCompleted()

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = focus_app._send_validation_external_mouse_click(
        x=101,
        y=202,
        backend="pynput",
        python_path=sys.executable,
    )

    assert result["ok"] is True
    assert result["backend"] == "pynput"
    assert result["python"] == sys.executable
    assert calls[0]["command"][0] == sys.executable
    assert calls[0]["command"][1] == "-c"
    assert calls[0]["command"][3:] == ["pynput", "101", "202", "0", "0", "0", "0"]
    assert calls[0]["capture_output"] is True
    assert calls[0]["text"] is True


def _collect_widget_texts(widget, widget_type) -> list[str]:
    texts: list[str] = []
    for child in widget.findChildren(widget_type):
        if hasattr(child, "text"):
            try:
                text = child.text()
            except TypeError:
                text = ""
            if text:
                texts.append(str(text))
    return texts


def _fill_required_setup(window) -> None:
    window.participant_name_input.setText("Mock Participant")
    window.age_input.setText("30")
    for combo_name, value in (("handedness_combo", "right"), ("gender_combo", "prefer_not_to_say")):
        combo = getattr(window, combo_name)
        assert _set_combo_for_test(combo, value)


def _set_combo_for_test(combo, value: str) -> bool:
    index = combo.findData(value)
    if index < 0:
        return False
    combo.setCurrentIndex(index)
    return True


def _write_focus_preview_block_csv(path: Path, *, block_offset: int = 0) -> None:
    path.write_text(
        "\n".join(
            [
                "Trial_Number,Trial_UID,Trial_Type,Family,Row_Label,Fixed_Audio_Labels,Noise_Type,SOA_ms,Trial_Start_S,Trial_End_S,Tactile_Onset_S,Sample_Rate_Hz",
                f"1,T{block_offset + 1:03d},Audio-Tactile,audio_tactile,Inhale,Frontal looming,pink,300,0.0,8.0,4.3,1000",
                f"2,T{block_offset + 2:03d},Baseline,baseline,Exhale,Baseline,white,800,8.0,16.0,8.8,1000",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_focus_preview_session_manifest(tmp_path: Path) -> Path:
    block_1_csv = tmp_path / "block_01.csv"
    block_2_csv = tmp_path / "block_02.csv"
    block_3_csv = tmp_path / "block_03.csv"
    _write_focus_preview_block_csv(block_1_csv)
    _write_focus_preview_block_csv(block_2_csv, block_offset=10)
    _write_focus_preview_block_csv(block_3_csv, block_offset=20)
    blocks = [
        {
            "index": 1,
            "label": "Block 01",
            "manifest_path": str(block_1_csv),
            "wav_path": str(tmp_path / "block_01.wav"),
            "trial_count": 2,
            "duration_s": 16.0,
            "metadata": {"part_number": 1, "phase": "pre", "phase_label": "Condition 1", "sample_rate_hz": 1000},
        },
        {
            "index": 2,
            "label": "Block 02",
            "manifest_path": str(block_2_csv),
            "wav_path": str(tmp_path / "block_02.wav"),
            "trial_count": 2,
            "duration_s": 16.0,
            "metadata": {"part_number": 1, "phase": "pre", "phase_label": "Condition 1", "sample_rate_hz": 1000},
        },
        {
            "index": 3,
            "label": "Block 03",
            "manifest_path": str(block_3_csv),
            "wav_path": str(tmp_path / "block_03.wav"),
            "trial_count": 2,
            "duration_s": 16.0,
            "metadata": {"part_number": 2, "phase": "post", "phase_label": "Condition 2", "sample_rate_hz": 1000},
        },
    ]
    manifest = _write_minimal_session_manifest(tmp_path, blocks=blocks)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["instruction_profile"] = {
        "schema": "pps-run-instructions.v1",
        "slots": [
            {"slot": "before_experiment", "label": "General", "enabled": True, "path": "general.wav", "duration_s": 85.7, "continue_mode": "button"},
            {"slot": "before_block", "label": "Pre-Block", "enabled": True, "path": "pre_block.wav", "duration_s": 8.4, "continue_mode": "click"},
            {"slot": "after_block", "label": "Post-Block", "enabled": True, "path": "post_block.wav", "duration_s": 8.8, "continue_mode": "click"},
            {"slot": "between_conditions", "label": "Interim", "enabled": True, "path": "interim.wav", "duration_s": 10.1, "continue_mode": "button"},
            {"slot": "after_experiment", "label": "Finish", "enabled": True, "path": "finish.wav", "duration_s": 7.0, "continue_mode": "button"},
        ],
    }
    manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def _write_split_focus_session_manifests(tmp_path: Path) -> tuple[Path, Path]:
    group_id = "P001_20260613_120000"
    group_dir = tmp_path / group_id
    part_manifests: list[Path] = []
    for part_number in (1, 2):
        part_dir = group_dir / f"part_{part_number:02d}"
        part_dir.mkdir(parents=True, exist_ok=True)
        block_csv = part_dir / f"part_{part_number:02d}_block_01.csv"
        _write_focus_preview_block_csv(block_csv, block_offset=part_number * 10)
        block_wav = part_dir / f"part_{part_number:02d}_block_01.wav"
        block_wav.write_bytes(b"")
        manifest_path = part_dir / "session_manifest.json"
        payload = {
            "schema": RUN_PACKAGE_SCHEMA,
            "participant_id": "P001",
            "session_id": f"{group_id}_part{part_number:02d}",
            "session_group_id": group_id,
            "part_number": part_number,
            "part_session_id": f"{group_id}_part{part_number:02d}",
            "part_folder_name": f"part_{part_number:02d}",
            "part_split_schema": "pps-runner-part-split.v1",
            "created_at": "2026-06-13T12:00:00",
            "session_dir": str(part_dir),
            "design_path": "design.json",
            "protocol_path": "protocol_schedule.csv",
            "render_manifest_path": "",
            "execution_mode": "participant_block_wavs",
            "sibling_part_manifest_paths": [],
            "blocks": [
                {
                    "index": 1,
                    "label": f"Part {part_number} Block 01",
                    "manifest_path": str(block_csv),
                    "wav_path": str(block_wav),
                    "trial_count": 2,
                    "duration_s": 16.0,
                    "metadata": {
                        "part_number": part_number,
                        "part_block_number": 1,
                        "phase": f"part_{part_number}",
                        "phase_label": f"Part {part_number}",
                        "sample_rate_hz": 1000,
                    },
                }
            ],
        }
        manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        part_manifests.append(manifest_path)
    for manifest_path in part_manifests:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["sibling_part_manifest_paths"] = [str(path) for path in part_manifests if path != manifest_path]
        manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return part_manifests[0], part_manifests[1]


def _write_analysis_review_outputs(session_dir: Path) -> dict[str, Path]:
    analysis_dir = session_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    session_id = session_dir.name
    scope = "Part 1 / Inhale / pink"
    pooled_scope = "All parts / Inhale / pink"
    curves = analysis_dir / f"{session_id}_pps_curve_points.csv"
    curves.write_text(
        "\n".join(
            [
                "scope,aggregation_mode,aggregation_label,soa_ms,fit_metric,facilitation_ms,facilitation_sem_ms,mean_rt_ms,n",
                f"{scope},separate_parts,Separate parts,100,facilitation_ms,10,2,320,3",
                f"{scope},separate_parts,Separate parts,200,facilitation_ms,20,3,300,3",
                f"{scope},separate_parts,Separate parts,400,facilitation_ms,35,4,280,3",
                f"{scope},separate_parts,Separate parts,800,facilitation_ms,44,3,260,3",
                f"{pooled_scope},pooled_parts,Pool parts,100,facilitation_ms,12,2,318,6",
                f"{pooled_scope},pooled_parts,Pool parts,200,facilitation_ms,22,3,298,6",
                f"{pooled_scope},pooled_parts,Pool parts,400,facilitation_ms,34,4,282,6",
                f"{pooled_scope},pooled_parts,Pool parts,800,facilitation_ms,43,3,262,6",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    fits = analysis_dir / f"{session_id}_model_fits.csv"
    fits.write_text(
        "\n".join(
            [
                "scope,aggregation_mode,aggregation_label,model,fit_metric,n_points,intercept,slope,log_slope,lower,upper,pps_boundary_soa_ms,aic,r2,rmse",
                f"{scope},separate_parts,Separate parts,linear,facilitation_ms,4,8,0.05,, ,,,14,0.91,2.0",
                f"{scope},separate_parts,Separate parts,logarithmic_decay,facilitation_ms,4,-12,,8,,,,12,0.94,1.6",
                f"{scope},separate_parts,Separate parts,sigmoid,facilitation_ms,4,,0.01,,5,50,300,10,0.97,1.1",
                f"{pooled_scope},pooled_parts,Pool parts,linear,facilitation_ms,4,9,0.047,,,,,13,0.92,1.9",
                f"{pooled_scope},pooled_parts,Pool parts,logarithmic_decay,facilitation_ms,4,-10,,7,,,,11,0.94,1.5",
                f"{pooled_scope},pooled_parts,Pool parts,sigmoid,facilitation_ms,4,,0.009,,4,48,320,9,0.98,1.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    comparison = analysis_dir / f"{session_id}_model_fit_comparison.csv"
    comparison.write_text(
        "scope,aggregation_mode,aggregation_label,best_model,best_aic,best_r2,fit_metric,n_points\n"
        f"{scope},separate_parts,Separate parts,sigmoid,10,0.97,facilitation_ms,4\n"
        f"{pooled_scope},pooled_parts,Pool parts,sigmoid,9,0.98,facilitation_ms,4\n",
        encoding="utf-8",
    )
    condition_curves = analysis_dir / f"{session_id}_condition_lens_curve_points.csv"
    condition_curve_lines = [
        "analysis_lens,analysis_lens_label,display_scope,scope,aggregation_mode,aggregation_label,part_label,state_label,pooled_factors,soa_ms,fit_metric,facilitation_ms,facilitation_sem_ms,mean_rt_ms,n,baseline_mean_rt_ms,baseline_n,baseline_source_soas_ms,baseline_correction_method",
    ]
    baseline_suffix = "330,32,100;200;400;800,condition_mean_pooled_soa"
    for part in (1, 2):
        for state, offset in (("Inhale", 0), ("Exhale", 5)):
            display = f"Part {part} / {state}"
            for soa, facilitation in ((100, 10 + offset + part), (200, 20 + offset + part), (400, 34 + offset + part), (800, 43 + offset + part)):
                condition_curve_lines.append(
                    f"two_by_two,2 x 2,{display},{display},two_by_two,2 x 2,Part {part},{state},noise/source,{soa},facilitation_ms,{facilitation},2,{330 - facilitation},8,{baseline_suffix}"
                )
    for part in (1, 2):
        display = f"Part {part}"
        for soa, facilitation in ((100, 12 + part), (200, 23 + part), (400, 35 + part), (800, 44 + part)):
            condition_curve_lines.append(
                f"part,Parts,{display},{display},part,Part lens,Part {part},All states,state;noise/source,{soa},facilitation_ms,{facilitation},2,{330 - facilitation},16,{baseline_suffix}"
            )
    for state, offset in (("Inhale", 0), ("Exhale", 5)):
        for soa, facilitation in ((100, 12 + offset), (200, 23 + offset), (400, 35 + offset), (800, 44 + offset)):
            condition_curve_lines.append(
                f"state,States,{state},{state},state,State lens,All parts,{state},part;noise/source,{soa},facilitation_ms,{facilitation},2,{330 - facilitation},16,{baseline_suffix}"
            )
    for soa, facilitation in ((100, 14), (200, 24), (400, 36), (800, 45)):
        condition_curve_lines.append(
            f"overall,Overall,All conditions,All conditions,overall,Overall lens,All parts,All states,part;state;noise/source,{soa},facilitation_ms,{facilitation},2,{330 - facilitation},32,{baseline_suffix}"
        )
    condition_curves.write_text("\n".join(condition_curve_lines) + "\n", encoding="utf-8")
    condition_fits = analysis_dir / f"{session_id}_condition_lens_model_fits.csv"
    condition_fit_lines = [
        "analysis_lens,analysis_lens_label,display_scope,scope,aggregation_mode,aggregation_label,model,fit_metric,n_points,parameter_count,intercept,slope,log_slope,lower,upper,pps_boundary_soa_ms,aic,aicc,r2,rmse,delta_aicc,evidence_tier",
    ]
    for lens, display in (
        ("two_by_two", "Part 1 / Inhale"),
        ("two_by_two", "Part 1 / Exhale"),
        ("two_by_two", "Part 2 / Inhale"),
        ("two_by_two", "Part 2 / Exhale"),
        ("part", "Part 1"),
        ("part", "Part 2"),
        ("state", "Inhale"),
        ("state", "Exhale"),
        ("overall", "All conditions"),
    ):
        label = "2 x 2" if lens == "two_by_two" else "Overall" if lens == "overall" else "Parts" if lens == "part" else "States"
        condition_fit_lines.extend(
            [
                f"{lens},{label},{display},{display},{lens},{label},linear,facilitation_ms,4,2,8,0.05,,,,14,26,0.91,2.0,6,mixed",
                f"{lens},{label},{display},{display},{lens},{label},logarithmic_decay,facilitation_ms,4,2,-12,,8,,,12,24,0.94,1.6,4,mixed",
                f"{lens},{label},{display},{display},{lens},{label},sigmoid,facilitation_ms,4,4,,0.01,,5,50,300,10,,0.97,1.1,,insufficient",
            ]
        )
    condition_fits.write_text("\n".join(condition_fit_lines) + "\n", encoding="utf-8")
    condition_comparison = analysis_dir / f"{session_id}_condition_lens_model_fit_comparison.csv"
    condition_comparison.write_text(
        "analysis_lens,analysis_lens_label,display_scope,scope,aggregation_mode,aggregation_label,best_model,best_aic,best_aicc,best_r2,fit_metric,n_points,delta_aicc,evidence_tier,candidate_models\n"
        "overall,Overall,All conditions,All conditions,overall,Overall lens,logarithmic_decay,12,24,0.94,facilitation_ms,4,2,mixed,linear;logarithmic_decay;sigmoid\n",
        encoding="utf-8",
    )
    condition_triage = analysis_dir / "condition_lens_triage_summary.json"
    condition_triage.write_text(
        json.dumps(
            {
                "schema": "pps-condition-lens-triage.v1",
                "default_lens": "two_by_two",
                "default_model": "logarithmic_decay",
                "interpretation_note": "Condition and model winners are exploratory triage cues.",
                "model_wins_by_subcondition": {"logarithmic_decay": 4},
                "model_button_summaries": {
                    "sigmoid": {"evidence_tier": "insufficient", "overall_winner": False, "subcondition_wins": 0},
                    "logarithmic_decay": {"evidence_tier": "mixed", "overall_winner": True, "subcondition_wins": 4},
                    "linear": {"evidence_tier": "insufficient", "overall_winner": False, "subcondition_wins": 0},
                },
                "condition_lens_buttons": {
                    "two_by_two": {"label": "2 x 2", "curve_separation_winner": True, "boundary_shift_winner": False},
                    "part": {"label": "Part 1 | Part 2", "curve_separation_winner": False, "boundary_shift_winner": True},
                    "state": {"label": "Inhale | Exhale", "curve_separation_winner": False, "boundary_shift_winner": False},
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    quality_gate = analysis_dir / "recording_quality_gate.v1.json"
    quality_gate.write_text(
        json.dumps(
            {
                "schema": "pps-recording-quality-gate.v1",
                "status": "PASS",
                "primary_reason": "No serious exclusion criteria were triggered.",
                "failures": [],
                "warnings": [],
                "metrics": {"overall_hit_rate": 1.0},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    assumption_checks = analysis_dir / "basic_assumption_checks.v1.json"
    assumption_checks.write_text(
        json.dumps(
            {
                "schema": "pps-basic-assumption-checks.v1",
                "alpha": 0.05,
                "outcome": "log_rt_ms",
                "proximity_coding": {
                    "method": "centered_soa_rank",
                    "orientation": "sorted_unique_soa_as_far_to_near",
                    "levels": [100.0, 200.0, 400.0, 800.0],
                    "scores_by_soa_ms": {"100": -1.5, "200": -0.5, "400": 0.5, "800": 1.5},
                },
                "baseline_assumption": {
                    "label": "Baseline Assumption",
                    "status": "PASS",
                    "passed": True,
                    "summary": "No significant baseline proximity/SOA trend was detected; pragmatic baseline flatness was accepted.",
                    "beta": -0.001,
                    "p_two_sided": 0.72,
                    "df_resid": 18,
                    "coverage": {"n": 12, "distinct_soa_count": 4, "counts_by_soa_ms": {"100": 3, "200": 3, "400": 3, "800": 3}},
                },
                "peripersonal_space_assumption": {
                    "label": "Peripersonal Space Assumption",
                    "status": "PASS",
                    "passed": True,
                    "summary": "Audio-tactile RTs sped up from far to near more than baseline, with the predicted significant interaction.",
                    "interaction_beta": -0.12,
                    "p_one_sided_negative": 0.012,
                    "df_resid": 28,
                    "baseline_slope_beta": -0.001,
                    "audio_tactile_slope_beta": -0.121,
                    "baseline_far_to_near_speedup_ms": 2.0,
                    "audio_tactile_far_to_near_speedup_ms": 68.0,
                    "pps_far_to_near_gain_ms": 66.0,
                    "coverage": {
                        "baseline": {"n": 12, "distinct_soa_count": 4, "counts_by_soa_ms": {"100": 3, "200": 3, "400": 3, "800": 3}},
                        "audio_tactile": {"n": 24, "distinct_soa_count": 4, "counts_by_soa_ms": {"100": 6, "200": 6, "400": 6, "800": 6}},
                    },
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    participant_trials = session_dir / f"{session_id}_trials.csv"
    trial_header = (
        "trial_uid,trial_number,trial_type,stimulus_modality,tactile_present,catch_trial,response_given,"
        "outcome,hit,part_number,condition,respiratory_phase,noise_type,soa_ms,rt_ms,is_topup,topup_role"
    )
    trial_rows = [
        "T001,1,Audio-Tactile,audio_tactile,true,false,true,Hit,true,1,,Inhale,pink,100,310,false,",
        "T002,2,Audio-Tactile,audio_tactile,true,false,true,Hit,true,1,,Inhale,pink,200,300,false,",
        "T003,3,Baseline,tactile,true,false,true,Hit,true,1,,Inhale,pink,,330,false,",
        "T004,4,Audio-Tactile,audio_tactile,true,false,false,Miss,false,1,,Inhale,pink,400,,false,",
        "TU001,5,Audio-Tactile,audio_tactile,true,false,true,Hit,true,1,,Inhale,pink,800,280,true,rescue",
        "C001,6,Catch,audio,false,true,false,Hit,true,1,,Inhale,pink,,,false,",
        "C002,7,Catch,audio,false,true,false,Hit,true,1,,Inhale,pink,,,false,",
        "C003,8,Catch,audio,false,true,false,Hit,true,1,,Inhale,pink,,,false,",
        "C004,9,Catch,audio,false,true,true,Miss,false,1,,Inhale,pink,,,false,",
    ]
    participant_trials.write_text("\n".join([trial_header, *trial_rows]) + "\n", encoding="utf-8")
    responses = analysis_dir / f"{session_id}_responses.csv"
    final_trial_outcomes = analysis_dir / f"{session_id}_final_trial_outcomes.csv"
    response_header = "trial_uid,trial_type,hit,part_number,condition,respiratory_phase,noise_type,soa_ms,rt_ms,is_topup,topup_role"
    response_rows = [
        "T001,Audio-Tactile,true,1,,Inhale,pink,100,310,false,",
        "T002,Audio-Tactile,true,1,,Inhale,pink,200,300,false,",
        "T003,Baseline,true,1,,Inhale,pink,,330,false,",
        "T004,Audio-Tactile,false,1,,Inhale,pink,400,,false,",
        "TU001,Audio-Tactile,true,1,,Inhale,pink,800,280,true,rescue",
    ]
    responses.write_text("\n".join([response_header, *response_rows]) + "\n", encoding="utf-8")
    final_trial_outcomes.write_text("\n".join([response_header, *response_rows]) + "\n", encoding="utf-8")
    summary = analysis_dir / f"{session_id}_summary.csv"
    summary.write_text(
        "scope,aggregation_mode,n,hit_rate\n"
        f"{scope},separate_parts,5,0.8\n"
        f"{pooled_scope},pooled_parts,10,0.8\n",
        encoding="utf-8",
    )
    behavior = analysis_dir / "data_behavior_by_scope.csv"
    behavior.write_text(
        "scope,aggregation_mode,signal,feature,message,evidence\n"
        f"{scope},separate_parts,Expected pattern,RT or facilitation by SOA/distance,The recording has enough SOA points for common PPS curve review,points=4\n"
        "Session,,Technical caveat,Timing evidence,Timing evidence is available for review,timing_qc_rows=1\n",
        encoding="utf-8",
    )
    behavior_summary = analysis_dir / "exploratory_quality_summary.json"
    behavior_summary.write_text(
        json.dumps(
            {
                "schema": "pps-exploratory-data-behavior.v1",
                "interpretation_note": "Exploratory data-behavior signals are not scientific conclusions or participant-readiness certification.",
                "signal_counts": {"Expected pattern": 1, "Technical caveat": 1},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (session_dir / "analysis_summary.txt").write_text("Tactile trials reconstructed: 4\n", encoding="utf-8")
    return {
        "curves": curves,
        "model_fits": fits,
        "model_fit_comparison": comparison,
        "summary": summary,
        "condition_lens_curves": condition_curves,
        "condition_lens_model_fits": condition_fits,
        "condition_lens_model_fit_comparison": condition_comparison,
        "condition_lens_triage_summary": condition_triage,
        "recording_quality_gate": quality_gate,
        "basic_assumption_checks": assumption_checks,
        "participant_trials": participant_trials,
        "responses": responses,
        "final_trial_outcomes": final_trial_outcomes,
        "data_behavior_by_scope": behavior,
        "exploratory_quality_summary": behavior_summary,
    }


def test_focus_mode_run_plan_numbers_topup_slots_by_play_order():
    from peripersonal_space_toolkit import focus_app

    package = SimpleNamespace(
        blocks=[
            SimpleNamespace(
                index=index,
                label=f"Block {index:02d}",
                duration_s=1.0,
                metadata={"part_number": 1 if index <= 6 else 2},
            )
            for index in range(1, 13)
        ]
    )

    plan = focus_app._run_plan_text(package, include_topup_slots=True)

    assert "Part 01:" in plan
    assert "6 Block 06" in plan
    assert "7 Top-up if needed" in plan
    assert "Part 02:" in plan
    assert "1 Block 07" in plan
    assert "6 Block 12" in plan
    assert "7 Top-up if needed" in plan
    assert focus_app._run_plan_total(package, include_topup_slots=True) == 14


def _assert_widget_inside_dialog(widget, dialog) -> None:
    top_left = widget.mapTo(dialog, widget.rect().topLeft())
    bottom_right = widget.mapTo(dialog, widget.rect().bottomRight())
    assert top_left.x() >= 0
    assert top_left.y() >= 0
    assert bottom_right.x() <= dialog.width()
    assert bottom_right.y() <= dialog.height()
    assert widget.visibleRegion().boundingRect().width() > 0
    assert widget.visibleRegion().boundingRect().height() > 0


def _widget_rect(widget, dialog) -> dict[str, int]:
    top_left = widget.mapTo(dialog, widget.rect().topLeft())
    bottom_right = widget.mapTo(dialog, widget.rect().bottomRight())
    return {
        "x": int(top_left.x()),
        "y": int(top_left.y()),
        "right": int(bottom_right.x()),
        "bottom": int(bottom_right.y()),
        "width": int(widget.width()),
        "height": int(widget.height()),
    }


def test_focus_layout_renderer_preserves_legibility_baselines():
    constrained = render_focus_layout_profile(1024, 600)
    compact = render_focus_layout_profile(1366, 768)
    standard = render_focus_layout_profile(1920, 1080)

    assert constrained.screen_class == "constrained"
    assert compact.screen_class in {"compact", "standard"}
    assert standard.screen_class == "spacious"
    assert constrained.window_width <= 1024
    assert constrained.window_height <= 600
    assert constrained.body_font_pt >= 10.5
    assert constrained.button_min_height >= 30
    assert constrained.response_panel_side >= constrained.target_min_height
    assert constrained.target_min_height >= 76
    assert constrained.target_max_height == constrained.target_min_height
    assert constrained.experiment_control_min_height >= 152
    assert compact.experiment_control_min_height >= 212
    assert standard.experiment_control_min_height >= 280
    assert constrained.experiment_control_min_height >= constrained.experiment_control_content_min_height
    assert compact.experiment_control_min_height >= compact.experiment_control_content_min_height
    assert standard.experiment_control_min_height >= standard.experiment_control_content_min_height
    assert constrained.experiment_control_initial_height >= constrained.experiment_control_min_height
    assert compact.experiment_control_initial_height > constrained.experiment_control_initial_height
    assert standard.experiment_control_initial_height > compact.experiment_control_initial_height
    for width, height in ((1920, 1000), (1600, 900), (1536, 864), (1366, 768)):
        laptop = render_focus_layout_profile(width, height)
        assert laptop.experiment_control_initial_height >= laptop.experiment_control_content_min_height
        assert laptop.experiment_control_min_height >= laptop.experiment_control_content_min_height
    assert constrained.right_stack_mode == "tabs"
    assert compact.right_stack_mode == "resizable"
    assert standard.right_stack_mode == "resizable"
    assert constrained.recording_chip_columns == 2
    assert standard.recording_chip_columns == 3
    assert standard.target_min_height > constrained.target_min_height
    assert standard.target_max_height == standard.target_min_height
    assert standard.response_panel_side > constrained.response_panel_side

    contrasts = focus_palette_contrast_report()
    assert contrasts["text_on_background"] >= 7.0
    assert contrasts["text_on_surface"] >= 7.0
    assert contrasts["muted_on_background"] >= 4.5
    assert contrasts["muted_on_surface"] >= 4.5
    assert contrasts["primary_button_text"] >= 4.5


def test_focus_mode_shell_visual_smoke(tmp_path: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PIL import Image, ImageStat
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))
    window = focus_app.FocusModeWindow(
        q,
        package,
        capture_options=SessionCaptureOptions(
            enable_lsl=False,
            write_internal_xdf=True,
            write_analysis_csvs=True,
            start_backup_recording=False,
        ),
        enable_missed_trial_topup=True,
    )
    window_type = q["Qt"].WindowType
    flags = window.dialog.windowFlags()
    assert flags & window_type.WindowSystemMenuHint == window_type.WindowSystemMenuHint
    assert flags & window_type.WindowMinimizeButtonHint == window_type.WindowMinimizeButtonHint
    assert flags & window_type.WindowMaximizeButtonHint == window_type.WindowMaximizeButtonHint
    assert flags & window_type.WindowCloseButtonHint == window_type.WindowCloseButtonHint
    assert window.dialog.isSizeGripEnabled()
    window.dialog.resize(1040, 720)
    window.dialog.show()
    app.processEvents()

    texts = _collect_widget_texts(window.dialog, q["QWidget"])
    joined = "\n".join(texts)
    assert "PPS Experiment Runner" in joined
    assert "Native Focus Mode" in joined
    assert "Part -" in joined
    assert "Participant Response" in joined
    assert "Participant Setup" in joined
    assert "Submit setup" in joined
    assert window.mode_tabs is not None
    assert window.mode_tabs.tabText(window.data_logging_tab_index) == "Data Logging"
    assert window.mode_tabs.tabText(window.experiment_control_tab_index) == "Experiment Control"
    assert window.mode_tabs.currentIndex() == window.data_logging_tab_index
    assert window.mode_tabs.isTabEnabled(window.experiment_control_tab_index)
    assert "Data Logging / Experiment Settings" in joined
    assert "Data Logging" in joined
    assert "Experiment Control" in joined
    assert "Output Levels" in joined
    assert "Output 1/2" in joined
    assert "Output 3/4" in joined
    assert "Test Audio" in joined
    assert "Test Tactile" in joined
    assert "Part 1" in joined
    assert "Part 2" in joined
    if window.layout_profile.screen_class != "constrained":
        assert "Block Order" in joined
        assert "Stimulus / Tactile / Click Timeline" in joined
    assert "Next tactile" in joined
    assert "Instruction clips" in joined
    assert "No preloaded clips" in joined
    assert "Include name in LSL/session markers" in joined
    assert "events.csv on" not in joined
    assert "LSL/event protocol" not in joined
    assert "Save additional fail-safe local recording" in joined
    assert "estimated extra file" in joined
    assert "Record wired loopback from Input 4" in joined
    assert "Record full-session LabRecorder XDF" in joined
    assert "Top up missed tactile trials at part end" in joined
    assert "CLICK" in joined
    assert window.participant_code_combo.objectName() == "runnerParticipantCombo"
    assert not window.participant_code_combo.isEditable()
    assert window.participant_code_combo.currentData() == "P001"
    assert window.participant_selector_widget.objectName() == "runnerParticipantStepper"
    assert window.participant_increment_button.objectName() == "participantIncrementButton"
    assert window.participant_decrement_button.objectName() == "participantDecrementButton"
    assert not window.participant_increment_button.isEnabled()
    assert not window.participant_decrement_button.isEnabled()
    assert window.participant_status_summary_label.objectName() == "participantLedgerSummary"
    assert "P001: setup not saved; tactile threshold not calibrated; data not collected" in window.participant_status_summary_label.text()
    assert "unlock start controls" in window.setup_status_label.text()
    assert not window.part_buttons["1"].isEnabled()
    assert not window.part_buttons["2"].isEnabled()
    assert window.preview_display_block_index is None
    placeholders = [line.placeholderText() for line in window.dialog.findChildren(q["QLineEdit"])]
    assert "Participant code" not in placeholders
    assert window.include_name_lsl_checkbox.objectName() == "nameSharingCheckbox"
    assert "(opt-in)" in window.include_name_lsl_checkbox.text()
    assert window.include_name_lsl_checkbox.minimumHeight() >= window.layout_profile.button_min_height + 8
    assert window.setup_submit_button.objectName() == "participantSetupSubmitButton"
    assert window.setup_submit_button.isEnabled()
    assert not window.start_button.isEnabled()
    assert window.output_12_volume_slider.objectName() == "output12VolumeSlider"
    assert window.output_34_volume_slider.objectName() == "output34VolumeSlider"
    assert window.output_12_volume_slider.minimum() == 0
    assert window.output_12_volume_slider.maximum() == 100_000
    assert window.output_34_volume_slider.minimum() == 0
    assert window.output_34_volume_slider.maximum() == 500
    assert window.output_12_volume_percent_box.objectName() == "output12VolumePercentBox"
    assert window.output_34_volume_percent_box.objectName() == "output34VolumePercentBox"
    assert window.output_34_volume_percent_box.decimals() == 3
    assert window.output_34_volume_percent_box.singleStep() == pytest.approx(0.001)
    assert window.output_34_volume_percent_box.maximum() == pytest.approx(0.5)
    assert window.test_audio_button.objectName() == "testAudioOutputButton"
    assert window.test_tactile_button.objectName() == "testTactileOutputButton"
    assert window.tactile_calibration_button.objectName() == "tactileCalibrationButton"
    assert "Threshold" in window.tactile_calibration_button.text()
    assert not window.output_12_volume_slider.isEnabled()
    assert not window.output_34_volume_slider.isEnabled()
    assert not window.test_audio_button.isEnabled()
    assert not window.test_tactile_button.isEnabled()
    assert window.tactile_calibration_button.isEnabled()
    assert window.backup_recording_checkbox.objectName() == "failSafeRecordingCheckbox"
    assert window.wired_loopback_checkbox.objectName() == "wiredLoopbackCheckbox"
    assert window.external_labrecorder_checkbox.objectName() == "externalLabRecorderCheckbox"
    assert not window.external_labrecorder_checkbox.isChecked()
    assert not window.external_labrecorder_checkbox.isEnabled()
    assert not window.wired_loopback_checkbox.isChecked()
    QTest.mouseClick(window.wired_loopback_checkbox, q["Qt"].MouseButton.LeftButton)
    app.processEvents()
    assert window._runtime_capture_options().wired_loopback_mode == "output4_tactile_proxy"
    QTest.mouseClick(window.wired_loopback_checkbox, q["Qt"].MouseButton.LeftButton)
    app.processEvents()
    assert window._runtime_capture_options().wired_loopback_mode == "off"

    _fill_required_setup(window)
    QTest.mouseClick(window.setup_submit_button, q["Qt"].MouseButton.LeftButton)
    app.processEvents()
    assert window.demographics_submitted
    assert window.tactile_calibration_button.isEnabled()
    assert window.mode_tabs.isTabEnabled(window.experiment_control_tab_index)
    assert window.mode_tabs.currentIndex() == window.experiment_control_tab_index
    assert window.part_buttons["1"].isEnabled()
    assert not window.part_buttons["2"].isEnabled()
    assert window.start_button.isEnabled()
    assert "Experiment Control is ready" in window.setup_status_label.text()
    assert window.output_12_volume_slider.isEnabled()
    assert window.output_34_volume_slider.isEnabled()
    assert window.test_audio_button.isEnabled()
    assert window.test_tactile_button.isEnabled()
    assert window.data_columns_widget.objectName() == "dataSettingsColumns"
    assert window.data_logging_column.objectName() == "dataLoggingColumn"
    assert window.experiment_settings_column.objectName() == "experimentSettingsColumn"
    assert "estimated extra file" in window.backup_recording_checkbox.text()
    assert window.response_panel.width() == window.response_panel.height()
    assert window.response_panel.width() == window.layout_profile.response_panel_side
    assert window.output_panel is not window.processing_panel
    assert window.processing_splitter is None
    response_rect = _widget_rect(window.response_panel, window.dialog)
    output_stack_rect = _widget_rect(window.output_stack_cell, window.dialog)
    output_levels_rect = _widget_rect(window.output_levels_panel, window.dialog)
    output_rect = _widget_rect(window.output_panel, window.dialog)
    test_audio_rect = _widget_rect(window.test_audio_button, window.dialog)
    test_tactile_rect = _widget_rect(window.test_tactile_button, window.dialog)
    tactile_threshold_rect = _widget_rect(window.tactile_calibration_button, window.dialog)
    response_cell_rect = _widget_rect(window.response_cell, window.dialog)
    processing_rect = _widget_rect(window.processing_panel, window.dialog)
    run_controls_rect = _widget_rect(window.run_controls_widget, window.dialog)
    start_rect = _widget_rect(window.start_button, window.dialog)
    workspace_rect = _widget_rect(window.workspace_splitter, window.dialog)
    assert window.run_controls_widget.objectName() == "experimentRunControls"
    assert run_controls_rect["y"] >= processing_rect["y"]
    assert start_rect["y"] >= processing_rect["y"]
    assert start_rect["y"] > response_rect["bottom"]
    assert output_stack_rect["x"] >= response_rect["right"]
    assert output_levels_rect["x"] >= output_stack_rect["x"]
    assert output_levels_rect["right"] <= output_stack_rect["right"]
    assert test_audio_rect["height"] >= window.layout_profile.button_min_height
    assert test_tactile_rect["height"] >= window.layout_profile.button_min_height
    assert test_audio_rect["bottom"] < tactile_threshold_rect["y"]
    assert test_tactile_rect["bottom"] < tactile_threshold_rect["y"]
    assert tactile_threshold_rect["bottom"] <= output_levels_rect["bottom"]
    if window.output_panel.isVisible():
        assert output_rect["y"] >= output_levels_rect["bottom"]
        assert output_rect["x"] >= output_stack_rect["x"]
        assert output_rect["right"] <= output_stack_rect["right"]
    else:
        assert window.layout_profile.screen_class == "constrained"
    assert processing_rect["width"] >= workspace_rect["width"] - 8

    screenshot = tmp_path / "focus_mode_shell.png"
    assert window.dialog.grab().save(str(screenshot))
    image = Image.open(screenshot).convert("RGB")
    stat = ImageStat.Stat(image)
    assert image.width >= 900
    assert image.height >= 600
    assert min(stat.stddev) > 2.0

    target_screenshot = tmp_path / "focus_mode_target.png"
    assert window.target_button.grab().save(str(target_screenshot))
    target_image = Image.open(target_screenshot).convert("RGB")
    target_colors = target_image.getcolors(maxcolors=100_000) or []
    assert target_image.width == target_image.height == window.target_button.width()
    assert len(target_colors) >= 4
    assert target_image.getpixel((target_image.width // 2, target_image.height // 2)) != target_image.getpixel((4, 4))
    window.dialog.close()


def test_focus_mode_default_capture_checkboxes_are_operator_opt_out(tmp_path: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))
    window = focus_app.FocusModeWindow(q, package)
    window.dialog.show()
    app.processEvents()

    assert window.wired_loopback_checkbox.isChecked()
    assert window.external_labrecorder_checkbox.isEnabled()
    assert window.external_labrecorder_checkbox.isChecked()
    assert window.topup_checkbox.isChecked()
    assert window._runtime_capture_options().wired_loopback_mode == "output4_tactile_proxy"
    assert window._runtime_capture_options().start_external_labrecorder is True
    assert window._topup_slots_enabled_for_plan() is True

    QTest.mouseClick(window.wired_loopback_checkbox, q["Qt"].MouseButton.LeftButton)
    QTest.mouseClick(window.external_labrecorder_checkbox, q["Qt"].MouseButton.LeftButton)
    QTest.mouseClick(window.topup_checkbox, q["Qt"].MouseButton.LeftButton)
    app.processEvents()

    assert window._runtime_capture_options().wired_loopback_mode == "off"
    assert window._runtime_capture_options().start_external_labrecorder is False
    assert window._topup_slots_enabled_for_plan() is False
    window.dialog.close()


def test_focus_mode_start_button_is_red_and_tracks_selected_split_part(tmp_path: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    part1_manifest, part2_manifest = _write_split_focus_session_manifests(tmp_path)
    package = load_run_package(part1_manifest)
    window = focus_app.FocusModeWindow(
        q,
        package,
        capture_options=SessionCaptureOptions(enable_lsl=False, start_backup_recording=False),
    )
    window.dialog.show()
    app.processEvents()

    assert window.dialog.findChild(q["QPushButton"], "loadNextPartButton") is None
    assert window.start_button.objectName() == "startButton"
    assert "QPushButton#startButton" in window.dialog.styleSheet()
    assert "#8c2f2f" in window.dialog.styleSheet()
    assert window.start_button.text() == "Start Part 01"
    assert not window.part_buttons["1"].isEnabled()
    assert not window.part_buttons["2"].isEnabled()

    _fill_required_setup(window)
    QTest.mouseClick(window.setup_submit_button, q["Qt"].MouseButton.LeftButton)
    app.processEvents()

    assert window.start_button.isEnabled()
    assert window.start_button.text() == "Start Part 01"
    assert window.part_buttons["1"].isEnabled()
    assert window.part_buttons["2"].isEnabled()

    QTest.mouseClick(window.part_buttons["2"], q["Qt"].MouseButton.LeftButton)
    app.processEvents()

    assert Path(window.package.manifest_path) == part2_manifest
    assert window.package.part_number == 2
    assert window.selected_part_key == "2"
    assert window.start_button.text() == "Start Part 02"
    assert [item["part_key"] for item in window.block_plan_items] == ["2", "2"]
    assert window.demographics_submitted
    assert window.start_button.isEnabled()
    window.dialog.close()


def test_focus_mode_clicking_part2_adopts_same_window_labrecorder_handoff(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("PPS_FOCUS_DISABLE_ANALYSIS_POPUP", "1")
    try:
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    part1_manifest, part2_manifest = _write_split_focus_session_manifests(tmp_path)
    package = load_run_package(part1_manifest)
    shared_lsl = object()
    created: list[object] = []

    class FakeController:
        def __init__(
            self,
            package_obj,
            *,
            audio_engine=None,
            capture_options=None,
            lsl_stream_session_id=None,
            shared_lsl_outlet=None,
            external_labrecorder_state=None,
            external_labrecorder_stop_on_run_end=True,
            external_labrecorder_finalize_path=None,
            **_kwargs,
        ):
            self.package = package_obj
            self.audio_engine = audio_engine or SimpleNamespace()
            self.capture_options = capture_options
            self.kwargs = {
                "lsl_stream_session_id": lsl_stream_session_id,
                "shared_lsl_outlet": shared_lsl_outlet,
                "external_labrecorder_state": external_labrecorder_state,
                "external_labrecorder_stop_on_run_end": external_labrecorder_stop_on_run_end,
                "external_labrecorder_finalize_path": external_labrecorder_finalize_path,
            }
            self.events = SimpleNamespace(
                lsl_status=SimpleNamespace(available=True, enabled=True, message="fake LSL active"),
                close=lambda: None,
            )
            self.run_called = False
            created.append(self)

        def handoff_external_labrecorder_to_next_part(self):
            return {
                "schema": "pps-runner-continuous-labrecorder-handoff.v1",
                "capture": object(),
                "status": {"enabled": True, "started": True, "xdf_path": str(self.package.session_dir / "part1_external.xdf")},
                "xdf_path": self.package.session_dir / f"{self.package.session_id}_external_labrecorder.xdf",
                "stdout_path": self.package.manifest_path.parent / "external_labrecorder_stdout.txt",
                "stderr_path": self.package.manifest_path.parent / "external_labrecorder_stderr.txt",
                "report_path": self.package.manifest_path.parent.parent / "external_labrecorder_capture_report.json",
                "lsl_outlet": shared_lsl,
                "lsl_stream_session_id": self.package.session_group_id,
                "session_group_id": self.package.session_group_id,
                "source_part_session_id": self.package.part_session_id,
                "finalize_path": self.package.session_dir.parent / f"{self.package.session_group_id}_external_labrecorder.xdf",
            }

        def run(self, *, progress_callback=None, event_callback=None):
            self.run_called = True
            if event_callback:
                event_callback("session_start")
            return SimpleNamespace(
                completed=True,
                interrupted=False,
                summary_text="done",
                session_dir=self.package.session_dir,
                events_csv=self.package.session_dir / "events.csv",
                events_xdf=self.package.session_dir / "events.xdf",
                lsl_markers_csv=None,
                lsl_markers_xdf=None,
                trigger_dictionary_path=None,
                session_metadata_path=None,
                recording_paths=[],
                warnings=[],
                capture_options={"write_analysis_csvs": False},
            )

    monkeypatch.setattr(focus_app, "SessionRunnerController", FakeController)
    window = focus_app.FocusModeWindow(q, package)
    window.dialog.show()
    app.processEvents()

    _fill_required_setup(window)
    QTest.mouseClick(window.setup_submit_button, q["Qt"].MouseButton.LeftButton)
    app.processEvents()

    assert len(created) == 1
    assert created[0].capture_options.external_labrecorder_scope == "session_group_same_window"
    assert created[0].kwargs["lsl_stream_session_id"] == package.session_group_id
    assert created[0].kwargs["external_labrecorder_stop_on_run_end"] is False
    assert window.start_button.text() == "Start Part 01"

    QTest.mouseClick(window.start_button, q["Qt"].MouseButton.LeftButton)
    window.thread.join(timeout=2)
    window._drain()
    app.processEvents()

    assert created[0].run_called is True
    assert "Part 02 loaded" in window.event_label.text()
    assert len(created) == 2
    assert Path(window.package.manifest_path) == part2_manifest
    assert window.package.part_number == 2
    assert window.selected_part_key == "2"
    assert window.start_button.text() == "Start Part 02"
    assert window.start_button.isEnabled()
    assert created[1].capture_options.external_labrecorder_scope == "session_group_same_window"
    assert created[1].kwargs["shared_lsl_outlet"] is shared_lsl
    assert created[1].kwargs["external_labrecorder_state"]["lsl_outlet"] is shared_lsl
    assert created[1].kwargs["external_labrecorder_stop_on_run_end"] is True
    assert str(created[1].kwargs["external_labrecorder_finalize_path"]).endswith(
        f"{package.session_group_id}_external_labrecorder.xdf"
    )

    QTest.mouseClick(window.start_button, q["Qt"].MouseButton.LeftButton)
    window.thread.join(timeout=2)
    window._drain()
    app.processEvents()

    assert created[1].run_called is True
    window.dialog.close()


def test_focus_mode_setup_submit_prepares_controller_before_start(tmp_path: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))
    created: list[dict[str, object]] = []

    class FakeController:
        def __init__(self, package_obj, *, capture_options=None, runner_metadata=None, enable_topup=False, **_kwargs):
            self.package = package_obj
            self.capture_options = capture_options
            self.runner_metadata = dict(runner_metadata or {})
            self.enable_topup = enable_topup
            self.topup_approval_callback = _kwargs.get("topup_approval_callback")
            self.audio_engine = None
            created.append(
                {
                    "runner_metadata": self.runner_metadata,
                    "enable_topup": bool(enable_topup),
                    "topup_approval_callback": self.topup_approval_callback,
                }
            )

    window = focus_app.FocusModeWindow(
        q,
        package,
        capture_options=SessionCaptureOptions(enable_lsl=False, start_backup_recording=False),
        controller_factory=FakeController,
    )
    window.dialog.show()
    app.processEvents()

    assert not window.start_button.isEnabled()
    assert window.mode_tabs.currentIndex() == window.data_logging_tab_index
    assert window.mode_tabs.isTabEnabled(window.experiment_control_tab_index)
    assert window.start() is None
    assert not created

    _fill_required_setup(window)
    QTest.mouseClick(window.setup_submit_button, q["Qt"].MouseButton.LeftButton)
    app.processEvents()

    assert created and created[0]["runner_metadata"]["participant_name"] == "Mock Participant"
    assert created[0]["enable_topup"] is True
    callback = created[0]["topup_approval_callback"]
    assert callable(callback)
    assert callback({"missed_trial_count": 1, "topup_trial_count": 1, "filler_trial_count": 0}) is True
    assert window.pending_topup_approval_request is None
    assert window.validation_topup_approval_records[-1]["mode"] == "setup_checkbox_auto_play"
    assert window.demographics_submitted
    assert window.controller is not None
    assert window.start_button.isEnabled()
    assert window.mode_tabs.isTabEnabled(window.experiment_control_tab_index)
    assert window.mode_tabs.currentIndex() == window.experiment_control_tab_index
    assert not window.participant_name_input.isEnabled()
    assert not window.setup_submit_button.isEnabled()
    window.dialog.close()


def test_focus_mode_companion_setup_and_commands_use_existing_ui_paths(tmp_path: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))
    created: list[dict[str, object]] = []
    controllers: list[object] = []

    class FakeController:
        def __init__(self, package_obj, *, capture_options=None, runner_metadata=None, **_kwargs):
            self.package = package_obj
            self.capture_options = capture_options
            self.runner_metadata = dict(runner_metadata or {})
            self.audio_engine = None
            self.calls: list[str] = []
            created.append(self.runner_metadata)
            controllers.append(self)

        def pause(self) -> None:
            self.calls.append("pause")

        def resume(self) -> None:
            self.calls.append("resume")

    window = focus_app.FocusModeWindow(
        q,
        package,
        capture_options=SessionCaptureOptions(enable_lsl=False, start_backup_recording=False),
        controller_factory=FakeController,
        companion_enabled=False,
    )
    window.dialog.show()
    app.processEvents()

    snapshot = window._companion_submit_setup(
        {
            "participant_code": "P001",
            "participant_name": "Phone Participant",
            "age": "31",
            "handedness": "left",
            "gender": "prefer_not_to_say",
            "name_sharing_opt_in": True,
        }
    )

    assert snapshot["setup"]["submitted"] is True
    assert created[-1]["participant_name"] == "Phone Participant"
    assert created[-1]["include_name_in_lsl"] is True
    ledger = json.loads(focus_app.participant_ledger_path(tmp_path).read_text(encoding="utf-8"))
    assert ledger["participants"]["P001"]["participant_name"] == "Phone Participant"
    assert ledger["participants"]["P001"]["include_name_in_lsl"] is True
    assert "start_part_1" in snapshot["allowed_commands"]

    starts: list[str] = []
    window.start = lambda: starts.append("start")  # type: ignore[method-assign]
    start_snapshot = window._companion_start_part(1)
    assert starts == ["start"]
    assert start_snapshot["schema"] == focus_app.SNAPSHOT_SCHEMA

    window._run_active = True
    window.controller = controllers[-1]
    window.pause_button.setEnabled(True)
    window.resume_button.setEnabled(False)
    pause_snapshot = window._companion_set_paused(True)
    assert controllers[-1].calls == ["pause"]
    assert pause_snapshot["run_status"]["paused"] is True
    assert window.pause_button.isEnabled() is False
    assert window.resume_button.isEnabled() is True
    assert "resume" in pause_snapshot["allowed_commands"]
    resume_snapshot = window._companion_set_paused(False)
    assert controllers[-1].calls == ["pause", "resume"]
    assert resume_snapshot["run_status"]["paused"] is False
    assert window.pause_button.isEnabled() is True
    assert window.resume_button.isEnabled() is False
    assert "pause" in resume_snapshot["allowed_commands"]

    gate = {"context": {"instruction_label": "Gate", "button_label": "Continue"}, "approved": False, "event": threading.Event()}
    window.pending_instruction_request = gate
    continue_snapshot = window._companion_continue_instruction()
    assert gate["approved"] is True
    assert gate["event"].is_set()
    assert window.pending_instruction_request is None
    assert continue_snapshot["instruction_gate"]["waiting"] is False
    window.result = SimpleNamespace(completed=True)
    assert window._companion_snapshot()["allowed_commands"] == []
    window.dialog.close()


def test_focus_mode_companion_tab_shows_pairing_qr(tmp_path: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))

    window = focus_app.FocusModeWindow(
        q,
        package,
        capture_options=SessionCaptureOptions(enable_lsl=False, start_backup_recording=False),
        companion_advertise_ip="10.0.2.2",
    )
    window.dialog.show()
    app.processEvents()

    assert window.mode_tabs.tabText(window.companion_tab_index) == "Companion Android App (Experimental)"
    window.mode_tabs.setCurrentIndex(window.companion_tab_index)
    app.processEvents()

    assert window.mode_tabs.currentIndex() == window.companion_tab_index
    qr_label = window.companion_panel.findChild(q["QLabel"], "companionQrCode")
    assert qr_label is not None
    pixmap = qr_label.pixmap()
    assert pixmap is not None and not pixmap.isNull()
    uri_field = window.companion_panel.findChild(q["QLineEdit"], "companionPairingUriField")
    assert uri_field is not None
    assert uri_field.text().startswith("pps-companion://pair?")
    assert "host=10.0.2.2" in uri_field.text()
    window.dialog.close()


def test_focus_mode_participant_setup_ledger_restores_submitted_fields(tmp_path: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))

    class FakeController:
        def __init__(self, package_obj, *, capture_options=None, runner_metadata=None, **_kwargs):
            self.package = package_obj
            self.capture_options = capture_options
            self.runner_metadata = dict(runner_metadata or {})
            self.audio_engine = None

    window = focus_app.FocusModeWindow(
        q,
        package,
        capture_options=SessionCaptureOptions(enable_lsl=False, start_backup_recording=False),
        controller_factory=FakeController,
    )
    window.dialog.show()
    app.processEvents()

    assert "setup not saved" in window.participant_status_summary_label.text()
    window.participant_name_input.setText("Ledger Participant")
    window.age_input.setText("34")
    assert _set_combo_for_test(window.handedness_combo, "right")
    assert _set_combo_for_test(window.gender_combo, "male")
    window.include_name_lsl_checkbox.setChecked(True)

    assert window._submit_participant_setup()

    ledger_path = focus_app.participant_ledger_path(tmp_path)
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    entry = ledger["participants"]["P001"]
    assert entry["participant_name"] == "Ledger Participant"
    assert entry["age_years"] == "34"
    assert entry["handedness"] == "right"
    assert entry["gender"] == "male"
    assert entry["include_name_in_lsl"] is True
    assert "setup saved" in window.participant_status_summary_label.text()
    window.dialog.close()

    restored = focus_app.FocusModeWindow(
        q,
        package,
        capture_options=SessionCaptureOptions(enable_lsl=False, start_backup_recording=False),
        controller_factory=FakeController,
    )
    restored.dialog.show()
    app.processEvents()

    assert restored.participant_name_input.text() == "Ledger Participant"
    assert restored.age_input.text() == "34"
    assert restored.handedness_combo.currentData() == "right"
    assert restored.gender_combo.currentData() == "male"
    assert restored.include_name_lsl_checkbox.isChecked()
    assert "P001: setup saved; tactile threshold not calibrated; data not collected" in restored.participant_status_summary_label.text()
    restored.dialog.close()


def test_focus_mode_split_part_labels_history_defaults_and_counterbalanced_restore(tmp_path: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
        from peripersonal_space_toolkit.session_runner import prepare_segment_run_package
        from test_session_runner import _two_part_segment_run_setup_fixture
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    run_manifest = _two_part_segment_run_setup_fixture(tmp_path)
    session_root = tmp_path / "sessions"
    package_p001 = prepare_segment_run_package(run_manifest, "P001", session_root=session_root)
    package_p002 = prepare_segment_run_package(run_manifest, "P002", session_root=session_root)
    created: list[dict[str, object]] = []

    class FakeController:
        def __init__(self, package_obj, *, capture_options=None, runner_metadata=None, **_kwargs):
            self.package = package_obj
            self.capture_options = capture_options
            self.runner_metadata = dict(runner_metadata or {})
            self.audio_engine = None
            created.append(self.runner_metadata)

    def combo_items(combo) -> set[str]:
        return {combo.itemText(index) for index in range(combo.count()) if combo.itemText(index)}

    first = focus_app.FocusModeWindow(
        q,
        package_p001,
        capture_options=SessionCaptureOptions(enable_lsl=False, start_backup_recording=False),
        controller_factory=FakeController,
    )
    first.dialog.show()
    app.processEvents()

    assert first.part1_label_combo.isVisible()
    assert first.part2_label_combo.isVisible()
    assert first.part1_label_combo.isEditable()
    assert first.part2_label_combo.isEditable()
    _fill_required_setup(first)
    first.part1_label_combo.setEditText("Pre")
    first.part2_label_combo.setEditText("Post")
    QTest.mouseClick(first.setup_submit_button, q["Qt"].MouseButton.LeftButton)
    app.processEvents()

    assert created[-1]["part_labels"] == {"1": "Pre", "2": "Post"}
    assert created[-1]["part_label"] == "Pre"
    history = json.loads(focus_app.part_label_history_path(session_root).read_text(encoding="utf-8"))
    record = next(iter(history["experiments"].values()))
    assert record["last_pair"] == {"1": "Pre", "2": "Post"}
    assert set(record["labels"]) == {"Pre", "Post"}
    first.dialog.close()

    second = focus_app.FocusModeWindow(
        q,
        package_p002,
        capture_options=SessionCaptureOptions(enable_lsl=False, start_backup_recording=False),
        controller_factory=FakeController,
    )
    second.dialog.show()
    app.processEvents()

    assert second.part1_label_combo.currentText() == "Pre"
    assert second.part2_label_combo.currentText() == "Post"
    assert combo_items(second.part1_label_combo) == {"Pre", "Post"}
    _fill_required_setup(second)
    second.part1_label_combo.setEditText("Post")
    second.part2_label_combo.setEditText("Pre")
    QTest.mouseClick(second.setup_submit_button, q["Qt"].MouseButton.LeftButton)
    app.processEvents()

    assert created[-1]["part_labels"] == {"1": "Post", "2": "Pre"}
    assert created[-1]["part_label"] == "Post"
    second.dialog.close()

    restored = focus_app.FocusModeWindow(
        q,
        package_p001,
        capture_options=SessionCaptureOptions(enable_lsl=False, start_backup_recording=False),
        controller_factory=FakeController,
    )
    restored.dialog.show()
    app.processEvents()

    assert restored.part1_label_combo.currentText() == "Pre"
    assert restored.part2_label_combo.currentText() == "Post"
    assert combo_items(restored.part2_label_combo) == {"Pre", "Post"}
    setup_snapshot = restored._companion_snapshot()["setup"]
    assert setup_snapshot["part_labels"] == {"1": "Pre", "2": "Post"}
    assert set(setup_snapshot["part_label_options"]) == {"Pre", "Post"}
    assert setup_snapshot["part_label_controls_visible"] is True
    ledger = json.loads(focus_app.participant_ledger_path(session_root).read_text(encoding="utf-8"))
    assert ledger["participants"]["P001"]["part_labels"] == {"1": "Pre", "2": "Post"}
    assert ledger["participants"]["P002"]["part_labels"] == {"1": "Post", "2": "Pre"}
    assert ledger["participants"]["P001"]["run_setup_sha256"]
    restored.dialog.close()


def test_focus_mode_loads_participant_tactile_calibration_into_output_field(tmp_path: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
        from peripersonal_space_toolkit.tactile_calibration.persistence import save_calibration_attempt
    except Exception as exc:  # pragma: no cover - depends on optional GUI smoke dependencies
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))
    save_calibration_attempt(
        output_root=tmp_path,
        participant_id="P001",
        timestamp="20260626_130000",
        report={
            "schema": CALIBRATION_SCHEMA,
            "participant_id": "P001",
            "created_at": "2026-06-26T13:00:00",
            "protocol": PROTOCOL_NAME,
            "accepted": True,
            "status": "accepted",
            "final_output_34_percent": 42.5,
            "detection_threshold_output_34_percent": 42.5,
            "recommended_output_34_percent": 42.5,
            "validation_hit_rate": 1.0,
            "validation_false_alarm_rate": 0.0,
        },
        trials=[],
    )

    created: list[dict[str, object]] = []

    class FakeController:
        def __init__(self, package_obj, *, runner_metadata=None, **_kwargs):
            self.package = package_obj
            self.runner_metadata = dict(runner_metadata or {})
            self.audio_engine = None
            created.append(self.runner_metadata)

    window = focus_app.FocusModeWindow(
        q,
        package,
        capture_options=SessionCaptureOptions(enable_lsl=False, start_backup_recording=False),
        controller_factory=FakeController,
    )
    window.dialog.show()
    app.processEvents()

    assert window.output_34_volume_percent == pytest.approx(0.5)
    assert window.output_34_volume_percent_box.value() == pytest.approx(0.5)
    assert "tactile threshold 0.5%" in window.participant_status_summary_label.text()
    metadata = window._runner_metadata()
    assert metadata["tactile_calibration"]["final_output_34_percent"] == pytest.approx(0.5)
    assert metadata["tactile_calibration"]["recommended_output_34_percent"] == pytest.approx(0.5)
    assert metadata["tactile_calibration"]["max_output_34_percent"] == pytest.approx(0.5)

    _fill_required_setup(window)
    assert window._submit_participant_setup()
    assert created[-1]["tactile_calibration"]["final_output_34_percent"] == pytest.approx(0.5)
    assert window.tactile_calibration_button.isEnabled()
    window.dialog.close()


def test_focus_mode_calibration_clicks_do_not_reach_trial_response_logger(tmp_path: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI smoke dependencies
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))

    class FakeController:
        def __init__(self):
            self.logged = []

        def log_click(self, **payload):
            self.logged.append(payload)

    window = focus_app.FocusModeWindow(
        q,
        package,
        capture_options=SessionCaptureOptions(enable_lsl=False, start_backup_recording=False),
    )
    window.dialog.show()
    app.processEvents()

    fake_controller = FakeController()
    window.controller = fake_controller
    now = time.perf_counter()
    window._tactile_calibration_active = True
    window._tactile_calibration_collector.start_trial(
        trial_index=1,
        phase="staircase",
        level_percent=35.0,
        is_catch=False,
        estimated_onset_perf=now - 0.2,
        valid_start_perf=now - 0.1,
        valid_end_perf=now + 1.0,
    )
    window._click()

    response = window._tactile_calibration_collector.wait_for_response(until_perf=now + 0.1)
    assert response is not None
    assert fake_controller.logged == []

    now = time.perf_counter()
    window._tactile_calibration_collector.start_trial(
        trial_index=2,
        phase="staircase",
        level_percent=35.0,
        is_catch=False,
        estimated_onset_perf=now - 0.2,
        valid_start_perf=now - 0.1,
        valid_end_perf=now + 1.0,
    )
    window._handle_global_response_mouse_click(123, 456)

    global_response = window._tactile_calibration_collector.wait_for_response(until_perf=now + 0.1)
    assert global_response is not None
    assert fake_controller.logged == []
    window.dialog.close()


def test_focus_mode_calibrate_tactile_button_click_saves_and_applies_value(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from PIL import Image, ImageStat
        from peripersonal_space_toolkit import focus_app
        from peripersonal_space_toolkit.tactile_calibration.persistence import load_latest_calibration
    except Exception as exc:  # pragma: no cover - depends on optional GUI smoke dependencies
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    class FakeCalibrationRunner:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run(self):
            return {
                "report": {
                    "schema": CALIBRATION_SCHEMA,
                    "participant_id": self.kwargs["participant_id"],
                    "created_at": "2026-06-26T15:00:00",
                    "completed_at": "2026-06-26T15:00:02",
                    "protocol": PROTOCOL_NAME,
                    "accepted": True,
                    "status": "accepted",
                    "message": "Accepted confirmed tactile task level at Output 3/4 0.36%.",
                    "threshold_method": "two_down_one_up_transformed_adaptive_staircase_with_catches",
                    "final_output_34_percent": 0.36,
                    "detection_threshold_output_34_percent": 0.35,
                    "recommended_output_34_percent": 0.36,
                    "confirmation_level_output_34_percent": 0.36,
                    "timing": {
                        "valid_response_start_ms": VALID_RESPONSE_START_MS,
                        "valid_response_end_ms": VALID_RESPONSE_END_MS,
                    },
                    "adaptive_staircase": {
                        "target_detection_rate": 0.7071067811865476,
                        "down_after_hits": 2,
                        "up_after_misses": 1,
                        "stop_reversals": 6,
                        "reversals_to_average": 4,
                        "minimum_catch_trials": 3,
                        "max_false_alarms": 3,
                    },
                    "confirmation_criteria": {
                        "required_consecutive_hits": CONFIRMATION_REQUIRED_CONSECUTIVE_HITS,
                        "required_clean_catches": CONFIRMATION_REQUIRED_CLEAN_CATCHES,
                        "level_increment_percent": 0.01,
                        "max_false_alarms": 3,
                    },
                    "staircase_summary": {
                        "target_detection_rate": 0.7071067811865476,
                        "hits": 14,
                        "misses": 6,
                        "signal_trials": 20,
                        "false_alarms": 0,
                        "catch_trials": 3,
                        "reversals": 6,
                        "reversal_levels_percent": [0.5, 0.35, 0.25, 0.35, 0.25, 0.35],
                        "reversal_levels_used_percent": [0.25, 0.35, 0.25, 0.35],
                        "hit_rate": 0.7,
                        "false_alarm_rate": 0.0,
                    },
                    "confirmation_summary": {
                        "hits": 10,
                        "misses": 1,
                        "signal_trials": 11,
                        "false_alarms": 0,
                        "catch_trials": 5,
                        "clean_catches": 5,
                        "consecutive_hits": 10,
                        "hit_rate": 10 / 11,
                        "false_alarm_rate": 0.0,
                        "confirmed_output_34_percent": 0.36,
                        "passed": True,
                    },
                    "staircase_hit_rate": 0.7,
                    "confirmation_hit_rate": 10 / 11,
                    "validation_hit_rate": 10 / 11,
                    "validation_false_alarm_rate": 0.0,
                },
                "trials": [
                    {
                        "trial_index": 1,
                        "phase": "staircase",
                        "level_percent": 0.35,
                        "staircase_index": 5,
                        "staircase_direction": "down",
                        "is_catch": False,
                        "valid_response": True,
                        "trial_outcome": "hit",
                    }
                ],
            }

    monkeypatch.setattr(focus_app, "TactileCalibrationRunner", FakeCalibrationRunner)

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))
    window = focus_app.FocusModeWindow(
        q,
        package,
        capture_options=SessionCaptureOptions(enable_lsl=False, start_backup_recording=False),
    )
    window._output_test_engine = lambda: object()
    window.dialog.show()
    app.processEvents()

    _fill_required_setup(window)
    assert window._submit_participant_setup()
    app.processEvents()
    assert window.mode_tabs.currentIndex() == window.experiment_control_tab_index
    assert window.start_button.isEnabled()
    assert window.tactile_calibration_button.isEnabled()
    QTest.mouseClick(window.tactile_calibration_button, q["Qt"].MouseButton.LeftButton)
    deadline = time.time() + 2.0
    while time.time() < deadline and window._tactile_calibration_active:
        app.processEvents()
        window._drain()
        time.sleep(0.01)
    app.processEvents()
    window._drain()

    assert not window._tactile_calibration_active
    assert window.output_34_volume_percent == pytest.approx(0.36)
    assert window.tactile_calibration_monitor_dialog is not None
    assert window.tactile_calibration_monitor_dialog.isVisible()
    assert window.tactile_calibration_monitor_dialog.close_button.isEnabled()
    assert window.tactile_calibration_monitor_dialog.close_button.text() == "Continue"
    assert "Calibration yielded a value" in window.tactile_calibration_monitor_dialog.status_label.text()
    assert "0.360%" in window.tactile_calibration_monitor_dialog.status_label.text()
    assert "Final hits: 10/10" in window.tactile_calibration_monitor_dialog.confirmation_hits_label.text()
    assert "Clean catches: 5/5" in window.tactile_calibration_monitor_dialog.confirmation_catches_label.text()
    screenshot = tmp_path / "tactile_calibration_monitor.png"
    assert window.tactile_calibration_monitor_dialog.grab().save(str(screenshot))
    image = Image.open(screenshot).convert("RGB")
    assert max(ImageStat.Stat(image).stddev) > 0.0
    deadline = time.time() + 3.0
    while time.time() < deadline:
        app.processEvents()
        window._drain()
        time.sleep(0.01)
    app.processEvents()
    assert window.tactile_calibration_monitor_dialog is not None
    QTest.mouseClick(window.tactile_calibration_monitor_dialog.close_button, q["Qt"].MouseButton.LeftButton)
    app.processEvents()
    assert window.tactile_calibration_monitor_dialog is None
    assert window.mode_tabs.currentIndex() == window.experiment_control_tab_index
    assert window.start_button.isEnabled()
    latest = load_latest_calibration(tmp_path, "P001")
    assert latest is not None
    assert latest["final_output_34_percent"] == pytest.approx(0.36)
    assert latest["recommended_output_34_percent"] == pytest.approx(0.36)
    assert latest["detection_threshold_output_34_percent"] == pytest.approx(0.35)
    assert "tactile calibration successful" in window.event_label.text()
    assert "Ready to start" in window.event_label.text()
    window.dialog.close()


def test_tactile_calibration_monitor_catch_false_alarm_shows_red_warning(monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication, QDialog
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI smoke dependencies
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    owner_dialog = QDialog()
    returned: list[bool] = []
    owner = SimpleNamespace(
        dialog=owner_dialog,
        _record_tactile_calibration_target_click=lambda _source: None,
        _abort_tactile_calibration=lambda: None,
        _return_from_successful_tactile_calibration=lambda: returned.append(True),
    )
    monitor = focus_app._create_tactile_calibration_monitor_dialog(q, owner, "P001")
    monitor.show()
    app.processEvents()
    monitor.update_progress(
        {
            "trial_index": 1,
            "phase": "confirmation",
            "level_percent": 0.35,
            "is_catch": True,
            "max_calibration_events": 120,
        }
    )
    monitor.finish_trial(
        {
            "trial_index": 1,
            "phase": "confirmation",
            "level_percent": 0.35,
            "is_catch": True,
            "response_present": True,
            "valid_response": True,
            "trial_outcome": "false_alarm",
            "warning": "Only press when you feel the tactile pulse.",
            "confirmation_consecutive_hits": 3,
            "confirmation_clean_catches": 0,
        }
    )
    app.processEvents()

    assert monitor.warning_label.isVisible()
    assert monitor.warning_label.text() == "Only press when you feel the tactile pulse."
    assert "#b3261e" in monitor.target_panel.styleSheet()
    assert "Clean catches: 0/5" in monitor.confirmation_catches_label.text()
    monitor.close()
    owner_dialog.close()


def test_focus_mode_output_volume_sliders_persist_and_apply_to_engine(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    state_root = tmp_path / "dashboard_state"
    monkeypatch.setattr(focus_app, "DEFAULT_DASHBOARD_STATE_ROOT", state_root)
    focus_app._persist_output_channel_volumes(72, 0.125, state_root=state_root)

    class FakeEngine:
        def __init__(self) -> None:
            self.audio_volume = 1.0
            self.tactile_volume = 1.0

        def set_main_volume(self, value: float) -> None:
            self.audio_volume = float(value)

    class FakeController:
        def __init__(self, package_obj, *, capture_options=None, runner_metadata=None, **_kwargs):
            self.package = package_obj
            self.capture_options = capture_options
            self.runner_metadata = dict(runner_metadata or {})
            self.audio_engine = FakeEngine()

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))
    window = focus_app.FocusModeWindow(
        q,
        package,
        capture_options=SessionCaptureOptions(enable_lsl=False, start_backup_recording=False),
        controller_factory=FakeController,
    )
    window.dialog.show()
    app.processEvents()

    assert window.output_12_volume_slider.value() == 72_000
    assert window.output_34_volume_slider.value() == 125
    assert window.output_12_volume_percent_box.value() == pytest.approx(72)
    assert window.output_34_volume_percent_box.value() == pytest.approx(0.125)
    _fill_required_setup(window)
    assert window._submit_participant_setup()
    assert window.controller is not None
    engine = window.controller.audio_engine
    assert engine.audio_volume == pytest.approx(0.72)
    assert engine.tactile_volume == pytest.approx(0.00125)
    assert window.output_12_volume_slider.isEnabled()
    assert window.output_34_volume_slider.isEnabled()
    assert window.controller.runner_metadata["playback_output_levels"]["output_1_2_percent"] == 72
    assert window.controller.runner_metadata["playback_output_levels"]["output_3_4_percent"] == pytest.approx(0.125)

    window.output_12_volume_slider.setValue(35_000)
    window.output_34_volume_percent_box.setFocus()
    tactile_volume_edit = window.output_34_volume_percent_box.lineEdit()
    tactile_volume_edit.selectAll()
    QTest.keyClicks(tactile_volume_edit, "0.005")
    QTest.keyClick(tactile_volume_edit, q["Qt"].Key.Key_Enter)
    app.processEvents()

    assert engine.audio_volume == pytest.approx(0.35)
    assert engine.tactile_volume == pytest.approx(0.00005)
    assert window.thread is None
    assert window.output_34_volume_slider.value() == 5
    settings = json.loads((state_root / "focus_runner_settings.v1.json").read_text(encoding="utf-8"))
    assert settings["output_1_2_volume_percent"] == 35
    assert settings["output_3_4_volume_percent"] == pytest.approx(0.005)
    assert settings["output_channel_volumes"]["output_1_2_linear_gain"] == pytest.approx(0.35)
    assert settings["output_channel_volumes"]["output_3_4_linear_gain"] == pytest.approx(0.00005)
    window.dialog.close()


def test_focus_mode_adaptive_threshold_progress_updates_live_output_without_saving_calibration(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    state_root = tmp_path / "dashboard_state"
    monkeypatch.setattr(focus_app, "DEFAULT_DASHBOARD_STATE_ROOT", state_root)
    focus_app._persist_output_channel_volumes(72, 0.35, state_root=state_root)

    class FakeEngine:
        def __init__(self) -> None:
            self.audio_volume = 1.0
            self.tactile_volume = 1.0

        def set_main_volume(self, value: float) -> None:
            self.audio_volume = float(value)

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))
    window = focus_app.FocusModeWindow(
        q,
        package,
        capture_options=SessionCaptureOptions(enable_lsl=False, start_backup_recording=False),
    )
    engine = FakeEngine()
    window.controller = SimpleNamespace(audio_engine=engine)
    window._latest_tactile_calibration = {
        "participant_id": "P001",
        "recommended_output_34_percent": 0.35,
        "final_output_34_percent": 0.35,
    }
    window.dialog.show()
    app.processEvents()

    window._handle_tactile_threshold_adapted(
        {
            "ui_event": "tactile_threshold_adapted",
            "old_output_34_percent": 0.35,
            "new_output_34_percent": 0.36,
            "triggering_miss_count": 2,
            "message": "Tactile threshold nudged to Output 3/4 0.36% after 2 tactile misses.",
        }
    )
    app.processEvents()

    assert window.output_34_volume_percent == pytest.approx(0.36)
    assert window.output_34_volume_percent_box.value() == pytest.approx(0.36)
    assert engine.tactile_volume == pytest.approx(0.0036)
    assert window._latest_tactile_calibration["recommended_output_34_percent"] == pytest.approx(0.35)
    settings = json.loads((state_root / "focus_runner_settings.v1.json").read_text(encoding="utf-8"))
    assert settings["output_3_4_volume_percent"] == pytest.approx(0.35)
    assert "0.36%" in window.event_label.text()
    window.dialog.close()


def test_focus_mode_output_test_buttons_use_standard_assets_and_current_gains(tmp_path: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    class FakeEngine:
        def __init__(self) -> None:
            self.audio_volume = 1.0
            self.tactile_volume = 1.0
            self.instruction_paths: list[str] = []
            self.block_paths: list[str] = []

        def set_main_volume(self, value: float) -> None:
            self.audio_volume = float(value)

        def play_instruction(self, path: str, done=None) -> bool:
            self.instruction_paths.append(path)
            if done is not None:
                done(True)
            return True

        def play_block(self, path: str) -> bool:
            self.block_paths.append(path)
            return True

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))
    window = focus_app.FocusModeWindow(
        q,
        package,
        capture_options=SessionCaptureOptions(enable_lsl=False, start_backup_recording=False),
    )
    engine = FakeEngine()
    window._create_real_audio_engine_on_ui_thread = lambda: engine
    window.dialog.show()
    app.processEvents()

    assert not window.test_audio_button.isEnabled()
    assert not window.test_tactile_button.isEnabled()
    _fill_required_setup(window)
    assert window._submit_participant_setup()
    assert window.test_audio_button.isEnabled()
    assert window.test_tactile_button.isEnabled()

    window.output_12_volume_percent_box.setValue(41)
    window.output_34_volume_percent_box.setValue(23)
    assert window.output_34_volume_percent_box.value() == pytest.approx(0.5)
    QTest.mouseClick(window.test_audio_button, q["Qt"].MouseButton.LeftButton)
    app.processEvents()
    window._drain()

    assert engine.instruction_paths == [str(focus_app.OUTPUT_TEST_AUDIO_PATH)]
    assert engine.audio_volume == pytest.approx(0.41)
    assert engine.tactile_volume == pytest.approx(0.005)
    assert window.test_audio_button.isEnabled()
    assert "Test Audio complete" in window.event_label.text()

    QTest.mouseClick(window.test_tactile_button, q["Qt"].MouseButton.LeftButton)
    for _ in range(25):
        app.processEvents()
        window._drain()
        if engine.block_paths:
            break
        time.sleep(0.01)
    window._drain()

    assert engine.block_paths == [str(focus_app.OUTPUT_TEST_TACTILE_PATH)]
    assert window.test_tactile_button.isEnabled()
    assert "Test Tactile complete" in window.event_label.text()
    window._run_active = True
    assert not window._run_output_test("audio")
    assert "before playback starts" in window.event_label.text()
    window.dialog.close()


def test_runner_output_test_assets_match_expected_routes_and_levels():
    from peripersonal_space_toolkit import focus_app

    audio, audio_sr = sf.read(focus_app.OUTPUT_TEST_AUDIO_PATH, dtype="float32", always_2d=True)
    audio_arr = audio if audio.ndim > 1 else audio[:, None]
    tactile, tactile_sr = sf.read(focus_app.OUTPUT_TEST_TACTILE_PATH, dtype="float32")

    repo = Path(__file__).resolve().parents[1]
    expected_rel = Path("assets") / "preloads" / focus_app.STUDY5_PROFILE_ID / "02_looming_stimuli" / "looming_Pink_frontal.wav"
    assert focus_app.OUTPUT_TEST_AUDIO_PATH == repo / expected_rel
    source_manifest = json.loads((repo / expected_rel.parent / "stimulus_sources.json").read_text(encoding="utf-8"))
    source_entry = next(asset for asset in source_manifest["assets"] if asset["label"] == "Pink frontal")
    assert Path(str(source_entry["path"])) == expected_rel
    assert source_entry["source_profile"] == "dynaspace_gaussian_burst_train"
    source_params = source_entry["source_profile_parameters"]
    assert source_params["burst_count_mode"] == "duration_derived"
    assert source_params["target_period_s"] == pytest.approx(0.095)
    assert source_params["burst_duration_s"] == pytest.approx(0.030)

    assert audio_sr == 44100
    assert audio_arr.shape[1] == 2
    assert audio_arr.shape[0] / audio_sr == pytest.approx(4.0)
    assert float(np.max(np.abs(audio_arr))) <= 0.901
    squared_mono = np.mean(np.square(audio_arr), axis=1)
    window = max(1, int(round(0.005 * audio_sr)))
    envelope = np.sqrt(np.convolve(squared_mono, np.ones(window, dtype=np.float32) / window, mode="same"))
    active = envelope > max(1e-5, float(np.max(envelope)) * 0.15)
    assert 0.03 <= float(np.mean(active)) <= 0.20
    raw_starts = np.flatnonzero(np.diff(active.astype(np.int8), prepend=0) == 1)
    burst_starts: list[int] = []
    minimum_gap = int(round(0.040 * audio_sr))
    for start in raw_starts:
        if not burst_starts or int(start) - burst_starts[-1] >= minimum_gap:
            burst_starts.append(int(start))
    assert 25 <= len(burst_starts) <= 40

    assert tactile_sr == 44100
    assert tactile.ndim == 2
    assert tactile.shape[1] == 3
    assert float(np.max(np.abs(tactile[:, :2]))) == pytest.approx(0.0)
    tactile_channel = tactile[:, 2]
    assert float(np.max(np.abs(tactile_channel))) > 0.90
    active = np.flatnonzero(np.abs(tactile_channel) > 0.1)
    assert active.size
    starts = [int(active[0])]
    for sample in active[1:]:
        if int(sample) - starts[-1] > int(0.5 * tactile_sr):
            starts.append(int(sample))
    assert len(starts) == 4
    intervals = np.diff(starts) / tactile_sr
    assert intervals == pytest.approx([1.0, 1.0, 1.0], abs=0.005)


def test_focus_mode_close_click_releases_waits_and_closes_labrecorder(tmp_path: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    class FakeController:
        def __init__(self) -> None:
            self.stop_called = False
            self.close_calls: list[float] = []
            self.events = SimpleNamespace(close=lambda: None)

        def stop(self) -> None:
            self.stop_called = True

        def close_external_labrecorder_for_runner_exit(self, *, timeout_s: float = 2.0) -> None:
            self.close_calls.append(float(timeout_s))

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))
    window = focus_app.FocusModeWindow(
        q,
        package,
        capture_options=SessionCaptureOptions(enable_lsl=False, start_backup_recording=False),
    )
    controller = FakeController()
    window.controller = controller
    instruction_event = threading.Event()
    topup_event = threading.Event()
    window.pending_instruction_request = {"approved": True, "event": instruction_event}
    window.pending_topup_approval_request = {"approved": True, "event": topup_event}
    window.dialog.show()
    app.processEvents()
    window._set_experiment_control_tab_ready(True, switch=True)
    app.processEvents()

    QTest.keyClick(window.dialog, q["Qt"].Key.Key_W, q["Qt"].KeyboardModifier.ControlModifier)
    app.processEvents()

    assert controller.stop_called is True
    assert controller.close_calls == [2.0]
    assert instruction_event.is_set()
    assert topup_event.is_set()
    assert window.pending_instruction_request is None
    assert window.pending_topup_approval_request is None


def test_focus_mode_participant_dropdown_switches_loaded_package(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    from peripersonal_space_toolkit.tactile_calibration.persistence import save_calibration_attempt

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    run_setup = tmp_path / "6_experiment_run_setup" / "experiment_run_setup_manifest.json"
    run_setup.parent.mkdir(parents=True)
    run_setup.write_text("{}", encoding="utf-8")
    package_p001 = load_run_package(
        _write_minimal_session_manifest(tmp_path, participant_id="P001", source_run_setup_manifest_path=run_setup)
    )
    package_p002 = load_run_package(
        _write_minimal_session_manifest(tmp_path, participant_id="P002", source_run_setup_manifest_path=run_setup)
    )
    save_calibration_attempt(
        output_root=tmp_path,
        participant_id="P002",
        timestamp="20260626_140000",
        report={
            "schema": CALIBRATION_SCHEMA,
            "participant_id": "P002",
            "created_at": "2026-06-26T14:00:00",
            "protocol": PROTOCOL_NAME,
            "accepted": True,
            "status": "accepted",
                "final_output_34_percent": 0.35,
                "detection_threshold_output_34_percent": 0.35,
                "recommended_output_34_percent": 0.35,
            "validation_hit_rate": 1.0,
            "validation_false_alarm_rate": 0.0,
        },
        trials=[],
    )
    prepared: list[str] = []

    monkeypatch.setattr(focus_app, "segment_run_setup_participants", lambda _path: ["P001", "P002"])
    monkeypatch.setattr(
        focus_app,
        "prepared_session_asset_statuses",
        lambda _path, _participants, **_kwargs: {
            "P001": {
                "participant_id": "P001",
                "generated": True,
                "status": "ready",
                "data_collected": False,
                "message": "Ready.",
            },
            "P002": {
                "participant_id": "P002",
                "generated": True,
                "status": "ready",
                "data_collected": True,
                "data_collection_message": "Completed participant data found.",
                "message": "Ready.",
            },
        },
    )

    def fake_prepare_segment_run_package(run_setup_path, participant_id, **_kwargs):
        assert run_setup_path == run_setup
        prepared.append(participant_id)
        return package_p002

    monkeypatch.setattr(focus_app, "prepare_segment_run_package", fake_prepare_segment_run_package)

    window = focus_app.FocusModeWindow(q, package_p001)
    window.dialog.show()
    app.processEvents()

    combo = window.participant_code_combo
    assert combo.count() == 2
    p002_index = combo.findData("P002")
    assert p002_index >= 0
    assert focus_app.DATA_COLLECTED_MARK in combo.itemText(p002_index)
    assert combo.itemData(p002_index, q["Qt"].ItemDataRole.ForegroundRole) is not None
    assert not window.participant_decrement_button.isEnabled()
    assert window.participant_increment_button.isEnabled()

    QTest.mouseClick(window.participant_increment_button, q["Qt"].MouseButton.LeftButton)
    app.processEvents()

    assert prepared == ["P002"]
    assert window.package.participant_id == "P002"
    assert window._runner_metadata()["participant_code"] == "P002"
    assert window.session_participant_value.text() == "P002"
    assert "P002" in window.dialog.windowTitle()
    assert window.participant_name_input.text() == ""
    assert not window.include_name_lsl_checkbox.isChecked()
    assert window.participant_decrement_button.isEnabled()
    assert not window.participant_increment_button.isEnabled()
    assert window.output_34_volume_percent == pytest.approx(0.35)
    assert "P002: setup not saved; tactile threshold 0.35%; data collected" in window.participant_status_summary_label.text()
    assert window.progress_label.text() == "Waiting to start"
    window.dialog.close()


def test_focus_mode_block_plan_click_previews_trial_composition_and_live_bar(tmp_path: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PIL import Image
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI smoke deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_focus_preview_session_manifest(tmp_path))
    window = focus_app.FocusModeWindow(q, package, enable_missed_trial_topup=True)
    window.dialog.resize(1180, 760)
    window.dialog.show()
    app.processEvents()
    window._set_experiment_control_tab_ready(True, switch=True)
    app.processEvents()

    assert window.selected_part_key == "1"
    assert window.part_buttons["1"].isEnabled()
    assert window.part_buttons["2"].isEnabled()
    assert window.start_part2_button is not None
    assert not window.start_part2_button.isEnabled()
    assert window.preview_display_block_index == 1
    assert [segment.clip_label for segment in window.timeline_preview_state.trial_segments] == ["Inhale", "Exhale"]
    assert [segment.trial_label for segment in window.timeline_preview_state.trial_segments] == ["Audio-tactile", "Baseline"]
    assert [segment.noise_type for segment in window.timeline_preview_state.trial_segments] == ["pink", "white"]
    assert [segment.soa_ms for segment in window.timeline_preview_state.trial_segments] == ["300", "800"]
    assert [segment.label for segment in window.timeline_preview_state.instruction_segments] == ["General", "Pre-block", "Post-block"]
    timeline_debug = window.layout_validation_snapshot()["timeline_debug"]
    assert timeline_debug["row_names"] == list(focus_app.TIMELINE_ROW_NAMES)
    assert timeline_debug["row_count"] == len(focus_app.TIMELINE_ROW_NAMES)
    assert "Instr" not in timeline_debug["row_names"]
    block_strip_entries = window.block_plan_widget._layout_items()
    instruction_entries = [entry for entry in block_strip_entries if entry.get("entry_kind") == "instruction"]
    assert {entry.get("slot") for entry in instruction_entries} >= {
        "before_experiment",
        "before_each_block",
        "after_each_block",
        "between_conditions",
    }
    assert all(int(entry["width"]) <= 13 for entry in instruction_entries)
    legend_entries = window.instruction_legend_widget._layout_items()
    assert [entry.get("slot") for entry in legend_entries] == [
        "before_experiment",
        "before_each_block",
        "after_each_block",
        "between_conditions",
        "after_experiment",
    ]

    QTest.mouseClick(
        window.block_plan_widget,
        q["Qt"].MouseButton.LeftButton,
        q["Qt"].KeyboardModifier.NoModifier,
        window.block_plan_widget.item_center(1),
    )
    app.processEvents()

    assert window.selected_display_block_index == 1
    assert window.preview_display_block_index == 1
    assert window._timeline_display_state() is window.timeline_preview_state
    assert [segment.clip_label for segment in window.timeline_preview_state.trial_segments] == ["Inhale", "Exhale"]
    assert [segment.trial_label for segment in window.timeline_preview_state.trial_segments] == ["Audio-tactile", "Baseline"]
    assert [segment.noise_type for segment in window.timeline_preview_state.trial_segments] == ["pink", "white"]
    assert [segment.soa_ms for segment in window.timeline_preview_state.trial_segments] == ["300", "800"]
    assert [cue.noise_type for cue in window.timeline_preview_state.cues] == ["pink", "white"]
    assert [cue.soa_ms for cue in window.timeline_preview_state.cues] == ["300", "800"]
    assert "Block preview: Block 1 | 2 trials | 2 tactile cues" in window.block_preview_label.text()

    QTest.mouseClick(
        window.block_plan_widget,
        q["Qt"].MouseButton.LeftButton,
        q["Qt"].KeyboardModifier.NoModifier,
        window.block_plan_widget.item_center(3),
    )
    app.processEvents()

    assert window.selected_display_block_index == 3
    assert window.preview_display_block_index == 3
    assert not window.timeline_preview_state.trial_segments
    assert "top-up" in window.block_preview_label.text()

    window._handle_topup_draft(
        {
            "ui_event": "topup_draft",
            "missed_trials": [
                {
                    "part_number": "1",
                    "block_number": "1",
                    "trial_number": "2",
                    "trial_uid": "T002",
                    "trial_type": "Baseline",
                    "family": "baseline",
                    "respiratory_phase": "Exhale",
                    "soa_ms": "800",
                }
            ],
        }
    )
    app.processEvents()
    assert len(window._visible_topup_draft_items()) == 1
    assert "1 missed trial(s) in draft" in window.block_preview_label.text()

    QTest.mouseClick(window.part_buttons["2"], q["Qt"].MouseButton.LeftButton)
    app.processEvents()
    assert window.selected_part_key == "2"
    assert [item["part_block_number"] for item in window.block_plan_items] == [1, 2]
    part2_instruction_entries = [entry for entry in window.block_plan_widget._layout_items() if entry.get("entry_kind") == "instruction"]
    assert "after_experiment" in {entry.get("slot") for entry in part2_instruction_entries}
    assert window.preview_display_block_index == 4
    assert "Condition 2" in window.timeline_preview_state.phase_label

    window._handle_block_schedule(
        {
            "part_number": 1,
            "phase_label": "Condition 1",
            "block_index": 1,
            "display_block_index": 1,
            "display_block_count": 3,
            "block_label": "Block 01",
            "duration_s": 16.0,
            "tactile_events": [
                {"trial_number": 1, "trial_uid": "T001", "time_s": 4.3, "soa_ms": "300", "row_label": "Inhale", "noise_type": "pink"},
                {"trial_number": 2, "trial_uid": "T002", "time_s": 8.8, "soa_ms": "800", "row_label": "Exhale", "noise_type": "white"},
            ],
            "trial_segments": [
                {
                    "trial_number": 1,
                    "trial_uid": "T001",
                    "start_s": 0.0,
                    "end_s": 8.0,
                    "clip_label": "Inhale",
                    "trial_label": "Audio-tactile",
                    "noise_type": "pink",
                    "soa_ms": "300",
                },
                {
                    "trial_number": 2,
                    "trial_uid": "T002",
                    "start_s": 8.0,
                    "end_s": 16.0,
                    "clip_label": "Exhale",
                    "trial_label": "Baseline",
                    "noise_type": "white",
                    "soa_ms": "800",
                },
            ],
        }
    )
    window._update_tactile_progress(5.0)
    app.processEvents()

    assert window.preview_display_block_index is None
    assert window.selected_display_block_index == 1
    assert window._timeline_display_state() is window.timeline_state
    assert [segment.noise_type for segment in window.timeline_state.trial_segments] == ["pink", "white"]
    assert [segment.soa_ms for segment in window.timeline_state.trial_segments] == ["300", "800"]
    assert window.progress.value() == int((5.0 / 16.0) * 1000)
    progress_margins = window.progress_track_widget.layout().contentsMargins()
    assert progress_margins.left() == focus_app.TIMELINE_LABEL_WIDTH
    assert progress_margins.right() == focus_app.TIMELINE_RIGHT_MARGIN
    response_click = window.timeline_state.record_click(4.6)
    off_cue_click = window.timeline_state.record_click(8.1)
    assert response_click.response_status == "tactile_response"
    assert off_cue_click.response_status == "off_cue"

    timeline_screenshot = tmp_path / "live_timeline_red_bar.png"
    assert window.tactile_timeline_widget.grab().save(str(timeline_screenshot))
    timeline_image = Image.open(timeline_screenshot).convert("RGB")
    pixels = timeline_image.load()
    red_pixels = sum(
        1
        for y in range(timeline_image.height)
        for x in range(timeline_image.width)
        if pixels[x, y][0] > 150 and pixels[x, y][1] < 70 and pixels[x, y][2] < 70
    )
    assert red_pixels > 60
    timeline_debug = window.tactile_timeline_widget.timeline_debug_snapshot()
    assert timeline_debug["row_names"] == list(focus_app.TIMELINE_ROW_NAMES)
    assert timeline_debug["label_fit"]["drawn"] > 0
    assert timeline_debug["label_fit"]["overlap_count"] == 0
    cue_linked_click_pixels = sum(
        1
        for y in range(timeline_image.height)
        for x in range(timeline_image.width)
        if pixels[x, y][0] < 90 and pixels[x, y][1] > 110 and pixels[x, y][2] < 170
    )
    off_cue_click_pixels = sum(
        1
        for y in range(timeline_image.height)
        for x in range(timeline_image.width)
        if pixels[x, y][0] > 180 and 70 < pixels[x, y][1] < 150 and pixels[x, y][2] < 90
    )
    height = timeline_image.height
    compact_rows = height < 96
    very_compact_rows = height < 84
    top_y = 5 if very_compact_rows else (8 if compact_rows else 14)
    bottom_y = max(top_y + 1, height - (5 if very_compact_rows else (8 if compact_rows else 12)))
    row_index = list(focus_app.TIMELINE_ROW_NAMES).index("Tactile")
    row_gap = (bottom_y - top_y) / max(1, len(focus_app.TIMELINE_ROW_NAMES) - 1)
    tactile_y = int(round(top_y + row_index * row_gap))
    cue_band_click_pixels = sum(
        1
        for y in range(max(0, tactile_y - 5), min(timeline_image.height, tactile_y + 6))
        for x in range(timeline_image.width)
        if (
            (pixels[x, y][0] < 90 and pixels[x, y][1] > 110 and pixels[x, y][2] < 170)
            or (pixels[x, y][0] > 180 and 70 < pixels[x, y][1] < 150 and pixels[x, y][2] < 90)
        )
    )
    assert cue_linked_click_pixels > 8
    assert off_cue_click_pixels > 8
    assert cue_band_click_pixels > 8
    window.dialog.close()


def test_focus_mode_zero_miss_completion_auto_loads_part2_with_finished_sign(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("PPS_FOCUS_DISABLE_ANALYSIS_POPUP", "1")
    try:
        from PIL import Image
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
        from peripersonal_space_toolkit.session_runner import prepare_segment_run_package
        from test_session_runner import _two_part_segment_run_setup_fixture
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    run_manifest = _two_part_segment_run_setup_fixture(tmp_path)
    package = prepare_segment_run_package(
        run_manifest,
        "P001",
        session_root=tmp_path / "sessions",
    )
    window = focus_app.FocusModeWindow(
        q,
        package,
        capture_options=SessionCaptureOptions(
            enable_lsl=False,
            start_backup_recording=False,
            start_external_labrecorder=False,
        ),
        enable_missed_trial_topup=True,
    )
    window.dialog.show()
    app.processEvents()
    _fill_required_setup(window)
    assert window._submit_participant_setup()
    app.processEvents()
    assert window.start_button.text() == "Start Part 01"

    message = "Part 1 data collected. No top-up needed. Part 02 is ready."
    result = SimpleNamespace(
        completed=True,
        interrupted=False,
        summary_text="Run complete.",
        session_dir=package.session_dir,
        events_csv=tmp_path / "events.csv",
        events_xdf=tmp_path / "events.xdf",
        lsl_markers_csv=None,
        lsl_markers_xdf=None,
        trigger_dictionary_path=None,
        session_metadata_path=None,
        recording_paths=[],
        warnings=[],
        capture_options={"write_internal_xdf": True},
        analysis_outputs={},
        topup_summary={
            "topup_outcome": "not_needed",
            "hit_count": 1,
            "missed_needs_topup_count": 0,
            "topup_attempt_count": 0,
        },
        operator_completion_message=message,
    )

    window._handle_topup_completion(
        {
            "ui_event": "topup_completion",
            "topup_outcome": "not_needed",
            "part_number": "1",
            "hit_count": 1,
            "missed_needs_topup_count": 0,
            "topup_attempt_count": 0,
            "operator_completion_message": message,
        }
    )
    app.processEvents()
    assert window.event_label.text() == message
    assert window.run_state_chip.text() == "No Top-Up Needed"

    window._handle_done(result)
    app.processEvents()
    assert "Operator status: Part 1 data collected. No top-up needed." in window.output_summary.toPlainText()
    assert "Top-up: not_needed" in window.output_summary.toPlainText()
    assert "Part 02 loaded for same-window continuation." in window.output_summary.toPlainText()
    assert getattr(window.package, "part_number", None) == 2
    assert window.selected_part_key == "2"
    assert window.start_button.text() == "Start Part 02"
    assert window.start_button.isEnabled()
    assert "No top-up needed" in window.event_label.text()
    assert "Part 02 loaded" in window.event_label.text()
    screenshot = tmp_path / "no_topup_completion_part02_ready.png"
    assert window.dialog.grab().save(str(screenshot))
    image = Image.open(screenshot).convert("RGB")
    pixels = np.asarray(image)
    nonblank_pixels = int(np.sum(np.any(pixels != 255, axis=2)))
    assert nonblank_pixels > 1000
    window.timer.stop()
    window.dialog.close()
    app.processEvents()


@pytest.mark.parametrize("available_width,available_height", [(1024, 600), (1366, 768), (1920, 1080)])
def test_focus_mode_shell_layout_profile_keeps_controls_visible(tmp_path: Path, available_width: int, available_height: int):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))
    profile = render_focus_layout_profile(available_width, available_height)
    window = focus_app.FocusModeWindow(
        q,
        package,
        capture_options=SessionCaptureOptions(
            enable_lsl=False,
            write_internal_xdf=True,
            write_analysis_csvs=True,
            start_backup_recording=False,
        ),
        enable_missed_trial_topup=True,
        layout_profile=profile,
    )
    window.dialog.resize(profile.window_width, profile.window_height)
    window.dialog.show()
    app.processEvents()

    assert window.dialog.width() <= available_width
    assert window.dialog.height() <= available_height
    assert window.target_button.minimumWidth() == profile.target_min_height
    assert window.target_button.maximumWidth() == profile.target_min_height
    assert window.target_button.minimumHeight() == profile.target_min_height
    assert window.target_button.maximumHeight() == profile.target_min_height
    assert window.include_name_lsl_checkbox.minimumHeight() >= profile.button_min_height + 8
    assert window.output_summary.minimumHeight() == profile.output_min_height
    assert window.mode_tabs.count() == 3
    assert window.mode_tabs.currentIndex() == window.data_logging_tab_index
    assert window.mode_tabs.tabText(window.companion_tab_index) == "Companion Android App (Experimental)"
    assert window.mode_tabs.isTabEnabled(window.experiment_control_tab_index)
    data_rect = _widget_rect(window.data_logging_column, window.dialog)
    settings_rect = _widget_rect(window.experiment_settings_column, window.dialog)
    if window.data_settings_columns_mode == "stacked":
        assert settings_rect["y"] >= data_rect["bottom"]
    else:
        assert abs(settings_rect["y"] - data_rect["y"]) <= 8
        assert settings_rect["x"] >= data_rect["right"]
    for widget in (
        window.participant_code_combo,
        window.include_name_lsl_checkbox,
        window.setup_submit_button,
        window.data_columns_widget,
        window.instruction_legend_widget,
    ):
        _assert_widget_inside_dialog(widget, window.dialog)

    _fill_required_setup(window)
    assert window._submit_participant_setup()
    app.processEvents()
    assert window.mode_tabs.currentIndex() == window.experiment_control_tab_index
    snapshot = window.layout_validation_snapshot()
    content_min = snapshot["experiment_control_debug"]["content_min_height"]
    assert snapshot["splitters"]["mode_tabs"]["count"] == 3
    assert snapshot["splitters"]["mode_tabs"]["experiment_control_enabled"] is True
    assert window.processing_panel.minimumHeight() >= profile.experiment_control_min_height
    assert window.processing_panel.minimumHeight() >= content_min
    assert snapshot["timeline_debug"]["row_names"] == list(focus_app.TIMELINE_ROW_NAMES)
    assert snapshot["timeline_debug"]["row_count"] == len(focus_app.TIMELINE_ROW_NAMES)
    assert window.workspace_splitter.sizes()[1] >= min(profile.experiment_control_initial_height, window.processing_panel.height())
    assert window.response_panel.minimumWidth() == profile.response_panel_side
    assert window.response_panel.minimumHeight() == profile.response_panel_side
    assert window.response_panel.maximumWidth() == profile.response_panel_side
    assert window.response_panel.maximumHeight() == profile.response_panel_side
    assert window.response_panel.geometry().width() == window.response_panel.geometry().height()
    assert window.output_panel is not window.processing_panel
    assert window.processing_splitter is None
    assert window.run_splitter.count() == 2

    visible_widgets = [
        window.target_button,
        window.response_panel,
        window.output_stack_cell,
        window.run_controls_widget,
        window.start_button,
        window.pause_button,
        window.resume_button,
        window.processing_panel,
        window.output_levels_panel,
        window.part_selector_widget,
        window.part_buttons["1"],
        window.part_buttons["2"],
        window.block_plan_widget,
        window.tactile_timeline_widget,
    ]
    if window.topup_draft_widget.isVisible():
        visible_widgets.append(window.topup_draft_widget)
    if window.block_preview_label.isVisible():
        visible_widgets.append(window.block_preview_label)
    assert not window.stop_button.isVisible()
    for widget in visible_widgets:
        _assert_widget_inside_dialog(widget, window.dialog)

    assert window.target_button.geometry().width() == profile.target_min_height
    assert window.target_button.geometry().height() == profile.target_min_height
    assert window.start_button.geometry().height() >= profile.button_min_height
    assert window.output_summary.geometry().height() >= profile.output_min_height
    assert window.processing_panel.geometry().height() >= profile.experiment_control_min_height
    response_rect = _widget_rect(window.response_panel, window.dialog)
    output_stack_rect = _widget_rect(window.output_stack_cell, window.dialog)
    output_rect = _widget_rect(window.output_panel, window.dialog)
    run_controls_rect = _widget_rect(window.run_controls_widget, window.dialog)
    start_rect = _widget_rect(window.start_button, window.dialog)
    run_rect = _widget_rect(window.run_splitter, window.dialog)
    processing_rect = _widget_rect(window.processing_panel, window.dialog)
    workspace_rect = _widget_rect(window.workspace_splitter, window.dialog)
    assert run_controls_rect["y"] >= processing_rect["y"]
    assert start_rect["y"] > response_rect["bottom"]
    assert output_stack_rect["x"] >= response_rect["right"]
    if window.output_panel.isVisible():
        assert output_rect["x"] >= output_stack_rect["x"]
        assert output_rect["right"] <= output_stack_rect["right"]
    else:
        assert window.layout_profile.screen_class in {"constrained", "compact"}
    assert processing_rect["y"] >= run_rect["bottom"]
    assert processing_rect["width"] >= workspace_rect["width"] - 8
    assert not window.layout_validation_failures()
    window.dialog.close()


@pytest.mark.parametrize("available_width,available_height", [(1024, 600), (1366, 768), (1536, 864), (1600, 900), (1920, 1000)])
def test_focus_mode_lower_control_panel_resists_splitter_compression(
    tmp_path: Path,
    available_width: int,
    available_height: int,
):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_focus_preview_session_manifest(tmp_path))
    profile = render_focus_layout_profile(available_width, available_height)
    window = focus_app.FocusModeWindow(q, package, enable_missed_trial_topup=True, layout_profile=profile)
    window.dialog.resize(profile.window_width, profile.window_height)
    window.dialog.show()
    app.processEvents()
    window._set_experiment_control_tab_ready(True, switch=True)
    app.processEvents()

    total = max(1, int(window.workspace_splitter.height()))
    window.workspace_splitter.setSizes([max(1, total - 24), 24])
    app.processEvents()
    window._clamp_workspace_splitter_for_experiment_control()
    app.processEvents()

    snapshot = window.layout_validation_snapshot()
    debug = snapshot["experiment_control_debug"]
    assert window.processing_panel.height() >= debug["content_min_height"]
    assert window.tactile_timeline_widget.height() >= focus_app.TIMELINE_MINIMUM_VISIBLE_HEIGHT
    assert debug["clipped_widgets"] == []
    assert debug["overlap_pairs"] == []
    assert debug["hidden_required_widgets"] == []
    assert not window.layout_validation_failures()
    window.dialog.close()


@pytest.mark.parametrize("available_width,available_height", [(1366, 768), (1600, 900), (1920, 1000)])
def test_focus_mode_lower_control_panel_handles_long_timeline_labels(
    tmp_path: Path,
    available_width: int,
    available_height: int,
):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_focus_preview_session_manifest(tmp_path))
    profile = render_focus_layout_profile(available_width, available_height)
    window = focus_app.FocusModeWindow(q, package, enable_missed_trial_topup=True, layout_profile=profile)
    window.dialog.resize(profile.window_width, profile.window_height)
    window.dialog.show()
    app.processEvents()
    window._set_experiment_control_tab_ready(True, switch=True)
    app.processEvents()

    long_label = "Very long respiratory condition and tactile cue detail " * 6
    window.next_tactile_label.setText(f"Next tactile: {long_label}")
    window.next_tactile_label.setToolTip(window.next_tactile_label.text())
    window.tactile_count_label.setText("999 / 999 cues | 999 clicks")
    window.topup_draft_items = [
        {
            "part_number": "1",
            "block_number": "1",
            "trial_number": str(index),
            "respiratory_phase": long_label,
            "trial_type": "Audio-Tactile",
            "family": "audio_tactile",
            "soa_ms": "2200",
        }
        for index in range(1, 7)
    ]
    window._refresh_topup_draft_widget()
    window._refresh_experiment_control_minimum_height()
    app.processEvents()

    debug = window.layout_validation_snapshot()["experiment_control_debug"]
    if profile.compact or profile.available_height <= 900:
        assert not window.topup_draft_widget.isVisible()
    else:
        assert window.topup_draft_widget.isVisible()
    assert debug["clipped_widgets"] == []
    assert debug["overlap_pairs"] == []
    assert not window.layout_validation_failures()
    window.dialog.close()


def test_focus_mode_instruction_continue_accepts_target_click_and_keyboard(tmp_path: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))
    window = focus_app.FocusModeWindow(q, package)
    window.dialog.show()
    app.processEvents()
    window._set_experiment_control_tab_ready(True, switch=True)
    app.processEvents()

    click_event = threading.Event()
    click_payload = {
        "context": {"mode": "button", "instruction_label": "General instructions", "button_label": "Continue"},
        "approved": False,
        "event": click_event,
    }
    window._handle_instruction_continue(click_payload)
    assert window.target_button.isEnabled()
    assert window.instruction_button.isVisible()

    window._click()

    assert click_payload["approved"] is True
    assert click_event.is_set()
    assert window.pending_instruction_request is None

    keyboard_event = threading.Event()
    keyboard_payload = {
        "context": {"mode": "click", "instruction_label": "Pre-block"},
        "approved": False,
        "event": keyboard_event,
    }
    window._handle_instruction_continue(keyboard_payload)

    window._handle_primary_action_shortcut()

    assert keyboard_payload["approved"] is True
    assert keyboard_event.is_set()
    assert window.pending_instruction_request is None
    window.dialog.close()


def test_focus_mode_logs_response_clicks_outside_target_area(tmp_path: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))
    logged_clicks: list[dict[str, object]] = []

    class FakeController:
        def __init__(self, package_obj, *, capture_options=None, **_kwargs):
            self.package = package_obj
            self.capture_options = capture_options
            self.audio_engine = None

        def log_click(self, *, x=None, y=None, in_target=True) -> None:
            logged_clicks.append({"x": x, "y": y, "in_target": in_target})

    window = focus_app.FocusModeWindow(
        q,
        package,
        capture_options=SessionCaptureOptions(enable_lsl=False, start_backup_recording=False),
        controller_factory=FakeController,
    )
    window.dialog.show()
    app.processEvents()
    _fill_required_setup(window)
    assert window._submit_participant_setup()
    window._run_active = True
    window.target_button.setEnabled(True)
    window.timeline_state.active = True
    window.timeline_state.elapsed_s = 1.25
    app.processEvents()

    QTest.mouseClick(
        window.response_panel,
        q["Qt"].MouseButton.LeftButton,
        q["Qt"].KeyboardModifier.NoModifier,
        q["QPoint"](4, 4),
    )
    app.processEvents()

    assert len(logged_clicks) == 1
    assert logged_clicks[0]["in_target"] is False
    assert logged_clicks[0]["x"] not in (None, "")
    assert logged_clicks[0]["y"] not in (None, "")
    assert window.timeline_state.click_count() == 1

    QTest.mouseClick(window.target_button, q["Qt"].MouseButton.LeftButton)
    app.processEvents()

    assert [click["in_target"] for click in logged_clicks] == [False, True]
    assert window.timeline_state.click_count() == 2
    window.dialog.close()


def test_focus_mode_logs_global_response_clicks_inside_and_outside_target_area(tmp_path: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))
    logged_clicks: list[dict[str, object]] = []

    class FakeController:
        def __init__(self, package_obj, *, capture_options=None, **_kwargs):
            self.package = package_obj
            self.capture_options = capture_options
            self.audio_engine = None

        def log_click(self, *, x=None, y=None, in_target=True) -> None:
            logged_clicks.append({"x": x, "y": y, "in_target": in_target})

    window = focus_app.FocusModeWindow(
        q,
        package,
        capture_options=SessionCaptureOptions(enable_lsl=False, start_backup_recording=False),
        controller_factory=FakeController,
    )
    window.dialog.show()
    app.processEvents()
    _fill_required_setup(window)
    assert window._submit_participant_setup()
    window._run_active = True
    window.target_button.setEnabled(True)
    window.timeline_state.active = True
    window.timeline_state.elapsed_s = 1.25
    app.processEvents()
    window._refresh_target_global_bounds()

    target_center = window.target_button.mapToGlobal(
        q["QPoint"](window.target_button.width() // 2, window.target_button.height() // 2)
    )
    inside_x, inside_y = int(target_center.x()), int(target_center.y())
    outside_x = inside_x + int(window.target_button.width()) + 80
    outside_y = inside_y + int(window.target_button.height()) + 80

    window._handle_global_response_mouse_click(outside_x, outside_y)

    assert len(logged_clicks) == 1
    assert logged_clicks[0]["in_target"] is False
    assert window.timeline_state.click_count() == 0

    window._drain()

    assert window.timeline_state.click_count() == 1
    assert "outside target" in window.event_label.text()

    window._handle_global_response_mouse_click(inside_x, inside_y)
    window._drain()

    assert [click["in_target"] for click in logged_clicks] == [False, True]
    assert window.timeline_state.click_count() == 2
    window.dialog.close()


def test_focus_mode_start_part2_button_controls_part_transition(tmp_path: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_focus_preview_session_manifest(tmp_path))
    window = focus_app.FocusModeWindow(q, package)
    window.dialog.show()
    app.processEvents()
    window._set_experiment_control_tab_ready(True, switch=True)
    app.processEvents()

    assert window.start_part2_button is not None
    assert window.start_part2_button.isVisible()
    assert not window.start_part2_button.isEnabled()

    transition_event = threading.Event()
    transition_payload = {
        "context": {
            "mode": "button",
            "instruction_label": "Interim",
            "button_label": "Start Part 2",
            "next_action": "next_condition",
            "block_part_number": 2,
        },
        "approved": False,
        "event": transition_event,
    }
    window._handle_instruction_continue(transition_payload)
    app.processEvents()

    assert window.start_part2_button.isEnabled()
    assert window.start_button.isEnabled()
    assert window.start_button.text() == "Start Part 02"
    assert not window.target_button.isEnabled()
    assert not window.instruction_button.isVisible()

    window._click()
    app.processEvents()
    assert transition_payload["approved"] is False
    assert not transition_event.is_set()

    window._handle_primary_action_shortcut()
    app.processEvents()
    assert transition_payload["approved"] is True
    assert transition_event.is_set()
    assert window.pending_instruction_request is None
    assert window.selected_part_key == "2"
    assert not window.start_part2_button.isEnabled()
    window.dialog.close()


def test_focus_mode_primary_shortcut_starts_only_after_setup(tmp_path: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))

    class FakeController:
        def __init__(self, package_obj, *, capture_options=None, **_kwargs):
            self.package = package_obj
            self.capture_options = capture_options
            self.audio_engine = None

    window = focus_app.FocusModeWindow(
        q,
        package,
        capture_options=SessionCaptureOptions(enable_lsl=False, start_backup_recording=False),
        controller_factory=FakeController,
    )
    window.dialog.show()
    app.processEvents()

    starts: list[bool] = []
    window.start = lambda: starts.append(True)  # type: ignore[method-assign]

    window.participant_name_input.setFocus()
    app.processEvents()
    window._handle_primary_action_shortcut()
    assert starts == []

    window.start_button.setFocus()
    app.processEvents()
    window._handle_primary_action_shortcut()
    assert starts == []

    _fill_required_setup(window)
    assert window._submit_participant_setup()
    window.start_button.setFocus()
    app.processEvents()
    window._handle_primary_action_shortcut()
    assert starts == [True]
    window.dialog.close()


def test_focus_mode_operator_keyboard_shortcuts_control_ui(tmp_path: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_focus_preview_session_manifest(tmp_path))
    window = focus_app.FocusModeWindow(
        q,
        package,
        capture_options=SessionCaptureOptions(enable_lsl=False, start_backup_recording=False),
        enable_missed_trial_topup=True,
    )
    window.dialog.show()
    window.dialog.activateWindow()
    window.dialog.setFocus(q["Qt"].FocusReason.ShortcutFocusReason)
    app.processEvents()
    _fill_required_setup(window)
    assert window._submit_participant_setup()

    shortcut_map = window.keyboard_shortcut_map()
    assert shortcut_map["pause_resume"] == ["Ctrl+P"]
    assert "stop" not in shortcut_map
    assert shortcut_map["select_part_2"] == ["Alt+2"]
    assert set(window.operator_action_shortcuts) >= {
        "pause_resume",
        "close",
        "select_part_1",
        "select_part_2",
        "select_topup_preview",
    }

    class FakeController:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def pause(self) -> None:
            self.calls.append("pause")

        def resume(self) -> None:
            self.calls.append("resume")

        def stop(self) -> None:
            self.calls.append("stop")

    fake = FakeController()
    window.controller = fake  # type: ignore[assignment]
    window._run_active = True
    window._run_paused = False
    window.pause_button.setEnabled(True)
    window.resume_button.setEnabled(False)
    ctrl = q["Qt"].KeyboardModifier.ControlModifier
    alt = q["Qt"].KeyboardModifier.AltModifier

    QTest.keyClick(window.dialog, q["Qt"].Key.Key_P, ctrl)
    app.processEvents()
    QTest.keyClick(window.dialog, q["Qt"].Key.Key_P, ctrl)
    app.processEvents()

    assert fake.calls == ["pause", "resume"]

    QTest.keyClick(window.dialog, q["Qt"].Key.Key_2, alt)
    app.processEvents()
    assert window.selected_part_key == "2"

    QTest.keyClick(window.dialog, q["Qt"].Key.Key_T, ctrl)
    app.processEvents()
    selected = window._run_plan_item_by_number(window.selected_display_block_index or 0)
    assert selected is not None
    assert selected["kind"] == "topup"
    window.dialog.close()


def test_focus_mode_validation_synthetic_click_shortcut_is_opt_in(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_focus_preview_session_manifest(tmp_path))

    monkeypatch.delenv("PPS_FOCUS_VALIDATION_ENABLE_SYNTHETIC_CLICK_SHORTCUT", raising=False)
    default_window = focus_app.FocusModeWindow(
        q,
        package,
        capture_options=SessionCaptureOptions(enable_lsl=False, start_backup_recording=False),
    )
    assert "validation_synthetic_click" not in default_window.keyboard_shortcut_map()
    default_window.dialog.close()

    monkeypatch.setenv("PPS_FOCUS_VALIDATION_ENABLE_SYNTHETIC_CLICK_SHORTCUT", "1")
    window = focus_app.FocusModeWindow(
        q,
        package,
        capture_options=SessionCaptureOptions(enable_lsl=False, start_backup_recording=False),
    )
    window.dialog.show()
    app.processEvents()
    assert window.keyboard_shortcut_map()["validation_synthetic_click"] == ["Ctrl+Alt+Shift+F12"]
    assert "validation_synthetic_click" in window.operator_action_shortcuts

    class FakeController:
        def __init__(self) -> None:
            self.clicks: list[dict[str, Any]] = []

        def log_click(self, **payload: Any) -> None:
            self.clicks.append(dict(payload))

    fake = FakeController()
    window.controller = fake  # type: ignore[assignment]
    window._run_active = True
    window._handle_validation_synthetic_click_shortcut()

    assert len(fake.clicks) == 1
    assert fake.clicks[0]["in_target"] is True
    window.dialog.close()


def test_focus_mode_mouse_area_lock_chord_toggles_and_releases_on_close(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_focus_preview_session_manifest(tmp_path))
    window = focus_app.FocusModeWindow(
        q,
        package,
        capture_options=SessionCaptureOptions(enable_lsl=False, start_backup_recording=False),
    )
    window.dialog.show()
    app.processEvents()

    calls: list[str] = []
    monkeypatch.setattr(focus_app.sys, "platform", "win32")
    monkeypatch.setattr(focus_app, "_append_output_diary_event", lambda event_type, **_kwargs: calls.append(event_type))
    monkeypatch.setattr(window, "_apply_mouse_area_clip", lambda: calls.append("apply_clip") or True)
    monkeypatch.setattr(window, "_release_mouse_area_clip", lambda: calls.append("release_clip"))
    monkeypatch.setattr(window, "_move_os_cursor_to_global_center", lambda *_args: calls.append("move_cursor") or "test")

    ctrl = q["Qt"].KeyboardModifier.ControlModifier
    keys = q["Qt"].Key

    class FakeKeyEvent:
        def __init__(self, key, *, modifiers=ctrl, auto_repeat: bool = False):
            self._key = key
            self._modifiers = modifiers
            self._auto_repeat = auto_repeat

        def isAutoRepeat(self) -> bool:  # noqa: N802 - Qt API shape
            return self._auto_repeat

        def key(self):
            return self._key

        def modifiers(self):
            return self._modifiers

    for key in (keys.Key_A, keys.Key_S, keys.Key_D):
        window._handle_mouse_lock_chord_event(FakeKeyEvent(key), True)
    assert window._mouse_area_lock_active is True
    assert "mouse_area_lock_enabled" in calls
    assert calls.count("apply_clip") == 1

    window._handle_mouse_lock_chord_event(FakeKeyEvent(keys.Key_D), True)
    assert calls.count("mouse_area_lock_enabled") == 1

    for key in (keys.Key_A, keys.Key_S, keys.Key_D):
        window._handle_mouse_lock_chord_event(FakeKeyEvent(key), False)
    for key in (keys.Key_A, keys.Key_S, keys.Key_D):
        window._handle_mouse_lock_chord_event(FakeKeyEvent(key), True)

    assert window._mouse_area_lock_active is False
    assert "mouse_area_lock_disabled" in calls
    assert "release_clip" in calls

    calls.clear()
    for key in (keys.Key_A, keys.Key_S, keys.Key_D):
        window._handle_mouse_lock_chord_event(FakeKeyEvent(key), False)
    for key in (keys.Key_A, keys.Key_S, keys.Key_D):
        window._handle_mouse_lock_chord_event(FakeKeyEvent(key), True)
    assert window._mouse_area_lock_active is True

    window._handle_dialog_finished(0)
    assert window._mouse_area_lock_active is False
    assert "mouse_area_lock_disabled" in calls
    window.dialog.close()


def test_focus_mode_hardware_start_injects_ui_thread_audio_engine(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))
    window = focus_app.FocusModeWindow(q, package)
    window.dialog.show()
    app.processEvents()

    class FakeEngine:
        def __init__(self) -> None:
            self.shutdown_count = 0

        def shutdown(self) -> None:
            self.shutdown_count += 1

    fake_engine = FakeEngine()
    created_on_threads: list[str] = []
    injected_engines: list[object] = []

    def fake_create_engine() -> FakeEngine:
        created_on_threads.append(threading.current_thread().name)
        return fake_engine

    class FakeController:
        def __init__(self, package_obj, *, audio_engine=None, capture_options=None, **_kwargs):
            self.package = package_obj
            self.audio_engine = audio_engine
            self.capture_options = capture_options
            injected_engines.append(audio_engine)

        def run(self, *, progress_callback=None, event_callback=None):
            return SimpleNamespace(
                completed=True,
                interrupted=False,
                summary_text="done",
                session_dir=self.package.session_dir,
                events_csv=self.package.session_dir / "events.csv",
                events_xdf=self.package.session_dir / "events.xdf",
                lsl_markers_csv=None,
                lsl_markers_xdf=None,
                trigger_dictionary_path=None,
                session_metadata_path=None,
                recording_paths=[],
                warnings=[],
                capture_options=(self.capture_options.as_dict() if self.capture_options is not None else {}),
            )

    monkeypatch.setattr(window, "_create_real_audio_engine_on_ui_thread", fake_create_engine)
    monkeypatch.setattr(focus_app, "SessionRunnerController", FakeController)

    _fill_required_setup(window)
    assert window._submit_participant_setup()
    assert window.demographics_submitted
    assert window.start_button.isEnabled()
    window.start()
    assert created_on_threads == [threading.current_thread().name]
    assert injected_engines == [None]
    assert window.controller is not None
    assert window.controller.audio_engine is fake_engine
    assert window.thread is not None
    window.thread.join(timeout=2)
    assert not window.thread.is_alive()
    window._drain()

    assert window.result is not None
    assert window.result.completed is True
    assert fake_engine.shutdown_count == 1
    window.dialog.close()


def test_focus_mode_start_click_locks_window_geometry_until_done(tmp_path: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))
    started = threading.Event()
    release = threading.Event()

    class FakeController:
        def __init__(self, package_obj, *, capture_options=None, **_kwargs):
            self.package = package_obj
            self.capture_options = capture_options
            self.audio_engine = SimpleNamespace()

        def run(self, *, progress_callback=None, event_callback=None):
            started.set()
            assert release.wait(timeout=2)
            return SimpleNamespace(
                completed=True,
                interrupted=False,
                summary_text="done",
                session_dir=self.package.session_dir,
                events_csv=self.package.session_dir / "events.csv",
                events_xdf=self.package.session_dir / "events.xdf",
                lsl_markers_csv=None,
                lsl_markers_xdf=None,
                trigger_dictionary_path=None,
                session_metadata_path=None,
                recording_paths=[],
                warnings=[],
                capture_options={"write_analysis_csvs": False},
            )

    window = focus_app.FocusModeWindow(
        q,
        package,
        capture_options=SessionCaptureOptions(enable_lsl=False, start_backup_recording=False),
        controller_factory=FakeController,
    )
    window.dialog.show()
    window.dialog.resize(900, 700)
    app.processEvents()

    _fill_required_setup(window)
    assert window._submit_participant_setup()
    assert window.start_button.isEnabled()
    QTest.mouseClick(window.start_button, q["Qt"].MouseButton.LeftButton)
    assert started.wait(timeout=2)
    app.processEvents()

    locked_geometry = window.dialog.geometry()
    locked_size = locked_geometry.size()
    lock_snapshot = window.layout_validation_snapshot()["experiment_window_lock"]
    assert lock_snapshot["active"] is True
    assert lock_snapshot["locked_geometry"] == {
        "x": locked_geometry.x(),
        "y": locked_geometry.y(),
        "width": locked_geometry.width(),
        "height": locked_geometry.height(),
    }
    assert window.dialog.minimumSize() == locked_size
    assert window.dialog.maximumSize() == locked_size

    window.dialog.setGeometry(
        locked_geometry.x() + 40,
        locked_geometry.y() + 25,
        locked_geometry.width() + 30,
        locked_geometry.height() + 30,
    )
    app.processEvents()
    window._restore_locked_experiment_window_geometry()
    app.processEvents()

    assert window.dialog.geometry() == locked_geometry
    assert window.layout_validation_snapshot()["experiment_window_lock"]["active"] is True

    release.set()
    assert window.thread is not None
    window.thread.join(timeout=2)
    assert not window.thread.is_alive()
    window._drain()
    app.processEvents()

    assert window.result is not None
    assert window.result.completed is True
    assert window.layout_validation_snapshot()["experiment_window_lock"]["active"] is False
    assert window.dialog.minimumSize().width() <= locked_size.width()
    assert window.dialog.maximumSize().width() >= locked_size.width()
    window.dialog.close()


def test_focus_mode_opens_post_run_analysis_review_dialog(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.delenv("PPS_FOCUS_DISABLE_ANALYSIS_POPUP", raising=False)
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))
    window = focus_app.FocusModeWindow(q, package)
    window.dialog.show()
    app.processEvents()
    outputs = _write_analysis_review_outputs(package.session_dir)

    result = SimpleNamespace(
        completed=True,
        session_dir=package.session_dir,
        summary_text="Tactile trials reconstructed: 4",
        analysis_outputs=outputs,
        capture_options={"write_analysis_csvs": True},
    )

    window._maybe_open_analysis_review(result)
    app.processEvents()

    assert window.analysis_review_dialog is not None
    dialog = window.analysis_review_dialog.dialog
    assert dialog.isVisible()
    model_combo = dialog.findChild(q["QComboBox"], "analysisModelCombo")
    dataset_combo = dialog.findChild(q["QComboBox"], "analysisDatasetCombo")
    scope_combo = dialog.findChild(q["QComboBox"], "analysisScopeCombo")
    metric_combo = dialog.findChild(q["QComboBox"], "analysisMetricCombo")
    source_combo = dialog.findChild(q["QComboBox"], "analysisSourceCombo")
    grouping_combo = dialog.findChild(q["QComboBox"], "analysisGroupingCombo")
    overview_table = dialog.findChild(q["QTableWidget"], "analysisOverviewTable")
    details = dialog.findChild(q["QTextEdit"], "analysisDetailsText")
    level1_panel = dialog.findChild(q["QFrame"], "analysisLevel1Panel")
    level2_panel = dialog.findChild(q["QFrame"], "analysisLevel2Panel")
    level3_panel = dialog.findChild(q["QFrame"], "analysisLevel3Panel")
    response_panel = dialog.findChild(q["QFrame"], "analysisResponseQualityPanel")
    assumption_panel = dialog.findChild(q["QFrame"], "analysisAssumptionPanel")
    baseline_assumption_button = dialog.findChild(q["QPushButton"], "analysisBaselineAssumptionButton")
    pps_assumption_button = dialog.findChild(q["QPushButton"], "analysisPpsAssumptionButton")
    assumption_preview_plot = dialog.findChild(q["QWidget"], "analysisAssumptionPreviewPlot")
    response_bars = dialog.findChild(q["QWidget"], "analysisResponseQualityBars")
    tactile_hits_percent = dialog.findChild(q["QLabel"], "analysisResponseMetricTactileHitsPercent")
    tactile_hits_count = dialog.findChild(q["QLabel"], "analysisResponseMetricTactileHitsCount")
    tactile_misses_percent = dialog.findChild(q["QLabel"], "analysisResponseMetricTactileMissesPercent")
    catch_correct_percent = dialog.findChild(q["QLabel"], "analysisResponseMetricCatchCorrectPercent")
    catch_false_alarm_percent = dialog.findChild(q["QLabel"], "analysisResponseMetricCatchFalseAlarmsPercent")
    catch_false_alarm_count = dialog.findChild(q["QLabel"], "analysisResponseMetricCatchFalseAlarmsCount")
    triage_hint = dialog.findChild(q["QLabel"], "analysisTriageHint")
    analysis_plot = dialog.findChild(q["QWidget"], "analysisCurvePlot")
    more_button = dialog.findChild(q["QPushButton"], "analysisMoreButton")
    level_nav_buttons = [button for button in dialog.findChildren(q["QPushButton"], "analysisLevelNavButton")]
    condition_buttons = [button for button in dialog.findChildren(q["QPushButton"], "analysisConditionLensButton")]
    quick_model_buttons = [button for button in dialog.findChildren(q["QPushButton"], "analysisModelButton")]
    assert dataset_combo is not None and dataset_combo.count() == 1
    assert level1_panel is not None
    assert level2_panel is not None
    assert level3_panel is not None
    assert [button.text() for button in level_nav_buttons] == ["1 Response", "2 Assumptions", "3 Model Fit"]
    assert response_panel is not None
    assert assumption_panel is not None
    assert assumption_preview_plot is not None
    assert baseline_assumption_button is not None and baseline_assumption_button.text() == "Baseline Assumption"
    assert pps_assumption_button is not None and pps_assumption_button.text() == "Peripersonal Space Assumption"
    assert "#238d5a" in baseline_assumption_button.styleSheet()
    assert "#238d5a" in pps_assumption_button.styleSheet()
    assert "two-sided p" in baseline_assumption_button.toolTip()
    assert "one-sided p" in pps_assumption_button.toolTip()
    assert response_bars is not None
    assert tactile_hits_percent is not None and tactile_hits_percent.text() == "80.0%"
    assert tactile_hits_count is not None and tactile_hits_count.text() == "4 / 5"
    assert tactile_misses_percent is not None and tactile_misses_percent.text() == "20.0%"
    assert catch_correct_percent is not None and catch_correct_percent.text() == "75.0%"
    assert catch_false_alarm_percent is not None and catch_false_alarm_percent.text() == "25.0%"
    assert catch_false_alarm_count is not None and catch_false_alarm_count.text() == "1 / 4"
    assert triage_hint is not None and "AICc support" in triage_hint.text()
    assert "Baseline: pooled across SOAs within condition" in triage_hint.text()
    assert analysis_plot is not None and getattr(analysis_plot, "metric_label", "") == "Baseline-corrected facilitation (ms)"
    assert _widget_rect(level1_panel, dialog)["bottom"] <= _widget_rect(level2_panel, dialog)["y"]
    assert _widget_rect(level2_panel, dialog)["bottom"] <= _widget_rect(level3_panel, dialog)["y"]
    assert _widget_rect(level1_panel, dialog)["y"] <= _widget_rect(response_panel, dialog)["y"] <= _widget_rect(level1_panel, dialog)["bottom"]
    assert _widget_rect(level2_panel, dialog)["y"] <= _widget_rect(assumption_panel, dialog)["y"] <= _widget_rect(level2_panel, dialog)["bottom"]
    assert _widget_rect(level2_panel, dialog)["y"] <= _widget_rect(assumption_preview_plot, dialog)["y"] <= _widget_rect(level2_panel, dialog)["bottom"]
    assert _widget_rect(level3_panel, dialog)["y"] <= _widget_rect(analysis_plot, dialog)["y"] <= _widget_rect(level3_panel, dialog)["bottom"]
    scrollbar = window.analysis_review_dialog.scroll_area.verticalScrollBar()
    level3_nav = next(button for button in level_nav_buttons if button.text() == "3 Model Fit")
    level1_nav = next(button for button in level_nav_buttons if button.text() == "1 Response")
    level3_nav.click()
    app.processEvents()
    model_scroll_value = scrollbar.value()
    assert model_scroll_value > 0
    assert level3_nav.isChecked()
    level1_nav.click()
    app.processEvents()
    assert scrollbar.value() < model_scroll_value
    assert level1_nav.isChecked()
    pps_assumption_button.click()
    app.processEvents()
    assumption_dialog = window.analysis_review_dialog.assumption_detail_dialog
    assert assumption_dialog is not None and assumption_dialog.isVisible()
    assumption_plot = assumption_dialog.findChild(q["QWidget"], "analysisAssumptionBetaPlot")
    assumption_summary = assumption_dialog.findChild(q["QLabel"], "analysisAssumptionDetailSummary")
    assert assumption_plot is not None
    assert assumption_summary is not None and "Green:" in assumption_summary.text()
    assert assumption_dialog.grab().size().width() > 0
    assumption_dialog.close()
    assert {button.text() for button in condition_buttons} == {"2 x 2", "Part 1 | Part 2", "Inhale | Exhale"}
    assert {button.text() for button in quick_model_buttons} == {"Sigmoid", "Log decay", "Linear"}
    assert details is not None and "Condition lens: two_by_two" in details.toPlainText()
    state_button = next(button for button in condition_buttons if button.text() == "Inhale | Exhale")
    state_button.click()
    app.processEvents()
    assert "Inhale | Exhale" in triage_hint.text()
    linear_button = next(button for button in quick_model_buttons if button.text() == "Linear")
    linear_button.click()
    app.processEvents()
    assert "Linear AICc support" in triage_hint.text()
    assert more_button is not None
    more_button.click()
    app.processEvents()
    assert model_combo is not None and model_combo.count() == 5
    assert "Compare all three" in [model_combo.itemText(index) for index in range(model_combo.count())]
    assert metric_combo is not None and "Hit rate" in [metric_combo.itemText(index) for index in range(metric_combo.count())]
    assert source_combo is not None and "Logged but excluded events" in [source_combo.itemText(index) for index in range(source_combo.count())]
    assert grouping_combo is not None and "By SOA/distance bin" in [grouping_combo.itemText(index) for index in range(grouping_combo.count())]
    assert scope_combo is not None and scope_combo.count() == 1
    assert overview_table is not None and overview_table.rowCount() == 1
    part_buttons = [button for button in dialog.findChildren(q["QPushButton"], "analysisSegmentButton")]
    assert {button.text() for button in part_buttons}.issuperset({"Data Behavior", "Model Fits", "Responses", "Timing Evidence", "Top-Up", "Artifacts", "Separate parts", "Pool parts"})
    toggles = [box.text() for box in dialog.findChildren(q["QCheckBox"], "analysisPlotToggle")]
    assert {"Observed means", "Uncertainty band", "Raw trial points", "Rejected / extra clicks", "Top-up rescues", "PPS boundary", "All model fits", "Low-N markers"}.issubset(set(toggles))
    compare_index = model_combo.findText("Compare all three")
    assert compare_index >= 0
    model_combo.setCurrentIndex(compare_index)
    app.processEvents()
    assert "Exploratory data-behavior signals" in details.toPlainText()
    assert "Expected pattern" in details.toPlainText()
    assert "participant-readiness certification" in details.toPlainText()
    assert "Best model by AIC" in details.toPlainText()
    assert "Displayed range: +/- SEM" in details.toPlainText()
    assert "Displayed models: Sigmoid, Linear, Logarithmic decay" in details.toPlainText()
    assert "Sigmoid PPS boundary" in details.toPlainText()
    pooled = next(button for button in part_buttons if button.text() == "Pool parts")
    pooled.click()
    app.processEvents()
    assert scope_combo.currentText() == "All parts / Inhale / pink"
    assert "Part summary: Pool parts" in details.toPlainText()
    screenshot = tmp_path / "analysis_review_dialog.png"
    assert dialog.grab().save(str(screenshot))
    assert screenshot.stat().st_size > 0
    dialog.close()
    window.dialog.close()


def test_analysis_review_dialog_switches_saved_datasets(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
        from peripersonal_space_toolkit.analysis_catalog import load_analysis_dataset
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    p001_dir = tmp_path / "P001"
    p002_dir = tmp_path / "P002"
    outputs_1 = _write_analysis_review_outputs(p001_dir)
    outputs_2 = _write_analysis_review_outputs(p002_dir)
    outputs_2["recording_quality_gate"].write_text(
        json.dumps(
            {
                "schema": "pps-recording-quality-gate.v1",
                "status": "FAIL",
                "primary_reason": "Injected test exclusion.",
                "failures": [{"code": "test_fail", "message": "Injected test exclusion.", "evidence": "test"}],
                "warnings": [],
                "metrics": {"overall_hit_rate": 0.2},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    outputs_2["participant_trials"].write_text(
        "\n".join(
            [
                (
                    "trial_uid,trial_number,trial_type,stimulus_modality,tactile_present,catch_trial,response_given,"
                    "outcome,hit,part_number,condition,respiratory_phase,noise_type,soa_ms,rt_ms,is_topup,topup_role"
                ),
                "T001,1,Audio-Tactile,audio_tactile,true,false,true,Hit,true,1,,Inhale,pink,100,310,false,",
                "T002,2,Audio-Tactile,audio_tactile,true,false,false,Miss,false,1,,Inhale,pink,200,,false,",
                "C001,3,Catch,audio,false,true,false,Hit,true,1,,Inhale,pink,,,false,",
                "C002,4,Catch,audio,false,true,true,Miss,false,1,,Inhale,pink,,,false,",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    outputs_2["basic_assumption_checks"].write_text(
        json.dumps(
            {
                "schema": "pps-basic-assumption-checks.v1",
                "baseline_assumption": {
                    "status": "FAIL",
                    "summary": "Baseline RTs showed a significant proximity/SOA trend, so the pragmatic flatness check failed.",
                    "beta": -0.08,
                    "p_two_sided": 0.01,
                    "coverage": {"n": 6, "distinct_soa_count": 2},
                },
                "peripersonal_space_assumption": {
                    "status": "FAIL",
                    "summary": "The audio-tactile proximity interaction had the predicted sign but was not significant at one-sided p<.05.",
                    "interaction_beta": -0.01,
                    "p_one_sided_negative": 0.34,
                    "pps_far_to_near_gain_ms": 4.0,
                    "coverage": {
                        "baseline": {"n": 6, "distinct_soa_count": 2},
                        "audio_tactile": {"n": 12, "distinct_soa_count": 3},
                    },
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    entries = [
        {
            "dataset_id": "participant:P001",
            "dataset_kind": "participant",
            "dataset_label": "P001",
            "participant_id": "P001",
            "quality_status": "PASS",
            "analysis_dir": str(p001_dir / "analysis"),
            "outputs": {key: str(value) for key, value in outputs_1.items()},
        },
        {
            "dataset_id": "participant:P002",
            "dataset_kind": "participant",
            "dataset_label": "P002",
            "participant_id": "P002",
            "quality_status": "FAIL",
            "analysis_dir": str(p002_dir / "analysis"),
            "outputs": {key: str(value) for key, value in outputs_2.items()},
        },
    ]
    dialog_controller = focus_app.AnalysisReviewDialog(
        q,
        None,
        load_analysis_dataset(entries[0]),
        dataset_entries=entries,
        selected_dataset_id="participant:P001",
    )
    dialog = dialog_controller.dialog
    dialog.show()
    app.processEvents()
    dataset_combo = dialog.findChild(q["QComboBox"], "analysisDatasetCombo")
    tactile_hits_percent = dialog.findChild(q["QLabel"], "analysisResponseMetricTactileHitsPercent")
    catch_false_alarm_percent = dialog.findChild(q["QLabel"], "analysisResponseMetricCatchFalseAlarmsPercent")
    pps_assumption_button = dialog.findChild(q["QPushButton"], "analysisPpsAssumptionButton")
    assert dataset_combo is not None and dataset_combo.count() == 2
    assert tactile_hits_percent is not None and tactile_hits_percent.text() == "80.0%"
    assert catch_false_alarm_percent is not None and catch_false_alarm_percent.text() == "25.0%"
    assert pps_assumption_button is not None and "#238d5a" in pps_assumption_button.styleSheet()

    dataset_combo.setCurrentIndex(dataset_combo.findData("participant:P002"))
    app.processEvents()

    assert dialog_controller.current_dataset_id == "participant:P002"
    assert tactile_hits_percent.text() == "50.0%"
    assert catch_false_alarm_percent.text() == "50.0%"
    assert "#d9544b" in pps_assumption_button.styleSheet()
    assert "not significant" in pps_assumption_button.toolTip()
    dialog.close()


def test_analysis_review_dialog_missing_assumption_artifact_falls_back_to_red(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
        from peripersonal_space_toolkit.analysis_catalog import load_analysis_dataset
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    outputs = _write_analysis_review_outputs(tmp_path / "P003")
    outputs["basic_assumption_checks"].unlink()
    entry = {
        "dataset_id": "participant:P003",
        "dataset_kind": "participant",
        "dataset_label": "P003",
        "participant_id": "P003",
        "quality_status": "PASS",
        "analysis_dir": str(tmp_path / "P003" / "analysis"),
        "outputs": {key: str(value) for key, value in outputs.items()},
    }

    dialog_controller = focus_app.AnalysisReviewDialog(q, None, load_analysis_dataset(entry), dataset_entries=[entry], selected_dataset_id="participant:P003")
    dialog = dialog_controller.dialog
    dialog.show()
    app.processEvents()

    baseline_button = dialog.findChild(q["QPushButton"], "analysisBaselineAssumptionButton")
    pps_button = dialog.findChild(q["QPushButton"], "analysisPpsAssumptionButton")
    assumption_preview_plot = dialog.findChild(q["QWidget"], "analysisAssumptionPreviewPlot")
    assert baseline_button is not None and "#d9544b" in baseline_button.styleSheet()
    assert pps_button is not None and "#d9544b" in pps_button.styleSheet()
    assert assumption_preview_plot is not None
    assert "basic_assumption_checks.v1.json was not available" in pps_button.toolTip()
    pps_button.click()
    app.processEvents()
    assumption_dialog = dialog_controller.assumption_detail_dialog
    assert assumption_dialog is not None and assumption_dialog.isVisible()
    assert assumption_dialog.findChild(q["QWidget"], "analysisAssumptionBetaPlot") is not None
    assumption_dialog.close()
    dialog.close()


def test_focus_mode_skips_analysis_review_for_interrupted_or_disabled_analysis(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.delenv("PPS_FOCUS_DISABLE_ANALYSIS_POPUP", raising=False)
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))
    outputs = _write_analysis_review_outputs(package.session_dir)
    window = focus_app.FocusModeWindow(q, package)
    window.dialog.show()
    app.processEvents()

    window._maybe_open_analysis_review(
        SimpleNamespace(completed=False, session_dir=package.session_dir, analysis_outputs=outputs, capture_options={"write_analysis_csvs": True})
    )
    assert window.analysis_review_dialog is None

    window._maybe_open_analysis_review(
        SimpleNamespace(completed=True, session_dir=package.session_dir, analysis_outputs=outputs, capture_options={"write_analysis_csvs": False})
    )
    assert window.analysis_review_dialog is None
    window.dialog.close()


def test_focus_mode_recenter_uses_pyautogui_backend(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
        from peripersonal_space_toolkit.focus_timeline import TactileTimelineCue
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    moves: list[tuple[int, int, int]] = []

    class FakePyAutoGUI:
        FAILSAFE = True
        PAUSE = 0.1

        @staticmethod
        def moveTo(x, y, duration=0):
            moves.append((int(x), int(y), int(duration)))

    monkeypatch.setitem(sys.modules, "pyautogui", FakePyAutoGUI)

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))
    window = focus_app.FocusModeWindow(q, package)
    window.dialog.show()
    app.processEvents()
    monkeypatch.setattr(window, "_offscreen_platform", lambda: False)

    cue = TactileTimelineCue(cue_id=1, trial_number=1, trial_uid="T001", time_s=4.0)
    window._move_cursor_to_target(cue)

    assert moves
    assert window.recenter_records[-1]["mode"] == "pyautogui"
    assert window.recenter_records[-1]["trial_uid"] == "T001"
    window.dialog.close()


def test_focus_mode_validation_no_mouse_records_recenter_intent(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
        from peripersonal_space_toolkit.focus_timeline import TactileTimelineCue
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    moves: list[tuple[int, int, int]] = []

    class FakePyAutoGUI:
        FAILSAFE = True
        PAUSE = 0.1

        @staticmethod
        def moveTo(x, y, duration=0):
            moves.append((int(x), int(y), int(duration)))

    monkeypatch.setitem(sys.modules, "pyautogui", FakePyAutoGUI)
    monkeypatch.setenv("PPS_FOCUS_VALIDATION_DISABLE_MOUSE_CAPTURE", "1")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))
    window = focus_app.FocusModeWindow(q, package)
    window.dialog.show()
    app.processEvents()
    monkeypatch.setattr(window, "_offscreen_platform", lambda: False)

    cue = TactileTimelineCue(cue_id=1, trial_number=1, trial_uid="T001", time_s=4.0)
    window._move_cursor_to_target(cue)

    record = window.recenter_records[-1]
    assert moves == []
    assert record["mode"] == "recorded_intent"
    assert record["cursor_move_suppressed"] is True
    assert "cursor recenter disabled" in record["backend_warning"]
    window.dialog.close()


def test_validation_window_rect_from_env(monkeypatch):
    from peripersonal_space_toolkit import focus_app

    monkeypatch.setenv("PPS_FOCUS_VALIDATION_WINDOW_RECT", "-1920,5,820,1032")
    assert focus_app._validation_window_rect_from_env() == (-1920, 5, 820, 1032)

    monkeypatch.setenv("PPS_FOCUS_VALIDATION_WINDOW_RECT", "-1920,5,-1,1032")
    assert focus_app._validation_window_rect_from_env() is None

    monkeypatch.setenv("PPS_FOCUS_VALIDATION_WINDOW_RECT", "not,a,rect")
    assert focus_app._validation_window_rect_from_env() is None


def test_tactile_timeline_uses_tactile_onset_response_window():
    from peripersonal_space_toolkit.focus_timeline import TactileTimelineState

    state = TactileTimelineState()
    state.load_block(
        duration_s=10.0,
        tactile_events=[
            {"trial_number": 1, "trial_uid": "T001", "time_s": 1.0},
        ],
    )

    accepted = state.record_click(2.3, trial_uid="T001")
    rejected = state.record_click(2.302, trial_uid="T001")

    assert accepted.response_status == "tactile_response"
    assert accepted.rt_s == pytest.approx(1.3)
    assert rejected.response_status == "off_cue"


def test_validation_realtime_audio_engine_waits_for_buffer_deadlines(tmp_path: Path):
    from peripersonal_space_toolkit.focus_app import _ValidationFastAudioEngine

    sample_rate = 1000
    duration_s = 0.12
    wav_path = tmp_path / "short_block.wav"
    sf.write(wav_path, [0.0] * int(sample_rate * duration_s), sample_rate)

    engine = _ValidationFastAudioEngine(chunk_frames=10, realtime=True)
    started = time.perf_counter()
    assert engine.play_block(str(wav_path))
    elapsed = time.perf_counter() - started

    assert elapsed >= duration_s * 0.85
    assert engine.played_block_durations_s == pytest.approx([duration_s])


def test_launcher_first_screen_is_four_option_environment_gate(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PIL import Image, ImageStat
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    errors: list[BaseException] = []
    remembered = tmp_path / "remembered"
    remembered.mkdir()

    monkeypatch.setattr(
        focus_app,
        "load_profile_runner_settings",
        lambda **_kwargs: {
            "active_profile_id": focus_app.STUDY5_PROFILE_ID,
            "active_output_folder": str(remembered),
            "participant_id": "P001",
        },
    )
    monkeypatch.setattr(
        focus_app,
        "load_runner_settings",
        lambda *args, **kwargs: {
            "last_experiment_name": "Study 5 gate test",
            "last_profile_id": focus_app.STUDY5_PROFILE_ID,
            "last_participant_id": "P001",
        },
    )
    monkeypatch.setattr(focus_app, "finished_profile_options", lambda: [(focus_app.STUDY5_PROFILE_ID, "Study 5")])
    monkeypatch.setattr(focus_app, "current_runner_diary_path", lambda: None)

    def inspect_launcher() -> None:
        try:
            dialogs = [widget for widget in app.topLevelWidgets() if widget.windowTitle() == "PPS Experiment Runner"]
            assert dialogs
            dialog = dialogs[0]
            assert dialog.findChild(q["QComboBox"], "participantCombo") is None
            output_field = dialog.findChild(q["QLineEdit"], "outputFolderField")
            assert output_field is not None
            assert output_field.isReadOnly()
            assert output_field.property("gateState") == "locked"
            profile_combo = dialog.findChild(q["QComboBox"], "environmentProfileCombo")
            assert profile_combo is not None
            assert not profile_combo.isEnabled()
            assert profile_combo.property("gateState") == "locked"
            session_field = dialog.findChild(q["QLineEdit"], "sessionNameField")
            assert session_field is not None
            assert session_field.isReadOnly()
            assert session_field.property("gateState") == "locked"
            step_label = dialog.findChild(q["QLabel"], "gateStepLabel")
            assert step_label is not None
            assert "Send To Phone" in step_label.text()
            assert step_label.property("attention") == "current"
            resume_button = dialog.findChild(q["QPushButton"], "resumeLastSessionButton")
            assert resume_button is not None
            assert resume_button.text() == "1 Resume Last Session"
            assert resume_button.property("decisionTone") == "resume"
            custom_button = dialog.findChild(q["QPushButton"], "resumeCustomSessionButton")
            assert custom_button is not None
            assert custom_button.text() == "2 Resume Custom Session"
            assert custom_button.property("decisionTone") == "custom"
            start_button = dialog.findChild(q["QPushButton"], "startNewSessionButton")
            assert start_button is not None
            assert start_button.text() == "3 Start New Session"
            assert start_button.property("decisionTone") == "start"
            phone_button = dialog.findChild(q["QPushButton"], "sendToPhoneButton")
            assert phone_button is not None
            assert phone_button.text() == "4 Send To Phone"
            assert phone_button.property("decisionTone") == "phone"
            assert dialog.findChild(q["QPushButton"], "initiateEnvironmentButton") is None
            assert dialog.findChild(q["QPushButton"], "chooseOutputFolderButton") is None
            for key in ("1", "2", "3", "4"):
                assert [
                    shortcut
                    for shortcut in dialog.findChildren(q["QShortcut"])
                    if shortcut.key().toString() == key
                ]
            assert 'decisionTone="start"' in dialog.styleSheet()
            swatch_dir = Path.cwd() / ".pytest_cache"
            swatch_dir.mkdir(parents=True, exist_ok=True)
            means = []
            for name, button in (
                ("resume", resume_button),
                ("custom", custom_button),
                ("start", start_button),
                ("phone", phone_button),
            ):
                path = swatch_dir / f"launcher_{name}_button.png"
                assert button.grab().save(str(path))
                means.append(tuple(round(value, 1) for value in ImageStat.Stat(Image.open(path).convert("RGB")).mean))
            assert len({tuple(int(value // 8) for value in mean) for mean in means}) == 4
            labels = _collect_widget_texts(dialog, q["QLabel"])
            assert labels.index("Output Folder") < labels.index("Experiment Profile")
            assert labels.index("Experiment Profile") < labels.index("Session Name")
            placeholders = [line.placeholderText() for line in dialog.findChildren(q["QLineEdit"])]
            assert "Participant ID" not in placeholders
            assert "1-10" not in placeholders
            button_labels = [button.text() for button in dialog.findChildren(q["QPushButton"])]
            assert "Generate Audio Assets" not in button_labels
            assert "Generate Range" not in button_labels
            assert "Run Selected Profile" not in button_labels
            assert "Initiate New Data Collection Environment" not in button_labels
            screenshot = Path.cwd() / ".pytest_cache" / "launcher_environment_gate.png"
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            assert dialog.grab().save(str(screenshot))
            image = Image.open(screenshot).convert("RGB")
            assert image.width >= 760
            assert image.height >= 520
            assert max(ImageStat.Stat(image).stddev) > 0.0
        except BaseException as exc:  # noqa: BLE001 - surfaced after the modal exits
            errors.append(exc)
        finally:
            for widget in app.topLevelWidgets():
                if widget.windowTitle() == "PPS Experiment Runner":
                    widget.reject()

    q["QTimer"].singleShot(50, inspect_launcher)
    exit_code = focus_app.run_launcher_window(
        capture_options=SessionCaptureOptions(enable_lsl=False, write_internal_xdf=False, start_backup_recording=False),
        participant_id="P001",
        initial_message="inspection",
    )
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    app.processEvents()

    assert exit_code == 1
    assert errors == []


def test_launcher_send_to_phone_click_opens_transfer_window(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    app.processEvents()
    errors: list[BaseException] = []
    calls: list[dict[str, object]] = []
    capture_options = SessionCaptureOptions(enable_lsl=False, write_internal_xdf=False, start_backup_recording=False)

    monkeypatch.setattr(
        focus_app,
        "load_profile_runner_settings",
        lambda **_kwargs: {
            "active_profile_id": focus_app.STUDY5_PROFILE_ID,
            "active_output_folder": str(tmp_path),
            "participant_id": "P321",
        },
    )
    monkeypatch.setattr(
        focus_app,
        "load_runner_settings",
        lambda *args, **kwargs: {
            "last_experiment_name": "Study 5 phone transfer",
            "last_profile_id": focus_app.STUDY5_PROFILE_ID,
            "last_participant_id": "P321",
        },
    )
    monkeypatch.setattr(focus_app, "finished_profile_options", lambda: [(focus_app.STUDY5_PROFILE_ID, "Study 5")])
    monkeypatch.setattr(focus_app, "current_runner_diary_path", lambda: None)

    def fake_phone_transfer_window(**kwargs):
        calls.append(kwargs)
        return 77

    monkeypatch.setattr(focus_app, "_run_phone_transfer_window", fake_phone_transfer_window)

    def reject_if_still_open() -> None:
        if calls or errors:
            return
        errors.append(AssertionError("Launcher Send To Phone click test timed out before handoff."))
        for widget in app.topLevelWidgets():
            if widget.windowTitle() == "PPS Experiment Runner":
                widget.reject()

    def click_send_to_phone() -> None:
        try:
            dialogs = [widget for widget in app.topLevelWidgets() if widget.windowTitle() == "PPS Experiment Runner"]
            assert dialogs
            dialog = dialogs[0]
            phone_button = dialog.findChild(q["QPushButton"], "sendToPhoneButton")
            assert phone_button is not None
            assert phone_button.isEnabled()
            QTest.mouseClick(phone_button, q["Qt"].MouseButton.LeftButton)
        except BaseException as exc:  # noqa: BLE001 - surfaced after modal exits
            errors.append(exc)
            for widget in app.topLevelWidgets():
                if widget.windowTitle() == "PPS Experiment Runner":
                    widget.reject()

    q["QTimer"].singleShot(50, click_send_to_phone)
    q["QTimer"].singleShot(1000, reject_if_still_open)
    exit_code = focus_app.run_launcher_window(
        capture_options=capture_options,
        participant_id="P321",
        initial_message="phone transfer click",
        companion_host="0.0.0.0",
        companion_port=8877,
        companion_advertise_ip="192.168.1.50",
    )
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    app.processEvents()

    assert errors == []
    assert exit_code == 77
    assert len(calls) == 1
    assert calls[0]["capture_options"] is capture_options
    assert calls[0]["companion_enabled"] is True
    assert calls[0]["companion_host"] == "0.0.0.0"
    assert calls[0]["companion_port"] == 8877
    assert calls[0]["companion_advertise_ip"] == "192.168.1.50"
    assert calls[0]["participant_id"] == "P321"


def test_phone_transfer_window_initial_layout_renders(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PIL import Image, ImageStat
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    app.processEvents()
    errors: list[BaseException] = []

    monkeypatch.setattr(
        focus_app,
        "load_profile_runner_settings",
        lambda **_kwargs: {
            "active_profile_id": focus_app.STUDY5_PROFILE_ID,
            "active_output_folder": str(tmp_path),
            "participant_id": "P001",
        },
    )
    monkeypatch.setattr(
        focus_app,
        "load_runner_settings",
        lambda *args, **kwargs: {
            "last_experiment_name": "Study 5 phone transfer",
            "last_profile_id": focus_app.STUDY5_PROFILE_ID,
            "last_participant_id": "P001",
        },
    )
    monkeypatch.setattr(focus_app, "current_runner_diary_path", lambda: None)
    monkeypatch.setattr(focus_app, "finished_profile_options", lambda: [(focus_app.STUDY5_PROFILE_ID, "Study 5")])
    monkeypatch.setattr(focus_app, "profile_participant_ids", lambda _profile: ["P001", "P002"])
    monkeypatch.setattr(
        focus_app,
        "_windows_wifi_direct_status",
        lambda: {"message": "Wi-Fi Direct test status.", "available": True},
    )

    def inspect_transfer_window() -> None:
        try:
            dialogs = [
                widget
                for widget in app.topLevelWidgets()
                if widget.windowTitle() == "PPS Experiment Runner - Send To Phone"
            ]
            assert dialogs
            dialog = dialogs[0]
            assert dialog.findChild(q["QComboBox"], "phoneTransferProfileCombo") is not None
            participant_combo = dialog.findChild(q["QComboBox"], "phoneTransferParticipantCombo")
            assert participant_combo is not None
            assert participant_combo.count() == 2
            assert dialog.findChild(q["QComboBox"], "phoneTransferTransportCombo") is not None
            assert dialog.findChild(q["QPushButton"], "phoneTransferPrepareButton") is not None
            assert dialog.findChild(q["QPushButton"], "phoneTransferStopButton") is not None
            lsl_target = dialog.findChild(q["QLineEdit"], "phoneTransferLslTargetField")
            lsl_command = dialog.findChild(q["QComboBox"], "phoneTransferLslCommandCombo")
            lsl_note = dialog.findChild(q["QLineEdit"], "phoneTransferLslOperatorNoteField")
            lsl_send = dialog.findChild(q["QPushButton"], "phoneTransferLslSendButton")
            assert lsl_target is not None
            assert lsl_command is not None
            assert lsl_note is not None
            assert lsl_send is not None
            commands = [lsl_command.itemData(index) for index in range(lsl_command.count())]
            assert commands == [
                "start_experiment",
                "start_part",
                "pause",
                "resume",
                "continue_instruction",
                "request_snapshot",
                "stop_after_block",
                "operator_note",
            ]
            assert lsl_note.isEnabled() is False
            assert lsl_send.isEnabled() is False
            assert dialog.findChild(q["QLabel"], "companionQrCode") is not None
            assert dialog.findChild(q["QLineEdit"], "phoneTransferPairingUriField") is not None
            screenshot = Path.cwd() / ".pytest_cache" / "phone_transfer_window.png"
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            assert dialog.grab().save(str(screenshot))
            image = Image.open(screenshot).convert("RGB")
            assert image.width >= 760
            assert image.height >= 620
            assert max(ImageStat.Stat(image).stddev) > 0.0
        except BaseException as exc:  # noqa: BLE001 - surfaced after the modal exits
            errors.append(exc)
        finally:
            for widget in app.topLevelWidgets():
                if widget.windowTitle() == "PPS Experiment Runner - Send To Phone":
                    widget.reject()

    q["QTimer"].singleShot(50, inspect_transfer_window)
    exit_code = focus_app._run_phone_transfer_window(
        participant_id="P001",
        initial_message="layout proof",
    )
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    app.processEvents()

    assert exit_code == 1
    assert errors == []


def test_phone_transfer_lsl_admin_context_prefers_part_session_and_runner_logs(tmp_path: Path):
    from peripersonal_space_toolkit import focus_app

    package = SimpleNamespace(
        participant_id="P321",
        session_id="session-001",
        session_group_id="group-001",
        part_session_id="part-001",
        part_number="01",
    )

    context = focus_app._phone_transfer_lsl_admin_context(
        [package],
        transfer_id="transfer-001",
        token="secret-token",
        output_root=tmp_path,
        participant_id="P321",
    )

    assert context["target_session_id"] == "part-001"
    assert context["token"] == "secret-token"
    assert context["package_id"] == "part-001-part01"
    assert context["participant_id"] == "P321"
    assert context["part_number"] == "01"
    assert context["target_part_session_id"] == "part-001"
    assert context["target_session_group_id"] == "group-001"
    assert str(output_runner_logs_dir(tmp_path) / "android_lsl_admin" / "transfer_001") == context["output_dir"]


def test_phone_transfer_lsl_admin_command_sends_expected_context(tmp_path: Path, monkeypatch):
    from peripersonal_space_toolkit import focus_app

    context = {
        "target_session_id": "part-001",
        "token": "secret-token",
        "package_id": "pkg-001",
        "participant_id": "P321",
        "part_number": "01",
        "target_part_session_id": "part-001",
        "target_session_group_id": "group-001",
        "output_dir": str(tmp_path / "pc-admin"),
    }
    calls: list[dict[str, object]] = []

    def fake_send_android_lsl_command(**kwargs):
        calls.append(dict(kwargs))
        return SimpleNamespace(row={"status": "ack_applied", "command": kwargs["command"], "outbox_path": "outbox.jsonl"})

    monkeypatch.setattr(focus_app, "send_android_lsl_command", fake_send_android_lsl_command)

    row = focus_app._send_phone_transfer_lsl_admin_command(context, "pause", require_ack=True)

    assert row["status"] == "ack_applied"
    assert calls == [
        {
            "target_session_id": "part-001",
            "token": "secret-token",
            "command": "pause",
            "package_id": "pkg-001",
            "participant_id": "P321",
            "target_part_session_id": "part-001",
            "target_session_group_id": "group-001",
            "part_number": "01",
            "extra_payload": {
                "target_session_id": "part-001",
                "target_part_session_id": "part-001",
                "target_session_group_id": "group-001",
            },
            "output_dir": tmp_path / "pc-admin",
            "require_ack": True,
        }
    ]


def test_phone_transfer_lsl_admin_command_forwards_operator_note(tmp_path: Path, monkeypatch):
    from peripersonal_space_toolkit import focus_app

    context = {
        "target_session_id": "part-001",
        "token": "secret-token",
        "package_id": "pkg-001",
        "participant_id": "P321",
        "part_number": "01",
        "target_part_session_id": "part-001",
        "target_session_group_id": "group-001",
        "output_dir": str(tmp_path / "pc-admin"),
    }
    calls: list[dict[str, object]] = []

    def fake_send_android_lsl_command(**kwargs):
        calls.append(dict(kwargs))
        return SimpleNamespace(row={"status": "ack_applied", "command": kwargs["command"], "outbox_path": "outbox.jsonl"})

    monkeypatch.setattr(focus_app, "send_android_lsl_command", fake_send_android_lsl_command)

    row = focus_app._send_phone_transfer_lsl_admin_command(
        context,
        "operator_note",
        require_ack=True,
        extra_payload={"note": "participant asked for a pause"},
    )

    assert row["status"] == "ack_applied"
    assert calls[-1]["command"] == "operator_note"
    assert calls[-1]["extra_payload"] == {
        "note": "participant asked for a pause",
        "target_session_id": "part-001",
        "target_part_session_id": "part-001",
        "target_session_group_id": "group-001",
    }


def test_launcher_resume_shortcut_opens_environment_operations(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    app.processEvents()
    errors: list[BaseException] = []
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        focus_app,
        "load_profile_runner_settings",
        lambda **_kwargs: {
            "active_profile_id": focus_app.STUDY5_PROFILE_ID,
            "active_output_folder": str(tmp_path),
            "participant_id": "P001",
        },
    )
    monkeypatch.setattr(
        focus_app,
        "load_runner_settings",
        lambda *args, **kwargs: {
            "last_experiment_name": "Study 5 gate test",
            "last_profile_id": focus_app.STUDY5_PROFILE_ID,
            "last_participant_id": "P001",
        },
    )
    monkeypatch.setattr(focus_app, "finished_profile_options", lambda: [(focus_app.STUDY5_PROFILE_ID, "Study 5")])
    monkeypatch.setattr(focus_app, "current_runner_diary_path", lambda: None)
    monkeypatch.setattr(focus_app, "find_output_diary", lambda _root: None)
    monkeypatch.setattr(focus_app, "remember_runner_context", lambda **_kwargs: {})
    monkeypatch.setattr(focus_app, "update_profile_runner_settings", lambda **_kwargs: {})
    monkeypatch.setattr(focus_app, "_append_output_diary_event", lambda *args, **kwargs: None)

    def fake_environment_operations_window(**kwargs):
        calls.append(kwargs)
        return 58

    monkeypatch.setattr(focus_app, "_run_environment_operations_window", fake_environment_operations_window)

    resume_attempts = {"count": 0}

    def reject_if_still_open() -> None:
        if calls or errors:
            return
        errors.append(AssertionError("Launcher resume shortcut test timed out before the dialog closed."))
        for widget in app.topLevelWidgets():
            if widget.windowTitle() == "PPS Experiment Runner":
                widget.reject()

    def click_resume() -> None:
        try:
            dialogs = [
                widget
                for widget in app.topLevelWidgets()
                if widget.windowTitle() == "PPS Experiment Runner"
                and widget.isVisible()
                and widget.findChild(q["QPushButton"], "resumeLastSessionButton") is not None
            ]
            if not dialogs and resume_attempts["count"] < 20:
                resume_attempts["count"] += 1
                q["QTimer"].singleShot(50, click_resume)
                return
            assert dialogs
            dialog = dialogs[0]
            assert dialog.findChild(q["QComboBox"], "participantCombo") is None
            resume = dialog.findChild(q["QPushButton"], "resumeLastSessionButton")
            assert resume is not None
            assert resume.isEnabled()
            resume_shortcuts = [
                shortcut
                for shortcut in dialog.findChildren(q["QShortcut"])
                if shortcut.key().toString() == "1"
            ]
            assert resume_shortcuts
            assert resume_shortcuts[0].isEnabled()
            resume_shortcuts[0].activated.emit()
        except BaseException as exc:  # noqa: BLE001 - surfaced after the modal exits
            errors.append(exc)
            for widget in app.topLevelWidgets():
                if widget.windowTitle() == "PPS Experiment Runner":
                    widget.reject()

    q["QTimer"].singleShot(50, click_resume)
    q["QTimer"].singleShot(3000, reject_if_still_open)
    exit_code = focus_app.run_launcher_window(
        capture_options=SessionCaptureOptions(enable_lsl=False, write_internal_xdf=False, start_backup_recording=False),
        participant_id="P001",
    )
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    app.processEvents()

    assert exit_code == 58
    assert errors == []
    assert len(calls) == 1
    assert calls[0]["participant_id"] == "P001"


def test_launcher_resume_custom_rejects_empty_folder_without_new_session_prompts(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PIL import Image, ImageStat
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    errors: list[BaseException] = []
    remembered = tmp_path / "remembered"
    remembered.mkdir()
    empty_folder = tmp_path / "empty_folder"
    empty_folder.mkdir()

    monkeypatch.setattr(
        focus_app,
        "load_profile_runner_settings",
        lambda **_kwargs: {
            "active_profile_id": focus_app.STUDY5_PROFILE_ID,
            "active_output_folder": str(remembered),
            "participant_id": "P001",
        },
    )
    monkeypatch.setattr(
        focus_app,
        "load_runner_settings",
        lambda *args, **kwargs: {
            "last_experiment_name": "Remembered Study",
            "last_profile_id": focus_app.STUDY5_PROFILE_ID,
            "last_participant_id": "P001",
        },
    )
    monkeypatch.setattr(focus_app, "finished_profile_options", lambda: [(focus_app.STUDY5_PROFILE_ID, "Study 5")])
    monkeypatch.setattr(focus_app, "current_runner_diary_path", lambda: None)
    monkeypatch.setattr(q["QFileDialog"], "getExistingDirectory", lambda *args, **kwargs: str(empty_folder))

    def pick_empty_folder_and_inspect() -> None:
        try:
            dialogs = [widget for widget in app.topLevelWidgets() if widget.windowTitle() == "PPS Experiment Runner"]
            assert dialogs
            dialog = dialogs[0]
            custom_button = dialog.findChild(q["QPushButton"], "resumeCustomSessionButton")
            assert custom_button is not None
            QTest.mouseClick(custom_button, q["Qt"].MouseButton.LeftButton)
            app.processEvents()

            output_field = dialog.findChild(q["QLineEdit"], "outputFolderField")
            profile_combo = dialog.findChild(q["QComboBox"], "environmentProfileCombo")
            session_field = dialog.findChild(q["QLineEdit"], "sessionNameField")
            start_dialog = dialog.findChild(q["QDialog"], "startNewSessionDialog")
            message_label = dialog.findChild(q["QLabel"], "gateStatusLabel")
            assert output_field is not None
            assert profile_combo is not None
            assert session_field is not None
            assert message_label is not None
            assert start_dialog is None
            assert Path(output_field.text()) == remembered
            assert output_field.isReadOnly()
            assert not profile_combo.isEnabled()
            assert session_field.isReadOnly()
            assert "No PPS session metadata" in message_label.text()

            screenshot = Path.cwd() / ".pytest_cache" / "launcher_gate_custom_empty_rejected.png"
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            assert dialog.grab().save(str(screenshot))
            image = Image.open(screenshot).convert("RGB")
            assert image.width >= 760
            assert image.height >= 480
            assert max(ImageStat.Stat(image).stddev) > 0.0
        except BaseException as exc:  # noqa: BLE001 - surfaced after the modal exits
            errors.append(exc)
        finally:
            for widget in app.topLevelWidgets():
                if widget.windowTitle() == "PPS Experiment Runner":
                    widget.reject()

    q["QTimer"].singleShot(50, pick_empty_folder_and_inspect)
    exit_code = focus_app.run_launcher_window(
        capture_options=SessionCaptureOptions(enable_lsl=False, write_internal_xdf=False, start_backup_recording=False),
        participant_id="P001",
    )
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    app.processEvents()

    assert exit_code == 1
    assert errors == []


def test_launcher_start_new_session_modal_creates_environment_and_opens_operations(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    errors: list[BaseException] = []
    calls: list[dict[str, object]] = []
    operation_calls: list[dict[str, object]] = []
    remembered = tmp_path / "remembered"
    remembered.mkdir()
    new_parent = tmp_path / "fresh_parent"
    new_parent.mkdir()
    environment_root = new_parent / "hoi_20260624_022151"
    diary_path = environment_root / "Experiment_context_folder_DO_NOT_DELETE" / "runner_logs" / "hoi_LOG-DIARY_DO_NOT_DELETE.txt"

    monkeypatch.setattr(
        focus_app,
        "load_profile_runner_settings",
        lambda **_kwargs: {
            "active_profile_id": focus_app.STUDY5_PROFILE_ID,
            "active_output_folder": str(remembered),
            "participant_id": "P001",
        },
    )
    monkeypatch.setattr(
        focus_app,
        "load_runner_settings",
        lambda *args, **kwargs: {
            "last_experiment_name": "Remembered Study",
            "last_profile_id": focus_app.STUDY5_PROFILE_ID,
            "last_participant_id": "P001",
        },
    )
    monkeypatch.setattr(focus_app, "finished_profile_options", lambda: [(focus_app.STUDY5_PROFILE_ID, "Study 5")])
    monkeypatch.setattr(focus_app, "current_runner_diary_path", lambda: None)
    monkeypatch.setattr(q["QFileDialog"], "getExistingDirectory", lambda *args, **kwargs: str(new_parent))

    def fake_initiate_environment(**kwargs):
        calls.append(kwargs)
        callback = kwargs.get("progress_callback")
        if callback:
            callback({"message": "Creating output environment", "detail": str(kwargs["parent_folder"]), "current": 1, "total": 4})
        environment_root.mkdir(parents=True, exist_ok=True)
        return {
            "environment_root": str(environment_root),
            "diary_path": str(diary_path),
            "profile_id": kwargs["profile_id"],
            "session_name": kwargs["session_name"],
            "participant_id": kwargs["participant_id"],
            "bridge": {"bridge_manifest_path": str(environment_root / "bridge.json")},
            "prepared_participants": {"prepared_count": 1},
        }

    def fake_environment_operations_window(**kwargs):
        operation_calls.append(kwargs)
        return 60

    monkeypatch.setattr(focus_app, "initiate_data_collection_environment", fake_initiate_environment)
    monkeypatch.setattr(focus_app, "_run_environment_operations_window", fake_environment_operations_window)

    def reject_if_still_open() -> None:
        if calls or errors:
            return
        errors.append(AssertionError("Launcher initiate click test timed out before the worker started."))
        for widget in app.topLevelWidgets():
            if widget.windowTitle() == "PPS Experiment Runner":
                widget.reject()

    def fill_start_new_dialog() -> None:
        try:
            dialogs = [widget for widget in app.topLevelWidgets() if widget.objectName() == "startNewSessionDialog"]
            assert dialogs
            setup_dialog = dialogs[0]
            parent_button = setup_dialog.findChild(q["QPushButton"], "newSessionParentButton")
            parent_field = setup_dialog.findChild(q["QLineEdit"], "newSessionParentField")
            profile_combo = setup_dialog.findChild(q["QComboBox"], "newSessionProfileCombo")
            session_field = setup_dialog.findChild(q["QLineEdit"], "newSessionNameField")
            create_button = setup_dialog.findChild(q["QPushButton"], "createNewSessionButton")
            assert parent_button is not None
            assert parent_field is not None
            assert profile_combo is not None
            assert session_field is not None
            assert create_button is not None

            QTest.mouseClick(parent_button, q["Qt"].MouseButton.LeftButton)
            app.processEvents()
            assert Path(parent_field.text()) == new_parent
            profile_index = profile_combo.findData(focus_app.STUDY5_PROFILE_ID)
            assert profile_index >= 0
            profile_combo.setCurrentIndex(profile_index)
            session_field.setText("hoi")
            app.processEvents()
            assert create_button.isEnabled()
            screenshot = Path.cwd() / ".pytest_cache" / "launcher_start_new_session_dialog.png"
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            assert setup_dialog.grab().save(str(screenshot))
            QTest.mouseClick(create_button, q["Qt"].MouseButton.LeftButton)
        except BaseException as exc:  # noqa: BLE001 - surfaced after the modal exits
            errors.append(exc)
            for widget in app.topLevelWidgets():
                if widget.windowTitle() == "PPS Experiment Runner":
                    widget.reject()

    def click_start_new() -> None:
        try:
            dialogs = [widget for widget in app.topLevelWidgets() if widget.windowTitle() == "PPS Experiment Runner"]
            assert dialogs
            dialog = dialogs[0]
            start_button = dialog.findChild(q["QPushButton"], "startNewSessionButton")
            assert start_button is not None
            assert dialog.findChild(q["QDialog"], "startNewSessionDialog") is None
            q["QTimer"].singleShot(100, fill_start_new_dialog)
            QTest.mouseClick(start_button, q["Qt"].MouseButton.LeftButton)
            app.processEvents()
        except BaseException as exc:  # noqa: BLE001 - surfaced after the modal exits
            errors.append(exc)
            for widget in app.topLevelWidgets():
                if widget.windowTitle() == "PPS Experiment Runner":
                    widget.reject()

    q["QTimer"].singleShot(50, click_start_new)
    q["QTimer"].singleShot(3000, reject_if_still_open)
    exit_code = focus_app.run_launcher_window(
        capture_options=SessionCaptureOptions(enable_lsl=False, write_internal_xdf=False, start_backup_recording=False),
        participant_id="P001",
    )
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    app.processEvents()

    assert exit_code == 60
    assert errors == []
    assert len(calls) == 1
    assert calls[0]["parent_folder"] == new_parent
    assert calls[0]["profile_id"] == focus_app.STUDY5_PROFILE_ID
    assert calls[0]["session_name"] == "hoi"
    assert calls[0]["participant_id"] == "P001"
    assert len(operation_calls) == 1
    assert operation_calls[0]["participant_id"] == "P001"


def test_launcher_resume_custom_session_folder_opens_operations_immediately(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PIL import Image, ImageStat
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    errors: list[BaseException] = []
    calls: list[dict[str, object]] = []
    remembered = tmp_path / "remembered"
    remembered.mkdir()
    existing_env = tmp_path / "existing_environment"
    existing_env.mkdir()
    (existing_env / focus_app.BRIDGE_MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "schema": "pps-dashboard-runner-bridge-manifest.v1",
                "profile_id": focus_app.STUDY5_PROFILE_ID,
                "display_name": "Existing Salience Study",
                "participant_id": "P009",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (existing_env / focus_app.OUTPUT_DIARY_FILENAME).write_text(
        json.dumps(
            {
                "schema": "pps-output-diary-event.v1",
                "event_type": "data_collection_environment_initiated",
                "profile_id": focus_app.STUDY5_PROFILE_ID,
                "participant_id": "P009",
                "session_name": "Output Diary Study",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        focus_app,
        "load_profile_runner_settings",
        lambda **_kwargs: {
            "active_profile_id": focus_app.STUDY5_PROFILE_ID,
            "active_output_folder": str(remembered),
            "participant_id": "P001",
        },
    )
    monkeypatch.setattr(
        focus_app,
        "load_runner_settings",
        lambda *args, **kwargs: {
            "last_experiment_name": "Remembered Study",
            "last_profile_id": focus_app.STUDY5_PROFILE_ID,
            "last_participant_id": "P001",
        },
    )
    monkeypatch.setattr(focus_app, "finished_profile_options", lambda: [(focus_app.STUDY5_PROFILE_ID, "Study 5")])
    monkeypatch.setattr(focus_app, "current_runner_diary_path", lambda: None)
    monkeypatch.setattr(q["QFileDialog"], "getExistingDirectory", lambda *args, **kwargs: str(existing_env))
    monkeypatch.setattr(focus_app, "remember_runner_context", lambda **_kwargs: {})
    monkeypatch.setattr(focus_app, "update_profile_runner_settings", lambda **_kwargs: {})
    monkeypatch.setattr(focus_app, "_append_output_diary_event", lambda *args, **kwargs: None)

    def fake_environment_operations_window(**kwargs):
        calls.append(kwargs)
        return 59

    monkeypatch.setattr(focus_app, "_run_environment_operations_window", fake_environment_operations_window)

    def pick_existing_and_resume() -> None:
        try:
            dialogs = [widget for widget in app.topLevelWidgets() if widget.windowTitle() == "PPS Experiment Runner"]
            assert dialogs
            dialog = dialogs[0]
            custom_button = dialog.findChild(q["QPushButton"], "resumeCustomSessionButton")
            assert custom_button is not None
            QTest.mouseClick(custom_button, q["Qt"].MouseButton.LeftButton)
            app.processEvents()
        except BaseException as exc:  # noqa: BLE001 - surfaced after the modal exits
            errors.append(exc)
            for widget in app.topLevelWidgets():
                if widget.windowTitle() == "PPS Experiment Runner":
                    widget.reject()

    q["QTimer"].singleShot(50, pick_existing_and_resume)
    exit_code = focus_app.run_launcher_window(
        capture_options=SessionCaptureOptions(enable_lsl=False, write_internal_xdf=False, start_backup_recording=False),
        participant_id="P001",
    )
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    app.processEvents()

    assert exit_code == 59
    assert errors == []
    assert len(calls) == 1
    assert calls[0]["participant_id"] == "P009"


def test_main_no_args_opens_resume_environment_gate(monkeypatch):
    from peripersonal_space_toolkit import focus_app

    calls: list[dict[str, object]] = []
    released: list[bool] = []

    def fake_launcher(**kwargs):
        calls.append(kwargs)
        return 37

    class FakeSingleInstance:
        acquired = True
        message = ""

        def release(self):
            released.append(True)

    monkeypatch.setattr(focus_app, "_acquire_runner_single_instance", lambda: FakeSingleInstance())
    monkeypatch.setattr(focus_app, "run_launcher_window", fake_launcher)
    monkeypatch.setattr(
        focus_app,
        "prepare_last_or_latest_focus_session",
        lambda *_args, **_kwargs: pytest.fail("no-argument launch must not auto-resume"),
    )
    monkeypatch.setattr(
        focus_app,
        "run_focus_window",
        lambda *_args, **_kwargs: pytest.fail("no-argument launch must not open Focus Mode directly"),
    )

    assert focus_app.main([]) == 37
    assert len(calls) == 1
    assert calls[0]["participant_id"] == ""
    assert released == [True]


def test_main_blocks_when_experiment_runner_already_open(monkeypatch):
    from peripersonal_space_toolkit import focus_app

    notices: list[str] = []

    monkeypatch.setattr(
        focus_app,
        "_acquire_runner_single_instance",
        lambda: focus_app._RunnerSingleInstance(acquired=False, message="runner already open"),
    )
    monkeypatch.setattr(focus_app, "_show_runner_single_instance_notice", notices.append)
    monkeypatch.setattr(
        focus_app,
        "run_launcher_window",
        lambda **_kwargs: pytest.fail("second runner launch must not open the launcher"),
    )
    monkeypatch.setattr(
        focus_app,
        "run_focus_window",
        lambda *_args, **_kwargs: pytest.fail("second runner launch must not open Focus Mode"),
    )

    assert focus_app.main([]) == focus_app.SINGLE_INSTANCE_EXIT_CODE
    assert notices == ["runner already open"]


def test_main_last_experiment_flag_keeps_explicit_direct_resume(tmp_path: Path, monkeypatch):
    from peripersonal_space_toolkit import focus_app

    manifest = tmp_path / "session_manifest.json"
    calls: dict[str, object] = {}
    released: list[bool] = []

    class FakeSingleInstance:
        acquired = True
        message = ""

        def release(self):
            released.append(True)

    def fake_prepare(participant_id=None, **kwargs):
        calls["participant_id"] = participant_id
        calls["prepare_kwargs"] = kwargs
        return manifest

    def fake_focus_window(path, **kwargs):
        calls["focus_path"] = path
        calls["focus_kwargs"] = kwargs
        return 41

    monkeypatch.setattr(focus_app, "prepare_last_or_latest_focus_session", fake_prepare)
    monkeypatch.setattr(focus_app, "run_focus_window", fake_focus_window)
    monkeypatch.setattr(focus_app, "_acquire_runner_single_instance", lambda: FakeSingleInstance())
    monkeypatch.setattr(
        focus_app,
        "run_launcher_window",
        lambda **_kwargs: pytest.fail("--last-experiment should remain an explicit gate bypass"),
    )

    assert focus_app.main(["--last-experiment", "--participant-id", "P007", "--manual-start"]) == 41
    assert calls["participant_id"] == "P007"
    assert calls["focus_path"] == manifest
    assert calls["focus_kwargs"]["manual_start"] is True
    assert released == [True]


def test_audio_dependency_dialog_retry_accepts_after_asio_detected(monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
        from peripersonal_space_toolkit.audio_routing import AudioRuntimeReadiness
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    errors: list[BaseException] = []

    missing = AudioRuntimeReadiness(
        ready=False,
        publication_ready=False,
        severity="error",
        summary="Audio preflight: Komplete Audio ASIO is missing.",
        details=("ASIO is visible, but no output exposes at least three synchronized channels.",),
        actions=(),
        sounddevice_available=True,
        sounddevice_version="0.4.7",
        asio_hostapi_present=True,
        preferred_devices=(),
        fallback_devices=(),
    )
    ready = AudioRuntimeReadiness(
        ready=True,
        publication_ready=True,
        severity="ok",
        summary="Audio preflight: validated Komplete multichannel ASIO output is visible.",
        details=("[3] Komplete Audio ASIO Driver (ASIO, 6 out)",),
        actions=(),
        sounddevice_available=True,
        sounddevice_version="0.4.7",
        asio_hostapi_present=True,
        preferred_devices=("[3] Komplete Audio ASIO Driver (ASIO, 6 out)",),
        fallback_devices=(),
    )
    monkeypatch.setattr(focus_app, "assess_audio_runtime_readiness", lambda: ready)

    def click_retry() -> None:
        try:
            dialogs = [widget for widget in app.topLevelWidgets() if widget.objectName() == "audioDependencyDialog"]
            assert dialogs
            dialog = dialogs[0]
            labels = _collect_widget_texts(dialog, q["QLabel"])
            assert any("Komplete Audio ASIO driver required" in label for label in labels)
            assert any("Retry Audio Detection" in label for label in labels)
            retry = dialog.findChild(q["QPushButton"], "retryAudioDetectionButton")
            assert retry is not None
            QTest.mouseClick(retry, q["Qt"].MouseButton.LeftButton)
        except BaseException as exc:  # noqa: BLE001 - surfaced after the modal exits
            errors.append(exc)
            for widget in app.topLevelWidgets():
                if widget.objectName() == "audioDependencyDialog":
                    widget.reject()

    q["QTimer"].singleShot(50, click_retry)
    assert focus_app._show_audio_dependency_dialog(q, readiness=missing) is True
    assert errors == []


def test_unvalidated_audio_route_confirmation_window_accepts_continue(monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    errors: list[BaseException] = []
    display_device = "Speakers (Nahimic Easy Surround)"

    def click_confirmation() -> None:
        try:
            confirms = [widget for widget in app.topLevelWidgets() if widget.objectName() == "unvalidatedAudioRouteConfirmDialog"]
            assert confirms
            confirm = confirms[0]
            assert "not calibrated" in confirm.informativeText()
            assert display_device in confirm.informativeText()
            assert "[44]" not in confirm.informativeText()
            assert "left=Output 4, right=Output 4, tactile=Output 6" in confirm.informativeText()
            buttons = confirm.findChildren(q["QPushButton"])
            continue_button = next(button for button in buttons if button.text() == "Continue Without Komplete Interface")
            QTest.mouseClick(continue_button, q["Qt"].MouseButton.LeftButton)
        except BaseException as exc:  # noqa: BLE001 - surfaced after the modal exits
            errors.append(exc)
            for widget in app.topLevelWidgets():
                if widget.objectName() == "unvalidatedAudioRouteConfirmDialog":
                    widget.reject()

    parent = q["QDialog"]()
    parent.setObjectName("unvalidatedConfirmParent")
    q["QTimer"].singleShot(50, click_confirmation)
    assert focus_app._confirm_unvalidated_audio_route(q, parent=parent, label=display_device, channels=(4, 4, 6)) is True
    parent.close()
    parent.deleteLater()
    app.processEvents()
    assert errors == []


def test_audio_dependency_dialog_user_selected_system_route_sets_audio_env_after_confirmation(monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.delenv("PPS_AUDIO_DEVICE_INDEX", raising=False)
    monkeypatch.delenv("PPS_AUDIO_OUTPUT_CHANNELS", raising=False)
    monkeypatch.delenv("PPS_AUDIO_UNVALIDATED_ROUTE_FROM_DIALOG", raising=False)
    try:
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
        from peripersonal_space_toolkit.audio_routing import AudioRuntimeReadiness
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    for widget in app.topLevelWidgets():
        if widget.objectName() in {"audioDependencyDialog", "unvalidatedAudioRouteConfirmDialog", "unvalidatedConfirmParent"}:
            widget.close()
            widget.deleteLater()
    app.processEvents()
    errors: list[BaseException] = []
    fallback = (
        "[44] Speakers (Nahimic Easy Surround) "
        "(Windows WDM-KS, 8 out; outputs 1-8 available; PPS uses 1=L, 2=R, 3=tactile)"
    )
    confirm_calls: list[str] = []
    missing_with_fallback = AudioRuntimeReadiness(
        ready=False,
        publication_ready=False,
        severity="error",
        summary=(
            "Audio preflight: Komplete Audio ASIO driver is installed, but the Komplete Audio 6 MK2 interface "
            "is not exposing a 3+ channel ASIO output."
        ),
        details=(
            "Komplete Audio ASIO Driver is installed/registered in Windows, but the Komplete Audio 6 MK2 interface "
            "is not connected or not ready as a usable 3+ channel ASIO device.",
            f"Non-ASIO multichannel output is visible, but not valid for PPS timing claims: {fallback}",
        ),
        actions=(),
        sounddevice_available=True,
        sounddevice_version="0.5.5",
        asio_hostapi_present=True,
        preferred_devices=(),
        fallback_devices=(fallback,),
        komplete_asio_driver_registered=True,
        unvalidated_output_devices=(fallback,),
    )

    def fake_confirm(q_arg, *, parent, label, channels):
        assert q_arg is q
        assert parent.objectName() == "audioDependencyDialog"
        confirm_calls.append(f"{label}|{channels}")
        return True

    monkeypatch.setattr(focus_app, "_confirm_unvalidated_audio_route", fake_confirm)

    def click_unvalidated_route() -> None:
        try:
            dialogs = [widget for widget in app.topLevelWidgets() if widget.objectName() == "audioDependencyDialog"]
            assert dialogs
            dialog = dialogs[0]
            labels = _collect_widget_texts(dialog, q["QLabel"])
            assert any("Komplete Audio 6 MK2 interface not detected" in label for label in labels)
            assert any("Unvalidated pretest route" in label for label in labels)
            assert any("Left (default 1)" in label for label in labels)
            assert any("Right (default 2)" in label for label in labels)
            assert any("Tactile (default 3)" in label for label in labels)
            assert dialog.findChild(q["QComboBox"], "unvalidatedAudioDeviceCombo") is None
            left = dialog.findChild(q["QComboBox"], "unvalidatedLeftChannelCombo")
            right = dialog.findChild(q["QComboBox"], "unvalidatedRightChannelCombo")
            tactile = dialog.findChild(q["QComboBox"], "unvalidatedTactileChannelCombo")
            assert left is not None and right is not None and tactile is not None
            assert left.count() == 8
            assert right.count() == 8
            assert tactile.count() == 8
            assert left.itemText(0) == "Speakers (Nahimic Easy Surround) - Output 1"
            assert right.itemText(1) == "Speakers (Nahimic Easy Surround) - Output 2"
            assert tactile.itemText(2) == "Speakers (Nahimic Easy Surround) - Output 3"
            assert left.itemData(0)[:2] == (44, 1)
            assert right.itemData(1)[:2] == (44, 2)
            assert tactile.itemData(2)[:2] == (44, 3)
            left.setCurrentIndex(next(index for index in range(left.count()) if left.itemData(index)[:2] == (44, 4)))
            right.setCurrentIndex(next(index for index in range(right.count()) if right.itemData(index)[:2] == (44, 4)))
            tactile.setCurrentIndex(next(index for index in range(tactile.count()) if tactile.itemData(index)[:2] == (44, 6)))
            button = dialog.findChild(q["QPushButton"], "useUnvalidatedAudioRouteButton")
            assert button is not None
            assert button.text() == "Accept Pretest Settings"
            QTest.mouseClick(button, q["Qt"].MouseButton.LeftButton)
        except BaseException as exc:  # noqa: BLE001 - surfaced after the modal exits
            errors.append(exc)
            for widget in app.topLevelWidgets():
                if widget.objectName() == "audioDependencyDialog":
                    widget.reject()

    q["QTimer"].singleShot(50, click_unvalidated_route)
    assert focus_app._show_audio_dependency_dialog(q, readiness=missing_with_fallback) is True
    assert confirm_calls == [f"Speakers (Nahimic Easy Surround)|{(4, 4, 6)}"]
    assert os.environ["PPS_AUDIO_DEVICE_INDEX"] == "44"
    assert os.environ["PPS_AUDIO_OUTPUT_CHANNELS"] == "4,4,6"
    assert os.environ["PPS_AUDIO_UNVALIDATED_ROUTE_FROM_DIALOG"] == "1"
    assert errors == []


def test_launcher_generate_range_button_prepares_requested_range(monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    participants = ["P001", "P002", "P003"]
    calls: list[tuple[str, list[str]]] = []
    errors: list[BaseException] = []

    monkeypatch.setattr(focus_app, "finished_profile_options", lambda: [(focus_app.STUDY5_PROFILE_ID, "Study 5")])
    monkeypatch.setattr(focus_app, "profile_participant_ids", lambda _profile: participants)
    monkeypatch.setattr(
        focus_app,
        "profile_participant_asset_statuses",
        lambda _profile, **_kwargs: {
            participant: {
                "participant_id": participant,
                "generated": participant != "P003",
                "status": "generated" if participant != "P003" else "not_generated",
                "data_collected": False,
            }
            for participant in participants
        },
    )

    def fake_prepare_profile_audio_assets(profile_id, participant_ids, *, session_root=None, progress_callback=None):
        calls.append((profile_id, list(participant_ids)))
        if progress_callback is not None:
            progress_callback({"message": "Fake range generation", "current": len(participant_ids), "total": len(participant_ids)})
        return {
            "profile_id": profile_id,
            "participant_count": len(participant_ids),
            "prepared_count": 1,
            "reused_count": 2,
            "results": [],
        }

    monkeypatch.setattr(focus_app, "prepare_profile_audio_assets", fake_prepare_profile_audio_assets)

    def inspect_launcher() -> None:
        try:
            dialogs = [
                widget
                for widget in app.topLevelWidgets()
                if widget.windowTitle() == "PPS Experiment Runner" and widget.findChild(q["QComboBox"], "participantCombo") is not None
            ]
            assert dialogs
            dialog = dialogs[0]
            range_inputs = [line for line in dialog.findChildren(q["QLineEdit"]) if line.placeholderText() == "1-10"]
            assert range_inputs
            range_buttons = [button for button in dialog.findChildren(q["QPushButton"]) if button.text() == "Generate Range"]
            assert range_buttons
            range_inputs[0].setText("1-3")
            QTest.mouseClick(range_buttons[0], q["Qt"].MouseButton.LeftButton)

            def verify_and_close() -> None:
                try:
                    assert calls == [(focus_app.STUDY5_PROFILE_ID, participants)]
                    labels = _collect_widget_texts(dialog, q["QLabel"])
                    assert any("Audio assets ready: 1 generated, 2 already available" in label for label in labels)
                except BaseException as exc:  # noqa: BLE001 - surfaced after the modal exits
                    errors.append(exc)
                finally:
                    dialog.reject()

            q["QTimer"].singleShot(600, verify_and_close)
        except BaseException as exc:  # noqa: BLE001 - surfaced after the modal exits
            errors.append(exc)
            for widget in app.topLevelWidgets():
                if widget.windowTitle() == "PPS Experiment Runner":
                    widget.reject()

    q["QTimer"].singleShot(50, inspect_launcher)
    exit_code = focus_app._run_environment_operations_window(
        capture_options=SessionCaptureOptions(enable_lsl=False, write_internal_xdf=False, start_backup_recording=False),
        participant_id="P001",
        initial_message="inspection",
    )

    assert exit_code == 1
    assert errors == []


def test_prepare_profile_focus_session_uses_finished_profile_gate(tmp_path: Path, monkeypatch):
    from peripersonal_space_toolkit import focus_app

    manifest = tmp_path / "sessions" / "P123_run" / "session_manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}", encoding="utf-8")
    run_setup = tmp_path / "profile" / "6_experiment_run_setup" / "experiment_run_setup_manifest.json"
    run_setup.parent.mkdir(parents=True)
    run_setup.write_text("{}", encoding="utf-8")
    calls: dict[str, object] = {}

    monkeypatch.setattr(
        focus_app,
        "_materialize_profile_run_setup",
        lambda profile_id, progress_callback=None: (
            SimpleNamespace(design_path=tmp_path / "design.json"),
            SimpleNamespace(),
            run_setup,
        ),
    )
    monkeypatch.setattr(focus_app, "claim_prepared_session", lambda *_args, **_kwargs: None)

    def fake_prepare_segment_run_package(run_setup_path, participant_id, **kwargs):
        calls["run_setup_path"] = run_setup_path
        calls["participant_id"] = participant_id
        calls["prepare_kwargs"] = dict(kwargs)
        return SimpleNamespace(
            manifest_path=manifest,
            source_run_setup_manifest_path=run_setup,
            session_dir=manifest.parent,
            blocks=[object()],
        )

    monkeypatch.setattr(focus_app, "prepare_segment_run_package", fake_prepare_segment_run_package)
    monkeypatch.setattr(focus_app, "record_prepared_session_queue", lambda **kwargs: calls.setdefault("queue", kwargs))
    monkeypatch.setattr(focus_app, "record_experiment_activity", lambda *args, **kwargs: calls.setdefault("activity", (args, kwargs)))
    monkeypatch.setattr(
        focus_app,
        "resolve_profile_entry",
        lambda *_args, **_kwargs: {"kind": "bundled", "dashboard_project_id": "profile_study5_box_breathing_pps"},
    )
    monkeypatch.setattr(focus_app, "update_profile_runner_settings", lambda **kwargs: calls.setdefault("settings", kwargs))

    assert (
        focus_app.prepare_profile_focus_session(
            "study5_box_breathing_pps",
            "P123",
            session_root=tmp_path / "isolated_output",
        )
        == manifest
    )
    assert calls["run_setup_path"] == run_setup
    assert calls["participant_id"] == "P123"
    assert calls["queue"]["participant_id"] == "P123"
    assert calls["settings"]["profile_id"] == "study5_box_breathing_pps"


def test_prepare_profile_focus_session_honors_validation_output_root(tmp_path: Path, monkeypatch):
    from peripersonal_space_toolkit import focus_app

    validation_root = tmp_path / "validation_runner_sessions"
    remembered_root = tmp_path / "remembered_dashboard_output"
    manifest = validation_root / "P124_run" / "session_manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}", encoding="utf-8")
    run_setup = tmp_path / "profile" / "6_experiment_run_setup" / "experiment_run_setup_manifest.json"
    run_setup.parent.mkdir(parents=True)
    run_setup.write_text("{}", encoding="utf-8")
    calls: dict[str, object] = {}

    monkeypatch.setenv("PPS_FOCUS_VALIDATION_OUTPUT_ROOT", str(validation_root))
    monkeypatch.setattr(focus_app, "active_output_folder", lambda **_kwargs: remembered_root)
    monkeypatch.setattr(
        focus_app,
        "_materialize_profile_run_setup",
        lambda profile_id, progress_callback=None: (
            SimpleNamespace(design_path=tmp_path / "design.json"),
            SimpleNamespace(),
            run_setup,
        ),
    )
    monkeypatch.setattr(focus_app, "claim_prepared_session", lambda *_args, **_kwargs: None)

    def fake_prepare_segment_run_package(run_setup_path, participant_id, **kwargs):
        calls["run_setup_path"] = run_setup_path
        calls["participant_id"] = participant_id
        calls["prepare_kwargs"] = dict(kwargs)
        return SimpleNamespace(
            manifest_path=manifest,
            source_run_setup_manifest_path=run_setup,
            session_dir=manifest.parent,
            blocks=[object()],
        )

    monkeypatch.setattr(focus_app, "prepare_segment_run_package", fake_prepare_segment_run_package)
    monkeypatch.setattr(focus_app, "record_prepared_session_queue", lambda **kwargs: calls.setdefault("queue", kwargs))
    monkeypatch.setattr(focus_app, "record_experiment_activity", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        focus_app,
        "resolve_profile_entry",
        lambda *_args, **_kwargs: {"kind": "bundled", "dashboard_project_id": "profile_study5_box_breathing_pps"},
    )
    monkeypatch.setattr(focus_app, "update_profile_runner_settings", lambda **kwargs: calls.setdefault("settings", kwargs))

    assert focus_app.prepare_profile_focus_session("study5_box_breathing_pps", "P124") == manifest
    assert calls["prepare_kwargs"]["session_root"] == validation_root
    assert calls["settings"]["output_folder"] == validation_root


def test_runner_output_project_setting_creates_timestamped_folder(tmp_path: Path, monkeypatch):
    from peripersonal_space_toolkit import focus_app

    state_root = tmp_path / "state"
    parent = tmp_path / "operator_outputs"
    monkeypatch.setattr(focus_app.time, "strftime", lambda _fmt: "20260617_151500")

    project = focus_app.create_runner_output_project(
        parent,
        state_root=state_root,
        experiment_identifier="Study 5 PPS box-breathing white/pink profile",
        profile_id="study5_box_breathing_pps",
        participant_id="P001",
        capture_options={"enable_lsl": True},
    )

    assert project == parent / "study_5_pps_box_breathing_white_pink_profile_20260617_151500"
    assert project.is_dir()
    assert focus_app.current_runner_session_root(state_root) == project
    settings = focus_app.load_runner_settings(state_root)
    assert settings["schema"] == "pps-focus-runner-settings.v1"
    assert settings["session_root"] == str(project)
    assert settings["current_output_project_root"] == str(project)
    assert settings["diary_path"].endswith("_LOG-DIARY_DO_NOT_DELETE.txt")
    assert settings["last_profile_id"] == "study5_box_breathing_pps"
    assert settings["last_participant_id"] == "P001"
    assert settings["last_capture_options"]["enable_lsl"] is True


def test_timestamped_output_environment_uses_parent_and_collision_suffix(tmp_path: Path, monkeypatch):
    from peripersonal_space_toolkit import focus_app

    parent = tmp_path / "operator_outputs"
    parent.mkdir()
    monkeypatch.setattr(focus_app.time, "strftime", lambda _fmt: "20260618_091011")
    first = parent / "my_lab_pilot_20260618_091011"
    first.mkdir()

    root, diary, slug = focus_app.create_timestamped_output_environment(parent, "My Lab Pilot ä/ß")

    assert slug == "my_lab_pilot"
    assert root == parent / "my_lab_pilot_20260618_091011_2"
    assert root.is_dir()
    assert diary.parent == output_runner_logs_dir(root)
    assert diary.name.endswith("_LOG-DIARY_DO_NOT_DELETE.txt")
    assert not (root / diary.name).exists()


def test_initiate_data_collection_environment_groups_snapshot_metadata(tmp_path: Path, monkeypatch):
    from peripersonal_space_toolkit import focus_app
    from peripersonal_space_toolkit.profile_memory import _path_exists

    state_root = tmp_path / "state"
    parent = tmp_path / "operator_outputs"
    parent.mkdir()
    source_project = tmp_path / "source_profile"
    run_setup = source_project / "6_experiment_run_setup" / "experiment_run_setup_manifest.json"
    run_setup.parent.mkdir(parents=True)
    run_csv = run_setup.parent / "experiment_block_order.csv"
    run_csv.write_text("participant_id\nP001\n", encoding="utf-8")
    run_setup.write_text(
        json.dumps(
            {
                "schema": "pps-experiment-run-setup.v1",
                "prepared": True,
                "csv_path": str(run_csv),
                "participant_count": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (source_project / "0_profile").mkdir(parents=True)
    (source_project / "0_profile" / "active_design.json").write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(focus_app, "DEFAULT_DASHBOARD_STATE_ROOT", state_root)
    monkeypatch.setattr(focus_app.time, "strftime", lambda fmt: "20260618_205901" if "%Y%m%d" in fmt else "2026-06-18T20:59:01")
    monkeypatch.setattr(
        focus_app,
        "_materialize_profile_run_setup",
        lambda profile, progress_callback=None: (SimpleNamespace(), SimpleNamespace(), run_setup),
    )
    monkeypatch.setattr(
        focus_app,
        "resolve_profile_entry",
        lambda *_args, **_kwargs: {
            "profile_id": focus_app.STUDY5_PROFILE_ID,
            "display_name": "Study 5",
            "kind": "bundled",
            "dashboard_project_id": "profile_study5_box_breathing_pps",
            "project_dir": str(source_project),
            "participant_count": 1,
            "participant_ids": ["P001"],
        },
    )
    monkeypatch.setattr(
        focus_app,
        "prepare_profile_audio_assets",
        lambda *_args, **_kwargs: {"prepared_count": 0, "reused_count": 1, "results": []},
    )

    result = focus_app.initiate_data_collection_environment(
        parent_folder=parent,
        profile_id=focus_app.STUDY5_PROFILE_ID,
        session_name="Study5",
        participant_id="P001",
        capture_options={"enable_lsl": False},
    )

    environment_root = Path(result["environment_root"])
    metadata_dir = output_metadata_dir(environment_root)
    project_state_dir = output_project_state_dir(environment_root)
    profile_snapshot_dir = output_profile_snapshot_dir(environment_root)
    assert environment_root == parent / "study5_20260618_205901"
    assert metadata_dir.is_dir()
    assert Path(result["diary_path"]).parent == output_runner_logs_dir(environment_root)
    assert (project_state_dir / "output_diary.v1.jsonl").is_file()
    assert (project_state_dir / "dashboard_runner_bridge_manifest.v1.json").is_file()
    copied_run_setup = profile_snapshot_dir / focus_app.STUDY5_PROFILE_ID / "6_experiment_run_setup" / "experiment_run_setup_manifest.json"
    assert _path_exists(copied_run_setup)
    assert not (environment_root / "output_diary.v1.jsonl").exists()
    assert not (environment_root / "dashboard_runner_bridge_manifest.v1.json").exists()
    assert not (environment_root / "study_profile_snapshot").exists()

    bridge = json.loads((project_state_dir / "dashboard_runner_bridge_manifest.v1.json").read_text(encoding="utf-8"))
    assert bridge["environment_metadata_dir"] == str(metadata_dir)
    assert bridge["acquisition_profile_snapshot_dir"] == str(profile_snapshot_dir / focus_app.STUDY5_PROFILE_ID)
    settings = focus_app.load_runner_settings(state_root)
    assert settings["current_output_project_root"] == str(environment_root)
    assert str(settings["diary_path"]).replace("\\\\?\\", "") == result["diary_path"]


def test_prepare_profile_audio_assets_reuses_scanned_generated_packages(tmp_path: Path, monkeypatch):
    from peripersonal_space_toolkit import focus_app

    run_setup_manifest = tmp_path / "6_experiment_run_setup" / "experiment_run_setup_manifest.json"
    run_setup_manifest.parent.mkdir(parents=True)
    run_setup_manifest.write_text("{}", encoding="utf-8")
    existing_manifest = tmp_path / "sessions" / "P001_existing" / "session_manifest.json"
    existing_manifest.parent.mkdir(parents=True)
    existing_manifest.write_text("{}", encoding="utf-8")
    generated_manifest = tmp_path / "sessions" / "P002_generated" / "session_manifest.json"
    generated_manifest.parent.mkdir(parents=True)

    prepared_participants: list[str] = []
    queue_records: list[dict[str, object]] = []
    activity_records: list[tuple[tuple[object, ...], dict[str, object]]] = []
    output_root = tmp_path / "operator_selected_output"

    monkeypatch.setattr(
        focus_app,
        "_materialize_profile_run_setup",
        lambda profile, progress_callback=None: (
            SimpleNamespace(design_path=tmp_path / "design.json"),
            SimpleNamespace(),
            run_setup_manifest,
        ),
    )

    def fake_asset_status(run_setup_path, participant_id, **_kwargs):
        assert run_setup_path == run_setup_manifest
        assert Path(_kwargs["session_root"]) == output_root
        if participant_id == "P001":
            return {
                "participant_id": "P001",
                "generated": True,
                "status": "generated",
                "source": "session_scan",
                "session_manifest_path": str(existing_manifest),
                "message": "Prepared local audio package is available.",
                "data_collected": False,
            }
        return {
            "participant_id": participant_id,
            "generated": False,
            "status": "not_generated",
            "source": "",
            "session_manifest_path": "",
            "message": "No prepared local audio package found.",
            "data_collected": False,
        }

    def fake_prepare_segment_run_package(run_setup_path, participant_id, **_kwargs):
        assert run_setup_path == run_setup_manifest
        assert Path(_kwargs["session_root"]) == output_root
        prepared_participants.append(participant_id)
        return SimpleNamespace(
            manifest_path=generated_manifest,
            session_dir=generated_manifest.parent,
            blocks=[object(), object()],
        )

    monkeypatch.setattr(focus_app, "prepared_session_asset_status", fake_asset_status)
    monkeypatch.setattr(focus_app, "prepare_segment_run_package", fake_prepare_segment_run_package)
    monkeypatch.setattr(focus_app, "record_prepared_session_queue", lambda **kwargs: queue_records.append(kwargs))
    monkeypatch.setattr(focus_app, "update_profile_runner_settings", lambda **_kwargs: {})
    monkeypatch.setattr(
        focus_app,
        "record_experiment_activity",
        lambda *args, **kwargs: activity_records.append((args, kwargs)),
    )

    result = focus_app.prepare_profile_audio_assets(
        "study5_box_breathing_pps",
        ["P001", "P002"],
        session_root=output_root,
    )

    assert prepared_participants == ["P002"]
    assert result["prepared_count"] == 1
    assert result["reused_count"] == 1
    assert [row["status"] for row in result["results"]] == ["already_ready", "generated"]
    assert queue_records[0]["participant_id"] == "P001"
    assert queue_records[0]["status"] == "ready"
    assert queue_records[0]["session_manifest_path"] == existing_manifest
    assert [record["status"] for record in queue_records if record["participant_id"] == "P002"] == ["preparing", "ready"]
    assert activity_records


def test_prepare_profile_focus_session_rejects_unfinished_profile(monkeypatch):
    from peripersonal_space_toolkit import dashboard_app, focus_app

    class FakeController:
        def __init__(self, **_kwargs):
            self.current_run_package = None

        def preload_inventory_payload(self):
            return {
                "profiles": [
                    {
                        "template_id": "canzoneri_2012_dynamic_sounds",
                        "finished_profile": False,
                        "segment_6_launchable": False,
                        "profile_completion_status": "unfinished_preload",
                    }
                ]
            }

    monkeypatch.setattr(dashboard_app, "DashboardController", FakeController)

    with pytest.raises(ValueError, match="not a finished Segment 6 launchable profile"):
        focus_app.prepare_profile_focus_session("canzoneri_2012_dynamic_sounds", "P001")


def test_prepare_last_or_latest_focus_session_skips_non_launchable_pointer(tmp_path: Path, monkeypatch):
    from peripersonal_space_toolkit import focus_app

    empty_manifest = _write_minimal_session_manifest(tmp_path)
    fallback_manifest = tmp_path / "fallback" / "session_manifest.json"
    fallback_manifest.parent.mkdir(parents=True)

    monkeypatch.setattr(
        focus_app,
        "load_last_experiment_pointer",
        lambda: {"session_manifest_path": str(empty_manifest), "participant_id": "P001"},
    )
    monkeypatch.setattr(
        focus_app,
        "prepare_latest_focus_session",
        lambda participant_id=None, session_root=None, progress_callback=None: fallback_manifest,
    )

    assert focus_app.prepare_last_or_latest_focus_session("P001") == fallback_manifest


def test_prepare_last_or_latest_focus_session_skips_pointer_outside_output_root(tmp_path: Path, monkeypatch):
    from peripersonal_space_toolkit import focus_app

    old_root = tmp_path / "old_output"
    old_root.mkdir()
    old_manifest = _write_focus_preview_session_manifest(old_root)
    new_root = tmp_path / "new_output"
    fallback_manifest = new_root / "P001_fallback" / "session_manifest.json"
    fallback_manifest.parent.mkdir(parents=True)
    calls: dict[str, object] = {}

    monkeypatch.setattr(
        focus_app,
        "load_last_experiment_pointer",
        lambda: {"session_manifest_path": str(old_manifest), "participant_id": "P001"},
    )

    def fake_prepare_latest(participant_id=None, session_root=None, progress_callback=None):
        calls["participant_id"] = participant_id
        calls["session_root"] = session_root
        return fallback_manifest

    monkeypatch.setattr(focus_app, "prepare_latest_focus_session", fake_prepare_latest)

    assert focus_app.prepare_last_or_latest_focus_session("P001", session_root=new_root) == fallback_manifest
    assert calls["participant_id"] == "P001"
    assert calls["session_root"] == new_root
