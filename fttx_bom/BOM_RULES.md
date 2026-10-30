# BOM rules (reverse-engineered from the Credit River NMK-R02..R05 BOM)

Machine-readable catalogue: `config/bom_rules.json`. Drawing conventions:
`config/conventions.json`. Investigated reference differences:
`config/investigations.json`. Column = network x {Grant, Non-Grant}.

## Classification

| Rule | Basis | Status |
|---|---|---|
| Network | Closed boundary polygons on `OLM Boundary - Designed Not Built` / `Boundary - Fiber Service Group`, named by the `NMK-R0x` / `DMI-R15 15f` label inside. | VERIFIED |
| Transport corridor | Objects inside `Transport Boundary - Designed Not Built` belong to the network fed by the OTN transport cable (the B end of `...OTN TO NMK-04034`). The reference books the corridor vault and transport cable to R04. | VERIFIED |
| Non-Grant area | Every polygon on `Boundary - Designed Not Built` (SpatialNet proxy LWPolygons decoded from proxy graphics, plus LWPOLYLINEs), except ones labelled as network or transport boundaries. Unlabelled polygons count too: this was needed to reproduce the commercial/MDU splits. | VERIFIED |
| Grant classification of infrastructure | By **location** (insertion point inside or outside the Non-Grant polygons). A service-based alternative (by addresses served) was tested and rejected: R02 MAX10 gave 24/35 vs 55/4 in the reference. | VERIFIED |

## Quantities

| BOM line | Formula | Evidence vs reference |
|---|---|---|
| Total passings per network | Served rows in the address list (PON + port, not POWER PORT) | 229 / 246 / 216 / 189, all exact |
| Residential | Total - commercial - MDU. Grant = `FMRESADD2` blocks on `GRANTADDRESS` that match a served address (token prefix, ignoring `C-` and N/S/E/W) | 8/8 cells exact |
| Commercial | ΣCC (`CX1-COMCNT`) + unused MDUC - MDU units carried by CC blocks. Grant = `FMCOMADD2` outside Non-Grant | 8/8 exact |
| MDU | Σ`FMMULTIADD` (RESIDENTIAL_COUNT + COMMERCIAL_COUNT), split by location | 8/8 exact |
| Cross-check | ΣHC + ΣCC + ΣMDUC must equal the address list; the address list wins and a warning is raised | NMK exact; DMI 223 vs 222 (duplicate "2023 60TH" block) |
| MAX10 / MAX5 peds | Count of `CX1-MAX10` / `CX1-MAX5` | Network totals exact; split 9/16 cells exact |
| Vault `CBV-HGIB2436` | Count of `CX1-VAULT` | Totals exact; 7/8 cells |
| Bonding jumper, ped kit, ped trays | Template formulas: (MAX10 + MAX5) x 2 / x 1 / x 1 | Recalculated 1706 / 853 / 853 |
| Fiber cable FCnnn | Σ `fiberinfo.dwg` TOTAL (= FTG route + SLK slack, equals the splice-report "Cable Design Length"), plus cables found only in splice reports (100 ft OLM->xx001G tails) | 15/17 network totals exact; 2 are reference errors (see below) |
| Cable Grant/Non-Grant | Route each segment through the cable polylines (graph shortest path from A to B splice), split at splices and structures, classify each span by majority area, then apportion TOTAL by span length | 11/16 exact cell pairs (R03 FC048 exact) |
| FOSC 450A-D | Splice reports `Enclosure Type`, area by splice location | Totals exact; 1 cell differs (NMK-05131 is 23 ft from an edge) |
| Splitter 1x32 / 1x64 | Ratio from splice-report `PLC COUPLER` rows (fallback: address list). Network = ROUNDUP(passings/ratio). Grant = ROUNDUP(grant/ratio); Non-Grant = rest | 8/8 exact; matches report coupler count and address-list PONs |
| XGS SFP+ | ROUNDUP(column passings / ratio) per column | 8/8 exact (gives 18 SFP for 15 PONs; flagged) |
| MDU enclosure | 1 per `FMMULTIADD` building | exact |
| OLM bundle, XM3.1 PSU, battery kit | 1 per `CX1_OLM`; Z-14 ped + ground enclosure + pedestal support per ground OLM; pole enclosure per aerial OLM (within 15 ft of an aerial pole) | exact |
| Batteries | 3 x OLM (3-battery enclosure) | exact |
| Transport BOM rows | 1 per OLM, in the OLM's column | exact |
| Jumper Calculator | Houses passed per column (sheet formulas do the rest) | 930/64/8/32/3 identical |
| Route miles / UG / aerial footage | Σ `CX1-FTG-N2` FTG labels on `RTE_UGTRENCH` / `RTE_AESTRAND` | INFERRED. Reference rows 6-10 are typed in and use a different method per network. |

## Not reproducible from the supplied data (left blank, flagged)

* **Drop footage**: `CX1-DROP` FTG attributes are blank; no drop length source.
* **450B / 450D trays**: no consistent splices-per-tray rule (see the investigations file).
* **MAX10 +4 upgrade kits**: engineer decision; no drawing attribute.
* **Ground wire kits, heat shrink**: the reference left them blank. The audit shows counts as SUGGESTED.
* **GOAT peds, peds-with-tap, FTP/FST/MST/OTE taps, plenum lateral**: no symbol in these designs.

## Reference BOM errors / inconsistencies found

1. NMK-R04 FC024/FC048: the reference moves 5,187 ft from 24 ct to 48 ct. The drawing labels and splice reports agree with each other (FC024 = 34,586 + 100).
2. The OLM tail (100 ft FC024) is counted for R02/R03 but omitted for R04/R05.
3. UG footage (row 10) is computed four different ways across the four networks.
4. Drop footage rows are hand-typed "total - x" values with no traceable source.
