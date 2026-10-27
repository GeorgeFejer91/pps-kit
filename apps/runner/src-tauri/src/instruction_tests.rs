// Included in runtime::tests so the existing native fixture/runtime helpers
// remain private. No device is opened by these callback tests.
fn instruction_group_fixture() -> (
    std::path::PathBuf,
    pps_session_package::VerifiedPreparedGroup,
) {
    instruction_group_fixture_with_blocks(2)
}

fn instruction_group_fixture_with_blocks(block_count: u32) -> (
    std::path::PathBuf,
    pps_session_package::VerifiedPreparedGroup,
) {
    use pps_designer_core::assembly::*;
    use serde_json::json;
    use sha2::{Digest, Sha256};
    let cancel = AtomicBool::new(false);
    let make_asset = |name: &str, role, mono: bool, frames: u32| {
        let mut bytes = pcm16_wav_bytes(8000, frames, 500);
        if mono {
            let samples: Vec<u8> = bytes[44..]
                .chunks_exact(4)
                .flat_map(|frame| frame[..2].iter().copied())
                .collect();
            bytes.truncate(44);
            bytes[4..8].copy_from_slice(&(36 + samples.len() as u32).to_le_bytes());
            bytes[22..24].copy_from_slice(&1u16.to_le_bytes());
            bytes[28..32].copy_from_slice(&16000u32.to_le_bytes());
            bytes[32..34].copy_from_slice(&2u16.to_le_bytes());
            bytes[40..44].copy_from_slice(&(samples.len() as u32).to_le_bytes());
            bytes.extend(samples);
        }
        VerifiedAssemblyAsset::from_wav_bytes(
            name,
            &bytes,
            &format!("{:x}", Sha256::digest(&bytes)),
            role,
            &cancel,
        )
        .unwrap()
    };
    let assets = vec![
        make_asset("speech", AssemblyAssetRole::Instruction, true, 80),
        make_asset("noise", AssemblyAssetRole::BinauralIngredient, false, 800),
    ];
    let cue = make_asset("cue", AssemblyAssetRole::TactileCue, true, 80);
    let design = json!({"noises":[{"label":"Noise","prebaked_path":"noise","gain":1.0}],"custom_looming_files":[],"prestimulus_files":[],
    "protocol":{"blocks":block_count,"participants":1,"random_seed":17,"baseline_strategy":"tactile_only","participant_order_policy":{"schema":"pps-participant-order-policy.v1","algorithm":"counterbalanced_rotation","seed":17},
        "trial_strips":[{"label":"Row","elements":[{"kind":"looming_stimulus","source_labels":["Noise"]}]}]},
    "study_profile_reference_parameters":{"dashboard_run_setup":{"experiment_structure":"pre_post","seed":41,"instruction_profile":{"schema":"pps-run-instructions.v1","slots":[
        {"slot":"before_experiment","enabled":true,"path":"speech","continue_mode":"click"},
        {"slot":"before_each_block","enabled":true,"path":"speech","continue_mode":"button","button_label":"Begin block"},
        {"slot":"after_each_block","enabled":true,"path":"speech","continue_mode":"delay","delay_s":0.02},
        {"slot":"between_conditions","enabled":true,"path":"speech","continue_mode":"button","button_label":"Next part"},
        {"slot":"after_experiment","enabled":true,"path":"speech","continue_mode":"click"}
    ]}}}});
    let variants = json!([{"row_label":"Row","sequence_variant_key":"Noise","choices":[{"kind":"audio","label":"Noise"}]}]);
    let blocks:Vec<Value> = (1..=block_count).map(|index| json!({"block_index":index,"block_label":format!("Block {index}"),"trial_count":1,"duration_ms":100,"preview_row_count":1,"preview_rows":[
        {"block_index":index,"block_label":format!("Block {index}"),"block_trial_index":1,"trial_pool_index":index,"family":"catch","row_label":"Row","sequence_variant_key":"Noise","sequence_labels":"Noise","soa_ms":0,"duration_ms":100,"duration_s":0.1,"looming_segment_onset_s":0,"tactile_onset_s":"","baseline_mode":"tactile_only","trial_file_path":"static://placeholder","source_sha256":""}]})).collect();
    let preview = json!({"schema":"pps-block-csv-preview.v1","accepted":true,"block_count":block_count,"total_trials":block_count,"total_count":block_count,"randomization_seed":17,"randomization_strategy":"seeded_gellermann_row_order_preserving","blocks":blocks});
    let source =
        plan_assembly_preview(&design, &preview, &variants, &assets, &cue, &cancel).unwrap();
    let order = plan_run_order_preview(&source, &assets, &cancel).unwrap();
    let (dh, sh, rh) = (
        source.design_sha256.clone(),
        source.preview_sha256.clone(),
        order.run_order_sha256.clone(),
    );
    let accepted = accept_participant_assembly(source, order, &dh, &sh, &rh, 7).unwrap();
    let root = std::env::temp_dir().join(format!("pps-instruction-consumer-{}", random_nonce()));
    let staged = prepare_accepted_participant(
        &accepted,
        &assets,
        &cue,
        &root,
        1,
        "synthetic_instruction_group",
        &cancel,
    )
    .unwrap();
    let verified =
        pps_session_package::verify_prepared_group(staged.group_manifest_path().unwrap()).unwrap();
    (root, verified)
}

fn run_software_part(
    runtime: &AppRuntime,
    control: &FakeControl,
    part: u8,
    abort_at_gate: bool,
) -> Vec<Value> {
    compile_current_execution(runtime);
    let mut gates = Vec::new();
    for _ in 0..32 {
        let preparation =
            tauri::async_runtime::block_on(runtime.begin_next_prepared_audio_preparation_async())
                .unwrap();
        let (guard, source) = match preparation {
            PreparedAudioPreparation::Decode { _guard, source } => (_guard, source),
            _ => panic!("new occurrence must decode"),
        };
        let candidate = prepare_verified_audio(source).unwrap();
        let instruction = candidate.source_receipt().instruction().is_some();
        let channels = candidate.media().channels();
        let rate = candidate.media().sample_rate_hz();
        if instruction {
            assert!(candidate
                .media()
                .interleaved_f32()
                .chunks_exact(3)
                .all(|frame| frame[2] == 0.0));
        }
        runtime.cache_prepared_audio(candidate).unwrap();
        tauri::async_runtime::block_on(runtime.ensure_execution_journal()).unwrap();
        drop(guard);
        let inventory =
            tauri::async_runtime::block_on(runtime.start_native_output_enumerate().unwrap())
                .unwrap()
                .unwrap();
        let mut request = fake_reserve_request(&inventory);
        request.channels = channels;
        request.sample_rate_hz = rate;
        tauri::async_runtime::block_on(runtime.start_native_output_reserve(request).unwrap())
            .unwrap()
            .unwrap();
        assert_eq!(
            runtime
                .dispatch_local(Action::TargetArm, serde_json::json!({}))
                .unwrap()
                .status,
            AppliedStatus::Accepted
        );
        assert_eq!(
            runtime
                .dispatch_local(Action::PartStart, serde_json::json!({"part_number":part}))
                .unwrap()
                .status,
            AppliedStatus::Accepted
        );
        // Production admission expires at six seconds; this assertion leaves
        // a small scheduling margin and never changes that production bound.
        let deadline = std::time::Instant::now() + Duration::from_secs(8);
        let mut handled_gate = false;
        loop {
            let mut output = vec![f32::NAN; 64 * channels as usize];
            control.render_software_callback(&mut output);
            assert!(output
                .iter()
                .all(|sample| sample.is_finite() && sample.abs() <= 1.0));
            let snapshot = runtime.snapshot().unwrap();
            if instruction {
                assert!(!snapshot.run.participant_capture_ready);
                assert!(output.chunks_exact(3).all(|frame| frame[2] == 0.0));
            }
            if snapshot.run.phase == RunnerPhase::InstructionGate && !handled_gate {
                if abort_at_gate {
                    assert_eq!(
                        runtime
                            .dispatch_local(Action::RunStop, serde_json::json!({}))
                            .unwrap()
                            .status,
                        AppliedStatus::Accepted
                    );
                    let mut silence = vec![1.0; 64 * channels as usize];
                    control.render_software_callback(&mut silence);
                    assert!(silence.iter().all(|sample| *sample == 0.0));
                    return gates;
                }
                let gate = snapshot.instruction_gate.clone();
                assert_eq!(
                    runtime
                        .dispatch_local(
                            Action::InstructionContinue,
                            serde_json::json!({"gate_id":"stale"})
                        )
                        .unwrap()
                        .status,
                    AppliedStatus::Rejected
                );
                match gate.next_action.as_str() {
                    "continue-click" => {
                        tauri::async_runtime::block_on(runtime.record_native_response(
                            NativeResponseRequest {
                                choice: String::new(),
                                x: Some(0.5),
                                y: Some(0.5),
                            },
                        ))
                        .unwrap();
                    }
                    "continue-button" => {
                        assert!(
                            tauri::async_runtime::block_on(runtime.record_native_response(
                                NativeResponseRequest {
                                    choice: String::new(),
                                    x: Some(0.5),
                                    y: Some(0.5)
                                }
                            ))
                            .is_err()
                        );
                        assert_eq!(
                            runtime
                                .dispatch_local(
                                    Action::InstructionContinue,
                                    serde_json::json!({"gate_id":gate.gate_id})
                                )
                                .unwrap()
                                .status,
                            AppliedStatus::Accepted
                        );
                    }
                    "continue-delay" => {
                        assert_eq!(
                            runtime
                                .dispatch_local(
                                    Action::InstructionContinue,
                                    serde_json::json!({"gate_id":gate.gate_id})
                                )
                                .unwrap()
                                .status,
                            AppliedStatus::Rejected
                        );
                    }
                    mode => panic!("unknown gate {mode}"),
                }
                gates.push(serde_json::json!({"mode":gate.next_action}));
                handled_gate = true;
            }
            if snapshot.run.phase == RunnerPhase::Prepared {
                break;
            }
            if snapshot.run.phase == RunnerPhase::Completed {
                return gates;
            }
            assert!(
                std::time::Instant::now() < deadline,
                "stage did not finish: {:?}",
                snapshot.run
            );
            std::thread::sleep(Duration::from_millis(2));
        }
    }
    panic!("too many stages")
}

#[test]
fn software_callback_instructions_and_two_parts_preserve_gates_identity_and_results() {
    let (root, group) = instruction_group_fixture_with_blocks(3);
    let expected_parts: Vec<_> = group
        .parts()
        .iter()
        .map(|part| part.summary().part_session_id.clone())
        .collect();
    let control = Arc::new(FakeControl::default());
    control.enable_software_callback();
    let runtime = AppRuntime::with_native_output(fake_coordinator(&control));
    tauri::async_runtime::block_on(runtime.adopt_verified_group_async(group)).unwrap();
    assert!(tauri::async_runtime::block_on(
        runtime.advance_verified_group_part_async(runtime.snapshot().unwrap().revision)
    )
    .is_err());
    assert_eq!(runtime.dispatch_local(Action::SetupSubmit,serde_json::json!({"participant_code":"P001","age":30,"handedness":"right","gender":"other","name_sharing_opt_in":false,"part_labels":{"1":"Pre","2":"Post"}})).unwrap().status,AppliedStatus::Accepted);
    let first = run_software_part(&runtime, &control, 1, false);
    assert!(first.iter().any(|gate| gate["mode"] == "continue-click"));
    assert!(first.iter().any(|gate| gate["mode"] == "continue-delay"));
    assert!(!runtime.snapshot().unwrap().run.complete);
    assert_eq!(
        runtime.snapshot().unwrap().identity.part_session_id,
        expected_parts[0]
    );
    let progress = tauri::async_runtime::block_on(runtime.native_group_status()).unwrap();
    assert_eq!(progress.completed_parts, 1);
    assert!(!progress.experiment_complete);
    assert!(tauri::async_runtime::block_on(
        runtime.advance_verified_group_part_async(progress.revision - 1)
    )
    .is_err());
    tauri::async_runtime::block_on(runtime.advance_verified_group_part_async(progress.revision))
        .unwrap();
    assert_eq!(
        runtime.snapshot().unwrap().identity.part_session_id,
        expected_parts[1]
    );
    let second = run_software_part(&runtime, &control, 2, false);
    assert!(!second.iter().any(|gate| gate["mode"] == "continue-click"));
    let progress = wait_group_publication(&runtime);
    assert!(runtime.snapshot().unwrap().run.complete);
    assert_eq!(progress.completed_parts, 2);
    assert!(progress.experiment_complete);
    for (part, expected_id) in expected_parts.iter().enumerate() {
        let directory = root.join(format!("part_{:02}", part + 1));
        let manifests: Vec<_> = fs::read_dir(&directory)
            .unwrap()
            .map(|e| e.unwrap().path())
            .filter(|p| {
                p.file_name()
                    .unwrap()
                    .to_string_lossy()
                    .ends_with(".results.json")
            })
            .collect();
        assert_eq!(manifests.len(), 1);
        let manifest: Value = serde_json::from_slice(&fs::read(&manifests[0]).unwrap()).unwrap();
        assert_eq!(manifest["identity"]["partSessionId"], *expected_id);
        assert_eq!(manifest["receipt"]["scoredTrialCount"], 3);
        assert_eq!(manifest["timingQualification"], "unqualified");
    }
    eprintln!("software instruction/group evidence: {}", root.display());
    let retained: Vec<_> = [1, 2]
        .into_iter()
        .flat_map(|part| {
            fs::read_dir(root.join(format!("part_{part:02}")))
                .unwrap()
                .map(|entry| entry.unwrap().path())
                .filter(|path| {
                    path.file_name()
                        .unwrap()
                        .to_string_lossy()
                        .starts_with("native_")
                })
        })
        .map(|path| {
            let bytes = fs::read(&path).unwrap();
            (path, bytes)
        })
        .collect();
    let reverified =
        pps_session_package::verify_prepared_group(&root.join("session_group_manifest.json"))
            .unwrap();
    tauri::async_runtime::block_on(runtime.adopt_verified_group_async(reverified)).unwrap();
    let selected = runtime.snapshot().unwrap();
    assert_eq!(selected.run.phase, RunnerPhase::Prepared);
    assert!(!selected.safety.local_armed && !selected.run.complete);
    assert_eq!(
        tauri::async_runtime::block_on(runtime.native_group_status())
            .unwrap()
            .completed_parts,
        0
    );
    for (path, bytes) in retained {
        assert_eq!(fs::read(path).unwrap(), bytes);
    }
}

#[test]
fn stopping_instruction_gate_leaves_both_parts_incomplete_and_silences_callback() {
    let (root, group) = instruction_group_fixture();
    let control = Arc::new(FakeControl::default());
    control.enable_software_callback();
    let runtime = AppRuntime::with_native_output(fake_coordinator(&control));
    tauri::async_runtime::block_on(runtime.adopt_verified_group_async(group)).unwrap();
    runtime.dispatch_local(Action::SetupSubmit,serde_json::json!({"participant_code":"P001","age":30,"handedness":"right","gender":"other","name_sharing_opt_in":false,"part_labels":{"1":"Pre","2":"Post"}})).unwrap();
    run_software_part(&runtime, &control, 1, true);
    assert_eq!(
        runtime.snapshot().unwrap().run.phase,
        RunnerPhase::Interrupted
    );
    assert!(!runtime.snapshot().unwrap().run.complete);
    let progress = tauri::async_runtime::block_on(runtime.native_group_status()).unwrap();
    assert_eq!(progress.completed_parts, 0);
    assert!(!progress.experiment_complete);
    assert!(tauri::async_runtime::block_on(
        runtime.advance_verified_group_part_async(progress.revision)
    )
    .is_err());
    for part in [1, 2] {
        assert!(fs::read_dir(root.join(format!("part_{part:02}")))
            .unwrap()
            .all(|entry| !entry
                .unwrap()
                .file_name()
                .to_string_lossy()
                .ends_with(".results.json")));
    }
}

#[test]
fn changed_instruction_bytes_cannot_enter_native_audio_cache() {
    let (_root, group) = instruction_group_fixture();
    let path = group.parts()[0].instructions()[0].wav().path().to_owned();
    let runtime =
        AppRuntime::with_native_output(fake_coordinator(&Arc::new(FakeControl::default())));
    tauri::async_runtime::block_on(runtime.adopt_verified_group_async(group)).unwrap();
    compile_current_execution(&runtime);
    let (_guard, source) = begin_audio_decode(&runtime, 0);
    let mut bytes = fs::read(&path).unwrap();
    let last = bytes.len() - 1;
    bytes[last] ^= 1;
    fs::write(&path, bytes).unwrap();
    assert!(prepare_verified_audio(source).is_err());
    assert!(!runtime
        .snapshot()
        .unwrap()
        .allowed_actions
        .contains(&Action::TargetArm));
    assert_eq!(
        tauri::async_runtime::block_on(runtime.native_group_status())
            .unwrap()
            .completed_parts,
        0
    );
}

fn wait_group_publication(runtime: &AppRuntime) -> crate::execution_owner::NativeGroupStatus {
    let deadline = std::time::Instant::now() + Duration::from_secs(8);
    loop {
        let status = tauri::async_runtime::block_on(runtime.native_group_status()).unwrap();
        if matches!(status.publication_status, "complete" | "failed") {
            return status;
        }
        assert!(
            std::time::Instant::now() < deadline,
            "group publication timeout: {status:?}"
        );
        std::thread::sleep(Duration::from_millis(2));
    }
}

fn group_test_runtime(
    group: pps_session_package::VerifiedPreparedGroup,
) -> (AppRuntime, Arc<FakeControl>) {
    let control = Arc::new(FakeControl::default());
    control.enable_software_callback();
    let runtime = AppRuntime::with_native_output(fake_coordinator(&control));
    tauri::async_runtime::block_on(runtime.adopt_verified_group_async(group)).unwrap();
    runtime.dispatch_local(Action::SetupSubmit,serde_json::json!({"participant_code":"P001","age":30,"handedness":"right","gender":"other","name_sharing_opt_in":false,"part_labels":{"1":"Pre","2":"Post"}})).unwrap();
    (runtime, control)
}
fn run_both_software_parts(runtime: &AppRuntime, control: &FakeControl) {
    run_software_part(runtime, control, 1, false);
    tauri::async_runtime::block_on(
        runtime.advance_verified_group_part_async(runtime.snapshot().unwrap().revision),
    )
    .unwrap();
    run_software_part(runtime, control, 2, false);
}

#[test]
fn durable_group_publication_collision_preserves_files_and_never_claims_complete() {
    let (root, group) = instruction_group_fixture();
    let (runtime, control) = group_test_runtime(group);
    let status = tauri::async_runtime::block_on(runtime.native_group_status()).unwrap();
    let attempt = status.group_attempt_id.unwrap();
    let final_path = root.join(format!("native_group_{attempt}.results.json"));
    fs::write(&final_path, b"pre-existing sentinel").unwrap();
    run_both_software_parts(&runtime, &control);
    let status = wait_group_publication(&runtime);
    assert_eq!(status.completed_parts, 2);
    assert_eq!(status.publication_status, "failed");
    assert!(!status.experiment_complete);
    assert!(!runtime.snapshot().unwrap().run.complete);
    assert_eq!(fs::read(final_path).unwrap(), b"pre-existing sentinel");
}

#[test]
fn durable_group_reselection_cancels_pending_commit_and_never_adopts_old_parts() {
    use crate::event_journal::group_results::pause_publication_for_test;
    let (root, group) = instruction_group_fixture();
    let (runtime, control) = group_test_runtime(group.clone());
    let old_attempt = tauri::async_runtime::block_on(runtime.native_group_status())
        .unwrap()
        .group_attempt_id
        .unwrap();
    let reached = pause_publication_for_test(&old_attempt);
    run_both_software_parts(&runtime, &control);
    let deadline = std::time::Instant::now() + Duration::from_secs(8);
    while !reached.load(Ordering::Acquire) {
        assert!(std::time::Instant::now() < deadline);
        std::thread::sleep(Duration::from_millis(2));
    }
    assert!(!runtime.snapshot().unwrap().run.complete);
    assert!(!root
        .join(format!("native_group_{old_attempt}.results.json"))
        .exists());
    tauri::async_runtime::block_on(runtime.adopt_verified_group_async(group)).unwrap();
    let selected = tauri::async_runtime::block_on(runtime.native_group_status()).unwrap();
    assert_ne!(
        selected.group_attempt_id.as_deref(),
        Some(old_attempt.as_str())
    );
    assert_eq!(selected.completed_parts, 0);
    assert!(!selected.experiment_complete);
    assert!(tauri::async_runtime::block_on(
        runtime.advance_verified_group_part_async(selected.revision)
    )
    .is_err());
    run_both_software_parts(&runtime, &control);
    let status = wait_group_publication(&runtime);
    assert!(status.experiment_complete);
    assert!(!root
        .join(format!("native_group_{old_attempt}.results.json"))
        .exists());
}

#[test]
fn durable_group_verifier_rejects_cross_attempt_part_substitution() {
    use crate::event_journal::group_results::{
        verify_published_group_result, verify_published_group_result_with_budget, GroupResultError,
    };
    let (root, group) = instruction_group_fixture();
    let (runtime, control) = group_test_runtime(group.clone());
    run_both_software_parts(&runtime, &control);
    let first = wait_group_publication(&runtime);
    assert!(first.experiment_complete);
    let first_path = root.join(format!(
        "native_group_{}.results.json",
        first.group_attempt_id.unwrap()
    ));
    let first_bytes = fs::read(&first_path).unwrap();
    let first_value: Value = serde_json::from_slice(&first_bytes).unwrap();
    tauri::async_runtime::block_on(runtime.adopt_verified_group_async(group.clone())).unwrap();
    run_both_software_parts(&runtime, &control);
    let second = wait_group_publication(&runtime);
    assert!(second.experiment_complete);
    let second_path = root.join(format!(
        "native_group_{}.results.json",
        second.group_attempt_id.unwrap()
    ));
    let second_bytes = fs::read(&second_path).unwrap();
    let mut mixed: Value = serde_json::from_slice(&second_bytes).unwrap();
    let receipt = verify_published_group_result(&group, &second_path).unwrap();
    assert_eq!(receipt.scored_trial_count, 4);
    assert_eq!(receipt.dataset_row_count, 4);
    let mut budget = 128 * 1024 * 1024;
    verify_published_group_result_with_budget(&group, &second_path, &mut budget).unwrap();
    let consumed = 128 * 1024 * 1024 - budget;
    assert!(consumed > second_bytes.len());
    let mut exact_budget = consumed;
    verify_published_group_result_with_budget(&group, &second_path, &mut exact_budget).unwrap();
    assert_eq!(exact_budget, 0);
    assert!(matches!(
        verify_published_group_result_with_budget(&group, &second_path, &mut exact_budget),
        Err(GroupResultError::BudgetExceeded)
    ));
    let mut short_budget = consumed - 1;
    assert!(matches!(
        verify_published_group_result_with_budget(&group, &second_path, &mut short_budget),
        Err(GroupResultError::BudgetExceeded)
    ));
    mixed["parts"][0] = first_value["parts"][0].clone();
    fs::write(&second_path, serde_json::to_vec(&mixed).unwrap()).unwrap();
    assert!(verify_published_group_result(&group, &second_path).is_err());
    fs::write(&second_path, second_bytes).unwrap();
    assert_eq!(fs::read(first_path).unwrap(), first_bytes);
}

#[test]
fn condition_transition_without_recording_requires_button_and_no_extra_pcm() {
    for (after_each_audio, stop_at_gate) in [(false, false), (true, false), (false, true)] {
        let (root, package) = verified_audio_package("P001", 2);
        let manifest_path = package.manifest_path().to_owned();
        let mut manifest: Value =
            serde_json::from_slice(&fs::read(&manifest_path).unwrap()).unwrap();
        manifest["blocks"][0]["metadata"]["phase_index"] = serde_json::json!(1);
        manifest["blocks"][1]["metadata"]["phase_index"] = serde_json::json!(2);
        manifest["blocks"][1]["metadata"]["part_number"] = serde_json::json!(2);
        if after_each_audio {
            use sha2::{Digest, Sha256};
            let bytes = pcm16_wav_bytes(48_000, 80, 500);
            fs::write(root.join("after-block.wav"), &bytes).unwrap();
            manifest["instruction_profile"] = serde_json::json!({"schema":"pps-run-instructions.v1","slots":[{"slot":"after_each_block","enabled":true,"label":"After block","path":"after-block.wav","sha256":format!("{:x}",Sha256::digest(bytes)),"duration_s":80.0/48000.0,"channels":2,"sample_rate":48000,"continue_mode":"click","delay_s":0.0,"button_label":"Continue"}]});
        }
        fs::write(&manifest_path, serde_json::to_vec(&manifest).unwrap()).unwrap();
        let package = verify_prepared_session(VerificationRequest::new(&manifest_path)).unwrap();
        let control = Arc::new(FakeControl::default());
        control.enable_software_callback();
        let runtime = AppRuntime::with_native_output(fake_coordinator(&control));
        runtime.adopt_verified_session(package).unwrap();
        runtime.dispatch_local(Action::SetupSubmit,serde_json::json!({"participant_code":"P001","age":30,"handedness":"right","gender":"other","name_sharing_opt_in":false,"part_labels":{"1":"Pre","2":"Post"}})).unwrap();
        let gates = run_software_part(&runtime, &control, 1, stop_at_gate);
        if stop_at_gate {
            assert!(!runtime.snapshot().unwrap().run.complete);
            assert!(!fs::read_dir(&root).unwrap().any(|entry| entry
                .unwrap()
                .path()
                .to_string_lossy()
                .ends_with(".results.json")));
            continue;
        }
        assert_eq!(gates, vec![serde_json::json!({"mode":"continue-button"})]);
        assert!(runtime.snapshot().unwrap().run.complete);
        let result_path = fs::read_dir(&root)
            .unwrap()
            .map(|entry| entry.unwrap().path())
            .find(|path| path.to_string_lossy().ends_with(".results.json"))
            .unwrap();
        let result: Value = serde_json::from_slice(&fs::read(result_path).unwrap()).unwrap();
        assert_eq!(result["receipt"]["scoredTrialCount"], 2);
        let events = fs::read_to_string(root.join(result["eventsFile"].as_str().unwrap())).unwrap();
        assert!(events.contains("condition-transition-without-audio"));
        assert_eq!(
            events.matches("instruction.sample-zero").count(),
            if after_each_audio { 2 } else { 0 }
        );
    }
}
