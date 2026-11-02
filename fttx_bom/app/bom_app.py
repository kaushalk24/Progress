"""FTTx BOM Tool - local application.

Start:  python -m fttx_bom app     (Windows: the FTTx BOM Tool desktop app, or windows\\run_app.bat)
Everything runs on this computer; no file leaves it.

Pages
  New BOM            1 inputs (upload or folders, detected-file table, project) -> 2 generate -> 3 results
  Batch              one BOM set per job folder + summary
  Design standards   how every BOM line is derived
  Settings           conventions that the drawing cannot settle
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fttx_bom import __version__  # noqa: E402
from fttx_bom.engine import policies as pol  # noqa: E402
from fttx_bom.engine.rules import load_rules  # noqa: E402
from fttx_bom.inputs.detect import detect  # noqa: E402
from fttx_bom.jobs import params_from_detected, run_batch  # noqa: E402
from fttx_bom.paths import bundle_root, jobs_dir, soffice_exe  # noqa: E402
from fttx_bom.pipeline import project_from_filename, run_job  # noqa: E402
from fttx_bom.views import LEVEL, SHOW, bom_preview, fmt_qty, network_summary  # noqa: E402

WORK = jobs_dir()
SYSTEMS = ["", "Coastal West", "Coastal East", "Capital West", "Capital East"]
SEVERITY = {"ERROR": "● Error", "WARN": "● Warning", "INFO": "● Info"}
PAGES = ["New BOM", "Batch", "Design standards", "Settings"]

st.set_page_config(page_title="FTTx BOM Tool", page_icon=":material/lan:", layout="wide")
st.markdown("""
<style>
  .block-container {padding-top: 1.4rem; max-width: 1480px;}
  h1, h2, h3, h4 {letter-spacing: -0.01em;}
  .step {font-size: 0.74rem; font-weight: 700; text-transform: uppercase; letter-spacing: .09em; color: #1F5FAD;
         margin: 1.2rem 0 .3rem 0;}
  .legend span {display: inline-block; padding: 2px 10px; border-radius: 4px; margin-right: 8px; font-size: .82rem;}
  .low {background: #FFC7CE; color: #9C0006;} .review {background: #FFEB9C; color: #7F6000;} .ok {background: #E2EFDA; color: #375623;}
  .brand {font-weight: 700; font-size: 1.05rem; color: #1F2933;} .brand small {font-weight: 400; color: #6b7280;}
  div[data-testid="stMetricValue"] {font-size: 1.7rem;}
</style>
""", unsafe_allow_html=True)


# --------------------------------------------------------------------------- helpers
def _save_uploads(files, dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for f in files:
        p = dest / Path(f.name).name
        p.write_bytes(f.getbuffer())
        out.append(p)
    return out


def _zip(paths) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in paths:
            if p and Path(p).exists():
                z.write(p, Path(p).name)
    return buf.getvalue()


def _detected_table(det) -> pd.DataFrame:
    rows = [{"File": p.name, "Recognised as": role} for role, ps in (
        ("Drawing", det.drawings), ("Address list", det.address_lists), ("Splice report", det.splice_reports),
        ("BOM template", det.bom_templates), ("Approved BOM (reference)", det.bom_completed)) for p in ps]
    rows += [{"File": p.name, "Recognised as": f"Not used - {why}"} for p, why in det.unknown]
    return pd.DataFrame(rows)


def _legend():
    st.markdown('<div class="legend"><span class="low">Low confidence - check before ordering</span>'
                '<span class="review">Review</span><span class="ok">Derived by the design standard</span></div>',
                unsafe_allow_html=True)


def _drawing_guess(names: list[str]) -> dict:
    """Project name and number from the drawing's file name (the first .dwg / .dxf among the inputs)."""
    dwg = next((n for n in names if n.lower().endswith((".dwg", ".dxf"))), None)
    return project_from_filename(dwg) if dwg else {"name": "", "number": ""}


def _open_folder(path: Path):
    """Open a folder in the file manager (the app runs on the user's own computer)."""
    try:
        if os.name == "nt":
            os.startfile(str(path))  # noqa: S606 - local desktop action
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError as exc:
        st.warning(f"Could not open the folder: {exc}")


# --------------------------------------------------------------------------- results
def show_results(res, notes):
    low = sum(g.flag_counts.get("LOW", 0) for g in res.groups)
    review = sum(g.flag_counts.get("REVIEW", 0) for g in res.groups)
    sev = res.issue_counts
    wb_ok = all(not g.workbook_failures for g in res.groups)
    st.markdown('<div class="step">Step 3 · Results</div>', unsafe_allow_html=True)
    st.subheader(", ".join(res.networks))
    st.caption(f"{len(res.groups)} BOM workbook(s) · generated in {res.elapsed:.0f} s · {Path(res.groups[0].bom).parent if res.groups else ''}")
    k = st.columns(6)
    k[0].metric("Passings", f"{int(sum(res.totals.get('passings', {}).values())):,}")
    k[1].metric("Low-confidence cells", low, help="Do not order without checking: an input is missing or the value could not be derived.")
    k[2].metric("Cells to review", review, help="Check before ordering: a design warning or an unsettled convention affects the value.")
    k[3].metric("Design errors", sev.get("ERROR", 0))
    k[4].metric("Design warnings", sev.get("WARN", 0))
    k[5].metric("Workbook check", "Passed" if wb_ok else "Failed")
    for n in notes:
        st.caption(n)
    if not all(g.recalculated for g in res.groups):
        st.caption("Formulas were not recalculated (LibreOffice not found); the workbook structure was verified. "
                   "Excel recalculates the formulas when the file is opened.")
    if getattr(res, "split", None):
        with st.expander("Network summary (Grant / Non-Grant)", expanded=True):
            st.dataframe(network_summary(res.split, res.networks), width="stretch", hide_index=True)

    for g in res.groups:
        name = ", ".join(g.networks)
        st.markdown(f"#### {name}")
        if g.ref_cells:
            st.caption(f"Compared with the approved BOM: {g.ref_cells[0]}/{g.ref_cells[1]} cells and "
                       f"{g.ref_totals[0]}/{g.ref_totals[1]} network totals equal. Differences are listed in the comparison workbook; "
                       "the tool follows the design standard, not the approved BOM.")
        tabs = st.tabs(["BOM preview", "Cells to check", "Design check", "Excluded plant", "Downloads"])
        lines = pd.DataFrame(g.lines)
        with tabs[0]:
            if lines.empty:
                st.info("No quantities written.")
            else:
                c1, c2, c3 = st.columns([2, 2, 3])
                show = c1.segmented_control("Show", list(SHOW), default=SHOW[0], key=f"show-{g.bom}") or SHOW[0]
                search = c2.text_input("Find a line", placeholder="Part number or description", key=f"find-{g.bom}")
                with c3:
                    _legend()
                view, styler = bom_preview(g.lines, show, search)
                st.dataframe(styler if styler is not None else view, width="stretch", hide_index=True, height=560,
                             column_config={"Status": st.column_config.TextColumn(width="medium"),
                                            "Description": st.column_config.TextColumn(width="large")})
                st.caption(f"{len(view)} line(s). Values as written to the BOM workbook; coloured cells are explained on the "
                           "'Cells to check' tab, in the cell comments and on the workbook's 'BOM Review' sheet.")
        with tabs[1]:
            _legend()
            chk = lines[lines["confidence"] != ""] if not lines.empty else lines
            if chk.empty:
                st.success("Every quantity is derived by the design standard from complete inputs.")
            else:
                lv = st.segmented_control("Show", ["All", "Low confidence only"], default="All", key=f"lv-{g.bom}") or "All"
                if lv != "All":
                    chk = chk[chk["confidence"] == "LOW"]
                chk = chk.assign(_r=chk["confidence"].map({"LOW": 0, "REVIEW": 1})).sort_values(["_r", "row"] if "row" in chk else ["_r"])
                cols = ["confidence", "line", "description", "unit", "network", "area", "value", "why"]
                view = (chk[[c for c in cols if c in chk]].assign(confidence=chk["confidence"].map(LEVEL), value=chk["value"].map(fmt_qty))
                        .rename(columns={"line": "Line", "description": "Description", "unit": "Unit", "network": "Network",
                                         "area": "Area", "value": "Value", "confidence": "Confidence", "why": "Why"}))
                try:
                    shown = view.style.apply(lambda c: ["background-color: #FFC7CE; color: #9C0006" if v == LEVEL["LOW"] else
                                                        "background-color: #FFEB9C; color: #7F6000" for v in c], subset=["Confidence"])
                except (ImportError, AttributeError):
                    shown = view
                st.dataframe(shown, width="stretch", hide_index=True, height=480,
                             column_config={"Why": st.column_config.TextColumn(width="large")})
                st.caption("The same cells are coloured in the BOM workbook, explained in a cell comment, and listed on its 'BOM Review' sheet.")
        with tabs[2]:
            df = pd.DataFrame([{"Severity": SEVERITY.get(i.severity, i.severity), "_s": i.severity, "Area": i.category, "Code": i.code,
                                "Network": i.network, "Problem": i.message, "Affects": i.affects, "How to fix": i.fix}
                               for i in g.issues])
            if df.empty:
                st.success("No design problems found.")
            else:
                counts = df["_s"].value_counts()
                pick = st.segmented_control("Severity", ["ERROR", "WARN", "INFO"], selection_mode="multi", default=["ERROR", "WARN"],
                                            format_func=lambda s: f"{SEVERITY[s][2:]}s ({counts.get(s, 0)})", key=f"sev-{g.bom}")
                st.dataframe(df[df["_s"].isin(pick or [])].drop(columns=["_s"]), width="stretch", hide_index=True, height=440,
                             column_config={"Problem": st.column_config.TextColumn(width="large")})
                st.caption("In AutoCAD, run SCRIPT on the ISSUES.scr file: every located problem is circled on layers "
                           "BOM_CHECK_ERROR / _WARN / _INFO.")
        with tabs[3]:
            ex = pd.DataFrame([{"Category": c, "Object": o, "Quantity": q, "Reason": r} for c, o, q, r, _p in res.excluded])
            if ex.empty:
                st.info("Nothing was excluded: the drawing holds only this design.")
            else:
                st.caption("Objects in the drawing that are not part of this design (existing / HFC plant, other fiber networks).")
                st.dataframe(ex, width="stretch", hide_index=True, height=380)
        with tabs[4]:
            files = [(g.bom, "BOM workbook"), (g.audit, "Audit workbook"), (g.discrepancies, "Comparison with approved BOM"),
                     (g.issues_csv, "Design check (CSV)"), (g.issues_scr, "AutoCAD issue script")]
            cols = st.columns(3)
            i = 0
            for path, label in files:
                if path and Path(path).exists():
                    cols[i % 3].download_button(label, Path(path).read_bytes(), file_name=Path(path).name, key=f"dl-{path}",
                                                width="stretch")
                    i += 1
            b1, b2 = st.columns([1, 2])
            b1.download_button("Everything (zip)", _zip([p for p, _ in files]), file_name=f"{Path(g.bom).stem}_all.zip",
                               key=f"zip-{g.bom}", type="primary", width="stretch")
            if b2.button("Open output folder", key=f"open-{g.bom}"):
                _open_folder(Path(g.bom).parent)
            st.caption(f"Saved in {Path(g.bom).parent}")


# --------------------------------------------------------------------------- pages
def page_new():
    st.title("New BOM")
    st.caption("Generate the OLM BOM from the design drawing and its inputs.")
    st.markdown('<div class="step">Step 1 · Inputs</div>', unsafe_allow_html=True)
    source = st.segmented_control("Source", ["Upload files", "Folders on this computer"], default="Upload files") or "Upload files"
    uploads, paths = [], []
    if source == "Folders on this computer":
        txt = st.text_area("Files or folders, one per line", placeholder=r"C:\Jobs\DMI-R15")
        paths = [Path(x.strip().strip('"')) for x in txt.splitlines() if x.strip()]
        names = [str(p) for p in paths]
        for p in paths:
            if p.is_dir():
                names += [str(q) for q in sorted(p.rglob("*")) if q.suffix.lower() in (".dwg", ".dxf")][:5]
    else:
        uploads = st.file_uploader("Drawing (DWG/DXF), address list, splice reports, BOM template; optionally an approved BOM to compare with. "
                                   "Zip files are fine.", type=["dwg", "dxf", "xlsx", "zip"], accept_multiple_files=True)
        names = [f.name for f in uploads or []]
    guess = _drawing_guess(names)
    c1, c2, c3 = st.columns(3)
    pname = c1.text_input("Project name", value=guess.get("name", ""), help="Taken from the drawing's file name; edit if needed.")
    pnum = c2.text_input("Project number", value=guess.get("number", ""))
    system = c3.selectbox("System", SYSTEMS, index=SYSTEMS.index(st.session_state.get("system", "")),
                          format_func=lambda s: s or "Choose the system")
    st.session_state["system"] = system
    with st.expander("Advanced"):
        recalc = st.toggle("Recalculate formulas with LibreOffice", value=soffice_exe() is not None,
                           help="Optional. Excel recalculates the formulas when the BOM is opened.")
        learn = st.toggle("Learn conventions from the approved BOM (when one is included)", value=False,
                          help="Off by default: the design standard decides, an approved BOM may contain errors.")

    st.markdown('<div class="step">Step 2 · Generate</div>', unsafe_allow_html=True)
    ready = bool(uploads or paths)
    if ready and not system:
        st.caption("The System is blank in the BOM header until you choose one.")
    if st.button("Generate BOM", type="primary", disabled=not ready, icon=":material/play_arrow:"):
        job = WORK / dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        inputs = _save_uploads(uploads, job / "in") if uploads else paths
        missing = [str(p) for p in inputs if not Path(p).exists()]
        if missing:
            st.error("Not found: " + ", ".join(missing))
            return
        with st.status("Generating the BOM ...", expanded=True) as status:
            det = detect(inputs, job / "extracted", exclude=[job / "out"])
            st.dataframe(_detected_table(det), width="stretch", hide_index=True)
            try:
                params, notes = params_from_detected(det, job / "out", project_name=pname or None, project_number=pnum or None,
                                                     system=system, learn=learn, recalc=recalc, cache=WORK / ".cache")
            except ValueError as exc:
                status.update(label="Inputs incomplete", state="error")
                st.error(str(exc))
                return
            line = st.empty()
            try:
                res = run_job(params, lambda m: line.write(str(m)))
            except Exception as exc:  # show the problem instead of a blank page
                status.update(label="Generation failed", state="error")
                st.exception(exc)
                return
            status.update(label=f"BOM generated in {res.elapsed:.0f} s", state="complete", expanded=False)
        st.session_state["last"] = (res, notes)
    if "last" in st.session_state:
        st.divider()
        show_results(*st.session_state["last"])


def page_batch():
    st.title("Batch")
    st.caption("One BOM set per job folder: each sub-folder holds one network's drawing, address list and splice reports.")
    root = st.text_input("Jobs folder", placeholder=r"C:\Jobs")
    c1, c2 = st.columns(2)
    tpl = c1.text_input("Template for folders without one (optional)")
    out = c2.text_input("Output folder", value=str(WORK / "batch"))
    recalc = st.toggle("Recalculate formulas with LibreOffice", value=False, key="b-recalc")
    if st.button("Run batch", type="primary", disabled=not root, icon=":material/play_arrow:"):
        with st.status("Running jobs ...", expanded=True) as status:
            line = st.empty()
            try:
                path = run_batch(Path(root), Path(out), template=Path(tpl) if tpl else None, log=lambda m: line.write(str(m)),
                                 recalc=recalc, cache=WORK / ".cache")
            except Exception as exc:
                status.update(label="Batch failed", state="error")
                st.exception(exc)
                return
            status.update(label="Batch complete", state="complete", expanded=False)
        st.dataframe(pd.read_excel(path), width="stretch", hide_index=True)
        b1, b2 = st.columns([1, 3])
        b1.download_button("Batch summary", path.read_bytes(), file_name=path.name, type="primary")
        if b2.button("Open output folder"):
            _open_folder(Path(out))


def page_standards():
    st.title("Design standards")
    st.caption("How every BOM line is derived. Lines without a rule are not used by these designs and stay blank.")
    doc = bundle_root() / "DESIGN_STANDARDS.md"
    if doc.exists():
        with st.expander("Standards document", expanded=False):
            st.markdown(doc.read_text(encoding="utf-8"))
    _cfg, rules = load_rules()
    rows = [{"BOM line": r.key, "Written": "yes" if r.write else "no", "Status": r.status, "How it is derived": r.basis, "Source": r.source}
            for r in rules]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=620,
                 column_config={"How it is derived": st.column_config.TextColumn(width="large")})
    st.caption("VERIFIED: follows the documented design standard or reproduces an approved BOM from independent inputs. VERIFIED_TOTAL: "
               "totals verified, Grant/Non-Grant from the boundaries. INFERRED: derived from the design data, highlighted for review. "
               "TEMPLATE_FORMULA: kept from the template.")


def page_settings():
    st.title("Settings")
    st.caption("Conventions the drawing cannot settle. Every option is computed on every run and shown in the audit; the "
               "selection below is written to the BOM.")
    data = json.loads(pol.CONFIG.read_text(encoding="utf-8")) if pol.CONFIG.exists() else {}
    sel, ev = data.get("selected", {}), data.get("evidence", {})
    new = {}
    for p in pol.POLICIES:
        opts = list(p.options)
        cur = sel.get(p.name, p.default)
        c1, c2 = st.columns([1, 2])
        new[p.name] = c1.selectbox(p.title, opts, index=opts.index(cur) if cur in opts else 0,
                                   format_func=lambda o, p=p: o.replace("_", " ") + (" (standard)" if o == p.default else ""),
                                   key=f"pol-{p.name}")
        c2.caption(p.options[new[p.name]])
        if ev.get(p.name):
            c2.caption("Evidence from approved BOMs: " + "; ".join(
                f"{o.replace('_', ' ')} {sum(j['matched'] for j in jobs.values())}/{sum(j['cells'] for j in jobs.values())} cells"
                for o, jobs in ev[p.name].items()))
    b1, b2 = st.columns([1, 5])
    if b1.button("Save", type="primary"):
        data["selected"] = new
        pol.CONFIG.parent.mkdir(parents=True, exist_ok=True)
        pol.CONFIG.write_text(json.dumps(data, indent=2), encoding="utf-8")
        st.success("Saved. Used for every new BOM.")
    if b2.button("Restore standard settings"):
        data["selected"] = {}
        pol.CONFIG.parent.mkdir(parents=True, exist_ok=True)
        pol.CONFIG.write_text(json.dumps(data, indent=2), encoding="utf-8")
        st.success("Standard settings restored.")
    st.caption(f"Settings file: {pol.CONFIG}")


with st.sidebar:
    st.markdown(f'<div class="brand">FTTx BOM Tool <small>v{__version__}</small></div>', unsafe_allow_html=True)
    st.caption("Runs on this computer. No file leaves it.")
    page = st.radio("Navigation", PAGES, label_visibility="collapsed")
    st.divider()
    st.caption("Before generating: run FXAUTO (FX_DROPS) in AutoCAD and save, so the drawing carries the drop lines.")
    st.caption(f"Job files: {WORK}")
{"New BOM": page_new, "Batch": page_batch, "Design standards": page_standards, "Settings": page_settings}[page]()
