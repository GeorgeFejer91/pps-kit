use pps_designer_core::*;
use sha2::{Digest, Sha256};
use std::{io::Cursor, sync::atomic::AtomicBool};

fn bytes(samples: &[f32], channels: u16) -> Vec<u8> {
    let mut bytes = Cursor::new(Vec::new());
    let mut writer = hound::WavWriter::new(
        &mut bytes,
        hound::WavSpec {
            channels,
            sample_rate: 8000,
            bits_per_sample: 32,
            sample_format: hound::SampleFormat::Float,
        },
    )
    .unwrap();
    for sample in samples {
        writer.write_sample(*sample).unwrap();
    }
    writer.finalize().unwrap();
    bytes.into_inner()
}

fn request(bytes: &[u8]) -> GenerationRequest {
    GenerationRequest {
        schema: REQUEST_SCHEMA.into(),
        source_algorithm: IMPORT_ALGORITHM.into(),
        sample_rate_hz: 8000,
        duration_s: 0.00025,
        seed: 0,
        source: SourceSpec::ImportedWav {
            sha256: format!("{:x}", Sha256::digest(bytes)),
            channel_policy: ImportChannelPolicy::StereoMean,
            length_policy: ImportLengthPolicy::Exact,
        },
        trajectory: TrajectorySpec::Fixed {
            position: Position {
                x_m: 0.0,
                y_m: 1.0,
                z_m: 0.0,
            },
        },
        tactile: vec![],
        level: LevelPolicy::Preserve {
            gain_db: 0.0,
            peak_ceiling_dbfs: 0.0,
        },
    }
}

#[test]
fn verified_stereo_downmix_preserves_amplitude_and_explicit_fit_policy() {
    let bytes = bytes(&[0.25, -0.5, 0.75, 0.5], 2);
    let mut input = request(&bytes);
    let prepared = prepare_imported_wav(&input, &bytes, &AtomicBool::new(false)).unwrap();
    assert_eq!(prepared.dry_pcm(), [-0.125, 0.625]);
    assert_eq!(prepared.source_qc().source_algorithm, IMPORT_ALGORITHM);
    assert_eq!(prepared.source_qc().peak, 0.625);
    assert_eq!(
        prepared.source_qc().imported_sha256,
        Some(format!("{:x}", Sha256::digest(&bytes)))
    );
    input.duration_s = 0.0005;
    assert!(matches!(
        prepare_imported_wav(&input, &bytes, &AtomicBool::new(false)),
        Err(GenerationError::Invalid("imported_exact_length"))
    ));
    if let SourceSpec::ImportedWav { length_policy, .. } = &mut input.source {
        *length_policy = ImportLengthPolicy::TrimOrZeroPad;
    }
    assert_eq!(
        prepare_imported_wav(&input, &bytes, &AtomicBool::new(false))
            .unwrap()
            .dry_pcm(),
        [-0.125, 0.625, 0.0, 0.0]
    );
    input.duration_s = 0.000125;
    assert_eq!(
        prepare_imported_wav(&input, &bytes, &AtomicBool::new(false))
            .unwrap()
            .dry_pcm(),
        [-0.125]
    );
}

#[test]
fn imported_pcm16_scaling_and_integrity_rejections_are_not_silent_fallbacks() {
    let mut file = Cursor::new(Vec::new());
    let mut writer = hound::WavWriter::new(
        &mut file,
        hound::WavSpec {
            channels: 1,
            sample_rate: 8000,
            bits_per_sample: 16,
            sample_format: hound::SampleFormat::Int,
        },
    )
    .unwrap();
    writer.write_sample(i16::MIN).unwrap();
    writer.write_sample(i16::MAX).unwrap();
    writer.finalize().unwrap();
    let bytes = file.into_inner();
    let mut input = request(&bytes);
    if let SourceSpec::ImportedWav { channel_policy, .. } = &mut input.source {
        *channel_policy = ImportChannelPolicy::Mono;
    }
    assert_eq!(
        prepare_imported_wav(&input, &bytes, &AtomicBool::new(false))
            .unwrap()
            .dry_pcm(),
        [-1.0, 32767.0 / 32768.0]
    );
    assert!(matches!(
        prepare(&input, &AtomicBool::new(false)),
        Err(GenerationError::Invalid("imported_bytes_required"))
    ));
    input.sample_rate_hz = 16000;
    assert!(matches!(
        prepare_imported_wav(&input, &bytes, &AtomicBool::new(false)),
        Err(GenerationError::Invalid(
            "imported_sample_rate_requires_explicit_resampling"
        ))
    ));
    input.sample_rate_hz = 8000;
    let mut changed = bytes.clone();
    let last = changed.len() - 1;
    changed[last] ^= 1;
    assert!(matches!(
        prepare_imported_wav(&input, &changed, &AtomicBool::new(false)),
        Err(GenerationError::Invalid("imported_sha256_mismatch"))
    ));
    assert_eq!(
        prepare_imported_wav(&input, &bytes, &AtomicBool::new(true)).unwrap_err(),
        GenerationError::Cancelled
    );
    input.seed = 1;
    assert!(prepare_imported_wav(&input, &bytes, &AtomicBool::new(false)).is_err());
}

#[test]
fn nonfinite_and_deceptive_header_imports_fail_before_publication() {
    let invalid = bytes(&[f32::NAN, 0.0, 0.0, 0.0], 2);
    assert_eq!(
        prepare_imported_wav(&request(&invalid), &invalid, &AtomicBool::new(false)).unwrap_err(),
        GenerationError::InvalidAudio
    );
    let mut invalid = bytes(&[0.0; 4], 2);
    let data = invalid.windows(4).position(|v| v == b"data").unwrap();
    invalid[data + 4..data + 8].copy_from_slice(&0xfffffff0_u32.to_le_bytes());
    assert!(prepare_imported_wav(&request(&invalid), &invalid, &AtomicBool::new(false)).is_err());
}
