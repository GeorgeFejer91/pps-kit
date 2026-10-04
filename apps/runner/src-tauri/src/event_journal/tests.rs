use super::*;
use pps_runner_execution::{EventLedger, LedgerEventInput, LedgerReserve};
use std::{
    fs,
    time::{Duration, Instant},
};

fn prepared(ledger: &EventLedger, time: u64) -> PreparedLedgerBatch {
    ledger
        .prepare_batch(
            [LedgerEventInput::new(
                "response.observed",
                "native-input",
                time,
            )],
            LedgerReserve::NONE,
        )
        .unwrap()
}

fn wait_until(condition: impl Fn() -> bool) {
    let deadline = Instant::now() + Duration::from_secs(3);
    while !condition() {
        assert!(Instant::now() < deadline, "journal worker did not finish");
        thread::sleep(Duration::from_millis(2));
    }
}

#[test]
fn durable_records_preserve_the_authority_schema_and_sequence_without_overwrite() {
    let path = std::env::temp_dir().join(format!("pps-journal-{}.partial.jsonl", random_nonce()));
    let mut journal = NativeEventJournal::open(
        &path,
        br#"{"schema":"test","completion":"partial"}"#.to_vec(),
    )
    .unwrap();
    let mut ledger = EventLedger::default();
    // A journal may begin after earlier setup records, but cannot skip records
    // once installed on this authority.
    ledger
        .append(LedgerEventInput::new("setup.submitted", "local", 1))
        .unwrap();
    for time in 2..=4 {
        let batch = prepared(&ledger, time);
        journal.admit(&batch).unwrap();
        ledger.commit_prepared(batch).unwrap();
    }
    wait_until(|| journal.durable_sequence() == 4);
    let progress = Arc::clone(&journal.progress);
    drop(journal);
    wait_until(|| progress.retired.load(Ordering::Acquire));
    let text = fs::read_to_string(&path).unwrap();
    let lines: Vec<_> = text.lines().collect();
    assert_eq!(lines.len(), 4);
    for (line, record) in lines[1..].iter().zip(&ledger.records()[1..]) {
        let decoded: pps_runner_execution::ExecutionEventRecord =
            serde_json::from_str(line).unwrap();
        assert_eq!(&decoded, record);
    }
    assert!(matches!(
        NativeEventJournal::open(&path, b"replacement".to_vec()),
        Err(JournalError::Unavailable)
    ));
    assert_eq!(fs::read_to_string(&path).unwrap(), text);
    fs::remove_file(path).unwrap();
}

#[test]
fn queue_full_and_sequence_gaps_do_not_advance_admission_or_claim_durability() {
    let (sender, _receive) = mpsc::sync_channel(1);
    let mut journal = NativeEventJournal {
        sender: Some(sender),
        progress: Arc::new(Progress::default()),
        last_enqueued_sequence: None,
        admitted_bytes: 0,
        dataset_enabled: false,
        admitted_dataset_rows: 0,
        first_enqueued_sequence: None,
        admitted_scored_trials: 0,
        interrupted: false,
        publication_enabled: false,
        pending_seal: None,
    };
    let mut ledger = EventLedger::default();
    let first = prepared(&ledger, 1);
    journal.admit(&first).unwrap();
    ledger.commit_prepared(first).unwrap();
    let second = prepared(&ledger, 2);
    assert_eq!(journal.admit(&second), Err(JournalError::QueueFull));
    assert_eq!(journal.last_enqueued_sequence, Some(1));
    assert_eq!(journal.durable_sequence(), 0);
    ledger.commit_prepared(second).unwrap();
    assert_eq!(
        journal.admit(&prepared(&ledger, 3)),
        Err(JournalError::SequenceGap)
    );
}

#[test]
fn file_budget_and_large_batches_are_rejected_before_queue_admission() {
    let (sender, receive) = mpsc::sync_channel(1);
    let mut journal = NativeEventJournal {
        sender: Some(sender),
        progress: Arc::new(Progress::default()),
        last_enqueued_sequence: None,
        admitted_bytes: MAX_FILE_BYTES,
        dataset_enabled: false,
        admitted_dataset_rows: 0,
        first_enqueued_sequence: None,
        admitted_scored_trials: 0,
        interrupted: false,
        publication_enabled: false,
        pending_seal: None,
    };
    let ledger = EventLedger::default();
    assert_eq!(
        journal.admit(&prepared(&ledger, 1)),
        Err(JournalError::ResourceLimit)
    );
    journal.admitted_bytes = 0;
    let batch = ledger
        .prepare_batch(
            (0..=MAX_BATCH_RECORDS).map(|i| LedgerEventInput::new("event", "native", i as u64)),
            LedgerReserve::NONE,
        )
        .unwrap();
    assert_eq!(journal.admit(&batch), Err(JournalError::ResourceLimit));
    assert!(matches!(receive.try_recv(), Err(mpsc::TryRecvError::Empty)));
    assert_eq!(journal.last_enqueued_sequence, None);
}

#[test]
fn io_failure_retains_the_partial_file_and_never_acknowledges_the_batch() {
    let path = std::env::temp_dir().join(format!(
        "pps-journal-fault-{}.partial.jsonl",
        random_nonce()
    ));
    fs::write(&path, b"retained prefix\n").unwrap();
    // A read-only file handle gives a deterministic write failure on every OS,
    // without changing permissions or depending on a full disk.
    let mut journal =
        NativeEventJournal::start_writer(File::open(&path).unwrap(), None, 16).unwrap();
    journal
        .admit(&prepared(&EventLedger::default(), 1))
        .unwrap();
    wait_until(|| journal.failed());
    assert_eq!(journal.durable_sequence(), 0);
    assert_eq!(
        journal.admit(&prepared(&EventLedger::default(), 1)),
        Err(JournalError::Unavailable)
    );
    let progress = Arc::clone(&journal.progress);
    drop(journal);
    wait_until(|| progress.retired.load(Ordering::Acquire));
    assert_eq!(fs::read(&path).unwrap(), b"retained prefix\n");
    fs::remove_file(path).unwrap();
}

#[test]
fn scored_trials_and_minimal_csv_share_one_durable_prefix_and_filler_counter() {
    let stem = std::env::temp_dir().join(format!("pps-dataset-{}", random_nonce()));
    let events = stem.with_extension("partial.jsonl");
    let dataset = stem.with_extension("partial.csv");
    let mut journal =
        NativeEventJournal::open_bundle(&events, Some(&dataset), b"{}".to_vec()).unwrap();
    let mut ledger = EventLedger::default();
    let batch = ledger.prepare_batch((1..=3).map(|number| {
        let mut input = LedgerEventInput::new("trial.scored", "native-output", number);
        input.payload = serde_json::json!({
            "participant_id": "p,\"quoted\"\nvalue", "trial_number": number,
            "trial_type": if number == 2 { "Filler" } else { "Audio-Tactile" },
            "response_given": number == 1, "outcome": if number == 1 { "Hit" } else { "Miss" },
            "rt_ms": if number == 1 { "100.000" } else { "" },
        });
        input
    }), LedgerReserve::NONE).unwrap();
    journal.admit(&batch).unwrap();
    ledger.commit_prepared(batch).unwrap();
    wait_until(|| journal.durable_sequence() == 3 && journal.durable_dataset_rows() == 2);
    let retired = journal.retirement_probe();
    drop(journal);
    wait_until(retired);
    let bytes = fs::read(&dataset).unwrap();
    assert!(bytes.starts_with(
        pps_runner_execution::DATA_MIN_FIELDNAMES
            .join(",")
            .as_bytes()
    ));
    let text = String::from_utf8(bytes).unwrap();
    assert!(text.contains("\"p,\"\"quoted\"\"\nvalue\""));
    assert!(text.contains(",1,1,,,,,Audio-Tactile,,true,Hit,100.000\r\n"));
    assert!(text.contains(",3,2,,,,,Audio-Tactile,,false,Miss,\r\n"));
    assert!(!text.contains("Filler"));
    assert_eq!(fs::read_to_string(&events).unwrap().lines().count(), 4);
    assert!(NativeEventJournal::open_bundle(&events, Some(&dataset), b"{}".to_vec()).is_err());
    assert_eq!(fs::read_to_string(&dataset).unwrap(), text);
    fs::remove_file(events).unwrap();
    fs::remove_file(dataset).unwrap();
}

#[test]
fn dataset_write_failure_never_acknowledges_events_or_rows_and_retains_both_files() {
    let stem = std::env::temp_dir().join(format!("pps-dataset-fault-{}", random_nonce()));
    let events = stem.with_extension("partial.jsonl");
    let dataset = stem.with_extension("partial.csv");
    fs::write(&events, b"retained events\n").unwrap();
    fs::write(&dataset, b"retained dataset\n").unwrap();
    let mut journal = NativeEventJournal::start_writer(
        OpenOptions::new().append(true).open(&events).unwrap(),
        Some(File::open(&dataset).unwrap()),
        0,
    )
    .unwrap();
    let ledger = EventLedger::default();
    let mut input = LedgerEventInput::new("trial.scored", "native-output", 1);
    input.payload =
        serde_json::json!({"trial_type": "Catch", "outcome": "Hit", "response_given": false});
    let batch = ledger.prepare_batch([input], LedgerReserve::NONE).unwrap();
    journal.admit(&batch).unwrap();
    wait_until(|| journal.failed());
    assert_eq!(
        (journal.durable_sequence(), journal.durable_dataset_rows()),
        (0, 0)
    );
    let retired = journal.retirement_probe();
    drop(journal);
    wait_until(retired);
    assert!(fs::read_to_string(&events)
        .unwrap()
        .starts_with("retained events\n"));
    assert_eq!(fs::read(&dataset).unwrap(), b"retained dataset\n");
    fs::remove_file(events).unwrap();
    fs::remove_file(dataset).unwrap();
}

fn publishable_journal(root: &Path) -> NativeEventJournal {
    let events = root.join("events.partial.jsonl");
    let dataset = root.join("trials.partial.csv");
    let header = serde_json::json!({"schema": "pps.native-event-journal.v1", "packageManifestSha256": "a".repeat(64),
        "participantId": "fixture", "sessionId": "S1", "partSessionId": "S1P2", "partNumber": 2,
        "executionMode": "participant_block_wavs", "completion": "partial", "timingQualification": "unqualified"});
    let publication = Publication {
        events: events.clone(),
        dataset: dataset.clone(),
        header: header.clone(),
    };
    NativeEventJournal::open_files(
        &events,
        Some(&dataset),
        serde_json::to_vec(&header).unwrap(),
        Some(publication),
    )
    .unwrap()
}

fn scored_prefix(journal: &mut NativeEventJournal) -> EventLedger {
    let mut ledger = EventLedger::default();
    let inputs = ["Audio-Tactile", "Filler", "Catch"]
        .into_iter()
        .enumerate()
        .map(|(index, kind)| {
            let mut input =
                LedgerEventInput::new("trial.scored", "native-participant", index as u64);
            input.payload = serde_json::json!({"trial_number": index + 1, "trial_type": kind,
            "response_given": kind == "Audio-Tactile", "outcome": "Hit", "rt_ms": "100.000"});
            input
        });
    let mut tail = LedgerEventInput::new("native.results.finalization-requested", "native", 4);
    tail.payload =
        serde_json::json!({"packageGeneration": 4, "runGeneration": 9, "expectedScoredTrials": 3});
    let batch = ledger
        .prepare_batch(
            [LedgerEventInput::new(
                "audio.final-frame-submitted",
                "native-output",
                0,
            )]
            .into_iter()
            .chain(inputs)
            .chain([tail]),
            LedgerReserve::NONE,
        )
        .unwrap();
    journal.admit(&batch).unwrap();
    ledger.commit_prepared(batch).unwrap();
    ledger
}

#[test]
fn completed_result_publishes_exact_synced_hashes_counts_and_an_exclusive_commit_manifest() {
    let root = std::env::temp_dir().join(format!("pps-publication-{}", random_nonce()));
    fs::create_dir(&root).unwrap();
    let mut journal = publishable_journal(&root);
    let ledger = scored_prefix(&mut journal);
    assert_eq!(journal.finish(4, 9, 2), Err(JournalError::Unavailable));
    assert!(journal.completion_receipt().is_none());
    let seal = journal.finish(4, 9, 3).unwrap();
    assert_eq!(
        journal.admit(&prepared(&ledger, 4)),
        Err(JournalError::Unavailable)
    );
    wait_until(|| journal.retired());
    assert!(!journal.failed());
    let receipt = journal.completion_receipt().unwrap();
    assert!(receipt.matches(seal));
    let mut stale = seal;
    stale.run_generation += 1;
    assert!(!receipt.matches(stale));
    assert_eq!(
        (
            receipt.event_record_count,
            receipt.scored_trial_count,
            receipt.dataset_row_count
        ),
        (5, 3, 2)
    );
    let events = fs::read(root.join("events.jsonl")).unwrap();
    let dataset = fs::read(root.join("trials.csv")).unwrap();
    assert_eq!(events, fs::read(root.join("events.partial.jsonl")).unwrap());
    assert_eq!(dataset, fs::read(root.join("trials.partial.csv")).unwrap());
    assert_eq!(
        receipt.events_sha256,
        format!("{:x}", Sha256::digest(&events))
    );
    assert_eq!(
        receipt.dataset_sha256,
        format!("{:x}", Sha256::digest(&dataset))
    );
    let manifest: serde_json::Value =
        serde_json::from_slice(&fs::read(root.join("events.results.json")).unwrap()).unwrap();
    assert_eq!(manifest["completion"], "complete");
    assert_eq!(manifest["timingQualification"], "unqualified");
    assert_eq!(manifest["eventsFile"], "events.jsonl");
    assert_eq!(manifest["datasetFile"], "trials.csv");
    assert_eq!(manifest["receipt"], serde_json::to_value(&receipt).unwrap());
    assert_eq!(journal.finish(4, 9, 3), Err(JournalError::Unavailable));
    // Only synthetic worker-test files may be retained for an independent
    // Python contract audit. This hook is absent from the production binary.
    if let Some(directory) = std::env::var_os("PPS_NATIVE_RESULT_FIXTURE_DIR") {
        let directory = PathBuf::from(directory);
        fs::create_dir_all(&directory).unwrap();
        for name in ["events.results.json", "events.jsonl", "trials.csv"] {
            fs::copy(root.join(name), directory.join(name)).unwrap();
        }
    }
    drop(journal);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn split_part_native_results_form_one_auditable_group() {
    let root = std::env::temp_dir().join(format!("pps-result-group-{}", random_nonce()));
    fs::create_dir(&root).unwrap();
    let group_id = "P001_group";
    let source_sha256 = "c".repeat(64);
    let mut prepared = Vec::new();
    let mut parts = Vec::new();
    for number in 1..=2 {
        let folder = format!("part_{number:02}");
        let part_dir = root.join(&folder);
        fs::create_dir(&part_dir).unwrap();
        fs::write(part_dir.join("block.wav"), b"not-played-validation-bytes").unwrap();
        fs::write(part_dir.join("block.csv"), b"Trial_UID\ntrial-1\n").unwrap();
        let session_id = format!("P001_group_part_{number:02}");
        let manifest_path = part_dir.join("session_manifest.json");
        fs::write(&manifest_path, serde_json::to_vec(&serde_json::json!({
            "schema": "pps-run-session.v1",
            "participant_id": "P001", "session_id": session_id,
            "session_group_id": group_id, "part_split_schema": "pps-runner-part-split.v1",
            "part_number": number, "part_session_id": session_id,
            "part_folder_name": folder, "source_run_setup_sha256": source_sha256,
            "execution_mode": "design_schedule_blocks",
            "blocks": [{"index": 1, "label": "Fixture block", "manifest_path": "block.csv",
                        "wav_path": "block.wav", "trial_count": 3, "duration_s": 1.0, "metadata": {}}]
        })).unwrap()).unwrap();
        prepared.push(verify_prepared_session(VerificationRequest::new(&manifest_path)).unwrap());
        parts.push(
            serde_json::json!({"part_number": number, "part_session_id": session_id,
            "part_folder_name": folder, "completed": false}),
        );
    }
    fs::write(
        root.join("session_group_manifest.json"),
        serde_json::to_vec(&serde_json::json!({
            "schema": "pps-run-session-group.v1", "part_split_schema": "pps-runner-part-split.v1",
            "session_group_id": group_id, "participant_id": "P001",
            "source_run_setup_sha256": source_sha256,
            "parts_per_participant": 2, "parts": parts
        }))
        .unwrap(),
    )
    .unwrap();

    for (index, verified) in prepared.iter().enumerate() {
        if index == 1 {
            assert!(verify_first_part_completion(verified).is_ok());
        }
        let mut journal = NativeEventJournal::create(verified).unwrap();
        scored_prefix(&mut journal);
        journal.finish(4, 9, 3).unwrap();
        wait_until(|| journal.retired());
        assert!(!journal.failed());
        assert!(journal.completion_receipt().is_some());
    }

    if let Some(directory) = std::env::var_os("PPS_NATIVE_RESULT_FIXTURE_DIR") {
        let destination = PathBuf::from(directory).join("group");
        fs::create_dir_all(&destination).unwrap();
        fs::copy(
            root.join("session_group_manifest.json"),
            destination.join("session_group_manifest.json"),
        )
        .unwrap();
        for number in 1..=2 {
            let folder = format!("part_{number:02}");
            let part_dir = root.join(&folder);
            let target = destination.join(&folder);
            fs::create_dir(&target).unwrap();
            fs::copy(
                part_dir.join("session_manifest.json"),
                target.join("session_manifest.json"),
            )
            .unwrap();
            for entry in fs::read_dir(&part_dir).unwrap() {
                let path = entry.unwrap().path();
                let name = path.file_name().unwrap().to_string_lossy();
                if name.ends_with(".results.json")
                    || name.ends_with(".jsonl")
                    || name.ends_with(".csv")
                {
                    fs::copy(&path, target.join(name.as_ref())).unwrap();
                }
            }
        }
    }
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn publication_collision_or_interruption_retains_partial_evidence_without_completing() {
    for collision in ["trials.csv", "events.results.json", "interrupted"] {
        let root = std::env::temp_dir().join(format!("pps-publication-fault-{}", random_nonce()));
        fs::create_dir(&root).unwrap();
        let mut journal = publishable_journal(&root);
        let mut ledger = scored_prefix(&mut journal);
        if collision == "interrupted" {
            let batch = ledger
                .prepare_batch(
                    [LedgerEventInput::new(
                        "trial.interrupted",
                        "native-participant",
                        4,
                    )],
                    LedgerReserve::NONE,
                )
                .unwrap();
            journal.admit(&batch).unwrap();
            ledger.commit_prepared(batch).unwrap();
            assert_eq!(journal.finish(4, 9, 3), Err(JournalError::Unavailable));
            journal.close();
        } else {
            fs::write(root.join(collision), b"existing bytes").unwrap();
            journal.finish(4, 9, 3).unwrap();
        }
        wait_until(|| journal.retired());
        assert!(journal.completion_receipt().is_none());
        assert!(root.join("events.partial.jsonl").is_file());
        assert!(root.join("trials.partial.csv").is_file());
        if collision != "interrupted" {
            assert!(journal.failed());
            assert_eq!(fs::read(root.join(collision)).unwrap(), b"existing bytes");
        }
        if collision != "events.results.json" {
            assert!(!root.join("events.results.json").exists());
        }
        drop(journal);
        fs::remove_dir_all(root).unwrap();
    }
}

#[test]
fn full_finish_queue_keeps_the_same_tail_retryable_without_accepting_more_records() {
    let (sender, receive) = mpsc::sync_channel(1);
    let mut journal = NativeEventJournal {
        sender: Some(sender),
        progress: Arc::new(Progress::default()),
        last_enqueued_sequence: None,
        admitted_bytes: 0,
        dataset_enabled: true,
        admitted_dataset_rows: 0,
        first_enqueued_sequence: None,
        admitted_scored_trials: 0,
        interrupted: false,
        publication_enabled: true,
        pending_seal: None,
    };
    let ledger = scored_prefix(&mut journal);
    assert_eq!(journal.finish(4, 9, 3), Err(JournalError::QueueFull));
    assert_eq!(
        journal.admit(&prepared(&ledger, 4)),
        Err(JournalError::Unavailable)
    );
    assert!(matches!(receive.recv().unwrap(), Message::Append(_)));
    let seal = journal.finish(4, 9, 3).unwrap();
    assert!(matches!(receive.recv().unwrap(), Message::Finish(value) if value == seal));
    assert!(journal.sender.is_none());
    assert!(journal.completion_receipt().is_none());
}
