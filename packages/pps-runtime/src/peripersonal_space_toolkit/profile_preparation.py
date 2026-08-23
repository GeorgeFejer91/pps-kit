"""Public profile-to-Runner preparation boundary shared by applets."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from .design import StimulusDesign
from .designer_segments.registry import manifest_sha256
from .preload_inventory import load_preload_inventory
from .profile_memory import active_output_folder, resolve_profile_entry
from .runtime_paths import repo_root
from .session_runner import (
    DEFAULT_DASHBOARD_STATE_ROOT,
    DEFAULT_PROJECT_REGISTRY_ROOT,
    DEFAULT_RENDER_DIR,
    DEFAULT_SESSION_ROOT,
)


ProgressCallback = Callable[[dict[str, Any]], None]
DEFAULT_PREPARATION_DESIGN_PATH = DEFAULT_DASHBOARD_STATE_ROOT / "focus_profile_runner_design.json"


@dataclass(frozen=True)
class PreparedProfile:
    """Validated Segment 6 handoff consumed by participant-session preparation."""

    profile_id: str
    profile_kind: str
    design: StimulusDesign
    design_path: Path
    project_dir: Path
    run_setup_manifest_path: Path
    run_setup_manifest_sha256: str
    materialization_status: str
    controller: Any = field(default=None, repr=False, compare=False)


def load_prepared_design(path: Path) -> StimulusDesign:
    """Load a stored Designer document without importing its private helpers."""
    from .dashboard_app import load_dashboard_design

    return load_dashboard_design(Path(path))


def prepare_profile_for_runner(
    profile_id: str,
    *,
    progress_callback: ProgressCallback | None = None,
    design_path: Path = DEFAULT_PREPARATION_DESIGN_PATH,
    render_dir: Path = DEFAULT_RENDER_DIR,
    session_root: Path | None = None,
    registry_root: Path = DEFAULT_PROJECT_REGISTRY_ROOT,
    state_root: Path = DEFAULT_DASHBOARD_STATE_ROOT,
) -> PreparedProfile:
    """Resolve and validate a finalized profile through the ordered segment chain."""

    from .dashboard_app import DEFAULT_IMPORT_DIR, DEFAULT_PREVIEW_DIR, DashboardController

    profile = str(profile_id or "").strip()
    if not profile:
        raise ValueError("Choose a study/profile preset before preparing the Runner.")
    output_root = Path(session_root) if session_root is not None else active_output_folder(
        state_root=state_root,
        fallback=DEFAULT_SESSION_ROOT,
    )
    inventory = load_preload_inventory(repo_root())
    entry = resolve_profile_entry(
        profile,
        registry_root=registry_root,
        state_root=state_root,
        session_root=output_root,
        inventory=inventory,
    )
    profile_kind = str(entry.get("kind") or "bundled")

    if profile_kind == "custom":
        return _prepare_custom_profile(
            profile,
            entry=entry,
            output_root=output_root,
            render_dir=render_dir,
            registry_root=registry_root,
            state_root=state_root,
            controller_class=DashboardController,
        )

    controller = DashboardController(
        design_path=Path(design_path),
        render_dir=Path(render_dir),
        session_root=output_root,
        import_dir=DEFAULT_IMPORT_DIR,
        preview_dir=DEFAULT_PREVIEW_DIR,
        project_registry_root=Path(registry_root),
        state_root=Path(state_root),
    )
    inventory_profiles = controller.preload_inventory_payload().get("profiles", [])
    status = next((item for item in inventory_profiles if item.get("template_id") == profile), None)
    if status is None:
        raise ValueError(f"Unknown study/profile preset: {profile}")
    if not (status.get("finished_profile") and status.get("segment_6_launchable")):
        reason = str(status.get("profile_completion_status") or status.get("runner_readiness") or "unfinished_preload")
        raise ValueError(
            f"Study/profile preset '{profile}' is not a finished Segment 6 launchable profile yet ({reason})."
        )

    controller.load_template(profile, snapshot=False)
    materialization = controller.ensure_profile_run_artifacts(progress_callback=progress_callback)
    project = controller.active_project_context()
    design = controller.design_copy()
    manifest_path = controller.active_run_setup_manifest_path()
    if not manifest_path.is_file():
        raise RuntimeError(f"Study/profile preset '{profile}' did not produce a Segment 6 run setup.")
    return PreparedProfile(
        profile_id=profile,
        profile_kind=profile_kind,
        design=design,
        design_path=Path(controller.design_path),
        project_dir=Path(project.project_dir),
        run_setup_manifest_path=manifest_path,
        run_setup_manifest_sha256=manifest_sha256(manifest_path),
        materialization_status=str(materialization.get("status") or "already_ready"),
        controller=controller,
    )


def _prepare_custom_profile(
    profile_id: str,
    *,
    entry: dict[str, Any],
    output_root: Path,
    render_dir: Path,
    registry_root: Path,
    state_root: Path,
    controller_class: Any,
) -> PreparedProfile:
    run_setup_manifest_path = Path(str(entry.get("run_setup_manifest_path") or ""))
    if not bool(entry.get("profile_ready", entry.get("segment_6_ready"))):
        reasons = entry.get("missing_or_stale_asset_reasons") or ["The profile is not ready for Runner materialization."]
        raise ValueError(f"Local study profile '{profile_id}' cannot be launched: {str(reasons[0])}")
    project_dir = Path(str(entry.get("project_dir") or ""))
    design_path = project_dir / "0_profile" / "active_design.json"
    if not design_path.is_file():
        raise FileNotFoundError(f"Stored profile design is missing: {design_path}")

    controller: Any
    materialization_status = "already_ready"
    if not run_setup_manifest_path.is_file() or bool(entry.get("runner_materialization_required")):
        controller = controller_class(
            design_path=design_path,
            render_dir=Path(render_dir),
            session_root=output_root,
            project_registry_root=Path(registry_root),
            state_root=Path(state_root),
        )
        result = controller.prepare_experiment_run_setup()
        run_setup_manifest_path = Path(str(result.get("run_sequence_prepare_result", {}).get("manifest_path") or ""))
        materialization_status = "materialized"
        if not run_setup_manifest_path.is_file():
            raise RuntimeError(f"Runner could not materialize an order manifest for '{profile_id}'.")
        design = controller.design_copy()
    else:
        controller = SimpleNamespace(design_path=design_path)
        design = load_prepared_design(design_path)

    return PreparedProfile(
        profile_id=profile_id,
        profile_kind="custom",
        design=design,
        design_path=design_path,
        project_dir=project_dir,
        run_setup_manifest_path=run_setup_manifest_path,
        run_setup_manifest_sha256=manifest_sha256(run_setup_manifest_path),
        materialization_status=materialization_status,
        controller=controller,
    )
