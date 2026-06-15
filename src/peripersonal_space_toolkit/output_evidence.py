"""Digital output evidence recording for runner playback.

The recorder stores the exact multichannel buffers handed to the audio output
callback. It is a local data-safety artifact, not a physical loopback
measurement.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf


class OutputEvidenceRecorder:
    """Nonblocking recorder for already-mixed audio output buffers."""

    def __init__(self, *, queue_size: int = 4096) -> None:
        self.queue_size = int(queue_size)
        self._queue: queue.Queue[np.ndarray | None] | None = None
        self._worker: threading.Thread | None = None
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._active = False
        self._path: Path | None = None
        self._metadata: dict[str, Any] = {}
        self._sample_rate = 0
        self._channels = 0
        self._frames_seen = 0
        self._dropped_buffers = 0
        self._started_perf_counter = 0.0

    @property
    def active(self) -> bool:
        with self._lock:
            return bool(self._active)

    @property
    def elapsed_s(self) -> float:
        with self._lock:
            if not self._active or self._started_perf_counter <= 0:
                return 0.0
            return time.perf_counter() - self._started_perf_counter

    def start(self, path: str | Path, *, metadata: dict[str, Any] | None = None) -> bool:
        self.stop(interrupted=True) if self.active else None
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._path = path
            self._metadata = dict(metadata or {})
            self._metadata.setdefault("schema", "pps-digital-output-evidence.v1")
            self._metadata.setdefault("mode", "digital_output_evidence_wav")
            self._chunks = []
            self._sample_rate = 0
            self._channels = 0
            self._frames_seen = 0
            self._dropped_buffers = 0
            self._started_perf_counter = time.perf_counter()
            self._active = True
            self._queue = queue.Queue(maxsize=self.queue_size)
            self._worker = threading.Thread(
                target=self._worker_loop,
                name=f"pps-output-evidence-{path.stem}",
                daemon=True,
            )
            self._worker.start()
        return True

    def write_buffer(self, samples: Any, *, sample_rate: int | float | None = None) -> None:
        with self._lock:
            if not self._active or self._queue is None:
                return
            active_queue = self._queue
        data = np.asarray(samples, dtype=np.float32)
        if data.ndim == 1:
            data = data[:, None]
        data = np.array(data, dtype=np.float32, copy=True, order="C")
        with self._lock:
            if sample_rate and not self._sample_rate:
                self._sample_rate = int(round(float(sample_rate)))
            self._channels = max(self._channels, int(data.shape[1]))
            self._frames_seen += int(data.shape[0])
        try:
            active_queue.put_nowait(data)
        except queue.Full:
            with self._lock:
                self._dropped_buffers += 1

    def stop(self, *, interrupted: bool = False) -> dict[str, Any]:
        with self._lock:
            if not self._active and self._path is None:
                return {"started": False, "mode": "digital_output_evidence_wav"}
            self._active = False
            active_queue = self._queue
            worker = self._worker
            path = self._path
        if active_queue is not None:
            try:
                active_queue.put_nowait(None)
            except queue.Full:
                try:
                    active_queue.get_nowait()
                    active_queue.task_done()
                except Exception:
                    pass
                try:
                    active_queue.put_nowait(None)
                except queue.Full:
                    pass
        if worker is not None:
            worker.join(timeout=5.0)

        with self._lock:
            chunks = list(self._chunks)
            self._chunks = []
            sample_rate = int(self._sample_rate or 0)
            channels = int(self._channels or 0)
            frames_seen = int(self._frames_seen)
            dropped = int(self._dropped_buffers)
            metadata = dict(self._metadata)
            self._queue = None
            self._worker = None
            self._path = None
            self._metadata = {}

        if chunks:
            data = np.concatenate(chunks, axis=0)
        else:
            data = np.zeros((0, max(channels, 1)), dtype=np.float32)
        if not sample_rate:
            sample_rate = int(metadata.get("sample_rate") or metadata.get("sample_rate_hz") or 44100)
        if path is not None:
            sf.write(path, data, sample_rate, subtype="FLOAT")

        peaks = np.max(np.abs(data), axis=0).astype(float).tolist() if data.size else []
        rms = np.sqrt(np.mean(np.square(data.astype(np.float64)), axis=0)).astype(float).tolist() if data.size else []
        summary = {
            **metadata,
            "started": True,
            "path": "" if path is None else str(path),
            "sample_rate": sample_rate,
            "channels": int(data.shape[1]) if data.ndim == 2 else 1,
            "frames": int(data.shape[0]),
            "frames_seen": frames_seen,
            "duration_s": float(data.shape[0] / sample_rate) if sample_rate else 0.0,
            "peak_by_channel": peaks,
            "rms_by_channel": rms,
            "clipped_channels_1based": [index + 1 for index, peak in enumerate(peaks) if peak >= 0.98],
            "dropped_buffer_count": dropped,
            "interrupted": bool(interrupted),
        }
        if path is not None:
            metadata_path = path.with_name(path.stem + ".output_evidence.json")
            metadata_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            summary["metadata_path"] = str(metadata_path)
        return summary

    def _worker_loop(self) -> None:
        while True:
            with self._lock:
                active_queue = self._queue
            if active_queue is None:
                return
            item = active_queue.get()
            try:
                if item is None:
                    return
                with self._lock:
                    self._chunks.append(item)
            finally:
                active_queue.task_done()
