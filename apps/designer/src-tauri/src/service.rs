use crate::{
    generation,
    jobs::{JobOwner, JobSnapshot, JobTicket},
};
use pps_designer_core::design::{self, GenerationOptIn, IngredientGenerationPlan};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs,
    io::Write,
    path::{Component, Path, PathBuf},
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        Arc, Mutex,
    },
};

const MAX_JSON: usize = 8 * 1024 * 1024;
const MAX_AUDIO: u64 = 64 * 1024 * 1024;
const HRTF: &str =
    "assets/0. Head-Related Impulse Response (HRIR) model/FABIAN_HRIR_measured_HATO_0.sofa";
static SEQUENCE: AtomicU64 = AtomicU64::new(1);
pub type Shared = Arc<Mutex<DesignerService>>;
pub type Result<T> = std::result::Result<T, String>;

#[derive(Clone, Serialize, Deserialize)]
struct AssetRecord {
    relative_path: String,
    sha256: String,
    source_name: String,
    dry_source: bool,
}
#[derive(Default, Serialize, Deserialize)]
struct Stored {
    snapshot: Option<Value>,
    assets: BTreeMap<String, AssetRecord>,
}

// Constructed only after the importer successfully created this new app-owned
// directory. Never used to clean up a caller's existing directory.
struct ImportDirectory(Option<PathBuf>);
impl ImportDirectory {
    fn remove(&mut self) -> Result<()> {
        if let Some(path) = self.0.as_ref() {
            fs::remove_dir_all(path).map_err(|_| "import_cleanup_failed")?;
            self.0 = None;
        }
        Ok(())
    }
}
impl Drop for ImportDirectory {
    fn drop(&mut self) {
        let _ = self.remove();
    }
}

pub struct DesignerService {
    pub jobs: JobOwner,
    pub(crate) review: Option<crate::assembly_host::Review>,
    pub(crate) accepted: Option<Arc<crate::assembly_host::Accepted>>,
    pub(crate) prepared_directory: Option<PathBuf>,
    stored: Stored,
    root: PathBuf,
    resources: PathBuf,
    renderer: PathBuf,
}

impl DesignerService {
    pub fn open(root: PathBuf, resources: PathBuf, renderer: PathBuf) -> Result<Self> {
        fs::create_dir_all(root.join("assets")).map_err(|_| "storage_unavailable")?;
        let stored = if root.join("draft.json").exists() {
            serde_json::from_slice(&read_bounded(&root.join("draft.json"), MAX_JSON as u64)?)
                .map_err(|_| "saved_draft_invalid")?
        } else {
            Stored::default()
        };
        Ok(Self {
            jobs: JobOwner::default(),
            review: None,
            accepted: None,
            prepared_directory: None,
            stored,
            root: fs::canonicalize(root).map_err(|_| "storage_unavailable")?,
            resources,
            renderer,
        })
    }

    pub fn snapshot(&self) -> Value {
        let mut snapshot = self.stored.snapshot.clone();
        if let Some(value) = snapshot.as_mut() {
            if value["native_execution_review"].is_object() {
                value["native_execution_review"]["available"] = json!(self.review.is_some());
                value["native_execution_review"]["accepted"] = json!(self.accepted.is_some());
            }
        }
        json!({"revision":self.jobs.revision(), "snapshot":snapshot, "capabilities":pps_designer_core::generation_capabilities()})
    }

    pub fn invalidate(&mut self, expected: u64) -> Result<u64> {
        let revision = self.jobs.revise(expected).map_err(str::to_owned)?;
        self.clear_authority();
        Ok(revision)
    }

    pub fn save(&mut self, expected: u64, snapshot: Value) -> Result<u64> {
        bound_snapshot(&snapshot)?;
        if self.jobs.revision() != expected {
            return Err("revision_conflict".into());
        }
        self.persist(&snapshot, &self.stored.assets)?;
        self.jobs.revise(expected).map_err(str::to_owned)?;
        self.clear_authority();
        self.stored.snapshot = Some(snapshot);
        Ok(self.jobs.revision())
    }

    fn clear_authority(&mut self) {
        self.review = None;
        self.accepted = None;
        self.prepared_directory = None;
    }

    pub(crate) fn publish_snapshot(&mut self, snapshot: Value) -> Result<()> {
        self.persist(&snapshot, &self.stored.assets)?;
        self.stored.snapshot = Some(snapshot);
        Ok(())
    }

    pub(crate) fn authorize_assembly_asset(&self, reference: &str) -> Result<(PathBuf, String)> {
        if let Some(asset) = self.stored.assets.get(reference) {
            return Ok((
                safe_join(&self.root, &asset.relative_path)?,
                asset.sha256.clone(),
            ));
        }
        let key = reference.trim_start_matches('/');
        let path = safe_join(&self.resources, key)?;
        let expected = if key.starts_with("assets/preloads/") {
            let inventory: Value = serde_json::from_slice(&read_bounded(
                &self
                    .resources
                    .join("assets/preloads/preload_inventory.json"),
                MAX_JSON as u64,
            )?)
            .map_err(|_| "preload_inventory_invalid")?;
            inventory["profiles"]
                .as_array()
                .into_iter()
                .flatten()
                .flat_map(|p| p["assets"].as_array().into_iter().flatten())
                .find(|asset| asset["path"] == key)
                .and_then(|asset| asset["sha256"].as_str())
                .map(str::to_owned)
        } else if key.starts_with("assets/breathing/") {
            let manifest = path
                .parent()
                .ok_or("asset_not_authorized")?
                .join("spoken_assets_manifest.json");
            let value: Value = serde_json::from_slice(&read_bounded(&manifest, MAX_JSON as u64)?)
                .map_err(|_| "spoken_inventory_invalid")?;
            value["files"][path
                .file_name()
                .and_then(|s| s.to_str())
                .ok_or("asset_not_authorized")?]["sha256"]
                .as_str()
                .map(str::to_owned)
        } else {
            None
        };
        Ok((path, expected.ok_or("assembly_asset_not_authorized")?))
    }

    fn persist(&self, snapshot: &Value, assets: &BTreeMap<String, AssetRecord>) -> Result<()> {
        let bytes = serde_json::to_vec(&Stored {
            snapshot: Some(snapshot.clone()),
            assets: assets.clone(),
        })
        .map_err(|_| "snapshot_serialization_failed")?;
        if bytes.len() > MAX_JSON {
            return Err("snapshot_limit".into());
        }
        let temporary = self.root.join("draft.next.json");
        let mut file = fs::File::create(&temporary).map_err(|_| "draft_write_failed")?;
        file.write_all(&bytes)
            .and_then(|_| file.sync_all())
            .map_err(|_| "draft_write_failed")?;
        fs::rename(temporary, self.root.join("draft.json"))
            .map_err(|_| "draft_commit_failed".into())
    }

    pub fn resource(&self, key: &str) -> Result<(Vec<u8>, &'static str)> {
        if key.starts_with("native-assets/") {
            let asset = self.stored.assets.get(key).ok_or("asset_not_authorized")?;
            let bytes = read_bounded(&safe_join(&self.root, &asset.relative_path)?, MAX_AUDIO)?;
            if sha(&bytes) != asset.sha256 {
                return Err("asset_hash_mismatch".into());
            }
            return Ok((bytes, "audio/wav"));
        }
        if !(key.starts_with("assets/preloads/")
            || key.starts_with("assets/breathing/")
            || key.starts_with("study_templates/"))
        {
            return Err("resource_not_allowed".into());
        }
        let mime = if key.ends_with(".wav") {
            "audio/wav"
        } else if key.ends_with(".json") {
            "application/json"
        } else {
            return Err("resource_not_allowed".into());
        };
        Ok((
            read_bounded(&safe_join(&self.resources, key)?, MAX_AUDIO)?,
            mime,
        ))
    }

    pub fn register_picked_audio(&mut self, path: &Path) -> Result<Value> {
        let bytes = read_bounded(path, MAX_AUDIO)?;
        // Decode before issuing authority; the generation core performs exact rate/channel policy checks later.
        let mut reader =
            hound::WavReader::new(std::io::Cursor::new(&bytes)).map_err(|_| "wav_required")?;
        let spec = reader.spec();
        if ![1, 2].contains(&spec.channels)
            || reader.duration() == 0
            || !(8_000..=192_000).contains(&spec.sample_rate)
            || reader.duration() as u64 > u64::from(spec.sample_rate) * 60
        {
            return Err("bounded_mono_or_stereo_wav_required".into());
        }
        match spec.sample_format {
            hound::SampleFormat::Float => {
                for sample in reader.samples::<f32>() {
                    if !sample.map_err(|_| "invalid_wav")?.is_finite() {
                        return Err("invalid_wav".into());
                    }
                }
            }
            hound::SampleFormat::Int => {
                for sample in reader.samples::<i32>() {
                    sample.map_err(|_| "invalid_wav")?;
                }
            }
        }
        let name = path
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("Audio.wav");
        let (key, record) = self.store_audio(&bytes, name, true)?;
        self.stored.assets.insert(key.clone(), record);
        Ok(
            json!({"path":key,"source_input_path":key,"sha256":sha(&bytes),"label":name.trim_end_matches(".wav"),
            "duration_s": reader.duration() as f64 / spec.sample_rate as f64, "sample_rate":spec.sample_rate,"channels":spec.channels,
            "channel_policy":if spec.channels == 1 {"mono"} else {"stereo_mean"},"length_policy":"exact"}),
        )
    }

    fn store_audio(
        &self,
        bytes: &[u8],
        name: &str,
        dry_source: bool,
    ) -> Result<(String, AssetRecord)> {
        self.store_audio_using(bytes, name, dry_source, |file| file.write_all(bytes))
    }

    fn store_audio_using(
        &self,
        bytes: &[u8],
        name: &str,
        dry_source: bool,
        write: impl FnOnce(&mut fs::File) -> std::io::Result<()>,
    ) -> Result<(String, AssetRecord)> {
        let digest = sha(bytes);
        let relative = format!("assets/{digest}.wav");
        let path = self.root.join(&relative);
        let staging = self.root.join("assets").join(format!(
            ".{digest}-{}-{}.pending",
            std::process::id(),
            SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ));
        let mut file = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&staging)
            .map_err(|_| "asset_write_failed")?;
        let written = write(&mut file).and_then(|_| file.sync_all());
        drop(file);
        if written.is_err() {
            let _ = fs::remove_file(&staging);
            return Err("asset_write_failed".into());
        }
        // Exclusive publication cannot replace another valid content-addressed
        // asset. A failed write never occupies the final digest path.
        let published = fs::hard_link(&staging, &path);
        let _ = fs::remove_file(&staging);
        match published {
            Ok(()) => (),
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
                if sha(&read_bounded(&path, MAX_AUDIO)?) != digest {
                    return Err("asset_hash_mismatch".into());
                }
            }
            Err(_) => return Err("asset_write_failed".into()),
        }
        Ok((
            format!("native-assets/{digest}.wav"),
            AssetRecord {
                relative_path: relative,
                sha256: digest,
                source_name: name.into(),
                dry_source,
            },
        ))
    }

    pub fn import_bundle(&mut self, expected: u64, source: &Path) -> Result<Value> {
        if expected != self.jobs.revision() {
            return Err("revision_conflict".into());
        }
        let target = self.root.join(format!(
            "import-{}-{}",
            std::process::id(),
            SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ));
        let receipt = pps_session_package::materialize_profile_bundle(
            source,
            &target,
            &AtomicBool::new(false),
        )
        .map_err(|error| format!("profile_{error}"))?;
        let mut extracted = ImportDirectory(Some(target));
        let mut design = receipt.rebased_design().clone();
        let mut replacements = BTreeMap::new();
        let mut records = BTreeMap::new();
        let mut assets = Vec::new();
        for asset in receipt.assets() {
            let bytes = read_bounded(&asset.path, MAX_AUDIO)?;
            if sha(&bytes) != asset.sha256 {
                return Err("asset_hash_mismatch".into());
            }
            let (key, record) = self.store_audio(&bytes, &asset.source_name, false)?;
            replacements.insert(asset.path.to_string_lossy().into_owned(), key.clone());
            records.insert(key.clone(), record);
            assets.push(json!({"path":key,"sha256":asset.sha256,"label":asset.source_name}));
        }
        replace_references(&mut design, &replacements);
        extracted.remove()?;
        self.jobs.revise(expected).map_err(str::to_owned)?;
        self.stored.assets.extend(records);
        self.clear_authority();
        Ok(
            json!({"revision":self.jobs.revision(),"design":design,"assets":assets,"display_name":receipt.display_name()}),
        )
    }

    pub fn begin(
        &mut self,
        expected: u64,
        snapshot: Value,
        payload: Value,
        opt_in: GenerationOptIn,
    ) -> Result<(JobSnapshot, Work)> {
        #[cfg(debug_assertions)]
        if std::env::var_os("PPS_DESIGNER_TEST_DATA").is_some() {
            let capture = json!({"payload":payload,"opt_in":opt_in});
            fs::write(
                self.root.join("last-generation-request.json"),
                serde_json::to_vec_pretty(&capture).map_err(|_| "test_capture_failed")?,
            )
            .map_err(|_| "test_capture_failed")?;
        }
        bound_snapshot(&snapshot)?;
        if snapshot["custom_workflow"]["is_custom"] != true
            || snapshot["custom_workflow"]["is_finalized"] == true
        {
            return Err("editable_custom_draft_required".into());
        }
        let plan = design::plan_ingredient_generation(&payload, &opt_in)
            .map_err(|error| format!("{} ({}): {}", error.code, error.field, error.message))?;
        self.begin_plan(expected, snapshot, NativePlan::Ingredient(plan))
    }

    pub fn begin_baseline(
        &mut self,
        expected: u64,
        snapshot: Value,
        source: &str,
        opt_in: &pps_designer_core::baseline::BaselineGenerationOptIn,
    ) -> Result<(JobSnapshot, Work)> {
        bound_snapshot(&snapshot)?;
        if snapshot["custom_workflow"]["is_custom"] != true
            || snapshot["custom_workflow"]["is_finalized"] == true
        {
            return Err("editable_custom_draft_required".into());
        }
        let plan = pps_designer_core::baseline::plan_stationary_baseline(
            &snapshot["design"],
            source,
            opt_in,
        )
        .map_err(|error| format!("{} ({}): {}", error.code, error.field, error.message))?;
        self.begin_plan(expected, snapshot, NativePlan::Baseline(plan))
    }

    fn begin_plan(
        &mut self,
        expected: u64,
        snapshot: Value,
        native_plan: NativePlan,
    ) -> Result<(JobSnapshot, Work)> {
        let plan = native_plan.generation();
        if plan.request.duration_s * f64::from(plan.request.sample_rate_hz)
            > ((MAX_AUDIO - 4096) / 8) as f64
        {
            return Err("native_audio_asset_limit".into());
        }
        if plan.request.sample_rate_hz != 44100 {
            return Err("bundled_hrtf_requires_44100_hz".into());
        }
        let reference = plan.renderer.hrtf_reference.replace('\\', "/");
        if reference != HRTF && reference != format!("packages/pps-resources/{HRTF}") {
            return Err("bundled_hrtf_required".into());
        }
        let hrtf = safe_join(&self.resources, HRTF)?;
        if !self.renderer.is_file() {
            return Err("renderer_unavailable".into());
        }
        let imported = if let Some(reference) = &plan.source_input_reference {
            let asset = self
                .stored
                .assets
                .get(reference)
                .filter(|asset| asset.dry_source)
                .ok_or("dry_source_picker_required")?;
            let bytes = read_bounded(&safe_join(&self.root, &asset.relative_path)?, MAX_AUDIO)?;
            if sha(&bytes) != asset.sha256 {
                return Err("asset_hash_mismatch".into());
            }
            Some(bytes)
        } else {
            None
        };
        let ticket = self.jobs.start(expected).map_err(str::to_owned)?;
        self.clear_authority();
        let directory = self.root.join(format!(
            "generation-{}-{}",
            std::process::id(),
            SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ));
        if fs::create_dir(&directory).is_err() {
            self.jobs.finish(
                &ticket,
                "failed",
                "Could not create staging directory",
                None,
            );
            return Err("staging_unavailable".into());
        }
        let job = self
            .jobs
            .snapshot(&ticket.id.to_string())
            .ok_or("job_missing")?;
        Ok((
            job,
            Work {
                ticket,
                plan: native_plan,
                snapshot,
                directory,
                executable: self.renderer.clone(),
                hrtf,
                imported,
            },
        ))
    }
}

pub struct Work {
    ticket: JobTicket,
    plan: NativePlan,
    snapshot: Value,
    directory: PathBuf,
    executable: PathBuf,
    hrtf: PathBuf,
    imported: Option<Vec<u8>>,
}
enum NativePlan {
    Ingredient(IngredientGenerationPlan),
    Baseline(pps_designer_core::baseline::StationaryBaselineGenerationPlan),
}
impl NativePlan {
    fn generation(&self) -> &IngredientGenerationPlan {
        match self {
            Self::Ingredient(plan) => plan,
            Self::Baseline(plan) => &plan.generation,
        }
    }
}
pub(crate) fn fail_job(shared: &Shared, ticket: &JobTicket, error: String) {
    if let Ok(mut owner) = shared.lock() {
        owner.jobs.finish(
            ticket,
            "failed",
            "Native work failed; no output published",
            Some(json!({"error":error})),
        );
    }
}
pub fn execute(shared: Shared, work: Work) {
    let plan = work.plan.generation();
    let result = generation::render(plan, &work.directory, &work.executable, &work.hrtf, work.imported.as_deref(), &work.ticket.cancel)
        .and_then(|(bytes, stimulus, report)| {
            let key = format!("native-assets/{}.wav", sha(&bytes));
            let (design, asset, source, minimum_invalidated) = match &work.plan {
                NativePlan::Ingredient(plan) => {
                    let entry = design::generated_ingredient_entry(plan, &key, &bytes, &stimulus, &report, &work.ticket.cancel).map_err(|e|e.to_string())?;
                    let publication = design::apply_generated_ingredient(plan, &entry).map_err(|e|e.to_string())?;
                    (publication.design, publication.asset, entry.source().clone(), 2)
                },
                NativePlan::Baseline(plan) => {
                    let entry = pps_designer_core::baseline::generated_stationary_baseline_entry(plan, &key, &bytes, &stimulus, &report, &work.ticket.cancel).map_err(|e|e.to_string())?;
                    let publication = pps_designer_core::baseline::apply_generated_stationary_baseline(plan, &entry).map_err(|e|e.to_string())?;
                    (publication.design, publication.asset, Value::Null, 3)
                },
            };
            let mut owner = shared.lock().map_err(|_| "host_unavailable")?;
            owner.jobs.publish(&work.ticket, || Ok(())).map_err(str::to_owned)?;
            let (_, record) = owner.store_audio(&bytes, &format!("{}.wav", plan.source_label), false)?;
            let mut next = work.snapshot.clone();
            next["design"] = design;
            next["native_execution_review"] = Value::Null;
            next["run_package"] = Value::Null;
            next["session"] = Value::Null;
            for (index, field) in [(2,"trial_sequence_bake"), (3,"trial_file_bake"), (4,"trial_pool_bake"), (5,"block_csv_preview")] { if index >= minimum_invalidated { next[field] = json!({}); } }
            if let Some(segments) = next["project_segments"].as_object_mut() {
                for (name, segment) in segments { if name.split('_').next().and_then(|v|v.parse::<u8>().ok()).is_some_and(|n|n >= minimum_invalidated) { segment["status"] = json!("stale"); segment["accepted"] = json!(false); } }
            }
            if let Some(assets) = next["preload_inventory"]["assets"].as_array_mut() { assets.retain(|item| if minimum_invalidated == 2 { item["label"] != plan.original_label } else { item["label"] != asset["label"] }); assets.push(asset.clone()); }
            let mut records = owner.stored.assets.clone(); records.insert(key, record);
            if work.ticket.cancel.load(Ordering::Acquire) { return Err("generation_cancelled".into()); }
            owner.persist(&next, &records)?;
            owner.stored = Stored { snapshot: Some(next), assets: records };
            let result = json!({"source_kind":plan.source_kind,"source_label":plan.source_label,"source":source,"asset":asset});
            owner.jobs.finish(&work.ticket, "succeeded", "Native ingredient generated; downstream plans need review", Some(result));
            owner.jobs.revise(work.ticket.revision).map_err(str::to_owned)?;
            Ok(())
        });
    // The unique directory was created by this job under app-owned storage.
    let _ = fs::remove_dir_all(&work.directory);
    if let Err(error) = result {
        if let Ok(mut owner) = shared.lock() {
            owner.jobs.finish(
                &work.ticket,
                "failed",
                "Native generation failed; no output published",
                Some(json!({"error":error})),
            );
        }
    }
}

pub(crate) fn bound_snapshot(snapshot: &Value) -> Result<()> {
    if !snapshot["design"].is_object()
        || serde_json::to_vec(snapshot)
            .map_err(|_| "invalid_snapshot")?
            .len()
            > MAX_JSON
    {
        return Err("invalid_snapshot".into());
    }
    for key in ["custom_workflow", "project_segments", "preload_inventory"] {
        if snapshot.get(key).is_some_and(|value| !value.is_object()) {
            return Err("invalid_snapshot".into());
        }
    }
    if snapshot["project_segments"]
        .as_object()
        .is_some_and(|segments| segments.values().any(|value| !value.is_object()))
    {
        return Err("invalid_snapshot".into());
    }
    Ok(())
}
fn replace_references(value: &mut Value, replacements: &BTreeMap<String, String>) {
    match value {
        Value::String(text) => {
            if let Some(replacement) = replacements.get(text) {
                *text = replacement.clone();
            }
        }
        Value::Array(values) => {
            for child in values {
                replace_references(child, replacements);
            }
        }
        Value::Object(values) => {
            for child in values.values_mut() {
                replace_references(child, replacements);
            }
        }
        _ => {}
    }
}
pub(crate) fn sha(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
pub(crate) fn read_bounded(path: &Path, maximum: u64) -> Result<Vec<u8>> {
    use std::io::Read;
    let file = fs::File::open(path).map_err(|_| "asset_unavailable")?;
    if file.metadata().map_err(|_| "asset_unavailable")?.len() > maximum {
        return Err("asset_limit".into());
    }
    let mut bytes = Vec::new();
    file.take(maximum + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| "asset_read_failed")?;
    if bytes.len() as u64 > maximum {
        return Err("asset_limit".into());
    }
    Ok(bytes)
}
fn safe_join(root: &Path, relative: &str) -> Result<PathBuf> {
    if relative.contains(['\\', ':'])
        || !Path::new(relative)
            .components()
            .all(|c| matches!(c, Component::Normal(_)))
    {
        return Err("asset_not_authorized".into());
    }
    let path = fs::canonicalize(root.join(relative)).map_err(|_| "asset_unavailable")?;
    let canonical_root = fs::canonicalize(root).map_err(|_| "asset_unavailable")?;
    if !path.starts_with(canonical_root) {
        return Err("asset_not_authorized".into());
    }
    Ok(path)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn partial_asset_write_does_not_poison_digest_path_and_retry_succeeds() {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../../artifacts")
            .join(format!(
                "designer-asset-retry-{}-{}",
                std::process::id(),
                SEQUENCE.fetch_add(1, Ordering::Relaxed)
            ));
        let owner = DesignerService::open(root.clone(), PathBuf::new(), PathBuf::new()).unwrap();
        let bytes = b"complete verified input bytes";
        let failure = owner.store_audio_using(bytes, "example.wav", false, |file| {
            file.write_all(&bytes[..4])?;
            Err(std::io::Error::other("injected write failure"))
        });
        assert_eq!(failure.err().unwrap(), "asset_write_failed");
        assert_eq!(fs::read_dir(root.join("assets")).unwrap().count(), 0);
        let (key, record) = owner.store_audio(bytes, "example.wav", false).unwrap();
        assert_eq!(fs::read(root.join(&record.relative_path)).unwrap(), bytes);
        assert_eq!(key, format!("native-assets/{}.wav", sha(bytes)));
        owner.store_audio(bytes, "retry.wav", false).unwrap();
        assert_eq!(fs::read_dir(root.join("assets")).unwrap().count(), 1);
    }

    #[test]
    fn owned_import_directory_is_removed_on_early_return() {
        let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../../artifacts")
            .join(format!(
                "designer-import-cleanup-{}-{}",
                std::process::id(),
                SEQUENCE.fetch_add(1, Ordering::Relaxed)
            ));
        fs::create_dir(&path).unwrap();
        fs::write(path.join("verified.wav"), b"temporary extraction").unwrap();
        let failed_copy = || -> Result<()> {
            let _owned = ImportDirectory(Some(path.clone()));
            Err("asset_write_failed".into())
        };
        assert!(failed_copy().is_err());
        assert!(!path.exists());
    }

    #[test]
    fn traversal_and_windows_absolute_paths_never_grant_authority() {
        for path in [
            "../draft.json",
            "C:/private.wav",
            "assets\\private.wav",
            "/absolute.wav",
        ] {
            assert_eq!(
                safe_join(Path::new("."), path).unwrap_err(),
                "asset_not_authorized"
            );
        }
    }
    #[test]
    fn projection_replaces_only_verified_references() {
        let mut value = json!({"path":"C:/verified.wav","source_input_path":"C:/untrusted.wav","native_stationary_baseline_asset":"C:/control.wav","browser_asset_id":"moving.wav"});
        replace_references(
            &mut value,
            &BTreeMap::from([
                ("C:/verified.wav".into(), "native-assets/receipt.wav".into()),
                ("C:/control.wav".into(), "native-assets/control.wav".into()),
            ]),
        );
        assert_eq!(value["path"], "native-assets/receipt.wav");
        assert_eq!(value["source_input_path"], "C:/untrusted.wav");
        assert_eq!(
            value["native_stationary_baseline_asset"],
            "native-assets/control.wav"
        );
        assert_eq!(value["browser_asset_id"], "moving.wav");
    }

    #[test]
    fn saved_browser_flags_cannot_authorize_participant_preparation() {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../../artifacts")
            .join(format!("designer-forged-review-{}", std::process::id()));
        let mut owner =
            DesignerService::open(root.clone(), PathBuf::new(), PathBuf::new()).unwrap();
        owner.save(0,json!({"design":{},"native_execution_review":{"accepted":true,"available":true,"hashes":{"design_sha256":"forged"}}})).unwrap();
        assert_eq!(
            owner.snapshot()["snapshot"]["native_execution_review"]["accepted"],
            false
        );
        assert_eq!(
            owner
                .begin_prepare(1, 1, "fake".into(), root.join("candidate"))
                .err()
                .unwrap(),
            "native_acceptance_required"
        );
        assert!(!root.join("candidate").exists());
    }

    #[test]
    #[ignore = "requires the retained real Study5 participant group"]
    fn actual_retained_group_conforms_to_verifier() {
        let fixture =
            PathBuf::from(std::env::var_os("PPS_STUDY5_FIXTURE").expect("set PPS_STUDY5_FIXTURE"));
        let result = pps_session_package::verify_prepared_group(
            &fixture.join("participant/session_group_manifest.json"),
        );
        assert!(result.is_ok(), "{result:?}");
    }

    #[test]
    #[ignore = "requires retained real Study5 controls and browser full-plan fixture"]
    fn actual_study5_review_accept_and_prepare_are_revision_bound() {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../..");
        let fixture =
            PathBuf::from(std::env::var_os("PPS_STUDY5_FIXTURE").expect("set PPS_STUDY5_FIXTURE"));
        let output = root
            .join("artifacts")
            .join(format!("designer-assembly-{}", std::process::id()));
        fs::create_dir(&output).unwrap();
        let mut owner = DesignerService::open(
            output.clone(),
            root.join("packages/pps-resources"),
            PathBuf::new(),
        )
        .unwrap();
        let captured: Value = serde_json::from_slice(
            &fs::read(root.join("artifacts/ui-workflow-check/browser-full-block-plan.json"))
                .unwrap(),
        )
        .unwrap();
        let setup: Value = serde_json::from_slice(
            &fs::read(fixture.join("participant/run_setup_manifest.json")).unwrap(),
        )
        .unwrap();
        for label in ["Pink-frontal", "White-frontal"] {
            let bytes = fs::read(fixture.join(label).join("baseline.wav")).unwrap();
            let (key, record) = owner.store_audio(&bytes, label, false).unwrap();
            owner.stored.assets.insert(key, record);
        }
        let snapshot = json!({"design":setup["design"],"block_csv_preview":captured["block_csv_preview"],"preload_inventory":{"assets":[]}});
        assert!(owner.accept_review(0, &json!({"accepted":true})).is_err());
        let (job, work) = owner
            .begin_review(0, snapshot.clone(), captured["variants"].clone())
            .unwrap();
        let shared = Arc::new(Mutex::new(owner));
        crate::assembly_host::review(shared.clone(), work);
        let mut owner = shared.lock().unwrap();
        let status = owner.jobs.snapshot(&job.job_id).unwrap();
        assert_eq!(status.status, "succeeded", "{:?}", status.result);
        let projection = owner.snapshot();
        assert_eq!(
            projection["snapshot"]["run_sequence_setup"]["csv_rows"]
                .as_array()
                .unwrap()
                .len(),
            600
        );
        let hashes = projection["snapshot"]["native_execution_review"]["hashes"].clone();
        assert!(owner
            .accept_review(0, &json!({"design_sha256":"forged"}))
            .is_err());
        assert!(
            owner.review.is_some(),
            "rejected browser hashes must not consume the sealed review"
        );
        owner.accept_review(0, &hashes).unwrap();
        let (job, work) = owner
            .begin_prepare(
                0,
                1,
                "host_actual_study5".into(),
                output.join("participant"),
            )
            .unwrap();
        drop(owner);
        crate::assembly_host::prepare(shared.clone(), work);
        let mut owner = shared.lock().unwrap();
        let status = owner.jobs.snapshot(&job.job_id).unwrap();
        assert_eq!(status.status, "succeeded", "{:?}", status.result);
        assert_eq!(status.result.unwrap()["part_count"], 2);
        let (cancelled, work) = owner
            .begin_prepare(0, 1, "host_cancelled".into(), output.join("cancelled"))
            .unwrap();
        owner.invalidate(0).unwrap();
        assert!(owner.accepted.is_none());
        assert!(owner.prepared_directory.is_none());
        drop(owner);
        crate::assembly_host::prepare(shared.clone(), work);
        assert_eq!(
            shared
                .lock()
                .unwrap()
                .jobs
                .snapshot(&cancelled.job_id)
                .unwrap()
                .status,
            "cancelled"
        );
        assert!(!output.join("cancelled").exists());
        // Persisted browser flags cannot restore native acceptance after restarting the host.
        let restored = DesignerService::open(
            output.clone(),
            root.join("packages/pps-resources"),
            PathBuf::new(),
        )
        .unwrap();
        assert_eq!(
            restored.snapshot()["snapshot"]["native_execution_review"]["available"],
            false
        );
        assert_eq!(
            restored.snapshot()["snapshot"]["native_execution_review"]["accepted"],
            false
        );
        eprintln!("Actual host participant evidence: {}", output.display());
    }

    #[test]
    #[ignore = "requires the rebuilt native renderer; does not open an audio device"]
    fn actual_renderer_publishes_verified_audio_and_rejects_obsolete_work() {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../..");
        let artifacts = root
            .join("artifacts")
            .join(format!("designer-host-native-{}", std::process::id()));
        fs::create_dir(&artifacts).unwrap();
        let renderer = PathBuf::from(
            std::env::var_os("PPS_DESIGNER_RENDERER").expect("set PPS_DESIGNER_RENDERER"),
        );
        let shared = Arc::new(Mutex::new(
            DesignerService::open(
                artifacts.clone(),
                root.join("packages/pps-resources"),
                renderer,
            )
            .unwrap(),
        ));
        let mut payload: Value = serde_json::from_str(include_str!(
            "../../../../packages/pps-designer-core/tests/fixtures/ingredient_payload.json"
        ))
        .unwrap();
        payload["design"]["sofa_file"] = json!(HRTF);
        payload["design"]["trajectory"]["sample_rate"] = json!(44100);
        let snapshot = json!({"design":payload["design"],"custom_workflow":{"is_custom":true,"is_finalized":false},
            "project_segments":{"2_trial_sequence_designs":{"status":"ready","accepted":true}},
            "preload_inventory":{"assets":[]},"block_csv_preview":{"accepted":true}});
        let opt = || GenerationOptIn {
            source_algorithm: pps_designer_core::SOURCE_ALGORITHM.into(),
            accept_non_legacy_source_algorithm: true,
            seed: 123,
        };
        let (job, work) = shared
            .lock()
            .unwrap()
            .begin(0, snapshot.clone(), payload.clone(), opt())
            .unwrap();
        execute(shared.clone(), work);
        let owner = shared.lock().unwrap();
        let status = owner.jobs.snapshot(&job.job_id).unwrap();
        assert_eq!(status.status, "succeeded", "{:?}", status.result);
        let state = owner.snapshot();
        assert_eq!(
            state["snapshot"]["design"]["noises"][0]["label"],
            "Native burst"
        );
        assert_eq!(
            state["snapshot"]["project_segments"]["2_trial_sequence_designs"]["status"],
            "stale"
        );
        assert_eq!(state["snapshot"]["block_csv_preview"], json!({}));
        let reference = state["snapshot"]["design"]["noises"][0]["prebaked_path"]
            .as_str()
            .unwrap();
        assert!(owner.resource(reference).unwrap().0.len() > 1000);
        drop(owner);
        let persisted = fs::read(artifacts.join("draft.json")).unwrap();
        let revision = shared.lock().unwrap().jobs.revision();
        assert_eq!(revision, 1);
        let (job, work) = shared
            .lock()
            .unwrap()
            .begin(revision, snapshot, payload, opt())
            .unwrap();
        shared.lock().unwrap().invalidate(revision).unwrap();
        execute(shared.clone(), work);
        assert_eq!(
            shared
                .lock()
                .unwrap()
                .jobs
                .snapshot(&job.job_id)
                .unwrap()
                .status,
            "cancelled"
        );
        assert_eq!(fs::read(artifacts.join("draft.json")).unwrap(), persisted);
        assert!(!fs::read_dir(&artifacts).unwrap().any(|entry| entry
            .unwrap()
            .file_name()
            .to_string_lossy()
            .starts_with("generation-")));
        eprintln!("Verified native host evidence: {}", artifacts.display());
    }

    #[test]
    #[ignore = "requires the actual browser portable export fixture"]
    fn actual_browser_bundle_has_path_free_audio_receipts_without_dry_authority() {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../..");
        let directory = root
            .join("artifacts")
            .join(format!("designer-import-test-{}", std::process::id()));
        fs::create_dir(&directory).unwrap();
        let mut service = DesignerService::open(
            directory,
            root.join("packages/pps-resources"),
            PathBuf::new(),
        )
        .unwrap();
        let receipt = service
            .import_bundle(
                0,
                &root.join("artifacts/ui-workflow-check/browser-finalized.pps-profile"),
            )
            .unwrap();
        assert_eq!(receipt["revision"], 1);
        assert_eq!(receipt["assets"].as_array().unwrap().len(), 9);
        for record in service.stored.assets.values() {
            assert!(!record.dry_source);
        }
        for asset in receipt["assets"].as_array().unwrap() {
            let key = asset["path"].as_str().unwrap();
            assert!(key.starts_with("native-assets/"));
            let (bytes, mime) = service.resource(key).unwrap();
            assert_eq!(mime, "audio/wav");
            assert_eq!(sha(&bytes), asset["sha256"]);
        }
        for collection in ["noises", "custom_looming_files", "prestimulus_files"] {
            for source in receipt["design"][collection].as_array().unwrap() {
                let path = source[if collection == "noises" {
                    "prebaked_path"
                } else {
                    "path"
                }]
                .as_str()
                .unwrap();
                assert!(
                    service.stored.assets.contains_key(path),
                    "{collection} output needs a verified native receipt"
                );
            }
        }
        let no_extraction = |service: &DesignerService| {
            assert!(fs::read_dir(&service.root).unwrap().all(|entry| !entry
                .unwrap()
                .file_name()
                .to_string_lossy()
                .starts_with("import-")));
        };
        no_extraction(&service);
        let (key, record) = service.stored.assets.iter().next().unwrap();
        let (original, _) = service.resource(key).unwrap();
        let cached_path = service.root.join(&record.relative_path);
        let authority = serde_json::to_value(&service.stored.assets).unwrap();
        service.stored.snapshot = Some(json!({"design":{"name":"previous draft"}}));
        fs::write(&cached_path, b"corrupt existing cache").unwrap();
        assert_eq!(
            service
                .import_bundle(
                    1,
                    &root.join("artifacts/ui-workflow-check/browser-finalized.pps-profile")
                )
                .err()
                .unwrap(),
            "asset_hash_mismatch"
        );
        no_extraction(&service);
        assert_eq!(service.jobs.revision(), 1);
        assert_eq!(
            serde_json::to_value(&service.stored.assets).unwrap(),
            authority
        );
        assert_eq!(
            service.stored.snapshot.as_ref().unwrap()["design"]["name"],
            "previous draft"
        );
        fs::write(cached_path, original).unwrap();
        assert!(service
            .import_bundle(
                1,
                &root.join("artifacts/ui-workflow-check/browser-finalized.pps-profile")
            )
            .is_ok());
        no_extraction(&service);
    }
}
