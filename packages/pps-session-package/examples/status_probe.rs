use std::io::{self, Read};
use std::path::PathBuf;

use pps_session_package::{verify_prepared_session, VerificationRequest};
use serde::{Deserialize, Serialize};

#[derive(Debug, Deserialize)]
struct ProbeInput {
    cases: Vec<ProbeCase>,
}

#[derive(Debug, Deserialize)]
struct ProbeCase {
    id: String,
    manifest_path: PathBuf,
    #[serde(default)]
    run_setup_manifest_path: Option<PathBuf>,
    #[serde(default)]
    participant_id: Option<String>,
}

#[derive(Debug, Serialize)]
struct ProbeOutput {
    cases: Vec<ProbeResult>,
}

#[derive(Debug, Serialize)]
struct ProbeResult {
    id: String,
    current: bool,
    message: String,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input)?;
    let input: ProbeInput = serde_json::from_str(&input)?;

    let cases = input
        .cases
        .into_iter()
        .map(|case| {
            let mut request = VerificationRequest::new(&case.manifest_path);
            if let Some(run_setup_manifest_path) = &case.run_setup_manifest_path {
                request = request.with_run_setup(run_setup_manifest_path);
            }
            if let Some(participant_id) = &case.participant_id {
                request = request.with_participant_id(participant_id);
            }

            match verify_prepared_session(request) {
                Ok(verified) => ProbeResult {
                    id: case.id,
                    current: true,
                    message: verified.v1_message().to_owned(),
                },
                Err(error) => ProbeResult {
                    id: case.id,
                    current: false,
                    message: error.to_string(),
                },
            }
        })
        .collect();

    serde_json::to_writer(io::stdout().lock(), &ProbeOutput { cases })?;
    Ok(())
}
