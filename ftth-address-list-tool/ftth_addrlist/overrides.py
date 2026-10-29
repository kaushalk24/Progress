"""Approved overrides: human decisions that are re-applied on every run.

CSV columns (header row required):
  olm, cable_name, fiber_no, field, action, value, approved_by, approved_on, reason, expected_generated

  action  SET     replace the generated value with `value`
          ACCEPT  accept the generated provisional value; `value` must equal it
  field   field key (e.g. fiber_splice) or the template header (e.g. "Fiber Splice")
  expected_generated  (SET only, optional) the generated value when the decision was taken.
          If the generated value has changed since, the override is flagged as stale and the
          field returns to PROVISIONAL until it is re-approved.

Rows are matched on stable identifiers (OLM + cable name + fibre number), never on row position.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .builder import FIELD_LABELS, FIELDS, OlmResult
from .model import APPROVED, CONFIRMED, PROVISIONAL, UNRESOLVED, Issue

COLUMNS = ["olm", "cable_name", "fiber_no", "field", "action", "value", "approved_by", "approved_on",
           "reason", "expected_generated"]
_LABEL_TO_KEY = {v.upper(): k for k, v in FIELD_LABELS.items()}


def _s(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _typed(field: str, text: str):
    if text == "":
        return None
    if field in ("pon_name", "pon_port", "fiber_no") and text.isdigit():
        return int(text)
    return text


def load_overrides(path: str | Path) -> tuple[list[dict], list[Issue]]:
    path = Path(path)
    issues: list[Issue] = []
    if not path.exists():
        return [], [Issue("ERROR", "OVERRIDES_MISSING", f"Overrides file not found: {path}")]
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        header = [h.strip().lower() for h in (reader.fieldnames or [])]
        missing = [c for c in COLUMNS[:8] if c not in header]
        if missing:
            return [], [Issue("ERROR", "OVERRIDES_BAD_HEADER",
                              f"{path.name}: missing column(s) {missing}; expected {COLUMNS}")]
        rows = []
        for n, raw in enumerate(reader, start=2):
            r = {k.strip().lower(): _s(v) for k, v in raw.items() if k}
            if not any(r.values()):
                continue
            r["_line"] = n
            r["_file"] = path.name
            rows.append(r)
    return rows, issues


def apply_overrides(result: OlmResult, overrides: list[dict]) -> list[Issue]:
    issues: list[Issue] = []
    index = {(r.cable, r.fiber): r for r in result.rows}
    for ov in overrides:
        if ov.get("olm") and ov["olm"] != result.olm:
            continue
        where = f"{ov['_file']} line {ov['_line']}"
        fkey = ov["field"] if ov["field"] in FIELDS else _LABEL_TO_KEY.get(ov["field"].upper())
        action = ov["action"].upper()
        if fkey is None:
            issues.append(Issue("ERROR", "OVERRIDE_BAD_FIELD", f"{where}: unknown field {ov['field']!r}", result.olm))
            continue
        if action not in ("SET", "ACCEPT"):
            issues.append(Issue("ERROR", "OVERRIDE_BAD_ACTION", f"{where}: action must be SET or ACCEPT", result.olm))
            continue
        if not ov.get("approved_by") or not ov.get("approved_on"):
            issues.append(Issue("ERROR", "OVERRIDE_NOT_APPROVED",
                                f"{where}: approved_by and approved_on are required; override not applied", result.olm))
            continue
        try:
            fiber = int(ov["fiber_no"])
        except ValueError:
            issues.append(Issue("ERROR", "OVERRIDE_BAD_FIBER", f"{where}: fiber_no {ov['fiber_no']!r} is not a number",
                                result.olm))
            continue
        row = index.get((ov["cable_name"], fiber))
        if row is None:
            issues.append(Issue("ERROR", "OVERRIDE_TARGET_MISSING", f"{where}: no row for cable {ov['cable_name']!r} "
                                f"fibre {fiber} in {result.olm}", result.olm, ov["cable_name"], fiber))
            continue
        fv = row.fields[fkey]
        current = _s(fv.value)
        stamp = f"{ov['approved_by']} {ov['approved_on']}"
        if action == "ACCEPT":
            if fv.status == UNRESOLVED:
                issues.append(Issue("ERROR", "OVERRIDE_ACCEPT_UNRESOLVED", f"{where}: an unresolved value cannot be "
                                    f"accepted; use SET with the value (or an explicit blank with a reason)",
                                    result.olm, row.cable, row.fiber))
                continue
            if current != ov["value"]:
                issues.append(Issue("WARNING", "OVERRIDE_STALE", f"{where}: ACCEPT of {ov['value']!r} no longer matches "
                                    f"generated value {current!r}; review again", result.olm, row.cable, row.fiber))
                continue
            if fv.status == PROVISIONAL:
                fv.status = APPROVED
            fv.note = (fv.note + "; " if fv.note else "") + f"accepted by {stamp} ({where}): {ov.get('reason', '')}"
            fv.evidence.append(where)
            continue
        # SET
        if ov["value"] == "" and not ov.get("reason"):
            issues.append(Issue("ERROR", "OVERRIDE_BLANK_WITHOUT_REASON", f"{where}: setting a blank value needs a "
                                f"reason", result.olm, row.cable, row.fiber))
            continue
        new_value = _typed(fkey, ov["value"])
        exp = ov.get("expected_generated", "")
        stale = exp != "" and exp != current
        if fv.status == CONFIRMED and current and current != ov["value"]:
            issues.append(Issue("WARNING", "OVERRIDE_REPLACES_CONFIRMED",
                                f"{where}: replaces confirmed value {current!r} with {ov['value']!r}",
                                result.olm, row.cable, row.fiber))
        prev = f"generated {current!r} ({fv.status}, {fv.code})"
        fv.value = new_value
        fv.code = "OVERRIDE"
        fv.rule = f"approved override by {stamp}: {ov.get('reason', '')}"
        fv.evidence.append(where)
        fv.note = prev
        fv.status = APPROVED
        if stale:
            fv.status = PROVISIONAL
            fv.note += f"; STALE - approved when generated value was {exp!r}"
            issues.append(Issue("WARNING", "OVERRIDE_STALE", f"{where}: generated value changed from {exp!r} to "
                                f"{current!r} since approval; re-approve", result.olm, row.cable, row.fiber))
    return issues


def review_worklist(result: OlmResult) -> list[dict]:
    """Rows/fields that need a decision, pre-filled for the overrides file."""
    out = []
    for r in result.rows:
        for k in FIELDS:
            fv = r.fields[k]
            if fv.status in (PROVISIONAL, UNRESOLVED):
                out.append({
                    "olm": r.olm, "cable_name": r.cable, "fiber_no": r.fiber, "field": k,
                    "action": "", "value": _s(fv.value), "approved_by": "", "approved_on": "", "reason": "",
                    "expected_generated": _s(fv.value),
                    "status": fv.status, "rule_code": fv.code, "address": _s(r.value("address")),
                    "why_review": "; ".join(x for x in (fv.rule, fv.note) if x),
                })
    return out
