"""Local browser dashboard for researcher-facing PPS control."""

from __future__ import annotations

import argparse
import base64
import binascii
import csv
import hashlib
import itertools
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
import webbrowser
from dataclasses import asdict, dataclass, field
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import Any, Callable

from . import render_backend
from .design import (
    AudioFileSpec,
    BlockSpec,
    CUSTOM_AUDIO_NOISE_TYPE,
    NoiseDefinition,
    SUPPORTED_BASELINE_STRATEGIES,
    SUPPORTED_NOISE_TYPES,
    StimulusDesign,
    azimuth_to_display_rotation_deg,
    audio_file_summary,
    block_trial_rows,
    cartesian_to_spherical,
    default_design,
    design_from_dict,
    design_to_dict,
    expand_trial_strip_source_labels,
    has_trial_strips,
    load_design,
    participant_block_orders,
    point_from_distance_rotation_height,
    protocol_summary,
    protocol_sound_sources,
    save_design,
    trajectory_endpoints_xyz,
    validate_design,
)
from .session_runner import (
    DEFAULT_DASHBOARD_STATE_ROOT,
    DEFAULT_RENDER_DIR,
    DEFAULT_SESSION_ROOT,
    RunPackage,
    claim_prepared_session,
    load_run_package,
    prepare_segment_run_package,
    available_stimulus_wavs,
    prepare_run_package,
    preflight_run_package,
    record_experiment_activity,
    rendered_wavs,
)
from .focus_launch import build_focus_runner_command
from .loudness import (
    LOUDNESS_POLICY_KEY,
    db_to_linear,
    loudness_policy_for_design,
    normalize_loudness_policy,
)
from .output_layout import output_profile_snapshot_dir
from .profile_memory import (
    append_output_diary_event,
    active_output_folder,
    bridge_manifest_path as acquisition_bridge_manifest_path,
    build_profile_catalog,
    copy_project_tree,
    generate_custom_profile_id,
    load_runner_settings as load_profile_runner_settings,
    prepare_acquisition_folder,
    rebase_project_copy_paths,
    refresh_project_dependency_hashes,
    update_runner_settings as update_profile_runner_settings,
)
from .templates import (
    DEFAULT_STUDY_TEMPLATE_ID,
    StudyTemplate,
    load_templates,
    study_template_bibtex,
    study_template_citation_label,
    study_template_csl_json,
)
from .preload_inventory import ensure_preload_assets, load_preload_inventory, preload_inventory_payload, profile_asset_status
from .runtime_paths import repo_root, writable_root
from .subprocess_utils import windows_no_console_kwargs
from .dashboard_backend.security import CompanionSecurity, TOKEN_HEADER
from .runner_diary import (
    append_diary_entry,
    find_output_diary,
    load_runner_settings as load_diary_runner_settings,
    resolve_or_create_output_project,
    runner_settings_path as diary_runner_settings_path,
    update_runner_settings as update_diary_runner_settings,
)


REPO_ROOT = repo_root()
WRITABLE_ROOT = writable_root()
DEFAULT_DESIGN_PATH = WRITABLE_ROOT / "configs" / "stimulus_design.generated.json"
TEMPLATE_DIR = REPO_ROOT / "study_templates"
DEFAULT_IMPORT_DIR = WRITABLE_ROOT / "local_data" / "dashboard_audio"
DEFAULT_PREVIEW_DIR = WRITABLE_ROOT / "local_data" / "dashboard_previews"
DEFAULT_PROJECT_REGISTRY_ROOT = WRITABLE_ROOT / "local_data" / "dashboard_projects" / "0_study_project_registry"
TRIAL_PREVIEW_LIMIT = 240
CUSTOM_TEMPLATE_IDS = {"custom", "__custom__"}
DEFAULT_WEB_ORIGINS = ("https://georgefejer91.github.io", "https://ppskit.qzz.io")
DEFAULT_TACTILE_CUE_PATH = REPO_ROOT / "assets" / "tactile" / "default_tactile_cue.wav"
PROJECT_MANIFEST_SCHEMA = "pps-dashboard-project.v1"
STUDY_SETTINGS_MANIFEST_SCHEMA = "pps-dashboard-study-settings-manifest.v1"
INGREDIENT_MANIFEST_SCHEMA = "pps-core-audio-ingredients.v1"
TRIAL_REPETITION_POOL_MANIFEST_SCHEMA = "pps-trial-repetition-pool.v1"
BLOCK_CSV_PREVIEW_MANIFEST_SCHEMA = "pps-block-csv-preview.v1"
RUN_SETUP_MANIFEST_SCHEMA = "pps-experiment-run-setup.v1"
DATA_ACQUISITION_BRIDGE_SCHEMA = "pps-dashboard-runner-bridge.v1"
DASHBOARD_DESIGN_EXPORT_DIRNAME = "dashboard_design_export"
PROJECT_METADATA_KEY = "dashboard_project"
RUN_SETUP_METADATA_KEY = "dashboard_run_setup"
CUSTOM_PROJECT_ID_SLUG_MAX_LENGTH = 21
TRIAL_POOL_FAMILIES = ("audio_tactile", "baseline", "catch")
EXPERIMENT_STRUCTURES = ("single", "pre_post")
RUN_INSTRUCTION_PROFILE_SCHEMA = "pps-run-instructions.v1"
RUN_INSTRUCTION_SLOTS = (
    "before_experiment",
    "before_each_block",
    "after_each_block",
    "between_conditions",
    "after_experiment",
)
RUN_INSTRUCTION_SLOT_LABELS = {
    "before_experiment": "Before experiment",
    "before_each_block": "Before each block",
    "after_each_block": "After each block",
    "between_conditions": "Between conditions",
    "after_experiment": "After experiment",
}
RUN_INSTRUCTION_CONTINUE_MODES = ("click", "delay", "button")
STUDY5_RUN_INSTRUCTION_ASSETS = {
    "before_experiment": {
        "label": "General instructions",
        "path": "assets/breathing/original_study5/General_Instructions.wav",
        "continue_mode": "click",
        "button_label": "Start experiment",
    },
    "before_each_block": {
        "label": "Pre-block instruction",
        "path": "assets/breathing/original_study5/Pre-Block_Instruction.wav",
        "continue_mode": "delay",
        "delay_s": 0.0,
        "button_label": "Start block",
    },
    "after_each_block": {
        "label": "Post-block instruction",
        "path": "assets/breathing/original_study5/Post-Block_Instruction.wav",
        "continue_mode": "click",
        "button_label": "Next block",
    },
    "between_conditions": {
        "label": "Condition transition",
        "path": "assets/breathing/original_study5/InterimMessage.wav",
        "continue_mode": "button",
        "button_label": "Start next condition",
    },
    "after_experiment": {
        "label": "Finish message",
        "path": "assets/breathing/original_study5/FinishMessage.wav",
        "continue_mode": "delay",
        "delay_s": 0.0,
        "button_label": "Finish",
    },
}
TRIAL_FAMILY_COLORS = {
    "audio_tactile": "#246b55",
    "baseline": "#4b5fa8",
    "catch": "#a4631b",
}
STUDY5_TRIAL_POOL_REPETITION_DEFAULTS = {
    "default": 3.0,
    "audio_tactile": 3.0,
    "baseline": 1.5,
    "catch": 3.0,
}
STUDY5_ORIGINAL_INSTRUCTION_ASSETS = {
    "Inhale instruction": {
        "phase": "Inhale",
        "path": "assets/breathing/original_study5/Inhale-2-3-4-hold_FIXED.wav",
        "legacy_path": "assets/breathing/british_kokoro/Inhale-2-3-4-hold_FIXED.wav",
    },
    "Exhale instruction": {
        "phase": "Exhale",
        "path": "assets/breathing/original_study5/Exhale-2-3-4-hold_FIXED.wav",
        "legacy_path": "assets/breathing/british_kokoro/Exhale-2-3-4-hold_FIXED.wav",
    },
}
STIMULUS_TRAJECTORY_COLORS = {
    "pink": "#d783b5",
    "blue": "#4b7fc4",
    "white": "#d8dde2",
    "brown": "#8b623f",
    "violet": "#8364b9",
    CUSTOM_AUDIO_NOISE_TYPE: "#246b55",
    "preserve": "#246b55",
    "spatialize": "#246b55",
}


@dataclass
class DashboardJob:
    job_id: str
    kind: str
    status: str = "queued"
    message: str = ""
    result: dict[str, Any] | None = None
    error: str = ""
    progress_current: int = 0
    progress_total: int = 0
    progress_percent: float = 0.0
    progress_label: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class DashboardProjectContext:
    project_id: str
    project_kind: str
    project_label: str
    source_template_id: str
    created_at: str
    registry_root: Path
    project_dir: Path
    profile_dir: Path
    segment1_dir: Path
    segment2_dir: Path
    segment3_dir: Path
    segment4_dir: Path
    segment5_dir: Path
    segment6_dir: Path
    shared_tactile_path: Path
    source_profile_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PROJECT_MANIFEST_SCHEMA,
            "project_id": self.project_id,
            "project_kind": self.project_kind,
            "project_label": self.project_label,
            "source_template_id": self.source_template_id,
            "source_profile_id": self.source_profile_id,
            "created_at": self.created_at,
            "registry_root": str(self.registry_root),
            "project_dir": str(self.project_dir),
            "profile_dir": str(self.profile_dir),
            "segment_folders": {
                "0_profile": str(self.profile_dir),
                "1_core_audio_ingredients": str(self.segment1_dir),
                "2_trial_sequence_designs": str(self.segment2_dir),
                "3_tactile_and_baseline_trials": str(self.segment3_dir),
                "4_trial_repetition_pool": str(self.segment4_dir),
                "5_block_csv_preview": str(self.segment5_dir),
                "6_experiment_run_setup": str(self.segment6_dir),
            },
            "shared_tactile_path": str(self.shared_tactile_path),
        }


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, DashboardJob] = {}
        self._lock = threading.Lock()

    def start(self, kind: str, func: Callable[..., dict[str, Any]], *, progress: bool = False) -> DashboardJob:
        job = DashboardJob(job_id=uuid.uuid4().hex[:12], kind=kind)
        with self._lock:
            self._jobs[job.job_id] = job

        def _progress(current: int, total: int, label: str = "") -> None:
            total = max(0, int(total or 0))
            current = max(0, min(int(current or 0), total if total else int(current or 0)))
            percent = round((current / total) * 100.0, 1) if total else 0.0
            self._update(
                job.job_id,
                progress_current=current,
                progress_total=total,
                progress_percent=percent,
                progress_label=label,
                message=label or f"{kind} running",
            )

        def _run() -> None:
            self._update(job.job_id, status="running", message=f"{kind} started")
            try:
                result = func(_progress) if progress else func()
            except Exception as exc:
                self._update(job.job_id, status="failed", error=str(exc), message=f"{kind} failed")
            else:
                total = int(job.progress_total or 0)
                if total:
                    self._update(
                        job.job_id,
                        progress_current=total,
                        progress_percent=100.0,
                        progress_label=f"{kind} complete",
                    )
                self._update(job.job_id, status="succeeded", result=_json_ready(result), message=f"{kind} complete")

        threading.Thread(target=_run, daemon=True).start()
        return job

    def get(self, job_id: str) -> DashboardJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def recent(self, limit: int = 12) -> list[DashboardJob]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)[:limit]

    def _update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            for key, value in changes.items():
                setattr(job, key, value)
            job.updated_at = time.time()


class DashboardController:
    def __init__(
        self,
        *,
        design_path: Path = DEFAULT_DESIGN_PATH,
        render_dir: Path = DEFAULT_RENDER_DIR,
        session_root: Path = DEFAULT_SESSION_ROOT,
        template_dir: Path = TEMPLATE_DIR,
        import_dir: Path = DEFAULT_IMPORT_DIR,
        preview_dir: Path = DEFAULT_PREVIEW_DIR,
        project_registry_root: Path = DEFAULT_PROJECT_REGISTRY_ROOT,
        state_root: Path = DEFAULT_DASHBOARD_STATE_ROOT,
    ) -> None:
        self.design_path = Path(design_path)
        self.render_dir = Path(render_dir)
        self.session_root = Path(session_root)
        self.template_dir = Path(template_dir)
        self.import_dir = Path(import_dir)
        self.preview_dir = Path(preview_dir)
        self.project_registry_root = Path(project_registry_root)
        if Path(state_root) == DEFAULT_DASHBOARD_STATE_ROOT and Path(project_registry_root) != DEFAULT_PROJECT_REGISTRY_ROOT:
            self.state_root = Path(project_registry_root).parent / "dashboard_state"
        else:
            self.state_root = Path(state_root)
        remembered = load_diary_runner_settings(self.state_root)
        remembered_root = str(remembered.get("current_output_project_root") or remembered.get("session_root") or "").strip()
        if remembered_root:
            remembered_path = Path(remembered_root).expanduser()
            remembered_diary = str(remembered.get("diary_path") or "").strip()
            if remembered_path.is_dir() and (not remembered_diary or Path(remembered_diary).expanduser().is_file() or find_output_diary(remembered_path)):
                self.session_root = remembered_path
        self.templates = load_templates(self.template_dir)
        self.preload_inventory = load_preload_inventory(REPO_ROOT)
        self.design = self._load_initial_design()
        project = self._ensure_project_context(self.design)
        if self.design.study_profile_id == DEFAULT_STUDY_TEMPLATE_ID:
            _materialize_study_profile_segment1_ingredients(project, self.design)
            _write_project_context_files(project, self.design)
            save_design(self.design, self.design_path)
        self.participant_id = "P001"
        self.current_run_package: RunPackage | None = None
        self.jobs = JobManager()
        self._lock = threading.Lock()

    def _load_initial_design(self) -> StimulusDesign:
        if self.design_path.exists():
            try:
                design = load_design(self.design_path)
                if not _should_replace_saved_design_with_default_profile(design):
                    return _normalize_dashboard_design(design)
            except Exception:
                pass
        return self._default_profile_design()

    def _default_profile_design(self) -> StimulusDesign:
        template = next((item for item in self.templates if item.template_id == DEFAULT_STUDY_TEMPLATE_ID), None)
        if template is None:
            return default_design()
        return _normalize_dashboard_design(template.design)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            project = self._ensure_project_context(self.design)
            design = _copy_design(self.design)
            participant_id = self.participant_id
            package = self.current_run_package
        artifact_root = self._lookup_root_for_design(design, project)
        preflight = _preflight_to_dict(
            preflight_run_package(design, participant_id, render_dir=artifact_root, require_audio=False)
        )
        runner_settings = load_profile_runner_settings(state_root=self.state_root, default_output_folder=self.session_root)
        profile_catalog = build_profile_catalog(
            registry_root=self.project_registry_root,
            state_root=self.state_root,
            session_root=Path(runner_settings["active_output_folder"]),
            inventory=self.preload_inventory,
        )
        return {
            "design": design_to_dict(design),
            "design_path": str(self.design_path),
            "project": project.to_dict(),
            "custom_projects": self.custom_projects_payload(),
            "profile_catalog": profile_catalog,
            "runner_settings": runner_settings,
            "participant_id": participant_id,
            "templates": self.templates_payload(),
            "selected_template": design.study_profile_id,
            "custom_workflow": _custom_workflow_status(design, participant_id, project.project_dir),
            "trajectory_controls": _trajectory_controls(design),
            "viewer_payload": trajectory_viewer_payload(design),
            "protocol_summary": protocol_summary(design),
            "trial_preview": _trial_preview_rows(design, artifact_root),
            "participant_orders": _participant_orders(design),
            "validation": validate_design(design),
            "render": _render_status(artifact_root, design),
            "project_segments": _project_segments_status(project, design),
            "trial_sequence_bake": _trial_sequence_bake_status(project.project_dir),
            "trial_file_bake": _trial_file_bake_status(artifact_root),
            "trial_pool_bake": _trial_pool_bake_status(project.project_dir, design),
            "block_csv_preview": _block_csv_preview_status(project.project_dir, design),
            "run_sequence_setup": _run_setup_preview(project.project_dir, design),
            "data_acquisition": self._data_acquisition_context(),
            "preload_inventory": profile_asset_status(
                design.study_profile_id,
                inventory=self.preload_inventory,
                repo_root=REPO_ROOT,
            ),
            "preflight": preflight,
            "session": _package_to_dict(package),
            "jobs": [_job_to_dict(job) for job in self.jobs.recent()],
        }

    def _ensure_project_context(self, design: StimulusDesign, *, force_new_custom: bool = False) -> DashboardProjectContext:
        context = _ensure_dashboard_project_context(
            design,
            self.project_registry_root,
            force_new_custom=force_new_custom,
        )
        _write_project_context_files(context, design)
        return context

    def _lookup_root_for_design(self, design: StimulusDesign, project: DashboardProjectContext | None = None) -> Path:
        context = project or _project_context_from_design(design, self.project_registry_root)
        if context and _project_has_generated_outputs(context.project_dir):
            return context.project_dir
        if context and available_stimulus_wavs(design, context.project_dir):
            return context.project_dir
        return self.render_dir

    def templates_payload(self) -> list[dict[str, Any]]:
        return [
            _template_to_dict(
                template,
                asset_status=profile_asset_status(
                    template.template_id,
                    inventory=self.preload_inventory,
                    repo_root=REPO_ROOT,
                ),
            )
            for template in self.templates
        ]

    def preload_inventory_payload(self) -> dict[str, Any]:
        return preload_inventory_payload(
            [template.template_id for template in self.templates],
            repo_root=REPO_ROOT,
        )

    def _data_acquisition_context(self) -> dict[str, Any]:
        settings = load_diary_runner_settings(self.state_root)
        root_text = str(settings.get("current_output_project_root") or settings.get("session_root") or "").strip()
        root = Path(root_text).expanduser() if root_text else None
        diary_text = str(settings.get("diary_path") or "").strip()
        diary = Path(diary_text).expanduser() if diary_text else None
        if (diary is None or not diary.is_file()) and root is not None:
            diary = find_output_diary(root)
        active = bool(root and root.is_dir() and diary and diary.is_file())
        return {
            "active": active,
            "root": "" if root is None else str(root),
            "diary_path": "" if diary is None else str(diary),
            "runner_settings_path": str(diary_runner_settings_path(self.state_root)),
            "last_experiment_name": str(settings.get("last_experiment_name") or ""),
            "last_profile_id": str(settings.get("last_profile_id") or ""),
            "last_participant_id": str(settings.get("last_participant_id") or ""),
            "updated_at": str(settings.get("updated_at") or ""),
        }

    def _append_dashboard_diary_event(
        self,
        event_type: str,
        *,
        design: StimulusDesign | None = None,
        project: DashboardProjectContext | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Path | None:
        context = self._data_acquisition_context()
        diary_text = str(context.get("diary_path") or "").strip()
        if not diary_text:
            return None
        active_design = design or self.design
        active_project = project or _project_context_from_design(active_design, self.project_registry_root)
        experiment_name = _experiment_identifier_for_diary(active_design, active_project)
        try:
            return append_diary_entry(
                Path(diary_text),
                event_type,
                participant_id=self.participant_id,
                experiment_name=experiment_name,
                profile_id=str(active_design.study_profile_id or ""),
                capture_options={},
                payload={
                    "project_dir": "" if active_project is None else str(active_project.project_dir),
                    "design_path": str(self.design_path),
                    **(payload or {}),
                },
            )
        except Exception:
            return None

    def profile_catalog_payload(self) -> dict[str, Any]:
        settings = load_profile_runner_settings(state_root=self.state_root, default_output_folder=self.session_root)
        return build_profile_catalog(
            registry_root=self.project_registry_root,
            state_root=self.state_root,
            session_root=Path(settings["active_output_folder"]),
            inventory=self.preload_inventory,
        )

    def custom_projects_payload(self) -> list[dict[str, Any]]:
        return _custom_project_records(self.project_registry_root)

    def sync_preload_assets(self, template_id: str) -> dict[str, Any]:
        return ensure_preload_assets(
            template_id,
            inventory=self.preload_inventory,
            repo_root=REPO_ROOT,
        )

    def load_template(self, template_id: str, *, snapshot: bool = True) -> dict[str, Any]:
        if template_id in CUSTOM_TEMPLATE_IDS:
            return self.load_custom_design()
        template = next((item for item in self.templates if item.template_id == template_id), None)
        if template is None:
            raise KeyError(template_id)
        self.sync_preload_assets(template_id)
        with self._lock:
            self.design = _normalize_dashboard_design(template.design)
            project = self._ensure_project_context(self.design)
            if self.design.study_profile_id:
                _materialize_study_profile_segment1_ingredients(project, self.design)
                _write_project_context_files(project, self.design)
                save_design(self.design, self.design_path)
            self.current_run_package = None
            self._append_dashboard_diary_event(
                "dashboard_profile_loaded",
                project=project,
                payload={"template_id": template_id},
            )
            participant_id = self.participant_id
        update_profile_runner_settings(
            state_root=self.state_root,
            output_folder=self.session_root,
            profile_id=template_id,
            profile_kind="bundled",
            dashboard_project_id=project.project_id,
            participant_id=participant_id,
        )
        append_output_diary_event(
            "profile_selected",
            state_root=self.state_root,
            profile_id=template_id,
            profile_kind="bundled",
            dashboard_project_id=project.project_id,
            participant_id=participant_id,
        )
        return self.snapshot() if snapshot else {"selected_template": template_id}

    def load_custom_design(self) -> dict[str, Any]:
        design = default_design()
        design.name = "Custom PPS design"
        design.study_profile_id = ""
        design.study_profile_title = ""
        design.study_profile_notes = ""
        design.study_profile_reference_parameters = {"dashboard_mode": "custom"}
        design.noises = []
        design.custom_looming_files = []
        design.prestimulus_files = []
        design.protocol.soa_values_ms = []
        design.protocol.spatial_values_cm = []
        design.protocol.trial_strips = []
        design.protocol.include_catch_trials = False
        design.protocol.catch_trial_percentage = 0.0
        design.protocol.include_baseline_trials = False
        design.protocol.baseline_strategy = ""
        design.protocol.baseline_trial_percentage = 0.0
        design.protocol.baseline_custom_trial_mode = "tactile_only"
        design.protocol.blocks = 1
        design.protocol.participants = 1
        design = _normalize_dashboard_design(design)
        with self._lock:
            self.design = design
            project = self._ensure_project_context(self.design)
            _write_segment_validation_report(project, self.design)
            self.participant_id = ""
            self.current_run_package = None
            self._append_dashboard_diary_event(
                "dashboard_custom_design_started",
                project=project,
                payload={"project_dir": str(project.project_dir)},
            )
        return self.snapshot()

    def customize_as_new_project(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        project_name = str(payload.get("name") or "").strip()
        if not project_name:
            raise ValueError("Enter a study name before creating a custom study.")
        with self._lock:
            source_design = _copy_design(self.design)
            design = _custom_project_design_from_source(
                source_design,
                project_name=project_name,
            )
            self.design = design
            project = self._ensure_project_context(self.design, force_new_custom=True)
            _materialize_segment1_ingredients_for_custom_project(
                project,
                self.design,
                source_design=source_design,
            )
            _clear_downstream_segment_outputs(project, from_segment=1)
            _write_project_context_files(project, self.design)
            _write_segment_validation_report(project, self.design)
            self.participant_id = ""
            self.current_run_package = None
            save_design(self.design, self.design_path)
            self._append_dashboard_diary_event(
                "dashboard_custom_project_created",
                project=project,
                payload={"project_name": project_name, "project_id": project.project_id},
            )
        snapshot = self.snapshot()
        snapshot["customized_project_created"] = {
            "project_id": snapshot["project"]["project_id"],
            "project_dir": snapshot["project"]["project_dir"],
            "source_template_id": snapshot["project"].get("source_template_id", ""),
        }
        return snapshot

    def load_custom_project(self, project_id: str) -> dict[str, Any]:
        record = _custom_project_record(self.project_registry_root, project_id)
        if record is None:
            raise KeyError(project_id)
        design = _normalize_dashboard_design(load_design(Path(record["active_design_path"])))
        if not _is_custom_design(design):
            raise ValueError("Only custom dashboard studies can be opened from the custom-study list.")
        context = _project_context_from_parts(
            registry_root=self.project_registry_root,
            project_id=record["project_id"],
            project_kind="custom",
            project_label=record["project_label"],
            source_template_id=record.get("source_template_id", ""),
            source_profile_id=record.get("source_profile_id", ""),
            created_at=record.get("created_at", ""),
        )
        design.study_profile_reference_parameters[PROJECT_METADATA_KEY] = {
            "schema": PROJECT_MANIFEST_SCHEMA,
            "project_id": context.project_id,
            "project_kind": context.project_kind,
            "project_label": context.project_label,
            "source_template_id": context.source_template_id,
            "source_profile_id": context.source_profile_id,
            "created_at": context.created_at,
            "placeholder_name": False,
        }
        with self._lock:
            self.design = design
            self.participant_id = ""
            self.current_run_package = None
            _write_project_context_files(context, self.design)
            _write_segment_validation_report(context, self.design)
            save_design(self.design, self.design_path)
            self._append_dashboard_diary_event(
                "dashboard_custom_project_loaded",
                project=context,
                payload={"project_id": project_id},
            )
        update_profile_runner_settings(
            state_root=self.state_root,
            output_folder=self.session_root,
            profile_id=context.project_id,
            profile_kind="custom",
            dashboard_project_id=context.project_id,
            participant_id="",
        )
        append_output_diary_event(
            "profile_selected",
            state_root=self.state_root,
            profile_id=context.project_id,
            profile_kind="custom",
            dashboard_project_id=context.project_id,
            participant_id="",
        )
        return self.snapshot()

    def export_data_acquisition_folder(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        save_payload = {
            key: value
            for key, value in payload.items()
            if key not in {"selected_folder", "data_acquisition_folder", "experiment_identifier"}
        }
        if save_payload:
            with self._lock:
                profile_run_mode = _is_readonly_profile_design(self.design)
            if profile_run_mode:
                self._apply_profile_runner_payload(save_payload)
            else:
                self.update_design(save_payload)
        selected_text = str(payload.get("selected_folder") or payload.get("data_acquisition_folder") or "").strip()
        selected_folder = Path(selected_text).expanduser() if selected_text else _choose_local_directory("Select PPS data acquisition folder")
        if selected_folder is None:
            raise ValueError("No data acquisition folder was selected.")
        with self._lock:
            project = self._ensure_project_context(self.design)
            design = _copy_design(self.design)
            participant_id = self.participant_id
        experiment_name = str(payload.get("experiment_identifier") or "").strip() or _experiment_identifier_for_diary(design, project)
        resolution = resolve_or_create_output_project(
            selected_folder,
            experiment_identifier=experiment_name,
        )
        profile_snapshot_root = output_profile_snapshot_dir(resolution.root)
        design_export_dir = _export_dashboard_project_to_acquisition_folder(project.project_dir, profile_snapshot_root, project.project_id)
        design_snapshot_path = profile_snapshot_root / "dashboard_design_snapshot.json"
        _write_text_file(design_snapshot_path, json.dumps(_json_ready(design_to_dict(design)), indent=2) + "\n", encoding="utf-8")
        bridge_manifest_path = acquisition_bridge_manifest_path(resolution.root)
        _ensure_dir(bridge_manifest_path.parent)
        bridge_manifest = {
            "schema": DATA_ACQUISITION_BRIDGE_SCHEMA,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "local_only": True,
            "data_acquisition_root": str(resolution.root),
            "diary_path": str(resolution.diary_path),
            "experiment_name": experiment_name,
            "profile_id": str(design.study_profile_id or ""),
            "participant_id": participant_id,
            "dashboard_project": project.to_dict(),
            "dashboard_project_export_dir": str(design_export_dir),
            "dashboard_design_snapshot_path": str(design_snapshot_path),
            "runner_settings_path": str(diary_runner_settings_path(self.state_root)),
            "reused_existing_diary": resolution.reused_existing_diary,
            "created_output_project": resolution.created,
        }
        _write_json(bridge_manifest_path, bridge_manifest)
        append_diary_entry(
            resolution.diary_path,
            "dashboard_data_acquisition_folder_exported",
            participant_id=participant_id,
            experiment_name=experiment_name,
            profile_id=str(design.study_profile_id or ""),
            payload={
                "selected_folder": str(selected_folder),
                "data_acquisition_root": str(resolution.root),
                "dashboard_project_dir": str(project.project_dir),
                "dashboard_project_export_dir": str(design_export_dir),
                "bridge_manifest_path": str(bridge_manifest_path),
                "design_snapshot_path": str(design_snapshot_path),
                "reused_existing_diary": resolution.reused_existing_diary,
                "created_output_project": resolution.created,
            },
        )
        update_diary_runner_settings(
            self.state_root,
            session_root=str(resolution.root),
            current_output_project_root=str(resolution.root),
            diary_path=str(resolution.diary_path),
            last_experiment_name=experiment_name,
            last_profile_id=str(design.study_profile_id or ""),
            last_participant_id=participant_id,
            last_capture_options={},
            bridge_manifest_path=str(bridge_manifest_path),
            dashboard_project_export_dir=str(design_export_dir),
        )
        profile_id = project.project_id if project.project_kind == "custom" else str(design.study_profile_id or project.project_id)
        update_profile_runner_settings(
            state_root=self.state_root,
            output_folder=resolution.root,
            profile_id=profile_id,
            profile_kind="custom" if project.project_kind == "custom" else "bundled",
            dashboard_project_id=project.project_id,
            participant_id=participant_id,
        )
        with self._lock:
            self.session_root = resolution.root
            self.current_run_package = None
        snapshot = self.snapshot()
        snapshot["data_acquisition_export_result"] = {
            **bridge_manifest,
            "bridge_manifest_path": str(bridge_manifest_path),
        }
        return snapshot

    def save_prepared_study_profile(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        profile_name = str(payload.get("name") or "").strip()
        if not profile_name:
            raise ValueError("Enter a profile name before saving.")
        created_at = datetime.now()
        with self._lock:
            source_project = self._ensure_project_context(self.design)
            source_design = _copy_design(self.design)
            run_setup_manifest_path = _run_setup_manifest_path(source_project.project_dir)
            manifest = _load_json(run_setup_manifest_path)
            errors = _validate_run_setup_manifest(manifest, project_dir=source_project.project_dir, design=source_design)
            if errors:
                raise ValueError(f"Prepare Segment 6 before saving a study profile: {errors[0]}")
            source_metadata = _project_metadata(source_design)
            source_profile_id = str(
                source_metadata.get("project_id")
                or source_design.study_profile_id
                or source_project.project_id
            ).strip()
            source_template_id = str(
                source_metadata.get("source_template_id")
                or source_design.study_profile_id
                or source_profile_id
            ).strip()
            project_id = generate_custom_profile_id(
                profile_name,
                self.project_registry_root,
                created_at=created_at,
                max_slug_length=CUSTOM_PROJECT_ID_SLUG_MAX_LENGTH,
            )
            new_context = _project_context_from_parts(
                registry_root=self.project_registry_root,
                project_id=project_id,
                project_kind="custom",
                project_label=profile_name,
                source_template_id=source_template_id,
                source_profile_id=source_profile_id,
                created_at=created_at.isoformat(timespec="seconds"),
            )
            if new_context.project_dir.exists():
                raise FileExistsError(f"Custom profile folder already exists: {new_context.project_dir}")
            copy_project_tree(source_project.project_dir, new_context.project_dir)
            rebase_project_copy_paths(new_context.project_dir, old_root=source_project.project_dir, new_root=new_context.project_dir)
            refresh_project_dependency_hashes(new_context.project_dir)
            saved_design = _copy_design(source_design)
            saved_design.name = profile_name
            saved_design.study_profile_id = ""
            saved_design.study_profile_title = ""
            params = dict(saved_design.study_profile_reference_parameters or {})
            params["dashboard_mode"] = "custom"
            params["source_profile_id"] = source_profile_id
            params["source_template_id"] = source_template_id
            params[PROJECT_METADATA_KEY] = {
                "schema": PROJECT_MANIFEST_SCHEMA,
                "project_id": new_context.project_id,
                "project_kind": new_context.project_kind,
                "project_label": new_context.project_label,
                "source_template_id": new_context.source_template_id,
                "source_profile_id": new_context.source_profile_id,
                "created_at": new_context.created_at,
                "placeholder_name": False,
            }
            saved_design.study_profile_reference_parameters = params
            self.design = saved_design
            self.participant_id = self.participant_id or "P001"
            self.current_run_package = None
            _write_project_context_files(new_context, self.design)
            _write_segment_validation_report(new_context, self.design)
            save_design(self.design, self.design_path)
            participant_id = self.participant_id
        update_profile_runner_settings(
            state_root=self.state_root,
            output_folder=self.session_root,
            profile_id=new_context.project_id,
            profile_kind="custom",
            dashboard_project_id=new_context.project_id,
            participant_id=participant_id,
            run_setup_manifest_path=_run_setup_manifest_path(new_context.project_dir),
        )
        record_experiment_activity(
            "profile_saved",
            state_root=self.state_root,
            template_id=new_context.project_id,
            project_dir=str(new_context.project_dir),
            design_path=str(self.design_path),
            run_setup_manifest_path=str(_run_setup_manifest_path(new_context.project_dir)),
            participant_id=participant_id,
            source_profile_id=source_profile_id,
        )
        append_output_diary_event(
            "profile_saved",
            state_root=self.state_root,
            profile_id=new_context.project_id,
            profile_kind="custom",
            dashboard_project_id=new_context.project_id,
            participant_id=participant_id,
            source_profile_id=source_profile_id,
            display_name=profile_name,
        )
        snapshot = self.snapshot()
        snapshot["saved_profile_result"] = {
            "profile_id": new_context.project_id,
            "display_name": profile_name,
            "project_dir": str(new_context.project_dir),
            "source_profile_id": source_profile_id,
        }
        return snapshot

    def export_active_output_folder(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if payload:
            with self._lock:
                profile_run_mode = _is_readonly_profile_design(self.design)
            if profile_run_mode:
                self._apply_profile_runner_payload(payload)
            else:
                self.update_design(payload)
        with self._lock:
            project = self._ensure_project_context(self.design)
            design = _copy_design(self.design)
            participant_id = self.participant_id
        manifest_path = _run_setup_manifest_path(project.project_dir)
        manifest = _load_json(manifest_path)
        errors = _validate_run_setup_manifest(manifest, project_dir=project.project_dir, design=design)
        if errors:
            raise ValueError(f"Prepare Segment 6 before preparing the output folder: {errors[0]}")
        settings = load_profile_runner_settings(state_root=self.state_root, default_output_folder=self.session_root)
        output_folder = Path(settings["active_output_folder"])
        profile_id = project.project_id if project.project_kind == "custom" else str(design.study_profile_id or project.project_id)
        catalog = build_profile_catalog(
            registry_root=self.project_registry_root,
            state_root=self.state_root,
            session_root=output_folder,
            inventory=self.preload_inventory,
        )
        profile_entry = next((entry for entry in catalog["entries"] if entry.get("profile_id") == profile_id), None)
        if profile_entry is None:
            profile_entry = {
                "profile_id": profile_id,
                "display_name": project.project_label,
                "kind": "custom" if project.project_kind == "custom" else "bundled",
                "dashboard_project_id": project.project_id,
                "project_dir": str(project.project_dir),
                "asset_roots": [str(project.project_dir)],
                "source_template_id": project.source_template_id,
                "source_profile_id": project.source_profile_id,
                "participant_count": int(manifest.get("participant_count") or 0),
                "participant_ids": [],
            }
        bridge = prepare_acquisition_folder(
            profile_entry=profile_entry,
            source_project_dir=project.project_dir,
            output_folder=output_folder,
            state_root=self.state_root,
            participant_id=participant_id,
        )
        record_experiment_activity(
            "acquisition_folder_exported",
            state_root=self.state_root,
            template_id=profile_id,
            project_dir=str(project.project_dir),
            design_path=str(self.design_path),
            run_setup_manifest_path=str(manifest_path),
            participant_id=participant_id,
            output_folder=str(output_folder),
            bridge_manifest_path=bridge.get("bridge_manifest_path", ""),
        )
        snapshot = self.snapshot()
        snapshot["output_folder_export_result"] = bridge
        return snapshot

    def update_design(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            previous_design = _copy_design(self.design)
            if _is_readonly_profile_design(previous_design) and _payload_mutates_design(payload):
                raise ValueError("Loaded study profiles are read-only. Use Edit As New Study before changing design settings.")
            if "participant_id" in payload:
                participant_id = str(payload.get("participant_id") or "").strip()
                self.participant_id = participant_id or ("" if _is_custom_design(self.design) else "P001")
            if "design" in payload:
                self.design = _carry_forward_project_metadata(previous_design, design_from_dict(dict(payload["design"])))
            elif any(key in payload for key in ("name", "trajectory", "protocol", "noises")):
                self.design = _carry_forward_project_metadata(previous_design, design_from_dict(payload))
            if "trajectory_controls" in payload:
                self.design = _apply_trajectory_controls(self.design, dict(payload["trajectory_controls"]))
            _apply_run_setup_payload(self.design, payload.get("run_setup"))
            self.design = _normalize_dashboard_design(self.design)
            if _should_refresh_placeholder_custom_project(self.design, self.project_registry_root):
                self._ensure_project_context(self.design, force_new_custom=True)
            else:
                self._ensure_project_context(self.design)
            self.current_run_package = None
            save_design(self.design, self.design_path)
            record_experiment_activity(
                "project_edited",
                state_root=self.state_root,
                template_id=self.design.study_profile_id,
                project_dir=str(_project_context_from_design(self.design, self.project_registry_root).project_dir if _project_context_from_design(self.design, self.project_registry_root) else ""),
                design_path=str(self.design_path),
                participant_id=self.participant_id,
            )
            self._append_dashboard_diary_event(
                "dashboard_design_saved",
                project=_project_context_from_design(self.design, self.project_registry_root),
                payload={
                    "payload_keys": sorted(str(key) for key in payload.keys()),
                    "design_name": self.design.name,
                },
            )
        return self.snapshot()

    def start_render_job(self, payload: dict[str, Any]) -> DashboardJob:
        if payload:
            self.update_design(payload)
        with self._lock:
            project = self._ensure_project_context(self.design)
            design = _copy_design(self.design)
            participant_id = self.participant_id
            self.current_run_package = None
        _require_custom_workflow_ready(design, participant_id, project.project_dir, require_participant=False)
        seed = int(design.protocol.random_seed or 20250604)
        render_dir = project.project_dir

        def _render() -> dict[str, Any]:
            _ensure_dir(render_dir)
            design_path = render_dir / "stimulus_design.for_dashboard_render.json"
            save_design(design, design_path)
            result = render_backend.render_design_with_3dti(design_path, render_dir, seed=seed)
            return {
                "status": result.status,
                "exit_code": result.exit_code,
                "output_dir": str(result.output_dir),
                "manifest_path": str(result.manifest_path),
                "qc_path": str(result.qc_path),
                "wav_paths": [str(path) for path in result.wav_paths],
                "tactile_events_path": str(result.tactile_events_path) if result.tactile_events_path else "",
            }

        return self.jobs.start("render", _render)

    def start_bake_stimulus_job(self, payload: dict[str, Any]) -> DashboardJob:
        recipe = dict(payload.get("bake_recipe") or {})
        if not recipe:
            raise ValueError("Choose a stimulus source before baking.")
        design_payload = {key: value for key, value in payload.items() if key != "bake_recipe"}
        if design_payload:
            self.update_design(design_payload)
        with self._lock:
            project = self._ensure_project_context(self.design)
            design = _copy_design(self.design)
        recipe_kind = str(recipe.get("kind") or "").strip().lower()
        self._append_dashboard_diary_event(
            "dashboard_bake_requested",
            design=design,
            project=project,
            payload={"recipe_kind": recipe_kind, "recipe_label": str(recipe.get("label") or "")},
        )
        if recipe_kind != "block_csv_preview":
            _raise_if_current_block_csvs_accepted(project.project_dir, design)
        if recipe_kind == "trial_sequence_batch":
            render_dir = project.project_dir

            def _batch_bake() -> dict[str, Any]:
                _ensure_dir(render_dir)
                with self._lock:
                    active_project = self._ensure_project_context(self.design)
                    result = _bake_trial_sequence_variants(self.design, active_project.project_dir)
                    _clear_downstream_segment_outputs(active_project, from_segment=2)
                    report = _write_segment_validation_report(active_project, self.design)
                    self.current_run_package = None
                    save_design(self.design, self.design_path)
                return {
                    **result,
                    "source_kind": "trial_sequence_batch",
                    "validation_report_path": str(report),
                    "local_only": True,
                    "message": "Trial-sequence variants were baked by the local companion backend; no online upload was performed.",
                }

            return self.jobs.start("stimulus_bake", _batch_bake)
        if recipe_kind == "audiotactile_trial_batch":
            render_dir = project.project_dir

            def _trial_file_bake() -> dict[str, Any]:
                _ensure_dir(render_dir)
                with self._lock:
                    active_project = self._ensure_project_context(self.design)
                    result = _bake_audio_tactile_trial_files(self.design, active_project.project_dir)
                    _clear_downstream_segment_outputs(active_project, from_segment=3)
                    report = _write_segment_validation_report(active_project, self.design)
                    self.current_run_package = None
                    save_design(self.design, self.design_path)
                return {
                    **result,
                    "source_kind": "audiotactile_trial_batch",
                    "validation_report_path": str(report),
                    "local_only": True,
                    "message": "Audio-tactile and baseline trial files were baked by the local companion backend; no online upload was performed.",
                }

            return self.jobs.start("stimulus_bake", _trial_file_bake)
        if recipe_kind == "trial_repetition_pool":
            render_dir = project.project_dir

            def _trial_pool_bake() -> dict[str, Any]:
                _ensure_dir(render_dir)
                with self._lock:
                    active_project = self._ensure_project_context(self.design)
                    result = _bake_trial_repetition_pool(self.design, active_project.project_dir, recipe)
                    _clear_downstream_segment_outputs(active_project, from_segment=4)
                    report = _write_segment_validation_report(active_project, self.design)
                    self.current_run_package = None
                    save_design(self.design, self.design_path)
                return {
                    **result,
                    "source_kind": "trial_repetition_pool",
                    "validation_report_path": str(report),
                    "local_only": True,
                    "message": "Trial repetition pool CSV was written by the local companion backend; no WAV files were duplicated.",
                }

            return self.jobs.start("stimulus_bake", _trial_pool_bake)
        if recipe_kind == "block_csv_preview":
            _raise_if_current_block_csvs_accepted(project.project_dir, design)
            render_dir = project.project_dir

            def _block_csv_bake(progress: Callable[[int, int, str], None]) -> dict[str, Any]:
                _ensure_dir(render_dir)
                with self._lock:
                    active_project = self._ensure_project_context(self.design)
                    active_design = _copy_design(self.design)
                    _raise_if_current_block_csvs_accepted(active_project.project_dir, active_design)
                result = _bake_block_csv_preview(active_design, active_project.project_dir, recipe, progress=progress)
                with self._lock:
                    _clear_downstream_segment_outputs(active_project, from_segment=5)
                    report = _write_segment_validation_report(active_project, self.design)
                    self.current_run_package = None
                    save_design(self.design, self.design_path)
                return {
                    **result,
                    "source_kind": "block_csv_preview",
                    "validation_report_path": str(report),
                    "local_only": True,
                    "message": "Block CSV preview files were written by the local companion backend.",
                }

            return self.jobs.start("block_csv_preview", _block_csv_bake, progress=True)
        label = _unique_stimulus_label(_bake_recipe_label(recipe), design)
        bake_design, source_kind, source_payload = _design_for_bake_recipe(design, recipe, label)
        trajectory_snapshot = _stimulus_trajectory_snapshot(
            design,
            label=label,
            source_kind=source_kind,
            noise_type=str(source_payload.get("noise_type") or CUSTOM_AUDIO_NOISE_TYPE),
        )
        source_payload["trajectory_snapshot"] = trajectory_snapshot
        seed = int(design.protocol.random_seed or 20250604)
        render_dir = project.project_dir
        ingredient_dir = project.segment1_dir

        def _bake() -> dict[str, Any]:
            _ensure_dir(ingredient_dir)
            design_path = ingredient_dir / f"stimulus_design.bake_{_slug(label)}.json"
            _save_design_file(bake_design, design_path)
            result = render_backend.render_design_with_3dti(
                design_path,
                ingredient_dir,
                seed=seed,
                engine="python-sofa-reference",
                include_tactile=False,
            )
            raw_wav_path = _baked_wav_path(result, label)
            if raw_wav_path is None or not _path_exists(raw_wav_path):
                raise RuntimeError(f"Bake did not create a WAV for {label}.")
            wav_path = _materialize_ingredient_audio_file(raw_wav_path, ingredient_dir, label, motion_mode="looming")
            _rewrite_render_manifest_wav_path(result.manifest_path, old_path=raw_wav_path, new_path=wav_path)

            with self._lock:
                active_project = self._ensure_project_context(self.design)
                _record_ingredient_file(
                    active_project,
                    wav_path,
                    label=label,
                    source_kind=source_kind,
                    trajectory_snapshot=trajectory_snapshot,
                    motion_mode="looming",
                    provenance={"loudness_policy": loudness_policy_for_design(bake_design)},
                )
                if source_kind == "generated_noise":
                    source_payload["prebaked_path"] = str(wav_path)
                    source = NoiseDefinition(**source_payload)
                    self.design.noises.append(source)
                    saved_source = asdict(source)
                else:
                    source = AudioFileSpec(
                        label=label,
                        path=str(wav_path),
                        target_duration_s=float(source_payload.get("target_duration_s", design.trajectory.total_duration_s)),
                        render_mode="preserve",
                        tone_type=str(source_payload.get("tone_type") or CUSTOM_AUDIO_NOISE_TYPE),
                        gain=1.0,
                        motion_mode="looming",
                        trajectory_snapshot=trajectory_snapshot,
                    )
                    self.design.custom_looming_files.append(source)
                    saved_source = asdict(source)
                _clear_downstream_segment_outputs(active_project, from_segment=1)
                report = _write_segment_validation_report(active_project, self.design)
                self.current_run_package = None
                save_design(self.design, self.design_path)

            return {
                "status": result.status,
                "exit_code": result.exit_code,
                "source_kind": source_kind,
                "source": saved_source,
                "wav_path": str(wav_path),
                "manifest_path": str(result.manifest_path),
                "qc_path": str(result.qc_path),
                "validation_report_path": str(report),
                "include_tactile": False,
                "local_only": True,
                "message": "Stimulus was baked by the local companion backend; no online upload was performed.",
            }

        return self.jobs.start("stimulus_bake", _bake)

    def prepare_session(
        self,
        payload: dict[str, Any],
        *,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        snapshot: bool = True,
    ) -> dict[str, Any]:
        if payload:
            with self._lock:
                profile_run_mode = _is_readonly_profile_design(self.design)
            if profile_run_mode:
                self._apply_profile_runner_payload(payload)
            else:
                self.update_design(payload)
        with self._lock:
            project = self._ensure_project_context(self.design)
            design = _copy_design(self.design)
            participant_id = self.participant_id
        session_root = active_output_folder(state_root=self.state_root, fallback=self.session_root)
        gate_errors = _profile_runner_readiness_errors(design)
        if gate_errors:
            raise ValueError(gate_errors[0])
        if _is_readonly_profile_design(design):
            self._ensure_profile_run_artifacts(project, design, progress_callback=progress_callback)
            with self._lock:
                project = self._ensure_project_context(self.design)
                design = _copy_design(self.design)
                participant_id = self.participant_id
        elif _is_custom_design(design):
            _require_custom_workflow_ready(design, participant_id, project.project_dir, require_participant=True)

        run_setup_manifest_path = _run_setup_manifest_path(project.project_dir)
        run_setup_manifest = _load_json(run_setup_manifest_path)
        run_setup_errors = _validate_run_setup_manifest(run_setup_manifest, project_dir=project.project_dir, design=design)
        segment_run_required = (
            _is_readonly_profile_design(design)
            or _is_custom_design(design)
            or str(project.project_kind or "").strip().lower() == "custom"
            or bool(run_setup_manifest)
        )
        if run_setup_manifest and not run_setup_errors:
            claimed_manifest = claim_prepared_session(
                run_setup_manifest_path,
                participant_id,
                state_root=self.state_root,
                session_root=self.session_root,
            )
            if claimed_manifest is not None and not _path_is_within(claimed_manifest, session_root):
                claimed_manifest = None
            if claimed_manifest is not None:
                package = load_run_package(claimed_manifest)
                if progress_callback is not None:
                    progress_callback(
                        {
                            "phase": "prewarm_reused",
                            "message": f"Using prewarmed session for {participant_id}",
                            "detail": str(claimed_manifest),
                            "current": 1,
                            "total": 1,
                            "timestamp_unix": time.time(),
                        }
                    )
            else:
                package = prepare_segment_run_package(
                    run_setup_manifest_path,
                    participant_id,
                    design=design,
                    session_root=session_root,
                    progress_callback=progress_callback,
                )
        else:
            if segment_run_required:
                detail = run_setup_errors[0] if run_setup_errors else "Segment 6 manifest is missing."
                raise ValueError(f"Prepare Segment 6 experiment before preparing a participant session: {detail}")
            artifact_root = self._lookup_root_for_design(design, project)
            package = prepare_run_package(
                design,
                participant_id,
                render_dir=artifact_root,
                session_root=session_root,
            )
        with self._lock:
            self.current_run_package = package
        self._append_dashboard_diary_event(
            "dashboard_session_prepared",
            design=design,
            project=project,
            payload={
                "session_manifest_path": str(package.manifest_path),
                "session_dir": str(package.session_dir),
                "run_setup_manifest_path": str(run_setup_manifest_path),
            },
        )
        return self.snapshot() if snapshot else {"session_manifest": str(package.manifest_path), "session_dir": str(package.session_dir)}

    def accept_block_csv_preview(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if payload:
            self.update_design(payload)
        with self._lock:
            project = self._ensure_project_context(self.design)
            design = _copy_design(self.design)
        manifest_path = _block_csv_preview_manifest_path(project.project_dir)
        manifest = _load_json(manifest_path)
        errors = _validate_block_csv_preview_manifest(manifest, project_dir=project.project_dir, design=design)
        if errors:
            raise ValueError(f"Cannot accept Segment 5 block CSVs: {errors[0]}")
        if not bool(manifest.get("accepted")):
            manifest = _finalize_block_csv_manifest(manifest)
        manifest["accepted"] = True
        manifest["accepted_at"] = manifest.get("accepted_at") or datetime.now().isoformat(timespec="seconds")
        manifest["accepted_source_segment4_manifest_sha256"] = manifest.get("source_segment4_manifest_sha256", "")
        errors = _validate_block_csv_preview_manifest(manifest, project_dir=project.project_dir, design=design)
        if errors:
            raise ValueError(f"Cannot accept Segment 5 block CSVs: {errors[0]}")
        _write_json(manifest_path, manifest)
        self._append_dashboard_diary_event(
            "dashboard_block_csvs_accepted",
            design=design,
            project=project,
            payload={"manifest_path": str(manifest_path)},
        )
        return self.snapshot()

    def edit_block_csv_preview(self) -> dict[str, Any]:
        with self._lock:
            project = self._ensure_project_context(self.design)
            design = _copy_design(self.design)
        manifest_path = _block_csv_preview_manifest_path(project.project_dir)
        manifest = _load_json(manifest_path)
        errors = _validate_block_csv_preview_manifest(manifest, project_dir=project.project_dir, design=design)
        if errors:
            raise ValueError(f"Cannot reopen Segment 5 block CSVs: {errors[0]}")
        if bool(manifest.get("accepted")):
            manifest = _reopen_block_csv_manifest(manifest)
        manifest["accepted"] = False
        manifest["accepted_at"] = ""
        manifest["accepted_source_segment4_manifest_sha256"] = ""
        manifest["reopened_at"] = datetime.now().isoformat(timespec="seconds")
        errors = _validate_block_csv_preview_manifest(manifest, project_dir=project.project_dir, design=design)
        if errors:
            raise ValueError(f"Cannot reopen Segment 5 block CSVs: {errors[0]}")
        _write_json(manifest_path, manifest)
        _clear_downstream_segment_outputs(project, from_segment=5)
        self._append_dashboard_diary_event(
            "dashboard_block_csvs_reopened",
            design=design,
            project=project,
            payload={"manifest_path": str(manifest_path)},
        )
        return self.snapshot()

    def preview_run_sequence(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if payload:
            self.update_design(payload)
        return self.snapshot()

    def regenerate_run_sequence(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if payload:
            self.update_design(payload)
        with self._lock:
            project = self._ensure_project_context(self.design)
            manifest = _load_json(_run_setup_manifest_path(project.project_dir))
            errors = _validate_run_setup_manifest(manifest, project_dir=project.project_dir, design=self.design)
            if manifest and not errors:
                raise ValueError("Segment 6 experiment setup is prepared. Change requests should start from a new prepared setup rather than silently regenerating it.")
            settings = _run_setup_settings(self.design)
            settings["seed"] = int(time.time() * 1000) + random.randint(1, 999999)
            _set_run_setup_settings(self.design, settings)
            self.current_run_package = None
            save_design(self.design, self.design_path)
            self._append_dashboard_diary_event(
                "dashboard_run_sequence_regenerated",
                project=project,
                payload={"seed": settings["seed"]},
            )
        return self.snapshot()

    def prepare_experiment_run_setup(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if payload:
            self.update_design(payload)
        with self._lock:
            project = self._ensure_project_context(self.design)
            gate_errors = _profile_runner_readiness_errors(self.design)
            if gate_errors:
                raise ValueError(gate_errors[0])
            manifest = _load_json(_run_setup_manifest_path(project.project_dir))
            errors = _validate_run_setup_manifest(manifest, project_dir=project.project_dir, design=self.design)
            if manifest and not errors:
                raise ValueError(
                    "Segment 6 experiment setup is already prepared. Start from a new setup or change upstream segments before preparing again."
                )
            result = _write_run_setup_outputs(project.project_dir, self.design)
            _write_segment_validation_report(project, self.design)
            self.current_run_package = None
            save_design(self.design, self.design_path)
            record_experiment_activity(
                "run_setup_prepared",
                state_root=self.state_root,
                template_id=self.design.study_profile_id,
                project_dir=str(project.project_dir),
                design_path=str(self.design_path),
                run_setup_manifest_path=result.get("manifest_path", ""),
                participant_id=self.participant_id,
                experiment_structure=result.get("experiment_structure", _run_setup_settings(self.design).get("experiment_structure", "")),
            )
            self._append_dashboard_diary_event(
                "dashboard_run_setup_prepared",
                project=project,
                payload={
                    "run_setup_manifest_path": result.get("manifest_path", ""),
                    "experiment_structure": result.get("experiment_structure", _run_setup_settings(self.design).get("experiment_structure", "")),
                },
            )
        snapshot = self.snapshot()
        snapshot["run_sequence_prepare_result"] = result
        return snapshot

    def _ensure_profile_run_artifacts(
        self,
        project: DashboardProjectContext,
        design: StimulusDesign,
        *,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        if _is_custom_design(design) or not str(design.study_profile_id or "").strip():
            return {}
        gate_errors = _profile_runner_readiness_errors(design)
        if gate_errors:
            raise ValueError(gate_errors[0])

        project_dir = project.project_dir
        result: dict[str, Any] = {
            "status": "already_ready",
            "profile_id": design.study_profile_id,
            "steps": [],
            "local_only": True,
        }

        def record_step(segment: str, payload: dict[str, Any]) -> None:
            result["status"] = "materialized"
            result["steps"].append({
                "segment": segment,
                "status": payload.get("status", "ready"),
                "manifest_path": payload.get("manifest_path", ""),
            })
            if progress_callback is not None:
                progress_callback(
                    {
                        "phase": segment,
                        "message": f"Prepared {segment}",
                        "detail": str(payload.get("manifest_path", "")),
                        "current": len(result["steps"]),
                        "total": 6,
                        "timestamp_unix": time.time(),
                    }
                )

        if progress_callback is not None:
            progress_callback(
                {
                    "phase": "checking_segments",
                    "message": "Checking Segment artifacts",
                    "detail": str(project_dir),
                    "current": 0,
                    "total": 6,
                    "timestamp_unix": time.time(),
                }
            )
        sequence_manifest = _load_trial_sequence_manifest(project_dir)
        sequence_errors = _validate_trial_sequence_manifest(sequence_manifest, design=design)
        if sequence_errors:
            record_step("2_trial_sequence_designs", _bake_trial_sequence_variants(design, project_dir))

        tactile_manifest_path = _baseline_tactile_bake_root(project_dir) / "baseline_tactile_trial_files_manifest.json"
        tactile_manifest = _load_json(tactile_manifest_path)
        tactile_errors = _validate_tactile_trial_manifest(tactile_manifest, design=design)
        if tactile_errors:
            record_step("3_tactile_and_baseline_trials", _bake_audio_tactile_trial_files(design, project_dir))

        pool_manifest = _load_json(_trial_pool_manifest_path(project_dir))
        pool_errors = _validate_trial_pool_manifest(pool_manifest, project_dir=project_dir, design=design)
        if pool_errors:
            record_step(
                "4_trial_repetition_pool",
                _bake_trial_repetition_pool(design, project_dir, {"kind": "trial_repetition_pool", "label": "4_trial_repetition_pool"}),
            )

        block_manifest_path = _block_csv_preview_manifest_path(project_dir)
        block_manifest = _load_json(block_manifest_path)
        block_errors = _validate_block_csv_preview_manifest(block_manifest, project_dir=project_dir, design=design)
        if block_errors:
            record_step(
                "5_block_csv_preview",
                _bake_block_csv_preview(
                    design,
                    project_dir,
                    {
                        "kind": "block_csv_preview",
                        "label": "5_block_csv_preview",
                        "block_count": max(1, int(getattr(design.protocol, "blocks", 1) or 1)),
                    },
                ),
            )
            block_manifest = _load_json(block_manifest_path)

        if block_manifest and not bool(block_manifest.get("accepted")):
            accepted_manifest = _finalize_block_csv_manifest(block_manifest)
            accepted_manifest["accepted"] = True
            accepted_manifest["accepted_at"] = accepted_manifest.get("accepted_at") or datetime.now().isoformat(timespec="seconds")
            accepted_manifest["accepted_source_segment4_manifest_sha256"] = accepted_manifest.get("source_segment4_manifest_sha256", "")
            accepted_errors = _validate_block_csv_preview_manifest(accepted_manifest, project_dir=project_dir, design=design)
            if accepted_errors:
                raise ValueError(f"Cannot accept Segment 5 block CSVs for profile launch: {accepted_errors[0]}")
            _write_json(block_manifest_path, accepted_manifest)
            record_step("5_block_csv_preview", {"status": "accepted", "manifest_path": str(block_manifest_path)})

        run_manifest = _load_json(_run_setup_manifest_path(project_dir))
        run_errors = _validate_run_setup_manifest(run_manifest, project_dir=project_dir, design=design)
        if run_errors:
            if progress_callback is not None:
                progress_callback(
                    {
                        "phase": "segment6",
                        "message": "Preparing Segment 6 setup",
                        "detail": str(_run_setup_manifest_path(project_dir)),
                        "current": 5,
                        "total": 6,
                        "timestamp_unix": time.time(),
                    }
                )
            record_step("6_experiment_run_setup", _write_run_setup_outputs(project_dir, design))

        if result["steps"]:
            _write_segment_validation_report(project, design)
            with self._lock:
                self.current_run_package = None
                save_design(self.design, self.design_path)
        return result

    def open_experiment_runner(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if payload:
            with self._lock:
                profile_run_mode = _is_readonly_profile_design(self.design)
            if profile_run_mode:
                self._apply_profile_runner_payload(payload)
            else:
                self.update_design(payload)
        with self._lock:
            project = self._ensure_project_context(self.design)
            design = _copy_design(self.design)
            participant_id = self.participant_id
            existing_package = self.current_run_package
        session_root = active_output_folder(state_root=self.state_root, fallback=self.session_root)
        gate_errors = _profile_runner_readiness_errors(design)
        if gate_errors:
            raise ValueError(gate_errors[0])
        profile_materialization = self._ensure_profile_run_artifacts(project, design)
        with self._lock:
            project = self._ensure_project_context(self.design)
            design = _copy_design(self.design)
            participant_id = self.participant_id
            existing_package = self.current_run_package
        run_setup_manifest_path = _run_setup_manifest_path(project.project_dir)
        manifest = _load_json(run_setup_manifest_path)
        errors = _validate_run_setup_manifest(manifest, project_dir=project.project_dir, design=design)
        if errors:
            raise ValueError(f"Prepare Segment 6 experiment before opening the runner: {errors[0]}")
        if not participant_id:
            raise ValueError("Participant ID is required before opening Focus Mode.")
        if (
            existing_package is not None
            and existing_package.participant_id == participant_id
            and existing_package.source_run_setup_manifest_path is not None
            and Path(existing_package.source_run_setup_manifest_path).resolve() == run_setup_manifest_path.resolve()
            and _path_exists(existing_package.manifest_path)
        ):
            package = existing_package
        else:
            claimed_manifest = claim_prepared_session(
                run_setup_manifest_path,
                participant_id,
                state_root=self.state_root,
                session_root=self.session_root,
            )
            if claimed_manifest is not None and not _path_is_within(claimed_manifest, session_root):
                claimed_manifest = None
            if claimed_manifest is not None:
                package = load_run_package(claimed_manifest)
            else:
                package = prepare_segment_run_package(
                    run_setup_manifest_path,
                    participant_id,
                    design=design,
                    session_root=session_root,
                )
            with self._lock:
                self.current_run_package = package
            record_experiment_activity(
                "session_prepared",
                state_root=self.state_root,
                template_id=design.study_profile_id,
                project_dir=str(project.project_dir),
                design_path=str(self.design_path),
                run_setup_manifest_path=str(run_setup_manifest_path),
                session_manifest_path=str(package.manifest_path),
                session_dir=str(package.session_dir),
                participant_id=participant_id,
                experiment_structure=str(manifest.get("experiment_structure") or ""),
            )
        profile_id = project.project_id if project.project_kind == "custom" else str(design.study_profile_id or project.project_id)
        profile_kind = "custom" if project.project_kind == "custom" else "bundled"
        update_profile_runner_settings(
            state_root=self.state_root,
            output_folder=session_root,
            profile_id=profile_id,
            profile_kind=profile_kind,
            dashboard_project_id=project.project_id,
            participant_id=participant_id,
            run_setup_manifest_path=run_setup_manifest_path,
            session_manifest_path=package.manifest_path,
        )
        export_snapshot = self.export_active_output_folder()
        bridge_result = export_snapshot.get("output_folder_export_result", {}) if isinstance(export_snapshot, dict) else {}
        launch_command = build_focus_runner_command(
            package.manifest_path,
            manual_start=True,
        )
        command = launch_command.command
        process = subprocess.Popen(command, cwd=WRITABLE_ROOT, **windows_no_console_kwargs())
        record_experiment_activity(
            "runner_launched",
            state_root=self.state_root,
            template_id=design.study_profile_id,
            project_dir=str(project.project_dir),
            design_path=str(self.design_path),
            run_setup_manifest_path=str(run_setup_manifest_path),
            session_manifest_path=str(package.manifest_path),
            session_dir=str(package.session_dir),
            participant_id=participant_id,
            runner_binary=launch_command.runner_binary,
            packaged_runner=launch_command.packaged_runner,
        )
        self._append_dashboard_diary_event(
            "dashboard_runner_opened",
            design=design,
            project=project,
            payload={
                "session_manifest_path": str(package.manifest_path),
                "session_dir": str(package.session_dir),
                "run_setup_manifest_path": str(run_setup_manifest_path),
                "runner_binary": launch_command.runner_binary,
                "packaged_runner": launch_command.packaged_runner,
            },
        )
        append_output_diary_event(
            "runner_launched",
            state_root=self.state_root,
            profile_id=profile_id,
            profile_kind=profile_kind,
            dashboard_project_id=project.project_id,
            participant_id=participant_id,
            run_setup_manifest_path=str(run_setup_manifest_path),
            session_manifest_path=str(package.manifest_path),
            session_dir=str(package.session_dir),
            runner_binary=launch_command.runner_binary,
        )
        result = {
            "status": "launched",
            "pid": process.pid,
            "command": command,
            "runner": "PPSExperimentRunner.exe",
            "packaged_runner": launch_command.packaged_runner,
            "runner_binary": launch_command.runner_binary,
            "execution_mode": "participant_block_wavs",
            "runner_input_manifest": str(package.manifest_path),
            "stimuli_dir": "",
            "run_setup_manifest": str(run_setup_manifest_path),
            "session_manifest": str(package.manifest_path),
            "session_dir": str(package.session_dir),
            "bridge_manifest": str(bridge_result.get("bridge_manifest_path") or ""),
            "runner_options": "collected by PPSExperimentRunner.exe",
            "local_only": True,
        }
        snapshot = self.snapshot()
        snapshot["experiment_runner_launch_result"] = result
        if profile_materialization:
            snapshot["profile_run_materialization_result"] = profile_materialization
        return snapshot

    def _apply_profile_runner_payload(self, payload: dict[str, Any]) -> None:
        with self._lock:
            if "participant_id" in payload:
                participant_id = str(payload.get("participant_id") or "").strip()
                self.participant_id = participant_id or "P001"
            self.current_run_package = None

    def import_audio_source(self, payload: dict[str, Any]) -> dict[str, Any]:
        filename = _safe_filename(str(payload.get("filename") or "audio.wav"))
        encoded = str(payload.get("content_base64") or "")
        if not encoded:
            raise ValueError("Audio import is missing file content.")
        if "," in encoded:
            encoded = encoded.split(",", 1)[1]
        try:
            content = base64.b64decode(encoded, validate=True)
        except binascii.Error as exc:
            raise ValueError("Audio import content is not valid base64.") from exc
        if not content:
            raise ValueError("Audio import file is empty.")

        original = Path(filename)
        suffix = original.suffix or ".wav"
        label = str(payload.get("label") or Path(filename).stem).strip() or Path(filename).stem
        with self._lock:
            project = self._ensure_project_context(self.design)
        _ensure_dir(project.segment1_dir)
        temp_path = project.segment1_dir / f"_import_{uuid.uuid4().hex[:10]}{suffix}"
        _write_bytes_file(temp_path, content)
        duration_s = _float(payload.get("target_duration_s"), 0.0)
        if duration_s <= 0:
            try:
                duration_s = float(audio_file_summary(temp_path)["duration_s"])
            except Exception:
                duration_s = 4.0
        render_mode = str(payload.get("render_mode") or "preserve").strip().lower()
        if render_mode not in {"spatialize", "preserve"}:
            render_mode = "preserve"
        placement = str(payload.get("placement") or "before").strip().lower()
        if placement not in {"before", "after"}:
            placement = "before"
        motion_mode = str(payload.get("motion_mode") or "looming").strip().lower()
        if motion_mode not in {"looming", "stationary"}:
            motion_mode = "looming"
        path = _materialize_ingredient_audio_file(temp_path, project.segment1_dir, label, motion_mode=motion_mode)
        audio = AudioFileSpec(
            label=label,
            path=str(path),
            target_duration_s=duration_s,
            render_mode=render_mode,
            gain=_float(payload.get("gain"), 1.0),
            placement=placement,
            target_source_label=str(payload.get("target_source_label") or "").strip(),
            phase=str(payload.get("phase") or "").strip(),
            gap_s=max(0.0, _float(payload.get("gap_s"), 0.0)),
            sequence_order=max(0, int(_float(payload.get("sequence_order"), 0.0))),
            motion_mode=motion_mode,
        )
        _record_ingredient_file(
            project,
            path,
            label=label,
            source_kind="imported_audio",
            trajectory_snapshot={},
            motion_mode=motion_mode,
            provenance={"loudness_policy": loudness_policy_for_design(self.design)},
        )
        _clear_downstream_segment_outputs(project, from_segment=1)
        _write_segment_validation_report(project, self.design)
        return {
            "audio": asdict(audio),
            "local_only": True,
            "message": "Stored by the local companion backend; no online upload was performed.",
        }

    def import_run_instruction_audio(self, payload: dict[str, Any]) -> dict[str, Any]:
        slot = str(payload.get("slot") or "").strip()
        if slot not in RUN_INSTRUCTION_SLOTS:
            raise ValueError("Choose a valid Segment 6 instruction slot.")
        filename = _safe_filename(str(payload.get("filename") or "instruction.wav"))
        encoded = str(payload.get("content_base64") or "")
        if not encoded:
            raise ValueError("Instruction audio import is missing file content.")
        if "," in encoded:
            encoded = encoded.split(",", 1)[1]
        try:
            content = base64.b64decode(encoded, validate=True)
        except binascii.Error as exc:
            raise ValueError("Instruction audio import content is not valid base64.") from exc
        if not content:
            raise ValueError("Instruction audio import file is empty.")
        label = str(payload.get("label") or Path(filename).stem).strip() or RUN_INSTRUCTION_SLOT_LABELS[slot]
        with self._lock:
            project = self._ensure_project_context(self.design)
            library_dir = _run_instruction_library_dir(project.project_dir)
            _ensure_dir(library_dir)
            temp_path = library_dir / f"_import_{uuid.uuid4().hex[:10]}{Path(filename).suffix or '.wav'}"
            _write_bytes_file(temp_path, content)
            audio = _materialize_run_instruction_audio_file(temp_path, library_dir, slot=slot, label=label)
            profile = _run_instruction_profile(self.design)
            slots = []
            for item in profile.get("slots", []):
                if item.get("slot") == slot:
                    item = {
                        **item,
                        "label": label,
                        "enabled": True,
                        "path": str(audio["path"]),
                        "duration_s": float(audio["duration_s"]),
                        "sample_rate": int(audio["sample_rate"]),
                        "channels": int(audio["channels"]),
                        "sha256": str(audio["sha256"]),
                        "source": "custom_import",
                    }
                slots.append(item)
            _set_run_setup_settings(self.design, {"instruction_profile": {"schema": RUN_INSTRUCTION_PROFILE_SCHEMA, "slots": slots}})
            _clear_segment6_generated_outputs(project.segment6_dir)
            _write_project_context_files(project, self.design)
            _write_segment_validation_report(project, self.design)
            self.current_run_package = None
            save_design(self.design, self.design_path)
        snapshot = self.snapshot()
        snapshot["run_instruction_import_result"] = {
            "slot": slot,
            "audio": audio,
            "local_only": True,
            "message": "Stored by the local companion backend; no online upload was performed.",
        }
        return snapshot

    def preview_trial_strip_audio(self, payload: dict[str, Any]) -> dict[str, Any]:
        if "design" in payload:
            design = design_from_dict(dict(payload["design"]))
        else:
            with self._lock:
                design = _copy_design(self.design)
        if "trajectory_controls" in payload:
            design = _apply_trajectory_controls(design, dict(payload["trajectory_controls"]))
        with self._lock:
            project = self._ensure_project_context(self.design)
        artifact_root = self._lookup_root_for_design(design, project)

        strips = [strip for strip in design.protocol.trial_strips if strip.elements]
        if not strips:
            raise ValueError("Create an event sequence before previewing audio.")
        strip_index = max(0, int(_float(payload.get("strip_index"), 0)))
        if strip_index >= len(strips):
            raise ValueError("The requested event sequence does not exist.")
        return _trial_strip_audio_preview(
            design,
            strips[strip_index],
            strip_index=strip_index,
            render_dir=artifact_root,
            preview_dir=self.preview_dir,
        )

    def preview_source_audio(self, payload: dict[str, Any]) -> dict[str, Any]:
        label = str(payload.get("label") or "").strip()
        if not label:
            raise ValueError("Choose a source label to preview.")
        if "design" in payload:
            design = design_from_dict(dict(payload["design"]))
        else:
            with self._lock:
                design = _copy_design(self.design)
        if "trajectory_controls" in payload:
            design = _apply_trajectory_controls(design, dict(payload["trajectory_controls"]))
        with self._lock:
            project = self._ensure_project_context(self.design)
        artifact_root = self._lookup_root_for_design(design, project)
        return _source_audio_preview(
            design,
            label,
            render_dir=artifact_root,
            preview_dir=self.preview_dir,
        )

    def open_local_folder(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_path = str(payload.get("path") or "").strip()
        if not raw_path:
            raise ValueError("No local path was provided.")
        target = Path(raw_path).expanduser()
        if not target.is_absolute():
            target = REPO_ROOT / target
        target = target.resolve()
        allowed_roots = [
            self.render_dir.resolve(),
            self.import_dir.resolve(),
            self.session_root.resolve(),
            self.design_path.resolve().parent,
            self.project_registry_root.resolve(),
            (REPO_ROOT / "assets" / "preloads").resolve(),
        ]
        if not any(target == root or root in target.parents for root in allowed_roots):
            raise ValueError("Local folder opening is limited to dashboard-managed folders.")
        folder = target if os.path.isdir(_filesystem_path(target)) else target.parent
        if not _path_exists(folder):
            raise FileNotFoundError(f"Local folder does not exist: {folder}")
        if sys.platform.startswith("win"):
            if _path_exists(target) and os.path.isfile(_filesystem_path(target)):
                subprocess.Popen(["explorer.exe", f"/select,{target}"])
            else:
                subprocess.Popen(["explorer.exe", str(folder)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])
        return {
            "local_only": True,
            "path": str(target),
            "folder": str(folder),
            "message": "Opened by the local companion backend.",
        }

    def start_audio_stress_job(self) -> DashboardJob:
        command = [
            sys.executable,
            "-m",
            "peripersonal_space_toolkit.audio_device_stress",
            "--device-query",
            "Komplete",
            "--mode",
            "callback",
            "--iterations",
            "1",
            "--duration-s",
            "2",
            "--latency",
            "0.010",
            "--blocksize",
            "256",
        ]

        def _stress() -> dict[str, Any]:
            completed = subprocess.run(
                command,
                cwd=WRITABLE_ROOT,
                text=True,
                capture_output=True,
                timeout=45,
                check=False,
                **windows_no_console_kwargs(),
            )
            return {
                "exit_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "command": command,
            }

        return self.jobs.start("audio_stress", _stress)

    def start_focus_job(self) -> DashboardJob:
        with self._lock:
            package = self.current_run_package
        if package is None:
            raise RuntimeError("Prepare a session before starting native Focus Mode.")
        launch_command = build_focus_runner_command(package.manifest_path, manual_start=True)
        command = launch_command.command

        def _focus() -> dict[str, Any]:
            process = subprocess.Popen(command, cwd=WRITABLE_ROOT, **windows_no_console_kwargs())
            return {
                "pid": process.pid,
                "command": command,
                "packaged_runner": launch_command.packaged_runner,
                "runner_binary": launch_command.runner_binary,
                "session_manifest": str(package.manifest_path),
            }

        return self.jobs.start("focus_start", _focus)


def create_app(
    controller: DashboardController | None = None,
    *,
    web_origins: list[str] | tuple[str, ...] | None = None,
    companion_token: str | None = None,
    require_mutation_token: bool | None = None,
) -> Any:
    try:
        from fastapi import Body, FastAPI, HTTPException, Request
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import JSONResponse
        from fastapi.responses import RedirectResponse
        from fastapi.staticfiles import StaticFiles
    except ImportError as exc:
        raise RuntimeError("Install the web extra to run the dashboard: pip install -e .[web]") from exc

    controller = controller or DashboardController()
    security = CompanionSecurity.from_environment(
        token=companion_token,
        require_mutation_token=require_mutation_token,
    )
    app = FastAPI(title="PPS Local Dashboard", docs_url=None, redoc_url=None)
    app.state.companion_security = security
    configured_origins = DEFAULT_WEB_ORIGINS if web_origins is None else web_origins
    origins = [origin.rstrip("/") for origin in configured_origins if origin]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", TOKEN_HEADER],
            allow_credentials=False,
        )
    dashboard_dir = files("peripersonal_space_toolkit.dashboard")
    viewer_dir = files("peripersonal_space_toolkit.viewer")

    @app.get("/")
    def index() -> Any:
        return RedirectResponse(url="/dashboard/index.html")

    app.mount("/dashboard", StaticFiles(directory=str(dashboard_dir)), name="dashboard")
    app.mount("/viewer", StaticFiles(directory=str(viewer_dir)), name="viewer")
    _ensure_dir(controller.preview_dir)
    app.mount("/api/trial-row-previews", StaticFiles(directory=str(controller.preview_dir)), name="trial_row_previews")

    @app.middleware("http")
    async def companion_security_middleware(request: Request, call_next: Any) -> Any:
        if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            accepted, reason = security.authorize_mutation(
                path=request.url.path,
                method=request.method.upper(),
                origin=request.headers.get("origin", ""),
                supplied_token=request.headers.get(TOKEN_HEADER, ""),
            )
            if not accepted:
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "Local companion mutation token is missing or invalid.",
                        "reason": reason,
                        "token_header": TOKEN_HEADER,
                    },
                )
        return await call_next(request)

    @app.get("/api/state")
    def api_state() -> dict[str, Any]:
        return controller.snapshot()

    @app.get("/api/health")
    def api_health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "pps-dashboard-companion",
            "local_only": True,
            "render_dir": str(controller.render_dir),
            "session_root": str(controller.session_root),
            "project_registry_root": str(controller.project_registry_root),
            "security": security.public_status(),
        }

    @app.get("/api/templates")
    def api_templates() -> list[dict[str, Any]]:
        return controller.templates_payload()

    @app.get("/api/preloads")
    def api_preloads() -> dict[str, Any]:
        return controller.preload_inventory_payload()

    @app.get("/api/profile-catalog")
    def api_profile_catalog() -> dict[str, Any]:
        return controller.profile_catalog_payload()

    @app.post("/api/preloads/{template_id}/sync")
    def api_sync_preload(template_id: str) -> dict[str, Any]:
        return controller.sync_preload_assets(template_id)

    @app.post("/api/templates/{template_id}/load")
    def api_load_template(template_id: str) -> dict[str, Any]:
        try:
            return controller.load_template(template_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Template not found: {template_id}") from exc

    @app.post("/api/project/customize")
    def api_customize_project(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        try:
            return controller.customize_as_new_project(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/data-acquisition/export")
    def api_export_data_acquisition_folder(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        try:
            return controller.export_data_acquisition_folder(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/profiles/save-prepared")
    def api_save_prepared_profile(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        try:
            return controller.save_prepared_study_profile(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/projects/{project_id}/load")
    def api_load_custom_project(project_id: str) -> dict[str, Any]:
        try:
            return controller.load_custom_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Custom project not found: {project_id}") from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/design")
    def api_design(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        try:
            return controller.update_design(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/render")
    def api_render(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        try:
            job = controller.start_render_job(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _job_to_dict(job)

    @app.post("/api/stimulus/bake")
    def api_bake_stimulus(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        try:
            job = controller.start_bake_stimulus_job(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _job_to_dict(job)

    @app.post("/api/block-csv/accept")
    def api_accept_block_csv(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        try:
            return controller.accept_block_csv_preview(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/block-csv/edit")
    def api_edit_block_csv() -> dict[str, Any]:
        try:
            return controller.edit_block_csv_preview()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/run-sequence/preview")
    def api_preview_run_sequence(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        try:
            return controller.preview_run_sequence(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/run-sequence/regenerate")
    def api_regenerate_run_sequence(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        try:
            return controller.regenerate_run_sequence(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/run-sequence/prepare")
    def api_prepare_run_sequence(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        try:
            return controller.prepare_experiment_run_setup(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/run-sequence/export-bridge")
    def api_export_run_sequence_bridge(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        try:
            return controller.export_active_output_folder(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/run-sequence/open-runner")
    def api_open_experiment_runner(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        try:
            return controller.open_experiment_runner(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/session/prepare")
    def api_prepare(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        try:
            return controller.prepare_session(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/audio/stress")
    def api_audio_stress() -> dict[str, Any]:
        return _job_to_dict(controller.start_audio_stress_job())

    @app.post("/api/audio/import")
    def api_audio_import(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        try:
            return controller.import_audio_source(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/run-instructions/import")
    def api_run_instruction_import(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        try:
            return controller.import_run_instruction_audio(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/trials/preview-row")
    def api_preview_trial_row(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        try:
            return controller.preview_trial_strip_audio(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/audio/preview-source")
    def api_preview_source_audio(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        try:
            return controller.preview_source_audio(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/local/open-folder")
    def api_open_local_folder(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        try:
            return controller.open_local_folder(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/focus/start")
    def api_focus_start() -> dict[str, Any]:
        try:
            job = controller.start_focus_job()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _job_to_dict(job)

    @app.get("/api/jobs/{job_id}")
    def api_job(job_id: str) -> dict[str, Any]:
        job = controller.jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
        return _job_to_dict(job)

    return app


def trajectory_viewer_payload(design: StimulusDesign, *, preview_mode: str = "2d") -> dict[str, Any]:
    start, end = trajectory_endpoints_xyz(design.trajectory)
    start_spherical = cartesian_to_spherical(start["x_m"], start["y_m"], start["z_m"])
    end_spherical = cartesian_to_spherical(end["x_m"], end["y_m"], end["z_m"])
    radius_m = max(float(start_spherical["radius_m"]), float(end_spherical["radius_m"]), 0.1)
    source_trajectories = _viewer_source_trajectories(design)
    radius_m = max(radius_m, _viewer_source_radius_m(source_trajectories), 0.1)
    return {
        "preview_mode": preview_mode,
        "radius_m": radius_m,
        "path_length_m": float(design.trajectory.path_length_m),
        "movement_duration_s": float(design.trajectory.movement_duration_s),
        "start": start,
        "end": end,
        "source_trajectories": source_trajectories,
    }


def _viewer_source_trajectories(design: StimulusDesign) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for noise in design.noises:
        snapshot = dict(noise.trajectory_snapshot) or _stimulus_trajectory_snapshot(
            design,
            label=noise.label,
            source_kind="generated_noise",
            noise_type=noise.noise_type,
        )
        rows.append(_viewer_source_trajectory_row(
            label=noise.label,
            source_kind="generated_noise",
            tone_type=noise.noise_type,
            local_path=noise.prebaked_path,
            snapshot=snapshot,
        ))
    for asset in design.custom_looming_files:
        tone_type = asset.tone_type or _infer_tone_type(asset.label, default=CUSTOM_AUDIO_NOISE_TYPE)
        snapshot = dict(asset.trajectory_snapshot) or _stimulus_trajectory_snapshot(
            design,
            label=asset.label,
            source_kind="imported_audio",
            noise_type=tone_type,
        )
        rows.append(_viewer_source_trajectory_row(
            label=asset.label,
            source_kind="imported_audio",
            tone_type=tone_type,
            local_path=asset.path,
            snapshot=snapshot,
        ))
    return rows


def _viewer_source_trajectory_row(
    *,
    label: str,
    source_kind: str,
    tone_type: str,
    local_path: str,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    start = dict(snapshot.get("start") or {})
    end = dict(snapshot.get("end") or {})
    return {
        "label": label,
        "source_kind": source_kind,
        "tone_type": tone_type,
        "color_hex": _source_color_hex(tone_type),
        "local_path": local_path,
        "trajectory_snapshot": snapshot,
        "start": start,
        "end": end,
        "path_length_m": snapshot.get("path_length_m"),
        "movement_duration_s": snapshot.get("movement_duration_s"),
    }


def _viewer_source_radius_m(rows: list[dict[str, Any]]) -> float:
    radii: list[float] = []
    for row in rows:
        for point in (row.get("start", {}), row.get("end", {})):
            try:
                radii.append(math.sqrt(float(point["x_m"]) ** 2 + float(point["y_m"]) ** 2 + float(point["z_m"]) ** 2))
            except Exception:
                continue
    return max(radii, default=0.0)


def _source_color_hex(tone_type: str) -> str:
    return STIMULUS_TRAJECTORY_COLORS.get(str(tone_type or "").lower(), STIMULUS_TRAJECTORY_COLORS[CUSTOM_AUDIO_NOISE_TYPE])


def _infer_tone_type(label: str, *, default: str) -> str:
    text = str(label or "").lower()
    for tone_type in SUPPORTED_NOISE_TYPES:
        if tone_type in text:
            return tone_type
    return default


def _apply_trajectory_controls(design: StimulusDesign, controls: dict[str, Any]) -> StimulusDesign:
    updated = _copy_design(design)
    start_distance_cm = _float(controls.get("start_distance_cm"), updated.trajectory.start_radius_m * 100.0)
    end_distance_cm = _float(controls.get("end_distance_cm"), updated.trajectory.end_radius_m * 100.0)
    start_rotation_deg = _float(controls.get("start_rotation_deg"), azimuth_to_display_rotation_deg(updated.trajectory.azimuth_start_deg))
    end_rotation_deg = _float(controls.get("end_rotation_deg"), azimuth_to_display_rotation_deg(updated.trajectory.azimuth_end_deg))
    start_height_cm = _float(controls.get("start_height_cm"), 0.0)
    end_height_cm = _float(controls.get("end_height_cm"), 0.0)
    movement_duration_s = max(0.1, _float(controls.get("movement_duration_s"), updated.trajectory.movement_duration_s or 3.0))
    start_hold_s = max(0.0, _float(controls.get("start_hold_s"), updated.trajectory.padding_pre_s))
    end_hold_s = max(0.0, _float(controls.get("end_hold_s"), updated.trajectory.padding_post_s))
    start = point_from_distance_rotation_height(start_distance_cm, start_rotation_deg, start_height_cm)
    end = point_from_distance_rotation_height(end_distance_cm, end_rotation_deg, end_height_cm)
    path_length = math.dist((start["x_m"], start["y_m"], start["z_m"]), (end["x_m"], end["y_m"], end["z_m"]))
    updated.trajectory.coordinate_mode = "cartesian"
    updated.trajectory.path_direction = "custom"
    updated.trajectory.start_radius_m = start_distance_cm / 100.0
    updated.trajectory.end_radius_m = end_distance_cm / 100.0
    updated.trajectory.azimuth_start_deg = ((start_rotation_deg + 180.0) % 360.0) - 180.0
    updated.trajectory.azimuth_end_deg = ((end_rotation_deg + 180.0) % 360.0) - 180.0
    updated.trajectory.start_x_m = start["x_m"]
    updated.trajectory.start_y_m = start["y_m"]
    updated.trajectory.start_z_m = start["z_m"]
    updated.trajectory.end_x_m = end["x_m"]
    updated.trajectory.end_y_m = end["y_m"]
    updated.trajectory.end_z_m = end["z_m"]
    updated.trajectory.path_length_m = path_length
    updated.trajectory.propagation_speed_mps = path_length / movement_duration_s if movement_duration_s > 0 else 0.0
    updated.trajectory.padding_pre_s = start_hold_s
    updated.trajectory.padding_post_s = end_hold_s
    return updated


def _trajectory_controls(design: StimulusDesign) -> dict[str, float]:
    start, end = trajectory_endpoints_xyz(design.trajectory)
    start_spherical = cartesian_to_spherical(start["x_m"], start["y_m"], start["z_m"])
    end_spherical = cartesian_to_spherical(end["x_m"], end["y_m"], end["z_m"])
    return {
        "start_distance_cm": round(float(start_spherical["radius_m"]) * 100.0, 4),
        "end_distance_cm": round(float(end_spherical["radius_m"]) * 100.0, 4),
        "start_rotation_deg": round(azimuth_to_display_rotation_deg(float(start_spherical["azimuth_deg"])), 4),
        "end_rotation_deg": round(azimuth_to_display_rotation_deg(float(end_spherical["azimuth_deg"])), 4),
        "start_height_cm": round(float(start["z_m"]) * 100.0, 4),
        "end_height_cm": round(float(end["z_m"]) * 100.0, 4),
        "movement_duration_s": round(float(design.trajectory.movement_duration_s), 4),
        "start_hold_s": round(float(design.trajectory.padding_pre_s), 4),
        "end_hold_s": round(float(design.trajectory.padding_post_s), 4),
    }


def _trial_preview_rows(design: StimulusDesign, render_dir: Path | None = None) -> list[dict[str, Any]]:
    variant_lookup = _trial_sequence_variant_lookup(render_dir) if render_dir is not None else {}
    rows = []
    for row in block_trial_rows(design)[:TRIAL_PREVIEW_LIMIT]:
        key = (int(row.get("trial_strip_index") or 0), str(row.get("sequence_variant_key") or ""))
        variant_path = "" if str(row.get("trial_type") or "") == "Baseline" else variant_lookup.get(key, "")
        rows.append(
            {
                "block": row.get("block_label", ""),
                "trial": row.get("block_trial_index", ""),
                "type": row.get("trial_type", ""),
                "trial_type": row.get("trial_type_label", row.get("trial_strip_label", row.get("phase", ""))),
                "phase": row.get("trial_type_label", row.get("trial_strip_label", row.get("phase", ""))),
                "soa_ms": row.get("soa_ms", ""),
                "space_cm": row.get("spatial_value_cm", ""),
                "tactile_site": row.get("tactile_site", ""),
                "sequence": row.get("sequence_labels") or row.get("noise_label", row.get("noise_type", "")),
                "variant": row.get("sequence_variant_key", ""),
                "variant_path": variant_path,
            }
        )
    return rows


def _participant_orders(design: StimulusDesign) -> list[dict[str, Any]]:
    orders = participant_block_orders(design)
    return [{"participant": participant, "block_order": " -> ".join(blocks)} for participant, blocks in list(orders.items())[:80]]


def _render_status(render_dir: Path, design: StimulusDesign | None = None) -> dict[str, Any]:
    manifest_path = Path(render_dir) / "render_manifest.json"
    manifest = _load_json(manifest_path)
    wavs = available_stimulus_wavs(design, render_dir) if design is not None else rendered_wavs(render_dir)
    return {
        "render_dir": str(render_dir),
        "manifest_path": str(manifest_path),
        "manifest_exists": _path_exists(manifest_path),
        "status": manifest.get("status", "missing") if isinstance(manifest, dict) else "missing",
        "render_engine": manifest.get("render_engine", "") if isinstance(manifest, dict) else "",
        "wav_count": len(wavs),
        "wavs": [_json_ready(asdict(wav)) for wav in wavs],
    }


def _trial_strip_audio_preview(
    design: StimulusDesign,
    strip: Any,
    *,
    strip_index: int,
    render_dir: Path,
    preview_dir: Path,
) -> dict[str, Any]:
    chunks = _trial_strip_preview_chunks(design, strip, render_dir)
    if not chunks:
        raise ValueError("This event sequence has no playable audio elements.")
    _ensure_dir(preview_dir)
    preview_path = preview_dir / f"row_{strip_index + 1}_{_slug(strip.label or 'filmstrip')}_{uuid.uuid4().hex[:8]}.wav"
    duration_s = _write_trial_strip_preview_wav(preview_path, chunks)
    return {
        "url": f"/api/trial-row-previews/{preview_path.name}",
        "path": str(preview_path),
        "row_label": strip.label or f"Row {strip_index + 1}",
        "sequence": [chunk["label"] for chunk in chunks],
        "selected_source_label": next((chunk["label"] for chunk in chunks if chunk["kind"] == "looming_stimulus"), ""),
        "duration_s": duration_s,
        "local_only": True,
        "auditory_preview_only": True,
        "message": "Temporary browser-playable event-sequence preview assembled by the local companion backend.",
    }


def _source_audio_preview(
    design: StimulusDesign,
    label: str,
    *,
    render_dir: Path,
    preview_dir: Path,
) -> dict[str, Any]:
    chunk = _preview_chunk_for_source_label(design, label, render_dir)
    _ensure_dir(preview_dir)
    preview_path = preview_dir / f"source_{_slug(label)}_{uuid.uuid4().hex[:8]}.wav"
    duration_s = _write_trial_strip_preview_wav(preview_path, [chunk])
    return {
        "url": f"/api/trial-row-previews/{preview_path.name}",
        "path": str(preview_path),
        "label": label,
        "duration_s": duration_s,
        "local_only": True,
        "auditory_preview_only": True,
        "message": "Temporary browser-playable source preview served by the local companion backend.",
    }


def _preview_chunk_for_source_label(design: StimulusDesign, label: str, render_dir: Path) -> dict[str, Any]:
    fixed = {asset.label: asset for asset in design.prestimulus_files if asset.label.strip()}
    if label in fixed:
        asset = fixed[label]
        return {
            "kind": "fixed_audio",
            "label": asset.label,
            "path": _resolve_dashboard_local_path(asset.path),
            "gain": asset.gain * _instruction_loudness_gain(design),
            "loudness_role": "instruction_clip",
        }

    source_key = _source_key(label)
    source_assets = {asset.label: asset for asset in design.custom_looming_files if asset.label.strip()}
    source_meta = {str(source.get("label", "")): source for source in protocol_sound_sources(design)}
    source_wavs = _stimulus_wav_lookup(design, render_dir)
    if source_key not in source_wavs:
        raise ValueError(f"Bake or import Segment 1 audio before previewing this source: {label}")
    asset = source_assets.get(label)
    return {
        "kind": "looming_stimulus",
        "label": label,
        "path": source_wavs[source_key],
        "gain": asset.gain if asset is not None else float(source_meta.get(label, {}).get("gain") or 1.0),
    }


def _trial_strip_preview_chunks(design: StimulusDesign, strip: Any, render_dir: Path) -> list[dict[str, Any]]:
    fixed = {asset.label: asset for asset in design.prestimulus_files if asset.label.strip()}
    source_assets = {asset.label: asset for asset in design.custom_looming_files if asset.label.strip()}
    source_wavs = _stimulus_wav_lookup(design, render_dir)
    chunks: list[dict[str, Any]] = []
    for element in strip.elements:
        if element.kind == "fixed_audio":
            asset = fixed.get(element.source_label)
            if asset is None:
                raise ValueError(f"Event sequence references an unknown fixed clip: {element.source_label}")
            chunks.append(
                {
                    "kind": "fixed_audio",
                    "label": asset.label,
                    "path": _resolve_dashboard_local_path(asset.path),
                    "gain": asset.gain * _instruction_loudness_gain(design),
                    "loudness_role": "instruction_clip",
                }
            )
        elif element.kind == "looming_stimulus":
            labels = [label for label in element.source_labels if label] or list(source_wavs)
            playable = [(label, _source_key(label)) for label in labels if _source_key(label) in source_wavs]
            if not playable:
                raise ValueError("Bake or render at least one selected looming source before previewing this event sequence.")
            selected, selected_key = random.choice(playable)
            asset = source_assets.get(selected)
            chunks.append(
                {
                    "kind": "looming_stimulus",
                    "label": selected,
                    "path": source_wavs[selected_key],
                    "gain": asset.gain if asset is not None else 1.0,
                }
            )
        elif element.kind == "jitter":
            values = []
            for value in getattr(element, "jitter_values_ms", []) or []:
                try:
                    timing_ms = int(value)
                except (TypeError, ValueError):
                    continue
                if timing_ms >= 0:
                    values.append(timing_ms)
            selected_ms = random.choice(values) if values else 0
            chunks.append(
                {
                    "kind": "jitter",
                    "label": f"{element.label or 'Jitter'} ({selected_ms} ms)",
                    "duration_s": selected_ms / 1000.0,
                }
            )
    return chunks


def _stimulus_wav_lookup(design: StimulusDesign, render_dir: Path) -> dict[str, Path]:
    lookup: dict[str, Path] = {}
    for wav in available_stimulus_wavs(design, render_dir):
        keys = {
            wav.label,
            wav.path.stem,
            wav.path.name,
            wav.path.stem.replace("looming_", ""),
            _slug(wav.label).replace("_", " "),
        }
        for key in keys:
            normalized = _source_key(key)
            if normalized and normalized not in lookup:
                lookup[normalized] = wav.path
    return lookup


def _source_key(value: str) -> str:
    return str(value or "").replace("_", " ").replace("-", " ").strip().lower()


def _choose_local_directory(title: str) -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:
        raise RuntimeError("The local companion could not open a folder picker in this environment.") from exc
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(parent=root, title=title, mustexist=False)
    finally:
        root.destroy()
    return Path(selected).expanduser() if selected else None


def _experiment_identifier_for_diary(
    design: StimulusDesign,
    project: DashboardProjectContext | None = None,
) -> str:
    candidates = [
        "" if project is None else project.project_label,
        design.study_profile_title,
        design.name,
        design.study_profile_id,
    ]
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text:
            return text
    return "PPS experiment"


def _export_dashboard_project_to_acquisition_folder(project_dir: Path, acquisition_root: Path, project_id: str) -> Path:
    source = Path(project_dir).expanduser().resolve()
    root = Path(acquisition_root).expanduser().resolve()
    _ensure_dir(root)
    target = root / DASHBOARD_DESIGN_EXPORT_DIRNAME / _safe_filename(project_id or source.name)
    resolved_target = target.resolve()
    if source == resolved_target or source in resolved_target.parents:
        raise ValueError("Cannot export a dashboard project into one of its own subfolders.")
    if resolved_target in source.parents:
        raise ValueError("Cannot overwrite a parent folder of the active dashboard project.")
    if _path_exists(target):
        _remove_tree(target)
    copy_project_tree(source, target, ignore_patterns=("__pycache__", ".pytest_cache"))
    refresh_project_dependency_hashes(target)
    return target


def _resolve_dashboard_local_path(value: str | Path) -> Path:
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def _soundfile_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    text = str(resolved)
    if sys.platform == "win32" and not text.startswith("\\\\?\\"):
        return "\\\\?\\" + text
    return text


def _filesystem_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    text = str(resolved)
    if sys.platform == "win32" and not text.startswith("\\\\?\\"):
        if text.startswith("\\\\"):
            return "\\\\?\\UNC\\" + text.lstrip("\\")
        return "\\\\?\\" + text
    return text


def _path_exists(path: str | Path) -> bool:
    try:
        return os.path.exists(_filesystem_path(path))
    except OSError:
        return False


def _path_is_within(path: str | Path, root: str | Path) -> bool:
    try:
        target = Path(path).resolve()
        base = Path(root).resolve()
    except Exception:
        return False
    return target == base or base in target.parents


def _ensure_dir(path: str | Path) -> None:
    os.makedirs(_filesystem_path(path), exist_ok=True)


def _write_text_file(path: str | Path, content: str, *, encoding: str = "utf-8") -> None:
    target = Path(path)
    _ensure_dir(target.parent)
    with open(_filesystem_path(target), "w", encoding=encoding) as handle:
        handle.write(content)


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    _write_text_file(path, json.dumps(_json_ready(payload), indent=2) + "\n", encoding="utf-8")


def _write_bytes_file(path: str | Path, content: bytes) -> None:
    target = Path(path)
    _ensure_dir(target.parent)
    with open(_filesystem_path(target), "wb") as handle:
        handle.write(content)


def _read_text_file(path: str | Path, *, encoding: str = "utf-8") -> str:
    with open(_filesystem_path(path), "r", encoding=encoding) as handle:
        return handle.read()


def _remove_tree(path: str | Path) -> None:
    if _path_exists(path):
        shutil.rmtree(_filesystem_path(path))


def _move_file(source: str | Path, target: str | Path) -> None:
    _ensure_dir(Path(target).parent)
    shutil.move(_filesystem_path(source), _filesystem_path(target))


def _copy_file(source: str | Path, target: str | Path) -> None:
    _ensure_dir(Path(target).parent)
    shutil.copy2(_filesystem_path(source), _filesystem_path(target))


def _save_design_file(design: StimulusDesign, path: Path) -> None:
    _write_text_file(path, json.dumps(design_to_dict(design), indent=2), encoding="utf-8")


def _local_file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(_soundfile_path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_trial_strip_preview_wav(path: Path, chunks: list[dict[str, Any]]) -> float:
    try:
        import numpy as np
        import soundfile as sf
        from scipy import signal
    except ImportError as exc:
        raise RuntimeError("Install numpy, scipy, and soundfile to preview trial type rows.") from exc

    sample_rate = 0
    audio_chunks = []
    for chunk in chunks:
        if chunk.get("kind") == "jitter":
            if not sample_rate:
                sample_rate = 44100
            duration_s = max(0.0, float(chunk.get("duration_s", 0.0)))
            audio_chunks.append(np.zeros((int(round(duration_s * sample_rate)), 2), dtype=np.float32))
            continue
        source_path = Path(chunk["path"])
        if not _path_exists(source_path):
            raise FileNotFoundError(f"Preview audio file was not found: {source_path}")
        data, rate = sf.read(_soundfile_path(source_path), dtype="float32", always_2d=True)
        if data.shape[1] == 1:
            data = np.repeat(data, 2, axis=1)
        elif data.shape[1] > 2:
            data = data[:, :2]
        if not sample_rate:
            sample_rate = int(rate)
        elif int(rate) != sample_rate:
            divisor = math.gcd(sample_rate, int(rate))
            data = signal.resample_poly(data, sample_rate // divisor, int(rate) // divisor, axis=0)
        gain = max(0.0, float(chunk.get("gain", 1.0)))
        audio_chunks.append(data * gain)

    if not audio_chunks or not sample_rate:
        raise ValueError("No audio data was available for this event sequence.")
    preview = np.concatenate(audio_chunks, axis=0)
    peak = float(np.max(np.abs(preview))) if preview.size else 0.0
    if peak > 0.99:
        preview = preview / peak * 0.99
    sf.write(_soundfile_path(path), preview, sample_rate, subtype="PCM_16")
    return float(preview.shape[0] / sample_rate)


def _trial_sequence_bake_root(render_dir: Path) -> Path:
    return Path(render_dir) / "2_trial_sequence_designs"


def _legacy_trial_sequence_bake_root(render_dir: Path) -> Path:
    return Path(render_dir) / "3_trial_sequence__variant_bakes"


def _ingredient_lookup(render_dir: Path) -> dict[str, dict[str, Any]]:
    manifest = _load_ingredient_manifest(Path(render_dir))
    lookup: dict[str, dict[str, Any]] = {}
    for item in manifest.get("ingredients", []) if isinstance(manifest.get("ingredients"), list) else []:
        label = str(item.get("label") or "").strip()
        if label:
            lookup[label] = dict(item)
    return lookup


def _metadata_for_audio_choice(
    label: str,
    path: Path,
    *,
    kind: str,
    gain: float,
    ingredient: dict[str, Any] | None = None,
    loudness_role: str = "",
) -> dict[str, Any]:
    path = Path(path)
    if not _path_exists(path):
        raise FileNotFoundError(f"Audio source file was not found: {path}")
    info = _audio_file_info(path)
    digest = _local_file_sha256(path)
    if ingredient:
        expected_hash = str(ingredient.get("sha256") or "").strip()
        if expected_hash and expected_hash != digest:
            raise ValueError(f"Segment 1 source changed after it was registered: {label}")
        expected_duration = int(ingredient.get("duration_ms") or 0)
        if expected_duration and abs(expected_duration - int(info["duration_ms"])) > 1:
            raise ValueError(f"Segment 1 source duration changed after it was registered: {label}")
    motion_mode = "looming" if kind == "looming_stimulus" else "stationary"
    descriptor = str(ingredient.get("descriptor") or "") if ingredient else ""
    if not descriptor:
        descriptor = _ingredient_descriptor(label, int(info["duration_ms"]), motion_mode=motion_mode)
    return {
        "kind": kind,
        "label": label,
        "path": path,
        "gain": gain,
        "loudness_role": loudness_role,
        "descriptor": descriptor,
        "duration_ms": int(info["duration_ms"]),
        "sample_rate": int(info["sample_rate"]),
        "channels": int(info["channels"]),
        "sha256": digest,
    }


def _audio_source_choice_labels(element: Any) -> list[str]:
    labels = [str(label).strip() for label in getattr(element, "source_labels", []) or [] if str(label).strip()]
    source_label = str(getattr(element, "source_label", "") or "").strip()
    if not labels and source_label:
        labels = [source_label]
    return list(dict.fromkeys(labels))


def _trial_variant_factors(design: StimulusDesign, strip: Any, render_dir: Path) -> list[list[dict[str, Any]]]:
    fixed = {asset.label: asset for asset in design.prestimulus_files if asset.label.strip()}
    source_assets = {asset.label: asset for asset in design.custom_looming_files if asset.label.strip()}
    source_wavs = _stimulus_wav_lookup(design, render_dir)
    source_meta = {str(source.get("label", "")): source for source in protocol_sound_sources(design)}
    ingredients = _ingredient_lookup(render_dir)
    factors: list[list[dict[str, Any]]] = []
    for element in getattr(strip, "elements", []) or []:
        if element.kind == "jitter":
            values = []
            for value in getattr(element, "jitter_values_ms", []) or []:
                try:
                    timing_ms = int(value)
                except (TypeError, ValueError):
                    continue
                if timing_ms >= 0:
                    values.append(timing_ms)
            if not values:
                return []
            factors.append([
                {"kind": "jitter", "label": element.label or "Jitter", "jitter_ms": value}
                for value in values
            ])
            continue
        labels = _audio_source_choice_labels(element)
        if element.kind == "looming_stimulus" and not labels:
            labels = list(source_meta)
        choices: list[dict[str, Any]] = []
        for label in labels:
            if label in fixed:
                asset = fixed[label]
                ingredient = ingredients.get(asset.label)
                choices.append(_metadata_for_audio_choice(
                    asset.label,
                    _resolve_dashboard_local_path(asset.path),
                    kind="fixed_audio",
                    gain=asset.gain * _instruction_loudness_gain(design),
                    ingredient=ingredient,
                    loudness_role="instruction_clip",
                ))
            else:
                key = _source_key(label)
                if key not in source_wavs:
                    continue
                asset = source_assets.get(label)
                ingredient = ingredients.get(label)
                choices.append(_metadata_for_audio_choice(
                    label,
                    source_wavs[key],
                    kind="looming_stimulus",
                    gain=asset.gain if asset is not None else float(source_meta.get(label, {}).get("gain") or 1.0),
                    ingredient=ingredient,
                    loudness_role="looming_stimulus",
                ))
        if not choices:
            return []
        factors.append(choices)
    return factors


def _required_segment1_labels_for_trial_sequences(design: StimulusDesign) -> list[str]:
    labels: list[str] = []
    source_meta = {str(source.get("label", "")): source for source in protocol_sound_sources(design)}
    for strip in design.protocol.trial_strips:
        for element in getattr(strip, "elements", []) or []:
            if element.kind == "jitter":
                continue
            element_labels = _audio_source_choice_labels(element)
            if element.kind == "looming_stimulus" and not element_labels:
                element_labels = list(source_meta)
            labels.extend(label for label in element_labels if label)
    return list(dict.fromkeys(labels))


def _validate_segment1_references_for_trial_sequences(design: StimulusDesign, render_dir: Path) -> None:
    ingredients = _ingredient_lookup(render_dir)
    if not ingredients:
        raise ValueError("Segment 1 has no registered ingredients. Bake or import Segment 1 audio before baking Segment 2.")
    keyed = {_source_key(label): row for label, row in ingredients.items()}
    ingredient_errors = _validate_ingredient_rows(list(ingredients.values()))
    if ingredient_errors:
        raise ValueError(f"Segment 1 ingredient registry is not ready: {ingredient_errors[0]}")
    required_labels = _required_segment1_labels_for_trial_sequences(design)
    current_loudness_signature = json.dumps(_json_ready(loudness_policy_for_design(design)), sort_keys=True)
    stale_loudness = [
        label
        for label in required_labels
        for row in [ingredients.get(label)]
        if row is not None
        if json.dumps(_json_ready((row.get("provenance") or {}).get("loudness_policy")), sort_keys=True)
        != current_loudness_signature
    ]
    if stale_loudness:
        raise ValueError(
            "Segment 1 ingredients were baked/imported under a different loudness policy: "
            + ", ".join(stale_loudness[:6])
            + ("." if len(stale_loudness) <= 6 else ", ...")
        )
    missing = [
        label
        for label in required_labels
        if _source_key(label) not in keyed
    ]
    if missing:
        raise ValueError(f"Segment 2 references missing Segment 1 ingredients: {', '.join(missing)}.")


def _choice_slug(choice: dict[str, Any]) -> str:
    if choice.get("kind") == "jitter":
        return f"jitter{int(choice.get('jitter_ms') or 0)}ms"
    return _descriptor_label(str(choice.get("descriptor") or choice.get("label") or "audio"))


def _schedule_slug(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", str(value).strip()).strip("_").lower()
    return text or "item"


def _scheduler_variant_key(variant: tuple[dict[str, Any], ...]) -> str:
    parts: list[str] = []
    for choice in variant:
        if choice.get("kind") == "jitter":
            parts.append(f"jitter_{int(choice.get('jitter_ms') or 0)}ms")
        else:
            parts.append(str(choice.get("label") or "audio"))
    return _schedule_slug("_".join(parts) or "variant")


def _compact_slug_text(value: str, max_length: int) -> str:
    slug = _slug(value)
    if len(slug) <= max_length:
        return slug
    digest = hashlib.sha256(slug.encode("utf-8")).hexdigest()[:8]
    return f"{slug[:max(1, max_length - 9)].rstrip('_')}_{digest}"


def _dashboard_audio_stem(stage_prefix: str, label: str, *, max_label_length: int = 72) -> str:
    stage = _slug(stage_prefix)
    label_slug = _compact_slug_text(label or "audio", max_label_length)
    return _slug(f"{stage}__{label_slug}")


def _descriptor_label(value: str, default: str = "audio") -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "").strip()).strip("_").lower()
    return text or default


def _duration_ms_from_seconds(seconds: float) -> int:
    return max(0, int(round(float(seconds or 0.0) * 1000.0)))


def _duration_token(duration_ms: int, *, pad: int = 0) -> str:
    value = max(0, int(duration_ms))
    return f"{value:0{pad}d}ms" if pad else f"{value}ms"


def _audio_file_duration_ms(path: Path) -> int:
    import soundfile as sf

    info = sf.info(_soundfile_path(path))
    return _duration_ms_from_seconds(float(info.frames / info.samplerate) if info.samplerate else 0.0)


def _audio_file_info(path: Path) -> dict[str, Any]:
    import soundfile as sf

    info = sf.info(_soundfile_path(path))
    duration_ms = _duration_ms_from_seconds(float(info.frames / info.samplerate) if info.samplerate else 0.0)
    return {
        "duration_ms": duration_ms,
        "duration_s": round(duration_ms / 1000.0, 6),
        "sample_rate": int(info.samplerate),
        "channels": int(info.channels),
    }


def _materialize_run_instruction_audio_file(path: Path, target_dir: Path, *, slot: str, label: str) -> dict[str, Any]:
    import soundfile as sf
    import numpy as np

    source = Path(path)
    try:
        data, sample_rate = sf.read(_soundfile_path(source), dtype="float32", always_2d=True)
    except Exception as exc:
        raise ValueError(f"Could not decode instruction audio. Use WAV/MP3 audio that libsndfile can read: {exc}") from exc
    target_rate = 44100
    if int(sample_rate) != target_rate:
        try:
            from scipy import signal

            divisor = math.gcd(int(target_rate), int(sample_rate))
            data = signal.resample_poly(data, int(target_rate) // divisor, int(sample_rate) // divisor, axis=0)
            sample_rate = target_rate
        except Exception:
            pass
    data = np.ascontiguousarray(data, dtype=np.float32)
    duration_ms = _duration_ms_from_seconds(data.shape[0] / float(sample_rate or target_rate))
    stem = _descriptor_label(f"{slot}_{label}_{_duration_token(duration_ms)}", "instruction")
    target = _unique_output_path(target_dir, stem, ".wav")
    sf.write(_soundfile_path(target), data, int(sample_rate or target_rate), subtype="PCM_16")
    try:
        if source.name.startswith("_import_"):
            source.unlink()
    except OSError:
        pass
    info = _audio_file_info(target)
    return {
        "path": str(target),
        "duration_s": float(info["duration_s"]),
        "sample_rate": int(info["sample_rate"]),
        "channels": int(info["channels"]),
        "sha256": _local_file_sha256(target),
    }


def _ingredient_descriptor(label: str, duration_ms: int, *, motion_mode: str = "") -> str:
    base = _descriptor_label(label, "audio")
    mode = str(motion_mode or "").strip().lower()
    if mode == "looming" and "looming" not in base:
        base = f"{base}_looming"
    return f"{base}{_duration_token(duration_ms)}"


def _shorten_stem(stem: str, max_length: int = 160) -> str:
    if len(stem) <= max_length:
        return stem
    digest = hashlib.sha256(stem.encode("utf-8")).hexdigest()[:8]
    return f"{stem[:max(1, max_length - 9)].rstrip('_')}_{digest}"


def _unique_output_path(folder: Path, stem: str, suffix: str = ".wav") -> Path:
    _ensure_dir(folder)
    safe_stem = _shorten_stem(_descriptor_label(stem, "audio"), 96)
    suffix = suffix if suffix.startswith(".") else f".{suffix}"
    candidate = folder / f"{safe_stem}{suffix}"
    if not _path_exists(candidate):
        return candidate
    for index in range(2, 1000):
        candidate = folder / f"{safe_stem}__{index}{suffix}"
        if not _path_exists(candidate):
            return candidate
    raise RuntimeError(f"Could not choose a unique output filename in {folder}")


def _materialize_ingredient_audio_file(path: Path, target_dir: Path, label: str, *, motion_mode: str = "") -> Path:
    source = Path(path)
    duration_ms = _audio_file_duration_ms(source)
    stem = _ingredient_descriptor(label, duration_ms, motion_mode=motion_mode)
    target = _unique_output_path(target_dir, stem, source.suffix or ".wav")
    if source.resolve() == target.resolve():
        return source
    _move_file(source, target)
    return target


def _materialize_dashboard_audio_file(path: Path, stage_prefix: str, label: str) -> Path:
    source = Path(path)
    target = source.with_name(f"{_dashboard_audio_stem(stage_prefix, label)}{source.suffix or '.wav'}")
    if source.resolve() == target.resolve():
        return source
    _ensure_dir(target.parent)
    if _path_exists(target):
        os.unlink(_filesystem_path(target))
    _move_file(source, target)
    return target


def _rewrite_render_manifest_wav_path(manifest_path: Path, *, old_path: Path, new_path: Path) -> None:
    manifest_path = Path(manifest_path)
    if not _path_exists(manifest_path):
        return
    try:
        data = json.loads(_read_text_file(manifest_path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    old_text = str(Path(old_path))
    changed = False
    for item in data.get("wav_outputs", []) if isinstance(data.get("wav_outputs"), list) else []:
        if str(item.get("path") or "") == old_text:
            item["path"] = str(new_path)
            changed = True
    if changed:
        _write_text_file(manifest_path, json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _ingredient_manifest_path(project_or_dir: DashboardProjectContext | Path) -> Path:
    if isinstance(project_or_dir, DashboardProjectContext):
        return project_or_dir.segment1_dir / "stimulus_ingredients_manifest.json"
    return Path(project_or_dir) / "1_core_audio_ingredients" / "stimulus_ingredients_manifest.json"


def _load_ingredient_manifest(project_or_dir: DashboardProjectContext | Path) -> dict[str, Any]:
    path = _ingredient_manifest_path(project_or_dir)
    data = _load_json(path)
    if data.get("schema") == INGREDIENT_MANIFEST_SCHEMA:
        return data
    return {"schema": INGREDIENT_MANIFEST_SCHEMA, "ingredients": []}


def _record_ingredient_file(
    project: DashboardProjectContext,
    path: Path,
    *,
    label: str,
    source_kind: str,
    trajectory_snapshot: dict[str, Any] | None = None,
    motion_mode: str = "",
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    info = _audio_file_info(path)
    descriptor = _ingredient_descriptor(label, int(info["duration_ms"]), motion_mode=motion_mode)
    row = {
        "label": label,
        "descriptor": descriptor,
        "source_kind": source_kind,
        "motion_mode": motion_mode,
        "path": str(path),
        "duration_ms": int(info["duration_ms"]),
        "duration_s": info["duration_s"],
        "sample_rate": info["sample_rate"],
        "channels": info["channels"],
        "trajectory_snapshot": trajectory_snapshot or {},
        "provenance": provenance or {},
        "sha256": _local_file_sha256(path),
    }
    manifest = _load_ingredient_manifest(project)
    rows = [
        item
        for item in manifest.get("ingredients", [])
        if str(item.get("path") or "") != str(path)
        and not (
            str(item.get("descriptor") or "") == descriptor
            and str(item.get("sha256") or "") == row["sha256"]
        )
    ]
    rows.append(row)
    manifest = {
        "schema": INGREDIENT_MANIFEST_SCHEMA,
        "status": "ready",
        "root": str(project.segment1_dir),
        "ingredient_count": len(rows),
        "ingredients": rows,
    }
    path_manifest = _ingredient_manifest_path(project)
    _write_text_file(path_manifest, json.dumps(_json_ready(manifest), indent=2) + "\n", encoding="utf-8")
    return row


def _row_folder_name(row_index: int, row_label: str) -> str:
    label = _compact_slug_text(row_label or f"row_{row_index:02d}", 28)
    return _slug(f"row_{row_index:02d}__{label}")


def _variant_component_descriptor(variant: tuple[dict[str, Any], ...]) -> str:
    return "_".join(_choice_slug(choice) for choice in variant) or "sequence"


def _variant_name(row_index: int, variant_index: int, variant: tuple[dict[str, Any], ...], total_duration_ms: int) -> str:
    factors = "_".join(_choice_slug(choice) for choice in variant)
    factors = _shorten_stem(factors or f"variant_{variant_index:03d}", 84)
    return _descriptor_label(f"{factors}_total{_duration_token(total_duration_ms)}")


def _variant_chunks_from_choices(variant: tuple[dict[str, Any], ...], silence_dir: Path) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for choice in variant:
        if choice.get("kind") == "jitter":
            timing_ms = int(choice.get("jitter_ms") or 0)
            chunks.append({
                "kind": "jitter",
                "label": f"{choice.get('label') or 'Jitter'} ({timing_ms} ms)",
                "duration_s": timing_ms / 1000.0,
            })
        else:
            chunks.append({
                "kind": str(choice.get("kind") or "audio"),
                "label": str(choice.get("label") or "Audio"),
                "path": Path(choice["path"]),
                "gain": float(choice.get("gain") or 1.0),
                "loudness_role": str(choice.get("loudness_role") or ""),
                "descriptor": str(choice.get("descriptor") or ""),
                "sha256": str(choice.get("sha256") or ""),
                "duration_ms": int(choice.get("duration_ms") or 0),
            })
    return chunks


def _chunk_duration_s(chunk: dict[str, Any]) -> float:
    if chunk.get("kind") == "jitter":
        return max(0.0, float(chunk.get("duration_s") or 0.0))
    import soundfile as sf

    info = sf.info(_soundfile_path(Path(chunk["path"])))
    return float(info.frames / info.samplerate) if info.samplerate else 0.0


def _variant_segment_metadata(chunks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], float]:
    segments: list[dict[str, Any]] = []
    cursor_s = 0.0
    for index, chunk in enumerate(chunks, start=1):
        duration_s = _chunk_duration_s(chunk)
        kind = str(chunk.get("kind") or "audio")
        segment = {
            "index": index,
            "kind": kind,
            "source_kind": kind,
            "label": str(chunk.get("label") or ("Jitter" if kind == "jitter" else "Audio")),
            "descriptor": str(chunk.get("descriptor") or ""),
            "path": str(chunk.get("path") or ""),
            "gain": round(max(0.0, float(chunk.get("gain", 1.0))), 9),
            "loudness_role": str(chunk.get("loudness_role") or ""),
            "start_s": round(cursor_s, 6),
            "start_ms": _duration_ms_from_seconds(cursor_s),
            "duration_s": round(duration_s, 6),
            "duration_ms": _duration_ms_from_seconds(duration_s),
            "end_s": round(cursor_s + duration_s, 6),
            "end_ms": _duration_ms_from_seconds(cursor_s + duration_s),
            "is_looming_stimulus": kind == "looming_stimulus",
            "sha256": str(chunk.get("sha256") or ""),
        }
        segments.append(segment)
        cursor_s += duration_s
    return segments, cursor_s


def _write_silence_wav(path: Path, duration_s: float, sample_rate: int, channels: int) -> None:
    import numpy as np
    import soundfile as sf

    frames = max(0, int(round(duration_s * sample_rate)))
    _ensure_dir(path.parent)
    sf.write(_soundfile_path(path), np.zeros((frames, channels), dtype=np.float32), sample_rate, subtype="PCM_16")


def _ffmpeg_concat_lossless(segment_paths: list[Path], output_path: Path) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not segment_paths:
        return False
    digest = hashlib.sha256(str(output_path).encode("utf-8")).hexdigest()[:12]
    list_path = output_path.parent / f"concat_{digest}.txt"
    lines = []
    for path in segment_paths:
        escaped = str(path.resolve()).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    _write_text_file(list_path, "\n".join(lines) + "\n", encoding="utf-8")
    completed = subprocess.run(
        [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(output_path)],
        capture_output=True,
        text=True,
        check=False,
        **windows_no_console_kwargs(),
    )
    try:
        os.unlink(_filesystem_path(list_path))
    except OSError:
        pass
    return completed.returncode == 0 and _path_exists(output_path)


def _write_variant_wav_lossless(path: Path, chunks: list[dict[str, Any]], silence_dir: Path) -> float:
    import numpy as np
    import soundfile as sf
    from scipy import signal

    _ensure_dir(path.parent)
    _ensure_dir(silence_dir)
    segment_paths: list[Path] = []
    path_digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:10]
    sample_rate = 0
    target_channels = 2
    for chunk in chunks:
        if chunk.get("kind") == "jitter":
            continue
        source_path = Path(chunk["path"])
        if not _path_exists(source_path):
            raise FileNotFoundError(f"Trial-sequence source file was not found: {source_path}")
        info = sf.info(_soundfile_path(source_path))
        if not sample_rate:
            sample_rate = int(info.samplerate)
    if not sample_rate:
        sample_rate = 44100
    for index, chunk in enumerate(chunks, start=1):
        if chunk.get("kind") == "jitter":
            silence_path = silence_dir / f"seg_{index:02d}_{path_digest}_silence.wav"
            _write_silence_wav(silence_path, float(chunk.get("duration_s") or 0.0), sample_rate, target_channels)
            segment_paths.append(silence_path)
            continue
        source_path = Path(chunk["path"])
        info = sf.info(_soundfile_path(source_path))
        if int(info.samplerate) == sample_rate and int(info.channels) == target_channels and abs(float(chunk.get("gain", 1.0)) - 1.0) < 0.0001:
            segment_paths.append(source_path)
        else:
            data, rate = sf.read(_soundfile_path(source_path), dtype="float32", always_2d=True)
            if int(rate) != sample_rate:
                divisor = math.gcd(sample_rate, int(rate))
                data = signal.resample_poly(data, sample_rate // divisor, int(rate) // divisor, axis=0)
            if data.shape[1] == 1 and target_channels == 2:
                data = np.repeat(data, 2, axis=1)
            elif data.shape[1] < target_channels:
                pad = np.zeros((data.shape[0], target_channels - data.shape[1]), dtype=data.dtype)
                data = np.concatenate([data, pad], axis=1)
            elif data.shape[1] > target_channels:
                data = data[:, :target_channels]
            data = data * max(0.0, float(chunk.get("gain", 1.0)))
            segment_path = silence_dir / f"seg_{index:02d}_{path_digest}.wav"
            sf.write(_soundfile_path(segment_path), data, sample_rate, subtype="PCM_16")
            segment_paths.append(segment_path)
    if segment_paths and _ffmpeg_concat_lossless(segment_paths, path):
        info = sf.info(_soundfile_path(path))
        return float(info.frames / info.samplerate) if info.samplerate else 0.0
    audio_chunks = []
    for segment_path in segment_paths:
        data, rate = sf.read(_soundfile_path(segment_path), dtype="float32", always_2d=True)
        if int(rate) != sample_rate:
            divisor = math.gcd(sample_rate, int(rate))
            data = signal.resample_poly(data, sample_rate // divisor, int(rate) // divisor, axis=0)
        if data.shape[1] == 1 and target_channels == 2:
            data = np.repeat(data, 2, axis=1)
        elif data.shape[1] < target_channels:
            pad = np.zeros((data.shape[0], target_channels - data.shape[1]), dtype=data.dtype)
            data = np.concatenate([data, pad], axis=1)
        elif data.shape[1] > target_channels:
            data = data[:, :target_channels]
        audio_chunks.append(data)
    if not audio_chunks:
        raise ValueError("No audio segments were available for this trial-sequence variant.")
    combined = np.concatenate(audio_chunks, axis=0)
    peak = float(np.max(np.abs(combined))) if combined.size else 0.0
    if peak > 0.99:
        combined = combined / peak * 0.99
    sf.write(_soundfile_path(path), combined, sample_rate, subtype="PCM_16")
    return float(combined.shape[0] / sample_rate) if sample_rate else 0.0


def _bake_trial_sequence_variants(design: StimulusDesign, render_dir: Path) -> dict[str, Any]:
    rows = [strip for strip in design.protocol.trial_strips if strip.elements]
    root = _trial_sequence_bake_root(render_dir)
    if not rows:
        return {"status": "skipped", "variant_count": 0, "root": str(root), "rows": []}
    _validate_segment1_references_for_trial_sequences(design, render_dir)
    _remove_tree(root)
    _ensure_dir(root)
    try:
        manifest_rows: list[dict[str, Any]] = []
        row_summaries: list[dict[str, Any]] = []
        for row_index, strip in enumerate(rows, start=1):
            row_label = strip.label or f"Row {row_index}"
            row_slug = _row_folder_name(row_index, row_label)
            row_dir = root / row_slug
            _ensure_dir(row_dir)
            silence_dir = row_dir / "_segments"
            factors = _trial_variant_factors(design, strip, render_dir)
            variants = list(itertools.product(*factors)) if factors else []
            row_count = 0
            for variant_index, variant in enumerate(variants, start=1):
                scheduler_variant_key = _scheduler_variant_key(variant)
                chunks = _variant_chunks_from_choices(variant, silence_dir)
                segments, segment_total_s = _variant_segment_metadata(chunks)
                total_duration_ms = _duration_ms_from_seconds(segment_total_s)
                content_descriptor = _variant_component_descriptor(variant)
                variant_stem = _variant_name(row_index, variant_index, variant, total_duration_ms)
                wav_path = _unique_output_path(row_dir, variant_stem, ".wav")
                duration_s = _write_variant_wav_lossless(wav_path, chunks, silence_dir)
                duration_ms = _duration_ms_from_seconds(duration_s)
                sequence_labels = [str(choice.get("label") or "Audio") if choice.get("kind") != "jitter" else f"{choice.get('label') or 'Jitter'} ({int(choice.get('jitter_ms') or 0)} ms)" for choice in variant]
                source_labels = [str(choice.get("label") or "") for choice in variant if choice.get("kind") != "jitter"]
                jitter_values = [str(int(choice.get("jitter_ms") or 0)) for choice in variant if choice.get("kind") == "jitter"]
                looming_onset_s = next((float(segment["start_s"]) for segment in segments if segment["is_looming_stimulus"]), 0.0)
                digest = _local_file_sha256(wav_path)
                manifest_rows.append({
                    "row_index": row_index,
                    "row_id": strip.strip_id or f"strip-{row_index}",
                    "row_label": row_label,
                    "row_folder": str(row_dir),
                    "variant_index": variant_index,
                    "variant_key": variant_stem,
                    "sequence_variant_key": scheduler_variant_key,
                    "content_descriptor": content_descriptor,
                    "file_descriptor": wav_path.stem,
                    "file_path": str(wav_path),
                    "sequence_labels": " | ".join(sequence_labels),
                    "source_labels": "; ".join(source_labels),
                    "jitter_values_ms": "; ".join(jitter_values),
                    "duration_ms": duration_ms,
                    "duration_s": round(duration_s, 6),
                    "segment_duration_ms": total_duration_ms,
                    "segment_duration_s": round(segment_total_s, 6),
                    "looming_segment_onset_s": round(looming_onset_s, 6),
                    "looming_segment_onset_ms": _duration_ms_from_seconds(looming_onset_s),
                    "segments": segments,
                    "segments_json": json.dumps(segments, separators=(",", ":")),
                    "sha256": digest,
                })
                row_count += 1
            try:
                _remove_tree(silence_dir)
            except OSError:
                pass
            row_summaries.append({
                "row_index": row_index,
                "row_label": row_label,
                "row_folder": str(row_dir),
                "variant_count": row_count,
            })
        manifest = {
            "schema": "pps-trial-sequence-variants.v1",
            "status": "baked",
            "root": str(root),
            "design_signature": _segment2_design_signature(design),
            "loudness_policy": loudness_policy_for_design(design),
            "variant_count": len(manifest_rows),
            "rows": row_summaries,
            "variants": manifest_rows,
        }
        manifest_path = root / "trial_sequence_variants_manifest.json"
        errors = _validate_trial_sequence_manifest(manifest, design=design)
        if errors:
            raise ValueError(f"Segment 2 bake validation failed before manifest publish: {errors[0]}")
        _write_text_file(manifest_path, json.dumps(manifest, indent=2), encoding="utf-8")
        csv_path = root / "trial_sequence_variants_manifest.csv"
        if manifest_rows:
            with open(_filesystem_path(csv_path), "w", newline="", encoding="utf-8") as handle:
                csv_rows = [
                    {
                        **row,
                        "segments": row.get("segments_json", ""),
                    }
                    for row in manifest_rows
                ]
                writer = csv.DictWriter(handle, fieldnames=list(csv_rows[0]))
                writer.writeheader()
                writer.writerows(csv_rows)
        return {
            "status": "baked",
            "root": str(root),
            "manifest_path": str(manifest_path),
            "csv_path": str(csv_path),
            "variant_count": len(manifest_rows),
            "rows": row_summaries,
        }
    except Exception:
        _remove_tree(root)
        raise


def _trial_sequence_variant_lookup(render_dir: Path) -> dict[tuple[int, str], str]:
    manifest_path = _trial_sequence_bake_root(render_dir) / "trial_sequence_variants_manifest.json"
    if not _path_exists(manifest_path):
        manifest_path = _legacy_trial_sequence_bake_root(render_dir) / "trial_sequence_variants_manifest.json"
    try:
        data = json.loads(_read_text_file(manifest_path, encoding="utf-8"))
    except Exception:
        return {}
    lookup: dict[tuple[int, str], str] = {}
    for item in data.get("variants", []):
        try:
            row_index = int(item.get("row_index") or 0)
        except (TypeError, ValueError):
            continue
        keys = {
            str(item.get("variant_key") or "").strip(),
            str(item.get("sequence_variant_key") or "").strip(),
        }
        path = str(item.get("file_path") or "").strip()
        if row_index and path:
            for key in keys:
                if key:
                    lookup[(row_index, key)] = path
    return lookup


def _baseline_tactile_bake_root(render_dir: Path) -> Path:
    return Path(render_dir) / "3_tactile_and_baseline_trials"


def _legacy_baseline_tactile_bake_root(render_dir: Path) -> Path:
    return Path(render_dir) / "4_baseline_tactile_trial_design__trial_bakes"


def _trial_pool_root(render_dir: Path) -> Path:
    return Path(render_dir) / "4_trial_repetition_pool"


def _trial_pool_manifest_path(render_dir: Path) -> Path:
    return _trial_pool_root(render_dir) / "trial_repetition_pool_manifest.json"


def _trial_pool_csv_path(render_dir: Path) -> Path:
    return _trial_pool_root(render_dir) / "trial_repetition_pool.csv"


def _block_csv_preview_root(render_dir: Path) -> Path:
    return Path(render_dir) / "5_block_csv_preview"


def _block_csv_preview_manifest_path(render_dir: Path) -> Path:
    return _block_csv_preview_root(render_dir) / "block_csv_preview_manifest.json"


def _run_setup_root(render_dir: Path) -> Path:
    return Path(render_dir) / "6_experiment_run_setup"


def _run_setup_manifest_path(render_dir: Path) -> Path:
    return _run_setup_root(render_dir) / "experiment_run_setup_manifest.json"


def _run_setup_csv_path(render_dir: Path) -> Path:
    return _run_setup_root(render_dir) / "experiment_block_order.csv"


def _block_csv_final_path(csv_path: Path) -> Path:
    if csv_path.stem.endswith("_final"):
        return csv_path
    return csv_path.with_name(f"{csv_path.stem}_final{csv_path.suffix or '.csv'}")


def _block_csv_working_path(csv_path: Path, block_index: int) -> Path:
    if csv_path.stem.endswith("_final"):
        return csv_path.with_name(f"{csv_path.stem[:-6]}{csv_path.suffix or '.csv'}")
    if block_index > 0:
        return csv_path.with_name(f"block_{block_index:02d}{csv_path.suffix or '.csv'}")
    return csv_path


def _retarget_block_csv(block: dict[str, Any], csv_path: Path) -> None:
    block["csv_path"] = str(csv_path)
    block["csv_file_name"] = csv_path.name


def _finalize_block_csv_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    blocks = manifest.get("blocks", []) if isinstance(manifest.get("blocks"), list) else []
    operations: list[tuple[Path, Path, dict[str, Any]]] = []
    for block in blocks:
        csv_path = Path(str(block.get("csv_path") or ""))
        final_path = _block_csv_final_path(csv_path)
        if csv_path == final_path:
            continue
        if not _path_exists(csv_path):
            raise ValueError(f"Cannot finalize Segment 5 block CSV because it is missing: {csv_path.name}.")
        if _path_exists(final_path):
            raise ValueError(f"Cannot finalize Segment 5 block CSV because the final file already exists: {final_path.name}.")
        operations.append((csv_path, final_path, block))
    for source, target, block in operations:
        _move_file(source, target)
        _retarget_block_csv(block, target)
    return manifest


def _reopen_block_csv_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    blocks = manifest.get("blocks", []) if isinstance(manifest.get("blocks"), list) else []
    operations: list[tuple[Path, Path, dict[str, Any]]] = []
    for block in blocks:
        try:
            block_index = int(block.get("block_index") or 0)
        except (TypeError, ValueError):
            block_index = 0
        csv_path = Path(str(block.get("csv_path") or ""))
        working_path = _block_csv_working_path(csv_path, block_index)
        if csv_path == working_path:
            continue
        if not _path_exists(csv_path):
            raise ValueError(f"Cannot reopen Segment 5 block CSV because it is missing: {csv_path.name}.")
        if _path_exists(working_path):
            raise ValueError(f"Cannot reopen Segment 5 block CSV because the working file already exists: {working_path.name}.")
        operations.append((csv_path, working_path, block))
    for source, target, block in operations:
        _move_file(source, target)
        _retarget_block_csv(block, target)
    return manifest


def _run_setup_settings(design: StimulusDesign) -> dict[str, Any]:
    raw = design.study_profile_reference_parameters.get(RUN_SETUP_METADATA_KEY)
    settings = dict(raw) if isinstance(raw, dict) else {}
    default_structure = "pre_post" if str(design.study_profile_id or "") == DEFAULT_STUDY_TEMPLATE_ID else "single"
    structure = str(settings.get("experiment_structure") or default_structure).strip().lower()
    if structure not in EXPERIMENT_STRUCTURES:
        structure = "single"
    try:
        seed = int(settings.get("seed") or (int(design.protocol.random_seed or 20250604) + 6000))
    except (TypeError, ValueError):
        seed = int(design.protocol.random_seed or 20250604) + 6000
    return {
        "experiment_structure": structure,
        "seed": seed,
        "instruction_profile": _run_instruction_profile(design, settings.get("instruction_profile")),
    }


def _run_instruction_library_dir(project_dir: Path) -> Path:
    return _run_setup_root(project_dir) / "instruction_library"


def _default_run_instruction_slot(slot: str, *, study5: bool) -> dict[str, Any]:
    defaults = dict(STUDY5_RUN_INSTRUCTION_ASSETS.get(slot, {})) if study5 else {}
    path = str(defaults.get("path") or "")
    resolved = _resolve_dashboard_local_path(path) if path else Path()
    info: dict[str, Any] = {}
    sha256 = ""
    if path and _path_exists(resolved):
        try:
            info = _audio_file_info(resolved)
            sha256 = _local_file_sha256(resolved)
        except Exception:
            info = {}
    mode = str(defaults.get("continue_mode") or "click").strip().lower()
    if mode not in RUN_INSTRUCTION_CONTINUE_MODES:
        mode = "click"
    return {
        "slot": slot,
        "label": str(defaults.get("label") or RUN_INSTRUCTION_SLOT_LABELS.get(slot, slot.replace("_", " ").title())),
        "enabled": bool(path and _path_exists(resolved)),
        "required": False,
        "path": path,
        "duration_s": float(info.get("duration_s") or 0.0),
        "sample_rate": int(info.get("sample_rate") or 0),
        "channels": int(info.get("channels") or 0),
        "sha256": sha256,
        "continue_mode": mode,
        "delay_s": max(0.0, _float(defaults.get("delay_s"), 0.0)),
        "button_label": str(defaults.get("button_label") or "Continue"),
        "source": "original_study5" if study5 and path else "",
    }


def _normalize_run_instruction_profile(value: Any, *, design: StimulusDesign | None = None) -> dict[str, Any]:
    study5 = bool(design is not None and str(design.study_profile_id or "") == DEFAULT_STUDY_TEMPLATE_ID)
    incoming_slots: dict[str, dict[str, Any]] = {}
    if isinstance(value, dict):
        raw_slots = value.get("slots", [])
        if isinstance(raw_slots, dict):
            raw_slots = list(raw_slots.values())
        if isinstance(raw_slots, list):
            for item in raw_slots:
                if isinstance(item, dict) and str(item.get("slot") or "").strip():
                    incoming_slots[str(item.get("slot")).strip()] = dict(item)
    slots: list[dict[str, Any]] = []
    for slot in RUN_INSTRUCTION_SLOTS:
        merged = _default_run_instruction_slot(slot, study5=study5)
        if slot in incoming_slots:
            item = incoming_slots[slot]
            merged.update(
                {
                    key: item[key]
                    for key in (
                        "label",
                        "enabled",
                        "required",
                        "path",
                        "duration_s",
                        "sample_rate",
                        "channels",
                        "sha256",
                        "continue_mode",
                        "delay_s",
                        "button_label",
                        "source",
                    )
                    if key in item
                }
            )
        mode = str(merged.get("continue_mode") or "click").strip().lower()
        if mode not in RUN_INSTRUCTION_CONTINUE_MODES:
            mode = "click"
        merged["continue_mode"] = mode
        merged["enabled"] = bool(merged.get("enabled"))
        merged["required"] = False
        merged["delay_s"] = max(0.0, _float(merged.get("delay_s"), 0.0))
        merged["button_label"] = str(merged.get("button_label") or "Continue").strip() or "Continue"
        merged["slot"] = slot
        slots.append(merged)
    return {"schema": RUN_INSTRUCTION_PROFILE_SCHEMA, "slots": slots}


def _run_instruction_profile(design: StimulusDesign, value: Any | None = None) -> dict[str, Any]:
    if value is None:
        raw = design.study_profile_reference_parameters.get(RUN_SETUP_METADATA_KEY)
        value = raw.get("instruction_profile") if isinstance(raw, dict) else {}
    return _normalize_run_instruction_profile(value, design=design)


def _instruction_profile_signature(profile: dict[str, Any]) -> str:
    slots = []
    for item in profile.get("slots", []):
        if not isinstance(item, dict):
            continue
        slots.append(
            {
                "slot": item.get("slot", ""),
                "enabled": bool(item.get("enabled", False)),
                "path": str(item.get("path") or ""),
                "sha256": str(item.get("sha256") or ""),
                "continue_mode": str(item.get("continue_mode") or ""),
                "delay_s": max(0.0, _float(item.get("delay_s"), 0.0)),
                "button_label": str(item.get("button_label") or ""),
            }
        )
    return hashlib.sha256(json.dumps(slots, sort_keys=True).encode("utf-8")).hexdigest()


def _instruction_profile_warnings(profile: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    for item in profile.get("slots", []):
        if not isinstance(item, dict) or not bool(item.get("enabled")):
            continue
        label = str(item.get("label") or item.get("slot") or "Instruction").strip()
        path_text = str(item.get("path") or "").strip()
        if not path_text:
            warnings.append(f"Optional instruction clip '{label}' has no audio file and will be skipped.")
            continue
        if not _path_exists(_resolve_dashboard_local_path(path_text)):
            warnings.append(f"Optional instruction clip '{label}' was not found and will be skipped.")
    return warnings


def _set_run_setup_settings(design: StimulusDesign, settings: dict[str, Any]) -> None:
    current = _run_setup_settings(design)
    current.update(settings)
    structure = str(current.get("experiment_structure") or "single").strip().lower()
    if structure not in EXPERIMENT_STRUCTURES:
        structure = "single"
    try:
        seed = int(current.get("seed") or (int(design.protocol.random_seed or 20250604) + 6000))
    except (TypeError, ValueError):
        seed = int(design.protocol.random_seed or 20250604) + 6000
    design.study_profile_reference_parameters[RUN_SETUP_METADATA_KEY] = {
        "experiment_structure": structure,
        "seed": seed,
        "instruction_profile": _normalize_run_instruction_profile(
            current.get("instruction_profile"),
            design=design,
        ),
    }


def _apply_run_setup_payload(design: StimulusDesign, payload: Any) -> None:
    if not isinstance(payload, dict):
        _set_run_setup_settings(design, _run_setup_settings(design))
        return
    updates: dict[str, Any] = {}
    if "experiment_structure" in payload:
        updates["experiment_structure"] = payload.get("experiment_structure")
    if "seed" in payload:
        updates["seed"] = payload.get("seed")
    if "instruction_profile" in payload:
        updates["instruction_profile"] = payload.get("instruction_profile")
    _set_run_setup_settings(design, updates)


def _run_setup_phase_labels(structure: str) -> list[str]:
    return ["single"] if structure == "single" else ["pre", "post"]


def _run_setup_phase_title(phase: str) -> str:
    return {"single": "Single", "pre": "Condition 1", "post": "Condition 2"}.get(phase, phase.title())


def _block_order_permutations(blocks: list[dict[str, Any]], needed: int, seed: int) -> list[list[dict[str, Any]]]:
    if not blocks or needed <= 0:
        return []
    rng = random.Random(seed)
    block_count = len(blocks)
    if block_count <= 7:
        permutations = [list(order) for order in itertools.permutations(blocks)]
        rng.shuffle(permutations)
        return permutations[:needed] if len(permutations) >= needed else permutations
    seen: set[tuple[str, ...]] = set()
    orders: list[list[dict[str, Any]]] = []
    attempts = 0
    max_attempts = max(needed * 30, 200)
    while len(orders) < needed and attempts < max_attempts:
        order = list(blocks)
        rng.shuffle(order)
        key = tuple(str(block.get("csv_file_name") or block.get("block_label") or block.get("block_index")) for block in order)
        if key not in seen:
            seen.add(key)
            orders.append(order)
        attempts += 1
    while len(orders) < needed:
        shift = len(orders) % block_count
        order = blocks[shift:] + blocks[:shift]
        if (len(orders) // block_count) % 2:
            order = list(reversed(order))
        orders.append(list(order))
    return orders


def _run_setup_preview_rows(
    blocks: list[dict[str, Any]],
    *,
    participant_count: int,
    structure: str,
    seed: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    phases = _run_setup_phase_labels(structure)
    needed = participant_count * len(phases)
    orders = _block_order_permutations(blocks, needed, seed)
    summary_rows: list[dict[str, Any]] = []
    csv_rows: list[dict[str, Any]] = []
    order_index = 0
    for participant_index in range(1, participant_count + 1):
        participant_id = f"P{participant_index:03d}"
        participant_phase_orders: list[tuple[str, list[dict[str, Any]]]] = []
        for phase in phases:
            order = list(orders[order_index % len(orders)]) if orders else []
            if phase == "post" and participant_phase_orders and order == participant_phase_orders[-1][1] and len(orders) > 1:
                order_index += 1
                order = list(orders[order_index % len(orders)])
            participant_phase_orders.append((phase, order))
            order_index += 1
        for phase_index, (phase, order) in enumerate(participant_phase_orders, start=1):
            block_names = [str(block.get("csv_file_name") or block.get("block_label") or f"block_{idx:02d}.csv") for idx, block in enumerate(order, start=1)]
            summary_rows.append(
                {
                    "participant": participant_id,
                    "participant_index": participant_index,
                    "part": _run_setup_phase_title(phase),
                    "phase": phase,
                    "phase_index": phase_index,
                    "block_count": len(order),
                    "block_order": " -> ".join(block_names),
                }
            )
            for block_position, block in enumerate(order, start=1):
                csv_rows.append(
                    {
                        "participant_id": participant_id,
                        "participant_index": participant_index,
                        "experiment_structure": structure,
                        "phase": phase,
                        "phase_label": _run_setup_phase_title(phase),
                        "phase_index": phase_index,
                        "participant_block_position": block_position,
                        "source_block_index": int(block.get("block_index") or block_position),
                        "block_label": str(block.get("block_label") or f"Block {block_position:02d}"),
                        "block_csv_file": str(block.get("csv_file_name") or ""),
                        "block_csv_path": str(block.get("csv_path") or ""),
                        "trial_count": int(block.get("trial_count") or 0),
                        "duration_ms": int(block.get("duration_ms") or 0),
                        "sequence_seed": seed,
                    }
                )
    return summary_rows, csv_rows


def _run_setup_preview(project_dir: Path, design: StimulusDesign) -> dict[str, Any]:
    block_manifest_path = _block_csv_preview_manifest_path(project_dir)
    block_manifest = _load_json(block_manifest_path)
    block_errors = _validate_block_csv_preview_manifest(block_manifest, project_dir=project_dir, design=design)
    if block_errors:
        return {
            "status": "missing",
            "ready": False,
            "message": f"Accept Segment 5 block CSVs first: {block_errors[0]}",
            "rows": [],
            "csv_rows": [],
        }
    if not bool(block_manifest.get("accepted")):
        return {
            "status": "missing",
            "ready": False,
            "message": "Accept Segment 5 block CSVs before saving Segment 6.",
            "rows": [],
            "csv_rows": [],
        }
    settings = _run_setup_settings(design)
    structure = str(settings["experiment_structure"])
    seed = int(settings["seed"])
    instruction_profile = _normalize_run_instruction_profile(settings.get("instruction_profile"), design=design)
    loudness_policy = loudness_policy_for_design(design)
    participants = max(1, int(design.protocol.participants or 1))
    blocks = [dict(block) for block in block_manifest.get("blocks", [])]
    summary_rows, csv_rows = _run_setup_preview_rows(
        blocks,
        participant_count=participants,
        structure=structure,
        seed=seed,
    )
    manifest = _load_json(_run_setup_manifest_path(project_dir))
    manifest_errors = _validate_run_setup_manifest(manifest, project_dir=project_dir, design=design)
    prepared = bool(manifest) and not manifest_errors
    return {
        "status": "ready" if prepared else "preview",
        "ready": True,
        "prepared": prepared,
        "message": "Experiment block order prepared." if prepared else "Previewing experiment block order.",
        "experiment_structure": structure,
        "experiment_structure_label": "Single experiment" if structure == "single" else "Two-condition experiment",
        "participant_count": participants,
        "parts_per_participant": len(_run_setup_phase_labels(structure)),
        "blocks_per_part": len(blocks),
        "total_block_runs": len(csv_rows),
        "seed": seed,
        "instruction_profile": instruction_profile,
        "instruction_profile_signature": _instruction_profile_signature(instruction_profile),
        "instruction_profile_warnings": _instruction_profile_warnings(instruction_profile),
        "loudness_policy": loudness_policy,
        "source_segment5_manifest": str(block_manifest_path),
        "source_segment5_manifest_sha256": _local_file_sha256(block_manifest_path),
        "rows": summary_rows[:240],
        "csv_rows": csv_rows,
        "csv_path": str(_run_setup_csv_path(project_dir)),
        "manifest_path": str(_run_setup_manifest_path(project_dir)),
        "validation_errors": manifest_errors,
    }


def _trial_pool_folder_key(row: dict[str, Any]) -> str:
    folder_path = Path(str(row.get("row_folder") or ""))
    if folder_path.name:
        parent = folder_path.parent.name
        if parent and parent != ".":
            return _slug(f"{parent}__{folder_path.name}").lower()
        return _slug(folder_path.name).lower()
    family = str(row.get("family") or "trial_files").strip()
    row_label = str(row.get("row_label") or f"row_{int(row.get('row_index') or 0):02d}")
    return _slug(f"{row_label}__{family}").lower()


def _trial_pool_file_key(row: dict[str, Any]) -> str:
    path = str(row.get("file_path") or "").strip()
    if path:
        return hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]
    digest = str(row.get("sha256") or "").strip()
    family = str(row.get("family") or "trial").strip()
    soa = str(row.get("soa_ms") or "0").strip()
    variant = str(row.get("sequence_variant_key") or row.get("variant_key") or "").strip()
    return hashlib.sha256(f"{family}|{variant}|{soa}|{digest}".encode("utf-8")).hexdigest()[:16]


def _trial_pool_source_file_rows(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        path = str(item.get("file_path") or "").strip()
        row_folder = str(item.get("row_folder") or "").strip()
        folder_path = Path(row_folder) if row_folder else Path()
        row = {
            **item,
            "folder_key": _trial_pool_folder_key(item),
            "folder_name": folder_path.name if row_folder else _trial_pool_folder_key(item),
            "row_folder_name": folder_path.parent.name if row_folder and folder_path.parent.name != "." else "",
            "file_key": _trial_pool_file_key(item),
            "source_file_name": Path(path).name if path else "",
        }
        rows.append(row)
    return rows


def _trial_file_bake_status(render_dir: Path) -> dict[str, Any]:
    root = _baseline_tactile_bake_root(render_dir)
    manifest_path = root / "baseline_tactile_trial_files_manifest.json"
    if not _path_exists(manifest_path):
        root = _legacy_baseline_tactile_bake_root(render_dir)
        manifest_path = root / "baseline_tactile_trial_files_manifest.json"
    data = _load_json(manifest_path)
    files = data.get("files", []) if isinstance(data, dict) else []
    return {
        "root": str(root),
        "manifest_path": str(manifest_path),
        "manifest_exists": _path_exists(manifest_path),
        "schema": data.get("schema", "") if isinstance(data, dict) else "",
        "status": data.get("status", "missing") if isinstance(data, dict) else "missing",
        "audio_tactile_count": int(data.get("audio_tactile_count", 0) or 0) if isinstance(data, dict) else 0,
        "baseline_count": int(data.get("baseline_count", 0) or 0) if isinstance(data, dict) else 0,
        "catch_count": int(data.get("catch_count", 0) or 0) if isinstance(data, dict) else 0,
        "total_count": len(files),
        "rows": data.get("rows", []) if isinstance(data, dict) else [],
        "files": _trial_pool_source_file_rows(files),
        "manifest_sha256": _local_file_sha256(manifest_path) if _path_exists(manifest_path) else "",
    }


def _trial_sequence_bake_status(render_dir: Path) -> dict[str, Any]:
    root = _trial_sequence_bake_root(render_dir)
    manifest_path = root / "trial_sequence_variants_manifest.json"
    if not _path_exists(manifest_path):
        root = _legacy_trial_sequence_bake_root(render_dir)
        manifest_path = root / "trial_sequence_variants_manifest.json"
    data = _load_json(manifest_path)
    variants = data.get("variants", []) if isinstance(data, dict) else []
    return {
        "root": str(root),
        "manifest_path": str(manifest_path),
        "manifest_exists": _path_exists(manifest_path),
        "schema": data.get("schema", "") if isinstance(data, dict) else "",
        "status": data.get("status", "missing") if isinstance(data, dict) else "missing",
        "variant_count": len(variants),
        "rows": data.get("rows", []) if isinstance(data, dict) else [],
    }


def _project_segments_status(project: DashboardProjectContext, design: StimulusDesign) -> dict[str, Any]:
    segments = {
        "0_profile": _segment_status_profile(project),
        "1_core_audio_ingredients": _segment_status_ingredients(project),
        "2_trial_sequence_designs": _segment_status_trial_sequences(project.project_dir, design),
        "3_tactile_and_baseline_trials": _segment_status_tactile_trials(project.project_dir, design),
        "4_trial_repetition_pool": _segment_status_trial_pool(project.project_dir, design),
        "5_block_csv_preview": _segment_status_block_csv_preview(project.project_dir, design),
        "6_experiment_run_setup": _segment_status_run_setup(project.project_dir, design),
    }
    expected = _expected_segment_counts(design, project.project_dir)
    for key, value in segments.items():
        value["expected"] = expected.get(key, {})
    return segments


def _segment_status_record(
    *,
    index: int,
    folder_name: str,
    label: str,
    folder_path: Path,
    manifest_path: Path,
    status: str,
    message: str,
) -> dict[str, Any]:
    return {
        "segment": index,
        "folder_name": folder_name,
        "label": label,
        "folder_path": str(folder_path),
        "manifest_path": str(manifest_path),
        "manifest_exists": _path_exists(manifest_path),
        "folder_exists": _path_exists(folder_path),
        "wav_count": _count_files(folder_path, suffix=".wav"),
        "file_count": _count_files(folder_path),
        "status": status,
        "last_validation_message": message,
    }


def _segment_status_profile(project: DashboardProjectContext) -> dict[str, Any]:
    manifest_path = project.profile_dir / "project_manifest.json"
    active_design_path = project.profile_dir / "active_design.json"
    study_manifest_path = project.profile_dir / "study_manifest.json"
    missing = [path.name for path in (manifest_path, active_design_path, study_manifest_path) if not _path_exists(path)]
    status = "ready" if not missing else "missing"
    message = "Profile, study settings, and active design are ready." if not missing else f"Missing: {', '.join(missing)}."
    record = _segment_status_record(
        index=0,
        folder_name="0_profile",
        label="Study project registry",
        folder_path=project.profile_dir,
        manifest_path=manifest_path,
        status=status,
        message=message,
    )
    record["active_design_path"] = str(active_design_path)
    record["study_manifest_path"] = str(study_manifest_path)
    return record


def _segment_status_ingredients(project: DashboardProjectContext) -> dict[str, Any]:
    manifest_path = _ingredient_manifest_path(project)
    manifest = _load_ingredient_manifest(project)
    ingredients = manifest.get("ingredients", []) if isinstance(manifest.get("ingredients"), list) else []
    errors = _validate_ingredient_rows(ingredients)
    if not _path_exists(manifest_path) or not ingredients:
        status = "missing"
        message = "No Segment 1 ingredient manifest has been created yet."
    elif errors:
        status = "stale"
        message = errors[0]
    else:
        status = "ready"
        message = f"{len(ingredients)} Segment 1 ingredient WAVs are registered and validated."
    record = _segment_status_record(
        index=1,
        folder_name="1_core_audio_ingredients",
        label="Core audio ingredients",
        folder_path=project.segment1_dir,
        manifest_path=manifest_path,
        status=status,
        message=message,
    )
    record["ingredient_count"] = len(ingredients)
    record["validation_errors"] = errors
    return record


def _segment_status_trial_sequences(project_dir: Path, design: StimulusDesign | None = None) -> dict[str, Any]:
    root = _trial_sequence_bake_root(project_dir)
    manifest_path = root / "trial_sequence_variants_manifest.json"
    manifest = _load_json(manifest_path)
    variants = manifest.get("variants", []) if isinstance(manifest, dict) else []
    errors = _validate_trial_sequence_manifest(manifest, design=design)
    if not _path_exists(manifest_path):
        status = "missing"
        message = "Bake Segment 2 trial sequences before downstream trial files."
    elif errors:
        status = "stale"
        message = errors[0]
    else:
        status = "ready"
        message = f"{len(variants)} Segment 2 sequence variants are registered and validated."
    record = _segment_status_record(
        index=2,
        folder_name="2_trial_sequence_designs",
        label="Trial sequence designs",
        folder_path=root,
        manifest_path=manifest_path,
        status=status,
        message=message,
    )
    record["variant_count"] = len(variants)
    record["validation_errors"] = errors
    return record


def _segment_status_tactile_trials(project_dir: Path, design: StimulusDesign | None = None) -> dict[str, Any]:
    root = _baseline_tactile_bake_root(project_dir)
    manifest_path = root / "baseline_tactile_trial_files_manifest.json"
    manifest = _load_json(manifest_path)
    files = manifest.get("files", []) if isinstance(manifest, dict) else []
    errors = _validate_tactile_trial_manifest(manifest, design=design)
    if not _path_exists(manifest_path):
        status = "missing"
        message = "Bake Segment 3 baseline/tactile trial files after Segment 2 is ready."
    elif errors:
        status = "stale"
        message = errors[0]
    else:
        status = "ready"
        message = f"{len(files)} Segment 3 trial WAVs are registered and validated."
    record = _segment_status_record(
        index=3,
        folder_name="3_tactile_and_baseline_trials",
        label="Tactile and baseline trials",
        folder_path=root,
        manifest_path=manifest_path,
        status=status,
        message=message,
    )
    record["audio_tactile_count"] = int(manifest.get("audio_tactile_count", 0) or 0) if isinstance(manifest, dict) else 0
    record["baseline_count"] = int(manifest.get("baseline_count", 0) or 0) if isinstance(manifest, dict) else 0
    record["catch_count"] = int(manifest.get("catch_count", 0) or 0) if isinstance(manifest, dict) else 0
    record["total_count"] = len(files)
    record["validation_errors"] = errors
    return record


def _trial_pool_bake_status(project_dir: Path, design: StimulusDesign | None = None) -> dict[str, Any]:
    root = _trial_pool_root(project_dir)
    manifest_path = _trial_pool_manifest_path(project_dir)
    csv_path = _trial_pool_csv_path(project_dir)
    manifest = _load_json(manifest_path)
    errors = _validate_trial_pool_manifest(manifest, project_dir=project_dir, design=design)
    rows = manifest.get("folder_summaries", []) if isinstance(manifest, dict) else []
    return {
        "root": str(root),
        "manifest_path": str(manifest_path),
        "csv_path": str(csv_path),
        "manifest_exists": _path_exists(manifest_path),
        "csv_exists": _path_exists(csv_path),
        "schema": manifest.get("schema", "") if isinstance(manifest, dict) else "",
        "status": manifest.get("status", "missing") if isinstance(manifest, dict) else "missing",
        "source_segment3_manifest_sha256": str(manifest.get("source_segment3_manifest_sha256") or "") if isinstance(manifest, dict) else "",
        "total_count": int(manifest.get("total_trials", 0) or 0) if isinstance(manifest, dict) else 0,
        "unique_file_count": int(manifest.get("unique_file_count", 0) or 0) if isinstance(manifest, dict) else 0,
        "audio_tactile_count": int(manifest.get("family_counts", {}).get("audio_tactile", 0) or 0) if isinstance(manifest, dict) else 0,
        "baseline_count": int(manifest.get("family_counts", {}).get("baseline", 0) or 0) if isinstance(manifest, dict) else 0,
        "catch_count": int(manifest.get("family_counts", {}).get("catch", 0) or 0) if isinstance(manifest, dict) else 0,
        "estimated_total_duration_ms": int(manifest.get("estimated_total_duration_ms", 0) or 0) if isinstance(manifest, dict) else 0,
        "average_trial_duration_ms": float(manifest.get("average_trial_duration_ms", 0) or 0) if isinstance(manifest, dict) else 0,
        "longest_folder": manifest.get("longest_folder", {}) if isinstance(manifest, dict) else {},
        "folder_summaries": rows,
        "settings": manifest.get("settings", {}) if isinstance(manifest, dict) else {},
        "balancing_signature": str(manifest.get("balancing_signature") or "") if isinstance(manifest, dict) else "",
        "balance_warnings": manifest.get("balance_warnings", []) if isinstance(manifest, dict) else [],
        "validation_errors": errors,
    }


def _block_csv_preview_status(project_dir: Path, design: StimulusDesign | None = None) -> dict[str, Any]:
    root = _block_csv_preview_root(project_dir)
    manifest_path = _block_csv_preview_manifest_path(project_dir)
    manifest = _load_json(manifest_path)
    errors = _validate_block_csv_preview_manifest(manifest, project_dir=project_dir, design=design)
    blocks = manifest.get("blocks", []) if isinstance(manifest, dict) else []
    return {
        "root": str(root),
        "manifest_path": str(manifest_path),
        "manifest_exists": _path_exists(manifest_path),
        "schema": manifest.get("schema", "") if isinstance(manifest, dict) else "",
        "status": manifest.get("status", "missing") if isinstance(manifest, dict) else "missing",
        "accepted": bool(manifest.get("accepted")) if isinstance(manifest, dict) else False,
        "accepted_at": str(manifest.get("accepted_at") or "") if isinstance(manifest, dict) else "",
        "source_segment4_manifest_sha256": str(manifest.get("source_segment4_manifest_sha256") or "") if isinstance(manifest, dict) else "",
        "block_count": len(blocks),
        "total_count": int(manifest.get("total_trials", 0) or 0) if isinstance(manifest, dict) else 0,
        "estimated_total_duration_ms": int(manifest.get("estimated_total_duration_ms", 0) or 0) if isinstance(manifest, dict) else 0,
        "csv_columns": manifest.get("csv_columns", []) if isinstance(manifest, dict) else [],
        "blocks": blocks,
        "validation_errors": errors,
    }


def _segment_status_trial_pool(project_dir: Path, design: StimulusDesign | None = None) -> dict[str, Any]:
    root = _trial_pool_root(project_dir)
    manifest_path = _trial_pool_manifest_path(project_dir)
    manifest = _load_json(manifest_path)
    errors = _validate_trial_pool_manifest(manifest, project_dir=project_dir, design=design)
    if not _path_exists(manifest_path):
        status = "missing"
        message = "Bake Segment 4 trial repetition pool after Segment 3 is ready."
    elif errors:
        status = "stale"
        message = errors[0]
    else:
        status = "ready"
        message = f"{int(manifest.get('total_trials', 0) or 0)} Segment 4 trial-pool rows are registered."
    record = _segment_status_record(
        index=4,
        folder_name="4_trial_repetition_pool",
        label="Trial repetition pool",
        folder_path=root,
        manifest_path=manifest_path,
        status=status,
        message=message,
    )
    record["csv_path"] = str(_trial_pool_csv_path(project_dir))
    record["csv_exists"] = _path_exists(_trial_pool_csv_path(project_dir))
    record["total_count"] = int(manifest.get("total_trials", 0) or 0) if isinstance(manifest, dict) else 0
    record["unique_file_count"] = int(manifest.get("unique_file_count", 0) or 0) if isinstance(manifest, dict) else 0
    record["audio_tactile_count"] = int(manifest.get("family_counts", {}).get("audio_tactile", 0) or 0) if isinstance(manifest, dict) else 0
    record["baseline_count"] = int(manifest.get("family_counts", {}).get("baseline", 0) or 0) if isinstance(manifest, dict) else 0
    record["catch_count"] = int(manifest.get("family_counts", {}).get("catch", 0) or 0) if isinstance(manifest, dict) else 0
    record["estimated_total_duration_ms"] = int(manifest.get("estimated_total_duration_ms", 0) or 0) if isinstance(manifest, dict) else 0
    record["validation_errors"] = errors
    return record


def _segment_status_block_csv_preview(project_dir: Path, design: StimulusDesign | None = None) -> dict[str, Any]:
    root = _block_csv_preview_root(project_dir)
    manifest_path = _block_csv_preview_manifest_path(project_dir)
    manifest = _load_json(manifest_path)
    errors = _validate_block_csv_preview_manifest(manifest, project_dir=project_dir, design=design)
    blocks = manifest.get("blocks", []) if isinstance(manifest, dict) else []
    if not _path_exists(manifest_path):
        status = "missing"
        message = "Bake Segment 5 block CSVs after Segment 4 is ready."
    elif errors:
        status = "stale"
        message = errors[0]
    else:
        status = "ready"
        message = (
            f"{len(blocks)} Segment 5 block CSVs are accepted."
            if bool(manifest.get("accepted"))
            else f"{len(blocks)} Segment 5 block CSVs are registered; accept them to unlock Segment 6."
        )
    record = _segment_status_record(
        index=5,
        folder_name="5_block_csv_preview",
        label="Block CSV preview",
        folder_path=root,
        manifest_path=manifest_path,
        status=status,
        message=message,
    )
    record["csv_count"] = _count_files(root, suffix=".csv")
    record["block_count"] = len(blocks)
    record["total_count"] = int(manifest.get("total_trials", 0) or 0) if isinstance(manifest, dict) else 0
    record["accepted"] = bool(manifest.get("accepted")) if isinstance(manifest, dict) else False
    record["accepted_at"] = str(manifest.get("accepted_at") or "") if isinstance(manifest, dict) else ""
    record["validation_errors"] = errors
    return record


def _segment_status_run_setup(project_dir: Path, design: StimulusDesign | None = None) -> dict[str, Any]:
    root = _run_setup_root(project_dir)
    manifest_path = _run_setup_manifest_path(project_dir)
    manifest = _load_json(manifest_path)
    errors = _validate_run_setup_manifest(manifest, project_dir=project_dir, design=design)
    if not _path_exists(manifest_path):
        block_manifest = _load_json(_block_csv_preview_manifest_path(project_dir))
        if bool(block_manifest.get("accepted")):
            status = "preview"
            message = "Choose Segment 6 experiment-level parameters and prepare the block-order CSV."
        else:
            status = "missing"
            message = "Accept Segment 5 block CSVs before preparing Segment 6."
    elif errors:
        status = "stale"
        message = errors[0]
    else:
        status = "ready"
        message = f"{int(manifest.get('total_block_runs') or 0)} Segment 6 block-order rows are prepared."
    record = _segment_status_record(
        index=6,
        folder_name="6_experiment_run_setup",
        label="Prepare experiment",
        folder_path=root,
        manifest_path=manifest_path,
        status=status,
        message=message,
    )
    record["csv_path"] = str(_run_setup_csv_path(project_dir))
    record["csv_exists"] = _path_exists(_run_setup_csv_path(project_dir))
    record["participant_count"] = int(manifest.get("participant_count") or 0) if isinstance(manifest, dict) else 0
    record["total_block_runs"] = int(manifest.get("total_block_runs") or 0) if isinstance(manifest, dict) else 0
    record["experiment_structure"] = str(manifest.get("experiment_structure") or "") if isinstance(manifest, dict) else ""
    record["validation_errors"] = errors
    return record


def _count_files(folder: Path, *, suffix: str = "") -> int:
    if not _path_exists(folder):
        return 0
    count = 0
    suffix = suffix.lower()
    for _root, _dirs, files in os.walk(_filesystem_path(folder)):
        for filename in files:
            if not suffix or filename.lower().endswith(suffix):
                count += 1
    return count


def _validate_ingredient_rows(ingredients: list[Any]) -> list[str]:
    errors: list[str] = []
    for item in ingredients:
        if not isinstance(item, dict):
            errors.append("Segment 1 manifest contains a malformed ingredient row.")
            continue
        path = Path(str(item.get("path") or ""))
        label = str(item.get("label") or path.name or "ingredient")
        if not _path_exists(path):
            errors.append(f"Segment 1 ingredient is missing: {label}.")
            continue
        expected_hash = str(item.get("sha256") or "").strip()
        if expected_hash and expected_hash != _local_file_sha256(path):
            errors.append(f"Segment 1 ingredient hash changed after registration: {label}.")
        expected_duration = int(item.get("duration_ms") or 0)
        if expected_duration:
            actual_duration = _audio_file_duration_ms(path)
            if abs(expected_duration - actual_duration) > 1:
                errors.append(f"Segment 1 ingredient duration changed after registration: {label}.")
        expected_channels = int(item.get("channels") or 0)
        if expected_channels:
            actual_channels = int(_audio_file_info(path)["channels"])
            if expected_channels != actual_channels:
                errors.append(f"Segment 1 ingredient channel count changed after registration: {label}.")
    return errors


def _validate_trial_sequence_manifest(manifest: dict[str, Any], *, design: StimulusDesign | None = None) -> list[str]:
    if not manifest:
        return ["Segment 2 manifest is missing."]
    if manifest.get("schema") != "pps-trial-sequence-variants.v1":
        return ["Segment 2 manifest schema is not recognized."]
    if design is not None:
        expected_signature = _segment2_design_signature(design)
        manifest_signature = str(manifest.get("design_signature") or "")
        if manifest_signature and manifest_signature != expected_signature:
            return ["Segment 2 manifest is stale because the trial sequence design changed."]
    variants = manifest.get("variants", []) if isinstance(manifest.get("variants"), list) else []
    if not variants:
        return ["Segment 2 manifest does not contain any sequence variants."]
    errors: list[str] = []
    for variant in variants:
        if not isinstance(variant, dict):
            errors.append("Segment 2 manifest contains a malformed variant row.")
            continue
        try:
            _validate_trial_sequence_variant(variant)
        except Exception as exc:
            errors.append(str(exc))
            continue
        variant_path = Path(str(variant.get("file_path") or ""))
        variant_info = _audio_file_info(variant_path)
        if int(variant_info["channels"]) != 2:
            errors.append(f"Segment 2 sequence variant is not stereo/binaural audio: {variant_path.name}.")
        segments = _variant_segments(variant)
        if not segments:
            errors.append(f"Segment 2 variant has no component timing registry: {variant.get('variant_key') or variant.get('file_path')}.")
            continue
        for segment in segments:
            source_path_text = str(segment.get("path") or "").strip()
            if not source_path_text:
                continue
            source_path = Path(source_path_text)
            if not _path_exists(source_path):
                errors.append(f"Segment 2 source component is missing: {source_path.name}.")
                continue
            expected_hash = str(segment.get("sha256") or "").strip()
            if expected_hash and expected_hash != _local_file_sha256(source_path):
                errors.append(f"Segment 2 source component hash changed: {source_path.name}.")
            expected_duration = int(segment.get("duration_ms") or 0)
            if expected_duration and abs(expected_duration - _audio_file_duration_ms(source_path)) > 1:
                errors.append(f"Segment 2 source component duration changed: {source_path.name}.")
    return errors


def _validate_tactile_trial_manifest(manifest: dict[str, Any], *, design: StimulusDesign | None = None) -> list[str]:
    if not manifest:
        return ["Segment 3 manifest is missing."]
    if manifest.get("schema") != "pps-baseline-tactile-trials.v1":
        return ["Segment 3 manifest schema is not recognized."]
    if design is not None:
        expected_signature = _segment3_design_signature(design)
        manifest_signature = str(manifest.get("design_signature") or "")
        if manifest_signature and manifest_signature != expected_signature:
            return ["Segment 3 manifest is stale because SOA or baseline settings changed."]
    trial_sequence_manifest = Path(str(manifest.get("trial_sequence_manifest") or ""))
    expected_sequence_hash = str(manifest.get("trial_sequence_manifest_sha256") or "").strip()
    if expected_sequence_hash:
        if not _path_exists(trial_sequence_manifest):
            return ["Segment 3 manifest is stale because the Segment 2 manifest is missing."]
        if _local_file_sha256(trial_sequence_manifest) != expected_sequence_hash:
            return ["Segment 3 manifest is stale because Segment 2 was changed or re-baked."]
    files = manifest.get("files", []) if isinstance(manifest.get("files"), list) else []
    if not files:
        return ["Segment 3 manifest does not contain any trial files."]
    errors: list[str] = []
    for item in files:
        if not isinstance(item, dict):
            errors.append("Segment 3 manifest contains a malformed trial-file row.")
            continue
        path = Path(str(item.get("file_path") or ""))
        if not _path_exists(path):
            errors.append(f"Segment 3 trial file is missing: {path.name}.")
            continue
        expected_hash = str(item.get("sha256") or "").strip()
        if expected_hash and expected_hash != _local_file_sha256(path):
            errors.append(f"Segment 3 trial file hash changed: {path.name}.")
        info = _audio_file_info(path)
        family = str(item.get("family") or "").strip()
        if family == "catch":
            if int(info["channels"]) != 2:
                errors.append(f"Segment 3 catch trial file is not stereo/binaural audio-only: {path.name}.")
        elif int(info["channels"]) != 3:
            errors.append(f"Segment 3 tactile/baseline trial file is not 3-channel: {path.name}.")
        expected_duration = int(item.get("duration_ms") or 0)
        if expected_duration and abs(expected_duration - int(info["duration_ms"])) > 1:
            errors.append(f"Segment 3 trial file duration changed: {path.name}.")
        if family != "catch" and int(item.get("tactile_channel") or 0) != 3:
            errors.append(f"Segment 3 manifest does not mark channel 3 as tactile: {path.name}.")
    return errors


def _validate_trial_pool_manifest(
    manifest: dict[str, Any],
    *,
    project_dir: Path,
    design: StimulusDesign | None = None,
) -> list[str]:
    if not manifest:
        return ["Segment 4 manifest is missing."]
    if manifest.get("schema") != TRIAL_REPETITION_POOL_MANIFEST_SCHEMA:
        return ["Segment 4 manifest schema is not recognized."]
    source_manifest_path = _baseline_tactile_bake_root(project_dir) / "baseline_tactile_trial_files_manifest.json"
    source_manifest = _load_json(source_manifest_path)
    if not _path_exists(source_manifest_path):
        return ["Segment 4 manifest is stale because the Segment 3 manifest is missing."]
    source_errors = _validate_tactile_trial_manifest(source_manifest, design=design)
    if source_errors:
        return [f"Segment 4 manifest is stale because Segment 3 is not ready: {source_errors[0]}"]
    recorded_hash = str(manifest.get("source_segment3_manifest_sha256") or "").strip()
    if recorded_hash != _local_file_sha256(source_manifest_path):
        return ["Segment 4 manifest is stale because Segment 3 was changed or re-baked."]
    csv_path = Path(str(manifest.get("csv_path") or _trial_pool_csv_path(project_dir)))
    if not _path_exists(csv_path):
        return ["Segment 4 trial-pool CSV is missing."]
    if _count_files(_trial_pool_root(project_dir), suffix=".wav"):
        return ["Segment 4 must not duplicate WAV files; remove WAVs from the trial-pool folder."]
    if int(manifest.get("total_trials") or 0) <= 0:
        return ["Segment 4 trial-pool manifest does not contain any trial rows."]
    return []


def _validate_block_csv_preview_manifest(
    manifest: dict[str, Any],
    *,
    project_dir: Path,
    design: StimulusDesign | None = None,
) -> list[str]:
    if not manifest:
        return ["Segment 5 manifest is missing."]
    if manifest.get("schema") != BLOCK_CSV_PREVIEW_MANIFEST_SCHEMA:
        return ["Segment 5 manifest schema is not recognized."]
    source_manifest_path = _trial_pool_manifest_path(project_dir)
    source_manifest = _load_json(source_manifest_path)
    source_errors = _validate_trial_pool_manifest(source_manifest, project_dir=project_dir, design=design)
    if source_errors:
        return [f"Segment 5 manifest is stale because Segment 4 is not ready: {source_errors[0]}"]
    recorded_hash = str(manifest.get("source_segment4_manifest_sha256") or "").strip()
    if recorded_hash != _local_file_sha256(source_manifest_path):
        return ["Segment 5 manifest is stale because Segment 4 was changed or re-baked."]
    blocks = manifest.get("blocks", []) if isinstance(manifest.get("blocks"), list) else []
    if not blocks:
        return ["Segment 5 manifest does not contain any block CSVs."]
    total_rows = 0
    for block in blocks:
        csv_path = Path(str(block.get("csv_path") or ""))
        if not _path_exists(csv_path):
            return [f"Segment 5 block CSV is missing: {csv_path.name}."]
        try:
            with open(_filesystem_path(csv_path), encoding="utf-8") as handle:
                row_count = sum(1 for _row in csv.DictReader(handle))
        except Exception as exc:
            return [f"Segment 5 block CSV could not be read: {exc}"]
        expected = int(block.get("trial_count") or 0)
        if expected and row_count != expected:
            return [f"Segment 5 block CSV row count changed: {csv_path.name}."]
        total_rows += row_count
    if int(manifest.get("total_trials") or 0) != total_rows:
        return ["Segment 5 block CSV manifest total does not match the CSV rows."]
    return []


def _validate_run_setup_manifest(
    manifest: dict[str, Any],
    *,
    project_dir: Path,
    design: StimulusDesign | None = None,
) -> list[str]:
    if not manifest:
        return ["Segment 6 manifest is missing."]
    if manifest.get("schema") != RUN_SETUP_MANIFEST_SCHEMA:
        return ["Segment 6 manifest schema is not recognized."]
    block_manifest_path = _block_csv_preview_manifest_path(project_dir)
    block_manifest = _load_json(block_manifest_path)
    block_errors = _validate_block_csv_preview_manifest(block_manifest, project_dir=project_dir, design=design)
    if block_errors:
        return [f"Segment 6 manifest is stale because Segment 5 is not ready: {block_errors[0]}"]
    if not bool(block_manifest.get("accepted")):
        return ["Segment 6 manifest is stale because Segment 5 block CSVs are not accepted."]
    recorded_hash = str(manifest.get("source_segment5_manifest_sha256") or "").strip()
    if recorded_hash != _local_file_sha256(block_manifest_path):
        return ["Segment 6 manifest is stale because Segment 5 was changed."]
    settings = _run_setup_settings(design) if design is not None else {
        "experiment_structure": manifest.get("experiment_structure", "single"),
        "seed": manifest.get("seed", 0),
    }
    if str(manifest.get("experiment_structure") or "") != str(settings.get("experiment_structure") or ""):
        return ["Segment 6 manifest is stale because the experiment structure changed."]
    try:
        manifest_seed = int(manifest.get("seed") or 0)
        settings_seed = int(settings.get("seed") or 0)
    except (TypeError, ValueError):
        return ["Segment 6 manifest stores an invalid seed."]
    if manifest_seed != settings_seed:
        return ["Segment 6 manifest is stale because the block sequence seed changed."]
    expected_participants = max(1, int(getattr(design.protocol, "participants", 1) or 1)) if design is not None else int(manifest.get("participant_count") or 0)
    if int(manifest.get("participant_count") or 0) != expected_participants:
        return ["Segment 6 manifest is stale because the participant count changed."]
    if design is not None:
        expected_loudness = loudness_policy_for_design(design)
        recorded_loudness = manifest.get("loudness_policy")
        if json.dumps(_json_ready(recorded_loudness), sort_keys=True) != json.dumps(_json_ready(expected_loudness), sort_keys=True):
            return ["Segment 6 manifest is stale because the loudness policy changed."]
    csv_path = Path(str(manifest.get("csv_path") or _run_setup_csv_path(project_dir)))
    if not _path_exists(csv_path):
        return ["Segment 6 block-order CSV is missing."]
    rows = _read_csv_dict_rows(csv_path)
    if int(manifest.get("total_block_runs") or 0) != len(rows):
        return ["Segment 6 block-order CSV row count does not match the manifest."]
    return []


def _write_run_setup_outputs(project_dir: Path, design: StimulusDesign) -> dict[str, Any]:
    preview = _run_setup_preview(project_dir, design)
    if not preview.get("ready"):
        raise ValueError(str(preview.get("message") or "Segment 6 is not ready."))
    root = _run_setup_root(project_dir)
    _ensure_dir(root)
    csv_path = _run_setup_csv_path(project_dir)
    fieldnames = [
        "participant_id",
        "participant_index",
        "experiment_structure",
        "phase",
        "phase_label",
        "phase_index",
        "participant_block_position",
        "source_block_index",
        "block_label",
        "block_csv_file",
        "block_csv_path",
        "trial_count",
        "duration_ms",
        "sequence_seed",
    ]
    with open(_filesystem_path(csv_path), "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(preview["csv_rows"])
    manifest_path = _run_setup_manifest_path(project_dir)
    manifest = {
        "schema": RUN_SETUP_MANIFEST_SCHEMA,
        "status": "prepared",
        "prepared": True,
        "prepared_at": datetime.now().isoformat(timespec="seconds"),
        "root": str(root),
        "csv_path": str(csv_path),
        "experiment_structure": preview["experiment_structure"],
        "participant_count": preview["participant_count"],
        "parts_per_participant": preview["parts_per_participant"],
        "blocks_per_part": preview["blocks_per_part"],
        "total_block_runs": preview["total_block_runs"],
        "seed": preview["seed"],
        "instruction_profile": preview["instruction_profile"],
        "instruction_profile_signature": preview["instruction_profile_signature"],
        "instruction_profile_warnings": preview["instruction_profile_warnings"],
        "loudness_policy": preview["loudness_policy"],
        "source_segment5_manifest": preview["source_segment5_manifest"],
        "source_segment5_manifest_sha256": preview["source_segment5_manifest_sha256"],
        "summary_rows": preview["rows"],
    }
    errors = _validate_run_setup_manifest(manifest, project_dir=project_dir, design=design)
    if errors:
        if _path_exists(csv_path):
            Path(_filesystem_path(csv_path)).unlink()
        raise ValueError(f"Segment 6 prepare validation failed before manifest publish: {errors[0]}")
    _write_json(manifest_path, manifest)
    return {
        "status": "prepared",
        "root": str(root),
        "csv_path": str(csv_path),
        "manifest_path": str(manifest_path),
        "participant_count": preview["participant_count"],
        "parts_per_participant": preview["parts_per_participant"],
        "total_block_runs": preview["total_block_runs"],
        "instruction_profile": preview["instruction_profile"],
        "loudness_policy": preview["loudness_policy"],
        "rows": preview["rows"],
    }


def _expected_segment_counts(design: StimulusDesign, project_dir: Path) -> dict[str, dict[str, Any]]:
    segment2_manifest = _load_json(_trial_sequence_bake_root(project_dir) / "trial_sequence_variants_manifest.json")
    segment2_variants = segment2_manifest.get("variants", []) if isinstance(segment2_manifest, dict) else []
    variant_count = len(segment2_variants)
    if not variant_count:
        try:
            variant_count = sum(_estimated_trial_strip_variant_counts(design, project_dir))
        except Exception:
            variant_count = 0
    expected_audio_tactile = variant_count * len([value for value in design.protocol.soa_values_ms if isinstance(value, (int, float))])
    expected_baseline = variant_count * len(_baseline_anchor_specs(design))
    expected_catch = variant_count if bool(getattr(design.protocol, "include_catch_trials", False)) else 0
    segment3_manifest = _load_json(_baseline_tactile_bake_root(project_dir) / "baseline_tactile_trial_files_manifest.json")
    segment3_files = segment3_manifest.get("files", []) if isinstance(segment3_manifest, dict) else []
    expected_pool = 0
    if segment3_files:
        try:
            settings = _trial_pool_recipe_settings({"kind": "trial_repetition_pool"}, design)
            records, _warnings, _signature = _trial_pool_fractional_records(_trial_pool_source_file_rows(segment3_files), settings)
            expected_pool = sum(int(record["base_repetitions"]) + (1 if record["fractional_extra"] else 0) for record in records)
        except Exception:
            expected_pool = len(segment3_files) * max(1, int(getattr(design.protocol, "repetitions_per_condition", 1) or 1))
    segment4_manifest = _load_json(_trial_pool_manifest_path(project_dir))
    segment4_total = int(segment4_manifest.get("total_trials", 0) or 0) if isinstance(segment4_manifest, dict) else expected_pool
    expected_blocks = max(1, int(getattr(design.protocol, "blocks", 1) or 1))
    return {
        "0_profile": {"manifest_count": 3},
        "1_core_audio_ingredients": {
            "ingredient_count": len(design.noises) + len(design.custom_looming_files) + len(design.prestimulus_files),
        },
        "2_trial_sequence_designs": {
            "row_count": len([strip for strip in design.protocol.trial_strips if strip.elements]),
            "variant_count": variant_count,
        },
        "3_tactile_and_baseline_trials": {
            "audio_tactile_count": expected_audio_tactile,
            "baseline_count": expected_baseline,
            "catch_count": expected_catch,
            "total_count": expected_audio_tactile + expected_baseline + expected_catch,
        },
        "4_trial_repetition_pool": {
            "source_file_count": len(segment3_files),
            "trial_count": expected_pool,
        },
        "5_block_csv_preview": {
            "block_count": expected_blocks,
            "trial_count": segment4_total,
        },
    }


def _estimated_trial_strip_variant_counts(design: StimulusDesign, project_dir: Path) -> list[int]:
    counts: list[int] = []
    for strip in design.protocol.trial_strips:
        if not strip.elements:
            continue
        factors = _trial_variant_factors(design, strip, project_dir)
        total = 1
        for factor in factors:
            total *= len(factor)
        counts.append(total if factors else 0)
    return counts


def _write_segment_validation_report(
    project: DashboardProjectContext,
    design: StimulusDesign,
    expected: dict[str, Any] | None = None,
) -> Path:
    expected_counts = expected or _expected_segment_counts(design, project.project_dir)
    segments = _project_segments_status(project, design)
    checks: list[dict[str, Any]] = []
    for key, segment in segments.items():
        segment_expected = expected_counts.get(key, {}) if isinstance(expected_counts, dict) else {}
        checks.append({
            "id": key,
            "status": segment["status"],
            "expected": segment_expected,
            "observed": {
                "wav_count": segment.get("wav_count", 0),
                "file_count": segment.get("file_count", 0),
                "ingredient_count": segment.get("ingredient_count", 0),
                "variant_count": segment.get("variant_count", 0),
                "audio_tactile_count": segment.get("audio_tactile_count", 0),
                "baseline_count": segment.get("baseline_count", 0),
                "catch_count": segment.get("catch_count", 0),
                "block_count": segment.get("block_count", 0),
                "csv_count": segment.get("csv_count", 0),
                "total_count": segment.get("total_count", 0),
            },
            "message": segment.get("last_validation_message", ""),
        })
    report = {
        "schema": "pps-segment-validation-report.v1",
        "written_at": datetime.now().isoformat(timespec="seconds"),
        "project": project.to_dict(),
        "expected": expected_counts,
        "observed": segments,
        "checks": checks,
        "status": "ready" if all(check["status"] == "ready" for check in checks) else "incomplete",
    }
    path = project.profile_dir / "segment_validation_report.json"
    _write_text_file(path, json.dumps(_json_ready(report), indent=2) + "\n", encoding="utf-8")
    return path


def _load_trial_sequence_manifest(render_dir: Path) -> dict[str, Any]:
    manifest_path = _trial_sequence_bake_root(render_dir) / "trial_sequence_variants_manifest.json"
    data = _load_json(manifest_path)
    if data:
        return data
    return _load_json(_legacy_trial_sequence_bake_root(render_dir) / "trial_sequence_variants_manifest.json")


def _ensure_trial_sequence_manifest(design: StimulusDesign, render_dir: Path) -> dict[str, Any]:
    data = _load_trial_sequence_manifest(render_dir)
    variants = data.get("variants", []) if isinstance(data, dict) else []
    if not _path_exists(_trial_sequence_bake_root(render_dir) / "trial_sequence_variants_manifest.json"):
        raise ValueError("Bake Segment 2 trial sequences before baking Segment 3 baseline/tactile trial files.")
    if any("segments" not in item for item in variants):
        raise ValueError("Segment 2 manifest is stale: component timing metadata is missing. Re-bake Segment 2.")
    errors = _validate_trial_sequence_manifest(data, design=design)
    if errors:
        raise ValueError(f"Segment 2 manifest is not ready: {errors[0]}")
    if not variants:
        raise ValueError("Bake the trial sequence first or add at least one complete trial-sequence row.")
    return data


def _baseline_anchor_specs(design: StimulusDesign) -> list[dict[str, Any]]:
    protocol = design.protocol
    strategy = str(protocol.baseline_strategy or "").strip().lower()
    if not protocol.include_baseline_trials or strategy == "none":
        return []
    soas = [int(value) for value in protocol.soa_values_ms if isinstance(value, (int, float))]
    custom_soas = [int(value) for value in protocol.baseline_soa_values_ms if isinstance(value, (int, float))]
    mode = "audio_tactile" if protocol.baseline_custom_trial_mode == "audio_tactile" else "tactile_only"
    if strategy == "min_anchor":
        return [{"anchor_label": "minimum", "soa_ms": soas[0], "mode": "audio_tactile"}] if soas else []
    if strategy == "max_anchor":
        return [{"anchor_label": "maximum", "soa_ms": soas[-1], "mode": "audio_tactile"}] if soas else []
    if strategy == "min_max":
        if not soas:
            return []
        values = list(dict.fromkeys([soas[0], soas[-1]]))
        labels = ["minimum", "maximum"] if len(values) > 1 else ["minimum_maximum"]
        return [
            {"anchor_label": labels[index], "soa_ms": soa_ms, "mode": "audio_tactile"}
            for index, soa_ms in enumerate(values)
        ]
    if strategy == "tactile_only":
        return [
            {"anchor_label": f"full_soa_{soa_ms}ms", "soa_ms": soa_ms, "mode": "tactile_only"}
            for soa_ms in soas
        ]
    if strategy == "custom":
        return [
            {"anchor_label": f"custom_{soa_ms}ms", "soa_ms": soa_ms, "mode": mode}
            for soa_ms in custom_soas
        ]
    if strategy == "soa_zero":
        return [{"anchor_label": "legacy_sound_onset", "soa_ms": 0, "mode": "audio_tactile"}]
    if strategy == "sound_offset":
        soa_ms = int(round(max(0.0, design.trajectory.total_duration_s) * 1000.0))
        return [{"anchor_label": "legacy_sound_offset", "soa_ms": soa_ms, "mode": "audio_tactile"}]
    return []


def _trial_bake_row_folder_name(row_index: int, row_label: str) -> str:
    label = _compact_slug_text(row_label or f"trial_type_{row_index:02d}", 32)
    return _slug(f"row_{int(row_index or 0):02d}__{label}").lower()


def _trial_bake_output_folder_name(family: str, row_index: int, row_label: str) -> str:
    suffix = {
        "audio_tactile": "target_audio_tactile",
        "baseline": "baseline",
        "catch": "catch_trials",
    }.get(family, family or "trial_files")
    return str(Path(_trial_bake_row_folder_name(row_index, row_label)) / suffix)


def _compact_trial_segment_label(label: str, kind: str) -> str:
    tokens = [
        token
        for token in _descriptor_label(label or kind or "audio").split("_")
        if token and token not in {"audio", "clip", "instruction", "stimulus", "event", "source"}
    ]
    if not tokens:
        tokens = [_descriptor_label(kind or "audio")]
    if kind == "looming_stimulus":
        tokens = tokens[:2]
    else:
        tokens = tokens[:1]
    return "".join(tokens) or "audio"


def _compact_trial_content_descriptor(variant: dict[str, Any], *, max_length: int) -> str:
    segments = variant.get("segments")
    parts: list[str] = []
    if isinstance(segments, list):
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            kind = str(segment.get("kind") or segment.get("source_kind") or "audio")
            duration_ms = int(segment.get("duration_ms") or 0)
            if kind == "jitter":
                parts.append(f"jitter{_duration_token(duration_ms)}")
            else:
                label = _compact_trial_segment_label(str(segment.get("label") or ""), kind)
                parts.append(f"{label}{_duration_token(duration_ms)}")
    descriptor = "_".join(part for part in parts if part)
    if not descriptor:
        descriptor = str(variant.get("content_descriptor") or variant.get("file_descriptor") or variant.get("sequence_variant_key") or "trial")
    descriptor = _descriptor_label(descriptor.replace("_total", "_prevtotal"), "trial")
    return _shorten_stem(descriptor, max_length)


def _trial_bake_file_stem(
    *,
    family: str,
    variant: dict[str, Any],
    soa_ms: int,
    tactile_duration_ms: int,
    total_duration_ms: int,
    anchor_label: str = "",
    baseline_mode: str = "",
) -> str:
    if family == "baseline":
        mode = "silent" if baseline_mode == "tactile_only" else "audio"
        descriptor = _compact_trial_content_descriptor(variant, max_length=28)
        stem = f"baseline_{mode}_{descriptor}_soa{_duration_token(soa_ms)}_tac{_duration_token(tactile_duration_ms)}_total{_duration_token(total_duration_ms)}_ch3"
    elif family == "catch":
        descriptor = _compact_trial_content_descriptor(variant, max_length=40)
        stem = f"catch_{descriptor}_total{_duration_token(total_duration_ms)}_audio"
    else:
        descriptor = _compact_trial_content_descriptor(variant, max_length=36)
        stem = f"{descriptor}_soa{_duration_token(soa_ms)}_tac{_duration_token(tactile_duration_ms)}_total{_duration_token(total_duration_ms)}_ch3"
    return _descriptor_label(stem)


def _read_stereo_audio(path: Path, *, target_sample_rate: int = 0) -> tuple[Any, int]:
    import numpy as np
    import soundfile as sf
    from scipy import signal

    data, sample_rate = sf.read(_soundfile_path(path), dtype="float32", always_2d=True)
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    elif data.shape[1] > 2:
        data = data[:, :2]
    if target_sample_rate and int(sample_rate) != int(target_sample_rate):
        divisor = math.gcd(int(target_sample_rate), int(sample_rate))
        data = signal.resample_poly(data, int(target_sample_rate) // divisor, int(sample_rate) // divisor, axis=0)
        sample_rate = int(target_sample_rate)
    return data, int(sample_rate)


def _default_tactile_waveform(sample_rate: int) -> Any:
    import numpy as np

    duration_s = 0.1
    samples = max(1, int(round(duration_s * sample_rate)))
    t = np.arange(samples, dtype=float) / sample_rate
    attack_samples = max(1, min(samples, int(round(0.02 * sample_rate))))
    waveform = np.empty(samples, dtype=float)
    waveform[:attack_samples] = np.sin(2 * np.pi * 200.0 * t[:attack_samples])
    waveform[attack_samples:] = np.sin(2 * np.pi * 50.0 * t[attack_samples:])
    envelope = np.hanning(max(4, samples * 2))[:samples]
    if len(envelope) != samples:
        envelope = np.ones(samples, dtype=float)
    waveform *= envelope
    peak = float(np.max(np.abs(waveform)))
    if peak > 0:
        waveform = waveform / peak * 0.95
    return waveform.astype("float32")


def _load_tactile_cue(sample_rate: int) -> Any:
    import numpy as np
    import soundfile as sf
    from scipy import signal

    if not _path_exists(DEFAULT_TACTILE_CUE_PATH):
        raise FileNotFoundError(f"Shared tactile cue is missing: {DEFAULT_TACTILE_CUE_PATH}")
    data, rate = sf.read(_soundfile_path(DEFAULT_TACTILE_CUE_PATH), dtype="float32", always_2d=True)
    cue = data[:, 0]
    if int(rate) != int(sample_rate):
        divisor = math.gcd(int(sample_rate), int(rate))
        cue = signal.resample_poly(cue, int(sample_rate) // divisor, int(rate) // divisor)
    return cue.astype("float32")


def _tactile_cue_duration_ms(sample_rate: int) -> int:
    cue = _load_tactile_cue(sample_rate)
    return _duration_ms_from_seconds(len(cue) / float(sample_rate or 1))


def _tactile_channel(sample_rate: int, frames: int, tactile_onset_s: float) -> Any:
    import numpy as np

    channel = np.zeros(max(0, frames), dtype="float32")
    cue = _load_tactile_cue(sample_rate)
    start = int(round(float(tactile_onset_s) * sample_rate))
    cue_start = 0
    if start < 0:
        cue_start = min(len(cue), -start)
        start = 0
    if start >= len(channel) or cue_start >= len(cue):
        return channel
    end = min(len(channel), start + len(cue) - cue_start)
    if end > start:
        channel[start:end] += cue[cue_start: cue_start + (end - start)]
    peak = float(np.max(np.abs(channel))) if channel.size else 0.0
    if peak > 1.0:
        channel /= peak
    return channel


def _ffmpeg_merge_three_channel(source_stereo_path: Path, tactile_mono_path: Path, output_path: Path) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    completed = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source_stereo_path),
            "-i",
            str(tactile_mono_path),
            "-filter_complex",
            "[0:a][1:a]amerge=inputs=2[aout]",
            "-map",
            "[aout]",
            "-ac",
            "3",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        **windows_no_console_kwargs(),
    )
    return completed.returncode == 0 and _path_exists(output_path)


def _write_three_channel_trial_wav(output_path: Path, source_audio_path: Path, tactile_onset_s: float, work_dir: Path) -> tuple[float, str]:
    import numpy as np
    import soundfile as sf

    _ensure_dir(output_path.parent)
    _ensure_dir(work_dir)
    source_data, sample_rate = _read_stereo_audio(Path(source_audio_path))
    tactile = _tactile_channel(sample_rate, source_data.shape[0], tactile_onset_s)
    digest = hashlib.sha256(str(output_path).encode("utf-8")).hexdigest()[:12]
    source_stereo_path = work_dir / f"{digest}_source_stereo.wav"
    tactile_path = work_dir / f"{digest}_tactile.wav"
    sf.write(_soundfile_path(source_stereo_path), source_data, sample_rate, subtype="PCM_16")
    sf.write(_soundfile_path(tactile_path), tactile, sample_rate, subtype="PCM_16")
    if _ffmpeg_merge_three_channel(source_stereo_path, tactile_path, output_path):
        try:
            merged, _rate = sf.read(_soundfile_path(output_path), dtype="float32", always_2d=True)
            expected_tactile = float(np.max(np.abs(tactile))) if tactile.size else 0.0
            merged_tactile = float(np.max(np.abs(merged[:, 2]))) if merged.shape[1] > 2 else 0.0
            audio_diff = float(np.max(np.abs(merged[:, :2] - source_data))) if merged.shape[1] >= 2 else float("inf")
            tactile_diff = float(np.max(np.abs(merged[:, 2] - tactile))) if merged.shape[1] > 2 else float("inf")
            pcm_tolerance = 2.0 / 32768.0
            if (
                merged.shape[1] == 3
                and (expected_tactile <= 0.00001 or merged_tactile > 0.00001)
                and audio_diff <= pcm_tolerance
                and tactile_diff <= pcm_tolerance
            ):
                return float(source_data.shape[0] / sample_rate) if sample_rate else 0.0, "ffmpeg"
        except Exception:
            pass
    combined = np.column_stack([source_data, tactile])
    audio_peak = float(np.max(np.abs(combined[:, :2]))) if combined.size else 0.0
    if audio_peak > 0.99:
        combined[:, :2] = combined[:, :2] / audio_peak * 0.99
    tactile_peak = float(np.max(np.abs(combined[:, 2]))) if combined.size else 0.0
    if tactile_peak > 0.99:
        combined[:, 2] = combined[:, 2] / tactile_peak * 0.99
    sf.write(_soundfile_path(output_path), combined, sample_rate, subtype="PCM_16")
    return float(combined.shape[0] / sample_rate) if sample_rate else 0.0, "python_soundfile"


def _write_audio_from_segments(path: Path, segments: list[dict[str, Any]], *, silence_all_audio: bool) -> float:
    import numpy as np
    import soundfile as sf

    _ensure_dir(path.parent)
    chunks = []
    sample_rate = 0
    for segment in segments:
        duration_s = max(0.0, float(segment.get("duration_s") or 0.0))
        should_silence = silence_all_audio
        source_text = str(segment.get("path") or "").strip()
        source_path = Path(source_text) if source_text else Path()
        if source_text and _path_exists(source_path) and not should_silence:
            data, rate = _read_stereo_audio(source_path, target_sample_rate=sample_rate)
            if not sample_rate:
                sample_rate = rate
            chunks.append(data * max(0.0, float(segment.get("gain", 1.0))))
        else:
            if not sample_rate:
                sample_rate = 44100
            chunks.append(np.zeros((int(round(duration_s * sample_rate)), 2), dtype="float32"))
    if not chunks:
        raise ValueError("No segment audio was available for baseline reconstruction.")
    combined = np.concatenate(chunks, axis=0)
    sf.write(_soundfile_path(path), combined, sample_rate, subtype="PCM_16")
    return float(combined.shape[0] / sample_rate) if sample_rate else 0.0


def _variant_segments(item: dict[str, Any]) -> list[dict[str, Any]]:
    segments = item.get("segments")
    if isinstance(segments, list):
        return [dict(segment) for segment in segments if isinstance(segment, dict)]
    try:
        loaded = json.loads(str(item.get("segments_json") or "[]"))
    except json.JSONDecodeError:
        return []
    return [dict(segment) for segment in loaded if isinstance(segment, dict)]


def _validate_trial_sequence_variant(variant: dict[str, Any]) -> None:
    source_path = Path(str(variant.get("file_path") or ""))
    if not _path_exists(source_path):
        raise FileNotFoundError(f"Trial-sequence variant is missing: {source_path}")
    expected_hash = str(variant.get("sha256") or "").strip()
    if expected_hash and expected_hash != _local_file_sha256(source_path):
        raise ValueError(f"Segment 2 variant changed after it was registered: {source_path.name}")
    expected_duration = int(variant.get("duration_ms") or 0)
    if expected_duration:
        actual_duration = _audio_file_duration_ms(source_path)
        if abs(expected_duration - actual_duration) > 1:
            raise ValueError(f"Segment 2 variant duration changed after it was registered: {source_path.name}")


def _bake_audio_tactile_trial_files(design: StimulusDesign, render_dir: Path) -> dict[str, Any]:
    if not design.protocol.soa_values_ms:
        raise ValueError("Enter at least one SOA value before baking baseline/tactile trial files.")
    manifest = _ensure_trial_sequence_manifest(design, render_dir)
    variants = [dict(item) for item in manifest.get("variants", []) if isinstance(item, dict)]
    root = _baseline_tactile_bake_root(render_dir)
    _remove_tree(root)
    _ensure_dir(root)
    work_dir = root / "_work"
    file_rows: list[dict[str, Any]] = []
    row_summaries: dict[tuple[str, int, str], dict[str, Any]] = {}

    def record_row_summary(family: str, row_index: int, row_label: str, row_folder: Path) -> None:
        key = (family, row_index, str(row_folder))
        row_summaries.setdefault(
            key,
            {
                "family": family,
                "row_index": row_index,
                "row_label": row_label,
                "row_folder": str(row_folder),
                "file_count": 0,
            },
        )
        row_summaries[key]["file_count"] += 1

    def add_manifest_row(
        *,
        family: str,
        variant: dict[str, Any],
        soa_ms: int,
        anchor_label: str,
        baseline_mode: str,
        source_audio_path: Path,
        output_path: Path,
        duration_s: float,
        merge_engine: str,
        tactile_onset_s: float,
        row_folder: Path,
    ) -> None:
        digest = _local_file_sha256(output_path)
        output_info = _audio_file_info(output_path)
        tactile_duration_ms = 0 if family == "catch" else _tactile_cue_duration_ms(int(output_info["sample_rate"]))
        row_index = int(variant.get("row_index") or 0)
        row_label = str(variant.get("row_label") or f"Row {row_index}")
        channel_role_map = {
            "1": "left auditory/binaural",
            "2": "right auditory/binaural",
            "zero_based": {
                "0": "left auditory/binaural",
                "1": "right auditory/binaural",
            },
        } if family == "catch" else {
            "1": "left auditory/binaural",
            "2": "right auditory/binaural",
            "3": "tactile cue",
            "zero_based": {
                "0": "left auditory/binaural",
                "1": "right auditory/binaural",
                "2": "tactile cue",
            },
        }
        file_rows.append(
            {
                "family": family,
                "row_index": row_index,
                "row_id": str(variant.get("row_id") or ""),
                "row_label": row_label,
                "row_folder": str(row_folder),
                "variant_index": int(variant.get("variant_index") or 0),
                "variant_key": str(variant.get("variant_key") or ""),
                "sequence_variant_key": str(variant.get("sequence_variant_key") or ""),
                "source_variant_path": str(variant.get("file_path") or ""),
                "source_audio_path": str(source_audio_path),
                "file_path": str(output_path),
                "soa_ms": int(soa_ms),
                "baseline_anchor_label": anchor_label,
                "baseline_mode": baseline_mode,
                "looming_segment_onset_s": float(variant.get("looming_segment_onset_s") or 0.0),
                "tactile_onset_s": round(float(tactile_onset_s), 6),
                "sequence_labels": str(variant.get("sequence_labels") or ""),
                "source_labels": str(variant.get("source_labels") or ""),
                "jitter_values_ms": str(variant.get("jitter_values_ms") or ""),
                "duration_ms": int(output_info["duration_ms"]),
                "duration_s": round(duration_s, 6),
                "sample_rate_hz": int(output_info["sample_rate"]),
                "channels": int(output_info["channels"]),
                "channel_role_map": channel_role_map,
                "tactile_channel": "" if family == "catch" else 3,
                "tactile_channel_zero_based": "" if family == "catch" else 2,
                "tactile_duration_ms": tactile_duration_ms,
                "merge_engine": merge_engine,
                "tactile_cue_path": "" if family == "catch" else str(DEFAULT_TACTILE_CUE_PATH),
                "sha256": digest,
            }
        )
        record_row_summary(family, row_index, row_label, row_folder)

    try:
        soa_values = [int(value) for value in design.protocol.soa_values_ms]
        baseline_anchors = _baseline_anchor_specs(design)
        include_catch = bool(getattr(design.protocol, "include_catch_trials", False))
        for variant in variants:
            _validate_trial_sequence_variant(variant)
            row_index = int(variant.get("row_index") or 0)
            row_label = str(variant.get("row_label") or f"Row {row_index}")
            variant_index = int(variant.get("variant_index") or 0)
            variant_key = str(variant.get("variant_key") or f"variant_{variant_index:03d}")
            source_path = Path(str(variant.get("file_path") or ""))
            looming_onset_s = float(variant.get("looming_segment_onset_s") or 0.0)
            audio_folder = root / _trial_bake_output_folder_name("audio_tactile", row_index, row_label)
            _ensure_dir(audio_folder)
            if include_catch:
                source_info = _audio_file_info(source_path)
                output_stem = _trial_bake_file_stem(
                    family="catch",
                    variant=variant,
                    soa_ms=0,
                    tactile_duration_ms=0,
                    total_duration_ms=int(source_info["duration_ms"]),
                )
                catch_folder = root / _trial_bake_output_folder_name("catch", row_index, row_label)
                _ensure_dir(catch_folder)
                output_path = _unique_output_path(catch_folder, output_stem, ".wav")
                _copy_file(source_path, output_path)
                add_manifest_row(
                    family="catch",
                    variant=variant,
                    soa_ms=0,
                    anchor_label="",
                    baseline_mode="audio_only",
                    source_audio_path=source_path,
                    output_path=output_path,
                    duration_s=float(source_info["duration_s"]),
                    merge_engine="copy_segment2_audio",
                    tactile_onset_s=0.0,
                    row_folder=catch_folder,
                )
            for soa_ms in soa_values:
                tactile_onset_s = looming_onset_s + int(soa_ms) / 1000.0
                source_info = _audio_file_info(source_path)
                tactile_duration_ms = _tactile_cue_duration_ms(int(source_info["sample_rate"]))
                total_duration_ms = int(source_info["duration_ms"])
                output_stem = _trial_bake_file_stem(
                    family="audio_tactile",
                    variant=variant,
                    soa_ms=int(soa_ms),
                    tactile_duration_ms=tactile_duration_ms,
                    total_duration_ms=total_duration_ms,
                )
                output_path = _unique_output_path(audio_folder, output_stem, ".wav")
                duration_s, merge_engine = _write_three_channel_trial_wav(output_path, source_path, tactile_onset_s, work_dir)
                add_manifest_row(
                    family="audio_tactile",
                    variant=variant,
                    soa_ms=int(soa_ms),
                    anchor_label="",
                    baseline_mode="audio_tactile",
                    source_audio_path=source_path,
                    output_path=output_path,
                    duration_s=duration_s,
                    merge_engine=merge_engine,
                    tactile_onset_s=tactile_onset_s,
                    row_folder=audio_folder,
                )
            if baseline_anchors:
                segments = _variant_segments(variant)
                baseline_folder = root / _trial_bake_output_folder_name("baseline", row_index, row_label)
                _ensure_dir(baseline_folder)
                for anchor in baseline_anchors:
                    soa_ms = int(anchor["soa_ms"])
                    mode = str(anchor.get("mode") or "tactile_only")
                    anchor_label = str(anchor.get("anchor_label") or f"soa_{soa_ms}ms")
                    if mode == "audio_tactile":
                        baseline_source_path = source_path
                    else:
                        source_stem = _descriptor_label(f"baseline_source_{variant_key}_soa{soa_ms:04d}ms")
                        baseline_source_path = work_dir / f"{source_stem}.wav"
                        _write_audio_from_segments(baseline_source_path, segments, silence_all_audio=True)
                    tactile_onset_s = looming_onset_s + soa_ms / 1000.0
                    baseline_info = _audio_file_info(baseline_source_path)
                    tactile_duration_ms = _tactile_cue_duration_ms(int(baseline_info["sample_rate"]))
                    total_duration_ms = int(baseline_info["duration_ms"])
                    output_stem = _trial_bake_file_stem(
                        family="baseline",
                        variant=variant,
                        soa_ms=soa_ms,
                        tactile_duration_ms=tactile_duration_ms,
                        total_duration_ms=total_duration_ms,
                        anchor_label=anchor_label,
                        baseline_mode=mode,
                    )
                    output_path = _unique_output_path(baseline_folder, output_stem, ".wav")
                    duration_s, merge_engine = _write_three_channel_trial_wav(output_path, baseline_source_path, tactile_onset_s, work_dir)
                    add_manifest_row(
                        family="baseline",
                        variant=variant,
                        soa_ms=soa_ms,
                        anchor_label=anchor_label,
                        baseline_mode=mode,
                        source_audio_path=baseline_source_path,
                        output_path=output_path,
                        duration_s=duration_s,
                        merge_engine=merge_engine,
                        tactile_onset_s=tactile_onset_s,
                        row_folder=baseline_folder,
                    )
        try:
            _remove_tree(work_dir)
        except OSError:
            pass

        rows = list(row_summaries.values())
        trial_sequence_manifest_path = _trial_sequence_bake_root(render_dir) / "trial_sequence_variants_manifest.json"
        manifest_payload = {
            "schema": "pps-baseline-tactile-trials.v1",
            "status": "baked",
            "root": str(root),
            "design_signature": _segment3_design_signature(design),
            "trial_sequence_manifest": str(trial_sequence_manifest_path),
            "trial_sequence_manifest_sha256": _local_file_sha256(trial_sequence_manifest_path),
            "tactile_cue_path": str(DEFAULT_TACTILE_CUE_PATH),
            "loudness_policy": loudness_policy_for_design(design),
            "soa_values_ms": soa_values,
            "include_catch_trials": include_catch,
            "baseline_strategy": design.protocol.baseline_strategy,
            "baseline_custom_trial_mode": design.protocol.baseline_custom_trial_mode,
            "channel_role_map": {
                "1": "left auditory/binaural",
                "2": "right auditory/binaural",
                "3": "tactile cue",
                "zero_based": {
                    "0": "left auditory/binaural",
                    "1": "right auditory/binaural",
                    "2": "tactile cue",
                },
            },
            "audio_tactile_count": sum(1 for row in file_rows if row["family"] == "audio_tactile"),
            "baseline_count": sum(1 for row in file_rows if row["family"] == "baseline"),
            "catch_count": sum(1 for row in file_rows if row["family"] == "catch"),
            "rows": rows,
            "files": file_rows,
        }
        errors = _validate_tactile_trial_manifest(manifest_payload, design=design)
        if errors:
            raise ValueError(f"Segment 3 bake validation failed before manifest publish: {errors[0]}")
        manifest_path = root / "baseline_tactile_trial_files_manifest.json"
        _write_text_file(manifest_path, json.dumps(manifest_payload, indent=2), encoding="utf-8")
        csv_path = root / "baseline_tactile_trial_files_manifest.csv"
        if file_rows:
            with open(_filesystem_path(csv_path), "w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(file_rows[0]))
                writer.writeheader()
                writer.writerows(file_rows)
        return {
            "status": "baked",
            "root": str(root),
            "manifest_path": str(manifest_path),
            "csv_path": str(csv_path),
            "audio_tactile_count": manifest_payload["audio_tactile_count"],
            "baseline_count": manifest_payload["baseline_count"],
            "catch_count": manifest_payload["catch_count"],
            "total_count": len(file_rows),
            "rows": rows,
        }
    except Exception:
        _remove_tree(root)
        raise


def _as_repetition_count(value: Any, default: int = 1) -> int:
    try:
        parsed = int(round(float(value)))
    except (TypeError, ValueError):
        parsed = int(default)
    return max(0, min(parsed, 100000))


def _as_repetition_value(value: Any, *, default: float = 1.0, field_name: str = "repetitions") -> float:
    raw_value = default if value in (None, "") else value
    try:
        parsed = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a non-negative number in 0.5 increments.") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{field_name} must be finite.")
    if parsed < 0:
        raise ValueError(f"{field_name} cannot be negative.")
    if parsed > 100000:
        raise ValueError(f"{field_name} is implausibly large.")
    doubled = parsed * 2.0
    if abs(doubled - round(doubled)) > 1e-7:
        raise ValueError(f"{field_name} must use whole or half repetitions, such as 0, 0.5, 1, 1.5, or 3.")
    return round(round(doubled) / 2.0, 1)


def _json_repetition_value(value: float) -> float | int:
    value = _as_repetition_value(value, default=0.0)
    if abs(value - round(value)) < 1e-7:
        return int(round(value))
    return value


def _trial_pool_family_key(value: Any) -> str:
    key = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if key in {"audio", "target", "target_audio_tactile", "audio_tactile_trials"}:
        return "audio_tactile"
    if key in {"baseline_trials", "tactile_baseline", "tactile_only"}:
        return "baseline"
    if key in {"catch_trials", "audio_only"}:
        return "catch"
    return key


def _protocol_trial_pool_repetition_defaults(design: StimulusDesign) -> dict[str, Any]:
    raw_defaults = getattr(design.protocol, "trial_pool_repetition_defaults", {}) or {}
    if not isinstance(raw_defaults, dict):
        raw_defaults = {}
    default_value = _as_repetition_value(
        raw_defaults.get("default", getattr(design.protocol, "repetitions_per_condition", 1)),
        default=float(max(1, int(getattr(design.protocol, "repetitions_per_condition", 1) or 1))),
        field_name="protocol.trial_pool_repetition_defaults.default",
    )
    family_defaults: dict[str, float] = {}
    for raw_key, raw_value in raw_defaults.items():
        family = _trial_pool_family_key(raw_key)
        if family not in TRIAL_POOL_FAMILIES:
            continue
        family_defaults[family] = _as_repetition_value(
            raw_value,
            default=default_value,
            field_name=f"protocol.trial_pool_repetition_defaults.{family}",
        )
    return {
        "default_repetitions": default_value,
        "family_repetitions": family_defaults,
    }


def _trial_pool_recipe_settings(recipe: dict[str, Any], design: StimulusDesign) -> dict[str, Any]:
    payload = recipe.get("trial_pool") if isinstance(recipe.get("trial_pool"), dict) else recipe
    protocol_defaults = _protocol_trial_pool_repetition_defaults(design)
    explicit_default_repetitions = "default_repetitions" in payload or "repetitions" in payload
    default_repetitions = _as_repetition_value(
        payload.get("default_repetitions", payload.get("repetitions", protocol_defaults["default_repetitions"])),
        default=float(protocol_defaults["default_repetitions"]),
        field_name="default_repetitions",
    )
    family_raw = payload.get("family_repetitions")
    if not isinstance(family_raw, dict):
        family_raw = payload.get("family_repetition_defaults")
    if not isinstance(family_raw, dict):
        family_raw = {}
    family_repetitions = {} if explicit_default_repetitions and not family_raw else dict(protocol_defaults["family_repetitions"])
    for raw_key, raw_value in family_raw.items():
        family = _trial_pool_family_key(raw_key)
        if family not in TRIAL_POOL_FAMILIES:
            continue
        family_repetitions[family] = _as_repetition_value(
            raw_value,
            default=default_repetitions,
            field_name=f"family_repetitions.{family}",
        )
    folder_raw = payload.get("folder_repetitions") if isinstance(payload.get("folder_repetitions"), dict) else {}
    file_raw = payload.get("file_repetition_overrides") if isinstance(payload.get("file_repetition_overrides"), dict) else {}
    folder_repetitions = {
        str(key): _as_repetition_value(value, default=default_repetitions, field_name=f"folder_repetitions.{key}")
        for key, value in folder_raw.items()
        if str(key).strip()
    }
    file_repetition_overrides = {
        str(key): _as_repetition_value(value, default=default_repetitions, field_name=f"file_repetition_overrides.{key}")
        for key, value in file_raw.items()
        if str(key).strip()
    }
    try:
        fractional_seed = int(payload.get("fractional_seed", getattr(design.protocol, "random_seed", 20250604)) or 20250604)
    except (TypeError, ValueError):
        fractional_seed = 20250604
    return {
        "default_repetitions": _json_repetition_value(default_repetitions),
        "family_repetitions": {key: _json_repetition_value(value) for key, value in family_repetitions.items()},
        "folder_repetitions": {key: _json_repetition_value(value) for key, value in folder_repetitions.items()},
        "file_repetition_overrides": {key: _json_repetition_value(value) for key, value in file_repetition_overrides.items()},
        "fractional_seed": fractional_seed,
    }


def _family_label(family: str) -> str:
    return {
        "audio_tactile": "Audio-Tactile",
        "baseline": "Baseline",
        "catch": "Catch",
    }.get(str(family or "").strip(), str(family or "Trial"))


def _trial_pool_percentages(counts: dict[str, int], total: int) -> dict[str, float]:
    denominator = max(1, int(total))
    return {
        key: round(100.0 * int(counts.get(key, 0) or 0) / denominator, 2)
        for key in ("audio_tactile", "baseline", "catch")
    }


def _trial_pool_source_lineage_key(source: dict[str, Any]) -> str:
    labels = str(source.get("source_labels") or source.get("sequence_labels") or "").strip()
    if labels:
        pieces = [piece.strip() for piece in re.split(r"\s*\|\s*", labels) if piece.strip()]
        if pieces:
            return _slug(pieces[-1])
    return _slug(str(source.get("sequence_variant_key") or source.get("variant_key") or source.get("source_file_name") or source.get("file_key") or "source"))


def _trial_pool_subgroup_key(source: dict[str, Any]) -> str:
    label = str(source.get("row_label") or source.get("row_folder_name") or "").strip()
    return _slug(label or "row")


def _trial_pool_fractional_stratum(source: dict[str, Any], fractional_remainder: float) -> str:
    family = _trial_pool_family_key(source.get("family"))
    row_key = _trial_pool_subgroup_key(source)
    soa_ms = int(source.get("soa_ms") or 0)
    baseline_mode = _slug(str(source.get("baseline_mode") or "none"))
    return f"{family}|{row_key}|soa{soa_ms}|{baseline_mode}|frac{_json_repetition_value(fractional_remainder)}"


def _trial_pool_fractional_parent_stratum(source: dict[str, Any], fractional_remainder: float) -> str:
    family = _trial_pool_family_key(source.get("family"))
    row_key = _trial_pool_subgroup_key(source)
    baseline_mode = _slug(str(source.get("baseline_mode") or "none"))
    return f"{family}|{row_key}|{baseline_mode}|frac{_json_repetition_value(fractional_remainder)}"


def _configured_trial_pool_repetitions(source: dict[str, Any], settings: dict[str, Any]) -> float:
    folder_key = str(source.get("folder_key") or "")
    file_key = str(source.get("file_key") or "")
    family = _trial_pool_family_key(source.get("family"))
    file_overrides = settings.get("file_repetition_overrides", {}) if isinstance(settings.get("file_repetition_overrides"), dict) else {}
    folder_repetitions = settings.get("folder_repetitions", {}) if isinstance(settings.get("folder_repetitions"), dict) else {}
    family_repetitions = settings.get("family_repetitions", {}) if isinstance(settings.get("family_repetitions"), dict) else {}
    default_repetitions = _as_repetition_value(settings.get("default_repetitions", 1), default=1.0, field_name="default_repetitions")
    if file_key and file_key in file_overrides:
        return _as_repetition_value(file_overrides[file_key], default=default_repetitions, field_name=f"file_repetition_overrides.{file_key}")
    if folder_key and folder_key in folder_repetitions:
        return _as_repetition_value(folder_repetitions[folder_key], default=default_repetitions, field_name=f"folder_repetitions.{folder_key}")
    if family and family in family_repetitions:
        return _as_repetition_value(family_repetitions[family], default=default_repetitions, field_name=f"family_repetitions.{family}")
    return default_repetitions


def _trial_pool_fractional_records(
    source_files: list[dict[str, Any]],
    settings: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str], str]:
    seed = int(settings.get("fractional_seed", 20250604) or 20250604)
    records: list[dict[str, Any]] = []
    for index, source in enumerate(source_files):
        configured = _configured_trial_pool_repetitions(source, settings)
        base_repetitions = int(math.floor(configured + 1e-9))
        fractional_remainder = round(configured - base_repetitions, 1)
        record = {
            "source": source,
            "source_index": index,
            "configured_repetitions": configured,
            "base_repetitions": base_repetitions,
            "fractional_remainder": fractional_remainder,
            "fractional_extra": False,
            "fractional_selection_rank": "",
            "balancing_stratum": _trial_pool_fractional_stratum(source, fractional_remainder) if fractional_remainder else "",
            "balancing_parent_stratum": _trial_pool_fractional_parent_stratum(source, fractional_remainder) if fractional_remainder else "",
            "source_lineage": _trial_pool_source_lineage_key(source),
        }
        records.append(record)

    warnings: list[str] = []
    fractional_groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        if float(record["fractional_remainder"]) <= 0:
            continue
        fractional_groups.setdefault(str(record["balancing_stratum"]), []).append(record)

    strata_by_parent: dict[str, list[str]] = {}
    for stratum, group in fractional_groups.items():
        parent = str(group[0].get("balancing_parent_stratum") or stratum)
        strata_by_parent.setdefault(parent, []).append(stratum)
    stratum_offsets: dict[str, int] = {}
    for parent, strata in strata_by_parent.items():
        ordered_strata = sorted(
            strata,
            key=lambda item: (
                int(fractional_groups[item][0]["source"].get("soa_ms") or 0),
                item,
            ),
        )
        base_offset = int(hashlib.sha256(f"{seed}|{parent}".encode("utf-8")).hexdigest()[:8], 16)
        running_offset = base_offset
        for stratum in ordered_strata:
            group = fractional_groups[stratum]
            remainder = float(group[0]["fractional_remainder"])
            expected_extra = len(group) * remainder
            extra_count = max(0, min(int(math.floor(expected_extra + 0.5)), len(group)))
            stratum_offsets[stratum] = running_offset % max(1, len(group))
            running_offset += extra_count

    for stratum, group in sorted(fractional_groups.items()):
        if not group:
            continue
        remainder = float(group[0]["fractional_remainder"])
        expected_extra = len(group) * remainder
        extra_count = int(math.floor(expected_extra + 0.5))
        extra_count = max(0, min(extra_count, len(group)))
        if abs(expected_extra - round(expected_extra)) > 1e-7:
            warnings.append(
                f"Fractional repetitions cannot split {len(group)} files exactly in {stratum}; selected {extra_count} extra rows."
            )
        if extra_count <= 0:
            continue
        ordered = sorted(
            group,
            key=lambda item: (
                str(item.get("source_lineage") or ""),
                str(item["source"].get("sequence_variant_key") or item["source"].get("variant_key") or ""),
                str(item["source"].get("source_file_name") or ""),
                str(item["source"].get("file_key") or ""),
            ),
        )
        offset = stratum_offsets.get(stratum, 0) % len(ordered)
        rotated = ordered[offset:] + ordered[:offset]
        for rank, record in enumerate(rotated[:extra_count], start=1):
            record["fractional_extra"] = True
            record["fractional_selection_rank"] = rank

    signature_payload = [
        {
            "file_key": str(record["source"].get("file_key") or ""),
            "configured": _json_repetition_value(float(record["configured_repetitions"])),
            "base": int(record["base_repetitions"]),
            "fractional": _json_repetition_value(float(record["fractional_remainder"])),
            "extra": bool(record["fractional_extra"]),
            "stratum": str(record["balancing_stratum"]),
        }
        for record in records
    ]
    signature = hashlib.sha256(json.dumps(signature_payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return records, warnings, signature


def _trial_pool_row_from_record(
    record: dict[str, Any],
    *,
    trial_pool_index: int,
    repetition_index: int,
    fractional_extra: bool,
    balancing_seed: int,
    balancing_signature: str,
) -> dict[str, Any]:
    source = record["source"]
    family = str(source.get("family") or "")
    duration_ms = int(source.get("duration_ms") or 0)
    return {
        "trial_pool_index": trial_pool_index,
        "family": family,
        "folder_key": str(source.get("folder_key") or ""),
        "folder_name": str(source.get("folder_name") or ""),
        "row_label": str(source.get("row_label") or ""),
        "source_file_name": str(source.get("source_file_name") or Path(str(source.get("file_path") or "")).name),
        "trial_file_path": str(source.get("file_path") or ""),
        "source_sha256": str(source.get("sha256") or ""),
        "duration_ms": duration_ms,
        "duration_s": source.get("duration_s", ""),
        "looming_segment_onset_s": source.get("looming_segment_onset_s", ""),
        "tactile_onset_s": source.get("tactile_onset_s", ""),
        "repetition_index": repetition_index,
        "configured_repetitions": _json_repetition_value(float(record["configured_repetitions"])),
        "base_repetitions": int(record["base_repetitions"]),
        "fractional_remainder": _json_repetition_value(float(record["fractional_remainder"])),
        "fractional_extra": 1 if fractional_extra else 0,
        "balancing_seed": balancing_seed,
        "balancing_stratum": str(record.get("balancing_stratum") or ""),
        "balancing_signature": balancing_signature,
        "source_lineage": str(record.get("source_lineage") or ""),
        "soa_ms": int(source.get("soa_ms") or 0),
        "baseline_mode": str(source.get("baseline_mode") or ""),
        "sequence_variant_key": str(source.get("sequence_variant_key") or source.get("variant_key") or ""),
        "sequence_labels": str(source.get("sequence_labels") or ""),
        "channels": int(source.get("channels") or 0),
        "tactile_channel": source.get("tactile_channel") if source.get("tactile_channel") not in (None, "") else "",
    }


def _bake_trial_repetition_pool(design: StimulusDesign, render_dir: Path, recipe: dict[str, Any]) -> dict[str, Any]:
    source_manifest_path = _baseline_tactile_bake_root(render_dir) / "baseline_tactile_trial_files_manifest.json"
    source_manifest = _load_json(source_manifest_path)
    source_errors = _validate_tactile_trial_manifest(source_manifest, design=design)
    if source_errors:
        raise ValueError(f"Bake Segment 3 trial files before baking Segment 4 trial pool: {source_errors[0]}")
    source_files = _trial_pool_source_file_rows(source_manifest.get("files", []) if isinstance(source_manifest, dict) else [])
    if not source_files:
        raise ValueError("Segment 3 does not contain any trial files for Segment 4.")

    settings = _trial_pool_recipe_settings(recipe, design)
    records, balance_warnings, balancing_signature = _trial_pool_fractional_records(source_files, settings)
    balancing_seed = int(settings.get("fractional_seed", 20250604) or 20250604)
    root = _trial_pool_root(render_dir)
    _remove_tree(root)
    _ensure_dir(root)

    fieldnames = [
        "trial_pool_index",
        "family",
        "folder_key",
        "folder_name",
        "row_label",
        "source_file_name",
        "trial_file_path",
        "source_sha256",
        "duration_ms",
        "duration_s",
        "looming_segment_onset_s",
        "tactile_onset_s",
        "repetition_index",
        "configured_repetitions",
        "base_repetitions",
        "fractional_remainder",
        "fractional_extra",
        "balancing_seed",
        "balancing_stratum",
        "balancing_signature",
        "source_lineage",
        "soa_ms",
        "baseline_mode",
        "sequence_variant_key",
        "sequence_labels",
        "channels",
        "tactile_channel",
    ]
    rows: list[dict[str, Any]] = []
    folder_summaries: dict[str, dict[str, Any]] = {}
    family_counts = {"audio_tactile": 0, "baseline": 0, "catch": 0}
    trial_pool_index = 1
    for record in records:
        source = record["source"]
        folder_key = str(source.get("folder_key") or "")
        family = str(source.get("family") or "")
        duration_ms = int(source.get("duration_ms") or 0)
        base_repetitions = int(record["base_repetitions"])
        fractional_extra = bool(record["fractional_extra"])
        occurrence_count = base_repetitions + (1 if fractional_extra else 0)
        summary = folder_summaries.setdefault(
            folder_key,
            {
                "folder_key": folder_key,
                "folder_name": str(source.get("folder_name") or ""),
                "row_folder_name": str(source.get("row_folder_name") or ""),
                "row_label": str(source.get("row_label") or ""),
                "family": family,
                "unique_file_count": 0,
                "trial_count": 0,
                "duration_ms": 0,
                "configured_repetition_values": [],
            },
        )
        summary["unique_file_count"] += 1
        summary["trial_count"] += occurrence_count
        summary["duration_ms"] += duration_ms * occurrence_count
        summary["configured_repetition_values"].append(_json_repetition_value(float(record["configured_repetitions"])))
        for repetition_index in range(1, base_repetitions + 1):
            row = _trial_pool_row_from_record(
                record,
                trial_pool_index=trial_pool_index,
                repetition_index=repetition_index,
                fractional_extra=False,
                balancing_seed=balancing_seed,
                balancing_signature=balancing_signature,
            )
            rows.append(row)
            if family in family_counts:
                family_counts[family] += 1
            trial_pool_index += 1
        if fractional_extra:
            row = _trial_pool_row_from_record(
                record,
                trial_pool_index=trial_pool_index,
                repetition_index=base_repetitions + 1,
                fractional_extra=True,
                balancing_seed=balancing_seed,
                balancing_signature=balancing_signature,
            )
            rows.append(row)
            if family in family_counts:
                family_counts[family] += 1
            trial_pool_index += 1
    if not rows:
        raise ValueError("Segment 4 repetition settings produced zero trial rows.")

    for summary in folder_summaries.values():
        unique_values = sorted({_json_repetition_value(float(value)) for value in summary.pop("configured_repetition_values", [])}, key=float)
        summary["configured_repetitions"] = unique_values[0] if len(unique_values) == 1 else unique_values

    folder_summary_rows = sorted(folder_summaries.values(), key=lambda item: (str(item.get("row_folder_name") or ""), str(item.get("folder_name") or "")))
    total_duration_ms = sum(int(row["duration_ms"]) for row in rows)
    longest_folder = max(folder_summary_rows, key=lambda item: int(item.get("duration_ms") or 0), default={})
    csv_path = _trial_pool_csv_path(render_dir)
    with open(_filesystem_path(csv_path), "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    manifest_path = _trial_pool_manifest_path(render_dir)
    manifest_payload = {
        "schema": TRIAL_REPETITION_POOL_MANIFEST_SCHEMA,
        "status": "baked",
        "accepted": False,
        "accepted_at": "",
        "written_at": datetime.now().isoformat(timespec="seconds"),
        "root": str(root),
        "csv_path": str(csv_path),
        "source_segment3_manifest": str(source_manifest_path),
        "source_segment3_manifest_sha256": _local_file_sha256(source_manifest_path),
        "loudness_policy": loudness_policy_for_design(design),
        "settings": settings,
        "balancing_seed": balancing_seed,
        "balancing_signature": balancing_signature,
        "balance_warnings": balance_warnings,
        "unique_file_count": len(source_files),
        "total_trials": len(rows),
        "family_counts": family_counts,
        "family_percentages": _trial_pool_percentages(family_counts, len(rows)),
        "estimated_total_duration_ms": total_duration_ms,
        "estimated_total_duration_s": round(total_duration_ms / 1000.0, 3),
        "average_trial_duration_ms": round(total_duration_ms / max(1, len(rows)), 3),
        "longest_folder": longest_folder,
        "folder_summaries": folder_summary_rows,
        "csv_columns": fieldnames,
    }
    errors = _validate_trial_pool_manifest(manifest_payload, project_dir=render_dir, design=design)
    if errors:
        _remove_tree(root)
        raise ValueError(f"Segment 4 bake validation failed before manifest publish: {errors[0]}")
    _write_text_file(manifest_path, json.dumps(_json_ready(manifest_payload), indent=2) + "\n", encoding="utf-8")
    return {
        "status": "baked",
        "root": str(root),
        "manifest_path": str(manifest_path),
        "csv_path": str(csv_path),
        "unique_file_count": len(source_files),
        "total_count": len(rows),
        "audio_tactile_count": family_counts["audio_tactile"],
        "baseline_count": family_counts["baseline"],
        "catch_count": family_counts["catch"],
        "estimated_total_duration_ms": total_duration_ms,
        "folder_count": len(folder_summary_rows),
        "balancing_signature": balancing_signature,
        "balance_warnings": balance_warnings,
    }


def _read_csv_dict_rows(path: Path) -> list[dict[str, str]]:
    with open(_filesystem_path(path), newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _stable_int(value: str) -> int:
    return int(hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:12], 16)


def _gradient_hex(value: float, minimum: float, maximum: float) -> str:
    start = (226, 237, 255)
    end = (37, 86, 151)
    if maximum <= minimum:
        t = 0.5
    else:
        t = max(0.0, min(1.0, (float(value) - minimum) / (maximum - minimum)))
    rgb = [round(start[index] + (end[index] - start[index]) * t) for index in range(3)]
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _hashed_feature_color(value: str) -> str:
    palette = [
        "#246b55",
        "#4b5fa8",
        "#a4631b",
        "#8b4d88",
        "#3f7f93",
        "#6b6f2a",
        "#a94c4c",
        "#4f6f9f",
        "#7a5b2e",
        "#5f5a9b",
    ]
    text = str(value or "feature")
    return palette[_stable_int(text) % len(palette)]


def _block_csv_noise_type(row: dict[str, Any]) -> str:
    text = " ".join(
        str(row.get(key) or "")
        for key in ("sequence_labels", "source_file_name", "sequence_variant_key", "source_lineage")
    ).lower()
    for noise_type in SUPPORTED_NOISE_TYPES:
        if noise_type in text:
            return noise_type
    return CUSTOM_AUDIO_NOISE_TYPE


def _block_csv_assignment_key(row: dict[str, Any]) -> str:
    return "|".join(
        str(row.get(key) or "")
        for key in ("family", "row_label", "soa_ms", "source_lineage", "sequence_variant_key", "baseline_mode")
    )


def _block_csv_feature_keys(row: dict[str, Any]) -> list[str]:
    return [
        f"family:{row.get('family') or ''}",
        f"row:{row.get('row_label') or ''}",
        f"soa:{row.get('soa_ms') or ''}",
        f"source:{row.get('source_lineage') or ''}",
        f"variant:{row.get('sequence_variant_key') or ''}",
    ]


def _block_csv_row_key(row: dict[str, Any]) -> str:
    folder_key = str(row.get("folder_key") or "")
    parts = folder_key.split("__")
    if len(parts) >= 2 and re.match(r"^row_\d+$", parts[0], flags=re.IGNORECASE):
        return "__".join(parts[:2]).lower()
    label = str(row.get("row_label") or row.get("row_folder_name") or "").strip()
    return _slug(label).lower() or "row_01"


def _block_csv_row_sort_key(row_key: str, first_seen: int) -> tuple[int, int, str]:
    match = re.search(r"row[_-]?(\d+)", row_key, flags=re.IGNORECASE)
    row_number = int(match.group(1)) if match else first_seen + 1
    return row_number, first_seen, row_key


def _block_csv_row_order(pool_rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    seen: dict[str, dict[str, str]] = {}
    for row in pool_rows:
        row_key = _block_csv_row_key(row)
        if row_key not in seen:
            seen[row_key] = {
                "row_key": row_key,
                "row_label": str(row.get("row_label") or row_key),
                "first_seen": str(len(seen)),
            }
    return [
        {key: value for key, value in row_info.items() if key != "first_seen"}
        for row_info in sorted(
            seen.values(),
            key=lambda item: _block_csv_row_sort_key(item["row_key"], int(item["first_seen"])),
        )
    ]


def _distribute_block_csv_row_family(
    rows_for_row_family: list[dict[str, Any]],
    block_count: int,
    *,
    seed: int,
    row_key: str,
) -> list[list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows_for_row_family:
        groups.setdefault(_block_csv_assignment_key(row), []).append(row)
    row_blocks: list[list[dict[str, Any]]] = [[] for _ in range(block_count)]
    feature_counts: list[dict[str, int]] = [{} for _ in range(block_count)]
    for group_key in sorted(groups):
        rows = sorted(groups[group_key], key=lambda item: int(item.get("trial_pool_index") or 0))
        offset = _stable_int(f"{seed}|{row_key}|{group_key}") % block_count
        rotation = [(offset + index) % block_count for index in range(block_count)]
        rotation_rank = {block_index: rank for rank, block_index in enumerate(rotation)}
        for row in rows:
            feature_keys = _block_csv_feature_keys(row)
            block_index = min(
                rotation,
                key=lambda candidate: (
                    len(row_blocks[candidate]),
                    sum(feature_counts[candidate].get(key, 0) for key in feature_keys),
                    rotation_rank[candidate],
                ),
            )
            row_blocks[block_index].append(row)
            for key in feature_keys:
                feature_counts[block_index][key] = feature_counts[block_index].get(key, 0) + 1
    for index, rows in enumerate(row_blocks, start=1):
        rows.sort(key=lambda item: _stable_int(f"{seed}|{row_key}|block:{index}|trial:{item.get('trial_pool_index')}"))
    return row_blocks


def _assign_trial_pool_rows_to_blocks(pool_rows: list[dict[str, Any]], block_count: int, *, seed: int) -> list[list[dict[str, Any]]]:
    row_order = _block_csv_row_order(pool_rows)
    if not row_order:
        return [[] for _ in range(block_count)]

    rows_by_row_key: dict[str, list[dict[str, Any]]] = {row_info["row_key"]: [] for row_info in row_order}
    for row in pool_rows:
        rows_by_row_key.setdefault(_block_csv_row_key(row), []).append(row)

    distributed_by_row = {
        row_info["row_key"]: _distribute_block_csv_row_family(
            rows_by_row_key.get(row_info["row_key"], []),
            block_count,
            seed=seed,
            row_key=row_info["row_key"],
        )
        for row_info in row_order
    }

    blocks: list[list[dict[str, Any]]] = [[] for _ in range(block_count)]
    for block_index in range(block_count):
        row_queues = {
            row_info["row_key"]: list(distributed_by_row[row_info["row_key"]][block_index])
            for row_info in row_order
        }
        while any(row_queues.values()):
            for row_info in row_order:
                queue = row_queues[row_info["row_key"]]
                if queue:
                    blocks[block_index].append(queue.pop(0))
    return blocks


def _block_csv_family_label(family: str) -> str:
    return {
        "audio_tactile": "Audio-tactile",
        "baseline": "Baseline",
        "catch": "Catch",
    }.get(family, family.replace("_", " ").title() if family else "Trial")


def _block_csv_row(
    source: dict[str, Any],
    *,
    block_index: int,
    block_label: str,
    block_trial_index: int,
    soa_min: int,
    soa_max: int,
) -> dict[str, Any]:
    family = _trial_pool_family_key(source.get("family"))
    row_label = str(source.get("row_label") or source.get("row_folder_name") or "")
    noise_type = _block_csv_noise_type(source)
    soa_text = str(source.get("soa_ms") or "").strip()
    try:
        soa_value = int(float(soa_text))
    except ValueError:
        soa_value = 0
    soa_color = _gradient_hex(soa_value, soa_min, soa_max) if soa_text and soa_value > 0 else "#d8dde2"
    return {
        "block_index": block_index,
        "block_label": block_label,
        "block_trial_index": block_trial_index,
        "trial_pool_index": source.get("trial_pool_index", ""),
        "family": family,
        "family_label": _block_csv_family_label(family),
        "family_color_hex": TRIAL_FAMILY_COLORS.get(family, "#68746c"),
        "row_label": row_label,
        "row_color_hex": _hashed_feature_color(row_label),
        "folder_key": source.get("folder_key", ""),
        "folder_name": source.get("folder_name", ""),
        "noise_type": noise_type,
        "noise_color_hex": _source_color_hex(noise_type),
        "soa_ms": soa_text,
        "soa_color_hex": soa_color,
        "baseline_mode": source.get("baseline_mode", ""),
        "sequence_variant_key": source.get("sequence_variant_key", ""),
        "sequence_labels": source.get("sequence_labels", ""),
        "source_file_name": source.get("source_file_name", ""),
        "trial_file_path": source.get("trial_file_path", ""),
        "source_sha256": source.get("source_sha256", ""),
        "duration_ms": source.get("duration_ms", ""),
        "duration_s": source.get("duration_s", ""),
        "looming_segment_onset_s": source.get("looming_segment_onset_s", ""),
        "tactile_onset_s": source.get("tactile_onset_s", ""),
        "repetition_index": source.get("repetition_index", ""),
        "configured_repetitions": source.get("configured_repetitions", ""),
        "fractional_extra": source.get("fractional_extra", ""),
        "channels": source.get("channels", ""),
        "tactile_channel": source.get("tactile_channel", ""),
    }


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (item[0] == "", item[0])))


def _block_csv_summary(block_index: int, block_label: str, csv_path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    duration_ms = sum(int(float(row.get("duration_ms") or 0)) for row in rows)
    return {
        "block_index": block_index,
        "block_label": block_label,
        "csv_path": str(csv_path),
        "csv_file_name": csv_path.name,
        "trial_count": len(rows),
        "duration_ms": duration_ms,
        "family_counts": _count_by(rows, "family"),
        "row_label_counts": _count_by(rows, "row_label"),
        "soa_counts": _count_by(rows, "soa_ms"),
        "noise_type_counts": _count_by(rows, "noise_type"),
        "preview_rows": rows[:240],
        "preview_row_count": min(len(rows), 240),
    }


def _bake_block_csv_preview(
    design: StimulusDesign,
    render_dir: Path,
    recipe: dict[str, Any],
    *,
    progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    source_manifest_path = _trial_pool_manifest_path(render_dir)
    source_manifest = _load_json(source_manifest_path)
    source_errors = _validate_trial_pool_manifest(source_manifest, project_dir=render_dir, design=design)
    if source_errors:
        raise ValueError(f"Bake Segment 4 trial pool before baking Segment 5 block CSVs: {source_errors[0]}")
    pool_csv_path = Path(str(source_manifest.get("csv_path") or _trial_pool_csv_path(render_dir)))
    pool_rows = _read_csv_dict_rows(pool_csv_path)
    if not pool_rows:
        raise ValueError("Segment 4 trial-pool CSV does not contain any rows.")

    block_count = max(1, int(recipe.get("block_count") or getattr(design.protocol, "blocks", 1) or 1))
    seed = int(recipe.get("seed") or getattr(design.protocol, "random_seed", 20250604) or 20250604)
    soa_values: list[int] = []
    for row in pool_rows:
        try:
            soa_value = int(float(str(row.get("soa_ms") or "").strip()))
        except ValueError:
            continue
        if soa_value > 0:
            soa_values.append(soa_value)
    soa_min = min(soa_values, default=0)
    soa_max = max(soa_values, default=0)
    root = _block_csv_preview_root(render_dir)
    _remove_tree(root)
    _ensure_dir(root)
    if progress:
        progress(0, block_count, "Reading Segment 4 trial pool")

    row_order = _block_csv_row_order(pool_rows)
    blocks = _assign_trial_pool_rows_to_blocks(pool_rows, block_count, seed=seed)
    fieldnames = [
        "block_index",
        "block_label",
        "block_trial_index",
        "trial_pool_index",
        "family",
        "family_label",
        "family_color_hex",
        "row_label",
        "row_color_hex",
        "folder_key",
        "folder_name",
        "noise_type",
        "noise_color_hex",
        "soa_ms",
        "soa_color_hex",
        "baseline_mode",
        "sequence_variant_key",
        "sequence_labels",
        "source_file_name",
        "trial_file_path",
        "source_sha256",
        "duration_ms",
        "duration_s",
        "looming_segment_onset_s",
        "tactile_onset_s",
        "repetition_index",
        "configured_repetitions",
        "fractional_extra",
        "channels",
        "tactile_channel",
    ]
    block_summaries: list[dict[str, Any]] = []
    total_duration_ms = 0
    for block_index, source_rows in enumerate(blocks, start=1):
        block_label = f"Block {block_index:02d}"
        csv_path = root / f"block_{block_index:02d}.csv"
        rows = [
            _block_csv_row(
                row,
                block_index=block_index,
                block_label=block_label,
                block_trial_index=trial_index,
                soa_min=soa_min,
                soa_max=soa_max,
            )
            for trial_index, row in enumerate(source_rows, start=1)
        ]
        with open(_filesystem_path(csv_path), "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        summary = _block_csv_summary(block_index, block_label, csv_path, rows)
        block_summaries.append(summary)
        total_duration_ms += int(summary["duration_ms"])
        if progress:
            progress(block_index, block_count, f"Wrote {block_label}")

    manifest_path = _block_csv_preview_manifest_path(render_dir)
    manifest_payload = {
        "schema": BLOCK_CSV_PREVIEW_MANIFEST_SCHEMA,
        "status": "baked",
        "accepted": False,
        "accepted_at": "",
        "accepted_source_segment4_manifest_sha256": "",
        "written_at": datetime.now().isoformat(timespec="seconds"),
        "root": str(root),
        "source_segment4_manifest": str(source_manifest_path),
        "source_segment4_manifest_sha256": _local_file_sha256(source_manifest_path),
        "source_segment4_csv": str(pool_csv_path),
        "loudness_policy": loudness_policy_for_design(design),
        "block_count": block_count,
        "randomization_seed": seed,
        "total_trials": len(pool_rows),
        "estimated_total_duration_ms": total_duration_ms,
        "estimated_total_duration_s": round(total_duration_ms / 1000.0, 3),
        "balancing_strategy": "row_order_preserving_minimum_divergence_by_family_soa_source_lineage",
        "row_sequence_strategy": "cycle_preserved_segment_row_order_within_each_block",
        "row_order": row_order,
        "soa_color_gradient": {
            "minimum_soa_ms": soa_min,
            "maximum_soa_ms": soa_max,
            "start_hex": "#e2edff",
            "end_hex": "#255697",
        },
        "csv_columns": fieldnames,
        "blocks": block_summaries,
    }
    errors = _validate_block_csv_preview_manifest(manifest_payload, project_dir=render_dir, design=design)
    if errors:
        _remove_tree(root)
        raise ValueError(f"Segment 5 bake validation failed before manifest publish: {errors[0]}")
    _write_text_file(manifest_path, json.dumps(_json_ready(manifest_payload), indent=2) + "\n", encoding="utf-8")
    return {
        "status": "baked",
        "root": str(root),
        "manifest_path": str(manifest_path),
        "block_count": block_count,
        "csv_count": len(block_summaries),
        "total_count": len(pool_rows),
        "estimated_total_duration_ms": total_duration_ms,
        "blocks": [
            {
                "block_index": block["block_index"],
                "block_label": block["block_label"],
                "csv_path": block["csv_path"],
                "trial_count": block["trial_count"],
                "duration_ms": block["duration_ms"],
            }
            for block in block_summaries
        ],
    }


def _bake_recipe_label(recipe: dict[str, Any]) -> str:
    label = str(recipe.get("label") or "").strip()
    if label:
        return label
    if str(recipe.get("kind") or "") == "generated_noise":
        return f"{str(recipe.get('noise_type') or 'pink').strip().title()} noise"
    audio = recipe.get("audio") if isinstance(recipe.get("audio"), dict) else {}
    return str(audio.get("label") or recipe.get("filename") or "Baked stimulus").strip() or "Baked stimulus"


def _unique_stimulus_label(label: str, design: StimulusDesign) -> str:
    base = str(label or "Baked stimulus").strip() or "Baked stimulus"
    existing = {noise.label.strip().lower() for noise in design.noises}
    existing.update(asset.label.strip().lower() for asset in design.custom_looming_files)
    if base.lower() not in existing:
        return base
    index = 2
    while f"{base} {index}".lower() in existing:
        index += 1
    return f"{base} {index}"


def _design_for_bake_recipe(design: StimulusDesign, recipe: dict[str, Any], label: str) -> tuple[StimulusDesign, str, dict[str, Any]]:
    bake_design = _copy_design(design)
    bake_design.name = f"{design.name} - baked {label}"
    bake_design.noises = []
    bake_design.custom_looming_files = []
    bake_design.prestimulus_files = []
    params = dict(bake_design.study_profile_reference_parameters or {})
    params[LOUDNESS_POLICY_KEY] = normalize_loudness_policy(
        recipe.get(LOUDNESS_POLICY_KEY) or recipe.get("loudness_policy") or params.get(LOUDNESS_POLICY_KEY),
        pre_hold_s=bake_design.trajectory.padding_pre_s,
        movement_duration_s=bake_design.trajectory.movement_duration_s,
        post_hold_s=bake_design.trajectory.padding_post_s,
    )
    bake_design.study_profile_reference_parameters = params
    kind = str(recipe.get("kind") or "generated_noise").strip().lower()
    if kind == "generated_noise":
        noise_type = str(recipe.get("noise_type") or "").strip().lower()
        if noise_type not in SUPPORTED_NOISE_TYPES:
            raise ValueError(f"Unsupported generated-noise type: {noise_type or 'missing'}")
        source = {
            "label": label,
            "noise_type": noise_type,
            "azimuth_deg": 0.0,
            "elevation_deg": 0.0,
            "gain": max(0.01, _float(recipe.get("gain"), 1.0)),
            "motion_mode": "looming",
        }
        bake_design.noises = [NoiseDefinition(**source)]
        return bake_design, "generated_noise", source

    if kind == "imported_audio":
        audio = recipe.get("audio") if isinstance(recipe.get("audio"), dict) else {}
        path = str(audio.get("path") or recipe.get("path") or "").strip()
        if not path or not _path_exists(Path(path).expanduser()):
            raise ValueError("Imported audio must be stored locally before baking.")
        render_mode = str(recipe.get("render_mode") or audio.get("render_mode") or "preserve").strip().lower()
        if render_mode not in {"spatialize", "preserve"}:
            render_mode = "preserve"
        duration_s = max(0.1, _float(audio.get("target_duration_s") or recipe.get("target_duration_s"), design.trajectory.total_duration_s))
        gain = max(0.01, _float(audio.get("gain") or recipe.get("gain"), 1.0))
        bake_design.custom_looming_files = [
            AudioFileSpec(
                label=label,
                path=path,
                target_duration_s=duration_s,
                render_mode=render_mode,
                gain=gain,
                motion_mode="looming",
            )
        ]
        return bake_design, "imported_audio", {"target_duration_s": duration_s, "render_mode": render_mode}

    raise ValueError(f"Unsupported bake recipe kind: {kind or 'missing'}")


def _baked_wav_path(result: render_backend.RenderResult, label: str) -> Path | None:
    if result.wav_paths:
        label_slug = _slug(label).lower()
        for path in result.wav_paths:
            if label_slug in _slug(path.stem).lower():
                return Path(path)
        return Path(result.wav_paths[0])
    candidate = result.output_dir / f"looming_{_slug(label)}.wav"
    return candidate if _path_exists(candidate) else None


def _preflight_to_dict(preflight: Any) -> dict[str, Any]:
    return {
        "participant_id": preflight.participant_id,
        "valid_design": preflight.valid_design,
        "participant_ready": preflight.participant_ready,
        "render_ready": preflight.render_ready,
        "schedule_ready": preflight.schedule_ready,
        "audio_route": preflight.audio_route,
        "audio_ready": preflight.audio_ready,
        "ready": preflight.ready,
        "messages": list(preflight.messages),
    }


def _custom_schedule_missing(project_dir: Path | None, design: StimulusDesign) -> list[str]:
    if project_dir is None:
        return ["Bake and accept Segment 5 block CSVs."]
    manifest = _load_json(_block_csv_preview_manifest_path(project_dir))
    errors = _validate_block_csv_preview_manifest(manifest, project_dir=project_dir, design=design)
    if errors:
        return ["Bake Segment 5 block CSVs."]
    if not bool(manifest.get("accepted")):
        return ["Accept Segment 5 block CSVs."]
    return []


def _raise_if_current_block_csvs_accepted(project_dir: Path, design: StimulusDesign | None = None) -> None:
    manifest = _load_json(_block_csv_preview_manifest_path(project_dir))
    if not bool(manifest.get("accepted")):
        return
    errors = _validate_block_csv_preview_manifest(manifest, project_dir=project_dir, design=design)
    if not errors:
        raise RuntimeError("Segment 5 block CSVs are accepted. Click Edit Blocks before regenerating or changing upstream segment outputs.")


def _custom_workflow_status(
    design: StimulusDesign,
    participant_id: str,
    project_dir: Path | None = None,
) -> dict[str, Any]:
    step_checks = [
        ("study", "Study Profile", _custom_study_missing(design)),
        ("stimulus", "Stimulus Design", _custom_stimulus_missing(project_dir, design)),
        ("trials", "Trial Sequence Design", _custom_trials_missing(project_dir, design)),
        ("baseline", "Baseline and Tactile Trial Design", _custom_baseline_missing(project_dir, design)),
        ("block", "Trial Composition", _custom_block_missing(project_dir, design)),
        ("schedule", "Block CSV Preview", _custom_schedule_missing(project_dir, design)),
        ("run", "Run Preparation", _custom_run_missing(project_dir, design)),
    ]
    is_custom = _is_custom_design(design)
    if not is_custom:
        steps = [
            {"id": step_id, "label": label, "complete": not missing, "missing": list(missing)}
            for step_id, label, missing in step_checks
        ]
        current_step = next((step["id"] for step in steps if not step["complete"]), "run")
        render_missing = _missing_for_steps(steps, {"study", "stimulus", "trials", "baseline", "block", "schedule"})
        prepare_missing = _missing_for_steps(steps, {"study", "stimulus", "trials", "baseline", "block", "schedule", "run"})
        return {
            "is_custom": False,
            "current_step": current_step,
            "ready_to_render": not render_missing,
            "ready_to_prepare": not prepare_missing,
            "missing": prepare_missing,
            "steps": steps,
        }

    steps = [
        {"id": step_id, "label": label, "complete": not missing, "missing": list(missing)}
        for step_id, label, missing in step_checks
    ]
    current_step = next((step["id"] for step in steps if not step["complete"]), "run")
    render_missing = _missing_for_steps(steps, {"study", "stimulus", "trials", "baseline", "block", "schedule"})
    prepare_missing = _missing_for_steps(steps, {"study", "stimulus", "trials", "baseline", "block", "schedule", "run"})
    return {
        "is_custom": True,
        "current_step": current_step,
        "ready_to_render": not render_missing,
        "ready_to_prepare": not prepare_missing,
        "missing": prepare_missing,
        "steps": steps,
    }


def _require_custom_workflow_ready(
    design: StimulusDesign,
    participant_id: str,
    project_dir: Path | None = None,
    *,
    require_participant: bool,
) -> None:
    workflow = _custom_workflow_status(design, participant_id, project_dir)
    if not workflow["is_custom"]:
        return
    ready_key = "ready_to_prepare" if require_participant else "ready_to_render"
    if workflow[ready_key]:
        return
    step_ids = (
        {"study", "stimulus", "trials", "baseline", "block", "schedule", "run"}
        if require_participant
        else {"study", "stimulus", "trials", "baseline", "block", "schedule"}
    )
    missing = _missing_for_steps(workflow["steps"], step_ids)
    raise RuntimeError(f"Custom design is incomplete: {'; '.join(missing)}")


def _is_custom_design(design: StimulusDesign) -> bool:
    return str(design.study_profile_reference_parameters.get("dashboard_mode", "")).lower() == "custom"


def _is_readonly_profile_design(design: StimulusDesign) -> bool:
    return bool(str(design.study_profile_id or "").strip()) and not _is_custom_design(design)


def _payload_mutates_design(payload: dict[str, Any] | None) -> bool:
    if not payload:
        return False
    if "design" in payload and isinstance(payload.get("design"), dict):
        incoming_profile_id = str(payload["design"].get("study_profile_id") or "").strip()
        return bool(incoming_profile_id)
    mutating_keys = {"design", "trajectory_controls", "run_setup", "name", "trajectory", "protocol", "noises"}
    return any(key in payload for key in mutating_keys)


def _missing_for_steps(steps: list[dict[str, Any]], step_ids: set[str]) -> list[str]:
    missing: list[str] = []
    for step in steps:
        if step["id"] not in step_ids:
            continue
        missing.extend(str(item) for item in step.get("missing", []))
    return missing


def _custom_study_missing(design: StimulusDesign) -> list[str]:
    name = design.name.strip()
    if not name or name.lower() in {"custom pps design", "untitled pps design"}:
        return ["Choose a custom design name."]
    return []


def _custom_stimulus_missing(project_dir: Path | None, design: StimulusDesign) -> list[str]:
    missing: list[str] = []
    t = design.trajectory
    if t.path_length_m <= 0 or t.movement_duration_s <= 0:
        missing.append("Choose a valid sound trajectory and movement duration.")
    has_noise = any(
        noise.label.strip()
        and noise.noise_type.lower() in SUPPORTED_NOISE_TYPES
        and noise.gain > 0
        for noise in design.noises
    )
    has_imported_source = any(
        asset.label.strip()
        and asset.path.strip()
        and _path_exists(Path(asset.path).expanduser())
        and asset.target_duration_s > 0
        for asset in design.custom_looming_files
    )
    if not has_noise and not has_imported_source:
        missing.append("Add at least one procedural noise or custom looming audio source.")
    if missing:
        return missing
    if project_dir is None:
        return ["Bake Segment 1 ingredients."]
    manifest_path = _ingredient_manifest_path(Path(project_dir))
    manifest = _load_ingredient_manifest(Path(project_dir))
    ingredients = manifest.get("ingredients", []) if isinstance(manifest.get("ingredients"), list) else []
    errors = _validate_ingredient_rows(ingredients)
    if not _path_exists(manifest_path) or not ingredients:
        return ["Bake Segment 1 ingredients."]
    if errors:
        return [f"Repair Segment 1 ingredient registry: {errors[0]}"]
    return missing


def _custom_trials_missing(project_dir: Path | None, design: StimulusDesign) -> list[str]:
    missing: list[str] = []
    p = design.protocol
    if not has_trial_strips(p):
        missing.append("Create at least one trial sequence row.")
    if not p.tactile_sites:
        missing.append("Keep at least one tactile site.")
    if not p.respiratory_phases:
        missing.append("Keep at least one respiratory phase.")
    if missing:
        return missing
    if project_dir is None:
        return ["Bake Segment 2 trial sequences."]
    manifest = _load_trial_sequence_manifest(Path(project_dir))
    errors = _validate_trial_sequence_manifest(manifest, design=design)
    if errors:
        return ["Bake Segment 2 trial sequences."]
    return missing


def _custom_block_missing(project_dir: Path | None, design: StimulusDesign) -> list[str]:
    missing: list[str] = []
    p = design.protocol
    if p.repetitions_per_condition < 1:
        missing.append("Set repetitions to at least 1.")
    if p.blocks < 1:
        missing.append("Set block count to at least 1.")
    if missing:
        return missing
    if project_dir is None:
        return ["Bake Segment 4 trial pool CSV."]
    manifest = _load_json(_trial_pool_manifest_path(Path(project_dir)))
    errors = _validate_trial_pool_manifest(manifest, project_dir=Path(project_dir), design=design)
    if errors:
        return ["Bake Segment 4 trial pool CSV."]
    return missing


def _custom_baseline_missing(project_dir: Path | None, design: StimulusDesign) -> list[str]:
    missing: list[str] = []
    p = design.protocol
    strategy = str(p.baseline_strategy or "").strip().lower()
    if strategy not in SUPPORTED_BASELINE_STRATEGIES:
        missing.append("Choose a baseline strategy.")
    if not p.soa_values_ms:
        missing.append("Enter at least one SOA value.")
    if strategy == "custom" and not p.baseline_soa_values_ms:
        missing.append("Enter custom baseline SOAs or choose a built-in baseline strategy.")
    if str(p.baseline_custom_trial_mode or "").strip().lower() not in {"tactile_only", "audio_tactile"}:
        missing.append("Choose whether custom baselines are tactile-only or audio-tactile.")
    if missing:
        return missing
    if project_dir is None:
        return ["Bake Segment 3 baseline/tactile trial files."]
    manifest = _load_json(_baseline_tactile_bake_root(Path(project_dir)) / "baseline_tactile_trial_files_manifest.json")
    errors = _validate_tactile_trial_manifest(manifest, design=design)
    if errors:
        return ["Bake Segment 3 baseline/tactile trial files."]
    return missing


def _custom_run_missing(project_dir: Path | None, design: StimulusDesign) -> list[str]:
    missing: list[str] = []
    if design.protocol.participants < 1:
        missing.append("Set planned participants to at least 1.")
    if project_dir is None:
        missing.append("Prepare Segment 6 experiment.")
        return missing
    manifest = _load_json(_run_setup_manifest_path(project_dir))
    errors = _validate_run_setup_manifest(manifest, project_dir=project_dir, design=design)
    if errors:
        missing.append("Prepare Segment 6 experiment.")
    return missing


def _template_to_dict(template: StudyTemplate, *, asset_status: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "template_id": template.template_id,
        "title": template.title,
        "citation_label": study_template_citation_label(template),
        "citation": template.citation,
        "bibtex": study_template_bibtex(template),
        "csl_json": study_template_csl_json(template),
        "doi": template.doi,
        "source_url": template.source_url,
        "verification_status": template.verification_status,
        "notes": template.notes,
    }
    if asset_status is not None:
        payload["preload_asset_status"] = asset_status
        payload["profile_parameters_manifest"] = asset_status.get("profile_parameters_manifest", "")
        payload["recreation_status"] = dict(asset_status.get("recreation_status") or {})
        payload["runner_readiness"] = asset_status.get("runner_readiness", "")
        payload["profile_checks_passed"] = bool(asset_status.get("profile_checks_passed", False))
        payload["segment_0_to_4_profile_checks_passed"] = bool(
            asset_status.get("segment_0_to_4_profile_checks_passed", False)
        )
        payload["finished_profile"] = bool(asset_status.get("finished_profile", False))
        payload["segment_6_launchable"] = bool(asset_status.get("segment_6_launchable", False))
        payload["profile_completion_status"] = asset_status.get("profile_completion_status", "unfinished_preload")
        payload["primary_recreation_category"] = asset_status.get("primary_recreation_category", "")
        payload["missing_parameter_count"] = int(asset_status.get("missing_parameter_count") or 0)
        payload["unsupported_structure_count"] = int(asset_status.get("unsupported_structure_count") or 0)
    return payload


def _profile_recreation_status_for_design(design: StimulusDesign) -> dict[str, Any]:
    template_id = str(design.study_profile_id or "").strip()
    if not template_id:
        return {}
    return profile_asset_status(
        template_id,
        inventory=load_preload_inventory(REPO_ROOT),
        repo_root=REPO_ROOT,
    )


def _profile_runner_readiness_errors(design: StimulusDesign) -> list[str]:
    if _is_custom_design(design) or not str(design.study_profile_id or "").strip():
        return []
    status = _profile_recreation_status_for_design(design)
    readiness = str(status.get("runner_readiness") or "").strip()
    checks_passed = bool(status.get("profile_checks_passed", False))
    segment_gate_passed = bool(status.get("segment_0_to_4_profile_checks_passed", checks_passed))
    if (not readiness or readiness == "ready") and checks_passed:
        return []
    category = str(status.get("primary_recreation_category") or "incomplete_profile")
    missing = int(status.get("missing_parameter_count") or 0)
    unsupported = int(status.get("unsupported_structure_count") or 0)
    manifest_path = str(status.get("profile_parameters_manifest") or "").strip()
    parts = []
    if unsupported:
        parts.append(f"{unsupported} unsupported toolkit structure(s)")
    if missing:
        parts.append(f"{missing} missing publication parameter(s)")
    if not segment_gate_passed:
        parts.append("Segment 0-4 profile gate failed")
    reason = ", ".join(parts) or readiness
    suffix = f" See {manifest_path}." if manifest_path else ""
    return [
        "Published-study preload is not a finished Segment 6 launchable profile yet "
        f"({category}: {reason}). A finished profile must pass the Segment 0-4 recreation gate "
        f"and launch as an experiment from Segment 6.{suffix}"
    ]


def _package_to_dict(package: RunPackage | None) -> dict[str, Any] | None:
    if package is None:
        return None
    return {
        "participant_id": package.participant_id,
        "session_id": package.session_id,
        "created_at": package.created_at,
        "session_dir": str(package.session_dir),
        "manifest_path": str(package.manifest_path),
        "design_path": str(package.design_path),
        "protocol_path": str(package.protocol_path),
        "blocks": [_json_ready(asdict(block)) for block in package.blocks],
    }


def _job_to_dict(job: DashboardJob) -> dict[str, Any]:
    return _json_ready(asdict(job))


def _copy_design(design: StimulusDesign) -> StimulusDesign:
    return design_from_dict(design_to_dict(design))


def _sync_loudness_policy_with_trajectory(design: StimulusDesign) -> StimulusDesign:
    params = dict(design.study_profile_reference_parameters or {})
    params[LOUDNESS_POLICY_KEY] = normalize_loudness_policy(
        params.get(LOUDNESS_POLICY_KEY),
        pre_hold_s=design.trajectory.padding_pre_s,
        movement_duration_s=design.trajectory.movement_duration_s,
        post_hold_s=design.trajectory.padding_post_s,
    )
    design.study_profile_reference_parameters = params
    return design


def _instruction_loudness_gain(design: StimulusDesign) -> float:
    policy = loudness_policy_for_design(design)
    return db_to_linear(float(policy.get("instruction_offset_db", -6.0)))


def _normalize_dashboard_design(design: StimulusDesign) -> StimulusDesign:
    updated = _normalize_study5_event_sequence_labels(_copy_design(design))
    updated = _sync_loudness_policy_with_trajectory(updated)
    updated = _normalize_study5_full_soa_baseline_defaults(updated)
    updated = _normalize_study5_trial_pool_repetition_defaults(updated)
    updated = _normalize_study5_original_instruction_assets(updated)
    updated = _ensure_source_trajectory_snapshots(updated)
    updated = _ensure_preload_source_assets(updated)
    return _prune_custom_trial_strip_source_labels(updated)


def _available_sequence_source_labels(design: StimulusDesign) -> set[str]:
    labels: set[str] = set()
    for source in [*design.noises, *design.custom_looming_files, *design.prestimulus_files]:
        label = str(getattr(source, "label", "") or "").strip()
        if label:
            labels.add(label)
    return labels


def _prune_custom_trial_strip_source_labels(design: StimulusDesign) -> StimulusDesign:
    if not _is_custom_design(design):
        return design
    available = _available_sequence_source_labels(design)
    for strip in design.protocol.trial_strips:
        for element in strip.elements:
            if element.kind not in {"fixed_audio", "looming_stimulus"}:
                continue
            labels = [str(label or "").strip() for label in element.source_labels if str(label or "").strip()]
            fallback = str(element.source_label or "").strip()
            if not labels and fallback:
                labels = [fallback]
            filtered = [label for label in dict.fromkeys(labels) if label in available]
            element.source_labels = filtered
            element.source_label = filtered[0] if filtered else ""
    return design


def _normalize_study5_full_soa_baseline_defaults(design: StimulusDesign) -> StimulusDesign:
    if design.study_profile_id != DEFAULT_STUDY_TEMPLATE_ID:
        return design
    design.protocol.include_baseline_trials = True
    design.protocol.include_catch_trials = True
    design.protocol.catch_trial_percentage = 0.0
    design.protocol.baseline_strategy = "tactile_only"
    design.protocol.baseline_custom_trial_mode = "tactile_only"
    design.protocol.baseline_soa_values_ms = []
    for strip in design.protocol.trial_strips:
        if strip.elements:
            strip.catch_percentage = 0.0
            strip.audio_tactile_percentage = 100.0
    return design


def _normalize_study5_trial_pool_repetition_defaults(design: StimulusDesign) -> StimulusDesign:
    if design.study_profile_id != DEFAULT_STUDY_TEMPLATE_ID:
        return design
    existing = getattr(design.protocol, "trial_pool_repetition_defaults", {}) or {}
    defaults = dict(STUDY5_TRIAL_POOL_REPETITION_DEFAULTS)
    defaults.update({key: value for key, value in existing.items() if key not in defaults})
    design.protocol.trial_pool_repetition_defaults = defaults
    return design


def _normalize_study5_original_instruction_assets(design: StimulusDesign) -> StimulusDesign:
    if design.study_profile_id != DEFAULT_STUDY_TEMPLATE_ID:
        return design
    params = dict(design.study_profile_reference_parameters or {})
    params["default_instruction_asset_variant"] = "original_study5"
    params["inhale_instruction_asset"] = STUDY5_ORIGINAL_INSTRUCTION_ASSETS["Inhale instruction"]["path"]
    params["exhale_instruction_asset"] = STUDY5_ORIGINAL_INSTRUCTION_ASSETS["Exhale instruction"]["path"]

    existing_assets = {
        str(item.get("label") or ""): dict(item)
        for item in params.get("custom_clip_assets", [])
        if isinstance(item, dict)
    }
    custom_clip_assets: list[dict[str, Any]] = []
    for label, metadata in STUDY5_ORIGINAL_INSTRUCTION_ASSETS.items():
        custom_clip_assets.append(
            {
                **existing_assets.get(label, {}),
                "label": label,
                "phase": metadata["phase"],
                "variant": "original_study5",
                "path": metadata["path"],
                "duration_s": 4.0,
                "default": True,
            }
        )
    custom_clip_assets.extend(
        item
        for item in params.get("custom_clip_assets", [])
        if isinstance(item, dict) and str(item.get("label") or "") not in STUDY5_ORIGINAL_INSTRUCTION_ASSETS
    )
    params["custom_clip_assets"] = custom_clip_assets
    design.study_profile_reference_parameters = params

    existing_clips = {asset.label: asset for asset in design.prestimulus_files if asset.label}
    normalized: list[AudioFileSpec] = []
    for label, metadata in STUDY5_ORIGINAL_INSTRUCTION_ASSETS.items():
        clip = existing_clips.get(label)
        if clip is None:
            clip = AudioFileSpec(
                label=label,
                path=metadata["path"],
                target_duration_s=4.0,
                render_mode="preserve",
                gain=1.0,
                placement="before",
                phase=metadata["phase"],
                sequence_order=1,
                motion_mode="stationary",
            )
        elif _should_replace_study5_instruction_path(clip.path, metadata):
            clip.path = metadata["path"]
        clip.label = label
        clip.phase = metadata["phase"]
        clip.target_duration_s = 4.0
        clip.render_mode = "preserve"
        clip.motion_mode = "stationary"
        clip.sequence_order = 1
        normalized.append(clip)
    normalized.extend(
        asset
        for asset in design.prestimulus_files
        if asset.label not in STUDY5_ORIGINAL_INSTRUCTION_ASSETS
    )
    design.prestimulus_files = normalized
    return design


def _should_replace_study5_instruction_path(path: str, metadata: dict[str, str]) -> bool:
    current = str(path or "").replace("\\", "/").strip()
    if not current:
        return True
    if current == metadata["path"] or current.endswith(metadata["path"]):
        return False
    if "assets/breathing/british_kokoro/" in current or current.endswith(metadata["legacy_path"]):
        return True
    try:
        current_path = _resolve_dashboard_local_path(current)
        legacy_path = _resolve_dashboard_local_path(metadata["legacy_path"])
        original_path = _resolve_dashboard_local_path(metadata["path"])
        if _path_exists(current_path) and _path_exists(original_path):
            if _local_file_sha256(current_path) == _local_file_sha256(original_path):
                return False
        if _path_exists(current_path) and _path_exists(legacy_path):
            return _local_file_sha256(current_path) == _local_file_sha256(legacy_path)
    except OSError:
        return False
    return False


def _ensure_source_trajectory_snapshots(design: StimulusDesign) -> StimulusDesign:
    for noise in design.noises:
        if noise.trajectory_snapshot:
            continue
        noise.trajectory_snapshot = _stimulus_trajectory_snapshot(
            design,
            label=noise.label,
            source_kind="generated_noise",
            noise_type=noise.noise_type,
        )
    for asset in design.custom_looming_files:
        if asset.trajectory_snapshot:
            continue
        asset.trajectory_snapshot = _stimulus_trajectory_snapshot(
            design,
            label=asset.label,
            source_kind="imported_audio",
            noise_type=CUSTOM_AUDIO_NOISE_TYPE,
        )
    return design


def _ensure_preload_source_assets(design: StimulusDesign) -> StimulusDesign:
    assets = _preload_assets_by_label(design.study_profile_id)
    if not assets:
        return design
    consumed: set[str] = set()
    direction_labels = {
        str(asset.get("direction_label") or "").strip()
        for asset in assets.values()
        if str(asset.get("direction_label") or "").strip()
    }
    for noise in design.noises:
        key = _source_key(noise.label)
        asset = assets.get(key)
        if asset is None:
            continue
        consumed.add(key)
        noise.prebaked_path = str(asset.get("path") or noise.prebaked_path or "")
        if not noise.trajectory_snapshot and isinstance(asset.get("trajectory_snapshot"), dict):
            noise.trajectory_snapshot = dict(asset.get("trajectory_snapshot") or {})
    for audio in design.custom_looming_files:
        key = _source_key(audio.label)
        asset = assets.get(key)
        if asset is None:
            continue
        consumed.add(key)
        audio.path = str(asset.get("path") or audio.path or "")
        if not audio.tone_type:
            audio.tone_type = str(asset.get("noise_type") or asset.get("tone_type") or CUSTOM_AUDIO_NOISE_TYPE)
        if not audio.trajectory_snapshot and isinstance(asset.get("trajectory_snapshot"), dict):
            audio.trajectory_snapshot = dict(asset.get("trajectory_snapshot") or {})
    for key, asset in assets.items():
        if key in consumed:
            continue
        label = str(asset.get("label") or "").strip()
        path = str(asset.get("path") or "").strip()
        if not label or not path:
            continue
        design.custom_looming_files.append(
            AudioFileSpec(
                label=label,
                path=path,
                target_duration_s=float(asset.get("duration_s") or design.trajectory.total_duration_s or 4.0),
                render_mode="preserve",
                tone_type=str(asset.get("noise_type") or asset.get("tone_type") or CUSTOM_AUDIO_NOISE_TYPE),
                gain=1.0,
                motion_mode=str(asset.get("motion_mode") or "looming"),
                trajectory_snapshot=dict(asset.get("trajectory_snapshot") or {}),
            )
        )
    expand_trial_strip_source_labels(
        design,
        [str(asset.get("label") or "") for asset in assets.values()],
    )
    if len(direction_labels) > 1:
        design.protocol.auditory_motion_directions = ["source_trajectory"]
    return design


def _preload_assets_by_label(template_id: str) -> dict[str, dict[str, Any]]:
    if not template_id:
        return {}
    inventory = load_preload_inventory(REPO_ROOT)
    for profile in inventory.get("profiles", []):
        if profile.get("template_id") != template_id:
            continue
        return {
            _source_key(str(asset.get("label") or "")): dict(asset)
            for asset in profile.get("assets", [])
            if str(asset.get("label") or "").strip()
        }
    return {}


def _stimulus_trajectory_snapshot(
    design: StimulusDesign,
    *,
    label: str = "",
    source_kind: str = "",
    noise_type: str = "",
) -> dict[str, Any]:
    controls = _trajectory_controls(design)
    start, end = trajectory_endpoints_xyz(design.trajectory)
    return {
        "schema": "pps-stimulus-trajectory.v1",
        "label": label,
        "source_kind": source_kind,
        "noise_type": noise_type,
        "start_distance_cm": controls["start_distance_cm"],
        "end_distance_cm": controls["end_distance_cm"],
        "start_rotation_deg": controls["start_rotation_deg"],
        "end_rotation_deg": controls["end_rotation_deg"],
        "movement_duration_s": controls["movement_duration_s"],
        "start_hold_s": controls["start_hold_s"],
        "end_hold_s": controls["end_hold_s"],
        "path_length_m": round(float(design.trajectory.path_length_m), 4),
        "coordinate_mode": design.trajectory.coordinate_mode,
        "path_direction": design.trajectory.path_direction,
        "start": {key: round(float(value), 6) for key, value in start.items()},
        "end": {key: round(float(value), 6) for key, value in end.items()},
    }


def _normalize_study5_event_sequence_labels(design: StimulusDesign) -> StimulusDesign:
    if design.study_profile_id != DEFAULT_STUDY_TEMPLATE_ID:
        return design
    updated = _copy_design(design)
    label_map = {
        "Inhale row": "Inhale trial type",
        "Exhale row": "Exhale trial type",
        "Inhale event": "Inhale trial type",
        "Exhale event": "Exhale trial type",
    }
    for strip in updated.protocol.trial_strips:
        strip.label = label_map.get(strip.label, strip.label)
    if "filmstrip trial rows" in updated.study_profile_notes:
        updated.study_profile_notes = updated.study_profile_notes.replace(
            "filmstrip trial rows",
            "within-block trial type rows",
        )
    if "within-block event sequences" in updated.study_profile_notes:
        updated.study_profile_notes = updated.study_profile_notes.replace(
            "within-block event sequences",
            "within-block trial type rows",
        )
    return updated


def _custom_project_design_from_source(source: StimulusDesign, *, project_name: str = "") -> StimulusDesign:
    design = _copy_design(source)
    source_metadata = _project_metadata(source)
    source_template_id = str(source.study_profile_id or source_metadata.get("source_template_id") or "").strip()
    source_project_id = str(source_metadata.get("project_id") or "").strip()
    default_name = f"{source.name or source.study_profile_title or 'PPS profile'} custom"
    design.name = project_name.strip() or default_name
    design.study_profile_id = ""
    design.study_profile_title = ""
    params = dict(design.study_profile_reference_parameters or {})
    params["dashboard_mode"] = "custom"
    params["customized_from_profile_id"] = source_template_id
    params["customized_from_profile_title"] = str(source.study_profile_title or source.name or "").strip()
    params["customized_from_project_id"] = source_project_id
    params.pop(PROJECT_METADATA_KEY, None)
    params.pop(RUN_SETUP_METADATA_KEY, None)
    design.study_profile_reference_parameters = params
    return design


def _copy_ingredient_to_custom_project(
    project: DashboardProjectContext,
    *,
    source_path: str,
    label: str,
    source_kind: str,
    motion_mode: str,
    trajectory_snapshot: dict[str, Any] | None = None,
    provenance: dict[str, Any] | None = None,
) -> str:
    resolved = _resolve_dashboard_local_path(source_path)
    if not _path_exists(resolved):
        raise FileNotFoundError(f"Cannot customize profile because a Segment 1 ingredient is missing: {label}.")
    copied = _copy_materialize_ingredient_audio_file(resolved, project.segment1_dir, label, motion_mode=motion_mode)
    _record_ingredient_file(
        project,
        copied,
        label=label,
        source_kind=source_kind,
        trajectory_snapshot=trajectory_snapshot or {},
        motion_mode=motion_mode,
        provenance=provenance or {},
    )
    return str(copied)


def _materialize_segment1_ingredients_for_custom_project(
    project: DashboardProjectContext,
    design: StimulusDesign,
    *,
    source_design: StimulusDesign,
) -> None:
    _remove_tree(project.segment1_dir)
    _ensure_dir(project.segment1_dir)
    source_metadata = _project_metadata(source_design)
    provenance = {
        "customized_from_profile_id": source_design.study_profile_id or source_metadata.get("source_template_id", ""),
        "customized_from_project_id": source_metadata.get("project_id", ""),
        "customized_at": datetime.now().isoformat(timespec="seconds"),
    }
    for noise in design.noises:
        if not str(noise.prebaked_path or "").strip():
            continue
        copied = _copy_ingredient_to_custom_project(
            project,
            source_path=noise.prebaked_path,
            label=noise.label,
            source_kind="customized_profile_ingredient",
            motion_mode=noise.motion_mode or "looming",
            trajectory_snapshot=noise.trajectory_snapshot,
            provenance={**provenance, "source_path": noise.prebaked_path},
        )
        noise.prebaked_path = copied
    for audio in design.custom_looming_files:
        if not str(audio.path or "").strip():
            continue
        copied = _copy_ingredient_to_custom_project(
            project,
            source_path=audio.path,
            label=audio.label,
            source_kind="customized_profile_ingredient",
            motion_mode=audio.motion_mode or "looming",
            trajectory_snapshot=audio.trajectory_snapshot,
            provenance={**provenance, "source_path": audio.path},
        )
        audio.path = copied
    for audio in design.prestimulus_files:
        if not str(audio.path or "").strip():
            continue
        copied = _copy_ingredient_to_custom_project(
            project,
            source_path=audio.path,
            label=audio.label,
            source_kind="customized_profile_ingredient",
            motion_mode=audio.motion_mode or "stationary",
            trajectory_snapshot=audio.trajectory_snapshot,
            provenance={**provenance, "source_path": audio.path},
        )
        audio.path = copied


def _should_replace_saved_design_with_default_profile(design: StimulusDesign) -> bool:
    if design.study_profile_id == DEFAULT_STUDY_TEMPLATE_ID:
        return False
    if design.study_profile_id:
        return True
    mode = str(design.study_profile_reference_parameters.get("dashboard_mode", "")).strip().lower()
    if mode == "custom":
        return True
    return design.name.strip() in {"", "Study 5 PPS design", "Custom PPS design"}


def _project_metadata(design: StimulusDesign) -> dict[str, Any]:
    metadata = design.study_profile_reference_parameters.get(PROJECT_METADATA_KEY)
    return dict(metadata) if isinstance(metadata, dict) else {}


def _carry_forward_project_metadata(previous: StimulusDesign, incoming: StimulusDesign) -> StimulusDesign:
    incoming_metadata = _project_metadata(incoming)
    previous_metadata = _project_metadata(previous)
    incoming_mode = str(incoming.study_profile_reference_parameters.get("dashboard_mode", "")).strip().lower()
    previous_mode = str(previous.study_profile_reference_parameters.get("dashboard_mode", "")).strip().lower()
    same_custom_context = incoming_mode == previous_mode == "custom"
    same_profile_context = incoming.study_profile_id and incoming.study_profile_id == previous.study_profile_id
    same_project_context = bool(same_custom_context or same_profile_context)
    if (
        same_project_context
        and RUN_SETUP_METADATA_KEY not in incoming.study_profile_reference_parameters
        and RUN_SETUP_METADATA_KEY in previous.study_profile_reference_parameters
    ):
        incoming.study_profile_reference_parameters[RUN_SETUP_METADATA_KEY] = dict(previous.study_profile_reference_parameters[RUN_SETUP_METADATA_KEY])
    if not previous_metadata:
        return incoming
    if incoming_metadata and not (
        incoming_metadata.get("placeholder_name")
        and not previous_metadata.get("placeholder_name")
    ):
        return incoming
    if same_project_context:
        incoming.study_profile_reference_parameters[PROJECT_METADATA_KEY] = previous_metadata
    return incoming


def _project_slug(value: str, default: str = "project", *, max_length: int | None = None) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "").strip()).strip("_").lower()
    text = text or default
    if max_length is not None and max_length > 0 and len(text) > max_length:
        digest = hashlib.sha1(str(value or text).encode("utf-8")).hexdigest()[:6]
        if max_length <= len(digest):
            return digest[:max_length]
        prefix = text[: max_length - len(digest) - 1].rstrip("_")
        text = f"{prefix}_{digest}" if prefix else digest[:max_length]
    return text


def _placeholder_custom_project_name(value: str) -> bool:
    return str(value or "").strip().lower() in {"", "custom pps design", "untitled pps design"}


def _custom_project_id(name: str, registry_root: Path = DEFAULT_PROJECT_REGISTRY_ROOT) -> str:
    return generate_custom_profile_id(
        name,
        registry_root,
        max_slug_length=CUSTOM_PROJECT_ID_SLUG_MAX_LENGTH,
    )


def _profile_project_id(design: StimulusDesign) -> str:
    template_id = str(design.study_profile_id or DEFAULT_STUDY_TEMPLATE_ID or "default_profile").strip()
    return f"profile_{_project_slug(template_id, 'profile')}"


def _project_context_from_parts(
    *,
    registry_root: Path,
    project_id: str,
    project_kind: str,
    project_label: str,
    source_template_id: str = "",
    created_at: str = "",
    source_profile_id: str = "",
) -> DashboardProjectContext:
    registry_root = Path(registry_root)
    project_dir = registry_root / project_id
    shared_tactile = registry_root / "shared_assets" / "tactile" / DEFAULT_TACTILE_CUE_PATH.name
    return DashboardProjectContext(
        project_id=project_id,
        project_kind=project_kind,
        project_label=project_label,
        source_template_id=source_template_id,
        created_at=created_at or datetime.now().isoformat(timespec="seconds"),
        source_profile_id=source_profile_id,
        registry_root=registry_root,
        project_dir=project_dir,
        profile_dir=project_dir / "0_profile",
        segment1_dir=project_dir / "1_core_audio_ingredients",
        segment2_dir=project_dir / "2_trial_sequence_designs",
        segment3_dir=project_dir / "3_tactile_and_baseline_trials",
        segment4_dir=project_dir / "4_trial_repetition_pool",
        segment5_dir=project_dir / "5_block_csv_preview",
        segment6_dir=project_dir / "6_experiment_run_setup",
        shared_tactile_path=shared_tactile,
    )


def _registry_project_dir(registry_root: Path, project_id: str) -> Path:
    project_name = str(project_id or "").strip()
    if not project_name or Path(project_name).name != project_name:
        raise ValueError("Custom project id must be a single registry folder name.")
    root = Path(registry_root).resolve()
    project_dir = (root / project_name).resolve()
    if root != project_dir and root not in project_dir.parents:
        raise ValueError("Custom project path escapes the dashboard project registry.")
    return project_dir


def _custom_project_record(registry_root: Path, project_id: str) -> dict[str, Any] | None:
    project_dir = _registry_project_dir(registry_root, project_id)
    if not project_dir.exists() or not project_dir.is_dir():
        return None
    profile_dir = project_dir / "0_profile"
    manifest_path = profile_dir / "project_manifest.json"
    active_design_path = profile_dir / "active_design.json"
    if not active_design_path.exists():
        return None
    try:
        design = load_design(active_design_path)
    except Exception:
        return None
    if not _is_custom_design(design):
        return None
    manifest = _load_json(manifest_path)
    metadata = _project_metadata(design)
    project_label = str(
        manifest.get("project_label")
        or metadata.get("project_label")
        or design.name
        or project_dir.name
    )
    return {
        "project_id": project_dir.name,
        "project_label": project_label,
        "source_template_id": str(manifest.get("source_template_id") or metadata.get("source_template_id") or ""),
        "source_profile_id": str(manifest.get("source_profile_id") or metadata.get("source_profile_id") or ""),
        "created_at": str(manifest.get("created_at") or metadata.get("created_at") or ""),
        "project_dir": str(project_dir),
        "active_design_path": str(active_design_path),
    }


def _custom_project_records(registry_root: Path) -> list[dict[str, Any]]:
    root = Path(registry_root)
    if not root.exists():
        return []
    records: list[dict[str, Any]] = []
    for child in root.iterdir():
        if not child.is_dir() or not child.name.startswith("custom_"):
            continue
        try:
            record = _custom_project_record(root, child.name)
        except ValueError:
            continue
        if record is not None:
            records.append(record)
    return sorted(records, key=lambda item: (item.get("created_at", ""), item.get("project_id", "")), reverse=True)


def _project_context_from_design(design: StimulusDesign, registry_root: Path) -> DashboardProjectContext | None:
    metadata = _project_metadata(design)
    project_id = str(metadata.get("project_id") or "").strip()
    if not project_id:
        return None
    return _project_context_from_parts(
        registry_root=registry_root,
        project_id=project_id,
        project_kind=str(metadata.get("project_kind") or ("custom" if _is_custom_design(design) else "profile")),
        project_label=str(metadata.get("project_label") or design.name or project_id),
        source_template_id=str(metadata.get("source_template_id") or design.study_profile_id or ""),
        created_at=str(metadata.get("created_at") or ""),
        source_profile_id=str(metadata.get("source_profile_id") or ""),
    )


def _ensure_dashboard_project_context(
    design: StimulusDesign,
    registry_root: Path,
    *,
    force_new_custom: bool = False,
) -> DashboardProjectContext:
    if not force_new_custom:
        existing = _project_context_from_design(design, registry_root)
        if existing is not None:
            _ensure_project_directories(existing)
            return existing

    if _is_custom_design(design):
        project_id = _custom_project_id(design.name, registry_root)
        source_template_id = str(design.study_profile_reference_parameters.get("customized_from_profile_id") or "").strip()
        source_profile_id = str(design.study_profile_reference_parameters.get("source_profile_id") or source_template_id).strip()
        context = _project_context_from_parts(
            registry_root=registry_root,
            project_id=project_id,
            project_kind="custom",
            project_label=design.name.strip() or "Custom PPS design",
            source_template_id=source_template_id,
            source_profile_id=source_profile_id,
            created_at=datetime.now().isoformat(timespec="seconds"),
        )
    else:
        project_id = _profile_project_id(design)
        context = _project_context_from_parts(
            registry_root=registry_root,
            project_id=project_id,
            project_kind="profile",
            project_label=design.study_profile_title or design.name or project_id,
            source_template_id=design.study_profile_id,
        )

    _ensure_project_directories(context)
    design.study_profile_reference_parameters[PROJECT_METADATA_KEY] = {
        "schema": PROJECT_MANIFEST_SCHEMA,
        "project_id": context.project_id,
        "project_kind": context.project_kind,
        "project_label": context.project_label,
        "source_template_id": context.source_template_id,
        "source_profile_id": context.source_profile_id,
        "created_at": context.created_at,
        "placeholder_name": _is_custom_design(design) and _placeholder_custom_project_name(design.name),
    }
    return context


def _ensure_project_directories(context: DashboardProjectContext) -> None:
    for folder in [
        context.profile_dir,
        context.segment1_dir,
        context.segment2_dir,
        context.segment3_dir,
        context.segment4_dir,
        context.segment5_dir,
        context.segment6_dir,
    ]:
        _ensure_dir(folder)
    _ensure_dir(context.shared_tactile_path.parent)
    if _path_exists(DEFAULT_TACTILE_CUE_PATH):
        if not _path_exists(context.shared_tactile_path) or _local_file_sha256(context.shared_tactile_path) != _local_file_sha256(DEFAULT_TACTILE_CUE_PATH):
            _copy_file(DEFAULT_TACTILE_CUE_PATH, context.shared_tactile_path)


def _clear_downstream_segment_outputs(context: DashboardProjectContext, *, from_segment: int) -> None:
    targets: list[Path] = []
    if from_segment <= 1:
        targets.extend([context.segment2_dir, context.segment3_dir, context.segment4_dir, context.segment5_dir, context.segment6_dir])
    elif from_segment <= 2:
        targets.extend([context.segment3_dir, context.segment4_dir, context.segment5_dir, context.segment6_dir])
    elif from_segment <= 3:
        targets.extend([context.segment4_dir, context.segment5_dir, context.segment6_dir])
    elif from_segment <= 4:
        targets.extend([context.segment5_dir, context.segment6_dir])
    elif from_segment <= 5:
        targets.append(context.segment6_dir)
    for target in targets:
        resolved = target.resolve()
        project_resolved = context.project_dir.resolve()
        if project_resolved not in resolved.parents and resolved != project_resolved:
            raise RuntimeError(f"Refusing to clear a folder outside the active dashboard project: {target}")
        if target.resolve() == context.segment6_dir.resolve():
            _clear_segment6_generated_outputs(target)
        else:
            _remove_tree(target)
            _ensure_dir(target)


def _clear_segment6_generated_outputs(segment6_dir: Path) -> None:
    _ensure_dir(segment6_dir)
    keep = {"instruction_library"}
    for child in Path(segment6_dir).iterdir():
        if child.name in keep:
            continue
        if child.is_dir():
            _remove_tree(child)
        elif child.exists():
            child.unlink()


def _copy_materialize_ingredient_audio_file(path: Path, target_dir: Path, label: str, *, motion_mode: str = "") -> Path:
    source = Path(path)
    if not _path_exists(source):
        raise FileNotFoundError(f"Profile source audio is missing: {source}")
    duration_ms = _audio_file_duration_ms(source)
    stem = _ingredient_descriptor(label, duration_ms, motion_mode=motion_mode)
    suffix = source.suffix or ".wav"
    descriptor = _descriptor_label(stem)
    target = target_dir / f"{descriptor}{suffix}"
    try:
        source_hash = _local_file_sha256(source)
        for candidate in sorted(target_dir.glob(f"{descriptor}*{suffix}")):
            if _path_exists(candidate) and _local_file_sha256(candidate) == source_hash:
                return candidate
    except OSError:
        pass
    if _path_exists(target):
        try:
            if _local_file_sha256(target) == _local_file_sha256(source):
                return target
        except OSError:
            pass
        target = _unique_output_path(target_dir, stem, suffix)
    _copy_file(source, target)
    return target


def _materialize_study_profile_segment1_ingredients(project: DashboardProjectContext, design: StimulusDesign) -> None:
    assets = _preload_assets_by_label(design.study_profile_id)
    for noise in design.noises:
        source_path = _resolve_dashboard_local_path(noise.prebaked_path)
        asset = assets.get(_source_key(noise.label), {})
        trajectory_snapshot = noise.trajectory_snapshot or dict(asset.get("trajectory_snapshot") or {})
        target_path = _copy_materialize_ingredient_audio_file(
            source_path,
            project.segment1_dir,
            noise.label,
            motion_mode="looming",
        )
        noise.prebaked_path = str(target_path)
        if trajectory_snapshot:
            noise.trajectory_snapshot = trajectory_snapshot
        _record_ingredient_file(
            project,
            target_path,
            label=noise.label,
            source_kind=str(asset.get("source_kind") or "preload_catalog"),
            trajectory_snapshot=trajectory_snapshot,
            motion_mode="looming",
            provenance={
                "source_catalog_path": str(source_path),
                "source_catalog_sha256": str(asset.get("sha256") or ""),
                "read_only_catalog": True,
                "loudness_policy": loudness_policy_for_design(design),
            },
        )
    for audio in design.custom_looming_files:
        source_path = _resolve_dashboard_local_path(audio.path)
        asset = assets.get(_source_key(audio.label), {})
        trajectory_snapshot = audio.trajectory_snapshot or dict(asset.get("trajectory_snapshot") or {})
        target_path = _copy_materialize_ingredient_audio_file(
            source_path,
            project.segment1_dir,
            audio.label,
            motion_mode=audio.motion_mode or "looming",
        )
        info = _audio_file_info(target_path)
        audio.path = str(target_path)
        audio.motion_mode = audio.motion_mode or "looming"
        audio.render_mode = "preserve"
        audio.target_duration_s = float(info["duration_s"])
        if not audio.tone_type:
            audio.tone_type = str(asset.get("noise_type") or asset.get("tone_type") or CUSTOM_AUDIO_NOISE_TYPE)
        if trajectory_snapshot:
            audio.trajectory_snapshot = trajectory_snapshot
        _record_ingredient_file(
            project,
            target_path,
            label=audio.label,
            source_kind=str(asset.get("source_kind") or "profile_looming_audio"),
            trajectory_snapshot=trajectory_snapshot,
            motion_mode=audio.motion_mode or "looming",
            provenance={
                "source_catalog_path": str(source_path),
                "source_catalog_sha256": str(asset.get("sha256") or ""),
                "read_only_catalog": True,
            },
        )
    for audio in design.prestimulus_files:
        source_path = _resolve_dashboard_local_path(audio.path)
        target_path = _copy_materialize_ingredient_audio_file(
            source_path,
            project.segment1_dir,
            audio.label,
            motion_mode="stationary",
        )
        info = _audio_file_info(target_path)
        audio.path = str(target_path)
        audio.motion_mode = "stationary"
        audio.render_mode = "preserve"
        audio.target_duration_s = float(info["duration_s"])
        _record_ingredient_file(
            project,
            target_path,
            label=audio.label,
            source_kind="profile_fixed_audio",
            trajectory_snapshot={},
            motion_mode="stationary",
            provenance={
                "source_catalog_path": str(source_path),
                "read_only_catalog": True,
                "loudness_policy": loudness_policy_for_design(design),
            },
        )


def _gui_setting_record(
    *,
    key: str,
    value: Any,
    segment: str,
    label: str = "",
    control: str = "",
    note: str = "",
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label or key.replace("_", " ").title(),
        "segment": segment,
        "control": control,
        "value": value,
        "note": note,
    }


def _study_settings_manifest(context: DashboardProjectContext, design: StimulusDesign) -> dict[str, Any]:
    protocol = design.protocol
    profile_recreation = _profile_recreation_status_for_design(design)
    baseline_anchors = _baseline_anchor_specs(design)
    trial_rows = []
    for row_index, strip in enumerate(protocol.trial_strips, start=1):
        if not strip.elements:
            continue
        trial_rows.append({
            "row_index": row_index,
            "row_id": strip.strip_id,
            "label": strip.label,
            "audio_tactile_percentage": strip.audio_tactile_percentage,
            "catch_percentage": strip.catch_percentage,
            "baseline_percentage": strip.baseline_percentage,
            "elements": [
                {
                    "kind": element.kind,
                    "label": element.label,
                    "source_label": element.source_label,
                    "source_labels": list(element.source_labels),
                    "jitter_values_ms": list(element.jitter_values_ms),
                    "randomized": bool(element.randomized),
                }
                for element in strip.elements
            ],
        })
    baseline_note = (
        "Empty baseline_soa_values_ms means full-SOA baseline generation uses the main soa_values_ms list."
        if protocol.include_baseline_trials
        and str(protocol.baseline_strategy or "").strip().lower() == "tactile_only"
        and not protocol.baseline_soa_values_ms
        else ""
    )
    trial_pool_defaults = _protocol_trial_pool_repetition_defaults(design)
    loudness_policy = loudness_policy_for_design(design)
    gui_settings_inventory = {
        record["key"]: record
        for record in [
            _gui_setting_record(
                key="study_profile_id",
                value=design.study_profile_id,
                segment="0_profile",
                label="Study profile",
                control="profile selector",
            ),
            _gui_setting_record(
                key="project_name",
                value=design.name,
                segment="0_profile",
                label="Project/design name",
                control="text input",
            ),
            _gui_setting_record(
                key="core_audio_source_count",
                value=len(design.noises) + len(design.custom_looming_files) + len(design.prestimulus_files),
                segment="1_core_audio_ingredients",
                label="Core audio ingredients",
                control="Bake Ingredient",
            ),
            _gui_setting_record(
                key="loudness_start_spl_db",
                value=loudness_policy["start_spl_db"],
                segment="1_core_audio_ingredients",
                label="Looming start SPL",
                control="Start dB SPL input",
                note="0.5 s pre-hold stays at this level before active movement.",
            ),
            _gui_setting_record(
                key="loudness_end_spl_db",
                value=loudness_policy["end_spl_db"],
                segment="1_core_audio_ingredients",
                label="Looming endpoint SPL",
                control="Endpoint dB SPL input",
                note="Final active movement window and 0.5 s post-hold use this endpoint level.",
            ),
            _gui_setting_record(
                key="instruction_offset_db",
                value=loudness_policy["instruction_offset_db"],
                segment="1_core_audio_ingredients",
                label="Instruction loudness offset",
                control="Instruction offset dB input",
                note="Fixed instruction clips are attenuated by this dB offset relative to the looming endpoint target.",
            ),
            _gui_setting_record(
                key="estimated_full_scale_spl_db",
                value=loudness_policy["estimated_full_scale_spl_db"],
                segment="1_core_audio_ingredients",
                label="Estimated full-scale SPL",
                control="loudness policy metadata",
                note="Estimated hardware correspondence for Komplete Audio 6 MK2 at max headphone output and Sennheiser HD 560S; replace with measured value after coupler calibration.",
            ),
            _gui_setting_record(
                key="loudness_calibration_status",
                value=loudness_policy["calibration_status"],
                segment="1_core_audio_ingredients",
                label="Loudness calibration status",
                control="loudness policy metadata",
                note="Estimated values are not a substitute for physical SPL measurement.",
            ),
            _gui_setting_record(
                key="trial_sequence_rows",
                value=len(trial_rows),
                segment="2_trial_sequence_designs",
                label="Trial sequence rows",
                control="Bake Trial Sequences",
            ),
            _gui_setting_record(
                key="soa_values_ms",
                value=list(protocol.soa_values_ms),
                segment="3_tactile_and_baseline_trials",
                label="SOA values",
                control="SOA input",
            ),
            _gui_setting_record(
                key="include_catch_trials",
                value=bool(getattr(protocol, "include_catch_trials", False)),
                segment="3_tactile_and_baseline_trials",
                label="Generate catch files",
                control="Include Catch Trials (audio only) checkbox",
                note="Segment 3 only creates audio-only files that can later be used as catch trials; scheduling is not defined here.",
            ),
            _gui_setting_record(
                key="include_baseline_trials",
                value=bool(protocol.include_baseline_trials),
                segment="3_tactile_and_baseline_trials",
                label="Generate baseline files",
                control="baseline strategy cards",
            ),
            _gui_setting_record(
                key="baseline_strategy",
                value=protocol.baseline_strategy,
                segment="3_tactile_and_baseline_trials",
                label="Baseline strategy",
                control="baseline strategy cards",
                note=baseline_note,
            ),
            _gui_setting_record(
                key="baseline_custom_trial_mode",
                value=protocol.baseline_custom_trial_mode,
                segment="3_tactile_and_baseline_trials",
                label="Baseline file mode",
                control="tactile-only/audio-tactile toggle",
            ),
            _gui_setting_record(
                key="baseline_soa_values_ms",
                value=list(protocol.baseline_soa_values_ms),
                segment="3_tactile_and_baseline_trials",
                label="Custom baseline SOAs",
                control="custom baseline timing input",
                note=baseline_note,
            ),
            _gui_setting_record(
                key="effective_baseline_soa_values_ms",
                value=[int(anchor["soa_ms"]) for anchor in baseline_anchors],
                segment="3_tactile_and_baseline_trials",
                label="Effective baseline SOAs",
                control="derived from baseline strategy",
                note=baseline_note,
            ),
            _gui_setting_record(
                key="baseline_scheduling_percentages",
                value=[row["baseline_percentage"] for row in trial_rows],
                segment="legacy_trial_composition",
                label="Row baseline scheduling percentages",
                control="trial composition row overrides",
                note="Legacy scheduler percentages are retained for compatibility; Segment 4 now writes a CSV trial pool by repetition count.",
            ),
            _gui_setting_record(
                key="trial_pool_default_repetitions",
                value=_json_repetition_value(float(trial_pool_defaults["default_repetitions"])),
                segment="4_trial_repetition_pool",
                label="Default trial-pool repetitions",
                control="Set all folders to",
                note="Segment 4 repeats Segment 3 WAV references in a CSV manifest; it does not duplicate WAV files or define blocks.",
            ),
            _gui_setting_record(
                key="trial_pool_family_repetitions",
                value={
                    key: _json_repetition_value(float(value))
                    for key, value in trial_pool_defaults["family_repetitions"].items()
                },
                segment="4_trial_repetition_pool",
                label="Family trial-pool repetitions",
                control="family default preset",
                note="Half-step values use deterministic balanced fractional sampling across row, SOA, and source lineage.",
            ),
        ]
    }
    expected = _expected_segment_counts(design, context.project_dir)
    return {
        "schema": STUDY_SETTINGS_MANIFEST_SCHEMA,
        "written_at": datetime.now().isoformat(timespec="seconds"),
        "project": context.to_dict(),
        "study": {
            "profile_id": design.study_profile_id,
            "title": design.study_profile_title,
            "design_name": design.name,
            "notes": design.study_profile_notes,
            "reference_parameters": design.study_profile_reference_parameters,
            "loudness_policy": loudness_policy,
            "profile_parameters_manifest": profile_recreation.get("profile_parameters_manifest", ""),
            "recreation_status": dict(profile_recreation.get("recreation_status") or {}),
            "runner_readiness": profile_recreation.get("runner_readiness", ""),
            "profile_checks_passed": bool(profile_recreation.get("profile_checks_passed", False)),
            "segment_0_to_4_profile_checks_passed": bool(
                profile_recreation.get("segment_0_to_4_profile_checks_passed", False)
            ),
            "finished_profile": bool(profile_recreation.get("finished_profile", False)),
            "segment_6_launchable": bool(profile_recreation.get("segment_6_launchable", False)),
            "profile_completion_status": profile_recreation.get("profile_completion_status", "unfinished_preload"),
            "primary_recreation_category": profile_recreation.get("primary_recreation_category", ""),
            "missing_parameter_count": int(profile_recreation.get("missing_parameter_count") or 0),
            "unsupported_structure_count": int(profile_recreation.get("unsupported_structure_count") or 0),
        },
        "default_settings": {
            "protocol": {
                "soa_values_ms": list(protocol.soa_values_ms),
                "spatial_values_cm": list(protocol.spatial_values_cm),
                "include_catch_trials": bool(getattr(protocol, "include_catch_trials", False)),
                "include_baseline_trials": bool(protocol.include_baseline_trials),
                "baseline_strategy": protocol.baseline_strategy,
                "baseline_custom_trial_mode": protocol.baseline_custom_trial_mode,
                "baseline_soa_values_ms": list(protocol.baseline_soa_values_ms),
                "catch_trial_percentage": protocol.catch_trial_percentage,
                "baseline_trial_percentage": protocol.baseline_trial_percentage,
                "repetitions_per_condition": protocol.repetitions_per_condition,
                "blocks": protocol.blocks,
                "participants": protocol.participants,
            },
            "baseline_generation": {
                "enabled": bool(protocol.include_baseline_trials and str(protocol.baseline_strategy or "").strip().lower() != "none"),
                "strategy": protocol.baseline_strategy,
                "mode": protocol.baseline_custom_trial_mode,
                "baseline_soa_values_ms": list(protocol.baseline_soa_values_ms),
                "effective_soa_values_ms": [int(anchor["soa_ms"]) for anchor in baseline_anchors],
                "full_soa_uses_main_soa_values": bool(
                    protocol.include_baseline_trials
                    and str(protocol.baseline_strategy or "").strip().lower() == "tactile_only"
                    and not protocol.baseline_soa_values_ms
                ),
            },
            "catch_generation": {
                "enabled": bool(getattr(protocol, "include_catch_trials", False)),
                "mode": "audio_only",
                "source": "Segment 2 trial-sequence WAVs copied and renamed into Segment 3 catch folders",
                "scheduling": "not defined in Segment 3",
            },
            "trial_pool_generation": {
                "segment": "4_trial_repetition_pool",
                "default_repetitions": _json_repetition_value(float(trial_pool_defaults["default_repetitions"])),
                "family_repetitions": {
                    key: _json_repetition_value(float(value))
                    for key, value in trial_pool_defaults["family_repetitions"].items()
                },
                "fractional_repetition_step": 0.5,
                "fractional_sampling": "deterministic balanced extra rows by family, row/phase, SOA, and source lineage",
                "mode": "csv_references_only",
                "output_files": ["trial_repetition_pool.csv", "trial_repetition_pool_manifest.json"],
                "duplicates_wavs": False,
                "blocks_defined_here": False,
            },
            "loudness_policy": loudness_policy,
            "trial_rows": trial_rows,
        },
        "gui_settings_inventory": gui_settings_inventory,
        "segment_expectations": expected,
    }


def _write_project_context_files(context: DashboardProjectContext, design: StimulusDesign) -> None:
    _ensure_project_directories(context)
    manifest = {
        **context.to_dict(),
        "active_design_path": str(context.profile_dir / "active_design.json"),
        "study_manifest_path": str(context.profile_dir / "study_manifest.json"),
    }
    _write_text_file(context.profile_dir / "project_manifest.json", json.dumps(_json_ready(manifest), indent=2) + "\n", encoding="utf-8")
    _write_text_file(
        context.profile_dir / "study_manifest.json",
        json.dumps(_json_ready(_study_settings_manifest(context, design)), indent=2) + "\n",
        encoding="utf-8",
    )
    _save_design_file(design, context.profile_dir / "active_design.json")


def _project_has_generated_outputs(project_dir: Path) -> bool:
    project_dir = Path(project_dir)
    manifest_candidates = [
        project_dir / "1_core_audio_ingredients" / "stimulus_ingredients_manifest.json",
        project_dir / "2_trial_sequence_designs" / "trial_sequence_variants_manifest.json",
        project_dir / "3_tactile_and_baseline_trials" / "baseline_tactile_trial_files_manifest.json",
        project_dir / "4_trial_repetition_pool" / "trial_repetition_pool_manifest.json",
        project_dir / "5_block_csv_preview" / "block_csv_preview_manifest.json",
        project_dir / "6_experiment_run_setup" / "experiment_run_setup_manifest.json",
    ]
    if any(_path_exists(path) for path in manifest_candidates):
        return True
    for folder_name in ("1_core_audio_ingredients", "2_trial_sequence_designs", "3_tactile_and_baseline_trials"):
        folder = project_dir / folder_name
        if _path_exists(folder):
            for _root, _dirs, files in os.walk(_filesystem_path(folder)):
                if any(str(name).lower().endswith(".wav") for name in files):
                    return True
    return False


def _should_refresh_placeholder_custom_project(design: StimulusDesign, registry_root: Path) -> bool:
    if not _is_custom_design(design) or _placeholder_custom_project_name(design.name):
        return False
    metadata = _project_metadata(design)
    if not metadata.get("placeholder_name"):
        return False
    context = _project_context_from_design(design, registry_root)
    return context is not None and not _project_has_generated_outputs(context.project_dir)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(_read_text_file(Path(path), encoding="utf-8"))
    except Exception:
        return {}


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _stable_json_hash(value: Any) -> str:
    payload = json.dumps(_json_ready(value), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _segment2_design_signature(design: StimulusDesign) -> str:
    return _stable_json_hash(
        {
            "trial_strips": [asdict(strip) for strip in design.protocol.trial_strips],
            "required_segment1_labels": _required_segment1_labels_for_trial_sequences(design),
            "loudness_policy": loudness_policy_for_design(design),
        }
    )


def _segment3_design_signature(design: StimulusDesign) -> str:
    protocol = design.protocol
    return _stable_json_hash(
        {
            "soa_values_ms": list(protocol.soa_values_ms),
            "include_catch_trials": bool(getattr(protocol, "include_catch_trials", False)),
            "include_baseline_trials": bool(protocol.include_baseline_trials),
            "baseline_strategy": str(protocol.baseline_strategy or ""),
            "baseline_soa_values_ms": list(protocol.baseline_soa_values_ms),
            "baseline_custom_trial_mode": str(protocol.baseline_custom_trial_mode or ""),
            "loudness_policy": loudness_policy_for_design(design),
        }
    )


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_filename(value: str) -> str:
    name = Path(value).name.strip() or "audio.wav"
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._")
    return safe or "audio.wav"


def _slug(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip()).strip("._")
    return safe or "stimulus"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch the local PPS browser dashboard.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind. Defaults to local-only 127.0.0.1.")
    parser.add_argument("--port", type=int, default=8766, help="Port for the local dashboard.")
    parser.add_argument("--no-browser", action="store_true", help="Start the server without opening a browser.")
    parser.add_argument("--design", type=Path, default=DEFAULT_DESIGN_PATH, help="Working design JSON path.")
    parser.add_argument("--render-dir", type=Path, default=DEFAULT_RENDER_DIR, help="Rendered stimulus handoff directory.")
    parser.add_argument("--session-root", type=Path, default=DEFAULT_SESSION_ROOT, help="Session output root directory.")
    parser.add_argument("--project-registry-root", type=Path, default=DEFAULT_PROJECT_REGISTRY_ROOT, help="Dashboard project registry root.")
    parser.add_argument(
        "--web-origin",
        action="append",
        default=[],
        help="Allow one hosted dashboard origin to call this local backend, for example https://user.github.io.",
    )
    parser.add_argument(
        "--no-default-web-origin",
        action="store_true",
        help="Do not allow the default project GitHub Pages origin.",
    )
    parser.add_argument(
        "--companion-token",
        default="",
        help="Token required in X-PPS-Companion-Token for mutating local companion API calls.",
    )
    parser.add_argument(
        "--require-companion-token",
        action="store_true",
        help="Require a per-launch token for mutating local companion API calls. Generates one if --companion-token is omitted.",
    )
    return parser


def _running_dashboard_url(host: str, port: int) -> str | None:
    url = f"http://{host}:{port}/"
    try:
        with urllib.request.urlopen(f"{url}api/state", timeout=1.5) as response:
            if response.status == 200:
                return url
    except Exception:
        return None
    return None


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    url = f"http://{args.host}:{args.port}/"
    running_url = _running_dashboard_url(args.host, args.port)
    if running_url is not None:
        print(f"PPS dashboard is already running at {running_url}")
        if not args.no_browser:
            webbrowser.open(running_url)
        return 0

    app = create_app(
        DashboardController(
            design_path=args.design,
            render_dir=args.render_dir,
            session_root=args.session_root,
            project_registry_root=args.project_registry_root,
        ),
        web_origins=[] if args.no_default_web_origin else [*DEFAULT_WEB_ORIGINS, *args.web_origin],
        companion_token=args.companion_token or None,
        require_mutation_token=args.require_companion_token or None,
    )
    security = getattr(app.state, "companion_security", None)
    if getattr(security, "enabled", False):
        print(f"Local companion mutation token: {security.token}")
        print("Hosted/static dashboards must send it as X-PPS-Companion-Token for mutating actions.")
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("Install the web extra to run the dashboard: pip install -e .[web]") from exc
    print(f"PPS dashboard running at {url}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
