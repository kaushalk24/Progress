"""Classify input files by content, so users can drop in everything at once.

Roles
  drawing        .dwg / .dxf
  address_list   .xlsx whose first sheet header has PON NAME ... ADDRESS
  splice_report  .xlsx starting with 'Splice Connections Report'
  bom_completed  BOM workbook (OLM SF-8M BOM sheet) with quantities filled in
  bom_template   BOM workbook with an empty OLM SF-8M BOM sheet
  unknown        anything else (reported, never silently used)
Zip files are extracted (safely) and their contents classified.
"""
from __future__ import annotations

import re
import shutil
import warnings
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

BOM_SHEET = "OLM SF-8M BOM"
GENERATED_MARK = "fttx_bom generated"  # workbook keyword written into every BOM this tool produces
GENERATED_NAME = re.compile(r"(_FINAL_BOM|_BOM_AUDIT|_BOM_DISCREPANCIES|^BATCH_SUMMARY)\.xlsx$", re.I)
ZIP_MAX_BYTES = 20 * 1024**3  # total uncompressed size accepted from one zip
ZIP_MAX_ENTRIES = 50_000
ZIP_MAX_RATIO = 200  # uncompressed / compressed per member (zip-bomb guard)


@dataclass
class Detected:
    drawings: list[Path] = field(default_factory=list)
    address_lists: list[Path] = field(default_factory=list)
    splice_reports: list[Path] = field(default_factory=list)
    bom_completed: list[Path] = field(default_factory=list)
    bom_templates: list[Path] = field(default_factory=list)
    unknown: list[tuple[Path, str]] = field(default_factory=list)

    def summary(self) -> dict[str, int]:
        return {"drawings": len(self.drawings), "address lists": len(self.address_lists),
                "splice reports": len(self.splice_reports), "completed BOMs": len(self.bom_completed),
                "BOM templates": len(self.bom_templates), "unrecognised": len(self.unknown)}


def safe_extract(zp: Path, dest: Path) -> Path:
    """Extract a zip without allowing paths outside `dest` (zip-slip), absolute paths, or zip bombs."""
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    with zipfile.ZipFile(zp) as z:
        infos = z.infolist()
        if len(infos) > ZIP_MAX_ENTRIES:
            raise ValueError(f"zip {zp.name} has {len(infos)} entries (limit {ZIP_MAX_ENTRIES})")
        if sum(i.file_size for i in infos) > ZIP_MAX_BYTES:
            raise ValueError(f"zip {zp.name} expands to more than {ZIP_MAX_BYTES // 1024**3} GB")
        for info in infos:
            if info.file_size > 10 * 1024**2 and info.compress_size and info.file_size / info.compress_size > ZIP_MAX_RATIO:
                raise ValueError(f"zip {zp.name}: {info.filename} compression ratio {info.file_size / info.compress_size:.0f}x looks like a zip bomb")
        for info in infos:
            target = (dest / info.filename).resolve()
            if root not in target.parents and target != root:
                raise ValueError(f"unsafe path in zip {zp.name}: {info.filename}")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
    return dest


def classify_xlsx(p: Path) -> str:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
    except Exception as exc:  # corrupt / password protected
        return f"unknown: cannot open ({exc.__class__.__name__})"
    try:
        if BOM_SHEET in wb.sheetnames:
            if GENERATED_MARK in (wb.properties.keywords or ""):
                return "unknown: a BOM produced by this tool - not used as template or approved BOM"
            return "bom_completed" if _bom_has_quantities(wb[BOM_SHEET]) else "bom_template"
        ws = wb.worksheets[0]
        rows = []
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for i, row in enumerate(ws.iter_rows(max_row=3, max_col=12, values_only=True)):
                rows.append([str(v).strip().upper() if v is not None else "" for v in row])
        first = rows[0] if rows else []
        if first and (first[0].startswith("SPLICE CONNECTIONS REPORT") or "FIBER OPTIC SPLICE GUIDE" in first[:3]):
            return "splice_report"
        if "PON NAME" in first and "ADDRESS" in first:
            return "address_list"
        return "unknown: spreadsheet not recognised"
    finally:
        wb.close()


def _bom_has_quantities(ws) -> bool:
    """Completed BOM = passings rows (Residential/Commercial/MDU) carry numbers in the area columns."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for row in ws.iter_rows(min_row=1, max_row=20, max_col=20, values_only=True):
            label = str(row[1] or "").strip().lower() if len(row) > 1 else ""
            if label.startswith(("residential count", "residental count")):
                return any(isinstance(v, (int, float)) and v for v in row[7:20])
    return False


def detect(paths: list[str | Path], extract_dir: Path, exclude: list[str | Path] = ()) -> Detected:
    """Classify every file under `paths`. Directories in `exclude` (the output folder) and files this
    tool generated are skipped, so a rerun never picks up its own FINAL_BOM as the approved BOM."""
    det = Detected()
    queue = [Path(p) for p in paths]
    skip = [Path(x).resolve() for x in exclude]
    seen = set()
    used_dest: set[Path] = set()
    while queue:
        p = queue.pop(0)
        if p.name.startswith(("~$", ".")) or p in seen:
            continue
        seen.add(p)
        rp = p.resolve()
        if any(rp == x or x in rp.parents for x in skip):
            continue
        if GENERATED_NAME.search(p.name):
            det.unknown.append((p, "output of a previous run - skipped"))
            continue
        if p.is_dir():
            queue += sorted(p.iterdir())
            continue
        suf = p.suffix.lower()
        if suf in (".dwg", ".dxf"):
            det.drawings.append(p)
        elif suf == ".zip":
            dest = extract_dir / p.stem
            n = 1
            while dest in used_dest or (dest.exists() and any(dest.iterdir())):
                n += 1
                dest = extract_dir / f"{p.stem}_{n}"  # two zips with the same name must not merge
            used_dest.add(dest)
            try:
                safe_extract(p, dest)
                queue.append(dest)
            except (zipfile.BadZipFile, ValueError) as exc:
                det.unknown.append((p, f"zip not extracted: {exc}"))
        elif suf in (".xlsx", ".xlsm"):
            role = classify_xlsx(p)
            if role == "address_list":
                det.address_lists.append(p)
            elif role == "splice_report":
                det.splice_reports.append(p)
            elif role == "bom_completed":
                det.bom_completed.append(p)
            elif role == "bom_template":
                det.bom_templates.append(p)
            else:
                det.unknown.append((p, role.split(":", 1)[-1].strip()))
        else:
            det.unknown.append((p, f"file type {suf or '(none)'} not used"))
    return det


def discover_jobs(root: Path) -> list[Path]:
    """Batch layout: every sub-folder of `root` holding a drawing is one job (one drawing per job)."""
    jobs = []
    for sub in sorted(x for x in root.iterdir() if x.is_dir() and not x.name.startswith(".")):
        if any(f.suffix.lower() in (".dwg", ".dxf", ".zip") for f in sub.rglob("*")):
            jobs.append(sub)
    if not jobs and any(f.suffix.lower() in (".dwg", ".dxf") for f in root.iterdir()):
        jobs.append(root)
    return jobs
