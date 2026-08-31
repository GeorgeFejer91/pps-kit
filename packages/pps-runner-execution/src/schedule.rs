use std::{
    cmp::Ordering,
    fs::File,
    io::{self, Read},
    path::{Path, PathBuf},
    sync::Arc,
};

use csv::StringRecord;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};

use crate::{encoded::encoded_len, ExecutionError, ExecutionErrorCode, JSON_MAX_SAFE_INTEGER};

pub const MAX_BLOCK_MANIFEST_BYTES: usize = 8 * 1024 * 1024;
pub const MAX_BLOCK_ROWS: usize = 100_000;
pub const MAX_SCHEDULE_EVENTS: usize = 500_001;
pub const MAX_BLOCK_METADATA_FIELDS: usize = 256;
pub const MAX_BLOCK_METADATA_BYTES: usize = 64 * 1024;
pub const MAX_SCHEDULE_ENCODED_BYTES: usize = 32 * 1024 * 1024;
pub const MAX_NATIVE_PATH_PAYLOAD_BYTES: usize = 32 * 1024;

const MAX_CSV_COLUMNS: usize = 256;
const MAX_CSV_FIELD_BYTES: usize = 16 * 1024;
const MAX_IDENTITY_BYTES: usize = 512;
const MAX_BLOCK_LABEL_BYTES: usize = 1024;
const MAX_SAMPLE_RATE_HZ: i64 = 1_000_000;
const MAX_INITIAL_EVENT_CAPACITY: usize = 4_096;

/// Native inputs used to compile one V1 block manifest.
///
/// `part_number` is a JSON scalar because the Python V1 runner preserves the
/// caller's integer-or-string representation in event payloads. Metadata is
/// projected with the V1 `block_` prefix; only scalar values are retained.
#[derive(Debug, Clone)]
pub struct BlockScheduleOptions {
    pub block_index: i64,
    pub block_label: String,
    pub block_wav_path: Option<PathBuf>,
    pub participant_id: String,
    pub session_id: String,
    pub part_number: Value,
    pub sample_rate: i64,
    pub block_metadata: Map<String, Value>,
    pub trial_duration_s: f64,
    pub stimulus_segment_onset_s: f64,
}

impl BlockScheduleOptions {
    pub fn new(block_index: i64) -> Self {
        Self {
            block_index,
            ..Self::default()
        }
    }
}

impl Default for BlockScheduleOptions {
    fn default() -> Self {
        Self {
            block_index: 0,
            block_label: String::new(),
            block_wav_path: None,
            participant_id: String::new(),
            session_id: String::new(),
            part_number: Value::String(String::new()),
            sample_rate: 0,
            block_metadata: Map::new(),
            trial_duration_s: 8.0,
            stimulus_segment_onset_s: 4.0,
        }
    }
}

/// One deterministic event in block-audio sample coordinates.
///
/// The payload intentionally preserves the V1 Python fields, including native
/// manifest/WAV path strings. Use [`BlockEventSchedule::summary`] for a
/// path-free browser projection; do not expose raw events to an untrusted UI.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ScheduledBlockEvent {
    pub event_type: String,
    pub sample_index: i64,
    pub trigger_key: String,
    pub payload: Value,
}

/// Browser-safe, path-free facts about one compiled schedule.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BlockScheduleSummary {
    pub block_index: i64,
    pub block_label: String,
    pub sample_rate_hz: i64,
    pub trial_row_count: u32,
    pub event_count: u32,
    pub encoded_bytes: u32,
    pub first_sample_index: Option<i64>,
    pub last_sample_index: Option<i64>,
    pub negative_sample_event_count: u32,
}

/// Cumulative-byte-bounded sorted schedule plus a forward-only, half-open
/// buffer cursor.
#[derive(Debug, Clone)]
pub struct BlockEventSchedule {
    events: Vec<ScheduledBlockEvent>,
    cursor: usize,
    summary: BlockScheduleSummary,
}

impl BlockEventSchedule {
    /// Construct a synthetic schedule with no block identity.
    ///
    /// This is primarily useful to test scheduler boundaries. Production V1
    /// manifests should use [`compile_block_schedule`].
    pub fn new(events: Vec<ScheduledBlockEvent>) -> Result<Self, ExecutionError> {
        Self::from_parts(events, 0, String::new(), 0, 0)
    }

    fn from_parts(
        events: Vec<ScheduledBlockEvent>,
        block_index: i64,
        block_label: String,
        sample_rate_hz: i64,
        trial_row_count: usize,
    ) -> Result<Self, ExecutionError> {
        Self::from_parts_with_budget(
            events,
            block_index,
            block_label,
            sample_rate_hz,
            trial_row_count,
            MAX_SCHEDULE_ENCODED_BYTES,
        )
    }

    fn from_parts_with_budget(
        mut events: Vec<ScheduledBlockEvent>,
        block_index: i64,
        block_label: String,
        sample_rate_hz: i64,
        trial_row_count: usize,
        maximum_encoded_bytes: usize,
    ) -> Result<Self, ExecutionError> {
        if events.len() > MAX_SCHEDULE_EVENTS {
            return Err(error(
                ExecutionErrorCode::TooManyEvents,
                "The block schedule contains too many events.",
                format!(
                    "schedule has {} events; the limit is {MAX_SCHEDULE_EVENTS}",
                    events.len()
                ),
            ));
        }
        if let Some(event) = events.iter().find(|event| {
            !(-JSON_MAX_SAFE_INTEGER..=JSON_MAX_SAFE_INTEGER).contains(&event.sample_index)
        }) {
            return Err(error(
                ExecutionErrorCode::SampleIndexOutOfRange,
                "A block event has an unsupported sample index.",
                format!(
                    "event `{}` has sample index {} outside the exact JSON integer range",
                    event.trigger_key, event.sample_index
                ),
            ));
        }
        let mut encoded_bytes = 0_usize;
        for event in &events {
            add_event_bytes(&mut encoded_bytes, event, maximum_encoded_bytes)?;
        }
        events.sort_by(compare_events);
        let first_sample_index = events.first().map(|event| event.sample_index);
        let last_sample_index = events.last().map(|event| event.sample_index);
        let negative_sample_event_count =
            events.iter().filter(|event| event.sample_index < 0).count();
        let summary = BlockScheduleSummary {
            block_index,
            block_label,
            sample_rate_hz,
            trial_row_count: checked_u32(trial_row_count, "trial row count")?,
            event_count: checked_u32(events.len(), "event count")?,
            encoded_bytes: checked_u32(encoded_bytes, "encoded schedule byte count")?,
            first_sample_index,
            last_sample_index,
            negative_sample_event_count: checked_u32(
                negative_sample_event_count,
                "negative event count",
            )?,
        };
        Ok(Self {
            events,
            cursor: 0,
            summary,
        })
    }

    pub fn events(&self) -> &[ScheduledBlockEvent] {
        &self.events
    }

    pub fn summary(&self) -> &BlockScheduleSummary {
        &self.summary
    }

    pub const fn cursor(&self) -> usize {
        self.cursor
    }

    pub fn reset(&mut self) {
        self.cursor = 0;
    }

    /// Return the next events in `[buffer_start_sample, start + frame_count)`.
    ///
    /// As in the V1 Python runner, a non-positive frame count returns nothing,
    /// negative starts clamp to zero, and events skipped behind the caller's
    /// start are consumed. The returned slice borrows the schedule and performs
    /// no payload allocation on the scheduler path.
    pub fn consume_buffer(
        &mut self,
        buffer_start_sample: i64,
        frame_count: i64,
    ) -> &[ScheduledBlockEvent] {
        if frame_count <= 0 || self.cursor >= self.events.len() {
            return &self.events[self.cursor..self.cursor];
        }
        let buffer_start_sample = buffer_start_sample.max(0);
        let buffer_end_sample = buffer_start_sample.saturating_add(frame_count);
        while self.cursor < self.events.len()
            && self.events[self.cursor].sample_index < buffer_start_sample
        {
            self.cursor += 1;
        }
        let due_start = self.cursor;
        while self.cursor < self.events.len()
            && self.events[self.cursor].sample_index < buffer_end_sample
        {
            self.cursor += 1;
        }
        &self.events[due_start..self.cursor]
    }
}

/// Compile a verified V1 block CSV into deterministic sample-indexed events.
///
/// This function performs bounded, read-only manifest input. It never writes a
/// file and owns no platform runtime. The Python V1 behavior is preserved for
/// event selection, aliases, payloads, stable ordering, explicit-invalid sample
/// suppression, UTF-8 BOM input, and ties-to-even seconds conversion. Signed
/// default sample indices are retained; this matters for extreme negative SOAs
/// and mirrors Python instead of silently coercing them to unsigned values.
pub fn compile_block_schedule(
    manifest_path: &Path,
    options: BlockScheduleOptions,
) -> Result<BlockEventSchedule, ExecutionError> {
    let bytes = read_manifest_bytes(manifest_path)?;
    compile_block_schedule_from_bytes(manifest_path, &bytes, options)
}

/// Compile only when the exact bounded CSV bytes still match a native
/// selection receipt.
///
/// The file is opened and read once. Its digest is computed over the owned
/// bounded byte snapshot, and the CSV parser consumes that same snapshot only
/// after the identity comparison succeeds. This closes replacement and
/// in-place-mutation gaps between package reverification and schedule parsing.
pub fn compile_verified_block_schedule(
    manifest_path: &Path,
    expected_sha256: &str,
    options: BlockScheduleOptions,
) -> Result<BlockEventSchedule, ExecutionError> {
    let bytes = read_manifest_bytes(manifest_path)?;
    let observed_sha256 = format!("{:x}", Sha256::digest(&bytes));
    if observed_sha256 != expected_sha256 {
        return Err(error(
            ExecutionErrorCode::ManifestIdentityMismatch,
            "The block manifest changed after package selection.",
            format!(
                "block manifest `{}` no longer matches its selected SHA-256 identity",
                manifest_path.display()
            ),
        ));
    }
    compile_block_schedule_from_bytes(manifest_path, &bytes, options)
}

fn compile_block_schedule_from_bytes(
    manifest_path: &Path,
    manifest_bytes: &[u8],
    options: BlockScheduleOptions,
) -> Result<BlockEventSchedule, ExecutionError> {
    validate_options(&options)?;
    let manifest_path_text = path_text(manifest_path, "manifest")?;
    let block_wav_path_text = options
        .block_wav_path
        .as_deref()
        .map(|path| path_text(path, "block WAV"))
        .transpose()?
        .unwrap_or_default();
    let projected_metadata = project_block_metadata(&options.block_metadata)?;
    let rows = parse_rows(manifest_path, manifest_bytes)?;
    if rows.len() > MAX_BLOCK_ROWS {
        return Err(error(
            ExecutionErrorCode::TooManyRows,
            "The block manifest contains too many trial rows.",
            format!(
                "block manifest `{}` has {} rows; the limit is {MAX_BLOCK_ROWS}",
                manifest_path.display(),
                rows.len()
            ),
        ));
    }
    let maximum_events = rows
        .len()
        .checked_mul(5)
        .and_then(|count| count.checked_add(1))
        .ok_or_else(|| {
            error(
                ExecutionErrorCode::TooManyEvents,
                "The block schedule contains too many events.",
                "schedule event count overflowed usize",
            )
        })?;
    if maximum_events > MAX_SCHEDULE_EVENTS {
        return Err(error(
            ExecutionErrorCode::TooManyEvents,
            "The block schedule contains too many events.",
            format!(
                "block manifest could generate {maximum_events} events; the limit is {MAX_SCHEDULE_EVENTS}"
            ),
        ));
    }

    let inferred_sample_rate = infer_sample_rate(&rows, options.sample_rate)?;
    let mut events = Vec::with_capacity(maximum_events.min(MAX_INITIAL_EVENT_CAPACITY));
    let mut encoded_bytes = 0_usize;
    push_bounded_event(
        &mut events,
        &mut encoded_bytes,
        ScheduledBlockEvent {
            event_type: "audio_sample_zero".to_owned(),
            sample_index: 0,
            trigger_key: "control:audio_sample_zero".to_owned(),
            payload: Value::Object(audio_zero_payload(
                &options,
                &block_wav_path_text,
                &manifest_path_text,
                &projected_metadata,
            )),
        },
    )?;

    for (fallback_offset, row) in rows.iter().enumerate() {
        let fallback_index = i64::try_from(fallback_offset + 1).map_err(|_| {
            error(
                ExecutionErrorCode::TooManyRows,
                "The block manifest contains too many trial rows.",
                "trial fallback index did not fit i64",
            )
        })?;
        compile_trial_events(
            &mut events,
            row,
            fallback_index,
            inferred_sample_rate,
            &options,
            &block_wav_path_text,
            &manifest_path_text,
            &projected_metadata,
            &mut encoded_bytes,
        )?;
    }

    BlockEventSchedule::from_parts(
        events,
        options.block_index,
        options.block_label,
        inferred_sample_rate,
        rows.len(),
    )
}

#[derive(Debug, Clone)]
struct CsvColumn {
    name: String,
    value_index: usize,
}

#[derive(Debug, Clone)]
struct CsvRow {
    columns: Arc<[CsvColumn]>,
    record: StringRecord,
}

struct EventSpecification<'a> {
    event_type: &'a str,
    sample_keys: &'a [&'a str],
    second_keys: &'a [&'a str],
    default_sample: Option<i64>,
}

impl CsvRow {
    fn value(&self, keys: &[&str], default: &str) -> String {
        for key in keys {
            if let Some(value) = self
                .columns
                .iter()
                .find(|column| column.name == *key)
                .and_then(|column| self.record.get(column.value_index))
            {
                if !value.is_empty() {
                    return value.to_owned();
                }
            }
        }
        default.to_owned()
    }
}

fn read_manifest_bytes(path: &Path) -> Result<Vec<u8>, ExecutionError> {
    let file = File::open(path).map_err(|cause| {
        let code = if cause.kind() == io::ErrorKind::NotFound {
            ExecutionErrorCode::ManifestMissing
        } else {
            ExecutionErrorCode::ManifestUnreadable
        };
        error(
            code,
            "The block manifest could not be read safely.",
            format!(
                "could not open block manifest `{}`: {cause}",
                path.display()
            ),
        )
    })?;
    if let Ok(metadata) = file.metadata() {
        if metadata.len() > MAX_BLOCK_MANIFEST_BYTES as u64 {
            return Err(error(
                ExecutionErrorCode::ManifestTooLarge,
                "The block manifest is too large.",
                format!(
                    "block manifest `{}` has {} bytes; the limit is {MAX_BLOCK_MANIFEST_BYTES}",
                    path.display(),
                    metadata.len()
                ),
            ));
        }
    }
    let read_limit = u64::try_from(MAX_BLOCK_MANIFEST_BYTES)
        .expect("manifest byte limit fits u64")
        .saturating_add(1);
    let mut bytes = Vec::new();
    file.take(read_limit)
        .read_to_end(&mut bytes)
        .map_err(|cause| {
            error(
                ExecutionErrorCode::ManifestUnreadable,
                "The block manifest could not be read safely.",
                format!(
                    "could not read block manifest `{}`: {cause}",
                    path.display()
                ),
            )
        })?;
    if bytes.len() > MAX_BLOCK_MANIFEST_BYTES {
        return Err(error(
            ExecutionErrorCode::ManifestTooLarge,
            "The block manifest is too large.",
            format!(
                "block manifest `{}` exceeded the {MAX_BLOCK_MANIFEST_BYTES}-byte limit",
                path.display()
            ),
        ));
    }
    Ok(bytes)
}

fn parse_rows(path: &Path, bytes: &[u8]) -> Result<Vec<CsvRow>, ExecutionError> {
    let csv_bytes = bytes.strip_prefix(&[0xef, 0xbb, 0xbf]).unwrap_or(bytes);
    let mut reader = csv::ReaderBuilder::new()
        .flexible(false)
        .from_reader(csv_bytes);
    let headers = reader
        .headers()
        .map_err(|cause| csv_error(path, cause))?
        .clone();
    if headers.len() > MAX_CSV_COLUMNS {
        return Err(error(
            ExecutionErrorCode::TooManyColumns,
            "The block manifest contains too many columns.",
            format!(
                "block manifest `{}` has {} columns; the limit is {MAX_CSV_COLUMNS}",
                path.display(),
                headers.len()
            ),
        ));
    }
    validate_csv_fields(path, headers.iter())?;
    let mut columns = Vec::<CsvColumn>::with_capacity(headers.len());
    for (value_index, header) in headers.iter().enumerate() {
        if let Some(column) = columns.iter_mut().find(|column| column.name == header) {
            column.value_index = value_index;
        } else {
            columns.push(CsvColumn {
                name: header.to_owned(),
                value_index,
            });
        }
    }
    let columns: Arc<[CsvColumn]> = columns.into();

    let mut rows = Vec::new();
    for record in reader.records() {
        if rows.len() >= MAX_BLOCK_ROWS {
            return Err(error(
                ExecutionErrorCode::TooManyRows,
                "The block manifest contains too many trial rows.",
                format!(
                    "block manifest `{}` exceeded the {MAX_BLOCK_ROWS}-row limit",
                    path.display()
                ),
            ));
        }
        let record = record.map_err(|cause| csv_error(path, cause))?;
        validate_csv_fields(path, record.iter())?;
        rows.push(CsvRow {
            columns: Arc::clone(&columns),
            record,
        });
    }
    Ok(rows)
}

fn validate_csv_fields<'a>(
    path: &Path,
    values: impl Iterator<Item = &'a str>,
) -> Result<(), ExecutionError> {
    if let Some(value) = values
        .into_iter()
        .find(|value| value.len() > MAX_CSV_FIELD_BYTES)
    {
        return Err(error(
            ExecutionErrorCode::CsvInvalid,
            "The block manifest contains an oversized CSV field.",
            format!(
                "block manifest `{}` contains a {}-byte field; the limit is {MAX_CSV_FIELD_BYTES}",
                path.display(),
                value.len()
            ),
        ));
    }
    Ok(())
}

fn csv_error(path: &Path, cause: csv::Error) -> ExecutionError {
    error(
        ExecutionErrorCode::CsvInvalid,
        "The block manifest is not valid CSV.",
        format!(
            "could not parse block manifest `{}`: {cause}",
            path.display()
        ),
    )
}

#[allow(clippy::too_many_arguments)]
fn compile_trial_events(
    events: &mut Vec<ScheduledBlockEvent>,
    row: &CsvRow,
    fallback_index: i64,
    sample_rate: i64,
    options: &BlockScheduleOptions,
    block_wav_path: &str,
    manifest_path: &str,
    projected_metadata: &Map<String, Value>,
    encoded_bytes: &mut usize,
) -> Result<(), ExecutionError> {
    let trial_number = as_i64(
        &row.value(&["Trial_Number", "trial_number"], ""),
        fallback_index,
        "trial number",
    )?;
    let default_trial_uid = format!("B{:02}_T{:03}", options.block_index, trial_number);
    let trial_uid = row.value(&["Trial_UID", "trial_uid"], &default_trial_uid);
    let trial_type = row
        .value(&["Trial_Type", "trial_type"], "")
        .trim()
        .to_owned();
    let family = row.value(&["Family", "family"], "").trim().to_owned();
    let trial_kind = trial_kind(&trial_type, &family);
    let has_looming = matches!(trial_kind, "audio_tactile" | "catch" | "auditory_only");
    let has_tactile = matches!(trial_kind, "audio_tactile" | "baseline");
    let soa_ms = as_f64(&row.value(&["SOA_ms", "soa_ms"], "0"), 0.0);
    let trial_duration_s = options.trial_duration_s.max(0.0);
    let stimulus_segment_onset_s = options.stimulus_segment_onset_s.max(0.0);

    let trial_start_default = if sample_rate > 0 {
        let zero_based_trial = trial_number.checked_sub(1).ok_or_else(|| {
            sample_range_error("trial number underflowed while deriving the start sample")
        })?;
        Some(round_sample(
            (zero_based_trial as f64) * trial_duration_s * (sample_rate as f64),
            "default trial start",
        )?)
    } else {
        None
    };
    let trial_start_sample = sample_index(
        row,
        &["Trial_Start_Sample", "trial_start_sample"],
        &["Trial_Start_S", "trial_start_s"],
        sample_rate,
        trial_start_default,
    )?;
    let duration_samples = if sample_rate > 0 {
        Some(round_sample(
            trial_duration_s * (sample_rate as f64),
            "trial duration",
        )?)
    } else {
        None
    };
    let segment_samples = if sample_rate > 0 {
        Some(round_sample(
            stimulus_segment_onset_s * (sample_rate as f64),
            "stimulus segment onset",
        )?)
    } else {
        None
    };
    let trial_end_default = match (trial_start_sample, duration_samples) {
        (Some(start), Some(duration)) => Some(checked_sample_add(start, duration, "trial end")?),
        _ => None,
    };
    let looming_default = match (trial_start_sample, segment_samples, has_looming) {
        (Some(start), Some(segment), true) => {
            Some(checked_sample_add(start, segment, "looming onset")?)
        }
        _ => None,
    };
    let tactile_default =
        if let (Some(start), true, true) = (trial_start_sample, sample_rate > 0, has_tactile) {
            let relative = round_sample(
                (stimulus_segment_onset_s + (soa_ms / 1000.0)) * (sample_rate as f64),
                "tactile onset",
            )?;
            Some(checked_sample_add(start, relative, "tactile onset")?)
        } else {
            None
        };
    let response_default = if has_looming {
        looming_default
    } else {
        tactile_default
    };
    let common = trial_payload(
        row,
        options,
        block_wav_path,
        manifest_path,
        trial_number,
        &trial_uid,
        projected_metadata,
    );

    let specifications = [
        EventSpecification {
            event_type: "trial_start",
            sample_keys: &["Trial_Start_Sample", "trial_start_sample"],
            second_keys: &["Trial_Start_S", "trial_start_s"],
            default_sample: trial_start_sample,
        },
        EventSpecification {
            event_type: "looming_onset",
            sample_keys: &["Looming_Onset_Sample", "looming_onset_sample"],
            second_keys: &["Looming_Onset_S", "looming_onset_s"],
            default_sample: looming_default,
        },
        EventSpecification {
            event_type: "tactile_onset",
            sample_keys: &["Tactile_Onset_Sample", "tactile_onset_sample"],
            second_keys: &["Tactile_Onset_S", "tactile_onset_s"],
            default_sample: tactile_default,
        },
        EventSpecification {
            event_type: "response_window_onset",
            sample_keys: &[
                "Response_Window_Onset_Sample",
                "response_window_onset_sample",
            ],
            second_keys: &["Response_Window_Onset_S", "response_window_onset_s"],
            default_sample: response_default,
        },
        EventSpecification {
            event_type: "trial_end",
            sample_keys: &["Trial_End_Sample", "trial_end_sample"],
            second_keys: &["Trial_End_S", "trial_end_s"],
            default_sample: trial_end_default,
        },
    ];
    for specification in specifications {
        let EventSpecification {
            event_type,
            sample_keys,
            second_keys,
            default_sample,
        } = specification;
        if (event_type == "looming_onset" && !has_looming)
            || (event_type == "tactile_onset" && !has_tactile)
        {
            continue;
        }
        let Some(sample_index) =
            sample_index(row, sample_keys, second_keys, sample_rate, default_sample)?
        else {
            continue;
        };
        let mut payload = common.clone();
        payload.insert(
            "relative_time_s".to_owned(),
            if sample_rate > 0 {
                Value::from((sample_index as f64) / (sample_rate as f64))
            } else {
                Value::String(String::new())
            },
        );
        payload.insert("planned_sample_index".to_owned(), Value::from(sample_index));
        let common_trial_type =
            first_truthy_string(payload.get("Trial_Type"), payload.get("trial_type"));
        payload.insert(
            "stimulus_modality".to_owned(),
            Value::String(stimulus_modality(event_type, common_trial_type)),
        );
        push_bounded_event(
            events,
            encoded_bytes,
            ScheduledBlockEvent {
                event_type: event_type.to_owned(),
                sample_index,
                trigger_key: format!(
                    "trial:{:02}:{:03}:{}:{}",
                    options.block_index, trial_number, trial_uid, event_type
                ),
                payload: Value::Object(payload),
            },
        )?;
    }
    Ok(())
}

fn audio_zero_payload(
    options: &BlockScheduleOptions,
    block_wav_path: &str,
    manifest_path: &str,
    projected_metadata: &Map<String, Value>,
) -> Map<String, Value> {
    let mut payload = base_payload(options, block_wav_path, manifest_path);
    for (key, value) in projected_metadata {
        payload.insert(key.clone(), value.clone());
    }
    payload
}

fn base_payload(
    options: &BlockScheduleOptions,
    block_wav_path: &str,
    manifest_path: &str,
) -> Map<String, Value> {
    let mut payload = Map::new();
    payload.insert(
        "participant_id".to_owned(),
        Value::String(options.participant_id.clone()),
    );
    payload.insert(
        "session_id".to_owned(),
        Value::String(options.session_id.clone()),
    );
    payload.insert("part_number".to_owned(), options.part_number.clone());
    payload.insert("block_number".to_owned(), Value::from(options.block_index));
    payload.insert("block_index".to_owned(), Value::from(options.block_index));
    payload.insert(
        "block_label".to_owned(),
        Value::String(options.block_label.clone()),
    );
    payload.insert(
        "block_path".to_owned(),
        Value::String(block_wav_path.to_owned()),
    );
    payload.insert(
        "manifest_path".to_owned(),
        Value::String(manifest_path.to_owned()),
    );
    payload.insert(
        "scheduled_from".to_owned(),
        Value::String("block_event_schedule".to_owned()),
    );
    payload
}

#[allow(clippy::too_many_arguments)]
fn trial_payload(
    row: &CsvRow,
    options: &BlockScheduleOptions,
    block_wav_path: &str,
    manifest_path: &str,
    trial_number: i64,
    trial_uid: &str,
    projected_metadata: &Map<String, Value>,
) -> Map<String, Value> {
    let mut payload = base_payload(options, block_wav_path, manifest_path);
    payload.insert("trial_number".to_owned(), Value::from(trial_number));
    payload.insert("trial_index".to_owned(), Value::from(trial_number));
    payload.insert("trial_uid".to_owned(), Value::String(trial_uid.to_owned()));
    for (key, value) in projected_metadata {
        payload.insert(key.clone(), value.clone());
    }
    for column in row.columns.iter() {
        let value = row.record.get(column.value_index).unwrap_or_default();
        payload.insert(column.name.clone(), Value::String(value.to_owned()));
        let normalized = normalize_key(&column.name);
        if !normalized.is_empty() && !payload.contains_key(&normalized) {
            payload.insert(normalized, Value::String(value.to_owned()));
        }
    }
    set_default_from(&mut payload, "trial_type", "Trial_Type", "");
    set_default_from(&mut payload, "family", "Family", "");
    if !payload.contains_key("row_label") {
        let row_label = payload
            .get("Row_Label")
            .or_else(|| payload.get("Row"))
            .cloned()
            .unwrap_or_else(|| Value::String(String::new()));
        payload.insert("row_label".to_owned(), row_label);
    }
    set_default_from(&mut payload, "soa_ms", "SOA_ms", "");
    payload
}

fn set_default_from(payload: &mut Map<String, Value>, key: &str, source: &str, default: &str) {
    if payload.contains_key(key) {
        return;
    }
    let value = payload
        .get(source)
        .cloned()
        .unwrap_or_else(|| Value::String(default.to_owned()));
    payload.insert(key.to_owned(), value);
}

fn project_block_metadata(
    metadata: &Map<String, Value>,
) -> Result<Map<String, Value>, ExecutionError> {
    let mut projected = Map::new();
    let mut projected_encoded_bytes = 2_usize;
    for (key, value) in metadata {
        if key.is_empty() || !matches!(value, Value::String(_) | Value::Number(_) | Value::Bool(_))
        {
            continue;
        }
        if projected.len() >= MAX_BLOCK_METADATA_FIELDS {
            return Err(error(
                ExecutionErrorCode::InvalidScheduleOptions,
                "The block metadata contains too many scalar fields.",
                format!(
                    "block metadata exceeds the limit of {MAX_BLOCK_METADATA_FIELDS} scalar fields"
                ),
            ));
        }
        validate_scalar_number(value)?;
        let projected_key_bytes = "block_".len().checked_add(key.len()).ok_or_else(|| {
            invalid_options("block metadata key length overflowed the native byte range")
        })?;
        if projected_key_bytes > MAX_BLOCK_METADATA_BYTES {
            return Err(invalid_options("block metadata contains an oversized key"));
        }
        let projected_key = format!("block_{key}");
        let key_encoded_bytes = encoded_len(&projected_key).map_err(|cause| {
            invalid_options(format!(
                "could not measure projected block metadata key: {cause}"
            ))
        })?;
        let value_encoded_bytes = encoded_len(value).map_err(|cause| {
            invalid_options(format!(
                "could not measure projected block metadata value: {cause}"
            ))
        })?;
        let separator_bytes = if projected.is_empty() { 1 } else { 2 };
        projected_encoded_bytes = projected_encoded_bytes
            .checked_add(key_encoded_bytes)
            .and_then(|size| size.checked_add(value_encoded_bytes))
            .and_then(|size| size.checked_add(separator_bytes))
            .ok_or_else(|| invalid_options("block metadata byte count overflowed"))?;
        if projected_encoded_bytes > MAX_BLOCK_METADATA_BYTES {
            return Err(error(
                ExecutionErrorCode::InvalidScheduleOptions,
                "The block metadata is too large.",
                format!(
                    "projected block metadata exceeds the {MAX_BLOCK_METADATA_BYTES}-byte limit"
                ),
            ));
        }
        projected.insert(projected_key, value.clone());
    }
    let encoded_bytes = encoded_len(&projected).map_err(|cause| {
        error(
            ExecutionErrorCode::InvalidScheduleOptions,
            "The block metadata is not valid JSON data.",
            format!("could not measure projected block metadata: {cause}"),
        )
    })?;
    if encoded_bytes > MAX_BLOCK_METADATA_BYTES {
        return Err(error(
            ExecutionErrorCode::InvalidScheduleOptions,
            "The block metadata is too large.",
            format!(
                "projected block metadata has {encoded_bytes} bytes; the limit is {MAX_BLOCK_METADATA_BYTES}"
            ),
        ));
    }
    Ok(projected)
}

fn validate_options(options: &BlockScheduleOptions) -> Result<(), ExecutionError> {
    if !(-JSON_MAX_SAFE_INTEGER..=JSON_MAX_SAFE_INTEGER).contains(&options.block_index) {
        return Err(invalid_options(
            "block index is outside the exact JSON integer range",
        ));
    }
    if options.block_label.len() > MAX_BLOCK_LABEL_BYTES {
        return Err(invalid_options("block label is too long"));
    }
    for (label, value) in [
        ("participant ID", options.participant_id.as_str()),
        ("session ID", options.session_id.as_str()),
    ] {
        if value.len() > MAX_IDENTITY_BYTES || value.chars().any(char::is_control) {
            return Err(invalid_options(format!(
                "{label} is not a bounded printable string"
            )));
        }
    }
    match &options.part_number {
        Value::String(value) if value.len() <= 64 && !value.chars().any(char::is_control) => {}
        Value::Number(_) => validate_scalar_number(&options.part_number)?,
        _ => {
            return Err(invalid_options(
                "part number must be a bounded string or number",
            ))
        }
    }
    if options.sample_rate > MAX_SAMPLE_RATE_HZ {
        return Err(invalid_options(format!(
            "sample rate exceeds {MAX_SAMPLE_RATE_HZ} Hz"
        )));
    }
    if !options.trial_duration_s.is_finite() || !options.stimulus_segment_onset_s.is_finite() {
        return Err(invalid_options("schedule timing defaults must be finite"));
    }
    Ok(())
}

fn validate_scalar_number(value: &Value) -> Result<(), ExecutionError> {
    let Value::Number(number) = value else {
        return Ok(());
    };
    let exact = if let Some(value) = number.as_i64() {
        (-JSON_MAX_SAFE_INTEGER..=JSON_MAX_SAFE_INTEGER).contains(&value)
    } else if let Some(value) = number.as_u64() {
        value <= JSON_MAX_SAFE_INTEGER as u64
    } else {
        number
            .as_f64()
            .is_some_and(|value| value.is_finite() && value.abs() <= JSON_MAX_SAFE_INTEGER as f64)
    };
    if exact {
        Ok(())
    } else {
        Err(invalid_options(
            "numeric option is outside the exact JSON number range",
        ))
    }
}

fn infer_sample_rate(rows: &[CsvRow], fallback: i64) -> Result<i64, ExecutionError> {
    if fallback > 0 {
        return Ok(fallback);
    }
    for row in rows {
        let value = as_i64(
            &row.value(&["Sample_Rate_Hz", "sample_rate_hz"], ""),
            0,
            "sample rate",
        )?;
        if value > 0 {
            if value > MAX_SAMPLE_RATE_HZ {
                return Err(invalid_options(format!(
                    "inferred sample rate exceeds {MAX_SAMPLE_RATE_HZ} Hz"
                )));
            }
            return Ok(value);
        }
    }
    Ok(0)
}

fn sample_index(
    row: &CsvRow,
    sample_keys: &[&str],
    second_keys: &[&str],
    sample_rate: i64,
    default_sample: Option<i64>,
) -> Result<Option<i64>, ExecutionError> {
    let sample_value = row.value(sample_keys, "");
    if !sample_value.is_empty() {
        let sample = as_i64(&sample_value, -1, "explicit sample index")?;
        return Ok((sample >= 0).then_some(sample));
    }
    let seconds_value = row.value(second_keys, "");
    if seconds_value.is_empty() || sample_rate <= 0 {
        return Ok(default_sample);
    }
    let Some(seconds) = parse_finite_f64(&seconds_value) else {
        return Ok(None);
    };
    if seconds < 0.0 {
        return Ok(None);
    }
    Ok(Some(round_sample(
        seconds * (sample_rate as f64),
        "seconds-derived sample index",
    )?))
}

fn as_i64(value: &str, default: i64, context: &str) -> Result<i64, ExecutionError> {
    let Some(parsed) = parse_finite_f64(value) else {
        return Ok(default);
    };
    let truncated = parsed.trunc();
    if truncated < -(JSON_MAX_SAFE_INTEGER as f64) || truncated > JSON_MAX_SAFE_INTEGER as f64 {
        return Err(sample_range_error(format!(
            "{context} is outside the exact JSON integer range"
        )));
    }
    Ok(truncated as i64)
}

fn as_f64(value: &str, default: f64) -> f64 {
    parse_finite_f64(value).unwrap_or(default)
}

fn parse_finite_f64(value: &str) -> Option<f64> {
    value
        .trim()
        .parse::<f64>()
        .ok()
        .filter(|parsed| parsed.is_finite())
}

fn round_sample(value: f64, context: &str) -> Result<i64, ExecutionError> {
    if !value.is_finite() {
        return Err(sample_range_error(format!(
            "{context} produced a non-finite sample index"
        )));
    }
    let rounded = value.round_ties_even();
    if rounded < -(JSON_MAX_SAFE_INTEGER as f64) || rounded > JSON_MAX_SAFE_INTEGER as f64 {
        return Err(sample_range_error(format!(
            "{context} produced a sample index outside the exact JSON integer range"
        )));
    }
    Ok(rounded as i64)
}

fn checked_sample_add(left: i64, right: i64, context: &str) -> Result<i64, ExecutionError> {
    left.checked_add(right)
        .filter(|value| (-JSON_MAX_SAFE_INTEGER..=JSON_MAX_SAFE_INTEGER).contains(value))
        .ok_or_else(|| sample_range_error(format!("{context} sample index overflowed")))
}

fn trial_kind(trial_type: &str, family: &str) -> &'static str {
    for value in [trial_type, family] {
        let key = value.trim().to_lowercase().replace(['-', ' '], "_");
        match key.as_str() {
            "audio_tactile" | "audiotactile" => return "audio_tactile",
            "baseline" | "tactile_only" | "tactile_baseline" => return "baseline",
            "catch" | "catch_trial" | "audio_only" => return "catch",
            "auditory" | "auditory_only" | "auditory_only_trial" => return "auditory_only",
            _ => {}
        }
    }
    ""
}

fn normalize_key(key: &str) -> String {
    key.trim().to_lowercase().replace(' ', "_")
}

fn stimulus_modality(event_type: &str, trial_type: &str) -> String {
    match event_type {
        "looming_onset" => "audio".to_owned(),
        "tactile_onset" => "tactile".to_owned(),
        "response_window_onset" | "trial_start" | "trial_end" => {
            let text = trial_type.trim().to_lowercase();
            match text.as_str() {
                "audio-tactile" => "audio+tactile".to_owned(),
                "auditory-only" => "audio".to_owned(),
                _ => text,
            }
        }
        _ => String::new(),
    }
}

fn first_truthy_string<'a>(first: Option<&'a Value>, second: Option<&'a Value>) -> &'a str {
    first
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .or_else(|| {
            second
                .and_then(Value::as_str)
                .filter(|value| !value.is_empty())
        })
        .unwrap_or("")
}

fn compare_events(left: &ScheduledBlockEvent, right: &ScheduledBlockEvent) -> Ordering {
    left.sample_index
        .cmp(&right.sample_index)
        .then_with(|| event_priority(&left.event_type).cmp(&event_priority(&right.event_type)))
        .then_with(|| left.trigger_key.cmp(&right.trigger_key))
}

fn event_priority(event_type: &str) -> u8 {
    match event_type {
        "audio_sample_zero" => 0,
        "trial_start" => 10,
        "looming_onset" => 20,
        "tactile_onset" => 30,
        "response_window_onset" => 40,
        "trial_end" => 50,
        _ => 100,
    }
}

fn path_text(path: &Path, kind: &str) -> Result<String, ExecutionError> {
    let text = path.to_str().ok_or_else(|| {
        invalid_options(format!(
            "{kind} path cannot be represented as Unicode payload text"
        ))
    })?;
    if text.len() > MAX_NATIVE_PATH_PAYLOAD_BYTES {
        return Err(invalid_options(format!(
            "{kind} path exceeds the {MAX_NATIVE_PATH_PAYLOAD_BYTES}-byte payload limit"
        )));
    }
    Ok(text.to_owned())
}

fn push_bounded_event(
    events: &mut Vec<ScheduledBlockEvent>,
    encoded_bytes: &mut usize,
    event: ScheduledBlockEvent,
) -> Result<(), ExecutionError> {
    add_event_bytes(encoded_bytes, &event, MAX_SCHEDULE_ENCODED_BYTES)?;
    events.push(event);
    Ok(())
}

fn add_event_bytes(
    encoded_bytes: &mut usize,
    event: &ScheduledBlockEvent,
    maximum_encoded_bytes: usize,
) -> Result<(), ExecutionError> {
    let event_bytes = encoded_len(event).map_err(|cause| {
        error(
            ExecutionErrorCode::ScheduleTooLarge,
            "The block schedule could not be measured safely.",
            format!("could not measure a scheduled event: {cause}"),
        )
    })?;
    let next_encoded_bytes = encoded_bytes.checked_add(event_bytes).ok_or_else(|| {
        schedule_too_large("encoded schedule byte count overflowed the native integer range")
    })?;
    if next_encoded_bytes > maximum_encoded_bytes {
        return Err(schedule_too_large(format!(
            "encoded schedule exceeds the {maximum_encoded_bytes}-byte cumulative limit"
        )));
    }
    *encoded_bytes = next_encoded_bytes;
    Ok(())
}

fn checked_u32(value: usize, context: &str) -> Result<u32, ExecutionError> {
    u32::try_from(value).map_err(|_| {
        error(
            ExecutionErrorCode::TooManyEvents,
            "The block schedule contains too many events.",
            format!("{context} did not fit u32"),
        )
    })
}

fn invalid_options(diagnostic: impl Into<String>) -> ExecutionError {
    error(
        ExecutionErrorCode::InvalidScheduleOptions,
        "The block schedule options are invalid.",
        diagnostic,
    )
}

fn sample_range_error(diagnostic: impl Into<String>) -> ExecutionError {
    error(
        ExecutionErrorCode::SampleIndexOutOfRange,
        "A block event has an unsupported sample index.",
        diagnostic,
    )
}

fn schedule_too_large(diagnostic: impl Into<String>) -> ExecutionError {
    error(
        ExecutionErrorCode::ScheduleTooLarge,
        "The block schedule is too large to execute safely.",
        diagnostic,
    )
}

fn error(
    code: ExecutionErrorCode,
    public_message: &'static str,
    diagnostic: impl Into<String>,
) -> ExecutionError {
    ExecutionError::new(code, public_message, diagnostic)
}

#[cfg(test)]
mod tests {
    use std::{fs, time::SystemTime};

    use serde_json::json;

    use super::*;

    fn temporary_manifest(name: &str, contents: &[u8]) -> PathBuf {
        let nonce = SystemTime::now()
            .duration_since(SystemTime::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let directory = std::env::temp_dir().join(format!(
            "pps-runner-execution-{}-{nonce}",
            std::process::id()
        ));
        fs::create_dir_all(&directory).unwrap();
        let path = directory.join(name);
        fs::write(&path, contents).unwrap();
        path
    }

    fn options() -> BlockScheduleOptions {
        BlockScheduleOptions {
            block_index: 1,
            block_label: "Block 01".to_owned(),
            block_wav_path: Some(PathBuf::from("block_01.wav")),
            participant_id: "P001".to_owned(),
            session_id: "S001".to_owned(),
            part_number: Value::String("2".to_owned()),
            sample_rate: 1_000,
            block_metadata: Map::from_iter([
                ("phase".to_owned(), json!("part2")),
                ("capture_enabled".to_owned(), json!(true)),
                ("nested".to_owned(), json!({"private": true})),
            ]),
            trial_duration_s: 8.0,
            stimulus_segment_onset_s: 4.0,
        }
    }

    #[test]
    fn compiles_bom_manifest_with_v1_order_and_scalar_metadata() {
        let path = temporary_manifest(
            "block.csv",
            concat!(
                "\u{feff}Trial_Number,Trial_UID,Trial_Type,Family,SOA_ms,Trial_Start_Sample,Looming_Onset_Sample,Tactile_Onset_Sample,Response_Window_Onset_Sample,Trial_End_Sample\n",
                "1,T_AUDIO_TACTILE,Audio-Tactile,audio_tactile,300,0,4000,4300,4000,8000\n",
                "2,T_CATCH,Catch,catch,0,8000,12000,,12000,16000\n"
            )
            .as_bytes(),
        );
        let schedule = compile_block_schedule(&path, options()).unwrap();
        let event_pairs: Vec<_> = schedule
            .events()
            .iter()
            .map(|event| (event.event_type.as_str(), event.sample_index))
            .collect();
        assert_eq!(
            event_pairs,
            [
                ("audio_sample_zero", 0),
                ("trial_start", 0),
                ("looming_onset", 4000),
                ("response_window_onset", 4000),
                ("tactile_onset", 4300),
                ("trial_start", 8000),
                ("trial_end", 8000),
                ("looming_onset", 12000),
                ("response_window_onset", 12000),
                ("trial_end", 16000),
            ]
        );
        let payload = schedule.events()[1].payload.as_object().unwrap();
        assert_eq!(payload["block_phase"], "part2");
        assert_eq!(payload["block_capture_enabled"], true);
        assert!(!payload.contains_key("block_nested"));
        assert_eq!(payload["part_number"], "2");
    }

    #[test]
    fn verified_compile_rejects_same_row_count_csv_mutation() {
        let original = b"Trial_Number,Trial_UID,Trial_Type\n1,ORIGINAL,Baseline\n";
        let path = temporary_manifest("identity.csv", original);
        let expected_sha256 = format!("{:x}", Sha256::digest(original));
        let schedule = compile_verified_block_schedule(&path, &expected_sha256, options()).unwrap();
        assert_eq!(schedule.summary().trial_row_count, 1);

        fs::write(
            &path,
            b"Trial_Number,Trial_UID,Trial_Type\n1,MUTATED_,Baseline\n",
        )
        .unwrap();
        let failure =
            compile_verified_block_schedule(&path, &expected_sha256, options()).unwrap_err();
        assert_eq!(failure.kind(), ExecutionErrorCode::ManifestIdentityMismatch);
        assert_eq!(failure.code(), "manifest_identity_mismatch");
        assert_eq!(
            failure.public_message(),
            "The block manifest changed after package selection."
        );
        assert!(!failure.public_message().contains("identity.csv"));
    }

    #[test]
    fn seconds_use_ties_to_even_and_invalid_explicit_samples_win() {
        let path = temporary_manifest(
            "seconds.csv",
            b"trial_number,trial_uid,trial_type,family,trial_start_s,looming_onset_sample,looming_onset_s,tactile_onset_s,response_window_onset_s,trial_end_s\n1,T,audio_tactile,audio_tactile,0.005,not-a-number,0.015,0.025,0.035,0.045\n",
        );
        let mut settings = options();
        settings.sample_rate = 100;
        let schedule = compile_block_schedule(&path, settings).unwrap();
        let pairs: Vec<_> = schedule
            .events()
            .iter()
            .map(|event| (event.event_type.as_str(), event.sample_index))
            .collect();
        assert_eq!(
            pairs,
            [
                ("audio_sample_zero", 0),
                ("trial_start", 0),
                ("tactile_onset", 2),
                ("response_window_onset", 4),
                ("trial_end", 4),
            ]
        );
    }

    #[test]
    fn signed_default_samples_are_preserved_but_cursor_skips_them() {
        let path = temporary_manifest(
            "negative.csv",
            b"Trial_Number,Trial_UID,Trial_Type,Family,SOA_ms\n1,T,Baseline,baseline,-5000\n",
        );
        let mut settings = options();
        settings.sample_rate = 100;
        settings.stimulus_segment_onset_s = 0.0;
        let mut schedule = compile_block_schedule(&path, settings).unwrap();
        assert_eq!(schedule.summary().negative_sample_event_count, 2);
        assert_eq!(schedule.events()[0].sample_index, -500);
        let due = schedule.consume_buffer(0, 1);
        assert_eq!(
            due.iter()
                .map(|event| event.event_type.as_str())
                .collect::<Vec<_>>(),
            ["audio_sample_zero", "trial_start"]
        );
    }

    #[test]
    fn cursor_is_forward_only_and_half_open() {
        let mut schedule = BlockEventSchedule::new(vec![
            ScheduledBlockEvent {
                event_type: "trial_end".to_owned(),
                sample_index: 100,
                trigger_key: "trial:end".to_owned(),
                payload: json!({}),
            },
            ScheduledBlockEvent {
                event_type: "trial_start".to_owned(),
                sample_index: 0,
                trigger_key: "trial:start".to_owned(),
                payload: json!({}),
            },
        ])
        .unwrap();
        assert_eq!(schedule.consume_buffer(0, 100).len(), 1);
        assert_eq!(schedule.consume_buffer(100, 1)[0].event_type, "trial_end");
        assert!(schedule.consume_buffer(101, 1).is_empty());
        schedule.reset();
        assert_eq!(schedule.consume_buffer(-50, 1)[0].event_type, "trial_start");
    }

    #[test]
    fn schedule_encoded_budget_is_cumulative_and_fail_closed() {
        let event = ScheduledBlockEvent {
            event_type: "trial_start".to_owned(),
            sample_index: 0,
            trigger_key: "trial:start".to_owned(),
            payload: json!({"value": "bounded"}),
        };
        let one_event_bytes = encoded_len(&event).unwrap();
        let failure = BlockEventSchedule::from_parts_with_budget(
            vec![event.clone(), event],
            1,
            "Block 01".to_owned(),
            1_000,
            1,
            one_event_bytes + 1,
        )
        .unwrap_err();
        assert_eq!(failure.kind(), ExecutionErrorCode::ScheduleTooLarge);
        assert_eq!(failure.code(), "schedule_too_large");
    }

    #[test]
    fn duplicate_headers_reuse_one_projection_and_keep_last_value() {
        let path = temporary_manifest(
            "duplicate.csv",
            b"Trial_Number,Trial_Number,Trial_Type\n1,7,Baseline\n",
        );
        let mut settings = options();
        settings.sample_rate = 100;
        let schedule = compile_block_schedule(&path, settings).unwrap();
        let trial_start = schedule
            .events()
            .iter()
            .find(|event| event.event_type == "trial_start")
            .unwrap();
        assert_eq!(trial_start.payload["trial_number"], 7);
        assert_eq!(trial_start.payload["Trial_Number"], "7");
        assert!(trial_start.trigger_key.contains(":007:"));
    }

    #[test]
    fn metadata_and_native_path_inputs_are_bounded_before_event_cloning() {
        let path = temporary_manifest("empty.csv", b"Trial_Number\n");
        let mut oversized_metadata = options();
        oversized_metadata.block_metadata = Map::from_iter([(
            "large".to_owned(),
            Value::String("x".repeat(MAX_BLOCK_METADATA_BYTES)),
        )]);
        assert_eq!(
            compile_block_schedule(&path, oversized_metadata)
                .unwrap_err()
                .kind(),
            ExecutionErrorCode::InvalidScheduleOptions
        );

        let mut oversized_path = options();
        oversized_path.block_wav_path =
            Some(PathBuf::from("x".repeat(MAX_NATIVE_PATH_PAYLOAD_BYTES + 1)));
        assert_eq!(
            compile_block_schedule(&path, oversized_path)
                .unwrap_err()
                .kind(),
            ExecutionErrorCode::InvalidScheduleOptions
        );
    }

    #[test]
    fn summary_is_path_free_even_when_events_retain_v1_paths() {
        let path = temporary_manifest("empty.csv", b"Trial_Number\n");
        let schedule = compile_block_schedule(&path, options()).unwrap();
        let summary = serde_json::to_string(schedule.summary()).unwrap();
        assert!(!summary.contains(path.to_string_lossy().as_ref()));
        assert!(!summary.contains("block_01.wav"));
        assert!(schedule.summary().encoded_bytes > 0);
        assert!(schedule.summary().encoded_bytes as usize <= MAX_SCHEDULE_ENCODED_BYTES);
        assert_eq!(
            schedule.events()[0].payload["manifest_path"],
            path.to_string_lossy().as_ref()
        );
    }

    #[test]
    fn missing_manifest_error_has_a_path_free_public_surface() {
        let path = PathBuf::from("secret-participant-folder/missing.csv");
        let failure = compile_block_schedule(&path, options()).unwrap_err();
        assert_eq!(failure.kind(), ExecutionErrorCode::ManifestMissing);
        assert!(!failure.public_message().contains("secret"));
        assert!(failure.to_string().contains("secret-participant-folder"));
    }
}
