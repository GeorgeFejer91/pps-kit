#!/usr/bin/env python
"""Release-readiness checks for the PPS toolkit."""

from __future__ import annotations

import argparse
import csv
import hashlib
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
    "Example-configs",
    "local_data",
    "models",
    "private_not_for_public",
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
FORBIDDEN_SUFFIXES = {".aup3", ".apk", ".xdf", ".zip", ".sofa", ".hrir", ".mp3", ".flac", ".m4a", ".ogg"}
ALLOWED_STANDARD_HRTF = (
    Path("assets")
    / "0. Head-Related Impulse Response (HRIR) model"
    / "FABIAN_HRIR_measured_HATO_0.sofa"
)
ALLOWED_STANDARD_HRTF_MANIFEST = ALLOWED_STANDARD_HRTF.with_suffix(".manifest.json")
ALLOWED_WAV_PREFIXES = {
    Path("assets") / "breathing",
    Path("assets") / "click",
    Path("assets") / "preloads",
    Path("assets") / "tactile",
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        "AGENTS.md",
        "LICENSE",
        "CITATION.cff",
        "pyproject.toml",
        "configs/experiment.example.toml",
        "configs/stimulus_design.example.json",
        "windows/Setup_Windows_App.ps1",
        "windows/Launch_Experiment_Runner.bat",
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
        "For-AI/README.md",
        "For-AI/project_context.md",
        "For-AI/evolving_goals.md",
        "For-AI/agent_update_protocol.md",
        "assets/breathing/spoken_assets_manifest.json",
        "assets/breathing/spoken_asset_variants.json",
        "assets/breathing/british_kokoro/spoken_assets_manifest.json",
        "assets/breathing/original_study5/spoken_assets_manifest.json",
        "assets/click/mouse_click_tone_1200Hz_50ms.wav",
        "assets/tactile/default_tactile_cue.wav",
        "assets/master_blocks/Master_Block_1.csv",
        "assets/master_blocks/Master_Block_2.csv",
        "assets/0. Head-Related Impulse Response (HRIR) model/FABIAN_HRIR_measured_HATO_0.sofa",
        "assets/0. Head-Related Impulse Response (HRIR) model/FABIAN_HRIR_measured_HATO_0.manifest.json",
        "third_party/nlohmann_json.PINNED.json",
        "third_party/nlohmann_json/LICENSE.MIT",
        "third_party/nlohmann_json/single_include/nlohmann/json.hpp",
        "third_party/3dti_AudioToolkit/3dti_ResourceManager/third_party_libraries/cereal/LICENSE",
        "third_party/3dti_AudioToolkit/3dti_ResourceManager/third_party_libraries/cereal/include/cereal/archives/portable_binary.hpp",
        "third_party/3dti_AudioToolkit/3dti_ResourceManager/third_party_libraries/eigen/COPYING.README",
        "third_party/3dti_AudioToolkit/3dti_ResourceManager/third_party_libraries/eigen/Eigen/QR",
        "third_party/3dti_AudioToolkit/3dti_ResourceManager/third_party_libraries/sofacoustics/libsofa/doc/LICENCE.txt",
        "third_party/3dti_AudioToolkit/3dti_ResourceManager/third_party_libraries/sofacoustics/libsofa/src/SOFA.h",
        "third_party/3dti_AudioToolkit/3dti_ResourceManager/third_party_libraries/sofacoustics/libsofa/dependencies/lib/win/x64/netcdf.dll",
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
        if suffix in FORBIDDEN_SUFFIXES and rel != ALLOWED_STANDARD_HRTF:
            problems.append(f"forbidden release artifact: {rel}")
        if suffix == ".wav" and not any(_is_under(rel, prefix) for prefix in ALLOWED_WAV_PREFIXES):
            problems.append(f"unapproved public WAV file: {rel}")
    return problems


def check_standard_hrtf_bundle() -> list[str]:
    problems = []
    hrtf_path = REPO_ROOT / ALLOWED_STANDARD_HRTF
    manifest_path = REPO_ROOT / ALLOWED_STANDARD_HRTF_MANIFEST
    if not hrtf_path.exists():
        problems.append(f"missing bundled standard HRTF: {ALLOWED_STANDARD_HRTF}")
        return problems
    if not manifest_path.exists():
        problems.append(f"missing bundled standard HRTF manifest: {ALLOWED_STANDARD_HRTF_MANIFEST}")
        return problems
    data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if data.get("id") != "fabian_tu_berlin_hato_0":
        problems.append(f"{ALLOWED_STANDARD_HRTF_MANIFEST} has unexpected id")
    if "CC BY" not in data.get("license", ""):
        problems.append(f"{ALLOWED_STANDARD_HRTF_MANIFEST} missing CC BY license note")
    if data.get("experimenter_visible") is not False:
        problems.append(f"{ALLOWED_STANDARD_HRTF_MANIFEST} should mark experimenter_visible=false")
    expected_hash = data.get("sha256")
    actual_hash = sha256_file(hrtf_path)
    if expected_hash != actual_hash:
        problems.append(
            f"{ALLOWED_STANDARD_HRTF_MANIFEST} hash mismatch for {ALLOWED_STANDARD_HRTF}: "
            f"manifest {expected_hash}, actual {actual_hash}"
        )
    return problems


def check_spoken_assets() -> list[str]:
    problems = []
    asset_dir = REPO_ROOT / "assets" / "breathing"
    root_manifest_path = asset_dir / "spoken_assets_manifest.json"
    if root_manifest_path.exists():
        try:
            root_manifest = json.loads(root_manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            root_manifest = {}
            problems.append(f"invalid spoken asset manifest JSON: {root_manifest_path.relative_to(REPO_ROOT)} ({exc})")
        if root_manifest.get("voice") != "bf_emma" or root_manifest.get("lang") != "en-gb":
            problems.append("root spoken assets should be British Kokoro bf_emma/en-gb")
    for filename in SPOKEN_ASSETS:
        path = asset_dir / filename
        if not path.exists():
            problems.append(f"missing spoken asset: {path.relative_to(REPO_ROOT)}")
            continue
        with wave.open(str(path), "rb") as wav:
            rate = wav.getframerate()
            frames = wav.getnframes()
            channels = wav.getnchannels()
        if rate != TARGET_RATE:
            seconds = frames / rate if rate else 0
            problems.append(
                f"{path.relative_to(REPO_ROOT)} is {seconds:.6f}s at {rate} Hz, expected 44100 Hz"
            )
        if frames != TARGET_FRAMES:
            seconds = frames / rate if rate else 0
            problems.append(
                f"{path.relative_to(REPO_ROOT)} is {seconds:.6f}s at {rate} Hz, expected 4.000000s at 44100 Hz"
            )
        if channels < 1:
            problems.append(f"{path.relative_to(REPO_ROOT)} has no audio channels")
    variants_path = asset_dir / "spoken_asset_variants.json"
    if not variants_path.exists():
        problems.append(f"missing spoken asset variants manifest: {variants_path.relative_to(REPO_ROOT)}")
        return problems
    try:
        variants = json.loads(variants_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        problems.append(f"invalid spoken asset variants JSON: {variants_path.relative_to(REPO_ROOT)} ({exc})")
        return problems
    expected_variants = {"british_kokoro", "original_study5"}
    found_variants = set(variants.get("variants", {}))
    if variants.get("active_root_variant") != "british_kokoro":
        problems.append("spoken asset root variant should be british_kokoro")
    if found_variants != expected_variants:
        problems.append(f"spoken asset variants should be {sorted(expected_variants)}, found {sorted(found_variants)}")
    for variant_id in sorted(expected_variants & found_variants):
        variant = variants["variants"][variant_id]
        directory = REPO_ROOT / variant.get("directory", "")
        manifest_path = REPO_ROOT / variant.get("manifest", "")
        if not directory.is_dir():
            problems.append(f"missing spoken asset variant directory: {directory.relative_to(REPO_ROOT)}")
            continue
        if not manifest_path.exists():
            problems.append(f"missing spoken asset variant manifest: {manifest_path.relative_to(REPO_ROOT)}")
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"invalid spoken asset variant manifest: {manifest_path.relative_to(REPO_ROOT)} ({exc})")
            continue
        manifest_text = json.dumps(manifest)
        if "C:\\" in manifest_text:
            problems.append(f"spoken asset variant manifest leaks a local absolute path: {manifest_path.relative_to(REPO_ROOT)}")
        if variant_id == "british_kokoro" and (
            manifest.get("voice") != "bf_emma" or manifest.get("lang") != "en-gb"
        ):
            problems.append("british_kokoro variant should use bf_emma/en-gb")
        if variant_id == "original_study5" and manifest.get("engine") != "original-study5-instruction-assets":
            problems.append("original_study5 variant should be marked as original-study5-instruction-assets")
        for filename in SPOKEN_ASSETS:
            path = directory / filename
            if not path.exists():
                problems.append(f"missing spoken asset variant file: {path.relative_to(REPO_ROOT)}")
                continue
            expected = manifest.get("files", {}).get(filename, {})
            with wave.open(str(path), "rb") as wav:
                rate = wav.getframerate()
                frames = wav.getnframes()
                channels = wav.getnchannels()
            if rate != TARGET_RATE:
                problems.append(f"{path.relative_to(REPO_ROOT)} is at {rate} Hz, expected 44100 Hz")
            if channels < 1:
                problems.append(f"{path.relative_to(REPO_ROOT)} has no audio channels")
            if expected and frames != expected.get("frames"):
                problems.append(f"{path.relative_to(REPO_ROOT)} frame count does not match manifest")
            if expected and expected.get("sha256") and sha256_file(path) != expected["sha256"]:
                problems.append(f"{path.relative_to(REPO_ROOT)} hash does not match manifest")
            if variant_id == "british_kokoro" or filename in {
                "Inhale-2-3-4-hold_FIXED.wav",
                "Exhale-2-3-4-hold_FIXED.wav",
            }:
                if frames != TARGET_FRAMES:
                    seconds = frames / rate if rate else 0
                    problems.append(
                        f"{path.relative_to(REPO_ROOT)} is {seconds:.6f}s at {rate} Hz, expected 4.000000s at 44100 Hz"
                    )
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
    if len(templates) < 15:
        problems.append("expected at least fifteen study template JSON files")
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
    problems.extend(check_standard_hrtf_bundle())
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
