//! Maps the existing collectPayload()+bake_recipe contract. It plans one
//! ingredient only; file authority, accepted-plan locks and jobs belong to host.
use crate::*;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct GenerationOptIn {
    pub source_algorithm: String,
    pub accept_non_legacy_source_algorithm: bool,
    pub seed: u64,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct CapabilityError {
    pub code: &'static str,
    pub field: String,
    pub message: &'static str,
}
impl std::fmt::Display for CapabilityError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}: {}", self.field, self.message)
    }
}
impl std::error::Error for CapabilityError {}
fn error(code: &'static str, field: impl Into<String>, message: &'static str) -> CapabilityError {
    CapabilityError {
        code,
        field: field.into(),
        message,
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct IngredientRendererPolicy {
    /// Opaque reference only. The host resolves an approved HRTF receipt/path.
    pub hrtf_reference: String,
    pub head_radius_m: f64,
    pub distance_attenuation: bool,
    pub near_field: bool,
    pub propagation_delay: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct IngredientGenerationPlan {
    pub source_kind: String,
    pub source_label: String,
    pub action: String,
    pub original_label: String,
    pub request: GenerationRequest,
    pub renderer: IngredientRendererPolicy,
    pub source_input_reference: Option<String>,
    pub source: Value,
    pub trajectory_snapshot: Value,
    pub display_color_hex: String,
    pub design_sha256: String,
    pub loudness_policy: Value,
    pub qualification: &'static str,
    #[serde(skip_serializing)]
    candidate_design: Value,
}

/// `payload` is the complete existing collectPayload() result including
/// trajectory_controls and bake_recipe. Never drop the ingredient draft.
pub fn plan_ingredient_generation(
    payload: &Value,
    opt_in: &GenerationOptIn,
) -> Result<IngredientGenerationPlan, CapabilityError> {
    bound_value(payload, 0, &mut 0)?;
    let design = payload
        .get("design")
        .filter(|v| v.is_object())
        .ok_or_else(|| {
            error(
                "design_required",
                "design",
                "Provide the existing design object.",
            )
        })?;
    let recipe = payload
        .get("bake_recipe")
        .filter(|v| v.is_object())
        .ok_or_else(|| {
            error(
                "recipe_required",
                "bake_recipe",
                "Choose an ingredient to generate.",
            )
        })?;
    validate_design_containers(design)?;
    let kind = text(recipe, "kind")?;
    if !["generated_noise", "imported_audio"].contains(&kind) {
        return Err(error(
            "unsupported_ingredient_kind",
            "bake_recipe.kind",
            "This generation route supports generated noise or imported dry WAV spatialization.",
        ));
    }
    let label = text(recipe, "label")?.trim();
    if label.is_empty() || label.len() > 128 || label.chars().any(char::is_control) {
        return Err(error(
            "invalid_label",
            "bake_recipe.label",
            "Use a nonempty ingredient label of at most 128 bytes.",
        ));
    }
    let action = text(recipe, "action")?;
    if !["create", "remake"].contains(&action) {
        return Err(error(
            "unsupported_action",
            "bake_recipe.action",
            "Choose create or remake.",
        ));
    }
    let original = recipe
        .get("original_label")
        .and_then(Value::as_str)
        .unwrap_or("");
    let entries = [
        ("noises", "generated_noise"),
        ("custom_looming_files", "imported_audio"),
        ("prestimulus_files", "fixed_audio"),
    ];
    let mut original_kind = None;
    for (collection, entry_kind) in entries {
        for entry in design
            .get(collection)
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
        {
            if source_key(entry["label"].as_str().unwrap_or("")) == source_key(label)
                && !(action == "remake" && source_key(label) == source_key(original))
            {
                return Err(error(
                    "duplicate_label",
                    "bake_recipe.label",
                    "Another ingredient already uses this label.",
                ));
            }
            if source_key(entry["label"].as_str().unwrap_or("")) == source_key(original) {
                original_kind = Some(entry_kind);
            }
        }
    }
    if action == "remake" && original_kind != Some(kind) {
        return Err(error(
            "remake_source_mismatch",
            "bake_recipe.original_label",
            "Remake requires an existing ingredient of the same source kind.",
        ));
    }
    let (trajectory, pre, movement, post) =
        trajectory_from_payload(design, payload.get("trajectory_controls"))?;
    let duration = pre + movement + post;
    let rate = number(&design["trajectory"], "sample_rate", None)?;
    if rate.fract() != 0.0 || !(8000.0..=192000.0).contains(&rate) {
        return Err(error(
            "invalid_sample_rate",
            "design.trajectory.sample_rate",
            "Choose an integer sample rate from 8000 to 192000 Hz.",
        ));
    }
    let (level, distance_attenuation) = level_policy(design, recipe, pre, movement)?;
    let gain = number(recipe, "gain", Some(1.0))?;
    if gain != 1.0 {
        return Err(error(
            "unsupported_recipe_gain",
            "bake_recipe.gain",
            "Use the explicit loudness policy for ingredient levels; recipe gain must be one.",
        ));
    }
    let (source, algorithm, seed, source_input, source_metadata) = if kind == "generated_noise" {
        if !opt_in.accept_non_legacy_source_algorithm || opt_in.source_algorithm != SOURCE_ALGORITHM
        {
            return Err(error("new_source_algorithm_opt_in_required","generation_opt_in","Explicitly accept the native source algorithm; legacy NumPy seed parity is unavailable."));
        }
        let noise_type = text(recipe, "noise_type")?;
        let color = serde_json::from_value::<NoiseColor>(json!(noise_type)).map_err(|_| {
            error(
                "unsupported_noise_color",
                "bake_recipe.noise_type",
                "Choose white, pink, blue, violet or brown noise.",
            )
        })?;
        let profile_id = text(recipe, "source_profile")?;
        let (profile, parameters) = source_profile(
            profile_id,
            &recipe["source_profile_parameters"],
            movement,
            duration,
        )?;
        (
            SourceSpec::Noise { color, profile },
            SOURCE_ALGORITHM,
            opt_in.seed,
            None,
            json!({"label":label,"noise_type":noise_type,
            "azimuth_deg":0.0,"elevation_deg":0.0,"gain":1.0,"source_profile":profile_id,
            "source_profile_parameters":parameters,"prebaked_path":"","sequence_order":0,"motion_mode":"looming"}),
        )
    } else {
        let audio = &recipe["audio"];
        if audio.get("render_mode").and_then(Value::as_str) != Some("spatialize") {
            return Err(error("import_requires_spatialize","bake_recipe.audio.render_mode","This route requires explicit dry-source spatialization; fixed stereo preservation is separate."));
        }
        let reference = audio
            .get("source_input_path")
            .or_else(|| audio.get("path"))
            .and_then(Value::as_str)
            .filter(|s| !s.is_empty() && s.len() <= 4096)
            .ok_or_else(|| {
                error(
                    "verified_import_required",
                    "bake_recipe.audio",
                    "Choose a verified dry WAV asset; a legacy rendered file is not a dry source.",
                )
            })?;
        let sha = text(audio, "sha256")?;
        if !valid_sha(sha) {
            return Err(error(
                "verified_import_required",
                "bake_recipe.audio.sha256",
                "Bind the selected native asset SHA-256 before generation.",
            ));
        }
        let channel_policy =
            serde_json::from_value::<ImportChannelPolicy>(audio["channel_policy"].clone())
                .map_err(|_| {
                    error(
                        "import_policy_required",
                        "bake_recipe.audio.channel_policy",
                        "Explicitly choose mono or stereo_mean.",
                    )
                })?;
        let length_policy = serde_json::from_value::<ImportLengthPolicy>(
            audio["length_policy"].clone(),
        )
        .map_err(|_| {
            error(
                "import_policy_required",
                "bake_recipe.audio.length_policy",
                "Explicitly choose exact or trim_or_zero_pad.",
            )
        })?;
        (
            SourceSpec::ImportedWav {
                sha256: sha.into(),
                channel_policy,
                length_policy,
            },
            IMPORT_ALGORITHM,
            0,
            Some(reference.to_owned()),
            json!({"label":label,"path":"","target_duration_s":duration,"render_mode":"spatialize","tone_type":"custom_audio",
                "gain":1.0,"motion_mode":"looming","source_input_path":reference}),
        )
    };
    let request = GenerationRequest {
        schema: REQUEST_SCHEMA.into(),
        source_algorithm: algorithm.into(),
        sample_rate_hz: rate as u32,
        duration_s: duration,
        seed,
        source,
        trajectory,
        tactile: vec![],
        level,
    };
    validate(&request).map_err(|_| {
        error(
            "unsupported_generation_parameters",
            "design.trajectory",
            "The requested timing, geometry or levels exceed the native generation contract.",
        )
    })?;
    let parameters = &design["study_profile_reference_parameters"];
    if let Some(options) = recipe.get("spatialization") {
        let object = options.as_object().ok_or_else(|| {
            error(
                "invalid_spatialization_policy",
                "bake_recipe.spatialization",
                "Spatialization policy must be an object.",
            )
        })?;
        if object.keys().any(|key| {
            !["near_field", "far_distance_filter", "propagation_delay"].contains(&key.as_str())
        }) {
            return Err(error(
                "unsupported_spatialization_policy",
                "bake_recipe.spatialization",
                "Unknown spatialization controls cannot be silently discarded.",
            ));
        }
    }
    let spatialization = recipe.get("spatialization").unwrap_or(parameters);
    if boolean(spatialization, "near_field", false)? {
        return Err(error(
            "near_field_ild_unavailable",
            "design.study_profile_reference_parameters.near_field",
            "Near-field correction needs a verified ILD asset and is unavailable.",
        ));
    }
    if boolean(spatialization, "far_distance_filter", false)? {
        return Err(error(
            "far_distance_filter_unavailable",
            "bake_recipe.spatialization.far_distance_filter",
            "Far-distance filtering has no validated native generation policy.",
        ));
    }
    let propagation_delay = boolean(spatialization, "propagation_delay", true)?;
    let head_radius = number(parameters, "head_diameter_m", Some(0.18))? / 2.0;
    if !(0.04..=0.15).contains(&head_radius) || request.trajectory.minimum_distance() <= head_radius
    {
        return Err(error(
            "source_inside_listener_head",
            "design.trajectory",
            "Keep the complete path outside the declared listener head.",
        ));
    }
    let hrtf = text(design, "sofa_file")?;
    if hrtf.is_empty() || hrtf.len() > 4096 {
        return Err(error(
            "hrtf_reference_required",
            "design.sofa_file",
            "Select a native-authorized HRTF asset.",
        ));
    }
    let color = recipe
        .get("display_color_hex")
        .and_then(Value::as_str)
        .unwrap_or("#1C7A86");
    if color.len() != 7
        || !color.starts_with('#')
        || !color[1..].bytes().all(|b| b.is_ascii_hexdigit())
    {
        return Err(error(
            "invalid_display_color",
            "bake_recipe.display_color_hex",
            "Use a six-digit hex color.",
        ));
    }
    let snapshot =
        trajectory_snapshot(&request, label, kind, &source_metadata, pre, movement, post);
    let mut candidate_design = design.clone();
    update_candidate_trajectory(
        &mut candidate_design,
        &request,
        &snapshot,
        pre,
        movement,
        post,
    )?;
    let mut loudness = recipe
        .get("loudness_policy")
        .or_else(|| parameters.get("loudness_policy"))
        .cloned()
        .unwrap_or(Value::Null);
    if let LevelPolicy::LinearDbRamp {
        start_rms_dbfs,
        end_rms_dbfs,
        calibration_window_s,
        ..
    } = request.level
    {
        loudness["pre_hold_s"] = json!(pre);
        loudness["movement_duration_s"] = json!(movement);
        loudness["post_hold_s"] = json!(post);
        loudness["total_duration_s"] = json!(duration);
        loudness["start_target_rms_dbfs"] = json!(start_rms_dbfs);
        loudness["end_target_rms_dbfs"] = json!(end_rms_dbfs);
        loudness["calibration_window_s"] = json!(calibration_window_s);
        loudness["distance_gain_policy"] =
            json!("disable_direct_path_gain_for_calibrated_loudness");
    }
    if !candidate_design["study_profile_reference_parameters"].is_object() {
        candidate_design["study_profile_reference_parameters"] = json!({});
    }
    candidate_design["study_profile_reference_parameters"]["loudness_policy"] = loudness.clone();
    let digest = format!(
        "{:x}",
        Sha256::digest(
            serde_json::to_vec(&json!({"payload":payload,"generation_opt_in":opt_in})).map_err(
                |_| error(
                    "invalid_payload",
                    "payload",
                    "Cannot encode the generation payload."
                )
            )?
        )
    );
    Ok(IngredientGenerationPlan {
        source_kind: kind.into(),
        source_label: label.into(),
        action: action.into(),
        original_label: original.into(),
        request,
        renderer: IngredientRendererPolicy {
            hrtf_reference: hrtf.into(),
            head_radius_m: head_radius,
            distance_attenuation,
            near_field: false,
            propagation_delay,
        },
        source_input_reference: source_input,
        source: source_metadata,
        trajectory_snapshot: snapshot,
        display_color_hex: color.to_uppercase(),
        design_sha256: digest,
        loudness_policy: loudness,
        qualification: "customized_native_generation_unqualified",
        candidate_design,
    })
}

fn update_candidate_trajectory(
    design: &mut Value,
    request: &GenerationRequest,
    snapshot: &Value,
    pre: f64,
    movement: f64,
    post: f64,
) -> Result<(), CapabilityError> {
    let t = &mut design["trajectory"];
    let chord = snapshot["path_length_m"].as_f64().unwrap_or(0.0);
    let length = if matches!(request.trajectory, TrajectorySpec::Polar { .. }) || chord == 0.0 {
        number(t, "path_length_m", None)?
    } else {
        chord
    };
    t["coordinate_mode"] = snapshot["coordinate_mode"].clone();
    t["path_direction"] = json!("custom");
    t["padding_pre_s"] = json!(pre);
    t["padding_post_s"] = json!(post);
    // Preserve the existing declared timing length for stationary sources.
    // Never fabricate a physical path length to encode a new hold duration.
    if movement > 0.0 && length == 0.0 {
        return Err(error(
            "stationary_duration_missing",
            "design.trajectory",
            "A stationary active interval needs an existing declared timing length.",
        ));
    }
    t["path_length_m"] = json!(length);
    t["propagation_speed_mps"] = json!(if movement > 0.0 {
        length / movement
    } else {
        0.0
    });
    for prefix in ["start", "end"] {
        for axis in ["x_m", "y_m", "z_m"] {
            t[format!("{prefix}_{axis}")] = snapshot[prefix][axis].clone();
        }
    }
    t["start_radius_m"] = json!(snapshot["start_distance_cm"].as_f64().unwrap() / 100.0);
    t["end_radius_m"] = json!(snapshot["end_distance_cm"].as_f64().unwrap() / 100.0);
    match request.trajectory {
        TrajectorySpec::Polar {
            azimuth_start_deg,
            azimuth_end_deg,
            elevation_deg,
            ..
        } => {
            t["azimuth_start_deg"] = json!(azimuth_start_deg);
            t["azimuth_end_deg"] = json!(azimuth_end_deg);
            t["elevation_deg"] = json!(elevation_deg);
        }
        _ => {
            t["azimuth_start_deg"] = snapshot["start_rotation_deg"].clone();
            t["azimuth_end_deg"] = snapshot["end_rotation_deg"].clone();
        }
    }
    Ok(())
}

#[derive(Debug, Serialize)]
pub struct GeneratedIngredientEntry {
    source: Value,
    asset: Value,
    qualification: &'static str,
}
impl GeneratedIngredientEntry {
    pub fn source(&self) -> &Value {
        &self.source
    }
    pub fn asset(&self) -> &Value {
        &self.asset
    }
}
#[derive(Debug, Serialize)]
pub struct IngredientPublication {
    pub design: Value,
    pub asset: Value,
    pub invalidate_segments: [u8; 5],
    pub invalidate_run_package: bool,
}

/// Applies only source semantics. The host must atomically fence publication by
/// design revision and invalidate downstream outputs and accepted packages.
pub fn apply_generated_ingredient(
    plan: &IngredientGenerationPlan,
    entry: &GeneratedIngredientEntry,
) -> Result<IngredientPublication, GenerationError> {
    if entry.asset["provenance"]["design_sha256"] != plan.design_sha256
        || entry.source["label"] != plan.source_label
    {
        return Err(GenerationError::Invalid("ingredient_plan_mismatch"));
    }
    let mut design = plan.candidate_design.clone();
    let original = source_key(&plan.original_label);
    for collection in ["noises", "custom_looming_files", "prestimulus_files"] {
        if design.get(collection).is_none() {
            design[collection] = json!([]);
        }
        let entries = design[collection]
            .as_array_mut()
            .ok_or(GenerationError::Invalid("source_collection"))?;
        if plan.action == "remake" {
            entries.retain(|e| source_key(e["label"].as_str().unwrap_or("")) != original);
        }
    }
    let collection = if plan.source_kind == "generated_noise" {
        "noises"
    } else {
        "custom_looming_files"
    };
    design[collection]
        .as_array_mut()
        .unwrap()
        .push(entry.source.clone());
    if plan.action == "remake" && original != source_key(&plan.source_label) {
        if let Some(strips) = design["protocol"]["trial_strips"].as_array_mut() {
            for strip in strips {
                if let Some(elements) = strip["elements"].as_array_mut() {
                    for element in elements {
                        for field in ["source_label", "label"] {
                            if source_key(element[field].as_str().unwrap_or("")) == original {
                                element[field] = json!(plan.source_label);
                            }
                        }
                        if let Some(labels) = element["source_labels"].as_array_mut() {
                            for label in labels {
                                if source_key(label.as_str().unwrap_or("")) == original {
                                    *label = json!(plan.source_label);
                                }
                            }
                        }
                    }
                }
            }
        }
        for collection in ["custom_looming_files", "prestimulus_files"] {
            for asset in design[collection].as_array_mut().unwrap() {
                if source_key(asset["target_source_label"].as_str().unwrap_or("")) == original {
                    asset["target_source_label"] = json!(plan.source_label);
                }
            }
        }
    }
    let old_profile = design["study_profile_id"].as_str().unwrap_or("").to_owned();
    let params = &mut design["study_profile_reference_parameters"];
    if !old_profile.is_empty() {
        params["customized_from_profile_id"] = json!(old_profile);
    }
    params["dashboard_mode"] = json!("custom");
    params["profile_status"] = json!("draft");
    params["native_generation_qualification"] = json!(plan.qualification);
    params["native_source_algorithm"] = json!(plan.request.source_algorithm);
    params.as_object_mut().unwrap().remove("finalized_at");
    design["study_profile_id"] = json!("");
    design["study_profile_title"] = json!("");
    Ok(IngredientPublication {
        design,
        asset: entry.asset.clone(),
        invalidate_segments: [2, 3, 4, 5, 6],
        invalidate_run_package: true,
    })
}
fn source_key(value: &str) -> String {
    value.replace(['_', '-'], " ").trim().to_lowercase()
}
fn validate_design_containers(design: &Value) -> Result<(), CapabilityError> {
    for key in ["noises", "custom_looming_files", "prestimulus_files"] {
        if let Some(value) = design.get(key) {
            let array = value.as_array().ok_or_else(|| {
                error(
                    "invalid_source_collection",
                    key,
                    "Ingredient collections must be arrays.",
                )
            })?;
            if array
                .iter()
                .any(|v| !v.is_object() || v["label"].as_str().is_none_or(|s| s.trim().is_empty()))
            {
                return Err(error(
                    "invalid_source_collection",
                    key,
                    "Each ingredient requires a label.",
                ));
            }
        }
    }
    if let Some(protocol) = design.get("protocol") {
        if !protocol.is_object() {
            return Err(error(
                "invalid_protocol",
                "design.protocol",
                "The protocol must be an object.",
            ));
        }
        if let Some(strips) = protocol.get("trial_strips") {
            let strips = strips.as_array().ok_or_else(|| {
                error(
                    "invalid_trial_strips",
                    "design.protocol.trial_strips",
                    "Trial strips must be an array.",
                )
            })?;
            for strip in strips {
                if !strip.is_object() {
                    return Err(error(
                        "invalid_trial_strip",
                        "design.protocol.trial_strips",
                        "Each trial strip must be an object.",
                    ));
                }
                if let Some(elements) = strip.get("elements") {
                    if !elements.is_array()
                        || elements.as_array().unwrap().iter().any(|v| !v.is_object())
                    {
                        return Err(error(
                            "invalid_trial_elements",
                            "design.protocol.trial_strips.elements",
                            "Trial elements must be objects.",
                        ));
                    }
                }
            }
        }
    }
    Ok(())
}

fn trajectory_from_payload(
    design: &Value,
    controls: Option<&Value>,
) -> Result<(TrajectorySpec, f64, f64, f64), CapabilityError> {
    let t = &design["trajectory"];
    // design_from_dict defaults old radius-only payloads to polar, but infers
    // Cartesian mode when any endpoint field exists. Do not force the HTML
    // adapter to invent a field absent from the saved Python schema.
    let cartesian_fields = [
        "start_x_m",
        "start_y_m",
        "start_z_m",
        "end_x_m",
        "end_y_m",
        "end_z_m",
    ];
    let inferred_mode = if cartesian_fields.iter().any(|key| t.get(key).is_some()) {
        "cartesian"
    } else {
        "polar"
    };
    let mode = t
        .get("coordinate_mode")
        .map(|_| text(t, "coordinate_mode"))
        .transpose()?
        .unwrap_or(inferred_mode);
    if !["polar", "cartesian"].contains(&mode) {
        return Err(error(
            "unsupported_trajectory_mode",
            "design.trajectory.coordinate_mode",
            "Choose explicit polar or Cartesian coordinates.",
        ));
    }
    let pre = number(t, "padding_pre_s", Some(0.0))?;
    let post = number(t, "padding_post_s", Some(0.0))?;
    let length = number(t, "path_length_m", None)?;
    let speed = number(t, "propagation_speed_mps", None)?;
    if length < 0.0 || speed < 0.0 {
        return Err(error(
            "invalid_trajectory_timing",
            "design.trajectory",
            "Path length and speed must be nonnegative.",
        ));
    }
    let movement = if speed > 0.0 { length / speed } else { 0.0 };
    let trajectory = if mode == "cartesian"
        || cartesian_fields
            .iter()
            .any(|key| t.get(key).is_some_and(|v| !v.is_null()))
    {
        let point = |prefix: &str| -> Result<Position, CapabilityError> {
            Ok(Position {
                x_m: number(t, &format!("{prefix}_x_m"), None)?,
                y_m: number(t, &format!("{prefix}_y_m"), None)?,
                z_m: number(t, &format!("{prefix}_z_m"), None)?,
            })
        };
        TrajectorySpec::Linear {
            start: point("start")?,
            end: point("end")?,
            pre_hold_s: pre,
            movement_duration_s: movement,
        }
    } else {
        let mut az0 = number(t, "azimuth_start_deg", Some(0.0))?;
        let mut az1 = number(t, "azimuth_end_deg", Some(0.0))?;
        if az0 == az1 {
            match t["path_direction"].as_str() {
                Some("left_to_right") => {
                    az0 = -45.0;
                    az1 = 45.0;
                }
                Some("right_to_left") => {
                    az0 = 45.0;
                    az1 = -45.0;
                }
                _ => {}
            }
        }
        TrajectorySpec::Polar {
            start_radius_m: number(t, "start_radius_m", None)?,
            end_radius_m: number(t, "end_radius_m", None)?,
            azimuth_start_deg: az0,
            azimuth_end_deg: az1,
            elevation_deg: number(t, "elevation_deg", Some(0.0))?,
            pre_hold_s: pre,
            movement_duration_s: movement,
        }
    };
    // Query endpoints at a positive duration even for a fixed-source design.
    let mut geometry = trajectory.clone();
    set_motion_timing(&mut geometry, 0.0, 1.0);
    let start = geometry.position_at(0.0);
    let end = geometry.position_at(1.0);
    let Some(c) = controls else {
        return finalize_motion(trajectory, start, end, pre, movement, post);
    };
    if !c.is_object() {
        return Err(error(
            "invalid_trajectory_controls",
            "trajectory_controls",
            "Trajectory controls must be an object.",
        ));
    }
    let pre = number(c, "start_hold_s", Some(pre))?;
    let post = number(c, "end_hold_s", Some(post))?;
    let movement = number(c, "movement_duration_s", Some(movement))?;
    let controlled = |prefix: &str, point: Position| -> Result<Position, CapabilityError> {
        let r = number(
            c,
            &format!("{prefix}_distance_cm"),
            Some(radius(point) * 100.0),
        )? / 100.0;
        let az = number(c, &format!("{prefix}_rotation_deg"), Some(azimuth(point)))?.to_radians();
        let z = number(c, &format!("{prefix}_height_cm"), Some(point.z_m * 100.0))? / 100.0;
        if r <= 0.0 || r > 100.0 || z.abs() > r {
            return Err(error(
                "invalid_trajectory_endpoint",
                "trajectory_controls",
                "Endpoint height must fit within its positive source radius.",
            ));
        }
        let horizontal = (r * r - z * z).max(0.0).sqrt();
        Ok(Position {
            x_m: horizontal * az.sin(),
            y_m: horizontal * az.cos(),
            z_m: z,
        })
    };
    let new_start = controlled("start", start)?;
    let new_end = controlled("end", end)?;
    // Existing UI controls round coordinates to 4 decimal cm/degrees. A
    // read/submit cycle must not turn a saved polar arc into its chord.
    let unchanged = distance(start, new_start) < 0.0002 && distance(end, new_end) < 0.0002;
    let requested_mode = c
        .get("coordinate_mode")
        .and_then(Value::as_str)
        .unwrap_or(if unchanged { mode } else { "cartesian" });
    let mut mapped=match requested_mode {
        "polar" if unchanged=>trajectory,
        "polar"=>return Err(error("polar_edit_requires_explicit_design","trajectory_controls.coordinate_mode","Edit polar radius, unwrapped angles and elevation in the design; Cartesian endpoint controls cannot determine an arc.")),
        "cartesian"=>TrajectorySpec::Linear{start:new_start,end:new_end,pre_hold_s:pre,movement_duration_s:movement},
        _=>return Err(error("unsupported_trajectory_mode","trajectory_controls.coordinate_mode","Choose polar or Cartesian coordinates.")),
    };
    set_motion_timing(&mut mapped, pre, movement);
    finalize_motion(
        mapped,
        if unchanged { start } else { new_start },
        if unchanged { end } else { new_end },
        pre,
        movement,
        post,
    )
}

fn set_motion_timing(t: &mut TrajectorySpec, pre: f64, movement: f64) {
    match t {
        TrajectorySpec::Linear {
            pre_hold_s,
            movement_duration_s,
            ..
        }
        | TrajectorySpec::Polar {
            pre_hold_s,
            movement_duration_s,
            ..
        } => {
            *pre_hold_s = pre;
            *movement_duration_s = movement;
        }
        _ => {}
    }
}
fn finalize_motion(
    t: TrajectorySpec,
    start: Position,
    end: Position,
    pre: f64,
    movement: f64,
    post: f64,
) -> Result<(TrajectorySpec, f64, f64, f64), CapabilityError> {
    if pre < 0.0
        || post < 0.0
        || movement < 0.0
        || pre + movement + post <= 0.0
        || pre + movement + post > 60.0
    {
        return Err(error(
            "invalid_trajectory_timing",
            "trajectory_controls",
            "Nonnegative holds and movement must total more than zero and at most 60 seconds.",
        ));
    }
    if movement == 0.0 {
        if distance(start, end) > 1e-9 {
            return Err(error(
                "zero_duration_motion",
                "design.trajectory",
                "Distinct endpoints require a positive movement duration.",
            ));
        }
        return Ok((
            TrajectorySpec::Fixed { position: start },
            pre,
            movement,
            post,
        ));
    }
    Ok((t, pre, movement, post))
}
fn radius(p: Position) -> f64 {
    (p.x_m * p.x_m + p.y_m * p.y_m + p.z_m * p.z_m).sqrt()
}
fn azimuth(p: Position) -> f64 {
    p.x_m.atan2(p.y_m).to_degrees()
}
fn distance(a: Position, b: Position) -> f64 {
    radius(Position {
        x_m: a.x_m - b.x_m,
        y_m: a.y_m - b.y_m,
        z_m: a.z_m - b.z_m,
    })
}
fn trajectory_snapshot(
    request: &GenerationRequest,
    label: &str,
    kind: &str,
    source: &Value,
    pre: f64,
    movement: f64,
    post: f64,
) -> Value {
    let start = request.trajectory.position_at(0.0);
    let end = request.trajectory.position_at(request.duration_s);
    // Snapshot declares the mapping and exact kernel trajectory. path_length_m
    // remains the endpoint chord used by the existing control UI, not an arc
    // length claim. Request timing is separately authoritative.
    let mode = if matches!(request.trajectory, TrajectorySpec::Polar { .. }) {
        "polar"
    } else {
        "cartesian"
    };
    json!({"schema":"pps-stimulus-trajectory.v1","label":label,"source_kind":kind,"noise_type":source.get("noise_type").and_then(Value::as_str).unwrap_or("custom_audio"),
        "start_distance_cm":radius(start)*100.0,"end_distance_cm":radius(end)*100.0,"start_rotation_deg":azimuth(start),"end_rotation_deg":azimuth(end),
        "start_height_cm":start.z_m*100.0,"end_height_cm":end.z_m*100.0,"movement_duration_s":movement,"start_hold_s":pre,"end_hold_s":post,
        "path_length_m":distance(start,end),"coordinate_mode":mode,"path_direction":"custom","start":start,"end":end,"native_trajectory":request.trajectory})
}

/// Enriches one staged stereo ingredient after its bytes and DSP results exist.
/// This returns metadata only. The host atomically publishes it at the captured
/// design revision after checking cancellation and approved-plan locks.
pub fn generated_ingredient_entry(
    plan: &IngredientGenerationPlan,
    relative_asset_path: &str,
    wav_bytes: &[u8],
    stimulus: &GeneratedStimulus,
    renderer_report: &Value,
    cancelled: &AtomicBool,
) -> Result<GeneratedIngredientEntry, GenerationError> {
    check_cancelled(cancelled)?;
    if relative_asset_path.is_empty()
        || relative_asset_path.len() > 1024
        || relative_asset_path.contains(['\\', ':'])
        || relative_asset_path
            .split('/')
            .any(|p| p.is_empty() || p == "." || p == "..")
    {
        return Err(GenerationError::Invalid("ingredient_relative_path"));
    }
    let frames = validate(&plan.request)?;
    if wav_bytes.len() > frames * 8 + 4096
        || stimulus.sample_rate_hz != plan.request.sample_rate_hz
        || stimulus.interleaved_pcm.len() != frames * 3
        || stimulus.source_qc.frames != frames
        || stimulus.source_qc.seed != plan.request.seed
        || stimulus.source_qc.source_algorithm != plan.request.source_algorithm
        || stimulus.level_qc.physical_spl_qualified
    {
        return Err(GenerationError::Invalid("ingredient_evidence_mismatch"));
    }
    let pcm = read_stereo_wav(
        std::io::Cursor::new(wav_bytes),
        plan.request.sample_rate_hz,
        frames,
        cancelled,
    )?;
    for (index, (actual, expected)) in pcm
        .chunks_exact(2)
        .zip(stimulus.interleaved_pcm.chunks_exact(3))
        .enumerate()
    {
        if index % 4096 == 0 {
            check_cancelled(cancelled)?;
        }
        if actual != &expected[..2] || expected[2] != 0.0 {
            return Err(GenerationError::Invalid("ingredient_pcm_mismatch"));
        }
    }
    if renderer_report["schema"] != "pps-3dti-spatialized.v2"
        || renderer_report["frames"] != frames
        || renderer_report["channels"] != 2
        || renderer_report["sample_rate_hz"] != plan.request.sample_rate_hz
        || renderer_report["source_algorithm"] != plan.request.source_algorithm
        || renderer_report["physical_spl_qualified"] != false
        || renderer_report["spatialization"]["normalization"] != "none"
        || renderer_report["spatialization"]["distance_attenuation"]
            != plan.renderer.distance_attenuation
        || renderer_report["spatialization"]["near_field"] != plan.renderer.near_field
        || renderer_report["spatialization"]["propagation_delay"] != plan.renderer.propagation_delay
        || renderer_report["spatialization"]["head_radius_m"] != plan.renderer.head_radius_m
        || renderer_report["spatialization"]["far_distance_filter"] != false
        || renderer_report["spatialization"]["output_channels"] != 2
        || renderer_report["motion"]
            != serde_json::to_value(&plan.request.trajectory)
                .map_err(|_| GenerationError::Invalid("trajectory_serialization"))?
        || !renderer_report["hrtf_sha256"]
            .as_str()
            .is_some_and(valid_sha)
    {
        return Err(GenerationError::Invalid("renderer_evidence_mismatch"));
    }
    let sha = format!("{:x}", Sha256::digest(wav_bytes));
    let mut source = plan.source.clone();
    source[if plan.source_kind == "generated_noise" {
        "prebaked_path"
    } else {
        "path"
    }] = json!(relative_asset_path);
    source["trajectory_snapshot"] = plan.trajectory_snapshot.clone();
    source["display_color_hex"] = json!(plan.display_color_hex);
    let duration = frames as f64 / f64::from(plan.request.sample_rate_hz);
    let asset = json!({"label":plan.source_label,"descriptor":plan.source_label,"source_kind":plan.source_kind,"motion_mode":"looming","path":relative_asset_path,
        "duration_ms":(duration*1000.0).round_ties_even() as u64,"duration_s":duration,"sample_rate":plan.request.sample_rate_hz,"channels":2,"frames":frames,"sha256":sha,
        "trajectory_snapshot":plan.trajectory_snapshot,"provenance":{"schema":"pps-native-ingredient.v1","generator_schema":REQUEST_SCHEMA,"qualification":plan.qualification,
            "numpy_seed_compatible":false,"physical_spl_qualified":false,"design_sha256":plan.design_sha256,"source_qc":stimulus.source_qc,"level_qc":stimulus.level_qc,
            "renderer":renderer_report,"loudness_policy":plan.loudness_policy,"display_color_hex":plan.display_color_hex,"action":plan.action,"original_label":plan.original_label}});
    check_cancelled(cancelled)?;
    Ok(GeneratedIngredientEntry {
        source,
        asset,
        qualification: plan.qualification,
    })
}

fn source_profile(
    id: &str,
    parameters: &Value,
    movement: f64,
    duration: f64,
) -> Result<(SourceProfile, Value), CapabilityError> {
    if id == "continuous_noise" {
        if !parameters.is_null() && !parameters.is_object() {
            return Err(error(
                "invalid_source_parameters",
                "bake_recipe.source_profile_parameters",
                "Source parameters must be an object.",
            ));
        }
        if parameters.as_object().is_some_and(|p| !p.is_empty()) {
            return Err(error(
                "unsupported_source_parameters",
                "bake_recipe.source_profile_parameters",
                "Continuous source parameters must be empty.",
            ));
        }
        return Ok((SourceProfile::Continuous, json!({})));
    }
    if id != "dynaspace_gaussian_burst_train" {
        return Err(error(
            "unsupported_source_profile",
            "bake_recipe.source_profile",
            "The selected source profile has no native implementation.",
        ));
    }
    if let Some(object) = parameters.as_object() {
        let known = [
            "burst_count_mode",
            "burst_duration_s",
            "rise_fall_s",
            "target_period_s",
            "onset_s",
            "active_window_s",
            "active_window_source",
            "spacing_policy",
            "standard_basis",
        ];
        if object.keys().any(|k| !known.contains(&k.as_str())) {
            return Err(error("unsupported_burst_policy","bake_recipe.source_profile_parameters","Fixed counts, overlap and legacy truncation need an explicit supported source policy."));
        }
    } else if !parameters.is_null() {
        return Err(error(
            "invalid_source_parameters",
            "bake_recipe.source_profile_parameters",
            "Source parameters must be an object.",
        ));
    }
    for (field, expected) in [
        ("burst_count_mode", "duration_derived"),
        ("spacing_policy", "symmetric_fit"),
        ("active_window_source", "trajectory_movement_duration"),
    ] {
        if parameters
            .get(field)
            .and_then(Value::as_str)
            .is_some_and(|value| value != expected)
        {
            return Err(error(
                "unsupported_burst_policy",
                format!("bake_recipe.source_profile_parameters.{field}"),
                "The requested burst scheduling policy is not implemented.",
            ));
        }
    }
    let onset = number(parameters, "onset_s", Some(0.3))?;
    let active = number(parameters, "active_window_s", Some(movement))?;
    let burst = number(parameters, "burst_duration_s", Some(0.03))?;
    let edge = number(parameters, "rise_fall_s", Some(0.01))?;
    let period = number(parameters, "target_period_s", Some(0.095))?;
    if onset < 0.0
        || active < burst
        || burst < 0.001
        || onset + active > duration
        || edge < 0.0
        || edge > burst / 2.0
        || period < burst
    {
        return Err(error(
            "invalid_burst_timing",
            "bake_recipe.source_profile_parameters",
            "Burst timing must fit completely without overlap or implicit truncation.",
        ));
    }
    Ok((
        SourceProfile::GaussianBurstTrain {
            onset_s: onset,
            active_window_s: active,
            burst_duration_s: burst,
            rise_fall_s: edge,
            target_period_s: period,
        },
        json!({"burst_count_mode":"duration_derived","burst_duration_s":burst,"rise_fall_s":edge,"target_period_s":period,"onset_s":onset,
            "active_window_s":active,"active_window_source":"trajectory_movement_duration","spacing_policy":"symmetric_fit"}),
    ))
}

fn level_policy(
    design: &Value,
    recipe: &Value,
    pre: f64,
    movement: f64,
) -> Result<(LevelPolicy, bool), CapabilityError> {
    let policy = recipe
        .get("loudness_policy")
        .or_else(|| design["study_profile_reference_parameters"].get("loudness_policy"))
        .ok_or_else(|| {
            error(
                "level_policy_required",
                "bake_recipe.loudness_policy",
                "Choose an explicit digital preservation or calibrated ramp policy.",
            )
        })?;
    if policy["kind"] == "preserve" {
        let level = serde_json::from_value::<LevelPolicy>(policy.clone()).map_err(|_| {
            error(
                "invalid_level_policy",
                "bake_recipe.loudness_policy",
                "Invalid preservation policy.",
            )
        })?;
        return Ok((
            level,
            design["trajectory"]["use_inverse_square"]
                .as_bool()
                .unwrap_or(false),
        ));
    }
    if policy["schema"] != "pps-loudness-policy.v1"
        || policy["movement_ramp_shape"] != "linear_db"
        || policy["hold_level_policy"] != "constant_start_and_endpoint"
    {
        return Err(error(
            "unsupported_level_policy",
            "bake_recipe.loudness_policy",
            "Only the declared linear-dB ramp and endpoint holds are supported.",
        ));
    }
    if policy["calibration_window"] != "final_500ms_active_movement_excluding_padding" {
        return Err(error(
            "unsupported_calibration_window",
            "bake_recipe.loudness_policy.calibration_window",
            "Only a final active-movement calibration window is implemented.",
        ));
    }
    let mode = text(policy, "mode")?;
    if mode == "measured_spl"
        || policy["calibration_status"] == "measured"
        || policy["calibration_mode"] == "measured_required"
    {
        return Err(error("measured_calibration_receipt_required","bake_recipe.loudness_policy","A measured SPL claim requires a native-verified calibration receipt; text metadata is insufficient."));
    }
    if !["estimated_spl", "digital_dbfs"].contains(&mode) {
        return Err(error(
            "unsupported_level_mode",
            "bake_recipe.loudness_policy.mode",
            "Choose estimated SPL or explicit digital dBFS.",
        ));
    }
    // normalize_loudness_policy supplies this value when the existing HTML
    // payload omits it. An explicitly conflicting value remains an error.
    if policy
        .get("distance_gain_policy")
        .is_some_and(|value| value != "disable_direct_path_gain_for_calibrated_loudness")
    {
        return Err(error(
            "conflicting_distance_gain",
            "bake_recipe.loudness_policy.distance_gain_policy",
            "Calibrated ramps require direct-path distance gain to be disabled.",
        ));
    }
    let (start, end) = if mode == "digital_dbfs" {
        (
            number(policy, "start_target_rms_dbfs", None)?,
            number(policy, "end_target_rms_dbfs", None)?,
        )
    } else {
        let full_scale = number(policy, "estimated_full_scale_spl_db", None)?;
        if !(80.0..=130.0).contains(&full_scale) {
            return Err(error(
                "invalid_spl_estimate",
                "bake_recipe.loudness_policy.estimated_full_scale_spl_db",
                "The full-scale estimate is outside the declared calibration range.",
            ));
        }
        (
            number(policy, "start_spl_db", None)? - full_scale,
            number(policy, "end_spl_db", None)? - full_scale,
        )
    };
    let window = number(policy, "calibration_window_s", None)?;
    if !(0.05..=2.0).contains(&window) {
        return Err(error(
            "invalid_calibration_window",
            "bake_recipe.loudness_policy.calibration_window_s",
            "Use the declared 0.05–2 s active calibration window.",
        ));
    }
    Ok((
        LevelPolicy::LinearDbRamp {
            start_rms_dbfs: start,
            end_rms_dbfs: end,
            pre_hold_s: pre,
            movement_duration_s: movement,
            calibration_window_s: window.min(movement),
            peak_ceiling_dbfs: number(policy, "audio_peak_ceiling_dbfs", None)?,
        },
        false,
    ))
}

fn text<'a>(value: &'a Value, key: &str) -> Result<&'a str, CapabilityError> {
    value
        .get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| error("missing_field", key, "A required string field is missing."))
}
fn boolean(value: &Value, key: &str, default: bool) -> Result<bool, CapabilityError> {
    match value.get(key) {
        None => Ok(default),
        Some(v) => v.as_bool().ok_or_else(|| {
            error(
                "invalid_boolean",
                key,
                "A Boolean policy value is required.",
            )
        }),
    }
}
fn number(value: &Value, key: &str, default: Option<f64>) -> Result<f64, CapabilityError> {
    let number = match value.get(key) {
        Some(v) => v.as_f64(),
        None => default,
    };
    number
        .filter(|v| v.is_finite())
        .ok_or_else(|| error("invalid_number", key, "A finite numeric value is required."))
}
fn valid_sha(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
fn bound_value(value: &Value, depth: usize, bytes: &mut usize) -> Result<(), CapabilityError> {
    if depth > 32 {
        return Err(error(
            "payload_limit",
            "payload",
            "Generation input exceeds structural limits.",
        ));
    }
    *bytes = bytes.saturating_add(16);
    match value {
        Value::String(s) => *bytes = bytes.saturating_add(s.len()),
        Value::Array(a) => {
            for v in a {
                bound_value(v, depth + 1, bytes)?;
            }
        }
        Value::Object(o) => {
            for (k, v) in o {
                *bytes = bytes.saturating_add(k.len());
                bound_value(v, depth + 1, bytes)?;
            }
        }
        _ => {}
    }
    if *bytes > 2 * 1024 * 1024 {
        return Err(error(
            "payload_limit",
            "payload",
            "Generation input exceeds 2 MiB.",
        ));
    }
    Ok(())
}
