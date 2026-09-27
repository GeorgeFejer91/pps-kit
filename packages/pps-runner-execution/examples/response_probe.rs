//! Differential oracle adapter; never a production input or IPC endpoint.
use std::{collections::BTreeSet, error::Error, io::Read};

use pps_runner_execution::{
    data_min_row, encode_data_min_csv, score_trial_response, ParticipantResponse,
    TrialResponseWindow, DATA_MIN_FIELDNAMES,
};
use serde::Deserialize;
use serde_json::{json, Map, Value};

#[derive(Deserialize)]
struct Input {
    cases: Vec<Case>,
    projections: Vec<Projection>,
}
#[derive(Deserialize)]
struct Case {
    id: String,
    row: Map<String, Value>,
    window: Window,
    responses: Vec<Response>,
    used: BTreeSet<u64>,
}
#[derive(Deserialize)]
struct Window {
    trial_start_ns: u64,
    response_window_ns: u64,
    tactile_onset_ns: Option<u64>,
    trial_end_ns: u64,
}
#[derive(Deserialize)]
struct Response {
    event_id: u64,
    monotonic_ns: u64,
    block_number: String,
    in_target: bool,
    during_playback: bool,
    choice: String,
    x: Option<f64>,
    y: Option<f64>,
}
#[derive(Deserialize)]
struct Projection {
    row: Map<String, Value>,
    global_index: u64,
}

fn projection(row: &Map<String, Value>, index: u64) -> Value {
    data_min_row(row, index)
        .map(|row| {
            Value::Object(
                DATA_MIN_FIELDNAMES
                    .into_iter()
                    .zip(row.fields())
                    .map(|(key, cell)| (key.into(), Value::String(cell.clone())))
                    .collect(),
            )
        })
        .unwrap_or(Value::Null)
}

fn main() -> Result<(), Box<dyn Error>> {
    let mut input = String::new();
    std::io::stdin().read_to_string(&mut input)?;
    let input: Input = serde_json::from_str(&input)?;
    let mut cases = Vec::new();
    for case in input.cases {
        let responses: Vec<_> = case
            .responses
            .into_iter()
            .map(|response| ParticipantResponse {
                event_id: response.event_id,
                monotonic_ns: response.monotonic_ns,
                block_number: response.block_number,
                in_target: response.in_target,
                during_playback: response.during_playback,
                choice: response.choice,
                x: response.x,
                y: response.y,
            })
            .collect();
        let window = TrialResponseWindow {
            trial_start_ns: case.window.trial_start_ns,
            response_window_ns: case.window.response_window_ns,
            tactile_onset_ns: case.window.tactile_onset_ns,
            trial_end_ns: case.window.trial_end_ns,
        };
        let score = score_trial_response(&case.row, window, &responses, &case.used)?;
        let mut rich = case.row;
        score.apply_to(&mut rich);
        cases.push(json!({"id": case.id, "score": score, "minimal": projection(&rich, 1)}));
    }
    let projections: Vec<_> = input
        .projections
        .iter()
        .map(|entry| projection(&entry.row, entry.global_index))
        .collect();
    let csv_rows: Vec<_> = input
        .projections
        .iter()
        .filter_map(|entry| data_min_row(&entry.row, entry.global_index))
        .collect();
    let csv = String::from_utf8(encode_data_min_csv(&csv_rows, true)?)?;
    serde_json::to_writer(
        std::io::stdout(),
        &json!({"cases": cases, "projections": projections, "csv": csv}),
    )?;
    Ok(())
}
