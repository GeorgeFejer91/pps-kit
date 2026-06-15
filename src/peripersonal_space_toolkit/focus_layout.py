"""Screen-aware layout profiles for the native Focus Mode runner."""

from __future__ import annotations

from dataclasses import asdict, dataclass


FOCUS_COLORS = {
    "background": "#f4f5f1",
    "surface": "#ffffff",
    "text": "#202621",
    "muted": "#647067",
    "border": "#d9dfd6",
    "border_strong": "#bcc7bd",
    "primary": "#246b55",
    "primary_hover": "#1d5846",
    "primary_soft": "#e9f4ef",
    "danger": "#8c2f2f",
    "danger_soft": "#f8e1df",
    "danger_border": "#e3aca7",
    "input": "#f8f9f6",
    "disabled": "#eef0eb",
    "disabled_text": "#9ba59d",
}


@dataclass(frozen=True)
class FocusLayoutProfile:
    """Concrete geometry and typography choices for a Focus Mode screen size."""

    screen_class: str
    available_width: int
    available_height: int
    window_width: int
    window_height: int
    min_width: int
    min_height: int
    root_margin: int
    root_spacing: int
    panel_margin: int
    panel_spacing: int
    grid_spacing: int
    body_font_pt: float
    muted_font_pt: float
    app_title_font_pt: float
    section_title_font_pt: float
    chip_font_pt: float
    button_min_height: int
    button_padding_y: int
    button_padding_x: int
    input_min_height: int
    input_padding_y: int
    input_padding_x: int
    progress_min_height: int
    target_min_height: int
    target_font_pt: float
    output_min_height: int
    output_max_height: int
    recording_chip_columns: int
    right_stack_mode: str
    compact: bool = False

    def as_dict(self) -> dict[str, int | float | str | bool]:
        return asdict(self)


def render_focus_layout_profile(
    available_width: int,
    available_height: int,
    *,
    target_width: int = 1120,
    target_height: int = 720,
    min_width: int = 820,
    min_height: int = 520,
) -> FocusLayoutProfile:
    """Return a legible runner layout profile for the available screen area."""

    width = max(640, int(available_width or target_width))
    height = max(440, int(available_height or target_height))
    compact = width <= 1180 or height <= 860
    constrained = width <= 980 or height <= 640
    spacious = width >= 1700 and height >= 960

    window_width = min(target_width, max(720, int(width * 0.96)))
    window_height = min(target_height, max(500, int(height * 0.94)))

    if constrained:
        screen_class = "constrained"
    elif compact:
        screen_class = "compact"
    elif spacious:
        screen_class = "spacious"
    else:
        screen_class = "standard"

    return FocusLayoutProfile(
        screen_class=screen_class,
        available_width=width,
        available_height=height,
        window_width=window_width,
        window_height=window_height,
        min_width=min(min_width, window_width),
        min_height=min(min_height, window_height),
        root_margin=8 if compact else 10,
        root_spacing=8 if compact else 10,
        panel_margin=10 if compact else 12,
        panel_spacing=6 if compact else 8,
        grid_spacing=8 if compact else 10,
        body_font_pt=10.5 if constrained else 11.0,
        muted_font_pt=9.2 if constrained else 9.5,
        app_title_font_pt=17.0 if constrained else (18.0 if compact else 20.0),
        section_title_font_pt=11.0 if constrained else 12.0,
        chip_font_pt=8.5 if constrained else 9.0,
        button_min_height=32 if constrained else 34,
        button_padding_y=6 if compact else 7,
        button_padding_x=10 if compact else 13,
        input_min_height=28 if constrained else 30,
        input_padding_y=6 if compact else 7,
        input_padding_x=8 if compact else 9,
        progress_min_height=18 if constrained else 20,
        target_min_height=138 if constrained else (160 if compact else 190),
        target_font_pt=21.0 if constrained else (22.0 if compact else 24.0),
        output_min_height=48 if constrained else (56 if compact else 60),
        output_max_height=72 if constrained else (84 if compact else 90),
        recording_chip_columns=3 if width >= 1080 else 2,
        right_stack_mode="tabs" if constrained or height <= 860 else "resizable",
        compact=compact,
    )


def render_focus_style_sheet(profile: FocusLayoutProfile, *, font_family: str = "Calibri") -> str:
    colors = FOCUS_COLORS
    family = font_family.replace('"', "").strip() or "Calibri"
    return f"""
QWidget {{
    background: {colors["background"]};
    color: {colors["text"]};
    font-family: "{family}";
    font-size: {profile.body_font_pt:g}pt;
}}
QLabel {{
    background: transparent;
}}
QLabel#appTitle {{
    font-size: {profile.app_title_font_pt:g}pt;
    font-weight: 800;
    color: {colors["text"]};
}}
QLabel#sectionTitle {{
    font-size: {profile.section_title_font_pt:g}pt;
    font-weight: 800;
    color: {colors["text"]};
}}
QLabel#sectionSubtitle {{
    color: {colors["text"]};
    font-weight: 800;
    min-height: {max(18, profile.input_min_height - 8)}px;
}}
QLabel#mutedLabel {{
    color: {colors["muted"]};
    font-size: {profile.muted_font_pt:g}pt;
    min-height: {max(16, profile.input_min_height - 10)}px;
}}
QLabel#metricLabel {{
    color: {colors["muted"]};
    font-size: {profile.muted_font_pt:g}pt;
    min-height: {max(16, profile.input_min_height - 10)}px;
}}
QLabel#metricValue {{
    font-weight: 800;
    min-height: {max(16, profile.input_min_height - 10)}px;
}}
QLabel#chip {{
    border: 1px solid {colors["border_strong"]};
    border-radius: 6px;
    padding: 4px 8px;
    background: {colors["surface"]};
    color: {colors["muted"]};
    font-size: {profile.chip_font_pt:g}pt;
    font-weight: 700;
    min-height: {max(18, profile.button_min_height - 14)}px;
}}
QLabel#chip[tone="ok"] {{
    background: {colors["primary_soft"]};
    color: #17634f;
    border-color: #9fd0bd;
}}
QLabel#chip[tone="off"] {{
    background: {colors["danger_soft"]};
    color: #a63831;
    border-color: {colors["danger_border"]};
}}
QFrame#topbar {{
    background: {colors["surface"]};
    border: 1px solid {colors["border"]};
    border-radius: 7px;
}}
QFrame#panel {{
    background: {colors["surface"]};
    border: 1px solid {colors["border"]};
    border-radius: 7px;
}}
QSplitter {{
    background: {colors["background"]};
}}
QSplitter::handle {{
    background: {colors["border"]};
    border: 1px solid {colors["border_strong"]};
    border-radius: 3px;
}}
QSplitter::handle:horizontal {{
    width: 7px;
}}
QSplitter::handle:vertical {{
    height: 7px;
}}
QSplitter::handle:hover {{
    background: {colors["border_strong"]};
}}
QTabWidget::pane {{
    background: transparent;
    border: 0;
    top: -1px;
}}
QTabBar::tab {{
    background: {colors["background"]};
    border: 1px solid {colors["border"]};
    border-bottom-color: {colors["border"]};
    padding: 7px 12px;
    margin-right: 4px;
    font-weight: 700;
}}
QTabBar::tab:selected {{
    background: {colors["surface"]};
    border-bottom-color: {colors["surface"]};
    color: {colors["text"]};
}}
QProgressBar {{
    border: 1px solid {colors["border_strong"]};
    border-radius: 6px;
    background: {colors["input"]};
    min-height: {profile.progress_min_height}px;
    text-align: center;
}}
QProgressBar::chunk {{
    background: {colors["primary"]};
    border-radius: 5px;
}}
QPushButton {{
    min-height: {profile.button_min_height}px;
    border: 1px solid {colors["border_strong"]};
    border-radius: 6px;
    background: {colors["surface"]};
    color: {colors["text"]};
    padding: {profile.button_padding_y}px {profile.button_padding_x}px;
    font-weight: 700;
}}
QPushButton:hover {{
    border-color: #819389;
    background: #f3f6f2;
}}
QPushButton:disabled {{
    color: {colors["disabled_text"]};
    background: {colors["disabled"]};
    border-color: #d7ded5;
}}
QPushButton#primaryButton {{
    background: {colors["primary"]};
    border-color: {colors["primary"]};
    color: {colors["surface"]};
}}
QPushButton#primaryButton:hover {{
    background: {colors["primary_hover"]};
    border-color: {colors["primary_hover"]};
}}
QPushButton#dangerButton {{
    color: {colors["danger"]};
}}
QPushButton#targetButton {{
    min-height: {profile.target_min_height}px;
    background: {colors["input"]};
    border: 2px solid {colors["border_strong"]};
    color: {colors["text"]};
    font-size: {profile.target_font_pt:g}pt;
    font-weight: 900;
}}
QPushButton#targetButton:hover {{
    background: {colors["surface"]};
    border-color: {colors["primary"]};
}}
QPushButton#targetButton:pressed {{
    background: {colors["primary_soft"]};
    border-color: {colors["primary"]};
}}
QTextEdit {{
    background: {colors["input"]};
    border: 1px solid {colors["border"]};
    border-radius: 7px;
    padding: 8px;
    color: {colors["text"]};
}}
QLineEdit {{
    background: {colors["surface"]};
    border: 1px solid {colors["border_strong"]};
    border-radius: 6px;
    padding: {profile.input_padding_y}px {profile.input_padding_x}px;
}}
QComboBox {{
    background: {colors["surface"]};
    border: 1px solid {colors["border_strong"]};
    border-radius: 6px;
    padding: 6px {profile.input_padding_x}px;
    min-height: {profile.input_min_height}px;
}}
QCheckBox {{
    background: transparent;
    spacing: 8px;
    font-weight: 700;
    min-height: {profile.input_min_height}px;
}}
"""


def _hex_to_srgb(value: str) -> tuple[float, float, float]:
    text = value.strip().lstrip("#")
    if len(text) != 6:
        raise ValueError(f"Expected six-digit hex color, got {value!r}")
    return tuple(int(text[index : index + 2], 16) / 255.0 for index in (0, 2, 4))


def _linearize(channel: float) -> float:
    return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    red, green, blue = (_linearize(channel) for channel in _hex_to_srgb(hex_color))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(foreground: str, background: str) -> float:
    light = max(relative_luminance(foreground), relative_luminance(background))
    dark = min(relative_luminance(foreground), relative_luminance(background))
    return (light + 0.05) / (dark + 0.05)


def focus_palette_contrast_report() -> dict[str, float]:
    colors = FOCUS_COLORS
    return {
        "text_on_background": contrast_ratio(colors["text"], colors["background"]),
        "text_on_surface": contrast_ratio(colors["text"], colors["surface"]),
        "muted_on_background": contrast_ratio(colors["muted"], colors["background"]),
        "muted_on_surface": contrast_ratio(colors["muted"], colors["surface"]),
        "primary_button_text": contrast_ratio(colors["surface"], colors["primary"]),
        "danger_text_on_surface": contrast_ratio(colors["danger"], colors["surface"]),
    }
