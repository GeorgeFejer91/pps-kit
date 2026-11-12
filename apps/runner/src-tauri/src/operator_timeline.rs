use pps_contracts::RunnerSnapshot;
use pps_runner_execution::BlockEventSchedule;
use serde::Serialize;

// Plot at most one marker per time bin per lane. The response count retains
// every accepted input, including inputs that share a display bin.
const TIMELINE_BINS: f64 = 240.0;

#[derive(Clone, Serialize)]
pub(crate) struct OperatorTimeline {
    block_label: String,
    duration_s: f64,
    elapsed_s: f64,
    audio_s: Vec<f64>,
    tactile_s: Vec<f64>,
    response_s: Vec<f64>,
    response_count: u64,
    #[serde(skip)]
    sample_rate_hz: u32,
}

#[derive(Serialize)]
pub(crate) struct OperatorSnapshot {
    #[serde(flatten)]
    pub snapshot: RunnerSnapshot,
    pub operator_timeline: Option<OperatorTimeline>,
}

impl OperatorTimeline {
    pub(crate) fn from_schedule(
        schedule: &BlockEventSchedule,
        total_frames: u64,
        sample_rate_hz: u32,
    ) -> Self {
        let rate = f64::from(sample_rate_hz);
        let duration_s = total_frames as f64 / rate;
        let mut timeline = Self {
            block_label: schedule.summary().block_label.clone(),
            duration_s,
            elapsed_s: 0.0,
            audio_s: Vec::new(),
            tactile_s: Vec::new(),
            response_s: Vec::new(),
            response_count: 0,
            sample_rate_hz,
        };
        for event in schedule.events() {
            let lane = match event.event_type.as_str() {
                "looming_onset" => &mut timeline.audio_s,
                "tactile_onset" => &mut timeline.tactile_s,
                _ => continue,
            };
            let Ok(frame) = u64::try_from(event.sample_index) else {
                continue;
            };
            if frame <= total_frames {
                push_marker(lane, frame as f64 / rate, duration_s);
            }
        }
        timeline
    }

    pub(crate) fn update_cursor(&mut self, submitted_frames: u64) {
        self.elapsed_s =
            (submitted_frames as f64 / f64::from(self.sample_rate_hz)).min(self.duration_s);
    }

    pub(crate) fn record_response(&mut self, submitted_frames: u64) {
        self.update_cursor(submitted_frames);
        self.response_count += 1;
        push_marker(&mut self.response_s, self.elapsed_s, self.duration_s);
    }
}

fn push_marker(lane: &mut Vec<f64>, time: f64, duration: f64) {
    let bin = |offset: f64| {
        (offset / duration * TIMELINE_BINS)
            .floor()
            .min(TIMELINE_BINS - 1.0)
    };
    if lane
        .last()
        .is_none_or(|previous| bin(*previous) < bin(time))
    {
        lane.push(time);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pps_runner_execution::ScheduledBlockEvent;
    use serde_json::{json, Value};

    #[test]
    fn projection_preserves_cue_and_response_positions_without_payloads() {
        let event = |kind: &str, sample| ScheduledBlockEvent {
            event_type: kind.into(),
            sample_index: sample,
            trigger_key: String::new(),
            payload: json!({ "wav_path": "private.wav" }),
        };
        let schedule = BlockEventSchedule::new(vec![
            event("looming_onset", -1),
            event("looming_onset", 100),
            event("tactile_onset", 500),
            event("tactile_onset", 1001),
        ])
        .unwrap();
        let mut timeline = OperatorTimeline::from_schedule(&schedule, 1000, 100);
        timeline.record_response(550);
        timeline.record_response(551);
        timeline.update_cursor(1001);
        let value = serde_json::to_value(&timeline).unwrap();
        assert_eq!(value["audio_s"], json!([1.0]));
        assert_eq!(value["tactile_s"], json!([5.0]));
        assert_eq!(value["response_s"], json!([5.5]));
        assert_eq!(value["response_count"], json!(2));
        assert_eq!(value["elapsed_s"], json!(10.0));
        assert_eq!(value["wav_path"], Value::Null);
    }
}
