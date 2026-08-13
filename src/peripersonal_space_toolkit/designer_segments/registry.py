"""Canonical ordered registry and manifest-lineage validation for Designer segments."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .contracts import LINEAGE_SCHEMA, SegmentDefinition, SegmentLineage
from .segment_0 import DEFINITION as SEGMENT_0
from .segment_1 import DEFINITION as SEGMENT_1
from .segment_2 import DEFINITION as SEGMENT_2
from .segment_3 import DEFINITION as SEGMENT_3
from .segment_4 import DEFINITION as SEGMENT_4
from .segment_5 import DEFINITION as SEGMENT_5
from .segment_6 import DEFINITION as SEGMENT_6


_ORDERED = (SEGMENT_0, SEGMENT_1, SEGMENT_2, SEGMENT_3, SEGMENT_4, SEGMENT_5, SEGMENT_6)
_BY_KEY = {item.key: item for item in _ORDERED}

if tuple(item.index for item in _ORDERED) != tuple(range(7)):
    raise RuntimeError("Designer segment registry must contain ordered Segment 0-6 definitions.")
for item in _ORDERED[1:]:
    if item.upstream_key != _ORDERED[item.index - 1].key:
        raise RuntimeError(f"{item.key} must consume {_ORDERED[item.index - 1].key}.")


def ordered_definitions() -> tuple[SegmentDefinition, ...]:
    return _ORDERED


def definition_for(segment: int | str) -> SegmentDefinition:
    if isinstance(segment, int):
        try:
            return _ORDERED[segment]
        except IndexError as exc:
            raise KeyError(segment) from exc
    try:
        return _BY_KEY[str(segment)]
    except KeyError as exc:
        raise KeyError(segment) from exc


def downstream_definitions(segment: int | str) -> tuple[SegmentDefinition, ...]:
    definition = definition_for(segment)
    return tuple(item for item in _ORDERED if item.index > definition.index)


def manifest_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_segment_lineage(
    segment: int | str,
    *,
    upstream_manifest_path: Path | None = None,
    design_signature: str = "",
    created_at: str = "",
) -> dict[str, Any]:
    definition = definition_for(segment)
    upstream = Path(upstream_manifest_path) if upstream_manifest_path is not None else None
    if definition.upstream_key and (upstream is None or not upstream.is_file()):
        raise FileNotFoundError(f"{definition.label} requires the {definition.upstream_key} manifest.")
    lineage = SegmentLineage(
        segment_key=definition.key,
        upstream_segment_key=definition.upstream_key,
        upstream_manifest_path=str(upstream) if upstream is not None else "",
        upstream_manifest_sha256=manifest_sha256(upstream) if upstream is not None else "",
        design_signature=str(design_signature or ""),
        created_at=created_at or datetime.now().isoformat(timespec="seconds"),
    )
    return lineage.to_dict()


def validate_segment_lineage(
    manifest: dict[str, Any],
    segment: int | str,
    *,
    upstream_manifest_path: Path | None = None,
) -> list[str]:
    """Validate v1 lineage when present while continuing to read legacy manifests."""

    definition = definition_for(segment)
    raw = manifest.get("segment_lineage") if isinstance(manifest, dict) else None
    if raw is None:
        return []
    if not isinstance(raw, dict):
        return [f"{definition.label} contains malformed segment lineage."]
    if raw.get("schema") != LINEAGE_SCHEMA:
        return [f"{definition.label} segment lineage schema is not recognized."]
    if str(raw.get("segment_key") or "") != definition.key:
        return [f"{definition.label} segment lineage identifies the wrong segment."]
    if str(raw.get("upstream_segment_key") or "") != definition.upstream_key:
        return [f"{definition.label} segment lineage identifies the wrong upstream segment."]
    if not definition.upstream_key:
        return []
    upstream = Path(upstream_manifest_path) if upstream_manifest_path is not None else None
    if upstream is None or not upstream.is_file():
        return [f"{definition.label} is stale because the {definition.upstream_key} manifest is missing."]
    recorded_hash = str(raw.get("upstream_manifest_sha256") or "").strip()
    if not recorded_hash:
        return [f"{definition.label} segment lineage does not record its upstream manifest hash."]
    if recorded_hash != manifest_sha256(upstream):
        return [f"{definition.label} is stale because the {definition.upstream_key} manifest changed."]
    return []


def segment_keys(definitions: Iterable[SegmentDefinition] | None = None) -> tuple[str, ...]:
    return tuple(item.key for item in definitions or _ORDERED)
