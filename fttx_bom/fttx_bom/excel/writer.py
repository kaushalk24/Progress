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
from openpyxl.formula.translate import Translator
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
    formula_repairs: list[str] = field(default_factory=list)
    formulas_replaced: list[str] = field(default_factory=list)


def area_label(net: str, area: str) -> str:
    return f"{net} {'Grant' if area == GRANT else 'Non Grant'}"


def area_columns(ws, header_row: int, first_col: int, max_scan: int = 24) -> list[str]:
    """Area (Grant / Non-Grant) column letters = the contiguous non-empty header cells after
    'Total Quantity' (the Credit River workbook has 8, the blank per-OLM template has 4)."""
    out = []
    for c in range(first_col, first_col + max_scan):
        v = ws.cell(header_row, c).value
        if v is None or not str(v).strip():
            break
        out.append(get_column_letter(c))
    return out


def template_area_count(template: Path, sheet: str) -> int:
    """Number of area columns in the template, read cheaply (read-only, header rows only)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(template, read_only=True)
        rows = list(wb[sheet].iter_rows(min_row=1, max_row=30, max_col=40, values_only=True))
        wb.close()
    for row in rows:
        vals = [str(v or "").strip() for v in row]
        if len(vals) > 1 and vals[1].lower() == "part number" and "total quantity" in [v.lower() for v in vals]:
            i = [v.lower() for v in vals].index("total quantity") + 1
            n = 0
            while i < len(vals) and vals[i]:
                n, i = n + 1, i + 1
            return n
    raise ValueError(f"header row with 'Part Number' / 'Total Quantity' not found in {sheet}")


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
    letters = area_columns(ws, header_row, c0)
    if not letters:
        raise ValueError("no area columns found after 'Total Quantity' in the template header")
    cols = tk.columns
    if len(cols) > len(letters):
        raise ValueError(f"{len(tk.networks)} networks need {len(cols)} area columns; template has {len(letters)}. "
                         f"Run one OLM per BOM (the CLI does this automatically).")
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

    # template formulas in the area columns must be the same formula shifted per column; the blank
    # per-OLM template has e.g. I28 =SUM(I21:I22) where H28 =SUM(H19:H20)*2 - repair from the first column
    for rule in rules:
        r = rows.get(rule.key)
        if r is None or rule.status != "TEMPLATE_FORMULA":
            continue
        base = ws[f"{letters[0]}{r}"].value
        if not (isinstance(base, str) and base.startswith("=")):
            continue
        for L in letters[1:]:
            want = Translator(base, origin=f"{letters[0]}{r}").translate_formula(f"{L}{r}")
            cell = ws[f"{L}{r}"]
            if cell.value != want:
                res.formula_repairs.append(f"{rule.key} {L}{r}: {cell.value!r} -> {want!r}")
                cell.value = want

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
                if isinstance(cell.value, str) and cell.value.startswith("=") and not CONST_FORMULA.match(cell.value.replace(" ", "")):
                    res.formulas_replaced.append(f"{rule.key} {L}{r}: template {cell.value} -> {v:g}")
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
    letters = area_columns(ws, hr, first)
    if len(letters) < len(cols):
        res.issues.append(f"Transport BOM has {len(letters)} area columns for {len(cols)} needed - extra columns not written")
    for i, L in enumerate(letters):
        ws[f"{L}{hr}"].value = area_label(*cols[i]) if i < len(cols) else ws[f"{L}{hr}"].value
    parts = {p.upper() for p in t["rows_per_olm"]}
    for r in range(hr + 1, ws.max_row + 1):
        b = str(ws.cell(r, 2).value or "").strip().upper()
        if b in parts:
            for i, L in enumerate(letters):
                ws[f"{L}{r}"].value = int(tk.get(t["value"], *cols[i], 0)) if i < len(cols) else None


def _write_jumpers(wb, tk, cfg, cols, res):
    """Jumper Calculator: one block per area column. Blocks are found by their 'Splitters Required'
    header (column C); the label is the row above, the houses-passed cell (column B) the row below."""
    j = cfg.get("jumper_sheet")
    if not j or j["sheet"] not in wb.sheetnames:
        res.issues.append("jumper sheet missing in template")
        return
    ws = wb[j["sheet"]]
    blocks = [r for r in range(1, ws.max_row + 1) if str(ws.cell(r, 3).value or "").strip().lower() == "splitters required"]
    if len(blocks) < len(cols):
        res.issues.append(f"Jumper Calculator has {len(blocks)} blocks for {len(cols)} area columns")
    for i, hr in enumerate(blocks):
        label_cell, houses = ws.cell(hr - 1, 2), ws.cell(hr + 1, 2)
        if i < len(cols):
            net, area = cols[i]
            label_cell.value = f"{net} {'Grant' if area == GRANT else 'Non-Grant'}"
            houses.value = int(tk.get("passings", net, area, 0))
        elif isinstance(houses.value, (int, float)) and houses.value:
            res.cleared.append(f"Jumper Calculator B{hr + 1}={houses.value!r} (unused block)")
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
