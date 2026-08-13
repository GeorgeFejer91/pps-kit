from __future__ import annotations

import io
import json
import re
import tempfile
import tomllib
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

from pypdf import PdfWriter

from tools.paper_metadata_parser import network_acquire
from tools.paper_metadata_parser.network_acquire import (
    FetchResult,
    PoliteHttpClient,
    _pmc_cloud_candidates,
    discover_network_candidates,
    discover_landing_pdf_candidates,
    doi_pdf_filename,
    is_prohibited_pmc_presentation_pdf_url,
    load_pdf_source_overrides,
    load_network_records,
    normalize_http_url,
    run_network_acquisition,
    validate_pdf_bytes,
)


ROOT = Path(__file__).resolve().parents[1]
NETWORK_PATH = ROOT / "src" / "peripersonal_space_toolkit" / "dashboard" / "publication_network.v3.json"


def make_pdf(*, title: str, doi: str) -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_metadata({"/Title": title, "/Subject": f"doi:{doi}"})
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class FakeResponse:
    def __init__(self, data: bytes, *, status: int = 200, url: str = "https://example.test/final", content_type: str = "application/json") -> None:
        self._data = data
        self._offset = 0
        self.status = status
        self._url = url
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        self.headers["Content-Length"] = str(len(data))

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._data) - self._offset
        value = self._data[self._offset : self._offset + size]
        self._offset += len(value)
        return value

    def geturl(self) -> str:
        return self._url


class StaticClient:
    def __init__(self, results: list[FetchResult]) -> None:
        self.results = list(results)
        self.urls: list[str] = []

    def get(self, url: str, **_kwargs) -> FetchResult:
        self.urls.append(url)
        assert self.results, f"Unexpected request: {url}"
        return self.results.pop(0)


def test_current_network_loader_is_exactly_94_unique_doi_publications():
    records = load_network_records(ROOT, NETWORK_PATH)

    assert len(records) == 94
    assert len({record["doi"] for record in records}) == 94
    assert len({record["publication_id"] for record in records}) == 94
    assert len({record["destination_filename"] for record in records}) == 94
    assert all(record["doi"] == record["doi"].lower() for record in records)
    assert all(re.fullmatch(r"[A-Za-z0-9._-]+\.pdf", record["destination_filename"]) for record in records)
    assert all(len(record["destination_filename"]) <= 110 for record in records)


def test_curated_pdf_source_overrides_are_unique_https_routes_for_current_network():
    records = load_network_records(ROOT, NETWORK_PATH)
    overrides = load_pdf_source_overrides(ROOT, {record["doi"] for record in records})

    assert len(overrides) == 14
    assert all(item["doi"] == doi for doi, item in overrides.items())
    assert all(item["url"].startswith("https://") for item in overrides.values())
    assert all(item["source_type"] and item["evidence"] for item in overrides.values())


def test_public_encrypted_pdf_routes_are_classified_and_crypto_support_is_declared():
    records = load_network_records(ROOT, NETWORK_PATH)
    overrides = load_pdf_source_overrides(ROOT, {record["doi"] for record in records})
    encrypted_dois = {"10.53829/ntr201911fa4", "10.61782/fa.2025.0866"}

    assert {doi for doi, item in overrides.items() if item["source_type"] == "public_encrypted_pdf"} == encrypted_dois
    assert all("AES document encryption" in overrides[doi]["notes"] for doi in encrypted_dois)

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert "pypdf[crypto]>=5,<7" in project["optional-dependencies"]["paper-audit"]
    assert "pypdf[crypto]>=5,<7" in project["optional-dependencies"]["dev"]


def test_doi_filename_is_stable_safe_and_collision_resistant():
    first = doi_pdf_filename("https://doi.org/10.1000/A:B/C")
    second = doi_pdf_filename("10.1000/a:b/c")
    nearby = doi_pdf_filename("10.1000/a-b/c")

    assert first == second
    assert first != nearby
    assert "/" not in first and ":" not in first and "\\" not in first
    assert first.endswith(".pdf")


def test_http_url_normalization_encodes_literal_spaces_without_double_encoding():
    source = "https://example.test/a file/already%20encoded.pdf?name=a b&token=x%20y"
    assert normalize_http_url(source) == (
        "https://example.test/a%20file/already%20encoded.pdf?name=a%20b&token=x%20y"
    )


def test_jstage_underscore_pdf_route_is_classified_as_direct():
    url = "https://www.jstage.jst.go.jp/article/ast/41/1/41_E19280/_pdf"
    assert network_acquire._candidate_kind(url) == "direct"


def test_pypdf_validation_records_structure_hash_pages_and_identity():
    title = "Dynamic sounds capture the boundaries of peripersonal space representation in humans"
    doi = "10.1371/journal.pone.0044306"
    data = make_pdf(title=title, doi=doi)

    result = validate_pdf_bytes(data, expected_doi=doi, expected_title=title)

    assert result["valid"] is True
    assert result["validation_status"] == "pypdf_valid"
    assert result["page_count"] == 1
    assert result["size_bytes"] == len(data)
    assert len(result["sha256"]) == 64
    assert result["identity_status"] == "doi_and_title_match"
    assert validate_pdf_bytes(b"%PDF-not-structurally-valid", expected_doi=doi, expected_title=title)["valid"] is False


def test_http_client_honors_retry_after_before_success():
    calls: list[Request] = []
    sleeps: list[float] = []
    headers = Message()
    headers["Retry-After"] = "2"

    def opener(request: Request, **_kwargs):
        calls.append(request)
        if len(calls) == 1:
            raise HTTPError(request.full_url, 429, "rate limited", headers, None)
        return FakeResponse(b"{}", url=request.full_url)

    client = PoliteHttpClient(
        delay_seconds=0,
        max_retries=1,
        opener=opener,
        sleep_fn=sleeps.append,
        monotonic_fn=lambda: 0.0,
    )
    result = client.get("https://api.example.test/item", accept="application/json")

    assert result.ok is True
    assert result.attempts == 2
    assert len(calls) == 2
    assert sleeps == [2.0]


def test_landing_page_discovers_only_citation_pdf_metadata():
    html = b"""
      <html><head>
      <meta name="citation_pdf_url" content="/article/main.pdf">
      </head><body><a href="/unrelated.pdf">unrelated link</a></body></html>
    """
    client = StaticClient(
        [
            FetchResult(
                True,
                "fetched",
                data=html,
                content_type="text/html",
                final_url="https://journal.example/article",
                attempts=1,
            )
        ]
    )
    candidates, attempt = discover_landing_pdf_candidates(
        client,
        {
            "source": "test:landing",
            "url": "https://journal.example/article",
            "kind": "landing",
            "license": "CC BY",
            "access_evidence": "fixture",
        },
    )

    assert [candidate["url"] for candidate in candidates] == ["https://journal.example/article/main.pdf"]
    assert attempt["status"] == "landing_metadata_checked"
    assert attempt["discovered_pdf_count"] == 1


def test_discovery_collects_stored_and_public_api_candidates_without_leaking_email():
    doi = "10.1000/example"
    payloads = [
        {
            "doi": f"https://doi.org/{doi}",
            "open_access": {"is_oa": True, "oa_url": "https://openalex.example/article"},
            "best_oa_location": {"is_oa": True, "pdf_url": "https://openalex.example/main.pdf", "license": "cc-by"},
        },
        {
            "doi": doi,
            "best_oa_location": {"url_for_pdf": "https://unpaywall.example/main.pdf", "license": "cc-by-nc"},
            "oa_locations": [],
        },
        {
            "externalIds": {"DOI": doi},
            "openAccessPdf": {"url": "https://semanticscholar.example/main.pdf", "status": "GREEN"},
        },
        {
            "message": {
                "DOI": doi,
                "URL": "https://crossref.example/article",
                "link": [{"URL": "https://crossref.example/main.pdf", "content-type": "application/pdf"}],
                "license": [{"URL": "https://creativecommons.org/licenses/by/4.0/"}],
            }
        },
        {"resultList": {"result": []}},
    ]
    client = StaticClient(
        [
            FetchResult(True, "fetched", data=json.dumps(payload).encode(), attempts=1)
            for payload in payloads
        ]
    )
    candidates, discovery = discover_network_candidates(
        {
            "doi": doi,
            "open_access_urls": ["https://stored.example/main.pdf"],
            "pmcids": [],
            "curated_pdf_sources": [
                {
                    "doi": doi,
                    "url": "https://curated.example/main.pdf",
                    "source_type": "institutional_repository_pdf",
                    "evidence": "reviewed fixture",
                    "notes": "",
                }
            ],
        },
        client,
        contact_email="person@example.org",
    )

    sources = {candidate["source"] for candidate in candidates}
    assert {
        "curated_override:institutional_repository_pdf",
        "network:open_access",
        "openalex:best_oa_location",
        "unpaywall:oa_pdf",
        "semantic_scholar:open_access_pdf",
        "crossref:pdf_link",
        "doi:landing",
    } <= sources
    assert candidates[0]["source"] == "curated_override:institutional_repository_pdf"
    assert {item["source"] for item in discovery} == {
        "openalex",
        "unpaywall",
        "semantic_scholar",
        "crossref",
        "europe_pmc",
    }
    assert "person%40example.org" not in json.dumps(discovery)
    assert "redacted" in json.dumps(discovery)


def test_pmc_presentation_routes_are_prohibited_and_cloud_metadata_is_required():
    render_url = "https://europepmc.org/articles/PMC1234567?pdf=render"
    ncbi_url = "https://pmc.ncbi.nlm.nih.gov/articles/PMC1234567/pdf/paper.pdf"
    legacy_numeric_landing = "https://www.ncbi.nlm.nih.gov/pmc/articles/1234567"
    assert is_prohibited_pmc_presentation_pdf_url(render_url)
    assert is_prohibited_pmc_presentation_pdf_url(ncbi_url)
    assert is_prohibited_pmc_presentation_pdf_url(legacy_numeric_landing)

    listing = b"""<?xml version="1.0"?>
      <ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
        <Contents><Key>PMC1234567.1/PMC1234567.1.json</Key></Contents>
        <Contents><Key>PMC1234567.2/PMC1234567.2.json</Key></Contents>
      </ListBucketResult>
    """
    metadata = {
        "pmcid": "PMC1234567",
        "version": 2,
        "doi": "10.1000/example",
        "is_pmc_openaccess": True,
        "is_retracted": False,
        "license_code": "CC BY",
        "pdf_url": "s3://pmc-oa-opendata/PMC1234567.2/PMC1234567.2.pdf?md5=abc123",
    }
    client = StaticClient(
        [
            FetchResult(True, "fetched", data=listing, content_type="application/xml", final_url="https://pmc-oa-opendata.s3.amazonaws.com/", attempts=1),
            FetchResult(True, "fetched", data=json.dumps(metadata).encode(), content_type="application/json", final_url="https://pmc-oa-opendata.s3.amazonaws.com/PMC1234567.2/PMC1234567.2.json", attempts=1),
        ]
    )
    candidates, ledger = _pmc_cloud_candidates(client, "PMC1234567", "10.1000/example")

    assert len(candidates) == 1
    assert candidates[0]["url"] == "https://pmc-oa-opendata.s3.amazonaws.com/PMC1234567.2/PMC1234567.2.pdf?md5=abc123"
    assert candidates[0]["license"] == "CC BY"
    assert ledger[-1]["status"] == "approved_oa_pdf_candidate"
    assert not any("europepmc.org/articles" in candidate["url"] for candidate in candidates)


def test_pmc_cloud_rejects_non_oa_or_retracted_metadata():
    listing = b"""<ListBucketResult><Contents><Key>PMC7654321.1/PMC7654321.1.json</Key></Contents></ListBucketResult>"""
    metadata = {
        "pmcid": "PMC7654321",
        "version": 1,
        "doi": "10.1000/retracted",
        "is_pmc_openaccess": True,
        "is_retracted": True,
        "pdf_url": "s3://pmc-oa-opendata/PMC7654321.1/PMC7654321.1.pdf",
    }
    client = StaticClient(
        [
            FetchResult(True, "fetched", data=listing, attempts=1),
            FetchResult(True, "fetched", data=json.dumps(metadata).encode(), attempts=1),
        ]
    )

    candidates, ledger = _pmc_cloud_candidates(client, "PMC7654321", "10.1000/retracted")

    assert candidates == []
    assert ledger[-1]["status"] == "retracted_or_retraction_status_unknown"


def test_network_ledger_remains_complete_during_limited_resume():
    calls: list[tuple[str, dict | None]] = []

    def fake_acquire(repo_root, record, _client, *, previous=None, **_kwargs):
        calls.append((record["doi"], previous))
        result = network_acquire._base_result(record, repo_root)
        result.update(
            {
                "pdf_status": "needs_user_download",
                "last_status": "mock_attempt",
                "attempts": list((previous or {}).get("attempts", []))
                + [{"source": "mock", "url": "https://example.test", "status": "http_404"}],
            }
        )
        result["attempt_count"] = len(result["attempts"])
        return result

    with tempfile.TemporaryDirectory() as tmp_dir, patch.object(
        network_acquire, "acquire_network_record", fake_acquire
    ):
        tmp_path = Path(tmp_dir)
        payload = run_network_acquisition(
            tmp_path,
            network_path=NETWORK_PATH,
            limit=1,
            client=StaticClient([]),
        )

        assert payload["source_node_count"] == 94
        assert payload["source_count"] == payload["unique_doi_count"] == 94
        assert payload["attempted_this_run_count"] == 1
        assert len(payload["records"]) == 94
        assert sum(record["pdf_status"] == "not_attempted_this_run" for record in payload["records"]) == 93
        assert len(calls) == 1

        resumed = run_network_acquisition(
            tmp_path,
            network_path=NETWORK_PATH,
            limit=1,
            client=StaticClient([]),
        )
        assert len(resumed["records"]) == 94
        assert calls[-1][1] is not None
        assert calls[-1][1]["attempt_count"] == 1
        assert resumed["records"][0]["attempt_count"] == 2


def test_network_ledger_redacts_presigned_url_credentials_before_checkpoint():
    credential_key = "X-Amz-" + "Credential"
    signature_key = "X-Amz-" + "Signature"
    signed_url = (
        "https://bucket.example/paper.pdf?"
        f"{credential_key}=TESTABCDEFGHIJKLMNOP%2Fdate%2Fregion%2Fs3%2Faws4_request&"
        f"{signature_key}=deadbeef&download=1"
    )

    def fake_acquire(repo_root, record, _client, **_kwargs):
        result = network_acquire._base_result(record, repo_root)
        result.update(
            {
                "pdf_status": "needs_user_download",
                "last_status": "mock_attempt",
                "final_url": signed_url,
                "attempts": [{"source": "mock", "url": signed_url, "status": "http_403"}],
            }
        )
        return result

    with tempfile.TemporaryDirectory() as tmp_dir, patch.object(
        network_acquire, "acquire_network_record", fake_acquire
    ):
        tmp_path = Path(tmp_dir)
        run_network_acquisition(
            tmp_path,
            network_path=NETWORK_PATH,
            limit=1,
            client=StaticClient([]),
        )
        ledger_text = (tmp_path / network_acquire.NETWORK_ACQUISITION_STATUS_PATH).read_text(
            encoding="utf-8"
        )

    assert "TESTABCDEFGHIJKLMNOP" not in ledger_text
    assert "deadbeef" not in ledger_text
    assert "download=1" in ledger_text
    assert "%5Bredacted%5D" in ledger_text


def test_network_ledger_checkpoints_every_completed_record_before_interruption():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        network_path = tmp_path / "network.json"
        network_path.write_text(
            json.dumps(
                {
                    "nodes": [
                        {"id": "doi:10.1000/a", "doi": "10.1000/a", "title": "Paper A", "links": {}, "toolkit": {}},
                        {"id": "doi:10.1000/b", "doi": "10.1000/b", "title": "Paper B", "links": {}, "toolkit": {}},
                    ]
                }
            ),
            encoding="utf-8",
        )
        call_count = 0

        def interrupted_acquire(repo_root, record, _client, **_kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("simulated interruption")
            result = network_acquire._base_result(record, repo_root)
            result.update({"pdf_status": "needs_user_download", "last_status": "mock_complete"})
            return result

        with patch.object(network_acquire, "acquire_network_record", interrupted_acquire):
            try:
                run_network_acquisition(tmp_path, network_path=network_path, client=StaticClient([]))
            except RuntimeError as exc:
                assert str(exc) == "simulated interruption"
            else:
                raise AssertionError("Expected simulated interruption")

        ledger = json.loads(
            (tmp_path / network_acquire.NETWORK_ACQUISITION_STATUS_PATH).read_text(encoding="utf-8")
        )
        assert ledger["source_count"] == 2
        assert len(ledger["records"]) == 2
        assert ledger["attempted_this_run_count"] == 1
        assert ledger["completed_at"] == ""
        assert ledger["records"][0]["last_status"] == "mock_complete"


def test_existing_valid_pdf_resumes_without_network_or_overwrite():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        record = load_network_records(ROOT, NETWORK_PATH)[0]
        destination = tmp_path / network_acquire.PDF_DIR / record["destination_filename"]
        destination.parent.mkdir(parents=True)
        original = make_pdf(title=record["title"], doi=record["doi"])
        destination.write_bytes(original)

        result = network_acquire.acquire_network_record(
            tmp_path,
            record,
            StaticClient([]),
            previous={"attempts": [], "downloaded_url": "https://example.test/original.pdf"},
        )

        assert result["last_status"] == "existing_valid_pdf"
        assert result["pdf_status"] == "downloaded"
        assert destination.read_bytes() == original
        assert result["downloaded_url"] == "https://example.test/original.pdf"


def test_existing_invalid_pdf_is_quarantined_and_replaced_by_valid_candidate():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        record = load_network_records(ROOT, NETWORK_PATH)[0]
        destination = tmp_path / network_acquire.PDF_DIR / record["destination_filename"]
        destination.parent.mkdir(parents=True)
        invalid = b"%PDF-invalid"
        destination.write_bytes(invalid)
        replacement = make_pdf(title=record["title"], doi=record["doi"])
        client = StaticClient(
            [
                FetchResult(
                    True,
                    "fetched",
                    status_code=200,
                    data=replacement,
                    content_type="application/pdf",
                    final_url="https://repository.example/replacement.pdf",
                    attempts=1,
                )
            ]
        )
        candidates = [
            {
                "source": "fixture:oa",
                "url": "https://repository.example/replacement.pdf",
                "kind": "direct",
                "license": "CC BY",
                "access_evidence": "fixture",
            }
        ]
        with patch.object(network_acquire, "discover_network_candidates", return_value=(candidates, [])):
            result = network_acquire.acquire_network_record(tmp_path, record, client)

        assert result["pdf_status"] == "downloaded"
        assert result["validation_status"] == "pypdf_valid"
        assert destination.read_bytes() == replacement
        quarantine = tmp_path / result["quarantined_invalid_file"]
        assert quarantine.read_bytes() == invalid
        assert result["attempts"][0]["source"] == "local_resume_validation"
        assert result["license"] == "CC BY"


def test_same_url_landing_pdf_promotion_is_not_deduplicated_away():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        record = load_network_records(ROOT, NETWORK_PATH)[0]
        public_pdf = make_pdf(title=record["title"], doi=record["doi"])
        url = "https://repository.example/article/_pdf"
        client = StaticClient(
            [
                FetchResult(
                    True,
                    "fetched",
                    status_code=200,
                    data=public_pdf,
                    content_type="application/pdf",
                    final_url=url,
                    attempts=1,
                ),
                FetchResult(
                    True,
                    "fetched",
                    status_code=200,
                    data=public_pdf,
                    content_type="application/pdf",
                    final_url=url,
                    attempts=1,
                ),
            ]
        )
        candidates = [
            {
                "source": "fixture:landing",
                "url": url,
                "kind": "landing",
                "license": "",
                "access_evidence": "fixture",
            }
        ]
        with patch.object(network_acquire, "discover_network_candidates", return_value=(candidates, [])):
            result = network_acquire.acquire_network_record(tmp_path, record, client)

        destination = tmp_path / network_acquire.PDF_DIR / record["destination_filename"]
        assert result["pdf_status"] == "downloaded"
        assert destination.read_bytes() == public_pdf
        assert [attempt["status"] for attempt in result["attempts"]] == [
            "landing_resolved_to_pdf",
            "pypdf_valid",
        ]


def test_structurally_valid_wrong_paper_is_rejected_before_correct_candidate_is_saved():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        record = load_network_records(ROOT, NETWORK_PATH)[0]
        wrong_paper = make_pdf(title="A completely unrelated publication", doi="10.9999/wrong-paper")
        correct_paper = make_pdf(title=record["title"], doi=record["doi"])
        client = StaticClient(
            [
                FetchResult(
                    True,
                    "fetched",
                    status_code=200,
                    data=wrong_paper,
                    content_type="application/pdf",
                    final_url="https://repository.example/wrong.pdf",
                    attempts=1,
                ),
                FetchResult(
                    True,
                    "fetched",
                    status_code=200,
                    data=correct_paper,
                    content_type="application/pdf",
                    final_url="https://repository.example/correct.pdf",
                    attempts=1,
                ),
            ]
        )
        candidates = [
            {
                "source": "fixture:wrong",
                "url": "https://repository.example/wrong.pdf",
                "kind": "direct",
                "license": "",
                "access_evidence": "fixture",
            },
            {
                "source": "fixture:correct",
                "url": "https://repository.example/correct.pdf",
                "kind": "direct",
                "license": "",
                "access_evidence": "fixture",
            },
        ]
        with patch.object(network_acquire, "discover_network_candidates", return_value=(candidates, [])):
            result = network_acquire.acquire_network_record(tmp_path, record, client)

        destination = tmp_path / network_acquire.PDF_DIR / record["destination_filename"]
        assert result["pdf_status"] == "downloaded"
        assert result["downloaded_url"] == "https://repository.example/correct.pdf"
        assert destination.read_bytes() == correct_paper
        assert result["attempts"][0]["validation_status"] == "pypdf_valid"
        assert result["attempts"][0]["status"] == "identity_mismatch"
        assert result["attempts"][0]["identity_status"] == "unverified_no_identifier_match"


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"passed {len(tests)} network PDF acquisition tests")
