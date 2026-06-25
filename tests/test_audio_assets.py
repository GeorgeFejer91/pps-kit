from __future__ import annotations

import json
import hashlib
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "assets" / "breathing"
SPOKEN_ASSETS = [
    "Inhale-2-3-4-hold_FIXED.wav",
    "Exhale-2-3-4-hold_FIXED.wav",
    "General_Instructions.wav",
    "Pre-Block_Instruction.wav",
    "Post-Block_Instruction.wav",
    "InterimMessage.wav",
    "FinishMessage.wav",
]
TRIAL_WINDOW_ASSETS = {
    "Inhale-2-3-4-hold_FIXED.wav",
    "Exhale-2-3-4-hold_FIXED.wav",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_spoken_assets_match_manifest_and_are_british_four_second_tts():
    manifest = json.loads((ASSET_DIR / "spoken_assets_manifest.json").read_text(encoding="utf-8"))
    assert manifest["engine"] == "kokoro-onnx"
    assert manifest["voice"] == "bf_emma"
    assert manifest["lang"] == "en-gb"
    assert manifest["accent"] == "British English"

    for filename in SPOKEN_ASSETS:
        path = ASSET_DIR / filename
        expected = manifest["files"][filename]
        with wave.open(str(path), "rb") as wav:
            assert wav.getframerate() == 44100
            assert wav.getnchannels() >= 1
            assert wav.getnframes() == expected["frames"]
            assert round(wav.getnframes() / wav.getframerate(), 6) == expected["seconds"]
            assert wav.getnframes() == 176400
            assert wav.getnframes() / wav.getframerate() == 4.0


def test_spoken_asset_variants_include_british_tts_and_original_study5_audio():
    variants = json.loads((ASSET_DIR / "spoken_asset_variants.json").read_text(encoding="utf-8"))
    assert variants["active_root_variant"] == "british_kokoro"
    assert set(variants["variants"]) == {"british_kokoro", "original_study5"}

    for variant_id, variant in variants["variants"].items():
        manifest_path = ROOT / variant["manifest"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        variant_dir = ROOT / variant["directory"]
        assert variant_dir.is_dir()

        if variant_id == "british_kokoro":
            assert manifest["voice"] == "bf_emma"
            assert manifest["lang"] == "en-gb"
        else:
            assert manifest["engine"] == "original-study5-instruction-assets"
            assert "original Study 5 instruction MP3 files" in manifest["provenance"]
            assert "C:\\" not in json.dumps(manifest)

        for filename in SPOKEN_ASSETS:
            path = variant_dir / filename
            expected = manifest["files"][filename]
            with wave.open(str(path), "rb") as wav:
                assert wav.getframerate() == 44100
                assert wav.getnchannels() >= 1
                assert wav.getnframes() == expected["frames"]
                if variant_id == "british_kokoro" or filename in TRIAL_WINDOW_ASSETS:
                    assert wav.getnframes() == 176400
                    assert wav.getnframes() / wav.getframerate() == 4.0
            assert _sha256(path) == expected["sha256"]
