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
        self.assertEqual(summary["studyInstances"], 121)
        self.assertEqual(summary["currentToolkitInputParameters"], 111)
        self.assertEqual(summary["currentInputReviewCells"], 13_431)
        self.assertEqual(summary["currentInputsOutsideTargetInventory"], 22)
        self.assertEqual(summary["targetMethodValidationParameters"], 281)
        self.assertEqual(summary["targetConfigurationCandidates"], 275)
        self.assertEqual(summary["targetValidationLeaves"], 6)
        self.assertEqual(summary["targetMethodReviewCells"], 34_001)
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
        self.assertEqual(len(dictionary), 111)
        self.assertEqual(len(paths), len(set(paths)))
        self.assertTrue(all(path.startswith("design.") for path in paths))
        self.assertEqual(matrix_header[-111:], paths)
        self.assertEqual(len(rows), 121)
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
        self.assertEqual(len(rows), 121)
        self.assertEqual(header[-111:], paths)
        self.assertTrue(all(row[path] for row in rows for path in paths))
        _, queue = read_csv(self.output_dir / "current_input_review_queue.csv")
        self.assertEqual(len(queue), 121 * 111)
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
        self.assertEqual(len(crosswalk), 111)
        uncovered = [row for row in crosswalk if row["mapped_target_count"] == "0"]
        self.assertEqual(len(uncovered), 22)

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
        self.assertEqual(len(rows), 121)
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
        self.assertEqual(len(registry["entries"]), 14)
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
        self.assertEqual(len(values), 3_108)

    def test_target_sidecar_is_complete_and_marks_composites(self) -> None:
        header, rows = read_csv(
            self.output_dir / "study_instance_target_method_evidence_sidecar.csv"
        )
        self.assertEqual(len(rows), 121 * 281)
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
        self.assertEqual(len(orientation), 121)
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
