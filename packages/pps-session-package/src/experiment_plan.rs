//! Read the approved participant order from a verified Planner JSON profile.
//!
//! This is a native planning receipt. It does not bake media or authorize a run.
//! The eventual assembler must recheck each audio ingredient as it consumes it.

use std::{
    collections::{BTreeMap, HashMap},
    fmt, fs,
    path::{Path, PathBuf},
};

use serde_json::Value;

use crate::{
    experiment_profile::{
        VerifiedExperimentProfile, VerifiedProfileIngredient, MAX_EXPERIMENT_PROFILE_BYTES,
        MAX_EXPERIMENT_PROFILE_FILE_BYTES,
    },
    read_bounded_bytes, sha256_bytes, sha256_file_bounded, BoundedReadError, MAX_PREPARED_BLOCKS,
};

const MAX_PLAN_ROWS: usize = 100_000;
const MAX_CSV_COLUMNS: usize = 256;
const MAX_CSV_FIELD_BYTES: usize = 16 * 1024;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PlanErrorCode {
    ProfileChanged,
    SourceChanged,
    PlanInvalid,
    PlanLimit,
    IngredientNotListed,
    ParticipantInvalid,
    ParticipantMissing,
}

impl PlanErrorCode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::ProfileChanged => "profile_changed",
            Self::SourceChanged => "profile_plan_source_changed",
            Self::PlanInvalid => "profile_plan_invalid",
            Self::PlanLimit => "profile_plan_limit",
            Self::IngredientNotListed => "profile_plan_ingredient_not_listed",
            Self::ParticipantInvalid => "profile_participant_invalid",
            Self::ParticipantMissing => "profile_participant_missing",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PlanError(PlanErrorCode);

impl PlanError {
    pub const fn code(self) -> &'static str {
        self.0.as_str()
    }
}

impl fmt::Display for PlanError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.code())
    }
}

impl std::error::Error for PlanError {}

/// One approved trial row and its inventoried audio source. Not serializable.
#[derive(Debug, Clone)]
pub struct ProfileTrialSource {
    fields: BTreeMap<String, String>,
    audio_path: PathBuf,
}

impl ProfileTrialSource {
    pub fn fields(&self) -> &BTreeMap<String, String> {
        &self.fields
    }

    pub fn audio_path(&self) -> &Path {
        &self.audio_path
    }
}

/// One selected block in the existing Segment 6 order. Not serializable.
#[derive(Debug, Clone)]
pub struct ProfileBlockSource {
    order_fields: BTreeMap<String, String>,
    source_csv_path: PathBuf,
    trials: Vec<ProfileTrialSource>,
}

impl ProfileBlockSource {
    pub fn order_fields(&self) -> &BTreeMap<String, String> {
        &self.order_fields
    }

    pub fn source_csv_path(&self) -> &Path {
        &self.source_csv_path
    }

    pub fn trials(&self) -> &[ProfileTrialSource] {
        &self.trials
    }
}

/// Path-bearing, provisional native plan; no media has been materialized.
///
/// ```compile_fail
/// fn require_serialize<T: serde::Serialize>() {}
/// require_serialize::<pps_session_package::experiment_plan::ProfileParticipantPlan>();
/// ```
#[derive(Debug, Clone)]
pub struct ProfileParticipantPlan {
    participant_id: String,
    profile_sha256: String,
    blocks: Vec<ProfileBlockSource>,
}

impl ProfileParticipantPlan {
    pub fn participant_id(&self) -> &str {
        &self.participant_id
    }

    pub fn profile_sha256(&self) -> &str {
        &self.profile_sha256
    }

    pub fn blocks(&self) -> &[ProfileBlockSource] {
        &self.blocks
    }
}

fn sanitized_participant_id(input: &str) -> String {
    let mut value = String::new();
    let mut replacement = false;
    for character in input.trim().chars() {
        if character.is_ascii_alphanumeric() || character == '_' || character == '-' {
            value.push(character);
            replacement = false;
        } else if !replacement {
            value.push('_');
            replacement = true;
        }
    }
    value.trim_matches('_').chars().take(64).collect()
}

fn plan_int(value: Option<&str>, default: i64) -> i64 {
    value
        .and_then(|text| text.parse::<f64>().ok())
        .filter(|number| {
            number.is_finite() && *number >= i64::MIN as f64 && *number < i64::MAX as f64
        })
        .map_or(default, |number| number.trunc() as i64)
}

fn plan_int_value(value: &Value, default: i64) -> Option<i64> {
    let text = match value {
        Value::String(text) => text.clone(),
        Value::Number(number) => number.to_string(),
        _ => return Some(default),
    };
    match text.parse::<f64>() {
        Ok(number)
            if number.is_finite() && number >= i64::MIN as f64 && number < i64::MAX as f64 =>
        {
            Some(number.trunc() as i64)
        }
        Ok(_) => None,
        Err(_) => Some(default),
    }
}

fn resolve(source: &str, base: &Path) -> Result<PathBuf, PlanError> {
    let source = source.trim();
    if source.is_empty() {
        return Err(PlanError(PlanErrorCode::PlanInvalid));
    }
    let path = Path::new(source);
    let candidate = if path.is_absolute() {
        path.to_path_buf()
    } else {
        base.join(path)
    };
    fs::canonicalize(candidate).map_err(|_| PlanError(PlanErrorCode::SourceChanged))
}

fn inventory(
    profile: &VerifiedExperimentProfile,
) -> Result<HashMap<PathBuf, &VerifiedProfileIngredient>, PlanError> {
    let mut files = HashMap::with_capacity(profile.ingredients().len());
    for item in profile.ingredients() {
        let canonical =
            fs::canonicalize(item.path()).map_err(|_| PlanError(PlanErrorCode::SourceChanged))?;
        if files.insert(canonical, item).is_some() {
            return Err(PlanError(PlanErrorCode::PlanInvalid));
        }
    }
    Ok(files)
}

fn read_inventoried_document(
    path: &Path,
    files: &HashMap<PathBuf, &VerifiedProfileIngredient>,
) -> Result<Vec<u8>, PlanError> {
    let ingredient = files
        .get(path)
        .ok_or(PlanError(PlanErrorCode::IngredientNotListed))?;
    let bytes =
        read_bounded_bytes(path, MAX_EXPERIMENT_PROFILE_BYTES).map_err(|error| match error {
            BoundedReadError::TooLarge => PlanError(PlanErrorCode::PlanLimit),
            BoundedReadError::Io(_) => PlanError(PlanErrorCode::SourceChanged),
        })?;
    if bytes.len() as u64 != ingredient.bytes() || sha256_bytes(&bytes) != ingredient.sha256() {
        return Err(PlanError(PlanErrorCode::SourceChanged));
    }
    Ok(bytes)
}

fn csv_rows(bytes: &[u8]) -> Result<Vec<BTreeMap<String, String>>, PlanError> {
    let content = bytes.strip_prefix(&[0xef, 0xbb, 0xbf]).unwrap_or(bytes);
    let mut reader = csv::ReaderBuilder::new()
        .flexible(true)
        .from_reader(content);
    let headers = reader
        .headers()
        .map_err(|_| PlanError(PlanErrorCode::PlanInvalid))?
        .clone();
    if headers.is_empty() || headers.len() > MAX_CSV_COLUMNS || headers.iter().any(str::is_empty) {
        return Err(PlanError(PlanErrorCode::PlanInvalid));
    }
    let mut rows = Vec::new();
    for record in reader.records() {
        let record = record.map_err(|_| PlanError(PlanErrorCode::PlanInvalid))?;
        if rows.len() >= MAX_PLAN_ROWS {
            return Err(PlanError(PlanErrorCode::PlanLimit));
        }
        if record.len() != headers.len()
            || record.iter().any(|field| field.len() > MAX_CSV_FIELD_BYTES)
        {
            return Err(PlanError(PlanErrorCode::PlanInvalid));
        }
        rows.push(
            headers
                .iter()
                .zip(record.iter())
                .map(|(key, value)| (key.to_owned(), value.to_owned()))
                .collect(),
        );
    }
    if rows.is_empty() {
        return Err(PlanError(PlanErrorCode::PlanInvalid));
    }
    Ok(rows)
}

fn rows_match_export(rows: &[BTreeMap<String, String>], embedded: &Value) -> bool {
    serde_json::to_value(rows).is_ok_and(|actual| &actual == embedded)
}

/// Select the existing Segment 6 participant order and its Segment 5 trial sources.
/// Profile/setup/CSV bytes are rechecked at consumption. Audio bytes remain
/// provisional until a native media assembler consumes and rechecks them.
pub fn select_profile_participant(
    profile: &VerifiedExperimentProfile,
    participant_id: &str,
) -> Result<ProfileParticipantPlan, PlanError> {
    let participant_id = sanitized_participant_id(participant_id);
    if participant_id.is_empty() {
        return Err(PlanError(PlanErrorCode::ParticipantInvalid));
    }
    let profile_bytes = read_bounded_bytes(profile.profile_path(), MAX_EXPERIMENT_PROFILE_BYTES)
        .map_err(|_| PlanError(PlanErrorCode::ProfileChanged))?;
    if sha256_bytes(&profile_bytes) != profile.profile_sha256() {
        return Err(PlanError(PlanErrorCode::ProfileChanged));
    }
    let content = profile_bytes
        .strip_prefix(&[0xef, 0xbb, 0xbf])
        .unwrap_or(&profile_bytes);
    let document: Value =
        serde_json::from_slice(content).map_err(|_| PlanError(PlanErrorCode::PlanInvalid))?;
    let files = inventory(profile)?;
    let run_setup_path = fs::canonicalize(profile.run_setup_path())
        .map_err(|_| PlanError(PlanErrorCode::SourceChanged))?;
    let run_setup_bytes = read_inventoried_document(&run_setup_path, &files)?;
    let run_setup: Value = serde_json::from_slice(
        run_setup_bytes
            .strip_prefix(&[0xef, 0xbb, 0xbf])
            .unwrap_or(&run_setup_bytes),
    )
    .map_err(|_| PlanError(PlanErrorCode::PlanInvalid))?;
    if run_setup != document["assembly"]["run_setup"]
        || run_setup["schema"] != "pps-experiment-run-setup.v1"
        || run_setup["prepared"] != true
    {
        return Err(PlanError(PlanErrorCode::PlanInvalid));
    }
    let base = run_setup_path
        .parent()
        .ok_or(PlanError(PlanErrorCode::PlanInvalid))?;
    let source_manifest_path = resolve(
        run_setup["source_segment5_manifest"].as_str().unwrap_or(""),
        base,
    )?;
    let source_manifest = files
        .get(&source_manifest_path)
        .ok_or(PlanError(PlanErrorCode::IngredientNotListed))?;
    if run_setup["source_segment5_manifest_sha256"].as_str() != Some(source_manifest.sha256()) {
        return Err(PlanError(PlanErrorCode::SourceChanged));
    }
    let (source_hash, source_bytes) =
        sha256_file_bounded(&source_manifest_path, MAX_EXPERIMENT_PROFILE_FILE_BYTES)
            .map_err(|_| PlanError(PlanErrorCode::SourceChanged))?;
    if source_hash != source_manifest.sha256() || source_bytes != source_manifest.bytes() {
        return Err(PlanError(PlanErrorCode::SourceChanged));
    }
    let order_path = resolve(run_setup["csv_path"].as_str().unwrap_or(""), base)?;
    if let Some(slots) = run_setup["instruction_profile"]["slots"].as_array() {
        for slot in slots {
            if slot["enabled"] == true && slot["path"].as_str().is_some_and(|path| !path.is_empty())
            {
                let instruction_path = resolve(slot["path"].as_str().unwrap_or(""), base)?;
                if !files.contains_key(&instruction_path) {
                    return Err(PlanError(PlanErrorCode::IngredientNotListed));
                }
            }
        }
    }
    let order_bytes = read_inventoried_document(&order_path, &files)?;
    let order_rows = csv_rows(&order_bytes)?;
    if !rows_match_export(&order_rows, &document["assembly"]["block_order"])
        || plan_int_value(&run_setup["total_block_runs"], order_rows.len() as i64)
            != Some(order_rows.len() as i64)
    {
        return Err(PlanError(PlanErrorCode::PlanInvalid));
    }
    let mut selected: Vec<_> = order_rows
        .into_iter()
        .filter(|row| {
            row.get("participant_id")
                .is_some_and(|id| id.trim() == participant_id)
        })
        .collect();
    if selected.is_empty() {
        return Err(PlanError(PlanErrorCode::ParticipantMissing));
    }
    if selected.len() > MAX_PREPARED_BLOCKS {
        return Err(PlanError(PlanErrorCode::PlanLimit));
    }
    selected.sort_by_key(|row| {
        (
            plan_int(row.get("phase_index").map(String::as_str), 1),
            plan_int(row.get("participant_block_position").map(String::as_str), 1),
        )
    });
    let order_base = order_path
        .parent()
        .ok_or(PlanError(PlanErrorCode::PlanInvalid))?;
    let exported_blocks = document["assembly"]["blocks"]
        .as_array()
        .ok_or(PlanError(PlanErrorCode::PlanInvalid))?;
    let mut exported_by_path = HashMap::with_capacity(exported_blocks.len());
    for block in exported_blocks {
        let source = block["source_csv_path"]
            .as_str()
            .ok_or(PlanError(PlanErrorCode::PlanInvalid))?;
        let canonical =
            fs::canonicalize(source).map_err(|_| PlanError(PlanErrorCode::SourceChanged))?;
        if exported_by_path.insert(canonical, block).is_some() {
            return Err(PlanError(PlanErrorCode::PlanInvalid));
        }
    }
    let mut blocks = Vec::with_capacity(selected.len());
    let mut trial_count = 0_usize;
    for order_fields in selected {
        let source_csv_path = resolve(
            order_fields
                .get("block_csv_path")
                .map(String::as_str)
                .unwrap_or(""),
            order_base,
        )?;
        let csv_bytes = read_inventoried_document(&source_csv_path, &files)?;
        let mut trial_rows = csv_rows(&csv_bytes)?;
        trial_count = trial_count
            .checked_add(trial_rows.len())
            .filter(|count| *count <= MAX_PLAN_ROWS)
            .ok_or(PlanError(PlanErrorCode::PlanLimit))?;
        let embedded = exported_by_path
            .get(&source_csv_path)
            .ok_or(PlanError(PlanErrorCode::PlanInvalid))?;
        if !rows_match_export(&trial_rows, &embedded["rows"]) {
            return Err(PlanError(PlanErrorCode::PlanInvalid));
        }
        // The compatibility assembler consumes the approved CSV in this stable
        // trial-index order; the exported row snapshot retains file order.
        trial_rows.sort_by_key(|row| plan_int(row.get("block_trial_index").map(String::as_str), 1));
        let trial_base = source_csv_path
            .parent()
            .ok_or(PlanError(PlanErrorCode::PlanInvalid))?;
        let mut trials = Vec::with_capacity(trial_rows.len());
        for fields in trial_rows {
            let audio = fields
                .get("trial_file_path")
                .or_else(|| fields.get("Trial_File_Path"))
                .map(String::as_str)
                .unwrap_or("");
            let audio_path = resolve(audio, trial_base)?;
            if !files.contains_key(&audio_path) {
                return Err(PlanError(PlanErrorCode::IngredientNotListed));
            }
            trials.push(ProfileTrialSource { fields, audio_path });
        }
        blocks.push(ProfileBlockSource {
            order_fields,
            source_csv_path,
            trials,
        });
    }
    Ok(ProfileParticipantPlan {
        participant_id,
        profile_sha256: profile.profile_sha256().to_owned(),
        blocks,
    })
}
