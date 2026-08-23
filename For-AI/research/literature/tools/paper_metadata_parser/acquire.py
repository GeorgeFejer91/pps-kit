from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import ssl
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urljoin, urlparse
from urllib.request import Request, urlopen

from .parser import ADJACENT_CATEGORY, ARTIFACT_DIR, COVERAGE_PATH, PDF_DIR, SUPPLEMENT_DIR, is_valid_pdf


USER_AGENT = "PPSKitPaperMetadataAudit/0.1 (+https://github.com/GeorgeFejer91/pps-kit)"
MAX_DOWNLOAD_BYTES = 80 * 1024 * 1024
SUPPLEMENT_EXTENSIONS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ods", ".csv", ".zip")
SUPPLEMENT_LINK_TERMS = (
    "supplement",
    "supplemental",
    "supplementary",
    "supporting information",
    "supporting material",
    "additional file",
    "appendix",
    "extended data",
    "moesm",
    "esm",
    "s1",
)
HTML_LINK_RE = re.compile(
    r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
TAG_RE = re.compile(r"<[^>]+>")


def normalize_doi(value: str) -> str:
    doi = (value or "").strip().lower()
    doi = doi.removeprefix("https://doi.org/")
    doi = doi.removeprefix("http://doi.org/")
    doi = doi.removeprefix("doi:")
    return doi.strip()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_dicts(child)


def candidate(label: str, url: str) -> dict[str, str]:
    return {"source": label, "url": url}


def source_url_candidates(repo_root: Path, record: dict[str, Any]) -> list[dict[str, str]]:
    record_id = record["record_id"]
    candidates: list[dict[str, str]] = []

    for template_id in record.get("current_template_ids", []):
        template_path = repo_root / "study_templates" / f"{template_id}.json"
        if template_path.exists():
            template = load_json(template_path)
            url = template.get("source_url", "")
            if url:
                candidates.append(candidate(f"study_template:{template_id}", url))

    preload_root = repo_root / "assets" / "preloads"
    for path in preload_root.glob("audiotactile_*screening.json"):
        try:
            payload = load_json(path)
        except json.JSONDecodeError:
            continue
        for item in walk_dicts(payload):
            linked = item.get("linked_literature_record_ids")
            if isinstance(linked, list) and record_id in linked:
                for key in ("source_url", "url", "pdf_url", "landing_page_url"):
                    url = item.get(key)
                    if isinstance(url, str) and url.startswith(("http://", "https://")):
                        candidates.append(candidate(path.name, url))

    return candidates


def openalex_pdf_candidates_from_obj(obj: dict[str, Any], doi: str) -> list[dict[str, str]]:
    obj_doi = normalize_doi(str(obj.get("doi", "")))
    if obj_doi != doi:
        return []
    candidates: list[dict[str, str]] = []
    for location_key in ("primary_location", "best_oa_location"):
        location = obj.get(location_key)
        if isinstance(location, dict):
            pdf_url = location.get("pdf_url")
            if isinstance(pdf_url, str) and pdf_url.startswith(("http://", "https://")):
                candidates.append(candidate(f"openalex:{location_key}", pdf_url))
    for location in obj.get("locations", []) if isinstance(obj.get("locations"), list) else []:
        if isinstance(location, dict):
            pdf_url = location.get("pdf_url")
            if isinstance(pdf_url, str) and pdf_url.startswith(("http://", "https://")):
                candidates.append(candidate("openalex:location", pdf_url))
    open_access = obj.get("open_access")
    if isinstance(open_access, dict):
        oa_url = open_access.get("oa_url")
        if isinstance(oa_url, str) and oa_url.lower().endswith(".pdf"):
            candidates.append(candidate("openalex:oa_url", oa_url))
    return candidates


def cached_openalex_candidates(repo_root: Path, doi: str) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    cache_dir = repo_root / "artifacts" / "literature_audit"
    for path in cache_dir.glob("openalex*.json"):
        try:
            payload = load_json(path)
        except json.JSONDecodeError:
            continue
        for obj in walk_dicts(payload):
            candidates.extend(openalex_pdf_candidates_from_obj(obj, doi))
    return candidates


def fetch_json(url: str, timeout: float = 12.0) -> dict[str, Any] | None:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ssl.SSLError):
        return None


def live_openalex_candidates(doi: str) -> tuple[list[dict[str, str]], bool | None]:
    if not doi:
        return [], None
    url = f"https://api.openalex.org/works/doi:{quote(doi, safe='')}"
    payload = fetch_json(url)
    if not payload:
        return [], None
    is_oa = None
    open_access = payload.get("open_access")
    if isinstance(open_access, dict):
        is_oa = bool(open_access.get("is_oa"))
    return openalex_pdf_candidates_from_obj(payload, doi), is_oa


def predictable_pdf_candidates(doi: str) -> list[dict[str, str]]:
    if not doi:
        return []
    candidates: list[dict[str, str]] = []
    if doi.startswith("10.1371/journal.pone."):
        candidates.append(candidate("publisher:plos-printable", f"https://journals.plos.org/plosone/article/file?id={doi}&type=printable"))
    if doi.startswith("10.1038/"):
        article_id = doi.split("/", 1)[1]
        candidates.append(candidate("publisher:nature-pdf", f"https://www.nature.com/articles/{article_id}.pdf"))
    if doi.startswith("10.3389/"):
        candidates.append(candidate("publisher:frontiers-pdf", f"https://www.frontiersin.org/articles/{doi}/pdf"))
    if doi.startswith("10.1073/pnas."):
        candidates.append(candidate("publisher:pnas-pdf", f"https://www.pnas.org/doi/pdf/{doi}"))
    if doi.startswith("10.1098/"):
        candidates.append(candidate("publisher:royal-society-pdf", f"https://royalsocietypublishing.org/doi/pdf/{doi}"))
    if doi.startswith("10.1523/"):
        candidates.append(candidate("publisher:jneurosci-doi-pdf", f"https://www.jneurosci.org/doi/pdf/{doi}"))
    if doi.startswith("10.3390/"):
        candidates.append(candidate("publisher:mdpi-doi-pdf", f"https://www.mdpi.com/{doi}/pdf"))
    if doi.startswith("10.61782/fa.2025.0866"):
        candidates.append(candidate("web-sanity:euracoustics-pdf", "https://dael.euracoustics.org/confs/fa2025/data/articles/000866.pdf"))
    return candidates


def unique_candidates(candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for item in candidates:
        url = item["url"].strip()
        if not url or url in seen:
            continue
        seen.add(url)
        unique.append({"source": item["source"], "url": url})
    return unique


def looks_like_pdf(data: bytes) -> bool:
    return b"%PDF-" in data[:1024]


def download_url(url: str, destination: Path, timeout: float = 30.0) -> tuple[bool, str]:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/pdf,application/octet-stream,*/*;q=0.8",
        },
    )
    try:
        with urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
            status = getattr(response, "status", 200)
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    return False, "download_too_large"
                chunks.append(chunk)
            data = b"".join(chunks)
    except HTTPError as exc:
        return False, f"http_{exc.code}"
    except (URLError, TimeoutError, ssl.SSLError) as exc:
        return False, f"network_error:{exc.__class__.__name__}"
    if status >= 400:
        return False, f"http_{status}"
    if not looks_like_pdf(data):
        parsed = urlparse(url)
        hint = parsed.path.rsplit("/", 1)[-1] or parsed.netloc
        return False, f"not_pdf:{hint[:80]}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(".tmp")
    tmp.write_bytes(data)
    if not is_valid_pdf(tmp):
        tmp.unlink(missing_ok=True)
        return False, "bad_pdf_after_write"
    tmp.replace(destination)
    return True, "downloaded"


def fetch_text(url: str, timeout: float = 8.0) -> tuple[str, str]:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        },
    )
    try:
        with urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
            status = getattr(response, "status", 200)
            data = response.read(2 * 1024 * 1024)
            charset = response.headers.get_content_charset() or "utf-8"
            text = data.decode(charset, errors="replace")
    except HTTPError as exc:
        return "", f"http_{exc.code}"
    except (URLError, TimeoutError, ssl.SSLError) as exc:
        return "", f"network_error:{exc.__class__.__name__}"
    if status >= 400:
        return "", f"http_{status}"
    return text, "fetched"


def clean_link_text(value: str) -> str:
    without_tags = TAG_RE.sub(" ", value)
    return " ".join(html.unescape(without_tags).split())


def looks_like_supplement_link(url: str, link_text: str = "") -> bool:
    parsed = urlparse(url)
    haystack = f"{unquote(parsed.path)} {unquote(parsed.query)} {link_text}".lower()
    suffix = Path(parsed.path).suffix.lower()
    if suffix in SUPPLEMENT_EXTENSIONS:
        return any(term in haystack for term in SUPPLEMENT_LINK_TERMS) or suffix != ".pdf"
    return any(term in haystack for term in SUPPLEMENT_LINK_TERMS)


def html_supplement_candidates(page_url: str, html_text: str, source_label: str) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for match in HTML_LINK_RE.finditer(html_text):
        href, label_html = match.groups()
        absolute = urljoin(page_url, html.unescape(href).strip())
        if not absolute.startswith(("http://", "https://")):
            continue
        label = clean_link_text(label_html)
        if looks_like_supplement_link(absolute, label):
            candidates.append(candidate(source_label, absolute))
    return candidates


def crossref_supplement_candidates(doi: str) -> list[dict[str, str]]:
    if not doi:
        return []
    payload = fetch_json(f"https://api.crossref.org/works/{quote(doi, safe='')}")
    if not payload:
        return []
    message = payload.get("message", {})
    candidates: list[dict[str, str]] = []
    for link in message.get("link", []) if isinstance(message, dict) else []:
        if not isinstance(link, dict):
            continue
        url = link.get("URL")
        content_type = str(link.get("content-type", "")).lower()
        intended = str(link.get("intended-application", "")).lower()
        descriptor = f"{content_type} {intended}"
        if isinstance(url, str) and url.startswith(("http://", "https://")) and (
            any(term in descriptor for term in ("supplement", "support", "component"))
            or looks_like_supplement_link(url, descriptor)
        ):
            candidates.append(candidate("crossref:link", url))
    return candidates


def doi_landing_candidates(doi: str) -> list[dict[str, str]]:
    if not doi:
        return []
    return [candidate("doi:landing", f"https://doi.org/{doi}")]


def predictable_supplement_page_candidates(doi: str) -> list[dict[str, str]]:
    if not doi:
        return []
    candidates: list[dict[str, str]] = []
    if doi.startswith("10.1038/"):
        article_id = doi.split("/", 1)[1]
        candidates.append(candidate("publisher:nature-article", f"https://www.nature.com/articles/{article_id}"))
    if doi.startswith("10.3389/"):
        candidates.append(candidate("publisher:frontiers-article", f"https://www.frontiersin.org/articles/{doi}/full"))
    if doi.startswith("10.1073/pnas."):
        candidates.append(candidate("publisher:pnas-article", f"https://www.pnas.org/doi/full/{doi}"))
    if doi.startswith("10.1098/"):
        candidates.append(candidate("publisher:royal-society-article", f"https://royalsocietypublishing.org/doi/full/{doi}"))
    if doi.startswith("10.1523/"):
        candidates.append(candidate("publisher:jneurosci-article", f"https://www.jneurosci.org/content/lookup/doi/{doi}"))
    if doi.startswith("10.3390/"):
        candidates.append(candidate("publisher:mdpi-article", f"https://www.mdpi.com/{doi}"))
    if doi.startswith("10.1371/journal.pone."):
        candidates.append(candidate("publisher:plos-article", f"https://journals.plos.org/plosone/article?id={doi}"))
    return candidates


def supplement_page_candidates(repo_root: Path, record: dict[str, Any], doi: str) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    candidates.extend(source_url_candidates(repo_root, record))
    candidates.extend(doi_landing_candidates(doi))
    candidates.extend(predictable_supplement_page_candidates(doi))
    candidates.extend(crossref_supplement_candidates(doi))
    return unique_candidates(candidates)


def extension_from_content_type(content_type: str) -> str:
    lower = content_type.lower()
    if "pdf" in lower:
        return ".pdf"
    if "word" in lower or "officedocument.wordprocessingml" in lower:
        return ".docx"
    if "excel" in lower or "spreadsheetml" in lower:
        return ".xlsx"
    if "opendocument" in lower:
        return ".ods"
    if "zip" in lower:
        return ".zip"
    if "csv" in lower:
        return ".csv"
    return ""


def safe_supplement_filename(url: str, content_type: str, index: int) -> str:
    parsed = urlparse(url)
    raw_name = unquote(Path(parsed.path).name)
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_name).strip("._")
    suffix = Path(name).suffix.lower()
    if suffix not in SUPPLEMENT_EXTENSIONS:
        suffix = extension_from_content_type(content_type)
        stem = Path(name).stem if name else f"supplement_{index:02d}"
        name = f"{stem or f'supplement_{index:02d}'}{suffix}"
    if not suffix:
        name = f"supplement_{index:02d}.bin"
    return name[:120]


def download_supplement_url(url: str, destination_dir: Path, index: int, timeout: float = 20.0) -> tuple[bool, str, str]:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/pdf,application/zip,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.*,application/msword,text/csv,*/*;q=0.8",
        },
    )
    try:
        with urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
            status = getattr(response, "status", 200)
            content_type = response.headers.get("Content-Type", "")
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    return False, "download_too_large", ""
                chunks.append(chunk)
            data = b"".join(chunks)
    except HTTPError as exc:
        return False, f"http_{exc.code}", ""
    except (URLError, TimeoutError, ssl.SSLError) as exc:
        return False, f"network_error:{exc.__class__.__name__}", ""
    if status >= 400:
        return False, f"http_{status}", ""
    if content_type.lower().startswith("text/html") or data.lstrip()[:20].lower().startswith(b"<!doctype html"):
        return False, "not_file_html", ""
    filename = safe_supplement_filename(url, content_type, index)
    if filename.endswith(".bin"):
        return False, "not_recognized_supplement_file", ""
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / filename
    tmp = destination.with_suffix(destination.suffix + ".tmp")
    tmp.write_bytes(data)
    if destination.suffix.lower() == ".pdf" and not is_valid_pdf(tmp):
        tmp.unlink(missing_ok=True)
        return False, "bad_pdf_after_write", ""
    tmp.replace(destination)
    return True, "downloaded", destination.as_posix()


def acquire_supplements_for_record(repo_root: Path, record: dict[str, Any]) -> dict[str, Any]:
    record_id = record["record_id"]
    doi = normalize_doi(record.get("doi", ""))
    destination_dir = repo_root / SUPPLEMENT_DIR / record_id
    existing_files = sorted(path for path in destination_dir.rglob("*") if path.is_file()) if destination_dir.exists() else []
    if existing_files:
        return {
            "record_id": record_id,
            "doi": doi,
            "supplement_status": "downloaded",
            "last_status": "existing_files",
            "attempt_count": 0,
            "downloaded_files": [path.relative_to(repo_root).as_posix() for path in existing_files],
            "attempts": [],
        }

    page_candidates = supplement_page_candidates(repo_root, record, doi)
    supplement_candidates: list[dict[str, str]] = []
    attempts: list[dict[str, str]] = []
    for page in page_candidates:
        url = page["url"]
        if looks_like_supplement_link(url):
            supplement_candidates.append(page)
            attempts.append({"source": page["source"], "url": url, "status": "direct_candidate"})
            continue
        html_text, status = fetch_text(url)
        attempts.append({"source": page["source"], "url": url, "status": status})
        if html_text:
            supplement_candidates.extend(html_supplement_candidates(url, html_text, page["source"]))
        time.sleep(0.1)

    supplement_candidates = unique_candidates(supplement_candidates)
    downloaded_files: list[str] = []
    for index, item in enumerate(supplement_candidates, start=1):
        ok, status, saved_path = download_supplement_url(item["url"], destination_dir, index)
        attempts.append({"source": item["source"], "url": item["url"], "status": status})
        if ok:
            downloaded_files.append(Path(saved_path).relative_to(repo_root).as_posix())
        time.sleep(0.1)

    if downloaded_files:
        supplement_status = "downloaded"
        last_status = "downloaded"
    elif supplement_candidates:
        supplement_status = "needs_user_download"
        last_status = attempts[-1]["status"] if attempts else "candidate_download_failed"
    elif any(attempt["status"] in {"http_401", "http_403"} for attempt in attempts):
        supplement_status = "paywalled"
        last_status = "supplement_routes_access_limited"
    elif not attempts:
        supplement_status = "not_checked"
        last_status = "no_supplement_search_routes"
    else:
        supplement_status = "not_found"
        last_status = "checked_no_supplement_candidates"
    return {
        "record_id": record_id,
        "doi": doi,
        "supplement_status": supplement_status,
        "last_status": last_status,
        "attempt_count": len(attempts),
        "downloaded_files": downloaded_files,
        "attempts": attempts,
    }


def copy_existing_holmes_supplements(repo_root: Path, target_root: Path) -> int:
    source_root = repo_root / "artifacts" / "literature_audit"
    target = target_root / "holmes_2020_four_experiments"
    copied = 0
    for source in source_root.glob("holmes_2020_MOESM*"):
        if source.is_file():
            target.mkdir(parents=True, exist_ok=True)
            dest = target / source.name
            if not dest.exists():
                shutil.copy2(source, dest)
                copied += 1
    return copied


def acquire_for_record(repo_root: Path, record: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    record_id = record["record_id"]
    doi = normalize_doi(record.get("doi", ""))
    destination = repo_root / PDF_DIR / f"{record_id}.pdf"
    if record["coverage_category"] == ADJACENT_CATEGORY:
        return {
            "record_id": record_id,
            "doi": doi,
            "pdf_status": "not_applicable",
            "last_status": "not_applicable",
            "attempt_count": 0,
            "downloaded_url": "",
            "attempts": [],
        }
    if destination.exists() and is_valid_pdf(destination) and not force:
        return {
            "record_id": record_id,
            "doi": doi,
            "pdf_status": "downloaded",
            "last_status": "existing_valid_pdf",
            "attempt_count": 0,
            "downloaded_url": "",
            "attempts": [],
        }

    candidates = []
    candidates.extend(source_url_candidates(repo_root, record))
    candidates.extend(cached_openalex_candidates(repo_root, doi))
    live_candidates, openalex_is_oa = live_openalex_candidates(doi)
    candidates.extend(live_candidates)
    candidates.extend(predictable_pdf_candidates(doi))
    candidates = unique_candidates(candidates)

    attempts: list[dict[str, str]] = []
    for item in candidates:
        ok, status = download_url(item["url"], destination)
        attempts.append({"source": item["source"], "url": item["url"], "status": status})
        if ok:
            return {
                "record_id": record_id,
                "doi": doi,
                "pdf_status": "downloaded",
                "last_status": status,
                "attempt_count": len(attempts),
                "downloaded_url": item["url"],
                "attempts": attempts,
            }
        time.sleep(0.2)

    if doi and openalex_is_oa is False:
        pdf_status = "paywalled"
        last_status = "openalex_not_oa"
    elif not candidates:
        pdf_status = "open_access_unavailable"
        last_status = "no_oa_pdf_candidates"
    else:
        pdf_status = "needs_user_download"
        last_status = attempts[-1]["status"] if attempts else "no_successful_download"
    return {
        "record_id": record_id,
        "doi": doi,
        "pdf_status": pdf_status,
        "last_status": last_status,
        "attempt_count": len(attempts),
        "downloaded_url": "",
        "attempts": attempts,
    }


def run_acquisition(repo_root: Path, *, force: bool = False, limit: int | None = None) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc).isoformat()
    coverage = load_json(repo_root / COVERAGE_PATH)
    records = [
        record for record in coverage["literature_records"]
        if record["coverage_category"] != ADJACENT_CATEGORY
    ]
    if limit is not None:
        records = records[:limit]
    copied_supplements = copy_existing_holmes_supplements(repo_root, repo_root / SUPPLEMENT_DIR)
    results = []
    for record in records:
        result = acquire_for_record(repo_root, record, force=force)
        result["supplement_acquisition"] = acquire_supplements_for_record(repo_root, record)
        results.append(result)

    counts: dict[str, int] = {}
    supplement_counts: dict[str, int] = {}
    for result in results:
        counts[result["pdf_status"]] = counts.get(result["pdf_status"], 0) + 1
        supplement_status = result.get("supplement_acquisition", {}).get("supplement_status", "not_checked")
        supplement_counts[supplement_status] = supplement_counts.get(supplement_status, 0) + 1
    payload = {
        "schema": "pps-paper-metadata-acquisition-status.v1",
        "generated_on": date.today().isoformat(),
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "source_count": len(records),
        "pdf_status_counts": dict(sorted(counts.items())),
        "supplement_status_counts": dict(sorted(supplement_counts.items())),
        "copied_existing_holmes_supplement_count": copied_supplements,
        "records": results,
    }
    write_json(repo_root / ARTIFACT_DIR / "acquisition_status.json", payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download legally reachable open-access PDFs for the paper metadata audit.")
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--force", action="store_true", help="Retry and overwrite existing valid PDFs.")
    parser.add_argument("--limit", type=int, default=None, help="Limit records for a quick smoke run.")
    parser.add_argument("--verbose", action="store_true", help="Print the full acquisition ledger instead of a summary.")
    args = parser.parse_args(argv)
    payload = run_acquisition(args.repo_root.resolve(), force=args.force, limit=args.limit)
    if args.verbose:
        print(json.dumps(payload, indent=2, ensure_ascii=True))
    else:
        summary = {
            "source_count": payload["source_count"],
            "pdf_status_counts": payload["pdf_status_counts"],
            "supplement_status_counts": payload["supplement_status_counts"],
            "copied_existing_holmes_supplement_count": payload["copied_existing_holmes_supplement_count"],
        }
        print(json.dumps(summary, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
