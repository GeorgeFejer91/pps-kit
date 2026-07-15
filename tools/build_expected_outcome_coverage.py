#!/usr/bin/env python
"""Build the audiotactile expected-outcome coverage ledger.

This ledger is deliberately conservative. It records which literature records
have a structured expected behavioral/scientific outcome extracted, and whether
the current toolkit has any observed evidence that can be compared with that
outcome. Software mock runs can validate schedules, WAV generation, markers, and
analysis plumbing; they do not validate human PPS effects.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
COVERAGE_PATH = REPO_ROOT / "assets" / "preloads" / "audiotactile_literature_coverage.json"
OUTPUT_PATH = REPO_ROOT / "assets" / "preloads" / "audiotactile_expected_outcome_coverage.json"
PAPER_AUDIT_CHECKLIST_PATH = (
    REPO_ROOT / "For-AI" / "audiotactile-paper-metadata-audit" / "running_checklist.csv"
)
MANUAL_REVIEW_INDEX_PATH = (
    REPO_ROOT / "For-AI" / "audiotactile-paper-metadata-audit" / "manual_review_index.csv"
)

SCHEMA = "pps-audiotactile-expected-outcome-coverage.v1"


EXPECTED_OUTCOMES: dict[str, dict[str, Any]] = {
    "noel_2015_bodily_self": {
        "outcome_family": "body-location-dependent_pps_boundary_shift",
        "primary_expected_effect": (
            "Synchronous full-body-illusion stroking shifts PPS toward the virtual body: "
            "front-space PPS expands toward the avatar and back-space PPS shrinks relative "
            "to asynchronous stroking."
        ),
        "expected_effect_direction": "synchronous_front_expansion_and_back_reduction",
        "observable_metric": "tactile RT facilitation as a function of looming-sound distance/SOA",
        "condition_contrast": "synchronous versus asynchronous visuo-tactile stroking, front versus back space",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/noel_2015_bodily_self.json",
            "Consensus MCP 2026-07-15 query: audiotactile peripersonal space auditory tactile integration boundary looming",
        ],
    },
    "serino_2015_peri_trunk_exp1": {
        "outcome_family": "distance_dependent_audio_tactile_facilitation",
        "primary_expected_effect": (
            "Task-irrelevant moving sounds closer to the trunk facilitate tactile responses "
            "more than far sounds, yielding an estimated peri-trunk PPS boundary from the "
            "RT-by-distance function."
        ),
        "expected_effect_direction": "near_or_approaching_trunk_sounds_speed_tactile_rt",
        "observable_metric": "baseline-corrected tactile RT/facilitation across D1-D6 distances",
        "condition_contrast": "near versus far trunk-centered auditory distances and looming/receding motion",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/serino_2015_peri_trunk_exp1.json",
            "assets/preloads/audiotactile_holmes2020_consensus_screening.json",
        ],
    },
    "pfeiffer_2018_vestibular": {
        "outcome_family": "vestibular_modulation_of_perihead_pps",
        "primary_expected_effect": (
            "Vestibular stimulation speeds tactile detection, and congruent audio-vestibular "
            "motion expands peri-head PPS farther from the body relative to no rotation or "
            "incongruent motion."
        ),
        "expected_effect_direction": "congruent_audio_vestibular_motion_expands_pps",
        "observable_metric": "maximal auditory distance/SOA at which tactile RT facilitation is present",
        "condition_contrast": "congruent versus incongruent vestibular/auditory motion and no-rotation baselines",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#pfeiffer_2018_vestibular",
            "Consensus MCP 2026-07-15 query: audiotactile peripersonal space auditory tactile integration boundary looming",
        ],
    },
    "matsuda_2021_four_directions": {
        "outcome_family": "directional_peritrunk_pps_for_approaching_sounds",
        "primary_expected_effect": (
            "Peri-trunk PPS representations are observed for approaching sounds in front, "
            "rear, left, and right directions; receding sounds are not expected to produce "
            "the same direction-general PPS facilitation pattern."
        ),
        "expected_effect_direction": "approaching_sounds_show_pps_facilitation_across_four_directions",
        "observable_metric": "tactile RT/facilitation by T1-T5 SOA and body-relative direction",
        "condition_contrast": "approaching versus receding sounds across front/rear/left/right blocks",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/matsuda_2021_four_directions.json",
            "Consensus MCP 2026-07-15 query: audio tactile peripersonal space looming sound tactile reaction time",
        ],
    },
    "lamia_2026_arm_movement": {
        "outcome_family": "arm_movement_reduction_of_audio_tactile_facilitation",
        "primary_expected_effect": (
            "Looming sounds enhance tactile reactivity near the hand and trunk when still, "
            "but arm movement execution reduces or eliminates the distance-dependent "
            "audio-tactile facilitation irrespective of the stimulated body part."
        ),
        "expected_effect_direction": "movement_blunts_looming_distance_facilitation",
        "observable_metric": "baseline-corrected tactile RT/facilitation across tactile delays and movement state",
        "condition_contrast": "motor versus static blocks, hand versus trunk tactile site, looming versus receding sounds",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/lamia_2026_arm_movement.json",
            "Consensus MCP 2026-07-15 query: audio tactile peripersonal space looming sound tactile reaction time",
        ],
    },
    "smartphone_rt_methods_2025": {
        "outcome_family": "mobile_looming_versus_static_tactile_rt_facilitation",
        "primary_expected_effect": (
            "On validated Android devices, looming sounds reduce tactile RTs by about "
            "20-25 ms compared with static sounds in the smartphone PPS task."
        ),
        "expected_effect_direction": "looming_faster_than_static",
        "observable_metric": "tactile RT difference between looming and fixed/static auditory conditions",
        "condition_contrast": "looming headphone sound versus fixed/static comparator sound",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#smartphone_rt_methods_2025",
            "Consensus MCP 2026-07-15 query: audio tactile peripersonal space looming sound tactile reaction time",
        ],
    },
    "jazz_duet_2021": {
        "outcome_family": "musical_joint_action_modulation_of_hand_pps",
        "primary_expected_effect": (
            "After an uncooperative jazz duet, tactile-auditory near-space "
            "reaction times are expected to increase, consistent with PPS "
            "suppression or withdrawal from the uncooperative partner; the "
            "predicted cooperative-extension pattern was not observed in the "
            "reported abstract."
        ),
        "expected_effect_direction": "uncooperative_jazz_interaction_slows_near_audio_tactile_rt",
        "observable_metric": "hand tactile RT to bimodal audio-tactile stimuli by auditory distance after duet condition",
        "condition_contrast": "cooperative correct-harmony duet versus uncooperative incorrect-harmony duet, near-subject versus near-partner sound locations",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#jazz_duet_2021",
            "Consensus MCP 2026-07-15 query: 10.1007/s00426-020-01365-6 jazz duet peripersonal space audio tactile 2021",
        ],
    },
    "looming_duration_2025": {
        "outcome_family": "duration_comparison_lateral_looming_audio_tactile_pps",
        "primary_expected_effect": (
            "Both the 2 s and 3 s right-lateral looming pink-noise tasks are "
            "expected to show audio-tactile RT facilitation compared with tactile-only "
            "baseline at late/near temporal delays. The 2 s task places the PPS "
            "boundary between T3 and T4 (875-1125 ms), while the 3 s task places it "
            "between T2 and T3 (937.5-1312.5 ms); the similar timing does not imply "
            "the same physical distance because the two durations use different "
            "starting distances."
        ),
        "expected_effect_direction": "both_2s_and_3s_looming_sounds_facilitate_late_tactile_rt_with_duration_specific_boundaries",
        "observable_metric": "baseline versus audio-tactile tactile RT by temporal delay plus sigmoid xc/k parameters",
        "condition_contrast": "2 s versus 3 s lateral looming pink-noise duration, tactile-only baseline versus audio-tactile rows",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#looming_duration_2025",
            "Publisher PDF live result/figure review 2026-07-15: DOI 10.61782/fa.2025.0866, Fig. 1-2 and Results/Discussion pp. 3552-3554",
            "Consensus MCP 2026-07-15 query: 10.61782/fa.2025.0866 looming sound duration peripersonal space measurement",
        ],
    },
    "novel_two_phase_audio_tactile_2025": {
        "outcome_family": "proposed_self_nonself_association_modulation_of_pps",
        "primary_expected_effect": (
            "The conference abstract proposes a two-phase sound-label association "
            "and PPS measurement paradigm. Its structured expected outcome is "
            "conditional: if PPS depends only on bodily self-modulation, no "
            "self versus non-self difference is expected; if abstract cognitive "
            "self-associations modulate PPS, non-self-associated sounds are "
            "expected to elicit a wider and more rigid PPS than self-associated "
            "sounds."
        ),
        "expected_effect_direction": "conditional_nonself_associated_sounds_widen_and_rigidify_pps_if_cognitive_self_associations_modulate_pps",
        "observable_metric": "tactile RT as a function of auditory proximity, converted to PPS size and strength estimates",
        "condition_contrast": "self-labeled versus non-self-labeled neutral auditory stimuli in a two-phase association/PPS measurement design",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#novel_two_phase_audio_tactile_2025",
            "IRIS/Sapienza handle 11573/1757869 live abstract review 2026-07-15",
            "SISSA Indico AIP Sperimentale 2025 contribution 3965 live abstract review 2026-07-15",
        ],
    },
    "biggio_2017_racket_tool_use": {
        "outcome_family": "tool_condition_modulation_of_static_audio_tactile_pps",
        "primary_expected_effect": (
            "Racket-related conditions are expected to modulate the static near/far "
            "audio-tactile interaction around the stimulated wrist, shifting the "
            "near-versus-far tactile-response benefit relative to the no-racket condition."
        ),
        "expected_effect_direction": "racket_context_changes_near_far_audio_tactile_facilitation",
        "observable_metric": "tactile response performance by near/far sound position and racket condition",
        "condition_contrast": "no-racket versus common-racket versus personal-racket blocked sessions",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/biggio_2017_racket_tool_use.json",
            "For-AI/audiotactile-paper-metadata-audit/manual_review_index.csv#biggio_2017_racket_tool_use",
        ],
    },
    "canzoneri_2012_dynamic_sounds": {
        "outcome_family": "dynamic_looming_audio_tactile_pps_boundary",
        "primary_expected_effect": (
            "Dynamic approaching sounds are expected to facilitate tactile responses "
            "as they enter near body space, producing a distance/SOA-dependent PPS "
            "function that is weaker or differently shaped for receding sounds."
        ),
        "expected_effect_direction": "approaching_near_body_sounds_speed_tactile_rt",
        "observable_metric": "tactile RT/facilitation curve and sigmoid-derived boundary by T1-T5 timing",
        "condition_contrast": "approaching/IN versus receding/OUT pink-noise trajectories plus tactile-only baselines",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/canzoneri_2012_dynamic_sounds.json",
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#canzoneri_2012_dynamic_sounds",
        ],
    },
    "cell_reports_medicine_2026_consciousness": {
        "outcome_family": "passive_near_far_audio_tactile_eeg_consciousness_index",
        "primary_expected_effect": (
            "Static near/far audio-tactile stimulation is expected to produce EEG "
            "multisensory-integration signatures that vary with conscious state, "
            "with near-space audio-tactile responses serving as the PPS-sensitive endpoint."
        ),
        "expected_effect_direction": "near_far_audio_tactile_eeg_integration_tracks_conscious_state",
        "observable_metric": "EEG multisensory response or classifier feature for ATNear/ATFar versus unisensory rows",
        "condition_contrast": "healthy wake/sleep or DoC state groups crossed with near/far audio-tactile conditions",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/cell_reports_medicine_2026_consciousness.json",
            "For-AI/audiotactile-paper-metadata-audit/manual_review_index.csv#cell_reports_medicine_2026_consciousness",
        ],
    },
    "disorders_consciousness_2019": {
        "outcome_family": "passive_near_far_audio_tactile_eeg_doc_encoding",
        "primary_expected_effect": (
            "Passive arm-centered near/far audio-tactile stimulation is expected to "
            "show multisensory EEG encoding of PPS that is preserved or graded by "
            "disorder-of-consciousness status rather than appearing as a behavioral RT effect."
        ),
        "expected_effect_direction": "near_far_audio_tactile_eeg_encoding_differs_by_consciousness_state",
        "observable_metric": "EEG response to ATNear/ATFar relative to tactile-only and auditory-only controls",
        "condition_contrast": "DoC/patient status and healthy controls crossed with tactile, auditory-near/far, and AT-near/far rows",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/disorders_consciousness_2019.json",
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#disorders_consciousness_2019",
        ],
    },
    "farne_ladavas_2002_auditory_pps_humans": {
        "outcome_family": "static_perihead_audio_tactile_extinction_modulation",
        "primary_expected_effect": (
            "Static sounds close to the body are expected to modulate tactile "
            "extinction/detection more strongly than far sounds, establishing a "
            "near-space auditory-tactile interaction without a looming trajectory."
        ),
        "expected_effect_direction": "near_sounds_modulate_tactile_extinction_more_than_far_sounds",
        "observable_metric": "tactile report/extinction rate by speaker distance and front/back position",
        "condition_contrast": "near versus far and front/back static auditory positions with tactile-only/no-stimulation rows",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/farne_ladavas_2002_auditory_pps_humans.json",
            "For-AI/audiotactile-paper-metadata-audit/manual_review_index.csv#farne_ladavas_2002_auditory_pps_humans",
        ],
    },
    "ladavas_2001_auditory_tactile_extinction": {
        "outcome_family": "single_case_perihead_audio_tactile_extinction",
        "primary_expected_effect": (
            "In a right-brain-damaged patient with tactile extinction, a complex "
            "sound close to the ipsilesional side of the head is expected to "
            "extinguish contralesional head touch more than a far sound; pure "
            "tones are not expected to produce the same spatially specific "
            "near-head extinction pattern."
        ),
        "expected_effect_direction": "near_ipsilesional_complex_sounds_increase_contralesional_head_tactile_extinction",
        "observable_metric": "contralesional tactile extinction/report rate by auditory distance and sound complexity",
        "condition_contrast": "near versus far ipsilesional head sounds and white-noise/complex sounds versus pure tones",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#ladavas_2001_auditory_tactile_extinction",
            "Consensus MCP 2026-07-15 query: 10.1093/neucas/7.2.97 auditory tactile extinction peripersonal space Ladavas 2001",
        ],
    },
    "kitagawa_2005_sound_complexity": {
        "outcome_family": "rear_perihead_complex_sound_audio_tactile_interference",
        "primary_expected_effect": (
            "Complex rear-space sounds are expected to modulate audio-tactile "
            "spatial processing more strongly when close to the back of the "
            "head than when far away; pure tones are expected to show weaker "
            "or no distance-dependent modulation."
        ),
        "expected_effect_direction": "near_rear_complex_sounds_increase_audio_tactile_interference",
        "observable_metric": "tactile side-discrimination latency/error and TOJ accuracy by auditory side, distance, and sound type",
        "condition_contrast": "white-noise versus pure-tone auditory distractors, close versus far behind-head positions, same versus opposite side",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#kitagawa_2005_sound_complexity",
            "Consensus MCP 2026-07-15 query: 10.1007/s00221-005-2393-8 Kitagawa sound complexity peripersonal space audio tactile",
        ],
    },
    "serino_2009_tms": {
        "outcome_family": "time_dependent_motor_coding_of_hand_centered_pps",
        "primary_expected_effect": (
            "Near-hand sounds are expected to enhance hand MEPs at short "
            "sound-to-TMS intervals, while longer intervals reverse the pattern "
            "toward greater far-sound excitability; the effect is hand-centered "
            "rather than body-centered."
        ),
        "expected_effect_direction": "early_near_hand_mep_facilitation_late_far_sound_reversal",
        "observable_metric": "TMS-evoked MEP amplitude by near/far sound position and sound-to-TMS interval",
        "condition_contrast": "near versus far sounds at early and late TMS delays in a hand-centered frame",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#serino_2009_tms",
            "Consensus MCP 2026-07-15 query: 10.1371/journal.pone.0006582 Serino 2009 TMS peripersonal space audio tactile",
        ],
    },
    "bassolino_2010_mouse_use": {
        "outcome_family": "mouse_use_extension_of_hand_audio_pps",
        "primary_expected_effect": (
            "When habitual users neither hold nor use a mouse, near-hand sounds "
            "are expected to speed tactile responses more than sounds near the "
            "screen; actively using or passively holding the mouse is expected "
            "to eliminate that near-versus-screen difference for the mouse hand, "
            "indicating PPS extension toward screen space."
        ),
        "expected_effect_direction": "mouse_holding_or_use_extends_right_hand_audio_pps_to_screen_space",
        "observable_metric": "hand tactile RT by sound location, mouse state, and stimulated hand",
        "condition_contrast": "no-mouse, passive holding, and active mouse-use conditions for right versus left hand",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#bassolino_2010_mouse_use",
            "Consensus MCP 2026-07-15 query: 10.1371/journal.pone.0006582 Serino 2009 TMS peripersonal space audio tactile",
        ],
    },
    "avenanti_2012_motor_cortex": {
        "outcome_family": "premotor_dependency_of_motor_pps_coding",
        "primary_expected_effect": (
            "Near-hand sounds are expected to produce a spatially dependent "
            "motor response in hand MEPs after sham or V1 stimulation, while "
            "cathodal suppression of premotor cortex is expected to abolish the "
            "near-far motor coding effect."
        ),
        "expected_effect_direction": "pmc_suppression_abolishes_near_hand_motor_coding",
        "observable_metric": "TMS-evoked MEP amplitude by sound distance and tDCS target",
        "condition_contrast": "sham, V1, posterior parietal, and premotor tDCS crossed with near/far hand-centered sounds",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#avenanti_2012_motor_cortex",
            "Consensus MCP 2026-07-15 query: 10.1016/j.neuroimage.2012.06.063 Avenanti motor cortex peripersonal space audio tactile",
        ],
    },
    "cimmino_2013_surgical_arm_elongation": {
        "outcome_family": "body_size_change_updates_body_and_pps_representation",
        "primary_expected_effect": (
            "Surgical arm elongation is expected to change body-size measures "
            "and the audio-tactile PPS task outcome, bringing the patient's "
            "body and space representations closer to healthy-control patterns."
        ),
        "expected_effect_direction": "arm_elongation_updates_body_and_audio_tactile_pps_representation",
        "observable_metric": "audio-tactile PPS task measure plus tactile distance/body-image measures before versus after surgery",
        "condition_contrast": "pre- versus post-arm elongation single-case measures and healthy-control comparison",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#cimmino_2013_surgical_arm_elongation",
            "Consensus MCP 2026-07-15 query: Cimmino 2013 surgical arm elongation peripersonal space body image social cognition 2024 audio tactile",
        ],
    },
    "teramoto_2013_visual_deprivation": {
        "outcome_family": "visual_deprivation_changes_audio_tactile_reference_frames",
        "primary_expected_effect": (
            "Visual deprivation is expected to alter the spatial coordinate "
            "systems supporting auditory-tactile processing: blind participants "
            "are expected to show reduced spatial multisensory binding in tasks "
            "requiring explicit cross-modal combination but stronger ability to "
            "handle distractor/attention demands in unimodal-target tasks."
        ),
        "expected_effect_direction": "visual_deprivation_reduces_spatial_multisensory_binding_and_alters_reference_frames",
        "observable_metric": "audio-tactile integration/interference or attention performance by visual-history group and posture/reference frame",
        "condition_contrast": "early blind, late blind, and sighted groups across auditory, tactile, and audio-tactile processing tasks",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#teramoto_2013_visual_deprivation",
            "Consensus MCP 2026-07-15 query: 10.1037/a0028416 Teramoto visual deprivation audiotactile peripersonal space",
        ],
    },
    "teramoto_2013_beyond_head_audiotactile": {
        "outcome_family": "audio_tactile_interference_beyond_perihead_space",
        "primary_expected_effect": (
            "Opposite-side sounds are expected to impair tactile spatial "
            "discrimination for multiple body parts, and sounds near the head "
            "are expected to exert stronger influence than far-head sounds; hand "
            "surface and hand position further modulate the interference."
        ),
        "expected_effect_direction": "opposite_side_and_near_head_sounds_increase_tactile_spatial_interference_across_body_parts",
        "observable_metric": "tactile side-discrimination latency/error by auditory congruency, body part, hand surface, and sound distance",
        "condition_contrast": "same versus opposite auditory side, cheek/hand/knee tactile sites, near versus far head sound positions",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#teramoto_2013_beyond_head_audiotactile",
            "Consensus MCP 2026-07-15 query: 10.1007/s00221-013-3574-5 Teramoto beyond head audiotactile interaction peripersonal space",
        ],
    },
    "taffou_2014_cynophobic_rear_looming": {
        "outcome_family": "fear_relevant_sound_expansion_of_rear_defensive_pps",
        "primary_expected_effect": (
            "Dog-fearful participants are expected to show a larger rear-space "
            "PPS boundary when looming dog growls are present than non-fearful "
            "participants, while non-threatening animal sounds should not "
            "produce the same fear-specific expansion."
        ),
        "expected_effect_direction": "dog_fear_extends_rear_pps_for_threatening_dog_sounds",
        "observable_metric": "PPS boundary or tactile RT facilitation by rear-looming sound distance and animal sound category",
        "condition_contrast": "dog-fearful versus non-fearful groups, dog growl versus sheep bleat rear-looming sounds",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#taffou_2014_cynophobic_rear_looming",
            "Consensus MCP 2026-07-15 query: Teramoto visual deprivation beyond head audiotactile Hobeika anisotropy cynophobic rear looming peripersonal space",
        ],
    },
    "ferri_2015_jneurosci_itv": {
        "outcome_family": "premotor_response_variability_predicts_individual_pps_boundary",
        "primary_expected_effect": (
            "Individual PPS boundary differences are expected to be predicted by "
            "intertrial variability of premotor BOLD responses to far dynamic "
            "approaching stimuli, rather than by trial-averaged response "
            "amplitude."
        ),
        "expected_effect_direction": "premotor_far_stimulus_itv_predicts_individual_pps_extension",
        "observable_metric": "behavioral PPS boundary estimate and premotor BOLD intertrial variability for far versus near dynamic stimuli",
        "condition_contrast": "far versus near approaching auditory stimuli and individual PPS boundary locations",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#ferri_2015_jneurosci_itv",
            "Consensus MCP 2026-07-15 query: 10.1523/jneurosci.1696-15.2015 Ferri heartbeat intertrial variability peripersonal space audio tactile",
        ],
    },
    "maister_2015_shared_sensory": {
        "outcome_family": "shared_sensory_experience_remaps_other_pps",
        "primary_expected_effect": (
            "After an enfacement-style shared sensory experience, audio-tactile "
            "integration is expected to increase in the space close to the "
            "confederate's body without extending continuously across the space "
            "between participant and confederate."
        ),
        "expected_effect_direction": "shared_sensory_experience_remaps_confederate_pps_without_self_space_expansion",
        "observable_metric": "audio-tactile integration/facilitation by distance from participant and confederate before versus after shared sensory experience",
        "condition_contrast": "pre/post shared sensory experience and self-near, between-person, and confederate-near space",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#maister_2015_shared_sensory",
            "Consensus MCP 2026-07-15 query: social perception shapes multisensory peripersonal space 2017 body image social cognition 2024 depersonalisation audio tactile",
        ],
    },
    "serino_2015_toolless_sync_training": {
        "outcome_family": "synchronous_audio_tactile_training_extends_pps_without_tool",
        "primary_expected_effect": (
            "Synchronous pairing of tactile stimulation at the hand with far "
            "auditory stimulation is expected to extend hand PPS even without "
            "tool use; the same auditory and tactile inputs presented "
            "asynchronously are not expected to produce the extension."
        ),
        "expected_effect_direction": "synchronous_far_audio_hand_tactile_pairing_extends_hand_pps_without_tool",
        "observable_metric": "audio-tactile PPS boundary or near/far tactile RT facilitation before versus after training",
        "condition_contrast": "synchronous versus asynchronous tactile-hand and far-auditory stimulation training",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#serino_2015_toolless_sync_training",
            "Consensus MCP 2026-07-15 query: 10.1371/journal.pone.0006582 Serino 2009 TMS peripersonal space audio tactile",
        ],
    },
    "social_perception_2017": {
        "outcome_family": "social_moral_evaluation_modulates_pps_boundary",
        "primary_expected_effect": (
            "PPS is expected to be more extended when participants face a person "
            "perceived as moral than when they face a person perceived as "
            "immoral; the social manipulation is not expected to affect PPS in "
            "the same way when the target is an object."
        ),
        "expected_effect_direction": "moral_social_target_extends_pps_relative_to_immoral_person",
        "observable_metric": "Social PPS task boundary estimate from multisensory interaction by social-target evaluation",
        "condition_contrast": "moral versus immoral person and person versus object target context",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#social_perception_2017",
            "Consensus MCP 2026-07-15 query: social perception shapes multisensory peripersonal space 2017 body image social cognition 2024 depersonalisation audio tactile",
        ],
    },
    "ardizzi_ferri_2018_interoceptive": {
        "outcome_family": "interoceptive_accuracy_predicts_pps_boundary_size",
        "primary_expected_effect": (
            "Higher cardiac interoceptive accuracy is expected to predict a "
            "narrower audio-tactile PPS boundary, with the relation moderated "
            "by private self-consciousness traits."
        ),
        "expected_effect_direction": "higher_interoceptive_accuracy_predicts_narrower_pps_boundary",
        "observable_metric": "audio-tactile PPS boundary estimate and heartbeat-counting interoceptive accuracy",
        "condition_contrast": "individual-difference association between PPS boundary, interoceptive accuracy, and self-consciousness traits",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#ardizzi_ferri_2018_interoceptive",
            "Consensus MCP 2026-07-15 query: social perception shapes multisensory peripersonal space 2017 body image social cognition 2024 depersonalisation audio tactile",
        ],
    },
    "hobeika_2018_anisotropy": {
        "outcome_family": "handedness_linked_lateral_pps_anisotropy",
        "primary_expected_effect": (
            "Right-handers are expected to show larger peri-trunk PPS in the "
            "left than the right hemispace, whereas left-handers are expected "
            "to show a more symmetric lateral PPS representation."
        ),
        "expected_effect_direction": "right_handers_show_left_hemispace_pps_expansion_left_handers_symmetric",
        "observable_metric": "PPS boundary/distance at which looming sound speeds tactile detection by hemispace and handedness",
        "condition_contrast": "right versus left hemispace and right-handed versus left-handed participant groups",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#hobeika_2018_anisotropy",
            "Consensus MCP 2026-07-15 query: 10.1007/s00221-017-5158-2 Hobeika anisotropy audiotactile peripersonal space",
        ],
    },
    "autism_2019": {
        "outcome_family": "autism_smaller_sharper_pps_and_reduced_body_illusion",
        "primary_expected_effect": (
            "Autistic adults are expected to show reduced susceptibility to the "
            "full-body illusion and a smaller, sharper PPS boundary than "
            "neurotypical adults in the audio-tactile reaction-time task."
        ),
        "expected_effect_direction": "autism_smaller_sharper_pps_and_reduced_full_body_illusion",
        "observable_metric": "PPS boundary size/slope plus self-location and self-identification measures",
        "condition_contrast": "autism versus neurotypical group and synchronous versus asynchronous full-body-illusion stroking",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#autism_2019",
            "Consensus MCP 2026-07-15 query: social perception shapes multisensory peripersonal space 2017 body image social cognition 2024 depersonalisation audio tactile",
        ],
    },
    "hobeika_2020_methods": {
        "outcome_family": "expectancy_corrected_log_distance_pps_method",
        "primary_expected_effect": (
            "A fixed-distance baseline is expected to separate expectancy from "
            "true audio-tactile proximity effects; after correction, the "
            "proximity effect is expected to vary linearly on a logarithmic "
            "distance scale rather than requiring a binary near/far boundary."
        ),
        "expected_effect_direction": "expectancy_corrected_audio_tactile_effect_varies_linearly_on_log_distance",
        "observable_metric": "baseline-subtracted tactile RT effect by logarithmically spaced looming-sound distance",
        "condition_contrast": "looming auditory distance samples versus fixed-distance baseline and sigmoid versus log-linear fit",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#hobeika_2020_methods",
            "Consensus MCP 2026-07-15 query: 10.1007/s00221-017-5158-2 Hobeika anisotropy audiotactile peripersonal space",
        ],
    },
    "ferroni_2020_tool_observation": {
        "outcome_family": "active_tool_use_but_not_observation_modulates_pps",
        "primary_expected_effect": (
            "Active tool use is expected to change body representation and PPS, "
            "including comparable tactile facilitation from near and far sounds "
            "after training, whereas first-person observation of tool use is "
            "not expected to significantly modulate BR or PPS."
        ),
        "expected_effect_direction": "active_tool_use_modulates_pps_but_observation_does_not",
        "observable_metric": "body-landmark localization and audio-tactile PPS boundary/facilitation before versus after training",
        "condition_contrast": "active tool-use training versus observational tool-use training",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#ferroni_2020_tool_observation",
            "Consensus MCP 2026-07-15 query: 10.1016/j.cortex.2020.11.021 ageing body space representations peripersonal space audio tactile",
        ],
    },
    "ageing_2021": {
        "outcome_family": "ageing_alters_body_representation_but_preserves_pps",
        "primary_expected_effect": (
            "Older adults are expected to show stronger distortions in implicit "
            "and explicit upper-limb body representations than young adults, "
            "while retaining comparable near-hand PPS multisensory facilitation."
        ),
        "expected_effect_direction": "ageing_alters_body_representation_but_preserves_near_hand_pps_facilitation",
        "observable_metric": "audio-tactile PPS facilitation plus body-landmark, tactile-distance, and avatar-adjustment measures",
        "condition_contrast": "healthy older versus young adults in upper-limb BR and PPS tasks",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#ageing_2021",
            "Consensus MCP 2026-07-15 query: 10.1016/j.cortex.2020.11.021 ageing body space representations peripersonal space audio tactile",
        ],
    },
    "body_image_social_cognition_2024": {
        "outcome_family": "body_image_links_to_interpersonal_distance_not_pps",
        "primary_expected_effect": (
            "Body surveillance and fear of negative evaluation are expected to "
            "relate to interpersonal-distance measures, but the audio-tactile "
            "PPS boundary is not expected to show the same body-image "
            "association pattern."
        ),
        "expected_effect_direction": "body_image_measures_link_to_interpersonal_distance_not_pps_boundary",
        "observable_metric": "PPS boundary from audio-tactile RT task and interpersonal-distance comfort boundary",
        "condition_contrast": "body image and social-evaluation individual differences predicting IPD versus PPS estimates",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#body_image_social_cognition_2024",
            "Consensus MCP 2026-07-15 query: 10.1016/j.bodyim.2024.101777 body image social cognition peripersonal space audio tactile",
        ],
    },
    "depersonalisation_2024": {
        "outcome_family": "depersonalisation_spares_pps_but_alters_time_perception",
        "primary_expected_effect": (
            "Frequent depersonalisation experiences are not expected to change "
            "audio-tactile PPS perception relative to low-DP participants, but "
            "are expected to impair egocentric mental time-travel performance."
        ),
        "expected_effect_direction": "depersonalisation_experiences_do_not_shift_pps_but_affect_time_perception",
        "observable_metric": "audio-tactile PPS boundary plus mental time-travel accuracy/performance",
        "condition_contrast": "high versus low depersonalisation-experience groups",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/depersonalisation_2024.json",
            "Consensus MCP 2026-07-15 query: social perception shapes multisensory peripersonal space 2017 body image social cognition 2024 depersonalisation audio tactile",
        ],
    },
    "interoception_exteroception_2025": {
        "outcome_family": "cardiac_interoception_competition_and_self_relevance_facilitation",
        "primary_expected_effect": (
            "Prestimulus heartbeat-evoked potentials are expected to show two "
            "independent effects: somatosensory competition associated with "
            "slower tactile/audio-tactile responses, and integrative-region "
            "facilitation of self-relevance encoding for audio-tactile stimuli "
            "inside versus outside PPS."
        ),
        "expected_effect_direction": "cardiac_interoception_competes_with_tactile_rt_and_facilitates_self_relevance_encoding",
        "observable_metric": "RT and audio-tactile evoked EEG response by HEP amplitude and self-relevance/PPS location",
        "condition_contrast": "audio source inside versus outside PPS and prestimulus HEP topography/amplitude",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#interoception_exteroception_2025",
            "Consensus MCP 2026-07-15 query: 10.1523/jneurosci.1696-15.2015 Ferri heartbeat intertrial variability peripersonal space audio tactile",
        ],
    },
    "finisguerra_2015_moving_sounds_motor": {
        "outcome_family": "moving_sound_modulation_of_hand_motor_excitability",
        "primary_expected_effect": (
            "Moving sounds within the hand-centered PPS are expected to modulate "
            "hand motor-cortex excitability, with MEP amplitude varying by sound "
            "position and motion direction rather than by tactile RT."
        ),
        "expected_effect_direction": "near_hand_moving_sounds_modulate_mep_excitability",
        "observable_metric": "TMS-evoked MEP amplitude by sampled sound position and IN/OUT direction",
        "condition_contrast": "approaching versus receding moving sounds, sampled positions, and pre/post no-noise baselines",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/finisguerra_2015_moving_sounds_motor.json",
            "For-AI/audiotactile-paper-metadata-audit/manual_review_index.csv#finisguerra_2015_moving_sounds_motor",
        ],
    },
    "ieeg_trunk_2018": {
        "outcome_family": "intracranial_trunk_pps_multisensory_neural_map",
        "primary_expected_effect": (
            "Passive trunk-centered audio-tactile trials are expected to reveal "
            "distance-sensitive multisensory neural responses in intracranial "
            "recordings, strongest for PPS-relevant front-approach timings."
        ),
        "expected_effect_direction": "near_trunk_audio_tactile_trials_show_stronger_neural_integration",
        "observable_metric": "iEEG multisensory response to AT trials relative to A-only and T-only rows by tactile timing",
        "condition_contrast": "A, T, and AT randomized trials across trunk-centered tactile timings/distances",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/ieeg_trunk_2018.json",
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#ieeg_trunk_2018",
        ],
    },
    "ronga_2021_newborn_erp": {
        "outcome_family": "newborn_near_far_audio_tactile_erp_spatial_tuning",
        "primary_expected_effect": (
            "Near hand-centered audio-tactile stimulation is expected to evoke a "
            "different ERP multisensory response than far stimulation, showing "
            "spatial tuning of audio-tactile PPS responses in newborns and adults."
        ),
        "expected_effect_direction": "near_audio_tactile_erp_response_differs_from_far",
        "observable_metric": "ERP amplitude/latency response for near/far audio-tactile versus unisensory controls",
        "condition_contrast": "near versus far speaker positions and audio-tactile versus unisensory condition rows",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/ronga_2021_newborn_erp.json",
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#ronga_2021_newborn_erp",
        ],
    },
    "serino_2007_blind_cane_users": {
        "outcome_family": "cane_use_static_near_far_pps_extension",
        "primary_expected_effect": (
            "Cane/tool-use conditions are expected to extend or reshape the "
            "near/far audio-tactile interaction, so far sounds aligned with cane "
            "use show stronger tactile-detection benefit than in baseline/handle conditions."
        ),
        "expected_effect_direction": "cane_use_extends_audio_tactile_facilitation_toward_far_space",
        "observable_metric": "tactile target detection/RT by near/far sound position and cane/handle/training condition",
        "condition_contrast": "cane versus handle/tool-use conditions, blind versus sighted groups, near versus far sounds",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/serino_2007_blind_cane_users.json",
            "For-AI/audiotactile-paper-metadata-audit/manual_review_index.csv#serino_2007_blind_cane_users",
        ],
    },
    "serino_2015_front_back_trunk_exp2": {
        "outcome_family": "front_back_trunk_audio_tactile_pps_boundary",
        "primary_expected_effect": (
            "Dynamic sounds moving through front and back trunk space are expected "
            "to facilitate tactile responses most when the sound is close to the "
            "corresponding trunk tactile anchor, yielding front/back PPS functions."
        ),
        "expected_effect_direction": "near_trunk_front_back_sounds_speed_corresponding_tactile_rt",
        "observable_metric": "tactile RT/facilitation by front/back trajectory distance and tactile site",
        "condition_contrast": "front-to-back versus back-to-front 16-speaker motion and sternum/back tactile anchors",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/serino_2015_front_back_trunk_exp2.json",
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#serino_2015_front_back_trunk_exp2",
        ],
    },
    "serino_2015_peri_hand_exp3": {
        "outcome_family": "lateralized_perihand_audio_tactile_pps_boundary",
        "primary_expected_effect": (
            "Hand-centered moving sounds are expected to facilitate tactile "
            "responses most near the stimulated hand, producing a peri-hand PPS "
            "function across the reported D1-D5 distance table."
        ),
        "expected_effect_direction": "near_hand_sounds_speed_hand_tactile_rt",
        "observable_metric": "hand tactile RT/facilitation by D1-D5 distance and looming/receding direction",
        "condition_contrast": "lateralized two-speaker moving sounds, tactile-only D1/D5 baselines, and sound-only catches",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/serino_2015_peri_hand_exp3.json",
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#serino_2015_peri_hand_exp3",
        ],
    },
    "serino_2015_exps_4_to_6": {
        "outcome_family": "body_part_centered_pps_remapping_across_hand_trunk_face",
        "primary_expected_effect": (
            "Experiments 4-6 are expected to show that audio-tactile facilitation "
            "follows the currently relevant body-part anchor and sound-location "
            "congruency, rather than a single fixed trunk-centered boundary."
        ),
        "expected_effect_direction": "audio_tactile_facilitation_tracks_body_part_anchor_and_congruency",
        "observable_metric": "tactile RT/facilitation by hand/trunk/face tactile site, distance, posture, and sound-location congruency",
        "condition_contrast": "Exp. 4 hand versus trunk, Exp. 5 hand near versus far from trunk, Exp. 6 face/trunk congruent versus incongruent locations",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/serino_2015_exps_4_to_6.json",
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#serino_2015_exps_4_to_6",
        ],
    },
    "taffou_2021_auditory_roughness": {
        "outcome_family": "affective_roughness_expansion_of_audio_tactile_pps",
        "primary_expected_effect": (
            "Rough looming sounds are expected to expand or strengthen PPS-related "
            "tactile facilitation relative to non-rough looming sounds, shifting "
            "the response benefit farther into rear-left space."
        ),
        "expected_effect_direction": "rough_sounds_expand_distance_range_of_tactile_facilitation",
        "observable_metric": "tactile RT/facilitation by Tbefore/T1-T5/Tafter timing and rough versus non-rough sound type",
        "condition_contrast": "rough versus non-rough rear-left binaural looming sounds plus silent baseline timings",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/taffou_2021_auditory_roughness.json",
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#taffou_2021_auditory_roughness",
        ],
    },
    "tajadura_jimenez_2009_visual_deprivation": {
        "outcome_family": "static_left_right_audio_tactile_spatial_congruency",
        "primary_expected_effect": (
            "Static left/right audio-tactile trials are expected to show "
            "spatial-congruency and posture-dependent multisensory facilitation, "
            "with visual-deprivation history affecting how external space is coded."
        ),
        "expected_effect_direction": "spatially_congruent_audio_tactile_trials_show_posture_dependent_facilitation",
        "observable_metric": "response speed/accuracy or redundancy-gain metric by side congruency and crossed/uncrossed posture",
        "condition_contrast": "auditory-only, tactile-only, and congruent audio-tactile rows in crossed versus uncrossed posture blocks",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/tajadura_jimenez_2009_visual_deprivation.json",
            "For-AI/audiotactile-paper-metadata-audit/manual_review_index.csv#tajadura_jimenez_2009_visual_deprivation",
        ],
    },
    "tonelli_2019_echolocation": {
        "outcome_family": "echolocation_training_modulation_of_lateral_head_pps",
        "primary_expected_effect": (
            "Echolocation training is expected to reshape lateral head/neck PPS, "
            "changing the distance-dependent tactile facilitation curve from pre "
            "to post training relative to control conditions."
        ),
        "expected_effect_direction": "echolocation_training_changes_lateral_head_pps_boundary",
        "observable_metric": "neck tactile RT/facilitation by seven speaker-defined distances before and after training",
        "condition_contrast": "pre versus post echolocation training, lateral seven-speaker looming trajectory, baselines, and catches",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/tonelli_2019_echolocation.json",
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#tonelli_2019_echolocation",
        ],
    },
    "mindfulness_pps_2024": {
        "outcome_family": "focused_attention_meditation_pps_boundary_sharpness_reduction",
        "primary_expected_effect": (
            "A 15-minute focused-attention meditation induction is expected to "
            "reduce the sharpness of the PPS boundary without producing a "
            "significant reduction in PPS extension."
        ),
        "expected_effect_direction": "fam_reduces_pps_boundary_sharpness_without_extension_reduction",
        "observable_metric": "PPS psychometric boundary sharpness/slope and extension before versus after FAM",
        "condition_contrast": "pre- versus post-focused-attention meditation audio-tactile PPS task",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/mindfulness_pps_2024.json",
            "Consensus MCP 2026-07-15 query: Mindfulness and peripersonal space boundaries 2024 audio tactile PPS",
        ],
    },
    "schizophrenia_tool_use_2022": {
        "outcome_family": "tool_use_pps_plasticity_in_schizophrenia",
        "primary_expected_effect": (
            "Schizophrenia patients are expected to show narrower baseline PPS "
            "extent and shallower boundary slope than controls, while tool-use "
            "training expands PPS in both groups and sharpens patients' boundary "
            "demarcation after training."
        ),
        "expected_effect_direction": "tool_use_expands_pps_with_scz_baseline_narrowing",
        "observable_metric": "PPS size/boundary and psychometric slope before and after tool-use training",
        "condition_contrast": "schizophrenia versus healthy controls, pre/post tool-use sessions",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#schizophrenia_tool_use_2022",
            "Consensus MCP 2026-07-15 query: Mindfulness and peripersonal space boundaries 2024 audio tactile PPS",
        ],
    },
    "social_coding_2019": {
        "outcome_family": "collaboration_selective_pps_boundary_extension",
        "primary_expected_effect": (
            "Collaborative social interaction is expected to extend PPS boundaries "
            "in the right hemispace, whereas competitive or inactive social "
            "contexts are not expected to produce the same boundary modulation."
        ),
        "expected_effect_direction": "collaboration_extends_right_hemispace_pps",
        "observable_metric": "PPS boundary estimate by social context and hemispace",
        "condition_contrast": "collaborative dyad versus competitive dyad versus inactive-person context",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#social_coding_2019",
            "Consensus MCP 2026-07-15 query: Mindfulness and peripersonal space boundaries 2024 audio tactile PPS",
        ],
    },
    "teneggi_2013_social_face": {
        "outcome_family": "social_context_modulation_of_face_pps_boundaries",
        "primary_expected_effect": (
            "Face-centered PPS boundaries are expected to shrink when another "
            "person is faced in far space compared with a mannequin, and to merge "
            "between self and other after cooperative interaction."
        ),
        "expected_effect_direction": "social_presence_shrinks_and_cooperation_merges_face_pps",
        "observable_metric": "critical auditory distance where looming/receding sounds facilitate face tactile RT",
        "condition_contrast": (
            "person versus mannequin and cooperative versus noncooperative "
            "post-game partner contexts"
        ),
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#teneggi_2013_social_face",
            "Consensus MCP 2026-07-15 query: Mindfulness and peripersonal space boundaries 2024 audio tactile PPS",
        ],
    },
    "ferri_2015_artificial_valence": {
        "outcome_family": "negative_valence_expansion_of_artificial_sound_pps",
        "primary_expected_effect": (
            "Artificial approaching sounds with negative emotional valence are "
            "expected to yield a larger PPS boundary than neutral artificial "
            "approaching sounds."
        ),
        "expected_effect_direction": "negative_artificial_sounds_expand_pps_boundary",
        "observable_metric": "PPS boundary/RT facilitation curve by artificial sound valence",
        "condition_contrast": "negative versus neutral artificial approaching sound sources",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#ferri_2015_artificial_valence",
            "Consensus MCP 2026-07-15 query: Mindfulness and peripersonal space boundaries 2024 audio tactile PPS",
        ],
    },
    "ferri_2015_ecological_valence": {
        "outcome_family": "negative_valence_expansion_of_ecological_sound_pps",
        "primary_expected_effect": (
            "Ecological approaching sounds with negative emotional content are "
            "expected to yield a larger PPS boundary than neutral or positive "
            "ecological approaching sounds."
        ),
        "expected_effect_direction": "negative_ecological_sounds_expand_pps_boundary",
        "observable_metric": "PPS boundary/RT facilitation curve by ecological sound valence",
        "condition_contrast": "negative versus neutral and positive ecological approaching sound sources",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#ferri_2015_ecological_valence",
            "Consensus MCP 2026-07-15 query: Mindfulness and peripersonal space boundaries 2024 audio tactile PPS",
        ],
    },
    "teraoka_2024_front_rear": {
        "outcome_family": "front_rear_asymmetry_in_audio_tactile_pps_facilitation",
        "primary_expected_effect": (
            "Approaching auditory probes are expected to facilitate tactile "
            "responses more strongly in rear space than in front space, while "
            "auditory distance and speed perception controls do not explain the "
            "front/rear difference."
        ),
        "expected_effect_direction": "rear_space_audio_tactile_facilitation_exceeds_front_space",
        "observable_metric": "auditory facilitation effect on vibrotactile detection by front/rear direction",
        "condition_contrast": "front versus rear approaching auditory probe with tactile-only baseline controls",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#teraoka_2024_front_rear",
            "Consensus MCP 2026-07-15 query: Mindfulness and peripersonal space boundaries 2024 audio tactile PPS",
        ],
    },
    "canzoneri_2013_tool_use_reshaping": {
        "outcome_family": "tool_use_extension_of_hand_pps_and_body_representation",
        "primary_expected_effect": (
            "Brief use of a long tool is expected to extend hand-centered PPS "
            "along the tool axis and concurrently reshape body representation, "
            "whereas a pointing control task is not expected to do so."
        ),
        "expected_effect_direction": "tool_use_extends_pps_along_tool_axis_and_elongates_body_representation",
        "observable_metric": "PPS boundary and tactile-distance/body-landmark body-representation metrics before and after tool use",
        "condition_contrast": "tool-use training versus pointing control and pre/post audio-tactile PPS task",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#canzoneri_2013_tool_use_reshaping",
            "Consensus MCP 2026-07-15 query: Canzoneri 2013 amputation prosthesis peripersonal space audio tactile",
        ],
    },
    "canzoneri_2013_amputation_prosthesis": {
        "outcome_family": "prosthesis_dependent_remapping_of_amputated_limb_pps",
        "primary_expected_effect": (
            "For the amputated limb, PPS boundaries are expected to shift toward "
            "the stump without the prosthesis and to extend to include the "
            "prosthetic hand when the prosthesis is worn."
        ),
        "expected_effect_direction": "prosthesis_extends_amputated_side_pps_after_stump_shift_without_prosthesis",
        "observable_metric": "audio-tactile PPS boundary and tactile-distance body-representation metrics by limb/prosthesis state",
        "condition_contrast": "amputated limb with versus without prosthesis, healthy limb, and healthy controls",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#canzoneri_2013_amputation_prosthesis",
            "Consensus MCP 2026-07-15 query: Canzoneri 2013 amputation prosthesis peripersonal space audio tactile",
        ],
    },
    "serino_2011_rtms": {
        "outcome_family": "frontoparietal_causal_role_in_hand_pps_facilitation",
        "primary_expected_effect": (
            "Near sounds are expected to speed tactile responses around the hand "
            "without rTMS; virtual lesions to ventral premotor or posterior "
            "parietal cortex are expected to eliminate that near-sound benefit."
        ),
        "expected_effect_direction": "vpmc_or_ppc_rtms_removes_near_sound_tactile_facilitation",
        "observable_metric": "tactile RT near-sound benefit under rTMS target site",
        "condition_contrast": "no-rTMS/V1 control versus vPMc and PPc rTMS, near versus far sound",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#serino_2011_rtms",
            "Consensus MCP 2026-07-15 query: Canzoneri 2013 amputation prosthesis peripersonal space audio tactile",
        ],
    },
    "serino_2011_professional_fencers": {
        "outcome_family": "expert_weapon_use_extension_of_hand_pps",
        "primary_expected_effect": (
            "Professional fencers are expected to show hand PPS extension while "
            "holding their weapon, so far auditory stimuli interact with tactile "
            "stimulation at the hand, unlike the short-handle condition."
        ),
        "expected_effect_direction": "weapon_holding_shifts_hand_pps_to_weapon_tip",
        "observable_metric": "audio-tactile facilitation by sound distance while holding weapon versus handle",
        "condition_contrast": "professional fencers holding weapon versus short handle, with weapon-type variation",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#serino_2011_professional_fencers",
            "Consensus MCP 2026-07-15 query: Canzoneri 2013 amputation prosthesis peripersonal space audio tactile",
        ],
    },
    "galli_2015_wheelchair": {
        "outcome_family": "wheelchair_mediated_full_body_pps_extension",
        "primary_expected_effect": (
            "Wheelchair-mediated passive exploration with vision is expected to "
            "extend full-body PPS, whereas active nonexpert training and "
            "blindfolded passive exploration are not expected to produce the same "
            "extension."
        ),
        "expected_effect_direction": "visible_passive_wheelchair_exploration_extends_full_body_pps",
        "observable_metric": "full-body PPS boundary before and after wheelchair training condition",
        "condition_contrast": "active wheelchair training, passive wheelchair training with vision, and blindfolded passive training",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#galli_2015_wheelchair",
            "Consensus MCP 2026-07-15 query: Canzoneri 2013 amputation prosthesis peripersonal space audio tactile",
        ],
    },
    "serino_2018_mixed_reality_pps": {
        "outcome_family": "mixed_reality_audio_visual_tactile_pps_boundary_capture",
        "primary_expected_effect": (
            "Mixed-reality looming stimuli are expected to enhance tactile "
            "detection when close to the body and to support individual PPS "
            "boundary estimation, with audio-visual looming producing stronger "
            "sigmoidal boundary fits than visual-only looming."
        ),
        "expected_effect_direction": "close_mixed_reality_audio_visual_stimuli_enhance_tactile_detection",
        "observable_metric": "tactile RT facilitation and sigmoidal PPS boundary fit by virtual stimulus distance",
        "condition_contrast": "visual-only versus audio-visual looming stimuli across near/far virtual distances",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#serino_2018_mixed_reality_pps",
            "Consensus MCP 2026-07-15 query: Canzoneri 2013 amputation prosthesis peripersonal space audio tactile",
        ],
    },
    "noel_2018_neural_adaptation": {
        "outcome_family": "velocity_dependent_dynamic_resizing_of_pps",
        "primary_expected_effect": (
            "Peri-trunk PPS is expected to be larger than peri-face PPS, and both "
            "representations are expected to enlarge as the velocity of incoming "
            "approaching auditory stimuli increases."
        ),
        "expected_effect_direction": "faster_approaching_sounds_expand_face_and_trunk_pps",
        "observable_metric": "peri-face/peri-trunk PPS size by incoming auditory-stimulus velocity",
        "condition_contrast": "body part and approaching-sound velocity conditions in the psychophysical-computational task",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#noel_2018_neural_adaptation",
            "Consensus MCP 2026-07-15 query: Noel 2018 neural adaptation peripersonal space audio tactile",
        ],
    },
    "noel_2015_walking": {
        "outcome_family": "walking_induced_expansion_of_full_body_pps",
        "primary_expected_effect": (
            "Walking is expected to expand chest-centered PPS so that tactile "
            "processing is facilitated by sounds at farther distances than while "
            "standing still, with the expansion driven by kinematic/proprioceptive "
            "cues rather than optic flow."
        ),
        "expected_effect_direction": "walking_expands_chest_pps_to_farther_looming_sound_distances",
        "observable_metric": "audio-tactile PPS boundary while standing versus walking",
        "condition_contrast": "standing still versus treadmill walking with and without congruent optic flow",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#noel_2015_walking",
            "Consensus MCP 2026-07-15 query: Noel 2018 neural adaptation peripersonal space audio tactile",
        ],
    },
    "spadone_2021_connectivity": {
        "outcome_family": "frontoparietal_connectivity_correlates_of_pps_extension",
        "primary_expected_effect": (
            "Premotor connectivity with dorsal-attention and frontoparietal nodes "
            "is expected to be stronger during near-space processing, and "
            "individual PPS extension is expected to relate to premotor-parietal "
            "connectivity and dynamic connectivity variability."
        ),
        "expected_effect_direction": "near_space_processing_strengthens_premotor_frontoparietal_connectivity",
        "observable_metric": "fMRI functional connectivity and across-trial variability by near/far audio-tactile PPS condition",
        "condition_contrast": "near versus far audio-tactile trials and individual PPS boundary estimates",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#spadone_2021_connectivity",
            "Consensus MCP 2026-07-15 query: Noel 2018 neural adaptation peripersonal space audio tactile",
        ],
    },
    "seeming_confines_2021": {
        "outcome_family": "tool_use_reduces_near_far_rt_erp_difference",
        "primary_expected_effect": (
            "Before tool use, bimodal-near trials are expected to show faster RTs "
            "and greater ERP super-additivity than bimodal-far trials; after "
            "tool-use training, this near-far differential is expected to be "
            "reduced, indicating PPS extension."
        ),
        "expected_effect_direction": "tool_use_reduces_far_near_differential_by_extending_pps",
        "observable_metric": "RT facilitation and ERP super-additivity for near versus far bimodal trials",
        "condition_contrast": "tool-use training versus far-space visual-discrimination control training",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#seeming_confines_2021",
            "Consensus MCP 2026-07-15 query: Noel 2018 neural adaptation peripersonal space audio tactile",
        ],
    },
    "holmes_2020_four_experiments": {
        "outcome_family": "mixed_support_for_near_sound_tactile_rt_benefit",
        "primary_expected_effect": (
            "Across four experiments, the expected outcome is weak or mixed "
            "support: no robust distance-dependent enhancement in error rates or "
            "task performance, but a small general RT speeding for near sounds "
            "and a meta-analytic near-versus-far benefit."
        ),
        "expected_effect_direction": "small_near_sound_rt_benefit_without_robust_distance_gradient",
        "observable_metric": "tactile RT/error performance for near versus far sounds plus meta-analytic RT benefit",
        "condition_contrast": "near versus far sound conditions across four experiments and meta-analysis filters",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#holmes_2020_four_experiments",
            "Consensus MCP 2026-07-15 query: Noel 2018 neural adaptation peripersonal space audio tactile",
        ],
    },
    "lerner_2021_3d_boundary": {
        "outcome_family": "vr_3d_audio_tactile_pps_boundary_mapping",
        "primary_expected_effect": (
            "The VR audio-tactile setup is expected to infer individualized 3D "
            "PPS boundary polyhedra from tactile RT thresholds across twelve "
            "virtual sound directions, without a systematic dynamic-versus-flat "
            "sound advantage in the reported pilot sample."
        ),
        "expected_effect_direction": "individual_3d_pps_maps_without_systematic_dynamic_flat_advantage",
        "observable_metric": "sigmoid-derived RT threshold/boundary distance by direction and flat/dynamic source condition",
        "condition_contrast": "dynamic looming versus flat stationary pink-noise sources across twelve virtual directions and six arm-length-scaled tactile timepoints",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#lerner_2021_3d_boundary",
            "Frontiers article live review 2026-07-15: DOI 10.3389/frvir.2021.644214, Materials and Methods/Results/Table 2",
            "Consensus MCP 2026-07-15 query: Lerner Tahar Bar Koren Flash 2021 VR setup assess peripersonal space audio tactile 3D boundaries",
        ],
    },
    "amiel_2025_front_rear": {
        "outcome_family": "quadrant_specific_front_rear_defensive_pps_asymmetry",
        "primary_expected_effect": (
            "Defensive audio-tactile PPS is expected to be nonhomogeneous: in "
            "front space, left-approaching sounds must be closer than right "
            "approaching sounds to facilitate tactile detection, whereas rear "
            "space shows similar facilitation distances for left and right."
        ),
        "expected_effect_direction": "front_space_lateral_asymmetry_but_rear_space_symmetric_facilitation",
        "observable_metric": "tactile detection facilitation distance by front/rear and left/right virtual approach quadrant",
        "condition_contrast": "front-left, front-right, rear-left, and rear-right looming 3D sound quadrants",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#amiel_2025_front_rear",
            "Consensus MCP 2026-07-15 query: Noel 2018 neural adaptation peripersonal space audio tactile",
        ],
    },
    "newborn_boundaries_2019": {
        "outcome_family": "newborn_intensity_defined_auditory_pps_boundary",
        "primary_expected_effect": (
            "Newborn saccadic reaction times to tactile stimulation are expected "
            "to vary with simultaneous sound intensity, becoming faster above a "
            "critical intensity that functions as a rudimentary PPS boundary cue."
        ),
        "expected_effect_direction": "louder_near_sound_intensity_speeds_newborn_tactile_saccadic_rt",
        "observable_metric": "newborn saccadic RT to tactile stimulation by simultaneous sound intensity",
        "condition_contrast": "sound intensities interpreted as distance cues in newborns and adults",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#newborn_boundaries_2019",
            "Consensus MCP 2026-07-15 query: pregnancy ageing newborn boundaries peripersonal space audio tactile PPS",
        ],
    },
    "pregnancy_2019": {
        "outcome_family": "third_trimester_expansion_of_pps",
        "primary_expected_effect": (
            "PPS is expected to be larger and the near/far transition more "
            "gradual in the third trimester of pregnancy, while second-trimester "
            "and postpartum PPS size are not expected to differ from controls."
        ),
        "expected_effect_direction": "third_trimester_expands_pps_and_softens_boundary_transition",
        "observable_metric": "audio-tactile PPS boundary size and psychometric slope by pregnancy stage",
        "condition_contrast": "second trimester, third trimester, postpartum, and non-pregnant controls",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#pregnancy_2019",
            "Consensus MCP 2026-07-15 query: pregnancy ageing newborn boundaries peripersonal space audio tactile PPS",
        ],
    },
    "footsole_vibration_2019": {
        "outcome_family": "pseudo_walking_footsole_vibration_pps_extension",
        "primary_expected_effect": (
            "Rhythmic walking-sound vibrations applied to the soles of the feet, "
            "but not the forearms, are expected to boost tactile processing when "
            "looming sounds are near the body, suggesting PPS extension without "
            "actual body movement."
        ),
        "expected_effect_direction": "footsole_walking_vibration_boosts_near_looming_tactile_processing",
        "observable_metric": "tactile processing/RT benefit for looming sounds by vibration site",
        "condition_contrast": "foot-sole walking-sound vibration versus forearm vibration/no-body-movement controls",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#footsole_vibration_2019",
            "Consensus MCP 2026-07-15 query: pregnancy ageing newborn boundaries peripersonal space audio tactile PPS",
        ],
    },
    "amemiya_2017_pseudowalking_footsole": {
        "outcome_family": "pseudowalking_footsole_vibration_extension_of_chest_pps",
        "primary_expected_effect": (
            "Cyclic foot-sole vibration based on low-pass-filtered walking "
            "sounds is expected to evoke a walking sensation and reduce chest "
            "tactile reaction times during looming sounds, indicating a forward "
            "expansion of PPS without physical body movement."
        ),
        "expected_effect_direction": "footsole_pseudowalking_vibration_expands_forward_pps",
        "observable_metric": "chest vibrotactile RT by looming-sound position/SOA and foot-sole vibration pattern",
        "condition_contrast": "walking-sensation foot-sole vibration pattern versus other/no vibration patterns during seated looming-sound PPS task",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#amemiya_2017_pseudowalking_footsole",
            "Consensus MCP 2026-07-15 query: 10.1109/WHC.2017.7989970 pseudowalking footsole vibration peripersonal space audio tactile",
        ],
    },
}


def main() -> int:
    coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))
    ledger = build_expected_outcome_coverage(coverage)
    OUTPUT_PATH.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    return 0


def build_expected_outcome_coverage(coverage: dict[str, Any]) -> dict[str, Any]:
    paper_audit_index = _load_csv_index(PAPER_AUDIT_CHECKLIST_PATH, key="record_id")
    manual_review_index = _load_csv_index(MANUAL_REVIEW_INDEX_PATH, key="record_id")
    records = [
        build_record(
            record,
            paper_audit_index.get(str(record.get("record_id") or ""), {}),
            manual_review_index.get(str(record.get("record_id") or ""), {}),
        )
        for record in coverage.get("literature_records", [])
    ]
    expected_counts = Counter(record["expected_outcome_status"] for record in records)
    observed_counts = Counter(record["observed_vs_expected_status"] for record in records)
    observed_gap_counts = Counter(record["observed_comparison_gap"] for record in records)
    blocker_counts = Counter(
        record["expected_outcome_extraction_blocker"]
        for record in records
        if record["expected_outcome_status"] == "pending_expected_outcome_extraction"
    )
    runnable_records = [record for record in records if record["runnable_status"] == "runnable_profile_parameters_ready"]
    return {
        "schema": SCHEMA,
        "generated_on": "2026-07-15",
        "source_literature_coverage": "assets/preloads/audiotactile_literature_coverage.json",
        "scope": {
            "goal": (
                "Track whether each known audiotactile PPS literature record has a structured "
                "expected outcome and whether the current toolkit has observed evidence that can "
                "be compared against it."
            ),
            "evidence_boundary": (
                "Protocol 12, static preview parity, one-block and ready-profile fake-audio runner "
                "stress, synthetic loopback, and ready-profile contrast audits prove software "
                "scheduling, WAV generation, event/marker, artifact, and comparison-readiness "
                "contracts. They do not prove human behavioral PPS effects. Observed scientific "
                "outcomes require either collected participant data or an explicit synthetic-participant "
                "model whose assumptions are documented separately."
            ),
        },
        "summary": {
            "literature_record_count": len(records),
            "structured_expected_outcome_record_count": expected_counts["structured_expected_outcome_extracted"],
            "pending_expected_outcome_record_count": expected_counts["pending_expected_outcome_extraction"],
            "adjacent_or_out_of_scope_record_count": expected_counts["adjacent_out_of_scope"],
            "runnable_profile_parameter_record_count": len(runnable_records),
            "observed_behavioral_comparison_record_count": observed_counts["observed_behavioral_comparison_available"],
            "parameter_run_evidence_only_record_count": observed_counts[
                "parameter_run_evidence_only_behavioral_effect_unobserved"
            ],
            "not_runnable_no_observed_comparison_record_count": observed_counts["not_runnable_no_observed_comparison"],
            "adjacent_not_applicable_record_count": observed_counts["adjacent_not_applicable"],
            "pending_expected_outcome_blocker_counts": dict(sorted(blocker_counts.items())),
            "observed_comparison_gap_counts": dict(sorted(observed_gap_counts.items())),
        },
        "expected_outcome_extraction_sources": {
            "paper_audit_checklist": "For-AI/audiotactile-paper-metadata-audit/running_checklist.csv",
            "manual_review_index": "For-AI/audiotactile-paper-metadata-audit/manual_review_index.csv",
        },
        "current_observed_evidence": {
            "profile_materialization": (
                "artifacts/validation_runs/current_goal_ready_profiles_protocol12_20260715_after_lerner_unlock/"
                "profile_recreation_interface_matrix_report.json"
            ),
            "static_dashboard_parity": (
                "artifacts/validation_runs/current_goal_ready_profiles_static_dashboard_parity_20260715_after_galli_wheelchair_unlock/"
                "static_dashboard_preview_parity_audit_report.json"
            ),
            "runner_mock": (
                "artifacts/validation_runs/current_goal_one_block_runner_20260714_duration500ms/"
                "one_block_trial_runner_report.json"
            ),
            "ready_profile_runner_smoke": (
                "artifacts/validation_runs/current_goal_ready_profiles_runner_smoke_20260715_after_lerner_unlock/"
                "ready_profile_runner_smoke_report.json"
            ),
            "ready_profile_response_marker_loopback": (
                "artifacts/validation_runs/current_goal_ready_profiles_response_marker_loopback_20260715_after_lerner_unlock/"
                "ready_profile_response_marker_loopback_report.json"
            ),
            "ready_profile_expected_contrast_audit": (
                "artifacts/validation_runs/current_goal_ready_profiles_expected_contrast_audit_20260715_after_lerner_unlock/"
                "ready_profile_expected_contrast_audit_report.json"
            ),
            "click_path_mock": (
                "artifacts/validation_runs/current_goal_session_click_path_20260714/"
                "session_runner_click_path_report.json"
            ),
            "synthetic_response_marker_loopback": (
                "artifacts/validation_runs/current_goal_mock_response_marker_loopback_20260714/comparison/"
                "response_marker_loopback_report.json"
            ),
            "synthetic_expected_outcome_smoke": (
                "artifacts/validation_runs/current_goal_synthetic_expected_outcome_smoke_20260715_after_lerner_unlock/"
                "synthetic_expected_outcome_smoke_report.json"
            ),
        },
        "records": records,
    }


def build_record(
    record: dict[str, Any],
    paper_audit_row: dict[str, str] | None = None,
    manual_review_row: dict[str, str] | None = None,
) -> dict[str, Any]:
    record_id = str(record.get("record_id") or "")
    coverage_category = str(record.get("coverage_category") or "")
    template_ids = [str(value) for value in record.get("current_template_ids") or []]
    expected = EXPECTED_OUTCOMES.get(record_id)
    adjacent = coverage_category == "adjacent_out_of_scope"
    paper_audit = paper_audit_row or {}
    manual_review = manual_review_row or {}

    if adjacent:
        expected_status = "adjacent_out_of_scope"
    elif expected:
        expected_status = "structured_expected_outcome_extracted"
    else:
        expected_status = "pending_expected_outcome_extraction"

    runnable_status = _runnable_status(record, coverage_category, template_ids, adjacent)
    observed_status = _observed_status(expected_status, runnable_status)
    observed_gap = _observed_comparison_gap(expected_status, runnable_status, coverage_category)
    extraction_blocker = _expected_outcome_extraction_blocker(expected_status, paper_audit, manual_review)

    return {
        "record_id": record_id,
        "citation_short": str(record.get("citation_short") or ""),
        "doi": str(record.get("doi") or ""),
        "coverage_category": coverage_category,
        "current_template_ids": template_ids,
        "runnable_status": runnable_status,
        "expected_outcome_status": expected_status,
        "expected_outcome": expected or {},
        "expected_outcome_extraction_blocker": extraction_blocker,
        "expected_outcome_source_audit": _expected_outcome_source_audit(paper_audit, manual_review),
        "observed_vs_expected_status": observed_status,
        "observed_comparison_gap": observed_gap,
        "observed_evidence_boundary": _observed_boundary(observed_status),
        "required_next_evidence": _required_next_evidence(expected_status, runnable_status),
    }


def _load_csv_index(path: Path, key: str) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = csv.DictReader(handle)
        return {
            str(row.get(key) or ""): {str(k): str(v or "") for k, v in row.items()}
            for row in rows
            if row.get(key)
        }


def _expected_outcome_extraction_blocker(
    expected_status: str,
    paper_audit: dict[str, str],
    manual_review: dict[str, str],
) -> str:
    if expected_status == "structured_expected_outcome_extracted":
        return "structured_expected_outcome_available"
    if expected_status == "adjacent_out_of_scope":
        return "adjacent_out_of_scope"

    manual_status = manual_review.get("manual_review_status", "")
    manual_confidence = manual_review.get("confidence_label", "")
    if manual_status:
        if manual_confidence == "partial_extraction" or "supplement_blocked" in manual_status:
            return "manual_review_partial_or_supplement_blocked"
        return "manual_review_needs_results_direction_structuring"

    pdf_status = paper_audit.get("pdf_status", "")
    extraction_status = paper_audit.get("extraction_status", "")
    metadata_confidence = paper_audit.get("metadata_confidence_label", "")
    visualization_status = paper_audit.get("pps_visualization_audit_status", "")

    if visualization_status == "source_mined":
        return "source_mined_needs_results_visual_review"
    if pdf_status == "needs_user_download":
        return "needs_user_pdf_download"
    if pdf_status in {"paywalled", "open_access_unavailable"}:
        return "main_pdf_unavailable_or_paywalled"
    if extraction_status == "pending_pdf":
        return "pending_pdf_extraction"
    if metadata_confidence in {"pending_source", "source_unavailable"}:
        return "source_unavailable_or_pending"
    return "expected_outcome_not_yet_reviewed"


def _expected_outcome_source_audit(
    paper_audit: dict[str, str],
    manual_review: dict[str, str],
) -> dict[str, str]:
    fields = {
        "paper_audit_pdf_status": paper_audit.get("pdf_status", ""),
        "paper_audit_supplement_status": paper_audit.get("supplement_status", ""),
        "paper_audit_extraction_status": paper_audit.get("extraction_status", ""),
        "paper_audit_metadata_confidence_label": paper_audit.get("metadata_confidence_label", ""),
        "paper_audit_visualization_status": paper_audit.get("pps_visualization_audit_status", ""),
        "paper_audit_visualization_candidate_count": paper_audit.get("pps_visualization_candidate_count", ""),
        "manual_review_status": manual_review.get("manual_review_status", ""),
        "manual_review_confidence_label": manual_review.get("confidence_label", ""),
        "manual_review_profile_recreation_assessment": manual_review.get("profile_recreation_assessment", ""),
    }
    return {key: value for key, value in fields.items() if value}


def _runnable_status(
    record: dict[str, Any],
    coverage_category: str,
    template_ids: list[str],
    adjacent: bool,
) -> str:
    if adjacent:
        return "adjacent_not_applicable"
    if record.get("can_recreate_audiotactile_components_now") is True and template_ids:
        return "runnable_profile_parameters_ready"
    if template_ids:
        return "template_present_but_blocked"
    return "not_yet_templated"


def _observed_status(expected_status: str, runnable_status: str) -> str:
    if expected_status == "adjacent_out_of_scope":
        return "adjacent_not_applicable"
    if runnable_status != "runnable_profile_parameters_ready":
        return "not_runnable_no_observed_comparison"
    return "parameter_run_evidence_only_behavioral_effect_unobserved"


def _observed_comparison_gap(expected_status: str, runnable_status: str, coverage_category: str) -> str:
    if expected_status == "adjacent_out_of_scope":
        return "not_applicable_adjacent_out_of_scope"
    if expected_status != "structured_expected_outcome_extracted":
        return "expected_outcome_extraction_pending"
    if runnable_status == "runnable_profile_parameters_ready":
        return "ready_profile_needs_behavioral_or_synthetic_outcome_comparison"
    if coverage_category == "covered_blocked_missing_publication_parameters":
        return "template_present_blocked_missing_publication_parameters"
    if coverage_category == "covered_blocked_toolkit_structure":
        return "template_present_blocked_toolkit_structure"
    if coverage_category == "not_yet_templated_missing_publication_parameters":
        return "not_yet_templated_missing_publication_parameters"
    if coverage_category == "not_yet_templated_requires_toolkit_structure":
        return "not_yet_templated_requires_toolkit_structure"
    return "not_runnable_unclassified"


def _observed_boundary(observed_status: str) -> str:
    if observed_status == "parameter_run_evidence_only_behavioral_effect_unobserved":
        return (
            "Current evidence can show that the profile can load/materialize/run as software, "
            "but no profile-specific participant or synthetic behavioral data have been "
            "compared with the paper's expected PPS effect."
        )
    if observed_status == "not_runnable_no_observed_comparison":
        return "The study is not yet runnable as a finished toolkit profile, so no observed comparison exists."
    return "The record is adjacent or out of scope for audiotactile PPS outcome comparison."


def _required_next_evidence(expected_status: str, runnable_status: str) -> str:
    if expected_status == "adjacent_out_of_scope":
        return "No outcome comparison required unless the record is reclassified as in scope."
    if expected_status == "pending_expected_outcome_extraction":
        return (
            "Extract a short structured expected outcome from the paper's Results/figures/tables "
            "and link it to an observable analysis metric."
        )
    if runnable_status == "not_yet_templated":
        return (
            "Create a profile template or add the missing toolkit structure before attempting "
            "observed-vs-expected evaluation."
        )
    if runnable_status != "runnable_profile_parameters_ready":
        return "Resolve profile blockers before attempting observed-vs-expected evaluation."
    return (
        "Run a profile-specific observed dataset: either collected participant data or an explicit "
        "synthetic participant model, then compare the analysis output with the structured expected effect."
    )


if __name__ == "__main__":
    raise SystemExit(main())
