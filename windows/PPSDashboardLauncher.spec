# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import os

from PyInstaller.utils.hooks import collect_data_files


root = Path.cwd().resolve()
src_root = root / "src"
icon_path = src_root / "peripersonal_space_toolkit" / "assets" / "pps_toolkit_icon.ico"
disable_icon = os.environ.get("PPS_DASHBOARD_LAUNCHER_DISABLE_ICON", "").strip().lower() in {
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
    (root / "configs", "configs"),
):
    if source.exists():
        datas.append((str(source), target))

a = Analysis(
    [str(root / "windows" / "dashboard_launcher_entry.py")],
    pathex=[str(src_root)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "uvicorn.lifespan.on",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.protocols.websockets.websockets_impl",
    ],
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
    name="PPSDashboardLauncher",
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
    name="PPSDashboardLauncher",
)
