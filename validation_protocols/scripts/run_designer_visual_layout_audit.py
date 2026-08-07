"""Capture and evaluate the PPS Experiment Designer's rendered layout.

The audit combines measurable DOM geometry with screenshots that must still be
reviewed by a human or vision-capable agent. It serves the compiled frontend so
the desktop package and hosted site are exercised from the same assets.
"""

from __future__ import annotations

import argparse
import json
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from PIL import Image, ImageDraw, ImageOps


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "designer_visual_layout_audit"
COMPILED_PAGE = "src/peripersonal_space_toolkit/dashboard/compiled/index.html"
SCHEMA = "pps-designer-visual-layout-audit.v1"


@dataclass(frozen=True)
class ViewportCase:
    name: str
    width: int
    height: int
    theme: str
    desktop: bool
    full_workflow: bool = True

    @property
    def stacked_segment_zero(self) -> bool:
        return self.width <= 760

    @property
    def phone(self) -> bool:
        return self.width <= 760

    @property
    def workflow_segment_indices(self) -> tuple[int, ...]:
        return tuple(range(7)) if self.full_workflow else (5, 6)


CASES = (
    ViewportCase("desktop_1440_light", 1440, 900, "light", True),
    ViewportCase("laptop_1280_light", 1280, 800, "light", True),
    ViewportCase("wide_1920_dark", 1920, 1080, "dark", False),
    ViewportCase("boundary_601_light", 601, 900, "light", False),
    ViewportCase("narrow_720_light", 720, 900, "light", False),
    ViewportCase("phone_390_dark", 390, 844, "dark", False),
    ViewportCase("phone_360_light", 360, 800, "light", False),
    # Breakpoint probes navigate directly to the late, layout-heavy stages.
    # The established cases above retain the complete seven-stage evidence set.
    ViewportCase("phone_320_light", 320, 800, "light", False, False),
    ViewportCase("phone_landscape_568_light", 568, 320, "light", False, False),
    ViewportCase("boundary_600_dark", 600, 900, "dark", False, False),
    ViewportCase("boundary_760_light", 760, 900, "light", False, False),
    ViewportCase("boundary_761_light", 761, 900, "light", False, False),
)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


@contextmanager
def serve_repository() -> Iterator[str]:
    handler = partial(QuietHandler, directory=str(REPO_ROOT))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--base-url", default="", help="Use an existing server instead of starting a local one.")
    source.add_argument(
        "--page-url",
        default="",
        help="Audit an absolute page URL directly, including a production deployment.",
    )
    parser.add_argument(
        "--page-path",
        default=COMPILED_PAGE,
        help="Page path relative to the local or --base-url server.",
    )
    parser.add_argument(
        "--case",
        dest="case_names",
        action="append",
        choices=[case.name for case in CASES],
        help="Audit only the named viewport case. Repeat to select several cases.",
    )
    parser.add_argument("--review-note", default="", help="Record who inspected the generated images and what was checked.")
    return parser


def _round(value: float) -> float:
    return round(float(value), 2)


def assess_geometry(case: ViewportCase, geometry: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    metrics = geometry["metrics"]

    if metrics["horizontal_overflow_px"] > 1:
        failures.append(f"page has {metrics['horizontal_overflow_px']:.2f}px horizontal overflow")
    if metrics["picker_card_left_delta_px"] > 1 or metrics["picker_card_right_delta_px"] > 1:
        failures.append("Segment 0 chooser and information card do not share left/right meridians")
    if metrics["panel_picker_left_delta_px"] > 1 or metrics["panel_picker_right_delta_px"] > 1:
        failures.append("Segment 0 chooser does not align to the panel inner meridians")
    if metrics["heading_panel_left_delta_px"] > 1:
        failures.append("Segment 0 heading and panel content do not share the leading meridian")
    if metrics["select_button_height_delta_px"] > 1:
        failures.append("Segment 0 selector and primary action have different heights")
    if not case.stacked_segment_zero and metrics["select_button_center_delta_px"] > 1:
        failures.append("Segment 0 selector and primary action have different vertical centers")
    if not case.stacked_segment_zero and metrics["select_button_overlap_px"] > 0:
        failures.append("Segment 0 selector and primary action overlap")
    if metrics.get("select_menu_width_delta_px", 0) > 1:
        failures.append("Segment 0 dropdown is not the same width as its selector")
    if metrics.get("select_menu_left_delta_px", 0) > 1:
        failures.append("Segment 0 dropdown is not anchored to its selector")
    if metrics.get("select_menu_viewport_overflow_px", 0) > 1:
        failures.append("Segment 0 dropdown extends beyond the viewport")
    if case.desktop and metrics.get("topbar_visible", 0) > 0:
        failures.append("desktop applet still shows the redundant hosted top bar")
    if not case.desktop and metrics.get("topbar_visible", 0) < 1:
        failures.append("hosted layout is missing its page-navigation top bar")
    if case.phone and metrics.get("mobile_topbar_above_rail", 0) < 1:
        failures.append("mobile page navigation is not above the sidebar")
    if case.phone and metrics.get("mobile_rail_toggles_visible", 1) < 1:
        failures.append("mobile sidebar is missing its compact section and connection disclosures")
    if case.phone and metrics.get("mobile_sections_collapsed", 1) < 1:
        failures.append("mobile section navigation is expanded before the user requests it")
    if case.phone and metrics.get("mobile_companion_collapsed", 1) < 1:
        failures.append("mobile companion controls are expanded before the user requests them")
    if case.phone and metrics.get("mobile_rail_height_px", 0) > 300:
        failures.append("collapsed mobile sidebar is taller than 300 CSS px")
    if case.width == 761 and metrics.get("mobile_rail_toggles_visible", 0) > 0:
        failures.append("mobile sidebar disclosures remain visible above the 760px breakpoint")
    if metrics.get("site_tab_labels_fit", 0) < 1:
        failures.append("page-navigation tab labels are clipped")
    if metrics.get("site_tab_overlap_px", 0) > 0:
        failures.append("page-navigation tabs overlap")
    if not case.phone and (
        metrics.get("mode_icon_center_delta_px", 0) > 1
        or metrics.get("mode_switch_center_delta_px", 0) > 1
    ):
        failures.append("profile lock and View/Edit switch are not centered on the sidebar meridian")
    if metrics.get("mode_view_switch_gap_px", 0) < 0 or metrics.get("mode_switch_edit_gap_px", 0) < 0:
        failures.append("View/Edit labels overlap the profile-mode switch")
    if metrics.get("mode_label_center_delta_px", 0) > 1:
        failures.append("View/Edit labels do not share the switch's horizontal centerline")
    if not geometry["primary_label_fits"]:
        failures.append("Start New Custom Design label is clipped")
    target_floor = 44 if case.phone else 24
    undersized_targets = geometry.get(
        "undersized_phone_targets" if case.phone else "undersized_targets",
        geometry.get("undersized_targets", []),
    )
    if undersized_targets:
        targets = ", ".join(item["selector"] for item in undersized_targets[:6])
        failures.append(
            f"visible interactive targets are below {target_floor}x{target_floor} CSS px: {targets}"
        )
    if case.width <= 760 and metrics.get("resize_handles_visible", 0) > 0:
        failures.append("panel resize handles remain interactive at or below the 760px breakpoint")
    if case.width == 761 and metrics.get("resize_handles_visible", 1) < 1:
        failures.append("panel resize handles do not return above the 760px breakpoint")
    return failures


def assess_mobile_segment(case: ViewportCase, segment_index: int, geometry: dict[str, Any]) -> list[str]:
    """Assess phone-only layout contracts that appear late in the workflow."""
    if not case.phone:
        return []
    failures: list[str] = []
    if geometry.get("footer_count", 0) and geometry.get("static_footer_count", 0) != geometry["footer_count"]:
        failures.append(f"Segment {segment_index} step footer is not in static document flow on phone")
    if geometry.get("local_horizontal_overflow_px", 0) > 1:
        failures.append(
            f"Segment {segment_index} has {geometry['local_horizontal_overflow_px']:.2f}px local horizontal overflow"
        )
    if segment_index in (5, 6):
        if geometry.get("card_table_count", 0) < 1:
            failures.append(f"Segment {segment_index} is missing its readable mobile card table")
        if geometry.get("card_table_unstacked_cells", 0) > 0:
            failures.append(f"Segment {segment_index} mobile table cells are not stacked as labeled card rows")
        if geometry.get("card_table_min_font_px", 12) < 12:
            failures.append(f"Segment {segment_index} mobile table text is smaller than 12 CSS px")
    if segment_index == 5:
        if geometry.get("block_summary_count", 0) < 1:
            failures.append("Segment 5 is missing a visible block summary")
        if geometry.get("block_summary_overflow_px", 0) > 1:
            failures.append(
                f"Segment 5 block summary exceeds its card by {geometry['block_summary_overflow_px']:.2f}px"
            )
    return failures


def _make_contact_sheet(paths: list[Path], destination: Path) -> None:
    cells: list[Image.Image] = []
    for path in paths:
        with Image.open(path).convert("RGB") as source:
            image = source.copy()
        image.thumbnail((420, 250))
        card = Image.new("RGB", (440, 290), "white")
        draw = ImageDraw.Draw(card)
        draw.text((10, 8), path.stem, fill="#202621")
        x = (card.width - image.width) // 2
        card.paste(image, (x, 32))
        cells.append(ImageOps.expand(card, border=1, fill="#bcc7bd"))

    columns = 3
    rows = (len(cells) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * 442, rows * 292), "#eef0eb")
    for index, cell in enumerate(cells):
        sheet.paste(cell, ((index % columns) * 442, (index // columns) * 292))
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination)


def _make_guide_overlay(source_path: Path, destination: Path, geometry: dict[str, Any]) -> None:
    with Image.open(source_path).convert("RGB") as source:
        image = source.copy()
    draw = ImageDraw.Draw(image)
    origin = geometry["rects"]["panel"]
    picker = geometry["rects"]["picker"]
    select = geometry["rects"]["select"]
    button = geometry["rects"]["button"]

    def x(value: float) -> int:
        return round(value - origin["x"])

    def y(value: float) -> int:
        return round(value - origin["y"])

    for value in (picker["x"], picker["right"]):
        draw.line((x(value), 0, x(value), image.height), fill="#d126d9", width=2)
    for rect in (select, button):
        center = y(rect["y"] + rect["height"] / 2)
        draw.line((0, center, image.width, center), fill="#087f8c", width=2)
        draw.rectangle((x(rect["x"]), y(rect["y"]), x(rect["right"]), y(rect["bottom"])), outline="#087f8c", width=2)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination)


def _page_url(
    base_url: str,
    case: ViewportCase,
    *,
    page_url: str = "",
    page_path: str = COMPILED_PAGE,
) -> str:
    target = page_url or urljoin(f"{base_url.rstrip('/')}/", page_path.lstrip("/"))
    parsed = urlsplit(target)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update({"page": "toolkit", "forceStaticPreview": "1", "auditStaticPreview": "1"})
    if case.desktop:
        query["desktop"] = "1"
    else:
        query.pop("desktop", None)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def _geometry_script() -> str:
    return """
    () => {
      const visible = (element) => {
        if (!element) return false;
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== 'none'
          && style.visibility !== 'hidden'
          && Number(style.opacity) > 0.01
          && rect.width > 0
          && rect.height > 0;
      };
      const rect = (selector) => {
        const element = document.querySelector(selector);
        if (!element) throw new Error(`Missing visual-audit selector: ${selector}`);
        const value = element.getBoundingClientRect();
        return {
          x: value.x, y: value.y, width: value.width, height: value.height,
          right: value.right, bottom: value.bottom,
        };
      };
      const panelElement = document.querySelector('#study');
      const panelStyle = getComputedStyle(panelElement);
      const panel = rect('#study');
      const topbar = rect('.topbar');
      const rail = rect('.rail');
      const picker = rect('.segment-zero-picker');
      const card = rect('.profile-inspection-card');
      const select = rect('#template-select');
      const button = rect('#start-new-custom-design');
      const modePanel = rect('#profile-mode-panel');
      const modeIcon = rect('#profile-lock-visual');
      const modeSwitch = rect('#edit-mode-button');
      const modeViewLabel = rect('#profile-view-label');
      const modeEditLabel = rect('#profile-edit-label');
      const headingKicker = rect('[aria-labelledby="study-segment-title"] > .segment-heading .segment-kicker');
      const panelTitle = rect('#study .panel-title');
      const innerLeft = panel.x + parseFloat(panelStyle.borderLeftWidth) + parseFloat(panelStyle.paddingLeft);
      const innerRight = panel.right - parseFloat(panelStyle.borderRightWidth) - parseFloat(panelStyle.paddingRight);
      const interactive = [...document.querySelectorAll(
        'button, input, select, textarea, [role="button"], [role="switch"], [role="combobox"], .button-link, .rail a, .segmented-control label, .inline-toggle, .box-mode-toggle'
      )]
        .filter((element) => visible(element)
          && !element.closest('[hidden], [inert]')
          && getComputedStyle(element).pointerEvents !== 'none'
          && !element.matches(
            '.state-only, .visually-hidden, .bounded-select-native, [aria-hidden="true"], input[type="hidden"], input[type="checkbox"], input[type="radio"], input[type="range"]'
          ))
        .map((element) => {
          const value = element.getBoundingClientRect();
          return {
            selector: element.id ? `#${element.id}` : element.className ? `.${String(element.className).trim().replaceAll(' ', '.')}` : element.tagName,
            width: value.width,
            height: value.height,
          };
        });
      const undersizedTargets = interactive.filter((item) => item.width < 24 || item.height < 24);
      const phoneOnlyTargets = [...document.querySelectorAll('summary')]
        .filter((element) => visible(element) && !element.closest('[hidden], [inert]'))
        .map((element) => {
          const value = element.getBoundingClientRect();
          return {
            selector: element.id ? `#${element.id}` : 'SUMMARY',
            width: value.width,
            height: value.height,
          };
        });
      const undersizedPhoneTargets = [...interactive, ...phoneOnlyTargets]
        .filter((item) => item.width < 44 || item.height < 44);
      const horizontalOverlap = Math.max(0, Math.min(select.right, button.right) - Math.max(select.x, button.x));
      const siteTabs = [...document.querySelectorAll('.site-tab')];
      const siteTabRects = siteTabs.map((element) => element.getBoundingClientRect());
      const siteTabOverlapPx = siteTabRects.reduce((maximum, current, index) => {
        const overlaps = siteTabRects.slice(index + 1).map((other) => {
          const width = Math.max(0, Math.min(current.right, other.right) - Math.max(current.left, other.left));
          const height = Math.max(0, Math.min(current.bottom, other.bottom) - Math.max(current.top, other.top));
          return width * height;
        });
        return Math.max(maximum, ...overlaps, 0);
      }, 0);
      const mobileSectionToggle = document.querySelector('#mobile-rail-nav-toggle');
      const mobileCompanionToggle = document.querySelector('#mobile-companion-toggle');
      const activeRailNav = document.querySelector('.rail-nav-group.active');
      const companionPanel = document.querySelector('#companion-panel');
      const resizeHandles = [...document.querySelectorAll('.panel-resize-handle')];
      return {
        rects: { panel, picker, card, select, button, headingKicker, panelTitle, modePanel, modeIcon, modeSwitch, modeViewLabel, modeEditLabel, topbar, rail },
        metrics: {
          horizontal_overflow_px: Math.max(0, document.documentElement.scrollWidth - window.innerWidth),
          picker_card_left_delta_px: Math.abs(picker.x - card.x),
          picker_card_right_delta_px: Math.abs(picker.right - card.right),
          panel_picker_left_delta_px: Math.abs(innerLeft - picker.x),
          panel_picker_right_delta_px: Math.abs(innerRight - picker.right),
          heading_panel_left_delta_px: Math.abs(headingKicker.x - panelTitle.x),
          select_button_height_delta_px: Math.abs(select.height - button.height),
          select_button_center_delta_px: Math.abs((select.y + select.height / 2) - (button.y + button.height / 2)),
          select_button_overlap_px: horizontalOverlap,
          topbar_visible: visible(document.querySelector('.topbar')),
          mobile_topbar_above_rail: topbar.bottom <= rail.y + 1,
          site_tab_labels_fit: siteTabs.every((element) => element.clientWidth + 1 >= element.scrollWidth),
          site_tab_overlap_px: siteTabOverlapPx,
          mode_icon_center_delta_px: Math.abs((modePanel.x + modePanel.width / 2) - (modeIcon.x + modeIcon.width / 2)),
          mode_switch_center_delta_px: Math.abs((modePanel.x + modePanel.width / 2) - (modeSwitch.x + modeSwitch.width / 2)),
          mode_view_switch_gap_px: modeSwitch.x - modeViewLabel.right,
          mode_switch_edit_gap_px: modeEditLabel.x - modeSwitch.right,
          mode_label_center_delta_px: Math.max(
            Math.abs((modeViewLabel.y + modeViewLabel.height / 2) - (modeSwitch.y + modeSwitch.height / 2)),
            Math.abs((modeEditLabel.y + modeEditLabel.height / 2) - (modeSwitch.y + modeSwitch.height / 2)),
          ),
          mobile_rail_toggles_visible: visible(mobileSectionToggle) && visible(mobileCompanionToggle),
          mobile_sections_collapsed: !visible(activeRailNav) && mobileSectionToggle?.getAttribute('aria-expanded') === 'false',
          mobile_companion_collapsed: !visible(companionPanel) && mobileCompanionToggle?.getAttribute('aria-expanded') === 'false',
          mobile_rail_height_px: rail.height,
          resize_handles_visible: resizeHandles.filter(visible).length,
        },
        primary_label_fits: button.width + 1 >= document.querySelector('#start-new-custom-design').scrollWidth,
        undersized_targets: undersizedTargets,
        undersized_phone_targets: undersizedPhoneTargets,
      };
    }
    """


def _mobile_segment_geometry_script() -> str:
    return """
    segment => {
      const visible = (element) => {
        if (!element) return false;
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
      };
      const footers = [...segment.querySelectorAll('.step-footer')].filter(visible);
      const overflowElements = [
        segment,
        ...[...segment.querySelectorAll('.scroll-table, .mobile-card-table')].filter(visible),
      ];
      const localOverflow = overflowElements.reduce(
        (maximum, element) => Math.max(maximum, element.scrollWidth - element.clientWidth),
        0,
      );
      const cardTables = [...segment.querySelectorAll('.mobile-card-table')].filter(visible);
      const cardCells = cardTables.flatMap((table) => [...table.querySelectorAll('tbody td')].filter(visible));
      const summaries = [...segment.querySelectorAll('.block-preview-card > summary')].filter(visible);
      const summaryOverflow = summaries.reduce((maximum, summary) => {
        const bounds = summary.getBoundingClientRect();
        const descendantOverflow = [...summary.querySelectorAll('*')].filter(visible).reduce((childMaximum, child) => {
          const childBounds = child.getBoundingClientRect();
          return Math.max(
            childMaximum,
            childBounds.right - bounds.right,
            bounds.left - childBounds.left,
          );
        }, 0);
        return Math.max(maximum, summary.scrollWidth - summary.clientWidth, descendantOverflow);
      }, 0);
      return {
        footer_count: footers.length,
        static_footer_count: footers.filter((footer) => getComputedStyle(footer).position === 'static').length,
        local_horizontal_overflow_px: Math.max(0, localOverflow),
        card_table_count: cardTables.length,
        card_table_unstacked_cells: cardCells.filter((cell) => !['block', 'grid'].includes(getComputedStyle(cell).display)).length,
        card_table_min_font_px: cardCells.length
          ? Math.min(...cardCells.map((cell) => parseFloat(getComputedStyle(cell).fontSize)))
          : 12,
        block_summary_count: summaries.length,
        block_summary_overflow_px: Math.max(0, summaryOverflow),
      };
    }
    """


def _phone_target_script() -> str:
    return """
    () => [...document.querySelectorAll(
      'button, input, select, textarea, summary, [role="button"], [role="switch"], [role="combobox"], .button-link, .rail a'
    )].filter((element) => {
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.display !== 'none'
        && style.visibility !== 'hidden'
        && Number(style.opacity) > 0.01
        && style.pointerEvents !== 'none'
        && rect.width > 0
        && rect.height > 0
        && !element.closest('[hidden], [inert]')
        && !element.matches(
          '.state-only, .visually-hidden, .bounded-select-native, [aria-hidden="true"], input[type="hidden"], input[type="checkbox"], input[type="radio"], input[type="range"]'
        );
    }).map((element) => {
      const rect = element.getBoundingClientRect();
      return {
        selector: element.id ? `#${element.id}` : element.tagName === 'SUMMARY' ? 'SUMMARY' : element.className ? `.${String(element.className).trim().replaceAll(' ', '.')}` : element.tagName,
        width: rect.width,
        height: rect.height,
      };
    }).filter((item) => item.width < 44 || item.height < 44)
    """


def run_audit(
    base_url: str,
    output_dir: Path,
    review_note: str = "",
    *,
    page_url: str = "",
    page_path: str = COMPILED_PAGE,
    cases: tuple[ViewportCase, ...] = CASES,
) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit("Playwright is required. Install the validation extra and run: playwright install chromium") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    screenshots: list[Path] = []
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "compiled_page": COMPILED_PAGE,
        "audited_page": page_url or urljoin(f"{base_url.rstrip('/')}/", page_path.lstrip("/")),
        "review_note": review_note,
        "manual_review_required": not bool(review_note.strip()),
        "cases": [],
        "failures": [],
    }

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for case_index, case in enumerate(cases):
                print(f"[visual-audit] {case.name}", flush=True)
                context = browser.new_context(
                    viewport={"width": case.width, "height": case.height},
                    color_scheme=case.theme,
                    device_scale_factor=1,
                    has_touch=case.phone,
                )
                context.add_init_script(
                    f"localStorage.setItem('ppsDesigner.theme', {json.dumps(case.theme)});"
                )
                page = context.new_page()
                page_errors: list[str] = []
                page.on("pageerror", lambda error, bucket=page_errors: bucket.append(str(error)))
                page.on(
                    "console",
                    lambda message, bucket=page_errors: bucket.append(message.text)
                    if message.type == "error"
                    # Chromium may emit this environment-level policy message
                    # even though PPS does not request or reference the API.
                    and not message.text.startswith("Permissions policy violation: compute-pressure")
                    else None,
                )
                page.goto(
                    _page_url(base_url, case, page_url=page_url, page_path=page_path),
                    wait_until="domcontentloaded",
                    timeout=30_000,
                )
                page.wait_for_selector("#template-select option", state="attached", timeout=20_000)
                page.wait_for_function("document.querySelector('#profile-inspection-id')?.textContent !== '—'")
                page.add_style_tag(
                    content=(
                        "html{scroll-behavior:auto!important}"
                        "*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}"
                    )
                )
                page.wait_for_timeout(500)

                geometry = page.evaluate(_geometry_script())
                profile_trigger = page.locator("#template-select-combobox")
                profile_trigger.scroll_into_view_if_needed()
                profile_trigger.click()
                page.wait_for_function(
                    "document.querySelector('#bounded-select-menu')?.hidden === false"
                )
                menu_geometry = page.evaluate(
                    """
                    () => {
                      const trigger = document.querySelector('#template-select-combobox').getBoundingClientRect();
                      const menu = document.querySelector('#bounded-select-menu').getBoundingClientRect();
                      return {
                        select_menu_width_delta_px: Math.abs(trigger.width - menu.width),
                        select_menu_left_delta_px: Math.abs(trigger.left - menu.left),
                        select_menu_viewport_overflow_px: Math.max(0, menu.right - window.innerWidth, -menu.left),
                      };
                    }
                    """
                )
                geometry["metrics"].update(menu_geometry)
                dropdown_path = output_dir / f"{case.name}_segment0_dropdown.png"
                page.screenshot(path=str(dropdown_path), animations="disabled")
                screenshots.append(dropdown_path)
                page.keyboard.press("Escape")
                page.wait_for_selector("#bounded-select-menu", state="hidden")
                geometry["metrics"] = {key: _round(value) for key, value in geometry["metrics"].items()}
                failures = assess_geometry(case, geometry)
                initial_readonly_mode = page.locator("body").evaluate(
                    "body => body.classList.contains('profile-readonly-mode')"
                )
                readonly_badge_state = page.locator("[data-step-badge]").evaluate_all(
                    """badges => ({
                      total: badges.length,
                      hidden: badges.filter(badge => badge.hidden).length,
                      visible: badges.filter(badge => badge.getClientRects().length > 0).length,
                      nonempty: badges.filter(badge => badge.textContent.trim()).length,
                    })"""
                )
                if not initial_readonly_mode:
                    failures.append("default immutable profile does not initialize in read-only mode")
                if readonly_badge_state != {"total": 7, "hidden": 7, "visible": 0, "nonempty": 0}:
                    failures.append(
                        "read-only workflow repeats the sidebar lock state in visible step badges"
                    )

                theme_path = output_dir / f"{case.name}_theme_toggle.png"
                page.locator("#designer-theme-toggle").screenshot(path=str(theme_path), animations="disabled")
                screenshots.append(theme_path)
                theme_interaction: dict[str, Any] = {}
                if case.name == "desktop_1440_light":
                    light_theme_state = page.locator("#designer-theme-toggle").evaluate(
                        """toggle => ({
                          theme: document.documentElement.dataset.theme,
                          pressed: toggle.getAttribute('aria-pressed'),
                          indicatorTransform: getComputedStyle(toggle.querySelector('.theme-toggle-indicator')).transform,
                        })"""
                    )
                    page.locator("#designer-theme-toggle").click()
                    page.wait_for_function("document.documentElement.dataset.theme === 'dark'")
                    dark_theme_state = page.locator("#designer-theme-toggle").evaluate(
                        """toggle => ({
                          theme: document.documentElement.dataset.theme,
                          pressed: toggle.getAttribute('aria-pressed'),
                          indicatorTransform: getComputedStyle(toggle.querySelector('.theme-toggle-indicator')).transform,
                        })"""
                    )
                    dark_theme_path = output_dir / "desktop_1440_dark_theme_toggle.png"
                    page.locator("#designer-theme-toggle").screenshot(path=str(dark_theme_path), animations="disabled")
                    screenshots.append(dark_theme_path)
                    page.locator("#designer-theme-toggle").click()
                    page.wait_for_function("document.documentElement.dataset.theme === 'light'")
                    theme_interaction = {"light": light_theme_state, "dark": dark_theme_state}
                    if light_theme_state["pressed"] != "false" or dark_theme_state["pressed"] != "true":
                        failures.append("theme toggle accessible state does not follow light/dark selection")
                    if light_theme_state["indicatorTransform"] == dark_theme_state["indicatorTransform"]:
                        failures.append("theme toggle indicator does not move between sun and moon")

                segment_path = output_dir / f"{case.name}_segment0.png"
                page.locator("#study").screenshot(path=str(segment_path), animations="disabled")
                screenshots.append(segment_path)

                viewport_path = output_dir / f"{case.name}_viewport.png"
                page.screenshot(path=str(viewport_path), animations="disabled")
                screenshots.append(viewport_path)

                phone_target_checks: dict[str, Any] = {}
                mobile_rail_interaction: dict[str, Any] = {}
                if case.phone:
                    section_toggle = page.locator("#mobile-rail-nav-toggle")
                    companion_toggle = page.locator("#mobile-companion-toggle")
                    section_toggle.click()
                    section_open = (
                        section_toggle.get_attribute("aria-expanded") == "true"
                        and page.locator(".rail-nav-group.active").is_visible()
                    )
                    section_path = output_dir / f"{case.name}_mobile_sections_open.png"
                    page.locator(".rail").screenshot(path=str(section_path), animations="disabled")
                    screenshots.append(section_path)
                    section_targets = page.evaluate(_phone_target_script())
                    phone_target_checks["sections_open"] = section_targets
                    if section_targets:
                        labels = ", ".join(item["selector"] for item in section_targets[:6])
                        failures.append(f"mobile expanded section targets are below 44x44 CSS px: {labels}")
                    section_toggle.click()
                    section_closed = (
                        section_toggle.get_attribute("aria-expanded") == "false"
                        and not page.locator(".rail-nav-group.active").is_visible()
                    )
                    companion_toggle.click()
                    companion_open = (
                        companion_toggle.get_attribute("aria-expanded") == "true"
                        and page.locator("#companion-panel").is_visible()
                    )
                    companion_targets = page.evaluate(_phone_target_script())
                    phone_target_checks["companion_open"] = companion_targets
                    if companion_targets:
                        labels = ", ".join(item["selector"] for item in companion_targets[:6])
                        failures.append(f"mobile expanded companion targets are below 44x44 CSS px: {labels}")
                    companion_toggle.click()
                    companion_closed = (
                        companion_toggle.get_attribute("aria-expanded") == "false"
                        and not page.locator("#companion-panel").is_visible()
                    )
                    mobile_rail_interaction = {
                        "section_open": section_open,
                        "section_closed": section_closed,
                        "companion_open": companion_open,
                        "companion_closed": companion_closed,
                    }
                    if not all(mobile_rail_interaction.values()):
                        failures.append("mobile sidebar disclosures do not open and return to their compact state")

                page_tab_interaction: dict[str, Any] = {}
                if case.phone:
                    for page_name in ("documentation", "downloads", "toolkit"):
                        tab = page.locator(f'[data-page-tab="{page_name}"]')
                        tab.click()
                        page.wait_for_function(
                            "page => document.body.dataset.activePage === page",
                            arg=page_name,
                        )
                        selected = tab.get_attribute("aria-selected")
                        panel_visible = page.locator(
                            f'[data-page-panel="{page_name}"]'
                        ).is_visible()
                        page_tab_interaction[page_name] = {
                            "selected": selected,
                            "panel_visible": panel_visible,
                        }
                        page_targets = page.evaluate(_phone_target_script())
                        phone_target_checks[f"page_{page_name}"] = page_targets
                        if page_targets:
                            labels = ", ".join(item["selector"] for item in page_targets[:6])
                            failures.append(f"mobile {page_name} page targets are below 44x44 CSS px: {labels}")
                        tab_path = output_dir / f"{case.name}_tab_{page_name}.png"
                        page.locator(".topbar").screenshot(
                            path=str(tab_path), animations="disabled"
                        )
                        screenshots.append(tab_path)
                        if selected != "true" or not panel_visible:
                            failures.append(
                                f"mobile {page_name} tab does not activate its page"
                            )

                    keyboard_states: list[dict[str, Any]] = []
                    keyboard_steps = (
                        ("toolkit", "ArrowRight", "documentation"),
                        ("documentation", "ArrowRight", "downloads"),
                        ("downloads", "ArrowRight", "toolkit"),
                        ("toolkit", "ArrowLeft", "downloads"),
                        ("downloads", "Home", "toolkit"),
                        ("toolkit", "End", "downloads"),
                        ("downloads", "Home", "toolkit"),
                    )
                    page.locator('[data-page-tab="toolkit"]').focus()
                    for source_page, key, expected_page in keyboard_steps:
                        page.keyboard.press(key)
                        page.wait_for_function(
                            "pageName => document.body.dataset.activePage === pageName",
                            arg=expected_page,
                        )
                        state = page.locator(f'[data-page-tab="{expected_page}"]').evaluate(
                            """tab => ({
                              selected: tab.getAttribute('aria-selected'),
                              tabIndex: tab.tabIndex,
                              focused: document.activeElement === tab,
                              panelVisible: !document.querySelector(`#${tab.getAttribute('aria-controls')}`).hidden,
                            })"""
                        )
                        state.update({"from": source_page, "key": key, "expected": expected_page})
                        keyboard_states.append(state)
                        if (
                            state["selected"] != "true"
                            or state["tabIndex"] != 0
                            or not state["focused"]
                            or not state["panelVisible"]
                        ):
                            failures.append(
                                f"mobile tab keyboard interaction {key} does not activate and focus {expected_page}"
                            )
                    page_tab_interaction["keyboard"] = keyboard_states

                modal_interaction: dict[str, Any] = {}
                if case.name == "desktop_1440_light":
                    locked_mode_path = output_dir / "desktop_1440_light_profile_lock_closed.png"
                    page.locator("#profile-mode-panel").screenshot(path=str(locked_mode_path), animations="disabled")
                    screenshots.append(locked_mode_path)

                    guide_path = output_dir / f"{case.name}_segment0_guides.png"
                    _make_guide_overlay(segment_path, guide_path, geometry)
                    screenshots.append(guide_path)

                    page.locator('[data-segment-info="study"]').click()
                    page.wait_for_selector("#segment-info-modal:not([hidden])")
                    about_path = output_dir / "desktop_1440_light_about.png"
                    page.locator(".segment-info-card").screenshot(path=str(about_path), animations="disabled")
                    screenshots.append(about_path)
                    page.locator("#segment-info-modal-close").click()

                if case.phone:
                    modal_trigger = page.locator('[data-segment-info="study"]')
                    modal_trigger.click()
                    page.wait_for_selector("#segment-info-modal:not([hidden])")
                    page.wait_for_timeout(50)
                    modal_geometry = page.locator("#segment-info-modal .modal-card").evaluate(
                        """dialog => {
                          const bounds = dialog.getBoundingClientRect();
                          const style = getComputedStyle(dialog);
                          const contentOverflows = dialog.scrollHeight > dialog.clientHeight + 1;
                          return {
                            viewport_overflow_px: Math.max(
                              0,
                              -bounds.left,
                              -bounds.top,
                              bounds.right - window.innerWidth,
                              bounds.bottom - window.innerHeight,
                            ),
                            content_clipped: contentOverflows && !['auto', 'scroll'].includes(style.overflowY),
                            environment_inert: Boolean(document.querySelector('.app-shell')?.inert),
                          };
                        }"""
                    )
                    dialog = page.locator("#segment-info-modal [role='dialog']")
                    focusable_count = dialog.evaluate(
                        """element => [...element.querySelectorAll(
                          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
                        )].filter(candidate => !candidate.hidden && candidate.getClientRects().length > 0).length"""
                    )
                    focus_containment = [
                        dialog.evaluate("element => element.contains(document.activeElement)")
                    ]
                    page.keyboard.press("Shift+Tab")
                    focus_containment.append(
                        dialog.evaluate("element => element.contains(document.activeElement)")
                    )
                    for _ in range(focusable_count + 2):
                        page.keyboard.press("Tab")
                        focus_containment.append(
                            dialog.evaluate("element => element.contains(document.activeElement)")
                        )
                    modal_path = output_dir / f"{case.name}_about_modal.png"
                    page.screenshot(path=str(modal_path), animations="disabled")
                    screenshots.append(modal_path)
                    modal_targets = page.evaluate(_phone_target_script())
                    phone_target_checks["about_modal"] = modal_targets
                    if modal_targets:
                        labels = ", ".join(item["selector"] for item in modal_targets[:6])
                        failures.append(f"mobile modal targets are below 44x44 CSS px: {labels}")
                    page.locator("#segment-info-modal-close").click()
                    page.wait_for_selector("#segment-info-modal", state="hidden")
                    returned_focus = modal_trigger.evaluate("element => document.activeElement === element")
                    modal_interaction = {
                        **{
                            key: _round(value)
                            if isinstance(value, (int, float)) and not isinstance(value, bool)
                            else value
                            for key, value in modal_geometry.items()
                        },
                        "focus_contained": all(focus_containment),
                        "returned_focus": returned_focus,
                    }
                    if modal_geometry["viewport_overflow_px"] > 1:
                        failures.append("mobile About dialog extends beyond the visual viewport")
                    if modal_geometry["content_clipped"]:
                        failures.append("mobile About dialog clips content instead of scrolling")
                    if not modal_geometry["environment_inert"]:
                        failures.append("mobile modal leaves the application shell interactive")
                    if not all(focus_containment):
                        failures.append("mobile modal allows keyboard focus to escape its dialog")
                    if not returned_focus:
                        failures.append("mobile modal does not return focus to its About trigger")

                # Established cases retain every workflow stage. Extra one-pixel
                # breakpoint probes focus on Segments 5 and 6, where responsive
                # table and footer regressions have the largest cost.
                workflow_geometry: dict[str, Any] = {}
                for segment_index, step_link in enumerate(page.locator("[data-step-link]").all()):
                    if segment_index not in case.workflow_segment_indices:
                        continue
                    # Exercise the operator's real navigation path instead of
                    # relying only on a test-only DOM scroll command.
                    if case.phone and not step_link.is_visible():
                        page.locator("#mobile-rail-nav-toggle").click()
                        page.wait_for_function(
                            "document.querySelector('#mobile-rail-nav-toggle')?.getAttribute('aria-expanded') === 'true'"
                        )
                    step_link.click()
                    segment = page.locator(".decision-segment").nth(segment_index)
                    page.evaluate(
                        """
                        () => new Promise(resolve => {
                          let previous = window.scrollY;
                          let stableFrames = 0;
                          const started = performance.now();
                          const check = () => {
                            const current = window.scrollY;
                            stableFrames = Math.abs(current - previous) < 0.5 ? stableFrames + 1 : 0;
                            previous = current;
                            if (stableFrames >= 5 || performance.now() - started > 4000) {
                              resolve(true);
                              return;
                            }
                            requestAnimationFrame(check);
                          };
                          requestAnimationFrame(check);
                        })
                        """
                    )
                    sticky_overlap = segment.locator(":scope > .segment-heading").evaluate(
                        """
                        headingElement => {
                          const topbar = document.querySelector('.topbar').getBoundingClientRect();
                          const heading = headingElement.getBoundingClientRect();
                          const width = Math.max(0, Math.min(topbar.right, heading.right) - Math.max(topbar.left, heading.left));
                          const height = Math.max(0, Math.min(topbar.bottom, heading.bottom) - Math.max(topbar.top, heading.top));
                          return width * height;
                        }
                        """
                    )
                    if sticky_overlap > 1:
                        failures.append(
                            f"page navigation overlaps a sticky segment heading after opening Segment {segment_index}"
                        )
                    segment_geometry = segment.evaluate(_mobile_segment_geometry_script())
                    segment_geometry = {
                        key: _round(value) if isinstance(value, (int, float)) else value
                        for key, value in segment_geometry.items()
                    }
                    workflow_geometry[str(segment_index)] = segment_geometry
                    failures.extend(assess_mobile_segment(case, segment_index, segment_geometry))
                    # Normalize only the evidence framing. Hash navigation can
                    # stop at the document boundary or beneath a prior sticky
                    # heading, which obscures the stage in a viewport capture.
                    segment.evaluate(
                        """
                        element => {
                          const topbar = document.querySelector('.topbar');
                          const stickyTopbarHeight = topbar && getComputedStyle(topbar).position === 'sticky'
                            ? topbar.getBoundingClientRect().height
                            : 0;
                          window.scrollTo(0, element.offsetTop - stickyTopbarHeight - 8);
                        }
                        """
                    )
                    page.wait_for_timeout(150)
                    path = output_dir / f"{case.name}_segment_{segment_index}.png"
                    page.screenshot(path=str(path), animations="disabled")
                    screenshots.append(path)

                mode_interaction: dict[str, Any] = {}
                if case.name == "desktop_1440_light":
                    closed_state = page.locator("#profile-mode-panel").evaluate(
                        """panel => ({
                          lockState: panel.dataset.lockState,
                          checked: panel.querySelector('#edit-mode-button').getAttribute('aria-checked'),
                          shackleTransform: getComputedStyle(panel.querySelector('.profile-lock-shackle')).transform,
                        })"""
                    )
                    page.locator("#edit-mode-button").click()
                    page.wait_for_selector("#customize-modal:not([hidden])")
                    prompt_lock_state = page.locator("#profile-mode-panel").get_attribute("data-lock-state")
                    prompt_path = output_dir / "desktop_1440_light_profile_copy_prompt.png"
                    page.locator("#customize-modal .modal-card").screenshot(path=str(prompt_path), animations="disabled")
                    screenshots.append(prompt_path)
                    page.locator("#customize-study-name").fill("Visual audit custom profile")
                    page.locator("#customize-submit").click()
                    page.wait_for_selector("#customize-modal", state="hidden")
                    page.wait_for_function("document.querySelector('#profile-mode-panel')?.dataset.lockState === 'open'")
                    open_state = page.locator("#profile-mode-panel").evaluate(
                        """panel => ({
                          lockState: panel.dataset.lockState,
                          checked: panel.querySelector('#edit-mode-button').getAttribute('aria-checked'),
                          shackleTransform: getComputedStyle(panel.querySelector('.profile-lock-shackle')).transform,
                        })"""
                    )
                    editable_badge_state = page.locator("[data-step-badge]").evaluate_all(
                        """badges => ({
                          total: badges.length,
                          hidden: badges.filter(badge => badge.hidden).length,
                          visible: badges.filter(badge => badge.getClientRects().length > 0).length,
                          nonempty: badges.filter(badge => badge.textContent.trim()).length,
                        })"""
                    )
                    open_mode_path = output_dir / "desktop_1440_light_profile_lock_open.png"
                    page.locator("#profile-mode-panel").screenshot(path=str(open_mode_path), animations="disabled")
                    screenshots.append(open_mode_path)
                    editable_badges_path = output_dir / "desktop_1440_light_editable_step_badges.png"
                    page.locator("#study").screenshot(path=str(editable_badges_path), animations="disabled")
                    screenshots.append(editable_badges_path)
                    sequential_before = page.evaluate(
                        """() => {
                          const segments = [...document.querySelectorAll('.decision-segment')];
                          const snapshot = window.PPSDesignerApp.getState();
                          return {
                            edit_step: snapshot.custom_workflow?.edit_step,
                            editing: segments.filter(segment => segment.dataset.workflowState === 'editing').map(segment => segment.id),
                            confirmed: segments.filter(segment => segment.dataset.workflowState === 'confirmed').map(segment => segment.id),
                            downstream: segments.filter(segment => segment.classList.contains('workflow-downstream')).map(segment => segment.id),
                            continue_enabled: (() => {
                              const button = document.querySelector('[data-continue-step="stimulus"]');
                              return Boolean(button && !button.hidden && !button.disabled && button.getClientRects().length);
                            })(),
                            visible_forward_ctas: [...document.querySelectorAll('[data-continue-step], #accept-block-csvs, #save-study-profile')]
                              .filter(button => !button.hidden && button.getClientRects().length > 0).length,
                            visible_step_footers: [...document.querySelectorAll('.step-footer')]
                              .filter(footer => !footer.hidden && footer.getClientRects().length > 0).length,
                            visible_step_footer_controls: [...document.querySelectorAll('.step-footer > *')]
                              .filter(control => !control.hidden && getComputedStyle(control).display !== 'none' && control.getClientRects().length > 0).length,
                            downstream_textarea_disabled: document.querySelector('#baseline-soa-values')?.disabled === true,
                            downstream_textarea_pointer_events: getComputedStyle(document.querySelector('#baseline-soa-values')).pointerEvents,
                            non_active_enabled_controls: [...document.querySelectorAll('[data-step-panel]')]
                              .filter(panel => panel.dataset.stepPanel !== snapshot.custom_workflow?.edit_step)
                              .flatMap(panel => [...panel.querySelectorAll('input, select, textarea, button:not([data-preview-view-control])')])
                              .filter(control => control.id !== 'audio-file-input')
                              .filter(control => !control.disabled)
                              .map(control => control.id || control.name || control.tagName),
                          };
                        }"""
                    )
                    edit_segment_path = output_dir / "desktop_1440_light_sequential_edit_segment_1.png"
                    page.locator("#stimulus-segment").screenshot(path=str(edit_segment_path), animations="disabled")
                    screenshots.append(edit_segment_path)
                    downstream_segment_path = output_dir / "desktop_1440_light_sequential_downstream_segment_2.png"
                    page.locator("#trials-segment").screenshot(path=str(downstream_segment_path), animations="disabled")
                    screenshots.append(downstream_segment_path)
                    page.locator('[data-continue-step="stimulus"]').click()
                    page.wait_for_function(
                        """() => (
                          window.PPSDesignerApp.getState().custom_workflow?.edit_step === 'trials'
                          && document.querySelector('#trials-segment')?.dataset.workflowState === 'editing'
                        )"""
                    )
                    sequential_after = page.evaluate(
                        """() => {
                          const segments = [...document.querySelectorAll('.decision-segment')];
                          const snapshot = window.PPSDesignerApp.getState();
                          return {
                            edit_step: snapshot.custom_workflow?.edit_step,
                            editing: segments.filter(segment => segment.dataset.workflowState === 'editing').map(segment => segment.id),
                            confirmed: segments.filter(segment => segment.dataset.workflowState === 'confirmed').map(segment => segment.id),
                            downstream: segments.filter(segment => segment.classList.contains('workflow-downstream')).map(segment => segment.id),
                            stimulus_reopen_visible: document.querySelector('[data-reopen-step="stimulus"]')?.getClientRects().length > 0,
                            stimulus_reopen_enabled: !document.querySelector('[data-reopen-step="stimulus"]')?.disabled,
                          };
                        }"""
                    )
                    saved_segment_path = output_dir / "desktop_1440_light_sequential_saved_segment_1.png"
                    page.locator("#stimulus-segment").screenshot(path=str(saved_segment_path), animations="disabled")
                    screenshots.append(saved_segment_path)
                    next_segment_path = output_dir / "desktop_1440_light_sequential_active_segment_2.png"
                    page.locator("#trials-segment").screenshot(path=str(next_segment_path), animations="disabled")
                    screenshots.append(next_segment_path)
                    page.once("dialog", lambda dialog: dialog.accept())
                    page.locator('[data-reopen-step="stimulus"]').click()
                    page.wait_for_function(
                        """() => (
                          window.PPSDesignerApp.getState().custom_workflow?.edit_step === 'stimulus'
                          && document.querySelector('#stimulus-segment')?.dataset.workflowState === 'editing'
                        )"""
                    )
                    reopened_state = page.evaluate(
                        """() => {
                          const segments = [...document.querySelectorAll('.decision-segment')];
                          const snapshot = window.PPSDesignerApp.getState();
                          return {
                            edit_step: snapshot.custom_workflow?.edit_step,
                            editing: segments.filter(segment => segment.dataset.workflowState === 'editing').map(segment => segment.id),
                            confirmed: segments.filter(segment => segment.dataset.workflowState === 'confirmed').map(segment => segment.id),
                            downstream: segments.filter(segment => segment.classList.contains('workflow-downstream')).map(segment => segment.id),
                          };
                        }"""
                    )
                    for step_id, next_step in (
                        ("stimulus", "trials"),
                        ("trials", "baseline"),
                        ("baseline", "block"),
                        ("block", "schedule"),
                    ):
                        page.locator(f'[data-continue-step="{step_id}"]').click()
                        page.wait_for_function(
                            """expected => (
                              window.PPSDesignerApp.getState().custom_workflow?.edit_step === expected
                              && document.querySelector(`[data-step-panel="${expected}"]`)
                                ?.closest('.decision-segment')?.dataset.workflowState === 'editing'
                            )""",
                            arg=next_step,
                        )
                    page.locator("#accept-block-csvs").click()
                    page.wait_for_function(
                        """() => {
                          const finalButton = document.querySelector('#save-study-profile');
                          return window.PPSDesignerApp.getState().custom_workflow?.edit_step === 'run'
                            && document.querySelector('#run-segment')?.dataset.workflowState === 'editing'
                            && finalButton
                            && !finalButton.hidden
                            && !finalButton.disabled
                            && finalButton.getClientRects().length > 0;
                        }"""
                    )
                    hosted_full_sequence = page.evaluate(
                        """() => {
                          const snapshot = window.PPSDesignerApp.getState();
                          const progress = snapshot.custom_workflow || {};
                          const finalButton = document.querySelector('#save-study-profile');
                          return {
                            edit_step: progress.edit_step,
                            confirmed_steps: progress.confirmed_steps,
                            needs_review_steps: progress.needs_review_steps,
                            final_action_visible: Boolean(finalButton && !finalButton.hidden && finalButton.getClientRects().length),
                            final_action_enabled: Boolean(finalButton && !finalButton.disabled),
                          };
                        }"""
                    )
                    page.locator("#edit-mode-button").click()
                    page.wait_for_function("document.querySelector('#profile-mode-panel')?.dataset.lockState === 'closed'")
                    overview_state = page.evaluate(
                        """() => {
                          const segments = [...document.querySelectorAll('.decision-segment')];
                          return {
                            visible: segments.filter(segment => segment.getClientRects().length > 0).length,
                            workflow_current: segments.filter(segment => segment.classList.contains('workflow-current')).length,
                            workflow_downstream: segments.filter(segment => segment.classList.contains('workflow-downstream')).length,
                            overview: segments.filter(segment => segment.dataset.workflowState === 'overview').length,
                            muted_panels: [...document.querySelectorAll('[data-step-panel]')].filter(panel => {
                              const style = getComputedStyle(panel);
                              return Number(style.opacity) < 0.99 || style.filter !== 'none';
                            }).length,
                          };
                        }"""
                    )
                    mode_interaction = {
                        "closed": closed_state,
                        "prompt_lock_state": prompt_lock_state,
                        "open": open_state,
                        "readonly_badge_state": readonly_badge_state,
                        "editable_badge_state": editable_badge_state,
                        "sequential_before": sequential_before,
                        "sequential_after": sequential_after,
                        "reopened_state": reopened_state,
                        "hosted_full_sequence": hosted_full_sequence,
                        "overview_state": overview_state,
                    }
                    if closed_state["lockState"] != "closed" or closed_state["checked"] != "false":
                        failures.append("profile mode does not initialize as locked View")
                    if prompt_lock_state != "closed":
                        failures.append("profile lock opens before the custom-copy naming dialog is completed")
                    if open_state["lockState"] != "open" or open_state["checked"] != "true":
                        failures.append("named custom copy does not unlock Edit mode")
                    if open_state["shackleTransform"] == closed_state["shackleTransform"]:
                        failures.append("profile lock shackle has no distinct open visual state")
                    if editable_badge_state != {"total": 7, "hidden": 0, "visible": 7, "nonempty": 7}:
                        failures.append("editable custom workflow loses its step-review badges")
                    if sequential_before != {
                        "edit_step": "stimulus",
                        "editing": ["stimulus-segment"],
                        "confirmed": ["study-segment"],
                        "downstream": ["trials-segment", "baseline-segment", "block-segment", "schedule-segment", "run-segment"],
                        "continue_enabled": True,
                        "visible_forward_ctas": 1,
                        "visible_step_footers": 1,
                        "visible_step_footer_controls": 1,
                        "downstream_textarea_disabled": True,
                        "downstream_textarea_pointer_events": "none",
                        "non_active_enabled_controls": [],
                    }:
                        failures.append("Edit mode does not initialize with exactly Segment 1 editable and downstream segments muted")
                    if sequential_after != {
                        "edit_step": "trials",
                        "editing": ["trials-segment"],
                        "confirmed": ["study-segment", "stimulus-segment"],
                        "downstream": ["baseline-segment", "block-segment", "schedule-segment", "run-segment"],
                        "stimulus_reopen_visible": True,
                        "stimulus_reopen_enabled": True,
                    }:
                        failures.append("Save & Continue does not lock Segment 1 and advance exactly once to Segment 2")
                    if reopened_state != {
                        "edit_step": "stimulus",
                        "editing": ["stimulus-segment"],
                        "confirmed": ["study-segment"],
                        "downstream": ["trials-segment", "baseline-segment", "block-segment", "schedule-segment", "run-segment"],
                    }:
                        failures.append("Reopen segment is not clickable or does not restore the earlier sequential boundary")
                    if hosted_full_sequence != {
                        "edit_step": "run",
                        "confirmed_steps": ["study", "stimulus", "trials", "baseline", "block", "schedule"],
                        "needs_review_steps": [],
                        "final_action_visible": True,
                        "final_action_enabled": True,
                    }:
                        failures.append("Hosted sequential review cannot traverse Segment 1 through Segment 6")
                    if overview_state != {
                        "visible": 7,
                        "workflow_current": 0,
                        "workflow_downstream": 0,
                        "overview": 7,
                        "muted_panels": 0,
                    }:
                        failures.append("View mode does not restore the full unmuted seven-segment overview")

                # Read browser errors only after every tab, disclosure, modal,
                # and workflow interaction so late failures cannot be omitted.
                browser_errors = list(dict.fromkeys(page_errors))
                failures.extend(f"browser error: {message}" for message in browser_errors)
                case_record = {
                    "name": case.name,
                    "viewport": {"width": case.width, "height": case.height},
                    "theme": case.theme,
                    "desktop": case.desktop,
                    "geometry": geometry,
                    "screenshots": [str(segment_path), str(viewport_path)],
                    "theme_interaction": theme_interaction,
                    "page_tab_interaction": page_tab_interaction,
                    "mobile_rail_interaction": mobile_rail_interaction,
                    "phone_target_checks": phone_target_checks,
                    "modal_interaction": modal_interaction,
                    "workflow_geometry": workflow_geometry,
                    "mode_interaction": mode_interaction,
                    "browser_errors": browser_errors,
                    "failures": failures,
                    "passed": not failures,
                }
                report["cases"].append(case_record)
                report["failures"].extend(f"{case.name}: {failure}" for failure in failures)
                context.close()
                # The compiled dashboard can include large lazy documentation
                # assets. Recycle Chromium between viewports so those assets and
                # GPU surfaces cannot accumulate across the full matrix.
                if case_index + 1 < len(cases):
                    browser.close()
                    browser = playwright.chromium.launch(headless=True)
        finally:
            browser.close()

    contact_sheet = output_dir / "designer_visual_contact_sheet.png"
    _make_contact_sheet(screenshots, contact_sheet)
    report["contact_sheet"] = str(contact_sheet)
    report["screenshots"] = [str(path) for path in screenshots]
    report["passed"] = not report["failures"]

    report_path = output_dir / "designer_visual_layout_audit_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    markdown = [
        "# PPS Designer Visual Layout Audit",
        "",
        f"- Geometry result: {'PASS' if report['passed'] else 'FAIL'}",
        f"- Manual review recorded: {'yes' if review_note.strip() else 'no'}",
        f"- Contact sheet: `{contact_sheet}`",
        "",
        "## Cases",
        "",
    ]
    for case in report["cases"]:
        markdown.append(f"- `{case['name']}`: {'PASS' if case['passed'] else 'FAIL'}")
        for failure in case["failures"]:
            markdown.append(f"  - {failure}")
    if review_note.strip():
        markdown.extend(["", "## Review note", "", review_note.strip()])
    (output_dir / "designer_visual_layout_audit_report.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    selected_cases = tuple(
        case for case in CASES
        if not args.case_names or case.name in args.case_names
    )
    if args.page_url:
        report = run_audit(
            "",
            args.output_dir,
            args.review_note,
            page_url=args.page_url,
            page_path=args.page_path,
            cases=selected_cases,
        )
    elif args.base_url:
        report = run_audit(
            args.base_url,
            args.output_dir,
            args.review_note,
            page_path=args.page_path,
            cases=selected_cases,
        )
    else:
        with serve_repository() as base_url:
            report = run_audit(
                base_url,
                args.output_dir,
                args.review_note,
                page_path=args.page_path,
                cases=selected_cases,
            )
    print(json.dumps({"passed": report["passed"], "failures": report["failures"], "contact_sheet": report["contact_sheet"]}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
