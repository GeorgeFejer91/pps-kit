"""Export a path-free phone study from complete, prepared PPS session parts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages/pps-runtime/src"))

from peripersonal_space_toolkit.session_runner import (  # noqa: E402
    _filesystem_path,
    _trial_is_catch,
    _trial_response_choice_metadata,
    _trial_response_metadata,
    load_run_package,
)
from peripersonal_space_toolkit.timing_schedule import BlockEventSchedule  # noqa: E402


def store_clip(out: Path, pcm: np.ndarray, rate: int, clips: dict) -> str | None:
    if not np.any(pcm):
        return None
    digest = hashlib.sha256(rate.to_bytes(4, "little") + pcm.astype("<i2", copy=False).tobytes()).hexdigest()
    if digest not in clips:
        path = out / "audio" / f"{digest}.flac"
        sf.write(path, pcm, rate, format="FLAC", subtype="PCM_16")
        data = path.read_bytes()
        clips[digest] = {
            "file": f"audio/{path.name}",
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        }
    return digest


def phone_block(block, out: Path, clips: dict, *, lateralization: bool = False) -> dict:
    with sf.SoundFile(_filesystem_path(block.wav_path)) as wav:
        if wav.channels != 3 or wav.subtype != "PCM_16":
            raise ValueError(f"{block.label} requires canonical stereo and tactile PCM16 channels.")
        rate = wav.samplerate
        schedule = BlockEventSchedule.from_block_manifest(
            block.manifest_path, block_index=block.index, block_label=block.label,
            sample_rate=rate, block_metadata=block.metadata,
        )
        by_trial = {}
        for event in schedule.events:
            if event.event_type == "audio_sample_zero":
                continue
            trial_number = event.payload["trial_number"]
            trial = by_trial.setdefault(trial_number, {"row": event.payload, "samples": {}})
            trial["samples"][event.event_type] = event.sample_index
        if len(by_trial) != block.trial_count:
            raise ValueError(f"{block.label} has inconsistent trial counts.")

        trials = []
        previous_end = 0
        for number, trial in sorted(by_trial.items()):
            row, samples = trial["row"], trial["samples"]
            start, end = samples["trial_start"], samples["trial_end"]
            tactile = samples.get("tactile_onset")
            audio = samples.get("looming_onset")
            anchor = tactile if tactile is not None else samples.get("response_window_onset")
            if not previous_end <= start < end <= len(wav) or anchor is None or not start <= anchor <= len(wav):
                raise ValueError(f"{block.label}, trial {number} has an invalid or missing response anchor.")
            choice = _trial_response_choice_metadata(row)
            if any(row.get(key) for key in ("Voice_Key_Response_Label", "Visual_Stimulus_Type", "Speaker_Switch_Sequence")) or (
                not lateralization and (choice["response_choice_set"] or choice["correct_response"])
            ):
                raise ValueError(f"{block.label}, trial {number} requires an additional stimulus or response device.")
            trial_type = str(row.get("Trial_Type") or "")
            family = str(row.get("Family") or "")
            expected = _trial_response_metadata(
                row, trial_type=trial_type, family=family, tactile_present=tactile is not None,
                catch_trial=_trial_is_catch(trial_type, family),
            )
            side_choice = {}
            if lateralization:
                location = f"{block.label}, trial {number}"
                choices = {value.strip().lower() for value in choice["response_choice_set"].split(",")}
                correct_response = choice["correct_response"].lower()
                if not expected["response_required"] or expected["response_rule"] != "choose_external_stimulus_side" or (
                    choices != {"left", "right"} or correct_response not in choices
                ):
                    raise ValueError(f"{location} requires a left/right external-side choice.")
                hand = None
                if tactile is not None:
                    if str(row.get("Tactile_Stimulation_Modality") or "").strip().lower() != "electrical":
                        raise ValueError(f"{location} does not specify electrical tactile stimulation.")
                    hand = str(row.get("Body_Side") or "").strip().lower()
                    if hand not in choices:
                        raise ValueError(f"{location} does not specify the stimulated hand.")
                side_choice = {
                    "tactile_hand": hand,
                    "correct_response": correct_response,
                    "response_scoring_policy": choice["response_scoring_policy"],
                }
            previous_end = end
            wav.seek(start)
            pcm = wav.read(end - start, dtype="int16", always_2d=True)
            if len(pcm) != end - start:
                raise ValueError(f"{block.label}, trial {number} has incomplete PCM data.")
            stereo = pcm[:, :2]
            clip = store_clip(out, stereo, rate, clips)
            if clip and audio is None:
                audio = start + int(np.flatnonzero(np.any(stereo != 0, axis=1))[0])
            duration = None
            if tactile is not None:
                duration = math.ceil(float(row["Tactile_Duration_ms"]))
                if duration <= 0 or duration > 1000 or tactile + round(duration * rate / 1000) > end + 1:
                    raise ValueError(f"{block.label}, trial {number} has an invalid tactile pulse.")
            trials.append({
                "number": number,
                "kind": family or trial_type,
                "start_sample": start,
                "end_sample": end,
                "audio_onset_sample": audio,
                "tactile_onset_sample": tactile,
                "tactile_duration_ms": duration,
                "response_anchor_sample": anchor,
                "response_required": expected["response_required"],
                "clip": clip,
                **side_choice,
            })
        pulses = sorted((trial["tactile_onset_sample"], trial["tactile_duration_ms"])
                        for trial in trials if trial["tactile_onset_sample"] is not None)
        for (start, duration), (next_start, _) in zip(pulses, pulses[1:]):
            if (next_start - start) * 1000 < duration * rate:
                raise ValueError(f"{block.label} has overlapping tactile cue intervals.")
        return {"label": block.label, "sample_rate": rate, "length_samples": len(wav), "trials": trials}


def instruction_slots(package, out: Path, clips: dict) -> list[dict]:
    slots = []
    for slot in package.instruction_profile.get("slots", []):
        if not slot.get("enabled"):
            continue
        clip = None
        if slot.get("path"):
            pcm, rate = sf.read(_filesystem_path(slot["path"]), dtype="int16", always_2d=True)
            if pcm.shape[1] not in (1, 2):
                raise ValueError("Phone instructions require mono or stereo audio.")
            clip = store_clip(out, pcm, rate, clips)
        slots.append({
            "slot": slot["slot"],
            "label": slot["label"],
            "clip": clip,
            "continue_mode": slot["continue_mode"],
            "delay_s": slot["delay_s"],
            "button_label": slot["button_label"],
        })
    return slots


def export_study(template_id: str, manifest: Path, out: Path, *, lateralization: bool = False) -> dict:
    inventory = json.loads((ROOT / "packages/pps-resources/assets/preloads/preload_inventory.json").read_text(encoding="utf-8"))
    profile = next((item for item in inventory["profiles"] if item["template_id"] == template_id), None)
    if not profile or profile["runner_readiness"] != "ready":
        raise ValueError("Select a finished study from the bundled catalogue.")
    package = load_run_package(manifest)
    siblings = [load_run_package(path) for path in package.sibling_part_manifest_paths]
    parts = sorted([package, *siblings], key=lambda part: part.part_number or 1)
    if not all(part.blocks and part.session_group_id == package.session_group_id for part in parts):
        raise ValueError("All prepared parts must belong to the same complete run.")
    for part in parts:
        design = json.loads(Path(_filesystem_path(part.design_path)).read_text(encoding="utf-8-sig"))
        if design.get("study_profile_id") != template_id:
            raise ValueError("Prepared session does not match the requested study.")
    out.mkdir(parents=True, exist_ok=False)
    (out / "audio").mkdir()
    clips = {}
    plan = {
        "schema": "pps-phone-lateralization-schedule.v1" if lateralization else "pps-phone-study.v1",
        "profile_id": template_id,
        "title": profile["title"],
        "timing_tier": "prepared_schedule" if lateralization else "browser_exploratory",
        "parts": [{
            "number": part.part_number or 1,
            "instructions": instruction_slots(part, out, clips),
            "blocks": [phone_block(block, out, clips, lateralization=lateralization) for block in part.blocks],
        } for part in parts],
        "clips": clips,
    }
    if lateralization:
        plan["required_output"] = "independent_electrical_tactile"
        plan["response_choices"] = ["left", "right"]
    (out / "study.json").write_text(json.dumps(plan, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    return plan


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("template_id")
    cli.add_argument("prepared_session", type=Path)
    cli.add_argument("output", type=Path)
    cli.add_argument(
        "--lateralization-schedule", action="store_true",
        help="export stereo and side-choice scheduling for independently controlled electrical tactile output",
    )
    args = cli.parse_args()
    plan = export_study(args.template_id, args.prepared_session, args.output, lateralization=args.lateralization_schedule)
    print(f'{len(plan["parts"])} parts, {len(plan["clips"])} unique audio clips')
