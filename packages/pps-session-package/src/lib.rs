//! Pure Rust verification for V1 PPS prepared-session packages.
//!
//! The verifier deliberately has no Tauri, UI, audio, or networking dependency.
//! It preserves the read-only acceptance and first-failure ordering of Python
//! `prepared_session_manifest_current_status`. The serializable summary contains
//! no filesystem paths or hashes; resolved paths and digests remain in the
//! Rust-only [`VerifiedPreparedSession`] receipt.

use std::{
    collections::BTreeMap,
    fmt, fs,
    io::{self, Read},
    path::{Path, PathBuf},
};

use serde::Serialize;
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};

pub const RUN_PACKAGE_SCHEMA: &str = "pps-run-session.v1";
pub const PARTICIPANT_BLOCK_WAVS_MODE: &str = "participant_block_wavs";
pub const VERIFIED_MESSAGE: &str = "Prepared local audio package is available.";

/// Borrowed native inputs for one V1-compatible verification pass.
#[derive(Debug, Clone, Copy)]
pub struct VerificationRequest<'a> {
    pub manifest_path: &'a Path,
    pub run_setup_manifest_path: Option<&'a Path>,
    pub participant_id: Option<&'a str>,
}

impl<'a> VerificationRequest<'a> {
    pub const fn new(manifest_path: &'a Path) -> Self {
        Self {
            manifest_path,
            run_setup_manifest_path: None,
            participant_id: None,
        }
    }

    pub const fn with_run_setup(mut self, run_setup_manifest_path: &'a Path) -> Self {
        self.run_setup_manifest_path = Some(run_setup_manifest_path);
        self
    }

    pub const fn with_participant_id(mut self, participant_id: &'a str) -> Self {
        self.participant_id = Some(participant_id);
        self
    }
}

/// Browser-safe, path-free description of a verified prepared session.
#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PreparedSessionSummary {
    pub schema: String,
    pub participant_id: String,
    pub session_id: String,
    pub session_group_id: String,
    pub part_number: Option<i64>,
    pub part_session_id: String,
    pub execution_mode: String,
    pub blocks: Vec<PreparedBlockSummary>,
}

/// Browser-safe, path-free description of one block in manifest order.
#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PreparedBlockSummary {
    pub index: i64,
    pub label: String,
    pub trial_count: i64,
    pub duration_s: f64,
}

/// Native-only identity for a file whose bytes were hash-verified.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VerifiedNativeFile {
    path: PathBuf,
    sha256: String,
}

impl VerifiedNativeFile {
    pub fn path(&self) -> &Path {
        &self.path
    }

    pub fn sha256(&self) -> &str {
        &self.sha256
    }
}

/// Native-only resolved paths and provenance for one verified block.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VerifiedPreparedBlock {
    manifest_path: PathBuf,
    wav_path: PathBuf,
    source_block_csv: Option<VerifiedNativeFile>,
    source_trial_wavs: Vec<VerifiedNativeFile>,
}

impl VerifiedPreparedBlock {
    pub fn manifest_path(&self) -> &Path {
        &self.manifest_path
    }

    pub fn wav_path(&self) -> &Path {
        &self.wav_path
    }

    pub fn source_block_csv(&self) -> Option<&VerifiedNativeFile> {
        self.source_block_csv.as_ref()
    }

    pub fn source_trial_wavs(&self) -> &[VerifiedNativeFile] {
        &self.source_trial_wavs
    }
}

/// A successful native verification receipt.
///
/// This type intentionally does not implement `Serialize`: native paths and
/// digests must not cross the Tauri/WebView boundary by accident. Reverify at
/// the final execution boundary to close the filesystem time-of-check/use gap.
#[derive(Debug, Clone, PartialEq)]
pub struct VerifiedPreparedSession {
    summary: PreparedSessionSummary,
    manifest_path: PathBuf,
    manifest_sha256: String,
    session_dir: PathBuf,
    run_setup_manifest: Option<VerifiedNativeFile>,
    blocks: Vec<VerifiedPreparedBlock>,
}

impl VerifiedPreparedSession {
    pub fn summary(&self) -> &PreparedSessionSummary {
        &self.summary
    }

    pub fn into_summary(self) -> PreparedSessionSummary {
        self.summary
    }

    pub fn manifest_path(&self) -> &Path {
        &self.manifest_path
    }

    pub fn manifest_sha256(&self) -> &str {
        &self.manifest_sha256
    }

    pub fn session_dir(&self) -> &Path {
        &self.session_dir
    }

    pub fn run_setup_manifest(&self) -> Option<&VerifiedNativeFile> {
        self.run_setup_manifest.as_ref()
    }

    pub fn blocks(&self) -> &[VerifiedPreparedBlock] {
        &self.blocks
    }

    pub const fn v1_message(&self) -> &'static str {
        VERIFIED_MESSAGE
    }
}

/// Stable failure categories suitable for a sanitized native adapter.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum VerificationErrorCode {
    ManifestMissing,
    UnsupportedSchema,
    ManifestInvalid,
    ForeignHostPath,
    ParticipantMismatch,
    RunSetupMismatch,
    NoBlocks,
    BlockWavMissing,
    BlockManifestMissing,
    SourceRunSetupMissing,
    SourceRunSetupUnreadable,
    SourceRunSetupHashMissing,
    SourceRunSetupStale,
    SourceProvenanceMissing,
    SourceBlockCsvMissing,
    SourceBlockCsvUnreadable,
    SourceBlockCsvStale,
    SourceTrialCountStale,
    PreparedBlockCsvUnreadable,
    PreparedTrialCountStale,
    SourceTrialWavMissing,
    SourceTrialWavUnreadable,
    SourceTrialWavStale,
}

impl VerificationErrorCode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::ManifestMissing => "manifest_missing",
            Self::UnsupportedSchema => "unsupported_schema",
            Self::ManifestInvalid => "manifest_invalid",
            Self::ForeignHostPath => "foreign_host_path",
            Self::ParticipantMismatch => "participant_mismatch",
            Self::RunSetupMismatch => "run_setup_mismatch",
            Self::NoBlocks => "no_blocks",
            Self::BlockWavMissing => "block_wav_missing",
            Self::BlockManifestMissing => "block_manifest_missing",
            Self::SourceRunSetupMissing => "source_run_setup_missing",
            Self::SourceRunSetupUnreadable => "source_run_setup_unreadable",
            Self::SourceRunSetupHashMissing => "source_run_setup_hash_missing",
            Self::SourceRunSetupStale => "source_run_setup_stale",
            Self::SourceProvenanceMissing => "source_provenance_missing",
            Self::SourceBlockCsvMissing => "source_block_csv_missing",
            Self::SourceBlockCsvUnreadable => "source_block_csv_unreadable",
            Self::SourceBlockCsvStale => "source_block_csv_stale",
            Self::SourceTrialCountStale => "source_trial_count_stale",
            Self::PreparedBlockCsvUnreadable => "prepared_block_csv_unreadable",
            Self::PreparedTrialCountStale => "prepared_trial_count_stale",
            Self::SourceTrialWavMissing => "source_trial_wav_missing",
            Self::SourceTrialWavUnreadable => "source_trial_wav_unreadable",
            Self::SourceTrialWavStale => "source_trial_wav_stale",
        }
    }
}

impl fmt::Display for VerificationErrorCode {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

/// Native verification failure with separate safe and diagnostic messages.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VerificationError {
    code: VerificationErrorCode,
    public_message: &'static str,
    diagnostic: String,
}

impl VerificationError {
    fn new(
        code: VerificationErrorCode,
        public_message: &'static str,
        diagnostic: impl Into<String>,
    ) -> Self {
        Self {
            code,
            public_message,
            diagnostic: diagnostic.into(),
        }
    }

    pub const fn kind(&self) -> VerificationErrorCode {
        self.code
    }

    pub const fn code(&self) -> &'static str {
        self.code.as_str()
    }

    pub const fn public_message(&self) -> &'static str {
        self.public_message
    }
}

impl fmt::Display for VerificationError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.diagnostic)
    }
}

impl std::error::Error for VerificationError {}

#[derive(Debug, Clone)]
struct ParsedBlock {
    summary: PreparedBlockSummary,
    manifest_path: PathBuf,
    wav_path: PathBuf,
    metadata: Map<String, Value>,
}

#[derive(Debug, Clone)]
struct ParsedManifest {
    summary: PreparedSessionSummary,
    session_dir: PathBuf,
    source_run_setup_manifest_path: Option<PathBuf>,
    source_run_setup_sha256: String,
    blocks: Vec<ParsedBlock>,
}

/// Verify a prepared-session package using the V1 Python oracle's acceptance
/// order and freshness semantics.
pub fn verify_prepared_session(
    request: VerificationRequest<'_>,
) -> Result<VerifiedPreparedSession, VerificationError> {
    let manifest_path = request.manifest_path;
    if !path_exists(manifest_path) {
        return Err(VerificationError::new(
            VerificationErrorCode::ManifestMissing,
            "Prepared session manifest is missing.",
            "Prepared session manifest is missing.",
        ));
    }

    let manifest_bytes = fs::read(manifest_path).map_err(|_| unsupported_schema(manifest_path))?;
    let manifest_value: Value =
        serde_json::from_slice(&manifest_bytes).map_err(|_| unsupported_schema(manifest_path))?;
    let manifest_object = manifest_value
        .as_object()
        .ok_or_else(|| unsupported_schema(manifest_path))?;
    if manifest_object.get("schema").and_then(Value::as_str) != Some(RUN_PACKAGE_SCHEMA) {
        return Err(unsupported_schema(manifest_path));
    }
    let parsed = parse_manifest(manifest_object, manifest_path)?;

    if request
        .participant_id
        .is_some_and(|participant_id| parsed.summary.participant_id != participant_id)
    {
        return Err(VerificationError::new(
            VerificationErrorCode::ParticipantMismatch,
            "Prepared session participant does not match.",
            "Prepared session participant does not match.",
        ));
    }

    let requested_run_setup = request
        .run_setup_manifest_path
        .map(Path::to_path_buf)
        .or_else(|| parsed.source_run_setup_manifest_path.clone());
    if let Some(run_setup_manifest_path) = request.run_setup_manifest_path {
        let source_matches = if let Some(source) = parsed.source_run_setup_manifest_path.as_deref()
        {
            ensure_native_path_syntax(source)?;
            same_resolved_path(source, run_setup_manifest_path)
        } else {
            false
        };
        if !source_matches {
            return Err(VerificationError::new(
                VerificationErrorCode::RunSetupMismatch,
                "Prepared session belongs to a different run setup.",
                "Prepared session belongs to a different run setup.",
            ));
        }
    }

    if parsed.blocks.is_empty() {
        return Err(VerificationError::new(
            VerificationErrorCode::NoBlocks,
            "Prepared session has no blocks.",
            "Prepared session has no blocks.",
        ));
    }

    let mut verified_blocks = Vec::with_capacity(parsed.blocks.len());
    for block in &parsed.blocks {
        let wav_path = session_package_path(&parsed.session_dir, &block.wav_path)?;
        if !path_exists(&wav_path) {
            return Err(VerificationError::new(
                VerificationErrorCode::BlockWavMissing,
                "A prepared block WAV is missing.",
                format!("Prepared block WAV is missing: {}", wav_path.display()),
            ));
        }
        let block_manifest_path = session_package_path(&parsed.session_dir, &block.manifest_path)?;
        if !path_exists(&block_manifest_path) {
            return Err(VerificationError::new(
                VerificationErrorCode::BlockManifestMissing,
                "A prepared block manifest is missing.",
                format!(
                    "Prepared block manifest is missing: {}",
                    block_manifest_path.display()
                ),
            ));
        }
        verified_blocks.push(VerifiedPreparedBlock {
            manifest_path: absolute_native_path(&block_manifest_path),
            wav_path: absolute_native_path(&wav_path),
            source_block_csv: None,
            source_trial_wavs: Vec::new(),
        });
    }

    let run_setup_manifest = if parsed.summary.execution_mode == PARTICIPANT_BLOCK_WAVS_MODE {
        let run_setup_path = requested_run_setup.ok_or_else(|| {
            VerificationError::new(
                VerificationErrorCode::SourceRunSetupMissing,
                "Prepared session source run setup is missing.",
                "Prepared session source run setup is missing.",
            )
        })?;
        ensure_native_path_syntax(&run_setup_path)?;
        if !path_exists(&run_setup_path) {
            return Err(VerificationError::new(
                VerificationErrorCode::SourceRunSetupMissing,
                "Prepared session source run setup is missing.",
                "Prepared session source run setup is missing.",
            ));
        }
        let run_setup_hash = sha256_file(&run_setup_path).map_err(|error| {
            VerificationError::new(
                VerificationErrorCode::SourceRunSetupUnreadable,
                "Prepared session source run setup cannot be read.",
                format!("Prepared session source run setup cannot be read: {error}"),
            )
        })?;
        if parsed.source_run_setup_sha256.is_empty() {
            return Err(VerificationError::new(
                VerificationErrorCode::SourceRunSetupHashMissing,
                "Prepared session must be regenerated because source-hash tracking is missing.",
                "Prepared session was created before source-hash tracking; regenerate audio assets.",
            ));
        }
        if parsed.source_run_setup_sha256 != run_setup_hash {
            return Err(VerificationError::new(
                VerificationErrorCode::SourceRunSetupStale,
                "Prepared session is stale because the run setup changed.",
                "Prepared session is stale because the Segment 6 run setup changed.",
            ));
        }

        for (parsed_block, verified_block) in parsed.blocks.iter().zip(&mut verified_blocks) {
            if parsed_block
                .metadata
                .get("is_topup_block")
                .is_some_and(python_truthy)
            {
                continue;
            }
            verify_block_sources(parsed_block, verified_block, &run_setup_path)?;
        }

        Some(VerifiedNativeFile {
            path: absolute_native_path(&run_setup_path),
            sha256: run_setup_hash,
        })
    } else {
        None
    };

    Ok(VerifiedPreparedSession {
        summary: parsed.summary,
        manifest_path: absolute_native_path(manifest_path),
        manifest_sha256: sha256_bytes(&manifest_bytes),
        session_dir: absolute_native_path(&parsed.session_dir),
        run_setup_manifest,
        blocks: verified_blocks,
    })
}

fn verify_block_sources(
    block: &ParsedBlock,
    verified_block: &mut VerifiedPreparedBlock,
    run_setup_manifest_path: &Path,
) -> Result<(), VerificationError> {
    let source_text = block
        .metadata
        .get("source_block_csv_path")
        .filter(|value| python_truthy(value))
        .map(python_string)
        .unwrap_or_default()
        .trim()
        .to_owned();
    let recorded_source_hash = block
        .metadata
        .get("source_block_csv_sha256")
        .filter(|value| python_truthy(value))
        .map(python_string)
        .unwrap_or_default()
        .trim()
        .to_owned();
    if source_text.is_empty() || recorded_source_hash.is_empty() {
        return Err(VerificationError::new(
            VerificationErrorCode::SourceProvenanceMissing,
            "A prepared block lacks source CSV provenance.",
            format!(
                "Prepared block {} lacks source CSV provenance; regenerate audio assets.",
                block.summary.index
            ),
        ));
    }

    let run_setup_parent = run_setup_manifest_path
        .parent()
        .unwrap_or_else(|| Path::new(""));
    let source_csv = resolve_relative_path(&source_text, run_setup_parent)?;
    if !path_exists(&source_csv) {
        return Err(VerificationError::new(
            VerificationErrorCode::SourceBlockCsvMissing,
            "A prepared block source CSV is missing.",
            format!(
                "Prepared block source CSV is missing: {}",
                source_csv.display()
            ),
        ));
    }
    let source_hash = sha256_file(&source_csv).map_err(|error| {
        VerificationError::new(
            VerificationErrorCode::SourceBlockCsvUnreadable,
            "A prepared block source CSV cannot be read.",
            format!("Prepared block source CSV cannot be read: {error}"),
        )
    })?;
    if source_hash != recorded_source_hash {
        return Err(VerificationError::new(
            VerificationErrorCode::SourceBlockCsvStale,
            "Prepared session is stale because a source block CSV changed.",
            format!(
                "Prepared block {} is stale because the source CSV changed: {}",
                block.summary.index,
                source_csv.display()
            ),
        ));
    }

    let mut source_rows = read_csv_rows(&source_csv).map_err(|error| {
        VerificationError::new(
            VerificationErrorCode::SourceBlockCsvUnreadable,
            "A prepared block source CSV cannot be read.",
            format!("Prepared block source CSV cannot be read: {error}"),
        )
    })?;
    if source_rows.len() as i128 != i128::from(block.summary.trial_count) {
        return Err(VerificationError::new(
            VerificationErrorCode::SourceTrialCountStale,
            "Prepared block trial count does not match its source CSV.",
            format!(
                "Prepared block {} trial count is stale: {} prepared vs {} source rows.",
                block.summary.index,
                block.summary.trial_count,
                source_rows.len()
            ),
        ));
    }

    let prepared_csv = verified_block.manifest_path.clone();
    let prepared_rows = read_csv_rows(&prepared_csv).map_err(|error| {
        VerificationError::new(
            VerificationErrorCode::PreparedBlockCsvUnreadable,
            "A prepared block manifest cannot be read.",
            format!("Prepared block manifest cannot be read: {error}"),
        )
    })?;
    if prepared_rows.len() as i128 != i128::from(block.summary.trial_count) {
        return Err(VerificationError::new(
            VerificationErrorCode::PreparedTrialCountStale,
            "Prepared block manifest row count is stale.",
            format!(
                "Prepared block {} manifest row count is stale: {} expected vs {} prepared rows.",
                block.summary.index,
                block.summary.trial_count,
                prepared_rows.len()
            ),
        ));
    }

    source_rows.sort_by_key(|row| {
        row.get("block_trial_index")
            .map(|value| v1_csv_int(value))
            .unwrap_or_default()
    });
    let mut source_trial_wavs = Vec::with_capacity(source_rows.len());
    for (source_row, prepared_row) in source_rows.iter().zip(&prepared_rows) {
        let trial_text = row_value(source_row, &["Trial_File_Path", "trial_file_path"], "");
        let source_parent = source_csv.parent().unwrap_or_else(|| Path::new(""));
        let trial_path = resolve_relative_path(trial_text, source_parent)?;
        if !path_exists(&trial_path) {
            return Err(VerificationError::new(
                VerificationErrorCode::SourceTrialWavMissing,
                "A source trial WAV is missing.",
                format!(
                    "Prepared block {} source trial WAV is missing: {}",
                    block.summary.index,
                    trial_path.display()
                ),
            ));
        }
        let current_hash = sha256_file(&trial_path).map_err(|error| {
            VerificationError::new(
                VerificationErrorCode::SourceTrialWavUnreadable,
                "A source trial WAV cannot be read.",
                format!(
                    "Prepared block {} source trial WAV cannot be read: {error}",
                    block.summary.index
                ),
            )
        })?;
        let declared_hash = row_value(source_row, &["Source_SHA256", "source_sha256"], "").trim();
        let prepared_hash = row_value(prepared_row, &["Source_SHA256", "source_sha256"], "").trim();
        if (!declared_hash.is_empty() && declared_hash != current_hash)
            || (!prepared_hash.is_empty() && prepared_hash != current_hash)
        {
            return Err(VerificationError::new(
                VerificationErrorCode::SourceTrialWavStale,
                "Prepared session is stale because a source trial WAV changed.",
                format!(
                    "Prepared block {} is stale because a source trial WAV changed: {}",
                    block.summary.index,
                    trial_path.display()
                ),
            ));
        }
        source_trial_wavs.push(VerifiedNativeFile {
            path: absolute_native_path(&trial_path),
            sha256: current_hash,
        });
    }

    verified_block.source_block_csv = Some(VerifiedNativeFile {
        path: absolute_native_path(&source_csv),
        sha256: source_hash,
    });
    verified_block.source_trial_wavs = source_trial_wavs;
    Ok(())
}

fn parse_manifest(
    object: &Map<String, Value>,
    manifest_path: &Path,
) -> Result<ParsedManifest, VerificationError> {
    let session_dir = object
        .get("session_dir")
        .filter(|value| python_truthy(value))
        .map(|value| PathBuf::from(python_string(value)))
        .unwrap_or_else(|| {
            manifest_path
                .parent()
                .unwrap_or_else(|| Path::new(""))
                .to_path_buf()
        });
    let participant_id = optional_python_string(object.get("participant_id"));
    let session_id = object
        .get("session_id")
        .filter(|value| python_truthy(value))
        .map(python_string)
        .unwrap_or_else(|| {
            session_dir
                .file_name()
                .map(|name| name.to_string_lossy().into_owned())
                .unwrap_or_default()
        });
    let session_group_id = optional_python_string(object.get("session_group_id"));
    let part_number = object
        .get("part_number")
        .map(|value| v1_as_int(value, 0))
        .filter(|number| *number != 0);
    let part_session_id = object
        .get("part_session_id")
        .filter(|value| python_truthy(value))
        .map(python_string)
        .unwrap_or_else(|| session_id.clone());
    let execution_mode = object
        .get("execution_mode")
        .filter(|value| python_truthy(value))
        .map(python_string)
        .unwrap_or_else(|| "design_schedule_blocks".to_owned());
    let source_run_setup_manifest_path = object
        .get("source_run_setup_manifest_path")
        .filter(|value| python_truthy(value))
        .map(|value| PathBuf::from(python_string(value)));
    let source_run_setup_sha256 = object
        .get("source_run_setup_sha256")
        .filter(|value| python_truthy(value))
        .map(python_string)
        .unwrap_or_default()
        .trim()
        .to_owned();

    let raw_blocks = match object.get("blocks") {
        None => &[][..],
        Some(Value::Array(blocks)) => blocks.as_slice(),
        Some(_) => return Err(invalid_manifest("blocks must be a list")),
    };
    let mut blocks = Vec::with_capacity(raw_blocks.len());
    let mut block_summaries = Vec::with_capacity(raw_blocks.len());
    for raw_block in raw_blocks {
        let block = parse_block(raw_block)?;
        block_summaries.push(block.summary.clone());
        blocks.push(block);
    }

    Ok(ParsedManifest {
        summary: PreparedSessionSummary {
            schema: RUN_PACKAGE_SCHEMA.to_owned(),
            participant_id,
            session_id,
            session_group_id,
            part_number,
            part_session_id,
            execution_mode,
            blocks: block_summaries,
        },
        session_dir,
        source_run_setup_manifest_path,
        source_run_setup_sha256,
        blocks,
    })
}

fn parse_block(value: &Value) -> Result<ParsedBlock, VerificationError> {
    let object = value
        .as_object()
        .ok_or_else(|| invalid_manifest("each block must be an object"))?;
    let index = required_int(object, "index")?;
    let label = required_python_string(object, "label")?;
    let manifest_path = required_path(object, "manifest_path")?;
    let wav_path = required_path(object, "wav_path")?;
    let trial_count = required_int(object, "trial_count")?;
    let duration_s = required_float(object, "duration_s")?;
    let metadata = match object.get("metadata") {
        None | Some(Value::Null) | Some(Value::Bool(false)) => Map::new(),
        Some(Value::Object(metadata)) => metadata.clone(),
        Some(value) if !python_truthy(value) => Map::new(),
        Some(_) => return Err(invalid_manifest("block metadata must be an object")),
    };
    Ok(ParsedBlock {
        summary: PreparedBlockSummary {
            index,
            label,
            trial_count,
            duration_s,
        },
        manifest_path,
        wav_path,
        metadata,
    })
}

fn required_python_string(
    object: &Map<String, Value>,
    field: &str,
) -> Result<String, VerificationError> {
    object
        .get(field)
        .map(python_string)
        .ok_or_else(|| invalid_manifest(format!("block is missing {field}")))
}

fn required_path(object: &Map<String, Value>, field: &str) -> Result<PathBuf, VerificationError> {
    let value = object
        .get(field)
        .ok_or_else(|| invalid_manifest(format!("block is missing {field}")))?;
    let text = value
        .as_str()
        .ok_or_else(|| invalid_manifest(format!("block {field} must be a path string")))?;
    Ok(PathBuf::from(text))
}

fn required_int(object: &Map<String, Value>, field: &str) -> Result<i64, VerificationError> {
    object
        .get(field)
        .and_then(python_int)
        .ok_or_else(|| invalid_manifest(format!("block {field} must be an integer")))
}

fn required_float(object: &Map<String, Value>, field: &str) -> Result<f64, VerificationError> {
    object
        .get(field)
        .and_then(python_float)
        .ok_or_else(|| invalid_manifest(format!("block {field} must be numeric")))
}

fn unsupported_schema(path: &Path) -> VerificationError {
    VerificationError::new(
        VerificationErrorCode::UnsupportedSchema,
        "Unsupported prepared-session schema.",
        format!("Unsupported run package manifest: {}", path.display()),
    )
}

fn invalid_manifest(detail: impl Into<String>) -> VerificationError {
    let detail = detail.into();
    VerificationError::new(
        VerificationErrorCode::ManifestInvalid,
        "Prepared session manifest is invalid.",
        format!("Invalid prepared session manifest: {detail}"),
    )
}

fn optional_python_string(value: Option<&Value>) -> String {
    value.map(python_string).unwrap_or_default()
}

fn python_string(value: &Value) -> String {
    match value {
        Value::Null => "None".to_owned(),
        Value::Bool(true) => "True".to_owned(),
        Value::Bool(false) => "False".to_owned(),
        Value::Number(number) => number.to_string(),
        Value::String(text) => text.clone(),
        Value::Array(_) | Value::Object(_) => value.to_string(),
    }
}

fn python_truthy(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(value) => *value,
        Value::Number(number) => number.as_f64().is_some_and(|value| value != 0.0),
        Value::String(value) => !value.is_empty(),
        Value::Array(value) => !value.is_empty(),
        Value::Object(value) => !value.is_empty(),
    }
}

fn python_int(value: &Value) -> Option<i64> {
    match value {
        Value::Bool(value) => Some(i64::from(*value)),
        Value::Number(number) => number
            .as_i64()
            .or_else(|| number.as_u64().and_then(|value| i64::try_from(value).ok()))
            .or_else(|| number.as_f64().and_then(finite_truncated_i64)),
        Value::String(text) => text.trim().parse::<i64>().ok(),
        _ => None,
    }
}

fn python_float(value: &Value) -> Option<f64> {
    match value {
        Value::Bool(value) => Some(if *value { 1.0 } else { 0.0 }),
        Value::Number(number) => number.as_f64(),
        Value::String(text) => text.trim().parse::<f64>().ok(),
        _ => None,
    }
    .filter(|number| number.is_finite())
}

fn finite_truncated_i64(value: f64) -> Option<i64> {
    if !value.is_finite() || value.trunc() < i64::MIN as f64 || value.trunc() > i64::MAX as f64 {
        return None;
    }
    Some(value.trunc() as i64)
}

fn v1_as_int(value: &Value, default: i64) -> i64 {
    let text = python_string(value);
    text.trim()
        .parse::<f64>()
        .ok()
        .and_then(finite_truncated_i64)
        .unwrap_or(default)
}

fn v1_csv_int(value: &str) -> i128 {
    let Ok(number) = value.trim().parse::<f64>() else {
        return 0;
    };
    if !number.is_finite() {
        return 0;
    }
    let truncated = number.trunc();
    if truncated >= i128::MAX as f64 {
        i128::MAX
    } else if truncated <= i128::MIN as f64 {
        i128::MIN
    } else {
        truncated as i128
    }
}

fn path_exists(path: &Path) -> bool {
    fs::metadata(path).is_ok()
}

fn session_package_path(session_dir: &Path, value: &Path) -> Result<PathBuf, VerificationError> {
    ensure_native_path_syntax(session_dir)?;
    ensure_native_path_syntax(value)?;
    if value.is_absolute() {
        Ok(value.to_path_buf())
    } else {
        Ok(session_dir.join(value))
    }
}

fn resolve_relative_path(value: &str, base_dir: &Path) -> Result<PathBuf, VerificationError> {
    let text = value.trim();
    if text.is_empty() {
        return Ok(base_dir.to_path_buf());
    }
    let path = PathBuf::from(text);
    ensure_native_path_syntax(&path)?;
    if path.is_absolute() {
        Ok(path)
    } else {
        Ok(base_dir.join(path))
    }
}

fn ensure_native_path_syntax(path: &Path) -> Result<(), VerificationError> {
    let text = path.to_string_lossy();
    if is_foreign_absolute_path(&text) {
        return Err(VerificationError::new(
            VerificationErrorCode::ForeignHostPath,
            "This legacy prepared session uses paths from a different operating system.",
            format!(
                "Prepared session contains an absolute path from a different operating system: {text}"
            ),
        ));
    }
    Ok(())
}

#[cfg(not(windows))]
fn is_foreign_absolute_path(value: &str) -> bool {
    let bytes = value.as_bytes();
    let drive_rooted = bytes.len() >= 3
        && bytes[0].is_ascii_alphabetic()
        && bytes[1] == b':'
        && matches!(bytes[2], b'\\' | b'/');
    drive_rooted || value.starts_with("\\\\")
}

#[cfg(windows)]
fn is_foreign_absolute_path(_value: &str) -> bool {
    // Windows accepts `/rooted` as drive-root-relative and `//server/share`
    // as UNC. V1 has no source-host marker, so those spellings cannot be
    // distinguished from Unix absolute paths without breaking Python parity.
    false
}

fn same_resolved_path(left: &Path, right: &Path) -> bool {
    resolved_identity(left) == resolved_identity(right)
}

fn resolved_identity(path: &Path) -> PathBuf {
    fs::canonicalize(path).unwrap_or_else(|_| absolute_native_path(path))
}

fn absolute_native_path(path: &Path) -> PathBuf {
    std::path::absolute(path).unwrap_or_else(|_| path.to_path_buf())
}

fn sha256_file(path: &Path) -> Result<String, io::Error> {
    let mut file = fs::File::open(path)?;
    let mut digest = Sha256::new();
    let mut buffer = vec![0_u8; 1024 * 1024];
    loop {
        let count = file.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        digest.update(&buffer[..count]);
    }
    Ok(format!("{:x}", digest.finalize()))
}

fn sha256_bytes(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

type CsvRow = BTreeMap<String, String>;

fn read_csv_rows(path: &Path) -> Result<Vec<CsvRow>, csv::Error> {
    let mut reader = csv::ReaderBuilder::new().flexible(true).from_path(path)?;
    let headers: Vec<String> = reader
        .headers()?
        .iter()
        .enumerate()
        .map(|(index, header)| {
            if index == 0 {
                header.trim_start_matches('\u{feff}').to_owned()
            } else {
                header.to_owned()
            }
        })
        .collect();
    let mut rows = Vec::new();
    for record in reader.records() {
        let record = record?;
        let mut row = BTreeMap::new();
        for (index, header) in headers.iter().enumerate() {
            if let Some(value) = record.get(index) {
                row.insert(header.clone(), value.to_owned());
            }
        }
        rows.push(row);
    }
    Ok(rows)
}

fn row_value<'a>(row: &'a CsvRow, names: &[&str], default: &'a str) -> &'a str {
    for name in names {
        if let Some(value) = row.get(*name).filter(|value| !value.is_empty()) {
            return value;
        }
    }
    default
}
