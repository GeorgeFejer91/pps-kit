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
