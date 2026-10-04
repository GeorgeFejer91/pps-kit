"""Private stdio adapter for the existing Planner API in a bundled desktop shell."""

from __future__ import annotations

import asyncio
import base64
import json
import sys
from urllib.parse import unquote, urlsplit

from .dashboard_app import DashboardController, create_app


MAX_REQUEST_LINE = 4 * 1024 * 1024
MAX_RESPONSE_BODY = 64 * 1024 * 1024
ALLOWED_METHODS = {"GET", "POST", "DELETE"}
WIRE_SCHEMA = "pps-planner-worker-stdio.v1"


def _request_parts(frame: object) -> tuple[int, str, str, bytes]:
    if not isinstance(frame, dict):
        raise ValueError("Request must be an object.")
    if frame.get("schema") != WIRE_SCHEMA:
        raise ValueError("Planner worker protocol version is unsupported.")
    request_id = frame.get("id")
    method = frame.get("method")
    path = frame.get("path")
    body = frame.get("body_base64", "")
    if not isinstance(request_id, int) or isinstance(request_id, bool) or request_id < 0:
        raise ValueError("Request id is invalid.")
    if method not in ALLOWED_METHODS or not isinstance(path, str) or not isinstance(body, str):
        raise ValueError("Request method, path, or body is invalid.")
    parsed = urlsplit(path)
    segments = unquote(parsed.path).split("/")
    if (
        not parsed.path.startswith("/api/")
        or parsed.scheme
        or parsed.netloc
        or parsed.fragment
        or any(segment in {".", ".."} for segment in segments)
    ):
        raise ValueError("Only local Planner API paths are allowed.")
    try:
        decoded = base64.b64decode(body, validate=True)
    except ValueError as exc:
        raise ValueError("Request body is not valid base64.") from exc
    if len(decoded) > MAX_REQUEST_LINE:
        raise ValueError("Request body is too large.")
    return request_id, method, path, decoded


async def _serve() -> None:
    import httpx

    wire = sys.stdout.buffer
    sys.stdout = sys.stderr
    app = create_app(DashboardController(), web_origins=[], require_mutation_token=False)
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://planner.local") as client:
            while line := await asyncio.to_thread(sys.stdin.buffer.readline, MAX_REQUEST_LINE + 1):
                if len(line) > MAX_REQUEST_LINE or not line.endswith(b"\n"):
                    break
                request_id = None
                try:
                    frame = json.loads(line)
                    if isinstance(frame, dict) and isinstance(frame.get("id"), int) and not isinstance(frame.get("id"), bool):
                        request_id = frame["id"]
                    request_id, method, path, body = _request_parts(frame)
                    response = await client.request(method, path, content=body, headers={"content-type": "application/json"})
                    if len(response.content) > MAX_RESPONSE_BODY:
                        raise ValueError("Planner response is too large.")
                    result = {
                        "schema": WIRE_SCHEMA,
                        "id": request_id,
                        "status": response.status_code,
                        "content_type": response.headers.get("content-type", "application/octet-stream"),
                        "content_disposition": response.headers.get("content-disposition", ""),
                        "body_base64": base64.b64encode(response.content).decode("ascii"),
                    }
                except (ValueError, TypeError, json.JSONDecodeError):
                    result = {"schema": WIRE_SCHEMA, "id": request_id, "status": 400, "error": "invalid_planner_request"}
                except Exception:
                    result = {"schema": WIRE_SCHEMA, "id": request_id, "status": 500, "error": "planner_worker_failed"}
                wire.write(json.dumps(result, separators=(",", ":")).encode("utf-8") + b"\n")
                wire.flush()


def main() -> int:
    asyncio.run(_serve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
