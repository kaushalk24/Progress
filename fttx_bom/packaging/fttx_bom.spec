# PyInstaller build of the Windows application: one folder with
#   FTTx BOM Tool.exe   the desktop application (no console)
#   fttx-bom.exe        the same program with a console: command line (run / auto / batch), --selftest, --version
# plus config/, app/, tools/ (DWG reader) and node/ (Node.js runtime) beside the package, as in the repository.
# Build:  pyinstaller packaging/fttx_bom.spec --noconfirm   (from the fttx_bom folder; NODE_EXE = path of node.exe)
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
sys.path.insert(0, ROOT)
from fttx_bom import __version__  # noqa: E402

datas = [
    (os.path.join(ROOT, "config"), "config"),
    (os.path.join(ROOT, "app", "bom_app.py"), "app"),
    (os.path.join(ROOT, "tools", "dwg2json.mjs"), "tools"),
    (os.path.join(ROOT, "tools", "check.mjs"), "tools"),
    (os.path.join(ROOT, "tools", "package.json"), "tools"),
    (os.path.join(ROOT, "tools", "node_modules"), os.path.join("tools", "node_modules")),
    (os.path.join(ROOT, "DESIGN_STANDARDS.md"), "."),
    (os.path.join(ROOT, "README.md"), "."),
]
binaries = []
node = os.environ.get("NODE_EXE")
if node:
    binaries.append((node, "node"))
hiddenimports = collect_submodules("fttx_bom")
for pkg in ("streamlit", "webview", "clr_loader", "pythonnet", "ezdxf", "openpyxl", "pandas", "pyarrow", "altair"):
    try:
        d, b, h = collect_all(pkg)
    except Exception:  # optional package not installed
        continue
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [os.path.join(SPECPATH, "launcher.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter.test", "matplotlib", "IPython", "pytest", "notebook"],
    noarchive=False,
)
pyz = PYZ(a.pure)
icon = os.path.join(SPECPATH, "icon.ico")
version = os.path.join(SPECPATH, "version_info.txt") if os.path.exists(os.path.join(SPECPATH, "version_info.txt")) else None
gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name="FTTx BOM Tool", console=False, icon=icon, version=version,
          upx=False)
cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name="fttx-bom", console=True, icon=icon, version=version, upx=False)
coll = COLLECT(gui, cli, a.binaries, a.datas, name="FTTx BOM Tool", upx=False)
