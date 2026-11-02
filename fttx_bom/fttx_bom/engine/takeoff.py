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

from ..extract.model import Drawing, Insert, Point, Polyline
from ..inputs.address_list import AddressList
from ..inputs.splice_reports import SpliceReport, network_from_splice_name
from .geometry import dist, length_inside, point_polyline_distance, point_segment_distance, polyline_length
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
    ng_fraction_majority: float | None = None
    # route not traced: areas of the label point and of each end found in the drawing. When they all agree
    # the Grant / Non-Grant split does not depend on the route.
    fallback_areas: tuple = ()

    @property
    def split_uncertain(self) -> bool:
        if not ("label point" in self.split_method or "report only" in self.split_method):
            return False
        return len(self.fallback_areas) < 3 or len(set(self.fallback_areas)) > 1


class Takeoff:
    def __init__(self, networks: list[str]):
        self.networks = networks
        self.q: dict[tuple[str, str, str], Qty] = {}
        self.checks: list[Check] = []
        self.cables: list[CableSegment] = []
        self.unassigned: list[str] = []
        self.foreign_cables: list[tuple[str, str, str, str]] = []  # (A, B, network, name) of other networks in the drawing
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
        sub.foreign_cables = list(self.foreign_cables)
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
    if net is None and not cls.foreign_of(ins.pt):
        tk.unassigned.append(f"{ins.name} {ins.handle} at ({ins.pt[0]:.0f},{ins.pt[1]:.0f}) on {ins.layer}")
    return net, cls.area_of(ins.pt)


def nongrant_depth(cls: Classifier, p: Point) -> float | None:
    """Distance from p to the edge of the Non-Grant polygon containing it, None when p is in Grant."""
    inside = [r for r in cls.nongrant if r.contains(p)]
    if not inside:
        return None if cls.area_of(p) == GRANT else float("inf")
    return min(point_polyline_distance(p, r.poly, True) for r in inside)


def structure_area(cls: Classifier, p: Point, tol: float = 5.0) -> str:
    """Design standard: a structure (ped, vault, closure) on the Non-Grant boundary, i.e. less than `tol` ft
    inside the Non-Grant edge, counts as Grant."""
    depth = nongrant_depth(cls, p)
    return GRANT if depth is None or depth < tol else NONGRANT


class StructureAreas:
    """Area of the structure at a point: the nearest ped / vault / L-box within `radius` (a splice symbol or
    cable vertex sits beside its ped), by the boundary rule; else the point itself by the same rule."""

    def __init__(self, d, conv, cls: Classifier, radius: float = 15.0):
        self.cls, self.radius = cls, radius
        self.tol = conv.get("boundary_structure_tolerance_ft", 5.0)
        self.grid: dict = defaultdict(list)
        for key in ("ped_max10", "ped_max5", "vault", "ug_lbox"):
            for ins in _blocks(d, conv, key):
                self.grid[(int(ins.pt[0] // 50), int(ins.pt[1] // 50))].append(ins.pt)

    def area(self, p: Point) -> str:
        gx, gy = int(p[0] // 50), int(p[1] // 50)
        near = min((q for dx in (-1, 0, 1) for dy in (-1, 0, 1) for q in self.grid.get((gx + dx, gy + dy), [])),
                   key=lambda q: dist(p, q), default=None)
        at = near if near is not None and dist(p, near) <= self.radius else p
        return structure_area(self.cls, at, self.tol)


def resolve_report_networks(d, conv, cls: Classifier, tk: "Takeoff", reports) -> None:
    """Set each splice report's network: the splice-name pattern when it names a network in the
    drawing, else the splice point's drawing location (symbol, then report coordinates), else the
    folder name; a single-network job without other networks owns every report."""
    known = set(tk.networks) | set(cls.foreign)
    pos = {}
    for ins in _blocks(d, conv, "splice_point"):
        pos.setdefault(ins.attr("NAME").upper(), ins.pt)
    for r in reports or []:
        by_name = network_from_splice_name(r.name.upper())
        if by_name in known:
            r.network = by_name
            continue
        p = pos.get(r.name.upper()) or r.coords
        net = cls.resolve(p)[0] if p else None
        if net is None and r.network not in known and len(tk.networks) == 1 and not cls.foreign:
            net = tk.networks[0]
        if net and net != r.network:
            tk.check("splice report network", True, f"{r.name}: network {net} from its drawing location (name/folder gave '{r.network}')")
            r.network = net
        elif net is None and r.network not in known:
            tk.check("splice report network", False, f"{r.name}: network not found (name/folder '{r.network}', no drawing location)", warn=True)


class SegIndex:
    """Grid index of polyline segments for 'distance to the nearest line' queries."""

    def __init__(self, polylines, cell: float = 100.0):
        self.cell = cell
        self.g = defaultdict(list)
        for pl in polylines:
            for a, b in zip(pl.points, pl.points[1:]):
                for gx in range(int(min(a[0], b[0]) // cell), int(max(a[0], b[0]) // cell) + 1):
                    for gy in range(int(min(a[1], b[1]) // cell), int(max(a[1], b[1]) // cell) + 1):
                        self.g[(gx, gy)].append((a, b))

    def nearest(self, p, radius: float) -> float | None:
        """Distance to the nearest indexed line within `radius`, else None."""
        k = int(radius // self.cell) + 1
        gx, gy = int(p[0] // self.cell), int(p[1] // self.cell)
        best = None
        for dx in range(-k, k + 1):
            for dy in range(-k, k + 1):
                for a, b in self.g.get((gx + dx, gy + dy), ()):
                    dd = point_segment_distance(p, a, b)
                    if dd <= radius and (best is None or dd < best):
                        best = dd
        return best


def fiber_cables(d, conv, which=("underground", "aerial")) -> list:
    layers = [lay for w in which for lay in conv["cable_layers"][w]]
    return [p for p in d.polylines if p.layer in layers and len(p.points) >= 2]


def rf_support_test(d, conv):
    """Callable(point) -> reason or None: a support structure (vault, L-box) that serves the RF (coax)
    plant, not the fiber. RF plant is not part of the FTTH BOM. A structure is RF when an RF
    device (amplifier, tap, splitter, terminator, end-of-line) is within rf_support_radius_ft and no
    fiber splice point is within rf_support_splice_ft. RF power supplies are not used as evidence:
    the coax-powered OLM sits beside one in the fiber hub vault."""
    layers = set(conv.get("rf_device_layers", []))
    names = set(conv.get("rf_device_blocks", []))
    devs = [i for i in d.inserts if i.layer in layers or i.name in names]
    if not devs:
        return lambda p: None
    splices = [i.pt for i in _blocks(d, conv, "splice_point")]
    r_dev, r_spl = conv.get("rf_support_radius_ft", 50.0), conv.get("rf_support_splice_ft", 100.0)

    def test(p):
        near = min(((dist(p, i.pt), i.name) for i in devs), default=(1e18, ""))
        if near[0] <= r_dev and not any(dist(p, q) <= r_spl for q in splices):
            return f"RF device {near[1]} {near[0]:.0f} ft away, no fiber splice within {r_spl:g} ft"
        return None

    return test


# ----------------------------------------------------------------- design scope
def design_scope(d, conv, tk: Takeoff) -> dict:
    """Which objects belong to networks this design does not own.

    A drawing can also carry an existing HFC (coax) plant and fiber networks designed by others.
    This design is built with MAX5/MAX10 pedestals and bulkheads. Fiber of another network is
    recognised by its terminals (MST-type blocks, `foreign_fiber_blocks`): a splice point housed
    at such a terminal belongs to that network, and so does every cable that ends there or at an
    HFC node (CX1_NODE tag)."""
    terminals = [i for i in d.inserts if i.name in set(conv.get("foreign_fiber_blocks", []))]
    peds = [i.pt for k in ("ped_max10", "ped_max5") for i in _blocks(d, conv, k)]
    r = conv.get("foreign_terminal_ft", 35.0)
    foreign = {}
    if terminals:
        for ins in _blocks(d, conv, "splice_point"):
            nm = (ins.attr("NAME") or "").strip().upper()
            dt, blk = min(((dist(ins.pt, t.pt), t.name) for t in terminals), key=lambda x: x[0])
            dp = min((dist(ins.pt, q) for q in peds), default=1e18)
            if nm and dt <= r and dt < dp:
                foreign[nm] = f"housed at {blk} {dt:.0f} ft away (terminal of another fiber network)"
    nodes = set()
    for ins in d.inserts:
        if ins.name in set(conv.get("hfc_node_blocks", [])):
            tag = (ins.attr("AMPTAG") or ins.attr("NAME") or "").strip().upper()
            if tag:
                nodes.add(re.sub(r"-0+$", "", tag))
    scope = {"foreign_splices": foreign, "hfc_nodes": nodes, "excluded": []}
    tk.extra["scope"] = scope
    return scope


def _foreign_end(a: str, b: str, scope: dict) -> str | None:
    for end in (a.upper(), b.upper()):
        if end in scope["foreign_splices"]:
            return f"{end} {scope['foreign_splices'][end]}"
        if end in scope["hfc_nodes"]:
            return f"{end} is an HFC node"
    return None


def exclude(tk: Takeoff, category: str, what: str, qty: str, reason: str, pt=None) -> None:
    """Record an object that is in the drawing but not part of this design's BOM."""
    tk.extra.setdefault("scope", {"foreign_splices": {}, "hfc_nodes": set(), "excluded": []})["excluded"].append(
        (category, what, qty, reason, pt))


def count_blocks(d, conv, cls, tk, key, qkey=None, unit="EA"):
    qkey = qkey or key
    names = conv["blocks"][key]["names"]
    found = _blocks(d, conv, key)
    if not found and d.block_census and not any(n in d.block_census for n in names):
        # the block is not even defined in this drawing: a renamed symbol, not a computed zero
        tk.check(f"block not defined {qkey}", False, f"no {names} block definition in the drawing - "
                 f"{qkey} not counted (left blank); add the drawing's block name to config/conventions.json")
        return
    tk.ensure(qkey, unit, f"count of block {names}")
    if key in conv.get("rf_support_keys", []):
        is_rf = rf_support_test(d, conv)
        ours, others = tk.extra.get("our_paths"), tk.extra.get("foreign_paths")
        fs = tk.extra.get("scope", {}).get("foreign_splices", {})
        our_splices = [i.pt for i in _blocks(d, conv, "splice_point") if (i.attr("NAME") or "").strip().upper() not in fs]
        kept = []
        for ins in found:
            why = is_rf(ins.pt)
            if why:
                tk.extra.setdefault("rf_structures", []).append((qkey, ins.handle, ins.pt, why))
                tk.check(f"RF support structure {qkey}", False, f"{ins.name} {ins.handle}: {why} - RF plant, not counted", warn=True)
                continue
            if others is not None and ours is not None:
                d_o, d_f = ours.nearest(ins.pt, 100.0), others.nearest(ins.pt, 100.0)
                on_ours = (d_o is not None and d_o <= 40.0) or any(dist(ins.pt, q) <= 50.0 for q in our_splices)
                if not on_ours and d_f is not None and (d_o is None or d_f < d_o):
                    exclude(tk, "Other fiber network", f"{ins.name} {ins.handle}", "1", f"on another network's fiber route ({d_f:.0f} ft)", ins.pt)
                    continue
                if not on_ours and d_o is None:
                    exclude(tk, "Existing / other plant", f"{ins.name} {ins.handle}", "1",
                            "not on a fiber route of this design (existing or other plant)", ins.pt)
                    continue
            kept.append(ins)
        found = kept
    tol = conv.get("boundary_structure_tolerance_ft", 5.0)
    for ins in found:
        net, area = _locate(cls, ins, tk)
        if net and area == NONGRANT and tol > 0 and structure_area(cls, ins.pt, tol) == GRANT:
            # a structure on the Non-Grant boundary counts as Grant (design standard)
            area = GRANT
            tk.check(f"structure on Non-Grant boundary {qkey}", True, f"{ins.name} {ins.handle} is "
                     f"{nongrant_depth(cls, ins.pt):.1f} ft inside a Non-Grant edge - counted Grant (on the boundary)")
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
    non-grant res/com= served address blocks inside the Non-Grant boundaries (one per address)
    grant            = total - non-grant (design standard: "everything inside the Non-Grant boundary is
                       Non-Grant, Grant = total - Non-Grant")
    MDU              = units of the FMMULTIADD blocks by location
    The GRANTADDRESS layer is a cross-check (deep check ADDRESS_LAYER_VS_BOUNDARY); conventions
    `passings_area_rule: "grant_layer"` counts grant residential by that layer instead.
    """
    rule = conv.get("passings_area_rule", "boundary")
    tk.extra["passings_rule"] = rule
    sums = defaultdict(float)
    ev = defaultdict(list)
    # count blocks of other plant (HFC taps / pedestals, other networks' terminals) are not this design's
    # passings: a count block belongs to the nearest housing within count_block_assoc_ft
    other = [i.pt for i in d.inserts if i.name in set(conv.get("foreign_fiber_blocks", []) + conv.get("hfc_ped_blocks", []))
             or i.layer in set(conv.get("rf_tap_layers", []))]
    peds = [i.pt for k in ("ped_max10", "ped_max5") for i in _blocks(d, conv, k)]
    assoc = conv.get("count_block_assoc_ft", 60.0)
    for key, tag in (("house_count", "HC"), ("com_count", "CC"), ("mdu_count", "MDUC")):
        for ins in _blocks(d, conv, key):
            # strict: passings outside every boundary are not served by any network
            net = cls.network_of(ins.pt, f"{ins.name}:{ins.handle}", strict=True)
            v = num(ins.attr(tag)) or 0
            if other and net is not None:
                d_o = min((dist(ins.pt, q) for q in other), default=1e18)
                d_p = min((dist(ins.pt, q) for q in peds), default=1e18)
                # an HFC aerial tap hangs on a pole: count blocks around it are HFC passings
                if (d_o <= assoc or (d_o <= 2.5 * assoc and d_p > assoc)) and d_o < d_p:
                    if v:
                        exclude(tk, "Existing / other plant", f"{ins.name} {ins.handle}", f"{tag} {v:g}",
                                f"count block of another network's terminal or HFC plant ({d_o:.0f} ft)", ins.pt)
                    continue
            if net is None:
                if v and not cls.foreign_of(ins.pt, strict=True):
                    tk.unassigned.append(f"{ins.name} {ins.handle} {tag}={v:g} outside all networks")
                continue
            sums[(net, tag)] += v
            ev[(net, tag)].append(ins.handle)
    served = {n: ServedIndex(address_lists[n]) for n in tk.networks if n in address_lists and address_lists[n].served}

    def is_served(net, number, street, what):
        idx = served.get(net)
        if idx is None:
            return True  # no address list: cannot filter
        if addr_tokens(f"{number} {street}") in idx:
            return True
        tk.check("address block not in address list", False, f"{net} {what} '{number} {street}' is not a served address of the address list - not counted", warn=True)
        return False

    def ours(net, ins) -> bool:
        """Without an address list, an address belongs to this design only when its nearest housing is one of
        this design's pedestals (the drawing may also hold HFC plant or another fiber network)."""
        if not other or (net in address_lists and address_lists[net].served):
            return True
        d_p = min((dist(ins.pt, q) for q in peds), default=1e18)
        if d_p > min((dist(ins.pt, q) for q in other), default=1e18):
            exclude(tk, "Existing / other plant", f"{ins.name} {ins.handle}", "address",
                    "nearest housing is not a pedestal of this design", ins.pt)
            return False
        return True

    mdu = defaultdict(list)  # net -> [(res, com, area, handle)]
    for ins in _blocks(d, conv, "mdu_address"):
        net, area = cls.network_of(ins.pt, ins.handle, strict=True), cls.area_of(ins.pt)
        if net and ours(net, ins):
            mdu[net].append((num(ins.attr("RESIDENTIAL_COUNT")) or 0, num(ins.attr("COMMERCIAL_COUNT")) or 0, area, ins.handle))
    def counted(kind, number, street, net, ins):
        """Served address of this design, counted once per address (duplicate blocks are drafting errors)."""
        if not ours(net, ins):
            return None
        tokens = addr_tokens(f"{number} {street}")
        idx = served.get(net)
        if idx is not None and tokens not in idx:
            skipped[(net, kind)] += 1
            return None
        return tokens

    skipped: dict = defaultdict(int)
    res_ng: dict = defaultdict(dict)  # net -> {address tokens: handle} inside the Non-Grant boundaries
    res_grant_layer: dict = defaultdict(dict)  # served blocks on the GRANTADDRESS layer (cross-check / option)
    for ins in _blocks(d, conv, "res_address"):
        net = cls.network_of(ins.pt, f"{ins.name}:{ins.handle}", strict=True)
        if not net:
            continue
        on_layer = ins.layer == conv["grant_address_layer"]
        if cls.area_of(ins.pt) != NONGRANT and not on_layer:
            continue
        # a GRANTADDRESS block that is not a served address is a design inconsistency: reported either way
        if on_layer and not is_served(net, ins.attr("STREET_NUMBER"), ins.attr("STREET_NAME"), "grant address"):
            continue
        tok = counted("res", ins.attr("STREET_NUMBER"), ins.attr("STREET_NAME"), net, ins)
        if tok is None:
            continue
        if cls.area_of(ins.pt) == NONGRANT:
            res_ng[net].setdefault(tok, ins.handle)
        if on_layer:
            res_grant_layer[net].setdefault(tok, ins.handle)
    com_ng: dict = defaultdict(dict)
    for ins in _blocks(d, conv, "com_address"):
        net = cls.network_of(ins.pt, ins.handle, strict=True)
        if not net or cls.area_of(ins.pt) != NONGRANT:
            continue
        tok = counted("com", ins.attr("BUILDING_ADDRESS"), ins.attr("BUILDING_NAME"), net, ins)
        if tok is not None:
            com_ng[net].setdefault(tok, ins.handle)
    for (net, kind), cnt in sorted(skipped.items()):
        tk.check(f"address blocks not served {net}", True, f"{cnt} {'residential' if kind == 'res' else 'commercial'} address "
                 "block(s) in the drawing are not served addresses of the address list - not counted")

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
        if al and al.served:
            total = al.passings
            ok = abs(dwg_total - total) < 0.5
            tk.check(f"passings vs address list {net}", ok,
                     f"DWG count blocks {dwg_total:g} vs address list served {total}"
                     + ("" if ok else " - address list used as the network total (residential adjusted)"), warn=not ok)
        else:
            total = dwg_total
            why = "address list has no served rows" if al else "no address list supplied"
            tk.check(f"passings vs address list {net}", False, f"{why} - drawing count blocks used", warn=True)
        res_total = total - com_total - mdu_total
        if rule == "grant_layer":
            rg = len(res_grant_layer[net])
            rn = res_total - rg
            m_res = "address list total; Grant = served FMRESADD2 blocks on the GRANTADDRESS layer, Non-Grant = total - Grant"
            ev_g, ev_n = list(res_grant_layer[net].values()), ev[(net, "HC")]
        else:
            rn = len(res_ng[net])
            rg = res_total - rn
            m_res = "address list total; Non-Grant = served address blocks inside the Non-Grant boundaries, Grant = total - Non-Grant"
            ev_g, ev_n = ev[(net, "HC")], list(res_ng[net].values())
        cn = len(com_ng[net])
        m_com = "Non-Grant = served commercial address blocks inside the Non-Grant boundaries, Grant = total - Non-Grant"
        tk.q[("pass_res", net, GRANT)] = Qty("pass_res", net, GRANT, rg, "EA", m_res, ev_g)
        tk.q[("pass_res", net, NONGRANT)] = Qty("pass_res", net, NONGRANT, rn, "EA", m_res, ev_n)
        tk.q[("pass_com", net, GRANT)] = Qty("pass_com", net, GRANT, com_total - cn, "EA", m_com, ev[(net, "CC")])
        tk.q[("pass_com", net, NONGRANT)] = Qty("pass_com", net, NONGRANT, cn, "EA", m_com, list(com_ng[net].values()))
        m = "FMMULTIADD RESIDENTIAL_COUNT + COMMERCIAL_COUNT by the block's location"
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
TRENCH_NO_FIBER_FT = 200.0  # a trench label this far from every fiber cable carries no fiber


def route_footage(d, conv, cls, tk: Takeoff):
    """Rows 6-10 (CalcFTG): sum of CX1-FTG-N2 route labels inside the boundary.

    Aerial strand counts only where an aerial fiber cable is lashed to it (within
    fiber_bearing_strand_ft); strand of the RF (coax) plant is not FTTH route (design standard: RF support
    structures are not calculated). UG trench with no fiber cable within TRENCH_NO_FIBER_FT is
    counted (the Credit River BOM counts it) but listed, and the `fiber_bearing` policy drops it."""
    names = set(conv["blocks"]["route_footage"]["names"])
    groups = {"route_ug_ft": conv["route_layers"]["ug_trench"], "route_aerial_ft": conv["route_layers"]["aerial_strand"],
              "route_ugdrop_ft": conv["route_layers"]["ug_drop"]}
    aerial_fiber = SegIndex(fiber_cables(d, conv, ("aerial",)))
    any_fiber = SegIndex(fiber_cables(d, conv))
    strand_ft = conv.get("fiber_bearing_strand_ft", 75.0)
    ours, others = tk.extra.get("our_paths"), tk.extra.get("foreign_paths")
    coax_lines = [p for p in d.polylines if re.match(conv.get("coax_layer_regex", r"^DES_\d+[PT]\d+[AU]$"), p.layer)]
    coax = SegIndex(coax_lines) if coax_lines else None
    tk.extra.setdefault("trench_no_fiber", [])
    for key, layers in groups.items():
        tk.ensure(key, "FT", f"sum of {sorted(names)} FTG labels on {layers}")
        for ins in d.inserts:
            if ins.name in names and ins.layer in layers:
                v = num(ins.attr("FTG"))
                if v is None:
                    tk.check("route label value", False, f"{ins.handle} on {ins.layer} has no numeric FTG", warn=True)
                    continue
                if key == "route_aerial_ft" and aerial_fiber.nearest(ins.pt, strand_ft) is None:
                    if cls.resolve(ins.pt)[0] in tk.networks:  # report only this job's strand
                        tk.extra.setdefault("rf_structures", []).append(("route_aerial_ft", ins.handle, ins.pt,
                                                                         f"{v:g} ft strand with no aerial fiber cable within {strand_ft:g} ft"))
                        tk.check("RF support structure strand", False, f"strand label {ins.handle} ({v:g} ft) carries no fiber "
                                 f"(no aerial fiber cable within {strand_ft:g} ft) - RF strand, not counted", warn=True)
                    continue
                if key == "route_ug_ft" and coax is not None:
                    d_c = coax.nearest(ins.pt, 40.0)
                    if d_c is not None and (ours is None or ours.nearest(ins.pt, 75.0) is None):
                        tk.extra.setdefault("rf_structures", []).append(("route_ug_ft", ins.handle, ins.pt,
                                                                         f"{v:g} ft trench along RF coax ({d_c:.0f} ft), no fiber of this design"))
                        tk.check("RF support structure trench", False, f"trench label {ins.handle} ({v:g} ft) carries RF coax and no fiber "
                                 "of this design - not counted", warn=True)
                        continue
                if key != "route_ugdrop_ft" and others is not None:
                    d_o, d_f = ours.nearest(ins.pt, 75.0), others.nearest(ins.pt, 75.0)
                    if d_f is not None and (d_o is None or d_f < d_o):
                        exclude(tk, "Other fiber network", f"route label {ins.handle}", f"{v:g} ft",
                                f"trench/strand of another network's fiber ({d_f:.0f} ft)", ins.pt)
                        continue
                net, area = _locate(cls, ins, tk)
                if net:
                    tk.add(key, net, area, v, "FT", f"sum of FTG labels on {layers}", [ins.handle])
                    if key == "route_ug_ft" and any_fiber.nearest(ins.pt, TRENCH_NO_FIBER_FT) is None:
                        tk.extra["trench_no_fiber"].append((net, area, v, ins.handle, ins.pt))
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


def _spans(path, breaks, cls, tol=3.0, mode: str = "downstream", feeds=None, end=None, inside_out=None):
    """Split a routed path (A end -> B end) at splice / structure points and classify each span.

    downstream  the area of the span's downstream end, i.e. the ped / splice it feeds: a span
                entering a Non-Grant area is Non-Grant from its start (design standard). `feeds(p)` gives
                the area of the structure at p (boundary rule, as the structure itself is counted);
                `end` is the B splice position (the path's last vertex is only the nearest cable vertex)
    majority    the area holding the majority of the span's length"""
    feeds = feeds or cls.area_of
    cuts, at = [0], {}
    for i in range(1, len(path) - 1):
        p = path[i]
        for k in breaks.get((int(p[0] // 50), int(p[1] // 50)), []):
            if dist(p, k) <= tol:
                cuts.append(i)
                at[i] = k
                break
    cuts.append(len(path) - 1)
    at[len(path) - 1] = end if end is not None else path[-1]
    out = []
    for i0, i1 in zip(cuts, cuts[1:]):
        piece = path[i0 : i1 + 1]
        L = polyline_length(piece)
        if L <= 0:
            continue
        if mode == "downstream":
            out.append((L, feeds(at.get(i1, path[i1]))))
            if inside_out is not None:
                inside_out.append(length_inside(piece, cls.nongrant))
        else:
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


SPAN_CROSSING_FT = 300.0  # span length lying in the other area than the ped it feeds, worth showing


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
    feeds = StructureAreas(d, conv, cls).area
    leaders = d.leaders
    netset = {n.upper(): n for n in net_names}
    known = {**{n.upper(): n for n in cls.foreign}, **netset}
    scope = tk.extra.get("scope") or design_scope(d, conv, tk)
    foreign_paths: list = []
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
        # the cable belongs to the network of its first end that names one (A end first), whether or
        # not that network is in this job, so per-OLM runs and combined runs book it identically
        net = foreign = None
        for end in (a, b):
            e = end.upper()
            owner = known.get(e) or known.get((network_from_splice_name(e) or "").upper())
            if owner:
                net, foreign = (owner, None) if owner in netset.values() else (None, owner)
                break
        if net is None and foreign is None:
            net = cls.network_of(ins.pt, f"cable label {segname}")
            foreign = None if net else cls.foreign_of(ins.pt)
        if net is None and foreign:
            # another network of the same drawing: not this job's material, kept for topology (end of line)
            tk.foreign_cables.append((a, b, foreign, segname.upper()))
            continue
        other = _foreign_end(a, b, scope)
        if other:
            exclude(tk, "Other fiber network", segname, f"{total:g} ft", other, ins.pt)
            pa_, pb_ = _resolve_endpoint(a, pos), _resolve_endpoint(b, pos)
            if pa_ and pb_:
                na_, _ = graph.nearest(pa_)
                nb_, _ = graph.nearest(pb_)
                fp = graph.path(na_, nb_) if na_ and nb_ else None
                if fp:
                    foreign_paths.append(Polyline(f"x{ins.handle}", "foreign", fp))
            continue
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
            inside: list[float] = []
            seg.spans = _spans(path, breaks, cls, mode="downstream", feeds=feeds, end=pb, inside_out=inside)
            for (L, ar), ins_len in zip(seg.spans, inside):
                # a long run through the other area than the ped it feeds: booked by the standard, shown to the reviewer
                other = ins_len if ar == GRANT else L - ins_len
                if other >= SPAN_CROSSING_FT:
                    tk.extra.setdefault("span_crossings", []).append((net, segname, round(L), round(other), ar))
            seg.ng_fraction_length = length_inside(path, cls.nongrant) / plen if plen else 0.0
            seg.ng_fraction_majority = sum(L for L, ar in _spans(path, breaks, cls, mode="majority") if ar == NONGRANT) / plen if plen else 0.0
            if split_mode == "span":
                ng_len = sum(L for L, ar in seg.spans if ar == NONGRANT)
                seg.split_method = "route spans (splice to splice), each in the area of the ped / splice it feeds"
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
            seg.fallback_areas = (cls.area_of(p),) + tuple(cls.area_of(e) for e in (pa, pb) if e)
            same = len(seg.fallback_areas) == 3 and len(set(seg.fallback_areas)) == 1
            tk.check("cable route", False, f"{segname}: route between {a} and {b} not found in cable polylines; whole segment classified at label"
                     + (f" (label and both ends in {seg.fallback_areas[0]}: split not affected)" if same else ""), warn=True)
        tk.cables.append(seg)

    tk.extra["our_paths"] = SegIndex([Polyline(c.handle, "ours", c.path) for c in tk.cables if c.path and len(c.path) > 1])
    tk.extra["foreign_paths"] = SegIndex(foreign_paths) if foreign_paths else None

    # cables present in the splice reports but carrying no DWG cable label
    # (e.g. the 100 ft OLM -> first splice FC024 tail). Real cable: include + flag.
    labelled = {c.name.upper() for c in tk.cables} | {f[3] for f in tk.foreign_cables}
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
        if r.network in cls.foreign:
            tk.foreign_cables.append((a, mm.group(2) if mm else "", r.network, name))
            continue
        if _foreign_end(a, mm.group(2) if mm else "", scope):
            continue
        net = r.network if r.network in tk.networks else None
        pa = _resolve_endpoint(a, pos) if a else None
        pb = _resolve_endpoint(mm.group(2), pos) if mm else None
        area = cls.area_of(pa) if pa else GRANT
        c = CableSegment(handle=f"report:{r.name}", name=sg.cable, a=a, b=mm.group(2) if mm else "", fibers=sg.fibers,
                         placement="AR" if sg.placement.lower().startswith("aer") else "UG", route_ft=sg.design_length or 0,
                         slack_ft=0, total_ft=sg.design_length or 0, network=net,
                         ng_fraction=1.0 if area == NONGRANT else 0.0, ng_fraction_length=1.0 if area == NONGRANT else 0.0,
                         split_method="splice report only (no DWG cable label)")
        if pa and pb:
            c.fallback_areas = (area, area, cls.area_of(pb))
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
    # round so Grant + Non-Grant = the rounded network total (separate rounding could lose 1 ft)
    for (k, n, a), q in list(tk.q.items()):
        if k.startswith("cable_") and a == NONGRANT:
            g = tk.q.get((k, n, GRANT))
            total = round(q.value + (g.value if g else 0))
            q.value = round(q.value)
            if g:
                g.value = total - q.value


# ----------------------------------------------------------------- splice reports
TRAY_CAPACITY = {"B": 24, "D": 48}  # splices per tray: ACC-B-24 tray, FOSC-ACC-D-TRAY-48 (CommScope ordering guide)
# trays one closure holds with its basket installed (ordering guide: B basket 'limit 6 trays', Tall basket 'limit 5')
TRAYS_PER_CLOSURE = {"B": 6, "D": 5}
# 'FOSC 450D', 'FOSC450-D', 'FOSC-450B', '450 D', 'Fosc 450-b' ... (shared with the deep check)
ENCL_RE = re.compile(r"(?<![0-9])450\s*-?\s*([A-D])(?![A-Z])", re.I)
NON_BOM_ENCLOSURES = ("SPLICE CASE",)  # splices made inside the MAX ped: no FOSC enclosure line


def enclosure_letter(enclosure: str | None, conv: dict | None = None) -> str | None:
    """FOSC 450 size letter of a splice-report Enclosure Type, None when it is not a FOSC 450."""
    m = ENCL_RE.search(enclosure or "")
    return m.group(1).upper() if m else None


def enclosure_is_non_bom(enclosure: str | None, conv: dict | None = None) -> bool:
    names = (conv or {}).get("non_bom_enclosures", NON_BOM_ENCLOSURES)
    return any(n.upper() in (enclosure or "").upper() for n in names)


def enclosures(d, conv, cls, tk: Takeoff, reports: list[SpliceReport]):
    pos = {}
    for ins in _blocks(d, conv, "splice_point"):
        pos.setdefault(ins.attr("NAME").upper(), ins.pt)
    if not reports:
        return  # enclosures and trays are not counted without splice reports (left blank, not 0)
    for L in "bd":
        tk.ensure(f"trays_450{L}", "EA", "per enclosure ROUNDUP(splices / tray capacity)")
    # FOSC450-D6-6-NT-0-T3V: the 'T' is the tall slack basket, shipped with the closure (CommScope ordering
    # guide), so no separate D basket is ordered; the approved BOM orders 0
    tk.ensure("basket_d", "EA", "0: the T3V 450D closure includes its tall basket")
    for letter in "ABCD":
        tk.ensure(f"fosc450{letter.lower()}", "EA", "splice report Enclosure Type")
        tk.ensure(f"fosc450{letter.lower()}_splices", "EA", "fusion splices in enclosure (splice report)")
    housing = StructureAreas(d, conv, cls)
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
        if r.enclosure and not m and not enclosure_is_non_bom(r.enclosure, conv):
            tk.check("enclosure type unknown", False, f"{r.name}: Enclosure Type '{r.enclosure}' is not a FOSC 450 A-D "
                     "and not a known non-BOM type - not counted", warn=True)
        p = pos.get(r.name.upper()) or r.coords
        net = None
        if p:
            net = cls.network_of(p, f"splice {r.name}")
        if net is None and r.network in tk.networks:
            net = r.network
        area = housing.area(p) if p else GRANT  # the closure sits in a ped / vault: same column as its housing
        if not r.enclosure:
            tk.check("splice report enclosure", False, f"{r.name}: Enclosure Type blank", warn=True)
        if m and net:
            k = f"fosc450{m.group(1).lower()}"
            tk.add(k, net, area, 1, "EA", "splice report Enclosure Type", [r.name])
            tk.add(k + "_splices", net, area, r.fusion_splices, "EA", "fusion splices in enclosure", [r.name])
            cap = TRAY_CAPACITY.get(m.group(1).upper())
            if cap:
                # Design standard: trays per splice location = ROUNDUP(splices / tray capacity);
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
        # Design standard: OLM equipment is always booked to Grant (1 per OLM) unless the whole OLM area is Non-Grant
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
            # Design standard: SFP = ROUNDUP(Jumper Calculator 'Splitters Required' / 2), where the calculator uses
            # ROUNDUP(passings/32) whatever splitter is actually designed
            tk.q[("pon_ports", n, a)] = Qty("pon_ports", n, a, math.ceil(math.ceil(p / 32) / 2) if p else 0, "EA",
                                            "ROUNDUP(ROUNDUP(passings/32)/2) (Jumper Calculator / 2)", [])
        # a second split ratio in the same network (e.g. an MDU node on 1x64 in a 1x32 design): write its
        # designed count too, in the column of each coupler's splice location
        for r2 in (32, 64):
            extra = tk.total(f"report_splitter_1x{r2}", n) if r2 != ratio else 0
            if not extra:
                continue
            for a in AREAS:
                tk.q[(f"splitter_1x{r2}", n, a)] = Qty(f"splitter_1x{r2}", n, a, tk.get(f"report_splitter_1x{r2}", n, a, 0), "EA",
                                                       f"designed 1x{r2} couplers (splice reports), by splice location", [])
            tk.check(f"mixed split ratios {n}", False, f"main 1x{ratio} plus {extra:g} x 1x{r2} in the splice reports - both written; "
                     "confirm the PON design", warn=True)
            need += int(extra)
        tk.extra.setdefault("designed_pons", {})[n] = need
        if reports:
            rep = sum(tk.total(f"report_splitter_1x{r2}", n) for r2 in (32, 64))
            tk.check(f"splitters vs splice reports {n}", rep == need, f"design rule {need} splitters (main 1x{ratio}) vs splice-report PLC COUPLER rows {rep:g}")
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
    tol = conv.get("boundary_structure_tolerance_ft", 5.0)
    for key in ("ped_max10", "ped_max5"):
        for ins in _blocks(d, conv, key):
            ports = sum(v for p, v in hc if dist(p, ins.pt) <= 30) + sum(v for p, v in cc if dist(p, ins.pt) <= 50)
            net, area = cls.network_of(ins.pt, ins.handle), structure_area(cls, ins.pt, tol)
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
        # the drop follows the address it serves, by the same rule as the passings
        if addr.name in conv["blocks"]["res_address"]["names"] and conv.get("passings_area_rule", "boundary") == "grant_layer":
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
        # design standard (confirmed): Non-Grant drops in the Non-Grant column, Grant = total - Non-Grant in the Grant column
        for a in AREAS:
            tk.q[("drop_ft_bom", n, a)] = Qty("drop_ft_bom", n, a, tk.get("drop_ft", n, a, 0), "FT",
                                              "FX_DROPS drop footage by the area of the served address", [])


GROUND_HUB_MAX_FT = 250.0  # OLM block -> its hub splice point (NMK 63-132 ft, DMI 66 ft)
ON_PATH_FT = 3.0  # routed cable paths pass through the splice points (measured 0 ft); same tolerance as _spans


def _first_on_path(path, points: dict[str, Insert], exclude: str) -> str | None:
    """Name of the first splice point lying on a routed path (by distance along the path)."""
    if len(path) < 2:
        return None
    xs, ys = [p[0] for p in path], [p[1] for p in path]
    x0, x1, y0, y1 = min(xs) - ON_PATH_FT, max(xs) + ON_PATH_FT, min(ys) - ON_PATH_FT, max(ys) + ON_PATH_FT
    best = None
    for name, ins in points.items():
        p = ins.pt
        if name == exclude or not (x0 <= p[0] <= x1 and y0 <= p[1] <= y1):
            continue
        acc = 0.0
        for a, b in zip(path, path[1:]):
            seg = dist(a, b)
            if point_segment_distance(p, a, b) <= ON_PATH_FT:
                t = 0.0 if seg == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / seg / seg))
                s = acc + t * seg
                if best is None or s < best[0]:
                    best = (s, name)
                break
            acc += seg
    return best[1] if best else None


def ground_locations(d, conv, tk: Takeoff) -> tuple[dict[str, set[str]], dict[str, Insert], set[str]]:
    """Splice locations that get a ground wire kit (FE0-07264810), each with its reasons.

    Blank-template note on the line: "Hand count for grounds: all splices with letter G
    at end, first in line, any ending in a zero, and also EOL peds".
      G suffix       splice name ends in G
      ends in 0      splice name ends in 0
      first in line  first splice point on the routed path of each cable leaving the OLM
                     hub (the splice point nearest the OLM block)
      end of line    a cable ends there and no cable starts there
    """
    points: dict[str, Insert] = {}
    for ins in _blocks(d, conv, "splice_point"):
        nm = (ins.attr("NAME") or "").strip().upper()
        if nm and nm not in points:
            points[nm] = ins
    reasons: dict[str, set[str]] = defaultdict(set)
    for nm in points:
        if nm.endswith("G"):
            reasons[nm].add("G suffix")
        if nm.endswith("0"):
            reasons[nm].add("ends in 0")
    # topology uses every cable in the drawing, including other networks' (per-OLM runs = combined run)
    ends_ab = [(c.a.upper(), c.b.upper()) for c in tk.cables] + [(f[0].upper(), f[1].upper()) for f in tk.foreign_cables]
    starts = {a for a, _b in ends_ab}
    for _a, b in ends_ab:
        if b in points and b not in starts:
            reasons[b].add("end of line")
    hubs: set[str] = set()
    for olm in _blocks(d, conv, "olm"):
        near = min(points.items(), key=lambda kv: dist(kv[1].pt, olm.pt), default=None)
        if near and dist(near[1].pt, olm.pt) <= GROUND_HUB_MAX_FT:
            hubs.add(near[0])
    for c in tk.cables:
        if c.a.upper() in hubs and c.path:
            first = _first_on_path(c.path, points, exclude=c.a.upper())
            if first:
                reasons[first].add("first in line")
    return reasons, points, hubs


def grounding_points(d, conv, cls, tk: Takeoff):
    method = "ground wire kits: splices named ...G, first in line after the OLM, names ending in 0, end-of-line (template note)"
    tk.ensure("grounding_points", "EA", method)
    reasons, points, hubs = ground_locations(d, conv, tk)
    if _blocks(d, conv, "olm") and not hubs:
        tk.check("ground kits: OLM hub", False, f"no splice point within {GROUND_HUB_MAX_FT:g} ft of the OLM block - "
                 "'first in line' grounds not counted", warn=True)
    rows = []
    housing = StructureAreas(d, conv, cls)
    for nm in sorted(reasons):
        net, _a = _locate(cls, points[nm], tk)
        if not net:
            continue
        area = housing.area(points[nm].pt)
        why = sorted(reasons[nm])
        rows.append((net, area, nm, why))
        tk.add("grounding_points", net, area, 1, "EA", method, [f"{nm} ({', '.join(why)})"])
    tk.extra["ground"] = rows


def build_takeoff(d: Drawing, conv: dict, cls: Classifier, networks: list[str],
                  address_lists: dict[str, AddressList], reports: list[SpliceReport],
                  policies: dict[str, str] | None = None) -> Takeoff:
    tk = Takeoff(networks)
    resolve_report_networks(d, conv, cls, tk, reports)
    design_scope(d, conv, tk)
    passings(d, conv, cls, tk, address_lists)
    cable_footage(d, conv, cls, tk, networks, reports)  # first: structures and route are judged against its paths
    for key in ("ped_max10", "ped_max5", "vault", "ug_lbox"):
        count_blocks(d, conv, cls, tk, key)
    route_footage(d, conv, cls, tk)
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
    for n in networks:
        if n not in cls.networks and not (cls.single_network == n and not cls.networks):
            # no boundary for this network: every drawing quantity would be a false zero - leave the BOM blank
            for k in [k for k in tk.q if k[1] == n]:
                del tk.q[k]
            tk.check(f"network boundary {n}", False, f"no boundary polygon for {n} in the drawing - its quantities are left blank "
                     "(see the NETWORK_BOUNDARY issue)")
    if cls.nearest_assigned:
        tk.checks.append(Check("objects outside boundaries", "WARN",
                               f"{len(cls.nearest_assigned)} objects outside every network boundary were assigned via the transport corridor "
                               f"or to the nearest network within {cls.tolerance:g} ft (listed in 'Network Assignment')"))
    if tk.unassigned:
        tk.checks.append(Check("unassigned objects", "WARN", f"{len(tk.unassigned)} objects could not be assigned to a network"))
    return tk
