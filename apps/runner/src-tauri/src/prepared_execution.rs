use std::sync::Arc;

use pps_runner_execution::{
    compile_verified_block_schedule, BlockEventSchedule, BlockScheduleOptions,
    BlockScheduleSummary, ExecutionError, JSON_MAX_SAFE_INTEGER, MAX_SCHEDULE_ENCODED_BYTES,
};
use pps_session_package::{
    verify_prepared_session, VerificationError, VerificationRequest, VerifiedPreparedSession,
};
use serde::Serialize;
use serde_json::Value;

const INSPECTION_SCOPE: &str = "schedule-only";
const TIMING_QUALIFICATION: &str = "unqualified";
pub(crate) const MAX_PREPARED_EXECUTION_ENCODED_BYTES: u64 = MAX_SCHEDULE_ENCODED_BYTES as u64;

/// Browser-safe facts about a single compiled block schedule.
///
/// The raw schedule deliberately remains in [`CompiledPreparedExecution`]
/// because its V1-compatible event payloads contain native filesystem paths.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PreparedExecutionBlockSummary {
    pub inspection_scope: &'static str,
    pub timing_qualification: &'static str,
    pub executable: bool,
    #[serde(flatten)]
    pub schedule: BlockScheduleSummary,
}

/// Path-free aggregate returned by the native inspection command.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PreparedExecutionSummary {
    pub inspection_scope: &'static str,
    pub timing_qualification: &'static str,
    pub executable: bool,
    pub block_count: u32,
    pub trial_row_count: u64,
    pub event_count: u64,
    pub encoded_bytes: u64,
    pub blocks: Vec<PreparedExecutionBlockSummary>,
}

/// Native snapshot captured when one schedule inspection begins.
pub(crate) struct PreparedExecutionSource {
    pub generation: u64,
    pub fingerprint: String,
    pub receipt: Arc<VerifiedPreparedSession>,
}

/// Native-only compiled schedules plus the package fence they belong to.
///
/// This type intentionally does not implement `Serialize`. Each schedule owns
/// V1-compatible path-bearing event payloads and is not executable until a
/// separately qualified scheduler/audio/logging adapter adopts it.
#[derive(Debug)]
pub(crate) struct CompiledPreparedExecution {
    pub generation: u64,
    pub fingerprint: String,
    schedules: Vec<BlockEventSchedule>,
    summary: PreparedExecutionSummary,
}

impl CompiledPreparedExecution {
    pub fn summary(&self) -> &PreparedExecutionSummary {
        &self.summary
    }

    pub(crate) fn schedules(&self) -> &[BlockEventSchedule] {
        &self.schedules
    }
}

/// Stable path-free failure returned by the native preparation service.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct PreparedExecutionError {
    code: String,
    public_message: &'static str,
}

impl PreparedExecutionError {
    fn new(code: impl Into<String>, public_message: &'static str) -> Self {
        Self {
            code: code.into(),
            public_message,
        }
    }

    pub fn code(&self) -> &str {
        &self.code
    }

    pub const fn public_message(&self) -> &'static str {
        self.public_message
    }

    fn package_changed() -> Self {
        Self::new(
            "prepared_package_changed",
            "The prepared package changed after selection; select it again before inspection.",
        )
    }

    fn manifest_order_mismatch() -> Self {
        Self::new(
            "prepared_execution_manifest_mismatch",
            "The verified package block order is inconsistent.",
        )
    }

    fn trial_count_mismatch() -> Self {
        Self::new(
            "prepared_execution_trial_count_mismatch",
            "A compiled block row count does not match the prepared package.",
        )
    }

    fn summary_too_large() -> Self {
        Self::new(
            "prepared_execution_summary_too_large",
            "The prepared execution summary is too large.",
        )
    }

    fn package_too_large() -> Self {
        Self::new(
            "prepared_execution_package_too_large",
            "The prepared execution schedules exceed the native inspection limit.",
        )
    }
}

impl From<VerificationError> for PreparedExecutionError {
    fn from(error: VerificationError) -> Self {
        Self::new(error.code(), error.public_message())
    }
}

impl From<ExecutionError> for PreparedExecutionError {
    fn from(error: ExecutionError) -> Self {
        Self::new(error.code(), error.public_message())
    }
}

/// Reverify and compile a retained prepared session without executing it.
pub(crate) fn compile_prepared_execution(
    source: PreparedExecutionSource,
) -> Result<CompiledPreparedExecution, PreparedExecutionError> {
    compile_prepared_execution_with_budget(source, MAX_PREPARED_EXECUTION_ENCODED_BYTES)
}

fn compile_prepared_execution_with_budget(
    source: PreparedExecutionSource,
    maximum_encoded_bytes: u64,
) -> Result<CompiledPreparedExecution, PreparedExecutionError> {
    let mut request = VerificationRequest::new(source.receipt.manifest_path())
        .with_participant_id(&source.receipt.summary().participant_id);
    if let Some(run_setup) = source.receipt.run_setup_manifest() {
        request = request.with_run_setup(run_setup.path());
    }
    let reverified = verify_prepared_session(request)?;

    // The digest is the reducer-facing package identity. Full receipt equality
    // additionally detects changed native provenance resolved from the same
    // manifest bytes before any path-bearing schedule is compiled.
    if reverified.manifest_sha256() != source.fingerprint || &reverified != source.receipt.as_ref()
    {
        return Err(PreparedExecutionError::package_changed());
    }

    compile_reverified_execution(source, reverified, maximum_encoded_bytes)
}

fn compile_reverified_execution(
    source: PreparedExecutionSource,
    reverified: VerifiedPreparedSession,
    maximum_encoded_bytes: u64,
) -> Result<CompiledPreparedExecution, PreparedExecutionError> {
    let package_summary = reverified.summary();
    if package_summary.blocks.len() != reverified.blocks().len() {
        return Err(PreparedExecutionError::manifest_order_mismatch());
    }

    let initial_capacity = package_summary.blocks.len().min(64);
    let mut schedules = Vec::with_capacity(initial_capacity);
    let mut block_summaries = Vec::with_capacity(initial_capacity);
    let mut trial_row_count = 0_u64;
    let mut event_count = 0_u64;
    let mut encoded_bytes = 0_u64;

    // This zip is deliberately manifest-order preserving. Do not key schedules
    // by block index: V1 permits labels/order independent of index uniqueness.
    for (declared, native) in package_summary.blocks.iter().zip(reverified.blocks()) {
        let mut options = BlockScheduleOptions::new(declared.index);
        options.block_label = declared.label.clone();
        options.block_wav_path = Some(native.wav_path().to_path_buf());
        options.participant_id = package_summary.participant_id.clone();
        options.session_id = package_summary.session_id.clone();
        options.part_number = native
            .metadata()
            .get("part_number")
            .cloned()
            .unwrap_or_else(|| Value::String(String::new()));
        options.sample_rate = metadata_i64(native.metadata().get("sample_rate_hz"));
        options.block_metadata = native.metadata().clone();

        // CSV identity is bound separately from the top-level package digest.
        // This call reads once, hashes those exact bounded bytes against the
        // selection receipt, and parses only that owned snapshot. WAV bytes are
        // deliberately not bound here: this inspection is non-executable and
        // media identity/decoding belongs to the later audio qualification.
        let schedule = compile_verified_block_schedule(
            native.manifest_path(),
            native.manifest_sha256(),
            options,
        )?;
        if i64::from(schedule.summary().trial_row_count) != declared.trial_count {
            return Err(PreparedExecutionError::trial_count_mismatch());
        }

        trial_row_count = checked_summary_add(
            trial_row_count,
            u64::from(schedule.summary().trial_row_count),
        )?;
        event_count = checked_summary_add(event_count, u64::from(schedule.summary().event_count))?;
        encoded_bytes = checked_package_schedule_bytes(
            encoded_bytes,
            u64::from(schedule.summary().encoded_bytes),
            maximum_encoded_bytes,
        )?;
        block_summaries.push(PreparedExecutionBlockSummary {
            inspection_scope: INSPECTION_SCOPE,
            timing_qualification: TIMING_QUALIFICATION,
            executable: false,
            schedule: schedule.summary().clone(),
        });
        schedules.push(schedule);
    }

    let block_count =
        u32::try_from(schedules.len()).map_err(|_| PreparedExecutionError::summary_too_large())?;
    Ok(CompiledPreparedExecution {
        generation: source.generation,
        fingerprint: source.fingerprint,
        schedules,
        summary: PreparedExecutionSummary {
            inspection_scope: INSPECTION_SCOPE,
            timing_qualification: TIMING_QUALIFICATION,
            executable: false,
            block_count,
            trial_row_count,
            event_count,
            encoded_bytes,
            blocks: block_summaries,
        },
    })
}

fn metadata_i64(value: Option<&Value>) -> i64 {
    let parsed = match value {
        Some(Value::Number(number)) => number.as_f64(),
        Some(Value::String(text)) => text.trim().parse::<f64>().ok(),
        _ => None,
    };
    parsed
        .filter(|number| number.is_finite())
        .map(f64::trunc)
        .filter(|number| *number >= i64::MIN as f64 && *number <= i64::MAX as f64)
        .map(|number| number as i64)
        .unwrap_or_default()
}

fn checked_summary_add(left: u64, right: u64) -> Result<u64, PreparedExecutionError> {
    left.checked_add(right)
        .filter(|value| *value <= JSON_MAX_SAFE_INTEGER as u64)
        .ok_or_else(PreparedExecutionError::summary_too_large)
}

fn checked_package_schedule_bytes(
    left: u64,
    right: u64,
    maximum: u64,
) -> Result<u64, PreparedExecutionError> {
    left.checked_add(right)
        .filter(|value| *value <= maximum)
        .ok_or_else(PreparedExecutionError::package_too_large)
}

#[cfg(test)]
mod tests {
    use std::{
        fs,
        path::{Path, PathBuf},
        sync::{
            atomic::{AtomicU64, Ordering},
            Arc,
        },
    };

    use serde_json::json;

    use super::*;

    static FIXTURE_SEQUENCE: AtomicU64 = AtomicU64::new(1);

    struct PreparedFixture {
        root: PathBuf,
        manifest_path: PathBuf,
        second_manifest_path: PathBuf,
    }

    impl Drop for PreparedFixture {
        fn drop(&mut self) {
            let temp_root = std::env::temp_dir();
            let has_prefix = self
                .root
                .file_name()
                .and_then(|name| name.to_str())
                .is_some_and(|name| name.starts_with("pps-tauri-inspection-"));
            if self.root.starts_with(&temp_root) && has_prefix {
                let _ = fs::remove_dir_all(&self.root);
            }
        }
    }

    fn write(path: &Path, bytes: impl AsRef<[u8]>) {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).unwrap();
        }
        fs::write(path, bytes).unwrap();
    }

    fn fixture(second_declared_trial_count: i64) -> PreparedFixture {
        let sequence = FIXTURE_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let root = std::env::temp_dir().join(format!(
            "pps-tauri-inspection-{}-{sequence}",
            std::process::id()
        ));
        fs::create_dir_all(&root).unwrap();
        let first_manifest_path = root.join("blocks/first.csv");
        let second_manifest_path = root.join("blocks/second.csv");
        write(
            &first_manifest_path,
            b"Trial_Number,Trial_UID,Trial_Type,Family,Sample_Rate_Hz,Trial_Start_Sample,Trial_End_Sample\n1,B09_T01,Audio-Tactile,audio_tactile,1000,0,8000\n",
        );
        write(
            &second_manifest_path,
            b"Trial_Number,Trial_UID,Trial_Type,Family,Sample_Rate_Hz,Trial_Start_Sample,Trial_End_Sample\n1,B03_T01,Auditory-Only,auditory_only,2000,0,16000\n2,B03_T02,Catch,catch,2000,16000,32000\n",
        );
        write(&root.join("blocks/first.wav"), b"native first WAV bytes");
        write(&root.join("blocks/second.wav"), b"native second WAV bytes");
        let manifest_path = root.join("session_manifest.json");
        let manifest = json!({
            "schema": "pps-run-session.v1",
            "participant_id": "P001",
            "session_id": "P001_inspection_fixture",
            "session_dir": root,
            "execution_mode": "design_schedule_blocks",
            "blocks": [
                {
                    "index": 9,
                    "label": "First in manifest",
                    "manifest_path": "blocks/first.csv",
                    "wav_path": "blocks/first.wav",
                    "trial_count": 1,
                    "duration_s": 8.0,
                    "metadata": {
                        "sample_rate_hz": 1000,
                        "part_number": 1,
                        "native_provenance_path": root.join("private/source-one.csv")
                    }
                },
                {
                    "index": 3,
                    "label": "Second in manifest",
                    "manifest_path": "blocks/second.csv",
                    "wav_path": "blocks/second.wav",
                    "trial_count": second_declared_trial_count,
                    "duration_s": 16.0,
                    "metadata": {"sample_rate_hz": "2000", "part_number": "1"}
                }
            ]
        });
        write(
            &manifest_path,
            serde_json::to_vec_pretty(&manifest).unwrap(),
        );
        PreparedFixture {
            root,
            manifest_path,
            second_manifest_path,
        }
    }

    fn source(fixture: &PreparedFixture, generation: u64) -> PreparedExecutionSource {
        let receipt = Arc::new(
            verify_prepared_session(VerificationRequest::new(&fixture.manifest_path)).unwrap(),
        );
        PreparedExecutionSource {
            generation,
            fingerprint: receipt.manifest_sha256().to_owned(),
            receipt,
        }
    }

    #[test]
    fn compiles_in_manifest_order_and_only_projects_unqualified_path_free_summaries() {
        let fixture = fixture(2);
        let compiled = compile_prepared_execution(source(&fixture, 7)).unwrap();
        let summary = compiled.summary();

        assert_eq!(compiled.generation, 7);
        assert_eq!(compiled.schedules().len(), 2);
        assert_eq!(summary.inspection_scope, "schedule-only");
        assert_eq!(summary.timing_qualification, "unqualified");
        assert!(!summary.executable);
        assert_eq!(summary.block_count, 2);
        assert_eq!(summary.trial_row_count, 3);
        assert_eq!(
            summary.encoded_bytes,
            summary
                .blocks
                .iter()
                .map(|block| u64::from(block.schedule.encoded_bytes))
                .sum::<u64>()
        );
        assert!(summary.encoded_bytes <= MAX_PREPARED_EXECUTION_ENCODED_BYTES);
        assert_eq!(
            summary
                .blocks
                .iter()
                .map(|block| block.schedule.block_index)
                .collect::<Vec<_>>(),
            [9, 3]
        );
        assert!(summary.blocks.iter().all(|block| {
            block.inspection_scope == "schedule-only"
                && block.timing_qualification == "unqualified"
                && !block.executable
        }));

        let wire = serde_json::to_string(summary).unwrap();
        assert!(!wire.contains(fixture.root.to_string_lossy().as_ref()));
        assert!(!wire.contains("manifestPath"));
        assert!(!wire.contains("wavPath"));
        assert!(!wire.contains("native_provenance_path"));

        let raw_payload = &compiled.schedules()[0].events()[0].payload;
        assert!(raw_payload["manifest_path"]
            .as_str()
            .is_some_and(|path| Path::new(path).is_absolute() && path.contains("first.csv")));
        assert!(raw_payload["block_native_provenance_path"]
            .as_str()
            .is_some_and(|path| path.contains("private")));
    }

    #[test]
    fn reverification_rejects_manifest_changes_after_native_selection() {
        let fixture = fixture(2);
        let source = source(&fixture, 1);
        let mut changed = fs::read(&fixture.manifest_path).unwrap();
        changed.push(b'\n');
        fs::write(&fixture.manifest_path, changed).unwrap();

        let error = compile_prepared_execution(source).unwrap_err();
        assert_eq!(error.code(), "prepared_package_changed");
        assert!(!error.public_message().contains("pps-tauri-inspection"));
    }

    #[test]
    fn exact_csv_identity_rejects_same_row_count_mutation_after_reverification() {
        let fixture = fixture(2);
        let source = source(&fixture, 1);
        let reverified =
            verify_prepared_session(VerificationRequest::new(source.receipt.manifest_path()))
                .unwrap();
        assert_eq!(&reverified, source.receipt.as_ref());

        // Simulate replacement in the narrow interval after package
        // reverification but before schedule compilation. Row count remains
        // identical so count-only fencing cannot detect this mutation.
        write(
            &fixture.second_manifest_path,
            b"Trial_Number,Trial_UID,Trial_Type,Family,Sample_Rate_Hz,Trial_Start_Sample,Trial_End_Sample\n1,MUTATED_1,Auditory-Only,auditory_only,2000,0,16000\n2,MUTATED_2,Catch,catch,2000,16000,32000\n",
        );

        let error =
            compile_reverified_execution(source, reverified, MAX_PREPARED_EXECUTION_ENCODED_BYTES)
                .unwrap_err();
        assert_eq!(error.code(), "manifest_identity_mismatch");
        assert_eq!(
            error.public_message(),
            "The block manifest changed after package selection."
        );
        assert!(!error.public_message().contains("pps-tauri-inspection"));
    }

    #[test]
    fn declared_trial_count_must_match_the_compiled_csv_rows() {
        let fixture = fixture(1);
        let error = compile_prepared_execution(source(&fixture, 1)).unwrap_err();
        assert_eq!(error.code(), "prepared_execution_trial_count_mismatch");
    }

    #[test]
    fn package_wide_byte_budget_rejects_individually_valid_block_schedules() {
        let fixture = fixture(2);
        let individually_valid = compile_prepared_execution(source(&fixture, 1)).unwrap();
        let first_block_bytes = u64::from(
            individually_valid.summary().blocks[0]
                .schedule
                .encoded_bytes,
        );
        assert!(first_block_bytes > 0);
        assert!(
            individually_valid.summary().blocks[1]
                .schedule
                .encoded_bytes
                > 0
        );

        let error = compile_prepared_execution_with_budget(source(&fixture, 1), first_block_bytes)
            .unwrap_err();
        assert_eq!(error.code(), "prepared_execution_package_too_large");
        assert!(!error.public_message().contains("pps-tauri-inspection"));
    }

    #[test]
    fn reverification_failures_keep_native_paths_out_of_public_errors() {
        let fixture = fixture(2);
        let source = source(&fixture, 1);
        fs::remove_file(&fixture.second_manifest_path).unwrap();

        let error = compile_prepared_execution(source).unwrap_err();
        assert_eq!(error.code(), "block_manifest_missing");
        assert!(!error.public_message().contains("pps-tauri-inspection"));
    }
}
