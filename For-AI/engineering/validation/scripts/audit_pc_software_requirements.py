"""Audit Windows PC software requirements for PPS validation and runtime.

The audit is read-only. It does not install drivers, download installers, or
modify system state. Generated reports belong under ignored validation
artifacts so a lab PC can be checked before participant data collection.
"""

from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
import os
import platform
import shutil
import sys
import time
from pathlib import Path
from typing import Any


SCHEMA = "pps-pc-software-requirements-audit.v1"

PYTHON_PACKAGES = [
    {"package": "numpy", "requirement": ">=2.0", "purpose": "stimulus arrays, analysis, validation scripts", "scope": "runtime"},
    {"package": "scipy", "requirement": ">=1.12", "purpose": "signal processing and onset detection", "scope": "runtime"},
    {"package": "soundfile", "requirement": ">=0.13.1", "purpose": "WAV read/write", "scope": "runtime"},
    {"package": "sounddevice", "requirement": ">=0.4.7", "purpose": "PortAudio playback/recording, ASIO callback timing", "scope": "runtime"},
    {"package": "sofar", "requirement": ">=1.1", "purpose": "SOFA/HRIR file handling", "scope": "runtime"},
    {"package": "netCDF4", "requirement": ">=1.6", "purpose": "SOFA/NetCDF backend", "scope": "runtime"},
    {"package": "pyaudiowpatch", "requirement": ">=0.2.12", "purpose": "optional Windows WASAPI loopback diagnostics", "scope": "windows_diagnostic"},
    {"package": "pynput", "requirement": ">=1.7.7", "purpose": "mouse/keyboard listener for response timing", "scope": "runtime"},
    {"package": "PySide6", "requirement": ">=6.7,<7", "purpose": "Qt designer and native Focus Mode", "scope": "gui_extra"},
    {"package": "fastapi", "requirement": ">=0.110,<1", "purpose": "local HTML dashboard backend", "scope": "web_extra"},
    {"package": "uvicorn", "requirement": ">=0.27,<1", "purpose": "local HTML dashboard server", "scope": "web_extra"},
    {"package": "pylsl", "requirement": ">=1.16", "purpose": "LSL marker output and probe scripts", "scope": "lsl_extra"},
    {"package": "pyxdf", "requirement": ">=1.17", "purpose": "offline XDF/LabRecorder import for validation", "scope": "validation_recommended"},
    {"package": "pytest", "requirement": ">=8.0", "purpose": "regression tests", "scope": "dev_validation"},
    {"package": "build", "requirement": ">=1.2", "purpose": "package build checks", "scope": "dev_validation"},
    {"package": "Pillow", "requirement": ">=10.0", "purpose": "image/icon tests and assets", "scope": "dev_validation"},
    {"package": "httpx", "requirement": ">=0.27", "purpose": "dashboard backend tests", "scope": "dev_validation"},
    {"package": "pydub", "requirement": ">=0.25.1", "purpose": "optional MP3/source conversion", "scope": "mp3_extra"},
    {"package": "kokoro-onnx", "requirement": "==0.5.0", "purpose": "optional synthetic instruction TTS", "scope": "tts_extra"},
]

EXTERNAL_TOOLS = [
    {
        "name": "Git",
        "command": "git",
        "purpose": "development/version-control workflow",
        "required_for": "development",
        "source": "https://git-scm.com/download/win",
    },
    {
        "name": "MiKTeX/pdfTeX",
        "command": "pdflatex",
        "purpose": "build latency_reliability_validations.pdf",
        "required_for": "validation_report_pdf",
        "source": "https://miktex.org/download",
    },
    {
        "name": "LabRecorder",
        "command": "LabRecorder",
        "purpose": "external LSL/XDF recording during validation and EEG sessions",
        "required_for": "external_lsl_xdf_recording",
        "source": "https://github.com/labstreaminglayer/App-LabRecorder/releases",
    },
]

WINDOWS_DRIVERS = [
    {
        "name": "Native Instruments Komplete Audio 6 MK2 Windows driver",
        "required_component": "Komplete Audio ASIO Driver",
        "purpose": "single synchronized full-duplex multichannel ASIO endpoint",
        "source": "https://www.native-instruments.com/en/support/downloads/drivers-other-files/",
        "notes": "Use the official NI driver or Native Access. Do not substitute ASIO4ALL/FlexASIO/Voicemeeter for publication timing.",
    },
    {
        "name": "Optional Woojer firmware/app tooling",
        "required_component": "Woojer wired analog audio path",
        "purpose": "device maintenance only; validation uses wired analog input, not Bluetooth",
        "source": "https://www.woojer.com/pages/support",
        "notes": "Mechanical onset still requires an external vibration/contact sensor.",
    },
]


def _version(package: str) -> str | None:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


def _package_rows() -> list[dict[str, Any]]:
    rows = []
    for item in PYTHON_PACKAGES:
        version = _version(item["package"])
        rows.append({**item, "installed": version is not None, "installed_version": version or ""})
    return rows


def _tool_rows() -> list[dict[str, Any]]:
    rows = []
    for item in EXTERNAL_TOOLS:
        path = shutil.which(item["command"])
        if not path and item["command"].lower() == "labrecorder":
            local_candidates = sorted(Path("local_data/software_tools/labrecorder").glob("**/LabRecorder.exe"))
            if local_candidates:
                path = str(local_candidates[0])
        rows.append({**item, "found": bool(path), "path": path or ""})
    return rows


def _asio_registry_rows() -> list[dict[str, Any]]:
    if platform.system().lower() != "windows":
        return []
    try:
        import winreg
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    for root_name, root in (("HKLM", winreg.HKEY_LOCAL_MACHINE), ("HKCU", winreg.HKEY_CURRENT_USER)):
        try:
            key = winreg.OpenKey(root, r"SOFTWARE\ASIO")
        except OSError:
            continue
        with key:
            index = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, index)
                except OSError:
                    break
                index += 1
                clsid = ""
                try:
                    subkey = winreg.OpenKey(key, subkey_name)
                    with subkey:
                        value, _kind = winreg.QueryValueEx(subkey, "CLSID")
                        clsid = str(value)
                except OSError:
                    pass
                rows.append({"root": root_name, "name": subkey_name, "clsid": clsid})
    return rows


def _sounddevice_rows() -> dict[str, Any]:
    os.environ.setdefault("SD_ENABLE_ASIO", "1")
    try:
        import sounddevice as sd  # type: ignore
    except Exception as exc:
        return {"available": False, "error": str(exc), "hostapis": [], "devices": [], "komplete_asio_ready": False}

    hostapis_raw = sd.query_hostapis()
    hostapis = [{"index": idx, "name": str(api.get("name", "")), "devices": list(api.get("devices", []))} for idx, api in enumerate(hostapis_raw)]
    devices = []
    komplete_asio_ready = False
    for idx, raw in enumerate(sd.query_devices()):
        dev = dict(raw)
        hostapi_name = str(hostapis_raw[int(dev.get("hostapi", 0))].get("name", ""))
        row = {
            "index": idx,
            "name": str(dev.get("name", "")),
            "hostapi": hostapi_name,
            "max_input_channels": int(dev.get("max_input_channels", 0)),
            "max_output_channels": int(dev.get("max_output_channels", 0)),
            "default_samplerate": float(dev.get("default_samplerate", 0.0)),
        }
        devices.append(row)
        if (
            "komplete" in row["name"].lower()
            and "asio" in row["hostapi"].lower()
            and row["max_input_channels"] >= 3
            and row["max_output_channels"] >= 3
        ):
            komplete_asio_ready = True
    return {"available": True, "hostapis": hostapis, "devices": devices, "komplete_asio_ready": komplete_asio_ready}


def build_audit() -> dict[str, Any]:
    package_rows = _package_rows()
    tool_rows = _tool_rows()
    asio_rows = _asio_registry_rows()
    sounddevice = _sounddevice_rows()
    missing_runtime = [
        row["package"]
        for row in package_rows
        if not row["installed"] and row["scope"] in {"runtime", "windows_diagnostic", "gui_extra", "web_extra", "lsl_extra"}
    ]
    missing_validation = [row["package"] for row in package_rows if not row["installed"] and row["scope"] in {"validation_recommended", "dev_validation"}]
    missing_tools = [row["name"] for row in tool_rows if not row["found"] and row["required_for"] in {"validation_report_pdf", "external_lsl_xdf_recording"}]
    return {
        "schema": SCHEMA,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "python": sys.version.replace("\n", " "),
            "executable": sys.executable,
        },
        "python_packages": package_rows,
        "external_tools": tool_rows,
        "windows_drivers": WINDOWS_DRIVERS,
        "asio_registry": asio_rows,
        "sounddevice": sounddevice,
        "summary": {
            "missing_runtime_packages": missing_runtime,
            "missing_validation_packages": missing_validation,
            "missing_external_tools": missing_tools,
            "komplete_asio_registry_present": any("komplete audio asio driver" == row["name"].lower() for row in asio_rows),
            "komplete_asio_sounddevice_ready": bool(sounddevice.get("komplete_asio_ready")),
        },
    }


def _write_markdown(path: Path, audit: dict[str, Any]) -> None:
    lines = [
        "# PPS PC Software Requirements Audit",
        "",
        f"- Created: `{audit['created_at']}`",
        f"- Python: `{audit['platform']['python']}`",
        f"- Executable: `{audit['platform']['executable']}`",
        f"- Komplete ASIO registry present: `{audit['summary']['komplete_asio_registry_present']}`",
        f"- Komplete ASIO sounddevice-ready: `{audit['summary']['komplete_asio_sounddevice_ready']}`",
        "",
        "## Python Packages",
        "",
        "| Package | Required | Installed | Version | Scope | Purpose |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in audit["python_packages"]:
        lines.append(
            f"| {row['package']} | `{row['requirement']}` | `{row['installed']}` | "
            f"`{row['installed_version']}` | {row['scope']} | {row['purpose']} |"
        )
    lines.extend(["", "## External Tools", "", "| Tool | Found | Path | Required for | Source |", "| --- | --- | --- | --- | --- |"])
    for row in audit["external_tools"]:
        lines.append(f"| {row['name']} | `{row['found']}` | `{row['path']}` | {row['required_for']} | {row['source']} |")
    lines.extend(["", "## ASIO Registry Entries", "", "| Root | Name | CLSID |", "| --- | --- | --- |"])
    for row in audit["asio_registry"]:
        lines.append(f"| {row['root']} | {row['name']} | `{row['clsid']}` |")
    lines.extend(["", "## Driver Requirements", "", "| Driver/tooling | Required component | Source | Notes |", "| --- | --- | --- | --- |"])
    for row in audit["windows_drivers"]:
        lines.append(f"| {row['name']} | {row['required_component']} | {row['source']} | {row['notes']} |")
    lines.extend(["", "## Missing Items", ""])
    lines.append(f"- Missing runtime packages: `{json.dumps(audit['summary']['missing_runtime_packages'])}`")
    lines.append(f"- Missing validation packages: `{json.dumps(audit['summary']['missing_validation_packages'])}`")
    lines.append(f"- Missing external tools: `{json.dumps(audit['summary']['missing_external_tools'])}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit PPS Windows PC software requirements.")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/validation_runs/pc_software_requirements"))
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    audit = build_audit()
    (args.output_dir / "pc_software_requirements_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    _write_markdown(args.output_dir / "pc_software_requirements_audit.md", audit)
    print(f"Wrote {args.output_dir / 'pc_software_requirements_audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
