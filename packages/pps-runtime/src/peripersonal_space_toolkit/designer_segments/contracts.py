"""Language-neutral contracts shared by all Designer backend segments."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


LINEAGE_SCHEMA = "pps-segment-lineage.v1"


@dataclass(frozen=True)
class SegmentDefinition:
    index: int
    key: str
    label: str
    folder_name: str
    manifest_name: str
    upstream_key: str = ""
    actions: tuple[str, ...] = ()


@dataclass(frozen=True)
class SegmentArtifactRef:
    segment_key: str
    manifest_path: Path
    manifest_sha256: str
    schema: str = ""


@dataclass(frozen=True)
class SegmentLineage:
    segment_key: str
    upstream_segment_key: str = ""
    upstream_manifest_path: str = ""
    upstream_manifest_sha256: str = ""
    design_signature: str = ""
    created_at: str = ""
    schema: str = LINEAGE_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "segment_key": self.segment_key,
            "upstream_segment_key": self.upstream_segment_key,
            "upstream_manifest_path": self.upstream_manifest_path,
            "upstream_manifest_sha256": self.upstream_manifest_sha256,
            "design_signature": self.design_signature,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class SegmentStatus:
    segment_key: str
    status: str
    message: str
    artifact: SegmentArtifactRef | None = None
    validation_errors: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SegmentResult:
    segment_key: str
    status: str
    artifact: SegmentArtifactRef | None = None
    payload: dict[str, Any] = field(default_factory=dict)


class SegmentFailure(RuntimeError):
    """Stable segment-domain failure suitable for API and job adapters."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "segment_operation_failed",
        segment_key: str = "",
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = str(code or "segment_operation_failed")
        self.segment_key = str(segment_key or "")
        self.retryable = bool(retryable)
