# Build on the target OS: python -m PyInstaller custompresence.spec
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH)
a = Analysis(
    [str(root / "app.py")],
    pathex=[str(root)],
    binaries=[],
    datas=collect_data_files("custompresence") + [(str(root / "LICENSE"), ".")],
    hiddenimports=["uvicorn.protocols.http.h11_impl", "uvicorn.lifespan.on"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PyQt5", "PyQt6", "PySide2", "PySide6", "cefpython3"],
    noarchive=False,
)
pyz = PYZ(a.pure)
common = dict(name="CustomPresence", debug=False, strip=False, upx=False, console=False)
if sys.platform == "darwin":
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **common)
    files = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="CustomPresence")
    app = BUNDLE(files, name="CustomPresence.app", bundle_identifier="app.custompresence.desktop",
                 icon=str(root / "custompresence/assets/icons/app.icns"),
                 info_plist={"NSHighResolutionCapable": True})
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [],
              icon=str(root / "custompresence/assets/icons/app.ico"), **common)
