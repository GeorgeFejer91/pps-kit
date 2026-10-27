use crate::{
    check_cancelled, peak, rms, sample_index, zeroed, GenerationError, GenerationRequest, SourceQc,
    SourceSpec, SOURCE_ALGORITHM,
};
use rand::{rngs::StdRng, RngCore, SeedableRng};
use std::{f64::consts::PI, sync::atomic::AtomicBool};

pub(crate) fn generate_source(
    request: &GenerationRequest,
    frames: usize,
    cancelled: &AtomicBool,
) -> Result<(Vec<f32>, SourceQc), GenerationError> {
    let mut pcm = zeroed(frames)?;
    let (onsets, burst_frames) = match request.source {
        SourceSpec::ContinuousWhite => {
            white(&mut pcm, request.seed, cancelled)?;
            (Vec::new(), None)
        }
        SourceSpec::GaussianBurstTrain {
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
        peak: peak(&pcm),
        rms: rms(&pcm),
    };
    Ok((pcm, qc))
}

fn raised_cosine(index: usize, edge: usize) -> f64 {
    if edge <= 1 {
        0.0
    } else {
        0.5 - 0.5 * (PI * index as f64 / (edge - 1) as f64).cos()
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
