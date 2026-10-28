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
    strip: Value,
}
#[derive(Debug, Clone)]
struct PlannedRow {
    row: Value,
    variant: Variant,
    family: String,
    baseline_mode: String,
    tactile_onset: Option<usize>,
    iti_frames: usize,
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
                // Round the signed offset independently of the sound onset, as for
                // positive SOAs. Negative offsets may use existing pre-sound frames.
                let offset = sample_index(soa.abs(), rate);
                let onset = if soa < 0.0 {
                    variant
                        .looming
                        .checked_sub(offset)
                        .ok_or(GenerationError::Invalid("assembly_tactile_outside_trial"))?
                } else {
                    variant
                        .looming
                        .checked_add(offset)
                        .ok_or(GenerationError::ResourceLimit)?
                };
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
            let mut enriched = crate::row_contract::merge(&variant.strip, row, family)?;
            let iti_ms = match enriched
                .get("iti_ms")
                .filter(|v| !v.is_null() && v.as_str() != Some(""))
            {
                None => 0.0,
                Some(value) => value
                    .as_f64()
                    .or_else(|| value.as_str().and_then(|s| s.trim().parse::<f64>().ok()))
                    .filter(|ms| ms.is_finite() && *ms >= 0.0)
                    .ok_or(GenerationError::Invalid("assembly_iti_ms"))?,
            };
            let iti_frames = sample_index(iti_ms / 1000.0, rate);
            let session_frames = variant
                .frames
                .checked_add(iti_frames)
                .filter(|n| *n <= MAX_FRAMES)
                .ok_or(GenerationError::ResourceLimit)?;
            enriched["native_iti_frames"] = json!(iti_frames);
            enriched["native_session_duration_ms"] = json!(milliseconds(session_frames, rate));
            enriched["duration_ms"] = json!(milliseconds(variant.frames, rate));
            enriched["duration_s"] = json!(variant.frames as f64 / f64::from(rate));
            enriched["sample_rate_hz"] = json!(rate);
            enriched["frames"] = json!(variant.frames);
            enriched["looming_segment_onset_s"] = json!(variant.looming as f64 / f64::from(rate));
            enriched["tactile_onset_s"] = tactile_onset
                .map(|v| json!(v as f64 / f64::from(rate)))
                .unwrap_or(json!(""));
            let actual_tactile_duration_ms = json!(if tactile_onset.is_some() {
                milliseconds(tactile.frames(), rate)
            } else {
                0
            });
            // A reported source contract is distinct from the actual shared
            // cue used by this explicitly unqualified native preparation.
            if enriched
                .get("tactile_duration_ms")
                .is_none_or(|v| v.is_null() || v.as_str() == Some(""))
            {
                enriched["tactile_duration_ms"] = actual_tactile_duration_ms.clone();
            }
            enriched["native_tactile_duration_ms"] = actual_tactile_duration_ms;
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
                .checked_add(session_frames)
                .ok_or(GenerationError::ResourceLimit)?;
            planned.push(PlannedRow {
                row: enriched,
                variant,
                family: family.into(),
                baseline_mode,
                tactile_onset,
                iti_frames,
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
                        || comparator.sha256 == asset.sha256
                        || source
                            .get("native_stationary_baseline_sha256")
                            .is_some_and(|sha| sha.as_str() != Some(comparator.sha256.as_str()))
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
                    strip: (**strip).clone(),
                },
            )
            .is_some()
        {
            return Err(GenerationError::Invalid("assembly_ambiguous_variant"));
        }
    }
    Ok(result)
}

/// Native receipt binding the full participant occurrence list and instruction
/// assets to the exact enriched source-block preview. No Deserialize.
#[derive(Debug, Serialize)]
pub struct RunOrderPreview {
    pub design_sha256: String,
    pub assembly_preview_sha256: String,
    pub run_order_sha256: String,
    pub preview: Value,
    #[serde(skip_serializing)]
    sealed_digest: String,
}

/// Both reviews travel together; neither browser `accepted` flags nor a saved
/// order JSON can manufacture this receipt.
#[derive(Debug)]
pub struct AcceptedParticipantAssembly {
    source: AcceptedAssemblyPlan,
    order: Value,
    order_sha256: String,
}
impl AcceptedParticipantAssembly {
    pub fn revision(&self) -> u64 {
        self.source.revision
    }
    pub fn design_sha256(&self) -> &str {
        &self.source.design_sha256
    }
    pub fn assembly_preview_sha256(&self) -> &str {
        &self.source.preview_sha256
    }
    pub fn run_order_sha256(&self) -> &str {
        &self.order_sha256
    }
}

pub fn plan_run_order_preview(
    source: &AssemblyPreview,
    assets: &[VerifiedAssemblyAsset],
    cancelled: &AtomicBool,
) -> Result<RunOrderPreview, GenerationError> {
    check_cancelled(cancelled)?;
    if hash_json(&source.preview)? != source.recipe.preview_digest
        || source.preview_sha256 != source.recipe.preview_digest
        || hash_json(&source.recipe.design)? != source.design_sha256
    {
        return Err(GenerationError::Invalid("assembly_preview_stale"));
    }
    verify_asset_hashes(&source.recipe, assets)?;
    let mut preview =
        crate::run_order::preview_run_order(&source.recipe.design, &source.preview, cancelled)?;
    preview["instruction_profile"] =
        verified_instruction_profile(&source.recipe.design, assets, source.recipe.sample_rate)?;
    preview["design_sha256"] = json!(source.design_sha256);
    preview["assembly_preview_sha256"] = json!(source.preview_sha256);
    preview["physical_timing_qualified"] = json!(false);
    let digest = hash_json(&preview)?;
    Ok(RunOrderPreview {
        design_sha256: source.design_sha256.clone(),
        assembly_preview_sha256: source.preview_sha256.clone(),
        run_order_sha256: digest.clone(),
        preview,
        sealed_digest: digest,
    })
}

pub fn accept_participant_assembly(
    source: AssemblyPreview,
    mut order: RunOrderPreview,
    expected_design_sha256: &str,
    expected_assembly_preview_sha256: &str,
    expected_run_order_sha256: &str,
    revision: u64,
) -> Result<AcceptedParticipantAssembly, GenerationError> {
    if order.design_sha256 != expected_design_sha256
        || order.assembly_preview_sha256 != expected_assembly_preview_sha256
        || order.run_order_sha256 != expected_run_order_sha256
        || order.sealed_digest != order.run_order_sha256
        || hash_json(&order.preview)? != order.sealed_digest
        || order.preview["design_sha256"] != expected_design_sha256
        || order.preview["assembly_preview_sha256"] != expected_assembly_preview_sha256
    {
        return Err(GenerationError::Invalid("assembly_run_order_stale"));
    }
    let source = accept_assembly_preview(
        source,
        expected_design_sha256,
        expected_assembly_preview_sha256,
        revision,
    )?;
    order.preview["accepted"] = json!(true);
    Ok(AcceptedParticipantAssembly {
        source,
        order: order.preview,
        order_sha256: order.run_order_sha256,
    })
}

fn verify_asset_hashes(
    recipe: &Recipe,
    assets: &[VerifiedAssemblyAsset],
) -> Result<(), GenerationError> {
    let mut seen = BTreeSet::new();
    if assets.len() != recipe.asset_hashes.len()
        || assets.iter().any(|a| {
            !seen.insert(&a.reference) || recipe.asset_hashes.get(&a.reference) != Some(&a.sha256)
        })
    {
        return Err(GenerationError::Invalid("assembly_assets_changed"));
    }
    Ok(())
}

fn verified_instruction_profile(
    design: &Value,
    assets: &[VerifiedAssemblyAsset],
    rate: u32,
) -> Result<Value, GenerationError> {
    let slots = [
        (
            "before_experiment",
            "Before experiment",
            "General instructions",
            "General_Instructions.wav",
            "click",
            "Start experiment",
        ),
        (
            "before_each_block",
            "Before each block",
            "Pre-block instruction",
            "Pre-Block_Instruction.wav",
            "delay",
            "Start block",
        ),
        (
            "after_each_block",
            "After each block",
            "Post-block instruction",
            "Post-Block_Instruction.wav",
            "click",
            "Next block",
        ),
        (
            "between_conditions",
            "Between conditions",
            "Condition transition",
            "InterimMessage.wav",
            "button",
            "Start next condition",
        ),
        (
            "after_experiment",
            "After experiment",
            "Finish message",
            "FinishMessage.wav",
            "delay",
            "Finish",
        ),
    ];
    let study5 = design["study_profile_id"] == "study5_box_breathing_pps";
    let raw =
        &design["study_profile_reference_parameters"]["dashboard_run_setup"]["instruction_profile"];
    let mut incoming = BTreeMap::new();
    let values: Vec<_> = match &raw["slots"] {
        Value::Null => Vec::new(),
        Value::Array(a) => a.iter().collect(),
        Value::Object(o) => o.values().collect(),
        _ => return Err(GenerationError::Invalid("assembly_instruction_slots")),
    };
    if values.len() > slots.len() {
        return Err(GenerationError::Invalid("assembly_instruction_slots"));
    }
    for value in values {
        let slot = string(&value["slot"])?;
        if !slots.iter().any(|s| s.0 == slot) || incoming.insert(slot, value).is_some() {
            return Err(GenerationError::Invalid("assembly_instruction_slots"));
        }
    }
    let mut output = Vec::new();
    for (slot, generic_label, study_label, file, mode, button) in slots {
        let item = incoming.get(slot).copied().unwrap_or(&Value::Null);
        let enabled = item
            .get("enabled")
            .map(|v| {
                v.as_bool()
                    .ok_or(GenerationError::Invalid("assembly_instruction_enabled"))
            })
            .transpose()?
            .unwrap_or(study5);
        let default_path = if study5 {
            format!("assets/breathing/original_study5/{file}")
        } else {
            String::new()
        };
        let path = item["path"].as_str().unwrap_or(&default_path);
        let label = item["label"]
            .as_str()
            .filter(|v| !v.is_empty())
            .unwrap_or(if study5 { study_label } else { generic_label });
        let mode = item["continue_mode"]
            .as_str()
            .filter(|v| !v.is_empty())
            .unwrap_or(if study5 { mode } else { "click" })
            .trim()
            .to_lowercase();
        if !["click", "delay", "button"].contains(&mode.as_str()) {
            return Err(GenerationError::Invalid(
                "assembly_instruction_continue_mode",
            ));
        }
        let delay = item
            .get("delay_s")
            .map(finite_number)
            .transpose()?
            .unwrap_or(0.0);
        if !(0.0..=3600.0).contains(&delay) {
            return Err(GenerationError::Invalid("assembly_instruction_delay"));
        }
        let button = item["button_label"]
            .as_str()
            .map(str::trim)
            .filter(|v| !v.is_empty())
            .unwrap_or(if study5 { button } else { "Continue" });
        if [label, button, path]
            .iter()
            .any(|s| s.len() > 4096 || s.chars().any(char::is_control))
        {
            return Err(GenerationError::Invalid("assembly_instruction_text"));
        }
        let mut resolved = json!({"slot":slot,"label":label,"enabled":enabled,"required":false,"path":"","duration_s":0.0,"sample_rate":0,"channels":0,"sha256":"","continue_mode":mode,"delay_s":delay,"button_label":button,"source":item["source"].as_str().unwrap_or(if study5 { "original_study5" } else { "" })});
        if enabled {
            let asset =
                assets
                    .iter()
                    .find(|a| a.reference == path)
                    .ok_or(GenerationError::Invalid(
                        "assembly_instruction_asset_required",
                    ))?;
            if asset.role != AssemblyAssetRole::Instruction {
                return Err(GenerationError::Invalid("assembly_instruction_asset_role"));
            }
            if asset.rate != rate {
                return Err(GenerationError::Invalid("assembly_component_rate_mismatch"));
            }
            if item["sha256"]
                .as_str()
                .is_some_and(|h| !h.is_empty() && h != asset.sha256)
            {
                return Err(GenerationError::Invalid("assembly_instruction_sha256"));
            }
            resolved["path"] = json!(path);
            resolved["duration_s"] = json!(asset.frames() as f64 / f64::from(rate));
            resolved["sample_rate"] = json!(rate);
            resolved["channels"] = json!(asset.channels);
            resolved["sha256"] = json!(asset.sha256);
            resolved["native_pcm_policy"] = json!("verified_source_samples_no_level_change.v1");
        }
        output.push(resolved);
    }
    Ok(json!({"schema":"pps-run-instructions.v1","slots":output}))
}

#[derive(Debug)]
pub struct StagedParticipantSession {
    group_manifest_path: Option<std::path::PathBuf>,
    parts: Vec<StagedSession>,
}
impl StagedParticipantSession {
    pub fn group_manifest_path(&self) -> Option<&std::path::Path> {
        self.group_manifest_path.as_deref()
    }
    pub fn parts(&self) -> &[StagedSession] {
        &self.parts
    }
}

struct PartWriteContext {
    group_id: String,
    number: usize,
    phase: String,
    phase_label: String,
    global_start: usize,
    source_blocks: Vec<usize>,
    siblings: Vec<std::path::PathBuf>,
    order: Value,
    order_sha256: String,
    split: bool,
    shared_setup: Option<(std::path::PathBuf, String)>,
}

pub fn prepare_accepted_participant(
    plan: &AcceptedParticipantAssembly,
    assets: &[VerifiedAssemblyAsset],
    tactile: &VerifiedAssemblyAsset,
    private_output_dir: &std::path::Path,
    participant_index: usize,
    session_group_id: &str,
    cancelled: &AtomicBool,
) -> Result<StagedParticipantSession, GenerationError> {
    check_cancelled(cancelled)?;
    verify_asset_hashes(&plan.source.recipe, assets)?;
    if !safe_identity(session_group_id) {
        return Err(GenerationError::Invalid("assembly_session_identity"));
    }
    let occurrences = plan.order["csv_rows"]
        .as_array()
        .ok_or(GenerationError::Invalid("assembly_run_order_rows"))?;
    let selected: Vec<_> = occurrences
        .iter()
        .filter(|r| r["participant_index"].as_u64() == Some(participant_index as u64))
        .collect();
    if participant_index == 0 || selected.is_empty() {
        return Err(GenerationError::Invalid("assembly_participant_selection"));
    }
    // Bound the entire selected participant, including repeated phase occurrences.
    let bytes = selected.iter().try_fold(0_u64, |total, row| {
        let index = integer(&row["source_block_index"])?;
        let block = plan
            .source
            .recipe
            .blocks
            .get(index - 1)
            .ok_or(GenerationError::Invalid("assembly_run_order_block"))?;
        total
            .checked_add(block.frames as u64 * 12)
            .ok_or(GenerationError::ResourceLimit)
    })?;
    if bytes > MAX_PACKAGE_BYTES {
        return Err(GenerationError::ResourceLimit);
    }
    let split = plan.order["experiment_structure"] == "pre_post";
    let count = if split { 2 } else { 1 };
    let participant_id = format!("P{participant_index:03}");
    let root = if split {
        new_output_directory(private_output_dir)?
    } else {
        private_output_dir.to_owned()
    };
    let shared_setup = if split {
        let path = root.join("run_setup_manifest.json");
        let digest = write_json_new(
            &path,
            &json!({"schema":"pps-native-run-setup.v1","participant_id":participant_id,"session_group_id":session_group_id,
            "design_revision":plan.source.revision,"design_sha256":plan.source.design_sha256,"approved_preview_sha256":plan.source.preview_sha256,
            "approved_run_order_sha256":plan.order_sha256,"approved_segment5":plan.source.preview,"approved_segment6":plan.order,
            "design":plan.source.recipe.design,"assets":plan.source.recipe.asset_hashes,"tactile_asset_sha256":tactile.sha256,
            "assembly_policy":"verified_pcm_exact_rate_no_hidden_normalization.v1","physical_timing_qualified":false,"replication_qualified":false}),
            cancelled,
        )?;
        Some((path, digest))
    } else {
        None
    };
    let paths: Vec<_> = (1..=count)
        .map(|number| {
            if split {
                root.join(format!("part_{number:02}"))
                    .join("session_manifest.json")
            } else {
                root.join("session_manifest.json")
            }
        })
        .collect();
    let mut parts = Vec::new();
    let mut entries = Vec::new();
    let mut global_start = 0;
    for number in 1..=count {
        check_cancelled(cancelled)?;
        let rows: Vec<_> = selected
            .iter()
            .filter(|r| r["phase_index"].as_u64() == Some(number as u64))
            .collect();
        if rows.is_empty() {
            return Err(GenerationError::Invalid("assembly_run_order_empty_part"));
        }
        let source_blocks: Vec<_> = rows
            .iter()
            .map(|r| integer(&r["source_block_index"]))
            .collect::<Result<_, _>>()?;
        let phase = string(&rows[0]["phase"])?.to_owned();
        let phase_label = string(&rows[0]["phase_label"])?.to_owned();
        let context = PartWriteContext {
            group_id: session_group_id.into(),
            number,
            phase,
            phase_label,
            global_start,
            source_blocks,
            siblings: paths
                .iter()
                .enumerate()
                .filter(|(i, _)| *i + 1 != number)
                .map(|(_, p)| p.clone())
                .collect(),
            order: plan.order.clone(),
            order_sha256: plan.order_sha256.clone(),
            split,
            shared_setup: shared_setup.clone(),
        };
        let id = if split {
            format!("{session_group_id}_part_{number:02}")
        } else {
            session_group_id.into()
        };
        let path = paths[number - 1].parent().unwrap();
        let part = write_session(
            &plan.source,
            assets,
            tactile,
            path,
            &participant_id,
            &id,
            cancelled,
            Some(&context),
        )?;
        global_start += part.block_count;
        entries.push(json!({"part_number":number,"part_label":context.phase_label,"part_session_id":id,"part_folder_name":format!("part_{number:02}"),"session_manifest_path":part.manifest_path,"session_dir":path,"block_count":part.block_count,"completed":false,"completion_message":"not_started","part_completion_status_path":path.join("part_completion_status.json")}));
        parts.push(part);
    }
    let group_manifest_path = if split {
        let path = root.join("session_group_manifest.json");
        write_json_new(
            &path,
            &json!({"schema":"pps-run-session-group.v1","part_split_schema":"pps-runner-part-split.v1","session_group_id":session_group_id,"participant_id":participant_id,
            "experiment_structure":"pre_post","parts_per_participant":parts.len(),"parts":entries,"approved_run_order_sha256":plan.order_sha256,
            "source_run_setup_manifest_path":shared_setup.as_ref().unwrap().0,"source_run_setup_sha256":shared_setup.as_ref().unwrap().1,
            "full_experiment_completed":false,"physical_timing_qualified":false}),
            cancelled,
        )?;
        Some(path)
    } else {
        None
    };
    check_cancelled(cancelled)?;
    Ok(StagedParticipantSession {
        group_manifest_path,
        parts,
    })
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
    write_session(
        plan,
        assets,
        tactile,
        private_output_dir,
        participant_id,
        session_id,
        cancelled,
        None,
    )
}

#[allow(clippy::too_many_arguments)]
fn write_session(
    plan: &AcceptedAssemblyPlan,
    assets: &[VerifiedAssemblyAsset],
    tactile: &VerifiedAssemblyAsset,
    private_output_dir: &std::path::Path,
    participant_id: &str,
    session_id: &str,
    cancelled: &AtomicBool,
    part: Option<&PartWriteContext>,
) -> Result<StagedSession, GenerationError> {
    use std::{fs, io::BufWriter};
    check_cancelled(cancelled)?;
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
    let root = new_output_directory(private_output_dir)?;
    for directory in ["blocks", "sources", "trials"] {
        fs::create_dir(root.join(directory)).map_err(|_| GenerationError::Io)?;
    }
    let mut setup = json!({"schema":"pps-native-run-setup.v1","participant_id":participant_id,"session_id":session_id,"design_revision":plan.revision,
        "design_sha256":plan.design_sha256,"approved_preview_sha256":plan.preview_sha256,"approved_segment5":plan.preview,
        "design":plan.recipe.design,"assets":plan.recipe.asset_hashes,"tactile_asset_sha256":tactile.sha256,
        "assembly_policy":"verified_pcm_exact_rate_no_hidden_normalization.v1","physical_timing_qualified":false,"replication_qualified":false});
    let instruction_profile = if let Some(part) = part {
        setup["approved_segment6"] = part.order.clone();
        setup["approved_run_order_sha256"] = json!(part.order_sha256);
        materialize_instruction_assets(
            &part.order["instruction_profile"],
            &root,
            &asset_map,
            cancelled,
        )?
    } else {
        json!({"schema":"pps-run-instructions.v1","slots":[]})
    };
    let (setup_path, setup_hash) = if let Some(shared) = part.and_then(|p| p.shared_setup.as_ref())
    {
        shared.clone()
    } else {
        let path = root.join("run_setup_manifest.json");
        let digest = write_json_new(&path, &setup, cancelled)?;
        (path, digest)
    };
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
    let block_order: Vec<_> = part
        .map(|p| p.source_blocks.clone())
        .unwrap_or_else(|| (1..=plan.recipe.blocks.len()).collect());
    for (position, source_index) in block_order.iter().enumerate() {
        check_cancelled(cancelled)?;
        let block = &plan.recipe.blocks[*source_index - 1];
        let block_number = position + 1;
        let stem = format!("block_{block_number:03}");
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
            // V1 appends the explicit saved per-row ITI to the prepared block,
            // while retaining the source trial WAV's original duration/hash.
            let silence = [0.0f32; 3072];
            let mut remaining = planned.iti_frames * 3;
            while remaining > 0 {
                let count = remaining.min(silence.len());
                write_pcm(&mut writer, &silence[..count], cancelled)?;
                remaining -= count;
            }
            let duration_frames = planned.variant.frames + planned.iti_frames;
            let mut source = planned.row.clone();
            source["trial_file_path"] = json!(format!("../{trial_relative}"));
            source["source_sha256"] = json!(trial_hash);
            source["source_file_name"] = json!(trial_relative.rsplit('/').next().unwrap());
            source_rows.push(source.clone());
            let mut row = source;
            row["Participant_ID"] = json!(participant_id);
            row["Session_ID"] = json!(session_id);
            row["Block_Number"] = json!(block_number);
            row["Block_Label"] = json!(block.label);
            row["Trial_Number"] = json!(ordinal + 1);
            row["Trial_UID"] = json!(format!(
                "{participant_id}_{session_id}_B{:03}_T{:05}",
                block_number,
                ordinal + 1
            ));
            if let Some(part) = part {
                if part.split {
                    row["Session_Group_ID"] = json!(part.group_id);
                    row["Part_Session_ID"] = json!(session_id);
                }
                row["Part_Number"] = json!(part.number);
                row["Part_Block_Number"] = json!(block_number);
                row["Global_Block_Index"] = json!(part.global_start + block_number);
                row["Phase"] = json!(part.phase);
                row["Phase_Label"] = json!(part.phase_label);
                row["Participant_Block_Position"] = json!(block_number);
                row["Source_Block_Index"] = json!(block.index);
                row["Source_Block_Label"] = json!(block.label);
                row["Block_Label"] = json!(format!("Block {block_number:02}"));
                row["Native_Approved_Run_Order_SHA256"] = json!(part.order_sha256);
            }
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
            row["Trial_Duration_S"] = json!(duration_frames as f64 / f64::from(rate));
            row["Trial_Start_Sample"] = json!(cursor);
            row["Trial_Start_S"] = json!(cursor as f64 / f64::from(rate));
            row["Trial_End_Sample"] = json!(cursor + duration_frames);
            row["Trial_End_S"] = json!((cursor + duration_frames) as f64 / f64::from(rate));
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
            cursor += duration_frames;
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
        let mut block_manifest = json!({"index":block_number,"label":block.label,"manifest_path":csv_relative,"wav_path":wav_relative,"trial_count":block.rows.len(),"duration_s":block.frames as f64/f64::from(rate),
            "metadata":{"source_block_csv_path":root.join(&source_relative),"source_block_csv_sha256":source_hash,"sample_rate_hz":rate,"channels":3,"frames":block.frames,
                "prepared_csv_sha256":csv_hash,"prepared_wav_sha256":wav_hash,"approved_preview_sha256":plan.preview_sha256,"physical_timing_qualified":false}});
        if let Some(part) = part {
            let metadata = &mut block_manifest["metadata"];
            if part.split {
                metadata["session_group_id"] = json!(part.group_id);
                metadata["part_session_id"] = json!(session_id);
            }
            metadata["part_number"] = json!(part.number);
            metadata["part_block_number"] = json!(block_number);
            metadata["global_block_index"] = json!(part.global_start + block_number);
            metadata["phase"] = json!(part.phase);
            metadata["phase_label"] = json!(part.phase_label);
            metadata["participant_block_position"] = json!(block_number);
            metadata["source_block_index"] = json!(block.index);
            metadata["source_block_label"] = json!(block.label);
        }
        manifests.push(block_manifest);
    }
    let mut manifest = json!({"schema":"pps-run-session.v1","participant_id":participant_id,"session_id":session_id,"session_dir":root,
        "execution_mode":"participant_block_wavs","source_run_setup_manifest_path":setup_path,"source_run_setup_sha256":setup_hash,"blocks":manifests,
        "instruction_profile":instruction_profile,"native_assembly_policy":"verified_pcm_exact_rate_no_hidden_normalization.v1","approved_preview_sha256":plan.preview_sha256,"qualification":"unqualified_exact_verified_assets"});
    if let Some(part) = part {
        if part.split {
            manifest["session_group_id"] = json!(part.group_id);
            manifest["part_number"] = json!(part.number);
            manifest["part_session_id"] = json!(session_id);
            manifest["part_folder_name"] = json!(format!("part_{:02}", part.number));
            manifest["part_split_schema"] = json!("pps-runner-part-split.v1");
            manifest["sibling_part_manifest_paths"] = json!(part.siblings);
        }
        manifest["approved_run_order_sha256"] = json!(part.order_sha256);
        manifest["full_experiment_completed"] = json!(false);
    }
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

fn new_output_directory(path: &std::path::Path) -> Result<std::path::PathBuf, GenerationError> {
    let parent = path
        .parent()
        .ok_or(GenerationError::Invalid("assembly_output_parent"))?
        .canonicalize()
        .map_err(|_| GenerationError::Io)?;
    let name = path
        .file_name()
        .and_then(|n| n.to_str())
        .filter(|n| safe_identity(n))
        .ok_or(GenerationError::Invalid("assembly_output_name"))?;
    let root = parent.join(name);
    std::fs::create_dir(&root)
        .map_err(|_| GenerationError::Invalid("assembly_output_must_be_new"))?;
    Ok(root)
}

fn materialize_instruction_assets(
    profile: &Value,
    root: &std::path::Path,
    assets: &BTreeMap<String, &VerifiedAssemblyAsset>,
    cancelled: &AtomicBool,
) -> Result<Value, GenerationError> {
    let mut result = profile.clone();
    for slot in result["slots"]
        .as_array_mut()
        .ok_or(GenerationError::Invalid("assembly_instruction_slots"))?
    {
        if slot["enabled"] != true {
            continue;
        }
        check_cancelled(cancelled)?;
        let asset = assets
            .get(string(&slot["path"])?)
            .ok_or(GenerationError::Invalid(
                "assembly_instruction_asset_required",
            ))?;
        let directory = root.join("instructions");
        if !directory.exists() {
            std::fs::create_dir(&directory).map_err(|_| GenerationError::Io)?;
        }
        let path = directory.join(format!("{}.wav", string(&slot["slot"])?));
        let mut writer = hound::WavWriter::new(
            std::io::BufWriter::new(new_file(&path)?),
            hound::WavSpec {
                channels: asset.channels as u16,
                sample_rate: asset.rate,
                bits_per_sample: 32,
                sample_format: hound::SampleFormat::Float,
            },
        )
        .map_err(|_| GenerationError::Io)?;
        write_pcm(&mut writer, &asset.pcm, cancelled)?;
        writer.finalize().map_err(|_| GenerationError::Io)?;
        sync_file(&path)?;
        slot["source_asset_sha256"] = json!(asset.sha256);
        slot["path"] = json!(path);
        slot["sha256"] = json!(hash_file(&path, cancelled)?);
    }
    Ok(result)
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
fn csv_cell(column: &str, value: &Value) -> Result<String, GenerationError> {
    let text = match value {
        Value::Null => String::new(),
        Value::String(s) if s.len() <= 16384 => s.clone(),
        Value::Number(n) => n.to_string(),
        Value::Bool(b) => b.to_string(),
        Value::Array(values)
            if crate::row_contract::ROW_CONTRACT_FIELDS.contains(&column)
                && values.len() <= 1024
                && values.iter().all(|value| {
                    matches!(
                        value,
                        Value::Null | Value::Bool(_) | Value::Number(_) | Value::String(_)
                    )
                }) =>
        {
            // Preserve the existing typed contract as one escaped CSV cell.
            // Only flat scalar arrays of known contract fields are supported;
            // arbitrary objects/nested structures cannot enter schedule rows.
            serde_json::to_string(values)
                .map_err(|_| GenerationError::Invalid("assembly_csv_scalar"))?
        }
        _ => return Err(GenerationError::Invalid("assembly_csv_scalar")),
    };
    if text.len() > 16384 {
        return Err(GenerationError::Invalid("assembly_csv_scalar"));
    }
    Ok(text)
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
        let record: Result<Vec<String>, GenerationError> =
            columns.iter().map(|c| csv_cell(c, &row[c])).collect();
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

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        cell::Cell,
        io::{Cursor, Seek, SeekFrom, Write},
        sync::atomic::Ordering,
    };

    #[test]
    fn csv_contract_arrays_roundtrip_but_objects_and_unknown_structures_fail() {
        let value = json!([1, 2, "left,right", false, null]);
        let cell = csv_cell("speaker_switch_channels", &value).unwrap();
        assert_eq!(serde_json::from_str::<Value>(&cell).unwrap(), value);
        let mut writer = csv::Writer::from_writer(Vec::new());
        writer.write_record(["speaker_switch_channels"]).unwrap();
        writer.write_record([cell]).unwrap();
        let bytes = writer.into_inner().unwrap();
        let mut reader = csv::Reader::from_reader(bytes.as_slice());
        assert_eq!(
            serde_json::from_str::<Value>(&reader.records().next().unwrap().unwrap()[0]).unwrap(),
            value
        );
        for (column, value) in [
            ("unknown_metadata", json!([1, 2])),
            ("speaker_switch_channels", json!({"path":"untrusted"})),
            ("speaker_switch_channels", json!([{"path":"untrusted"}])),
            ("speaker_switch_channels", json!([[1, 2]])),
            ("speaker_switch_channels", json!(vec![0; 1025])),
            ("speaker_switch_channels", json!(["x".repeat(16384)])),
        ] {
            assert_eq!(
                csv_cell(column, &value),
                Err(GenerationError::Invalid("assembly_csv_scalar"))
            );
        }
    }

    #[test]
    fn cancellation_after_pcm_write_returns_error_with_only_a_strict_prefix() {
        struct CancelOnWrite<'a> {
            bytes: Cursor<Vec<u8>>,
            armed: &'a Cell<bool>,
            cancelled: &'a AtomicBool,
        }
        impl Write for CancelOnWrite<'_> {
            fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
                let written = self.bytes.write(bytes)?;
                if written > 0 && self.armed.get() {
                    self.cancelled.store(true, Ordering::Release);
                }
                Ok(written)
            }
            fn flush(&mut self) -> std::io::Result<()> {
                self.bytes.flush()
            }
        }
        impl Seek for CancelOnWrite<'_> {
            fn seek(&mut self, position: SeekFrom) -> std::io::Result<u64> {
                self.bytes.seek(position)
            }
        }

        let cancelled = AtomicBool::new(false);
        let armed = Cell::new(false);
        let mut sink = CancelOnWrite {
            bytes: Cursor::new(Vec::new()),
            armed: &armed,
            cancelled: &cancelled,
        };
        let mut writer = hound::WavWriter::new(
            &mut sink,
            hound::WavSpec {
                channels: 1,
                sample_rate: 8000,
                bits_per_sample: 32,
                sample_format: hound::SampleFormat::Float,
            },
        )
        .unwrap();
        // Cancel on a real PCM write, after header construction. This exercises
        // the existing writer boundary without depending on disk or CPU speed.
        armed.set(true);
        let pcm = vec![0.25_f32; 32768];
        assert_eq!(
            write_pcm(&mut writer, &pcm, &cancelled),
            Err(GenerationError::Cancelled)
        );
        armed.set(false);
        drop(writer);
        let mut partial = hound::WavReader::new(Cursor::new(sink.bytes.into_inner())).unwrap();
        assert!(partial.duration() > 0);
        assert!((partial.duration() as usize) < pcm.len());
        assert!(partial
            .samples::<f32>()
            .all(|sample| sample.unwrap() == 0.25));
    }
}
