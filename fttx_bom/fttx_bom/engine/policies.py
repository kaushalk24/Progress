"""Policies: BOM conventions that the drawings alone cannot settle.

Every policy is computed every way (`key@option` quantities), the selected
option is copied into the base key the rule catalogue uses, and - when an
approved BOM is supplied - every option is scored against it. Scores from
approved BOMs accumulate in config/policies.json (`--learn`), so the tool picks
conventions from evidence instead of waiting for manual confirmation.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from .network import AREAS, GRANT, NONGRANT
from .takeoff import Qty, Takeoff

CONFIG = Path(__file__).resolve().parents[2] / "config" / "policies.json"


@dataclass(frozen=True)
class Policy:
    name: str
    title: str
    keys: str  # regex of base quantity keys the policy decides
    default: str
    options: dict[str, str]
    engine: str = ""  # option the engine's base value implements (default when empty)

    @property
    def base_option(self) -> str:
        return self.engine or self.default

    def owns(self, key: str) -> bool:
        return re.fullmatch(self.keys, key) is not None


POLICIES = [
    Policy("sfp", "XGS SFP+ per column", r"pon_ports", "jumper_half", {
        "total_minus_ng": "Non-Grant = ROUNDUP(Non-Grant passings/64); Grant = network total ROUNDUP(passings/64) - Non-Grant",
        "jumper_half": "Design standard: ROUNDUP(Jumper Calculator splitters / 2) = ROUNDUP(ROUNDUP(passings/32)/2) per column",
        "split_ratio": "one SFP per PON at the designed split ratio: ROUNDUP(passings/ratio) per column",
        "designed_pons": "one SFP per designed splitter (same Grant/Non-Grant split as the splitter line)",
    }, engine="jumper_half"),
    Policy("splitter_split", "Splitters Grant / Non-Grant", r"splitter_1x\d+", "grant_first", {
        "grant_first": "Design standard: designed count; Grant = ROUNDUP(grant passings/ratio), rest Non-Grant",
        "per_column": "blank-template formula: ROUNDUP(column passings/ratio) in every column",
    }),
    Policy("trays", "450B / 450D splice tray packages", r"tray_450[bd]", "pooled", {
        "pooled": "trays per location ROUNDUP(splices/cap); packages of 2 pooled per column",
        "per_location": "packages per location ROUNDUP(ROUNDUP(splices/cap)/2), summed",
        "fully_pooled": "ROUNDUP(ROUNDUP(all splices in the column/cap)/2)",
    }),
    Policy("max10_upgrade", "MAX10 +4 upgrade kits", r"max10_upgrades", "max10_nongrant", {
        "need_based": "a kit per 4 passings a MAX ped feeds above its 4 stock ports",
        "all_max10": "one kit for every MAX10 ped",
        "max10_nongrant": "blank-template default: every Non-Grant MAX10 (Grant 0)",
    }, engine="need_based"),
    Policy("drop_columns", "Drop footage columns", r"drop_ft_bom", "both", {
        "both": "Design standard: Non-Grant = drops of Non-Grant addresses; Grant = total - Non-Grant",
        "nongrant_only": "Credit River BOM: Non-Grant drops only, Grant column 0",
        "total_nongrant": "Melcher-Dallas BOM: all drop footage in the Non-Grant column",
    }, engine="nongrant_only"),
    Policy("route_footage", "Route footage rows 6-10", r"route_(ug_ft|aerial_ft|miles)", "route_labels", {
        "route_labels": "CalcFTG: sum of CX1-FTG-N2 route labels inside the boundary",
        "cable_totals": "sum of cable design length (TOTAL) by placement",
        "fiber_bearing": "route labels, minus UG trench with no fiber cable within 200 ft",
    }),
    Policy("cable_split", "Cable Grant / Non-Grant split", r"cable_\d{3}", "span", {
        "span": "routed cable split at splices/structures, each span by majority area",
        "length": "routed cable length inside the Non-Grant polygons",
    }),
    Policy("ground_kits", "Ground wire kits (FE0-07264810)", r"grounding_points", "template_note", {
        "template_note": "blank-template note: splices named ...G, first in line after the OLM, names ending in 0, end-of-line peds",
        "g_suffix": "splices whose name ends in G only",
        "not_ordered": "not ordered separately (0); the MAX peds already include a grounding bar and wire kit",
    }),
    Policy("olm_column", "OLM equipment column", r"olm(_ground|_aerial)?", "grant_if_any", {
        "grant_if_any": "Design standard: Grant column unless the OLM area has no grant passings",
        "location": "column of the OLM block's location",
    }),
]
BY_NAME = {p.name: p for p in POLICIES}


def _put(tk: Takeoff, key: str, net: str, area: str, value: float, unit: str, method: str):
    tk.q[(key, net, area)] = Qty(key, net, area, value, unit, method, [])


def compute_variants(tk: Takeoff) -> None:
    """Create `key@option` for every policy option. The engine's base value is the default option."""
    # default variants = copy of the engine result
    for (k, n, a), q in list(tk.q.items()):
        if "@" in k:
            continue
        for p in POLICIES:
            if p.owns(k):
                tk.q[(f"{k}@{p.base_option}", n, a)] = Qty(f"{k}@{p.base_option}", n, a, q.value, q.unit, q.method, q.evidence)
    nets = tk.networks
    for n in nets:
        ratio = tk.extra["ratio"].get(n, 64)
        sk = f"splitter_1x{ratio}"
        for a in AREAS:
            p = tk.get("passings", n, a, 0)
            _put(tk, f"pon_ports@split_ratio", n, a, math.ceil(p / ratio) if p else 0, "EA", f"ROUNDUP(passings/{ratio})")
            # total - Non-Grant: ROUNDUP(ROUNDUP(x/32)/2) == ROUNDUP(x/64)
            tot_p, ng_p = tk.total("passings", n), tk.get("passings", n, NONGRANT, 0)
            ng_sfp = math.ceil(ng_p / 64) if ng_p else 0
            _put(tk, "pon_ports@total_minus_ng", n, a, ng_sfp if a == NONGRANT else (math.ceil(tot_p / 64) if tot_p else 0) - ng_sfp,
                 "EA", "Non-Grant ROUNDUP(NG passings/64); Grant = ROUNDUP(total/64) - Non-Grant")
            _put(tk, f"pon_ports@designed_pons", n, a, tk.get(sk, n, a, 0), "EA", "designed splitters in the column")
            for r in (32, 64):
                if r == ratio:
                    _put(tk, f"splitter_1x{r}@per_column", n, a, math.ceil(p / r) if p else 0, "EA", f"ROUNDUP(column passings/{r})")
                else:  # a second ratio is always the designed count (see derived())
                    _put(tk, f"splitter_1x{r}@per_column", n, a, tk.get(f"splitter_1x{r}", n, a, 0), "EA", "designed (second ratio)")
            m10 = tk.get("ped_max10", n, a, 0)
            _put(tk, "max10_upgrades@all_max10", n, a, m10, "EA", "every MAX10")
            _put(tk, "max10_upgrades@max10_nongrant", n, a, m10 if a == NONGRANT else 0, "EA", "Non-Grant MAX10")
            if ("drop_ft_bom", n, a) in tk.q:
                _put(tk, "drop_ft_bom@both", n, a, tk.get("drop_ft", n, a, 0), "FT", "drops in their own column (Grant = total - Non-Grant)")
                _put(tk, "drop_ft_bom@nongrant_only", n, a, tk.get("drop_ft", n, a, 0) if a == NONGRANT else 0, "FT", "Non-Grant drops only")
                _put(tk, "drop_ft_bom@total_nongrant", n, a, tk.total("drop_ft", n) if a == NONGRANT else 0, "FT", "all drops in Non-Grant")
            ug, ar = tk.get("cable_ug_ft", n, a, 0), tk.get("cable_aerial_ft", n, a, 0)
            _put(tk, "route_ug_ft@cable_totals", n, a, round(ug), "FT", "cable TOTAL, UG")
            _put(tk, "route_aerial_ft@cable_totals", n, a, round(ar), "FT", "cable TOTAL, aerial")
            _put(tk, "route_miles@cable_totals", n, a, round((ug + ar) / 5280.0, 4), "MI", "cable TOTAL / 5280")
            nofib = sum(v for nn, aa, v, _h, _p in tk.extra.get("trench_no_fiber", []) if nn == n and aa == a)
            rug, rar = tk.get("route_ug_ft", n, a, 0), tk.get("route_aerial_ft", n, a, 0)
            _put(tk, "route_ug_ft@fiber_bearing", n, a, rug - nofib, "FT", "route labels minus trench with no fiber cable")
            _put(tk, "route_aerial_ft@fiber_bearing", n, a, rar, "FT", "route labels (fiber-bearing strand)")
            _put(tk, "route_miles@fiber_bearing", n, a, round((rug - nofib + rar) / 5280.0, 4), "MI", "fiber-bearing route / 5280")
    # trays
    caps = {"B": 24, "D": 48}
    for L in "BD":
        key = f"tray_450{L.lower()}"
        if not any(k == key for k, _n, _a in tk.q):
            continue
        for n in nets:
            for a in AREAS:
                encl = [s for (nn, aa, ll, s, _nm) in tk.extra["enclosures"] if nn == n and aa == a and ll == L]
                _put(tk, f"{key}@per_location", n, a, sum(math.ceil(math.ceil(s / caps[L]) / 2) for s in encl if s), "PKG", "per location")
                tot = sum(encl)
                _put(tk, f"{key}@fully_pooled", n, a, math.ceil(math.ceil(tot / caps[L]) / 2) if tot else 0, "PKG", "fully pooled")
    # cable split by length
    cable_keys = {k for k, _n, _a in tk.q if re.fullmatch(r"cable_\d{3}", k)}
    cable_keys |= {f"cable_{c.fibers:03d}" for c in tk.cables if c.network in nets}
    for k in sorted(cable_keys):
        for n in nets:
            for a in AREAS:
                _put(tk, f"{k}@length", n, a, 0, "FT", "routed length inside Non-Grant polygons")
    for c in tk.cables:
        if c.network not in nets:
            continue
        f = c.ng_fraction_length if c.ng_fraction_length is not None else (c.ng_fraction or 0)
        k = f"cable_{c.fibers:03d}@length"
        tk.q[(k, c.network, NONGRANT)].value += c.total_ft * f
        tk.q[(k, c.network, GRANT)].value += c.total_ft * (1 - f)
    for (k, n, a), q in tk.q.items():
        if k.endswith("@length") and k.startswith("cable_"):
            q.value = round(q.value)
    # ground kits
    for n in nets:
        for a in AREAS:
            if ("grounding_points", n, a) not in tk.q:
                continue
            rows = [nm for (nn, aa, nm, why) in tk.extra.get("ground", []) if nn == n and aa == a]
            _put(tk, "grounding_points@g_suffix", n, a, sum(1 for nm in rows if nm.endswith("G")), "EA", "splices named ...G")
            _put(tk, "grounding_points@not_ordered", n, a, 0, "EA", "not ordered separately")
    # OLM by location
    for n in nets:
        for a in AREAS:
            for k in ("olm", "olm_ground", "olm_aerial"):
                _put(tk, f"{k}@location", n, a, 0, "EA", "OLM block location")
    for n, loc, aerial, _h in tk.extra["olms"]:
        if n in nets:
            for k in ("olm", "olm_aerial" if aerial else "olm_ground"):
                tk.q[(f"{k}@location", n, loc)].value += 1


def load_selection(path: str | Path | None = None) -> dict[str, str]:
    p = Path(path) if path else CONFIG
    if not p.exists():
        return {}
    return json.loads(p.read_text()).get("selected", {})


def apply(tk: Takeoff, selection: dict[str, str]) -> None:
    """Copy the selected option of every policy into the base keys."""
    for p in POLICIES:
        opt = selection.get(p.name, p.default)
        if opt not in p.options:
            tk.check(f"policy {p.name}", False, f"unknown option '{opt}' - default '{p.default}' used", warn=True)
            opt = p.default
        tk.policy_used[p.name] = opt
        for (k, n, a), q in list(tk.q.items()):
            if "@" in k:
                base, o = k.split("@", 1)
                if o == opt and p.owns(base):
                    tk.q[(base, n, a)] = Qty(base, n, a, q.value, q.unit, f"{q.method} [policy {p.name}={opt}]", q.evidence)


def calibrate(tk: Takeoff, rules, ref) -> list[dict]:
    """Score every policy option against an approved BOM (cells matched / compared)."""
    out = []
    for p in POLICIES:
        # a row left blank in every column of the approved BOM was not filled in: no evidence either way
        rows = [r for r in rules if r.value and p.owns(r.value) and r.key in ref.values
                and any(v is not None for v in ref.values[r.key].values())]
        if not rows:
            continue
        for opt, desc in p.options.items():
            matched = cells = 0
            err = 0.0
            for r in rows:
                tol = 0.01 if r.unit == "MI" else 0.5
                for n in tk.networks:
                    for a in AREAS:
                        if (n, a) not in ref.columns:
                            continue
                        rv = ref.values[r.key].get((n, a))
                        av = tk.get(f"{r.value}@{opt}", n, a)
                        if av is None and (r.value, n, a) not in tk.q:
                            continue  # not computable for this network (e.g. no drop lines)
                        cells += 1
                        diff = abs((av or 0) - (rv or 0))
                        err += diff
                        matched += diff <= tol
            out.append(dict(policy=p.name, title=p.title, option=opt, description=desc, matched=matched, cells=cells,
                            abs_error=round(err, 2), default=opt == p.default, selected=tk.policy_used.get(p.name) == opt))
    best = {}
    for row in out:
        k = row["policy"]
        cur = best.get(k)
        # ties go to the documented default (design standard / AutoCAD routine) before total error
        key = (row["matched"], row["default"], -row["abs_error"])
        if cur is None or key > (cur["matched"], cur["default"], -cur["abs_error"]):
            best[k] = row
    for row in out:
        row["best"] = best[row["policy"]] is row
    return out


def learn(rows: list[dict], job: str, path: str | Path | None = None) -> dict:
    """Merge calibration scores into the knowledge file and re-select the best option per policy."""
    p = Path(path) if path else CONFIG
    data = json.loads(p.read_text()) if p.exists() else {}
    ev = data.setdefault("evidence", {})
    for r in rows:
        ev.setdefault(r["policy"], {}).setdefault(r["option"], {})[job] = {"matched": r["matched"], "cells": r["cells"], "abs_error": r["abs_error"]}
    sel = data.setdefault("selected", {})
    for pol in POLICIES:
        scores = []
        for opt in pol.options:
            jobs = ev.get(pol.name, {}).get(opt, {})
            m = sum(j["matched"] for j in jobs.values())
            c = sum(j["cells"] for j in jobs.values())
            e = sum(j["abs_error"] for j in jobs.values())
            if c:
                scores.append(((m / c, opt == pol.default, -e), opt))
        if scores:
            sel[pol.name] = max(scores)[1]
    data["_comment"] = ("Policy options learned from approved BOMs (python -m fttx_bom ... --reference BOM --learn). "
                        "'selected' is used for every new BOM; 'evidence' keeps per-job scores (cells matched / compared).")
    p.write_text(json.dumps(data, indent=2))
    return sel
