#!/usr/bin/env python3
"""Derive the current StimulusDesign JSON input contract without importing it.

The design module imports optional scientific dependencies, so this inventory is
intentionally based on Python's AST.  It follows only dataclass-to-dataclass
relationships rooted at ``StimulusDesign``.  Primitive lists and arbitrary
``dict`` fields remain atomic JSON inputs; lists of dataclasses are expanded
with ``[]`` path markers.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DESIGN_SOURCE = REPO_ROOT / "src/peripersonal_space_toolkit/design.py"
TEMPLATE_SOURCE = REPO_ROOT / "src/peripersonal_space_toolkit/templates.py"
ROOT_DATACLASS = "StimulusDesign"
ROOT_JSON_PREFIX = "design"
PARSER = "peripersonal_space_toolkit.design.design_from_dict"
SERIALIZER = "peripersonal_space_toolkit.design.design_to_dict"
TEMPLATE_PARSER = "peripersonal_space_toolkit.templates.template_from_dict"
TEMPLATE_FIELD_ALIASES = {
    "design.study_profile_id": ("template_id", True),
    "design.study_profile_title": ("title", True),
    "design.study_profile_notes": ("notes", False),
    "design.study_profile_reference_parameters": ("reference_parameters", False),
}


@dataclass(frozen=True)
class FieldDefinition:
    owner: str
    name: str
    annotation_node: ast.expr
    annotation: str
    default_node: ast.expr | None
    source_line: int


def _is_dataclass(class_node: ast.ClassDef) -> bool:
    return any(
        (isinstance(decorator, ast.Name) and decorator.id == "dataclass")
        or (isinstance(decorator, ast.Attribute) and decorator.attr == "dataclass")
        for decorator in class_node.decorator_list
    )


def _safe_eval(node: ast.AST, constants: dict[str, Any]) -> Any:
    """Evaluate the small literal subset used by design dataclass defaults."""

    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in constants:
            return constants[node.id]
        raise ValueError(node.id)
    if isinstance(node, ast.List):
        return [_safe_eval(item, constants) for item in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_safe_eval(item, constants) for item in node.elts)
    if isinstance(node, ast.Set):
        return {_safe_eval(item, constants) for item in node.elts}
    if isinstance(node, ast.Dict):
        return {
            _safe_eval(key, constants): _safe_eval(value, constants)
            for key, value in zip(node.keys, node.values)
        }
    if isinstance(node, ast.UnaryOp):
        value = _safe_eval(node.operand, constants)
        if isinstance(node.op, ast.USub):
            return -value
        if isinstance(node.op, ast.UAdd):
            return +value
        if isinstance(node.op, ast.Not):
            return not value
    if isinstance(node, ast.BinOp):
        left = _safe_eval(node.left, constants)
        right = _safe_eval(node.right, constants)
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id == "list":
            return list(_safe_eval(node.args[0], constants)) if node.args else []
        if node.func.id == "dict" and not node.args and not node.keywords:
            return {}
        if node.func.id == "tuple":
            return tuple(_safe_eval(node.args[0], constants)) if node.args else ()
    raise ValueError(ast.unparse(node))


def _module_constants(module: ast.Module) -> dict[str, Any]:
    constants: dict[str, Any] = {}
    for statement in module.body:
        name = None
        value = None
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
            if isinstance(target, ast.Name):
                name, value = target.id, statement.value
        elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            name, value = statement.target.id, statement.value
        if not name or value is None:
            continue
        try:
            constants[name] = _safe_eval(value, constants)
        except (TypeError, ValueError):
            continue
    return constants


def _dataclass_fields(module: ast.Module) -> dict[str, list[FieldDefinition]]:
    definitions: dict[str, list[FieldDefinition]] = {}
    for statement in module.body:
        if not isinstance(statement, ast.ClassDef) or not _is_dataclass(statement):
            continue
        fields: list[FieldDefinition] = []
        for item in statement.body:
            if not isinstance(item, ast.AnnAssign) or not isinstance(item.target, ast.Name):
                continue
            fields.append(
                FieldDefinition(
                    owner=statement.name,
                    name=item.target.id,
                    annotation_node=item.annotation,
                    annotation=ast.unparse(item.annotation),
                    default_node=item.value,
                    source_line=item.lineno,
                )
            )
        definitions[statement.name] = fields
    return definitions


def _template_alias_metadata(source_path: Path = TEMPLATE_SOURCE) -> dict[str, dict[str, Any]]:
    """Trace the four top-level StudyTemplate-to-design assignments."""

    module = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    function = next(
        (
            node
            for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == "template_from_dict"
        ),
        None,
    )
    if function is None:
        raise RuntimeError("templates.py must define template_from_dict")
    assignments = {
        f"design.{statement.targets[0].attr}": statement
        for statement in function.body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Attribute)
        and isinstance(statement.targets[0].value, ast.Name)
        and statement.targets[0].value.id == "design"
    }
    metadata: dict[str, dict[str, Any]] = {}
    for serialized_path, (template_path, template_required) in TEMPLATE_FIELD_ALIASES.items():
        assignment = assignments.get(serialized_path)
        if assignment is None or template_path not in ast.unparse(assignment.value):
            raise RuntimeError(
                f"Expected template_from_dict alias {template_path} -> {serialized_path}"
            )
        metadata[serialized_path] = {
            "accepted_via_template_parser": True,
            "accepted_template_source_path": template_path,
            "template_alias_required": template_required,
            "template_parser": TEMPLATE_PARSER,
            "template_parser_handling": ast.unparse(assignment),
            "template_parser_source_file": str(source_path.relative_to(REPO_ROOT)),
            "template_parser_source_line": assignment.lineno,
        }
    return metadata


def _nested_dataclass(annotation: ast.expr, dataclass_names: set[str]) -> tuple[str, bool] | None:
    if isinstance(annotation, ast.Name) and annotation.id in dataclass_names:
        return annotation.id, False
    if isinstance(annotation, ast.Subscript) and isinstance(annotation.value, ast.Name):
        if annotation.value.id != "list":
            return None
        element = annotation.slice
        if isinstance(element, ast.Name) and element.id in dataclass_names:
            return element.id, True
    return None


def _default_metadata(field: FieldDefinition, constants: dict[str, Any]) -> dict[str, Any]:
    node = field.default_node
    if node is None:
        return {
            "required": True,
            "default_kind": "required",
            "default_source": "",
            "default_value_json": "",
        }

    source = ast.unparse(node)
    default_kind = "literal_or_constant"
    value_node: ast.AST = node
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "field":
        default_kind = "factory"
        factory = next((keyword.value for keyword in node.keywords if keyword.arg == "default_factory"), None)
        if factory is None:
            return {
                "required": False,
                "default_kind": "field_configuration",
                "default_source": source,
                "default_value_json": "",
            }
        if isinstance(factory, ast.Lambda):
            value_node = factory.body
        elif isinstance(factory, ast.Name) and factory.id in {"dict", "list", "tuple"}:
            value_node = ast.Call(func=factory, args=[], keywords=[])
        else:
            return {
                "required": False,
                "default_kind": default_kind,
                "default_source": source,
                "default_value_json": "",
            }
    try:
        value = _safe_eval(value_node, constants)
        default_value_json = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        default_value_json = ""
    return {
        "required": False,
        "default_kind": default_kind,
        "default_source": source,
        "default_value_json": default_value_json,
    }


def _json_type(annotation: ast.expr) -> str:
    if isinstance(annotation, ast.Name):
        return {
            "str": "string",
            "int": "integer",
            "float": "number",
            "bool": "boolean",
            "Any": "any",
        }.get(annotation.id, "object")
    if isinstance(annotation, ast.Subscript) and isinstance(annotation.value, ast.Name):
        container = annotation.value.id
        if container == "list":
            return f"array[{_json_type(annotation.slice)}]"
        if container == "dict":
            return "object"
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        parts = [_json_type(annotation.left), _json_type(annotation.right)]
        return "|".join(dict.fromkeys(parts))
    if isinstance(annotation, ast.Constant) and annotation.value is None:
        return "null"
    return "unknown"


def _unit_hint(field_name: str) -> str:
    for suffix, unit in (
        ("_mps", "m/s"),
        ("_ms", "ms"),
        ("_cm", "cm"),
        ("_deg", "degrees"),
        ("_s", "s"),
        ("_m", "m"),
    ):
        if field_name.endswith(suffix):
            return unit
    if field_name == "sample_rate":
        return "Hz"
    if field_name.endswith("_percentage"):
        return "percent"
    return ""


def _parameter_group(path_parts: list[str]) -> str:
    joined = ".".join(path_parts)
    if joined.startswith("design.noises[]"):
        return "generated_audio_sources"
    if joined.startswith("design.custom_looming_files[]"):
        return "custom_looming_audio_sources"
    if joined.startswith("design.prestimulus_files[]"):
        return "prestimulus_audio_sources"
    if joined.startswith("design.trajectory"):
        return "trajectory"
    if joined.startswith("design.protocol.block_specs[]"):
        return "block_specs"
    if joined.startswith("design.protocol.trial_strips[].elements[]"):
        return "trial_strip_elements"
    if joined.startswith("design.protocol.trial_strips[]"):
        return "trial_strips"
    if joined.startswith("design.protocol"):
        return "protocol"
    return "design_identity_and_assets"


def _parser_handling(path: str) -> str:
    if path.startswith("design.noises[]"):
        return "NoiseDefinition(**item), followed by generated-source-profile normalization"
    if path.startswith("design.custom_looming_files[]"):
        return "_audio_file_specs_from_dicts(..., default_motion_mode='looming'); AudioFileSpec(**data)"
    if path.startswith("design.prestimulus_files[]"):
        return "_audio_file_specs_from_dicts(..., default_motion_mode='stationary'); AudioFileSpec(**data)"
    if path.startswith("design.trajectory."):
        return "TrajectorySpec(**trajectory_data); coordinate_mode may be inferred for Cartesian coordinates"
    if path.startswith("design.protocol.block_specs[]"):
        return "BlockSpec(**item), with string-label shorthand accepted"
    if path.startswith("design.protocol.trial_strips[].elements[]"):
        return "TrialStripElementSpec(**element), followed by source-label normalization"
    if path.startswith("design.protocol.trial_strips[]"):
        return "_trial_strip_specs_from_dicts; numeric-list and optional-float normalization"
    if path.startswith("design.protocol."):
        return "ProtocolSpec(**protocol_data); catch/audio-only inclusion may be inferred when omitted"
    return "StimulusDesign keyword selected by design_from_dict"


def derive_current_toolkit_inputs(source_path: Path = DESIGN_SOURCE) -> list[dict[str, Any]]:
    """Return ordered atomic input metadata for the current serialized design."""

    source = source_path.read_text(encoding="utf-8")
    module = ast.parse(source, filename=str(source_path))
    functions = {node.name: node for node in module.body if isinstance(node, ast.FunctionDef)}
    if "design_from_dict" not in functions or "design_to_dict" not in functions:
        raise RuntimeError("design.py must define design_from_dict and design_to_dict")
    if "asdict(design)" not in ast.unparse(functions["design_to_dict"]):
        raise RuntimeError("Schema exporter expects design_to_dict to serialize with asdict(design)")

    constants = _module_constants(module)
    definitions = _dataclass_fields(module)
    template_aliases = _template_alias_metadata()
    if ROOT_DATACLASS not in definitions:
        raise RuntimeError(f"Missing root dataclass {ROOT_DATACLASS}")

    inputs: list[dict[str, Any]] = []

    def visit(
        class_name: str,
        path_parts: list[str],
        traversal: list[dict[str, Any]],
        repeatable_paths: list[str],
    ) -> None:
        for field in definitions[class_name]:
            nested = _nested_dataclass(field.annotation_node, set(definitions))
            if nested:
                nested_name, repeated = nested
                component = f"{field.name}[]" if repeated else field.name
                nested_parts = [*path_parts, component]
                nested_path = ".".join(nested_parts)
                visit(
                    nested_name,
                    nested_parts,
                    [
                        *traversal,
                        {
                            "field": field.name,
                            "repeated": repeated,
                            "owner_dataclass": class_name,
                        },
                    ],
                    [*repeatable_paths, nested_path] if repeated else repeatable_paths,
                )
                continue

            leaf_parts = [*path_parts, field.name]
            serialized_path = ".".join(leaf_parts)
            default = _default_metadata(field, constants)
            inputs.append(
                {
                    "ordinal": len(inputs) + 1,
                    "serialized_path": serialized_path,
                    "parameter_group": _parameter_group(leaf_parts),
                    "owner_dataclass": class_name,
                    "field_name": field.name,
                    "type_annotation": field.annotation,
                    "json_type": _json_type(field.annotation_node),
                    "value_shape": (
                        "object"
                        if _json_type(field.annotation_node) == "object"
                        else "array"
                        if _json_type(field.annotation_node).startswith("array[")
                        else "scalar"
                    ),
                    "unit": _unit_hint(field.name),
                    **default,
                    "repeatable_entity_paths": " | ".join(repeatable_paths),
                    "repeatable_depth": len(repeatable_paths),
                    "accepted_by_parser": True,
                    "emitted_by_serializer": True,
                    "parser": PARSER,
                    "parser_handling": _parser_handling(serialized_path),
                    "serializer": SERIALIZER,
                    "serializer_handling": "dataclasses.asdict(StimulusDesign)",
                    **template_aliases.get(
                        serialized_path,
                        {
                            "accepted_via_template_parser": False,
                            "accepted_template_source_path": "",
                            "template_alias_required": False,
                            "template_parser": "",
                            "template_parser_handling": "",
                            "template_parser_source_file": "",
                            "template_parser_source_line": "",
                        },
                    ),
                    "contract_scope": "current parser/serializer input contract",
                    "runtime_consumer_trace": "not_traced_by_schema_exporter",
                    "source_file": str(source_path.relative_to(REPO_ROOT)),
                    "source_line": field.source_line,
                    "traversal": [
                        *traversal,
                        {
                            "field": field.name,
                            "repeated": False,
                            "owner_dataclass": class_name,
                        },
                    ],
                }
            )

    visit(ROOT_DATACLASS, [ROOT_JSON_PREFIX], [], [])
    paths = [item["serialized_path"] for item in inputs]
    if len(paths) != len(set(paths)):
        raise RuntimeError("Duplicate serialized input path derived from design.py")
    return inputs


CURRENT_TOOLKIT_INPUTS = derive_current_toolkit_inputs()


def schema_document() -> dict[str, Any]:
    return {
        "schema_version": "current-toolkit-input-schema.v1",
        "source_file": str(DESIGN_SOURCE.relative_to(REPO_ROOT)),
        "root_dataclass": ROOT_DATACLASS,
        "root_json_prefix": ROOT_JSON_PREFIX,
        "parser": PARSER,
        "serializer": SERIALIZER,
        "template_parser": TEMPLATE_PARSER,
        "arbitrary_mapping_policy": (
            "dict-valued dataclass fields remain one atomic object input; only nested dataclasses "
            "and lists of nested dataclasses are expanded"
        ),
        "repeatable_path_notation": "[] marks each list-of-dataclass entity boundary",
        "input_count": len(CURRENT_TOOLKIT_INPUTS),
        "inputs": CURRENT_TOOLKIT_INPUTS,
    }


if __name__ == "__main__":
    print(json.dumps(schema_document(), indent=2, ensure_ascii=False) + "\n", end="")
