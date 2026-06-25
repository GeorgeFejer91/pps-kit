#!/usr/bin/env python
"""Generate 4-second British spoken instruction WAV assets with Kokoro ONNX.

The generated files are study seed assets, not participant data. Model files are
downloaded into an ignored local cache by the Windows setup script or manually
from the kokoro-onnx release page.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from urllib.request import urlretrieve

import numpy as np
from scipy.signal import resample

try:
    import soundfile as sf
    from kokoro_onnx import Kokoro
except ImportError as exc:  # pragma: no cover - exercised by setup docs
    raise SystemExit(
        "Missing TTS dependencies. Install them with:\n"
        "  python -m pip install kokoro-onnx soundfile scipy numpy\n"
    ) from exc


REPO_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = REPO_ROOT / "assets" / "breathing"
MODEL_DIR = REPO_ROOT / "models" / "kokoro"
MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx"
VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
TARGET_SAMPLE_RATE = 44100
TARGET_SECONDS = 4.0
TARGET_FRAMES = int(TARGET_SAMPLE_RATE * TARGET_SECONDS)

PROMPTS = {
    "Inhale-2-3-4-hold_FIXED.wav": "Inhale. Two. Three. Four. Hold.",
    "Exhale-2-3-4-hold_FIXED.wav": "Exhale. Two. Three. Four. Hold.",
    "General_Instructions.wav": "Follow the breathing count. Click when you feel the vibration.",
    "Pre-Block_Instruction.wav": "Get ready. The next block will begin after your click.",
    "Post-Block_Instruction.wav": "Block complete. Please rest and wait for the next block.",
    "InterimMessage.wav": "Halfway point. Take a short rest before continuing.",
    "FinishMessage.wav": "Experiment complete. Please wait for the researcher.",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_file(path: Path, url: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {path.name}...")
    urlretrieve(url, path)


def exact_duration_mono(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    samples = samples.astype(np.float32, copy=False)
    if sample_rate != TARGET_SAMPLE_RATE:
        target_len = max(1, round(len(samples) * TARGET_SAMPLE_RATE / sample_rate))
        samples = resample(samples, target_len).astype(np.float32)
    if len(samples) == 0:
        samples = np.zeros(TARGET_FRAMES, dtype=np.float32)
    else:
        samples = resample(samples, TARGET_FRAMES).astype(np.float32)
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    if peak > 0:
        samples = (0.90 * samples / peak).astype(np.float32)
    assert len(samples) == TARGET_FRAMES
    return samples


def generate_assets(
    *,
    output_dir: Path,
    model_path: Path,
    voices_path: Path,
    voice: str,
    speed: float,
    lang: str,
) -> dict[str, object]:
    kokoro = Kokoro(str(model_path), str(voices_path))
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "engine": "kokoro-onnx",
        "model": model_path.name,
        "voices": voices_path.name,
        "voice": voice,
        "speed": speed,
        "lang": lang,
        "accent": "British English" if voice.startswith(("bf_", "bm_")) else "English",
        "provenance": (
            "Synthetic spoken instruction assets generated from repository prompts "
            "with Kokoro ONNX; source audio is not copied from Study 5 MP3 files."
        ),
        "target_sample_rate": TARGET_SAMPLE_RATE,
        "target_seconds": TARGET_SECONDS,
        "files": {},
    }

    for filename, text in PROMPTS.items():
        print(f"Generating {filename}: {text}")
        samples, sample_rate = kokoro.create(text, voice=voice, speed=speed, lang=lang)
        fixed = exact_duration_mono(np.asarray(samples), int(sample_rate))
        output_path = output_dir / filename
        sf.write(output_path, fixed, TARGET_SAMPLE_RATE, subtype="PCM_16")
        info = sf.info(str(output_path))
        manifest["files"][filename] = {
            "text": text,
            "sample_rate": info.samplerate,
            "frames": info.frames,
            "seconds": info.frames / info.samplerate,
            "sha256": sha256(output_path),
        }

    manifest_path = output_dir / "spoken_assets_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ASSET_DIR)
    parser.add_argument("--model-dir", type=Path, default=MODEL_DIR)
    parser.add_argument("--voice", default="bf_emma")
    parser.add_argument("--speed", type=float, default=0.92)
    parser.add_argument("--lang", default="en-gb")
    parser.add_argument("--no-download", action="store_true", help="Require existing model files instead of downloading.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    model_path = args.model_dir / "kokoro-v1.0.int8.onnx"
    voices_path = args.model_dir / "voices-v1.0.bin"
    if not args.no_download:
        ensure_file(model_path, MODEL_URL)
        ensure_file(voices_path, VOICES_URL)
    if not model_path.exists() or not voices_path.exists():
        raise SystemExit(f"Missing Kokoro model files in {args.model_dir}")
    generate_assets(
        output_dir=args.output_dir,
        model_path=model_path,
        voices_path=voices_path,
        voice=args.voice,
        speed=args.speed,
        lang=args.lang,
    )
    print(f"Generated {len(PROMPTS)} exact 4-second WAV clips in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
