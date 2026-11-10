# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
root = Path.cwd().resolve()
src_root = root / "packages" / "pps-runtime" / "src"
datas = [
    (str(root / "apps" / "designer" / "frontend" / "compiled"), "apps/designer/frontend/compiled"),
]

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
    icon=str(root / "packages" / "pps-resources" / "assets" / "app" / "pps_toolkit_icon.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="PPSDesigner")
