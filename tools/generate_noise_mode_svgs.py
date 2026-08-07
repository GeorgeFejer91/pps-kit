"""Generate PPS-kit signal graphics directly from deterministic sample arrays.

This pipeline has no screenshot, canvas, tracing, or raster stage. It uses the
same Gaussian-noise, DynaSpace burst, and tactile-signal primitives as the audio
renderer, reduces those samples into min/max bins, and builds every graphic
from native SVG elements.
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
ASSET_DIR = SRC_DIR / "peripersonal_space_toolkit" / "assets"
DASHBOARD_DIR = SRC_DIR / "peripersonal_space_toolkit" / "dashboard"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from peripersonal_space_toolkit import render_backend  # noqa: E402
from peripersonal_space_toolkit.design import (  # noqa: E402
    PPS_LOOMING_GOLD_STANDARD_SOURCE_PARAMETERS,
    PPS_LOOMING_GOLD_STANDARD_SOURCE_PROFILE,
    gold_standard_looming_source_parameters,
)


SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)

PIPELINE_SCHEMA = "pps-native-signal-svg.v1"
GENERATOR_PATH = "tools/generate_noise_mode_svgs.py"
SAMPLE_RATE = 44_100
SEED = 20_250_604

SHOWCASE_DURATION_S = 3.85
SHOWCASE_ACTIVE_START_S = 0.30
SHOWCASE_ACTIVE_WINDOW_S = 3.07
SHOWCASE_ACTIVE_END_S = round(SHOWCASE_ACTIVE_START_S + SHOWCASE_ACTIVE_WINDOW_S, 2)
SHOWCASE_START_RADIUS_M = 1.40
SHOWCASE_END_RADIUS_M = 0.20

SHOWCASE_WIDTH = 960
SHOWCASE_HEIGHT = 360
PANEL_X = 96
PANEL_Y = 98
PANEL_W = 792
PANEL_H = 166

SOURCE_WIDGET_WIDTH = 320
SOURCE_WIDGET_HEIGHT = 96
SOURCE_WIDGET_PANEL_X = 4
SOURCE_WIDGET_PANEL_Y = 4
SOURCE_WIDGET_PANEL_W = 312
SOURCE_WIDGET_PANEL_H = 68

BASELINE_WIDTH = 320
BASELINE_HEIGHT = 96
BASELINE_DURATION_S = 1.50

COLORS = {
    "background": "#f4f5f1",
    "surface": "#ffffff",
    "surface_2": "#f8faf7",
    "text": "#202621",
    "muted": "#68746c",
    "line": "#d9dfd6",
    "line_strong": "#b8c5bb",
    "panel": "#141f1a",
    "panel_soft": "#1b2821",
    "panel_line": "#2e4038",
    "widget_plot": "#eef3ef",
    "widget_lane": "#f8faf7",
    "widget_grid": "#c9d5cd",
    "primary": "#246b55",
    "primary_hover": "#1d5846",
    "cyan": "#2a8f84",
    "accent": "#d8892f",
    "orange": "#b75b2f",
    "baseline": "#4b5fa8",
    "white_noise": "#d8dde2",
    "chip_surface": "#eef7f3",
    "chip_line": "#b8d9cf",
    "plot_border": "#9aaba0",
    "plot_label": "#5f7469",
    "plot_label_strong": "#355447",
    "silenced": "#6d8176",
    "soft_mark": "#8da399",
    "stimulus_span": "#496d5d",
    "tactile_text": "#8a4020",
    "footer": "#526c60",
}

DARK_COLORS = {
    "background": "#151a17",
    "surface": "#202723",
    "surface_2": "#252e29",
    "text": "#f1f5f2",
    "muted": "#bdc9c1",
    "line": "#3d4b43",
    "line_strong": "#607066",
    "panel": "#111915",
    "panel_soft": "#1b2821",
    "panel_line": "#33483e",
    "widget_plot": "#171e1a",
    "widget_lane": "#202a24",
    "widget_grid": "#3b4b42",
    "primary": "#54b58f",
    "primary_hover": "#6bc7a2",
    "cyan": "#69cfc3",
    "accent": "#f2b35c",
    "orange": "#e58c59",
    "baseline": "#899af0",
    "white_noise": "#d8dde2",
    "chip_surface": "#1f3b31",
    "chip_line": "#3f725e",
    "plot_border": "#52645a",
    "plot_label": "#91a99d",
    "plot_label_strong": "#c0d2c8",
    "silenced": "#8ca095",
    "soft_mark": "#8ca095",
    "stimulus_span": "#8ab9a3",
    "tactile_text": "#f0a071",
    "footer": "#91a99d",
}

LIGHT_COLORS = COLORS
COLORS = {
    key: f"var(--pps-svg-{key.replace('_', '-')}, {value})"
    for key, value in LIGHT_COLORS.items()
}

FONT_SANS = "Aptos, Noto Sans, Helvetica Neue, sans-serif"
FONT_MONO = "Cascadia Mono, SFMono-Regular, Consolas, monospace"


@dataclass(frozen=True)
class ShowcaseSpec:
    filename: str
    title: str
    subtitle: str
    label: str
    mode: str
    description: str


@dataclass(frozen=True)
class BaselineSpec:
    filename: str
    title: str
    audio_mode: str
    tactile_positions: tuple[float, ...]
    footer: str
    marker_labels: tuple[str, ...] = ()


SHOWCASE_SPECS = (
    ShowcaseSpec(
        filename="looming_burst_train_waveform.svg",
        title="Looming Bursts",
        subtitle="Gaussian white-noise bursts rendered through the approach gain.",
        label="DynaSpace-derived burst source",
        mode="burst",
        description=(
            "A native-vector min-max waveform generated from the PPS-kit DynaSpace "
            "Gaussian burst source and reciprocal-distance approach gain."
        ),
    ),
    ShowcaseSpec(
        filename="looming_smooth_linear_approach_waveform.svg",
        title="Smooth Linear Approach",
        subtitle="Continuous Gaussian noise on a linear path with reciprocal-distance gain.",
        label="Continuous source; linear path; 1/r gain",
        mode="continuous",
        description=(
            "A native-vector min-max waveform generated from continuous PPS-kit "
            "Gaussian noise and the reciprocal-distance gain of a linear approach."
        ),
    ),
)

SHOWCASE_WIDGET_FILENAMES = {
    "burst": "looming_burst_train_widget.svg",
    "continuous": "looming_smooth_linear_approach_widget.svg",
}

BASELINE_SPECS = (
    BaselineSpec(
        "baseline_none.svg",
        "No baseline",
        "looming",
        (0.58,),
        "TRIALS ONLY",
    ),
    BaselineSpec(
        "baseline_min_anchor.svg",
        "Minimum SOA anchor",
        "looming",
        (0.22,),
        "FIRST ENTERED SOA",
        ("FIRST",),
    ),
    BaselineSpec(
        "baseline_max_anchor.svg",
        "Maximum SOA anchor",
        "looming",
        (0.80,),
        "LAST ENTERED SOA",
        ("LAST",),
    ),
    BaselineSpec(
        "baseline_min_max.svg",
        "Minimum and maximum SOA anchors",
        "looming",
        (0.22, 0.80),
        "FIRST + LAST SOA",
        ("FIRST", "LAST"),
    ),
    BaselineSpec(
        "baseline_tactile_only.svg",
        "Full SOA tactile-only",
        "silent",
        (0.22, 0.50, 0.80),
        "LOOMING AUDIO SILENCED",
    ),
    BaselineSpec(
        "baseline_stationary_burst.svg",
        "Full SOA stationary bursts",
        "stationary",
        (0.22, 0.50, 0.80),
        "STATIONARY BURST SOURCE",
    ),
    BaselineSpec(
        "baseline_custom.svg",
        "Custom baseline timings",
        "optional",
        (0.30, 0.57, 0.76),
        "CUSTOM SOAS; AUDIO OPTIONAL",
    ),
)

GENERATED_FILENAMES = tuple(
    [spec.filename for spec in SHOWCASE_SPECS]
    + [SHOWCASE_WIDGET_FILENAMES[spec.mode] for spec in SHOWCASE_SPECS]
    + ["audiogram_looming_trial.svg"]
    + [spec.filename for spec in BASELINE_SPECS]
)

INTERFACE_FILENAMES = tuple(
    [SHOWCASE_WIDGET_FILENAMES[spec.mode] for spec in SHOWCASE_SPECS]
    + ["audiogram_looming_trial.svg"]
    + [spec.filename for spec in BASELINE_SPECS]
)


def _tag(name: str) -> str:
    return f"{{{SVG_NS}}}{name}"


def _number(value: float | int) -> str:
    if isinstance(value, int):
        return str(value)
    text = f"{float(value):.3f}".rstrip("0").rstrip(".")
    return text if text else "0"


def _attributes(values: dict[str, Any] | None = None, **extra: Any) -> dict[str, str]:
    merged = dict(values or {})
    merged.update(extra)
    return {str(key).replace("_", "-"): _number(value) if isinstance(value, (float, int)) else str(value) for key, value in merged.items()}


def _element(
    parent: ET.Element,
    name: str,
    attributes: dict[str, Any] | None = None,
    *,
    text: str | None = None,
) -> ET.Element:
    node = ET.SubElement(parent, _tag(name), _attributes(attributes))
    if text is not None:
        node.text = text
    return node


def _text(
    parent: ET.Element,
    value: str,
    x: float,
    y: float,
    *,
    fill: str = COLORS["text"],
    size: float = 12,
    family: str = FONT_SANS,
    weight: int | None = None,
    anchor: str | None = None,
    opacity: float | None = None,
    data_layer: str | None = None,
) -> ET.Element:
    attributes: dict[str, Any] = {
        "x": x,
        "y": y,
        "fill": fill,
        "font-size": size,
        "font-family": family,
        "letter-spacing": "0",
    }
    if weight is not None:
        attributes["font-weight"] = weight
    if anchor is not None:
        attributes["text-anchor"] = anchor
    if opacity is not None:
        attributes["opacity"] = opacity
    if data_layer is not None:
        attributes["data-layer"] = data_layer
    return _element(parent, "text", attributes, text=value)


def _theme_stylesheet() -> str:
    light = "".join(
        f"--pps-svg-{key.replace('_', '-')}:{value};"
        for key, value in LIGHT_COLORS.items()
    )
    dark = "".join(
        f"--pps-svg-{key.replace('_', '-')}:{value};"
        for key, value in DARK_COLORS.items()
    )
    return (
        f":root{{{light}}}"
        "@media (prefers-color-scheme:dark){"
        f":root{{{dark}}}"
        "}"
    )


def _document(
    *,
    width: int,
    height: int,
    title: str,
    description: str,
    document_id: str,
    metadata: dict[str, Any],
) -> tuple[ET.Element, ET.Element]:
    root = ET.Element(
        _tag("svg"),
        _attributes(
            {
                "viewBox": f"0 0 {width} {height}",
                "width": width,
                "height": height,
                "role": "img",
                "aria-labelledby": f"{document_id}-title {document_id}-desc",
                "data-pipeline": PIPELINE_SCHEMA,
            }
        ),
    )
    _element(root, "title", {"id": f"{document_id}-title"}, text=title)
    _element(root, "desc", {"id": f"{document_id}-desc"}, text=description)
    _element(
        root,
        "style",
        {"data-layer": "theme-palette"},
        text=_theme_stylesheet(),
    )
    metadata_node = _element(root, "metadata", {"id": f"{document_id}-metadata"})
    metadata_node.text = json.dumps(
        {
            "schema": PIPELINE_SCHEMA,
            "generator": GENERATOR_PATH,
            "theme_behavior": "light/dark palette follows the embedding element color-scheme",
            **metadata,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return root, _element(root, "defs")


def _serialize(root: ET.Element) -> str:
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", short_empty_elements=True) + "\n"


def _linear_gradient(
    defs: ET.Element,
    gradient_id: str,
    start: str,
    end: str,
    *,
    start_opacity: float = 1.0,
    end_opacity: float = 1.0,
) -> None:
    gradient = _element(
        defs,
        "linearGradient",
        {
            "id": gradient_id,
            "x1": "0%",
            "y1": "0%",
            "x2": "100%",
            "y2": "0%",
        },
    )
    _element(
        gradient,
        "stop",
        {"offset": "0%", "stop-color": start, "stop-opacity": start_opacity},
    )
    _element(
        gradient,
        "stop",
        {"offset": "100%", "stop-color": end, "stop-opacity": end_opacity},
    )


def _clip_rect(
    defs: ET.Element,
    clip_id: str,
    x: float,
    y: float,
    width: float,
    height: float,
) -> None:
    clip = _element(defs, "clipPath", {"id": clip_id})
    _element(clip, "rect", {"x": x, "y": y, "width": width, "height": height})


def _normalize(signal: np.ndarray) -> np.ndarray:
    values = np.asarray(signal, dtype=float)
    peak = float(np.max(np.abs(values))) if values.size else 0.0
    return values / peak if peak > 0 else values.copy()


def _approach_gain(
    sample_count: int,
    *,
    sample_rate: int,
    start_s: float,
    end_s: float,
    hold_after: bool,
) -> np.ndarray:
    """Return the renderer's normalized 1/r gain for a linear-distance path."""

    times = np.arange(sample_count, dtype=float) / sample_rate
    progress = np.clip((times - start_s) / max(end_s - start_s, 1.0 / sample_rate), 0.0, 1.0)
    radius = SHOWCASE_START_RADIUS_M + (SHOWCASE_END_RADIUS_M - SHOWCASE_START_RADIUS_M) * progress
    gain = (1.0 / radius) / (1.0 / SHOWCASE_END_RADIUS_M)
    if not hold_after:
        gain[times > end_s] = 0.0
    return gain


def _showcase_signals() -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    samples = int(round(SHOWCASE_DURATION_S * SAMPLE_RATE))
    parameters = gold_standard_looming_source_parameters(
        {
            "active_window_s": SHOWCASE_ACTIVE_WINDOW_S,
            "onset_s": SHOWCASE_ACTIVE_START_S,
        }
    )
    burst_onsets, resolved = render_backend._dynaspace_burst_onsets(
        samples=samples,
        sample_rate=SAMPLE_RATE,
        parameters=parameters,
    )
    burst_source = render_backend._generate_dynaspace_burst_train(
        "white",
        samples,
        SAMPLE_RATE,
        SEED,
        parameters,
    )
    continuous_source = render_backend._generate_noise("white", samples, SAMPLE_RATE, SEED)
    burst_gain = _approach_gain(
        samples,
        sample_rate=SAMPLE_RATE,
        start_s=SHOWCASE_ACTIVE_START_S,
        end_s=SHOWCASE_ACTIVE_END_S,
        hold_after=False,
    )
    continuous_gain = _approach_gain(
        samples,
        sample_rate=SAMPLE_RATE,
        start_s=SHOWCASE_ACTIVE_START_S,
        end_s=SHOWCASE_ACTIVE_END_S,
        hold_after=True,
    )
    burst = _normalize(np.asarray(burst_source) * burst_gain)
    continuous = _normalize(np.asarray(continuous_source) * continuous_gain)
    return (
        {
            "burst": burst,
            "continuous": continuous,
            "burst_gain": burst_gain,
            "continuous_gain": continuous_gain,
        },
        {
            "parameters": parameters,
            "burst_onsets_s": burst_onsets,
            "resolved": resolved,
        },
    )


def _min_max_bins(signal: np.ndarray, bins: int) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(signal, dtype=float).reshape(-1)
    if not values.size or bins <= 0:
        return np.zeros(max(0, bins)), np.zeros(max(0, bins))
    edges = np.linspace(0, values.size, bins + 1, dtype=int)
    lows = np.zeros(bins, dtype=float)
    highs = np.zeros(bins, dtype=float)
    for index in range(bins):
        start = int(edges[index])
        stop = max(start + 1, int(edges[index + 1]))
        section = values[start:min(stop, values.size)]
        lows[index] = float(np.min(section))
        highs[index] = float(np.max(section))
    return lows, highs


def _waveform_path(
    signal: np.ndarray,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    bins: int,
) -> str:
    lows, highs = _min_max_bins(signal, bins)
    if not len(lows):
        return ""
    center = y + height / 2.0
    amplitude = height * 0.46
    x_values = np.linspace(x, x + width, bins)
    top = [
        (float(x_value), center - amplitude * float(np.clip(high, -1.0, 1.0)))
        for x_value, high in zip(x_values, highs, strict=True)
    ]
    bottom = [
        (float(x_value), center - amplitude * float(np.clip(low, -1.0, 1.0)))
        for x_value, low in zip(x_values, lows, strict=True)
    ]
    commands = [f"M {_number(top[0][0])},{_number(top[0][1])}"]
    commands.extend(f"L {_number(point_x)},{_number(point_y)}" for point_x, point_y in top[1:])
    commands.extend(f"L {_number(point_x)},{_number(point_y)}" for point_x, point_y in reversed(bottom))
    commands.append("Z")
    return " ".join(commands)


def _sampled_line_path(
    values: np.ndarray,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    points: int,
    upper: bool,
) -> str:
    indices = np.linspace(0, max(0, len(values) - 1), points, dtype=int)
    center = y + height / 2.0
    amplitude = height * 0.44
    coords: list[tuple[float, float]] = []
    for output_index, sample_index in enumerate(indices):
        gain = float(np.clip(values[int(sample_index)], 0.0, 1.0))
        point_x = x + width * output_index / max(1, points - 1)
        point_y = center + (-1.0 if upper else 1.0) * amplitude * gain
        coords.append((point_x, point_y))
    return " ".join(
        [f"M {_number(coords[0][0])},{_number(coords[0][1])}"]
        + [f"L {_number(point_x)},{_number(point_y)}" for point_x, point_y in coords[1:]]
    )


def _envelope_fill_path(
    values: np.ndarray,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    points: int,
) -> str:
    indices = np.linspace(0, max(0, len(values) - 1), points, dtype=int)
    center = y + height / 2.0
    amplitude = height * 0.44
    top: list[tuple[float, float]] = []
    bottom: list[tuple[float, float]] = []
    for output_index, sample_index in enumerate(indices):
        gain = float(np.clip(values[int(sample_index)], 0.0, 1.0))
        point_x = x + width * output_index / max(1, points - 1)
        top.append((point_x, center - amplitude * gain))
        bottom.append((point_x, center + amplitude * gain))
    commands = [f"M {_number(top[0][0])},{_number(top[0][1])}"]
    commands.extend(f"L {_number(point_x)},{_number(point_y)}" for point_x, point_y in top[1:])
    commands.extend(f"L {_number(point_x)},{_number(point_y)}" for point_x, point_y in reversed(bottom))
    commands.append("Z")
    return " ".join(commands)


def _showcase_metadata(spec: ShowcaseSpec, signal_details: dict[str, Any]) -> dict[str, Any]:
    resolved = signal_details["resolved"]
    metadata: dict[str, Any] = {
        "asset_role": "generated_source_mode_widget",
        "mode": spec.mode,
        "sample_rate_hz": SAMPLE_RATE,
        "duration_s": SHOWCASE_DURATION_S,
        "seed": SEED,
        "noise_distribution": "Gaussian",
        "sample_reduction": "per-column minimum and maximum",
        "waveform_bins": 720,
        "approach": {
            "trajectory": "linear_distance",
            "gain": "reciprocal_distance_1_over_r",
            "start_s": SHOWCASE_ACTIVE_START_S,
            "end_s": SHOWCASE_ACTIVE_END_S,
            "start_radius_m": SHOWCASE_START_RADIUS_M,
            "end_radius_m": SHOWCASE_END_RADIUS_M,
        },
    }
    if spec.mode == "burst":
        metadata.update(
            {
                "source_profile": PPS_LOOMING_GOLD_STANDARD_SOURCE_PROFILE,
                "source_parameters": {
                    "burst_duration_s": resolved["burst_duration_s"],
                    "rise_fall_s": resolved["rise_fall_s"],
                    "target_period_s": resolved["target_period_s"],
                    "active_window_s": resolved["active_window_s"],
                },
                "resolved_burst_count": resolved["burst_count"],
                "resolved_actual_period_s": resolved["actual_period_s"],
            }
        )
    else:
        metadata["source_profile"] = "continuous_noise"
    return metadata


def _render_showcase(
    spec: ShowcaseSpec,
    signal: np.ndarray,
    gain: np.ndarray,
    signal_details: dict[str, Any],
) -> str:
    prefix = "burst" if spec.mode == "burst" else "continuous"
    root, defs = _document(
        width=SHOWCASE_WIDTH,
        height=SHOWCASE_HEIGHT,
        title=spec.title,
        description=spec.description,
        document_id=prefix,
        metadata=_showcase_metadata(spec, signal_details),
    )
    _linear_gradient(defs, f"{prefix}-wave-fill", COLORS["primary"], COLORS["cyan"])
    _linear_gradient(
        defs,
        f"{prefix}-approach-fill",
        COLORS["baseline"],
        COLORS["accent"],
        start_opacity=0.08,
        end_opacity=0.28,
    )
    _clip_rect(defs, f"{prefix}-plot-clip", PANEL_X, PANEL_Y, PANEL_W, PANEL_H)

    _element(root, "rect", {"width": SHOWCASE_WIDTH, "height": SHOWCASE_HEIGHT, "fill": COLORS["background"], "data-layer": "background"})
    _element(
        root,
        "rect",
        {
            "x": 28,
            "y": 24,
            "width": 904,
            "height": 310,
            "fill": COLORS["surface"],
            "stroke": COLORS["line"],
            "data-layer": "frame",
        },
    )
    _text(root, spec.title, 56, 59, size=24, weight=700, data_layer="title")
    _text(root, spec.subtitle, 56, 82, fill=COLORS["muted"], size=13, data_layer="subtitle")

    chip = _element(root, "g", {"transform": "translate(680 40)", "data-layer": "parameter-chip"})
    _element(
        chip,
        "rect",
        {
            "width": 205,
            "height": 28,
            "fill": COLORS["chip_surface"],
            "stroke": COLORS["chip_line"],
        },
    )
    _element(chip, "circle", {"cx": 17, "cy": 14, "r": 5, "fill": COLORS["primary"]})
    chip_text = "30 ms bursts / 95 ms target" if spec.mode == "burst" else "continuous / 1/r gain"
    _text(chip, chip_text, 31, 18, fill=COLORS["primary_hover"], size=11, weight=700)

    _element(
        root,
        "rect",
        {
            "x": PANEL_X + 6,
            "y": PANEL_Y + 8,
            "width": PANEL_W,
            "height": PANEL_H,
            "fill": "#071612",
            "opacity": 0.14,
            "data-layer": "vector-shadow",
        },
    )
    _element(
        root,
        "rect",
        {
            "x": PANEL_X,
            "y": PANEL_Y,
            "width": PANEL_W,
            "height": PANEL_H,
            "fill": COLORS["panel"],
            "stroke": COLORS["plot_border"],
            "stroke-width": 1.2,
            "data-layer": "plot-background",
        },
    )
    plot = _element(
        root,
        "g",
        {
            "clip-path": f"url(#{prefix}-plot-clip)",
            "data-layer": "plot",
        },
    )
    for index in range(9):
        line_x = PANEL_X + PANEL_W * index / 8
        _element(
            plot,
            "line",
            {
                "x1": line_x,
                "y1": PANEL_Y,
                "x2": line_x,
                "y2": PANEL_Y + PANEL_H,
                "stroke": COLORS["panel_line"],
                "stroke-width": 1.1 if index in (0, 8) else 0.7,
                "opacity": 0.82 if index in (0, 8) else 0.52,
                "data-layer": "grid",
            },
        )
    for index in range(5):
        line_y = PANEL_Y + PANEL_H * index / 4
        _element(
            plot,
            "line",
            {
                "x1": PANEL_X,
                "y1": line_y,
                "x2": PANEL_X + PANEL_W,
                "y2": line_y,
                "stroke": COLORS["panel_line"],
                "stroke-width": 1.2 if index == 2 else 0.7,
                "opacity": 0.92 if index == 2 else 0.46,
                "data-layer": "grid",
            },
        )

    _element(
        plot,
        "path",
        {
            "d": _envelope_fill_path(
                gain,
                x=PANEL_X,
                y=PANEL_Y,
                width=PANEL_W,
                height=PANEL_H,
                points=160,
            ),
            "fill": f"url(#{prefix}-approach-fill)",
            "data-layer": "approach-envelope-fill",
            "data-envelope": "reciprocal-distance",
        },
    )
    _element(
        plot,
        "path",
        {
            "d": _waveform_path(
                signal,
                x=PANEL_X,
                y=PANEL_Y,
                width=PANEL_W,
                height=PANEL_H,
                bins=720,
            ),
            "fill": f"url(#{prefix}-wave-fill)",
            "stroke": COLORS["cyan"],
            "stroke-width": 0.45,
            "opacity": 0.9,
            "data-layer": "waveform",
            "data-channel": "generated-source",
            "data-sample-reduction": "min-max-bin",
        },
    )

    if spec.mode == "burst":
        for onset_s in signal_details["burst_onsets_s"]:
            onset_index = min(len(gain) - 1, int(round(onset_s * SAMPLE_RATE)))
            marker_gain = float(gain[onset_index])
            marker_x = PANEL_X + PANEL_W * onset_s / SHOWCASE_DURATION_S
            top_y = PANEL_Y + PANEL_H / 2 - PANEL_H * 0.44 * marker_gain
            bottom_y = PANEL_Y + PANEL_H / 2 + PANEL_H * 0.44 * marker_gain
            _element(
                plot,
                "line",
                {
                    "x1": marker_x,
                    "y1": top_y,
                    "x2": marker_x,
                    "y2": bottom_y,
                    "stroke": COLORS["accent"],
                    "stroke-width": 0.9,
                    "opacity": 0.25,
                    "data-layer": "burst-onset",
                },
            )
            _element(
                plot,
                "circle",
                {
                    "cx": marker_x,
                    "cy": top_y,
                    "r": 1.8,
                    "fill": COLORS["accent"],
                    "data-layer": "burst-peak",
                },
            )

    for upper, color, width_value in (
        (True, COLORS["accent"], 2.8),
        (False, COLORS["orange"], 2.0),
    ):
        _element(
            plot,
            "path",
            {
                "d": _sampled_line_path(
                    gain,
                    x=PANEL_X,
                    y=PANEL_Y,
                    width=PANEL_W,
                    height=PANEL_H,
                    points=160,
                    upper=upper,
                ),
                "fill": "none",
                "stroke": color,
                "stroke-width": width_value,
                "stroke-linecap": "round",
                "stroke-linejoin": "round",
                "stroke-dasharray": "7 7" if spec.mode == "burst" else "none",
                "opacity": 0.92 if upper else 0.72,
                "data-layer": "approach-envelope",
                "data-envelope-side": "upper" if upper else "lower",
            },
        )

    _text(root, spec.label, PANEL_X + 12, PANEL_Y + 18, fill=COLORS["plot_label"], size=10, family=FONT_MONO, data_layer="plot-label")
    _text(root, "PEAK ENVELOPE - RECIPROCAL DISTANCE", PANEL_X + PANEL_W, PANEL_Y - 12, fill=COLORS["muted"], size=10, family=FONT_MONO, anchor="end")
    _text(root, "far / quiet", PANEL_X, PANEL_Y + PANEL_H + 30, fill=COLORS["muted"], size=12)
    _text(root, "near / loud", PANEL_X + PANEL_W, PANEL_Y + PANEL_H + 30, fill=COLORS["muted"], size=12, anchor="end")
    _element(
        root,
        "line",
        {
            "x1": PANEL_X + 92,
            "y1": PANEL_Y + PANEL_H + 25,
            "x2": PANEL_X + PANEL_W - 92,
            "y2": PANEL_Y + PANEL_H + 25,
            "stroke": COLORS["line"],
            "stroke-width": 1.2,
            "data-layer": "direction-axis",
        },
    )
    _element(
        root,
        "path",
        {
            "d": f"M {PANEL_X + PANEL_W - 104},{PANEL_Y + PANEL_H + 19} L {PANEL_X + PANEL_W - 92},{PANEL_Y + PANEL_H + 25} L {PANEL_X + PANEL_W - 104},{PANEL_Y + PANEL_H + 31}",
            "fill": "none",
            "stroke": COLORS["line"],
            "stroke-width": 1.2,
            "stroke-linecap": "round",
            "stroke-linejoin": "round",
            "data-layer": "direction-arrow",
        },
    )
    _element(root, "rect", {"x": 56, "y": 314, "width": 14, "height": 7, "fill": COLORS["primary"], "data-layer": "legend-swatch"})
    _text(root, "sample-derived waveform", 78, 322, fill=COLORS["muted"], size=11)
    _element(
        root,
        "line",
        {
            "x1": 230,
            "y1": 318,
            "x2": 264,
            "y2": 318,
            "stroke": COLORS["accent"],
            "stroke-width": 3,
            "stroke-linecap": "round",
            "stroke-dasharray": "7 7" if spec.mode == "burst" else "none",
            "data-layer": "legend-envelope",
        },
    )
    _text(root, "approach gain", 274, 322, fill=COLORS["muted"], size=11)
    return _serialize(root)


def _render_showcase_widget(
    spec: ShowcaseSpec,
    signal: np.ndarray,
    gain: np.ndarray,
    signal_details: dict[str, Any],
) -> str:
    """Render the signal as a compact selectable-control preview."""

    prefix = f"{spec.mode}-widget"
    metadata = _showcase_metadata(spec, signal_details)
    metadata.update(
        {
            "asset_role": "source_mode_control_preview",
            "composition": "compact_transparent_widget",
            "waveform_bins": 256,
        }
    )
    root, defs = _document(
        width=SOURCE_WIDGET_WIDTH,
        height=SOURCE_WIDGET_HEIGHT,
        title=f"{spec.title} source preview",
        description=(
            f"Compact native-vector interface preview of {spec.description.lower()}"
        ),
        document_id=prefix,
        metadata=metadata,
    )
    _linear_gradient(defs, f"{prefix}-wave-fill", COLORS["primary"], COLORS["cyan"])
    _linear_gradient(
        defs,
        f"{prefix}-gain-fill",
        COLORS["baseline"],
        COLORS["accent"],
        start_opacity=0.05,
        end_opacity=0.22,
    )
    _clip_rect(
        defs,
        f"{prefix}-clip",
        SOURCE_WIDGET_PANEL_X,
        SOURCE_WIDGET_PANEL_Y,
        SOURCE_WIDGET_PANEL_W,
        SOURCE_WIDGET_PANEL_H,
    )

    _element(
        root,
        "rect",
        {
            "width": SOURCE_WIDGET_WIDTH,
            "height": SOURCE_WIDGET_HEIGHT,
            "fill": "none",
            "data-layer": "transparent-background",
        },
    )
    _element(
        root,
        "rect",
        {
            "x": SOURCE_WIDGET_PANEL_X,
            "y": SOURCE_WIDGET_PANEL_Y,
            "width": SOURCE_WIDGET_PANEL_W,
            "height": SOURCE_WIDGET_PANEL_H,
            "rx": 5,
            "fill": COLORS["widget_plot"],
            "stroke": COLORS["plot_border"],
            "data-layer": "plot-background",
        },
    )
    plot = _element(
        root,
        "g",
        {
            "clip-path": f"url(#{prefix}-clip)",
            "data-layer": "plot",
        },
    )
    for index in range(9):
        line_x = SOURCE_WIDGET_PANEL_X + SOURCE_WIDGET_PANEL_W * index / 8
        _element(
            plot,
            "line",
            {
                "x1": line_x,
                "y1": SOURCE_WIDGET_PANEL_Y,
                "x2": line_x,
                "y2": SOURCE_WIDGET_PANEL_Y + SOURCE_WIDGET_PANEL_H,
                "stroke": COLORS["widget_grid"],
                "stroke-width": 0.6,
                "data-layer": "grid",
            },
        )
    for index in range(3):
        line_y = SOURCE_WIDGET_PANEL_Y + SOURCE_WIDGET_PANEL_H * index / 2
        _element(
            plot,
            "line",
            {
                "x1": SOURCE_WIDGET_PANEL_X,
                "y1": line_y,
                "x2": SOURCE_WIDGET_PANEL_X + SOURCE_WIDGET_PANEL_W,
                "y2": line_y,
                "stroke": COLORS["widget_grid"],
                "stroke-width": 0.8 if index == 1 else 0.5,
                "data-layer": "grid",
            },
        )
    _element(
        plot,
        "path",
        {
            "d": _envelope_fill_path(
                gain,
                x=SOURCE_WIDGET_PANEL_X,
                y=SOURCE_WIDGET_PANEL_Y,
                width=SOURCE_WIDGET_PANEL_W,
                height=SOURCE_WIDGET_PANEL_H,
                points=96,
            ),
            "fill": f"url(#{prefix}-gain-fill)",
            "data-layer": "approach-envelope-fill",
        },
    )
    _element(
        plot,
        "path",
        {
            "d": _waveform_path(
                signal,
                x=SOURCE_WIDGET_PANEL_X,
                y=SOURCE_WIDGET_PANEL_Y,
                width=SOURCE_WIDGET_PANEL_W,
                height=SOURCE_WIDGET_PANEL_H,
                bins=256,
            ),
            "fill": f"url(#{prefix}-wave-fill)",
            "stroke": COLORS["cyan"],
            "stroke-width": 0.35,
            "opacity": 0.92,
            "data-layer": "waveform",
            "data-channel": "generated-source",
            "data-sample-reduction": "min-max-bin",
        },
    )
    if spec.mode == "burst":
        for onset_s in signal_details["burst_onsets_s"]:
            onset_index = min(len(gain) - 1, int(round(onset_s * SAMPLE_RATE)))
            marker_gain = float(gain[onset_index])
            marker_x = SOURCE_WIDGET_PANEL_X + SOURCE_WIDGET_PANEL_W * onset_s / SHOWCASE_DURATION_S
            top_y = SOURCE_WIDGET_PANEL_Y + SOURCE_WIDGET_PANEL_H / 2 - SOURCE_WIDGET_PANEL_H * 0.44 * marker_gain
            _element(
                plot,
                "circle",
                {
                    "cx": marker_x,
                    "cy": top_y,
                    "r": 0.85,
                    "fill": COLORS["accent"],
                    "data-layer": "burst-peak",
                },
            )
    for upper in (True, False):
        _element(
            plot,
            "path",
            {
                "d": _sampled_line_path(
                    gain,
                    x=SOURCE_WIDGET_PANEL_X,
                    y=SOURCE_WIDGET_PANEL_Y,
                    width=SOURCE_WIDGET_PANEL_W,
                    height=SOURCE_WIDGET_PANEL_H,
                    points=96,
                    upper=upper,
                ),
                "fill": "none",
                "stroke": COLORS["accent"] if upper else COLORS["orange"],
                "stroke-width": 1.15 if upper else 0.85,
                "stroke-linecap": "round",
                "stroke-dasharray": "3 3" if spec.mode == "burst" else "none",
                "opacity": 0.88,
                "data-layer": "approach-envelope",
            },
        )

    chip_label = "33 BURSTS / 95 MS" if spec.mode == "burst" else "CONTINUOUS / 1/R"
    chip_width = 91 if spec.mode == "burst" else 88
    chip_x = SOURCE_WIDGET_WIDTH - chip_width - 9
    _element(
        root,
        "rect",
        {
            "x": chip_x,
            "y": 9,
            "width": chip_width,
            "height": 15,
            "rx": 3,
            "fill": COLORS["chip_surface"],
            "stroke": COLORS["chip_line"],
            "data-layer": "parameter-chip",
        },
    )
    _text(
        root,
        chip_label,
        chip_x + chip_width / 2,
        19,
        fill=COLORS["primary_hover"],
        size=7.2,
        family=FONT_MONO,
        weight=700,
        anchor="middle",
        data_layer="parameter-chip-label",
    )
    _text(root, "far / quiet", 6, 89, fill=COLORS["muted"], size=8.2, weight=700)
    _text(root, "near / loud", 314, 89, fill=COLORS["muted"], size=8.2, weight=700, anchor="end")
    _element(
        root,
        "line",
        {
            "x1": 61,
            "y1": 86,
            "x2": 253,
            "y2": 86,
            "stroke": COLORS["line_strong"],
            "stroke-width": 1,
            "data-layer": "direction-axis",
        },
    )
    _element(
        root,
        "path",
        {
            "d": "M 248,82 L 254,86 L 248,90",
            "fill": "none",
            "stroke": COLORS["line_strong"],
            "stroke-width": 1,
            "stroke-linecap": "round",
            "stroke-linejoin": "round",
            "data-layer": "direction-arrow",
        },
    )
    return _serialize(root)


def _mini_signals() -> dict[str, np.ndarray]:
    samples = int(round(BASELINE_DURATION_S * SAMPLE_RATE))
    continuous = render_backend._generate_noise("white", samples, SAMPLE_RATE, SEED + 101)
    gain = _approach_gain(
        samples,
        sample_rate=SAMPLE_RATE,
        start_s=0.08,
        end_s=BASELINE_DURATION_S - 0.08,
        hold_after=True,
    )
    looming = _normalize(np.asarray(continuous) * gain)
    stationary_parameters = gold_standard_looming_source_parameters(
        {
            "onset_s": 0.04,
            "active_window_s": BASELINE_DURATION_S - 0.08,
        }
    )
    stationary = render_backend._generate_dynaspace_burst_train(
        "white",
        samples,
        SAMPLE_RATE,
        SEED + 202,
        stationary_parameters,
    )
    return {
        "looming": _normalize(np.asarray(looming)),
        "stationary": _normalize(np.asarray(stationary)),
        "silent": np.zeros(samples, dtype=float),
    }


def _tactile_track(positions: Sequence[float]) -> np.ndarray:
    samples = int(round(BASELINE_DURATION_S * SAMPLE_RATE))
    track = np.zeros(samples, dtype=float)
    cue = render_backend._tactile_waveform(
        {
            "tactile": {
                "waveform": {
                    "duration_s": 0.10,
                    "attack_frequency_hz": 200,
                    "decay_frequency_hz": 50,
                    "peak_normalization": 0.95,
                }
            }
        },
        SAMPLE_RATE,
    )
    for normalized_position in positions:
        onset = int(round(float(normalized_position) * samples))
        stop = min(samples, onset + len(cue))
        if stop > onset:
            track[onset:stop] += cue[: stop - onset]
    return _normalize(track)


def _render_baseline_preview(spec: BaselineSpec, mini_signals: dict[str, np.ndarray]) -> str:
    plot_x = 56
    plot_y = 6
    plot_w = 260
    plot_h = 84
    audio_center_y = 30
    tactile_center_y = 66
    root, defs = _document(
        width=BASELINE_WIDTH,
        height=BASELINE_HEIGHT,
        title=spec.title,
        description=(
            f"Native-vector timeline preview for the {spec.title} baseline strategy, "
            "showing audio and tactile signal lanes."
        ),
        document_id=spec.filename.removesuffix(".svg").replace("_", "-"),
        metadata={
            "asset_role": "baseline_strategy_widget",
            "strategy": spec.filename.removeprefix("baseline_").removesuffix(".svg"),
            "sample_rate_hz": SAMPLE_RATE,
            "duration_s": BASELINE_DURATION_S,
            "seed": SEED,
            "audio_mode": spec.audio_mode,
            "tactile_positions_normalized": list(spec.tactile_positions),
            "sample_reduction": "per-column minimum and maximum",
            "waveform_bins": 190,
        },
    )
    _linear_gradient(defs, "baseline-audio-fill", COLORS["primary"], COLORS["cyan"])
    _clip_rect(defs, "baseline-preview-clip", plot_x, plot_y, plot_w, plot_h)

    _element(
        root,
        "rect",
        {
            "width": BASELINE_WIDTH,
            "height": BASELINE_HEIGHT,
            "fill": "none",
            "data-layer": "transparent-background",
        },
    )
    _element(
        root,
        "rect",
        {
            "x": plot_x,
            "y": plot_y,
            "width": plot_w,
            "height": plot_h,
            "rx": 5,
            "fill": COLORS["widget_plot"],
            "stroke": COLORS["plot_border"],
            "data-layer": "plot-background",
        },
    )
    _text(root, "AUDIO", 49, 33, fill=COLORS["muted"], size=9.5, family=FONT_MONO, weight=700, anchor="end", data_layer="channel-label")
    _text(root, "TACTILE", 49, 69, fill=COLORS["muted"], size=9.5, family=FONT_MONO, weight=700, anchor="end", data_layer="channel-label")

    plot = _element(root, "g", {"clip-path": "url(#baseline-preview-clip)", "data-layer": "plot"})
    for index in range(6):
        grid_x = plot_x + plot_w * index / 5
        _element(
            plot,
            "line",
            {
                "x1": grid_x,
                "y1": plot_y,
                "x2": grid_x,
                "y2": plot_y + plot_h,
                "stroke": COLORS["widget_grid"],
                "stroke-width": 0.7,
                "data-layer": "grid",
            },
        )
    for center_y in (audio_center_y, tactile_center_y):
        _element(
            plot,
            "line",
            {
                "x1": plot_x,
                "y1": center_y,
                "x2": plot_x + plot_w,
                "y2": center_y,
                "stroke": COLORS["widget_grid"],
                "stroke-width": 0.8,
                "data-layer": "channel-center",
            },
        )

    signal_key = "looming" if spec.audio_mode == "optional" else spec.audio_mode
    audio_signal = mini_signals[signal_key]
    audio_opacity = 0.34 if spec.audio_mode == "optional" else (0.0 if spec.audio_mode == "silent" else 0.9)
    if audio_opacity > 0:
        _element(
            plot,
            "path",
            {
                "d": _waveform_path(audio_signal, x=plot_x, y=16, width=plot_w, height=28, bins=190),
                "fill": "url(#baseline-audio-fill)",
                "stroke": COLORS["cyan"],
                "stroke-width": 0.35,
                "opacity": audio_opacity,
                "data-layer": "waveform",
                "data-channel": "audio",
                "data-sample-reduction": "min-max-bin",
            },
        )
    else:
        _element(
            plot,
            "line",
            {
                "x1": plot_x,
                "y1": audio_center_y,
                "x2": plot_x + plot_w,
                "y2": audio_center_y,
                "stroke": COLORS["silenced"],
                "stroke-width": 1.2,
                "stroke-dasharray": "4 4",
                "data-layer": "silenced-audio",
            },
        )

    tactile = _tactile_track(spec.tactile_positions)
    _element(
        plot,
        "path",
        {
            "d": _waveform_path(tactile, x=plot_x, y=52, width=plot_w, height=28, bins=190),
            "fill": COLORS["orange"],
            "stroke": COLORS["accent"],
            "stroke-width": 0.35,
            "opacity": 0.92,
            "data-layer": "waveform",
            "data-channel": "tactile",
            "data-sample-reduction": "min-max-bin",
        },
    )
    for index, normalized_position in enumerate(spec.tactile_positions):
        marker_x = plot_x + plot_w * normalized_position
        _element(
            plot,
            "line",
            {
                "x1": marker_x,
                "y1": 10,
                "x2": marker_x,
                "y2": 86,
                "stroke": COLORS["accent"],
                "stroke-width": 0.9,
                "stroke-dasharray": "3 3",
                "opacity": 0.72,
                "data-layer": "soa-marker",
            },
        )
        if index < len(spec.marker_labels):
            anchor = "start" if normalized_position < 0.5 else "end"
            label_x = marker_x + (3 if anchor == "start" else -3)
            _text(
                plot,
                spec.marker_labels[index],
                label_x,
                17,
                fill=COLORS["accent"],
                size=8.5,
                family=FONT_MONO,
                weight=700,
                anchor=anchor,
                data_layer="soa-label",
            )

    if spec.filename == "baseline_none.svg":
        _text(
            plot,
            "TRIAL ONLY",
            plot_x + plot_w - 6,
            17,
            fill=COLORS["plot_label_strong"],
            size=8.5,
            family=FONT_MONO,
            weight=700,
            anchor="end",
            data_layer="no-extra-baseline-mark",
        )

    return _serialize(root)


def _audiogram_signals() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    duration_s = 2.0
    samples = int(round(duration_s * SAMPLE_RATE))
    source = np.asarray(render_backend._generate_noise("white", samples, SAMPLE_RATE, SEED + 303))
    secondary = np.asarray(render_backend._generate_noise("white", samples, SAMPLE_RATE, SEED + 304))
    times = np.arange(samples, dtype=float) / SAMPLE_RATE
    active_start_s = 0.28
    active_end_s = 1.66
    progress = np.clip((times - active_start_s) / (active_end_s - active_start_s), 0.0, 1.0)
    radius = 1.40 + (0.20 - 1.40) * progress
    gain = (1.0 / radius) / (1.0 / 0.20)
    gain[(times < active_start_s) | (times > active_end_s)] = 0.0
    fade_samples = int(round(0.02 * SAMPLE_RATE))
    active_indices = np.flatnonzero(gain > 0)
    if active_indices.size and fade_samples:
        fade = np.linspace(0.0, 1.0, fade_samples, endpoint=True)
        first = int(active_indices[0])
        last = int(active_indices[-1])
        gain[first:min(first + fade_samples, samples)] *= fade[: min(fade_samples, samples - first)]
        fade_start = max(first, last - fade_samples + 1)
        fade_length = last - fade_start + 1
        gain[fade_start:last + 1] *= fade[:fade_length][::-1]
    left = _normalize(source * gain)
    shifted = np.roll(source, 5)
    right = _normalize((0.94 * shifted + 0.06 * secondary) * gain)

    tactile = np.zeros(samples, dtype=float)
    cue = render_backend._tactile_waveform(
        {
            "tactile": {
                "waveform": {
                    "duration_s": 0.10,
                    "attack_frequency_hz": 200,
                    "decay_frequency_hz": 50,
                    "peak_normalization": 0.95,
                }
            }
        },
        SAMPLE_RATE,
    )
    tactile_onset = int(round(1.30 * SAMPLE_RATE))
    tactile_stop = min(samples, tactile_onset + len(cue))
    tactile[tactile_onset:tactile_stop] = cue[: tactile_stop - tactile_onset]
    return left, right, tactile


def _render_audiogram() -> str:
    width = 820
    height = 300
    timeline_x = 100
    timeline_w = 712
    duration_s = 2.0
    soa_s = 1.30
    channels = (
        ("left-audio", "Ch 1", "Left Audio", 32, COLORS["primary"]),
        ("right-audio", "Ch 2", "Right Audio", 109, COLORS["cyan"]),
        ("tactile-drive", "Ch 3", "Tactile Drive", 186, COLORS["orange"]),
    )
    signals = _audiogram_signals()
    root, defs = _document(
        width=width,
        height=height,
        title="Three-channel looming trial audiogram",
        description=(
            "Native-vector sample-derived audiogram with left audio, right audio, "
            "and tactile drive channels on a shared two-second timeline."
        ),
        document_id="looming-audiogram",
        metadata={
            "asset_role": "architecture_audiogram",
            "sample_rate_hz": SAMPLE_RATE,
            "duration_s": duration_s,
            "seed": SEED,
            "source_profile": "continuous_noise",
            "noise_distribution": "Gaussian",
            "approach": {
                "trajectory": "linear_distance",
                "gain": "reciprocal_distance_1_over_r",
                "active_start_s": 0.28,
                "active_end_s": 1.66,
                "start_radius_m": 1.40,
                "end_radius_m": 0.20,
            },
            "tactile": {
                "soa_s": soa_s,
                "duration_s": 0.10,
                "attack_frequency_hz": 200,
                "decay_frequency_hz": 50,
            },
            "channels": ["left_audio", "right_audio", "tactile_drive"],
            "sample_reduction": "per-column minimum and maximum",
            "waveform_bins": 475,
            "spatialization_boundary": "illustrative stereo preview; not an HRTF render",
        },
    )
    for channel_id, _channel, _label, lane_y, _color in channels:
        _clip_rect(defs, f"{channel_id}-clip", timeline_x, lane_y, timeline_w, 72)

    _element(root, "rect", {"width": width, "height": height, "fill": COLORS["widget_plot"], "data-layer": "background"})
    for tick_index in range(9):
        milliseconds = tick_index * 250
        tick_x = timeline_x + timeline_w * tick_index / 8
        _element(
            root,
            "line",
            {
                "x1": tick_x,
                "y1": 30,
                "x2": tick_x,
                "y2": 34,
                "stroke": COLORS["widget_grid"],
                "data-layer": "time-tick",
                "data-time-ms": milliseconds,
            },
        )
        label = "0" if milliseconds == 0 else f"{milliseconds} ms"
        anchor = "start" if tick_index == 0 else ("end" if tick_index == 8 else "middle")
        label_x = tick_x + (2 if tick_index == 0 else (-2 if tick_index == 8 else 0))
        _text(root, label, label_x, 28, fill=COLORS["plot_label"], size=9, family=FONT_MONO, anchor=anchor, data_layer="time-label")
    _element(root, "line", {"x1": timeline_x, "y1": 30, "x2": timeline_x + timeline_w, "y2": 30, "stroke": COLORS["widget_grid"], "stroke-width": 0.5, "data-layer": "time-axis"})

    for (channel_id, channel_label, description, lane_y, color), signal in zip(channels, signals, strict=True):
        _element(
            root,
            "rect",
            {
                "x": timeline_x,
                "y": lane_y,
                "width": timeline_w,
                "height": 72,
                "fill": COLORS["widget_lane"],
                "data-layer": "channel-background",
                "data-channel": channel_id,
            },
        )
        center_y = lane_y + 36
        _element(
            root,
            "line",
            {
                "x1": timeline_x,
                "y1": center_y,
                "x2": timeline_x + timeline_w,
                "y2": center_y,
                "stroke": COLORS["widget_grid"],
                "stroke-width": 0.75,
                "data-layer": "channel-center",
                "data-channel": channel_id,
            },
        )
        channel_group = _element(
            root,
            "g",
            {
                "clip-path": f"url(#{channel_id}-clip)",
                "data-layer": "channel-waveform",
                "data-channel": channel_id,
            },
        )
        _element(
            channel_group,
            "path",
            {
                "d": _waveform_path(signal, x=timeline_x, y=lane_y, width=timeline_w, height=72, bins=475),
                "fill": color,
                "stroke": COLORS["accent"] if channel_id == "tactile-drive" else color,
                "stroke-width": 0.35,
                "opacity": 0.86,
                "data-layer": "waveform",
                "data-channel": channel_id,
                "data-sample-reduction": "min-max-bin",
            },
        )
        _element(
            root,
            "rect",
            {
                "x": 0,
                "y": lane_y,
                "width": timeline_x,
                "height": 72,
                "fill": COLORS["widget_plot"],
                "data-layer": "channel-label-background",
            },
        )
        _text(root, channel_label, 90, lane_y + 30, fill=COLORS["plot_label_strong"], size=11, family=FONT_MONO, weight=700, anchor="end", data_layer="channel-label")
        _text(root, description, 90, lane_y + 44, fill=COLORS["plot_label"], size=9, anchor="end", data_layer="channel-description")
        _element(
            root,
            "line",
            {
                "x1": timeline_x,
                "y1": lane_y,
                "x2": timeline_x,
                "y2": lane_y + 72,
                "stroke": COLORS["widget_grid"],
                "stroke-width": 0.75,
                "data-layer": "channel-boundary",
            },
        )

    soa_x = timeline_x + timeline_w * soa_s / duration_s
    for lane_y in (32, 109, 186):
        _element(
            root,
            "line",
            {
                "x1": soa_x,
                "y1": lane_y,
                "x2": soa_x,
                "y2": lane_y + 72,
                "stroke": COLORS["orange"],
                "stroke-width": 0.75,
                "stroke-dasharray": "3 2",
                "opacity": 0.72,
                "data-layer": "soa-marker",
                "data-soa-ms": 1300,
            },
        )
    _text(root, "SOA", soa_x + 3, 42, fill=COLORS["orange"], size=8.5, family=FONT_MONO, data_layer="soa-label")

    active_start_x = timeline_x + timeline_w * 0.28 / duration_s
    active_end_x = timeline_x + timeline_w * 1.66 / duration_s
    _element(root, "line", {"x1": active_start_x, "y1": 263, "x2": active_end_x, "y2": 263, "stroke": COLORS["stimulus_span"], "data-layer": "stimulus-span"})
    for marker_x in (active_start_x, active_end_x):
        _element(root, "line", {"x1": marker_x, "y1": 260, "x2": marker_x, "y2": 266, "stroke": COLORS["stimulus_span"], "data-layer": "stimulus-span-boundary"})
    _text(root, "LOOMING STIMULUS", (active_start_x + active_end_x) / 2, 276, fill=COLORS["stimulus_span"], size=8.5, anchor="middle", data_layer="stimulus-span-label")
    _text(root, "TACTILE", soa_x + 27, 276, fill=COLORS["tactile_text"], size=8.5, anchor="middle", data_layer="tactile-label")
    _text(root, "EXAMPLE LOOMING TRIAL - NATIVE MIN/MAX SVG - SHARED 44.1 KHZ SAMPLE CLOCK", timeline_x, 293, fill=COLORS["footer"], size=8.5, data_layer="footer")
    return _serialize(root)


def generate_svg_documents() -> dict[str, str]:
    signals, signal_details = _showcase_signals()
    documents = {
        spec.filename: _render_showcase(
            spec,
            signals[spec.mode],
            signals[f"{spec.mode}_gain"],
            signal_details,
        )
        for spec in SHOWCASE_SPECS
    }
    documents.update(
        {
            SHOWCASE_WIDGET_FILENAMES[spec.mode]: _render_showcase_widget(
                spec,
                signals[spec.mode],
                signals[f"{spec.mode}_gain"],
                signal_details,
            )
            for spec in SHOWCASE_SPECS
        }
    )
    documents["audiogram_looming_trial.svg"] = _render_audiogram()
    mini_signals = _mini_signals()
    documents.update(
        {
            spec.filename: _render_baseline_preview(spec, mini_signals)
            for spec in BASELINE_SPECS
        }
    )
    return documents


def _write_documents(documents: dict[str, str], output_dirs: Iterable[Path]) -> None:
    for output_dir in output_dirs:
        output_dir.mkdir(parents=True, exist_ok=True)
        for filename, svg in documents.items():
            path = output_dir / filename
            path.write_text(svg, encoding="utf-8", newline="\n")
            print(f"Wrote {path}")


def _check_documents(documents: dict[str, str], output_dirs: Iterable[Path]) -> int:
    stale: list[Path] = []
    for output_dir in output_dirs:
        for filename, expected in documents.items():
            path = output_dir / filename
            if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                stale.append(path)
    if stale:
        print("Generated SVGs are missing or stale:", file=sys.stderr)
        for path in stale:
            print(f"  {path}", file=sys.stderr)
        return 1
    print(f"All {len(documents)} generated SVGs match in {len(tuple(output_dirs))} output directories.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when committed generated SVGs differ from the deterministic pipeline output.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Write one complete asset set to this directory instead of the canonical package directories.",
    )
    args = parser.parse_args(argv)
    if args.check and args.output_dir:
        parser.error("--check and --output-dir cannot be used together")

    documents = generate_svg_documents()
    output_dirs = (ASSET_DIR, DASHBOARD_DIR)
    if args.check:
        return _check_documents(documents, output_dirs)
    if args.output_dir:
        output_dirs = (args.output_dir,)
    _write_documents(documents, output_dirs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
