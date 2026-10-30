"""Engineering quantity takeoff from the drawing + address lists + splice reports.

Every quantity is stored per (network, area) column together with the method
used and the CAD handles / names it was derived from, so each BOM number can
be traced back to the drawing.
"""
from __future__ import annotations

import heapq
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field

from ..extract.model import Drawing, Insert, Point
from ..inputs.address_list import AddressList
from ..inputs.splice_reports import SpliceReport, network_from_splice_name
from .geometry import dist, length_inside, polyline_length
from .network import AREAS, GRANT, NONGRANT, Classifier

FT_RE = re.compile(r"-?\d+(?:\.\d+)?")


def num(text: str) -> float | None:
    m = FT_RE.search(text.replace(",", "")) if text else None
    return float(m.group()) if m else None


@dataclass
class Qty:
    key: str
    network: str
    area: str
    value: float
    unit: str
    method: str
    evidence: list[str] = field(default_factory=list)


@dataclass
class Check:
    name: str
    status: str  # PASS | FAIL | WARN | INFO
    detail: str


@dataclass
class CableSegment:
    handle: str
    name: str
    a: str
    b: str
    fibers: int
    placement: str  # UG | AR
    route_ft: float
    slack_ft: float
    total_ft: float
    network: str | None
    ng_fraction: float | None = None
    path_ft: float | None = None
    split_method: str = ""
    path: list = field(default_factory=list)
    spans: list = field(default_factory=list)  # (length_ft, area)


class Takeoff:
    def __init__(self, networks: list[str]):
        self.networks = networks
        self.q: dict[tuple[str, str, str], Qty] = {}
        self.checks: list[Check] = []
        self.cables: list[CableSegment] = []
        self.unassigned: list[str] = []

    @property
    def columns(self) -> list[tuple[str, str]]:
        return [(n, a) for n in self.networks for a in AREAS]

    def add(self, key, net, area, value, unit, method, evidence=None):
        k = (key, net, area)
        if k in self.q:
            self.q[k].value += value
            self.q[k].evidence += list(evidence or [])
        else:
            self.q[k] = Qty(key, net, area, value, unit, method, list(evidence or []))

    def ensure(self, key, unit, method):
        """Register a key for every column (explicit computed zero when nothing was found)."""
        for n, a in self.columns:
            if (key, n, a) not in self.q:
                self.q[(key, n, a)] = Qty(key, n, a, 0, unit, method, [])

    def get(self, key, net, area, default=None):
        q = self.q.get((key, net, area))
        return q.value if q else default

    def total(self, key, net=None):
        return sum(q.value for (k, n, _a), q in self.q.items() if k == key and (net is None or n == net))

    def column(self, net, area) -> dict[str, float]:
        return {k: q.value for (k, n, a), q in self.q.items() if n == net and a == area}

    def check(self, name, ok, detail, warn=False):
        self.checks.append(Check(name, "PASS" if ok else ("WARN" if warn else "FAIL"), detail))


# ----------------------------------------------------------------- helpers
def _blocks(d: Drawing, conv: dict, key: str) -> list[Insert]:
    names = set(conv["blocks"][key]["names"])
    return [i for i in d.inserts if i.name in names]


def _locate(cls: Classifier, ins: Insert, tk: Takeoff) -> tuple[str | None, str]:
    net = cls.network_of(ins.pt, f"{ins.name}:{ins.handle}")
    if net is None:
        tk.unassigned.append(f"{ins.name} {ins.handle} at ({ins.pt[0]:.0f},{ins.pt[1]:.0f}) on {ins.layer}")
    return net, cls.area_of(ins.pt)


def count_blocks(d, conv, cls, tk, key, qkey=None, unit="EA"):
    qkey = qkey or key
    names = conv["blocks"][key]["names"]
    tk.ensure(qkey, unit, f"count of block {names}")
    for ins in _blocks(d, conv, key):
        net, area = _locate(cls, ins, tk)
        if net:
            tk.add(qkey, net, area, 1, unit, f"count of block {names}", [ins.handle])


# ----------------------------------------------------------------- passings
DIRECTIONALS = {"N", "S", "E", "W", "NE", "NW", "SE", "SW", "NORTH", "SOUTH", "EAST", "WEST"}


def addr_tokens(text: str) -> tuple[str, ...]:
    """Normalized address tokens: upper case, no 'C-' commercial prefix, no directionals.
    '23955 N BEARD AVE' -> ('23955', 'BEARD', 'AVE'); 'C-9030 247TH ST E' -> ('9030', '247TH', 'ST')."""
    t = re.sub(r"\bC-", "", (text or "").upper())
    return tuple(w for w in re.split(r"[\s\.,]+", t) if w and w not in DIRECTIONALS)


class ServedIndex:
    """Served addresses of one address list; a drawing address block matches when its
    tokens are a prefix of a served address ('78TH AVE' matches '78TH AVE AVE')."""

    def __init__(self, al: AddressList):
        self.addrs = [addr_tokens(a.address) for a in al.served]

    def __contains__(self, tokens: tuple[str, ...]) -> bool:
        n = len(tokens)
        return n > 0 and any(a[:n] == tokens for a in self.addrs)


def passings(d, conv, cls, tk: Takeoff, address_lists: dict[str, AddressList]):
    """Residential / commercial / MDU passings per network and area.

    network total    = served addresses in the address list (authoritative); the
                       drawing house-count blocks (HC + CC + MDUC) are the cross-check
    MDU units        = FMMULTIADD RESIDENTIAL_COUNT + COMMERCIAL_COUNT
    commercial       = CC (+ unused MDUC) minus MDU units carried by CC blocks
    residential      = total - commercial - MDU
    grant residential= served FMRESADD2 blocks on the GRANTADDRESS layer
    grant com / MDU  = served address blocks outside the Non-Grant polygons
    non-grant        = total - grant (per category)
    """
    sums = defaultdict(float)
    ev = defaultdict(list)
    for key, tag in (("house_count", "HC"), ("com_count", "CC"), ("mdu_count", "MDUC")):
        for ins in _blocks(d, conv, key):
            # strict: passings outside every boundary are not served by any network
            net = cls.network_of(ins.pt, f"{ins.name}:{ins.handle}", strict=True)
            v = num(ins.attr(tag)) or 0
            if net is None:
                if v:
                    tk.unassigned.append(f"{ins.name} {ins.handle} {tag}={v:g} outside all networks")
                continue
            sums[(net, tag)] += v
            ev[(net, tag)].append(ins.handle)
    served = {n: ServedIndex(address_lists[n]) for n in tk.networks if n in address_lists}

    def is_served(net, number, street, what):
        idx = served.get(net)
        if idx is None:
            return True  # no address list: cannot filter
        if addr_tokens(f"{number} {street}") in idx:
            return True
        tk.check("address block not in address list", False, f"{net} {what} '{number} {street}' not served - excluded from grant count", warn=True)
        return False

    mdu = defaultdict(list)  # net -> [(res, com, area, handle)]
    for ins in _blocks(d, conv, "mdu_address"):
        net, area = cls.network_of(ins.pt, ins.handle, strict=True), cls.area_of(ins.pt)
        if net:
            mdu[net].append((num(ins.attr("RESIDENTIAL_COUNT")) or 0, num(ins.attr("COMMERCIAL_COUNT")) or 0, area, ins.handle))
    res_grant = defaultdict(list)
    for ins in _blocks(d, conv, "res_address"):
        if ins.layer == conv["grant_address_layer"]:
            net = cls.network_of(ins.pt, f"{ins.name}:{ins.handle}", strict=True)
            if net and is_served(net, ins.attr("STREET_NUMBER"), ins.attr("STREET_NAME"), "grant address"):
                res_grant[net].append(ins.handle)
    com_grant = defaultdict(list)
    for ins in _blocks(d, conv, "com_address"):
        net, area = cls.network_of(ins.pt, ins.handle, strict=True), cls.area_of(ins.pt)
        if net and area == GRANT and is_served(net, ins.attr("BUILDING_ADDRESS"), ins.attr("BUILDING_NAME"), "grant commercial address"):
            com_grant[net].append(ins.handle)

    for key in ("pass_res", "pass_com", "pass_mdu"):
        tk.ensure(key, "EA", "")
    for net in tk.networks:
        hc, cc, mduc = sums[(net, "HC")], sums[(net, "CC")], sums[(net, "MDUC")]
        pool = mduc
        com_in_cc = 0.0
        mdu_total = mdu_grant = 0.0
        for r, c, area, _h in mdu[net]:
            units = r + c
            mdu_total += units
            if area == GRANT:
                mdu_grant += units
            take = min(pool, units)
            pool -= take
            rest = units - take
            # remaining units are carried by HC (residential) or CC (commercial) blocks
            com_in_cc += rest - min(rest, r)
        com_total = cc + pool - com_in_cc  # unused MDUC units are not MDU -> commercial
        dwg_total = hc + cc + mduc
        al = address_lists.get(net)
        if al:
            total = al.passings
            ok = abs(dwg_total - total) < 0.5
            tk.check(f"passings vs address list {net}", ok,
                     f"DWG count blocks {dwg_total:g} vs address list served {total}"
                     + ("" if ok else " - address list used as the network total (residential adjusted)"), warn=not ok)
        else:
            total = dwg_total
            tk.check(f"passings vs address list {net}", False, "no address list supplied - drawing count blocks used", warn=True)
        res_total = total - com_total - mdu_total
        rg = len(res_grant[net])
        cg = len(com_grant[net])
        m = "address list total; HC/CC/MDUC count blocks; grant via served GRANTADDRESS blocks / outside Non-Grant polygons"
        tk.q[("pass_res", net, GRANT)] = Qty("pass_res", net, GRANT, rg, "EA", m, res_grant[net])
        tk.q[("pass_res", net, NONGRANT)] = Qty("pass_res", net, NONGRANT, res_total - rg, "EA", m, ev[(net, "HC")])
        tk.q[("pass_com", net, GRANT)] = Qty("pass_com", net, GRANT, cg, "EA", m, com_grant[net])
        tk.q[("pass_com", net, NONGRANT)] = Qty("pass_com", net, NONGRANT, com_total - cg, "EA", m, ev[(net, "CC")])
        tk.q[("pass_mdu", net, GRANT)] = Qty("pass_mdu", net, GRANT, mdu_grant, "EA", m, [h for *_x, a, h in mdu[net] if a == GRANT])
        tk.q[("pass_mdu", net, NONGRANT)] = Qty("pass_mdu", net, NONGRANT, mdu_total - mdu_grant, "EA", m, [h for *_x, a, h in mdu[net] if a != GRANT])
        for a in AREAS:
            tk.q[("passings", net, a)] = Qty(
                "passings", net, a,
                sum(tk.get(k, net, a, 0) for k in ("pass_res", "pass_com", "pass_mdu")), "EA", "res + com + MDU", []
            )
            if tk.get("pass_res", net, a) < 0 or tk.get("pass_com", net, a) < 0:
                tk.check(f"passings sign {net} {a}", False, "negative passings - grant blocks exceed served totals")
        tk.add("mdu_buildings", net, GRANT, sum(1 for *_x, a, _h in mdu[net] if a == GRANT), "EA", "FMMULTIADD blocks")
        tk.add("mdu_buildings", net, NONGRANT, sum(1 for *_x, a, _h in mdu[net] if a != GRANT), "EA", "FMMULTIADD blocks")


# ----------------------------------------------------------------- route footage
def route_footage(d, conv, cls, tk: Takeoff):
    names = set(conv["blocks"]["route_footage"]["names"])
    groups = {"route_ug_ft": conv["route_layers"]["ug_trench"], "route_aerial_ft": conv["route_layers"]["aerial_strand"],
              "route_ugdrop_ft": conv["route_layers"]["ug_drop"]}
    for key, layers in groups.items():
        tk.ensure(key, "FT", f"sum of {sorted(names)} FTG labels on {layers}")
        for ins in d.inserts:
            if ins.name in names and ins.layer in layers:
                v = num(ins.attr("FTG"))
                if v is None:
                    tk.check("route label value", False, f"{ins.handle} on {ins.layer} has no numeric FTG", warn=True)
                    continue
                net, area = _locate(cls, ins, tk)
                if net:
                    tk.add(key, net, area, v, "FT", f"sum of FTG labels on {layers}", [ins.handle])
    for n, a in tk.columns:
        tk.q[("route_miles", n, a)] = Qty(
            "route_miles", n, a, round((tk.get("route_ug_ft", n, a, 0) + tk.get("route_aerial_ft", n, a, 0)) / 5280.0, 4),
            "MI", "(UG trench + aerial strand footage labels) / 5280", []
        )


# ----------------------------------------------------------------- cables
SEG_RE = re.compile(r"^(.+?)\s+TO\s+(.+?)\s+FC(\d+)\s*$", re.I)
STANDARD_COUNTS = (24, 48, 72, 96, 120, 144, 168, 216, 288)


class CableGraph:
    """Vertex graph of the fiber cable polylines (UG + aerial), for routing a
    labelled cable segment between its two end points."""

    def __init__(self, polylines, snap=0.05):
        self.snap = snap
        self.nodes: dict[tuple[int, int], Point] = {}
        self.adj: dict[tuple[int, int], list[tuple[tuple[int, int], float]]] = defaultdict(list)
        for pl in polylines:
            pts = pl.points
            for i in range(len(pts) - 1):
                a, b = self._key(pts[i]), self._key(pts[i + 1])
                if a == b:
                    continue
                w = dist(pts[i], pts[i + 1])
                self.adj[a].append((b, w))
                self.adj[b].append((a, w))
        self._grid = defaultdict(list)
        for k, p in self.nodes.items():
            self._grid[(int(p[0] // 200), int(p[1] // 200))].append(k)

    def _key(self, p):
        k = (round(p[0] / self.snap), round(p[1] / self.snap))
        self.nodes.setdefault(k, p)
        return k

    def nearest(self, p, max_d=60.0):
        gx, gy = int(p[0] // 200), int(p[1] // 200)
        best, bd = None, max_d
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for k in self._grid.get((gx + dx, gy + dy), []):
                    dd = dist(p, self.nodes[k])
                    if dd < bd:
                        best, bd = k, dd
        return best, bd

    def path(self, a, b):
        dist_ = {a: 0.0}
        prev = {}
        pq = [(0.0, a)]
        while pq:
            d0, u = heapq.heappop(pq)
            if u == b:
                break
            if d0 > dist_.get(u, math.inf):
                continue
            for v, w in self.adj[u]:
                nd = d0 + w
                if nd < dist_.get(v, math.inf):
                    dist_[v] = nd
                    prev[v] = u
                    heapq.heappush(pq, (nd, v))
        if b not in dist_:
            return None
        out = [b]
        while out[-1] != a:
            out.append(prev[out[-1]])
        return [self.nodes[k] for k in reversed(out)]


def _endpoint_positions(d, conv, cls, reports=None) -> dict[str, Point]:
    pos: dict[str, Point] = {}
    for ins in _blocks(d, conv, "splice_point"):
        name = ins.attr("NAME").upper()
        if name:
            pos.setdefault(name, ins.pt)
    for ins in _blocks(d, conv, "olm"):
        net = cls.network_of(ins.pt, "olm")
        if net:
            pos.setdefault(net.upper(), ins.pt)
    for ins in _blocks(d, conv, "otn"):
        nm = ins.attr("NAME").upper()
        if nm:
            pos.setdefault(nm, ins.pt)
    # splice points without a drawing symbol: use the splice-report coordinates
    for r in reports or []:
        if r.coords and r.name.upper() not in pos:
            pos[r.name.upper()] = r.coords
    return pos


def _resolve_endpoint(name: str, pos: dict[str, Point]) -> Point | None:
    n = name.strip().upper()
    if n in pos:
        return pos[n]
    # "NMK-NEW MARKET MN OTN" vs OTN block "New Market MN NMK"
    for k, p in pos.items():
        if "OTN" in n and k.split()[0:2] and all(w in n for w in k.split() if len(w) > 2 and w != "NMK"):
            return p
    return None


def _spans(path, breaks, cls, tol=3.0):
    """Split a routed path at splice / structure points; classify each span by
    the area holding the majority of its length."""
    cuts = [0]
    for i in range(1, len(path) - 1):
        p = path[i]
        for k in breaks.get((int(p[0] // 50), int(p[1] // 50)), []):
            if dist(p, k) <= tol:
                cuts.append(i)
                break
    cuts.append(len(path) - 1)
    out = []
    for i0, i1 in zip(cuts, cuts[1:]):
        piece = path[i0 : i1 + 1]
        L = polyline_length(piece)
        if L <= 0:
            continue
        inside = length_inside(piece, cls.nongrant)
        out.append((L, NONGRANT if inside > L / 2 else GRANT))
    return out


def _break_points(d, conv):
    grid = defaultdict(list)
    for key in ("splice_point", "ped_max10", "ped_max5", "vault", "ug_lbox"):
        for ins in _blocks(d, conv, key):
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    grid[(int(ins.pt[0] // 50) + dx, int(ins.pt[1] // 50) + dy)].append(ins.pt)
    return grid


def cable_footage(d, conv, cls, tk: Takeoff, net_names: list[str], reports=None, split_mode: str = "span"):
    """Cable footage per fiber count from the cable labels (fiberinfo blocks).

    TOTAL = FTG (route) + SLK (slack) is the per-segment design length (equals the
    splice-report 'Cable Design Length'). The Grant / Non-Grant split follows the
    cable route geometry: the segment is routed through the cable polylines from
    its A to its B splice and TOTAL is apportioned by the length lying inside the
    Non-Grant polygons.
    """
    labels = _blocks(d, conv, "cable_label")
    ug_layers = conv["cable_layers"]["underground"] + conv["cable_layers"]["aerial"]
    graph = CableGraph([p for p in d.polylines if p.layer in ug_layers])
    pos = _endpoint_positions(d, conv, cls, reports)
    breaks = _break_points(d, conv)
    leaders = d.leaders
    netset = {n.upper(): n for n in net_names}
    seen: dict[str, tuple] = {}
    for ins in labels:
        segname = ins.attr("SEGNUM")
        m = SEG_RE.match(segname)
        ttl = num(ins.attr("TTL"))
        total = num(ins.attr("TOTAL"))
        if not m or ttl is None or total is None:
            tk.check("cable label parse", False, f"label {ins.handle} unparseable: {ins.attribs}")
            continue
        if int(ttl) != int(m.group(3)):
            tk.check("cable label fiber count", False, f"{segname}: TTL={ttl:g} disagrees with name FC{m.group(3)}")
        if segname in seen:
            same = seen[segname] == (ttl, total)
            tk.check("duplicate cable label", False,
                     f"{segname} labelled more than once ({ins.handle}); "
                     + ("identical values - counted once" if same else f"CONFLICTING values {seen[segname]} vs {(ttl, total)} - first kept"),
                     warn=same)
            continue
        seen[segname] = (ttl, total)
        a, b = m.group(1).strip(), m.group(2).strip()
        net = None
        for end in (a, b):
            if end.upper() in netset:
                net = netset[end.upper()]
                break
            nn = network_from_splice_name(end.upper())
            if nn and nn.upper() in netset:
                net = netset[nn.upper()]
                break
        if net is None:
            net = cls.network_of(ins.pt, f"cable label {segname}")
        seg = CableSegment(ins.handle, segname, a, b, int(ttl), ins.attr("CON").upper(), num(ins.attr("FTG")) or 0,
                           num(ins.attr("SLK")) or 0, total, net)
        pa, pb = _resolve_endpoint(a, pos), _resolve_endpoint(b, pos)
        path = None
        if pa and pb:
            na, da = graph.nearest(pa)
            nb, db = graph.nearest(pb)
            if na and nb:
                path = graph.path(na, nb)
        if path and len(path) > 1:
            plen = polyline_length(path)
            seg.path_ft = plen
            seg.path = path
            seg.spans = _spans(path, breaks, cls)
            if split_mode == "span":
                ng_len = sum(L for L, ar in seg.spans if ar == NONGRANT)
                seg.split_method = "route spans (splice to splice) by majority area"
            else:
                ng_len = length_inside(path, cls.nongrant)
                seg.split_method = "route length inside Non-Grant polygons"
            seg.ng_fraction = ng_len / plen if plen else 0.0
        else:
            # fall back: classify whole segment at the point the label's leader touches the cable
            arrow = None
            best = None
            for ld in leaders:
                if ld.points:
                    dd = dist(ld.points[-1], ins.pt)
                    if best is None or dd < best:
                        best, arrow = dd, ld.points[0]
            p = arrow if (arrow and best is not None and best < 5) else ins.pt
            seg.ng_fraction = 1.0 if cls.area_of(p) == NONGRANT else 0.0
            seg.split_method = "label point (route not found)"
            tk.check("cable route", False, f"{segname}: route between {a} and {b} not found in cable polylines; whole segment classified at label", warn=True)
        tk.cables.append(seg)

    # cables present in the splice reports but carrying no DWG cable label
    # (e.g. the 100 ft OLM -> first splice FC024 tail). Real cable: include + flag.
    labelled = {c.name.upper() for c in tk.cables}
    rep_only = {}
    for r in reports or []:
        for sg in r.segments:
            if sg.placement.lower() == "pigtail" or sg.cable.upper() in labelled or sg.cable.upper() in rep_only:
                continue
            rep_only[sg.cable.upper()] = (sg, r)
    for name, (sg, r) in rep_only.items():
        mm = SEG_RE.match(sg.cable)
        a = mm.group(1) if mm else ""
        net = r.network if r.network in tk.networks else None
        pa = _resolve_endpoint(a, pos) if a else None
        area = cls.area_of(pa) if pa else GRANT
        c = CableSegment(f"report:{r.name}", sg.cable, a, mm.group(2) if mm else "", sg.fibers,
                         "AR" if sg.placement.lower().startswith("aer") else "UG", sg.design_length or 0, 0,
                         sg.design_length or 0, net, 1.0 if area == NONGRANT else 0.0, None,
                         "splice report only (no DWG cable label)")
        tk.cables.append(c)
        tk.check("cable missing DWG label", False,
                 f"{sg.cable} ({sg.fibers}F, {sg.design_length:g} ft) is in splice report {r.name} but has no DWG cable label; included from the report",
                 warn=True)
    if reports:
        rep_names = {sg.cable.upper(): sg for r in reports for sg in r.segments if sg.placement.lower() != "pigtail"}
        for c in tk.cables:
            sg = rep_names.get(c.name.upper())
            if sg and (sg.fibers != c.fibers or (sg.design_length is not None and abs(sg.design_length - c.total_ft) > 0.5)):
                tk.check("cable label vs splice report", False,
                         f"{c.name}: DWG {c.fibers}F/{c.total_ft:g} ft vs report {sg.fibers}F/{sg.design_length} ft")
    counts = sorted({c.fibers for c in tk.cables})
    if tk.cables:
        # every cable segment was enumerated, so absent fiber counts are computed zeros
        for fc in sorted(set(counts) | set(STANDARD_COUNTS)):
            tk.ensure(f"cable_{fc:03d}", "FT", "fiberinfo TOTAL")
    for fc in counts:
        if fc not in STANDARD_COUNTS:
            tk.check("cable fiber count without BOM row", False, f"FC{fc:03d} cable present but the template has no row for it")
    for c in tk.cables:
        if c.network is None:
            tk.unassigned.append(f"cable {c.name} total {c.total_ft:g} ft (no network)")
            continue
        key = f"cable_{c.fibers:03d}"
        ng = c.total_ft * c.ng_fraction
        tk.add(key, c.network, NONGRANT, ng, "FT", "fiberinfo TOTAL x Non-Grant route fraction", [c.handle])
        tk.add(key, c.network, GRANT, c.total_ft - ng, "FT", "fiberinfo TOTAL x Grant route fraction", [c.handle])
        place_key = "cable_aerial_ft" if c.placement.startswith("A") else "cable_ug_ft"
        tk.add(place_key, c.network, NONGRANT, ng, "FT", "cable footage by placement", [c.handle])
        tk.add(place_key, c.network, GRANT, c.total_ft - ng, "FT", "cable footage by placement", [c.handle])
    for (k, n, a), q in list(tk.q.items()):
        if k.startswith("cable_"):
            q.value = round(q.value)


# ----------------------------------------------------------------- splice reports
ENCL_RE = re.compile(r"FOSC\s*450\s*([A-D])", re.I)


def enclosures(d, conv, cls, tk: Takeoff, reports: list[SpliceReport]):
    pos = {}
    for ins in _blocks(d, conv, "splice_point"):
        pos.setdefault(ins.attr("NAME").upper(), ins.pt)
    for letter in "ABCD":
        tk.ensure(f"fosc450{letter.lower()}", "EA", "splice report Enclosure Type")
        tk.ensure(f"fosc450{letter.lower()}_splices", "EA", "fusion splices in enclosure (splice report)")
    names = defaultdict(list)
    for r in reports:
        names[r.name].append(r.path)
    for n, paths in names.items():
        if len(paths) > 1:
            tk.check("duplicate splice report", False, f"{n} appears in {len(paths)} files; counted once", warn=True)
    done = set()
    for r in reports:
        if r.name in done:
            continue
        done.add(r.name)
        m = ENCL_RE.search(r.enclosure or "")
        p = pos.get(r.name.upper()) or r.coords
        net = None
        if p:
            net = cls.network_of(p, f"splice {r.name}")
        if net is None and r.network in tk.networks:
            net = r.network
        area = cls.area_of(p) if p else GRANT
        if not r.enclosure:
            tk.check("splice report enclosure", False, f"{r.name}: Enclosure Type blank", warn=True)
        if m and net:
            k = f"fosc450{m.group(1).lower()}"
            tk.add(k, net, area, 1, "EA", "splice report Enclosure Type", [r.name])
            tk.add(k + "_splices", net, area, r.fusion_splices, "EA", "fusion splices in enclosure", [r.name])
        if net:
            tk.add("fusion_splices", net, area, r.fusion_splices, "EA", "fusion splices (all splice reports)", [r.name])
            for ratio, part in r.couplers:
                tk.add(f"report_splitter_1x{ratio}", net, area, 1, "EA", "splice report PLC COUPLER rows", [f"{r.name}:{part}"])


# ----------------------------------------------------------------- derived equipment
def derived(d, conv, cls, tk: Takeoff, reports, address_lists):
    poles = [i.pt for i in _blocks(d, conv, "aerial_pole")]
    tk.ensure("olm_ground", "EA", "OLM blocks not at an aerial pole")
    tk.ensure("olm_aerial", "EA", "OLM blocks within 15 ft of an aerial pole")
    for ins in _blocks(d, conv, "olm"):
        net, area = _locate(cls, ins, tk)
        if not net:
            continue
        aerial = any(dist(ins.pt, p) <= 15 for p in poles)
        tk.add("olm_aerial" if aerial else "olm_ground", net, area, 1, "EA", "OLM mounting by proximity to aerial pole", [ins.handle])
        tk.add("olm", net, area, 1, "EA", "count of OLM blocks", [ins.handle])
    tk.ensure("olm", "EA", "count of OLM blocks")
    for n in tk.networks:
        ratio, why = split_ratio(n, reports, address_lists)
        if ratio is None:
            ratio = 64
            tk.check(f"split ratio {n}", False, "no PLC COUPLER rows in splice reports or address list - assumed 1x64", warn=True)
        else:
            tk.check(f"split ratio {n}", True, f"1x{ratio} ({why})")
        tot = tk.total("passings", n)
        need = math.ceil(tot / ratio) if tot else 0
        gp = tk.get("passings", n, GRANT, 0)
        g = min(math.ceil(gp / ratio) if gp else 0, need)
        for r in (32, 64):
            tk.ensure(f"splitter_1x{r}", "EA", "")
        tk.q[(f"splitter_1x{ratio}", n, GRANT)] = Qty(f"splitter_1x{ratio}", n, GRANT, g, "EA", f"ROUNDUP(grant passings/{ratio})", [])
        tk.q[(f"splitter_1x{ratio}", n, NONGRANT)] = Qty(f"splitter_1x{ratio}", n, NONGRANT, need - g, "EA", f"ROUNDUP(network passings/{ratio}) - grant", [])
        for a in AREAS:
            p = tk.get("passings", n, a, 0)
            tk.q[("pon_ports", n, a)] = Qty("pon_ports", n, a, math.ceil(p / ratio) if p else 0, "EA", f"ROUNDUP(passings/{ratio})", [])
        sfp = tk.total("pon_ports", n)
        tk.check(f"SFP vs designed PONs {n}", sfp == need,
                 f"per-area ROUNDUP gives {sfp:g} XGS SFP+ for {need} designed PONs (reference convention rounds Grant and "
                 f"Non-Grant separately; NMK reference: 18 SFP for 15 PONs) - confirm", warn=True)
        if reports:
            rep = tk.total(f"report_splitter_1x{ratio}", n)
            tk.check(f"splitters vs splice reports {n}", rep == need, f"design rule {need} x 1x{ratio} vs splice-report PLC COUPLER rows {rep:g}")
        al = address_lists.get(n)
        if al:
            tk.check(f"splitters vs address-list PONs {n}", al.pon_count == need, f"design rule {need} vs address-list PON count {al.pon_count}")


def split_ratio(net, reports, address_lists) -> tuple[int | None, str]:
    """Splitter ratio actually designed for a network (splice reports first, then address list)."""
    from collections import Counter

    c = Counter(ratio for r in reports or [] if r.network == net for ratio, _p in r.couplers)
    if c:
        return c.most_common(1)[0][0], "splice-report PLC COUPLER rows"
    al = address_lists.get(net)
    if al and al.coupler_ratios:
        return Counter(al.coupler_ratios).most_common(1)[0][0], "address-list PLC COUPLER rows"
    return None, ""


def grounding_points(d, conv, cls, tk: Takeoff):
    tk.ensure("grounding_points", "EA", "splice points whose name ends in G")
    for ins in _blocks(d, conv, "splice_point"):
        if ins.attr("NAME").upper().endswith("G"):
            net, area = _locate(cls, ins, tk)
            if net:
                tk.add("grounding_points", net, area, 1, "EA", "splice points whose name ends in G", [ins.attr("NAME")])


def build_takeoff(d: Drawing, conv: dict, cls: Classifier, networks: list[str],
                  address_lists: dict[str, AddressList], reports: list[SpliceReport]) -> Takeoff:
    tk = Takeoff(networks)
    passings(d, conv, cls, tk, address_lists)
    for key in ("ped_max10", "ped_max5", "vault", "ug_lbox"):
        count_blocks(d, conv, cls, tk, key)
    route_footage(d, conv, cls, tk)
    cable_footage(d, conv, cls, tk, networks, reports)
    enclosures(d, conv, cls, tk, reports)
    derived(d, conv, cls, tk, reports, address_lists)
    grounding_points(d, conv, cls, tk)
    if cls.nearest_assigned:
        tk.checks.append(Check("objects outside boundaries", "WARN",
                               f"{len(cls.nearest_assigned)} objects outside every network boundary were assigned to the nearest network (<= {cls.tolerance:g} ft)"))
    if tk.unassigned:
        tk.checks.append(Check("unassigned objects", "WARN", f"{len(tk.unassigned)} objects could not be assigned to a network"))
    return tk
