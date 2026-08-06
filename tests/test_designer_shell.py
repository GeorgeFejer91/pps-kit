from __future__ import annotations

from peripersonal_space_toolkit import designer_shell


def test_external_doi_prefers_linux_gio_handoff(monkeypatch) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_popen(command: list[str], **kwargs: object) -> object:
        calls.append((command, kwargs))
        return object()

    monkeypatch.setattr(designer_shell.sys, "platform", "linux")
    monkeypatch.setattr(designer_shell.subprocess, "Popen", fake_popen)

    opened = designer_shell.ShellApi().open_external("https://doi.org/10.1038/srep18603")

    assert opened is True
    assert calls[0][0] == ["gio", "open", "https://doi.org/10.1038/srep18603"]
    assert calls[0][1]["start_new_session"] is True


def test_external_doi_falls_back_when_gio_is_unavailable(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_popen(command: list[str], **_kwargs: object) -> object:
        calls.append(command)
        if command[0] == "gio":
            raise FileNotFoundError("gio is unavailable")
        return object()

    monkeypatch.setattr(designer_shell.sys, "platform", "linux")
    monkeypatch.setattr(designer_shell.subprocess, "Popen", fake_popen)

    opened = designer_shell.ShellApi().open_external("https://doi.org/10.1038/srep18603")

    assert opened is True
    assert calls == [
        ["gio", "open", "https://doi.org/10.1038/srep18603"],
        ["xdg-open", "https://doi.org/10.1038/srep18603"],
    ]


def test_external_handoff_rejects_unsafe_schemes(monkeypatch) -> None:
    monkeypatch.setattr(
        designer_shell.subprocess,
        "Popen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not launch")),
    )

    assert designer_shell.ShellApi().open_external("file:///tmp/private") is False
    assert designer_shell.ShellApi().open_external("javascript:alert(1)") is False
