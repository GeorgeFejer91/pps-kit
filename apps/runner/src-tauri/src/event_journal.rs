//! A native-only, bounded writer for the authority's existing event records.
//!
//! Opening and syncing files belongs to a worker, never the authority or audio
//! callback. Queue admission is not a durability acknowledgement. Files retain
//! partial names until the native owner seals a complete event/dataset prefix.
//! An exclusively published manifest is the result commit point. Neither that
//! receipt nor submitted software frames qualify physical experiment timing.

use std::{
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        mpsc::{self, SyncSender, TrySendError},
        Arc, Mutex,
    },
    thread,
};

use pps_brsp::random_nonce;
use pps_runner_execution::{
    data_min_row, encode_data_min_csv, PreparedLedgerBatch, MAX_LEDGER_ENCODED_BYTES,
};
use pps_session_package::{verify_prepared_session, VerificationRequest, VerifiedPreparedSession};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

const QUEUE_CAPACITY: usize = 8;
const MAX_BATCH_RECORDS: usize = 128;
const MAX_BATCH_BYTES: usize = 256 * 1024;
const MAX_FILE_BYTES: usize = MAX_LEDGER_ENCODED_BYTES;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum JournalError {
    Unavailable,
    QueueFull,
    SequenceGap,
    ResourceLimit,
}

#[derive(Default)]
struct Progress {
    durable_sequence: AtomicU64,
    durable_dataset_rows: AtomicU64,
    failed: AtomicBool,
    retired: AtomicBool,
    completion: Mutex<Option<NativeResultReceipt>>,
}

/// Native-only acknowledgement of the exact published prefix, never a browser
/// completion request. The manifest contains relative names; no path crosses IPC.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct NativeResultReceipt {
    pub package_manifest_sha256: String,
    pub package_generation: u64,
    pub run_generation: u64,
    pub first_event_sequence: u64,
    pub last_event_sequence: u64,
    pub event_record_count: u64,
    pub scored_trial_count: u64,
    pub dataset_row_count: u64,
    pub events_sha256: String,
    pub dataset_sha256: String,
}

/// Native-only proof that the adjacent Part 1 package has a complete, sealed
/// result. This is re-created from disk on every Part 2 selection so a
/// pre/post participant can return after the application has closed.
pub(crate) struct VerifiedFirstPart {
    manifest_path: PathBuf,
    participant_id: String,
    session_group_id: String,
}

impl VerifiedFirstPart {
    pub(crate) fn matches(&self, next: &VerifiedPreparedSession) -> bool {
        self.participant_id == next.summary().participant_id
            && self.session_group_id == next.summary().session_group_id
            && next.summary().part_number == Some(2)
            && self.manifest_path.parent().and_then(Path::parent)
                == next.manifest_path().parent().and_then(Path::parent)
    }
}

pub(crate) fn verify_first_part_completion(
    next: &VerifiedPreparedSession,
) -> Result<VerifiedFirstPart, &'static str> {
    if next.summary().part_number != Some(2) {
        return Err("prepared_part_one_completion_required");
    }
    let next_dir = next
        .manifest_path()
        .parent()
        .ok_or("prepared_part_one_completion_required")?;
    if next.manifest_path().file_name() != Some(std::ffi::OsStr::new("session_manifest.json"))
        || next_dir.file_name() != Some(std::ffi::OsStr::new("part_02"))
    {
        return Err("prepared_part_one_completion_required");
    }
    let first_path = next_dir
        .parent()
        .ok_or("prepared_part_one_completion_required")?
        .join("part_01")
        .join("session_manifest.json");
    let first = verify_prepared_session(VerificationRequest::new(&first_path))
        .map_err(|_| "prepared_part_one_completion_required")?;
    if first.summary().part_number != Some(1)
        || first.summary().participant_id != next.summary().participant_id
        || first.summary().session_group_id.is_empty()
        || first.summary().session_group_id != next.summary().session_group_id
        || !has_published_native_result(&first)
    {
        return Err("prepared_part_one_completion_required");
    }
    Ok(VerifiedFirstPart {
        manifest_path: first.manifest_path().to_path_buf(),
        participant_id: first.summary().participant_id.clone(),
        session_group_id: first.summary().session_group_id.clone(),
    })
}

fn has_published_native_result(first: &VerifiedPreparedSession) -> bool {
    let Ok(entries) = fs::read_dir(first.session_dir()) else {
        return false;
    };
    let mut seen = 0_usize;
    for entry in entries {
        let Ok(entry) = entry else { return false };
        seen += 1;
        if seen > 4096 {
            return false;
        }
        let name = entry.file_name();
        let name = name.to_string_lossy();
        let Some(nonce) = name
            .strip_prefix("native_events_")
            .and_then(|name| name.strip_suffix(".results.json"))
        else {
            continue;
        };
        if nonce.len() != 32
            || !nonce
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
        {
            return false;
        }
        if verify_published_result(first, nonce) {
            return true;
        }
    }
    false
}

fn verify_published_result(first: &VerifiedPreparedSession, nonce: &str) -> bool {
    let directory = first.session_dir();
    let manifest_path = directory.join(format!("native_events_{nonce}.results.json"));
    let events_path = directory.join(format!("native_events_{nonce}.jsonl"));
    let dataset_path = directory.join(format!("native_trials_{nonce}.csv"));
    let Ok(manifest_bytes) = read_bounded_file(&manifest_path, MAX_BATCH_BYTES) else {
        return false;
    };
    let Ok(manifest) = serde_json::from_slice::<serde_json::Value>(&manifest_bytes) else {
        return false;
    };
    let Some(receipt) = manifest
        .get("receipt")
        .and_then(|value| serde_json::from_value::<NativeResultReceipt>(value.clone()).ok())
    else {
        return false;
    };
    let identity = &manifest["identity"];
    if manifest["schema"] != "pps.native-results.v1"
        || manifest["completion"] != "complete"
        || manifest["timingQualification"] != "unqualified"
        || manifest["audioEvidence"] != "software-frame-submission"
        || manifest["eventsFile"] != format!("native_events_{nonce}.jsonl")
        || manifest["datasetFile"] != format!("native_trials_{nonce}.csv")
        || identity["participantId"] != first.summary().participant_id
        || identity["sessionId"] != first.summary().session_id
        || identity["partSessionId"] != first.summary().part_session_id
        || identity["partNumber"] != 1
        || identity["executionMode"] != first.summary().execution_mode
        || receipt.package_manifest_sha256 != first.manifest_sha256()
        || receipt.first_event_sequence == 0
        || receipt.last_event_sequence == u64::MAX
        || receipt.last_event_sequence < receipt.first_event_sequence
        || receipt.event_record_count
            != receipt.last_event_sequence - receipt.first_event_sequence + 1
        || receipt.scored_trial_count == 0
        || receipt.dataset_row_count > receipt.scored_trial_count
    {
        return false;
    }
    let Ok(events) = read_bounded_file(&events_path, MAX_FILE_BYTES) else {
        return false;
    };
    let Ok(dataset) = read_bounded_file(&dataset_path, MAX_FILE_BYTES) else {
        return false;
    };
    if format!("{:x}", Sha256::digest(&events)) != receipt.events_sha256
        || format!("{:x}", Sha256::digest(&dataset)) != receipt.dataset_sha256
        || events.last() != Some(&b'\n')
    {
        return false;
    }
    let mut lines = events[..events.len() - 1].split(|byte| *byte == b'\n');
    let Some(Ok(header)) = lines
        .next()
        .map(serde_json::from_slice::<serde_json::Value>)
    else {
        return false;
    };
    if header["schema"] != "pps.native-event-journal.v1"
        || header["packageManifestSha256"] != receipt.package_manifest_sha256
        || header["participantId"] != first.summary().participant_id
        || header["sessionId"] != first.summary().session_id
        || header["partSessionId"] != first.summary().part_session_id
        || header["partNumber"] != 1
        || header["executionMode"] != first.summary().execution_mode
        || header["timingQualification"] != "unqualified"
    {
        return false;
    }
    let mut expected = receipt.first_event_sequence;
    let mut scored = 0_u64;
    let mut final_frames = false;
    let mut tail = serde_json::Value::Null;
    for line in lines {
        let Ok(event) = serde_json::from_slice::<serde_json::Value>(line) else {
            return false;
        };
        if event["sequence"].as_u64() != Some(expected) || event["eventType"] == "trial.interrupted"
        {
            return false;
        }
        if event["eventType"] == "trial.scored" {
            scored += 1;
        }
        if event["eventType"] == "audio.final-frame-submitted" {
            final_frames = true;
        }
        let Some(next_expected) = expected.checked_add(1) else {
            return false;
        };
        expected = next_expected;
        tail = event;
    }
    expected == receipt.last_event_sequence + 1
        && scored == receipt.scored_trial_count
        && final_frames
        && tail["eventType"] == "native.results.finalization-requested"
        && tail["payload"]["packageGeneration"] == receipt.package_generation
        && tail["payload"]["runGeneration"] == receipt.run_generation
        && tail["payload"]["expectedScoredTrials"] == receipt.scored_trial_count
}

fn read_bounded_file(path: &Path, maximum: usize) -> std::io::Result<Vec<u8>> {
    let mut bytes = Vec::new();
    File::open(path)?
        .take(maximum as u64 + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() > maximum {
        return Err(std::io::Error::other("native result file limit"));
    }
    Ok(bytes)
}

struct Publication {
    events: PathBuf,
    dataset: PathBuf,
    header: serde_json::Value,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct NativeResultSeal {
    package_generation: u64,
    run_generation: u64,
    first_sequence: u64,
    last_sequence: u64,
    scored_trials: u64,
    dataset_rows: u64,
}

enum Message {
    Append(Batch),
    Finish(NativeResultSeal),
}

struct Batch {
    last_sequence: u64,
    bytes: Vec<u8>,
    dataset_bytes: Vec<u8>,
    dataset_rows: u64,
    scored_trials: u64,
}

/// A single authority's non-cloneable admission port. No filesystem path or
/// file handle can cross IPC through this type.
pub(crate) struct NativeEventJournal {
    sender: Option<SyncSender<Message>>,
    progress: Arc<Progress>,
    last_enqueued_sequence: Option<u64>,
    admitted_bytes: usize,
    dataset_enabled: bool,
    admitted_dataset_rows: u64,
    first_enqueued_sequence: Option<u64>,
    admitted_scored_trials: u64,
    interrupted: bool,
    publication_enabled: bool,
    pending_seal: Option<NativeResultSeal>,
}

impl NativeEventJournal {
    /// Called on a blocking preflight worker, using the native verifier's
    /// retained directory. The WebView/phone cannot choose a results path.
    pub(crate) fn create(verified: &VerifiedPreparedSession) -> Result<Self, JournalError> {
        let nonce = random_nonce();
        let filename = format!("native_events_{nonce}.partial.jsonl");
        let header = serde_json::to_vec(&serde_json::json!({
            "schema": "pps.native-event-journal.v1",
            "packageManifestSha256": verified.manifest_sha256(),
            "participantId": verified.summary().participant_id,
            "sessionId": verified.summary().session_id,
            "partSessionId": verified.summary().part_session_id,
            "partNumber": verified.summary().part_number,
            "executionMode": verified.summary().execution_mode,
            "timingQualification": "unqualified",
            "completion": "partial",
        }))
        .map_err(|_| JournalError::Unavailable)?;
        let events = verified.session_dir().join(filename);
        let dataset = verified
            .session_dir()
            .join(format!("native_trials_{nonce}.partial.csv"));
        let publication = Publication {
            events: events.clone(),
            dataset: dataset.clone(),
            header: serde_json::from_slice(&header).map_err(|_| JournalError::Unavailable)?,
        };
        Self::open_files(&events, Some(&dataset), header, Some(publication))
    }

    #[cfg(test)]
    fn open(path: &Path, header: Vec<u8>) -> Result<Self, JournalError> {
        Self::open_bundle(path, None, header)
    }

    #[cfg(test)]
    fn open_bundle(
        path: &Path,
        dataset_path: Option<&Path>,
        header: Vec<u8>,
    ) -> Result<Self, JournalError> {
        Self::open_files(path, dataset_path, header, None)
    }

    fn open_files(
        path: &Path,
        dataset_path: Option<&Path>,
        mut header: Vec<u8>,
        publication: Option<Publication>,
    ) -> Result<Self, JournalError> {
        if header.len() >= MAX_BATCH_BYTES {
            return Err(JournalError::ResourceLimit);
        }
        header.push(b'\n');
        // A collision or existing file is a denial, never an overwrite.
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(path)
            .map_err(|_| JournalError::Unavailable)?;
        file.write_all(&header)
            .and_then(|()| file.sync_all())
            .map_err(|_| JournalError::Unavailable)?;
        let mut admitted_bytes = header.len();
        let mut event_digest = Sha256::new();
        event_digest.update(&header);
        let mut dataset_digest = Sha256::new();
        let dataset = if let Some(path) = dataset_path {
            let bytes = encode_data_min_csv(&[], true).map_err(|_| JournalError::Unavailable)?;
            let mut dataset = OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(path)
                .map_err(|_| JournalError::Unavailable)?;
            dataset
                .write_all(&bytes)
                .and_then(|()| dataset.sync_all())
                .map_err(|_| JournalError::Unavailable)?;
            admitted_bytes += bytes.len();
            dataset_digest.update(&bytes);
            Some(dataset)
        } else {
            None
        };
        Self::start_writer_with_publication(
            file,
            dataset,
            admitted_bytes,
            publication,
            event_digest,
            dataset_digest,
        )
    }

    #[cfg(test)]
    fn start_writer(
        file: File,
        dataset: Option<File>,
        admitted_bytes: usize,
    ) -> Result<Self, JournalError> {
        Self::start_writer_with_publication(
            file,
            dataset,
            admitted_bytes,
            None,
            Sha256::new(),
            Sha256::new(),
        )
    }

    fn start_writer_with_publication(
        file: File,
        dataset: Option<File>,
        admitted_bytes: usize,
        publication: Option<Publication>,
        event_digest: Sha256,
        dataset_digest: Sha256,
    ) -> Result<Self, JournalError> {
        let (sender, receive) = mpsc::sync_channel(QUEUE_CAPACITY);
        let progress = Arc::new(Progress::default());
        let worker_progress = Arc::clone(&progress);
        let dataset_enabled = dataset.is_some();
        let publication_enabled = publication.is_some() && dataset_enabled;
        thread::Builder::new()
            .name("pps-native-event-journal".to_owned())
            .spawn(move || {
                write_batches(
                    file,
                    dataset,
                    receive,
                    &worker_progress,
                    publication,
                    event_digest,
                    dataset_digest,
                );
                worker_progress.retired.store(true, Ordering::Release);
            })
            .map_err(|_| JournalError::Unavailable)?;
        Ok(Self {
            sender: Some(sender),
            progress,
            last_enqueued_sequence: None,
            admitted_bytes,
            dataset_enabled,
            admitted_dataset_rows: 0,
            first_enqueued_sequence: None,
            admitted_scored_trials: 0,
            interrupted: false,
            publication_enabled,
            pending_seal: None,
        })
    }

    /// Admit the same validated batch the authority will commit. Serialization
    /// is bounded; all disk work and fsync acknowledgements remain off actor.
    pub(crate) fn admit(&mut self, prepared: &PreparedLedgerBatch) -> Result<(), JournalError> {
        if self.failed()
            || self.progress.retired.load(Ordering::Acquire)
            || self.pending_seal.is_some()
        {
            return Err(JournalError::Unavailable);
        }
        let records = prepared.records();
        if records.is_empty() {
            return Ok(());
        }
        if records.len() > MAX_BATCH_RECORDS || prepared.encoded_bytes() > MAX_BATCH_BYTES {
            return Err(JournalError::ResourceLimit);
        }
        let first = records.first().expect("nonempty batch").sequence;
        let last = records.last().expect("nonempty batch").sequence;
        if first == 0
            || self
                .last_enqueued_sequence
                .is_some_and(|previous| previous.checked_add(1) != Some(first))
            || last.checked_sub(first) != u64::try_from(records.len() - 1).ok()
        {
            return Err(JournalError::SequenceGap);
        }
        let mut bytes = Vec::with_capacity(prepared.encoded_bytes().saturating_add(records.len()));
        for record in records {
            serde_json::to_writer(&mut bytes, record).map_err(|_| JournalError::Unavailable)?;
            bytes.push(b'\n');
        }
        if bytes.len() > MAX_BATCH_BYTES {
            return Err(JournalError::ResourceLimit);
        }
        // Scoring facts and CSV cells share this exact admitted event prefix.
        // Filler/debug events remain rich evidence but do not consume a
        // Data_min index. There is no independent response writer or counter.
        let mut rows = Vec::new();
        for record in records
            .iter()
            .filter(|record| record.event_type == "trial.scored")
        {
            if !self.dataset_enabled {
                return Err(JournalError::Unavailable);
            }
            let row = record
                .payload
                .as_object()
                .ok_or(JournalError::Unavailable)?;
            let index = self
                .admitted_dataset_rows
                .checked_add(rows.len() as u64)
                .and_then(|count| count.checked_add(1))
                .ok_or(JournalError::ResourceLimit)?;
            if let Some(row) = data_min_row(row, index) {
                rows.push(row);
            }
        }
        let dataset_bytes =
            encode_data_min_csv(&rows, false).map_err(|_| JournalError::Unavailable)?;
        let dataset_rows = self
            .admitted_dataset_rows
            .checked_add(rows.len() as u64)
            .ok_or(JournalError::ResourceLimit)?;
        let scored_trials = self
            .admitted_scored_trials
            .checked_add(
                records
                    .iter()
                    .filter(|record| record.event_type == "trial.scored")
                    .count() as u64,
            )
            .ok_or(JournalError::ResourceLimit)?;
        let batch_bytes = bytes
            .len()
            .checked_add(dataset_bytes.len())
            .filter(|total| *total <= MAX_BATCH_BYTES)
            .ok_or(JournalError::ResourceLimit)?;
        let admitted_bytes = self
            .admitted_bytes
            .checked_add(batch_bytes)
            .filter(|total| {
                total
                    .checked_add(if self.publication_enabled {
                        MAX_BATCH_BYTES
                    } else {
                        0
                    })
                    .is_some_and(|total| total <= MAX_FILE_BYTES)
            })
            .ok_or(JournalError::ResourceLimit)?;
        let sender = self.sender.as_ref().ok_or(JournalError::Unavailable)?;
        match sender.try_send(Message::Append(Batch {
            last_sequence: last,
            bytes,
            dataset_bytes,
            dataset_rows,
            scored_trials,
        })) {
            Ok(()) => {
                self.last_enqueued_sequence = Some(last);
                self.admitted_bytes = admitted_bytes;
                self.admitted_dataset_rows = dataset_rows;
                self.first_enqueued_sequence.get_or_insert(first);
                self.admitted_scored_trials = scored_trials;
                self.interrupted |= records
                    .iter()
                    .any(|record| record.event_type == "trial.interrupted");
                Ok(())
            }
            Err(TrySendError::Full(_)) => Err(JournalError::QueueFull),
            Err(TrySendError::Disconnected(_)) => Err(JournalError::Unavailable),
        }
    }

    pub(crate) fn failed(&self) -> bool {
        self.progress.failed.load(Ordering::Acquire)
    }

    pub(crate) fn close(&mut self) {
        self.sender = None;
    }

    /// Seal only the already admitted complete prefix. Disconnecting without
    /// this native request leaves partial evidence. No more appends may follow.
    pub(crate) fn finish(
        &mut self,
        package_generation: u64,
        run_generation: u64,
        expected_trials: u64,
    ) -> Result<NativeResultSeal, JournalError> {
        if self.failed()
            || self.retired()
            || !self.publication_enabled
            || self.interrupted
            || expected_trials == 0
            || self.admitted_scored_trials != expected_trials
        {
            return Err(JournalError::Unavailable);
        }
        let seal = NativeResultSeal {
            package_generation,
            run_generation,
            first_sequence: self
                .first_enqueued_sequence
                .ok_or(JournalError::SequenceGap)?,
            last_sequence: self
                .last_enqueued_sequence
                .ok_or(JournalError::SequenceGap)?,
            scored_trials: expected_trials,
            dataset_rows: self.admitted_dataset_rows,
        };
        if self.pending_seal.is_some_and(|pending| pending != seal) {
            return Err(JournalError::Unavailable);
        }
        self.pending_seal = Some(seal);
        match self
            .sender
            .as_ref()
            .ok_or(JournalError::Unavailable)?
            .try_send(Message::Finish(seal))
        {
            Ok(()) => {
                self.sender = None;
                Ok(seal)
            }
            Err(TrySendError::Full(_)) => Err(JournalError::QueueFull),
            Err(TrySendError::Disconnected(_)) => Err(JournalError::Unavailable),
        }
    }

    pub(crate) fn completion_receipt(&self) -> Option<NativeResultReceipt> {
        self.progress
            .completion
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .clone()
    }

    pub(crate) fn retired(&self) -> bool {
        self.progress.retired.load(Ordering::Acquire)
    }

    /// The fsync-confirmed prefix, not the queue's accepted tail.
    pub(crate) fn durable_sequence(&self) -> u64 {
        self.progress.durable_sequence.load(Ordering::Acquire)
    }

    pub(crate) fn durable_dataset_rows(&self) -> u64 {
        self.progress.durable_dataset_rows.load(Ordering::Acquire)
    }

    #[cfg(test)]
    pub(crate) fn retirement_probe(&self) -> impl Fn() -> bool + Send + 'static {
        let progress = Arc::clone(&self.progress);
        move || progress.retired.load(Ordering::Acquire)
    }

    #[cfg(test)]
    pub(crate) fn failing_writer(path: &Path) -> Self {
        Self::start_writer(File::open(path).expect("test fixture exists"), None, 0)
            .expect("test writer starts")
    }
}

fn write_batches(
    mut file: File,
    mut dataset: Option<File>,
    receive: mpsc::Receiver<Message>,
    progress: &Progress,
    publication: Option<Publication>,
    mut event_digest: Sha256,
    mut dataset_digest: Sha256,
) {
    let mut scored_trials = 0;
    while let Ok(message) = receive.recv() {
        let batch = match message {
            Message::Append(batch) => batch,
            Message::Finish(seal) => {
                let result = (|| {
                    if progress.durable_sequence.load(Ordering::Acquire) != seal.last_sequence
                        || progress.durable_dataset_rows.load(Ordering::Acquire)
                            != seal.dataset_rows
                        || scored_trials != seal.scored_trials
                        || seal.first_sequence > seal.last_sequence
                    {
                        return Err(std::io::Error::other("result prefix mismatch"));
                    }
                    file.sync_all()?;
                    dataset
                        .as_ref()
                        .ok_or_else(|| std::io::Error::other("dataset unavailable"))?
                        .sync_all()?;
                    let publication = publication
                        .as_ref()
                        .ok_or_else(|| std::io::Error::other("publication unavailable"))?;
                    let receipt = NativeResultReceipt {
                        package_manifest_sha256: publication.header["packageManifestSha256"]
                            .as_str()
                            .ok_or_else(|| std::io::Error::other("package identity unavailable"))?
                            .to_owned(),
                        package_generation: seal.package_generation,
                        run_generation: seal.run_generation,
                        first_event_sequence: seal.first_sequence,
                        last_event_sequence: seal.last_sequence,
                        event_record_count: seal.last_sequence - seal.first_sequence + 1,
                        scored_trial_count: seal.scored_trials,
                        dataset_row_count: seal.dataset_rows,
                        events_sha256: format!("{:x}", event_digest.finalize()),
                        dataset_sha256: format!("{:x}", dataset_digest.finalize()),
                    };
                    // Close the sole append handles before publishing the sealed
                    // bytes. Retained partial names remain recovery evidence.
                    drop(file);
                    drop(dataset);
                    publication.publish(&receipt)?;
                    *progress
                        .completion
                        .lock()
                        .unwrap_or_else(|error| error.into_inner()) = Some(receipt);
                    Ok::<_, std::io::Error>(())
                })();
                if result.is_err() {
                    progress.failed.store(true, Ordering::Release);
                }
                return;
            }
        };
        let write = (|| {
            file.write_all(&batch.bytes)?;
            if let Some(dataset) = dataset.as_mut() {
                dataset.write_all(&batch.dataset_bytes)?;
                dataset.sync_data()?;
            }
            file.sync_data()
        })();
        if write.is_err() {
            progress.failed.store(true, Ordering::Release);
            return;
        }
        event_digest.update(&batch.bytes);
        dataset_digest.update(&batch.dataset_bytes);
        scored_trials = batch.scored_trials;
        progress
            .durable_sequence
            .store(batch.last_sequence, Ordering::Release);
        progress
            .durable_dataset_rows
            .store(batch.dataset_rows, Ordering::Release);
    }
    // Every accepted batch was synced before its acknowledgement. Disconnect
    // simply closes the partial file, including after package replacement.
}

impl NativeResultReceipt {
    pub(crate) fn matches(&self, seal: NativeResultSeal) -> bool {
        self.package_generation == seal.package_generation
            && self.run_generation == seal.run_generation
            && self.first_event_sequence == seal.first_sequence
            && self.last_event_sequence == seal.last_sequence
            && self.scored_trial_count == seal.scored_trials
            && self.dataset_row_count == seal.dataset_rows
            && seal
                .last_sequence
                .checked_sub(seal.first_sequence)
                .and_then(|count| count.checked_add(1))
                == Some(self.event_record_count)
    }
}

impl Publication {
    fn publish(&self, receipt: &NativeResultReceipt) -> std::io::Result<()> {
        fn final_path(partial: &Path, suffix: &str, replacement: &str) -> std::io::Result<PathBuf> {
            let name = partial
                .file_name()
                .and_then(|name| name.to_str())
                .and_then(|name| name.strip_suffix(suffix))
                .ok_or_else(|| std::io::Error::other("invalid result filename"))?;
            Ok(partial.with_file_name(format!("{name}{replacement}")))
        }
        let events = final_path(&self.events, ".partial.jsonl", ".jsonl")?;
        let dataset = final_path(&self.dataset, ".partial.csv", ".csv")?;
        let pending = final_path(&self.events, ".partial.jsonl", ".results.pending.json")?;
        let manifest = final_path(&self.events, ".partial.jsonl", ".results.json")?;
        let bytes = serde_json::to_vec(&serde_json::json!({
            "schema": "pps.native-results.v1", "completion": "complete", "timingQualification": "unqualified",
            "audioEvidence": "software-frame-submission", "identity": {
                "participantId": self.header["participantId"], "sessionId": self.header["sessionId"],
                "partSessionId": self.header["partSessionId"], "partNumber": self.header["partNumber"],
                "executionMode": self.header["executionMode"],
            },
            "receipt": receipt, "eventsFile": events.file_name().and_then(|name| name.to_str()),
            "datasetFile": dataset.file_name().and_then(|name| name.to_str()),
        }))?;
        if bytes.len() > MAX_BATCH_BYTES {
            return Err(std::io::Error::other("result manifest limit"));
        }
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&pending)?;
        file.write_all(&bytes)?;
        file.sync_all()?;
        drop(file);
        // Stdlib hard_link is atomic and refuses an existing target on every
        // supported host. Unsupported filesystems fail closed. The manifest
        // appears last; two data files without it are not a completed result.
        fs::hard_link(&self.events, &events)?;
        fs::hard_link(&self.dataset, &dataset)?;
        // Re-read the published names on the worker: replacing a partial name
        // while its append handle was open must not certify different bytes.
        for (path, expected) in [
            (&events, &receipt.events_sha256),
            (&dataset, &receipt.dataset_sha256),
        ] {
            let mut file = File::open(path)?;
            let mut digest = Sha256::new();
            let mut bytes = [0; 8192];
            let mut count = 0usize;
            loop {
                let read = file.read(&mut bytes)?;
                if read == 0 {
                    break;
                }
                count = count
                    .checked_add(read)
                    .filter(|count| *count <= MAX_FILE_BYTES)
                    .ok_or_else(|| std::io::Error::other("result file limit"))?;
                digest.update(&bytes[..read]);
            }
            if format!("{:x}", digest.finalize()) != *expected {
                return Err(std::io::Error::other("published bytes changed"));
            }
        }
        fs::hard_link(&pending, &manifest)
    }
}

#[cfg(test)]
mod tests;
