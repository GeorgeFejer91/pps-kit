use std::{error::Error, io::Read, path::PathBuf};

use pps_runner_execution::{compile_block_schedule, BlockScheduleOptions, ScheduledBlockEvent};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

#[derive(Debug, Deserialize)]
struct ProbeInput {
    cases: Vec<ProbeCase>,
}

#[derive(Debug, Deserialize)]
struct ProbeCase {
    id: String,
    manifest_path: PathBuf,
    block_index: i64,
    block_label: String,
    block_wav_path: PathBuf,
    participant_id: String,
    session_id: String,
    part_number: Value,
    sample_rate: i64,
    block_metadata: Map<String, Value>,
    trial_duration_s: f64,
    stimulus_segment_onset_s: f64,
    buffers: Vec<BufferQuery>,
}

#[derive(Debug, Deserialize)]
struct BufferQuery {
    start_sample: i64,
    frame_count: i64,
}

#[derive(Debug, Serialize)]
struct ProbeOutput {
    cases: Vec<ProbeResult>,
}

#[derive(Debug, Serialize)]
struct ProbeResult {
    id: String,
    events: Vec<ScheduledBlockEvent>,
    buffers: Vec<Vec<ScheduledBlockEvent>>,
}

fn main() -> Result<(), Box<dyn Error>> {
    let mut input_json = String::new();
    std::io::stdin().read_to_string(&mut input_json)?;
    let input: ProbeInput = serde_json::from_str(&input_json)?;
    let mut results = Vec::with_capacity(input.cases.len());

    for case in input.cases {
        let options = BlockScheduleOptions {
            block_index: case.block_index,
            block_label: case.block_label,
            block_wav_path: Some(case.block_wav_path),
            participant_id: case.participant_id,
            session_id: case.session_id,
            part_number: case.part_number,
            sample_rate: case.sample_rate,
            block_metadata: case.block_metadata,
            trial_duration_s: case.trial_duration_s,
            stimulus_segment_onset_s: case.stimulus_segment_onset_s,
        };
        let mut schedule = compile_block_schedule(&case.manifest_path, options)?;
        let events = schedule.events().to_vec();
        let buffers = case
            .buffers
            .iter()
            .map(|query| {
                schedule
                    .consume_buffer(query.start_sample, query.frame_count)
                    .to_vec()
            })
            .collect();
        results.push(ProbeResult {
            id: case.id,
            events,
            buffers,
        });
    }

    serde_json::to_writer(std::io::stdout(), &ProbeOutput { cases: results })?;
    Ok(())
}
