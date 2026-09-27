//! Native response acquisition state. The existing callback schedule supplies
//! boundaries; this module does not schedule media or read a browser clock.
use std::collections::{BTreeMap, BTreeSet};

use pps_runner_execution::{
    score_trial_response, LedgerEventInput, ParticipantResponse, TrialResponseWindow,
    MAX_BLOCK_ROWS, MAX_LEDGER_PAYLOAD_BYTES, MAX_TRIAL_RESPONSES,
};
use serde::Deserialize;
use serde_json::{Map, Value};

const MAX_ACTIVE_TRIALS: usize = 64;
const MAX_ROWS_PER_POLL: usize = 2;

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct NativeResponseRequest {
    #[serde(default)]
    pub choice: String,
    pub x: Option<f64>,
    pub y: Option<f64>,
}

impl NativeResponseRequest {
    pub(crate) fn valid(&self) -> bool {
        self.choice.len() <= 512
            && [self.x, self.y]
                .into_iter()
                .flatten()
                .all(|value| value.is_finite() && (0.0..=1.0).contains(&value))
    }
}

#[derive(Default)]
struct Trial {
    row: Map<String, Value>,
    // Start, looming, tactile, response-window, end; no duplicated schedule.
    times: [Option<u64>; 5],
    interrupted: bool,
}

impl Trial {
    fn window(&self) -> Result<TrialResponseWindow, &'static str> {
        let start = self.times[0].ok_or("native_trial_start_missing")?;
        Ok(TrialResponseWindow {
            trial_start_ns: start,
            response_window_ns: self.times[3]
                .or(self.times[1])
                .or(self.times[2])
                .unwrap_or(start),
            tactile_onset_ns: self.times[2],
            trial_end_ns: self.times[4].ok_or("native_trial_end_missing")?,
        })
    }
}

#[derive(Default)]
pub(crate) struct NativeTrialCapture {
    active: BTreeMap<(String, String), Trial>,
    finished: BTreeSet<(String, String)>,
    responses: Vec<ParticipantResponse>,
    used: BTreeSet<u64>,
    last_response_id: u64,
    interrupted: bool,
}

impl NativeTrialCapture {
    pub(crate) fn observe(&mut self, input: &LedgerEventInput) -> Result<(), &'static str> {
        if input.event_type == "audio.control.applied" && input.payload["requested"] == "Pause" {
            // A pause through a trial cannot create a valid reaction time.
            for trial in self.active.values_mut() {
                trial.interrupted = true;
                self.interrupted = true;
            }
            return Ok(());
        }
        let slot = match input.event_type.as_str() {
            "trial_start" => 0,
            "looming_onset" => 1,
            "tactile_onset" => 2,
            "response_window_onset" => 3,
            "trial_end" => 4,
            _ => return Ok(()),
        };
        let row = input
            .payload
            .as_object()
            .ok_or("native_trial_metadata_invalid")?;
        let block = scalar(row.get("block_index")).ok_or("native_trial_metadata_invalid")?;
        let uid = scalar(row.get("trial_uid"))
            .filter(|value| !value.trim().is_empty())
            .or_else(|| scalar(row.get("trial_number")))
            .ok_or("native_trial_metadata_invalid")?;
        let key = (block, uid);
        let onset = row
            .get("estimatedEventHostMonotonicNs")
            .and_then(Value::as_u64)
            .ok_or("native_trial_clock_invalid")?;
        if key.0.len() > 512
            || key.1.len() > 512
            || self.finished.contains(&key)
            || (!self.active.contains_key(&key) && self.active.len() == MAX_ACTIVE_TRIALS)
            || serde_json::to_vec(row)
                .map_err(|_| "native_trial_metadata_invalid")?
                .len()
                > MAX_LEDGER_PAYLOAD_BYTES
        {
            return Err("native_trial_capacity_or_order_invalid");
        }
        let trial = self.active.entry(key).or_default();
        if trial.times[slot].is_some() {
            return Err("native_trial_boundary_repeated");
        }
        trial.times[slot] = Some(onset);
        for (key, value) in row {
            if !value.is_null() && *value != Value::String(String::new()) {
                trial.row.insert(key.clone(), value.clone());
            }
        }
        Ok(())
    }

    pub(crate) fn record_response(
        &mut self,
        response: ParticipantResponse,
    ) -> Result<(), &'static str> {
        if self.responses.len() == MAX_TRIAL_RESPONSES
            || response.event_id <= self.last_response_id
            || response.choice.len() > 512
            || response.block_number.len() > 512
        {
            return Err("native_response_capacity_or_order_invalid");
        }
        self.last_response_id = response.event_id;
        self.responses.push(response);
        Ok(())
    }

    pub(crate) fn resolve_ready(
        &mut self,
        now: u64,
        unix_ms: u64,
    ) -> Result<Vec<LedgerEventInput>, &'static str> {
        let mut ready = Vec::new();
        for (key, trial) in &self.active {
            let Some(end) = trial.times[4] else {
                continue;
            };
            let deadline = trial
                .window()?
                .selection_end_ns()
                .map_err(|_| "native_trial_clock_invalid")?;
            if deadline <= now {
                ready.push((
                    trial.times[0].ok_or("native_trial_start_missing")?,
                    end,
                    key.clone(),
                ));
            }
        }
        ready.sort();
        let mut inputs = Vec::new();
        // ponytail: two rich rows per poll stay under the existing journal's
        // 256 KiB batch bound. Increase only with a measured need and budget.
        for (_, _, key) in ready.into_iter().take(MAX_ROWS_PER_POLL) {
            if self.finished.len() == MAX_BLOCK_ROWS {
                return Err("native_trial_capacity_invalid");
            }
            let mut trial = self
                .active
                .remove(&key)
                .ok_or("native_trial_state_invalid")?;
            let window = trial.window()?;
            let start = window.trial_start_ns;
            let response_window = window.response_window_ns;
            let mut input = LedgerEventInput::new(
                if trial.interrupted {
                    "trial.interrupted"
                } else {
                    "trial.scored"
                },
                "native-participant",
                now,
            );
            input.unix_ms = Some(unix_ms);
            if !trial.interrupted {
                let score = score_trial_response(&trial.row, window, &self.responses, &self.used)
                    .map_err(|_| "native_trial_scoring_invalid")?;
                if let Some(id) = score.response_event_id {
                    self.used.insert(id);
                    trial.row.insert(
                        "response_observed_host_monotonic_ns".into(),
                        serde_json::json!(self
                            .responses
                            .iter()
                            .find(|response| response.event_id == id)
                            .map(|response| response.monotonic_ns)),
                    );
                }
                score.apply_to(&mut trial.row);
            }
            trial
                .row
                .insert("trial_start_monotonic_ns".into(), serde_json::json!(start));
            trial.row.insert(
                "response_window_onset_monotonic_ns".into(),
                serde_json::json!(response_window),
            );
            trial.row.insert(
                "tactile_onset_monotonic_ns".into(),
                serde_json::json!(trial.times[2]),
            );
            trial.row.insert(
                "trial_end_monotonic_ns".into(),
                serde_json::json!(trial.times[4]),
            );
            trial
                .row
                .insert("timingQualification".into(), "unqualified".into());
            trial
                .row
                .insert("inputRoute".into(), "local-webview-native-ingress".into());
            trial
                .row
                .insert("trialInterrupted".into(), trial.interrupted.into());
            input.payload = Value::Object(trial.row);
            self.finished.insert(key);
            inputs.push(input);
        }
        Ok(inputs)
    }

    pub(crate) fn complete(&self, expected_trials: u32) -> bool {
        expected_trials > 0
            && !self.interrupted
            && self.active.is_empty()
            && self.finished.len() == expected_trials as usize
    }
}

fn scalar(value: Option<&Value>) -> Option<String> {
    match value {
        Some(Value::String(value)) => Some(value.clone()),
        Some(Value::Number(value)) => Some(value.to_string()),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn boundary(kind: &str, ns: u64) -> LedgerEventInput {
        let mut input = LedgerEventInput::new(kind, "native-output", ns);
        input.payload = json!({"block_index": 1, "trial_number": 1, "trial_uid": "T1", "trial_type": "Audio-Tactile", "estimatedEventHostMonotonicNs": ns});
        input
    }

    #[test]
    fn native_boundary_clock_waits_for_response_window_and_pause_cannot_score_a_trial() {
        let mut capture = NativeTrialCapture::default();
        for (kind, ns) in [
            ("trial_start", 1_000_000_000),
            ("looming_onset", 2_000_000_000),
            ("tactile_onset", 2_300_000_000),
            ("response_window_onset", 2_000_000_000),
            ("trial_end", 2_500_000_000),
        ] {
            capture.observe(&boundary(kind, ns)).unwrap();
        }
        assert!(capture
            .resolve_ready(3_599_999_999, 100)
            .unwrap()
            .is_empty());
        capture
            .record_response(ParticipantResponse {
                event_id: 10,
                monotonic_ns: 3_600_000_000,
                block_number: "1".into(),
                in_target: true,
                during_playback: true,
                choice: String::new(),
                x: None,
                y: None,
            })
            .unwrap();
        let rows = capture.resolve_ready(3_600_000_000, 100).unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].event_type, "trial.scored");
        assert_eq!(rows[0].payload["outcome"], "Hit");
        assert_eq!(rows[0].payload["rt_ms"], "1300.000");
        assert_eq!(rows[0].payload["timingQualification"], "unqualified");
        assert!(capture.complete(1));
        assert!(!capture.complete(0));
        assert!(!capture.complete(2));
        assert!(capture
            .observe(&boundary("trial_start", 4_000_000_000))
            .is_err());
        assert!(capture
            .record_response(ParticipantResponse {
                event_id: 10,
                monotonic_ns: 4_000_000_000,
                block_number: "1".into(),
                in_target: true,
                during_playback: true,
                choice: String::new(),
                x: None,
                y: None
            })
            .is_err());
        let mut capture = NativeTrialCapture::default();
        capture
            .observe(&boundary("trial_start", 1_000_000_000))
            .unwrap();
        let mut pause =
            LedgerEventInput::new("audio.control.applied", "native-output", 1_000_000_001);
        pause.payload = json!({"requested": "Pause"});
        capture.observe(&pause).unwrap();
        capture
            .observe(&boundary("trial_end", 2_000_000_000))
            .unwrap();
        let rows = capture.resolve_ready(2_000_000_000, 100).unwrap();
        assert_eq!(rows[0].event_type, "trial.interrupted");
        assert!(!capture.complete(1));
        assert!(rows[0].payload.get("outcome").is_none());
        assert!(capture
            .resolve_ready(3_000_000_000, 100)
            .unwrap()
            .is_empty());
        assert!(!NativeResponseRequest {
            choice: "x".repeat(513),
            x: None,
            y: None
        }
        .valid());
        let mut capture = NativeTrialCapture::default();
        for (kind, ns) in [
            ("trial_start", 1_000_000_000),
            ("response_window_onset", 2_000_000_000),
            ("trial_end", 2_000_000_000),
        ] {
            let mut input = boundary(kind, ns);
            input.payload["trial_type"] = "Auditory-Only".into();
            capture.observe(&input).unwrap();
        }
        assert!(capture
            .resolve_ready(3_299_999_999, 100)
            .unwrap()
            .is_empty());
        capture
            .record_response(ParticipantResponse {
                event_id: 1,
                monotonic_ns: 3_300_000_000,
                block_number: "1".into(),
                in_target: true,
                during_playback: true,
                choice: String::new(),
                x: None,
                y: None,
            })
            .unwrap();
        let rows = capture.resolve_ready(3_300_000_000, 100).unwrap();
        assert_eq!(rows[0].payload["outcome"], "Hit");
        assert_eq!(rows[0].payload["rt_ms"], "1300.000");
        assert!(serde_json::from_value::<NativeResponseRequest>(
            json!({"choice": "left", "monotonicNs": 123})
        )
        .is_err());
        assert!(!NativeResponseRequest {
            choice: String::new(),
            x: Some(f64::NAN),
            y: None
        }
        .valid());
    }
}
