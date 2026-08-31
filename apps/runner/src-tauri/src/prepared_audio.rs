use pps_runner_audio::{
    bind_and_decode_verified_wav, AudioFence, AudioLoadLimits, AudioPreparationError,
    PpsChannelLayout, PreparedPcmBlock, VerifiedWavRequest, DEFAULT_MAXIMUM_DECODED_BYTES,
};
use pps_session_package::VerifiedPreparedWav;
use serde::Serialize;

pub(crate) const PREPARED_AUDIO_CACHE_CAPACITY_BLOCKS: u8 = 1;
pub(crate) const MAXIMUM_CACHED_DECODED_BYTES: u64 = DEFAULT_MAXIMUM_DECODED_BYTES;

/// Native-only snapshot captured by the authority actor before decoding.
///
/// It deliberately does not implement `Serialize` or `Debug`: the retained WAV
/// receipt contains a local path and content digest. The blocking decoder may
/// own this value, but only the authority actor may later accept its result.
pub(crate) struct PreparedAudioSource {
    fence: AudioFence,
    run_generation: u64,
    wav_receipt: VerifiedPreparedWav,
    expected_sample_rate_hz: u32,
}

/// Actor decision for a local preload request. Cache hits return only the
/// existing path-free summary; misses hand one fenced source to the blocking
/// decoder. No caller can request a filesystem path or bypass the actor.
pub(crate) enum PreparedAudioLookup {
    Cached(PreparedAudioSummary),
    Decode(PreparedAudioSource),
}

impl PreparedAudioSource {
    pub(crate) fn new(
        fence: AudioFence,
        run_generation: u64,
        wav_receipt: VerifiedPreparedWav,
        expected_sample_rate_hz: u32,
    ) -> Self {
        Self {
            fence,
            run_generation,
            wav_receipt,
            expected_sample_rate_hz,
        }
    }
}

/// Decoded candidate returned from the blocking worker to the authority actor.
///
/// The exact selection-time receipt is carried back so the actor can compare
/// it with its current package rather than trusting worker-supplied summary
/// fields. This type is native-only and intentionally non-serializable.
pub(crate) struct PreparedAudioCandidate {
    run_generation: u64,
    wav_receipt: VerifiedPreparedWav,
    media: PreparedPcmBlock,
}

impl PreparedAudioCandidate {
    pub(crate) const fn run_generation(&self) -> u64 {
        self.run_generation
    }

    pub(crate) fn wav_receipt(&self) -> &VerifiedPreparedWav {
        &self.wav_receipt
    }

    pub(crate) fn media(&self) -> &PreparedPcmBlock {
        &self.media
    }

    pub(crate) fn decoded_bytes(&self) -> Result<u64, PreparedAudioError> {
        u64::try_from(self.media.interleaved_f32().len())
            .ok()
            .and_then(|samples| samples.checked_mul(size_of::<f32>() as u64))
            .ok_or_else(PreparedAudioError::resource_limit)
    }

    pub(crate) fn summary(&self) -> Result<PreparedAudioSummary, PreparedAudioError> {
        Ok(PreparedAudioSummary {
            schema: "pps-runner-prepared-audio-summary.v1",
            preparation_scope: "pcm-cache-only",
            output_qualification: "unqualified",
            executable: false,
            block_ordinal: self.media.fence().block_ordinal(),
            sample_rate_hz: self.media.sample_rate_hz(),
            source_channels: self.media.channels(),
            source_channel_layout: match self.media.layout() {
                PpsChannelLayout::LegacyStudy5TactileAudio => "legacy-study5-tactile-audio",
                PpsChannelLayout::BinauralLeftRightTactile => "binaural-left-right-tactile",
            },
            frames: self.media.frames(),
            decoded_bytes: self.decoded_bytes()?,
            cache_capacity_blocks: PREPARED_AUDIO_CACHE_CAPACITY_BLOCKS,
            cache_byte_budget: MAXIMUM_CACHED_DECODED_BYTES,
        })
    }
}

/// Explicit path-free projection for the local bundled WebView.
///
/// This reports only media shape and qualification state. It contains no PCM,
/// path, digest, package identity, participant identity, or run generation.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct PreparedAudioSummary {
    pub schema: &'static str,
    pub preparation_scope: &'static str,
    pub output_qualification: &'static str,
    pub executable: bool,
    pub block_ordinal: u32,
    pub sample_rate_hz: u32,
    pub source_channels: u16,
    pub source_channel_layout: &'static str,
    pub frames: u64,
    pub decoded_bytes: u64,
    pub cache_capacity_blocks: u8,
    pub cache_byte_budget: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct PreparedAudioError {
    code: &'static str,
    public_message: &'static str,
}

impl PreparedAudioError {
    const fn new(code: &'static str, public_message: &'static str) -> Self {
        Self {
            code,
            public_message,
        }
    }

    pub(crate) const fn code(&self) -> &'static str {
        self.code
    }

    pub(crate) const fn public_message(&self) -> &'static str {
        self.public_message
    }

    pub(crate) const fn resource_limit() -> Self {
        Self::new(
            "prepared_audio_resource_limit",
            "The prepared audio exceeds the native preload resource limit.",
        )
    }

    fn from_preparation(error: AudioPreparationError) -> Self {
        match error {
            AudioPreparationError::EncodedByteCountMismatch
            | AudioPreparationError::DigestMismatch => Self::new(
                "prepared_audio_changed",
                "The prepared audio changed after package verification; select the package again.",
            ),
            AudioPreparationError::EncodedBytesTooLarge { .. }
            | AudioPreparationError::FrameLimitExceeded { .. }
            | AudioPreparationError::DecodedBytesTooLarge { .. }
            | AudioPreparationError::DecodedAllocationFailed
            | AudioPreparationError::DecodedShapeOverflow
            | AudioPreparationError::DeclaredDataExceedsFile => Self::resource_limit(),
            AudioPreparationError::UnsupportedSampleFormat
            | AudioPreparationError::UnsupportedBitsPerSample
            | AudioPreparationError::UnsupportedChannelCount
            | AudioPreparationError::SampleRateMismatch => Self::new(
                "prepared_audio_format_unsupported",
                "The prepared audio format does not match the native Runner contract.",
            ),
            AudioPreparationError::Open(_)
            | AudioPreparationError::Inspect(_)
            | AudioPreparationError::Malformed(_)
            | AudioPreparationError::InvalidExpectedDigest
            | AudioPreparationError::InvalidLimits => Self::new(
                "prepared_audio_unavailable",
                "The prepared audio could not be loaded by the native Runner.",
            ),
        }
    }
}

/// Decode one captured block outside the actor. Acceptance remains a separate
/// actor operation and must revalidate every fence and receipt.
pub(crate) fn prepare_verified_audio(
    source: PreparedAudioSource,
) -> Result<PreparedAudioCandidate, PreparedAudioError> {
    prepare_verified_audio_with_limits(source, AudioLoadLimits::default())
}

fn prepare_verified_audio_with_limits(
    source: PreparedAudioSource,
    mut limits: AudioLoadLimits,
) -> Result<PreparedAudioCandidate, PreparedAudioError> {
    limits.maximum_decoded_bytes = limits
        .maximum_decoded_bytes
        .min(MAXIMUM_CACHED_DECODED_BYTES);
    let media = bind_and_decode_verified_wav(VerifiedWavRequest {
        fence: &source.fence,
        path: source.wav_receipt.path(),
        expected_sha256: source.wav_receipt.sha256(),
        expected_encoded_byte_count: source.wav_receipt.encoded_byte_count(),
        expected_sample_rate_hz: source.expected_sample_rate_hz,
        limits,
    })
    .map_err(PreparedAudioError::from_preparation)?;
    Ok(PreparedAudioCandidate {
        run_generation: source.run_generation,
        wav_receipt: source.wav_receipt,
        media,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use pps_session_package::{verify_prepared_session, VerificationRequest};
    use std::{
        fs,
        path::PathBuf,
        sync::atomic::{AtomicU64, Ordering},
    };

    static NEXT_FIXTURE: AtomicU64 = AtomicU64::new(1);

    fn wav_bytes(sample_rate_hz: u32, frames: u32) -> Vec<u8> {
        let channels = 2_u16;
        let data_bytes = frames * u32::from(channels) * 2;
        let mut bytes = Vec::with_capacity(44 + data_bytes as usize);
        bytes.extend_from_slice(b"RIFF");
        bytes.extend_from_slice(&(36 + data_bytes).to_le_bytes());
        bytes.extend_from_slice(b"WAVEfmt ");
        bytes.extend_from_slice(&16_u32.to_le_bytes());
        bytes.extend_from_slice(&1_u16.to_le_bytes());
        bytes.extend_from_slice(&channels.to_le_bytes());
        bytes.extend_from_slice(&sample_rate_hz.to_le_bytes());
        bytes.extend_from_slice(&(sample_rate_hz * u32::from(channels) * 2).to_le_bytes());
        bytes.extend_from_slice(&(channels * 2).to_le_bytes());
        bytes.extend_from_slice(&16_u16.to_le_bytes());
        bytes.extend_from_slice(b"data");
        bytes.extend_from_slice(&data_bytes.to_le_bytes());
        bytes.resize(44 + data_bytes as usize, 0);
        bytes
    }

    fn source() -> (PathBuf, PreparedAudioSource) {
        let root = std::env::temp_dir().join(format!(
            "pps-prepared-audio-tauri-{}-{}",
            std::process::id(),
            NEXT_FIXTURE.fetch_add(1, Ordering::Relaxed)
        ));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        fs::write(root.join("block.wav"), wav_bytes(48_000, 2)).unwrap();
        fs::write(root.join("block.csv"), b"Sample_Rate_Hz\n48000\n").unwrap();
        let manifest_path = root.join("run-session.json");
        fs::write(
            &manifest_path,
            serde_json::to_vec(&serde_json::json!({
                "schema": "pps-run-session.v1",
                "participant_id": "P001",
                "session_id": "session_audio_test",
                "session_group_id": "group_audio_test",
                "part_number": 1,
                "part_session_id": "part_audio_test",
                "session_dir": root,
                "execution_mode": "design_schedule_blocks",
                "blocks": [{
                    "index": 1,
                    "label": "Block",
                    "manifest_path": "block.csv",
                    "wav_path": "block.wav",
                    "trial_count": 1,
                    "duration_s": 1.0,
                    "metadata": {"sample_rate_hz": 48000}
                }]
            }))
            .unwrap(),
        )
        .unwrap();
        let receipt = verify_prepared_session(VerificationRequest::new(&manifest_path)).unwrap();
        let wav = receipt.blocks()[0].block_wav().clone();
        let fence = AudioFence::new(4, receipt.manifest_sha256(), 0);
        (root, PreparedAudioSource::new(fence, 8, wav, 48_000))
    }

    #[test]
    fn resource_limit_fails_before_a_candidate_can_enter_the_cache() {
        let (root, source) = source();
        let error = prepare_verified_audio_with_limits(
            source,
            AudioLoadLimits {
                maximum_encoded_bytes: 1024,
                maximum_frames: 1024,
                maximum_decoded_bytes: 4,
            },
        )
        .err()
        .unwrap();
        assert_eq!(error.code(), "prepared_audio_resource_limit");
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn local_summary_is_path_digest_pcm_and_identity_free() {
        let (root, source) = source();
        let path_text = source.wav_receipt.path().display().to_string();
        let digest = source.wav_receipt.sha256().to_owned();
        let summary = prepare_verified_audio(source).unwrap().summary().unwrap();
        let json = serde_json::to_string(&summary).unwrap();
        assert_eq!(summary.preparation_scope, "pcm-cache-only");
        assert!(!summary.executable);
        for forbidden in [
            path_text.as_str(),
            digest.as_str(),
            "participant",
            "runGeneration",
            "interleaved",
        ] {
            assert!(
                !json.contains(forbidden),
                "summary leaked {forbidden}: {json}"
            );
        }
        fs::remove_dir_all(root).unwrap();
    }
}
