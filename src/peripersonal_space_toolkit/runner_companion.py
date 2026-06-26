"""LAN companion service for the native Focus Mode runner."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from io import BytesIO
import secrets
import socket
import threading
import time
from typing import Any, Protocol
from urllib.parse import urlencode

from .dashboard_backend.security import TOKEN_HEADER


DEFAULT_COMPANION_HOST = "0.0.0.0"
DEFAULT_COMPANION_PORT = 8767
PAIRING_SCHEME = "pps-companion"
SNAPSHOT_SCHEMA = "pps-runner-companion-snapshot.v1"
HEALTH_SCHEMA = "pps-runner-companion-health.v1"
PAIRING_SCHEMA_VERSION = "1"


class CompanionCommandError(RuntimeError):
    """HTTP-safe command failure raised by the runner bridge."""

    def __init__(self, message: str = "", *, status_code: int = 409, reason: str = "command_not_allowed") -> None:
        super().__init__(message or reason)
        self.status_code = int(status_code)
        self.reason = reason


class RunnerCompanionBridge(Protocol):
    """Small interface implemented by Focus Mode on the Qt UI thread."""

    def health(self) -> dict[str, Any]:
        ...

    def snapshot(self) -> dict[str, Any]:
        ...

    def submit_setup(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    def continue_instruction(self) -> dict[str, Any]:
        ...

    def start_part(self, part_number: int) -> dict[str, Any]:
        ...

    def pause(self) -> dict[str, Any]:
        ...

    def resume(self) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class RunnerCompanionConfig:
    host: str = DEFAULT_COMPANION_HOST
    port: int = DEFAULT_COMPANION_PORT
    advertise_ip: str = ""

    @property
    def advertised_host(self) -> str:
        return self.advertise_ip or choose_lan_ipv4() or "127.0.0.1"


def generate_companion_token() -> str:
    return secrets.token_urlsafe(32)


def choose_lan_ipv4() -> str:
    """Best-effort non-loopback IPv4 address for QR pairing."""

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            candidate = str(probe.getsockname()[0])
            if candidate and not candidate.startswith("127."):
                return candidate
    except Exception:
        pass
    try:
        hostname = socket.gethostname()
        for _, _, _, _, sockaddr in socket.getaddrinfo(hostname, None, socket.AF_INET):
            candidate = str(sockaddr[0])
            if candidate and not candidate.startswith("127.") and not candidate.startswith("169.254."):
                return candidate
    except Exception:
        pass
    return ""


def build_pairing_uri(
    *,
    host: str,
    port: int,
    session_id: str,
    token: str,
) -> str:
    query = urlencode(
        {
            "v": PAIRING_SCHEMA_VERSION,
            "host": str(host),
            "port": str(int(port)),
            "session_id": str(session_id),
            "token": str(token),
        }
    )
    return f"{PAIRING_SCHEME}://pair?{query}"


def pairing_qr_png_bytes(uri: str) -> bytes:
    try:
        import qrcode
    except ImportError as exc:  # pragma: no cover - dependency checked by packaging tests
        raise RuntimeError("Install qrcode[pil] to render the runner companion pairing QR code.") from exc
    image = qrcode.make(str(uri))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _token_matches(expected: str, supplied: str) -> bool:
    return bool(supplied) and secrets.compare_digest(str(expected), str(supplied))


def create_runner_companion_app(
    bridge: RunnerCompanionBridge,
    *,
    token: str,
) -> Any:
    try:
        from fastapi import Body, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
    except ImportError as exc:
        raise RuntimeError("Install the web extra to run the runner companion service.") from exc
    globals()["WebSocket"] = WebSocket

    app = FastAPI(title="PPS Runner Companion", docs_url=None, redoc_url=None)

    def _authorize_token(supplied_token: str) -> None:
        if not _token_matches(token, supplied_token):
            raise HTTPException(
                status_code=403,
                detail={
                    "reason": "missing_token" if not supplied_token else "stale_or_invalid_token",
                    "token_header": TOKEN_HEADER,
                },
            )

    def _handle_command_error(exc: CompanionCommandError) -> None:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"reason": exc.reason, "message": str(exc), "token_header": TOKEN_HEADER},
        ) from exc

    @app.get("/api/runner/health")
    def health() -> dict[str, Any]:
        try:
            payload = dict(bridge.health())
        except CompanionCommandError as exc:
            _handle_command_error(exc)
        payload.setdefault("schema", HEALTH_SCHEMA)
        payload.setdefault("service", "pps-runner-companion")
        payload.setdefault("status", "ok")
        payload["security"] = {"token_required": True, "token_header": TOKEN_HEADER}
        return payload

    @app.get("/api/runner/snapshot")
    def snapshot(companion_token: str = Header(default="", alias=TOKEN_HEADER)) -> dict[str, Any]:
        _authorize_token(companion_token)
        try:
            return bridge.snapshot()
        except CompanionCommandError as exc:
            _handle_command_error(exc)

    @app.post("/api/runner/setup")
    def setup(
        payload: dict[str, Any] | None = Body(default=None),
        companion_token: str = Header(default="", alias=TOKEN_HEADER),
    ) -> dict[str, Any]:
        _authorize_token(companion_token)
        try:
            return bridge.submit_setup(dict(payload or {}))
        except CompanionCommandError as exc:
            _handle_command_error(exc)

    @app.post("/api/runner/commands/continue-instruction")
    def continue_instruction(companion_token: str = Header(default="", alias=TOKEN_HEADER)) -> dict[str, Any]:
        _authorize_token(companion_token)
        try:
            return bridge.continue_instruction()
        except CompanionCommandError as exc:
            _handle_command_error(exc)

    @app.post("/api/runner/commands/start-part")
    def start_part(
        payload: dict[str, Any] | None = Body(default=None),
        companion_token: str = Header(default="", alias=TOKEN_HEADER),
    ) -> dict[str, Any]:
        _authorize_token(companion_token)
        payload = dict(payload or {})
        try:
            part_number = int(payload.get("part_number"))
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail={"reason": "invalid_part_number", "message": "part_number must be 1 or 2."},
            ) from exc
        if part_number not in {1, 2}:
            raise HTTPException(
                status_code=400,
                detail={"reason": "invalid_part_number", "message": "part_number must be 1 or 2."},
            )
        try:
            return bridge.start_part(part_number)
        except CompanionCommandError as exc:
            _handle_command_error(exc)

    @app.post("/api/runner/commands/pause")
    def pause(companion_token: str = Header(default="", alias=TOKEN_HEADER)) -> dict[str, Any]:
        _authorize_token(companion_token)
        try:
            return bridge.pause()
        except CompanionCommandError as exc:
            _handle_command_error(exc)

    @app.post("/api/runner/commands/resume")
    def resume(companion_token: str = Header(default="", alias=TOKEN_HEADER)) -> dict[str, Any]:
        _authorize_token(companion_token)
        try:
            return bridge.resume()
        except CompanionCommandError as exc:
            _handle_command_error(exc)

    @app.websocket("/api/runner/ws")
    async def websocket(websocket: WebSocket) -> None:
        if not _token_matches(token, websocket.headers.get(TOKEN_HEADER, "")):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        last_sequence: int | None = None
        try:
            while True:
                try:
                    snapshot_payload = bridge.snapshot()
                except CompanionCommandError as exc:
                    await websocket.close(code=1011, reason=exc.reason[:120])
                    return
                sequence = int(snapshot_payload.get("sequence") or 0)
                snapshot_payload["message_type"] = "snapshot" if last_sequence != sequence else "heartbeat"
                await websocket.send_json(snapshot_payload)
                last_sequence = sequence
                await asyncio.sleep(1.0)
        except WebSocketDisconnect:
            return

    return app


class RunnerCompanionService:
    """Background uvicorn server owned by one Focus Mode window."""

    def __init__(
        self,
        bridge: RunnerCompanionBridge,
        *,
        config: RunnerCompanionConfig | None = None,
        token: str | None = None,
    ) -> None:
        self.bridge = bridge
        self.config = config or RunnerCompanionConfig()
        self.token = token or generate_companion_token()
        self.app = create_runner_companion_app(bridge, token=self.token)
        self._server: Any | None = None
        self._thread: threading.Thread | None = None
        self.error_message = ""

    @property
    def pairing_uri(self) -> str:
        session_id = str(self.bridge.health().get("session_id") or "")
        return build_pairing_uri(
            host=self.config.advertised_host,
            port=self.config.port,
            session_id=session_id,
            token=self.token,
        )

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        def _run() -> None:
            try:
                import uvicorn

                server_config = uvicorn.Config(
                    self.app,
                    host=self.config.host,
                    port=int(self.config.port),
                    loop="asyncio",
                    http="h11",
                    ws="websockets",
                    log_level="warning",
                    log_config=None,
                    access_log=False,
                )
                self._server = uvicorn.Server(server_config)
                self._server.run()
            except Exception as exc:  # noqa: BLE001 - surfaced in Focus Mode status text.
                self.error_message = str(exc)

        self._thread = threading.Thread(target=_run, name="pps-runner-companion", daemon=True)
        self._thread.start()
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if self.error_message:
                raise RuntimeError(self.error_message)
            server = self._server
            if server is not None and bool(getattr(server, "started", False)):
                return
            if self._thread is not None and not self._thread.is_alive():
                raise RuntimeError(self.error_message or "Companion service stopped during startup.")
            time.sleep(0.05)

    def stop(self, *, timeout_s: float = 2.0) -> None:
        server = self._server
        if server is not None:
            try:
                server.should_exit = True
            except Exception:
                pass
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=max(0.0, float(timeout_s)))
