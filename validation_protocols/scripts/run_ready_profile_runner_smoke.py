"""Run ready published profile packages through the runner with fake audio.

This smoke harness links Protocol 12 profile materialization to the actual
SessionRunnerController path. It proves prepared profile block WAVs can be
loaded, scheduled, logged, and analyzed by the runner without touching hardware.
It is not timing, loopback, tactile-perception, or behavioral replication
evidence.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import time
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

import run_profile_recreation_interface_matrix as protocol12  # noqa: E402
from peripersonal_space_toolkit.session_runner import (  # noqa: E402
    SessionCaptureOptions,
    SessionRunnerController,
    load_run_package,
)


SCHEMA = "pps-ready-profile-runner-smoke.v1"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "validation_runs" / "current_goal_ready_profile_runner_smoke_20260715"
EVIDENCE_BOUNDARY = (
    "This is a software-only runner-contract smoke using a fake audio engine. "
    "It proves prepared profile WAVs and schedules can run through "
    "SessionRunnerController and produce runner artifacts; it does not prove "
    "hardware timing, physical loopback, tactile perception, participant "
    "behavior, or published PPS effects."
)


class FastProfileSmokeAudioEngine:
    """Callback-shaped fake engine for prepared profile block WAVs."""

    def __init__(self, *, max_clicks_per_block: int = 1, response_delay_s: float = 0.12):
        self.max_clicks_per_block = max(0, int(max_clicks_per_block))
        self.response_delay_s = max(0.0, float(response_delay_s))
        self.played_blocks: list[str] = []
        self.played_instructions: list[str] = []
        self.recording_paths: list[str] = []
        self._audio_event_callback = None
        self._on_tactile = None
        self._current_block_path: Path | None = None
        self._block_start_perf = 0.0
        self._sample_rate = 44100
        self._clicks_this_block = 0
        self._stopped = False

    def set_tactile_callback(self, callback) -> None:
        self._on_tactile = callback

    def play_instruction(self, path: str, on_complete=None) -> bool:
        self.played_instructions.append(str(path))
        if on_complete is not None:
            on_complete(True)
        return True

    def play_block(self, path: str, progress_callback=None, audio_event_callback=None, block_event_schedule=None) -> bool:
        self._current_block_path = Path(path)
        self.played_blocks.append(str(path))
        self._audio_event_callback = audio_event_callback
        self._clicks_this_block = 0
        info = sf.info(path)
        self._sample_rate = int(info.samplerate)
        frames_total = int(info.frames)
        self._block_start_perf = time.perf_counter()
        if progress_callback is not None:
            progress_callback(0.0)
        if block_event_schedule is not None and audio_event_callback is not None:
            block_event_schedule.reset()
            for event in block_event_schedule.consume_buffer(0, frames_total + 1):
                if self._stopped:
                    break
                now = time.perf_counter()
                payload = dict(event.payload)
                payload.pop("sample_index", None)
                payload.pop("planned_sample_index", None)
                payload.update(
                    {
                        "event_type": event.event_type,
                        "sample_rate": self._sample_rate,
                        "sample_offset_in_buffer": 0,
                        "scheduled_sample_index": int(event.sample_index),
                        "callback_perf_counter": now,
                        "stream_current_time": now,
                        "stream_output_buffer_dac_time": now,
                        "trigger_key": event.trigger_key,
                    }
                )
                if event.event_type == "audio_sample_zero":
                    payload["sample_index"] = 0
                audio_event_callback(payload)
                if event.event_type == "tactile_onset" and self._clicks_this_block < self.max_clicks_per_block:
                    self._clicks_this_block += 1
                    if self._on_tactile is not None:
                        self._on_tactile()
        if progress_callback is not None:
            progress_callback(float(info.duration))
        return not self._stopped

    def trigger_click(self, metadata=None, marker_gain=None) -> None:
        if self._audio_event_callback is None:
            return
        now = time.perf_counter()
        sample_index = max(0, int(round((now - self._block_start_perf) * self._sample_rate)))
        payload = {
            "event_type": "response_marker_start",
            "sample_index": sample_index,
            "buffer_start_sample": sample_index,
            "sample_offset_in_buffer": 0,
            "sample_rate": self._sample_rate,
            "callback_perf_counter": now,
            "stream_current_time": now,
            "stream_output_buffer_dac_time": now,
            "marker_channel": 2,
            "marker_gain": marker_gain,
            **dict(metadata or {}),
        }
        self._audio_event_callback(payload)

    def start_recording(self, output_path=None) -> bool:
        if output_path:
            self.recording_paths.append(str(output_path))
        return True

    def stop_recording(self, output_path=None, interrupted=False):
        target = Path(output_path) if output_path else None
        if target is None:
            return None
        target.parent.mkdir(parents=True, exist_ok=True)
        if self._current_block_path is not None and self._current_block_path.exists():
            shutil.copyfile(self._current_block_path, target)
        else:
            sf.write(target, np.zeros((1, 3), dtype=np.float32), self._sample_rate)
        return None

    def stop(self) -> None:
        self._stopped = True

    def pause(self) -> None:
        return None

    def resume(self) -> None:
        return None

    def shutdown(self) -> None:
        self.stop()


def run_smoke(
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    templates: list[str] | None = None,
    profile_set: str = "ready-published",
    max_clicks_per_block: int = 1,
) -> dict[str, Any]:
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    status = protocol12.load_profile_recreation_status(REPO_ROOT)
    target_ids = templates or protocol12._target_template_ids(status, profile_set=profile_set)
    profile_results = [
        _run_profile(
            template_id,
            output_dir=output_dir,
            max_clicks_per_block=max_clicks_per_block,
        )
        for template_id in target_ids
    ]
    passed = bool(profile_results) and all(result["passed"] for result in profile_results)
    summary = _summary(profile_results)
    report = {
        "schema": SCHEMA,
        "generated_on": "2026-07-15",
        "profile_set": profile_set,
        "templates": target_ids,
        "passed": passed,
        "summary": summary,
        "evidence_boundary": EVIDENCE_BOUNDARY,
        "profiles": profile_results,
        "report_json": str(output_dir / "ready_profile_runner_smoke_report.json"),
        "report_md": str(output_dir / "ready_profile_runner_smoke_report.md"),
    }
    _write_json(Path(report["report_json"]), report)
    _write_markdown(Path(report["report_md"]), report)
    return report


def _run_profile(template_id: str, *, output_dir: Path, max_clicks_per_block: int) -> dict[str, Any]:
    materialized = protocol12._materialize_ready_profile(template_id, output_dir=output_dir)
    if materialized.get("status") != "prepared":
        return {
            "template_id": template_id,
            "passed": False,
            "materialization": materialized,
            "failure": "profile materialization did not prepare a session package",
        }
    package = load_run_package(Path(str(materialized["session_manifest_path"])))
    engine = FastProfileSmokeAudioEngine(max_clicks_per_block=max_clicks_per_block)
    controller = SessionRunnerController(
        package,
        audio_engine=engine,
        capture_options=SessionCaptureOptions(
            enable_lsl=False,
            write_events_csv=True,
            write_internal_xdf=True,
            write_analysis_csvs=True,
            write_lsl_marker_mirror=True,
            write_trigger_dictionary=True,
            start_backup_recording=True,
            start_external_labrecorder=False,
        ),
        enable_topup=False,
        instruction_continue_callback=lambda _context: True,
        runner_metadata={"participant_code": package.participant_id},
    )

    def _click_after_tactile() -> None:
        controller.events.flush_callback_events(timeout_s=0.5)
        if engine.response_delay_s:
            time.sleep(engine.response_delay_s)
        controller.log_click(x=320, y=240, in_target=True)

    engine.set_tactile_callback(_click_after_tactile)
    result = controller.run()
    controller.events.flush_callback_events(timeout_s=1.0)
    event_rows = _read_csv(result.events_csv)
    event_counts = _event_counts(event_rows)
    analysis_rows = _read_csv(result.analysis_outputs.get("analysis_ready_trials", Path()))
    block_wav_facts = [_wav_facts(block.wav_path) for block in package.blocks]
    recording_facts = [_wav_facts(path) for path in result.recording_paths if str(path).lower().endswith(".wav")]
    played_all_blocks = len(engine.played_blocks) == len(package.blocks)
    block_wavs_readable = bool(block_wav_facts) and all(fact["readable"] for fact in block_wav_facts)
    recordings_readable = bool(recording_facts) and all(fact["readable"] for fact in recording_facts)
    hit_count = sum(1 for row in analysis_rows if str(row.get("hit") or "").strip().lower() in {"true", "1", "yes"})
    criteria = {
        "completed": bool(result.completed and not result.interrupted),
        "played_all_prepared_blocks": played_all_blocks,
        "prepared_block_wavs_readable": block_wavs_readable,
        "events_csv_written": Path(result.events_csv).is_file(),
        "internal_xdf_written": Path(result.events_xdf).is_file(),
        "marker_mirror_written": bool(result.lsl_markers_csv and Path(result.lsl_markers_csv).is_file()),
        "trigger_dictionary_written": bool(result.trigger_dictionary_path and Path(result.trigger_dictionary_path).is_file()),
        "backup_recording_wavs_written": recordings_readable,
        "block_events_logged": event_counts.get("block_start", 0) == len(package.blocks)
        and event_counts.get("block_end", 0) == len(package.blocks),
        "trial_events_logged": event_counts.get("trial_start", 0) > 0 and event_counts.get("trial_end", 0) > 0,
        "tactile_and_response_marker_logged": event_counts.get("tactile_onset", 0) > 0
        and event_counts.get("mouse_click", 0) > 0
        and event_counts.get("response_marker_start", 0) > 0,
        "analysis_rows_written": len(analysis_rows) > 0,
        "at_least_one_valid_hit": hit_count > 0,
    }
    return {
        "template_id": template_id,
        "passed": all(criteria.values()),
        "criteria": criteria,
        "materialization": materialized,
        "session_manifest_path": str(package.manifest_path),
        "session_dir": str(package.session_dir),
        "block_count": len(package.blocks),
        "played_block_count": len(engine.played_blocks),
        "instruction_count": len(engine.played_instructions),
        "event_counts": event_counts,
        "analysis_ready_trial_count": len(analysis_rows),
        "analysis_ready_hit_count": hit_count,
        "recording_wav_count": len(recording_facts),
        "block_wavs": block_wav_facts,
        "recording_wavs": recording_facts,
        "outputs": {
            "events_csv": str(result.events_csv),
            "events_xdf": str(result.events_xdf),
            "analysis_ready_trials": str(result.analysis_outputs.get("analysis_ready_trials", "")),
            "participant_trials": str(result.analysis_outputs.get("participant_trials", "")),
            "lsl_markers_csv": str(result.lsl_markers_csv or ""),
            "trigger_dictionary": str(result.trigger_dictionary_path or ""),
            "session_metadata": str(result.session_metadata_path or ""),
        },
        "warnings": list(result.warnings),
    }


def _summary(profile_results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "profile_count": len(profile_results),
        "passed_profile_count": sum(1 for result in profile_results if result.get("passed")),
        "failed_profile_count": sum(1 for result in profile_results if not result.get("passed")),
        "total_blocks_played": sum(int(result.get("played_block_count") or 0) for result in profile_results),
        "total_analysis_ready_trials": sum(int(result.get("analysis_ready_trial_count") or 0) for result in profile_results),
        "total_analysis_ready_hits": sum(int(result.get("analysis_ready_hit_count") or 0) for result in profile_results),
        "total_response_markers": sum(int((result.get("event_counts") or {}).get("response_marker_start") or 0) for result in profile_results),
    }


def _read_csv(path: Path | str) -> list[dict[str, str]]:
    path = Path(path)
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _event_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        event_type = str(row.get("event_type") or "")
        if event_type:
            counts[event_type] = counts.get(event_type, 0) + 1
    return dict(sorted(counts.items()))


def _wav_facts(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    try:
        info = sf.info(path)
    except Exception as exc:  # noqa: BLE001 - report per-file readability.
        return {
            "path": str(path),
            "exists": path.is_file(),
            "readable": False,
            "error": str(exc),
        }
    return {
        "path": str(path),
        "exists": path.is_file(),
        "readable": True,
        "sample_rate": int(info.samplerate),
        "channels": int(info.channels),
        "frames": int(info.frames),
        "duration_s": float(info.duration),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Ready Profile Runner Smoke",
        "",
        f"- Passed: `{report['passed']}`",
        f"- Profiles: `{report['summary']['passed_profile_count']}/{report['summary']['profile_count']}`",
        f"- Blocks played: `{report['summary']['total_blocks_played']}`",
        f"- Analysis-ready rows: `{report['summary']['total_analysis_ready_trials']}`",
        f"- Response markers: `{report['summary']['total_response_markers']}`",
        "",
        EVIDENCE_BOUNDARY,
        "",
        "## Profiles",
        "",
    ]
    for profile in report["profiles"]:
        lines.append(
            f"- `{profile['template_id']}`: passed=`{profile['passed']}`, "
            f"blocks=`{profile.get('played_block_count')}/{profile.get('block_count')}`, "
            f"analysis_rows=`{profile.get('analysis_ready_trial_count')}`, "
            f"hits=`{profile.get('analysis_ready_hit_count')}`, "
            f"markers=`{(profile.get('event_counts') or {}).get('response_marker_start', 0)}`"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run ready profile packages through SessionRunnerController with fake audio.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--profile-set", choices=["ready-published", "ready-all"], default="ready-published")
    parser.add_argument("--template", action="append", default=[])
    parser.add_argument("--max-clicks-per-block", type=int, default=1)
    args = parser.parse_args(argv)

    report = run_smoke(
        output_dir=args.output_dir,
        templates=args.template or None,
        profile_set=args.profile_set,
        max_clicks_per_block=args.max_clicks_per_block,
    )
    print(f"Wrote ready profile runner smoke report: {report['report_json']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
