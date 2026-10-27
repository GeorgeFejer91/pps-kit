//! Explicit offline native test: no audio device or playback is opened.
use pps_designer_core::design::{
    apply_generated_ingredient, generated_ingredient_entry, plan_ingredient_generation,
    GenerationOptIn,
};
use pps_designer_core::*;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs,
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::atomic::AtomicBool,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

fn input() -> GenerationRequest {
    GenerationRequest {
        schema: REQUEST_SCHEMA.into(),
        source_algorithm: SOURCE_ALGORITHM.into(),
        sample_rate_hz: 44100,
        duration_s: 1.0,
        seed: 123,
        source: SourceSpec::GaussianBurstTrain {
            onset_s: 0.05,
            active_window_s: 0.9,
            burst_duration_s: 0.03,
            rise_fall_s: 0.01,
            target_period_s: 0.095,
        },
        trajectory: TrajectorySpec::Fixed {
            position: Position {
                x_m: 0.0,
                y_m: 1.0,
                z_m: 0.0,
            },
        },
        tactile: vec![TactileCue {
            onset_s: 0.5,
            duration_s: 0.05,
            attack_frequency_hz: 250.0,
            decay_frequency_hz: 150.0,
            peak_amplitude: 0.5,
        }],
        level: LevelPolicy::Preserve {
            gain_db: -12.0,
            peak_ceiling_dbfs: -1.0,
        },
    }
}

fn execute(executable: &Path, directory: &Path, config: &Value, dry: &[u8]) -> bool {
    fs::create_dir_all(directory).unwrap();
    fs::write(
        directory.join("config.json"),
        serde_json::to_vec(config).unwrap(),
    )
    .unwrap();
    fs::write(directory.join("dry.f32"), dry).unwrap();
    let log = fs::File::create(directory.join("native.log")).unwrap();
    let mut command = Command::new(executable);
    command
        .args(["--config"])
        .arg(directory.join("config.json"))
        .arg("--output-dir")
        .arg(directory)
        .arg("--manifest")
        .arg(directory.join("manifest.json"))
        .arg("--qc")
        .arg(directory.join("qc.csv"))
        .stdout(Stdio::from(log.try_clone().unwrap()))
        .stderr(Stdio::from(log));
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    let mut child = command.spawn().unwrap();
    let deadline = Instant::now() + Duration::from_secs(45);
    loop {
        if let Some(status) = child.try_wait().unwrap() {
            return status.success();
        }
        if Instant::now() >= deadline {
            child.kill().unwrap();
            child.wait().unwrap();
            panic!("Native renderer exceeded 45s: {}", directory.display());
        }
        std::thread::sleep(Duration::from_millis(25));
    }
}

fn rendered(directory: &Path) -> Vec<f32> {
    let pcm = read_stereo_wav(
        fs::File::open(directory.join("stereo.wav")).unwrap(),
        44100,
        44100,
        &AtomicBool::new(false),
    )
    .unwrap();
    let report: Value =
        serde_json::from_slice(&fs::read(directory.join("manifest.json")).unwrap()).unwrap();
    let mut digest = Sha256::new();
    for sample in &pcm {
        digest.update(sample.to_le_bytes());
    }
    assert_eq!(
        report["stereo_pcm_sha256"],
        format!("{:x}", digest.finalize())
    );
    assert_eq!(report["spatialization"]["normalization"], "none");
    assert_eq!(report["channels"], 2);
    assert_eq!(report["physical_spl_qualified"], false);
    assert!(
        pcm.iter().any(|v| v.abs() > 0.001),
        "native output is silent"
    );
    pcm
}

fn rms(pcm: &[f32]) -> f64 {
    (pcm.iter().map(|v| f64::from(*v).powi(2)).sum::<f64>() / pcm.len() as f64).sqrt()
}
fn ratio_db(a: &[f32], b: &[f32]) -> f64 {
    20.0 * (rms(a) / rms(b)).log10()
}

#[test]
#[ignore = "requires PPS_TEST_RENDERER pointing at the locally built Windows 3DTI executable"]
fn native_imported_dry_source_preserves_its_tone_and_records_import_algorithm() {
    let executable =
        PathBuf::from(std::env::var_os("PPS_TEST_RENDERER").expect("PPS_TEST_RENDERER required"));
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap();
    let directory = root.join("artifacts").join(format!(
        "native-import-test-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_millis()
    ));
    let tone: Vec<f32> = (0..44100)
        .map(|i| (0.1 * (2.0 * std::f64::consts::PI * 440.0 * i as f64 / 44100.0).sin()) as f32)
        .collect();
    let mut file = std::io::Cursor::new(Vec::new());
    write_mono_wav(&mut file, &tone, 44100, &AtomicBool::new(false)).unwrap();
    let bytes = file.into_inner();
    let mut request = input();
    request.seed = 0;
    request.source_algorithm = IMPORT_ALGORITHM.into();
    request.source = SourceSpec::ImportedWav {
        sha256: format!("{:x}", Sha256::digest(&bytes)),
        channel_policy: ImportChannelPolicy::Mono,
        length_policy: ImportLengthPolicy::Exact,
    };
    let prepared = prepare_imported_wav(&request, &bytes, &AtomicBool::new(false)).unwrap();
    assert_eq!(prepared.dry_pcm(), tone);
    let options=SpatializerOptions {hrtf_path:root.join("packages/pps-resources/assets/0. Head-Related Impulse Response (HRIR) model/FABIAN_HRIR_measured_HATO_0.sofa").to_str().unwrap().into(),
        hrtf_format:HrtfFormat::Sofa,head_radius_m:0.09,distance_attenuation:false,near_field:false,propagation_delay:false};
    let mut dry = Vec::new();
    let config =
        write_spatializer_input(&prepared, &mut dry, &options, &AtomicBool::new(false)).unwrap();
    assert!(execute(
        &executable,
        &directory,
        &serde_json::to_value(config).unwrap(),
        &dry
    ));
    let stereo = rendered(&directory);
    let energy = |hz: f64| {
        let mut real = 0.0;
        let mut imaginary = 0.0;
        for (i, frame) in stereo.chunks_exact(2).enumerate().skip(22050) {
            let phase = 2.0 * std::f64::consts::PI * hz * i as f64 / 44100.0;
            real += f64::from(frame[0]) * phase.cos();
            imaginary += f64::from(frame[0]) * phase.sin();
        }
        real.hypot(imaginary)
    };
    assert!(
        energy(440.0) > 10.0 * energy(880.0),
        "imported tone was replaced or altered"
    );
    let report: Value =
        serde_json::from_slice(&fs::read(directory.join("manifest.json")).unwrap()).unwrap();
    assert_eq!(report["source_algorithm"], IMPORT_ALGORITHM);
    eprintln!("Native imported-source evidence: {}", directory.display());
}

#[test]
#[ignore = "requires PPS_TEST_RENDERER pointing at the locally built Windows 3DTI executable"]
fn native_designer_payload_produces_verified_stereo_ingredient_and_custom_design() {
    let executable =
        PathBuf::from(std::env::var_os("PPS_TEST_RENDERER").expect("PPS_TEST_RENDERER required"));
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap();
    let directory = root.join("artifacts").join(format!(
        "native-ingredient-test-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_millis()
    ));
    let mut payload: Value =
        serde_json::from_str(include_str!("fixtures/ingredient_payload.json")).unwrap();
    payload["design"]["trajectory"]["sample_rate"] = json!(44100);
    let plan = plan_ingredient_generation(
        &payload,
        &GenerationOptIn {
            source_algorithm: SOURCE_ALGORITHM.into(),
            accept_non_legacy_source_algorithm: true,
            seed: 123,
        },
    )
    .unwrap();
    let cancel = AtomicBool::new(false);
    let prepared = prepare(&plan.request, &cancel).unwrap();
    let options=SpatializerOptions{hrtf_path:root.join("packages/pps-resources/assets/0. Head-Related Impulse Response (HRIR) model/FABIAN_HRIR_measured_HATO_0.sofa").to_str().unwrap().into(),
        hrtf_format:HrtfFormat::Sofa,head_radius_m:plan.renderer.head_radius_m,distance_attenuation:plan.renderer.distance_attenuation,
        near_field:plan.renderer.near_field,propagation_delay:plan.renderer.propagation_delay};
    let mut dry = Vec::new();
    let config = write_spatializer_input(&prepared, &mut dry, &options, &cancel).unwrap();
    assert!(execute(
        &executable,
        &directory,
        &serde_json::to_value(config).unwrap(),
        &dry
    ));
    let stereo = rendered(&directory);
    let generated = compose_spatial_output(prepared, stereo, &cancel).unwrap();
    assert!(
        (generated.level_qc.actual_window_rms_dbfs.unwrap()
            - generated.level_qc.target_window_rms_dbfs.unwrap())
        .abs()
            < 0.02
    );
    let mut wav = std::io::Cursor::new(Vec::new());
    write_ingredient_wav(&mut wav, &generated, &cancel).unwrap();
    let bytes = wav.into_inner();
    fs::write(directory.join("ingredient.wav"), &bytes).unwrap();
    let report: Value =
        serde_json::from_slice(&fs::read(directory.join("manifest.json")).unwrap()).unwrap();
    let entry = generated_ingredient_entry(
        &plan,
        "ingredients/native.wav",
        &bytes,
        &generated,
        &report,
        &cancel,
    )
    .unwrap();
    let publication = apply_generated_ingredient(&plan, &entry).unwrap();
    assert_eq!(publication.design["noises"][0]["label"], "Native burst");
    assert_eq!(entry.asset()["channels"], 2);
    assert_eq!(entry.asset()["frames"], 44100);
    assert_eq!(
        publication.design["study_profile_reference_parameters"]["native_generation_qualification"],
        "customized_native_generation_unqualified"
    );
    fs::write(
        directory.join("publication.json"),
        serde_json::to_vec_pretty(&publication).unwrap(),
    )
    .unwrap();
    eprintln!("Native ingredient evidence: {}", directory.display());
}

#[test]
#[ignore = "requires PPS_TEST_RENDERER pointing at the locally built Windows 3DTI executable"]
fn native_prepared_pcm_controls_and_final_waveform_are_measured() {
    let executable =
        PathBuf::from(std::env::var_os("PPS_TEST_RENDERER").expect("PPS_TEST_RENDERER required"));
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap();
    let directory = root.join("artifacts").join(format!(
        "native-generation-test-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_millis()
    ));
    let options = SpatializerOptions {
        hrtf_path: root.join("packages/pps-resources/assets/0. Head-Related Impulse Response (HRIR) model/FABIAN_HRIR_measured_HATO_0.sofa").to_str().unwrap().into(),
        hrtf_format: HrtfFormat::Sofa, head_radius_m: 0.09, distance_attenuation: false, near_field: false, propagation_delay: false };
    let prepared = prepare(&input(), &AtomicBool::new(false)).unwrap();
    let mut dry = Vec::new();
    let config =
        write_spatializer_input(&prepared, &mut dry, &options, &AtomicBool::new(false)).unwrap();
    let config = serde_json::to_value(config).unwrap();
    assert!(execute(
        &executable,
        &directory.join("reference"),
        &config,
        &dry
    ));
    let reference = rendered(&directory.join("reference"));

    let mut half = Vec::with_capacity(dry.len());
    for sample in prepared.dry_pcm() {
        half.extend_from_slice(&(sample * 0.5).to_le_bytes());
    }
    let mut modified = config.clone();
    modified["dry_source"]["sha256"] = format!("{:x}", Sha256::digest(&half)).into();
    assert!(execute(
        &executable,
        &directory.join("half"),
        &modified,
        &half
    ));
    let half_output = rendered(&directory.join("half"));
    assert!(
        (ratio_db(&half_output, &reference) + 6.020599913).abs() < 0.02,
        "hidden normalization or regenerated input"
    );

    modified = config.clone();
    modified["trajectory"]["position"]["y_m"] = 2.0.into();
    assert!(execute(
        &executable,
        &directory.join("far-no-attenuation"),
        &modified,
        &dry
    ));
    let far = rendered(&directory.join("far-no-attenuation"));
    // HRTF ear projection changes with distance even with the gain controller
    // disabled. Compare that controller at identical geometry below.

    modified["spatialization"]["distance_attenuation"] = true.into();
    assert!(execute(
        &executable,
        &directory.join("far-with-attenuation"),
        &modified,
        &dry
    ));
    let attenuated = rendered(&directory.join("far-with-attenuation"));
    assert!(
        (ratio_db(&attenuated[44100..], &far[44100..]) - 20.0 * (1.95_f64 / 2.0).log10()).abs()
            < 0.02,
        "distance attenuation law drifted"
    );

    modified = config.clone();
    modified["trajectory"] = json!({"kind":"linear", "start":{"x_m":-1.0,"y_m":1.0,"z_m":0.0},
        "end":{"x_m":1.0,"y_m":1.0,"z_m":0.0},"pre_hold_s":0.1,"movement_duration_s":0.8});
    assert!(execute(
        &executable,
        &directory.join("moving"),
        &modified,
        &dry
    ));
    let moving = rendered(&directory.join("moving"));
    let left_first: Vec<_> = moving[..22050].chunks_exact(2).map(|v| v[0]).collect();
    let right_first: Vec<_> = moving[..22050].chunks_exact(2).map(|v| v[1]).collect();
    let left_last: Vec<_> = moving[66150..].chunks_exact(2).map(|v| v[0]).collect();
    let right_last: Vec<_> = moving[66150..].chunks_exact(2).map(|v| v[1]).collect();
    assert!(ratio_db(&left_first, &right_first) > 0.5);
    assert!(ratio_db(&left_last, &right_last) < -0.5);
    assert!(
        rms(&moving
            .iter()
            .zip(&reference)
            .map(|(a, b)| a - b)
            .collect::<Vec<_>>())
            > 0.005,
        "motion was ignored"
    );
    modified["trajectory"] = json!({"kind":"polar", "start_radius_m":2.0_f64.sqrt(), "end_radius_m":2.0_f64.sqrt(),
        "azimuth_start_deg":-45.0,"azimuth_end_deg":45.0,"elevation_deg":0.0,"pre_hold_s":0.1,"movement_duration_s":0.8});
    assert!(execute(
        &executable,
        &directory.join("polar"),
        &modified,
        &dry
    ));
    let polar = rendered(&directory.join("polar"));
    assert!(
        rms(&polar
            .iter()
            .zip(&moving)
            .map(|(a, b)| a - b)
            .collect::<Vec<_>>())
            > 0.001,
        "polar arc was silently replaced with a Cartesian chord"
    );

    modified = config.clone();
    modified["spatialization"]["propagation_delay"] = true.into();
    assert!(execute(
        &executable,
        &directory.join("propagation"),
        &modified,
        &dry
    ));
    let propagation = rendered(&directory.join("propagation"));
    let first_frame = |pcm: &[f32]| {
        pcm.chunks_exact(2)
            .position(|v| v[0].abs().max(v[1].abs()) > 1e-5)
            .unwrap()
    };
    let delay = first_frame(&propagation) - first_frame(&reference);
    assert!(
        (100..160).contains(&delay),
        "unexpected 1m propagation delay: {delay} frames"
    );

    modified = config.clone();
    modified["dry_source"]["sha256"] = "0".repeat(64).into();
    assert!(!execute(
        &executable,
        &directory.join("invalid-hash"),
        &modified,
        &dry
    ));
    assert!(!directory.join("invalid-hash/stereo.wav").exists());
    modified = config.clone();
    modified["spatialization"]["normalization"] = "peak".into();
    assert!(!execute(
        &executable,
        &directory.join("invalid-normalization"),
        &modified,
        &dry
    ));
    for (name, mutation) in [
        (
            "invalid-near-field",
            json!({"field":"near_field","value":true}),
        ),
        (
            "invalid-far-filter",
            json!({"field":"far_distance_filter","value":true}),
        ),
    ] {
        modified = config.clone();
        modified["spatialization"][mutation["field"].as_str().unwrap()] = mutation["value"].clone();
        assert!(!execute(
            &executable,
            &directory.join(name),
            &modified,
            &dry
        ));
    }
    modified = config.clone();
    modified["sample_rate_hz"] = 48000.into();
    assert!(!execute(
        &executable,
        &directory.join("invalid-hrtf-rate"),
        &modified,
        &dry
    ));

    let tactile = prepared.tactile_pcm().to_vec();
    let generated =
        compose_spatial_output(prepared, reference.clone(), &AtomicBool::new(false)).unwrap();
    for (index, frame) in generated.interleaved_pcm.chunks_exact(3).enumerate() {
        assert_eq!(frame[2], tactile[index]);
    }
    let audio: Vec<_> = generated
        .interleaved_pcm
        .chunks_exact(3)
        .flat_map(|v| [v[0], v[1]])
        .collect();
    assert!((ratio_db(&audio, &reference) + 12.0).abs() < 0.02);

    let mut ramp = input();
    ramp.level = LevelPolicy::LinearDbRamp {
        start_rms_dbfs: -40.0,
        end_rms_dbfs: -20.0,
        pre_hold_s: 0.1,
        movement_duration_s: 0.8,
        calibration_window_s: 0.5,
        peak_ceiling_dbfs: -1.0,
    };
    assert_eq!(
        compose_spatial_output(
            prepare(&ramp, &AtomicBool::new(false)).unwrap(),
            reference.clone(),
            &AtomicBool::new(false),
        )
        .unwrap_err(),
        GenerationError::PeakCeilingExceeded
    );
    ramp.level = LevelPolicy::LinearDbRamp {
        start_rms_dbfs: -50.0,
        end_rms_dbfs: -30.0,
        pre_hold_s: 0.1,
        movement_duration_s: 0.8,
        calibration_window_s: 0.5,
        peak_ceiling_dbfs: -1.0,
    };
    let generated = compose_spatial_output(
        prepare(&ramp, &AtomicBool::new(false)).unwrap(),
        reference,
        &AtomicBool::new(false),
    )
    .unwrap();
    assert!(
        (generated.level_qc.actual_window_rms_dbfs.unwrap()
            - generated.level_qc.target_window_rms_dbfs.unwrap())
        .abs()
            < 0.02
    );
    write_stimulus_wav(
        fs::File::create(directory.join("final.wav")).unwrap(),
        &generated,
        &AtomicBool::new(false),
    )
    .unwrap();
    fs::write(
        directory.join("final-qc.json"),
        serde_json::to_vec_pretty(&generated.level_qc).unwrap(),
    )
    .unwrap();
    eprintln!("Native measured evidence: {}", directory.display());
}

#[test]
#[ignore = "requires renderer and actual PPS_BROWSER_BLOCK_PLAN; writes about2GiB of offline two-part evidence"]
fn native_browser_stationary_controls_complete_two_part_preparation() {
    use pps_designer_core::{assembly::*, baseline::*};
    use pps_runner_execution::{compile_verified_block_schedule, BlockScheduleOptions};
    use pps_session_package::{verify_prepared_session, VerificationRequest};
    let executable = PathBuf::from(std::env::var_os("PPS_TEST_RENDERER").unwrap());
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap();
    let resource_root = root.join("packages/pps-resources");
    let directory = root.join("artifacts").join(format!(
        "native-study5-participant-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_millis()
    ));
    fs::create_dir(&directory).unwrap();
    let capture: Value = serde_json::from_slice(
        &fs::read(std::env::var("PPS_BROWSER_BLOCK_PLAN").unwrap()).unwrap(),
    )
    .unwrap();
    let mut design = capture["design"].clone();
    let cancel = AtomicBool::new(false);
    let mut assets = Vec::new();
    let mut baseline_reports = Vec::new();
    for label in ["Pink frontal", "White frontal"] {
        let plan = plan_stationary_baseline(
            &design,
            label,
            &BaselineGenerationOptIn {
                source_algorithm: SOURCE_ALGORITHM.into(),
                accept_non_legacy_source_algorithm: true,
            },
        )
        .unwrap();
        assert_eq!(plan.generation.request.sample_rate_hz, 44100);
        assert_eq!(plan.generation.request.duration_s, 4.0);
        let prepared = prepare(&plan.generation.request, &cancel).unwrap();
        let options=SpatializerOptions{hrtf_path:resource_root.join("assets/0. Head-Related Impulse Response (HRIR) model/FABIAN_HRIR_measured_HATO_0.sofa").to_str().unwrap().into(),hrtf_format:HrtfFormat::Sofa,
            head_radius_m:plan.generation.renderer.head_radius_m,distance_attenuation:plan.generation.renderer.distance_attenuation,near_field:plan.generation.renderer.near_field,propagation_delay:plan.generation.renderer.propagation_delay};
        let mut dry = Vec::new();
        let config = write_spatializer_input(&prepared, &mut dry, &options, &cancel).unwrap();
        let render_dir = directory.join(label.replace(' ', "-"));
        assert!(execute(
            &executable,
            &render_dir,
            &serde_json::to_value(config).unwrap(),
            &dry
        ));
        let stereo = read_stereo_wav(
            fs::File::open(render_dir.join("stereo.wav")).unwrap(),
            44100,
            176400,
            &cancel,
        )
        .unwrap();
        let generated = compose_spatial_output(prepared, stereo, &cancel).unwrap();
        assert!((generated.level_qc.audio_peak_dbfs - 20.0 * 0.9_f64.log10()).abs() < 0.00001);
        let mut wav = std::io::Cursor::new(Vec::new());
        write_ingredient_wav(&mut wav, &generated, &cancel).unwrap();
        let bytes = wav.into_inner();
        let hash = format!("{:x}", Sha256::digest(&bytes));
        let reference = format!("native-assets/{hash}.wav");
        let report: Value =
            serde_json::from_slice(&fs::read(render_dir.join("manifest.json")).unwrap()).unwrap();
        let entry = generated_stationary_baseline_entry(
            &plan, &reference, &bytes, &generated, &report, &cancel,
        )
        .unwrap();
        let publication = apply_generated_stationary_baseline(&plan, &entry).unwrap();
        fs::write(render_dir.join("baseline.wav"), &bytes).unwrap();
        fs::write(
            render_dir.join("publication.json"),
            serde_json::to_vec_pretty(&publication).unwrap(),
        )
        .unwrap();
        assets.push(
            VerifiedAssemblyAsset::from_wav_bytes(
                &reference,
                &bytes,
                &hash,
                AssemblyAssetRole::StationaryBaseline,
                &cancel,
            )
            .unwrap(),
        );
        baseline_reports.push(publication.asset);
        design = publication.design;
        eprintln!("Rendered real V2 stationary control: {label}");
    }
    let mut references = std::collections::BTreeMap::new();
    let selected: std::collections::BTreeSet<_> = capture["variants"]
        .as_array()
        .unwrap()
        .iter()
        .flat_map(|v| v["choices"].as_array().unwrap())
        .filter(|choice| choice["kind"] == "audio")
        .map(|choice| choice["label"].as_str().unwrap())
        .collect();
    for (collection, field, role) in [
        (
            "noises",
            "prebaked_path",
            AssemblyAssetRole::BinauralIngredient,
        ),
        ("prestimulus_files", "path", AssemblyAssetRole::Instruction),
    ] {
        for asset in design[collection].as_array().unwrap() {
            if !selected.contains(asset["label"].as_str().unwrap()) {
                continue;
            }
            references.insert(asset[field].as_str().unwrap().to_owned(), role);
        }
    }
    for slot in design["study_profile_reference_parameters"]["dashboard_run_setup"]
        ["instruction_profile"]["slots"]
        .as_array()
        .unwrap()
    {
        if slot["enabled"] == true {
            references.insert(
                slot["path"].as_str().unwrap().to_owned(),
                AssemblyAssetRole::Instruction,
            );
        }
    }
    assert_eq!(references.len(), 9);
    for (reference, role) in references {
        assert!(reference.starts_with("assets/") && !reference.contains(".."));
        let bytes = fs::read(resource_root.join(&reference)).unwrap();
        let hash = format!("{:x}", Sha256::digest(&bytes));
        assets.push(
            VerifiedAssemblyAsset::from_wav_bytes(&reference, &bytes, &hash, role, &cancel)
                .unwrap(),
        );
    }
    let cue = fs::read(resource_root.join("assets/tactile/default_tactile_cue.wav")).unwrap();
    let cue_hash = format!("{:x}", Sha256::digest(&cue));
    let tactile = VerifiedAssemblyAsset::from_wav_bytes(
        "bundled-tactile",
        &cue,
        &cue_hash,
        AssemblyAssetRole::TactileCue,
        &cancel,
    )
    .unwrap();
    let source = plan_assembly_preview(
        &design,
        &capture["block_csv_preview"],
        &capture["variants"],
        &assets,
        &tactile,
        &cancel,
    )
    .unwrap();
    let order = plan_run_order_preview(&source, &assets, &cancel).unwrap();
    assert_eq!(order.preview["csv_rows"].as_array().unwrap().len(), 600);
    let expected: Vec<usize> = order.preview["csv_rows"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|r| r["participant_index"] == 1)
        .map(|r| r["source_block_index"].as_u64().unwrap() as usize)
        .collect();
    let (dh, sh, rh) = (
        source.design_sha256.clone(),
        source.preview_sha256.clone(),
        order.run_order_sha256.clone(),
    );
    let accepted = accept_participant_assembly(source, order, &dh, &sh, &rh, 1).unwrap();
    let staged = prepare_accepted_participant(
        &accepted,
        &assets,
        &tactile,
        &directory.join("participant"),
        1,
        "P001_native_v2_software_fixture",
        &cancel,
    )
    .unwrap();
    assert_eq!(staged.parts().len(), 2);
    let mut trial_count = 0;
    let mut baseline_count = 0;
    for (part_index, part) in staged.parts().iter().enumerate() {
        let verified = verify_prepared_session(
            VerificationRequest::new(part.manifest_path()).with_participant_id("P001"),
        )
        .unwrap();
        assert_eq!(verified.blocks().len(), 6);
        assert_eq!(verified.summary().part_number, Some(part_index as i64 + 1));
        for (block_index, block) in verified.blocks().iter().enumerate() {
            let mut options = BlockScheduleOptions::new(block_index as i64 + 1);
            options.sample_rate = 44100;
            options.block_wav_path = Some(block.wav_path().to_owned());
            let schedule = compile_verified_block_schedule(
                block.manifest_path(),
                block.manifest_sha256(),
                options,
            )
            .unwrap();
            assert_eq!(schedule.summary().trial_row_count, 34);
            trial_count += schedule.summary().trial_row_count;
            let mut csv = csv::Reader::from_path(block.manifest_path()).unwrap();
            let header = csv.headers().unwrap().clone();
            let source_index = header
                .iter()
                .position(|h| h == "Source_Block_Index")
                .unwrap();
            let family = header.iter().position(|h| h == "Family").unwrap();
            let pool = header.iter().position(|h| h == "trial_pool_index").unwrap();
            let expected_source = expected[part_index * 6 + block_index];
            let mut pools = Vec::new();
            for row in csv.records() {
                let row = row.unwrap();
                assert_eq!(row[source_index].parse::<usize>().unwrap(), expected_source);
                baseline_count += usize::from(&row[family] == "baseline");
                pools.push(row[pool].parse::<u64>().unwrap());
            }
            let original: Vec<u64> = capture["block_csv_preview"]["blocks"][expected_source - 1]
                ["preview_rows"]
                .as_array()
                .unwrap()
                .iter()
                .map(|r| r["trial_pool_index"].as_u64().unwrap())
                .collect();
            assert_eq!(pools, original);
        }
        eprintln!(
            "Verified real participant part{}:6blocks/204rows",
            part_index + 1
        );
    }
    assert_eq!(trial_count, 408);
    assert_eq!(baseline_count, 120);
    fs::write(directory.join("software-evidence.json"),serde_json::to_vec_pretty(&json!({"qualification":"customized_native_generation_unqualified","physical_timing_qualified":false,"legacy_numpy_seed_compatible":false,"part_count":2,"block_count":12,"trial_count":trial_count,"baseline_count":baseline_count,"source_assets":9,"generated_stationary_controls":baseline_reports,"group_manifest":staged.group_manifest_path()})).unwrap()).unwrap();
    eprintln!(
        "Full native customized software evidence: {}",
        directory.display()
    );
}
