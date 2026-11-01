"""Tables the app shows, built from a job's results (kept out of the Streamlit script so they can be tested)."""
from __future__ import annotations

LEVEL = {"LOW": "● Low confidence", "REVIEW": "● Review", "": "✓"}
RANK = {"LOW": 2, "REVIEW": 1, "": 0}


def bom_preview(lines: list[dict]):
    """One row per written BOM line, in template order: status, line, description, then a value column per
    network and area. The status is the worst confidence of the line's cells."""
    import pandas as pd

    df = pd.DataFrame(lines)
    if df.empty:
        return df
    order = list(dict.fromkeys(zip(df["line"], df["description"])))
    view = (df.drop_duplicates(["line", "description", "network", "area"])
            .set_index(["line", "description", "network", "area"])["value"]
            .unstack(["network", "area"]).reindex(order))
    view.index.names = ["line", "description"]
    view = view.reset_index()
    view.columns = [" ".join(c).strip() if isinstance(c, tuple) else c for c in view.columns]
    worst = df.assign(rank=df["confidence"].map(RANK)).groupby("line")["rank"].max()
    status = {v: k for k, v in RANK.items()}
    view.insert(0, "Status", view["line"].map(lambda x: LEVEL[status[int(worst.get(x, 0))]]))
    return view
