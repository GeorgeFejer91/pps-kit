from __future__ import annotations

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


def test_spoken_assets_are_exactly_four_seconds():
    for filename in SPOKEN_ASSETS:
        path = ASSET_DIR / filename
        with wave.open(str(path), "rb") as wav:
            assert wav.getframerate() == 44100
            assert wav.getnframes() == 176400
            assert wav.getnframes() / wav.getframerate() == 4.0
