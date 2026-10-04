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


def _fixture(root: Path, *, sha: str = "a" * 64,
             identity: dict | None = None, nonce: str = "") -> Path:
    identity = identity or {"participantId": "fixture", "sessionId": "S1", "partSessionId": "S1P2",
                            "partNumber": 2, "executionMode": "participant_block_wavs"}
    events_name = f"native_events_{nonce}.jsonl" if nonce else "events.jsonl"
    dataset_name = f"native_trials_{nonce}.csv" if nonce else "trials.csv"
    manifest_name = f"native_events_{nonce}.results.json" if nonce else "events.results.json"
    header = {"schema": "pps.native-event-journal.v1", "packageManifestSha256": sha,
              "completion": "partial", **identity}
    rows = [{"participant_id": identity["participantId"] if nonce else 'fixture, "quoted"\nvalue\u2028label',
             "trial_number": index, "trial_type": kind, "response_given": False, "outcome": "Hit"}
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
    (root / events_name).write_bytes(event_bytes)
    (root / dataset_name).write_bytes(csv_bytes)
    manifest = {"schema": "pps.native-results.v1", "completion": "complete", "timingQualification": "unqualified",
                "audioEvidence": "software-frame-submission", "identity": identity,
                "eventsFile": events_name, "datasetFile": dataset_name,
                "receipt": {"packageManifestSha256": sha, "packageGeneration": 2, "runGeneration": 3,
                            "firstEventSequence": 5, "lastEventSequence": 9, "eventRecordCount": 5,
                            "scoredTrialCount": 3, "datasetRowCount": 2,
                            "eventsSha256": hashlib.sha256(event_bytes).hexdigest(),
                            "datasetSha256": hashlib.sha256(csv_bytes).hexdigest()}}
    path = root / manifest_name
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _group_fixture(root: Path, *, trials_per_part: int = 3) -> Path:
    group_id = "P001_group"
    entries = []
    for number in (1, 2):
        folder = f"part_{number:02}"
        part_dir = root / folder
        part_dir.mkdir()
        session_id = f"P001_group_part_{number:02}"
        package = {"schema": "pps-run-session.v1", "part_split_schema": "pps-runner-part-split.v1",
                   "participant_id": "P001", "session_group_id": group_id, "part_number": number,
                   "part_folder_name": folder, "part_session_id": session_id, "session_id": session_id,
                   "source_run_setup_sha256": "c" * 64,
                   "execution_mode": "participant_block_wavs", "blocks": [{"trial_count": trials_per_part}]}
        package_bytes = json.dumps(package).encode()
        (part_dir / "session_manifest.json").write_bytes(package_bytes)
        identity = {"participantId": "P001", "sessionId": session_id, "partSessionId": session_id,
                    "partNumber": number, "executionMode": "participant_block_wavs"}
        _fixture(part_dir, sha=hashlib.sha256(package_bytes).hexdigest(), identity=identity,
                 nonce=str(number) * 32)
        entries.append({"part_number": number, "part_session_id": session_id,
                        "part_folder_name": folder, "completed": False})
    path = root / "session_group_manifest.json"
    path.write_text(json.dumps({"schema": "pps-run-session-group.v1",
                                "part_split_schema": "pps-runner-part-split.v1",
                                "session_group_id": group_id, "participant_id": "P001",
                                "source_run_setup_sha256": "c" * 64,
                                "parts_per_participant": 2, "parts": entries}), encoding="utf-8")
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


def test_native_group_audit_requires_both_matching_sealed_parts(tmp_path: Path) -> None:
    group_path = _group_fixture(tmp_path)
    result = audit.validate_group(group_path)
    assert result == {"schema": "pps.native-group-result-file-audit.v1", "passed": True,
                      "evidence": "file-contract-only", "timingQualification": "unqualified",
                      "sessionGroupComplete": True, "partCount": 2,
                      "eventRecordCount": 10, "scoredTrialCount": 6, "datasetRowCount": 4}
    second = tmp_path / "part_02" / f"native_events_{'2' * 32}.results.json"
    second.unlink()
    with pytest.raises(ValueError, match="one unambiguous published native result"):
        audit.validate_group(group_path)


def test_native_group_audit_rejects_cross_part_identity_and_modified_package(tmp_path: Path) -> None:
    group_path = _group_fixture(tmp_path)
    second = tmp_path / "part_02" / f"native_events_{'2' * 32}.results.json"
    manifest = json.loads(second.read_text())
    manifest["identity"]["partNumber"] = 1
    second.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="differs from its split package"):
        audit.validate_group(group_path)
    manifest["identity"]["partNumber"] = 2
    second.write_text(json.dumps(manifest), encoding="utf-8")
    first_package = tmp_path / "part_01" / "session_manifest.json"
    first_package.write_text(first_package.read_text() + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="another package"):
        audit.validate_group(group_path)


def test_native_group_audit_rejects_plausible_results_with_wrong_package_trial_count(tmp_path: Path) -> None:
    group_path = _group_fixture(tmp_path, trials_per_part=2)
    with pytest.raises(ValueError, match="trial count differs"):
        audit.validate_group(group_path)


@pytest.mark.skipif(not os.environ.get("PPS_NATIVE_RESULT_FIXTURE_DIR"), reason="native worker fixture is supplied by desktop CI")
def test_actual_native_writer_files_match_the_independent_v1_projection() -> None:
    path = Path(os.environ["PPS_NATIVE_RESULT_FIXTURE_DIR"]) / "events.results.json"
    result = audit.validate(path, expected_package_sha256="a" * 64)
    assert result["passed"] and result["eventRecordCount"] == 5
    assert result["datasetRowCount"] == 2 and result["scoredTrialCount"] == 3


@pytest.mark.skipif(not os.environ.get("PPS_NATIVE_RESULT_FIXTURE_DIR"), reason="native worker fixture is supplied by desktop CI")
def test_actual_native_writer_group_requires_both_sealed_parts() -> None:
    path = Path(os.environ["PPS_NATIVE_RESULT_FIXTURE_DIR"]) / "group" / "session_group_manifest.json"
    result = audit.validate_group(path)
    assert result["sessionGroupComplete"] and result["partCount"] == 2
    assert result["eventRecordCount"] == 10 and result["scoredTrialCount"] == 6
    assert result["datasetRowCount"] == 4 and result["timingQualification"] == "unqualified"
