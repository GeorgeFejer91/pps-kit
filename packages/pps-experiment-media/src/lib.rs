//! Content-bound native trial media from an approved Planner profile.
//!
//! This binds one source WAV to the exact bytes in the verified inventory.
//! The standard-route assembler composes inventoried trials into one block.
//! Neither path publishes a run package or authorizes playback.

#![forbid(unsafe_code)]

pub mod block;

use std::fmt;

use pps_runner_audio::{
    bind_and_decode_verified_wav, AudioFence, AudioLoadLimits, PreparedPcmBlock, VerifiedWavRequest,
};
use pps_session_package::experiment_plan::ProfileTrialSource;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProfileMediaErrorCode {
    AudioHintMissing,
    FormatUnsupported,
    RowDigestMismatch,
    MediaChangedOrUnsupported,
    HintMismatch,
}

impl ProfileMediaErrorCode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::AudioHintMissing => "profile_audio_hint_missing",
            Self::FormatUnsupported => "profile_audio_format_unsupported",
            Self::RowDigestMismatch => "profile_audio_row_digest_mismatch",
            Self::MediaChangedOrUnsupported => "profile_audio_changed_or_unsupported",
            Self::HintMismatch => "profile_audio_hint_mismatch",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ProfileMediaError(ProfileMediaErrorCode);

impl ProfileMediaError {
    pub const fn code(self) -> &'static str {
        self.0.as_str()
    }
}

impl fmt::Display for ProfileMediaError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.code())
    }
}

impl std::error::Error for ProfileMediaError {}

/// Decode one inventoried PCM16 WAV through the existing single-handle
/// hash+decode owner. The caller retains native package/run admission fences.
pub fn bind_profile_trial_wav(
    trial: &ProfileTrialSource,
    fence: &AudioFence,
    limits: AudioLoadLimits,
) -> Result<PreparedPcmBlock, ProfileMediaError> {
    let ingredient = trial.ingredient();
    let hint = ingredient
        .audio()
        .ok_or(ProfileMediaError(ProfileMediaErrorCode::AudioHintMissing))?;
    if hint.format() != "WAV" || hint.sample_rate_hz() == 0 {
        return Err(ProfileMediaError(ProfileMediaErrorCode::FormatUnsupported));
    }
    if let Some(row_hash) = trial
        .fields()
        .get("source_sha256")
        .filter(|hash| !hash.trim().is_empty())
        .or_else(|| {
            trial
                .fields()
                .get("Source_SHA256")
                .filter(|hash| !hash.trim().is_empty())
        })
    {
        if row_hash.trim() != ingredient.sha256() {
            return Err(ProfileMediaError(ProfileMediaErrorCode::RowDigestMismatch));
        }
    }
    let media = bind_and_decode_verified_wav(VerifiedWavRequest {
        fence,
        path: ingredient.path(),
        expected_sha256: ingredient.sha256(),
        expected_encoded_byte_count: ingredient.bytes(),
        expected_sample_rate_hz: hint.sample_rate_hz(),
        limits,
    })
    .map_err(|_| ProfileMediaError(ProfileMediaErrorCode::MediaChangedOrUnsupported))?;
    if media.frames() != hint.frames() || media.channels() != hint.channels() {
        return Err(ProfileMediaError(ProfileMediaErrorCode::HintMismatch));
    }
    Ok(media)
}
