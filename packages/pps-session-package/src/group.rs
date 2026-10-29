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
    let setup_bytes = read_bounded_bytes(&setup, MAX_SESSION_MANIFEST_BYTES)
        .map_err(|_| invalid("Run setup exceeds its read limit."))?;
    let setup_document: Value = serde_json::from_slice(&setup_bytes)
        .map_err(|_| invalid("Run setup is not valid JSON."))?;
    let order = &setup_document["approved_segment6"];
    let sources = &setup_document["approved_segment5"];
    if reviewed_digest(order)? != text(&group, "approved_run_order_sha256")? {
        return Err(invalid(
            "Accepted run-order digest does not match its serialized preview.",
        ));
    }
    if reviewed_digest(sources)? != text(&setup_document, "approved_preview_sha256")? {
        return Err(invalid(
            "Accepted source-block digest does not match its serialized preview.",
        ));
    }
    if json_digest(&setup_document["design"])? != text(&setup_document, "design_sha256")? {
        return Err(invalid(
            "Accepted design digest does not match its serialized design.",
        ));
    }
    if sha256_bytes(&setup_bytes) != setup_hash
        || setup_document["schema"] != "pps-native-run-setup.v1"
        || setup_document["participant_id"] != participant
        || setup_document["session_group_id"] != group_id
        || setup_document["approved_run_order_sha256"] != group["approved_run_order_sha256"]
        || order["assembly_preview_sha256"] != setup_document["approved_preview_sha256"]
        || order["design_sha256"] != setup_document["design_sha256"]
        || order["schema"] != "pps-native-run-order-preview.v1"
        || order["experiment_structure"] != "pre_post"
        || order["parts_per_participant"].as_u64() != Some(2)
    {
        return Err(invalid(
            "Group does not match its accepted design and run-order snapshots.",
        ));
    }
    let occurrences: Vec<_> = order["csv_rows"]
        .as_array()
        .ok_or_else(|| invalid("Accepted run order has no occurrence list."))?
        .iter()
        .filter(|row| row["participant_id"] == participant)
        .collect();
    let source_blocks = sources["blocks"]
        .as_array()
        .ok_or_else(|| invalid("Accepted source preview has no block list."))?;
    let mut paths = Vec::new();
    for entry in entries {
        paths.push(local_file(entry, "session_manifest_path", root)?);
    }
    if paths[0] == paths[1] {
        return Err(invalid("Part manifests must be distinct."));
    }
    let mut parts = Vec::new();
    let mut directories = BTreeSet::new();
    let mut identities = BTreeSet::new();
    let mut total_wav_bytes = 0u64;
    let mut global_position = 0usize;
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
            || !identities.insert(summary.part_session_id.clone())
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
            || document["approved_preview_sha256"] != setup_document["approved_preview_sha256"]
            || !group["approved_run_order_sha256"]
                .as_str()
                .is_some_and(|s| s.len() == 64 && s.bytes().all(|b| b.is_ascii_hexdigit()))
        {
            return Err(invalid(
                "Part linkage or approved ordering differs from its group.",
            ));
        }
        verify_instruction_binding(
            &document["instruction_profile"],
            &order["instruction_profile"],
        )?;
        for (position, (declared, block)) in summary.blocks.iter().zip(part.blocks()).enumerate() {
            let row = occurrences.get(global_position).ok_or_else(|| {
                invalid("Part contains a block absent from the accepted run order.")
            })?;
            let source_index = row["source_block_index"]
                .as_u64()
                .and_then(|n| n.checked_sub(1))
                .and_then(|n| usize::try_from(n).ok())
                .ok_or_else(|| invalid("Invalid accepted source block index."))?;
            let source = source_blocks
                .get(source_index)
                .ok_or_else(|| invalid("Accepted source block is missing."))?;
            let metadata = block.metadata();
            if row["phase_index"].as_i64() != Some(number)
                || row["participant_block_position"].as_u64() != Some((position + 1) as u64)
                || metadata.get("part_number").and_then(Value::as_i64) != Some(number)
                || metadata.get("part_block_number").and_then(Value::as_u64)
                    != Some((position + 1) as u64)
                || metadata.get("global_block_index").and_then(Value::as_u64)
                    != Some((global_position + 1) as u64)
                || metadata.get("source_block_index") != Some(&row["source_block_index"])
                || metadata.get("phase") != Some(&row["phase"])
                || metadata.get("phase_label") != Some(&row["phase_label"])
                || metadata.get("part_session_id").and_then(Value::as_str)
                    != Some(summary.part_session_id.as_str())
                || metadata.get("session_group_id").and_then(Value::as_str) != Some(group_id)
                || row["trial_count"].as_i64() != Some(declared.trial_count)
                || source["trial_count"] != row["trial_count"]
                || row["block_label"].as_str() != Some(declared.label.as_str())
                || source["block_label"] != row["block_label"]
                || metadata.get("prepared_csv_sha256").and_then(Value::as_str)
                    != Some(block.manifest_sha256())
                || metadata.get("prepared_wav_sha256").and_then(Value::as_str)
                    != Some(block.block_wav().sha256())
            {
                return Err(invalid(
                    "Part block identity/order differs from the accepted occurrence.",
                ));
            }
            global_position += 1;
            total_wav_bytes = total_wav_bytes
                .checked_add(block.block_wav().encoded_byte_count())
                .filter(|n| *n <= MAX_TOTAL_PREPARED_BLOCK_WAV_BYTES)
                .ok_or_else(|| invalid("Combined part WAVs exceed the group byte limit."))?;
        }
        parts.push(part);
    }
    if global_position != occurrences.len() {
        return Err(invalid("Part inventory omits accepted block occurrences."));
    }
    Ok(VerifiedPreparedGroup {
        manifest: VerifiedNativeFile {
            path,
            sha256: sha256_bytes(&bytes),
        },
        parts,
    })
}

fn json_digest(value: &Value) -> Result<String, VerificationError> {
    serde_json::to_vec(value)
        .map(|bytes| sha256_bytes(&bytes))
        .map_err(|_| invalid("Cannot hash accepted snapshot."))
}

fn reviewed_digest(value: &Value) -> Result<String, VerificationError> {
    if value["accepted"] != true {
        return Err(invalid("The saved review was not accepted."));
    }
    // The native acceptance receipt seals the preview before toggling this flag.
    let mut preview = value.clone();
    preview["accepted"] = Value::Bool(false);
    json_digest(&preview)
}

fn verify_instruction_binding(actual: &Value, accepted: &Value) -> Result<(), VerificationError> {
    if actual.is_null() && accepted.is_null() {
        return Ok(());
    }
    if actual["schema"] != accepted["schema"] {
        return Err(invalid(
            "Instruction schema differs from the accepted review.",
        ));
    }
    let actual = actual["slots"]
        .as_array()
        .ok_or_else(|| invalid("Prepared instruction inventory is missing."))?;
    let accepted = accepted["slots"]
        .as_array()
        .ok_or_else(|| invalid("Accepted instruction inventory is missing."))?;
    if actual.len() != accepted.len() {
        return Err(invalid(
            "Instruction inventory differs from the accepted review.",
        ));
    }
    for (actual, accepted) in actual.iter().zip(accepted) {
        for key in [
            "slot",
            "enabled",
            "required",
            "label",
            "continue_mode",
            "delay_s",
            "button_label",
            "duration_s",
            "sample_rate",
            "channels",
        ] {
            if actual[key] != accepted[key] {
                return Err(invalid(
                    "Instruction settings differ from the accepted review.",
                ));
            }
        }
        if actual["enabled"] == true && actual["source_asset_sha256"] != accepted["sha256"] {
            return Err(invalid(
                "Instruction source identity differs from the accepted review.",
            ));
        }
    }
    Ok(())
}
