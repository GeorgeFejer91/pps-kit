use std::{
    fs::{self, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
};

use hound::{SampleFormat, WavSpec, WavWriter};
use pps_runner_audio::{
    bind_and_decode_verified_wav, AudioFence, AudioLoadLimits, AudioPreparationError,
    PpsChannelLayout, VerifiedWavRequest,
};
use sha2::{Digest, Sha256};

static TEST_DIRECTORY_SEQUENCE: AtomicU64 = AtomicU64::new(1);

struct TestDirectory {
    path: PathBuf,
}

impl TestDirectory {
    fn new() -> Self {
        let sequence = TEST_DIRECTORY_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "pps-runner-audio-test-{}-{sequence}",
            std::process::id()
        ));
        fs::create_dir_all(&path).expect("create test directory");
        Self { path }
    }

    fn join(&self, path: impl AsRef<Path>) -> PathBuf {
        self.path.join(path)
    }
}

impl Drop for TestDirectory {
    fn drop(&mut self) {
        let is_owned = self
            .path
            .file_name()
            .and_then(|name| name.to_str())
            .is_some_and(|name| name.starts_with("pps-runner-audio-test-"));
        if self.path.starts_with(std::env::temp_dir()) && is_owned {
            let _ = fs::remove_dir_all(&self.path);
        }
    }
}

fn write_i16_wav(path: &Path, channels: u16, sample_rate: u32, samples: &[i16]) {
    let spec = WavSpec {
        channels,
        sample_rate,
        bits_per_sample: 16,
        sample_format: SampleFormat::Int,
    };
    let mut writer = WavWriter::create(path, spec).expect("create PCM16 fixture");
    for sample in samples {
        writer.write_sample(*sample).expect("write PCM16 sample");
    }
    writer.finalize().expect("finalize PCM16 fixture");
}

fn write_i32_wav(path: &Path, channels: u16, bits_per_sample: u16, samples: &[i32]) {
    let spec = WavSpec {
        channels,
        sample_rate: 48_000,
        bits_per_sample,
        sample_format: SampleFormat::Int,
    };
    let mut writer = WavWriter::create(path, spec).expect("create integer fixture");
    for sample in samples {
        writer.write_sample(*sample).expect("write integer sample");
    }
    writer.finalize().expect("finalize integer fixture");
}

fn write_float_wav(path: &Path, channels: u16, samples: &[f32]) {
    let spec = WavSpec {
        channels,
        sample_rate: 48_000,
        bits_per_sample: 32,
        sample_format: SampleFormat::Float,
    };
    let mut writer = WavWriter::create(path, spec).expect("create float fixture");
    for sample in samples {
        writer.write_sample(*sample).expect("write float sample");
    }
    writer.finalize().expect("finalize float fixture");
}

fn digest(path: &Path) -> String {
    format!(
        "{:x}",
        Sha256::digest(fs::read(path).expect("read digest fixture"))
    )
}

fn bind(
    path: &Path,
    fence: &AudioFence,
    expected_sha256: &str,
    expected_encoded_byte_count: u64,
    expected_sample_rate_hz: u32,
    limits: AudioLoadLimits,
) -> Result<pps_runner_audio::PreparedPcmBlock, AudioPreparationError> {
    bind_and_decode_verified_wav(VerifiedWavRequest {
        fence,
        path,
        expected_sha256,
        expected_encoded_byte_count,
        expected_sample_rate_hz,
        limits,
    })
}

fn default_fence() -> AudioFence {
    AudioFence::new(7, "package-fingerprint", 2)
}

#[test]
fn decodes_legacy_two_channel_pcm16_with_exact_identity_and_source_order() {
    let root = TestDirectory::new();
    let path = root.join("stereo.wav");
    let samples = [-32_768, 32_767, 0, 16_384];
    write_i16_wav(&path, 2, 48_000, &samples);
    let expected_digest = digest(&path);
    let encoded_bytes = fs::metadata(&path).unwrap().len();
    let fence = default_fence();

    let prepared = bind(
        &path,
        &fence,
        &expected_digest,
        encoded_bytes,
        48_000,
        AudioLoadLimits::default(),
    )
    .expect("bind legacy two-channel WAV");

    assert_eq!(
        prepared.layout(),
        PpsChannelLayout::LegacyStudy5TactileAudio
    );
    assert_eq!(prepared.channels(), 2);
    assert_eq!(prepared.frames(), 2);
    assert_eq!(prepared.sample_rate_hz(), 48_000);
    assert_eq!(prepared.identity().sha256(), expected_digest);
    assert_eq!(prepared.identity().encoded_byte_count(), encoded_bytes);
    assert_eq!(prepared.fence(), &fence);
    assert_eq!(
        prepared.interleaved_f32(),
        &[-1.0, 32_767.0 / 32_768.0, 0.0, 0.5]
    );
}

#[test]
fn decodes_three_channel_pcm16_without_reordering() {
    let root = TestDirectory::new();
    let path = root.join("left-right-tactile.wav");
    let samples = [-16_384, 0, 16_384, 32_767, -32_768, 8_192];
    write_i16_wav(&path, 3, 44_100, &samples);
    let expected_digest = digest(&path);
    let encoded_bytes = fs::metadata(&path).unwrap().len();

    let prepared = bind(
        &path,
        &default_fence(),
        &expected_digest,
        encoded_bytes,
        44_100,
        AudioLoadLimits::default(),
    )
    .expect("bind three-channel WAV");

    assert_eq!(
        prepared.layout(),
        PpsChannelLayout::BinauralLeftRightTactile
    );
    assert_eq!(prepared.frames(), 2);
    assert_eq!(
        prepared.interleaved_f32(),
        &[-0.5, 0.0, 0.5, 32_767.0 / 32_768.0, -1.0, 0.25]
    );
}

#[test]
fn rejects_mono_four_channel_float_and_24_bit_inputs() {
    let root = TestDirectory::new();
    let fence = default_fence();

    let mono = root.join("mono.wav");
    write_i16_wav(&mono, 1, 48_000, &[0, 1]);
    assert!(matches!(
        bind(
            &mono,
            &fence,
            &digest(&mono),
            fs::metadata(&mono).unwrap().len(),
            48_000,
            AudioLoadLimits::default()
        ),
        Err(AudioPreparationError::UnsupportedChannelCount)
    ));

    let four = root.join("four.wav");
    write_i16_wav(&four, 4, 48_000, &[0, 1, 2, 3]);
    assert!(matches!(
        bind(
            &four,
            &fence,
            &digest(&four),
            fs::metadata(&four).unwrap().len(),
            48_000,
            AudioLoadLimits::default()
        ),
        Err(AudioPreparationError::UnsupportedChannelCount)
    ));

    let float = root.join("float.wav");
    write_float_wav(&float, 2, &[0.0, 0.5]);
    assert!(matches!(
        bind(
            &float,
            &fence,
            &digest(&float),
            fs::metadata(&float).unwrap().len(),
            48_000,
            AudioLoadLimits::default()
        ),
        Err(AudioPreparationError::UnsupportedSampleFormat)
    ));

    let pcm24 = root.join("pcm24.wav");
    write_i32_wav(&pcm24, 2, 24, &[0, 1]);
    assert!(matches!(
        bind(
            &pcm24,
            &fence,
            &digest(&pcm24),
            fs::metadata(&pcm24).unwrap().len(),
            48_000,
            AudioLoadLimits::default()
        ),
        Err(AudioPreparationError::UnsupportedBitsPerSample)
    ));
}

#[test]
fn rejects_changed_truncated_malformed_and_oversized_files() {
    let root = TestDirectory::new();
    let fence = default_fence();
    let path = root.join("changed.wav");
    write_i16_wav(&path, 2, 48_000, &[1, 2, 3, 4]);
    let original_digest = digest(&path);
    let original_bytes = fs::metadata(&path).unwrap().len();

    OpenOptions::new()
        .append(true)
        .open(&path)
        .unwrap()
        .write_all(b"changed")
        .unwrap();
    assert!(matches!(
        bind(
            &path,
            &fence,
            &original_digest,
            original_bytes,
            48_000,
            AudioLoadLimits::default()
        ),
        Err(AudioPreparationError::EncodedByteCountMismatch)
    ));

    let truncated = root.join("truncated.wav");
    write_i16_wav(&truncated, 2, 48_000, &[1, 2, 3, 4]);
    let truncated_length = fs::metadata(&truncated).unwrap().len() - 1;
    OpenOptions::new()
        .write(true)
        .open(&truncated)
        .unwrap()
        .set_len(truncated_length)
        .unwrap();
    assert!(matches!(
        bind(
            &truncated,
            &fence,
            &digest(&truncated),
            truncated_length,
            48_000,
            AudioLoadLimits::default()
        ),
        Err(AudioPreparationError::Malformed(_))
    ));

    let malformed = root.join("malformed.wav");
    fs::write(&malformed, b"not a WAV file").unwrap();
    assert!(matches!(
        bind(
            &malformed,
            &fence,
            &digest(&malformed),
            fs::metadata(&malformed).unwrap().len(),
            48_000,
            AudioLoadLimits::default()
        ),
        Err(AudioPreparationError::Malformed(_))
    ));

    let oversized = root.join("oversized.wav");
    write_i16_wav(&oversized, 2, 48_000, &[1, 2]);
    let limits = AudioLoadLimits {
        maximum_encoded_bytes: fs::metadata(&oversized).unwrap().len() - 1,
        ..AudioLoadLimits::default()
    };
    assert!(matches!(
        bind(
            &oversized,
            &fence,
            &digest(&oversized),
            fs::metadata(&oversized).unwrap().len(),
            48_000,
            limits
        ),
        Err(AudioPreparationError::EncodedBytesTooLarge { .. })
    ));
}

#[test]
fn detects_digest_mismatch_only_after_supported_content_decodes() {
    let root = TestDirectory::new();
    let path = root.join("digest-drift.wav");
    write_i16_wav(&path, 2, 48_000, &[1, 2, 3, 4]);
    let original_digest = digest(&path);
    let length = fs::metadata(&path).unwrap().len();
    let mut bytes = fs::read(&path).unwrap();
    let last = bytes.last_mut().expect("fixture byte");
    *last ^= 1;
    fs::write(&path, bytes).unwrap();

    assert!(matches!(
        bind(
            &path,
            &default_fence(),
            &original_digest,
            length,
            48_000,
            AudioLoadLimits::default()
        ),
        Err(AudioPreparationError::DigestMismatch)
    ));
}

#[test]
fn trailing_bytes_are_included_in_media_digest() {
    let root = TestDirectory::new();
    let path = root.join("trailing.wav");
    write_i16_wav(&path, 2, 48_000, &[1, 2, 3, 4]);
    OpenOptions::new()
        .append(true)
        .open(&path)
        .unwrap()
        .write_all(b"JUNK\x04\x00\x00\x00tail")
        .unwrap();
    let expected_digest = digest(&path);
    let length = fs::metadata(&path).unwrap().len();

    let prepared = bind(
        &path,
        &default_fence(),
        &expected_digest,
        length,
        48_000,
        AudioLoadLimits::default(),
    )
    .expect("trailing bytes remain part of exact identity");

    assert_eq!(prepared.identity().sha256(), expected_digest);
    assert_eq!(prepared.identity().encoded_byte_count(), length);
}

#[test]
fn frame_decoded_byte_and_sample_rate_limits_fail_closed() {
    let root = TestDirectory::new();
    let path = root.join("limited.wav");
    write_i16_wav(&path, 2, 48_000, &[1, 2, 3, 4]);
    let expected_digest = digest(&path);
    let length = fs::metadata(&path).unwrap().len();
    let fence = default_fence();

    let limits = AudioLoadLimits {
        maximum_frames: 1,
        ..AudioLoadLimits::default()
    };
    assert!(matches!(
        bind(&path, &fence, &expected_digest, length, 48_000, limits),
        Err(AudioPreparationError::FrameLimitExceeded { .. })
    ));

    let limits = AudioLoadLimits {
        maximum_decoded_bytes: 15,
        ..AudioLoadLimits::default()
    };
    assert!(matches!(
        bind(&path, &fence, &expected_digest, length, 48_000, limits),
        Err(AudioPreparationError::DecodedBytesTooLarge { .. })
    ));

    assert!(matches!(
        bind(
            &path,
            &fence,
            &expected_digest,
            length,
            44_100,
            AudioLoadLimits::default()
        ),
        Err(AudioPreparationError::SampleRateMismatch)
    ));
}

#[test]
fn prepared_media_debug_projection_contains_no_source_path() {
    let root = TestDirectory::new();
    let path = root.join("private-participant-path.wav");
    write_i16_wav(&path, 2, 48_000, &[1, 2]);
    let prepared = bind(
        &path,
        &default_fence(),
        &digest(&path),
        fs::metadata(&path).unwrap().len(),
        48_000,
        AudioLoadLimits::default(),
    )
    .expect("bind path-free prepared media");

    let debug = format!("{prepared:?}");
    assert!(debug.len() < 512);
    assert!(!debug.contains("private-participant-path.wav"));
    assert!(!debug.contains("package-fingerprint"));
    assert!(!debug.contains(prepared.identity().sha256()));
    assert!(!debug.contains("interleaved_f32"));
}

#[test]
fn tiny_file_with_huge_declared_data_cannot_drive_decoded_allocation() {
    let root = TestDirectory::new();
    let path = root.join("forged-data-length.wav");
    write_i16_wav(&path, 2, 48_000, &[]);
    let mut bytes = fs::read(&path).unwrap();
    assert_eq!(&bytes[36..40], b"data");
    bytes[40..44].copy_from_slice(&0xffff_fffc_u32.to_le_bytes());
    fs::write(&path, &bytes).unwrap();

    assert!(matches!(
        bind(
            &path,
            &default_fence(),
            &digest(&path),
            fs::metadata(&path).unwrap().len(),
            48_000,
            AudioLoadLimits::default()
        ),
        Err(AudioPreparationError::DeclaredDataExceedsFile)
    ));
}
