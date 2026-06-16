from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import re
import shutil
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


PARSER_VERSION = "0.5.5"

COVERAGE_PATH = Path("assets/preloads/audiotactile_literature_coverage.json")
AUDIT_DIR = Path("For-AI/audiotactile-paper-metadata-audit")
ARTIFACT_DIR = Path("artifacts/paper_metadata_audit")
PDF_DIR = ARTIFACT_DIR / "publication_pdfs"
SUPPLEMENT_DIR = ARTIFACT_DIR / "supplements"
EXTRACTED_DIR = ARTIFACT_DIR / "extracted"
ACQUISITION_STATUS_PATH = ARTIFACT_DIR / "acquisition_status.json"
LOCAL_JAVA_ROOT = ARTIFACT_DIR / "tooling" / "jdk"

PDF_STATUSES = (
    "downloaded",
    "open_access_unavailable",
    "paywalled",
    "needs_user_download",
    "not_applicable",
    "bad_pdf",
)
SUPPLEMENT_STATUSES = (
    "downloaded",
    "not_found",
    "needs_user_download",
    "paywalled",
    "not_applicable",
    "not_checked",
)
EXTRACTION_STATUSES = (
    "parsed",
    "parsed_with_warnings",
    "failed",
    "pending_pdf",
)
FIELD_STATUSES = (
    "reported",
    "derived",
    "inferred_low_confidence",
    "not_reported_after_review",
    "not_applicable",
    "source_unavailable",
)
CONFIDENCE_LABELS = (
    "not_applicable",
    "pending_source",
    "source_unavailable",
    "source_acquired_unreviewed",
    "partial_extraction",
    "high_confidence_extraction",
)

ADJACENT_CATEGORY = "adjacent_out_of_scope"

SEGMENT_FIELDS: dict[str, list[dict[str, str]]] = {
    "segment_1_stimulus_reconstruction": [
        {
            "key": "stimulus_type",
            "label": "Stimulus type",
            "description": "Noise, tone, ecological sound, speech, or custom/baked stimulus class.",
        },
        {
            "key": "source_provenance",
            "label": "Source/provenance",
            "description": "Original asset, generated stimulus, licensed set, apparatus source, or supplement file.",
        },
        {
            "key": "trajectory_count",
            "label": "Number of trajectories/tones",
            "description": "Distinct looming/receding/static paths, tones, or auditory conditions.",
        },
        {
            "key": "trajectory_path",
            "label": "Trajectory path",
            "description": "Start/end distance, direction, body anchor, azimuth/elevation, and spatial coordinate frame.",
        },
        {
            "key": "stimulus_duration",
            "label": "Duration",
            "description": "Auditory stimulus duration and any pre/post padding.",
        },
        {
            "key": "stimulus_speed",
            "label": "Speed/path length",
            "description": "Motion speed, path length, propagation timing, or distance-at-time mapping.",
        },
        {
            "key": "auditory_conditions",
            "label": "Auditory conditions",
            "description": "Valence, direction, semantic, movement, or apparatus conditions affecting the auditory stimulus.",
        },
        {
            "key": "gain_envelope",
            "label": "Gain/envelope",
            "description": "SPL, intensity law, gain curve, cross-fade, or amplitude-field information.",
        },
        {
            "key": "renderer_or_apparatus",
            "label": "Renderer/HRTF/speaker apparatus",
            "description": "Headphones, HRTF, Unity/3D Tune-In, physical speakers, arrays, or other rendering provenance.",
        },
    ],
    "segment_2_sequence_and_intermixing": [
        {
            "key": "trial_rows_families",
            "label": "Trial rows/families",
            "description": "Within-trial audio sequence families and task rows.",
        },
        {
            "key": "condition_intermixing",
            "label": "Condition intermixing",
            "description": "Whether systematic manipulations are intermixed with task trials or separated.",
        },
        {
            "key": "blocked_or_random_order",
            "label": "Blocked/random order",
            "description": "Blocked condition structure, random intermixing, and task-critical order constraints.",
        },
        {
            "key": "iti_jitter_policy",
            "label": "ITI/jitter policy",
            "description": "Fixed ITI, jitter values, jitter range, distribution, or hazard-control policy.",
        },
        {
            "key": "response_window",
            "label": "Response window",
            "description": "Allowed response interval, timeout, or scoring window.",
        },
        {
            "key": "task_sequence_rules",
            "label": "Task-critical sequence rules",
            "description": "Special trial scheduling, target/no-target logic, or expectancy controls.",
        },
    ],
    "segment_3_tactile_soa_baseline": [
        {
            "key": "tactile_stimulus",
            "label": "Tactile stimulus",
            "description": "Tactile modality, body site, waveform, duration, frequency, amplitude, and calibration.",
        },
        {
            "key": "soa_table",
            "label": "SOA/distance-at-touch table",
            "description": "SOA values, tactile timing values, or distance-at-tactile values.",
        },
        {
            "key": "baseline_strategy",
            "label": "Baseline strategy",
            "description": "Tactile-only, far/static, fastest-baseline, SOA-matched, direction-coupled, or other baseline type.",
        },
        {
            "key": "baseline_timing",
            "label": "Baseline SOAs/timing",
            "description": "Baseline SOA values, baseline timing relative to omitted sound, or fixed baseline schedule.",
        },
        {
            "key": "catch_trial_type",
            "label": "Catch-trial type",
            "description": "Auditory-only, tactile-only, omitted target, no-go, target-absent, or other catch rule.",
        },
    ],
    "segment_4_counts": [
        {
            "key": "repetitions_per_tactile_soa_condition",
            "label": "Repetitions per tactile SOA/condition",
            "description": "Trial repetitions for each tactile SOA crossed with relevant conditions.",
        },
        {
            "key": "baseline_count",
            "label": "Baseline count",
            "description": "Baseline trial count or percentage.",
        },
        {
            "key": "catch_count",
            "label": "Catch count",
            "description": "Catch/no-go/auditory-only trial count or percentage.",
        },
        {
            "key": "block_count",
            "label": "Block count",
            "description": "Number of blocks, sessions, or phases when task-relevant.",
        },
        {
            "key": "total_trial_count",
            "label": "Total trial count",
            "description": "Total trials per participant, block, condition, or experiment.",
        },
    ],
}

TOTAL_SEGMENT_FIELD_COUNT = sum(len(fields) for fields in SEGMENT_FIELDS.values())

FIELD_KEYWORDS: dict[str, list[str]] = {
    "stimulus_type": ["pink noise", "white noise", "tone", "tones", "sound", "audio stimuli", "auditory stimuli", "click", "speech"],
    "source_provenance": ["samples", "generated", "created", "source", "stimuli were", "audio stimuli", "soundforge", "unity"],
    "trajectory_count": ["types of sound", "directions", "approaching", "receding", "in and out", "front", "rear", "left", "right"],
    "trajectory_path": ["distance", "near", "far", "towards", "away", "approaching", "receding", "moved", "loudspeaker", "cm"],
    "stimulus_duration": ["duration", "presented for", "for 3000 ms", "for 3,000 ms", "ms", "seconds", "sound onset", "sound offset"],
    "stimulus_speed": ["cm/s", "velocity", "linear uniform motion"],
    "auditory_conditions": ["approaching", "receding", "in sound", "out sound", "front", "rear", "left", "right", "condition"],
    "gain_envelope": ["db", "dba", "spl", "intensity", "exponential", "rising", "falling", "sound pressure"],
    "renderer_or_apparatus": ["loudspeaker", "speaker", "headphone", "unity", "arduino", "hrtfs", "hrtf", "virtual", "3d"],
    "trial_rows_families": ["types of trials", "audio-tactile", "unimodal", "catch", "trial", "conditions", "baseline"],
    "condition_intermixing": ["randomly intermingled", "randomized", "random", "intermixed", "blocked", "block"],
    "blocked_or_random_order": ["block", "blocked design", "randomized", "randomly", "pseudo-random", "order"],
    "iti_jitter_policy": ["inter-trial", "inter trial", "iti", "silence", "jitter", "preceded", "followed"],
    "response_window": ["respond", "response", "reaction time", "rt", "timeout", "voice", "microphone", "button"],
    "task_sequence_rules": ["ignore", "catch", "no response", "no-go", "target", "trial", "sequence", "expectancy"],
    "tactile_stimulus": ["tactile stimulus", "vibration", "vibro-tactile", "stimulator", "electrical", "actuator", "duration", "ms"],
    "soa_table": ["temporal delays", "sound onset", "soa", "t1", "t2", "t3", "t4", "t5", "tbefore", "tafter"],
    "baseline_strategy": ["unimodal tactile", "without any sound", "absence of auditory", "baseline", "silence", "tbefore", "tafter"],
    "baseline_timing": ["before sound", "after sound", "before the sound", "after the sound", "tbefore", "tafter", "silence"],
    "catch_trial_type": ["catch", "auditory stimulation only", "without tactile", "no tactile", "not to respond", "false alarm"],
    "repetitions_per_tactile_soa_condition": ["repetitions", "for each", "trials for each", "combination", "target stimuli", "audio-tactile combination"],
    "baseline_count": ["unimodal tactile", "baseline", "without any sound", "trials", "tbefore", "tafter"],
    "catch_count": ["catch", "false alarm", "auditory only", "trials"],
    "block_count": ["blocks", "sessions", "phases", "divided into", "block"],
    "total_trial_count": ["total", "trials", "experiment consisted", "performed a total", "participants performed"],
}

FIELD_CANONICAL_TERMS: dict[str, list[tuple[str, str]]] = {
    "stimulus_type": [
        ("pink noise", "pink noise"),
        ("white noise", "white noise"),
        ("pure tone", "pure tone"),
        ("500 hz tone", "500 Hz tone"),
        ("click", "click"),
        ("speech", "speech"),
    ],
    "source_provenance": [
        ("soundforge", "SoundForge"),
        ("sonic foundry", "Sonic Foundry"),
        ("unity", "Unity"),
        ("samples of pink-noise", "samples of pink noise"),
        ("pink-noise", "pink-noise samples"),
        ("pink noise", "pink-noise samples"),
    ],
    "trajectory_path": [
        ("near loudspeaker", "near loudspeaker"),
        ("far loudspeaker", "far loudspeaker"),
        ("towards", "towards body"),
        ("away", "away from body"),
        ("approaching", "approaching trajectory"),
        ("receding", "receding trajectory"),
    ],
    "stimulus_duration": [
        ("sound onset", "duration relative to sound onset"),
        ("sound offset", "duration relative to sound offset"),
    ],
    "stimulus_speed": [
        ("linear uniform motion", "linear uniform motion"),
    ],
    "auditory_conditions": [
        ("approaching", "approaching"),
        ("receding", "receding"),
        ("in sound", "IN sound"),
        ("out sound", "OUT sound"),
        ("front", "front"),
        ("rear", "rear"),
        ("left", "left"),
        ("right", "right"),
    ],
    "renderer_or_apparatus": [
        ("loudspeaker", "loudspeaker(s)"),
        ("speaker", "speaker(s)"),
        ("headphone", "headphones"),
        ("unity", "Unity"),
        ("arduino", "Arduino"),
        ("hrtf", "HRTF"),
        ("virtual", "virtual audio source"),
    ],
    "condition_intermixing": [
        ("randomly intermingled", "randomly intermingled"),
        ("random combination", "random combination of trials"),
        ("randomized", "randomized"),
        ("pseudo-random", "pseudo-randomized"),
        ("blocked design", "blocked design"),
        ("constant at", "condition held constant within block"),
    ],
    "blocked_or_random_order": [
        ("blocked design", "blocked design"),
        ("randomly", "randomized/random order"),
        ("pseudo-random", "pseudo-randomized"),
    ],
    "iti_jitter_policy": [
        ("inter-trial-interval was not fixed", "ITI not fixed"),
        ("inter-trial interval was not fixed", "ITI not fixed"),
        ("preceded and followed", "pre/post trial silence"),
        ("silence", "silence interval"),
        ("jitter", "jittered interval"),
    ],
    "response_window": [
        ("respond vocally", "vocal response"),
        ("microphone", "microphone response capture"),
        ("voice-activated", "voice-key response capture"),
        ("button", "button response"),
        ("as quickly as possible", "speeded response"),
    ],
    "task_sequence_rules": [
        ("ignore the auditory", "ignore auditory stimulus"),
        ("ignore the sound", "ignore sound"),
        ("not to respond", "withhold response on catch trials"),
        ("catch", "catch/no-target trials"),
        ("target", "tactile target trials"),
    ],
    "tactile_stimulus": [
        ("electrical", "electrical tactile stimulation"),
        ("vibration", "vibrotactile stimulation"),
        ("vibro-tactile", "vibrotactile stimulation"),
        ("actuator", "tactile actuator"),
        ("stimulator", "tactile stimulator"),
    ],
    "catch_trial_type": [
        ("auditory stimulation only", "auditory-only catch trials"),
        ("only auditory", "auditory-only catch trials"),
        ("without tactile", "no-tactile catch trials"),
        ("not to respond", "withhold response on catch trials"),
    ],
    "baseline_strategy": [
        ("unimodal tactile", "unimodal tactile baseline"),
        ("without any sound", "tactile-only/no-sound baseline"),
        ("absence of auditory", "tactile-only/no-sound baseline"),
        ("silence", "silence baseline window"),
    ],
    "baseline_timing": [
        ("before the sound", "pre-sound tactile baseline"),
        ("after the sound", "post-sound tactile baseline"),
        ("before sound onset", "pre-sound tactile baseline"),
        ("after sound offset", "post-sound tactile baseline"),
    ],
    "trial_rows_families": [
        ("audio-tactile", "audio-tactile trials"),
        ("unimodal tactile", "unimodal tactile trials"),
        ("catch", "catch trials"),
        ("baseline", "baseline trials"),
    ],
}

NUMERIC_PATTERN = re.compile(
    r"\b\d+(?:[.,]\d+)?(?:\s*[-\u2010-\u2015]\s*\d+(?:[.,]\d+)?)?\s*"
    r"(?:ms|msec|s|sec|cm/s|cm|m|dB|dBA|SPL|Hz|kHz|mA|%|trials?|blocks?|sessions?)\b",
    re.IGNORECASE,
)

FIELD_NUMERIC_ALLOW: dict[str, tuple[str, ...]] = {
    "stimulus_type": ("hz", "khz"),
    "trajectory_path": ("cm", " m"),
    "stimulus_duration": ("ms", "msec", " sec", " s"),
    "stimulus_speed": ("cm/s", "m/s"),
    "gain_envelope": ("db", "dba", "spl"),
    "iti_jitter_policy": ("ms", "msec", " sec", " s"),
    "tactile_stimulus": ("ms", "msec", "hz", "ma", "%"),
    "soa_table": ("ms", "msec"),
    "baseline_timing": ("ms", "msec", " sec", " s"),
    "catch_trial_type": ("%", "trial"),
    "repetitions_per_tactile_soa_condition": ("trial", "%"),
    "baseline_count": ("trial", "%"),
    "catch_count": ("trial", "%"),
    "block_count": ("block", "session"),
    "total_trial_count": ("trial", "block", "session"),
}

SEMANTIC_REVIEW_STRATEGIES: tuple[dict[str, Any], ...] = (
    {
        "strategy": "stimulus_reconstruction",
        "purpose": "Find auditory stimulus type, source provenance, trajectory/path, speed, gain/envelope, and renderer/speaker details.",
        "keywords": (
            "pink noise", "tone", "sound", "audio stimuli", "auditory stimuli", "loudspeaker",
            "speaker", "headphone", "approaching", "receding", "near", "far", "distance",
            "cm/s", "dba", "db", "spl", "unity", "hrtf", "soundforge",
        ),
    },
    {
        "strategy": "timing_soa",
        "purpose": "Find sound duration, tactile SOAs, temporal delays, silence windows, ITI, and jitter policies.",
        "keywords": (
            "temporal delay", "delays", "soa", "sound onset", "sound offset", "t1", "t2",
            "t3", "t4", "t5", "tbefore", "tafter", "silence", "inter-trial",
            "inter trial", "jitter", "duration",
        ),
    },
    {
        "strategy": "trial_structure_intermixing",
        "purpose": "Find trial families, condition intermixing, randomization, blocking, and task-critical sequence rules.",
        "keywords": (
            "trial", "trials", "audio-tactile", "unimodal", "condition", "conditions",
            "random", "randomized", "randomly", "intermingled", "intermixed", "block",
            "blocked", "sequence", "order",
        ),
    },
    {
        "strategy": "baseline_catch_counts",
        "purpose": "Find baseline strategy, catch/no-target trials, repetition counts, block counts, and total trial counts.",
        "keywords": (
            "baseline", "catch", "without any sound", "absence of auditory", "auditory only",
            "unimodal tactile", "false alarm", "no tactile", "not to respond", "total",
            "repetitions", "for each", "blocks",
        ),
    },
    {
        "strategy": "tactile_response_apparatus",
        "purpose": "Find tactile stimulus modality/device/site, response capture, response window, and calibration details.",
        "keywords": (
            "tactile stimulus", "vibro-tactile", "vibration", "actuator", "stimulator",
            "electrical", "electrodes", "arduino", "respond", "response", "reaction time",
            "microphone", "voice", "button", "threshold", "calibration",
        ),
    },
)

@dataclass(frozen=True)
class AuditPaths:
    repo_root: Path
    coverage_path: Path
    audit_dir: Path
    artifact_dir: Path
    pdf_dir: Path
    supplement_dir: Path
    extracted_dir: Path


def ascii_safe(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "; ".join(ascii_safe(item) for item in value)
    return str(value).encode("ascii", "backslashreplace").decode("ascii")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def resolve_paths(
    repo_root: Path,
    coverage_path: Path = COVERAGE_PATH,
    audit_dir: Path = AUDIT_DIR,
    artifact_dir: Path = ARTIFACT_DIR,
) -> AuditPaths:
    repo_root = repo_root.resolve()
    return AuditPaths(
        repo_root=repo_root,
        coverage_path=(repo_root / coverage_path),
        audit_dir=(repo_root / audit_dir),
        artifact_dir=(repo_root / artifact_dir),
        pdf_dir=(repo_root / artifact_dir / "publication_pdfs"),
        supplement_dir=(repo_root / artifact_dir / "supplements"),
        extracted_dir=(repo_root / artifact_dir / "extracted"),
    )


def ensure_directories(paths: AuditPaths) -> None:
    for folder in (
        paths.audit_dir,
        paths.audit_dir / "paper_audits",
        paths.pdf_dir,
        paths.supplement_dir,
        paths.extracted_dir,
    ):
        folder.mkdir(parents=True, exist_ok=True)


def local_java_executable(repo_root: Path) -> Path | None:
    java_root = repo_root / LOCAL_JAVA_ROOT
    if not java_root.exists():
        return None
    candidates = sorted(java_root.rglob("bin/java.exe")) + sorted(java_root.rglob("bin/java"))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def ensure_java_on_path(repo_root: Path) -> Path | None:
    existing = shutil.which("java")
    if existing:
        return Path(existing)
    local_java = local_java_executable(repo_root)
    if local_java is None:
        return None
    java_bin = str(local_java.parent)
    path_parts = os.environ.get("PATH", "").split(os.pathsep)
    if java_bin not in path_parts:
        os.environ["PATH"] = java_bin + os.pathsep + os.environ.get("PATH", "")
    os.environ.setdefault("JAVA_HOME", str(local_java.parent.parent))
    return local_java


def detect_environment(repo_root: Path | None = None) -> dict[str, Any]:
    repo_root = (repo_root or Path(".")).resolve()
    path_java = shutil.which("java")
    local_java = local_java_executable(repo_root)
    java_available = path_java is not None or local_java is not None
    opendataloader_installed = importlib.util.find_spec("opendataloader_pdf") is not None
    pdfplumber_installed = importlib.util.find_spec("pdfplumber") is not None
    pypdf_installed = importlib.util.find_spec("pypdf") is not None
    pdftoppm_available = shutil.which("pdftoppm") is not None
    pdfinfo_available = shutil.which("pdfinfo") is not None
    return {
        "schema": "pps-paper-metadata-environment.v1",
        "parser_version": PARSER_VERSION,
        "checked_on": date.today().isoformat(),
        "java_available": java_available,
        "java_source": "PATH" if path_java else ("local_artifact_jdk" if local_java else ""),
        "opendataloader_pdf_installed": opendataloader_installed,
        "opendataloader_ready": java_available and opendataloader_installed,
        "fallback_extractors": {
            "pdfplumber_installed": pdfplumber_installed,
            "pypdf_installed": pypdf_installed,
            "pdftoppm_available": pdftoppm_available,
            "pdfinfo_available": pdfinfo_available,
        },
        "notes": [
            "OpenDataLoader PDF is the primary extraction route when Java and opendataloader_pdf are available.",
            "Fallback extractor output is written only under ignored artifacts/paper_metadata_audit/extracted.",
            "No executable paths are stored here to avoid local absolute paths in tracked project memory.",
        ],
    }


def is_valid_pdf(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    with path.open("rb") as handle:
        prefix = handle.read(1024)
    return b"%PDF-" in prefix[:128]


def find_pdf(record_id: str, pdf_dir: Path) -> tuple[Path | None, str]:
    candidates = sorted(pdf_dir.glob(f"{record_id}*.pdf"))
    if not candidates:
        return None, "needs_user_download"
    valid = [candidate for candidate in candidates if is_valid_pdf(candidate)]
    if valid:
        return valid[0], "downloaded"
    return candidates[0], "bad_pdf"


def load_acquisition_status(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    payload = load_json(path)
    records = payload.get("records", [])
    return {
        str(record.get("record_id")): record
        for record in records
        if record.get("record_id")
    }


def find_supplements(record_id: str, supplement_dir: Path) -> tuple[list[Path], str]:
    folder = supplement_dir / record_id
    if not folder.exists():
        return [], "not_checked"
    files = sorted(path for path in folder.rglob("*") if path.is_file())
    if files:
        return files, "downloaded"
    return [], "not_checked"


def artifact_rel(path: Path, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.name


def doi_url(doi: str) -> str:
    return f"https://doi.org/{doi}" if doi else ""


def initial_field_audit(status: str) -> dict[str, Any]:
    return {
        "status": status,
        "value": "",
        "source_file": "",
        "page_or_section": "",
        "evidence_note": "",
    }


def make_field_template(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    status = "not_applicable" if record["coverage_category"] == ADJACENT_CATEGORY else "source_unavailable"
    return {
        segment: {field["key"]: initial_field_audit(status) for field in fields}
        for segment, fields in SEGMENT_FIELDS.items()
    }


def clean_evidence_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def collect_content_nodes(value: Any) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    if isinstance(value, dict):
        content = value.get("content")
        if isinstance(content, str) and clean_evidence_text(content):
            nodes.append(
                {
                    "type": str(value.get("type", "")),
                    "page": str(value.get("page number", "")),
                    "content": clean_evidence_text(content),
                }
            )
        for child in value.get("kids", []) if isinstance(value.get("kids"), list) else []:
            nodes.extend(collect_content_nodes(child))
    elif isinstance(value, list):
        for child in value:
            nodes.extend(collect_content_nodes(child))
    return nodes


def safe_extracted_name(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", path.stem).strip("._") or "supplement"


def iter_xml_text(xml_bytes: bytes) -> str:
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError:
        return ""
    parts: list[str] = []
    for element in root.iter():
        if element.text and element.text.strip():
            parts.append(element.text.strip())
        if element.tail and element.tail.strip():
            parts.append(element.tail.strip())
    return "\n".join(parts)


def extract_docx_text(path: Path) -> str:
    texts: list[str] = []
    xml_names = ("word/document.xml", "word/footnotes.xml", "word/endnotes.xml", "word/comments.xml")
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        for name in xml_names:
            if name in names:
                text = iter_xml_text(archive.read(name))
                if text:
                    texts.append(text)
    return "\n\n".join(texts)


def extract_ods_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        if "content.xml" not in archive.namelist():
            return ""
        return iter_xml_text(archive.read("content.xml"))


def extract_pdf_text(path: Path) -> str:
    if importlib.util.find_spec("pdfplumber") is not None:
        import pdfplumber  # type: ignore

        chunks: list[str] = []
        with pdfplumber.open(str(path)) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                page_text = page.extract_text() or ""
                chunks.append(f"\n\n[page {index}]\n{page_text}")
        if any(chunk.strip() for chunk in chunks):
            return "".join(chunks)
    if importlib.util.find_spec("pypdf") is not None:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        return "".join(
            f"\n\n[page {index}]\n{page.extract_text() or ''}"
            for index, page in enumerate(reader.pages, start=1)
        )
    return ""


def extract_legacy_doc_text(path: Path) -> str:
    data = path.read_bytes()
    snippets: list[str] = []
    for match in re.finditer(rb"(?:[\x20-\x7e]\x00){5,}", data):
        text = match.group(0).decode("utf-16le", errors="ignore").strip()
        if text:
            snippets.append(text)
    for match in re.finditer(rb"[\x20-\x7e]{8,}", data):
        text = match.group(0).decode("latin-1", errors="ignore").strip()
        if text:
            snippets.append(text)
    return "\n".join(dedupe_preserve_order(snippets))


def extract_supplement_text(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()
    try:
        if suffix == ".docx":
            text = extract_docx_text(path)
        elif suffix == ".ods":
            text = extract_ods_text(path)
        elif suffix == ".pdf":
            text = extract_pdf_text(path)
        elif suffix == ".doc":
            text = extract_legacy_doc_text(path)
        elif suffix in {".csv", ".tsv"}:
            text = path.read_text(encoding="utf-8", errors="replace")
        else:
            return "", "unsupported"
    except Exception as exc:
        return "", f"failed:{exc.__class__.__name__}"
    cleaned = clean_evidence_text(text)
    if not cleaned:
        return "", "empty"
    return cleaned, "parsed"


def extract_downloaded_supplements(records: list[dict[str, Any]], paths: AuditPaths) -> dict[str, dict[str, Any]]:
    log: dict[str, dict[str, Any]] = {}
    output_root = paths.extracted_dir / "supplements"
    for record in records:
        record_id = record["record_id"]
        if record.get("coverage_category") == ADJACENT_CATEGORY:
            continue
        supplement_files, supplement_status = find_supplements(record_id, paths.supplement_dir)
        if supplement_status != "downloaded":
            continue
        out_dir = output_root / record_id
        out_dir.mkdir(parents=True, exist_ok=True)
        parsed_files: list[str] = []
        statuses: list[str] = []
        for supplement in supplement_files:
            text, status = extract_supplement_text(supplement)
            statuses.append(status)
            if status != "parsed":
                continue
            out_path = out_dir / f"{safe_extracted_name(supplement)}.txt"
            out_path.write_text(text + "\n", encoding="utf-8")
            parsed_files.append(artifact_rel(out_path, paths.repo_root))
        if parsed_files or statuses:
            log[record_id] = {
                "parsed_files": parsed_files,
                "status_counts": {
                    status: statuses.count(status)
                    for status in sorted(set(statuses))
                },
            }
    return log


def load_opendataloader_nodes(record_id: str, paths: AuditPaths) -> tuple[list[dict[str, Any]], str]:
    json_path = paths.extracted_dir / "opendataloader" / f"{record_id}.json"
    if not json_path.exists():
        return [], ""
    try:
        payload = load_json(json_path)
    except json.JSONDecodeError:
        return [], artifact_rel(json_path, paths.repo_root)

    nodes = collect_content_nodes(payload.get("kids", []))
    filtered: list[dict[str, Any]] = []
    current_section = ""
    references_started = False
    for node in nodes:
        content = node["content"]
        lower = content.lower()
        if lower.strip() in {"references", "reference"}:
            references_started = True
        if references_started:
            continue
        if node["type"] == "heading" or lower.strip() in {"methods", "materials and methods", "stimuli", "procedure"}:
            current_section = content[:80]
            continue
        if len(content) < 25:
            continue
        node["section"] = current_section
        node["source_file"] = artifact_rel(json_path, paths.repo_root)
        filtered.append(node)
    return filtered, artifact_rel(json_path, paths.repo_root)


def load_supplement_text_nodes(record_id: str, paths: AuditPaths) -> tuple[list[dict[str, Any]], list[str]]:
    folder = paths.extracted_dir / "supplements" / record_id
    if not folder.exists():
        return [], []
    nodes: list[dict[str, Any]] = []
    source_files: list[str] = []
    for path in sorted(folder.glob("*.txt")):
        content = clean_evidence_text(path.read_text(encoding="utf-8", errors="replace"))
        if len(content) < 25:
            continue
        rel = artifact_rel(path, paths.repo_root)
        source_files.append(rel)
        nodes.append(
            {
                "type": "supplement_text",
                "page": "supplement",
                "content": content,
                "section": "supplement",
                "source_file": rel,
            }
        )
    return nodes, source_files


def load_fallback_text_nodes(record_id: str, paths: AuditPaths) -> tuple[list[dict[str, Any]], list[str]]:
    folder = paths.extracted_dir / "fallback" / record_id
    if not folder.exists():
        return [], []
    nodes: list[dict[str, Any]] = []
    source_files: list[str] = []
    page_splitter = re.compile(r"(?:^|\n)\s*\[page\s+([^\]]+)\]\s*\n", flags=re.IGNORECASE)
    for path in sorted(folder.glob("*.fallback.txt")):
        raw = path.read_text(encoding="utf-8", errors="replace")
        rel = artifact_rel(path, paths.repo_root)
        source_files.append(rel)
        parts = page_splitter.split(raw)
        page_chunks = zip(parts[1::2], parts[2::2]) if len(parts) > 1 else [("fallback", raw)]
        for page, content in page_chunks:
            text = clean_evidence_text(content)
            if len(text) < 25:
                continue
            nodes.append(
                {
                    "type": "fallback_pdf_text",
                    "page": str(page).strip(),
                    "content": text,
                    "section": "fallback_pdf_text",
                    "source_file": rel,
                }
            )
    return nodes, source_files


def load_mining_nodes(record_id: str, paths: AuditPaths) -> tuple[list[dict[str, Any]], list[str]]:
    main_nodes, main_source = load_opendataloader_nodes(record_id, paths)
    fallback_nodes, fallback_sources = load_fallback_text_nodes(record_id, paths)
    supplement_nodes, supplement_sources = load_supplement_text_nodes(record_id, paths)
    source_files = [source for source in [main_source, *fallback_sources, *supplement_sources] if source]
    return [*main_nodes, *fallback_nodes, *supplement_nodes], source_files


def score_node_for_field(node: dict[str, Any], field_key: str) -> int:
    lower = node["content"].lower()
    score = 0
    for keyword in FIELD_KEYWORDS[field_key]:
        if keyword in lower:
            score += 3 if " " in keyword else 1
    if NUMERIC_PATTERN.search(node["content"]):
        score += 1
    section = str(node.get("section", "")).lower()
    if section and any(term in section for term in ("method", "stimuli", "procedure", "experiment")):
        score += 1
    return score


def semantic_review_passes(record: dict[str, Any], nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if record["coverage_category"] == ADJACENT_CATEGORY:
        return [
            {
                "strategy": strategy["strategy"],
                "status": "not_applicable",
                "hit_count": 0,
                "matched_terms": [],
                "page_or_section": "",
                "purpose": strategy["purpose"],
            }
            for strategy in SEMANTIC_REVIEW_STRATEGIES
        ]
    if not nodes:
        return [
            {
                "strategy": strategy["strategy"],
                "status": "source_unavailable",
                "hit_count": 0,
                "matched_terms": [],
                "page_or_section": "",
                "purpose": strategy["purpose"],
            }
            for strategy in SEMANTIC_REVIEW_STRATEGIES
        ]

    passes: list[dict[str, Any]] = []
    for strategy in SEMANTIC_REVIEW_STRATEGIES:
        terms = list(strategy["keywords"])
        matched_terms: list[str] = []
        pages: list[str] = []
        hit_count = 0
        for node in nodes:
            lower = node["content"].lower()
            node_terms = [term for term in terms if term in lower]
            if not node_terms:
                continue
            hit_count += 1
            matched_terms.extend(node_terms)
            if node.get("page"):
                pages.append(str(node["page"]))
        matched_terms = dedupe_preserve_order(matched_terms)
        pages = dedupe_preserve_order(pages)
        passes.append(
            {
                "strategy": strategy["strategy"],
                "status": "completed" if hit_count else "completed_no_hits",
                "hit_count": hit_count,
                "matched_terms": matched_terms[:12],
                "page_or_section": "source page/section(s) " + ", ".join(pages[:8]) if pages else "",
                "purpose": strategy["purpose"],
            }
        )
    return passes


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        normalized = value.strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        unique.append(normalized)
    return unique


def numeric_values_for_field(field_key: str, text: str) -> list[str]:
    values: list[str] = []
    for match in NUMERIC_PATTERN.finditer(text):
        value = match.group(0).replace("\u2013", "-").replace("\u2014", "-")
        lower = value.lower()
        if field_key in {"stimulus_duration", "iti_jitter_policy", "soa_table", "baseline_timing"} and any(
            unit in lower for unit in ("cm/s", "cm", "db", "dba", "spl", "hz", "khz", "ma", "trial", "block")
        ):
            continue
        if field_key == "stimulus_type" and re.search(r"\b(?:hz|khz)\b", lower):
            values.append(value)
        elif field_key == "trajectory_path" and re.search(r"\bcm\b", lower) and "cm/s" not in lower:
            values.append(value)
        elif field_key == "stimulus_duration" and re.search(r"\b(?:ms|msec|sec|s)\b", lower):
            values.append(value)
        elif field_key == "stimulus_speed" and re.search(r"\b(?:cm/s|m/s)\b", lower):
            values.append(value)
        elif field_key == "gain_envelope" and re.search(r"\b(?:db|dba|spl)\b", lower):
            values.append(value)
        elif field_key == "iti_jitter_policy" and re.search(r"\b(?:ms|msec|sec|s)\b", lower):
            values.append(value)
        elif field_key == "tactile_stimulus" and re.search(r"\b(?:ms|msec|hz|ma|%)\b", lower):
            values.append(value)
        elif field_key == "soa_table" and re.search(r"\b(?:ms|msec)\b", lower):
            values.append(value)
        elif field_key == "baseline_timing" and re.search(r"\b(?:ms|msec|sec|s)\b", lower):
            values.append(value)
        elif field_key in {"catch_trial_type", "repetitions_per_tactile_soa_condition", "baseline_count", "catch_count", "total_trial_count"} and re.search(r"\b(?:trial|trials|%)\b", lower):
            values.append(value)
        elif field_key == "block_count" and re.search(r"\b(?:block|blocks|session|sessions)\b", lower):
            values.append(value)
    return values


def field_candidate_value(field_key: str, nodes: list[dict[str, Any]]) -> str:
    text = " ".join(node["content"] for node in nodes)
    lower = text.lower()
    values: list[str] = []
    for needle, label in FIELD_CANONICAL_TERMS.get(field_key, []):
        if needle in lower:
            values.append(label)
    values.extend(numeric_values_for_field(field_key, text))
    if field_key == "trajectory_count":
        if all(term in lower for term in ("front", "rear", "left", "right")):
            values.append("four body-relative directions")
        if "approaching" in lower and "receding" in lower:
            values.append("approaching and receding motions")
        if "in sound" in lower and "out sound" in lower:
            values.append("IN and OUT sounds")
    if field_key == "blocked_or_random_order":
        if "random" in lower:
            values.append("randomized/random order")
        if "two blocks" in lower:
            values.append("2 blocks")
    if field_key == "block_count" and "two blocks" in lower:
        values.append("2 blocks")
    if field_key == "soa_table":
        for pattern in (
            r"T1[^.;]{0,90}T2[^.;]{0,90}T3[^.;]{0,90}T4[^.;]{0,90}T5[^.;]{0,90}",
            r"300\s*,?\s*800\s*,?\s*1500\s*,?\s*2200\s*,?\s*2700\s*ms",
        ):
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                values.append(clean_evidence_text(match.group(0))[:180])
                break
    if field_key == "baseline_timing":
        for token in ("Tbefore", "Tafter", "T0", "T6"):
            if token.lower() in lower:
                values.append(token)
    values = dedupe_preserve_order(values)
    if not values:
        return ""
    return "Auto-mined candidates: " + "; ".join(values[:16])


def mine_segment_field_audit(record: dict[str, Any], paths: AuditPaths) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    field_audit = make_field_template(record)
    if record["coverage_category"] == ADJACENT_CATEGORY:
        return field_audit, {
            "status": "not_applicable",
            "field_count": 0,
            "coverage_ratio": 0.0,
            "source_files": [],
            "semantic_review_passes": semantic_review_passes(record, []),
        }

    nodes, source_files = load_mining_nodes(record["record_id"], paths)
    review_passes = semantic_review_passes(record, nodes)
    if not nodes:
        return field_audit, {
            "status": "no_extracted_source",
            "field_count": 0,
            "coverage_ratio": 0.0,
            "source_files": source_files,
            "semantic_review_passes": review_passes,
        }

    mined_count = 0
    for segment, fields in field_audit.items():
        for field_key, field in fields.items():
            scored = [
                (score_node_for_field(node, field_key), index, node)
                for index, node in enumerate(nodes)
            ]
            ranked = [
                (score, index, node)
                for score, index, node in sorted(scored, key=lambda item: (-item[0], item[1]))
                if score > 0
            ][:3]
            if not ranked:
                continue
            candidate_nodes = [node for _, _, node in ranked]
            value = field_candidate_value(field_key, candidate_nodes)
            if not value:
                continue
            pages = dedupe_preserve_order([node["page"] for node in candidate_nodes if node.get("page")])
            field_source_files = dedupe_preserve_order(
                [node["source_file"] for node in candidate_nodes if node.get("source_file")]
            )
            field.update(
                {
                    "status": "inferred_low_confidence",
                    "value": ascii_safe(value[:320]),
                    "source_file": field_source_files[0] if field_source_files else (source_files[0] if source_files else ""),
                    "page_or_section": "source page/section(s) " + ", ".join(pages[:4]) if pages else "extracted source text",
                    "evidence_note": "Automated Segment 1-4 miner found field-specific keywords/numeric values; verify against PDF and supplements before final profile recreation.",
                }
            )
            mined_count += 1

    return field_audit, {
        "status": "source_mined",
        "field_count": mined_count,
        "coverage_ratio": round(mined_count / TOTAL_SEGMENT_FIELD_COUNT, 3),
        "source_files": source_files,
        "semantic_review_passes": review_passes,
    }


def metadata_confidence(
    record: dict[str, Any],
    pdf_status: str,
    extraction_status: str,
    automated_evidence: dict[str, Any] | None = None,
) -> tuple[float, str, str]:
    if record["coverage_category"] == ADJACENT_CATEGORY:
        return (
            0.0,
            "not_applicable",
            "Record is adjacent/out of scope for audiotactile PPS Segment 1-4 extraction.",
        )
    mined_ratio = float((automated_evidence or {}).get("coverage_ratio", 0.0) or 0.0)
    mined_count = int((automated_evidence or {}).get("field_count", 0) or 0)
    if pdf_status == "downloaded" and extraction_status in {"parsed", "parsed_with_warnings"} and mined_count:
        return (
            round(0.25 + min(0.35, mined_ratio * 0.35), 2),
            "partial_extraction",
            f"Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for {mined_count}/{TOTAL_SEGMENT_FIELD_COUNT} fields; values still require critical PDF/supplement review.",
        )
    if pdf_status == "downloaded" and extraction_status in {"parsed", "parsed_with_warnings"}:
        return (
            0.2,
            "source_acquired_unreviewed",
            "Publication PDF is locally available and parsed, but Segment 1-4 values still require critical manual review.",
        )
    if mined_count:
        return (
            round(0.15 + min(0.25, mined_ratio * 0.30), 2),
            "partial_extraction",
            f"Supplement or other extracted source text yielded candidate values for {mined_count}/{TOTAL_SEGMENT_FIELD_COUNT} fields, but the main publication PDF is still missing or unavailable.",
        )
    if pdf_status in {"open_access_unavailable", "paywalled"}:
        return (
            0.0,
            "source_unavailable",
            "Automated open-access acquisition did not produce a locally inspectable publication PDF.",
        )
    return (
        0.0,
        "pending_source",
        "Main publication PDF is not yet locally available for Segment 1-4 inspection.",
    )


def make_review_attempts(record: dict[str, Any], pdf_status: str, supplement_status: str) -> list[dict[str, str]]:
    if supplement_status == "downloaded":
        supplement_attempt_status = "available_for_review"
        supplement_note = "Downloaded or locally provided supplement files are available for methods/table review."
    elif supplement_status == "not_found":
        supplement_attempt_status = "checked_not_found"
        supplement_note = "Automated source routes found no supplement candidates; use publisher/source checks again before final missing-value decisions."
    elif supplement_status in {"needs_user_download", "paywalled"}:
        supplement_attempt_status = "pending_manual_download"
        supplement_note = "Supplement-like sources were found or access was limited; manual download/check is still needed."
    else:
        supplement_attempt_status = "pending_download_or_check"
        supplement_note = "Check supplementary PDFs, spreadsheets, methods appendices, and task scripts when main-paper fields are absent."
    if record["coverage_category"] == ADJACENT_CATEGORY:
        return [
            {
                "attempt": "scope check",
                "status": "complete_from_existing_ledger",
                "note": "Existing literature ledger marks this record adjacent/out of scope for audiotactile PPS metadata extraction.",
            }
        ]
    return [
        {
            "attempt": "main PDF OpenDataLoader extraction",
            "status": "pending" if pdf_status == "needs_user_download" else "available_for_run",
            "note": "Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.",
        },
        {
            "attempt": "targeted methods/table search",
            "status": "pending_pdf" if pdf_status == "needs_user_download" else "pending_review",
            "note": "Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.",
        },
        {
            "attempt": "supplement search",
            "status": supplement_attempt_status,
            "note": supplement_note,
        },
        {
            "attempt": "fallback extractor/source check",
            "status": "pending_pdf" if pdf_status == "needs_user_download" else "pending_review",
            "note": "Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.",
        },
    ]


def fallback_extract_pdf(pdf_path: Path, output_dir: Path) -> tuple[str, list[str]]:
    warnings: list[str] = []
    text = ""
    if importlib.util.find_spec("pdfplumber") is not None:
        try:
            import pdfplumber  # type: ignore

            chunks: list[str] = []
            with pdfplumber.open(str(pdf_path)) as pdf:
                for index, page in enumerate(pdf.pages, start=1):
                    page_text = page.extract_text() or ""
                    chunks.append(f"\n\n[page {index}]\n{page_text}")
            text = "".join(chunks)
        except Exception as exc:  # pragma: no cover - exercised only with real PDFs
            warnings.append(f"pdfplumber failed: {exc}")
    if not text and importlib.util.find_spec("pypdf") is not None:
        try:
            from pypdf import PdfReader  # type: ignore

            reader = PdfReader(str(pdf_path))
            chunks = [
                f"\n\n[page {index}]\n{page.extract_text() or ''}"
                for index, page in enumerate(reader.pages, start=1)
            ]
            text = "".join(chunks)
        except Exception as exc:  # pragma: no cover - exercised only with real PDFs
            warnings.append(f"pypdf failed: {exc}")
    if not text:
        raise RuntimeError("; ".join(warnings) or "No fallback PDF extractor available")
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{pdf_path.stem}.fallback.txt"
    out_path.write_text(text, encoding="utf-8", errors="replace")
    return out_path.name, warnings


def run_opendataloader(pdf_paths: list[Path], output_dir: Path, repo_root: Path) -> tuple[bool, str]:
    if not pdf_paths:
        return True, "no PDFs to parse"
    java_path = ensure_java_on_path(repo_root)
    if not (java_path and importlib.util.find_spec("opendataloader_pdf")):
        return False, "Java and/or opendataloader_pdf unavailable"
    try:
        import opendataloader_pdf  # type: ignore

        output_dir.mkdir(parents=True, exist_ok=True)
        opendataloader_pdf.convert(
            input_path=[str(path) for path in pdf_paths],
            output_dir=str(output_dir),
            format="markdown,json",
        )
    except Exception as exc:  # pragma: no cover - exercised only when dependency is installed
        return False, f"OpenDataLoader failed: {exc}"
    return True, "OpenDataLoader conversion completed"


def extract_downloaded_pdfs(records: list[dict[str, Any]], paths: AuditPaths) -> dict[str, dict[str, Any]]:
    downloaded = []
    pdf_by_record: dict[str, Path] = {}
    for record in records:
        if record["coverage_category"] == ADJACENT_CATEGORY:
            continue
        pdf_path, pdf_status = find_pdf(record["record_id"], paths.pdf_dir)
        if pdf_path is not None and pdf_status == "downloaded":
            downloaded.append(pdf_path)
            pdf_by_record[record["record_id"]] = pdf_path

    extraction_log: dict[str, dict[str, Any]] = {}
    success, message = run_opendataloader(downloaded, paths.extracted_dir / "opendataloader", paths.repo_root)
    for record_id, pdf_path in pdf_by_record.items():
        extraction_log[record_id] = {
            "primary_extractor": "opendataloader_pdf",
            "primary_success": success,
            "primary_message": message,
            "fallback_output": "",
            "warnings": [],
            "status": "parsed" if success else "parsed_with_warnings",
        }
        if not success:
            try:
                fallback_output, warnings = fallback_extract_pdf(
                    pdf_path,
                    paths.extracted_dir / "fallback" / record_id,
                )
                extraction_log[record_id].update(
                    {
                        "fallback_output": fallback_output,
                        "warnings": warnings,
                        "status": "parsed_with_warnings",
                    }
                )
            except Exception as exc:  # pragma: no cover - exercised only with bad local PDFs
                extraction_log[record_id].update(
                    {
                        "warnings": [str(exc)],
                        "status": "failed",
                    }
                )
    return extraction_log


def build_records(
    literature_records: list[dict[str, Any]],
    paths: AuditPaths,
    extraction_log: dict[str, dict[str, Any]],
    supplement_extraction_log: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    audit_records: list[dict[str, Any]] = []
    missing_requests: list[dict[str, Any]] = []
    acquisition_by_record = load_acquisition_status(paths.repo_root / ACQUISITION_STATUS_PATH)
    for record in literature_records:
        record_id = record["record_id"]
        is_adjacent = record["coverage_category"] == ADJACENT_CATEGORY
        acquisition_status = acquisition_by_record.get(record_id, {})
        pdf_path, pdf_status = (None, "not_applicable") if is_adjacent else find_pdf(record_id, paths.pdf_dir)
        if not is_adjacent and pdf_path is None:
            acquired_status = acquisition_status.get("pdf_status")
            if acquired_status in PDF_STATUSES and acquired_status != "downloaded":
                pdf_status = acquired_status
        supplement_files, supplement_status = (
            ([], "not_applicable") if is_adjacent else find_supplements(record_id, paths.supplement_dir)
        )
        supplement_acquisition = acquisition_status.get("supplement_acquisition", {})
        supplement_extraction = supplement_extraction_log.get(record_id, {})
        if (
            not is_adjacent
            and not supplement_files
            and supplement_acquisition.get("supplement_status") in SUPPLEMENT_STATUSES
        ):
            supplement_status = supplement_acquisition["supplement_status"]
        if is_adjacent:
            extraction_status = "parsed_with_warnings"
        elif pdf_status == "bad_pdf":
            extraction_status = "failed"
        elif pdf_status != "downloaded":
            extraction_status = "pending_pdf"
        else:
            extraction_status = extraction_log.get(record_id, {}).get("status", "parsed_with_warnings")
        segment_field_audit, automated_evidence = mine_segment_field_audit(record, paths)
        confidence_score, confidence_label, confidence_basis = metadata_confidence(
            record,
            pdf_status,
            extraction_status,
            automated_evidence,
        )

        audit_record = {
            "schema": "pps-paper-metadata-audit-record.v1",
            "record_id": record_id,
            "citation_short": ascii_safe(record["citation_short"]),
            "doi": record.get("doi", ""),
            "doi_url": doi_url(record.get("doi", "")),
            "coverage_category": record["coverage_category"],
            "audiotactile_task_family": ascii_safe(record.get("audiotactile_task_family", "")),
            "source_basis": record.get("source_basis", []),
            "current_template_ids": record.get("current_template_ids", []),
            "pdf_status": pdf_status,
            "pdf_file": artifact_rel(pdf_path, paths.repo_root) if pdf_path else "",
            "pdf_acquisition_attempt_count": acquisition_status.get("attempt_count", 0),
            "pdf_acquisition_last_status": acquisition_status.get("last_status", ""),
            "supplement_status": supplement_status,
            "supplement_files": [artifact_rel(path, paths.repo_root) for path in supplement_files],
            "supplement_acquisition_attempt_count": supplement_acquisition.get("attempt_count", 0),
            "supplement_acquisition_last_status": supplement_acquisition.get("last_status", ""),
            "supplement_extracted_text_files": supplement_extraction.get("parsed_files", []),
            "supplement_extraction_status_counts": supplement_extraction.get("status_counts", {}),
            "extraction_status": extraction_status,
            "metadata_confidence_score": confidence_score,
            "metadata_confidence_label": confidence_label,
            "metadata_confidence_basis": confidence_basis,
            "automated_evidence_mining": automated_evidence,
            "extraction_outputs": {
                "primary": "artifacts/paper_metadata_audit/extracted/opendataloader/",
                "fallback": f"artifacts/paper_metadata_audit/extracted/fallback/{record_id}/",
            },
            "known_missing_or_unresolved_from_prior_ledger": [
                ascii_safe(item) for item in record.get("missing_publication_parameters", [])
            ],
            "blocking_constraint_ids_from_prior_ledger": record.get("blocking_constraint_ids", []),
            "segment_field_audit": segment_field_audit,
            "review_attempts": make_review_attempts(record, pdf_status, supplement_status),
        }
        audit_records.append(audit_record)

        if not is_adjacent and pdf_status in {"needs_user_download", "bad_pdf", "open_access_unavailable", "paywalled"}:
            missing_requests.append(
                {
                    "record_id": record_id,
                    "citation_short": ascii_safe(record["citation_short"]),
                    "doi": record.get("doi", ""),
                    "doi_url": doi_url(record.get("doi", "")),
                    "requested_item": "publication_pdf",
                    "current_status": pdf_status,
                    "target_location": f"artifacts/paper_metadata_audit/publication_pdfs/{record_id}.pdf",
                    "note": "Download the main publication PDF here for exact Segment 1-4 inspection.",
                }
            )
        if not is_adjacent and supplement_status in {"not_checked", "needs_user_download", "paywalled"}:
            missing_requests.append(
                {
                    "record_id": record_id,
                    "citation_short": ascii_safe(record["citation_short"]),
                    "doi": record.get("doi", ""),
                    "doi_url": doi_url(record.get("doi", "")),
                    "requested_item": "supplement_or_methods_files",
                    "current_status": supplement_status,
                    "target_location": f"artifacts/paper_metadata_audit/supplements/{record_id}/",
                    "note": "Check publisher/PMC/OSF/project pages for supplementary PDFs, tables, scripts, or appendices.",
                }
            )
    return audit_records, missing_requests


def summary_from_records(audit_records: list[dict[str, Any]], missing_requests: list[dict[str, Any]]) -> dict[str, Any]:
    def count_by(key: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in audit_records:
            counts[record[key]] = counts.get(record[key], 0) + 1
        return dict(sorted(counts.items()))

    mined_field_counts = [
        int(record.get("automated_evidence_mining", {}).get("field_count", 0) or 0)
        for record in audit_records
    ]
    semantic_status_counts: dict[str, int] = {}
    semantic_pass_total = 0
    supplement_extracted_file_total = 0
    supplement_extracted_record_count = 0
    for record in audit_records:
        supplement_extracted_files = record.get("supplement_extracted_text_files", [])
        if supplement_extracted_files:
            supplement_extracted_record_count += 1
            supplement_extracted_file_total += len(supplement_extracted_files)
        for review_pass in record.get("automated_evidence_mining", {}).get("semantic_review_passes", []):
            semantic_pass_total += 1
            status = str(review_pass.get("status", ""))
            semantic_status_counts[status] = semantic_status_counts.get(status, 0) + 1
    return {
        "schema": "pps-paper-metadata-audit-summary.v1",
        "generated_on": date.today().isoformat(),
        "parser_version": PARSER_VERSION,
        "record_count": len(audit_records),
        "doi_record_count": sum(1 for record in audit_records if record.get("doi")),
        "missing_doi_record_count": sum(1 for record in audit_records if not record.get("doi")),
        "pdf_retrieved_record_count": sum(1 for record in audit_records if record.get("pdf_status") == "downloaded"),
        "pdf_missing_or_unavailable_record_count": sum(
            1
            for record in audit_records
            if record.get("pdf_status") in {"needs_user_download", "bad_pdf", "open_access_unavailable", "paywalled"}
        ),
        "pdf_not_applicable_record_count": sum(
            1 for record in audit_records if record.get("pdf_status") == "not_applicable"
        ),
        "pdf_status_counts": count_by("pdf_status"),
        "supplement_status_counts": count_by("supplement_status"),
        "extraction_status_counts": count_by("extraction_status"),
        "metadata_confidence_label_counts": count_by("metadata_confidence_label"),
        "automated_evidence_status_counts": {
            status: sum(
                1
                for record in audit_records
                if record.get("automated_evidence_mining", {}).get("status") == status
            )
            for status in sorted(
                {
                    str(record.get("automated_evidence_mining", {}).get("status", ""))
                    for record in audit_records
                }
            )
            if status
        },
        "automated_evidence_field_total": sum(mined_field_counts),
        "supplement_extracted_record_count": supplement_extracted_record_count,
        "supplement_extracted_file_total": supplement_extracted_file_total,
        "semantic_review_strategy_count": len(SEMANTIC_REVIEW_STRATEGIES),
        "semantic_review_pass_total": semantic_pass_total,
        "semantic_review_pass_status_counts": dict(sorted(semantic_status_counts.items())),
        "missing_download_request_count": len(missing_requests),
        "tracked_pdf_folder": "artifacts/paper_metadata_audit/publication_pdfs/",
        "tracked_supplement_folder": "artifacts/paper_metadata_audit/supplements/",
        "tracked_extraction_folder": "artifacts/paper_metadata_audit/extracted/",
        "copyright_boundary": "PDFs, supplements, extracted text, and long quoted passages stay in ignored artifacts; tracked files store only metadata, statuses, and short evidence pointers.",
    }


def schema_payload() -> dict[str, Any]:
    return {
        "schema": "pps-paper-metadata-extraction-schema.v1",
        "parser_version": PARSER_VERSION,
        "pdf_statuses": list(PDF_STATUSES),
        "supplement_statuses": list(SUPPLEMENT_STATUSES),
        "extraction_statuses": list(EXTRACTION_STATUSES),
        "field_statuses": list(FIELD_STATUSES),
        "confidence_labels": list(CONFIDENCE_LABELS),
        "automated_evidence": {
            "status_values": ["not_applicable", "no_extracted_source", "source_mined"],
            "semantic_review_pass_status_values": ["completed", "completed_no_hits", "source_unavailable", "not_applicable"],
            "semantic_review_strategy_count": len(SEMANTIC_REVIEW_STRATEGIES),
            "rule": "Store only short candidate values and page pointers; do not commit full text excerpts.",
        },
        "supplement_extraction": {
            "supported_local_formats": [".doc", ".docx", ".pdf", ".ods", ".csv", ".tsv"],
            "rule": "Supplement text extraction writes only ignored local text artifacts; tracked audit files store counts, statuses, and short evidence pointers.",
        },
        "manual_reviews": {
            "folder": "For-AI/audiotactile-paper-metadata-audit/manual_reviews/",
            "index": "For-AI/audiotactile-paper-metadata-audit/manual_review_index.csv",
            "schema": "pps-paper-metadata-manual-review.v1",
            "rule": "Manual reviews promote auto-mined candidates only after repeated critical passes; store normalized values, field statuses, confidence scores, and short source pointers, not full text.",
        },
        "pdf_retrieval_inventory": {
            "path": "For-AI/audiotactile-paper-metadata-audit/pdf_retrieval_inventory.csv",
            "rule": "One row per literature record; records whether the main publication PDF has been retrieved locally, gives the DOI/DOI URL for missing PDFs, and names the target local PDF path.",
        },
        "protocol_lineage_candidates": {
            "path": "For-AI/audiotactile-paper-metadata-audit/protocol_lineage_candidates.csv",
            "rule": "Cited prior-protocol papers that may contain missing stimulus, trajectory, timing, apparatus, or count details for another audited paper; promote to the main literature database after screening when appropriate.",
        },
        "segment_fields": SEGMENT_FIELDS,
        "review_rule": {
            "missing_value_rule": "Only mark not_reported_after_review after main PDF extraction, targeted methods/table search, supplement search, fallback extractor/source check, and cited prior-protocol lineage search have all been attempted.",
            "copyright_boundary": "Do not commit PDFs, supplements, extracted full text, screenshots of pages, or long verbatim passages.",
            "automated_evidence_rule": "Automated evidence mining stores only short candidate values and page pointers; it is not a substitute for final human/AI critical review against PDFs and supplements.",
        },
        "local_artifact_conventions": {
            "main_pdf_filename": "artifacts/paper_metadata_audit/publication_pdfs/<record_id>.pdf",
            "supplement_folder": "artifacts/paper_metadata_audit/supplements/<record_id>/",
            "extracted_output_folder": "artifacts/paper_metadata_audit/extracted/",
        },
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: ascii_safe(row.get(key, "")) for key in fieldnames})


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")


def readme_text(summary: dict[str, Any], environment: dict[str, Any]) -> str:
    return f"""# Audiotactile Paper Metadata Audit

This folder is dedicated to metadata extraction from published audio-tactile PPS papers. It is intentionally independent from GUI/profile recreation: the goal is to inspect papers and supplements and record whether Segment 1-4 metadata can be extracted.

## Local Artifact Folders

- `artifacts/paper_metadata_audit/publication_pdfs/`: place publication PDFs here as `<record_id>.pdf`.
- `artifacts/paper_metadata_audit/supplements/<record_id>/`: place supplementary PDFs, DOCX, XLSX, ODS, ZIPs, scripts, or appendices here.
- `artifacts/paper_metadata_audit/extracted/`: parser output from OpenDataLoader PDF and fallback extractors.
- `artifacts/paper_metadata_audit/resume_bundles/`: ignored local ZIP backups for private transfer/resume only.

The `artifacts/` tree is ignored by Git. Do not commit PDFs, supplements, extracted full text, page images, or long copied passages.
Use `python -m tools.paper_metadata_parser.bundle --repo-root .` to refresh `local_artifact_inventory.json` and create/update the ignored local resume ZIP. The inventory is GitHub-safe because it stores only relative paths, sizes, hashes, and restore notes.

## Tracked Manual Reviews

- `manual_reviews/<record_id>.json`: durable critical reviews with normalized Segment 1-4 values, field statuses, confidence scores, and short source pointers.
- `manual_review_index.csv`: compact progress index for hand-reviewed records.

Manual reviews are the layer where auto-mined candidates become checked metadata. Keep them short and source-pointer-only; do not paste full methods text or copyrighted passages.

## Protocol Lineage Rule

Some papers omit low-level stimulus, trajectory, timing, or count details because they say the task was adapted from, based on, or used as an established paradigm from earlier work. In those cases, inspect the cited prior-protocol paper before marking the field `not_reported_after_review`, and record the linked source in `protocol_lineage_candidates.csv`.

## Tracked Generated Ledgers

- `pdf_retrieval_inventory.csv`: canonical running list of which main publication PDFs are already retrieved, which are missing, DOI/DOI URL for missing records, and the local target filename.
- `protocol_lineage_candidates.csv`: cited prior-protocol papers that may contain missing stimulus, trajectory, timing, or count details for another audited paper.
- `doi_inventory.csv`: DOI/DOI URL inventory plus current PDF and supplement status for every literature record.
- `missing_pdf_request_list.csv`: actionable download queue for missing main PDFs and supplement/methods files.
- `running_checklist.csv`: compact all-record metadata audit progress checklist.

## Current Inventory

- Literature records: {summary["record_count"]}
- PDF status counts: `{json.dumps(summary["pdf_status_counts"], sort_keys=True)}`
- Main PDFs retrieved/missing/not applicable: {summary["pdf_retrieved_record_count"]} / {summary["pdf_missing_or_unavailable_record_count"]} / {summary["pdf_not_applicable_record_count"]}
- Supplement status counts: `{json.dumps(summary["supplement_status_counts"], sort_keys=True)}`
- Extraction status counts: `{json.dumps(summary["extraction_status_counts"], sort_keys=True)}`
- Metadata confidence counts: `{json.dumps(summary["metadata_confidence_label_counts"], sort_keys=True)}`
- Automated evidence status counts: `{json.dumps(summary["automated_evidence_status_counts"], sort_keys=True)}`
- Automated evidence mined field total: {summary["automated_evidence_field_total"]}
- Supplement extracted records/files: {summary["supplement_extracted_record_count"]} records / {summary["supplement_extracted_file_total"]} files
- Semantic review strategy count: {summary["semantic_review_strategy_count"]}
- Semantic review pass status counts: `{json.dumps(summary["semantic_review_pass_status_counts"], sort_keys=True)}`
- Missing download/check requests: {summary["missing_download_request_count"]}

## Environment Readiness

- Java available: `{environment["java_available"]}`
- `opendataloader_pdf` installed: `{environment["opendataloader_pdf_installed"]}`
- OpenDataLoader ready: `{environment["opendataloader_ready"]}`
- Fallback extractors: `{json.dumps(environment["fallback_extractors"], sort_keys=True)}`

## How To Use

1. Download each available publication PDF into `artifacts/paper_metadata_audit/publication_pdfs/<record_id>.pdf`.
2. Download supplements into `artifacts/paper_metadata_audit/supplements/<record_id>/`.
3. Run `python -m tools.paper_metadata_parser --refresh` from the repo root.
4. Review `pdf_retrieval_inventory.csv` first for the running list of retrieved/missing PDFs and missing-paper DOI URLs.
5. Review `protocol_lineage_candidates.csv` when a paper cites an adapted or established prior protocol.
6. Review `running_checklist.csv`, `missing_pdf_request_list.csv`, and `paper_audits/<record_id>.md`.
7. Promote critically checked Segment 1-4 values into `manual_reviews/<record_id>.json` and update `manual_review_index.csv`.

Automated evidence-mined values are `inferred_low_confidence` candidates. Treat them as a triage map for critical review, not as final paper metadata.

Before marking any value `not_reported_after_review`, inspect the main PDF, methods/tables, supplements, at least one fallback/source route, and any cited prior protocol paper that the article says it adapted, followed, or used as an established paradigm.
"""


def checklist_text() -> str:
    lines = [
        "# Segment 1-4 Metadata Checklist",
        "",
        "Use this checklist for every in-scope publication. Each field must carry one of the schema statuses and a short source pointer when a value is present.",
        "",
    ]
    for segment, fields in SEGMENT_FIELDS.items():
        title = segment.replace("_", " ").title()
        lines.append(f"## {title}")
        lines.append("")
        lines.append("| Field | What to extract |")
        lines.append("|---|---|")
        for field in fields:
            lines.append(f"| `{field['key']}` | {field['description']} |")
        lines.append("")
    lines.extend(
        [
            "## Missing-Value Rule",
            "",
            "A field can be marked `not_reported_after_review` only after all of these attempts are logged:",
            "",
            "1. Main publication PDF extraction with OpenDataLoader PDF.",
            "2. Targeted review of methods, apparatus, procedure, trial-design tables, and figures.",
            "3. Supplement search, including PDFs, spreadsheets, appendices, scripts, and project pages.",
            "4. Fallback extraction or source check using pdfplumber/pypdf, publisher HTML, rendered pages, or a second source route.",
            "5. Protocol-lineage search for terms such as adapted, previous, protocol, as described, based on, following, well-established, paradigm, front/frontal, and cited-methods references.",
            "",
            "When a paper says it adapted or used an established paradigm, record the cited source study and inspect that source before deciding that low-level stimulus, trajectory, timing, or count details are unavailable.",
            "",
            "Keep tracked evidence short. Store raw PDF/text artifacts only under ignored `artifacts/paper_metadata_audit/`.",
            "",
        ]
    )
    return "\n".join(lines)


def paper_audit_text(record: dict[str, Any]) -> str:
    lines = [
        f"# {ascii_safe(record['citation_short'])}",
        "",
        f"- Record ID: `{record['record_id']}`",
        f"- DOI: `{record['doi'] or 'not recorded'}`",
        f"- DOI URL: {record['doi_url'] or 'not recorded'}",
        f"- Coverage category: `{record['coverage_category']}`",
        f"- Task family: {ascii_safe(record['audiotactile_task_family'])}",
        f"- PDF status: `{record['pdf_status']}`",
        f"- Supplement status: `{record['supplement_status']}`",
        f"- Supplement acquisition attempts: `{record.get('supplement_acquisition_attempt_count', 0)}` (`{record.get('supplement_acquisition_last_status', '')}`)",
        f"- Supplement extracted text files: `{len(record.get('supplement_extracted_text_files', []))}`",
        f"- Extraction status: `{record['extraction_status']}`",
        f"- Metadata confidence: `{record['metadata_confidence_score']}` (`{record['metadata_confidence_label']}`)",
        f"- Confidence basis: {ascii_safe(record['metadata_confidence_basis'])}",
        f"- Automated evidence mining: `{record['automated_evidence_mining']['status']}`; {record['automated_evidence_mining']['field_count']}/{TOTAL_SEGMENT_FIELD_COUNT} fields with candidate values",
        "",
        "## Known Prior Gaps",
        "",
    ]
    gaps = record["known_missing_or_unresolved_from_prior_ledger"]
    if gaps:
        lines.extend(f"- {ascii_safe(gap)}" for gap in gaps)
    else:
        lines.append("- None recorded in the prior coverage ledger.")
    lines.extend(["", "## Review Attempts", ""])
    for attempt in record["review_attempts"]:
        lines.append(f"- `{attempt['attempt']}`: `{attempt['status']}` - {ascii_safe(attempt['note'])}")
    lines.extend(["", "## Five Semantic Review Passes", ""])
    lines.append("| Strategy | Status | Hits | Matched terms | Pages |")
    lines.append("|---|---|---:|---|---|")
    for review_pass in record["automated_evidence_mining"]["semantic_review_passes"]:
        lines.append(
            f"| `{review_pass['strategy']}` | `{review_pass['status']}` | {review_pass['hit_count']} | {ascii_safe(review_pass.get('matched_terms', []))} | {ascii_safe(review_pass.get('page_or_section', ''))} |"
        )
    lines.extend(["", "## Segment Field Status", ""])
    lines.append("| Segment | Field | Status | Value | Source pointer |")
    lines.append("|---|---|---|---|---|")
    for segment, fields in record["segment_field_audit"].items():
        for field_key, field in fields.items():
            source = "; ".join(
                part
                for part in (field.get("source_file", ""), field.get("page_or_section", ""))
                if part
            )
            lines.append(
                f"| `{segment}` | `{field_key}` | `{field['status']}` | {ascii_safe(field.get('value', ''))} | {ascii_safe(source)} |"
            )
    lines.append("")
    lines.append("Do not paste long source text here; use short page/section pointers and concise paraphrases.")
    lines.append("")
    return "\n".join(lines)


def write_audit_files(
    audit_records: list[dict[str, Any]],
    missing_requests: list[dict[str, Any]],
    summary: dict[str, Any],
    environment: dict[str, Any],
    paths: AuditPaths,
) -> None:
    write_json(paths.audit_dir / "extraction_schema.json", schema_payload())
    write_json(paths.audit_dir / "environment_readiness.json", environment)
    write_json(paths.audit_dir / "audit_summary.json", summary)
    (paths.audit_dir / "README.md").write_text(readme_text(summary, environment), encoding="utf-8")
    (paths.audit_dir / "parameter_checklist.md").write_text(checklist_text(), encoding="utf-8")
    write_jsonl(paths.audit_dir / "metadata_audit.jsonl", audit_records)

    doi_rows = [
        {
            "record_id": record["record_id"],
            "citation_short": record["citation_short"],
            "doi": record["doi"],
            "doi_url": doi_url(record["doi"]),
            "coverage_category": record["coverage_category"],
            "pdf_status": record["pdf_status"],
            "supplement_status": record["supplement_status"],
        }
        for record in audit_records
    ]
    write_csv(
        paths.audit_dir / "doi_inventory.csv",
        doi_rows,
        [
            "record_id",
            "citation_short",
            "doi",
            "doi_url",
            "coverage_category",
            "pdf_status",
            "supplement_status",
        ],
    )

    pdf_retrieval_rows = []
    for record in audit_records:
        pdf_status = record["pdf_status"]
        if pdf_status == "downloaded":
            pdf_retrieved = "yes"
        elif pdf_status == "not_applicable":
            pdf_retrieved = "not_applicable"
        else:
            pdf_retrieved = "no"
        doi = record["doi"]
        manual_download_target = ""
        if pdf_status not in {"downloaded", "not_applicable"}:
            manual_download_target = f"artifacts/paper_metadata_audit/publication_pdfs/{record['record_id']}.pdf"
        pdf_retrieval_rows.append(
            {
                "record_id": record["record_id"],
                "citation_short": record["citation_short"],
                "coverage_category": record["coverage_category"],
                "pdf_retrieved": pdf_retrieved,
                "pdf_status": pdf_status,
                "pdf_file": record["pdf_file"],
                "doi": doi,
                "doi_url": doi_url(doi),
                "doi_missing": "yes" if not doi else "no",
                "manual_download_target": manual_download_target,
                "manual_download_priority": (
                    "already_retrieved"
                    if pdf_status == "downloaded"
                    else "not_applicable"
                    if pdf_status == "not_applicable"
                    else "doi_lookup_needed"
                    if not doi
                    else "download_by_doi"
                ),
                "pdf_acquisition_attempt_count": record["pdf_acquisition_attempt_count"],
                "pdf_acquisition_last_status": record["pdf_acquisition_last_status"],
                "note": (
                    "Main publication PDF is available locally."
                    if pdf_status == "downloaded"
                    else "Adjacent/out-of-scope record; no PDF retrieval required."
                    if pdf_status == "not_applicable"
                    else "Main publication PDF still missing locally; use DOI/DOI URL when available."
                ),
            }
        )
    write_csv(
        paths.audit_dir / "pdf_retrieval_inventory.csv",
        pdf_retrieval_rows,
        [
            "record_id",
            "citation_short",
            "coverage_category",
            "pdf_retrieved",
            "pdf_status",
            "pdf_file",
            "doi",
            "doi_url",
            "doi_missing",
            "manual_download_target",
            "manual_download_priority",
            "pdf_acquisition_attempt_count",
            "pdf_acquisition_last_status",
            "note",
        ],
    )

    checklist_rows = [
        {
            "record_id": record["record_id"],
            "citation_short": record["citation_short"],
            "doi": record["doi"],
            "coverage_category": record["coverage_category"],
            "pdf_status": record["pdf_status"],
            "supplement_status": record["supplement_status"],
            "extraction_status": record["extraction_status"],
            "pdf_file": record["pdf_file"],
            "supplement_file_count": len(record["supplement_files"]),
            "supplement_acquisition_attempt_count": record["supplement_acquisition_attempt_count"],
            "supplement_acquisition_last_status": record["supplement_acquisition_last_status"],
            "supplement_extracted_text_file_count": len(record["supplement_extracted_text_files"]),
            "known_prior_gap_count": len(record["known_missing_or_unresolved_from_prior_ledger"]),
            "metadata_confidence_score": record["metadata_confidence_score"],
            "metadata_confidence_label": record["metadata_confidence_label"],
            "automated_evidence_field_count": record["automated_evidence_mining"]["field_count"],
            "automated_evidence_coverage_ratio": record["automated_evidence_mining"]["coverage_ratio"],
            "semantic_review_completed_passes": sum(
                1
                for review_pass in record["automated_evidence_mining"]["semantic_review_passes"]
                if review_pass["status"] in {"completed", "completed_no_hits"}
            ),
            "semantic_review_source_unavailable_passes": sum(
                1
                for review_pass in record["automated_evidence_mining"]["semantic_review_passes"]
                if review_pass["status"] == "source_unavailable"
            ),
        }
        for record in audit_records
    ]
    write_csv(
        paths.audit_dir / "running_checklist.csv",
        checklist_rows,
        [
            "record_id",
            "citation_short",
            "doi",
            "coverage_category",
            "pdf_status",
            "supplement_status",
            "extraction_status",
            "pdf_file",
            "supplement_file_count",
            "supplement_acquisition_attempt_count",
            "supplement_acquisition_last_status",
            "supplement_extracted_text_file_count",
            "known_prior_gap_count",
            "metadata_confidence_score",
            "metadata_confidence_label",
            "automated_evidence_field_count",
            "automated_evidence_coverage_ratio",
            "semantic_review_completed_passes",
            "semantic_review_source_unavailable_passes",
        ],
    )
    write_csv(
        paths.audit_dir / "missing_pdf_request_list.csv",
        missing_requests,
        [
            "record_id",
            "citation_short",
            "doi",
            "doi_url",
            "requested_item",
            "current_status",
            "target_location",
            "note",
        ],
    )
    paper_dir = paths.audit_dir / "paper_audits"
    for old_file in paper_dir.glob("*.md"):
        old_file.unlink()
    for record in audit_records:
        (paper_dir / f"{record['record_id']}.md").write_text(
            paper_audit_text(record),
            encoding="utf-8",
        )


def run_audit(
    repo_root: Path | str = Path("."),
    *,
    coverage_path: Path = COVERAGE_PATH,
    audit_dir: Path = AUDIT_DIR,
    artifact_dir: Path = ARTIFACT_DIR,
    parse_downloaded: bool = True,
) -> dict[str, Any]:
    paths = resolve_paths(Path(repo_root), coverage_path, audit_dir, artifact_dir)
    ensure_directories(paths)
    coverage = load_json(paths.coverage_path)
    records = list(coverage["literature_records"])
    environment = detect_environment(paths.repo_root)
    extraction_log = extract_downloaded_pdfs(records, paths) if parse_downloaded else {}
    supplement_extraction_log = extract_downloaded_supplements(records, paths)
    audit_records, missing_requests = build_records(records, paths, extraction_log, supplement_extraction_log)
    summary = summary_from_records(audit_records, missing_requests)
    write_audit_files(audit_records, missing_requests, summary, environment, paths)
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inventory and scaffold paper metadata extraction for audio-tactile PPS publications."
    )
    parser.add_argument("--repo-root", type=Path, default=Path("."), help="Repository root.")
    parser.add_argument("--coverage-path", type=Path, default=COVERAGE_PATH, help="Literature coverage JSON path.")
    parser.add_argument("--audit-dir", type=Path, default=AUDIT_DIR, help="Tracked audit output folder.")
    parser.add_argument("--artifact-dir", type=Path, default=ARTIFACT_DIR, help="Ignored local artifact folder.")
    parser.add_argument(
        "--no-parse-downloaded",
        action="store_true",
        help="Only inventory PDFs/supplements; do not extract downloaded PDFs.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh audit files. Kept explicit for readable command history.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    summary = run_audit(
        args.repo_root,
        coverage_path=args.coverage_path,
        audit_dir=args.audit_dir,
        artifact_dir=args.artifact_dir,
        parse_downloaded=not args.no_parse_downloaded,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=True))
    return 0
