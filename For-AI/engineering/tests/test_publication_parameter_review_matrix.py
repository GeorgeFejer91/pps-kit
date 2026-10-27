from __future__ import annotations

import csv
import importlib.util
import hashlib
import json
import subprocess
import tempfile
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BUILDER = ROOT / "For-AI" / "research" / "literature" / "tools" / "build_publication_parameter_review_matrix.mjs"
REGISTRY = (
    ROOT
    / "For-AI/research/literature/audiotactile-paper-metadata-audit/study_instance_registry.json"
)
TRACKED_OUTPUT = (
    ROOT
    / "For-AI/research/literature/audiotactile-paper-metadata-audit/publication-parameter-matrix"
)


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


class PublicationParameterReviewMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary_directory = tempfile.TemporaryDirectory()
        cls.output_dir = Path(cls.temporary_directory.name) / "matrix"
        cls.public_output = Path(cls.temporary_directory.name) / "publication_study_reviews.v1.json"
        result = subprocess.run(
            ["node", str(BUILDER), "--output", str(cls.output_dir), "--public-output", str(cls.public_output)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        cls.build_summary = json.loads(result.stdout)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary_directory.cleanup()

    def test_builder_reports_authoritative_counts(self) -> None:
        summary = self.build_summary
        self.assertEqual(summary["publications"], 94)
        self.assertEqual(summary["networkEdges"], 750)
        self.assertEqual(summary["studyInstances"], 126)
        self.assertEqual(summary["parsimoniousContractCount"], 11)
        self.assertEqual(summary["parsimoniousReviewCells"], 1_386)
        self.assertEqual(summary["currentToolkitInputParameters"], 115)
        self.assertEqual(summary["currentInputReviewCells"], 14_490)
        self.assertEqual(summary["currentInputsOutsideTargetInventory"], 26)
        self.assertEqual(summary["targetMethodValidationParameters"], 281)
        self.assertEqual(summary["targetConfigurationCandidates"], 275)
        self.assertEqual(summary["targetValidationLeaves"], 6)
        self.assertEqual(summary["targetMethodReviewCells"], 35_406)
        self.assertEqual(summary["structuredOrientationReviewRecords"], 8)
        self.assertEqual(summary["experimentSpecificOrientationRows"], 4)
        self.assertEqual(summary["combinedOrientationRows"], 10)
        self.assertEqual(summary["automatedVisualizationCandidates"], 173)
        self.assertEqual(summary["studyVisualizationCandidateRows"], 251)
        self.assertEqual(summary["confirmedVisualizationRows"], 0)
        self.assertEqual(summary["publicationNodesWithAbstract"], 37)
        self.assertEqual(summary["publicationNodesWithoutAbstractOrAudit"], 26)
        self.assertEqual(summary["outsideAuditRecords"], 6)

    def test_primary_matrix_uses_exact_current_serialized_paths(self) -> None:
        dictionary_header, dictionary = read_csv(
            self.output_dir / "current_toolkit_input_dictionary.csv"
        )
        matrix_header, rows = read_csv(
            self.output_dir / "study_instance_current_toolkit_input_matrix.csv"
        )
        paths = [row["serialized_path"] for row in dictionary]
        self.assertEqual(len(dictionary), 115)
        self.assertEqual(len(paths), len(set(paths)))
        self.assertTrue(all(path.startswith("design.") for path in paths))
        self.assertEqual(matrix_header[-115:], paths)
        self.assertEqual(len(rows), 126)
        self.assertTrue(all(row[path] for row in rows for path in paths))
        self.assertIn("parser", dictionary_header)
        self.assertIn("serializer", dictionary_header)
        self.assertIn("accepted_template_source_path", dictionary_header)
        self.assertTrue(all(row["accepted_by_parser"] == "true" for row in dictionary))
        self.assertTrue(all(row["emitted_by_serializer"] == "true" for row in dictionary))

    def test_current_input_review_matrix_is_complete_and_documented(self) -> None:
        dictionary = read_csv(
            self.output_dir / "current_toolkit_input_dictionary.csv"
        )[1]
        paths = [row["serialized_path"] for row in dictionary]
        header, rows = read_csv(
            self.output_dir / "study_instance_current_input_review_matrix.csv"
        )
        self.assertEqual(len(rows), 126)
        self.assertEqual(header[-115:], paths)
        self.assertTrue(all(row[path] for row in rows for path in paths))
        _, queue = read_csv(self.output_dir / "current_input_review_queue.csv")
        self.assertEqual(len(queue), 126 * 115)
        self.assertEqual(
            len({(row["study_row_id"], row["current_toolkit_input_path"]) for row in queue}),
            len(queue),
        )
        _, legend = read_csv(
            self.output_dir / "current_input_review_status_legend.csv"
        )
        observed = {row[path] for row in rows for path in paths}
        documented = {row["current_review_status"] for row in legend}
        self.assertTrue(observed <= documented)

        _, crosswalk = read_csv(
            self.output_dir / "current_input_to_target_crosswalk.csv"
        )
        self.assertEqual(len(crosswalk), 115)
        uncovered = [row for row in crosswalk if row["mapped_target_count"] == "0"]
        self.assertEqual(len(uncovered), 26)

    def test_target_gap_matrix_is_separate_and_crosswalked(self) -> None:
        dictionary_header, dictionary = read_csv(
            self.output_dir / "target_method_validation_dictionary.csv"
        )
        matrix_header, rows = read_csv(
            self.output_dir / "study_instance_target_method_validation_gap_matrix.csv"
        )
        target_paths = [row["target_parameter_path"] for row in dictionary]
        self.assertEqual(len(dictionary), 281)
        self.assertEqual(len(target_paths), len(set(target_paths)))
        self.assertTrue(all(path.startswith("target.") for path in target_paths))
        self.assertEqual(matrix_header[-281:], target_paths)
        self.assertEqual(len(rows), 126)
        self.assertTrue(all(row[path] for row in rows for path in target_paths))
        for field in (
            "current_design_binding_state",
            "current_serialized_paths",
            "current_crosswalk_cardinality",
            "current_binding_basis",
            "crosswalk_scope",
        ):
            self.assertIn(field, dictionary_header)
        self.assertEqual(
            Counter(row["parameter_role"] for row in dictionary),
            Counter({"configuration_input": 275, "reported_or_target_validation_input": 6}),
        )
        valid_current_paths = {
            row["serialized_path"]
            for row in read_csv(
                self.output_dir / "current_toolkit_input_dictionary.csv"
            )[1]
        }
        for row in dictionary:
            mapped = [item.strip() for item in row["current_serialized_paths"].split("|") if item.strip()]
            self.assertEqual(int(row["current_crosswalk_cardinality"]), len(mapped))
            self.assertTrue(set(mapped) <= valid_current_paths)
            if row["current_design_binding_state"] == "not_in_current_design_serializer":
                self.assertEqual(mapped, [])
        self.assertNotIn("current_implementation_support", dictionary_header)
        _, legend = read_csv(
            self.output_dir / "target_method_validation_status_legend.csv"
        )
        observed = {row[path] for row in rows for path in target_paths}
        documented = {
            row["status"]
            for row in legend
            if row["legend_type"] == "atomic_review_status"
        }
        self.assertTrue(observed <= documented)

    def test_publication_aggregates_are_exactly_the_network(self) -> None:
        _, current_rows = read_csv(
            self.output_dir / "publication_current_toolkit_input_matrix.csv"
        )
        _, target_rows = read_csv(
            self.output_dir / "publication_target_method_validation_gap_matrix.csv"
        )
        network = json.loads(
            (
                ROOT
                / "apps/designer/frontend/publication_network.v3.json"
            ).read_text(encoding="utf-8")
        )
        node_ids = {node["id"] for node in network["nodes"]}
        self.assertEqual(len(current_rows), 94)
        self.assertEqual(len(target_rows), 94)
        self.assertEqual({row["network_node_id"] for row in current_rows}, node_ids)
        self.assertEqual({row["network_node_id"] for row in target_rows}, node_ids)

    def test_registry_drives_contiguous_lettered_rows(self) -> None:
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        _, rows = read_csv(self.output_dir / "study_instance_index.csv")
        self.assertEqual(len(registry["entries"]), 32)
        registered_instance_count = sum(
            len(entry["instances"]) for entry in registry["entries"]
        )
        self.assertEqual(registered_instance_count, 64)
        network = json.loads(
            (
                ROOT
                / "apps/designer/frontend/publication_network.v3.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            len(rows),
            len(network["nodes"]) - len(registry["entries"]) + registered_instance_count,
        )
        self.assertEqual(len({row["study_row_id"] for row in rows}), len(rows))
        by_node: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            by_node.setdefault(row["network_node_id"], []).append(row)
        for entry in registry["entries"]:
            expected = [instance["suffix"] for instance in entry["instances"]]
            actual = sorted(
                (row["experiment_letter"] for row in by_node[entry["network_node_id"]])
            )
            self.assertEqual(actual, expected)
            self.assertEqual(expected, [chr(ord("a") + i) for i in range(len(expected))])

        serino = sorted(
            by_node["doi:10.1038/srep18603"],
            key=lambda row: row["experiment_letter"],
        )
        self.assertEqual([row["experiment_letter"] for row in serino], list("abcdefg"))
        self.assertEqual(serino[-1]["record_id"], "")
        self.assertEqual(serino[-1]["parameter_evidence_scope"], "none")

        cell = sorted(
            by_node["doi:10.1016/j.xcrm.2026.102705"],
            key=lambda row: row["experiment_letter"],
        )
        self.assertEqual([row["experiment_letter"] for row in cell], ["a", "b"])
        self.assertEqual(
            [row["experiment_label"] for row in cell],
            [
                "Healthy wake/sleep chest EEG PPS variant",
                "Disorders-of-consciousness arm clinical PPS variant",
            ],
        )
        self.assertTrue(
            all(row["parameter_evidence_scope"] == "composite_requires_split" for row in cell)
        )

        canzoneri_tool = sorted(
            by_node["doi:10.1007/s00221-013-3532-2"],
            key=lambda row: row["experiment_letter"],
        )
        self.assertEqual(
            [row["experiment_letter"] for row in canzoneri_tool], ["a", "b"]
        )
        self.assertEqual(
            [row["experiment_label"] for row in canzoneri_tool],
            [
                "Experiment 1A — tool-use training PPS task",
                "Experiment 3 — pointing-control PPS task",
            ],
        )

        teneggi = sorted(
            by_node["doi:10.1016/j.cub.2013.01.043"],
            key=lambda row: row["experiment_letter"],
        )
        self.assertEqual(
            [row["experiment_letter"] for row in teneggi], list("abc")
        )

    def test_template_mappings_are_experiment_safe(self) -> None:
        _, rows = read_csv(self.output_dir / "study_instance_index.csv")
        by_doi: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            by_doi.setdefault(row["doi"], []).append(row)

        lamia = sorted(
            by_doi["10.1038/s41598-026-36796-5"],
            key=lambda row: row["experiment_letter"],
        )
        self.assertEqual(
            [row["profile_id"] for row in lamia],
            ["barumerli_2026_arm_movement_exp1", "barumerli_2026_arm_movement_exp2"],
        )
        noel = sorted(
            by_doi["10.1016/j.cognition.2015.07.012"],
            key=lambda row: row["experiment_letter"],
        )
        self.assertEqual(
            [row["profile_id"] for row in noel],
            ["noel_2015_bodily_self", "noel_2015_bodily_self_back_space", ""],
        )
        self.assertTrue(
            all(row["parameter_evidence_scope"] == "composite_requires_split" for row in noel)
        )

    def test_publication_matrix_retains_unscoped_composite_profiles(self) -> None:
        _, rows = read_csv(
            self.output_dir / "publication_current_toolkit_input_matrix.csv"
        )
        by_doi = {row["doi"]: row for row in rows}
        for doi in (
            "10.1016/j.neuropsychologia.2014.08.030",
            "10.1038/srep02844",
            "10.3389/fpsyg.2015.00639",
            "10.1111/ejn.13872",
        ):
            row = by_doi[doi]
            self.assertEqual(
                row["publication_profile_scope"],
                "composite_profile_not_experiment_scoped",
            )
            self.assertGreater(int(row["profile_count"]), 0)
            self.assertGreater(int(row["serialized_explicit_count"]), 0)
            self.assertEqual(int(row["no_profile_count"]), 0)
        _, values = read_csv(
            self.output_dir / "publication_current_toolkit_input_values.csv"
        )
        self.assertEqual(len(values), 3_220)

    def test_target_sidecar_is_complete_and_marks_composites(self) -> None:
        header, rows = read_csv(
            self.output_dir / "study_instance_target_method_evidence_sidecar.csv"
        )
        self.assertEqual(len(rows), 126 * 281)
        for field in (
            "study_row_id",
            "network_node_id",
            "record_id",
            "parameter_evidence_scope",
            "target_parameter_path",
            "field_status",
            "source_file",
            "page_or_section",
            "reviewer_note",
            "review_date",
        ):
            self.assertIn(field, header)
        self.assertEqual(
            len({(row["study_row_id"], row["target_parameter_path"]) for row in rows}),
            len(rows),
        )
        composite = [
            row for row in rows if row["field_status"] == "composite_parent_atomic_unreviewed"
        ]
        self.assertTrue(composite)
        self.assertTrue(
            all(row["parameter_evidence_scope"] == "composite_requires_split" for row in composite)
        )
        _, queue = read_csv(self.output_dir / "study_instance_target_method_review_queue.csv")
        self.assertTrue(
            any(row["review_action"] == "disaggregate_composite_record_before_atomic_review" for row in queue)
        )

    def test_orientation_and_visualization_reviews_remain_unconfounded(self) -> None:
        _, orientation = read_csv(self.output_dir / "study_orientation_review.csv")
        self.assertEqual(len(orientation), 126)
        orientation_counts = Counter(
            row["orientation_review_status"] for row in orientation
        )
        self.assertEqual(orientation_counts["structured_orientation_review_present"], 4)
        self.assertEqual(
            orientation_counts["combined_record_orientation_requires_experiment_check"],
            10,
        )

        # The existing Canzoneri tool-use review covers two experiments jointly;
        # neither inherits a false experiment-specific orientation confirmation.
        tool_use = [row for row in orientation if row["record_id"] == "canzoneri_2013_tool_use_reshaping"]
        self.assertEqual(len(tool_use), 2)
        self.assertEqual({row["orientation_review_status"] for row in tool_use},
                         {"combined_record_orientation_requires_experiment_check"})

        visualization_header, visualizations = read_csv(
            self.output_dir / "study_visualizations.csv"
        )
        self.assertEqual(len(visualization_header), 23)
        visualization_counts = Counter(
            row["confirmation_status"] for row in visualizations
        )
        self.assertEqual(visualization_counts["automated_candidate_unverified"], 120)
        self.assertEqual(
            visualization_counts["record_level_candidate_requires_experiment_check"],
            131,
        )
        self.assertNotIn("confirmed", visualization_counts)
        ronga = [row for row in visualizations if row["study_row_id"].startswith("doi:10.1073/pnas.2024548118::")]
        self.assertEqual(len(ronga), 8)  # Four publication candidates for each cohort variant.
        self.assertEqual({row["confirmation_status"] for row in ronga}, {"record_level_candidate_requires_experiment_check"})

    def test_parsimonious_matrix_is_complete_compact_and_evidence_guarded(self) -> None:
        expected_contracts = [
            "auditory_stimulus",
            "trajectory_kinematics",
            "trial_sequence",
            "task_response",
            "jitter_iti_policy",
            "soa_schedule",
            "tactile_target",
            "baseline_trial_contract",
            "catch_trial_contract",
            "repetition_allocation",
            "block_order_contract",
        ]
        dictionary_header, dictionary = read_csv(
            self.output_dir / "parsimonious_contract_dictionary.csv"
        )
        self.assertEqual(
            [row["contract_key"] for row in dictionary], expected_contracts
        )
        for field in (
            "required_components",
            "conditional_components",
            "partial_missing_components",
            "normalization_vocabularies",
            "controlled_vocabulary_json",
            "current_toolkit_support",
        ):
            self.assertIn(field, dictionary_header)
        contract_document = json.loads(
            (
                ROOT
                / "For-AI/research/literature/audiotactile-paper-metadata-audit/parsimonious_emulation_contract.v1.json"
            ).read_text(encoding="utf-8")
        )
        vocabularies = set(contract_document["controlled_vocabularies"])
        for row in dictionary:
            self.assertTrue(row["required_components"])
            self.assertTrue(row["current_toolkit_support"])
            referenced_vocabularies = {
                value.strip()
                for value in row["normalization_vocabularies"].split("|")
                if value.strip()
            }
            self.assertTrue(referenced_vocabularies <= vocabularies)
            serialized_vocabularies = json.loads(row["controlled_vocabulary_json"])
            self.assertEqual(set(serialized_vocabularies), referenced_vocabularies)

        current_paths = {
            row["serialized_path"]
            for row in read_csv(
                self.output_dir / "current_toolkit_input_dictionary.csv"
            )[1]
        }
        for row in dictionary:
            mapped = {
                item.strip()
                for item in row["current_toolkit_paths"].split("|")
                if item.strip()
            }
            self.assertTrue(mapped <= current_paths)

        header, rows = read_csv(
            self.output_dir / "study_instance_parsimonious_status_matrix.csv"
        )
        self.assertEqual(len(rows), 126)
        self.assertEqual(
            header[:-11],
            [
                "study_row_id",
                "study_label",
                "year",
                "doi",
                "experiment_label",
                "evidence_stage",
                "toolkit_status",
                "resolved_contracts",
                "contract_coverage_pct",
            ],
        )
        self.assertEqual(header[-11:], expected_contracts)
        _, study_index = read_csv(self.output_dir / "study_instance_index.csv")
        self.assertEqual(
            [row["study_row_id"] for row in rows],
            [row["study_row_id"] for row in study_index],
        )
        _, legend = read_csv(self.output_dir / "parsimonious_status_legend.csv")
        documented_statuses = {row["status"] for row in legend}
        observed_statuses = {
            row[contract] for row in rows for contract in expected_contracts
        }
        self.assertTrue(observed_statuses <= documented_statuses)
        self.assertNotIn("mixed_across_studies", observed_statuses)
        self.assertTrue(all(row[contract] for row in rows for contract in expected_contracts))

        evidence_header, evidence = read_csv(
            self.output_dir / "parsimonious_contract_evidence.csv"
        )
        for field in (
            "current_toolkit_support",
            "review_date",
            "coarse_parent_status_json",
            "coarse_parent_value_json",
            "component_evidence_note_json",
        ):
            self.assertIn(field, evidence_header)
        self.assertEqual(len(evidence), 126 * 11)
        self.assertEqual(
            len({(row["study_row_id"], row["contract_key"]) for row in evidence}),
            len(evidence),
        )
        dictionary_by_key = {row["contract_key"]: row for row in dictionary}
        final_component_statuses = {
            "reported",
            "derived",
            "approximation_required",
            "not_reported",
            "source_unavailable",
            "explicitly_absent",
            "not_applicable",
            "conflicting_evidence",
            "low_confidence",
        }
        legacy_statuses = {
            "available_reported",
            "available_with_derivation",
            "available_caveated",
            "missing_after_review",
        }
        for row in evidence:
            component_statuses = json.loads(row["component_status_json"])
            component_values = json.loads(row["component_value_json"])
            component_notes = json.loads(row["component_evidence_note_json"])
            json.loads(row["coarse_parent_status_json"])
            json.loads(row["coarse_parent_value_json"])
            self.assertIn(row["contract_key"], expected_contracts)
            self.assertNotIn(row["evidence_status"], legacy_statuses)
            declared_components = {
                value.strip()
                for field in ("required_components", "conditional_components")
                for value in dictionary_by_key[row["contract_key"]][field].split("|")
                if value.strip()
            }
            self.assertEqual(
                row["current_toolkit_support"],
                dictionary_by_key[row["contract_key"]]["current_toolkit_support"],
            )
            self.assertTrue(set(component_statuses) <= declared_components)
            self.assertEqual(set(component_values), set(component_statuses))
            self.assertTrue(set(component_notes) <= set(component_statuses))
            self.assertTrue(set(component_statuses.values()) <= final_component_statuses)
            for component, component_status in component_statuses.items():
                if component_status in {
                    "reported",
                    "derived",
                    "approximation_required",
                    "explicitly_absent",
                    "conflicting_evidence",
                    "low_confidence",
                }:
                    self.assertTrue(component_values[component])
            if "derived" in component_statuses.values():
                self.assertTrue(row["derivation_note"])
            if row["paper_value"] and row["evidence_status"] in {
                "reported_complete",
                "derived_complete",
                "approximation_required",
                "partial",
                "conflicting_evidence",
                "low_confidence",
                "explicitly_absent",
            }:
                self.assertTrue(row["source_file"])
                self.assertTrue(row["page_or_section"])
            if row["experiment_scoped_source_override"] == "yes":
                self.assertTrue(row["source_file"])
                self.assertTrue(row["page_or_section"])
                self.assertTrue(row["source_review_keys"])
                self.assertTrue(row["review_date"])
                self.assertNotEqual(row["evidence_status"], "composite_requires_split")
                if row["evidence_status"] == "derived_complete":
                    self.assertTrue(row["derivation_note"])
            elif row["evidence_status"] in {"reported_complete", "derived_complete"}:
                self.fail(
                    "Coarse parents, profiles, and defaults cannot establish final completion: "
                    f"{row['study_row_id']}/{row['contract_key']}"
                )
            if row["evidence_status"] in {"reported_complete", "derived_complete"}:
                self.assertFalse(row["missing_required_components"])
                required = {
                    value.strip()
                    for value in dictionary_by_key[row["contract_key"]][
                        "required_components"
                    ].split("|")
                    if value.strip()
                }
                self.assertTrue(required <= set(component_statuses))
                self.assertTrue(
                    all(
                        component_statuses[component]
                        in {"reported", "derived", "explicitly_absent", "not_applicable"}
                        for component in required
                    )
                )
            if row["evidence_status"] == "explicitly_absent":
                self.assertIn(
                    row["contract_key"],
                    {"baseline_trial_contract", "catch_trial_contract"},
                )
            if row["evidence_status"] == "composite_requires_split":
                self.assertFalse(row["paper_value"])
                self.assertEqual(row["parameter_evidence_scope"], "composite_requires_split")

        evidence_by_pair = {
            (row["study_row_id"], row["contract_key"]): row for row in evidence
        }
        for matrix_row in rows:
            for contract_key in expected_contracts:
                self.assertEqual(
                    matrix_row[contract_key],
                    evidence_by_pair[(matrix_row["study_row_id"], contract_key)][
                        "evidence_status"
                    ],
                )
            resolved_count = sum(
                matrix_row[contract_key]
                in {"reported_complete", "derived_complete", "explicitly_absent"}
                for contract_key in expected_contracts
            )
            self.assertEqual(matrix_row["resolved_contracts"], f"{resolved_count}/11")
            self.assertEqual(
                float(matrix_row["contract_coverage_pct"]),
                round(100 * resolved_count / 11, 1),
            )
        adjacent = next(
            row for row in rows if row["doi"] == "10.1038/s41598-022-21469-w"
        )
        self.assertEqual(
            {adjacent[contract_key] for contract_key in expected_contracts},
            {"not_applicable"},
        )
        self.assertEqual(adjacent["resolved_contracts"], "0/11")
        self.assertEqual(adjacent["contract_coverage_pct"], "0.0")

        source_reviews = json.loads(
            (
                ROOT
                / "For-AI/research/literature/audiotactile-paper-metadata-audit/parsimonious_source_reviews.v1.json"
            ).read_text(encoding="utf-8")
        )
        for entry in source_reviews["entries"]:
            # Bounded batches name exactly what was reviewed. Omitted contracts
            # retain the existing resolver evidence, rather than fake reviews.
            reviewed = entry.get("reviewed_contract_keys", expected_contracts)
            self.assertTrue(reviewed)
            self.assertEqual(reviewed, [key for key in expected_contracts if key in reviewed])
            self.assertEqual(list(entry["contracts"]), reviewed)
            for contract_key, review in entry["contracts"].items():
                self.assertNotIn(review["status"], legacy_statuses)
                self.assertIn("component_reviews", review)
                self.assertTrue(
                    set(review["component_reviews"])
                    <= {
                        value.strip()
                        for field in ("required_components", "conditional_components")
                        for value in dictionary_by_key[contract_key][field].split("|")
                        if value.strip()
                    }
                )
        self.assertEqual(
            sum(row["experiment_scoped_source_override"] == "yes" for row in evidence),
            sum(len(entry["contracts"]) for entry in source_reviews["entries"]),
        )

        _, summary = read_csv(
            self.output_dir / "parsimonious_contract_summary.csv"
        )
        self.assertEqual([row["contract_key"] for row in summary], expected_contracts)
        summary_statuses = [
            status
            for status in documented_statuses
            if status != "mixed_across_studies"
        ]
        for summary_row in summary:
            contract_key = summary_row["contract_key"]
            counts = Counter(
                row["evidence_status"]
                for row in evidence
                if row["contract_key"] == contract_key
            )
            self.assertEqual(summary_row["study_count"], "126")
            for status in summary_statuses:
                self.assertEqual(int(summary_row[status]), counts[status])
            resolved = sum(
                counts[status]
                for status in {
                    "reported_complete",
                    "derived_complete",
                    "explicitly_absent",
                }
            )
            self.assertEqual(int(summary_row["available_or_resolved_count"]), resolved)
            self.assertEqual(
                float(summary_row["available_or_resolved_pct"]),
                round(100 * resolved / 126, 1),
            )

        _, review_queue = read_csv(
            self.output_dir / "parsimonious_contract_review_queue.csv"
        )
        queue_pairs = {
            (row["study_row_id"], row["contract_key"]) for row in review_queue
        }
        expected_queue_pairs = {
            (row["study_row_id"], row["contract_key"])
            for row in evidence
            if row["evidence_status"]
            not in {"reported_complete", "explicitly_absent", "not_applicable"}
        }
        self.assertEqual(len(queue_pairs), len(review_queue))
        self.assertEqual(queue_pairs, expected_queue_pairs)

        _, publications = read_csv(
            self.output_dir / "publication_parsimonious_status_matrix.csv"
        )
        network = json.loads(
            (
                ROOT
                / "apps/designer/frontend/publication_network.v3.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(len(publications), 94)
        self.assertEqual(
            {row["network_node_id"] for row in publications},
            {node["id"] for node in network["nodes"]},
        )
        rows_by_node: dict[str, list[dict[str, str]]] = {}
        study_index_by_id = {
            row["study_row_id"]: row
            for row in read_csv(self.output_dir / "study_instance_index.csv")[1]
        }
        for row in rows:
            rows_by_node.setdefault(
                study_index_by_id[row["study_row_id"]]["network_node_id"], []
            ).append(row)
        publication_by_node = {row["network_node_id"]: row for row in publications}
        for node_id, child_rows in rows_by_node.items():
            for contract_key in expected_contracts:
                child_statuses = {row[contract_key] for row in child_rows}
                expected = (
                    next(iter(child_statuses))
                    if len(child_statuses) == 1
                    else "mixed_across_studies"
                )
                self.assertEqual(publication_by_node[node_id][contract_key], expected)

    def test_output_only_surfaces_are_not_wide_matrix_columns(self) -> None:
        _, surfaces = read_csv(
            self.output_dir / "implementation_surface_inventory.csv"
        )
        excluded = {
            row["namespace"]
            for row in surfaces
            if row["primary_matrix_treatment"] == "no"
        }
        self.assertTrue(
            {
                "rich_participant_trial_schema",
                "public_data_min",
                "tactile_calibration_trial_fields",
                "adaptive_adjustment_fields",
                "topup_ledger_fields",
            }.issubset(excluded)
        )

    def test_public_projection_is_final_evidence_with_independent_template_links(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        evidence = read_csv(self.output_dir / "parsimonious_contract_evidence.csv")[1]
        by_cell = {(row["study_row_id"], row["contract_key"]): row for row in evidence}
        studies = {row["studyRowId"]: row for row in data["studies"]}
        self.assertEqual(data["schema"], "pps-publication-study-reviews.v1")
        self.assertEqual(data["scope"]["onlineActions"], ["prepare", "preview"])
        self.assertEqual(data["counts"]["contracts"], len(evidence))
        self.assertEqual(data["counts"]["parameterStatusCounts"], dict(Counter(row["evidence_status"] for row in evidence)))
        self.assertEqual(data["scope"]["nativeQualification"], "not_assessed")
        for study in studies.values():
            self.assertEqual(len(study["contracts"]), 11)
            self.assertEqual(study["nativeQualification"], "not_assessed")
            for contract in study["contracts"]:
                original = by_cell[(study["studyRowId"], contract["key"])]
                self.assertEqual(contract["status"], original["evidence_status"])
                self.assertEqual(contract["value"], original["paper_value"])
                self.assertEqual(contract["compositeValue"], original["composite_record_value"])
                self.assertTrue(contract["sourceUrl"].startswith("https://doi.org/10."))
                self.assertNotIn("source_file", contract)
                self.assertNotIn("toolkit_value_summary", contract)
        for publication in data["publications"]:
            children = [studies[key] for key in publication["studyIds"]]
            self.assertEqual(publication["templateIds"], sorted({key for child in children for key in child["templateIds"]}))
            self.assertEqual(publication["parameterStatusCounts"], dict(Counter(contract["status"] for child in children for contract in child["contracts"])))
        # A linked template must not turn unreviewed evidence into completion.
        self.assertTrue(any(row["templateIds"] and any(c["status"] not in {"reported_complete", "derived_complete", "explicitly_absent", "not_applicable"} for c in row["contracts"]) for row in studies.values()))
        # Conversely, resolved paper evidence is still not native qualification.
        self.assertTrue(any(all(c["status"] in {"reported_complete", "derived_complete", "explicitly_absent"} for c in row["contracts"]) for row in studies.values()))
        self.assertEqual(self.public_output.read_bytes(), (ROOT / "apps/designer/frontend/publication_study_reviews.v1.json").read_bytes())

    def test_public_projection_rejects_local_paths_but_preserves_source_urls(self) -> None:
        spec = importlib.util.spec_from_file_location("compact_builder", BUILDER.with_name("build_parsimonious_publication_matrix.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for text in [r"C:\Users\private\paper.pdf", "artifacts/paper.pdf", "packages/runtime/a.py", "file:///home/private/paper.pdf", r"\\server\private\paper.pdf"]:
            with self.assertRaises(ValueError):
                module._public_text(text)
        for text in ["https://doi.org/10.1016/j.cognition.2015.07.012", "Source https://publisher.example/artifacts/paper.pdf, Methods pp. 3–4", "10.1007/s00221-013-3532-2"]:
            self.assertEqual(module._public_text(text), text)

    def test_corpus_freeze_preserves_identities_and_explicit_boundaries(self) -> None:
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        freeze = registry["corpus_freeze"]
        network = json.loads((ROOT / freeze["publication_authority"]).read_text(encoding="utf-8"))
        ids = sorted(row["id"] for row in network["nodes"])
        self.assertEqual(freeze["publication_count"], len(ids))
        self.assertEqual(freeze["publication_id_sha256"], hashlib.sha256(("\n".join(ids) + "\n").encode()).hexdigest())
        self.assertEqual(freeze["completion_status"], "open")
        boundaries = freeze["boundary_records"]
        self.assertEqual(len(boundaries), 9)
        self.assertEqual({row["record_id"] for row in boundaries if "record_id" in row}, {row["record_id"] for row in read_csv(self.output_dir / "audit_records_outside_network.csv")[1]})
        self.assertEqual(Counter(row["disposition"] for row in boundaries), {"identity_pending_not_scientifically_excluded": 6, "deferred_adjacent_family": 3})
        self.assertTrue(all(row["evidence_pointer"] and row["basis"] and row["next_action"] for row in boundaries))

    def test_primary_timing_batch_keeps_anchors_counts_and_remaining_gaps(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        study = next(row for row in data["studies"] if row["studyRowId"] == "doi:10.1371/journal.pone.0044306")
        self.assertEqual(study["templateIds"], ["canzoneri_2012_dynamic_sounds"])
        contracts = {row["key"]: row for row in study["contracts"]}
        self.assertEqual(contracts["soa_schedule"]["status"], "reported_complete")
        self.assertIn("+300, +800, +1500, +2200, +2700", contracts["soa_schedule"]["value"])
        baseline = contracts["baseline_trial_contract"]
        self.assertEqual(baseline["status"], "derived_complete")
        self.assertIn("-700 and +3600", baseline["derivationNote"])
        self.assertIn("32", baseline["components"]["resolved_trial_count"]["value"])
        self.assertEqual(contracts["catch_trial_contract"]["status"], "reported_complete")
        self.assertIn("76", contracts["catch_trial_contract"]["value"])
        self.assertEqual(contracts["repetition_allocation"]["status"], "reported_complete")
        self.assertIn("188", contracts["repetition_allocation"]["value"])
        self.assertEqual(study["parameterStatusCounts"], {"derived_complete": 1, "partial": 7, "reported_complete": 3})
        self.assertEqual(study["nativeQualification"], "not_assessed")

    def test_pregnancy_review_does_not_inherit_prior_study_baselines(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        study = next(row for row in data["studies"] if row["studyRowId"] == "doi:10.1038/s41598-019-45224-w")
        contracts = {row["key"]: row for row in study["contracts"]}
        self.assertEqual(contracts["baseline_trial_contract"]["status"], "explicitly_absent")
        self.assertIn("prior studies", contracts["baseline_trial_contract"]["evidenceNote"])
        self.assertEqual(contracts["soa_schedule"]["status"], "reported_complete")
        self.assertIn("+2500", contracts["soa_schedule"]["value"])
        self.assertNotIn("+2700", contracts["soa_schedule"]["value"])
        self.assertIn("15", contracts["catch_trial_contract"]["components"]["resolved_trial_count"]["value"])
        self.assertIn("65", contracts["repetition_allocation"]["value"])
        for key in ("tactile_target", "task_response", "jitter_iti_policy", "block_order_contract", "trajectory_kinematics"):
            self.assertEqual(contracts[key]["status"], "partial")
            self.assertTrue(contracts[key]["missingComponents"])
        self.assertEqual(study["nativeQualification"], "not_assessed")
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        inventory = next(row for row in registry["entries"] if row["network_node_id"] == study["networkNodeId"])
        self.assertEqual(len(inventory["instances"]), 1, "longitudinal occasions are not distinct experiment identities")
        self.assertEqual(inventory["supporting_task_boundaries"][0]["disposition"], "identity_and_scope_unassessed")

    def test_mechanistic_split_preserves_alias_without_treating_tms_as_touch(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        old_id = "doi:10.1371/journal.pone.0006582"
        children = [old_id + "::a", old_id + "::b"]
        self.assertEqual(data["studyRowAliases"][old_id], children)
        studies = {row["studyRowId"]: row for row in data["studies"]}
        self.assertNotIn(old_id, studies)
        for key in children:
            study = studies[key]
            self.assertEqual(study["networkNodeId"], old_id)
            self.assertEqual(study["templateIds"], [])
            self.assertEqual(study["parameterStatusCounts"], {"not_applicable": 11})
            soa = next(row for row in study["contracts"] if row["key"] == "soa_schedule")
            self.assertIn("sound-to-TMS", soa["evidenceNote"])
            self.assertEqual(soa["status"], "not_applicable")
        network = json.loads((ROOT / "apps/designer/frontend/publication_network.v3.json").read_text(encoding="utf-8"))
        node = next(row for row in network["nodes"] if row["id"] == old_id)
        self.assertEqual(node["toolkit"]["status"], "adjacent_scope_conflict")
        self.assertEqual(len(network["nodes"]), 94)

    def test_rear_looming_review_keeps_head_frame_and_control_arithmetic(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        study = next(row for row in data["studies"] if row["studyRowId"] == "doi:10.3389/fpsyt.2014.00122")
        contracts = {row["key"]: row for row in study["contracts"]}
        self.assertIn("Head-centred", contracts["trajectory_kinematics"]["value"])
        self.assertIn("520", contracts["trajectory_kinematics"]["value"])
        self.assertEqual(contracts["baseline_trial_contract"]["status"], "derived_complete")
        self.assertIn("64", contracts["baseline_trial_contract"]["components"]["resolved_trial_count"]["value"])
        self.assertIn("32", contracts["catch_trial_contract"]["value"])
        self.assertIn("256", contracts["repetition_allocation"]["value"])
        self.assertEqual(contracts["jitter_iti_policy"]["status"], "partial")
        self.assertIn("distribution", contracts["jitter_iti_policy"]["missingComponents"])
        self.assertEqual(contracts["auditory_stimulus"]["status"], "partial")
        self.assertEqual(study["nativeQualification"], "not_assessed")

    def test_training_batch_separates_measurement_counts_and_missing_baselines(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        studies = {row["studyRowId"]: row for row in data["studies"]}
        serino = studies["doi:10.3389/fnbeh.2015.00004"]
        contracts = {row["key"]: row for row in serino["contracts"]}
        self.assertEqual(contracts["baseline_trial_contract"]["status"], "not_reported")
        self.assertEqual(contracts["jitter_iti_policy"]["status"], "not_reported")
        self.assertIn("training", contracts["jitter_iti_policy"]["evidenceNote"])
        self.assertEqual(contracts["catch_trial_contract"]["status"], "partial")
        self.assertIn("resolved_trial_count", contracts["catch_trial_contract"]["missingComponents"])
        self.assertEqual(contracts["repetition_allocation"]["status"], "partial")
        self.assertIn("23 trains", contracts["repetition_allocation"]["evidenceNote"])
        mindfulness = studies["doi:10.3390/bs14040306"]
        contracts = {row["key"]: row for row in mindfulness["contracts"]}
        self.assertEqual(contracts["baseline_trial_contract"]["status"], "partial")
        self.assertIn("timing_and_anchor", contracts["baseline_trial_contract"]["missingComponents"])
        self.assertIn("12", contracts["baseline_trial_contract"]["components"]["resolved_trial_count"]["value"])
        self.assertEqual(contracts["tactile_target"]["status"], "conflicting_evidence")
        self.assertIn("constant-voltage", contracts["tactile_target"]["evidenceNote"])
        self.assertEqual(mindfulness["templateIds"], [])
        taffou = studies["doi:10.1038/s41598-020-79767-0"]
        contracts = {row["key"]: row for row in taffou["contracts"]}
        self.assertIn("80", contracts["baseline_trial_contract"]["components"]["resolved_trial_count"]["value"])
        self.assertIn("40", contracts["catch_trial_contract"]["value"])
        self.assertIn("trunk", contracts["trajectory_kinematics"]["components"]["coordinate_frame_body_anchor"]["value"])
        self.assertEqual(taffou["templateIds"], [])
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        for study in (serino, mindfulness, taffou):
            self.assertEqual(study["nativeQualification"], "not_assessed")
            inventory = next(row for row in registry["entries"] if row["network_node_id"] == study["networkNodeId"])
            self.assertEqual(len(inventory["instances"]), 1)
            self.assertTrue(inventory["supporting_task_boundaries"])

    def test_computational_review_is_a_retained_publication_boundary(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        studies = {row["studyRowId"]: row for row in data["studies"]}
        node = "doi:10.3389/fpsyg.2011.00077"
        study = studies[node]
        self.assertEqual({row["status"] for row in study["contracts"]}, {"not_applicable"})
        self.assertEqual(study["templateIds"], [])
        self.assertEqual(study["nativeQualification"], "not_assessed")
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        entry = next(row for row in registry["entries"] if row["network_node_id"] == node)
        self.assertEqual(entry["instances"][0]["instance_kind"], "publication_scope_boundary")
        self.assertEqual(len(data["publications"]), 94)
        # Apparently adjacent titles can still contain audio-tactile tasks.
        for retained in ("doi:10.1016/j.bodyim.2024.101777", "doi:10.1016/j.actpsy.2011.01.003", "doi:10.3758/app.72.4.885"):
            self.assertNotEqual({row["status"] for row in studies[retained]["contracts"]}, {"not_applicable"})

    def test_passive_and_directional_tasks_keep_trial_units_and_time_anchors(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        studies = {row["studyRowId"]: row for row in data["studies"]}
        ieeg = studies["doi:10.1093/cercor/bhy156"]
        contracts = {row["key"]: row for row in ieeg["contracts"]}
        self.assertEqual(contracts["task_response"]["status"], "reported_complete")
        self.assertEqual(contracts["task_response"]["components"]["response_window_and_anchor"]["status"], "not_applicable")
        self.assertIn("three", contracts["trial_sequence"]["value"])
        self.assertIn("255", contracts["repetition_allocation"]["value"])
        self.assertIn("510", contracts["repetition_allocation"]["components"]["derived_total_reconciliation"]["value"])
        self.assertEqual(contracts["catch_trial_contract"]["status"], "explicitly_absent")
        self.assertIn("controls", contracts["catch_trial_contract"]["value"])
        matsuda = studies["doi:10.1038/s41598-021-90784-5"]
        contracts = {row["key"]: row for row in matsuda["contracts"]}
        self.assertEqual(contracts["baseline_trial_contract"]["status"], "derived_complete")
        self.assertIn("+3700", contracts["baseline_trial_contract"]["value"])
        self.assertNotIn("+3600", contracts["baseline_trial_contract"]["value"])
        self.assertIn("800", contracts["repetition_allocation"]["components"]["derived_total_reconciliation"]["value"])
        self.assertIn("turns", contracts["block_order_contract"]["evidenceNote"])
        self.assertEqual(matsuda["templateIds"], ["matsuda_2021_four_directions"])
        for study in (ieeg, matsuda):
            self.assertEqual(study["nativeQualification"], "not_assessed")

    def test_newborn_adult_alias_keeps_cohort_counts_and_prior_source_limits(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        old = "doi:10.1073/pnas.2024548118"
        ids = [old + "::a", old + "::b"]
        self.assertEqual(data["studyRowAliases"][old], ids)
        studies = {row["studyRowId"]: row for row in data["studies"]}
        self.assertNotIn(old, studies)
        for study_id, total, blocks, block_status in zip(ids, ["75-150", "180"], ["3-6", "3"], ["partial", "reported_complete"]):
            study = studies[study_id]
            contracts = {row["key"]: row for row in study["contracts"]}
            self.assertIn(total, contracts["repetition_allocation"]["value"])
            self.assertIn(blocks, contracts["block_order_contract"]["components"]["block_count"]["value"])
            self.assertEqual(contracts["block_order_contract"]["status"], block_status)
            self.assertEqual(contracts["soa_schedule"]["status"], "derived_complete")
            self.assertIn("-40", contracts["soa_schedule"]["value"])
            self.assertIn("current SI reaccess failed", contracts["soa_schedule"]["evidenceNote"])
            self.assertEqual(contracts["tactile_target"]["status"], "composite_requires_split")
            self.assertEqual(study["nativeQualification"], "not_assessed")
        self.assertEqual(len(data["publications"]), 94)
        self.assertEqual(len(data["studies"]), 126)

    def test_echolocation_assessment_keeps_training_and_manual_timing_separate(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        study = next(row for row in data["studies"] if row["studyRowId"] == "doi:10.1007/s00221-019-05469-3")
        contracts = {row["key"]: row for row in study["contracts"]}
        self.assertIn("left", contracts["trajectory_kinematics"]["value"])
        self.assertIn("119", contracts["trajectory_kinematics"]["value"])
        self.assertEqual(contracts["soa_schedule"]["status"], "derived_complete")
        self.assertIn("0,500,1000,1500,2000,2500,3000", contracts["soa_schedule"]["value"])
        self.assertIn("manual_or_event_driven", contracts["jitter_iti_policy"]["components"]["policy_type"]["value"])
        self.assertIn("experimenter", contracts["jitter_iti_policy"]["value"])
        self.assertEqual(contracts["task_response"]["status"], "conflicting_evidence")
        self.assertIn("response_window_and_anchor", contracts["task_response"]["missingComponents"])
        self.assertEqual(contracts["baseline_trial_contract"]["status"], "partial")
        self.assertIn("+3500", contracts["baseline_trial_contract"]["value"])
        self.assertIn("28", contracts["catch_trial_contract"]["value"])
        self.assertIn("140", contracts["repetition_allocation"]["value"])
        self.assertNotRegex(contracts["repetition_allocation"]["value"], r"\b40 trials\b")
        self.assertEqual(study["templateIds"], ["tonelli_2019_echolocation"])
        self.assertEqual(study["nativeQualification"], "not_assessed")
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        inventory = next(row for row in registry["entries"] if row["network_node_id"] == study["networkNodeId"])
        self.assertEqual(len(inventory["instances"]), 1)
        self.assertEqual(len(inventory["supporting_task_boundaries"]), 3)

    def test_moving_sound_tms_boundary_is_not_a_tactile_detection_delay(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        study = next(row for row in data["studies"] if row["studyRowId"] == "doi:10.1016/j.neuropsychologia.2014.09.043")
        self.assertEqual(study["parameterStatusCounts"], {"not_applicable": 11})
        self.assertEqual(study["templateIds"], [])
        self.assertEqual(study["nativeQualification"], "not_assessed")
        soa = next(row for row in study["contracts"] if row["key"] == "soa_schedule")
        self.assertIn("sound-position-to-TMS", soa["evidenceNote"])
        self.assertIn("not a tactile-detection SOA", soa["evidenceNote"])
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        inventory = next(row for row in registry["entries"] if row["network_node_id"] == study["networkNodeId"])
        self.assertEqual(len(inventory["instances"]), 1)
        self.assertEqual(inventory["supporting_task_boundaries"][0]["disposition"], "supporting_localization_validation")

    def test_static_tasks_preserve_response_roles_and_source_specific_timing(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        studies = {row["studyRowId"]: row for row in data["studies"]}
        cane = studies["doi:10.1111/j.1467-9280.2007.01952.x"]
        racket = studies["doi:10.1016/j.neuropsychologia.2017.07.018"]
        crossed = studies["doi:10.1016/j.neuropsychologia.2009.07.025"]
        cane_contracts = {row["key"]: row for row in cane["contracts"]}
        racket_contracts = {row["key"]: row for row in racket["contracts"]}
        crossed_contracts = {row["key"]: row for row in crossed["contracts"]}
        self.assertIn("+5 ms", cane_contracts["soa_schedule"]["value"])
        self.assertEqual(racket_contracts["soa_schedule"]["status"], "partial")
        self.assertIn("unspecified", racket_contracts["soa_schedule"]["value"])
        self.assertIn("60 strong", cane_contracts["catch_trial_contract"]["value"])
        self.assertIn("30 paper-labelled", cane_contracts["catch_trial_contract"]["components"]["resolved_trial_count"]["value"])
        self.assertEqual(cane_contracts["block_order_contract"]["status"], "partial")
        self.assertIn("Novices", racket_contracts["block_order_contract"]["value"])
        self.assertIn("personal-racket", racket_contracts["block_order_contract"]["value"])
        self.assertIn("existing primary PDF critical review", racket_contracts["repetition_allocation"]["evidenceNote"])
        self.assertIn("left hand in crossed posture", crossed_contracts["task_response"]["components"]["response_mapping_or_expected_action"]["value"])
        self.assertEqual(crossed_contracts["task_response"]["status"], "partial")
        self.assertIn("response_window_and_anchor", crossed_contracts["task_response"]["missingComponents"])
        self.assertIn("not an online timeout", crossed_contracts["task_response"]["components"]["scoring_rule"]["value"])
        self.assertEqual(crossed_contracts["catch_trial_contract"]["status"], "explicitly_absent")
        self.assertIn("600", crossed_contracts["repetition_allocation"]["value"])
        self.assertIn("Collignon", crossed["experimentLabel"])
        self.assertEqual(len(racket["templateIds"]), 3)
        self.assertEqual(len(crossed["templateIds"]), 2)
        for study in (cane, racket, crossed):
            self.assertEqual(study["nativeQualification"], "not_assessed")

    def test_build_is_byte_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as second_temp:
            second = Path(second_temp) / "matrix"
            second_public = Path(second_temp) / "public.json"
            subprocess.run(
                ["node", str(BUILDER), "--output", str(second), "--public-output", str(second_public)],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            first_files = sorted(
                path.relative_to(self.output_dir)
                for path in self.output_dir.rglob("*")
                if path.is_file()
            )
            second_files = sorted(
                path.relative_to(second)
                for path in second.rglob("*")
                if path.is_file()
            )
            self.assertEqual(first_files, second_files)
            self.assertEqual(self.public_output.read_bytes(), second_public.read_bytes())
            manifest = json.loads(
                (self.output_dir / "generated_output_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            managed = sorted(
                [Path(name) for name in manifest["files"]]
                + [Path("generated_output_manifest.json")]
            )
            self.assertEqual(first_files, managed)
            tracked_files = sorted(
                path.relative_to(TRACKED_OUTPUT)
                for path in TRACKED_OUTPUT.rglob("*")
                if path.is_file()
            )
            self.assertEqual(tracked_files, managed)
            for relative in first_files:
                self.assertEqual(
                    (self.output_dir / relative).read_bytes(),
                    (second / relative).read_bytes(),
                    str(relative),
                )
                # Git may normalize text line endings by platform; content must
                # nevertheless match the checked-in source-derived projection.
                self.assertEqual(
                    (self.output_dir / relative).read_text(encoding="utf-8"),
                    (TRACKED_OUTPUT / relative).read_text(encoding="utf-8"),
                    f"Stale tracked matrix: {relative}",
                )


if __name__ == "__main__":
    unittest.main()
