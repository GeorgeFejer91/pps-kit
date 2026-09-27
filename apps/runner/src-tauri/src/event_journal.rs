//! A native-only, bounded writer for the authority's existing event records.
//!
//! Opening and syncing files belongs to a worker, never the authority or audio
//! callback. Queue admission is not a durability acknowledgement. Files retain
//! their `.partial.jsonl` suffix: this journal alone cannot certify a completed
//! experiment, response dataset, or physical timing qualification.

use std::{
    fs::{File, OpenOptions},
    io::Write,
    path::Path,
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        mpsc::{self, SyncSender, TrySendError},
        Arc,
    },
    thread,
};

use pps_brsp::random_nonce;
use pps_runner_execution::{
    data_min_row, encode_data_min_csv, PreparedLedgerBatch, MAX_LEDGER_ENCODED_BYTES,
};
use pps_session_package::VerifiedPreparedSession;

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
}

struct Batch {
    last_sequence: u64,
    bytes: Vec<u8>,
    dataset_bytes: Vec<u8>,
    dataset_rows: u64,
}

/// A single authority's non-cloneable admission port. No filesystem path or
/// file handle can cross IPC through this type.
pub(crate) struct NativeEventJournal {
    sender: Option<SyncSender<Batch>>,
    progress: Arc<Progress>,
    last_enqueued_sequence: Option<u64>,
    admitted_bytes: usize,
    dataset_enabled: bool,
    admitted_dataset_rows: u64,
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
        Self::open_bundle(
            &verified.session_dir().join(filename),
            Some(
                &verified
                    .session_dir()
                    .join(format!("native_trials_{nonce}.partial.csv")),
            ),
            header,
        )
    }

    #[cfg(test)]
    fn open(path: &Path, header: Vec<u8>) -> Result<Self, JournalError> {
        Self::open_bundle(path, None, header)
    }

    fn open_bundle(
        path: &Path,
        dataset_path: Option<&Path>,
        mut header: Vec<u8>,
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
            Some(dataset)
        } else {
            None
        };
        Self::start_writer(file, dataset, admitted_bytes)
    }

    fn start_writer(
        file: File,
        dataset: Option<File>,
        admitted_bytes: usize,
    ) -> Result<Self, JournalError> {
        let (sender, receive) = mpsc::sync_channel(QUEUE_CAPACITY);
        let progress = Arc::new(Progress::default());
        let worker_progress = Arc::clone(&progress);
        let dataset_enabled = dataset.is_some();
        thread::Builder::new()
            .name("pps-native-event-journal".to_owned())
            .spawn(move || {
                write_batches(file, dataset, receive, &worker_progress);
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
        })
    }

    /// Admit the same validated batch the authority will commit. Serialization
    /// is bounded; all disk work and fsync acknowledgements remain off actor.
    pub(crate) fn admit(&mut self, prepared: &PreparedLedgerBatch) -> Result<(), JournalError> {
        if self.failed() || self.progress.retired.load(Ordering::Acquire) {
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
        let batch_bytes = bytes
            .len()
            .checked_add(dataset_bytes.len())
            .filter(|total| *total <= MAX_BATCH_BYTES)
            .ok_or(JournalError::ResourceLimit)?;
        let admitted_bytes = self
            .admitted_bytes
            .checked_add(batch_bytes)
            .filter(|total| *total <= MAX_FILE_BYTES)
            .ok_or(JournalError::ResourceLimit)?;
        let sender = self.sender.as_ref().ok_or(JournalError::Unavailable)?;
        match sender.try_send(Batch {
            last_sequence: last,
            bytes,
            dataset_bytes,
            dataset_rows,
        }) {
            Ok(()) => {
                self.last_enqueued_sequence = Some(last);
                self.admitted_bytes = admitted_bytes;
                self.admitted_dataset_rows = dataset_rows;
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
    receive: mpsc::Receiver<Batch>,
    progress: &Progress,
) {
    while let Ok(batch) = receive.recv() {
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

#[cfg(test)]
mod tests;
