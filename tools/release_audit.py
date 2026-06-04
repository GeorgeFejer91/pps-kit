#!/usr/bin/env python
"""Release-readiness checks for the PPS toolkit."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import wave
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
IGNORED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "artifacts",
    "build",
    "dist",
    "local_data",
    "models",
}
TEXT_SUFFIXES = {
    ".bat",
    ".cff",
    ".csv",
    ".ini",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".toml",
    ".txt",
    ".yml",
    ".yaml",
}
FORBIDDEN_PATTERNS = [
    re.compile(r"Proton Drive", re.IGNORECASE),
    re.compile(r"Project2_PeriPersonalSpace", re.IGNORECASE),
    re.compile(r"C:\\Users\\", re.IGNORECASE),
    re.compile(r"George\.Fejer", re.IGNORECASE),
    re.compile(r"REPLACE-ME", re.IGNORECASE),
    re.compile(r"private_not_for_public", re.IGNORECASE),
    re.compile(r"raw_recordings", re.IGNORECASE),
    re.compile(r"decoder_outputs_name_bearing", re.IGNORECASE),
]
FORBIDDEN_SUFFIXES = {".aup3", ".apk", ".xdf", ".sofa", ".hrir", ".mp3", ".flac", ".m4a", ".ogg"}
ALLOWED_WAV_PREFIXES = {
    Path("assets") / "breathing",
    Path("assets") / "click",
}
SPOKEN_ASSETS = [
    "Inhale-2-3-4-hold_FIXED.wav",
    "Exhale-2-3-4-hold_FIXED.wav",
    "General_Instructions.wav",
    "Pre-Block_Instruction.wav",
    "Post-Block_Instruction.wav",
    "InterimMessage.wav",
    "FinishMessage.wav",
]
TARGET_RATE = 44100
TARGET_FRAMES = 176400


def iter_public_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        parts = set(path.relative_to(root).parts)
        if parts & IGNORED_DIRS:
            continue
        yield path


def _is_under(rel_path: Path, parent: Path) -> bool:
    try:
        rel_path.relative_to(parent)
        return True
    except ValueError:
        return False


def check_required_files() -> list[str]:
    required = [
        "README.md",
        "LICENSE",
        "CITATION.cff",
        "pyproject.toml",
        "configs/experiment.example.toml",
        "configs/stimulus_design.example.json",
        "windows/Setup_Windows_App.ps1",
        "windows/Launch_PPS_App.bat",
        "windows/Launch_Stimulus_Designer.bat",
        "windows/Create_Desktop_Shortcut.ps1",
        "docs/hardware_setup.md",
        "docs/replication_workflow.md",
        "docs/privacy_boundary.md",
        "docs/REPLICATION.md",
        "docs/WINDOWS_APP.md",
        "docs/STIMULUS_DESIGNER.md",
        "docs/PARADIGM_LIBRARY.md",
        "docs/PPS_METADATA_REPRODUCIBILITY_AUDIT.md",
        "docs/PRIVACY_RELEASE.md",
        "assets/breathing/spoken_assets_manifest.json",
        "assets/click/mouse_click_tone_1200Hz_50ms.wav",
        "assets/master_blocks/Master_Block_1.csv",
        "assets/master_blocks/Master_Block_2.csv",
        "data/sample/audio_tactile_with_facilitation_preregistered_2p5sd.csv",
    ]
    problems = []
    for rel in required:
        if not (REPO_ROOT / rel).exists():
            problems.append(f"missing required file: {rel}")
    return problems


def check_public_file_inventory() -> list[str]:
    problems = []
    for path in iter_public_files(REPO_ROOT):
        rel = path.relative_to(REPO_ROOT)
        suffix = path.suffix.lower()
        if suffix in FORBIDDEN_SUFFIXES:
            problems.append(f"forbidden release artifact: {rel}")
        if suffix == ".wav" and not any(_is_under(rel, prefix) for prefix in ALLOWED_WAV_PREFIXES):
            problems.append(f"unapproved public WAV file: {rel}")
    return problems


def check_spoken_assets() -> list[str]:
    problems = []
    asset_dir = REPO_ROOT / "assets" / "breathing"
    for filename in SPOKEN_ASSETS:
        path = asset_dir / filename
        if not path.exists():
            problems.append(f"missing spoken asset: {path.relative_to(REPO_ROOT)}")
            continue
        with wave.open(str(path), "rb") as wav:
            rate = wav.getframerate()
            frames = wav.getnframes()
            channels = wav.getnchannels()
        if rate != TARGET_RATE or frames != TARGET_FRAMES:
            seconds = frames / rate if rate else 0
            problems.append(
                f"{path.relative_to(REPO_ROOT)} is {seconds:.6f}s at {rate} Hz, expected 4.000000s at 44100 Hz"
            )
        if channels < 1:
            problems.append(f"{path.relative_to(REPO_ROOT)} has no audio channels")
    return problems


def check_master_blocks() -> list[str]:
    problems = []
    expected_columns = ["Trial_Number", "Trial_Type", "SOA_ms", "Noise_Type", "Respiratory_Phase"]
    for filename in ["Master_Block_1.csv", "Master_Block_2.csv"]:
        path = REPO_ROOT / "assets" / "master_blocks" / filename
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        if rows and list(rows[0].keys()) != expected_columns:
            problems.append(f"{path.relative_to(REPO_ROOT)} columns changed")
        if len(rows) == 0:
            problems.append(f"{path.relative_to(REPO_ROOT)} is empty")
    return problems


def check_study_templates() -> list[str]:
    problems = []
    template_dir = REPO_ROOT / "study_templates"
    templates = sorted(template_dir.glob("*.json"))
    if len(templates) < 5:
        problems.append("expected at least five study template JSON files")
    for path in templates:
        data = json.loads(path.read_text(encoding="utf-8"))
        for key in ["template_id", "title", "citation", "source_url", "verification_status", "design"]:
            if not data.get(key):
                problems.append(f"{path.relative_to(REPO_ROOT)} missing {key}")
        if data.get("verification_status") not in {"verified", "partial", "unverified"}:
            problems.append(f"{path.relative_to(REPO_ROOT)} has unknown verification_status")
        protocol = data.get("design", {}).get("protocol", {})
        if not protocol.get("soa_values_ms"):
            problems.append(f"{path.relative_to(REPO_ROOT)} missing protocol SOA values")
        if not protocol.get("spatial_values_cm"):
            problems.append(f"{path.relative_to(REPO_ROOT)} missing protocol spatial values")
    return problems


def check_forbidden_text() -> list[str]:
    problems = []
    for path in iter_public_files(REPO_ROOT):
        if path == Path(__file__).resolve():
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in FORBIDDEN_PATTERNS:
            match = pattern.search(text)
            if match:
                rel = path.relative_to(REPO_ROOT)
                problems.append(f"forbidden text '{match.group(0)}' in {rel}")
    return problems


def run_audit() -> list[str]:
    problems = []
    problems.extend(check_required_files())
    problems.extend(check_public_file_inventory())
    problems.extend(check_spoken_assets())
    problems.extend(check_master_blocks())
    problems.extend(check_study_templates())
    problems.extend(check_forbidden_text())
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    problems = run_audit()
    if problems:
        print("Release audit failed:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    if not args.quiet:
        print("Release audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
