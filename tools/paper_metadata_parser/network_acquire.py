"""Public/OA-only acquisition for the DOI-deduplicated citation network.

The module deliberately has no authenticated publisher-session, cookie, proxy,
or access-control bypass support. Raw PDFs and its resumable ledger live only
under the repository's ignored paper-audit artifact tree.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import ssl
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from http.client import HTTPException
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from .parser import ARTIFACT_DIR, PDF_DIR


NETWORK_PATH = Path("src/peripersonal_space_toolkit/dashboard/publication_network.v3.json")
NETWORK_ACQUISITION_STATUS_PATH = ARTIFACT_DIR / "network_acquisition_status.json"
PAPER_PDF_SOURCE_OVERRIDES_PATH = Path("tools/paper_pdf_source_overrides.json")
PAPER_PDF_SOURCE_OVERRIDES_SCHEMA = "pps-paper-pdf-source-overrides.v1"
USER_AGENT = "PPSKitPaperAcquisition/0.2 (+https://github.com/GeorgeFejer91/pps-kit)"
MAX_DOWNLOAD_BYTES = 80 * 1024 * 1024
MAX_RETRY_AFTER_SECONDS = 30.0
RETRYABLE_HTTP_STATUSES = {429, 500, 502, 503, 504}
VERIFIED_IDENTITY_STATUSES = frozenset({"doi_and_title_match", "doi_match", "title_match"})
TITLE_STOPWORDS = {
    "about",
    "after",
    "among",
    "around",
    "between",
    "from",
    "into",
    "near",
    "peripersonal",
    "space",
    "study",
    "that",
    "their",
    "this",
    "through",
    "using",
    "with",
}


def normalize_doi(value: str) -> str:
    doi = (value or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.startswith(prefix):
            doi = doi[len(prefix) :]
    return doi.strip().rstrip(". ")


def doi_pdf_filename(doi: str) -> str:
    normalized = normalize_doi(doi)
    if not normalized:
        raise ValueError("A DOI is required for a network publication PDF filename.")
    readable = re.sub(r"[^a-z0-9._-]+", "_", normalized).strip("._-")[:84]
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    return f"doi_{readable}__{digest}.pdf"


def normalize_http_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"}:
        return value.strip()
    path = quote(parsed.path, safe="/%:@!$&'()*+,;=-._~")
    query = quote(parsed.query, safe="=&%:@!$'()*+,;/?-._~")
    return urlunparse(parsed._replace(path=path, query=query, fragment=""))


def _candidate(source: str, url: str, *, kind: str = "unknown", license_value: str = "", evidence: str = "") -> dict[str, str]:
    return {
        "source": source,
        "url": url,
        "kind": kind,
        "license": license_value or "",
        "access_evidence": evidence or source,
    }


def _candidate_kind(url: str) -> str:
    parsed = urlparse(url.lower())
    haystack = f"{parsed.path}?{parsed.query}"
    if (
        parsed.path.endswith(".pdf")
        or parsed.path.endswith("/_pdf")
        or "/pdf" in parsed.path
        or "pdf=render" in parsed.query
        or parsed.path.endswith("/download")
        or "show_pdf" in parsed.query
    ):
        return "direct"
    return "landing"


def _pmcid_from_url(url: str) -> str:
    parsed = urlparse(url)
    match = re.search(r"/(?:pmc/)?articles/(?:PMC)?(\d+)(?:[/?]|$)", parsed.path, re.IGNORECASE)
    if match:
        return f"PMC{match.group(1)}"
    match = re.search(r"/(PMC\d+)(?:[/?]|$)", parsed.path, re.IGNORECASE)
    return match.group(1).upper() if match else ""


def is_prohibited_pmc_presentation_pdf_url(url: str) -> bool:
    parsed = urlparse(url.lower())
    if parsed.netloc in {"europepmc.org", "www.europepmc.org"}:
        return bool(re.search(r"/articles/(?:pmc)?\d+", parsed.path))
    if parsed.netloc in {"pmc.ncbi.nlm.nih.gov", "www.pmc.ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov"}:
        return bool(re.search(r"/(?:pmc/)?articles/(?:pmc)?\d+", parsed.path))
    return False


def unique_candidates(candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for item in candidates:
        url = normalize_http_url(str(item.get("url", "")))
        if (
            not url.startswith(("http://", "https://"))
            or url in seen
            or is_prohibited_pmc_presentation_pdf_url(url)
        ):
            continue
        seen.add(url)
        normalized = dict(item)
        normalized["url"] = url
        if normalized.get("kind") not in {"direct", "landing"}:
            normalized["kind"] = _candidate_kind(url)
        result.append(normalized)
    return result


def load_pdf_source_overrides(
    repo_root: Path,
    network_dois: set[str],
    override_path: Path = PAPER_PDF_SOURCE_OVERRIDES_PATH,
) -> dict[str, dict[str, str]]:
    """Load reviewed anonymous PDF routes and reject ambiguous manifest entries."""

    path = override_path if override_path.is_absolute() else repo_root / override_path
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != PAPER_PDF_SOURCE_OVERRIDES_SCHEMA:
        raise ValueError(f"Unsupported PDF source override schema: {payload.get('schema')!r}")
    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise ValueError(f"PDF source override manifest has no source list: {path}")

    expected_dois = {normalize_doi(value) for value in network_dois if normalize_doi(value)}
    overrides: dict[str, dict[str, str]] = {}
    for index, item in enumerate(sources):
        if not isinstance(item, dict):
            raise ValueError(f"PDF source override {index} is not an object: {path}")
        doi = normalize_doi(str(item.get("doi", "")))
        url = normalize_http_url(str(item.get("url", "")))
        source_type = str(item.get("source_type", "")).strip()
        evidence = str(item.get("evidence", "")).strip()
        notes = str(item.get("notes", "")).strip()
        if not doi or doi not in expected_dois:
            raise ValueError(f"PDF source override DOI is absent from the current network: {doi or '<missing>'}")
        if doi in overrides:
            raise ValueError(f"Duplicate PDF source override DOI: {doi}")
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError(f"PDF source override must use an absolute HTTPS URL: {doi}")
        if is_prohibited_pmc_presentation_pdf_url(url):
            raise ValueError(f"PDF source override uses a prohibited PMC presentation route: {doi}")
        if not source_type or not evidence:
            raise ValueError(f"PDF source override requires source_type and evidence: {doi}")
        overrides[doi] = {
            "doi": doi,
            "url": url,
            "source_type": source_type,
            "evidence": evidence,
            "notes": notes,
        }
    return overrides


def load_network_records(repo_root: Path, network_path: Path = NETWORK_PATH) -> list[dict[str, Any]]:
    path = network_path if network_path.is_absolute() else repo_root / network_path
    payload = json.loads(path.read_text(encoding="utf-8"))
    nodes = payload.get("nodes")
    if not isinstance(nodes, list):
        raise ValueError(f"Publication network has no node list: {path}")

    records_by_doi: dict[str, dict[str, Any]] = {}
    missing_doi: list[str] = []
    for node in nodes:
        doi = normalize_doi(str(node.get("doi", "")))
        if not doi:
            missing_doi.append(str(node.get("id", "unknown")))
            continue
        links = node.get("links") if isinstance(node.get("links"), dict) else {}
        toolkit = node.get("toolkit") if isinstance(node.get("toolkit"), dict) else {}
        toolkit_records = toolkit.get("records") if isinstance(toolkit.get("records"), list) else []
        audit_record_ids = sorted(
            {
                str(item.get("recordId"))
                for item in toolkit_records
                if isinstance(item, dict) and item.get("recordId")
            }
        )
        oa_url = str(links.get("openAccess", "")).strip()
        stored_pmcid = _pmcid_from_url(oa_url)
        record = {
            "record_id": f"network_{hashlib.sha256(doi.encode('utf-8')).hexdigest()[:16]}",
            "publication_id": str(node.get("id", f"doi:{doi}")),
            "doi": doi,
            "title": str(node.get("title", "")).strip(),
            "year": node.get("year"),
            "pmid": str(node.get("pmid", "")).strip(),
            "openalex_ids": sorted(str(value) for value in node.get("openAlexIds", []) if value),
            "semantic_scholar_ids": sorted(str(value) for value in node.get("semanticScholarIds", []) if value),
            "audit_record_ids": audit_record_ids,
            "open_access_urls": (
                [oa_url]
                if oa_url.startswith(("http://", "https://"))
                and not is_prohibited_pmc_presentation_pdf_url(oa_url)
                else []
            ),
            "pmcids": [stored_pmcid] if stored_pmcid else [],
            "destination_filename": doi_pdf_filename(doi),
        }
        previous = records_by_doi.get(doi)
        if previous is None:
            records_by_doi[doi] = record
        else:
            previous["open_access_urls"] = sorted(set(previous["open_access_urls"] + record["open_access_urls"]))
            previous["audit_record_ids"] = sorted(set(previous["audit_record_ids"] + record["audit_record_ids"]))
            previous["openalex_ids"] = sorted(set(previous["openalex_ids"] + record["openalex_ids"]))
            previous["semantic_scholar_ids"] = sorted(
                set(previous["semantic_scholar_ids"] + record["semantic_scholar_ids"])
            )
            previous["pmcids"] = sorted(set(previous["pmcids"] + record["pmcids"]))

    if missing_doi:
        raise ValueError(f"Network acquisition requires DOI-bearing nodes; missing DOI for: {', '.join(missing_doi)}")
    return [records_by_doi[doi] for doi in sorted(records_by_doi)]


@dataclass
class FetchResult:
    ok: bool
    status: str
    status_code: int | None = None
    data: bytes = b""
    content_type: str = ""
    final_url: str = ""
    attempts: int = 0


class PoliteHttpClient:
    def __init__(
        self,
        *,
        delay_seconds: float = 1.0,
        max_retries: int = 3,
        timeout: float = 30.0,
        opener: Callable[..., Any] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        monotonic_fn: Callable[[], float] | None = None,
    ) -> None:
        if delay_seconds < 0:
            raise ValueError("delay_seconds must be non-negative")
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        self.delay_seconds = delay_seconds
        self.max_retries = max_retries
        self.timeout = timeout
        self.opener = opener or urlopen
        self.sleep_fn = sleep_fn or time.sleep
        self.monotonic_fn = monotonic_fn or time.monotonic
        self._last_request_at: float | None = None

    def _throttle(self) -> None:
        now = self.monotonic_fn()
        if self._last_request_at is not None:
            remaining = self.delay_seconds - (now - self._last_request_at)
            if remaining > 0:
                self.sleep_fn(remaining)
                now = self.monotonic_fn()
        self._last_request_at = now

    @staticmethod
    def _retry_after(headers: Any) -> float | None:
        value = headers.get("Retry-After") if headers is not None else None
        if not value:
            return None
        try:
            return min(MAX_RETRY_AFTER_SECONDS, max(0.0, float(value)))
        except (TypeError, ValueError):
            try:
                parsed = parsedate_to_datetime(str(value))
                seconds = (parsed - datetime.now(parsed.tzinfo or timezone.utc)).total_seconds()
                return min(MAX_RETRY_AFTER_SECONDS, max(0.0, seconds))
            except (TypeError, ValueError, OverflowError):
                return None

    def get(
        self,
        url: str,
        *,
        accept: str,
        headers: dict[str, str] | None = None,
        max_bytes: int = MAX_DOWNLOAD_BYTES,
    ) -> FetchResult:
        url = normalize_http_url(url)
        request_headers = {"User-Agent": USER_AGENT, "Accept": accept}
        request_headers.update(headers or {})
        try:
            request = Request(url, headers=request_headers)
        except ValueError:
            return FetchResult(False, "invalid_url", attempts=0)
        last_status = "not_attempted"
        for attempt_index in range(self.max_retries + 1):
            self._throttle()
            try:
                with self.opener(
                    request,
                    timeout=self.timeout,
                    context=ssl.create_default_context(),
                ) as response:
                    status_code = int(getattr(response, "status", 200))
                    content_length = response.headers.get("Content-Length")
                    if content_length:
                        try:
                            if int(content_length) > max_bytes:
                                return FetchResult(False, "download_too_large", status_code=status_code, attempts=attempt_index + 1)
                        except ValueError:
                            pass
                    chunks: list[bytes] = []
                    total = 0
                    while True:
                        chunk = response.read(256 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > max_bytes:
                            return FetchResult(False, "download_too_large", status_code=status_code, attempts=attempt_index + 1)
                        chunks.append(chunk)
                    return FetchResult(
                        True,
                        "fetched",
                        status_code=status_code,
                        data=b"".join(chunks),
                        content_type=str(response.headers.get("Content-Type", "")),
                        final_url=str(response.geturl() if hasattr(response, "geturl") else url),
                        attempts=attempt_index + 1,
                    )
            except HTTPError as exc:
                last_status = f"http_{exc.code}"
                if exc.code not in RETRYABLE_HTTP_STATUSES or attempt_index >= self.max_retries:
                    return FetchResult(False, last_status, status_code=exc.code, attempts=attempt_index + 1)
                retry_after = self._retry_after(exc.headers)
                self.sleep_fn(retry_after if retry_after is not None else min(8.0, 0.5 * (2**attempt_index)))
            except (URLError, TimeoutError, ssl.SSLError, ConnectionError, OSError, HTTPException) as exc:
                last_status = f"network_error:{exc.__class__.__name__}"
                if attempt_index >= self.max_retries:
                    return FetchResult(False, last_status, attempts=attempt_index + 1)
                self.sleep_fn(min(8.0, 0.5 * (2**attempt_index)))
        return FetchResult(False, last_status, attempts=self.max_retries + 1)


def _redact_query(url: str, sensitive_keys: set[str] | None = None) -> str:
    sensitive_keys = sensitive_keys or {
        "email",
        "mailto",
        "api_key",
        "apikey",
        "access_token",
        "token",
        "x-amz-credential",
        "x-amz-security-token",
        "x-amz-signature",
        "x-goog-credential",
        "x-goog-signature",
    }
    parsed = urlparse(url)
    query = [
        (key, "[redacted]" if key.lower() in sensitive_keys else value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    return urlunparse(parsed._replace(query=urlencode(query)))


def _sanitize_ledger_value(value: Any) -> Any:
    """Redact credentials from URLs before a resumable ledger is persisted."""
    if isinstance(value, dict):
        return {key: _sanitize_ledger_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_ledger_value(item) for item in value]
    if isinstance(value, str) and value.lower().startswith(("http://", "https://")):
        return _redact_query(value)
    return value


def _fetch_json(client: PoliteHttpClient, url: str, source: str, *, headers: dict[str, str] | None = None) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    response = client.get(url, accept="application/json", headers=headers, max_bytes=8 * 1024 * 1024)
    ledger = {
        "source": source,
        "url": _redact_query(url),
        "status": response.status,
        "http_attempt_count": response.attempts,
    }
    if not response.ok:
        return None, ledger
    try:
        payload = json.loads(response.data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        ledger["status"] = "invalid_json"
        return None, ledger
    ledger["status"] = "fetched"
    return payload if isinstance(payload, dict) else None, ledger


def _openalex_candidates(payload: dict[str, Any], doi: str) -> list[dict[str, str]]:
    if normalize_doi(str(payload.get("doi", ""))) != doi:
        return []
    candidates: list[dict[str, str]] = []
    locations: list[tuple[str, dict[str, Any]]] = []
    for key in ("best_oa_location", "primary_location"):
        value = payload.get(key)
        if isinstance(value, dict):
            locations.append((key, value))
    for value in payload.get("locations", []) if isinstance(payload.get("locations"), list) else []:
        if isinstance(value, dict):
            locations.append(("location", value))
    for label, location in locations:
        if location.get("is_oa") is False:
            continue
        license_value = str(location.get("license") or "")
        pdf_url = location.get("pdf_url")
        if isinstance(pdf_url, str):
            candidates.append(_candidate(f"openalex:{label}", pdf_url, kind="direct", license_value=license_value, evidence="OpenAlex OA location"))
        landing_url = location.get("landing_page_url")
        if isinstance(landing_url, str):
            candidates.append(_candidate(f"openalex:{label}:landing", landing_url, kind="landing", license_value=license_value, evidence="OpenAlex OA location"))
    open_access = payload.get("open_access")
    if isinstance(open_access, dict) and open_access.get("is_oa"):
        oa_url = open_access.get("oa_url")
        if isinstance(oa_url, str):
            candidates.append(_candidate("openalex:oa_url", oa_url, evidence="OpenAlex OA record"))
    return candidates


def _unpaywall_candidates(payload: dict[str, Any], doi: str) -> list[dict[str, str]]:
    if normalize_doi(str(payload.get("doi", ""))) != doi:
        return []
    candidates: list[dict[str, str]] = []
    locations: list[dict[str, Any]] = []
    best = payload.get("best_oa_location")
    if isinstance(best, dict):
        locations.append(best)
    locations.extend(value for value in payload.get("oa_locations", []) if isinstance(value, dict))
    for location in locations:
        license_value = str(location.get("license") or "")
        pdf_url = location.get("url_for_pdf")
        if isinstance(pdf_url, str):
            candidates.append(_candidate("unpaywall:oa_pdf", pdf_url, kind="direct", license_value=license_value, evidence="Unpaywall OA location"))
        landing_url = location.get("url_for_landing_page") or location.get("url")
        if isinstance(landing_url, str):
            candidates.append(_candidate("unpaywall:oa_landing", landing_url, kind="landing", license_value=license_value, evidence="Unpaywall OA location"))
    return candidates


def _semantic_scholar_candidates(payload: dict[str, Any], doi: str) -> list[dict[str, str]]:
    external_ids = payload.get("externalIds") if isinstance(payload.get("externalIds"), dict) else {}
    returned_doi = normalize_doi(str(external_ids.get("DOI", "")))
    if returned_doi and returned_doi != doi:
        return []
    oa = payload.get("openAccessPdf")
    if not isinstance(oa, dict) or not isinstance(oa.get("url"), str):
        return []
    status = str(oa.get("status") or "")
    return [_candidate("semantic_scholar:open_access_pdf", oa["url"], kind="direct", evidence=f"Semantic Scholar openAccessPdf {status}".strip())]


def _crossref_candidates(payload: dict[str, Any], doi: str) -> list[dict[str, str]]:
    message = payload.get("message")
    if not isinstance(message, dict) or normalize_doi(str(message.get("DOI", ""))) != doi:
        return []
    licenses = message.get("license") if isinstance(message.get("license"), list) else []
    license_value = ""
    if licenses and isinstance(licenses[0], dict):
        license_value = str(licenses[0].get("URL") or "")
    candidates: list[dict[str, str]] = []
    for link in message.get("link", []) if isinstance(message.get("link"), list) else []:
        if not isinstance(link, dict):
            continue
        url = link.get("URL")
        content_type = str(link.get("content-type") or "").lower()
        if isinstance(url, str) and "pdf" in content_type:
            candidates.append(_candidate("crossref:pdf_link", url, kind="direct", license_value=license_value, evidence="Crossref public metadata link; access not assumed"))
    landing = message.get("URL")
    if isinstance(landing, str):
        candidates.append(_candidate("crossref:landing", landing, kind="landing", license_value=license_value, evidence="Crossref DOI landing page"))
    return candidates


def _europe_pmc_pmcids(payload: dict[str, Any], doi: str) -> list[str]:
    result_list = payload.get("resultList")
    results = result_list.get("result", []) if isinstance(result_list, dict) else []
    pmcids: set[str] = set()
    for result in results if isinstance(results, list) else []:
        if not isinstance(result, dict) or normalize_doi(str(result.get("doi", ""))) != doi:
            continue
        pmcid = str(result.get("pmcid") or "").strip().upper()
        if re.fullmatch(r"PMC\d+", pmcid):
            pmcids.add(pmcid)
    return sorted(pmcids)


def _s3_url_to_https(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "s3" or parsed.netloc != "pmc-oa-opendata" or not parsed.path:
        return ""
    return urlunparse(
        (
            "https",
            "pmc-oa-opendata.s3.amazonaws.com",
            parsed.path,
            "",
            parsed.query,
            "",
        )
    )


def _pmc_cloud_candidates(
    client: PoliteHttpClient,
    pmcid: str,
    doi: str,
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Resolve a PMCID through the approved, versioned PMC AWS dataset."""

    prefix = f"{pmcid}."
    list_url = (
        "https://pmc-oa-opendata.s3.amazonaws.com/"
        f"?list-type=2&prefix={quote(prefix, safe='')}&delimiter=%2F&max-keys=1000"
    )
    response = client.get(list_url, accept="application/xml,text/xml", max_bytes=4 * 1024 * 1024)
    ledger: list[dict[str, Any]] = [
        {
            "source": "pmc_cloud:list",
            "url": list_url,
            "status": response.status,
            "http_attempt_count": response.attempts,
            "pmcid": pmcid,
        }
    ]
    if not response.ok:
        return [], ledger
    try:
        root = ElementTree.fromstring(response.data)
    except ElementTree.ParseError:
        ledger[-1]["status"] = "invalid_xml"
        return [], ledger
    keys = [str(element.text or "") for element in root.iter() if element.tag.rsplit("}", 1)[-1] == "Key"]
    version_prefixes = [
        str(element.text or "")
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] == "Prefix"
    ]
    versions: list[tuple[int, str]] = []
    pattern = re.compile(rf"^{re.escape(pmcid)}\.(\d+)/{re.escape(pmcid)}\.\1\.json$")
    for key in keys:
        match = pattern.fullmatch(key)
        if match:
            versions.append((int(match.group(1)), key))
    prefix_pattern = re.compile(rf"^{re.escape(pmcid)}\.(\d+)/$")
    for value in version_prefixes:
        match = prefix_pattern.fullmatch(value)
        if match:
            version = int(match.group(1))
            versions.append((version, f"{pmcid}.{version}/{pmcid}.{version}.json"))
    versions = sorted(set(versions), reverse=True)
    if not versions:
        ledger[-1]["status"] = "no_versioned_metadata_object"
        return [], ledger

    candidates: list[dict[str, str]] = []
    for version, key in versions:
        metadata_url = f"https://pmc-oa-opendata.s3.amazonaws.com/{quote(key, safe='/')}"
        payload, metadata_status = _fetch_json(client, metadata_url, "pmc_cloud:metadata")
        metadata_status.update({"pmcid": pmcid, "version": version})
        ledger.append(metadata_status)
        if not payload:
            continue
        payload_doi = normalize_doi(str(payload.get("doi", "")))
        payload_pmcid = str(payload.get("pmcid") or "").upper()
        if payload_pmcid != pmcid or payload_doi != doi:
            metadata_status["status"] = "identifier_mismatch"
            continue
        if payload.get("is_pmc_openaccess") is not True:
            metadata_status["status"] = "not_in_pmc_open_access_subset"
            continue
        if payload.get("is_retracted") is not False:
            metadata_status["status"] = "retracted_or_retraction_status_unknown"
            continue
        pdf_url = _s3_url_to_https(str(payload.get("pdf_url") or ""))
        if not pdf_url:
            metadata_status["status"] = "no_valid_pdf_url"
            continue
        license_value = str(payload.get("license_code") or "")
        metadata_status["status"] = "approved_oa_pdf_candidate"
        candidates.append(
            _candidate(
                "pmc_cloud:oa_pdf",
                pdf_url,
                kind="direct",
                license_value=license_value,
                evidence=(
                    f"PMC AWS version {version}; is_pmc_openaccess=true; "
                    "is_retracted=false"
                ),
            )
        )
        # The newest qualifying article version is authoritative.
        break
    return unique_candidates(candidates), ledger


def discover_network_candidates(
    record: dict[str, Any],
    client: PoliteHttpClient,
    *,
    contact_email: str = "",
    semantic_scholar_api_key: str = "",
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    doi = record["doi"]
    pmcids = {str(value).upper() for value in record.get("pmcids", []) if re.fullmatch(r"PMC\d+", str(value), re.IGNORECASE)}
    candidates = [
        _candidate(
            f"curated_override:{item['source_type']}",
            item["url"],
            kind="direct",
            evidence=item["evidence"],
        )
        for item in record.get("curated_pdf_sources", [])
    ]
    candidates.extend(
        [
            _candidate("network:open_access", url, evidence="Stored publication-network open-access link")
            for url in record.get("open_access_urls", [])
        ]
    )
    discovery: list[dict[str, Any]] = []

    def extend_provider(items: list[dict[str, str]]) -> None:
        for item in items:
            url = item.get("url", "")
            if is_prohibited_pmc_presentation_pdf_url(url):
                pmcid = _pmcid_from_url(url)
                if pmcid:
                    pmcids.add(pmcid)
                continue
            candidates.append(item)

    query_suffix = f"?mailto={quote(contact_email, safe='@')}" if contact_email else ""
    payload, status = _fetch_json(client, f"https://api.openalex.org/works/doi:{quote(doi, safe='')}{query_suffix}", "openalex")
    discovery.append(status)
    if payload:
        extend_provider(_openalex_candidates(payload, doi))

    if contact_email:
        payload, status = _fetch_json(
            client,
            f"https://api.unpaywall.org/v2/{quote(doi, safe='')}?email={quote(contact_email, safe='@')}",
            "unpaywall",
        )
        discovery.append(status)
        if payload:
            extend_provider(_unpaywall_candidates(payload, doi))
    else:
        discovery.append({"source": "unpaywall", "url": "", "status": "skipped_no_contact_email", "http_attempt_count": 0})

    semantic_headers = {"x-api-key": semantic_scholar_api_key} if semantic_scholar_api_key else None
    payload, status = _fetch_json(
        client,
        f"https://api.semanticscholar.org/graph/v1/paper/DOI:{quote(doi, safe='')}?fields=title,externalIds,openAccessPdf",
        "semantic_scholar",
        headers=semantic_headers,
    )
    discovery.append(status)
    if payload:
        extend_provider(_semantic_scholar_candidates(payload, doi))

    payload, status = _fetch_json(
        client,
        f"https://api.crossref.org/works/{quote(doi, safe='')}{query_suffix}",
        "crossref",
    )
    discovery.append(status)
    if payload:
        extend_provider(_crossref_candidates(payload, doi))

    europe_query = quote(f"DOI:{doi}", safe="")
    payload, status = _fetch_json(
        client,
        f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={europe_query}&format=json&pageSize=3",
        "europe_pmc",
    )
    discovery.append(status)
    if payload:
        pmcids.update(_europe_pmc_pmcids(payload, doi))

    for pmcid in sorted(pmcids):
        pmc_candidates, pmc_discovery = _pmc_cloud_candidates(client, pmcid, doi)
        candidates.extend(pmc_candidates)
        discovery.extend(pmc_discovery)

    # Public predictable routes and DOI landing-page metadata are fallback-only.
    if doi.startswith("10.1371/journal.pone."):
        candidates.append(_candidate("publisher:plos", f"https://journals.plos.org/plosone/article/file?id={doi}&type=printable", kind="direct", evidence="Predictable public publisher route"))
    if doi.startswith("10.1038/"):
        candidates.append(_candidate("publisher:nature", f"https://www.nature.com/articles/{doi.split('/', 1)[1]}.pdf", kind="direct", evidence="Predictable public publisher route"))
    if doi.startswith("10.3389/"):
        candidates.append(_candidate("publisher:frontiers", f"https://www.frontiersin.org/articles/{doi}/pdf", kind="direct", evidence="Predictable public publisher route"))
    if doi.startswith("10.1073/pnas."):
        candidates.append(_candidate("publisher:pnas", f"https://www.pnas.org/doi/pdf/{doi}", kind="direct", evidence="Predictable public publisher route"))
    if doi.startswith("10.1098/"):
        candidates.append(_candidate("publisher:royal_society", f"https://royalsocietypublishing.org/doi/pdf/{doi}", kind="direct", evidence="Predictable public publisher route"))
    if doi.startswith("10.1523/"):
        candidates.append(_candidate("publisher:jneurosci", f"https://www.jneurosci.org/doi/pdf/{doi}", kind="direct", evidence="Predictable public publisher route"))
    if doi.startswith("10.3390/"):
        candidates.append(_candidate("publisher:mdpi", f"https://www.mdpi.com/{doi}/pdf", kind="direct", evidence="Predictable public publisher route"))
    candidates.append(_candidate("doi:landing", f"https://doi.org/{doi}", kind="landing", evidence="DOI landing-page metadata only"))
    return unique_candidates(candidates), discovery


class CitationPdfParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {str(key).lower(): value or "" for key, value in attrs}
        if tag.lower() == "meta" and values.get("name", "").lower() == "citation_pdf_url":
            if values.get("content"):
                self.urls.append(values["content"])
        if tag.lower() == "link" and "pdf" in values.get("type", "").lower() and values.get("href"):
            self.urls.append(values["href"])


def discover_landing_pdf_candidates(
    client: PoliteHttpClient,
    item: dict[str, str],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    response = client.get(item["url"], accept="text/html,application/xhtml+xml,*/*;q=0.5", max_bytes=3 * 1024 * 1024)
    attempt = {
        "source": item["source"],
        "url": item["url"],
        "kind": "landing",
        "status": response.status,
        "http_attempt_count": response.attempts,
        "final_url": response.final_url,
        "content_type": response.content_type,
        "discovered_pdf_count": 0,
    }
    if not response.ok:
        return [], attempt
    if is_prohibited_pmc_presentation_pdf_url(response.final_url):
        pmcid = _pmcid_from_url(response.final_url)
        attempt.update(
            {
                "status": "prohibited_pmc_presentation_redirect",
                "prohibited_pmc_presentation_pmcids": [pmcid] if pmcid else [],
            }
        )
        return [], attempt
    if b"%PDF-" in response.data[:1024]:
        direct = dict(item)
        direct.update({"url": response.final_url or item["url"], "kind": "direct", "prefetched_pdf": "yes"})
        attempt.update({"status": "landing_resolved_to_pdf", "discovered_pdf_count": 1})
        return [direct], attempt
    try:
        text = response.data.decode("utf-8", errors="replace")
        parser = CitationPdfParser()
        parser.feed(text)
    except Exception:
        attempt["status"] = "landing_html_parse_failed"
        return [], attempt
    raw_discovered_urls = [urljoin(response.final_url or item["url"], url) for url in parser.urls]
    prohibited_pmcids = sorted(
        {
            _pmcid_from_url(url)
            for url in raw_discovered_urls
            if is_prohibited_pmc_presentation_pdf_url(url) and _pmcid_from_url(url)
        }
    )
    discovered = [
        _candidate(
            f"{item['source']}:citation_pdf_url",
            url,
            kind="direct",
            license_value=item.get("license", ""),
            evidence=f"{item.get('access_evidence', item['source'])}; citation_pdf_url",
        )
        for url in raw_discovered_urls
    ]
    discovered = unique_candidates(discovered)
    attempt.update(
        {
            "status": "landing_metadata_checked",
            "discovered_pdf_count": len(discovered),
            "prohibited_pmc_presentation_pmcids": prohibited_pmcids,
        }
    )
    return discovered, attempt


def _title_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) >= 4 and token not in TITLE_STOPWORDS
    }


def validate_pdf_bytes(data: bytes, *, expected_doi: str, expected_title: str) -> dict[str, Any]:
    digest = hashlib.sha256(data).hexdigest()
    base = {
        "valid": False,
        "validation_status": "not_pdf",
        "size_bytes": len(data),
        "sha256": digest,
        "page_count": 0,
        "identity_status": "not_checked",
        "identity_basis": "",
    }
    if b"%PDF-" not in data[:1024]:
        return base
    try:
        from pypdf import PdfReader
    except ImportError:
        base["validation_status"] = "pypdf_unavailable"
        return base
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted and reader.decrypt("") == 0:
            base["validation_status"] = "encrypted_unreadable"
            return base
        page_count = len(reader.pages)
        if page_count < 1:
            base["validation_status"] = "zero_page_pdf"
            return base
        metadata = reader.metadata or {}
        metadata_title = str(getattr(metadata, "title", "") or metadata.get("/Title", "") or "")
        metadata_subject = str(getattr(metadata, "subject", "") or metadata.get("/Subject", "") or "")
        metadata_keywords = str(metadata.get("/Keywords", "") or "")
        text_parts = [metadata_title, metadata_subject, metadata_keywords]
        for page in reader.pages[: min(2, page_count)]:
            try:
                text_parts.append((page.extract_text() or "")[:50000])
            except Exception:
                continue
    except Exception as exc:
        base["validation_status"] = f"pypdf_error:{exc.__class__.__name__}"
        return base

    searchable = "\n".join(text_parts).lower()
    doi = normalize_doi(expected_doi)
    doi_variants = {doi, doi.replace("/", " "), f"doi.org/{doi}"}
    doi_match = any(value and value in searchable for value in doi_variants)
    expected_tokens = _title_tokens(expected_title)
    found_tokens = _title_tokens(searchable)
    title_overlap = len(expected_tokens & found_tokens) / len(expected_tokens) if expected_tokens else 0.0
    if doi_match and title_overlap >= 0.6:
        identity_status = "doi_and_title_match"
        identity_basis = f"Expected DOI and {title_overlap:.0%} of distinctive title tokens matched PDF metadata/first pages."
    elif doi_match:
        identity_status = "doi_match"
        identity_basis = "Expected DOI matched PDF metadata/first pages."
    elif title_overlap >= 0.6:
        identity_status = "title_match"
        identity_basis = f"{title_overlap:.0%} of distinctive title tokens matched PDF metadata/first pages."
    elif searchable.strip():
        identity_status = "unverified_no_identifier_match"
        identity_basis = f"Structurally valid PDF; DOI absent and title-token overlap was {title_overlap:.0%}."
    else:
        identity_status = "unverified_no_extractable_text"
        identity_basis = "Structurally valid PDF, but no usable metadata or first-page text was extractable."
    base.update(
        {
            "valid": True,
            "validation_status": "pypdf_valid",
            "page_count": page_count,
            "identity_status": identity_status,
            "identity_basis": identity_basis,
        }
    )
    return base


def validate_pdf_file(path: Path, *, expected_doi: str, expected_title: str) -> dict[str, Any]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        return {
            "valid": False,
            "validation_status": f"read_error:{exc.__class__.__name__}",
            "size_bytes": 0,
            "sha256": "",
            "page_count": 0,
            "identity_status": "not_checked",
            "identity_basis": "",
        }
    return validate_pdf_bytes(data, expected_doi=expected_doi, expected_title=expected_title)


def _has_verified_identity(validation: dict[str, Any]) -> bool:
    return str(validation.get("identity_status", "")) in VERIFIED_IDENTITY_STATUSES


def _base_result(record: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    destination = repo_root / PDF_DIR / record["destination_filename"]
    return {
        "record_id": record["record_id"],
        "publication_id": record["publication_id"],
        "audit_record_ids": record["audit_record_ids"],
        "title": record["title"],
        "year": record["year"],
        "doi": record["doi"],
        "pdf_status": "not_attempted_this_run",
        "last_status": "not_attempted_this_run",
        "local_file": destination.relative_to(repo_root).as_posix(),
        "downloaded_url": "",
        "final_url": "",
        "candidate_source": "",
        "license": "",
        "redistribution_status": "not_established_keep_local_only",
        "size_bytes": 0,
        "sha256": "",
        "page_count": 0,
        "validation_status": "not_checked",
        "identity_status": "not_checked",
        "identity_basis": "",
        "discovery_attempts": [],
        "attempts": [],
        "attempt_count": 0,
    }


def acquire_network_record(
    repo_root: Path,
    record: dict[str, Any],
    client: PoliteHttpClient,
    *,
    previous: dict[str, Any] | None = None,
    force: bool = False,
    contact_email: str = "",
    semantic_scholar_api_key: str = "",
) -> dict[str, Any]:
    result = _base_result(record, repo_root)
    previous_attempts = list(previous.get("attempts", [])) if isinstance(previous, dict) else []
    destination = repo_root / PDF_DIR / record["destination_filename"]
    if destination.exists() and not force:
        validation = validate_pdf_file(destination, expected_doi=record["doi"], expected_title=record["title"])
        if validation["valid"] and _has_verified_identity(validation):
            result.update(validation)
            result["attempts"] = previous_attempts
            result["attempt_count"] = len(previous_attempts)
            result.update(
                {
                    "pdf_status": "downloaded",
                    "last_status": "existing_valid_pdf",
                    "downloaded_url": str((previous or {}).get("downloaded_url", "")),
                    "final_url": str((previous or {}).get("final_url", "")),
                    "candidate_source": str((previous or {}).get("candidate_source", "")),
                    "license": str((previous or {}).get("license", "")),
                    "redistribution_status": str((previous or {}).get("redistribution_status", "not_established_keep_local_only")),
                }
            )
            result["discovery_attempts"] = list((previous or {}).get("discovery_attempts", []))
            return result

        quarantine_reason = "identity_mismatch" if validation["valid"] else "invalid"
        quarantine = destination.with_name(
            f"{destination.stem}.{quarantine_reason}_{validation.get('sha256', '')[:12] or 'unknown'}"
            f"{destination.suffix}"
        )
        if quarantine.exists():
            destination.unlink()
        else:
            destination.replace(quarantine)
        previous_attempts.append(
            {
                "source": "local_resume_validation",
                "url": "",
                "kind": "local_file",
                "status": "identity_mismatch" if validation["valid"] else validation["validation_status"],
                "validation_status": validation["validation_status"],
                "quarantined_file": quarantine.relative_to(repo_root).as_posix(),
                "size_bytes": validation["size_bytes"],
                "sha256": validation["sha256"],
                "identity_status": validation["identity_status"],
                "identity_basis": validation["identity_basis"],
            }
        )
        result["quarantined_invalid_file"] = quarantine.relative_to(repo_root).as_posix()

    candidates, discovery_attempts = discover_network_candidates(
        record,
        client,
        contact_email=contact_email,
        semantic_scholar_api_key=semantic_scholar_api_key,
    )
    previous_discovery = list(previous.get("discovery_attempts", [])) if isinstance(previous, dict) else []
    result["discovery_attempts"] = previous_discovery + discovery_attempts
    queue = list(candidates)
    seen_candidates = {(item["url"], item["kind"]) for item in queue}
    new_attempts: list[dict[str, Any]] = []
    while queue:
        item = queue.pop(0)
        if item["kind"] == "landing":
            discovered, attempt = discover_landing_pdf_candidates(client, item)
            new_attempts.append(attempt)
            for pmcid in attempt.get("prohibited_pmc_presentation_pmcids", []):
                pmc_candidates, pmc_discovery = _pmc_cloud_candidates(client, pmcid, record["doi"])
                result["discovery_attempts"].extend(pmc_discovery)
                discovered.extend(pmc_candidates)
            for found in discovered:
                candidate_key = (found["url"], found["kind"])
                if candidate_key not in seen_candidates:
                    seen_candidates.add(candidate_key)
                    queue.append(found)
            continue

        response = client.get(item["url"], accept="application/pdf,application/octet-stream,*/*;q=0.2")
        attempt = {
            "source": item["source"],
            "url": item["url"],
            "kind": "direct",
            "access_evidence": item.get("access_evidence", ""),
            "status": response.status,
            "http_attempt_count": response.attempts,
            "status_code": response.status_code,
            "final_url": response.final_url,
            "content_type": response.content_type,
        }
        if not response.ok:
            new_attempts.append(attempt)
            continue
        if is_prohibited_pmc_presentation_pdf_url(response.final_url):
            attempt["status"] = "prohibited_pmc_presentation_redirect"
            new_attempts.append(attempt)
            pmcid = _pmcid_from_url(response.final_url)
            if pmcid:
                pmc_candidates, pmc_discovery = _pmc_cloud_candidates(client, pmcid, record["doi"])
                result["discovery_attempts"].extend(pmc_discovery)
                for found in pmc_candidates:
                    candidate_key = (found["url"], found["kind"])
                    if candidate_key not in seen_candidates:
                        seen_candidates.add(candidate_key)
                        queue.append(found)
            continue
        validation = validate_pdf_bytes(response.data, expected_doi=record["doi"], expected_title=record["title"])
        attempt.update(
            {
                "status": validation["validation_status"],
                "validation_status": validation["validation_status"],
                "size_bytes": validation["size_bytes"],
                "sha256": validation["sha256"],
                "page_count": validation["page_count"],
                "identity_status": validation["identity_status"],
                "identity_basis": validation["identity_basis"],
            }
        )
        new_attempts.append(attempt)
        if not validation["valid"]:
            continue
        if not _has_verified_identity(validation):
            attempt["status"] = "identity_mismatch"
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp = destination.with_suffix(destination.suffix + ".tmp")
        tmp.write_bytes(response.data)
        tmp.replace(destination)
        result.update(validation)
        license_value = item.get("license", "")
        result.update(
            {
                "pdf_status": "downloaded",
                "last_status": "downloaded",
                "downloaded_url": item["url"],
                "final_url": response.final_url or item["url"],
                "candidate_source": item["source"],
                "license": license_value,
                "redistribution_status": (
                    "license_recorded_review_terms_before_reuse"
                    if license_value
                    else "not_established_keep_local_only"
                ),
            }
        )
        break

    result["attempts"] = previous_attempts + new_attempts
    result["attempt_count"] = len(result["attempts"])
    if result["pdf_status"] != "downloaded":
        result["pdf_status"] = "needs_user_download" if candidates else "open_access_unavailable"
        result["last_status"] = new_attempts[-1]["status"] if new_attempts else "no_public_pdf_candidates"
    return result


def _load_previous_records(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        normalize_doi(str(item.get("doi", ""))): item
        for item in payload.get("records", [])
        if isinstance(item, dict) and normalize_doi(str(item.get("doi", "")))
    }


def run_network_acquisition(
    repo_root: Path,
    *,
    network_path: Path = NETWORK_PATH,
    force: bool = False,
    limit: int | None = None,
    delay_seconds: float = 1.0,
    max_retries: int = 3,
    contact_email: str = "",
    semantic_scholar_api_key: str = "",
    client: PoliteHttpClient | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    records = load_network_records(repo_root, network_path)
    overrides_by_doi = load_pdf_source_overrides(repo_root, {record["doi"] for record in records})
    for record in records:
        override = overrides_by_doi.get(record["doi"])
        record["curated_pdf_sources"] = [override] if override else []
    status_path = repo_root / NETWORK_ACQUISITION_STATUS_PATH
    previous_by_doi = _load_previous_records(status_path)
    selected = records if limit is None else records[: max(0, limit)]
    client = client or PoliteHttpClient(delay_seconds=delay_seconds, max_retries=max_retries)
    started_at = datetime.now(timezone.utc).isoformat()
    results: list[dict[str, Any]] = []
    for record in records:
        previous = previous_by_doi.get(record["doi"])
        if previous:
            result = _base_result(record, repo_root)
            result.update(previous)
            result.update(
                {
                    "record_id": record["record_id"],
                    "publication_id": record["publication_id"],
                    "audit_record_ids": record["audit_record_ids"],
                    "title": record["title"],
                    "year": record["year"],
                    "doi": record["doi"],
                    "local_file": (PDF_DIR / record["destination_filename"]).as_posix(),
                }
            )
        else:
            result = _base_result(record, repo_root)
        results.append(result)

    status_path.parent.mkdir(parents=True, exist_ok=True)

    def checkpoint(attempted_count: int, *, completed: bool) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for item in results:
            counts[item["pdf_status"]] = counts.get(item["pdf_status"], 0) + 1
        payload = {
            "schema": "pps-network-paper-pdf-acquisition-status.v1",
            "source": "publication_network",
            "network_path": network_path.as_posix(),
            "started_at": started_at,
            "checkpointed_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat() if completed else "",
            "source_node_count": len(
                json.loads(
                    (
                        network_path if network_path.is_absolute() else repo_root / network_path
                    ).read_text(encoding="utf-8")
                )["nodes"]
            ),
            "source_count": len(records),
            "unique_doi_count": len(records),
            "run_target_count": len(selected),
            "attempted_this_run_count": attempted_count,
            "pdf_status_counts": dict(sorted(counts.items())),
            "main_pdf_only": True,
            "raw_artifact_policy": "PDFs remain under ignored artifacts/paper_metadata_audit/publication_pdfs and must not be committed or redistributed without reviewing license terms.",
            "records": _sanitize_ledger_value(results),
        }
        tmp = status_path.with_suffix(status_path.suffix + ".tmp")
        serialized_payload = _sanitize_ledger_value(payload)
        tmp.write_text(json.dumps(serialized_payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        tmp.replace(status_path)
        return serialized_payload

    # A complete 94-row ledger exists even if the first request is interrupted.
    payload = checkpoint(0, completed=False)
    result_index_by_doi = {result["doi"]: index for index, result in enumerate(results)}
    for attempted_count, record in enumerate(selected, start=1):
        index = result_index_by_doi[record["doi"]]
        results[index] = acquire_network_record(
            repo_root,
            record,
            client,
            previous=results[index],
            force=force,
            contact_email=contact_email,
            semantic_scholar_api_key=semantic_scholar_api_key,
        )
        payload = checkpoint(attempted_count, completed=False)
    payload = checkpoint(len(selected), completed=True)
    return payload


def contact_email_from_environment(explicit: str = "") -> str:
    return explicit.strip() or os.environ.get("PPSKIT_UNPAYWALL_EMAIL", "").strip() or os.environ.get("UNPAYWALL_EMAIL", "").strip()


def semantic_scholar_key_from_environment() -> str:
    return os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip()
