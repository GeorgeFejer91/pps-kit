// Included only in service::tests. One complete production browser capture is
// consumed per process; the caller owns its fresh temporary output directory.
// The actual host owns authorization, generation, review and preparation.

fn preset_json(path: &Path) -> Result<Value> {
    serde_json::from_slice(&read_bounded(path, MAX_JSON as u64)?).map_err(|error| error.to_string())
}

fn preset_job(shared: &Shared, id: &str) -> Result<Value> {
    let owner = shared.lock().map_err(|_| "host_unavailable")?;
    let job = owner.jobs.snapshot(id).ok_or("job_missing")?;
    if job.status != "succeeded" {
        return Err(format!(
            "{}: {}",
            job.status,
            job.result.unwrap_or(Value::Null)
        ));
    }
    Ok(job.result.unwrap_or(Value::Null))
}

fn preset_expected_empty_plan_guard(case: &Value, rows: usize, error: &str) -> bool {
    case["configuration_eligible"] == false
        && rows == 0
        && error == "native_complete_block_plan_required"
}

fn preset_compare_complete_rows(before: &Value, after: &Value) -> Result<()> {
    let original = before["blocks"].as_array().ok_or("capture_blocks")?;
    let enriched = after["blocks"].as_array().ok_or("review_blocks")?;
    if original.len() != enriched.len() {
        return Err("native_source_block_count_changed".into());
    }
    for (old, new) in original.iter().zip(enriched) {
        let old_rows = old["preview_rows"].as_array().ok_or("capture_rows")?;
        let new_rows = new["preview_rows"].as_array().ok_or("review_rows")?;
        if old_rows.len() != new_rows.len() {
            return Err("native_source_row_count_changed".into());
        }
        for (old, new) in old_rows.iter().zip(new_rows) {
            for field in [
                "block_index",
                "block_trial_index",
                "trial_pool_index",
                "row_label",
                "family",
                "soa_ms",
                "sequence_variant_key",
                "source_file_name",
            ] {
                if old[field] != new[field] {
                    return Err(format!("native_saved_order_changed: {field}"));
                }
            }
            // Browser durations are rounded to milliseconds. A one-millisecond
            // tolerance accommodates that representation, not a missing segment.
            for field in ["duration_s", "looming_segment_onset_s", "tactile_onset_s"] {
                if let Some(expected) = old[field].as_f64() {
                    let actual = new[field]
                        .as_f64()
                        .ok_or_else(|| format!("native_timing_missing: {field}"))?;
                    if (actual - expected).abs() > 0.001 {
                        return Err(format!("captured_pcm_timing_mismatch: pool={} {field}: captured={expected}, actual={actual}", old["trial_pool_index"]));
                    }
                }
            }
        }
    }
    Ok(())
}

fn preset_prepare_case(
    captured: Value,
    case: &Value,
    resources: PathBuf,
    output: &Path,
    evidence: &mut Value,
) -> Result<()> {
    let original_plan = captured["block_csv_preview"].clone();
    let variants = captured["variants"].clone();
    let source_blocks = original_plan["blocks"]
        .as_array()
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    let source_rows: usize = source_blocks
        .iter()
        .map(|b| b["preview_rows"].as_array().map_or(0, Vec::len))
        .sum();
    evidence["source_trial_count"] = json!(source_rows);
    evidence["source_block_rows"] = json!(source_blocks.iter().map(|b| json!({"index":b["block_index"],"label":b["block_label"],"rows":b["preview_rows"].as_array().map_or(0,Vec::len)})).collect::<Vec<_>>());
    evidence["block_count"] = json!(source_blocks.len());
    if evidence["source_block_rows"] != case["source_block_rows"]
        || case["source_trial_count"].as_u64() != Some(source_rows as u64)
        || (case["configuration_eligible"] == true
            && captured["trial_pool_bake"]["total_count"].as_u64() != Some(source_rows as u64))
    {
        return Err("capture_full_pool_count_mismatch".into());
    }
    evidence["captured_pool_trial_count"] = captured["trial_pool_bake"]["total_count"].clone();
    let renderer = std::env::var_os("PPS_DESIGNER_RENDERER")
        .map(PathBuf::from)
        .unwrap_or_default();
    let shared = Arc::new(Mutex::new(DesignerService::open(
        output.join("host"),
        resources,
        renderer,
    )?));
    let mut snapshot = captured;
    let needs_baselines = source_blocks
        .iter()
        .flat_map(|b| b["preview_rows"].as_array().into_iter().flatten())
        .any(|row| row["family"] == "baseline" && row["baseline_mode"] == "stationary_burst");
    if needs_baselines {
        if std::env::var_os("PPS_PRESET_GENERATE_BASELINES").as_deref()
            != Some(std::ffi::OsStr::new("1"))
        {
            return Err("explicit_native_baseline_generation_opt_in_required".into());
        }
        let renderer_path = shared
            .lock()
            .map_err(|_| "host_unavailable")?
            .renderer
            .clone();
        let renderer_sha = sha(&read_bounded(&renderer_path, 64 * 1024 * 1024)?);
        if std::env::var("PPS_DESIGNER_RENDERER_SHA256")
            .ok()
            .as_deref()
            != Some(&renderer_sha)
        {
            return Err("explicit_verified_renderer_sha256_required".into());
        }
        evidence["renderer_sha256"] = json!(renderer_sha);
        let labels: std::collections::BTreeSet<String> = variants
            .as_array()
            .ok_or("capture_variants")?
            .iter()
            .flat_map(|v| v["choices"].as_array().into_iter().flatten())
            .filter_map(|c| c["label"].as_str())
            .filter(|label| {
                snapshot["design"]["noises"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .any(|n| n["label"] == *label)
            })
            .map(str::to_owned)
            .collect();
        snapshot["custom_workflow"]["is_custom"] = json!(true);
        snapshot["custom_workflow"]["is_finalized"] = json!(false);
        evidence["generation"] = json!({"status":"running","source_algorithm":pps_designer_core::SOURCE_ALGORITHM,"legacy_numpy_seed_compatible":false,"customized_controls":true,"sources":[]});
        for label in labels {
            let (job, work) = {
                let mut owner = shared.lock().map_err(|_| "host_unavailable")?;
                let revision = owner.jobs.revision();
                owner.begin_baseline(
                    revision,
                    snapshot,
                    &label,
                    &pps_designer_core::baseline::BaselineGenerationOptIn {
                        source_algorithm: pps_designer_core::SOURCE_ALGORITHM.into(),
                        accept_non_legacy_source_algorithm: true,
                    },
                )?
            };
            execute(shared.clone(), work);
            let generated = preset_job(&shared, &job.job_id)?;
            evidence["generation"]["sources"]
                .as_array_mut()
                .unwrap()
                .push(generated);
            snapshot =
                shared.lock().map_err(|_| "host_unavailable")?.snapshot()["snapshot"].clone();
            // Re-review the same complete captured row order after controls are
            // generated. No previous browser acceptance authorizes native work.
            snapshot["block_csv_preview"] = original_plan.clone();
        }
        evidence["generation"]["status"] = json!("generated");
    }
    let revision = shared
        .lock()
        .map_err(|_| "host_unavailable")?
        .jobs
        .revision();
    let review = shared
        .lock()
        .map_err(|_| "host_unavailable")?
        .begin_review(revision, snapshot, variants);
    let (job, work) = match review {
        Ok(value) => value,
        Err(error) if preset_expected_empty_plan_guard(case, source_rows, &error) => {
            evidence["status"] = json!("blocked");
            evidence["native_guard_error"] = json!(error);
            return Ok(());
        }
        Err(error) => return Err(error),
    };
    crate::assembly_host::review(shared.clone(), work);
    preset_job(&shared, &job.job_id)?;
    if case["configuration_eligible"] != true {
        return Err("blocked_capture_unexpectedly_reviewed".into());
    }
    let projection = shared.lock().map_err(|_| "host_unavailable")?.snapshot()["snapshot"].clone();
    preset_compare_complete_rows(&original_plan, &projection["block_csv_preview"])?;
    let selected: Vec<Value> = projection["run_sequence_setup"]["csv_rows"]
        .as_array()
        .ok_or("native_order_rows")?
        .iter()
        .filter(|row| row["participant_index"] == 1)
        .cloned()
        .collect();
    if selected.is_empty() {
        return Err("native_participant_order_empty".into());
    }
    evidence["participant_occurrences"] = json!(selected);
    evidence["review_hashes"] = projection["native_execution_review"]["hashes"].clone();
    evidence["full_plan_preserved"] = json!(true);
    fs::write(
        output.join("reviewed-snapshot.json"),
        serde_json::to_vec_pretty(&projection).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    if std::env::var_os("PPS_PRESET_PREFLIGHT_ONLY").as_deref() == Some(std::ffi::OsStr::new("1")) {
        evidence["status"] = json!("reviewed");
        return Ok(());
    }
    let toolkit_iti = projection["block_csv_preview"]["blocks"]
        .as_array()
        .into_iter()
        .flatten()
        .flat_map(|b| b["preview_rows"].as_array().into_iter().flatten())
        .any(|row| row["native_iti_materialization_policy"].is_string());
    if toolkit_iti {
        if std::env::var_os("PPS_PRESET_RESOLVE_ITI_RANGES").as_deref()
            != Some(std::ffi::OsStr::new("1"))
        {
            return Err("explicit_toolkit_iti_resolution_acceptance_required".into());
        }
        evidence["toolkit_iti_resolution"] = json!({"accepted_for_software_audit":true,"source_distribution_reported":false,"source_anchor_reported":false,"legacy_compatible":false});
    }
    let (job, work) = {
        let mut owner = shared.lock().map_err(|_| "host_unavailable")?;
        owner.accept_review(revision, &evidence["review_hashes"])?;
        owner.begin_prepare(
            revision,
            1,
            "synthetic_preset_audit".into(),
            output.join("prepared"),
        )?
    };
    crate::assembly_host::prepare(shared.clone(), work);
    let prepared = preset_job(&shared, &job.job_id)?;
    let directory = shared
        .lock()
        .map_err(|_| "host_unavailable")?
        .prepared_directory
        .clone()
        .ok_or("prepared_directory_missing")?;
    let handoff = directory.join(
        prepared["handoff_file"]
            .as_str()
            .ok_or("handoff_file_missing")?,
    );
    let parts = if prepared["part_count"] == 2 {
        pps_session_package::verify_prepared_group(&handoff)
            .map_err(|e| e.to_string())?
            .parts()
            .to_vec()
    } else {
        vec![pps_session_package::verify_prepared_session(
            pps_session_package::VerificationRequest::new(&handoff),
        )
        .map_err(|e| e.to_string())?]
    };
    let mut observed = Vec::new();
    let mut receipts = Vec::new();
    for part in &parts {
        let mut block_receipts = Vec::new();
        for (block, summary) in part.blocks().iter().zip(&part.summary().blocks) {
            let metadata = block.metadata();
            let source = metadata
                .get("source_block_index")
                .and_then(Value::as_u64)
                .ok_or("source_block_index_missing")?;
            let expected = selected.get(observed.len()).ok_or("extra_native_block")?;
            if expected["source_block_index"] != source
                || expected["phase"] != metadata["phase"]
                || source_blocks[(source - 1) as usize]["trial_count"] != summary.trial_count
            {
                return Err("prepared_part_order_or_count_changed".into());
            }
            let wav = hound::WavReader::open(block.wav_path()).map_err(|e| e.to_string())?;
            if metadata["frames"] != wav.duration()
                || metadata["sample_rate_hz"] != wav.spec().sample_rate
            {
                return Err("prepared_pcm_header_mismatch".into());
            }
            observed.push(expected.clone());
            block_receipts.push(json!({"source_block_index":source,"phase":metadata["phase"],"trial_count":summary.trial_count,"frames":wav.duration(),"sample_rate_hz":wav.spec().sample_rate,"wav_sha256":block.block_wav().sha256(),"csv_sha256":block.manifest_sha256()}));
        }
        receipts.push(json!({"manifest_path":part.manifest_path(),"manifest_sha256":part.manifest_sha256(),"part_number":part.summary().part_number,"part_session_id":part.summary().part_session_id,"block_count":part.blocks().len(),"trial_count":part.summary().blocks.iter().map(|b|b.trial_count).sum::<i64>(),"instruction_slots":part.instructions().len(),"blocks":block_receipts}));
    }
    if observed != selected {
        return Err("prepared_participant_occurrences_changed".into());
    }
    evidence["status"] = json!("prepared");
    evidence["handoff_manifest_path"] = json!(handoff);
    evidence["handoff_sha256"] = json!(sha(&read_bounded(&handoff, MAX_JSON as u64)?));
    evidence["parts"] = json!(receipts);
    evidence["all_part_packages_verified"] = json!(true);
    Ok(())
}

#[test]
#[ignore = "requires a hash-bound complete browser capture, fresh temporary output and optional actual renderer"]
fn full_archived_preset_native_host_preparation() {
    let capture =
        PathBuf::from(std::env::var_os("PPS_PRESET_CAPTURE").expect("PPS_PRESET_CAPTURE"));
    let output = PathBuf::from(
        std::env::var_os("PPS_PRESET_OUTPUT").expect("PPS_PRESET_OUTPUT: fresh empty directory"),
    );
    assert!(
        output.is_dir() && fs::read_dir(&output).unwrap().next().is_none(),
        "caller must own a fresh empty output directory"
    );
    let resources = std::env::var_os("PPS_PRESET_RESOURCE_ROOT")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../packages/pps-resources")
        });
    let report = preset_json(&capture.parent().unwrap().join("capture-report.json")).unwrap();
    let filename = capture.file_name().unwrap().to_str().unwrap();
    let matches: Vec<_> = report["cases"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|case| case["capture_file"] == filename)
        .collect();
    assert_eq!(matches.len(), 1, "exactly one capture identity required");
    let case = matches[0];
    let id = case["template_id"].as_str().unwrap();
    assert!(id.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_'));
    let bytes = read_bounded(&capture, MAX_JSON as u64).unwrap();
    assert_eq!(sha(&bytes), case["capture_sha256"]);
    assert_eq!(
        sha(&read_bounded(
            &resources.join("study_templates").join(format!("{id}.json")),
            MAX_JSON as u64
        )
        .unwrap()),
        case["template_sha256"]
    );
    assert_eq!(
        sha(&read_bounded(
            &resources.join("assets/preloads/preload_inventory.json"),
            MAX_JSON as u64
        )
        .unwrap()),
        report["input_hashes"]["packages/pps-resources/assets/preloads/preload_inventory.json"],
        "capture and native resources must use the same preload inventory"
    );
    let captured: Value = serde_json::from_slice(&bytes).unwrap();
    assert_eq!(captured["design"]["study_profile_id"], id);
    let mut evidence = json!({"schema":"pps-native-preset-preparation.v1","template_id":id,"template_sha256":case["template_sha256"],"capture_sha256":case["capture_sha256"],"capture_input_hashes":report["input_hashes"],"status":"failed","participant_index":1,"full_plan_preserved":false,"all_part_packages_verified":false,"all_block_schedules_compiled":false,"generation":{"status":"premade_assets_reused"},"execution":{"status":"not_run"},"physical_timing_qualified":false,"replication_qualified":false});
    let outcome = preset_prepare_case(captured, case, resources, &output, &mut evidence);
    if let Err(error) = &outcome {
        evidence["error"] = json!(error);
    }
    let mut file = fs::OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(output.join("native-preparation.json"))
        .unwrap();
    file.write_all(&serde_json::to_vec_pretty(&evidence).unwrap())
        .unwrap();
    file.sync_all().unwrap();
    assert!(outcome.is_ok(), "native case failed: {}", evidence["error"]);
}

#[test]
fn complete_preset_comparison_rejects_changed_order_and_verified_duration() {
    let original = json!({"blocks":[{"preview_rows":[{"block_index":1,"block_trial_index":1,"trial_pool_index":9,"row_label":"full","family":"audio_tactile","soa_ms":200,"sequence_variant_key":"source","source_file_name":"source.wav","duration_s":5.0,"looming_segment_onset_s":1.0,"tactile_onset_s":1.2}]}]});
    assert!(preset_compare_complete_rows(&original, &original).is_ok());
    let mut changed = original.clone();
    changed["blocks"][0]["preview_rows"][0]["trial_pool_index"] = json!(8);
    assert!(preset_compare_complete_rows(&original, &changed)
        .unwrap_err()
        .contains("order_changed"));
    changed = original.clone();
    changed["blocks"][0]["preview_rows"][0]["duration_s"] = json!(6.0);
    assert!(preset_compare_complete_rows(&original, &changed)
        .unwrap_err()
        .contains("pcm_timing_mismatch"));
    changed = original.clone();
    changed["blocks"][0]["preview_rows"] = json!([]);
    assert!(preset_compare_complete_rows(&original, &changed)
        .unwrap_err()
        .contains("row_count_changed"));
}

#[test]
fn empty_preset_plan_guard_precedes_assets_and_does_not_classify_unrelated_errors() {
    let case = json!({"configuration_eligible":false});
    assert!(preset_expected_empty_plan_guard(
        &case,
        0,
        "native_complete_block_plan_required"
    ));
    for error in [
        "asset_hash_mismatch",
        "storage_unavailable",
        "invalid_snapshot",
        "ResourceLimit",
    ] {
        assert!(!preset_expected_empty_plan_guard(&case, 0, error));
    }
    assert!(!preset_expected_empty_plan_guard(
        &case,
        1,
        "native_complete_block_plan_required"
    ));
    let root = std::env::temp_dir().join(format!(
        "pps-empty-plan-{}-{}",
        std::process::id(),
        SEQUENCE.fetch_add(1, Ordering::Relaxed)
    ));
    fs::create_dir(&root).unwrap();
    let _cleanup = ImportDirectory(Some(root.clone()));
    let mut owner = DesignerService::open(root, PathBuf::new(), PathBuf::new()).unwrap();
    let result = owner.begin_review(0, json!({"design":{"noises":[{"label":"missing","prebaked_path":"unavailable.wav"}]},"block_csv_preview":{}}), json!([{"choices":[{"kind":"audio","label":"missing"}]}]));
    assert_eq!(result.err().unwrap(), "native_complete_block_plan_required");
    assert!(owner.jobs.snapshot("1").is_none());
}
