//! Existing V1 strip metadata contract, shared in meaning with
//! dashboard_app.ROW_CONTRACT_FIELDS. Unknown metadata is never promoted.
use crate::GenerationError;
use serde_json::{Map, Value};

pub const ROW_CONTRACT_FIELDS: &[&str] = &[
    "spatial_value_cm",
    "expected_response",
    "response_rule",
    "target_role",
    "response_mode",
    "response_choice_set",
    "correct_response",
    "response_scoring_policy",
    "response_capture_device",
    "response_input_modality",
    "tool_condition",
    "locomotion_condition",
    "multisensory_trial_family",
    "exteroceptive_modality_set",
    "visual_stimulus_type",
    "visual_motion_profile",
    "visual_start_distance_cm",
    "visual_end_distance_cm",
    "visual_speed_cm_s",
    "visual_duration_ms",
    "visual_renderer_engine",
    "visual_display_device",
    "mixed_reality_context",
    "body_rendering_mode",
    "audiovisual_synchrony_policy",
    "mixed_reality_equivalence_boundary",
    "voice_key_enabled",
    "voice_key_response_label",
    "voice_key_threshold",
    "voice_key_latency_correction_ms",
    "spatial_coordinate_frame",
    "body_anchor",
    "body_part",
    "body_side",
    "spatial_hemifield",
    "body_relative_axis",
    "auditory_trajectory_family",
    "auditory_trajectory_direction",
    "trajectory_coordinate_frame",
    "trajectory_start_hemifield",
    "trajectory_end_hemifield",
    "trajectory_start_distance_cm",
    "trajectory_end_distance_cm",
    "trajectory_start_azimuth_deg",
    "trajectory_end_azimuth_deg",
    "spatial_renderer_engine",
    "spatial_renderer_version",
    "hrtf_database",
    "hrtf_subject_id",
    "hrtf_filter_id",
    "hrtf_near_field_compensation",
    "source_asset_equivalence",
    "renderer_equivalence_boundary",
    "primary_analysis_included",
    "audio_output_mode",
    "speaker_array_id",
    "speaker_array_layout",
    "speaker_switch_sequence",
    "speaker_switch_times_ms",
    "speaker_switch_channels",
    "speaker_switch_gains",
    "speaker_source_channel",
    "speaker_switch_generated",
    "iti_policy",
    "iti_ms",
    "foreperiod_ms",
    "hazard_control_policy",
    "expectancy_control_role",
    "tactile_stimulation_modality",
    "tactile_calibration_method",
    "tactile_threshold_reference",
    "tactile_intensity",
    "tactile_intensity_unit",
    "tactile_pulse_duration_ms",
    "electrical_stimulator_model",
    "electrical_electrode_site",
    "tactile_waveform_shape",
    "tactile_frequency_hz",
    "tactile_duration_ms",
    "tactile_amplitude",
    "tactile_waveform_generated",
    "external_trigger_required",
    "external_trigger_modality",
    "external_trigger_role",
    "external_trigger_code",
    "external_trigger_tolerance_ms",
    "external_trigger_channel",
];

fn nonempty(value: &Value) -> bool {
    !value.is_null() && value.as_str() != Some("")
}

pub(crate) fn merge(strip: &Value, row: &Value, family: &str) -> Result<Value, GenerationError> {
    let metadata = strip.get("metadata").filter(|v| !v.is_null());
    if metadata.is_some_and(|v| !v.is_object()) {
        return Err(GenerationError::Invalid("assembly_strip_contract_metadata"));
    }
    let mut expected = Map::new();
    for field in ROW_CONTRACT_FIELDS {
        if let Some(value) = metadata.and_then(|m| m.get(*field)).filter(|v| nonempty(v)) {
            expected.insert((*field).to_owned(), value.clone());
        }
    }
    let defaults: &[(&str, &str)] = match family {
        "catch" => {
            expected.insert("expected_response".into(), Value::from("withhold"));
            expected.insert("target_role".into(), Value::from("catch_no_target"));
            &[("response_rule", "withhold_response_to_audio_only_catch")]
        }
        "auditory_only" => &[
            ("expected_response", "respond"),
            ("target_role", "auditory_target"),
            ("response_rule", "respond_to_auditory_target"),
        ],
        _ => &[],
    };
    for (key, fallback) in defaults {
        expected.entry((*key).to_owned()).or_insert_with(|| {
            row.get(*key)
                .filter(|v| nonempty(v))
                .cloned()
                .unwrap_or_else(|| Value::from(*fallback))
        });
    }
    let mut enriched = row.clone();
    let object = enriched
        .as_object_mut()
        .ok_or(GenerationError::Invalid("assembly_row_contract"))?;
    for (field, value) in expected {
        if object
            .get(&field)
            .is_some_and(|v| nonempty(v) && *v != value)
        {
            return Err(GenerationError::Invalid("assembly_row_contract_conflict"));
        }
        object.insert(field, value);
    }
    Ok(enriched)
}
