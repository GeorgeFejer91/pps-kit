from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _method_body(source: str, method_name: str) -> str:
    marker = f"    def {method_name}(self"
    start = source.index(marker)
    next_method = source.find("\n    def ", start + len(marker))
    return source[start:] if next_method == -1 else source[start:next_method]


def test_retired_runner_mouse_lock_is_disabled():
    source = (REPO_ROOT / "src" / "peripersonal_space_toolkit" / "runner.py").read_text(encoding="utf-8")
    start_body = _method_body(source, "_start_mouse_lock")
    loop_body = _method_body(source, "_do_mouse_lock")

    assert "Deprecated no-op" in start_body
    assert "_do_mouse_lock()" not in start_body
    assert "moveTo" not in loop_body
    assert ".after(" not in loop_body
