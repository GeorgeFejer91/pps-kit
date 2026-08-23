# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
root = Path.cwd().resolve()
src_root = root / "packages" / "pps-runtime" / "src"
resource_root = root / "packages" / "pps-resources"
datas = [
    (str(root / "apps" / "designer" / "frontend" / "compiled"), "apps/designer/frontend/compiled"),
    (str(resource_root / "assets" / "app"), "assets/app"),
]
for source, target in (
    (resource_root / "assets" / "preloads", "assets/preloads"),
    (resource_root / "assets" / "breathing", "assets/breathing"),
    (resource_root / "assets" / "click", "assets/click"),
    (resource_root / "assets" / "tactile", "assets/tactile"),
    (resource_root / "assets" / "0. Head-Related Impulse Response (HRIR) model", "assets/0. Head-Related Impulse Response (HRIR) model"),
    (resource_root / "study_templates", "study_templates"),
):
    if source.exists():
        datas.append((str(source), target))

a = Analysis(
    [str(root / "apps" / "designer" / "launchers" / "designer_launcher_entry.py")],
    pathex=[str(src_root)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "webview",
        "webview.platforms.edgechromium",
        "uvicorn.lifespan.on",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
    ],
    excludes=["PySide6", "PyQt5", "PyQt6", "cefpython3", "qtpy"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="PPSDesigner",
    console=False, upx=False,
    icon=str(resource_root / "assets" / "app" / "pps_toolkit_icon.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="PPSDesigner")
