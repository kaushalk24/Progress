"""FTTx BOM Tool - local browser application.

Start:  python -m fttx_bom app     (Windows: windows\\run_app.bat)
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
import shutil
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
from fttx_bom.pipeline import project_from_filename, run_job  # noqa: E402
from fttx_bom.views import LEVEL, bom_preview  # noqa: E402

WORK = Path.home() / "FTTx_BOM_Jobs"
SYSTEMS = ["", "Coastal West", "Coastal East", "Capital West", "Capital East"]
SEVERITY = {"ERROR": "● Error", "WARN": "● Warning", "INFO": "● Info"}
PAGES = ["New BOM", "Batch", "Design standards", "Settings"]

st.set_page_config(page_title="FTTx BOM Tool", page_icon=":material/fiber_manual_record:", layout="wide")
st.markdown("""
<style>
  .block-container {padding-top: 1.6rem; max-width: 1400px;}
  h1, h2, h3 {letter-spacing: -0.01em;}
  .step {font-size: 0.78rem; font-weight: 600; text-transform: uppercase; letter-spacing: .08em; color: #6b7280;}
  .legend span {display: inline-block; padding: 2px 10px; border-radius: 4px; margin-right: 8px; font-size: .85rem;}
  .low {background: #FFC7CE; color: #9C0006;} .review {background: #FFEB9C; color: #7F6000;} .ok {background: #E2EFDA; color: #375623;}
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


# --------------------------------------------------------------------------- results
def show_results(res, notes):
    low = sum(g.flag_counts.get("LOW", 0) for g in res.groups)
    review = sum(g.flag_counts.get("REVIEW", 0) for g in res.groups)
    sev = res.issue_counts
    wb_ok = all(not g.workbook_failures for g in res.groups)
    st.markdown('<div class="step">Step 3 · Results</div>', unsafe_allow_html=True)
    st.subheader(f"{len(res.groups)} BOM file(s) for {', '.join(res.networks)}")
    k = st.columns(6)
    k[0].metric("Passings", int(sum(res.totals.get("passings", {}).values())))
    k[1].metric("Low-confidence cells", low)
    k[2].metric("Cells to review", review)
    k[3].metric("Design errors", sev.get("ERROR", 0))
    k[4].metric("Design warnings", sev.get("WARN", 0))
    k[5].metric("Workbook check", "Passed" if wb_ok else "Failed")
    for n in notes:
        st.caption(n)
    if not all(g.recalculated for g in res.groups):
        st.caption("Formulas were not recalculated (LibreOffice not installed); the workbook structure was verified.")

    for g in res.groups:
        name = ", ".join(g.networks)
        st.markdown(f"#### {name}")
        if g.ref_cells:
            st.caption(f"Compared with the approved BOM: {g.ref_cells[0]}/{g.ref_cells[1]} cells and "
                       f"{g.ref_totals[0]}/{g.ref_totals[1]} network totals equal.")
        tabs = st.tabs(["BOM preview", "Cells to check", "Design check", "Excluded plant", "Downloads"])
        lines = pd.DataFrame(g.lines)
        with tabs[0]:
            _legend()
            if lines.empty:
                st.info("No quantities written.")
            else:
                view = bom_preview(g.lines)
                st.dataframe(view, width="stretch", hide_index=True, height=520)
        with tabs[1]:
            _legend()
            chk = lines[lines["confidence"] != ""] if not lines.empty else lines
            if chk.empty:
                st.success("Every quantity is derived by the design standard from complete inputs.")
            else:
                lv = st.radio("Show", ["All", "Low confidence only"], horizontal=True, key=f"lv-{g.bom}")
                if lv != "All":
                    chk = chk[chk["confidence"] == "LOW"]
                st.dataframe(chk.assign(confidence=chk["confidence"].map(LEVEL))
                             .rename(columns={"line": "Line", "description": "Description", "network": "Network", "area": "Area",
                                              "value": "Value", "confidence": "Confidence", "why": "Why"}),
                             width="stretch", hide_index=True, height=480)
                st.caption("The same cells are coloured in the BOM workbook, explained in a cell comment, and listed on its 'BOM Review' sheet.")
        with tabs[2]:
            df = pd.DataFrame([{"Severity": SEVERITY.get(i.severity, i.severity), "_s": i.severity, "Area": i.category, "Code": i.code,
                                "Network": i.network, "Problem": i.message, "Affects": i.affects, "How to fix": i.fix}
                               for i in g.issues])
            if df.empty:
                st.success("No design problems found.")
            else:
                pick = st.multiselect("Severity", ["ERROR", "WARN", "INFO"], default=["ERROR", "WARN"], key=f"sev-{g.bom}")
                st.dataframe(df[df["_s"].isin(pick)].drop(columns=["_s"]), width="stretch", hide_index=True, height=420)
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
            for path, label in files:
                if path and Path(path).exists():
                    st.download_button(label, Path(path).read_bytes(), file_name=Path(path).name, key=f"dl-{path}")
            st.download_button("Everything (zip)", _zip([p for p, _ in files]), file_name=f"{Path(g.bom).stem}_all.zip",
                               key=f"zip-{g.bom}", type="primary")


# --------------------------------------------------------------------------- pages
def page_new():
    st.title("New BOM")
    st.caption("Generate the OLM BOM from the design drawing and its inputs.")
    st.markdown('<div class="step">Step 1 · Inputs</div>', unsafe_allow_html=True)
    source = st.segmented_control("Source", ["Upload files", "Folders on this computer"], default="Upload files")
    uploads, paths = [], []
    if source == "Folders on this computer":
        txt = st.text_area("Files or folders, one per line", placeholder=r"C:\Jobs\DMI-R15")
        paths = [Path(x.strip().strip('"')) for x in txt.splitlines() if x.strip()]
    else:
        uploads = st.file_uploader("Drawing (DWG/DXF), address list, splice reports, BOM template; optionally an approved BOM to compare with. "
                                   "Zip files are fine.", type=["dwg", "dxf", "xlsx", "zip"], accept_multiple_files=True)
    guess = project_from_filename(uploads[0].name) if uploads else {"name": "", "number": ""}
    c1, c2, c3 = st.columns(3)
    pname = c1.text_input("Project name", value=guess.get("name", ""))
    pnum = c2.text_input("Project number", value=guess.get("number", ""))
    system = c3.selectbox("System", SYSTEMS)
    with st.expander("Advanced"):
        recalc = st.toggle("Recalculate formulas with LibreOffice", value=shutil.which("soffice") is not None)
        learn = st.toggle("Learn conventions from the approved BOM (when one is included)", value=False)

    st.markdown('<div class="step">Step 2 · Generate</div>', unsafe_allow_html=True)
    if st.button("Generate BOM", type="primary", disabled=not (uploads or paths)):
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
    root = st.text_input("Jobs folder")
    c1, c2 = st.columns(2)
    tpl = c1.text_input("Template for folders without one (optional)")
    out = c2.text_input("Output folder", value=str(WORK / "batch"))
    recalc = st.toggle("Recalculate formulas with LibreOffice", value=False, key="b-recalc")
    if st.button("Run batch", type="primary", disabled=not root):
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
        st.download_button("Batch summary", path.read_bytes(), file_name=path.name, type="primary")


def page_standards():
    st.title("Design standards")
    st.caption("How every BOM line is derived. Lines without a rule are not used by these designs and stay blank.")
    doc = ROOT / "DESIGN_STANDARDS.md"
    if doc.exists():
        with st.expander("Standards document", expanded=False):
            st.markdown(doc.read_text())
    _cfg, rules = load_rules()
    rows = [{"BOM line": r.key, "Written": "yes" if r.write else "no", "Status": r.status, "How it is derived": r.basis, "Source": r.source}
            for r in rules]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=620)
    st.caption("VERIFIED: reproduces an approved BOM from independent inputs. VERIFIED_TOTAL: totals verified, Grant/Non-Grant from the "
               "boundaries. INFERRED: rule derived from the design data, highlighted for review. TEMPLATE_FORMULA: kept from the template.")


def page_settings():
    st.title("Settings")
    st.caption("Conventions the drawing cannot settle. Every option is computed on every run and shown in the audit; the "
               "selection below is written to the BOM.")
    data = json.loads(pol.CONFIG.read_text()) if pol.CONFIG.exists() else {}
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
        pol.CONFIG.write_text(json.dumps(data, indent=2))
        st.success("Saved. Used for every new BOM.")
    if b2.button("Restore standard settings"):
        data["selected"] = {}
        pol.CONFIG.write_text(json.dumps(data, indent=2))
        st.success("Standard settings restored.")


with st.sidebar:
    st.markdown("### FTTx BOM Tool")
    st.caption(f"Version {__version__} · runs on this computer")
    page = st.radio("Navigation", PAGES, label_visibility="collapsed")
    st.divider()
    st.caption("Before generating: run FXAUTO (FX_DROPS) in AutoCAD and save, so the drawing carries the drop lines.")
    st.caption(f"Job files: {WORK}")
{"New BOM": page_new, "Batch": page_batch, "Design standards": page_standards, "Settings": page_settings}[page]()
