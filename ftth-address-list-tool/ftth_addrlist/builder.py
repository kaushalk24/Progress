"""Build address-list rows for one OLM from the connectivity network.

Every field carries a status, a rule code, a readable derivation and the source
rows it came from. Rule codes are documented in docs/FIELD_MAPPING.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .colors import ColorCode
from .model import (APPROVED, CONFIRMED, PROVISIONAL, UNRESOLVED, CableFiber, Connection, DevicePort,
                    FieldValue, Issue, OutputRow)
from .network import Network, SegmentEnds, TraceResult, compare_usage

FIELDS = ["pon_name", "pon_port", "fiber_no", "address", "tube_color", "fiber_color",
          "cable_name", "tap_name", "fiber_splice"]

FIELD_LABELS = {
    "pon_name": "PON NAME", "pon_port": "PON PORT", "fiber_no": "FIBER #", "address": "ADDRESS",
    "tube_color": "COLOR TUBE", "fiber_color": "COLOR FIBER", "cable_name": "CABLE NAME",
    "tap_name": "Fiber Tap Name", "fiber_splice": "Fiber Splice",
}


@dataclass
class OlmResult:
    olm: str
    hub: str | None
    rows: list[OutputRow] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    sections: list[tuple[str, int, int]] = field(default_factory=list)   # (cable, seg, count)

    @property
    def counts(self) -> dict[str, int]:
        out = {CONFIRMED: 0, APPROVED: 0, PROVISIONAL: 0, UNRESOLVED: 0}
        for r in self.rows:
            out[r.status] += 1
        return out

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "ERROR"]

    @property
    def is_final(self) -> bool:
        c = self.counts
        return bool(self.rows) and c[PROVISIONAL] == 0 and c[UNRESOLVED] == 0 and not self.errors


def _ws(text, cfg):
    if text is None:
        return None
    if cfg["address"].get("normalise_whitespace", True) and isinstance(text, str):
        return " ".join(text.split())
    return text


def seg_named_dest(cable: str) -> str | None:
    m = re.match(r"^.+? TO (.+?) FC\d+$", cable)
    return m.group(1) if m else None


class Builder:
    def __init__(self, net: Network, cfg: dict):
        self.net = net
        self.cfg = cfg
        self.colors = ColorCode(cfg)
        self.usage_re = re.compile(cfg["address"]["usage_regex"])
        self.addr_rewrites = [(re.compile(r["pattern"]), r["replace"]) for r in cfg["address"]["rewrites"]]
        self.usage_rewrites = [(re.compile(r["pattern"]), r["replace"]) for r in cfg["labels"]["usage_rewrites"]]
        self.spare_states = set(cfg["labels"]["spare_states"])
        self.terminal_kinds = set(cfg["network"]["terminal_kinds"])
        self.accepted_rules = set(cfg.get("approvals", {}).get("accepted_rules", []))

    # ------------------------------------------------------------------ helpers
    def _rewrite_usage(self, usage: str | None) -> str | None:
        if usage is None:
            return None
        for pat, rep in self.usage_rewrites:
            if pat.search(usage):
                return pat.sub(rep, usage)
        return usage

    def _rewrite_address(self, addr: str) -> tuple[str, list[str]]:
        applied = []
        for pat, rep in self.addr_rewrites:
            new = pat.sub(rep, addr)
            if new != addr:
                applied.append(f"rewrite {pat.pattern!r}")
                addr = new
        return addr, applied

    def _hub_cables(self, hub: str, olm: str) -> tuple[list[SegmentEnds], list[SegmentEnds]]:
        rep = self.net.reports[hub]
        feeder, dist, seen = [], [], set()
        for s in rep.segments:
            k = (s.cable, s.seg)
            if k in seen:
                continue
            seen.add(k)
            seg = self.net.segments[k]
            if not seg.touches(hub):
                continue
            other = seg.other_end(hub)
            if other and other.kind in self.cfg["network"]["olm_kinds"] and other.name == olm:
                feeder.append(seg)
            else:
                dist.append(seg)
        return feeder, dist

    # ------------------------------------------------------------------ main
    def build(self, olm: str) -> OlmResult:
        hubs = self.net.find_hubs(olm)
        res = OlmResult(olm, hubs[0] if hubs else None)
        if not hubs:
            res.issues.append(Issue("ERROR", "NO_HUB",
                                    f"No splice report has a segment to 'OLM Housing: {olm}'. Supply the hub "
                                    f"(splitter) closure report for {olm}.", olm=olm))
            return res
        if len(hubs) > 1:
            res.issues.append(Issue("ERROR", "MULTIPLE_HUBS",
                                    f"{olm} connects to several closures {hubs}; only {hubs[0]} is used", olm=olm))
        hub = hubs[0]
        if not any(h == hub for h, _ in self.net.devices):
            res.issues.append(Issue("ERROR", "NO_SPLITTERS", f"Hub {hub} report lists no splitters; PON names "
                                    f"and ports cannot be derived", olm=olm, source=self.net.reports[hub].path.name))
        feeder, dist = self._hub_cables(hub, olm)
        rows_by_seg: dict[tuple, list[OutputRow]] = {}
        for seg in feeder + dist:
            rows_by_seg[(seg.cable, seg.seg)] = self._section_rows(olm, hub, seg)

        def first_port(seg):
            ports = [(r.value("_pon_sort"), r.value("pon_port")) for r in rows_by_seg[(seg.cable, seg.seg)]
                     if r.value("pon_port") is not None]
            return min(ports) if ports else (float("inf"), float("inf"))

        order = list(feeder) if self.cfg["network"].get("include_feeder", True) else []
        if self.cfg["network"].get("section_order") == "first_pon_port":
            order += sorted(dist, key=lambda s: (first_port(s), dist.index(s)))
        else:
            order += dist
        for n, seg in enumerate(order, 1):
            for r in rows_by_seg[(seg.cable, seg.seg)]:
                r.section = n
                r.fields.pop("_pon_sort", None)
                res.rows.append(r)
            res.sections.append((seg.cable, seg.seg, seg.count or 0))
        if not feeder:
            res.issues.append(Issue("WARNING", "NO_FEEDER", f"No feeder cable from {olm} found in {hub}", olm=olm))
        self._post_checks(res, hub)
        self._apply_rule_policy(res)
        for r in res.rows:
            res.issues.extend(r.issues)
        return res

    def _apply_rule_policy(self, res: OlmResult):
        if not self.accepted_rules:
            return
        for r in res.rows:
            for fv in r.fields.values():
                if fv.status == PROVISIONAL and fv.code in self.accepted_rules:
                    fv.status = APPROVED
                    fv.note = (fv.note + "; " if fv.note else "") + f"rule {fv.code} accepted by approvals policy"

    def _same_premise(self, a: str | None, b: str | None) -> bool:
        ma, mb = self.usage_re.match(a or ""), self.usage_re.match(b or "")
        if not ma or not mb:
            return False
        norm = lambda t: " ".join(t.split()).upper()
        num = lambda t: (re.match(r"^\D*?(\d+)", t) or [None, None])[1]
        return norm(ma.group("address")) == norm(mb.group("address")) or \
            (num(ma.group("address")) is not None and num(ma.group("address")) == num(mb.group("address")))

    # ------------------------------------------------------------------ rows
    def _section_rows(self, olm: str, hub: str, seg: SegmentEnds) -> list[OutputRow]:
        count = seg.count
        if not count:
            fibers = sorted({k[3] for k in self.net.conn_index.get(hub, {})
                             if k[0] == "C" and k[1] == seg.cable and k[2] == seg.seg})
            count = max(fibers) if fibers else 0
        return [self._row(olm, hub, seg, f) for f in range(1, count + 1)]

    def _row(self, olm: str, hub: str, seg: SegmentEnds, f: int) -> OutputRow:
        cfg = self.cfg
        key = ("C", seg.cable, seg.seg, f)
        conns = self.net.connections_at(hub, key)
        F: dict[str, FieldValue] = {}
        row = OutputRow(olm, 0, seg.cable, f, F)
        hub_src = self.net.reports[hub].path.name
        F["fiber_no"] = FieldValue(f, CONFIRMED, "fibre position in the hub cable", [hub_src], code="FIB-NO")
        F["cable_name"] = FieldValue(seg.cable, CONFIRMED, "cable name from hub segment table",
                                     seg.sources[:1], code="CABLE")
        for k in ("pon_name", "pon_port", "tap_name", "fiber_splice"):
            F[k] = FieldValue(None, CONFIRMED, "not applicable to this fibre", code="N/A")

        if not conns:
            # The hub report lists every splice made in the hub; a fibre with no row is not spliced there.
            st = CONFIRMED if cfg["labels"].get("unlisted_hub_fibre_is_spare", True) else PROVISIONAL
            F["address"] = FieldValue(cfg["labels"]["spare"], st, "no splice recorded for this fibre in the hub report",
                                      [hub_src], code="ADDR-SPARE")
            self._colors(F, None, f, hub_src, row, unspliced=True)
            row.kind = "spare"
            return row

        conn = conns[0]
        ev = str(conn.source)
        other = conn.other(key).endpoint
        self._colors(F, conn.side_for(key), f, ev, row)
        state = conn.state or ""

        if isinstance(other, DevicePort):
            dev = self.net.devices.get((hub, other.device))
            if dev is None or dev.index is None:
                row.kind = "other"
                F["address"] = FieldValue(self._rewrite_usage(conn.usage), UNRESOLVED, "unknown equipment",
                                          [ev], f"connected to {other}, not a recognised splitter", code="ADDR-EQUIP")
                row.issues.append(Issue("ERROR", "UNKNOWN_EQUIPMENT", f"{seg.cable} fibre {f} connects to "
                                        f"{other.device} (not a splitter)", olm, seg.cable, f, ev))
                return row
            if other.port == cfg["network"]["splitter_common_port"]:
                row.kind = "splitter_common"
                F["address"] = FieldValue(cfg["labels"]["splitter_common"].format(ratio=dev.ratio, index=dev.index),
                                          CONFIRMED, "fibre feeds the splitter common (input) port",
                                          [ev, str(dev.source)], code="ADDR-SPLITTER-COM")
                F["fiber_splice"] = FieldValue(hub, CONFIRMED, "fibre ends in the hub", [ev], code="FS-HUB")
                return row
            F["pon_name"] = FieldValue(cfg["network"]["pon_name_format"].format(index=dev.index, olm=olm,
                                                                                ratio=dev.ratio),
                                       CONFIRMED, f"index of splitter {dev.label}", [ev, str(dev.source)],
                                       code="PON-NAME")
            F["_pon_sort"] = FieldValue(dev.index)
            off = cfg["network"]["pon_port_offset"]
            F["pon_port"] = FieldValue(other.port - off, CONFIRMED, f"splitter port {other.port} minus {off}",
                                       [ev], code="PON-PORT")
            if dev.count and other.port > dev.count:
                F["pon_port"].status = UNRESOLVED
                F["pon_port"].note = f"port {other.port} exceeds splitter size {dev.count}"
            self._subscriber(row, F, hub, seg, f, conn, ev)
            return row

        # cable-to-cable at the hub: transport / through fibres, or spare
        if state in self.spare_states:
            row.kind = "spare"
            F["address"] = FieldValue(cfg["labels"]["spare"], CONFIRMED, f"hub record state {state!r}", [ev],
                                      code="ADDR-SPARE")
            return row
        row.kind = "transport"
        F["address"] = FieldValue(self._rewrite_usage(conn.usage), CONFIRMED, "circuit usage text of the hub record",
                                  [ev], code="ADDR-LABEL")
        if not conn.usage or conn.usage == "No Desc":
            F["address"].status = UNRESOLVED
            F["address"].note = f"through fibre to {other} has no usage description"
        if cfg["fiber_splice"]["hub_value_for_hub_fibres"]:
            F["fiber_splice"] = FieldValue(hub, CONFIRMED, "fibre spliced in the hub", [ev], code="FS-HUB")
        return row

    def _colors(self, F, side, fiber_no, ev, row: OutputRow, unspliced=False):
        exp = dict(zip(("tube_color", "fiber_color"), self.colors.expected(fiber_no)))
        for key in ("tube_color", "fiber_color"):
            rep_color = (side.tube_color if key == "tube_color" else side.fiber_color) if side else None
            expected = exp[key]
            if rep_color:
                ab = self.colors.to_abbr(rep_color)
                if ab is None:
                    F[key] = FieldValue(rep_color, UNRESOLVED, "colour name not in colour table", [ev],
                                        code="COL-UNKNOWN")
                    continue
                F[key] = FieldValue(ab, CONFIRMED, "colour from splice report", [ev], code="COL-REPORT")
                if rep_color != expected:
                    F[key].status, F[key].code = PROVISIONAL, "COL-MISMATCH"
                    F[key].note = f"report colour {rep_color} differs from colour-code position ({expected})"
                    row.issues.append(Issue("WARNING", "COLOR_MISMATCH", f"{row.cable} fibre {row.fiber}: {key} "
                                            f"{rep_color} vs expected {expected}", row.olm, row.cable, row.fiber, ev))
            else:
                F[key] = FieldValue(self.colors.to_abbr(expected), CONFIRMED if unspliced else PROVISIONAL,
                                    "colour from fibre number (colour-code sequence)", [ev], code="COL-STANDARD")

    def _subscriber(self, row: OutputRow, F, hub, seg: SegmentEnds, f: int, conn: Connection, ev: str):
        cfg = self.cfg
        m = self.usage_re.match(conn.usage or "")
        circuit_term = None
        for loc in (conn.circuit_start, conn.circuit_end):
            if loc and loc.kind in self.terminal_kinds:
                circuit_term = loc
        tr: TraceResult = self.net.trace(hub, CableFiber(seg.cable, seg.seg, f), expected_usage=conn.usage)
        row.trace = [tr.path_text()]
        trace_term = tr.stop_location if tr.stop == "terminal" else None
        trace_ev = [str(s.conn.source) for s in tr.steps if s.conn is not None]

        # --- address and tap --------------------------------------------------------------
        # Tap evidence ranking: enclosure reached by the fibre trace > circuit start/end enclosure
        # named by the spatial system > tap prefix of the usage text.
        tap_sources = []
        if trace_term is not None:
            tap_sources.append(("trace", trace_term.name, "TAP-TRACE"))
        if circuit_term is not None:
            tap_sources.append(("circuit", circuit_term.name, "TAP-CIRCUIT"))
        if m:
            row.kind = "subscriber"
            addr, applied = self._rewrite_address(_ws(m.group("address"), cfg))
            F["address"] = FieldValue(addr, CONFIRMED, "usage text after '<tap>:<port> '" +
                                      (f" ({', '.join(applied)})" if applied else ""), [ev], code="ADDR-USAGE")
            tap_sources.append(("usage", _ws(m.group("tap"), cfg), "TAP-USAGE"))
            tap_prefix = re.match(r"^\D*", m.group("tap")).group(0)
            if len(tap_prefix) >= 3 and addr.startswith(tap_prefix):
                F["address"].status, F["address"].code = PROVISIONAL, "ADDR-SUSPECT"
                F["address"].note = "address part of the usage text looks like a tap identifier"
                row.issues.append(Issue("WARNING", "ADDRESS_SUSPECT", f"{seg.cable} fibre {f}: usage {conn.usage!r} "
                                        f"has a tap identifier where the address should be", row.olm, seg.cable, f, ev))
        else:
            label = self._rewrite_usage(conn.usage)
            row.kind = "power" if label != conn.usage else "other"
            F["address"] = FieldValue(label, CONFIRMED, "circuit usage text (non-subscriber)", [ev], code="ADDR-LABEL")
            if row.kind == "other":
                F["address"].status, F["address"].code = PROVISIONAL, "ADDR-NONSTANDARD"
                F["address"].note = "PON-port usage text is not in '<tap>:<port> <address>' form"
                row.issues.append(Issue("WARNING", "USAGE_NONSTANDARD", f"{seg.cable} fibre {f}: PON-port usage "
                                        f"{conn.usage!r} is not '<tap>:<port> <address>'", row.olm, seg.cable, f, ev))
            if not conn.usage or conn.usage == "No Desc":
                F["address"] = FieldValue(None, UNRESOLVED, "PON port in use but no usage/address recorded", [ev],
                                          code="ADDR-MISSING")
                row.issues.append(Issue("ERROR", "PON_WITHOUT_ADDRESS", f"{seg.cable} fibre {f}: PON port in use "
                                        f"but no usage/address recorded", row.olm, seg.cable, f, ev))
        if tap_sources:
            src, tap, code = tap_sources[0]
            names = {"trace": "terminal enclosure reached by the fibre trace",
                     "circuit": "circuit start/end enclosure", "usage": "usage text before ':'"}
            F["tap_name"] = FieldValue(tap, CONFIRMED, names[src], [ev], code=code)
            agree = [s for s, v, _ in tap_sources[1:] if v == tap]
            disagree = [(s, v) for s, v, _ in tap_sources[1:] if v != tap]
            if agree:
                F["tap_name"].rule += f" (agrees with {', '.join(agree)})"
            if disagree:
                F["tap_name"].status, F["tap_name"].code = PROVISIONAL, "TAP-CONFLICT"
                F["tap_name"].note = "source conflict: " + "; ".join(f"{s} says {v!r}" for s, v in disagree)
                row.issues.append(Issue("WARNING", "TAP_CONFLICT", f"{seg.cable} fibre {f}: tap {tap!r} from {src}, "
                                        "but " + "; ".join(f"{s} says {v!r}" for s, v in disagree),
                                        row.olm, seg.cable, f, ev))
        else:
            F["tap_name"] = FieldValue(None, UNRESOLVED, "no tap in usage text and no terminal enclosure found",
                                       [ev], code="TAP-NONE")

        F["fiber_splice"] = self._fiber_splice(row, seg, f, tr, ev, trace_ev)
        if tr.stop in ("missing_report", "unknown_segment") and tr.last_fiber is not None and tr.step:
            nxt = self.net._nearest_record(tr.last_fiber, tr.step, arriving_only=False, exclude=tr.path_closures)
            if nxt is not None:
                ncon = nxt[3]
                live = (ncon.state or "") not in self.spare_states and ncon.usage not in (None, "No Desc")
                # A cut fibre's remnant may be reused for another premise further on (normal). It is only
                # suspicious when the downstream circuit names the same premise differently.
                if live and compare_usage(ncon.usage, conn.usage, self.usage_re) == "different" and \
                        self._same_premise(ncon.usage, conn.usage):
                    msg = (f"next downstream record of the same fibre ({ncon.source}) carries a different circuit "
                           f"{ncon.usage!r}")
                    for k in ("tap_name", "address"):
                        if F[k].status == CONFIRMED:
                            F[k].status = PROVISIONAL
                        F[k].note = (F[k].note + "; " if F[k].note else "") + msg
                    row.issues.append(Issue("WARNING", "DOWNSTREAM_CIRCUIT_DIFFERS", f"{seg.cable} fibre {f}: hub usage "
                                            f"{conn.usage!r} but {msg} - check report revisions", row.olm, seg.cable,
                                            f, ev))

    def _fiber_splice(self, row, seg, f, tr: TraceResult, ev, trace_ev) -> FieldValue:
        cfg = self.cfg
        fs = FieldValue(None, UNRESOLVED, "", [ev] + trace_ev, code="FS-UNKNOWN")
        if tr.stop == "terminal":
            fs.value, fs.status, fs.code = tr.last_closure, CONFIRMED, "FS-TRACE-TERMINAL"
            fs.rule = "fibre trace reaches the pigtail/drop to the terminal enclosure in this closure"
        elif tr.stop in ("missing_report", "unknown_segment") and tr.last_fiber is not None and tr.step:
            x = tr.stop_location.name if tr.stop_location is not None else None
            brk = self.net.find_break_point(x, tr.last_fiber, tr.step, tr.path_closures)
            dest = seg_named_dest(tr.last_fiber.cable)
            where = (f"arriving at {x} (no report)" if x else
                     f"leaving {tr.last_closure} (far end of the segment not recorded)")
            if brk is not None:
                loc, bconn = brk
                fs.value, fs.status, fs.code = loc.name, PROVISIONAL, "FS-BREAK-POINT"
                fs.rule = (f"remnant of the fibre beyond {loc.name} is recorded '{bconn.state}' "
                           f"({bconn.source}): the fibre leaves cable {tr.last_fiber.cable} at {loc.name}")
                fs.note = (f"splice report for {loc.name} not supplied - splice to the tap not seen "
                           f"(fibre could continue on a branch cable)")
                fs.evidence.append(str(bconn.source))
                row.needs_reports.append(loc.name)
            elif x is not None and dest == x:
                fs.value, fs.code = x, "FS-CABLE-END"
                fs.status = PROVISIONAL
                fs.rule = f"fibre reaches the end of cable {tr.last_fiber.cable} at {x}"
                fs.note = f"splice report for {x} not supplied - splice to the tap not seen"
                row.needs_reports.append(x)
                if cfg["fiber_splice"]["missing_report_policy"] == "unresolved":
                    fs.value, fs.status = None, UNRESOLVED
            else:
                fs.rule = "fibre continues past a closure without a report"
                fs.note = (f"last seen on {tr.last_fiber} {where}; candidate closures "
                           f"{x or tr.last_closure} ... {dest or 'cable end'}; supply those splice reports")
                row.needs_reports.append(x or f"(next closure after {tr.last_closure} on {tr.last_fiber.cable})")
                row.issues.append(Issue("WARNING", "SPLICE_CLOSURE_UNKNOWN", f"{seg.cable} fibre {f} "
                                        f"({row.value('address')}): {fs.note}", row.olm, seg.cable, f, ev))
        elif tr.stop == "not_listed":
            fs.code = "FS-TRACE-BROKEN"
            fs.rule = "live fibre is not listed in a closure report on its path"
            fs.note = f"fibre {tr.last_fiber} not listed in {tr.last_closure} report"
            row.issues.append(Issue("ERROR", "TRACE_BROKEN", f"{seg.cable} fibre {f}: {fs.note}",
                                    row.olm, seg.cable, f, ev))
        else:
            fs.rule = f"trace stopped ({tr.stop}) at {tr.last_closure}"
            row.issues.append(Issue("ERROR", "TRACE_STOPPED", f"{seg.cable} fibre {f}: {fs.rule}",
                                    row.olm, seg.cable, f, ev))
        if tr.usage_variants:
            if fs.status == CONFIRMED:
                fs.status, fs.code = PROVISIONAL, "FS-USAGE-VARIANT"
            fs.note = (fs.note + "; " if fs.note else "") + "usage text differs between report revisions: " + \
                "; ".join(tr.usage_variants[:2])
            row.issues.append(Issue("WARNING", "USAGE_TEXT_VARIANT", f"{seg.cable} fibre {f}: hub usage "
                                    f"{row.value('address')!r} but downstream " + "; ".join(tr.usage_variants[:2]),
                                    row.olm, seg.cable, f, ev))
        if tr.seg_aliases:
            if fs.status == CONFIRMED:
                fs.status, fs.code = PROVISIONAL, "FS-SEG-ALIAS"
            fs.note = (fs.note + "; " if fs.note else "") + "segment numbering differs between reports: " + \
                "; ".join(tr.seg_aliases[:2])
            row.issues.append(Issue("WARNING", "SEGMENT_NUMBER_MISMATCH", f"{seg.cable} fibre {f}: " +
                                    "; ".join(tr.seg_aliases[:2]) + " - report revisions out of sync",
                                    row.olm, seg.cable, f, ev))
        if tr.uses_guide:
            if fs.status == CONFIRMED:
                fs.status = PROVISIONAL
                fs.code = "FS-GUIDE"
            fs.note = (fs.note + "; " if fs.note else "") + "path uses a hand-made splice guide (colour-derived fibres)"
        if tr.usage_conflicts:
            fs.status, fs.code = UNRESOLVED, "FS-CIRCUIT-CONFLICT"
            fs.note = (fs.note + "; " if fs.note else "") + "downstream usage differs: " + "; ".join(tr.usage_conflicts[:3])
            row.issues.append(Issue("ERROR", "CIRCUIT_CONFLICT", f"{seg.cable} fibre {f}: downstream records disagree "
                                    f"with hub usage ({'; '.join(tr.usage_conflicts[:3])})", row.olm, seg.cable, f, ev))
        return fs

    # ------------------------------------------------------------------ checks
    def _post_checks(self, res: OlmResult, hub: str):
        seen_port: dict[tuple, OutputRow] = {}
        seen_addr: dict[str, list[OutputRow]] = {}
        for r in res.rows:
            pp = (r.value("pon_name"), r.value("pon_port"))
            if pp[1] is not None:
                if pp in seen_port:
                    prev = seen_port[pp]
                    res.issues.append(Issue("ERROR", "PON_PORT_REUSED", f"PON {pp[0]} port {pp[1]} on {prev.cable} "
                                            f"f{prev.fiber} and {r.cable} f{r.fiber}", res.olm, r.cable, r.fiber))
                    r.fields["pon_port"].status = UNRESOLVED
                seen_port[pp] = r
            if r.kind == "subscriber" and r.value("address"):
                seen_addr.setdefault(r.value("address"), []).append(r)
        for addr, rs in seen_addr.items():
            if len(rs) > 1:
                where = ", ".join(f"{x.cable} f{x.fiber}" for x in rs)
                res.issues.append(Issue("WARNING", "DUPLICATE_ADDRESS",
                                        f"Address {addr!r} is served by {len(rs)} fibres: {where}", res.olm))
                for x in rs:
                    fv = x.fields["address"]
                    if fv.status == CONFIRMED:
                        fv.status, fv.code = PROVISIONAL, "ADDR-DUPLICATE"
                    fv.note = (fv.note + "; " if fv.note else "") + f"same address on {len(rs)} fibres ({where})"
        # splitter outputs present in the hub report but not represented in any section
        used = {(r.cable, r.fiber) for r in res.rows}
        common = self.cfg["network"]["splitter_common_port"]
        for key, conns in self.net.conn_index.get(hub, {}).items():
            if key[0] != "D" or key[2] == common or not self.net.devices.get((hub, key[1])):
                continue
            dev = self.net.devices[(hub, key[1])]
            for c in conns:
                o = c.other(key).endpoint
                if isinstance(o, CableFiber) and (o.cable, o.fiber) not in used:
                    res.issues.append(Issue("WARNING", "PON_PORT_NOT_LISTED", f"{dev.label} port {key[2]} feeds {o}, "
                                            f"which is not in any address-list section", res.olm, o.cable, o.fiber,
                                            str(c.source)))
        off = self.cfg["network"]["pon_port_offset"]
        for (h, _), dev in self.net.devices.items():
            if h != hub or not dev.count or dev.index is None:
                continue
            used_ports = {k[2] for k in self.net.conn_index.get(hub, {}) if k[0] == "D" and k[1] == dev.device_id}
            free = [p - off for p in range(common + 1, dev.count + 1) if p not in used_ports]
            if free:
                res.issues.append(Issue("INFO", "PON_PORTS_FREE", f"{dev.label}: {len(free)} unused output port(s): "
                                        f"{_ranges(free)}", res.olm, source=str(dev.source)))


def _ranges(nums: list[int]) -> str:
    out, start, prev = [], None, None
    for n in sorted(nums):
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            out.append(f"{start}-{prev}" if start != prev else str(start))
            start = prev = n
    if start is not None:
        out.append(f"{start}-{prev}" if start != prev else str(start))
    return ", ".join(out)
