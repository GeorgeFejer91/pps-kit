//! Explicit V2 stationary controls. Reuses the ingredient renderer contract;
//! never treats a saved moving waveform as a stationary or raw source.
use crate::{design::*, *};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::sync::atomic::AtomicBool;

pub const BASELINE_POLICY: &str = "native-stationary-t0-source-profile.v2";
pub const BASELINE_SEED_POLICY: &str = "sha256-stationary-burst-label-color-first32.v1";

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BaselineGenerationOptIn {
    pub source_algorithm: String,
    pub accept_non_legacy_source_algorithm: bool,
}

#[derive(Debug, Serialize)]
pub struct StationaryBaselineGenerationPlan {
    pub generation: IngredientGenerationPlan,
    pub source_label: String,
    pub seed_policy: &'static str,
    pub baseline_policy: &'static str,
    pub level_basis: &'static str,
    #[serde(skip_serializing)]
    original_design: Value,
    #[serde(skip_serializing)]
    source_index: usize,
    #[serde(skip_serializing)]
    design_sha256: String,
}

fn error(code: &'static str, field: &str, message: &'static str) -> CapabilityError {
    CapabilityError {
        code,
        field: field.into(),
        message,
    }
}
fn key(value: &str) -> String {
    value.replace(['_', '-'], " ").trim().to_lowercase()
}
fn number(value: &Value, field: &str, fallback: Option<f64>) -> Result<f64, CapabilityError> {
    value
        .get(field)
        .map(|v| v.as_f64().filter(|f| f.is_finite()))
        .unwrap_or(fallback)
        .ok_or_else(|| {
            error(
                "invalid_baseline_trajectory",
                "noises.trajectory_snapshot",
                "Saved source geometry and timing must contain finite numbers.",
            )
        })
}
fn point(value: &Value) -> Result<Position, CapabilityError> {
    Ok(Position {
        x_m: number(value, "x_m", None)?,
        y_m: number(value, "y_m", None)?,
        z_m: number(value, "z_m", Some(0.0))?,
    })
}
fn saved_point(
    snapshot: &Value,
    prefix: &str,
    trajectory: &Value,
) -> Result<Position, CapabilityError> {
    if let Some(p) = snapshot.get(prefix) {
        return point(p);
    }
    let radius = number(
        snapshot,
        &format!("{prefix}_distance_cm"),
        Some(number(trajectory, &format!("{prefix}_radius_m"), None)? * 100.0),
    )? / 100.0;
    let angle = number(
        snapshot,
        &format!("{prefix}_rotation_deg"),
        Some(number(
            trajectory,
            if prefix == "start" {
                "azimuth_start_deg"
            } else {
                "azimuth_end_deg"
            },
            Some(0.0),
        )?),
    )?
    .to_radians();
    let z = number(snapshot, &format!("{prefix}_height_cm"), Some(0.0))? / 100.0;
    if radius <= 0.0 || z.abs() > radius {
        return Err(error(
            "invalid_baseline_trajectory",
            "noises.trajectory_snapshot",
            "The saved height must fit within a positive source radius.",
        ));
    }
    let horizontal = (radius * radius - z * z).sqrt();
    Ok(Position {
        x_m: horizontal * angle.sin(),
        y_m: horizontal * angle.cos(),
        z_m: z,
    })
}

/// Mirrors _stationary_burst_source_for_segment geometry/timing/seed selection,
/// but requires explicit native RNG opt-in and records the changed renderer/source.
pub fn plan_stationary_baseline(
    design: &Value,
    source_label: &str,
    opt_in: &BaselineGenerationOptIn,
) -> Result<StationaryBaselineGenerationPlan, CapabilityError> {
    if source_label.trim().is_empty()
        || source_label.len() > 128
        || source_label.chars().any(char::is_control)
    {
        return Err(error(
            "baseline_generated_source_required",
            "source_label",
            "Choose a nonempty generated source label of at most 128 bytes.",
        ));
    }
    if !opt_in.accept_non_legacy_source_algorithm || opt_in.source_algorithm != SOURCE_ALGORITHM {
        return Err(error("new_source_algorithm_opt_in_required","baseline_generation_opt_in","Explicitly customize the profile for native V2 stationary controls; legacy NumPy waveform parity is unavailable."));
    }
    let design_sha256 = assembly::design_fingerprint(design).map_err(|_| {
        error(
            "invalid_baseline_design",
            "design",
            "Provide a bounded design object.",
        )
    })?;
    let noises = design["noises"].as_array().ok_or_else(|| {
        error(
            "baseline_generated_source_required",
            "noises",
            "Stationary controls require a selected generated noise source.",
        )
    })?;
    let matching: Vec<_> = noises
        .iter()
        .enumerate()
        .filter(|(_, s)| key(s["label"].as_str().unwrap_or("")) == key(source_label))
        .collect();
    if matching.len() != 1 {
        return Err(error(
            "baseline_generated_source_required",
            "source_label",
            "Choose exactly one existing generated noise source.",
        ));
    }
    let (source_index, source) = matching[0];
    let label = source["label"]
        .as_str()
        .ok_or_else(|| {
            error(
                "baseline_generated_source_required",
                "noises.label",
                "Choose a generated source with a text label.",
            )
        })?
        .trim();
    let color = source["noise_type"]
        .as_str()
        .unwrap_or("")
        .trim()
        .to_lowercase();
    let digest = Sha256::digest(format!("stationary-burst-baseline:{label}:{color}").as_bytes());
    let seed = u32::from_be_bytes(digest[..4].try_into().unwrap()) as u64;
    let mut working = design.clone();
    let snapshot = &source["trajectory_snapshot"];
    if !snapshot.is_null() && !snapshot.is_object() {
        return Err(error(
            "invalid_baseline_trajectory",
            "noises.trajectory_snapshot",
            "Saved source trajectory must be an object.",
        ));
    }
    if snapshot.as_object().is_some_and(|s| !s.is_empty()) {
        let trajectory = &design["trajectory"];
        let start = saved_point(snapshot, "start", trajectory)?;
        let end = saved_point(snapshot, "end", trajectory)?;
        let chord = ((end.x_m - start.x_m).powi(2)
            + (end.y_m - start.y_m).powi(2)
            + (end.z_m - start.z_m).powi(2))
        .sqrt();
        let previous_length = number(trajectory, "path_length_m", None)?;
        let previous_speed = number(trajectory, "propagation_speed_mps", None)?;
        let movement = number(
            snapshot,
            "movement_duration_s",
            Some(if previous_speed > 0.0 {
                previous_length / previous_speed
            } else {
                0.0
            }),
        )?;
        let length = number(snapshot, "path_length_m", Some(chord))?;
        let t = working
            .get_mut("trajectory")
            .filter(|t| t.is_object())
            .ok_or_else(|| {
                error(
                    "invalid_baseline_trajectory",
                    "design.trajectory",
                    "A saved trajectory is required.",
                )
            })?;
        t["coordinate_mode"] = json!("cartesian");
        for (prefix, p) in [("start", start), ("end", end)] {
            t[format!("{prefix}_x_m")] = json!(p.x_m);
            t[format!("{prefix}_y_m")] = json!(p.y_m);
            t[format!("{prefix}_z_m")] = json!(p.z_m);
        }
        t["path_length_m"] = json!(length);
        t["propagation_speed_mps"] = json!(if movement > 0.0 {
            length / movement
        } else {
            0.0
        });
        t["padding_pre_s"] = json!(number(
            snapshot,
            "start_hold_s",
            Some(number(trajectory, "padding_pre_s", Some(0.0))?)
        )?);
        t["padding_post_s"] = json!(number(
            snapshot,
            "end_hold_s",
            Some(number(trajectory, "padding_post_s", Some(0.0))?)
        )?);
    }
    let raw_policy = design["study_profile_reference_parameters"]
        .get("loudness_policy")
        .filter(|p| !p.is_null());
    let (policy, level_basis) = if let Some(policy) = raw_policy {
        if !policy.is_object() {
            return Err(error(
                "invalid_baseline_level_policy",
                "study_profile_reference_parameters.loudness_policy",
                "An explicit source level policy must be an object.",
            ));
        }
        (policy.clone(), "inherited_explicit_loudness_policy")
    } else {
        let peak = 20.0 * 0.9_f64.log10();
        (
            json!({"kind":"peak_normalize","target_peak_dbfs":peak,"peak_ceiling_dbfs":peak}),
            "legacy_absent_policy_digital_peak_0_90",
        )
    };
    let profile = source["source_profile"]
        .as_str()
        .filter(|s| !s.is_empty())
        .unwrap_or("dynaspace_gaussian_burst_train");
    let payload = json!({"design":working,"bake_recipe":{"kind":"generated_noise","action":"remake","original_label":label,"label":label,"gain":1.0,"noise_type":color,"source_profile":profile,"source_profile_parameters":source["source_profile_parameters"],"loudness_policy":policy,"display_color_hex":source["display_color_hex"].as_str().unwrap_or("#1C7A86")}});
    let mut generation = plan_ingredient_generation(
        &payload,
        &GenerationOptIn {
            source_algorithm: opt_in.source_algorithm.clone(),
            accept_non_legacy_source_algorithm: true,
            seed,
        },
    )?;
    let start = generation.request.trajectory.position_at(0.0);
    generation.request.trajectory = TrajectorySpec::Fixed { position: start };
    if raw_policy.is_none() {
        // The historical absent-policy branch enables direct-path gain before
        // its explicit 0.90 peak normalization, independently of trajectory UI hints.
        generation.renderer.distance_attenuation = true;
    }
    generation.source["motion_mode"] = json!("stationary");
    generation.trajectory_snapshot["native_trajectory"] =
        serde_json::to_value(&generation.request.trajectory).unwrap();
    generation.trajectory_snapshot["end"] = generation.trajectory_snapshot["start"].clone();
    generation.trajectory_snapshot["end_distance_cm"] =
        generation.trajectory_snapshot["start_distance_cm"].clone();
    generation.trajectory_snapshot["end_rotation_deg"] =
        generation.trajectory_snapshot["start_rotation_deg"].clone();
    generation.trajectory_snapshot["end_height_cm"] =
        generation.trajectory_snapshot["start_height_cm"].clone();
    generation.trajectory_snapshot["coordinate_mode"] = json!("cartesian");
    generation.trajectory_snapshot["path_direction"] = json!("stationary");
    generation.trajectory_snapshot["path_length_m"] = json!(0.0);
    generation.trajectory_snapshot["motion_mode"] = json!("stationary");
    generation.design_sha256=format!("{:x}",Sha256::digest(serde_json::to_vec(&json!({"design_sha256":design_sha256,"source_index":source_index,"request":generation.request,"renderer":generation.renderer,"seed_policy":BASELINE_SEED_POLICY,"baseline_policy":BASELINE_POLICY,"level_basis":level_basis})).unwrap()));
    Ok(StationaryBaselineGenerationPlan {
        generation,
        source_label: label.into(),
        seed_policy: BASELINE_SEED_POLICY,
        baseline_policy: BASELINE_POLICY,
        level_basis,
        original_design: design.clone(),
        source_index,
        design_sha256,
    })
}

#[derive(Debug, Serialize)]
pub struct GeneratedStationaryBaselineEntry {
    asset: Value,
    reference: String,
    design_sha256: String,
    generation_sha256: String,
}
impl GeneratedStationaryBaselineEntry {
    pub fn asset(&self) -> &Value {
        &self.asset
    }
}

pub fn generated_stationary_baseline_entry(
    plan: &StationaryBaselineGenerationPlan,
    relative_asset_path: &str,
    wav_bytes: &[u8],
    stimulus: &GeneratedStimulus,
    renderer_report: &Value,
    cancelled: &AtomicBool,
) -> Result<GeneratedStationaryBaselineEntry, GenerationError> {
    let entry = generated_ingredient_entry(
        &plan.generation,
        relative_asset_path,
        wav_bytes,
        stimulus,
        renderer_report,
        cancelled,
    )?;
    if !matches!(
        plan.generation.request.trajectory,
        TrajectorySpec::Fixed { .. }
    ) {
        return Err(GenerationError::Invalid("baseline_fixed_motion_required"));
    }
    let mut asset = entry.asset().clone();
    asset["label"] = json!(format!("{} stationary baseline", plan.source_label));
    asset["source_kind"] = json!("stationary_baseline");
    asset["motion_mode"] = json!("stationary");
    asset["role"] = json!("stationary_baseline");
    asset["target_source_label"] = json!(plan.source_label);
    asset["provenance"]["baseline_policy"] = json!(BASELINE_POLICY);
    asset["provenance"]["seed_policy"] = json!(BASELINE_SEED_POLICY);
    asset["provenance"]["baseline_design_sha256"] = json!(plan.design_sha256);
    asset["provenance"]["level_basis"] = json!(plan.level_basis);
    asset["provenance"]["moving_condition_validation_inherited"] = json!(false);
    asset["provenance"]["perceptual_loudness_matched"] = json!(false);
    Ok(GeneratedStationaryBaselineEntry {
        asset,
        reference: relative_asset_path.into(),
        design_sha256: plan.design_sha256.clone(),
        generation_sha256: plan.generation.design_sha256.clone(),
    })
}

#[derive(Debug, Serialize)]
pub struct StationaryBaselinePublication {
    pub design: Value,
    pub asset: Value,
    pub invalidate_segments: [u8; 4],
    pub invalidate_run_package: bool,
}
pub fn apply_generated_stationary_baseline(
    plan: &StationaryBaselineGenerationPlan,
    entry: &GeneratedStationaryBaselineEntry,
) -> Result<StationaryBaselinePublication, GenerationError> {
    if entry.design_sha256 != plan.design_sha256
        || entry.generation_sha256 != plan.generation.design_sha256
    {
        return Err(GenerationError::Invalid("baseline_plan_mismatch"));
    }
    let mut design = plan.original_design.clone();
    let source = &mut design["noises"][plan.source_index];
    source["native_stationary_baseline_asset"] = json!(entry.reference);
    source["native_stationary_baseline_sha256"] = entry.asset["sha256"].clone();
    source["native_stationary_baseline_provenance"] = entry.asset["provenance"].clone();
    let profile = design["study_profile_id"].as_str().unwrap_or("").to_owned();
    if !design["study_profile_reference_parameters"].is_object() {
        design["study_profile_reference_parameters"] = json!({});
    }
    let params = &mut design["study_profile_reference_parameters"];
    if !profile.is_empty() {
        params["customized_from_profile_id"] = json!(profile);
    }
    params["dashboard_mode"] = json!("custom");
    params["profile_status"] = json!("draft");
    params["native_generation_qualification"] = json!("customized_native_generation_unqualified");
    params.as_object_mut().unwrap().remove("finalized_at");
    design["study_profile_id"] = json!("");
    design["study_profile_title"] = json!("");
    Ok(StationaryBaselinePublication {
        design,
        asset: entry.asset.clone(),
        invalidate_segments: [3, 4, 5, 6],
        invalidate_run_package: true,
    })
}
