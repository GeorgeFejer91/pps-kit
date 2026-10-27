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
        self.assertEqual(summary["studyInstances"], 163)
        self.assertEqual(summary["parsimoniousContractCount"], 11)
        self.assertEqual(summary["parsimoniousReviewCells"], 1_793)
        self.assertEqual(summary["currentToolkitInputParameters"], 115)
        self.assertEqual(summary["currentInputReviewCells"], 18_745)
        self.assertEqual(summary["currentInputsOutsideTargetInventory"], 26)
        self.assertEqual(summary["targetMethodValidationParameters"], 281)
        self.assertEqual(summary["targetConfigurationCandidates"], 275)
        self.assertEqual(summary["targetValidationLeaves"], 6)
        self.assertEqual(summary["targetMethodReviewCells"], 45_803)
        self.assertEqual(summary["structuredOrientationReviewRecords"], 8)
        self.assertEqual(summary["experimentSpecificOrientationRows"], 4)
        self.assertEqual(summary["combinedOrientationRows"], 10)
        self.assertEqual(summary["automatedVisualizationCandidates"], 173)
        self.assertEqual(summary["studyVisualizationCandidateRows"], 311)
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
        self.assertEqual(len(rows), 163)
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
        self.assertEqual(len(rows), 163)
        self.assertEqual(header[-115:], paths)
        self.assertTrue(all(row[path] for row in rows for path in paths))
        _, queue = read_csv(self.output_dir / "current_input_review_queue.csv")
        self.assertEqual(len(queue), 163 * 115)
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
        self.assertEqual(len(rows), 163)
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
        self.assertEqual(len(registry["entries"]), 76)
        registered_instance_count = sum(
            len(entry["instances"]) for entry in registry["entries"]
        )
        self.assertEqual(registered_instance_count, 145)
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
        self.assertEqual([row["experiment_letter"] for row in serino], list("abcdefghij"))
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
                "Experiment 1: healthy wake/sleep chest EEG",
                "Experiment 2: clinical DoC arm EEG",
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
            [row["experiment_letter"] for row in teneggi], list("abcdef")
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
        self.assertEqual(len(rows), 163 * 281)
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
        self.assertEqual(len(orientation), 163)
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
        self.assertEqual(visualization_counts["automated_candidate_unverified"], 81)
        self.assertEqual(
            visualization_counts["record_level_candidate_requires_experiment_check"],
            230,
        )
        self.assertNotIn("confirmed", visualization_counts)
        duration = [row for row in visualizations if row["study_row_id"].startswith("doi:10.61782/fa.2025.0866::")]
        self.assertEqual(len(duration), 16)  # Eight publication candidates require assignment across two protocols.
        self.assertEqual({row["confirmation_status"] for row in duration}, {"record_level_candidate_requires_experiment_check"})
        ferri = [row for row in visualizations if row["study_row_id"].startswith("doi:10.1523/jneurosci.1696-15.2015::")]
        self.assertEqual(len(ferri), 35)  # Seven prior candidates now require assignment to five protocol variants.
        self.assertEqual({row["confirmation_status"] for row in ferri}, {"record_level_candidate_requires_experiment_check"})
        ronga = [row for row in visualizations if row["study_row_id"] in {"doi:10.1073/pnas.2024548118::a", "doi:10.1073/pnas.2024548118::b"}]
        self.assertEqual(len(ronga), 8)  # Four publication candidates for each cohort variant.
        self.assertEqual({row["confirmation_status"] for row in ronga}, {"record_level_candidate_requires_experiment_check"})
        orioli = [row for row in visualizations if row["study_row_id"].startswith("doi:10.1038/s41598-019-45084-4::")]
        self.assertEqual(len(orioli), 14)  # Seven legacy candidates now need pilot/main assignment.
        self.assertEqual({row["confirmation_status"] for row in orioli}, {"record_level_candidate_requires_experiment_check"})
        spadone = [row for row in visualizations if row["study_row_id"].startswith("doi:10.1038/s41598-021-00048-5::")]
        self.assertEqual(len(spadone), 16)  # Eight source candidates need behavioral/fMRI assignment.
        self.assertEqual({row["confirmation_status"] for row in spadone}, {"record_level_candidate_requires_experiment_check"})

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
        self.assertEqual(len(rows), 163)
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
        self.assertEqual(len(evidence), 163 * 11)
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
            self.assertEqual(summary_row["study_count"], "163")
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
                round(100 * resolved / 163, 1),
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
        for pointer in [r"C:\Users\private\paper.pdf", "artifacts/paper.pdf", "file:///home/private/paper.pdf", "https://localhost/file", "https://localhost./file", "https://127.0.0.1/paper", "https://127.0.0.1./paper", "https://[::ffff:127.0.0.1]/paper", "https://user:secret@example.org/paper", "https://example.org/paper?token=private", "https://example.org/paper?%74oken=private", "https://example.org/paper?%2574oken=private", "https://example.org/paper#access_token=private", "https://example.org/paper#section?api%5fkey=private", "https://example.org/paper | artifacts/private.pdf"]:
            self.assertEqual(module._public_evidence_url(pointer), "")
        for pointer in ["https://backoffice.biblio.ugent.be/download/8673877/8673880", "https://doi.org/10.1007/s00426-020-01365-6", "https://publisher.example/article?id=123", "https://publisher.example/article?design=123#sec002"]:
            self.assertEqual(module._public_evidence_url(pointer), pointer)

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

    def test_frozen_identity_audit_and_bounded_lineage_keep_omissions_visible(self) -> None:
        freeze = json.loads(REGISTRY.read_text(encoding="utf-8"))["corpus_freeze"]
        network = json.loads((ROOT / freeze["publication_authority"]).read_text(encoding="utf-8"))
        nodes = network["nodes"]
        ids = {row["id"] for row in nodes}
        audit = freeze["identity_audit"]
        self.assertEqual(audit["unique_publication_ids"], len(ids))
        self.assertEqual(audit["unique_normalized_dois"], len({row["doi"].lower() for row in nodes}))
        self.assertTrue(all(row["id"] == "doi:" + row["doi"].lower() for row in nodes))
        records = json.loads((ROOT / "For-AI/research/literature/preload-ledgers/audiotactile_literature_coverage.json").read_text(encoding="utf-8"))["literature_records"]
        doi_by_record = {row["record_id"]: row.get("doi", "").lower() for row in records}
        joins = [(node, record) for node in nodes for record in node["toolkit"]["records"]]
        self.assertEqual(audit["exact_doi_record_joins"], len(joins))
        self.assertEqual(audit["mismatched_record_doi_joins"], 0)
        for node, record in joins:
            self.assertEqual(doi_by_record[record["recordId"]], node["doi"].lower())
        self.assertIn("not a fresh", audit["scope"])

        check = freeze["foundational_lineage_check"]
        candidates = check["candidates"]
        self.assertEqual(check["candidate_count"], len(candidates))
        self.assertEqual(len({row["doi"] for row in candidates}), len(candidates))
        self.assertEqual(check["present_in_frozen_corpus"], sum("doi:" + row["doi"] in ids for row in candidates))
        outside = [row for row in candidates if "doi:" + row["doi"] not in ids]
        self.assertEqual(check["outside_frozen_corpus"], len(outside))
        self.assertTrue(all(row["seed_reference_locators"] for row in candidates))
        self.assertEqual({row["doi"] for row in outside}, {"10.1007/s00221-010-2255-x"})
        for row in outside:
            self.assertEqual(row["membership"], "outside_frozen_corpus")
            self.assertEqual(row["disposition"], "source_backed_omission_candidate")
            self.assertEqual(row["network_node_id"], "")
            self.assertIn("Full Methods were not reviewed", row["evidence_basis"])
            self.assertTrue(row["identity_source_url"] and row["membership_decision"] and row["next_action"])
        self.assertEqual(freeze["completion_status"], "open")

    def test_primary_timing_batch_keeps_anchors_counts_and_remaining_gaps(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        study = next(row for row in data["studies"] if row["studyRowId"] == "doi:10.1371/journal.pone.0044306::a")
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
        self.assertEqual(contracts["repetition_allocation"]["status"], "derived_complete")
        self.assertIn("188", contracts["repetition_allocation"]["value"])
        self.assertEqual(study["parameterStatusCounts"], {"approximation_required": 1, "derived_complete": 3, "partial": 5, "reported_complete": 2})
        self.assertEqual(study["nativeQualification"], "not_assessed")

    def test_newborn_intensity_studies_preserve_visual_endpoint_and_planned_maxima(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        node = "doi:10.1038/s41598-019-45084-4"
        self.assertEqual(data["studyRowAliases"][node], [node + "::a", node + "::b"])
        studies = [row for row in data["studies"] if row["networkNodeId"] == node]
        self.assertEqual(len(studies), 2)
        for study in studies:
            contracts = {row["key"]: row for row in study["contracts"]}
            pilot = study["studyRowId"].endswith("::a")
            self.assertIn("Offline video-coded", contracts["task_response"]["value"])
            self.assertEqual(contracts["task_response"]["status"], "partial")
            self.assertEqual(contracts["soa_schedule"]["status"], "partial")
            self.assertIn("manual", contracts["soa_schedule"]["value"])
            self.assertIn("metric", contracts["trajectory_kinematics"]["evidenceNote"])
            self.assertIn("30" if pilot else "31", contracts["repetition_allocation"]["value"])
            self.assertIn("maximum", contracts["repetition_allocation"]["value"])
            self.assertIn("Attention-dependent", contracts["repetition_allocation"]["components"]["exceptions_or_overrides"]["value"])
            self.assertEqual(contracts["catch_trial_contract"]["status"], "explicitly_absent")
            baseline = contracts["baseline_trial_contract"]
            self.assertEqual(baseline["status"], "explicitly_absent" if pilot else "reported_complete")
            if not pilot:
                self.assertIn("between-group", baseline["value"])
                self.assertEqual(contracts["block_order_contract"]["status"], "partial")
            self.assertEqual(study["templateIds"], [])
            self.assertEqual(study["nativeQualification"], "not_assessed")

    def test_guided_reaching_keeps_tactile_training_outside_detection_contracts(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        node = "doi:10.3389/fpsyg.2022.983189"
        studies = [row for row in data["studies"] if row["networkNodeId"] == node]
        self.assertEqual(len(studies), 1)
        study = studies[0]
        self.assertEqual(study["parameterStatusCounts"], {"not_applicable": 11})
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        inventory = next(row for row in registry["entries"] if row["network_node_id"] == node)
        self.assertEqual(inventory["framework_disposition"], "adjacent_auditory_reaching_with_tactile_training_feedback")
        self.assertIn("92 trials", inventory["supporting_task_boundaries"][0]["basis"])
        self.assertEqual(study["templateIds"], [])
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
        for retained in ("doi:10.1016/j.bodyim.2024.101777",):
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
        self.assertEqual(contracts["block_order_contract"]["components"]["block_count"]["value"], "4.")
        self.assertIn("counterbalanced", contracts["block_order_contract"]["value"])
        self.assertEqual(matsuda["templateIds"], ["matsuda_2021_four_directions"])
        for study in (ieeg, matsuda):
            self.assertEqual(study["nativeQualification"], "not_assessed")

    def test_newborn_adult_alias_keeps_cohort_counts_and_fresh_source_limits(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        old = "doi:10.1073/pnas.2024548118"
        ids = [old + "::a", old + "::b"]
        self.assertEqual(data["studyRowAliases"][old], ids + [old + "::c"])
        studies = {row["studyRowId"]: row for row in data["studies"]}
        self.assertNotIn(old, studies)
        for study_id, total, blocks, block_status in zip(ids, ["75–150", "180"], ["3–6", "Three"], ["partial", "reported_complete"]):
            study = studies[study_id]
            contracts = {row["key"]: row for row in study["contracts"]}
            self.assertIn(total, contracts["repetition_allocation"]["value"])
            self.assertIn(blocks, contracts["block_order_contract"]["components"]["block_count"]["value"])
            self.assertEqual(contracts["block_order_contract"]["status"], block_status)
            self.assertEqual(contracts["soa_schedule"]["status"], "derived_complete")
            self.assertIn("−40", contracts["soa_schedule"]["value"])
            self.assertEqual(contracts["repetition_allocation"]["status"], "derived_complete")
            self.assertEqual(contracts["tactile_target"]["status"], "reported_complete")
            self.assertIn("Original", contracts["soa_schedule"]["pageOrSection"])
            self.assertEqual(study["nativeQualification"], "not_assessed")
        self.assertEqual(len(data["publications"]), 94)
        self.assertEqual(len(data["studies"]), 163)

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
        self.assertIn("Historical full-PDF review dated 2026-06-16", racket_contracts["repetition_allocation"]["evidenceNote"])
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

    def test_reanalysis_and_supplement_preserve_roles_and_count_conflicts(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        studies = {row["studyRowId"]: row for row in data["studies"]}
        old = "doi:10.1038/s41598-021-00048-5"
        self.assertEqual(data["studyRowAliases"][old], [old + "::a", old + "::b"])
        behavioral = {row["key"]: row for row in studies[old + "::a"]["contracts"]}
        imaging = {row["key"]: row for row in studies[old + "::b"]["contracts"]}
        self.assertIn("+300,+800,+1500,+2200,+2700", behavioral["soa_schedule"]["value"])
        self.assertEqual(behavioral["repetition_allocation"]["status"], "partial")
        self.assertIn("individual", imaging["soa_schedule"]["value"])
        self.assertEqual(imaging["task_response"]["status"], "conflicting_evidence")
        self.assertIn("left middle", imaging["task_response"]["value"])
        self.assertIn("positive response", imaging["catch_trial_contract"]["value"])
        self.assertIn("4.56", imaging["jitter_iti_policy"]["value"])
        ferroni = {row["key"]: row for row in studies["doi:10.1093/schbul/sbac067"]["contracts"]}
        self.assertEqual(ferroni["repetition_allocation"]["status"], "conflicting_evidence")
        self.assertIn("180", ferroni["repetition_allocation"]["value"])
        self.assertIn("120", ferroni["repetition_allocation"]["value"])
        self.assertIn("-700", ferroni["baseline_trial_contract"]["value"])
        self.assertEqual(ferroni["tactile_target"]["status"], "conflicting_evidence")
        self.assertEqual(ferroni["auditory_stimulus"]["status"], "partial")
        boundary = studies["doi:10.1038/s41598-022-21469-w"]
        self.assertEqual(boundary["parameterStatusCounts"], {"not_applicable": 11})
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        inventory = next(row for row in registry["entries"] if row["network_node_id"] == old)
        self.assertIn("reanaly", inventory["instance_count_basis"].lower())
        self.assertEqual(inventory["source_lineage"]["network_node_id"], "doi:10.1523/jneurosci.1696-15.2015")
        for study_id in (old + "::a", old + "::b", "doi:10.1093/schbul/sbac067", boundary["studyRowId"]):
            self.assertEqual(studies[study_id]["nativeQualification"], "not_assessed")

    def test_body_image_protocol_is_retained_and_haptic_bisection_is_disclosed(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        studies = {row["studyRowId"]: row for row in data["studies"]}
        finn = studies["doi:10.1016/j.bodyim.2024.101777"]
        contracts = {row["key"]: row for row in finn["contracts"]}
        self.assertIn("81", contracts["repetition_allocation"]["value"])
        self.assertIn("14", contracts["baseline_trial_contract"]["value"])
        self.assertIn("+300", contracts["baseline_trial_contract"]["value"])
        self.assertEqual(contracts["baseline_trial_contract"]["status"], "partial")
        self.assertIn("timing_and_anchor", contracts["baseline_trial_contract"]["missingComponents"])
        self.assertEqual(contracts["jitter_iti_policy"]["status"], "not_reported")
        self.assertIn("left index", contracts["tactile_target"]["value"])
        self.assertIn("right index", contracts["task_response"]["value"])
        haptic = studies["doi:10.3758/app.72.4.885"]
        self.assertEqual(haptic["parameterStatusCounts"], {"not_applicable": 11})
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        inventory = next(row for row in registry["entries"] if row["network_node_id"] == haptic["networkNodeId"])
        self.assertEqual(len(inventory["instances"]), 1)
        self.assertIn("bisection", inventory["instance_count_basis"])
        for study in (finn, haptic):
            self.assertEqual(study["nativeQualification"], "not_assessed")

    def test_device_protocols_keep_published_conflicts_and_route_limits(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        studies = {row["studyRowId"]: row for row in data["studies"]}
        phone = studies["doi:10.3390/s25196072"]
        vr = studies["doi:10.3389/frvir.2021.644214"]
        stroke = studies["doi:10.1093/braincomms/fcac179"]
        pc = {row["key"]: row for row in phone["contracts"]}
        vc = {row["key"]: row for row in vr["contracts"]}
        sc = {row["key"]: row for row in stroke["contracts"]}
        self.assertEqual(pc["catch_trial_contract"]["status"], "conflicting_evidence")
        self.assertIn("184", pc["catch_trial_contract"]["value"])
        self.assertIn("144", pc["catch_trial_contract"]["value"])
        self.assertIn("+105,+1625,+2385,+2765,+2955,+3050", pc["soa_schedule"]["value"])
        self.assertEqual(pc["jitter_iti_policy"]["status"], "partial")
        self.assertEqual(vc["repetition_allocation"]["status"], "conflicting_evidence")
        self.assertIn("96", vc["repetition_allocation"]["value"])
        self.assertIn("144", vc["repetition_allocation"]["value"])
        self.assertEqual(vc["trajectory_kinematics"]["status"], "conflicting_evidence")
        self.assertEqual(vc["soa_schedule"]["status"], "partial")
        self.assertEqual(sc["task_response"]["status"], "reported_complete")
        self.assertIn("2000 ms", sc["task_response"]["value"])
        self.assertIn("foot", sc["task_response"]["value"])
        self.assertIn("+300,+1500,+2700", sc["soa_schedule"]["value"])
        self.assertIn("110", sc["repetition_allocation"]["value"])
        self.assertEqual(sc["repetition_allocation"]["status"], "partial")
        for study in (phone, vr, stroke):
            self.assertEqual(study["nativeQualification"], "not_assessed")
        self.assertTrue(phone["templateIds"])
        self.assertTrue(vr["templateIds"])

    def test_original_fmri_inventory_separates_response_roles_and_reanalysis(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        studies = {row["studyRowId"]: row for row in data["studies"]}
        parent = "doi:10.1523/jneurosci.1696-15.2015"
        ids = [parent + "::" + suffix for suffix in "abcde"]
        self.assertEqual(data["studyRowAliases"][parent], ids)
        contracts = [{row["key"]: row for row in studies[key]["contracts"]} for key in ids]
        self.assertIn("300", contracts[0]["repetition_allocation"]["value"])
        self.assertIn("120", contracts[0]["catch_trial_contract"]["value"])
        self.assertIn("600", contracts[2]["repetition_allocation"]["value"])
        self.assertIn("left index", contracts[1]["catch_trial_contract"]["value"])
        self.assertIn("positive response", contracts[1]["catch_trial_contract"]["value"])
        self.assertIn("withhold", contracts[4]["catch_trial_contract"]["value"])
        self.assertEqual(contracts[4]["repetition_allocation"]["status"], "partial")
        self.assertEqual(contracts[1]["jitter_iti_policy"]["status"], "conflicting_evidence")
        self.assertIn("1.55 ms", contracts[1]["jitter_iti_policy"]["value"])
        reanalysis = {row["key"]: row for row in studies["doi:10.1038/s41598-021-00048-5::b"]["contracts"]}
        self.assertEqual(reanalysis["repetition_allocation"]["status"], "conflicting_evidence")
        self.assertIn("30", reanalysis["repetition_allocation"]["evidenceNote"])
        self.assertEqual(reanalysis["block_order_contract"]["status"], "conflicting_evidence")
        for key in ids:
            self.assertEqual(studies[key]["nativeQualification"], "not_assessed")

    def test_social_context_and_ageing_do_not_invent_new_cohorts_or_timing(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        studies = {row["studyRowId"]: row for row in data["studies"]}
        parent = "doi:10.1098/rsos.181878"
        self.assertEqual(data["studyRowAliases"][parent], [parent + "::" + suffix for suffix in "abc"])
        for suffix in "abc":
            contracts = {row["key"]: row for row in studies[parent + "::" + suffix]["contracts"]}
            self.assertIn("480", contracts["repetition_allocation"]["value"])
            self.assertIn("80", contracts["baseline_trial_contract"]["value"])
            self.assertIn("+3000", contracts["soa_schedule"]["value"])
            self.assertIn("-650", contracts["baseline_trial_contract"]["value"])
            self.assertEqual(contracts["jitter_iti_policy"]["status"], "partial")
        ageing = {row["key"]: row for row in studies["doi:10.1016/j.cortex.2020.11.021"]["contracts"]}
        self.assertIn("2000", ageing["task_response"]["value"])
        self.assertEqual(ageing["repetition_allocation"]["status"], "partial")
        self.assertIn("110", ageing["repetition_allocation"]["value"])
        self.assertIn("hand", ageing["repetition_allocation"]["evidenceNote"])
        self.assertEqual(ageing["baseline_trial_contract"]["status"], "partial")
        self.assertEqual(ageing["trajectory_kinematics"]["status"], "partial")
        self.assertEqual(ageing["jitter_iti_policy"]["status"], "partial")
        self.assertNotIn("220 total", ageing["repetition_allocation"]["value"])

    def test_matched_expectancy_source_anchors_and_short_report_limits(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        studies = {row["studyRowId"]: row for row in data["studies"]}
        methods = {row["key"]: row for row in studies["doi:10.1016/j.jneumeth.2019.108534"]["contracts"]}
        self.assertEqual(methods["soa_schedule"]["status"], "reported_complete")
        self.assertIn("+105,+1625,+2385,+2765,+2955,+3050", methods["soa_schedule"]["value"])
        self.assertIn("+105,+675,+1245,+1910,+2480,+3050", methods["soa_schedule"]["value"])
        self.assertIn("-250", methods["baseline_trial_contract"]["value"])
        self.assertEqual(methods["task_response"]["status"], "partial")
        self.assertEqual(methods["jitter_iti_policy"]["status"], "partial")
        self.assertIn("1152", methods["repetition_allocation"]["value"])
        parent = "doi:10.1250/ast.41.345"
        self.assertEqual(data["studyRowAliases"][parent], [parent + "::" + suffix for suffix in "abc"])
        for suffix in "abc":
            short = {row["key"]: row for row in studies[parent + "::" + suffix]["contracts"]}
            self.assertEqual(short["catch_trial_contract"]["status"], "not_reported")
            self.assertEqual(short["baseline_trial_contract"]["status"], "partial")
            self.assertEqual(short["repetition_allocation"]["status"], "partial")

    def test_front_rear_short_probe_preserves_cue_and_catch_families(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        study = next(row for row in data["studies"] if row["studyRowId"] == "doi:10.1007/s00221-024-06782-2")
        contracts = {row["key"]: row for row in study["contracts"]}
        self.assertIn("+250,+500,+750", contracts["soa_schedule"]["value"])
        self.assertIn("112", contracts["repetition_allocation"]["value"])
        self.assertIn("warning", contracts["catch_trial_contract"]["value"])
        self.assertIn("16", contracts["catch_trial_contract"]["value"])
        self.assertEqual(contracts["baseline_trial_contract"]["status"], "partial")
        self.assertIn("1250", contracts["baseline_trial_contract"]["value"])
        self.assertEqual(contracts["jitter_iti_policy"]["status"], "partial")
        self.assertIn("four", contracts["trajectory_kinematics"]["value"])

    def test_audited_access_gap_does_not_claim_a_confirmed_experiment(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        study = next(row for row in data["studies"] if row["studyRowId"] == "doi:10.1007/s00221-017-5158-2")
        self.assertEqual(study["inventoryStatus"], "source_access_blocked_experiment_inventory_unresolved")
        self.assertEqual(len(study["contracts"]), 11)
        self.assertEqual({row["status"] for row in study["contracts"]}, {"source_unavailable"})
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        record = next(row for row in registry["entries"] if row["network_node_id"] == study["studyRowId"])
        self.assertEqual(record["instances"][0]["instance_kind"], "unresolved_publication_review_unit")
        self.assertIn("not one confirmed experiment", record["instance_count_basis"])
        self.assertGreaterEqual(len(record["retrieval_attempts"]), 2)

    def test_holmes_includes_pilot_failure_and_project_lineage_without_new_cohorts(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        node = "doi:10.1007/s00221-020-05771-5"
        studies = {row["studyRowId"]: row for row in data["studies"]}
        self.assertEqual({key for key in studies if key.startswith(node + "::")}, {node + "::" + suffix for suffix in "abcdef"})
        pilot = studies[node + "::e"]
        self.assertEqual(pilot["parameterStatusCounts"], {"not_applicable": 11})
        failed = {row["key"]: row for row in studies[node + "::f"]["contracts"]}
        self.assertEqual(failed["auditory_stimulus"]["status"], "conflicting_evidence")
        self.assertEqual(failed["trajectory_kinematics"]["status"], "conflicting_evidence")
        self.assertEqual(failed["repetition_allocation"]["status"], "not_reported")
        self.assertEqual(studies[node + "::f"]["templateIds"], [])
        main = {row["key"]: row for row in studies[node + "::d"]["contracts"]}
        self.assertEqual(main["jitter_iti_policy"]["status"], "not_reported")
        self.assertIn("17 had five-minute", main["block_order_contract"]["value"])
        self.assertIn("27 had self-paced", main["block_order_contract"]["value"])
        project = studies["doi:10.17605/osf.io/73x59"]
        self.assertEqual(project["parameterStatusCounts"], {"not_applicable": 11})
        self.assertEqual(project["templateIds"], [])
        self.assertEqual(data["inventoryAudit"]["projectLineageReviews"], 1)
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        record = next(row for row in registry["entries"] if row["network_node_id"] == node)
        variants = record["instances"][4]["protocol_variants"]
        self.assertEqual([variant["n"] for variant in variants], [3, 1])
        self.assertTrue(variants[1]["sameParticipantAsPilot"])
        self.assertEqual(variants[1]["blocks"], 14)

    def test_project_lineage_gate_cannot_admit_an_acquisition_protocol(self) -> None:
        spec = importlib.util.spec_from_file_location("project_inventory_builder", BUILDER.with_name("build_parsimonious_publication_matrix.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        node = "doi:10.17605/osf.io/73x59"
        studies = [row for row in read_csv(self.output_dir / "study_instance_index.csv")[1] if row["network_node_id"] == node]
        cells = [row for row in read_csv(self.output_dir / "parsimonious_contract_evidence.csv")[1] if row["network_node_id"] == node]
        _, baseline = module.inventory_review_audit(registry, studies, cells)
        self.assertEqual(baseline["inventoryAndContractsAudited"], 1)
        self.assertEqual(baseline["methodsReviewedInventories"], 0)
        changed = [dict(row) for row in cells]
        changed[0]["evidence_status"] = "partial"
        _, result = module.inventory_review_audit(registry, studies, changed)
        self.assertEqual(result["inventoryAndContractsAudited"], 0)
        entry = next(row for row in registry["entries"] if row["network_node_id"] == node)
        entry["instances"][0]["instance_kind"] = "experiment"
        with self.assertRaisesRegex(ValueError, "project lineage"):
            module.inventory_review_audit(registry, studies, cells)

    def test_amputation_inventory_preserves_body_targets_and_count_conflict(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        node = "doi:10.1038/srep02844"
        studies = {row["studyRowId"]: row for row in data["studies"]}
        self.assertEqual(studies[node + "::a"]["parameterStatusCounts"], {"not_applicable": 11})
        for suffix in "bc":
            cs = {row["key"]: row for row in studies[node + "::" + suffix]["contracts"]}
            self.assertEqual(cs["repetition_allocation"]["status"], "conflicting_evidence")
            self.assertIn("Neither 152 nor 156", cs["repetition_allocation"]["value"])
            self.assertIn("from the near speaker", cs["trajectory_kinematics"]["value"])
            self.assertEqual(cs["block_order_contract"]["status"], "conflicting_evidence")
        cs = {row["key"]: row for row in studies[node + "::c"]["contracts"]}
        self.assertIn("Upper arm and hand", cs["tactile_target"]["value"])
        self.assertIn("four blocks", cs["block_order_contract"]["value"])
        self.assertIn("counterbalanced", cs["block_order_contract"]["value"])
        publication = next(row for row in data["publications"] if row["networkNodeId"] == node)
        self.assertTrue(publication["inventoryAudit"]["inventoryAndContractsAudited"])

    def test_adaptation_model_batch_separates_acquisition_from_simulation(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        studies = {row["studyRowId"]: row for row in data["studies"]}
        noel = "doi:10.1152/jn.00652.2017"
        ferroni = "doi:10.1016/j.neuropsychologia.2020.107579"
        for node in (noel, ferroni):
            self.assertEqual(data["studyRowAliases"][node], [node + "::a", node + "::b"])
        for suffix in "ab":
            cs = {row["key"]: row for row in studies[noel + "::" + suffix]["contracts"]}
            self.assertEqual(cs["soa_schedule"]["status"], "reported_complete")
            self.assertIn("330, 660, 1000, 1330, 1660, 2000, 2330", cs["soa_schedule"]["value"])
            self.assertEqual(cs["repetition_allocation"]["status"], "derived_complete")
            self.assertIn("224 AT", cs["repetition_allocation"]["value"])
            self.assertIn("64", cs["baseline_trial_contract"]["value"])
            self.assertIn("32", cs["catch_trial_contract"]["value"])
            self.assertEqual(cs["jitter_iti_policy"]["status"], "not_reported")
            self.assertIn("215-Hz", cs["task_response"]["components"]["response_mode_or_device"]["value"])
            self.assertIn("constant loudness", cs["auditory_stimulus"]["value"])
            fs = {row["key"]: row for row in studies[ferroni + "::" + suffix]["contracts"]}
            self.assertEqual(fs["tactile_target"]["status"], "source_unavailable")
            self.assertEqual(fs["repetition_allocation"]["status"], "source_unavailable")
            self.assertIn("pre-training", fs["baseline_trial_contract"]["value"])
        model = studies["doi:10.1016/j.schres.2021.06.026"]
        self.assertEqual(model["parameterStatusCounts"], {"not_applicable": 11})
        self.assertEqual(model["templateIds"], [])
        self.assertEqual(model["nativeQualification"], "not_assessed")
        mc = {row["key"]: row for row in model["contracts"]}
        self.assertIn("model assumption", mc["trajectory_kinematics"]["value"])
        self.assertIn("100-ms neural inputs", mc["tactile_target"]["value"])
        self.assertIn("100-microsecond", mc["tactile_target"]["value"])
        self.assertEqual(mc["auditory_stimulus"]["sourceType"], "accepted_author_manuscript_final_comparison_pending")
        pubs = {row["networkNodeId"]: row for row in data["publications"]}
        self.assertEqual(pubs[ferroni]["inventoryAudit"]["evidenceStatus"], "audited_source_access_gap")
        self.assertTrue(pubs[ferroni]["inventoryAudit"]["inventoryAndContractsAudited"])

    def test_serino_whole_inventory_preserves_adjacent_controls_and_source_conflicts(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        node = "doi:10.1038/srep18603"
        studies = {row["studyRowId"].rsplit("::", 1)[-1]: row for row in data["studies"] if row["networkNodeId"] == node}
        self.assertEqual(set(studies), set("abcdefghij"))
        contracts = {suffix: {row["key"]: row for row in study["contracts"]} for suffix, study in studies.items()}
        for suffix in "ghij":
            self.assertEqual(studies[suffix]["parameterStatusCounts"], {"not_applicable": 11})
            self.assertEqual(studies[suffix]["templateIds"], [])
            self.assertEqual(studies[suffix]["nativeQualification"], "not_assessed")
        self.assertIn("visual-tactile", studies["g"]["experimentLabel"])
        self.assertIn("240", contracts["a"]["repetition_allocation"]["value"])
        self.assertIn("288", contracts["a"]["repetition_allocation"]["value"])
        for key in ("repetition_allocation", "baseline_trial_contract", "catch_trial_contract"):
            self.assertEqual(contracts["a"][key]["status"], "conflicting_evidence")
        for suffix in "bf":
            audio = contracts[suffix]["auditory_stimulus"]
            self.assertEqual(audio["status"], "conflicting_evidence")
            self.assertIn("44.1 kHz", audio["value"])
            self.assertIn("2048", audio["value"])
            self.assertIn("18.0618", audio["evidenceNote"])
            self.assertEqual(audio["components"]["level_envelope_calibration"]["status"], "conflicting_evidence")
        self.assertEqual(contracts["b"]["soa_schedule"]["status"], "conflicting_evidence")
        self.assertIn("without contact", contracts["d"]["trajectory_kinematics"]["components"]["coordinate_frame_body_anchor"]["value"])
        for suffix in "def":
            self.assertEqual(contracts[suffix]["soa_schedule"]["status"], "approximation_required")
            self.assertEqual(contracts[suffix]["block_order_contract"]["components"]["block_count"]["status"], "not_reported")
        self.assertIn("per participant", contracts["f"]["repetition_allocation"]["components"]["repetitions_or_exact_counts"]["value"])
        self.assertIn("between subjects", contracts["f"]["repetition_allocation"]["components"]["factor_dimensions"]["value"])
        publication = next(row for row in data["publications"] if row["networkNodeId"] == node)
        self.assertTrue(publication["inventoryAudit"]["inventoryAndContractsAudited"])
        self.assertEqual(publication["inventoryAudit"]["studyRowCount"], 10)

    def test_jazz_author_version_preserves_control_and_pilot_limits(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        parent = "doi:10.1007/s00426-020-01365-6"
        ids = [parent + "::" + suffix for suffix in "abc"]
        self.assertEqual(data["studyRowAliases"][parent], ids)
        studies = {row["studyRowId"]: row for row in data["studies"]}
        for study_id in ids:
            self.assertEqual(studies[study_id]["inventoryStatus"], "author_version_inventory_assessed_final_comparison_pending")
            self.assertEqual(studies[study_id]["evidenceScope"], "study_specific_source_review")
            self.assertNotIn("not_assessed", studies[study_id]["parameterStatusCounts"])
            for contract in studies[study_id]["contracts"]:
                self.assertEqual(contract["evidenceSourceUrl"], "https://backoffice.biblio.ugent.be/download/8673877/8673880")
                self.assertEqual(contract["sourceUrl"], "https://doi.org/10.1007/s00426-020-01365-6")
                self.assertEqual(contract["sourceType"], "author_thesis_chapter_final_comparison_pending")
        main = {row["key"]: row for row in studies[ids[0]]["contracts"]}
        control = {row["key"]: row for row in studies[ids[1]]["contracts"]}
        pilot = {row["key"]: row for row in studies[ids[2]]["contracts"]}
        self.assertEqual(main["repetition_allocation"]["status"], "derived_complete")
        self.assertIn("600", main["repetition_allocation"]["value"])
        self.assertIn("120", control["repetition_allocation"]["value"])
        self.assertNotIn("600", control["repetition_allocation"]["value"])
        self.assertEqual(pilot["repetition_allocation"]["status"], "partial")
        self.assertEqual(pilot["catch_trial_contract"]["status"], "not_reported")
        self.assertIn("source_recipe_or_asset_provenance", main["auditory_stimulus"]["missingComponents"])
        self.assertEqual(main["jitter_iti_policy"]["status"], "partial")
        self.assertIn("50-ms 784-Hz tone with 50-Hz", main["auditory_stimulus"]["value"])
        self.assertIn("and 5-ms", main["auditory_stimulus"]["value"])
        # Resolving the compact review must not promote the coarse composite
        # record or imply equivalence with the inaccessible final article.
        index = read_csv(self.output_dir / "study_instance_index.csv")[1]
        self.assertEqual(next(row for row in index if row["study_row_id"] == ids[0])["parameter_evidence_scope"], "composite_requires_split")

    def test_duration_and_front_rear_contracts_preserve_source_controls(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        studies = {row["studyRowId"]: row for row in data["studies"]}
        ra = "doi:10.61782/fa.2025.0866"
        self.assertEqual(data["studyRowAliases"][ra], [ra + "::a", ra + "::b"])
        for suffix, last in [("a", "1750"), ("b", "2625")]:
            cs = {c["key"]: c for c in studies[ra + "::" + suffix]["contracts"]}
            self.assertIn(last, cs["soa_schedule"]["value"])
            self.assertIn("245", cs["repetition_allocation"]["value"])
            self.assertIn("200 ms", cs["tactile_target"]["value"])
            self.assertIn("80 Hz", cs["tactile_target"]["value"])
            self.assertIn("15×15", cs["tactile_target"]["evidenceNote"])
        cs = {c["key"]: c for c in studies["doi:10.1016/j.cortex.2025.11.015"]["contracts"]}
        self.assertIn("1600", cs["repetition_allocation"]["value"])
        self.assertIn("retain", cs["trial_sequence"]["value"])
        self.assertEqual(cs["trajectory_kinematics"]["components"]["timing_constraint"]["status"], "not_reported")
        self.assertIn("160 fixed endpoint", cs["baseline_trial_contract"]["components"]["resolved_trial_count"]["value"])
        occelli = next(x for x in data["publications"] if x["networkNodeId"] == "doi:10.1080/17470210903068989")
        self.assertEqual(occelli["inventoryAudit"]["evidenceStatus"], "audited_source_access_gap")

    def test_collignon_full_contract_audit_preserves_electrical_ambiguity(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        node = "doi:10.1016/j.neuropsychologia.2009.07.025"
        study = next(x for x in data["studies"] if x["studyRowId"] == node)
        cs = {c["key"]: c for c in study["contracts"]}
        self.assertEqual(cs["auditory_stimulus"]["status"], "approximation_required")
        self.assertIn("five 1-ms", cs["tactile_target"]["value"])
        self.assertIn("25 ms", cs["tactile_target"]["value"])
        self.assertEqual(cs["tactile_target"]["components"]["waveform_and_duration"]["status"], "not_reported")
        self.assertIn("not proof", cs["tactile_target"]["evidenceNote"])
        self.assertEqual(cs["jitter_iti_policy"]["components"]["timing_scope_and_anchor"]["status"], "not_reported")
        self.assertEqual(cs["repetition_allocation"]["status"], "derived_complete")
        pub = next(x for x in data["publications"] if x["networkNodeId"] == node)
        self.assertTrue(pub["inventoryAudit"]["inventoryAndContractsAudited"])

    def test_context_audit_keeps_access_and_exact_preprint_phase_boundaries(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        studies = {row["studyRowId"]: row for row in data["studies"]}
        pubs = {row["networkNodeId"]: row for row in data["publications"]}
        h = "doi:10.1016/j.actpsy.2011.01.003"
        a = "doi:10.1101/2025.09.02.673729"
        self.assertEqual(data["studyRowAliases"][h], [h + "::" + s for s in "abcd"])
        self.assertEqual(pubs[h]["inventoryAudit"]["evidenceStatus"], "audited_source_access_gap")
        for sid in [h + "::" + s for s in "abcd"] + [a + "::a", a + "::b"]:
            self.assertEqual(studies[sid]["parameterStatusCounts"], {"not_applicable": 11})
            self.assertEqual(studies[sid]["templateIds"], [])
        listening = {c["key"]: c for c in studies[a + "::a"]["contracts"]}
        survey = {c["key"]: c for c in studies[a + "::b"]["contracts"]}
        self.assertIn("18", listening["repetition_allocation"]["value"])
        self.assertIn("13", survey["repetition_allocation"]["value"])
        self.assertIn("not imported", survey["repetition_allocation"]["evidenceNote"])
        self.assertIn("No delivered tactile", survey["tactile_target"]["value"])

    def test_observation_and_elongation_inventory_preserves_timing_limits(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        studies = {row["studyRowId"]: row for row in data["studies"]}
        gal = "doi:10.1016/j.neuropsychologia.2020.107622"
        cim = "doi:10.3233/rnn-120286"
        for node in (gal, cim):
            self.assertEqual(data["studyRowAliases"][node], [node + "::a", node + "::b"])
        for sid in (gal + "::a", cim + "::b"):
            self.assertEqual(studies[sid]["parameterStatusCounts"], {"not_applicable": 11})
            self.assertEqual(studies[sid]["templateIds"], [])
        cs = {c["key"]: c for c in studies[gal + "::b"]["contracts"]}
        self.assertEqual(cs["soa_schedule"]["status"], "partial")
        self.assertIn("up to 40 ms", cs["soa_schedule"]["value"])
        self.assertIn("post-only", cs["block_order_contract"]["value"])
        self.assertIn("360", cs["repetition_allocation"]["value"])
        cs = {c["key"]: c for c in studies[cim + "::a"]["contracts"]}
        self.assertEqual(cs["block_order_contract"]["status"], "conflicting_evidence")
        self.assertIn("strong", cs["catch_trial_contract"]["value"])
        self.assertIn("follow-up", cs["repetition_allocation"]["derivationNote"])
        big = studies["doi:10.1016/j.neuropsychologia.2017.07.018"]
        self.assertTrue(all("retained_primary" in c["sourceType"] for c in big["contracts"]))

    def test_social_motion_inventory_keeps_controls_and_version_limits(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        studies = {row["studyRowId"]: row for row in data["studies"]}
        publications = {row["networkNodeId"]: row for row in data["publications"]}
        ten = "doi:10.1016/j.cub.2013.01.043"
        walk = "doi:10.1016/j.neuropsychologia.2014.08.030"
        for sid in [ten + "::d", ten + "::e", ten + "::f", walk + "::c"]:
            self.assertEqual(studies[sid]["parameterStatusCounts"], {"not_applicable": 11})
            self.assertEqual(studies[sid]["templateIds"], [])
        cs = {c["key"]: c for c in studies[ten + "::c"]["contracts"]}
        self.assertEqual(cs["baseline_trial_contract"]["status"], "not_reported")
        self.assertEqual(cs["repetition_allocation"]["status"], "partial")
        self.assertIn("3700", cs["soa_schedule"]["value"])
        self.assertEqual(publications[walk]["inventoryAudit"]["evidenceStatus"], "author_version_methods_reviewed_final_comparison_pending")
        for suffix in "ab":
            cs = {c["key"]: c for c in studies[walk + "::" + suffix]["contracts"]}
            self.assertIn("512", cs["repetition_allocation"]["value"])
            self.assertIn("not source fact", cs["block_order_contract"]["value"])
        mat = studies["doi:10.1038/s41598-021-90784-5"]
        cs = {c["key"]: c for c in mat["contracts"]}
        self.assertEqual(cs["jitter_iti_policy"]["status"], "not_reported")
        self.assertIn("without audio", cs["baseline_trial_contract"]["value"])
        self.assertIn("24 ms", cs["tactile_target"]["value"])

    def test_ronga_fresh_supplement_keeps_jitter_and_pilot_separate(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        node = "doi:10.1073/pnas.2024548118"
        self.assertEqual(data["studyRowAliases"][node], [node + "::a", node + "::b", node + "::c"])
        studies = {row["studyRowId"]: row for row in data["studies"]}
        for suffix in "ab":
            cs = {row["key"]: row for row in studies[node + "::" + suffix]["contracts"]}
            self.assertIn("4–6 s", cs["jitter_iti_policy"]["components"]["values_or_range"]["value"])
            self.assertEqual(cs["jitter_iti_policy"]["components"]["distribution"]["status"], "not_reported")
            self.assertIn("−40", cs["soa_schedule"]["derivationNote"])
            self.assertEqual(cs["catch_trial_contract"]["status"], "not_applicable")
            self.assertIn("EEG", cs["baseline_trial_contract"]["value"])
        self.assertEqual(studies[node + "::c"]["parameterStatusCounts"], {"not_applicable": 11})
        self.assertEqual(studies[node + "::c"]["templateIds"], [])
        self.assertTrue(all("Five-newborn" in c["value"] for c in studies[node + "::c"]["contracts"]))

    def test_cane_review_distinguishes_emission_soa_and_group_schedule(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        node = "doi:10.1111/j.1467-9280.2007.01952.x"
        study = next(row for row in data["studies"] if row["studyRowId"] == node)
        cs = {row["key"]: row for row in study["contracts"]}
        self.assertEqual(cs["soa_schedule"]["status"], "derived_complete")
        self.assertIn("+5 ms", cs["soa_schedule"]["derivationNote"])
        self.assertIn("300", cs["repetition_allocation"]["derivationNote"])
        self.assertIn("600", cs["repetition_allocation"]["derivationNote"])
        self.assertEqual(cs["tactile_target"]["components"]["waveform_and_duration"]["status"], "not_reported")
        self.assertEqual(cs["jitter_iti_policy"]["status"], "not_reported")
        self.assertEqual(cs["catch_trial_contract"]["status"], "partial")
        self.assertEqual(study["nativeQualification"], "not_assessed")
        publication = next(row for row in data["publications"] if row["networkNodeId"] == node)
        self.assertTrue(publication["inventoryAudit"]["inventoryAndContractsAudited"])
        self.assertEqual(publication["inventoryAudit"]["studyRowCount"], 1)

    def test_teneggi_template_association_is_experiment_three_only(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        studies = {row["studyRowId"]: row for row in data["studies"]}
        node = "doi:10.1016/j.cub.2013.01.043"
        self.assertEqual(studies[node + "::a"]["templateIds"], [])
        self.assertEqual(studies[node + "::b"]["templateIds"], [])
        self.assertEqual(studies[node + "::c"]["templateIds"], ["teneggi_2013_social_face_pps"])
        self.assertEqual(studies[node + "::c"]["nativeQualification"], "not_assessed")

    def test_canzoneri_controls_retain_sound_and_localizer_is_adjacent(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        node = "doi:10.1371/journal.pone.0044306"
        self.assertEqual(data["studyRowAliases"][node], [node + "::a", node + "::b"])
        studies = {row["studyRowId"]: row for row in data["studies"]}
        main, localizer = studies[node + "::a"], studies[node + "::b"]
        cs = {row["key"]: row for row in main["contracts"]}
        self.assertIn("sound remains present", cs["baseline_trial_contract"]["value"])
        self.assertIn("−700/+3600", cs["baseline_trial_contract"]["value"])
        self.assertIn("100 µs", cs["tactile_target"]["components"]["waveform_and_duration"]["value"])
        self.assertEqual(cs["task_response"]["status"], "partial")
        self.assertEqual(cs["jitter_iti_policy"]["status"], "partial")
        self.assertEqual(localizer["parameterStatusCounts"], {"not_applicable": 11})
        self.assertEqual(localizer["templateIds"], [])
        self.assertIn("canzoneri_2012_dynamic_sounds", main["templateIds"])
        self.assertTrue(all("overlap" in c["value"] for c in localizer["contracts"]))

    def test_plasticity_four_slots_are_access_audited_not_methods_confirmed(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        node = "doi:10.1016/j.neuropsychologia.2026.109490"
        publication = next(row for row in data["publications"] if row["networkNodeId"] == node)
        audit = publication["inventoryAudit"]
        self.assertEqual(audit["evidenceStatus"], "audited_source_access_gap")
        self.assertTrue(audit["inventoryAndContractsAudited"])
        self.assertEqual(audit["studyRowCount"], 4)
        for study in [row for row in data["studies"] if row["studyRowId"].startswith(node + "::")]:
            self.assertEqual(study["parameterStatusCounts"], {"source_unavailable": 11})
            self.assertEqual(study["nativeQualification"], "not_assessed")
            self.assertTrue(all("metadata response is not access to Methods" in c["evidenceNote"] for c in study["contracts"]))
            self.assertEqual(study["templateIds"], [])

    def test_accepted_social_body_protocols_keep_different_timing_and_cohort_boundaries(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        studies = {row["studyRowId"]: row for row in data["studies"]}
        maister = studies["doi:10.1016/j.neuropsychologia.2014.10.027"]
        node = "doi:10.1177/1362361319838950"
        at, fbi = studies[node + "::a"], studies[node + "::b"]
        self.assertEqual(data["studyRowAliases"][node], [node + "::a", node + "::b"])
        mc = {row["key"]: row for row in maister["contracts"]}
        ac = {row["key"]: row for row in at["contracts"]}
        self.assertIn("2.700", mc["soa_schedule"]["value"])
        self.assertIn("2.500", ac["soa_schedule"]["value"])
        self.assertIn("0.2 ms", mc["tactile_target"]["value"])
        self.assertIn("4 mm magnet", ac["tactile_target"]["value"])
        self.assertEqual(ac["tactile_target"]["components"]["waveform_and_duration"]["status"], "not_reported")
        self.assertEqual(mc["catch_trial_contract"]["status"], "not_reported")
        self.assertEqual(ac["catch_trial_contract"]["status"], "reported_complete")
        self.assertIn("200", mc["repetition_allocation"]["derivationNote"])
        self.assertIn("65", ac["repetition_allocation"]["derivationNote"])
        self.assertIn("before", ac["block_order_contract"]["value"])
        self.assertEqual(fbi["parameterStatusCounts"], {"not_applicable": 11})
        for study in (maister, at, fbi):
            self.assertEqual(study["nativeQualification"], "not_assessed")
            self.assertTrue(all(c["sourceType"] == "accepted_author_manuscript_final_comparison_pending" for c in study["contracts"]))

    def test_pellencin_boundary_retains_access_gap_without_auditory_protocol(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        node = "doi:10.1016/j.cortex.2017.08.033"
        self.assertEqual(data["studyRowAliases"][node], [node + "::a", node + "::b"])
        publication = next(row for row in data["publications"] if row["networkNodeId"] == node)
        self.assertEqual(publication["inventoryAudit"]["evidenceStatus"], "audited_source_access_gap")
        self.assertTrue(publication["inventoryAudit"]["inventoryAndContractsAudited"])
        for study in [row for row in data["studies"] if row["studyRowId"].startswith(node + "::")]:
            self.assertEqual(study["parameterStatusCounts"], {"not_applicable": 11})
            self.assertIn("minimum_two", study["inventoryStatus"])
            self.assertEqual(study["templateIds"], [])
            self.assertEqual(study["nativeQualification"], "not_assessed")

    def test_interoception_versions_keep_negative_soa_and_distinct_current_evidence(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        studies = {row["studyRowId"]: row for row in data["studies"]}
        final = studies["doi:10.1073/pnas.2516229122"]
        pre = studies["doi:10.1101/2025.06.25.660685"]
        for study in (final, pre):
            cs = {row["key"]: row for row in study["contracts"]}
            self.assertEqual(cs["soa_schedule"]["status"], "derived_complete")
            self.assertIn("−0.040", cs["soa_schedule"]["derivationNote"])
            self.assertIn("300", cs["repetition_allocation"]["value"])
            self.assertIn("120", cs["catch_trial_contract"]["value"])
            self.assertEqual(cs["jitter_iti_policy"]["components"]["distribution"]["status"], "not_reported")
            self.assertEqual(cs["task_response"]["components"]["response_window_and_anchor"]["status"], "not_reported")
            self.assertEqual(study["nativeQualification"], "not_assessed")
        fc = {row["key"]: row for row in final["contracts"]}
        pc = {row["key"]: row for row in pre["contracts"]}
        self.assertEqual(fc["tactile_target"]["status"], "partial")
        self.assertEqual(pc["tactile_target"]["status"], "conflicting_evidence")
        self.assertIn("2.5–5.1", fc["tactile_target"]["value"])
        self.assertIn("25.3–51", pc["tactile_target"]["value"])
        self.assertNotEqual(fc["tactile_target"]["evidenceSourceUrl"], pc["tactile_target"]["evidenceSourceUrl"])
        pubs = {row["networkNodeId"]: row for row in data["publications"]}
        gap = pubs["doi:10.1016/j.cognition.2018.04.001"]["inventoryAudit"]
        self.assertEqual(gap["evidenceStatus"], "audited_source_access_gap")
        self.assertTrue(gap["inventoryAndContractsAudited"])
        self.assertEqual(gap["studyRowCount"], 1)

    def test_wheelchair_groups_share_blindfolded_acquisition_without_timing_defaults(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        node = "doi:10.3389/fpsyg.2015.00639"
        publication = next(row for row in data["publications"] if row["networkNodeId"] == node)
        self.assertTrue(publication["inventoryAudit"]["inventoryAndContractsAudited"])
        self.assertEqual(publication["inventoryAudit"]["studyRowCount"], 3)
        studies = [row for row in data["studies"] if row["studyRowId"].startswith(node + "::")]
        for study in studies:
            cs = {row["key"]: row for row in study["contracts"]}
            self.assertEqual(study["evidenceScope"], "study_specific_source_review")
            self.assertEqual(cs["soa_schedule"]["status"], "reported_complete")
            self.assertIn("2280", cs["soa_schedule"]["value"])
            self.assertIn("432", cs["repetition_allocation"]["derivationNote"])
            self.assertIn("216", cs["repetition_allocation"]["value"])
            for key in ("task_response", "jitter_iti_policy", "baseline_trial_contract", "catch_trial_contract", "block_order_contract", "tactile_target"):
                self.assertEqual(cs[key]["status"], "partial")
            self.assertEqual(cs["task_response"]["components"]["response_window_and_anchor"]["status"], "not_reported")
            self.assertIn("offline", cs["task_response"]["value"])
            self.assertEqual(cs["tactile_target"]["components"]["intensity_or_calibration"]["status"], "not_reported")
            self.assertEqual(cs["baseline_trial_contract"]["components"]["allocation_rule"]["status"], "not_reported")
            self.assertEqual(cs["auditory_stimulus"]["evidenceSourceUrl"], "https://www.ebi.ac.uk/europepmc/webservices/rest/PMC4435246/fullTextXML")

    def test_inventory_audit_does_not_count_registry_presence_as_methods_review(self) -> None:
        rows = read_csv(self.output_dir / "publication_inventory_audit.csv")[1]
        self.assertEqual(len(rows), 94)
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        summary = data["inventoryAudit"]
        self.assertEqual(summary["registeredInventories"], 76)
        self.assertEqual(summary["methodsReviewedInventories"], 62)
        self.assertEqual(summary["auditedAccessBlockers"], 11)
        self.assertEqual(summary["inventoryEvidenceCounts"], dict(Counter(row["inventory_evidence_status"] for row in rows)))
        self.assertEqual(summary["inventoryAndContractsAudited"], sum(row["inventory_and_contracts_audited"] == "yes" for row in rows))
        self.assertEqual(summary["remainingInventoryOrContractAudit"], 94 - summary["inventoryAndContractsAudited"])
        by_node = {row["network_node_id"]: row for row in rows}
        holmes = by_node["doi:10.1007/s00221-020-05771-5"]
        self.assertEqual(holmes["inventory_evidence_status"], "primary_methods_reviewed")
        self.assertEqual(holmes["inventory_and_contracts_audited"], "yes")
        for source_partial in rows:
            if source_partial["all_rows_have_eleven_source_dispositions"] == "no":
                self.assertEqual(source_partial["inventory_and_contracts_audited"], "no")
        gap = by_node["doi:10.1007/s00221-017-5158-2"]
        self.assertEqual(gap["inventory_evidence_status"], "audited_source_access_gap")
        self.assertEqual(gap["inventory_and_contracts_audited"], "yes")
        self.assertEqual(data["scope"]["nativeQualification"], "not_assessed")
        for publication in data["publications"]:
            row = by_node[publication["networkNodeId"]]
            audit = publication["inventoryAudit"]
            self.assertEqual(audit["evidenceStatus"], row["inventory_evidence_status"])
            self.assertEqual(audit["studyRowCount"], len(publication["studyIds"]))
            self.assertIs(audit["inventoryAndContractsAudited"], row["inventory_and_contracts_audited"] == "yes")
            self.assertIs(audit["allRowsHaveElevenSourceDispositions"], row["all_rows_have_eleven_source_dispositions"] == "yes")

    def test_ieeg_versions_preserve_trial_units_and_source_unit_interpretation(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        studies = {row["studyRowId"]: row for row in data["studies"]}
        for node in ("doi:10.1093/cercor/bhy156", "doi:10.1101/249078"):
            contracts = {row["key"]: row for row in studies[node]["contracts"]}
            self.assertEqual(contracts["auditory_stimulus"]["status"], "partial")
            self.assertEqual(contracts["tactile_target"]["status"], "partial")
            self.assertEqual(contracts["soa_schedule"]["status"], "derived_complete")
            self.assertIn("2500m", contracts["soa_schedule"]["derivationNote"])
            self.assertIn("255", contracts["repetition_allocation"]["value"])
            self.assertIn("510", contracts["repetition_allocation"]["derivationNote"])
            self.assertEqual(contracts["task_response"]["status"], "reported_complete")
            self.assertEqual(contracts["catch_trial_contract"]["status"], "explicitly_absent")
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        preprint = next(row for row in registry["entries"] if row["network_node_id"] == "doi:10.1101/249078")
        self.assertEqual(preprint["source_lineage"]["relationship"], "preprint_of_final_same_experiment_methods_compared")

    def test_inventory_gate_rejects_unreviewed_components_in_partial_override(self) -> None:
        spec = importlib.util.spec_from_file_location("compact_inventory_builder", BUILDER.with_name("build_parsimonious_publication_matrix.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        node = "doi:10.1007/s00221-017-5158-2"
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        registry["entries"] = [row for row in registry["entries"] if row["network_node_id"] == node]
        studies = [row for row in read_csv(self.output_dir / "study_instance_index.csv")[1] if row["network_node_id"] == node]
        cells = [row for row in read_csv(self.output_dir / "parsimonious_contract_evidence.csv")[1] if row["network_node_id"] == node]
        _, baseline = module.inventory_review_audit(registry, studies, cells)
        self.assertEqual(baseline["inventoryAndContractsAudited"], 1)
        for unreviewed in ("not_assessed", "composite_requires_split"):
            changed = [dict(row) for row in cells]
            changed[0]["evidence_status"] = "partial"
            changed[0]["component_status_json"] = json.dumps({"source_mode": unreviewed})
            _, result = module.inventory_review_audit(registry, studies, changed)
            self.assertEqual(result["inventoryAndContractsAudited"], 0)
            self.assertEqual(result["remainingInventoryOrContractAudit"], 1)
        registry["entries"][0]["inventory_evidence_status"] = "abstract_or_metadata_inventory"
        _, abstract_only = module.inventory_review_audit(registry, studies, cells)
        self.assertEqual(abstract_only["publicationsWithAllContractDispositions"], 1)
        self.assertEqual(abstract_only["inventoryAndContractsAudited"], 0)

    def test_depersonalisation_versions_do_not_transfer_conflicted_supplement(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        studies = {row["studyRowId"]: row for row in data["studies"]}
        final = {row["key"]: row for row in studies["doi:10.1177/17470218241261645"]["contracts"]}
        pre = {row["key"]: row for row in studies["doi:10.31234/osf.io/t8h6a"]["contracts"]}
        self.assertIn("44.1", final["auditory_stimulus"]["value"])
        self.assertNotIn("44.1", pre["auditory_stimulus"]["value"])
        self.assertEqual(final["auditory_stimulus"]["sourceType"], "retained_primary_pdf_review_fresh_access_blocked")
        self.assertEqual(final["jitter_iti_policy"]["status"], "not_reported")
        self.assertEqual(pre["jitter_iti_policy"]["status"], "conflicting_evidence")
        self.assertIn("1000", pre["jitter_iti_policy"]["value"])
        self.assertEqual(pre["repetition_allocation"]["status"], "conflicting_evidence")
        self.assertIn("180", pre["repetition_allocation"]["components"]["repetitions_or_exact_counts"]["value"])
        self.assertIn("120", pre["repetition_allocation"]["value"])
        self.assertEqual(final["repetition_allocation"]["status"], "partial")
        self.assertEqual(pre["tactile_target"]["status"], "conflicting_evidence")
        self.assertEqual(pre["auditory_stimulus"]["evidenceSourceUrl"], "https://osf.io/download/86j4g/")

    def test_footsole_report_distinguishes_target_context_and_source_access(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        studies = {row["studyRowId"]: row for row in data["studies"]}
        for node in ("doi:10.1109/whc.2017.7989970", "doi:10.1177/0956797619869337"):
            self.assertEqual(studies[node]["inventoryStatus"], "source_access_blocked_experiment_inventory_unresolved")
            self.assertEqual(studies[node]["parameterStatusCounts"], {"source_unavailable": 11})
        report_id = "doi:10.53829/ntr201911fa4"
        report = {row["key"]: row for row in studies[report_id]["contracts"]}
        self.assertIn("removes heel vibration", report["baseline_trial_contract"]["value"])
        self.assertIn("retaining", report["baseline_trial_contract"]["value"])
        self.assertIn("150-Hz chest", report["tactile_target"]["value"])
        self.assertEqual(report["catch_trial_contract"]["status"], "not_reported")
        self.assertEqual(report["soa_schedule"]["status"], "partial")
        self.assertEqual(report["jitter_iti_policy"]["status"], "not_reported")
        self.assertEqual(report["auditory_stimulus"]["evidenceSourceUrl"], "https://www.ntt-review.jp/archive/ntttechnical.php?contents=ntr201911fa4.pdf&mode=show_pdf")
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        row = next(row for row in registry["entries"] if row["network_node_id"] == report_id)
        self.assertEqual(row["instances"][0]["instance_kind"], "summary_of_existing_protocol")
        self.assertEqual(row["source_lineage"]["network_node_id"], "doi:10.1177/0956797619869337")
        exception = next(row for row in registry["corpus_freeze"]["identity_audit"]["known_identity_exceptions"] if row["network_node_id"] == "doi:10.1109/whc.2017.7989970")
        self.assertEqual(exception["other_doi"], "10.1109/WHC.2017.7989907")
        self.assertEqual(registry["corpus_freeze"]["publication_count"], 94)

    def test_consciousness_versions_preserve_calibration_and_synchrony_limits(self) -> None:
        data = json.loads(self.public_output.read_text(encoding="utf-8"))
        studies = {row["studyRowId"]: row for row in data["studies"]}
        final_id = "doi:10.1016/j.xcrm.2026.102705"
        pre_id = "doi:10.1101/2024.10.25.619776"
        self.assertEqual(data["studyRowAliases"][pre_id], [pre_id + "::a", pre_id + "::b"])
        final = {row["key"]: row for row in studies[final_id + "::a"]["contracts"]}
        pre = {row["key"]: row for row in studies[pre_id + "::a"]["contracts"]}
        self.assertEqual(final["soa_schedule"]["status"], "reported_complete")
        self.assertEqual(pre["soa_schedule"]["status"], "not_reported")
        for contracts in (final, pre):
            self.assertEqual(contracts["tactile_target"]["status"], "conflicting_evidence")
            self.assertIn("requesting higher intensity decreases", contracts["tactile_target"]["components"]["intensity_or_calibration"]["value"])
            self.assertEqual(contracts["repetition_allocation"]["status"], "partial")
            self.assertIn("sleep_trial_allocation", contracts["repetition_allocation"]["missingComponents"])
            self.assertEqual(contracts["catch_trial_contract"]["status"], "explicitly_absent")
        clinical_pre = {row["key"]: row for row in studies[pre_id + "::b"]["contracts"]}
        self.assertIn("Participants section", clinical_pre["repetition_allocation"]["evidenceNote"])
        self.assertEqual(clinical_pre["tactile_target"]["status"], "partial")
        tool_id = "doi:10.1016/j.cortex.2021.08.004"
        self.assertEqual(data["studyRowAliases"][tool_id], [tool_id + "::" + suffix for suffix in "abc"])
        for suffix in "abc":
            self.assertEqual(studies[tool_id + "::" + suffix]["parameterStatusCounts"], {"source_unavailable": 11})

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
