from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from peripersonal_space_toolkit.session_runner import (
    prepared_session_manifest_current_status,
)


AVAILABLE_MESSAGE = "Prepared local audio package is available."


@dataclass(frozen=True)
class ParticipantPackageFixture:
    manifest_path: Path
    run_setup_path: Path
    source_csv_path: Path
    trial_wav_path: Path
    source_rows: list[dict[str, str]]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _cargo_executable() -> str:
    if cargo := shutil.which("cargo"):
        return cargo
    rustup_cargo = Path.home() / ".cargo" / "bin" / (
        "cargo.exe" if os.name == "nt" else "cargo"
    )
    assert rustup_cargo.is_file(), "cargo was not found on PATH or in the rustup bin directory"
    return str(rustup_cargo)


def _write_participant_package(
    case_dir: Path, participant_id: str
) -> ParticipantPackageFixture:
    setup_dir = case_dir / "run-setup"
    setup_dir.mkdir(parents=True)
    run_setup_path = setup_dir / "run_setup_manifest.json"
    run_setup_path.write_text('{"schema":"test-run-setup.v1"}\n', encoding="utf-8")

    trial_wav_path = setup_dir / "trial.wav"
    trial_wav_path.write_bytes(b"RIFF-differential-source-trial")
    trial_hash = _sha256(trial_wav_path)

    source_csv_path = setup_dir / "source_block.csv"
    source_rows = [
        {
            "block_trial_index": "1",
            "trial_file_path": trial_wav_path.name,
            "source_sha256": trial_hash,
        }
    ]
    _write_csv(
        source_csv_path,
        ["block_trial_index", "trial_file_path", "source_sha256"],
        source_rows,
    )

    session_dir = case_dir / "prepared-session"
    blocks_dir = session_dir / "blocks"
    blocks_dir.mkdir(parents=True)
    block_wav_path = blocks_dir / "block_001.wav"
    block_wav_path.write_bytes(b"RIFF-differential-prepared-block")
    prepared_csv_path = blocks_dir / "block_001.csv"
    _write_csv(prepared_csv_path, ["Source_SHA256"], [{"Source_SHA256": trial_hash}])

    manifest_path = session_dir / "session_manifest.json"
    manifest = {
        "schema": "pps-run-session.v1",
        "participant_id": participant_id,
        "session_id": f"{participant_id}_session",
        "created_at": "2026-08-31T00:00:00+00:00",
        "session_dir": str(session_dir),
        "execution_mode": "participant_block_wavs",
        "source_run_setup_manifest_path": str(run_setup_path),
        "source_run_setup_sha256": _sha256(run_setup_path),
        "blocks": [
            {
                "index": 1,
                "label": "Block 1",
                "manifest_path": "blocks/block_001.csv",
                "wav_path": "blocks/block_001.wav",
                "trial_count": 1,
                "duration_s": 1.0,
                "metadata": {
                    "source_block_csv_path": source_csv_path.name,
                    "source_block_csv_sha256": _sha256(source_csv_path),
                },
            }
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return ParticipantPackageFixture(
        manifest_path=manifest_path,
        run_setup_path=run_setup_path,
        source_csv_path=source_csv_path,
        trial_wav_path=trial_wav_path,
        source_rows=source_rows,
    )


def _write_legacy_package(case_dir: Path) -> Path:
    session_dir = case_dir / "prepared-session"
    blocks_dir = session_dir / "blocks"
    blocks_dir.mkdir(parents=True)
    (blocks_dir / "block_001.wav").write_bytes(b"RIFF-legacy-block")
    _write_csv(blocks_dir / "block_001.csv", ["trial"], [{"trial": "1"}])

    manifest_path = session_dir / "session_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "pps-run-session.v1",
                "participant_id": "P-LEGACY",
                "session_dir": str(session_dir),
                "blocks": [
                    {
                        "index": 1,
                        "label": "Block 1",
                        "manifest_path": "blocks/block_001.csv",
                        "wav_path": "blocks/block_001.wav",
                        "trial_count": 1,
                        "duration_s": 1.0,
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


def test_rust_verifier_matches_python_v1_status_contract(tmp_path: Path) -> None:
    valid = _write_participant_package(tmp_path / "valid", "P-VALID")

    setup_drift = _write_participant_package(tmp_path / "setup-drift", "P-SETUP")
    setup_drift.run_setup_path.write_text(
        '{"schema":"test-run-setup.v1","changed":true}\n',
        encoding="utf-8",
    )

    row_drift = _write_participant_package(tmp_path / "row-drift", "P-ROWS")
    source_rows = list(row_drift.source_rows)
    source_rows.append(
        {
            "block_trial_index": "2",
            "trial_file_path": "trial.wav",
            "source_sha256": _sha256(row_drift.trial_wav_path),
        }
    )
    _write_csv(
        row_drift.source_csv_path,
        ["block_trial_index", "trial_file_path", "source_sha256"],
        source_rows,
    )
    row_manifest = json.loads(row_drift.manifest_path.read_text(encoding="utf-8"))
    row_manifest["blocks"][0]["metadata"]["source_block_csv_sha256"] = _sha256(
        row_drift.source_csv_path
    )
    row_drift.manifest_path.write_text(
        json.dumps(row_manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    legacy_manifest_path = _write_legacy_package(tmp_path / "legacy")
    cases = [
        {
            "id": "valid_participant_block_wavs",
            "manifest_path": str(valid.manifest_path),
            "run_setup_manifest_path": str(valid.run_setup_path),
            "participant_id": "P-VALID",
        },
        {
            "id": "run_setup_hash_drift",
            "manifest_path": str(setup_drift.manifest_path),
            "run_setup_manifest_path": str(setup_drift.run_setup_path),
            "participant_id": "P-SETUP",
        },
        {
            "id": "source_csv_row_count_drift",
            "manifest_path": str(row_drift.manifest_path),
            "run_setup_manifest_path": str(row_drift.run_setup_path),
            "participant_id": "P-ROWS",
        },
        {
            "id": "legacy_non_participant_mode",
            "manifest_path": str(legacy_manifest_path),
        },
    ]

    expected = {
        "valid_participant_block_wavs": (True, AVAILABLE_MESSAGE),
        "run_setup_hash_drift": (
            False,
            "Prepared session is stale because the Segment 6 run setup changed.",
        ),
        "source_csv_row_count_drift": (
            False,
            "Prepared block 1 trial count is stale: 1 prepared vs 2 source rows.",
        ),
        "legacy_non_participant_mode": (True, AVAILABLE_MESSAGE),
    }
    python_results = []
    for case in cases:
        kwargs: dict[str, object] = {}
        if run_setup_path := case.get("run_setup_manifest_path"):
            kwargs["run_setup_manifest_path"] = Path(str(run_setup_path))
        if participant_id := case.get("participant_id"):
            kwargs["participant_id"] = str(participant_id)
        current, message = prepared_session_manifest_current_status(
            Path(str(case["manifest_path"])),
            **kwargs,
        )
        assert (current, message) == expected[str(case["id"])]
        python_results.append(
            {"id": case["id"], "current": current, "message": message}
        )

    repo_root = Path(__file__).resolve().parents[3]
    completed = subprocess.run(
        [
            _cargo_executable(),
            "run",
            "--quiet",
            "--locked",
            "-p",
            "pps-session-package",
            "--example",
            "status_probe",
        ],
        cwd=repo_root,
        input=json.dumps({"cases": cases}),
        text=True,
        capture_output=True,
        timeout=120,
        env={**os.environ, "CARGO_TERM_COLOR": "never"},
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"cases": python_results}
