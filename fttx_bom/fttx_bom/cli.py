"""Command line entry point.

  python -m fttx_bom auto  <files/folders/zips ...> --out OUT          everything auto-detected
  python -m fttx_bom batch <jobs folder> --out OUT [--template T]      one sub-folder per network/job
  python -m fttx_bom run   --dwg D --address-list A --splice-reports S --template T --out OUT
  python -m fttx_bom app                                               local browser app
(`python -m fttx_bom --dwg ...` without a sub-command means `run`.)
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from . import __version__
from .extract.backends import ExtractionError
from .pipeline import JobParams, JobResult, project_from_filename, run_job  # noqa: F401 (re-exported)


def _expand(paths: list[str], suffixes: tuple[str, ...]) -> list[Path]:
    out = []
    for p in paths or []:
        pp = Path(p)
        if pp.is_dir():
            out += sorted(x for x in pp.rglob("*") if x.suffix.lower() in suffixes and not x.name.startswith("~$"))
        elif pp.exists():
            out.append(pp)
        else:
            raise FileNotFoundError(f"input not found: {p}")
    return out


def report(res: JobResult) -> None:
    if res.calibration:
        print("calibration (cells matched per policy option vs the approved BOM):")
        for r in res.calibration:
            print(f"  {r['policy']:15s} {r['option']:15s} {r['matched']:>3}/{r['cells']:<3} "
                  f"{'BEST' if r['best'] else '    '} {'in use' if r['selected'] else ''}")
    for g in res.groups:
        print(f"FINAL BOM : {g.bom}")
        print(f"AUDIT     : {g.audit}")
        if g.discrepancies:
            print(f"DISCREP.  : {g.discrepancies}")
            print(f"reference : area cells {g.ref_cells[0]}/{g.ref_cells[1]} match, network totals {g.ref_totals[0]}/{g.ref_totals[1]} match")
        print("coverage  : " + ", ".join(f"{k}={v}" for k, v in sorted(g.coverage.items())))
        sev = {s: sum(1 for i in g.issues if i.severity == s) for s in ("ERROR", "WARN", "INFO")}
        print(f"deep check: ERROR={sev['ERROR']} WARN={sev['WARN']} INFO={sev['INFO']}  "
              f"(list: {g.issues_csv.name}; AutoCAD: SCRIPT {g.issues_scr.name} circles each located issue)")
        for i in g.issues:
            if i.severity == "ERROR":
                print(f"  ERROR {i.code} {i.network}: {i.message[:160]}")
        print(f"workbook  : FAIL={len(g.workbook_failures)} (recalculated={'yes' if g.recalculated else 'NO'})")
        for c in g.workbook_failures:
            print(f"  FAIL {c[0]}: {c[2]}")
    print(f"policies  : {', '.join(f'{k}={v}' for k, v in res.policies_used.items())}")
    print(f"elapsed   : {res.elapsed:.1f}s")


def _common(p):
    p.add_argument("--out", required=True, help="output folder")
    p.add_argument("--project-name")
    p.add_argument("--project-number")
    p.add_argument("--system", default="", help="e.g. 'Capital West' (template B1 list)")
    p.add_argument("--policies", help="policy selection JSON (default config/policies.json)")
    p.add_argument("--learn", action="store_true", help="with an approved BOM as reference: learn the best policy options")
    p.add_argument("--no-recalc", action="store_true", help="skip LibreOffice formula recalculation")
    p.add_argument("--cache", help="DWG conversion cache folder")


def _kw(a) -> dict:
    return dict(project_name=a.project_name, project_number=a.project_number, system=a.system or "",
                policies=Path(a.policies) if a.policies else None, learn=a.learn, recalc=not a.no_recalc,
                cache=Path(a.cache) if a.cache else None)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0].startswith("-") and argv[0] not in ("-h", "--help", "--version"):
        argv = ["run"] + argv
    ap = argparse.ArgumentParser(prog="fttx_bom", description="FTTx BOM automation: DWG + address list + splice reports -> BOM")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="explicit inputs")
    r.add_argument("--dwg", required=True, help="design drawing (.dwg, .dxf, or converter .json)")
    r.add_argument("--address-list", nargs="*", default=[], help="address list .xlsx files or folders")
    r.add_argument("--splice-reports", nargs="*", default=[], help="splice report .xlsx files or folders")
    r.add_argument("--template", required=True, help="approved BOM template workbook")
    r.add_argument("--reference", help="completed BOM to reconcile against (optional)")
    r.add_argument("--networks", help="comma separated network names (default: address-list sheet names)")
    r.add_argument("--rules", help="alternative rule catalogue JSON")
    r.add_argument("--conventions", help="alternative CAD conventions JSON")
    _common(r)

    a = sub.add_parser("auto", help="give files/folders/zips; roles are detected from content")
    a.add_argument("paths", nargs="+")
    a.add_argument("--template", help="force a template (else detected)")
    a.add_argument("--reference", help="force a reference BOM (else a detected completed BOM)")
    _common(a)

    b = sub.add_parser("batch", help="run every job sub-folder of a folder")
    b.add_argument("root")
    b.add_argument("--template", help="template used when a job folder has none")
    _common(b)

    sub.add_parser("app", help="start the local browser app")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "app":
            from .paths import app_script, streamlit_args

            return subprocess.call([sys.executable, "-m", "streamlit", "run", str(app_script()), *streamlit_args()])
        if args.cmd == "run":
            p = JobParams(dwg=Path(args.dwg), address_lists=_expand(args.address_list, (".xlsx",)),
                          splice_reports=_expand(args.splice_reports, (".xlsx",)), template=Path(args.template),
                          out=Path(args.out), reference=Path(args.reference) if args.reference else None,
                          networks=[n.strip() for n in args.networks.split(",")] if args.networks else None,
                          rules=Path(args.rules) if args.rules else None,
                          conventions=Path(args.conventions) if args.conventions else None, **_kw(args))
            res = run_job(p)
            report(res)
            return res.exit_code
        from .jobs import run_auto, run_batch

        if args.cmd == "auto":
            res, _notes = run_auto([Path(x) for x in args.paths], Path(args.out),
                                   template=Path(args.template) if args.template else None,
                                   reference=Path(args.reference) if args.reference else None, **_kw(args))
            report(res)
            return res.exit_code
        if args.cmd == "batch":
            run_batch(Path(args.root), Path(args.out), template=Path(args.template) if args.template else None, **_kw(args))
            return 0
    except (ExtractionError, FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
