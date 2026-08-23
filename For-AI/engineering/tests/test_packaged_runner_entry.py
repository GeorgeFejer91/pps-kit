from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_packaged_runner_entry_enables_asio_before_focus_import():
    source = (REPO_ROOT / "apps" / "runner" / "launchers" / "focus_runner_entry.py").read_text(encoding="utf-8")

    asio_guard = 'os.environ.setdefault("SD_ENABLE_ASIO", "1")'
    focus_import = "from peripersonal_space_toolkit.focus_app import main"

    assert asio_guard in source
    assert focus_import in source
    assert source.index(asio_guard) < source.index(focus_import)


def test_packaged_runner_spec_includes_tactile_click_assets():
    source = (REPO_ROOT / "apps" / "runner" / "packaging" / "PPSExperimentRunner.spec").read_text(encoding="utf-8")

    assert '"assets" / "click"' in source
    assert '"assets/click"' in source


def test_packaged_runner_build_has_iconless_retry_fallback():
    spec = (REPO_ROOT / "apps" / "runner" / "packaging" / "PPSExperimentRunner.spec").read_text(encoding="utf-8")
    build_script = (REPO_ROOT / "For-AI" / "engineering" / "build" / "windows" / "Build_Experiment_Runner_Exe.ps1").read_text(encoding="utf-8")

    assert "PPS_EXPERIMENT_RUNNER_DISABLE_ICON" in spec
    assert 'icon="NONE" if disable_icon else str(icon_path)' in spec
    assert "$StandardBuildExitCode = $LASTEXITCODE" in build_script
    assert 'PPS_EXPERIMENT_RUNNER_DISABLE_ICON = "1"' in build_script
    assert "after iconless fallback retry" in build_script
