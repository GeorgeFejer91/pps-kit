"""Live tactile timeline state for the native Focus Mode runner."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Callable


RECENTER_LEAD_S = 0.5


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
    recentered: bool = False


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
        self.cues: list[TactileTimelineCue] = []

    def load_block(
        self,
        *,
        part_number: Any = "",
        phase_label: Any = "",
        block_index: Any = "",
        block_label: Any = "",
        duration_s: Any = 0.0,
        tactile_events: list[dict[str, Any]] | None = None,
    ) -> None:
        self.part_number = str(part_number or "").strip()
        self.phase_label = str(phase_label or "").strip()
        self.block_index = str(block_index or "").strip()
        self.block_label = str(block_label or "").strip()
        self.duration_s = max(0.0, _float(duration_s, default=0.0))
        self.elapsed_s = 0.0
        self.active = True
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
                )
            )
        self.cues = sorted(cues, key=lambda cue: (cue.time_s, cue.trial_number, cue.cue_id))
        for index, cue in enumerate(self.cues, start=1):
            cue.cue_id = index

    def clear(self) -> None:
        self.part_number = ""
        self.phase_label = ""
        self.block_index = ""
        self.block_label = ""
        self.duration_s = 0.0
        self.elapsed_s = 0.0
        self.active = False
        self.cues = []

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
