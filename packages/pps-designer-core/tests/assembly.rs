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
