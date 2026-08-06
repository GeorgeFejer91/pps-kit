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

    @property
    def stacked_segment_zero(self) -> bool:
        return self.width <= 760


CASES = (
    ViewportCase("desktop_1440_light", 1440, 900, "light", True),
    ViewportCase("laptop_1280_light", 1280, 800, "light", True),
    ViewportCase("wide_1920_dark", 1920, 1080, "dark", False),
    ViewportCase("narrow_720_light", 720, 900, "light", False),
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
    parser.add_argument("--base-url", default="", help="Use an existing server instead of starting a local one.")
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
    if metrics.get("mode_icon_center_delta_px", 0) > 1 or metrics.get("mode_switch_center_delta_px", 0) > 1:
        failures.append("profile lock and View/Edit switch are not centered on the sidebar meridian")
    if metrics.get("mode_view_switch_gap_px", 0) < 0 or metrics.get("mode_switch_edit_gap_px", 0) < 0:
        failures.append("View/Edit labels overlap the profile-mode switch")
    if metrics.get("mode_label_center_delta_px", 0) > 1:
        failures.append("View/Edit labels do not share the switch's horizontal centerline")
    if not geometry["primary_label_fits"]:
        failures.append("Start New Custom Design label is clipped")
    if geometry["undersized_targets"]:
        targets = ", ".join(item["selector"] for item in geometry["undersized_targets"][:6])
        failures.append(f"visible interactive targets are below 24x24 CSS px: {targets}")
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


def _page_url(base_url: str, case: ViewportCase) -> str:
    desktop = "&desktop=1" if case.desktop else ""
    return (
        f"{base_url.rstrip('/')}/{COMPILED_PAGE}"
        f"?page=toolkit&forceStaticPreview=1&auditStaticPreview=1{desktop}"
    )


def _geometry_script() -> str:
    return """
    () => {
      const visible = (element) => {
        const style = getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
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
      const interactive = [...document.querySelectorAll('button, input, select, [role="button"], .button-link')]
        .filter((element) => visible(element)
          && !element.matches('.state-only, [aria-hidden="true"], input[type="hidden"], input[type="checkbox"], input[type="radio"]'))
        .map((element) => {
          const value = element.getBoundingClientRect();
          return {
            selector: element.id ? `#${element.id}` : element.className ? `.${String(element.className).trim().replaceAll(' ', '.')}` : element.tagName,
            width: value.width,
            height: value.height,
          };
        });
      const undersizedTargets = interactive.filter((item) => item.width < 24 || item.height < 24);
      const horizontalOverlap = Math.max(0, Math.min(select.right, button.right) - Math.max(select.x, button.x));
      return {
        rects: { panel, picker, card, select, button, headingKicker, panelTitle, modePanel, modeIcon, modeSwitch, modeViewLabel, modeEditLabel },
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
          mode_icon_center_delta_px: Math.abs((modePanel.x + modePanel.width / 2) - (modeIcon.x + modeIcon.width / 2)),
          mode_switch_center_delta_px: Math.abs((modePanel.x + modePanel.width / 2) - (modeSwitch.x + modeSwitch.width / 2)),
          mode_view_switch_gap_px: modeSwitch.x - modeViewLabel.right,
          mode_switch_edit_gap_px: modeEditLabel.x - modeSwitch.right,
          mode_label_center_delta_px: Math.max(
            Math.abs((modeViewLabel.y + modeViewLabel.height / 2) - (modeSwitch.y + modeSwitch.height / 2)),
            Math.abs((modeEditLabel.y + modeEditLabel.height / 2) - (modeSwitch.y + modeSwitch.height / 2)),
          ),
        },
        primary_label_fits: button.width + 1 >= document.querySelector('#start-new-custom-design').scrollWidth,
        undersized_targets: undersizedTargets,
      };
    }
    """


def run_audit(base_url: str, output_dir: Path, review_note: str = "") -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit("Playwright is required. Install the validation extra and run: playwright install chromium") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    screenshots: list[Path] = []
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "compiled_page": COMPILED_PAGE,
        "review_note": review_note,
        "manual_review_required": not bool(review_note.strip()),
        "cases": [],
        "failures": [],
    }

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for case_index, case in enumerate(CASES):
                context = browser.new_context(
                    viewport={"width": case.width, "height": case.height},
                    color_scheme=case.theme,
                    device_scale_factor=1,
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
                page.goto(_page_url(base_url, case), wait_until="domcontentloaded", timeout=30_000)
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
                page.locator("#template-select-combobox").click()
                page.wait_for_selector("#bounded-select-menu:not([hidden])")
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
                failures.extend(f"browser error: {message}" for message in page_errors)

                segment_path = output_dir / f"{case.name}_segment0.png"
                page.locator("#study").screenshot(path=str(segment_path), animations="disabled")
                screenshots.append(segment_path)

                viewport_path = output_dir / f"{case.name}_viewport.png"
                page.screenshot(path=str(viewport_path), animations="disabled")
                screenshots.append(viewport_path)

                if case_index == 0:
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

                # Capture every workflow stage in every target layout. Geometry
                # gates catch measurable regressions; these images make the
                # necessary human/vision review of hierarchy and rhythm possible.
                for segment_index, step_link in enumerate(page.locator("[data-step-link]").all()):
                    # Exercise the operator's real navigation path instead of
                    # relying only on a test-only DOM scroll command.
                    step_link.click()
                    segment = page.locator(".decision-segment").nth(segment_index)
                    # Normalize only the evidence framing. Hash navigation can
                    # stop at the document boundary or beneath a prior sticky
                    # heading, which obscures the stage in a viewport capture.
                    segment.evaluate("element => window.scrollTo(0, element.offsetTop - 96)")
                    page.wait_for_timeout(150)
                    path = output_dir / f"{case.name}_segment_{segment_index}.png"
                    page.screenshot(path=str(path), animations="disabled")
                    screenshots.append(path)

                mode_interaction: dict[str, Any] = {}
                if case_index == 0:
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
                    open_mode_path = output_dir / "desktop_1440_light_profile_lock_open.png"
                    page.locator("#profile-mode-panel").screenshot(path=str(open_mode_path), animations="disabled")
                    screenshots.append(open_mode_path)
                    page.locator("#edit-mode-button").click()
                    page.wait_for_function("document.querySelector('#profile-mode-panel')?.dataset.lockState === 'closed'")
                    mode_interaction = {
                        "closed": closed_state,
                        "prompt_lock_state": prompt_lock_state,
                        "open": open_state,
                    }
                    if closed_state["lockState"] != "closed" or closed_state["checked"] != "false":
                        failures.append("profile mode does not initialize as locked View")
                    if prompt_lock_state != "closed":
                        failures.append("profile lock opens before the custom-copy naming dialog is completed")
                    if open_state["lockState"] != "open" or open_state["checked"] != "true":
                        failures.append("named custom copy does not unlock Edit mode")
                    if open_state["shackleTransform"] == closed_state["shackleTransform"]:
                        failures.append("profile lock shackle has no distinct open visual state")

                case_record = {
                    "name": case.name,
                    "viewport": {"width": case.width, "height": case.height},
                    "theme": case.theme,
                    "desktop": case.desktop,
                    "geometry": geometry,
                    "screenshots": [str(segment_path), str(viewport_path)],
                    "mode_interaction": mode_interaction,
                    "failures": failures,
                    "passed": not failures,
                }
                report["cases"].append(case_record)
                report["failures"].extend(f"{case.name}: {failure}" for failure in failures)
                context.close()
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
    if args.base_url:
        report = run_audit(args.base_url, args.output_dir, args.review_note)
    else:
        with serve_repository() as base_url:
            report = run_audit(base_url, args.output_dir, args.review_note)
    print(json.dumps({"passed": report["passed"], "failures": report["failures"], "contact_sheet": report["contact_sheet"]}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
