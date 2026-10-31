# BOM design standards

These are the rules the tool applies to every line of the OLM BOM template, one network (OLM) per BOM. Each rule shows how the quantity is derived and how it is split between Grant and Non-Grant.

## Grant / Non-Grant

- **Non-Grant** is whatever lies inside the Non-Grant boundaries.
- **Grant** is the network total minus Non-Grant.
- **OLM equipment** (Z-14 ped, OLM bundle, power supply, enclosures, batteries) is booked to Grant, 1 per OLM. When the whole OLM area is Non-Grant, it all moves to Non-Grant.

## Scope: what belongs to this design

- **This design** uses MAX5 and MAX10 pedestals with fiber bulkheads. Fiber taps (FTP/MST/OTE) are not used; the only tap-type enclosure is the MDU enclosure.
- **Only proposed plant is counted.** Existing structures are not counted.
- **Not counted:**
  - HFC (coax) plant: amplifiers, taps, power supplies, RF pedestals, coax strand and trench, and their vaults;
  - fiber networks designed by others: MST terminals and the splices, cables, trench and structures on their routes.

  Each excluded object is listed in the audit with its reason.

## Line by line

| Section | BOM line | Standard |
|---|---|---|
| Footage | Total route mileage, UG and aerial footage | Fiber-drafting route length: CX1-FTG-N2 labels on the trench / strand layers inside the boundary (as the CalcFTG routine). Strand counts only where fiber is lashed to it. |
| Footage | Total drop footage | FX_DROPS drop lines (ped edge to the address PED, rounded to the foot). Not counted in the route rows. |
| Passings | Residential, commercial, MDU | Served addresses from the address list. Grant = served addresses on the GRANTADDRESS layer (commercial / MDU: outside the Non-Grant boundaries). |
| UG structures | Z-14 OLM ped | 1 per OLM, in Grant. |
| UG structures | MAX10 / MAX5 peds | Count of pedestals inside the OLM boundary, split by location. |
| UG structures | Vaults | Count of new vaults on the routes of this design, any size, split by location. |
| UG structures | Bonding jumper, ped bonding kit, ped splice tray | Template formulas (2, 1 and 1 per ped). Inconsistent template formulas are repaired from the first area column. |
| UG structures | MAX10 +4 upgrade | Template formula: one kit per Non-Grant MAX10. |
| Fiber cable | 24 ... 288 count | Cable design length (route + slack loops = splice-report design length), split by where the cable runs, slack included at its location. Totals per fiber count must equal the splice-report design length. |
| Splice cases | FOSC 450B / 450D | From the splice reports' enclosure type, by splice location. |
| Splice trays | 450B / 450D trays | Closures ship without trays. Per splice location, trays = ROUNDUP(splices / 24 for 450B or / 48 for 450D), counting every splice (homes, power port, transport fibers, splitter legs). Packages = ROUNDUP(trays / 2), because each package holds 2 trays and a spare tray can serve another location. |
| Splice trays | D basket | 0. The T3V 450D ships with its basket. |
| Not updated | Burns and heat shrink, ONU, ground wire kits | Left blank. The audit shows the counts. |
| OLM equipment | OLM bundle | 1 per OLM, Grant. |
| OLM equipment | XGS SFP+ | Per column: ROUNDUP(Jumper Calculator "Splitters Required" / 2), whatever splitter is used. |
| OLM equipment | Splitters | Designed count. Grant = ROUNDUP(grant passings / split ratio); the rest are Non-Grant. |
| Power supply | XM3.1, enclosures, battery kit, batteries | 1 per OLM (3 batteries), Grant. Pole or ground mount follows the OLM location. |
| Transport BOM, Jumper Calculator | — | Per-area inputs only; the sheet formulas do the rest. |

## AutoCAD routines the BOM depends on

- **FX_DROPS (FXAUTO, FXMISSING)** must be run and saved before the BOM. It draws one drop line per served address on `RTE_SpatialNet_UGDROP`, with its footage label.
- **CalcFTG** sums the route-footage labels inside a selected boundary. The tool does the same with the OLM boundary and the Non-Grant polygons.

## Template

One OLM per BOM, using the blank template's area columns. Template formulas are preserved. Formulas that are inconsistent across area columns are repaired and listed in the audit.

## Related deliverable (separate)

The grant address validation report (grant and non-grant addresses, field-verified differences, remarks) is a separate deliverable and not produced by this tool.
