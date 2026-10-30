# Input requirements and new-region export checklist

## Can the DWG and splice reports alone populate the template?

* **Splice reports – yes, for 7 of 9 columns** (PON NAME, PON PORT, FIBER #, ADDRESS,
  COLOR TUBE, COLOR FIBER, CABLE NAME) and for Fiber Tap Name; these came out 100 % on
  the reference pack apart from documented manual errors. All of it comes from the
  **hub closure report**.
* **Fiber Splice is confirmed only by the downstream closure reports** – the report of the
  closure where the tap pigtail/drop is spliced. In the two validation regions most of
  those closures had no report (region A: 624 of 706).
* **The design DWG fills the rest.** It has no fibre, tube, splitter, PON port, circuit or
  tap-name data, so it cannot produce the list by itself, but it does hold the drawn
  network: closure symbols (`NAME`), tap enclosures joined to their closure by pigtails,
  fibre-cable polylines, address points and drop symbols. Where the reports stop before
  the tap splice, the tool locates the closure from these objects (rule `FS-DRAWING`,
  PROVISIONAL, evidence recorded): in validation this filled every remaining row and
  matched the completed lists in 354 of 354 such rows (286 in region A, 68 in
  region B). Service is never assigned by proximity alone: candidates are restricted to the
  part of the network the traced fibre can still reach, and the drop symbol, the pigtail
  and the fibre order decide between them.

## Input matrix

| Input | Need | Format | Required content | Purpose | Quality checks done by the tool | If absent |
|---|---|---|---|---|---|---|
| Hub closure Splice Connections Report (one per OLM) | **Mandatory** | `.xlsx` export (layout "Splice Connections Report") | Segment table incl. the `OLM Housing` feeder and splitter rows; connection table with Usage, State, Start/End | PON, ports, fibres, colours, cables, addresses, taps, section order | layout/columns present, splice name, splitters present, duplicate fibres, PON ports reused/unused | OLM cannot be generated (`NO_HUB`) |
| Downstream closure reports, every closure on the hub cables' paths **including the closures where taps are spliced** | **Mandatory for a final list** | same | segment tables + connections for pass-through and drop splices | Fiber Splice confirmation, circuit consistency | trace continuity, segment numbering agreement, circuit text agreement | Fiber Splice provisional/unresolved; *Reports to Request* lists what is missing |
| Reports of closures in neighbouring OLMs that the paths cross | Conditional (when cables run through other OLM areas) | same | same | continuity across OLM boundaries | as above | more unresolved rows |
| Template workbook | Optional | `.xlsx`, header in row 1, a styled row 2 | header text, column order, styles, widths | output layout | header matched to `template.columns` | built-in layout (identical to the reference lists) |
| Regional config | Optional | `.toml` | conventions that differ (naming, prefixes, splitter naming, address rewrites, approved rules) | regional conventions without code changes | validated on load | defaults |
| Approved overrides | Optional | `.csv` (see README) | olm, cable_name, fiber_no, field, action, value, approved_by, approved_on, reason | recorded human decisions | approver/date mandatory, target exists, stale detection | review items stay open |
| Design drawing | **Recommended** (needed where downstream reports are missing) | **DWG** AutoCAD 2010–2018 (AC1024–AC1032) or **DXF** | closure blocks with `NAME`, tap enclosure blocks + pigtail polylines, fibre-cable polylines, address-point blocks (`STREET_NUMBER`/`STREET_NAME`, `BUILDING_ADDRESS`/`BUILDING_NAME`), drop symbols | Fiber Splice where the reports stop (`FS-DRAWING`), corroboration of report-derived values, identifier cross-check, address-point coverage | decode-error rate, enclosure–pigtail links, coverage counts | those Fiber Splice cells stay UNRESOLVED |
| Premise/address export from the spatial system (address points with unit numbers, grant flag) | Optional, recommended | `.csv`/`.xlsx` | address id, house number, street, unit, OLM/serving area | detect premises not served, unit completeness | (planned: same as DXF address coverage) | coverage relies on DXF address points |

## DWG handling

The spatial-system export is an AutoCAD 2018-format DWG (AC1032) written by the SpatialNet
DWG filer. The tool reads it directly, with no AutoCAD or converter:

* `dwg_container.py` decrypts the file header and decompresses the sections;
* `dwg_objects.py` decodes the objects the model needs (layers, block names, INSERT with
  attributes, LWPOLYLINE/LINE, TEXT/MTEXT) and skips everything else by size. Both
  validation drawings decoded with **0 errors** (43,189 and 70,399 objects, 2–4 s).
  AC1024/AC1027 use the same layout and are attempted; older versions are refused with a
  message. If more than 1 % of objects fail to decode, the drawing is not used for
  Fiber Splice (`DRAWING_MODEL_UNRELIABLE`) and only the identifier scan runs.
* The block names, attribute tags, layer names and tolerances are in the `[drawing]`
  section of the configuration, so another export style is a configuration change.

A DXF (AutoCAD `SAVEAS` → *AutoCAD 2018 DXF*, or the free ODA File Converter) is read with
`ezdxf` and gives the same model. Map 3D object data and SpatialNet database links are not
in the DWG/DXF block attributes and are not used.

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
- [ ] **Design drawing** of the same revision (DWG as exported, or DXF), covering every
      OLM area: closures, tap enclosures with pigtails, cables, address points, drop symbols.
- [ ] Optional: premise/address export with unit numbers for coverage checks.
- [ ] Project file-name prefix (e.g. `<job number>_<area name>`), and a regional config if
      naming conventions differ (splitter naming, power-port wording, address prefixes).
- [ ] Decide, with the engineering lead, whether the evidence-based inference rules
      (`FS-CABLE-END`, `FS-BREAK-POINT`, `FS-TAP-CABLE`, `FS-DRAWING`, ...) are acceptable without
      per-row review for this project (`config/desk_study_acceptance.toml` is a starting point).
