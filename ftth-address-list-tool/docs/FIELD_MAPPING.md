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
| **ADDRESS** | Premise address, or a label for non-subscriber fibres | Subscriber: text after `<tap>:<port> ` in the hub record's Usage (`ADDR-USAGE`); MDU units are part of that text. Labels: transport/spare usage text as recorded (`ADDR-LABEL`), `*-POWER PORT` → `POWER PORT`, splitter common → `PLC COUPLER <ratio> <index> COM` (`ADDR-SPLITTER-COM`), state `Spare (dark)`/`Broken` or no hub splice → `Spare (dark)` (`ADDR-SPARE`). Optional regional rewrites (`address.rewrites`). | PROVISIONAL when the same address is on several fibres (`ADDR-DUPLICATE`), the address part looks like a tap id (`ADDR-SUSPECT`), the PON usage is not `<tap>:<port> <address>` (`ADDR-NONSTANDARD`) or downstream reports name the same premise differently; UNRESOLVED when a PON port has no usage (`ADDR-MISSING`) | direct |
| **COLOR TUBE / COLOR FIBER** | 2-letter TIA-598 code (BL OR GR BR SL WH RD BK YL VI RO AQ) | Report `Group 2` / `Fiber` colour of the hub-cable side, abbreviated (`COL-REPORT`); unspliced fibres: from fibre number (`COL-STANDARD`). Cross-checked against the colour-code position. | PROVISIONAL on mismatch with the position (`COL-MISMATCH`) | direct |
| **CABLE NAME** | `<FROM> TO <TO> FCnnn` | Cable part of `<CABLE>: SegN` (`CABLE`). | CONFIRMED | direct |
| **Fiber Tap Name** | Terminal enclosure (tap / MDU) serving the fibre | Evidence ranking: enclosure reached by the fibre trace (`TAP-TRACE`) > circuit Start/End enclosure of kind MAX10/MDU (`TAP-CIRCUIT`) > tap prefix of the Usage text (`TAP-USAGE`). For power ports the terminal enclosure. | PROVISIONAL when sources disagree (`TAP-CONFLICT`); UNRESOLVED if none | direct/derived |
| **Fiber Splice** | Closure where the fibre is spliced to the tap pigtail/drop; hub for fibres ending in the hub | See trace rules below. | see below | derived |

### Fiber Splice – trace rules (FS-*)

The fibre is followed from the hub segment by segment: at each closure the report row for
`(cable, segment, fibre)` gives the next cable/fibre; the next closure is the far end of
that segment (segment tables of all supplied reports).

| Code | Situation | Value | Status |
|---|---|---|---|
| `FS-HUB` | Transport, splitter common, power-port fibres | hub | CONFIRMED |
| `FS-TRACE-TERMINAL` | Trace reaches a closure whose next segment ends at the terminal enclosure (pigtail/drop) | that closure | CONFIRMED |
| bridge | Closure(s) on the path have no report, but the next downstream report lists the **same cable and fibre number with the same circuit usage** | trace continues | (no downgrade) |
| `FS-BREAK-POINT` | Trace stops at a closure without report; the next downstream record of the same fibre is `Broken` and its circuit Start/End names closure *Y* (between the stop and the record) – the fibre leaves the cable at *Y* | *Y* | PROVISIONAL (could be a branch splice, not the tap splice) |
| `FS-CABLE-END` | Trace stops at the closure where the cable ends (`… TO <X> FCnnn`) and *X* has no report | *X* | PROVISIONAL |
| `FS-UNKNOWN` | Fibre continues past a closure without report and nothing further identifies the splice | blank | UNRESOLVED (candidates listed) |
| `FS-GUIDE` | Path uses a hand-made splice guide | as traced | PROVISIONAL |
| `FS-SEG-ALIAS` | Two reports number the same span differently (matched by cable + both end closures) | as traced | PROVISIONAL |
| `FS-USAGE-VARIANT` | Downstream usage differs only in text (same tap port and house numbers) – report revisions | as traced | PROVISIONAL |
| `FS-CIRCUIT-CONFLICT` | Downstream record on the path carries another circuit | blank | UNRESOLVED |
| `FS-TRACE-BROKEN` | Live fibre not listed in a closure report on its path | blank | UNRESOLVED |

Approved overrides (`OVERRIDE`) and accepted rule policies turn values into APPROVED.

## Checks across rows

PON port reused (error), duplicate address, splitter outputs feeding fibres outside all
sections, unused splitter outputs (info), duplicate report for one closure, unreadable
reports, colour mismatches, segment conflicts between reports.

## What the reference lists did that the tool does not copy

The completed lists contain manual errors (tube colours repeating BL/OR on a 96-fibre
cable, transport fibres labelled RETURN where the report says FORWARD, missing leading
digits in house numbers, a mistyped closure prefix, leading spaces) and inconsistent
conventions (the commercial `C-` address prefix dropped in some lists and kept in
others; Fiber Splice left blank for transport fibres on some cables only). The tool
follows the reports and reports these differences instead of reproducing them; see
docs/VALIDATION.md.
