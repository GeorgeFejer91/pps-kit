"""Development-only oracle capture; no Python is used by native generation/planning.

Executes only the named existing pure functions (AST extraction avoids GUI/native imports).
The committed fixture records CPython version and reference-file SHA-256 values.
"""
import ast
import hashlib
import itertools
import json
import random
import runpy
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / "packages/pps-runtime/src/peripersonal_space_toolkit"
participant_path = SOURCE / "participant_orders.py"
dashboard_path = SOURCE / "dashboard_app.py"
ns = {"Any": Any, "random": random, "itertools": itertools,
      "participant_order": runpy.run_path(str(participant_path))["participant_order"]}
names = {"_run_setup_phase_labels", "_run_setup_phase_title", "_block_order_permutations", "_run_setup_preview_rows"}
tree = ast.parse(dashboard_path.read_text(encoding="utf-8"))
selected = ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names], type_ignores=[])
exec(compile(selected, str(dashboard_path), "exec"), ns)

cases = []
for count, participants, structure, seed, policy in [
    (1, 4, "pre_post", 0, None),
    (2, 8, "pre_post", -7, None),
    (6, 50, "pre_post", 20256604, None),
    (8, 5, "single", 2**60 + 31, None),
    (4, 10, "pre_post", 11, {"algorithm": "counterbalanced_rotation", "seed": 17}),
    (4, 7, "single", 11, {"algorithm": "seeded_random_permutation", "seed": -19}),
    (4, 2, "pre_post", 11, {"algorithm": "fixed", "seed": 19, "part_membership": {"pre": ["Block 01", "Block 03"], "2": ["Block 02", "Block 04"]}}),
    (3, 20, "pre_post", 11, {"algorithm": "seeded_factoradic_cycle.v1", "seed": 19}),
    (20, 3, "single", 11, {"algorithm": "seeded_factoradic_cycle.v1", "seed": 19}),
]:
    blocks = [{"block_index": i, "block_label": f"Block {i:02}", "csv_file_name": f"static_block_{i:02}.csv", "trial_count": 34, "duration_ms": 272000} for i in range(1, count+1)]
    design = {"protocol": {"participants": participants, "random_seed": seed, "participant_order_policy": policy}, "study_profile_reference_parameters": {"dashboard_run_setup": {"experiment_structure": structure, "seed": seed}}}
    rows, occurrences = ns["_run_setup_preview_rows"](blocks, participant_count=participants, structure=structure, seed=seed, order_policy=policy)
    cases.append({"design": design, "source_preview": {"blocks": blocks}, "rows": rows, "csv_rows": occurrences})

fixture = {"schema": "pps-native-run-order-oracle.v1", "python_version": sys.version, "references": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [participant_path, dashboard_path]}, "cases": cases}
Path(__file__).with_name("run_order_oracle.json").write_text(json.dumps(fixture, separators=(",", ":")) + "\n", encoding="utf-8")
