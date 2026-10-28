"""Run complete captured presets through already-built native test owners.

This development harness never generates or schedules in Python. Each case has
one fresh temporary directory. Native preparation and callback execution plus
the independent result-file audit finish before its PCM is released. Retained
receipts are software/file evidence; they do not qualify devices or replication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import wave
import zipfile


def read_json(path: Path, limit: int = 8 * 1024 * 1024):
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(f"JSON exceeds bounded input: {path.name}")
    return json.loads(raw)


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def run_test(executable: Path, name: str, environment: dict[str, str], log: Path) -> None:
    with log.open("wb") as output:
        completed = subprocess.run(
            [str(executable), name, "--ignored", "--nocapture", "--test-threads=1"],
            env=environment, stdout=output, stderr=subprocess.STDOUT, timeout=3600,
            check=False,
        )
    # A stale binary selecting zero tests is not successful evidence.
    with log.open("rb") as handle:
        handle.seek(max(0, log.stat().st_size - 16 * 1024))
        tail = handle.read().decode("utf-8", errors="replace")
    if completed.returncode or not re.search(r"test result: ok\. 1 passed; 0 failed;", tail):
        raise ValueError(f"native owner did not pass exactly one case: {name}")


def retain_text_receipts(work: Path, destination: Path) -> None:
    """Retain bounded exact bytes, without rewriting paths or result hashes."""
    remaining = 128 * 1024 * 1024
    for path in sorted(work.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".json", ".jsonl", ".csv"}:
            continue
        size = path.stat().st_size
        if size > 32 * 1024 * 1024 or size > remaining:
            raise ValueError("compact evidence retention budget exhausted")
        remaining -= size
        target = destination / "receipts" / path.relative_to(work)
        if os.name == "nt":
            # Deep managed checkouts plus exact receipt names can exceed MAX_PATH.
            # Use the Windows file namespace without shortening evidence identities.
            absolute = str(target.resolve())
            slash = chr(92)
            prefix = slash * 2 + "?" + slash
            if not absolute.startswith(prefix):
                absolute = prefix + ("UNC" + absolute[1:] if absolute.startswith(slash * 2) else absolute)
            target = Path(absolute)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def validate_execution(prepared: dict, execution: dict) -> None:
    if (execution.get("passed") is not True
            or execution.get("input_manifest_sha256") != prepared["handoff_sha256"]):
        raise ValueError("execution does not bind the prepared native package")
    expected, actual = prepared["parts"], execution.get("parts", [])
    if len(expected) != len(actual):
        raise ValueError("execution omitted a prepared part")
    for planned, observed in zip(expected, actual):
        if (planned["manifest_sha256"] != observed["package_manifest_sha256"]
                or planned["trial_count"] != observed["trial_count"]
                or planned["block_count"] != observed["block_count"]
                or [b["trial_count"] for b in planned["blocks"]] != observed["per_block_trial_counts"]
                or not all(observed.get(field) is True for field in (
                    "all_block_schedules_compiled", "all_saved_occurrences_preserved",
                    "all_callback_boundaries_matched",
                    "all_trial_response_identities_outcomes_and_rts_matched"))):
            raise ValueError("execution omitted or changed a saved block, trial or response")


def corrupt_embedded_audio(source: Path, destination: Path) -> None:
    """Development negative only: valid ZIP/CRC, one changed WAV, stale inventory."""
    with zipfile.ZipFile(source) as archive, zipfile.ZipFile(destination, "x") as changed:
        entries = archive.infolist()
        if len(entries) > 1024 or sum(e.file_size for e in entries) > 270 * 1024 * 1024:
            raise ValueError("portable negative fixture exceeds bounded input")
        altered = False
        for entry in entries:
            if entry.file_size > 64 * 1024 * 1024:
                raise ValueError("portable fixture member exceeds bounded input")
            with archive.open(entry) as handle:
                content = handle.read(64 * 1024 * 1024 + 1)
            if len(content) != entry.file_size:
                raise ValueError("portable fixture member length changed")
            if not altered and entry.filename.startswith("assets/") and content[:4] in {b"RIFF", b"RF64"}:
                content = content[:-1] + bytes([content[-1] ^ 1])
                altered = True
            changed.writestr(entry, content)
        if not altered:
            raise ValueError("portable fixture has no embedded WAV to corrupt")


def preparation_disk_bound(capture: dict, resources: Path) -> int:
    """Conservative storage admission only; never edits the accepted schedule."""
    with wave.open(str(resources / "assets/tactile/default_tactile_cue.wav"), "rb") as cue:
        rate = cue.getframerate()
    setup = capture["design"].get("study_profile_reference_parameters", {}).get("dashboard_run_setup", {})
    parts = 2 if setup.get("experiment_structure") == "pre_post" else 1
    block_frames = 0
    trial_frames: dict[tuple, int] = {}
    for block in capture["block_csv_preview"].get("blocks", []):
        for row in block["preview_rows"]:
            seconds = float(row["duration_s"])
            iti = row.get("iti_ms") or 0
            if iti == "1000-1500" and row.get("iti_policy") == "paper_randomized_1000_to_1500_ms":
                # Storage bound only; native review chooses and binds the actual
                # toolkit realization. This never selects an interval in Python.
                iti_seconds = 1.5
            else:
                iti_seconds = float(iti) / 1000
            if not all(math.isfinite(v) and v >= 0 for v in (seconds, iti_seconds)):
                raise ValueError("invalid duration in disk admission input")
            frames = math.ceil(seconds * rate)
            block_frames += frames + math.ceil(iti_seconds * rate)
            key = (row["row_label"], row["sequence_variant_key"], row["family"],
                   str(row["soa_ms"]), row.get("baseline_mode", ""))
            trial_frames[key] = max(frames, trial_frames.get(key, 0))
    # Native trial-file caching can be narrower than this identity; use its
    # larger per-block worst case rather than underbudget repeated files.
    trial_frames_upper = sum(trial_frames.values()) * max(1, len(capture["block_csv_preview"].get("blocks", [])))
    # Instructions, source control generation, JSON/CSV and filesystem headers.
    return parts * (block_frames + trial_frames_upper) * 12 + 128 * 1024 * 1024


def run_case(args, case: dict, evidence_directory: Path) -> dict:
    target = evidence_directory / case["template_id"]
    target.mkdir()
    environment = dict(os.environ)
    for name in ("PPS_PRESET_PREFLIGHT_ONLY", "PPS_PRESET_GENERATE_BASELINES", "PPS_PRESET_RESOLVE_ITI_RANGES",
                 "PPS_NATIVE_FULL_MANIFEST", "PPS_NATIVE_EXPECTED_SHA256",
                 "PPS_BROWSER_BINDING", "PPS_BROWSER_CORRUPT_BUNDLE"):
        environment.pop(name, None)
    environment["PPS_PRESET_CAPTURE"] = str(args.captures / case["capture_file"])
    environment["PPS_PRESET_RESOURCE_ROOT"] = str(args.resources)
    if args.preflight_only:
        environment["PPS_PRESET_PREFLIGHT_ONLY"] = "1"
    if args.resolve_iti_ranges:
        environment["PPS_PRESET_RESOLVE_ITI_RANGES"] = "1"
    if args.renderer:
        environment.update(PPS_PRESET_GENERATE_BASELINES="1",
                           PPS_DESIGNER_RENDERER=str(args.renderer),
                           PPS_DESIGNER_RENDERER_SHA256=args.renderer_sha256)
    record = {"template_id": case["template_id"], "template_sha256": case["template_sha256"],
              "capture_sha256": case["capture_sha256"], "status": "failed",
              "execution": {"status": "not_run"}, "physical_timing_qualified": False}
    try:
        reserve = args.minimum_free_mib * 1024 * 1024
        required = 0 if args.preflight_only or not case["configuration_eligible"] else preparation_disk_bound(
            read_json(args.captures / case["capture_file"]), args.resources)
        record["conservative_preparation_bytes"] = required
        if shutil.disk_usage(args.work_root).free < required + reserve:
            raise ValueError("insufficient free disk for complete native case and reserve; no shortened plan attempted")
        with tempfile.TemporaryDirectory(prefix="pps-native-preset-", dir=args.work_root) as temporary:
            work = Path(temporary)
            environment["PPS_PRESET_OUTPUT"] = str(work)
            try:
                test_name = "full_archived_preset_native_host_preparation"
                if args.portable_binding:
                    binding = read_json(args.portable_binding)
                    # Keep the negative ZIP outside the native owner's required
                    # empty work directory. Both files are owned by this case.
                    corrupt = target / "corrupt-embedded-asset.pps-profile"
                    corrupt_embedded_audio(args.captures / binding["bundle_file"], corrupt)
                    environment.update(PPS_BROWSER_BINDING=str(args.portable_binding),
                                       PPS_BROWSER_CORRUPT_BUNDLE=str(corrupt))
                    test_name = "hosted_portable_bundle_preserves_full_native_pipeline"
                run_test(args.designer_test_exe, test_name,
                         environment, target / "designer.log")
                prepared = read_json(work / "native-preparation.json")
                record.update(prepared)
                if prepared["status"] in {"blocked", "reviewed"} or args.prepare_only:
                    return record
                if prepared["status"] != "prepared" or not prepared["all_part_packages_verified"]:
                    raise ValueError("native preparation did not verify the complete package")
                environment.update(PPS_NATIVE_FULL_MANIFEST=prepared["handoff_manifest_path"],
                                   PPS_NATIVE_EXPECTED_SHA256=prepared["handoff_sha256"])
                run_test(args.runner_test_exe, "full_retained_profile_runs_all_saved_blocks_instructions_and_parts",
                         environment, target / "runner.log")
                reports = list(Path(prepared["handoff_manifest_path"]).parent.glob("native_software_*.evidence.json"))
                if len(reports) != 1:
                    raise ValueError("exactly one fresh native execution receipt required")
                execution = read_json(reports[0], 32 * 1024 * 1024)
                validate_execution(prepared, execution)
                if args.portable_binding and (len(execution["parts"]) != 2
                        or any(p["trial_count"] != 204 or p["block_count"] != 6
                               or p["gate_count"] <= 0 or p["stage_count"] <= 6
                               for p in execution["parts"])
                        or not execution.get("group_result_manifest")):
                    raise ValueError("hosted bridge omitted full parts, instructions, gates or durable group receipt")
                # Import only after native execution; this is a development
                # cross-language file oracle, never a shipped runtime fallback.
                import validate_native_results as auditor
                if execution["group_result_manifest"]:
                    independent = auditor.validate_group(
                        Path(execution["group_result_manifest"]),
                        expected_group_sha256=prepared["handoff_sha256"])
                else:
                    if len(execution["parts"]) != 1:
                        raise ValueError("multiple parts require a durable group receipt")
                    part = execution["parts"][0]
                    independent = auditor.validate(Path(part["result_manifest"]),
                                                   expected_package_sha256=part["package_manifest_sha256"])
                expected_rows = sum(part["trial_count"] for part in prepared["parts"])
                if (independent.get("passed") is not True
                        or independent["scoredTrialCount"] != expected_rows
                        or independent["datasetRowCount"] != expected_rows):
                    raise ValueError("independent results omit complete participant rows")
                record["execution"] = {"status": "completed_software", "receipt": execution,
                                       "independent_file_audit": independent}
                record["all_block_schedules_compiled"] = True
                record["status"] = "software_pipeline_passed"
            finally:
                if (work / "native-preparation.json").exists() and record["status"] == "failed":
                    record["preparation_attempt"] = read_json(work / "native-preparation.json")
                retain_text_receipts(work, target)
                record["pcm_retention"] = "owned temporary PCM released after this attempt; exact compact receipts retained"
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        record["status"] = "failed"
        record["error"] = str(error)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--captures", type=Path)
    inputs.add_argument("--portable-binding", type=Path,
                        help="one actual hosted bundle/full-plan binding; reuses native import and full execution")
    parser.add_argument("--resources", type=Path, required=True)
    parser.add_argument("--designer-test-exe", type=Path, required=True)
    parser.add_argument("--runner-test-exe", type=Path)
    parser.add_argument("--output", type=Path, required=True, help="new ignored evidence directory")
    parser.add_argument("--work-root", type=Path, required=True, help="existing directory for owned temporary PCM")
    parser.add_argument("--renderer", type=Path)
    parser.add_argument("--renderer-sha256")
    parser.add_argument("--template-id", action="append", default=[])
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--resolve-iti-ranges", action="store_true", help="explicitly accept disclosed native toolkit ITI realizations for this software audit; no source/legacy parity")
    parser.add_argument("--minimum-free-mib", type=int, default=512)
    args = parser.parse_args()
    if args.portable_binding and (args.preflight_only or args.prepare_only or args.template_id):
        parser.error("portable bridge requires the complete representative participant and results audit")
    if not (args.preflight_only or args.prepare_only) and not args.runner_test_exe:
        parser.error("complete execution requires --runner-test-exe")
    if bool(args.renderer) != bool(args.renderer_sha256):
        parser.error("renderer path and independently expected SHA-256 must be supplied together")
    if args.minimum_free_mib < 512:
        parser.error("retain at least 512 MiB free before starting each case")
    for name in ("captures", "portable_binding", "resources", "designer_test_exe", "runner_test_exe", "work_root", "renderer"):
        value = getattr(args, name)
        if value is not None:
            setattr(args, name, value.resolve(strict=True))
    if args.portable_binding:
        binding = read_json(args.portable_binding)
        if binding.get("schema") != "pps-hosted-native-bridge-binding.v1":
            raise ValueError("unknown portable binding schema")
        args.captures = args.portable_binding.parent
        for field in ("bundle", "capture"):
            name = binding[f"{field}_file"]
            if Path(name).name != name or name in {".", ".."} or ":" in name or "\\" in name:
                raise ValueError("portable binding requires simple local filenames")
            if digest(args.captures / name) != binding[f"{field}_sha256"]:
                raise ValueError("portable binding input digest changed")
        capture = read_json(args.captures / binding["capture_file"])
        blocks = capture["block_csv_preview"]["blocks"]
        if len(blocks) != 6 or sum(len(b["preview_rows"]) for b in blocks) != 204:
            raise ValueError("portable bridge requires all 204 source rows and six source blocks")
        cases = [{"template_id": "hosted_portable_study5", "template_sha256": None,
                  "capture_sha256": binding["capture_sha256"], "capture_file": binding["capture_file"],
                  "configuration_eligible": True}]
        input_hash = digest(args.portable_binding)
    else:
        capture_report = read_json(args.captures / "capture-report.json")
        cases = capture_report["cases"]
        input_hash = digest(args.captures / "capture-report.json")
    ids = [case["template_id"] for case in cases]
    if len(ids) != len(set(ids)) or not all(re.fullmatch(r"[a-zA-Z0-9_]+", name) for name in ids):
        raise ValueError("duplicate or invalid captured template identity")
    if set(args.template_id) - set(ids):
        raise ValueError("requested template absent from captured inventory")
    args.output.mkdir(parents=True, exist_ok=False)
    selected = [case for case in cases if not args.template_id or case["template_id"] in args.template_id]
    report = {"schema": "pps-hosted-native-bridge-audit.v1" if args.portable_binding else "pps-native-preset-pipeline-audit.v1", "cases": [],
              "capture_report_sha256": input_hash,
              "designer_test_exe_sha256": digest(args.designer_test_exe),
              "runner_test_exe_sha256": digest(args.runner_test_exe) if args.runner_test_exe else None,
              "scope": "complete selected captures; software/file evidence only",
              "all_capture_cases_selected": len(selected) == len(cases),
              "physical_timing_qualified": False, "replication_qualified": False}
    for case in selected:
        record = run_case(args, case, args.output)
        report["cases"].append(record)
        (args.output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"{case['template_id']}: {record['status']}", flush=True)
    if any(case["status"] == "failed" for case in report["cases"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
