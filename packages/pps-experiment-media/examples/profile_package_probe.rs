use std::{
    io::{self, Read},
    path::PathBuf,
};

use pps_experiment_media::package::prepare_standard_profile_package;
use pps_session_package::experiment_profile::verify_experiment_profile_inventory;
use serde::{Deserialize, Serialize};

#[derive(Deserialize)]
struct Input {
    profile_path: PathBuf,
    participant_id: String,
    output_dir: PathBuf,
}

#[derive(Serialize)]
struct ResultRow {
    accepted: bool,
    code: &'static str,
    block_count: usize,
    trial_counts: Vec<i64>,
}

fn check(input: &Input) -> Result<ResultRow, &'static str> {
    let profile =
        verify_experiment_profile_inventory(&input.profile_path).map_err(|error| error.code())?;
    let package =
        prepare_standard_profile_package(&profile, &input.participant_id, &input.output_dir, 1)
            .map_err(|error| error.code())?;
    Ok(ResultRow {
        accepted: true,
        code: "package_prepared",
        block_count: package.blocks().len(),
        trial_counts: package
            .summary()
            .blocks
            .iter()
            .map(|block| block.trial_count)
            .collect(),
    })
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input)?;
    let input: Input = serde_json::from_str(&input)?;
    let result = check(&input).unwrap_or_else(|code| ResultRow {
        accepted: false,
        code,
        block_count: 0,
        trial_counts: Vec::new(),
    });
    serde_json::to_writer(io::stdout().lock(), &result)?;
    Ok(())
}
