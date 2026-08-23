from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "For-AI" / "engineering" / "tooling" / "generate_noise_mode_svgs.py"
ASSET_DIR = ROOT / "packages" / "pps-resources" / "assets" / "app"
DASHBOARD_DIR = ROOT / "apps" / "designer" / "frontend"
COMPILED_ASSET_DIR = DASHBOARD_DIR / "compiled" / "assets"
SVG_NS = "http://www.w3.org/2000/svg"
NS = {"svg": SVG_NS}
FORBIDDEN_ELEMENTS = {
    "canvas",
    "embed",
    "foreignObject",
    "iframe",
    "image",
    "object",
    "script",
}


def _load_generator():
    spec = importlib.util.spec_from_file_location("generate_noise_mode_svgs", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _local_name(value: str) -> str:
    return value.rsplit("}", 1)[-1]


def _metadata(root: ET.Element) -> dict[str, object]:
    node = root.find("svg:metadata", NS)
    assert node is not None and node.text
    return json.loads(node.text)


def test_pipeline_generates_complete_native_vector_asset_set() -> None:
    generator = _load_generator()
    documents = generator.generate_svg_documents()

    assert tuple(documents) == generator.GENERATED_FILENAMES
    assert len(documents) == 12

    for filename, svg in documents.items():
        root = ET.fromstring(svg)
        assert root.tag == f"{{{SVG_NS}}}svg"
        assert root.attrib["data-pipeline"] == generator.PIPELINE_SCHEMA
        assert root.attrib["width"]
        assert root.attrib["height"]

        metadata = _metadata(root)
        assert metadata["schema"] == generator.PIPELINE_SCHEMA
        assert metadata["generator"] == generator.GENERATOR_PATH
        assert metadata["theme_behavior"] == "light/dark palette follows the embedding element color-scheme"
        assert metadata["sample_reduction"] == "per-column minimum and maximum"

        theme_style = root.find("svg:style[@data-layer='theme-palette']", NS)
        assert theme_style is not None and theme_style.text
        assert "@media (prefers-color-scheme:dark)" in theme_style.text
        assert "--pps-svg-surface:#ffffff" in theme_style.text
        assert "--pps-svg-surface:#202723" in theme_style.text

        element_names = {_local_name(node.tag) for node in root.iter()}
        assert not element_names.intersection(FORBIDDEN_ELEMENTS), filename
        assert "path" in element_names
        assert "text" in element_names
        assert "rect" in element_names

        for node in root.iter():
            for name, value in node.attrib.items():
                assert _local_name(name) != "href", filename
                lowered = value.lower()
                assert "data:" not in lowered
                assert "base64" not in lowered
                assert "file:" not in lowered
                assert "http://" not in lowered
                assert "https://" not in lowered


def test_showcase_uses_runtime_gaussian_source_and_canonical_burst_contract() -> None:
    generator = _load_generator()
    documents = generator.generate_svg_documents()

    burst_root = ET.fromstring(documents["looming_burst_train_waveform.svg"])
    burst_metadata = _metadata(burst_root)
    canonical = generator.PPS_LOOMING_GOLD_STANDARD_SOURCE_PARAMETERS

    assert burst_metadata["noise_distribution"] == "Gaussian"
    assert burst_metadata["source_profile"] == generator.PPS_LOOMING_GOLD_STANDARD_SOURCE_PROFILE
    assert burst_metadata["resolved_burst_count"] == 33
    assert burst_metadata["resolved_actual_period_s"] == canonical["target_period_s"] == 0.095
    assert burst_metadata["source_parameters"]["burst_duration_s"] == canonical["burst_duration_s"] == 0.030
    assert burst_metadata["source_parameters"]["rise_fall_s"] == canonical["rise_fall_s"] == 0.010
    assert burst_metadata["approach"]["gain"] == "reciprocal_distance_1_over_r"

    waveform = burst_root.find(".//svg:path[@data-channel='generated-source']", NS)
    assert waveform is not None
    assert waveform.attrib["data-layer"] == "waveform"
    assert waveform.attrib["data-sample-reduction"] == "min-max-bin"
    assert waveform.attrib["d"].count("L ") > 1_000

    burst_markers = burst_root.findall(".//svg:line[@data-layer='burst-onset']", NS)
    assert len(burst_markers) == burst_metadata["resolved_burst_count"]


def test_audiogram_and_baseline_previews_have_semantic_vector_channels() -> None:
    generator = _load_generator()
    documents = generator.generate_svg_documents()

    audiogram = ET.fromstring(documents["audiogram_looming_trial.svg"])
    channels = {
        node.attrib["data-channel"]
        for node in audiogram.findall(".//svg:path[@data-layer='waveform']", NS)
    }
    assert channels == {"left-audio", "right-audio", "tactile-drive"}
    assert len(audiogram.findall(".//svg:line[@data-layer='soa-marker']", NS)) == 3
    assert _metadata(audiogram)["tactile"]["soa_s"] == 1.30

    for filename in generator.GENERATED_FILENAMES:
        if not filename.startswith("baseline_"):
            continue
        root = ET.fromstring(documents[filename])
        metadata = _metadata(root)
        assert metadata["asset_role"] == "baseline_strategy_widget"
        assert root.find(".//*[@data-channel='tactile']") is not None
        if metadata["audio_mode"] == "silent":
            assert root.find(".//*[@data-layer='silenced-audio']") is not None
        else:
            assert root.find(".//*[@data-channel='audio']") is not None


def test_interface_previews_are_compact_transparent_widget_scenes() -> None:
    generator = _load_generator()
    documents = generator.generate_svg_documents()

    for filename in (
        "looming_burst_train_widget.svg",
        "looming_smooth_linear_approach_widget.svg",
    ):
        root = ET.fromstring(documents[filename])
        metadata = _metadata(root)
        assert metadata["asset_role"] == "source_mode_control_preview"
        assert metadata["composition"] == "compact_transparent_widget"
        assert root.attrib["width"] == "320"
        assert root.attrib["height"] == "96"
        transparent = root.find("svg:rect[@data-layer='transparent-background']", NS)
        assert transparent is not None
        assert transparent.attrib["fill"] == "none"
        assert root.find(".//svg:path[@data-channel='generated-source']", NS) is not None

    for filename in generator.GENERATED_FILENAMES:
        if not filename.startswith("baseline_"):
            continue
        root = ET.fromstring(documents[filename])
        transparent = root.find("svg:rect[@data-layer='transparent-background']", NS)
        assert transparent is not None
        assert transparent.attrib["fill"] == "none"
        assert root.find("svg:rect[@data-layer='frame']", NS) is None

    baseline_none = ET.fromstring(documents["baseline_none.svg"])
    none_mark = baseline_none.find(".//*[@data-layer='no-extra-baseline-mark']", NS)
    assert none_mark is not None
    assert none_mark.tag == f"{{{SVG_NS}}}text"
    assert none_mark.text == "TRIAL ONLY"


def test_dashboard_uses_compact_theme_bridged_signal_widgets() -> None:
    html = (DASHBOARD_DIR / "index.html").read_text(encoding="utf-8")
    css = (DASHBOARD_DIR / "styles.css").read_text(encoding="utf-8")

    assert 'src="looming_burst_train_widget.svg"' in html
    assert 'src="looming_smooth_linear_approach_widget.svg"' in html
    assert 'class="native-signal-graphic"' in html
    assert 'class="baseline-option-graphic native-signal-graphic"' in html
    assert "color-scheme: inherit" in css
    assert ".source-mode-widget-copy::before" in css
    assert ".source-mode-widget:has(input:checked) .source-mode-widget-copy::before" in css
    assert ".source-mode-widget:has(input:focus-visible) .source-mode-widget-body" in css


def test_generation_is_reproducible_and_committed_copies_are_identical() -> None:
    generator = _load_generator()
    first = generator.generate_svg_documents()
    second = generator.generate_svg_documents()

    assert first == second
    for filename, expected in first.items():
        package_copy = ASSET_DIR / filename
        dashboard_copy = DASHBOARD_DIR / filename
        assert package_copy.read_text(encoding="utf-8") == expected
        assert dashboard_copy.read_text(encoding="utf-8") == expected
        assert package_copy.read_bytes() == dashboard_copy.read_bytes()


def test_generator_check_mode_and_compiled_asset_parity() -> None:
    generator = _load_generator()
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    for filename in generator.INTERFACE_FILENAMES:
        source = DASHBOARD_DIR / filename
        compiled = list(COMPILED_ASSET_DIR.glob(f"{source.stem}-*.svg"))
        assert len(compiled) == 1, filename
        assert compiled[0].read_bytes() == source.read_bytes()
