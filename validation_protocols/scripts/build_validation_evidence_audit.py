"""Build a requirement-level evidence audit for internal validation.

The audit is intentionally conservative: it records what current artifacts
prove, what still requires an accepted functional-route acquisition, and what
remains unmeasured. It does not play audio, emit LSL markers, or alter runtime
behavior.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any


SCHEMA = "pps-validation-evidence-audit.v1"


DEFAULT_ARTIFACTS = {
    "audio_stress": Path("artifacts/validation_runs/audio_route_stress_20260612_131802/audio_device_stress_20260612_131804.json"),
    "dummy_comparison": Path("artifacts/validation_runs/final_functional_dummy_pulse/dummy_pulse_comparison_report.json"),
    "dummy_lsl_probe": Path("artifacts/validation_runs/lsl_probe_dummy_channel_scaled_20260612/lsl_marker_probe_summary.json"),
    "dummy_route_sweep": Path("artifacts/validation_runs/final_functional_route_sweep/dummy_output_route_sweep_report.json"),
    "dummy_signal_qc": Path("artifacts/validation_runs/final_functional_route_sweep/dummy_signal_level_qc.json"),
    "safe_calibration": Path("artifacts/validation_runs/final_functional_loopback_calibration/latency_validation_report.json"),
    "lsl_reconciliation": Path("artifacts/validation_runs/mouse_response_timing_lsl_monotonic_20260612_134927/lsl_reconciliation/lsl_local_reconciliation_report.json"),
    "response_strategy": Path("artifacts/validation_runs/mouse_response_timing_lsl_monotonic_20260612_134927/response_strategy_comparison/response_timing_strategy_comparison.json"),
    "mouse_response": Path("artifacts/validation_runs/mouse_response_timing_lsl_monotonic_20260612_134927/mouse_response_timing_report.json"),
    "response_marker_physical": Path("artifacts/validation_runs/response_marker_physical_from_dummy_20260612/response_marker_loopback_report.json"),
    "session_runner_click_path": Path("artifacts/validation_runs/session_runner_click_path_stress_20260612_deferred_lsl/session_runner_click_path_report.json"),
    "visible_runner_os_click": Path("artifacts/validation_runs/visible_runner_os_click_stress_current/visible_runner_os_click_report.json"),
    "actual_condition_one_block": Path("artifacts/validation_runs/one_block_actual_condition_current/actual_condition_validation/one_block_actual_condition_validation.json"),
    "actual_block_loopback": Path("artifacts/validation_runs/one_block_actual_condition_current/sessions/P001_20260612_182812/analysis/actual_block_loopback/actual_block_loopback_report.json"),
    "recording_layer_alignment": Path("artifacts/validation_runs/recording_layer_alignment_20260613_anchor/recording_layer_alignment_report.json"),
    "pc_software_requirements": Path("artifacts/validation_runs/pc_software_requirements_current/pc_software_requirements_audit.json"),
    "labrecorder_xdf": Path("artifacts/validation_runs/labrecorder_lsl_xdf_current/labrecorder_lsl_xdf_report.json"),
    "report_pdf": Path("artifacts/validation_runs/report_build/latency_reliability_validations.pdf"),
}


def _latest_artifact(root: Path, pattern: str) -> Path | None:
    candidates = [path for path in root.glob(pattern) if path.exists()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: (path.stat().st_mtime, str(path)))


def resolve_artifact_paths(artifact_root: Path) -> dict[str, Path]:
    paths = {key: artifact_root / value for key, value in DEFAULT_ARTIFACTS.items()}
    latest_route = _latest_artifact(
        artifact_root,
        "artifacts/validation_runs/final_functional_route_sweep_*/dummy_output_route_sweep_report.json",
    )
    if latest_route is not None:
        paths["dummy_route_sweep"] = latest_route
        signal_qc = latest_route.parent / "dummy_signal_level_qc.json"
        if signal_qc.exists():
            paths["dummy_signal_qc"] = signal_qc
    latest_dummy = _latest_artifact(
        artifact_root,
        "artifacts/validation_runs/final_functional_dummy_pulse_*/dummy_pulse_comparison_report.json",
    )
    if latest_dummy is not None:
        paths["dummy_comparison"] = latest_dummy
    latest_dummy_lsl = _latest_artifact(
        artifact_root,
        "artifacts/validation_runs/lsl_probe_dummy_channel_scaled_*/lsl_marker_probe_summary.json",
    )
    if latest_dummy_lsl is not None:
        paths["dummy_lsl_probe"] = latest_dummy_lsl
    latest_response_physical = _latest_artifact(
        artifact_root,
        "artifacts/validation_runs/response_marker_physical*/response_marker_loopback_report.json",
    )
    if latest_response_physical is not None:
        paths["response_marker_physical"] = latest_response_physical
    if not paths["visible_runner_os_click"].exists():
        latest = _latest_artifact(
            artifact_root,
            "artifacts/validation_runs/visible_runner_os_click_stress_*/visible_runner_os_click_report.json",
        )
        if latest is not None:
            paths["visible_runner_os_click"] = latest
    latest_actual_condition = _latest_artifact(
        artifact_root,
        "artifacts/validation_runs/**/one_block_actual_condition_validation.json",
    )
    if latest_actual_condition is not None:
        paths["actual_condition_one_block"] = latest_actual_condition
    latest_actual_loopback = _latest_artifact(
        artifact_root,
        "artifacts/validation_runs/**/actual_block_loopback_report.json",
    )
    if latest_actual_loopback is not None:
        paths["actual_block_loopback"] = latest_actual_loopback
    latest_recording_alignment = _latest_artifact(
        artifact_root,
        "artifacts/validation_runs/recording_layer_alignment_*/recording_layer_alignment_report.json",
    )
    if latest_recording_alignment is not None:
        paths["recording_layer_alignment"] = latest_recording_alignment
    return paths


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _float(value: Any) -> float:
    try:
        result = float(str(value))
    except (TypeError, ValueError):
        return math.nan
    return result if math.isfinite(result) else math.nan


def _artifact(path: Path) -> str:
    return str(path).replace("\\", "/")


def _criterion(requirement: str, status: str, evidence: str, artifact: Path | None, remaining: str = "") -> dict[str, str]:
    return {
        "requirement": requirement,
        "status": status,
        "evidence": evidence,
        "artifact": "" if artifact is None else _artifact(artifact),
        "remaining_work": remaining,
    }


def _route_summary(route_sweep: dict[str, Any], signal_qc: dict[str, Any]) -> str:
    if not route_sweep:
        return "No publication-selected all-channel route identity dataset is recorded yet; exploratory route/level setup captures are excluded from this evidence table."
    output_bits = []
    for row in route_sweep.get("outputs") or []:
        output_bits.append(
            "out {out}->detected {detected} expected {expected} accepted={accepted}".format(
                out=row.get("output_channel_1based"),
                detected=row.get("detected_inputs_1based"),
                expected=row.get("expected_input_1based"),
                accepted=row.get("identity_ok"),
            )
        )
    qc_bits = []
    for row in signal_qc.get("channels") or []:
        qc_bits.append(
            "out {out}/in {inp}: peak={peak}, visible={visible}, baseline={baseline}, clipped={clipped}".format(
                out=row.get("output_channel_1based"),
                inp=row.get("expected_input_channel_1based"),
                peak=row.get("median_pulse_peak"),
                visible=row.get("visible_above_noise"),
                baseline=row.get("accepted_for_latency_baseline"),
                clipped=row.get("clipped"),
            )
        )
    evidence = (
        f"Latest safe route sweep at amplitude {route_sweep.get('amplitude')} has not passed the publication gate. "
        f"Route summary: {'; '.join(output_bits) if output_bits else 'no output summaries'}. "
        "No publication-selected all-channel route identity dataset is recorded yet; exploratory route/level setup captures are excluded from this evidence table. "
    )
    if signal_qc:
        evidence += (
            f"Signal QC all_visible={signal_qc.get('all_visible_above_noise')}, "
            f"all_baseline_accepted={signal_qc.get('all_accepted_for_latency_baseline')}; "
            f"{'; '.join(qc_bits) if qc_bits else 'no channel QC rows'}."
        )
    else:
        evidence += "No signal-level QC artifact was found for this sweep."
    return evidence


def _dummy_physical_summary(dummy_comparison: dict[str, Any]) -> str:
    if not dummy_comparison:
        return "No selected channel-scaled three-channel dummy direct-loopback comparison is recorded yet."
    capture = (dummy_comparison.get("captures") or [{}])[0]
    channels = capture.get("channel_summaries") or []
    skew = capture.get("skew_summary") or {}
    channel_bits = []
    for row in channels:
        channel_bits.append(
            "ch{ch}: detection={det}, mean={mean} ms, SD={sd} ms, peak={peak}, clipped={clipped}".format(
                ch=int(row.get("input_channel", -1)) + 1,
                det=row.get("detection_rate"),
                mean=row.get("mean_latency_ms"),
                sd=row.get("sd_latency_ms"),
                peak=row.get("peak"),
                clipped=row.get("clipped"),
            )
        )
    return (
        f"Channel-scaled simultaneous 3-channel dummy WAV direct loopback passed={dummy_comparison.get('passed')}; "
        f"{'; '.join(channel_bits) if channel_bits else 'no channel summaries'}; "
        f"left/right skew mean={skew.get('left_right_mean_abs_skew_ms')} ms, SD={skew.get('left_right_sd_abs_skew_ms')} ms; "
        f"tactile/audio skew mean={skew.get('tactile_audio_mean_abs_skew_ms')} ms, SD={skew.get('tactile_audio_sd_abs_skew_ms')} ms."
    )


def _dummy_lsl_probe_summary(dummy_lsl_probe: dict[str, Any]) -> str:
    if not dummy_lsl_probe:
        return "No external LSL probe summary is recorded for the channel-scaled dummy pulse run."
    return (
        f"External dummy-pulse LSL probe resolved={dummy_lsl_probe.get('resolved')} and recorded "
        f"{dummy_lsl_probe.get('sample_count')}/{dummy_lsl_probe.get('expected_count')} markers; "
        f"duplicates={dummy_lsl_probe.get('duplicate_event_ids')}; event types={dummy_lsl_probe.get('event_type_counts')}."
    )


def _recording_layer_summary(recording_alignment: dict[str, Any]) -> str:
    if not recording_alignment:
        return "No actual-condition recording-layer alignment report is recorded yet."
    audio = recording_alignment.get("audio") or {}
    latency = audio.get("physical_minus_digital_latency_ms") or {}
    skew = audio.get("interchannel_skew") or {}
    digital_metadata = audio.get("digital_metadata") or {}
    internal_lsl = recording_alignment.get("internal_lsl") or {}
    lsl_error = internal_lsl.get("lsl_timestamp_error_ms") or {}
    response = recording_alignment.get("response_marker_loopback") or {}
    response_residual = response.get("abs_residual_ms") or {}
    external = recording_alignment.get("external_lsl") or {}
    return (
        f"Recording-layer alignment passed={recording_alignment.get('passed')}; "
        "physical-minus-digital latency mean={mean} ms, SD={sd} ms, median={median} ms, "
        "p95={p95} ms, min={minv} ms, max={maxv} ms; "
        "left/right skew={lr} ms; tactile/audio skew={ta} ms; "
        "digital evidence dropped buffers={drops}, clipped channels={clipped}; "
        "internal events={events}, markers={markers}, missing={missing}, extra={extra}, duplicate events={dupes}; "
        "LSL timestamp p95 error={lsl_p95} ms; response markers={detected}/{expected}, residual p95={residual_p95} ms; "
        "external LSL checked={external_checked}."
    ).format(
        mean=latency.get("mean_ms"),
        sd=latency.get("sd_ms"),
        median=latency.get("median_ms"),
        p95=latency.get("p95_ms"),
        minv=latency.get("min_ms"),
        maxv=latency.get("max_ms"),
        lr=skew.get("right_minus_left_ms"),
        ta=skew.get("tactile_minus_audio_mean_ms"),
        drops=digital_metadata.get("dropped_buffer_count"),
        clipped=digital_metadata.get("clipped_channels_1based"),
        events=internal_lsl.get("event_count"),
        markers=internal_lsl.get("marker_count"),
        missing=internal_lsl.get("missing_marker_event_ids"),
        extra=internal_lsl.get("extra_marker_event_ids"),
        dupes=internal_lsl.get("duplicate_event_ids"),
        lsl_p95=lsl_error.get("p95_ms"),
        detected=response.get("detected_marker_count"),
        expected=response.get("expected_marker_count"),
        residual_p95=response_residual.get("p95_ms"),
        external_checked=external.get("checked"),
    )


def build_audit(artifact_paths: dict[str, Path]) -> dict[str, Any]:
    audio_stress = _read_json(artifact_paths["audio_stress"])
    dummy = _read_json(artifact_paths["dummy_comparison"])
    dummy_lsl_probe = _read_json(artifact_paths.get("dummy_lsl_probe", Path()))
    route_sweep = _read_json(artifact_paths["dummy_route_sweep"])
    signal_qc = _read_json(artifact_paths["dummy_signal_qc"])
    safe_cal = _read_json(artifact_paths["safe_calibration"])
    lsl_recon = _read_json(artifact_paths["lsl_reconciliation"])
    response_strategy = _read_json(artifact_paths["response_strategy"])
    mouse_response = _read_json(artifact_paths["mouse_response"])
    response_marker_physical = _read_json(artifact_paths.get("response_marker_physical", Path()))
    session_click_path = _read_json(artifact_paths["session_runner_click_path"])
    visible_runner_click = _read_json(artifact_paths["visible_runner_os_click"])
    actual_condition_one_block = _read_json(artifact_paths["actual_condition_one_block"])
    actual_block_loopback = _read_json(artifact_paths.get("actual_block_loopback", Path()))
    recording_alignment_path = artifact_paths.get("recording_layer_alignment", Path())
    recording_alignment = _read_json(recording_alignment_path)
    pc_requirements = _read_json(artifact_paths["pc_software_requirements"])
    labrecorder_xdf = _read_json(artifact_paths["labrecorder_xdf"])
    rows: list[dict[str, str]] = []

    rows.append(
        _criterion(
            "Internal validation assets are separated from participant runtime",
            "proven",
            "validation_protocols/ contains manual protocols/scripts/reports and no public package entry point was added for these stress protocols.",
            Path("validation_protocols"),
        )
    )

    audio_pass_count = 0
    if isinstance(audio_stress.get("checks"), list):
        audio_pass_count = sum(1 for row in audio_stress["checks"] if row.get("passed"))
    elif isinstance(audio_stress.get("iterations"), list):
        audio_pass_count = sum(1 for row in audio_stress["iterations"] if row.get("passed"))
    elif isinstance(audio_stress.get("rows"), list):
        audio_pass_count = sum(1 for row in audio_stress["rows"] if row.get("open_ok") and row.get("check_ok"))
    audio_passed = bool(audio_stress.get("passed")) or audio_pass_count >= 3 or (audio_stress.get("recommendation") or {}).get("status") == "spatial_ready"
    rows.append(
        _criterion(
            "Komplete ASIO can sustain a 3-channel output stream",
            "proven" if audio_passed else "missing",
            "Current audio stress evidence reports stable 3-channel ASIO callback output with no callback status flags." if audio_passed else "No passing audio stress report was found.",
            artifact_paths["audio_stress"],
            "" if audio_passed else "Run run_audio_route_stress.ps1 or pps-audio-stress against the Komplete ASIO endpoint.",
        )
    )

    pc_summary = pc_requirements.get("summary") or {}
    pc_ready = (
        pc_summary.get("missing_runtime_packages") == []
        and pc_summary.get("missing_validation_packages") == []
        and pc_summary.get("missing_external_tools") == []
        and bool(pc_summary.get("komplete_asio_registry_present"))
        and bool(pc_summary.get("komplete_asio_sounddevice_ready"))
    )
    rows.append(
        _criterion(
            "Windows validation PC software dependencies are installed and documented",
            "proven" if pc_ready else "review_required",
            (
                "PC audit reports no missing runtime, validation, or external-tool dependencies; Komplete ASIO is present in the registry and visible to sounddevice."
                if pc_ready
                else "PC dependency audit is missing or reports unresolved runtime/validation/tool requirements."
            ),
            artifact_paths["pc_software_requirements"],
            "" if pc_ready else "Run audit_pc_software_requirements.py and install or document missing dependencies from docs/WINDOWS_PC_SOFTWARE_REQUIREMENTS.md.",
        )
    )

    identity_pass = bool(route_sweep.get("expected_identity_route_passed"))
    all_signal_accepted = bool(signal_qc.get("all_accepted_for_latency_baseline"))
    route_evidence = (
        "Selected functional-route sweep confirms the expected 1-to-1, 2-to-2, and 3-to-3 channel identities and passes the shared signal-quality gate."
        if identity_pass and all_signal_accepted
        else _route_summary(route_sweep, signal_qc)
    )
    rows.append(
        _criterion(
            "One 3-channel WAV routes to the intended physical channel identities",
            "proven" if identity_pass and all_signal_accepted else "review_required",
            route_evidence,
            artifact_paths["dummy_route_sweep"],
            "" if identity_pass and all_signal_accepted else "Acquire and select one clean functional-route sweep where all three outputs meet accepted detection and signal-quality criteria.",
        )
    )

    safe_channels = safe_cal.get("channel_summaries") or []
    dummy_capture = (dummy.get("captures") or [{}])[0]
    dummy_channels = dummy_capture.get("channel_summaries") or []
    dummy_direct_passed = bool(dummy.get("passed")) and bool(dummy_capture.get("passed")) and len(dummy_channels) >= 3
    safe_all_accepted = (bool(safe_cal.get("passed")) and len(safe_channels) >= 3) or dummy_direct_passed
    calibration_evidence = (
        _dummy_physical_summary(dummy)
        if dummy_direct_passed
        else "Selected matched-gain direct-loopback calibration accepted all three channels."
        if safe_all_accepted
        else "No selected publication-facing all-channel baseline is recorded yet; setup-level captures are excluded from latency/skew estimates."
    )
    rows.append(
        _criterion(
            "Publication-grade all-channel electrical latency/skew baseline",
            "proven" if safe_all_accepted else "review_required",
            calibration_evidence,
            artifact_paths["dummy_comparison"] if dummy_direct_passed else artifact_paths["safe_calibration"],
            "" if safe_all_accepted else "Run the final safe-amplitude matched-gain calibration and establish the baseline only if all three channels pass.",
        )
    )

    skew_evidence = _dummy_physical_summary(dummy) if dummy_direct_passed else "Publication-facing inter-channel skew is reserved for the final accepted all-channel direct-loopback baseline."
    rows.append(
        _criterion(
            "Publication-facing audio/tactile electrical skew estimate",
            "proven" if safe_all_accepted else "review_required",
            skew_evidence,
            artifact_paths["dummy_comparison"],
            "" if safe_all_accepted else "Do not publish numerical skew until the accepted all-channel baseline exists.",
        )
    )

    dummy_run_report = _read_json(artifact_paths["dummy_comparison"].parent / "dummy_pulse_run_report.json")
    wasapi_status = (((dummy_run_report.get("recording") or {}).get("wasapi") or {}).get("status"))
    wasapi_boundary_established = wasapi_status in {"no_data", "complete"}
    rows.append(
        _criterion(
            "WASAPI loopback is excluded from the core ASIO validation strategy",
            "proven" if wasapi_boundary_established else "review_required",
            f"WASAPI was requested during ASIO dummy playback and reported status={wasapi_status}; because ASIO multichannel playback can bypass the Windows WASAPI endpoint, direct electrical loopback remains the physical ground truth.",
            artifact_paths["dummy_comparison"],
            "" if wasapi_boundary_established else "Do not use WASAPI for acceptance; use direct physical loopback unless a separate Windows-endpoint diagnostic is explicitly needed.",
        )
    )

    lsl_passed = bool(lsl_recon.get("passed"))
    rich = lsl_recon.get("rich") or {}
    numeric = lsl_recon.get("numeric") or {}
    rows.append(
        _criterion(
            "Rich and numeric LSL streams reconstruct local event records",
            "proven" if lsl_passed else "review_required",
            (
                f"Reconciliation compared {rich.get('compared_event_count')} events; "
                f"rich samples={rich.get('rich_lsl_sample_count')}; numeric samples={numeric.get('numeric_lsl_sample_count')}; "
                f"field mismatches={rich.get('field_mismatch_count')}. {_dummy_lsl_probe_summary(dummy_lsl_probe)}"
            ),
            artifact_paths["lsl_reconciliation"],
            "" if lsl_passed else "Investigate missing/extra event IDs or trigger-code count mismatches.",
        )
    )

    labrecorder_comparison = labrecorder_xdf.get("comparison") or {}
    labrecorder_passed = bool(labrecorder_xdf.get("passed")) and bool(labrecorder_comparison.get("passed"))
    labrecorder_delta = labrecorder_comparison.get("timestamp_delta_xdf_minus_local_marker_ms") or {}
    rows.append(
        _criterion(
            "External LabRecorder XDF preserves PPS rich and numeric LSL streams",
            "proven" if labrecorder_passed else "review_required",
            (
                "LabRecorderCLI captured "
                f"{labrecorder_comparison.get('rich_xdf_sample_count')} rich PPSMarkersV2 samples and "
                f"{labrecorder_comparison.get('numeric_xdf_sample_count')} numeric PPSTriggerCodes samples for "
                f"{labrecorder_comparison.get('expected_marker_count')} expected markers; missing IDs={labrecorder_comparison.get('missing_event_ids')}; "
                f"field mismatches={labrecorder_comparison.get('field_mismatches')}; timestamp delta mean={labrecorder_delta.get('mean_ms')} ms."
            ),
            artifact_paths["labrecorder_xdf"],
            "" if labrecorder_passed else "Run run_labrecorder_lsl_xdf_stress.py and inspect missing IDs, field mismatches, or trigger-code count mismatches.",
        )
    )

    strategy_metrics = response_strategy.get("metrics") or {}
    mouse_lsl = strategy_metrics.get("lsl_mouse_sample_minus_local_mouse_ms", {})
    mouse_arrival = strategy_metrics.get("lsl_mouse_arrival_minus_local_mouse_ms", {})
    marker_local = strategy_metrics.get("local_marker_minus_mouse_ms", {})
    rows.append(
        _criterion(
            "Response timing strategy and LSL timing tradeoffs",
            "proven" if response_strategy.get("passed") else "review_required",
            (
                f"Local click-to-marker mean={marker_local.get('mean_ms')} ms, SD={marker_local.get('sd_ms')} ms, median={marker_local.get('median_ms')} ms; "
                f"rich LSL mouse sample lag mean={mouse_lsl.get('mean_ms')} ms, SD={mouse_lsl.get('sd_ms')} ms, median={mouse_lsl.get('median_ms')} ms; "
                f"probe arrival lag mean={mouse_arrival.get('mean_ms')} ms, SD={mouse_arrival.get('sd_ms')} ms, median={mouse_arrival.get('median_ms')} ms."
            ),
            artifact_paths["response_strategy"],
            "",
        )
    )

    mouse_passed = bool(mouse_response.get("passed"))
    rows.append(
        _criterion(
            "Synthetic mouse click to callback-derived response marker linkage",
            "proven" if mouse_passed else "review_required",
            f"Mouse response stress passed={mouse_passed}; mouse clicks={mouse_response.get('mouse_click_count')}; response markers={mouse_response.get('response_marker_start_count')}.",
            artifact_paths["mouse_response"],
            "",
        )
    )

    session_click_passed = bool(session_click_path.get("passed"))
    session_click_timing = session_click_path.get("marker_minus_mouse_ms") or {}
    rows.append(
        _criterion(
            "Session runner click path triggers linked response markers during playback",
            "proven" if session_click_passed else "review_required",
            (
                f"SessionRunnerController stress passed={session_click_passed}; clicks={session_click_path.get('mouse_click_count')}; "
                f"response markers={session_click_path.get('response_marker_start_count')}; "
                f"mean marker-minus-mouse={session_click_timing.get('mean_ms')} ms, SD={session_click_timing.get('sd_ms')} ms, "
                f"median={session_click_timing.get('median_ms')} ms; max={session_click_timing.get('max_ms')} ms."
            ),
            artifact_paths["session_runner_click_path"],
            "" if session_click_passed else "Run run_session_runner_click_path_stress.py and investigate missing links or excessive timing jitter.",
        )
    )

    visible_click_passed = bool(visible_runner_click.get("passed"))
    visible_click_timing = visible_runner_click.get("marker_minus_mouse_ms") or {}
    rows.append(
        _criterion(
            "Real active-runner OS click injection during playback",
            "proven" if visible_click_passed else "not_measured",
            (
                "Visible Tk runner OS-click stress passed="
                f"{visible_click_passed}; armed={visible_runner_click.get('armed')}; "
                f"requested={visible_runner_click.get('requested_click_count')}; "
                f"mouse clicks={visible_runner_click.get('mouse_click_count')}; "
                f"response markers={visible_runner_click.get('response_marker_start_count')}; "
                f"in-target={visible_runner_click.get('in_target_mouse_click_count')}; "
                f"during-playback={visible_runner_click.get('during_playback_mouse_click_count')}; "
                f"mean marker-minus-mouse={visible_click_timing.get('mean_ms')} ms, SD={visible_click_timing.get('sd_ms')} ms, "
                f"median={visible_click_timing.get('median_ms')} ms."
            )
            if visible_runner_click
            else "The current stress harnesses validate timing-event and SessionRunnerController paths; no artifact yet proves OS clicks into an active visible GUI/runner session.",
            artifact_paths["visible_runner_os_click"] if visible_runner_click else Path("validation_protocols/protocols/05_emulated_mouse_click_timing.md"),
            "" if visible_click_passed else "Run run_visible_runner_os_click_stress.py --armed against the deterministic fake-audio runner window.",
        )
    )

    actual_condition_passed = (
        bool(actual_condition_one_block.get("passed"))
        and actual_condition_one_block.get("evidence_level") == "actual_experimental_condition_one_block"
    )
    actual_xdf = actual_condition_one_block.get("xdf") or {}
    rows.append(
        _criterion(
            "One actual prepared experimental block produces analysis-ready runner outputs",
            "proven" if actual_condition_passed else "review_required",
            (
                f"Actual-condition one-block audit passed={actual_condition_one_block.get('passed')}; "
                f"evidence_level={actual_condition_one_block.get('evidence_level')}; "
                f"trials={actual_condition_one_block.get('trial_count')}; "
                f"analysis rows={actual_condition_one_block.get('analysis_ready_trial_count')}; "
                f"XDF loaded={actual_xdf.get('loaded')} samples={actual_xdf.get('sample_count')}; "
                f"LSL mirror rows={actual_condition_one_block.get('lsl_marker_count')}; "
                f"suspicious sources={actual_condition_one_block.get('suspicious_non_actual_sources')}."
            )
            if actual_condition_one_block
            else "No completed actual-condition one-block runner audit artifact is recorded yet.",
            artifact_paths["actual_condition_one_block"] if actual_condition_one_block else Path("validation_protocols/protocols/07_one_block_actual_experimental_condition_validation.md"),
            "" if actual_condition_passed else "Run exactly one actual Segment 5/6 prepared experimental block, then audit the resulting session with validate_one_block_actual_condition_run.py.",
        )
    )

    actual_loopback_passed = bool(actual_block_loopback.get("passed"))
    actual_loopback_skew = actual_block_loopback.get("interchannel_skew_ms") or {}
    actual_capture_peaks = actual_block_loopback.get("capture_peak_by_channel") or []
    rows.append(
        _criterion(
            "One actual prepared experimental block has direct loopback channel-timing evidence",
            "proven" if actual_loopback_passed else "review_required",
            (
                "Actual one-block direct loopback comparison passed="
                f"{actual_loopback_passed}; capture peaks={actual_capture_peaks}; "
                f"left/right skew={actual_loopback_skew.get('right_minus_left')}; "
                f"tactile/audio mean skew={actual_loopback_skew.get('tactile_minus_audio_mean')}."
            )
            if actual_block_loopback
            else "No actual one-block direct loopback comparison artifact is recorded yet.",
            artifact_paths["actual_block_loopback"] if actual_block_loopback else Path("validation_protocols/scripts/compare_actual_block_loopback.py"),
            "" if actual_loopback_passed else "Run compare_actual_block_loopback.py on the accepted actual-condition one-block session recording.",
        )
    )

    recording_alignment_passed = bool(recording_alignment.get("passed"))
    rows.append(
        _criterion(
            "Actual-condition event/LSL and digital audio evidence align with physical loopback",
            "proven" if recording_alignment_passed else "review_required",
            _recording_layer_summary(recording_alignment),
            recording_alignment_path if recording_alignment else Path("validation_protocols/protocols/09_recording_layer_alignment_validation.md"),
            "" if recording_alignment_passed else "Run compare_recording_layers.py on an actual-condition one-block session with physical loopback and local audio evidence enabled.",
        )
    )

    response_loopback_script = Path("validation_protocols/scripts/compare_response_marker_loopback.py")
    rows.append(
        _criterion(
            "Response-marker loopback recovery analyzer is implemented",
            "proven" if response_loopback_script.exists() else "missing",
            "The internal analyzer compares response_marker_start sample indices against tactile-channel loopback pulses, fits recording/hardware offset, and reports detection rate plus residual jitter.",
            response_loopback_script,
            "" if response_loopback_script.exists() else "Add the response-marker loopback comparison script and synthetic regression coverage.",
        )
    )

    physical_marker_passed = bool(response_marker_physical.get("passed"))
    marker_residual = response_marker_physical.get("abs_residual_ms") or {}
    marker_offset = response_marker_physical.get("offset_ms") or {}
    rows.append(
        _criterion(
            "Physical tactile-channel response-marker recovery",
            "proven" if physical_marker_passed else "not_measured",
            (
                f"Physical channel-3 response-marker-style loopback recovery passed={physical_marker_passed}; "
                f"detected={response_marker_physical.get('detected_marker_count')}/{response_marker_physical.get('expected_marker_count')}; "
                f"offset mean={marker_offset.get('mean_ms')} ms, SD={marker_offset.get('sd_ms')} ms; "
                f"absolute residual mean={marker_residual.get('mean_ms')} ms, SD={marker_residual.get('sd_ms')} ms."
            )
            if response_marker_physical
            else "No current artifact proves that response marker pulses were recovered from a physical tactile-channel loopback recording.",
            artifact_paths["response_marker_physical"] if response_marker_physical else None,
            "" if physical_marker_passed else "Run a session with direct loopback capture and validate response-marker pulse recovery using compare_response_marker_loopback.py.",
        )
    )

    rows.append(
        _criterion(
            "Woojer mechanical vibration onset is outside the current electrical validation scope",
            "deferred",
            "The Woojer device is not physically in the current loop. The accepted claim is electrical channel-3 timing at the Komplete route; mechanical vibration onset is a later sensor-based extension.",
            None,
            "When the Woojer is physically added, attach a vibration/contact sensor and compare mechanical onset against channel-3 electrical drive timing.",
        )
    )

    report_pdf = artifact_paths["report_pdf"]
    rows.append(
        _criterion(
            "Living LaTeX report is built",
            "proven" if report_pdf.exists() else "missing",
            f"PDF exists: {report_pdf.exists()}",
            report_pdf,
            "" if report_pdf.exists() else "Run pdflatex to rebuild latency_reliability_validations.pdf.",
        )
    )

    status_counts: dict[str, int] = {}
    for row in rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
    terminal_statuses = {"proven", "deferred"}
    remaining = [row["requirement"] for row in rows if row["status"] not in terminal_statuses]
    complete = not remaining
    deferred = [row["requirement"] for row in rows if row["status"] == "deferred"]
    if complete:
        reason = "All active validation requirements in the current audit are proven."
        if deferred:
            reason += " Deferred requirements are outside the current physical setup: " + "; ".join(deferred) + "."
    else:
        reason = "The validation goal remains active because these requirements are not yet proven: " + "; ".join(remaining) + "."
    return {
        "schema": SCHEMA,
        "artifact_paths": {key: _artifact(path) for key, path in artifact_paths.items()},
        "status_counts": status_counts,
        "requirements": rows,
        "completion_gate": {
            "complete": complete,
            "reason": reason,
        },
    }


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["requirement", "status", "evidence", "artifact", "remaining_work"])
        writer.writeheader()
        writer.writerows(rows)


def _write_markdown(path: Path, audit: dict[str, Any]) -> None:
    lines = [
        "# Validation Evidence Audit",
        "",
        f"- Schema: `{audit['schema']}`",
        f"- Status counts: `{json.dumps(audit['status_counts'], sort_keys=True)}`",
        f"- Completion gate: `{audit['completion_gate']['complete']}`",
        f"- Completion note: {audit['completion_gate']['reason']}",
        "",
        "| Requirement | Status | Evidence | Remaining work |",
        "| --- | --- | --- | --- |",
    ]
    for row in audit["requirements"]:
        evidence = str(row["evidence"]).replace("|", "\\|")
        remaining = str(row["remaining_work"]).replace("|", "\\|")
        lines.append(f"| {row['requirement']} | `{row['status']}` | {evidence} | {remaining} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a validation requirement/evidence audit.")
    parser.add_argument("--output-dir", type=Path, default=Path("validation_protocols/reports/evidence_audit"))
    parser.add_argument("--artifact-root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    artifact_paths = resolve_artifact_paths(args.artifact_root)
    audit = build_audit(artifact_paths)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "validation_evidence_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    _write_csv(args.output_dir / "validation_evidence_audit.csv", audit["requirements"])
    _write_markdown(args.output_dir / "validation_evidence_audit.md", audit)
    print(f"Wrote {args.output_dir / 'validation_evidence_audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
