//! Build a V1 prepared-session package from an approved local Planner profile.
//!
//! The package is verified and its schedules are compiled before the canonical
//! manifest is published. Paths and receipts remain native-only.

use std::{
    collections::{BTreeMap, BTreeSet},
    fmt, fs,
    fs::OpenOptions,
    io::Write,
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
};

use csv::WriterBuilder;
use pps_runner_execution::{compile_verified_block_schedule, BlockScheduleOptions};
use pps_session_package::{
    experiment_plan::{select_profile_participant, ProfileBlockSource, ProfileParticipantPlan},
    experiment_profile::VerifiedExperimentProfile,
    verify_prepared_session, VerificationRequest, VerifiedPreparedSession,
    MAX_PREPARED_BLOCK_MANIFEST_BYTES, MAX_TOTAL_PREPARED_BLOCK_WAV_BYTES,
    PARTICIPANT_BLOCK_WAVS_MODE, RUN_PACKAGE_SCHEMA,
};
use serde_json::{json, Value};

use crate::block::{
    assemble_standard_profile_block, compensation_ms, family, looming_onset_s, row_value,
    tactile_onset_s, AssembledBlockWav, TrialFrameSpan,
};

static PACKAGE_SEQUENCE: AtomicU64 = AtomicU64::new(1);
const MAX_CSV_COLUMNS: usize = 256;
const MAX_CSV_FIELD_BYTES: usize = 16 * 1024;
const TACTILE_STATUS: &str = "provisional_woojer_audio_path_not_mechanical_onset";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ProfilePackageError(&'static str);

impl ProfilePackageError {
    pub const fn code(self) -> &'static str {
        self.0
    }
}

impl fmt::Display for ProfilePackageError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.0)
    }
}

impl std::error::Error for ProfilePackageError {}

fn package_error(code: &'static str) -> ProfilePackageError {
    ProfilePackageError(code)
}

struct PendingDirectory(PathBuf);

impl Drop for PendingDirectory {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

struct PublishedDirectory {
    path: PathBuf,
    linked: Vec<PathBuf>,
    retained: bool,
}

impl PublishedDirectory {
    fn new(path: PathBuf) -> Self {
        Self {
            path,
            linked: Vec::new(),
            retained: false,
        }
    }

    fn link(&mut self, source: &Path, target: PathBuf) -> Result<(), ProfilePackageError> {
        fs::hard_link(source, &target)
            .map_err(|_| package_error("profile_package_output_failed"))?;
        self.linked.push(target);
        Ok(())
    }

    fn retain(&mut self) {
        self.retained = true;
    }
}

impl Drop for PublishedDirectory {
    fn drop(&mut self) {
        if !self.retained {
            for path in self.linked.iter().rev() {
                let _ = fs::remove_file(path);
            }
            let _ = fs::remove_dir(self.path.join("blocks"));
            let _ = fs::remove_dir(&self.path);
        }
    }
}

fn path_text(path: &Path) -> Result<&str, ProfilePackageError> {
    path.to_str()
        .ok_or(package_error("profile_package_path_unsupported"))
}

fn field<'a>(fields: &'a BTreeMap<String, String>, names: &[&str]) -> &'a str {
    row_value(fields, names).unwrap_or("").trim()
}

fn order_number(
    fields: &BTreeMap<String, String>,
    name: &str,
    fallback: i64,
) -> Result<i64, ProfilePackageError> {
    let value = match fields
        .get(name)
        .map(String::as_str)
        .filter(|value| !value.trim().is_empty())
    {
        Some(value) => value
            .trim()
            .parse::<i64>()
            .map_err(|_| package_error("profile_package_order_invalid")),
        None => Ok(fallback),
    }?;
    (value > 0)
        .then_some(value)
        .ok_or(package_error("profile_package_order_invalid"))
}

fn phase(block: &ProfileBlockSource) -> Result<&'static str, ProfilePackageError> {
    let token = field(block.order_fields(), &["phase"]);
    if token.is_empty() || token.eq_ignore_ascii_case("single") {
        Ok("single")
    } else if token.eq_ignore_ascii_case("pre") {
        Ok("pre")
    } else if token.eq_ignore_ascii_case("post") {
        Ok("post")
    } else {
        Err(package_error("profile_package_phase_unsupported"))
    }
}

fn display_phase(phase: &str) -> &'static str {
    match phase {
        "pre" => "Pre",
        "post" => "Post",
        _ => "Single",
    }
}

fn trial_type(trial_family: &str) -> &'static str {
    match trial_family {
        "baseline" => "Baseline",
        "catch" => "Catch",
        "auditory_only" => "Auditory-Only",
        _ => "Audio-Tactile",
    }
}

fn set(row: &mut BTreeMap<String, String>, name: &str, value: impl ToString) {
    row.retain(|key, _| !key.eq_ignore_ascii_case(name));
    row.insert(name.to_owned(), value.to_string());
}

fn set_alias(
    row: &mut BTreeMap<String, String>,
    source: &BTreeMap<String, String>,
    name: &str,
    aliases: &[&str],
) {
    set(row, name, field(source, aliases));
}

fn six_significant(value: f64) -> String {
    let scientific = format!("{value:.5e}");
    let (mantissa, exponent) = scientific.split_once('e').unwrap_or(("0", "0"));
    let exponent = exponent.parse::<i32>().unwrap_or(0);
    fn trim(text: &str) -> &str {
        if text.contains('.') {
            text.trim_end_matches('0').trim_end_matches('.')
        } else {
            text
        }
    }
    if (-4..6).contains(&exponent) {
        trim(&format!("{:.*}", (5 - exponent) as usize, value)).to_owned()
    } else {
        format!("{}e{exponent:+03}", trim(mantissa))
    }
}

fn sample_at(start: u64, relative_s: f64, rate: u32) -> u64 {
    (((start as f64 / f64::from(rate)) + relative_s) * f64::from(rate))
        .round_ties_even()
        .max(0.0) as u64
}

fn prepared_row(
    plan: &ProfileParticipantPlan,
    block: &ProfileBlockSource,
    span: &TrialFrameSpan,
    ordinal: usize,
    trial_index: usize,
    session_id: &str,
    rate: u32,
) -> Result<BTreeMap<String, String>, ProfilePackageError> {
    let phase = phase(block)?;
    let part_number = if phase == "post" { 2 } else { 1 };
    let trial = block
        .trials()
        .get(trial_index - 1)
        .ok_or(package_error("profile_package_plan_invalid"))?;
    let source = trial.fields();
    let trial_family = family(source);
    let has_audio = matches!(trial_family, "audio_tactile" | "catch" | "auditory_only");
    let has_tactile = matches!(trial_family, "audio_tactile" | "baseline");
    let looming = looming_onset_s(source);
    let tactile = tactile_onset_s(source, trial_family);
    let nominal = (tactile * f64::from(rate)).round_ties_even().max(0.0) as u64;
    let drive = if span.tactile_shift_frames > 0 {
        nominal.saturating_sub(span.tactile_shift_frames) as f64 / f64::from(rate)
    } else {
        tactile
    };
    let response = if has_audio { looming } else { tactile };
    let duration_s = (span.end - span.start) as f64 / f64::from(rate);
    let source_file = trial
        .audio_path()
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or(package_error("profile_package_path_unsupported"))?;
    let position = order_number(
        block.order_fields(),
        "participant_block_position",
        ordinal as i64,
    )?;
    let source_index = order_number(block.order_fields(), "source_block_index", position)?;
    let source_label = field(block.order_fields(), &["block_label"]);
    let source_label = if source_label.is_empty() {
        format!("Block {position:02}")
    } else {
        source_label.to_owned()
    };
    let phase_label = field(block.order_fields(), &["phase_label"]);
    let phase_label = if phase_label.is_empty() {
        display_phase(phase)
    } else {
        phase_label
    };
    let mut row = source.clone();
    set(&mut row, "Participant_ID", plan.participant_id());
    set(&mut row, "Session_ID", session_id);
    set(&mut row, "Part_Number", part_number);
    set(&mut row, "Phase", phase);
    set(&mut row, "Phase_Label", phase_label);
    set(&mut row, "Block_Number", ordinal);
    set(&mut row, "Block_Label", format!("Block {ordinal:02}"));
    set(&mut row, "Participant_Block_Position", position);
    set(&mut row, "Source_Block_Index", source_index);
    set(&mut row, "Source_Block_Label", source_label);
    set(
        &mut row,
        "Source_Block_CSV_Path",
        path_text(block.source_csv_path())?,
    );
    set(
        &mut row,
        "Source_Block_CSV_SHA256",
        block.source_csv_sha256(),
    );
    set(&mut row, "Trial_Number", trial_index);
    let pool_index = field(source, &["trial_pool_index"]);
    let pool_index = if pool_index.is_empty() {
        trial_index.to_string()
    } else {
        pool_index.to_owned()
    };
    set(
        &mut row,
        "Trial_UID",
        format!(
            "{}_{}_B{ordinal:02}_T{trial_index:03}_{pool_index}",
            plan.participant_id(),
            phase
        ),
    );
    set(&mut row, "Trial_Type", trial_type(trial_family));
    set(&mut row, "Family", trial_family);
    set_alias(&mut row, source, "SOA_ms", &["soa_ms", "SOA_ms"]);
    set_alias(
        &mut row,
        source,
        "Expected_Response",
        &[
            "expected_response",
            "Expected_Response",
            "response_expected",
            "Response_Expected",
            "required_response",
            "Required_Response",
        ],
    );
    set_alias(
        &mut row,
        source,
        "Response_Rule",
        &[
            "response_rule",
            "Response_Rule",
            "response_mapping",
            "Response_Mapping",
            "task_response_rule",
            "Task_Response_Rule",
        ],
    );
    set_alias(
        &mut row,
        source,
        "Target_Role",
        &[
            "target_role",
            "Target_Role",
            "go_nogo_role",
            "Go_NoGo_Role",
            "stimulus_role",
            "Stimulus_Role",
            "tactile_role",
            "Tactile_Role",
        ],
    );
    set_alias(
        &mut row,
        source,
        "Response_Mode",
        &[
            "response_mode",
            "Response_Mode",
            "choice_mode",
            "Choice_Mode",
            "task_response_mode",
            "Task_Response_Mode",
        ],
    );
    set_alias(
        &mut row,
        source,
        "Response_Choice_Set",
        &[
            "response_choice_set",
            "Response_Choice_Set",
            "choice_set",
            "Choice_Set",
            "response_choices",
            "Response_Choices",
            "response_options",
            "Response_Options",
        ],
    );
    set_alias(
        &mut row,
        source,
        "Correct_Response",
        &[
            "correct_response",
            "Correct_Response",
            "correct_choice",
            "Correct_Choice",
            "target_choice",
            "Target_Choice",
            "expected_choice",
            "Expected_Choice",
        ],
    );
    set_alias(
        &mut row,
        source,
        "Response_Scoring_Policy",
        &[
            "response_scoring_policy",
            "Response_Scoring_Policy",
            "choice_scoring_policy",
            "Choice_Scoring_Policy",
            "response_mapping_policy",
            "Response_Mapping_Policy",
        ],
    );
    set_alias(
        &mut row,
        source,
        "Response_Capture_Device",
        &[
            "response_capture_device",
            "Response_Capture_Device",
            "response_device",
            "Response_Device",
            "response_capture",
            "Response_Capture",
        ],
    );
    set_alias(
        &mut row,
        source,
        "Response_Input_Modality",
        &[
            "response_input_modality",
            "Response_Input_Modality",
            "response_modality",
            "Response_Modality",
            "input_modality",
            "Input_Modality",
        ],
    );
    let row_label = field(source, &["row_label", "Row_Label", "Row"]);
    set(&mut row, "Row", row_label);
    set(&mut row, "Row_Label", row_label);
    set(&mut row, "Respiratory_Phase", row_label);
    let primary_analysis = field(
        source,
        &["primary_analysis_included", "Primary_Analysis_Included"],
    );
    set(
        &mut row,
        "Primary_Analysis_Included",
        if primary_analysis.is_empty() {
            "true"
        } else {
            primary_analysis
        },
    );
    set_alias(
        &mut row,
        source,
        "Noise_Type",
        &["noise_type", "Noise_Type"],
    );
    set_alias(
        &mut row,
        source,
        "Baseline_Mode",
        &["baseline_mode", "Baseline_Mode"],
    );
    set_alias(
        &mut row,
        source,
        "Sequence_Labels",
        &["sequence_labels", "Sequence_Labels"],
    );
    set_alias(
        &mut row,
        source,
        "Sequence_Variant_Key",
        &["sequence_variant_key", "Sequence_Variant_Key"],
    );
    let switching = span.speaker_switching.as_ref();
    let mode = field(
        source,
        &[
            "audio_output_mode",
            "Audio_Output_Mode",
            "speaker_array_mode",
            "Speaker_Array_Mode",
        ],
    );
    set(
        &mut row,
        "Audio_Output_Mode",
        if mode.is_empty() && switching.is_some() {
            "switched_speaker_array"
        } else {
            mode
        },
    );
    set_alias(
        &mut row,
        source,
        "Speaker_Array_ID",
        &["speaker_array_id", "Speaker_Array_ID"],
    );
    set_alias(
        &mut row,
        source,
        "Speaker_Array_Layout",
        &["speaker_array_layout", "Speaker_Array_Layout"],
    );
    set_alias(
        &mut row,
        source,
        "Speaker_Switch_Sequence",
        &["speaker_switch_sequence", "Speaker_Switch_Sequence"],
    );
    let times = field(
        source,
        &[
            "speaker_switch_times_ms",
            "Speaker_Switch_Times_ms",
            "speaker_switch_boundaries_ms",
            "Speaker_Switch_Boundaries_ms",
        ],
    );
    set(
        &mut row,
        "Speaker_Switch_Times_ms",
        if times.is_empty() {
            switching.map_or_else(String::new, |spec| {
                spec.times_ms
                    .iter()
                    .map(|value| six_significant(*value))
                    .collect::<Vec<_>>()
                    .join("|")
            })
        } else {
            times.to_owned()
        },
    );
    let channels = field(
        source,
        &[
            "speaker_switch_channels",
            "Speaker_Switch_Channels",
            "speaker_output_channels",
            "Speaker_Output_Channels",
        ],
    );
    set(
        &mut row,
        "Speaker_Switch_Channels",
        if channels.is_empty() {
            switching.map_or_else(String::new, |spec| {
                spec.channels
                    .iter()
                    .map(u16::to_string)
                    .collect::<Vec<_>>()
                    .join("|")
            })
        } else {
            channels.to_owned()
        },
    );
    let gains = field(source, &["speaker_switch_gains", "Speaker_Switch_Gains"]);
    set(
        &mut row,
        "Speaker_Switch_Gains",
        if gains.is_empty() {
            switching.map_or_else(String::new, |spec| {
                spec.gains
                    .iter()
                    .map(|value| six_significant(*value))
                    .collect::<Vec<_>>()
                    .join("|")
            })
        } else {
            gains.to_owned()
        },
    );
    let source_channel = field(
        source,
        &["speaker_source_channel", "Speaker_Source_Channel"],
    );
    set(
        &mut row,
        "Speaker_Source_Channel",
        if source_channel.is_empty() {
            switching.map_or("", |spec| spec.source_channel.as_str())
        } else {
            source_channel
        },
    );
    set(
        &mut row,
        "Speaker_Switch_Generated",
        if switching.is_some() {
            "true"
        } else {
            field(
                source,
                &["speaker_switch_generated", "Speaker_Switch_Generated"],
            )
        },
    );
    set_alias(
        &mut row,
        source,
        "ITI_ms",
        &["iti_ms", "ITI_ms", "Intertrial_Interval_ms"],
    );
    let source_name = field(source, &["source_file_name", "Source_File_Name"]);
    set(
        &mut row,
        "Source_File_Name",
        if source_name.is_empty() {
            source_file
        } else {
            source_name
        },
    );
    set(&mut row, "Trial_File_Path", path_text(trial.audio_path())?);
    set(&mut row, "Source_SHA256", trial.ingredient().sha256());
    set(
        &mut row,
        "Duration_ms",
        (duration_s * 1000.0).round_ties_even() as u64,
    );
    set(&mut row, "Trial_Duration_S", format!("{duration_s:.9}"));
    set(&mut row, "Sample_Rate_Hz", rate);
    set(&mut row, "Channels", span.prepared_channels);
    let waveform = span.tactile_waveform;
    set(
        &mut row,
        "Tactile_Channel",
        if field(source, &["tactile_channel", "Tactile_Channel"]).is_empty() {
            waveform
                .map(|value| value.channel.to_string())
                .unwrap_or_default()
        } else {
            field(source, &["tactile_channel", "Tactile_Channel"]).to_owned()
        },
    );
    set(
        &mut row,
        "Tactile_Waveform_Shape",
        waveform.map_or_else(
            || {
                field(
                    source,
                    &["tactile_waveform_shape", "Tactile_Waveform_Shape"],
                )
                .to_owned()
            },
            |value| value.shape.as_str().to_owned(),
        ),
    );
    set(
        &mut row,
        "Tactile_Frequency_Hz",
        waveform.map_or_else(
            || {
                field(
                    source,
                    &[
                        "tactile_frequency_hz",
                        "Tactile_Frequency_Hz",
                        "tactile_waveform_frequency_hz",
                        "Tactile_Waveform_Frequency_Hz",
                    ],
                )
                .to_owned()
            },
            |value| six_significant(value.frequency_hz),
        ),
    );
    set(
        &mut row,
        "Tactile_Duration_ms",
        waveform.map_or_else(
            || {
                field(
                    source,
                    &[
                        "tactile_duration_ms",
                        "Tactile_Duration_ms",
                        "tactile_waveform_duration_ms",
                        "Tactile_Waveform_Duration_ms",
                    ],
                )
                .to_owned()
            },
            |value| six_significant(value.duration_ms),
        ),
    );
    set(
        &mut row,
        "Tactile_Amplitude",
        waveform.map_or_else(
            || {
                field(
                    source,
                    &[
                        "tactile_amplitude",
                        "Tactile_Amplitude",
                        "tactile_waveform_amplitude",
                    ],
                )
                .to_owned()
            },
            |value| six_significant(f64::from(value.amplitude)),
        ),
    );
    set_alias(
        &mut row,
        source,
        "Tactile_Pulse_Duration_ms",
        &[
            "tactile_pulse_duration_ms",
            "Tactile_Pulse_Duration_ms",
            "electrical_pulse_duration_ms",
            "Electrical_Pulse_Duration_ms",
            "pulse_duration_ms",
            "Pulse_Duration_ms",
        ],
    );
    set(
        &mut row,
        "Trial_Start_S",
        format!("{:.9}", span.start as f64 / f64::from(rate)),
    );
    set(&mut row, "Trial_Start_Sample", span.start);
    set(
        &mut row,
        "Looming_Onset_S",
        if has_audio {
            format!("{looming:.9}")
        } else {
            String::new()
        },
    );
    set(
        &mut row,
        "Looming_Onset_Sample",
        if has_audio {
            sample_at(span.start, looming, rate).to_string()
        } else {
            String::new()
        },
    );
    set(
        &mut row,
        "Tactile_Onset_S",
        if has_tactile {
            format!("{tactile:.9}")
        } else {
            String::new()
        },
    );
    set(
        &mut row,
        "Tactile_Onset_Sample",
        if has_tactile {
            sample_at(span.start, tactile, rate).to_string()
        } else {
            String::new()
        },
    );
    set(
        &mut row,
        "Tactile_Drive_Onset_S",
        if has_tactile {
            format!("{drive:.9}")
        } else {
            String::new()
        },
    );
    set(
        &mut row,
        "Tactile_Drive_Onset_Sample",
        if has_tactile {
            sample_at(span.start, drive, rate).to_string()
        } else {
            String::new()
        },
    );
    let requested = (tactile - (tactile - compensation_ms() / 1000.0).max(0.0)).max(0.0) * 1000.0;
    let applied = span.tactile_shift_frames as f64 / f64::from(rate) * 1000.0;
    set(
        &mut row,
        "Tactile_Latency_Compensation_Requested_ms",
        if has_tactile {
            format!("{requested:.3}")
        } else {
            String::new()
        },
    );
    set(
        &mut row,
        "Tactile_Latency_Compensation_Applied_ms",
        if has_tactile {
            format!("{applied:.3}")
        } else {
            String::new()
        },
    );
    set(
        &mut row,
        "Tactile_Latency_Compensation_Status",
        if has_tactile { TACTILE_STATUS } else { "" },
    );
    set(
        &mut row,
        "Tactile_Latency_Compensation_Applied",
        if has_tactile {
            if span.tactile_shift_frames > 0 {
                "True"
            } else {
                "False"
            }
        } else {
            ""
        },
    );
    set(
        &mut row,
        "Tactile_Waveform_Generated",
        if has_tactile {
            if waveform.is_some() {
                "true"
            } else {
                "false"
            }
        } else {
            ""
        },
    );
    set(
        &mut row,
        "Tactile_Latency_Compensation_Note",
        if has_tactile {
            span.tactile_compensation_note
        } else {
            ""
        },
    );
    set(
        &mut row,
        "Response_Window_Onset_S",
        format!("{response:.9}"),
    );
    set(
        &mut row,
        "Response_Window_Onset_Sample",
        sample_at(span.start, response, rate),
    );
    set(
        &mut row,
        "Trial_End_S",
        format!("{:.9}", span.end as f64 / f64::from(rate)),
    );
    set(&mut row, "Trial_End_Sample", span.end);
    set_alias(
        &mut row,
        source,
        "Segment5_Block_Trial_Index",
        &["block_trial_index"],
    );
    set_alias(
        &mut row,
        source,
        "Segment4_Trial_Pool_Index",
        &["trial_pool_index"],
    );
    Ok(row)
}

fn write_sync(path: &Path, bytes: &[u8]) -> Result<(), ProfilePackageError> {
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .map_err(|_| package_error("profile_package_output_failed"))?;
    file.write_all(bytes)
        .and_then(|()| file.sync_all())
        .map_err(|_| package_error("profile_package_output_failed"))
}

fn prepared_csv(
    plan: &ProfileParticipantPlan,
    block: &ProfileBlockSource,
    assembled: &AssembledBlockWav,
    ordinal: usize,
    session_id: &str,
) -> Result<Vec<u8>, ProfilePackageError> {
    let mut rows = Vec::with_capacity(block.trials().len());
    let mut columns = BTreeSet::new();
    for (index, span) in assembled.spans().iter().enumerate() {
        let row = prepared_row(
            plan,
            block,
            span,
            ordinal,
            index + 1,
            session_id,
            assembled.sample_rate_hz(),
        )?;
        columns.extend(row.keys().cloned());
        rows.push(row);
    }
    if rows.len() != block.trials().len() || columns.len() > MAX_CSV_COLUMNS {
        return Err(package_error("profile_package_limit"));
    }
    let headers: Vec<_> = columns.into_iter().collect();
    let mut writer = WriterBuilder::new().from_writer(Vec::new());
    writer
        .write_record(&headers)
        .map_err(|_| package_error("profile_package_csv_failed"))?;
    for row in rows {
        let fields: Vec<_> = headers
            .iter()
            .map(|header| row.get(header).map(String::as_str).unwrap_or(""))
            .collect();
        if fields.iter().any(|value| value.len() > MAX_CSV_FIELD_BYTES) {
            return Err(package_error("profile_package_limit"));
        }
        writer
            .write_record(fields)
            .map_err(|_| package_error("profile_package_csv_failed"))?;
    }
    let bytes = writer
        .into_inner()
        .map_err(|_| package_error("profile_package_csv_failed"))?;
    if bytes.len() > MAX_PREPARED_BLOCK_MANIFEST_BYTES {
        return Err(package_error("profile_package_limit"));
    }
    Ok(bytes)
}

fn verify_and_compile(
    manifest: &Path,
    plan: &ProfileParticipantPlan,
    assembled: &[AssembledBlockWav],
) -> Result<VerifiedPreparedSession, ProfilePackageError> {
    let receipt = verify_prepared_session(
        VerificationRequest::new(manifest)
            .with_run_setup(plan.run_setup_path())
            .with_participant_id(plan.participant_id()),
    )
    .map_err(|error| package_error(error.code()))?;
    if receipt.blocks().len() != assembled.len() {
        return Err(package_error("profile_package_plan_invalid"));
    }
    for (index, (block, media)) in receipt.blocks().iter().zip(assembled).enumerate() {
        if block.block_wav().sha256() != media.sha256()
            || block.block_wav().encoded_byte_count() != media.bytes()
        {
            return Err(package_error("profile_package_media_changed"));
        }
        let summary = &receipt.summary().blocks[index];
        let mut options = BlockScheduleOptions::new(summary.index);
        options.block_label = summary.label.clone();
        options.block_wav_path = Some(block.wav_path().to_path_buf());
        options.participant_id = receipt.summary().participant_id.clone();
        options.session_id = receipt.summary().session_id.clone();
        options.part_number = receipt
            .summary()
            .part_number
            .map(Value::from)
            .unwrap_or(Value::Null);
        options.sample_rate = i64::from(media.sample_rate_hz());
        options.block_metadata = block.metadata().clone();
        let schedule = compile_verified_block_schedule(
            block.manifest_path(),
            block.manifest_sha256(),
            options,
        )
        .map_err(|error| package_error(error.code()))?;
        if schedule
            .events()
            .iter()
            .any(|event| event.sample_index < 0 || event.sample_index as u64 > media.frames())
        {
            return Err(package_error("profile_package_schedule_outside_media"));
        }
    }
    Ok(receipt)
}

/// Link staged files into a new output directory; dropping the returned guard
/// removes a failed publication, including any already linked files.
fn publish_staged_package(
    stage_blocks: &Path,
    stage_manifest: &Path,
    output_dir: &Path,
    block_count: usize,
) -> Result<PublishedDirectory, ProfilePackageError> {
    fs::create_dir(output_dir).map_err(|error| {
        if error.kind() == std::io::ErrorKind::AlreadyExists {
            package_error("profile_package_output_exists")
        } else {
            package_error("profile_package_output_failed")
        }
    })?;
    let mut published = PublishedDirectory::new(output_dir.to_path_buf());
    let final_blocks = output_dir.join("blocks");
    fs::create_dir(&final_blocks).map_err(|_| package_error("profile_package_output_failed"))?;
    for ordinal in 1..=block_count {
        for extension in ["wav", "csv"] {
            let name = format!("Block_{ordinal:02}.{extension}");
            published.link(&stage_blocks.join(&name), final_blocks.join(&name))?;
        }
    }
    published.link(
        stage_manifest,
        output_dir.join(".session_manifest.pending.json"),
    )?;
    Ok(published)
}

/// Materialize all blocks of one single-phase participant profile and return
/// Runner's existing native V1 verification receipt. No existing path is overwritten.
pub fn prepare_standard_profile_package(
    profile: &VerifiedExperimentProfile,
    participant_id: &str,
    requested_dir: &Path,
    generation: u64,
) -> Result<VerifiedPreparedSession, ProfilePackageError> {
    let plan = select_profile_participant(profile, participant_id)
        .map_err(|error| package_error(error.code()))?;
    let parent = requested_dir
        .parent()
        .ok_or(package_error("profile_package_path_unsupported"))?;
    let parent =
        fs::canonicalize(parent).map_err(|_| package_error("profile_package_output_failed"))?;
    let session_id = requested_dir
        .file_name()
        .and_then(|name| name.to_str())
        .filter(|name| {
            !name.is_empty()
                && name.len() <= 128
                && name.chars().all(|character| {
                    character.is_ascii_alphanumeric() || matches!(character, '_' | '-')
                })
        })
        .ok_or(package_error("profile_package_path_unsupported"))?;
    if !session_id.starts_with(plan.participant_id()) {
        return Err(package_error("profile_package_identity_invalid"));
    }
    let output_dir = parent.join(session_id);
    if output_dir.exists() {
        return Err(package_error("profile_package_output_exists"));
    }
    let selected_phase = phase(
        plan.blocks()
            .first()
            .ok_or(package_error("profile_package_plan_invalid"))?,
    )?;
    if plan
        .blocks()
        .iter()
        .any(|block| phase(block).ok() != Some(selected_phase))
    {
        return Err(package_error("profile_package_phase_unsupported"));
    }
    let part_number = if selected_phase == "post" { 2 } else { 1 };
    let mut pending = None;
    for _ in 0..16 {
        let candidate = parent.join(format!(
            ".{session_id}.pending.{}.{}",
            std::process::id(),
            PACKAGE_SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ));
        match fs::create_dir(&candidate) {
            Ok(()) => {
                pending = Some(PendingDirectory(candidate));
                break;
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(_) => return Err(package_error("profile_package_output_failed")),
        }
    }
    let pending = pending.ok_or(package_error("profile_package_output_failed"))?;
    let stage_blocks = pending.0.join("blocks");
    fs::create_dir(&stage_blocks).map_err(|_| package_error("profile_package_output_failed"))?;
    let mut blocks = Vec::with_capacity(plan.blocks().len());
    let mut assembled = Vec::with_capacity(plan.blocks().len());
    let mut total_wav_bytes = 0_u64;
    for (index, block) in plan.blocks().iter().enumerate() {
        let ordinal = index + 1;
        let stem = format!("Block_{ordinal:02}");
        let wav_name = format!("{stem}.wav");
        let csv_name = format!("{stem}.csv");
        let media = assemble_standard_profile_block(
            &plan,
            ordinal,
            &stage_blocks.join(&wav_name),
            generation,
        )
        .map_err(|error| package_error(error.code()))?;
        total_wav_bytes = total_wav_bytes
            .checked_add(media.bytes())
            .filter(|bytes| *bytes <= MAX_TOTAL_PREPARED_BLOCK_WAV_BYTES)
            .ok_or(package_error("profile_package_limit"))?;
        let csv = prepared_csv(&plan, block, &media, ordinal, session_id)?;
        write_sync(&stage_blocks.join(&csv_name), &csv)?;
        let label = field(block.order_fields(), &["block_label"]);
        let label = if label.is_empty() {
            format!("Block {ordinal:02}")
        } else {
            label.to_owned()
        };
        blocks.push(json!({
            "index": ordinal, "label": label, "manifest_path": format!("blocks/{csv_name}"),
            "wav_path": format!("blocks/{wav_name}"), "trial_count": block.trials().len(),
            "duration_s": media.frames() as f64 / f64::from(media.sample_rate_hz()),
            "metadata": {
                "execution_mode": PARTICIPANT_BLOCK_WAVS_MODE,
                "phase": selected_phase,
                "phase_label": display_phase(selected_phase),
                "part_number": part_number,
                "source_block_csv_path": path_text(block.source_csv_path())?,
                "source_block_csv_sha256": block.source_csv_sha256(),
                "sample_rate_hz": media.sample_rate_hz(),
                "channels": media.channels(),
            }
        }));
        assembled.push(media);
    }
    select_profile_participant(profile, participant_id)
        .map_err(|error| package_error(error.code()))?;
    let stage_manifest = pending.0.join("session_manifest.json");
    let manifest = json!({
        "schema": RUN_PACKAGE_SCHEMA,
        "participant_id": plan.participant_id(),
        "session_id": session_id,
        "part_number": part_number,
        "part_session_id": session_id,
        "execution_mode": PARTICIPANT_BLOCK_WAVS_MODE,
        "source_run_setup_manifest_path": path_text(plan.run_setup_path())?,
        "source_run_setup_sha256": plan.run_setup_sha256(),
        "blocks": blocks,
    });
    let manifest_bytes = serde_json::to_vec_pretty(&manifest)
        .map_err(|_| package_error("profile_package_manifest_failed"))?;
    write_sync(&stage_manifest, &manifest_bytes)?;
    let _ = verify_and_compile(&stage_manifest, &plan, &assembled)?;
    let mut published = publish_staged_package(
        &stage_blocks,
        &stage_manifest,
        &output_dir,
        plan.blocks().len(),
    )?;
    let pending_manifest = output_dir.join(".session_manifest.pending.json");
    let _ = verify_and_compile(&pending_manifest, &plan, &assembled)?;
    let final_manifest = output_dir.join("session_manifest.json");
    published.link(&pending_manifest, final_manifest.clone())?;
    fs::remove_file(&pending_manifest)
        .map_err(|_| package_error("profile_package_output_failed"))?;
    let receipt = verify_and_compile(&final_manifest, &plan, &assembled)?;
    published.retain();
    Ok(receipt)
}

#[cfg(test)]
mod tests {
    use std::{fs, time::SystemTime};

    use super::{publish_staged_package, six_significant, PendingDirectory};

    #[test]
    fn prepared_tactile_numbers_use_six_significant_digits() {
        assert_eq!(six_significant(0.2), "0.2");
        assert_eq!(six_significant(100_000.0), "100000");
        assert_eq!(six_significant(1_000_000.0), "1e+06");
        assert_eq!(six_significant(0.00001), "1e-05");
    }

    #[test]
    fn failed_package_publication_cleans_partial_directory_without_overwriting() {
        let nonce = SystemTime::now()
            .duration_since(SystemTime::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "pps-package-publication-test-{}-{nonce}",
            std::process::id()
        ));
        fs::create_dir(&root).unwrap();
        let cleanup = PendingDirectory(root.clone());
        let stage_blocks = root.join("stage-blocks");
        fs::create_dir(&stage_blocks).unwrap();
        fs::write(stage_blocks.join("Block_01.wav"), b"wav").unwrap();
        let stage_manifest = root.join("staged-manifest.json");
        fs::write(&stage_manifest, b"manifest").unwrap();
        let output = root.join("P001_session");

        let failed = publish_staged_package(&stage_blocks, &stage_manifest, &output, 1);
        assert!(failed.is_err());
        assert_eq!(
            failed.err().unwrap().code(),
            "profile_package_output_failed"
        );
        assert!(!output.exists());

        fs::write(stage_blocks.join("Block_01.csv"), b"csv").unwrap();
        let published = publish_staged_package(&stage_blocks, &stage_manifest, &output, 1).unwrap();
        assert!(output.join("blocks/Block_01.csv").exists());
        let unrelated = output.join("unrelated.txt");
        fs::write(&unrelated, b"preserve").unwrap();
        drop(published);
        assert_eq!(fs::read(&unrelated).unwrap(), b"preserve");
        assert!(!output.join("blocks/Block_01.csv").exists());
        fs::remove_file(unrelated).unwrap();
        fs::remove_dir(&output).unwrap();

        let mut published =
            publish_staged_package(&stage_blocks, &stage_manifest, &output, 1).unwrap();
        published.retain();
        drop(published);
        assert!(output.join(".session_manifest.pending.json").exists());
        let exists = publish_staged_package(&stage_blocks, &stage_manifest, &output, 1);
        assert_eq!(
            exists.err().unwrap().code(),
            "profile_package_output_exists"
        );
        assert!(output.join("blocks/Block_01.wav").exists());
        drop(cleanup);
    }
}
