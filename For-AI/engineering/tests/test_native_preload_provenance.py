"""Native premade evidence must survive the ordinary catalogue build."""
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

from peripersonal_space_toolkit.templates import load_templates

ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = "serino_2015_peri_hand_exp3"


@pytest.fixture
def native_catalog(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("native_preload_builder", ROOT / "For-AI/engineering/tooling/build_preload_catalog.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    resources = ROOT / "packages/pps-resources"
    template = next(t for t in load_templates(resources / "study_templates") if t.template_id == TEMPLATE)
    template.design.sofa_file = str(resources / builder.DEFAULT_SOFA_FILE)
    preloads = tmp_path / "assets/preloads"
    source = resources / "assets/preloads" / TEMPLATE / "02_looming_stimuli"
    destination = preloads / TEMPLATE / "02_looming_stimuli"
    destination.mkdir(parents=True)
    for file in source.iterdir():
        if file.suffix == ".wav" or file.name.endswith(".native_generation.json"):
            shutil.copyfile(file, destination / file.name)
    monkeypatch.setattr(builder, "RESOURCE_ROOT", tmp_path)
    monkeypatch.setattr(builder, "PRELOAD_ROOT", preloads)
    return builder, template, preloads / TEMPLATE


def test_catalog_rebuild_preserves_native_audio_and_generation_authority(native_catalog):
    builder, template, folder = native_catalog
    entry, _parameters = builder.build_profile_catalog(template, force=False)
    manifest = json.loads((folder / "preload_manifest.json").read_text(encoding="utf-8"))
    assert manifest["render_contract"]["engine"] == "rust-native-corrected-3dti"
    assert not manifest["render_contract"]["scientific_source_conformance"]
    assert len(entry["assets"]) == 2
    for asset in entry["assets"]:
        assert asset["frames"] == 176400
        assert asset["duration_s"] == 4
        assert asset["source_profile"] == "continuous_noise"
        evidence = json.loads((builder.RESOURCE_ROOT / asset["native_generation_provenance"]).read_text(encoding="utf-8"))
        assert asset["sha256"] == evidence["asset"]["sha256"]
    with pytest.raises(ValueError, match="Rust regeneration workflow"):
        builder.build_profile_catalog(template, force=True)


def test_native_catalog_rejects_changed_audio_or_template(native_catalog):
    builder, template, folder = native_catalog
    template.design.trajectory.propagation_speed_mps = 0.44
    with pytest.raises(ValueError, match="does not match its template"):
        builder.build_profile_catalog(template, force=False)
    template.design.trajectory.propagation_speed_mps = 0.22
    template.design.trajectory.padding_pre_s = 0.1
    with pytest.raises(ValueError, match="does not match its template"):
        builder.build_profile_catalog(template, force=False)
    template.design.trajectory.padding_pre_s = 0
    template.design.trajectory.use_inverse_square = False
    with pytest.raises(ValueError, match="does not match its template"):
        builder.build_profile_catalog(template, force=False)
    template.design.trajectory.use_inverse_square = True
    template.design.trajectory.coordinate_mode = "polar"
    with pytest.raises(ValueError, match="does not match its template"):
        builder.build_profile_catalog(template, force=False)
    template.design.trajectory.coordinate_mode = "cartesian"
    original_sofa = template.design.sofa_file
    template.design.sofa_file = "missing.sofa"
    with pytest.raises(ValueError, match="does not match its template HRTF"):
        builder.build_profile_catalog(template, force=False)
    different_sofa = folder / "different.sofa"
    different_sofa.write_bytes(b"different HRTF bytes")
    template.design.sofa_file = str(different_sofa)
    with pytest.raises(ValueError, match="does not match its template"):
        builder.build_profile_catalog(template, force=False)
    template.design.sofa_file = original_sofa
    wav = folder / "02_looming_stimuli/looming_Hand_moving_sound.wav"
    with wav.open("r+b") as stream:
        stream.seek(-1, 2)
        last = stream.read(1)
        stream.seek(-1, 2)
        stream.write(bytes([last[0] ^ 1]))
    with pytest.raises(ValueError, match="does not match its audio"):
        builder.build_profile_catalog(template, force=False)
