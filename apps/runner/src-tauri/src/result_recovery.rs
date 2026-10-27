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

pub(crate) fn assess_native_results(verified: &VerifiedPreparedSession) -> NativeResultsAssessment {
    assess_directory(verified.session_dir(), verified.manifest_sha256())
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

pub(crate) fn assess_directory(directory: &Path, package_hash: &str) -> NativeResultsAssessment {
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
        if let Err(reason) = assess_attempt(
            &directory,
            &id,
            &files,
            package_hash,
            &mut budget,
            &mut result,
        ) {
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
    package_hash: &str,
    budget: &mut usize,
    out: &mut AttemptAssessment,
) -> Result<(), &'static str> {
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
        if manifest["identity"][key] != header[key] {
            return Err("identity_mismatch");
        }
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
