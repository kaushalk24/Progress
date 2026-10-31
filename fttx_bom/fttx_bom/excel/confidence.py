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

import re
from dataclasses import dataclass, field

from ..engine import policies as pol
from ..engine.network import AREAS
from ..engine.rules import Rule, evaluate
from ..engine.takeoff import Takeoff

LOW, REVIEW = "LOW", "REVIEW"
FILL = {LOW: "FFC7CE", REVIEW: "FFEB9C"}  # light red / light amber
FONT = {LOW: "9C0006", REVIEW: "7F6000"}
REVIEW_SHEET = "BOM Review"

# BOM line families, by the takeoff key a rule reads
GROUPS = {
    "passings": r"pass_(res|com|mdu)|passings",
    "peds": r"ped_max(5|10)",
    "structures": r"vault|ug_lbox",
    "route": r"route_(ug_ft|aerial_ft|miles)",
    "drops": r"drop_ft_bom",
    "cable": r"cable_\d{3}",
    "enclosures": r"fosc450[a-d]",
    "trays": r"tray_450[bd]|basket_d",
    "splitters": r"splitter_1x\d+|pon_ports",
    "upgrades": r"max10_upgrades",
    "olm": r".*\bolm\w*",
}

# design-check issue code -> (line families, level)
ISSUE_EFFECT = {
    "NETWORK_BOUNDARY": ("*", LOW), "NETWORK_BLANK": ("*", LOW),
    "ADDRESS_LIST_MISSING": ("passings splitters", LOW), "ADDRESS_LIST_EMPTY": ("passings splitters", LOW),
    "SPLIT_RATIO_ASSUMED": ("splitters", LOW), "REPORT_UNREADABLE": ("enclosures trays splitters", LOW),
    "CABLE_TOTAL_MISMATCH": ("cable", LOW), "CABLE_UNDERSIZED": ("cable", REVIEW),
    "PON_PORT_DUPLICATE": ("splitters", REVIEW), "SPLITTER_MISMATCH": ("splitters", REVIEW),
    "PON_MISMATCH": ("splitters", REVIEW), "SPLIT_RATIO_MIXED": ("splitters", REVIEW),
    "DROP_COUNT_MISMATCH": ("drops", REVIEW), "ADDRESS_NO_DROP": ("drops", REVIEW), "DROP_NOT_FROM_PED": ("drops", REVIEW),
    "CABLE_ROUTE_NOT_FOUND": ("cable", REVIEW), "CABLE_ONLY_IN_REPORT": ("cable", REVIEW), "CABLE_ROUTE_LENGTH": ("cable", REVIEW),
    "CLOSURE_OVER_CAPACITY": ("trays enclosures", REVIEW), "ENCLOSURE_UNMAPPED": ("enclosures trays", REVIEW),
    "ENCLOSURE_TYPE_BLANK": ("enclosures trays", REVIEW), "MAX5_ON_LARGE_CABLE": ("peds", REVIEW),
    "ADDRESS_LAYER_VS_BOUNDARY": ("passings splitters", REVIEW), "SERVED_NOT_DRAWN": ("passings", REVIEW),
    "TRENCH_NO_FIBER": ("route", REVIEW), "NETWORK_BOUNDARY_FALLBACK": ("*", REVIEW),
    "CABLE_REPORT_MISMATCH": ("cable", REVIEW), "CABLE_LABEL_DUPLICATE": ("cable", REVIEW),
    "PASSINGS_NEGATIVE": ("passings", LOW), "BLOCK_NOT_DEFINED": ("peds structures", LOW),
}
NEAR_EDGE_BLOCK = {"CX1-MAX10": r"ped_max10", "CX1-MAX5": r"ped_max5", "CX1-VAULT": r"vault"}
# conventions whose evidence is not settled: flag the cell when the alternatives give another number
UNSETTLED = {"drop_columns", "max10_upgrade", "route_footage"}


@dataclass
class Flag:
    key: str  # rule key (part number or label)
    net: str
    area: str
    level: str
    reasons: list[str] = field(default_factory=list)
    value: float | None = None

    def add(self, level: str, reason: str):
        if reason not in self.reasons:
            self.reasons.append(reason)
        if level == LOW:
            self.level = LOW


def _group(value_expr: str | None) -> set[str]:
    if not value_expr:
        return set()
    names = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", value_expr))
    return {g for g, rx in GROUPS.items() if any(re.fullmatch(rx, n) for n in names)}


def assess(rules: list[Rule], tk: Takeoff, issues=(), address_lists=None, reports=None) -> dict[tuple[str, str, str], Flag]:
    flags: dict[tuple[str, str, str], Flag] = {}
    address_lists = address_lists or {}

    def flag(rule, n, a, level, reason, value=None):
        f = flags.get((rule.key, n, a))
        if f is None:
            f = flags[(rule.key, n, a)] = Flag(rule.key, n, a, level, [], value)
        f.add(level, reason)

    by_net: dict[str, list] = {}
    for i in issues:
        by_net.setdefault(i.network, []).append(i)
    for rule in rules:
        if not rule.write or not rule.value:
            continue
        groups = _group(rule.value)
        for n in tk.networks:
            for a in AREAS:
                v, note = evaluate(rule, tk, n, a)
                if v is None:
                    flag(rule, n, a, LOW, f"not computed - {note}")
                    continue
                if rule.status == "INFERRED":
                    flag(rule, n, a, REVIEW, "rule inferred from the design data, not confirmed by an approved BOM", v)
                if "passings" in groups and not (n in address_lists and address_lists[n].served):
                    flag(rule, n, a, LOW, "no address list - passings from drawing count blocks", v)
                if "splitters" in groups and not (n in address_lists and address_lists[n].served) and not reports:
                    flag(rule, n, a, LOW, "no address list or splice reports - split ratio and PON design not confirmed", v)
                if "cable" in groups:
                    fib = int(re.findall(r"cable_(\d{3})", rule.value)[0])
                    odd = [c.name for c in tk.cables if c.network == n and c.fibers == fib
                           and ("label point" in c.split_method or "report only" in c.split_method)]
                    if odd:
                        flag(rule, n, a, REVIEW, f"{len(odd)} cable(s) not routed in the drawing; Grant/Non-Grant split at the label", v)
                for p in pol.POLICIES:
                    if p.name not in UNSETTLED or not any(p.owns(k) for k in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", rule.value)):
                        continue
                    alts = {o: tk.get(f"{rule.value}@{o}", n, a) for o in p.options}
                    other = {o: x for o, x in alts.items() if x is not None and o != tk.policy_used.get(p.name) and abs(x - v) > 1e-6}
                    if other:
                        flag(rule, n, a, REVIEW, f"convention '{p.title}' not settled - other options give "
                             + ", ".join(f"{o} {x:g}" for o, x in other.items()), v)
                for i in by_net.get(n, []) + by_net.get("", []):
                    eff = ISSUE_EFFECT.get(i.code)
                    if eff and (eff[0] == "*" or groups & set(eff[0].split())):
                        flag(rule, n, a, eff[1], f"{i.code}: {i.message[:140]}", v)
                    if i.code == "NEAR_GRANT_EDGE":
                        for blk, rx in NEAR_EDGE_BLOCK.items():
                            if blk in i.message and re.fullmatch(rx, rule.value or ""):
                                flag(rule, n, a, REVIEW, f"object near a Non-Grant edge: {i.message[:120]}", v)
                if (rule.key, n, a) in flags:
                    flags[(rule.key, n, a)].value = v
    return flags
