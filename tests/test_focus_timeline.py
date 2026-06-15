from __future__ import annotations

from peripersonal_space_toolkit.focus_timeline import TactileRecenterController, TactileTimelineState


def test_tactile_timeline_state_loads_and_labels_cues():
    state = TactileTimelineState()

    state.load_block(
        part_number=2,
        phase_label="Condition 2",
        block_index=7,
        block_label="Block 07",
        duration_s=20.0,
        tactile_events=[
            {
                "trial_number": 2,
                "trial_uid": "T002",
                "time_s": 8.8,
                "sample_index": 388080,
                "soa_ms": "800",
                "family": "baseline",
                "row_label": "Exhale",
            },
            {
                "trial_number": 1,
                "trial_uid": "T001",
                "time_s": 4.3,
                "sample_index": 189630,
                "soa_ms": "300",
                "family": "audio_tactile",
                "row_label": "Inhale",
            },
        ],
    )

    assert state.part_number == "2"
    assert state.phase_label == "Condition 2"
    assert state.block_index == "7"
    assert [cue.trial_number for cue in state.cues] == [1, 2]
    assert [cue.family for cue in state.cues] == ["audio_tactile", "baseline"]
    assert state.next_cue().trial_uid == "T001"


def test_tactile_recenter_controller_fires_once_per_due_cue():
    state = TactileTimelineState(recenter_lead_s=0.5)
    state.load_block(
        duration_s=12.0,
        tactile_events=[
            {"trial_number": 1, "trial_uid": "T001", "time_s": 4.3},
            {"trial_number": 2, "trial_uid": "T002", "time_s": 8.8},
        ],
    )
    moved: list[int] = []
    controller = TactileRecenterController(state, lambda cue: moved.append(cue.trial_number))

    assert controller.tick(3.7, active=True) == []
    assert [cue.trial_number for cue in controller.tick(3.8, active=True)] == [1]
    assert controller.tick(3.9, active=True) == []
    assert [cue.trial_number for cue in controller.tick(8.3, active=True)] == [2]
    assert controller.tick(8.4, active=True) == []
    assert moved == [1, 2]


def test_tactile_recenter_controller_respects_pause_and_instruction_wait():
    state = TactileTimelineState(recenter_lead_s=0.5)
    state.load_block(duration_s=6.0, tactile_events=[{"trial_number": 1, "time_s": 4.0}])
    moved: list[int] = []
    controller = TactileRecenterController(state, lambda cue: moved.append(cue.trial_number))

    assert controller.tick(3.5, active=True, paused=True) == []
    assert controller.tick(3.6, active=True, instruction_waiting=True) == []
    assert moved == []
    assert [cue.trial_number for cue in controller.tick(3.7, active=True)] == [1]
    assert moved == [1]
