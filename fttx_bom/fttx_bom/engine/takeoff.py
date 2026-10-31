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
    ng_fraction_length: float | None = None
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
        self.extra: dict = {"ratio": {}, "enclosures": [], "olms": []}  # facts the policy variants need
        self.policy_used: dict[str, str] = {}

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

    def subset(self, nets: list[str]) -> "Takeoff":
        """View of the takeoff restricted to some networks (one BOM per OLM)."""
        others = [n for n in self.networks if n not in nets]
        sub = Takeoff(list(nets))
        sub.q = {k: v for k, v in self.q.items() if k[1] in nets}
        sub.checks = [c for c in self.checks if not any(o in c.name or o in c.detail for o in others)]
        sub.cables = [c for c in self.cables if c.network in nets]
        sub.unassigned = list(self.unassigned)
        sub.extra = self.extra
        sub.policy_used = dict(self.policy_used)
        return sub

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
            seg.ng_fraction_length = length_inside(path, cls.nongrant) / plen if plen else 0.0
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
            if sg.design_length is None:
                continue  # splice-guide format carries no length: cannot add footage from it
            rep_only[sg.cable.upper()] = (sg, r)
    for name, (sg, r) in rep_only.items():
        mm = SEG_RE.match(sg.cable)
        a = mm.group(1) if mm else ""
        net = r.network if r.network in tk.networks else None
        pa = _resolve_endpoint(a, pos) if a else None
        area = cls.area_of(pa) if pa else GRANT
        c = CableSegment(handle=f"report:{r.name}", name=sg.cable, a=a, b=mm.group(2) if mm else "", fibers=sg.fibers,
                         placement="AR" if sg.placement.lower().startswith("aer") else "UG", route_ft=sg.design_length or 0,
                         slack_ft=0, total_ft=sg.design_length or 0, network=net,
                         ng_fraction=1.0 if area == NONGRANT else 0.0, ng_fraction_length=1.0 if area == NONGRANT else 0.0,
                         split_method="splice report only (no DWG cable label)")
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
TRAY_CAPACITY = {"B": 24, "D": 48}  # splices per tray: ACC-B-24 tray, FOSC-ACC-D-TRAY-48
ENCL_RE = re.compile(r"FOSC\s*450\s*([A-D])", re.I)


def enclosures(d, conv, cls, tk: Takeoff, reports: list[SpliceReport]):
    pos = {}
    for ins in _blocks(d, conv, "splice_point"):
        pos.setdefault(ins.attr("NAME").upper(), ins.pt)
    if reports:
        for L in "bd":
            tk.ensure(f"trays_450{L}", "EA", "per enclosure ROUNDUP(splices / tray capacity)")
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
            cap = TRAY_CAPACITY.get(m.group(1).upper())
            if cap:
                # SME walkthrough: trays per splice location = ROUNDUP(splices / tray capacity);
                # packages of 2 trays are pooled per column (spare tray of a package goes to another location)
                trays = math.ceil(r.fusion_splices / cap) if r.fusion_splices else 0
                tk.extra["enclosures"].append((net, area, m.group(1).upper(), r.fusion_splices, r.name))
                tk.add(f"trays_450{m.group(1).lower()}", net, area, trays, "EA",
                       f"per enclosure ROUNDUP(splices/{cap})", [f"{r.name}:{r.fusion_splices} splices -> {trays} trays"])
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
        net, _loc = _locate(cls, ins, tk)
        if not net:
            continue
        # SME: OLM equipment is always booked to Grant (1 per OLM) unless the whole OLM area is Non-Grant
        area = GRANT if tk.get("passings", net, GRANT, 0) > 0 else NONGRANT
        tk.extra["olms"].append((net, _loc, any(dist(ins.pt, p) <= 15 for p in poles), ins.handle))
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
        tk.extra["ratio"][n] = ratio
        tot = tk.total("passings", n)
        need = math.ceil(tot / ratio) if tot else 0
        designed = tk.total(f"report_splitter_1x{ratio}", n) if reports else 0
        if designed:
            if designed != need:
                tk.check(f"designed splitters {n}", False, f"splice reports show {designed:g} x 1x{ratio}; ROUNDUP(passings/{ratio}) = {need}; designed count used", warn=True)
            need = int(designed)
        gp = tk.get("passings", n, GRANT, 0)
        g = min(math.ceil(gp / ratio) if gp else 0, need)
        for r in (32, 64):
            tk.ensure(f"splitter_1x{r}", "EA", "")
        tk.q[(f"splitter_1x{ratio}", n, GRANT)] = Qty(f"splitter_1x{ratio}", n, GRANT, g, "EA", f"ROUNDUP(grant passings/{ratio})", [])
        tk.q[(f"splitter_1x{ratio}", n, NONGRANT)] = Qty(f"splitter_1x{ratio}", n, NONGRANT, need - g, "EA", f"ROUNDUP(network passings/{ratio}) - grant", [])
        for a in AREAS:
            p = tk.get("passings", n, a, 0)
            # SME: SFP = ROUNDUP(Jumper Calculator 'Splitters Required' / 2), where the calculator uses
            # ROUNDUP(passings/32) whatever splitter is actually designed
            tk.q[("pon_ports", n, a)] = Qty("pon_ports", n, a, math.ceil(math.ceil(p / 32) / 2) if p else 0, "EA",
                                            "ROUNDUP(ROUNDUP(passings/32)/2) (Jumper Calculator / 2)", [])
        tk.extra.setdefault("designed_pons", {})[n] = need
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


def tray_packages(tk: Takeoff):
    for L in "bd":
        if any(k == f"trays_450{L}" for k, _n, _a in tk.q):
            for n, a in tk.columns:
                t = tk.get(f"trays_450{L}", n, a, 0)
                tk.q[(f"tray_450{L}", n, a)] = Qty(f"tray_450{L}", n, a, math.ceil(t / 2), "PKG",
                                                   "ROUNDUP(sum of per-location trays / 2) - 2 trays per package", [])


def max10_upgrades(d, conv, cls, tk: Takeoff):
    """Upgrade kits (+4 ports) needed where a MAX ped feeds more than its 4 stock ports.
    Ports used = house count (CX1-COUNT HC within 30 ft) + commercial count (CX1-COMCNT CC within 50 ft),
    the same association the FX_DROPS routine uses."""
    hc = [(i.pt, num(i.attr("HC")) or 0) for i in _blocks(d, conv, "house_count")]
    cc = [(i.pt, num(i.attr("CC")) or 0) for i in _blocks(d, conv, "com_count")]
    tk.ensure("max10_upgrades", "EA", "MAX peds feeding > 4 passings: ROUNDUP((ports - 4) / 4) kits")
    tk.ensure("ped_ports_max", "EA", "largest number of passings fed by one MAX ped")
    for key in ("ped_max10", "ped_max5"):
        for ins in _blocks(d, conv, key):
            ports = sum(v for p, v in hc if dist(p, ins.pt) <= 30) + sum(v for p, v in cc if dist(p, ins.pt) <= 50)
            net, area = cls.network_of(ins.pt, ins.handle), cls.area_of(ins.pt)
            if not net:
                continue
            q = tk.q[("ped_ports_max", net, area)]
            q.value = max(q.value, ports)
            if ports > 4:
                tk.add("max10_upgrades", net, area, math.ceil((ports - 4) / 4), "EA",
                       "MAX peds feeding > 4 passings", [f"{ins.name}:{ins.handle}:{ports:g}"])


def drop_footage(d, conv, cls, tk: Takeoff, address_lists):
    """Drop footage from the FX_DROPS routine output: straight drop lines on RTE_SpatialNet_UGDROP from
    the feeding MAX ped to a PED 6.6 ft off the address, labelled with a CX1-FTG-N2 length (rounded).
    Network and Grant / Non-Grant follow the address the drop serves."""
    layers = conv["route_layers"]["ug_drop"]
    drops = [p for p in d.polylines if p.layer in layers and len(p.points) >= 2]
    labels = [i for i in d.inserts if i.layer in layers and i.name in conv["blocks"]["route_footage"]["names"]]
    addrs = [i for i in d.inserts if i.name in set(conv["blocks"]["res_address"]["names"] + conv["blocks"]["com_address"]["names"])]
    if not drops:
        for n in tk.networks:
            tk.check(f"drop lines {n}", False, "no drop lines on RTE_SpatialNet_UGDROP - run FX_DROPS (FXAUTO) in AutoCAD before the BOM; drop footage left blank", warn=True)
        return
    tk.ensure("drop_ft", "FT", "sum of FX_DROPS drop lengths by served address")
    tk.ensure("drop_count", "EA", "drop lines")
    grid = defaultdict(list)
    for a in addrs:
        grid[(int(a.pt[0] // 100), int(a.pt[1] // 100))].append(a)

    def near_addr(p):
        best, bd = None, 1e9
        gx, gy = int(p[0] // 100), int(p[1] // 100)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for a in grid.get((gx + dx, gy + dy), []):
                    dd = dist(p, a.pt)
                    if dd < bd:
                        best, bd = a, dd
        return best, bd

    lab_grid = defaultdict(list)
    for lb in labels:
        lab_grid[(int(lb.pt[0] // 50), int(lb.pt[1] // 50))].append(lb)
    for pl in drops:
        geo = polyline_length(pl.points)
        (a0, d0), (a1, d1) = near_addr(pl.points[0]), near_addr(pl.points[-1])
        addr, dd = (a0, d0) if d0 <= d1 else (a1, d1)
        if addr is None or dd > 25:
            tk.check("drop without address", False, f"drop {pl.handle} ({geo:.0f} ft) ends > 25 ft from any address block", warn=True)
            continue
        # prefer the drawn length label (what the designer sees) when it sits on this drop
        mid = pl.points[len(pl.points) // 2] if len(pl.points) > 2 else ((pl.points[0][0] + pl.points[-1][0]) / 2, (pl.points[0][1] + pl.points[-1][1]) / 2)
        L = round(geo)
        for lb in lab_grid.get((int(mid[0] // 50), int(mid[1] // 50)), []):
            v = num(lb.attr("FTG"))
            if v is not None and dist(lb.pt, mid) < 15 and abs(v - geo) <= 1.5:
                L = v
                break
        net = cls.network_of(addr.pt, f"drop:{pl.handle}", strict=True) or cls.network_of(addr.pt, f"drop:{pl.handle}")
        if not net:
            continue
        if addr.name in conv["blocks"]["res_address"]["names"]:
            area = GRANT if addr.layer == conv["grant_address_layer"] else NONGRANT
        else:
            area = cls.area_of(addr.pt)
        tk.add("drop_ft", net, area, L, "FT", "FX_DROPS drop length, area of the served address", [pl.handle])
        tk.add("drop_count", net, area, 1, "EA", "drop lines", [pl.handle])
    for n in tk.networks:
        cnt = tk.total("drop_count", n)
        mdu = tk.total("pass_mdu", n)
        need = tk.total("passings", n) - mdu
        tk.check(f"drops vs passings {n}", cnt == need,
                 f"{cnt:g} drop lines vs {need:g} non-MDU passings (FX_DROPS skips MDU addresses)" + ("" if cnt == need else " - run FXMISSING"),
                 warn=cnt != need)
        if cnt == 0:
            continue  # no drops drawn for this network: leave the BOM row "not computed", never 0
        # reference convention: BOM row carries the Non-Grant drop footage only ("total - grant")
        tk.q[("drop_ft_bom", n, GRANT)] = Qty("drop_ft_bom", n, GRANT, 0, "FT", "reference convention: grant drops not ordered on this BOM", [])
        tk.q[("drop_ft_bom", n, NONGRANT)] = Qty("drop_ft_bom", n, NONGRANT, tk.get("drop_ft", n, NONGRANT, 0), "FT",
                                                 "Non-Grant drop footage (reference: total - grant)", [])


def grounding_points(d, conv, cls, tk: Takeoff):
    tk.ensure("grounding_points", "EA", "splice points whose name ends in G")
    for ins in _blocks(d, conv, "splice_point"):
        if ins.attr("NAME").upper().endswith("G"):
            net, area = _locate(cls, ins, tk)
            if net:
                tk.add("grounding_points", net, area, 1, "EA", "splice points whose name ends in G", [ins.attr("NAME")])


def build_takeoff(d: Drawing, conv: dict, cls: Classifier, networks: list[str],
                  address_lists: dict[str, AddressList], reports: list[SpliceReport],
                  policies: dict[str, str] | None = None) -> Takeoff:
    tk = Takeoff(networks)
    passings(d, conv, cls, tk, address_lists)
    for key in ("ped_max10", "ped_max5", "vault", "ug_lbox"):
        count_blocks(d, conv, cls, tk, key)
    route_footage(d, conv, cls, tk)
    cable_footage(d, conv, cls, tk, networks, reports)
    enclosures(d, conv, cls, tk, reports)
    derived(d, conv, cls, tk, reports, address_lists)
    tray_packages(tk)
    max10_upgrades(d, conv, cls, tk)
    drop_footage(d, conv, cls, tk, address_lists)
    grounding_points(d, conv, cls, tk)
    from . import policies as pol

    pol.compute_variants(tk)
    pol.apply(tk, pol.load_selection() if policies is None else policies)
    for n in networks:
        sfp, need = tk.total("pon_ports", n), tk.extra.get("designed_pons", {}).get(n)
        if need is not None:
            tk.check(f"SFP vs designed PONs {n}", sfp == need,
                     f"policy sfp={tk.policy_used['sfp']} gives {sfp:g} XGS SFP+ for {need} designed PONs"
                     + ("" if sfp == need else " (per-column rounding) - see Policies sheet"), warn=True)
    if cls.nearest_assigned:
        tk.checks.append(Check("objects outside boundaries", "WARN",
                               f"{len(cls.nearest_assigned)} objects outside every network boundary were assigned via the transport corridor "
                               f"or to the nearest network within {cls.tolerance:g} ft (listed in 'Network Assignment')"))
    if tk.unassigned:
        tk.checks.append(Check("unassigned objects", "WARN", f"{len(tk.unassigned)} objects could not be assigned to a network"))
    return tk
