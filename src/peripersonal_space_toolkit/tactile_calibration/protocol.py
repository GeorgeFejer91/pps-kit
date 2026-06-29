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
    CONFIRMATION_CATCH_TRIALS,
    CONFIRMATION_MAX_FALSE_ALARMS,
    CONFIRMATION_REQUIRED_HITS,
    CONFIRMATION_SIGNAL_TRIALS,
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
        phase_label = "threshold" if phase == "confirmation" else phase
        self._progress(
            f"Tactile {phase_label}: trial {trial_index}, level {level_percent:g}%",
            trial_index=trial_index,
            phase=phase,
            level_percent=level_percent,
            is_catch=is_catch,
            candidate_level_percent="" if candidate_level_percent is None else float(candidate_level_percent),
            inter_trial_interval_ms="" if inter_trial_interval_ms is None else float(inter_trial_interval_ms),
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

    def _confirmation_summary(self, trials: list[dict[str, Any]], *, candidate_level_percent: float) -> dict[str, Any]:
        signal = [trial for trial in trials if not bool(trial.get("is_catch"))]
        catch = [trial for trial in trials if bool(trial.get("is_catch"))]
        hits = sum(1 for trial in signal if bool(trial.get("valid_response")))
        false_alarms = sum(1 for trial in catch if bool(trial.get("valid_response")))
        return {
            "candidate_level_percent": float(candidate_level_percent),
            "hits": hits,
            "signal_trials": len(signal),
            "false_alarms": false_alarms,
            "catch_trials": len(catch),
            "hit_rate": hits / len(signal) if signal else 0.0,
            "false_alarm_rate": false_alarms / len(catch) if catch else 0.0,
            "passed": hits >= CONFIRMATION_REQUIRED_HITS and false_alarms <= CONFIRMATION_MAX_FALSE_ALARMS,
        }

    def _has_event_capacity(self, trial_index: int, needed: int = 1) -> bool:
        return int(trial_index) + int(needed) <= int(MAX_CALIBRATION_EVENTS)

    def run(self) -> dict[str, Any]:
        levels = [float(level) for level in SEARCH_LEVELS_PERCENT]
        trial_index = 0
        accepted_level: float | None = None
        confirmation_summary: dict[str, Any] = {}
        candidate_summaries: list[dict[str, Any]] = []
        first_detected_level: float | None = None
        status = "failed"
        message = "No tactile level passed confirmation."
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
                first_detected_index = -1
                for level_index, level in enumerate(levels):
                    if not self._has_event_capacity(trial_index):
                        status = "inconclusive_max_events"
                        message = f"Tactile threshold assay reached the {MAX_CALIBRATION_EVENTS} event cap during ascending search."
                        break
                    trial_index += 1
                    trial = self._play_trial(
                        temp_dir,
                        trial_index=trial_index,
                        phase="search",
                        level_percent=level,
                        inter_trial_interval_ms=self._next_inter_trial_interval_ms(),
                    )
                    if bool(trial.get("valid_response")):
                        first_detected_index = level_index
                        first_detected_level = float(level)
                        break
                if first_detected_index < 0 and status != "inconclusive_max_events":
                    status = "failed_no_detection"
                    message = "Participant did not report feeling the tactile pulse at any search level."
                elif first_detected_index >= 0:
                    block_size = CONFIRMATION_SIGNAL_TRIALS + CONFIRMATION_CATCH_TRIALS
                    for level in levels[first_detected_index:]:
                        if not self._has_event_capacity(trial_index, block_size):
                            status = "inconclusive_max_events"
                            message = (
                                f"Tactile threshold assay reached the {MAX_CALIBRATION_EVENTS} event cap before "
                                f"confirmation at {level:g}% could be completed."
                            )
                            break
                        confirmation_plan = [False] * CONFIRMATION_SIGNAL_TRIALS + [True] * CONFIRMATION_CATCH_TRIALS
                        self.rng.shuffle(confirmation_plan)
                        confirmation_trials: list[dict[str, Any]] = []
                        for is_catch in confirmation_plan:
                            trial_index += 1
                            confirmation_trials.append(
                                self._play_trial(
                                    temp_dir,
                                    trial_index=trial_index,
                                    phase="confirmation",
                                    level_percent=level,
                                    is_catch=is_catch,
                                    candidate_level_percent=level,
                                    inter_trial_interval_ms=self._next_inter_trial_interval_ms(),
                                )
                            )
                        confirmation_summary = self._confirmation_summary(
                            confirmation_trials,
                            candidate_level_percent=level,
                        )
                        candidate_summaries.append(dict(confirmation_summary))
                        if int(confirmation_summary.get("false_alarms") or 0) > CONFIRMATION_MAX_FALSE_ALARMS:
                            status = "invalid_false_alarm"
                            message = (
                                "Tactile threshold assay invalidated by a click during a catch trial; "
                                "repeat after reinstruction."
                            )
                            break
                        if bool(confirmation_summary.get("passed")):
                            accepted_level = float(level)
                            status = "accepted"
                            message = f"Accepted tactile detection threshold at Output 3/4 level {accepted_level:g}%."
                            break
                    if accepted_level is None and status == "failed":
                        message = "No candidate level passed 10/10 tactile detections with 0/3 catch false alarms."
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
            "threshold_method": "ascending_search_plus_10_of_10_confirmation_with_catches",
            "threshold_definition": (
                "Lowest Output 3/4 percent with 10/10 confirmed tactile detections and 0/3 catch false alarms."
            ),
            "search_levels_percent": levels,
            "first_detected_level_percent": "" if first_detected_level is None else first_detected_level,
            "max_calibration_events": MAX_CALIBRATION_EVENTS,
            "timing": {
                "pulse_duration_ms": DEFAULT_PULSE_DURATION_MS,
                "valid_response_start_ms": VALID_RESPONSE_START_MS,
                "valid_response_end_ms": VALID_RESPONSE_END_MS,
                "inter_trial_interval_min_ms": INTER_TRIAL_INTERVAL_MIN_MS,
                "inter_trial_interval_max_ms": INTER_TRIAL_INTERVAL_MAX_MS,
            },
            "confirmation_criteria": {
                "signal_trials": CONFIRMATION_SIGNAL_TRIALS,
                "catch_trials": CONFIRMATION_CATCH_TRIALS,
                "required_hits": CONFIRMATION_REQUIRED_HITS,
                "max_false_alarms": CONFIRMATION_MAX_FALSE_ALARMS,
                "valid_response_start_ms": VALID_RESPONSE_START_MS,
                "valid_response_end_ms": VALID_RESPONSE_END_MS,
            },
            "validation_criteria": {
                "signal_trials": CONFIRMATION_SIGNAL_TRIALS,
                "catch_trials": CONFIRMATION_CATCH_TRIALS,
                "min_hits": CONFIRMATION_REQUIRED_HITS,
                "max_false_alarms": CONFIRMATION_MAX_FALSE_ALARMS,
                "valid_response_start_ms": VALID_RESPONSE_START_MS,
                "valid_response_end_ms": VALID_RESPONSE_END_MS,
            },
            "final_output_34_percent": threshold_value,
            "detection_threshold_output_34_percent": threshold_value,
            "recommended_output_34_percent": threshold_value,
            "confirmation_level_output_34_percent": threshold_value,
            "confirmation_hit_rate": confirmation_summary.get("hit_rate", ""),
            "confirmation_false_alarm_rate": confirmation_summary.get("false_alarm_rate", ""),
            "validation_hit_rate": confirmation_summary.get("hit_rate", ""),
            "validation_false_alarm_rate": confirmation_summary.get("false_alarm_rate", ""),
            "confirmation_summary": confirmation_summary,
            "validation_summary": confirmation_summary,
            "candidate_summaries": candidate_summaries,
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
