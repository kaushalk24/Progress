# -*- mode: python ; coding: utf-8 -*-
# PyInstaller build of FiberCallout Studio (single-file, windowed exe).
#   pyinstaller packaging/FiberCalloutStudio.spec --noconfirm
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
IS_WIN = sys.platform.startswith("win")


def _keep(name: str) -> bool:
    skip = ("ezdxf.addons.drawing.matplotlib", "ezdxf.addons.drawing.pyqt", "ezdxf.addons.drawing.qtviewer",
            "ezdxf.addons.xqt", "ezdxf.addons.drawing.pymupdf", "ezdxf.addons.browser", "ezdxf.addons.hpgl2",
            "ezdxf.addons.text2path", "ezdxf.addons.geo", "ezdxf.addons.meshex", "ezdxf.addons.openscad")
    return not name.startswith(skip)


hidden = collect_submodules("ezdxf", filter=_keep) + ["openpyxl.cell._writer"]
datas = [(os.path.join(ROOT, "assets"), "assets")] + collect_data_files("ezdxf")

a = Analysis(
    [os.path.join(ROOT, "fiber_callout_studio.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pandas", "PyQt5", "PySide2", "PySide6", "IPython", "pytest", "scipy",
              "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets", "PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.Qt3DCore",
              "PyQt6.QtMultimedia", "PyQt6.QtBluetooth", "PyQt6.QtPdf"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="FiberCalloutStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon=os.path.join(ROOT, "assets", "app.ico"),
    version=os.path.join(SPECPATH, "version_info.txt") if IS_WIN else None,
)
