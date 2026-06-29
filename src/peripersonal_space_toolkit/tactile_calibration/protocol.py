"""Participant-specific tactile detection-threshold calibration protocol."""

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
    DEFAULT_POST_SILENCE_MS,
    DEFAULT_PRE_SILENCE_MS,
    DEFAULT_PULSE_DURATION_MS,
    FAMILIARIZATION_MIN_LEVEL_PERCENT,
    FAMILIARIZATION_TRIAL_COUNT,
    INTER_TRIAL_INTERVAL_MAX_MS,
    INTER_TRIAL_INTERVAL_MIN_MS,
    MAX_CALIBRATION_EVENTS,
    PROTOCOL_NAME,
    SEARCH_LEVELS_PERCENT,
    STAIRCASE_CATCH_INTERVAL_SIGNALS,
    STAIRCASE_DOWN_AFTER_HITS,
    STAIRCASE_MAX_FALSE_ALARMS,
    STAIRCASE_MIN_CATCH_TRIALS,
    STAIRCASE_REVERSALS_TO_AVERAGE,
    STAIRCASE_STOP_REVERSALS,
    STAIRCASE_TARGET_DETECTION_RATE,
    STAIRCASE_UP_AFTER_MISSES,
    VALID_RESPONSE_END_MS,
    VALID_RESPONSE_START_MS,
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
        candidate_level_percent: float | None = None,
        inter_trial_interval_ms: float | None = None,
        staircase_index: int | None = None,
        staircase_direction: str = "",
        reversal_index: int | None = None,
        consecutive_hits: int | None = None,
        consecutive_misses: int | None = None,
        step_index: int | None = None,
    ) -> dict[str, Any]:
        self._check_cancelled()
        wav_path = temp_dir / f"trial_{trial_index:03d}_{phase}.wav"
        pre_silence_ms = self._pre_silence_ms_for_interval(inter_trial_interval_ms)
        stimulus = write_calibration_trial_wav(
            wav_path,
            level_percent=level_percent,
            is_catch=is_catch,
            source_pulse_path=self.source_pulse_path,
            pre_silence_ms=pre_silence_ms,
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
        phase_label = "threshold staircase" if phase == "staircase" else phase
        self._progress(
            f"Tactile {phase_label}: trial {trial_index}, level {level_percent:g}%",
            trial_index=trial_index,
            phase=phase,
            level_percent=level_percent,
            is_catch=is_catch,
            candidate_level_percent="" if candidate_level_percent is None else float(candidate_level_percent),
            inter_trial_interval_ms="" if inter_trial_interval_ms is None else float(inter_trial_interval_ms),
            staircase_index="" if staircase_index is None else int(staircase_index),
            staircase_direction=str(staircase_direction or ""),
            reversal_index="" if reversal_index is None else int(reversal_index),
            consecutive_hits="" if consecutive_hits is None else int(consecutive_hits),
            consecutive_misses="" if consecutive_misses is None else int(consecutive_misses),
            step_index="" if step_index is None else int(step_index),
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
        response_present = isinstance(response, dict)
        valid = bool(response.get("valid_response")) if isinstance(response, dict) else False
        if is_catch:
            outcome = "false_alarm" if valid else "catch_response_out_of_window" if response_present else "correct_reject"
        else:
            outcome = "hit" if valid else "miss"
        trial = {
            "trial_index": trial_index,
            "phase": phase,
            "level_percent": float(level_percent),
            "candidate_level_percent": "" if candidate_level_percent is None else float(candidate_level_percent),
            "staircase_index": "" if staircase_index is None else int(staircase_index),
            "staircase_direction": str(staircase_direction or ""),
            "reversal_index": "" if reversal_index is None else int(reversal_index),
            "consecutive_hits": "" if consecutive_hits is None else int(consecutive_hits),
            "consecutive_misses": "" if consecutive_misses is None else int(consecutive_misses),
            "step_index": "" if step_index is None else int(step_index),
            "is_catch": bool(is_catch),
            "pulse_present": not bool(is_catch),
            "inter_trial_interval_ms": "" if inter_trial_interval_ms is None else float(inter_trial_interval_ms),
            "estimated_onset_perf": onset_perf,
            "valid_start_perf": valid_start,
            "valid_end_perf": valid_end,
            "response_perf": response_perf,
            "response_latency_ms": latency_ms,
            "valid_response": valid,
            "response_present": response_present,
            "trial_outcome": outcome,
        }
        self.trials.append(trial)
        return trial

    def _next_inter_trial_interval_ms(self) -> float:
        return float(self.rng.uniform(INTER_TRIAL_INTERVAL_MIN_MS, INTER_TRIAL_INTERVAL_MAX_MS))

    def _pre_silence_ms_for_interval(self, inter_trial_interval_ms: float | None) -> float:
        if inter_trial_interval_ms is None:
            return float(DEFAULT_PRE_SILENCE_MS)
        prior_tail_ms = float(DEFAULT_PULSE_DURATION_MS) + float(DEFAULT_POST_SILENCE_MS)
        return max(0.0, float(inter_trial_interval_ms) - prior_tail_ms)

    def _starting_level_index(self, levels: list[float]) -> int:
        start_level = min(100.0, max(FAMILIARIZATION_MIN_LEVEL_PERCENT, self.current_output_34_percent))
        for index, level in enumerate(levels):
            if level >= start_level:
                return index
        return max(0, len(levels) - 1)

    def _staircase_summary(
        self,
        *,
        signal_trials: int,
        catch_trials: int,
        hits: int,
        misses: int,
        false_alarms: int,
        reversal_levels: list[float],
        reversal_trial_indices: list[int],
        threshold_estimate: float | None,
    ) -> dict[str, Any]:
        used_reversals = reversal_levels[-STAIRCASE_REVERSALS_TO_AVERAGE:]
        return {
            "target_detection_rate": STAIRCASE_TARGET_DETECTION_RATE,
            "down_after_hits": STAIRCASE_DOWN_AFTER_HITS,
            "up_after_misses": STAIRCASE_UP_AFTER_MISSES,
            "signal_trials": int(signal_trials),
            "catch_trials": int(catch_trials),
            "hits": int(hits),
            "misses": int(misses),
            "false_alarms": int(false_alarms),
            "hit_rate": hits / signal_trials if signal_trials else 0.0,
            "false_alarm_rate": false_alarms / catch_trials if catch_trials else 0.0,
            "reversals": len(reversal_levels),
            "reversal_levels_percent": [float(level) for level in reversal_levels],
            "reversal_trial_indices": [int(index) for index in reversal_trial_indices],
            "reversal_levels_used_percent": [float(level) for level in used_reversals],
            "threshold_estimator": f"mean_last_{STAIRCASE_REVERSALS_TO_AVERAGE}_reversals",
            "threshold_estimate_output_34_percent": "" if threshold_estimate is None else float(threshold_estimate),
            "passed": threshold_estimate is not None and false_alarms <= STAIRCASE_MAX_FALSE_ALARMS,
        }

    def _has_event_capacity(self, trial_index: int, needed: int = 1) -> bool:
        return int(trial_index) + int(needed) <= int(MAX_CALIBRATION_EVENTS)

    def run(self) -> dict[str, Any]:
        levels = [float(level) for level in SEARCH_LEVELS_PERCENT]
        trial_index = 0
        accepted_level: float | None = None
        threshold_estimate: float | None = None
        status = "inconclusive_max_events"
        message = f"Tactile threshold staircase reached the {MAX_CALIBRATION_EVENTS} event cap before converging."
        current_index = self._starting_level_index(levels)
        starting_level = levels[current_index]
        last_step_direction = ""
        consecutive_hits = 0
        consecutive_misses = 0
        step_index = 0
        signal_trials = 0
        catch_trials = 0
        hits = 0
        misses = 0
        false_alarms = 0
        next_catch_after_signal_count = STAIRCASE_CATCH_INTERVAL_SIGNALS
        reversal_levels: list[float] = []
        reversal_trial_indices: list[int] = []
        with tempfile.TemporaryDirectory(prefix="pps_tactile_calibration_") as temp_text:
            temp_dir = Path(temp_text)
            familiarization_level = min(100.0, max(FAMILIARIZATION_MIN_LEVEL_PERCENT, self.current_output_34_percent))
            for _ in range(FAMILIARIZATION_TRIAL_COUNT):
                if not self._has_event_capacity(trial_index):
                    status = "inconclusive_max_events"
                    message = f"Tactile threshold assay reached the {MAX_CALIBRATION_EVENTS} event cap during familiarization."
                    break
                trial_index += 1
                self._play_trial(
                    temp_dir,
                    trial_index=trial_index,
                    phase="familiarization",
                    level_percent=familiarization_level,
                )
            else:
                while self._has_event_capacity(trial_index):
                    if len(reversal_levels) >= STAIRCASE_STOP_REVERSALS and catch_trials >= STAIRCASE_MIN_CATCH_TRIALS:
                        break
                    level = levels[current_index]
                    if (
                        catch_trials < STAIRCASE_MIN_CATCH_TRIALS
                        and signal_trials >= next_catch_after_signal_count
                    ):
                        trial_index += 1
                        trial = self._play_trial(
                            temp_dir,
                            trial_index=trial_index,
                            phase="staircase",
                            level_percent=level,
                            is_catch=True,
                            candidate_level_percent=level,
                            inter_trial_interval_ms=self._next_inter_trial_interval_ms(),
                            staircase_index=current_index,
                            reversal_index=len(reversal_levels),
                            consecutive_hits=consecutive_hits,
                            consecutive_misses=consecutive_misses,
                            step_index=step_index,
                        )
                        catch_trials += 1
                        next_catch_after_signal_count += STAIRCASE_CATCH_INTERVAL_SIGNALS
                        if bool(trial.get("valid_response")):
                            false_alarms += 1
                        if false_alarms > STAIRCASE_MAX_FALSE_ALARMS:
                            status = "invalid_false_alarm"
                            message = (
                                "Tactile threshold staircase invalidated by a click during a catch trial; "
                                "repeat after reinstruction."
                            )
                            break
                        continue

                    trial_index += 1
                    level = levels[current_index]
                    trial = self._play_trial(
                        temp_dir,
                        trial_index=trial_index,
                        phase="staircase",
                        level_percent=level,
                        inter_trial_interval_ms=self._next_inter_trial_interval_ms(),
                        staircase_index=current_index,
                        reversal_index=len(reversal_levels),
                        consecutive_hits=consecutive_hits,
                        consecutive_misses=consecutive_misses,
                        step_index=step_index,
                    )
                    signal_trials += 1
                    step_direction = ""
                    if bool(trial.get("valid_response")):
                        hits += 1
                        consecutive_hits += 1
                        consecutive_misses = 0
                        if consecutive_hits >= STAIRCASE_DOWN_AFTER_HITS:
                            step_direction = "down"
                            consecutive_hits = 0
                    else:
                        misses += 1
                        consecutive_misses += 1
                        consecutive_hits = 0
                        if consecutive_misses >= STAIRCASE_UP_AFTER_MISSES:
                            step_direction = "up"
                            consecutive_misses = 0

                    if step_direction:
                        next_index = current_index - 1 if step_direction == "down" else current_index + 1
                        next_index = max(0, min(len(levels) - 1, next_index))
                        if next_index != current_index:
                            step_index += 1
                            if last_step_direction and step_direction != last_step_direction:
                                reversal_levels.append(float(level))
                                reversal_trial_indices.append(int(trial_index))
                                trial["reversal_index"] = len(reversal_levels)
                            last_step_direction = step_direction
                            current_index = next_index
                        else:
                            step_direction = f"{step_direction}_limit"
                    trial["staircase_direction"] = step_direction
                    trial["consecutive_hits"] = consecutive_hits
                    trial["consecutive_misses"] = consecutive_misses
                    trial["step_index"] = step_index

                if status != "invalid_false_alarm":
                    if len(reversal_levels) >= STAIRCASE_STOP_REVERSALS and catch_trials >= STAIRCASE_MIN_CATCH_TRIALS:
                        used_reversals = reversal_levels[-STAIRCASE_REVERSALS_TO_AVERAGE:]
                        threshold_estimate = sum(used_reversals) / len(used_reversals)
                        accepted_level = float(threshold_estimate)
                        status = "accepted"
                        message = (
                            f"Accepted adaptive tactile threshold at Output 3/4 level {accepted_level:g}% "
                            f"from {len(reversal_levels)} staircase reversals."
                        )
                    elif hits == 0:
                        status = "failed_no_detection"
                        message = "Participant did not report feeling the tactile pulse during the staircase."

        staircase_summary = self._staircase_summary(
            signal_trials=signal_trials,
            catch_trials=catch_trials,
            hits=hits,
            misses=misses,
            false_alarms=false_alarms,
            reversal_levels=reversal_levels,
            reversal_trial_indices=reversal_trial_indices,
            threshold_estimate=threshold_estimate,
        )
        threshold_value: float | str = "" if accepted_level is None else accepted_level
        report = {
            "schema": CALIBRATION_SCHEMA,
            "participant_id": self.participant_id,
            "created_at": self.created_at,
            "completed_at": datetime.now().isoformat(timespec="seconds"),
            "protocol": PROTOCOL_NAME,
            "accepted": accepted_level is not None,
            "status": status,
            "message": message,
            "threshold_method": "two_down_one_up_transformed_adaptive_staircase_with_catches",
            "threshold_definition": (
                f"Mean of the last {STAIRCASE_REVERSALS_TO_AVERAGE} reversal levels from a 2-down/1-up "
                "adaptive staircase targeting approximately 70.7% tactile detection; catch false alarms invalidate the attempt."
            ),
            "search_levels_percent": levels,
            "staircase_levels_percent": levels,
            "starting_level_percent": starting_level,
            "max_calibration_events": MAX_CALIBRATION_EVENTS,
            "timing": {
                "pulse_duration_ms": DEFAULT_PULSE_DURATION_MS,
                "valid_response_start_ms": VALID_RESPONSE_START_MS,
                "valid_response_end_ms": VALID_RESPONSE_END_MS,
                "inter_trial_interval_min_ms": INTER_TRIAL_INTERVAL_MIN_MS,
                "inter_trial_interval_max_ms": INTER_TRIAL_INTERVAL_MAX_MS,
            },
            "adaptive_staircase": {
                "target_detection_rate": STAIRCASE_TARGET_DETECTION_RATE,
                "down_after_hits": STAIRCASE_DOWN_AFTER_HITS,
                "up_after_misses": STAIRCASE_UP_AFTER_MISSES,
                "stop_reversals": STAIRCASE_STOP_REVERSALS,
                "reversals_to_average": STAIRCASE_REVERSALS_TO_AVERAGE,
                "minimum_catch_trials": STAIRCASE_MIN_CATCH_TRIALS,
                "catch_interval_signal_trials": STAIRCASE_CATCH_INTERVAL_SIGNALS,
                "max_false_alarms": STAIRCASE_MAX_FALSE_ALARMS,
                "valid_response_start_ms": VALID_RESPONSE_START_MS,
                "valid_response_end_ms": VALID_RESPONSE_END_MS,
            },
            "final_output_34_percent": threshold_value,
            "detection_threshold_output_34_percent": threshold_value,
            "recommended_output_34_percent": threshold_value,
            "confirmation_level_output_34_percent": threshold_value,
            "staircase_hit_rate": staircase_summary.get("hit_rate", ""),
            "staircase_false_alarm_rate": staircase_summary.get("false_alarm_rate", ""),
            "staircase_summary": staircase_summary,
            "confirmation_hit_rate": "",
            "confirmation_false_alarm_rate": "",
            "validation_hit_rate": staircase_summary.get("hit_rate", ""),
            "validation_false_alarm_rate": staircase_summary.get("false_alarm_rate", ""),
            "confirmation_summary": {},
            "validation_summary": staircase_summary,
            "trial_count": len(self.trials),
            "rng_seed": self.rng_seed,
            "output_root": self.output_root,
            "playback_output_levels_before": self.playback_output_levels_before,
            "stimuli": self.stimuli,
            **self.package_context,
        }
        return {"report": report, "trials": list(self.trials)}


def run_quick_tactile_calibration(**kwargs: Any) -> dict[str, Any]:
    return TactileCalibrationRunner(**kwargs).run()
