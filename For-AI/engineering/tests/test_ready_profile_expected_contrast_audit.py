from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "For-AI/engineering/validation" / "scripts" / "run_ready_profile_expected_contrast_audit.py"


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
    noel_rows_path = tmp_path / "noel_analysis_ready_trials.csv"
    serino_rows_path = tmp_path / "serino_analysis_ready_trials.csv"
    serino_hand_rows_path = tmp_path / "serino_hand_analysis_ready_trials.csv"
    serino_front_back_rows_path = tmp_path / "serino_front_back_analysis_ready_trials.csv"
    matsuda_rows_path = tmp_path / "matsuda_analysis_ready_trials.csv"
    lamia_rows_path = tmp_path / "lamia_analysis_ready_trials.csv"
    pfeiffer_rows_path = tmp_path / "pfeiffer_analysis_ready_trials.csv"
    canzoneri_rows_path = tmp_path / "canzoneri_analysis_ready_trials.csv"
    tonelli_rows_path = tmp_path / "tonelli_analysis_ready_trials.csv"
    galli_rows_path = tmp_path / "galli_analysis_ready_trials.csv"
    lerner_rows_path = tmp_path / "lerner_analysis_ready_trials.csv"
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
    noel_rows: list[dict[str, str]] = []
    for block_label in (
        "Front synchronous stroking block",
        "Front asynchronous stroking block",
        "Back synchronous stroking block",
        "Back asynchronous stroking block",
    ):
        for soa_ms in ("190", "1140"):
            noel_rows.append(
                {
                    "block_label": block_label,
                    "row_label": "Bodily-self PPS trial",
                    "respiratory_phase": "Bodily-self PPS trial",
                    "family": "audio_tactile",
                    "soa_ms": soa_ms,
                }
            )
    _write_csv(noel_rows_path, noel_rows)
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
    _write_csv(
        serino_hand_rows_path,
        [
            {
                "row_label": "Peri-hand moving-sound trial",
                "respiratory_phase": "Peri-hand moving-sound trial",
                "sequence_labels": "Hand moving sound",
                "sequence_variant_key": "hand_moving_sound",
                "family": "audio_tactile",
                "soa_ms": "0",
            },
            {
                "row_label": "Peri-hand moving-sound trial",
                "respiratory_phase": "Peri-hand moving-sound trial",
                "sequence_labels": "Hand moving sound",
                "sequence_variant_key": "hand_moving_sound",
                "family": "audio_tactile",
                "soa_ms": "4000",
            },
            {
                "row_label": "Peri-hand moving-sound trial",
                "respiratory_phase": "Peri-hand moving-sound trial",
                "sequence_labels": "Hand moving sound - receding",
                "sequence_variant_key": "hand_moving_sound_receding",
                "family": "audio_tactile",
                "soa_ms": "0",
            },
            {
                "row_label": "Peri-hand moving-sound trial",
                "respiratory_phase": "Peri-hand moving-sound trial",
                "sequence_labels": "Hand moving sound - receding",
                "sequence_variant_key": "hand_moving_sound_receding",
                "family": "audio_tactile",
                "soa_ms": "4000",
            },
        ],
    )
    _write_csv(
        serino_front_back_rows_path,
        [
            {
                "block_label": "Front/back trunk PPS block",
                "row_label": "Front-back trunk moving-sound trial",
                "respiratory_phase": "Front-back trunk moving-sound trial",
                "sequence_labels": "Front-back moving sound",
                "sequence_variant_key": "front_to_back",
                "family": "audio_tactile",
                "soa_ms": "143",
            },
            {
                "block_label": "Front/back trunk PPS block",
                "row_label": "Front-back trunk moving-sound trial",
                "respiratory_phase": "Front-back trunk moving-sound trial",
                "sequence_labels": "Front-back moving sound",
                "sequence_variant_key": "front_to_back",
                "family": "audio_tactile",
                "soa_ms": "2714",
            },
            {
                "block_label": "Front/back trunk PPS block",
                "row_label": "Front-back trunk moving-sound trial",
                "respiratory_phase": "Front-back trunk moving-sound trial",
                "sequence_labels": "Front-back moving sound - back to front",
                "sequence_variant_key": "back_to_front",
                "family": "audio_tactile",
                "soa_ms": "2714",
            },
            {
                "block_label": "Front/back trunk PPS block",
                "row_label": "Front-back trunk moving-sound trial",
                "respiratory_phase": "Front-back trunk moving-sound trial",
                "sequence_labels": "Front-back moving sound - back to front",
                "sequence_variant_key": "back_to_front",
                "family": "audio_tactile",
                "soa_ms": "5571",
            },
            {
                "block_label": "Front/back trunk PPS block",
                "row_label": "Front/back tactile-only baseline",
                "respiratory_phase": "Front/back tactile-only baseline",
                "sequence_labels": "Front-back moving sound",
                "sequence_variant_key": "front_to_back",
                "family": "baseline",
                "soa_ms": "2714",
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
    pfeiffer_rows: list[dict[str, str]] = []
    for block_label in (
        "Congruent vestibular rotation block",
        "Incongruent vestibular rotation block",
        "No rotation baseline block",
    ):
        for soa_ms in ("300", "2700"):
            pfeiffer_rows.append(
                {
                    "block_label": block_label,
                    "row_label": "Lateral motion PPS trial",
                    "respiratory_phase": "Lateral motion PPS trial",
                    "family": "audio_tactile",
                    "soa_ms": soa_ms,
                }
            )
    _write_csv(pfeiffer_rows_path, pfeiffer_rows)
    _write_csv(
        canzoneri_rows_path,
        [
            {
                "row_label": "Canzoneri dynamic-sound trial",
                "respiratory_phase": "Canzoneri dynamic-sound trial",
                "sequence_labels": "Pink moving sound",
                "sequence_variant_key": "pink_moving_sound",
                "family": "audio_tactile",
                "soa_ms": "300",
            },
            {
                "row_label": "Canzoneri dynamic-sound trial",
                "respiratory_phase": "Canzoneri dynamic-sound trial",
                "sequence_labels": "Pink moving sound",
                "sequence_variant_key": "pink_moving_sound",
                "family": "audio_tactile",
                "soa_ms": "2700",
            },
            {
                "row_label": "Canzoneri dynamic-sound trial",
                "respiratory_phase": "Canzoneri dynamic-sound trial",
                "sequence_labels": "Pink moving sound - receding",
                "sequence_variant_key": "pink_moving_sound_receding",
                "family": "audio_tactile",
                "soa_ms": "300",
            },
            {
                "row_label": "Canzoneri dynamic-sound trial",
                "respiratory_phase": "Canzoneri dynamic-sound trial",
                "sequence_labels": "Pink moving sound - receding",
                "sequence_variant_key": "pink_moving_sound_receding",
                "family": "audio_tactile",
                "soa_ms": "2700",
            },
            {
                "row_label": "Baseline tactile",
                "respiratory_phase": "Baseline tactile",
                "sequence_labels": "Baseline tactile | Pink moving sound",
                "sequence_variant_key": "pink_moving_sound",
                "family": "baseline",
                "soa_ms": "-700",
            },
        ],
    )
    tonelli_rows: list[dict[str, str]] = []
    for soa_ms in ("0", "500", "1000", "1500", "2000", "2500", "3000"):
        tonelli_rows.append(
            {
                "row_label": "Tonelli lateral echolocation PPS trial",
                "respiratory_phase": "Tonelli lateral echolocation PPS trial",
                "sequence_labels": "Lateral white-noise moving source",
                "sequence_variant_key": "lateral_white_noise_moving_source",
                "family": "audio_tactile",
                "soa_ms": soa_ms,
            }
        )
    for soa_ms in ("-500", "3500"):
        tonelli_rows.append(
            {
                "row_label": "Tonelli tactile-only baseline",
                "respiratory_phase": "Tonelli tactile-only baseline",
                "sequence_labels": "Lateral white-noise moving source",
                "sequence_variant_key": "lateral_white_noise_moving_source",
                "family": "baseline",
                "soa_ms": soa_ms,
            }
        )
    _write_csv(tonelli_rows_path, tonelli_rows)
    _write_csv(
        galli_rows_path,
        [
            {
                "block_label": "Wheelchair PPS block",
                "row_label": "Wheelchair PPS moving-sound trial",
                "respiratory_phase": "Wheelchair PPS moving-sound trial",
                "sequence_labels": "Wheelchair PPS broadband moving sound",
                "sequence_variant_key": "wheelchair_pps_broadband_moving_sound",
                "family": "audio_tactile",
                "soa_ms": "380",
            },
            {
                "block_label": "Wheelchair PPS block",
                "row_label": "Wheelchair PPS moving-sound trial",
                "respiratory_phase": "Wheelchair PPS moving-sound trial",
                "sequence_labels": "Wheelchair PPS broadband moving sound - back looming",
                "sequence_variant_key": "wheelchair_pps_broadband_moving_sound_back_looming",
                "family": "audio_tactile",
                "soa_ms": "2280",
            },
            {
                "block_label": "Wheelchair PPS block",
                "row_label": "Wheelchair PPS tactile-only baseline",
                "respiratory_phase": "Wheelchair PPS tactile-only baseline",
                "sequence_labels": "Wheelchair PPS broadband moving sound - back looming",
                "sequence_variant_key": "wheelchair_pps_broadband_moving_sound_back_looming",
                "family": "baseline",
                "soa_ms": "380",
            },
        ],
    )
    lerner_rows: list[dict[str, str]] = []
    for direction in range(1, 13):
        for source_label in ("Dynamic pink 3D sound", "Flat pink 3D sound"):
            for soa_ms in ("0", "5500"):
                variant_base = source_label.lower().replace(" ", "_")
                lerner_rows.append(
                    {
                        "block_label": "3D boundary block",
                        "row_label": "3D boundary source trial",
                        "respiratory_phase": "3D boundary source trial",
                        "sequence_labels": f"{source_label} - direction {direction:02d}",
                        "sequence_variant_key": f"{variant_base}_direction_{direction:02d}",
                        "family": "audio_tactile",
                        "soa_ms": soa_ms,
                    }
                )
    _write_csv(lerner_rows_path, lerner_rows)
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
                        "outputs": {"analysis_ready_trials": str(noel_rows_path)},
                    },
                    {
                        "template_id": "noel_2015_bodily_self_back_space",
                        "outputs": {"analysis_ready_trials": str(noel_rows_path)},
                    },
                    {
                        "template_id": "serino_2015_peri_trunk_exp1",
                        "outputs": {"analysis_ready_trials": str(serino_rows_path)},
                    },
                    {
                        "template_id": "serino_2015_peri_hand_exp3",
                        "outputs": {"analysis_ready_trials": str(serino_hand_rows_path)},
                    },
                    {
                        "template_id": "serino_2015_front_back_trunk_exp2",
                        "outputs": {"analysis_ready_trials": str(serino_front_back_rows_path)},
                    },
                    {
                        "template_id": "matsuda_2021_four_directions",
                        "outputs": {"analysis_ready_trials": str(matsuda_rows_path)},
                    },
                    {
                        "template_id": "barumerli_2026_arm_movement_exp1",
                        "outputs": {"analysis_ready_trials": str(lamia_rows_path)},
                    },
                    {
                        "template_id": "pfeiffer_2018_lateral_perihead_left_to_right",
                        "outputs": {"analysis_ready_trials": str(pfeiffer_rows_path)},
                    },
                    {
                        "template_id": "canzoneri_2012_dynamic_sounds",
                        "outputs": {"analysis_ready_trials": str(canzoneri_rows_path)},
                    },
                    {
                        "template_id": "tonelli_2019_echolocation",
                        "outputs": {"analysis_ready_trials": str(tonelli_rows_path)},
                    },
                    {
                        "template_id": "galli_2015_wheelchair_full_body",
                        "outputs": {"analysis_ready_trials": str(galli_rows_path)},
                    },
                    {
                        "template_id": "lerner_2021_3d_audio_tactile_boundary",
                        "outputs": {"analysis_ready_trials": str(lerner_rows_path)},
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
                        "current_template_ids": [
                            "noel_2015_bodily_self",
                            "noel_2015_bodily_self_back_space",
                        ],
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
                        "record_id": "serino_2015_peri_hand_exp3",
                        "citation_short": "Serino 2015 Exp. 3",
                        "observed_comparison_gap": audit.READY_GAP,
                        "current_template_ids": ["serino_2015_peri_hand_exp3"],
                        "expected_outcome": {
                            "expected_effect_direction": "near_hand_sounds_speed_hand_tactile_rt"
                        },
                    },
                    {
                        "record_id": "serino_2015_front_back_trunk_exp2",
                        "citation_short": "Serino 2015 Exp. 2",
                        "observed_comparison_gap": audit.READY_GAP,
                        "current_template_ids": ["serino_2015_front_back_trunk_exp2"],
                        "expected_outcome": {
                            "expected_effect_direction": (
                                "near_trunk_front_back_sounds_speed_corresponding_tactile_rt"
                            )
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
                    {
                        "record_id": "pfeiffer_2018_vestibular",
                        "citation_short": "Pfeiffer 2018",
                        "observed_comparison_gap": audit.READY_GAP,
                        "current_template_ids": ["pfeiffer_2018_lateral_perihead_left_to_right"],
                        "expected_outcome": {
                            "expected_effect_direction": "congruent_audio_vestibular_motion_expands_pps"
                        },
                    },
                    {
                        "record_id": "canzoneri_2012_dynamic_sounds",
                        "citation_short": "Canzoneri 2012",
                        "observed_comparison_gap": audit.READY_GAP,
                        "current_template_ids": ["canzoneri_2012_dynamic_sounds"],
                        "expected_outcome": {
                            "expected_effect_direction": "approaching_near_body_sounds_speed_tactile_rt"
                        },
                    },
                    {
                        "record_id": "tonelli_2019_echolocation",
                        "citation_short": "Tonelli 2019",
                        "observed_comparison_gap": audit.READY_GAP,
                        "current_template_ids": ["tonelli_2019_echolocation"],
                        "expected_outcome": {
                            "expected_effect_direction": "echolocation_training_changes_lateral_head_pps_boundary"
                        },
                    },
                    {
                        "record_id": "galli_2015_wheelchair",
                        "citation_short": "Galli 2015",
                        "observed_comparison_gap": audit.READY_GAP,
                        "current_template_ids": ["galli_2015_wheelchair_full_body"],
                        "expected_outcome": {
                            "expected_effect_direction": (
                                "visible_passive_wheelchair_exploration_extends_full_body_pps"
                            )
                        },
                    },
                    {
                        "record_id": "lerner_2021_3d_boundary",
                        "citation_short": "Lerner 2021",
                        "observed_comparison_gap": audit.READY_GAP,
                        "current_template_ids": ["lerner_2021_3d_audio_tactile_boundary"],
                        "expected_outcome": {
                            "expected_effect_direction": (
                                "individual_3d_pps_maps_without_systematic_dynamic_flat_advantage"
                            )
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
        "ready_profile_record_count": 12,
        "synthetic_comparison_record_count": 12,
        "synthetic_comparison_passed_count": 12,
        "synthetic_comparison_failed_count": 0,
        "contrast_metadata_blocked_record_count": 0,
        "contrast_metadata_present_model_missing_record_count": 0,
    }
    by_id = {row["record_id"]: row for row in report["records"]}
    smartphone = by_id["smartphone_rt_methods_2025"]
    assert smartphone["status"] == "synthetic_behavioral_comparison_passed"
    assert smartphone["synthetic_comparison"]["fixed_minus_looming_ms"] == 25.0
    assert Path(smartphone["synthetic_comparison"]["synthetic_rows_csv"]).is_file()

    noel = by_id["noel_2015_bodily_self"]
    assert noel["status"] == "synthetic_behavioral_comparison_passed"
    assert noel["missing_contrasts"] == []
    assert noel["synthetic_comparison"]["spaces_observed"] == ["back", "front"]
    assert noel["synthetic_comparison"]["synchronies_observed"] == ["asynchronous", "synchronous"]
    assert noel["synthetic_comparison"]["observed_effect_direction"] == (
        "synchronous_front_expansion_and_back_reduction"
    )

    serino = by_id["serino_2015_peri_trunk_exp1"]
    assert serino["status"] == "synthetic_behavioral_comparison_passed"
    assert serino["missing_contrasts"] == []
    assert serino["synthetic_comparison"]["far_minus_near_ms"] == 45.0
    assert serino["synthetic_comparison"]["observed_effect_direction"] == (
        "near_or_approaching_trunk_sounds_speed_tactile_rt"
    )

    serino_hand = by_id["serino_2015_peri_hand_exp3"]
    assert serino_hand["status"] == "synthetic_behavioral_comparison_passed"
    assert serino_hand["missing_contrasts"] == []
    assert serino_hand["synthetic_comparison"]["motions_observed"] == ["looming", "receding"]
    assert serino_hand["synthetic_comparison"]["looming_far_minus_near_ms"] >= 20.0
    assert serino_hand["synthetic_comparison"]["observed_effect_direction"] == (
        "near_hand_sounds_speed_hand_tactile_rt"
    )

    serino_front_back = by_id["serino_2015_front_back_trunk_exp2"]
    assert serino_front_back["status"] == "synthetic_behavioral_comparison_passed"
    assert serino_front_back["missing_contrasts"] == []
    assert serino_front_back["contrast_availability"]["front_back_space"] is True
    assert serino_front_back["contrast_availability"]["front_back_trunk_paths"] is True
    assert serino_front_back["contrast_availability"]["soa_or_distance_rank"] is True
    assert serino_front_back["contrast_availability"]["audio_tactile_vs_baseline"] is True
    assert serino_front_back["synthetic_comparison"]["paths_observed"] == ["back_to_front", "front_to_back"]
    assert serino_front_back["synthetic_comparison"]["baseline_family_present"] is True
    assert serino_front_back["synthetic_comparison"]["far_endpoint_minus_near_crossing_ms"] >= 20.0
    assert serino_front_back["synthetic_comparison"]["observed_effect_direction"] == (
        "near_trunk_front_back_sounds_speed_corresponding_tactile_rt"
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

    pfeiffer = by_id["pfeiffer_2018_vestibular"]
    assert pfeiffer["status"] == "synthetic_behavioral_comparison_passed"
    assert pfeiffer["missing_contrasts"] == []
    assert pfeiffer["synthetic_comparison"]["conditions_observed"] == [
        "congruent_rotation",
        "incongruent_rotation",
        "no_rotation",
    ]
    assert pfeiffer["synthetic_comparison"]["far_control_conditions_observed"] == {
        "incongruent_rotation_far": True,
        "no_rotation_far": True,
    }
    assert pfeiffer["synthetic_comparison"]["congruent_far_control_minus_congruent_ms"] >= 15.0
    assert pfeiffer["synthetic_comparison"]["observed_effect_direction"] == (
        "congruent_audio_vestibular_motion_expands_pps"
    )

    canzoneri = by_id["canzoneri_2012_dynamic_sounds"]
    assert canzoneri["status"] == "synthetic_behavioral_comparison_passed"
    assert canzoneri["missing_contrasts"] == []
    assert canzoneri["synthetic_comparison"]["motions_observed"] == ["approaching", "receding"]
    assert canzoneri["synthetic_comparison"]["baseline_family_present"] is True
    assert canzoneri["synthetic_comparison"]["approaching_far_minus_near_ms"] >= 20.0
    assert canzoneri["synthetic_comparison"]["observed_effect_direction"] == (
        "approaching_near_body_sounds_speed_tactile_rt"
    )

    tonelli = by_id["tonelli_2019_echolocation"]
    assert tonelli["status"] == "synthetic_behavioral_comparison_passed"
    assert tonelli["missing_contrasts"] == []
    assert tonelli["synthetic_comparison"]["distance_levels_observed"] == 7
    assert tonelli["synthetic_comparison"]["baseline_family_present"] is True
    assert tonelli["synthetic_comparison"]["near_pre_minus_post_ms"] >= 15.0
    assert tonelli["synthetic_comparison"]["middle_pre_minus_post_ms"] >= 8.0
    assert tonelli["synthetic_comparison"]["observed_effect_direction"] == (
        "echolocation_training_changes_lateral_head_pps_boundary"
    )

    galli = by_id["galli_2015_wheelchair"]
    assert galli["status"] == "synthetic_behavioral_comparison_passed"
    assert galli["missing_contrasts"] == []
    assert galli["contrast_availability"]["wheelchair_front_back_paths"] is True
    assert galli["synthetic_comparison"]["paths_observed"] == ["back", "front"]
    assert galli["synthetic_comparison"]["baseline_family_present"] is True
    assert galli["synthetic_comparison"]["visible_passive_far_control_minus_visible_ms"] >= 15.0
    assert galli["synthetic_comparison"]["observed_effect_direction"] == (
        "visible_passive_wheelchair_exploration_extends_full_body_pps"
    )

    lerner = by_id["lerner_2021_3d_boundary"]
    assert lerner["status"] == "synthetic_behavioral_comparison_passed"
    assert lerner["missing_contrasts"] == []
    assert lerner["contrast_availability"]["dynamic_flat_source_profile"] is True
    assert lerner["contrast_availability"]["twelve_direction_3d_profile"] is True
    assert lerner["synthetic_comparison"]["source_types_observed"] == ["dynamic", "flat"]
    assert lerner["synthetic_comparison"]["directions_observed"] == 12
    assert abs(lerner["synthetic_comparison"]["dynamic_minus_flat_mean_rt_ms"]) <= 5.0
    assert lerner["synthetic_comparison"]["dynamic_closer_direction_count"] == 6
    assert lerner["synthetic_comparison"]["flat_closer_direction_count"] == 6
    assert lerner["synthetic_comparison"]["observed_effect_direction"] == (
        "individual_3d_pps_maps_without_systematic_dynamic_flat_advantage"
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
