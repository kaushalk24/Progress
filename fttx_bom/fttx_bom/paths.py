"""Where the tool's files live, from a source checkout and in the packaged Windows application.

The packaged app (PyInstaller, one folder) keeps the same layout as the repository next to the package:
config/, tools/ (DWG reader), app/ (interface) and node/ (Node.js runtime for the DWG reader). Files the user
changes (settings) and job output go to the user's profile, because the install folder is read-only.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "FTTx BOM Tool"
FROZEN = bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    """Folder holding config/, tools/, app/ (the repository root, or the packaged app's data folder)."""
    if FROZEN:
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[1]


def user_dir() -> Path:
    """Per-user settings folder: %APPDATA%\\FTTx BOM Tool on Windows, ~/.config/fttx_bom elsewhere."""
    base = os.environ.get("APPDATA") if os.name == "nt" else None
    d = Path(base) / APP_NAME if base else Path.home() / ".config" / "fttx_bom"
    d.mkdir(parents=True, exist_ok=True)
    return d


def jobs_dir() -> Path:
    """Job inputs and outputs of the app: Documents\\FTTx BOM Jobs when Documents exists."""
    docs = Path.home() / "Documents"
    return docs / "FTTx BOM Jobs" if docs.is_dir() else Path.home() / "FTTx_BOM_Jobs"


def policies_file() -> Path:
    """Selected conventions (Settings page). In the packaged app they belong to the user; from a source
    checkout they stay in config/ so they can be versioned with the rules."""
    if FROZEN or os.environ.get("FTTX_USER_SETTINGS"):
        return user_dir() / "policies.json"
    return bundle_root() / "config" / "policies.json"


def node_exe() -> str | None:
    """Node.js for the DWG reader: the runtime shipped with the app first, then one on the PATH."""
    for cand in (bundle_root() / "node" / ("node.exe" if os.name == "nt" else "node"),):
        if cand.is_file():
            return str(cand)
    return shutil.which("node")


def soffice_exe() -> str | None:
    """LibreOffice (optional, formula recalculation): on the PATH or in its standard install folders."""
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return found
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), r"C:\Program Files"):
            if base:
                p = Path(base) / "LibreOffice" / "program" / "soffice.exe"
                if p.is_file():
                    return str(p)
    elif sys.platform == "darwin":
        p = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
        if p.is_file():
            return str(p)
    return None


# Streamlit options shared by every way of starting the interface (CLI, Windows app)
STREAMLIT_OPTIONS = {
    "server.maxUploadSize": 4096,
    "server.fileWatcherType": "none",
    "browser.gatherUsageStats": False,
    "global.developmentMode": False,
    "client.toolbarMode": "minimal",
    "theme.base": "light",
    "theme.primaryColor": "#1F5FAD",
    "theme.backgroundColor": "#FFFFFF",
    "theme.secondaryBackgroundColor": "#F4F6F9",
    "theme.textColor": "#1F2933",
}


def streamlit_args(port: int | None = None, headless: bool = False) -> list[str]:
    args = [f"--{k}={str(v).lower() if isinstance(v, bool) else v}" for k, v in STREAMLIT_OPTIONS.items()]
    if port:
        args += [f"--server.port={port}", "--server.address=127.0.0.1"]
    if headless:
        args.append("--server.headless=true")
    return args


def app_script() -> Path:
    return bundle_root() / "app" / "bom_app.py"
