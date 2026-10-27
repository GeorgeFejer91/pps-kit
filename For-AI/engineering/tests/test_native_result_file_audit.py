"""The offline native file audit must reject incomplete or substituted evidence."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "validation" / "scripts" / "validate_native_results.py"
spec = importlib.util.spec_from_file_location("native_result_file_audit", SCRIPT)
assert spec and spec.loader
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def _fixture(root: Path) -> Path:
    sha = "a" * 64
    identity = {"participantId": "fixture", "sessionId": "S1", "partSessionId": "S1P2",
                "partNumber": 2, "executionMode": "participant_block_wavs"}
    header = {"schema": "pps.native-event-journal.v1", "packageManifestSha256": sha,
              "completion": "partial", **identity}
    rows = [{"participant_id": 'fixture, "quoted"\nvalue\u2028label', "trial_number": index, "trial_type": kind, "response_given": False, "outcome": "Hit"}
            for index, kind in enumerate(["Catch", "Filler", "Audio-Only"], 1)]
    events = [{"sequence": 5, "eventType": "audio.final-frame-submitted", "payload": {}}]
    events += [{"sequence": index + 6, "eventType": "trial.scored", "payload": row} for index, row in enumerate(rows)]
    events += [{"sequence": 9, "eventType": "native.results.finalization-requested",
                "payload": {"packageGeneration": 2, "runGeneration": 3, "expectedScoredTrials": 3}}]
    event_bytes = ("\n".join(json.dumps(entry, ensure_ascii=False) for entry in [header, *events]) + "\n").encode()
    minimal = [row for row in rows if not audit.oracle._is_data_min_filler_or_debug(row)]
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=audit.oracle.DATA_MIN_FIELDNAMES)
    writer.writeheader()
    writer.writerows(audit.oracle._data_min_row_from_rich(row, trial_number_global=index)
                     for index, row in enumerate(minimal, 1))
    csv_bytes = text.getvalue().encode()
    (root / "events.jsonl").write_bytes(event_bytes)
    (root / "trials.csv").write_bytes(csv_bytes)
    manifest = {"schema": "pps.native-results.v1", "completion": "complete", "timingQualification": "unqualified",
                "audioEvidence": "software-frame-submission", "identity": identity,
                "eventsFile": "events.jsonl", "datasetFile": "trials.csv",
                "receipt": {"packageManifestSha256": sha, "packageGeneration": 2, "runGeneration": 3,
                            "firstEventSequence": 5, "lastEventSequence": 9, "eventRecordCount": 5,
                            "scoredTrialCount": 3, "datasetRowCount": 2,
                            "eventsSha256": hashlib.sha256(event_bytes).hexdigest(),
                            "datasetSha256": hashlib.sha256(csv_bytes).hexdigest()}}
    path = root / "events.results.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_native_file_audit_preserves_the_v1_projection_without_claiming_acquisition(tmp_path: Path) -> None:
    path = _fixture(tmp_path)
    result = audit.validate(path, expected_package_sha256="a" * 64)
    assert result["passed"] and result["datasetRowCount"] == 2 and result["scoredTrialCount"] == 3
    assert result["evidence"] == "file-contract-only" and result["timingQualification"] == "unqualified"
    with pytest.raises(ValueError, match="another package"):
        audit.validate(path, expected_package_sha256="b" * 64)
    (tmp_path / "trials.csv").write_bytes(b"substituted bytes")
    with pytest.raises(ValueError, match="dataset bytes changed"):
        audit.validate(path)


def test_native_file_audit_rejects_partial_paths_counts_and_forged_csv_even_with_fresh_hashes(tmp_path: Path) -> None:
    for change in ["partial", "count", "path", "csv"]:
        path = _fixture(tmp_path)
        manifest = json.loads(path.read_text())
        if change == "partial":
            manifest["completion"] = "partial"
        elif change == "count":
            manifest["receipt"]["datasetRowCount"] += 1
        elif change == "path":
            manifest["datasetFile"] = "../trials.csv"
        else:
            csv_bytes = (tmp_path / "trials.csv").read_bytes().replace(b"Hit", b"Miss")
            (tmp_path / "trials.csv").write_bytes(csv_bytes)
            manifest["receipt"]["datasetSha256"] = hashlib.sha256(csv_bytes).hexdigest()
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with pytest.raises(ValueError):
            audit.validate(path)


@pytest.mark.skipif(not os.environ.get("PPS_NATIVE_RESULT_FIXTURE_DIR"), reason="native worker fixture is supplied by desktop CI")
def test_actual_native_writer_files_match_the_independent_v1_projection() -> None:
    path = Path(os.environ["PPS_NATIVE_RESULT_FIXTURE_DIR"]) / "events.results.json"
    result = audit.validate(path, expected_package_sha256="a" * 64)
    assert result["passed"] and result["eventRecordCount"] == 5
    assert result["datasetRowCount"] == 2 and result["scoredTrialCount"] == 3


def _group_fixture(root: Path) -> Path:
    attempt = "g" * 32
    selected = []
    for number in (1, 2):
        directory = root / f"part_{number:02}"
        directory.mkdir(exist_ok=True)
        package = directory / "session_manifest.json"
        package.write_text(json.dumps({"part_number": number, "part_session_id": f"part{number}",
                                      "participant_id": "fixture", "blocks": [{"trial_count": 3}]}))
        selected.append({"part_number": number, "part_session_id": f"part{number}",
                         "session_manifest_path": str(package)})
    source_path = root / "session_group_manifest.json"
    source_path.write_text(json.dumps({"schema": "pps-run-session-group.v1",
                                      "part_split_schema": "pps-runner-part-split.v1",
                                      "experiment_structure": "pre_post", "parts_per_participant": 2,
                                      "participant_id": "fixture", "parts": selected}))
    source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    parts = []
    for number in (1, 2):
        directory = root / f"part_{number:02}"
        path = _fixture(directory)
        result = json.loads(path.read_text())
        package = directory / "session_manifest.json"
        package_hash = hashlib.sha256(package.read_bytes()).hexdigest()
        result["identity"].update({"partNumber": number, "partSessionId": f"part{number}",
                                   "groupAttemptId": attempt, "selectedGroupManifestSha256": source_hash})
        result["receipt"]["packageManifestSha256"] = package_hash
        events = directory / result["eventsFile"]
        lines = events.read_text(encoding="utf-8").split("\n")
        header = json.loads(lines[0])
        header.update(result["identity"], packageManifestSha256=package_hash)
        lines[0] = json.dumps(header)
        events.write_bytes("\n".join(lines).encode("utf-8"))
        result["receipt"]["eventsSha256"] = hashlib.sha256(events.read_bytes()).hexdigest()
        path.write_text(json.dumps(result), encoding="utf-8")
        def relative(item: Path) -> str:
            return item.relative_to(root).as_posix()
        parts.append({"partNumber": number, "partSessionId": f"part{number}",
                      "packageManifestFile": relative(package), "resultManifestFile": relative(path),
                      "resultManifestSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                      "eventsFile": relative(events), "datasetFile": relative(directory / result["datasetFile"]),
                      "receipt": result["receipt"]})
    path = root / f"native_group_{attempt}.results.json"
    path.write_text(json.dumps({"schema": "pps.native-group-results.v1", "completion": "complete",
                               "timingQualification": "unqualified", "groupAttemptId": attempt,
                               "selectedGroupManifestFile": source_path.name,
                               "selectedGroupManifestSha256": source_hash, "parts": parts}))
    return path


def test_group_audit_joins_both_exact_attempts_and_complete_selected_inventory(tmp_path: Path) -> None:
    path = _group_fixture(tmp_path)
    report = audit.validate_group(path)
    assert report["passed"] and report["partCount"] == 2
    assert report["scoredTrialCount"] == 6 and report["datasetRowCount"] == 4
    assert report["evidence"] == "file-contract-only" and report["timingQualification"] == "unqualified"
    with pytest.raises(ValueError, match="another group"):
        audit.validate_group(path, expected_group_sha256="f" * 64)


@pytest.mark.parametrize("change", ["old_attempt", "duplicate", "partial", "outside", "missing_part", "omitted_trials"])
def test_group_audit_rejects_mixed_attempts_and_incomplete_or_rebound_parts(tmp_path: Path, change: str) -> None:
    path = _group_fixture(tmp_path)
    group = json.loads(path.read_text())
    if change == "old_attempt":
        result_path = tmp_path / group["parts"][1]["resultManifestFile"]
        result = json.loads(result_path.read_text())
        result["identity"]["groupAttemptId"] = "x" * 32
        result_path.write_text(json.dumps(result))
        group["parts"][1]["resultManifestSha256"] = hashlib.sha256(result_path.read_bytes()).hexdigest()
    elif change == "duplicate":
        group["parts"][1] = group["parts"][0]
    elif change == "partial":
        group["completion"] = "partial"
    elif change == "outside":
        group["parts"][1]["resultManifestFile"] = "../other/results.json"
    elif change == "missing_part":
        group["parts"].pop()
    else:
        package = tmp_path / group["parts"][1]["packageManifestFile"]
        content = json.loads(package.read_text())
        content["blocks"][0]["trial_count"] += 1
        package.write_text(json.dumps(content))
    path.write_text(json.dumps(group))
    with pytest.raises(ValueError):
        audit.validate_group(path)
