"""Fiber Splice from the design drawing where the splice reports stop before the tap splice (FS-DRAWING).

When a fibre trace reaches a closure whose report was not supplied, the reports cannot say in which
downstream closure the fibre meets the tap. The drawing can narrow it down with evidence:

1. Reachable closures: the fibre is still on the cable at the trace stop, so its tap splice is in a
   closure reachable from there along drawn cables without passing a closure that has a report
   (that report would have shown the fibre).
2. Candidate closures: of those, the closures whose tap enclosure is joined to them by a drawn
   pigtail, and that are not already the confirmed splice closure of another tap.
3. Fit of each candidate to the tap: the drop symbol drawn on the line between the premise and the
   candidate's enclosure (position, offset, rotation pointing to the premise); a value already
   derived from the reports (FS-CABLE-END / FS-BREAK-POINT / FS-TAP-CABLE) is preferred.
4. All taps that compete for the same closures are assigned together (one tap per closure), keeping
   the fibre-order convention of the network: measured from the traced rows of the run, lower fibre
   numbers are spliced farther along a route (or as configured).

The result is PROVISIONAL with its evidence (closure, pigtail, drop symbol, competing candidates) and
the closure report that would confirm it. The ranking numbers only choose between candidates; they
are not reported as a confidence. A value derived from the reports is kept when the drawing agrees
(noted as corroborated) or disagrees (DRAWING_DISAGREES warning). It is replaced only when its closure
has no tap enclosure in the drawing: the fibre must then continue on a branch cable beyond it.
"""

from __future__ import annotations

import collections
import itertools
import math
import re
from dataclasses import dataclass, field

from .model import APPROVED, PROVISIONAL, FieldValue, Issue, OutputRow

REPORT_DERIVED = ("FS-CABLE-END", "FS-BREAK-POINT", "FS-TAP-CABLE")


@dataclass
class Demand:
    olm: str
    tap: str
    rows: list[OutputRow] = field(default_factory=list)
    starts: set[str] = field(default_factory=set)
    x0: str | None = None                 # closure where the trace stopped (route position origin)
    entry: tuple[str, int] | None = None  # (cable, fibre number) the fibre was last seen on
    prior: str | None = None              # closure derived from the reports, if any
    passed: set[str] = field(default_factory=set)   # closures the fibre is known to pass (trace route)
    premises: list[tuple[float, float]] = field(default_factory=list)
    candidates: dict[str, tuple[float, str, tuple | None]] = field(default_factory=dict)  # closure -> (cost, kind, drop)


# ------------------------------------------------------------------------------- assignment
def hungarian(cost: list[list[float]]) -> list[int]:
    """Minimum-cost assignment of n rows to m >= n columns; returns the column of each row."""
    n = len(cost)
    m = len(cost[0]) if n else 0
    inf = math.inf
    u, v = [0.0] * (n + 1), [0.0] * (m + 1)
    p, way = [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        p[0], j0 = i, 0
        minv, used = [inf] * (m + 1), [False] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], inf, 0
            for j in range(1, m + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j], way[j] = cur, j0
                    if minv[j] < delta:
                        delta, j1 = minv[j], j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    out = [0] * n
    for j in range(1, m + 1):
        if p[j]:
            out[p[j] - 1] = j - 1
    return out


def assign(demands: list, closures: list, cost: dict, unassigned: float, penalty, weight: float) -> dict:
    """Assign each demand one closure (or none), each closure to at most one demand, minimising
    sum(cost) + weight * penalty(assignment). Exact for the cost part (Hungarian method), then
    pairwise swaps / moves while they lower the total."""
    big = 1e9
    cols = list(closures) + [None] * len(demands)
    matrix = [[(cost.get((d, c), big) if c is not None else (unassigned if k == len(closures) + i else big))
               for k, c in enumerate(cols)] for i, d in enumerate(demands)]
    sol = hungarian(matrix)
    asg = {d: cols[sol[i]] for i, d in enumerate(demands)}
    for d in demands:
        if asg[d] is not None and (d, asg[d]) not in cost:
            asg[d] = None
    if not weight:
        return asg

    def total(a):
        return sum(cost[(d, c)] if c is not None else unassigned for d, c in a.items()) + weight * penalty(a)
    best, improved = total(asg), True
    while improved:
        improved = False
        for i, d1 in enumerate(demands):
            for d2 in demands[i + 1:]:
                c1, c2 = asg[d1], asg[d2]
                if (c2 is None or (d1, c2) in cost) and (c1 is None or (d2, c1) in cost):
                    trial = dict(asg)
                    trial[d1], trial[d2] = c2, c1
                    val = total(trial)
                    if val < best - 1e-9:
                        asg, best, improved = trial, val, True
            used = set(asg.values())
            for c in closures:
                if c not in used and (d1, c) in cost:
                    trial = dict(asg)
                    trial[d1] = c
                    val = total(trial)
                    if val < best - 1e-9:
                        asg, best, improved = trial, val, True
                        used = set(asg.values())
    return asg


# ------------------------------------------------------------------------------- fibre order
def _known_value(r: OutputRow) -> str | None:
    fs = r.fields["fiber_splice"]
    if not fs.value or not r.trace_end:
        return None
    if r.trace_end["stop"] == "terminal" or fs.code in REPORT_DERIVED:
        return fs.value
    return None


def learn_fiber_order(results) -> tuple[str, int, int]:
    """Count, over pairs of traced rows on the same hub cable whose routes share a path and end in
    different closures, whether the lower fibre ends farther along. Returns (direction, farther, nearer)."""
    farther = nearer = 0
    for res in results:
        by_cable = collections.defaultdict(list)
        for r in res.rows:
            v = _known_value(r)
            if r.kind in ("subscriber", "power") and v and r.route:
                path = r.route[:r.route.index(v) + 1] if v in r.route else r.route + [v]
                by_cable[r.cable].append((r.fiber, r.value("tap_name"), path))
        for items in by_cable.values():
            for (fa, ta, pa), (fb, tb, pb) in itertools.combinations(sorted(items, key=lambda t: t[0]), 2):
                if ta == tb or pa[-1] == pb[-1] or fa == fb:
                    continue
                if pb[:len(pa)] == pa:      # b continues past a's closure: lower fibre (a) nearer
                    nearer += 1
                elif pa[:len(pb)] == pb:
                    farther += 1
    n = farther + nearer
    if n >= 10 and farther >= 0.9 * n:
        return "lower_farther", farther, nearer
    if n >= 10 and nearer >= 0.9 * n:
        return "lower_nearer", farther, nearer
    return "none", farther, nearer


# ------------------------------------------------------------------------------- resolver
def resolve_from_drawing(results, net, design, cfg) -> list[Issue]:
    """Fill / corroborate Fiber Splice of the OLM results from the design model. Returns run-level issues."""
    d = cfg["drawing"]
    have = set(net.reports)
    tap_re = re.compile(d["tap_address_regex"])
    accepted = set(cfg.get("approvals", {}).get("accepted_rules", []))

    claimed: dict[str, str] = {}
    demands: dict[tuple, Demand] = {}
    for res in results:
        for r in res.rows:
            tap = r.value("tap_name")
            if r.kind not in ("subscriber", "power") or not tap or not r.trace_end:
                continue
            fs = r.fields["fiber_splice"]
            te = r.trace_end
            if (te["stop"] == "terminal" or fs.code == "FS-TAP-CABLE") and fs.value:
                claimed.setdefault(fs.value, tap)
                continue
            if fs.code == "FS-UNKNOWN" or fs.code in ("FS-CABLE-END", "FS-BREAK-POINT") or \
                    (fs.status in (PROVISIONAL, APPROVED) and fs.value and te["stop"] != "terminal"):
                at = te["at"] or te["last_closure"]
                dm = demands.setdefault((res.olm, tap, at), Demand(res.olm, tap))
                dm.rows.append(r)
                dm.x0 = at
                dm.passed |= set(r.route)
                if te["cable"] is not None:
                    dm.entry = (te["cable"], te["fiber"])
                if fs.value:
                    dm.prior = dm.prior or fs.value
    for dm in demands.values():
        # search from the report-derived closure when there is one (the fibre passed the trace stop to
        # reach a break point), else from the trace stop; never back along the traced route
        dm.starts = {dm.prior} if dm.prior else {dm.x0}
        dm.passed -= dm.starts

    if not demands:
        return []
    direction = d.get("fiber_order", "learn")
    learned = None
    if direction == "learn":
        direction, far, near = learn_fiber_order(results)
        learned = (far, near)

    # candidates and their fit
    for dm in demands.values():
        for r in dm.rows:
            dm.premises += [p["xy"] for p in design.address_points(str(r.value("address") or ""))]
        m = tap_re.match(dm.tap)
        if m:
            dm.premises += [p["xy"] for p in design.address_points(m.group("address"))]
        reach = design.region(dm.starts, have | dm.passed)
        for c in reach:
            enc = design.enclosure_of.get(c)
            if enc is None or claimed.get(c, dm.tap) != dm.tap:
                continue
            if c in have and c != dm.prior:
                continue   # the fibre left this closure on a cable (its report shows it); not the tap splice
            fits = [x for x in (design.drop_support(a, enc["xy"]) for a in dm.premises) if x is not None]
            if fits:
                cost, kind, drop = min(fits)[0], "drop", min(fits)[1]
            elif dm.premises:
                cost = d["no_drop_base"] + min(math.dist(a, enc["xy"]) for a in dm.premises) / 20
                kind, drop = "premise", None
            else:
                cost, kind, drop = d["no_premise_cost"], "none", None
            if dm.prior == c:
                cost -= d["report_value_bonus"]
            dm.candidates[c] = (cost, kind, drop)

    # components of demands competing for closures
    keys = [k for k, dm in demands.items() if dm.candidates]
    owner = collections.defaultdict(set)
    for k in keys:
        for c in demands[k].candidates:
            owner[c].add(k)
    seen, assigned = set(), {}
    pos_cache: dict[str, dict] = {}

    def pos(dm: Demand, c: str):
        if dm.x0 not in pos_cache:
            pos_cache[dm.x0] = design.path_lengths(dm.x0, have)
        return pos_cache[dm.x0].get(c)

    for k0 in keys:
        if k0 in seen:
            continue
        comp, stack = [], [k0]
        while stack:
            k = stack.pop()
            if k in seen:
                continue
            seen.add(k)
            comp.append(k)
            for c in demands[k].candidates:
                stack += [x for x in owner[c] if x not in seen]
        comp.sort()
        closures = sorted({c for k in comp for c in demands[k].candidates})
        cost = {(k, c): v[0] for k in comp for c, v in demands[k].candidates.items()}

        def penalty(a, comp=comp):
            fwd = back = 0
            for k1, k2 in itertools.combinations(comp, 2):
                d1, d2 = demands[k1], demands[k2]
                c1, c2 = a[k1], a[k2]
                if not (d1.entry and d2.entry and c1 and c2) or d1.entry[0] != d2.entry[0] or \
                        d1.entry[1] == d2.entry[1]:
                    continue
                p1, p2 = pos(d1, c1), pos(d1, c2)
                if p1 is None or p2 is None or p1 == p2:
                    continue
                s = (d1.entry[1] - d2.entry[1]) * (p1 - p2)
                if s > 0:
                    back += 1        # higher fibre farther along
                elif s < 0:
                    fwd += 1         # lower fibre farther along
            if direction == "lower_farther":
                return back
            if direction == "lower_nearer":
                return fwd
            return min(fwd, back)
        assigned.update(assign(comp, closures, cost, d["unassigned_cost"], penalty, d["order_weight"]))

    # apply
    n_new = n_agree = n_disagree = n_none = n_branch = 0
    for key, dm in demands.items():
        c = assigned.get(key)
        res_issues = next(res.issues for res in results if res.olm == dm.olm)
        for r in dm.rows:
            fs = r.fields["fiber_splice"]
            ev_base = [f"drawing {design.source}"]
            if c is None:
                if fs.code == "FS-UNKNOWN":
                    n_none += 1
                    why = ("no tap enclosure joined by a pigtail is reachable from "
                           f"{dm.x0} without passing a closure that has a report" if not dm.candidates else
                           "every reachable candidate closure is taken by another tap")
                    fs.note = (fs.note + "; " if fs.note else "") + f"drawing: {why}"
                    _issue(r, res_issues, Issue("WARNING", "DRAWING_NO_CANDIDATE",
                                                f"{r.cable} fibre {r.fiber} ({r.value('address')}): {why}",
                                                r.olm, r.cable, r.fiber, design.source))
                continue
            cst, kind, drop = dm.candidates[c]
            enc = design.enclosure_of[c]
            evid = ev_base + [f"closure {c} at ({design.closures[c][0]:.0f}, {design.closures[c][1]:.0f}); "
                              f"tap enclosure joined by pigtail at ({enc['xy'][0]:.0f}, {enc['xy'][1]:.0f})"]
            if drop is not None:
                evid.append(f"drop symbol at ({drop[0]:.0f}, {drop[1]:.0f}) on the line premise - enclosure")
            how = {"drop": "a drop symbol on the line from the premise to its tap enclosure points to the premise",
                   "premise": "premise found in the drawing, no drop symbol fits; nearest free enclosure in the "
                              "reachable network",
                   "none": "premise not found in the drawing; chosen by elimination and the fibre-order convention"
                   }[kind]
            others = sorted((v[0], x) for x, v in dm.candidates.items() if x != c)
            if fs.code == "FS-UNKNOWN":
                n_new += 1
                note = (f"splice report for {c} not supplied - tap splice not seen in a report; "
                        f"{len(dm.candidates)} candidate closure(s) reachable from {dm.x0}"
                        + (f"; next best {others[0][1]}" if others else ""))
                new = FieldValue(c, PROVISIONAL, f"closure located from the design drawing: the fibre continues "
                                 f"past {dm.x0} without reports; in {c} {how}",
                                 evid + fs.evidence, note, code="FS-DRAWING")
                if "FS-DRAWING" in accepted:
                    new.status = APPROVED
                    new.note += "; rule FS-DRAWING accepted by approvals policy"
                r.fields["fiber_splice"] = new
                r.needs_reports = [c] + [x for x in r.needs_reports if x != c and not x.startswith("(")]
                r.issues = [i for i in r.issues if i.code != "SPLICE_CLOSURE_UNKNOWN"]
                res_issues[:] = [i for i in res_issues if not (i.code == "SPLICE_CLOSURE_UNKNOWN" and
                                                               i.cable == r.cable and i.fiber == r.fiber)]
                _issue(r, res_issues, Issue("WARNING", "FIBER_SPLICE_FROM_DRAWING",
                                            f"{r.cable} fibre {r.fiber} ({r.value('address')}): Fiber Splice {c} "
                                            f"located from the drawing ({how})", r.olm, r.cable, r.fiber,
                                            design.source))
            elif fs.value == c:
                n_agree += 1
                fs.note = (fs.note + "; " if fs.note else "") + f"corroborated by the design drawing ({how})"
                fs.evidence += evid
            elif fs.value not in design.enclosure_of and fs.value in design.closures:
                # the report-derived closure has no tap enclosure: the fibre goes on along a branch cable
                n_branch += 1
                new = FieldValue(c, PROVISIONAL, f"the report-derived closure {fs.value} ({fs.code}: {fs.rule}) "
                                 f"has no tap enclosure in the drawing, so the fibre continues on a branch cable; "
                                 f"in {c} {how}", evid + fs.evidence,
                                 f"splice reports for {fs.value} and {c} not supplied; "
                                 f"{len(dm.candidates)} candidate closure(s) beyond {fs.value}", code="FS-DRAWING")
                if "FS-DRAWING" in accepted:
                    new.status = APPROVED
                    new.note += "; rule FS-DRAWING accepted by approvals policy"
                r.fields["fiber_splice"] = new
                r.needs_reports = [c] + [x for x in r.needs_reports if x != c]
                _issue(r, res_issues, Issue("WARNING", "FIBER_SPLICE_FROM_DRAWING",
                                            f"{r.cable} fibre {r.fiber} ({r.value('address')}): Fiber Splice {c} "
                                            f"from the drawing - report-derived {fs.value} has no tap enclosure",
                                            r.olm, r.cable, r.fiber, design.source))
            else:
                n_disagree += 1
                msg = f"drawing suggests {c} ({how}) instead of the report-derived {fs.value}"
                fs.note = (fs.note + "; " if fs.note else "") + msg
                _issue(r, res_issues, Issue("WARNING", "DRAWING_DISAGREES", f"{r.cable} fibre {r.fiber} "
                                            f"({r.value('address')}): {msg}", r.olm, r.cable, r.fiber, design.source))
    order_txt = {"lower_farther": "lower fibre numbers farther along the route",
                 "lower_nearer": "lower fibre numbers nearer along the route",
                 "none": "not used"}[direction]
    if learned is not None:
        order_txt += f" (learned from {learned[0] + learned[1]} traced pairs: {learned[0]} lower-farther, " \
                     f"{learned[1]} lower-nearer)"
    return [Issue("INFO", "DRAWING_FIBER_SPLICE",
                  f"Drawing {design.source}: Fiber Splice located for {n_new} row(s) (PROVISIONAL, FS-DRAWING); "
                  f"{n_agree} report-derived value(s) corroborated, {n_branch} replaced (report-derived closure has "
                  f"no tap enclosure), {n_disagree} disagree, {n_none} without a candidate. "
                  f"Fibre order: {order_txt}.")]


def _issue(row: OutputRow, res_issues: list, issue: Issue):
    row.issues.append(issue)
    res_issues.append(issue)


def address_hints(results, design) -> None:
    """Review hints from the drawing for doubtful addresses (values are never changed):
    * hub and downstream reports name different premises: which one has an address point;
    * address without a house number: unserved address points on that street near the tap enclosure."""
    from .design import split_address, street_core
    served = set()
    for res in results:
        for r in res.rows:
            num, core = split_address(str(r.value("address") or ""))
            if num:
                served.add((num, core))
    for res in results:
        for r in res.rows:
            fv = r.fields.get("address")
            if fv is None:
                continue
            if fv.code == "ADDR-VARIANT":
                found = bool(design.address_points(str(fv.value)))
                fv.note = (fv.note + "; " if fv.note else "") + \
                    (f"drawing has an address point for {fv.value}" if found else
                     f"drawing has no address point for {fv.value}")
                if found:
                    fv.evidence.append(f"drawing {design.source}: address point {fv.value}")
            elif fv.code == "ADDR-NO-NUMBER":
                core = street_core(re.sub(r"^(?:C-|VAC\s+)", "", str(fv.value or "")))
                enc = design.enclosure_of.get(r.value("fiber_splice") or "")
                if not core or enc is None:
                    continue
                near = sorted((math.dist(a["xy"], enc["xy"]), a["raw"]) for a in design.addresses
                              if a["street"] == core and (a["num"], a["street"]) not in served)
                near = [(dist, raw) for dist, raw in near if dist <= design.cfg.get("address_hint_radius", 1500.0)]
                if near:
                    fv.note = (fv.note + "; " if fv.note else "") + "check whether this premise is the unserved " \
                        "address point on the same street nearest its tap enclosure: " + \
                        ", ".join(f"{raw} ({dist:.0f} from the enclosure)" for dist, raw in near[:2])
