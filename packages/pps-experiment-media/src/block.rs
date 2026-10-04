//! Staged standard-route block WAV assembly from already approved trial rows.

use std::{
    collections::BTreeMap,
    env, fmt, fs,
    fs::OpenOptions,
    io::Read,
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
};

use hound::{SampleFormat, WavSpec, WavWriter};
use pps_runner_audio::{AudioFence, AudioLoadLimits};
use pps_session_package::experiment_plan::ProfileParticipantPlan;
use sha2::{Digest, Sha256};

use crate::bind_profile_trial_wav;

const OUTPUT_CHANNELS: u16 = 3;
const MAX_OUTPUT_WAV_BYTES: u64 = 768 * 1024 * 1024;
const DEFAULT_TACTILE_COMPENSATION_MS: f64 = 23.0;
static PENDING_SEQUENCE: AtomicU64 = AtomicU64::new(1);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BlockMediaErrorCode {
    BlockMissing,
    SourceUnsupported,
    TransformUnsupported,
    MixedSampleRates,
    ResourceLimit,
    MediaChanged,
    OutputExists,
    OutputFailed,
}

impl BlockMediaErrorCode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::BlockMissing => "profile_block_missing",
            Self::SourceUnsupported => "profile_block_source_unsupported",
            Self::TransformUnsupported => "profile_block_transform_unsupported",
            Self::MixedSampleRates => "profile_block_sample_rates_mixed",
            Self::ResourceLimit => "profile_block_resource_limit",
            Self::MediaChanged => "profile_block_media_changed",
            Self::OutputExists => "profile_block_output_exists",
            Self::OutputFailed => "profile_block_output_failed",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BlockMediaError(BlockMediaErrorCode);

impl BlockMediaError {
    pub const fn code(self) -> &'static str {
        self.0.as_str()
    }
}

impl fmt::Display for BlockMediaError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.code())
    }
}

impl std::error::Error for BlockMediaError {}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TrialFrameSpan {
    pub start: u64,
    pub end: u64,
    pub source_frames: u64,
    pub iti_frames: u64,
}

/// Content-bound on-disk PCM16 block. Path/hash never serialize to WebView.
///
/// ```compile_fail
/// fn require_serialize<T: serde::Serialize>() {}
/// require_serialize::<pps_experiment_media::block::AssembledBlockWav>();
/// ```
#[derive(Debug)]
pub struct AssembledBlockWav {
    path: PathBuf,
    sha256: String,
    bytes: u64,
    frames: u64,
    sample_rate_hz: u32,
    spans: Vec<TrialFrameSpan>,
}

impl AssembledBlockWav {
    pub fn path(&self) -> &Path {
        &self.path
    }
    pub fn sha256(&self) -> &str {
        &self.sha256
    }
    pub const fn bytes(&self) -> u64 {
        self.bytes
    }
    pub const fn frames(&self) -> u64 {
        self.frames
    }
    pub const fn sample_rate_hz(&self) -> u32 {
        self.sample_rate_hz
    }
    pub const fn channels(&self) -> u16 {
        OUTPUT_CHANNELS
    }
    pub fn spans(&self) -> &[TrialFrameSpan] {
        &self.spans
    }
}

struct PendingWav(PathBuf);

impl Drop for PendingWav {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.0);
    }
}

fn row_value<'a>(fields: &'a BTreeMap<String, String>, names: &[&str]) -> Option<&'a str> {
    names.iter().find_map(|name| {
        fields
            .get(*name)
            .map(String::as_str)
            .filter(|value| !value.is_empty())
    })
}

fn number(value: Option<&str>, default: f64) -> f64 {
    value
        .and_then(|text| text.trim().parse::<f64>().ok())
        .filter(|value| value.is_finite())
        .unwrap_or(default)
}

fn family(fields: &BTreeMap<String, String>) -> &'static str {
    let declared = row_value(fields, &["family", "Family"])
        .unwrap_or("")
        .trim()
        .to_ascii_lowercase()
        .replace(['-', ' '], "_");
    match declared.as_str() {
        "audio_tactile" => "audio_tactile",
        "baseline" => "baseline",
        "catch" => "catch",
        "auditory_only" => "auditory_only",
        _ => {
            let trial_type = fields
                .get("Trial_Type")
                .map(String::as_str)
                .unwrap_or("")
                .to_ascii_lowercase();
            if trial_type.contains("baseline") {
                "baseline"
            } else if trial_type.contains("catch") {
                "catch"
            } else if trial_type.contains("auditory") {
                "auditory_only"
            } else {
                "audio_tactile"
            }
        }
    }
}

fn has_unsupported_transform(fields: &BTreeMap<String, String>, trial_family: &str) -> bool {
    let switching = row_value(
        fields,
        &[
            "speaker_switch_channels",
            "Speaker_Switch_Channels",
            "speaker_output_channels",
            "Speaker_Output_Channels",
            "speaker_switch_times_ms",
            "Speaker_Switch_Times_ms",
            "speaker_switch_boundaries_ms",
            "Speaker_Switch_Boundaries_ms",
        ],
    )
    .is_some();
    let tactile = matches!(trial_family, "audio_tactile" | "baseline")
        && (row_value(
            fields,
            &["tactile_waveform_shape", "Tactile_Waveform_Shape"],
        )
        .is_some()
            || number(
                row_value(
                    fields,
                    &[
                        "tactile_frequency_hz",
                        "Tactile_Frequency_Hz",
                        "tactile_waveform_frequency_hz",
                        "Tactile_Waveform_Frequency_Hz",
                    ],
                ),
                0.0,
            ) > 0.0);
    switching || tactile
}

fn iti_frames(
    fields: &BTreeMap<String, String>,
    sample_rate_hz: u32,
) -> Result<u64, BlockMediaError> {
    let ms = number(
        row_value(fields, &["iti_ms", "ITI_ms", "Intertrial_Interval_ms"]),
        0.0,
    )
    .max(0.0);
    let frames = (ms / 1000.0 * f64::from(sample_rate_hz)).round_ties_even();
    if !frames.is_finite() || frames < 0.0 || frames > u64::MAX as f64 {
        return Err(BlockMediaError(BlockMediaErrorCode::ResourceLimit));
    }
    Ok(frames as u64)
}

fn looming_from_filename(fields: &BTreeMap<String, String>) -> f64 {
    let filename = row_value(
        fields,
        &[
            "source_file_name",
            "Source_File_Name",
            "trial_file_path",
            "Trial_File_Path",
        ],
    )
    .unwrap_or("");
    let stem = Path::new(filename)
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    let stem = stem
        .strip_prefix("baseline_")
        .and_then(|remainder| {
            let (direction, tail) = remainder.split_once('_')?;
            direction
                .chars()
                .all(|character| character.is_ascii_lowercase())
                .then_some(tail)
        })
        .unwrap_or(&stem);
    let stem = stem.strip_prefix("catch_").unwrap_or(stem);
    let mut total_ms = 0_u64;
    for token in stem.split('_') {
        if ["soa", "tac", "total", "ch3"]
            .iter()
            .any(|prefix| token.starts_with(prefix))
            || ["loom", "frontal", "pink", "blue", "white", "brown"]
                .iter()
                .any(|word| token.contains(word))
        {
            break;
        }
        if let Some(before_ms) = token.strip_suffix("ms") {
            let trailing_digits = before_ms.trim_end_matches(|c: char| c.is_ascii_digit());
            let digits = &before_ms[trailing_digits.len()..];
            if digits.len() >= 2 {
                if let Ok(value) = digits[digits.len().saturating_sub(6)..].parse::<u64>() {
                    total_ms = total_ms.saturating_add(value);
                }
            }
        }
    }
    total_ms as f64 / 1000.0
}

fn tactile_onset_s(fields: &BTreeMap<String, String>, trial_family: &str) -> f64 {
    if let Some(explicit) = row_value(fields, &["tactile_onset_s", "Tactile_Onset_S"]) {
        return number(Some(explicit), 0.0).max(0.0);
    }
    if matches!(trial_family, "catch" | "auditory_only") {
        return 0.0;
    }
    let looming = row_value(fields, &["looming_segment_onset_s", "Looming_Onset_S"])
        .map(|value| number(Some(value), 0.0).max(0.0))
        .unwrap_or_else(|| looming_from_filename(fields));
    let soa_ms = number(row_value(fields, &["soa_ms", "SOA_ms"]), 0.0);
    ((looming + soa_ms / 1000.0).max(0.0) * 1_000_000.0).round_ties_even() / 1_000_000.0
}

fn compensation_ms() -> f64 {
    env::var("PPS_WOOJER_TACTILE_COMPENSATION_MS")
        .ok()
        .and_then(|value| value.trim().parse::<f64>().ok())
        .filter(|value| value.is_finite())
        .unwrap_or(DEFAULT_TACTILE_COMPENSATION_MS)
        .max(0.0)
}

fn tactile_shift(
    samples: &[f32],
    channels: usize,
    frames: usize,
    sample_rate_hz: u32,
    onset_s: f64,
    trial_family: &str,
) -> usize {
    if !matches!(trial_family, "audio_tactile" | "baseline") || channels < 3 {
        return 0;
    }
    let compensation = compensation_ms();
    if compensation <= 0.0 {
        return 0;
    }
    let nominal = (onset_s * f64::from(sample_rate_hz))
        .round_ties_even()
        .max(0.0) as usize;
    if nominal >= frames {
        return 0;
    }
    let drive_s = (onset_s - compensation / 1000.0).max(0.0);
    let drive = (drive_s * f64::from(sample_rate_hz))
        .round_ties_even()
        .max(0.0) as usize;
    if drive >= nominal {
        return 0;
    }
    let last_active = (0..frames)
        .rev()
        .find(|frame| samples[frame * channels + 2].abs() > 1.0e-7);
    if last_active.is_none_or(|last| last < nominal) {
        return 0;
    }
    nominal - drive
}

fn output_sample(value: f32) -> i16 {
    (value.clamp(-1.0, 1.0) * 32768.0)
        .round()
        .clamp(-32768.0, 32767.0) as i16
}

fn output_hash(path: &Path) -> Result<(String, u64), BlockMediaError> {
    let mut file =
        fs::File::open(path).map_err(|_| BlockMediaError(BlockMediaErrorCode::OutputFailed))?;
    let mut digest = Sha256::new();
    let mut bytes = 0_u64;
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let read = file
            .read(&mut buffer)
            .map_err(|_| BlockMediaError(BlockMediaErrorCode::OutputFailed))?;
        if read == 0 {
            break;
        }
        bytes = bytes
            .checked_add(read as u64)
            .filter(|size| *size <= MAX_OUTPUT_WAV_BYTES)
            .ok_or(BlockMediaError(BlockMediaErrorCode::ResourceLimit))?;
        digest.update(&buffer[..read]);
    }
    Ok((format!("{:x}", digest.finalize()), bytes))
}

/// Assemble one standard 2/3-channel PCM16 block in approved trial order.
/// Advanced tactile synthesis and speaker switching reject explicitly until
/// their Python oracle behavior is reproduced. Publication never overwrites.
pub fn assemble_standard_profile_block(
    plan: &ProfileParticipantPlan,
    block_ordinal: usize,
    output_path: &Path,
    package_generation: u64,
) -> Result<AssembledBlockWav, BlockMediaError> {
    let block = plan
        .blocks()
        .get(
            block_ordinal
                .checked_sub(1)
                .ok_or(BlockMediaError(BlockMediaErrorCode::BlockMissing))?,
        )
        .ok_or(BlockMediaError(BlockMediaErrorCode::BlockMissing))?;
    if output_path.exists() {
        return Err(BlockMediaError(BlockMediaErrorCode::OutputExists));
    }
    let sample_rate_hz = block
        .trials()
        .first()
        .and_then(|trial| trial.ingredient().audio())
        .map(|hint| hint.sample_rate_hz())
        .filter(|rate| *rate > 0)
        .ok_or(BlockMediaError(BlockMediaErrorCode::SourceUnsupported))?;
    let mut estimated_frames = 0_u64;
    for trial in block.trials() {
        let hint = trial
            .ingredient()
            .audio()
            .ok_or(BlockMediaError(BlockMediaErrorCode::SourceUnsupported))?;
        if hint.sample_rate_hz() != sample_rate_hz {
            return Err(BlockMediaError(BlockMediaErrorCode::MixedSampleRates));
        }
        if hint.format() != "WAV" || !matches!(hint.channels(), 2 | 3) {
            return Err(BlockMediaError(BlockMediaErrorCode::SourceUnsupported));
        }
        if has_unsupported_transform(trial.fields(), family(trial.fields())) {
            return Err(BlockMediaError(BlockMediaErrorCode::TransformUnsupported));
        }
        estimated_frames = estimated_frames
            .checked_add(hint.frames())
            .and_then(|frames| frames.checked_add(iti_frames(trial.fields(), sample_rate_hz).ok()?))
            .ok_or(BlockMediaError(BlockMediaErrorCode::ResourceLimit))?;
        if 44_u64
            .checked_add(
                estimated_frames
                    .checked_mul(6)
                    .ok_or(BlockMediaError(BlockMediaErrorCode::ResourceLimit))?,
            )
            .is_none_or(|bytes| bytes > MAX_OUTPUT_WAV_BYTES)
        {
            return Err(BlockMediaError(BlockMediaErrorCode::ResourceLimit));
        }
    }
    let parent = output_path
        .parent()
        .filter(|path| !path.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    if !parent.is_dir() {
        return Err(BlockMediaError(BlockMediaErrorCode::OutputFailed));
    }
    let name = output_path
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or(BlockMediaError(BlockMediaErrorCode::OutputFailed))?;
    let mut pending = None;
    for _ in 0..16 {
        let candidate = parent.join(format!(
            ".{name}.pending.{}.{}",
            std::process::id(),
            PENDING_SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ));
        match OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&candidate)
        {
            Ok(file) => {
                pending = Some((PendingWav(candidate), file));
                break;
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(_) => return Err(BlockMediaError(BlockMediaErrorCode::OutputFailed)),
        }
    }
    let (pending, file) = pending.ok_or(BlockMediaError(BlockMediaErrorCode::OutputFailed))?;
    let spec = WavSpec {
        channels: OUTPUT_CHANNELS,
        sample_rate: sample_rate_hz,
        bits_per_sample: 16,
        sample_format: SampleFormat::Int,
    };
    let mut writer = WavWriter::new(file, spec)
        .map_err(|_| BlockMediaError(BlockMediaErrorCode::OutputFailed))?;
    let fence = AudioFence::new(
        package_generation,
        plan.profile_sha256().to_owned(),
        block_ordinal as u32,
    );
    let mut spans = Vec::with_capacity(block.trials().len());
    let mut cursor = 0_u64;
    for trial in block.trials() {
        let media = bind_profile_trial_wav(trial, &fence, AudioLoadLimits::default())
            .map_err(|_| BlockMediaError(BlockMediaErrorCode::MediaChanged))?;
        if media.sample_rate_hz() != sample_rate_hz {
            return Err(BlockMediaError(BlockMediaErrorCode::MixedSampleRates));
        }
        let channels = usize::from(media.channels());
        let frames = usize::try_from(media.frames())
            .map_err(|_| BlockMediaError(BlockMediaErrorCode::ResourceLimit))?;
        let samples = media.interleaved_f32();
        let trial_family = family(trial.fields());
        let shift = tactile_shift(
            samples,
            channels,
            frames,
            sample_rate_hz,
            tactile_onset_s(trial.fields(), trial_family),
            trial_family,
        );
        for frame in 0..frames {
            for channel in 0..usize::from(OUTPUT_CHANNELS) {
                let value = if channel >= channels {
                    0.0
                } else if channel == 2 && shift > 0 {
                    frame
                        .checked_add(shift)
                        .filter(|source| *source < frames)
                        .map_or(0.0, |source| samples[source * channels + channel])
                } else {
                    samples[frame * channels + channel]
                };
                writer
                    .write_sample(output_sample(value))
                    .map_err(|_| BlockMediaError(BlockMediaErrorCode::OutputFailed))?;
            }
        }
        let iti = iti_frames(trial.fields(), sample_rate_hz)?;
        for _ in 0..iti {
            for _ in 0..OUTPUT_CHANNELS {
                writer
                    .write_sample(0_i16)
                    .map_err(|_| BlockMediaError(BlockMediaErrorCode::OutputFailed))?;
            }
        }
        let end = cursor
            .checked_add(media.frames())
            .and_then(|value| value.checked_add(iti))
            .ok_or(BlockMediaError(BlockMediaErrorCode::ResourceLimit))?;
        spans.push(TrialFrameSpan {
            start: cursor,
            end,
            source_frames: media.frames(),
            iti_frames: iti,
        });
        cursor = end;
    }
    writer
        .finalize()
        .map_err(|_| BlockMediaError(BlockMediaErrorCode::OutputFailed))?;
    let synced = OpenOptions::new()
        .read(true)
        .write(true)
        .open(&pending.0)
        .map_err(|_| BlockMediaError(BlockMediaErrorCode::OutputFailed))?;
    synced
        .sync_all()
        .map_err(|_| BlockMediaError(BlockMediaErrorCode::OutputFailed))?;
    let (sha256, bytes) = output_hash(&pending.0)?;
    if cursor != estimated_frames {
        return Err(BlockMediaError(BlockMediaErrorCode::ResourceLimit));
    }
    fs::hard_link(&pending.0, output_path).map_err(|error| {
        if error.kind() == std::io::ErrorKind::AlreadyExists {
            BlockMediaError(BlockMediaErrorCode::OutputExists)
        } else {
            BlockMediaError(BlockMediaErrorCode::OutputFailed)
        }
    })?;
    Ok(AssembledBlockWav {
        path: output_path.to_path_buf(),
        sha256,
        bytes,
        frames: cursor,
        sample_rate_hz,
        spans,
    })
}
