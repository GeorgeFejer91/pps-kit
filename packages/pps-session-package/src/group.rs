//! A group binds two complete, distinct parts; completion claims in source
//! manifests are not acquisition evidence and are deliberately ignored.
use std::{
    collections::BTreeSet,
    fs,
    path::{Path, PathBuf},
};

use serde_json::Value;

use crate::{
    read_bounded_bytes, sha256_bytes, verify_prepared_session, VerificationError,
    VerificationErrorCode, VerificationRequest, VerifiedNativeFile, VerifiedPreparedSession,
    MAX_SESSION_MANIFEST_BYTES, MAX_TOTAL_PREPARED_BLOCK_WAV_BYTES,
};

#[derive(Debug, Clone, PartialEq)]
pub struct VerifiedPreparedGroup {
    manifest: VerifiedNativeFile,
    parts: Vec<VerifiedPreparedSession>,
}
impl VerifiedPreparedGroup {
    pub fn manifest(&self) -> &VerifiedNativeFile {
        &self.manifest
    }
    pub fn parts(&self) -> &[VerifiedPreparedSession] {
        &self.parts
    }
}

fn invalid(detail: &str) -> VerificationError {
    VerificationError::new(
        VerificationErrorCode::GroupInvalid,
        "The prepared session group is incomplete or inconsistent; regenerate both parts.",
        detail,
    )
}
fn text<'a>(value: &'a Value, key: &str) -> Result<&'a str, VerificationError> {
    value[key]
        .as_str()
        .filter(|s| !s.is_empty() && s.len() <= 4096 && !s.chars().any(char::is_control))
        .ok_or_else(|| invalid("Group field is missing or exceeds its bound."))
}
fn local_file(value: &Value, key: &str, root: &Path) -> Result<PathBuf, VerificationError> {
    let raw = Path::new(text(value, key)?);
    crate::ensure_native_path_syntax(raw)?;
    let path = fs::canonicalize(if raw.is_absolute() {
        raw.to_owned()
    } else {
        root.join(raw)
    })
    .map_err(|_| invalid("A declared group file is missing."))?;
    if !path.starts_with(root) || !path.is_file() {
        return Err(invalid(
            "Group files must be contained in the group directory.",
        ));
    }
    Ok(path)
}

/// Read-only native verification. Re-run before adoption/execution and compare
/// this complete receipt; neither a browser flag nor a source completion flag
/// can certify that either part ran.
pub fn verify_prepared_group(path: &Path) -> Result<VerifiedPreparedGroup, VerificationError> {
    let path = fs::canonicalize(path).map_err(|_| invalid("Group manifest is missing."))?;
    let root = path
        .parent()
        .ok_or_else(|| invalid("Group directory is missing."))?;
    let bytes = read_bounded_bytes(&path, MAX_SESSION_MANIFEST_BYTES)
        .map_err(|_| invalid("Group manifest exceeds its read limit."))?;
    let group: Value =
        serde_json::from_slice(&bytes).map_err(|_| invalid("Invalid group JSON."))?;
    if group["schema"] != "pps-run-session-group.v1"
        || group["part_split_schema"] != "pps-runner-part-split.v1"
        || group["experiment_structure"] != "pre_post"
        || group["parts_per_participant"].as_u64() != Some(2)
    {
        return Err(invalid("Unsupported group or part-split contract."));
    }
    let participant = text(&group, "participant_id")?;
    let group_id = text(&group, "session_group_id")?;
    let entries = group["parts"]
        .as_array()
        .filter(|p| p.len() == 2)
        .ok_or_else(|| invalid("Both ordered parts are required."))?;
    let setup = local_file(&group, "source_run_setup_manifest_path", root)?;
    let setup_hash = text(&group, "source_run_setup_sha256")?;
    let mut paths = Vec::new();
    for entry in entries {
        paths.push(local_file(entry, "session_manifest_path", root)?);
    }
    if paths[0] == paths[1] {
        return Err(invalid("Part manifests must be distinct."));
    }
    let mut parts = Vec::new();
    let mut directories = BTreeSet::new();
    let mut total_wav_bytes = 0u64;
    for (index, entry) in entries.iter().enumerate() {
        let number = (index + 1) as i64;
        if entry["part_number"].as_i64() != Some(number) {
            return Err(invalid("Part ordering must be 1 then 2."));
        }
        let part = verify_prepared_session(
            VerificationRequest::new(&paths[index])
                .with_participant_id(participant)
                .with_run_setup(&setup),
        )?;
        let summary = part.summary();
        if summary.part_number != Some(number)
            || summary.session_group_id != group_id
            || summary.part_session_id != text(entry, "part_session_id")?
            || summary.session_id != summary.part_session_id
            || !part.is_split_part()
            || entry["block_count"].as_u64() != Some(summary.blocks.len() as u64)
            || part
                .run_setup_manifest()
                .is_none_or(|s| s.sha256() != setup_hash)
        {
            return Err(invalid(
                "Part identity, setup or block inventory differs from its group.",
            ));
        }
        let directory = fs::canonicalize(part.session_dir())
            .map_err(|_| invalid("Part directory is missing."))?;
        if !directory.starts_with(root)
            || directory == root
            || !directories.insert(directory.clone())
            || fs::canonicalize(text(entry, "session_dir")?).ok().as_ref() != Some(&directory)
            || paths[index].parent() != Some(directory.as_path())
        {
            return Err(invalid(
                "Each part needs a distinct contained session directory.",
            ));
        }
        let raw = read_bounded_bytes(part.manifest_path(), MAX_SESSION_MANIFEST_BYTES)
            .map_err(|_| invalid("Part manifest cannot be reread."))?;
        if sha256_bytes(&raw) != part.manifest_sha256() {
            return Err(invalid("Part changed during group verification."));
        }
        let document: Value =
            serde_json::from_slice(&raw).map_err(|_| invalid("Invalid part JSON."))?;
        let siblings = document["sibling_part_manifest_paths"]
            .as_array()
            .filter(|p| p.len() == 1)
            .ok_or_else(|| invalid("Each part must identify exactly its other part."))?;
        let sibling = siblings[0]
            .as_str()
            .filter(|s| s.len() <= 4096)
            .ok_or_else(|| invalid("Invalid sibling manifest path."))?;
        if document["part_split_schema"] != "pps-runner-part-split.v1"
            || fs::canonicalize(sibling).ok().as_ref() != Some(&paths[1 - index])
            || document["approved_run_order_sha256"] != group["approved_run_order_sha256"]
            || !group["approved_run_order_sha256"]
                .as_str()
                .is_some_and(|s| s.len() == 64 && s.bytes().all(|b| b.is_ascii_hexdigit()))
        {
            return Err(invalid(
                "Part linkage or approved ordering differs from its group.",
            ));
        }
        for block in part.blocks() {
            total_wav_bytes = total_wav_bytes
                .checked_add(block.block_wav().encoded_byte_count())
                .filter(|n| *n <= MAX_TOTAL_PREPARED_BLOCK_WAV_BYTES)
                .ok_or_else(|| invalid("Combined part WAVs exceed the group byte limit."))?;
        }
        parts.push(part);
    }
    Ok(VerifiedPreparedGroup {
        manifest: VerifiedNativeFile {
            path,
            sha256: sha256_bytes(&bytes),
        },
        parts,
    })
}
