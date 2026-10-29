//! One bounded, exclusive commit joining two specific published part attempts.
//! No acquisition replay, implicit recovery, device access, or qualification.
use super::{
    GroupAttemptContext, NativeResultCommit, NativeResultReceipt, MAX_BATCH_BYTES, MAX_FILE_BYTES,
};
use pps_session_package::VerifiedPreparedGroup;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    path::{Component, Path},
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
    thread,
};

const MAX_GROUP_BYTES: usize = 64 * 1024;
const DEFAULT_READ_BUDGET: usize = 128 * 1024 * 1024;
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum GroupResultError {
    Invalid,
    Io,
    Cancelled,
    BudgetExceeded,
}
impl From<std::io::Error> for GroupResultError {
    fn from(_: std::io::Error) -> Self {
        Self::Io
    }
}
#[derive(Debug, Clone)]
pub(crate) struct VerifiedGroupResult {
    pub group_attempt_id: String,
    pub manifest_sha256: String,
    pub part_count: usize,
    pub scored_trial_count: u64,
    pub dataset_row_count: u64,
}

pub(crate) struct GroupPublication {
    cancelled: Arc<AtomicBool>,
    outcome: Arc<Mutex<Option<Result<VerifiedGroupResult, GroupResultError>>>>,
}
impl GroupPublication {
    pub(crate) fn start(
        group: Arc<VerifiedPreparedGroup>,
        attempt: GroupAttemptContext,
        commits: Vec<NativeResultCommit>,
    ) -> Result<Self, GroupResultError> {
        if commits.len() != 2 {
            return Err(GroupResultError::Invalid);
        }
        let cancelled = Arc::new(AtomicBool::new(false));
        let outcome = Arc::new(Mutex::new(None));
        let worker_cancel = Arc::clone(&cancelled);
        let worker_outcome = Arc::clone(&outcome);
        thread::Builder::new()
            .name("pps-group-results".into())
            .spawn(move || {
                let result = publish(&group, &attempt, &commits, &worker_cancel);
                *worker_outcome.lock().unwrap_or_else(|e| e.into_inner()) = Some(result);
            })?;
        Ok(Self { cancelled, outcome })
    }
    pub(crate) fn cancel(&self) {
        self.cancelled.store(true, Ordering::Release);
    }
    pub(crate) fn outcome(&self) -> Option<Result<VerifiedGroupResult, GroupResultError>> {
        self.outcome
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .clone()
    }
}
impl Drop for GroupPublication {
    fn drop(&mut self) {
        self.cancel();
    }
}
fn check_cancel(cancel: &AtomicBool) -> Result<(), GroupResultError> {
    if cancel.load(Ordering::Acquire) {
        Err(GroupResultError::Cancelled)
    } else {
        Ok(())
    }
}
fn invalid<T>() -> Result<T, GroupResultError> {
    Err(GroupResultError::Invalid)
}
fn text<'a>(v: &'a Value, key: &str) -> Result<&'a str, GroupResultError> {
    v[key]
        .as_str()
        .filter(|s| !s.is_empty() && s.len() <= 4096)
        .ok_or(GroupResultError::Invalid)
}
fn relative(root: &Path, path: &Path) -> Result<String, GroupResultError> {
    let path = path
        .strip_prefix(root)
        .map_err(|_| GroupResultError::Invalid)?;
    if !path.components().all(|c| matches!(c, Component::Normal(_))) {
        return invalid();
    }
    Ok(path.to_string_lossy().replace('\\', "/"))
}
fn contained(root: &Path, reference: &str) -> Result<std::path::PathBuf, GroupResultError> {
    let path = Path::new(reference);
    if reference.contains(['\\', ':'])
        || !path.components().all(|c| matches!(c, Component::Normal(_)))
    {
        return invalid();
    }
    let path = fs::canonicalize(root.join(path))?;
    if !path.starts_with(root) || !path.is_file() {
        return invalid();
    }
    Ok(path)
}
fn bounded_bytes(
    path: &Path,
    limit: usize,
    remaining: &mut usize,
) -> Result<Vec<u8>, GroupResultError> {
    let file = File::open(path)?;
    let length = file.metadata()?.len();
    if length > limit as u64 {
        return invalid();
    }
    if length > *remaining as u64 {
        return Err(GroupResultError::BudgetExceeded);
    }
    let mut bytes = Vec::new();
    // Count even failed or racing reads against the caller's cumulative cap.
    let result = (&file)
        .take(limit.min(*remaining) as u64)
        .read_to_end(&mut bytes);
    *remaining -= bytes.len();
    result?;
    if bytes.len() as u64 != length || file.metadata()?.len() != length {
        return invalid();
    }
    if bytes.len() > limit {
        return invalid();
    }
    Ok(bytes)
}
fn digest_file(
    path: &Path,
    cancel: &AtomicBool,
    remaining: &mut usize,
) -> Result<(String, Vec<u8>), GroupResultError> {
    let mut file = File::open(path)?;
    let length = file.metadata()?.len();
    if length > MAX_FILE_BYTES as u64 {
        return invalid();
    }
    if length > *remaining as u64 {
        return Err(GroupResultError::BudgetExceeded);
    }
    let mut digest = Sha256::new();
    let mut buffer = [0; 8192];
    let mut count = 0usize;
    let mut header = Vec::new();
    let mut header_done = false;
    loop {
        check_cancel(cancel)?;
        if count as u64 == length {
            if file.metadata()?.len() != length {
                return invalid();
            }
            break;
        }
        let available = buffer.len().min(*remaining);
        if available == 0 {
            return Err(GroupResultError::BudgetExceeded);
        }
        let read = file.read(&mut buffer[..available])?;
        *remaining -= read;
        if read == 0 {
            return invalid();
        }
        count = count
            .checked_add(read)
            .filter(|n| *n <= MAX_FILE_BYTES)
            .ok_or(GroupResultError::Invalid)?;
        digest.update(&buffer[..read]);
        if !header_done {
            let end = buffer[..read].iter().position(|b| *b == b'\n');
            let length = end.unwrap_or(read);
            if header.len() + length > MAX_BATCH_BYTES {
                return invalid();
            }
            header.extend_from_slice(&buffer[..length]);
            header_done = end.is_some();
        }
    }
    Ok((format!("{:x}", digest.finalize()), header))
}

/// Native-only bounded join validation for read-only recovery. The root is
/// supplied by the selected verified group, never by the result document.
pub(crate) fn verify_published_group_result(
    group: &VerifiedPreparedGroup,
    path: &Path,
) -> Result<VerifiedGroupResult, GroupResultError> {
    let mut remaining = DEFAULT_READ_BUDGET;
    verify_published_group_result_with_budget(group, path, &mut remaining)
}

/// Every file read, including repeated references, consumes this shared cap.
pub(crate) fn verify_published_group_result_with_budget(
    group: &VerifiedPreparedGroup,
    path: &Path,
    remaining: &mut usize,
) -> Result<VerifiedGroupResult, GroupResultError> {
    let root = fs::canonicalize(
        group
            .manifest()
            .path()
            .parent()
            .ok_or(GroupResultError::Invalid)?,
    )?;
    let path = fs::canonicalize(path)?;
    if path.parent() != Some(root.as_path()) {
        return invalid();
    }
    let bytes = bounded_bytes(&path, MAX_GROUP_BYTES, remaining)?;
    let value: Value = serde_json::from_slice(&bytes).map_err(|_| GroupResultError::Invalid)?;
    let result = verify_document(group, &value, &AtomicBool::new(false), remaining)?;
    if path.file_name().and_then(|s| s.to_str())
        != Some(format!("native_group_{}.results.json", result.group_attempt_id).as_str())
    {
        return invalid();
    }
    Ok(VerifiedGroupResult {
        manifest_sha256: format!("{:x}", Sha256::digest(bytes)),
        ..result
    })
}

fn verify_document(
    group: &VerifiedPreparedGroup,
    value: &Value,
    cancel: &AtomicBool,
    remaining: &mut usize,
) -> Result<VerifiedGroupResult, GroupResultError> {
    check_cancel(cancel)?;
    let root = fs::canonicalize(
        group
            .manifest()
            .path()
            .parent()
            .ok_or(GroupResultError::Invalid)?,
    )?;
    let attempt = text(value, "groupAttemptId")?;
    if !(16..=128).contains(&attempt.len())
        || !attempt
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
        || value["schema"] != "pps.native-group-results.v1"
        || value["completion"] != "complete"
        || value["timingQualification"] != "unqualified"
        || value["selectedGroupManifestSha256"] != group.manifest().sha256()
        || contained(&root, text(value, "selectedGroupManifestFile")?)? != group.manifest().path()
        || format!(
            "{:x}",
            Sha256::digest(bounded_bytes(
                group.manifest().path(),
                MAX_GROUP_BYTES,
                remaining
            )?)
        ) != group.manifest().sha256()
    {
        return invalid();
    }
    let parts = value["parts"]
        .as_array()
        .filter(|p| p.len() == 2 && p.len() == group.parts().len())
        .ok_or(GroupResultError::Invalid)?;
    let mut scored = 0u64;
    let mut dataset = 0u64;
    for (index, (entry, package)) in parts.iter().zip(group.parts()).enumerate() {
        check_cancel(cancel)?;
        let summary = package.summary();
        if entry["partNumber"].as_u64() != Some(index as u64 + 1)
            || entry["partSessionId"] != summary.part_session_id
            || contained(&root, text(entry, "packageManifestFile")?)? != package.manifest_path()
            || format!(
                "{:x}",
                Sha256::digest(bounded_bytes(
                    package.manifest_path(),
                    pps_session_package::MAX_SESSION_MANIFEST_BYTES,
                    remaining
                )?)
            ) != package.manifest_sha256()
        {
            return invalid();
        }
        let part_path = contained(&root, text(entry, "resultManifestFile")?)?;
        if part_path.parent() != Some(package.session_dir()) {
            return invalid();
        }
        let part_bytes = bounded_bytes(&part_path, MAX_BATCH_BYTES, remaining)?;
        if format!("{:x}", Sha256::digest(&part_bytes)) != text(entry, "resultManifestSha256")? {
            return invalid();
        }
        let part: Value =
            serde_json::from_slice(&part_bytes).map_err(|_| GroupResultError::Invalid)?;
        let identity = &part["identity"];
        let receipt: NativeResultReceipt = serde_json::from_value(entry["receipt"].clone())
            .map_err(|_| GroupResultError::Invalid)?;
        let expected = summary
            .blocks
            .iter()
            .try_fold(0u64, |sum, block| {
                sum.checked_add(u64::try_from(block.trial_count).ok()?)
            })
            .ok_or(GroupResultError::Invalid)?;
        if part["schema"] != "pps.native-results.v1"
            || part["completion"] != "complete"
            || part["timingQualification"] != "unqualified"
            || part["receipt"] != entry["receipt"]
            || identity["groupAttemptId"] != attempt
            || identity["selectedGroupManifestSha256"] != group.manifest().sha256()
            || identity["participantId"] != summary.participant_id
            || identity["sessionId"] != summary.session_id
            || identity["partSessionId"] != summary.part_session_id
            || identity["partNumber"] != entry["partNumber"]
            || receipt.package_manifest_sha256 != package.manifest_sha256()
            || receipt.scored_trial_count != expected
            || receipt.dataset_row_count > expected
            || expected == 0
            || receipt
                .last_event_sequence
                .checked_sub(receipt.first_event_sequence)
                .and_then(|n| n.checked_add(1))
                != Some(receipt.event_record_count)
        {
            return invalid();
        }
        for (key, expected_hash) in [
            ("eventsFile", &receipt.events_sha256),
            ("datasetFile", &receipt.dataset_sha256),
        ] {
            let path = contained(&root, text(entry, key)?)?;
            if path.parent() != Some(package.session_dir())
                || path.file_name().and_then(|s| s.to_str()) != part[key].as_str()
            {
                return invalid();
            }
            let (hash, header) = digest_file(&path, cancel, remaining)?;
            if hash != *expected_hash {
                return invalid();
            }
            if key == "eventsFile" {
                let header: Value =
                    serde_json::from_slice(&header).map_err(|_| GroupResultError::Invalid)?;
                if header["groupAttemptId"] != attempt
                    || header["selectedGroupManifestSha256"] != group.manifest().sha256()
                    || header["packageManifestSha256"] != package.manifest_sha256()
                    || header["partSessionId"] != summary.part_session_id
                    || header["participantId"] != summary.participant_id
                    || header["sessionId"] != summary.session_id
                    || header["partNumber"] != entry["partNumber"]
                {
                    return invalid();
                }
            }
        }
        scored = scored
            .checked_add(receipt.scored_trial_count)
            .ok_or(GroupResultError::Invalid)?;
        dataset = dataset
            .checked_add(receipt.dataset_row_count)
            .ok_or(GroupResultError::Invalid)?;
    }
    Ok(VerifiedGroupResult {
        group_attempt_id: attempt.to_owned(),
        manifest_sha256: String::new(),
        part_count: parts.len(),
        scored_trial_count: scored,
        dataset_row_count: dataset,
    })
}

fn publish(
    group: &VerifiedPreparedGroup,
    attempt: &GroupAttemptContext,
    commits: &[NativeResultCommit],
    cancel: &AtomicBool,
) -> Result<VerifiedGroupResult, GroupResultError> {
    if commits.len() != 2
        || group.parts().len() != 2
        || attempt.selected_group_manifest_sha256 != group.manifest().sha256()
    {
        return invalid();
    }
    let root = group
        .manifest()
        .path()
        .parent()
        .ok_or(GroupResultError::Invalid)?;
    let parts=group.parts().iter().zip(commits).enumerate().map(|(index,(package,commit))|{
        if commit.group_attempt.as_ref()!=Some(attempt){return invalid();}
        Ok(json!({"partNumber":index+1,"partSessionId":package.summary().part_session_id,"packageManifestFile":relative(root,package.manifest_path())?,
            "resultManifestFile":relative(root,&package.session_dir().join(&commit.manifest_file))?,"resultManifestSha256":commit.manifest_sha256,
            "eventsFile":relative(root,&package.session_dir().join(&commit.events_file))?,"datasetFile":relative(root,&package.session_dir().join(&commit.dataset_file))?,"receipt":commit.receipt}))
    }).collect::<Result<Vec<_>,GroupResultError>>()?;
    let document = json!({"schema":"pps.native-group-results.v1","completion":"complete","timingQualification":"unqualified","groupAttemptId":attempt.group_attempt_id,
        "selectedGroupManifestFile":relative(root,group.manifest().path())?,"selectedGroupManifestSha256":attempt.selected_group_manifest_sha256,"parts":parts});
    let mut remaining = DEFAULT_READ_BUDGET;
    verify_document(group, &document, cancel, &mut remaining)?;
    let bytes = serde_json::to_vec(&document).map_err(|_| GroupResultError::Invalid)?;
    if bytes.len() > MAX_GROUP_BYTES {
        return invalid();
    }
    check_cancel(cancel)?;
    let pending = root.join(format!(
        "native_group_{}.results.pending.json",
        attempt.group_attempt_id
    ));
    let final_path = root.join(format!(
        "native_group_{}.results.json",
        attempt.group_attempt_id
    ));
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&pending)?;
    file.write_all(&bytes)?;
    file.sync_all()?;
    drop(file);
    #[cfg(test)]
    publication_test_hook(&attempt.group_attempt_id, cancel)?;
    check_cancel(cancel)?;
    fs::hard_link(&pending, &final_path)?;
    if bounded_bytes(&final_path, MAX_GROUP_BYTES, &mut remaining)? != bytes {
        return invalid();
    }
    verify_published_group_result(group, &final_path)
}

#[cfg(test)]
static PUBLICATION_TEST_HOOKS: std::sync::LazyLock<
    Mutex<std::collections::BTreeMap<String, Arc<AtomicBool>>>,
> = std::sync::LazyLock::new(|| Mutex::new(std::collections::BTreeMap::new()));
#[cfg(test)]
pub(crate) fn pause_publication_for_test(attempt: &str) -> Arc<AtomicBool> {
    let reached = Arc::new(AtomicBool::new(false));
    PUBLICATION_TEST_HOOKS
        .lock()
        .unwrap()
        .insert(attempt.to_owned(), Arc::clone(&reached));
    reached
}
#[cfg(test)]
fn publication_test_hook(attempt: &str, cancel: &AtomicBool) -> Result<(), GroupResultError> {
    let gate = PUBLICATION_TEST_HOOKS.lock().unwrap().remove(attempt);
    if let Some(reached) = gate {
        reached.store(true, Ordering::Release);
        while !cancel.load(Ordering::Acquire) {
            thread::sleep(std::time::Duration::from_millis(2));
        }
        return Err(GroupResultError::Cancelled);
    }
    Ok(())
}
