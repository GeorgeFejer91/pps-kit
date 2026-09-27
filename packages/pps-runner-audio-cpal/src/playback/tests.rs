use super::*;
use pps_runner_audio::{
    bind_and_decode_verified_wav, AudioFence, AudioLoadLimits, OutputGains, OutputRouteRequest,
    RtEventKind, RtScheduledEvent, VerifiedWavRequest,
};
use sha2::{Digest, Sha256};
use std::{
    fs::{self, OpenOptions},
    io::{Cursor, Write},
    sync::atomic::AtomicU64,
};

static SEQUENCE: AtomicU64 = AtomicU64::new(0);

pub(crate) fn plan(run_generation: u64) -> Arc<PreparedPlaybackPlan> {
    let mut bytes = Cursor::new(Vec::new());
    {
        let mut wav = hound::WavWriter::new(
            &mut bytes,
            hound::WavSpec {
                channels: 2,
                sample_rate: 48_000,
                bits_per_sample: 16,
                sample_format: hound::SampleFormat::Int,
            },
        )
        .unwrap();
        for sample in [16_384_i16, -8_192, 8_192, 16_384, 0, 0] {
            wav.write_sample(sample).unwrap();
        }
        wav.finalize().unwrap();
    }
    let bytes = bytes.into_inner();
    let path = std::env::temp_dir().join(format!(
        "pps-cpal-{}-{}-{}.wav",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos(),
        SEQUENCE.fetch_add(1, Ordering::Relaxed)
    ));
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&path)
        .unwrap();
    file.write_all(&bytes).unwrap();
    drop(file);
    let fence = AudioFence::new(1, "a".repeat(64), 0);
    let digest = format!("{:x}", Sha256::digest(&bytes));
    let media = bind_and_decode_verified_wav(VerifiedWavRequest {
        fence: &fence,
        path: &path,
        expected_sha256: &digest,
        expected_encoded_byte_count: bytes.len() as u64,
        expected_sample_rate_hz: 48_000,
        limits: AudioLoadLimits {
            maximum_encoded_bytes: 4_096,
            maximum_frames: 1_024,
            maximum_decoded_bytes: 4_096,
        },
    })
    .unwrap();
    fs::remove_file(path).unwrap();
    Arc::new(
        PreparedPlaybackPlan::new(
            media,
            run_generation,
            OutputRouteRequest::legacy_stereo(),
            OutputGains::new(1.0, 1.0).unwrap(),
            vec![RtScheduledEvent::new(0, 1)].into_boxed_slice(),
        )
        .unwrap(),
    )
}

#[test]
fn preparation_stays_silent_without_filling_evidence_until_exact_pcm_submission() {
    let plan = plan(1);
    let (mut owner, mut callback) = PlaybackOwner::new(Arc::clone(&plan));
    let mut output = [9.0; 2];
    for _ in 0..PLAYBACK_EVENT_CAPACITY + 1 {
        assert!(!callback.render(&mut output, Instant::now(), None));
        assert_eq!(output, [0.0; 2]);
    }
    assert_eq!(owner.status().submitted_frames, 0);
    assert!(owner.drain(PLAYBACK_EVENT_CAPACITY).is_empty());
    let receipt = owner.control(plan.fence(), RenderControl::Start).unwrap();
    assert_eq!(owner.status().last_control_sequence, 0);
    assert!(!callback.render(&mut output, Instant::now(), None));
    assert_eq!(output, [-0.25, 0.5]);
    assert_eq!(owner.status().last_control_sequence, receipt.sequence);
    callback.render(&mut output, Instant::now(), None);
    assert_eq!(output, [0.5, 0.25]);
    callback.render(&mut output, Instant::now(), None);
    assert_eq!(owner.status().state, RenderState::SourceExhausted);
    let records = owner.drain(PLAYBACK_EVENT_CAPACITY);
    assert!(records
        .iter()
        .all(|record| record.fence == plan.fence().rt_projection()));
    assert!(records.iter().any(|record| matches!(
        record.kind,
        PlaybackRecordKind::Control {
            requested: RenderControl::Start,
            result: ControlResult::Applied,
            ..
        }
    )));
    let boundaries: Vec<_> = records
        .iter()
        .filter_map(|record| match record.kind {
            PlaybackRecordKind::Boundary(event) => Some(event.kind()),
            _ => None,
        })
        .collect();
    assert_eq!(
        boundaries,
        [
            RtEventKind::SampleZero,
            RtEventKind::Scheduled { event_index: 0 },
            RtEventKind::FinalFrameSubmitted
        ]
    );
}

#[test]
fn pause_retains_cursor_and_resume_submits_the_next_sample() {
    let plan = plan(2);
    let (mut owner, mut callback) = PlaybackOwner::new(Arc::clone(&plan));
    let mut output = [9.0; 2];
    owner.control(plan.fence(), RenderControl::Start).unwrap();
    callback.render(&mut output, Instant::now(), None);
    owner.control(plan.fence(), RenderControl::Pause).unwrap();
    callback.render(&mut output, Instant::now(), None);
    assert_eq!(output, [0.0; 2]);
    assert_eq!(owner.status().state, RenderState::Paused);
    assert_eq!(owner.status().submitted_frames, 1);
    owner.control(plan.fence(), RenderControl::Resume).unwrap();
    callback.render(&mut output, Instant::now(), None);
    assert_eq!(output, [0.5, 0.25]);
    assert_eq!(owner.status().submitted_frames, 2);
}

#[test]
fn safety_controls_dominate_a_full_normal_queue_and_reject_stale_fences() {
    let plan = plan(3);
    let stale = super::tests::plan(4);
    let (mut owner, mut callback) = PlaybackOwner::new(Arc::clone(&plan));
    assert_eq!(
        owner.control(stale.fence(), RenderControl::Start),
        Err(PlaybackControlError::StaleFence)
    );
    owner.control(plan.fence(), RenderControl::Start).unwrap();
    assert_eq!(
        owner.control(plan.fence(), RenderControl::Pause),
        Err(PlaybackControlError::Busy)
    );
    owner.control(plan.fence(), RenderControl::Stop).unwrap();
    owner.control(plan.fence(), RenderControl::Abort).unwrap();
    let mut output = [9.0; 2];
    callback.render(&mut output, Instant::now(), None);
    assert_eq!(output, [0.0; 2]);
    assert_eq!(owner.status().state, RenderState::Aborted);
    assert_eq!(owner.status().submitted_frames, 0);
    assert!(!owner
        .drain(PLAYBACK_EVENT_CAPACITY)
        .iter()
        .any(|record| matches!(record.kind, PlaybackRecordKind::Boundary(_))));
}

#[test]
fn evidence_capacity_is_checked_before_source_samples_and_controls() {
    let plan = plan(5);
    let (mut owner, mut callback) =
        PlaybackOwner::with_capacity(Arc::clone(&plan), RECORDS_PER_CALLBACK - 1);
    owner.control(plan.fence(), RenderControl::Start).unwrap();
    let mut output = [9.0; 2];
    assert!(callback.render(&mut output, Instant::now(), None));
    assert_eq!(output, [0.0; 2]);
    assert_eq!(owner.status().submitted_frames, 0);
    assert_eq!(owner.status().last_control_sequence, 0);
    assert_eq!(owner.status().fault, Some(PlaybackFault::EvidenceQueueFull));
    assert!(owner.drain(PLAYBACK_EVENT_CAPACITY).is_empty());
}

#[test]
fn owner_retains_storage_until_callback_retires_and_old_cancellation_is_fenced() {
    let plan = plan(6);
    let weak = Arc::downgrade(&plan);
    let (owner, callback) = PlaybackOwner::new(plan);
    let old_cancel = owner.cancellation();
    assert!(!owner.status().callback_retired);
    drop(callback);
    assert!(owner.status().callback_retired);
    assert!(weak.upgrade().is_some());
    drop(owner);
    assert!(weak.upgrade().is_none());
    let current = super::tests::plan(7);
    let (mut owner, mut callback) = PlaybackOwner::new(Arc::clone(&current));
    old_cancel.abort();
    owner
        .control(current.fence(), RenderControl::Start)
        .unwrap();
    let mut output = [9.0; 2];
    callback.render(&mut output, Instant::now(), None);
    assert_eq!(output, [-0.25, 0.5]);
}

#[test]
fn stalled_evidence_consumer_cannot_advance_unrecorded_audio() {
    let plan = plan(9);
    let (mut owner, mut callback) =
        PlaybackOwner::with_capacity(Arc::clone(&plan), RECORDS_PER_CALLBACK);
    owner.control(plan.fence(), RenderControl::Start).unwrap();
    let mut output = [9.0; 2];
    assert!(!callback.render(&mut output, Instant::now(), None));
    assert_eq!(output, [-0.25, 0.5]);
    assert_eq!(owner.status().submitted_frames, 1);
    assert!(callback.render(&mut output, Instant::now(), None));
    assert_eq!(output, [0.0; 2]);
    assert_eq!(owner.status().submitted_frames, 1);
    let records = owner.drain(PLAYBACK_EVENT_CAPACITY);
    assert_eq!(
        records
            .iter()
            .filter(|record| matches!(record.kind, PlaybackRecordKind::Boundary(_)))
            .count(),
        1
    );
    assert_eq!(owner.status().fault, Some(PlaybackFault::EvidenceQueueFull));
    assert!(callback.render(&mut output, Instant::now(), None));
    assert_eq!(owner.status().submitted_frames, 1);
}

#[test]
fn stopped_callback_cannot_restart_or_resume_its_source() {
    let plan = plan(10);
    let (mut owner, mut callback) = PlaybackOwner::new(Arc::clone(&plan));
    let mut output = [9.0; 2];
    owner.control(plan.fence(), RenderControl::Start).unwrap();
    callback.render(&mut output, Instant::now(), None);
    owner.control(plan.fence(), RenderControl::Stop).unwrap();
    callback.render(&mut output, Instant::now(), None);
    for action in [RenderControl::Start, RenderControl::Resume] {
        owner.control(plan.fence(), action).unwrap();
        callback.render(&mut output, Instant::now(), None);
        assert_eq!(output, [0.0; 2]);
        assert_eq!(owner.status().state, RenderState::Stopped);
        assert_eq!(owner.status().submitted_frames, 1);
    }
}
