use crate::{
    check_cancelled, peak, sample_index, zeroed, GenerationError, LevelPolicy, PreparedStimulus,
};
use serde::Serialize;
use std::sync::atomic::AtomicBool;

#[derive(Debug, Clone, Serialize)]
pub struct LevelQc {
    pub kind: &'static str,
    pub physical_spl_qualified: bool,
    pub applied_gain_db: f64,
    pub audio_peak_dbfs: f64,
    pub target_peak_dbfs: Option<f64>,
    pub calibration_window_frames: Option<[usize; 2]>,
    pub target_window_rms_dbfs: Option<f64>,
    pub actual_window_rms_dbfs: Option<f64>,
}

pub struct GeneratedStimulus {
    pub sample_rate_hz: u32,
    pub interleaved_pcm: Vec<f32>,
    pub source_qc: crate::SourceQc,
    pub level_qc: LevelQc,
}

impl std::fmt::Debug for GeneratedStimulus {
    fn fmt(&self, out: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        out.debug_struct("GeneratedStimulus")
            .field("frames", &(self.interleaved_pcm.len() / 3))
            .finish_non_exhaustive()
    }
}

pub fn compose_spatial_output(
    prepared: PreparedStimulus,
    mut stereo: Vec<f32>,
    cancelled: &AtomicBool,
) -> Result<GeneratedStimulus, GenerationError> {
    check_cancelled(cancelled)?;
    if stereo.len() != prepared.dry.len() * 2 || stereo.iter().any(|v| !v.is_finite()) {
        return Err(GenerationError::InvalidAudio);
    }
    let rate = prepared.request.sample_rate_hz;
    let frames = prepared.dry.len();
    let (gain, ceiling, mut qc) = level_gain(
        &prepared.request.level,
        &mut stereo,
        rate,
        frames,
        cancelled,
    )?;
    for (index, sample) in stereo.iter_mut().enumerate() {
        if index % 4096 == 0 {
            check_cancelled(cancelled)?;
        }
        *sample *= gain as f32;
    }
    let actual_peak = peak(&stereo);
    if actual_peak > db_to_linear(ceiling) * (1.0 + 1e-7) {
        return Err(GenerationError::PeakCeilingExceeded);
    }
    qc.audio_peak_dbfs = linear_to_db(actual_peak);
    if let Some([start, stop]) = qc.calibration_window_frames {
        qc.actual_window_rms_dbfs = Some(linear_to_db(window_rms(&stereo, start, stop)));
    }
    let mut interleaved = zeroed(frames * 3)?;
    for (index, output) in interleaved.chunks_exact_mut(3).enumerate() {
        if index % 4096 == 0 {
            check_cancelled(cancelled)?;
        }
        output.copy_from_slice(&[
            stereo[index * 2],
            stereo[index * 2 + 1],
            prepared.tactile[index],
        ]);
    }
    Ok(GeneratedStimulus {
        sample_rate_hz: rate,
        interleaved_pcm: interleaved,
        source_qc: prepared.qc,
        level_qc: qc,
    })
}

fn level_gain(
    policy: &LevelPolicy,
    stereo: &mut [f32],
    rate: u32,
    frames: usize,
    cancelled: &AtomicBool,
) -> Result<(f64, f64, LevelQc), GenerationError> {
    let mut qc = LevelQc {
        kind: "preserve",
        physical_spl_qualified: false,
        applied_gain_db: 0.0,
        audio_peak_dbfs: -300.0,
        target_peak_dbfs: None,
        calibration_window_frames: None,
        target_window_rms_dbfs: None,
        actual_window_rms_dbfs: None,
    };
    match *policy {
        LevelPolicy::Preserve {
            gain_db,
            peak_ceiling_dbfs,
        } => {
            qc.applied_gain_db = gain_db;
            Ok((db_to_linear(gain_db), peak_ceiling_dbfs, qc))
        }
        LevelPolicy::PeakNormalize {
            target_peak_dbfs,
            peak_ceiling_dbfs,
        } => {
            let measured = peak(stereo);
            if measured <= 0.0 {
                return Err(GenerationError::Invalid("silent_peak_normalization"));
            }
            let gain = db_to_linear(target_peak_dbfs) / measured;
            qc.kind = "peak_normalize";
            qc.applied_gain_db = linear_to_db(gain);
            qc.target_peak_dbfs = Some(target_peak_dbfs);
            Ok((gain, peak_ceiling_dbfs, qc))
        }
        LevelPolicy::LinearDbRamp {
            start_rms_dbfs,
            end_rms_dbfs,
            pre_hold_s,
            movement_duration_s,
            calibration_window_s,
            peak_ceiling_dbfs,
        } => {
            let stop = sample_index(pre_hold_s + movement_duration_s, rate).min(frames);
            let start = sample_index(
                (pre_hold_s + movement_duration_s - calibration_window_s).max(pre_hold_s),
                rate,
            );
            if stop <= start {
                return Err(GenerationError::Invalid("calibration_window"));
            }
            let mut target_power = 0.0;
            for (frame, pair) in stereo.chunks_exact_mut(2).enumerate() {
                if frame % 4096 == 0 {
                    check_cancelled(cancelled)?;
                }
                let fraction = ((frame as f64 / f64::from(rate) - pre_hold_s)
                    / movement_duration_s)
                    .clamp(0.0, 1.0);
                let db = start_rms_dbfs + fraction * (end_rms_dbfs - start_rms_dbfs);
                let envelope = db_to_linear(db - end_rms_dbfs) as f32;
                pair[0] *= envelope;
                pair[1] *= envelope;
                if (start..stop).contains(&frame) {
                    target_power += db_to_linear(db).powi(2);
                }
            }
            let measured = window_rms(stereo, start, stop);
            if measured <= 0.0 {
                return Err(GenerationError::SilentCalibrationWindow);
            }
            let target = (target_power / (stop - start) as f64).sqrt();
            let gain = target / measured;
            qc.kind = "linear_db_ramp";
            qc.applied_gain_db = linear_to_db(gain);
            qc.calibration_window_frames = Some([start, stop]);
            qc.target_window_rms_dbfs = Some(linear_to_db(target));
            Ok((gain, peak_ceiling_dbfs, qc))
        }
    }
}

pub(crate) fn validate_level(policy: &LevelPolicy, duration: f64) -> Result<(), GenerationError> {
    let valid_db = |db: f64| db.is_finite() && (-180.0..=0.0).contains(&db);
    let valid = match *policy {
        LevelPolicy::Preserve {
            gain_db,
            peak_ceiling_dbfs,
        } => {
            gain_db.is_finite() && (-180.0..=24.0).contains(&gain_db) && valid_db(peak_ceiling_dbfs)
        }
        LevelPolicy::PeakNormalize {
            target_peak_dbfs,
            peak_ceiling_dbfs,
        } => {
            valid_db(target_peak_dbfs)
                && valid_db(peak_ceiling_dbfs)
                && target_peak_dbfs <= peak_ceiling_dbfs
        }
        LevelPolicy::LinearDbRamp {
            start_rms_dbfs,
            end_rms_dbfs,
            pre_hold_s,
            movement_duration_s,
            calibration_window_s,
            peak_ceiling_dbfs,
        } => {
            valid_db(start_rms_dbfs)
                && valid_db(end_rms_dbfs)
                && valid_db(peak_ceiling_dbfs)
                && pre_hold_s.is_finite()
                && pre_hold_s >= 0.0
                && movement_duration_s.is_finite()
                && movement_duration_s > 0.0
                && pre_hold_s + movement_duration_s <= duration
                && calibration_window_s.is_finite()
                && calibration_window_s > 0.0
                && calibration_window_s <= movement_duration_s
        }
    };
    if valid {
        Ok(())
    } else {
        Err(GenerationError::Invalid("level_policy"))
    }
}

fn window_rms(stereo: &[f32], start: usize, stop: usize) -> f64 {
    (stereo[start * 2..stop * 2]
        .iter()
        .map(|v| f64::from(*v).powi(2))
        .sum::<f64>()
        / ((stop - start) * 2) as f64)
        .sqrt()
}
fn db_to_linear(db: f64) -> f64 {
    10.0_f64.powf(db / 20.0)
}
fn linear_to_db(amplitude: f64) -> f64 {
    if amplitude > 0.0 {
        20.0 * amplitude.log10()
    } else {
        -300.0
    }
}
