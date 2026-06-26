from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from peripersonal_space_toolkit.dashboard_backend.security import TOKEN_HEADER
from peripersonal_space_toolkit.runner_companion import (
    HEALTH_SCHEMA,
    SNAPSHOT_SCHEMA,
    CompanionCommandError,
    build_pairing_uri,
    create_runner_companion_app,
    pairing_qr_png_bytes,
)


pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402


class FakeBridge:
    def __init__(self) -> None:
        self.sequence = 1
        self.setup_payloads: list[dict[str, Any]] = []
        self.continued = 0
        self.started_parts: list[int] = []
        self.fail_continue = False

    def health(self) -> dict[str, Any]:
        return {
            "schema": HEALTH_SCHEMA,
            "status": "ok",
            "session_id": "session-001",
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema": SNAPSHOT_SCHEMA,
            "sequence": self.sequence,
            "server_unix_ms": 1000,
            "server_perf_counter_s": 12.5,
            "connection_state": "online",
            "allowed_commands": ["setup", "start_part_1"],
            "participant": {"participant_id": "P001"},
            "setup": {"submitted": False},
            "part_status": {"available_parts": ["1", "2"]},
            "run_status": {"running": False},
            "run_plan": [],
            "active_block": {
                "duration_s": 10.0,
                "elapsed_s": 0.0,
                "last_anchor_server_perf_counter_s": 12.5,
                "running": False,
                "paused": False,
                "instruction_waiting": False,
            },
            "timeline": {"trial_rows": [], "tactile_cues": [], "clicks": [], "counts": {"clicks": 0}},
            "topup": {"draft_count": 0},
            "instruction_gate": {"waiting": False},
        }

    def submit_setup(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.setup_payloads.append(dict(payload))
        self.sequence += 1
        return self.snapshot()

    def continue_instruction(self) -> dict[str, Any]:
        if self.fail_continue:
            raise CompanionCommandError(reason="no_instruction_gate")
        self.continued += 1
        self.sequence += 1
        return self.snapshot()

    def start_part(self, part_number: int) -> dict[str, Any]:
        self.started_parts.append(int(part_number))
        self.sequence += 1
        return self.snapshot()


def _client(bridge: FakeBridge, token: str = "secret") -> TestClient:
    return TestClient(create_runner_companion_app(bridge, token=token))


def test_pairing_uri_contains_lan_endpoint_session_and_token():
    uri = build_pairing_uri(host="192.168.1.50", port=8767, session_id="abc", token="tok")
    parsed = urlparse(uri)
    query = parse_qs(parsed.query)

    assert parsed.scheme == "pps-companion"
    assert parsed.netloc == "pair"
    assert query["host"] == ["192.168.1.50"]
    assert query["port"] == ["8767"]
    assert query["session_id"] == ["abc"]
    assert query["token"] == ["tok"]


def test_pairing_qr_generation_returns_png_bytes():
    pytest.importorskip("qrcode")
    png = pairing_qr_png_bytes("pps-companion://pair?host=127.0.0.1&token=t")

    assert png.startswith(b"\x89PNG\r\n\x1a\n")


def test_health_is_public_but_snapshot_requires_token():
    bridge = FakeBridge()
    client = _client(bridge)

    health = client.get("/api/runner/health")
    assert health.status_code == 200
    assert health.json()["security"]["token_required"] is True

    denied = client.get("/api/runner/snapshot")
    assert denied.status_code == 403

    allowed = client.get("/api/runner/snapshot", headers={TOKEN_HEADER: "secret"})
    assert allowed.status_code == 200
    assert allowed.json()["schema"] == SNAPSHOT_SCHEMA


def test_setup_and_commands_route_through_bridge():
    bridge = FakeBridge()
    client = _client(bridge)
    headers = {TOKEN_HEADER: "secret"}

    setup = client.post(
        "/api/runner/setup",
        headers=headers,
        json={
            "participant_code": "P001",
            "participant_name": "Participant One",
            "age": "30",
            "handedness": "right",
            "gender": "prefer_not_to_say",
            "name_sharing_opt_in": False,
        },
    )
    assert setup.status_code == 200
    assert bridge.setup_payloads[-1]["participant_name"] == "Participant One"

    continue_response = client.post("/api/runner/commands/continue-instruction", headers=headers)
    assert continue_response.status_code == 200
    assert bridge.continued == 1

    part1 = client.post("/api/runner/commands/start-part", headers=headers, json={"part_number": 1})
    part2 = client.post("/api/runner/commands/start-part", headers=headers, json={"part_number": 2})
    assert part1.status_code == 200
    assert part2.status_code == 200
    assert bridge.started_parts == [1, 2]


def test_command_gating_errors_are_http_safe():
    bridge = FakeBridge()
    bridge.fail_continue = True
    client = _client(bridge)

    response = client.post("/api/runner/commands/continue-instruction", headers={TOKEN_HEADER: "secret"})
    assert response.status_code == 409
    assert response.json()["detail"]["reason"] == "no_instruction_gate"

    invalid_part = client.post("/api/runner/commands/start-part", headers={TOKEN_HEADER: "secret"}, json={"part_number": 3})
    assert invalid_part.status_code == 400
    assert invalid_part.json()["detail"]["reason"] == "invalid_part_number"


def test_no_pause_stop_or_participant_switching_endpoints_exist():
    paths = {route.path for route in create_runner_companion_app(FakeBridge(), token="secret").routes}

    assert "/api/runner/commands/pause" not in paths
    assert "/api/runner/commands/stop" not in paths
    assert "/api/runner/participants" not in paths


def test_websocket_replays_snapshot_and_marks_heartbeats():
    bridge = FakeBridge()
    client = _client(bridge)

    with client.websocket_connect("/api/runner/ws", headers={TOKEN_HEADER: "secret"}) as websocket:
        first = websocket.receive_json()
        second = websocket.receive_json()

    assert first["schema"] == SNAPSHOT_SCHEMA
    assert first["message_type"] == "snapshot"
    assert second["message_type"] == "heartbeat"
