"""One BOM job end to end: inputs -> takeoff -> policies -> BOM -> verification -> deep check -> audit.

Shared by the command line, the batch runner and the app.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import __version__
from .engine import policies as pol
from .engine.doctor import Issue, run_doctor, write_issue_files
from .engine.network import build_classifier
from .engine.rules import CONFIG_DIR, load_rules
from .engine.takeoff import build_takeoff
from .excel.reports import compare, read_reference, write_audit, write_discrepancies
from .excel.verify import verify
from .excel.confidence import assess
from .excel.writer import template_capacity, write_bom
from .extract.backends import load_drawing
from .inputs.address_list import read_address_lists
from .inputs.splice_reports import read_splice_reports


@dataclass
class JobParams:
    dwg: Path
    address_lists: list[Path]
    splice_reports: list[Path]
    template: Path
    out: Path
    reference: Path | None = None
    networks: list[str] | None = None
    project_name: str | None = None
    project_number: str | None = None
    system: str = ""
    policies: Path | None = None
    learn: bool = False
    recalc: bool = True
    cache: Path | None = None
    rules: Path | None = None
    conventions: Path | None = None


@dataclass
class GroupResult:
    networks: list[str]
    bom: Path
    audit: Path
    discrepancies: Path | None
    issues_csv: Path
    issues_scr: Path
    issues: list[Issue]
    coverage: dict
    workbook_failures: list
    recalculated: bool
    ref_cells: tuple[int, int] | None = None  # (matched, compared)
    ref_totals: tuple[int, int] | None = None


@dataclass
class JobResult:
    params: JobParams
    networks: list[str] = field(default_factory=list)
    groups: list[GroupResult] = field(default_factory=list)
    calibration: list[dict] | None = None
    learned: dict | None = None
    policies_used: dict = field(default_factory=dict)
    totals: dict = field(default_factory=dict)  # key -> {network: total}
    elapsed: float = 0.0

    @property
    def exit_code(self) -> int:
        return 1 if any(g.workbook_failures for g in self.groups) else 0

    @property
    def issue_counts(self) -> Counter:
        c = Counter()
        for g in self.groups:
            c.update(i.severity for i in g.issues)
        return c


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


SUMMARY_KEYS = ["passings", "pass_res", "pass_com", "pass_mdu", "ped_max10", "ped_max5", "vault", "olm",
                "cable_024", "cable_048", "cable_072", "cable_096", "cable_144", "fosc450b", "fosc450d",
                "tray_450b", "tray_450d", "splitter_1x32", "splitter_1x64", "pon_ports", "drop_ft_bom", "route_ug_ft"]


def run_job(p: JobParams, log: Callable[[str], None] = print) -> JobResult:
    t0 = time.time()
    p.out.mkdir(parents=True, exist_ok=True)
    conv = json.loads((p.conventions or CONFIG_DIR / "conventions.json").read_text())
    cfg, rules = load_rules(p.rules)
    if not p.template.exists():
        raise FileNotFoundError(f"template not found: {p.template}")
    skipped: list[str] = []
    address_lists = read_address_lists(p.address_lists, skipped) if p.address_lists else {}
    for msg in skipped:
        log(f"NOTE: {msg}")
    report_errors: list[str] = []
    reports = read_splice_reports(p.splice_reports, report_errors) if p.splice_reports else []
    for msg in report_errors:
        log(f"WARNING: splice report not read: {msg}")
    networks = p.networks or sorted(address_lists)
    if not networks:
        raise ValueError("no networks: supply address lists (their sheet names are the network names) or --networks")
    for n in networks:
        if n not in address_lists:
            log(f"WARNING: no address list for {n}")

    log(f"reading drawing {p.dwg.name} ...")
    drawing = load_drawing(p.dwg, p.cache or p.out / ".cache")
    cls = build_classifier(drawing, conv, networks)
    selection = pol.load_selection(p.policies)
    tk = build_takeoff(drawing, conv, cls, networks, address_lists, reports, policies=selection)
    for msg in report_errors:
        tk.check("splice report unreadable", False, f"{msg} - its enclosure, splices and couplers are NOT counted")
    for r in reports:
        for msg in r.issues:
            tk.check("splice report cell", False, f"{r.name}: {msg}", warn=True)

    proj = project_from_filename(p.dwg.name)
    project = {"name": p.project_name or proj["name"], "number": p.project_number or proj["number"], "system": p.system or ""}
    res_job = JobResult(params=p, networks=networks)
    n_area = template_capacity(p.template, cfg)  # main sheet, Transport BOM and Jumper Calculator must all fit
    groups = [networks] if len(networks) * 2 <= n_area else [[n] for n in networks]
    if len(groups) > 1:
        log(f"template holds {n_area} area columns (main / Transport / Jumper): writing one BOM per OLM ({len(networks)} files)")
    ref = read_reference(p.reference, cfg["sheet"], rules) if p.reference else None
    if ref is not None:
        res_job.calibration = pol.calibrate(tk, rules, ref)
        if p.learn:
            job = f"{project['number']} {' '.join(networks)}".strip()
            res_job.learned = pol.learn(res_job.calibration, job, p.policies)
            log(f"learned policies saved: {res_job.learned}")
            pol.apply(tk, res_job.learned)
            for r in res_job.calibration:
                r["selected"] = tk.policy_used.get(r["policy"]) == r["option"]
    elif p.learn:
        log("WARNING: learning needs an approved (completed) BOM as reference - nothing learned")
    tk.extra["calibration"] = res_job.calibration
    res_job.policies_used = dict(tk.policy_used)
    res_job.totals = {k: {n: tk.total(k, n) for n in networks} for k in SUMMARY_KEYS if any(kk == k for kk, _n, _a in tk.q)}

    for group in groups:
        res_job.groups.append(_write_group(p, group, tk.subset(group), drawing, cls, reports, rules, cfg, project, ref, conv,
                                           address_lists, log))
    res_job.elapsed = time.time() - t0
    return res_job


def _write_group(p: JobParams, networks, tk, drawing, cls, reports, rules, cfg, project, ref, conv, address_lists, log) -> GroupResult:
    tag = networks[0] if len(networks) == 1 else networks[0] + "".join("-" + n.split("-")[-1] for n in networks[1:])
    prefix = f"{project['number']}_{tag}" if project["number"] else tag
    out = p.out
    bom_path = out / f"{prefix}_FINAL_BOM.xlsx"
    log(f"writing {bom_path.name} ...")
    # confidence of every quantity cell (design check without the workbook-level checks), highlighted in the BOM
    pre = run_doctor(drawing, conv, cls, tk, address_lists, reports)
    flags = assess(rules, tk, pre, address_lists, reports)
    res = write_bom(p.template, bom_path, tk, rules, cfg, project, flags)
    expected = {}
    for rule in rules:
        if rule.write and rule.key in res.rule_values:
            vals = [v for v, _n in res.rule_values[rule.key].values() if v is not None]
            expected[(rule.key,)] = sum(vals) if vals else None
    log("verifying workbook" + (" (LibreOffice recalculation) ..." if p.recalc else " ..."))
    ver = verify(res, expected, out / ".work", recalc=p.recalc)
    comp = None
    disc_path = None
    if ref is not None:
        comp = compare(rules, res, ref, tk)
        disc_path = out / f"{prefix}_BOM_DISCREPANCIES.xlsx"
        write_discrepancies(disc_path, comp, ref, tk)
    issues = run_doctor(drawing, conv, cls, tk, address_lists, reports, res, ver)
    csv_path, scr_path = write_issue_files(issues, out / prefix)
    meta = {
        "Generated": dt.datetime.now().isoformat(timespec="seconds"),
        "Tool version": __version__,
        "Drawing": str(p.dwg),
        "CAD backend": drawing.backend,
        "Drawing units (INSUNITS)": drawing.header.get("INSUNITS"),
        "CAD reader warnings": "; ".join(drawing.warnings) or "none",
        "Address lists": ", ".join(str(x) for x in p.address_lists) or "none",
        "Splice reports": f"{len(reports)} files",
        "Template": str(p.template),
        "Template area columns": ", ".join(res.columns.values()),
        "Template formulas repaired": "; ".join(res.formula_repairs) or "none",
        "Template formulas replaced by computed values": "; ".join(res.formulas_replaced) or "none",
        "Reference BOM": str(p.reference) if p.reference else "none (no independent reference - quantities are internally checked only)",
        "Networks": ", ".join(networks),
        "Network boundaries found": ", ".join(cls.networks) or "single-network drawing",
        "Non-Grant polygons": len(cls.nongrant),
        "Cable segments": len(tk.cables),
        "Writer issues": "; ".join(res.issues) or "none",
        "Reference constants cleared from template": len(res.cleared),
    }
    audit_path = out / f"{prefix}_BOM_AUDIT.xlsx"
    summary = write_audit(audit_path, tk, rules, res, ver,
                          meta | {"_census": dict(drawing.census), "_block_census": drawing.block_census},
                          cls, reports, ref, comp, res.template_rows, issues)
    g = GroupResult(networks, bom_path, audit_path, disc_path, csv_path, scr_path, issues, summary["coverage"],
                    ver.failed, ver.recalculated)
    if comp is not None:
        cells = [x for x in comp if x["area"] != "TOTAL"]
        tots = [x for x in comp if x["area"] == "TOTAL"]
        g.ref_cells = (sum(x["status"] == "MATCH" for x in cells), len(cells))
        g.ref_totals = (sum(x["status"] == "MATCH" for x in tots), len(tots))
    return g
