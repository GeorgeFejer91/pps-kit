use std::{
    fs,
    sync::atomic::{AtomicU64, Ordering},
};

use pps_runner_audio::{
    bind_and_decode_verified_wav, resolve_output_route, AudioFence, AudioLoadLimits, ControlResult,
    MockOutput, OutputFence, OutputGains, OutputPlanError, OutputRouteError, OutputRouteRequest,
    PpsChannelLayout, PreparedPcmBlock, PreparedPlaybackPlan, RenderControl, RenderIntegrityFault,
    RenderState, RtEvent, RtEventKind, RtScheduledEvent, VerifiedWavRequest,
    MAXIMUM_METADATA_EVENTS_PER_CALLBACK, MAXIMUM_OUTPUT_CALLBACK_FRAMES,
};
use sha2::{Digest, Sha256};

const SAMPLE_RATE_HZ: u32 = 48_000;
static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

fn wav_bytes(channels: u16, samples: &[i16]) -> Vec<u8> {
    assert!(samples.len().is_multiple_of(usize::from(channels)));
    let data_bytes = u32::try_from(size_of_val(samples)).unwrap();
    let mut bytes = Vec::with_capacity(44 + data_bytes as usize);
    bytes.extend_from_slice(b"RIFF");
    bytes.extend_from_slice(&(36 + data_bytes).to_le_bytes());
    bytes.extend_from_slice(b"WAVEfmt ");
    bytes.extend_from_slice(&16_u32.to_le_bytes());
    bytes.extend_from_slice(&1_u16.to_le_bytes());
    bytes.extend_from_slice(&channels.to_le_bytes());
    bytes.extend_from_slice(&SAMPLE_RATE_HZ.to_le_bytes());
    bytes.extend_from_slice(
        &(SAMPLE_RATE_HZ * u32::from(channels) * size_of::<i16>() as u32).to_le_bytes(),
    );
    bytes.extend_from_slice(&(channels * size_of::<i16>() as u16).to_le_bytes());
    bytes.extend_from_slice(&16_u16.to_le_bytes());
    bytes.extend_from_slice(b"data");
    bytes.extend_from_slice(&data_bytes.to_le_bytes());
    for sample in samples {
        bytes.extend_from_slice(&sample.to_le_bytes());
    }
    bytes
}

fn prepared_pcm(channels: u16, samples: &[i16], package_generation: u64) -> PreparedPcmBlock {
    let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
    let root = std::env::temp_dir().join(format!(
        "pps-output-render-{}-{sequence}",
        std::process::id()
    ));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    let path = root.join("block.wav");
    let bytes = wav_bytes(channels, samples);
    fs::write(&path, &bytes).unwrap();
    let sha256 = format!("{:x}", Sha256::digest(&bytes));
    let fence = AudioFence::new(package_generation, "a".repeat(64), u32::from(channels));
    let prepared = bind_and_decode_verified_wav(VerifiedWavRequest {
        fence: &fence,
        path: &path,
        expected_sha256: &sha256,
        expected_encoded_byte_count: bytes.len() as u64,
        expected_sample_rate_hz: SAMPLE_RATE_HZ,
        limits: AudioLoadLimits {
            maximum_encoded_bytes: 4096,
            maximum_frames: 1024,
            maximum_decoded_bytes: 4096,
        },
    })
    .unwrap();
    fs::remove_dir_all(root).unwrap();
    prepared
}

fn playback_plan(
    channels: u16,
    samples: &[i16],
    package_generation: u64,
    run_generation: u64,
    route: OutputRouteRequest,
    gains: OutputGains,
    events: Vec<RtScheduledEvent>,
) -> PreparedPlaybackPlan {
    PreparedPlaybackPlan::new(
        prepared_pcm(channels, samples, package_generation),
        run_generation,
        route,
        gains,
        events.into_boxed_slice(),
    )
    .unwrap()
}

fn start(output: &mut MockOutput) -> OutputFence {
    let fence = output.fence().clone();
    assert_eq!(
        output.apply_control(&fence, RenderControl::Start),
        ControlResult::Applied
    );
    fence
}

fn emitted(slots: &[Option<RtEvent>], count: usize) -> Vec<RtEvent> {
    slots[..count]
        .iter()
        .map(|slot| slot.expect("the callback must fill its reported event prefix"))
        .collect()
}

fn pcm(sample: i16) -> f32 {
    f32::from(sample) / 32768.0
}

#[test]
fn routes_legacy_and_canonical_vectors_with_gains_and_mirror() {
    let gains = OutputGains::new(0.5, 0.5).unwrap();

    let mut legacy = MockOutput::new(playback_plan(
        2,
        &[16_384, -8_192],
        1,
        1,
        OutputRouteRequest::legacy_stereo(),
        gains,
        vec![],
    ));
    start(&mut legacy);
    let mut legacy_buffer = [9.0; 2];
    let mut event_slots = [None; 2];
    let outcome = legacy.callback(&mut legacy_buffer, &mut event_slots);
    assert_eq!(outcome.state, RenderState::SourceExhausted);
    assert_eq!(legacy_buffer, [-0.125, 0.25]);

    let mut canonical_three = MockOutput::new(playback_plan(
        3,
        &[16_384, -16_384, 8_192],
        2,
        2,
        OutputRouteRequest::canonical_three(),
        gains,
        vec![],
    ));
    start(&mut canonical_three);
    let mut three_buffer = [9.0; 3];
    let outcome = canonical_three.callback(&mut three_buffer, &mut event_slots);
    assert_eq!(outcome.state, RenderState::SourceExhausted);
    assert_eq!(three_buffer, [0.25, -0.25, 0.125]);

    let mut canonical_four = MockOutput::new(playback_plan(
        3,
        &[16_384, -16_384, 8_192],
        3,
        3,
        OutputRouteRequest::canonical_four_with_tactile_mirror(),
        gains,
        vec![],
    ));
    start(&mut canonical_four);
    let mut four_buffer = [9.0; 4];
    let outcome = canonical_four.callback(&mut four_buffer, &mut event_slots);
    assert_eq!(outcome.state, RenderState::SourceExhausted);
    assert_eq!(four_buffer, [0.25, -0.25, 0.125, 0.125]);
}

#[test]
fn route_resolver_rejects_duplicate_ambiguous_and_unsupported_mappings() {
    let duplicate = resolve_output_route(
        PpsChannelLayout::LegacyStudy5TactileAudio,
        OutputRouteRequest::LegacyStereo {
            output_channels: 2,
            audio_output: 0,
            tactile_output: 0,
        },
    )
    .unwrap_err();
    assert_eq!(duplicate, OutputRouteError::DuplicateOutput);

    let out_of_range = resolve_output_route(
        PpsChannelLayout::LegacyStudy5TactileAudio,
        OutputRouteRequest::LegacyStereo {
            output_channels: 2,
            audio_output: 0,
            tactile_output: 2,
        },
    )
    .unwrap_err();
    assert_eq!(out_of_range, OutputRouteError::OutputOutOfRange);

    let unsupported = resolve_output_route(
        PpsChannelLayout::BinauralLeftRightTactile,
        OutputRouteRequest::BinauralTactile {
            output_channels: 3,
            left_output: 1,
            right_output: 0,
            tactile_output: 2,
            tactile_mirror_output: None,
        },
    )
    .unwrap_err();
    assert_eq!(unsupported, OutputRouteError::UnsupportedMapping);

    let ambiguous_mirror = resolve_output_route(
        PpsChannelLayout::BinauralLeftRightTactile,
        OutputRouteRequest::BinauralTactile {
            output_channels: 4,
            left_output: 0,
            right_output: 1,
            tactile_output: 2,
            tactile_mirror_output: Some(2),
        },
    )
    .unwrap_err();
    assert_eq!(ambiguous_mirror, OutputRouteError::DuplicateOutput);

    let layout_mismatch = resolve_output_route(
        PpsChannelLayout::BinauralLeftRightTactile,
        OutputRouteRequest::legacy_stereo(),
    )
    .unwrap_err();
    assert_eq!(layout_mismatch, OutputRouteError::SourceLayoutMismatch);
}

#[test]
fn variable_callback_buffers_advance_one_u64_source_cursor_and_zero_the_tail() {
    let samples = [
        1_000, 2_000, 3_000, 4_000, 5_000, 6_000, 7_000, 8_000, 9_000, 10_000,
    ];
    let mut output = MockOutput::new(playback_plan(
        2,
        &samples,
        4,
        9,
        OutputRouteRequest::legacy_stereo(),
        OutputGains::unity(),
        vec![],
    ));
    start(&mut output);

    let mut events = [None; 1];
    let mut first = [0.0; 2];
    let first_outcome = output.callback(&mut first, &mut events);
    assert_eq!(first_outcome.cursor_frames, 1);
    assert_eq!(first, [pcm(2_000), pcm(1_000)]);

    let mut second = [0.0; 4];
    let second_outcome = output.callback(&mut second, &mut events);
    assert_eq!(second_outcome.cursor_frames, 3);
    assert_eq!(second, [pcm(4_000), pcm(3_000), pcm(6_000), pcm(5_000)]);

    let mut final_buffer = [7.0; 8];
    let final_outcome = output.callback(&mut final_buffer, &mut events);
    assert_eq!(final_outcome.state, RenderState::SourceExhausted);
    assert_eq!(final_outcome.cursor_frames, 5);
    assert_eq!(final_outcome.rendered_source_frames, 2);
    assert_eq!(
        final_buffer,
        [
            pcm(8_000),
            pcm(7_000),
            pcm(10_000),
            pcm(9_000),
            0.0,
            0.0,
            0.0,
            0.0,
        ]
    );
}

#[test]
fn pause_freezes_the_cursor_resume_continues_and_every_stale_fence_dimension_is_inert() {
    let mut output = MockOutput::new(playback_plan(
        2,
        &[1_000, 2_000, 3_000, 4_000, 5_000, 6_000, 7_000, 8_000],
        5,
        11,
        OutputRouteRequest::legacy_stereo(),
        OutputGains::unity(),
        vec![],
    ));
    let fence = start(&mut output);
    let stale_fences = [
        OutputFence::new(fence.audio(), fence.run_generation() - 1),
        OutputFence::new(
            &AudioFence::new(
                fence.audio().package_generation() + 1,
                fence.audio().package_fingerprint().to_owned(),
                fence.audio().block_ordinal(),
            ),
            fence.run_generation(),
        ),
        OutputFence::new(
            &AudioFence::new(
                fence.audio().package_generation(),
                "b".repeat(64),
                fence.audio().block_ordinal(),
            ),
            fence.run_generation(),
        ),
        OutputFence::new(
            &AudioFence::new(
                fence.audio().package_generation(),
                fence.audio().package_fingerprint().to_owned(),
                fence.audio().block_ordinal() + 1,
            ),
            fence.run_generation(),
        ),
    ];
    let mut events = [None; 1];
    let mut buffer = [0.0; 2];
    output.callback(&mut buffer, &mut events);
    assert_eq!(output.cursor_frames(), 1);

    for stale in &stale_fences {
        assert_eq!(
            output.apply_control(stale, RenderControl::Pause),
            ControlResult::Stale
        );
    }
    output.callback(&mut buffer, &mut events);
    assert_eq!(buffer, [pcm(4_000), pcm(3_000)]);
    assert_eq!(output.cursor_frames(), 2);

    assert_eq!(
        output.apply_control(&fence, RenderControl::Pause),
        ControlResult::Applied
    );
    buffer.fill(7.0);
    let paused = output.callback(&mut buffer, &mut events);
    assert_eq!(paused.state, RenderState::Paused);
    assert_eq!(paused.cursor_frames, 2);
    assert_eq!(paused.rendered_source_frames, 0);
    assert_eq!(buffer, [0.0, 0.0]);

    assert_eq!(
        output.apply_control(&fence, RenderControl::Resume),
        ControlResult::Applied
    );
    output.callback(&mut buffer, &mut events);
    assert_eq!(buffer, [pcm(6_000), pcm(5_000)]);
    assert_eq!(output.cursor_frames(), 3);
}

#[test]
fn sample_zero_half_open_events_and_terminal_eof_are_emitted_exactly_once() {
    let mut output = MockOutput::new(playback_plan(
        3,
        &[
            1_000, 2_000, 3_000, 4_000, 5_000, 6_000, 7_000, 8_000, 9_000,
        ],
        6,
        12,
        OutputRouteRequest::canonical_three(),
        OutputGains::unity(),
        vec![
            RtScheduledEvent::new(10, 0),
            RtScheduledEvent::new(20, 2),
            RtScheduledEvent::new(30, 3),
        ],
    ));
    start(&mut output);
    let mut buffer = [7.0; 15];
    let mut slots = [None; 5];
    let outcome = output.callback(&mut buffer, &mut slots);
    assert_eq!(outcome.state, RenderState::SourceExhausted);
    assert_eq!(outcome.cursor_frames, 3);
    assert_eq!(&buffer[9..], &[0.0; 6]);

    let events = emitted(&slots, outcome.events_written);
    assert_eq!(events.len(), 5);
    assert_eq!(events[0].kind(), RtEventKind::SampleZero);
    assert_eq!(events[0].sample_index(), 0);
    assert_eq!(events[0].sample_offset_in_callback(), 0);
    assert_eq!(events[1].kind(), RtEventKind::Scheduled { event_index: 10 });
    assert_eq!(events[1].sample_offset_in_callback(), 0);
    assert_eq!(events[2].kind(), RtEventKind::Scheduled { event_index: 20 });
    assert_eq!(events[2].sample_offset_in_callback(), 2);
    assert_eq!(events[3].kind(), RtEventKind::Scheduled { event_index: 30 });
    assert_eq!(events[3].sample_offset_in_callback(), 3);
    assert_eq!(events[3].fence().run_generation(), 12);
    assert_eq!(events[3].fence().block_ordinal(), 3);
    assert_eq!(events[4].kind(), RtEventKind::FinalFrameSubmitted);
    assert_eq!(events[4].sample_index(), 3);
    assert_eq!(events[4].sample_offset_in_callback(), 3);
    assert_eq!(events[4].callback_sequence(), events[3].callback_sequence());

    buffer.fill(7.0);
    let repeated = output.callback(&mut buffer, &mut slots);
    assert_eq!(repeated.state, RenderState::SourceExhausted);
    assert_eq!(repeated.events_written, 0);
    assert_eq!(buffer, [0.0; 15]);
}

#[test]
fn one_frame_callback_orders_metadata_before_final_submission_and_emits_it_once() {
    let mut output = MockOutput::new(playback_plan(
        2,
        &[1_000, 2_000],
        60,
        120,
        OutputRouteRequest::legacy_stereo(),
        OutputGains::unity(),
        vec![RtScheduledEvent::new(10, 0), RtScheduledEvent::new(20, 1)],
    ));
    start(&mut output);

    let mut buffer = [7.0; 2];
    let mut slots = [None; 4];
    let outcome = output.callback(&mut buffer, &mut slots);
    assert_eq!(outcome.state, RenderState::SourceExhausted);
    assert_eq!(outcome.events_written, 4);
    assert_eq!(
        emitted(&slots, outcome.events_written)
            .into_iter()
            .map(|event| (
                event.kind(),
                event.sample_index(),
                event.sample_offset_in_callback()
            ))
            .collect::<Vec<_>>(),
        vec![
            (RtEventKind::SampleZero, 0, 0),
            (RtEventKind::Scheduled { event_index: 10 }, 0, 0),
            (RtEventKind::Scheduled { event_index: 20 }, 1, 1),
            (RtEventKind::FinalFrameSubmitted, 1, 1),
        ]
    );

    buffer.fill(7.0);
    let repeated = output.callback(&mut buffer, &mut slots);
    assert_eq!(repeated.state, RenderState::SourceExhausted);
    assert_eq!(repeated.events_written, 0);
    assert_eq!(buffer, [0.0; 2]);
}

#[test]
fn terminal_event_overflow_is_preflighted_without_partial_events_or_samples() {
    let mut output = MockOutput::new(playback_plan(
        2,
        &[1_000, 2_000],
        61,
        121,
        OutputRouteRequest::legacy_stereo(),
        OutputGains::unity(),
        vec![RtScheduledEvent::new(10, 0), RtScheduledEvent::new(20, 1)],
    ));
    start(&mut output);

    let mut buffer = [7.0; 2];
    let mut too_small = [None; 3];
    let outcome = output.callback(&mut buffer, &mut too_small);
    assert_eq!(outcome.state, RenderState::Faulted);
    assert_eq!(
        outcome.fault,
        Some(RenderIntegrityFault::EventSinkOverflow {
            required: 4,
            available: 3,
        })
    );
    assert_eq!(outcome.cursor_frames, 0);
    assert_eq!(outcome.events_written, 0);
    assert_eq!(buffer, [0.0; 2]);
    assert_eq!(too_small, [None; 3]);
}

#[test]
fn equal_sample_events_keep_input_order_at_the_next_half_open_window() {
    let mut output = MockOutput::new(playback_plan(
        2,
        &[1_000, 2_000, 3_000, 4_000, 5_000, 6_000],
        7,
        13,
        OutputRouteRequest::legacy_stereo(),
        OutputGains::unity(),
        vec![
            RtScheduledEvent::new(30, 1),
            RtScheduledEvent::new(10, 1),
            RtScheduledEvent::new(20, 1),
        ],
    ));
    start(&mut output);
    let mut buffer = [0.0; 2];
    let mut first_slots = [None; 1];
    let first = output.callback(&mut buffer, &mut first_slots);
    assert_eq!(first.events_written, 1);
    assert_eq!(emitted(&first_slots, 1)[0].kind(), RtEventKind::SampleZero);

    let mut tied_slots = [None; 3];
    let second = output.callback(&mut buffer, &mut tied_slots);
    let tied = emitted(&tied_slots, second.events_written);
    assert_eq!(
        tied.iter().map(|event| event.kind()).collect::<Vec<_>>(),
        vec![
            RtEventKind::Scheduled { event_index: 30 },
            RtEventKind::Scheduled { event_index: 10 },
            RtEventKind::Scheduled { event_index: 20 },
        ]
    );
    assert!(tied
        .iter()
        .all(|event| event.sample_offset_in_callback() == 0));
}

#[test]
fn reused_event_slots_expose_only_the_reported_current_callback_prefix() {
    let mut output = MockOutput::new(playback_plan(
        2,
        &[1_000, 2_000, 3_000, 4_000],
        62,
        122,
        OutputRouteRequest::legacy_stereo(),
        OutputGains::unity(),
        vec![RtScheduledEvent::new(10, 0)],
    ));
    start(&mut output);

    let mut buffer = [0.0; 2];
    let mut slots = [None; 4];
    let first = output.callback(&mut buffer, &mut slots);
    assert_eq!(first.events_written, 2);
    assert_eq!(slots[0].unwrap().kind(), RtEventKind::SampleZero);
    assert_eq!(
        slots[1].unwrap().kind(),
        RtEventKind::Scheduled { event_index: 10 }
    );

    let second = output.callback(&mut buffer, &mut slots);
    assert_eq!(second.state, RenderState::SourceExhausted);
    assert_eq!(second.events_written, 1);
    assert_eq!(slots[0].unwrap().kind(), RtEventKind::FinalFrameSubmitted);
    assert_eq!(
        slots[1].unwrap().kind(),
        RtEventKind::Scheduled { event_index: 10 },
        "storage beyond the reported prefix may retain an older callback"
    );

    let repeated = output.callback(&mut buffer, &mut slots);
    assert_eq!(repeated.events_written, 0);
    assert!(
        slots[0].is_some(),
        "a zero-length prefix does not clear storage"
    );
}

#[test]
fn event_sink_saturation_silences_the_current_buffer_and_latches_fail_stop() {
    let mut output = MockOutput::new(playback_plan(
        2,
        &[8_000, 16_000, 4_000, 12_000],
        8,
        14,
        OutputRouteRequest::legacy_stereo(),
        OutputGains::unity(),
        vec![RtScheduledEvent::new(1, 0), RtScheduledEvent::new(2, 0)],
    ));
    start(&mut output);
    let mut buffer = [7.0; 2];
    let mut too_small = [None; 2];
    let outcome = output.callback(&mut buffer, &mut too_small);
    assert_eq!(outcome.state, RenderState::Faulted);
    assert_eq!(
        outcome.fault,
        Some(RenderIntegrityFault::EventSinkOverflow {
            required: 3,
            available: 2,
        })
    );
    assert_eq!(outcome.events_written, 0);
    assert_eq!(outcome.cursor_frames, 0);
    assert_eq!(buffer, [0.0, 0.0]);

    let mut ample = [None; 8];
    buffer.fill(7.0);
    let repeated = output.callback(&mut buffer, &mut ample);
    assert_eq!(repeated.state, RenderState::Faulted);
    assert_eq!(repeated.events_written, 0);
    assert_eq!(repeated.cursor_frames, 0);
    assert_eq!(buffer, [0.0, 0.0]);
}

#[test]
fn malformed_output_shape_and_oversized_callback_fail_closed_before_rendering() {
    let mut malformed = MockOutput::new(playback_plan(
        2,
        &[1_000, 2_000, 3_000, 4_000],
        63,
        123,
        OutputRouteRequest::legacy_stereo(),
        OutputGains::unity(),
        vec![],
    ));
    start(&mut malformed);
    let mut malformed_buffer = [7.0; 3];
    let mut slots = [None; 2];
    let malformed_outcome = malformed.callback(&mut malformed_buffer, &mut slots);
    assert_eq!(malformed_outcome.state, RenderState::Faulted);
    assert_eq!(
        malformed_outcome.fault,
        Some(RenderIntegrityFault::OutputBufferShape)
    );
    assert_eq!(malformed_outcome.cursor_frames, 0);
    assert_eq!(malformed_outcome.events_written, 0);
    assert_eq!(malformed_buffer, [0.0; 3]);

    let mut oversized = MockOutput::new(playback_plan(
        2,
        &[1_000, 2_000],
        64,
        124,
        OutputRouteRequest::legacy_stereo(),
        OutputGains::unity(),
        vec![],
    ));
    start(&mut oversized);
    let mut oversized_buffer = vec![7.0; (MAXIMUM_OUTPUT_CALLBACK_FRAMES + 1) * 2];
    let oversized_outcome = oversized.callback(&mut oversized_buffer, &mut slots);
    assert_eq!(oversized_outcome.state, RenderState::Faulted);
    assert_eq!(
        oversized_outcome.fault,
        Some(RenderIntegrityFault::CallbackFrameLimitExceeded {
            observed: MAXIMUM_OUTPUT_CALLBACK_FRAMES + 1,
            maximum: MAXIMUM_OUTPUT_CALLBACK_FRAMES,
        })
    );
    assert_eq!(oversized_outcome.cursor_frames, 0);
    assert_eq!(oversized_outcome.events_written, 0);
    assert!(oversized_buffer.iter().all(|sample| *sample == 0.0));
}

#[test]
fn stop_and_abort_are_terminal_silent_states() {
    for (control, state) in [
        (RenderControl::Stop, RenderState::Stopped),
        (RenderControl::Abort, RenderState::Aborted),
    ] {
        let mut output = MockOutput::new(playback_plan(
            2,
            &[8_000, 16_000],
            9,
            15,
            OutputRouteRequest::legacy_stereo(),
            OutputGains::unity(),
            vec![],
        ));
        let fence = start(&mut output);
        assert_eq!(
            output.apply_control(&fence, control),
            ControlResult::Applied
        );
        let mut buffer = [7.0; 2];
        let mut slots = [None; 1];
        let outcome = output.callback(&mut buffer, &mut slots);
        assert_eq!(outcome.state, state);
        assert_eq!(outcome.cursor_frames, 0);
        assert_eq!(outcome.events_written, 0);
        assert_eq!(buffer, [0.0, 0.0]);
    }
}

#[test]
fn plan_validation_rejects_bad_gains_event_order_and_events_beyond_eof() {
    assert_eq!(
        OutputGains::new(f32::NAN, 1.0).unwrap_err(),
        OutputPlanError::InvalidGain
    );
    assert_eq!(
        OutputGains::new(1.0, 1.01).unwrap_err(),
        OutputPlanError::InvalidGain
    );

    let unordered = PreparedPlaybackPlan::new(
        prepared_pcm(2, &[1, 2, 3, 4], 10),
        16,
        OutputRouteRequest::legacy_stereo(),
        OutputGains::unity(),
        vec![RtScheduledEvent::new(1, 2), RtScheduledEvent::new(2, 1)].into_boxed_slice(),
    )
    .unwrap_err();
    assert_eq!(unordered, OutputPlanError::EventOrder);

    let beyond = PreparedPlaybackPlan::new(
        prepared_pcm(2, &[1, 2, 3, 4], 11),
        17,
        OutputRouteRequest::legacy_stereo(),
        OutputGains::unity(),
        vec![RtScheduledEvent::new(9, 3)].into_boxed_slice(),
    )
    .unwrap_err();
    assert_eq!(
        beyond,
        OutputPlanError::EventBeyondEnd {
            event_index: 9,
            sample_index: 3,
            total_frames: 2,
        }
    );
}

#[test]
fn plan_validation_rejects_oversized_tied_bursts_at_sample_zero_and_eof() {
    let burst = |sample_index| {
        (0..=MAXIMUM_METADATA_EVENTS_PER_CALLBACK)
            .map(|index| RtScheduledEvent::new(u32::try_from(index).unwrap(), sample_index))
            .collect::<Vec<_>>()
            .into_boxed_slice()
    };

    let sample_zero = PreparedPlaybackPlan::new(
        prepared_pcm(2, &[1, 2, 3, 4], 65),
        125,
        OutputRouteRequest::legacy_stereo(),
        OutputGains::unity(),
        burst(0),
    )
    .unwrap_err();
    assert_eq!(
        sample_zero,
        OutputPlanError::EventBurstLimitExceeded {
            sample_index: 0,
            event_count: MAXIMUM_METADATA_EVENTS_PER_CALLBACK + 1,
            maximum: MAXIMUM_METADATA_EVENTS_PER_CALLBACK,
        }
    );
    assert_eq!(
        sample_zero.to_string(),
        "sample 0 has 63 metadata events; the callback burst limit is 62"
    );

    let eof = PreparedPlaybackPlan::new(
        prepared_pcm(2, &[1, 2, 3, 4], 66),
        126,
        OutputRouteRequest::legacy_stereo(),
        OutputGains::unity(),
        burst(2),
    )
    .unwrap_err();
    assert_eq!(
        eof,
        OutputPlanError::EventBurstLimitExceeded {
            sample_index: 2,
            event_count: MAXIMUM_METADATA_EVENTS_PER_CALLBACK + 1,
            maximum: MAXIMUM_METADATA_EVENTS_PER_CALLBACK,
        }
    );
}

#[test]
fn plan_validation_rejects_oversized_event_density_before_rendering() {
    let samples = vec![0_i16; 128 * 2];
    let events = (0..=MAXIMUM_METADATA_EVENTS_PER_CALLBACK)
        .map(|index| {
            RtScheduledEvent::new(u32::try_from(index).unwrap(), u64::try_from(index).unwrap())
        })
        .collect::<Vec<_>>()
        .into_boxed_slice();
    let error = PreparedPlaybackPlan::new(
        prepared_pcm(2, &samples, 67),
        127,
        OutputRouteRequest::legacy_stereo(),
        OutputGains::unity(),
        events,
    )
    .unwrap_err();
    assert_eq!(
        error,
        OutputPlanError::EventDensityLimitExceeded {
            window_start_sample: 0,
            window_end_sample: MAXIMUM_METADATA_EVENTS_PER_CALLBACK as u64,
            event_count: MAXIMUM_METADATA_EVENTS_PER_CALLBACK + 1,
            maximum: MAXIMUM_METADATA_EVENTS_PER_CALLBACK,
        }
    );
}

#[test]
fn playback_plan_debug_omits_private_fingerprints_digests_and_pcm() {
    let media = prepared_pcm(2, &[1_234, -2_345, 3_456, -4_567], 68);
    let package_fingerprint = media.fence().package_fingerprint().to_owned();
    let media_digest = media.identity().sha256().to_owned();
    let plan = PreparedPlaybackPlan::new(
        media,
        128,
        OutputRouteRequest::legacy_stereo(),
        OutputGains::unity(),
        Box::new([]),
    )
    .unwrap();

    let debug = format!("{plan:?}");
    assert!(!debug.contains(&package_fingerprint));
    assert!(!debug.contains(&media_digest));
    assert!(!debug.contains("sha256"));
    assert!(!debug.contains("interleaved_f32"));
    assert!(!debug.contains("1234"));
    assert!(!debug.contains("2345"));
}
