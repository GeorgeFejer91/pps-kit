"""LAN companion service for the native Focus Mode runner."""

from __future__ import annotations

import asyncio
import json
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
PHONE_EXPORT_PAIRING_SCHEMA_VERSION = "2"
DISCOVERY_SCHEMA = "pps-runner-companion-discovery.v1"
DISCOVERY_SERVICE = "pps-runner-companion"
DISCOVERY_MULTICAST_GROUP = "239.255.77.83"
DISCOVERY_PORT = 48767
DISCOVERY_INTERVAL_S = 1.0
DISCOVERY_NETWORK_SCOPE = "same_lan_or_local_hotspot"
DISCOVERY_TOKEN_DELIVERY = "qr_or_manual_uri_only"
DISCOVERY_ALLOWED_MODES = frozenset({"pc_runner", "phone_export"})
DISCOVERY_ALLOWED_TRANSPORTS = frozenset({"lan", "phone_hotspot", "wifi_direct"})


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

    def mobile_packages(self) -> dict[str, Any]:
        ...

    def mobile_package_manifest(self, package_id: str) -> dict[str, Any]:
        ...

    def mobile_package_asset_path(self, package_id: str, asset_id: str) -> tuple[str, str]:
        ...

    def mobile_run_events(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    def mobile_run_complete(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
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
    mode: str = "pc_runner",
    transfer_id: str = "",
    transport: str = "lan",
) -> str:
    payload = {
        "v": PAIRING_SCHEMA_VERSION,
        "host": str(host),
        "port": str(int(port)),
        "session_id": str(session_id),
        "token": str(token),
    }
    if str(mode or "pc_runner") != "pc_runner" or str(transfer_id or "").strip() or str(transport or "lan") != "lan":
        payload.update(
            {
                "v": PHONE_EXPORT_PAIRING_SCHEMA_VERSION,
                "mode": str(mode or "pc_runner"),
                "transport": str(transport or "lan"),
            }
        )
        if str(transfer_id or "").strip():
            payload["transfer_id"] = str(transfer_id)
    query = urlencode(payload)
    return f"{PAIRING_SCHEME}://pair?{query}"


def build_companion_discovery_payload(
    *,
    host: str,
    port: int,
    session_id: str,
    mode: str = "pc_runner",
    transfer_id: str = "",
    transport: str = "lan",
    service_name: str = "PPS Runner Companion",
) -> dict[str, Any]:
    """Build the token-free LAN discovery packet advertised by the companion service."""

    clean_mode = str(mode or "pc_runner")
    clean_transport = str(transport or "lan")
    clean_transfer_id = str(transfer_id or "").strip()
    if clean_mode not in DISCOVERY_ALLOWED_MODES:
        raise ValueError(f"Unsupported companion discovery mode: {clean_mode}")
    if clean_transport not in DISCOVERY_ALLOWED_TRANSPORTS:
        raise ValueError(f"Unsupported companion discovery transport: {clean_transport}")
    if clean_mode == "phone_export" and not clean_transfer_id:
        raise ValueError("Phone-export discovery payloads require a transfer_id.")
    payload: dict[str, Any] = {
        "schema": DISCOVERY_SCHEMA,
        "service": DISCOVERY_SERVICE,
        "service_name": str(service_name or "PPS Runner Companion"),
        "generated_unix_ms": int(time.time() * 1000),
        "network_scope": DISCOVERY_NETWORK_SCOPE,
        "discovery": {
            "udp_multicast_group": DISCOVERY_MULTICAST_GROUP,
            "udp_port": DISCOVERY_PORT,
            "also_sent_as_limited_broadcast": True,
            "ttl": 1,
        },
        "pairing": {
            "scheme": PAIRING_SCHEME,
            "host": str(host),
            "port": int(port),
            "session_id": str(session_id),
            "mode": clean_mode,
            "transport": clean_transport,
            "token_required": True,
            "token_delivery": DISCOVERY_TOKEN_DELIVERY,
        },
        "privacy": {
            "contains_pairing_token": False,
            "contains_participant_demographics": False,
            "stream_names_are_generic": True,
        },
    }
    if clean_transfer_id:
        payload["pairing"]["transfer_id"] = clean_transfer_id
    return payload


def validate_companion_discovery_payload(payload: dict[str, Any]) -> None:
    """Validate the token-free LAN discovery packet contract before broadcast."""

    if not isinstance(payload, dict):
        raise ValueError("Discovery payload must be a JSON object.")
    if payload.get("schema") != DISCOVERY_SCHEMA:
        raise ValueError("Discovery payload schema mismatch.")
    if payload.get("service") != DISCOVERY_SERVICE:
        raise ValueError("Discovery payload service mismatch.")
    if payload.get("network_scope") != DISCOVERY_NETWORK_SCOPE:
        raise ValueError("Discovery payload network scope must be same_lan_or_local_hotspot.")
    if "token" in payload or "companion_token" in payload:
        raise ValueError("Discovery payloads must not contain pairing tokens.")
    discovery = payload.get("discovery") if isinstance(payload.get("discovery"), dict) else {}
    if discovery.get("udp_multicast_group") != DISCOVERY_MULTICAST_GROUP:
        raise ValueError("Discovery multicast group mismatch.")
    if int(discovery.get("udp_port") or 0) != DISCOVERY_PORT:
        raise ValueError("Discovery UDP port mismatch.")
    if discovery.get("also_sent_as_limited_broadcast") is not True:
        raise ValueError("Discovery payload must declare limited-broadcast fallback.")
    if int(discovery.get("ttl") or 0) != 1:
        raise ValueError("Discovery multicast TTL must be 1 for local-network scope.")

    pairing = payload.get("pairing") if isinstance(payload.get("pairing"), dict) else {}
    if not pairing:
        raise ValueError("Discovery pairing metadata is missing.")
    if "token" in pairing or "companion_token" in pairing:
        raise ValueError("Discovery pairing metadata must not contain pairing tokens.")
    if pairing.get("scheme") != PAIRING_SCHEME:
        raise ValueError("Discovery pairing scheme mismatch.")
    if not str(pairing.get("host") or "").strip():
        raise ValueError("Discovery pairing host is missing.")
    port = int(pairing.get("port") or 0)
    if port < 1 or port > 65535:
        raise ValueError("Discovery pairing port is invalid.")
    if not str(pairing.get("session_id") or "").strip():
        raise ValueError("Discovery pairing session_id is missing.")
    mode = str(pairing.get("mode") or "pc_runner")
    transport = str(pairing.get("transport") or "lan")
    if mode not in DISCOVERY_ALLOWED_MODES:
        raise ValueError("Discovery pairing mode is unsupported.")
    if transport not in DISCOVERY_ALLOWED_TRANSPORTS:
        raise ValueError("Discovery pairing transport is unsupported.")
    if mode == "phone_export" and not str(pairing.get("transfer_id") or "").strip():
        raise ValueError("Phone-export discovery pairing metadata requires transfer_id.")
    if pairing.get("token_required") is not True:
        raise ValueError("Discovery pairing metadata must require a token.")
    if pairing.get("token_delivery") != DISCOVERY_TOKEN_DELIVERY:
        raise ValueError("Discovery pairing token_delivery must be qr_or_manual_uri_only.")

    privacy = payload.get("privacy") if isinstance(payload.get("privacy"), dict) else {}
    if privacy.get("contains_pairing_token") is not False:
        raise ValueError("Discovery privacy must declare contains_pairing_token=false.")
    if privacy.get("contains_participant_demographics") is not False:
        raise ValueError("Discovery privacy must declare contains_participant_demographics=false.")
    if privacy.get("stream_names_are_generic") is not True:
        raise ValueError("Discovery privacy must declare generic stream names.")


def companion_discovery_payload_json(payload: dict[str, Any]) -> str:
    validate_companion_discovery_payload(payload)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


class RunnerCompanionDiscoveryAdvertiser:
    """Best-effort local UDP discovery announcer for QR/manual companion pairing."""

    def __init__(
        self,
        payload_factory: Any,
        *,
        multicast_group: str = DISCOVERY_MULTICAST_GROUP,
        port: int = DISCOVERY_PORT,
        interval_s: float = DISCOVERY_INTERVAL_S,
    ) -> None:
        self.payload_factory = payload_factory
        self.multicast_group = str(multicast_group)
        self.port = int(port)
        self.interval_s = max(0.25, float(interval_s))
        self.sent_count = 0
        self.last_error = ""
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="pps-companion-discovery", daemon=True)
        self._thread.start()

    def stop(self, *, timeout_s: float = 1.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=max(0.0, float(timeout_s)))

    def status(self) -> dict[str, Any]:
        return {
            "schema": "pps-runner-companion-discovery-advertiser-status.v1",
            "enabled": self._thread is not None and self._thread.is_alive(),
            "multicast_group": self.multicast_group,
            "port": self.port,
            "interval_s": self.interval_s,
            "sent_count": self.sent_count,
            "last_error": self.last_error,
        }

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                payload = self.payload_factory()
                self._send(companion_discovery_payload_json(payload).encode("utf-8"))
                self.sent_count += 1
                self.last_error = ""
            except Exception as exc:  # noqa: BLE001 - discovery must never break the runner.
                self.last_error = str(exc)
            self._stop.wait(self.interval_s)

    def _send(self, data: bytes) -> None:
        errors: list[str] = []
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as udp:
            udp.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
            try:
                udp.sendto(data, (self.multicast_group, self.port))
            except Exception as exc:  # noqa: BLE001 - try limited broadcast below.
                errors.append(f"multicast: {exc}")
            udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            try:
                udp.sendto(data, ("255.255.255.255", self.port))
            except Exception as exc:  # noqa: BLE001 - surfaced as nonfatal advertiser status.
                errors.append(f"broadcast: {exc}")
        if len(errors) >= 2:
            raise RuntimeError("; ".join(errors))


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
        from fastapi.responses import FileResponse
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

    @app.get("/api/mobile/packages")
    def mobile_packages(companion_token: str = Header(default="", alias=TOKEN_HEADER)) -> dict[str, Any]:
        _authorize_token(companion_token)
        try:
            return bridge.mobile_packages()
        except CompanionCommandError as exc:
            _handle_command_error(exc)

    @app.get("/api/mobile/packages/{package_id}/manifest")
    def mobile_package_manifest(
        package_id: str,
        companion_token: str = Header(default="", alias=TOKEN_HEADER),
    ) -> dict[str, Any]:
        _authorize_token(companion_token)
        try:
            return bridge.mobile_package_manifest(package_id)
        except CompanionCommandError as exc:
            _handle_command_error(exc)

    @app.get("/api/mobile/packages/{package_id}/assets/{asset_id}")
    def mobile_package_asset(
        package_id: str,
        asset_id: str,
        companion_token: str = Header(default="", alias=TOKEN_HEADER),
    ) -> Any:
        _authorize_token(companion_token)
        try:
            path, media_type = bridge.mobile_package_asset_path(package_id, asset_id)
        except CompanionCommandError as exc:
            _handle_command_error(exc)
        return FileResponse(path, media_type=media_type or "application/octet-stream")

    @app.post("/api/mobile/runs/{run_id}/events")
    def mobile_run_events(
        run_id: str,
        payload: dict[str, Any] | None = Body(default=None),
        companion_token: str = Header(default="", alias=TOKEN_HEADER),
    ) -> dict[str, Any]:
        _authorize_token(companion_token)
        try:
            return bridge.mobile_run_events(run_id, dict(payload or {}))
        except CompanionCommandError as exc:
            _handle_command_error(exc)

    @app.post("/api/mobile/runs/{run_id}/complete")
    def mobile_run_complete(
        run_id: str,
        payload: dict[str, Any] | None = Body(default=None),
        companion_token: str = Header(default="", alias=TOKEN_HEADER),
    ) -> dict[str, Any]:
        _authorize_token(companion_token)
        try:
            return bridge.mobile_run_complete(run_id, dict(payload or {}))
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
        discovery_mode: str = "pc_runner",
        discovery_transfer_id: str = "",
        discovery_transport: str = "lan",
    ) -> None:
        self.bridge = bridge
        self.config = config or RunnerCompanionConfig()
        self.token = token or generate_companion_token()
        self.discovery_mode = str(discovery_mode or "pc_runner")
        self.discovery_transfer_id = str(discovery_transfer_id or "")
        self.discovery_transport = str(discovery_transport or "lan")
        self.app = create_runner_companion_app(bridge, token=self.token)
        self._server: Any | None = None
        self._thread: threading.Thread | None = None
        self.discovery = RunnerCompanionDiscoveryAdvertiser(self.discovery_payload)
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

    def discovery_payload(
        self,
        *,
        mode: str = "",
        transfer_id: str = "",
        transport: str = "",
    ) -> dict[str, Any]:
        session_id = str(self.bridge.health().get("session_id") or "")
        return build_companion_discovery_payload(
            host=self.config.advertised_host,
            port=self.config.port,
            session_id=session_id,
            mode=str(mode or self.discovery_mode),
            transfer_id=str(transfer_id or self.discovery_transfer_id),
            transport=str(transport or self.discovery_transport),
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
                self.discovery.start()
                return
            if self._thread is not None and not self._thread.is_alive():
                raise RuntimeError(self.error_message or "Companion service stopped during startup.")
            time.sleep(0.05)

    def stop(self, *, timeout_s: float = 2.0) -> None:
        self.discovery.stop(timeout_s=timeout_s)
        server = self._server
        if server is not None:
            try:
                server.should_exit = True
            except Exception:
                pass
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=max(0.0, float(timeout_s)))
