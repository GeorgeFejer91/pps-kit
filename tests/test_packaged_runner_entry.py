from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_packaged_runner_entry_enables_asio_before_focus_import():
    source = (REPO_ROOT / "windows" / "focus_runner_entry.py").read_text(encoding="utf-8")

    asio_guard = 'os.environ.setdefault("SD_ENABLE_ASIO", "1")'
    focus_import = "from peripersonal_space_toolkit.focus_app import main"

    assert asio_guard in source
    assert focus_import in source
    assert source.index(asio_guard) < source.index(focus_import)


def test_packaged_runner_spec_includes_tactile_click_assets():
    source = (REPO_ROOT / "windows" / "PPSExperimentRunner.spec").read_text(encoding="utf-8")

    assert '"assets" / "click"' in source
    assert '"assets/click"' in source
