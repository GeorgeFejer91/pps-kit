"""Tkinter stimulus designer for custom PPS looming designs."""

from __future__ import annotations

import argparse
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .design import (
    AudioFileSpec,
    BlockSpec,
    NoiseDefinition,
    ProtocolSpec,
    SUPPORTED_BLOCK_ORDER_RANDOMIZATION,
    SUPPORTED_TRIAL_RANDOMIZATION,
    StimulusDesign,
    TrajectorySpec,
    audio_file_summary,
    default_design,
    effective_block_specs,
    export_protocol_csv,
    export_trajectory_csv,
    load_design,
    protocol_summary,
    save_design,
    snap_noises_to_sofa,
    sofa_summary,
    trajectory_points,
    validate_design,
)
from .templates import StudyTemplate, load_templates


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DESIGN_PATH = REPO_ROOT / "configs" / "stimulus_design.generated.json"
TEMPLATE_DIR = REPO_ROOT / "study_templates"
PALETTE = {
    "window": "#f6f1ea",
    "surface": "#fffbf5",
    "surface_alt": "#eee5dc",
    "border": "#d5c8ba",
    "text": "#2f2a24",
    "muted": "#6f6257",
    "primary": "#8f4d2e",
    "primary_active": "#77402a",
    "accent": "#2f7d73",
    "canvas": "#15110e",
    "canvas_grid": "#3a3028",
    "canvas_text": "#f2e7d8",
}


class StimulusDesignerApp:
    def __init__(self, root: tk.Tk, design_path: Path = DEFAULT_DESIGN_PATH):
        self.root = root
        self.design_path = design_path
        self.design = load_design(design_path) if design_path.exists() else default_design()
        self.noises: list[NoiseDefinition] = list(self.design.noises)
        self.block_specs: list[BlockSpec] = effective_block_specs(self.design.protocol)
        self.custom_looming_files: list[AudioFileSpec] = list(self.design.custom_looming_files)
        self.prestimulus_files: list[AudioFileSpec] = list(self.design.prestimulus_files)
        self.templates: list[StudyTemplate] = load_templates(TEMPLATE_DIR)

        self.root.title("Peripersonal Space Toolkit - Stimulus Designer")
        self.root.geometry("1180x780")
        self.root.minsize(1020, 680)
        self._configure_style()

        self.name_var = tk.StringVar()
        self.sofa_var = tk.StringVar()
        self.noise_label_var = tk.StringVar()
        self.noise_type_var = tk.StringVar()
        self.noise_azimuth_var = tk.StringVar()
        self.noise_elevation_var = tk.StringVar()
        self.noise_gain_var = tk.StringVar()
        self.audio_preload_type_var = tk.StringVar(value="Looming")
        self.audio_preload_label_var = tk.StringVar()
        self.audio_preload_path_var = tk.StringVar()
        self.audio_preload_duration_var = tk.StringVar(value="4.0")
        self.template_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready.")

        self.traj_vars = {
            "start_radius_m": tk.StringVar(),
            "end_radius_m": tk.StringVar(),
            "path_direction": tk.StringVar(),
            "path_length_m": tk.StringVar(),
            "propagation_speed_mps": tk.StringVar(),
            "azimuth_start_deg": tk.StringVar(),
            "azimuth_end_deg": tk.StringVar(),
            "elevation_deg": tk.StringVar(),
            "padding_pre_s": tk.StringVar(),
            "padding_post_s": tk.StringVar(),
        }
        self.protocol_vars = {
            "repetitions_per_condition": tk.StringVar(),
            "soa_values_ms": tk.StringVar(),
            "spatial_values_cm": tk.StringVar(),
            "auditory_motion_directions": tk.StringVar(),
            "tactile_sites": tk.StringVar(),
            "catch_trial_percentage": tk.StringVar(),
            "catch_trials_exact": tk.StringVar(),
            "baseline_soa_values_ms": tk.StringVar(),
            "respiratory_phases": tk.StringVar(),
            "blocks": tk.StringVar(),
            "trial_randomization_strategy": tk.StringVar(),
            "block_order_randomization": tk.StringVar(),
            "max_consecutive_same_trial_type": tk.StringVar(),
            "participants": tk.StringVar(),
            "random_seed": tk.StringVar(),
        }
        self.block_label_var = tk.StringVar()
        self.block_audio_tactile_var = tk.BooleanVar(value=True)
        self.block_baseline_var = tk.BooleanVar(value=True)
        self.block_catch_var = tk.BooleanVar(value=True)
        self.pair_spatial_values_var = tk.BooleanVar()
        self.include_baseline_var = tk.BooleanVar()

        self._build_ui()
        self._load_into_fields(self.design)
        self._update_preview()

    def _configure_style(self) -> None:
        self.root.configure(background=PALETTE["window"])
        self.root.option_add("*Font", "Aptos 10")
        self.root.option_add("*TCombobox*Listbox.background", PALETTE["surface"])
        self.root.option_add("*TCombobox*Listbox.foreground", PALETTE["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", PALETTE["primary"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=PALETTE["window"], foreground=PALETTE["text"], font=("Aptos", 10))
        style.configure("TFrame", background=PALETTE["window"])
        style.configure("TLabel", background=PALETTE["window"], foreground=PALETTE["text"])
        style.configure("TLabelframe", background=PALETTE["window"], bordercolor=PALETTE["border"], relief="solid")
        style.configure("TLabelframe.Label", background=PALETTE["window"], foreground=PALETTE["text"], font=("Aptos", 10, "bold"))
        style.configure("TNotebook", background=PALETTE["window"], borderwidth=0)
        style.configure("TNotebook.Tab", background=PALETTE["surface_alt"], foreground=PALETTE["muted"], padding=(10, 5))
        style.map(
            "TNotebook.Tab",
            background=[("selected", PALETTE["surface"]), ("active", PALETTE["surface"])],
            foreground=[("selected", PALETTE["text"]), ("active", PALETTE["text"])],
        )
        style.configure(
            "TButton",
            background=PALETTE["surface_alt"],
            foreground=PALETTE["text"],
            bordercolor=PALETTE["border"],
            focusthickness=1,
            focuscolor=PALETTE["accent"],
            padding=(8, 3),
        )
        style.map(
            "TButton",
            background=[("active", "#e6d8ca"), ("pressed", "#ddcbbb")],
            foreground=[("disabled", PALETTE["muted"])],
        )
        style.configure(
            "TEntry",
            fieldbackground=PALETTE["surface"],
            foreground=PALETTE["text"],
            bordercolor=PALETTE["border"],
            insertcolor=PALETTE["text"],
            padding=(4, 2),
        )
        style.configure(
            "TSpinbox",
            fieldbackground=PALETTE["surface"],
            foreground=PALETTE["text"],
            bordercolor=PALETTE["border"],
            arrowsize=12,
        )
        style.configure(
            "TCombobox",
            fieldbackground=PALETTE["surface"],
            background=PALETTE["surface_alt"],
            foreground=PALETTE["text"],
            bordercolor=PALETTE["border"],
            arrowcolor=PALETTE["muted"],
            padding=(4, 2),
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", PALETTE["surface"])],
            foreground=[("readonly", PALETTE["text"])],
        )
        style.configure(
            "Treeview",
            background=PALETTE["surface"],
            fieldbackground=PALETTE["surface"],
            foreground=PALETTE["text"],
            bordercolor=PALETTE["border"],
            rowheight=23,
        )
        style.configure(
            "Treeview.Heading",
            background=PALETTE["surface_alt"],
            foreground=PALETTE["text"],
            relief="flat",
            font=("Aptos", 10, "bold"),
        )
        style.map("Treeview", background=[("selected", PALETTE["primary"])], foreground=[("selected", "#ffffff")])
        style.configure("TCheckbutton", background=PALETTE["window"], foreground=PALETTE["text"])

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=8)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        header = ttk.LabelFrame(outer, text="Design")
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="Name").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        ttk.Entry(header, textvariable=self.name_var, width=44).grid(row=0, column=1, sticky="ew", padx=6, pady=4)
        ttk.Label(header, text="Preload").grid(row=0, column=2, sticky="w", padx=6, pady=4)
        template_values = [f"{item.title} [{item.verification_status}]" for item in self.templates]
        self.template_combo = ttk.Combobox(
            header,
            textvariable=self.template_var,
            values=template_values,
            state="readonly",
        )
        self.template_combo.grid(row=0, column=3, sticky="ew", padx=6, pady=4)
        ttk.Button(header, text="Load Template", command=self._load_template_clicked).grid(row=0, column=4, padx=4, pady=4)
        header.columnconfigure(1, weight=1)
        header.columnconfigure(3, weight=2)

        notebook = ttk.Notebook(outer)
        notebook.grid(row=1, column=0, sticky="nsew", pady=(8, 6))

        stimulus_tab = ttk.Frame(notebook, padding=6)
        trial_tab = ttk.Frame(notebook, padding=6)
        notebook.add(stimulus_tab, text="Stimulus Design")
        notebook.add(trial_tab, text="Trial Design")

        stimulus_body = ttk.PanedWindow(stimulus_tab, orient="horizontal")
        stimulus_body.pack(fill="both", expand=True)
        stimulus_left = ttk.Frame(stimulus_body, padding=(0, 0, 8, 0))
        stimulus_right = ttk.Frame(stimulus_body)
        stimulus_body.add(stimulus_left, weight=2)
        stimulus_body.add(stimulus_right, weight=3)

        self._build_sofa_panel(stimulus_left)
        self._build_noise_panel(stimulus_left)
        self._build_audio_preload_panel(stimulus_left)
        self._build_trajectory_panel(stimulus_right)
        self._build_protocol_panel(trial_tab)

        footer = ttk.Frame(outer)
        footer.grid(row=2, column=0, sticky="ew")
        ttk.Label(footer, textvariable=self.status_var).pack(side="left", fill="x", expand=True)
        ttk.Button(footer, text="Load File", command=self._load_clicked).pack(side="right", padx=4)
        ttk.Button(footer, text="Save As", command=self._save_clicked).pack(side="right", padx=4)
        ttk.Button(footer, text="Load Settings", command=self._load_settings_clicked).pack(side="right", padx=4)
        ttk.Button(footer, text="Save Settings", command=self._save_settings_clicked).pack(side="right", padx=4)
        ttk.Button(footer, text="Export Protocol", command=self._export_protocol_clicked).pack(side="right", padx=4)
        ttk.Button(footer, text="Export Trajectory", command=self._export_trajectory_clicked).pack(side="right", padx=4)
        ttk.Button(footer, text="Check", command=self._check_design).pack(side="right", padx=4)

    def _build_sofa_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.LabelFrame(parent, text="SOFA / HRIR Source")
        panel.pack(fill="x", pady=(0, 6))
        ttk.Label(panel, text="SOFA file").grid(row=0, column=0, sticky="w", padx=8, pady=5)
        ttk.Entry(panel, textvariable=self.sofa_var).grid(row=0, column=1, sticky="ew", padx=4, pady=5)
        ttk.Button(panel, text="Browse", command=self._browse_sofa).grid(row=0, column=2, padx=4, pady=5)
        ttk.Button(panel, text="Validate", command=self._validate_sofa).grid(row=0, column=3, padx=(4, 8), pady=5)
        panel.columnconfigure(1, weight=1)

    def _build_noise_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.LabelFrame(parent, text="Noise Types And Orientations")
        panel.pack(fill="x", pady=(0, 6))

        self.noise_tree = ttk.Treeview(
            panel,
            columns=("label", "type", "azimuth", "elevation", "gain"),
            show="headings",
            height=4,
        )
        for column, label, width in [
            ("label", "Label", 140),
            ("type", "Type", 80),
            ("azimuth", "Azimuth", 80),
            ("elevation", "Elevation", 80),
            ("gain", "Gain", 70),
        ]:
            self.noise_tree.heading(column, text=label)
            self.noise_tree.column(column, width=width, anchor="center")
        self.noise_tree.pack(fill="x", padx=8, pady=6)
        self.noise_tree.bind("<<TreeviewSelect>>", self._noise_selected)

        form = ttk.Frame(panel)
        form.pack(fill="x", padx=8)
        labels = ["Label", "Type", "Azimuth", "Elevation", "Gain"]
        for idx, text in enumerate(labels):
            ttk.Label(form, text=text).grid(row=0, column=idx, sticky="w", padx=3)

        ttk.Entry(form, textvariable=self.noise_label_var, width=16).grid(row=1, column=0, sticky="ew", padx=3, pady=4)
        ttk.Combobox(
            form,
            textvariable=self.noise_type_var,
            values=("pink", "blue", "white", "brown"),
            width=8,
            state="readonly",
        ).grid(row=1, column=1, padx=3, pady=4)
        ttk.Spinbox(form, textvariable=self.noise_azimuth_var, from_=-180, to=180, increment=1, width=8).grid(row=1, column=2, padx=3, pady=4)
        ttk.Spinbox(form, textvariable=self.noise_elevation_var, from_=-90, to=90, increment=1, width=8).grid(row=1, column=3, padx=3, pady=4)
        ttk.Spinbox(form, textvariable=self.noise_gain_var, from_=0.1, to=2.0, increment=0.1, width=8).grid(row=1, column=4, padx=3, pady=4)
        form.columnconfigure(0, weight=1)

        buttons = ttk.Frame(panel)
        buttons.pack(fill="x", padx=8, pady=(2, 6))
        ttk.Button(buttons, text="Add / Update", command=self._add_or_update_noise).pack(side="left", padx=2)
        ttk.Button(buttons, text="Remove", command=self._remove_noise).pack(side="left", padx=2)
        ttk.Button(buttons, text="Snap To SOFA", command=self._snap_noises).pack(side="left", padx=2)

    def _build_audio_preload_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.LabelFrame(parent, text="Custom Audio Preloads")
        panel.pack(fill="both", expand=True)

        self.audio_preload_tree = ttk.Treeview(
            panel,
            columns=("type", "label", "target", "path"),
            show="headings",
            height=1,
        )
        for column, label, width, anchor in [
            ("type", "Type", 78, "center"),
            ("label", "Label", 110, "w"),
            ("target", "Target s", 70, "center"),
            ("path", "File", 190, "w"),
        ]:
            self.audio_preload_tree.heading(column, text=label)
            self.audio_preload_tree.column(column, width=width, anchor=anchor)
        self.audio_preload_tree.pack(fill="x", padx=8, pady=6)
        self.audio_preload_tree.bind("<<TreeviewSelect>>", self._audio_preload_selected)

        form = ttk.Frame(panel)
        form.pack(fill="x", padx=8)
        for idx, text in enumerate(["Type", "Label", "Target s"]):
            ttk.Label(form, text=text).grid(row=0, column=idx, sticky="w", padx=3)
        ttk.Combobox(
            form,
            textvariable=self.audio_preload_type_var,
            values=("Looming", "Prestimulus"),
            width=12,
            state="readonly",
        ).grid(row=1, column=0, sticky="ew", padx=3, pady=4)
        ttk.Entry(form, textvariable=self.audio_preload_label_var, width=16).grid(row=1, column=1, sticky="ew", padx=3, pady=4)
        ttk.Spinbox(form, textvariable=self.audio_preload_duration_var, from_=0.1, to=60.0, increment=0.1, width=8).grid(row=1, column=2, sticky="w", padx=3, pady=4)
        ttk.Label(form, text="File").grid(row=2, column=0, sticky="w", padx=3, pady=2)
        ttk.Entry(form, textvariable=self.audio_preload_path_var).grid(row=3, column=0, columnspan=2, sticky="ew", padx=3, pady=4)
        ttk.Button(form, text="Browse", command=self._browse_audio_preload).grid(row=3, column=2, sticky="ew", padx=3, pady=4)
        form.columnconfigure(1, weight=1)

        buttons = ttk.Frame(panel)
        buttons.pack(fill="x", padx=8, pady=(2, 6))
        ttk.Button(buttons, text="Add / Update", command=self._add_or_update_audio_preload).pack(side="left", padx=2)
        ttk.Button(buttons, text="Remove", command=self._remove_audio_preload).pack(side="left", padx=2)
        ttk.Button(buttons, text="Validate File", command=self._validate_audio_preload).pack(side="left", padx=2)

    def _build_protocol_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.LabelFrame(parent, text="Protocol Schedule")
        panel.pack(fill="both", expand=True, pady=(8, 0))

        form = ttk.Frame(panel)
        form.pack(fill="x", padx=8, pady=8)
        rows = [
            ("repetitions_per_condition", "Repetitions"),
            ("soa_values_ms", "SOAs ms"),
            ("spatial_values_cm", "Spatial cm"),
            ("auditory_motion_directions", "Motions"),
            ("tactile_sites", "Tactile sites"),
            ("catch_trial_percentage", "Catch %"),
            ("catch_trials_exact", "Catch exact"),
            ("baseline_soa_values_ms", "Baseline SOAs"),
            ("respiratory_phases", "Phases"),
            ("blocks", "Blocks"),
            ("participants", "Participants"),
            ("random_seed", "Seed"),
        ]
        for idx, (key, label) in enumerate(rows):
            row = idx % 6
            col = 0 if idx < 6 else 2
            ttk.Label(form, text=label).grid(row=row, column=col, sticky="w", padx=4, pady=3)
            entry = ttk.Entry(form, textvariable=self.protocol_vars[key], width=28)
            entry.grid(row=row, column=col + 1, sticky="ew", padx=4, pady=3)
            self.protocol_vars[key].trace_add("write", lambda *_: self._update_protocol_summary())
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        ttk.Checkbutton(
            form,
            text="Pair SOA and spatial values",
            variable=self.pair_spatial_values_var,
            command=self._update_protocol_summary,
        ).grid(row=6, column=0, columnspan=2, sticky="w", padx=4, pady=(8, 2))
        ttk.Checkbutton(
            form,
            text="Include tactile-only baseline",
            variable=self.include_baseline_var,
            command=self._update_protocol_summary,
        ).grid(row=6, column=2, columnspan=2, sticky="w", padx=4, pady=(8, 2))

        strategy = ttk.Frame(panel)
        strategy.pack(fill="x", padx=8, pady=(0, 6))
        ttk.Label(strategy, text="Trial randomization").grid(row=0, column=0, sticky="w", padx=4, pady=3)
        ttk.Combobox(
            strategy,
            textvariable=self.protocol_vars["trial_randomization_strategy"],
            values=SUPPORTED_TRIAL_RANDOMIZATION,
            state="readonly",
            width=22,
        ).grid(row=0, column=1, sticky="ew", padx=4, pady=3)
        ttk.Label(strategy, text="Block order").grid(row=0, column=2, sticky="w", padx=4, pady=3)
        ttk.Combobox(
            strategy,
            textvariable=self.protocol_vars["block_order_randomization"],
            values=SUPPORTED_BLOCK_ORDER_RANDOMIZATION,
            state="readonly",
            width=24,
        ).grid(row=0, column=3, sticky="ew", padx=4, pady=3)
        ttk.Label(strategy, text="Max same type").grid(row=0, column=4, sticky="w", padx=4, pady=3)
        ttk.Spinbox(
            strategy,
            textvariable=self.protocol_vars["max_consecutive_same_trial_type"],
            from_=1,
            to=20,
            increment=1,
            width=5,
            command=self._update_protocol_summary,
        ).grid(row=0, column=5, sticky="w", padx=4, pady=3)
        strategy.columnconfigure(1, weight=1)
        strategy.columnconfigure(3, weight=1)
        self.protocol_vars["trial_randomization_strategy"].trace_add("write", lambda *_: self._update_protocol_summary())
        self.protocol_vars["block_order_randomization"].trace_add("write", lambda *_: self._update_protocol_summary())
        self.protocol_vars["max_consecutive_same_trial_type"].trace_add("write", lambda *_: self._update_protocol_summary())

        self._build_block_design_panel(panel)

        self.protocol_tree = ttk.Treeview(panel, columns=("metric", "value"), show="headings", height=5)
        self.protocol_tree.heading("metric", text="Metric")
        self.protocol_tree.heading("value", text="Count")
        self.protocol_tree.column("metric", width=150, anchor="w")
        self.protocol_tree.column("value", width=90, anchor="center")
        self.protocol_tree.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def _build_block_design_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.LabelFrame(parent, text="Block Design")
        panel.pack(fill="x", padx=8, pady=(0, 8))

        self.block_tree = ttk.Treeview(
            panel,
            columns=("label", "types"),
            show="headings",
            height=3,
        )
        self.block_tree.heading("label", text="Block")
        self.block_tree.heading("types", text="Stimulus types")
        self.block_tree.column("label", width=150, anchor="w")
        self.block_tree.column("types", width=420, anchor="w")
        self.block_tree.grid(row=0, column=0, columnspan=6, sticky="ew", padx=8, pady=6)
        self.block_tree.bind("<<TreeviewSelect>>", self._block_selected)

        ttk.Label(panel, text="Label").grid(row=1, column=0, sticky="w", padx=8, pady=3)
        ttk.Entry(panel, textvariable=self.block_label_var, width=18).grid(row=2, column=0, sticky="ew", padx=8, pady=3)
        ttk.Checkbutton(panel, text="Audio-tactile", variable=self.block_audio_tactile_var).grid(row=2, column=1, sticky="w", padx=4, pady=3)
        ttk.Checkbutton(panel, text="Baseline", variable=self.block_baseline_var).grid(row=2, column=2, sticky="w", padx=4, pady=3)
        ttk.Checkbutton(panel, text="Catch", variable=self.block_catch_var).grid(row=2, column=3, sticky="w", padx=4, pady=3)
        ttk.Button(panel, text="Add / Update", command=self._add_or_update_block).grid(row=2, column=4, sticky="ew", padx=4, pady=3)
        ttk.Button(panel, text="Remove", command=self._remove_block).grid(row=2, column=5, sticky="ew", padx=(4, 8), pady=3)
        ttk.Button(panel, text="Reset From Count", command=self._reset_blocks_from_count).grid(row=3, column=4, columnspan=2, sticky="e", padx=8, pady=(0, 6))
        panel.columnconfigure(0, weight=1)
        panel.columnconfigure(4, weight=0)

    def _build_trajectory_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.LabelFrame(parent, text="Looming Trajectory")
        panel.pack(fill="both", expand=True)

        controls = ttk.Frame(panel)
        controls.pack(fill="x", padx=8, pady=8)

        rows = [
            ("start_radius_m", "Start radius (m)", 0.01, 10.0, 0.05),
            ("end_radius_m", "End radius (m)", 0.01, 10.0, 0.05),
            ("path_length_m", "Path length (m)", 0.01, 20.0, 0.05),
            ("propagation_speed_mps", "Speed (m/s)", 0.01, 5.0, 0.01),
            ("azimuth_start_deg", "Start azimuth", -180, 180, 1),
            ("azimuth_end_deg", "End azimuth", -180, 180, 1),
            ("elevation_deg", "Elevation", -90, 90, 1),
            ("padding_pre_s", "Lead padding (s)", 0, 5, 0.1),
            ("padding_post_s", "Tail padding (s)", 0, 5, 0.1),
        ]
        for idx, (key, label, lo, hi, step) in enumerate(rows):
            row = idx // 2
            col = (idx % 2) * 2
            ttk.Label(controls, text=label).grid(row=row, column=col, sticky="w", padx=5, pady=4)
            spin = ttk.Spinbox(controls, textvariable=self.traj_vars[key], from_=lo, to=hi, increment=step, width=10, command=self._update_preview)
            spin.grid(row=row, column=col + 1, sticky="w", padx=5, pady=4)
            self.traj_vars[key].trace_add("write", lambda *_: self._update_preview())

        ttk.Label(controls, text="Direction").grid(row=5, column=0, sticky="w", padx=5, pady=4)
        ttk.Combobox(
            controls,
            textvariable=self.traj_vars["path_direction"],
            values=("approach", "recede", "left_to_right", "right_to_left", "custom"),
            state="readonly",
            width=16,
        ).grid(row=5, column=1, sticky="w", padx=5, pady=4)
        self.traj_vars["path_direction"].trace_add("write", lambda *_: self._update_preview())

        self.duration_label = ttk.Label(controls, text="")
        self.duration_label.grid(row=5, column=2, columnspan=2, sticky="w", padx=5, pady=4)

        self.canvas = tk.Canvas(panel, background=PALETTE["canvas"], highlightthickness=1, highlightbackground=PALETTE["border"])
        self.canvas.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.canvas.bind("<Configure>", lambda _event: self._update_preview())

    def _load_into_fields(self, design: StimulusDesign) -> None:
        self.name_var.set(design.name)
        self.sofa_var.set(design.sofa_file)
        self.noises = list(design.noises)
        self.custom_looming_files = list(design.custom_looming_files)
        self.prestimulus_files = list(design.prestimulus_files)
        traj = design.trajectory
        for key, var in self.traj_vars.items():
            var.set(str(getattr(traj, key)))
        protocol = design.protocol
        self.protocol_vars["repetitions_per_condition"].set(str(protocol.repetitions_per_condition))
        self.protocol_vars["soa_values_ms"].set(", ".join(str(value) for value in protocol.soa_values_ms))
        self.protocol_vars["spatial_values_cm"].set(", ".join(f"{value:g}" for value in protocol.spatial_values_cm))
        self.protocol_vars["auditory_motion_directions"].set(", ".join(protocol.auditory_motion_directions))
        self.protocol_vars["tactile_sites"].set(", ".join(protocol.tactile_sites))
        self.protocol_vars["catch_trial_percentage"].set(f"{protocol.catch_trial_percentage:g}")
        self.protocol_vars["catch_trials_exact"].set("" if protocol.catch_trials_exact is None else str(protocol.catch_trials_exact))
        self.protocol_vars["baseline_soa_values_ms"].set(", ".join(str(value) for value in protocol.baseline_soa_values_ms))
        self.protocol_vars["respiratory_phases"].set(", ".join(protocol.respiratory_phases))
        self.protocol_vars["blocks"].set(str(protocol.blocks))
        self.protocol_vars["trial_randomization_strategy"].set(protocol.trial_randomization_strategy)
        self.protocol_vars["block_order_randomization"].set(protocol.block_order_randomization)
        self.protocol_vars["max_consecutive_same_trial_type"].set(str(protocol.max_consecutive_same_trial_type))
        self.protocol_vars["participants"].set(str(protocol.participants))
        self.protocol_vars["random_seed"].set(str(protocol.random_seed))
        self.pair_spatial_values_var.set(protocol.pair_spatial_values_with_soas)
        self.include_baseline_var.set(protocol.include_baseline_trials)
        self.block_specs = effective_block_specs(protocol)
        self._refresh_noise_tree()
        self._refresh_audio_preload_tree()
        self._refresh_block_tree()
        self._update_protocol_summary()

    def _refresh_noise_tree(self) -> None:
        for item in self.noise_tree.get_children():
            self.noise_tree.delete(item)
        for idx, noise in enumerate(self.noises):
            self.noise_tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    noise.label,
                    noise.noise_type,
                    f"{noise.azimuth_deg:.1f}",
                    f"{noise.elevation_deg:.1f}",
                    f"{noise.gain:.2f}",
                ),
            )
        if self.noises and not self.noise_tree.selection():
            self.noise_tree.selection_set("0")
            self._noise_selected()

    def _refresh_audio_preload_tree(self) -> None:
        for item in self.audio_preload_tree.get_children():
            self.audio_preload_tree.delete(item)
        for kind, assets in [
            ("looming", self.custom_looming_files),
            ("prestimulus", self.prestimulus_files),
        ]:
            for idx, asset in enumerate(assets):
                self.audio_preload_tree.insert(
                    "",
                    "end",
                    iid=f"{kind}:{idx}",
                    values=(
                        "Looming" if kind == "looming" else "Prestimulus",
                        asset.label,
                        f"{asset.target_duration_s:g}",
                        asset.path,
                    ),
                )

    def _refresh_block_tree(self) -> None:
        for item in self.block_tree.get_children():
            self.block_tree.delete(item)
        for idx, block in enumerate(self.block_specs):
            self.block_tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(block.label, ", ".join(block.stimulus_types)),
            )
        self.protocol_vars["blocks"].set(str(len(self.block_specs)))
        if self.block_specs and not self.block_tree.selection():
            self.block_tree.selection_set("0")
            self._block_selected()

    def _parse_float(self, value: str, label: str) -> float:
        try:
            return float(value)
        except ValueError as exc:
            raise ValueError(f"{label} must be a number.") from exc

    def _parse_int(self, value: str, label: str) -> int:
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"{label} must be an integer.") from exc

    def _parse_int_list(self, value: str, label: str) -> list[int]:
        try:
            return [int(part.strip()) for part in value.split(",") if part.strip()]
        except ValueError as exc:
            raise ValueError(f"{label} must be a comma-separated list of integers.") from exc

    def _parse_float_list(self, value: str, label: str) -> list[float]:
        try:
            return [float(part.strip()) for part in value.split(",") if part.strip()]
        except ValueError as exc:
            raise ValueError(f"{label} must be a comma-separated list of numbers.") from exc

    def _parse_string_list(self, value: str) -> list[str]:
        return [part.strip() for part in value.split(",") if part.strip()]

    def _parse_optional_int(self, value: str, label: str) -> int | None:
        value = value.strip()
        if not value:
            return None
        return self._parse_int(value, label)

    def _build_design_from_fields(self) -> StimulusDesign:
        trajectory = TrajectorySpec(
            start_radius_m=self._parse_float(self.traj_vars["start_radius_m"].get(), "Start radius"),
            end_radius_m=self._parse_float(self.traj_vars["end_radius_m"].get(), "End radius"),
            path_direction=self.traj_vars["path_direction"].get(),
            path_length_m=self._parse_float(self.traj_vars["path_length_m"].get(), "Path length"),
            propagation_speed_mps=self._parse_float(self.traj_vars["propagation_speed_mps"].get(), "Speed"),
            azimuth_start_deg=self._parse_float(self.traj_vars["azimuth_start_deg"].get(), "Start azimuth"),
            azimuth_end_deg=self._parse_float(self.traj_vars["azimuth_end_deg"].get(), "End azimuth"),
            elevation_deg=self._parse_float(self.traj_vars["elevation_deg"].get(), "Elevation"),
            padding_pre_s=self._parse_float(self.traj_vars["padding_pre_s"].get(), "Lead padding"),
            padding_post_s=self._parse_float(self.traj_vars["padding_post_s"].get(), "Tail padding"),
        )
        protocol = ProtocolSpec(
            repetitions_per_condition=self._parse_int(self.protocol_vars["repetitions_per_condition"].get(), "Repetitions"),
            soa_values_ms=self._parse_int_list(self.protocol_vars["soa_values_ms"].get(), "SOAs"),
            spatial_values_cm=self._parse_float_list(self.protocol_vars["spatial_values_cm"].get(), "Spatial values"),
            pair_spatial_values_with_soas=self.pair_spatial_values_var.get(),
            auditory_motion_directions=self._parse_string_list(self.protocol_vars["auditory_motion_directions"].get()),
            tactile_sites=self._parse_string_list(self.protocol_vars["tactile_sites"].get()),
            catch_trial_percentage=self._parse_float(self.protocol_vars["catch_trial_percentage"].get(), "Catch percentage"),
            catch_trials_exact=self._parse_optional_int(self.protocol_vars["catch_trials_exact"].get(), "Exact catch count"),
            include_baseline_trials=self.include_baseline_var.get(),
            baseline_soa_values_ms=self._parse_int_list(self.protocol_vars["baseline_soa_values_ms"].get(), "Baseline SOAs"),
            respiratory_phases=self._parse_string_list(self.protocol_vars["respiratory_phases"].get()),
            blocks=len(self.block_specs) or self._parse_int(self.protocol_vars["blocks"].get(), "Blocks"),
            block_specs=list(self.block_specs),
            trial_randomization_strategy=self.protocol_vars["trial_randomization_strategy"].get(),
            block_order_randomization=self.protocol_vars["block_order_randomization"].get(),
            max_consecutive_same_trial_type=self._parse_int(self.protocol_vars["max_consecutive_same_trial_type"].get(), "Max same type"),
            participants=self._parse_int(self.protocol_vars["participants"].get(), "Participants"),
            random_seed=self._parse_int(self.protocol_vars["random_seed"].get(), "Seed"),
        )
        return StimulusDesign(
            name=self.name_var.get().strip() or "Untitled PPS stimulus design",
            sofa_file=self.sofa_var.get().strip(),
            noises=list(self.noises),
            custom_looming_files=list(self.custom_looming_files),
            prestimulus_files=list(self.prestimulus_files),
            trajectory=trajectory,
            protocol=protocol,
        )

    def _noise_selected(self, _event=None) -> None:
        selected = self.noise_tree.selection()
        if not selected:
            return
        noise = self.noises[int(selected[0])]
        self.noise_label_var.set(noise.label)
        self.noise_type_var.set(noise.noise_type)
        self.noise_azimuth_var.set(str(noise.azimuth_deg))
        self.noise_elevation_var.set(str(noise.elevation_deg))
        self.noise_gain_var.set(str(noise.gain))

    def _add_or_update_noise(self) -> None:
        try:
            noise = NoiseDefinition(
                label=self.noise_label_var.get().strip() or self.noise_type_var.get().title(),
                noise_type=self.noise_type_var.get().strip().lower(),
                azimuth_deg=self._parse_float(self.noise_azimuth_var.get(), "Noise azimuth"),
                elevation_deg=self._parse_float(self.noise_elevation_var.get(), "Noise elevation"),
                gain=self._parse_float(self.noise_gain_var.get(), "Noise gain"),
            )
        except ValueError as exc:
            messagebox.showerror("Invalid noise", str(exc))
            return

        selected = self.noise_tree.selection()
        if selected:
            self.noises[int(selected[0])] = noise
        else:
            self.noises.append(noise)
        self._refresh_noise_tree()
        self._update_protocol_summary()
        self.status_var.set("Noise definition updated.")

    def _remove_noise(self) -> None:
        selected = self.noise_tree.selection()
        if not selected:
            return
        del self.noises[int(selected[0])]
        self._refresh_noise_tree()
        self._update_protocol_summary()
        self.status_var.set("Noise definition removed.")

    def _audio_preload_kind(self) -> str:
        return "looming" if self.audio_preload_type_var.get().lower().startswith("loom") else "prestimulus"

    def _audio_preload_list(self, kind: str) -> list[AudioFileSpec]:
        return self.custom_looming_files if kind == "looming" else self.prestimulus_files

    def _selected_audio_preload(self) -> tuple[str, int] | None:
        selected = self.audio_preload_tree.selection()
        if not selected:
            return None
        kind, idx_text = selected[0].split(":", 1)
        return kind, int(idx_text)

    def _audio_preload_selected(self, _event=None) -> None:
        selected = self._selected_audio_preload()
        if selected is None:
            return
        kind, idx = selected
        asset = self._audio_preload_list(kind)[idx]
        self.audio_preload_type_var.set("Looming" if kind == "looming" else "Prestimulus")
        self.audio_preload_label_var.set(asset.label)
        self.audio_preload_path_var.set(asset.path)
        self.audio_preload_duration_var.set(str(asset.target_duration_s))

    def _browse_audio_preload(self) -> None:
        path = filedialog.askopenfilename(
            title="Select custom audio preload",
            filetypes=[
                ("Audio files", "*.wav *.flac *.aiff *.aif *.mp3"),
                ("WAV files", "*.wav"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.audio_preload_path_var.set(path)
            if not self.audio_preload_label_var.get().strip():
                self.audio_preload_label_var.set(Path(path).stem)

    def _add_or_update_audio_preload(self) -> None:
        try:
            asset = AudioFileSpec(
                label=self.audio_preload_label_var.get().strip() or Path(self.audio_preload_path_var.get()).stem,
                path=self.audio_preload_path_var.get().strip(),
                target_duration_s=self._parse_float(self.audio_preload_duration_var.get(), "Target duration"),
            )
        except ValueError as exc:
            messagebox.showerror("Invalid audio preload", str(exc))
            return
        if not asset.path:
            messagebox.showerror("Invalid audio preload", "Choose an audio file path.")
            return
        if asset.target_duration_s <= 0:
            messagebox.showerror("Invalid audio preload", "Target duration must be positive.")
            return

        target_kind = self._audio_preload_kind()
        selected = self._selected_audio_preload()
        new_iid: str
        if selected is None:
            target_list = self._audio_preload_list(target_kind)
            target_list.append(asset)
            new_iid = f"{target_kind}:{len(target_list) - 1}"
        else:
            old_kind, idx = selected
            if old_kind == target_kind:
                target_list = self._audio_preload_list(target_kind)
                target_list[idx] = asset
                new_iid = f"{target_kind}:{idx}"
            else:
                del self._audio_preload_list(old_kind)[idx]
                target_list = self._audio_preload_list(target_kind)
                target_list.append(asset)
                new_iid = f"{target_kind}:{len(target_list) - 1}"

        self._refresh_audio_preload_tree()
        self.audio_preload_tree.selection_set(new_iid)
        self.status_var.set("Custom audio preload updated.")

    def _remove_audio_preload(self) -> None:
        selected = self._selected_audio_preload()
        if selected is None:
            return
        kind, idx = selected
        del self._audio_preload_list(kind)[idx]
        self._refresh_audio_preload_tree()
        self.status_var.set("Custom audio preload removed.")

    def _validate_audio_preload(self) -> None:
        path = Path(self.audio_preload_path_var.get())
        if not path.exists():
            messagebox.showerror("Audio preload", f"File not found:\n{path}")
            return
        try:
            target = self._parse_float(self.audio_preload_duration_var.get(), "Target duration")
            summary = audio_file_summary(path)
        except Exception as exc:
            messagebox.showerror("Audio preload", str(exc))
            return
        duration = summary["duration_s"]
        msg = (
            f"Duration: {duration:.4f}s\n"
            f"Target: {target:.4f}s\n"
            f"Sample rate: {summary['sample_rate']} Hz\n"
            f"Channels: {summary['channels']}\n"
            f"Frames: {summary['frames']}"
        )
        if abs(duration - target) > 0.001:
            messagebox.showwarning("Audio preload", msg)
            self.status_var.set(f"Audio file differs from target by {duration - target:+.4f}s.")
        else:
            messagebox.showinfo("Audio preload", msg)
            self.status_var.set("Audio preload duration matches target.")

    def _block_selected(self, _event=None) -> None:
        selected = self.block_tree.selection()
        if not selected:
            return
        block = self.block_specs[int(selected[0])]
        self.block_label_var.set(block.label)
        self.block_audio_tactile_var.set("Audio-Tactile" in block.stimulus_types)
        self.block_baseline_var.set("Baseline" in block.stimulus_types)
        self.block_catch_var.set("Catch" in block.stimulus_types)

    def _block_from_fields(self) -> BlockSpec:
        stimulus_types: list[str] = []
        if self.block_audio_tactile_var.get():
            stimulus_types.append("Audio-Tactile")
        if self.block_baseline_var.get():
            stimulus_types.append("Baseline")
        if self.block_catch_var.get():
            stimulus_types.append("Catch")
        label = self.block_label_var.get().strip() or f"Block {len(self.block_specs) + 1}"
        return BlockSpec(label=label, stimulus_types=stimulus_types)

    def _add_or_update_block(self) -> None:
        block = self._block_from_fields()
        if not block.stimulus_types:
            messagebox.showerror("Invalid block", "Select at least one stimulus type for this block.")
            return
        selected = self.block_tree.selection()
        if selected:
            self.block_specs[int(selected[0])] = block
            new_iid = selected[0]
        else:
            self.block_specs.append(block)
            new_iid = str(len(self.block_specs) - 1)
        self._refresh_block_tree()
        self.block_tree.selection_set(new_iid)
        self._update_protocol_summary()
        self.status_var.set("Block definition updated.")

    def _remove_block(self) -> None:
        selected = self.block_tree.selection()
        if not selected:
            return
        if len(self.block_specs) <= 1:
            messagebox.showerror("Invalid block", "At least one block is required.")
            return
        del self.block_specs[int(selected[0])]
        self._refresh_block_tree()
        self._update_protocol_summary()
        self.status_var.set("Block definition removed.")

    def _reset_blocks_from_count(self) -> None:
        try:
            count = self._parse_int(self.protocol_vars["blocks"].get(), "Blocks")
        except ValueError as exc:
            messagebox.showerror("Invalid blocks", str(exc))
            return
        if count < 1:
            messagebox.showerror("Invalid blocks", "Block count must be at least 1.")
            return
        self.block_specs = [
            BlockSpec(f"Block {idx + 1}", ["Audio-Tactile", "Baseline", "Catch"])
            for idx in range(count)
        ]
        self._refresh_block_tree()
        self._update_protocol_summary()
        self.status_var.set(f"Reset block design to {count} block(s).")

    def _browse_sofa(self) -> None:
        path = filedialog.askopenfilename(
            title="Select SOFA HRIR file",
            filetypes=[("SOFA files", "*.sofa"), ("All files", "*.*")],
        )
        if path:
            self.sofa_var.set(path)

    def _load_template_clicked(self) -> None:
        selected = self.template_combo.current()
        if selected < 0 or selected >= len(self.templates):
            return
        template = self.templates[selected]
        self.design = template.design
        self._load_into_fields(self.design)
        self._update_preview()
        self.status_var.set(f"Loaded template: {template.title} ({template.verification_status})")
        if template.verification_status != "verified":
            messagebox.showwarning(
                "Template needs verification",
                "This template contains partial literature metadata. Confirm the source paper before exact replication.",
            )

    def _validate_sofa(self) -> None:
        path = Path(self.sofa_var.get())
        if not path.exists():
            messagebox.showerror("SOFA file", f"File not found:\n{path}")
            return
        try:
            summary = sofa_summary(path)
        except Exception as exc:
            messagebox.showerror("SOFA file", str(exc))
            return
        msg = (
            f"{summary['positions']} positions\n"
            f"Azimuth: {summary['azimuth_min']:.1f} to {summary['azimuth_max']:.1f} deg\n"
            f"Elevation: {summary['elevation_min']:.1f} to {summary['elevation_max']:.1f} deg\n"
            f"Sample rate: {summary['sample_rate'] or 'unknown'}"
        )
        messagebox.showinfo("SOFA file summary", msg)
        self.status_var.set("SOFA file validated.")

    def _snap_noises(self) -> None:
        try:
            design = snap_noises_to_sofa(self._build_design_from_fields())
        except Exception as exc:
            messagebox.showerror("Snap to SOFA", str(exc))
            return
        self.design = design
        self._load_into_fields(design)
        self.status_var.set("Noise azimuth/elevation values snapped to nearest SOFA positions.")

    def _check_design(self) -> None:
        try:
            design = self._build_design_from_fields()
        except ValueError as exc:
            messagebox.showerror("Invalid design", str(exc))
            return
        warnings = validate_design(design)
        if warnings:
            messagebox.showwarning("Design check", "\n".join(warnings))
            self.status_var.set(f"Design check found {len(warnings)} warning(s).")
        else:
            messagebox.showinfo("Design check", "Design check passed.")
            self.status_var.set("Design check passed.")

    def _update_protocol_summary(self) -> None:
        if not hasattr(self, "protocol_tree"):
            return
        for item in self.protocol_tree.get_children():
            self.protocol_tree.delete(item)
        try:
            design = self._build_design_from_fields()
            summary = protocol_summary(design)
        except Exception:
            return
        labels = [
            ("Audio-tactile trials", "audio_tactile_trials"),
            ("Baseline trials", "baseline_trials"),
            ("Catch trials", "catch_trials"),
            ("Total trials", "total_trials"),
            ("Blocks", "blocks"),
            ("Max trials/block", "max_trials_per_block"),
            ("Min trials/block", "min_trials_per_block"),
            ("Participants", "participants"),
            ("Participant-trials", "total_participant_trials"),
        ]
        for label, key in labels:
            self.protocol_tree.insert("", "end", values=(label, summary[key]))

    def _save_clicked(self) -> None:
        try:
            design = self._build_design_from_fields()
        except ValueError as exc:
            messagebox.showerror("Invalid design", str(exc))
            return
        path = filedialog.asksaveasfilename(
            title="Save stimulus design",
            defaultextension=".json",
            initialdir=str(self.design_path.parent),
            initialfile=self.design_path.name,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        self.design_path = Path(path)
        self.design = design
        save_design(design, self.design_path)
        self.status_var.set(f"Saved {self.design_path}")

    def _save_settings_clicked(self) -> None:
        try:
            design = self._build_design_from_fields()
        except ValueError as exc:
            messagebox.showerror("Invalid design", str(exc))
            return
        self.design = design
        save_design(design, self.design_path)
        self.status_var.set(f"Saved settings to {self.design_path}")

    def _load_clicked(self) -> None:
        path = filedialog.askopenfilename(
            title="Load stimulus design",
            initialdir=str(self.design_path.parent),
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        self.design_path = Path(path)
        self.design = load_design(self.design_path)
        self._load_into_fields(self.design)
        self._update_preview()
        self.status_var.set(f"Loaded {self.design_path}")

    def _load_settings_clicked(self) -> None:
        if not self.design_path.exists():
            messagebox.showinfo("Load settings", f"No saved settings found yet:\n{self.design_path}")
            return
        self.design = load_design(self.design_path)
        self._load_into_fields(self.design)
        self._update_preview()
        self.status_var.set(f"Loaded settings from {self.design_path}")

    def _export_trajectory_clicked(self) -> None:
        try:
            design = self._build_design_from_fields()
        except ValueError as exc:
            messagebox.showerror("Invalid design", str(exc))
            return
        path = filedialog.asksaveasfilename(
            title="Export trajectory CSV",
            defaultextension=".csv",
            initialdir=str(REPO_ROOT / "artifacts"),
            initialfile="stimulus_trajectory.csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        export_trajectory_csv(design, Path(path))
        self.status_var.set(f"Exported {path}")

    def _export_protocol_clicked(self) -> None:
        try:
            design = self._build_design_from_fields()
        except ValueError as exc:
            messagebox.showerror("Invalid design", str(exc))
            return
        path = filedialog.asksaveasfilename(
            title="Export protocol CSV",
            defaultextension=".csv",
            initialdir=str(REPO_ROOT / "artifacts"),
            initialfile="stimulus_protocol.csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        export_protocol_csv(design, Path(path))
        self.status_var.set(f"Exported {path}")

    def _update_preview(self) -> None:
        if not hasattr(self, "canvas"):
            return
        try:
            design = self._build_design_from_fields()
        except Exception:
            return

        points = trajectory_points(design.trajectory, samples=100)
        movement = design.trajectory.movement_duration_s
        total = design.trajectory.total_duration_s
        self.duration_label.config(text=f"Movement: {movement:.3f}s   Total: {total:.3f}s")

        canvas = self.canvas
        canvas.delete("all")
        w = max(canvas.winfo_width(), 320)
        h = max(canvas.winfo_height(), 240)
        cx, cy = w / 2, h * 0.58
        max_abs = max(
            0.25,
            max(abs(p["x_m"]) for p in points),
            max(abs(p["y_m"]) for p in points),
            design.trajectory.start_radius_m,
            design.trajectory.end_radius_m,
        )
        scale = min(w, h) * 0.38 / max_abs

        for radius in (0.25, 0.5, 1.0, 1.5, 2.0):
            if radius <= max_abs * 1.1:
                r = radius * scale
                canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline=PALETTE["canvas_grid"])

        canvas.create_line(cx, 16, cx, h - 16, fill=PALETTE["canvas_grid"])
        canvas.create_line(16, cy, w - 16, cy, fill=PALETTE["canvas_grid"])
        canvas.create_oval(cx - 7, cy - 7, cx + 7, cy + 7, fill="#f3dcc3", outline="")
        canvas.create_text(cx, cy + 20, fill=PALETTE["canvas_text"], text="Listener")

        xy = []
        for p in points:
            xy.extend([cx + p["x_m"] * scale, cy - p["y_m"] * scale])
        if len(xy) >= 4:
            canvas.create_line(*xy, fill="#4fb3a6", width=3, smooth=True)
        start = points[0]
        end = points[-1]
        canvas.create_oval(cx + start["x_m"] * scale - 6, cy - start["y_m"] * scale - 6, cx + start["x_m"] * scale + 6, cy - start["y_m"] * scale + 6, fill="#a8d672", outline="")
        canvas.create_oval(cx + end["x_m"] * scale - 6, cy - end["y_m"] * scale - 6, cx + end["x_m"] * scale + 6, cy - end["y_m"] * scale + 6, fill="#df7c52", outline="")
        canvas.create_text(18, 18, anchor="nw", fill=PALETTE["canvas_text"], text="Top-down trajectory preview")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch the PPS stimulus designer.")
    parser.add_argument("--design", type=Path, default=DEFAULT_DESIGN_PATH, help="Design JSON to open or create.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    root = tk.Tk()
    StimulusDesignerApp(root, design_path=args.design)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
