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
use pps_runner_audio::{AudioFence, AudioLoadLimits, MAXIMUM_DIRECT_OUTPUT_CHANNELS};
use pps_session_package::experiment_plan::ProfileParticipantPlan;
use sha2::{Digest, Sha256};

use crate::bind_profile_trial_wav;

const MINIMUM_OUTPUT_CHANNELS: u16 = 3;
const MAXIMUM_OUTPUT_CHANNELS: u16 = MAXIMUM_DIRECT_OUTPUT_CHANNELS;
const MAX_OUTPUT_WAV_BYTES: u64 = 768 * 1024 * 1024;
const STORAGE_RESERVE_BYTES: u64 = 8 * 1024 * 1024;
const DEFAULT_TACTILE_COMPENSATION_MS: f64 = 23.0;
static PENDING_SEQUENCE: AtomicU64 = AtomicU64::new(1);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BlockMediaErrorCode {
    BlockMissing,
    SourceUnsupported,
    TransformUnsupported,
    MixedSampleRates,
    ResourceLimit,
    StorageUnavailable,
    StorageLow,
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
            Self::StorageUnavailable => "profile_block_storage_unavailable",
            Self::StorageLow => "profile_block_storage_low",
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

#[derive(Debug, Clone)]
pub struct TrialFrameSpan {
    pub start: u64,
    pub end: u64,
    pub source_frames: u64,
    pub iti_frames: u64,
    pub tactile_shift_frames: u64,
    pub tactile_compensation_note: &'static str,
    pub(crate) prepared_channels: u16,
    pub(crate) tactile_waveform: Option<TactileWaveform>,
    pub(crate) speaker_switching: Option<SpeakerSwitching>,
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
    channels: u16,
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
        self.channels
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

pub(crate) fn row_value<'a>(
    fields: &'a BTreeMap<String, String>,
    names: &[&str],
) -> Option<&'a str> {
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

fn tactile_number(value: Option<&str>, default: f64) -> Result<f64, BlockMediaError> {
    if value
        .and_then(|text| text.trim().parse::<f64>().ok())
        .is_some_and(|parsed| !parsed.is_finite())
    {
        return Err(BlockMediaError(BlockMediaErrorCode::TransformUnsupported));
    }
    Ok(number(value, default))
}

pub(crate) fn family(fields: &BTreeMap<String, String>) -> &'static str {
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

#[derive(Debug, Clone)]
pub(crate) struct SpeakerSegment {
    start: u64,
    end: u64,
    channel: u16,
    gain: f32,
}

#[derive(Debug, Clone)]
pub(crate) struct SpeakerSwitching {
    pub(crate) channels: Vec<u16>,
    pub(crate) times_ms: Vec<f64>,
    pub(crate) gains: Vec<f64>,
    pub(crate) source_channel: String,
    pub(crate) tactile_channel: u16,
    pub(crate) prepared_channels: u16,
    segments: Vec<SpeakerSegment>,
    mixdown: bool,
    source_index: usize,
}

fn contract_parts(text: &str) -> impl Iterator<Item = &str> {
    text.split(['|', ';', ','])
        .map(str::trim)
        .filter(|part| !part.is_empty())
}

fn speaker_switching(
    fields: &BTreeMap<String, String>,
    frames: u64,
    sample_rate_hz: u32,
    source_channels: u16,
) -> Result<Option<SpeakerSwitching>, BlockMediaError> {
    let channel_text = row_value(
        fields,
        &[
            "speaker_switch_channels",
            "Speaker_Switch_Channels",
            "speaker_output_channels",
            "Speaker_Output_Channels",
        ],
    )
    .unwrap_or("")
    .trim();
    let times_text = row_value(
        fields,
        &[
            "speaker_switch_times_ms",
            "Speaker_Switch_Times_ms",
            "speaker_switch_boundaries_ms",
            "Speaker_Switch_Boundaries_ms",
        ],
    )
    .unwrap_or("")
    .trim();
    if channel_text.is_empty() && times_text.is_empty() {
        return Ok(None);
    }
    let channels: Vec<u16> = contract_parts(channel_text)
        .filter_map(|part| part.parse::<f64>().ok())
        .filter(|value| value.is_finite() && *value >= 1.0)
        .map(|value| value.trunc().min(f64::from(u16::MAX)) as u16)
        .filter(|channel| *channel > 0)
        .collect();
    let mut times_ms: Vec<f64> = contract_parts(times_text)
        .filter_map(|part| part.parse::<f64>().ok())
        .filter(|value| value.is_finite() && *value >= 0.0)
        .collect();
    if channels.is_empty() || times_ms.is_empty() {
        return Err(BlockMediaError(BlockMediaErrorCode::TransformUnsupported));
    }
    if channels
        .iter()
        .any(|channel| *channel > MAXIMUM_OUTPUT_CHANNELS)
    {
        return Err(BlockMediaError(BlockMediaErrorCode::TransformUnsupported));
    }
    if times_ms.len() == channels.len() {
        times_ms.push(
            times_ms[times_ms.len() - 1].max(frames as f64 / f64::from(sample_rate_hz) * 1000.0),
        );
    }
    if times_ms.len() != channels.len() + 1 || times_ms.windows(2).any(|pair| pair[1] < pair[0]) {
        return Err(BlockMediaError(BlockMediaErrorCode::TransformUnsupported));
    }
    let gain_text =
        row_value(fields, &["speaker_switch_gains", "Speaker_Switch_Gains"]).unwrap_or("");
    let mut gains: Vec<f64> = contract_parts(gain_text)
        .filter_map(|part| part.parse::<f64>().ok())
        .filter(|value| value.is_finite())
        .collect();
    if gains.is_empty() {
        gains = vec![1.0; channels.len()];
    }
    if gains.len() != channels.len() || gains.iter().any(|value| value.abs() > f64::from(f32::MAX))
    {
        return Err(BlockMediaError(BlockMediaErrorCode::TransformUnsupported));
    }
    let source_channel = row_value(
        fields,
        &["speaker_source_channel", "Speaker_Source_Channel"],
    )
    .unwrap_or("1")
    .trim();
    let source_channel = if source_channel.is_empty() {
        "1".to_owned()
    } else {
        source_channel.to_owned()
    };
    let mixdown = matches!(
        source_channel.to_ascii_lowercase().as_str(),
        "mix" | "mixdown" | "mean" | "mono" | "mono_mixdown"
    );
    let source_index = if mixdown {
        0
    } else {
        let index = source_channel
            .parse::<f64>()
            .ok()
            .filter(|value| value.is_finite())
            .unwrap_or(1.0)
            .trunc()
            .max(1.0)
            - 1.0;
        if index >= f64::from(source_channels) {
            return Err(BlockMediaError(BlockMediaErrorCode::TransformUnsupported));
        }
        index as usize
    };
    let tactile_channel = number(
        row_value(fields, &["tactile_channel", "Tactile_Channel"]),
        0.0,
    )
    .trunc()
    .max(0.0);
    if tactile_channel > f64::from(MAXIMUM_OUTPUT_CHANNELS) {
        return Err(BlockMediaError(BlockMediaErrorCode::TransformUnsupported));
    }
    let tactile_channel = tactile_channel as u16;
    let prepared_channels = source_channels
        .max(channels.iter().copied().max().unwrap_or(0))
        .max(tactile_channel);
    let mut segments = Vec::with_capacity(channels.len());
    for (index, channel) in channels.iter().enumerate() {
        let start =
            bounded_frames(times_ms[index] / 1000.0 * f64::from(sample_rate_hz))?.min(frames);
        let end =
            bounded_frames(times_ms[index + 1] / 1000.0 * f64::from(sample_rate_hz))?.min(frames);
        segments.push(SpeakerSegment {
            start,
            end,
            channel: *channel,
            gain: gains[index] as f32,
        });
    }
    Ok(Some(SpeakerSwitching {
        channels,
        times_ms,
        gains,
        source_channel,
        tactile_channel,
        prepared_channels,
        segments,
        mixdown,
        source_index,
    }))
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum TactileShape {
    Sawtooth,
    Sine,
    Square,
    BiphasicSquarePulseTrain,
}

impl TactileShape {
    pub(crate) const fn as_str(self) -> &'static str {
        match self {
            Self::Sawtooth => "sawtooth",
            Self::Sine => "sine",
            Self::Square => "square",
            Self::BiphasicSquarePulseTrain => "biphasic_square_pulse_train",
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub(crate) struct TactileWaveform {
    pub(crate) shape: TactileShape,
    pub(crate) frequency_hz: f64,
    pub(crate) duration_ms: f64,
    pub(crate) amplitude: f32,
    pub(crate) channel: u16,
    start: u64,
    frames: u64,
    period_frames: u64,
    pulse_frames: u64,
    pulse_count: u64,
}

impl TactileWaveform {
    fn stop(self) -> u64 {
        self.start + self.frames
    }

    fn sample(self, relative_frame: u64, sample_rate_hz: u32) -> f32 {
        let value = match self.shape {
            TactileShape::BiphasicSquarePulseTrain => {
                let pulse = (relative_frame / self.period_frames).min(self.pulse_count - 1);
                let position = relative_frame - pulse * self.period_frames;
                if position >= self.pulse_frames {
                    0.0
                } else if position < (self.pulse_frames / 2).max(1) {
                    1.0
                } else {
                    -1.0
                }
            }
            shape => {
                let time = relative_frame as f32 / sample_rate_hz as f32;
                let cycles = time * self.frequency_hz as f32;
                let phase = cycles.fract();
                match shape {
                    TactileShape::Sawtooth => 2.0 * phase - 1.0,
                    TactileShape::Square => {
                        if phase < 0.5 {
                            1.0
                        } else {
                            -1.0
                        }
                    }
                    TactileShape::Sine => {
                        ((std::f64::consts::TAU * self.frequency_hz) as f32 * time).sin()
                    }
                    TactileShape::BiphasicSquarePulseTrain => unreachable!(),
                }
            }
        };
        value * self.amplitude
    }
}

fn bounded_frames(value: f64) -> Result<u64, BlockMediaError> {
    let value = value.round_ties_even();
    if !value.is_finite() || value < 0.0 || value > u64::MAX as f64 {
        return Err(BlockMediaError(BlockMediaErrorCode::ResourceLimit));
    }
    Ok(value as u64)
}

fn tactile_waveform(
    fields: &BTreeMap<String, String>,
    trial_family: &str,
    sample_rate_hz: u32,
) -> Result<Option<TactileWaveform>, BlockMediaError> {
    if !matches!(trial_family, "audio_tactile" | "baseline") {
        return Ok(None);
    }
    let raw_shape = row_value(
        fields,
        &["tactile_waveform_shape", "Tactile_Waveform_Shape"],
    )
    .unwrap_or("")
    .trim();
    let frequency_hz = tactile_number(
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
    )?;
    if raw_shape.is_empty() && frequency_hz <= 0.0 {
        return Ok(None);
    }
    let token = raw_shape
        .to_ascii_lowercase()
        .split(|character: char| !character.is_ascii_alphanumeric())
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>()
        .join("_");
    let shape = match token.as_str() {
        "saw" | "saw_tooth" | "sawtooth" | "ramp" => TactileShape::Sawtooth,
        "sine" | "sin" | "sinusoid" | "sinusoidal" => TactileShape::Sine,
        "square" | "pulse" => TactileShape::Square,
        "pulse_train"
        | "square_pulse_train"
        | "biphasic_pulse"
        | "biphasic_square_pulse"
        | "biphasic_square_pulse_train" => TactileShape::BiphasicSquarePulseTrain,
        _ => return Err(BlockMediaError(BlockMediaErrorCode::TransformUnsupported)),
    };
    let duration_ms = tactile_number(
        row_value(
            fields,
            &[
                "tactile_duration_ms",
                "Tactile_Duration_ms",
                "tactile_waveform_duration_ms",
                "Tactile_Waveform_Duration_ms",
            ],
        ),
        0.0,
    )?;
    if frequency_hz <= 0.0 || duration_ms <= 0.0 {
        return Err(BlockMediaError(BlockMediaErrorCode::TransformUnsupported));
    }
    let pulse_duration_ms = tactile_number(
        row_value(
            fields,
            &[
                "tactile_pulse_duration_ms",
                "Tactile_Pulse_Duration_ms",
                "tactile_waveform_pulse_duration_ms",
                "Tactile_Waveform_Pulse_Duration_ms",
            ],
        ),
        0.0,
    )?;
    if shape == TactileShape::BiphasicSquarePulseTrain && pulse_duration_ms <= 0.0 {
        return Err(BlockMediaError(BlockMediaErrorCode::TransformUnsupported));
    }
    let channel = number(
        row_value(fields, &["tactile_channel", "Tactile_Channel"]),
        3.0,
    )
    .trunc()
    .max(1.0);
    if channel > f64::from(MAXIMUM_OUTPUT_CHANNELS) {
        return Err(BlockMediaError(BlockMediaErrorCode::TransformUnsupported));
    }
    let start = bounded_frames(tactile_onset_s(fields, trial_family) * f64::from(sample_rate_hz))?;
    let mut frames = bounded_frames(duration_ms / 1000.0 * f64::from(sample_rate_hz))?.max(1);
    let mut period_frames = 1;
    let mut pulse_frames = 2;
    let mut pulse_count = 1;
    if shape == TactileShape::BiphasicSquarePulseTrain {
        period_frames = bounded_frames(f64::from(sample_rate_hz) / frequency_hz)?.max(1);
        pulse_frames =
            bounded_frames(pulse_duration_ms / 1000.0 * f64::from(sample_rate_hz))?.max(2);
        let count = (duration_ms / 1000.0 * frequency_hz + 1.0e-9).floor();
        if !count.is_finite() || count > u64::MAX as f64 - 1.0 {
            return Err(BlockMediaError(BlockMediaErrorCode::ResourceLimit));
        }
        pulse_count = (count.max(1.0) as u64)
            .checked_add(1)
            .ok_or(BlockMediaError(BlockMediaErrorCode::ResourceLimit))?;
        frames = frames.max(
            (pulse_count - 1)
                .checked_mul(period_frames)
                .and_then(|value| value.checked_add(pulse_frames))
                .ok_or(BlockMediaError(BlockMediaErrorCode::ResourceLimit))?,
        );
    }
    start
        .checked_add(frames)
        .ok_or(BlockMediaError(BlockMediaErrorCode::ResourceLimit))?;
    if std::f64::consts::TAU * frequency_hz * frames as f64 / f64::from(sample_rate_hz)
        > f64::from(f32::MAX)
    {
        return Err(BlockMediaError(BlockMediaErrorCode::TransformUnsupported));
    }
    Ok(Some(TactileWaveform {
        shape,
        frequency_hz,
        duration_ms,
        amplitude: tactile_number(
            row_value(
                fields,
                &[
                    "tactile_amplitude",
                    "Tactile_Amplitude",
                    "tactile_waveform_amplitude",
                ],
            ),
            0.2,
        )?
        .clamp(0.0, 1.0) as f32,
        channel: channel as u16,
        start,
        frames,
        period_frames,
        pulse_frames,
        pulse_count,
    }))
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

pub(crate) fn looming_onset_s(fields: &BTreeMap<String, String>) -> f64 {
    row_value(fields, &["looming_segment_onset_s", "Looming_Onset_S"])
        .map(|value| number(Some(value), 0.0).max(0.0))
        .unwrap_or_else(|| looming_from_filename(fields))
}

pub(crate) fn tactile_onset_s(fields: &BTreeMap<String, String>, trial_family: &str) -> f64 {
    if let Some(explicit) = row_value(fields, &["tactile_onset_s", "Tactile_Onset_S"]) {
        return number(Some(explicit), 0.0).max(0.0);
    }
    if matches!(trial_family, "catch" | "auditory_only") {
        return 0.0;
    }
    let looming = looming_onset_s(fields);
    let soa_ms = number(row_value(fields, &["soa_ms", "SOA_ms"]), 0.0);
    ((looming + soa_ms / 1000.0).max(0.0) * 1_000_000.0).round_ties_even() / 1_000_000.0
}

pub(crate) fn compensation_ms() -> f64 {
    env::var("PPS_WOOJER_TACTILE_COMPENSATION_MS")
        .ok()
        .and_then(|value| value.trim().parse::<f64>().ok())
        .filter(|value| value.is_finite())
        .unwrap_or(DEFAULT_TACTILE_COMPENSATION_MS)
        .max(0.0)
}

fn tactile_shift(
    tactile_sample: impl Fn(usize) -> f32,
    channels: u16,
    frames: usize,
    sample_rate_hz: u32,
    onset_s: f64,
    trial_family: &str,
) -> (usize, &'static str) {
    if !matches!(trial_family, "audio_tactile" | "baseline") {
        return (0, "no_tactile_trial");
    }
    let compensation = compensation_ms();
    if compensation <= 0.0 {
        return (0, "compensation_disabled");
    }
    if channels < 3 {
        return (0, "no_tactile_channel_available");
    }
    let nominal = (onset_s * f64::from(sample_rate_hz))
        .round_ties_even()
        .max(0.0) as usize;
    let drive_s = (onset_s - compensation / 1000.0).max(0.0);
    let drive = (drive_s * f64::from(sample_rate_hz))
        .round_ties_even()
        .max(0.0) as usize;
    if drive >= nominal {
        return (0, "no_advance_after_clamp");
    }
    if nominal >= frames {
        return (0, "nominal_onset_outside_trial_audio");
    }
    let last_active = (0..frames)
        .rev()
        .find(|frame| tactile_sample(*frame).abs() > 1.0e-7);
    if last_active.is_none_or(|last| last < nominal) {
        return if last_active.is_none() {
            (0, "empty_tactile_channel")
        } else {
            (0, "tactile_signal_before_nominal_onset")
        };
    }
    (nominal - drive, "tactile_channel_shifted_earlier")
}

fn trial_sample(
    samples: &[f32],
    source_channels: usize,
    source_frames: usize,
    waveform: Option<TactileWaveform>,
    frame: usize,
    channel: usize,
    sample_rate_hz: u32,
) -> f32 {
    if let Some(waveform) = waveform {
        let frame = frame as u64;
        if usize::from(waveform.channel) == channel + 1
            && frame >= waveform.start
            && frame < waveform.stop()
        {
            return waveform.sample(frame - waveform.start, sample_rate_hz);
        }
    }
    if frame < source_frames && channel < source_channels {
        samples[frame * source_channels + channel]
    } else {
        0.0
    }
}

fn output_sample(value: f32) -> i16 {
    // Match libsndfile's float32-to-PCM16 conversion used by the Python oracle.
    (value.clamp(-1.0, 1.0) * 32768.0)
        .floor()
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

fn require_storage(estimated_bytes: u64, available_bytes: u64) -> Result<(), BlockMediaError> {
    let required_bytes = estimated_bytes
        .checked_mul(3)
        .and_then(|bytes| bytes.checked_add(STORAGE_RESERVE_BYTES))
        .ok_or(BlockMediaError(BlockMediaErrorCode::ResourceLimit))?;
    if available_bytes < required_bytes {
        return Err(BlockMediaError(BlockMediaErrorCode::StorageLow));
    }
    Ok(())
}

/// Assemble one bounded PCM16 block from approved 2/3-channel trial sources.
/// The block width is the largest trial output width, with a three-channel
/// minimum. Each output position has the same 1-based meaning as its row.
/// Publication never overwrites.
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
    let mut output_channels = MINIMUM_OUTPUT_CHANNELS;
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
        let waveform = tactile_waveform(trial.fields(), family(trial.fields()), sample_rate_hz)?;
        let trial_frames = hint.frames().max(waveform.map_or(0, TactileWaveform::stop));
        let source_prepared_channels = hint
            .channels()
            .max(waveform.map_or(0, |value| value.channel));
        let switching = speaker_switching(
            trial.fields(),
            trial_frames,
            sample_rate_hz,
            source_prepared_channels,
        )?;
        output_channels = output_channels.max(
            switching
                .as_ref()
                .map_or(source_prepared_channels, |spec| spec.prepared_channels),
        );
        estimated_frames = estimated_frames
            .checked_add(trial_frames)
            .and_then(|frames| frames.checked_add(iti_frames(trial.fields(), sample_rate_hz).ok()?))
            .ok_or(BlockMediaError(BlockMediaErrorCode::ResourceLimit))?;
    }
    let parent = output_path
        .parent()
        .filter(|path| !path.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    if !parent.is_dir() {
        return Err(BlockMediaError(BlockMediaErrorCode::OutputFailed));
    }
    let estimated_bytes = estimated_frames
        .checked_mul(u64::from(output_channels) * 2)
        .and_then(|bytes| bytes.checked_add(44))
        .filter(|bytes| *bytes <= MAX_OUTPUT_WAV_BYTES)
        .ok_or(BlockMediaError(BlockMediaErrorCode::ResourceLimit))?;
    // Like the Python generation preflight, allow room for output, scratch,
    // and filesystem overhead before decoding any trial or creating a file.
    let available_bytes = fs2::available_space(parent)
        .map_err(|_| BlockMediaError(BlockMediaErrorCode::StorageUnavailable))?;
    require_storage(estimated_bytes, available_bytes)?;
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
        channels: output_channels,
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
        let source_frames = usize::try_from(media.frames())
            .map_err(|_| BlockMediaError(BlockMediaErrorCode::ResourceLimit))?;
        let samples = media.interleaved_f32();
        let trial_family = family(trial.fields());
        let waveform = tactile_waveform(trial.fields(), trial_family, sample_rate_hz)?;
        let frames = usize::try_from(
            media
                .frames()
                .max(waveform.map_or(0, TactileWaveform::stop)),
        )
        .map_err(|_| BlockMediaError(BlockMediaErrorCode::ResourceLimit))?;
        let source_prepared_channels = media
            .channels()
            .max(waveform.map_or(0, |value| value.channel));
        let (shift, tactile_compensation_note) = tactile_shift(
            |frame| {
                trial_sample(
                    samples,
                    channels,
                    source_frames,
                    waveform,
                    frame,
                    2,
                    sample_rate_hz,
                )
            },
            source_prepared_channels,
            frames,
            sample_rate_hz,
            tactile_onset_s(trial.fields(), trial_family),
            trial_family,
        );
        let switching = speaker_switching(
            trial.fields(),
            frames as u64,
            sample_rate_hz,
            source_prepared_channels,
        )?;
        let prepared_channels = switching
            .as_ref()
            .map_or(source_prepared_channels, |spec| spec.prepared_channels);
        let prepared_sample = |frame: usize, channel: usize| {
            let source = if channel == 2 && shift > 0 {
                match frame.checked_add(shift).filter(|source| *source < frames) {
                    Some(source) => source,
                    None => return 0.0,
                }
            } else {
                frame
            };
            trial_sample(
                samples,
                channels,
                source_frames,
                waveform,
                source,
                channel,
                sample_rate_hz,
            )
        };
        let mut active_segment = 0;
        for frame in 0..frames {
            let segment = switching.as_ref().and_then(|spec| {
                while active_segment < spec.segments.len()
                    && frame as u64 >= spec.segments[active_segment].end
                {
                    active_segment += 1;
                }
                spec.segments
                    .get(active_segment)
                    .filter(|segment| frame as u64 >= segment.start && (frame as u64) < segment.end)
            });
            let source_signal = if let (Some(_), Some(spec)) = (segment, switching.as_ref()) {
                if spec.mixdown {
                    (prepared_sample(frame, 0) + prepared_sample(frame, 1)) * 0.5
                } else {
                    prepared_sample(frame, spec.source_index)
                }
            } else {
                0.0
            };
            for channel in 0..usize::from(output_channels) {
                let value = if let Some(spec) = switching.as_ref() {
                    let tactile = if spec.tactile_channel == channel as u16 + 1
                        && channel < usize::from(source_prepared_channels)
                    {
                        prepared_sample(frame, channel)
                    } else {
                        0.0
                    };
                    tactile
                        + segment
                            .filter(|segment| segment.channel == channel as u16 + 1)
                            .map_or(0.0, |segment| source_signal * segment.gain)
                } else {
                    prepared_sample(frame, channel)
                };
                writer
                    .write_sample(output_sample(value))
                    .map_err(|_| BlockMediaError(BlockMediaErrorCode::OutputFailed))?;
            }
        }
        let iti = iti_frames(trial.fields(), sample_rate_hz)?;
        for _ in 0..iti {
            for _ in 0..output_channels {
                writer
                    .write_sample(0_i16)
                    .map_err(|_| BlockMediaError(BlockMediaErrorCode::OutputFailed))?;
            }
        }
        let end = cursor
            .checked_add(frames as u64)
            .and_then(|value| value.checked_add(iti))
            .ok_or(BlockMediaError(BlockMediaErrorCode::ResourceLimit))?;
        spans.push(TrialFrameSpan {
            start: cursor,
            end,
            source_frames: media.frames(),
            iti_frames: iti,
            tactile_shift_frames: shift as u64,
            tactile_compensation_note,
            prepared_channels,
            tactile_waveform: waveform,
            speaker_switching: switching,
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
        channels: output_channels,
        spans,
    })
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use super::{
        require_storage, speaker_switching, tactile_waveform, BlockMediaErrorCode,
        STORAGE_RESERVE_BYTES,
    };

    #[test]
    fn storage_preflight_keeps_three_output_copies_and_a_reserve() {
        let required = 3 * 1024 * 1024 + STORAGE_RESERVE_BYTES;
        assert_eq!(
            require_storage(1024 * 1024, required - 1).unwrap_err().0,
            BlockMediaErrorCode::StorageLow
        );
        assert!(require_storage(1024 * 1024, required).is_ok());
        assert_eq!(
            require_storage(u64::MAX, u64::MAX).unwrap_err().0,
            BlockMediaErrorCode::ResourceLimit
        );
    }

    #[test]
    fn tactile_profile_rejects_nonfinite_or_unroutable_values() {
        let mut fields = BTreeMap::from([
            ("tactile_waveform_shape".to_owned(), "square".to_owned()),
            ("tactile_frequency_hz".to_owned(), "100".to_owned()),
            ("tactile_duration_ms".to_owned(), "10".to_owned()),
        ]);
        fields.insert("tactile_frequency_hz".to_owned(), "NaN".to_owned());
        assert_eq!(
            tactile_waveform(&fields, "audio_tactile", 44_100)
                .unwrap_err()
                .0,
            BlockMediaErrorCode::TransformUnsupported
        );
        fields.insert("tactile_frequency_hz".to_owned(), "100".to_owned());
        fields.insert("tactile_channel".to_owned(), "19".to_owned());
        assert_eq!(
            tactile_waveform(&fields, "audio_tactile", 44_100)
                .unwrap_err()
                .0,
            BlockMediaErrorCode::TransformUnsupported
        );
    }

    #[test]
    fn speaker_switching_rejects_reversed_or_incomplete_boundaries() {
        let mut fields = BTreeMap::from([
            ("speaker_switch_channels".to_owned(), "1|2".to_owned()),
            ("speaker_switch_times_ms".to_owned(), "0|50|40".to_owned()),
        ]);
        assert_eq!(
            speaker_switching(&fields, 4_000, 44_100, 3).unwrap_err().0,
            BlockMediaErrorCode::TransformUnsupported
        );
        fields.insert("speaker_switch_times_ms".to_owned(), "0".to_owned());
        assert_eq!(
            speaker_switching(&fields, 4_000, 44_100, 3).unwrap_err().0,
            BlockMediaErrorCode::TransformUnsupported
        );
    }
}
