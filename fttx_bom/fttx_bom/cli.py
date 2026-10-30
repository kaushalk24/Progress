"""Command line entry point.

Example:
  python -m fttx_bom --dwg design.dwg --address-list "Address List/" \
      --splice-reports "Splice Reports/" --template BOM_template.xlsx --out out/ \
      [--reference completed_BOM.xlsx]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

from . import __version__
from .engine.network import build_classifier
from .engine.rules import CONFIG_DIR, load_rules
from .engine.takeoff import build_takeoff
from .excel.reports import compare, read_reference, write_audit, write_discrepancies
from .excel.verify import verify
from .excel.writer import template_area_count, write_bom
from .extract.backends import ExtractionError, load_drawing
from .inputs.address_list import read_address_lists
from .inputs.splice_reports import read_splice_reports


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


def project_from_filename(name: str) -> dict:
    stem = re.sub(r"^[0-9a-f]{8}-", "", Path(name).stem)
    m = re.match(r"^(\d{4,})_(.+)$", stem)
    if not m:
        return {"number": "", "name": stem}
    number, rest = m.group(1), m.group(2)
    words = []
    for w in rest.split("_"):
        if w.upper() in ("FTTH", "FTTX", "BEAD", "DWG", "COMBINED") or re.match(r"^[A-Z]{2,5}-R\d{2}$", w):
            break
        words.append(w)
    if len(words) >= 2 and re.fullmatch(r"[A-Z]{2}", words[-1]):
        return {"number": number, "name": " ".join(words[:-1]) + ", " + words[-1]}
    return {"number": number, "name": " ".join(words)}


def run(args) -> int:
    t0 = time.time()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    conv = json.loads((Path(args.conventions) if args.conventions else CONFIG_DIR / "conventions.json").read_text())
    cfg, rules = load_rules(args.rules)

    template = Path(args.template)
    if not template.exists():
        raise FileNotFoundError(f"template not found: {template}")
    al_files = _expand(args.address_list, (".xlsx",))
    address_lists = read_address_lists(al_files) if al_files else {}
    reports = read_splice_reports(_expand(args.splice_reports, (".xlsx",))) if args.splice_reports else []
    networks = [n.strip() for n in args.networks.split(",")] if args.networks else sorted(address_lists)
    if not networks:
        raise SystemExit("no networks: supply address lists or --networks")
    for n in networks:
        if n not in address_lists:
            print(f"WARNING: no address list for {n}", file=sys.stderr)

    drawing = load_drawing(args.dwg, Path(args.cache) if args.cache else out / ".cache")
    cls = build_classifier(drawing, conv, networks)
    tk = build_takeoff(drawing, conv, cls, networks, address_lists, reports)

    proj = project_from_filename(Path(args.dwg).name)
    project = {"name": args.project_name or proj["name"], "number": args.project_number or proj["number"], "system": args.system or ""}
    n_area = template_area_count(template, cfg["sheet"])
    if len(networks) * 2 <= n_area:
        groups = [networks]
    else:
        print(f"template has {n_area} area columns: writing one BOM per OLM ({len(networks)} files)")
        groups = [[n] for n in networks]
    ref = read_reference(Path(args.reference), cfg["sheet"], rules) if args.reference else None
    worst = 0
    for group in groups:
        worst = max(worst, _write_group(args, group, tk.subset(group), drawing, cls, reports, al_files, template,
                                        rules, cfg, project, out, ref))
    print(f"elapsed   : {time.time() - t0:.1f}s")
    return worst


def _write_group(args, networks, tk, drawing, cls, reports, al_files, template, rules, cfg, project, out, ref) -> int:
    tag = networks[0] if len(networks) == 1 else networks[0] + "".join("-" + n.split("-")[-1] for n in networks[1:])
    prefix = f"{project['number']}_{tag}" if project["number"] else tag
    bom_path = out / f"{prefix}_FINAL_BOM.xlsx"
    res = write_bom(template, bom_path, tk, rules, cfg, project)

    expected = {}
    for rule in rules:
        if rule.write and rule.key in res.rule_values:
            vals = [v for v, _n in res.rule_values[rule.key].values() if v is not None]
            expected[(rule.key,)] = sum(vals) if vals else None
    ver = verify(res, expected, out / ".work", recalc=not args.no_recalc)

    comp = None
    if ref is not None:
        comp = compare(rules, res, ref, tk)
        write_discrepancies(out / f"{prefix}_BOM_DISCREPANCIES.xlsx", comp, ref, tk)

    meta = {
        "Generated": dt.datetime.now().isoformat(timespec="seconds"),
        "Tool version": __version__,
        "Drawing": str(args.dwg),
        "CAD backend": drawing.backend,
        "Drawing units (INSUNITS)": drawing.header.get("INSUNITS"),
        "CAD reader warnings": "; ".join(drawing.warnings) or "none",
        "Address lists": ", ".join(str(p) for p in al_files) or "none",
        "Splice reports": f"{len(reports)} files",
        "Template": str(template),
        "Template area columns": ", ".join(res.columns.values()),
        "Template formulas repaired": "; ".join(res.formula_repairs) or "none",
        "Template formulas replaced by computed values": "; ".join(res.formulas_replaced) or "none",
        "Reference BOM": args.reference or "none (no independent reference - quantities are internally checked only)",
        "Networks": ", ".join(networks),
        "Network boundaries found": ", ".join(cls.networks) or "single-network drawing",
        "Non-Grant polygons": len(cls.nongrant),
        "Cable segments": len(tk.cables),
        "Writer issues": "; ".join(res.issues) or "none",
        "Reference constants cleared from template": len(res.cleared),
    }
    summary = write_audit(out / f"{prefix}_BOM_AUDIT.xlsx", tk, rules, res, ver,
                          meta | {"_census": dict(drawing.census), "_block_census": drawing.block_census},
                          cls, reports, ref, comp, res.template_rows)

    print(f"FINAL BOM : {bom_path}")
    print(f"AUDIT     : {out / f'{prefix}_BOM_AUDIT.xlsx'}")
    if comp is not None:
        cells = [x for x in comp if x["area"] != "TOTAL"]
        tots = [x for x in comp if x["area"] == "TOTAL"]
        print(f"DISCREP.  : {out / f'{prefix}_BOM_DISCREPANCIES.xlsx'}")
        print(f"reference : area cells {sum(x['status'] == 'MATCH' for x in cells)}/{len(cells)} match, "
              f"network totals {sum(x['status'] == 'MATCH' for x in tots)}/{len(tots)} match")
    if res.formula_repairs:
        print(f"template  : {len(res.formula_repairs)} inconsistent template formulas repaired (see audit)")
    print("coverage  : " + ", ".join(f"{k}={v}" for k, v in sorted(summary["coverage"].items())))
    nfail = sum(1 for c in tk.checks if c.status == "FAIL")
    print(f"checks    : engine FAIL={nfail} WARN={sum(1 for c in tk.checks if c.status == 'WARN')}; "
          f"workbook FAIL={len(ver.failed)} (recalculated={'yes' if ver.recalculated else 'NO'})")
    for c in tk.checks:
        if c.status == "FAIL":
            print(f"  FAIL {c.name}: {c.detail}")
    for c in ver.failed:
        print(f"  FAIL {c[0]}: {c[2]}")
    return 1 if ver.failed else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="fttx_bom", description="FTTx BOM automation: DWG + address list + splice reports -> BOM")
    p.add_argument("--dwg", required=True, help="design drawing (.dwg, .dxf, or converter .json)")
    p.add_argument("--address-list", nargs="*", default=[], help="address list .xlsx files or folders")
    p.add_argument("--splice-reports", nargs="*", default=[], help="splice report .xlsx files or folders")
    p.add_argument("--template", required=True, help="approved BOM template workbook")
    p.add_argument("--out", required=True, help="output folder")
    p.add_argument("--reference", help="completed BOM to reconcile against (optional)")
    p.add_argument("--networks", help="comma separated network names (default: address-list sheet names)")
    p.add_argument("--project-name")
    p.add_argument("--project-number")
    p.add_argument("--system", help="e.g. 'Capital West' (template B1 list)")
    p.add_argument("--rules", help="alternative rule catalogue JSON")
    p.add_argument("--conventions", help="alternative CAD conventions JSON")
    p.add_argument("--cache", help="DWG conversion cache folder")
    p.add_argument("--no-recalc", action="store_true", help="skip LibreOffice formula recalculation")
    p.add_argument("--version", action="version", version=__version__)
    args = p.parse_args(argv)
    try:
        return run(args)
    except (ExtractionError, FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
