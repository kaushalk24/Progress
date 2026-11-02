"""Tables the app shows, built from a job's results (kept out of the Streamlit script so they can be tested)."""
from __future__ import annotations

import math

LEVEL = {"LOW": "● Low confidence", "REVIEW": "● Review", "": "✓"}
RANK = {"LOW": 2, "REVIEW": 1, "": 0}
# cell colours, identical to the BOM workbook (excel/confidence.py)
CELL_CSS = {"LOW": "background-color: #FFC7CE; color: #9C0006; font-weight: 600",
            "REVIEW": "background-color: #FFEB9C; color: #7F6000; font-weight: 600"}
SHOW = ("Lines with a quantity", "Cells to check", "All lines")

SUMMARY = [  # label, takeoff key(s), unit
    ("Passings", ("passings",), "EA"),
    ("  Residential", ("pass_res",), "EA"),
    ("  Commercial", ("pass_com",), "EA"),
    ("  MDU units", ("pass_mdu",), "EA"),
    ("MAX10 pedestals", ("ped_max10",), "EA"),
    ("MAX5 pedestals", ("ped_max5",), "EA"),
    ("Vaults", ("vault",), "EA"),
    ("Fiber cable", ("cable_*",), "FT"),
    ("UG route", ("route_ug_ft",), "FT"),
    ("Aerial route", ("route_aerial_ft",), "FT"),
    ("Route", ("route_miles",), "MI"),
    ("Drop footage", ("drop_ft_bom",), "FT"),
    ("FOSC 450B / 450D closures", ("fosc450b", "fosc450d"), "EA"),
    ("Splitters", ("splitter_1x32", "splitter_1x64"), "EA"),
    ("XGS SFP+", ("pon_ports",), "EA"),
]


def fmt_qty(v) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    v = float(v)
    return f"{v:,.0f}" if v.is_integer() else f"{v:,.2f}"


def bom_preview(lines: list[dict], show: str = "All lines", search: str = ""):
    """One row per written BOM line, in template order: status, section, line, description, unit, a value column
    per network and area, and the total. Returns (DataFrame, Styler); the styler colours every flagged cell
    exactly as the workbook does. The status is the worst confidence of the line's cells."""
    import pandas as pd

    df = pd.DataFrame(lines)
    if df.empty:
        return df, None
    for col, default in (("section", ""), ("unit", ""), ("row", 0)):
        if col not in df:
            df[col] = default
    df["col"] = df["network"] + " " + df["area"]
    keys = ["line", "description", "section", "unit"]
    order = list(dict.fromkeys(zip(*(df[k] for k in keys))))
    vals = (df.drop_duplicates(keys + ["col"]).set_index(keys + ["col"])["value"].unstack("col").reindex(order))
    cols = list(dict.fromkeys(df["col"]))
    vals = vals[cols].apply(pd.to_numeric, errors="coerce")
    vals["Total"] = vals[cols].sum(axis=1, min_count=1)
    view = vals.reset_index()
    worst = df.assign(rank=df["confidence"].map(RANK)).groupby("line")["rank"].max()
    status = {v: k for k, v in RANK.items()}
    view.insert(0, "Status", view["line"].map(lambda x: LEVEL[status[int(worst.get(x, 0))]]))
    view = view.rename(columns={"line": "Line", "description": "Description", "section": "Section", "unit": "Unit"})
    view = view[["Status", "Section", "Line", "Description", "Unit"] + cols + ["Total"]]
    if show == SHOW[0]:
        view = view[(view[cols].fillna(0) != 0).any(axis=1) | (view["Status"] != LEVEL[""])]
    elif show == SHOW[1]:
        view = view[view["Status"] != LEVEL[""]]
    if search.strip():
        s = search.strip().lower()
        view = view[view["Line"].str.lower().str.contains(s, regex=False) | view["Description"].str.lower().str.contains(s, regex=False)]
    view = view.reset_index(drop=True)
    level = {(r.line, r.col): r.confidence for r in df.itertuples() if r.confidence}

    def colour(column):
        return [CELL_CSS.get(level.get((line, column.name), ""), "") for line in view["Line"]]

    def status_colour(column):
        return [CELL_CSS["LOW"] if v == LEVEL["LOW"] else CELL_CSS["REVIEW"] if v == LEVEL["REVIEW"] else "" for v in column]

    try:  # pandas styling needs jinja2; without it the table is shown uncoloured rather than failing
        styler = (view.style.apply(colour, axis=0, subset=cols).apply(status_colour, axis=0, subset=["Status"])
                  .format(fmt_qty, subset=cols + ["Total"]))
    except (ImportError, AttributeError):
        styler = None
    return view, styler


def network_summary(split: dict, networks: list[str]):
    """Key quantities per network as Grant / Non-Grant / Total, for the results header."""
    import pandas as pd

    rows = []
    for label, keys, unit in SUMMARY:
        ks = [k for k in split if k.startswith("cable_")] if keys == ("cable_*",) else [k for k in keys if k in split]
        if not ks:
            continue
        row = {"Quantity": label, "Unit": unit}
        for n in networks:
            g = [split[k].get((n, "G")) for k in ks]
            ng = [split[k].get((n, "NG")) for k in ks]
            gv = None if all(v is None for v in g) else sum(v or 0 for v in g)
            nv = None if all(v is None for v in ng) else sum(v or 0 for v in ng)
            row[f"{n} Grant"] = fmt_qty(gv)
            row[f"{n} Non-Grant"] = fmt_qty(nv)
            row[f"{n} Total"] = fmt_qty(None if gv is None and nv is None else (gv or 0) + (nv or 0))
        rows.append(row)
    return pd.DataFrame(rows)
