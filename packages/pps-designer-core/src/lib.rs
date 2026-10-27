//! Bounded offline stimulus preparation. No playback, job authority or Python runtime.
mod imported;
mod level;
mod source;
mod spatializer;
mod wav;

use serde::{Deserialize, Serialize};
use std::sync::atomic::{AtomicBool, Ordering};

pub use imported::prepare_imported_wav;
pub use level::{compose_spatial_output, GeneratedStimulus, LevelQc};
pub use spatializer::{write_spatializer_input, HrtfFormat, SpatializerConfig, SpatializerOptions};
pub use wav::{read_stereo_wav, write_mono_wav, write_stimulus_wav};

pub const REQUEST_SCHEMA: &str = "pps-native-generation.v1";
pub const SOURCE_ALGORITHM: &str = "rand-0.8.8-std-rng-box-muller.v1";
pub const IMPORT_ALGORITHM: &str = "wav-pcm-dry.v1";
pub const MAX_FRAMES: usize = 192_000 * 60;
pub const MAX_SPECTRAL_FRAMES: usize = 1_048_576;
pub const MAX_TACTILE_CUES: usize = 256;

/// Implemented kernel semantics; the host must separately verify its renderer
/// executable/resources and never interpret these as replication qualification.
pub fn generation_capabilities() -> serde_json::Value {
    serde_json::json!({"schema":"pps-native-generation-capabilities.v1",
        "source_algorithms":[SOURCE_ALGORITHM,IMPORT_ALGORITHM],"legacy_numpy_seed_compatible":false,
        "noise_colors":["white","pink","blue","violet","brown"],
        "source_profiles":["continuous","gaussian_burst_train"],
        "burst_policy":"duration_derived_symmetric_fit_endpoint_exclusive",
        "trajectory_modes":["fixed","linear","polar"],
        "imported_wav":{"encodings":["pcm16","pcm24","pcm32","float32"],"channels":["mono","stereo_mean"],
            "length_policies":["exact","trim_or_zero_pad"],"sample_rate_policy":"exact_match","sha256_required":true},
        "level_modes":["preserve","linear_db_ramp"],"physical_spl_qualified":false,
        "renderer_contract":"pps-3dti-spatialize.v2","near_field_ild":false,"far_distance_filter":false,
        "max_frames":MAX_FRAMES,"max_spectral_frames":MAX_SPECTRAL_FRAMES,"max_tactile_cues":MAX_TACTILE_CUES})
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum GenerationError {
    Invalid(&'static str),
    ResourceLimit,
    Cancelled,
    SilentCalibrationWindow,
    PeakCeilingExceeded,
    InvalidAudio,
    Io,
}

impl std::fmt::Display for GenerationError {
    fn fmt(&self, out: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(out, "{self:?}")
    }
}
impl std::error::Error for GenerationError {}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct GenerationRequest {
    pub schema: String,
    pub source_algorithm: String,
    pub sample_rate_hz: u32,
    pub duration_s: f64,
    pub seed: u64,
    pub source: SourceSpec,
    pub trajectory: TrajectorySpec,
    pub tactile: Vec<TactileCue>,
    pub level: LevelPolicy,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum SourceSpec {
    ContinuousWhite,
    GaussianBurstTrain {
        onset_s: f64,
        active_window_s: f64,
        burst_duration_s: f64,
        rise_fall_s: f64,
        target_period_s: f64,
    },
    Noise {
        color: NoiseColor,
        profile: SourceProfile,
    },
    ImportedWav {
        sha256: String,
        channel_policy: ImportChannelPolicy,
        length_policy: ImportLengthPolicy,
    },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NoiseColor {
    White,
    Pink,
    Blue,
    Violet,
    Brown,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum SourceProfile {
    Continuous,
    GaussianBurstTrain {
        onset_s: f64,
        active_window_s: f64,
        burst_duration_s: f64,
        rise_fall_s: f64,
        target_period_s: f64,
    },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ImportChannelPolicy {
    Mono,
    StereoMean,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ImportLengthPolicy {
    Exact,
    TrimOrZeroPad,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Position {
    pub x_m: f64,
    pub y_m: f64,
    pub z_m: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum TrajectorySpec {
    Fixed {
        position: Position,
    },
    Linear {
        start: Position,
        end: Position,
        pre_hold_s: f64,
        movement_duration_s: f64,
    },
    Polar {
        start_radius_m: f64,
        end_radius_m: f64,
        azimuth_start_deg: f64,
        azimuth_end_deg: f64,
        elevation_deg: f64,
        pre_hold_s: f64,
        movement_duration_s: f64,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TactileCue {
    pub onset_s: f64,
    pub duration_s: f64,
    pub attack_frequency_hz: f64,
    pub decay_frequency_hz: f64,
    pub peak_amplitude: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum LevelPolicy {
    Preserve {
        gain_db: f64,
        peak_ceiling_dbfs: f64,
    },
    LinearDbRamp {
        start_rms_dbfs: f64,
        end_rms_dbfs: f64,
        pre_hold_s: f64,
        movement_duration_s: f64,
        calibration_window_s: f64,
        peak_ceiling_dbfs: f64,
    },
}

#[derive(Debug, Clone, Serialize)]
pub struct SourceQc {
    pub seed: u64,
    pub source_algorithm: &'static str,
    pub numpy_seed_compatible: bool,
    pub frames: usize,
    pub burst_onset_frames: Vec<usize>,
    pub burst_frames: Option<usize>,
    pub burst_envelope_algorithm: Option<&'static str>,
    pub noise_color: Option<NoiseColor>,
    pub color_algorithm: Option<&'static str>,
    pub imported_sha256: Option<String>,
    pub peak: f64,
    pub rms: f64,
}

pub struct PreparedStimulus {
    request: GenerationRequest,
    dry: Vec<f32>,
    tactile: Vec<f32>,
    qc: SourceQc,
}

impl PreparedStimulus {
    pub fn request(&self) -> &GenerationRequest {
        &self.request
    }
    pub fn dry_pcm(&self) -> &[f32] {
        &self.dry
    }
    pub fn tactile_pcm(&self) -> &[f32] {
        &self.tactile
    }
    pub fn source_qc(&self) -> &SourceQc {
        &self.qc
    }
    pub fn position_at(&self, time_s: f64) -> Result<Position, GenerationError> {
        if !time_s.is_finite() || time_s < 0.0 || time_s > self.request.duration_s {
            return Err(GenerationError::Invalid("trajectory_time"));
        }
        Ok(self.request.trajectory.position_at(time_s))
    }
}

impl std::fmt::Debug for PreparedStimulus {
    fn fmt(&self, out: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        out.debug_struct("PreparedStimulus")
            .field("frames", &self.dry.len())
            .finish_non_exhaustive()
    }
}

impl TrajectorySpec {
    fn position_at(&self, time_s: f64) -> Position {
        match *self {
            Self::Fixed { position } => position,
            Self::Linear {
                start,
                end,
                pre_hold_s,
                movement_duration_s,
            } => {
                let fraction = ((time_s - pre_hold_s) / movement_duration_s).clamp(0.0, 1.0);
                Position {
                    x_m: start.x_m + fraction * (end.x_m - start.x_m),
                    y_m: start.y_m + fraction * (end.y_m - start.y_m),
                    z_m: start.z_m + fraction * (end.z_m - start.z_m),
                }
            }
            Self::Polar {
                start_radius_m,
                end_radius_m,
                azimuth_start_deg,
                azimuth_end_deg,
                elevation_deg,
                pre_hold_s,
                movement_duration_s,
            } => {
                let fraction = ((time_s - pre_hold_s) / movement_duration_s).clamp(0.0, 1.0);
                let radius = start_radius_m + fraction * (end_radius_m - start_radius_m);
                let azimuth = (azimuth_start_deg
                    + fraction * (azimuth_end_deg - azimuth_start_deg))
                    .to_radians();
                let elevation = elevation_deg.to_radians();
                Position {
                    x_m: radius * elevation.cos() * azimuth.sin(),
                    y_m: radius * elevation.cos() * azimuth.cos(),
                    z_m: radius * elevation.sin(),
                }
            }
        }
    }

    fn minimum_distance(&self) -> f64 {
        match *self {
            Self::Fixed { position } => segment_clearance(position, position),
            Self::Linear { start, end, .. } => segment_clearance(start, end),
            Self::Polar {
                start_radius_m,
                end_radius_m,
                ..
            } => start_radius_m.min(end_radius_m),
        }
    }
}

pub fn prepare(
    request: &GenerationRequest,
    cancelled: &AtomicBool,
) -> Result<PreparedStimulus, GenerationError> {
    check_cancelled(cancelled)?;
    let frames = validate(request)?;
    let (dry, qc) = source::generate_source(request, frames, cancelled)?;
    let tactile = source::generate_tactile(request, frames, cancelled)?;
    check_cancelled(cancelled)?;
    Ok(PreparedStimulus {
        request: request.clone(),
        dry,
        tactile,
        qc,
    })
}

fn validate(request: &GenerationRequest) -> Result<usize, GenerationError> {
    let expected_algorithm = if matches!(request.source, SourceSpec::ImportedWav { .. }) {
        IMPORT_ALGORITHM
    } else {
        SOURCE_ALGORITHM
    };
    if request.schema != REQUEST_SCHEMA || request.source_algorithm != expected_algorithm {
        return Err(GenerationError::Invalid("schema_or_source_algorithm"));
    }
    if !(8_000..=192_000).contains(&request.sample_rate_hz)
        || !request.duration_s.is_finite()
        || request.duration_s <= 0.0
        || request.duration_s > 60.0
    {
        return Err(GenerationError::Invalid("sample_rate_or_duration"));
    }
    let frames = sample_index(request.duration_s, request.sample_rate_hz);
    if frames == 0 || frames > MAX_FRAMES || request.tactile.len() > MAX_TACTILE_CUES {
        return Err(GenerationError::ResourceLimit);
    }
    let valid_position = |p: Position| {
        [p.x_m, p.y_m, p.z_m]
            .iter()
            .all(|v| v.is_finite() && v.abs() <= 100.0)
            && (p.x_m * p.x_m + p.y_m * p.y_m + p.z_m * p.z_m) >= 0.0001
    };
    match request.trajectory {
        TrajectorySpec::Fixed { position } if valid_position(position) => (),
        TrajectorySpec::Linear {
            start,
            end,
            pre_hold_s,
            movement_duration_s,
        } if valid_position(start)
            && valid_position(end)
            && segment_clearance(start, end) >= 0.01
            && pre_hold_s.is_finite()
            && pre_hold_s >= 0.0
            && movement_duration_s.is_finite()
            && movement_duration_s > 0.0
            && pre_hold_s + movement_duration_s <= request.duration_s => {}
        TrajectorySpec::Polar {
            start_radius_m,
            end_radius_m,
            azimuth_start_deg,
            azimuth_end_deg,
            elevation_deg,
            pre_hold_s,
            movement_duration_s,
        } if [
            start_radius_m,
            end_radius_m,
            azimuth_start_deg,
            azimuth_end_deg,
            elevation_deg,
            pre_hold_s,
            movement_duration_s,
        ]
        .iter()
        .all(|v| v.is_finite())
            && (0.01..=100.0).contains(&start_radius_m)
            && (0.01..=100.0).contains(&end_radius_m)
            && (-360.0..=360.0).contains(&azimuth_start_deg)
            && (-360.0..=360.0).contains(&azimuth_end_deg)
            && (-90.0..=90.0).contains(&elevation_deg)
            && pre_hold_s >= 0.0
            && movement_duration_s > 0.0
            && pre_hold_s + movement_duration_s <= request.duration_s => {}
        _ => return Err(GenerationError::Invalid("trajectory")),
    }
    level::validate_level(&request.level, request.duration_s)?;
    Ok(frames)
}

fn segment_clearance(start: Position, end: Position) -> f64 {
    let a = [start.x_m, start.y_m, start.z_m];
    let delta = [
        end.x_m - start.x_m,
        end.y_m - start.y_m,
        end.z_m - start.z_m,
    ];
    let length_squared = delta.iter().map(|v| v * v).sum::<f64>();
    let fraction = if length_squared > 0.0 {
        (-a.iter().zip(delta).map(|(a, d)| a * d).sum::<f64>() / length_squared).clamp(0.0, 1.0)
    } else {
        0.0
    };
    a.iter()
        .zip(delta)
        .map(|(a, d)| (a + fraction * d).powi(2))
        .sum::<f64>()
        .sqrt()
}

fn check_cancelled(cancelled: &AtomicBool) -> Result<(), GenerationError> {
    if cancelled.load(Ordering::Acquire) {
        Err(GenerationError::Cancelled)
    } else {
        Ok(())
    }
}

fn zeroed(frames: usize) -> Result<Vec<f32>, GenerationError> {
    let mut pcm = Vec::new();
    pcm.try_reserve_exact(frames)
        .map_err(|_| GenerationError::ResourceLimit)?;
    pcm.resize(frames, 0.0);
    Ok(pcm)
}

fn sample_index(seconds: f64, rate: u32) -> usize {
    (seconds * f64::from(rate)).round_ties_even() as usize
}

fn peak(pcm: &[f32]) -> f64 {
    pcm.iter().map(|v| f64::from(v.abs())).fold(0.0, f64::max)
}
fn rms(pcm: &[f32]) -> f64 {
    (pcm.iter().map(|v| f64::from(*v).powi(2)).sum::<f64>() / pcm.len().max(1) as f64).sqrt()
}
