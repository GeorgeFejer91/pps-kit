"""Check the desktop Planner worker without opening a local HTTP listener."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path


def test_planner_worker_accepts_api_and_rejects_other_paths(tmp_path):
    requests = [
        {"schema": "pps-planner-worker-stdio.v1", "id": 1, "method": "GET", "path": "/api/health"},
        {"schema": "pps-planner-worker-stdio.v1", "id": 2, "method": "GET", "path": "/api/capabilities"},
        {"schema": "pps-planner-worker-stdio.v1", "id": 3, "method": "GET", "path": "http://elsewhere.example/api/health"},
        {"schema": "pps-planner-worker-stdio.v1", "id": 4, "method": "GET", "path": "/api/../dashboard/compiled/index.html"},
        {
            "schema": "pps-planner-worker-stdio.v1",
            "id": 5,
            "method": "POST",
            "path": "/api/project/new-custom",
            "body_base64": base64.b64encode(b'{"name":"Worker smoke study"}').decode("ascii"),
        },
        {"schema": "unsupported", "id": 6, "method": "GET", "path": "/api/health"},
    ]
    payload = "".join(json.dumps(request) + "\n" for request in requests)
    source_root = Path(__file__).resolve().parents[3] / "packages" / "pps-runtime" / "src"
    environment = {
        **os.environ,
        "PPS_TOOLKIT_DATA_ROOT": str(tmp_path),
        "PYTHONPATH": os.pathsep.join([str(source_root), os.environ.get("PYTHONPATH", "")]),
    }
    process = subprocess.run(
        [sys.executable, "-m", "peripersonal_space_toolkit.planner_worker"],
        input=payload,
        text=True,
        capture_output=True,
        env=environment,
        timeout=30,
        check=True,
    )
    replies = [json.loads(line) for line in process.stdout.splitlines()]
    assert all(reply["schema"] == "pps-planner-worker-stdio.v1" for reply in replies)
    assert [reply["id"] for reply in replies] == [1, 2, 3, 4, 5, 6]
    assert [reply["status"] for reply in replies] == [200, 200, 400, 400, 200, 400]
    health = json.loads(base64.b64decode(replies[0]["body_base64"]))
    capabilities = json.loads(base64.b64decode(replies[1]["body_base64"]))
    assert health["status"] == "ok"
    assert capabilities["schema"] == "pps-designer-capabilities.v1"
    assert all("body_base64" not in reply for reply in replies[2:4])
    custom = json.loads(base64.b64decode(replies[4]["body_base64"]))
    assert custom["design"]["name"] == "Worker smoke study"
