use crate::{check_cancelled, GeneratedStimulus, GenerationError, MAX_FRAMES};
use std::{
    io::{Read, Seek, Write},
    sync::atomic::AtomicBool,
};

pub fn write_mono_wav<W: Write + Seek>(
    output: W,
    samples: &[f32],
    sample_rate_hz: u32,
    cancelled: &AtomicBool,
) -> Result<(), GenerationError> {
    write_wav(output, samples, sample_rate_hz, 1, cancelled)
}

pub fn write_stimulus_wav<W: Write + Seek>(
    output: W,
    stimulus: &GeneratedStimulus,
    cancelled: &AtomicBool,
) -> Result<(), GenerationError> {
    write_wav(
        output,
        &stimulus.interleaved_pcm,
        stimulus.sample_rate_hz,
        3,
        cancelled,
    )
}

/// Segment 1 ingredients contain audio only; tactile is assembled later from
/// the approved trial plan. Never silently discard an already-present cue.
pub fn write_ingredient_wav<W: Write + Seek>(
    output: W,
    stimulus: &GeneratedStimulus,
    cancelled: &AtomicBool,
) -> Result<(), GenerationError> {
    check_cancelled(cancelled)?;
    if stimulus.interleaved_pcm.is_empty()
        || !stimulus.interleaved_pcm.len().is_multiple_of(3)
        || stimulus.interleaved_pcm.len() / 3 > MAX_FRAMES
        || !(8000..=192000).contains(&stimulus.sample_rate_hz)
        || stimulus.interleaved_pcm.iter().any(|v| !v.is_finite())
    {
        return Err(GenerationError::InvalidAudio);
    }
    if stimulus
        .interleaved_pcm
        .chunks_exact(3)
        .any(|v| v[2] != 0.0)
    {
        return Err(GenerationError::Invalid("ingredient_contains_tactile"));
    }
    let mut writer = hound::WavWriter::new(
        output,
        hound::WavSpec {
            channels: 2,
            sample_rate: stimulus.sample_rate_hz,
            bits_per_sample: 32,
            sample_format: hound::SampleFormat::Float,
        },
    )
    .map_err(|_| GenerationError::Io)?;
    for (index, frame) in stimulus.interleaved_pcm.chunks_exact(3).enumerate() {
        if index % 4096 == 0 {
            check_cancelled(cancelled)?;
        }
        writer
            .write_sample(frame[0])
            .map_err(|_| GenerationError::Io)?;
        writer
            .write_sample(frame[1])
            .map_err(|_| GenerationError::Io)?;
    }
    check_cancelled(cancelled)?;
    writer.finalize().map_err(|_| GenerationError::Io)
}

fn write_wav<W: Write + Seek>(
    output: W,
    samples: &[f32],
    sample_rate_hz: u32,
    channels: u16,
    cancelled: &AtomicBool,
) -> Result<(), GenerationError> {
    check_cancelled(cancelled)?;
    if samples.is_empty()
        || !samples.len().is_multiple_of(usize::from(channels))
        || samples.len() / usize::from(channels) > MAX_FRAMES
        || !(8_000..=192_000).contains(&sample_rate_hz)
        || samples.iter().any(|v| !v.is_finite())
    {
        return Err(GenerationError::InvalidAudio);
    }
    let spec = hound::WavSpec {
        channels,
        sample_rate: sample_rate_hz,
        bits_per_sample: 32,
        sample_format: hound::SampleFormat::Float,
    };
    let mut writer = hound::WavWriter::new(output, spec).map_err(|_| GenerationError::Io)?;
    for (index, sample) in samples.iter().enumerate() {
        if index % 4096 == 0 {
            check_cancelled(cancelled)?;
        }
        writer
            .write_sample(*sample)
            .map_err(|_| GenerationError::Io)?;
    }
    check_cancelled(cancelled)?;
    writer.finalize().map_err(|_| GenerationError::Io)
}

pub fn read_stereo_wav<R: Read + Seek>(
    input: R,
    sample_rate_hz: u32,
    frames: usize,
    cancelled: &AtomicBool,
) -> Result<Vec<f32>, GenerationError> {
    check_cancelled(cancelled)?;
    if frames == 0 || frames > MAX_FRAMES {
        return Err(GenerationError::ResourceLimit);
    }
    let mut reader = hound::WavReader::new(input).map_err(|_| GenerationError::InvalidAudio)?;
    let spec = reader.spec();
    if spec.channels != 2
        || spec.sample_rate != sample_rate_hz
        || spec.bits_per_sample != 32
        || spec.sample_format != hound::SampleFormat::Float
        || reader.len() as usize != frames * 2
    {
        return Err(GenerationError::InvalidAudio);
    }
    let mut pcm = Vec::new();
    pcm.try_reserve_exact(frames * 2)
        .map_err(|_| GenerationError::ResourceLimit)?;
    for (index, sample) in reader.samples::<f32>().enumerate() {
        if index % 4096 == 0 {
            check_cancelled(cancelled)?;
        }
        let sample = sample.map_err(|_| GenerationError::InvalidAudio)?;
        if !sample.is_finite() || pcm.len() == frames * 2 {
            return Err(GenerationError::InvalidAudio);
        }
        pcm.push(sample);
    }
    if pcm.len() != frames * 2 {
        return Err(GenerationError::InvalidAudio);
    }
    Ok(pcm)
}
