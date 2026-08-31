//! Pure Rust verification for V1 PPS prepared-session packages.
//!
//! The verifier deliberately has no Tauri, UI, audio, or networking dependency.
//! It preserves the read-only acceptance and first-failure ordering of Python
//! `prepared_session_manifest_current_status`. The serializable summary contains
//! no filesystem paths or hashes; resolved paths and digests remain in the
//! Rust-only [`VerifiedPreparedSession`] receipt.

use std::{
    fmt, fs,
    io::{self, Read, Write},
    path::{Path, PathBuf},
    sync::Arc,
};

use csv::StringRecord;
use serde::Serialize;
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};

pub const RUN_PACKAGE_SCHEMA: &str = "pps-run-session.v1";
pub const PARTICIPANT_BLOCK_WAVS_MODE: &str = "participant_block_wavs";
pub const VERIFIED_MESSAGE: &str = "Prepared local audio package is available.";
pub const MAX_SESSION_MANIFEST_BYTES: usize = 8 * 1024 * 1024;
pub const MAX_PREPARED_BLOCKS: usize = 1_024;
pub const MAX_PREPARED_BLOCK_MANIFEST_BYTES: usize = 8 * 1024 * 1024;
pub const MAX_PREPARED_BLOCK_METADATA_BYTES: usize = 64 * 1024;

const MAX_TOTAL_BLOCK_METADATA_BYTES: usize = 4 * 1024 * 1024;
const MAX_BLOCK_METADATA_FIELDS: usize = 256;
const MAX_BLOCK_METADATA_NODES: usize = 4_096;
const MAX_BLOCK_METADATA_DEPTH: usize = 32;
const MAX_MANIFEST_IDENTITY_BYTES: usize = 1_024;
const MAX_BLOCK_LABEL_BYTES: usize = 1_024;
const MAX_MANIFEST_PATH_BYTES: usize = 32 * 1024;
const MAX_EXECUTION_MODE_BYTES: usize = 256;
const MAX_DIGEST_TEXT_BYTES: usize = 128;
const MAX_CSV_COLUMNS: usize = 256;
const MAX_CSV_ROWS: usize = 100_000;
const MAX_CSV_FIELD_BYTES: usize = 16 * 1024;
const MAX_INITIAL_READ_CAPACITY: usize = 64 * 1024;

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
    manifest_sha256: String,
    wav_path: PathBuf,
    metadata: Map<String, Value>,
    source_block_csv: Option<VerifiedNativeFile>,
    source_trial_wavs: Vec<VerifiedNativeFile>,
}

impl VerifiedPreparedBlock {
    pub fn manifest_path(&self) -> &Path {
        &self.manifest_path
    }

    /// Digest of the exact bounded prepared-CSV bytes observed during native
    /// package selection. A later compiler must compare freshly read bytes to
    /// this identity before parsing them.
    pub fn manifest_sha256(&self) -> &str {
        &self.manifest_sha256
    }

    pub fn wav_path(&self) -> &Path {
        &self.wav_path
    }

    /// Native-only block metadata retained for deterministic schedule
    /// compilation. Metadata may contain filesystem provenance, so callers
    /// must not project this map across a WebView or network boundary.
    pub fn metadata(&self) -> &Map<String, Value> {
        &self.metadata
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
    ManifestTooLarge,
    ManifestResourceLimit,
    UnsupportedSchema,
    ManifestInvalid,
    ForeignHostPath,
    ParticipantMismatch,
    RunSetupMismatch,
    NoBlocks,
    BlockWavMissing,
    BlockManifestMissing,
    BlockManifestTooLarge,
    SourceRunSetupMissing,
    SourceRunSetupUnreadable,
    SourceRunSetupHashMissing,
    SourceRunSetupStale,
    SourceProvenanceMissing,
    SourceBlockCsvMissing,
    SourceBlockCsvUnreadable,
    SourceBlockCsvTooLarge,
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
            Self::ManifestTooLarge => "manifest_too_large",
            Self::ManifestResourceLimit => "manifest_resource_limit",
            Self::UnsupportedSchema => "unsupported_schema",
            Self::ManifestInvalid => "manifest_invalid",
            Self::ForeignHostPath => "foreign_host_path",
            Self::ParticipantMismatch => "participant_mismatch",
            Self::RunSetupMismatch => "run_setup_mismatch",
            Self::NoBlocks => "no_blocks",
            Self::BlockWavMissing => "block_wav_missing",
            Self::BlockManifestMissing => "block_manifest_missing",
            Self::BlockManifestTooLarge => "block_manifest_too_large",
            Self::SourceRunSetupMissing => "source_run_setup_missing",
            Self::SourceRunSetupUnreadable => "source_run_setup_unreadable",
            Self::SourceRunSetupHashMissing => "source_run_setup_hash_missing",
            Self::SourceRunSetupStale => "source_run_setup_stale",
            Self::SourceProvenanceMissing => "source_provenance_missing",
            Self::SourceBlockCsvMissing => "source_block_csv_missing",
            Self::SourceBlockCsvUnreadable => "source_block_csv_unreadable",
            Self::SourceBlockCsvTooLarge => "source_block_csv_too_large",
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

    let manifest_bytes = read_bounded_bytes(manifest_path, MAX_SESSION_MANIFEST_BYTES).map_err(
        |error| match error {
            BoundedReadError::TooLarge => VerificationError::new(
                VerificationErrorCode::ManifestTooLarge,
                "Prepared session manifest is too large.",
                format!(
                    "Prepared session manifest exceeds the {MAX_SESSION_MANIFEST_BYTES}-byte limit: {}",
                    manifest_path.display()
                ),
            ),
            BoundedReadError::Io(_) => unsupported_schema(manifest_path),
        },
    )?;
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
            manifest_sha256: String::new(),
            wav_path: absolute_native_path(&wav_path),
            metadata: block.metadata.clone(),
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

    // V1 checks every WAV/CSV path for existence before source freshness. The
    // additional byte-identity pass therefore runs only after those gates. A
    // participant block that was parsed above already owns its exact digest;
    // top-up and legacy blocks are read once here solely to bind CSV identity.
    for verified_block in &mut verified_blocks {
        if verified_block.manifest_sha256.is_empty() {
            bind_prepared_block_manifest(verified_block)?;
        }
    }

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
    let source_bytes = read_bounded_bytes(&source_csv, MAX_PREPARED_BLOCK_MANIFEST_BYTES)
        .map_err(source_block_csv_read_error)?;
    let source_hash = sha256_bytes(&source_bytes);
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

    let mut source_rows = parse_csv_rows(&source_csv, &source_bytes).map_err(|error| {
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
    let prepared_bytes = read_bounded_bytes(&prepared_csv, MAX_PREPARED_BLOCK_MANIFEST_BYTES)
        .map_err(prepared_block_csv_read_error)?;
    let prepared_hash = sha256_bytes(&prepared_bytes);
    let prepared_rows = parse_csv_rows(&prepared_csv, &prepared_bytes).map_err(|error| {
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

    source_rows.sort_by_key(|row| v1_csv_int(row.value(&["block_trial_index"], "")));
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
    verified_block.manifest_sha256 = prepared_hash;
    verified_block.source_trial_wavs = source_trial_wavs;
    Ok(())
}

fn bind_prepared_block_manifest(
    verified_block: &mut VerifiedPreparedBlock,
) -> Result<(), VerificationError> {
    let bytes = read_bounded_bytes(
        &verified_block.manifest_path,
        MAX_PREPARED_BLOCK_MANIFEST_BYTES,
    )
    .map_err(prepared_block_csv_read_error)?;
    verified_block.manifest_sha256 = sha256_bytes(&bytes);
    Ok(())
}

fn parse_manifest(
    object: &Map<String, Value>,
    manifest_path: &Path,
) -> Result<ParsedManifest, VerificationError> {
    let session_dir = if let Some(value) = object
        .get("session_dir")
        .filter(|value| python_truthy(value))
    {
        PathBuf::from(bounded_python_string(
            value,
            "session_dir",
            MAX_MANIFEST_PATH_BYTES,
        )?)
    } else {
        let fallback = manifest_path
            .parent()
            .unwrap_or_else(|| Path::new(""))
            .to_path_buf();
        ensure_path_byte_limit(&fallback, "session_dir")?;
        fallback
    };
    let participant_id = optional_bounded_python_string(
        object.get("participant_id"),
        "participant_id",
        MAX_MANIFEST_IDENTITY_BYTES,
    )?;
    let session_id = if let Some(value) = object
        .get("session_id")
        .filter(|value| python_truthy(value))
    {
        bounded_python_string(value, "session_id", MAX_MANIFEST_IDENTITY_BYTES)?
    } else {
        let fallback = session_dir
            .file_name()
            .map(|name| name.to_string_lossy().into_owned())
            .unwrap_or_default();
        ensure_string_byte_limit(&fallback, "session_id", MAX_MANIFEST_IDENTITY_BYTES)?;
        fallback
    };
    let session_group_id = optional_bounded_python_string(
        object.get("session_group_id"),
        "session_group_id",
        MAX_MANIFEST_IDENTITY_BYTES,
    )?;
    let part_number = object
        .get("part_number")
        .map(|value| v1_as_int(value, 0))
        .filter(|number| *number != 0);
    let part_session_id = if let Some(value) = object
        .get("part_session_id")
        .filter(|value| python_truthy(value))
    {
        bounded_python_string(value, "part_session_id", MAX_MANIFEST_IDENTITY_BYTES)?
    } else {
        session_id.clone()
    };
    let execution_mode = if let Some(value) = object
        .get("execution_mode")
        .filter(|value| python_truthy(value))
    {
        bounded_python_string(value, "execution_mode", MAX_EXECUTION_MODE_BYTES)?
    } else {
        "design_schedule_blocks".to_owned()
    };
    let source_run_setup_manifest_path = object
        .get("source_run_setup_manifest_path")
        .filter(|value| python_truthy(value))
        .map(|value| {
            bounded_python_string(
                value,
                "source_run_setup_manifest_path",
                MAX_MANIFEST_PATH_BYTES,
            )
            .map(PathBuf::from)
        })
        .transpose()?;
    let source_run_setup_sha256 = object
        .get("source_run_setup_sha256")
        .filter(|value| python_truthy(value))
        .map(|value| bounded_python_string(value, "source_run_setup_sha256", MAX_DIGEST_TEXT_BYTES))
        .transpose()?
        .unwrap_or_default()
        .trim()
        .to_owned();

    let raw_blocks = match object.get("blocks") {
        None => &[][..],
        Some(Value::Array(blocks)) => blocks.as_slice(),
        Some(_) => return Err(invalid_manifest("blocks must be a list")),
    };
    if raw_blocks.len() > MAX_PREPARED_BLOCKS {
        return Err(resource_limit(format!(
            "blocks contains {} entries; the limit is {MAX_PREPARED_BLOCKS}",
            raw_blocks.len()
        )));
    }
    let mut blocks = Vec::with_capacity(raw_blocks.len());
    let mut block_summaries = Vec::with_capacity(raw_blocks.len());
    let mut total_metadata_bytes = 0_usize;
    for raw_block in raw_blocks {
        let (block, metadata_bytes) = parse_block(raw_block)?;
        total_metadata_bytes = total_metadata_bytes
            .checked_add(metadata_bytes)
            .filter(|bytes| *bytes <= MAX_TOTAL_BLOCK_METADATA_BYTES)
            .ok_or_else(|| {
                resource_limit(format!(
                    "block metadata exceeds the {MAX_TOTAL_BLOCK_METADATA_BYTES}-byte cumulative limit"
                ))
            })?;
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

fn parse_block(value: &Value) -> Result<(ParsedBlock, usize), VerificationError> {
    let object = value
        .as_object()
        .ok_or_else(|| invalid_manifest("each block must be an object"))?;
    let index = required_int(object, "index")?;
    let label = required_bounded_python_string(object, "label", MAX_BLOCK_LABEL_BYTES)?;
    let manifest_path = required_path(object, "manifest_path")?;
    let wav_path = required_path(object, "wav_path")?;
    let trial_count = required_int(object, "trial_count")?;
    let duration_s = required_float(object, "duration_s")?;
    let metadata_source = match object.get("metadata") {
        None | Some(Value::Null) | Some(Value::Bool(false)) => None,
        Some(Value::Object(metadata)) => Some(metadata),
        Some(value) if !python_truthy(value) => None,
        Some(_) => return Err(invalid_manifest("block metadata must be an object")),
    };
    let metadata_bytes = metadata_source
        .map(validate_block_metadata)
        .transpose()?
        .unwrap_or(2);
    let metadata = metadata_source.cloned().unwrap_or_default();
    Ok((
        ParsedBlock {
            summary: PreparedBlockSummary {
                index,
                label,
                trial_count,
                duration_s,
            },
            manifest_path,
            wav_path,
            metadata,
        },
        metadata_bytes,
    ))
}

fn required_bounded_python_string(
    object: &Map<String, Value>,
    field: &str,
    maximum_bytes: usize,
) -> Result<String, VerificationError> {
    object
        .get(field)
        .map(|value| bounded_python_string(value, field, maximum_bytes))
        .transpose()?
        .ok_or_else(|| invalid_manifest(format!("block is missing {field}")))
}

fn required_path(object: &Map<String, Value>, field: &str) -> Result<PathBuf, VerificationError> {
    let value = object
        .get(field)
        .ok_or_else(|| invalid_manifest(format!("block is missing {field}")))?;
    let text = value
        .as_str()
        .ok_or_else(|| invalid_manifest(format!("block {field} must be a path string")))?;
    ensure_string_byte_limit(text, field, MAX_MANIFEST_PATH_BYTES)?;
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

fn resource_limit(detail: impl Into<String>) -> VerificationError {
    let detail = detail.into();
    VerificationError::new(
        VerificationErrorCode::ManifestResourceLimit,
        "Prepared session manifest exceeds supported resource limits.",
        format!("Prepared session manifest resource limit exceeded: {detail}"),
    )
}

fn optional_bounded_python_string(
    value: Option<&Value>,
    field: &str,
    maximum_bytes: usize,
) -> Result<String, VerificationError> {
    value
        .map(|value| bounded_python_string(value, field, maximum_bytes))
        .transpose()
        .map(Option::unwrap_or_default)
}

fn bounded_python_string(
    value: &Value,
    field: &str,
    maximum_bytes: usize,
) -> Result<String, VerificationError> {
    if let Value::String(text) = value {
        ensure_string_byte_limit(text, field, maximum_bytes)?;
        return Ok(text.clone());
    }
    if matches!(value, Value::Array(_) | Value::Object(_)) {
        let mut counter = BoundedCountingWriter::new(maximum_bytes);
        serde_json::to_writer(&mut counter, value).map_err(|_| {
            resource_limit(format!(
                "{field} exceeds the {maximum_bytes}-byte encoded limit"
            ))
        })?;
    }
    let text = python_string(value);
    ensure_string_byte_limit(&text, field, maximum_bytes)?;
    Ok(text)
}

fn ensure_string_byte_limit(
    value: &str,
    field: &str,
    maximum_bytes: usize,
) -> Result<(), VerificationError> {
    if value.len() > maximum_bytes {
        return Err(resource_limit(format!(
            "{field} contains {} UTF-8 bytes; the limit is {maximum_bytes}",
            value.len()
        )));
    }
    Ok(())
}

fn ensure_path_byte_limit(path: &Path, field: &str) -> Result<(), VerificationError> {
    let byte_count = path.as_os_str().to_string_lossy().len();
    if byte_count > MAX_MANIFEST_PATH_BYTES {
        return Err(resource_limit(format!(
            "{field} contains {byte_count} path bytes; the limit is {MAX_MANIFEST_PATH_BYTES}"
        )));
    }
    Ok(())
}

fn validate_block_metadata(metadata: &Map<String, Value>) -> Result<usize, VerificationError> {
    if metadata.len() > MAX_BLOCK_METADATA_FIELDS {
        return Err(resource_limit(format!(
            "block metadata contains {} top-level fields; the limit is {MAX_BLOCK_METADATA_FIELDS}",
            metadata.len()
        )));
    }

    let mut nodes = 1_usize;
    for (key, value) in metadata {
        ensure_string_byte_limit(key, "block metadata key", MAX_PREPARED_BLOCK_METADATA_BYTES)?;
        validate_json_shape(value, 1, &mut nodes)?;
    }

    let mut counter = BoundedCountingWriter::new(MAX_PREPARED_BLOCK_METADATA_BYTES);
    serde_json::to_writer(&mut counter, metadata).map_err(|_| {
        resource_limit(format!(
            "block metadata exceeds the {MAX_PREPARED_BLOCK_METADATA_BYTES}-byte encoded limit"
        ))
    })?;
    Ok(counter.count)
}

fn validate_json_shape(
    value: &Value,
    depth: usize,
    nodes: &mut usize,
) -> Result<(), VerificationError> {
    if depth > MAX_BLOCK_METADATA_DEPTH {
        return Err(resource_limit(format!(
            "block metadata exceeds the nesting limit of {MAX_BLOCK_METADATA_DEPTH}"
        )));
    }
    *nodes = nodes.checked_add(1).ok_or_else(|| {
        resource_limit("block metadata node count overflowed the native integer range")
    })?;
    if *nodes > MAX_BLOCK_METADATA_NODES {
        return Err(resource_limit(format!(
            "block metadata exceeds the node limit of {MAX_BLOCK_METADATA_NODES}"
        )));
    }

    match value {
        Value::String(text) => ensure_string_byte_limit(
            text,
            "block metadata string",
            MAX_PREPARED_BLOCK_METADATA_BYTES,
        )?,
        Value::Array(values) => {
            for value in values {
                validate_json_shape(value, depth + 1, nodes)?;
            }
        }
        Value::Object(values) => {
            for (key, value) in values {
                ensure_string_byte_limit(
                    key,
                    "block metadata key",
                    MAX_PREPARED_BLOCK_METADATA_BYTES,
                )?;
                validate_json_shape(value, depth + 1, nodes)?;
            }
        }
        Value::Null | Value::Bool(_) | Value::Number(_) => {}
    }
    Ok(())
}

struct BoundedCountingWriter {
    count: usize,
    maximum: usize,
}

impl BoundedCountingWriter {
    const fn new(maximum: usize) -> Self {
        Self { count: 0, maximum }
    }
}

impl Write for BoundedCountingWriter {
    fn write(&mut self, buffer: &[u8]) -> io::Result<usize> {
        let next = self
            .count
            .checked_add(buffer.len())
            .filter(|count| *count <= self.maximum)
            .ok_or_else(|| io::Error::other("encoded JSON byte limit exceeded"))?;
        self.count = next;
        Ok(buffer.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
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
    ensure_string_byte_limit(text, "resolved package path", MAX_MANIFEST_PATH_BYTES)?;
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
    ensure_path_byte_limit(path, "prepared package path")?;
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

#[derive(Debug)]
enum BoundedReadError {
    Io(io::Error),
    TooLarge,
}

impl fmt::Display for BoundedReadError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(error) => error.fmt(formatter),
            Self::TooLarge => formatter.write_str("file exceeds the configured byte limit"),
        }
    }
}

fn read_bounded_bytes(path: &Path, maximum_bytes: usize) -> Result<Vec<u8>, BoundedReadError> {
    let file = fs::File::open(path).map_err(BoundedReadError::Io)?;
    let observed_length = file.metadata().ok().map(|metadata| metadata.len());
    if observed_length.is_some_and(|length| length > maximum_bytes as u64) {
        return Err(BoundedReadError::TooLarge);
    }

    let initial_capacity = observed_length
        .and_then(|length| usize::try_from(length).ok())
        .unwrap_or_default()
        .min(maximum_bytes)
        .min(MAX_INITIAL_READ_CAPACITY);
    let mut bytes = Vec::with_capacity(initial_capacity);
    file.take((maximum_bytes as u64).saturating_add(1))
        .read_to_end(&mut bytes)
        .map_err(BoundedReadError::Io)?;
    if bytes.len() > maximum_bytes {
        return Err(BoundedReadError::TooLarge);
    }
    Ok(bytes)
}

fn source_block_csv_read_error(error: BoundedReadError) -> VerificationError {
    match error {
        BoundedReadError::TooLarge => VerificationError::new(
            VerificationErrorCode::SourceBlockCsvTooLarge,
            "A prepared block source CSV is too large.",
            format!(
                "Prepared block source CSV exceeds the {MAX_PREPARED_BLOCK_MANIFEST_BYTES}-byte limit"
            ),
        ),
        BoundedReadError::Io(error) => VerificationError::new(
            VerificationErrorCode::SourceBlockCsvUnreadable,
            "A prepared block source CSV cannot be read.",
            format!("Prepared block source CSV cannot be read: {error}"),
        ),
    }
}

fn prepared_block_csv_read_error(error: BoundedReadError) -> VerificationError {
    match error {
        BoundedReadError::TooLarge => VerificationError::new(
            VerificationErrorCode::BlockManifestTooLarge,
            "A prepared block manifest is too large.",
            format!(
                "Prepared block manifest exceeds the {MAX_PREPARED_BLOCK_MANIFEST_BYTES}-byte limit"
            ),
        ),
        BoundedReadError::Io(error) => VerificationError::new(
            VerificationErrorCode::PreparedBlockCsvUnreadable,
            "A prepared block manifest cannot be read.",
            format!("Prepared block manifest cannot be read: {error}"),
        ),
    }
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

impl CsvRow {
    fn value<'a>(&'a self, names: &[&str], default: &'a str) -> &'a str {
        for name in names {
            if let Some(value) = self
                .columns
                .iter()
                .find(|column| column.name == *name)
                .and_then(|column| self.record.get(column.value_index))
                .filter(|value| !value.is_empty())
            {
                return value;
            }
        }
        default
    }
}

fn parse_csv_rows(path: &Path, bytes: &[u8]) -> Result<Vec<CsvRow>, String> {
    let csv_bytes = bytes.strip_prefix(&[0xef, 0xbb, 0xbf]).unwrap_or(bytes);
    let mut reader = csv::ReaderBuilder::new()
        .flexible(true)
        .from_reader(csv_bytes);
    let headers = reader
        .headers()
        .map_err(|error| format!("{}: {error}", path.display()))?
        .clone();
    if headers.len() > MAX_CSV_COLUMNS {
        return Err(format!(
            "{} contains {} columns; the limit is {MAX_CSV_COLUMNS}",
            path.display(),
            headers.len()
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
        if rows.len() >= MAX_CSV_ROWS {
            return Err(format!(
                "{} exceeds the {MAX_CSV_ROWS}-row verification limit",
                path.display()
            ));
        }
        let record = record.map_err(|error| format!("{}: {error}", path.display()))?;
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
) -> Result<(), String> {
    if let Some(value) = values
        .into_iter()
        .find(|value| value.len() > MAX_CSV_FIELD_BYTES)
    {
        return Err(format!(
            "{} contains a {}-byte field; the limit is {MAX_CSV_FIELD_BYTES}",
            path.display(),
            value.len()
        ));
    }
    Ok(())
}

fn row_value<'a>(row: &'a CsvRow, names: &[&str], default: &'a str) -> &'a str {
    row.value(names, default)
}
