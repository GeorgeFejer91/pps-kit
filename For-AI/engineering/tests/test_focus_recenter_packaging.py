from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_pyautogui_is_installed_and_packaged_for_focus_recenter():
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    spec = (REPO_ROOT / "apps" / "runner" / "packaging" / "PPSExperimentRunner.spec").read_text(encoding="utf-8")

    assert '"pyautogui>=0.9.54"' in pyproject
    assert '"pyautogui"' in spec
