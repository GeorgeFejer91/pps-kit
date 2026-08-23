"""Generate redistributable schematic figures for the BRM manuscript.

The figures are intentionally source-owned diagrams. They do not depend on
private participant data, copyrighted paper figures, local SOFA files, or
generated run artifacts that cannot be redistributed with the manuscript.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OUT_DIR = Path(__file__).resolve().parent
WIDTH = 2400
HEIGHT = 1350
BG = "#fbfbf7"
INK = "#1f2933"
MUTED = "#5b6770"
LINE = "#cad2d8"
BLUE = "#2f6f9f"
GREEN = "#3c8a5f"
TEAL = "#217d83"
AMBER = "#bd7b25"
ROSE = "#b55267"
PURPLE = "#7357a4"
GRAY = "#e8edf0"
PALE_BLUE = "#e7f0f7"
PALE_GREEN = "#e8f3ec"
PALE_AMBER = "#f7eddf"
PALE_ROSE = "#f7e6ea"
PALE_PURPLE = "#eee9f6"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibrib.ttf" if bold else "C:/Windows/Fonts/calibri.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


TITLE = font(54, True)
SUBTITLE = font(30)
H1 = font(34, True)
H2 = font(29, True)
BODY = font(25)
SMALL = font(21)
TINY = font(18)


def canvas(title: str, subtitle: str | None = None) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    draw.text((90, 60), title, fill=INK, font=TITLE)
    if subtitle:
        draw.text((92, 128), subtitle, fill=MUTED, font=SUBTITLE)
    draw.line((90, 185, WIDTH - 90, 185), fill=LINE, width=3)
    return img, draw


def text_size(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.ImageFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=fnt)
    return box[2] - box[0], box[3] - box[1]


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word]).strip()
        if not candidate:
            continue
        width, _ = text_size(draw, candidate, fnt)
        if width <= max_width or not current:
            current.append(word)
        else:
            lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines


def paragraph(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    fnt: ImageFont.ImageFont,
    fill: str,
    width: int,
    line_gap: int = 8,
) -> int:
    x, y = xy
    for line in wrap(draw, text, fnt, width):
        draw.text((x, y), line, fill=fill, font=fnt)
        _, h = text_size(draw, line, fnt)
        y += h + line_gap
    return y


def box(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    title: str,
    body: str,
    fill: str,
    outline: str,
    title_color: str = INK,
    body_color: str = MUTED,
    radius: int = 28,
) -> None:
    x1, y1, x2, y2 = rect
    draw.rounded_rectangle(rect, radius=radius, fill=fill, outline=outline, width=3)
    draw.text((x1 + 26, y1 + 22), title, fill=title_color, font=H2)
    paragraph(draw, (x1 + 26, y1 + 68), body, BODY, body_color, x2 - x1 - 52, line_gap=7)


def capsule(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    text: str,
    fill: str,
    outline: str,
    fnt: ImageFont.ImageFont = SMALL,
) -> None:
    draw.rounded_rectangle(rect, radius=(rect[3] - rect[1]) // 2, fill=fill, outline=outline, width=2)
    w, h = text_size(draw, text, fnt)
    x = rect[0] + (rect[2] - rect[0] - w) // 2
    y = rect[1] + (rect[3] - rect[1] - h) // 2 - 2
    draw.text((x, y), text, fill=INK, font=fnt)


def arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    color: str = "#6b7b86",
    width: int = 6,
) -> None:
    x1, y1 = start
    x2, y2 = end
    draw.line((x1, y1, x2, y2), fill=color, width=width)
    angle = math.atan2(y2 - y1, x2 - x1)
    size = 22
    points = [
        (x2, y2),
        (x2 - size * math.cos(angle - math.pi / 6), y2 - size * math.sin(angle - math.pi / 6)),
        (x2 - size * math.cos(angle + math.pi / 6), y2 - size * math.sin(angle + math.pi / 6)),
    ]
    draw.polygon(points, fill=color)


def save(img: Image.Image, name: str) -> None:
    img.save(OUT_DIR / name, optimize=True)


def figure1() -> None:
    img, draw = canvas(
        "PPS Toolkit workflow",
        "Seven visible design segments turn methodological choices into reusable runner artifacts.",
    )
    segments = [
        ("0 Profile", "study context, citation, editable copy", PALE_BLUE, BLUE),
        ("1 Audio", "source mode, trajectory, loudness policy", PALE_GREEN, GREEN),
        ("2 Sequence", "trial families, jitter, instructions", PALE_AMBER, AMBER),
        ("3 Tactile", "SOA, baseline, catch, channel 3", PALE_ROSE, ROSE),
        ("4 Pool", "repetitions, proportions, duration", PALE_PURPLE, PURPLE),
        ("5 Blocks", "order review, accepted CSVs", PALE_BLUE, BLUE),
        ("6 Handoff", "participant plan, runner package", PALE_GREEN, GREEN),
    ]
    x0 = 90
    y0 = 240
    bw = 292
    bh = 190
    gap = 20
    for i, (title, body, fill, outline) in enumerate(segments):
        x = x0 + i * (bw + gap)
        box(draw, (x, y0, x + bw, y0 + bh), title, body, fill, outline)
        if i < len(segments) - 1:
            arrow(draw, (x + bw, y0 + bh // 2), (x + bw + gap - 4, y0 + bh // 2), width=4)

    artifacts = [
        ("manifest chain", 125, 510, BLUE),
        ("source hashes", 430, 510, GREEN),
        ("sequence timing", 730, 510, AMBER),
        ("target/baseline/catch WAVs", 1025, 510, ROSE),
        ("repetition pool CSV", 1365, 510, PURPLE),
        ("accepted block CSVs", 1670, 510, BLUE),
        ("runner handoff package", 1965, 510, GREEN),
    ]
    for label, x, y, color in artifacts:
        capsule(draw, (x, y, x + 285, y + 60), label, "#ffffff", color)

    box(
        draw,
        (145, 705, 730, 1025),
        "Design archive",
        "Profile snapshot, manifests, source files, hashes, generated trial assets, and accepted block schedules.",
        "#ffffff",
        BLUE,
    )
    box(
        draw,
        (910, 705, 1495, 1025),
        "Native Focus Mode runner",
        "Synchronized playback, responses, LSL markers, optional LabRecorder, audio evidence, loopback route, and top-up.",
        "#ffffff",
        TEAL,
    )
    box(
        draw,
        (1675, 705, 2260, 1025),
        "Output layers",
        "Public 1.Data_min rows plus private 2.Data_max reconstruction evidence, calibration artifacts, and exploratory analyses.",
        "#ffffff",
        GREEN,
    )
    arrow(draw, (730, 865), (910, 865), TEAL)
    arrow(draw, (1495, 865), (1675, 865), TEAL)
    paragraph(
        draw,
        (150, 1110),
        "Boundary: the workflow proves design provenance and materialization. Hardware timing, tactile mechanics, and participant effects require their own validation artifacts.",
        SMALL,
        MUTED,
        WIDTH - 300,
    )
    save(img, "figure1_workflow_segments.png")


def figure2() -> None:
    img, draw = canvas(
        "Design-decision evidence map",
        "The manuscript treats GUI controls as reportable method choices when they alter PPS interpretation.",
    )
    center = (915, 470, 1485, 715)
    box(
        draw,
        center,
        "Visible GUI or runner decision",
        "A displayed choice becomes a manifest field, CSV row, hash, caveat, or saved output rule.",
        "#ffffff",
        INK,
    )
    clusters = [
        ((120, 260, 650, 460), "Profile and provenance", "citation, verification state, editable copy, rights boundary", PALE_BLUE, BLUE),
        ((120, 620, 650, 820), "Source and trajectory", "burst or smooth source, loudness, azimuth, elevation, distance path", PALE_GREEN, GREEN),
        ((120, 980, 650, 1180), "Baseline and catch", "tactile-only, fixed/stationary auditory, auditory-only catch, no baseline", PALE_ROSE, ROSE),
        ((1750, 260, 2280, 460), "Sequence and blocks", "jitter, row families, repetitions, deterministic block review", PALE_AMBER, AMBER),
        ((1750, 620, 2280, 820), "Tactile safeguards", "threshold assay, misses, adaptive nudge, top-up ledger", PALE_PURPLE, PURPLE),
        ((1750, 980, 2280, 1180), "Analysis choices", "raw RT, baseline correction, sigmoid, log-decay, linear, low-N warnings", PALE_BLUE, BLUE),
    ]
    for rect, title, body, fill, outline in clusters:
        box(draw, rect, title, body, fill, outline)
        if rect[0] < center[0]:
            arrow(draw, (rect[2], (rect[1] + rect[3]) // 2), (center[0], (center[1] + center[3]) // 2), outline, 5)
        else:
            arrow(draw, (rect[0], (rect[1] + rect[3]) // 2), (center[2], (center[1] + center[3]) // 2), outline, 5)

    capsule(draw, (680, 900, 1715, 970), "evidence_matrix.csv + gui_control_coverage.csv + profile_family_examples.csv", "#ffffff", TEAL, SMALL)
    paragraph(
        draw,
        (700, 1018),
        "Interpretive rule: the matrix is a source-pointer design audit. It is not a PRISMA review, effect-size meta-analysis, or proof that one PPS design is best.",
        SMALL,
        MUTED,
        980,
    )
    save(img, "figure2_design_decision_map.png")


def draw_wave(draw: ImageDraw.ImageDraw, origin: tuple[int, int], size: tuple[int, int], burst: bool, color: str) -> None:
    x0, y0 = origin
    w, h = size
    draw.rectangle((x0, y0, x0 + w, y0 + h), fill="#ffffff", outline=LINE, width=2)
    mid = y0 + h // 2
    draw.line((x0 + 30, mid, x0 + w - 30, mid), fill="#c7d0d6", width=2)
    points: list[tuple[int, int]] = []
    if burst:
        for b in range(13):
            cx = x0 + 60 + b * (w - 120) / 12
            amp = 18 + b * 4
            for j in range(18):
                t = j / 17
                xx = int(cx - 18 + t * 36)
                yy = int(mid + math.sin(t * math.pi * 5) * amp * math.sin(t * math.pi))
                points.append((xx, yy))
            if len(points) > 1:
                draw.line(points, fill=color, width=4)
            points = []
    else:
        for i in range(360):
            t = i / 359
            amp = 16 + 54 * t
            xx = int(x0 + 35 + t * (w - 70))
            yy = int(mid + math.sin(t * math.pi * 26) * amp)
            points.append((xx, yy))
        draw.line(points, fill=color, width=4)


def figure3() -> None:
    img, draw = canvas(
        "Stimulus and trajectory alternatives",
        "PPS Toolkit keeps waveform, trajectory, and baseline choices separate because studies vary on each dimension.",
    )
    box(draw, (100, 245, 745, 1120), "Auditory source form", "Generated sources can be burst-train or smooth continuous noise; imported clips preserve source identity and hashes.", "#ffffff", BLUE)
    draw_wave(draw, (160, 465), (520, 185), burst=True, color=GREEN)
    draw.text((170, 420), "Burst train", fill=GREEN, font=H2)
    draw_wave(draw, (160, 790), (520, 185), burst=False, color=BLUE)
    draw.text((170, 745), "Smooth linear", fill=BLUE, font=H2)

    box(draw, (875, 245, 1515, 1120), "Trajectory and body frame", "Distance, azimuth, elevation, direction, duration, and hold periods are stored as source metadata.", "#ffffff", GREEN)
    cx, cy = 1195, 780
    draw.ellipse((cx - 70, cy - 70, cx + 70, cy + 70), fill=PALE_GREEN, outline=GREEN, width=4)
    draw.text((cx - 48, cy - 15), "body", fill=INK, font=BODY)
    dirs = [
        ((cx, cy - 330), "front"),
        ((cx, cy + 330), "rear"),
        ((cx - 280, cy), "left"),
        ((cx + 280, cy), "right"),
    ]
    for (x, y), label in dirs:
        draw.line((cx, cy, x, y), fill="#d1d9dd", width=3)
        draw.ellipse((x - 28, y - 28, x + 28, y + 28), fill="#ffffff", outline=GREEN, width=4)
        draw.text((x - 42, y + 38), label, fill=MUTED, font=SMALL)
    arrow(draw, (1465, 990), (1185, 820), AMBER, 7)
    draw.text((1390, 1002), "far", fill=AMBER, font=SMALL)
    draw.text((1190, 860), "near", fill=AMBER, font=SMALL)

    box(draw, (1645, 245, 2300, 1120), "Baseline and catch structure", "The same auditory source can be paired with different control logic, changing the estimand.", "#ffffff", ROSE)
    rows = [
        ("Target", "binaural audio + tactile cue"),
        ("Tactile-only", "cue without auditory source"),
        ("Fixed auditory", "stationary or far-distance sound"),
        ("Auditory catch", "sound without tactile cue"),
        ("No baseline", "raw RT curve only"),
    ]
    y = 500
    colors = [GREEN, PURPLE, AMBER, BLUE, ROSE]
    for i, (name, desc) in enumerate(rows):
        capsule(draw, (1710, y, 1935, y + 60), name, "#ffffff", colors[i], SMALL)
        paragraph(draw, (1965, y + 2), desc, SMALL, MUTED, 260, 6)
        y += 105
    save(img, "figure3_stimulus_alternatives.png")


def figure4() -> None:
    img, draw = canvas(
        "Spatial rendering and output evidence chain",
        "Rendering provenance, software timing, digital output, electrical loopback, and tactile perception are separate claims.",
    )
    steps = [
        ("HRTF/SOFA", "FABIAN or local SOFA metadata; near-field caveats", PALE_BLUE, BLUE),
        ("Renderer", "3DTI-compatible or Python reference path; trajectory samples", PALE_GREEN, GREEN),
        ("WAV package", "channels 1-2 audio, channel 3 tactile, channel 4 mirror", PALE_AMBER, AMBER),
        ("Native route", "audio interface, output levels, route settings", PALE_ROSE, ROSE),
        ("Event mirrors", "event CSV, LSL markers, trigger codes, optional XDF", PALE_PURPLE, PURPLE),
        ("Evidence", "digital audio, optional loopback, tactile calibration", PALE_BLUE, BLUE),
    ]
    x = 95
    y = 320
    bw = 315
    bh = 210
    for i, (title, body, fill, outline) in enumerate(steps):
        box(draw, (x, y, x + bw, y + bh), title, body, fill, outline)
        if i < len(steps) - 1:
            arrow(draw, (x + bw, y + bh // 2), (x + bw + 42, y + bh // 2), outline, 5)
        x += bw + 60

    tiers = [
        ("Software schedule", "planned sample positions, trial starts, tactile onsets, response windows", BLUE),
        ("Digital audio evidence", "mixed buffers and rendered WAV content", GREEN),
        ("Electrical loopback", "analog return path for interface route when patched", AMBER),
        ("Tactile perceptual evidence", "participant threshold assay, hits, misses, top-up rows", ROSE),
    ]
    y = 725
    for label, desc, color in tiers:
        capsule(draw, (165, y, 560, y + 70), label, "#ffffff", color, BODY)
        paragraph(draw, (610, y + 9), desc, BODY, INK, 1380, 7)
        y += 115
    box(
        draw,
        (1630, 760, 2250, 1135),
        "Do not collapse evidence tiers",
        "Loopback does not measure Woojer mechanical onset. HRTF metadata does not prove perceived distance or externalization. Tactile calibration does not prove PPS facilitation.",
        "#ffffff",
        INK,
    )
    save(img, "figure4_evidence_tiers.png")


def figure5() -> None:
    img, draw = canvas(
        "Operator safeguards for tactile delivery",
        "Calibration, miss handling, adaptive nudges, and top-up are logged as safeguards rather than hidden corrections.",
    )
    nodes = [
        ((130, 330, 510, 560), "Threshold assay", "two-down one-up detection threshold; confirmation hits and catch checks", BLUE, PALE_BLUE),
        ((620, 330, 1000, 560), "Task blocks", "standard trials, catches, baselines, participant clicks, response windows", GREEN, PALE_GREEN),
        ((1110, 330, 1490, 560), "Miss counter", "misses remain visible; original trials are not rewritten", AMBER, PALE_AMBER),
        ((1600, 330, 1980, 560), "Adaptive nudge", "+0.01 percentage points after two misses, capped at 0.5 percent", ROSE, PALE_ROSE),
    ]
    for rect, title, body, outline, fill in nodes:
        box(draw, rect, title, body, fill, outline)
    for a, b in [((510, 445), (620, 445)), ((1000, 445), (1110, 445)), ((1490, 445), (1600, 445))]:
        arrow(draw, a, b, TEAL, 6)
    box(
        draw,
        (620, 750, 1000, 985),
        "Top-up ledger",
        "missed tactile trials can be replayed as bounded rescue rows; top-up rows never erase original misses.",
        "#ffffff",
        PURPLE,
    )
    box(
        draw,
        (1110, 750, 1490, 985),
        "Adaptive artifacts",
        "tactile_threshold_adapted events plus summary JSON and adjustment CSV.",
        "#ffffff",
        ROSE,
    )
    box(
        draw,
        (1600, 750, 1980, 985),
        "Analysis review",
        "hit rate, false alarms, misses, top-up, and low-N warnings before PPS interpretation.",
        "#ffffff",
        GREEN,
    )
    arrow(draw, (1300, 560), (820, 750), PURPLE, 6)
    arrow(draw, (1790, 560), (1300, 750), ROSE, 6)
    arrow(draw, (1000, 865), (1110, 865), TEAL, 6)
    arrow(draw, (1490, 865), (1600, 865), TEAL, 6)
    paragraph(
        draw,
        (150, 1110),
        "Boundary: the adaptive rule is an operator safeguard motivated by tactile-threshold and adaptation concerns. It is not presented as a validated psychophysical correction.",
        SMALL,
        MUTED,
        WIDTH - 300,
    )
    save(img, "figure5_tactile_safeguards.png")


def figure6() -> None:
    img, draw = canvas(
        "Exploratory post-run analysis surfaces",
        "The runner presents response quality and model alternatives before any PPS curve is interpreted.",
    )
    panels = [
        ((120, 270, 680, 600), "1 Response", "tactile hits, tactile misses, catch correct no-responses, false alarms, top-up rows", BLUE, PALE_BLUE),
        ((120, 730, 680, 1060), "2 Assumptions", "baseline coverage, baseline proximity slope, audio-tactile by proximity direction", GREEN, PALE_GREEN),
        ((830, 270, 1540, 1060), "3 Model fit", "observed means plus sigmoid, log-decay, and linear summaries with low-N markers", AMBER, PALE_AMBER),
        ((1690, 270, 2260, 1060), "Artifacts", "curve points, model fits, response rows, quality gate, analysis catalog, source CSVs", PURPLE, PALE_PURPLE),
    ]
    for rect, title, body, outline, fill in panels:
        box(draw, rect, title, body, fill, outline)

    # Response bars.
    bar_x, bar_y = 185, 510
    values = [(0.68, GREEN), (0.18, ROSE), (0.11, BLUE), (0.03, AMBER)]
    pos = bar_x
    for frac, color in values:
        w = int(420 * frac)
        draw.rectangle((pos, bar_y, pos + w, bar_y + 42), fill=color)
        pos += w
    draw.rectangle((bar_x, bar_y, bar_x + 420, bar_y + 42), outline=INK, width=2)

    # Assumption lights.
    for y, label, color in [(910, "Baseline", GREEN), (980, "PPS pattern", AMBER)]:
        draw.ellipse((195, y, 245, y + 50), fill=color, outline=INK, width=2)
        draw.text((270, y + 7), label, fill=INK, font=BODY)

    # Model plot.
    plot = (900, 520, 1470, 900)
    draw.rectangle(plot, fill="#ffffff", outline=LINE, width=3)
    x0, y0, x1, y1 = plot
    draw.line((x0 + 50, y1 - 50, x1 - 35, y1 - 50), fill=INK, width=3)
    draw.line((x0 + 50, y0 + 35, x0 + 50, y1 - 50), fill=INK, width=3)
    draw.text((x0 + 215, y1 - 28), "SOA / distance bin", fill=MUTED, font=TINY)
    draw.text((x0 + 8, y0 + 28), "RT", fill=MUTED, font=TINY)
    curves = [
        (BLUE, lambda t: 0.72 - 0.28 / (1 + math.exp(-8 * (t - 0.45)))),
        (GREEN, lambda t: 0.68 - 0.24 * math.log1p(3.2 * t) / math.log1p(3.2)),
        (ROSE, lambda t: 0.70 - 0.22 * t),
    ]
    for color, fn in curves:
        pts = []
        for i in range(160):
            t = i / 159
            xx = x0 + 55 + t * (x1 - x0 - 105)
            yy = y0 + 45 + fn(t) * (y1 - y0 - 110)
            pts.append((int(xx), int(yy)))
        draw.line(pts, fill=color, width=5)
    for t in [0.08, 0.28, 0.52, 0.76, 0.92]:
        yy = y0 + 45 + (0.70 - 0.20 * t + math.sin(8 * t) * 0.03) * (y1 - y0 - 110)
        xx = x0 + 55 + t * (x1 - x0 - 105)
        draw.ellipse((xx - 9, yy - 9, xx + 9, yy + 9), fill=INK)
    capsule(draw, (930, 930, 1090, 982), "sigmoid", "#ffffff", BLUE, TINY)
    capsule(draw, (1120, 930, 1300, 982), "log decay", "#ffffff", GREEN, TINY)
    capsule(draw, (1330, 930, 1470, 982), "linear", "#ffffff", ROSE, TINY)

    artifact_rows = ["analysis catalog", "curve points", "model fits", "responses", "quality gate", "source tables"]
    y = 520
    for row in artifact_rows:
        capsule(draw, (1770, y, 2180, y + 55), row, "#ffffff", PURPLE, SMALL)
        y += 72

    paragraph(
        draw,
        (150, 1150),
        "Boundary: these surfaces are exploratory operator feedback. Confirmatory inference still needs preregistered exclusions, baseline rules, response windows, and model-family decisions.",
        SMALL,
        MUTED,
        WIDTH - 300,
    )
    save(img, "figure6_analysis_surfaces.png")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    figure1()
    figure2()
    figure3()
    figure4()
    figure5()
    figure6()


if __name__ == "__main__":
    main()
