"""Portable, hash-verified PPS custom profile bundles."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .design import StimulusDesign, design_from_dict, design_to_dict


BUNDLE_SCHEMA = "pps-profile-bundle.v1"
PROFILE_SCHEMA = "pps-study-profile.v1"
ALLOWED_AUDIO_SUFFIXES = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_member(name: str) -> PurePosixPath:
    path = PurePosixPath(str(name).replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"Unsafe profile bundle path: {name}")
    return path


def _looks_like_audio(path: str, data: bytes) -> bool:
    suffix = PurePosixPath(path).suffix.lower()
    signatures = {
        ".wav": data.startswith((b"RIFF", b"RF64")) and data[8:12] == b"WAVE",
        ".flac": data.startswith(b"fLaC"),
        ".ogg": data.startswith(b"OggS"),
        ".mp3": data.startswith(b"ID3") or (len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0),
        ".m4a": len(data) > 12 and data[4:8] == b"ftyp",
    }
    return bool(signatures.get(suffix, False))


def write_profile_bundle(
    design: StimulusDesign,
    destination: Path,
    *,
    profile_id: str,
    display_name: str,
    assets: Mapping[str, Path] | None = None,
    parent: Mapping[str, Any] | None = None,
    capability_provenance: str = "desktop_full",
) -> Path:
    destination = Path(destination)
    if destination.suffix != ".pps-profile":
        destination = destination.with_suffix(".pps-profile")
    asset_records: list[dict[str, Any]] = []
    payloads: dict[str, bytes] = {}
    logical_ids: set[str] = set()
    for logical_id, source in sorted((assets or {}).items()):
        logical = str(logical_id).strip()
        if not logical or logical in logical_ids:
            raise ValueError(f"Duplicate or empty profile asset id: {logical!r}")
        logical_ids.add(logical)
        source = Path(source)
        suffix = source.suffix.lower()
        if suffix not in ALLOWED_AUDIO_SUFFIXES or not source.is_file():
            raise ValueError(f"Profile asset must be a supported audio file: {source}")
        data = source.read_bytes()
        digest = _sha256(data)
        member = f"assets/{digest}{suffix}"
        payloads.setdefault(member, data)
        asset_records.append(
            {
                "logical_id": logical,
                "path": member,
                "sha256": digest,
                "bytes": len(data),
                "media_type": mimetypes.guess_type(source.name)[0] or "application/octet-stream",
                "source_name": source.name,
            }
        )
    profile = {
        "schema": PROFILE_SCHEMA,
        "profile_id": str(profile_id),
        "profile_kind": "custom",
        "display_name": str(display_name),
        "design": design_to_dict(design),
        "assets": asset_records,
    }
    profile_bytes = _json_bytes(profile)
    payloads["profile.json"] = profile_bytes
    snapshots = {
        "schema": "pps-trajectory-snapshots.v1",
        "renderer": {"engine": "three.js", "representation": "stored-read-only-snapshot"},
        "design_trajectory": design_to_dict(design).get("trajectory", {}),
        "sources": [
            {"logical_id": item.label, "snapshot": dict(item.trajectory_snapshot or {})}
            for item in [*design.noises, *design.custom_looming_files]
            if item.trajectory_snapshot
        ],
    }
    payloads["trajectories/snapshots.json"] = _json_bytes(snapshots)
    inventory = [
        {"path": name, "sha256": _sha256(data), "bytes": len(data)}
        for name, data in sorted(payloads.items())
    ]
    manifest = {
        "schema": BUNDLE_SCHEMA,
        "profile_id": str(profile_id),
        "profile_kind": "custom",
        "display_name": str(display_name),
        "profile_schema": PROFILE_SCHEMA,
        "profile_revision": 1,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "capability_provenance": capability_provenance,
        "parent": dict(parent or {}),
        "files": inventory,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", _json_bytes(manifest))
        for name, data in payloads.items():
            archive.writestr(name, data)
    temporary.replace(destination)
    return destination


def read_profile_bundle(path: Path) -> dict[str, Any]:
    path = Path(path)
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Profile bundle contains duplicate paths.")
        for name in names:
            _safe_member(name)
        if "manifest.json" not in names or "profile.json" not in names:
            raise ValueError("Profile bundle must contain manifest.json and profile.json.")
        manifest = json.loads(archive.read("manifest.json"))
        profile = json.loads(archive.read("profile.json"))
        if manifest.get("schema") != BUNDLE_SCHEMA or profile.get("schema") != PROFILE_SCHEMA:
            raise ValueError("Unsupported PPS profile bundle schema.")
        inventory = manifest.get("files")
        if not isinstance(inventory, list):
            raise ValueError("Profile bundle file inventory is missing.")
        inventoried: set[str] = set()
        for record in inventory:
            member = str(record.get("path") or "")
            _safe_member(member)
            if member in inventoried:
                raise ValueError(f"Duplicate profile inventory path: {member}")
            inventoried.add(member)
            if member not in names:
                raise ValueError(f"Profile bundle file is missing: {member}")
            data = archive.read(member)
            if _sha256(data) != str(record.get("sha256") or "") or len(data) != int(record.get("bytes") or -1):
                raise ValueError(f"Profile bundle hash or size mismatch: {member}")
        extras = set(names) - {"manifest.json"} - inventoried
        if extras:
            raise ValueError(f"Profile bundle contains uninventoried files: {sorted(extras)[0]}")
        asset_ids: set[str] = set()
        for asset in profile.get("assets") or []:
            logical_id = str(asset.get("logical_id") or "")
            member = str(asset.get("path") or "")
            if not logical_id or logical_id in asset_ids:
                raise ValueError(f"Duplicate or empty profile asset id: {logical_id!r}")
            asset_ids.add(logical_id)
            if member not in inventoried or PurePosixPath(member).suffix.lower() not in ALLOWED_AUDIO_SUFFIXES:
                raise ValueError(f"Invalid profile audio asset: {member}")
            data = archive.read(member)
            if str(asset.get("sha256") or "") != _sha256(data) or int(asset.get("bytes") or -1) != len(data):
                raise ValueError(f"Profile audio asset record does not match its inventory: {member}")
            if not _looks_like_audio(member, data):
                raise ValueError(f"Profile asset is not recognizable audio data: {member}")
        design = design_from_dict(profile.get("design") or {})
        return {"manifest": manifest, "profile": profile, "design": design}


def install_profile_bundle(path: Path, workspace_root: Path) -> dict[str, Any]:
    loaded = read_profile_bundle(path)
    profile = loaded["profile"]
    profile_id = str(profile.get("profile_id") or "").strip()
    if not profile_id or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for character in profile_id):
        raise ValueError("Profile id contains unsupported characters.")
    destination = Path(workspace_root) / profile_id
    if destination.exists():
        raise FileExistsError(f"Profile already exists: {profile_id}")
    with tempfile.TemporaryDirectory(prefix="pps-profile-") as temporary_text:
        temporary = Path(temporary_text)
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                member = _safe_member(name)
                target = temporary.joinpath(*member.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(temporary, destination)
    return {**loaded, "installed_path": destination}
