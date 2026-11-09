# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for PortMasterForwarder.exe  (build on Windows:  python -m PyInstaller packaging/portmasterforwarder.spec)."""
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent                    # noqa: F821  (SPECPATH is provided by PyInstaller)
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from portmasterforwarder import __version__ as VERSION          # noqa: E402

ASSETS = SRC / "portmasterforwarder" / "assets"

# ---- Windows version information (shown in the file properties of PortMasterForwarder.exe). Only generated on Windows.
_version_file = None
if sys.platform == "win32":
    try:
        from PyInstaller.utils.win32.versioninfo import (  # noqa: E402
            FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo)

        _nums = tuple(int(x) for x in VERSION.split(".")) + (0,)
        _info = VSVersionInfo(
            ffi=FixedFileInfo(filevers=_nums, prodvers=_nums, mask=0x3F, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
            kids=[
                StringFileInfo([StringTable("040904B0", [
                    StringStruct("CompanyName", "PortMasterForwarder contributors"),
                    StringStruct("FileDescription", "PortMasterForwarder - Your games. Properly organized."),
                    StringStruct("FileVersion", VERSION),
                    StringStruct("InternalName", "PortMasterForwarder"),
                    StringStruct("LegalCopyright", "MIT License"),
                    StringStruct("OriginalFilename", "PortMasterForwarder.exe"),
                    StringStruct("ProductName", "PortMasterForwarder"),
                    StringStruct("ProductVersion", VERSION),
                ])]),
                VarFileInfo([VarStruct("Translation", [1033, 1200])]),
            ],
        )
        _build = ROOT / "build"
        _build.mkdir(exist_ok=True)
        _version_file = str(_build / "version_info.txt")
        Path(_version_file).write_text(str(_info), encoding="utf-8")
    except Exception as exc:  # the version resource is cosmetic: never fail the build because of it
        print("WARNING: could not create the Windows version resource:", exc)
        _version_file = None

a = Analysis(                                              # noqa: F821
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=[(str(ASSETS), "portmasterforwarder/assets")],
    hiddenimports=["PIL._tkinter_finder"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["numpy", "matplotlib", "pytest", "unittest.mock"],
    noarchive=False,
)
pyz = PYZ(a.pure)                                          # noqa: F821
exe = EXE(                                                 # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="PortMasterForwarder",
    icon=str(ASSETS / "icon.ico"),
    version=_version_file,
    console=False,
    upx=False,
    runtime_tmpdir=None,
)
