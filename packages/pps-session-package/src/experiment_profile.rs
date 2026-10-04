//! Read-only native verification of the Planner's local JSON ingredient inventory.
//!
//! This is a handoff preflight, not a session assembler or an execution receipt.
//! Paths and digests remain in this native-only value and must be rechecked when
//! an assembler consumes the ingredients.

use std::{
    collections::HashSet,
    fmt, fs,
    path::{Path, PathBuf},
};

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::{read_bounded_bytes, sha256_bytes, sha256_file_bounded, BoundedReadError};

pub const EXPERIMENT_PROFILE_SCHEMA: &str = "pps-experiment-profile.v1";
pub const MAX_EXPERIMENT_PROFILE_BYTES: usize = 8 * 1024 * 1024;
pub const MAX_EXPERIMENT_PROFILE_FILES: usize = 100_000;
pub const MAX_EXPERIMENT_PROFILE_FILE_BYTES: u64 = 8 * 1024 * 1024 * 1024;
pub const MAX_EXPERIMENT_PROFILE_TOTAL_BYTES: u64 = 64 * 1024 * 1024 * 1024;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProfileErrorCode {
    Missing,
    TooLarge,
    Invalid,
    UnsupportedSchema,
    InventoryMissing,
    InventoryLimit,
    IngredientInvalid,
    IngredientMissing,
    IngredientChanged,
    RunSetupMissing,
}

impl ProfileErrorCode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Missing => "profile_missing",
            Self::TooLarge => "profile_too_large",
            Self::Invalid => "profile_invalid",
            Self::UnsupportedSchema => "profile_schema_unsupported",
            Self::InventoryMissing => "profile_inventory_missing",
            Self::InventoryLimit => "profile_inventory_limit",
            Self::IngredientInvalid => "profile_ingredient_invalid",
            Self::IngredientMissing => "profile_ingredient_missing",
            Self::IngredientChanged => "profile_ingredient_changed",
            Self::RunSetupMissing => "profile_run_setup_missing",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ProfileError(ProfileErrorCode);

impl ProfileError {
    pub const fn code(self) -> &'static str {
        self.0.as_str()
    }
}

impl fmt::Display for ProfileError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.0.as_str())
    }
}

impl std::error::Error for ProfileError {}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ExperimentProfileSummary {
    pub schema: &'static str,
    pub profile_id: String,
    pub display_name: String,
    pub source_revision: i64,
    pub ingredient_count: usize,
    pub ingredient_bytes: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VerifiedProfileIngredient {
    path: PathBuf,
    bytes: u64,
    sha256: String,
}

impl VerifiedProfileIngredient {
    pub fn path(&self) -> &Path {
        &self.path
    }

    pub const fn bytes(&self) -> u64 {
        self.bytes
    }

    pub fn sha256(&self) -> &str {
        &self.sha256
    }
}

/// Native-only receipt for the checked inventory. No path-bearing type here
/// implements `Serialize`.
///
/// ```compile_fail
/// fn require_serialize<T: serde::Serialize>() {}
/// require_serialize::<pps_session_package::experiment_profile::VerifiedExperimentProfile>();
/// ```
#[derive(Debug, Clone)]
pub struct VerifiedExperimentProfile {
    summary: ExperimentProfileSummary,
    profile_path: PathBuf,
    profile_sha256: String,
    run_setup_path: PathBuf,
    ingredients: Vec<VerifiedProfileIngredient>,
}

impl VerifiedExperimentProfile {
    pub fn summary(&self) -> &ExperimentProfileSummary {
        &self.summary
    }

    pub fn profile_path(&self) -> &Path {
        &self.profile_path
    }

    pub fn profile_sha256(&self) -> &str {
        &self.profile_sha256
    }

    pub fn run_setup_path(&self) -> &Path {
        &self.run_setup_path
    }

    pub fn ingredients(&self) -> &[VerifiedProfileIngredient] {
        &self.ingredients
    }
}

#[derive(Deserialize)]
struct ProfileDocument {
    schema: String,
    profile_id: String,
    display_name: String,
    source_revision: i64,
    design: Value,
    run_setup_path: String,
    assembly: ProfileAssembly,
    files: Vec<ProfileFile>,
}

#[derive(Deserialize)]
struct ProfileAssembly {
    run_setup: Value,
    block_order: Vec<Value>,
    blocks: Vec<Value>,
}

#[derive(Deserialize)]
struct ProfileFile {
    path: String,
    bytes: u64,
    sha256: String,
}

/// Check the exact local ingredient inventory exported by the Planner.
/// The source files remain mutable; an assembler must recheck these hashes
/// against the bytes it actually consumes.
pub fn verify_experiment_profile_inventory(
    profile_path: &Path,
) -> Result<VerifiedExperimentProfile, ProfileError> {
    if !profile_path.is_file() {
        return Err(ProfileError(ProfileErrorCode::Missing));
    }
    let bytes = read_bounded_bytes(profile_path, MAX_EXPERIMENT_PROFILE_BYTES).map_err(
        |error| match error {
            BoundedReadError::TooLarge => ProfileError(ProfileErrorCode::TooLarge),
            BoundedReadError::Io(_) => ProfileError(ProfileErrorCode::Invalid),
        },
    )?;
    let content = bytes.strip_prefix(&[0xef, 0xbb, 0xbf]).unwrap_or(&bytes);
    let document: ProfileDocument =
        serde_json::from_slice(content).map_err(|_| ProfileError(ProfileErrorCode::Invalid))?;
    if document.schema != EXPERIMENT_PROFILE_SCHEMA {
        return Err(ProfileError(ProfileErrorCode::UnsupportedSchema));
    }
    if !document.design.is_object()
        || document
            .assembly
            .run_setup
            .get("schema")
            .and_then(Value::as_str)
            != Some("pps-experiment-run-setup.v1")
        || document
            .assembly
            .run_setup
            .get("prepared")
            .and_then(Value::as_bool)
            != Some(true)
        || document.assembly.block_order.is_empty()
        || document.assembly.blocks.is_empty()
    {
        return Err(ProfileError(ProfileErrorCode::Invalid));
    }
    if document.files.is_empty() {
        return Err(ProfileError(ProfileErrorCode::InventoryMissing));
    }
    if document.files.len() > MAX_EXPERIMENT_PROFILE_FILES {
        return Err(ProfileError(ProfileErrorCode::InventoryLimit));
    }

    let mut seen = HashSet::with_capacity(document.files.len());
    let mut ingredients = Vec::with_capacity(document.files.len());
    let mut total_bytes = 0_u64;
    for item in document.files {
        let path = PathBuf::from(&item.path);
        if !path.is_absolute()
            || !seen.insert(item.path)
            || item.sha256.len() != 64
            || !item.sha256.bytes().all(|byte| byte.is_ascii_hexdigit())
        {
            return Err(ProfileError(ProfileErrorCode::IngredientInvalid));
        }
        if item.bytes > MAX_EXPERIMENT_PROFILE_FILE_BYTES {
            return Err(ProfileError(ProfileErrorCode::InventoryLimit));
        }
        total_bytes = total_bytes
            .checked_add(item.bytes)
            .filter(|size| *size <= MAX_EXPERIMENT_PROFILE_TOTAL_BYTES)
            .ok_or(ProfileError(ProfileErrorCode::InventoryLimit))?;
        let metadata =
            fs::metadata(&path).map_err(|_| ProfileError(ProfileErrorCode::IngredientMissing))?;
        if !metadata.is_file() || metadata.len() != item.bytes {
            return Err(ProfileError(ProfileErrorCode::IngredientChanged));
        }
        let (actual, read_bytes) = sha256_file_bounded(&path, MAX_EXPERIMENT_PROFILE_FILE_BYTES)
            .map_err(|error| match error {
                BoundedReadError::TooLarge => ProfileError(ProfileErrorCode::InventoryLimit),
                BoundedReadError::Io(_) => ProfileError(ProfileErrorCode::IngredientChanged),
            })?;
        if read_bytes != item.bytes || actual != item.sha256 {
            return Err(ProfileError(ProfileErrorCode::IngredientChanged));
        }
        ingredients.push(VerifiedProfileIngredient {
            path,
            bytes: item.bytes,
            sha256: actual,
        });
    }
    if !seen.contains(&document.run_setup_path) {
        return Err(ProfileError(ProfileErrorCode::RunSetupMissing));
    }
    Ok(VerifiedExperimentProfile {
        summary: ExperimentProfileSummary {
            schema: EXPERIMENT_PROFILE_SCHEMA,
            profile_id: document.profile_id,
            display_name: document.display_name,
            source_revision: document.source_revision,
            ingredient_count: ingredients.len(),
            ingredient_bytes: total_bytes,
        },
        profile_path: profile_path.to_path_buf(),
        profile_sha256: sha256_bytes(&bytes),
        run_setup_path: PathBuf::from(document.run_setup_path),
        ingredients,
    })
}
