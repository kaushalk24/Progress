"""Build the stand-alone program folder and zip it.

    python packaging/build.py            (from the tool folder; needs: pip install -r packaging/requirements-build.txt)

Steps: PyInstaller (packaging/ftth_tool.spec) -> copy config/, templates/, docs/, README -> smoke test the
command-line program on a synthetic region -> dist/FTTH_Address_List_Tool_v<version>_<platform>.zip
Used by build_exe.bat and by the GitHub Actions workflow, so both produce the same result.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
APP = DIST / "FTTH_Address_List_Tool"
EXE = ".exe" if os.name == "nt" else ""

HOW_TO = """FTTH Address List Tool {version} - stand-alone program
=========================================================

Nothing needs to be installed: Python and all packages are inside this folder.

1. Copy the whole folder to the computer (keep every file together, e.g. C:\\Tools\\FTTH_Address_List_Tool).
2. Double-click "FTTH Address List Tool.exe".
3. Choose the splice-report folder, an output folder, the file-name prefix and the design drawing
   (.dwg as exported; run FXAUTO / FXMISSING first if drops are used), then "Generate address list(s)".

Command line / batch:  ftth_addrlist_cli.exe run --reports "<folder>" --out "<folder>" --prefix "<prefix>" --drawing "<file.dwg>"
                       ftth_addrlist_cli.exe --help

Settings: config\\default_config.toml (copy it to make a regional config, select it in the window).
Approvals policy for desk studies: config\\desk_study_acceptance.toml.
Documentation: docs\\ and README.md.

The packaged program reads DWG drawings directly (AutoCAD 2010-2018 formats). DXF is not read by the
packaged program; give it the .dwg.
"""


def version() -> str:
    sys.path.insert(0, str(ROOT))
    from ftth_addrlist import __version__
    return __version__


def run(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def pyinstaller():
    shutil.rmtree(APP, ignore_errors=True)
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(DIST),
         "--workpath", str(ROOT / "build"), str(ROOT / "packaging" / "ftth_tool.spec")], cwd=ROOT)


def copy_support_files(ver: str):
    for d in ("config", "templates", "docs"):
        shutil.copytree(ROOT / d, APP / d, dirs_exist_ok=True)
    shutil.copy2(ROOT / "README.md", APP / "README.md")
    (APP / "HOW TO RUN.txt").write_text(HOW_TO.format(version=ver), encoding="utf-8")


def smoke_test():
    """Run the packaged command-line program on a synthetic region: it must read the reports, write a
    workbook and exit with 1 (draft produced) - not crash."""
    sys.path.insert(0, str(ROOT / "tests"))
    from fixtures import build_network
    cli = APP / f"ftth_addrlist_cli{EXE}"
    gui = APP / f"FTTH Address List Tool{EXE}"
    assert cli.exists(), f"missing {cli}"
    assert gui.exists(), f"missing {gui}"
    with tempfile.TemporaryDirectory() as tmp:
        reports = build_network(Path(tmp) / "reports")
        out = Path(tmp) / "out"
        run([str(cli), "--help"], stdout=subprocess.DEVNULL)
        res = subprocess.run([str(cli), "run", "--reports", str(reports), "--out", str(out), "--prefix", "SMOKE"],
                             capture_output=True, text=True)
        print(res.stdout[-2000:], res.stderr[-2000:])
        books = list(out.glob("*.xlsx"))
        if res.returncode != 1 or not books:
            raise SystemExit(f"smoke test failed: exit {res.returncode}, workbooks {books}")
    print("smoke test passed", flush=True)


def main():
    ver = version()
    pyinstaller()
    copy_support_files(ver)
    smoke_test()
    plat = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}.get(platform.system(), platform.system())
    zip_base = DIST / f"FTTH_Address_List_Tool_v{ver}_{plat}"
    archive = shutil.make_archive(str(zip_base), "zip", root_dir=DIST, base_dir=APP.name)
    print(f"\nBuilt: {APP}\nZip:   {archive}")


if __name__ == "__main__":
    main()
