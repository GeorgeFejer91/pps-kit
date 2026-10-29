//! Read-only restart assessment. A matching readable prefix is evidence of file
//! contents, not an fsync receipt, permission to replay, or timing qualification.
//! Call on the selection worker; never on the authority/audio callback.
use pps_runner_execution::{data_min_row, encode_data_min_csv, MAX_LEDGER_ENCODED_BYTES};
use pps_session_package::VerifiedPreparedSession;
use serde::Serialize;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, File},
    io::Read,
    path::Path,
};

const MAX_BYTES: usize = MAX_LEDGER_ENCODED_BYTES;
const MAX_RECORD: usize = 256 * 1024;
const MAX_SCAN_BYTES: usize = 128 * 1024 * 1024;
const MAX_DIRECTORY_ENTRIES: usize = 2048;
const MAX_ATTEMPTS: usize = 256;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct NativeResultsAssessment {
    schema: &'static str,
    inspection_scope: &'static str,
    timing_qualification: &'static str,
    complete_scan: bool,
    reason: &'static str,
    attempts: Vec<AttemptAssessment>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
struct AttemptAssessment {
    attempt_id: String,
    status: &'static str,
    reason: &'static str,
    common_event_sequence: Option<u64>,
    common_event_records: u64,
    common_dataset_rows: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct NativeGroupResultsAssessment {
    schema: &'static str,
    timing_qualification: &'static str,
    complete_scan: bool,
    reason: &'static str,
    parts: Vec<PartResultsAssessment>,
    groups: Vec<GroupAttemptAssessment>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
struct PartResultsAssessment {
    part_number: usize,
    assessment: NativeResultsAssessment,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
struct GroupAttemptAssessment {
    group_attempt_id: String,
    status: &'static str,
    reason: &'static str,
    part_count: Option<usize>,
    scored_trial_count: Option<u64>,
    dataset_row_count: Option<u64>,
}

/// Inspect saved evidence only; this does not restore progress or replay a run.
pub(crate) fn assess_native_group_results(
    group: &pps_session_package::VerifiedPreparedGroup,
) -> NativeGroupResultsAssessment {
    let parts: Vec<_> = group
        .parts()
        .iter()
        .enumerate()
        .map(|(index, part)| PartResultsAssessment {
            part_number: index + 1,
            assessment: assess_native_results(part),
        })
        .collect();
    let mut result = NativeGroupResultsAssessment {
        schema: "pps.native-group-result-assessment.v1",
        timing_qualification: "unqualified",
        complete_scan: parts.iter().all(|part| part.assessment.complete_scan),
        reason: "inspected",
        parts,
        groups: Vec::new(),
    };
    let Some(root) = group.manifest().path().parent() else {
        result.complete_scan = false;
        result.reason = "group_directory_unavailable";
        return result;
    };
    let Ok(entries) = fs::read_dir(root) else {
        result.complete_scan = false;
        result.reason = "group_directory_unreadable";
        return result;
    };
    let mut candidates = BTreeMap::new();
    for (index, entry) in entries.enumerate() {
        if index >= MAX_DIRECTORY_ENTRIES || candidates.len() >= MAX_ATTEMPTS {
            result.complete_scan = false;
            result.reason = "group_scan_limit";
            break;
        }
        let Ok(entry) = entry else {
            result.complete_scan = false;
            result.reason = "group_directory_unreadable";
            continue;
        };
        let name = entry.file_name();
        let Some(name) = name.to_str() else { continue };
        let Some(stem) = name.strip_prefix("native_group_") else {
            continue;
        };
        let (id, pending) = match stem.strip_suffix(".results.json") {
            Some(id) => (id, false),
            None => match stem.strip_suffix(".results.pending.json") {
                Some(id) => (id, true),
                None => continue,
            },
        };
        if id.len() != 32
            || !id
                .bytes()
                .all(|c| c.is_ascii_alphanumeric() || b"_-".contains(&c))
        {
            continue;
        }
        let candidate = candidates.entry(id.to_owned()).or_insert(None);
        if !pending {
            *candidate = Some(entry.path());
        }
    }
    let mut remaining = MAX_SCAN_BYTES;
    for (id, path) in candidates {
        if remaining == 0 {
            result.complete_scan = false;
            result.reason = "group_scan_limit";
            break;
        }
        let mut attempt = GroupAttemptAssessment {
            group_attempt_id: id,
            status: if path.is_none() {
                "interrupted"
            } else {
                "invalid"
            },
            reason: if path.is_none() {
                "group_receipt_not_published"
            } else {
                "group_receipt_failed_verification"
            },
            part_count: None,
            scored_trial_count: None,
            dataset_row_count: None,
        };
        if let Some(path) = path {
            match crate::event_journal::group_results::verify_published_group_result_with_budget(
                group,
                &path,
                &mut remaining,
            ) {
                Ok(receipt) => {
                    attempt.status = "complete";
                    attempt.reason = "matching_group_receipt";
                    attempt.part_count = Some(receipt.part_count);
                    attempt.scored_trial_count = Some(receipt.scored_trial_count);
                    attempt.dataset_row_count = Some(receipt.dataset_row_count);
                }
                Err(crate::event_journal::group_results::GroupResultError::BudgetExceeded) => {
                    attempt.status = "not_assessed";
                    attempt.reason = "group_scan_limit";
                    remaining = 0;
                }
                Err(_) => {}
            }
        }
        result.groups.push(attempt);
    }
    if remaining == 0 {
        result.complete_scan = false;
        result.reason = "group_scan_limit";
    }
    if !result.complete_scan && result.reason == "inspected" {
        result.reason = "part_scan_incomplete";
    }
    result
}

// Native verified expectations are not inferred from the result being assessed.
pub(crate) struct ExpectedResultContext {
    pub package_hash: String,
    pub identity: Value,
    pub scored_trial_count: Option<u64>,
}

pub(crate) fn assess_native_results(verified: &VerifiedPreparedSession) -> NativeResultsAssessment {
    let summary = verified.summary();
    let expected = ExpectedResultContext {
        package_hash: verified.manifest_sha256().to_owned(),
        identity: serde_json::json!({"participantId":summary.participant_id,"sessionId":summary.session_id,
            "partSessionId":summary.part_session_id,"partNumber":summary.part_number,"executionMode":summary.execution_mode}),
        scored_trial_count: summary.blocks.iter().try_fold(0_u64, |sum, block| {
            sum.checked_add(u64::try_from(block.trial_count).ok()?)
        }),
    };
    assess_directory(verified.session_dir(), &expected)
}

fn artifact(name: &str) -> Option<(&str, &'static str)> {
    let (stem, endings) = if let Some(stem) = name.strip_prefix("native_events_") {
        (
            stem,
            &[
                ".partial.jsonl",
                ".jsonl",
                ".results.pending.json",
                ".results.json",
            ][..],
        )
    } else {
        (
            name.strip_prefix("native_trials_")?,
            &[".partial.csv", ".csv"][..],
        )
    };
    for &ending in endings {
        if let Some(id) = stem.strip_suffix(ending) {
            if id.len() == 32
                && id
                    .bytes()
                    .all(|c| c.is_ascii_alphanumeric() || b"_-".contains(&c))
            {
                return Some((id, ending));
            }
        }
    }
    None
}

pub(crate) fn assess_directory(
    directory: &Path,
    expected: &ExpectedResultContext,
) -> NativeResultsAssessment {
    let mut summary = NativeResultsAssessment {
        schema: "pps.native-result-assessment.v1",
        inspection_scope: "read-only-file-prefix",
        timing_qualification: "unqualified",
        complete_scan: true,
        reason: "assessed",
        attempts: Vec::new(),
    };
    let Ok(directory) = fs::canonicalize(directory) else {
        summary.complete_scan = false;
        summary.reason = "directory_unavailable";
        return summary;
    };
    let Ok(entries) = fs::read_dir(&directory) else {
        summary.complete_scan = false;
        summary.reason = "directory_unavailable";
        return summary;
    };
    let mut attempts: BTreeMap<String, BTreeSet<&'static str>> = BTreeMap::new();
    for (count, entry) in entries.enumerate() {
        if count >= MAX_DIRECTORY_ENTRIES {
            summary.complete_scan = false;
            summary.reason = "resource_limit";
            break;
        }
        let Ok(entry) = entry else {
            summary.complete_scan = false;
            summary.reason = "directory_unavailable";
            continue;
        };
        let name = entry.file_name();
        if let Some((id, ending)) = name.to_str().and_then(artifact) {
            if !attempts.contains_key(id) && attempts.len() >= MAX_ATTEMPTS {
                summary.complete_scan = false;
                summary.reason = "resource_limit";
                break;
            }
            attempts.entry(id.to_owned()).or_default().insert(ending);
        }
    }
    let mut budget = MAX_SCAN_BYTES;
    for (id, files) in attempts {
        let committed = files.contains(".results.json");
        let orphan = files
            .iter()
            .any(|suffix| [".jsonl", ".csv", ".results.pending.json"].contains(suffix));
        let mut result = AttemptAssessment {
            attempt_id: id.clone(),
            status: if orphan { "orphaned" } else { "interrupted" },
            reason: "no_commit_manifest",
            common_event_sequence: None,
            common_event_records: 0,
            common_dataset_rows: 0,
        };
        if let Err(reason) =
            assess_attempt(&directory, &id, &files, expected, &mut budget, &mut result)
        {
            result.reason = reason;
            result.status = if committed || reason != "missing_pair" {
                "invalid"
            } else {
                "orphaned"
            };
            if reason == "resource_limit" {
                summary.complete_scan = false;
                summary.reason = "resource_limit";
            }
        }
        summary.attempts.push(result);
    }
    summary
}

fn read_member(
    directory: &Path,
    name: &str,
    cap: usize,
    budget: &mut usize,
) -> Result<Vec<u8>, &'static str> {
    let path = directory.join(name);
    let metadata = fs::symlink_metadata(&path).map_err(|_| "missing_pair")?;
    if !metadata.is_file()
        || metadata.file_type().is_symlink()
        || fs::canonicalize(&path)
            .map_err(|_| "unreadable_file")?
            .parent()
            != Some(directory)
    {
        return Err("unsafe_member");
    }
    let limit = cap.min(*budget);
    if metadata.len() > limit as u64 {
        return Err("resource_limit");
    }
    let mut bytes = Vec::new();
    File::open(path)
        .map_err(|_| "unreadable_file")?
        .take(limit as u64 + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| "unreadable_file")?;
    if bytes.len() > limit {
        return Err("resource_limit");
    }
    *budget -= bytes.len();
    Ok(bytes)
}

fn assess_attempt(
    directory: &Path,
    id: &str,
    files: &BTreeSet<&str>,
    expected: &ExpectedResultContext,
    budget: &mut usize,
    out: &mut AttemptAssessment,
) -> Result<(), &'static str> {
    let package_hash = expected.package_hash.as_str();
    let committed = files.contains(".results.json");
    let event_name = format!(
        "native_events_{id}{}",
        if committed || files.contains(".jsonl") {
            ".jsonl"
        } else {
            ".partial.jsonl"
        }
    );
    let csv_name = format!(
        "native_trials_{id}{}",
        if committed || files.contains(".csv") {
            ".csv"
        } else {
            ".partial.csv"
        }
    );
    let events = read_member(directory, &event_name, MAX_BYTES, budget)?;
    let csv = read_member(directory, &csv_name, MAX_BYTES - events.len(), budget)?;
    let mut lines = events.split_inclusive(|b| *b == b'\n');
    let header = lines.next().ok_or("missing_header")?;
    if header.len() > MAX_RECORD || !header.ends_with(b"\n") {
        return Err("invalid_header");
    }
    let header: Value = serde_json::from_slice(header).map_err(|_| "invalid_header")?;
    if header["schema"] != "pps.native-event-journal.v1"
        || header["packageManifestSha256"] != package_hash
        || header["timingQualification"] != "unqualified"
        || header["completion"] != "partial"
    {
        return Err("header_mismatch");
    }
    let csv_header = encode_data_min_csv(&[], true).map_err(|_| "invalid_csv_header")?;
    if !csv.starts_with(&csv_header) {
        return Err("invalid_csv_header");
    }
    let mut offset = csv_header.len();
    let mut first = None;
    let mut scored = 0_u64;
    let mut interrupted = false;
    let mut submitted = false;
    let mut tail = Value::Null;
    let mut prefix_reason = None;
    for line in lines {
        if line.len() > MAX_RECORD {
            prefix_reason = Some("resource_limit");
            break;
        }
        if !line.ends_with(b"\n") {
            prefix_reason = Some("incomplete_event_tail");
            break;
        }
        let Ok(event) = serde_json::from_slice::<Value>(line) else {
            prefix_reason = Some("malformed_event");
            break;
        };
        let Some(sequence) = event["sequence"].as_u64().filter(|n| *n > 0) else {
            prefix_reason = Some("invalid_sequence");
            break;
        };
        if out
            .common_event_sequence
            .is_some_and(|previous| previous.checked_add(1) != Some(sequence))
        {
            prefix_reason = Some("event_sequence_gap");
            break;
        }
        let Some(kind) = event["eventType"].as_str().filter(|s| !s.is_empty()) else {
            prefix_reason = Some("invalid_event_type");
            break;
        };
        if kind == "trial.scored" {
            let Some(payload) = event["payload"].as_object() else {
                prefix_reason = Some("invalid_scored_payload");
                break;
            };
            if let Some(row) = data_min_row(payload, out.common_dataset_rows + 1) {
                let bytes =
                    encode_data_min_csv(&[row], false).map_err(|_| "invalid_scored_payload")?;
                if csv.get(offset..offset + bytes.len()) != Some(bytes.as_slice()) {
                    prefix_reason = Some("csv_prefix_mismatch");
                    break;
                }
                offset += bytes.len();
                out.common_dataset_rows += 1;
            }
            scored += 1;
        }
        interrupted |= kind == "trial.interrupted";
        submitted |= kind == "audio.final-frame-submitted";
        first.get_or_insert(sequence);
        out.common_event_sequence = Some(sequence);
        out.common_event_records += 1;
        tail = event;
    }
    if offset != csv.len() {
        prefix_reason.get_or_insert("unmatched_csv_tail");
    }
    if let Some(reason) = prefix_reason {
        out.reason = reason;
        if reason == "resource_limit" {
            return Err(reason);
        }
        if committed {
            return Err("invalid_committed_prefix");
        }
        return Ok(());
    }
    if !committed {
        return Ok(());
    }
    let manifest = read_member(
        directory,
        &format!("native_events_{id}.results.json"),
        MAX_RECORD,
        budget,
    )?;
    let manifest: Value = serde_json::from_slice(&manifest).map_err(|_| "invalid_manifest")?;
    if manifest["schema"] != "pps.native-results.v1"
        || manifest["completion"] != "complete"
        || manifest["timingQualification"] != "unqualified"
        || manifest["audioEvidence"] != "software-frame-submission"
        || manifest["eventsFile"] != event_name
        || manifest["datasetFile"] != csv_name
    {
        return Err("invalid_manifest");
    }
    for key in [
        "participantId",
        "sessionId",
        "partSessionId",
        "partNumber",
        "executionMode",
    ] {
        if manifest["identity"][key] != header[key] || header[key] != expected.identity[key] {
            return Err("identity_mismatch");
        }
    }
    if expected.scored_trial_count != Some(scored) {
        return Err("verified_package_trial_count_mismatch");
    }
    let receipt = &manifest["receipt"];
    if interrupted
        || !submitted
        || scored == 0
        || receipt["packageManifestSha256"] != package_hash
        || receipt["eventsSha256"] != format!("{:x}", Sha256::digest(&events))
        || receipt["datasetSha256"] != format!("{:x}", Sha256::digest(&csv))
        || receipt["firstEventSequence"].as_u64() != first
        || receipt["lastEventSequence"].as_u64() != out.common_event_sequence
        || receipt["eventRecordCount"].as_u64() != Some(out.common_event_records)
        || receipt["scoredTrialCount"].as_u64() != Some(scored)
        || receipt["datasetRowCount"].as_u64() != Some(out.common_dataset_rows)
        || tail["eventType"] != "native.results.finalization-requested"
        || tail["payload"]["expectedScoredTrials"].as_u64() != Some(scored)
    {
        return Err("receipt_mismatch");
    }
    for key in ["packageGeneration", "runGeneration"] {
        if receipt[key].as_u64().is_none() || receipt[key] != tail["payload"][key] {
            return Err("receipt_mismatch");
        }
    }
    out.status = "complete";
    out.reason = "verified_commit_manifest";
    Ok(())
}

#[cfg(test)]
mod tests;
