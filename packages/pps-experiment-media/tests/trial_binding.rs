use std::{
    fs,
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
};

use hound::{SampleFormat, WavSpec, WavWriter};
use pps_experiment_media::bind_profile_trial_wav;
use pps_runner_audio::{AudioFence, AudioLoadLimits};
use pps_session_package::{
    experiment_plan::select_profile_participant,
    experiment_profile::verify_experiment_profile_inventory,
};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

static TEST_SEQUENCE: AtomicU64 = AtomicU64::new(1);

struct TestDirectory(PathBuf);

impl TestDirectory {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "pps-experiment-media-test-{}-{}",
            std::process::id(),
            TEST_SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir_all(&path).expect("create fixture folder");
        Self(path)
    }

    fn join(&self, name: &str) -> PathBuf {
        self.0.join(name)
    }
}

impl Drop for TestDirectory {
    fn drop(&mut self) {
        if self.0.starts_with(std::env::temp_dir())
            && self
                .0
                .file_name()
                .and_then(|name| name.to_str())
                .is_some_and(|name| name.starts_with("pps-experiment-media-test-"))
        {
            let _ = fs::remove_dir_all(&self.0);
        }
    }
}

fn write_json(path: &Path, value: &Value) {
    fs::write(path, serde_json::to_vec(value).expect("serialize fixture")).expect("write fixture");
}

fn file_record(path: &Path, audio: bool) -> Value {
    let mut record = json!({
        "path": path,
        "bytes": fs::metadata(path).expect("ingredient metadata").len(),
        "sha256": format!("{:x}", Sha256::digest(fs::read(path).expect("ingredient bytes"))),
    });
    if audio {
        record["audio"] = json!({
            "frames": 16,
            "sample_rate": 44_100,
            "channels": 2,
            "duration_s": 16.0 / 44_100.0,
            "format": "WAV",
        });
    }
    record
}

#[test]
fn trial_decode_rejects_media_changed_after_plan_selection() {
    let root = TestDirectory::new();
    let accepted = root.join("accepted.json");
    let wav = root.join("trial.wav");
    let block = root.join("block.csv");
    let order = root.join("order.csv");
    let setup = root.join("setup.json");
    let profile_path = root.join("profile.json");
    fs::write(&accepted, b"{}").unwrap();
    let spec = WavSpec {
        channels: 2,
        sample_rate: 44_100,
        bits_per_sample: 16,
        sample_format: SampleFormat::Int,
    };
    let mut writer = WavWriter::create(&wav, spec).unwrap();
    for _ in 0..16 {
        writer.write_sample::<i16>(100).unwrap();
        writer.write_sample::<i16>(-100).unwrap();
    }
    writer.finalize().unwrap();
    fs::write(&block, format!("trial_file_path\n{}\n", wav.display())).unwrap();
    fs::write(
        &order,
        format!(
            "participant_id,block_csv_path,block_label\nP001,{},First\n",
            block.display()
        ),
    )
    .unwrap();
    let setup_value = json!({
        "schema": "pps-experiment-run-setup.v1", "prepared": true,
        "source_segment5_manifest": accepted,
        "source_segment5_manifest_sha256": file_record(&accepted, false)["sha256"],
        "csv_path": order,
    });
    write_json(&setup, &setup_value);
    write_json(
        &profile_path,
        &json!({
            "schema": "pps-experiment-profile.v1", "profile_id": "", "display_name": "Fixture",
            "source_revision": 1, "design": {}, "run_setup_path": setup,
            "assembly": {
                "run_setup": setup_value,
                "block_order": [{"participant_id": "P001", "block_csv_path": block, "block_label": "First"}],
                "blocks": [{"source_csv_path": block, "label": "First", "rows": [{"trial_file_path": wav}]}],
            },
            "files": [file_record(&accepted, false), file_record(&setup, false),
                      file_record(&order, false), file_record(&block, false), file_record(&wav, true)],
        }),
    );
    let profile = verify_experiment_profile_inventory(&profile_path).unwrap();
    let plan = select_profile_participant(&profile, "P001").unwrap();
    let trial = &plan.blocks()[0].trials()[0];
    let fence = AudioFence::new(1, profile.profile_sha256().to_owned(), 1);
    let prepared = bind_profile_trial_wav(trial, &fence, AudioLoadLimits::default()).unwrap();
    assert_eq!(
        (
            prepared.frames(),
            prepared.channels(),
            prepared.sample_rate_hz()
        ),
        (16, 2, 44_100)
    );
    let mut changed = fs::read(&wav).unwrap();
    let last = changed.last_mut().unwrap();
    *last ^= 1;
    fs::write(&wav, changed).unwrap();
    let error = bind_profile_trial_wav(trial, &fence, AudioLoadLimits::default()).unwrap_err();
    assert_eq!(error.code(), "profile_audio_changed_or_unsupported");
}
