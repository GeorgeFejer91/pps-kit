use crate::{
    check_cancelled, peak, rms, validate, zeroed, GenerationError, GenerationRequest,
    ImportChannelPolicy, ImportLengthPolicy, PreparedStimulus, SourceQc, SourceSpec,
    IMPORT_ALGORITHM, MAX_FRAMES,
};
use sha2::{Digest, Sha256};
use std::{io::Cursor, sync::atomic::AtomicBool};

/// The native host authorizes and bounds file acquisition before this call.
/// Hash, format, channel, rate and length policies are checked before allocating
/// decoded PCM. Source amplitude is preserved, never peak-normalized.
pub fn prepare_imported_wav(
    request: &GenerationRequest,
    bytes: &[u8],
    cancelled: &AtomicBool,
) -> Result<PreparedStimulus, GenerationError> {
    check_cancelled(cancelled)?;
    let frames = validate(request)?;
    let SourceSpec::ImportedWav {
        sha256,
        channel_policy,
        length_policy,
    } = &request.source
    else {
        return Err(GenerationError::Invalid("imported_wav_source_required"));
    };
    if request.seed != 0 {
        return Err(GenerationError::Invalid(
            "imported_source_seed_must_be_zero",
        ));
    }
    if bytes.len() > MAX_FRAMES * 8 + 1024 * 1024 {
        return Err(GenerationError::ResourceLimit);
    }
    if sha256.len() != 64
        || !sha256
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        return Err(GenerationError::Invalid("imported_sha256"));
    }
    let mut digest = Sha256::new();
    for chunk in bytes.chunks(65536) {
        check_cancelled(cancelled)?;
        digest.update(chunk);
    }
    if format!("{:x}", digest.finalize()) != *sha256 {
        return Err(GenerationError::Invalid("imported_sha256_mismatch"));
    }
    let mut reader =
        hound::WavReader::new(Cursor::new(bytes)).map_err(|_| GenerationError::InvalidAudio)?;
    let spec = reader.spec();
    let expected_channels = match channel_policy {
        ImportChannelPolicy::Mono => 1,
        ImportChannelPolicy::StereoMean => 2,
    };
    if spec.channels != expected_channels {
        return Err(GenerationError::Invalid("imported_channel_policy"));
    }
    if spec.sample_rate != request.sample_rate_hz {
        return Err(GenerationError::Invalid(
            "imported_sample_rate_requires_explicit_resampling",
        ));
    }
    let count = reader.len() as usize;
    if count == 0
        || count > MAX_FRAMES * usize::from(spec.channels)
        || !count.is_multiple_of(usize::from(spec.channels))
    {
        return Err(GenerationError::ResourceLimit);
    }
    let source_frames = count / usize::from(spec.channels);
    if *length_policy == ImportLengthPolicy::Exact && source_frames != frames {
        return Err(GenerationError::Invalid("imported_exact_length"));
    }
    let mut dry = zeroed(frames)?;
    match (spec.sample_format, spec.bits_per_sample) {
        (hound::SampleFormat::Float, 32) => decode(
            reader.samples::<f32>(),
            source_frames,
            spec.channels,
            &mut dry,
            cancelled,
        )?,
        (hound::SampleFormat::Int, 16 | 24 | 32) => {
            let scale = (1_u64 << (spec.bits_per_sample - 1)) as f64;
            decode(
                reader
                    .samples::<i32>()
                    .map(|sample| sample.map(|value| (f64::from(value) / scale) as f32)),
                source_frames,
                spec.channels,
                &mut dry,
                cancelled,
            )?;
        }
        _ => return Err(GenerationError::Invalid("imported_wav_encoding")),
    }
    let tactile = crate::source::generate_tactile(request, frames, cancelled)?;
    let qc = SourceQc {
        seed: 0,
        source_algorithm: IMPORT_ALGORITHM,
        numpy_seed_compatible: false,
        frames,
        burst_onset_frames: vec![],
        burst_frames: None,
        burst_envelope_algorithm: None,
        noise_color: None,
        color_algorithm: None,
        imported_sha256: Some(sha256.clone()),
        peak: peak(&dry),
        rms: rms(&dry),
    };
    check_cancelled(cancelled)?;
    Ok(PreparedStimulus {
        request: request.clone(),
        dry,
        tactile,
        qc,
    })
}

fn decode<I: Iterator<Item = Result<f32, hound::Error>>>(
    mut samples: I,
    source_frames: usize,
    channels: u16,
    output: &mut [f32],
    cancelled: &AtomicBool,
) -> Result<(), GenerationError> {
    for frame in 0..source_frames {
        if frame % 4096 == 0 {
            check_cancelled(cancelled)?;
        }
        let mut sum = 0.0_f64;
        for _ in 0..channels {
            let sample = samples
                .next()
                .ok_or(GenerationError::InvalidAudio)?
                .map_err(|_| GenerationError::InvalidAudio)?;
            if !sample.is_finite() {
                return Err(GenerationError::InvalidAudio);
            }
            sum += f64::from(sample);
        }
        if frame < output.len() {
            output[frame] = (sum / f64::from(channels)) as f32;
        }
    }
    if samples.next().is_some() {
        return Err(GenerationError::InvalidAudio);
    }
    Ok(())
}
