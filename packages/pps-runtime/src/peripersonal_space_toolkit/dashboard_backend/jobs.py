"""Bounded lifecycle management for local Designer background work."""

from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

from .contracts import application_error_from_exception


TERMINAL_STATES = frozenset({"succeeded", "failed", "cancelled"})


@dataclass
class DashboardJob:
    job_id: str
    kind: str
    status: str = "queued"
    message: str = ""
    result: dict[str, Any] | None = None
    resource_estimate: dict[str, Any] | None = None
    error: str = ""
    error_code: str = ""
    retryable: bool = False
    cancel_requested: bool = False
    commit_started: bool = False
    progress_current: int = 0
    progress_total: int = 0
    progress_percent: float = 0.0
    progress_label: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class JobCancelled(RuntimeError):
    pass


class JobSourceChanged(RuntimeError):
    code = "job_source_changed"
    retryable = True


class JobProgress:
    """Cooperative checkpoints and one uncancellable output publication."""

    def __init__(self, manager: JobManager, job_id: str, cancel: threading.Event) -> None:
        self.manager, self.job_id, self.cancel = manager, job_id, cancel

    def __call__(self, current: int, total: int, label: str = "") -> None:
        if self.cancel.is_set():
            raise JobCancelled("Background job cancelled.")
        total = max(0, int(total or 0))
        current = max(0, min(int(current or 0), total if total else int(current or 0)))
        self.manager._update(self.job_id, progress_current=current, progress_total=total,
            progress_percent=round(current / total * 100, 1) if total else 0.0,
            progress_label=label, message=label or "Background job running")

    @contextmanager
    def commit(self):
        # Cancellation and publication admission share the existing job lock.
        # The actual publication does not hold it, so status remains responsive.
        with self.manager._lock:
            if self.cancel.is_set() or self.manager._closing:
                raise JobCancelled("Background job cancelled before publication.")
            job = self.manager._jobs[self.job_id]
            job.commit_started = True
            job.message = "Publishing verified outputs"
            job.updated_at = time.time()
        yield


class JobManager:
    """Runs bounded daemon jobs and exposes copy-only snapshots to callers."""

    def __init__(
        self,
        *,
        max_concurrent: int = 2,
        max_pending_jobs: int = 64,
        max_terminal_jobs: int = 100,
        result_normalizer: Callable[[Any], Any] | None = None,
    ) -> None:
        self._jobs: dict[str, DashboardJob] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._max_terminal_jobs = max(1, int(max_terminal_jobs))
        self._normalize = result_normalizer or _json_ready
        self._closing = False
        self._worker_count = max(1, int(max_concurrent))
        self._queue: queue.Queue[Callable[[], None]] = queue.Queue(maxsize=max(1, int(max_pending_jobs)))
        self._workers: list[threading.Thread] = []

    def start(
        self, kind: str, func: Callable[..., dict[str, Any]], *, progress: bool = False,
        resource_estimate: dict[str, Any] | None = None,
    ) -> DashboardJob:
        job = DashboardJob(job_id=uuid.uuid4().hex[:12], kind=str(kind or "job"),
                           resource_estimate=deepcopy(resource_estimate))
        cancel_event = threading.Event()

        _progress = JobProgress(self, job.job_id, cancel_event)

        def _run() -> None:
            try:
                if cancel_event.is_set():
                    self._update_cancelled(job.job_id)
                    return
                self._update(job.job_id, status="running", message=f"{job.kind} started")
                try:
                    result = func(_progress) if progress else func()
                    if cancel_event.is_set():
                        raise JobCancelled("Background job cancelled.")
                except JobCancelled:
                    self._update_cancelled(job.job_id)
                except Exception as exc:
                    logging.getLogger(__name__).exception("Designer background job %s failed", job.kind)
                    error = application_error_from_exception(
                        exc,
                        code="job_failed",
                        fallback_message="Background job failed. Review the local log for details.",
                    )
                    self._update(
                        job.job_id,
                        status="failed",
                        error=error.message,
                        error_code=error.code,
                        retryable=error.retryable,
                        message=f"{job.kind} failed",
                    )
                else:
                    snapshot = self.get(job.job_id)
                    total_value = int(snapshot.progress_total or 0) if snapshot is not None else 0
                    if total_value:
                        self._update(
                            job.job_id,
                            progress_current=total_value,
                            progress_percent=100.0,
                            progress_label=f"{job.kind} complete",
                        )
                    self._update(
                        job.job_id,
                        status="succeeded",
                        result=self._normalize(result),
                        message=f"{job.kind} complete",
                    )
            finally:
                with self._lock:
                    self._trim_terminal_locked()

        with self._lock:
            if self._closing:
                raise RuntimeError("The Designer background-job service is shutting down.")
            self._ensure_workers_locked()
            self._jobs[job.job_id] = job
            self._cancel_events[job.job_id] = cancel_event
            try:
                self._queue.put_nowait(_run)
            except queue.Full as exc:
                self._jobs.pop(job.job_id, None)
                self._cancel_events.pop(job.job_id, None)
                raise RuntimeError("The Designer background-job queue is full. Try again after a job finishes.") from exc
        return _job_snapshot(job)

    def _ensure_workers_locked(self) -> None:
        if self._workers:
            return
        self._workers = [
            threading.Thread(target=self._worker, name=f"pps-job-worker-{index + 1}", daemon=True)
            for index in range(self._worker_count)
        ]
        for worker in self._workers:
            worker.start()

    def _worker(self) -> None:
        while True:
            try:
                task = self._queue.get(timeout=0.1)
            except queue.Empty:
                with self._lock:
                    if self._closing:
                        return
                continue
            try:
                task()
            finally:
                self._queue.task_done()

    def get(self, job_id: str) -> DashboardJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return _job_snapshot(job) if job is not None else None

    def recent(self, limit: int = 12) -> list[DashboardJob]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)[: max(0, int(limit))]
            return [_job_snapshot(job) for job in jobs]

    def cancel(self, job_id: str) -> DashboardJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.status in TERMINAL_STATES or job.commit_started:
                return _job_snapshot(job)
            event = self._cancel_events[job_id]
            event.set()
            job.cancel_requested = True
            job.message = f"{job.kind} cancellation requested"
            job.updated_at = time.time()
            return _job_snapshot(job)

    def shutdown(self, *, timeout: float = 5.0) -> None:
        with self._lock:
            self._closing = True
            events = [event for job_id, event in self._cancel_events.items() if not self._jobs[job_id].commit_started]
            workers = list(self._workers)
        for event in events:
            event.set()
        deadline = time.monotonic() + max(0.0, float(timeout))
        for thread in workers:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            thread.join(remaining)

    def _update_cancelled(self, job_id: str) -> None:
        self._update(
            job_id,
            status="cancelled",
            error="Background job cancelled.",
            error_code="job_cancelled",
            retryable=True,
            cancel_requested=True,
            message="Background job cancelled",
        )

    def _update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in changes.items():
                setattr(job, key, value)
            job.updated_at = time.time()
            if job.status in TERMINAL_STATES:
                self._trim_terminal_locked()

    def _trim_terminal_locked(self) -> None:
        terminal = sorted(
            (job for job in self._jobs.values() if job.status in TERMINAL_STATES),
            key=lambda item: item.updated_at,
            reverse=True,
        )
        for job in terminal[self._max_terminal_jobs :]:
            self._jobs.pop(job.job_id, None)
            self._cancel_events.pop(job.job_id, None)


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _job_snapshot(job: DashboardJob) -> DashboardJob:
    return replace(job, result=deepcopy(job.result), resource_estimate=deepcopy(job.resource_estimate))
