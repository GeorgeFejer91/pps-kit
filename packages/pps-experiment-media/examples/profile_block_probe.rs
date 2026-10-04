use std::{
    io::{self, Read},
    path::PathBuf,
};

use pps_experiment_media::block::assemble_standard_profile_block;
use pps_session_package::{
    experiment_plan::select_profile_participant,
    experiment_profile::verify_experiment_profile_inventory,
};
use serde::{Deserialize, Serialize};

#[derive(Deserialize)]
struct Input {
    profile_path: PathBuf,
    participant_id: String,
    output_path: PathBuf,
}

#[derive(Serialize)]
struct ResultRow {
    accepted: bool,
    code: &'static str,
    frames: u64,
    sample_rate_hz: u32,
    channels: u16,
    spans: Vec<[u64; 2]>,
}

fn check(input: &Input) -> Result<ResultRow, &'static str> {
    let profile = verify_experiment_profile_inventory(&input.profile_path).map_err(|e| e.code())?;
    let plan = select_profile_participant(&profile, &input.participant_id).map_err(|e| e.code())?;
    let media =
        assemble_standard_profile_block(&plan, 1, &input.output_path, 1).map_err(|e| e.code())?;
    Ok(ResultRow {
        accepted: true,
        code: "block_assembled",
        frames: media.frames(),
        sample_rate_hz: media.sample_rate_hz(),
        channels: media.channels(),
        spans: media
            .spans()
            .iter()
            .map(|span| [span.start, span.end])
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
        frames: 0,
        sample_rate_hz: 0,
        channels: 0,
        spans: Vec::new(),
    });
    serde_json::to_writer(io::stdout().lock(), &result)?;
    Ok(())
}
