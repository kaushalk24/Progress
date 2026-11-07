# Using the address list from another tool

The address-list tool can be used by another program (for example a callout generator) in two ways. Both
give exactly the rows, values and statuses of the workbook: they come from the same code path
(`pipeline.build`).

## 1. JSON file (any language)

Every run writes, next to each workbook, a JSON file with the same name:

    <prefix>_<OLM>_FTTH_Address List.json                         (FINAL)
    <prefix>_<OLM>_FTTH_Address List_DRAFT-REVIEW-REQUIRED.json   (DRAFT)

The run manifest (`..._run_manifest.json`) names it under `"json"`.

```json
{
  "schema": "ftth-address-list",
  "schema_version": 1,
  "tool_version": "2.4.0",
  "run_at": "2026-11-07T10:15:00",
  "olm": "ABC-R01",
  "hub": "ABC-00001G",
  "final": false,
  "counts": {"CONFIRMED": 359, "APPROVED": 0, "PROVISIONAL": 5, "UNRESOLVED": 0},
  "columns": [{"field": "pon_name", "header": "PON NAME"}, "... 9 columns in workbook order ..."],
  "sections": [{"cable": "ABC-00001G TO ABC-00004G FC096", "segment": 1, "fibers": 96}],
  "rows": [
    {
      "row": 30, "kind": "subscriber", "status": "CONFIRMED",
      "section": "ABC-00001G TO ABC-00004G FC096", "cable_fiber": 1,
      "pon_name": "1", "pon_port": 2, "fiber_no": 1, "address": "1097 MAIN ST",
      "tube_color": "BL", "fiber_color": "BL", "cable_name": "ABC-00001G TO ABC-00004G FC096",
      "tap_name": "ABC-R-1097 MAIN ST", "fiber_splice": "ABC-00037G",
      "cells": {"fiber_splice": {"status": "CONFIRMED", "code": "FS-TRACE-TERMINAL", "note": ""}, "...": "..."},
      "route": ["ABC-00001G", "ABC-00002", "..."],
      "terminal_kind": "MAX10 Enclosure(M Bulk)"
    }
  ],
  "issues": [{"severity": "WARNING", "code": "ADDR-NO-NUMBER", "message": "...", "cable": "...", "fiber": 4,
              "source": "..."}]
}
```

| Field | Meaning |
|---|---|
| `rows` | In workbook order, one per fibre of every section (spares and transport included). |
| `kind` | `subscriber`, `spare`, `transport`, `splitter_common`, `power` or `other`. A consumer that only wants premises filters on `subscriber`. |
| `status` | Worst status of the row's cells: `CONFIRMED`, `APPROVED`, `PROVISIONAL` (amber, inferred) or `UNRESOLVED` (red, missing). |
| the 9 column fields | Exactly the workbook values. `null` = empty cell. `pon_name` is text (`"1"`), `pon_port` / `fiber_no` / `cable_fiber` are numbers, the rest text. |
| `cells` | Per column: status, rule code (see FIELD_MAPPING.md) and the review note. |
| `route` | Closures the fibre passes, hub first, as traced in the splice reports. |
| `terminal_kind` | Kind of the enclosure the fibre ends in (`MAX10 Enclosure(M Bulk)`, `FTTx MDU Enclosure`, ...), when known. |
| `final` | `true` only when nothing is left to review. A consumer should show a warning when it is `false`. |

`schema_version` changes only when a field is removed or changes meaning. New fields may be added at any
time, so a reader must ignore fields it does not know.

## 2. Python

```python
from ftth_addrlist.api import generate, load_json

lists = generate("C:/Regions/R17/Splice reports", drawing="C:/Regions/R17/DMI-R17.dwg")
for olm in lists:                          # one dict per OLM, the structure above
    for row in olm["rows"]:
        if row["kind"] == "subscriber":
            print(row["address"], row["tap_name"], row["fiber_splice"], row["status"])

data = load_json("...FTTH_Address List.json")   # read a file written by an earlier run
```

* `generate(reports, drawing=None, olms=None, config=None, overrides=None, log=None)` writes no files.
  `log` receives the progress lines the window shows.
* Unusable inputs raise `ftth_addrlist.pipeline.InputError` (or `config.ConfigError`) with a message
  meant for the user: a missing folder or drawing, no splice reports, no OLM found.
* `ftth_addrlist.pipeline.run(...)` is the full run with all files (what the window and command line do).

## Rules for a combined application

* Keep the address list's statuses visible: a callout made from a `PROVISIONAL` or `UNRESOLVED` cell must
  be marked for review too.
* Do not change values: corrections go through the overrides file (ACCEPT / SET with a name and date) so
  that the address list and everything made from it stay the same.
* Use one tool version for both: the JSON carries `tool_version`.
