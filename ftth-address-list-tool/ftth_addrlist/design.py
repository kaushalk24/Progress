"""Design model read from the drawing (DWG via the built-in decoder, or DXF via ezdxf).

The model holds what the Fiber Splice resolver needs, all taken from drawn objects:

  * closures        - splice closure symbols with their NAME attribute,
  * enclosures      - tap enclosure symbols, each tied to its closure by a drawn pigtail,
  * address points  - premise symbols with street number / street name attributes,
  * drop symbols    - drop markers (position and rotation),
  * cable graph     - fibre cable polylines, vertices joined where they meet; closures are nodes.

Block names, attribute tags, layers and tolerances come from the [drawing] configuration section.
"""

from __future__ import annotations

import collections
import heapq
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from .model import Issue

DIRECTIONS = {"N", "S", "E", "W", "NE", "NW", "SE", "SW"}
STREET_TYPES = {"AVE", "ST", "RD", "DR", "LN", "CT", "CIR", "BLVD", "TRL", "WAY", "PL", "PKWY", "HWY", "TER",
                "LOOP", "RUN", "PATH", "SQ", "XING"}


@dataclass
class Insert:
    block: str
    layer: str
    x: float
    y: float
    rot: float
    attribs: dict[str, str] = field(default_factory=dict)


@dataclass
class Polyline:
    layer: str
    points: list[tuple[float, float]]


def street_core(street: str) -> str:
    """Street name without leading/trailing directions and the street type: 'S OAK ST' -> 'OAK'."""
    toks = []
    for t in re.split(r"[\s,]+", (street or "").upper()):
        if t and (not toks or toks[-1] != t):       # 'HIGHWAY X9 X9' -> 'HIGHWAY X9'
            toks.append(t)
    while toks and toks[0] in DIRECTIONS:
        toks = toks[1:]
    while toks and (toks[-1] in STREET_TYPES or toks[-1] in DIRECTIONS):
        toks = toks[:-1]
    return " ".join(toks)


def street_full(street: str) -> str:
    """Street name without the street type but with its directions: 'S OAK ST' -> 'S OAK'."""
    toks = []
    for t in re.split(r"[\s,]+", (street or "").upper()):
        if t and (not toks or toks[-1] != t):
            toks.append(t)
    return " ".join(t for i, t in enumerate(toks) if i == 0 or t not in STREET_TYPES)


def address_rest(address: str) -> str:
    """Street part of an address after the house number, units removed."""
    m = re.match(r"^\s*(?:C-|VAC\s+)?\d+\s+(.*)$", (address or "").upper())
    return re.sub(r"(?:\b(?:UNIT|APT|BLDG|STE)\b|#)\s*[\w-]+", " ", m.group(1)) if m else ""


def split_label(address: str) -> tuple[str, str]:
    """First word and street core of an address without a numeric house number:
    '12TH AVE AVE' -> ('12TH', ''), 'NA ELM ST' -> ('NA', 'ELM')."""
    words = re.sub(r"^\s*(?:C-|VAC\s+)", "", (address or "").upper()).split()
    return (words[0] if words else ""), street_core(" ".join(words[1:]))


def split_address(address: str) -> tuple[str | None, str | None]:
    """'C-2309 12TH AVE UNIT 2' -> ('2309', '12TH'). Addresses without a numeric house number -> (None, None)."""
    m = re.match(r"^\s*(?:C-|VAC\s+)?(\d+)\s+(.*)$", (address or "").upper())
    if not m:
        return None, None
    return m.group(1), street_core(re.sub(r"(?:\b(?:UNIT|APT|BLDG|STE)\b|#)\s*[\w-]+", " ", m.group(2)))


def address_text(attribs: dict[str, str], dcfg: dict) -> str | None:
    """'<number> <street>' of an address-point block from the configured attribute tag pairs."""
    for num_tag, street_tag in dcfg.get("address_tags", [["STREET_NUMBER", "STREET_NAME"]]):
        num, street = attribs.get(num_tag.upper(), "").strip(), attribs.get(street_tag.upper(), "").strip()
        if num and street:
            return f"{num} {street}".upper()
    return None


def streets_match(a: str, b: str) -> bool:
    """Street cores equal, or one is the other plus trailing words ('STATE' ~ 'STATE HIGHWAY 14')."""
    if not a or not b:
        return False
    return a == b or a.startswith(b + " ") or b.startswith(a + " ")


# ---------------------------------------------------------------------------------------- readers
_DWG_CACHE: dict[tuple, tuple] = {}


def dwg_entities(path: Path):
    """(inserts, lines, texts, meta) of a DWG; decoded once per file version."""
    key = (str(Path(path).resolve()), Path(path).stat().st_mtime_ns)
    if key not in _DWG_CACHE:
        _DWG_CACHE.clear()
        _DWG_CACHE[key] = _entities_from_dwg(Path(path))
    return _DWG_CACHE[key]


def _entities_from_dwg(path: Path):
    from .dwg_container import DwgContainer
    from .dwg_objects import ATTRIB, BLOCK_HEADER, INSERT, LAYER, LINE, LWPOLYLINE, MTEXT, TEXT, read_objects
    objs = read_objects(DwgContainer(path))
    recs = objs.records
    texts = [r.get("text") or "" for r in recs.values() if r["type"] in (TEXT, MTEXT, ATTRIB)]
    texts += [r["name"] for r in recs.values() if r["type"] == BLOCK_HEADER]
    layers = {h: r["name"] for h, r in recs.items() if r["type"] == LAYER}
    blocks = {h: r["name"] for h, r in recs.items() if r["type"] == BLOCK_HEADER}
    inserts, lines = [], []
    for r in recs.values():
        if r.get("entmode") != 2:          # model space only (block contents and paper space excluded)
            continue
        if r["type"] == INSERT:
            att = {}
            for a in r["attribs"]:
                ar = recs.get(a)
                if ar is not None and ar["type"] == ATTRIB and ar.get("tag"):
                    att[ar["tag"].upper()] = " ".join(str(ar.get("text") or "").split())
            inserts.append(Insert(blocks.get(r["block"], ""), layers.get(r["layer"], ""), r["x"], r["y"], r["rot"],
                                  att))
        elif r["type"] in (LWPOLYLINE, LINE):
            lines.append(Polyline(layers.get(r["layer"], ""), r["points"]))
    meta = {"method": f"DWG {objs.version} object decoder", "objects": objs.objects, "decode_errors": objs.errors}
    return inserts, lines, texts, meta


def _entities_from_dxf(path: Path):
    from ezdxf import recover  # optional dependency
    doc, auditor = recover.readfile(str(path))
    inserts, lines = [], []
    for e in doc.modelspace():
        t = e.dxftype()
        if t == "INSERT":
            att = {a.dxf.get("tag", "").upper(): " ".join(str(a.dxf.get("text", "")).split()) for a in e.attribs}
            ip = e.dxf.insert
            inserts.append(Insert(e.dxf.name, e.dxf.get("layer", ""), ip.x, ip.y,
                                  math.radians(e.dxf.get("rotation", 0.0)), att))
        elif t == "LWPOLYLINE":
            lines.append(Polyline(e.dxf.get("layer", ""), [(p[0], p[1]) for p in e.get_points("xy")]))
        elif t == "LINE":
            lines.append(Polyline(e.dxf.get("layer", ""), [(e.dxf.start.x, e.dxf.start.y),
                                                             (e.dxf.end.x, e.dxf.end.y)]))
    meta = {"method": "DXF (ezdxf)", "objects": len(doc.entitydb), "decode_errors": len(auditor.errors) if auditor else 0}
    return inserts, lines, meta


# ---------------------------------------------------------------------------------------- model
class Design:
    def __init__(self, inserts: list[Insert], lines: list[Polyline], cfg: dict, source: str, method: str):
        d = cfg["drawing"]
        self.cfg = d
        self.source, self.method = source, method
        self.issues: list[Issue] = []
        self.closures: dict[str, tuple[float, float]] = {}
        self.enclosures: list[dict] = []
        self.addresses: list[dict] = []
        self.drops: list[tuple[float, float, float]] = []
        self.peds: list[tuple[float, float]] = []
        closure_blocks, encl_blocks = set(d["closure_blocks"]), set(d["enclosure_blocks"])
        addr_blocks, drop_blocks = set(d["address_blocks"]), set(d["drop_blocks"])
        ped_blocks = set(d.get("ped_blocks", []))
        for ins in inserts:
            if ins.block in closure_blocks:
                name = ins.attribs.get(d["closure_name_tag"].upper(), "").strip()
                if name:
                    self.closures.setdefault(name, (ins.x, ins.y))
            elif ins.block in encl_blocks:
                self.enclosures.append({"xy": (ins.x, ins.y), "closure": None, "link": None})
            elif ins.block in addr_blocks:
                raw = address_text(ins.attribs, d)
                if raw:
                    num, core = split_address(raw)
                    tok = None if num else split_label(raw)[0]
                    if not num:
                        core = split_label(raw)[1]
                    self.addresses.append({"num": num, "tok": tok, "street": core, "raw": raw,
                                           "full": street_full(address_rest(raw)) if num else "",
                                           "xy": (ins.x, ins.y), "drawn_drops": []})
            elif ins.block in drop_blocks:
                self.drops.append((ins.x, ins.y, ins.rot))
            elif ins.block in ped_blocks:
                self.peds.append((ins.x, ins.y))
        self._link_enclosures(lines)
        self.enclosure_of: dict[str, dict] = {}
        for e in self.enclosures:
            if e["closure"] is not None:
                self.enclosure_of.setdefault(e["closure"], e)
        self._build_graph(lines)
        self.drawn_drops: list[dict] = []
        self._read_drawn_drops(lines)

    # -------------------------------------------------------------- drawn drop lines
    def _read_drawn_drops(self, lines: list[Polyline]):
        """Drop lines drawn from a ped (tap pedestal) to a premise, e.g. by the FX_DROPS routine.
        Each is tied to the address point at its house end and to the closure nearest its ped."""
        layers = set(self.cfg.get("drop_line_layers", []))
        if not layers:
            return
        snap = float(self.cfg.get("drop_end_snap", 15.0))
        far = float(self.cfg.get("ped_closure_max", 100.0))
        cl = list(self.closures.items())
        unattached = 0
        for ln in lines:
            if ln.layer not in layers or len(ln.points) < 2 or not self.peds or not cl:
                continue
            ends = (ln.points[0], ln.points[-1])
            pd = [min(math.dist(e, p) for p in self.peds) for e in ends]
            i = 0 if pd[0] <= pd[1] else 1
            ped_end, house_end = ends[i], ends[1 - i]
            ped = min(self.peds, key=lambda p: math.dist(p, ped_end))
            addr = min(self.addresses, key=lambda a: math.dist(a["xy"], house_end), default=None)
            if pd[i] > snap or addr is None or math.dist(addr["xy"], house_end) > snap:
                unattached += 1
                continue
            near = sorted((math.dist(ped, xy), n) for n, xy in cl)[:2]
            if near[0][0] > far:
                unattached += 1
                continue
            alt = near[1] if len(near) > 1 and near[1][0] < 1.25 * near[0][0] else None
            drop = {"address": addr["raw"], "house": house_end, "ped": ped, "closure": near[0][1],
                    "ped_dist": near[0][0], "alternative": alt[1] if alt else None,
                    "length": sum(math.dist(a, b) for a, b in zip(ln.points, ln.points[1:]))}
            addr["drawn_drops"].append(drop)
            self.drawn_drops.append(drop)
        if unattached:
            self.issues.append(Issue("INFO", "DRAWING_DROP_UNATTACHED",
                                     f"{unattached} drawn drop line(s) in {self.source} do not join a ped to an "
                                     f"address point; they are not used"))

    def drawn_drop_closures(self, points: list[dict]) -> dict[str, tuple[str, dict]]:
        """Closures named by the drawn drops of these address points: closure -> ('drop' | 'alternative', drop).
        'alternative' = a second closure almost as close to the ped (the drop does not decide between them)."""
        out: dict[str, tuple[str, dict]] = {}
        for p in points:
            for dr in p.get("drawn_drops", []):
                out[dr["closure"]] = ("drop", dr)
                if dr["alternative"] and dr["alternative"] not in out:
                    out[dr["alternative"]] = ("alternative", dr)
        return out

    # -------------------------------------------------------------- enclosures
    def _link_enclosures(self, lines: list[Polyline]):
        """A tap enclosure belongs to the closure its pigtail polyline starts from."""
        snap = float(self.cfg["pigtail_snap"])
        pig = [p for p in lines if p.layer == self.cfg["pigtail_layer"] and len(p.points) >= 2]
        cl = list(self.closures.items())
        unlinked = 0
        for e in self.enclosures:
            for p in pig:
                for i, j in ((0, -1), (-1, 0)):
                    if math.dist(p.points[i], e["xy"]) <= snap and cl:
                        name, dist = min(((n, math.dist(p.points[j], xy)) for n, xy in cl), key=lambda t: t[1])
                        if dist <= snap:
                            e["closure"], e["link"] = name, "pigtail"
                if e["closure"]:
                    break
            if e["closure"] is None:
                unlinked += 1
        if unlinked:
            self.issues.append(Issue("INFO", "DRAWING_ENCLOSURE_UNLINKED",
                                     f"{unlinked} tap enclosure symbol(s) have no pigtail to a closure in "
                                     f"{self.source}; they are not used"))

    # -------------------------------------------------------------- cable graph
    def _build_graph(self, lines: list[Polyline]):
        tol = float(self.cfg["node_snap"])
        self._tol = tol
        key = lambda p: (round(p[0] / tol), round(p[1] / tol))
        node_cl: dict[tuple, str] = {}
        for n, xy in self.closures.items():
            node_cl.setdefault(key(xy), n)
        self.adj: dict[tuple, set] = collections.defaultdict(set)

        def node(p):
            k = key(p)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    kk = (k[0] + dx, k[1] + dy)
                    if kk in node_cl:
                        return ("C", node_cl[kk])
            return ("P", k)
        prefix, pig = self.cfg["cable_layer_prefix"], self.cfg["pigtail_layer"]
        for ln in lines:
            if not ln.layer.startswith(prefix) or ln.layer == pig:
                continue
            pts = [node(p) for p in ln.points]
            for a, b in zip(pts, pts[1:]):
                if a != b:
                    self.adj[a].add(b)
                    self.adj[b].add(a)

    def _xy(self, n) -> tuple[float, float]:
        return self.closures[n[1]] if n[0] == "C" else (n[1][0] * self._tol, n[1][1] * self._tol)

    def region(self, starts: set[str], stop_at: set[str]) -> set[str]:
        """Closures reachable along drawn cables from `starts` without passing through a closure in
        `stop_at` (closures whose splice reports were supplied: the fibre would have been seen there)."""
        seen, out = set(), set()
        stack = [("C", s) for s in starts if s in self.closures]
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            if n[0] == "C":
                out.add(n[1])
                if n[1] in stop_at and n[1] not in starts:
                    continue
            for m in self.adj.get(n, ()):
                if m not in seen and not (m[0] == "C" and m[1] in stop_at and m[1] not in starts):
                    stack.append(m)
        return out

    def path_lengths(self, src: str, stop_at: set[str]) -> dict[str, float]:
        """Drawn cable length from closure `src` to every closure reachable without passing `stop_at`."""
        if src not in self.closures:
            return {}
        dist = {("C", src): 0.0}
        pq = [(0.0, ("C", src))]
        out: dict[str, float] = {}
        while pq:
            d, n = heapq.heappop(pq)
            if d > dist.get(n, math.inf):
                continue
            if n[0] == "C":
                out.setdefault(n[1], d)
                if n[1] in stop_at and n[1] != src:
                    continue
            for m in self.adj.get(n, ()):
                nd = d + math.dist(self._xy(n), self._xy(m))
                if nd < dist.get(m, math.inf):
                    dist[m] = nd
                    heapq.heappush(pq, (nd, m))
        return out

    # -------------------------------------------------------------- premises and drops
    def address_points(self, address: str) -> list[dict]:
        num, core = split_address(address)
        if not num:     # no house number: the same placeholder text, e.g. '12TH AVE AVE' ~ '12TH' + 'AVE'
            tok, core = split_label(address)
            return [a for a in self.addresses if a["num"] is None and tok and a["tok"] == tok and
                    a["street"] == core]
        full = street_full(address_rest(address))
        hits = [a for a in self.addresses if a["num"] == num and a["full"] == full]   # 'S OAK' != 'OAK'
        if not hits:
            hits = [a for a in self.addresses if a["num"] == num and a["street"] == core and
                    not (a["full"] != a["street"] and full != core)]   # both carry directions, and they differ
        if not hits and core:
            hits = [a for a in self.addresses if a["num"] == num and streets_match(core, a["street"])]
        return hits

    def drop_support(self, premise: tuple[float, float], enclosure: tuple[float, float]):
        """Best drop symbol on the premise-enclosure line, or None. A drop symbol is drawn part-way along
        the drop, close to the line, rotated to point from the enclosure towards the premise. Returns
        (score, symbol position); lower score = closer fit (offset in drawing units + angle in degrees +
        distance from the usual position along the line)."""
        d = self.cfg
        tmin, tmax = d["drop_position"]
        vx, vy = enclosure[0] - premise[0], enclosure[1] - premise[1]
        length = math.hypot(vx, vy)
        if length < 1:
            return None
        want = math.degrees(math.atan2(-vy, -vx))
        mid = d["drop_typical_position"]
        best = None
        for x, y, rot in self.drops:
            t = ((x - premise[0]) * vx + (y - premise[1]) * vy) / (length * length)
            if not tmin <= t <= tmax:
                continue
            off = abs((x - premise[0]) * vy - (y - premise[1]) * vx) / length
            if off > d["drop_max_offset"]:
                continue
            ang = abs((math.degrees(rot) - want + 180) % 360 - 180)
            if ang > d["drop_max_angle"]:
                continue
            score = off + ang + 20 * abs(t - mid)
            if best is None or score < best[0]:
                best = (score, (x, y))
        return best


def load_design(path: str | Path, cfg: dict) -> tuple[Design | None, list[Issue]]:
    path = Path(path)
    if not path.exists():
        return None, [Issue("ERROR", "DRAWING_MISSING", f"Drawing not found: {path}")]
    suffix = path.suffix.lower()
    try:
        if suffix == ".dwg":
            inserts, lines, _texts, meta = dwg_entities(path)
        elif suffix == ".dxf":
            try:
                inserts, lines, meta = _entities_from_dxf(path)
            except ImportError:
                return None, [Issue("ERROR", "DRAWING_NO_EZDXF", "Reading a DXF needs the 'ezdxf' package "
                                    "(pip install ezdxf)")]
        else:
            return None, [Issue("ERROR", "DRAWING_UNSUPPORTED", f"Unsupported drawing type {suffix}; use .dwg or .dxf")]
    except Exception as exc:  # any decoding failure: the drawing is simply not used
        return None, [Issue("WARNING", "DRAWING_MODEL_UNREADABLE",
                            f"{path.name}: design objects could not be read ({exc}); the drawing is not used to "
                            f"resolve Fiber Splice. Save as AutoCAD 2018 DWG or export a DXF.", source=path.name)]
    issues = []
    if meta["objects"] and meta["decode_errors"] > 0.01 * meta["objects"]:
        return None, [Issue("WARNING", "DRAWING_MODEL_UNRELIABLE",
                            f"{path.name}: {meta['decode_errors']} of {meta['objects']} objects could not be decoded; "
                            f"the drawing is not used to resolve Fiber Splice", source=path.name)]
    des = Design(inserts, lines, cfg, path.name, meta["method"])
    issues += des.issues
    linked = sum(1 for e in des.enclosures if e["closure"])
    issues.append(Issue("INFO", "DRAWING_MODEL",
                        f"{path.name} ({meta['method']}): {len(des.closures)} closures, {linked} tap enclosures with "
                        f"pigtail, {len(des.addresses)} address points, {len(des.drops)} drop symbols, "
                        f"{len(des.drawn_drops)} drawn drop lines", source=path.name))
    if not des.closures or not linked:
        issues.append(Issue("WARNING", "DRAWING_MODEL_EMPTY",
                            f"{path.name}: no closure or tap-enclosure symbols found with the configured block names "
                            f"([drawing] closure_blocks / enclosure_blocks)", source=path.name))
    return des, issues
