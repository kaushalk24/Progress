"""Confidence of every BOM quantity cell.

Each written (line, network, area) cell gets a level:

  LOW     do not order without checking: the value could not be computed, a key input is missing
          (no address list, split ratio assumed, no splice reports) or a blocking issue affects it
  REVIEW  check before ordering: inferred rule, an unsettled convention whose alternatives give a
          different number, or a design-check warning on that line in that network
  (none)  derived from the drawing and the design inputs by a confirmed standard

The writer highlights LOW / REVIEW cells in the BOM (fill + comment) and lists them on a
"BOM Review" sheet; the audit repeats the list.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from ..engine import policies as pol
from ..engine.network import AREAS, GRANT, NONGRANT
from ..engine.rules import Rule, evaluate
from ..engine.takeoff import Takeoff

LOW, REVIEW = "LOW", "REVIEW"
FILL = {LOW: "FFC7CE", REVIEW: "FFEB9C"}  # light red / light amber
FONT = {LOW: "9C0006", REVIEW: "7F6000"}
REVIEW_SHEET = "BOM Review"

# BOM line families, by the takeoff key a rule reads (a rule can belong to several)
GROUPS = {
    "passings": r"pass_(res|com|mdu)|passings",
    "residential": r"pass_res",
    "peds": r"ped_max(5|10)",
    "structures": r"vault|ug_lbox",
    "route": r"route_(ug_ft|aerial_ft|miles)",
    "route_ug": r"route_(ug_ft|miles)",
    "drops": r"drop_ft_bom",
    "cable": r"cable_\d{3}",
    "enclosures": r"fosc450[a-d]",
    "trays": r"tray_450[bd]",
    "splitters": r"splitter_1x\d+",
    "sfp": r"pon_ports",
    "upgrades": r"max10_upgrades",
    "olm": r".*\bolm\w*",
}

# design-check issue code -> (line families, level). Cable issues are applied to the fiber count they name only.
ISSUE_EFFECT = {
    "NETWORK_BOUNDARY": ("*", LOW), "NETWORK_BLANK": ("*", LOW), "NETWORK_BOUNDARY_FALLBACK": ("*", REVIEW),
    "SPLIT_RATIO_ASSUMED": ("splitters", LOW), "REPORT_UNREADABLE": ("enclosures trays splitters", LOW),
    "PON_PORT_DUPLICATE": ("splitters", REVIEW), "SPLITTER_MISMATCH": ("splitters", REVIEW),
    "PON_MISMATCH": ("splitters", REVIEW), "SPLIT_RATIO_MIXED": ("splitters sfp", REVIEW),
    "DROP_COUNT_MISMATCH": ("drops", REVIEW), "ADDRESS_NO_DROP": ("drops", REVIEW), "DROP_NOT_FROM_PED": ("drops", REVIEW),
    "CLOSURE_OVER_CAPACITY": ("trays enclosures", REVIEW), "ENCLOSURE_UNMAPPED": ("enclosures trays", REVIEW),
    "ENCLOSURE_TYPE_BLANK": ("enclosures trays", REVIEW), "MAX5_ON_LARGE_CABLE": ("peds", REVIEW),
    "SERVED_NOT_DRAWN": ("passings", REVIEW), "ADDRESS_SERVED_TWICE": ("passings", REVIEW), "TRENCH_NO_FIBER": ("route_ug", REVIEW),
    "PASSINGS_NEGATIVE": ("passings", LOW), "BLOCK_NOT_DEFINED": ("peds structures", LOW),
}
CABLE_EFFECT = {"CABLE_TOTAL_MISMATCH": LOW, "CABLE_UNDERSIZED": REVIEW, "CABLE_ROUTE_LENGTH": REVIEW,
                "CABLE_REPORT_MISMATCH": REVIEW, "CABLE_LABEL_DUPLICATE": REVIEW}
NEAR_EDGE_BLOCK = {"CX1-MAX10": r"ped_max10", "CX1-MAX5": r"ped_max5", "CX1-VAULT": r"vault"}
# why a value could not be derived, in plain words (by takeoff key pattern)
NOT_COMPUTED = [
    (r"drop_ft\w*", "no drop lines in the drawing - run FXAUTO (FX_DROPS) in AutoCAD and save"),
    (r"fosc450\w*|tray_450\w*|trays_450\w*|basket_d", "no splice reports supplied - closures and trays come from the splice reports"),
    (r"ped_max\w*|vault|ug_lbox", "the block is not defined in this drawing (renamed symbol?)"),
    (r"pass_\w*|passings", "passings could not be derived"),
    (r"cable_\d{3}", "no cable labels found"),
]
# conventions whose evidence is not settled: flag the cell when the alternatives give another number
UNSETTLED = {"max10_upgrade"}  # drop columns: confirmed (Grant drops in the Grant column)
# unmapped symbols on these layers could be pedestal types the template writes as 0 (GOAT, ped with tap)
PED_LAYERS = ("RTE_UGPOLES",)
FC_RE = re.compile(r"FC(\d{3})")


@dataclass
class Flag:
    key: str  # rule key (part number or label)
    net: str
    area: str
    level: str
    reasons: list[str] = field(default_factory=list)
    value: float | None = None
    _seen: dict = field(default_factory=dict, repr=False)  # reason kind -> [index in reasons, count]

    def add(self, level: str, reason: str, kind: str | None = None):
        """Add a reason; repeated reasons of one kind (e.g. one per address) are shown once with a count."""
        if kind:
            if kind in self._seen:
                self._seen[kind][1] += 1
            else:
                self._seen[kind] = [len(self.reasons), 1]
                self.reasons.append(reason)
        elif reason not in self.reasons:
            self.reasons.append(reason)
        if level == LOW:
            self.level = LOW

    def finish(self):
        for i, cnt in self._seen.values():
            if cnt > 1:
                self.reasons[i] += f" (+{cnt - 1} more like this)"
        self._seen.clear()


def _group(value_expr: str | None) -> set[str]:
    if not value_expr:
        return set()
    names = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", value_expr))
    return {g for g, rx in GROUPS.items() if any(re.fullmatch(rx, n) for n in names)}


def _cable_targets(issue, tk: Takeoff) -> set[tuple[str, int]]:
    """(network, fiber count) cells a cable issue affects: the cable(s) it names, else the FCnnn in the text."""
    msg = issue.message.upper()
    named = [c for c in tk.cables if c.name and c.name.upper() in msg]
    if named:
        out = {(c.network or issue.network, c.fibers) for c in named}
    else:
        out = {(issue.network, int(f)) for f in FC_RE.findall(msg)}
    if issue.code == "CABLE_REPORT_MISMATCH":  # the report gives another size: both rows
        out |= {(n, int(f)) for n, _ in list(out) for f in re.findall(r"REPORT (\d+)F", msg)}
    return out


def _address_side_shift(tk: Takeoff, n: str, issues) -> tuple[int, str]:
    """Change of Grant passings if the conflicting addresses followed the other rule (address layer when the
    count uses the Non-Grant boundary, and the reverse)."""
    conflict = [i for i in issues if i.code == "ADDRESS_LAYER_VS_BOUNDARY" and i.network == n]
    by_layer = tk.extra.get("passings_rule", "boundary") == "grant_layer"
    # "outside every Non-Grant polygon" on the Address layer: Grant by the boundary, Non-Grant by the layer
    shift = sum((1 if "outside every Non-Grant" in i.message else -1) * (1 if by_layer else -1) for i in conflict)
    other = "the Non-Grant boundary" if by_layer else "the GRANTADDRESS layer"
    return shift, (f"{len(conflict)} served address(es) are on a layer that disagrees with the Non-Grant boundary; "
                   f"by {other}, Grant would be {shift:+d}" if conflict else "")


def assess(rules: list[Rule], tk: Takeoff, issues=(), address_lists=None, reports=None) -> dict[tuple[str, str, str], Flag]:
    flags: dict[tuple[str, str, str], Flag] = {}
    address_lists = address_lists or {}

    def flag(rule, n, a, level, reason, value=None, kind=None):
        f = flags.get((rule.key, n, a))
        if f is None:
            f = flags[(rule.key, n, a)] = Flag(rule.key, n, a, level, [], value)
        f.add(level, reason, kind)

    by_net: dict[str, list] = {}
    cable_hits: dict[tuple[str, int], list] = {}
    # closure findings go to that closure's type (450B / 450D ...) and area only
    closures = {name.upper(): (net, area, typ.lower()) for net, area, typ, _s, name in tk.extra.get("enclosures", [])}
    closure_hits: dict[tuple[str, str, str], list] = {}
    for i in issues:
        if i.code == "CLOSURE_OVER_CAPACITY" and i.message.split(":")[0].upper() in closures:
            closure_hits.setdefault(closures[i.message.split(":")[0].upper()], []).append(i)
            continue
        if i.code in CABLE_EFFECT:
            if i.code == "CABLE_LABEL_DUPLICATE" and "identical values" in i.message:
                continue  # counted once: the quantity is not affected
            for t in _cable_targets(i, tk):
                cable_hits.setdefault(t, []).append(i)
            continue
        by_net.setdefault(i.network, []).append(i)
    unmapped_peds = [i for i in issues if i.code == "UNMAPPED_BLOCK" and any(f" on {lay} " in i.message for lay in PED_LAYERS)]
    for rule in rules:
        if rule.hand_count and rule.value:
            for n in tk.networks:
                for a in AREAS:
                    v, _note = evaluate(rule, tk, n, a)
                    flag(rule, n, a, LOW, "hand count required (template note)" + (f"; the drawing gives {v:g} by the note's criteria" if v is not None else ""), v)
            continue
        if not rule.write or not rule.value:
            continue
        if rule.value.strip() == "0":
            if unmapped_peds:
                for n in tk.networks:
                    for a in AREAS:
                        flag(rule, n, a, REVIEW, "written 0 by the design standard, but the drawing has unmapped structure blocks: "
                             + "; ".join(i.message[:80] for i in unmapped_peds[:3]), 0)
            continue
        groups = _group(rule.value)
        names = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", rule.value)
        for n in tk.networks:
            shift, shift_why = _address_side_shift(tk, n, issues)
            for a in AREAS:
                v, note = evaluate(rule, tk, n, a)
                if v is None:
                    why = next((w for rx, w in NOT_COMPUTED if re.search(rx, rule.value)), "could not be derived from the inputs")
                    flag(rule, n, a, LOW, f"not computed: {why}")
                    continue
                if rule.status == "INFERRED":
                    flag(rule, n, a, REVIEW, "derived by an inferred rule (not yet confirmed against an approved BOM)", v)
                has_list = n in address_lists and address_lists[n].served
                if "passings" in groups and not has_list:
                    flag(rule, n, a, LOW, "no address list - passings from drawing count blocks", v)
                if groups & {"splitters", "sfp"} and not has_list and not reports:
                    flag(rule, n, a, LOW, "no address list or splice reports - split ratio and PON design not confirmed", v)
                if shift_why and "residential" in groups:
                    flag(rule, n, a, REVIEW, shift_why, v)
                if shift and groups & {"splitters", "sfp"}:
                    gp, ngp = tk.get("passings", n, GRANT, 0) or 0, tk.get("passings", n, NONGRANT, 0) or 0
                    alt = {GRANT: gp + shift, NONGRANT: ngp - shift}[a]
                    cur = {GRANT: gp, NONGRANT: ngp}[a]
                    ratio = tk.extra.get("ratio", {}).get(n, 64)
                    if "sfp" in groups:
                        changed = math.ceil(math.ceil(max(alt, 0) / 32) / 2) != math.ceil(math.ceil(cur / 32) / 2)
                    else:
                        changed = math.ceil(max(gp + shift, 0) / ratio) != math.ceil(gp / ratio)
                    if changed:
                        flag(rule, n, a, REVIEW, shift_why + " - moving them to the boundary side changes this quantity", v)
                if "cable" in groups:
                    fib = int(re.findall(r"cable_(\d{3})", rule.value)[0])
                    odd = [c.name for c in tk.cables if c.network == n and c.fibers == fib and c.split_uncertain]
                    if odd:
                        flag(rule, n, a, REVIEW, f"{len(odd)} cable(s) without a traced route and with ends in different areas "
                             f"(or not found): Grant/Non-Grant split taken at the label - " + ", ".join(odd[:3]), v)
                    # an issue that names neither a cable nor a network applies to that fiber count everywhere
                    for i in cable_hits.get((n, fib), []) + cable_hits.get(("", fib), []):
                        flag(rule, n, a, CABLE_EFFECT[i.code], i.message[:160], v, kind=i.code)
                m = re.fullmatch(r"fosc450([a-d])|tray_450([a-d])", rule.value.strip())
                if m:
                    for i in closure_hits.get((n, a, m.group(1) or m.group(2)), []):
                        flag(rule, n, a, REVIEW, i.message[:160], v, kind=i.code)
                for pp in pol.POLICIES:
                    if pp.name not in UNSETTLED or not any(pp.owns(k) for k in names):
                        continue
                    alts = {o: tk.get(f"{rule.value}@{o}", n, a) for o in pp.options}
                    other = {o: x for o, x in alts.items() if x is not None and o != tk.policy_used.get(pp.name) and abs(x - v) > 1e-6}
                    if other:
                        flag(rule, n, a, REVIEW, f"convention '{pp.title}' not settled - other options give "
                             + ", ".join(f"{o} {x:g}" for o, x in other.items()), v)
                for i in by_net.get(n, []) + by_net.get("", []):
                    eff = ISSUE_EFFECT.get(i.code)
                    if eff and (eff[0] == "*" or groups & set(eff[0].split())):
                        flag(rule, n, a, eff[1], i.message[:160], v, kind=i.code)
                    if i.code == "NEAR_GRANT_EDGE":
                        for blk, rx in NEAR_EDGE_BLOCK.items():
                            if blk in i.message and re.fullmatch(rx, rule.value or ""):
                                flag(rule, n, a, REVIEW, f"object near a Non-Grant edge: {i.message[:120]}", v, kind="NEAR_GRANT_EDGE")
                if (rule.key, n, a) in flags:
                    flags[(rule.key, n, a)].value = v
    for f in flags.values():
        f.finish()
    return flags
