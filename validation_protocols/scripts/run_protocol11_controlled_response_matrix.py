"""Protocol 11 controlled emulated-response matrix.

This harness builds a tiny Segment 5/6 package, runs it through the real
SessionRunnerController, injects deterministic emulated clicks keyed to the
controller's scheduled tactile/trial events, then audits the completed session
with the Protocol 11 artifact validator.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCRIPT_DIR = Path(__file__).resolve().parent
for candidate in (SRC_ROOT, SCRIPT_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from peripersonal_space_toolkit.session_runner import (  # noqa: E402
    RESPONSE_MARKER_GAIN,
    SessionCaptureOptions,
    SessionRunnerController,
    prepare_segment_run_package,
)
from run_one_block_trial_runner_realtime_stress import (  # noqa: E402
    RealtimeFakeAudioEngine,
    _add_pulse,
    _read_csv,
    _read_events,
    _sha256,
    _summary,
    _write_csv,
)
from validate_protocol11_emulated_runner_artifacts import validate_artifacts  # noqa: E402


SCHEMA = "pps-protocol11-controlled-response-matrix.v1"
PLAN_SCHEMA = "pps-protocol11-response-plan.v1"
DEFAULT_LOOMING_ONSET_S = 0.040


def _default_output_dir() -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return Path("artifacts") / "validation_runs" / f"protocol11_controlled_response_matrix_{stamp}"


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    return str(value).strip().lower() not in {"0", "false", "no", "none", "nan"}


def _trial_specs() -> list[dict[str, Any]]:
    return [
        {
            "scenario_label": "early_99ms_reject",
            "family": "audio_tactile",
            "duration_s": 1.550,
            "soa_ms": 0,
            "row_label": "Inhale",
            "action": "early",
            "expected_hit": False,
            "clicks": [{"delay_ms": 99.0, "in_target": True}],
        },
        {
            "scenario_label": "boundary_100ms_accept",
            "family": "audio_tactile",
            "duration_s": 1.550,
            "soa_ms": 20,
            "row_label": "Exhale",
            "action": "boundary_accept",
            "expected_hit": True,
            "planned_rt_ms": 100.0,
            "clicks": [{"delay_ms": 100.0, "in_target": True}],
        },
        {
            "scenario_label": "double_click_one_binding",
            "family": "audio_tactile",
            "duration_s": 1.550,
            "soa_ms": 40,
            "row_label": "Inhale",
            "action": "hit",
            "expected_hit": True,
            "planned_rt_ms": 180.0,
            "clicks": [
                {"delay_ms": 180.0, "in_target": True},
                {"delay_ms": 220.0, "in_target": True, "extra_click": True},
            ],
        },
        {
            "scenario_label": "out_of_target_excluded",
            "family": "audio_tactile",
            "duration_s": 1.550,
            "soa_ms": 60,
            "row_label": "Exhale",
            "action": "out_of_target",
            "expected_hit": False,
            "clicks": [{"delay_ms": 180.0, "in_target": False}],
        },
        {
            "scenario_label": "catch_no_tactile_channel",
            "family": "catch",
            "duration_s": 1.550,
            "soa_ms": 0,
            "row_label": "Inhale",
            "action": "no_tactile_expected",
            "expected_hit": None,
            "clicks": [],
        },
        {
            "scenario_label": "baseline_tactile_hit",
            "family": "baseline",
            "duration_s": 1.550,
            "soa_ms": 0,
            "row_label": "Exhale",
            "action": "hit",
            "expected_hit": True,
            "planned_rt_ms": 180.0,
            "clicks": [{"delay_ms": 180.0, "in_target": True}],
        },
        {
            "scenario_label": "miss_no_click",
            "family": "audio_tactile",
            "duration_s": 1.550,
            "soa_ms": 80,
            "row_label": "Inhale",
            "action": "miss",
            "expected_hit": False,
            "clicks": [],
        },
        {
            "scenario_label": "click_after_next_trial_start_accepts_previous",
            "family": "audio_tactile",
            "duration_s": 0.420,
            "soa_ms": 100,
            "row_label": "Exhale",
            "action": "hit",
            "expected_hit": True,
            "clicks": [],
            "click_at_next_trial_start": True,
        },
        {
            "scenario_label": "next_trial_nominal_hit",
            "family": "audio_tactile",
            "duration_s": 0.420,
            "soa_ms": 120,
            "row_label": "Inhale",
            "action": "hit",
            "expected_hit": True,
            "planned_rt_ms": 180.0,
            "clicks": [{"delay_ms": 180.0, "in_target": True}],
        },
        {
            "scenario_label": "boundary_1300ms_accept",
            "family": "audio_tactile",
            "duration_s": 1.550,
            "soa_ms": 0,
            "row_label": "Exhale",
            "action": "boundary_accept",
            "expected_hit": True,
            "planned_rt_ms": 1300.0,
            "clicks": [{"delay_ms": 1300.0, "in_target": True}],
        },
        {
            "scenario_label": "late_1301ms_reject",
            "family": "audio_tactile",
            "duration_s": 1.550,
            "soa_ms": 0,
            "row_label": "Inhale",
            "action": "late",
            "expected_hit": False,
            "clicks": [{"delay_ms": 1301.0, "in_target": True}],
        },
    ]


def _build_segment_fixture(
    output_dir: Path,
    *,
    participant_id: str,
    sample_rate: int,
) -> tuple[Path, list[dict[str, Any]]]:
    project_root = output_dir / "segment_fixture"
    block_root = project_root / "5_block_csv_preview"
    run_root = project_root / "6_experiment_run_setup"
    stim_root = output_dir / "stimuli"
    instruction_root = output_dir / "instructions"
    block_root.mkdir(parents=True, exist_ok=True)
    run_root.mkdir(parents=True, exist_ok=True)
    stim_root.mkdir(parents=True, exist_ok=True)
    instruction_root.mkdir(parents=True, exist_ok=True)

    block_rows: list[dict[str, Any]] = []
    specs = _trial_specs()
    for index, spec in enumerate(specs, start=1):
        family = str(spec["family"])
        duration_s = float(spec["duration_s"])
        soa_ms = int(spec.get("soa_ms") or 0)
        looming_onset_s = DEFAULT_LOOMING_ONSET_S
        tactile_onset_s = DEFAULT_LOOMING_ONSET_S + (soa_ms / 1000.0)
        if family == "baseline":
            tactile_onset_s = DEFAULT_LOOMING_ONSET_S
        frames = int(round(duration_s * sample_rate))
        data = np.zeros((frames, 3), dtype=np.float32)
        if family in {"audio_tactile", "catch"}:
            _add_pulse(data, 0, looming_onset_s, sample_rate=sample_rate, amplitude=0.018)
            _add_pulse(data, 1, looming_onset_s + 0.002, sample_rate=sample_rate, amplitude=0.016)
        if family in {"audio_tactile", "baseline"}:
            _add_pulse(data, 2, tactile_onset_s, sample_rate=sample_rate, amplitude=0.014)
        wav_path = stim_root / f"trial_{index:02d}_{spec['scenario_label']}.wav"
        sf.write(wav_path, data, sample_rate)
        block_rows.append(
            {
                "block_trial_index": index,
                "trial_pool_index": index,
                "family": family,
                "row_label": spec["row_label"],
                "noise_type": "protocol11_rect_pulse",
                "soa_ms": soa_ms,
                "sequence_labels": f"Protocol 11 {spec['scenario_label']} | SOA {soa_ms} ms",
                "sequence_variant_key": f"protocol11_{spec['scenario_label']}",
                "source_file_name": wav_path.name,
                "trial_file_path": str(wav_path),
                "source_sha256": _sha256(wav_path),
                "duration_ms": int(round(duration_s * 1000.0)),
                "duration_s": f"{duration_s:.9f}",
                "looming_segment_onset_s": f"{looming_onset_s:.9f}" if family in {"audio_tactile", "catch"} else "",
                "tactile_onset_s": f"{tactile_onset_s:.9f}" if family in {"audio_tactile", "baseline"} else "",
                "channels": 3,
                "tactile_channel": 3 if family in {"audio_tactile", "baseline"} else "",
            }
        )

    block_csv = block_root / "block_01_final.csv"
    block_fieldnames = [
        "block_trial_index",
        "trial_pool_index",
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
    ]
    _write_csv(block_csv, block_rows, block_fieldnames)

    block_manifest = block_root / "block_csv_preview_manifest.json"
    block_manifest.write_text(
        json.dumps(
            {
                "schema": "pps-block-csv-preview.v1",
                "accepted": True,
                "blocks": [
                    {
                        "block_index": 1,
                        "csv_path": str(block_csv),
                        "csv_file_name": block_csv.name,
                        "trial_count": len(block_rows),
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    order_csv = run_root / "experiment_block_order.csv"
    _write_csv(
        order_csv,
        [
            {
                "participant_id": participant_id,
                "participant_index": 1,
                "experiment_structure": "single",
                "phase": "single",
                "phase_label": "Single",
                "phase_index": 1,
                "participant_block_position": 1,
                "source_block_index": 1,
                "block_label": "Protocol 11 Controlled Matrix",
                "block_csv_file": block_csv.name,
                "block_csv_path": str(block_csv),
                "trial_count": len(block_rows),
                "duration_ms": int(round(sum(float(row["duration_s"]) for row in block_rows) * 1000.0)),
                "sequence_seed": 20260615,
            }
        ],
        [
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

    instruction_path = instruction_root / "before_experiment.wav"
    sf.write(instruction_path, np.zeros((max(1, sample_rate // 100), 1), dtype=np.float32), sample_rate)
    run_manifest = run_root / "experiment_run_setup_manifest.json"
    run_manifest.write_text(
        json.dumps(
            {
                "schema": "pps-experiment-run-setup.v1",
                "status": "prepared",
                "prepared": True,
                "csv_path": str(order_csv),
                "experiment_structure": "single",
                "participant_count": 1,
                "parts_per_participant": 1,
                "blocks_per_part": 1,
                "total_block_runs": 1,
                "seed": 20260615,
                "source_segment5_manifest": str(block_manifest),
                "source_segment5_manifest_sha256": _sha256(block_manifest),
                "instruction_profile": {
                    "schema": "pps-run-instructions.v1",
                    "slots": [
                        {
                            "slot": "before_experiment",
                            "label": "Protocol 11 click-to-continue instruction",
                            "enabled": True,
                            "required": True,
                            "path": str(instruction_path),
                            "continue_mode": "click",
                            "button_label": "Start matrix",
                        }
                    ],
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return run_manifest, specs


class FastSampleExactAudioEngine(RealtimeFakeAudioEngine):
    """Sample-schedule engine that emits callbacks fast and waits for injection."""

    def __init__(
        self,
        *,
        sample_rate: int,
        blocksize: int,
        response_marker_delay_ms: float,
        injection_timeout_s: float = 10.0,
    ):
        super().__init__(
            sample_rate=sample_rate,
            blocksize=blocksize,
            response_marker_delay_ms=response_marker_delay_ms,
        )
        self.schedule_emitted = threading.Event()
        self.injection_complete = threading.Event()
        self.injection_timeout_s = float(injection_timeout_s)
        self.instruction_paths: list[str] = []

    def play_instruction(self, path: str, done_callback=None) -> bool:
        self.instruction_paths.append(path)
        if done_callback is not None:
            done_callback(True)
        return True

    def play_block(self, path: str, progress_callback=None, audio_event_callback=None, block_event_schedule=None) -> bool:
        self._last_block_path = Path(path)
        info = sf.info(path)
        frames_total = int(info.frames)
        self.sample_rate = int(info.samplerate)
        self._audio_event_callback = audio_event_callback
        duration_s = frames_total / float(self.sample_rate) if self.sample_rate else 0.0
        self._play_start_perf = time.perf_counter() - duration_s - 0.050
        if block_event_schedule is not None:
            block_event_schedule.reset()
        self.playback_started.set()

        if audio_event_callback is not None and block_event_schedule is not None:
            for event in block_event_schedule.consume_buffer(0, frames_total + 1):
                event_perf = self._play_start_perf + (int(event.sample_index) / float(self.sample_rate))
                payload = dict(event.payload)
                payload.update(
                    {
                        "event_type": event.event_type,
                        "sample_index": event.sample_index,
                        "buffer_start_sample": event.sample_index,
                        "sample_offset_in_buffer": 0,
                        "sample_rate": self.sample_rate,
                        "trigger_key": event.trigger_key,
                        "callback_perf_counter": event_perf,
                        "stream_current_time": event_perf,
                        "stream_output_buffer_dac_time": event_perf,
                    }
                )
                audio_event_callback(payload)
        if progress_callback is not None:
            progress_callback(duration_s)
        self.schedule_emitted.set()
        if not self.injection_complete.wait(timeout=self.injection_timeout_s):
            self.finish_requested.set()
            return False
        return not self.finish_requested.is_set()

    def stop_recording(self, output_path: str | None = None, interrupted: bool = False) -> None:
        self._recording_active = False
        target = Path(output_path) if output_path else self._recording_output_path
        if target is None:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        if self._last_block_path and self._last_block_path.exists():
            shutil.copyfile(self._last_block_path, target)
        else:
            sf.write(target, np.zeros((1, 3), dtype=np.float32), self.sample_rate)


def _payload(event: Any) -> dict[str, Any]:
    return dict(getattr(event, "payload", {}) or {})


def _event_uid(event: Any) -> str:
    payload = _payload(event)
    return str(payload.get("trial_uid") or payload.get("Trial_UID") or "").strip()


def _event_sample_rate(event: Any, default: int) -> int:
    payload = _payload(event)
    try:
        return int(float(str(payload.get("sample_rate") or payload.get("Sample_Rate_Hz") or default)))
    except (TypeError, ValueError):
        return int(default)


def _block_key(event: Any) -> str:
    payload = _payload(event)
    return str(payload.get("block_number") or payload.get("block_index") or payload.get("Block_Number") or "1")


def _click_context(event: Any) -> dict[str, Any]:
    payload = _payload(event)
    return {
        "block_number": payload.get("block_number", payload.get("Block_Number", "")),
        "block_label": payload.get("block_label", payload.get("Block_Label", "")),
        "part_number": payload.get("part_number", payload.get("Part_Number", "")),
        "phase": payload.get("phase", payload.get("Phase", "")),
        "phase_label": payload.get("phase_label", payload.get("Phase_Label", "")),
        "is_topup": _truthy(payload.get("is_topup", payload.get("Is_Topup", False))),
    }


def _log_scripted_click(
    controller: SessionRunnerController,
    *,
    context_event: Any,
    anchor_event: Any,
    unix_time: float,
    monotonic_time: float,
    sample_rate: int,
    marker_delay_ms: float,
    in_target: bool,
    x: int,
    y: int,
    label: str,
) -> dict[str, Any]:
    click = controller.events.log(
        "mouse_click",
        unix_time=unix_time,
        monotonic_time=monotonic_time,
        x=x,
        y=y,
        in_target=bool(in_target),
        during_playback=True,
        response_plan_label=label,
        **_click_context(context_event),
        push_lsl=False,
    )
    marker_delay_s = marker_delay_ms / 1000.0
    marker_unix = unix_time + marker_delay_s
    marker_mono = monotonic_time + marker_delay_s
    sample_index = max(0, int(round((marker_mono - float(anchor_event.monotonic_time)) * sample_rate)))
    marker = controller.events.log(
        "response_marker_start",
        unix_time=marker_unix,
        monotonic_time=marker_mono,
        mouse_event_id=click.event_id,
        mouse_event_unix_time=click.unix_time,
        mouse_event_monotonic_time=click.monotonic_time,
        sample_index=sample_index,
        sample_rate=sample_rate,
        marker_channel=2,
        marker_gain=RESPONSE_MARKER_GAIN,
        timestamp_quality="dac_time_sample_exact",
        lsl_timestamp=marker_mono,
        response_plan_label=label,
        **_click_context(context_event),
    )
    controller.events.push_deferred_event_marker(click)
    return {
        "label": label,
        "mouse_event_id": click.event_id,
        "response_marker_event_id": marker.event_id,
        "click_unix_time": f"{click.unix_time:.9f}",
        "click_monotonic_time": f"{click.monotonic_time:.9f}",
        "marker_unix_time": f"{marker.unix_time:.9f}",
        "marker_monotonic_time": f"{marker.monotonic_time:.9f}",
        "in_target": bool(in_target),
        "sample_index": sample_index,
    }


def _inject_response_plan(
    controller: SessionRunnerController,
    *,
    block_manifest_rows: list[dict[str, str]],
    specs: list[dict[str, Any]],
    sample_rate: int,
    marker_delay_ms: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    events = controller.logger.events
    tactile_by_uid = {uid: event for event in events if event.event_type == "tactile_onset" for uid in [_event_uid(event)] if uid}
    trial_start_by_uid = {uid: event for event in events if event.event_type == "trial_start" for uid in [_event_uid(event)] if uid}
    anchors = {str(_block_key(event)): event for event in events if event.event_type == "audio_sample_zero"}
    if not anchors:
        raise RuntimeError("audio_sample_zero was not emitted before response injection.")

    plan_trials: list[dict[str, Any]] = []
    click_records: list[dict[str, Any]] = []
    uid_by_index = [str(row.get("Trial_UID") or "").strip() for row in block_manifest_rows]
    click_index = 0
    for index, (spec, row) in enumerate(zip(specs, block_manifest_rows, strict=True), start=1):
        uid = str(row.get("Trial_UID") or "").strip()
        family = str(row.get("Family") or spec.get("family") or "")
        if family.lower() == "catch":
            continue
        expected_hit = spec.get("expected_hit")
        plan_row: dict[str, Any] = {
            "trial_uid": uid,
            "scenario_label": spec["scenario_label"],
            "action": spec["action"],
            "expected_hit": bool(expected_hit),
            "trial_family": family,
        }
        if expected_hit and "planned_rt_ms" in spec:
            plan_row["planned_rt_ms"] = float(spec["planned_rt_ms"])
            plan_row["rt_tolerance_ms"] = 0.1
        plan_trials.append(plan_row)

        tactile = tactile_by_uid.get(uid)
        if tactile is None:
            raise RuntimeError(f"Missing tactile_onset for planned trial {uid}.")
        anchor = anchors.get(_block_key(tactile)) or next(iter(anchors.values()))
        rate = _event_sample_rate(tactile, sample_rate)
        for click_spec in spec.get("clicks", []):
            delay_ms = float(click_spec["delay_ms"])
            click_index += 1
            record = _log_scripted_click(
                controller,
                context_event=tactile,
                anchor_event=anchor,
                unix_time=float(tactile.unix_time) + (delay_ms / 1000.0),
                monotonic_time=float(tactile.monotonic_time) + (delay_ms / 1000.0),
                sample_rate=rate,
                marker_delay_ms=marker_delay_ms,
                in_target=bool(click_spec.get("in_target", True)),
                x=320 + click_index,
                y=240,
                label=f"{spec['scenario_label']}:{delay_ms:.1f}ms",
            )
            record.update(
                {
                    "trial_uid": uid,
                    "delay_ms": delay_ms,
                    "click_kind": "extra_double_click" if click_spec.get("extra_click") else "planned_click",
                }
            )
            click_records.append(record)
        if spec.get("click_at_next_trial_start"):
            if index >= len(uid_by_index):
                raise RuntimeError(f"{spec['scenario_label']} requested a next-trial click but has no next trial.")
            next_uid = uid_by_index[index]
            next_start = trial_start_by_uid.get(next_uid)
            if next_start is None:
                raise RuntimeError(f"Missing next trial_start for {next_uid}.")
            click_index += 1
            record = _log_scripted_click(
                controller,
                context_event=next_start,
                anchor_event=anchors.get(_block_key(next_start)) or anchor,
                unix_time=float(next_start.unix_time),
                monotonic_time=float(next_start.monotonic_time),
                sample_rate=_event_sample_rate(next_start, sample_rate),
                marker_delay_ms=marker_delay_ms,
                in_target=True,
                x=320 + click_index,
                y=240,
                label=f"{spec['scenario_label']}:at_next_trial_start",
            )
            record.update(
                {
                    "trial_uid": uid,
                    "target_next_trial_uid": next_uid,
                    "delay_ms": "",
                    "click_kind": "at_next_trial_start",
                }
            )
            click_records.append(record)
    return plan_trials, click_records


def _event_type_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        event_type = str(event.get("event_type") or "")
        counts[event_type] = counts.get(event_type, 0) + 1
    return counts


def _analysis_by_uid(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {str(row.get("trial_uid") or row.get("Trial_UID") or "").strip(): row for row in rows}


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Protocol 11 Controlled Response Matrix",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Session dir: `{report.get('session_dir')}`",
        f"- Response plan: `{report.get('response_plan_json')}`",
        f"- Artifact audit: `{report.get('artifact_audit_json')}`",
        f"- Event counts: `{json.dumps(report.get('event_type_counts'), sort_keys=True)}`",
        "",
        "## Checks",
    ]
    for key, value in report.get("checks", {}).items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(
        [
            "",
            "This scenario validates deterministic software pairing and artifact contracts. It does not measure OS-click latency, physical audio output, Woojer mechanical onset, participant behavior, or scientific PPS interpretability.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_matrix(
    *,
    output_dir: Path,
    participant_id: str,
    sample_rate: int,
    blocksize: int,
    enable_lsl: bool,
    response_marker_delay_ms: float,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    run_manifest, specs = _build_segment_fixture(
        output_dir,
        participant_id=participant_id,
        sample_rate=sample_rate,
    )
    package = prepare_segment_run_package(
        run_manifest,
        participant_id,
        session_root=output_dir / "sessions",
        created_at=datetime.now(),
        use_block_cache=False,
    )
    engine = FastSampleExactAudioEngine(
        sample_rate=sample_rate,
        blocksize=blocksize,
        response_marker_delay_ms=response_marker_delay_ms,
    )
    holder: dict[str, SessionRunnerController] = {}

    def _continue_with_target_double_click(_context: dict[str, Any]) -> bool:
        controller = holder["controller"]
        controller.log_click(x=12, y=14)
        controller.log_click(x=13, y=14)
        return False

    controller = SessionRunnerController(
        package,
        audio_engine=engine,
        capture_options=SessionCaptureOptions(enable_lsl=enable_lsl),
        instruction_continue_callback=_continue_with_target_double_click,
    )
    holder["controller"] = controller
    result_holder: dict[str, Any] = {}
    exception_holder: dict[str, BaseException] = {}

    def _run_controller() -> None:
        try:
            result_holder["result"] = controller.run()
        except BaseException as exc:  # pragma: no cover - re-raised in caller
            exception_holder["exception"] = exc
            engine.injection_complete.set()

    thread = threading.Thread(target=_run_controller, name="pps-protocol11-controlled-matrix", daemon=True)
    thread.start()
    if not engine.schedule_emitted.wait(timeout=10.0):
        engine.stop()
        thread.join(timeout=2.0)
        if "exception" in exception_holder:
            raise exception_holder["exception"]
        raise RuntimeError("Controller did not emit the block schedule in time.")
    controller.events.flush_callback_events()
    block_manifest_rows = _read_csv(package.blocks[0].manifest_path)
    plan_trials, click_records = _inject_response_plan(
        controller,
        block_manifest_rows=block_manifest_rows,
        specs=specs,
        sample_rate=sample_rate,
        marker_delay_ms=response_marker_delay_ms,
    )
    _write_csv(
        output_dir / "scripted_response_events.csv",
        click_records,
        [
            "trial_uid",
            "target_next_trial_uid",
            "label",
            "click_kind",
            "delay_ms",
            "mouse_event_id",
            "response_marker_event_id",
            "click_unix_time",
            "click_monotonic_time",
            "marker_unix_time",
            "marker_monotonic_time",
            "in_target",
            "sample_index",
        ],
    )
    engine.injection_complete.set()
    thread.join(timeout=30.0)
    if thread.is_alive():
        engine.stop()
        thread.join(timeout=2.0)
        raise RuntimeError("Controller did not finish the controlled response matrix.")
    if "exception" in exception_holder:
        raise exception_holder["exception"]

    result = result_holder["result"]
    controller.events.flush_callback_events()
    plan = {
        "schema": PLAN_SCHEMA,
        "expected_capture_options": result.capture_options,
        "instruction_slots": [{"slot": "before_experiment", "required": True}],
        "instruction_clicks": [
            {
                "slot": "before_experiment",
                "source": "target_click",
                "double_click": True,
                "expected_mouse_click_rows": 0,
            }
        ],
        "trials": plan_trials,
    }
    plan_path = output_dir / "protocol11_response_plan.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    audit = validate_artifacts(
        Path(result.session_dir),
        response_plan_path=plan_path,
        output_dir=output_dir / "protocol11_artifact_audit",
    )
    events = _read_events(result.events_csv)
    event_counts = _event_type_counts(events)
    analysis_ready_path = result.analysis_outputs["analysis_ready_trials"]
    analysis_rows = _read_csv(analysis_ready_path)
    by_uid = _analysis_by_uid(analysis_rows)
    timing_qc_path = result.analysis_outputs["timing_qc"]
    timing_rows = _read_csv(timing_qc_path)
    marker_delta_values = [
        float(row["marker_minus_mouse_ms"])
        for row in timing_rows
        if str(row.get("marker_minus_mouse_ms") or "").strip()
    ]

    checks = {
        "controller_completed": bool(result.completed and not result.interrupted),
        "artifact_audit_passed": bool(audit.get("passed")),
        "instruction_clicks_created_no_mouse_responses": event_counts.get("instruction_continue", 0) == 1
        and all(str(row.get("event_type")) != "mouse_click" or _truthy(row.get("during_playback", True)) for row in events),
        "early_99ms_rejected": not _truthy(by_uid[plan_trials[0]["trial_uid"]].get("hit")),
        "boundary_100ms_accepted": _truthy(by_uid[plan_trials[1]["trial_uid"]].get("hit")),
        "double_click_bound_once": _truthy(by_uid[plan_trials[2]["trial_uid"]].get("hit"))
        and sum(1 for row in analysis_rows if str(row.get("trial_uid")) == plan_trials[2]["trial_uid"] and str(row.get("click_event_id") or "").strip()) == 1,
        "out_of_target_rejected": not _truthy(by_uid[plan_trials[3]["trial_uid"]].get("hit")),
        "baseline_tactile_hit": _truthy(by_uid[plan_trials[4]["trial_uid"]].get("hit")),
        "miss_no_click_rejected": not _truthy(by_uid[plan_trials[5]["trial_uid"]].get("hit")),
        "next_trial_start_click_accepted_previous": _truthy(by_uid[plan_trials[6]["trial_uid"]].get("hit")),
        "max_1300ms_accepted": _truthy(by_uid[plan_trials[8]["trial_uid"]].get("hit")),
        "late_1301ms_rejected": not _truthy(by_uid[plan_trials[9]["trial_uid"]].get("hit")),
        "all_in_playback_clicks_have_markers": event_counts.get("mouse_click", 0) == event_counts.get("response_marker_start", 0),
        "timing_qc_marker_delay_stable": bool(marker_delta_values)
        and max(abs(value - response_marker_delay_ms) for value in marker_delta_values) <= 0.1,
    }
    rt_by_label = {
        item["scenario_label"]: by_uid.get(item["trial_uid"], {}).get("rt_ms", "")
        for item in plan_trials
    }
    report = {
        "schema": SCHEMA,
        "passed": all(bool(value) for value in checks.values()),
        "participant_id": participant_id,
        "session_dir": str(result.session_dir),
        "run_setup_manifest": str(run_manifest),
        "response_plan_json": str(plan_path),
        "scripted_response_events_csv": str(output_dir / "scripted_response_events.csv"),
        "artifact_audit_json": str(Path(audit["output_dir"]) / "protocol11_emulated_runner_artifact_audit.json"),
        "events_csv": str(result.events_csv),
        "analysis_ready_trials_csv": str(analysis_ready_path),
        "timing_qc_csv": str(timing_qc_path),
        "event_type_counts": event_counts,
        "analysis_ready_trial_count": len(analysis_rows),
        "response_marker_minus_mouse_ms": _summary(marker_delta_values),
        "rt_ms_by_scenario": rt_by_label,
        "checks": checks,
        "capture_options": result.capture_options,
        "artifact_audit_passed": bool(audit.get("passed")),
        "artifact_audit_required": f"{audit.get('required_passed_count')}/{audit.get('required_count')}",
        "limitations": [
            "Fast sample-exact software emulation; not a wall-clock realtime validation.",
            "No physical audio interface, OS-click backend, LSL receiver, or Woojer mechanical onset is measured.",
            "Use alongside the existing realtime, UI mouse, LSL, top-up, and fault-injection Protocol 11 scenarios.",
        ],
    }
    (output_dir / "protocol11_controlled_response_matrix_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_markdown(report, output_dir / "protocol11_controlled_response_matrix_report.md")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Protocol 11 controlled emulated-response matrix.")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--participant-id", default="P011")
    parser.add_argument("--sample-rate", type=int, default=44100)
    parser.add_argument("--blocksize", type=int, default=512)
    parser.add_argument("--response-marker-delay-ms", type=float, default=8.0)
    parser.add_argument("--enable-lsl", action="store_true")
    args = parser.parse_args(argv)

    output_dir = args.output_dir or _default_output_dir()
    report = run_matrix(
        output_dir=output_dir,
        participant_id=args.participant_id,
        sample_rate=args.sample_rate,
        blocksize=args.blocksize,
        enable_lsl=args.enable_lsl,
        response_marker_delay_ms=args.response_marker_delay_ms,
    )
    print(f"Wrote Protocol 11 controlled-response report: {output_dir / 'protocol11_controlled_response_matrix_report.json'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
