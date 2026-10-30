"""Rule catalogue loader / evaluator (config/bom_rules.json)."""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from .takeoff import Takeoff

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass
class Rule:
    part: str | None
    label: str | None
    value: str | None
    unit: str
    status: str
    write: bool
    basis: str
    source: str

    @property
    def key(self) -> str:
        return self.part or self.label or "?"


def load_rules(path: str | Path | None = None) -> tuple[dict, list[Rule]]:
    cfg = json.loads(Path(path or CONFIG_DIR / "bom_rules.json").read_text())
    rules = [
        Rule(r.get("part"), r.get("label"), r.get("value"), r.get("unit", "EA"), r["status"],
             bool(r.get("write", False)), r.get("basis", ""), r.get("source", ""))
        for r in cfg["rows"]
    ]
    return cfg, rules


class _Env(dict):
    """Evaluation namespace that records names missing from the takeoff."""

    def __init__(self, values: dict, known: set[str]):
        super().__init__(values)
        self.known = known
        self.missing: set[str] = set()

    def __missing__(self, key):
        if key in ("ceil", "floor", "min", "max", "round"):
            return {"ceil": math.ceil, "floor": math.floor, "min": min, "max": max, "round": round}[key]
        self.missing.add(key)
        return 0


def evaluate(rule: Rule, tk: Takeoff, net: str, area: str) -> tuple[float | None, str]:
    """Return (value, note). None means 'not computed' (never silently 0)."""
    if not rule.value:
        return None, "no quantity rule"
    known = {k for k, _n, _a in tk.q}
    if IDENT.match(rule.value):
        if rule.value not in known:
            return None, f"takeoff key '{rule.value}' not computed"
        return tk.get(rule.value, net, area, 0), ""
    env = _Env(tk.column(net, area), known)
    val = eval(rule.value, {"__builtins__": {}}, env)  # expressions come from the trusted rule catalogue
    if env.missing:
        return None, f"missing takeoff keys {sorted(env.missing)}"
    return val, ""
