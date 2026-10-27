//! Native, bounded portable-profile materialization. Call from a blocking worker
//! with an app-authorized source and a new destination under app-owned storage.
//! Original inventory bytes are preserved; local rebinding is recorded separately.
use serde::Deserialize;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, File, OpenOptions},
    io::{Read, Seek, SeekFrom, Write},
    path::{Path, PathBuf},
    sync::atomic::{AtomicBool, AtomicU64, Ordering},
};
use zip::{CompressionMethod, ZipArchive};

const MAX_FILES: usize = 1_024;
const MAX_JSON: u64 = 8 * 1024 * 1024;
const MAX_ARCHIVE: u64 = 768 * 1024 * 1024;
const MAX_ASSET: u64 = 256 * 1024 * 1024;
const MAX_TOTAL: u64 = 1024 * 1024 * 1024;
static STAGING_SEQUENCE: AtomicU64 = AtomicU64::new(1);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProfileBundleError {
    InvalidArchive,
    ResourceLimit,
    InvalidInventory,
    InvalidProfile,
    InvalidAsset,
    MissingAsset,
    UnsafePath,
    DestinationExists,
    Cancelled,
    Io,
}
impl std::fmt::Display for ProfileBundleError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{self:?}")
    }
}
impl std::error::Error for ProfileBundleError {}
type Result<T> = std::result::Result<T, ProfileBundleError>;
fn io<T>(value: std::io::Result<T>) -> Result<T> {
    value.map_err(|_| ProfileBundleError::Io)
}
fn check_cancel(cancelled: &AtomicBool) -> Result<()> {
    if cancelled.load(Ordering::Acquire) {
        Err(ProfileBundleError::Cancelled)
    } else {
        Ok(())
    }
}

/// Path-bearing native receipt; deliberately not serializable to remote callers.
#[derive(Debug)]
pub struct VerifiedProfileAsset {
    pub logical_id: String,
    pub source_name: String,
    pub media_type: String,
    pub path: PathBuf,
    pub sha256: String,
    pub bytes: u64,
}
#[derive(Debug)]
pub struct VerifiedProfileBundle {
    profile_id: String,
    display_name: String,
    design: Value,
    assets: Vec<VerifiedProfileAsset>,
}
impl VerifiedProfileBundle {
    pub fn profile_id(&self) -> &str {
        &self.profile_id
    }
    pub fn display_name(&self) -> &str {
        &self.display_name
    }
    /// Native-only JSON with resolved paths. The host must project asset IDs,
    /// not forward this value to a remote/hosted surface.
    pub fn rebased_design(&self) -> &Value {
        &self.design
    }
    pub fn assets(&self) -> &[VerifiedProfileAsset] {
        &self.assets
    }
}

#[derive(Deserialize)]
struct Inventory {
    path: String,
    sha256: String,
    bytes: u64,
}
#[derive(Deserialize)]
struct Manifest {
    schema: String,
    profile_id: String,
    profile_kind: String,
    files: Vec<Inventory>,
}
#[derive(Deserialize)]
struct Asset {
    logical_id: String,
    path: String,
    sha256: String,
    bytes: u64,
    #[serde(default)]
    media_type: String,
    #[serde(default)]
    source_name: String,
}
#[derive(Deserialize)]
struct Profile {
    schema: String,
    profile_id: String,
    profile_kind: String,
    display_name: String,
    design: Value,
    #[serde(default)]
    assets: Vec<Asset>,
}

fn component(name: &str) -> bool {
    if name.is_empty()
        || name.len() > 180
        || matches!(name, "." | "..")
        || name.ends_with('.')
        || !name
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || b"._-".contains(&c))
    {
        return false;
    }
    let stem = name
        .split('.')
        .next()
        .unwrap_or_default()
        .to_ascii_uppercase();
    !matches!(
        stem.as_str(),
        "CON"
            | "PRN"
            | "AUX"
            | "NUL"
            | "COM1"
            | "COM2"
            | "COM3"
            | "COM4"
            | "COM5"
            | "COM6"
            | "COM7"
            | "COM8"
            | "COM9"
            | "LPT1"
            | "LPT2"
            | "LPT3"
            | "LPT4"
            | "LPT5"
            | "LPT6"
            | "LPT7"
            | "LPT8"
            | "LPT9"
    )
}
fn member(name: &str) -> bool {
    matches!(
        name,
        "manifest.json" | "profile.json" | "trajectories/snapshots.json"
    ) || name.strip_prefix("assets/").is_some_and(component)
}
fn digest_valid(hash: &str) -> bool {
    hash.len() == 64
        && hash
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}

/// Bound metadata before the ZIP parser allocates it. Existing browser/Python
/// bundles fit ordinary single-disk ZIP; ZIP64/multipart archives are rejected.
fn preflight(file: &mut File) -> Result<usize> {
    let length = io(file.metadata())?.len();
    if !(22..=MAX_ARCHIVE).contains(&length) {
        return Err(ProfileBundleError::ResourceLimit);
    }
    let tail_len = length.min(65_557) as usize;
    io(file.seek(SeekFrom::End(-(tail_len as i64))))?;
    let mut tail = vec![0; tail_len];
    io(file.read_exact(&mut tail))?;
    let index = (0..=tail_len - 22)
        .rev()
        .find(|&i| {
            tail[i..i + 4] == [0x50, 0x4b, 0x05, 0x06]
                && i + 22 + u16::from_le_bytes([tail[i + 20], tail[i + 21]]) as usize == tail_len
        })
        .ok_or(ProfileBundleError::InvalidArchive)?;
    let word = |offset| u16::from_le_bytes([tail[index + offset], tail[index + offset + 1]]);
    let dword =
        |offset| u32::from_le_bytes(tail[index + offset..index + offset + 4].try_into().unwrap());
    let count = word(10) as usize;
    if word(4) != 0
        || word(6) != 0
        || word(8) as usize != count
        || !(2..=MAX_FILES).contains(&count)
        || u64::from(dword(12)) > MAX_JSON
        || u64::from(dword(16)) + u64::from(dword(12)) != length - tail_len as u64 + index as u64
    {
        return Err(ProfileBundleError::ResourceLimit);
    }
    io(file.seek(SeekFrom::Start(0)))?;
    let mut signature = [0; 4];
    io(file.read_exact(&mut signature))?;
    if signature != [0x50, 0x4b, 0x03, 0x04] {
        return Err(ProfileBundleError::InvalidArchive);
    }
    io(file.seek(SeekFrom::Start(0)))?;
    Ok(count)
}

struct Staging {
    path: PathBuf,
    parent: PathBuf,
    published: bool,
}
impl Staging {
    fn create(parent: &Path) -> Result<Self> {
        for _ in 0..16 {
            let path = parent.join(format!(
                ".pps-import-{}-{}",
                std::process::id(),
                STAGING_SEQUENCE.fetch_add(1, Ordering::Relaxed)
            ));
            match fs::create_dir(&path) {
                Ok(()) => {
                    return Ok(Self {
                        path,
                        parent: parent.to_path_buf(),
                        published: false,
                    })
                }
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
                Err(_) => return Err(ProfileBundleError::Io),
            }
        }
        Err(ProfileBundleError::Io)
    }
}
impl Drop for Staging {
    fn drop(&mut self) {
        if !self.published
            && fs::canonicalize(&self.path)
                .ok()
                .is_some_and(|path| path.parent() == Some(self.parent.as_path()))
        {
            let _ = fs::remove_dir_all(&self.path);
        }
    }
}

fn read_json(archive: &mut ZipArchive<File>, name: &str) -> Result<Vec<u8>> {
    let entry = archive
        .by_name(name)
        .map_err(|_| ProfileBundleError::InvalidArchive)?;
    if entry.size() > MAX_JSON {
        return Err(ProfileBundleError::ResourceLimit);
    }
    let mut bytes = Vec::new();
    io(entry.take(MAX_JSON + 1).read_to_end(&mut bytes))?;
    if bytes.len() as u64 > MAX_JSON {
        return Err(ProfileBundleError::ResourceLimit);
    }
    Ok(bytes)
}
fn audio_header(bytes: &[u8]) -> bool {
    (bytes.len() >= 12
        && (bytes.starts_with(b"RIFF") || bytes.starts_with(b"RF64"))
        && &bytes[8..12] == b"WAVE")
        || bytes.starts_with(b"fLaC")
        || bytes.starts_with(b"OggS")
        || bytes.starts_with(b"ID3")
        || (bytes.len() > 1 && bytes[0] == 0xff && bytes[1] & 0xe0 == 0xe0)
        || (bytes.len() >= 12 && &bytes[4..8] == b"ftyp")
}

fn rebind_group(group: &mut Value, field: &str, assets: &BTreeMap<String, PathBuf>) -> Result<()> {
    if group.is_null() {
        return Ok(());
    }
    for item in group
        .as_array_mut()
        .ok_or(ProfileBundleError::InvalidProfile)?
    {
        let item = item
            .as_object_mut()
            .ok_or(ProfileBundleError::InvalidProfile)?;
        let path = item
            .get(field)
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_owned();
        // A secondary comparator belongs to the noise but has its own identity.
        let primary = field != "native_stationary_baseline_asset";
        let id = item
            .get("browser_asset_id")
            .filter(|_| primary)
            .and_then(Value::as_str)
            .filter(|id| !id.is_empty());
        let path_id = path.strip_prefix("browser-asset:");
        if id.is_some() && path_id.is_some() && id != path_id {
            return Err(ProfileBundleError::MissingAsset);
        }
        if path.is_empty() && id.is_none() {
            continue;
        }
        let key = id.or(path_id).unwrap_or(&path);
        let bound = assets.get(key).ok_or(ProfileBundleError::MissingAsset)?;
        item.insert(
            field.to_owned(),
            Value::String(
                bound
                    .to_str()
                    .ok_or(ProfileBundleError::UnsafePath)?
                    .to_owned(),
            ),
        );
        if primary {
            item.remove("browser_asset_id");
        }
    }
    Ok(())
}

/// Verify every inventory member and asset before atomically exposing the new
/// directory. On error/cancellation only this call's staging tree is removed.
/// A completed rename is the publication point; late cancellation cannot turn
/// a successful import into an unpublished result. Decoding/scientific fitness
/// are separate generation gates; hashes and recognizable media are not those claims.
pub fn materialize_profile_bundle(
    source: &Path,
    destination: &Path,
    cancelled: &AtomicBool,
) -> Result<VerifiedProfileBundle> {
    check_cancel(cancelled)?;
    if fs::symlink_metadata(destination).is_ok() {
        return Err(ProfileBundleError::DestinationExists);
    }
    let parent = io(fs::canonicalize(
        destination.parent().ok_or(ProfileBundleError::UnsafePath)?,
    ))?;
    let name = destination
        .file_name()
        .and_then(|name| name.to_str())
        .filter(|name| component(name))
        .ok_or(ProfileBundleError::UnsafePath)?;
    let destination = parent.join(name);
    let mut input = io(File::open(source))?;
    if !io(input.metadata())?.is_file() {
        return Err(ProfileBundleError::InvalidArchive);
    }
    let expected_count = preflight(&mut input)?;
    let mut archive = ZipArchive::new(input).map_err(|_| ProfileBundleError::InvalidArchive)?;
    if archive.len() != expected_count || archive.has_duplicate_names() || archive.offset() != 0 {
        return Err(ProfileBundleError::InvalidArchive);
    }
    let mut members = BTreeMap::new();
    let mut folded = BTreeSet::new();
    let mut total = 0_u64;
    for i in 0..archive.len() {
        check_cancel(cancelled)?;
        let entry = archive
            .by_index(i)
            .map_err(|_| ProfileBundleError::InvalidArchive)?;
        let name = entry
            .name()
            .map_err(|_| ProfileBundleError::UnsafePath)?
            .into_owned();
        if !member(&name)
            || !folded.insert(name.to_ascii_lowercase())
            || entry.is_dir()
            || entry.is_symlink()
            || entry
                .unix_mode()
                .is_some_and(|mode| ![0, 0o100000].contains(&(mode & 0o170000)))
        {
            return Err(ProfileBundleError::UnsafePath);
        }
        if entry.encrypted()
            || !matches!(
                entry.compression(),
                CompressionMethod::Stored | CompressionMethod::Deflated
            )
        {
            return Err(ProfileBundleError::InvalidArchive);
        }
        let cap = if name.starts_with("assets/") {
            MAX_ASSET
        } else {
            MAX_JSON
        };
        total = total
            .checked_add(entry.size())
            .filter(|total| *total <= MAX_TOTAL)
            .ok_or(ProfileBundleError::ResourceLimit)?;
        if entry.size() > cap {
            return Err(ProfileBundleError::ResourceLimit);
        }
        members.insert(name, entry.size());
    }
    let manifest_bytes = read_json(&mut archive, "manifest.json")?;
    let manifest: Manifest = serde_json::from_slice(&manifest_bytes)
        .map_err(|_| ProfileBundleError::InvalidInventory)?;
    if manifest.schema != "pps-profile-bundle.v1"
        || manifest.profile_kind != "custom"
        || !component(&manifest.profile_id)
        || manifest.files.len() + 1 != members.len()
    {
        return Err(ProfileBundleError::InvalidInventory);
    }
    let mut inventory = BTreeMap::new();
    for file in manifest.files {
        if file.path == "manifest.json"
            || !digest_valid(&file.sha256)
            || members.get(&file.path) != Some(&file.bytes)
            || inventory.insert(file.path.clone(), file).is_some()
        {
            return Err(ProfileBundleError::InvalidInventory);
        }
    }
    let profile_bytes = read_json(&mut archive, "profile.json")?;
    let expected = inventory
        .get("profile.json")
        .ok_or(ProfileBundleError::InvalidInventory)?;
    if profile_bytes.len() as u64 != expected.bytes
        || format!("{:x}", Sha256::digest(&profile_bytes)) != expected.sha256
    {
        return Err(ProfileBundleError::InvalidInventory);
    }
    let mut profile: Profile =
        serde_json::from_slice(&profile_bytes).map_err(|_| ProfileBundleError::InvalidProfile)?;
    if profile.schema != "pps-study-profile.v1"
        || profile.profile_kind != "custom"
        || profile.profile_id != manifest.profile_id
        || !profile.design.is_object()
        || profile.display_name.len() > 1024
        || profile.assets.len() > MAX_FILES
    {
        return Err(ProfileBundleError::InvalidProfile);
    }
    let mut ids = BTreeSet::new();
    let mut asset_members = BTreeSet::new();
    for asset in &profile.assets {
        let record = inventory
            .get(&asset.path)
            .ok_or(ProfileBundleError::InvalidAsset)?;
        if !component(&asset.logical_id)
            || !ids.insert(asset.logical_id.clone())
            || !asset.path.starts_with("assets/")
            || asset.sha256 != record.sha256
            || asset.bytes != record.bytes
            || asset.source_name.len() > 1024
            || asset.media_type.len() > 128
        {
            return Err(ProfileBundleError::InvalidAsset);
        }
        asset_members.insert(asset.path.clone());
    }
    if inventory
        .keys()
        .any(|name| name.starts_with("assets/") && !asset_members.contains(name))
    {
        return Err(ProfileBundleError::InvalidAsset);
    }
    let mut staging = Staging::create(&parent)?;
    let mut originals = BTreeMap::new();
    originals.insert("manifest.json".to_owned(), manifest_bytes);
    originals.insert("profile.json".to_owned(), profile_bytes);
    for (name, size) in &members {
        check_cancel(cancelled)?;
        let target = staging.path.join(name);
        io(fs::create_dir_all(
            target.parent().ok_or(ProfileBundleError::UnsafePath)?,
        ))?;
        let mut output = io(OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&target))?;
        if let Some(bytes) = originals.get(name) {
            io(output.write_all(bytes))?;
        } else {
            let mut entry = archive
                .by_name(name)
                .map_err(|_| ProfileBundleError::InvalidArchive)?;
            let mut hash = Sha256::new();
            let mut count = 0_u64;
            let mut buffer = [0_u8; 64 * 1024];
            let mut header = Vec::new();
            loop {
                check_cancel(cancelled)?;
                let read = io(entry.read(&mut buffer))?;
                if read == 0 {
                    break;
                }
                count = count
                    .checked_add(read as u64)
                    .filter(|count| *count <= *size)
                    .ok_or(ProfileBundleError::ResourceLimit)?;
                if header.len() < 16 {
                    header.extend_from_slice(&buffer[..read.min(16 - header.len())]);
                }
                hash.update(&buffer[..read]);
                io(output.write_all(&buffer[..read]))?;
            }
            let record = inventory
                .get(name)
                .ok_or(ProfileBundleError::InvalidInventory)?;
            if count != record.bytes || format!("{:x}", hash.finalize()) != record.sha256 {
                return Err(ProfileBundleError::InvalidInventory);
            }
            if name.starts_with("assets/") && !audio_header(&header) {
                return Err(ProfileBundleError::InvalidAsset);
            }
        }
        io(output.sync_all())?;
    }
    let mut bindings = BTreeMap::new();
    let mut assets = Vec::new();
    for asset in profile.assets {
        let path = destination.join(&asset.path);
        bindings.insert(asset.logical_id.clone(), path.clone());
        bindings.insert(asset.path.clone(), path.clone());
        assets.push(VerifiedProfileAsset {
            logical_id: asset.logical_id,
            source_name: asset.source_name,
            media_type: asset.media_type,
            path,
            sha256: asset.sha256,
            bytes: asset.bytes,
        });
    }
    for (group, field) in [
        ("noises", "prebaked_path"),
        ("noises", "native_stationary_baseline_asset"),
        ("custom_looming_files", "path"),
        ("prestimulus_files", "path"),
    ] {
        if let Some(value) = profile.design.get_mut(group) {
            rebind_group(value, field, &bindings)?;
        }
    }
    if let Some(slots) = profile.design.pointer_mut(
        "/study_profile_reference_parameters/dashboard_run_setup/instruction_profile/slots",
    ) {
        rebind_group(slots, "path", &bindings)?;
    }
    let record = serde_json::json!({"schema":"pps-materialized-profile.v1","profile_id":profile.profile_id,"design":profile.design,"original_profile_sha256":expected.sha256,"qualification":"not_assessed"});
    let mut output = io(OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(staging.path.join("materialized-profile.json")))?;
    io(output.write_all(
        &serde_json::to_vec_pretty(&record).map_err(|_| ProfileBundleError::InvalidProfile)?,
    ))?;
    io(output.sync_all())?;
    drop(output);
    check_cancel(cancelled)?;
    if fs::symlink_metadata(&destination).is_ok() {
        return Err(ProfileBundleError::DestinationExists);
    }
    io(fs::rename(&staging.path, &destination))?;
    staging.published = true;
    Ok(VerifiedProfileBundle {
        profile_id: profile.profile_id,
        display_name: profile.display_name,
        design: profile.design,
        assets,
    })
}
