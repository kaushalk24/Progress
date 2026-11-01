#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FiberCallout Studio - entry point.

  GUI : FiberCalloutStudio.exe            (or: python fiber_callout_studio.py)
  CLI : FiberCalloutStudio.exe --cli --drawing design.dwg --splice reports.zip --address address_lists --out output
  Test: FiberCalloutStudio.exe --selftest [--report selftest.txt]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Optional, Sequence


def _ensure_console() -> None:
    """A windowed (no-console) Windows build has no stdout; reattach to the parent console for CLI use."""
    if os.name == "nt" and (sys.stdout is None or sys.stderr is None):
        try:
            import ctypes
            if ctypes.windll.kernel32.AttachConsole(-1):
                sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
                sys.stderr = sys.stdout
        except Exception:  # noqa: BLE001 - no console available: output goes nowhere
            pass
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = sys.stdout


def build_arg_parser() -> argparse.ArgumentParser:
    from fcs import APP_NAME, APP_VERSION
    p = argparse.ArgumentParser(prog="FiberCalloutStudio", description=f"{APP_NAME} {APP_VERSION}")
    p.add_argument("--cli", action="store_true", help="run without the GUI")
    p.add_argument("--selftest", action="store_true", help="generate a synthetic network and verify the engine")
    p.add_argument("--gui-smoke", action="store_true", help="open the main window, then close it (installation check)")
    p.add_argument("--report", default="", help="self-test: also write the result to this text file")
    p.add_argument("--drawing", help="target .dwg / .dxf")
    p.add_argument("--splice", nargs="*", default=[], help="splice report files / folders / zips")
    p.add_argument("--address", nargs="*", default=[], help="address list files / folders / zips "
                   "(one combined list in either option also works)")
    p.add_argument("--out", default="", help="output folder")
    p.add_argument("--project", default="", help="optional .json with input paths / overrides")
    p.add_argument("--validate-only", action="store_true")
    p.add_argument("--scan-only", action="store_true")
    p.add_argument("--ports-per-pon", type=int, default=None, help="override the splitter size (default: from splice reports)")
    p.add_argument("--units", choices=["auto", "feet", "meters", "inches"], default=None, help="override drawing units")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.gui_smoke:
        from PyQt6.QtCore import QTimer
        from fcs.gui import run_gui
        state = {}

        def ready(win, app):
            state["title"] = win.windowTitle()
            state["pages"] = win.stack.count()
            QTimer.singleShot(1500, app.quit)
        rc = run_gui(ready)
        ok = rc == 0 and state.get("pages") == 2
        if args.report:
            Path(args.report).write_text(f"GUI smoke test {'PASSED' if ok else 'FAILED'}: {state}\n", encoding="utf-8")
        return 0 if ok else 1
    if not (args.cli or args.selftest):
        from fcs.gui import run_gui
        return run_gui()
    _ensure_console()
    if args.selftest:
        from fcs.selftest import run_selftest
        ok, text = run_selftest(verbose=True)
        if args.report:
            Path(args.report).write_text(text, encoding="utf-8")
        return 0 if ok else 1
    from fcs.engine import CalloutEngine, Cancelled, Reporter, RunConfig
    cfg = RunConfig()
    if args.project:
        cfg = RunConfig.from_dict(json.loads(Path(args.project).read_text(encoding="utf-8")))
    if args.drawing:
        cfg.drawing_path = args.drawing
    if args.splice:
        cfg.splice_paths = args.splice
    if args.address:
        cfg.address_paths = args.address
    if args.out:
        cfg.output_dir = args.out
    if args.ports_per_pon is not None:
        cfg.ports_per_pon = args.ports_per_pon
    if args.units:
        cfg.units = args.units
    # one combined list works too: splice reports and address lists are told apart by their content
    if cfg.address_paths and not cfg.splice_paths:
        cfg.splice_paths = list(cfg.address_paths)
    elif cfg.splice_paths and not cfg.address_paths:
        cfg.address_paths = list(cfg.splice_paths)
    rep = Reporter()
    eng = CalloutEngine(cfg, rep)
    try:
        if args.scan_only:
            res = eng.scan()
            print(json.dumps(dict(columns=res.columns.__dict__, cad=res.cad.__dict__ if res.cad else None,
                                  ports=res.ports_hint, drawing=res.drawing_info), indent=2))
            return 0
        if not cfg.drawing_path:
            rep.log("--drawing is required", "ERROR")
            return 2
        if args.validate_only:
            res = eng.validate()
            return 1 if res.issues.count("ERROR") else 0
        res = eng.generate()
        print(json.dumps(res.outputs, indent=2))
        return 0
    except Cancelled:
        return 130
    except Exception as exc:  # noqa: BLE001 - CLI reports any failure with a non-zero exit code
        rep.log(f"{type(exc).__name__}: {exc}", "ERROR")
        rep.log(traceback.format_exc(), "DEBUG")
        return 1


if __name__ == "__main__":
    sys.exit(main())
