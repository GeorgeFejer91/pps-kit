"""Protocol 11 capture-options matrix for SessionRunnerController outputs.

The harness runs several tiny real SessionRunnerController sessions with
different SessionCaptureOptions and verifies which durable artifacts are written
or suppressed. It validates output-policy mechanics only; response-boundary and
top-up behavior are covered by separate Protocol 11 scenarios.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

REPO_ROOT = Path(__file__).resolve().parents[4]
SRC_ROOT = REPO_ROOT / "packages" / "pps-runtime" / "src"
SCRIPT_DIR = Path(__file__).resolve().parent
for candidate in (SRC_ROOT, SCRIPT_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from peripersonal_space_toolkit.session_runner import (  # noqa: E402
    SessionCaptureOptions,
    SessionRunnerController,
    prepare_segment_run_package,
)
from peripersonal_space_toolkit.output_layout import (  # noqa: E402
    output_data_analytics_dir,
    output_runner_logs_dir,
    output_verbose_events_dir,
)
from run_one_block_trial_runner_realtime_stress import (  # noqa: E402
    _build_segment_fixture,
    _write_csv,
)


SCHEMA = "pps-protocol11-capture-options-matrix.v1"


def _default_output_dir() -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return Path("artifacts") / "validation_runs" / f"protocol11_capture_options_matrix_{stamp}"


def _event_counts(events: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        event_type = str(getattr(event, "event_type", "") or "")
        counts[event_type] = counts.get(event_type, 0) + 1
    return counts


def _path_status(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() and path.is_file() else 0,
    }


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _resolve_path(value: Any, *, base: Path, fallback: Path) -> Path:
    text = str(value or "").strip()
    if not text:
        return fallback
    path = Path(text)
    return path if path.is_absolute() else base / path


def _session_manifest_path(session_dir: Path) -> Path:
    return (
        session_dir / "session_manifest.json"
        if (session_dir / "session_manifest.json").is_file()
        else output_runner_logs_dir(session_dir.parent) / session_dir.name / "session_manifest.json"
    )


def _analysis_csv_paths(session_dir: Path, *, analysis_dir: Path | None = None) -> list[Path]:
    candidates = [analysis_dir or Path(), session_dir / "analysis", output_data_analytics_dir(session_dir.parent) / session_dir.name]
    seen: set[str] = set()
    paths: list[Path] = []
    for candidate in candidates:
        key = str(candidate)
        if key in seen or str(candidate) in {"", "."} or not candidate.exists():
            continue
        seen.add(key)
        paths.extend(sorted(path for path in candidate.glob("*.csv") if path.is_file()))
    return paths


def _capture_variants() -> list[dict[str, Any]]:
    return [
        {
            "name": "standard_all_local",
            "description": "All local mirrors enabled, LSL network disabled for offline validation.",
            "options": {
                "enable_lsl": False,
                "write_events_csv": True,
                "write_internal_xdf": True,
                "write_analysis_csvs": True,
                "write_lsl_marker_mirror": True,
                "write_trigger_dictionary": True,
                "start_backup_recording": True,
            },
        },
        {
            "name": "events_only_no_recording",
            "description": "Only events.csv is durable; no XDF, marker mirror, trigger dictionary, analysis CSVs, or recording.",
            "options": {
                "enable_lsl": False,
                "write_events_csv": True,
                "write_internal_xdf": False,
                "write_analysis_csvs": False,
                "write_lsl_marker_mirror": False,
                "write_trigger_dictionary": False,
                "start_backup_recording": False,
            },
        },
        {
            "name": "xdf_without_events_csv",
            "description": "Internal events XDF is durable while events.csv and analysis/LSL mirrors are disabled.",
            "options": {
                "enable_lsl": False,
                "write_events_csv": False,
                "write_internal_xdf": True,
                "write_analysis_csvs": False,
                "write_lsl_marker_mirror": False,
                "write_trigger_dictionary": False,
                "start_backup_recording": False,
            },
        },
        {
            "name": "analysis_without_xdf_or_lsl",
            "description": "Events CSV and analysis CSVs are durable; internal XDF, LSL mirrors, and trigger dictionary are disabled.",
            "options": {
                "enable_lsl": False,
                "write_events_csv": True,
                "write_internal_xdf": False,
                "write_analysis_csvs": True,
                "write_lsl_marker_mirror": False,
                "write_trigger_dictionary": False,
                "start_backup_recording": False,
            },
        },
        {
            "name": "marker_mirror_only",
            "description": "Only local marker mirror XDF/CSV plus trigger dictionary are durable; event CSV/XDF and analysis CSVs are disabled.",
            "options": {
                "enable_lsl": False,
                "write_events_csv": False,
                "write_internal_xdf": False,
                "write_analysis_csvs": False,
                "write_lsl_marker_mirror": True,
                "write_trigger_dictionary": True,
                "start_backup_recording": False,
            },
        },
    ]


class FastScheduleAudioEngine:
    """Fast callback-shaped engine that emits a block schedule without hardware."""

    def __init__(self, *, sample_rate: int):
        self.sample_rate = int(sample_rate)
        self.played_blocks: list[str] = []
        self.recording_paths: list[str] = []
        self.playback_started = threading.Event()
        self._last_block_path: Path | None = None
        self._recording_active = False
        self._recording_output_path: Path | None = None

    def play_block(self, path: str, progress_callback=None, audio_event_callback=None, block_event_schedule=None) -> bool:
        self.played_blocks.append(path)
        self._last_block_path = Path(path)
        info = sf.info(path)
        frames_total = int(info.frames)
        self.sample_rate = int(info.samplerate)
        duration_s = frames_total / float(self.sample_rate) if self.sample_rate else 0.0
        play_start_perf = time.perf_counter() - duration_s - 0.050
        if block_event_schedule is not None:
            block_event_schedule.reset()
        self.playback_started.set()
        if audio_event_callback is not None and block_event_schedule is not None:
            for event in block_event_schedule.consume_buffer(0, frames_total + 1):
                event_perf = play_start_perf + (int(event.sample_index) / float(self.sample_rate))
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
        return True

    def start_recording(self, output_path: str) -> bool:
        self._recording_active = True
        self._recording_output_path = Path(output_path)
        self.recording_paths.append(output_path)
        return True

    def is_recording(self) -> bool:
        return self._recording_active

    def stop_recording(self, output_path: str | None = None, interrupted: bool = False) -> None:
        self._recording_active = False
        target = Path(output_path) if output_path else self._recording_output_path
        if target is None:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        if self._last_block_path is not None and self._last_block_path.exists():
            shutil.copyfile(self._last_block_path, target)
        else:
            sf.write(target, np.zeros((1, 3), dtype=np.float32), self.sample_rate)

    def stop(self) -> None:
        return None

    def pause(self) -> None:
        return None

    def resume(self) -> None:
        return None

    def shutdown(self) -> None:
        return None


def _file_inventory(session_dir: Path) -> dict[str, Any]:
    manifest_path = _session_manifest_path(session_dir)
    manifest = _read_json(manifest_path)
    outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), dict) else {}
    manifest_base = manifest_path.parent if manifest_path.parent != Path() else session_dir
    verbose_dir = output_verbose_events_dir(session_dir.parent) / session_dir.name
    analysis_dir = _resolve_path(
        outputs.get("analysis_dir"),
        base=manifest_base,
        fallback=output_data_analytics_dir(session_dir.parent) / session_dir.name,
    )
    analysis_csvs = _analysis_csv_paths(session_dir, analysis_dir=analysis_dir)
    return {
        "events_csv": _path_status(_resolve_path(outputs.get("verbose_events_csv") or outputs.get("events_csv"), base=manifest_base, fallback=verbose_dir / "events.csv")),
        "events_xdf": _path_status(_resolve_path(outputs.get("verbose_events_xdf") or outputs.get("events_xdf"), base=manifest_base, fallback=verbose_dir / "events.xdf")),
        "lsl_markers_csv": _path_status(_resolve_path(outputs.get("lsl_markers_csv"), base=manifest_base, fallback=verbose_dir / "lsl_markers.csv")),
        "lsl_markers_xdf": _path_status(_resolve_path(outputs.get("lsl_markers_xdf"), base=manifest_base, fallback=verbose_dir / "lsl_markers.xdf")),
        "trigger_dictionary_json": _path_status(_resolve_path(outputs.get("trigger_dictionary_json"), base=manifest_base, fallback=verbose_dir / "trigger_dictionary.json")),
        "analysis_summary_txt": _path_status(_resolve_path(outputs.get("analysis_summary_txt"), base=manifest_base, fallback=analysis_dir / "analysis_summary.txt")),
        "session_metadata_json": _path_status(_resolve_path(outputs.get("session_metadata_json"), base=manifest_base, fallback=output_runner_logs_dir(session_dir.parent) / session_dir.name / "session_metadata.json")),
        "analysis_csvs": [str(path) for path in analysis_csvs],
        "analysis_csv_count": len(analysis_csvs),
    }


def _expected_file_checks(inventory: dict[str, Any], options: dict[str, bool]) -> dict[str, bool]:
    checks = {
        "events_csv_policy": bool(inventory["events_csv"]["exists"]) == bool(options["write_events_csv"]),
        "events_xdf_policy": bool(inventory["events_xdf"]["exists"]) == bool(options["write_internal_xdf"]),
        "lsl_markers_csv_policy": bool(inventory["lsl_markers_csv"]["exists"]) == bool(options["write_lsl_marker_mirror"]),
        "lsl_markers_xdf_policy": bool(inventory["lsl_markers_xdf"]["exists"]) == bool(options["write_lsl_marker_mirror"]),
        "trigger_dictionary_policy": bool(inventory["trigger_dictionary_json"]["exists"]) == bool(options["write_trigger_dictionary"]),
        "analysis_csv_policy": (int(inventory["analysis_csv_count"]) > 0) == bool(options["write_analysis_csvs"]),
        "session_metadata_always_written": bool(inventory["session_metadata_json"]["exists"]),
        "analysis_summary_written": bool(inventory["analysis_summary_txt"]["exists"]),
    }
    for key in (
        "events_csv",
        "events_xdf",
        "lsl_markers_csv",
        "lsl_markers_xdf",
        "trigger_dictionary_json",
        "session_metadata_json",
        "analysis_summary_txt",
    ):
        status = inventory[key]
        if status["exists"]:
            checks[f"{key}_nonempty"] = int(status["size_bytes"]) > 0
    return checks


def _recording_checks(events: list[Any], options: dict[str, bool], recording_paths: list[str]) -> dict[str, bool]:
    counts = _event_counts(events)
    if options["start_backup_recording"]:
        return {
            "recording_start_logged": counts.get("recording_start", 0) >= 1,
            "recording_end_logged": counts.get("recording_end", 0) >= 1,
            "recording_file_written": bool(recording_paths) and all(Path(path).exists() for path in recording_paths),
        }
    return {
        "recording_disabled_logged": counts.get("recording_disabled", 0) >= 1,
        "recording_not_written": not recording_paths,
    }


def _run_variant(
    *,
    run_manifest: Path,
    output_dir: Path,
    participant_id: str,
    sample_rate: int,
    created_at: datetime,
    variant: dict[str, Any],
) -> dict[str, Any]:
    variant_dir = output_dir / variant["name"]
    package = prepare_segment_run_package(
        run_manifest,
        participant_id,
        session_root=variant_dir / "sessions",
        created_at=created_at,
        use_block_cache=False,
    )
    options = SessionCaptureOptions(**variant["options"])
    engine = FastScheduleAudioEngine(sample_rate=sample_rate)
    controller = SessionRunnerController(package, audio_engine=engine, capture_options=options)
    result = controller.run()
    events = controller.logger.events
    inventory = _file_inventory(package.session_dir)
    checks = {
        "controller_completed": bool(result.completed and not result.interrupted),
        "event_log_in_memory": len(events) > 0,
        "block_schedule_exercised": _event_counts(events).get("audio_sample_zero", 0) == 1,
        **_expected_file_checks(inventory, options.as_dict()),
        **_recording_checks(events, options.as_dict(), [str(path) for path in result.recording_paths]),
    }
    return {
        "name": variant["name"],
        "description": variant["description"],
        "passed": all(bool(value) for value in checks.values()),
        "participant_id": participant_id,
        "session_dir": str(package.session_dir),
        "session_id": package.session_id,
        "capture_options": options.as_dict(),
        "completed": bool(result.completed),
        "interrupted": bool(result.interrupted),
        "event_counts": _event_counts(events),
        "file_inventory": inventory,
        "analysis_outputs": {key: str(path) for key, path in result.analysis_outputs.items()},
        "recording_paths": [str(path) for path in result.recording_paths],
        "checks": checks,
    }


def _write_variant_csv(path: Path, variants: list[dict[str, Any]]) -> None:
    rows = []
    for variant in variants:
        inventory = variant["file_inventory"]
        row = {
            "variant": variant["name"],
            "passed": variant["passed"],
            "session_dir": variant["session_dir"],
            "events_csv": inventory["events_csv"]["exists"],
            "events_xdf": inventory["events_xdf"]["exists"],
            "lsl_markers_csv": inventory["lsl_markers_csv"]["exists"],
            "lsl_markers_xdf": inventory["lsl_markers_xdf"]["exists"],
            "trigger_dictionary_json": inventory["trigger_dictionary_json"]["exists"],
            "analysis_csv_count": inventory["analysis_csv_count"],
            "analysis_summary_txt": inventory["analysis_summary_txt"]["exists"],
            "recording_count": len(variant["recording_paths"]),
        }
        for option, value in variant["capture_options"].items():
            row[f"option_{option}"] = value
        rows.append(row)
    _write_csv(path, rows, list(rows[0]) if rows else ["variant", "passed"])


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Protocol 11 Capture Options Matrix",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Variant count: `{len(report.get('variants', []))}`",
        f"- Run setup manifest: `{report.get('run_setup_manifest')}`",
        "",
        "## Variants",
    ]
    for variant in report.get("variants", []):
        inventory = variant.get("file_inventory", {})
        lines.append(
            "- `{}`: `{}` events_csv={} events_xdf={} lsl_csv={} lsl_xdf={} trigger={} analysis_csvs={} recordings={}".format(
                variant.get("name"),
                variant.get("passed"),
                inventory.get("events_csv", {}).get("exists"),
                inventory.get("events_xdf", {}).get("exists"),
                inventory.get("lsl_markers_csv", {}).get("exists"),
                inventory.get("lsl_markers_xdf", {}).get("exists"),
                inventory.get("trigger_dictionary_json", {}).get("exists"),
                inventory.get("analysis_csv_count"),
                len(variant.get("recording_paths", [])),
            )
        )
    lines.extend(
        [
            "",
            "This matrix validates local output-policy behavior with a fast fake audio engine. It does not measure physical audio timing, OS-click latency, external LSL receiver behavior, or Woojer mechanical onset.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_matrix(
    *,
    output_dir: Path,
    participant_id: str,
    sample_rate: int,
    trial_count: int,
    trial_duration_s: float,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    run_manifest = _build_segment_fixture(
        output_dir,
        participant_id=participant_id,
        trial_count=trial_count,
        sample_rate=sample_rate,
        trial_duration_s=trial_duration_s,
    )
    variants = []
    base_time = datetime.now()
    for index, variant in enumerate(_capture_variants()):
        variants.append(
            _run_variant(
                run_manifest=run_manifest,
                output_dir=output_dir,
                participant_id=participant_id,
                sample_rate=sample_rate,
                created_at=base_time + timedelta(seconds=index),
                variant=variant,
            )
        )
    report = {
        "schema": SCHEMA,
        "passed": all(bool(variant["passed"]) for variant in variants),
        "participant_id": participant_id,
        "run_setup_manifest": str(run_manifest),
        "output_dir": str(output_dir),
        "variant_count": len(variants),
        "variants": variants,
        "limitations": [
            "Fast fake-audio software run; no physical audio interface is opened.",
            "No emulated response clicks are injected in this capture matrix.",
            "Use alongside Protocol 11 response, top-up, LSL, OS-click, and operator-failure scenarios.",
        ],
    }
    report_path = output_dir / "protocol11_capture_options_matrix_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_variant_csv(output_dir / "protocol11_capture_options_matrix_variants.csv", variants)
    _write_markdown(output_dir / "protocol11_capture_options_matrix_report.md", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Protocol 11 capture option output matrix.")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--participant-id", default="P011")
    parser.add_argument("--sample-rate", type=int, default=44100)
    parser.add_argument("--trial-count", type=int, default=2)
    parser.add_argument("--trial-duration-s", type=float, default=0.250)
    args = parser.parse_args(argv)

    output_dir = args.output_dir or _default_output_dir()
    report = run_matrix(
        output_dir=output_dir,
        participant_id=args.participant_id,
        sample_rate=args.sample_rate,
        trial_count=args.trial_count,
        trial_duration_s=args.trial_duration_s,
    )
    print(f"Wrote Protocol 11 capture-options report: {output_dir / 'protocol11_capture_options_matrix_report.json'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
