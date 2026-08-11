#!/usr/bin/env python3
"""Build matrices for the Toolkit's exact current StimulusDesign inputs."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from current_toolkit_input_schema import (
    CURRENT_TOOLKIT_INPUTS,
    REPO_ROOT,
    schema_document,
)


DEFAULT_OUTPUT_DIR = (
    REPO_ROOT
    / "For-AI/audiotactile-paper-metadata-audit/publication-parameter-matrix"
)
DEFAULT_SCHEMA_OUTPUT = REPO_ROOT / "tools/current_toolkit_input_schema.json"
STUDY_TEMPLATE_DIR = REPO_ROOT / "study_templates"

CELL_STATUS_DESCRIPTIONS = {
    "serialized_explicit": (
        "Every attached profile explicitly supplies this input path directly or through a "
        "tracked StudyTemplate loader alias."
    ),
    "typed_or_parser_default_not_serialized": (
        "The path is omitted and the current dataclass/parser supplies its defined default."
    ),
    "partially_serialized_with_defaults": (
        "At least one repeated entity explicitly serializes the path and another uses its default."
    ),
    "repeatable_entity_absent": (
        "The owning repeatable entity list is absent or empty, so this leaf has no instance."
    ),
    "required_field_missing": (
        "A present repeated entity omits a constructor-required leaf; the serialized input is invalid."
    ),
    "invalid_serialized_shape": "The stored JSON shape is incompatible with the typed path.",
    "mixed": "Attached profiles or registered study instances have different categorical states.",
    "no_profile": "No current study template/profile is attached to this row.",
}


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _load_templates() -> dict[str, dict[str, Any]]:
    templates: dict[str, dict[str, Any]] = {}
    for path in sorted(STUDY_TEMPLATE_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        template_id = str(data.get("template_id") or "").strip()
        if not template_id:
            raise RuntimeError(f"Study template has no template_id: {path}")
        if template_id in templates:
            raise RuntimeError(f"Duplicate study template ID: {template_id}")
        templates[template_id] = {**data, "_source_file": str(path.relative_to(REPO_ROOT))}
    return templates


def _profile_ids(raw: str) -> list[str]:
    return [item.strip() for item in str(raw or "").split("|") if item.strip()]


def _aggregate_statuses(statuses: list[str], *, empty: str) -> str:
    normalized = sorted(set(statuses))
    if not normalized:
        return empty
    if len(normalized) == 1:
        return normalized[0]
    if set(normalized) <= {
        "serialized_explicit",
        "typed_or_parser_default_not_serialized",
        "partially_serialized_with_defaults",
    }:
        return "partially_serialized_with_defaults"
    return "mixed"


def _resolve_profile_path(
    design: Any,
    parameter: dict[str, Any],
) -> tuple[str, list[Any]]:
    """Return categorical literal-presence status and explicit values."""

    traversal = parameter["traversal"]
    required = bool(parameter["required"])

    def walk(node: Any, index: int) -> tuple[str, list[Any]]:
        step = traversal[index]
        field = step["field"]
        repeated = bool(step["repeated"])
        is_leaf = index == len(traversal) - 1

        if not isinstance(node, dict):
            return "invalid_serialized_shape", []
        if repeated:
            if field not in node or node[field] in (None, []):
                return "repeatable_entity_absent", []
            values = node[field]
            if not isinstance(values, list):
                return "invalid_serialized_shape", []
            child_results = [walk(child, index + 1) for child in values]
            statuses = [status for status, _ in child_results]
            explicit_values = [
                value
                for _, child_values in child_results
                for value in child_values
            ]
            return _aggregate_statuses(statuses, empty="repeatable_entity_absent"), explicit_values

        if is_leaf:
            if field in node:
                return "serialized_explicit", [node[field]]
            if required:
                return "required_field_missing", []
            return "typed_or_parser_default_not_serialized", []

        if field not in node or node[field] is None:
            # The only non-repeated intermediate objects in the current root are
            # trajectory and protocol, both constructed from an empty dict when
            # omitted.  Their descendants therefore use typed/parser defaults.
            return "typed_or_parser_default_not_serialized", []
        return walk(node[field], index + 1)

    return walk(design, 0)


def _template_parameter_state(
    template: dict[str, Any],
    parameter: dict[str, Any],
) -> tuple[str, list[Any]]:
    template_source_path = str(parameter.get("accepted_template_source_path") or "")
    if template_source_path:
        if template_source_path in template:
            return "serialized_explicit", [template[template_source_path]]
        if parameter.get("template_alias_required"):
            return "required_field_missing", []
        return "typed_or_parser_default_not_serialized", []
    design = template.get("design")
    if not isinstance(design, dict):
        return "invalid_serialized_shape", []
    return _resolve_profile_path(design, parameter)


def _summary_fields(statuses: dict[str, str]) -> dict[str, Any]:
    counts = Counter(statuses.values())
    return {
        "current_input_parameter_count": len(CURRENT_TOOLKIT_INPUTS),
        "serialized_explicit_count": counts["serialized_explicit"],
        "default_not_serialized_count": counts["typed_or_parser_default_not_serialized"],
        "partially_serialized_count": counts["partially_serialized_with_defaults"],
        "repeatable_entity_absent_count": counts["repeatable_entity_absent"],
        "required_field_missing_count": counts["required_field_missing"],
        "invalid_serialized_shape_count": counts["invalid_serialized_shape"],
        "mixed_count": counts["mixed"],
        "no_profile_count": counts["no_profile"],
    }


def build_matrices(output_dir: Path) -> dict[str, Any]:
    study_index_path = output_dir / "study_instance_index.csv"
    publication_index_path = output_dir / "publication_study_index.csv"
    if not study_index_path.exists() or not publication_index_path.exists():
        raise RuntimeError(
            "Run tools/build_publication_parameter_review_matrix.mjs first; "
            "the current-input matrices use its registered study/publication indices."
        )

    study_index = _read_csv(study_index_path)
    publication_index = _read_csv(publication_index_path)
    templates = _load_templates()
    parameter_paths = [item["serialized_path"] for item in CURRENT_TOOLKIT_INPUTS]

    study_rows: list[dict[str, Any]] = []
    value_rows: list[dict[str, Any]] = []
    publication_value_rows: list[dict[str, Any]] = []
    rows_by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source_row in study_index:
        profile_ids = _profile_ids(source_row.get("profile_id", ""))
        missing_profiles = sorted(set(profile_ids) - set(templates))
        if missing_profiles:
            raise RuntimeError(
                f"Unknown profile ID(s) on {source_row['study_row_id']}: {', '.join(missing_profiles)}"
            )
        parameter_statuses: dict[str, str] = {}
        for parameter in CURRENT_TOOLKIT_INPUTS:
            path = parameter["serialized_path"]
            per_profile: list[str] = []
            for profile_id in profile_ids:
                status, explicit_values = _template_parameter_state(templates[profile_id], parameter)
                per_profile.append(status)
                value_rows.append(
                    {
                        "study_row_id": source_row["study_row_id"],
                        "network_node_id": source_row["network_node_id"],
                        "profile_id": profile_id,
                        "profile_source_file": templates[profile_id]["_source_file"],
                        "current_toolkit_input_path": path,
                        "categorical_status": status,
                        "explicit_value_count": len(explicit_values),
                        "explicit_values_json": json.dumps(
                            explicit_values,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        "default_value_json": parameter["default_value_json"],
                    }
                )
            parameter_statuses[path] = _aggregate_statuses(per_profile, empty="no_profile")

        row = {
            "study_row_id": source_row["study_row_id"],
            "network_node_id": source_row["network_node_id"],
            "study_label": source_row["study_label"],
            "experiment_letter": source_row["experiment_letter"],
            "experiment_label": source_row["experiment_label"],
            "toolkit_scope": source_row["toolkit_scope"],
            "profile_ids": " | ".join(profile_ids),
            "profile_count": len(profile_ids),
            **_summary_fields(parameter_statuses),
            **parameter_statuses,
        }
        study_rows.append(row)
        rows_by_node[source_row["network_node_id"]].append(row)

    publication_rows: list[dict[str, Any]] = []
    for source_row in publication_index:
        node_id = source_row["node_id"]
        instances = rows_by_node.get(node_id, [])
        if not instances:
            raise RuntimeError(f"Publication index node has no registered study row: {node_id}")
        publication_profile_ids = _profile_ids(source_row.get("template_ids", ""))
        missing_profiles = sorted(set(publication_profile_ids) - set(templates))
        if missing_profiles:
            raise RuntimeError(
                f"Unknown publication profile ID(s) on {node_id}: {', '.join(missing_profiles)}"
            )
        child_rows_with_profiles = [row for row in instances if int(row["profile_count"]) > 0]
        if not publication_profile_ids:
            publication_profile_scope = "no_profile"
        elif len(instances) > 1 and not child_rows_with_profiles:
            publication_profile_scope = "composite_profile_not_experiment_scoped"
        elif len(instances) > 1 and len(child_rows_with_profiles) < len(instances):
            publication_profile_scope = "mixed_publication_and_experiment_scope"
        elif len(instances) > 1:
            publication_profile_scope = "experiment_or_variant_scoped_profiles"
        else:
            publication_profile_scope = "publication_and_single_review_unit_profile"

        statuses: dict[str, str] = {}
        for parameter in CURRENT_TOOLKIT_INPUTS:
            path = parameter["serialized_path"]
            per_profile: list[str] = []
            for profile_id in publication_profile_ids:
                status, explicit_values = _template_parameter_state(templates[profile_id], parameter)
                per_profile.append(status)
                publication_value_rows.append(
                    {
                        "network_node_id": node_id,
                        "publication_profile_scope": publication_profile_scope,
                        "profile_id": profile_id,
                        "profile_source_file": templates[profile_id]["_source_file"],
                        "current_toolkit_input_path": path,
                        "categorical_status": status,
                        "explicit_value_count": len(explicit_values),
                        "explicit_values_json": json.dumps(
                            explicit_values,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        "default_value_json": parameter["default_value_json"],
                    }
                )
            statuses[path] = _aggregate_statuses(per_profile, empty="no_profile")
        publication_rows.append(
            {
                "network_node_id": node_id,
                "title": source_row["title"],
                "year": source_row["year"],
                "doi": source_row["doi"],
                "toolkit_status": source_row["toolkit_status"],
                "study_instance_count": len(instances),
                "study_row_ids": " | ".join(row["study_row_id"] for row in instances),
                "profile_ids": " | ".join(publication_profile_ids),
                "profile_count": len(publication_profile_ids),
                "publication_profile_scope": publication_profile_scope,
                "study_rows_with_experiment_scoped_profiles": len(child_rows_with_profiles),
                "study_rows_without_experiment_scoped_profiles": (
                    len(instances) - len(child_rows_with_profiles)
                ),
                **_summary_fields(statuses),
                **statuses,
            }
        )

    study_metadata = [
        "study_row_id",
        "network_node_id",
        "study_label",
        "experiment_letter",
        "experiment_label",
        "toolkit_scope",
        "profile_ids",
        "profile_count",
        "current_input_parameter_count",
        "serialized_explicit_count",
        "default_not_serialized_count",
        "partially_serialized_count",
        "repeatable_entity_absent_count",
        "required_field_missing_count",
        "invalid_serialized_shape_count",
        "mixed_count",
        "no_profile_count",
    ]
    publication_metadata = [
        "network_node_id",
        "title",
        "year",
        "doi",
        "toolkit_status",
        "study_instance_count",
        "study_row_ids",
        "profile_ids",
        "profile_count",
        "publication_profile_scope",
        "study_rows_with_experiment_scoped_profiles",
        "study_rows_without_experiment_scoped_profiles",
        "current_input_parameter_count",
        "serialized_explicit_count",
        "default_not_serialized_count",
        "partially_serialized_count",
        "repeatable_entity_absent_count",
        "required_field_missing_count",
        "invalid_serialized_shape_count",
        "mixed_count",
        "no_profile_count",
    ]
    value_columns = [
        "study_row_id",
        "network_node_id",
        "profile_id",
        "profile_source_file",
        "current_toolkit_input_path",
        "categorical_status",
        "explicit_value_count",
        "explicit_values_json",
        "default_value_json",
    ]
    publication_value_columns = [
        "network_node_id",
        "publication_profile_scope",
        "profile_id",
        "profile_source_file",
        "current_toolkit_input_path",
        "categorical_status",
        "explicit_value_count",
        "explicit_values_json",
        "default_value_json",
    ]
    dictionary_columns = [key for key in CURRENT_TOOLKIT_INPUTS[0] if key != "traversal"]
    dictionary_rows = [
        {
            key: (
                str(value).lower()
                if isinstance(value, bool)
                else value
            )
            for key, value in parameter.items()
            if key != "traversal"
        }
        for parameter in CURRENT_TOOLKIT_INPUTS
    ]
    legend_rows = [
        {
            "categorical_status": status,
            "meaning": description,
            "manual_review_implication": (
                "No current profile value is available to compare with the publication."
                if status == "no_profile"
                else "Inspect the value sidecar and publication evidence before changing the profile."
            ),
        }
        for status, description in CELL_STATUS_DESCRIPTIONS.items()
    ]

    _write_csv(
        output_dir / "study_instance_current_toolkit_input_matrix.csv",
        study_rows,
        [*study_metadata, *parameter_paths],
    )
    _write_csv(
        output_dir / "publication_current_toolkit_input_matrix.csv",
        publication_rows,
        [*publication_metadata, *parameter_paths],
    )
    _write_csv(
        output_dir / "current_toolkit_input_dictionary.csv",
        dictionary_rows,
        dictionary_columns,
    )
    _write_csv(
        output_dir / "current_toolkit_input_values.csv",
        value_rows,
        value_columns,
    )
    _write_csv(
        output_dir / "publication_current_toolkit_input_values.csv",
        publication_value_rows,
        publication_value_columns,
    )
    _write_csv(
        output_dir / "current_toolkit_input_status_legend.csv",
        legend_rows,
        ["categorical_status", "meaning", "manual_review_implication"],
    )
    return {
        "current_toolkit_input_count": len(CURRENT_TOOLKIT_INPUTS),
        "study_instance_count": len(study_rows),
        "publication_count": len(publication_rows),
        "attached_profile_value_rows": len(value_rows),
        "publication_profile_value_rows": len(publication_value_rows),
        "output_dir": _display_path(output_dir),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--schema-output", type=Path, default=DEFAULT_SCHEMA_OUTPUT)
    parser.add_argument("--schema-only", action="store_true")
    args = parser.parse_args()

    schema_output = args.schema_output.resolve()
    schema_output.parent.mkdir(parents=True, exist_ok=True)
    schema_output.write_text(
        json.dumps(schema_document(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if args.schema_only:
        result = {
            "current_toolkit_input_count": len(CURRENT_TOOLKIT_INPUTS),
            "schema_output": _display_path(schema_output),
        }
    else:
        result = build_matrices(args.output.resolve())
        result["schema_output"] = _display_path(schema_output)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
