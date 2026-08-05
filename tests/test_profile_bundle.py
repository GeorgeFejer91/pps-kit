from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from peripersonal_space_toolkit.design import default_design
from peripersonal_space_toolkit.profile_bundle import read_profile_bundle, write_profile_bundle


def test_profile_bundle_round_trip_with_audio(tmp_path: Path) -> None:
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"RIFF" + b"\0" * 4 + b"WAVE" + b"\0" * 32)
    bundle = write_profile_bundle(
        default_design(),
        tmp_path / "example.pps-profile",
        profile_id="custom_example",
        display_name="Example",
        assets={"clip": audio},
        parent={"profile_id": "study5_box_breathing_pps", "sha256": "abc"},
    )
    loaded = read_profile_bundle(bundle)
    assert loaded["profile"]["profile_id"] == "custom_example"
    assert loaded["profile"]["assets"][0]["logical_id"] == "clip"
    assert loaded["manifest"]["parent"]["profile_id"] == "study5_box_breathing_pps"


def test_profile_bundle_rejects_hash_corruption(tmp_path: Path) -> None:
    bundle = write_profile_bundle(
        default_design(), tmp_path / "example.pps-profile", profile_id="custom_example", display_name="Example"
    )
    rewritten = tmp_path / "corrupt.pps-profile"
    with zipfile.ZipFile(bundle) as source, zipfile.ZipFile(rewritten, "w") as target:
        for name in source.namelist():
            data = source.read(name)
            if name == "profile.json":
                data += b" "
            target.writestr(name, data)
    with pytest.raises(ValueError, match="hash or size mismatch"):
        read_profile_bundle(rewritten)


def test_profile_bundle_rejects_traversal(tmp_path: Path) -> None:
    bundle = tmp_path / "unsafe.pps-profile"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("../escape.wav", b"unsafe")
        archive.writestr("manifest.json", json.dumps({"schema": "pps-profile-bundle.v1", "files": []}))
        archive.writestr("profile.json", json.dumps({"schema": "pps-study-profile.v1", "design": {}}))
    with pytest.raises(ValueError, match="Unsafe"):
        read_profile_bundle(bundle)


def test_profile_bundle_rejects_missing_and_non_audio_assets(tmp_path: Path) -> None:
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"RIFF" + b"\0" * 4 + b"WAVE" + b"\0" * 32)
    bundle = write_profile_bundle(
        default_design(), tmp_path / "example.pps-profile", profile_id="custom_example", display_name="Example", assets={"clip": audio}
    )
    missing = tmp_path / "missing.pps-profile"
    with zipfile.ZipFile(bundle) as source, zipfile.ZipFile(missing, "w") as target:
        for name in source.namelist():
            if not name.startswith("assets/"):
                target.writestr(name, source.read(name))
    with pytest.raises(ValueError, match="missing"):
        read_profile_bundle(missing)

    substituted = tmp_path / "substituted.pps-profile"
    with zipfile.ZipFile(bundle) as source:
        manifest = json.loads(source.read("manifest.json"))
        profile = json.loads(source.read("profile.json"))
        trajectories = source.read("trajectories/snapshots.json")
        asset_path = next(item["path"] for item in manifest["files"] if item["path"].startswith("assets/"))
    fake = b"this is an executable-shaped binary, not wave audio"
    for record in manifest["files"]:
        if record["path"] == asset_path:
            import hashlib

            record["sha256"] = hashlib.sha256(fake).hexdigest()
            record["bytes"] = len(fake)
    for record in profile["assets"]:
        if record["path"] == asset_path:
            record["sha256"] = hashlib.sha256(fake).hexdigest()
            record["bytes"] = len(fake)
    profile_bytes = (json.dumps(profile, indent=2, sort_keys=True) + "\n").encode()
    profile_inventory = next(item for item in manifest["files"] if item["path"] == "profile.json")
    profile_inventory["sha256"] = hashlib.sha256(profile_bytes).hexdigest()
    profile_inventory["bytes"] = len(profile_bytes)
    with zipfile.ZipFile(substituted, "w") as target:
        target.writestr("manifest.json", json.dumps(manifest))
        target.writestr("profile.json", profile_bytes)
        target.writestr("trajectories/snapshots.json", trajectories)
        target.writestr(asset_path, fake)
    with pytest.raises(ValueError, match="not recognizable audio"):
        read_profile_bundle(substituted)
