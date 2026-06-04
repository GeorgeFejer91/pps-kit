"""Console entry points for the public PPS toolkit."""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path


def generate(argv: list[str] | None = None) -> int:
    from . import stimulus_generation

    args = stimulus_generation.build_arg_parser().parse_args(argv)
    stimulus_generation.configure_paths(
        root_dir=args.root_dir,
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        breathing_dir=args.breathing_dir,
        use_pregenerated_looming=args.use_pregenerated_looming,
        looming_version=args.looming_version,
        participants=args.participants,
        seed=args.seed,
    )

    print("PPS stimulus generation")
    print(f"  output: {stimulus_generation.OUTPUT_DIR}")
    print(f"  breathing assets: {stimulus_generation.BREATHING_DIR}")
    print(f"  mode: {'pregenerated looming WAVs' if stimulus_generation.USE_PREGENERATED_LOOMING else 'generate looming from HRIR'}")
    print(f"  seed: {stimulus_generation.RANDOM_SEED}")

    missing = stimulus_generation.missing_input_files()
    if args.dry_run:
        if missing:
            print("Missing inputs:")
            for item in missing:
                print(f"  - {item}")
        else:
            print("Dry run passed.")
        return 0
    if missing:
        print("Cannot generate stimuli because required inputs are missing:")
        for item in missing:
            print(f"  - {item}")
        return 2

    stimulus_generation.create_directories()
    stimulus_generation.generate_tactile_stimulus()
    stimulus_generation.generate_all_looming_stimuli()
    stimulus_generation.combine_looming_tactile_stimuli()
    stimulus_generation.generate_breathing_looming_tactile_trials()
    stimulus_generation.generate_baseline_trials()
    stimulus_generation.generate_catch_trials()
    stimulus_generation.generate_master_blocks()
    stimulus_generation.generate_experiment_blocks()
    stimulus_generation.generate_participant_sequences(num_participants=args.participants)
    return 0


def run(argv: list[str] | None = None) -> int:
    from . import runner

    return runner.main(argv)


def decode(argv: list[str] | None = None) -> int:
    from . import decoder

    return decoder.main(argv)


def analyze(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize deidentified PPS sample data.")
    parser.add_argument("--sample", action="store_true", help="Use data/sample/audio_tactile_with_facilitation_preregistered_2p5sd.csv")
    parser.add_argument("--input", type=Path, help="Analysis CSV with facilitation_ms.")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts") / "analysis")
    args = parser.parse_args(argv)

    input_path = args.input
    if args.sample or input_path is None:
        input_path = Path("data") / "sample" / "audio_tactile_with_facilitation_preregistered_2p5sd.csv"
    if not input_path.exists():
        raise SystemExit(f"Analysis input not found: {input_path}")

    rows: list[dict[str, str]] = []
    with input_path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    grouped: dict[tuple[str, str, str], list[float]] = {}
    for row in rows:
        if row.get("trial_type") != "Audio-Tactile":
            continue
        try:
            facilitation = float(row.get("facilitation_ms", ""))
        except ValueError:
            continue
        key = (
            row.get("condition", ""),
            row.get("phase", ""),
            row.get("SOA_ms", ""),
        )
        grouped.setdefault(key, []).append(facilitation)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / "sample_facilitation_summary.csv"
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["condition", "phase", "SOA_ms", "n", "mean_facilitation_ms", "sd_facilitation_ms"],
        )
        writer.writeheader()
        for (condition, phase, soa), values in sorted(grouped.items()):
            writer.writerow(
                {
                    "condition": condition,
                    "phase": phase,
                    "SOA_ms": soa,
                    "n": len(values),
                    "mean_facilitation_ms": f"{statistics.mean(values):.6f}",
                    "sd_facilitation_ms": f"{statistics.stdev(values):.6f}" if len(values) > 1 else "",
                }
            )
    print(f"Wrote {output_path}")
    return 0
