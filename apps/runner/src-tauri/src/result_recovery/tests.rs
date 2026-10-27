use super::*;
use serde_json::json;
use std::path::PathBuf;

struct Fixture {
    root: PathBuf,
    id: String,
    header: Value,
    events: Vec<u8>,
    csv: Vec<u8>,
}
impl Fixture {
    fn new() -> Self {
        let root = std::env::temp_dir().join(format!("pps-recovery-{}", pps_brsp::random_nonce()));
        fs::create_dir(&root).unwrap();
        let id = pps_brsp::random_nonce();
        let header = json!({"schema":"pps.native-event-journal.v1","packageManifestSha256":"a".repeat(64),
            "participantId":"private-participant", "sessionId":"session", "partSessionId":"part", "partNumber":1,
            "executionMode":"participant_block_wavs", "completion":"partial", "timingQualification":"unqualified"});
        let row = json!({"trial_type":"Audio-Tactile","response_given":true,"outcome":"Hit","rt_ms":"10.000"});
        let records = [
            header.clone(),
            json!({"sequence":5,"eventType":"audio.final-frame-submitted","payload":{}}),
            json!({"sequence":6,"eventType":"trial.scored","payload":row}),
            json!({"sequence":7,"eventType":"native.results.finalization-requested","payload":{
                "packageGeneration":1,"runGeneration":2,"expectedScoredTrials":1}}),
        ];
        let events = records
            .iter()
            .flat_map(|v| {
                let mut b = serde_json::to_vec(v).unwrap();
                b.push(b'\n');
                b
            })
            .collect::<Vec<_>>();
        let csv = encode_data_min_csv(&[data_min_row(row.as_object().unwrap(), 1).unwrap()], true)
            .unwrap();
        fs::write(
            root.join(format!("native_events_{id}.partial.jsonl")),
            &events,
        )
        .unwrap();
        fs::write(root.join(format!("native_trials_{id}.partial.csv")), &csv).unwrap();
        Self {
            root,
            id,
            header,
            events,
            csv,
        }
    }
    fn publish(&self) {
        let events = format!("native_events_{}.jsonl", self.id);
        let dataset = format!("native_trials_{}.csv", self.id);
        fs::hard_link(
            self.root
                .join(format!("native_events_{}.partial.jsonl", self.id)),
            self.root.join(&events),
        )
        .unwrap();
        fs::hard_link(
            self.root
                .join(format!("native_trials_{}.partial.csv", self.id)),
            self.root.join(&dataset),
        )
        .unwrap();
        let manifest = json!({"schema":"pps.native-results.v1","completion":"complete","timingQualification":"unqualified",
            "audioEvidence":"software-frame-submission", "eventsFile":events,"datasetFile":dataset,"identity":self.header,
            "receipt":{"packageManifestSha256":"a".repeat(64),"packageGeneration":1,"runGeneration":2,
                "firstEventSequence":5,"lastEventSequence":7,"eventRecordCount":3,"scoredTrialCount":1,"datasetRowCount":1,
                "eventsSha256":format!("{:x}",Sha256::digest(&self.events)),"datasetSha256":format!("{:x}",Sha256::digest(&self.csv))}});
        fs::write(
            self.root
                .join(format!("native_events_{}.results.json", self.id)),
            serde_json::to_vec(&manifest).unwrap(),
        )
        .unwrap();
    }
    fn assess(&self) -> NativeResultsAssessment {
        assess_directory(&self.root, &"a".repeat(64))
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.root).unwrap();
    }
}

#[test]
fn complete_commit_is_verified_and_partial_links_are_one_attempt() {
    let f = Fixture::new();
    f.publish();
    let a = f.assess();
    assert!(a.complete_scan);
    assert_eq!(a.attempts.len(), 1);
    assert_eq!(a.attempts[0].status, "complete");
    assert_eq!(a.attempts[0].common_event_sequence, Some(7));
    assert_eq!(a.attempts[0].common_dataset_rows, 1);
    let public = serde_json::to_string(&a).unwrap();
    assert!(!public.contains("private-participant"));
    assert!(!public.contains("session"));
    assert!(!public.contains(f.root.to_str().unwrap()));
}

#[test]
fn missing_commit_never_completes_even_when_every_row_matches() {
    let f = Fixture::new();
    assert_eq!(f.assess().attempts[0].status, "interrupted");
    assert_eq!(f.assess().attempts[0].common_dataset_rows, 1);
    fs::hard_link(
        f.root.join(format!("native_events_{}.partial.jsonl", f.id)),
        f.root.join(format!("native_events_{}.jsonl", f.id)),
    )
    .unwrap();
    assert_eq!(f.assess().attempts[0].status, "orphaned");
}

#[test]
fn torn_event_and_csv_keep_only_the_matching_prefix_without_writing() {
    let f = Fixture::new();
    let events = f.root.join(format!("native_events_{}.partial.jsonl", f.id));
    let bytes = [f.events.as_slice(), b"{\"sequence\":"].concat();
    fs::write(&events, &bytes).unwrap();
    assert_eq!(f.assess().attempts[0].common_event_sequence, Some(7));
    assert_eq!(fs::read(&events).unwrap(), bytes);
    fs::write(
        f.root.join(format!("native_trials_{}.partial.csv", f.id)),
        &f.csv[..f.csv.len() - 3],
    )
    .unwrap();
    let a = f.assess();
    assert_eq!(a.attempts[0].status, "interrupted");
    assert_eq!(a.attempts[0].common_event_sequence, Some(5));
    assert_eq!(a.attempts[0].common_dataset_rows, 0);
}

#[test]
fn changed_complete_bytes_wrong_package_and_unsafe_member_are_invalid() {
    for mode in 0..3 {
        let f = Fixture::new();
        f.publish();
        if mode == 0 {
            fs::write(
                f.root.join(format!("native_trials_{}.csv", f.id)),
                b"changed",
            )
            .unwrap();
        }
        if mode == 2 {
            let path = f.root.join(format!("native_events_{}.results.json", f.id));
            let mut manifest: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
            manifest["eventsFile"] = json!("../outside.jsonl");
            fs::write(path, serde_json::to_vec(&manifest).unwrap()).unwrap();
        }
        let a = if mode == 1 {
            assess_directory(&f.root, &"b".repeat(64))
        } else {
            f.assess()
        };
        assert_eq!(a.attempts[0].status, "invalid");
    }
}

#[test]
fn missing_pair_and_oversized_file_remain_visible_failures() {
    let f = Fixture::new();
    fs::remove_file(f.root.join(format!("native_trials_{}.partial.csv", f.id))).unwrap();
    assert_eq!(f.assess().attempts[0].status, "orphaned");
    let file = File::options()
        .write(true)
        .open(f.root.join(format!("native_events_{}.partial.jsonl", f.id)))
        .unwrap();
    file.set_len(MAX_BYTES as u64 + 1).unwrap();
    assert_eq!(f.assess().attempts[0].reason, "resource_limit");
}
