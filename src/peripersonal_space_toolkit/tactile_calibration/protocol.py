"""Quick reliable tactile working-level calibration protocol."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import random
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Protocol

from .schema import (
    CALIBRATION_SCHEMA,
    PRACTICE_MIN_LEVEL_PERCENT,
    PRACTICE_TRIAL_COUNT,
    PROTOCOL_NAME,
    SEARCH_LEVELS_PERCENT,
    VALID_RESPONSE_END_MS,
    VALID_RESPONSE_START_MS,
    VALIDATION_CATCH_TRIALS,
    VALIDATION_MAX_FALSE_ALARMS,
    VALIDATION_MIN_HITS,
    VALIDATION_SIGNAL_TRIALS,
)
from .stimulus import write_calibration_trial_wav


class TactileCalibrationResponseCollector(Protocol):
    def start_trial(
        self,
        *,
        trial_index: int,
        phase: str,
        level_percent: float,
        is_catch: bool,
        estimated_onset_perf: float,
        valid_start_perf: float,
        valid_end_perf: float,
    ) -> None:
        ...

    def wait_for_response(self, *, until_perf: float) -> dict[str, Any] | None:
        ...

    def finish_trial(self) -> None:
        ...


class TactileCalibrationRunner:
    def __init__(
        self,
        *,
        audio_engine: Any,
        response_collector: TactileCalibrationResponseCollector,
        participant_id: str,
        output_root: Path | str,
        source_pulse_path: Path | str | None,
        current_output_34_percent: float,
        playback_output_levels_before: dict[str, Any] | None = None,
        package_context: dict[str, Any] | None = None,
        progress_callback: Any | None = None,
        cancel_event: threading.Event | None = None,
        rng_seed: int | None = None,
    ) -> None:
        self.audio_engine = audio_engine
        self.response_collector = response_collector
        self.participant_id = str(participant_id or "")
        self.output_root = str(output_root)
        self.source_pulse_path = Path(source_pulse_path) if source_pulse_path else None
        self.current_output_34_percent = max(0.0, min(100.0, float(current_output_34_percent or 0.0)))
        self.playback_output_levels_before = dict(playback_output_levels_before or {})
        self.package_context = dict(package_context or {})
        self.progress_callback = progress_callback
        self.cancel_event = cancel_event or threading.Event()
        self.created_at = datetime.now().isoformat(timespec="seconds")
        self.rng_seed = int(rng_seed if rng_seed is not None else time.time_ns() & 0xFFFFFFFF)
        self.rng = random.Random(self.rng_seed)
        self.trials: list[dict[str, Any]] = []
        self.stimuli: list[dict[str, Any]] = []

    def _progress(self, message: str, **payload: Any) -> None:
        if callable(self.progress_callback):
            self.progress_callback({"message": message, **payload})

    def _check_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise RuntimeError("calibration cancelled")

    def _play_trial(
        self,
        temp_dir: Path,
        *,
        trial_index: int,
        phase: str,
        level_percent: float,
        is_catch: bool = False,
    ) -> dict[str, Any]:
        self._check_cancelled()
        wav_path = temp_dir / f"trial_{trial_index:03d}_{phase}.wav"
        stimulus = write_calibration_trial_wav(
            wav_path,
            level_percent=level_percent,
            is_catch=is_catch,
            source_pulse_path=self.source_pulse_path,
        )
        self.stimuli.append(asdict(stimulus))
        start_perf = time.perf_counter()
        onset_perf = start_perf + (float(stimulus.pre_silence_ms) / 1000.0)
        valid_start = onset_perf + (VALID_RESPONSE_START_MS / 1000.0)
        valid_end = onset_perf + (VALID_RESPONSE_END_MS / 1000.0)
        self.response_collector.start_trial(
            trial_index=trial_index,
            phase=phase,
            level_percent=level_percent,
            is_catch=is_catch,
            estimated_onset_perf=onset_perf,
            valid_start_perf=valid_start,
            valid_end_perf=valid_end,
        )
        self._progress(
            f"Calibration {phase}: trial {trial_index}, level {level_percent:g}%",
            trial_index=trial_index,
            phase=phase,
            level_percent=level_percent,
            is_catch=is_catch,
        )
        play_block = getattr(self.audio_engine, "play_block", None)
        if not callable(play_block):
            raise RuntimeError("audio engine has no block playback API")
        try:
            success = bool(play_block(str(wav_path)))
        finally:
            response = self.response_collector.wait_for_response(until_perf=valid_end)
            self.response_collector.finish_trial()
        if not success:
            raise RuntimeError("audio engine rejected tactile calibration trial playback")
        response_perf = response.get("response_perf") if isinstance(response, dict) else ""
        latency_ms = response.get("response_latency_ms") if isinstance(response, dict) else ""
        valid = bool(response.get("valid_response")) if isinstance(response, dict) else False
        outcome = "false_alarm" if is_catch and valid else "hit" if valid else "correct_reject" if is_catch else "miss"
        trial = {
            "trial_index": trial_index,
            "phase": phase,
            "level_percent": float(level_percent),
            "is_catch": bool(is_catch),
            "estimated_onset_perf": onset_perf,
            "valid_start_perf": valid_start,
            "valid_end_perf": valid_end,
            "response_perf": response_perf,
            "response_latency_ms": latency_ms,
            "valid_response": valid,
            "trial_outcome": outcome,
        }
        self.trials.append(trial)
        return trial

    def _validation_passes(self, trials: list[dict[str, Any]]) -> tuple[bool, int, int, int, int]:
        signal = [trial for trial in trials if not bool(trial.get("is_catch"))]
        catch = [trial for trial in trials if bool(trial.get("is_catch"))]
        hits = sum(1 for trial in signal if bool(trial.get("valid_response")))
        false_alarms = sum(1 for trial in catch if bool(trial.get("valid_response")))
        return (
            hits >= VALIDATION_MIN_HITS and false_alarms <= VALIDATION_MAX_FALSE_ALARMS,
            hits,
            len(signal),
            false_alarms,
            len(catch),
        )

    def run(self) -> dict[str, Any]:
        levels = [float(level) for level in SEARCH_LEVELS_PERCENT]
        trial_index = 0
        accepted_level: float | None = None
        validation_summary: dict[str, Any] = {}
        status = "failed"
        message = "No tactile level passed validation."
        with tempfile.TemporaryDirectory(prefix="pps_tactile_calibration_") as temp_text:
            temp_dir = Path(temp_text)
            practice_level = min(100.0, max(PRACTICE_MIN_LEVEL_PERCENT, self.current_output_34_percent))
            for _ in range(PRACTICE_TRIAL_COUNT):
                trial_index += 1
                self._play_trial(temp_dir, trial_index=trial_index, phase="practice", level_percent=practice_level)
            first_detected_index = -1
            for level_index, level in enumerate(levels):
                trial_index += 1
                trial = self._play_trial(temp_dir, trial_index=trial_index, phase="search", level_percent=level)
                if bool(trial.get("valid_response")):
                    first_detected_index = level_index
                    break
            if first_detected_index < 0:
                message = "Participant did not report feeling the tactile pulse at any search level."
            else:
                for level in levels[first_detected_index:]:
                    validation_plan = [False] * VALIDATION_SIGNAL_TRIALS + [True] * VALIDATION_CATCH_TRIALS
                    self.rng.shuffle(validation_plan)
                    validation_trials: list[dict[str, Any]] = []
                    for is_catch in validation_plan:
                        trial_index += 1
                        validation_trials.append(
                            self._play_trial(
                                temp_dir,
                                trial_index=trial_index,
                                phase="validation",
                                level_percent=level,
                                is_catch=is_catch,
                            )
                        )
                    passed, hits, signal_n, false_alarms, catch_n = self._validation_passes(validation_trials)
                    validation_summary = {
                        "candidate_level_percent": float(level),
                        "hits": hits,
                        "signal_trials": signal_n,
                        "false_alarms": false_alarms,
                        "catch_trials": catch_n,
                        "hit_rate": hits / signal_n if signal_n else 0.0,
                        "false_alarm_rate": false_alarms / catch_n if catch_n else 0.0,
                    }
                    if passed:
                        accepted_level = float(level)
                        status = "accepted"
                        message = f"Accepted tactile Output 3/4 level {accepted_level:g}%."
                        break
        report = {
            "schema": CALIBRATION_SCHEMA,
            "participant_id": self.participant_id,
            "created_at": self.created_at,
            "completed_at": datetime.now().isoformat(timespec="seconds"),
            "protocol": PROTOCOL_NAME,
            "accepted": accepted_level is not None,
            "status": status,
            "message": message,
            "search_levels_percent": levels,
            "validation_criteria": {
                "signal_trials": VALIDATION_SIGNAL_TRIALS,
                "catch_trials": VALIDATION_CATCH_TRIALS,
                "min_hits": VALIDATION_MIN_HITS,
                "max_false_alarms": VALIDATION_MAX_FALSE_ALARMS,
                "valid_response_start_ms": VALID_RESPONSE_START_MS,
                "valid_response_end_ms": VALID_RESPONSE_END_MS,
            },
            "final_output_34_percent": "" if accepted_level is None else accepted_level,
            "validation_hit_rate": validation_summary.get("hit_rate", ""),
            "validation_false_alarm_rate": validation_summary.get("false_alarm_rate", ""),
            "validation_summary": validation_summary,
            "rng_seed": self.rng_seed,
            "output_root": self.output_root,
            "playback_output_levels_before": self.playback_output_levels_before,
            "stimuli": self.stimuli,
            **self.package_context,
        }
        return {"report": report, "trials": list(self.trials)}


def run_quick_tactile_calibration(**kwargs: Any) -> dict[str, Any]:
    return TactileCalibrationRunner(**kwargs).run()
