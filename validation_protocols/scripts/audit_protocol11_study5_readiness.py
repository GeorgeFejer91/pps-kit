"""Audit Protocol 11 Study 5 realtime runner-readiness evidence.

This is an offline evidence gate for completed packaged-runner validation
folders. It intentionally does not launch Focus Mode or play audio; instead it
checks the concrete files produced by a real run, including local XDF mirrors,
audio-evidence WAVs, screenshots, analysis CSVs, and expected-vs-observed event
counts.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import os
import statistics
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import soundfile as sf
from PIL import Image, ImageStat


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from peripersonal_space_toolkit.output_layout import _filesystem_path  # noqa: E402


SCHEMA = "pps-protocol11-study5-readiness-audit.v1"
TACTILE_TRIAL_TYPES = {"audio-tactile", "audio_tactile", "baseline"}
LOOMING_TRIAL_TYPES = {"audio-tactile", "audio_tactile", "catch"}
SCHEDULED_EVENT_TYPES = {
    "audio_sample_zero",
    "trial_start",
    "looming_onset",
    "tactile_onset",
    "response_window_onset",
    "trial_end",
    "response_marker_start",
}
OS_CLICK_BACKENDS = {"pyautogui", "pynput", "win32"}
EXPECTED_ANALYSIS_SUFFIXES = [
    "responses",
    "analysis_ready_trials",
    "final_trial_outcomes",
    "summary",
    "pps_curve_points",
    "sigmoid_fits",
    "model_fits",
    "model_fit_comparison",
    "timing_qc",
]


@dataclass
class Criterion:
    section: str
    name: str
    passed: bool
    detail: str = ""
    required: bool = True
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "section": self.section,
            "name": self.name,
            "passed": bool(self.passed),
            "required": bool(self.required),
            "detail": self.detail,
        }
        if self.evidence:
            payload["evidence"] = _json_ready(self.evidence)
        return payload


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value


def _mkdir(path: Path | str) -> None:
    os.makedirs(_filesystem_path(Path(path)), exist_ok=True)


def _path_exists(path: Path | str) -> bool:
    return os.path.exists(_filesystem_path(Path(path)))


def _path_is_file(path: Path | str) -> bool:
    return os.path.isfile(_filesystem_path(Path(path)))


def _path_is_dir(path: Path | str) -> bool:
    return os.path.isdir(_filesystem_path(Path(path)))


def _path_size(path: Path | str) -> int:
    try:
        return os.path.getsize(_filesystem_path(Path(path)))
    except OSError:
        return 0


def _path_mtime(path: Path | str) -> float:
    try:
        return os.path.getmtime(_filesystem_path(Path(path)))
    except OSError:
        return 0.0


def _display_path(value: str) -> Path:
    if value.startswith("\\\\?\\UNC\\"):
        return Path("\\\\" + value[len("\\\\?\\UNC\\") :])
    if value.startswith("\\\\?\\"):
        return Path(value[len("\\\\?\\") :])
    return Path(value)


def _canonical_path_text(path: Path | str) -> str:
    text = str(path)
    if text.startswith("\\\\?\\UNC\\"):
        text = "\\\\" + text[len("\\\\?\\UNC\\") :]
    elif text.startswith("\\\\?\\"):
        text = text[len("\\\\?\\") :]
    return os.path.normcase(os.path.normpath(text))


def _glob_files(directory: Path, pattern: str, *, recursive: bool = False) -> list[Path]:
    if not _path_is_dir(directory):
        return []
    matches = glob.glob(os.path.join(_filesystem_path(directory), pattern), recursive=recursive)
    return sorted(_display_path(item) for item in matches)


def _read_text(path: Path, *, encoding: str) -> str:
    with open(_filesystem_path(path), "r", encoding=encoding) as handle:
        return handle.read()


def _write_text(path: Path, text: str) -> None:
    _mkdir(path.parent)
    with open(_filesystem_path(path), "w", encoding="utf-8") as handle:
        handle.write(text)


def _read_json(path: Path) -> dict[str, Any]:
    if not _path_is_file(path):
        return {}
    for encoding in ("utf-8", "utf-8-sig", "utf-16"):
        try:
            return json.loads(_read_text(path, encoding=encoding))
        except (UnicodeError, json.JSONDecodeError):
            continue
        except Exception:
            return {}
    return {}


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not _path_is_file(path):
        return []
    with open(_filesystem_path(path), newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _write_text(path, json.dumps(_json_ready(payload), indent=2, sort_keys=True) + "\n")


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Protocol 11 Study 5 Readiness Audit",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Full Study 5 realtime ready: `{report.get('full_study5_realtime_ready')}`",
        f"- Scope: `{report.get('scope')}`",
        f"- Artifact dir: `{report.get('artifact_dir')}`",
        f"- Session dir: `{report.get('session_dir')}`",
        f"- Required criteria: `{report.get('required_passed_count')}/{report.get('required_count')}`",
        "",
        "## Sections",
    ]
    for name, summary in report.get("sections", {}).items():
        lines.append(f"- `{name}`: `{summary.get('passed')}` ({summary.get('passed_count')}/{summary.get('count')})")
    failures = [item for item in report.get("criteria", []) if item.get("required") and not item.get("passed")]
    if failures:
        lines.extend(["", "## Required Failures"])
        for failure in failures:
            lines.append(f"- `{failure.get('section')}.{failure.get('name')}`: {failure.get('detail')}")
    lines.extend(
        [
            "",
            "This audit verifies completed runner artifacts. It can prove XDF/local audio-evidence consistency and expected-vs-observed software behavior for the supplied run, but it does not replace physical loopback or Woojer mechanical-onset measurement.",
        ]
    )
    _write_text(path, "\n".join(lines) + "\n")


def _norm(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    return str(value).strip().lower() not in {"0", "false", "no", "none", "nan"}


def _as_float(value: Any, default: float = math.nan) -> float:
    try:
        result = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _as_int(value: Any, default: int | None = None) -> int | None:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(str(row.get("payload_json", "") or "{}"))
    except json.JSONDecodeError:
        return {}


def _event_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _read_csv(path):
        payload = _payload(row)
        merged: dict[str, Any] = dict(row)
        merged["payload"] = payload
        for key, value in payload.items():
            merged.setdefault(key, value)
        rows.append(merged)
    return rows


def _resolve_path(value: Any, *, base: Path) -> Path:
    text = str(value or "").strip()
    if not text:
        return Path()
    path = Path(text)
    if path.is_absolute():
        return path
    base_candidate = base / path
    if _path_exists(base_candidate):
        return base_candidate
    repo_candidate = REPO_ROOT / path
    if _path_exists(repo_candidate):
        return repo_candidate
    return base_candidate


def _path_is_set(path: Path | None) -> bool:
    return path is not None and str(path) not in {"", "."}


def _first_existing(paths: Iterable[Path]) -> Path | None:
    for path in paths:
        if _path_is_set(path) and _path_exists(path):
            return path
    return None


def _latest_analysis_csv(session_dir: Path, suffix: str, *, analysis_dir: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if analysis_dir is not None and _path_is_set(analysis_dir):
        candidates.append(analysis_dir)
    candidates.append(session_dir / "analysis")
    candidates.append(session_dir.parent / "Data_Analytics" / session_dir.name)
    seen: set[str] = set()
    matches: list[Path] = []
    for candidate in candidates:
        key = str(candidate)
        if key in seen or not _path_is_dir(candidate):
            continue
        seen.add(key)
        matches.extend(_glob_files(candidate, f"*_{suffix}.csv"))
    return matches[-1] if matches else None


def _block_manifest_paths(session_dir: Path, manifest: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for block in manifest.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        path = _resolve_path(block.get("manifest_path") or block.get("csv_path"), base=session_dir)
        if path:
            paths.append(path)
    if not paths:
        paths.extend(_glob_files(session_dir / "blocks", "*.csv"))
    return list(dict.fromkeys(paths))


def _block_wav_paths(session_dir: Path, manifest: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for block in manifest.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        path = _resolve_path(block.get("wav_path"), base=session_dir)
        if path:
            paths.append(path)
    if not paths:
        paths.extend(_glob_files(session_dir / "blocks", "*.wav"))
    return list(dict.fromkeys(paths))


def _trial_type(row: dict[str, Any]) -> str:
    return _norm(row.get("Trial_Type") or row.get("trial_type") or row.get("Family") or row.get("family"))


def _trial_uid(row: dict[str, Any]) -> str:
    return str(row.get("Trial_UID") or row.get("trial_uid") or "").strip()


def _has_value(row: dict[str, Any], *keys: str) -> bool:
    return any(str(row.get(key, "")).strip() not in {"", "nan", "None", "none"} for key in keys)


def _sample_count_expected(block_rows: list[dict[str, str]]) -> dict[str, int]:
    expected = Counter()
    expected["trial_start"] = len(block_rows)
    expected["response_window_onset"] = len(block_rows)
    expected["trial_end"] = len(block_rows)
    for row in block_rows:
        trial_type = _trial_type(row)
        if trial_type in LOOMING_TRIAL_TYPES or _has_value(row, "Looming_Onset_Sample", "looming_onset_sample"):
            expected["looming_onset"] += 1
        if trial_type in TACTILE_TRIAL_TYPES or _has_value(row, "Tactile_Onset_Sample", "tactile_onset_sample"):
            expected["tactile_onset"] += 1
    return dict(expected)


def _schedule_expected_counts(session_dir: Path, manifest: dict[str, Any]) -> dict[str, int]:
    block_paths = _block_manifest_paths(session_dir, manifest)
    expected = Counter()
    for path in block_paths:
        rows = _read_csv(path)
        expected.update(_sample_count_expected(rows))
    block_count = len(block_paths)
    expected["audio_sample_zero"] = block_count
    expected["block_schedule_loaded"] = block_count
    expected["block_start"] = block_count
    expected["block_end"] = block_count
    return dict(expected)


def _ms_stats(values: Iterable[float]) -> dict[str, Any]:
    finite = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not finite:
        return {"count": 0}
    p95_index = min(len(finite) - 1, int(math.ceil(len(finite) * 0.95)) - 1)
    return {
        "count": len(finite),
        "mean_ms": statistics.fmean(finite),
        "sd_ms": statistics.stdev(finite) if len(finite) > 1 else 0.0,
        "median_ms": statistics.median(finite),
        "p95_ms": finite[p95_index],
        "min_ms": min(finite),
        "max_ms": max(finite),
    }


def _file_inventory(paths: dict[str, Path]) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    for key, path in paths.items():
        inventory[key] = {
            "path": str(path),
            "exists": _path_is_file(path),
            "bytes": _path_size(path) if _path_is_file(path) else 0,
        }
    return inventory


def _xdf_summary(path: Path) -> dict[str, Any]:
    if not _path_is_file(path):
        return {"exists": False, "loaded": False, "sample_count": 0, "streams": [], "error": "missing"}
    try:
        import pyxdf  # type: ignore

        streams, _header = pyxdf.load_xdf(_filesystem_path(path))
    except Exception as exc:  # pragma: no cover - parser error surface is environment-specific
        return {"exists": True, "loaded": False, "sample_count": 0, "streams": [], "error": str(exc)}
    stream_summaries = []
    total = 0
    for stream in streams:
        info = stream.get("info") or {}
        name = str((info.get("name") or [""])[0])
        stream_type = str((info.get("type") or [""])[0])
        channel_count = _as_int((info.get("channel_count") or [""])[0], default=0) or 0
        sample_count = len(stream.get("time_stamps", []))
        total += sample_count
        stream_summaries.append(
            {
                "name": name,
                "type": stream_type,
                "channel_count": channel_count,
                "sample_count": sample_count,
            }
        )
    return {"exists": True, "loaded": True, "sample_count": total, "streams": stream_summaries, "error": ""}


def _screenshot_summary(path: Path) -> dict[str, Any]:
    if not _path_is_file(path):
        return {"exists": False, "valid": False, "nonblank": False, "error": "missing"}
    try:
        with Image.open(_filesystem_path(path)) as image:
            image.load()
            stat = ImageStat.Stat(image.convert("RGB"))
            extrema = image.convert("RGB").getextrema()
            nonblank = any(lo != hi for lo, hi in extrema)
            return {
                "exists": True,
                "valid": True,
                "nonblank": bool(nonblank),
                "width": int(image.width),
                "height": int(image.height),
                "mode": image.mode,
                "mean_rgb": [float(value) for value in stat.mean],
            }
    except Exception as exc:
        return {"exists": True, "valid": False, "nonblank": False, "error": str(exc)}


def _wav_scan(path: Path, *, blocksize: int = 65536) -> dict[str, Any]:
    if not _path_is_file(path):
        return {"exists": False, "readable": False, "error": "missing"}
    try:
        audio_path = _filesystem_path(path)
        info = sf.info(audio_path)
        peaks = np.zeros(int(info.channels), dtype=np.float64)
        rms_sum = np.zeros(int(info.channels), dtype=np.float64)
        frames_seen = 0
        with sf.SoundFile(audio_path) as handle:
            while True:
                chunk = handle.read(blocksize, dtype="float32", always_2d=True)
                if chunk.size == 0:
                    break
                peaks = np.maximum(peaks, np.max(np.abs(chunk), axis=0))
                rms_sum += np.sum(np.square(chunk.astype(np.float64)), axis=0)
                frames_seen += int(chunk.shape[0])
        rms = np.sqrt(rms_sum / max(frames_seen, 1))
        return {
            "exists": True,
            "readable": True,
            "samplerate": int(info.samplerate),
            "channels": int(info.channels),
            "frames": int(info.frames),
            "duration_s": float(info.duration),
            "max_abs_by_channel": [float(value) for value in peaks],
            "rms_by_channel": [float(value) for value in rms],
            "error": "",
        }
    except Exception as exc:
        return {"exists": True, "readable": False, "error": str(exc)}


def _flatten_json_values(value: Any) -> list[str]:
    if isinstance(value, dict):
        values: list[str] = []
        for item in value.values():
            values.extend(_flatten_json_values(item))
        return values
    if isinstance(value, list):
        values = []
        for item in value:
            values.extend(_flatten_json_values(item))
        return values
    return [str(value)] if value not in (None, "") else []


def _planned_click_summary(focus_report: dict[str, Any]) -> dict[str, Any]:
    actions = [item for item in focus_report.get("validation_mouse_clicks") or [] if isinstance(item, dict)]
    standard = [item for item in actions if item.get("action") == "standard_click"]
    topup = [item for item in actions if item.get("action") == "topup_click"]
    misses = [item for item in actions if item.get("action") == "deliberate_miss"]
    plan_headers = [item for item in actions if item.get("label") == "participant_emulator_plan"]
    return {
        "standard_click_count": len(standard),
        "topup_click_count": len(topup),
        "all_click_count": len(standard) + len(topup),
        "deliberate_miss_count": len(misses),
        "plan_declared_tactile_count": _as_int(plan_headers[-1].get("standard_tactile_cue_count"), default=None) if plan_headers else None,
        "plan_declared_miss_count": _as_int(plan_headers[-1].get("planned_miss_count"), default=None) if plan_headers else None,
        "standard_clicks": standard,
        "topup_clicks": topup,
        "misses": misses,
    }


def _click_event_id(row: dict[str, Any]) -> str:
    for key in ("click_event_id", "topup_click_event_id", "mouse_event_id"):
        text = str(row.get(key) or "").strip()
        if text:
            return text
    return ""


def _analysis_selection_audit(
    *,
    planned: dict[str, Any],
    analysis_ready_rows: list[dict[str, str]],
    response_rows: list[dict[str, str]],
    mouse_event_ids: set[str],
    scheduled_tactile_count: int,
) -> dict[str, Any]:
    hit_rows = [row for row in analysis_ready_rows if _truthy(row.get("hit") or row.get("Hit"))]
    original_hit_rows = [
        row
        for row in analysis_ready_rows
        if _truthy(row.get("hit") or row.get("Hit")) and _norm(row.get("final_outcome_source") or "original") in {"", "original"}
    ]
    topup_rescue_rows = [
        row
        for row in analysis_ready_rows
        if _truthy(row.get("hit") or row.get("Hit")) and _norm(row.get("final_outcome_source")) == "topup_rescue"
    ]
    response_hit_rows = [row for row in response_rows if _truthy(row.get("hit") or row.get("Hit"))]
    response_selected_ids = [_click_event_id(row) for row in response_hit_rows]
    response_selected_ids = [value for value in response_selected_ids if value]
    duplicate_selected_ids = sorted(value for value, count in Counter(response_selected_ids).items() if count > 1)
    selected_id_set = set(response_selected_ids)
    missing_selected_ids = sorted(selected_id_set - mouse_event_ids)
    extra_logged_mouse_ids = sorted(mouse_event_ids - selected_id_set, key=lambda value: (0, int(value)) if value.isdigit() else (1, value))

    declared_tactile_count = planned.get("plan_declared_tactile_count")
    if declared_tactile_count is None:
        declared_tactile_count = len(analysis_ready_rows)
    declared_miss_count = planned.get("plan_declared_miss_count")
    if declared_miss_count is None:
        declared_miss_count = planned.get("deliberate_miss_count", 0)
    standard_click_count = int(planned.get("standard_click_count") or 0)
    topup_click_count = int(planned.get("topup_click_count") or 0)
    planned_click_count = int(planned.get("all_click_count") or standard_click_count + topup_click_count)

    final_hits_cover_standard_pool = len(hit_rows) == int(declared_tactile_count or -1)
    expected_original_hits_ok = len(original_hit_rows) <= standard_click_count if standard_click_count else True
    expected_topup_ok = int(declared_miss_count or 0) == 0 or len(topup_rescue_rows) >= int(declared_miss_count or 0)
    return {
        "analysis_ready_rows": len(analysis_ready_rows),
        "analysis_ready_hit_count": len(hit_rows),
        "analysis_ready_original_hit_count": len(original_hit_rows),
        "analysis_ready_topup_rescue_hit_count": len(topup_rescue_rows),
        "response_rows": len(response_rows),
        "response_hit_count": len(response_hit_rows),
        "response_selected_click_event_id_count": len(response_selected_ids),
        "raw_mouse_click_count": len(mouse_event_ids),
        "extra_logged_mouse_click_count": max(0, len(mouse_event_ids) - len(selected_id_set)),
        "extra_logged_mouse_event_ids": extra_logged_mouse_ids[:20],
        "duplicate_selected_click_event_ids": duplicate_selected_ids[:20],
        "missing_selected_mouse_event_ids": missing_selected_ids[:20],
        "scheduled_tactile_onset_count": scheduled_tactile_count,
        "declared_standard_tactile_count": declared_tactile_count,
        "declared_miss_count": declared_miss_count,
        "planned_standard_click_count": standard_click_count,
        "planned_topup_click_count": topup_click_count,
        "planned_all_click_count": planned_click_count,
        "rows_match_declared_standard_tactile_count": len(analysis_ready_rows) == int(declared_tactile_count or -1),
        "original_hits_match_standard_plan": expected_original_hits_ok,
        "topup_rescues_match_miss_plan": expected_topup_ok,
        "response_hits_match_all_planned_clicks": len(response_hit_rows) >= standard_click_count,
        "selected_click_ids_are_unique_and_logged": (
            len(response_selected_ids) == len(response_hit_rows)
            and not duplicate_selected_ids
            and not missing_selected_ids
        ),
        "final_hits_cover_standard_pool": final_hits_cover_standard_pool,
    }


def _response_marker_reports(artifact_dir: Path) -> list[dict[str, Any]]:
    reports = []
    for path in _glob_files(artifact_dir, "**/response_marker_loopback_report.json", recursive=True):
        payload = _read_json(path)
        if not payload:
            continue
        payload = dict(payload)
        payload["_path"] = str(path)
        payload["_mtime"] = _path_mtime(path)
        reports.append(payload)
    return reports


def _best_response_marker_report(artifact_dir: Path) -> dict[str, Any]:
    reports = _response_marker_reports(artifact_dir)
    if not reports:
        return {"exists": False, "passed": False, "reports": []}
    passed = [report for report in reports if bool(report.get("passed"))]
    chosen = max(passed or reports, key=lambda item: (bool(item.get("passed")), float(item.get("detection_rate") or 0.0), float(item.get("_mtime") or 0.0)))
    return {"exists": True, "passed": bool(chosen.get("passed")), "chosen": chosen, "reports": reports}


def _response_marker_report_from_audio(
    *,
    events_csv: Path,
    recordings: list[Path],
    output_dir: Path,
) -> dict[str, Any]:
    if not _path_is_file(events_csv) or not recordings:
        return {"exists": False, "passed": False, "generated": False, "error": "missing events.csv or audio evidence recordings"}
    try:
        from compare_response_marker_loopback import compare_loopback  # type: ignore

        report = compare_loopback(
            events_csv=events_csv,
            recordings=recordings,
            output_dir=output_dir,
            tactile_channel_1based=3,
        )
    except Exception as exc:
        return {"exists": False, "passed": False, "generated": False, "error": str(exc)}
    report = dict(report)
    report["exists"] = True
    report["generated"] = True
    report["_path"] = str(output_dir / "response_marker_loopback_report.json")
    return {"exists": True, "passed": bool(report.get("passed")), "chosen": report, "reports": [report], "generated": True}


def _audio_evidence_records(session_dir: Path) -> list[dict[str, Any]]:
    sidecars = _glob_files(session_dir, "*audio_evidence.output_evidence.json")
    recordings_dir = session_dir / "recordings"
    if not sidecars and _path_exists(recordings_dir):
        sidecars = _glob_files(recordings_dir, "*output_evidence.json")
    records: list[dict[str, Any]] = []
    for sidecar_path in sidecars:
        sidecar = _read_json(sidecar_path)
        wav_path = _resolve_path(sidecar.get("path"), base=session_dir) if sidecar else Path()
        if not _path_is_set(wav_path):
            candidate = sidecar_path.with_suffix("")
            if candidate.name.endswith(".output_evidence"):
                candidate = candidate.with_name(candidate.name[: -len(".output_evidence")] + ".wav")
            wav_path = candidate
        records.append(
            {
                "sidecar_path": sidecar_path,
                "wav_path": wav_path,
                "sidecar": sidecar,
                "scan": _wav_scan(wav_path),
            }
        )
    if not records:
        for wav_path in _glob_files(session_dir, "*audio_evidence.wav"):
            records.append({"sidecar_path": Path(), "wav_path": wav_path, "sidecar": {}, "scan": _wav_scan(wav_path)})
    return records


def _audio_record_ok(record: dict[str, Any]) -> bool:
    sidecar = record.get("sidecar") or {}
    device_name = str(sidecar.get("device_name") or sidecar.get("device") or "")
    return (
        bool(sidecar)
        and sidecar.get("schema") == "pps-digital-output-evidence.v1"
        and "komplete" in device_name.lower()
        and str(sidecar.get("hostapi", "")).upper() == "ASIO"
        and int(sidecar.get("runtime_output_channels") or 0) >= 4
        and int(sidecar.get("tactile_output_channel_1based") or 0) == 3
        and int(sidecar.get("dropped_buffer_count") or 0) == 0
        and not bool(sidecar.get("interrupted"))
    )


def _audio_wav_matches_sidecar(record: dict[str, Any]) -> bool:
    sidecar = record.get("sidecar") or {}
    scan = record.get("scan") or {}
    return bool(
        scan.get("readable")
        and int(scan.get("frames") or -1) == int(sidecar.get("frames") or -2)
        and int(scan.get("samplerate") or -1) == int(sidecar.get("sample_rate") or sidecar.get("sample_rate_hz") or -2)
    )


def _audio_signal_shape_ok(record: dict[str, Any]) -> bool:
    peaks = [float(value) for value in (record.get("scan") or {}).get("max_abs_by_channel", [])]
    sidecar = record.get("sidecar") or {}
    duplicate_channel = _as_int(sidecar.get("duplicate_tactile_output_channel_1based"), default=0)
    output4_ok = peaks[3] <= 1e-6
    if duplicate_channel == 4:
        output4_ok = peaks[3] > 0
    return len(peaks) >= 4 and all(value > 0 for value in peaks[:3]) and output4_ok


def _computed_reconciliation_report(
    *,
    session_dir: Path,
    output_dir: Path,
    event_counts: dict[str, int],
    marker_counts: dict[str, int],
    reconciliation: dict[str, Any],
    xdf: dict[str, Any],
    audio_records: list[dict[str, Any]],
) -> dict[str, Any]:
    audio_wavs = [Path(record["wav_path"]) for record in audio_records if _path_is_set(Path(record["wav_path"]))]
    session_dir_key = _canonical_path_text(session_dir)
    criteria = {
        "events_xdf_loadable": bool(xdf.get("events_xdf", {}).get("loaded")),
        "lsl_markers_xdf_loadable": bool(xdf.get("lsl_markers_xdf", {}).get("loaded")),
        "events_and_lsl_marker_ids_match": not reconciliation.get("missing_from_lsl_markers_csv") and not reconciliation.get("extra_in_lsl_markers_csv"),
        "event_types_match_between_csv_layers": not reconciliation.get("event_type_mismatches"),
        "event_codes_match_between_csv_layers": not reconciliation.get("event_code_mismatches"),
        "trigger_keys_match_between_csv_layers": not reconciliation.get("trigger_key_mismatches"),
        "xdf_and_audio_evidence_share_session_folder": bool(audio_wavs)
        and all(_canonical_path_text(Path(path).parent) == session_dir_key for path in audio_wavs),
        "audio_evidence_is_komplete_asio": bool(audio_records) and all(_audio_record_ok(record) for record in audio_records),
        "audio_evidence_is_four_channel_runtime": bool(audio_records)
        and all(int((record.get("sidecar") or {}).get("runtime_output_channels") or 0) >= 4 for record in audio_records),
        "tactile_channel_is_output_3": bool(audio_records)
        and all(int((record.get("sidecar") or {}).get("tactile_output_channel_1based") or 0) == 3 for record in audio_records),
        "silent_output_4_confirmed": bool(audio_records) and all(_audio_signal_shape_ok(record) for record in audio_records),
        "no_audio_drops_or_interrupts": bool(audio_records)
        and all(int((record.get("sidecar") or {}).get("dropped_buffer_count") or 0) == 0 and not bool((record.get("sidecar") or {}).get("interrupted")) for record in audio_records),
    }
    report = {
        "schema": "pps-lsl-xdf-audio-reconciliation.v1",
        "session_dir": str(session_dir),
        "passed": all(criteria.values()),
        "criteria": criteria,
        "event_counts": event_counts,
        "lsl_marker_counts": marker_counts,
        "row_counts": {
            "events_csv": reconciliation.get("events_csv_count", 0),
            "lsl_markers_csv": reconciliation.get("lsl_markers_csv_count", 0),
        },
        "event_id_reconciliation": {
            "missing_from_lsl_markers_csv": reconciliation.get("missing_from_lsl_markers_csv", []),
            "extra_in_lsl_markers_csv": reconciliation.get("extra_in_lsl_markers_csv", []),
            "event_type_mismatches": reconciliation.get("event_type_mismatches", []),
            "event_code_mismatches": reconciliation.get("event_code_mismatches", []),
            "trigger_key_mismatches": reconciliation.get("trigger_key_mismatches", []),
        },
        "xdf": xdf,
        "audio_evidence": [
            {
                "sidecar_path": str(record.get("sidecar_path") or ""),
                "wav_path": str(record.get("wav_path") or ""),
                "sidecar": record.get("sidecar") or {},
                "scan": record.get("scan") or {},
            }
            for record in audio_records
        ],
    }
    _mkdir(output_dir)
    _write_json(output_dir / "lsl_xdf_audio_reconciliation_report.json", report)
    return report


def _event_id_reconciliation(events: list[dict[str, Any]], markers: list[dict[str, str]]) -> dict[str, Any]:
    event_by_id = {str(row.get("event_id", "")).strip(): row for row in events if str(row.get("event_id", "")).strip()}
    marker_by_id = {str(row.get("event_id", "")).strip(): row for row in markers if str(row.get("event_id", "")).strip()}
    event_ids = set(event_by_id)
    marker_ids = set(marker_by_id)
    common = sorted(event_ids & marker_ids, key=lambda item: int(item) if item.isdigit() else item)
    type_mismatches = []
    code_mismatches = []
    key_mismatches = []
    for event_id in common:
        event = event_by_id[event_id]
        marker = marker_by_id[event_id]
        if str(event.get("event_type", "")) != str(marker.get("event_type", "")):
            type_mismatches.append(event_id)
        event_code = str(event.get("event_code", "") or event.get("payload", {}).get("event_code", ""))
        marker_code = str(marker.get("event_code", ""))
        if event_code and marker_code and event_code != marker_code:
            code_mismatches.append(event_id)
        event_key = str(event.get("trigger_key", "") or event.get("payload", {}).get("trigger_key", ""))
        marker_key = str(marker.get("trigger_key", ""))
        if event_key and marker_key and event_key != marker_key:
            key_mismatches.append(event_id)
    return {
        "events_csv_count": len(events),
        "lsl_markers_csv_count": len(markers),
        "missing_from_lsl_markers_csv": sorted(event_ids - marker_ids, key=lambda item: int(item) if item.isdigit() else item),
        "extra_in_lsl_markers_csv": sorted(marker_ids - event_ids, key=lambda item: int(item) if item.isdigit() else item),
        "event_type_mismatches": type_mismatches,
        "event_code_mismatches": code_mismatches,
        "trigger_key_mismatches": key_mismatches,
    }


def _validate_manifest_samples(block_paths: list[Path]) -> dict[str, Any]:
    mismatches = []
    row_counts = []
    cue_checks = Counter()
    for path in block_paths:
        rows = _read_csv(path)
        row_counts.append({"path": str(path), "rows": len(rows)})
        for row in rows:
            trial_uid = _trial_uid(row)
            sample_rate = _as_float(row.get("Sample_Rate_Hz") or row.get("sample_rate_hz"), default=math.nan)
            if not math.isfinite(sample_rate) or sample_rate <= 0:
                mismatches.append({"path": str(path), "trial_uid": trial_uid, "field": "Sample_Rate_Hz", "expected": "positive", "observed": row.get("Sample_Rate_Hz", "")})
                continue
            trial_start_s = _as_float(row.get("Trial_Start_S"), default=0.0)
            checks = [
                ("Trial_Start_Sample", trial_start_s),
                ("Response_Window_Onset_Sample", trial_start_s + _as_float(row.get("Response_Window_Onset_S"), default=0.0)),
                ("Trial_End_Sample", _as_float(row.get("Trial_End_S"), default=trial_start_s + _as_float(row.get("Trial_Duration_S"), default=0.0))),
            ]
            if _has_value(row, "Looming_Onset_Sample"):
                checks.append(("Looming_Onset_Sample", trial_start_s + _as_float(row.get("Looming_Onset_S"), default=0.0)))
            if _has_value(row, "Tactile_Onset_Sample"):
                checks.append(("Tactile_Onset_Sample", trial_start_s + _as_float(row.get("Tactile_Onset_S"), default=0.0)))
            for field, seconds in checks:
                observed = _as_int(row.get(field), default=None)
                expected = int(round(seconds * sample_rate))
                if observed != expected:
                    mismatches.append({"path": str(path), "trial_uid": trial_uid, "field": field, "expected": expected, "observed": observed})
            trial_type = _trial_type(row)
            if trial_type == "catch" and not _has_value(row, "Tactile_Onset_Sample", "Tactile_Onset_S"):
                cue_checks["catch_without_tactile"] += 1
            elif trial_type == "catch":
                mismatches.append({"path": str(path), "trial_uid": trial_uid, "field": "catch_tactile", "expected": "blank", "observed": row.get("Tactile_Onset_Sample", "")})
            if trial_type == "baseline" and _has_value(row, "Tactile_Onset_Sample", "Tactile_Onset_S"):
                cue_checks["baseline_with_tactile"] += 1
            elif trial_type == "baseline":
                mismatches.append({"path": str(path), "trial_uid": trial_uid, "field": "baseline_tactile", "expected": "present", "observed": ""})
            if trial_type in {"audio_tactile", "audio-tactile"}:
                soa_ms = _as_float(row.get("SOA_ms") or row.get("soa_ms"), default=math.nan)
                looming_s = _as_float(row.get("Looming_Onset_S"), default=math.nan)
                tactile_s = _as_float(row.get("Tactile_Onset_S"), default=math.nan)
                if math.isfinite(soa_ms) and math.isfinite(looming_s) and math.isfinite(tactile_s):
                    observed_soa_ms = (tactile_s - looming_s) * 1000.0
                    if abs(observed_soa_ms - soa_ms) <= 0.51:
                        cue_checks["audio_tactile_soa_preserved"] += 1
                    else:
                        mismatches.append(
                            {
                                "path": str(path),
                                "trial_uid": trial_uid,
                                "field": "SOA_ms",
                                "expected": soa_ms,
                                "observed": observed_soa_ms,
                            }
                        )
    return {"mismatches": mismatches, "row_counts": row_counts, "cue_checks": dict(cue_checks)}


def _analysis_rt_audit(
    focus_report: dict[str, Any],
    analysis_ready_rows: list[dict[str, str]],
    tolerance_ms: float,
    os_click_p95_tolerance_ms: float,
    os_click_max_tolerance_ms: float,
) -> dict[str, Any]:
    click_summary = _planned_click_summary(focus_report)
    row_by_uid = {str(row.get("trial_uid") or row.get("Trial_UID") or ""): row for row in analysis_ready_rows}
    diffs = []
    planned_diffs = []
    missing = []
    backends = Counter()
    outliers = []
    skipped_topup_rescued = []
    skipped_unselected = []
    for click in click_summary["standard_clicks"]:
        trial_uid = str(click.get("trial_uid") or "")
        row = row_by_uid.get(trial_uid)
        if row is None:
            missing.append(trial_uid)
            continue
        if str(row.get("final_outcome_source") or "original").strip().lower() != "original":
            skipped_topup_rescued.append(trial_uid)
            continue
        if str(row.get("click_event_id") or "") != str(click.get("mouse_event_id") or ""):
            skipped_unselected.append(trial_uid)
            continue
        backend = _norm(click.get("backend"))
        if backend:
            backends[backend] += 1
        planned_schedule_rt = _as_float(click.get("planned_delay_ms"), default=math.nan)
        planned_rt = _as_float(click.get("actual_delay_ms"), default=math.nan)
        observed_rt = _as_float(row.get("rt_ms") or row.get("RT_ms"), default=math.nan)
        if math.isfinite(planned_rt) and math.isfinite(observed_rt):
            diff = observed_rt - planned_rt
            diffs.append(diff)
            if abs(diff) > tolerance_ms:
                outliers.append(
                    {
                        "trial_uid": trial_uid,
                        "backend": backend,
                        "emulated_actual_delay_ms": planned_rt,
                        "analysis_rt_ms": observed_rt,
                        "absolute_error_ms": abs(diff),
                    }
                )
        if math.isfinite(planned_schedule_rt) and math.isfinite(observed_rt):
            planned_diffs.append(observed_rt - planned_schedule_rt)
    stats = _ms_stats([abs(value) for value in diffs])
    planned_stats = _ms_stats([abs(value) for value in planned_diffs])
    os_backend_observed = any(backend in OS_CLICK_BACKENDS for backend in backends)
    max_error = float(stats.get("max_ms", 0.0)) if stats.get("count", 0) else 0.0
    p95_error = float(stats.get("p95_ms", 0.0)) if stats.get("count", 0) else 0.0
    strict_within_tolerance = max_error <= tolerance_ms
    os_distribution_within_tolerance = os_backend_observed and p95_error <= os_click_p95_tolerance_ms and max_error <= os_click_max_tolerance_ms
    return {
        "planned_standard_click_count": click_summary["standard_click_count"],
        "planned_deliberate_miss_count": click_summary["deliberate_miss_count"],
        "declared_tactile_count": click_summary["plan_declared_tactile_count"],
        "declared_miss_count": click_summary["plan_declared_miss_count"],
        "matched_rt_count": len(diffs),
        "missing_analysis_uids": missing,
        "skipped_topup_rescued_standard_uids": skipped_topup_rescued,
        "skipped_unselected_standard_uids": skipped_unselected,
        "backend_counts": dict(backends),
        "os_click_backend_observed": os_backend_observed,
        "absolute_rt_error_ms": stats,
        "absolute_rt_error_against_planned_schedule_ms": planned_stats,
        "strict_max_tolerance_ms": tolerance_ms,
        "os_click_p95_tolerance_ms": os_click_p95_tolerance_ms,
        "os_click_max_tolerance_ms": os_click_max_tolerance_ms,
        "strict_max_within_tolerance": strict_within_tolerance,
        "os_distribution_within_tolerance": os_distribution_within_tolerance,
        "outliers_over_strict_tolerance": sorted(outliers, key=lambda item: float(item["absolute_error_ms"]), reverse=True)[:20],
        "within_tolerance": not missing and not skipped_unselected and (stats.get("count", 0) == 0 or strict_within_tolerance or os_distribution_within_tolerance),
    }


def _scope_summary(session_dir: Path, manifest: dict[str, Any], focus_report: dict[str, Any], session_metadata: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    values = " ".join(_flatten_json_values({"manifest": manifest, "metadata": session_metadata})).lower()
    is_study5 = "study5" in values or "box_breathing" in values or "original_study5" in values
    blocks = manifest.get("blocks") or []
    run_setup = ((session_metadata.get("experiment") or {}).get("run_setup_snapshot") or {}) if isinstance(session_metadata.get("experiment"), dict) else {}
    blocks_per_part = _as_int(run_setup.get("blocks_per_part"), default=None)
    parts_per_participant = _as_int(((session_metadata.get("experiment") or {}).get("parts_per_participant") if isinstance(session_metadata.get("experiment"), dict) else None), default=None)
    expected_blocks = None
    if blocks_per_part is not None and parts_per_participant is not None:
        expected_blocks = blocks_per_part * parts_per_participant
    elif is_study5:
        expected_blocks = 12
    observed_block_count = len(blocks) if blocks else Counter(row.get("event_type", "") for row in events).get("block_start", 0)
    full_study5 = bool(is_study5 and expected_blocks and observed_block_count >= expected_blocks)
    realtime = bool(
        focus_report.get("validation_audio_realtime")
        or focus_report.get("hardware_audio_realtime")
        or str(focus_report.get("protocol11_audio_mode") or "").strip().lower() == "hardware"
    )
    if full_study5 and realtime:
        scope = "full_study5_realtime"
    elif is_study5 and observed_block_count == 1:
        scope = "one_block_study5_real_asio_rehearsal"
    elif is_study5:
        scope = "partial_study5"
    else:
        scope = "non_study5_or_unknown"
    return {
        "scope": scope,
        "is_study5": is_study5,
        "full_study5": full_study5,
        "validation_audio_realtime": realtime,
        "observed_block_count": observed_block_count,
        "expected_study5_block_count": expected_blocks,
    }


def _section_summaries(criteria: list[Criterion]) -> dict[str, dict[str, Any]]:
    sections: dict[str, dict[str, Any]] = {}
    for criterion in criteria:
        section = sections.setdefault(criterion.section, {"count": 0, "passed_count": 0, "required_count": 0, "required_passed_count": 0})
        section["count"] += 1
        if criterion.passed:
            section["passed_count"] += 1
        if criterion.required:
            section["required_count"] += 1
            if criterion.passed:
                section["required_passed_count"] += 1
    for section in sections.values():
        section["passed"] = section["required_count"] == section["required_passed_count"]
    return sections


def audit_readiness(
    artifact_dir: Path,
    *,
    session_dir: Path | None = None,
    output_dir: Path | None = None,
    require_full_study5: bool = False,
    require_realtime: bool = False,
    rt_tolerance_ms: float = 25.0,
    os_click_rt_p95_tolerance_ms: float = 40.0,
    os_click_rt_max_tolerance_ms: float = 125.0,
) -> dict[str, Any]:
    artifact_dir = artifact_dir.resolve()
    focus_report = _read_json(artifact_dir / "focus_validation_report.json")
    launch_report = _read_json(artifact_dir / "packaged_runner_process_launch.json")
    preparation_report = _read_json(artifact_dir / "preparation_report.json")
    if session_dir is None:
        session_dir = _first_existing(
            [
                _resolve_path(focus_report.get("session_dir"), base=artifact_dir),
                _resolve_path(preparation_report.get("session_dir"), base=artifact_dir),
                artifact_dir / "session_one_block",
            ]
        )
    session_dir = (session_dir or Path()).resolve()
    output_dir = (output_dir or (artifact_dir / "protocol11_study5_readiness_audit")).resolve()

    manifest_path = _first_existing(
        [
            _resolve_path(focus_report.get("session_manifest"), base=artifact_dir),
            session_dir / "session_manifest.json",
        ]
    ) or (session_dir / "session_manifest.json")
    manifest = _read_json(manifest_path)
    outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), dict) else {}
    manifest_base = manifest_path.parent if manifest_path.parent != Path() else session_dir
    metadata_path = _first_existing(
        [
            _resolve_path(outputs.get("session_metadata_json"), base=manifest_base),
            session_dir / "session_metadata.json",
        ]
    ) or (session_dir / "session_metadata.json")
    session_metadata = _read_json(metadata_path)
    analysis_dir = _first_existing(
        [
            _resolve_path(outputs.get("analysis_dir"), base=manifest_base),
            session_dir / "analysis",
            session_dir.parent / "Data_Analytics" / session_dir.name,
        ]
    ) or (session_dir / "analysis")

    paths = {
        "focus_validation_report": artifact_dir / "focus_validation_report.json",
        "packaged_runner_process_launch": artifact_dir / "packaged_runner_process_launch.json",
        "preparation_report": artifact_dir / "preparation_report.json",
        "session_manifest": manifest_path,
        "session_metadata": metadata_path,
        "events_csv": _first_existing(
            [
                _resolve_path(outputs.get("verbose_events_csv") or outputs.get("events_csv"), base=manifest_base),
                session_dir / "events.csv",
            ]
        )
        or (session_dir / "events.csv"),
        "events_xdf": _first_existing(
            [
                _resolve_path(outputs.get("verbose_events_xdf") or outputs.get("events_xdf"), base=manifest_base),
                session_dir / "events.xdf",
            ]
        )
        or (session_dir / "events.xdf"),
        "lsl_markers_csv": _first_existing(
            [
                _resolve_path(outputs.get("lsl_markers_csv"), base=manifest_base),
                session_dir / "lsl_markers.csv",
            ]
        )
        or (session_dir / "lsl_markers.csv"),
        "lsl_markers_xdf": _first_existing(
            [
                _resolve_path(outputs.get("lsl_markers_xdf"), base=manifest_base),
                session_dir / "lsl_markers.xdf",
            ]
        )
        or (session_dir / "lsl_markers.xdf"),
        "trigger_dictionary": _first_existing(
            [
                _resolve_path(outputs.get("trigger_dictionary_json"), base=manifest_base),
                session_dir / "trigger_dictionary.json",
            ]
        )
        or (session_dir / "trigger_dictionary.json"),
        "analysis_summary": _first_existing([analysis_dir / "analysis_summary.txt", session_dir / "analysis_summary.txt"])
        or (analysis_dir / "analysis_summary.txt"),
    }
    screenshot_candidates = [artifact_dir / "focus_screenshot.png", artifact_dir / "live_desktop_after_first_cues.png"]
    screenshot_summaries = {path.name: _screenshot_summary(path) for path in screenshot_candidates}

    events = _event_rows(paths["events_csv"])
    markers = _read_csv(paths["lsl_markers_csv"])
    event_counts = dict(Counter(str(row.get("event_type") or "") for row in events))
    marker_counts = dict(Counter(str(row.get("event_type") or "") for row in markers))
    scheduled_expected = _schedule_expected_counts(session_dir, manifest)
    block_paths = _block_manifest_paths(session_dir, manifest)
    block_wavs = _block_wav_paths(session_dir, manifest)
    sample_audit = _validate_manifest_samples(block_paths)
    xdf = {"events_xdf": _xdf_summary(paths["events_xdf"]), "lsl_markers_xdf": _xdf_summary(paths["lsl_markers_xdf"])}
    reconciliation = _event_id_reconciliation(events, markers)
    audio_records = _audio_evidence_records(session_dir)
    audio_wav_paths = [Path(record["wav_path"]) for record in audio_records if _path_is_set(Path(record["wav_path"]))]
    computed_reconciliation_report = _computed_reconciliation_report(
        session_dir=session_dir,
        output_dir=output_dir,
        event_counts=event_counts,
        marker_counts=marker_counts,
        reconciliation=reconciliation,
        xdf=xdf,
        audio_records=audio_records,
    )
    existing_reconciliation_report = _read_json(artifact_dir / "lsl_xdf_audio_reconciliation_report.json")
    reconciliation_report = existing_reconciliation_report if existing_reconciliation_report.get("passed") else computed_reconciliation_report
    response_marker_report = _best_response_marker_report(artifact_dir)
    expected_response_marker_count = event_counts.get("response_marker_start", 0)
    chosen_marker_report = response_marker_report.get("chosen", {}) if response_marker_report.get("exists") else {}
    if (
        not response_marker_report.get("passed")
        or int(chosen_marker_report.get("expected_marker_count") or -1) != expected_response_marker_count
    ):
        response_marker_report = _response_marker_report_from_audio(
            events_csv=paths["events_csv"],
            recordings=audio_wav_paths,
            output_dir=output_dir / "response_marker_audio_evidence_validation",
        )
    block_wav_scans = {path.name: _wav_scan(path) for path in block_wavs}

    analysis_paths = {suffix: _latest_analysis_csv(session_dir, suffix, analysis_dir=analysis_dir) for suffix in EXPECTED_ANALYSIS_SUFFIXES}
    response_rows = _read_csv(analysis_paths["responses"] or Path())
    analysis_ready_rows = _read_csv(analysis_paths["analysis_ready_trials"] or Path())
    timing_qc_rows = _read_csv(analysis_paths["timing_qc"] or Path())
    analysis_rt = _analysis_rt_audit(
        focus_report,
        analysis_ready_rows,
        rt_tolerance_ms,
        os_click_rt_p95_tolerance_ms,
        os_click_rt_max_tolerance_ms,
    )
    scope = _scope_summary(session_dir, manifest, focus_report, session_metadata, events)

    criteria: list[Criterion] = []
    add = criteria.append

    inventory = _file_inventory(paths)
    required_files_ok = all(item["exists"] and item["bytes"] > 0 for item in inventory.values())
    add(Criterion("session_resolution", "required_core_files_exist", required_files_ok, "Core session files exist and are nonempty.", evidence=inventory))
    add(Criterion("session_resolution", "focus_completed_successfully", bool(focus_report.get("completed")) and _as_int(focus_report.get("exit_code"), default=-1) == 0, "Focus validation report completed with exit code 0.", evidence={"completed": focus_report.get("completed"), "exit_code": focus_report.get("exit_code")}))
    add(Criterion("session_resolution", "packaged_launch_report_present", bool(launch_report.get("schema")) and bool(launch_report.get("exe")), "Packaged process launch report exists with executable identity.", evidence={"schema": launch_report.get("schema"), "exe": launch_report.get("exe"), "mouse_backend": launch_report.get("mouse_backend")}))
    add(Criterion("session_resolution", "session_manifest_matches_session_dir", str(manifest.get("session_dir") or session_dir) == str(session_dir) or Path(str(manifest.get("session_dir") or "")).resolve() == session_dir, "Session manifest points at the audited session directory.", evidence={"manifest_session_dir": manifest.get("session_dir"), "audited_session_dir": str(session_dir)}))

    valid_screenshots = {name: summary for name, summary in screenshot_summaries.items() if summary.get("valid") and summary.get("nonblank")}
    add(Criterion("visual_verification", "nonblank_focus_screenshot_present", bool(valid_screenshots), "At least one Focus Mode screenshot is a valid nonblank PNG.", evidence=screenshot_summaries))

    block_geometry = []
    for path in block_wavs:
        scan = block_wav_scans[path.name]
        block_geometry.append(scan)
    block_geometry_ok = bool(block_geometry) and all(item.get("readable") and int(item.get("channels") or 0) == 3 and int(item.get("samplerate") or 0) > 0 and int(item.get("frames") or 0) > 0 for item in block_geometry)
    add(Criterion("stimulus_assembly", "block_wavs_are_readable_3_channel_pcm", block_geometry_ok, "Every manifest block WAV is readable 3-channel PCM.", evidence={"block_wavs": block_wav_scans}))
    add(Criterion("stimulus_assembly", "manifest_sample_columns_recompute", not sample_audit["mismatches"], "Trial sample columns recompute from seconds and sample rate.", evidence=sample_audit))
    add(Criterion("stimulus_assembly", "catch_baseline_audio_tactile_cue_rules_hold", not sample_audit["mismatches"], "Catch, baseline, and audio-tactile cue invariants hold at manifest level.", evidence=sample_audit.get("cue_checks", {})))

    expected_mismatches = {
        key: {"expected": value, "observed": event_counts.get(key, 0)}
        for key, value in scheduled_expected.items()
        if event_counts.get(key, 0) != value
    }
    add(Criterion("timing_event_schedule", "event_counts_match_manifest", not expected_mismatches, "Scheduled event counts match block manifests.", evidence={"expected": scheduled_expected, "observed": event_counts, "mismatches": expected_mismatches}))
    scheduled_quality_failures = [
        {"event_id": row.get("event_id"), "event_type": row.get("event_type"), "timestamp_quality": row.get("timestamp_quality") or row.get("payload", {}).get("timestamp_quality", "")}
        for row in events
        if row.get("event_type") in SCHEDULED_EVENT_TYPES and (row.get("timestamp_quality") or row.get("payload", {}).get("timestamp_quality", "")) != "dac_time_sample_exact"
    ]
    marker_quality_failures = [
        failure
        for failure in scheduled_quality_failures
        if failure["event_type"] not in {"block_start", "block_end", "block_schedule_loaded"}
    ]
    fallback_events = [row for row in events if "fallback" in str(row.get("timestamp_quality") or row.get("payload", {}).get("timestamp_quality", "")).lower()]
    add(Criterion("timing_event_schedule", "sample_anchored_markers_use_dac_time", not marker_quality_failures, "Sample-scheduled markers use dac_time_sample_exact.", evidence={"failures": marker_quality_failures[:20]}))
    add(Criterion("timing_event_schedule", "no_timing_anchor_fallback", not fallback_events, "Normal run contains no fallback timestamp markers.", evidence={"fallback_count": len(fallback_events)}))

    add(Criterion("lsl_xdf_trigger_logging", "events_xdf_loadable_and_complete", xdf["events_xdf"].get("loaded") and xdf["events_xdf"].get("sample_count") == len(events), "events.xdf loads with pyxdf and sample count matches events.csv.", evidence=xdf["events_xdf"]))
    lsl_streams = {stream["name"]: stream for stream in xdf["lsl_markers_xdf"].get("streams", [])}
    lsl_ok = xdf["lsl_markers_xdf"].get("loaded") and lsl_streams.get("PPSMarkersV2", {}).get("sample_count") == len(markers) and lsl_streams.get("PPSTriggerCodes", {}).get("sample_count") == len(markers)
    add(Criterion("lsl_xdf_trigger_logging", "lsl_marker_xdf_dual_streams_complete", bool(lsl_ok), "lsl_markers.xdf has complete PPSMarkersV2 and PPSTriggerCodes streams.", evidence=xdf["lsl_markers_xdf"]))
    reconciliation_ok = not any(reconciliation[key] for key in ("missing_from_lsl_markers_csv", "extra_in_lsl_markers_csv", "event_type_mismatches", "event_code_mismatches", "trigger_key_mismatches"))
    add(Criterion("lsl_xdf_trigger_logging", "events_and_lsl_marker_csvs_match", reconciliation_ok, "events.csv and lsl_markers.csv agree on event IDs, types, codes, and trigger keys.", evidence=reconciliation))
    trigger_dictionary = _read_json(paths["trigger_dictionary"])
    reserved = trigger_dictionary.get("reserved_codes") or {}
    triggers = trigger_dictionary.get("triggers") or []
    add(Criterion("lsl_xdf_trigger_logging", "trigger_dictionary_has_reserved_and_trial_codes", bool(reserved) and any(str((item or {}).get("trigger_key", "")).startswith("trial:") for item in triggers), "Trigger dictionary includes reserved controls and deterministic trial keys.", evidence={"reserved_count": len(reserved), "trigger_count": len(triggers)}))

    expected_audio_recordings = scheduled_expected.get("block_start", 0)
    audio_inventory = [
        {
            "sidecar_path": str(record.get("sidecar_path") or ""),
            "wav_path": str(record.get("wav_path") or ""),
            "sidecar_ok": _audio_record_ok(record),
            "wav_matches_sidecar": _audio_wav_matches_sidecar(record),
            "signal_shape_ok": _audio_signal_shape_ok(record),
            "sidecar": record.get("sidecar") or {},
            "scan": record.get("scan") or {},
        }
        for record in audio_records
    ]
    add(
        Criterion(
            "local_recorder_audio_evidence",
            "audio_evidence_files_cover_played_blocks",
            bool(audio_records) and len(audio_records) >= expected_audio_recordings,
            "There is one local audio-evidence WAV/sidecar set for every played block.",
            evidence={"expected_recordings": expected_audio_recordings, "observed_recordings": len(audio_records), "records": audio_inventory},
        )
    )
    add(Criterion("local_recorder_audio_evidence", "audio_evidence_sidecars_are_komplete_asio_4ch_clean", bool(audio_records) and all(_audio_record_ok(record) for record in audio_records), "Every local audio-evidence sidecar records clean 4-channel ASIO output with tactile on output 3.", evidence={"records": audio_inventory}))
    add(Criterion("local_recorder_audio_evidence", "audio_evidence_wavs_match_sidecars", bool(audio_records) and all(_audio_wav_matches_sidecar(record) for record in audio_records), "Every audio-evidence WAV is readable and agrees with its sidecar sample rate/frame count.", evidence={"records": audio_inventory}))
    add(Criterion("local_recorder_audio_evidence", "runtime_channels_have_expected_signal_shape", bool(audio_records) and all(_audio_signal_shape_ok(record) for record in audio_records), "Every audio-evidence WAV has signal on outputs 1-3; output 4 is silent unless the sidecar declares a tactile mirror on output 4.", evidence={"records": audio_inventory}))
    recon_criteria = reconciliation_report.get("criteria") if isinstance(reconciliation_report.get("criteria"), dict) else {}
    add(Criterion("local_recorder_audio_evidence", "lsl_xdf_audio_reconciliation_passed", bool(reconciliation_report.get("passed")) and all(bool(value) for value in recon_criteria.values()), "LSL/XDF/audio reconciliation passes every criterion.", evidence={"existing_report": artifact_dir / "lsl_xdf_audio_reconciliation_report.json", "computed_report": output_dir / "lsl_xdf_audio_reconciliation_report.json", "criteria": recon_criteria}))

    mouse_count = event_counts.get("mouse_click", 0)
    response_marker_count = event_counts.get("response_marker_start", 0)
    planned = _planned_click_summary(focus_report)
    mouse_event_ids = {str(row.get("event_id") or "").strip() for row in events if row.get("event_type") == "mouse_click" and str(row.get("event_id") or "").strip()}
    analysis_selection = _analysis_selection_audit(
        planned=planned,
        analysis_ready_rows=analysis_ready_rows,
        response_rows=response_rows,
        mouse_event_ids=mouse_event_ids,
        scheduled_tactile_count=scheduled_expected.get("tactile_onset", 0),
    )
    response_markers = [row for row in events if row.get("event_type") == "response_marker_start"]
    linked_marker_ids = [row.get("payload", {}).get("mouse_event_id") for row in response_markers if str(row.get("payload", {}).get("mouse_event_id") or "").strip()]
    add(Criterion("response_marker_path", "mouse_clicks_and_response_markers_pair_one_to_one", mouse_count == response_marker_count and len(linked_marker_ids) == response_marker_count, "Each accepted in-playback click has one linked response_marker_start.", evidence={"mouse_click_count": mouse_count, "response_marker_start_count": response_marker_count, "linked_marker_count": len(linked_marker_ids)}))
    if planned["all_click_count"]:
        add(
            Criterion(
                "response_marker_path",
                "accepted_click_count_matches_emulated_plan",
                bool(analysis_selection["final_hits_cover_standard_pool"])
                and bool(analysis_selection["selected_click_ids_are_unique_and_logged"]),
                "Analysis-selected responses cover the full standard tactile pool and selected click IDs are unique/logged; runtime extra clicks are allowed when excluded.",
                evidence=analysis_selection,
            )
        )
        add(
            Criterion(
                "response_marker_path",
                "extra_logged_clicks_are_excluded_from_analysis_selection",
                bool(analysis_selection["selected_click_ids_are_unique_and_logged"]),
                "Raw mouse clicks can include extra/double clicks, but selected response click IDs must be unique and logged.",
                evidence=analysis_selection,
            )
        )
    qc_deltas = [_as_float(row.get("marker_minus_mouse_ms"), default=math.nan) for row in timing_qc_rows]
    add(Criterion("response_marker_path", "timing_qc_links_all_response_markers", len(timing_qc_rows) == response_marker_count and all(math.isfinite(value) for value in qc_deltas), "timing_qc.csv has one mouse-marker row per response marker.", evidence={"timing_qc_rows": len(timing_qc_rows), "response_marker_count": response_marker_count, "marker_minus_mouse_ms": _ms_stats(qc_deltas)}))
    chosen_marker_report = response_marker_report.get("chosen", {}) if response_marker_report.get("exists") else {}
    residual = chosen_marker_report.get("abs_residual_ms") or {}
    marker_audio_ok = bool(response_marker_report.get("passed")) and int(chosen_marker_report.get("expected_marker_count") or -1) == response_marker_count and float(chosen_marker_report.get("detection_rate") or 0.0) >= 0.95 and float(residual.get("p95_ms") or 0.0) <= 2.0
    add(Criterion("response_marker_path", "audio_evidence_response_marker_loopback_passed", marker_audio_ok, "Local audio-evidence response-marker pulse recovery passes with stable residuals.", evidence=response_marker_report))

    analysis_files = {
        suffix: {
            "path": str(path) if path else "",
            "exists": bool(path and _path_is_file(path)),
            "bytes": _path_size(path) if path and _path_is_file(path) else 0,
        }
        for suffix, path in analysis_paths.items()
    }
    add(Criterion("analysis_outputs", "all_expected_analysis_csvs_exist", all(item["exists"] and item["bytes"] > 0 for item in analysis_files.values()), "Expected analysis CSV family exists.", evidence=analysis_files))
    expected_hit_ok = (
        bool(analysis_selection["rows_match_declared_standard_tactile_count"])
        and bool(analysis_selection["topup_rescues_match_miss_plan"])
        and bool(analysis_selection["final_hits_cover_standard_pool"])
        and bool(analysis_selection["selected_click_ids_are_unique_and_logged"])
    )
    add(Criterion("analysis_outputs", "analysis_ready_matches_expected_hits_and_misses", expected_hit_ok, "analysis_ready_trials rows cover the original tactile pool, preserve logged click IDs, and use top-up rescues for runtime misses.", evidence=analysis_selection))
    add(Criterion("analysis_outputs", "emulated_rt_values_match_plan_tolerance", analysis_rt["within_tolerance"], f"Analysis RTs match emulated click timings within strict {rt_tolerance_ms:.1f} ms, or OS-click p95 within {os_click_rt_p95_tolerance_ms:.1f} ms and max within {os_click_rt_max_tolerance_ms:.1f} ms.", evidence=analysis_rt))

    full_ready = bool(scope["full_study5"] and scope["validation_audio_realtime"])
    add(Criterion("scope_acceptance", "artifact_is_full_study5_when_required", (not require_full_study5) or bool(scope["full_study5"]), "Full Study 5 evidence is required only for final participant-readiness claims.", evidence=scope))
    add(Criterion("scope_acceptance", "artifact_is_realtime_when_required", (not require_realtime) or bool(scope["validation_audio_realtime"]), "Realtime evidence is required only for final participant-readiness claims.", evidence=scope))

    criteria_dicts = [criterion.as_dict() for criterion in criteria]
    sections = _section_summaries(criteria)
    required_count = sum(1 for criterion in criteria if criterion.required)
    required_passed_count = sum(1 for criterion in criteria if criterion.required and criterion.passed)
    report = {
        "schema": SCHEMA,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "artifact_dir": str(artifact_dir),
        "session_dir": str(session_dir),
        "output_dir": str(output_dir),
        "passed": required_count == required_passed_count,
        "full_study5_realtime_ready": full_ready and required_count == required_passed_count,
        "scope": scope["scope"],
        "scope_summary": scope,
        "required_count": required_count,
        "required_passed_count": required_passed_count,
        "criteria": criteria_dicts,
        "sections": sections,
        "event_counts": event_counts,
        "lsl_marker_counts": marker_counts,
        "expected_event_counts": scheduled_expected,
        "xdf": xdf,
        "audio_evidence": {
            "record_count": len(audio_records),
            "records": [
                {
                    "sidecar_path": record.get("sidecar_path"),
                    "wav_path": record.get("wav_path"),
                    "scan": record.get("scan"),
                }
                for record in audio_records
            ],
        },
        "response_marker_loopback_report": response_marker_report,
        "lsl_xdf_audio_reconciliation_report": reconciliation_report,
        "analysis_selection_audit": analysis_selection,
        "analysis_rt_audit": analysis_rt,
    }
    _write_json(output_dir / "protocol11_study5_readiness_audit.json", report)
    _write_markdown(output_dir / "protocol11_study5_readiness_audit.md", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Protocol 11 Study 5 realtime runner-readiness artifacts.")
    parser.add_argument("--artifact-dir", type=Path, required=True, help="Validation run folder containing focus/launch reports and a session folder.")
    parser.add_argument("--session-dir", type=Path, default=None, help="Session folder to audit. Defaults to reports/session_one_block.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Directory for the readiness audit report.")
    parser.add_argument("--require-full-study5", action="store_true", help="Fail if the artifact is not a complete 12-block Study 5 run.")
    parser.add_argument("--require-realtime", action="store_true", help="Fail if the artifact is not marked as realtime validation audio.")
    parser.add_argument("--rt-tolerance-ms", type=float, default=25.0, help="Allowed absolute RT error against the emulated click plan.")
    parser.add_argument(
        "--os-click-rt-p95-tolerance-ms",
        type=float,
        default=40.0,
        help="Allowed p95 absolute RT error for real OS-click backends.",
    )
    parser.add_argument(
        "--os-click-rt-max-tolerance-ms",
        type=float,
        default=125.0,
        help="Allowed max absolute RT error for real OS-click backends when the RT error p95 still satisfies --rt-tolerance-ms.",
    )
    args = parser.parse_args()

    report = audit_readiness(
        args.artifact_dir,
        session_dir=args.session_dir,
        output_dir=args.output_dir,
        require_full_study5=args.require_full_study5,
        require_realtime=args.require_realtime,
        rt_tolerance_ms=args.rt_tolerance_ms,
        os_click_rt_p95_tolerance_ms=args.os_click_rt_p95_tolerance_ms,
        os_click_rt_max_tolerance_ms=args.os_click_rt_max_tolerance_ms,
    )
    report_path = Path(report["output_dir"]) / "protocol11_study5_readiness_audit.json"
    print(f"Wrote Protocol 11 Study 5 readiness audit: {report_path}")
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
