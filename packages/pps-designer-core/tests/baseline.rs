use pps_designer_core::{baseline::*, *};
use serde_json::{json, Value};
use std::{io::Cursor, sync::atomic::AtomicBool};

fn design() -> Value {
    let p: Value = serde_json::from_str(include_str!("fixtures/ingredient_payload.json")).unwrap();
    let mut design = p["design"].clone();
    design["noises"] = json!([{"label":"Pink frontal","noise_type":"pink","source_profile":"dynaspace_gaussian_burst_train","source_profile_parameters":{},"prebaked_path":"existing-moving.wav","gain":0.7,"trajectory_snapshot":{
        "start":{"x_m":0.2,"y_m":1.1,"z_m":0.3},"end":{"x_m":0.2,"y_m":0.3,"z_m":0.1},"movement_duration_s":0.6,"start_hold_s":0.2,"end_hold_s":0.2,"path_length_m":0.8
    }}]);
    design
}
fn opt_in() -> BaselineGenerationOptIn {
    BaselineGenerationOptIn {
        source_algorithm: SOURCE_ALGORITHM.into(),
        accept_non_legacy_source_algorithm: true,
    }
}

fn output(plan: &StationaryBaselineGenerationPlan) -> (Vec<u8>, GeneratedStimulus, Value) {
    let p = &plan.generation;
    let cancel = AtomicBool::new(false);
    let prepared = prepare(&p.request, &cancel).unwrap();
    let stereo = prepared
        .dry_pcm()
        .iter()
        .flat_map(|s| [*s * 0.3, *s * 0.2])
        .collect();
    let generated = compose_spatial_output(prepared, stereo, &cancel).unwrap();
    let mut file = Cursor::new(Vec::new());
    write_ingredient_wav(&mut file, &generated, &cancel).unwrap();
    let report = json!({"schema":"pps-3dti-spatialized.v2","frames":p.request.sample_rate_hz,"channels":2,"sample_rate_hz":p.request.sample_rate_hz,"source_algorithm":SOURCE_ALGORITHM,"physical_spl_qualified":false,"hrtf_sha256":"b".repeat(64),"motion":p.request.trajectory,
        "spatialization":{"normalization":"none","distance_attenuation":p.renderer.distance_attenuation,"near_field":false,"propagation_delay":p.renderer.propagation_delay,"head_radius_m":p.renderer.head_radius_m,"far_distance_filter":false,"output_channels":2}});
    (file.into_inner(), generated, report)
}

#[test]
fn saved_source_start_and_duration_are_fixed_without_reusing_moving_pcm() {
    let design = design();
    let plan = plan_stationary_baseline(&design, "Pink frontal", &opt_in()).unwrap();
    assert_eq!(plan.generation.request.duration_s, 1.0);
    assert_eq!(plan.seed_policy, BASELINE_SEED_POLICY);
    let prepared = prepare(&plan.generation.request, &AtomicBool::new(false)).unwrap();
    for t in [0.0, 0.2, 0.5, 1.0] {
        let p = prepared.position_at(t).unwrap();
        assert_eq!((p.x_m, p.y_m, p.z_m), (0.2, 1.1, 0.3));
    }
    assert!(plan.generation.renderer.distance_attenuation);
    assert_eq!(plan.level_basis, "legacy_absent_policy_digital_peak_0_90");
    assert!(!prepared.source_qc().numpy_seed_compatible);
    assert_eq!(plan.generation.request.seed, 1485064395); // Python SHA256 first-eight-hex oracle.
    let (wav, generated, report) = output(&plan);
    assert!((generated.level_qc.audio_peak_dbfs - 20.0 * 0.9_f64.log10()).abs() < 0.00001);
    let entry = generated_stationary_baseline_entry(
        &plan,
        "native-assets/control.wav",
        &wav,
        &generated,
        &report,
        &AtomicBool::new(false),
    )
    .unwrap();
    let publication = apply_generated_stationary_baseline(&plan, &entry).unwrap();
    assert_eq!(
        publication.design["noises"][0]["prebaked_path"],
        "existing-moving.wav"
    );
    assert_eq!(
        publication.design["noises"][0]["trajectory_snapshot"],
        design["noises"][0]["trajectory_snapshot"]
    );
    assert_eq!(publication.design["noises"][0]["gain"], 0.7);
    assert_eq!(
        publication.design["noises"][0]["native_stationary_baseline_asset"],
        "native-assets/control.wav"
    );
    assert_eq!(publication.asset["role"], "stationary_baseline");
    assert_eq!(
        publication.asset["provenance"]["moving_condition_validation_inherited"],
        false
    );
    assert_eq!(
        publication.asset["provenance"]["perceptual_loudness_matched"],
        false
    );
    assert_eq!(
        publication.asset["provenance"]["level_qc"]["kind"],
        "peak_normalize"
    );
    assert_eq!(publication.design["study_profile_id"], "");
    assert_eq!(
        publication.design["study_profile_reference_parameters"]["customized_from_profile_id"],
        "reference_fixture"
    );
    assert_eq!(publication.invalidate_segments, [3, 4, 5, 6]);
    assert!(publication.invalidate_run_package);
}

#[test]
fn inherited_calibrated_envelope_and_new_rng_opt_in_remain_distinct() {
    let mut design = design();
    let fixture: Value =
        serde_json::from_str(include_str!("fixtures/ingredient_payload.json")).unwrap();
    design["study_profile_reference_parameters"]["loudness_policy"] =
        fixture["bake_recipe"]["loudness_policy"].clone();
    let plan = plan_stationary_baseline(&design, "Pink frontal", &opt_in()).unwrap();
    assert!(!plan.generation.renderer.distance_attenuation);
    assert_eq!(plan.level_basis, "inherited_explicit_loudness_policy");
    let (_, generated, _) = output(&plan);
    assert_eq!(generated.level_qc.kind, "linear_db_ramp");
    assert!(generated.level_qc.target_peak_dbfs.is_none());
    assert!(
        (generated.level_qc.actual_window_rms_dbfs.unwrap()
            - generated.level_qc.target_window_rms_dbfs.unwrap())
        .abs()
            < 0.02
    );
    let mut opt = opt_in();
    opt.accept_non_legacy_source_algorithm = false;
    assert_eq!(
        plan_stationary_baseline(&design, "Pink frontal", &opt)
            .unwrap_err()
            .code,
        "new_source_algorithm_opt_in_required"
    );
    opt.accept_non_legacy_source_algorithm = true;
    opt.source_algorithm = "numpy-legacy".into();
    assert_eq!(
        plan_stationary_baseline(&design, "Pink frontal", &opt)
            .unwrap_err()
            .code,
        "new_source_algorithm_opt_in_required"
    );
    assert!(plan_stationary_baseline(&design, "Missing dry import", &opt_in()).is_err());
    design["noises"][0]["source_profile_parameters"] = json!({"burst_count":32});
    assert_eq!(
        plan_stationary_baseline(&design, "Pink frontal", &opt_in())
            .unwrap_err()
            .code,
        "unsupported_burst_policy"
    );
}
