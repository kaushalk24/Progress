# PyInstaller build of the FTTH address-list tool: one folder with two programs sharing one runtime:
#   FTTH Address List Tool.exe  - the window (no console)
#   ftth_addrlist_cli.exe       - command line / batch use
# Run through packaging/build.py, which also copies config/, templates/ and docs/ next to them.
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
HIDDEN = collect_submodules("ftth_addrlist")
DATAS = collect_data_files("ftth_addrlist") + [       # built-in logo; fallback copy of the default settings
    (os.path.join(ROOT, "config", "default_config.toml"), "config")]
ICON = os.path.join(SPECPATH, "app.ico")
EXCLUDE = ["pytest", "numpy", "ezdxf", "matplotlib", "PIL", "IPython"]


def analysis(script):
    return Analysis([os.path.join(SPECPATH, script)], pathex=[ROOT], hiddenimports=HIDDEN, excludes=EXCLUDE,
                    datas=DATAS, noarchive=False)


gui = analysis("gui_main.py")
cli = analysis("cli_main.py")
gui_exe = EXE(PYZ(gui.pure), gui.scripts, [], exclude_binaries=True, name="FTTH Address List Tool",
              console=False, upx=False, icon=ICON)
cli_exe = EXE(PYZ(cli.pure), cli.scripts, [], exclude_binaries=True, name="ftth_addrlist_cli",
              console=True, upx=False, icon=ICON)
COLLECT(gui_exe, gui.binaries, gui.datas, cli_exe, cli.binaries, cli.datas, name="FTTH_Address_List_Tool",
        upx=False)
