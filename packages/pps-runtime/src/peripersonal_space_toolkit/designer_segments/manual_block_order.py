"""Spreadsheet templates and exact within-block permutations of trusted trial rows."""

from __future__ import annotations

import csv
import io
import re
from typing import Any

from ..resource_limits import MAX_DOCUMENT_BYTES

MANUAL_BLOCK_ORDER = "manual_csv_order"
_TEMPLATE_COLUMNS = ("template_id", "trial_pool_index", "family", "row_label", "soa_ms", "noise_type", "sequence_labels")


def manual_block_template(rows: list[dict[str, Any]], template_id: str) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=_TEMPLATE_COLUMNS)
    writer.writeheader()
    for row in rows:
        values = {key: row.get(key, "") for key in _TEMPLATE_COLUMNS[1:]}
        # Spreadsheet programs may interpret editable design labels as formulas.
        for key in ("row_label", "sequence_labels"):
            value = str(values[key])
            if re.match(r"^\s*[=+@-]", value):
                values[key] = "'" + value
        writer.writerow({"template_id": template_id, **values})
    return output.getvalue()


def apply_manual_block_order(
    blocks: list[list[dict[str, Any]]], files: Any, template_scope: str,
) -> list[list[dict[str, Any]]]:
    if not isinstance(files, list) or len(files) != len(blocks) or not all(isinstance(file, str) for file in files):
        raise ValueError("Select one CSV per block.")
    if sum(len(file.encode("utf-8")) for file in files) > MAX_DOCUMENT_BYTES:
        raise ValueError("The selected CSVs exceed the 8 MiB import limit.")
    return [
        _read_block_order(rows, content, f"{template_scope}-{index}", index)
        for index, (rows, content) in enumerate(zip(blocks, files), start=1)
    ]


def _read_block_order(
    rows: list[dict[str, Any]], content: str, template_id: str, block_index: int,
) -> list[dict[str, Any]]:
    label = f"Block {block_index:02d}"
    content = content.removeprefix("\ufeff")
    first_line = content.partition("\n")[0]
    delimiter = ";" if ";" in first_line and "," not in first_line else ","
    reader = csv.DictReader(io.StringIO(content, newline=""), delimiter=delimiter, strict=True)
    by_id = {str(row["trial_pool_index"]): row for row in rows}
    ordered = []
    seen = set()
    try:
        header = reader.fieldnames or []
        if len(set(header)) != len(header) or not {"template_id", "trial_pool_index"} <= set(header):
            raise ValueError(f"{label}: keep the template_id and trial_pool_index headers.")
        for row in reader:
            if not any(row.values()):
                continue
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"{label}, line {reader.line_num}: the CSV columns do not match the header.")
            if row["template_id"] != template_id:
                raise ValueError(f"{label}, line {reader.line_num}: use the current template for this block.")
            trial_id = row["trial_pool_index"].strip()
            if trial_id not in by_id:
                raise ValueError(f"{label}, line {reader.line_num}: unknown trial ID for this block.")
            if trial_id in seen:
                raise ValueError(f"{label}, line {reader.line_num}: duplicate trial ID {trial_id}.")
            seen.add(trial_id)
            ordered.append(by_id[trial_id])
    except csv.Error as exc:
        raise ValueError(f"{label}, line {reader.line_num}: invalid CSV.") from exc
    if len(ordered) != len(rows):
        raise ValueError(f"{label}: {len(rows) - len(ordered)} required trial rows are missing.")
    return ordered
