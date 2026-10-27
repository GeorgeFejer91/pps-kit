//! Narrow replacement of participant_orders.py and dashboard_app._run_setup_preview_rows.
//! The projection is descriptive until assembly binds it to verified PCM and operator acceptance.
use crate::{check_cancelled, GenerationError};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{collections::BTreeSet, sync::atomic::AtomicBool};

pub const MAX_ORDER_BLOCKS: usize = 20;
pub const MAX_PARTICIPANTS: usize = 100;
pub const ORDER_COMPATIBILITY: &str = "cpython-integer-mt19937-getrandbits-shuffle.v1";
pub const FACTORADIC_ALGORITHM: &str = "seeded_factoradic_cycle.v1";

/// Only the integer-seed/getrandbits path used by the established planner.
/// This is separate from the explicitly versioned native audio-source RNG.
struct PythonIntegerRandom(rand_mt::Mt);
impl PythonIntegerRandom {
    fn new(seed: i128) -> Self {
        let mut magnitude = seed.unsigned_abs();
        let mut words = Vec::new();
        loop {
            words.push(magnitude as u32);
            magnitude >>= 32;
            if magnitude == 0 {
                break;
            }
        }
        Self(rand_mt::Mt::new_with_key(words))
    }
    fn below(&mut self, n: usize) -> usize {
        // Python intentionally uses n.bit_length(), including powers of two.
        let bits = usize::BITS - n.leading_zeros();
        loop {
            let value = (self.0.next_u32() >> (32 - bits)) as usize;
            if value < n {
                return value;
            }
        }
    }
    fn shuffle<T>(&mut self, values: &mut [T]) {
        for index in (1..values.len()).rev() {
            let other = self.below(index + 1);
            values.swap(index, other);
        }
    }
}

fn seed(value: &Value) -> Result<i128, GenerationError> {
    value
        .as_i64()
        .map(i128::from)
        .or_else(|| value.as_u64().map(i128::from))
        .ok_or(GenerationError::Invalid("run_order_integer_seed_required"))
}
fn factorial(n: usize) -> u128 {
    (1..=n as u128).product()
}
fn gcd(mut a: u128, mut b: u128) -> u128 {
    while b != 0 {
        (a, b) = (b, a % b);
    }
    a
}
fn unrank(n: usize, mut rank: u128) -> Vec<usize> {
    let mut available: Vec<_> = (0..n).collect();
    (1..=n)
        .rev()
        .map(|remaining| {
            let factor = factorial(remaining - 1);
            let index = (rank / factor) as usize;
            rank %= factor;
            available.remove(index)
        })
        .collect()
}
struct Order {
    indices: Vec<usize>,
    cycle: u128,
    rank: u128,
    algorithm: String,
}
fn participant_order(
    labels: &[String],
    participant: usize,
    policy: &Value,
) -> Result<Order, GenerationError> {
    let algorithm = policy["algorithm"]
        .as_str()
        .filter(|v| !v.is_empty())
        .unwrap_or("counterbalanced_rotation");
    let seed = seed(
        policy
            .get("seed")
            .filter(|v| !v.is_null())
            .unwrap_or(&json!(20250604)),
    )?;
    let space = factorial(labels.len());
    let cycle = (participant - 1) as u128 / space;
    let mut rank = (participant - 1) as u128 % space;
    let mut indices: Vec<_> = (0..labels.len()).collect();
    match algorithm {
        FACTORADIC_ALGORITHM => {
            let digest = Sha256::digest(format!("{seed}|{}|{cycle}", labels.join("|")).as_bytes());
            let mut multiplier = u128::from_be_bytes(digest[..16].try_into().unwrap()) % space;
            if multiplier == 0 {
                multiplier = 1;
            }
            while gcd(multiplier, space) != 1 {
                multiplier = (multiplier + 1) % space;
                if multiplier == 0 {
                    multiplier = 1;
                }
            }
            let offset = u128::from_be_bytes(digest[16..].try_into().unwrap()) % space;
            rank = if space == 1 {
                0
            } else {
                (multiplier * rank + offset) % space
            };
            indices = unrank(labels.len(), rank);
        }
        "fixed" => {}
        "seeded_random_permutation" => {
            PythonIntegerRandom::new(seed + participant as i128 * 7919).shuffle(&mut indices)
        }
        "counterbalanced_rotation" => {
            PythonIntegerRandom::new(seed).shuffle(&mut indices);
            indices.rotate_left((participant - 1) % labels.len());
            if ((participant - 1) / labels.len()) % 2 == 1 {
                indices.reverse();
            }
        }
        _ => return Err(GenerationError::Invalid("run_order_unsupported_algorithm")),
    }
    Ok(Order {
        indices,
        cycle,
        rank,
        algorithm: algorithm.into(),
    })
}
fn legacy_orders(
    n: usize,
    needed: usize,
    seed: i128,
    cancelled: &AtomicBool,
) -> Result<Vec<Vec<usize>>, GenerationError> {
    let mut rng = PythonIntegerRandom::new(seed);
    if n <= 7 {
        let mut orders: Vec<_> = (0..factorial(n)).map(|rank| unrank(n, rank)).collect();
        rng.shuffle(&mut orders);
        orders.truncate(needed);
        return Ok(orders);
    }
    let mut seen = BTreeSet::new();
    let mut orders = Vec::new();
    for _ in 0..(needed * 30).max(200) {
        check_cancelled(cancelled)?;
        if orders.len() == needed {
            break;
        }
        let mut order: Vec<_> = (0..n).collect();
        rng.shuffle(&mut order);
        if seen.insert(order.clone()) {
            orders.push(order);
        }
    }
    while orders.len() < needed {
        let mut order: Vec<_> = (0..n).collect();
        order.rotate_left(orders.len() % n);
        if (orders.len() / n) % 2 == 1 {
            order.reverse();
        }
        orders.push(order);
    }
    Ok(orders)
}
fn nonempty(value: &Value) -> Option<&str> {
    value.as_str().filter(|s| !s.is_empty())
}

/// Complete order projection for review, never a prepared or accepted execution receipt.
/// Segment 5 rows remain untouched; this only orders whole source-block occurrences.
/// Inputs are bounded to 20 blocks, 100 participants and integer seeds. No string/float seed coercion.
pub fn preview_run_order(
    design: &Value,
    source_preview: &Value,
    cancelled: &AtomicBool,
) -> Result<Value, GenerationError> {
    check_cancelled(cancelled)?;
    crate::assembly::design_fingerprint(design)?;
    crate::assembly::design_fingerprint(source_preview)?;
    let blocks = source_preview["blocks"]
        .as_array()
        .ok_or(GenerationError::Invalid("run_order_blocks"))?;
    if blocks.is_empty() || blocks.len() > MAX_ORDER_BLOCKS {
        return Err(GenerationError::ResourceLimit);
    }
    let participants = design["protocol"]
        .get("participants")
        .filter(|v| !v.is_null())
        .unwrap_or(&Value::Null);
    let participants = if participants.is_null() {
        1
    } else {
        participants
            .as_u64()
            .ok_or(GenerationError::Invalid("run_order_participants"))? as usize
    };
    if !(1..=MAX_PARTICIPANTS).contains(&participants) {
        return Err(GenerationError::ResourceLimit);
    }
    let settings = &design["study_profile_reference_parameters"]["dashboard_run_setup"];
    let default_structure = if design["study_profile_id"] == "study5_box_breathing_pps" {
        "pre_post"
    } else {
        "single"
    };
    let structure = nonempty(&settings["experiment_structure"]).unwrap_or(default_structure);
    let phases: &[(&str, &str)] = match structure {
        "single" => &[("single", "Single")],
        "pre_post" => &[("pre", "Condition 1"), ("post", "Condition 2")],
        _ => return Err(GenerationError::Invalid("run_order_structure")),
    };
    let seed_value = settings
        .get("seed")
        .filter(|v| !v.is_null())
        .unwrap_or(&design["protocol"]["random_seed"]);
    let seed = seed(seed_value)?;
    let policy = design["protocol"]
        .get("participant_order_policy")
        .filter(|v| !v.is_null());
    if policy.is_some_and(|p| !p.is_object()) {
        return Err(GenerationError::Invalid("run_order_policy"));
    }
    let policy = policy.filter(|p| !p.as_object().unwrap().is_empty());
    if let Some(schema) = policy.and_then(|p| p.get("schema")) {
        if schema != "pps-participant-order-policy.v1" {
            return Err(GenerationError::Invalid("run_order_policy_schema"));
        }
    }
    let labels: Vec<String> = blocks
        .iter()
        .enumerate()
        .map(|(i, b)| {
            nonempty(&b["block_label"])
                .map(str::to_owned)
                .unwrap_or_else(|| format!("Block {:02}", i + 1))
        })
        .collect();
    let keys: Vec<_> = blocks
        .iter()
        .enumerate()
        .map(|(i, b)| {
            nonempty(&b["csv_file_name"])
                .unwrap_or(&labels[i])
                .to_owned()
        })
        .collect();
    if labels
        .iter()
        .any(|s| s.len() > 1024 || s.chars().any(char::is_control))
        || labels.iter().collect::<BTreeSet<_>>().len() != labels.len()
        || keys.iter().collect::<BTreeSet<_>>().len() != keys.len()
    {
        return Err(GenerationError::Invalid("run_order_ambiguous_blocks"));
    }
    for (i, block) in blocks.iter().enumerate() {
        if block["block_index"].as_u64() != Some(i as u64 + 1)
            || block["trial_count"].as_u64().is_none_or(|n| n == 0)
            || block["duration_ms"].as_u64().is_none()
        {
            return Err(GenerationError::Invalid("run_order_block_metadata"));
        }
    }
    let legacy = if policy.is_none() {
        legacy_orders(blocks.len(), participants * phases.len(), seed, cancelled)?
    } else {
        Vec::new()
    };
    let mut rows = Vec::new();
    let mut csv_rows = Vec::new();
    let mut cursor = 0;
    for participant in 1..=participants {
        check_cancelled(cancelled)?;
        let id = format!("P{participant:03}");
        let generated = policy
            .map(|p| participant_order(&labels, participant, p))
            .transpose()?;
        let mut previous: Option<Vec<usize>> = None;
        for (phase_index, (phase, title)) in phases.iter().enumerate() {
            let (indices, cycle, rank, algorithm) = if let Some(order) = &generated {
                let memberships = &policy.unwrap()["part_membership"];
                if !memberships.is_null() && !memberships.is_object() {
                    return Err(GenerationError::Invalid("run_order_membership"));
                }
                let allowed = memberships
                    .get(*phase)
                    .filter(|v| v.as_array().is_none_or(|a| !a.is_empty()))
                    .or_else(|| {
                        memberships
                            .get((phase_index + 1).to_string())
                            .filter(|v| v.as_array().is_none_or(|a| !a.is_empty()))
                    });
                let indices = if let Some(allowed) = allowed {
                    let allowed = allowed
                        .as_array()
                        .ok_or(GenerationError::Invalid("run_order_membership"))?;
                    let mut set = BTreeSet::new();
                    for label in allowed {
                        let s = label
                            .as_str()
                            .ok_or(GenerationError::Invalid("run_order_membership"))?;
                        if !labels.iter().any(|l| l == s) || !set.insert(s) {
                            return Err(GenerationError::Invalid("run_order_membership"));
                        }
                    }
                    order
                        .indices
                        .iter()
                        .copied()
                        .filter(|i| set.contains(labels[*i].as_str()))
                        .collect()
                } else {
                    order.indices.clone()
                };
                (indices, order.cycle, order.rank, order.algorithm.as_str())
            } else {
                let mut order = legacy[cursor % legacy.len()].clone();
                if *phase == "post" && previous.as_ref() == Some(&order) && legacy.len() > 1 {
                    cursor += 1;
                    order = legacy[cursor % legacy.len()].clone();
                }
                (order, 0, (participant - 1) as u128, "legacy")
            };
            if indices.is_empty() {
                return Err(GenerationError::Invalid("run_order_empty_part"));
            }
            previous = Some(indices.clone());
            cursor += 1;
            rows.push(json!({"participant":id,"participant_index":participant,"part":title,"phase":phase,"phase_index":phase_index+1,"block_count":indices.len(),"block_order":indices.iter().map(|i|keys[*i].clone()).collect::<Vec<_>>().join(" -> "),"cycle_index":cycle as u64,"permutation_index":rank as u64,"order_algorithm":algorithm}));
            for (position, index) in indices.iter().enumerate() {
                let block = &blocks[*index];
                csv_rows.push(json!({"participant_id":id,"participant_index":participant,"experiment_structure":structure,"phase":phase,"phase_label":title,"phase_index":phase_index+1,"participant_block_position":position+1,"source_block_index":index+1,"block_label":labels[*index],"block_csv_file":nonempty(&block["csv_file_name"]).unwrap_or(""),"block_csv_path":nonempty(&block["csv_path"]).unwrap_or(""),"trial_count":block["trial_count"],"duration_ms":block["duration_ms"],"sequence_seed":seed_value,"order_algorithm":algorithm,"cycle_index":cycle as u64,"permutation_index":rank as u64}));
            }
        }
    }
    Ok(
        json!({"schema":"pps-native-run-order-preview.v1","status":"native_review_required","accepted":false,"ready":true,"prepared":false,"experiment_structure":structure,"participant_count":participants,"parts_per_participant":phases.len(),"blocks_per_part":blocks.len(),"total_block_runs":csv_rows.len(),"seed":seed_value,"rows":rows,"csv_rows":csv_rows,"order_compatibility":ORDER_COMPATIBILITY,"instruction_profile":settings["instruction_profile"]}),
    )
}
