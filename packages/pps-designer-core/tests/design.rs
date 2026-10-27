use pps_designer_core::{design::*, *};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{io::Cursor, sync::atomic::AtomicBool};

fn payload() -> Value {
    serde_json::from_str(include_str!("fixtures/ingredient_payload.json")).unwrap()
}
fn opt_in() -> GenerationOptIn {
    GenerationOptIn {
        source_algorithm: SOURCE_ALGORITHM.into(),
        accept_non_legacy_source_algorithm: true,
        seed: 123,
    }
}
fn contract_output(plan: &IngredientGenerationPlan) -> (Vec<u8>, GeneratedStimulus, Value) {
    let cancel = AtomicBool::new(false);
    let prepared = prepare(&plan.request, &cancel).unwrap();
    let stereo: Vec<f32> = prepared
        .dry_pcm()
        .iter()
        .flat_map(|sample| [*sample, *sample])
        .collect();
    let generated = compose_spatial_output(prepared, stereo, &cancel).unwrap();
    let mut wav = Cursor::new(Vec::new());
    write_ingredient_wav(&mut wav, &generated, &cancel).unwrap();
    // A contract fixture, not spatializer qualification. Native integration
    // separately checks the real executable's report and actual rendered PCM.
    let report = json!({"schema":"pps-3dti-spatialized.v2","frames":8000,"channels":2,"sample_rate_hz":8000,
        "source_algorithm":SOURCE_ALGORITHM,"physical_spl_qualified":false,"hrtf_sha256":"a".repeat(64),
        "spatialization":{"normalization":"none","distance_attenuation":plan.renderer.distance_attenuation,"near_field":false,
            "propagation_delay":plan.renderer.propagation_delay,"head_radius_m":plan.renderer.head_radius_m,"far_distance_filter":false,"output_channels":2},
        "motion":plan.request.trajectory});
    (wav.into_inner(), generated, report)
}

#[test]
fn full_payload_preserves_saved_polar_arc_and_explicit_source_algorithm() {
    let p = payload();
    let plan = plan_ingredient_generation(&p, &opt_in()).unwrap();
    assert!(matches!(
        plan.request.trajectory,
        TrajectorySpec::Polar { .. }
    ));
    let prepared = prepare(&plan.request, &AtomicBool::new(false)).unwrap();
    assert!((prepared.position_at(0.5).unwrap().y_m - 2.0).abs() < 1e-10);
    assert!((prepared.position_at(0.0).unwrap().y_m + 1.969615506).abs() < 1e-8);
    assert_eq!(prepared.dry_pcm().len(), 8000);
    assert_eq!(plan.request.tactile.len(), 0);
    assert_eq!(plan.trajectory_snapshot["coordinate_mode"], "polar");
    assert!(!plan.renderer.distance_attenuation);
    assert!(plan.renderer.propagation_delay);
    assert_eq!(
        plan.qualification,
        "customized_native_generation_unqualified"
    );
    let mut opt = opt_in();
    opt.accept_non_legacy_source_algorithm = false;
    assert_eq!(
        plan_ingredient_generation(&p, &opt).unwrap_err().code,
        "new_source_algorithm_opt_in_required"
    );
    opt.accept_non_legacy_source_algorithm = true;
    opt.source_algorithm = "numpy-legacy".into();
    assert_eq!(
        plan_ingredient_generation(&p, &opt).unwrap_err().code,
        "new_source_algorithm_opt_in_required"
    );
}

#[test]
fn endpoint_edits_and_pending_timing_map_without_stale_saved_geometry() {
    let mut p = payload();
    p["trajectory_controls"]["start_rotation_deg"] = json!(-45.0);
    p["trajectory_controls"]["end_rotation_deg"] = json!(45.0);
    p["trajectory_controls"]["movement_duration_s"] = json!(0.7);
    let plan = plan_ingredient_generation(&p, &opt_in()).unwrap();
    assert!(matches!(
        plan.request.trajectory,
        TrajectorySpec::Linear { .. }
    ));
    let prepared = prepare(&plan.request, &AtomicBool::new(false)).unwrap();
    let point = prepared.position_at(0.55).unwrap();
    assert!(point.x_m.abs() < 1e-10);
    assert!((point.y_m - 2.0_f64.sqrt()).abs() < 1e-10);
    assert!((plan.request.duration_s - 1.1).abs() < 1e-12);
    p["trajectory_controls"]["coordinate_mode"] = json!("polar");
    assert_eq!(
        plan_ingredient_generation(&p, &opt_in()).unwrap_err().code,
        "polar_edit_requires_explicit_design"
    );
}

#[test]
fn level_modes_keep_estimates_separate_from_measured_claims_and_actual_rms_matches() {
    let mut p = payload();
    let plan = plan_ingredient_generation(&p, &opt_in()).unwrap();
    match plan.request.level {
        LevelPolicy::LinearDbRamp {
            start_rms_dbfs,
            end_rms_dbfs,
            ..
        } => {
            assert!((start_rms_dbfs + 69.2).abs() < 1e-10);
            assert!((end_rms_dbfs + 49.2).abs() < 1e-10);
        }
        _ => panic!("expected ramp"),
    }
    let (_, stimulus, _) = contract_output(&plan);
    assert!(
        (stimulus.level_qc.actual_window_rms_dbfs.unwrap()
            - stimulus.level_qc.target_window_rms_dbfs.unwrap())
        .abs()
            < 0.02
    );
    assert!(!stimulus.level_qc.physical_spl_qualified);
    p["bake_recipe"]["loudness_policy"]["mode"] = json!("digital_dbfs");
    p["bake_recipe"]["loudness_policy"]["start_target_rms_dbfs"] = json!(-55.0);
    p["bake_recipe"]["loudness_policy"]["end_target_rms_dbfs"] = json!(-40.0);
    let plan = plan_ingredient_generation(&p, &opt_in()).unwrap();
    assert!(matches!(
        plan.request.level,
        LevelPolicy::LinearDbRamp {
            start_rms_dbfs: -55.0,
            end_rms_dbfs: -40.0,
            ..
        }
    ));
    p["bake_recipe"]["loudness_policy"]["calibration_status"] = json!("measured");
    assert_eq!(
        plan_ingredient_generation(&p, &opt_in()).unwrap_err().code,
        "measured_calibration_receipt_required"
    );
    p["bake_recipe"]["loudness_policy"] =
        json!({"kind":"preserve","gain_db":-12.0,"peak_ceiling_dbfs":-1.0});
    let plan = plan_ingredient_generation(&p, &opt_in()).unwrap();
    assert!(matches!(
        plan.request.level,
        LevelPolicy::Preserve { gain_db: -12.0, .. }
    ));
    assert!(plan.renderer.distance_attenuation);
}

#[test]
fn unsupported_profiles_renderer_flags_and_bad_collection_types_fail_explicitly() {
    for (path, value, code) in [
        (
            "source_profile",
            json!("legacy_unknown"),
            "unsupported_source_profile",
        ),
        (
            "source_profile_parameters",
            json!({"burst_count":8}),
            "unsupported_burst_policy",
        ),
        ("gain", json!(0.5), "unsupported_recipe_gain"),
        (
            "spatialization",
            json!({"near_field":true}),
            "near_field_ild_unavailable",
        ),
        (
            "spatialization",
            json!({"far_distance_filter":true}),
            "far_distance_filter_unavailable",
        ),
        (
            "spatialization",
            json!({"propagation_delay":"false"}),
            "invalid_boolean",
        ),
    ] {
        let mut p = payload();
        p["bake_recipe"][path] = value;
        assert_eq!(
            plan_ingredient_generation(&p, &opt_in()).unwrap_err().code,
            code
        );
    }
    let mut p = payload();
    p["design"]["noises"] = json!([{"label":"native_burst"}]);
    assert_eq!(
        plan_ingredient_generation(&p, &opt_in()).unwrap_err().code,
        "duplicate_label"
    );
    for key in ["noises", "custom_looming_files", "prestimulus_files"] {
        let mut p = payload();
        p["design"][key] = json!("malformed");
        assert_eq!(
            plan_ingredient_generation(&p, &opt_in()).unwrap_err().code,
            "invalid_source_collection"
        );
    }
    let mut p = payload();
    p["design"]["protocol"] = json!("malformed");
    assert_eq!(
        plan_ingredient_generation(&p, &opt_in()).unwrap_err().code,
        "invalid_protocol"
    );
}

#[test]
fn imported_generation_requires_explicit_verified_raw_source_contract() {
    let mut p = payload();
    p["bake_recipe"]["kind"] = json!("imported_audio");
    p["bake_recipe"]["audio"] = json!({"render_mode":"spatialize","source_input_path":"native-picked-dry-asset", "sha256":"a".repeat(64),"channel_policy":"stereo_mean","length_policy":"trim_or_zero_pad"});
    let plan = plan_ingredient_generation(&p, &opt_in()).unwrap();
    assert_eq!(plan.request.source_algorithm, IMPORT_ALGORITHM);
    assert_eq!(plan.request.seed, 0);
    assert_eq!(
        plan.source_input_reference.as_deref(),
        Some("native-picked-dry-asset")
    );
    // The host separately resolves this reference only from a native asset
    // receipt. A source_input_path string by itself never grants file authority.
    p["bake_recipe"]["audio"]
        .as_object_mut()
        .unwrap()
        .remove("sha256");
    assert!(plan_ingredient_generation(&p, &opt_in()).is_err());
    p["bake_recipe"]["audio"]["render_mode"] = json!("preserve");
    assert_eq!(
        plan_ingredient_generation(&p, &opt_in()).unwrap_err().code,
        "import_requires_spatialize"
    );
}

#[test]
fn publication_checks_actual_bytes_and_preserves_rename_links_without_stale_qualification() {
    let mut p = payload();
    p["design"]["noises"] = json!([{"label":"Old-source","noise_type":"white"}]);
    p["design"]["prestimulus_files"] =
        json!([{"label":"Instruction","target_source_label":"old_source"}]);
    p["design"]["protocol"]["trial_strips"] = json!([{"elements":[{"label":"Old-source","source_label":"old_source","source_labels":["old source","Other"]}]}]);
    p["bake_recipe"]["action"] = json!("remake");
    p["bake_recipe"]["original_label"] = json!("Old-source");
    let plan = plan_ingredient_generation(&p, &opt_in()).unwrap();
    let (wav, generated, report) = contract_output(&plan);
    let cancel = AtomicBool::new(false);
    let entry = generated_ingredient_entry(
        &plan,
        "ingredients/native.wav",
        &wav,
        &generated,
        &report,
        &cancel,
    )
    .unwrap();
    assert_eq!(
        entry.asset()["sha256"],
        format!("{:x}", Sha256::digest(&wav))
    );
    assert_eq!(entry.asset()["channels"], 2);
    assert_eq!(entry.asset()["duration_ms"], 1000);
    let published = apply_generated_ingredient(&plan, &entry).unwrap();
    assert_eq!(published.design["noises"].as_array().unwrap().len(), 1);
    assert_eq!(
        published.design["noises"][0]["prebaked_path"],
        "ingredients/native.wav"
    );
    assert_eq!(
        published.design["protocol"]["trial_strips"][0]["elements"][0]["source_labels"],
        json!(["Native burst", "Other"])
    );
    assert_eq!(
        published.design["prestimulus_files"][0]["target_source_label"],
        "Native burst"
    );
    assert_eq!(published.design["study_profile_id"], "");
    assert_eq!(
        published.design["study_profile_reference_parameters"]["customized_from_profile_id"],
        "reference_fixture"
    );
    assert_eq!(published.invalidate_segments, [2, 3, 4, 5, 6]);
    assert!(published.invalidate_run_package);
    assert_eq!(published.design["trajectory"]["azimuth_start_deg"], 170.0);
    assert_eq!(published.design["trajectory"]["azimuth_end_deg"], -170.0);
    let mut different = opt_in();
    different.seed += 1;
    assert!(apply_generated_ingredient(
        &plan_ingredient_generation(&p, &different).unwrap(),
        &entry
    )
    .is_err());
    let mut corrupt = wav.clone();
    let last = corrupt.len() - 1;
    corrupt[last] ^= 1;
    assert!(generated_ingredient_entry(
        &plan,
        "ingredients/native.wav",
        &corrupt,
        &generated,
        &report,
        &cancel
    )
    .is_err());
    assert!(generated_ingredient_entry(
        &plan,
        "../outside.wav",
        &wav,
        &generated,
        &report,
        &cancel
    )
    .is_err());
    let mut mismatched = report.clone();
    mismatched["motion"]["azimuth_end_deg"] = json!(0.0);
    assert!(generated_ingredient_entry(
        &plan,
        "ingredients/native.wav",
        &wav,
        &generated,
        &mismatched,
        &cancel
    )
    .is_err());
    assert!(generated_ingredient_entry(
        &plan,
        "ingredients/native.wav",
        &wav,
        &generated,
        &report,
        &AtomicBool::new(true)
    )
    .is_err());
}
