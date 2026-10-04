# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

root = Path.cwd().resolve()
resources = root / "packages" / "pps-resources"
datas = []
if os.environ.get("PPS_PLANNER_EXTERNAL_SHARED") != "1":
    datas.append((str(root / "apps" / "designer" / "frontend" / "compiled"), "apps/designer/frontend/compiled"))
    datas.append((str(resources / "assets" / "app"), "assets/app"))
    for source, destination in (
        (resources / "assets" / "0. Head-Related Impulse Response (HRIR) model", "assets/0. Head-Related Impulse Response (HRIR) model"),
        (resources / "assets" / "preloads", "assets/preloads"),
        (resources / "assets" / "breathing", "assets/breathing"),
        (resources / "assets" / "click", "assets/click"),
        (resources / "assets" / "tactile", "assets/tactile"),
        (resources / "study_templates", "study_templates"),
        (resources / "configs", "configs"),
    ):
        if source.exists():
            datas.append((str(source), destination))
    renderer_dir = root / "third_party" / "3dti_renderer" / "bin"
    for binary in (*renderer_dir.glob("*.exe"), *renderer_dir.glob("*.dll")):
        datas.append((str(binary), "third_party/3dti_renderer/bin"))
    for name in ("3DTI_AUDIOTOOLKIT_LICENSE", "LICENSE"):
        license_file = root / "third_party" / "3dti_AudioToolkit" / name
        if license_file.is_file():
            datas.append((str(license_file), "third_party/3dti_AudioToolkit"))

a = Analysis(
    [str(root / "apps" / "designer" / "launchers" / "planner_worker_entry.py")],
    pathex=[str(root / "packages" / "pps-runtime" / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=["fastapi", "httpx._transports.asgi"],
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
    name="PPSPlannerWorker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PPSPlannerWorker",
)
