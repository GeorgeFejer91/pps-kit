use std::sync::Arc;

use pps_runner_audio::{
    bind_and_decode_verified_wav, AudioFence, AudioLoadLimits, AudioPreparationError, OutputGains,
    OutputPlanError, OutputRouteRequest, PpsChannelLayout, PreparedPcmBlock, PreparedPlaybackPlan,
    ResolvedOutputRouteKind, RtScheduledEvent, VerifiedWavRequest, DEFAULT_MAXIMUM_DECODED_BYTES,
};
use pps_runner_execution::BlockEventSchedule;
use pps_session_package::{VerifiedPreparedSession, VerifiedPreparedWav};
use serde::Serialize;

pub(crate) const PREPARED_AUDIO_CACHE_CAPACITY_BLOCKS: u8 = 1;
pub(crate) const MAXIMUM_CACHED_DECODED_BYTES: u64 = DEFAULT_MAXIMUM_DECODED_BYTES;

/// Native-only snapshot captured by the authority actor before decoding.
///
/// It deliberately does not implement `Serialize` or `Debug`: the shared
/// verified-session receipt contains local paths and content digests. The
/// blocking decoder may own this value, but only the authority actor may later
/// accept its result.
pub(crate) struct PreparedAudioSourceReceipt {
    preparation_generation: u64,
    fence: AudioFence,
    run_generation: u64,
    verified_session: Arc<VerifiedPreparedSession>,
    schedule: Arc<BlockEventSchedule>,
}

pub(crate) struct PreparedAudioSource {
    receipt: Arc<PreparedAudioSourceReceipt>,
}

/// Actor decision for a local preload request. Cache hits return only the
/// existing path-free summary; misses hand one fenced source to the blocking
/// decoder. No caller can request a filesystem path or bypass the actor.
pub(crate) enum PreparedAudioLookup {
    Cached(PreparedAudioSummary),
    Decode(PreparedAudioSource),
}

impl PreparedAudioSourceReceipt {
    pub(crate) fn new(
        preparation_generation: u64,
        fence: AudioFence,
        run_generation: u64,
        verified_session: Arc<VerifiedPreparedSession>,
        schedule: Arc<BlockEventSchedule>,
    ) -> Self {
        Self {
            preparation_generation,
            fence,
            run_generation,
            verified_session,
            schedule,
        }
    }

    pub(crate) const fn preparation_generation(&self) -> u64 {
        self.preparation_generation
    }

    pub(crate) fn fence(&self) -> &AudioFence {
        &self.fence
    }

    pub(crate) const fn run_generation(&self) -> u64 {
        self.run_generation
    }

    pub(crate) fn verified_session(&self) -> &Arc<VerifiedPreparedSession> {
        &self.verified_session
    }

    pub(crate) fn wav_receipt(&self) -> Option<&VerifiedPreparedWav> {
        usize::try_from(self.fence.block_ordinal())
            .ok()
            .and_then(|ordinal| self.verified_session.blocks().get(ordinal))
            .map(|block| block.block_wav())
    }

    pub(crate) fn schedule(&self) -> &Arc<BlockEventSchedule> {
        &self.schedule
    }
}

impl PreparedAudioSource {
    pub(crate) fn new(receipt: Arc<PreparedAudioSourceReceipt>) -> Self {
        Self { receipt }
    }
}

/// Decoded candidate returned from the blocking worker to the authority actor.
///
/// The exact selection-time receipt is carried back so the actor can compare
/// it with its current package rather than trusting worker-supplied summary
/// fields. This type is native-only and intentionally non-serializable.
pub(crate) struct PreparedAudioCandidate {
    receipt: Arc<PreparedAudioSourceReceipt>,
    playback_plan: PreparedPlaybackPlan,
}

impl PreparedAudioCandidate {
    pub(crate) fn source_receipt(&self) -> &Arc<PreparedAudioSourceReceipt> {
        &self.receipt
    }

    pub(crate) fn run_generation(&self) -> u64 {
        self.receipt.run_generation()
    }

    pub(crate) fn verified_session(&self) -> &Arc<VerifiedPreparedSession> {
        self.receipt.verified_session()
    }

    pub(crate) fn wav_receipt(&self) -> Option<&VerifiedPreparedWav> {
        self.receipt.wav_receipt()
    }

    pub(crate) fn schedule(&self) -> &Arc<BlockEventSchedule> {
        self.receipt.schedule()
    }

    pub(crate) fn media(&self) -> &PreparedPcmBlock {
        self.playback_plan.media()
    }

    pub(crate) fn playback_plan(&self) -> &PreparedPlaybackPlan {
        &self.playback_plan
    }

    pub(crate) fn decoded_bytes(&self) -> Result<u64, PreparedAudioError> {
        u64::try_from(self.media().interleaved_f32().len())
            .ok()
            .and_then(|samples| samples.checked_mul(size_of::<f32>() as u64))
            .ok_or_else(PreparedAudioError::resource_limit)
    }

    pub(crate) fn summary(&self) -> Result<PreparedAudioSummary, PreparedAudioError> {
        Ok(PreparedAudioSummary {
            schema: "pps-runner-prepared-audio-summary.v1",
            preparation_scope: "pcm-and-output-plan-cache",
            output_qualification: "unqualified",
            executable: false,
            output_plan_prepared: true,
            output_route: output_route_name(self.playback_plan.route().kind()),
            scheduled_event_count: u32::try_from(self.playback_plan.scheduled_events().len())
                .map_err(|_| PreparedAudioError::schedule_overflow())?,
            block_ordinal: self.media().fence().block_ordinal(),
            sample_rate_hz: self.media().sample_rate_hz(),
            source_channels: self.media().channels(),
            source_channel_layout: match self.media().layout() {
                PpsChannelLayout::LegacyStudy5TactileAudio => "legacy-study5-tactile-audio",
                PpsChannelLayout::BinauralLeftRightTactile => "binaural-left-right-tactile",
            },
            frames: self.media().frames(),
            decoded_bytes: self.decoded_bytes()?,
            cache_capacity_blocks: PREPARED_AUDIO_CACHE_CAPACITY_BLOCKS,
            cache_byte_budget: MAXIMUM_CACHED_DECODED_BYTES,
        })
    }
}

/// Explicit path-free projection for the local bundled WebView.
///
/// This reports only media shape, compact renderer-plan facts, and
/// qualification state. It contains no PCM, event payload, path, digest,
/// package identity, participant identity, or run generation.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct PreparedAudioSummary {
    pub schema: &'static str,
    pub preparation_scope: &'static str,
    pub output_qualification: &'static str,
    pub executable: bool,
    pub output_plan_prepared: bool,
    pub output_route: &'static str,
    pub scheduled_event_count: u32,
    pub block_ordinal: u32,
    pub sample_rate_hz: u32,
    pub source_channels: u16,
    pub source_channel_layout: &'static str,
    pub frames: u64,
    pub decoded_bytes: u64,
    pub cache_capacity_blocks: u8,
    pub cache_byte_budget: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct PreparedAudioError {
    code: &'static str,
    public_message: &'static str,
}

impl PreparedAudioError {
    const fn new(code: &'static str, public_message: &'static str) -> Self {
        Self {
            code,
            public_message,
        }
    }

    pub(crate) const fn code(&self) -> &'static str {
        self.code
    }

    pub(crate) const fn public_message(&self) -> &'static str {
        self.public_message
    }

    pub(crate) const fn resource_limit() -> Self {
        Self::new(
            "prepared_audio_resource_limit",
            "The prepared audio exceeds the native preload resource limit.",
        )
    }

    const fn sample_rate_invalid() -> Self {
        Self::new(
            "prepared_audio_sample_rate_invalid",
            "The prepared schedule does not provide a supported audio sample rate.",
        )
    }

    const fn schedule_overflow() -> Self {
        Self::new(
            "prepared_audio_schedule_overflow",
            "The prepared schedule exceeds the native output-plan limits.",
        )
    }

    const fn event_outside_media() -> Self {
        Self::new(
            "prepared_audio_schedule_outside_media",
            "A prepared schedule event falls outside the verified audio block.",
        )
    }

    const fn sample_zero_anchor_invalid() -> Self {
        Self::new(
            "prepared_audio_sample_zero_anchor_invalid",
            "The prepared schedule does not contain exactly one valid audio sample-zero anchor.",
        )
    }

    const fn output_plan_limit() -> Self {
        Self::new(
            "prepared_audio_output_plan_limit",
            "The prepared schedule exceeds the bounded native callback limits.",
        )
    }

    const fn output_plan_unsupported() -> Self {
        Self::new(
            "prepared_audio_output_plan_unsupported",
            "The verified audio and schedule cannot form a native output plan.",
        )
    }

    fn from_preparation(error: AudioPreparationError) -> Self {
        match error {
            AudioPreparationError::EncodedByteCountMismatch
            | AudioPreparationError::DigestMismatch => Self::new(
                "prepared_audio_changed",
                "The prepared audio changed after package verification; select the package again.",
            ),
            AudioPreparationError::EncodedBytesTooLarge { .. }
            | AudioPreparationError::FrameLimitExceeded { .. }
            | AudioPreparationError::DecodedBytesTooLarge { .. }
            | AudioPreparationError::DecodedAllocationFailed
            | AudioPreparationError::DecodedShapeOverflow
            | AudioPreparationError::DeclaredDataExceedsFile => Self::resource_limit(),
            AudioPreparationError::UnsupportedSampleFormat
            | AudioPreparationError::UnsupportedBitsPerSample
            | AudioPreparationError::UnsupportedChannelCount
            | AudioPreparationError::SampleRateMismatch => Self::new(
                "prepared_audio_format_unsupported",
                "The prepared audio format does not match the native Runner contract.",
            ),
            AudioPreparationError::Open(_)
            | AudioPreparationError::Inspect(_)
            | AudioPreparationError::Malformed(_)
            | AudioPreparationError::InvalidExpectedDigest
            | AudioPreparationError::InvalidLimits => Self::new(
                "prepared_audio_unavailable",
                "The prepared audio could not be loaded by the native Runner.",
            ),
        }
    }

    fn from_output_plan(error: OutputPlanError) -> Self {
        match error {
            OutputPlanError::EventBeyondEnd { .. } => Self::event_outside_media(),
            OutputPlanError::EventBurstLimitExceeded { .. }
            | OutputPlanError::EventDensityLimitExceeded { .. } => Self::output_plan_limit(),
            OutputPlanError::Route(_)
            | OutputPlanError::InvalidGain
            | OutputPlanError::EmptyMedia
            | OutputPlanError::PreparedMediaShape
            | OutputPlanError::EventOrder => Self::output_plan_unsupported(),
        }
    }
}

/// Decode one captured block outside the actor. Acceptance remains a separate
/// actor operation and must revalidate every fence and receipt.
pub(crate) fn prepare_verified_audio(
    source: PreparedAudioSource,
) -> Result<PreparedAudioCandidate, PreparedAudioError> {
    prepare_verified_audio_with_limits(source, AudioLoadLimits::default())
}

fn prepare_verified_audio_with_limits(
    source: PreparedAudioSource,
    mut limits: AudioLoadLimits,
) -> Result<PreparedAudioCandidate, PreparedAudioError> {
    let receipt = source.receipt;
    let schedule_sample_rate_hz =
        checked_schedule_sample_rate_hz(receipt.schedule().summary().sample_rate_hz)?;
    let wav_receipt = receipt
        .wav_receipt()
        .ok_or_else(PreparedAudioError::output_plan_unsupported)?;
    limits.maximum_decoded_bytes = limits
        .maximum_decoded_bytes
        .min(MAXIMUM_CACHED_DECODED_BYTES);
    let media = bind_and_decode_verified_wav(VerifiedWavRequest {
        fence: receipt.fence(),
        path: wav_receipt.path(),
        expected_sha256: wav_receipt.sha256(),
        expected_encoded_byte_count: wav_receipt.encoded_byte_count(),
        expected_sample_rate_hz: schedule_sample_rate_hz,
        limits,
    })
    .map_err(PreparedAudioError::from_preparation)?;
    if media.sample_rate_hz() != schedule_sample_rate_hz {
        return Err(PreparedAudioError::sample_rate_invalid());
    }
    let scheduled_events = project_schedule_events(receipt.schedule(), media.frames())?;
    let route = match media.layout() {
        PpsChannelLayout::LegacyStudy5TactileAudio => OutputRouteRequest::legacy_stereo(),
        PpsChannelLayout::BinauralLeftRightTactile => OutputRouteRequest::canonical_three(),
    };
    let playback_plan = PreparedPlaybackPlan::new(
        media,
        receipt.run_generation(),
        route,
        OutputGains::unity(),
        scheduled_events,
    )
    .map_err(PreparedAudioError::from_output_plan)?;
    Ok(PreparedAudioCandidate {
        receipt,
        playback_plan,
    })
}

fn checked_schedule_sample_rate_hz(value: i64) -> Result<u32, PreparedAudioError> {
    u32::try_from(value)
        .ok()
        .filter(|rate| *rate > 0)
        .ok_or_else(PreparedAudioError::sample_rate_invalid)
}

fn project_schedule_events(
    schedule: &BlockEventSchedule,
    total_frames: u64,
) -> Result<Box<[RtScheduledEvent]>, PreparedAudioError> {
    const AUDIO_SAMPLE_ZERO: &str = "audio_sample_zero";

    let sample_zero_anchor_count = schedule
        .events()
        .iter()
        .filter(|event| event.event_type == AUDIO_SAMPLE_ZERO)
        .count();
    if sample_zero_anchor_count != 1
        || schedule
            .events()
            .iter()
            .any(|event| event.event_type == AUDIO_SAMPLE_ZERO && event.sample_index != 0)
    {
        return Err(PreparedAudioError::sample_zero_anchor_invalid());
    }
    let retained_count = schedule
        .events()
        .iter()
        .filter(|event| event.event_type != AUDIO_SAMPLE_ZERO && event.sample_index >= 0)
        .count();
    let mut projected = Vec::new();
    projected
        .try_reserve_exact(retained_count)
        .map_err(|_| PreparedAudioError::resource_limit())?;
    for (original_index, event) in schedule.events().iter().enumerate() {
        // The compiled anchor is retained as metadata but deliberately omitted
        // here. The renderer-owned `RtEventKind::SampleZero` is the one
        // authoritative callback-placement boundary; its future non-real-time
        // owner maps it to canonical audio-zero evidence. Every other projected
        // event keeps its index into this original sorted schedule.
        if event.event_type == AUDIO_SAMPLE_ZERO {
            continue;
        }
        if event.sample_index < 0 {
            continue;
        }
        let event_index = checked_event_index(original_index)?;
        let sample_index = u64::try_from(event.sample_index)
            .map_err(|_| PreparedAudioError::schedule_overflow())?;
        if sample_index > total_frames {
            return Err(PreparedAudioError::event_outside_media());
        }
        projected.push(RtScheduledEvent::new(event_index, sample_index));
    }
    Ok(projected.into_boxed_slice())
}

fn checked_event_index(value: usize) -> Result<u32, PreparedAudioError> {
    u32::try_from(value).map_err(|_| PreparedAudioError::schedule_overflow())
}

const fn output_route_name(route: ResolvedOutputRouteKind) -> &'static str {
    match route {
        ResolvedOutputRouteKind::LegacyStereo => "legacy-stereo",
        ResolvedOutputRouteKind::CanonicalThree => "canonical-three",
        ResolvedOutputRouteKind::CanonicalFourWithTactileMirror => {
            "canonical-four-with-tactile-mirror"
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pps_runner_execution::{compile_block_schedule, BlockScheduleOptions, ScheduledBlockEvent};
    use pps_session_package::{verify_prepared_session, VerificationRequest};
    use serde_json::json;
    use std::{
        fs,
        path::PathBuf,
        sync::atomic::{AtomicU64, Ordering},
    };

    static NEXT_FIXTURE: AtomicU64 = AtomicU64::new(1);

    fn wav_bytes(sample_rate_hz: u32, frames: u32, channels: u16) -> Vec<u8> {
        let data_bytes = frames * u32::from(channels) * 2;
        let mut bytes = Vec::with_capacity(44 + data_bytes as usize);
        bytes.extend_from_slice(b"RIFF");
        bytes.extend_from_slice(&(36 + data_bytes).to_le_bytes());
        bytes.extend_from_slice(b"WAVEfmt ");
        bytes.extend_from_slice(&16_u32.to_le_bytes());
        bytes.extend_from_slice(&1_u16.to_le_bytes());
        bytes.extend_from_slice(&channels.to_le_bytes());
        bytes.extend_from_slice(&sample_rate_hz.to_le_bytes());
        bytes.extend_from_slice(&(sample_rate_hz * u32::from(channels) * 2).to_le_bytes());
        bytes.extend_from_slice(&(channels * 2).to_le_bytes());
        bytes.extend_from_slice(&16_u16.to_le_bytes());
        bytes.extend_from_slice(b"data");
        bytes.extend_from_slice(&data_bytes.to_le_bytes());
        bytes.resize(44 + data_bytes as usize, 0);
        bytes
    }

    fn source() -> (PathBuf, PreparedAudioSource) {
        source_with_channels(2)
    }

    fn source_with_channels(channels: u16) -> (PathBuf, PreparedAudioSource) {
        let root = std::env::temp_dir().join(format!(
            "pps-prepared-audio-tauri-{}-{}",
            std::process::id(),
            NEXT_FIXTURE.fetch_add(1, Ordering::Relaxed)
        ));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        fs::write(root.join("block.wav"), wav_bytes(48_000, 2, channels)).unwrap();
        fs::write(
            root.join("block.csv"),
            b"Trial_Number,Trial_UID,Trial_Type,Family,Sample_Rate_Hz,Trial_Start_Sample,Trial_End_Sample\n1,T1,Other,other,48000,0,2\n",
        )
        .unwrap();
        let manifest_path = root.join("run-session.json");
        fs::write(
            &manifest_path,
            serde_json::to_vec(&serde_json::json!({
                "schema": "pps-run-session.v1",
                "participant_id": "P001",
                "session_id": "session_audio_test",
                "session_group_id": "group_audio_test",
                "part_number": 1,
                "part_session_id": "part_audio_test",
                "session_dir": root,
                "execution_mode": "design_schedule_blocks",
                "blocks": [{
                    "index": 1,
                    "label": "Block",
                    "manifest_path": "block.csv",
                    "wav_path": "block.wav",
                    "trial_count": 1,
                    "duration_s": 1.0,
                    "metadata": {"sample_rate_hz": 48000}
                }]
            }))
            .unwrap(),
        )
        .unwrap();
        let receipt =
            Arc::new(verify_prepared_session(VerificationRequest::new(&manifest_path)).unwrap());
        let fence = AudioFence::new(4, receipt.manifest_sha256(), 0);
        let mut options = BlockScheduleOptions::new(1);
        options.sample_rate = 48_000;
        let schedule = Arc::new(compile_block_schedule(&root.join("block.csv"), options).unwrap());
        let source_receipt = Arc::new(PreparedAudioSourceReceipt::new(
            11, fence, 8, receipt, schedule,
        ));
        (root, PreparedAudioSource::new(source_receipt))
    }

    fn event(event_type: &str, sample_index: i64, trigger_key: &str) -> ScheduledBlockEvent {
        ScheduledBlockEvent {
            event_type: event_type.to_owned(),
            sample_index,
            trigger_key: trigger_key.to_owned(),
            payload: json!({"private_path": "C:/private/participant.csv"}),
        }
    }

    fn with_schedule(
        source: PreparedAudioSource,
        schedule: BlockEventSchedule,
    ) -> PreparedAudioSource {
        let receipt = source.receipt;
        PreparedAudioSource::new(Arc::new(PreparedAudioSourceReceipt::new(
            receipt.preparation_generation(),
            receipt.fence().clone(),
            receipt.run_generation(),
            Arc::clone(receipt.verified_session()),
            Arc::new(schedule),
        )))
    }

    #[test]
    fn resource_limit_fails_before_a_candidate_can_enter_the_cache() {
        let (root, source) = source();
        let error = prepare_verified_audio_with_limits(
            source,
            AudioLoadLimits {
                maximum_encoded_bytes: 1024,
                maximum_frames: 1024,
                maximum_decoded_bytes: 4,
            },
        )
        .err()
        .unwrap();
        assert_eq!(error.code(), "prepared_audio_resource_limit");
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn local_summary_is_path_digest_pcm_and_identity_free() {
        let (root, source) = source();
        let path_text = source
            .receipt
            .wav_receipt()
            .unwrap()
            .path()
            .display()
            .to_string();
        let digest = source.receipt.wav_receipt().unwrap().sha256().to_owned();
        let summary = prepare_verified_audio(source).unwrap().summary().unwrap();
        let json = serde_json::to_string(&summary).unwrap();
        assert_eq!(summary.preparation_scope, "pcm-and-output-plan-cache");
        assert!(summary.output_plan_prepared);
        assert_eq!(summary.output_route, "legacy-stereo");
        assert!(summary.scheduled_event_count > 0);
        assert!(!summary.executable);
        for forbidden in [
            path_text.as_str(),
            digest.as_str(),
            "participant",
            "runGeneration",
            "interleaved",
        ] {
            assert!(
                !json.contains(forbidden),
                "summary leaked {forbidden}: {json}"
            );
        }
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn source_layout_selects_only_the_closed_unity_preflight_route() {
        let (legacy_root, legacy_source) = source_with_channels(2);
        let legacy = prepare_verified_audio(legacy_source).unwrap();
        assert_eq!(legacy.playback_plan().gains(), OutputGains::unity());
        assert_eq!(legacy.summary().unwrap().output_route, "legacy-stereo");
        fs::remove_dir_all(legacy_root).unwrap();

        let (canonical_root, canonical_source) = source_with_channels(3);
        let canonical = prepare_verified_audio(canonical_source).unwrap();
        assert_eq!(canonical.playback_plan().gains(), OutputGains::unity());
        assert_eq!(canonical.summary().unwrap().output_route, "canonical-three");
        assert_eq!(canonical.playback_plan().route().output_channels(), 3);
        fs::remove_dir_all(canonical_root).unwrap();
    }

    #[test]
    fn schedule_projection_discards_negative_events_and_keeps_original_sorted_indices() {
        let schedule = BlockEventSchedule::new(vec![
            event("negative-late", -1, "negative-late"),
            event("positive", 1, "positive"),
            event("negative-early", -10, "negative-early"),
            event("audio_sample_zero", 0, "control:audio_sample_zero"),
            event("terminal", 2, "terminal"),
        ])
        .unwrap();
        assert_eq!(
            schedule
                .events()
                .iter()
                .map(|event| event.sample_index)
                .collect::<Vec<_>>(),
            [-10, -1, 0, 1, 2]
        );

        let projected = project_schedule_events(&schedule, 2).unwrap();
        assert_eq!(
            projected
                .iter()
                .map(|event| (event.event_index(), event.sample_index()))
                .collect::<Vec<_>>(),
            [(3, 1), (4, 2)]
        );
        assert_eq!(
            projected
                .iter()
                .map(|event| {
                    schedule.events()[event.event_index() as usize]
                        .trigger_key
                        .as_str()
                })
                .collect::<Vec<_>>(),
            ["positive", "terminal"]
        );
        assert!(projected.iter().all(|event| {
            schedule.events()[event.event_index() as usize].event_type != "audio_sample_zero"
        }));
    }

    #[test]
    fn schedule_projection_requires_one_exact_sample_zero_anchor() {
        for events in [
            vec![event("trial_start", 0, "trial:start")],
            vec![
                event("audio_sample_zero", -1, "control:audio_sample_zero"),
                event("trial_start", 0, "trial:start"),
            ],
            vec![
                event("audio_sample_zero", 1, "control:audio_sample_zero"),
                event("trial_start", 0, "trial:start"),
            ],
            vec![
                event("audio_sample_zero", 0, "control:audio_sample_zero"),
                event(
                    "audio_sample_zero",
                    0,
                    "control:audio_sample_zero:duplicate",
                ),
            ],
        ] {
            let schedule = BlockEventSchedule::new(events).unwrap();
            let error = project_schedule_events(&schedule, 2).unwrap_err();
            assert_eq!(error.code(), "prepared_audio_sample_zero_anchor_invalid");
            assert_eq!(
                error.public_message(),
                "The prepared schedule does not contain exactly one valid audio sample-zero anchor."
            );
            assert!(!error.public_message().contains("trial:start"));
        }
    }

    #[test]
    fn sample_rate_event_index_and_eof_checks_fail_closed() {
        assert_eq!(
            checked_schedule_sample_rate_hz(0).unwrap_err().code(),
            "prepared_audio_sample_rate_invalid"
        );
        assert_eq!(
            checked_schedule_sample_rate_hz(i64::from(u32::MAX) + 1)
                .unwrap_err()
                .code(),
            "prepared_audio_sample_rate_invalid"
        );
        #[cfg(target_pointer_width = "64")]
        assert_eq!(
            checked_event_index(u32::MAX as usize + 1)
                .unwrap_err()
                .code(),
            "prepared_audio_schedule_overflow"
        );

        let schedule = BlockEventSchedule::new(vec![
            event("audio_sample_zero", 0, "control:audio_sample_zero"),
            event("past-eof", 3, "past-eof"),
        ])
        .unwrap();
        let error = project_schedule_events(&schedule, 2).unwrap_err();
        assert_eq!(error.code(), "prepared_audio_schedule_outside_media");
        assert!(!error.public_message().contains('3'));
    }

    #[test]
    fn output_plan_validation_errors_are_sanitized() {
        let burst =
            PreparedAudioError::from_output_plan(OutputPlanError::EventBurstLimitExceeded {
                sample_index: 123_456,
                event_count: 63,
                maximum: 62,
            });
        let density =
            PreparedAudioError::from_output_plan(OutputPlanError::EventDensityLimitExceeded {
                window_start_sample: 45,
                window_end_sample: 4_141,
                event_count: 63,
                maximum: 62,
            });
        for error in [burst, density] {
            assert_eq!(error.code(), "prepared_audio_output_plan_limit");
            assert_eq!(
                error.public_message(),
                "The prepared schedule exceeds the bounded native callback limits."
            );
            assert!(!error.public_message().contains("123456"));
        }
    }

    #[test]
    fn worker_rejects_exact_sample_rate_mismatch_before_a_candidate_exists() {
        let (root, source) = source();
        let mut options = BlockScheduleOptions::new(1);
        options.sample_rate = 44_100;
        let schedule = compile_block_schedule(&root.join("block.csv"), options).unwrap();
        let error = prepare_verified_audio(with_schedule(source, schedule))
            .err()
            .unwrap();
        assert_eq!(error.code(), "prepared_audio_format_unsupported");
        assert_eq!(
            error.public_message(),
            "The prepared audio format does not match the native Runner contract."
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn worker_sanitizes_eof_and_density_failures_without_returning_a_plan() {
        let (eof_root, eof_source) = source();
        fs::write(
            eof_root.join("outside.csv"),
            b"Trial_Number,Trial_UID,Trial_Type,Family,Trial_Start_Sample,Trial_End_Sample\n1,T1,Other,other,0,3\n",
        )
        .unwrap();
        let mut options = BlockScheduleOptions::new(1);
        options.sample_rate = 48_000;
        let eof_schedule = compile_block_schedule(&eof_root.join("outside.csv"), options).unwrap();
        let eof_error = prepare_verified_audio(with_schedule(eof_source, eof_schedule))
            .err()
            .unwrap();
        assert_eq!(eof_error.code(), "prepared_audio_schedule_outside_media");
        assert!(!eof_error.public_message().contains('3'));
        fs::remove_dir_all(eof_root).unwrap();

        let (density_root, density_source) = source();
        let mut csv = String::from(
            "Trial_Number,Trial_UID,Trial_Type,Family,Trial_Start_Sample,Looming_Onset_Sample,Tactile_Onset_Sample,Response_Window_Onset_Sample,Trial_End_Sample\n",
        );
        for trial in 1..=16 {
            csv.push_str(&format!("{trial},T{trial},Catch,catch,0,0,0,0,0\n"));
        }
        fs::write(density_root.join("dense.csv"), csv).unwrap();
        let mut options = BlockScheduleOptions::new(1);
        options.sample_rate = 48_000;
        let dense_schedule =
            compile_block_schedule(&density_root.join("dense.csv"), options).unwrap();
        assert!(dense_schedule.events().len() > 62);
        let dense_error = prepare_verified_audio(with_schedule(density_source, dense_schedule))
            .err()
            .unwrap();
        assert_eq!(dense_error.code(), "prepared_audio_output_plan_limit");
        assert_eq!(
            dense_error.public_message(),
            "The prepared schedule exceeds the bounded native callback limits."
        );
        assert!(!dense_error
            .public_message()
            .contains(density_root.to_string_lossy().as_ref()));
        fs::remove_dir_all(density_root).unwrap();
    }
}
