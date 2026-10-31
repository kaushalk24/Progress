"""FTTx BOM Tool - local browser app.

Start:  python -m fttx_bom app     (or windows\\run_app.bat)
Everything runs on this computer; files never leave it.
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
from fttx_bom.engine.rules import CONFIG_DIR, load_rules  # noqa: E402
from fttx_bom.inputs.detect import detect  # noqa: E402
from fttx_bom.jobs import params_from_detected, run_batch  # noqa: E402
from fttx_bom.pipeline import run_job  # noqa: E402

WORK = Path.home() / "FTTx_BOM_Jobs"
SYSTEMS = ["", "Coastal West", "Coastal East", "Capital West", "Capital East"]
SEV_MARK = {"ERROR": "🔴 ERROR", "WARN": "🟡 WARN", "INFO": "🔵 INFO"}

st.set_page_config(page_title="FTTx BOM Tool", page_icon=":bar_chart:", layout="wide")


def _save_uploads(files, dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for f in files:
        p = dest / Path(f.name).name
        p.write_bytes(f.getbuffer())
        out.append(p)
    return out


def _zip_outputs(paths: list[Path]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in paths:
            if p and Path(p).exists():
                z.write(p, Path(p).name)
    return buf.getvalue()


def _issues_df(issues) -> pd.DataFrame:
    return pd.DataFrame([{"Severity": SEV_MARK.get(i.severity, i.severity), "_sev": i.severity, "Category": i.category, "Code": i.code, "Network": i.network,
                          "Problem": i.message, "BOM lines affected": i.affects, "How to fix": i.fix,
                          "X": round(i.x, 1) if i.x is not None else None, "Y": round(i.y, 1) if i.y is not None else None}
                         for i in issues])


def show_result(res, notes):
    st.success(f"Done in {res.elapsed:.0f} s - {len(res.groups)} BOM file(s).")
    sev = res.issue_counts
    c = st.columns(5)
    c[0].metric("Networks", len(res.networks))
    c[1].metric("Passings", int(sum(res.totals.get("passings", {}).values())))
    c[2].metric("Errors", sev.get("ERROR", 0))
    c[3].metric("Warnings", sev.get("WARN", 0))
    c[4].metric("Info", sev.get("INFO", 0))
    for n in notes:
        st.caption("note: " + n)
    for g in res.groups:
        st.subheader("BOM " + ", ".join(g.networks))
        if g.ref_cells:
            st.write(f"Against the approved BOM: **{g.ref_cells[0]}/{g.ref_cells[1]}** area cells and "
                     f"**{g.ref_totals[0]}/{g.ref_totals[1]}** network totals match.")
        if g.workbook_failures:
            st.error("Workbook verification failed: " + "; ".join(f"{x[0]}: {x[2]}" for x in g.workbook_failures))
        elif not g.recalculated:
            st.warning("Formulas were not recalculated (LibreOffice not found) - the workbook structure was verified only.")
        files = [g.bom, g.audit, g.discrepancies, g.issues_csv, g.issues_scr]
        cols = st.columns(len([f for f in files if f]) + 1)
        k = 0
        for f in files:
            if f:
                cols[k].download_button(Path(f).name.split("_", 1)[-1], Path(f).read_bytes(), file_name=Path(f).name,
                                        key=f"dl-{f}")
                k += 1
        cols[k].download_button("All files (zip)", _zip_outputs(files), file_name=f"{g.bom.stem}_all.zip", key=f"zip-{g.bom}")
        df = _issues_df(g.issues)
        if df.empty:
            st.info("Deep check found no problems.")
        else:
            f1, f2 = st.columns(2)
            sevs = f1.multiselect("Severity", ["ERROR", "WARN", "INFO"], default=["ERROR", "WARN"], key=f"sev-{g.bom}")
            cats = f2.multiselect("Category", sorted(df["Category"].unique()), key=f"cat-{g.bom}")
            view = df[df["_sev"].isin(sevs)]
            if cats:
                view = view[view["Category"].isin(cats)]
            st.dataframe(view.drop(columns=["_sev"]), width="stretch", hide_index=True)
            st.caption("In AutoCAD: type SCRIPT and pick the ISSUES.scr file - every located problem is circled on "
                       "layers BOM_CHECK_ERROR / _WARN / _INFO.")
    with st.expander("Key quantities by network"):
        st.dataframe(pd.DataFrame(res.totals).T, width="stretch")
    if res.calibration:
        with st.expander("Policy calibration against the approved BOM", expanded=True):
            st.dataframe(pd.DataFrame(res.calibration)[["policy", "option", "matched", "cells", "abs_error", "best", "selected"]],
                         width="stretch", hide_index=True)
            if res.learned:
                st.success(f"Learned and saved: {res.learned}")
    st.caption("Policies used: " + ", ".join(f"{k}={v}" for k, v in res.policies_used.items()))


def page_run():
    st.header("Run a BOM job")
    st.write("Drop **everything** for one OLM job or one combined drawing: the DWG/DXF, address list(s), splice reports "
             "(files or zip), the blank BOM template, and optionally a completed/approved BOM to compare and learn from. "
             "The tool works out which file is which.")
    how = st.radio("Inputs", ["Upload files", "Use folders on this computer"], horizontal=True)
    uploads, paths = [], []
    if how == "Upload files":
        uploads = st.file_uploader("Files (.dwg .dxf .xlsx .zip)", type=["dwg", "dxf", "xlsx", "zip"], accept_multiple_files=True)
    else:
        txt = st.text_area("One file or folder path per line")
        paths = [Path(x.strip().strip('"')) for x in txt.splitlines() if x.strip()]
    with st.expander("Options"):
        c1, c2, c3 = st.columns(3)
        pname = c1.text_input("Project name (e.g. Melcher-Dallas, IA)")
        pnum = c2.text_input("Project number")
        system = c3.selectbox("System", SYSTEMS)
        learn = st.checkbox("Learn policies from the approved BOM (if one is included)", value=False)
        recalc = st.checkbox("Recalculate formulas with LibreOffice (slower, recommended)", value=shutil.which("soffice") is not None)
    if st.button("Run", type="primary", disabled=not (uploads or paths)):
        job = WORK / dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        inputs = _save_uploads(uploads, job / "in") if uploads else paths
        missing = [str(p) for p in inputs if not Path(p).exists()]
        if missing:
            st.error("Not found: " + ", ".join(missing))
            return
        log_box = st.empty()
        lines: list[str] = []

        def log(msg):
            lines.append(str(msg))
            log_box.code("\n".join(lines[-14:]))

        with st.spinner("Detecting inputs ..."):
            det = detect(inputs, job / "extracted")
        st.write("Detected: " + ", ".join(f"**{v}** {k}" for k, v in det.summary().items()))
        try:
            params, notes = params_from_detected(det, job / "out", project_name=pname or None, project_number=pnum or None,
                                                 system=system, learn=learn, recalc=recalc, cache=WORK / ".cache")
        except ValueError as exc:
            st.error(str(exc))
            return
        with st.spinner("Building the BOM (1-3 minutes) ..."):
            try:
                res = run_job(params, log)
            except Exception as exc:  # show the error instead of a blank page
                st.exception(exc)
                return
        st.session_state["last"] = (res, notes)
    if "last" in st.session_state:
        show_result(*st.session_state["last"])


def page_batch():
    st.header("Batch: many networks")
    st.write("Point at a folder with **one sub-folder per network/job** (each with its drawing, address list, splice "
             "reports - zips are fine). Each job gets its own BOM, audit and deep check, plus one BATCH_SUMMARY.xlsx.")
    root = st.text_input("Jobs folder")
    tpl = st.text_input("Template to use when a job folder has none (optional)")
    out = st.text_input("Output folder", value=str(WORK / "batch"))
    recalc = st.checkbox("Recalculate formulas with LibreOffice", value=False, key="b-recalc")
    if st.button("Run batch", type="primary", disabled=not root):
        lines: list[str] = []
        box = st.empty()

        def log(msg):
            lines.append(str(msg))
            box.code("\n".join(lines[-16:]))

        with st.spinner("Running jobs ..."):
            try:
                path = run_batch(Path(root), Path(out), template=Path(tpl) if tpl else None, log=log, recalc=recalc,
                                 cache=WORK / ".cache")
            except Exception as exc:
                st.exception(exc)
                return
        st.dataframe(pd.read_excel(path), width="stretch", hide_index=True)
        st.download_button("BATCH_SUMMARY.xlsx", path.read_bytes(), file_name=path.name)


def page_guide():
    st.header("BOM guide - how every line is calculated")
    _cfg, rules = load_rules()
    inv = json.loads((CONFIG_DIR / "investigations.json").read_text())
    rows = [{"BOM line": r.key, "Status": r.status, "Written to BOM": "yes" if r.write else "no",
             "How it is calculated": r.basis, "Source": r.source, "Notes from reconciliation": inv.get(r.key, "")}
            for r in rules]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=600)
    st.markdown("**Status:** VERIFIED = reproduces the approved Credit River BOM from independent sources. "
                "VERIFIED_TOTAL = network totals verified; Grant/Non-Grant split inferred from the boundaries. "
                "INFERRED = defensible rule, not proven against an approved BOM. TEMPLATE_FORMULA = kept from the template. "
                "NOT_DETECTED = no drawing symbol for it; left blank. SUGGESTED = shown in the audit only. "
                "Template lines without a rule (taps, ONU, ...) are not used by these designs and stay blank.")


def page_policies():
    st.header("Policies - conventions the drawing alone cannot settle")
    st.write("Each policy is computed every way on every run. The option selected here is written to the BOM; the others "
             "are shown in the audit's Policies sheet. Running against an approved BOM with **Learn** ticked scores every "
             "option and selects the best automatically.")
    data = json.loads(pol.CONFIG.read_text()) if pol.CONFIG.exists() else {}
    sel = data.get("selected", {})
    ev = data.get("evidence", {})
    new = {}
    for p in pol.POLICIES:
        opts = list(p.options)
        cur = sel.get(p.name, p.default)
        c1, c2 = st.columns([1, 2])
        new[p.name] = c1.selectbox(p.title, opts, index=opts.index(cur) if cur in opts else 0,
                                   format_func=lambda o, p=p: o + (" (default)" if o == p.default else ""), key=f"pol-{p.name}")
        c2.caption(p.options[new[p.name]])
        if ev.get(p.name):
            c2.caption("Evidence: " + "; ".join(
                f"{o}: {sum(j['matched'] for j in jobs.values())}/{sum(j['cells'] for j in jobs.values())} cells"
                for o, jobs in ev[p.name].items()))
    if st.button("Save policy selection"):
        data["selected"] = new
        pol.CONFIG.write_text(json.dumps(data, indent=2))
        st.success("Saved to config/policies.json - used for every new BOM.")


st.sidebar.title("FTTx BOM Tool")
st.sidebar.caption(f"version {__version__} - runs locally")
page = st.sidebar.radio("Go to", ["Run a job", "Batch", "BOM guide", "Policies"])
st.sidebar.markdown("---")
st.sidebar.markdown("**Before running:** in AutoCAD run **FXAUTO** (FX_DROPS.lsp) and save, so the drawing has drop lines.")
st.sidebar.caption(f"Job files are kept in {WORK}")
{"Run a job": page_run, "Batch": page_batch, "BOM guide": page_guide, "Policies": page_policies}[page]()
