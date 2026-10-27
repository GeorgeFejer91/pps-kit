use crate::{check_cancelled, GenerationError, LevelPolicy, PreparedStimulus, TrajectorySpec};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{io::Write, sync::atomic::AtomicBool};

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum HrtfFormat {
    Sofa,
    ThreeDti,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SpatializerOptions {
    /// A native-authorized local HRTF asset, never a browser-supplied path.
    pub hrtf_path: String,
    pub hrtf_format: HrtfFormat,
    pub head_radius_m: f64,
    pub distance_attenuation: bool,
    pub near_field: bool,
    pub propagation_delay: bool,
}

#[derive(Debug, Serialize)]
pub struct SpatializerConfig {
    pub schema: &'static str,
    pub sample_rate_hz: u32,
    pub frames: usize,
    pub dry_source: DrySource,
    pub trajectory: TrajectorySpec,
    pub spatialization: Spatialization,
    pub hrtf: Hrtf,
}

#[derive(Debug, Serialize)]
pub struct DrySource {
    pub path: &'static str,
    pub sha256: String,
    pub algorithm: &'static str,
}
#[derive(Debug, Serialize)]
pub struct Hrtf {
    pub path: String,
    pub format: HrtfFormat,
}
#[derive(Debug, Serialize)]
pub struct Spatialization {
    pub far_distance_filter: bool,
    pub distance_attenuation: bool,
    pub near_field: bool,
    pub propagation_delay: bool,
    pub head_radius_m: f64,
    pub normalization: &'static str,
    pub output_channels: u8,
}

/// Write `dry.f32` in a caller-owned staging directory, returning the config
/// to serialize beside it. This does not execute, publish, or choose file paths.
pub fn write_spatializer_input<W: Write>(
    prepared: &PreparedStimulus,
    mut dry_file: W,
    options: &SpatializerOptions,
    cancelled: &AtomicBool,
) -> Result<SpatializerConfig, GenerationError> {
    check_cancelled(cancelled)?;
    if options.near_field {
        return Err(GenerationError::Invalid(
            "near_field_requires_verified_ild_asset",
        ));
    }
    if options.hrtf_path.is_empty()
        || options.hrtf_path.len() > 4096
        || !options.head_radius_m.is_finite()
        || !(0.04..=0.15).contains(&options.head_radius_m)
    {
        return Err(GenerationError::Invalid("spatializer_options"));
    }
    let minimum_distance = prepared.request.trajectory.minimum_distance();
    if minimum_distance <= options.head_radius_m {
        return Err(GenerationError::Invalid("source_inside_listener_head"));
    }
    // A calibrated dB ramp is the sole distance-level controller for that mode.
    if matches!(prepared.request.level, LevelPolicy::LinearDbRamp { .. })
        && options.distance_attenuation
    {
        return Err(GenerationError::Invalid("ramp_with_distance_attenuation"));
    }
    let mut digest = Sha256::new();
    for chunk in prepared.dry.chunks(4096) {
        check_cancelled(cancelled)?;
        let mut bytes = [0_u8; 4096 * 4];
        for (sample, output) in chunk.iter().zip(bytes.chunks_exact_mut(4)) {
            output.copy_from_slice(&sample.to_le_bytes());
        }
        let bytes = &bytes[..chunk.len() * 4];
        digest.update(bytes);
        dry_file.write_all(bytes).map_err(|_| GenerationError::Io)?;
    }
    check_cancelled(cancelled)?;
    Ok(SpatializerConfig {
        schema: "pps-3dti-spatialize.v2",
        sample_rate_hz: prepared.request.sample_rate_hz,
        frames: prepared.dry.len(),
        dry_source: DrySource {
            path: "dry.f32",
            sha256: format!("{:x}", digest.finalize()),
            algorithm: crate::SOURCE_ALGORITHM,
        },
        trajectory: prepared.request.trajectory.clone(),
        spatialization: Spatialization {
            far_distance_filter: false,
            distance_attenuation: options.distance_attenuation,
            near_field: options.near_field,
            propagation_delay: options.propagation_delay,
            head_radius_m: options.head_radius_m,
            normalization: "none",
            output_channels: 2,
        },
        hrtf: Hrtf {
            path: options.hrtf_path.clone(),
            format: options.hrtf_format,
        },
    })
}
