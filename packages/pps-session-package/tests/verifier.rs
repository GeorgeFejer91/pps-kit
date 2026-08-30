use std::{
    fs,
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
};

use pps_session_package::{
    verify_prepared_session, VerificationErrorCode, VerificationRequest,
    PARTICIPANT_BLOCK_WAVS_MODE, RUN_PACKAGE_SCHEMA, VERIFIED_MESSAGE,
};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

static TEST_DIRECTORY_SEQUENCE: AtomicU64 = AtomicU64::new(1);

struct TestDirectory {
    path: PathBuf,
}

impl TestDirectory {
    fn new() -> Self {
        let sequence = TEST_DIRECTORY_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "pps-session-package-test-{}-{sequence}",
            std::process::id()
        ));
        fs::create_dir_all(&path).expect("create synthetic fixture root");
        Self { path }
    }

    fn join(&self, path: impl AsRef<Path>) -> PathBuf {
        self.path.join(path)
    }
}

impl Drop for TestDirectory {
    fn drop(&mut self) {
        let temp_root = std::env::temp_dir();
        let has_test_prefix = self
            .path
            .file_name()
            .and_then(|name| name.to_str())
            .is_some_and(|name| name.starts_with("pps-session-package-test-"));
        if self.path.starts_with(&temp_root) && has_test_prefix {
            let _ = fs::remove_dir_all(&self.path);
        }
    }
}

fn write(path: &Path, bytes: impl AsRef<[u8]>) {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).expect("create fixture parent");
    }
    fs::write(path, bytes).expect("write fixture");
}

fn write_json(path: &Path, value: &Value) {
    write(
        path,
        serde_json::to_vec_pretty(value).expect("serialize fixture"),
    );
}

fn sha256(path: &Path) -> String {
    format!(
        "{:x}",
        Sha256::digest(fs::read(path).expect("read hash fixture"))
    )
}

fn legacy_fixture(root: &TestDirectory) -> PathBuf {
    let session_dir = root.join("session");
    let block_manifest = session_dir.join("blocks/block.csv");
    let block_wav = session_dir.join("blocks/block.wav");
    write(&block_manifest, b"trial\n1\n");
    write(&block_wav, b"synthetic wav bytes");
    let manifest_path = root.join("runner_logs/session_manifest.json");
    write_json(
        &manifest_path,
        &json!({
            "schema": RUN_PACKAGE_SCHEMA,
            "participant_id": "P001",
            "session_id": "P001_fixture",
            "session_group_id": "group_fixture",
            "part_number": " 2.9 ",
            "part_session_id": "P001_fixture_part_02",
            "session_dir": session_dir,
            "execution_mode": "design_schedule_blocks",
            "unknown_root_field_is_v1_compatible": true,
            "blocks": [{
                "index": 2,
                "label": "Second condition",
                "manifest_path": "blocks/block.csv",
                "wav_path": "blocks/block.wav",
                "trial_count": 1,
                "duration_s": 1.25,
                "unknown_block_field_is_v1_compatible": true
            }]
        }),
    );
    manifest_path
}

struct ParticipantFixture {
    manifest_path: PathBuf,
    run_setup_path: PathBuf,
    source_csv: PathBuf,
    trial_one: PathBuf,
}

fn participant_fixture(root: &TestDirectory, topup_marker: Option<Value>) -> ParticipantFixture {
    let setup_dir = root.join("design/6_experiment_run_setup");
    let run_setup_path = setup_dir.join("experiment_run_setup_manifest.json");
    write(&run_setup_path, b"{\"schema\":\"synthetic-segment-6\"}\n");

    let trial_one = setup_dir.join("trials/trial,one.wav");
    let trial_two = setup_dir.join("trials/trial_two.wav");
    write(&trial_one, b"trial one bytes");
    write(&trial_two, b"trial two bytes");
    let trial_one_hash = sha256(&trial_one);
    let trial_two_hash = sha256(&trial_two);

    let source_csv = setup_dir.join("source_block.csv");
    write(
        &source_csv,
        format!(
            "\u{feff}block_trial_index,Trial_File_Path,Source_SHA256\r\n 2 ,trials/trial_two.wav,{trial_two_hash}\r\n 1 ,\"trials/trial,one.wav\",{trial_one_hash}\r\n"
        ),
    );

    let session_dir = root.join("prepared/P001_fixture");
    let prepared_csv = session_dir.join("blocks/block_01.csv");
    write(
        &prepared_csv,
        format!("Source_SHA256\n{trial_one_hash}\n{trial_two_hash}\n"),
    );
    write(
        &session_dir.join("blocks/block_01.wav"),
        b"prepared block wav bytes",
    );

    let mut metadata = json!({
        "source_block_csv_path": "source_block.csv",
        "source_block_csv_sha256": sha256(&source_csv)
    });
    if let Some(marker) = topup_marker {
        metadata["is_topup_block"] = marker;
        metadata
            .as_object_mut()
            .expect("metadata object")
            .remove("source_block_csv_path");
        metadata
            .as_object_mut()
            .expect("metadata object")
            .remove("source_block_csv_sha256");
    }

    let manifest_path = root.join("runner_logs/P001_fixture/session_manifest.json");
    write_json(
        &manifest_path,
        &json!({
            "schema": RUN_PACKAGE_SCHEMA,
            "participant_id": "P001",
            "session_id": "P001_fixture",
            "session_dir": session_dir,
            "execution_mode": PARTICIPANT_BLOCK_WAVS_MODE,
            "source_run_setup_manifest_path": run_setup_path,
            "source_run_setup_sha256": sha256(&run_setup_path),
            "blocks": [{
                "index": 1,
                "label": "Prepared block",
                "manifest_path": "blocks/block_01.csv",
                "wav_path": "blocks/block_01.wav",
                "trial_count": 2,
                "duration_s": 2.5,
                "metadata": metadata
            }]
        }),
    );

    ParticipantFixture {
        manifest_path,
        run_setup_path,
        source_csv,
        trial_one,
    }
}

#[test]
fn legacy_package_returns_an_ordered_path_free_camel_case_summary() {
    let root = TestDirectory::new();
    let manifest = legacy_fixture(&root);

    let verified =
        verify_prepared_session(VerificationRequest::new(&manifest).with_participant_id("P001"))
            .expect("legacy package should verify");

    assert_eq!(verified.v1_message(), VERIFIED_MESSAGE);
    assert_eq!(verified.summary().blocks[0].index, 2);
    assert_eq!(verified.summary().blocks[0].label, "Second condition");
    assert_eq!(verified.summary().part_number, Some(2));
    assert_eq!(verified.manifest_sha256().len(), 64);
    assert_eq!(verified.blocks().len(), 1);

    let serialized = serde_json::to_value(verified.summary()).expect("serialize safe summary");
    assert_eq!(serialized["sessionId"], "P001_fixture");
    assert_eq!(serialized["partNumber"], 2);
    assert_eq!(serialized["blocks"][0]["trialCount"], 1);
    assert_eq!(serialized["blocks"][0]["durationS"], 1.25);
    let wire = serialized.to_string();
    assert!(!wire.contains("manifestPath"));
    assert!(!wire.contains("wavPath"));
    assert!(!wire.contains("sha256"));
    assert!(!wire.contains(&root.path.to_string_lossy().to_string()));
}

#[test]
fn participant_block_package_verifies_hashes_aliases_bom_quotes_and_stable_order() {
    let root = TestDirectory::new();
    let fixture = participant_fixture(&root, None);

    let verified = verify_prepared_session(
        VerificationRequest::new(&fixture.manifest_path)
            .with_run_setup(&fixture.run_setup_path)
            .with_participant_id("P001"),
    )
    .expect("participant package should verify");

    let run_setup = verified
        .run_setup_manifest()
        .expect("participant package binds run setup");
    assert_eq!(run_setup.sha256(), sha256(&fixture.run_setup_path));
    let block = &verified.blocks()[0];
    assert_eq!(
        block
            .source_block_csv()
            .expect("source CSV receipt")
            .sha256(),
        sha256(&fixture.source_csv)
    );
    assert_eq!(block.source_trial_wavs().len(), 2);
    assert!(block.source_trial_wavs()[0]
        .path()
        .ends_with("trial,one.wav"));
    assert!(block.source_trial_wavs()[1]
        .path()
        .ends_with("trial_two.wav"));
}

#[test]
fn exact_v1_first_failure_order_checks_participant_then_setup_then_block_files() {
    let root = TestDirectory::new();
    let manifest = legacy_fixture(&root);
    let other_setup = root.join("other/setup.json");
    write(&other_setup, b"{}");

    let participant_error = verify_prepared_session(
        VerificationRequest::new(&manifest)
            .with_run_setup(&other_setup)
            .with_participant_id("P999"),
    )
    .expect_err("participant mismatch should win");
    assert_eq!(
        participant_error.kind(),
        VerificationErrorCode::ParticipantMismatch
    );
    assert_eq!(
        participant_error.to_string(),
        "Prepared session participant does not match."
    );

    let setup_error = verify_prepared_session(
        VerificationRequest::new(&manifest)
            .with_run_setup(&other_setup)
            .with_participant_id("P001"),
    )
    .expect_err("setup identity mismatch should precede blocks");
    assert_eq!(setup_error.kind(), VerificationErrorCode::RunSetupMismatch);

    let data: Value = serde_json::from_slice(&fs::read(&manifest).expect("read manifest"))
        .expect("parse manifest");
    let session_dir = PathBuf::from(data["session_dir"].as_str().expect("session dir"));
    fs::remove_file(session_dir.join("blocks/block.wav")).expect("remove exact test WAV");
    fs::remove_file(session_dir.join("blocks/block.csv")).expect("remove exact test CSV");
    let wav_error = verify_prepared_session(VerificationRequest::new(&manifest))
        .expect_err("WAV existence is checked before CSV existence");
    assert_eq!(wav_error.kind(), VerificationErrorCode::BlockWavMissing);
    assert!(wav_error
        .to_string()
        .starts_with("Prepared block WAV is missing: "));
    assert!(!wav_error
        .public_message()
        .contains(&root.path.to_string_lossy().to_string()));
}

#[test]
fn source_run_setup_drift_precedes_source_csv_and_trial_drift() {
    let root = TestDirectory::new();
    let fixture = participant_fixture(&root, None);
    write(&fixture.run_setup_path, b"changed setup bytes");
    write(&fixture.source_csv, b"changed source CSV bytes");
    write(&fixture.trial_one, b"changed trial bytes");

    let error = verify_prepared_session(
        VerificationRequest::new(&fixture.manifest_path).with_run_setup(&fixture.run_setup_path),
    )
    .expect_err("setup hash is the first freshness gate");

    assert_eq!(error.kind(), VerificationErrorCode::SourceRunSetupStale);
    assert_eq!(
        error.to_string(),
        "Prepared session is stale because the Segment 6 run setup changed."
    );
}

#[test]
fn source_csv_and_trial_hash_drift_have_distinct_stable_codes() {
    let root = TestDirectory::new();
    let fixture = participant_fixture(&root, None);
    write(&fixture.source_csv, b"changed source CSV bytes");
    let csv_error = verify_prepared_session(
        VerificationRequest::new(&fixture.manifest_path).with_run_setup(&fixture.run_setup_path),
    )
    .expect_err("source CSV hash drift should reject");
    assert_eq!(csv_error.kind(), VerificationErrorCode::SourceBlockCsvStale);
    assert_eq!(csv_error.code(), "source_block_csv_stale");

    let root = TestDirectory::new();
    let fixture = participant_fixture(&root, None);
    write(&fixture.trial_one, b"changed trial bytes");
    let trial_error = verify_prepared_session(
        VerificationRequest::new(&fixture.manifest_path).with_run_setup(&fixture.run_setup_path),
    )
    .expect_err("trial hash drift should reject");
    assert_eq!(
        trial_error.kind(),
        VerificationErrorCode::SourceTrialWavStale
    );
    assert_eq!(trial_error.code(), "source_trial_wav_stale");
    assert!(!trial_error
        .public_message()
        .contains(&root.path.to_string_lossy().to_string()));
}

#[test]
fn python_truthy_topup_marker_skips_source_provenance_even_when_text_is_false() {
    let root = TestDirectory::new();
    let fixture = participant_fixture(&root, Some(json!("false")));

    let verified = verify_prepared_session(
        VerificationRequest::new(&fixture.manifest_path).with_run_setup(&fixture.run_setup_path),
    )
    .expect("nonempty string is truthy in the V1 Python oracle");

    assert!(verified.blocks()[0].source_block_csv().is_none());
    assert!(verified.blocks()[0].source_trial_wavs().is_empty());
}

#[test]
fn missing_source_hash_keeps_the_v1_regeneration_message() {
    let root = TestDirectory::new();
    let fixture = participant_fixture(&root, None);
    let mut manifest: Value = serde_json::from_slice(
        &fs::read(&fixture.manifest_path).expect("read participant manifest"),
    )
    .expect("parse participant manifest");
    manifest["source_run_setup_sha256"] = json!("");
    write_json(&fixture.manifest_path, &manifest);

    let error = verify_prepared_session(
        VerificationRequest::new(&fixture.manifest_path).with_run_setup(&fixture.run_setup_path),
    )
    .expect_err("legacy source-hash omission should reject");

    assert_eq!(
        error.kind(),
        VerificationErrorCode::SourceRunSetupHashMissing
    );
    assert_eq!(
        error.to_string(),
        "Prepared session was created before source-hash tracking; regenerate audio assets."
    );
}

#[test]
fn malformed_or_unknown_schema_is_never_accepted() {
    let root = TestDirectory::new();
    let malformed = root.join("malformed/session_manifest.json");
    write(&malformed, b"not json");
    let error = verify_prepared_session(VerificationRequest::new(&malformed))
        .expect_err("malformed JSON follows V1 unsupported-manifest behavior");
    assert_eq!(error.kind(), VerificationErrorCode::UnsupportedSchema);
    assert_eq!(error.code(), "unsupported_schema");
    assert_eq!(
        error.to_string(),
        format!("Unsupported run package manifest: {}", malformed.display())
    );

    let missing = root.join("missing/session_manifest.json");
    let error = verify_prepared_session(VerificationRequest::new(&missing))
        .expect_err("missing manifest should reject before parsing");
    assert_eq!(error.kind(), VerificationErrorCode::ManifestMissing);
    assert_eq!(
        error.public_message(),
        "Prepared session manifest is missing."
    );
}

#[cfg(not(windows))]
#[test]
fn foreign_absolute_paths_are_rejected_instead_of_reinterpreted() {
    let root = TestDirectory::new();
    let manifest = root.join("foreign/session_manifest.json");
    let foreign_session_dir = r"C:\pps\session";

    write_json(
        &manifest,
        &json!({
            "schema": RUN_PACKAGE_SCHEMA,
            "participant_id": "P001",
            "session_id": "foreign_fixture",
            "session_dir": foreign_session_dir,
            "execution_mode": "design_schedule_blocks",
            "blocks": [{
                "index": 1,
                "label": "Foreign-host block",
                "manifest_path": "blocks/block.csv",
                "wav_path": "blocks/block.wav",
                "trial_count": 1,
                "duration_s": 1.0
            }]
        }),
    );

    let error = verify_prepared_session(VerificationRequest::new(&manifest))
        .expect_err("foreign absolute paths must fail before native lookup");
    assert_eq!(error.kind(), VerificationErrorCode::ForeignHostPath);
    assert_eq!(error.code(), "foreign_host_path");
    assert!(!error.public_message().contains(foreign_session_dir));
}

#[cfg(not(windows))]
#[test]
fn foreign_source_run_setup_paths_are_rejected_before_lookup_or_hashing() {
    let root = TestDirectory::new();
    let fixture = participant_fixture(&root, None);
    let foreign_run_setup = r"C:\pps\run_setup.json";
    let mut manifest: Value = serde_json::from_slice(
        &fs::read(&fixture.manifest_path).expect("read participant manifest"),
    )
    .expect("parse participant manifest");
    manifest["source_run_setup_manifest_path"] = json!(foreign_run_setup);
    write_json(&fixture.manifest_path, &manifest);

    let error = verify_prepared_session(VerificationRequest::new(&fixture.manifest_path))
        .expect_err("foreign run-setup path must fail before native lookup");
    assert_eq!(error.kind(), VerificationErrorCode::ForeignHostPath);
    assert_eq!(error.code(), "foreign_host_path");
    assert!(!error.public_message().contains(foreign_run_setup));
}
