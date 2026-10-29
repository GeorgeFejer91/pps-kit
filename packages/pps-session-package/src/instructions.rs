//! Verify instruction media from one bounded byte snapshot before native use.
use std::{collections::BTreeSet, io::Cursor, path::Path};

use serde_json::{Map, Value};

use crate::{
    read_bounded_bytes, sha256_bytes, VerificationError, VerificationErrorCode, VerifiedPreparedWav,
};

const MAX_INSTRUCTION_BYTES: usize = 64 * 1024 * 1024;
const MAX_PROFILE_BYTES: usize = 128 * 1024 * 1024;

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum InstructionSlot {
    BeforeExperiment,
    BeforeEachBlock,
    AfterEachBlock,
    BetweenConditions,
    AfterExperiment,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InstructionContinueMode {
    Click,
    Button,
    Delay,
}

/// Native-only receipt; paths/hashes are never part of a public snapshot.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VerifiedInstruction {
    slot: InstructionSlot,
    label: String,
    button_label: String,
    continue_mode: InstructionContinueMode,
    delay_ns: u64,
    wav: VerifiedPreparedWav,
    sample_rate_hz: u32,
    channels: u16,
    frames: u64,
}

impl VerifiedInstruction {
    pub const fn slot(&self) -> InstructionSlot {
        self.slot
    }
    pub fn label(&self) -> &str {
        &self.label
    }
    pub fn button_label(&self) -> &str {
        &self.button_label
    }
    pub const fn continue_mode(&self) -> InstructionContinueMode {
        self.continue_mode
    }
    pub const fn delay_ns(&self) -> u64 {
        self.delay_ns
    }
    pub fn wav(&self) -> &VerifiedPreparedWav {
        &self.wav
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
}

fn invalid(detail: &str) -> VerificationError {
    VerificationError::new(
        VerificationErrorCode::InstructionInvalid,
        "Instruction media or its saved settings are invalid; regenerate the prepared session.",
        detail,
    )
}

fn text<'a>(value: &'a Value, key: &str) -> Result<&'a str, VerificationError> {
    value[key]
        .as_str()
        .filter(|s| !s.is_empty() && s.len() <= 4096 && !s.chars().any(char::is_control))
        .ok_or_else(|| invalid("Instruction text is missing or exceeds its limit."))
}

pub(super) fn verify_instructions(
    object: &Map<String, Value>,
    session_dir: &Path,
) -> Result<Vec<VerifiedInstruction>, VerificationError> {
    let Some(profile) = object.get("instruction_profile").filter(|v| !v.is_null()) else {
        return Ok(Vec::new());
    };
    if profile["schema"] != "pps-run-instructions.v1" {
        return Err(invalid("Unsupported instruction profile schema."));
    }
    let slots = profile["slots"]
        .as_array()
        .filter(|s| s.len() <= 5)
        .ok_or_else(|| invalid("Instruction slots must be a bounded list."))?;
    let mut seen = BTreeSet::new();
    let mut instructions = Vec::new();
    let mut bytes_used = 0usize;
    for item in slots {
        let slot = match item["slot"].as_str() {
            Some("before_experiment") => InstructionSlot::BeforeExperiment,
            Some("before_each_block") => InstructionSlot::BeforeEachBlock,
            Some("after_each_block") => InstructionSlot::AfterEachBlock,
            Some("between_conditions") => InstructionSlot::BetweenConditions,
            Some("after_experiment") => InstructionSlot::AfterExperiment,
            _ => return Err(invalid("Unknown instruction slot.")),
        };
        if !seen.insert(slot) {
            return Err(invalid("Duplicate instruction slot."));
        }
        match item["enabled"].as_bool() {
            Some(false) => continue,
            Some(true) => (),
            None => return Err(invalid("Instruction enabled flag must be boolean.")),
        }
        let continue_mode = match item["continue_mode"].as_str() {
            Some("click") => InstructionContinueMode::Click,
            Some("button") => InstructionContinueMode::Button,
            Some("delay") => InstructionContinueMode::Delay,
            _ => return Err(invalid("Unsupported instruction continuation mode.")),
        };
        let delay = item["delay_s"]
            .as_f64()
            .filter(|n| n.is_finite() && (0.0..=3600.0).contains(n))
            .ok_or_else(|| invalid("Invalid instruction continuation delay."))?;
        let raw_path = Path::new(text(item, "path")?);
        crate::ensure_native_path_syntax(raw_path)?;
        let path = if raw_path.is_absolute() {
            raw_path.to_owned()
        } else {
            session_dir.join(raw_path)
        };
        let root = std::fs::canonicalize(session_dir)
            .map_err(|_| invalid("Instruction root is missing."))?;
        let path =
            std::fs::canonicalize(path).map_err(|_| invalid("Instruction WAV is missing."))?;
        if !path.starts_with(&root) || !path.is_file() {
            return Err(invalid(
                "Instruction WAV must be contained in its prepared session.",
            ));
        }
        let bytes = read_bounded_bytes(&path, MAX_INSTRUCTION_BYTES)
            .map_err(|_| invalid("Instruction WAV cannot be read within its byte limit."))?;
        bytes_used = bytes_used
            .checked_add(bytes.len())
            .filter(|n| *n <= MAX_PROFILE_BYTES)
            .ok_or_else(|| invalid("Instruction profile exceeds its aggregate byte limit."))?;
        let sha256 = sha256_bytes(&bytes);
        if item["sha256"].as_str() != Some(sha256.as_str()) {
            return Err(invalid("Instruction WAV hash changed."));
        }
        let mut reader = hound::WavReader::new(Cursor::new(&bytes))
            .map_err(|_| invalid("Instruction WAV header cannot be decoded."))?;
        let spec = reader.spec();
        let frames = u64::from(reader.duration());
        if !matches!(spec.channels, 1 | 2)
            || !(8000..=192000).contains(&spec.sample_rate)
            || frames == 0
            || frames > u64::from(spec.sample_rate) * 3600
            || item["channels"].as_u64() != Some(u64::from(spec.channels))
            || item["sample_rate"].as_u64() != Some(u64::from(spec.sample_rate))
            || !item["duration_s"].as_f64().is_some_and(|duration| {
                duration.is_finite()
                    && (duration - frames as f64 / f64::from(spec.sample_rate)).abs() <= 1e-9
            })
        {
            return Err(invalid(
                "Instruction WAV metadata does not match its actual samples.",
            ));
        }
        // Verify every sample, without retaining another decoded allocation.
        let count = match (spec.sample_format, spec.bits_per_sample) {
            (hound::SampleFormat::Float, 32) => {
                reader.samples::<f32>().try_fold(0u64, |count, sample| {
                    sample
                        .ok()
                        .filter(|s| s.is_finite() && s.abs() <= 1.0)
                        .map(|_| count + 1)
                })
            }
            (hound::SampleFormat::Int, 16 | 24 | 32) => reader
                .samples::<i32>()
                .try_fold(0u64, |count, sample| sample.ok().map(|_| count + 1)),
            _ => None,
        };
        if count != Some(frames * u64::from(spec.channels)) {
            return Err(invalid(
                "Instruction WAV samples are truncated, nonfinite or unsupported.",
            ));
        }
        instructions.push(VerifiedInstruction {
            slot,
            label: text(item, "label")?.to_owned(),
            button_label: text(item, "button_label")?.to_owned(),
            continue_mode,
            delay_ns: (delay * 1e9).round() as u64,
            wav: VerifiedPreparedWav {
                path,
                sha256,
                encoded_byte_count: bytes.len() as u64,
            },
            sample_rate_hz: spec.sample_rate,
            channels: spec.channels,
            frames,
        });
    }
    Ok(instructions)
}
