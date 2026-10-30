# Field mapping and derivation rules

The address list has one row per fibre of each cable that touches the OLM's **hub
closure** (the closure holding the PLC splitters). Rows are fibre-level, so the join key
of every row is **OLM + cable name + fibre number**; addresses are attributes of fibres,
not the other way round.

## Source records used

Spatial-system *Splice Connections Report* (one workbook per closure):

| Report part | Fields used |
|---|---|
| Header block | `Splice name:` (closure id), `On:` (export time – revision), `Location:`, `Enclosure Type:` |
| Segment table (`Segment`, `Count`, `Start Splice`, `End Splice`) | `Segment N of <CABLE> - <placement>`, fibre count, start/end enclosure as `<kind>: <name>` (kinds: `Splice Case`, `OLM Housing`, `MAX10 Enclosure(M Bulk)`, `FTTx MDU Enclosure`). Non-segment rows = equipment, e.g. `PLC COUPLER 64 1 FE0-F1PLC64` (count 65 = 1 common + 64 outputs) |
| Connection table (A Cable / B Cable / Usage / Circuit) | each side: `Segment` (`<CABLE>: SegN` or device id `PLCCOUPLER641`), `Group 2` (tube colour), `Fiber` (fibre colour), `#` (`TT.FF(abs)` for cables, `P(P)` for device ports); `Usage` (circuit text, e.g. `<TAP>:<tap port> <address>`), `State` (`Return`, `Forward`, `Forward/Return`, `Spare (dark)`, `Broken`, `Misc`), circuit `Start` / `End` enclosures |

A hand-made *Fiber Optic Splice Guide* layout is also read (low trust: no outgoing fibre
numbers, colours only, no circuit data; any value whose path uses one is PROVISIONAL).

## Row set and order (rules SEC-*)

1. **Hub** = the closure whose report has a segment from/to `OLM Housing: <OLM>`.
2. **Sections** = cables with a segment at the hub: the **feeder** (`<OLM> TO <HUB> FCnnn`) first,
   then the other hub cables ordered by the lowest (PON NAME, PON PORT) they carry
   (`network.section_order = "first_pon_port"`); cables without PON ports follow in report order.
3. Within a section: fibres 1 … *Count* from the segment table, in fibre order, including spare fibres.

## Columns

| Column | Meaning / format | Source and rule | Status logic | Class |
|---|---|---|---|---|
| **PON NAME** | Splitter number, integer as text (`"1"`) | Hub connection of the fibre goes to splitter output port; splitter index from equipment label `PLC COUPLER <ratio> <index>` (`PON-NAME`). Format via `pon_name_format`. | CONFIRMED; blank for non-PON fibres | derived (direct) |
| **PON PORT** | Splitter output 1…64, integer | Report port − 1 (port 1 is the common input) (`PON-PORT`, `pon_port_offset`). | CONFIRMED; UNRESOLVED if port > splitter size or reused | derived |
| **FIBER #** | Absolute fibre number in the hub cable | Section enumeration; equals the `(abs)` of `TT.FF(abs)` (`FIB-NO`). | CONFIRMED | direct |
| **ADDRESS** | Premise address, or a label for non-subscriber fibres | Subscriber: text after `<tap>:<port> ` in the hub record's Usage (`ADDR-USAGE`); MDU units are part of that text. Labels: transport/spare usage text as recorded (`ADDR-LABEL`), `*-POWER PORT` → `POWER PORT`, splitter common → `PLC COUPLER <ratio> <index> COM` (`ADDR-SPLITTER-COM`), state `Spare (dark)`/`Broken` or no hub splice → `Spare (dark)` (`ADDR-SPARE`). Optional regional rewrites (`address.rewrites`). The value is never corrected by the tool. | PROVISIONAL when the same address is on several fibres (`ADDR-DUPLICATE`), the address part looks like a tap id (`ADDR-SUSPECT`), the PON usage is not `<tap>:<port> <address>` (`ADDR-NONSTANDARD`), the address has no house number (`ADDR-NO-NUMBER`, e.g. `12TH AVE AVE`: a numbered street, no house number) or downstream records of the same circuit name another premise (`ADDR-VARIANT`, e.g. hub `625 MAIN ST`, downstream `652 MAIN ST`; the drawing note says which has an address point); UNRESOLVED when a PON port has no usage (`ADDR-MISSING`). Repeated words (`AVE AVE`) give an `ADDRESS_REPEATED_WORD` warning only | direct |
| **COLOR TUBE / COLOR FIBER** | 2-letter TIA-598 code (BL OR GR BR SL WH RD BK YL VI RO AQ) | Report `Group 2` / `Fiber` colour of the hub-cable side, abbreviated (`COL-REPORT`); unspliced fibres: from fibre number (`COL-STANDARD`). Cross-checked against the colour-code position. | PROVISIONAL on mismatch with the position (`COL-MISMATCH`) | direct |
| **CABLE NAME** | `<FROM> TO <TO> FCnnn` | Cable part of `<CABLE>: SegN` (`CABLE`). | CONFIRMED | direct |
| **Fiber Tap Name** | Terminal enclosure (tap / MDU) serving the fibre | Evidence ranking: enclosure reached by the fibre trace (`TAP-TRACE`) > circuit Start/End enclosure of kind MAX10/MDU (`TAP-CIRCUIT`) > tap prefix of the Usage text (`TAP-USAGE`). For power ports the terminal enclosure. | PROVISIONAL when sources disagree (`TAP-CONFLICT`) or downstream records of the same circuit name another tap (`TAP-VARIANT`); UNRESOLVED if none | direct/derived |
| **Fiber Splice** | Closure where the fibre is spliced to the tap pigtail/drop; hub for fibres ending in the hub | See trace rules below. | see below | derived |

### Fiber Splice – trace rules (FS-*)

The fibre is followed from the hub segment by segment: at each closure the report row for
`(cable, segment, fibre)` gives the next cable/fibre; the next closure is the far end of
that segment (segment tables of all supplied reports).

**Same circuit or cut piece?** A downstream record of the same cable and fibre number is
the *same circuit* when it is live and its circuit Start/End names the hub (whatever its
usage text says). It is a *cut piece* (remnant) when its state is `Broken`, or when both
circuit ends are splice closures and neither is the hub (e.g. state `Residential`, circuit
`<closure X> → <closure Y>`): the live fibre left the cable before it, at the remnant's
circuit start/end. Only when the circuit fields do not decide is the usage text compared.

| Code | Situation | Value | Status |
|---|---|---|---|
| `FS-HUB` | Transport, splitter common, power-port fibres, on the sections named by `fiber_splice.hub_value_sections` (default: the feeder and the first distribution section that is not a pigtail) | hub | CONFIRMED |
| `FS-HUB-OMITTED` | The same fibres on later distribution sections (convention of the completed lists: 60 of 60 rows in 5 lists) | blank | CONFIRMED |
| `FS-TRACE-TERMINAL` | Trace reaches a closure whose next segment ends at the terminal enclosure (pigtail/drop) | that closure | CONFIRMED |
| bridge | Closure(s) on the path have no report, but the next downstream report lists the **same cable and fibre number carrying the same circuit** (same hub origin, or same usage) | trace continues | (no downgrade) |
| `FS-BREAK-POINT` | Trace stops at a closure without report; the next downstream record of the same fibre is a cut piece whose circuit Start/End names closure *Y* (between the stop and the record) – the fibre leaves the cable at *Y* | *Y* | PROVISIONAL (could be a branch splice, not the tap splice) |
| `FS-CABLE-END` | Trace stops at the closure where the cable ends (`… TO <X> FCnnn`) and *X* has no report | *X* | PROVISIONAL |
| `FS-TAP-CABLE` | The fibre is put, in closure *A*, on a cable named to the row's own tap (`<A> TO <tap> FCnnn`) whose far end is not recorded | *A* | PROVISIONAL |
| `FS-DROP` | Reports stop before the tap splice; a **drawn drop line** runs from the premise to the ped next to the closure (see below) | closure | PROVISIONAL |
| `FS-DRAWING` | Reports stop before the tap splice; closure located from the design drawing without a drawn drop (see below) | closure | PROVISIONAL |
| `FS-UNKNOWN` | Fibre continues past a closure without report, nothing further identifies the splice and no drawing (or no drawing candidate) | blank | UNRESOLVED (candidates listed) |
| `FS-GUIDE` | Path uses a hand-made splice guide | as traced | PROVISIONAL |
| `FS-SEG-ALIAS` | Two reports number the same span differently (matched by cable + both end closures) | as traced | PROVISIONAL |
| `FS-USAGE-VARIANT` | Downstream usage text differs on the same circuit (report revisions) | as traced | PROVISIONAL |
| `FS-CIRCUIT-CONFLICT` | Downstream record on the path carries another circuit (not from the hub) | blank | UNRESOLVED |
| `FS-TRACE-BROKEN` | Live fibre not listed in a closure report on its path | blank | UNRESOLVED |

### Fiber Splice from the design drawing (FS-DRAWING)

Used when a drawing (`.dwg` AutoCAD 2010–2018, or `.dxf`) is supplied and the reports stop
before the tap splice. All evidence is drawn objects (block names and tags in `[drawing]`):

1. **Reachable closures** – from the trace stop (or from the report-derived closure, for
   break points) along drawn fibre-cable polylines, never back along the traced route and
   never through a closure whose report does not carry the row's circuit (that report would
   show the fibre). A closure whose report does carry the circuit, on any cable, is passed.
2. **Candidates** – reachable closures whose tap enclosure (`CX1_MDU_ENCLOSURE`) is joined to
   them by a drawn pigtail, and which are not the confirmed splice closure of another tap.
3. **Fit** – first a **drawn drop line** (layer `RTE_SpatialNet_UGDROP`, as drawn by the
   FX_DROPS routine): premise address point → drop line → ped (`CX1-MAX5` / `CX1-MAX10` /
   `CX1-PED4`) → the closure nearest that ped (rule `FS-DROP`; when a second closure is
   almost as close to the ped, both stay candidates and the other evidence decides).
   Without a drawn drop: the drop symbol (`CX1-DROP`) on the line from the premise's
   address point (`FMRESADD2` / `FMCOMADD2`) to the candidate's enclosure – position along
   the line, offset from it and rotation pointing to the premise. A value already derived
   from the reports is preferred. Premises are matched on house number and street, keeping
   the direction (`S OAK` ≠ `OAK`); an address without a house number is matched
   on its text (`12TH AVE AVE` ~ number `12TH`, street `AVE`).
4. **Joint assignment** – taps competing for the same closures are assigned together, one
   tap per closure (Hungarian method plus swap search), keeping the network's fibre-order
   convention: measured on the traced rows of the run (validation region A 4,532 of
   4,603 pairs, region B 1,118 of 1,118: lower fibre numbers are spliced farther along the route).

The ranking numbers only choose between candidates; they are never reported as a
confidence. The cell is PROVISIONAL with the closure, pigtail and drop-symbol positions as
evidence, the next-best candidate in the note and the closure report that would confirm it
in *Reports to Request*. Report-derived values are kept and noted as corroborated (or get
`DRAWING_DISAGREES`). A report-derived closure is replaced only when it has **no tap
enclosure** in the drawing (the fibre must continue on a branch cable beyond it), or when a
drawn drop names a closure reachable from it (`drawn_drop_over_report_inference`).
Drawn drops are also checked against confirmed values: a drop that names another closure
gives `DRAWN_DROP_DISAGREES` and the cell becomes PROVISIONAL; a drop to a closure the fibre
cannot reach gives `DRAWN_DROP_UNREACHABLE`.

Approved overrides (`OVERRIDE`) and accepted rule policies turn values into APPROVED.

## Checks across rows

PON port reused (error), duplicate address, splitter outputs feeding fibres outside all
sections, unused splitter outputs (info), duplicate report for one closure, unreadable
reports, colour mismatches, segment conflicts between reports.

## What the reference lists did that the tool does not copy

The completed lists contain manual errors (tube colours repeating BL/OR on a 96-fibre
cable, transport fibres labelled RETURN where the report says FORWARD, missing leading
digits in house numbers, a mistyped closure prefix, leading spaces, a trailing colon
after two tap names) and one inconsistent convention (the commercial `C-` address prefix
dropped in some lists and kept in others). The tool follows the reports and reports these
differences instead of reproducing them; see docs/VALIDATION.md. The convention of leaving
Fiber Splice blank for hub-ending fibres on later distribution sections turned out to be
consistent across all five lists and is now followed (`hub_value_sections`).
