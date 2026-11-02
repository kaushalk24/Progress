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
from .geometry import area, dist, point_polyline_distance, point_segment_distance, polyline_length
from .network import Classifier
from .takeoff import (ON_PATH_FT, TRAY_CAPACITY, TRAYS_PER_CLOSURE, ServedIndex, Takeoff, addr_tokens, enclosure_letter,
                      network_from_splice_name, num, structure_area)


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
    ("mixed split ratios", "Splitters", "SPLIT_RATIO_MIXED", "Splitters 1x32 / 1x64, SFP", "Two split ratios designed in one network - both are written; confirm"),
    ("split ratio", "Splitters", "SPLIT_RATIO_ASSUMED", "Splitters, SFP", "No PLC COUPLER rows found - supply the splice reports or address list"),
    ("SFP vs designed PONs", "Policies", "SFP_POLICY", "XGS SFP+", "Per-column rounding gives more/fewer SFP than designed PONs - check the Policies sheet"),
    ("drop lines", "Drops", "DROPS_MISSING", "Total Drop Footage", "Run FXAUTO (FX_DROPS.lsp) in AutoCAD and save the drawing"),
    ("drops vs passings", "Drops", "DROP_COUNT_MISMATCH", "Total Drop Footage", "Run FXMISSING in AutoCAD, draw the missing drops (FXDROP) and save"),
    ("drop without address", "Drops", "DROP_NO_ADDRESS", "Total Drop Footage", "Drop line does not end at an address - move or delete it"),
    ("objects outside boundaries", "Boundaries", "OUTSIDE_BOUNDARY", "All lines of that network", "See Network Assignment sheet; extend the OLM boundary if an object belongs inside"),
    ("unassigned objects", "Boundaries", "UNASSIGNED", "All lines", "Objects outside every OLM boundary and the transport corridor are not counted"),
    ("policy", "Policies", "POLICY_UNKNOWN", "Policy lines", "Fix the option name in the policy file"),
    ("network boundary", "Boundaries", "NETWORK_BLANK", "Every line of the network", "Draw / label the OLM boundary; the network's BOM is blank until then"),
    ("RF support structure", "RF plant", "RF_EXCLUDED", "Vaults / L-boxes / aerial footage", "None - RF (coax) plant is not part of the FTTH BOM; check the structure carries no fiber"),
    ("block not defined", "Drawing", "BLOCK_NOT_DEFINED", "The line named in the message", "Block renamed in this drawing? Add its name to config/conventions.json"),
    ("splice report unreadable", "Splice reports", "REPORT_UNREADABLE", "FOSC enclosures, trays, splitters", "Re-export the splice report"),
    ("splice report cell", "Splice reports", "REPORT_CELL", "Cable cross-check", "Fix the cell in the export"),
    ("splice report network", "Splice reports", "REPORT_NETWORK", "Enclosure / splitter network", "Name the splice point with the network prefix or place it in the drawing"),
    ("enclosure type unknown", "Splice reports", "ENCLOSURE_UNMAPPED", "FOSC enclosures, trays", "Set a FOSC 450 A-D Enclosure Type, or add the type to non_bom_enclosures in conventions.json"),
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
        if code in ("OUTSIDE_BOUNDARY", "RF_EXCLUDED"):
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


PED_SPLICE_MAX_FT = 80.0  # a ped's splice symbol is drawn 20-60 ft from the ped block (NMK/DMI)
LARGE_CABLE = 48  # fibers


def ped_cable_roles(d: Drawing, conv: dict, tk: Takeoff, closures: set[str] | None = None) -> list[tuple]:
    """For every MAX ped: (ped insert, splice name, role, largest cable fibers at the splice).

    role: 'branch' (a cable starts there), 'end' (cables only end there) or 'pass'
    (cables only pass through, mid-span access). A splice belongs to a ped only when that ped is the
    splice's nearest housing (ped, vault or L-box), and splices made in a FOSC closure (`closures`,
    from the splice reports) are not ped splices - e.g. the OLM hub splice beside a MAX5."""
    spl = {}
    for i in d.inserts:
        if i.name in conv["blocks"]["splice_point"]["names"]:
            spl.setdefault((i.attr("NAME") or "").strip().upper(), i.pt)
    spl.pop("", None)
    sg = _grid([(n, p) for n, p in spl.items()])
    seg_grid = defaultdict(list)
    cell = 100.0
    for c in tk.cables:
        for a, b in zip(c.path, c.path[1:]):
            for gx in range(int(min(a[0], b[0]) // cell), int(max(a[0], b[0]) // cell) + 1):
                for gy in range(int(min(a[1], b[1]) // cell), int(max(a[1], b[1]) // cell) + 1):
                    seg_grid[(gx, gy)].append((c, a, b))
    starts, ends = defaultdict(list), defaultdict(list)
    for c in tk.cables:
        starts[c.a.upper()].append(c)
        ends[c.b.upper()].append(c)
    out = []
    names = set(conv["blocks"]["ped_max10"]["names"] + conv["blocks"]["ped_max5"]["names"])
    housing_names = names | set(conv["blocks"]["vault"]["names"] + conv["blocks"]["ug_lbox"]["names"])
    hg = _grid([(i, i.pt) for i in d.inserts if i.name in housing_names])
    for ped in (i for i in d.inserts if i.name in names):
        near = min(((dist(ped.pt, q), n, q) for n, q in _near(sg, ped.pt, PED_SPLICE_MAX_FT)), default=None)
        if near is None:
            continue
        _d, nm, q = near
        if closures and nm in closures:
            continue
        home = min(((dist(q, h.pt), h.handle) for h, _p in _near(hg, q, PED_SPLICE_MAX_FT)), default=None)
        if home and home[1] != ped.handle:
            continue  # the splice is housed in another (nearer) ped / vault / L-box
        through = {id(c): c for c, a, b in seg_grid.get((int(q[0] // cell), int(q[1] // cell)), [])
                   if c.a.upper() != nm and c.b.upper() != nm and point_segment_distance(q, a, b) <= ON_PATH_FT}
        cs = starts.get(nm, []) + ends.get(nm, []) + list(through.values())
        role = "branch" if starts.get(nm) else ("end" if ends.get(nm) and not through else "pass")
        out.append((ped, nm, role, max((c.fibers for c in cs), default=0)))
    return out


def run_doctor(d: Drawing, conv: dict, cls: Classifier, tk: Takeoff, address_lists, reports, res=None, ver=None) -> list[Issue]:
    issues = _from_engine(tk)
    add = issues.append
    nets = set(tk.networks)
    cls_pos = {i.attr("NAME").upper(): i.pt for i in d.inserts if i.name in conv["blocks"]["splice_point"]["names"]}

    def net_of(p):
        # resolve without recording: the deep check must not add rows to the classifier's assignment log
        n = cls.resolve(p)[0] if hasattr(cls, "resolve") else cls.network_of(p, "doctor")
        return n if n and (not nets or n in nets) else ""

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
                           ("house_count", "ERROR", "Passing counts"), ("splice_point", "WARN", "Cable routing, Grant split"),
                           # 0 is written for these lines, so a renamed symbol would pass silently (the old block
                           # definition often stays in drawings made from a company template)
                           ("vault", "WARN", "Vaults (0 written)"), ("ug_lbox", "INFO", "UG L-boxes (0 written)"),
                           ("route_footage", "ERROR", "Route footage rows 6-10"), ("res_address", "WARN", "Grant residential passings")):
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
        elif note.startswith("boundary fallback"):
            add(Issue("WARN", "Boundaries", "NETWORK_BOUNDARY_FALLBACK", "", note, "All drawing quantities",
                      "Label the OLM boundary with the network name so objects outside it are excluded"))
        elif "excluded from this job" in note or "corridor excluded" in note:
            add(Issue("INFO", "Boundaries", "OTHER_NETWORKS", "", note, "All drawing quantities",
                      "None - objects of the other networks are not counted in this BOM"))
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
                      f"(counted {'Grant' if structure_area(cls, p, conv.get('boundary_structure_tolerance_ft', 5.0)) == 'G' else 'Non-Grant'})", f"{ins.name} Grant/Non-Grant split", "Confirm which side it belongs to; move the polygon edge if needed", p[0], p[1]))

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
            sev = "WARN" if iss.startswith("header differs") else "ERROR"
            add(Issue(sev, "Addresses", "ADDRESS_LIST_FORMAT", n, iss, "Passing counts", "Use the standard address-list export"))
        if not al.served:
            add(Issue("ERROR", "Addresses", "ADDRESS_LIST_EMPTY", n, "The address list has no served rows (PON NAME + PON PORT)",
                      "Passing counts, splitters, SFP", "Check the export; the drawing count blocks were used instead"))
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
        same = Counter(" ".join(addr_tokens(s.address)) for s in al.served
                       if not re.search(r"\b(UNIT|APT|STE|SUITE|BLDG)\b|#", s.address.upper()))
        twice = [a for a, v in same.items() if a and v > 1]
        if twice:
            add(Issue("WARN", "Addresses", "ADDRESS_SERVED_TWICE", n, f"{len(twice)} address(es) are served on more than one PON port: "
                      + "; ".join(twice[:6]) + (" ..." if len(twice) > 6 else "") + " - each port counts as a passing",
                      "Passings, splitters, SFP",
                      "Remove the duplicate row from the address list, unless the address really has several units"))
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
        ends = {network_from_splice_name(e.upper()) for e in (c.a, c.b)} - {None}
        if len(ends) > 1 and c.path:
            mid = c.path[len(c.path) // 2]
            add(Issue("INFO", "Cable", "CABLE_CROSS_NETWORK", c.network or "", f"{c.name} joins {sorted(ends)}; booked wholly to its "
                      f"A-end network {c.network} (convention, network totals agree with the approved BOM)", "Fiber cable lines",
                      "None unless the cable should be split between OLM BOMs", mid[0], mid[1]))
    for c in tk.cables:
        # splice symbols sit beside the peds, so short cables always differ a little: need both a big ratio and > 150 ft
        if c.path_ft and c.route_ft and not (0.8 <= c.path_ft / c.route_ft <= 1.25) and abs(c.path_ft - c.route_ft) > 150:
            lbl = next((i for i in d.inserts if i.handle == c.handle), None)
            add(Issue("WARN", "Cable", "CABLE_ROUTE_LENGTH", c.network or "", f"{c.name}: drawn route {c.path_ft:.0f} ft vs label FTG {c.route_ft:g} ft "
                      f"({c.path_ft / c.route_ft:.2f}x)", "Cable Grant/Non-Grant split; possibly the footage",
                      "Check the label footage or the cable polylines (routing may follow a different cable)",
                      lbl.pt[0] if lbl else None, lbl.pt[1] if lbl else None))

    # ---------------------------------------------------------------- Grant address layer vs Non-Grant boundary
    # Grant / Non-Grant passings follow the GRANTADDRESS layer (both approved BOMs); the design standard "Non-Grant =
    # inside the Non-Grant boundaries" agrees only when every served address sits on the matching side.
    for n in tk.networks:
        if n not in address_lists or not address_lists[n].served:
            continue
        idx = ServedIndex(address_lists[n])
        for a in d.inserts:
            if a.name not in conv["blocks"]["res_address"]["names"] or net_of(a.pt) != n:
                continue
            if addr_tokens(f"{a.attr('STREET_NUMBER')} {a.attr('STREET_NAME')}") not in idx:
                continue
            grant_layer, ng_area = a.layer == conv["grant_address_layer"], cls.area_of(a.pt) == "NG"
            if grant_layer == ng_area:
                where = "inside a Non-Grant polygon" if ng_area else "outside every Non-Grant polygon"
                add(Issue("WARN", "Addresses", "ADDRESS_LAYER_VS_BOUNDARY", n,
                          f"Served address {a.attr('STREET_NUMBER')} {a.attr('STREET_NAME')} is on layer {a.layer} but {where}",
                          "Grant / Non-Grant passings, splitters, SFP",
                          "Move the address to the right layer (GRANTADDRESS = BEAD location) or fix the Non-Grant boundary", a.pt[0], a.pt[1]))

    # ---------------------------------------------------------------- plant that is not part of this design
    excl = Counter(cat for cat, *_x in tk.extra.get("scope", {}).get("excluded", []))
    for cat, cnt in sorted(excl.items()):
        add(Issue("INFO", "Scope", "EXCLUDED_PLANT", "", f"{cnt} objects excluded as '{cat}' (listed on the audit's Excluded sheet)",
                  "All drawing quantities", "None - check the list if this design should include any of them"))

    # ---------------------------------------------------------------- route footage without fiber (one note per network)
    by_net = defaultdict(list)
    for net, _area, ftg, handle, pt in tk.extra.get("trench_no_fiber", []):
        by_net[net].append((ftg, handle, pt))
    for net, rows in by_net.items():
        big = max(rows)
        add(Issue("INFO", "Route", "TRENCH_NO_FIBER", net,
                  f"{len(rows)} trench labels ({sum(r[0] for r in rows):,.0f} ft) have no fiber cable within 200 ft - counted in UG footage; "
                  f"largest {big[1]} ({big[0]:g} ft, circled)", "UG / route footage rows 6-10",
                  "If a trench carries only RF (coax) or is not FTTH route, it should not be in the FTTH route (policy route_footage=fiber_bearing)",
                  big[2][0], big[2][1]))

    # ---------------------------------------------------------------- cable spans crossing the boundary
    for net, seg, L, other, ar in tk.extra.get("span_crossings", []):
        where = "inside a Non-Grant polygon" if ar == "G" else "outside the Non-Grant polygons"
        add(Issue("INFO", "Cable", "CABLE_SPAN_CROSSES_BOUNDARY", net or "", f"{seg}: a {L:,} ft span runs {other:,} ft {where} "
                  f"but feeds a {'Grant' if ar == 'G' else 'Non-Grant'} ped - booked {'Grant' if ar == 'G' else 'Non-Grant'} "
                  "(each span follows the ped it feeds)", "Cable Grant/Non-Grant split",
                  "None if the route is right; otherwise check the Non-Grant polygon or the cable route"))

    # ---------------------------------------------------------------- closure capacity (FOSC 450 ordering guide)
    for net, _area, L, splices, name in tk.extra.get("enclosures", []):
        cap, per = TRAY_CAPACITY.get(L), TRAYS_PER_CLOSURE.get(L)
        if cap and per and splices and -(-splices // cap) > per:
            p = cls_pos.get(name.upper())
            add(Issue("WARN", "Design", "CLOSURE_OVER_CAPACITY", net, f"{name}: {splices} fusion splices need {-(-splices // cap)} trays; "
                      f"the FOSC 450 ordering guide (2004 edition) gives {per} trays ({per * cap} splices) for a 450{L} with its basket",
                      f"FOSC 450{L}, trays", "Verify the closure configuration: two closures, or a basket that leaves more tray positions",
                      p[0] if p else None, p[1] if p else None))

    # ---------------------------------------------------------------- ped size vs cable (design rule from NMK + DMI)
    m5 = set(conv["blocks"]["ped_max5"]["names"])
    in_closure = {r.name.upper() for r in reports if enclosure_letter(r.enclosure)}
    for ped, nm, role, fib in ped_cable_roles(d, conv, tk, in_closure):
        ok, n = in_scope(ped.pt)
        if not ok:
            continue
        if ped.name in m5 and fib > LARGE_CABLE:
            add(Issue("WARN", "Design", "MAX5_ON_LARGE_CABLE", n, f"MAX5 ped at {nm} ({role}) on a {fib}F cable",
                      "MAX10 / MAX5 ped counts", "Confirm the ped size: in the approved designs every ped splice on a cable above 48F "
                      "is in a MAX10 (or a FOSC closure)", ped.pt[0], ped.pt[1]))
        elif ped.name not in m5 and fib and fib <= LARGE_CABLE and role in ("pass", "end"):
            add(Issue("INFO", "Design", "MAX10_SMALL_CABLE", n, f"MAX10 ped at {nm} ({role}) on a {fib}F cable",
                      "MAX10 / MAX5 ped counts", "A MAX5 is normally used here - confirm the larger ped is intended", ped.pt[0], ped.pt[1]))

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
        # unknown enclosure types are reported by the engine check 'enclosure type unknown'
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
