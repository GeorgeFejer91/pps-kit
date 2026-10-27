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

pub struct DesignerService {
    pub jobs: JobOwner,
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
            stored,
            root: fs::canonicalize(root).map_err(|_| "storage_unavailable")?,
            resources,
            renderer,
        })
    }

    pub fn snapshot(&self) -> Value {
        json!({"revision":self.jobs.revision(), "snapshot":self.stored.snapshot, "capabilities":pps_designer_core::generation_capabilities()})
    }

    pub fn invalidate(&mut self, expected: u64) -> Result<u64> {
        self.jobs.revise(expected).map_err(str::to_owned)
    }

    pub fn save(&mut self, expected: u64, snapshot: Value) -> Result<u64> {
        bound_snapshot(&snapshot)?;
        if self.jobs.revision() != expected {
            return Err("revision_conflict".into());
        }
        self.persist(&snapshot, &self.stored.assets)?;
        self.jobs.revise(expected).map_err(str::to_owned)?;
        self.stored.snapshot = Some(snapshot);
        Ok(self.jobs.revision())
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
        let digest = sha(bytes);
        let relative = format!("assets/{digest}.wav");
        let path = self.root.join(&relative);
        match fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&path)
        {
            Ok(mut file) => file
                .write_all(bytes)
                .and_then(|_| file.sync_all())
                .map_err(|_| "asset_write_failed")?,
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
        let mut design = receipt.rebased_design().clone();
        let mut replacements = BTreeMap::new();
        let mut assets = Vec::new();
        for asset in receipt.assets() {
            let bytes = read_bounded(&asset.path, MAX_AUDIO)?;
            if sha(&bytes) != asset.sha256 {
                return Err("asset_hash_mismatch".into());
            }
            let (key, record) = self.store_audio(&bytes, &asset.source_name, false)?;
            replacements.insert(asset.path.to_string_lossy().into_owned(), key.clone());
            self.stored.assets.insert(key.clone(), record);
            assets.push(json!({"path":key,"sha256":asset.sha256,"label":asset.source_name}));
        }
        replace_references(&mut design, &replacements);
        self.jobs.revise(expected).map_err(str::to_owned)?;
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
                plan,
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
    plan: IngredientGenerationPlan,
    snapshot: Value,
    directory: PathBuf,
    executable: PathBuf,
    hrtf: PathBuf,
    imported: Option<Vec<u8>>,
}
pub fn execute(shared: Shared, work: Work) {
    let result = generation::render(&work.plan, &work.directory, &work.executable, &work.hrtf, work.imported.as_deref(), &work.ticket.cancel)
        .and_then(|(bytes, stimulus, report)| {
            let key = format!("native-assets/{}.wav", sha(&bytes));
            let entry = design::generated_ingredient_entry(&work.plan, &key, &bytes, &stimulus, &report, &work.ticket.cancel).map_err(|e| e.to_string())?;
            let publication = design::apply_generated_ingredient(&work.plan, &entry).map_err(|e| e.to_string())?;
            let mut owner = shared.lock().map_err(|_| "host_unavailable")?;
            owner.jobs.publish(&work.ticket, || Ok(())).map_err(str::to_owned)?;
            let (_, record) = owner.store_audio(&bytes, &format!("{}.wav", work.plan.source_label), false)?;
            let mut next = work.snapshot.clone();
            next["design"] = publication.design;
            next["run_package"] = Value::Null;
            next["session"] = Value::Null;
            for field in ["trial_sequence_bake", "trial_file_bake", "trial_pool_bake", "block_csv_preview"] { next[field] = json!({}); }
            if let Some(segments) = next["project_segments"].as_object_mut() {
                for (name, segment) in segments { if !name.starts_with("1_") { segment["status"] = json!("stale"); segment["accepted"] = json!(false); } }
            }
            if let Some(assets) = next["preload_inventory"]["assets"].as_array_mut() { assets.retain(|asset| asset["label"] != work.plan.original_label); assets.push(publication.asset.clone()); }
            let mut records = owner.stored.assets.clone(); records.insert(key, record);
            if work.ticket.cancel.load(Ordering::Acquire) { return Err("generation_cancelled".into()); }
            owner.persist(&next, &records)?;
            owner.stored = Stored { snapshot: Some(next), assets: records };
            let result = json!({"source_kind":work.plan.source_kind,"source_label":work.plan.source_label,"source":entry.source(),"asset":publication.asset});
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

fn bound_snapshot(snapshot: &Value) -> Result<()> {
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
fn sha(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn read_bounded(path: &Path, maximum: u64) -> Result<Vec<u8>> {
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
        let mut value = json!({"path":"C:/verified.wav","source_input_path":"C:/untrusted.wav"});
        replace_references(
            &mut value,
            &BTreeMap::from([("C:/verified.wav".into(), "native-assets/receipt.wav".into())]),
        );
        assert_eq!(value["path"], "native-assets/receipt.wav");
        assert_eq!(value["source_input_path"], "C:/untrusted.wav");
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
    }
}
