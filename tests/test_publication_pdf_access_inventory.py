from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.build_publication_pdf_access_inventory import (
    INVENTORY_FILENAME,
    NON_CREDENTIAL_CLASSES,
    OUTPUT_DIR,
    REQUEST_FILENAME,
    REQUEST_MARKDOWN_FILENAME,
    build_inventory,
    generated_outputs,
)


EXPECTED_CREDENTIAL_DOIS = {
    "10.1007/s00221-004-2212-7",
    "10.1007/s00221-005-2393-8",
    "10.1007/s00221-013-3574-5",
    "10.1007/s00221-017-5158-2",
    "10.1007/s10548-021-00826-4",
    "10.1016/j.actpsy.2004.10.017",
    "10.1016/j.cortex.2017.08.033",
    "10.1016/j.neuropsychologia.2006.12.004",
    "10.1016/j.neuropsychologia.2009.11.009",
    "10.1016/j.neuropsychologia.2014.09.043",
    "10.1016/j.neuropsychologia.2021.107823",
    "10.1080/17470210903068989",
    "10.1093/neucas/7.2.97",
    "10.1162/089892902320474481",
}
AUTOMATABLE_OR_NON_MAIN_DOIS = {
    "10.1250/ast.41.345",  # J-STAGE PDF is local.
    "10.53829/ntr201911fa4",  # Public AES PDF is local.
    "10.61782/fa.2025.0866",  # Public AES PDF is local.
    "10.17605/osf.io/73x59",  # Project record has no distinct main paper.
    "10.3233/rnn-120286",  # Exact public PDF verified, but blocked to automation.
    "10.1523/jneurosci.1696-15.2015",  # Public full HTML is usable.
    "10.1177/17470218241261645",  # The public preprint is local under its DOI.
}


def _read_csv(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def test_publication_pdf_access_outputs_are_exact_valid_and_deterministic():
    inventory, requests, summary = build_inventory(ROOT)
    outputs, regenerated_summary = generated_outputs(ROOT)

    assert regenerated_summary == summary
    assert summary["network_count"] == 94
    assert summary["local_pdf_count"] == 58
    assert summary["unresolved_count"] == 36
    assert summary["credential_request_count"] == 14
    assert len(inventory) == len({row["doi"] for row in inventory}) == 94
    assert len(requests) == len({row["doi"] for row in requests}) == 14
    assert {row["doi"] for row in requests} == EXPECTED_CREDENTIAL_DOIS

    by_doi = {row["doi"]: row for row in inventory}
    assert all(by_doi[doi]["credentials_required"] == "no" for doi in AUTOMATABLE_OR_NON_MAIN_DOIS)
    assert all(
        row["credentials_required"] == "no"
        for row in inventory
        if row["public_access_class"] in NON_CREDENTIAL_CLASSES
    )

    local_rows = [row for row in inventory if row["local_status"] == "validated_local_main_pdf"]
    assert len(local_rows) == 58
    assert all(len(row["local_sha256"]) == 64 and int(row["local_page_count"]) > 0 for row in local_rows)
    assert all((ROOT / row["local_path"]).is_file() for row in local_rows)

    assert len(_read_csv(outputs[INVENTORY_FILENAME])) == 94
    assert len(_read_csv(outputs[REQUEST_FILENAME])) == 14
    assert "Exactly **14 publications**" in outputs[REQUEST_MARKDOWN_FILENAME]
    for filename, content in outputs.items():
        assert (ROOT / OUTPUT_DIR / filename).read_text(encoding="utf-8") == content


if __name__ == "__main__":
    test_publication_pdf_access_outputs_are_exact_valid_and_deterministic()
    print("passed publication PDF access inventory test")
