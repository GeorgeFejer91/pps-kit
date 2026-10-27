use pps_designer_core::*;
use std::{io::Cursor, sync::atomic::AtomicBool};

fn request() -> GenerationRequest {
    GenerationRequest {
        schema: REQUEST_SCHEMA.into(),
        source_algorithm: SOURCE_ALGORITHM.into(),
        sample_rate_hz: 8000,
        duration_s: 1.0,
        seed: 123,
        source: SourceSpec::ContinuousWhite,
        trajectory: TrajectorySpec::Linear {
            start: Position {
                x_m: 0.0,
                y_m: 2.0,
                z_m: 0.0,
            },
            end: Position {
                x_m: 0.0,
                y_m: 0.3,
                z_m: 0.0,
            },
            pre_hold_s: 0.2,
            movement_duration_s: 0.6,
        },
        tactile: vec![TactileCue {
            onset_s: 0.5,
            duration_s: 0.05,
            attack_frequency_hz: 250.0,
            decay_frequency_hz: 150.0,
            peak_amplitude: 0.5,
        }],
        level: LevelPolicy::Preserve {
            gain_db: -6.0,
            peak_ceiling_dbfs: -1.0,
        },
    }
}

#[test]
fn explicit_peak_normalization_reports_gain_and_leaves_tactile_unchanged() {
    let mut input = request();
    let target = 20.0 * 0.9_f64.log10();
    input.level = LevelPolicy::PeakNormalize {
        target_peak_dbfs: target,
        peak_ceiling_dbfs: target,
    };
    let cancel = AtomicBool::new(false);
    let prepared = prepare(&input, &cancel).unwrap();
    let tactile = prepared.tactile_pcm().to_vec();
    let mut stereo = vec![0.1; prepared.dry_pcm().len() * 2];
    stereo[123] = -0.3;
    let generated = compose_spatial_output(prepared, stereo, &cancel).unwrap();
    assert_eq!(generated.level_qc.kind, "peak_normalize");
    assert_eq!(generated.level_qc.target_peak_dbfs, Some(target));
    assert!((generated.level_qc.audio_peak_dbfs - target).abs() < 0.00001);
    assert!((generated.interleaved_pcm[0] - 0.3).abs() < 0.000001);
    assert!((generated.interleaved_pcm[61 * 3 + 1] + 0.9).abs() < 0.000001);
    for (frame, expected) in generated.interleaved_pcm.chunks_exact(3).zip(tactile) {
        assert_eq!(frame[2], expected);
    }
    assert!(!generated.level_qc.physical_spl_qualified);
    assert!(generated.level_qc.calibration_window_frames.is_none());
    assert!(matches!(
        compose_spatial_output(prepare(&input, &cancel).unwrap(), vec![0.0; 16000], &cancel),
        Err(GenerationError::Invalid("silent_peak_normalization"))
    ));
    input.level = LevelPolicy::PeakNormalize {
        target_peak_dbfs: 0.0,
        peak_ceiling_dbfs: -1.0,
    };
    assert!(prepare(&input, &cancel).is_err());
}

#[test]
fn deterministic_white_is_real_pcm_and_explicitly_not_numpy_seed_compatible() {
    let prepared = prepare(&request(), &AtomicBool::new(false)).unwrap();
    let repeated = prepare(&request(), &AtomicBool::new(false)).unwrap();
    let frozen = [
        0.26266164,
        0.3727154,
        -0.0792855,
        0.04729554,
        0.22672619,
        -0.014781525,
        0.24429841,
        0.30015013,
    ];
    for (actual, expected) in prepared.dry_pcm().iter().zip(frozen) {
        assert!((actual - expected).abs() < 1e-7);
    }
    assert_eq!(prepared.dry_pcm(), repeated.dry_pcm());
    assert_eq!(prepared.dry_pcm().len(), 8000);
    assert!(prepared.source_qc().rms > 0.15 && prepared.source_qc().rms < 0.4);
    assert_eq!(prepared.source_qc().peak, 1.0);
    assert!(!prepared.source_qc().numpy_seed_compatible);
    let mut changed = request();
    changed.seed += 1;
    assert_ne!(
        prepared.dry_pcm(),
        prepare(&changed, &AtomicBool::new(false))
            .unwrap()
            .dry_pcm()
    );
}

#[test]
fn duration_derived_bursts_have_exact_support_and_symmetric_spacing() {
    let mut input = request();
    input.source = SourceSpec::GaussianBurstTrain {
        onset_s: 0.1,
        active_window_s: 0.48,
        burst_duration_s: 0.03,
        rise_fall_s: 0.01,
        target_period_s: 0.095,
    };
    let prepared = prepare(&input, &AtomicBool::new(false)).unwrap();
    assert_eq!(
        prepared.source_qc().burst_onset_frames,
        [800, 1520, 2240, 2960, 3680, 4400]
    );
    assert_eq!(prepared.source_qc().burst_frames, Some(240));
    for frame in 0..8000 {
        let audible = [800, 1520, 2240, 2960, 3680, 4400]
            .iter()
            .any(|first| (*first..*first + 240).contains(&frame));
        if !audible {
            assert_eq!(
                prepared.dry_pcm()[frame],
                0.0,
                "unexpected energy at {frame}"
            );
        }
    }
    assert!(prepared.dry_pcm()[800..1040].iter().any(|v| v.abs() > 0.1));
    assert_eq!(prepared.dry_pcm()[800], 0.0);
    assert_eq!(prepared.dry_pcm()[1039], 0.0);
}

#[test]
fn trajectory_holds_and_tactile_channel_are_sample_accurate() {
    let prepared = prepare(&request(), &AtomicBool::new(false)).unwrap();
    assert_eq!(prepared.position_at(0.0).unwrap().y_m, 2.0);
    assert!((prepared.position_at(0.5).unwrap().y_m - 1.15).abs() < 1e-12);
    assert!((prepared.position_at(1.0).unwrap().y_m - 0.3).abs() < 1e-12);
    assert!(prepared.tactile_pcm()[..4000].iter().all(|v| *v == 0.0));
    assert!(prepared.tactile_pcm()[4400..].iter().all(|v| *v == 0.0));
    assert_eq!(
        prepared.tactile_pcm()[4000..4400]
            .iter()
            .map(|v| v.abs())
            .fold(0.0_f32, f32::max),
        0.5
    );
}

#[test]
fn preserve_gain_does_not_normalize_and_wav_channels_round_trip() {
    let prepared = prepare(&request(), &AtomicBool::new(false)).unwrap();
    let generated =
        compose_spatial_output(prepared, vec![0.25; 16000], &AtomicBool::new(false)).unwrap();
    let actual = generated.interleaved_pcm[0];
    assert!((20.0 * (f64::from(actual) / 0.25).log10() + 6.0).abs() < 0.02);
    assert_eq!(
        generated.interleaved_pcm[4001 * 3 + 2],
        prepare(&request(), &AtomicBool::new(false))
            .unwrap()
            .tactile_pcm()[4001]
    );
    let mut file = Cursor::new(Vec::new());
    write_stimulus_wav(&mut file, &generated, &AtomicBool::new(false)).unwrap();
    file.set_position(0);
    let mut reader = hound::WavReader::new(file).unwrap();
    assert_eq!(reader.spec().channels, 3);
    assert_eq!(reader.duration(), 8000);
    assert_eq!(
        reader
            .samples::<f32>()
            .collect::<Result<Vec<_>, _>>()
            .unwrap(),
        generated.interleaved_pcm
    );
}

#[test]
fn ramp_matches_final_active_window_within_point_zero_two_db() {
    let mut input = request();
    input.level = LevelPolicy::LinearDbRamp {
        start_rms_dbfs: -40.0,
        end_rms_dbfs: -20.0,
        pre_hold_s: 0.2,
        movement_duration_s: 0.6,
        calibration_window_s: 0.3,
        peak_ceiling_dbfs: -1.0,
    };
    let prepared = prepare(&input, &AtomicBool::new(false)).unwrap();
    let generated =
        compose_spatial_output(prepared, vec![0.25; 16000], &AtomicBool::new(false)).unwrap();
    let qc = &generated.level_qc;
    assert_eq!(qc.calibration_window_frames, Some([4000, 6400]));
    assert!((qc.target_window_rms_dbfs.unwrap() - qc.actual_window_rms_dbfs.unwrap()).abs() < 0.02);
    let start = generated.interleaved_pcm[0];
    let end = generated.interleaved_pcm[7999 * 3];
    assert!((20.0 * f64::from(end / start).log10() - 20.0).abs() < 0.02);
    assert!(!qc.physical_spl_qualified);
}

#[test]
fn legacy_algorithm_invalid_audio_limits_and_cancellation_fail_closed() {
    let mut input = request();
    input.source_algorithm = "numpy-default_rng".into();
    assert!(matches!(
        prepare(&input, &AtomicBool::new(false)),
        Err(GenerationError::Invalid("schema_or_source_algorithm"))
    ));
    assert_eq!(
        prepare(&request(), &AtomicBool::new(true)).unwrap_err(),
        GenerationError::Cancelled
    );
    input = request();
    input.duration_s = 61.0;
    assert!(prepare(&input, &AtomicBool::new(false)).is_err());
    input = request();
    input.level = LevelPolicy::Preserve {
        gain_db: 24.0,
        peak_ceiling_dbfs: -1.0,
    };
    assert_eq!(
        compose_spatial_output(
            prepare(&input, &AtomicBool::new(false)).unwrap(),
            vec![1.0; 16000],
            &AtomicBool::new(false)
        )
        .unwrap_err(),
        GenerationError::PeakCeilingExceeded
    );
    assert_eq!(
        compose_spatial_output(
            prepare(&request(), &AtomicBool::new(false)).unwrap(),
            vec![f32::NAN; 16000],
            &AtomicBool::new(false)
        )
        .unwrap_err(),
        GenerationError::InvalidAudio
    );
}

#[test]
fn requests_reject_unknown_fields_and_unknown_source_modes() {
    let mut json = serde_json::to_value(request()).unwrap();
    json["execute"] = true.into();
    assert!(serde_json::from_value::<GenerationRequest>(json).is_err());
    let mut json = serde_json::to_value(request()).unwrap();
    json["source"]["kind"] = "unsupported".into();
    assert!(serde_json::from_value::<GenerationRequest>(json).is_err());
}

#[test]
fn python_reference_freezes_tactile_samples_burst_schedule_and_ramp_window() {
    let fixture: serde_json::Value =
        serde_json::from_str(include_str!("fixtures/python_reference.json")).unwrap();
    let prepared = prepare(&request(), &AtomicBool::new(false)).unwrap();
    let expected = fixture["tactile_pcm"].as_array().unwrap();
    for (actual, expected) in prepared.tactile_pcm()[4000..4400].iter().zip(expected) {
        assert!((f64::from(*actual) - expected.as_f64().unwrap()).abs() < 1e-7);
    }
    let mut input = request();
    input.source = SourceSpec::GaussianBurstTrain {
        onset_s: 0.1,
        active_window_s: 0.48,
        burst_duration_s: 0.03,
        rise_fall_s: 0.01,
        target_period_s: 0.095,
    };
    let prepared = prepare(&input, &AtomicBool::new(false)).unwrap();
    assert_eq!(
        serde_json::to_value(&prepared.source_qc().burst_onset_frames).unwrap(),
        fixture["burst_onset_frames"]
    );
    input.level = LevelPolicy::LinearDbRamp {
        start_rms_dbfs: -40.0,
        end_rms_dbfs: -20.0,
        pre_hold_s: 0.2,
        movement_duration_s: 0.6,
        calibration_window_s: 0.3,
        peak_ceiling_dbfs: -1.0,
    };
    let generated = compose_spatial_output(
        prepare(&input, &AtomicBool::new(false)).unwrap(),
        vec![0.25; 16000],
        &AtomicBool::new(false),
    )
    .unwrap();
    assert!(
        (generated.level_qc.target_window_rms_dbfs.unwrap()
            - fixture["target_window_rms_dbfs"].as_f64().unwrap())
        .abs()
            < 0.02
    );
    assert_eq!(
        serde_json::to_value(generated.level_qc.calibration_window_frames.unwrap()).unwrap(),
        fixture["calibration_window_frames"]
    );
    for (index, expected) in fixture["envelope_samples"].as_object().unwrap() {
        let actual = generated.interleaved_pcm[index.parse::<usize>().unwrap() * 3]
            / generated.interleaved_pcm[7999 * 3];
        assert!((f64::from(actual) - expected.as_f64().unwrap()).abs() < 1e-6);
    }
}

#[test]
fn bridge_rejects_conflicting_loudness_and_invalid_spatial_paths() {
    let mut input = request();
    input.trajectory = TrajectorySpec::Linear {
        start: Position {
            x_m: -1.0,
            y_m: 0.0,
            z_m: 0.0,
        },
        end: Position {
            x_m: 1.0,
            y_m: 0.0,
            z_m: 0.0,
        },
        pre_hold_s: 0.0,
        movement_duration_s: 1.0,
    };
    assert!(prepare(&input, &AtomicBool::new(false)).is_err());
    input = request();
    input.level = LevelPolicy::LinearDbRamp {
        start_rms_dbfs: -40.0,
        end_rms_dbfs: -20.0,
        pre_hold_s: 0.2,
        movement_duration_s: 0.6,
        calibration_window_s: 0.3,
        peak_ceiling_dbfs: -1.0,
    };
    let options = SpatializerOptions {
        hrtf_path: "asset.sofa".into(),
        hrtf_format: HrtfFormat::Sofa,
        head_radius_m: 0.09,
        distance_attenuation: true,
        near_field: false,
        propagation_delay: false,
    };
    assert!(matches!(
        write_spatializer_input(
            &prepare(&input, &AtomicBool::new(false)).unwrap(),
            Vec::new(),
            &options,
            &AtomicBool::new(false)
        ),
        Err(GenerationError::Invalid("ramp_with_distance_attenuation"))
    ));
}

#[test]
fn polar_arcs_and_burst_edges_match_the_reference_samples() {
    let fixture: serde_json::Value =
        serde_json::from_str(include_str!("fixtures/python_reference.json")).unwrap();
    let mut input = request();
    input.trajectory = TrajectorySpec::Polar {
        start_radius_m: 2.0,
        end_radius_m: 1.0,
        azimuth_start_deg: 170.0,
        azimuth_end_deg: -170.0,
        elevation_deg: 30.0,
        pre_hold_s: 0.2,
        movement_duration_s: 0.6,
    };
    let prepared = prepare(&input, &AtomicBool::new(false)).unwrap();
    for expected in fixture["polar_points"].as_array().unwrap() {
        let point = prepared
            .position_at(expected["time_s"].as_f64().unwrap())
            .unwrap();
        for (actual, key) in [(point.x_m, "x_m"), (point.y_m, "y_m"), (point.z_m, "z_m")] {
            assert!((actual - expected[key].as_f64().unwrap()).abs() < 1e-12);
        }
    }
    // The 170 -> -170 reference travels through the front. Neither shortest-arc
    // wrapping nor a Cartesian chord is an interchangeable interpretation.
    assert!(prepared.position_at(0.5).unwrap().y_m > 1.0);

    input.duration_s = 0.03;
    input.tactile.clear();
    input.trajectory = TrajectorySpec::Fixed {
        position: Position {
            x_m: 0.0,
            y_m: 1.0,
            z_m: 0.0,
        },
    };
    let white = prepare(&input, &AtomicBool::new(false)).unwrap();
    input.source = SourceSpec::GaussianBurstTrain {
        onset_s: 0.0,
        active_window_s: 0.03,
        burst_duration_s: 0.03,
        rise_fall_s: 0.01,
        target_period_s: 0.095,
    };
    let burst = prepare(&input, &AtomicBool::new(false)).unwrap();
    let mut expected: Vec<_> = white
        .dry_pcm()
        .iter()
        .zip(fixture["burst_envelope"].as_array().unwrap())
        .map(|(sample, envelope)| sample * envelope.as_f64().unwrap() as f32)
        .collect();
    let peak = expected.iter().map(|v| v.abs()).fold(0.0_f32, f32::max);
    for sample in &mut expected {
        *sample /= peak;
    }
    for (actual, expected) in burst.dry_pcm().iter().zip(expected) {
        assert!((actual - expected).abs() < 1e-7);
    }
    assert_eq!(
        burst.source_qc().burst_envelope_algorithm,
        Some("raised-cosine-endpoint-exclusive.v1")
    );
}

#[test]
fn explicit_noise_colors_and_profiles_generate_distinct_bounded_waveforms() {
    let mut input = request();
    let white = prepare(&input, &AtomicBool::new(false)).unwrap();
    for color in [
        NoiseColor::White,
        NoiseColor::Pink,
        NoiseColor::Blue,
        NoiseColor::Violet,
        NoiseColor::Brown,
    ] {
        input.source = SourceSpec::Noise {
            color,
            profile: SourceProfile::Continuous,
        };
        let generated = prepare(&input, &AtomicBool::new(false)).unwrap();
        assert_eq!(generated.source_qc().noise_color, Some(color));
        assert_eq!(generated.source_qc().peak, 1.0);
        if color == NoiseColor::White {
            assert_eq!(generated.dry_pcm(), white.dry_pcm());
        } else {
            assert_ne!(generated.dry_pcm(), white.dry_pcm());
        }
        input.source = SourceSpec::Noise {
            color,
            profile: SourceProfile::GaussianBurstTrain {
                onset_s: 0.1,
                active_window_s: 0.48,
                burst_duration_s: 0.03,
                rise_fall_s: 0.01,
                target_period_s: 0.095,
            },
        };
        let burst = prepare(&input, &AtomicBool::new(false)).unwrap();
        assert_eq!(
            burst.source_qc().burst_onset_frames,
            [800, 1520, 2240, 2960, 3680, 4400]
        );
        assert!(burst.dry_pcm()[..800].iter().all(|v| *v == 0.0));
        assert!(burst.dry_pcm()[4640..].iter().all(|v| *v == 0.0));
    }
    input.sample_rate_hz = 192000;
    input.duration_s = 6.0;
    input.source = SourceSpec::Noise {
        color: NoiseColor::Pink,
        profile: SourceProfile::Continuous,
    };
    assert_eq!(
        prepare(&input, &AtomicBool::new(false)).unwrap_err(),
        GenerationError::ResourceLimit
    );
}
