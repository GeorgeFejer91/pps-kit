"""Preloadable published-paradigm templates for the stimulus designer."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .design import StimulusDesign, design_from_dict


@dataclass
class StudyTemplate:
    template_id: str
    title: str
    citation: str
    source_url: str
    doi: str
    verification_status: str
    notes: str
    design: StimulusDesign
    provenance: list[dict[str, str]]


def template_from_dict(data: dict[str, Any]) -> StudyTemplate:
    return StudyTemplate(
        template_id=data["template_id"],
        title=data["title"],
        citation=data["citation"],
        source_url=data.get("source_url", ""),
        doi=data.get("doi", ""),
        verification_status=data.get("verification_status", "unverified"),
        notes=data.get("notes", ""),
        design=design_from_dict(data["design"]),
        provenance=list(data.get("provenance", [])),
    )


def load_template(path: Path) -> StudyTemplate:
    return template_from_dict(json.loads(path.read_text(encoding="utf-8")))


def load_templates(template_dir: Path) -> list[StudyTemplate]:
    if not template_dir.exists():
        return []
    templates = [load_template(path) for path in sorted(template_dir.glob("*.json"))]
    return sorted(templates, key=lambda item: (item.verification_status != "verified", item.title))
