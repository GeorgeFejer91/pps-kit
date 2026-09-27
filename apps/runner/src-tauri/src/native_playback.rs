//! Native callback ownership and metadata resolution for the execution actor.
//! No command policy, filesystem selection, or second scheduler lives here.

use std::{
    sync::{Arc, Mutex},
    time::Instant,
};

use pps_contracts::{Action, ClockStamp, JSON_MAX_SAFE_INTEGER};
use pps_runner_audio::{OutputFence, PreparedPlaybackPlan, RenderState, RtEventKind};
use pps_runner_audio_cpal::{NativePlaybackRecord, PlaybackPort, PlaybackRecordKind};
use pps_runner_core::NativeBlockSummary;
use pps_runner_execution::{BlockEventSchedule, LedgerEventInput};

use crate::{
    native_output::{NativeOutputSelection, NativeOutputTicket},
    prepared_audio::{PreparedAudioCandidate, PreparedAudioSourceReceipt},
    trial_capture::NativeTrialCapture,
};

pub(crate) struct NativeOutputPreparation {
    pub ticket: NativeOutputTicket,
    pub selection: NativeOutputSelection,
    pub source: Option<NativePlaybackSource>,
}

pub(crate) type NativePlaybackCompletion = (NativePlaybackSource, NativePlaybackHandoff);

#[derive(Clone)]
pub(crate) struct NativePlaybackSource {
    pub receipt: Arc<PreparedAudioSourceReceipt>,
    pub plan: Arc<PreparedPlaybackPlan>,
}

impl NativePlaybackSource {
    pub(crate) fn capture(candidate: &PreparedAudioCandidate) -> Self {
        Self {
            receipt: Arc::clone(candidate.source_receipt()),
            plan: candidate.shared_playback_plan(),
        }
    }

    pub(crate) fn matches(&self, candidate: &PreparedAudioCandidate) -> bool {
        Arc::ptr_eq(&self.receipt, candidate.source_receipt())
            && Arc::ptr_eq(&self.plan, &candidate.shared_playback_plan())
    }

    pub(crate) fn block_summary(&self) -> Result<NativeBlockSummary, &'static str> {
        let schedule = self.receipt.schedule().summary();
        let media = self.plan.media();
        let duration_ns = u128::from(media.frames())
            .checked_mul(1_000_000_000)
            .and_then(|ns| ns.checked_div(u128::from(media.sample_rate_hz())))
            .and_then(|ns| u64::try_from(ns).ok())
            .filter(|ns| *ns > 0 && *ns <= JSON_MAX_SAFE_INTEGER)
            .ok_or("native_block_duration_invalid")?;
        Ok(NativeBlockSummary {
            block_index: u32::try_from(schedule.block_index)
                .ok()
                .filter(|index| *index > 0)
                .ok_or("native_block_index_invalid")?,
            block_ordinal: self.plan.fence().audio().block_ordinal(),
            block_label: schedule.block_label.clone(),
            duration_ns,
        })
    }
}

/// One non-cloneable port survives mailbox-admission retries. A rejected or
/// abandoned completion drops the port and irreversibly silences its callback.
#[derive(Clone)]
pub(crate) struct NativePlaybackHandoff(Arc<Mutex<Option<PlaybackPort>>>);

impl NativePlaybackHandoff {
    pub(crate) fn new(port: PlaybackPort) -> Self {
        Self(Arc::new(Mutex::new(Some(port))))
    }

    pub(crate) fn take(&self) -> Option<PlaybackPort> {
        self.0
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .take()
    }
}

pub(crate) struct NativePreparedPlayback {
    pub source: NativePlaybackSource,
    pub port: PlaybackPort,
    pub capture: NativeTrialCapture,
    pub final_submission_estimate_ns: Option<u64>,
}

/// One native control waits for its durable intent and callback application.
/// No second command queue or scheduler is introduced above the existing port.
pub(crate) struct NativeControlIntent {
    pub action: Action,
    pub ledger_sequence: u64,
    pub callback_sequence: Option<u64>,
    pub requested_at: Instant,
}

impl NativeControlIntent {
    pub(crate) fn new(action: Action, ledger_sequence: u64) -> Self {
        Self {
            action,
            ledger_sequence,
            callback_sequence: None,
            requested_at: Instant::now(),
        }
    }

    pub(crate) fn render_control(&self) -> Result<pps_runner_audio::RenderControl, &'static str> {
        match self.action {
            Action::PartStart => Ok(pps_runner_audio::RenderControl::Start),
            Action::RunPause => Ok(pps_runner_audio::RenderControl::Pause),
            Action::RunResume => Ok(pps_runner_audio::RenderControl::Resume),
            _ => Err("native_control_invalid"),
        }
    }

    pub(crate) fn can_submit(&self, durable_sequence: u64) -> bool {
        self.action == Action::RunPause || durable_sequence >= self.ledger_sequence
    }

    pub(crate) fn acknowledge(&self, input: &LedgerEventInput) -> Result<bool, &'static str> {
        if input.event_type != "audio.control.applied" {
            return Ok(false);
        }
        let sequence = input.payload["controlSequence"]
            .as_str()
            .and_then(|value| value.parse::<u64>().ok())
            .ok_or("native_control_record_invalid")?;
        if Some(sequence) != self.callback_sequence {
            return Err("native_control_record_stale");
        }
        let control = self.render_control()?;
        let state = match self.action {
            Action::RunPause => "Paused",
            _ => "Playing",
        };
        if input.payload["requested"] != format!("{control:?}")
            || input.payload["result"] != "Applied"
            || input.payload["renderState"] != state
        {
            return Err("native_control_rejected");
        }
        Ok(true)
    }
}

impl NativePreparedPlayback {
    pub(crate) fn new(
        source: NativePlaybackSource,
        port: PlaybackPort,
    ) -> Result<Self, &'static str> {
        let status = port.status();
        if status.state != RenderState::Prepared
            || status.fault.is_some()
            || status.callback_retired
        {
            return Err("native_playback_unavailable");
        }
        Ok(Self {
            source,
            port,
            capture: NativeTrialCapture::default(),
            final_submission_estimate_ns: None,
        })
    }

    pub(crate) fn drain(
        &mut self,
        stamp: &ClockStamp,
        host_time: impl Fn(Instant) -> u64,
        resolve_responses: bool,
    ) -> Result<Vec<LedgerEventInput>, &'static str> {
        let status = self.port.status();
        // Prepared callbacks emit no records. Avoid allocating a batch for
        // every idle authority poll, while still observing callback faults.
        if status.state == RenderState::Prepared
            && status.last_control_sequence == 0
            && status.fault.is_none()
        {
            return if status.callback_retired {
                Err("native_playback_retired")
            } else {
                Ok(Vec::new())
            };
        }
        let records = self
            .port
            .drain(126)
            .map_err(|_| "native_playback_unavailable")?;
        let mut inputs = Vec::with_capacity(records.len());
        for record in records {
            if let Some(input) = record_input(
                self.source.receipt.schedule(),
                self.source.plan.fence(),
                record,
                stamp,
                host_time(record.host_received),
            )? {
                if input.event_type == "audio.final-frame-submitted" {
                    self.final_submission_estimate_ns = Some(
                        input.payload["estimatedEventHostMonotonicNs"]
                            .as_u64()
                            .ok_or("native_playback_clock_invalid")?,
                    );
                }
                self.capture.observe(&input)?;
                inputs.push(input);
            }
        }
        if resolve_responses {
            inputs.extend(
                self.capture
                    .resolve_ready(stamp.monotonic_ns, stamp.unix_ms)?,
            );
        }
        Ok(inputs)
    }
}

pub(crate) fn record_input(
    schedule: &BlockEventSchedule,
    fence: &OutputFence,
    record: NativePlaybackRecord,
    stamp: &ClockStamp,
    host_monotonic_ns: u64,
) -> Result<Option<LedgerEventInput>, &'static str> {
    if record.fence != fence.rt_projection() {
        return Err("native_playback_stale_record");
    }
    let mut input = match record.kind {
        PlaybackRecordKind::Boundary(boundary) => {
            if boundary.fence() != record.fence {
                return Err("native_playback_stale_record");
            }
            let (event_type, trigger, payload) = match boundary.kind() {
                RtEventKind::SampleZero => {
                    let anchor = schedule
                        .events()
                        .iter()
                        .find(|event| event.event_type == "audio_sample_zero")
                        .ok_or("native_playback_metadata_missing")?;
                    (
                        anchor.event_type.clone(),
                        Some(anchor.trigger_key.clone()),
                        anchor.payload.clone(),
                    )
                }
                RtEventKind::Scheduled { event_index } => {
                    let event = usize::try_from(event_index)
                        .ok()
                        .and_then(|index| schedule.events().get(index))
                        .ok_or("native_playback_metadata_missing")?;
                    if event.event_type == "audio_sample_zero"
                        || u64::try_from(event.sample_index).ok() != Some(boundary.sample_index())
                    {
                        return Err("native_playback_metadata_mismatch");
                    }
                    (
                        event.event_type.clone(),
                        Some(event.trigger_key.clone()),
                        event.payload.clone(),
                    )
                }
                RtEventKind::FinalFrameSubmitted => (
                    "audio.final-frame-submitted".to_owned(),
                    None,
                    serde_json::json!({}),
                ),
            };
            let mut input = LedgerEventInput::new(event_type, "native-output", stamp.monotonic_ns);
            input.trigger_key = trigger;
            if !payload.is_object() {
                return Err("native_playback_metadata_mismatch");
            }
            input.payload = payload;
            input.payload["callbackSequence"] =
                serde_json::json!(boundary.callback_sequence().to_string());
            input.payload["sourceSampleIndex"] = serde_json::json!(boundary.sample_index());
            input.payload["sampleOffsetInCallback"] =
                serde_json::json!(boundary.sample_offset_in_callback());
            input
        }
        PlaybackRecordKind::Control {
            sequence,
            requested,
            result,
            state,
        } => {
            let mut input =
                LedgerEventInput::new("audio.control.applied", "native-output", stamp.monotonic_ns);
            input.payload = serde_json::json!({
                "controlSequence": sequence.to_string(),
                "requested": format!("{requested:?}"),
                "result": format!("{result:?}"),
                "renderState": format!("{state:?}"),
            });
            input
        }
        PlaybackRecordKind::Render(outcome) => {
            // Per-buffer render counters belong in status, not an unbounded
            // scientific event trail. Retain terminal/fault evidence.
            if matches!(
                outcome.state,
                RenderState::Playing | RenderState::Paused | RenderState::Prepared
            ) && outcome.fault.is_none()
            {
                return Ok(None);
            }
            let mut input =
                LedgerEventInput::new("audio.render.state", "native-output", stamp.monotonic_ns);
            input.payload = serde_json::json!({
                "renderState": format!("{:?}", outcome.state),
                "sourceSubmittedFrames": outcome.cursor_frames,
                "renderFault": outcome.fault.map(|fault| format!("{fault:?}")),
                "completion": "source-submission-only",
            });
            input
        }
    };
    input.unix_ms = Some(stamp.unix_ms);
    input.payload["observedHostMonotonicNs"] =
        serde_json::json!(host_monotonic_ns.min(JSON_MAX_SAFE_INTEGER));
    input.payload["timingQualification"] = serde_json::json!("unqualified");
    input.payload["clockBasis"] = serde_json::json!("host-callback-observation");
    input.payload["driverPredictionLeadNs"] =
        serde_json::json!(record.device_timestamp.and_then(|time| {
            time.playback
                .checked_duration_since(time.callback)
                .and_then(|duration| u64::try_from(duration.as_nanos()).ok())
                .map(|value| value.min(JSON_MAX_SAFE_INTEGER))
        }));
    if let PlaybackRecordKind::Boundary(boundary) = record.kind {
        let rate = u64::try_from(schedule.summary().sample_rate_hz)
            .ok()
            .filter(|rate| *rate > 0)
            .ok_or("native_playback_sample_rate_invalid")?;
        let offset_ns = u64::try_from(
            u128::from(boundary.sample_offset_in_callback()) * 1_000_000_000 / u128::from(rate),
        )
        .map_err(|_| "native_playback_clock_invalid")?;
        let estimate = host_monotonic_ns
            .checked_add(
                input.payload["driverPredictionLeadNs"]
                    .as_u64()
                    .unwrap_or(0),
            )
            .and_then(|ns| ns.checked_add(offset_ns))
            .filter(|ns| *ns <= JSON_MAX_SAFE_INTEGER)
            .ok_or("native_playback_clock_invalid")?;
        input.payload["estimatedEventHostMonotonicNs"] = serde_json::json!(estimate);
        input.payload["eventClockBasis"] =
            serde_json::json!("callback-observation-plus-driver-prediction-and-sample-offset");
    }
    Ok(Some(input))
}

#[cfg(test)]
mod control_tests {
    use super::*;

    #[test]
    fn start_resume_wait_for_durable_intent_but_pause_does_not() {
        for action in [Action::PartStart, Action::RunResume] {
            let intent = NativeControlIntent::new(action, 42);
            assert!(!intent.can_submit(41));
            assert!(intent.can_submit(42));
        }
        assert!(NativeControlIntent::new(Action::RunPause, 42).can_submit(0));
        assert!(NativeControlIntent::new(Action::RunStop, 42)
            .render_control()
            .is_err());
    }

    #[test]
    fn admission_is_not_application_and_only_the_matching_applied_callback_confirms() {
        for (action, requested, state) in [
            (Action::PartStart, "Start", "Playing"),
            (Action::RunPause, "Pause", "Paused"),
            (Action::RunResume, "Resume", "Playing"),
        ] {
            let mut intent = NativeControlIntent::new(action, 10);
            let mut input = LedgerEventInput::new("audio.control.applied", "native-output", 11);
            input.payload = serde_json::json!({"controlSequence": "5", "requested": requested,
                "result": "Applied", "renderState": state});
            assert_eq!(
                intent.acknowledge(&input),
                Err("native_control_record_stale")
            );
            intent.callback_sequence = Some(5);
            assert_eq!(intent.acknowledge(&input), Ok(true));
            input.payload["result"] = serde_json::json!("NoChange");
            assert_eq!(intent.acknowledge(&input), Err("native_control_rejected"));
            input.payload["result"] = serde_json::json!("Applied");
            input.payload["renderState"] = serde_json::json!("Prepared");
            assert_eq!(intent.acknowledge(&input), Err("native_control_rejected"));
            input.event_type = "audio_sample_zero".to_owned();
            assert_eq!(intent.acknowledge(&input), Ok(false));
        }
    }
}
