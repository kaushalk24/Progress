"""Deep check: inspect every input and the engine results, list every problem with
severity, the BOM lines it affects, how to fix it and (when it has one) its drawing
location. Locations are exported as an AutoCAD script that circles each issue.

Severity
  ERROR  a BOM quantity is (or may be) wrong until this is fixed
  WARN   verify - the BOM is computed but a design/input inconsistency exists
  INFO   for awareness (e.g. objects close to a Grant boundary)
"""
from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from ..extract.model import Drawing
from .geometry import area, dist, point_polyline_distance, polyline_length
from .network import Classifier
from .takeoff import SEG_RE, ServedIndex, Takeoff, addr_tokens, num


@dataclass
class Issue:
    severity: str
    category: str
    code: str
    network: str
    message: str
    affects: str
    fix: str
    x: float | None = None
    y: float | None = None


SEV_ORDER = {"ERROR": 0, "WARN": 1, "INFO": 2}

# engine check name prefix -> (category, code, affects, fix)
ENGINE_MAP = [
    ("passings vs address list", "Passings", "PASSINGS_MISMATCH", "Passing counts",
     "Compare CX1-COUNT / CX1-COMCNT house counts with the address list; remove duplicate address blocks or fix HC values"),
    ("address block not in address list", "Addresses", "GRANT_ADDRESS_NOT_SERVED", "Residential/Commercial grant counts",
     "Address on GRANTADDRESS layer is not in the address list - fix the block text or the address list"),
    ("cable label parse", "Cable", "CABLE_LABEL_UNREADABLE", "Fiber cable lines", "Fix the fiberinfo block attributes (SEGNUM 'A TO B FCnnn', TTL, TOTAL)"),
    ("cable label fiber count", "Cable", "CABLE_TTL_MISMATCH", "Fiber cable lines", "TTL attribute disagrees with FCnnn in SEGNUM - correct the label"),
    ("duplicate cable label", "Cable", "CABLE_LABEL_DUPLICATE", "Fiber cable lines", "Delete the extra fiberinfo label (counted once)"),
    ("cable route", "Cable", "CABLE_ROUTE_NOT_FOUND", "Cable Grant/Non-Grant split",
     "Cable polylines do not connect the two splice points (gap, or end point has no splice symbol) - join the polylines / add the MC_SPLICE block"),
    ("cable missing DWG label", "Cable", "CABLE_ONLY_IN_REPORT", "Fiber cable lines", "Segment exists in the splice reports but has no fiberinfo label - add the label"),
    ("cable label vs splice report", "Cable", "CABLE_REPORT_MISMATCH", "Fiber cable lines", "Fiber count / design length differ between DWG label and splice report - re-export one of them"),
    ("cable fiber count without BOM row", "Cable", "CABLE_SIZE_UNMAPPED", "Fiber cable lines", "Add a template row / rule for this fiber count"),
    ("splice report enclosure", "Splice reports", "ENCLOSURE_TYPE_BLANK", "FOSC enclosures, trays", "Set Enclosure Type in the design tool and re-export the report"),
    ("duplicate splice report", "Splice reports", "REPORT_DUPLICATE", "FOSC enclosures, trays", "Remove the duplicate report file"),
    ("splitters vs splice reports", "Splitters", "SPLITTER_MISMATCH", "Splitters, SFP", "Designed couplers in the splice reports differ from ROUNDUP(passings/ratio) - check the PON design"),
    ("splitters vs address-list PONs", "Splitters", "PON_MISMATCH", "Splitters, SFP", "Address-list PON count differs from the splitter design"),
    ("designed splitters", "Splitters", "SPLITTER_DESIGN_DIFF", "Splitters", "Designed splitter count used; verify against passings"),
    ("split ratio", "Splitters", "SPLIT_RATIO_ASSUMED", "Splitters, SFP", "No PLC COUPLER rows found - supply the splice reports or address list"),
    ("SFP vs designed PONs", "Policies", "SFP_POLICY", "XGS SFP+", "Per-column rounding gives more/fewer SFP than designed PONs - check the Policies sheet"),
    ("drop lines", "Drops", "DROPS_MISSING", "Total Drop Footage", "Run FXAUTO (FX_DROPS.lsp) in AutoCAD and save the drawing"),
    ("drops vs passings", "Drops", "DROP_COUNT_MISMATCH", "Total Drop Footage", "Run FXMISSING in AutoCAD, draw the missing drops (FXDROP) and save"),
    ("drop without address", "Drops", "DROP_NO_ADDRESS", "Total Drop Footage", "Drop line does not end at an address - move or delete it"),
    ("objects outside boundaries", "Boundaries", "OUTSIDE_BOUNDARY", "All lines of that network", "See Network Assignment sheet; extend the OLM boundary if an object belongs inside"),
    ("unassigned objects", "Boundaries", "UNASSIGNED", "All lines", "Objects outside every OLM boundary and the transport corridor are not counted"),
    ("policy", "Policies", "POLICY_UNKNOWN", "Policy lines", "Fix the option name in the policy file"),
    ("passings sign", "Passings", "PASSINGS_NEGATIVE", "Passing counts", "More grant address blocks than served passings - check GRANTADDRESS layer"),
]


def _from_engine(tk: Takeoff) -> list[Issue]:
    out = []
    for c in tk.checks:
        if c.status == "PASS":
            continue
        cat, code, aff, fix = "Engine", "CHECK", "", ""
        for pref, ca, co, af, fx in ENGINE_MAP:
            if c.name.startswith(pref):
                cat, code, aff, fix = ca, co, af, fx
                break
        net = next((n for n in tk.networks if n in c.name or n in c.detail), "")
        sev = "ERROR" if c.status == "FAIL" else "WARN"
        if code in ("OUTSIDE_BOUNDARY",):
            sev = "INFO"
        out.append(Issue(sev, cat, code, net, c.detail, aff, fix))
    return out


def _grid(items, cell=100.0):
    g = defaultdict(list)
    for it, p in items:
        g[(int(p[0] // cell), int(p[1] // cell))].append((it, p))
    return g


def _near(g, p, r, cell=100.0):
    gx, gy = int(p[0] // cell), int(p[1] // cell)
    k = int(r // cell) + 1
    for dx in range(-k, k + 1):
        for dy in range(-k, k + 1):
            for it, q in g.get((gx + dx, gy + dy), []):
                if dist(p, q) <= r:
                    yield it, q


def run_doctor(d: Drawing, conv: dict, cls: Classifier, tk: Takeoff, address_lists, reports, res=None, ver=None) -> list[Issue]:
    issues = _from_engine(tk)
    add = issues.append
    nets = set(tk.networks)

    def net_of(p):
        return cls.network_of(p, "doctor") or ""

    def in_scope(p):
        n = net_of(p)
        return (not nets) or n in nets, n

    # ---------------------------------------------------------------- drawing / CAD reader
    for w in d.warnings:
        add(Issue("ERROR" if "CRITICAL" in w else "INFO", "Drawing", "CAD_READ", "", w, "All lines",
                  "Re-save the DWG in AutoCAD (AUDIT, then SAVEAS 2018) or supply a DXF export" if "CRITICAL" in w else "Non-critical reader status - no action"))
    layers_used = Counter(e.layer for e in d.inserts) + Counter(p.layer for p in d.polylines) + Counter(t.layer for t in d.texts)
    needed_layers = {
        "Non-Grant polygons": [conv["nongrant_layer"]],
        "Grant addresses": [conv["grant_address_layer"]],
        "Route footage (rows 6-10)": conv["route_layers"]["ug_trench"],
        "Cable routing": conv["cable_layers"]["underground"],
        "Drop footage": conv["route_layers"]["ug_drop"],
    }
    for what, lays in needed_layers.items():
        if not any(layers_used.get(l) for l in lays):
            add(Issue("WARN", "Drawing", "LAYER_EMPTY", "", f"No objects on layer(s) {lays}", what,
                      f"Check the drawing uses the standard layer names (config/conventions.json) for {what.lower()}"))
    names_present = Counter(i.name for i in d.inserts)
    for key, sev, what in (("olm", "ERROR", "OLM equipment, power"), ("cable_label", "ERROR", "Fiber cable lines"),
                           ("ped_max10", "WARN", "MAX10 peds"), ("ped_max5", "WARN", "MAX5 peds"),
                           ("house_count", "ERROR", "Passing counts"), ("splice_point", "WARN", "Cable routing, Grant split")):
        if not any(names_present.get(n) for n in conv["blocks"][key]["names"]):
            add(Issue(sev, "Drawing", "BLOCK_MISSING", "", f"No {conv['blocks'][key]['names']} blocks in the drawing", what,
                      "Wrong drawing, or a renamed block - add the name to config/conventions.json"))
    mapped = {n for b in conv["blocks"].values() for n in b["names"]} | set(conv.get("ignore_blocks", []))
    for lay in ("RTE_UGPOLES", "RTE_AEPOLES", "Fiber Node", "Fiber Splice", "DES_TAPS"):
        other = Counter(i.name for i in d.inserts if i.layer == lay and i.name not in mapped)
        for name, cnt in other.items():
            add(Issue("INFO" if lay.startswith("DES") else "WARN", "Drawing", "UNMAPPED_BLOCK", "",
                      f"{cnt} x '{name}' on {lay} is not mapped to any BOM line", "Possibly a missing material (e.g. GOAT ped, tap)",
                      "If it is a material, add a block mapping and a rule; otherwise ignore"))

    # ---------------------------------------------------------------- boundaries
    for note in cls.notes:
        if "no DWG boundary" in note or "contains several" in note:
            add(Issue("ERROR", "Boundaries", "NETWORK_BOUNDARY", "", note, "All lines",
                      "Draw / label the OLM boundary (layer 'OLM Boundary - Designed Not Built' with the network name inside)"))
    for n in tk.networks:
        if cls.networks and n in cls.networks and not any(cls.networks[n].contains(r.poly[0]) for r in cls.nongrant):
            add(Issue("INFO", "Boundaries", "NO_NONGRANT", n, "No Non-Grant polygon inside this network - everything counts as Grant",
                      "Every Grant/Non-Grant split", "Confirm the network is fully Grant, else draw the Non-Grant polygons"))
    for r in cls.nongrant:
        a = area(r.poly)
        if a < 500:
            p = r.poly[0]
            add(Issue("WARN", "Boundaries", "NONGRANT_TINY", net_of(p), f"Non-Grant polygon {r.handle} is only {a:.0f} sq ft",
                      "Grant/Non-Grant split", "Probably a drafting error - delete or fix the polygon", p[0], p[1]))
    edge_items = [(i, i.pt) for i in d.inserts if i.name in set(conv["blocks"]["ped_max10"]["names"] + conv["blocks"]["ped_max5"]["names"]
                                                                       + conv["blocks"]["vault"]["names"])]
    for ins, p in edge_items:
        ok, n = in_scope(p)
        if not ok:
            continue
        dd = min((point_polyline_distance(p, r.poly, True) for r in cls.nongrant if r.bb[0] - 30 <= p[0] <= r.bb[2] + 30
                  and r.bb[1] - 30 <= p[1] <= r.bb[3] + 30), default=None)
        if dd is not None and dd <= 15:
            add(Issue("INFO", "Boundaries", "NEAR_GRANT_EDGE", n, f"{ins.name} {ins.handle} is {dd:.1f} ft from a Non-Grant edge "
                      f"(counted {cls.area_of(p)})", f"{ins.name} Grant/Non-Grant split", "Confirm which side it belongs to; move the polygon edge if needed", p[0], p[1]))

    # ---------------------------------------------------------------- addresses
    addr_blocks = [i for i in d.inserts if i.name in set(conv["blocks"]["res_address"]["names"] + conv["blocks"]["com_address"]["names"])]
    seen = defaultdict(list)
    for a in addr_blocks:
        num_ = a.attr("STREET_NUMBER") or a.attr("BUILDING_ADDRESS")
        street = a.attr("STREET_NAME") or a.attr("BUILDING_NAME")
        seen[addr_tokens(f"{num_} {street}")].append(a)
    for toks, blocks in seen.items():
        if len(blocks) < 2 or not toks:
            continue
        for i in range(1, len(blocks)):
            if dist(blocks[0].pt, blocks[i].pt) < 400:
                ok, n = in_scope(blocks[i].pt)
                if ok:
                    add(Issue("WARN", "Addresses", "ADDRESS_DUPLICATE", n, f"Address '{' '.join(toks)}' has {len(blocks)} blocks "
                              f"({dist(blocks[0].pt, blocks[i].pt):.0f} ft apart)", "Passing counts, drops",
                              "Delete the duplicate address block (and its house count)", blocks[i].pt[0], blocks[i].pt[1]))
                break
    for n in tk.networks:
        al = address_lists.get(n)
        if not al:
            add(Issue("ERROR", "Addresses", "ADDRESS_LIST_MISSING", n, "No address list supplied for this network", "Passing counts, grant counts",
                      "Add the network's address list"))
            continue
        for iss in al.issues:
            add(Issue("ERROR", "Addresses", "ADDRESS_LIST_FORMAT", n, iss, "Passing counts", "Use the standard address-list export"))
        drawn = {addr_tokens(f"{a.attr('STREET_NUMBER') or a.attr('BUILDING_ADDRESS')} {a.attr('STREET_NAME') or a.attr('BUILDING_NAME')}")
                 for a in addr_blocks}
        missing = []
        for s in al.served:
            if re.search(r"\b(UNIT|APT|STE|SUITE|BLDG)\b|#", s.address.upper()):
                continue  # MDU / multi-unit addresses are drawn as one FMMULTIADD building without a number
            t = addr_tokens(s.address)
            if not any(t[:len(x)] == x for x in drawn if x and len(x) <= len(t)):
                missing.append(s.address)
        if missing:
            add(Issue("WARN", "Addresses", "SERVED_NOT_DRAWN", n, f"{len(missing)} served address(es) have no matching address block: "
                      + "; ".join(missing[:8]) + (" ..." if len(missing) > 8 else ""), "Grant counts",
                      "Add the address block or correct the street number/name (non-grant addresses are corrected in SpatialNet)"))
        ports = Counter((s.pon, s.port) for s in al.served)
        dup = [k for k, v in ports.items() if v > 1]
        if dup:
            add(Issue("ERROR", "Addresses", "PON_PORT_DUPLICATE", n, f"PON/port used twice in the address list: {dup[:6]}", "Splitters, SFP",
                      "Regenerate the address list"))

    # ---------------------------------------------------------------- cable labels
    for ins in d.inserts:
        if ins.name not in conv["blocks"]["cable_label"]["names"]:
            continue
        ok, n = in_scope(ins.pt)
        if not ok:
            continue
        ttl, req, spare = num(ins.attr("TTL")), num(ins.attr("REQ")), num(ins.attr("SPARE"))
        ftg, slk, tot = num(ins.attr("FTG")), num(ins.attr("SLK")), num(ins.attr("TOTAL"))
        seg = ins.attr("SEGNUM")
        if None not in (ftg, slk, tot) and abs(ftg + slk - tot) > 0.5:
            add(Issue("ERROR", "Cable", "CABLE_TOTAL_MISMATCH", n, f"{seg}: FTG {ftg:g} + SLK {slk:g} != TOTAL {tot:g}", "Fiber cable lines (uses TOTAL)",
                      "Recalculate the fiberinfo label", ins.pt[0], ins.pt[1]))
        if None not in (ttl, req) and req > ttl:
            add(Issue("ERROR", "Cable", "CABLE_UNDERSIZED", n, f"{seg}: required fibers {req:g} > cable size {ttl:g}", "Fiber cable lines",
                      "Upsize the cable in the design", ins.pt[0], ins.pt[1]))
        if None not in (ttl, req, spare) and abs(req + spare - ttl) > 0.5:
            add(Issue("WARN", "Cable", "CABLE_REQ_SPARE", n, f"{seg}: REQ {req:g} + SPARE {spare:g} != TTL {ttl:g}", "Fiber cable lines",
                      "Refresh the fiber counts on the label", ins.pt[0], ins.pt[1]))
    for c in tk.cables:
        # splice symbols sit beside the peds, so short cables always differ a little: need both a big ratio and > 150 ft
        if c.path_ft and c.route_ft and not (0.8 <= c.path_ft / c.route_ft <= 1.25) and abs(c.path_ft - c.route_ft) > 150:
            lbl = next((i for i in d.inserts if i.handle == c.handle), None)
            add(Issue("WARN", "Cable", "CABLE_ROUTE_LENGTH", c.network or "", f"{c.name}: drawn route {c.path_ft:.0f} ft vs label FTG {c.route_ft:g} ft "
                      f"({c.path_ft / c.route_ft:.2f}x)", "Cable Grant/Non-Grant split; possibly the footage",
                      "Check the label footage or the cable polylines (routing may follow a different cable)",
                      lbl.pt[0] if lbl else None, lbl.pt[1] if lbl else None))

    # ---------------------------------------------------------------- drops
    drop_layers = conv["route_layers"]["ug_drop"]
    drops = [p for p in d.polylines if p.layer in drop_layers and len(p.points) >= 2]
    if drops:
        peds = [(i, i.pt) for i in d.inserts if i.name in set(conv["blocks"]["ped_max10"]["names"] + conv["blocks"]["ped_max5"]["names"])]
        pg = _grid(peds)
        ends = _grid([(pl, e) for pl in drops for e in (pl.points[0], pl.points[-1])])
        for pl in drops:
            L = polyline_length(pl.points)
            ok, n = in_scope(pl.points[0])
            if not ok:
                continue
            if L > 1000:
                add(Issue("WARN", "Drops", "DROP_LONG", n, f"Drop {pl.handle} is {L:.0f} ft", "Total Drop Footage",
                          "Confirm the feeding ped (FX_DROPS max is 1,500 ft)", pl.points[0][0], pl.points[0][1]))
            if not any(True for _ in _near(pg, pl.points[0], 20)) and not any(True for _ in _near(pg, pl.points[-1], 20)):
                add(Issue("WARN", "Drops", "DROP_NOT_FROM_PED", n, f"Drop {pl.handle} ({L:.0f} ft) does not start at a MAX ped",
                          "Total Drop Footage", "Redraw with FXDROP from the feeding ped", pl.points[0][0], pl.points[0][1]))
        mdu = set(conv["blocks"]["mdu_address"]["names"])
        for n in tk.networks:
            idx = ServedIndex(address_lists[n]) if n in address_lists else None
            if not tk.total("drop_count", n):
                continue
            for a in addr_blocks:
                if a.name in mdu or net_of(a.pt) != n:
                    continue
                toks = addr_tokens(f"{a.attr('STREET_NUMBER') or a.attr('BUILDING_ADDRESS')} {a.attr('STREET_NAME') or a.attr('BUILDING_NAME')}")
                if idx is not None and toks not in idx:
                    continue  # not served
                if not any(True for _ in _near(ends, a.pt, 25)):
                    add(Issue("WARN", "Drops", "ADDRESS_NO_DROP", n, f"Served address '{' '.join(toks)}' has no drop line", "Total Drop Footage",
                              "Run FXMISSING / FXDROP in AutoCAD", a.pt[0], a.pt[1]))

    # ---------------------------------------------------------------- splice reports vs drawing
    names_dwg = {i.attr("NAME").upper(): i.pt for i in d.inserts if i.name in conv["blocks"]["splice_point"]["names"]}
    for r in reports:
        if r.network not in nets:
            continue
        known = re.search(r"450\s*[A-D]|SPLICE CASE", r.enclosure or "", re.I)
        if r.enclosure and not known:
            add(Issue("WARN", "Splice reports", "ENCLOSURE_UNMAPPED", r.network, f"{r.name}: enclosure type '{r.enclosure}' has no BOM rule",
                      "FOSC enclosures", "Add a rule for this enclosure type"))
        if r.name.upper() not in names_dwg:
            add(Issue("WARN", "Splice reports", "REPORT_NOT_IN_DRAWING", r.network, f"Splice report {r.name} has no MC_SPLICE point in the drawing",
                      "Enclosure Grant/Non-Grant column, cable routing", "Add / rename the splice point, or remove the stale report"))
        for sg in r.segments:
            if sg.placement.lower() != "pigtail" and sg.design_length == 0:
                add(Issue("INFO", "Splice reports", "DESIGN_LENGTH_ZERO", r.network, f"{sg.name}: design length 0 in report {r.name}",
                          "Fiber cable lines (cross-check only)", "Normal for zero-length tails; otherwise re-export the report"))
        if r.format == "splice guide":
            add(Issue("INFO", "Splice reports", "SPLICE_GUIDE_FORMAT", r.network, f"{r.name} is a 'Fiber Optic Splice Guide' (no design lengths)",
                      "Cable cross-check", "Re-export as Splice Connections Report for full cross-checks"))
    rep_names = {r.name.upper() for r in reports}
    if reports:
        no_rep = defaultdict(list)
        for name, p in names_dwg.items():
            ok, n = in_scope(p)
            if ok and name not in rep_names:
                no_rep[n].append(name)
        for n, names in no_rep.items():
            add(Issue("INFO", "Splice reports", "SPLICE_NO_REPORT", n, f"{len(names)} splice points have no splice report (normal for "
                      f"pass-through peds): {', '.join(sorted(names)[:6])}{' ...' if len(names) > 6 else ''}",
                      "Trays (only reported splice locations are counted)", "Export reports for any FOSC location missing from the list"))

    # ---------------------------------------------------------------- policies that change the BOM
    from .policies import POLICIES

    for pol in POLICIES:
        used = tk.policy_used.get(pol.name)
        if not used:
            continue
        keys = sorted({k.split("@")[0] for k, _n, _a in tk.q if "@" in k and pol.owns(k.split("@")[0])})
        for key in keys:
            totals = {opt: sum(tk.get(f"{key}@{opt}", n, a, 0) or 0 for n in tk.networks for a in ("G", "NG")) for opt in pol.options}
            if len({round(v, 2) for v in totals.values()}) > 1:
                add(Issue("INFO", "Policies", "POLICY_MATTERS", "", f"{pol.title} ({key}): " +
                          ", ".join(f"{o}={v:g}{' (in use)' if o == used else ''}" for o, v in totals.items()),
                          key, "Options give different totals - calibrate against an approved BOM (--reference ... --learn) or set it in config/policies.json"))

    # ---------------------------------------------------------------- template / workbook
    if res is not None:
        for iss in res.issues:
            add(Issue("WARN", "Template", "TEMPLATE_ISSUE", "", iss, "Template", "Check the template layout"))
        for rep in res.formula_repairs:
            add(Issue("INFO", "Template", "TEMPLATE_FORMULA_REPAIRED", "", rep, rep.split()[0], "Template formula was inconsistent across columns - repaired from the first column"))
    if ver is not None:
        for name, st, detail in ver.checks:
            if st != "PASS":
                add(Issue("ERROR" if st == "FAIL" else "WARN", "Workbook", "WORKBOOK_CHECK", "", f"{name}: {detail}", "Output workbook",
                          "Report this as a tool bug" if st == "FAIL" else "Install LibreOffice to verify formulas"))
    issues.sort(key=lambda i: (SEV_ORDER.get(i.severity, 3), i.category, i.network, i.code))
    return issues


def write_issue_files(issues: list[Issue], prefix: Path) -> tuple[Path, Path]:
    """CSV of all issues + AutoCAD script circling every located issue (layers BOM_CHECK_*)."""
    csv_path = prefix.with_name(prefix.name + "_ISSUES.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["#", "Severity", "Category", "Code", "Network", "Message", "Affects", "How to fix", "X", "Y"])
        for k, i in enumerate(issues, 1):
            w.writerow([k, i.severity, i.category, i.code, i.network, i.message, i.affects, i.fix,
                        f"{i.x:.2f}" if i.x is not None else "", f"{i.y:.2f}" if i.y is not None else ""])
    scr = prefix.with_name(prefix.name + "_ISSUES.scr")
    colors = {"ERROR": (1, 60), "WARN": (2, 40), "INFO": (4, 25)}
    # running object snaps apply to typed points inside scripts: switch them off, restore at the end
    lines = ['(setq bomchk_os (getvar "OSMODE"))', '(setvar "OSMODE" 0)']
    for sev, (col, _r) in colors.items():
        lines += ["-LAYER", "M", f"BOM_CHECK_{sev}", "C", str(col), f"BOM_CHECK_{sev}", ""]
    for i in issues:
        if i.x is None:
            continue
        col, rad = colors.get(i.severity, (4, 25))
        lines += ["-LAYER", "S", f"BOM_CHECK_{i.severity}", "", "CIRCLE", f"{i.x:.3f},{i.y:.3f}", str(rad)]
    lines += ["-LAYER", "S", "0", "", '(setvar "OSMODE" bomchk_os)', ""]
    scr.write_text("\r\n".join(lines) + "\r\n", encoding="ascii", errors="replace")
    return csv_path, scr
