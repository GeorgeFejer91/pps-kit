use std::{
    io::{self, Read},
    path::PathBuf,
};

use pps_experiment_media::bind_profile_trial_wav;
use pps_runner_audio::{AudioFence, AudioLoadLimits};
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
    frames: Vec<u64>,
    sample_rates: Vec<u32>,
    channels: Vec<u16>,
}

fn check(case: &Case) -> Result<ResultRow, &'static str> {
    let profile = verify_experiment_profile_inventory(&case.profile_path).map_err(|e| e.code())?;
    let plan = select_profile_participant(&profile, &case.participant_id).map_err(|e| e.code())?;
    let block = plan.blocks().first().ok_or("profile_participant_missing")?;
    let fence = AudioFence::new(1, plan.profile_sha256().to_owned(), 1);
    let mut frames = Vec::new();
    let mut sample_rates = Vec::new();
    let mut channels = Vec::new();
    for trial in block.trials() {
        let media = bind_profile_trial_wav(trial, &fence, AudioLoadLimits::default())
            .map_err(|e| e.code())?;
        frames.push(media.frames());
        sample_rates.push(media.sample_rate_hz());
        channels.push(media.channels());
    }
    Ok(ResultRow {
        accepted: true,
        code: "media_bound",
        frames,
        sample_rates,
        channels,
    })
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input)?;
    let input: Input = serde_json::from_str(&input)?;
    let results: Vec<_> = input
        .cases
        .iter()
        .map(|case| {
            check(case).unwrap_or_else(|code| ResultRow {
                accepted: false,
                code,
                frames: Vec::new(),
                sample_rates: Vec::new(),
                channels: Vec::new(),
            })
        })
        .collect();
    serde_json::to_writer(io::stdout().lock(), &results)?;
    Ok(())
}
