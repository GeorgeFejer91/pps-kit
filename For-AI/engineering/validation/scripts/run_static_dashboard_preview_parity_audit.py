#!/usr/bin/env python
"""Audit hosted/static dashboard profile previews against local dashboard truth."""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


REPO_ROOT = Path(__file__).resolve().parents[4]
SRC_ROOT = REPO_ROOT / "packages" / "pps-runtime" / "src"
RESOURCE_ROOT = REPO_ROOT / "packages" / "pps-resources"
SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

import run_profile_recreation_interface_matrix as profile_matrix  # noqa: E402
from peripersonal_space_toolkit.profile_recreation import READY_RUNNER, load_profile_recreation_status  # noqa: E402


SCHEMA = "pps-static-dashboard-preview-parity-audit.v1"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "validation_runs" / "static_dashboard_preview_parity_audit"
DIRECT_DASHBOARD_PATH = "apps/designer/frontend/index.html"
AUDIT_QUERY = {
    "page": "toolkit",
    "forceStaticPreview": "1",
    "auditStaticPreview": "1",
}
COMPANION_REQUIRED_CONTROL_IDS = {
    "export-data-acquisition-folder",
    "bake-stimulus",
    "bake-trial-sequences",
    "bake-trial-files",
    "apply-trial-pool-repetitions",
    "bake-trial-pool",
    "regenerate-block-csvs",
    "accept-block-csvs",
    "regenerate-run-sequence",
    "export-output-folder",
    "prepare-experiment",
}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit static dashboard profile preview parity.")
    parser.add_argument(
        "--profile-set",
        choices=["all", "ready-all"],
        default="all",
        help="Profiles to audit. `all` includes blocked profiles for blocker-state parity.",
    )
    parser.add_argument("--template", action="append", default=[], help="Template ID to audit. Repeat for multiple IDs.")
    parser.add_argument(
        "--dashboard-url",
        action="append",
        default=[],
        help="Dashboard base or direct URL to audit. Defaults to a local static server rooted at the repo.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--browser-headed", action="store_true")
    parser.add_argument("--timeout-ms", type=int, default=60_000)
    parser.add_argument(
        "--skip-materialization",
        action="store_true",
        help="Skip local Segment 0-6 materialization and check only static metadata/gates.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    report = run_audit(
        output_dir=args.output_dir,
        profile_set=args.profile_set,
        templates=args.template,
        dashboard_urls=args.dashboard_url,
        host=args.host,
        port=args.port,
        browser_headed=args.browser_headed,
        timeout_ms=args.timeout_ms,
        skip_materialization=args.skip_materialization,
    )
    print(f"Wrote static dashboard preview parity audit: {report['report_json']}")
    return 0 if report["passed"] else 1


def run_audit(
    *,
    output_dir: Path,
    profile_set: str = "all",
    templates: list[str] | None = None,
    dashboard_urls: list[str] | None = None,
    host: str = "127.0.0.1",
    port: int = 0,
    browser_headed: bool = False,
    timeout_ms: int = 60_000,
    skip_materialization: bool = False,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    status = load_profile_recreation_status(RESOURCE_ROOT)
    inventory = _load_preload_inventory()
    selected_ids = templates or _target_template_ids(inventory, status, profile_set=profile_set)
    known_ids = {str(profile.get("template_id") or "") for profile in inventory.get("profiles", [])}
    unknown = sorted(set(selected_ids) - known_ids)
    if unknown:
        raise SystemExit(f"Unknown static profile ID(s): {', '.join(unknown)}")

    server: StaticServer | None = None
    urls = list(dashboard_urls or [])
    if not urls:
        server = _start_static_server(host=host, port=port)
        urls = [server.url]

    ready_ids = [template_id for template_id in selected_ids if _is_ready_profile(_profile_status(status, template_id))]
    local_authority: dict[str, dict[str, Any]] = {}
    if not skip_materialization:
        for template_id in ready_ids:
            print(f"[static-parity] materialize {template_id}", flush=True)
            local_authority[template_id] = profile_matrix._materialize_ready_profile(template_id, output_dir=output_dir)

    try:
        url_reports = []
        failures: list[str] = []
        for url in urls:
            direct_url = dashboard_audit_url(url)
            print(f"[static-parity] inspect {direct_url}", flush=True)
            snapshots = _collect_browser_snapshots(
                direct_url,
                selected_ids,
                browser_headed=browser_headed,
                timeout_ms=timeout_ms,
            )
            comparison = _compare_snapshots(
                snapshots,
                selected_ids=selected_ids,
                status=status,
                inventory=inventory,
                local_authority=local_authority,
                materialization_required=not skip_materialization,
            )
            failures.extend(f"{direct_url}: {failure}" for failure in comparison["failures"])
            url_reports.append(
                {
                    "dashboard_url": direct_url,
                    "profile_count": len(selected_ids),
                    "ready_profile_count": len(ready_ids),
                    "passed": not comparison["failures"],
                    "failures": comparison["failures"],
                    "profile_results": comparison["profile_results"],
                }
            )
    finally:
        if server:
            server.stop()

    report = {
        "schema": SCHEMA,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "passed": not failures,
        "profile_set": profile_set,
        "profile_count": len(selected_ids),
        "ready_profile_count": len(ready_ids),
        "profiles": selected_ids,
        "materialization_checked": not skip_materialization,
        "dashboard_reports": url_reports,
        "failures": failures,
        "report_json": str(output_dir / "static_dashboard_preview_parity_audit_report.json"),
        "report_md": str(output_dir / "static_dashboard_preview_parity_audit_report.md"),
    }
    _write_json(Path(report["report_json"]), report)
    _write_markdown(Path(report["report_md"]), report)
    return report


def dashboard_audit_url(url: str) -> str:
    parts = urlsplit(str(url).strip())
    if not parts.scheme or not parts.netloc:
        raise ValueError(f"Dashboard URL must be absolute: {url}")
    path = parts.path or "/"
    if not path.endswith(".html"):
        path = "/".join([path.rstrip("/"), DIRECT_DASHBOARD_PATH]).replace("//", "/")
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(AUDIT_QUERY)
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query), parts.fragment))


def _collect_browser_snapshots(
    dashboard_url: str,
    template_ids: list[str],
    *,
    browser_headed: bool,
    timeout_ms: int,
) -> dict[str, dict[str, Any]]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError("Python Playwright is required for static dashboard parity audit.") from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not browser_headed)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.goto(dashboard_url, wait_until="networkidle", timeout=timeout_ms)
        page.wait_for_function(
            "() => window.PPSDashboardAudit && window.PPSDashboardAudit.snapshot().loaded",
            timeout=timeout_ms,
        )
        snapshots: dict[str, dict[str, Any]] = {}
        for template_id in template_ids:
            print(f"[static-parity] snapshot {template_id}", flush=True)
            page.select_option("#template-select", template_id)
            page.wait_for_function(
                "(templateId) => window.PPSDashboardAudit && window.PPSDashboardAudit.snapshot().selected_template === templateId",
                arg=template_id,
                timeout=timeout_ms,
            )
            snapshots[template_id] = page.evaluate("() => window.PPSDashboardAudit.snapshot()")
        browser.close()
    return snapshots


def _compare_snapshots(
    snapshots: dict[str, dict[str, Any]],
    *,
    selected_ids: list[str],
    status: dict[str, Any],
    inventory: dict[str, Any],
    local_authority: dict[str, dict[str, Any]],
    materialization_required: bool,
) -> dict[str, Any]:
    failures: list[str] = []
    profile_results = []
    first_snapshot = snapshots.get(selected_ids[0], {}) if selected_ids else {}
    visible_templates = {str(item.get("template_id") or "") for item in first_snapshot.get("templates", [])}
    missing_templates = sorted(set(selected_ids) - visible_templates)
    if missing_templates:
        failures.append(f"static selector missing profiles: {', '.join(missing_templates)}")

    for template_id in selected_ids:
        snapshot = snapshots.get(template_id) or {}
        profile = _profile_status(status, template_id)
        inventory_profile = _inventory_profile(inventory, template_id)
        template_data = _load_template_json(template_id)
        result_failures = _compare_one_profile(
            template_id,
            snapshot,
            profile=profile,
            inventory_profile=inventory_profile,
            template_data=template_data,
            local_authority=local_authority.get(template_id),
            materialization_required=materialization_required,
        )
        failures.extend(result_failures)
        profile_results.append(
            {
                "template_id": template_id,
                "ready": _is_ready_profile(profile),
                "passed": not result_failures,
                "failures": result_failures,
                "static_counts": {
                    "segment3_total_count": snapshot.get("trial_file_bake", {}).get("total_count", 0),
                    "segment4_total_count": snapshot.get("trial_pool_bake", {}).get("total_count", 0),
                    "segment5_block_count": snapshot.get("block_csv_preview", {}).get("block_count", 0),
                },
            }
        )
    return {"failures": failures, "profile_results": profile_results}


def _compare_one_profile(
    template_id: str,
    snapshot: dict[str, Any],
    *,
    profile: dict[str, Any],
    inventory_profile: dict[str, Any],
    template_data: dict[str, Any],
    local_authority: dict[str, Any] | None,
    materialization_required: bool,
) -> list[str]:
    failures: list[str] = []
    prefix = f"{template_id}: "
    if snapshot.get("selected_template") != template_id:
        failures.append(prefix + f"selected template mismatch: {snapshot.get('selected_template')}")
    if not snapshot.get("static_mode"):
        failures.append(prefix + "snapshot is not in static mode")
    if snapshot.get("controls", {}).get("edit-mode-button", {}).get("disabled") is not False:
        failures.append(prefix + "Edit mode button must remain available for browser-local copy-on-edit")
    enabled = sorted(
        set(snapshot.get("disabled_summary", {}).get("mutating_enabled", []))
        & COMPANION_REQUIRED_CONTROL_IDS
    )
    if enabled:
        failures.append(prefix + f"companion-required controls enabled without companion: {', '.join(enabled)}")

    expected_labels = _expected_source_labels(template_data, inventory_profile)
    actual_labels = [str(item.get("label") or "") for item in snapshot.get("sources", [])]
    if actual_labels != expected_labels:
        failures.append(prefix + f"source labels mismatch: expected {expected_labels}, got {actual_labels}")

    expected_assets = {str(asset.get("label") or "") for asset in inventory_profile.get("assets", [])}
    actual_asset_labels = {
        str(item.get("label") or "")
        for item in snapshot.get("sources", [])
        if str(item.get("path") or "").strip()
    }
    if expected_assets and not expected_assets.issubset(actual_asset_labels):
        failures.append(prefix + f"static source assets missing labels: {sorted(expected_assets - actual_asset_labels)}")

    ready = _is_ready_profile(profile)
    segments = snapshot.get("segments", {})
    if ready:
        for folder in (
            "0_profile",
            "1_core_audio_ingredients",
            "2_trial_sequence_designs",
            "3_tactile_and_baseline_trials",
            "4_trial_repetition_pool",
            "5_block_csv_preview",
            "6_experiment_run_setup",
        ):
            if segments.get(folder, {}).get("status") != "ready":
                failures.append(prefix + f"{folder} static status is not ready")
        if snapshot.get("block_csv_preview", {}).get("accepted") is not True:
            failures.append(prefix + "Segment 5 static block preview is not accepted")
        if snapshot.get("run_sequence_setup", {}).get("prepared") is not True:
            failures.append(prefix + "Segment 6 static run setup is not prepared/read-only launchable")
        if materialization_required:
            if not local_authority or local_authority.get("status") != "prepared":
                failures.append(prefix + f"local materialization did not prepare: {local_authority}")
            else:
                _compare_count(
                    failures,
                    prefix,
                    "Segment 3 total",
                    snapshot.get("trial_file_bake", {}).get("total_count", 0),
                    local_authority.get("segment3_total_count", 0),
                )
                _compare_count(
                    failures,
                    prefix,
                    "Segment 4 total",
                    snapshot.get("trial_pool_bake", {}).get("total_count", 0),
                    local_authority.get("segment4_total_count", 0),
                )
                _compare_count(
                    failures,
                    prefix,
                    "Segment 5 block count",
                    snapshot.get("block_csv_preview", {}).get("block_count", 0),
                    local_authority.get("segment5_block_count", 0),
                )
    else:
        if snapshot.get("profile", {}).get("preload_inventory", {}).get("finished_profile") is True:
            failures.append(prefix + "blocked profile appears finished in static mode")
        if segments.get("6_experiment_run_setup", {}).get("status") == "ready":
            failures.append(prefix + "blocked profile has ready Segment 6 static status")
        if snapshot.get("run_sequence_setup", {}).get("prepared") is True:
            failures.append(prefix + "blocked profile appears prepared in static mode")
        if not (snapshot.get("profile", {}).get("custom_missing") or _profile_blockers(profile)):
            failures.append(prefix + "blocked profile lacks visible or ledger blocker reasons")
    return failures


def _compare_count(failures: list[str], prefix: str, label: str, actual: Any, expected: Any) -> None:
    if int(actual or 0) != int(expected or 0):
        failures.append(prefix + f"{label} mismatch: static {actual}, local {expected}")


def _load_preload_inventory() -> dict[str, Any]:
    return json.loads(
        (RESOURCE_ROOT / "assets" / "preloads" / "preload_inventory.json").read_text(
            encoding="utf-8"
        )
    )


def _load_template_json(template_id: str) -> dict[str, Any]:
    return json.loads(
        (RESOURCE_ROOT / "study_templates" / f"{template_id}.json").read_text(
            encoding="utf-8"
        )
    )


def _target_template_ids(inventory: dict[str, Any], status: dict[str, Any], *, profile_set: str) -> list[str]:
    ids = [str(profile.get("template_id") or "") for profile in inventory.get("profiles", []) if profile.get("template_id")]
    if profile_set == "ready-all":
        return [template_id for template_id in ids if _is_ready_profile(_profile_status(status, template_id))]
    return ids


def _profile_status(status: dict[str, Any], template_id: str) -> dict[str, Any]:
    for profile in status.get("profiles", []):
        if str(profile.get("template_id") or "") == template_id:
            return profile
    return {}


def _inventory_profile(inventory: dict[str, Any], template_id: str) -> dict[str, Any]:
    for profile in inventory.get("profiles", []):
        if str(profile.get("template_id") or "") == template_id:
            return profile
    return {}


def _is_ready_profile(profile: dict[str, Any]) -> bool:
    return (
        profile.get("runner_readiness") == READY_RUNNER
        and bool(profile.get("profile_checks_passed"))
        and bool(profile.get("segment_0_to_4_profile_checks_passed"))
        and bool(profile.get("segment_6_launchable"))
    )


def _profile_blockers(profile: dict[str, Any]) -> list[str]:
    blockers = []
    for key in ("missing_publication_parameters", "unsupported_toolkit_structures", "readiness_blockers"):
        value = profile.get(key)
        if isinstance(value, list):
            blockers.extend(str(item) for item in value if item)
    return blockers


def _expected_source_labels(template_data: dict[str, Any], inventory_profile: dict[str, Any]) -> list[str]:
    design = template_data.get("design") or {}
    labels = []
    consumed_asset_keys = set()
    asset_labels_by_key = {
        _source_key(str(asset.get("label") or "")): str(asset.get("label") or "")
        for asset in inventory_profile.get("assets", [])
        if str(asset.get("label") or "")
    }
    for item in design.get("noises") or []:
        if item.get("label"):
            label = str(item["label"])
            labels.append(label)
            if _source_key(label) in asset_labels_by_key:
                consumed_asset_keys.add(_source_key(label))
    for item in design.get("custom_looming_files") or []:
        if item.get("label"):
            label = str(item["label"])
            labels.append(label)
            if _source_key(label) in asset_labels_by_key:
                consumed_asset_keys.add(_source_key(label))
    for key, label in asset_labels_by_key.items():
        if key not in consumed_asset_keys:
            labels.append(label)
    for item in design.get("prestimulus_files") or []:
        if item.get("label"):
            labels.append(str(item["label"]))
    return list(dict.fromkeys(labels))


def _source_key(label: str) -> str:
    return " ".join(str(label or "").strip().lower().split())


def _free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


class QuietStaticHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: Any) -> None:
        return


class StaticServer:
    def __init__(self, *, host: str, port: int) -> None:
        actual_port = int(port or _free_port(host))
        handler = functools.partial(QuietStaticHandler, directory=str(REPO_ROOT))
        self.server = http.server.ThreadingHTTPServer((host, actual_port), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, name="pps-static-dashboard-audit", daemon=True)
        self.url = f"http://{host}:{actual_port}/"

    def start(self) -> "StaticServer":
        self.thread.start()
        return self

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5.0)


def _start_static_server(*, host: str, port: int) -> StaticServer:
    return StaticServer(host=host, port=port).start()


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_ready(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Static Dashboard Preview Parity Audit",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Profiles: `{report.get('profile_count')}`",
        f"- Ready profiles: `{report.get('ready_profile_count')}`",
        f"- Materialization checked: `{report.get('materialization_checked')}`",
    ]
    for dashboard in report.get("dashboard_reports", []):
        lines.extend(
            [
                "",
                f"## {dashboard.get('dashboard_url')}",
                "",
                f"- Passed: `{dashboard.get('passed')}`",
                f"- Profiles checked: `{dashboard.get('profile_count')}`",
            ]
        )
        if dashboard.get("failures"):
            lines.append("")
            lines.append("### Failures")
            lines.extend(f"- {failure}" for failure in dashboard.get("failures", []))
    if report.get("failures"):
        lines.extend(["", "## All Failures"])
        lines.extend(f"- {failure}" for failure in report["failures"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
