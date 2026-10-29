# Input requirements and new-region export checklist

## Can the DWG and splice reports alone populate the template?

* **Splice reports – yes, for 7 of 9 columns** (PON NAME, PON PORT, FIBER #, ADDRESS,
  COLOR TUBE, COLOR FIBER, CABLE NAME) and for Fiber Tap Name; these came out 100 % on
  the reference pack apart from documented manual errors. All of it comes from the
  **hub closure report**.
* **Fiber Splice needs the downstream closure reports.** It is confirmed only when the
  report of the closure where the tap pigtail/drop is spliced is supplied. In the
  reference pack 88 % of those closures (624 of 706) had no report, so most Fiber Splice values
  are provisional (inferred from cable ends or broken remnants) or unresolved.
* **The DWG alone cannot produce the list.** It holds closure names, cable names,
  address points (house number + street attributes), poles, strand, grant/non-grant area
  labels and drawing notes, but **no fibre, tube, splitter, PON port or circuit
  assignments, and no tap names**. It is used for validation (identifier and
  address-point coverage), never to assign service by proximity.

## Input matrix

| Input | Need | Format | Required content | Purpose | Quality checks done by the tool | If absent |
|---|---|---|---|---|---|---|
| Hub closure Splice Connections Report (one per OLM) | **Mandatory** | `.xlsx` export (layout "Splice Connections Report") | Segment table incl. the `OLM Housing` feeder and splitter rows; connection table with Usage, State, Start/End | PON, ports, fibres, colours, cables, addresses, taps, section order | layout/columns present, splice name, splitters present, duplicate fibres, PON ports reused/unused | OLM cannot be generated (`NO_HUB`) |
| Downstream closure reports, every closure on the hub cables' paths **including the closures where taps are spliced** | **Mandatory for a final list** | same | segment tables + connections for pass-through and drop splices | Fiber Splice confirmation, circuit consistency | trace continuity, segment numbering agreement, circuit text agreement | Fiber Splice provisional/unresolved; *Reports to Request* lists what is missing |
| Reports of closures in neighbouring OLMs that the paths cross | Conditional (when cables run through other OLM areas) | same | same | continuity across OLM boundaries | as above | more unresolved rows |
| Template workbook | Optional | `.xlsx`, header in row 1, a styled row 2 | header text, column order, styles, widths | output layout | header matched to `template.columns` | built-in layout (identical to the reference lists) |
| Regional config | Optional | `.toml` | conventions that differ (naming, prefixes, splitter naming, address rewrites, approved rules) | regional conventions without code changes | validated on load | defaults |
| Approved overrides | Optional | `.csv` (see README) | olm, cable_name, fiber_no, field, action, value, approved_by, approved_on, reason | recorded human decisions | approver/date mandatory, target exists, stale detection | review items stay open |
| Design drawing | Optional (validation) | **DXF** (full) or DWG (experimental) | text, block attributes (closure `NAME`, `STREET_NUMBER`, `STREET_NAME`) | identifier cross-check, address-point coverage | coverage counts | no drawing cross-check |
| Premise/address export from the spatial system (address points with unit numbers, grant flag) | Optional, recommended | `.csv`/`.xlsx` | address id, house number, street, unit, OLM/serving area | detect premises not served, unit completeness | (planned: same as DXF address coverage) | coverage relies on DXF address points |

## DWG handling

The DWG is AutoCAD 2018-format (AC1032), saved by AutoCAD 2020 / Map 3D, written by the
SpatialNet DWG filer. The tool contains a read-only container reader that recovers the
text strings (enough for identifier cross-checks: it found every closure that appears in
the reports and in the reference lists) but it does not decode entities, so it cannot
pair attribute tags with values or read geometry.

**Supported export for full content (DXF):**

1. AutoCAD / Map 3D / Civil 3D: open the DWG → `SAVEAS` → *AutoCAD 2018 DXF (*.dxf)*.
   Or, without AutoCAD: free **ODA File Converter** (Windows) – input folder with the DWG,
   output version *ACAD2018*, output type *DXF*.
2. Give the `.dxf` to the tool (*Design drawing*).
3. Preserved: text, MTEXT, block names, **block attribute tags and values** (closure
   `NAME`, address points `STREET_NUMBER`/`STREET_NAME`, `TAP_ID`, `NODE`, …), layers, geometry.
   Lost: Map 3D *object data* tables and SpatialNet database links (not part of DXF). If
   address or asset attributes are held as object data rather than block attributes,
   export them separately (Map 3D `MAPEXPORT` to SHP/CSV, or directly from the spatial system).

The DXF path is implemented and tested with synthetic drawings; it has **not** been run
on the reference drawing because no DWG→DXF converter was available in the build
environment.

## New-region export checklist

Before running the tool for a region, obtain:

- [ ] **Hub closure report for every OLM** (the closure with the PLC splitters; its segment
      table shows `OLM Housing: <OLM>`), exported as *Splice Connections Report* `.xlsx`.
- [ ] **Splice Connections Reports for every closure on every cable leaving each hub**,
      down to and including the closures where tap pigtails/drops are spliced (closures
      whose segment table contains a `… TO <tap> FC004 – Pigtail` segment) and MDU feeds.
      Tip: after a first run, the *Reports to Request* list names the missing ones.
- [ ] Reports for closures in neighbouring areas that these cables pass through.
- [ ] **All reports exported from the same spatial-system revision, on the same day**,
      after design changes are complete (mixed revisions cause renamed streets, re-numbered
      segments and moved taps between hub and downstream reports).
- [ ] System-exported reports only – no hand-made "Fiber Optic Splice Guide" sheets.
- [ ] Report file names = splice names; one report per closure (no copies).
- [ ] Optional: design drawing as **DXF** (see above) for the cross-check.
- [ ] Optional: premise/address export with unit numbers for coverage checks.
- [ ] Project file-name prefix (e.g. `<job number>_<area name>`), and a regional config if
      naming conventions differ (splitter naming, power-port wording, address prefixes).
- [ ] Decide, with the engineering lead, whether any inference rules (`FS-CABLE-END`,
      `FS-BREAK-POINT`) are acceptable without per-row review for this project.
