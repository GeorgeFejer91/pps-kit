#!/usr/bin/env python
"""Write the published-study profile recreation audit as LaTeX."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = REPO_ROOT / "assets" / "preloads" / "profile_recreation_status.json"
MATERIALIZATION_PATH = REPO_ROOT / "local_data" / "profile_recreation_batch" / "materialization_summary.json"
REPORT_PATH = REPO_ROOT / "docs" / "audit_report.tex"


def main() -> int:
    parser = argparse.ArgumentParser(description="Write docs/audit_report.tex from the profile recreation ledger.")
    parser.add_argument("--status", type=Path, default=STATUS_PATH, help="profile_recreation_status.json path.")
    parser.add_argument(
        "--materialization",
        type=Path,
        default=MATERIALIZATION_PATH,
        help="local materialization_summary.json path.",
    )
    parser.add_argument("--output", type=Path, default=REPORT_PATH, help="LaTeX report output path.")
    args = parser.parse_args()

    status = _load_json(args.status)
    materialization = _load_json(args.materialization) if args.materialization.exists() else {}
    report = render_audit_report(status, materialization)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


def render_audit_report(status: dict[str, Any], materialization: dict[str, Any]) -> str:
    profiles = list(status.get("profiles") or [])
    materialized = {
        str(item.get("template_id") or ""): dict(item)
        for item in materialization.get("results", [])
        if item.get("template_id")
    }
    gui_ready = [profile for profile in profiles if profile.get("profile_checks_passed") is True]
    published_ready = [profile for profile in gui_ready if _is_published_profile(profile)]
    missing_profiles = [
        profile for profile in profiles if int(profile.get("missing_parameter_count") or 0) > 0
    ]
    structural_profiles = [
        profile for profile in profiles if int(profile.get("unsupported_structure_count") or 0) > 0
    ]

    lines = [
        r"\documentclass[11pt]{article}",
        r"\usepackage[margin=1in]{geometry}",
        r"\usepackage{booktabs}",
        r"\usepackage{longtable}",
        r"\usepackage{array}",
        r"\usepackage{hyperref}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage[utf8]{inputenc}",
        r"\title{Published-Study Audiotactile Task Recreation Audit}",
        r"\author{Peripersonal Space Toolkit}",
        r"\date{2026-06-13}",
        r"\begin{document}",
        r"\emergencystretch=3em",
        r"\sloppy",
        r"\maketitle",
        "",
        r"\section*{Audit Goal}",
        (
            "The goal of this audit is to turn the preload library into an explicit "
            "replication-readiness ledger. A profile passes only when the current Segment "
            "0--4 dashboard/backend schema contains all publication-derived parameters needed "
            "to recreate the audiotactile PPS task profile; later segments are native toolkit "
            "materialization and runner handoff. "
            "Profiles that do not pass remain audit targets, separated into missing "
            "publication parameters and toolkit structural gaps. Clinical populations, "
            "interventions, non-audiotactile stimuli, and extra experimental conditions are "
            "treated as context notes rather than blockers unless they change the "
            "audiotactile PPS task execution itself. No visible GUI progress indicator or "
            "completeness panel is part of this task."
        ),
        "",
        (
            "The structural-gap category is intentionally narrow. It flags only "
            "standardization constraints inside the PPS task itself: trial-family and "
            "baseline logic, auditory stimulus type/provenance/rendering/gain law, "
            "spatial trajectory and apparatus geometry, tactile site/channel/calibration, "
            "response capture, and core timing/repetition parameters. Ordinary "
            "randomization and block order are reproducible runner defaults, not "
            "publication-acceptance blockers. Two-speaker analog setups are treated as "
            "apparatus provenance: when the paper reports enough motion/timing/source "
            "parameters, the toolkit recreates the motion as a binaural spatialized trajectory."
        ),
        "",
        r"\section*{Method}",
        (
            "Every study template was rebuilt into a profile-parameter manifest in "
            r"\texttt{assets/preloads/<template\_id>/}; the canonical file is "
            r"\texttt{01\_profile/profile\_parameters\_manifest.json}. "
            "Each manifest records Segment 0 profile provenance, Segment 1 source assets "
            "and trajectories, Segment 2 trial rows, source sequence, and ITI/jitter boxes, "
            "Segment 3 SOA/tactile/baseline/catch settings, and Segment 4 repetition-pool "
            "settings. Segment 5 block generation and Segment 6 participant/run setup are "
            "native app outputs after the profile gate. Fields are marked as reported, inferred, "
            "defaulted, missing publication parameter, or unsupported toolkit structure."
        ),
        "",
        (
            "The batch materializer then attempted every profile. It prepared Segment 6 "
            "only for profiles whose manifests passed the profile checks and skipped blocked "
            "profiles with an explicit readiness reason. The runner was not launched."
        ),
        "",
        r"\section*{Overall Result}",
        _summary_table(
            [
                ("Catalogued profiles", str(len(profiles))),
                ("Profiles passing checks", str(len(gui_ready))),
                ("Published-paper profiles passing checks", str(len(published_ready))),
                ("Profiles with missing publication parameters", str(len(missing_profiles))),
                ("Profiles with toolkit structural gaps", str(len(structural_profiles))),
                ("Runner launched during audit", "no"),
            ]
        ),
        "",
        _overall_result_text(gui_ready, published_ready),
        "",
        r"\section*{Profiles Successfully Materialized}",
        _ready_table(gui_ready, materialized),
        "",
        r"\section*{Published Profiles Needing Re-Audit Or Toolkit Expansion}",
        _blocked_table([profile for profile in profiles if profile not in gui_ready]),
        "",
        r"\section*{Missing Publication Parameters}",
        _reason_lists(missing_profiles, "missing_publication_parameters"),
        "",
        r"\section*{Toolkit Structural Gaps}",
        _reason_lists(structural_profiles, "unsupported_toolkit_structures"),
        "",
        r"\section*{Interpretation}",
        (
            "A missing-publication finding means the paper or encoded source notes do not "
            "yet provide enough detail to fill a required current-toolkit field honestly. "
            "Examples include exact audio assets, timing or distance tables, tactile "
            "calibration, response-capture details, gain/envelope values, HRTF provenance, "
            "or apparatus-specific switching details."
        ),
        "",
        (
            "A toolkit-structural-gap finding means the study contains an audiotactile PPS "
            "task-execution element that cannot yet be represented as a faithful Segment "
            "0--4 dashboard/backend profile. Examples in this ledger include "
            "separate rear-hemifield trajectory families, unreduced speaker-array "
            "switching, unreduced Gaussian amplitude fields, and renderer behavior "
            "that cannot be reduced to a reported trajectory/timing profile."
        ),
        "",
        r"\section*{Machine-Readable Sources}",
        r"\begin{itemize}",
        r"\item \texttt{assets/preloads/profile\_recreation\_status.json}",
        r"\item \texttt{assets/preloads/<template\_id>/01\_profile/profile\_parameters\_manifest.json}",
        r"\item \texttt{local\_data/profile\_recreation\_batch/materialization\_summary.json}",
        r"\end{itemize}",
        r"\end{document}",
        "",
    ]
    return "\n".join(lines)


def _summary_table(rows: list[tuple[str, str]]) -> str:
    lines = [r"\begin{center}", r"\begin{tabular}{lr}", r"\toprule", r"Measure & Count \\", r"\midrule"]
    for label, value in rows:
        lines.append(f"{_tex(label)} & {_tex(value)} \\\\")
    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{center}"])
    return "\n".join(lines)


def _overall_result_text(gui_ready: list[dict[str, Any]], published_ready: list[dict[str, Any]]) -> str:
    ready_ids = [str(profile.get("template_id") or "") for profile in gui_ready]
    published_ids = [str(profile.get("template_id") or "") for profile in published_ready]
    unpublished_ids = [str(profile.get("template_id") or "") for profile in gui_ready if not _is_published_profile(profile)]
    if published_ids:
        return (
            "The current audit found "
            + _tex(str(len(ready_ids)))
            + " profile(s) that can be materialized end-to-end. "
            + "The unpublished lab profile(s) passing current checks are "
            + ", ".join(_texttt(template_id) for template_id in unpublished_ids)
            + "; the published-paper profile(s) passing current checks are "
            + ", ".join(_texttt(template_id) for template_id in published_ids)
            + "."
        )
    if ready_ids:
        return (
            "The current audit found one profile that can be materialized end-to-end: "
            + _texttt(ready_ids[0])
            + ". This is an unpublished lab profile, not a published-paper profile. Therefore, no currently "
            "catalogued published paper yet passes all exact-recreation profile checks."
        )
    return "No profile currently passes all exact-recreation profile checks."


def _is_published_profile(profile: dict[str, Any]) -> bool:
    return str(profile.get("publication_status") or "published") != "unpublished_lab_profile"


def _ready_table(profiles: list[dict[str, Any]], materialized: dict[str, dict[str, Any]]) -> str:
    if not profiles:
        return "No profiles passed the current profile checks."
    lines = [
        r"{\small",
        r"\begin{longtable}{>{\raggedright\arraybackslash}p{0.35\linewidth}p{0.13\linewidth}p{0.13\linewidth}p{0.13\linewidth}p{0.13\linewidth}}",
        r"\toprule",
        r"Profile & Segment 2 variants & Segment 3 files & Segment 4 rows & Segment 5 blocks \\",
        r"\midrule",
        r"\endhead",
    ]
    for profile in profiles:
        template_id = str(profile.get("template_id") or "")
        result = materialized.get(template_id, {})
        lines.append(
            "{profile} & {s2} & {s3} & {s4} & {s5} \\\\".format(
                profile=_texttt(template_id),
                s2=_tex(str(result.get("segment2_variant_count", "not run"))),
                s3=_tex(str(result.get("segment3_total_count", "not run"))),
                s4=_tex(str(result.get("segment4_total_count", "not run"))),
                s5=_tex(str(result.get("segment5_block_count", "not run"))),
            )
        )
    lines.extend([r"\bottomrule", r"\end{longtable}", r"}"])
    return "\n".join(lines)


def _blocked_table(profiles: list[dict[str, Any]]) -> str:
    if not profiles:
        return "No blocked profiles remain."
    lines = [
        r"{\footnotesize",
        r"\begin{longtable}{>{\raggedright\arraybackslash}p{0.29\linewidth}p{0.15\linewidth}p{0.07\linewidth}p{0.07\linewidth}>{\raggedright\arraybackslash}p{0.31\linewidth}}",
        r"\toprule",
        r"Profile & Primary outcome & Missing & Gaps & Short reason \\",
        r"\midrule",
        r"\endhead",
    ]
    for profile in profiles:
        lines.append(
            "{profile} & {outcome} & {missing} & {gaps} & {reason} \\\\".format(
                profile=_texttt(str(profile.get("template_id") or "")),
                outcome=_tex(str(profile.get("category_label") or profile.get("primary_category") or "")),
                missing=_tex(str(profile.get("missing_parameter_count") or 0)),
                gaps=_tex(str(profile.get("unsupported_structure_count") or 0)),
                reason=_tex(_short_reason(profile)),
            )
        )
    lines.extend([r"\bottomrule", r"\end{longtable}", r"}"])
    return "\n".join(lines)


def _reason_lists(profiles: list[dict[str, Any]], key: str) -> str:
    if not profiles:
        return "No profiles currently fall in this category."
    lines: list[str] = []
    for profile in profiles:
        lines.append(r"\paragraph{" + _texttt(str(profile.get("template_id") or "")) + "}")
        reasons = [str(item.get("reason") or item.get("parameter") or "").strip() for item in profile.get(key, [])]
        reasons = [reason for reason in reasons if reason]
        if not reasons:
            lines.append("No detailed reason was recorded.")
            continue
        lines.append(r"\begin{itemize}")
        for reason in reasons:
            lines.append(r"\item " + _tex(reason))
        lines.append(r"\end{itemize}")
    return "\n".join(lines)


def _short_reason(profile: dict[str, Any]) -> str:
    for key in ("unsupported_toolkit_structures", "missing_publication_parameters"):
        for item in profile.get(key, [])[:1]:
            reason = str(item.get("reason") or item.get("parameter") or "").strip()
            if reason:
                return reason
    return "All current profile checks passed."


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _texttt(value: str) -> str:
    return r"\texttt{" + _tex_code(value) + "}"


def _tex(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in str(value))


def _tex_code(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}\allowbreak{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_\allowbreak{}",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
        "-": r"-\allowbreak{}",
        "/": r"/\allowbreak{}",
    }
    return "".join(replacements.get(char, char) for char in str(value))


if __name__ == "__main__":
    raise SystemExit(main())
