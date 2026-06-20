"""Preloadable published-paradigm templates for the stimulus designer."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .design import StimulusDesign, design_from_dict


DEFAULT_STUDY_TEMPLATE_ID = "study5_box_breathing_pps"


@dataclass
class StudyTemplate:
    template_id: str
    title: str
    citation: str
    source_url: str
    doi: str
    verification_status: str
    notes: str
    reference_parameters: dict[str, Any]
    design: StimulusDesign
    provenance: list[dict[str, str]]


def _parse_citation(citation: str) -> dict[str, str]:
    text = " ".join(citation.strip().split())
    match = re.match(r"(?P<authors>.+?)\s*\((?P<year>\d{4})\)[\.,]?\s*(?P<rest>.*)", text)
    if not match:
        return {"authors": "", "year": "", "title": "", "journal": text}
    rest = match.group("rest").strip()
    title = ""
    journal = ""
    if rest:
        pieces = re.split(r"\.\s+", rest, maxsplit=1)
        if len(pieces) == 2:
            title, journal = pieces[0].strip(), pieces[1].strip()
        else:
            journal = rest.strip()
    return {
        "authors": match.group("authors").strip(" ,."),
        "year": match.group("year"),
        "title": title.strip(" ."),
        "journal": journal.strip(" ."),
    }


def _bibtex_escape(value: str) -> str:
    return (
        str(value)
        .replace("\\", "\\textbackslash{}")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\n", " ")
        .strip()
    )


def _authors_to_bibtex(authors: str) -> str:
    if not authors:
        return ""
    normalized = re.sub(r"\bet al\.?", "and others", authors)
    normalized = re.sub(r",\s*&\s*", " and ", normalized)
    normalized = normalized.replace(" & ", " and ")
    parts: list[str] = []
    for section in re.split(r"\s+and\s+", normalized):
        parts.extend(
            part.strip(" ,")
            for part in re.split(r"(?<=\.),\s+(?=[A-Z][^,]+,)", section.strip())
            if part.strip(" ,")
        )
    return " and ".join(parts)


def study_template_citation_label(template: StudyTemplate) -> str:
    if template.template_id == DEFAULT_STUDY_TEMPLATE_ID:
        return (
            "PPS Toolkit Study 5 white/pink protocol (2026) - "
            f"White and pink looming sources [{template.verification_status}]"
        )
    parsed = _parse_citation(template.citation)
    lead = f"{parsed['authors']} ({parsed['year']})" if parsed["authors"] and parsed["year"] else template.title
    paper_title = parsed["title"] or template.title
    return f"{lead} - {paper_title} [{template.verification_status}]"


def study_template_priority(template_id: str) -> int:
    if template_id == DEFAULT_STUDY_TEMPLATE_ID:
        return 0
    return 100


def study_template_bibtex(template: StudyTemplate) -> str:
    parsed = _parse_citation(template.citation)
    entry_type = "article" if template.doi or parsed["journal"] else "misc"
    title = parsed["title"] or template.title
    fields = [
        ("author", _authors_to_bibtex(parsed["authors"])),
        ("year", parsed["year"]),
        ("title", title),
        ("journal", parsed["journal"]),
        ("doi", template.doi),
        ("url", template.source_url),
        (
            "note",
            f"PPS Toolkit study profile: {template.title}; verification status: "
            f"{template.verification_status}; original citation: {template.citation}",
        ),
    ]
    body = [f"@{entry_type}{{{template.template_id},"]
    for key, value in fields:
        if value:
            body.append(f"  {key} = {{{_bibtex_escape(value)}}},")
    body.append("}")
    return "\n".join(body) + "\n"


def study_template_csl_json(template: StudyTemplate) -> str:
    parsed = _parse_citation(template.citation)
    authors = [
        {"literal": author.strip()}
        for author in re.split(r"\s+and\s+", _authors_to_bibtex(parsed["authors"]))
        if author.strip()
    ]
    item: dict[str, Any] = {
        "id": template.template_id,
        "type": "article-journal" if template.doi or parsed["journal"] else "document",
        "title": parsed["title"] or template.title,
        "author": authors,
        "issued": {"date-parts": [[int(parsed["year"])]]} if parsed["year"].isdigit() else {},
        "container-title": parsed["journal"],
        "DOI": template.doi,
        "URL": template.source_url,
        "note": (
            f"PPS Toolkit study profile: {template.title}; verification status: "
            f"{template.verification_status}; original citation: {template.citation}"
        ),
    }
    return json.dumps({key: value for key, value in item.items() if value}, indent=2) + "\n"


def template_from_dict(data: dict[str, Any]) -> StudyTemplate:
    design = design_from_dict(data["design"])
    design.study_profile_id = data["template_id"]
    design.study_profile_title = data["title"]
    design.study_profile_notes = data.get("notes", "")
    design.study_profile_reference_parameters = dict(data.get("reference_parameters", {}))
    return StudyTemplate(
        template_id=data["template_id"],
        title=data["title"],
        citation=data["citation"],
        source_url=data.get("source_url", ""),
        doi=data.get("doi", ""),
        verification_status=data.get("verification_status", "unverified"),
        notes=data.get("notes", ""),
        reference_parameters=dict(data.get("reference_parameters", {})),
        design=design,
        provenance=list(data.get("provenance", [])),
    )


def load_template(path: Path) -> StudyTemplate:
    return template_from_dict(json.loads(path.read_text(encoding="utf-8")))


def load_templates(template_dir: Path) -> list[StudyTemplate]:
    if not template_dir.exists():
        return []
    templates = [load_template(path) for path in sorted(template_dir.glob("*.json"))]
    return sorted(
        templates,
        key=lambda item: (
            study_template_priority(item.template_id),
            item.verification_status != "verified",
            item.title,
        ),
    )
