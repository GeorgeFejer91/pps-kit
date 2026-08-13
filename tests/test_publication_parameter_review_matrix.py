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
        cls.network = json.loads(
            (
                ROOT
                / "src/peripersonal_space_toolkit/dashboard/publication_network.v3.json"
            ).read_text(encoding="utf-8")
        )
        cls.registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        cls.expected_study_instances = (
            len(cls.network["nodes"])
            - len(cls.registry["entries"])
            + sum(len(entry["instances"]) for entry in cls.registry["entries"])
        )
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
        self.assertEqual(len(self.network["nodes"]), 94)
        self.assertEqual(self.expected_study_instances, 142)
        self.assertEqual(summary["publications"], len(self.network["nodes"]))
        self.assertEqual(summary["networkEdges"], 750)
        self.assertEqual(summary["studyInstances"], self.expected_study_instances)
        self.assertEqual(summary["parsimoniousContractCount"], 13)
        self.assertEqual(
            summary["parsimoniousReviewCells"], self.expected_study_instances * 13
        )
        self.assertEqual(summary["currentToolkitInputParameters"], 115)
        self.assertEqual(
            summary["currentInputReviewCells"], self.expected_study_instances * 115
        )
        self.assertEqual(summary["currentInputsOutsideTargetInventory"], 26)
        self.assertEqual(summary["targetMethodValidationParameters"], 281)
        self.assertEqual(summary["targetConfigurationCandidates"], 275)
        self.assertEqual(summary["targetValidationLeaves"], 6)
        self.assertEqual(
            summary["targetMethodReviewCells"], self.expected_study_instances * 281
        )
        self.assertEqual(summary["structuredOrientationReviewRecords"], 7)
        self.assertEqual(summary["experimentSpecificOrientationRows"], 3)
        self.assertEqual(summary["combinedOrientationRows"], 10)
        self.assertEqual(summary["automatedVisualizationCandidates"], 173)
        self.assertEqual(summary["studyVisualizationCandidateRows"], 276)
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
        self.assertEqual(len(rows), self.expected_study_instances)
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
        self.assertEqual(len(rows), self.expected_study_instances)
        self.assertEqual(header[-115:], paths)
        self.assertTrue(all(row[path] for row in rows for path in paths))
        _, queue = read_csv(self.output_dir / "current_input_review_queue.csv")
        self.assertEqual(len(queue), self.expected_study_instances * 115)
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
        self.assertEqual(len(rows), self.expected_study_instances)
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
        registry = self.registry
        _, rows = read_csv(self.output_dir / "study_instance_index.csv")
        registered_instance_count = sum(
            len(entry["instances"]) for entry in registry["entries"]
        )
        self.assertEqual(
            len(rows),
            len(self.network["nodes"])
            - len(registry["entries"])
            + registered_instance_count,
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

        bassolino = sorted(
            by_node["doi:10.1016/j.neuropsychologia.2009.11.009"],
            key=lambda row: row["experiment_letter"],
        )
        self.assertEqual([row["experiment_letter"] for row in bassolino], ["a", "b"])
        self.assertEqual(
            [row["experiment_label"] for row in bassolino],
            [
                "Experiment 1 — right-hand mouse-use task",
                "Experiment 2 — new-group left-hand mouse-use task",
            ],
        )
        self.assertTrue(
            all(
                row["parameter_evidence_scope"] == "composite_requires_split"
                for row in bassolino
            )
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

        source_review_only = [
            row
            for row in rows
            if row["experiment_disaggregation_status"]
            == "experiment_specific_source_review_available"
        ]
        self.assertEqual(len(source_review_only), 19)
        self.assertTrue(
            all(row["parameter_evidence_scope"] == "composite_requires_split" for row in source_review_only)
        )
        registered_instances = {
            f"{entry['network_node_id']}::{instance['suffix']}": instance
            for entry in self.registry["entries"]
            for instance in entry["instances"]
        }
        for row in source_review_only:
            instance = registered_instances[row["study_row_id"]]
            expected_profiles = " | ".join(sorted(instance.get("template_ids", [])))
            self.assertEqual(row["profile_id"], expected_profiles)

        _, compact_evidence = read_csv(
            self.output_dir / "parsimonious_contract_evidence.csv"
        )
        source_review_row_ids = {row["study_row_id"] for row in source_review_only}
        source_review_evidence = [
            row
            for row in compact_evidence
            if row["study_row_id"] in source_review_row_ids
        ]
        self.assertEqual(len(source_review_evidence), len(source_review_only) * 13)
        self.assertTrue(
            all(
                row["experiment_scoped_source_override"] == "yes"
                and row["evidence_status"] != "composite_requires_split"
                for row in source_review_evidence
            )
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
        self.assertEqual(len(rows), self.expected_study_instances * 281)
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
        self.assertEqual(len(orientation), self.expected_study_instances)
        orientation_counts = Counter(
            row["orientation_review_status"] for row in orientation
        )
        self.assertEqual(orientation_counts["structured_orientation_review_present"], 3)
        self.assertEqual(
            orientation_counts["combined_record_orientation_requires_experiment_check"],
            10,
        )

        visualization_header, visualizations = read_csv(
            self.output_dir / "study_visualizations.csv"
        )
        self.assertEqual(len(visualization_header), 23)
        visualization_counts = Counter(
            row["confirmation_status"] for row in visualizations
        )
        self.assertEqual(visualization_counts["automated_candidate_unverified"], 94)
        self.assertEqual(
            visualization_counts["record_level_candidate_requires_experiment_check"],
            182,
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
            "study_structure_schedule",
            "measurement_acquisition_outcome",
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
        self.assertEqual(len(rows), self.expected_study_instances)
        self.assertEqual(
            header[:-13],
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
        self.assertEqual(header[-13:], expected_contracts)
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
        self.assertEqual(len(evidence), self.expected_study_instances * 13)
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
            "partial",
            "not_assessed",
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
                    "partial",
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
            self.assertEqual(matrix_row["resolved_contracts"], f"{resolved_count}/13")
            self.assertEqual(
                float(matrix_row["contract_coverage_pct"]),
                round(100 * resolved_count / 13, 1),
            )
        adjacent = next(
            row for row in rows if row["doi"] == "10.1038/s41598-022-21469-w"
        )
        self.assertEqual(
            {adjacent[contract_key] for contract_key in expected_contracts[:-2]},
            {"not_applicable"},
        )
        self.assertEqual(adjacent["study_structure_schedule"], "partial")
        self.assertEqual(adjacent["measurement_acquisition_outcome"], "not_applicable")
        self.assertEqual(adjacent["resolved_contracts"], "0/13")
        self.assertEqual(adjacent["contract_coverage_pct"], "0.0")

        source_reviews = json.loads(
            (
                ROOT
                / "For-AI/audiotactile-paper-metadata-audit/parsimonious_source_reviews.v1.json"
            ).read_text(encoding="utf-8")
        )
        for entry in source_reviews["entries"]:
            self.assertEqual(list(entry["contracts"]), expected_contracts[:-2])
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
            len(source_reviews["entries"]) * len(expected_contracts[:-2])
            + (
                len(
                    json.loads(
                        (
                            ROOT
                            / "For-AI/audiotactile-paper-metadata-audit/study_structure_reviews.v1.json"
                        ).read_text(encoding="utf-8")
                    )["entries"]
                )
                if (
                    ROOT
                    / "For-AI/audiotactile-paper-metadata-audit/study_structure_reviews.v1.json"
                ).exists()
                else 0
            )
            + (
                len(
                    json.loads(
                        (
                            ROOT
                            / "For-AI/audiotactile-paper-metadata-audit/measurement_acquisition_reviews.v1.json"
                        ).read_text(encoding="utf-8")
                    )["entries"]
                )
                if (
                    ROOT
                    / "For-AI/audiotactile-paper-metadata-audit/measurement_acquisition_reviews.v1.json"
                ).exists()
                else 0
            ),
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
            self.assertEqual(
                summary_row["study_count"], str(self.expected_study_instances)
            )
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
                round(100 * resolved / self.expected_study_instances, 1),
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

    def test_study_structure_tables_are_normalized_and_conservatively_mapped(self) -> None:
        structure_header, structure_rows = read_csv(
            self.output_dir / "study_structure.csv"
        )
        _, study_index = read_csv(self.output_dir / "study_instance_index.csv")
        self.assertEqual(len(structure_rows), self.expected_study_instances)
        self.assertEqual(
            [row["study_row_id"] for row in structure_rows],
            [row["study_row_id"] for row in study_index],
        )
        for field in (
            "sample_and_assignment_summary",
            "population_summary",
            "inclusion_criteria",
            "exclusion_criteria",
            "planned_sample_n",
            "analyzed_sample_n",
            "cohort_or_arm_count",
            "per_arm_sample_json",
            "design_family",
            "assignment_scope",
            "pps_occurrence_pattern",
            "compiled_factor_count",
            "compiled_event_count",
            "future_toolkit_paths",
            "legacy_untyped_metadata_paths",
            "compiler_derived_outputs",
        ):
            self.assertIn(field, structure_header)
        self.assertTrue(
            all(
                row["current_toolkit_support"] == "unsupported_no_typed_study_plan"
                and not row["current_toolkit_paths"]
                and "pps-study-plan.v1" in row["future_toolkit_paths"]
                for row in structure_rows
            )
        )

        _, evidence = read_csv(
            self.output_dir / "parsimonious_contract_evidence.csv"
        )
        structure_evidence = [
            row
            for row in evidence
            if row["contract_key"] == "study_structure_schedule"
        ]
        self.assertEqual(len(structure_evidence), self.expected_study_instances)
        self.assertTrue(
            all(
                row["toolkit_encoding_status"]
                == "not_in_current_design_or_run_plan_schema"
                and not row["current_toolkit_paths"]
                and "pps-study-plan.v1" in row["future_toolkit_paths"]
                for row in structure_evidence
            )
        )

        structure_review_path = (
            ROOT
            / "For-AI/audiotactile-paper-metadata-audit/study_structure_reviews.v1.json"
        )
        if not structure_review_path.exists():
            self.assertTrue(all(not row["source_file"] for row in structure_rows))
            return

        reviews = json.loads(structure_review_path.read_text(encoding="utf-8"))
        self.assertEqual(reviews["schema"], "pps-study-structure-reviews.v1")
        entries = reviews["entries"]
        entries_by_id = {entry["study_row_id"]: entry for entry in entries}
        self.assertEqual(len(entries_by_id), len(entries))
        structure_by_id = {row["study_row_id"]: row for row in structure_rows}
        for study_row_id, entry in entries_by_id.items():
            row = structure_by_id[study_row_id]
            self.assertEqual(row["source_file"], entry["source_file"])
            self.assertEqual(row["page_or_section"], entry["page_or_section"])
            self.assertTrue(row["review_date"])
            self.assertIsInstance(json.loads(row["per_arm_sample_json"]), dict)
            self.assertEqual(
                int(row["compiled_factor_count"]), len(entry.get("factors", []))
            )
            self.assertEqual(
                int(row["compiled_event_count"]), len(entry.get("events", []))
            )

        contract_document = json.loads(
            (
                ROOT
                / "For-AI/audiotactile-paper-metadata-audit/parsimonious_emulation_contract.v1.json"
            ).read_text(encoding="utf-8")
        )
        vocabularies = contract_document["controlled_vocabularies"]
        factor_header, factor_rows = read_csv(
            self.output_dir / "study_factor_levels.csv"
        )
        for field in ("factor_role", "factor_scope", "assignment_method", "planned_n", "analyzed_n"):
            self.assertIn(field, factor_header)
        expected_factor_rows = sum(
            max(1, len(factor.get("levels", [])))
            for entry in entries
            for factor in entry.get("factors", [])
        )
        self.assertEqual(len(factor_rows), expected_factor_rows)
        self.assertEqual(self.build_summary["studyFactorLevelRows"], len(factor_rows))
        for row in factor_rows:
            self.assertIn(row["study_row_id"], entries_by_id)
            self.assertIn(row["factor_role"], vocabularies["study_factor_role"])
            self.assertIn(row["factor_scope"], vocabularies["study_factor_scope"])
            self.assertIn(
                row["assignment_method"], vocabularies["study_assignment_method"]
            )
            for field in ("planned_n", "analyzed_n"):
                if row[field]:
                    self.assertGreaterEqual(int(row[field]), 0)

        event_header, event_rows = read_csv(
            self.output_dir / "study_schedule_events.csv"
        )
        for field in (
            "visit_id",
            "session_id",
            "pps_occurrence_id",
            "relative_to_event_id",
            "compiled_predecessor_event_ids",
            "compiled_concurrent_event_ids",
            "factor_level_bindings_json",
            "profile_or_protocol_ref",
            "parameter_overrides_json",
        ):
            self.assertIn(field, event_header)
        self.assertEqual(
            len(event_rows),
            sum(len(entry.get("events", [])) for entry in entries),
        )
        self.assertEqual(self.build_summary["studyScheduleEventRows"], len(event_rows))
        self.assertEqual(self.build_summary["studyStructureReviewRows"], len(entries))
        events_by_study: dict[str, set[str]] = {}
        occurrences_by_study: dict[str, set[str]] = {}
        for row in event_rows:
            events_by_study.setdefault(row["study_row_id"], set()).add(row["event_id"])
            if row["pps_occurrence_id"]:
                self.assertNotIn(
                    row["pps_occurrence_id"],
                    occurrences_by_study.setdefault(row["study_row_id"], set()),
                )
                occurrences_by_study[row["study_row_id"]].add(row["pps_occurrence_id"])
            self.assertIn(
                row["event_kind"], vocabularies["study_schedule_event_kind"]
            )
            self.assertIn(
                row["execution_mode"],
                vocabularies["study_schedule_execution_mode"],
            )
            self.assertIn(
                row["relation"], vocabularies["study_schedule_relation"]
            )
            json.loads(row["factor_level_bindings_json"])
            self.assertIsInstance(json.loads(row["parameter_overrides_json"]), dict)
        for row in event_rows:
            if row["relative_to_event_id"]:
                self.assertIn(
                    row["relative_to_event_id"], events_by_study[row["study_row_id"]]
                )

    def test_measurement_acquisition_contract_excludes_analysis_and_keeps_runtime_gap_visible(self) -> None:
        header, rows = read_csv(
            self.output_dir / "study_measurement_acquisitions.csv"
        )
        for field in (
            "acquisition_id",
            "outcome_family",
            "modality_or_signal",
            "primary_measure",
            "binding_mode",
            "device_or_system",
            "channels_or_sites_json",
            "event_trigger",
            "clock_sync_method",
            "acquisition_window",
            "primary_outcome_definition",
            "calibration_or_online_processing",
            "applies_to_event_ids",
            "applies_to_pps_occurrence_ids",
            "profile_or_protocol_ref",
            "current_toolkit_support",
            "future_toolkit_paths",
            "analysis_model_scope",
        ):
            self.assertIn(field, header)
        self.assertTrue(
            all(
                row["current_toolkit_support"]
                == "native_behavioral_runtime_plus_external_capture_scaffolding_no_typed_acquisition_plan"
                and not row["current_toolkit_paths"]
                and "pps-acquisition-plan.v1" in row["future_toolkit_paths"]
                and row["analysis_model_scope"]
                == "excluded_from_acquisition_contract"
                for row in rows
            )
        )

        _, evidence = read_csv(
            self.output_dir / "parsimonious_contract_evidence.csv"
        )
        measurement_evidence = [
            row
            for row in evidence
            if row["contract_key"] == "measurement_acquisition_outcome"
        ]
        self.assertEqual(len(measurement_evidence), self.expected_study_instances)
        self.assertTrue(
            all(
                row["current_toolkit_support"]
                == "native_behavioral_runtime_plus_external_capture_scaffolding_no_typed_acquisition_plan"
                and not row["current_toolkit_paths"]
                and "pps-acquisition-plan.v1" in row["future_toolkit_paths"]
                for row in measurement_evidence
            )
        )

        review_path = (
            ROOT
            / "For-AI/audiotactile-paper-metadata-audit/measurement_acquisition_reviews.v1.json"
        )
        if not review_path.exists():
            self.assertFalse(rows)
            self.assertEqual(self.build_summary["measurementAcquisitionReviewRows"], 0)
            self.assertEqual(self.build_summary["studyMeasurementAcquisitionRows"], 0)
            return

        review_document = json.loads(review_path.read_text(encoding="utf-8"))
        self.assertEqual(
            review_document["schema"], "pps-measurement-acquisition-reviews.v1"
        )
        entries = review_document["entries"]
        self.assertEqual(
            len(rows),
            sum(len(entry.get("acquisitions", [])) for entry in entries),
        )
        self.assertEqual(
            self.build_summary["measurementAcquisitionReviewRows"], len(entries)
        )
        self.assertEqual(
            self.build_summary["studyMeasurementAcquisitionRows"], len(rows)
        )

        contract_document = json.loads(
            (
                ROOT
                / "For-AI/audiotactile-paper-metadata-audit/parsimonious_emulation_contract.v1.json"
            ).read_text(encoding="utf-8")
        )
        vocabularies = contract_document["controlled_vocabularies"]
        ids_by_study: dict[str, set[str]] = {}
        for row in rows:
            prior = ids_by_study.setdefault(row["study_row_id"], set())
            self.assertNotIn(row["acquisition_id"], prior)
            prior.add(row["acquisition_id"])
            self.assertIn(
                row["outcome_family"], vocabularies["measurement_outcome_family"]
            )
            self.assertIn(
                row["binding_mode"], vocabularies["measurement_binding_mode"]
            )
            self.assertIn(
                row["clock_sync_method"],
                vocabularies["measurement_clock_sync_method"],
            )
            if row["binding_mode"] == "native_response_log":
                self.assertIn(row["outcome_family"], {"behavioral_response", "multimodal"})
            json.loads(row["channels_or_sites_json"])
            self.assertNotIn("analysis", row["analysis_model_scope"].replace("excluded_from_", ""))

        _, structure_events = read_csv(
            self.output_dir / "study_schedule_events.csv"
        )
        valid_event_ids: dict[str, set[str]] = {}
        valid_occurrence_ids: dict[str, set[str]] = {}
        for event in structure_events:
            valid_event_ids.setdefault(event["study_row_id"], set()).add(event["event_id"])
            if event["pps_occurrence_id"]:
                valid_occurrence_ids.setdefault(event["study_row_id"], set()).add(
                    event["pps_occurrence_id"]
                )
        for row in rows:
            for event_id in filter(None, row["applies_to_event_ids"].split(" | ")):
                self.assertIn(event_id, valid_event_ids.get(row["study_row_id"], set()))
            for occurrence_id in filter(
                None, row["applies_to_pps_occurrence_ids"].split(" | ")
            ):
                self.assertIn(
                    occurrence_id,
                    valid_occurrence_ids.get(row["study_row_id"], set()),
                )

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
                and not (
                    path.name.startswith(".~lock.") and path.name.endswith("#")
                )
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
