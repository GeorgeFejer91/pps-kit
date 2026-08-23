"""Runner-owned LabRecorder capture helpers."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import ctypes
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from typing import Any, TextIO

from .output_layout import _filesystem_path
from .runtime_paths import writable_root
from .timing_events import (
    LSL_NUMERIC_SOURCE_ID_PREFIX,
    LSL_NUMERIC_STREAM_NAME,
    LSL_SOURCE_ID_PREFIX,
    LSL_STREAM_NAME,
)


class LabRecorderCaptureError(RuntimeError):
    """Raised when runner-owned LabRecorder capture cannot be started."""


def _mkdir(path: Path | str) -> None:
    os.makedirs(_filesystem_path(Path(path)), exist_ok=True)


def _path_is_file(path: Path | str) -> bool:
    return os.path.isfile(_filesystem_path(Path(path)))


def _path_size(path: Path | str) -> int:
    try:
        return os.path.getsize(_filesystem_path(Path(path)))
    except OSError:
        return 0


def find_labrecorder_cli(explicit: str | Path | None = None) -> Path:
    """Return a LabRecorderCLI executable from an explicit path, PATH, or local tools."""

    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    for command in ("LabRecorderCLI", "LabRecorderCLI.exe"):
        found = shutil.which(command)
        if found:
            candidates.append(Path(found))

    root = writable_root()
    candidates.extend(sorted((root / "local_data" / "software_tools" / "labrecorder").glob("**/LabRecorderCLI.exe")))
    candidates.extend(sorted(Path("local_data/software_tools/labrecorder").glob("**/LabRecorderCLI.exe")))

    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        if _path_is_file(resolved):
            return resolved
    raise FileNotFoundError(
        "LabRecorderCLI.exe was not found. Install/extract LabRecorder under "
        "local_data/software_tools/labrecorder, put it on PATH, or pass --labrecorder-cli."
    )


def labrecorder_gui_from_cli(cli_path: Path) -> Path:
    gui = Path(cli_path).with_name("LabRecorder.exe")
    if _path_is_file(gui):
        return gui.resolve()
    raise FileNotFoundError(f"LabRecorder.exe was not found beside LabRecorderCLI.exe: {gui}")


def labrecorder_source_ids(session_id: str) -> tuple[str, str]:
    session = str(session_id)
    return f"{LSL_SOURCE_ID_PREFIX}-{session}", f"{LSL_NUMERIC_SOURCE_ID_PREFIX}-{session}"


def labrecorder_predicates(session_id: str) -> list[str]:
    rich_source_id, numeric_source_id = labrecorder_source_ids(session_id)
    return [f"source_id='{rich_source_id}'", f"source_id='{numeric_source_id}'"]


def wait_for_runner_lsl_streams(session_id: str, *, timeout_s: float = 10.0) -> dict[str, Any]:
    """Wait until the runner's rich and numeric LSL streams are discoverable."""

    rich_source_id, numeric_source_id = labrecorder_source_ids(session_id)
    expected = {
        rich_source_id: LSL_STREAM_NAME,
        numeric_source_id: LSL_NUMERIC_STREAM_NAME,
    }
    try:
        from pylsl import resolve_byprop  # type: ignore
    except Exception as exc:
        return {
            "ready": False,
            "error": f"pylsl unavailable: {exc}",
            "expected_source_ids": list(expected),
            "found_source_ids": [],
        }

    deadline = time.perf_counter() + max(0.0, float(timeout_s))
    found: dict[str, list[str]] = {source_id: [] for source_id in expected}
    while time.perf_counter() <= deadline:
        all_ready = True
        for source_id, stream_name in expected.items():
            if found[source_id]:
                continue
            remaining = max(0.01, min(0.25, deadline - time.perf_counter()))
            try:
                matches = resolve_byprop("source_id", source_id, minimum=1, timeout=remaining)
            except TypeError:
                matches = resolve_byprop("source_id", source_id, 1, remaining)
            except Exception:
                matches = []
            names = [str(getattr(match, "name", lambda: "")() if callable(getattr(match, "name", None)) else "") for match in matches]
            names = [name for name in names if name]
            if stream_name in names or names:
                found[source_id] = names or [stream_name]
            else:
                all_ready = False
        if all_ready:
            return {
                "ready": True,
                "error": "",
                "expected_source_ids": list(expected),
                "found_source_ids": sorted(source_id for source_id, names in found.items() if names),
                "found_streams": found,
                "wait_s": max(0.0, timeout_s - max(0.0, deadline - time.perf_counter())),
            }
        time.sleep(0.05)

    return {
        "ready": False,
        "error": "Timed out waiting for runner LSL streams.",
        "expected_source_ids": list(expected),
        "found_source_ids": sorted(source_id for source_id, names in found.items() if names),
        "found_streams": found,
        "wait_s": max(0.0, timeout_s),
    }


@dataclass
class LabRecorderCapture:
    """A small process owner for one LabRecorder RCS XDF capture."""

    labrecorder_cli: Path
    xdf_path: Path
    session_id: str
    stdout_path: Path
    stderr_path: Path
    process: subprocess.Popen[str] | None = field(default=None, init=False, repr=False)
    command: list[str] = field(default_factory=list, init=False)
    started_at_unix: float = 0.0
    labrecorder_exe: Path = field(default=Path(), init=False)
    rcs_port: int = 22345
    started_stream_count: int = 0
    stream_selection_refreshes: int = 0
    _stdout_handle: TextIO | None = field(default=None, init=False, repr=False)
    _stderr_handle: TextIO | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.labrecorder_cli = Path(self.labrecorder_cli).expanduser().resolve()
        self.labrecorder_exe = labrecorder_gui_from_cli(self.labrecorder_cli)
        self.xdf_path = Path(self.xdf_path).expanduser().resolve()
        self.stdout_path = Path(self.stdout_path).expanduser().resolve()
        self.stderr_path = Path(self.stderr_path).expanduser().resolve()

    def start(self, *, stream_timeout_s: float = 10.0, startup_s: float = 1.0) -> dict[str, Any]:
        lsl = wait_for_runner_lsl_streams(self.session_id, timeout_s=stream_timeout_s)
        if not bool(lsl.get("ready")):
            raise LabRecorderCaptureError(str(lsl.get("error") or "Runner LSL streams were not discoverable."))

        _mkdir(self.xdf_path.parent)
        _mkdir(self.stdout_path.parent)
        _mkdir(self.stderr_path.parent)
        self.command = [str(self.labrecorder_exe), "-c", str(self.labrecorder_exe.with_name("LabRecorder.cfg"))]
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        startupinfo = None
        if hasattr(subprocess, "STARTUPINFO") and hasattr(subprocess, "STARTF_USESHOWWINDOW"):
            startupinfo = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
            startupinfo.wShowWindow = 7  # SW_SHOWMINNOACTIVE: keep LabRecorder off the runner focus path.
        self._stdout_handle = open(_filesystem_path(self.stdout_path), "w", encoding="utf-8", errors="replace")
        self._stderr_handle = open(_filesystem_path(self.stderr_path), "w", encoding="utf-8", errors="replace")
        with _external_subprocess_dll_search_context():
            self.process = subprocess.Popen(
                self.command,
                cwd=str(self.labrecorder_exe.parent),
                stdin=subprocess.DEVNULL,
                stdout=self._stdout_handle,
                stderr=self._stderr_handle,
                text=True,
                creationflags=creationflags,
                startupinfo=startupinfo,
                env=_labrecorder_subprocess_env(self.labrecorder_exe.parent),
            )
        self.started_at_unix = time.time()
        rcs = self._wait_for_rcs(timeout_s=max(3.0, float(stream_timeout_s)))
        if self.process.poll() is not None:
            self.process.wait(timeout=2.0)
            self._close_output_handles()
            stdout_text = _read_text(self.stdout_path)
            stderr_text = _read_text(self.stderr_path)
            raise LabRecorderCaptureError(
                "LabRecorder exited before playback could start. "
                f"returncode={self.process.returncode} stdout={stdout_text!r} stderr={stderr_text!r}"
            )
        self.started_stream_count = 0
        self.stream_selection_refreshes = self._select_all_visible_network_streams(refresh_s=max(0.0, float(startup_s)))
        self._send_rcs_commands(
            [
                f"filename {{root:{_rcs_path(self.xdf_path.parent)}}} {{template:{self.xdf_path.name}}}",
                "start",
            ]
        )
        collection_started = _wait_for_labrecorder_collection_started(
            self.stdout_path,
            timeout_s=max(1.0, float(startup_s), 8.0),
        )
        if not collection_started:
            time.sleep(max(0.0, float(startup_s)))
        self.started_stream_count = _labrecorder_started_stream_count(self.stdout_path)
        if collection_started:
            self.started_stream_count = max(2, self.started_stream_count)
        if self.process.poll() is not None:
            self.process.wait(timeout=2.0)
            self._close_output_handles()
            stdout_text = _read_text(self.stdout_path)
            stderr_text = _read_text(self.stderr_path)
            raise LabRecorderCaptureError(
                "LabRecorder exited immediately after the remote start command. "
                f"returncode={self.process.returncode} stdout={stdout_text!r} stderr={stderr_text!r}"
            )
        return {
            "enabled": True,
            "started": True,
            "mode": "rcs",
            "pid": self.process.pid,
            "xdf_path": str(self.xdf_path),
            "labrecorder_cli": str(self.labrecorder_cli),
            "labrecorder_exe": str(self.labrecorder_exe),
            "command": list(self.command),
            "lsl": lsl,
            "rcs": rcs,
            "collection_started": bool(collection_started),
            "stream_selection": "select_all_visible_network_streams",
            "stream_selection_refreshes": int(self.stream_selection_refreshes),
            "minimum_required_stream_count": 2,
            "started_stream_count": int(self.started_stream_count),
            "window_show_state": "show_min_no_activate",
            "started_at_unix": self.started_at_unix,
        }

    def stop(self, *, timeout_s: float = 8.0) -> dict[str, Any]:
        process = self.process
        if process is None:
            return {"enabled": True, "stopped": False, "returncode": None, "stdout": "", "stderr": ""}
        stop_error = ""
        recording_stopped = False
        footer_observed = False
        graceful_close_sent = False
        expected_streams = max(2, int(self.started_stream_count or 0))
        try:
            if process.poll() is None:
                self._send_rcs_commands(["stop"])
                footer_observed = _wait_for_labrecorder_footer(
                    self.stdout_path,
                    timeout_s=max(0.5, float(timeout_s)),
                    expected_streams=expected_streams,
                )
                recording_stopped = _wait_for_file_quiet(self.xdf_path, timeout_s=max(0.5, float(timeout_s)))
                graceful_close_sent = _close_labrecorder_windows(process.pid)
                try:
                    process.wait(timeout=max(2.0, min(10.0, float(timeout_s))))
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=2.0)
            else:
                recording_stopped = _path_is_file(self.xdf_path) and _path_size(self.xdf_path) > 0
                process.wait(timeout=0.1)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2.0)
        except Exception as exc:
            stop_error = str(exc)
            process.terminate()
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2.0)
        self._close_output_handles()
        stdout_text = _read_text(self.stdout_path)
        stderr_text = _read_text(self.stderr_path)
        return {
            "enabled": True,
            "stopped": True,
            "mode": "rcs",
            "recording_stopped": bool(recording_stopped),
            "footer_observed": bool(footer_observed),
            "expected_footer_stream_count": expected_streams,
            "graceful_close_sent": bool(graceful_close_sent),
            "returncode": process.returncode,
            "stdout_path": str(self.stdout_path),
            "stderr_path": str(self.stderr_path),
            "xdf_path": str(self.xdf_path),
            "error": stop_error,
            "duration_s": max(0.0, time.time() - self.started_at_unix) if self.started_at_unix else 0.0,
            "command": list(self.command),
            "stdout_tail": stdout_text[-2000:],
            "stderr_tail": stderr_text[-2000:],
        }

    def close_for_runner_exit(self, *, timeout_s: float = 2.0) -> dict[str, Any]:
        return self.stop(timeout_s=max(0.25, float(timeout_s)))

    def _wait_for_rcs(self, *, timeout_s: float) -> dict[str, Any]:
        deadline = time.perf_counter() + max(0.1, float(timeout_s))
        last_error = ""
        while time.perf_counter() <= deadline:
            if self.process is not None and self.process.poll() is not None:
                break
            try:
                with socket.create_connection(("127.0.0.1", int(self.rcs_port)), timeout=0.5):
                    return {"ready": True, "port": int(self.rcs_port), "error": ""}
            except OSError as exc:
                last_error = str(exc)
                time.sleep(0.1)
        raise LabRecorderCaptureError(f"Timed out waiting for LabRecorder RCS port {self.rcs_port}: {last_error}")

    def _send_rcs_commands(self, commands: list[str]) -> None:
        with socket.create_connection(("127.0.0.1", int(self.rcs_port)), timeout=2.0) as sock:
            for command in commands:
                sock.sendall((command.rstrip() + "\n").encode("utf-8"))
                time.sleep(0.15)

    def _select_all_visible_network_streams(self, *, refresh_s: float) -> int:
        deadline = time.perf_counter() + max(0.0, float(refresh_s))
        refreshes = 0
        while True:
            self._send_rcs_commands(["update"])
            refreshes += 1
            time.sleep(min(0.35, max(0.0, deadline - time.perf_counter())))
            self._send_rcs_commands(["select all"])
            if time.perf_counter() >= deadline:
                return refreshes
            time.sleep(min(0.15, max(0.0, deadline - time.perf_counter())))

    def _close_output_handles(self) -> None:
        for handle in (self._stdout_handle, self._stderr_handle):
            if handle is None:
                continue
            try:
                handle.flush()
            except Exception:
                pass
            try:
                handle.close()
            except Exception:
                pass
        self._stdout_handle = None
        self._stderr_handle = None


def _decode_pipe(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.decode("utf-8", errors="replace")


def _read_text(path: Path) -> str:
    try:
        with open(_filesystem_path(path), "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except Exception:
        return ""


def _labrecorder_subprocess_env(labrecorder_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    for key in ("PYTHONHOME", "PYTHONPATH", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "PYSIDE_DESIGNER_PLUGINS"):
        env.pop(key, None)

    lab_dir = str(Path(labrecorder_dir).resolve())
    blocked = _packaged_runtime_paths()
    path_entries = [lab_dir]
    for entry in str(env.get("PATH") or "").split(os.pathsep):
        if not entry:
            continue
        try:
            resolved = str(Path(entry).resolve()).lower()
        except OSError:
            resolved = entry.lower()
        if resolved in blocked:
            continue
        if resolved == lab_dir.lower():
            continue
        path_entries.append(entry)
    env["PATH"] = os.pathsep.join(path_entries)
    return env


def _packaged_runtime_paths() -> set[str]:
    paths: set[str] = set()
    for value in (getattr(sys, "_MEIPASS", None), Path(sys.executable).parent if getattr(sys, "frozen", False) else None):
        if not value:
            continue
        try:
            paths.add(str(Path(value).resolve()).lower())
        except OSError:
            paths.add(str(value).lower())
    return paths


@contextmanager
def _external_subprocess_dll_search_context():
    if os.name != "nt" or not getattr(sys, "frozen", False):
        yield
        return
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
        kernel32.SetDllDirectoryW.restype = ctypes.c_bool
        kernel32.SetDllDirectoryW(None)
    except Exception:
        kernel32 = None
    try:
        yield
    finally:
        runtime_dir = getattr(sys, "_MEIPASS", None)
        if kernel32 is not None and runtime_dir:
            try:
                kernel32.SetDllDirectoryW(str(runtime_dir))
            except Exception:
                pass


def _rcs_path(path: Path) -> str:
    return str(Path(path).resolve()).replace("\\", "/") + "/"


def _wait_for_file_quiet(path: Path, *, timeout_s: float) -> bool:
    deadline = time.perf_counter() + max(0.1, float(timeout_s))
    previous_size = -1
    stable_count = 0
    while time.perf_counter() <= deadline:
        if _path_is_file(path):
            size = _path_size(path)
            if size > 0 and size == previous_size:
                stable_count += 1
                if stable_count >= 2:
                    return True
            else:
                stable_count = 0
            previous_size = size
        time.sleep(0.25)
    return _path_is_file(path) and _path_size(path) > 0


def _wait_for_labrecorder_footer(stdout_path: Path, *, timeout_s: float, expected_streams: int = 2) -> bool:
    deadline = time.perf_counter() + max(0.1, float(timeout_s))
    expected = max(1, int(expected_streams))
    while time.perf_counter() <= deadline:
        text = _read_text(stdout_path)
        if text.count("Wrote footer for stream") >= expected:
            return True
        time.sleep(0.25)
    return _read_text(stdout_path).count("Wrote footer for stream") >= expected


def _wait_for_labrecorder_collection_started(stdout_path: Path, *, timeout_s: float, expected_streams: int = 2) -> bool:
    deadline = time.perf_counter() + max(0.1, float(timeout_s))
    expected = max(1, int(expected_streams))
    last_count = -1
    last_change = time.perf_counter()
    while time.perf_counter() <= deadline:
        count = _labrecorder_started_stream_count(stdout_path)
        now = time.perf_counter()
        if count != last_count:
            last_count = count
            last_change = now
        if count >= expected and (now - last_change) >= 0.5:
            return True
        time.sleep(0.25)
    return _labrecorder_started_stream_count(stdout_path) >= expected


def _labrecorder_started_stream_count(stdout_path: Path) -> int:
    return _read_text(stdout_path).count("Started data collection for stream")


def _close_labrecorder_windows(pid: int | None) -> bool:
    if sys.platform != "win32" or not pid:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        WM_CLOSE = 0x0010
        handles: list[int] = []

        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def _callback(hwnd: int, _lparam: int) -> bool:
            process_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
            if int(process_id.value) == int(pid):
                handles.append(int(hwnd))
            return True

        user32.EnumWindows(EnumWindowsProc(_callback), 0)
        sent = False
        for hwnd in handles:
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            sent = True
        return sent
    except Exception:
        return False
