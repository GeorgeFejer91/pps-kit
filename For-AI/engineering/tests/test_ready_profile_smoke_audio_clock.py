from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import soundfile as sf


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "For-AI/engineering/validation/scripts/run_ready_profile_runner_smoke.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("run_ready_profile_runner_smoke", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Clock:
    """Only the harness engine's clock/wait is controlled, not Python time globally."""

    def __init__(self):
        self.now = 1000.0
        self.cancel_at = None
        self.stopped = False

    def perf_counter(self):
        return self.now

    def wait(self, timeout):
        if self.cancel_at is not None and self.now + timeout >= self.cancel_at:
            self.now = self.cancel_at
            self.stopped = True
        elif not self.stopped:
            self.now += timeout
        return self.stopped

    def set(self):
        self.stopped = True


def _fixture(tmp_path, monkeypatch):
    smoke = _load_script()
    from peripersonal_space_toolkit.timing_schedule import BlockEventSchedule, ScheduledBlockEvent

    clock = Clock()
    monkeypatch.setattr(smoke, "time", clock)
    monkeypatch.setattr(smoke, "threading", SimpleNamespace(Event=lambda: clock), raising=False)
    path = tmp_path / "silent.wav"
    sf.write(path, np.zeros((8000, 3), dtype=np.float32), 1000)
    events = [ScheduledBlockEvent("audio_sample_zero", 0, "zero", {"block_number": 1})]
    for uid, sample in [("missed", 1000), ("selected", 4000)]:
        events.append(ScheduledBlockEvent("tactile_onset", sample, uid, {
            "trial_uid": uid, "block_number": 1, "planned_sample_index": sample,
        }))
    events.append(ScheduledBlockEvent("trial_end", 7999, "end", {"block_number": 1}))
    return smoke, clock, path, BlockEventSchedule(events)


def test_unanswered_trial_cannot_steal_next_trial_click(tmp_path, monkeypatch):
    smoke, clock, path, schedule = _fixture(tmp_path, monkeypatch)
    from peripersonal_space_toolkit.session_analysis import _pair_tactile_responses

    engine = smoke.FastProfileSmokeAudioEngine(max_clicks_per_block=100)
    callbacks, analysis_events = [], []

    def emit(payload):
        callbacks.append(dict(payload))
        analysis_events.append({
            **payload, "event_id": len(analysis_events) + 1,
            "unix_time": payload["stream_output_buffer_dac_time"],
        })

    def respond(payload):
        if payload["trial_uid"] == "selected":
            clock.now += 0.2
            analysis_events.append({
                "event_type": "mouse_click", "event_id": len(analysis_events) + 1,
                "unix_time": clock.now, "block_number": 1,
                "in_target": True, "during_playback": True,
            })
            engine.trigger_click(metadata={"block_number": 1})

    engine.set_tactile_callback(respond)
    assert engine.play_block(str(path), audio_event_callback=emit, block_event_schedule=schedule)
    rows = _pair_tactile_responses(analysis_events, min_rt_s=0.05, max_rt_s=2.0)
    assert [(row["trial_uid"], row["hit"]) for row in rows] == [("missed", False), ("selected", True)]
    assert rows[1]["rt_ms"] == 200.0
    tactile = [row for row in callbacks if row["event_type"] == "tactile_onset"]
    assert [row["sample_index"] for row in tactile] == [1000, 4000]
    assert [row["callback_perf_counter"] for row in tactile] == [1001.0, 1004.0]
    marker = next(row for row in callbacks if row["event_type"] == "response_marker_start")
    assert marker["sample_index"] == 4200
    assert clock.now == 1008.0  # Tail is part of the WAV even without another event.


def test_stop_during_gap_emits_no_future_events_or_completed_progress(tmp_path, monkeypatch):
    smoke, clock, path, schedule = _fixture(tmp_path, monkeypatch)
    engine = smoke.FastProfileSmokeAudioEngine(max_clicks_per_block=100)
    clock.cancel_at = 1002.0
    callbacks, progress = [], []
    assert not engine.play_block(str(path), progress_callback=progress.append,
                                 audio_event_callback=callbacks.append, block_event_schedule=schedule)
    assert [row["event_type"] for row in callbacks] == ["audio_sample_zero", "tactile_onset"]
    assert progress == [0.0]
    assert clock.now == 1002.0
