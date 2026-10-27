//! Explicit offline native test: no audio device or playback is opened.
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
