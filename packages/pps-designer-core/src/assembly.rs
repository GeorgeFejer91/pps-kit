//! Native composition of already-reviewed Segment 5 rows. This module never
//! randomizes, discovers files from JSON, synthesizes replacement comparators,
//! or grants permission to publish a staged package.
use crate::{check_cancelled, sample_index, GenerationError, MAX_FRAMES};
use serde::Serialize;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    io::Cursor,
    sync::atomic::AtomicBool,
};

pub const MAX_ASSEMBLY_ROWS: usize = 10_000;
pub const MAX_ASSEMBLY_BLOCKS: usize = 128;
const MAX_DECODED_ASSET_BYTES: usize = 512 * 1024 * 1024;
const MAX_ASSET_BYTES: usize = MAX_FRAMES * 8 + 1024 * 1024;
const MAX_BLOCK_BYTES: u64 = 768 * 1024 * 1024;
const MAX_PACKAGE_BYTES: u64 = 8 * 1024 * 1024 * 1024;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum AssemblyAssetRole {
    BinauralIngredient,
    Instruction,
    TactileCue,
    StationaryBaseline,
}

/// Decoded native receipt. No Deserialize: browser strings are never sufficient
/// authority to open an asset. The host must bound acquisition before this call.
#[derive(Debug)]
pub struct VerifiedAssemblyAsset {
    reference: String,
    sha256: String,
    role: AssemblyAssetRole,
    rate: u32,
    channels: usize,
    pcm: Vec<f32>,
}
impl VerifiedAssemblyAsset {
    pub fn from_wav_bytes(
        reference: &str,
        bytes: &[u8],
        expected_sha256: &str,
        role: AssemblyAssetRole,
        cancelled: &AtomicBool,
    ) -> Result<Self, GenerationError> {
        check_cancelled(cancelled)?;
        if reference.is_empty() || reference.len() > 4096 || bytes.len() > MAX_ASSET_BYTES {
            return Err(GenerationError::ResourceLimit);
        }
        let mut hash = Sha256::new();
        for chunk in bytes.chunks(65536) {
            check_cancelled(cancelled)?;
            hash.update(chunk);
        }
        if format!("{:x}", hash.finalize()) != expected_sha256 {
            return Err(GenerationError::Invalid("assembly_asset_sha256"));
        }
        let mut reader =
            hound::WavReader::new(Cursor::new(bytes)).map_err(|_| GenerationError::InvalidAudio)?;
        let spec = reader.spec();
        let channels = usize::from(spec.channels);
        let samples = reader.len() as usize;
        let valid_channels = match role {
            AssemblyAssetRole::Instruction => (1..=2).contains(&channels),
            AssemblyAssetRole::TactileCue => channels == 1,
            _ => channels == 2,
        };
        if !valid_channels
            || !(8000..=192000).contains(&spec.sample_rate)
            || samples == 0
            || samples > MAX_FRAMES * channels
            || !samples.is_multiple_of(channels)
        {
            return Err(GenerationError::Invalid("assembly_asset_layout"));
        }
        let mut pcm = Vec::new();
        pcm.try_reserve_exact(samples)
            .map_err(|_| GenerationError::ResourceLimit)?;
        match (spec.sample_format, spec.bits_per_sample) {
            (hound::SampleFormat::Float, 32) => {
                read_samples(reader.samples::<f32>(), samples, &mut pcm, cancelled)?
            }
            (hound::SampleFormat::Int, 16 | 24 | 32) => {
                let scale = (1_u64 << (spec.bits_per_sample - 1)) as f64;
                read_samples(
                    reader
                        .samples::<i32>()
                        .map(|v| v.map(|s| (f64::from(s) / scale) as f32)),
                    samples,
                    &mut pcm,
                    cancelled,
                )?;
            }
            _ => return Err(GenerationError::Invalid("assembly_asset_encoding")),
        }
        if role == AssemblyAssetRole::TactileCue
            && (samples as f64 / f64::from(spec.sample_rate) > 2.0 || pcm.iter().all(|v| *v == 0.0))
        {
            return Err(GenerationError::Invalid("assembly_tactile_cue"));
        }
        Ok(Self {
            reference: reference.into(),
            sha256: expected_sha256.into(),
            role,
            rate: spec.sample_rate,
            channels,
            pcm,
        })
    }
    pub fn reference(&self) -> &str {
        &self.reference
    }
    pub fn sha256(&self) -> &str {
        &self.sha256
    }
    pub fn sample_rate_hz(&self) -> u32 {
        self.rate
    }
    pub fn frames(&self) -> usize {
        self.pcm.len() / self.channels
    }
    pub fn role(&self) -> AssemblyAssetRole {
        self.role
    }
}
fn read_samples(
    samples: impl Iterator<Item = Result<f32, hound::Error>>,
    expected: usize,
    pcm: &mut Vec<f32>,
    cancelled: &AtomicBool,
) -> Result<(), GenerationError> {
    for (i, sample) in samples.enumerate() {
        if i % 4096 == 0 {
            check_cancelled(cancelled)?;
        }
        let sample = sample.map_err(|_| GenerationError::InvalidAudio)?;
        if !sample.is_finite() || sample.abs() > 1.0 || pcm.len() >= expected {
            return Err(GenerationError::InvalidAudio);
        }
        pcm.push(sample);
    }
    if pcm.len() != expected {
        return Err(GenerationError::InvalidAudio);
    }
    Ok(())
}

#[derive(Debug, Clone)]
enum Component {
    Audio {
        reference: String,
        frames: usize,
        gain: f64,
        looming: bool,
        baseline: Option<String>,
    },
    Silence {
        frames: usize,
    },
}
#[derive(Debug, Clone)]
struct Variant {
    components: Vec<Component>,
    frames: usize,
    looming: usize,
}
#[derive(Debug, Clone)]
struct PlannedRow {
    row: Value,
    variant: Variant,
    family: String,
    baseline_mode: String,
    tactile_onset: Option<usize>,
}
#[derive(Debug, Clone)]
struct PlannedBlock {
    index: usize,
    label: String,
    rows: Vec<PlannedRow>,
    frames: usize,
}
#[derive(Debug, Clone)]
struct Recipe {
    blocks: Vec<PlannedBlock>,
    sample_rate: u32,
    asset_hashes: BTreeMap<String, String>,
    tactile_reference: String,
    tactile_sha256: String,
    design: Value,
    preview_digest: String,
}

/// Complete enriched rows are safe for local review. Native recipe is retained
/// privately; a caller cannot manufacture an accepted plan from accepted:true.
#[derive(Debug, Serialize)]
pub struct AssemblyPreview {
    pub design_sha256: String,
    pub preview_sha256: String,
    pub preview: Value,
    #[serde(skip_serializing)]
    recipe: Recipe,
}
#[derive(Debug)]
pub struct AcceptedAssemblyPlan {
    design_sha256: String,
    preview_sha256: String,
    revision: u64,
    preview: Value,
    recipe: Recipe,
}
impl AcceptedAssemblyPlan {
    pub fn revision(&self) -> u64 {
        self.revision
    }
    pub fn design_sha256(&self) -> &str {
        &self.design_sha256
    }
    pub fn preview_sha256(&self) -> &str {
        &self.preview_sha256
    }
}

pub fn design_fingerprint(design: &Value) -> Result<String, GenerationError> {
    bounded_json(design)?;
    hash_json(design)
}
fn hash_json(value: &Value) -> Result<String, GenerationError> {
    Ok(format!(
        "{:x}",
        Sha256::digest(
            serde_json::to_vec(value).map_err(|_| GenerationError::Invalid("assembly_json"))?
        )
    ))
}
fn bounded_json(value: &Value) -> Result<(), GenerationError> {
    fn visit(v: &Value, depth: usize, n: &mut usize) -> Result<(), GenerationError> {
        if depth > 32 {
            return Err(GenerationError::ResourceLimit);
        }
        *n = n.saturating_add(16);
        match v {
            Value::String(s) => *n = n.saturating_add(s.len()),
            Value::Array(a) => {
                for x in a {
                    visit(x, depth + 1, n)?;
                }
            }
            Value::Object(o) => {
                for (k, x) in o {
                    *n = n.saturating_add(k.len());
                    visit(x, depth + 1, n)?;
                }
            }
            _ => {}
        }
        if *n > 8 * 1024 * 1024 {
            return Err(GenerationError::ResourceLimit);
        }
        Ok(())
    }
    visit(value, 0, &mut 0)
}
pub fn accept_assembly_preview(
    mut preview: AssemblyPreview,
    expected_design_sha256: &str,
    expected_preview_sha256: &str,
    revision: u64,
) -> Result<AcceptedAssemblyPlan, GenerationError> {
    if preview.design_sha256 != expected_design_sha256
        || preview.preview_sha256 != expected_preview_sha256
        || hash_json(&preview.preview)? != preview.preview_sha256
        || preview.recipe.preview_digest != preview.preview_sha256
        || hash_json(&preview.recipe.design)? != preview.design_sha256
    {
        return Err(GenerationError::Invalid("assembly_preview_stale"));
    }
    preview.preview["accepted"] = json!(true);
    Ok(AcceptedAssemblyPlan {
        design_sha256: preview.design_sha256,
        preview_sha256: preview.preview_sha256,
        revision,
        preview: preview.preview,
        recipe: preview.recipe,
    })
}

/// Enrich the existing planner output before operator review. Choices come from
/// the existing stripPreviewVariants helper, not a second scheduling algorithm.
pub fn plan_assembly_preview(
    design: &Value,
    preview: &Value,
    variants: &Value,
    assets: &[VerifiedAssemblyAsset],
    tactile: &VerifiedAssemblyAsset,
    cancelled: &AtomicBool,
) -> Result<AssemblyPreview, GenerationError> {
    check_cancelled(cancelled)?;
    bounded_json(design)?;
    bounded_json(preview)?;
    bounded_json(variants)?;
    let design_sha256 = design_fingerprint(design)?;
    if preview["randomization_seed"] != design["protocol"]["random_seed"]
        || preview["randomization_strategy"] != "seeded_gellermann_row_order_preserving"
    {
        return Err(GenerationError::Invalid(
            "assembly_randomization_provenance",
        ));
    }
    let asset_map = asset_map(assets, tactile)?;
    let rate = tactile.rate;
    let variants = validate_variants(design, variants, &asset_map, rate, cancelled)?;
    let raw_blocks = preview["blocks"]
        .as_array()
        .ok_or(GenerationError::Invalid("assembly_blocks"))?;
    if raw_blocks.is_empty()
        || raw_blocks.len() > MAX_ASSEMBLY_BLOCKS
        || integer(&preview["block_count"])? != raw_blocks.len()
        || integer(&design["protocol"]["blocks"])? != raw_blocks.len()
    {
        return Err(GenerationError::Invalid("assembly_block_count"));
    }
    let mut output = preview.clone();
    let mut blocks = Vec::new();
    let mut total_rows = 0;
    let mut total_bytes = 0_u64;
    let mut seen_pool = BTreeSet::new();
    for (ordinal, block) in raw_blocks.iter().enumerate() {
        check_cancelled(cancelled)?;
        if integer(&block["block_index"])? != ordinal + 1 {
            return Err(GenerationError::Invalid("assembly_block_order"));
        }
        let label = string(&block["block_label"])?;
        let rows = block["preview_rows"]
            .as_array()
            .ok_or(GenerationError::Invalid("assembly_rows"))?;
        if rows.is_empty()
            || rows.len() != integer(&block["trial_count"])?
            || block
                .get("preview_row_count")
                .is_some_and(|n| integer(n).ok() != Some(rows.len()))
        {
            return Err(GenerationError::Invalid("assembly_truncated_rows"));
        }
        total_rows += rows.len();
        if total_rows > MAX_ASSEMBLY_ROWS {
            return Err(GenerationError::ResourceLimit);
        }
        let mut planned = Vec::new();
        let mut frames = 0_usize;
        for (row_index, row) in rows.iter().enumerate() {
            check_cancelled(cancelled)?;
            if integer(&row["block_index"])? != ordinal + 1
                || integer(&row["block_trial_index"])? != row_index + 1
                || string(&row["block_label"])? != label
            {
                return Err(GenerationError::Invalid("assembly_row_order"));
            }
            if !seen_pool.insert(integer(&row["trial_pool_index"])?) {
                return Err(GenerationError::Invalid(
                    "assembly_duplicate_trial_pool_index",
                ));
            }
            let family = string(&row["family"])?;
            if !["audio_tactile", "baseline", "catch", "auditory_only"].contains(&family) {
                return Err(GenerationError::Invalid(
                    "assembly_unsupported_trial_family",
                ));
            }
            let key = (
                string(&row["row_label"])?.to_owned(),
                string(&row["sequence_variant_key"])?.to_owned(),
            );
            let variant = variants
                .get(&key)
                .ok_or(GenerationError::Invalid("assembly_variant_missing"))?
                .clone();
            let baseline_mode = if family == "baseline" {
                baseline_policy(design, row)?
            } else {
                String::new()
            };
            if baseline_mode == "stationary_burst"
                && variant.components.iter().any(|c| {
                    matches!(
                        c,
                        Component::Audio {
                            looming: true,
                            baseline: None,
                            ..
                        }
                    )
                })
            {
                return Err(GenerationError::Invalid(
                    "assembly_stationary_comparator_required",
                ));
            }
            let tactile_onset = if ["audio_tactile", "baseline"].contains(&family) {
                let soa = finite_number(&row["soa_ms"])? / 1000.0;
                if soa < 0.0 {
                    return Err(GenerationError::Invalid("assembly_negative_soa"));
                }
                let onset = variant
                    .looming
                    .checked_add(sample_index(soa, rate))
                    .ok_or(GenerationError::ResourceLimit)?;
                if onset
                    .checked_add(tactile.frames())
                    .is_none_or(|end| end > variant.frames)
                {
                    return Err(GenerationError::Invalid("assembly_tactile_outside_trial"));
                }
                Some(onset)
            } else {
                None
            };
            let mut enriched = row.clone();
            enriched["duration_ms"] = json!(milliseconds(variant.frames, rate));
            enriched["duration_s"] = json!(variant.frames as f64 / f64::from(rate));
            enriched["sample_rate_hz"] = json!(rate);
            enriched["frames"] = json!(variant.frames);
            enriched["looming_segment_onset_s"] = json!(variant.looming as f64 / f64::from(rate));
            enriched["tactile_onset_s"] = tactile_onset
                .map(|v| json!(v as f64 / f64::from(rate)))
                .unwrap_or(json!(""));
            enriched["tactile_duration_ms"] = json!(if tactile_onset.is_some() {
                milliseconds(tactile.frames(), rate)
            } else {
                0
            });
            enriched["channels"] = json!(3);
            enriched["tactile_channel"] = if tactile_onset.is_some() {
                json!(3)
            } else {
                json!("")
            };
            enriched["baseline_mode"] = json!(baseline_mode);
            enriched["trial_file_path"] = json!("");
            enriched["source_sha256"] = json!("");
            enriched["native_assembly_policy"] =
                json!("verified_pcm_exact_rate_no_hidden_normalization.v1");
            frames = frames
                .checked_add(variant.frames)
                .ok_or(GenerationError::ResourceLimit)?;
            planned.push(PlannedRow {
                row: enriched,
                variant,
                family: family.into(),
                baseline_mode,
                tactile_onset,
            });
        }
        let bytes = (frames as u64)
            .checked_mul(12)
            .ok_or(GenerationError::ResourceLimit)?;
        total_bytes = total_bytes
            .checked_add(bytes)
            .ok_or(GenerationError::ResourceLimit)?;
        if bytes > MAX_BLOCK_BYTES || total_bytes > MAX_PACKAGE_BYTES {
            return Err(GenerationError::ResourceLimit);
        }
        let out = &mut output["blocks"][ordinal];
        out["preview_rows"] = json!(planned.iter().map(|r| &r.row).collect::<Vec<_>>());
        out["duration_ms"] = json!(milliseconds(frames, rate));
        out["preview_row_count"] = json!(planned.len());
        blocks.push(PlannedBlock {
            index: ordinal + 1,
            label: label.into(),
            rows: planned,
            frames,
        });
    }
    if integer(&preview["total_trials"])? != total_rows
        || preview
            .get("total_count")
            .is_some_and(|n| integer(n).ok() != Some(total_rows))
    {
        return Err(GenerationError::Invalid("assembly_total_count"));
    }
    output["schema"] = json!("pps-block-csv-preview.v1");
    output["accepted"] = json!(false);
    output["status"] = json!("native_review_required");
    output["estimated_total_duration_ms"] = json!(blocks
        .iter()
        .map(|b| milliseconds(b.frames, rate))
        .sum::<u64>());
    output["native_assembly_qualification"] = json!("unqualified_exact_verified_assets");
    output["native_assembly_scope"] = json!("source_blocks_once");
    let preview_sha256 = hash_json(&output)?;
    let asset_hashes = assets
        .iter()
        .map(|a| (a.reference.clone(), a.sha256.clone()))
        .collect();
    Ok(AssemblyPreview {
        design_sha256,
        preview_sha256: preview_sha256.clone(),
        preview: output,
        recipe: Recipe {
            blocks,
            sample_rate: rate,
            asset_hashes,
            tactile_reference: tactile.reference.clone(),
            tactile_sha256: tactile.sha256.clone(),
            design: design.clone(),
            preview_digest: preview_sha256.clone(),
        },
    })
}

fn asset_map<'a>(
    assets: &'a [VerifiedAssemblyAsset],
    tactile: &'a VerifiedAssemblyAsset,
) -> Result<BTreeMap<String, &'a VerifiedAssemblyAsset>, GenerationError> {
    if tactile.role != AssemblyAssetRole::TactileCue || assets.len() > 1024 {
        return Err(GenerationError::Invalid("assembly_tactile_receipt"));
    }
    let mut map = BTreeMap::new();
    let mut bytes = tactile.pcm.len() * 4;
    for asset in assets {
        bytes = bytes
            .checked_add(asset.pcm.len() * 4)
            .ok_or(GenerationError::ResourceLimit)?;
        if bytes > MAX_DECODED_ASSET_BYTES {
            return Err(GenerationError::ResourceLimit);
        }
        if map.insert(asset.reference.clone(), asset).is_some() {
            return Err(GenerationError::Invalid("assembly_duplicate_asset"));
        }
    }
    Ok(map)
}
fn string(value: &Value) -> Result<&str, GenerationError> {
    value
        .as_str()
        .filter(|s| !s.is_empty() && s.len() <= 1024 && !s.chars().any(char::is_control))
        .ok_or(GenerationError::Invalid("assembly_text"))
}
fn finite_number(value: &Value) -> Result<f64, GenerationError> {
    value
        .as_f64()
        .filter(|v| v.is_finite())
        .ok_or(GenerationError::Invalid("assembly_number"))
}
fn integer(value: &Value) -> Result<usize, GenerationError> {
    value
        .as_u64()
        .and_then(|v| usize::try_from(v).ok())
        .ok_or(GenerationError::Invalid("assembly_integer"))
}
fn milliseconds(frames: usize, rate: u32) -> u64 {
    (frames as f64 * 1000.0 / f64::from(rate)).round_ties_even() as u64
}
fn baseline_policy(design: &Value, row: &Value) -> Result<String, GenerationError> {
    let mode = design["protocol"]["baseline_strategy"]
        .as_str()
        .or_else(|| row["baseline_mode"].as_str())
        .unwrap_or("");
    match mode {
        "tactile_only" | "stationary_burst" => Ok(mode.into()),
        "custom" => match design["protocol"]["baseline_custom_trial_mode"].as_str() {
            Some("tactile_only") => Ok("tactile_only".into()),
            _ => Err(GenerationError::Invalid(
                "assembly_custom_baseline_unsupported",
            )),
        },
        _ => Err(GenerationError::Invalid("assembly_baseline_policy")),
    }
}

fn validate_variants(
    design: &Value,
    variants: &Value,
    assets: &BTreeMap<String, &VerifiedAssemblyAsset>,
    rate: u32,
    cancelled: &AtomicBool,
) -> Result<BTreeMap<(String, String), Variant>, GenerationError> {
    let variants = variants
        .as_array()
        .ok_or(GenerationError::Invalid("assembly_variants"))?;
    if variants.len() > MAX_ASSEMBLY_ROWS {
        return Err(GenerationError::ResourceLimit);
    }
    let mut sources = BTreeMap::new();
    for (collection, path_key, role) in [
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
        if let Some(entries) = design.get(collection) {
            for source in entries
                .as_array()
                .ok_or(GenerationError::Invalid("assembly_sources"))?
            {
                let label = string(&source["label"])?;
                if sources.insert(label, (source, path_key, role)).is_some() {
                    return Err(GenerationError::Invalid("assembly_ambiguous_source"));
                }
            }
        }
    }
    let strips = design["protocol"]["trial_strips"]
        .as_array()
        .ok_or(GenerationError::Invalid("assembly_strips"))?;
    let mut strip_map = BTreeMap::new();
    for strip in strips {
        if strip_map.insert(string(&strip["label"])?, strip).is_some() {
            return Err(GenerationError::Invalid("assembly_ambiguous_strip"));
        }
    }
    let instruction_db = design["study_profile_reference_parameters"]["loudness_policy"]
        .get("instruction_offset_db")
        .map(finite_number)
        .transpose()?
        .unwrap_or(-6.0);
    if !(-30.0..=0.0).contains(&instruction_db) {
        return Err(GenerationError::Invalid("assembly_instruction_gain"));
    }
    let mut result = BTreeMap::new();
    for v in variants {
        check_cancelled(cancelled)?;
        let row_label = string(&v["row_label"])?;
        let key = string(&v["sequence_variant_key"])?;
        let strip = strip_map
            .get(row_label)
            .ok_or(GenerationError::Invalid("assembly_strip_missing"))?;
        let elements = strip["elements"]
            .as_array()
            .ok_or(GenerationError::Invalid("assembly_elements"))?;
        let choices = v["choices"]
            .as_array()
            .ok_or(GenerationError::Invalid("assembly_choices"))?;
        if choices.is_empty() || choices.len() != elements.len() || choices.len() > 256 {
            return Err(GenerationError::Invalid("assembly_choice_count"));
        }
        let mut components = Vec::new();
        let mut frames = 0_usize;
        let mut looming = None;
        let mut reconstructed = Vec::new();
        for (choice, element) in choices.iter().zip(elements) {
            if element["kind"] == "jitter" {
                if choice["kind"] != "jitter" {
                    return Err(GenerationError::Invalid("assembly_choice_kind"));
                }
                let ms = integer(&choice["value"])?;
                if ms > 60_000
                    || !element["jitter_values_ms"]
                        .as_array()
                        .is_some_and(|a| a.iter().any(|v| integer(v).ok() == Some(ms)))
                {
                    return Err(GenerationError::Invalid("assembly_jitter_choice"));
                }
                let n = sample_index(ms as f64 / 1000.0, rate);
                components.push(Component::Silence { frames: n });
                frames += n;
                reconstructed.push(format!("jitter_{ms}ms"));
            } else {
                if choice["kind"] != "audio" {
                    return Err(GenerationError::Invalid("assembly_choice_kind"));
                }
                let label = string(&choice["label"])?;
                let permitted = element["source_labels"]
                    .as_array()
                    .filter(|a| !a.is_empty())
                    .map(|a| a.iter().any(|v| v.as_str() == Some(label)))
                    .unwrap_or(element["source_label"].as_str() == Some(label));
                if !permitted {
                    return Err(GenerationError::Invalid("assembly_source_choice"));
                }
                let (source, path_key, role) = sources
                    .get(label)
                    .ok_or(GenerationError::Invalid("assembly_source_missing"))?;
                let reference = string(&source[*path_key])?;
                let asset = assets
                    .get(reference)
                    .ok_or(GenerationError::Invalid("assembly_asset_receipt_missing"))?;
                if asset.role != *role {
                    return Err(GenerationError::Invalid("assembly_asset_role"));
                }
                if asset.rate != rate {
                    return Err(GenerationError::Invalid(
                        "assembly_asset_rate_requires_explicit_resampling",
                    ));
                }
                let is_looming = *role == AssemblyAssetRole::BinauralIngredient;
                if is_looming {
                    if looming.is_some() {
                        return Err(GenerationError::Invalid(
                            "assembly_multiple_looming_sources",
                        ));
                    }
                    looming = Some(frames);
                }
                let mut gain = source
                    .get("gain")
                    .map(finite_number)
                    .transpose()?
                    .unwrap_or(1.0);
                if !is_looming {
                    gain *= 10.0_f64.powf(instruction_db / 20.0);
                }
                if !(0.0..=16.0).contains(&gain)
                    || asset.pcm.iter().any(|v| f64::from(v.abs()) * gain > 1.0)
                {
                    return Err(GenerationError::PeakCeilingExceeded);
                }
                let baseline = source
                    .get("native_stationary_baseline_asset")
                    .and_then(Value::as_str)
                    .map(str::to_owned);
                if let Some(reference) = &baseline {
                    let comparator = assets.get(reference).ok_or(GenerationError::Invalid(
                        "assembly_stationary_comparator_required",
                    ))?;
                    if comparator.role != AssemblyAssetRole::StationaryBaseline
                        || comparator.rate != rate
                        || comparator.frames() != asset.frames()
                        || comparator
                            .pcm
                            .iter()
                            .any(|v| f64::from(v.abs()) * gain > 1.0)
                    {
                        return Err(GenerationError::Invalid(
                            "assembly_stationary_comparator_contract",
                        ));
                    }
                }
                components.push(Component::Audio {
                    reference: reference.into(),
                    frames: asset.frames(),
                    gain,
                    looming: is_looming,
                    baseline,
                });
                frames += asset.frames();
                reconstructed.push(label.into());
            }
            if frames > MAX_FRAMES {
                return Err(GenerationError::ResourceLimit);
            }
        }
        if reconstructed.join(" + ") != key {
            return Err(GenerationError::Invalid("assembly_variant_key_mismatch"));
        }
        let looming = looming.ok_or(GenerationError::Invalid("assembly_looming_anchor_missing"))?;
        if result
            .insert(
                (row_label.into(), key.into()),
                Variant {
                    components,
                    frames,
                    looming,
                },
            )
            .is_some()
        {
            return Err(GenerationError::Invalid("assembly_ambiguous_variant"));
        }
    }
    Ok(result)
}

#[derive(Debug)]
pub struct StagedSession {
    manifest_path: std::path::PathBuf,
    preview_sha256: String,
    block_count: usize,
    trial_count: usize,
}
impl StagedSession {
    pub fn manifest_path(&self) -> &std::path::Path {
        &self.manifest_path
    }
    pub fn preview_sha256(&self) -> &str {
        &self.preview_sha256
    }
    pub fn block_count(&self) -> usize {
        self.block_count
    }
    pub fn trial_count(&self) -> usize {
        self.trial_count
    }
}

/// Writes a new immutable private candidate directory. The host must reverify
/// this V1 package, then atomically expose its manifest reference only after
/// revision/cancellation checks. Do not rename it: native paths bind this root.
/// On failure the host owns removal of this private, unpublished directory.
pub fn prepare_accepted_session(
    plan: &AcceptedAssemblyPlan,
    assets: &[VerifiedAssemblyAsset],
    tactile: &VerifiedAssemblyAsset,
    private_output_dir: &std::path::Path,
    participant_id: &str,
    session_id: &str,
    cancelled: &AtomicBool,
) -> Result<StagedSession, GenerationError> {
    use std::{fs, io::BufWriter};
    check_cancelled(cancelled)?;
    let structure = plan.recipe.design["study_profile_reference_parameters"]["dashboard_run_setup"]
        ["experiment_structure"]
        .as_str()
        .unwrap_or("single");
    let block_policy = plan.recipe.design["protocol"]["block_order_randomization"]
        .as_str()
        .unwrap_or("fixed");
    if !["single", "single_phase"].contains(&structure)
        || !["fixed", "none", "sequential"].contains(&block_policy)
    {
        return Err(GenerationError::Invalid(
            "assembly_participant_run_order_required",
        ));
    }
    if !safe_identity(participant_id) || !safe_identity(session_id) {
        return Err(GenerationError::Invalid("assembly_session_identity"));
    }
    let asset_map = asset_map(assets, tactile)?;
    if tactile.reference != plan.recipe.tactile_reference
        || tactile.sha256 != plan.recipe.tactile_sha256
        || assets.len() != plan.recipe.asset_hashes.len()
        || plan
            .recipe
            .asset_hashes
            .iter()
            .any(|(id, hash)| asset_map.get(id).is_none_or(|asset| asset.sha256 != *hash))
    {
        return Err(GenerationError::Invalid("assembly_assets_changed"));
    }
    let parent = private_output_dir
        .parent()
        .ok_or(GenerationError::Invalid("assembly_output_parent"))?
        .canonicalize()
        .map_err(|_| GenerationError::Io)?;
    let name = private_output_dir
        .file_name()
        .and_then(|n| n.to_str())
        .filter(|n| safe_identity(n))
        .ok_or(GenerationError::Invalid("assembly_output_name"))?;
    let root = parent.join(name);
    fs::create_dir(&root).map_err(|_| GenerationError::Invalid("assembly_output_must_be_new"))?;
    for directory in ["blocks", "sources", "trials"] {
        fs::create_dir(root.join(directory)).map_err(|_| GenerationError::Io)?;
    }
    let setup = json!({"schema":"pps-native-run-setup.v1","participant_id":participant_id,"session_id":session_id,"design_revision":plan.revision,
        "design_sha256":plan.design_sha256,"approved_preview_sha256":plan.preview_sha256,"approved_segment5":plan.preview,
        "design":plan.recipe.design,"assets":plan.recipe.asset_hashes,"tactile_asset_sha256":tactile.sha256,
        "assembly_policy":"verified_pcm_exact_rate_no_hidden_normalization.v1","physical_timing_qualified":false,"replication_qualified":false});
    let setup_path = root.join("run_setup_manifest.json");
    let setup_hash = write_json_new(&setup_path, &setup, cancelled)?;
    let rate = plan.recipe.sample_rate;
    let spec = hound::WavSpec {
        channels: 3,
        sample_rate: rate,
        bits_per_sample: 32,
        sample_format: hound::SampleFormat::Float,
    };
    let mut manifests = Vec::new();
    let mut cache: BTreeMap<String, (String, String)> = BTreeMap::new();
    let mut trial_total = 0;
    for block in &plan.recipe.blocks {
        check_cancelled(cancelled)?;
        let stem = format!("block_{:03}", block.index);
        let wav_relative = format!("blocks/{stem}.wav");
        let csv_relative = format!("blocks/{stem}.csv");
        let source_relative = format!("sources/{stem}_final.csv");
        let file = new_file(&root.join(&wav_relative))?;
        let mut writer =
            hound::WavWriter::new(BufWriter::new(file), spec).map_err(|_| GenerationError::Io)?;
        let mut source_rows = Vec::new();
        let mut prepared_rows = Vec::new();
        let mut cursor = 0_usize;
        for (ordinal, planned) in block.rows.iter().enumerate() {
            check_cancelled(cancelled)?;
            let pcm = compose_trial(planned, &asset_map, tactile, cancelled)?;
            let key = hash_json(&json!([
                planned.row["row_label"],
                planned.row["sequence_variant_key"],
                planned.family,
                planned.baseline_mode,
                planned.tactile_onset
            ]))?;
            let (trial_relative, trial_hash) = if let Some(cached) = cache.get(&key) {
                cached.clone()
            } else {
                let path = format!("trials/trial_{:05}.wav", cache.len() + 1);
                let mut trial =
                    hound::WavWriter::new(BufWriter::new(new_file(&root.join(&path))?), spec)
                        .map_err(|_| GenerationError::Io)?;
                write_pcm(&mut trial, &pcm, cancelled)?;
                trial.finalize().map_err(|_| GenerationError::Io)?;
                sync_file(&root.join(&path))?;
                let digest = hash_file(&root.join(&path), cancelled)?;
                cache.insert(key, (path.clone(), digest.clone()));
                (path, digest)
            };
            write_pcm(&mut writer, &pcm, cancelled)?;
            let mut source = planned.row.clone();
            source["trial_file_path"] = json!(format!("../{trial_relative}"));
            source["source_sha256"] = json!(trial_hash);
            source["source_file_name"] = json!(trial_relative.rsplit('/').next().unwrap());
            source_rows.push(source.clone());
            let mut row = source;
            row["Participant_ID"] = json!(participant_id);
            row["Session_ID"] = json!(session_id);
            row["Block_Number"] = json!(block.index);
            row["Block_Label"] = json!(block.label);
            row["Trial_Number"] = json!(ordinal + 1);
            row["Trial_UID"] = json!(format!(
                "{participant_id}_{session_id}_B{:03}_T{:05}",
                block.index,
                ordinal + 1
            ));
            row["Trial_Type"] = json!(match planned.family.as_str() {
                "audio_tactile" => "Audio-Tactile",
                "baseline" => "Baseline",
                "catch" => "Catch",
                _ => "Auditory-Only",
            });
            row["Family"] = json!(planned.family);
            row["SOA_ms"] = row["soa_ms"].clone();
            row["Source_SHA256"] = json!(trial_hash);
            row["Trial_File_Path"] = json!(root
                .join(&trial_relative)
                .to_str()
                .ok_or(GenerationError::Invalid("assembly_native_path"))?);
            row["Sample_Rate_Hz"] = json!(rate);
            row["Channels"] = json!(3);
            row["Trial_Duration_S"] = json!(planned.variant.frames as f64 / f64::from(rate));
            row["Trial_Start_Sample"] = json!(cursor);
            row["Trial_Start_S"] = json!(cursor as f64 / f64::from(rate));
            row["Trial_End_Sample"] = json!(cursor + planned.variant.frames);
            row["Trial_End_S"] = json!((cursor + planned.variant.frames) as f64 / f64::from(rate));
            row["Looming_Onset_Sample"] = if planned.family == "baseline" {
                json!("")
            } else {
                json!(cursor + planned.variant.looming)
            };
            row["Tactile_Onset_Sample"] = planned
                .tactile_onset
                .map(|n| json!(cursor + n))
                .unwrap_or(json!(""));
            row["Tactile_Drive_Onset_Sample"] = row["Tactile_Onset_Sample"].clone();
            row["Response_Window_Onset_Sample"] = json!(
                cursor
                    + if planned.family == "baseline" {
                        planned.tactile_onset.unwrap()
                    } else {
                        planned.variant.looming
                    }
            );
            row["Tactile_Waveform_Generated"] = json!(false);
            row["Tactile_Asset_SHA256"] = if planned.tactile_onset.is_some() {
                json!(tactile.sha256)
            } else {
                json!("")
            };
            row["Tactile_Latency_Compensation_Status"] = json!("not_applied_unqualified");
            row["Native_Approved_Preview_SHA256"] = json!(plan.preview_sha256);
            row["Physical_Timing_Qualified"] = json!(false);
            cursor += planned.variant.frames;
            prepared_rows.push(row);
            trial_total += 1;
        }
        if cursor != block.frames {
            return Err(GenerationError::Invalid("assembly_block_frame_count"));
        }
        writer.finalize().map_err(|_| GenerationError::Io)?;
        sync_file(&root.join(&wav_relative))?;
        let source_hash = write_csv_new(&root.join(&source_relative), &source_rows, cancelled)?;
        for row in &mut prepared_rows {
            row["Source_Block_CSV_Path"] = json!(root
                .join(&source_relative)
                .to_str()
                .ok_or(GenerationError::Invalid("assembly_native_path"))?);
            row["Source_Block_CSV_SHA256"] = json!(source_hash);
        }
        let csv_hash = write_csv_new(&root.join(&csv_relative), &prepared_rows, cancelled)?;
        let wav_hash = hash_file(&root.join(&wav_relative), cancelled)?;
        manifests.push(json!({"index":block.index,"label":block.label,"manifest_path":csv_relative,"wav_path":wav_relative,"trial_count":block.rows.len(),"duration_s":block.frames as f64/f64::from(rate),
            "metadata":{"source_block_csv_path":source_relative,"source_block_csv_sha256":source_hash,"sample_rate_hz":rate,"channels":3,"frames":block.frames,
                "prepared_csv_sha256":csv_hash,"prepared_wav_sha256":wav_hash,"approved_preview_sha256":plan.preview_sha256,"physical_timing_qualified":false}}));
    }
    let manifest = json!({"schema":"pps-run-session.v1","participant_id":participant_id,"session_id":session_id,"session_dir":root,
        "execution_mode":"participant_block_wavs","source_run_setup_manifest_path":setup_path,"source_run_setup_sha256":setup_hash,"blocks":manifests,
        "native_assembly_policy":"verified_pcm_exact_rate_no_hidden_normalization.v1","approved_preview_sha256":plan.preview_sha256,"qualification":"unqualified_exact_verified_assets"});
    let manifest_path = root.join("session_manifest.json");
    write_json_new(&manifest_path, &manifest, cancelled)?;
    check_cancelled(cancelled)?;
    Ok(StagedSession {
        manifest_path,
        preview_sha256: plan.preview_sha256.clone(),
        block_count: manifests.len(),
        trial_count: trial_total,
    })
}

fn compose_trial(
    planned: &PlannedRow,
    assets: &BTreeMap<String, &VerifiedAssemblyAsset>,
    tactile: &VerifiedAssemblyAsset,
    cancelled: &AtomicBool,
) -> Result<Vec<f32>, GenerationError> {
    let mut pcm = crate::zeroed(planned.variant.frames * 3)?;
    let mut cursor = 0;
    for component in &planned.variant.components {
        match component {
            Component::Silence { frames } => cursor += *frames,
            Component::Audio {
                reference,
                frames,
                gain,
                looming,
                baseline,
            } => {
                let mute = planned.family == "baseline"
                    && planned.baseline_mode == "tactile_only"
                    && *looming;
                let selected = if planned.family == "baseline"
                    && planned.baseline_mode == "stationary_burst"
                    && *looming
                {
                    baseline.as_ref().ok_or(GenerationError::Invalid(
                        "assembly_stationary_comparator_required",
                    ))?
                } else {
                    reference
                };
                let asset = assets
                    .get(selected)
                    .ok_or(GenerationError::Invalid("assembly_asset_receipt_missing"))?;
                if !mute {
                    for i in 0..*frames {
                        if i % 4096 == 0 {
                            check_cancelled(cancelled)?;
                        }
                        pcm[(cursor + i) * 3] =
                            (f64::from(asset.pcm[i * asset.channels]) * *gain) as f32;
                        pcm[(cursor + i) * 3 + 1] =
                            (f64::from(asset.pcm[i * asset.channels + asset.channels - 1]) * *gain)
                                as f32;
                    }
                }
                cursor += frames;
            }
        }
    }
    if cursor != planned.variant.frames {
        return Err(GenerationError::Invalid("assembly_trial_frame_count"));
    }
    if let Some(onset) = planned.tactile_onset {
        for (i, sample) in tactile.pcm.iter().enumerate() {
            if i % 4096 == 0 {
                check_cancelled(cancelled)?;
            }
            pcm[(onset + i) * 3 + 2] = *sample;
        }
    }
    Ok(pcm)
}
fn safe_identity(s: &str) -> bool {
    let stem = s.split('.').next().unwrap_or("").to_ascii_uppercase();
    !s.is_empty()
        && s.len() <= 128
        && s != "."
        && s != ".."
        && !s.ends_with('.')
        && s.bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b))
        && !matches!(
            stem.as_str(),
            "CON"
                | "PRN"
                | "AUX"
                | "NUL"
                | "COM1"
                | "COM2"
                | "COM3"
                | "COM4"
                | "COM5"
                | "COM6"
                | "COM7"
                | "COM8"
                | "COM9"
                | "LPT1"
                | "LPT2"
                | "LPT3"
                | "LPT4"
                | "LPT5"
                | "LPT6"
                | "LPT7"
                | "LPT8"
                | "LPT9"
        )
}
fn new_file(path: &std::path::Path) -> Result<std::fs::File, GenerationError> {
    std::fs::OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(path)
        .map_err(|_| GenerationError::Io)
}
fn sync_file(path: &std::path::Path) -> Result<(), GenerationError> {
    std::fs::OpenOptions::new()
        .write(true)
        .open(path)
        .and_then(|f| f.sync_all())
        .map_err(|_| GenerationError::Io)
}
fn write_pcm<W: std::io::Write + std::io::Seek>(
    writer: &mut hound::WavWriter<W>,
    pcm: &[f32],
    cancelled: &AtomicBool,
) -> Result<(), GenerationError> {
    for (i, sample) in pcm.iter().enumerate() {
        if i % 12288 == 0 {
            check_cancelled(cancelled)?;
        }
        writer
            .write_sample(*sample)
            .map_err(|_| GenerationError::Io)?;
    }
    Ok(())
}
fn write_json_new(
    path: &std::path::Path,
    value: &Value,
    cancelled: &AtomicBool,
) -> Result<String, GenerationError> {
    use std::io::Write;
    check_cancelled(cancelled)?;
    let bytes =
        serde_json::to_vec_pretty(value).map_err(|_| GenerationError::Invalid("assembly_json"))?;
    if bytes.len() > 8 * 1024 * 1024 {
        return Err(GenerationError::ResourceLimit);
    }
    let mut file = new_file(path)?;
    for chunk in bytes.chunks(65536) {
        check_cancelled(cancelled)?;
        file.write_all(chunk).map_err(|_| GenerationError::Io)?;
    }
    file.sync_all().map_err(|_| GenerationError::Io)?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}
fn write_csv_new(
    path: &std::path::Path,
    rows: &[Value],
    cancelled: &AtomicBool,
) -> Result<String, GenerationError> {
    let mut columns = BTreeSet::new();
    for row in rows {
        for key in row
            .as_object()
            .ok_or(GenerationError::Invalid("assembly_csv_row"))?
            .keys()
        {
            columns.insert(key.clone());
        }
    }
    if columns.len() > 256 {
        return Err(GenerationError::ResourceLimit);
    }
    let columns: Vec<String> = columns.into_iter().collect();
    let mut writer = csv::Writer::from_writer(new_file(path)?);
    writer
        .write_record(&columns)
        .map_err(|_| GenerationError::Io)?;
    for row in rows {
        check_cancelled(cancelled)?;
        let record: Result<Vec<String>, GenerationError> = columns
            .iter()
            .map(|c| match &row[c] {
                Value::Null => Ok(String::new()),
                Value::String(s) if s.len() <= 16384 => Ok(s.clone()),
                Value::Number(n) => Ok(n.to_string()),
                Value::Bool(b) => Ok(b.to_string()),
                _ => Err(GenerationError::Invalid("assembly_csv_scalar")),
            })
            .collect();
        writer
            .write_record(record?)
            .map_err(|_| GenerationError::Io)?;
    }
    let file = writer.into_inner().map_err(|_| GenerationError::Io)?;
    file.sync_all().map_err(|_| GenerationError::Io)?;
    if file.metadata().map_err(|_| GenerationError::Io)?.len() > 8 * 1024 * 1024 {
        return Err(GenerationError::ResourceLimit);
    }
    drop(file);
    hash_file(path, cancelled)
}
fn hash_file(path: &std::path::Path, cancelled: &AtomicBool) -> Result<String, GenerationError> {
    use std::io::Read;
    let mut file = std::fs::File::open(path).map_err(|_| GenerationError::Io)?;
    let expected = file.metadata().map_err(|_| GenerationError::Io)?.len();
    if expected > MAX_BLOCK_BYTES + 4096 {
        return Err(GenerationError::ResourceLimit);
    }
    let mut hash = Sha256::new();
    let mut buffer = [0_u8; 65536];
    let mut total = 0_u64;
    loop {
        check_cancelled(cancelled)?;
        let n = file.read(&mut buffer).map_err(|_| GenerationError::Io)?;
        if n == 0 {
            break;
        }
        total = total
            .checked_add(n as u64)
            .filter(|n| *n <= expected)
            .ok_or(GenerationError::ResourceLimit)?;
        hash.update(&buffer[..n]);
    }
    if total != expected {
        return Err(GenerationError::Invalid("assembly_file_changed"));
    }
    Ok(format!("{:x}", hash.finalize()))
}
