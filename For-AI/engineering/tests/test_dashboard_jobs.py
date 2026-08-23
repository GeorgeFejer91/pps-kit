from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from peripersonal_space_toolkit.dashboard_backend.jobs import JobManager


def _wait_for_terminal(manager: JobManager, job_id: str, timeout: float = 3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = manager.get(job_id)
        if job is not None and job.status in {"succeeded", "failed", "cancelled"}:
            return job
        time.sleep(0.01)
    raise AssertionError(f"Job did not finish: {job_id}")


def test_job_manager_returns_snapshots_and_normalizes_results() -> None:
    manager = JobManager(max_concurrent=1)
    try:
        assert manager._workers == []
        started = manager.start("prepare", lambda: {"path": Path(__file__)})
        assert len(manager._workers) == 1
        finished = _wait_for_terminal(manager, started.job_id)
        finished.message = "caller mutation"

        assert finished.status == "succeeded"
        assert finished.result == {"path": str(Path(__file__))}
        assert manager.get(started.job_id).message == "prepare complete"
    finally:
        manager.shutdown(timeout=1.0)


def test_job_manager_cooperatively_cancels_running_work() -> None:
    manager = JobManager(max_concurrent=1)
    entered = threading.Event()

    def long_job(progress):
        entered.set()
        for current in range(100):
            progress(current, 100, "working")
            time.sleep(0.01)
        return {"status": "unexpected"}

    try:
        job = manager.start("segment_build", long_job, progress=True)
        assert entered.wait(1.0)
        cancelled = manager.cancel(job.job_id)
        assert cancelled is not None and cancelled.cancel_requested is True
        finished = _wait_for_terminal(manager, job.job_id)

        assert finished.status == "cancelled"
        assert finished.error_code == "job_cancelled"
        assert finished.retryable is True
    finally:
        manager.shutdown(timeout=1.0)


def test_job_manager_bounds_pending_work() -> None:
    manager = JobManager(max_concurrent=1, max_pending_jobs=1)
    entered = threading.Event()
    release = threading.Event()

    def blocking_job():
        entered.set()
        release.wait(2.0)
        return {"status": "done"}

    try:
        first = manager.start("first", blocking_job)
        assert entered.wait(1.0)
        second = manager.start("second", lambda: {"status": "done"})
        with pytest.raises(RuntimeError, match="queue is full"):
            manager.start("third", lambda: {"status": "done"})
        release.set()
        assert _wait_for_terminal(manager, first.job_id).status == "succeeded"
        assert _wait_for_terminal(manager, second.job_id).status == "succeeded"
    finally:
        release.set()
        manager.shutdown(timeout=1.0)
