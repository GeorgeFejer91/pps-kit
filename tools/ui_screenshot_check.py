"""Capture and sanity-check PPS designer screenshots.

This script opens the Tkinter stimulus designer, visits each main tab, saves a
screenshot, and writes a small JSON report that supports repeated visual QA.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any

from PIL import Image, ImageGrab, ImageStat


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from peripersonal_space_toolkit.designer_app import DEFAULT_DESIGN_PATH, StimulusDesignerApp


EXPECTED_TABS = ("Stimulus Design", "Trial Design")
IMPORTANT_WIDGET_CLASSES = {
    "TButton",
    "TCheckbutton",
    "TCombobox",
    "TEntry",
    "TLabel",
    "TSpinbox",
    "Treeview",
    "Canvas",
}
REQUIRED_FOOTER_BUTTONS = {
    "Check",
    "Export Trajectory",
    "Export Protocol",
    "Save Settings",
    "Load Settings",
    "Save As",
    "Load File",
}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture visual QA screenshots for the PPS designer UI.")
    parser.add_argument("--design", type=Path, default=DEFAULT_DESIGN_PATH, help="Design JSON to open.")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "artifacts" / "ui_verification")
    parser.add_argument("--iterations", type=int, default=1, help="Repeat the tab screenshot loop.")
    parser.add_argument("--delay", type=float, default=0.35, help="Seconds to wait before each capture.")
    parser.add_argument("--geometry", default="1180x780", help="Tk geometry for the verification window.")
    return parser


def iter_widgets(widget: tk.Misc):
    yield widget
    for child in widget.winfo_children():
        yield from iter_widgets(child)


def find_notebook(root: tk.Misc) -> ttk.Notebook:
    for widget in iter_widgets(root):
        if isinstance(widget, ttk.Notebook):
            return widget
    raise RuntimeError("Could not find the designer notebook.")


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_").lower()


def widget_label(widget: tk.Misc) -> str:
    try:
        return str(widget.cget("text"))
    except tk.TclError:
        return ""


def inspect_widgets(root: tk.Misc) -> dict[str, Any]:
    visible_widgets: list[dict[str, Any]] = []
    tiny_widgets: list[dict[str, Any]] = []
    clipped_widgets: list[dict[str, Any]] = []
    root_width = int(root.winfo_width())
    root_height = int(root.winfo_height())
    for widget in iter_widgets(root):
        if not widget.winfo_ismapped():
            continue
        class_name = widget.winfo_class()
        if class_name not in IMPORTANT_WIDGET_CLASSES:
            continue
        width = int(widget.winfo_width())
        height = int(widget.winfo_height())
        item = {
            "class": class_name,
            "text": widget_label(widget),
            "x": int(widget.winfo_rootx() - root.winfo_rootx()),
            "y": int(widget.winfo_rooty() - root.winfo_rooty()),
            "width": width,
            "height": height,
        }
        visible_widgets.append(item)
        if width < 8 or height < 8:
            tiny_widgets.append(item)
        if item["x"] < 0 or item["y"] < 0 or item["x"] + width > root_width or item["y"] + height > root_height:
            clipped_widgets.append(item)
    return {
        "visible_widget_count": len(visible_widgets),
        "visible_widgets": visible_widgets,
        "tiny_widgets": tiny_widgets,
        "clipped_widgets": clipped_widgets,
    }


def screenshot_window(root: tk.Tk, path: Path) -> dict[str, Any]:
    root.update_idletasks()
    root.update()
    left = root.winfo_rootx()
    top = root.winfo_rooty()
    width = root.winfo_width()
    height = root.winfo_height()
    if width <= 0 or height <= 0:
        raise RuntimeError(f"Invalid window size: {width}x{height}")
    image = ImageGrab.grab(bbox=(left, top, left + width, top + height), all_screens=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return {"width": width, "height": height}


def inspect_image(path: Path) -> dict[str, Any]:
    image = Image.open(path).convert("RGB")
    stat = ImageStat.Stat(image)
    channel_stddev = [float(value) for value in stat.stddev]
    return {
        "path": str(path),
        "width": image.width,
        "height": image.height,
        "mean_rgb": [float(value) for value in stat.mean],
        "stddev_rgb": channel_stddev,
        "min_stddev_rgb": min(channel_stddev),
        "nonblank": min(channel_stddev) > 2.0,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.iterations < 1:
        raise SystemExit("--iterations must be at least 1")

    root = tk.Tk()
    root.geometry(args.geometry)
    root.update_idletasks()
    app = StimulusDesignerApp(root, design_path=args.design)
    root.geometry(args.geometry)
    root.lift()
    root.attributes("-topmost", True)
    root.update()
    root.attributes("-topmost", False)

    report: dict[str, Any] = {
        "design": str(args.design),
        "geometry": args.geometry,
        "screenshots": [],
        "checks": [],
        "failures": [],
    }
    try:
        notebook = find_notebook(root)
        tab_labels = [notebook.tab(tab_id, option="text") for tab_id in notebook.tabs()]
        report["tabs"] = tab_labels
        if tuple(tab_labels) != EXPECTED_TABS:
            report["failures"].append(f"Expected tabs {EXPECTED_TABS}, found {tuple(tab_labels)}")

        for iteration in range(args.iterations):
            for tab_index, tab_label in enumerate(tab_labels):
                notebook.select(tab_index)
                root.update()
                time.sleep(args.delay)
                shot_path = args.output_dir / f"{iteration + 1:02d}_{safe_name(tab_label)}.png"
                window_metrics = screenshot_window(root, shot_path)
                image_metrics = inspect_image(shot_path)
                widget_metrics = inspect_widgets(root)
                item = {
                    "iteration": iteration + 1,
                    "tab": tab_label,
                    "window": window_metrics,
                    "image": image_metrics,
                    "widgets": widget_metrics,
                }
                report["screenshots"].append(item)

                if not image_metrics["nonblank"]:
                    report["failures"].append(f"{tab_label} screenshot appears blank or nearly blank.")
                if window_metrics["width"] < 1000 or window_metrics["height"] < 650:
                    report["failures"].append(f"{tab_label} window is smaller than the usability baseline.")
                if widget_metrics["visible_widget_count"] < 15:
                    report["failures"].append(f"{tab_label} has unexpectedly few visible controls.")
                if widget_metrics["tiny_widgets"]:
                    report["failures"].append(f"{tab_label} has tiny visible widgets.")
                if widget_metrics["clipped_widgets"]:
                    report["failures"].append(f"{tab_label} has visible controls outside the captured window.")
                visible_labels = {item["text"] for item in widget_metrics["visible_widgets"] if item["text"]}
                missing_footer = REQUIRED_FOOTER_BUTTONS - visible_labels
                if missing_footer:
                    report["failures"].append(f"{tab_label} is missing visible footer actions: {sorted(missing_footer)}")

        report["checks"].append("Captured all notebook tabs.")
        report["checks"].append("Checked screenshot size, nonblank image variance, tab names, and visible widget geometry.")
    finally:
        root.destroy()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.output_dir / "ui_screenshot_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {report_path}")
    for item in report["screenshots"]:
        print(f"  {item['tab']}: {item['image']['path']}")
    if report["failures"]:
        print("Failures:")
        for failure in report["failures"]:
            print(f"  - {failure}")
        return 1
    print("UI screenshot checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
