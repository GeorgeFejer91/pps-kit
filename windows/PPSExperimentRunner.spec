# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from importlib.util import find_spec
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


root = Path.cwd().resolve()
src_root = root / "src"
icon_path = src_root / "peripersonal_space_toolkit" / "assets" / "pps_toolkit_icon.ico"
disable_icon = os.environ.get("PPS_EXPERIMENT_RUNNER_DISABLE_ICON", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

datas = collect_data_files(
    "peripersonal_space_toolkit",
    includes=[
        "assets/*",
        "dashboard/*",
        "viewer/*",
        "viewer/vendor/three/*",
    ],
)
companion_hiddenimports = (
    collect_submodules("h11")
    + collect_submodules("sniffio")
    + collect_submodules("uvicorn.protocols.http")
    + collect_submodules("uvicorn.protocols.websockets")
)

pyside_spec = find_spec("PySide6")
if pyside_spec and pyside_spec.submodule_search_locations:
    pyside_root = Path(list(pyside_spec.submodule_search_locations)[0])
    for plugin_name in ("platforms", "styles", "imageformats", "iconengines"):
        plugin_dir = pyside_root / "plugins" / plugin_name
        if plugin_dir.exists():
            datas.append((str(plugin_dir), f"PySide6/plugins/{plugin_name}"))

for source, target in (
    (
        root / "assets" / "0. Head-Related Impulse Response (HRIR) model",
        "assets/0. Head-Related Impulse Response (HRIR) model",
    ),
    (root / "assets" / "preloads", "assets/preloads"),
    (root / "assets" / "breathing", "assets/breathing"),
    (root / "assets" / "click", "assets/click"),
    (root / "assets" / "tactile", "assets/tactile"),
    (root / "study_templates", "study_templates"),
):
    if source.exists():
        datas.append((str(source), target))

a = Analysis(
    [str(root / "windows" / "focus_runner_entry.py")],
    pathex=[str(src_root)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "PySide6.QtTest",
        "fastapi",
        "PIL.Image",
        "pyautogui",
        "pynput.mouse",
        "qrcode",
        "soundfile",
        "uvicorn.lifespan.on",
        "uvicorn.loops.asyncio",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.protocols.websockets.websockets_impl",
        "websockets",
    ]
    + companion_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PPSExperimentRunner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="NONE" if disable_icon else str(icon_path),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PPSExperimentRunner",
)
