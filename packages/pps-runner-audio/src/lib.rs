//! Pure native preparation of content-bound PPS block audio.
//!
//! This crate deliberately owns no Tauri, network, device, or experiment-state
//! dependency. It verifies and decodes one exact WAV snapshot for a later
//! platform output adapter; successful preparation does not make a package
//! executable or scientifically qualified.

#![forbid(unsafe_code)]

pub mod output;

pub use output::{
    resolve_output_route, ControlResult, MockOutput, OutputFence, OutputGains, OutputPlanError,
    OutputRouteError, OutputRouteRequest, PreparedPlaybackPlan, RenderControl, RenderEngine,
    RenderIntegrityFault, RenderOutcome, RenderState, ResolvedOutputRoute, ResolvedOutputRouteKind,
    RtEvent, RtEventFence, RtEventKind, RtEventSink, RtScheduledEvent,
    MAXIMUM_METADATA_EVENTS_PER_CALLBACK, MAXIMUM_OUTPUT_CALLBACK_FRAMES,
    MAXIMUM_RT_EVENTS_PER_CALLBACK,
};

use std::{
    fmt,
    fs::File,
    io::{self, Read},
    path::Path,
    sync::Arc,
};

use hound::{SampleFormat, WavReader};
use sha2::{Digest, Sha256};
use thiserror::Error;

const BOUNDED_READER_LIMIT_MESSAGE: &str = "pps encoded WAV byte limit exceeded";
const F32_SAMPLE_BYTES: u64 = size_of::<f32>() as u64;

/// Default per-WAV encoded limit. The current largest migration fixture is
/// approximately 453 MiB; 768 MiB leaves bounded headroom.
pub const DEFAULT_MAXIMUM_ENCODED_BYTES: u64 = 768 * 1024 * 1024;
/// Default decoded allocation limit. A 453 MiB PCM16 file expands to roughly
/// 906 MiB as `f32`, so this allows that workload without unbounded growth.
pub const DEFAULT_MAXIMUM_DECODED_BYTES: u64 = 1280 * 1024 * 1024;
/// Default frame limit, slightly above 37 minutes at 44.1 kHz.
pub const DEFAULT_MAXIMUM_FRAMES: u64 = 100_000_000;

/// Generation fence retained with prepared media so late work can be rejected
/// by the native authority owner after package replacement.
#[derive(Clone, PartialEq, Eq)]
pub struct AudioFence {
    package_generation: u64,
    package_fingerprint: Arc<str>,
    block_ordinal: u32,
}

impl fmt::Debug for AudioFence {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("AudioFence")
            .field("package_generation", &self.package_generation)
            .field("block_ordinal", &self.block_ordinal)
            .finish_non_exhaustive()
    }
}

impl AudioFence {
    pub fn new(
        package_generation: u64,
        package_fingerprint: impl Into<Arc<str>>,
        block_ordinal: u32,
    ) -> Self {
        Self {
            package_generation,
            package_fingerprint: package_fingerprint.into(),
            block_ordinal,
        }
    }

    pub const fn package_generation(&self) -> u64 {
        self.package_generation
    }

    pub fn package_fingerprint(&self) -> &str {
        &self.package_fingerprint
    }

    pub const fn block_ordinal(&self) -> u32 {
        self.block_ordinal
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct AudioLoadLimits {
    pub maximum_encoded_bytes: u64,
    pub maximum_frames: u64,
    pub maximum_decoded_bytes: u64,
}

impl Default for AudioLoadLimits {
    fn default() -> Self {
        Self {
            maximum_encoded_bytes: DEFAULT_MAXIMUM_ENCODED_BYTES,
            maximum_frames: DEFAULT_MAXIMUM_FRAMES,
            maximum_decoded_bytes: DEFAULT_MAXIMUM_DECODED_BYTES,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PpsChannelLayout {
    /// V1 Study 5 source order: `[tactile, audio]`. Physical routing remains
    /// a later platform-adapter decision.
    LegacyStudy5TactileAudio,
    /// Canonical source order: `[left, right, tactile]`.
    BinauralLeftRightTactile,
}

#[derive(Clone, PartialEq, Eq)]
pub struct PreparedMediaIdentity {
    sha256: Arc<str>,
    encoded_byte_count: u64,
}

impl fmt::Debug for PreparedMediaIdentity {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("PreparedMediaIdentity")
            .field("encoded_byte_count", &self.encoded_byte_count)
            .finish_non_exhaustive()
    }
}

impl PreparedMediaIdentity {
    pub fn sha256(&self) -> &str {
        &self.sha256
    }

    pub const fn encoded_byte_count(&self) -> u64 {
        self.encoded_byte_count
    }
}

/// Immutable decoded media. It is intentionally native-only and path-free.
///
/// This type deliberately does not implement `Serialize`, preventing decoded
/// audio, fences, and private media identity from becoming an IPC payload.
///
/// ```compile_fail
/// fn require_serialize<T: serde::Serialize>() {}
/// require_serialize::<pps_runner_audio::PreparedPcmBlock>();
/// ```
#[derive(Clone, PartialEq)]
pub struct PreparedPcmBlock {
    fence: AudioFence,
    identity: PreparedMediaIdentity,
    layout: PpsChannelLayout,
    sample_rate_hz: u32,
    channels: u16,
    frames: u64,
    interleaved_f32: Arc<Vec<f32>>,
}

impl fmt::Debug for PreparedPcmBlock {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("PreparedPcmBlock")
            .field("fence", &self.fence)
            .field("identity", &self.identity)
            .field("layout", &self.layout)
            .field("sample_rate_hz", &self.sample_rate_hz)
            .field("channels", &self.channels)
            .field("frames", &self.frames)
            .field("decoded_sample_count", &self.interleaved_f32.len())
            .finish()
    }
}

impl PreparedPcmBlock {
    pub fn fence(&self) -> &AudioFence {
        &self.fence
    }

    pub fn identity(&self) -> &PreparedMediaIdentity {
        &self.identity
    }

    pub const fn layout(&self) -> PpsChannelLayout {
        self.layout
    }

    pub const fn sample_rate_hz(&self) -> u32 {
        self.sample_rate_hz
    }

    pub const fn channels(&self) -> u16 {
        self.channels
    }

    pub const fn frames(&self) -> u64 {
        self.frames
    }

    pub fn interleaved_f32(&self) -> &[f32] {
        self.interleaved_f32.as_slice()
    }
}

#[derive(Debug, Clone, Copy)]
pub struct VerifiedWavRequest<'a> {
    pub fence: &'a AudioFence,
    pub path: &'a Path,
    pub expected_sha256: &'a str,
    pub expected_encoded_byte_count: u64,
    pub expected_sample_rate_hz: u32,
    pub limits: AudioLoadLimits,
}

#[derive(Debug, Error)]
pub enum AudioPreparationError {
    #[error("prepared WAV cannot be opened")]
    Open(#[source] io::Error),
    #[error("prepared WAV metadata cannot be inspected")]
    Inspect(#[source] io::Error),
    #[error("expected WAV digest is not a canonical SHA-256 value")]
    InvalidExpectedDigest,
    #[error("audio preparation limits must all be nonzero")]
    InvalidLimits,
    #[error("prepared WAV exceeds the encoded byte limit of {limit} bytes")]
    EncodedBytesTooLarge { limit: u64 },
    #[error("prepared WAV encoded byte count no longer matches verification")]
    EncodedByteCountMismatch,
    #[error("prepared WAV is malformed or truncated")]
    Malformed(#[source] hound::Error),
    #[error("prepared WAV must use integer PCM samples")]
    UnsupportedSampleFormat,
    #[error("prepared WAV must use exactly 16 bits per sample")]
    UnsupportedBitsPerSample,
    #[error("prepared WAV must contain exactly 2 or 3 channels")]
    UnsupportedChannelCount,
    #[error("prepared WAV sample rate does not match the prepared schedule")]
    SampleRateMismatch,
    #[error("prepared WAV decoded shape overflows native limits")]
    DecodedShapeOverflow,
    #[error("prepared WAV declares more PCM data than the opened file contains")]
    DeclaredDataExceedsFile,
    #[error("prepared WAV exceeds the frame limit of {limit}")]
    FrameLimitExceeded { limit: u64 },
    #[error("prepared WAV exceeds the decoded byte limit of {limit}")]
    DecodedBytesTooLarge { limit: u64 },
    #[error("prepared WAV decoded buffer cannot be allocated within native limits")]
    DecodedAllocationFailed,
    #[error("prepared WAV bytes changed after package verification")]
    DigestMismatch,
}

/// Hash and decode exactly one already-verified WAV through one opened handle.
///
/// The same bounded stream feeds Hound and SHA-256. After Hound consumes the
/// declared data samples, the reader is drained to EOF so trailing chunks and
/// bytes also contribute to the digest. No encoded-file-sized buffer is held.
pub fn bind_and_decode_verified_wav(
    request: VerifiedWavRequest<'_>,
) -> Result<PreparedPcmBlock, AudioPreparationError> {
    validate_request(&request)?;

    let file = File::open(request.path).map_err(AudioPreparationError::Open)?;
    let opened_length = file
        .metadata()
        .map_err(AudioPreparationError::Inspect)?
        .len();
    if opened_length > request.limits.maximum_encoded_bytes {
        return Err(AudioPreparationError::EncodedBytesTooLarge {
            limit: request.limits.maximum_encoded_bytes,
        });
    }
    if opened_length != request.expected_encoded_byte_count {
        return Err(AudioPreparationError::EncodedByteCountMismatch);
    }

    let bounded = BoundedHashReader::new(file, request.limits.maximum_encoded_bytes);
    let mut wav = WavReader::new(bounded)
        .map_err(|error| map_hound_error(error, request.limits.maximum_encoded_bytes))?;
    let spec = wav.spec();
    if spec.sample_format != SampleFormat::Int {
        return Err(AudioPreparationError::UnsupportedSampleFormat);
    }
    if spec.bits_per_sample != 16 {
        return Err(AudioPreparationError::UnsupportedBitsPerSample);
    }
    let layout = match spec.channels {
        2 => PpsChannelLayout::LegacyStudy5TactileAudio,
        3 => PpsChannelLayout::BinauralLeftRightTactile,
        _ => return Err(AudioPreparationError::UnsupportedChannelCount),
    };
    if spec.sample_rate != request.expected_sample_rate_hz {
        return Err(AudioPreparationError::SampleRateMismatch);
    }

    let sample_count = u64::from(wav.len());
    let declared_pcm_bytes = sample_count
        .checked_mul(u64::from(spec.bits_per_sample / 8))
        .ok_or(AudioPreparationError::DecodedShapeOverflow)?;
    if declared_pcm_bytes > opened_length {
        return Err(AudioPreparationError::DeclaredDataExceedsFile);
    }
    let (frames, _) = decoded_shape(sample_count, spec.channels, request.limits)?;
    let sample_capacity =
        usize::try_from(sample_count).map_err(|_| AudioPreparationError::DecodedShapeOverflow)?;

    // The file-controlled count has passed the frame, multiplication, and
    // decoded-byte ceilings above. Reserve exactly once so Vec's geometric
    // growth cannot transiently exceed the documented decoded-memory budget.
    let mut decoded = Vec::new();
    decoded
        .try_reserve_exact(sample_capacity)
        .map_err(|_| AudioPreparationError::DecodedAllocationFailed)?;
    for sample in wav.samples::<i16>() {
        let sample =
            sample.map_err(|error| map_hound_error(error, request.limits.maximum_encoded_bytes))?;
        let next_count = (decoded.len() as u64)
            .checked_add(1)
            .ok_or(AudioPreparationError::DecodedShapeOverflow)?;
        let next_bytes = next_count
            .checked_mul(F32_SAMPLE_BYTES)
            .ok_or(AudioPreparationError::DecodedShapeOverflow)?;
        if next_bytes > request.limits.maximum_decoded_bytes {
            return Err(AudioPreparationError::DecodedBytesTooLarge {
                limit: request.limits.maximum_decoded_bytes,
            });
        }
        decoded.push(f32::from(sample) / 32768.0);
    }
    if decoded.len() as u64 != sample_count {
        return Err(AudioPreparationError::DecodedShapeOverflow);
    }

    let mut bounded = wav.into_inner();
    io::copy(&mut bounded, &mut io::sink())
        .map_err(|error| map_io_error(error, request.limits.maximum_encoded_bytes))?;
    let (digest, actual_encoded_bytes) = bounded.finish();
    if actual_encoded_bytes != request.expected_encoded_byte_count {
        return Err(AudioPreparationError::EncodedByteCountMismatch);
    }
    let observed_sha256 = format!("{digest:x}");
    if !observed_sha256.eq_ignore_ascii_case(request.expected_sha256) {
        return Err(AudioPreparationError::DigestMismatch);
    }

    Ok(PreparedPcmBlock {
        fence: request.fence.clone(),
        identity: PreparedMediaIdentity {
            sha256: Arc::from(observed_sha256),
            encoded_byte_count: actual_encoded_bytes,
        },
        layout,
        sample_rate_hz: spec.sample_rate,
        channels: spec.channels,
        frames,
        interleaved_f32: Arc::new(decoded),
    })
}

fn validate_request(request: &VerifiedWavRequest<'_>) -> Result<(), AudioPreparationError> {
    if request.limits.maximum_encoded_bytes == 0
        || request.limits.maximum_frames == 0
        || request.limits.maximum_decoded_bytes == 0
    {
        return Err(AudioPreparationError::InvalidLimits);
    }
    if request.expected_sha256.len() != 64
        || !request
            .expected_sha256
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit())
    {
        return Err(AudioPreparationError::InvalidExpectedDigest);
    }
    Ok(())
}

fn decoded_shape(
    sample_count: u64,
    channels: u16,
    limits: AudioLoadLimits,
) -> Result<(u64, u64), AudioPreparationError> {
    let channels = u64::from(channels);
    if channels == 0 || !sample_count.is_multiple_of(channels) {
        return Err(AudioPreparationError::DecodedShapeOverflow);
    }
    let frames = sample_count / channels;
    if frames > limits.maximum_frames {
        return Err(AudioPreparationError::FrameLimitExceeded {
            limit: limits.maximum_frames,
        });
    }
    let decoded_bytes = sample_count
        .checked_mul(F32_SAMPLE_BYTES)
        .ok_or(AudioPreparationError::DecodedShapeOverflow)?;
    if decoded_bytes > limits.maximum_decoded_bytes {
        return Err(AudioPreparationError::DecodedBytesTooLarge {
            limit: limits.maximum_decoded_bytes,
        });
    }
    Ok((frames, decoded_bytes))
}

fn map_hound_error(error: hound::Error, maximum_encoded_bytes: u64) -> AudioPreparationError {
    match error {
        hound::Error::IoError(error) if is_limit_error(&error) => {
            AudioPreparationError::EncodedBytesTooLarge {
                limit: maximum_encoded_bytes,
            }
        }
        other => AudioPreparationError::Malformed(other),
    }
}

fn map_io_error(error: io::Error, maximum_encoded_bytes: u64) -> AudioPreparationError {
    if is_limit_error(&error) {
        AudioPreparationError::EncodedBytesTooLarge {
            limit: maximum_encoded_bytes,
        }
    } else {
        AudioPreparationError::Malformed(hound::Error::IoError(error))
    }
}

fn is_limit_error(error: &io::Error) -> bool {
    error.kind() == io::ErrorKind::InvalidData && error.to_string() == BOUNDED_READER_LIMIT_MESSAGE
}

struct BoundedHashReader {
    file: File,
    digest: Sha256,
    bytes_read: u64,
    maximum_bytes: u64,
}

impl BoundedHashReader {
    fn new(file: File, maximum_bytes: u64) -> Self {
        Self {
            file,
            digest: Sha256::new(),
            bytes_read: 0,
            maximum_bytes,
        }
    }

    fn finish(self) -> (sha2::digest::Output<Sha256>, u64) {
        (self.digest.finalize(), self.bytes_read)
    }
}

impl Read for BoundedHashReader {
    fn read(&mut self, buffer: &mut [u8]) -> io::Result<usize> {
        if buffer.is_empty() {
            return Ok(0);
        }
        let remaining = self.maximum_bytes.saturating_sub(self.bytes_read);
        if remaining == 0 {
            let mut probe = [0_u8; 1];
            return match self.file.read(&mut probe)? {
                0 => Ok(0),
                _ => Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    BOUNDED_READER_LIMIT_MESSAGE,
                )),
            };
        }
        let allowed = remaining.min(buffer.len() as u64) as usize;
        let read = self.file.read(&mut buffer[..allowed])?;
        self.bytes_read = self
            .bytes_read
            .checked_add(read as u64)
            .ok_or_else(|| io::Error::other("encoded WAV byte counter overflow"))?;
        self.digest.update(&buffer[..read]);
        Ok(read)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn decoded_shape_rejects_overflow_before_allocation() {
        let error = decoded_shape(
            u64::MAX,
            1,
            AudioLoadLimits {
                maximum_encoded_bytes: 1,
                maximum_frames: u64::MAX,
                maximum_decoded_bytes: u64::MAX,
            },
        )
        .expect_err("f32 byte multiplication must overflow");
        assert!(matches!(error, AudioPreparationError::DecodedShapeOverflow));
    }
}
