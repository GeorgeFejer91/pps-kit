"""Generate timed OS mouse clicks for internal PPS response-marker validation."""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path


def _default_output_dir() -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return Path("artifacts") / "validation_runs" / f"emulated_mouse_clicks_{stamp}"


def _sleep_until(target_perf: float) -> None:
    while True:
        remaining = target_perf - time.perf_counter()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.01))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit timed mouse clicks for internal PPS validation.")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--interval-s", type=float, default=0.5)
    parser.add_argument("--start-delay-s", type=float, default=2.0)
    parser.add_argument("--x", type=int, default=None)
    parser.add_argument("--y", type=int, default=None)
    parser.add_argument("--button", choices=["left", "right", "middle"], default="left")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--armed", action="store_true", help="Actually send OS clicks. Without this, only write a dry-run schedule.")
    args = parser.parse_args(argv)

    output_dir = args.output_dir or _default_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "emulated_mouse_clicks.csv"

    controller = None
    button = None
    if args.armed:
        try:
            from pynput.mouse import Button, Controller  # type: ignore
        except Exception as exc:
            print(f"pynput is required to send real mouse clicks: {exc}", file=sys.stderr)
            return 2
        controller = Controller()
        button = {
            "left": Button.left,
            "right": Button.right,
            "middle": Button.middle,
        }[args.button]
        if args.x is not None and args.y is not None:
            controller.position = (args.x, args.y)
    else:
        print("Dry run only. Re-run with --armed to send OS mouse clicks.")

    start_perf = time.perf_counter() + max(0.0, args.start_delay_s)
    rows = []
    for index in range(1, max(0, args.count) + 1):
        scheduled_perf = start_perf + (index - 1) * max(0.0, args.interval_s)
        if args.armed:
            _sleep_until(scheduled_perf)
        before_perf = time.perf_counter()
        before_unix = time.time()
        position = ""
        if controller is not None:
            position = f"{controller.position[0]},{controller.position[1]}"
            controller.click(button)
        after_perf = time.perf_counter()
        rows.append(
            {
                "click_index": index,
                "armed": bool(args.armed),
                "scheduled_perf_counter": f"{scheduled_perf:.9f}",
                "before_click_perf_counter": f"{before_perf:.9f}",
                "after_click_perf_counter": f"{after_perf:.9f}",
                "before_click_unix_time": f"{before_unix:.9f}",
                "dispatch_jitter_ms": f"{(before_perf - scheduled_perf) * 1000.0:.3f}",
                "button": args.button,
                "position": position,
            }
        )
        if not args.armed:
            time.sleep(0.001)

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "click_index",
            "armed",
            "scheduled_perf_counter",
            "before_click_perf_counter",
            "after_click_perf_counter",
            "before_click_unix_time",
            "dispatch_jitter_ms",
            "button",
            "position",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote emulated click schedule/results to {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
