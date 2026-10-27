//! Native receipts join the existing browser block planner to immutable preparation.
use crate::{
    jobs::JobTicket,
    service::{self, DesignerService, Result, Shared},
};
use pps_designer_core::assembly::{
    self, AcceptedParticipantAssembly, AssemblyAssetRole, AssemblyPreview, RunOrderPreview,
    VerifiedAssemblyAsset,
};
use serde_json::{json, Value};
use std::{
    collections::BTreeMap,
    fs,
    path::PathBuf,
    sync::{atomic::Ordering, Arc},
};

pub struct Input {
    reference: String,
    path: PathBuf,
    sha256: String,
    role: AssemblyAssetRole,
}
pub struct Review {
    source: AssemblyPreview,
    order: RunOrderPreview,
    assets: Vec<VerifiedAssemblyAsset>,
    tactile: VerifiedAssemblyAsset,
}
pub struct Accepted {
    plan: AcceptedParticipantAssembly,
    assets: Vec<VerifiedAssemblyAsset>,
    tactile: VerifiedAssemblyAsset,
}
pub struct ReviewWork {
    ticket: JobTicket,
    snapshot: Value,
    variants: Value,
    inputs: Vec<Input>,
}
pub struct PrepareWork {
    ticket: JobTicket,
    accepted: Arc<Accepted>,
    directory: PathBuf,
    container: PathBuf,
    participant: usize,
    identity: String,
}

impl DesignerService {
    pub fn begin_review(
        &mut self,
        expected: u64,
        snapshot: Value,
        variants: Value,
    ) -> Result<(crate::jobs::JobSnapshot, ReviewWork)> {
        service::bound_snapshot(&snapshot)?;
        if serde_json::to_vec(&variants)
            .map_err(|_| "invalid_variants")?
            .len()
            > 8 * 1024 * 1024
        {
            return Err("variant_limit".into());
        }
        let mut references = BTreeMap::new();
        let design = &snapshot["design"];
        let selected: std::collections::BTreeSet<_> = variants
            .as_array()
            .into_iter()
            .flatten()
            .flat_map(|variant| variant["choices"].as_array().into_iter().flatten())
            .filter(|choice| choice["kind"] == "audio")
            .filter_map(|choice| choice["label"].as_str())
            .collect();
        for (collection, path, role) in [
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
                if !source["label"]
                    .as_str()
                    .is_some_and(|label| selected.contains(label))
                {
                    continue;
                }
                if let Some(reference) = source[path].as_str().filter(|s| !s.is_empty()) {
                    add_reference(&mut references, reference, role)?;
                }
                if let Some(reference) = source["native_stationary_baseline_asset"].as_str() {
                    add_reference(
                        &mut references,
                        reference,
                        AssemblyAssetRole::StationaryBaseline,
                    )?;
                }
            }
        }
        for slot in design["study_profile_reference_parameters"]["dashboard_run_setup"]
            ["instruction_profile"]["slots"]
            .as_array()
            .into_iter()
            .flatten()
        {
            if slot["enabled"] == true {
                let reference = slot["path"]
                    .as_str()
                    .filter(|s| !s.is_empty())
                    .ok_or("instruction_asset_required")?;
                add_reference(&mut references, reference, AssemblyAssetRole::Instruction)?;
            }
        }
        if references.len() > 128 {
            return Err("assembly_asset_limit".into());
        }
        let inputs = references
            .into_iter()
            .map(|(reference, role)| {
                let (path, sha256) = self.authorize_assembly_asset(&reference)?;
                Ok(Input {
                    reference,
                    path,
                    sha256,
                    role,
                })
            })
            .collect::<Result<Vec<_>>>()?;
        let ticket = self.jobs.start(expected).map_err(str::to_owned)?;
        self.review = None;
        self.accepted = None;
        self.prepared_directory = None;
        Ok((
            self.jobs
                .snapshot(&ticket.id.to_string())
                .ok_or("job_missing")?,
            ReviewWork {
                ticket,
                snapshot,
                variants,
                inputs,
            },
        ))
    }

    pub fn accept_review(&mut self, expected: u64, hashes: &Value) -> Result<Value> {
        if self.jobs.revision() != expected {
            return Err("revision_conflict".into());
        }
        let review = self.review.as_ref().ok_or("native_review_required")?;
        if hashes["design_sha256"] != review.source.design_sha256
            || hashes["assembly_preview_sha256"] != review.source.preview_sha256
            || hashes["run_order_sha256"] != review.order.run_order_sha256
        {
            return Err("review_hash_mismatch".into());
        }
        let review = self.review.take().ok_or("native_review_required")?;
        let plan = assembly::accept_participant_assembly(
            review.source,
            review.order,
            hashes["design_sha256"]
                .as_str()
                .ok_or("review_hash_required")?,
            hashes["assembly_preview_sha256"]
                .as_str()
                .ok_or("review_hash_required")?,
            hashes["run_order_sha256"]
                .as_str()
                .ok_or("review_hash_required")?,
            expected,
        )
        .map_err(|e| e.to_string())?;
        self.accepted = Some(Arc::new(Accepted {
            plan,
            assets: review.assets,
            tactile: review.tactile,
        }));
        Ok(json!({"accepted":true,"revision":expected}))
    }

    pub fn begin_prepare(
        &mut self,
        expected: u64,
        participant: usize,
        identity: String,
        directory: PathBuf,
    ) -> Result<(crate::jobs::JobSnapshot, PrepareWork)> {
        let accepted = self
            .accepted
            .as_ref()
            .ok_or("native_acceptance_required")?
            .clone();
        if accepted.plan.revision() != expected || expected != self.jobs.revision() {
            return Err("revision_conflict".into());
        }
        if participant == 0
            || participant > 100
            || identity.is_empty()
            || identity.len() > 80
            || !identity
                .bytes()
                .all(|c| c.is_ascii_alphanumeric() || c == b'_' || c == b'-')
        {
            return Err("participant_or_session_identity_invalid".into());
        }
        if directory.exists() {
            return Err("new_output_directory_required".into());
        }
        let ticket = self.jobs.start(expected).map_err(str::to_owned)?;
        // Claim this one new directory before giving the writer a child path.
        // Cleanup may remove only this successfully-created owner directory.
        if fs::create_dir(&directory).is_err() {
            self.jobs.finish(
                &ticket,
                "failed",
                "Output directory could not be created",
                None,
            );
            return Err("new_output_directory_required".into());
        }
        Ok((
            self.jobs
                .snapshot(&ticket.id.to_string())
                .ok_or("job_missing")?,
            PrepareWork {
                ticket,
                accepted,
                directory: directory.join("participant"),
                container: directory,
                participant,
                identity,
            },
        ))
    }
}

fn add_reference(
    map: &mut BTreeMap<String, AssemblyAssetRole>,
    reference: &str,
    role: AssemblyAssetRole,
) -> Result<()> {
    if reference.len() > 4096 {
        return Err("asset_reference_limit".into());
    }
    if map
        .insert(reference.into(), role)
        .is_some_and(|old| old != role)
    {
        return Err("ambiguous_asset_role".into());
    }
    Ok(())
}

pub fn review(shared: Shared, work: ReviewWork) {
    let result = (|| {
        let mut assets = Vec::new();
        let mut bytes_total = 0usize;
        for input in work.inputs {
            let bytes = service::read_bounded(&input.path, 64 * 1024 * 1024)?;
            // PCM16 inputs can double when decoded to float; keep aggregate acquisition below 256 MiB.
            bytes_total = bytes_total
                .checked_add(bytes.len())
                .ok_or("assembly_asset_limit")?;
            if bytes_total > 256 * 1024 * 1024 {
                return Err("assembly_asset_limit".into());
            }
            assets.push(
                VerifiedAssemblyAsset::from_wav_bytes(
                    &input.reference,
                    &bytes,
                    &input.sha256,
                    input.role,
                    &work.ticket.cancel,
                )
                .map_err(|e| e.to_string())?,
            );
        }
        let cue = include_bytes!(
            "../../../../packages/pps-resources/assets/tactile/default_tactile_cue.wav"
        );
        let tactile = VerifiedAssemblyAsset::from_wav_bytes(
            "bundled-tactile",
            cue,
            &service::sha(cue),
            AssemblyAssetRole::TactileCue,
            &work.ticket.cancel,
        )
        .map_err(|e| e.to_string())?;
        let source = assembly::plan_assembly_preview(
            &work.snapshot["design"],
            &work.snapshot["block_csv_preview"],
            &work.variants,
            &assets,
            &tactile,
            &work.ticket.cancel,
        )
        .map_err(|e| e.to_string())?;
        let order = assembly::plan_run_order_preview(&source, &assets, &work.ticket.cancel)
            .map_err(|e| e.to_string())?;
        let hashes = json!({"design_sha256":source.design_sha256,"assembly_preview_sha256":source.preview_sha256,"run_order_sha256":order.run_order_sha256});
        let mut next = work.snapshot;
        next["block_csv_preview"] = source.preview.clone();
        next["run_sequence_setup"] = order.preview.clone();
        next["native_execution_review"] =
            json!({"hashes":hashes,"accepted":false,"physical_timing_qualified":false});
        next["run_package"] = Value::Null;
        let mut owner = shared.lock().map_err(|_| "host_unavailable")?;
        owner
            .jobs
            .publish(&work.ticket, || Ok(()))
            .map_err(str::to_owned)?;
        owner.publish_snapshot(next)?;
        owner.review = Some(Review {
            source,
            order,
            assets,
            tactile,
        });
        owner.jobs.finish(
            &work.ticket,
            "succeeded",
            "Full block and participant order ready for review",
            Some(json!({"kind":"assembly_review"})),
        );
        Ok(())
    })();
    if let Err(error) = result {
        service::fail_job(&shared, &work.ticket, error);
    }
}

pub fn prepare(shared: Shared, work: PrepareWork) {
    let result = (|| {
        let staged = assembly::prepare_accepted_participant(
            &work.accepted.plan,
            &work.accepted.assets,
            &work.accepted.tactile,
            &work.directory,
            work.participant,
            &work.identity,
            &work.ticket.cancel,
        )
        .map_err(|e| e.to_string())?;
        let handoff = if let Some(group) = staged.group_manifest_path() {
            pps_session_package::verify_prepared_group(group)
                .map_err(|_| "prepared_group_verification_failed")?;
            group.to_path_buf()
        } else {
            let part = staged.parts().first().ok_or("prepared_part_missing")?;
            pps_session_package::verify_prepared_session(
                pps_session_package::VerificationRequest::new(part.manifest_path()),
            )
            .map_err(|_| "prepared_session_verification_failed")?;
            part.manifest_path().to_path_buf()
        };
        if work.ticket.cancel.load(Ordering::Acquire) {
            return Err("generation_cancelled".into());
        }
        let mut owner = shared.lock().map_err(|_| "host_unavailable")?;
        owner
            .jobs
            .publish(&work.ticket, || Ok(()))
            .map_err(str::to_owned)?;
        owner.prepared_directory = Some(work.directory.clone());
        let result = json!({"kind":"prepared_participant","participant_index":work.participant,"part_count":staged.parts().len(),"handoff_file":handoff.file_name().and_then(|s|s.to_str()).unwrap_or("session_manifest.json"),"executed":false,"physical_timing_qualified":false});
        owner.jobs.finish(
            &work.ticket,
            "succeeded",
            "Participant files verified; not yet executed",
            Some(result),
        );
        Ok(())
    })();
    if let Err(error) = result {
        // This job owns this newly created child directory; never remove the chosen parent.
        let _ = fs::remove_dir_all(&work.container);
        service::fail_job(&shared, &work.ticket, error);
    }
}
