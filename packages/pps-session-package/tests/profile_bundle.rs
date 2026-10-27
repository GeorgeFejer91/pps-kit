use pps_session_package::materialize_profile_bundle;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::Write,
    path::PathBuf,
    sync::atomic::{AtomicBool, AtomicU64, Ordering},
};
use zip::{write::SimpleFileOptions, CompressionMethod, ZipWriter};

static SEQUENCE: AtomicU64 = AtomicU64::new(0);
struct Fixture(PathBuf);
impl Fixture {
    fn new() -> Self {
        let root = std::env::temp_dir().join(format!(
            "pps-native-bundle-{}-{}",
            std::process::id(),
            SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&root).unwrap();
        Self(root)
    }
    fn source(&self) -> PathBuf {
        self.0.join("source.pps-profile")
    }
    fn destination(&self) -> PathBuf {
        self.0.join("installed")
    }
    fn bundle(&self, change: impl FnOnce(&mut Value, &mut Value, &mut Vec<(String, Vec<u8>)>)) {
        // A valid one-sample mono PCM16 WAV; materialization is independent of
        // scientific decoding/qualification, but the interchange fixture is real.
        let mut audio = b"RIFF".to_vec();
        audio.extend(38_u32.to_le_bytes());
        audio.extend(b"WAVEfmt ");
        audio.extend(16_u32.to_le_bytes());
        audio.extend(1_u16.to_le_bytes());
        audio.extend(1_u16.to_le_bytes());
        audio.extend(48_000_u32.to_le_bytes());
        audio.extend(96_000_u32.to_le_bytes());
        audio.extend(2_u16.to_le_bytes());
        audio.extend(16_u16.to_le_bytes());
        audio.extend(b"data");
        audio.extend(2_u32.to_le_bytes());
        audio.extend(0_i16.to_le_bytes());
        let hash = format!("{:x}", Sha256::digest(&audio));
        let asset = json!({"logical_id":"cue", "path":"assets/cue", "sha256":hash, "bytes":audio.len(), "media_type":"audio/wav", "source_name":"cue.wav"});
        let mut profile = json!({"schema":"pps-study-profile.v1", "profile_id":"custom_test", "profile_kind":"custom", "display_name":"Portable test", "assets":[asset], "design": {
            "name":"Portable test", "noises":[{"label":"Imported","prebaked_path":"browser-asset:cue","browser_asset_id":"cue"}],
            "custom_looming_files":[{"path":"browser-asset:cue","browser_asset_id":"cue"}],
            "prestimulus_files":[{"path":"browser-asset:cue"}],
            "study_profile_reference_parameters":{"dashboard_run_setup":{"instruction_profile":{"slots":[{"path":"browser-asset:cue","browser_asset_id":"cue"}]}}}
        }});
        let mut manifest = json!({"schema":"pps-profile-bundle.v1", "profile_id":"custom_test", "profile_kind":"custom", "files":[]});
        let mut files = vec![("assets/cue".to_string(), audio)];
        change(&mut manifest, &mut profile, &mut files);
        files.push(("profile.json".into(), serde_json::to_vec(&profile).unwrap()));
        manifest["files"] = json!(files.iter().map(|(name, bytes)| json!({"path":name,"sha256":format!("{:x}",Sha256::digest(bytes)),"bytes":bytes.len()})).collect::<Vec<_>>());
        let mut writer = ZipWriter::new(fs::File::create(self.source()).unwrap());
        let options = SimpleFileOptions::default().compression_method(CompressionMethod::Deflated);
        writer.start_file("manifest.json", options).unwrap();
        writer
            .write_all(&serde_json::to_vec(&manifest).unwrap())
            .unwrap();
        for (name, bytes) in files {
            writer.start_file(name, options).unwrap();
            writer.write_all(&bytes).unwrap();
        }
        writer.finish().unwrap();
    }
    fn assert_rejected(&self) {
        assert!(materialize_profile_bundle(
            &self.source(),
            &self.destination(),
            &AtomicBool::new(false)
        )
        .is_err());
        assert!(!self.destination().exists());
        assert_eq!(
            fs::read_dir(&self.0).unwrap().count(),
            1,
            "failed import must remove only its staging tree"
        );
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

#[test]
fn portable_audio_is_materialized_rebound_and_verifiable_offline() {
    let f = Fixture::new();
    f.bundle(|_, _, _| {});
    let receipt =
        materialize_profile_bundle(&f.source(), &f.destination(), &AtomicBool::new(false)).unwrap();
    assert_eq!(receipt.profile_id(), "custom_test");
    assert_eq!(receipt.assets().len(), 1);
    let asset = &receipt.assets()[0];
    assert!(asset.path.is_file());
    assert_eq!(
        format!("{:x}", Sha256::digest(fs::read(&asset.path).unwrap())),
        asset.sha256
    );
    for pointer in [
        "/noises/0/prebaked_path",
        "/custom_looming_files/0/path",
        "/prestimulus_files/0/path",
        "/study_profile_reference_parameters/dashboard_run_setup/instruction_profile/slots/0/path",
    ] {
        assert_eq!(
            receipt
                .rebased_design()
                .pointer(pointer)
                .unwrap()
                .as_str()
                .unwrap(),
            asset.path.to_str().unwrap()
        );
    }
    assert!(f.destination().join("profile.json").is_file());
    assert!(f.destination().join("materialized-profile.json").is_file());
}

#[test]
fn corrupted_asset_hash_and_missing_references_leave_no_published_tree() {
    for broken_hash in [true, false] {
        let f = Fixture::new();
        f.bundle(|_, p, _| {
            if broken_hash {
                p["assets"][0]["sha256"] = json!("0".repeat(64));
            } else {
                p["design"]["prestimulus_files"][0]["path"] = json!("browser-asset:missing");
            }
        });
        f.assert_rejected();
    }
}

#[test]
fn traversal_case_collisions_and_unlisted_types_are_rejected() {
    for member in [
        "../escape.wav",
        "assets/../escape.wav",
        "assets/CUE",
        "assets/CON.wav",
        "assets/a:stream",
        "scripts/run.exe",
    ] {
        let f = Fixture::new();
        f.bundle(|_, _, files| files.push((member.into(), b"not-a-valid-asset".to_vec())));
        f.assert_rejected();
    }
}

#[test]
fn cancellation_and_existing_destination_preserve_user_files() {
    let f = Fixture::new();
    f.bundle(|_, _, _| {});
    assert!(
        materialize_profile_bundle(&f.source(), &f.destination(), &AtomicBool::new(true)).is_err()
    );
    assert!(!f.destination().exists());
    fs::create_dir(f.destination()).unwrap();
    fs::write(f.destination().join("keep.txt"), b"keep").unwrap();
    assert!(
        materialize_profile_bundle(&f.source(), &f.destination(), &AtomicBool::new(false)).is_err()
    );
    assert_eq!(fs::read(f.destination().join("keep.txt")).unwrap(), b"keep");
}

#[test]
fn mismatched_identity_and_external_audio_paths_are_rejected() {
    for external in [true, false] {
        let f = Fixture::new();
        f.bundle(|_, p, _| {
            if external {
                p["design"]["prestimulus_files"][0]["path"] = json!("C:/private/missing.wav");
            } else {
                p["profile_id"] = json!("different");
            }
        });
        f.assert_rejected();
    }
}

#[test]
fn corrupted_zip_stream_and_excessive_directory_count_are_rejected() {
    for corrupt_stream in [true, false] {
        let f = Fixture::new();
        f.bundle(|_, _, _| {});
        let mut bytes = fs::read(f.source()).unwrap();
        if corrupt_stream {
            // Alter the central-directory CRC for the audio member. Rejection
            // must also remove the staging directory after extraction starts.
            let central = bytes
                .windows(4)
                .enumerate()
                .find_map(|(i, signature)| {
                    (signature == b"PK\x01\x02"
                        && bytes.get(i + 46..i + 56) == Some(b"assets/cue".as_slice()))
                    .then_some(i)
                })
                .unwrap();
            bytes[central + 16] ^= 1;
        } else {
            let end = bytes
                .windows(4)
                .rposition(|signature| signature == b"PK\x05\x06")
                .unwrap();
            bytes[end + 8..end + 10].copy_from_slice(&1025_u16.to_le_bytes());
            bytes[end + 10..end + 12].copy_from_slice(&1025_u16.to_le_bytes());
        }
        fs::write(f.source(), bytes).unwrap();
        f.assert_rejected();
    }
}

#[test]
fn missing_optional_groups_are_not_fabricated_during_import() {
    let f = Fixture::new();
    f.bundle(|_, p, _| {
        p["design"].as_object_mut().unwrap().remove("noises");
    });
    let receipt =
        materialize_profile_bundle(&f.source(), &f.destination(), &AtomicBool::new(false)).unwrap();
    assert!(receipt.rebased_design().get("noises").is_none());
}

#[test]
#[ignore = "requires PPS_TEST_PROFILE_BUNDLE from a real browser export"]
fn materializes_real_browser_export_offline() {
    let f = Fixture::new();
    let source = PathBuf::from(
        std::env::var_os("PPS_TEST_PROFILE_BUNDLE").expect("PPS_TEST_PROFILE_BUNDLE"),
    );
    let receipt =
        materialize_profile_bundle(&source, &f.destination(), &AtomicBool::new(false)).unwrap();
    assert!(!receipt.assets().is_empty());
    for asset in receipt.assets() {
        let bytes = fs::read(&asset.path).unwrap();
        assert_eq!(bytes.len() as u64, asset.bytes);
        assert_eq!(format!("{:x}", Sha256::digest(bytes)), asset.sha256);
    }
    println!(
        "Verified {} embedded browser assets offline",
        receipt.assets().len()
    );
}
