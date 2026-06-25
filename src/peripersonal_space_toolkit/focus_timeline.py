"""Live tactile timeline state for the native Focus Mode runner."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Callable


RECENTER_LEAD_S = 0.5
CLICK_RESPONSE_MIN_RT_S = 0.1
CLICK_RESPONSE_MAX_RT_S = 4.0
CLICK_RESPONSE_EPSILON_S = 0.001


@dataclass
class TactileTimelineCue:
    cue_id: int
    trial_number: int
    trial_uid: str
    time_s: float
    sample_index: int | None = None
    soa_ms: str = ""
    family: str = ""
    row_label: str = ""
    clip_label: str = ""
    trial_label: str = ""
    noise_type: str = ""
    recentered: bool = False


@dataclass
class TimelineTrialSegment:
    trial_number: int
    trial_uid: str
    start_s: float
    end_s: float
    clip_label: str = ""
    trial_label: str = ""
    noise_type: str = ""
    soa_ms: str = ""
    family: str = ""


@dataclass
class TimelineInstructionSegment:
    slot: str
    label: str
    start_s: float
    end_s: float
    color: str = ""


@dataclass
class TimelineClickMarker:
    click_id: int
    time_s: float
    trial_uid: str = ""
    response_status: str = "off_cue"
    cue_id: int | None = None
    cue_trial_uid: str = ""
    rt_s: float | None = None


class TactileTimelineState:
    """Mutable planned tactile-cue state for one currently playing block."""

    def __init__(self, *, recenter_lead_s: float = RECENTER_LEAD_S):
        self.recenter_lead_s = max(0.0, float(recenter_lead_s))
        self.part_number = ""
        self.phase_label = ""
        self.block_index = ""
        self.block_label = ""
        self.duration_s = 0.0
        self.elapsed_s = 0.0
        self.active = False
        self.instruction_segments: list[TimelineInstructionSegment] = []
        self.cues: list[TactileTimelineCue] = []
        self.trial_segments: list[TimelineTrialSegment] = []
        self.click_markers: list[TimelineClickMarker] = []

    def load_block(
        self,
        *,
        part_number: Any = "",
        phase_label: Any = "",
        block_index: Any = "",
        block_label: Any = "",
        duration_s: Any = 0.0,
        instruction_segments: list[dict[str, Any]] | None = None,
        tactile_events: list[dict[str, Any]] | None = None,
        trial_segments: list[dict[str, Any]] | None = None,
    ) -> None:
        self.part_number = str(part_number or "").strip()
        self.phase_label = str(phase_label or "").strip()
        self.block_index = str(block_index or "").strip()
        self.block_label = str(block_label or "").strip()
        self.duration_s = max(0.0, _float(duration_s, default=0.0))
        self.elapsed_s = 0.0
        self.active = True
        instructions: list[TimelineInstructionSegment] = []
        for segment in instruction_segments or []:
            start_s = _float(segment.get("start_s"), default=math.nan)
            end_s = _float(segment.get("end_s"), default=math.nan)
            if not math.isfinite(start_s) or start_s < 0:
                continue
            if not math.isfinite(end_s) or end_s <= start_s:
                end_s = start_s + 0.001
            instructions.append(
                TimelineInstructionSegment(
                    slot=str(segment.get("slot") or "").strip(),
                    label=str(segment.get("label") or segment.get("slot") or "Instruction").strip(),
                    start_s=start_s,
                    end_s=end_s,
                    color=str(segment.get("color") or "").strip(),
                )
            )
        self.instruction_segments = sorted(instructions, key=lambda item: (item.start_s, item.end_s, item.slot))
        cues: list[TactileTimelineCue] = []
        for index, event in enumerate(tactile_events or [], start=1):
            time_s = _float(event.get("time_s"), default=math.nan)
            if not math.isfinite(time_s) or time_s < 0:
                continue
            cues.append(
                TactileTimelineCue(
                    cue_id=index,
                    trial_number=_int(event.get("trial_number"), default=index),
                    trial_uid=str(event.get("trial_uid") or ""),
                    time_s=time_s,
                    sample_index=_optional_int(event.get("sample_index")),
                    soa_ms=str(event.get("soa_ms") or ""),
                    family=str(event.get("family") or ""),
                    row_label=str(event.get("row_label") or ""),
                    clip_label=str(event.get("clip_label") or ""),
                    trial_label=str(event.get("trial_label") or event.get("row_label") or ""),
                    noise_type=str(event.get("noise_type") or event.get("Noise_Type") or "").strip(),
                )
            )
        self.cues = sorted(cues, key=lambda cue: (cue.time_s, cue.trial_number, cue.cue_id))
        for index, cue in enumerate(self.cues, start=1):
            cue.cue_id = index
        segments: list[TimelineTrialSegment] = []
        for index, segment in enumerate(trial_segments or [], start=1):
            start_s = _float(segment.get("start_s"), default=math.nan)
            end_s = _float(segment.get("end_s"), default=math.nan)
            if not math.isfinite(start_s) or start_s < 0:
                continue
            if not math.isfinite(end_s) or end_s <= start_s:
                end_s = start_s + 0.001
            segments.append(
                TimelineTrialSegment(
                    trial_number=_int(segment.get("trial_number"), default=index),
                    trial_uid=str(segment.get("trial_uid") or ""),
                    start_s=start_s,
                    end_s=end_s,
                    clip_label=str(segment.get("clip_label") or ""),
                    trial_label=str(segment.get("trial_label") or segment.get("row_label") or ""),
                    noise_type=str(segment.get("noise_type") or segment.get("Noise_Type") or "").strip(),
                    soa_ms=str(segment.get("soa_ms") or segment.get("SOA_ms") or "").strip(),
                    family=str(segment.get("family") or ""),
                )
            )
        self.trial_segments = sorted(segments, key=lambda item: (item.start_s, item.trial_number, item.trial_uid))
        self.click_markers = []

    def clear(self) -> None:
        self.part_number = ""
        self.phase_label = ""
        self.block_index = ""
        self.block_label = ""
        self.duration_s = 0.0
        self.elapsed_s = 0.0
        self.active = False
        self.instruction_segments = []
        self.cues = []
        self.trial_segments = []
        self.click_markers = []

    def update_elapsed(self, elapsed_s: Any) -> None:
        self.elapsed_s = max(0.0, _float(elapsed_s, default=0.0))
        if self.duration_s > 0 and self.elapsed_s >= self.duration_s:
            self.active = False

    def next_cue(self) -> TactileTimelineCue | None:
        for cue in self.cues:
            if cue.time_s >= self.elapsed_s:
                return cue
        return None

    def passed_count(self) -> int:
        return sum(1 for cue in self.cues if cue.time_s < self.elapsed_s)

    def recentered_count(self) -> int:
        return sum(1 for cue in self.cues if cue.recentered)

    def click_count(self) -> int:
        return len(self.click_markers)

    def segment_at(self, time_s: Any) -> TimelineTrialSegment | None:
        value = max(0.0, _float(time_s, default=0.0))
        for segment in self.trial_segments:
            if segment.start_s <= value <= segment.end_s:
                return segment
        return None

    def record_click(self, elapsed_s: Any, *, trial_uid: str = "") -> TimelineClickMarker:
        time_s = max(0.0, _float(elapsed_s, default=self.elapsed_s))
        if self.duration_s > 0:
            time_s = min(time_s, self.duration_s)
        clean_uid = str(trial_uid or "").strip()
        if not clean_uid:
            segment = self.segment_at(time_s)
            clean_uid = segment.trial_uid if segment is not None else ""
        status, cue, rt_s = self._classify_click_response(time_s, clean_uid)
        marker = TimelineClickMarker(
            click_id=len(self.click_markers) + 1,
            time_s=time_s,
            trial_uid=clean_uid,
            response_status=status,
            cue_id=cue.cue_id if cue is not None else None,
            cue_trial_uid=cue.trial_uid if cue is not None else "",
            rt_s=rt_s,
        )
        self.click_markers.append(marker)
        return marker

    def _classify_click_response(
        self,
        time_s: float,
        trial_uid: str,
    ) -> tuple[str, TactileTimelineCue | None, float | None]:
        clean_uid = str(trial_uid or "").strip()
        best: tuple[float, TactileTimelineCue] | None = None
        for cue in self.cues:
            if clean_uid and cue.trial_uid and clean_uid != cue.trial_uid:
                continue
            rt_s = float(time_s) - float(cue.time_s)
            if rt_s < CLICK_RESPONSE_MIN_RT_S - CLICK_RESPONSE_EPSILON_S:
                continue
            if rt_s > CLICK_RESPONSE_MAX_RT_S + CLICK_RESPONSE_EPSILON_S:
                continue
            segment = self.segment_at(time_s)
            if segment is not None and cue.trial_uid and segment.trial_uid and segment.trial_uid != cue.trial_uid:
                continue
            if best is None or rt_s < best[0]:
                best = (rt_s, cue)
        if best is None:
            return "off_cue", None, None
        return "tactile_response", best[1], best[0]

    def due_recenter_cues(self) -> list[TactileTimelineCue]:
        due: list[TactileTimelineCue] = []
        if not self.active:
            return due
        for cue in self.cues:
            if cue.recentered:
                continue
            if self.elapsed_s < max(0.0, cue.time_s - self.recenter_lead_s):
                continue
            if self.elapsed_s >= cue.time_s:
                continue
            due.append(cue)
        return due

    def mark_recentered(self, cue: TactileTimelineCue) -> None:
        cue.recentered = True

    def cue_status(self, cue: TactileTimelineCue) -> str:
        if cue.time_s < self.elapsed_s:
            return "passed"
        if cue.recentered:
            return "recentered"
        if self.next_cue() is cue:
            return "next"
        return "upcoming"


class TactileRecenterController:
    """Calls an injected cursor mover once per due tactile cue."""

    def __init__(
        self,
        state: TactileTimelineState,
        move_cursor: Callable[[TactileTimelineCue], None],
    ):
        self.state = state
        self.move_cursor = move_cursor

    def tick(
        self,
        elapsed_s: Any,
        *,
        active: bool,
        paused: bool = False,
        instruction_waiting: bool = False,
    ) -> list[TactileTimelineCue]:
        self.state.update_elapsed(elapsed_s)
        if not active or paused or instruction_waiting:
            return []
        moved: list[TactileTimelineCue] = []
        for cue in self.state.due_recenter_cues():
            self.move_cursor(cue)
            self.state.mark_recentered(cue)
            moved.append(cue)
        return moved


def _float(value: Any, *, default: float) -> float:
    try:
        result = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _int(value: Any, *, default: int) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    result = _int(value, default=-1)
    return result if result >= 0 else None
