"""Connectivity index over a set of splice reports, and fibre tracing."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from .model import (CableFiber, Connection, DevicePort, Issue, Location, SegmentInfo, SpliceReport)
from .splice_reports import FMT_GUIDE


@dataclass
class SegmentEnds:
    cable: str
    seg: int
    count: int | None = None
    start: Location | None = None
    end: Location | None = None
    placement: str | None = None
    sources: list[str] = field(default_factory=list)

    def other_end(self, closure: str) -> Location | None:
        if self.start and self.start.name == closure:
            return self.end
        if self.end and self.end.name == closure:
            return self.start
        return None

    def touches(self, name: str) -> bool:
        return bool((self.start and self.start.name == name) or (self.end and self.end.name == name))


@dataclass
class TraceStep:
    closure: str
    conn: Connection | None
    arrived_on: CableFiber | None


@dataclass
class TraceResult:
    steps: list[TraceStep]
    stop: str                 # terminal | missing_report | not_listed | olm | device | unknown_segment | loop
    stop_location: Location | None
    last_closure: str
    last_fiber: CableFiber | None
    uses_guide: bool = False
    usage_conflicts: list[str] = field(default_factory=list)
    step: int | None = None
    seg_aliases: list[str] = field(default_factory=list)
    usage_variants: list[str] = field(default_factory=list)
    premise_variants: list[str] = field(default_factory=list)   # same circuit, but a different premise named
    path_closures: set = field(default_factory=set)
    route: list[str] = field(default_factory=list)   # closures in path order, incl. bridged ones without report

    def path_text(self) -> str:
        parts = [s.closure for s in self.steps]
        if self.stop_location is not None and self.stop in ("terminal", "missing_report", "olm"):
            parts.append(str(self.stop_location))
        return " > ".join(parts)


def _house_number(text: str | None) -> str | None:
    m = re.match(r"^\D*?(\d+)", text or "")
    return m.group(1) if m else None


def compare_usage(a: str | None, b: str | None, usage_re: re.Pattern) -> str:
    """'exact' | 'variant' (same tap port and house numbers, text differs - e.g. a street renamed
    between report revisions) | 'different'."""
    if a == b:
        return "exact"
    ma, mb = usage_re.match(a or ""), usage_re.match(b or "")
    if bool(ma) != bool(mb):
        # one side carries only an address (hand-made splice guides): compare addresses
        full, bare = (ma, b) if ma else (mb, a)
        norm = lambda t: " ".join((t or "").split()).upper()
        return "address_only" if norm(full.group("address")) == norm(bare) else "different"
    if not ma or not mb:
        return "different"
    if (ma.group("port") == mb.group("port")
            and _house_number(ma.group("tap")) == _house_number(mb.group("tap"))
            and _house_number(ma.group("address")) == _house_number(mb.group("address"))
            and _house_number(ma.group("address")) is not None):
        return "variant"
    return "different"


class Network:
    def __init__(self, reports: list[SpliceReport], cfg: dict):
        self.cfg = cfg
        self.issues: list[Issue] = []
        self.reports: dict[str, SpliceReport] = {}
        self.segments: dict[tuple[str, int], SegmentEnds] = {}
        self.conn_index: dict[str, dict[tuple, list[Connection]]] = {}
        self.devices = {}
        net = cfg["network"]
        self.terminal_kinds = set(net["terminal_kinds"])
        self.olm_kinds = set(net["olm_kinds"])
        self.usage_re = re.compile(cfg["address"]["usage_regex"])
        self._by_fiber = None
        for rep in reports:
            self._add(rep)

    # ----------------------------------------------------------------- build
    def _add(self, rep: SpliceReport):
        if rep.closure in self.reports:
            prev = self.reports[rep.closure]
            self.issues.append(Issue("ERROR", "DUPLICATE_REPORT",
                                     f"Two reports for closure {rep.closure}: {prev.path.name} and "
                                     f"{rep.path.name}; the second is ignored. Remove the outdated one.",
                                     source=rep.path.name))
            return
        self.reports[rep.closure] = rep
        for d in rep.devices:
            self.devices.setdefault((rep.closure, d.device_id), d)
        for s in rep.segments:
            self._add_segment(s)
        idx: dict[tuple, list[Connection]] = defaultdict(list)
        for c in rep.connections:
            idx[c.a.endpoint.key].append(c)
            if c.b.endpoint.key != c.a.endpoint.key:
                idx[c.b.endpoint.key].append(c)
        for key, conns in idx.items():
            if key[0] == "C" and len(conns) > 1 and rep.fmt != FMT_GUIDE:
                self.issues.append(Issue(
                    "WARNING", "FIBER_LISTED_TWICE",
                    f"{key[1]} Seg{key[2]} fibre {key[3]} appears in {len(conns)} rows of {rep.path.name} "
                    f"({', '.join(str(c.source.row) for c in conns)})",
                    cable=key[1], fiber=key[3], source=rep.path.name))
        self.conn_index[rep.closure] = idx

    def _add_segment(self, s: SegmentInfo):
        k = (s.cable, s.seg)
        cur = self.segments.get(k)
        if cur is None:
            cur = self.segments[k] = SegmentEnds(s.cable, s.seg)
        cur.sources.append(str(s.source))
        for attr in ("count", "start", "end", "placement"):
            new = getattr(s, attr)
            old = getattr(cur, attr)
            if new is None or (isinstance(new, Location) and not new.name):
                continue
            if old is None:
                setattr(cur, attr, new)
            elif old != new:
                self.issues.append(Issue("WARNING", "SEGMENT_CONFLICT",
                                         f"{s.cable} Seg{s.seg}: {attr} {old} vs {new} ({s.source})",
                                         cable=s.cable, source=str(s.source)))

    # ----------------------------------------------------------------- queries
    def connections_at(self, closure: str, key) -> list[Connection]:
        return self.conn_index.get(closure, {}).get(key, [])

    def find_hubs(self, olm: str) -> list[str]:
        """Closures with a segment that starts or ends at the OLM housing."""
        hubs = []
        for rep in self.reports.values():
            for s in rep.segments:
                for loc in (s.start, s.end):
                    if loc and loc.kind in self.olm_kinds and loc.name == olm:
                        if rep.closure not in hubs:
                            hubs.append(rep.closure)
        return hubs

    def olms(self) -> list[str]:
        found = []
        for rep in self.reports.values():
            for s in rep.segments:
                for loc in (s.start, s.end):
                    if loc and loc.kind in self.olm_kinds and loc.name not in found:
                        found.append(loc.name)
        return found

    # ----------------------------------------------------------------- tracing
    @staticmethod
    def arrival_step(seg: SegmentEnds, closure: str) -> int | None:
        """+1 when `closure` is the end of the segment (travelling with the segment numbering)."""
        if seg.end and seg.end.name == closure:
            return 1
        if seg.start and seg.start.name == closure:
            return -1
        return None

    def _records_of(self, cable: str, fiber: int) -> list[tuple[str, tuple, list[Connection]]]:
        """(closure, key, connections) of every report row on this cable and fibre number (any segment)."""
        if self._by_fiber is None:
            self._by_fiber = defaultdict(list)
            for name, idx in self.conn_index.items():
                for key, conns in idx.items():
                    if key[0] == "C":
                        self._by_fiber[(key[1], key[3])].append((name, key, conns))
        return self._by_fiber.get((cable, fiber), [])

    def _nearest_record(self, fiber: CableFiber, step: int, arriving_only: bool, exclude=frozenset()):
        best = None
        for name, key, conns in self._records_of(fiber.cable, fiber.fiber):
            if name in exclude:
                continue  # never jump back to a closure already on the path
            s2 = key[2]
            if (s2 - fiber.seg) * step <= 0:
                continue
            if arriving_only:
                seg2 = self.segments.get((fiber.cable, s2))
                arrive_end = (seg2.end if step == 1 else seg2.start) if seg2 else None
                if arrive_end is None or arrive_end.name != name:
                    continue  # record is where segment s2 leaves, not where it arrives
            d = abs(s2 - fiber.seg)
            if best is None or d < best[0]:
                best = (d, name, s2, conns[0])
        return best

    def circuit_relation(self, conn: Connection, origin: str | None) -> str | None:
        """How a downstream record's circuit relates to a live circuit that starts at `origin` (the hub):
        'same'    - a live record whose circuit start/end names the origin: the same fibre circuit, whatever
                    the usage text;
        'remnant' - both circuit ends are splice closures and neither is the origin: a cut piece of fibre
                    (Broken, Residential, ...) whose circuit ends mark where it was cut;
        None      - not decidable from the circuit fields (e.g. hand-made guides)."""
        if not origin:
            return None
        ends = [loc for loc in (conn.circuit_start, conn.circuit_end) if loc is not None and loc.name]
        dark = (conn.state or "") in self.cfg["labels"]["spare_states"]
        if any(loc.name == origin for loc in ends):
            return None if dark else "same"
        closure_kinds = set(self.cfg["network"]["closure_kinds"])
        if len(ends) == 2 and all(loc.kind in closure_kinds for loc in ends):
            return "remnant"
        return None

    def _bridge(self, fiber: CableFiber, step: int, expected_usage: str | None, exclude=frozenset(),
                origin: str | None = None):
        """The path reaches a closure without a report (or a segment whose far end is unknown).
        The fibre is taken to continue only when the next downstream report on the same cable
        lists the same fibre number carrying the same circuit: same circuit origin, or (when the
        circuit fields do not decide) the same usage text."""
        if not expected_usage or expected_usage == "No Desc":
            return None
        best = self._nearest_record(fiber, step, arriving_only=True, exclude=exclude)
        if best is None:
            return None
        dist, name, s2, conn = best
        rel = self.circuit_relation(conn, origin)
        if rel == "remnant" or (conn.state or "") in self.cfg["labels"].get("break_states", ["Broken"]):
            return None   # a cut piece: the live fibre left the cable before this closure
        if rel != "same" and compare_usage(conn.usage, expected_usage, self.usage_re) == "different":
            return None
        return {"closure": Location("Splice Case", name), "fiber": CableFiber(fiber.cable, s2, fiber.fiber),
                "from_seg": fiber.seg, "to_seg": s2}

    def cable_positions(self, cable: str) -> dict[str, int]:
        """Closure -> boundary index along a cable (closure at the end of SegK -> K)."""
        pos: dict[str, int] = {}
        for (cab, s), seg in self.segments.items():
            if cab != cable:
                continue
            if seg.start and seg.start.name:
                pos.setdefault(seg.start.name, s - 1)
            if seg.end and seg.end.name:
                pos.setdefault(seg.end.name, s)
        return pos

    def find_break_point(self, closure: str | None, fiber: CableFiber, step: int, exclude=frozenset(),
                         origin: str | None = None):
        """The live fibre stops being traceable at `closure` (no report, or unknown segment end).
        Look for the nearest downstream record of the same cable and fibre number. When that record
        is a remnant (state Broken, or a circuit between two closures that does not come from the
        origin), its circuit start/end names the closure where the fibre was cut.
        Returns (Location, Connection) or None."""
        best = self._nearest_record(fiber, step, arriving_only=False, exclude=exclude)
        if best is None:
            return None
        _, rec_closure, _, conn = best
        if (conn.state or "") not in self.cfg["labels"].get("break_states", ["Broken"]) and \
                self.circuit_relation(conn, origin) != "remnant":
            return None
        m = re.match(r"^(.+?) TO (.+?) FC\d+$", fiber.cable)
        far_name = (m.group(2) if step == 1 else m.group(1)) if m else None
        pos = self.cable_positions(fiber.cable)
        x_pos, r_pos = (pos.get(closure) if closure else None), pos.get(rec_closure)
        closure_kinds = set(self.cfg["network"]["closure_kinds"])
        good = []
        for loc in (conn.circuit_start, conn.circuit_end):
            if loc is None or loc.kind not in closure_kinds or not loc.name or loc.name == far_name:
                continue
            p = pos.get(loc.name)
            if p is not None and r_pos is not None:
                if x_pos is not None and (p - x_pos) * step < 0:
                    continue
                if (r_pos - p) * step < 0:
                    continue
            if loc.name in self.reports and loc.name != closure:
                continue  # a closure with a report would have been traced through
            good.append(loc)
        if len(good) == 1:
            return good[0], conn
        return None

    def trace(self, start_closure: str, start: CableFiber, expected_usage: str | None = None,
              max_steps: int = 500) -> TraceResult:
        self._aliases_scratch = []
        self._variants_scratch = []
        self._premise_scratch = []
        self._path = {start_closure}
        self._route = [start_closure]
        self._origin = start_closure
        result = self._trace(start_closure, start, expected_usage, max_steps)
        result.seg_aliases = list(self._aliases_scratch)
        result.usage_variants = list(self._variants_scratch)
        result.premise_variants = list(self._premise_scratch)
        result.path_closures = set(self._path)
        result.route = list(self._route)
        if result.stop == "missing_report" and result.stop_location is not None and \
                result.stop_location.name not in result.route:
            result.route.append(result.stop_location.name)
        return result

    def _passed(self, cable: str, from_seg: int, to_seg: int) -> list[str]:
        """Closures between segment from_seg and to_seg of a cable (bridged without reports)."""
        out = []
        step = 1 if to_seg > from_seg else -1
        for k in range(from_seg, to_seg, step):
            seg = self.segments.get((cable, k))
            loc = (seg.end if step == 1 else seg.start) if seg else None
            if loc is not None and loc.name and loc.name not in out:
                out.append(loc.name)
        return out

    def _segment_alias(self, fiber: CableFiber, from_closure: str, at_closure: str) -> CableFiber | None:
        """Same physical span listed under a different segment number in the two closure reports
        (report revisions out of sync). Matched by cable name and both end closures."""
        for (cab, s), seg in self.segments.items():
            if cab != fiber.cable or s == fiber.seg:
                continue
            ends = {seg.start.name if seg.start else None, seg.end.name if seg.end else None}
            if ends == {from_closure, at_closure}:
                cand = CableFiber(fiber.cable, s, fiber.fiber)
                if self.connections_at(at_closure, cand.key):
                    return cand
        return None

    def _trace(self, start_closure: str, start: CableFiber, expected_usage: str | None,
               max_steps: int) -> TraceResult:
        """Follow a fibre that leaves `start_closure` on segment `start` until it reaches a
        terminal enclosure, an OLM housing, a closure without a report, or a dead end."""
        steps = [TraceStep(start_closure, None, None)]
        closure, fiber = start_closure, start
        uses_guide = False
        conflicts: list[str] = []
        seg_aliases: list[str] = self._aliases_scratch
        visited = set()
        for _ in range(max_steps):
            seg = self.segments.get((fiber.cable, fiber.seg))
            if seg is None:
                return TraceResult(steps, "unknown_segment", None, closure, fiber, uses_guide, conflicts)
            far = seg.other_end(closure)
            if far is None or not far.name:
                # far end not recorded anywhere (e.g. only a hand-made guide lists this segment)
                leave = self.arrival_step(seg, closure)
                step = -leave if leave else None
                bridge = self._bridge(fiber, step, expected_usage, self._path, self._origin) if step else None
                if bridge is None:
                    r = TraceResult(steps, "unknown_segment", None, closure, fiber, uses_guide, conflicts)
                    r.step = step
                    return r
                steps.append(TraceStep(f"[{fiber.cable} Seg{bridge['from_seg']}->Seg{bridge['to_seg']}: far end "
                                       f"not recorded; same fibre, same circuit downstream]", None, None))
                self._route += self._passed(fiber.cable, bridge["from_seg"], bridge["to_seg"])
                far, fiber = bridge["closure"], bridge["fiber"]
            elif far.kind in self.terminal_kinds:
                return TraceResult(steps, "terminal", far, closure, fiber, uses_guide, conflicts)
            elif far.kind in self.olm_kinds:
                return TraceResult(steps, "olm", far, closure, fiber, uses_guide, conflicts)
            elif far.name not in self.reports:
                step = self.arrival_step(seg, far.name)
                bridge = self._bridge(fiber, step, expected_usage, self._path, self._origin) if step else None
                if bridge is None:
                    r = TraceResult(steps, "missing_report", far, closure, fiber, uses_guide, conflicts)
                    r.step = step
                    return r
                self._route += self._passed(fiber.cable, bridge["from_seg"], bridge["to_seg"])
                steps.append(TraceStep(
                    f"[{far.name}{' ...' if abs(bridge['to_seg'] - bridge['from_seg']) > 1 else ''}: no report; "
                    f"Seg{bridge['from_seg']}->Seg{bridge['to_seg']} same fibre, same circuit downstream]",
                    None, None))
                far, fiber = bridge["closure"], bridge["fiber"]
            conns = self.connections_at(far.name, fiber.key)
            if not conns:
                alias = self._segment_alias(fiber, closure, far.name)
                if alias is not None:
                    seg_aliases.append(f"{fiber.cable}: Seg{fiber.seg} in the {closure} report is Seg{alias.seg} "
                                       f"in the {far.name} report (same span {closure}-{far.name})")
                    fiber = alias
                    conns = self.connections_at(far.name, fiber.key)
            if not conns:
                steps.append(TraceStep(far.name, None, fiber))
                return TraceResult(steps, "not_listed", far, far.name, fiber, uses_guide, conflicts)
            conn = conns[0]
            if conn.fmt == FMT_GUIDE:
                uses_guide = True
            rel = self.circuit_relation(conn, self._origin) if expected_usage and conn.fmt != FMT_GUIDE else None
            if expected_usage and conn.usage and conn.fmt != FMT_GUIDE and conn.usage != expected_usage:
                kind = compare_usage(conn.usage, expected_usage, self.usage_re)
                if kind == "variant" or rel == "same":
                    # same circuit (same origin, or same tap port and house numbers): text differs between
                    # report revisions
                    self._variants_scratch.append(f"{far.name} ({conn.source}): {conn.usage!r}")
                    if kind not in ("variant", "address_only"):
                        self._premise_scratch.append(f"{far.name} ({conn.source}): {conn.usage!r}")
                else:
                    conflicts.append(f"{far.name} ({conn.source}): usage {conn.usage!r}")
            if rel == "remnant" and (conn.state or "") not in self.cfg["labels"]["spare_states"]:
                conflicts.append(f"{far.name} ({conn.source}): record is a cut piece ({conn.state!r}, circuit "
                                 f"{conn.circuit_start} - {conn.circuit_end}) on a live circuit")
            steps.append(TraceStep(far.name, conn, fiber))
            self._path.add(far.name)
            self._route.append(far.name)
            nxt = conn.other(fiber.key).endpoint
            if isinstance(nxt, DevicePort):
                return TraceResult(steps, "device", far, far.name, None, uses_guide, conflicts)
            state = (conn.state or "")
            if state in self.cfg["labels"]["spare_states"] and expected_usage:
                conflicts.append(f"{far.name} ({conn.source}): fibre state {state!r} on a live circuit")
            if (far.name, nxt.key) in visited:
                return TraceResult(steps, "loop", far, far.name, nxt, uses_guide, conflicts)
            visited.add((far.name, nxt.key))
            closure, fiber = far.name, nxt
        return TraceResult(steps, "loop", None, closure, fiber, uses_guide, conflicts)
