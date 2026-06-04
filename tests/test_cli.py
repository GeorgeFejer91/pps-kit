from __future__ import annotations

import csv
from pathlib import Path

from peripersonal_space_toolkit import cli


ROOT = Path(__file__).resolve().parents[1]


def test_analyze_sample_writes_summary(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    exit_code = cli.analyze(["--sample", "--output-dir", str(tmp_path)])
    assert exit_code == 0
    output = tmp_path / "sample_facilitation_summary.csv"
    assert output.exists()
    with output.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows
    assert {"condition", "phase", "SOA_ms", "n", "mean_facilitation_ms"}.issubset(rows[0])


def test_generate_dry_run_does_not_require_private_hrir(monkeypatch):
    monkeypatch.chdir(ROOT)
    exit_code = cli.generate(["--dry-run"])
    assert exit_code == 0
