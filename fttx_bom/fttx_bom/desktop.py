"""Windows desktop application: FTTx BOM Tool.exe.

    FTTx BOM Tool.exe              open the application window
    FTTx BOM Tool.exe --selftest   check the installation (engine, DWG reader, interface server) and exit
    FTTx BOM Tool.exe --version    print the version

The interface is served on 127.0.0.1 only, by a second process of the same executable (`--serve PORT`), and
shown in an application window (Microsoft Edge WebView2, part of Windows 10/11). When the window cannot be
created, the default browser opens instead and a small control window keeps the application running.
Closing the window stops the server. No file leaves the computer.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from . import __version__
from .paths import APP_NAME, FROZEN, app_script, bundle_root, node_exe, streamlit_args, user_dir

LOADING_HTML = """<html><body style="font-family:Segoe UI,Arial,sans-serif;display:flex;align-items:center;justify-content:center;
height:100vh;margin:0;color:#1F2933;background:#F4F6F9"><div style="text-align:center"><div style="font-size:22px;font-weight:600">
FTTx BOM Tool</div><div style="margin-top:10px;color:#6b7280">Starting ...</div></div></body></html>"""


def _log(msg: str) -> None:
    try:
        with open(user_dir() / "app.log", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except OSError:
        pass


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_ready(port: int, timeout: float = 90.0, proc: subprocess.Popen | None = None) -> bool:
    url = f"http://127.0.0.1:{port}/_stcore/health"
    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc is not None and proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except OSError:
            time.sleep(0.4)
    return False


def serve(port: int) -> int:
    """Run the interface server in this process (the server needs the main thread)."""
    if sys.stdout is None or sys.stderr is None:  # windowed executable: no console streams
        sys.stdout = sys.stderr = open(user_dir() / "server.log", "a", encoding="utf-8")  # noqa: SIM115
    from streamlit.web import cli as stcli

    sys.argv = ["streamlit", "run", str(app_script()), *streamlit_args(port=port, headless=True)]
    return stcli.main()


def start_server(port: int) -> subprocess.Popen:
    if FROZEN:
        # the console companion (fttx-bom.exe) has standard streams; its window is hidden below
        cli = Path(sys.executable).with_name("fttx-bom.exe")
        cmd = [str(cli if cli.is_file() else sys.executable), "--serve", str(port)]
    else:
        cmd = [sys.executable, "-m", "fttx_bom.desktop", "--serve", str(port)]
    flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW: no console window behind the app
    log = open(user_dir() / "server.log", "w", encoding="utf-8")  # noqa: SIM115 - lives as long as the server
    return subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, creationflags=flags, cwd=str(bundle_root()))


def _window(url: str, server: subprocess.Popen) -> bool:
    """Application window; False when no window toolkit is available."""
    try:
        import webview  # pywebview: Edge WebView2 on Windows
    except Exception as exc:  # noqa: BLE001 - any failure falls back to the browser
        _log(f"window toolkit unavailable: {exc!r}")
        return False
    try:
        win = webview.create_window(APP_NAME, html=LOADING_HTML, width=1440, height=920, min_size=(1100, 700))

        def load():
            if wait_ready(int(url.rsplit(":", 1)[1].strip("/")), proc=server):
                win.load_url(url)
            else:
                win.load_html("<p style='font-family:Segoe UI;padding:2em'>The FTTx BOM Tool engine did not start. "
                              f"See {user_dir() / 'server.log'}.</p>")

        webview.start(load, private_mode=False, storage_path=str(user_dir() / "webview"))
        return True
    except Exception as exc:  # noqa: BLE001
        _log(f"application window failed: {exc!r}")
        return False


def _browser_fallback(url: str, server: subprocess.Popen) -> None:
    import webbrowser

    if not wait_ready(int(url.rsplit(":", 1)[1].strip("/")), proc=server):
        _message(f"The FTTx BOM Tool engine did not start. See {user_dir() / 'server.log'}.")
        return
    webbrowser.open(url)
    try:
        import tkinter as tk

        root = tk.Tk()
        root.title(APP_NAME)
        root.geometry("420x150")
        tk.Label(root, text=f"{APP_NAME} is running in your browser.", font=("Segoe UI", 11)).pack(pady=(18, 6))
        tk.Label(root, text=url, fg="#1F5FAD").pack()
        row = tk.Frame(root)
        row.pack(pady=12)
        tk.Button(row, text="Open again", width=14, command=lambda: webbrowser.open(url)).pack(side="left", padx=6)
        tk.Button(row, text="Quit", width=14, command=root.destroy).pack(side="left", padx=6)
        root.mainloop()
    except Exception:  # noqa: BLE001 - no GUI at all: keep serving until the server stops
        server.wait()


def _message(text: str) -> None:
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, text, APP_NAME, 0x10)
            return
        except Exception:  # noqa: BLE001
            pass
    print(text, file=sys.stderr)


def selftest() -> int:
    """Check every part of the installation; print one line per part, exit code 0 when all pass."""
    ok = True

    def report(name, passed, detail=""):
        nonlocal ok
        ok &= passed
        print(f"{'PASS' if passed else 'FAIL'}  {name}{('  ' + detail) if detail else ''}", flush=True)

    try:
        from .engine.rules import load_rules
        from .pipeline import run_job  # noqa: F401 - import check of the whole engine

        _cfg, rules = load_rules()
        report("engine and rules", len(rules) >= 40, f"{len(rules)} BOM rules")
    except Exception as exc:  # noqa: BLE001
        report("engine and rules", False, repr(exc))
    node = node_exe()
    if node:
        r = subprocess.run([node, str(bundle_root() / "tools" / "check.mjs")], capture_output=True, text=True, timeout=120,
                           cwd=str(bundle_root() / "tools"))
        report("DWG reader", r.returncode == 0, (r.stdout or r.stderr).strip()[:200])
    else:
        report("DWG reader", False, "Node.js runtime not found")
    try:
        import ezdxf  # noqa: F401

        report("DXF reader", True)
    except Exception as exc:  # noqa: BLE001
        report("DXF reader", False, repr(exc))
    port = free_port()
    server = start_server(port)
    try:
        up = wait_ready(port, timeout=120, proc=server)
        page = ""
        if up:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=10) as r:
                page = r.read(2000).decode("utf-8", "replace")
        report("interface server", up and "<html" in page.lower(), f"port {port}")
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
    print("ALL PASS" if ok else "SOME CHECKS FAILED", flush=True)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--serve"]:
        return serve(int(argv[1]))
    if argv[:1] == ["--version"]:
        print(f"{APP_NAME} {__version__}")
        return 0
    if argv[:1] == ["--selftest"]:
        return selftest()
    if argv[:1] in (["run"], ["auto"], ["batch"]):  # the command line, from the same executable
        from .cli import main as cli_main

        return cli_main(argv)
    port = free_port()
    server = start_server(port)
    url = f"http://127.0.0.1:{port}/"
    _log(f"start {__version__} {url} bundle={bundle_root()}")
    try:
        if not _window(url, server):
            _browser_fallback(url, server)
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
