"""Rule catalogue loader / evaluator (config/bom_rules.json)."""
from __future__ import annotations

import ast
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
    hand_count: bool = False  # not written: an engineer counts it; the BOM cell is highlighted with the tool's count

    @property
    def key(self) -> str:
        return self.part or self.label or "?"


def load_rules(path: str | Path | None = None) -> tuple[dict, list[Rule]]:
    cfg = json.loads(Path(path or CONFIG_DIR / "bom_rules.json").read_text(encoding="utf-8"))
    rules = [
        Rule(r.get("part"), r.get("label"), r.get("value"), r.get("unit", "EA"), r["status"],
             bool(r.get("write", False)), r.get("basis", ""), r.get("source", ""), bool(r.get("hand_count", False)))
        for r in cfg["rows"]
    ]
    return cfg, rules


FUNCS = {"ceil": math.ceil, "floor": math.floor, "min": min, "max": max, "round": round, "abs": abs}
_BINOPS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
           ast.Div: lambda a, b: a / b, ast.FloorDiv: lambda a, b: a // b, ast.Mod: lambda a, b: a % b}
_UNOPS = {ast.UAdd: lambda a: +a, ast.USub: lambda a: -a}


def safe_eval(expr: str, values: dict, known: set[str]) -> tuple[float, set[str]]:
    """Evaluate an arithmetic rule expression over takeoff keys.

    Only numbers, takeoff key names, + - * / // %, unary +/- and the functions in FUNCS are
    allowed - attribute access, subscripts, comprehensions, lambdas etc. are rejected, so a rule
    catalogue cannot run code. Returns (value, missing key names)."""
    missing: set[str] = set()

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return n.value
        if isinstance(n, ast.Name):
            if n.id in values:
                return values[n.id]
            missing.add(n.id)
            return 0
        if isinstance(n, ast.BinOp) and type(n.op) in _BINOPS:
            return _BINOPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _UNOPS:
            return _UNOPS[type(n.op)](ev(n.operand))
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in FUNCS and not n.keywords):
            return FUNCS[n.func.id](*[ev(a) for a in n.args])
        raise ValueError(f"rule expression not allowed: {ast.dump(n)[:80]}")

    return ev(ast.parse(expr, mode="eval")), missing


def evaluate(rule: Rule, tk: Takeoff, net: str, area: str) -> tuple[float | None, str]:
    """Return (value, note). None means 'not computed' (never silently 0)."""
    if not rule.value:
        return None, "no quantity rule"
    known = {k for k, _n, _a in tk.q}
    if IDENT.match(rule.value):
        if rule.value not in known:
            return None, f"takeoff key '{rule.value}' not computed"
        if (rule.value, net, area) not in tk.q:
            return None, f"'{rule.value}' not computed for {net}"
        return _no_negative(tk.get(rule.value, net, area))
    try:
        val, missing = safe_eval(rule.value, tk.column(net, area), known)
    except (ValueError, SyntaxError, ZeroDivisionError, TypeError) as e:
        return None, f"rule expression error: {e}"
    if missing:
        return None, f"missing takeoff keys {sorted(missing)}"
    return _no_negative(val)


def _no_negative(v) -> tuple[float | None, str]:
    """A BOM quantity is never negative: a negative result means inconsistent inputs, so it is left blank."""
    if v is not None and v < 0:
        return None, f"computed {v:g} < 0 - inconsistent inputs (see Checks), left blank"
    return v, ""
