"""End-to-end run: inputs -> address-list workbooks, review worklists, exception reports."""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import __version__
from .builder import Builder, OlmResult
from .compare import compare
from .config import load_config, resolve_tool_path
from .model import Issue
from .network import Network
from .overrides import apply_overrides, load_overrides, review_worklist
from .splice_reports import load_reports
from .workbook import write_workbook


class InputError(Exception):
    pass


@dataclass
class RunOutcome:
    olm: str
    workbook: Path | None
    final: bool
    counts: dict
    errors: int
    warnings: int
    worklist: Path | None = None
    exceptions_csv: Path | None = None
    reports_to_request: Path | None = None
    comparison: dict | None = None
    messages: list[str] = field(default_factory=list)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_report_files(folder: Path) -> list[Path]:
    if not folder.exists():
        raise InputError(f"Splice report folder not found: {folder}")
    if folder.is_file():
        return [folder]
    files = sorted(p for p in folder.rglob("*.xlsx") if not p.name.startswith("~$"))
    if not files:
        raise InputError(f"No .xlsx splice reports found in {folder}")
    return files


def unique_path(path: Path) -> Path:
    """Never overwrite: add ' (2)', ' (3)' ... when the file exists."""
    if not path.exists():
        return path
    n = 2
    while True:
        cand = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not cand.exists():
            return cand
        n += 1


def _write_csv(path: Path, rows: list[dict], columns: list[str]):
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def run(reports: str | Path, out_dir: str | Path, olms: list[str] | None = None, config: str | Path | None = None,
        overrides: str | Path | None = None, prefix: str | None = None, reference: str | Path | None = None,
        drawing: str | Path | None = None, template: str | Path | None = None, log=print) -> list[RunOutcome]:
    cfg = load_config(config)
    if template:
        cfg["template"]["path"] = str(template)
    if prefix is not None:
        cfg["project"]["name_prefix"] = prefix
    reports = Path(reports)
    out_dir = Path(out_dir)
    files = find_report_files(reports)
    inputs_resolved = {p.resolve() for p in files}
    if out_dir.resolve() in {p.parent for p in inputs_resolved}:
        log("Note: output folder is an input folder; existing files are never overwritten.")
    out_dir.mkdir(parents=True, exist_ok=True)

    log(f"Reading {len(files)} splice report(s) from {reports}")
    reps, load_issues = load_reports(files, cfg)
    net = Network(reps, cfg)
    global_issues = load_issues + net.issues
    found = net.olms()
    targets = olms or found
    if not targets:
        raise InputError("No OLM found: no splice report has a segment to an 'OLM Housing'. "
                         "Supply the hub closure report(s).")
    log(f"OLMs found: {', '.join(found) or 'none'}; generating: {', '.join(targets)}")

    ov_rows, ov_issues = ([], [])
    if overrides or cfg.get("overrides", {}).get("path"):
        ov_path = Path(overrides) if overrides else resolve_tool_path(cfg["overrides"]["path"])
        ov_rows, ov_issues = load_overrides(ov_path)
        log(f"Overrides: {len(ov_rows)} row(s) from {ov_path}")

    inventory = None
    if drawing:
        from .drawing import read_drawing_inventory
        inventory, d_issues = read_drawing_inventory(Path(drawing), cfg)
        global_issues += d_issues
        if inventory:
            log(f"Drawing: {inventory['source']} - {len(inventory['closures'])} closure ids, "
                f"{len(inventory['cables'])} cable names found ({inventory['method']})")

    run_at = dt.datetime.now().isoformat(timespec="seconds")
    input_meta = []
    for rep in reps:
        input_meta.append({"file": str(rep.path.relative_to(reports) if reports.is_dir() else rep.path.name),
                           "format": rep.fmt, "closure": rep.closure,
                           "prepared_on": str(rep.header.get("prepared_on") or rep.header.get("date_created") or ""),
                           "sha256": sha256(rep.path), "bytes": rep.path.stat().st_size})
    if drawing:
        input_meta.append({"file": Path(drawing).name, "format": "drawing", "closure": "", "prepared_on": "",
                           "sha256": sha256(Path(drawing)), "bytes": Path(drawing).stat().st_size})

    outcomes, results, comparisons = [], [], []
    for olm in targets:
        res: OlmResult = Builder(net, cfg).build(olm)
        res.issues = _relevant_issues(global_issues, res) + res.issues
        if ov_rows or ov_issues:
            res.issues += ov_issues + apply_overrides(res, ov_rows)
        cross = None
        if inventory is not None:
            from .drawing import crosscheck
            cross, x_issues = crosscheck(res, inventory)
            res.issues += x_issues
        name = cfg["project"]["output_filename"].format(prefix=cfg["project"]["name_prefix"], olm=olm).lstrip("_ ")
        out = out_dir / name
        if not res.is_final:
            out = out.with_name(out.stem + cfg["project"]["draft_suffix"] + out.suffix)
        out = unique_path(out)
        if out.resolve() in inputs_resolved:
            raise InputError(f"Refusing to overwrite an input file: {out}")
        info = {"run_at": run_at, "inputs": input_meta, "overrides": str(overrides) if overrides else None,
                "template": cfg["template"].get("path")}
        oc = RunOutcome(olm, None, res.is_final, res.counts, len(res.errors),
                        sum(1 for i in res.issues if i.severity == "WARNING"))
        if not res.rows:
            oc.messages.append("No rows generated - see exceptions")
            log(f"{olm}: FAILED - no rows generated ({'; '.join(i.message for i in res.errors[:3])})")
        else:
            write_workbook(res, cfg, out, info, cross)
            oc.workbook = out
        stem = (out.stem if res.rows else f"{olm}_FAILED")
        wl = review_worklist(res)
        oc.worklist = unique_path(out_dir / f"{stem}_review_worklist.csv")
        _write_csv(oc.worklist, wl, ["olm", "cable_name", "fiber_no", "field", "action", "value", "approved_by",
                                     "approved_on", "reason", "expected_generated", "status", "rule_code", "address",
                                     "why_review"])
        need = {}
        for r in res.rows:
            for c in r.needs_reports:
                e = need.setdefault(c, {"closure": c, "rows_affected": 0, "example_addresses": []})
                e["rows_affected"] += 1
                if len(e["example_addresses"]) < 3 and r.value("address"):
                    e["example_addresses"].append(str(r.value("address")))
        req = sorted(need.values(), key=lambda e: (-e["rows_affected"], e["closure"]))
        for e in req:
            e["example_addresses"] = "; ".join(e["example_addresses"])
        oc.reports_to_request = unique_path(out_dir / f"{stem}_splice_reports_to_request.csv")
        _write_csv(oc.reports_to_request, req, ["closure", "rows_affected", "example_addresses"])
        oc.exceptions_csv = unique_path(out_dir / f"{stem}_exceptions.csv")
        _write_csv(oc.exceptions_csv, [asdict(i) for i in res.issues],
                   ["severity", "code", "olm", "cable", "fiber", "message", "source"])
        if reference:
            ref = _find_reference(Path(reference), olm)
            if ref:
                cmpr = compare(res, ref, cfg)
                comparisons.append(cmpr)
                oc.comparison = _comparison_summary(cmpr)
                log(f"{olm}: compared with {ref.name}: {cmpr.matched}/{cmpr.ref_rows} rows matched")
        manifest = {"tool_version": __version__, "run_at": run_at, "olm": olm, "hub": res.hub,
                    "final": res.is_final, "counts": res.counts, "errors": oc.errors, "warnings": oc.warnings,
                    "workbook": str(oc.workbook) if oc.workbook else None, "config": cfg.get("_source"),
                    "accepted_rules": cfg.get("approvals", {}).get("accepted_rules", []),
                    "inputs": input_meta, "comparison": oc.comparison}
        with open(unique_path(out_dir / f"{stem}_run_manifest.json"), "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2, default=str)
        c = res.counts
        log(f"{olm}: {'FINAL' if res.is_final else 'DRAFT (review required)'} - {len(res.rows)} rows: "
            f"{c['CONFIRMED']} confirmed, {c['APPROVED']} approved, {c['PROVISIONAL']} provisional, "
            f"{c['UNRESOLVED']} unresolved; {oc.errors} error(s). -> {oc.workbook.name if oc.workbook else 'no workbook'}")
        outcomes.append(oc)
        results.append(res)
    if comparisons:
        from .compare import write_comparison_workbook
        cp = write_comparison_workbook(comparisons, unique_path(out_dir / "comparison_with_reference.xlsx"))
        log(f"Comparison workbook: {cp.name}")
    if inventory is not None and inventory.get("addresses") is not None:
        from .drawing import address_coverage
        rows, iss = address_coverage(results, inventory)
        cov = unique_path(out_dir / "drawing_address_coverage.csv")
        _write_csv(cov, rows, ["check", "identifier", "found"])
        for i in iss:
            log(f"Drawing address coverage: {i.message} -> {cov.name}")
    return outcomes


def _relevant_issues(global_issues: list[Issue], res: OlmResult) -> list[Issue]:
    """Report-level issues that concern this OLM: those on files used as evidence for its rows,
    plus unreadable/duplicate reports (they may hide connectivity for any OLM)."""
    used = set()
    for r in res.rows:
        for fv in r.fields.values():
            for e in fv.evidence:
                used.add(e.split(" row ")[0])
    out = []
    for i in global_issues:
        src = (i.source or "").split(" row ")[0]
        if not src or src in used or i.code in ("REPORT_UNREADABLE", "DUPLICATE_REPORT") or i.code.startswith("DRAWING"):
            out.append(i)
    return out


def _find_reference(ref: Path, olm: str) -> Path | None:
    if ref.is_file():
        return ref
    hits = sorted(p for p in ref.rglob("*.xlsx") if olm in p.name and not p.name.startswith("~$"))
    return hits[0] if hits else None


def _comparison_summary(c) -> dict:
    return {"reference": c.reference, "ref_rows": c.ref_rows, "gen_rows": c.gen_rows, "matched": c.matched,
            "only_generated": len(c.only_generated), "only_reference": len(c.only_reference),
            "order_identical": c.order_identical, "field_stats": c.field_stats,
            "substantive_diffs": sum(1 for d in c.diffs if d.kind == "substantive"),
            "cosmetic_diffs": sum(1 for d in c.diffs if d.kind == "cosmetic")}


def run_batch(jobs_csv: str | Path, log=print) -> list[RunOutcome]:
    """jobs CSV columns: reports, out_dir, olm (optional, ';' separated), config, overrides, prefix,
    reference, drawing. Relative paths are resolved against the CSV's folder."""
    jobs_csv = Path(jobs_csv)
    base = jobs_csv.parent
    outcomes = []
    with open(jobs_csv, newline="", encoding="utf-8-sig") as fh:
        for n, job in enumerate(csv.DictReader(fh), start=2):
            job = {k.strip().lower(): (v or "").strip() for k, v in job.items() if k}
            if not job.get("reports"):
                continue

            def p(key):
                v = job.get(key)
                return (base / v) if v and not Path(v).is_absolute() else (Path(v) if v else None)
            log(f"--- job line {n}: {job.get('reports')}")
            try:
                outcomes += run(p("reports"), p("out_dir") or base / "output",
                                [o for o in job.get("olm", "").split(";") if o] or None, p("config"),
                                p("overrides"), job.get("prefix") or None, p("reference"), p("drawing"), log=log)
            except Exception as exc:  # keep going with the next job
                log(f"job line {n} FAILED: {exc}")
                outcomes.append(RunOutcome(job.get("olm") or "?", None, False, {}, 1, 0, messages=[str(exc)]))
    return outcomes
