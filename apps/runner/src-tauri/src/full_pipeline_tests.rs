// Included in runtime::tests. This driver replaces only the physical device
// and observation clock. The immutable PCM, scheduler, actor, input ingress,
// continuation policy, journal and transactional result owners are production.
// An external full profile is never shortened to make this test finish.

fn software_frame_ns(frames: u64, rate: u32) -> u64 {
    u64::try_from(u128::from(frames) * 1_000_000_000 / u128::from(rate)).unwrap()
}

fn software_result_files(
    session: &VerifiedPreparedSession,
) -> std::collections::BTreeSet<std::path::PathBuf> {
    fs::read_dir(session.session_dir())
        .unwrap()
        .map(|entry| entry.unwrap().path())
        .filter(|path| {
            path.file_name()
                .unwrap()
                .to_string_lossy()
                .ends_with(".results.json")
        })
        .collect()
}

fn software_run_complete_part(
    runtime: &AppRuntime,
    control: &FakeControl,
    clock: &crate::execution_owner::SoftwareTestClock,
    session: &VerifiedPreparedSession,
) -> Value {
    use pps_runner_audio::RenderState;
    use std::io::{BufRead, BufReader};
    let before = software_result_files(session);
    compile_current_execution(runtime);
    assert_eq!(
        runtime.0.authority.test_view().compiled_schedule_count,
        Some(session.blocks().len())
    );
    let stages = crate::execution_owner::instruction::stages(session).unwrap();
    let mut media_evidence = Vec::new();
    let mut expected_boundaries = Vec::<(String, u64)>::new();
    let mut expected_boundary_times = Vec::new();
    let mut response_count = 0;
    let mut gate_count = 0;
    for stage in &stages {
        let boundary_start = expected_boundaries.len();
        let preparation =
            tauri::async_runtime::block_on(runtime.begin_next_prepared_audio_preparation_async())
                .unwrap();
        let (guard, source) = match preparation {
            PreparedAudioPreparation::Decode { _guard, source } => (_guard, source),
            _ => panic!("each saved occurrence must be prepared exactly once"),
        };
        let candidate = prepare_verified_audio(source).unwrap();
        assert_eq!(candidate.source_receipt().stage(), *stage);
        let instruction = candidate.source_receipt().instruction();
        let is_instruction = instruction.is_some();
        let delay_ns = instruction.map(|item| item.delay_ns()).unwrap_or(0);
        let plan = candidate.shared_playback_plan();
        let frames = plan.media().frames();
        let channels = plan.media().channels();
        let rate = plan.media().sample_rate_hz();
        assert_eq!(plan.gains(), pps_runner_audio::OutputGains::unity());
        expected_boundaries.push((
            if is_instruction {
                "instruction.sample-zero"
            } else {
                "audio_sample_zero"
            }
            .into(),
            0,
        ));
        let mut responses = Vec::new();
        if !is_instruction {
            for event in candidate
                .schedule()
                .events()
                .iter()
                .filter(|e| e.event_type != "audio_sample_zero" && e.sample_index >= 0)
            {
                expected_boundaries.push((event.event_type.clone(), event.sample_index as u64));
                // Deliberately synthetic tactile-detection responses. No
                // psychometric model or physical response claim is implied.
                let kind = format!(
                    "{} {}",
                    event.payload["family"], event.payload["trial_type"]
                )
                .to_lowercase();
                if event.event_type == "tactile_onset"
                    && !kind.contains("catch")
                    && !kind.contains("audio_only")
                {
                    responses.push(event.sample_index as u64 + u64::from(rate) * 3 / 10);
                }
            }
        }
        responses.sort_unstable();
        let response_end_frame = responses.last().copied().unwrap_or(frames).max(frames);
        expected_boundaries.push(("audio.final-frame-submitted".into(), frames));
        media_evidence.push(serde_json::json!({
            "stage_ordinal": stage.ordinal, "block_ordinal": stage.block_ordinal,
            "kind": if is_instruction { "instruction" } else { "block" },
            "wav_sha256": candidate.wav_receipt().unwrap().sha256(),
            "frames": frames, "sample_rate_hz": rate, "channels": channels,
            "scheduled_event_count": plan.scheduled_events().len(),
            "instruction_tactile_zero": is_instruction,
            "all_pcm_samples_compared": true
        }));
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
                .dispatch_local(
                    Action::PartStart,
                    serde_json::json!({"part_number":session.summary().part_number.unwrap_or(1)})
                )
                .unwrap()
                .status,
            AppliedStatus::Accepted
        );

        let origin = clock.now_ns();
        expected_boundary_times.extend(
            expected_boundaries[boundary_start..]
                .iter()
                .map(|(_, frame)| origin + software_frame_ns(*frame, rate)),
        );
        let deadline = std::time::Instant::now() + Duration::from_secs(300);
        let mut cursor = 0u64;
        let mut response_index = 0;
        let mut gate_handled = false;
        let mut output = vec![f32::NAN; 1024 * channels as usize];
        loop {
            assert!(
                std::time::Instant::now() < deadline,
                "full saved stage exceeded software worker deadline: {stage:?}"
            );
            while responses
                .get(response_index)
                .is_some_and(|frame| *frame <= cursor)
            {
                tauri::async_runtime::block_on(runtime.record_native_response(
                    NativeResponseRequest {
                        choice: String::new(),
                        x: Some(0.5),
                        y: Some(0.5),
                    },
                ))
                .unwrap();
                response_index += 1;
                response_count += 1;
            }
            if cursor < frames {
                let next_response = responses.get(response_index).copied().unwrap_or(frames);
                let count = 1024u64
                    .min(frames - cursor)
                    .min(next_response.saturating_sub(cursor).max(1));
                let buffer = &mut output[..count as usize * channels as usize];
                buffer.fill(f32::NAN);
                let status = control.render_software_callback_at(buffer, clock.observed());
                assert!(
                    status.fault.is_none() && !status.callback_retired,
                    "callback failed: {status:?}"
                );
                let consumed = status.submitted_frames.checked_sub(cursor).unwrap();
                assert!(
                    consumed == 0 || consumed == count,
                    "callback skipped saved PCM"
                );
                if consumed == 0 {
                    assert_eq!(status.state, RenderState::Prepared);
                    assert!(buffer.iter().all(|v| *v == 0.0));
                    runtime.snapshot().unwrap(); // drain durable intent before retry
                    std::thread::yield_now();
                    continue;
                }
                let begin = cursor as usize * channels as usize;
                let expected = &plan.media().interleaved_f32()[begin..begin + buffer.len()];
                assert_eq!(
                    buffer, expected,
                    "callback changed, omitted or reordered actual PCM"
                );
                assert!(buffer.iter().all(|v| v.is_finite() && v.abs() <= 1.0));
                if is_instruction {
                    assert_eq!(channels, 3);
                    assert!(buffer.chunks_exact(3).all(|frame| frame[2] == 0.0));
                    assert!(!runtime.snapshot().unwrap().run.participant_capture_ready);
                }
                cursor = status.submitted_frames;
                clock.advance_to(origin + software_frame_ns(cursor, rate));
            } else if let Some(next) = responses.get(response_index).copied() {
                cursor = next;
                clock.advance_to(origin + software_frame_ns(cursor, rate));
                continue;
            } else {
                let tail = if is_instruction {
                    1
                } else {
                    pps_runner_execution::RESPONSE_MAX_RT_NS + 1
                };
                clock.advance_to(
                    clock
                        .now_ns()
                        .max(origin + software_frame_ns(response_end_frame, rate) + tail),
                );
            }
            let snapshot = runtime.snapshot().unwrap(); // authority drains callback boundaries
                                                        // Synthetic time may run much faster than disk. Let the existing
                                                        // bounded file worker acknowledge this prefix before another
                                                        // callback; never enlarge its queues or suppress a write error.
            loop {
                let view = runtime.0.authority.test_view();
                assert!(!view.evidence_unavailable, "native evidence worker failed");
                if view.journal_durable_sequence.is_none() {
                    assert_eq!(
                        runtime.snapshot().unwrap().run.phase,
                        RunnerPhase::Completed
                    );
                    break;
                }
                if view.journal_durable_sequence == view.ledger_last_sequence {
                    break;
                }
                assert!(
                    std::time::Instant::now() < deadline,
                    "native journal did not acknowledge the callback prefix"
                );
                std::thread::yield_now();
            }
            assert!(
                !matches!(snapshot.run.phase, RunnerPhase::Interrupted),
                "native acquisition interrupted: {:?}",
                snapshot.run
            );
            if snapshot.run.phase == RunnerPhase::InstructionGate && !gate_handled {
                assert!(cursor >= frames && response_index == responses.len());
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
                let gate = snapshot.instruction_gate;
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
                        clock.advance_to(clock.now_ns() + delay_ns + 1);
                    }
                    mode => panic!("unsupported saved continuation: {mode}"),
                }
                gate_handled = true;
                gate_count += 1;
            }
            if matches!(
                snapshot.run.phase,
                RunnerPhase::Prepared | RunnerPhase::Completed
            ) {
                assert!(cursor >= frames && response_index == responses.len());
                break;
            }
            std::thread::yield_now();
        }
    }
    assert_eq!(
        runtime.snapshot().unwrap().run.phase,
        RunnerPhase::Completed
    );
    let after = software_result_files(session);
    let added: Vec<_> = after.difference(&before).cloned().collect();
    assert_eq!(
        added.len(),
        1,
        "one fresh native attempt, without replacing existing results"
    );
    let result: Value = serde_json::from_slice(&fs::read(&added[0]).unwrap()).unwrap();
    assert_eq!(
        result["receipt"]["packageManifestSha256"],
        session.manifest_sha256()
    );
    let expected_rows: i64 = session
        .summary()
        .blocks
        .iter()
        .map(|block| block.trial_count)
        .sum();
    assert_eq!(result["receipt"]["scoredTrialCount"], expected_rows);
    assert_eq!(result["timingQualification"], "unqualified");
    let event_path = session
        .session_dir()
        .join(result["eventsFile"].as_str().unwrap());
    assert!(fs::metadata(&event_path).unwrap().len() <= 128 * 1024 * 1024);
    let mut actual_boundaries = Vec::new();
    let boundary_types: std::collections::BTreeSet<_> = expected_boundaries
        .iter()
        .map(|(kind, _)| kind.as_str())
        .collect();
    let mut actual_boundary_times = Vec::new();
    let mut native_responses = 0;
    let mut scored_responses = Vec::new();
    for line in BufReader::new(fs::File::open(event_path).unwrap())
        .lines()
        .skip(1)
    {
        let event: Value = serde_json::from_str(&line.unwrap()).unwrap();
        if let Some(index) = event["payload"]["sourceSampleIndex"]
            .as_u64()
            .filter(|_| boundary_types.contains(event["eventType"].as_str().unwrap()))
        {
            actual_boundaries.push((event["eventType"].as_str().unwrap().to_owned(), index));
            actual_boundary_times.push(
                event["payload"]["estimatedEventHostMonotonicNs"]
                    .as_u64()
                    .unwrap(),
            );
        }
        if event["eventType"] == "response.observed" {
            native_responses += 1;
        }
        if event["eventType"] == "trial.scored" && event["payload"]["response_given"] == true {
            scored_responses.push(serde_json::json!({"outcome":event["payload"]["outcome"],"rt_ms":event["payload"]["rt_ms"]}));
        }
    }
    assert_eq!(
        actual_boundaries, expected_boundaries,
        "all saved sample boundaries must reach the durable event stream in order"
    );
    assert_eq!(native_responses, response_count);
    assert_eq!(actual_boundary_times.len(), expected_boundary_times.len());
    assert!(actual_boundary_times.iter().zip(&expected_boundary_times).all(|(actual, expected)|actual.abs_diff(*expected)<=1), "callback times must preserve the saved sample durations, within integer-nanosecond rounding");
    serde_json::json!({
        "package_manifest_sha256":session.manifest_sha256(), "result_manifest":added[0],
        "block_count":session.blocks().len(), "trial_count":expected_rows,
        "per_block_trial_counts":session.summary().blocks.iter().map(|b|b.trial_count).collect::<Vec<_>>(),
        "stage_count":stages.len(), "gate_count":gate_count, "media":media_evidence,
        "injected_tactile_responses":response_count, "native_response_events":native_responses,
        "scored_responses":scored_responses,
        "receipt":result["receipt"], "all_block_schedules_compiled":true,
        "all_saved_occurrences_preserved":true, "all_callback_boundaries_matched":true
    })
}

fn software_run_complete_package(path: &std::path::Path, expected_sha256: &str) -> Value {
    use sha2::{Digest, Sha256};
    assert!(fs::metadata(path).unwrap().len() <= 8 * 1024 * 1024);
    let bytes = fs::read(path).unwrap();
    assert_eq!(
        format!("{:x}", Sha256::digest(&bytes)),
        expected_sha256,
        "explicit immutable input identity"
    );
    let input: Value = serde_json::from_slice(&bytes).unwrap();
    let group = if input["schema"] == "pps-run-session-group.v1" {
        Some(pps_session_package::verify_prepared_group(path).unwrap())
    } else {
        None
    };
    let parts = if let Some(group) = &group {
        group.parts().to_vec()
    } else {
        vec![verify_prepared_session(VerificationRequest::new(path)).unwrap()]
    };
    let control = Arc::new(FakeControl::default());
    control.enable_software_callback();
    let runtime = AppRuntime::with_native_output(fake_coordinator(&control));
    let clock = runtime.0.authority.install_software_clock();
    let start_ns = clock.now_ns();
    if let Some(group) = &group {
        tauri::async_runtime::block_on(runtime.adopt_verified_group_async(group.clone())).unwrap();
    } else {
        tauri::async_runtime::block_on(runtime.adopt_verified_session_async(parts[0].clone()))
            .unwrap();
    }
    assert_eq!(runtime.dispatch_local(Action::SetupSubmit,serde_json::json!({"participant_code":parts[0].summary().participant_id,"age":30,"handedness":"right","gender":"other","name_sharing_opt_in":false,"part_labels":{"1":"Pre","2":"Post"}})).unwrap().status,AppliedStatus::Accepted);
    let mut evidence = Vec::new();
    for (index, part) in parts.iter().enumerate() {
        if index > 0 {
            let status = tauri::async_runtime::block_on(runtime.native_group_status()).unwrap();
            assert!(!status.experiment_complete);
            assert_eq!(status.completed_parts, index);
            tauri::async_runtime::block_on(
                runtime.advance_verified_group_part_async(status.revision),
            )
            .unwrap();
        }
        evidence.push(software_run_complete_part(&runtime, &control, &clock, part));
    }
    let group_result = group.as_ref().map(|group| {
        let progress = wait_group_publication(&runtime);
        assert!(progress.experiment_complete && progress.completed_parts == parts.len());
        let path = group.manifest().path().parent().unwrap().join(format!(
            "native_group_{}.results.json",
            progress.group_attempt_id.unwrap()
        ));
        let verified =
            crate::event_journal::group_results::verify_published_group_result(group, &path)
                .unwrap();
        assert_eq!(
            verified.scored_trial_count,
            evidence
                .iter()
                .map(|part| part["trial_count"].as_u64().unwrap())
                .sum::<u64>()
        );
        path
    });
    let report = serde_json::json!({
        "schema":"pps.native-full-package-software-execution.v1", "passed":true,
        "input_manifest_sha256":expected_sha256,"parts":evidence,"group_result_manifest":group_result,
        "clock_basis":"test-only-sample-paced-simulated-monotonic", "synthetic_responses":true,
        "simulated_elapsed_ns":clock.now_ns()-start_ns,"timing_qualification":"unqualified",
        "physical_device_used":false,"all_part_packages_verified":true,
        "scope":"complete-selected-prepared-package-not-a-template-inventory-claim"
    });
    let report_path = path
        .parent()
        .unwrap()
        .join(format!("native_software_{}.evidence.json", random_nonce()));
    use std::io::Write;
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&report_path)
        .unwrap();
    file.write_all(&serde_json::to_vec_pretty(&report).unwrap())
        .unwrap();
    file.sync_all().unwrap();
    eprintln!(
        "Full saved package software evidence: {}",
        report_path.display()
    );
    report
}

#[test]
fn full_package_software_clock_preserves_native_three_hundred_ms_response() {
    let (root, original) = verified_audio_package("SOFTWARE_FIXTURE", 1);
    fs::write(root.join("block-0.wav"), pcm16_wav_bytes(8000, 16_000, 500)).unwrap();
    fs::write(root.join("block-0.csv"), "Trial_Number,Trial_UID,Trial_Type,Family,Sample_Rate_Hz,Trial_Start_Sample,Looming_Onset_Sample,Tactile_Onset_Sample,Response_Window_Onset_Sample,Trial_End_Sample\n1,T1,Target,audiotactile,8000,0,0,4000,0,16000\n").unwrap();
    let mut manifest: Value =
        serde_json::from_slice(&fs::read(original.manifest_path()).unwrap()).unwrap();
    manifest["blocks"][0]["duration_s"] = serde_json::json!(2.0);
    manifest["blocks"][0]["metadata"]["sample_rate_hz"] = serde_json::json!(8000);
    fs::write(
        original.manifest_path(),
        serde_json::to_vec_pretty(&manifest).unwrap(),
    )
    .unwrap();
    let verified =
        verify_prepared_session(VerificationRequest::new(original.manifest_path())).unwrap();
    let report =
        software_run_complete_package(verified.manifest_path(), verified.manifest_sha256());
    assert_eq!(report["parts"][0]["injected_tactile_responses"], 1);
    assert_eq!(
        report["parts"][0]["scored_responses"],
        serde_json::json!([{"outcome":"Hit","rt_ms":"300.000"}])
    );
    assert!(report["simulated_elapsed_ns"].as_u64().unwrap() >= 2_000_000_000);
}

#[test]
fn full_package_software_driver_preserves_three_blocks_instructions_and_both_parts() {
    let (_root, group) = instruction_group_fixture_with_blocks(3);
    let report = software_run_complete_package(group.manifest().path(), group.manifest().sha256());
    assert_eq!(report["parts"].as_array().unwrap().len(), 2);
    for part in report["parts"].as_array().unwrap() {
        assert_eq!(part["block_count"], 3);
        assert_eq!(part["trial_count"], 3);
        assert!(part["gate_count"].as_u64().unwrap() > 0);
    }
}

#[test]
#[ignore = "requires PPS_NATIVE_FULL_MANIFEST and PPS_NATIVE_EXPECTED_SHA256; consumes every saved PCM frame and writes fresh synthetic results beside the immutable package"]
fn full_retained_profile_runs_all_saved_blocks_instructions_and_parts() {
    let path = std::path::PathBuf::from(
        std::env::var_os("PPS_NATIVE_FULL_MANIFEST")
            .expect("complete prepared session/group manifest"),
    );
    let sha =
        std::env::var("PPS_NATIVE_EXPECTED_SHA256").expect("explicit selected manifest SHA256");
    software_run_complete_package(&path, &sha);
}
