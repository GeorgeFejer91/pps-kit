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
    CALIBRATION_MAX_FALSE_ALARMS,
    CONFIRMATION_LEVEL_INCREMENT_PERCENT,
    CONFIRMATION_REQUIRED_CLEAN_CATCHES,
    CONFIRMATION_REQUIRED_CONSECUTIVE_HITS,
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
    STAIRCASE_LOWER_BOUND_HITS,
    STAIRCASE_MIN_CATCH_TRIALS,
    STAIRCASE_REVERSALS_TO_AVERAGE,
    STAIRCASE_STOP_REVERSALS,
    STAIRCASE_TARGET_DETECTION_RATE,
    STAIRCASE_UP_AFTER_MISSES,
    TACTILE_OUTPUT_34_MAX_PERCENT,
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
        recenter_callback: Any | None = None,
        cancel_event: threading.Event | None = None,
        rng_seed: int | None = None,
    ) -> None:
        self.audio_engine = audio_engine
        self.response_collector = response_collector
        self.participant_id = str(participant_id or "")
        self.output_root = str(output_root)
        self.source_pulse_path = Path(source_pulse_path) if source_pulse_path else None
        self.current_output_34_percent = max(
            0.0,
            min(float(TACTILE_OUTPUT_34_MAX_PERCENT), float(current_output_34_percent or 0.0)),
        )
        self.playback_output_levels_before = dict(playback_output_levels_before or {})
        self.package_context = dict(package_context or {})
        self.progress_callback = progress_callback
        self.recenter_callback = recenter_callback
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

    def _set_audio_engine_tactile_level(self, level_percent: float) -> None:
        gain = max(0.0, min(float(TACTILE_OUTPUT_34_MAX_PERCENT), float(level_percent or 0.0))) / 100.0
        setter = getattr(self.audio_engine, "set_tactile_volume", None)
        if callable(setter):
            setter(gain)
        else:
            setattr(self.audio_engine, "tactile_volume", gain)

    def _request_recenter(
        self,
        *,
        trial_index: int,
        phase: str,
        level_percent: float,
        is_catch: bool,
    ) -> dict[str, Any]:
        if not callable(self.recenter_callback):
            return {}
        try:
            result = self.recenter_callback(
                {
                    "trial_index": int(trial_index),
                    "phase": str(phase),
                    "level_percent": float(level_percent),
                    "is_catch": bool(is_catch),
                }
            )
        except Exception as exc:
            return {"mode": "failed", "error": str(exc)}
        return dict(result or {})

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
        confirmation_consecutive_hits: int | None = None,
        confirmation_clean_catches: int | None = None,
        confirmation_false_alarms: int | None = None,
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
            pulse_scale_percent=100.0,
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
        recenter_record = self._request_recenter(
            trial_index=trial_index,
            phase=phase,
            level_percent=level_percent,
            is_catch=is_catch,
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
            confirmation_consecutive_hits=(
                "" if confirmation_consecutive_hits is None else int(confirmation_consecutive_hits)
            ),
            confirmation_clean_catches="" if confirmation_clean_catches is None else int(confirmation_clean_catches),
            confirmation_false_alarms=(
                "" if confirmation_false_alarms is None else int(confirmation_false_alarms)
            ),
            max_calibration_events=MAX_CALIBRATION_EVENTS,
            recenter=dict(recenter_record),
        )
        play_block = getattr(self.audio_engine, "play_block", None)
        if not callable(play_block):
            raise RuntimeError("audio engine has no block playback API")
        try:
            self._set_audio_engine_tactile_level(0.0 if is_catch else level_percent)
            success = bool(play_block(str(wav_path)))
        finally:
            response = self.response_collector.wait_for_response(until_perf=valid_end)
            self.response_collector.finish_trial()
        if not success:
            raise RuntimeError("audio engine rejected tactile calibration trial playback")
        response_perf = response.get("response_perf") if isinstance(response, dict) else ""
        latency_ms = response.get("response_latency_ms") if isinstance(response, dict) else ""
        response_x = response.get("response_x", "") if isinstance(response, dict) else ""
        response_y = response.get("response_y", "") if isinstance(response, dict) else ""
        response_in_target = response.get("response_in_target", "") if isinstance(response, dict) else ""
        response_source = response.get("response_source", "") if isinstance(response, dict) else ""
        response_present = isinstance(response, dict)
        valid = bool(response.get("valid_response")) if isinstance(response, dict) else False
        if is_catch:
            outcome = "false_alarm" if valid else "catch_response_out_of_window" if response_present else "correct_reject"
        else:
            outcome = "hit" if valid else "miss"
        warning = "Only press when you feel the tactile pulse." if outcome == "false_alarm" else ""
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
            "confirmation_consecutive_hits": (
                "" if confirmation_consecutive_hits is None else int(confirmation_consecutive_hits)
            ),
            "confirmation_clean_catches": "" if confirmation_clean_catches is None else int(confirmation_clean_catches),
            "confirmation_false_alarms": (
                "" if confirmation_false_alarms is None else int(confirmation_false_alarms)
            ),
            "warning": warning,
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
            "response_x": response_x,
            "response_y": response_y,
            "response_in_target": response_in_target,
            "response_source": response_source,
            "recenter_mode": recenter_record.get("mode", ""),
            "recenter_x": recenter_record.get("x", ""),
            "recenter_y": recenter_record.get("y", ""),
            "recenter_coordinate_source": recenter_record.get("coordinate_source", ""),
        }
        self.trials.append(trial)
        self._progress(
            f"Tactile threshold trial {trial_index}: {outcome}",
            ui_event="trial_complete",
            **trial,
            max_calibration_events=MAX_CALIBRATION_EVENTS,
        )
        return trial

    def _next_inter_trial_interval_ms(self) -> float:
        return float(self.rng.uniform(INTER_TRIAL_INTERVAL_MIN_MS, INTER_TRIAL_INTERVAL_MAX_MS))

    def _pre_silence_ms_for_interval(self, inter_trial_interval_ms: float | None) -> float:
        if inter_trial_interval_ms is None:
            return float(DEFAULT_PRE_SILENCE_MS)
        prior_tail_ms = float(DEFAULT_PULSE_DURATION_MS) + float(DEFAULT_POST_SILENCE_MS)
        return max(0.0, float(inter_trial_interval_ms) - prior_tail_ms)

    def _starting_level_index(self, levels: list[float]) -> int:
        start_level = min(max(levels), max(FAMILIARIZATION_MIN_LEVEL_PERCENT, self.current_output_34_percent))
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
        threshold_censoring: str = "",
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
            "threshold_censoring": str(threshold_censoring or ""),
            "passed": threshold_estimate is not None and false_alarms < CALIBRATION_MAX_FALSE_ALARMS,
        }

    def _has_event_capacity(self, trial_index: int, needed: int = 1) -> bool:
        return int(trial_index) + int(needed) <= int(MAX_CALIBRATION_EVENTS)

    def _increase_confirmation_level(self, level_percent: float) -> float:
        return min(
            float(TACTILE_OUTPUT_34_MAX_PERCENT),
            round(float(level_percent) + float(CONFIRMATION_LEVEL_INCREMENT_PERCENT), 6),
        )

    def _confirmation_summary(
        self,
        *,
        signal_trials: int,
        catch_trials: int,
        hits: int,
        misses: int,
        false_alarms: int,
        clean_catches: int,
        consecutive_hits: int,
        final_level: float | None,
        passed: bool,
    ) -> dict[str, Any]:
        return {
            "required_consecutive_hits": CONFIRMATION_REQUIRED_CONSECUTIVE_HITS,
            "required_clean_catches": CONFIRMATION_REQUIRED_CLEAN_CATCHES,
            "level_increment_percent": CONFIRMATION_LEVEL_INCREMENT_PERCENT,
            "max_false_alarms": CALIBRATION_MAX_FALSE_ALARMS,
            "signal_trials": int(signal_trials),
            "catch_trials": int(catch_trials),
            "hits": int(hits),
            "misses": int(misses),
            "false_alarms": int(false_alarms),
            "clean_catches": int(clean_catches),
            "consecutive_hits": int(consecutive_hits),
            "hit_rate": hits / signal_trials if signal_trials else 0.0,
            "false_alarm_rate": false_alarms / catch_trials if catch_trials else 0.0,
            "confirmed_output_34_percent": "" if final_level is None else float(final_level),
            "passed": bool(passed),
        }

    def _run_confirmation(
        self,
        temp_dir: Path,
        *,
        trial_index: int,
        starting_level: float,
        cumulative_false_alarms: int,
    ) -> dict[str, Any]:
        current_level = max(0.0, min(float(TACTILE_OUTPUT_34_MAX_PERCENT), float(starting_level)))
        consecutive_hits = 0
        clean_catches = 0
        signal_trials = 0
        catch_trials = 0
        hits = 0
        misses = 0
        confirmation_false_alarms = 0
        signal_trials_since_catch = 0
        status = "inconclusive_max_events"
        message = f"Tactile threshold confirmation reached the {MAX_CALIBRATION_EVENTS} event cap before passing."
        accepted_level: float | None = None

        while self._has_event_capacity(trial_index):
            if (
                consecutive_hits >= CONFIRMATION_REQUIRED_CONSECUTIVE_HITS
                and clean_catches >= CONFIRMATION_REQUIRED_CLEAN_CATCHES
            ):
                accepted_level = float(current_level)
                status = "accepted"
                message = (
                    f"Accepted confirmed tactile task level at Output 3/4 {accepted_level:g}% "
                    f"after {CONFIRMATION_REQUIRED_CONSECUTIVE_HITS} consecutive hits and "
                    f"{CONFIRMATION_REQUIRED_CLEAN_CATCHES} clean catch trials."
                )
                break

            need_catches = clean_catches < CONFIRMATION_REQUIRED_CLEAN_CATCHES
            is_catch = bool(
                need_catches
                and (
                    signal_trials_since_catch >= 2
                    or consecutive_hits >= CONFIRMATION_REQUIRED_CONSECUTIVE_HITS
                )
            )
            trial_index += 1
            trial = self._play_trial(
                temp_dir,
                trial_index=trial_index,
                phase="confirmation",
                level_percent=current_level,
                is_catch=is_catch,
                candidate_level_percent=current_level,
                inter_trial_interval_ms=self._next_inter_trial_interval_ms(),
                confirmation_consecutive_hits=consecutive_hits,
                confirmation_clean_catches=clean_catches,
                confirmation_false_alarms=confirmation_false_alarms,
            )
            stop_after_trial = False
            if is_catch:
                catch_trials += 1
                signal_trials_since_catch = 0
                if bool(trial.get("valid_response")):
                    confirmation_false_alarms += 1
                    cumulative_false_alarms += 1
                    clean_catches = 0
                    if cumulative_false_alarms >= CALIBRATION_MAX_FALSE_ALARMS:
                        status = "invalid_false_alarm"
                        message = (
                            "Tactile threshold confirmation failed after repeated responses during catch trials; "
                            "repeat after reinstruction."
                        )
                        stop_after_trial = True
                else:
                    clean_catches += 1
            else:
                signal_trials += 1
                signal_trials_since_catch += 1
                if bool(trial.get("valid_response")):
                    hits += 1
                    consecutive_hits += 1
                else:
                    misses += 1
                    consecutive_hits = 0
                    if current_level >= float(TACTILE_OUTPUT_34_MAX_PERCENT):
                        status = "failed_confirmation_at_max"
                        message = (
                            f"Participant missed a confirmation pulse at the capped maximum "
                            f"{TACTILE_OUTPUT_34_MAX_PERCENT:g}% Output 3/4."
                        )
                        stop_after_trial = True
                    else:
                        current_level = self._increase_confirmation_level(current_level)
            trial["confirmation_consecutive_hits"] = consecutive_hits
            trial["confirmation_clean_catches"] = clean_catches
            trial["confirmation_false_alarms"] = confirmation_false_alarms
            self._progress(
                (
                    f"Tactile confirmation: Final hits {consecutive_hits}/"
                    f"{CONFIRMATION_REQUIRED_CONSECUTIVE_HITS}, clean catches {clean_catches}/"
                    f"{CONFIRMATION_REQUIRED_CLEAN_CATCHES}"
                ),
                ui_event="confirmation_update",
                **trial,
                next_level_percent=current_level,
                max_calibration_events=MAX_CALIBRATION_EVENTS,
            )
            if stop_after_trial:
                break

        summary = self._confirmation_summary(
            signal_trials=signal_trials,
            catch_trials=catch_trials,
            hits=hits,
            misses=misses,
            false_alarms=confirmation_false_alarms,
            clean_catches=clean_catches,
            consecutive_hits=consecutive_hits,
            final_level=accepted_level,
            passed=accepted_level is not None,
        )
        return {
            "trial_index": trial_index,
            "accepted_level": accepted_level,
            "status": status,
            "message": message,
            "summary": summary,
            "cumulative_false_alarms": cumulative_false_alarms,
        }

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
        lowest_level_hits = 0
        next_catch_after_signal_count = STAIRCASE_CATCH_INTERVAL_SIGNALS
        reversal_levels: list[float] = []
        reversal_trial_indices: list[int] = []
        threshold_censoring = ""
        confirmation_summary: dict[str, Any] = {}
        staircase_false_alarms = 0
        with tempfile.TemporaryDirectory(prefix="pps_tactile_calibration_") as temp_text:
            temp_dir = Path(temp_text)
            familiarization_level = min(max(levels), max(FAMILIARIZATION_MIN_LEVEL_PERCENT, self.current_output_34_percent))
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
                        if false_alarms >= CALIBRATION_MAX_FALSE_ALARMS:
                            status = "invalid_false_alarm"
                            message = (
                                "Tactile threshold staircase failed after repeated responses during catch trials; "
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
                        if current_index == 0:
                            lowest_level_hits += 1
                        else:
                            lowest_level_hits = 0
                        consecutive_hits += 1
                        consecutive_misses = 0
                        if consecutive_hits >= STAIRCASE_DOWN_AFTER_HITS:
                            step_direction = "down"
                            consecutive_hits = 0
                    else:
                        misses += 1
                        if current_index == 0:
                            lowest_level_hits = 0
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
                    if (
                        current_index == 0
                        and lowest_level_hits >= STAIRCASE_LOWER_BOUND_HITS
                        and catch_trials >= STAIRCASE_MIN_CATCH_TRIALS
                        and false_alarms < CALIBRATION_MAX_FALSE_ALARMS
                    ):
                        threshold_estimate = float(levels[0])
                        threshold_censoring = "lower_bound"
                        status = "staircase_lower_bound_censored"
                        message = (
                            f"Staircase estimated tactile threshold at <= {threshold_estimate:g}% Output 3/4; "
                            f"participant detected the lowest candidate level on {lowest_level_hits} signal trials."
                        )
                        break

                if status != "invalid_false_alarm":
                    if threshold_estimate is not None:
                        pass
                    elif len(reversal_levels) >= STAIRCASE_STOP_REVERSALS and catch_trials >= STAIRCASE_MIN_CATCH_TRIALS:
                        used_reversals = reversal_levels[-STAIRCASE_REVERSALS_TO_AVERAGE:]
                        threshold_estimate = sum(used_reversals) / len(used_reversals)
                        status = "staircase_converged"
                        message = (
                            f"Estimated adaptive tactile threshold at Output 3/4 level {threshold_estimate:g}% "
                            f"from {len(reversal_levels)} staircase reversals."
                        )
                    elif hits == 0:
                        status = "failed_no_detection_at_max"
                        message = (
                            f"Participant did not report feeling the tactile pulse during the staircase, "
                            f"including at the capped maximum {TACTILE_OUTPUT_34_MAX_PERCENT:g}% Output 3/4."
                        )
                if status != "invalid_false_alarm" and threshold_estimate is not None:
                    staircase_false_alarms = false_alarms
                    confirmation = self._run_confirmation(
                        temp_dir,
                        trial_index=trial_index,
                        starting_level=threshold_estimate,
                        cumulative_false_alarms=false_alarms,
                    )
                    trial_index = int(confirmation.get("trial_index") or trial_index)
                    accepted_level = confirmation.get("accepted_level")
                    status = str(confirmation.get("status") or status)
                    message = str(confirmation.get("message") or message)
                    confirmation_summary = dict(confirmation.get("summary") or {})
                    false_alarms = int(confirmation.get("cumulative_false_alarms") or false_alarms)

        staircase_summary = self._staircase_summary(
            signal_trials=signal_trials,
            catch_trials=catch_trials,
            hits=hits,
            misses=misses,
            false_alarms=staircase_false_alarms if confirmation_summary else false_alarms,
            reversal_levels=reversal_levels,
            reversal_trial_indices=reversal_trial_indices,
            threshold_estimate=threshold_estimate,
            threshold_censoring=threshold_censoring,
        )
        threshold_value: float | str = "" if threshold_estimate is None else threshold_estimate
        final_value: float | str = "" if accepted_level is None else accepted_level
        validation_summary = confirmation_summary or staircase_summary
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
                "adaptive staircase targeting approximately 70.7% tactile detection, followed by a same-session "
                f"confirmation requiring {CONFIRMATION_REQUIRED_CONSECUTIVE_HITS} consecutive hits and "
                f"{CONFIRMATION_REQUIRED_CLEAN_CATCHES} clean catch trials."
            ),
            "search_levels_percent": levels,
            "staircase_levels_percent": levels,
            "starting_level_percent": starting_level,
            "max_output_34_percent": TACTILE_OUTPUT_34_MAX_PERCENT,
            "output_level_control": "candidate_output_34_percent_sets_audio_engine_tactile_gain",
            "threshold_censoring": threshold_censoring,
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
                "lower_bound_hits": STAIRCASE_LOWER_BOUND_HITS,
                "minimum_catch_trials": STAIRCASE_MIN_CATCH_TRIALS,
                "catch_interval_signal_trials": STAIRCASE_CATCH_INTERVAL_SIGNALS,
                "max_false_alarms": CALIBRATION_MAX_FALSE_ALARMS,
                "valid_response_start_ms": VALID_RESPONSE_START_MS,
                "valid_response_end_ms": VALID_RESPONSE_END_MS,
            },
            "final_output_34_percent": final_value,
            "detection_threshold_output_34_percent": threshold_value,
            "recommended_output_34_percent": final_value,
            "confirmation_level_output_34_percent": final_value,
            "staircase_hit_rate": staircase_summary.get("hit_rate", ""),
            "staircase_false_alarm_rate": staircase_summary.get("false_alarm_rate", ""),
            "staircase_summary": staircase_summary,
            "confirmation_hit_rate": confirmation_summary.get("hit_rate", ""),
            "confirmation_false_alarm_rate": confirmation_summary.get("false_alarm_rate", ""),
            "validation_hit_rate": validation_summary.get("hit_rate", ""),
            "validation_false_alarm_rate": validation_summary.get("false_alarm_rate", ""),
            "confirmation_criteria": {
                "required_consecutive_hits": CONFIRMATION_REQUIRED_CONSECUTIVE_HITS,
                "required_clean_catches": CONFIRMATION_REQUIRED_CLEAN_CATCHES,
                "level_increment_percent": CONFIRMATION_LEVEL_INCREMENT_PERCENT,
                "max_false_alarms": CALIBRATION_MAX_FALSE_ALARMS,
            },
            "confirmation_summary": confirmation_summary,
            "validation_summary": validation_summary,
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
