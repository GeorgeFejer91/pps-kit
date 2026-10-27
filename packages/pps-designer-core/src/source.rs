use crate::{
    check_cancelled, peak, rms, sample_index, zeroed, GenerationError, GenerationRequest,
    NoiseColor, SourceProfile, SourceQc, SourceSpec, MAX_SPECTRAL_FRAMES, SOURCE_ALGORITHM,
};
use rand::{rngs::StdRng, RngCore, SeedableRng};
use rustfft::{num_complex::Complex, FftPlanner};
use std::{f64::consts::PI, sync::atomic::AtomicBool};

pub(crate) fn generate_source(
    request: &GenerationRequest,
    frames: usize,
    cancelled: &AtomicBool,
) -> Result<(Vec<f32>, SourceQc), GenerationError> {
    let (color, profile) = match &request.source {
        SourceSpec::ContinuousWhite => (NoiseColor::White, SourceProfile::Continuous),
        SourceSpec::GaussianBurstTrain {
            onset_s,
            active_window_s,
            burst_duration_s,
            rise_fall_s,
            target_period_s,
        } => (
            NoiseColor::White,
            SourceProfile::GaussianBurstTrain {
                onset_s: *onset_s,
                active_window_s: *active_window_s,
                burst_duration_s: *burst_duration_s,
                rise_fall_s: *rise_fall_s,
                target_period_s: *target_period_s,
            },
        ),
        SourceSpec::Noise { color, profile } => (*color, *profile),
        SourceSpec::ImportedWav { .. } => {
            return Err(GenerationError::Invalid("imported_bytes_required"))
        }
    };
    let mut planner = FftPlanner::<f64>::new();
    if matches!(profile, SourceProfile::Continuous)
        && spectral_color(color)
        && frames > MAX_SPECTRAL_FRAMES
    {
        return Err(GenerationError::ResourceLimit);
    }
    let mut pcm = zeroed(frames)?;
    let (onsets, burst_frames) = match profile {
        SourceProfile::Continuous => {
            white(&mut pcm, request.seed, cancelled)?;
            color_noise(
                &mut pcm,
                color,
                request.sample_rate_hz,
                &mut planner,
                cancelled,
            )?;
            (Vec::new(), None)
        }
        SourceProfile::GaussianBurstTrain {
            onset_s,
            active_window_s,
            burst_duration_s,
            rise_fall_s,
            target_period_s,
        } => {
            let values = [
                onset_s,
                active_window_s,
                burst_duration_s,
                rise_fall_s,
                target_period_s,
            ];
            if values.iter().any(|v| !v.is_finite())
                || onset_s < 0.0
                || active_window_s <= 0.0
                || burst_duration_s < 0.001
                || burst_duration_s > active_window_s
                || rise_fall_s < 0.0
                || rise_fall_s > burst_duration_s / 2.0
                || target_period_s < burst_duration_s
                || onset_s + active_window_s > request.duration_s
            {
                return Err(GenerationError::Invalid("burst_parameters"));
            }
            let span = active_window_s - burst_duration_s;
            let count = (((span / target_period_s) + 0.5).floor() as usize + 1)
                .min((span / burst_duration_s).floor() as usize + 1);
            let count = count.max(1);
            let length = sample_index(burst_duration_s, request.sample_rate_hz).max(1);
            if spectral_color(color) && length > MAX_SPECTRAL_FRAMES {
                return Err(GenerationError::ResourceLimit);
            }
            let edge = sample_index(rise_fall_s, request.sample_rate_hz).min(length / 2);
            let mut burst = zeroed(length)?;
            let mut onsets = Vec::with_capacity(count);
            for index in 0..count {
                check_cancelled(cancelled)?;
                let onset = onset_s
                    + if count == 1 {
                        span / 2.0
                    } else {
                        index as f64 * span / (count - 1) as f64
                    };
                let first = sample_index(onset, request.sample_rate_hz);
                if first.checked_add(length).is_none_or(|last| last > frames) {
                    return Err(GenerationError::Invalid("burst_sample_boundary"));
                }
                white(
                    &mut burst,
                    request.seed.wrapping_add(index as u64 * 37),
                    cancelled,
                )?;
                color_noise(
                    &mut burst,
                    color,
                    request.sample_rate_hz,
                    &mut planner,
                    cancelled,
                )?;
                for (frame, sample) in burst.iter().enumerate() {
                    let envelope = if frame < edge {
                        raised_cosine(frame, edge)
                    } else if frame >= length - edge {
                        raised_cosine(length - 1 - frame, edge)
                    } else {
                        1.0
                    };
                    pcm[first + frame] += *sample * envelope as f32;
                }
                onsets.push(first);
            }
            normalize_peak(&mut pcm);
            (onsets, Some(length))
        }
    };
    let qc = SourceQc {
        seed: request.seed,
        source_algorithm: SOURCE_ALGORITHM,
        numpy_seed_compatible: false,
        frames,
        burst_onset_frames: onsets,
        burst_frames,
        burst_envelope_algorithm: burst_frames.map(|_| "raised-cosine-endpoint-exclusive.v1"),
        noise_color: Some(color),
        color_algorithm: Some(match color {
            NoiseColor::White => "identity.v1",
            NoiseColor::Brown => "cumulative-sum.v1",
            _ => "reference-spectral-shaping-rustfft-6.4.1.v1",
        }),
        imported_sha256: None,
        peak: peak(&pcm),
        rms: rms(&pcm),
    };
    Ok((pcm, qc))
}

fn spectral_color(color: NoiseColor) -> bool {
    matches!(
        color,
        NoiseColor::Pink | NoiseColor::Blue | NoiseColor::Violet
    )
}

fn complex_buffer(length: usize) -> Result<Vec<Complex<f64>>, GenerationError> {
    let mut buffer = Vec::new();
    buffer
        .try_reserve_exact(length)
        .map_err(|_| GenerationError::ResourceLimit)?;
    buffer.resize(length, Complex::new(0.0, 0.0));
    Ok(buffer)
}

fn color_noise(
    pcm: &mut [f32],
    color: NoiseColor,
    rate: u32,
    planner: &mut FftPlanner<f64>,
    cancelled: &AtomicBool,
) -> Result<(), GenerationError> {
    check_cancelled(cancelled)?;
    match color {
        NoiseColor::White => return Ok(()),
        NoiseColor::Brown => {
            let mut sum = 0.0_f64;
            for (index, sample) in pcm.iter_mut().enumerate() {
                if index % 4096 == 0 {
                    check_cancelled(cancelled)?;
                }
                sum += f64::from(*sample);
                *sample = sum as f32;
            }
        }
        NoiseColor::Pink | NoiseColor::Blue | NoiseColor::Violet => {
            if pcm.len() > MAX_SPECTRAL_FRAMES {
                return Err(GenerationError::ResourceLimit);
            }
            let length = pcm.len();
            let forward = planner.plan_fft_forward(length);
            let inverse = planner.plan_fft_inverse(length);
            let scratch_len = forward
                .get_inplace_scratch_len()
                .max(inverse.get_inplace_scratch_len());
            if scratch_len > MAX_SPECTRAL_FRAMES * 4 {
                return Err(GenerationError::ResourceLimit);
            }
            let mut scratch = complex_buffer(scratch_len)?;
            let mut spectrum = complex_buffer(length)?;
            for (s, sample) in spectrum.iter_mut().zip(pcm.iter()) {
                s.re = f64::from(*sample);
            }
            check_cancelled(cancelled)?;
            forward.process_with_scratch(&mut spectrum, &mut scratch);
            check_cancelled(cancelled)?;
            for (bin, sample) in spectrum.iter_mut().enumerate() {
                if bin % 4096 == 0 {
                    check_cancelled(cancelled)?;
                }
                // Preserve the reference's nonzero DC substitution and mirrored
                // real spectrum, including odd sample counts.
                let frequency =
                    bin.min(length - bin).max(1) as f64 * f64::from(rate) / length as f64;
                let gain = match color {
                    NoiseColor::Pink => 1.0 / frequency.sqrt(),
                    NoiseColor::Blue => frequency.sqrt(),
                    _ => frequency,
                };
                *sample *= gain;
            }
            inverse.process_with_scratch(&mut spectrum, &mut scratch);
            check_cancelled(cancelled)?;
            for (sample, value) in pcm.iter_mut().zip(spectrum) {
                *sample = (value.re / length as f64) as f32;
            }
        }
    }
    normalize_peak(pcm);
    check_cancelled(cancelled)
}

fn raised_cosine(index: usize, edge: usize) -> f64 {
    if edge <= 1 {
        0.0
    } else {
        0.5 - 0.5 * (PI * index as f64 / edge as f64).cos()
    }
}

fn white(pcm: &mut [f32], seed: u64, cancelled: &AtomicBool) -> Result<(), GenerationError> {
    let mut rng = StdRng::seed_from_u64(seed);
    for (index, pair) in pcm.chunks_mut(2).enumerate() {
        if index % 2048 == 0 {
            check_cancelled(cancelled)?;
        }
        // Open-unit uniforms avoid log(0); the exact RNG release is part of provenance.
        let u1 = ((rng.next_u64() >> 11) as f64 + 0.5) / 9_007_199_254_740_992.0;
        let u2 = ((rng.next_u64() >> 11) as f64 + 0.5) / 9_007_199_254_740_992.0;
        let radius = (-2.0 * u1.ln()).sqrt();
        pair[0] = (radius * (2.0 * PI * u2).cos()) as f32;
        if pair.len() == 2 {
            pair[1] = (radius * (2.0 * PI * u2).sin()) as f32;
        }
    }
    normalize_peak(pcm);
    Ok(())
}

fn normalize_peak(pcm: &mut [f32]) {
    let maximum = peak(pcm) as f32;
    if maximum > 0.0 {
        for sample in pcm {
            *sample /= maximum;
        }
    }
}

pub(crate) fn generate_tactile(
    request: &GenerationRequest,
    frames: usize,
    cancelled: &AtomicBool,
) -> Result<Vec<f32>, GenerationError> {
    let mut channel = zeroed(frames)?;
    for cue in &request.tactile {
        check_cancelled(cancelled)?;
        let values = [
            cue.onset_s,
            cue.duration_s,
            cue.attack_frequency_hz,
            cue.decay_frequency_hz,
            cue.peak_amplitude,
        ];
        if values.iter().any(|v| !v.is_finite())
            || cue.onset_s < 0.0
            || cue.duration_s <= 0.0
            || cue.onset_s + cue.duration_s > request.duration_s
            || cue.peak_amplitude <= 0.0
            || cue.peak_amplitude > 1.0
            || cue.attack_frequency_hz <= 0.0
            || cue.attack_frequency_hz >= f64::from(request.sample_rate_hz) / 2.0
            || cue.decay_frequency_hz <= 0.0
            || cue.decay_frequency_hz >= f64::from(request.sample_rate_hz) / 2.0
        {
            return Err(GenerationError::Invalid("tactile_cue"));
        }
        let first = sample_index(cue.onset_s, request.sample_rate_hz);
        let length = sample_index(cue.duration_s, request.sample_rate_hz).max(1);
        if first.checked_add(length).is_none_or(|last| last > frames) {
            return Err(GenerationError::Invalid("tactile_sample_boundary"));
        }
        let attack = sample_index(0.02, request.sample_rate_hz)
            .min(length)
            .max(1);
        let mut waveform = zeroed(length)?;
        for (index, sample) in waveform.iter_mut().enumerate() {
            if index % 4096 == 0 {
                check_cancelled(cancelled)?;
            }
            let hz = if index < attack {
                cue.attack_frequency_hz
            } else {
                cue.decay_frequency_hz
            };
            let hann = 0.5
                - 0.5
                    * (2.0 * PI * index as f64 / (length * 2).max(4).saturating_sub(1) as f64)
                        .cos();
            *sample = ((2.0 * PI * hz * index as f64 / f64::from(request.sample_rate_hz)).sin()
                * hann) as f32;
        }
        if peak(&waveform) == 0.0 {
            return Err(GenerationError::Invalid("silent_tactile_cue"));
        }
        normalize_peak(&mut waveform);
        for (index, sample) in waveform.iter().enumerate() {
            channel[first + index] += *sample * cue.peak_amplitude as f32;
        }
    }
    if peak(&channel) > 1.0 {
        return Err(GenerationError::PeakCeilingExceeded);
    }
    Ok(channel)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reference_spectral_shapes_match_shared_input_without_seed_parity_claims() {
        let fixture: serde_json::Value =
            serde_json::from_str(include_str!("../tests/fixtures/spectral_reference.json"))
                .unwrap();
        for (name, color) in [
            ("pink", NoiseColor::Pink),
            ("blue", NoiseColor::Blue),
            ("violet", NoiseColor::Violet),
            ("brown", NoiseColor::Brown),
        ] {
            let mut pcm: Vec<f32> = fixture["white_input"]
                .as_array()
                .unwrap()
                .iter()
                .map(|v| v.as_f64().unwrap() as f32)
                .collect();
            color_noise(
                &mut pcm,
                color,
                8000,
                &mut FftPlanner::new(),
                &AtomicBool::new(false),
            )
            .unwrap();
            for (actual, expected) in pcm.iter().zip(fixture["outputs"][name].as_array().unwrap()) {
                assert!(
                    (f64::from(*actual) - expected.as_f64().unwrap()).abs() < 2e-6,
                    "{name} shared-input waveform drift"
                );
            }
        }
    }
}
