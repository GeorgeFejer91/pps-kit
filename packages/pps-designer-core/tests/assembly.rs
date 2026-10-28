use pps_designer_core::{assembly::*, GenerationError};
use pps_runner_execution::{compile_verified_block_schedule, BlockScheduleOptions};
use pps_session_package::{verify_prepared_session, VerificationRequest};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::Cursor,
    path::PathBuf,
    sync::atomic::{AtomicBool, AtomicU64, Ordering},
};
static SEQUENCE: AtomicU64 = AtomicU64::new(1);
struct Temp {
    path: PathBuf,
}
impl Temp {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "pps-native-assembly-{}-{}",
            std::process::id(),
            SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        Self { path }
    }
}
impl Drop for Temp {
    fn drop(&mut self) {
        let root = std::env::temp_dir().canonicalize().unwrap();
        if let Ok(path) = self.path.canonicalize() {
            if path.parent() == Some(root.as_path())
                && path
                    .file_name()
                    .unwrap()
                    .to_string_lossy()
                    .starts_with("pps-native-assembly-")
            {
                let _ = fs::remove_dir_all(path);
            }
        }
    }
}
fn asset(
    reference: &str,
    role: AssemblyAssetRole,
    rate: u32,
    channels: u16,
    frames: usize,
    left: f32,
    right: f32,
) -> VerifiedAssemblyAsset {
    let mut file = Cursor::new(Vec::new());
    let mut writer = hound::WavWriter::new(
        &mut file,
        hound::WavSpec {
            channels,
            sample_rate: rate,
            bits_per_sample: 32,
            sample_format: hound::SampleFormat::Float,
        },
    )
    .unwrap();
    for _ in 0..frames {
        writer.write_sample(left).unwrap();
        if channels == 2 {
            writer.write_sample(right).unwrap();
        }
    }
    writer.finalize().unwrap();
    let bytes = file.into_inner();
    VerifiedAssemblyAsset::from_wav_bytes(
        reference,
        &bytes,
        &format!("{:x}", Sha256::digest(&bytes)),
        role,
        &AtomicBool::new(false),
    )
    .unwrap()
}
fn assets() -> (Vec<VerifiedAssemblyAsset>, VerifiedAssemblyAsset) {
    (
        vec![
            asset(
                "speech",
                AssemblyAssetRole::Instruction,
                8000,
                1,
                800,
                0.2,
                0.0,
            ),
            asset(
                "noise",
                AssemblyAssetRole::BinauralIngredient,
                8000,
                2,
                1600,
                0.05,
                -0.025,
            ),
        ],
        asset("cue", AssemblyAssetRole::TactileCue, 8000, 1, 80, 0.7, 0.0),
    )
}
fn fixture() -> (Value, Value, Value) {
    let design = json!({"noises":[{"label":"Noise","prebaked_path":"noise","gain":1.0}],"custom_looming_files":[],"prestimulus_files":[{"label":"Speech","path":"speech","gain":1.0}],
        "study_profile_reference_parameters":{"loudness_policy":{"instruction_offset_db":-6.0}},"protocol":{"blocks":2,"random_seed":20260745,"baseline_strategy":"tactile_only","trial_strips":[{"label":"Row","elements":[
            {"kind":"fixed_audio","source_labels":["Speech"]},{"kind":"jitter","label":"Wait","jitter_values_ms":[10,20]},{"kind":"looming_stimulus","source_labels":["Noise"]}]}]}});
    let variants = json!([{"row_label":"Row","sequence_variant_key":"Speech + jitter_10ms + Noise","choices":[{"kind":"audio","label":"Speech"},{"kind":"jitter","label":"Wait (10 ms)","value":10},{"kind":"audio","label":"Noise"}]}]);
    let blocks:Vec<Value>=(0..2).map(|block| {let rows:Vec<Value>=(0..2).map(|row|json!({"block_index":block+1,"block_label":format!("Block {}",block+1),"block_trial_index":row+1,
        "trial_pool_index":([4,1,2,3][block*2+row]),"family":(["audio_tactile","catch","baseline","auditory_only"][block*2+row]),"row_label":"Row","sequence_variant_key":"Speech + jitter_10ms + Noise",
        "sequence_labels":"Speech | Wait (10 ms) | Noise","soa_ms":50,"duration_ms":310,"duration_s":0.31,"looming_segment_onset_s":"","tactile_onset_s":0.05,
        "baseline_mode":"tactile_only","trial_file_path":"static://placeholder","source_sha256":""})).collect();json!({"block_index":block+1,"block_label":format!("Block {}",block+1),"trial_count":2,"duration_ms":620,"preview_rows":rows,"preview_row_count":2})}).collect();
    let preview = json!({"schema":"pps-block-csv-preview.v1","accepted":true,"block_count":2,"total_trials":4,"total_count":4,"randomization_seed":20260745,"randomization_strategy":"seeded_gellermann_row_order_preserving","blocks":blocks});
    (design, preview, variants)
}

#[test]
fn saved_strip_contract_survives_native_preview_csv_and_compiled_rows() {
    let (mut design, preview, variants) = fixture();
    design["protocol"]["trial_strips"][0]["metadata"] = json!({
        "expected_response":"respond","response_mode":"mouse_click_choice_proxy_for_left_right_keypress",
        "response_choice_set":"left,right","correct_response":"left","response_rule":"choose_external_stimulus_side",
        "spatial_value_cm":39.1,"external_trigger_required":false,"iti_ms":0,
        "speaker_switch_channels":[1,2],"tactile_duration_ms":100,"unknown_private_metadata":"must not promote"
    });
    let (assets, cue) = assets();
    let cancel = AtomicBool::new(false);
    let enriched =
        plan_assembly_preview(&design, &preview, &variants, &assets, &cue, &cancel).unwrap();
    for block in enriched.preview["blocks"].as_array().unwrap() {
        for row in block["preview_rows"].as_array().unwrap() {
            assert_eq!(row["correct_response"], "left");
            assert_eq!(row["response_choice_set"], "left,right");
            assert_eq!(row["spatial_value_cm"], 39.1);
            assert_eq!(row["external_trigger_required"], false);
            assert_eq!(row["iti_ms"], 0);
            assert_eq!(row["speaker_switch_channels"], json!([1, 2]));
            assert_eq!(row["tactile_duration_ms"], 100);
            assert_eq!(
                row["native_tactile_duration_ms"],
                if row["family"] == "catch" || row["family"] == "auditory_only" {
                    0
                } else {
                    10
                }
            );
            assert!(row.get("unknown_private_metadata").is_none());
            assert_eq!(
                row["expected_response"],
                if row["family"] == "catch" {
                    "withhold"
                } else {
                    "respond"
                }
            );
            if row["family"] == "catch" {
                assert_eq!(row["target_role"], "catch_no_target");
            }
        }
    }
    let accepted = accept_assembly_preview(
        enriched,
        &design_fingerprint(&design).unwrap(),
        &plan_assembly_preview(&design, &preview, &variants, &assets, &cue, &cancel)
            .unwrap()
            .preview_sha256,
        1,
    )
    .unwrap();
    let temp = Temp::new();
    let staged = prepare_accepted_session(
        &accepted,
        &assets,
        &cue,
        &temp.path.join("prepared"),
        "P001",
        "contracts",
        &cancel,
    )
    .unwrap();
    let verified =
        verify_prepared_session(VerificationRequest::new(staged.manifest_path())).unwrap();
    for (ordinal, block) in verified.blocks().iter().enumerate() {
        let mut options = BlockScheduleOptions::new(ordinal as i64 + 1);
        options.sample_rate = 8000;
        options.block_wav_path = Some(block.wav_path().to_owned());
        let schedule = compile_verified_block_schedule(
            block.manifest_path(),
            block.manifest_sha256(),
            options,
        )
        .unwrap();
        for event in schedule
            .events()
            .iter()
            .filter(|event| event.event_type == "trial_start")
        {
            assert_eq!(event.payload["correct_response"], "left");
            assert_eq!(event.payload["response_choice_set"], "left,right");
            assert_eq!(event.payload["speaker_switch_channels"], "[1,2]");
        }
    }
}

#[test]
fn native_strip_contract_rejects_conflicts_and_keeps_explicit_legacy_values() {
    let (mut design, mut preview, variants) = fixture();
    let (assets, cue) = assets();
    let cancel = AtomicBool::new(false);
    preview["blocks"][0]["preview_rows"][0]["response_rule"] = json!("legacy_explicit_rule");
    let kept = plan_assembly_preview(&design, &preview, &variants, &assets, &cue, &cancel).unwrap();
    assert_eq!(
        kept.preview["blocks"][0]["preview_rows"][0]["response_rule"],
        "legacy_explicit_rule"
    );
    design["protocol"]["trial_strips"][0]["metadata"] =
        json!({"correct_response":"left","external_trigger_required":false});
    for (field, value) in [
        ("correct_response", json!("right")),
        ("external_trigger_required", json!(true)),
    ] {
        let mut conflicting = preview.clone();
        conflicting["blocks"][0]["preview_rows"][0][field] = value;
        assert_eq!(
            plan_assembly_preview(&design, &conflicting, &variants, &assets, &cue, &cancel)
                .unwrap_err(),
            GenerationError::Invalid("assembly_row_contract_conflict")
        );
    }
    preview["blocks"][0]["preview_rows"][1]["expected_response"] = json!("respond");
    assert_eq!(
        plan_assembly_preview(&design, &preview, &variants, &assets, &cue, &cancel).unwrap_err(),
        GenerationError::Invalid("assembly_row_contract_conflict")
    );
}

#[test]
fn native_strip_contract_allowlist_matches_existing_python_v1() {
    let python = include_str!("../../pps-runtime/src/peripersonal_space_toolkit/dashboard_app.py");
    let fields: Vec<_> = python
        .split("ROW_CONTRACT_FIELDS = (")
        .nth(1)
        .unwrap()
        .split(')')
        .next()
        .unwrap()
        .lines()
        .map(str::trim)
        .filter(|line| line.starts_with('"'))
        .map(|line| line.trim_matches(',').trim_matches('"'))
        .collect();
    assert_eq!(fields, pps_designer_core::row_contract::ROW_CONTRACT_FIELDS);
}

#[test]
fn saved_iti_is_real_silence_in_prepared_pcm_and_next_trial_sample_offsets() {
    let (mut design, preview, variants) = fixture();
    design["protocol"]["trial_strips"][0]["metadata"] =
        json!({"iti_ms":"300","iti_policy":"reported_fixed_interval"});
    let (assets, cue) = assets();
    let cancel = AtomicBool::new(false);
    let enriched =
        plan_assembly_preview(&design, &preview, &variants, &assets, &cue, &cancel).unwrap();
    assert_eq!(enriched.preview["blocks"][0]["duration_ms"], 1220);
    assert_eq!(
        enriched.preview["blocks"][0]["preview_rows"][0]["duration_ms"],
        310
    );
    assert_eq!(
        enriched.preview["blocks"][0]["preview_rows"][0]["native_session_duration_ms"],
        610
    );
    let dh = enriched.design_sha256.clone();
    let ph = enriched.preview_sha256.clone();
    let accepted = accept_assembly_preview(enriched, &dh, &ph, 1).unwrap();
    let temp = Temp::new();
    let staged = prepare_accepted_session(
        &accepted,
        &assets,
        &cue,
        &temp.path.join("prepared"),
        "P001",
        "iti",
        &cancel,
    )
    .unwrap();
    let verified =
        verify_prepared_session(VerificationRequest::new(staged.manifest_path())).unwrap();
    for block in verified.blocks() {
        let mut wav = hound::WavReader::open(block.wav_path()).unwrap();
        assert_eq!(wav.duration(), 9760);
        let pcm: Vec<f32> = wav.samples::<f32>().map(Result::unwrap).collect();
        for start in [2480, 7360] {
            assert!(pcm[start * 3..(start + 2400) * 3].iter().all(|v| *v == 0.0));
        }
        assert!(pcm[..2480 * 3].iter().any(|v| *v != 0.0));
        assert!(pcm[4880 * 3..7360 * 3].iter().any(|v| *v != 0.0));
        let mut csv = csv::Reader::from_path(block.manifest_path()).unwrap();
        let header = csv.headers().unwrap().clone();
        let start = header
            .iter()
            .position(|v| v == "Trial_Start_Sample")
            .unwrap();
        let end = header.iter().position(|v| v == "Trial_End_Sample").unwrap();
        for (index, row) in csv.records().enumerate() {
            let row = row.unwrap();
            assert_eq!(row[start].parse::<usize>().unwrap(), index * 4880);
            assert_eq!(row[end].parse::<usize>().unwrap(), (index + 1) * 4880);
        }
        for source in block.source_trial_wavs() {
            assert_eq!(
                hound::WavReader::open(source.path()).unwrap().duration(),
                2480
            );
        }
    }
}

#[test]
fn iti_uses_existing_ties_even_samples_and_rejects_invalid_values() {
    let (mut design, preview, variants) = fixture();
    let (assets, cue) = assets();
    let cancel = AtomicBool::new(false);
    for (ms, frames) in [(0.0625, 0), (0.1875, 2)] {
        design["protocol"]["trial_strips"][0]["metadata"] = json!({"iti_ms":ms});
        let result =
            plan_assembly_preview(&design, &preview, &variants, &assets, &cue, &cancel).unwrap();
        assert_eq!(
            result.preview["blocks"][0]["preview_rows"][0]["native_iti_frames"],
            frames
        );
    }
    for invalid in [
        json!(-1),
        json!("NaN"),
        json!("infinite"),
        json!({"value":300}),
    ] {
        design["protocol"]["trial_strips"][0]["metadata"] = json!({"iti_ms":invalid});
        assert_eq!(
            plan_assembly_preview(&design, &preview, &variants, &assets, &cue, &cancel)
                .unwrap_err(),
            GenerationError::Invalid("assembly_iti_ms")
        );
    }
}

#[test]
fn reported_iti_range_has_reviewed_identity_bound_toolkit_delay_and_real_pcm() {
    let (mut design, preview, variants) = fixture();
    design["protocol"]["trial_strips"][0]["metadata"] =
        json!({"iti_ms":"1000-1500","iti_policy":"paper_randomized_1000_to_1500_ms"});
    let (assets, cue) = assets();
    let cancel = AtomicBool::new(false);
    let proposed =
        plan_assembly_preview(&design, &preview, &variants, &assets, &cue, &cancel).unwrap();
    let repeated =
        plan_assembly_preview(&design, &preview, &variants, &assets, &cue, &cancel).unwrap();
    assert_eq!(proposed.preview, repeated.preview);
    assert_eq!(proposed.preview_sha256, repeated.preview_sha256);
    let rows = proposed.preview["blocks"].clone();
    let mut seeds = std::collections::BTreeSet::new();
    for block in rows.as_array().unwrap() {
        for row in block["preview_rows"].as_array().unwrap() {
            assert_eq!(row["iti_ms"], "1000-1500");
            assert_eq!(row["iti_policy"], "paper_randomized_1000_to_1500_ms");
            assert_eq!(
                row["native_iti_materialization_policy"],
                NATIVE_ITI_RANGE_POLICY
            );
            assert_eq!(row["native_iti_anchor"], "after_trial_audio_end");
            assert_eq!(row["native_iti_source_distribution_reported"], false);
            assert_eq!(row["native_iti_source_anchor_reported"], false);
            assert_eq!(row["native_iti_legacy_compatible"], false);
            let ms = row["native_resolved_iti_ms"].as_u64().unwrap();
            assert!((1000..=1500).contains(&ms));
            assert_eq!(row["native_iti_frames"], ms * 8);
            let seed = row["native_iti_seed_sha256"].as_str().unwrap();
            assert_eq!(seed.len(), 64);
            assert!(seeds.insert(seed.to_owned()));
        }
    }
    let dh = proposed.design_sha256.clone();
    let ph = proposed.preview_sha256.clone();
    let accepted = accept_assembly_preview(proposed, &dh, &ph, 1).unwrap();
    let temp = Temp::new();
    let staged = prepare_accepted_session(
        &accepted,
        &assets,
        &cue,
        &temp.path.join("range"),
        "P001",
        "range",
        &cancel,
    )
    .unwrap();
    let verified =
        verify_prepared_session(VerificationRequest::new(staged.manifest_path())).unwrap();
    for (block, planned) in verified.blocks().iter().zip(rows.as_array().unwrap()) {
        let mut wav = hound::WavReader::open(block.wav_path()).unwrap();
        let pcm: Vec<f32> = wav.samples::<f32>().map(Result::unwrap).collect();
        let mut cursor = 0;
        for row in planned["preview_rows"].as_array().unwrap() {
            let gap = row["native_iti_frames"].as_u64().unwrap() as usize;
            assert!(pcm[cursor * 3..(cursor + 2480) * 3]
                .iter()
                .any(|v| *v != 0.0));
            assert!(pcm[(cursor + 2480) * 3..(cursor + 2480 + gap) * 3]
                .iter()
                .all(|v| *v == 0.0));
            cursor += 2480 + gap;
        }
        assert_eq!(wav.duration() as usize, cursor);
        let mut csv = csv::Reader::from_path(block.manifest_path()).unwrap();
        let header = csv.headers().unwrap().clone();
        let original = header.iter().position(|v| v == "iti_ms").unwrap();
        let selected = header
            .iter()
            .position(|v| v == "native_resolved_iti_ms")
            .unwrap();
        for (row, planned) in csv
            .records()
            .zip(planned["preview_rows"].as_array().unwrap())
        {
            let row = row.unwrap();
            assert_eq!(&row[original], "1000-1500");
            assert_eq!(
                row[selected].parse::<u64>().unwrap(),
                planned["native_resolved_iti_ms"].as_u64().unwrap()
            );
        }
    }
}
fn accept(
    design: &Value,
    preview: &Value,
    variants: &Value,
    assets: &[VerifiedAssemblyAsset],
    cue: &VerifiedAssemblyAsset,
) -> AcceptedAssemblyPlan {
    let preview = plan_assembly_preview(
        design,
        preview,
        variants,
        assets,
        cue,
        &AtomicBool::new(false),
    )
    .unwrap();
    let dh = preview.design_sha256.clone();
    let ph = preview.preview_sha256.clone();
    accept_assembly_preview(preview, &dh, &ph, 7).unwrap()
}

fn signed_soa_fixture(soa_ms: f64) -> (Value, Value, Value) {
    let (mut design, mut preview, _) = fixture();
    design["protocol"]["trial_strips"][0]["elements"] = json!([
        {"kind":"jitter","label":"Wait","jitter_values_ms":[1000]},
        {"kind":"looming_stimulus","source_labels":["Noise"]}
    ]);
    let key = "jitter_1000ms + Noise";
    let variants = json!([{"row_label":"Row","sequence_variant_key":key,"choices":[
        {"kind":"jitter","label":"Wait (1000 ms)","value":1000},
        {"kind":"audio","label":"Noise"}
    ]}]);
    for block in preview["blocks"].as_array_mut().unwrap() {
        for row in block["preview_rows"].as_array_mut().unwrap() {
            row["sequence_variant_key"] = json!(key);
            row["sequence_labels"] = json!("Wait (1000 ms) | Noise");
            row["soa_ms"] = json!(soa_ms);
        }
    }
    (design, preview, variants)
}

#[test]
fn signed_soa_preserves_real_prefix_cue_pcm_and_verified_schedule() {
    let root = Temp::new();
    let (assets, cue) = assets();
    let (design, preview, variants) = signed_soa_fixture(-700.0);
    let cancel = AtomicBool::new(false);
    let enriched =
        plan_assembly_preview(&design, &preview, &variants, &assets, &cue, &cancel).unwrap();
    for block in enriched.preview["blocks"].as_array().unwrap() {
        let rows = block["preview_rows"].as_array().unwrap();
        assert_eq!(rows[0]["looming_segment_onset_s"], 1.0);
        assert_eq!(rows[0]["tactile_onset_s"], 0.3);
        assert_eq!(rows[0]["duration_s"], 1.2);
        assert_eq!(rows[1]["tactile_onset_s"], "");
    }
    let plan = accept(&design, &preview, &variants, &assets, &cue);
    let staged = prepare_accepted_session(
        &plan,
        &assets,
        &cue,
        &root.path.join("candidate"),
        "P001",
        "S001",
        &cancel,
    )
    .unwrap();
    let verified =
        verify_prepared_session(VerificationRequest::new(staged.manifest_path())).unwrap();
    for (index, block) in verified.blocks().iter().enumerate() {
        let mut options = BlockScheduleOptions::new((index + 1) as i64);
        options.sample_rate = 8000;
        options.block_wav_path = Some(block.wav_path().to_owned());
        let schedule = compile_verified_block_schedule(
            block.manifest_path(),
            block.manifest_sha256(),
            options,
        )
        .unwrap();
        let tactile: Vec<_> = schedule
            .events()
            .iter()
            .filter(|event| event.event_type == "tactile_onset")
            .map(|event| event.sample_index)
            .collect();
        assert_eq!(tactile, [2400]);
        let mut csv = csv::Reader::from_path(block.manifest_path()).unwrap();
        let soa_column = csv
            .headers()
            .unwrap()
            .iter()
            .position(|s| s == "soa_ms")
            .unwrap();
        let first = csv.records().next().unwrap().unwrap();
        assert_eq!(first[soa_column].parse::<f64>().unwrap(), -700.0);
        let mut wav = hound::WavReader::open(block.wav_path()).unwrap();
        assert_eq!(wav.duration(), 19_200);
        let pcm: Vec<f32> = wav.samples::<f32>().map(Result::unwrap).collect();
        for (frame, channels) in pcm.chunks_exact(3).enumerate() {
            assert_eq!(
                channels[2],
                if (2400..2480).contains(&frame) {
                    0.7
                } else {
                    0.0
                }
            );
            if frame < 8000 {
                assert_eq!(&channels[..2], &[0.0, 0.0]);
            }
        }
        assert_eq!(pcm[8000 * 3], if index == 0 { 0.05 } else { 0.0 });
        assert_eq!(pcm[8000 * 3 + 1], if index == 0 { -0.025 } else { 0.0 });
    }
}

#[test]
fn signed_soa_checks_whole_cue_bounds_and_keeps_ties_to_even_offset_rounding() {
    let (assets, cue) = assets();
    for (soa_ms, expected_sample) in [
        (-1000.0, 0),
        (190.0, 9520),
        (-0.0625, 8000),
        (0.0625, 8000),
        (-0.1875, 7998),
        (0.1875, 8002),
    ] {
        let (design, preview, variants) = signed_soa_fixture(soa_ms);
        let enriched = plan_assembly_preview(
            &design,
            &preview,
            &variants,
            &assets,
            &cue,
            &AtomicBool::new(false),
        )
        .unwrap_or_else(|error| panic!("SOA {soa_ms}: {error:?}"));
        assert_eq!(
            enriched.preview["blocks"][0]["preview_rows"][0]["tactile_onset_s"],
            expected_sample as f64 / 8000.0,
            "SOA {soa_ms}"
        );
    }
    for soa_ms in [-1000.125, 190.125, -1e300, 1e300] {
        let (design, preview, variants) = signed_soa_fixture(soa_ms);
        assert!(
            plan_assembly_preview(
                &design,
                &preview,
                &variants,
                &assets,
                &cue,
                &AtomicBool::new(false),
            )
            .is_err(),
            "out-of-trial SOA {soa_ms} must fail without adding padding"
        );
    }
}

#[test]
fn reviewed_rows_keep_order_and_actual_prefix_timing_through_real_package_and_schedule() {
    let root = Temp::new();
    let (assets, cue) = assets();
    let (design, preview, variants) = fixture();
    let cancel = AtomicBool::new(false);
    let enriched =
        plan_assembly_preview(&design, &preview, &variants, &assets, &cue, &cancel).unwrap();
    assert_eq!(enriched.preview["accepted"], false);
    assert_eq!(
        enriched.preview["blocks"][0]["preview_rows"][0]["looming_segment_onset_s"],
        0.11
    );
    assert_eq!(
        enriched.preview["blocks"][0]["preview_rows"][0]["tactile_onset_s"],
        0.16
    );
    assert_eq!(
        enriched.preview["blocks"][0]["preview_rows"][1]["tactile_onset_s"],
        ""
    );
    let dh = enriched.design_sha256.clone();
    let ph = enriched.preview_sha256.clone();
    let plan = accept_assembly_preview(enriched, &dh, &ph, 7).unwrap();
    let staged = prepare_accepted_session(
        &plan,
        &assets,
        &cue,
        &root.path.join("candidate"),
        "P001",
        "S001",
        &cancel,
    )
    .unwrap();
    assert_eq!(staged.block_count(), 2);
    assert_eq!(staged.trial_count(), 4);
    let verified = verify_prepared_session(
        VerificationRequest::new(staged.manifest_path()).with_participant_id("P001"),
    )
    .unwrap();
    assert_eq!(verified.blocks().len(), 2);
    assert_eq!(
        verified
            .summary()
            .blocks
            .iter()
            .map(|b| b.trial_count)
            .collect::<Vec<_>>(),
        [2, 2]
    );
    let mut observed_pool = Vec::new();
    for (i, block) in verified.blocks().iter().enumerate() {
        let mut options = BlockScheduleOptions::new((i + 1) as i64);
        options.sample_rate = 8000;
        options.block_label = format!("Block {}", i + 1);
        options.block_wav_path = Some(block.wav_path().to_owned());
        let schedule = compile_verified_block_schedule(
            block.manifest_path(),
            block.manifest_sha256(),
            options,
        )
        .unwrap();
        assert_eq!(schedule.summary().trial_row_count, 2);
        let tactile: Vec<_> = schedule
            .events()
            .iter()
            .filter(|e| e.event_type == "tactile_onset")
            .map(|e| e.sample_index)
            .collect();
        assert_eq!(tactile, [1280]);
        let starts: Vec<_> = schedule
            .events()
            .iter()
            .filter(|e| e.event_type == "trial_start")
            .map(|e| e.sample_index)
            .collect();
        assert_eq!(starts, [0, 2480]);
        let mut csv = csv::Reader::from_path(block.manifest_path()).unwrap();
        let headers = csv.headers().unwrap().clone();
        let pool = headers
            .iter()
            .position(|s| s == "trial_pool_index")
            .unwrap();
        for row in csv.records() {
            observed_pool.push(row.unwrap()[pool].parse::<usize>().unwrap());
        }
        let mut wav = hound::WavReader::open(block.wav_path()).unwrap();
        assert_eq!(wav.spec().channels, 3);
        assert_eq!(wav.duration(), 4960);
        let pcm: Vec<f32> = wav.samples::<f32>().map(Result::unwrap).collect();
        assert!((pcm[0] - 0.2 * 10.0_f32.powf(-6.0 / 20.0)).abs() < 1e-7);
        assert_eq!(&pcm[800 * 3..880 * 3], vec![0.0; 80 * 3]);
        assert_eq!(pcm[1280 * 3 + 2], 0.7);
        assert_eq!(pcm[(2480 + 1280) * 3 + 2], 0.0);
        assert_eq!(pcm[900 * 3], if i == 0 { 0.05 } else { 0.0 });
        assert_eq!(pcm[900 * 3 + 1], if i == 0 { -0.025 } else { 0.0 });
    }
    assert_eq!(observed_pool, [4, 1, 2, 3]);
    let setup: Value = serde_json::from_slice(
        &fs::read(root.path.join("candidate/run_setup_manifest.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(setup["approved_segment5"]["randomization_seed"], 20260745);
    assert_eq!(setup["approved_preview_sha256"], ph);
    let trial = verified.blocks()[0].source_trial_wavs()[0].path();
    fs::write(trial, b"changed").unwrap();
    assert!(verify_prepared_session(VerificationRequest::new(staged.manifest_path())).is_err());
}

fn participant_fixture() -> (Value, Value, Value) {
    let (mut design, preview, variants) = fixture();
    design["protocol"]["participants"] = json!(2);
    design["protocol"]["participant_order_policy"] = json!({"schema":"pps-participant-order-policy.v1","algorithm":"counterbalanced_rotation","seed":17});
    design["study_profile_reference_parameters"]["dashboard_run_setup"] = json!({"experiment_structure":"pre_post","seed":41,"instruction_profile":{"schema":"pps-run-instructions.v1","slots":[
        {"slot":"before_experiment","enabled":true,"path":"speech","continue_mode":"click"},
        {"slot":"before_each_block","enabled":true,"path":"speech","continue_mode":"delay","delay_s":0.5},
        {"slot":"between_conditions","enabled":true,"path":"speech","continue_mode":"button","button_label":"Start Part 2"}
    ]}});
    (design, preview, variants)
}

#[test]
fn stationary_receipt_cannot_relabel_the_identical_moving_asset_or_stale_hash() {
    let (mut assets, cue) = assets();
    let (mut design, preview, variants) = fixture();
    design["protocol"]["baseline_strategy"] = json!("stationary_burst");
    design["noises"][0]["native_stationary_baseline_asset"] = json!("comparator");
    assets.push(asset(
        "comparator",
        AssemblyAssetRole::StationaryBaseline,
        8000,
        2,
        1600,
        0.05,
        -0.025,
    ));
    let cancel = AtomicBool::new(false);
    assert!(matches!(
        plan_assembly_preview(&design, &preview, &variants, &assets, &cue, &cancel),
        Err(GenerationError::Invalid(
            "assembly_stationary_comparator_contract"
        ))
    ));
    assets.pop();
    assets.push(asset(
        "comparator",
        AssemblyAssetRole::StationaryBaseline,
        8000,
        2,
        1600,
        0.03,
        -0.02,
    ));
    design["noises"][0]["native_stationary_baseline_sha256"] = json!("0".repeat(64));
    assert!(matches!(
        plan_assembly_preview(&design, &preview, &variants, &assets, &cue, &cancel),
        Err(GenerationError::Invalid(
            "assembly_stationary_comparator_contract"
        ))
    ));
}

#[test]
fn accepted_participant_order_keeps_separate_parts_and_verified_instruction_pcm() {
    let temp = Temp::new();
    let (assets, cue) = assets();
    let (design, preview, variants) = participant_fixture();
    let cancel = AtomicBool::new(false);
    let source =
        plan_assembly_preview(&design, &preview, &variants, &assets, &cue, &cancel).unwrap();
    let order = plan_run_order_preview(&source, &assets, &cancel).unwrap();
    let expected: Vec<usize> = order.preview["csv_rows"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|r| r["participant_index"] == 2)
        .map(|r| r["source_block_index"].as_u64().unwrap() as usize)
        .collect();
    assert_eq!(expected.len(), 4);
    assert_eq!(
        order.preview["instruction_profile"]["slots"][0]["sha256"],
        assets[0].sha256()
    );
    assert_eq!(
        order.preview["instruction_profile"]["slots"][1]["delay_s"],
        0.5
    );
    let (dh, sh, rh) = (
        source.design_sha256.clone(),
        source.preview_sha256.clone(),
        order.run_order_sha256.clone(),
    );
    let accepted = accept_participant_assembly(source, order, &dh, &sh, &rh, 9).unwrap();
    assert_eq!(accepted.revision(), 9);
    let staged = prepare_accepted_participant(
        &accepted,
        &assets,
        &cue,
        &temp.path.join("group"),
        2,
        "P002_20261027_120000",
        &cancel,
    )
    .unwrap();
    assert_eq!(staged.parts().len(), 2);
    let group: Value =
        serde_json::from_slice(&fs::read(staged.group_manifest_path().unwrap()).unwrap()).unwrap();
    assert_eq!(group["schema"], "pps-run-session-group.v1");
    assert_eq!(group["full_experiment_completed"], false);
    let mut observed = Vec::new();
    for (part_index, part) in staged.parts().iter().enumerate() {
        let verified = verify_prepared_session(
            VerificationRequest::new(part.manifest_path()).with_participant_id("P002"),
        )
        .unwrap();
        let id = format!("P002_20261027_120000_part_{:02}", part_index + 1);
        assert_eq!(verified.summary().session_id, id);
        assert_eq!(verified.summary().part_session_id, id);
        assert_eq!(verified.summary().part_number, Some(part_index as i64 + 1));
        assert_eq!(verified.summary().session_group_id, "P002_20261027_120000");
        let manifest: Value =
            serde_json::from_slice(&fs::read(part.manifest_path()).unwrap()).unwrap();
        assert_eq!(manifest["part_split_schema"], "pps-runner-part-split.v1");
        assert_eq!(
            manifest["sibling_part_manifest_paths"][0],
            json!(staged.parts()[1 - part_index].manifest_path())
        );
        assert_eq!(manifest["full_experiment_completed"], false);
        for slot in manifest["instruction_profile"]["slots"]
            .as_array()
            .unwrap()
            .iter()
            .filter(|s| s["enabled"] == true)
        {
            let bytes = fs::read(slot["path"].as_str().unwrap()).unwrap();
            assert_eq!(
                format!("{:x}", Sha256::digest(&bytes)),
                slot["sha256"].as_str().unwrap()
            );
            let mut wav = hound::WavReader::new(Cursor::new(bytes)).unwrap();
            assert_eq!(wav.spec().channels, 1);
            assert_eq!(wav.spec().sample_rate, 8000);
            assert_eq!(wav.duration(), 800);
            assert!(wav.samples::<f32>().all(|s| s.unwrap() == 0.2));
            assert_eq!(slot["source_asset_sha256"], assets[0].sha256());
        }
        for (block_position, block) in verified.blocks().iter().enumerate() {
            let source_index = expected[part_index * 2 + block_position];
            observed.push(source_index);
            let mut reader = csv::Reader::from_path(block.manifest_path()).unwrap();
            let header = reader.headers().unwrap().clone();
            let rows: Vec<_> = reader.records().map(Result::unwrap).collect();
            let get = |row: usize, name: &str| {
                rows[row]
                    .get(header.iter().position(|h| h == name).unwrap())
                    .unwrap()
            };
            assert_eq!(get(0, "Part_Session_ID"), id);
            assert_eq!(get(0, "Part_Number"), (part_index + 1).to_string());
            assert_eq!(get(0, "Block_Number"), (block_position + 1).to_string());
            assert_eq!(
                get(0, "Global_Block_Index"),
                (part_index * 2 + block_position + 1).to_string()
            );
            assert_eq!(get(0, "Source_Block_Index"), source_index.to_string());
            assert_eq!(
                get(0, "trial_pool_index"),
                if source_index == 1 { "4" } else { "2" }
            );
            assert_eq!(
                get(1, "trial_pool_index"),
                if source_index == 1 { "1" } else { "3" }
            );
            assert_eq!(
                get(0, "Phase"),
                if part_index == 0 { "pre" } else { "post" }
            );
            let mut options = BlockScheduleOptions::new((block_position + 1) as i64);
            options.sample_rate = 8000;
            options.block_wav_path = Some(block.wav_path().to_owned());
            let schedule = compile_verified_block_schedule(
                block.manifest_path(),
                block.manifest_sha256(),
                options,
            )
            .unwrap();
            assert_eq!(schedule.summary().trial_row_count, 2);
            assert_eq!(
                schedule
                    .events()
                    .iter()
                    .filter(|e| e.event_type == "tactile_onset")
                    .map(|e| e.sample_index)
                    .collect::<Vec<_>>(),
                [1280]
            );
        }
    }
    assert_eq!(observed, expected);
    assert!(matches!(
        prepare_accepted_participant(
            &accepted,
            &assets,
            &cue,
            &temp.path.join("cancelled"),
            2,
            "P002_cancelled",
            &AtomicBool::new(true)
        ),
        Err(GenerationError::Cancelled)
    ));
    assert!(!temp.path.join("cancelled").exists());
    if std::env::var("PPS_KEEP_PARTICIPANT_FIXTURE").as_deref() == Ok("1") {
        println!(
            "Verified participant fixture retained at {}",
            temp.path.display()
        );
        std::mem::forget(temp);
    }
}

#[test]
fn participant_acceptance_rejects_tampering_stale_assets_and_missing_instructions() {
    let (assets, cue) = assets();
    let (mut design, preview, variants) = participant_fixture();
    let cancel = AtomicBool::new(false);
    let source =
        plan_assembly_preview(&design, &preview, &variants, &assets, &cue, &cancel).unwrap();
    let mut order = plan_run_order_preview(&source, &assets, &cancel).unwrap();
    let (dh, sh, rh) = (
        source.design_sha256.clone(),
        source.preview_sha256.clone(),
        order.run_order_sha256.clone(),
    );
    order.preview["csv_rows"][0]["source_block_index"] = json!(2);
    order.preview["instruction_profile"]["slots"][0]["continue_mode"] = json!("delay");
    assert!(accept_participant_assembly(source, order, &dh, &sh, &rh, 1).is_err());
    design["study_profile_reference_parameters"]["dashboard_run_setup"]["instruction_profile"]
        ["slots"][0]["path"] = json!("arbitrary-unverified-local-path");
    let source =
        plan_assembly_preview(&design, &preview, &variants, &assets, &cue, &cancel).unwrap();
    assert!(matches!(
        plan_run_order_preview(&source, &assets, &cancel),
        Err(GenerationError::Invalid(
            "assembly_instruction_asset_required"
        ))
    ));
    design["study_profile_reference_parameters"]["dashboard_run_setup"]["instruction_profile"]
        ["slots"][0]["path"] = json!("noise");
    let source =
        plan_assembly_preview(&design, &preview, &variants, &assets, &cue, &cancel).unwrap();
    assert!(matches!(
        plan_run_order_preview(&source, &assets, &cancel),
        Err(GenerationError::Invalid("assembly_instruction_asset_role"))
    ));
    assert!(matches!(
        plan_run_order_preview(&source, &assets[..1], &cancel),
        Err(GenerationError::Invalid("assembly_assets_changed"))
    ));
}

#[test]
fn explicit_membership_filters_whole_blocks_and_single_session_has_no_fabricated_part() {
    let temp = Temp::new();
    let (assets, cue) = assets();
    let (mut design, preview, variants) = participant_fixture();
    design["study_profile_reference_parameters"]["dashboard_run_setup"]["experiment_structure"] =
        json!("single");
    design["protocol"]["participant_order_policy"] =
        json!({"algorithm":"fixed","seed":0,"part_membership":{"single":["Block 2"]}});
    let cancel = AtomicBool::new(false);
    let source =
        plan_assembly_preview(&design, &preview, &variants, &assets, &cue, &cancel).unwrap();
    let order = plan_run_order_preview(&source, &assets, &cancel).unwrap();
    assert_eq!(order.preview["csv_rows"].as_array().unwrap().len(), 2);
    assert_eq!(order.preview["csv_rows"][0]["source_block_index"], 2);
    let (dh, sh, rh) = (
        source.design_sha256.clone(),
        source.preview_sha256.clone(),
        order.run_order_sha256.clone(),
    );
    let accepted = accept_participant_assembly(source, order, &dh, &sh, &rh, 4).unwrap();
    let staged = prepare_accepted_participant(
        &accepted,
        &assets,
        &cue,
        &temp.path.join("single"),
        1,
        "P001_single",
        &cancel,
    )
    .unwrap();
    assert!(staged.group_manifest_path().is_none());
    assert_eq!(staged.parts().len(), 1);
    let package =
        verify_prepared_session(VerificationRequest::new(staged.parts()[0].manifest_path()))
            .unwrap();
    assert_eq!(package.summary().session_id, "P001_single");
    assert_eq!(package.summary().session_group_id, "");
    // Existing V1 verification projects absent part_session_id as session_id;
    // the writer must still omit split identity fields for a single session.
    assert_eq!(package.summary().part_session_id, "P001_single");
    let manifest: Value =
        serde_json::from_slice(&fs::read(staged.parts()[0].manifest_path()).unwrap()).unwrap();
    assert!(manifest.get("part_number").is_none());
    assert!(manifest.get("part_session_id").is_none());
    assert!(manifest.get("part_split_schema").is_none());
    assert_eq!(package.summary().part_number, None);
    assert_eq!(package.blocks().len(), 1);
    assert_eq!(package.summary().blocks[0].label, "Block 2");
    assert_eq!(package.summary().blocks[0].index, 1);
    assert_eq!(staged.parts()[0].trial_count(), 2);
}

#[test]
fn stale_truncated_ambiguous_and_cancelled_inputs_never_create_publishable_output() {
    let root = Temp::new();
    let (assets, cue) = assets();
    let (design, preview, variants) = fixture();
    let cancel = AtomicBool::new(false);
    for mutation in 0..5 {
        let mut p = preview.clone();
        match mutation {
            0 => {
                p["blocks"][0]["preview_rows"].as_array_mut().unwrap().pop();
            }
            1 => p["blocks"][1]["preview_rows"][0]["block_trial_index"] = json!(3),
            2 => p["total_trials"] = json!(5),
            3 => p["blocks"][1]["preview_rows"][0]["trial_pool_index"] = json!(4),
            _ => p["blocks"][0]["preview_rows"][0]["soa_ms"] = json!(99999),
        }
        assert!(plan_assembly_preview(&design, &p, &variants, &assets, &cue, &cancel).is_err());
    }
    let enriched =
        plan_assembly_preview(&design, &preview, &variants, &assets, &cue, &cancel).unwrap();
    let ph = enriched.preview_sha256.clone();
    assert!(accept_assembly_preview(enriched, "stale", &ph, 7).is_err());
    let mut enriched =
        plan_assembly_preview(&design, &preview, &variants, &assets, &cue, &cancel).unwrap();
    let dh = enriched.design_sha256.clone();
    let ph = enriched.preview_sha256.clone();
    enriched.preview["blocks"][0]["preview_rows"]
        .as_array_mut()
        .unwrap()
        .reverse();
    assert!(accept_assembly_preview(enriched, &dh, &ph, 7).is_err());
    let plan = accept(&design, &preview, &variants, &assets, &cue);
    let destination = root.path.join("cancelled");
    assert_eq!(
        prepare_accepted_session(
            &plan,
            &assets,
            &cue,
            &destination,
            "P001",
            "S001",
            &AtomicBool::new(true)
        )
        .unwrap_err(),
        GenerationError::Cancelled
    );
    assert!(!destination.exists());
    let mut changed = assets;
    changed[1] = asset(
        "noise",
        AssemblyAssetRole::BinauralIngredient,
        8000,
        2,
        1600,
        0.1,
        0.1,
    );
    assert!(prepare_accepted_session(
        &plan,
        &changed,
        &cue,
        &root.path.join("changed"),
        "P001",
        "S001",
        &cancel
    )
    .is_err());
    assert!(!root.path.join("changed").exists());
    let mut ambiguous = variants.clone();
    ambiguous.as_array_mut().unwrap().push(variants[0].clone());
    assert!(plan_assembly_preview(&design, &preview, &ambiguous, &changed, &cue, &cancel).is_err());
}

#[test]
fn stationary_comparators_and_sample_rates_are_explicit_no_substitution() {
    let root = Temp::new();
    let (mut assets, cue) = assets();
    let (mut design, preview, variants) = fixture();
    let cancel = AtomicBool::new(false);
    design["protocol"]["baseline_strategy"] = json!("stationary_burst");
    assert_eq!(
        plan_assembly_preview(&design, &preview, &variants, &assets, &cue, &cancel).unwrap_err(),
        GenerationError::Invalid("assembly_stationary_comparator_required")
    );
    assets.push(asset(
        "stationary",
        AssemblyAssetRole::StationaryBaseline,
        8000,
        2,
        1600,
        0.012,
        -0.01,
    ));
    design["noises"][0]["native_stationary_baseline_asset"] = json!("stationary");
    let plan = accept(&design, &preview, &variants, &assets, &cue);
    let staged = prepare_accepted_session(
        &plan,
        &assets,
        &cue,
        &root.path.join("stationary"),
        "P001",
        "S001",
        &cancel,
    )
    .unwrap();
    let verified =
        verify_prepared_session(VerificationRequest::new(staged.manifest_path())).unwrap();
    let mut wav = hound::WavReader::open(verified.blocks()[1].wav_path()).unwrap();
    let pcm: Vec<f32> = wav.samples::<f32>().map(Result::unwrap).collect();
    assert_eq!(pcm[900 * 3], 0.012);
    assert_eq!(pcm[900 * 3 + 1], -0.01);
    assets[0] = asset(
        "speech",
        AssemblyAssetRole::Instruction,
        44100,
        1,
        4410,
        0.2,
        0.0,
    );
    assert_eq!(
        plan_assembly_preview(&design, &preview, &variants, &assets, &cue, &cancel).unwrap_err(),
        GenerationError::Invalid("assembly_asset_rate_requires_explicit_resampling")
    );
}

#[test]
fn pre_post_requires_accepted_participant_order_before_creating_output() {
    let root = Temp::new();
    let (assets, cue) = assets();
    let (mut design, preview, variants) = fixture();
    design["study_profile_reference_parameters"]["dashboard_run_setup"] =
        json!({"experiment_structure":"pre_post"});
    let plan = accept(&design, &preview, &variants, &assets, &cue);
    assert_eq!(
        prepare_accepted_session(
            &plan,
            &assets,
            &cue,
            &root.path.join("prepost"),
            "P001",
            "S001",
            &AtomicBool::new(false)
        )
        .unwrap_err(),
        GenerationError::Invalid("assembly_participant_run_order_required")
    );
    assert!(!root.path.join("prepost").exists());
}

#[test]
#[ignore = "requires PPS_BROWSER_BLOCK_PLAN pointing at an actual exported complete browser fixture"]
fn actual_browser_snapshot_preserves_assets_and_reports_missing_stationary_comparator() {
    let path = std::env::var_os("PPS_BROWSER_BLOCK_PLAN").expect("PPS_BROWSER_BLOCK_PLAN required");
    let snapshot: Value = serde_json::from_slice(&fs::read(path).unwrap()).unwrap();
    let design = &snapshot["design"];
    let preview = &snapshot["block_csv_preview"];
    let variants = &snapshot["variants"];
    let resource_root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../pps-resources");
    let mut refs = std::collections::BTreeSet::new();
    for variant in variants.as_array().unwrap() {
        for choice in variant["choices"].as_array().unwrap() {
            if choice["kind"] == "audio" {
                refs.insert(choice["label"].as_str().unwrap());
            }
        }
    }
    let cancel = AtomicBool::new(false);
    let mut assets = Vec::new();
    for (collection, key, role) in [
        (
            "noises",
            "prebaked_path",
            AssemblyAssetRole::BinauralIngredient,
        ),
        (
            "custom_looming_files",
            "path",
            AssemblyAssetRole::BinauralIngredient,
        ),
        ("prestimulus_files", "path", AssemblyAssetRole::Instruction),
    ] {
        for source in design[collection].as_array().into_iter().flatten() {
            if !refs.contains(source["label"].as_str().unwrap()) {
                continue;
            }
            let reference = source[key].as_str().unwrap();
            assert!(
                reference.starts_with("assets/")
                    && !reference.contains("..")
                    && !reference.contains('\\')
            );
            let bytes = fs::read(resource_root.join(reference)).unwrap();
            let hash = format!("{:x}", Sha256::digest(&bytes));
            assets.push(
                VerifiedAssemblyAsset::from_wav_bytes(reference, &bytes, &hash, role, &cancel)
                    .unwrap(),
            );
        }
    }
    let bytes = fs::read(resource_root.join("assets/tactile/default_tactile_cue.wav")).unwrap();
    let hash = format!("{:x}", Sha256::digest(&bytes));
    let tactile = VerifiedAssemblyAsset::from_wav_bytes(
        "bundled-tactile",
        &bytes,
        &hash,
        AssemblyAssetRole::TactileCue,
        &cancel,
    )
    .unwrap();
    assert_eq!(assets.len(), 4);
    assert!(assets.iter().all(|a| a.sample_rate_hz() == 44100));
    assert_eq!(tactile.sample_rate_hz(), 44100);
    assert_eq!(
        plan_assembly_preview(design, preview, variants, &assets, &tactile, &cancel).unwrap_err(),
        GenerationError::Invalid("assembly_stationary_comparator_required")
    );
    eprintln!("Actual complete browser snapshot checked: {} blocks, {} rows, {} verified used assets, tactile {} frames; unavailable stationary comparators rejected.",preview["block_count"],preview["total_trials"],assets.len(),tactile.frames());
}
