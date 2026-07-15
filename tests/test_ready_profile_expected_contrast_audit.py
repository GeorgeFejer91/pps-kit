from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "validation_protocols" / "scripts" / "run_ready_profile_expected_contrast_audit.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("run_ready_profile_expected_contrast_audit", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_ready_profile_expected_contrast_audit_reports_supported_and_missing_contrasts(tmp_path: Path):
    audit = _load_script()
    rows_path = tmp_path / "roussel_analysis_ready_trials.csv"
    serino_rows_path = tmp_path / "serino_analysis_ready_trials.csv"
    matsuda_rows_path = tmp_path / "matsuda_analysis_ready_trials.csv"
    lamia_rows_path = tmp_path / "lamia_analysis_ready_trials.csv"
    _write_csv(
        rows_path,
        [
            {
                "row_label": "DynaSpace looming source",
                "respiratory_phase": "DynaSpace looming source",
                "family": "audio_tactile",
                "soa_ms": "105",
            },
            {
                "row_label": "DynaSpace fixed 640 cm source",
                "respiratory_phase": "DynaSpace fixed 640 cm source",
                "family": "audio_tactile",
                "soa_ms": "105",
            },
        ],
    )
    _write_csv(
        serino_rows_path,
        [
            {
                "row_label": "Peri-trunk moving-sound trial",
                "respiratory_phase": "Peri-trunk moving-sound trial",
                "sequence_labels": "Trunk moving sound",
                "sequence_variant_key": "trunk_moving_sound",
                "family": "audio_tactile",
                "soa_ms": "0",
            },
            {
                "row_label": "Peri-trunk moving-sound trial",
                "respiratory_phase": "Peri-trunk moving-sound trial",
                "sequence_labels": "Trunk moving sound",
                "sequence_variant_key": "trunk_moving_sound",
                "family": "audio_tactile",
                "soa_ms": "4318",
            },
            {
                "row_label": "Peri-trunk moving-sound trial",
                "respiratory_phase": "Peri-trunk moving-sound trial",
                "sequence_labels": "Trunk moving sound - receding",
                "sequence_variant_key": "trunk_moving_sound_receding",
                "family": "audio_tactile",
                "soa_ms": "0",
            },
            {
                "row_label": "Peri-trunk moving-sound trial",
                "respiratory_phase": "Peri-trunk moving-sound trial",
                "sequence_labels": "Trunk moving sound - receding",
                "sequence_variant_key": "trunk_moving_sound_receding",
                "family": "audio_tactile",
                "soa_ms": "4318",
            },
        ],
    )
    matsuda_rows: list[dict[str, str]] = []
    for block_label in ("Front direction", "Rear direction", "Left direction", "Right direction"):
        for sequence_label in ("Pink moving sound", "Pink moving sound - receding"):
            for soa_ms in ("300", "2700"):
                matsuda_rows.append(
                    {
                        "block_label": block_label,
                        "row_label": "Sound-motion PPS trial",
                        "respiratory_phase": "Sound-motion PPS trial",
                        "sequence_labels": sequence_label,
                        "sequence_variant_key": sequence_label.lower().replace(" - ", "_").replace(" ", "_"),
                        "family": "audio_tactile",
                        "soa_ms": soa_ms,
                    }
                )
    _write_csv(matsuda_rows_path, matsuda_rows)
    lamia_rows: list[dict[str, str]] = []
    for block_label in ("Trunk motor block", "Trunk static block", "Hand motor block", "Hand static block"):
        for sequence_label in ("Pink moving sound", "Pink moving sound - receding"):
            for soa_ms in ("300", "2700"):
                lamia_rows.append(
                    {
                        "block_label": block_label,
                        "row_label": "Arm-movement sound-motion trial",
                        "respiratory_phase": "Arm-movement sound-motion trial",
                        "sequence_labels": sequence_label,
                        "sequence_variant_key": sequence_label.lower().replace(" - ", "_").replace(" ", "_"),
                        "family": "audio_tactile",
                        "soa_ms": soa_ms,
                    }
                )
    _write_csv(lamia_rows_path, lamia_rows)
    smoke_path = tmp_path / "runner_smoke.json"
    smoke_path.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "template_id": "roussel_2025_dynaspace_mobile_pps",
                        "outputs": {"analysis_ready_trials": str(rows_path)},
                    },
                    {
                        "template_id": "noel_2015_bodily_self",
                        "outputs": {"analysis_ready_trials": str(tmp_path / "missing.csv")},
                    },
                    {
                        "template_id": "serino_2015_peri_trunk_exp1",
                        "outputs": {"analysis_ready_trials": str(serino_rows_path)},
                    },
                    {
                        "template_id": "matsuda_2021_four_directions",
                        "outputs": {"analysis_ready_trials": str(matsuda_rows_path)},
                    },
                    {
                        "template_id": "barumerli_2026_arm_movement_exp1",
                        "outputs": {"analysis_ready_trials": str(lamia_rows_path)},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "record_id": "smartphone_rt_methods_2025",
                        "citation_short": "Roussel 2025",
                        "observed_comparison_gap": audit.READY_GAP,
                        "current_template_ids": ["roussel_2025_dynaspace_mobile_pps"],
                        "expected_outcome": {"expected_effect_direction": "looming_faster_than_static"},
                    },
                    {
                        "record_id": "noel_2015_bodily_self",
                        "citation_short": "Noel 2015",
                        "observed_comparison_gap": audit.READY_GAP,
                        "current_template_ids": ["noel_2015_bodily_self"],
                        "expected_outcome": {
                            "expected_effect_direction": "synchronous_front_expansion_and_back_reduction"
                        },
                    },
                    {
                        "record_id": "serino_2015_peri_trunk_exp1",
                        "citation_short": "Serino 2015",
                        "observed_comparison_gap": audit.READY_GAP,
                        "current_template_ids": ["serino_2015_peri_trunk_exp1"],
                        "expected_outcome": {
                            "expected_effect_direction": "near_or_approaching_trunk_sounds_speed_tactile_rt"
                        },
                    },
                    {
                        "record_id": "matsuda_2021_four_directions",
                        "citation_short": "Matsuda 2021",
                        "observed_comparison_gap": audit.READY_GAP,
                        "current_template_ids": ["matsuda_2021_four_directions"],
                        "expected_outcome": {
                            "expected_effect_direction": (
                                "approaching_sounds_show_pps_facilitation_across_four_directions"
                            )
                        },
                    },
                    {
                        "record_id": "lamia_2026_arm_movement",
                        "citation_short": "Lamia 2026",
                        "observed_comparison_gap": audit.READY_GAP,
                        "current_template_ids": ["barumerli_2026_arm_movement_exp1"],
                        "expected_outcome": {
                            "expected_effect_direction": "movement_blunts_looming_distance_facilitation"
                        },
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    report = audit.run_audit(
        ledger_path=ledger_path,
        runner_smoke_report=smoke_path,
        output_dir=tmp_path / "audit",
    )

    assert report["schema"] == audit.SCHEMA
    assert report["passed"]
    assert report["summary"] == {
        "ready_profile_record_count": 5,
        "synthetic_comparison_record_count": 4,
        "synthetic_comparison_passed_count": 4,
        "synthetic_comparison_failed_count": 0,
        "contrast_metadata_blocked_record_count": 1,
        "contrast_metadata_present_model_missing_record_count": 0,
    }
    by_id = {row["record_id"]: row for row in report["records"]}
    smartphone = by_id["smartphone_rt_methods_2025"]
    assert smartphone["status"] == "synthetic_behavioral_comparison_passed"
    assert smartphone["synthetic_comparison"]["fixed_minus_looming_ms"] == 25.0
    assert Path(smartphone["synthetic_comparison"]["synthetic_rows_csv"]).is_file()

    noel = by_id["noel_2015_bodily_self"]
    assert noel["status"] == "contrast_metadata_missing"
    assert noel["missing_contrasts"] == ["stroking_synchrony", "front_back_space"]
    assert "Propagate stroking_synchrony, front_back_space" in noel["required_next_step"]

    serino = by_id["serino_2015_peri_trunk_exp1"]
    assert serino["status"] == "synthetic_behavioral_comparison_passed"
    assert serino["missing_contrasts"] == []
    assert serino["synthetic_comparison"]["far_minus_near_ms"] == 45.0
    assert serino["synthetic_comparison"]["observed_effect_direction"] == (
        "near_or_approaching_trunk_sounds_speed_tactile_rt"
    )

    matsuda = by_id["matsuda_2021_four_directions"]
    assert matsuda["status"] == "synthetic_behavioral_comparison_passed"
    assert matsuda["missing_contrasts"] == []
    assert matsuda["synthetic_comparison"]["approaching_far_minus_near_ms"] == 42.0
    assert matsuda["synthetic_comparison"]["body_directions_observed"] == ["front", "left", "rear", "right"]
    assert matsuda["synthetic_comparison"]["observed_effect_direction"] == (
        "approaching_sounds_show_pps_facilitation_across_four_directions"
    )

    lamia = by_id["lamia_2026_arm_movement"]
    assert lamia["status"] == "synthetic_behavioral_comparison_passed"
    assert lamia["missing_contrasts"] == []
    assert lamia["synthetic_comparison"]["movement_states_observed"] == ["motor", "static"]
    assert lamia["synthetic_comparison"]["tactile_sites_observed"] == ["hand", "trunk"]
    assert lamia["synthetic_comparison"]["observed_effect_direction"] == (
        "movement_blunts_looming_distance_facilitation"
    )


def test_contrast_availability_requires_both_factor_poles_for_lamia():
    audit = _load_script()

    incomplete = audit._contrast_availability(
        "lamia_2026_arm_movement",
        [
            {
                "template_id": "barumerli_2026_arm_movement_exp1",
                "analysis_ready_trials": "",
                "rows": [
                    {
                        "family": "audio_tactile",
                        "block_label": "Arm movement block",
                        "row_label": "Arm-movement sound-motion trial",
                        "sequence_labels": "Pink moving sound - receding",
                        "soa_ms": "300",
                    }
                ],
            }
        ],
    )

    assert incomplete["auditory_motion_direction"]
    assert not incomplete["movement_state"]
    assert not incomplete["tactile_site"]

    complete = audit._contrast_availability(
        "lamia_2026_arm_movement",
        [
            {
                "template_id": "barumerli_2026_arm_movement_exp1",
                "analysis_ready_trials": "",
                "rows": [
                    {
                        "family": "audio_tactile",
                        "block_label": "Motor hand block",
                        "row_label": "Finger tactile site",
                        "sequence_labels": "Pink moving sound - receding",
                        "soa_ms": "300",
                    },
                    {
                        "family": "audio_tactile",
                        "block_label": "Static trunk block",
                        "row_label": "Chest tactile site",
                        "sequence_labels": "Pink moving sound",
                        "soa_ms": "2700",
                    },
                ],
            }
        ],
    )

    assert complete["movement_state"]
    assert complete["tactile_site"]


def test_contrast_availability_requires_complete_noel_and_pfeiffer_factor_poles():
    audit = _load_script()

    noel_front_async_only = audit._contrast_availability(
        "noel_2015_bodily_self",
        [
            {
                "template_id": "noel_2015_bodily_self",
                "analysis_ready_trials": "",
                "rows": [
                    {
                        "family": "audio_tactile",
                        "block_label": "Front asynchronous stroking block",
                        "row_label": "Bodily-self PPS trial",
                        "soa_ms": "190",
                    },
                    {
                        "family": "audio_tactile",
                        "block_label": "Front asynchronous stroking block",
                        "row_label": "Bodily-self PPS trial",
                        "soa_ms": "1140",
                    },
                ],
            }
        ],
    )
    assert not noel_front_async_only["stroking_synchrony"]
    assert not noel_front_async_only["front_back_space"]

    noel_front_sync_async = audit._contrast_availability(
        "noel_2015_bodily_self",
        [
            {
                "template_id": "noel_2015_bodily_self",
                "analysis_ready_trials": "",
                "rows": [
                    {
                        "family": "audio_tactile",
                        "block_label": "Front synchronous stroking block",
                        "row_label": "Bodily-self PPS trial",
                        "soa_ms": "190",
                    },
                    {
                        "family": "audio_tactile",
                        "block_label": "Front asynchronous stroking block",
                        "row_label": "Bodily-self PPS trial",
                        "soa_ms": "1140",
                    },
                ],
            }
        ],
    )
    assert noel_front_sync_async["stroking_synchrony"]
    assert not noel_front_sync_async["front_back_space"]

    pfeiffer_incomplete = audit._contrast_availability(
        "pfeiffer_2018_vestibular",
        [
            {
                "template_id": "pfeiffer_2018_lateral_perihead_left_to_right",
                "analysis_ready_trials": "",
                "rows": [
                    {
                        "family": "audio_tactile",
                        "block_label": "Incongruent vestibular rotation block",
                        "row_label": "Lateral motion PPS trial",
                        "soa_ms": "300",
                    }
                ],
            }
        ],
    )
    assert not pfeiffer_incomplete["vestibular_condition"]
    assert not pfeiffer_incomplete["audio_vestibular_congruence"]

    pfeiffer_complete = audit._contrast_availability(
        "pfeiffer_2018_vestibular",
        [
            {
                "template_id": "pfeiffer_2018_lateral_perihead_left_to_right",
                "analysis_ready_trials": "",
                "rows": [
                    {
                        "family": "audio_tactile",
                        "block_label": "Congruent vestibular rotation block",
                        "row_label": "Lateral motion PPS trial",
                        "soa_ms": "300",
                    },
                    {
                        "family": "audio_tactile",
                        "block_label": "Incongruent no rotation block",
                        "row_label": "Lateral motion PPS trial",
                        "soa_ms": "2700",
                    },
                ],
            }
        ],
    )
    assert pfeiffer_complete["vestibular_condition"]
    assert pfeiffer_complete["audio_vestibular_congruence"]
