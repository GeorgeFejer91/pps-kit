from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from peripersonal_space_toolkit.dashboard_backend.security import TOKEN_HEADER
from peripersonal_space_toolkit.runner_companion import (
    DISCOVERY_DIRECTED_BROADCAST_TARGET,
    DISCOVERY_LIMITED_BROADCAST_TARGET,
    DISCOVERY_SCHEMA,
    HEALTH_SCHEMA,
    SNAPSHOT_SCHEMA,
    CompanionCommandError,
    RunnerCompanionConfig,
    RunnerCompanionService,
    build_companion_discovery_payload,
    build_pairing_uri,
    companion_discovery_payload_json,
    create_runner_companion_app,
    pairing_qr_png_bytes,
    validate_companion_discovery_payload,
    _best_effort_directed_broadcast_targets,
)
from peripersonal_space_toolkit.mobile_phone_runtime import (
    MOBILE_PACKAGE_LIST_SCHEMA,
    MOBILE_PACKAGE_SCHEMA,
    MOBILE_RUN_COMPLETE_SCHEMA,
    MOBILE_RUN_EVENTS_SCHEMA,
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
        self.paused = 0
        self.resumed = 0
        self.fail_continue = False
        self.fail_health = False
        self.fail_snapshot = False
        self.mobile_event_uploads: list[tuple[str, dict[str, Any]]] = []
        self.mobile_complete_uploads: list[tuple[str, dict[str, Any]]] = []
        self.mobile_asset_path = ""

    def health(self) -> dict[str, Any]:
        if self.fail_health:
            raise CompanionCommandError(
                "Focus Mode did not answer the companion request in time.",
                status_code=503,
                reason="ui_timeout",
            )
        return {
            "schema": HEALTH_SCHEMA,
            "status": "ok",
            "session_id": "session-001",
        }

    def snapshot(self) -> dict[str, Any]:
        if self.fail_snapshot:
            raise CompanionCommandError(
                "Focus Mode did not answer the companion request in time.",
                status_code=503,
                reason="ui_timeout",
            )
        return {
            "schema": SNAPSHOT_SCHEMA,
            "sequence": self.sequence,
            "server_unix_ms": 1000,
            "server_perf_counter_s": 12.5,
            "connection_state": "online",
            "allowed_commands": ["setup", "start_part_1", "pause"],
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

    def pause(self) -> dict[str, Any]:
        self.paused += 1
        self.sequence += 1
        return self.snapshot()

    def resume(self) -> dict[str, Any]:
        self.resumed += 1
        self.sequence += 1
        return self.snapshot()

    def mobile_packages(self) -> dict[str, Any]:
        return {
            "schema": MOBILE_PACKAGE_LIST_SCHEMA,
            "active_package_id": "pkg-001",
            "packages": [
                {
                    "package_id": "pkg-001",
                    "participant_id": "P001",
                    "session_id": "session-001",
                    "block_count": 1,
                    "asset_count": 1,
                    "total_asset_bytes": 4,
                    "mobile_runnable": True,
                    "warnings": [],
                }
            ],
        }

    def mobile_package_manifest(self, package_id: str) -> dict[str, Any]:
        if package_id != "pkg-001":
            raise CompanionCommandError(status_code=404, reason="mobile_package_not_found")
        return {
            "schema": MOBILE_PACKAGE_SCHEMA,
            "package_id": package_id,
            "participant_id": "P001",
            "blocks": [{"block_id": "block-01", "audio_asset_id": "block-01-audio", "tactile_cues": []}],
            "assets": [{"asset_id": "block-01-audio", "filename": "block.wav", "media_type": "audio/wav"}],
            "mobile_runnable": True,
        }

    def mobile_package_asset_path(self, package_id: str, asset_id: str) -> tuple[str, str]:
        if package_id != "pkg-001" or asset_id != "block-01-audio" or not self.mobile_asset_path:
            raise CompanionCommandError(status_code=404, reason="mobile_asset_not_found")
        return self.mobile_asset_path, "audio/wav"

    def mobile_run_events(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.mobile_event_uploads.append((run_id, dict(payload)))
        return {
            "schema": MOBILE_RUN_EVENTS_SCHEMA,
            "status": "accepted",
            "run_id": run_id,
            "event_count": len(payload.get("events") or []),
        }

    def mobile_run_complete(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.mobile_complete_uploads.append((run_id, dict(payload)))
        return {
            "schema": MOBILE_RUN_COMPLETE_SCHEMA,
            "status": "accepted",
            "run_id": run_id,
            "event_count": len(payload.get("events") or []),
        }


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


def test_phone_export_pairing_uri_marks_mode_transport_and_transfer():
    uri = build_pairing_uri(
        host="192.168.1.50",
        port=8767,
        session_id="transfer-1",
        token="tok",
        mode="phone_export",
        transfer_id="transfer-1",
        transport="wifi_direct",
    )
    parsed = urlparse(uri)
    query = parse_qs(parsed.query)

    assert parsed.scheme == "pps-companion"
    assert query["v"] == ["2"]
    assert query["mode"] == ["phone_export"]
    assert query["transport"] == ["wifi_direct"]
    assert query["transfer_id"] == ["transfer-1"]
    assert query["token"] == ["tok"]


def test_pairing_qr_generation_returns_png_bytes():
    pytest.importorskip("qrcode")
    png = pairing_qr_png_bytes("pps-companion://pair?host=127.0.0.1&token=t")

    assert png.startswith(b"\x89PNG\r\n\x1a\n")


def test_discovery_payload_advertises_endpoint_without_pairing_token():
    payload = build_companion_discovery_payload(
        host="192.168.43.1",
        port=8767,
        session_id="session-001",
        mode="phone_export",
        transfer_id="transfer-001",
        transport="phone_hotspot",
    )
    raw = companion_discovery_payload_json(payload)

    assert payload["schema"] == DISCOVERY_SCHEMA
    assert payload["network_scope"] == "same_lan_or_local_hotspot"
    assert payload["discovery"]["also_sent_as_limited_broadcast"] is True
    assert payload["discovery"]["broadcast_targets"] == [
        DISCOVERY_LIMITED_BROADCAST_TARGET,
        DISCOVERY_DIRECTED_BROADCAST_TARGET,
    ]
    assert payload["pairing"]["host"] == "192.168.43.1"
    assert payload["pairing"]["token_required"] is True
    assert payload["pairing"]["token_delivery"] == "qr_or_manual_uri_only"
    assert "secret" not in raw.lower()
    assert '"token":' not in raw


def test_discovery_payload_validates_same_lan_or_hotspot_contract():
    payload = build_companion_discovery_payload(
        host="192.168.43.1",
        port=8767,
        session_id="session-001",
        transport="phone_hotspot",
    )

    validate_companion_discovery_payload(payload)

    assert payload["network_scope"] == "same_lan_or_local_hotspot"
    assert payload["discovery"]["udp_multicast_group"] == "239.255.77.83"
    assert payload["discovery"]["udp_port"] == 48767
    assert payload["discovery"]["broadcast_targets"] == [
        "255.255.255.255",
        "interface_ipv4_directed_broadcasts",
    ]
    assert payload["discovery"]["ttl"] == 1
    assert payload["privacy"]["contains_pairing_token"] is False
    assert payload["privacy"]["contains_participant_demographics"] is False
    assert payload["privacy"]["stream_names_are_generic"] is True


def test_discovery_payload_json_rejects_token_leakage():
    payload = build_companion_discovery_payload(host="127.0.0.1", port=8767, session_id="session-001")
    payload["pairing"]["token"] = "secret"

    with pytest.raises(ValueError, match="pairing tokens"):
        companion_discovery_payload_json(payload)


def test_discovery_payload_json_rejects_nested_token_leakage():
    payload = build_companion_discovery_payload(host="127.0.0.1", port=8767, session_id="session-001")
    payload["debug"] = {"companion_token": "secret"}

    with pytest.raises(ValueError, match="pairing tokens"):
        companion_discovery_payload_json(payload)


def test_discovery_payload_json_rejects_demographic_privacy_leakage():
    payload = build_companion_discovery_payload(host="127.0.0.1", port=8767, session_id="session-001")
    payload["privacy"]["contains_participant_demographics"] = True

    with pytest.raises(ValueError, match="participant_demographics=false"):
        companion_discovery_payload_json(payload)


def test_discovery_payload_json_rejects_hidden_participant_identifier():
    payload = build_companion_discovery_payload(host="127.0.0.1", port=8767, session_id="session-001")
    payload["debug"] = {"participant_id": "P001"}

    with pytest.raises(ValueError, match="participant demographics or identifiers"):
        companion_discovery_payload_json(payload)


def test_discovery_payload_json_rejects_hidden_lsl_stream_names():
    payload = build_companion_discovery_payload(host="127.0.0.1", port=8767, session_id="session-001")
    payload["debug"] = {"lsl_stream_name": "P001_PPSMarkersV2"}

    with pytest.raises(ValueError, match="LSL stream names"):
        companion_discovery_payload_json(payload)


def test_discovery_payload_json_rejects_unknown_transport():
    with pytest.raises(ValueError, match="Unsupported companion discovery transport"):
        build_companion_discovery_payload(
            host="127.0.0.1",
            port=8767,
            session_id="session-001",
            transport="public_internet",
        )


def test_discovery_payload_json_rejects_missing_directed_broadcast_fallback():
    payload = build_companion_discovery_payload(host="127.0.0.1", port=8767, session_id="session-001")
    payload["discovery"]["broadcast_targets"] = ["255.255.255.255"]

    with pytest.raises(ValueError, match="directed interface broadcast"):
        companion_discovery_payload_json(payload)


def test_discovery_best_effort_directed_broadcast_targets_ignore_public_and_loopback_addresses():
    targets = _best_effort_directed_broadcast_targets(
        ("127.0.0.1", "8.8.8.8", "192.168.43.1", "10.0.2.15", "169.254.7.33", "not-an-ip"),
    )

    assert targets == ("10.0.2.255", "169.254.7.255", "192.168.43.255")


def test_discovery_payload_json_requires_transfer_id_for_phone_export():
    with pytest.raises(ValueError, match="require a transfer_id"):
        build_companion_discovery_payload(
            host="127.0.0.1",
            port=8767,
            session_id="session-001",
            mode="phone_export",
        )


def test_service_discovery_payload_can_advertise_phone_export_transfer():
    service = RunnerCompanionService(
        FakeBridge(),
        token="secret",
        config=RunnerCompanionConfig(host="0.0.0.0", port=8767, advertise_ip="192.168.43.1"),
        discovery_mode="phone_export",
        discovery_transfer_id="transfer-001",
        discovery_transport="phone_hotspot",
    )

    payload = service.discovery_payload()

    assert payload["pairing"]["host"] == "192.168.43.1"
    assert payload["pairing"]["mode"] == "phone_export"
    assert payload["pairing"]["transfer_id"] == "transfer-001"
    assert payload["pairing"]["transport"] == "phone_hotspot"
    assert "token" not in payload["pairing"]
    assert DISCOVERY_LIMITED_BROADCAST_TARGET in service.discovery.status()["broadcast_targets"]


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


def test_bridge_timeout_errors_are_http_safe_for_health_and_snapshot():
    bridge = FakeBridge()
    client = _client(bridge)

    bridge.fail_health = True
    health = client.get("/api/runner/health")
    assert health.status_code == 503
    assert health.json()["detail"]["reason"] == "ui_timeout"

    bridge.fail_health = False
    bridge.fail_snapshot = True
    snapshot = client.get("/api/runner/snapshot", headers={TOKEN_HEADER: "secret"})
    assert snapshot.status_code == 503
    assert snapshot.json()["detail"]["reason"] == "ui_timeout"


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

    pause = client.post("/api/runner/commands/pause", headers=headers)
    resume = client.post("/api/runner/commands/resume", headers=headers)
    assert pause.status_code == 200
    assert resume.status_code == 200
    assert bridge.paused == 1
    assert bridge.resumed == 1


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


def test_pause_resume_exist_but_stop_and_participant_switching_stay_laptop_only():
    paths = {route.path for route in create_runner_companion_app(FakeBridge(), token="secret").routes}

    assert "/api/runner/commands/pause" in paths
    assert "/api/runner/commands/resume" in paths
    assert "/api/runner/commands/stop" not in paths
    assert "/api/runner/participants" not in paths


def test_mobile_package_routes_are_token_gated_and_route_through_bridge(tmp_path):
    bridge = FakeBridge()
    asset = tmp_path / "block.wav"
    asset.write_bytes(b"RIFF")
    bridge.mobile_asset_path = str(asset)
    client = _client(bridge)
    headers = {TOKEN_HEADER: "secret"}

    denied = client.get("/api/mobile/packages")
    assert denied.status_code == 403

    packages = client.get("/api/mobile/packages", headers=headers)
    assert packages.status_code == 200
    assert packages.json()["schema"] == MOBILE_PACKAGE_LIST_SCHEMA
    assert packages.json()["packages"][0]["mobile_runnable"] is True

    manifest = client.get("/api/mobile/packages/pkg-001/manifest", headers=headers)
    assert manifest.status_code == 200
    assert manifest.json()["schema"] == MOBILE_PACKAGE_SCHEMA
    assert manifest.json()["blocks"][0]["audio_asset_id"] == "block-01-audio"

    downloaded = client.get("/api/mobile/packages/pkg-001/assets/block-01-audio", headers=headers)
    assert downloaded.status_code == 200
    assert downloaded.content == b"RIFF"

    events = client.post(
        "/api/mobile/runs/run-001/events",
        headers=headers,
        json={"package_id": "pkg-001", "events": [{"type": "tap"}]},
    )
    complete = client.post(
        "/api/mobile/runs/run-001/complete",
        headers=headers,
        json={"package_id": "pkg-001", "events": [{"type": "complete"}]},
    )
    assert events.status_code == 200
    assert events.json()["schema"] == MOBILE_RUN_EVENTS_SCHEMA
    assert complete.status_code == 200
    assert complete.json()["schema"] == MOBILE_RUN_COMPLETE_SCHEMA
    assert bridge.mobile_event_uploads[-1][0] == "run-001"
    assert bridge.mobile_complete_uploads[-1][1]["events"][0]["type"] == "complete"


def test_websocket_replays_snapshot_and_marks_heartbeats():
    bridge = FakeBridge()
    client = _client(bridge)

    with client.websocket_connect("/api/runner/ws", headers={TOKEN_HEADER: "secret"}) as websocket:
        first = websocket.receive_json()
        second = websocket.receive_json()

    assert first["schema"] == SNAPSHOT_SCHEMA
    assert first["message_type"] == "snapshot"
    assert second["message_type"] == "heartbeat"
