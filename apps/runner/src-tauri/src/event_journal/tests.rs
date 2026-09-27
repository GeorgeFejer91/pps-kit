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
    let mut journal = NativeEventJournal::start_writer(File::open(&path).unwrap(), 16).unwrap();
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
