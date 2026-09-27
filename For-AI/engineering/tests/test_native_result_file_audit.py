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
