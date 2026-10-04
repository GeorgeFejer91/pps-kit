use std::{
    io::{self, Read},
    path::PathBuf,
};

use pps_session_package::{
    experiment_plan::select_profile_participant,
    experiment_profile::verify_experiment_profile_inventory,
};
use serde::{Deserialize, Serialize};

#[derive(Deserialize)]
struct Input {
    cases: Vec<Case>,
}

#[derive(Deserialize)]
struct Case {
    profile_path: PathBuf,
    participant_id: String,
}

#[derive(Serialize)]
struct ResultRow {
    accepted: bool,
    code: &'static str,
    block_labels: Vec<String>,
    trial_counts: Vec<usize>,
    trial_orders: Vec<Vec<String>>,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input)?;
    let input: Input = serde_json::from_str(&input)?;
    let results: Vec<_> = input
        .cases
        .iter()
        .map(|case| {
            let profile = match verify_experiment_profile_inventory(&case.profile_path) {
                Ok(profile) => profile,
                Err(error) => {
                    return ResultRow {
                        accepted: false,
                        code: error.code(),
                        block_labels: Vec::new(),
                        trial_counts: Vec::new(),
                        trial_orders: Vec::new(),
                    };
                }
            };
            match select_profile_participant(&profile, &case.participant_id) {
                Ok(plan) => ResultRow {
                    accepted: true,
                    code: "selected",
                    block_labels: plan
                        .blocks()
                        .iter()
                        .map(|block| {
                            block
                                .order_fields()
                                .get("block_label")
                                .cloned()
                                .unwrap_or_default()
                        })
                        .collect(),
                    trial_counts: plan
                        .blocks()
                        .iter()
                        .map(|block| block.trials().len())
                        .collect(),
                    trial_orders: plan
                        .blocks()
                        .iter()
                        .map(|block| {
                            block
                                .trials()
                                .iter()
                                .map(|trial| {
                                    trial
                                        .fields()
                                        .get("block_trial_index")
                                        .cloned()
                                        .unwrap_or_default()
                                })
                                .collect()
                        })
                        .collect(),
                },
                Err(error) => ResultRow {
                    accepted: false,
                    code: error.code(),
                    block_labels: Vec::new(),
                    trial_counts: Vec::new(),
                    trial_orders: Vec::new(),
                },
            }
        })
        .collect();
    serde_json::to_writer(io::stdout().lock(), &results)?;
    Ok(())
}
