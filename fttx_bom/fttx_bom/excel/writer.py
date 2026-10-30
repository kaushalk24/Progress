"""Populate the approved BOM template (OLM SF-8M BOM layout).

Only quantity cells in the Grant/Non-Grant columns, the header text and the
per-area inputs of the Jumper Calculator / Transport BOM sheets are written.
Part numbers, descriptions, G/F-column formulas, template formulas
(e.g. bonding jumpers = peds x 2), formatting, comments and external links are
left untouched. Reference-project constants (typed numbers or constant-only
formulas such as '=3+1') in the area columns are cleared so no stale value
from the reference job can leak into a new BOM.
"""
from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl
from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from ..engine.network import GRANT
from ..engine.rules import Rule, evaluate
from ..engine.takeoff import Takeoff

CONST_FORMULA = re.compile(r"^=[\d\.\s\+\-\*/\(\)]+$")


def norm(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower()) if s is not None else ""


LABEL_ALIASES = {norm("Residential Count"): [norm("Residental Count")]}


@dataclass
class WriteResult:
    path: Path
    sheet: str
    columns: dict[tuple[str, str], str] = field(default_factory=dict)  # (net, area) -> column letter
    rows: dict[str, int] = field(default_factory=dict)  # rule key -> row
    written: dict[tuple[str, str], float | None] = field(default_factory=dict)  # (rule key, col letter) -> value
    cleared: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    rule_values: dict[str, dict[tuple[str, str], tuple[float | None, str]]] = field(default_factory=dict)
    template_sheets: list[str] = field(default_factory=list)
    template_snapshot: dict[str, object] = field(default_factory=dict)  # B..G cells below the header
    template_rows: list[tuple[int, str, str]] = field(default_factory=list)


def area_label(net: str, area: str) -> str:
    return f"{net} {'Grant' if area == GRANT else 'Non Grant'}"


def find_rows(ws, rules: list[Rule], header_row: int) -> tuple[dict[str, int], list[str]]:
    by_part: dict[str, int] = {}
    by_label: dict[str, int] = {}
    for r in range(header_row + 1, ws.max_row + 1):
        b = ws.cell(r, 2).value
        if isinstance(b, str) and b.strip():
            if b.strip().startswith("="):
                continue
            by_part.setdefault(b.strip().upper(), r)
            by_label.setdefault(norm(b), r)
    rows, issues = {}, []
    for rule in rules:
        if rule.part:
            r = by_part.get(rule.part.upper())
        else:
            r = by_label.get(norm(rule.label))
            for alias in LABEL_ALIASES.get(norm(rule.label), []):
                r = r or by_label.get(alias)
        if r is None:
            issues.append(f"template row not found for rule '{rule.key}'")
        else:
            rows[rule.key] = r
    return rows, issues


def write_bom(template: Path, out: Path, tk: Takeoff, rules: list[Rule], cfg: dict, project: dict) -> WriteResult:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(template, keep_links=True)
    sheet = cfg["sheet"]
    if sheet not in wb.sheetnames:
        raise ValueError(f"template has no sheet '{sheet}' (sheets: {wb.sheetnames})")
    ws = wb[sheet]
    res = WriteResult(out, sheet)
    res.template_sheets = list(wb.sheetnames)

    header_row = next((r for r in range(1, 30) if str(ws.cell(r, 2).value or "").strip().lower() == "part number"), None)
    if header_row is None:
        raise ValueError("template header row ('Part Number' in column B) not found")
    c0 = column_index_from_string(cfg["first_data_col"])
    ncol = cfg["max_columns"]
    cols = tk.columns
    if len(cols) > ncol:
        raise ValueError(f"{len(tk.networks)} networks need {len(cols)} area columns; template has {ncol}. Run networks in groups of {ncol // 2}.")
    letters = [get_column_letter(c0 + i) for i in range(ncol)]
    res.columns = {col: letters[i] for i, col in enumerate(cols)}

    # header text
    ws.cell(1, 2).value = f"System: {project.get('system', '')}".rstrip() if project.get("system") else "System: "
    ws.cell(2, 2).value = f"Project: {project.get('name', '')}"
    ws.cell(4, 2).value = f"Project Number: {project.get('number', '')}"
    for i, L in enumerate(letters):
        ws[f"{L}{header_row}"].value = area_label(*cols[i]) if i < len(cols) else None

    for r in range(header_row + 1, ws.max_row + 1):
        for c in "BCDEFG":
            v = ws[f"{c}{r}"].value
            if v is not None:
                res.template_snapshot[f"{c}{r}"] = v
    from .reports import template_material_rows

    res.template_rows = template_material_rows(ws)
    rows, issues = find_rows(ws, rules, header_row)
    res.rows, res.issues = rows, issues
    rule_rows = set(rows.values())

    # clear reference-project constants everywhere in the area columns, keep formulas that reference cells
    for r in range(header_row + 1, ws.max_row + 1):
        for L in letters:
            cell = ws[f"{L}{r}"]
            v = cell.value
            if v is None:
                continue
            is_const = isinstance(v, (int, float)) or (isinstance(v, str) and CONST_FORMULA.match(v.replace(" ", "")))
            if is_const and r not in rule_rows:
                res.cleared.append(f"{L}{r}={v!r}")
                cell.value = None

    for rule in rules:
        r = rows.get(rule.key)
        if r is None or rule.status == "TEMPLATE_FORMULA":
            continue
        vals = {}
        for i, L in enumerate(letters):
            cell = ws[f"{L}{r}"]
            if i >= len(cols):
                cell.value = None
                continue
            net, area = cols[i]
            v, note = evaluate(rule, tk, net, area)
            vals[(net, area)] = (v, note)
            if rule.write and v is not None:
                cell.value = int(v) if float(v).is_integer() else v
            else:
                if cell.value is not None:
                    res.cleared.append(f"{L}{r}={cell.value!r} ({rule.status})")
                cell.value = None
            res.written[(rule.key, L)] = cell.value
        res.rule_values[rule.key] = vals

    _write_transport(wb, tk, cfg, cols, res)
    _write_jumpers(wb, tk, cfg, cols, res)
    _restore_validation(wb)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return res


def _write_transport(wb, tk, cfg, cols, res):
    t = cfg.get("transport_sheet")
    if not t or t["sheet"] not in wb.sheetnames:
        res.issues.append("transport sheet missing in template")
        return
    ws = wb[t["sheet"]]
    hr = t["header_row"]
    start = next((c for c in range(1, 30) if str(ws.cell(hr, c).value or "").strip().lower() == "total quantity"), None)
    if start is None:
        res.issues.append("Transport BOM header 'Total Quantity' not found")
        return
    first = start + 1
    for i in range(8):
        ws.cell(hr, first + i).value = area_label(*cols[i]) if i < len(cols) else None
    parts = {p.upper() for p in t["rows_per_olm"]}
    for r in range(hr + 1, ws.max_row + 1):
        b = str(ws.cell(r, 2).value or "").strip().upper()
        if b in parts:
            for i in range(8):
                c = ws.cell(r, first + i)
                c.value = int(tk.get(t["value"], *cols[i], 0)) if i < len(cols) else None


def _write_jumpers(wb, tk, cfg, cols, res):
    j = cfg.get("jumper_sheet")
    if not j or j["sheet"] not in wb.sheetnames:
        res.issues.append("jumper sheet missing in template")
        return
    ws = wb[j["sheet"]]
    lc = column_index_from_string(j["label_col"])
    for i in range(j["blocks"]):
        r = j["first_label_row"] + i * j["block_rows"]
        label_cell = ws.cell(r, lc)
        houses = ws.cell(r + j["houses_offset"], lc)
        if not str(label_cell.value or "").strip() or "cabinet" in str(label_cell.value).lower():
            res.issues.append(f"Jumper Calculator block {i + 1} at row {r} has unexpected label {label_cell.value!r}")
            continue
        if i < len(cols):
            net, area = cols[i]
            label_cell.value = f"{net} {'Grant' if area == GRANT else 'Non-Grant'}"
            houses.value = int(tk.get("passings", net, area, 0))
        else:
            label_cell.value = "(unused)"
            houses.value = 0


def _restore_validation(wb):
    """openpyxl drops the x14 list validation on B1 ('System:' picker); re-add it."""
    if "Sheet1" not in wb.sheetnames:
        return
    for name in ("Cabinet OLT BOM", "OLM SF-8M BOM"):
        if name in wb.sheetnames:
            ws = wb[name]
            dv = DataValidation(type="list", formula1="Sheet1!$A$1:$A$5", allow_blank=True,
                                showErrorMessage=True, error="Please select from list")
            dv.add("B1")
            ws.add_data_validation(dv)
