# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

root = Path.cwd().resolve()
src_root = root / "src"
datas = collect_data_files(
    "peripersonal_space_toolkit",
    includes=["assets/*", "dashboard/**/*", "viewer/**/*"],
)
for source, target in (
    (root / "assets" / "preloads", "assets/preloads"),
    (root / "assets" / "breathing", "assets/breathing"),
    (root / "assets" / "click", "assets/click"),
    (root / "assets" / "tactile", "assets/tactile"),
    (root / "study_templates", "study_templates"),
):
    if source.exists():
        datas.append((str(source), target))

a = Analysis(
    [str(root / "windows" / "designer_launcher_entry.py")],
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
    icon=str(src_root / "peripersonal_space_toolkit" / "assets" / "pps_toolkit_icon.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="PPSDesigner")
