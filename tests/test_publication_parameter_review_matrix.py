from __future__ import annotations

import csv
import json
import subprocess
import tempfile
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools" / "build_publication_parameter_review_matrix.mjs"
REGISTRY = (
    ROOT
    / "For-AI/audiotactile-paper-metadata-audit/study_instance_registry.json"
)
TRACKED_OUTPUT = (
    ROOT
    / "For-AI/audiotactile-paper-metadata-audit/publication-parameter-matrix"
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
        result = subprocess.run(
            ["node", str(BUILDER), "--output", str(cls.output_dir)],
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
        self.assertEqual(summary["studyInstances"], 124)
        self.assertEqual(summary["parsimoniousContractCount"], 11)
        self.assertEqual(summary["parsimoniousReviewCells"], 1_364)
        self.assertEqual(summary["currentToolkitInputParameters"], 115)
        self.assertEqual(summary["currentInputReviewCells"], 14_260)
        self.assertEqual(summary["currentInputsOutsideTargetInventory"], 26)
        self.assertEqual(summary["targetMethodValidationParameters"], 281)
        self.assertEqual(summary["targetConfigurationCandidates"], 275)
        self.assertEqual(summary["targetValidationLeaves"], 6)
        self.assertEqual(summary["targetMethodReviewCells"], 34_844)
        self.assertEqual(summary["structuredOrientationReviewRecords"], 7)
        self.assertEqual(summary["experimentSpecificOrientationRows"], 4)
        self.assertEqual(summary["combinedOrientationRows"], 8)
        self.assertEqual(summary["automatedVisualizationCandidates"], 173)
        self.assertEqual(summary["studyVisualizationCandidateRows"], 247)
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
        self.assertEqual(len(rows), 124)
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
        self.assertEqual(len(rows), 124)
        self.assertEqual(header[-115:], paths)
        self.assertTrue(all(row[path] for row in rows for path in paths))
        _, queue = read_csv(self.output_dir / "current_input_review_queue.csv")
        self.assertEqual(len(queue), 124 * 115)
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
        self.assertEqual(len(rows), 124)
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
                / "src/peripersonal_space_toolkit/dashboard/publication_network.v3.json"
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
        self.assertEqual(len(registry["entries"]), 16)
        registered_instance_count = sum(
            len(entry["instances"]) for entry in registry["entries"]
        )
        self.assertEqual(registered_instance_count, 46)
        network = json.loads(
            (
                ROOT
                / "src/peripersonal_space_toolkit/dashboard/publication_network.v3.json"
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
        self.assertEqual(len(rows), 124 * 281)
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
        self.assertEqual(len(orientation), 124)
        orientation_counts = Counter(
            row["orientation_review_status"] for row in orientation
        )
        self.assertEqual(orientation_counts["structured_orientation_review_present"], 4)
        self.assertEqual(
            orientation_counts["combined_record_orientation_requires_experiment_check"],
            8,
        )

        visualization_header, visualizations = read_csv(
            self.output_dir / "study_visualizations.csv"
        )
        self.assertEqual(len(visualization_header), 23)
        visualization_counts = Counter(
            row["confirmation_status"] for row in visualizations
        )
        self.assertEqual(visualization_counts["automated_candidate_unverified"], 124)
        self.assertEqual(
            visualization_counts["record_level_candidate_requires_experiment_check"],
            123,
        )
        self.assertNotIn("confirmed", visualization_counts)

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
                / "For-AI/audiotactile-paper-metadata-audit/parsimonious_emulation_contract.v1.json"
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
        self.assertEqual(len(rows), 124)
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
        self.assertEqual(len(evidence), 124 * 11)
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
                / "For-AI/audiotactile-paper-metadata-audit/parsimonious_source_reviews.v1.json"
            ).read_text(encoding="utf-8")
        )
        for entry in source_reviews["entries"]:
            self.assertEqual(list(entry["contracts"]), expected_contracts)
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
            len(source_reviews["entries"]) * len(expected_contracts),
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
            self.assertEqual(summary_row["study_count"], "124")
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
                round(100 * resolved / 124, 1),
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
                / "src/peripersonal_space_toolkit/dashboard/publication_network.v3.json"
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

    def test_build_is_byte_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as second_temp:
            second = Path(second_temp) / "matrix"
            subprocess.run(
                ["node", str(BUILDER), "--output", str(second)],
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
                self.assertEqual(
                    (self.output_dir / relative).read_bytes(),
                    (TRACKED_OUTPUT / relative).read_bytes(),
                    f"tracked {relative}",
                )


if __name__ == "__main__":
    unittest.main()
