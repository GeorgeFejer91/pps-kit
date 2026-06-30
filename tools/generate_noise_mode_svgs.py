"""Generate publication/widget SVGs for PPS-kit generated-noise modes."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "src" / "peripersonal_space_toolkit" / "assets"
DASHBOARD_DIR = ROOT / "src" / "peripersonal_space_toolkit" / "dashboard"

WIDTH = 960
HEIGHT = 360
PANEL_X = 96
PANEL_Y = 98
PANEL_W = 792
PANEL_H = 166
CENTER_Y = PANEL_Y + PANEL_H / 2
MAX_AMP = PANEL_H * 0.42

COLORS = {
    "background": "#f4f5f1",
    "surface": "#ffffff",
    "text": "#202621",
    "muted": "#68746c",
    "line": "#d9dfd6",
    "panel": "#141f1a",
    "panel_soft": "#1b2821",
    "panel_line": "#2e4038",
    "primary": "#246b55",
    "primary_hover": "#1d5846",
    "cyan": "#69cfc3",
    "accent": "#f2a74b",
    "orange": "#c06030",
    "baseline": "#4b5fa8",
    "white_noise": "#d8dde2",
}


@dataclass(frozen=True)
class GraphicSpec:
    filename: str
    title: str
    subtitle: str
    label: str
    mode: str
    description: str


def f(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text if text else "0"


def x_for_t(t: float) -> float:
    return PANEL_X + PANEL_W * t


def noise_texture(t: float, seed: float) -> float:
    value = (
        math.sin(math.tau * (31.0 * t + 0.071 * seed))
        + 0.58 * math.sin(math.tau * (79.0 * t + 0.137 * seed))
        + 0.34 * math.sin(math.tau * (151.0 * t + 0.019 * seed))
        + 0.21 * math.sin(math.tau * (233.0 * t + 0.173 * seed))
    )
    return min(1.0, max(0.06, abs(value) / 1.88))


def smoothstep(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return t * t * (3.0 - 2.0 * t)


def continuous_envelope(t: float) -> float:
    if t < 0.08:
        return 0.12
    if t > 0.92:
        return 0.94
    u = (t - 0.08) / 0.84
    return 0.12 + 0.82 * u


def burst_envelope(t: float) -> tuple[float, float]:
    active_start = 0.10
    active_end = 0.90
    if t < active_start or t > active_end:
        return 0.0, 0.0

    count = 24
    span = active_end - active_start
    period = span / (count - 1)
    sigma = period * 0.16
    local = 0.0
    nearest_u = 0.0
    for index in range(count):
        center = active_start + period * index
        candidate = math.exp(-0.5 * ((t - center) / sigma) ** 2)
        if candidate > local:
            local = candidate
            nearest_u = index / (count - 1)
    if local < 0.035:
        return 0.0, 0.0
    peak = 0.15 + 0.80 * nearest_u
    return peak * local, peak


def waveform_path(spec: GraphicSpec) -> str:
    top: list[tuple[float, float]] = []
    bottom: list[tuple[float, float]] = []
    samples = 760
    for i in range(samples + 1):
        t = i / samples
        if spec.mode == "burst":
            local_env, _ = burst_envelope(t)
            height = MAX_AMP * local_env * (0.32 + 0.68 * noise_texture(t, 3.0))
        else:
            env = continuous_envelope(t)
            height = MAX_AMP * env * (0.38 + 0.62 * noise_texture(t, 7.0))
        x = x_for_t(t)
        top.append((x, CENTER_Y - height))
        bottom.append((x, CENTER_Y + height))
    commands = [f"M {f(top[0][0])},{f(top[0][1])}"]
    commands.extend(f"L {f(x)},{f(y)}" for x, y in top[1:])
    commands.extend(f"L {f(x)},{f(y)}" for x, y in reversed(bottom))
    commands.append("Z")
    return " ".join(commands)


def envelope_paths(spec: GraphicSpec) -> tuple[str, str, str]:
    top: list[tuple[float, float]] = []
    bottom: list[tuple[float, float]] = []
    samples = 96
    for i in range(samples + 1):
        t = i / samples
        if spec.mode == "burst":
            if t < 0.10 or t > 0.90:
                env = 0.0
            else:
                u = (t - 0.10) / 0.80
                env = 0.15 + 0.80 * u
        else:
            env = continuous_envelope(t)
        top.append((x_for_t(t), CENTER_Y - MAX_AMP * env))
        bottom.append((x_for_t(t), CENTER_Y + MAX_AMP * env))
    top_path = " ".join([f"M {f(top[0][0])},{f(top[0][1])}"] + [f"L {f(x)},{f(y)}" for x, y in top[1:]])
    bottom_path = " ".join(
        [f"M {f(bottom[0][0])},{f(bottom[0][1])}"] + [f"L {f(x)},{f(y)}" for x, y in bottom[1:]]
    )
    fill_path = " ".join(
        [f"M {f(top[0][0])},{f(top[0][1])}"]
        + [f"L {f(x)},{f(y)}" for x, y in top[1:]]
        + [f"L {f(x)},{f(y)}" for x, y in reversed(bottom)]
        + ["Z"]
    )
    return top_path, bottom_path, fill_path


def burst_peak_markers() -> str:
    active_start = 0.10
    active_end = 0.90
    count = 24
    span = active_end - active_start
    period = span / (count - 1)
    parts: list[str] = []
    for index in range(count):
        t = active_start + period * index
        env = 0.15 + 0.80 * (index / (count - 1))
        x = x_for_t(t)
        y1 = CENTER_Y - MAX_AMP * env
        y2 = CENTER_Y + MAX_AMP * env
        parts.append(
            f'<line x1="{f(x)}" y1="{f(y1)}" x2="{f(x)}" y2="{f(y2)}" '
            f'stroke="{COLORS["accent"]}" stroke-width="1.1" opacity="0.28"/>'
        )
        parts.append(
            f'<circle cx="{f(x)}" cy="{f(y1)}" r="2.2" fill="{COLORS["accent"]}" opacity="0.86"/>'
        )
    return "\n      ".join(parts)


def grid_lines() -> str:
    parts: list[str] = []
    for index in range(9):
        x = PANEL_X + PANEL_W * index / 8
        width = 1.1 if index in (0, 8) else 0.7
        opacity = 0.82 if index in (0, 8) else 0.52
        parts.append(
            f'<line x1="{f(x)}" y1="{PANEL_Y}" x2="{f(x)}" y2="{PANEL_Y + PANEL_H}" '
            f'stroke="{COLORS["panel_line"]}" stroke-width="{width}" opacity="{opacity}"/>'
        )
    for index in range(5):
        y = PANEL_Y + PANEL_H * index / 4
        width = 1.2 if index == 2 else 0.7
        opacity = 0.92 if index == 2 else 0.46
        parts.append(
            f'<line x1="{PANEL_X}" y1="{f(y)}" x2="{PANEL_X + PANEL_W}" y2="{f(y)}" '
            f'stroke="{COLORS["panel_line"]}" stroke-width="{width}" opacity="{opacity}"/>'
        )
    return "\n      ".join(parts)


def axis_labels() -> str:
    return f"""
    <g font-family="Aptos, Noto Sans, Helvetica Neue, sans-serif" font-size="12" letter-spacing="0.02em">
      <text x="{PANEL_X}" y="{PANEL_Y + PANEL_H + 30}" fill="{COLORS["muted"]}">far / quiet</text>
      <text x="{PANEL_X + PANEL_W}" y="{PANEL_Y + PANEL_H + 30}" text-anchor="end" fill="{COLORS["muted"]}">near / loud</text>
      <line x1="{PANEL_X + 92}" y1="{PANEL_Y + PANEL_H + 25}" x2="{PANEL_X + PANEL_W - 92}" y2="{PANEL_Y + PANEL_H + 25}" stroke="{COLORS["line"]}" stroke-width="1.2"/>
      <path d="M {PANEL_X + PANEL_W - 104},{PANEL_Y + PANEL_H + 19} L {PANEL_X + PANEL_W - 92},{PANEL_Y + PANEL_H + 25} L {PANEL_X + PANEL_W - 104},{PANEL_Y + PANEL_H + 31}" fill="none" stroke="{COLORS["line"]}" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
    </g>
"""


def render_svg(spec: GraphicSpec) -> str:
    prefix = "burst" if spec.mode == "burst" else "linear"
    waveform = waveform_path(spec)
    top_env, bottom_env, env_fill = envelope_paths(spec)
    dash = ' stroke-dasharray="7 7"' if spec.mode == "burst" else ""
    markers = burst_peak_markers() if spec.mode == "burst" else ""
    mode_chip = "30 ms bursts / 95 ms period" if spec.mode == "burst" else "continuous linear ramp"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="{prefix}-title {prefix}-desc">
  <title id="{prefix}-title">{spec.title}</title>
  <desc id="{prefix}-desc">{spec.description}</desc>
  <defs>
    <linearGradient id="{prefix}-wave-fill" x1="{PANEL_X}" y1="{PANEL_Y}" x2="{PANEL_X + PANEL_W}" y2="{PANEL_Y}" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="{COLORS["primary"]}"/>
      <stop offset="1" stop-color="{COLORS["cyan"]}"/>
    </linearGradient>
    <linearGradient id="{prefix}-approach-fill" x1="{PANEL_X}" y1="{PANEL_Y}" x2="{PANEL_X + PANEL_W}" y2="{PANEL_Y + PANEL_H}" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="{COLORS["baseline"]}" stop-opacity="0.16"/>
      <stop offset="1" stop-color="{COLORS["accent"]}" stop-opacity="0.28"/>
    </linearGradient>
    <filter id="{prefix}-soft-shadow" x="-8%" y="-18%" width="116%" height="140%">
      <feDropShadow dx="0" dy="8" stdDeviation="10" flood-color="#071612" flood-opacity="0.18"/>
    </filter>
    <clipPath id="{prefix}-panel-clip">
      <rect x="{PANEL_X}" y="{PANEL_Y}" width="{PANEL_W}" height="{PANEL_H}"/>
    </clipPath>
  </defs>
  <rect width="{WIDTH}" height="{HEIGHT}" fill="{COLORS["background"]}"/>
  <rect x="28" y="24" width="904" height="310" fill="{COLORS["surface"]}" stroke="{COLORS["line"]}" stroke-width="1"/>
  <g font-family="Aptos, Noto Sans, Helvetica Neue, sans-serif">
    <text x="56" y="59" fill="{COLORS["text"]}" font-size="24" font-weight="700" letter-spacing="0">{spec.title}</text>
    <text x="56" y="82" fill="{COLORS["muted"]}" font-size="13" letter-spacing="0.01em">{spec.subtitle}</text>
    <g transform="translate(680 40)">
      <rect x="0" y="0" width="205" height="28" fill="#eef7f3" stroke="#b8d9cf" stroke-width="1"/>
      <circle cx="17" cy="14" r="5" fill="{COLORS["primary"]}"/>
      <text x="31" y="18" fill="{COLORS["primary_hover"]}" font-size="11" font-weight="700" letter-spacing="0.03em">{mode_chip}</text>
    </g>
  </g>
  <g filter="url(#{prefix}-soft-shadow)">
    <rect x="{PANEL_X}" y="{PANEL_Y}" width="{PANEL_W}" height="{PANEL_H}" fill="{COLORS["panel"]}"/>
    <rect x="{PANEL_X}" y="{PANEL_Y}" width="{PANEL_W}" height="{PANEL_H}" fill="{COLORS["panel_soft"]}" opacity="0.46"/>
    <g clip-path="url(#{prefix}-panel-clip)">
      {grid_lines()}
      <path d="{env_fill}" fill="url(#{prefix}-approach-fill)" opacity="0.95"/>
      <path d="{waveform}" fill="url(#{prefix}-wave-fill)" opacity="0.88"/>
      {markers}
      <path d="{top_env}" fill="none" stroke="{COLORS["accent"]}" stroke-width="3.1" stroke-linecap="round" stroke-linejoin="round"{dash}/>
      <path d="{bottom_env}" fill="none" stroke="{COLORS["orange"]}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" opacity="0.74"{dash}/>
    </g>
    <rect x="{PANEL_X}" y="{PANEL_Y}" width="{PANEL_W}" height="{PANEL_H}" fill="none" stroke="#253a2e" stroke-width="1.2"/>
  </g>
  <g font-family="Cascadia Mono, SFMono-Regular, Consolas, monospace" font-size="10" letter-spacing="0.03em">
    <text x="{PANEL_X + 12}" y="{PANEL_Y + 18}" fill="#8aaa9e">{spec.label}</text>
    <text x="{PANEL_X + PANEL_W}" y="{PANEL_Y - 12}" text-anchor="end" fill="{COLORS["muted"]}">PEAK ENVELOPE</text>
  </g>
  {axis_labels()}
  <g font-family="Aptos, Noto Sans, Helvetica Neue, sans-serif" font-size="11" letter-spacing="0.04em">
    <rect x="56" y="314" width="14" height="7" fill="{COLORS["primary"]}"/>
    <text x="78" y="322" fill="{COLORS["muted"]}">noise waveform</text>
    <line x1="198" y1="318" x2="232" y2="318" stroke="{COLORS["accent"]}" stroke-width="3" stroke-linecap="round"{dash}/>
    <text x="242" y="322" fill="{COLORS["muted"]}">rising approach envelope</text>
  </g>
</svg>
"""


def main() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    specs = [
        GraphicSpec(
            filename="looming_burst_train_waveform.svg",
            title="Looming Bursts",
            subtitle="Discrete Gaussian noise bursts with a rising approach envelope.",
            label="Hobeika et al. (2020) burst train",
            mode="burst",
            description=(
                "A stylized Audacity-like waveform for the PPS-kit burst-train source mode: "
                "separate short noise bursts increase in peak amplitude from far and quiet to near and loud."
            ),
        ),
        GraphicSpec(
            filename="looming_smooth_linear_approach_waveform.svg",
            title="Smooth Linear Approach",
            subtitle="Smooth noise with one rising approach envelope.",
            label="Smooth linear approach",
            mode="linear",
            description=(
                "A stylized Audacity-like waveform for the PPS-kit smooth-linear source mode: "
                "uninterrupted noise grows smoothly from far and quiet to near and loud."
            ),
        ),
    ]
    output_dirs = (ASSET_DIR, DASHBOARD_DIR)
    for spec in specs:
        svg = render_svg(spec)
        for output_dir in output_dirs:
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / spec.filename
            path.write_text(svg, encoding="utf-8", newline="\n")
            print(f"Wrote {path}")


if __name__ == "__main__":
    main()
