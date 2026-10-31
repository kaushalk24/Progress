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

## Design scope and confidence (0.7.0)

| Rule | Basis |
|---|---|
| A splice point within 35 ft of an MST terminal (and nearer than any MAX ped) belongs to another fiber network | DMF-R04: DMF-04002…04025 |
| A cable ending at such a splice, or at an HFC node (CX1_NODE tag), belongs to another network | DMF-R04: FC144, FC072, FC024 excluded |
| A vault or L-box counts only within 40 ft of this design's cable routes or 50 ft of its splices, and not when another network's route is nearer | DMF-R04: 7 vaults kept, 1 L-box excluded; NMK/DMI unchanged |
| A trench label is RF when coax is within 40 ft and none of this design's fiber is within 75 ft; it is foreign when another network's fiber is nearer | NMK R04 −684 ft; DMF 12 RF and 27 foreign labels |
| A count block is not this design's when an HFC pedestal, MST or RF tap is its nearest housing | DMF: 300+ in the boundary, 18 kept |
| Cable split: span by span, each in the area of the ped or splice it feeds | Design standard; NMK error −26% |
| A pedestal or vault on the Non-Grant boundary (< 5 ft inside) counts as Grant | Design standard |
| Every written cell is rated low / review and highlighted | `excel/confidence.py` |
| A design warning marks only the cells it can change (cable: its fiber count; address layer: residential count, plus splitters or SFP only when the count would change) | `excel/confidence.py` |
| A cable without a traced route is marked only when its label and two ends are not all in one area | `CableSegment.split_uncertain` |
| Route footage and splice-tray rows follow the design standard (CalcFTG labels; ROUNDUP(splices/24 or /48), packages of 2) and are rated VERIFIED | `config/bom_rules.json` |

## Grant / Non-Grant rule (design standard) and where it applies

**Rule:** Non-Grant = everything inside the Non-Grant boundaries; Grant = total − Non-Grant.

| Line | How the rule is applied | Evidence |
|---|---|---|
| Peds, vaults, closures, OLM equipment | By location; each object is either inside or outside | Both BOMs; differences are a few objects near edited edges |
| Cables | Routed spans, each in the area of the ped / splice it feeds; Grant = TOTAL − Non-Grant spans | Design standard; NMK absolute error 19,366 ft (span majority 26,142) |
| Route footage (rows 6–10) | Route labels inside the Non-Grant polygons; Grant = rest | CalcFTG method |
| XGS SFP+ | Per column ROUNDUP(Jumper Calculator splitters required / 2) | Design standard; Credit River 8/8 |
| Drops | Non-Grant = drops of Non-Grant addresses; Grant = total − Non-Grant | design standard; the approved BOMs differ (policy `drop_columns`) |
| **Exception: splitters** | Grant = ROUNDUP(grant passings / ratio); Non-Grant = designed − Grant | Both approved BOMs |
| **Exception: passings** | Grant = served addresses on GRANTADDRESS; Non-Grant = total − Grant | Both approved BOMs; the deep check lists addresses whose layer and boundary disagree |

## RF (coax) plant: not calculated (design standard)

- **Vaults and L-boxes:** one is RF support when an RF device is within 50 ft and no fiber splice is within 100 ft. RF devices are the DES_AMPS / TAPS / EOL / TERM / SPLITS blocks and CX1_TRIPAM / HGDULA.
  - RF power supplies are not evidence: the coax-powered OLM hub vault sits beside one.
  - DMI-R15: vault 3CC8B7 at the amplifier is excluded.
- **Aerial strand** counts only where an aerial fiber cable is within 75 ft. DMI-R15: the 512 ft of RF strand is excluded.
- **Trench with no fiber cable within 200 ft** is still counted, because the Credit River BOM counts such trench. It is listed (INFO TRENCH_NO_FIBER), and the policy `route_footage=fiber_bearing` removes it.
- **RF taps, amplifiers, power supplies and anchors** are never FTTH materials (they are in `ignore_blocks`).

## Quantities

| BOM line | Formula | Evidence vs reference |
|---|---|---|
| Total passings per network | Served rows in the address list (PON + port, not POWER PORT) | 229 / 246 / 216 / 189, all exact |
| Residential | Total - commercial - MDU. Grant = `FMRESADD2` blocks on `GRANTADDRESS` that match a served address (token prefix, ignoring `C-` and N/S/E/W) | 8/8 cells exact |
| Commercial | ΣCC (`CX1-COMCNT`) + unused MDUC - MDU units carried by CC blocks. Grant = `FMCOMADD2` outside Non-Grant | 8/8 exact |
| MDU | Σ`FMMULTIADD` (RESIDENTIAL_COUNT + COMMERCIAL_COUNT), split by location | 8/8 exact |
| Cross-check | ΣHC + ΣCC + ΣMDUC must equal the address list; the address list wins and a warning is raised | NMK exact; DMI 223 vs 222 (duplicate "2023 60TH" block) |
| MAX10 / MAX5 peds | Count of `CX1-MAX10` / `CX1-MAX5` | Network totals 8/8 exact; cells MAX10 6/8, MAX5 0/8 (off by 2-8 peds near Non-Grant edges) |
| Vault `CBV-HGIB2436` | Count of `CX1-VAULT` | Totals 4/4; cells 6/8 (one R05 vault) |
| Bonding jumper, ped kit, ped trays | Template formulas: (MAX10 + MAX5) x 2 / x 1 / x 1 | Recalculated 1706 / 853 / 853 |
| Fiber cable FCnnn | Σ `fiberinfo.dwg` TOTAL (= FTG route + SLK slack, equals the splice-report "Cable Design Length"), plus cables found only in splice reports (100 ft OLM->xx001G tails) | Network totals 17/20 exact (FC024 R04/R05 and FC048 R04 are reference errors - see below) |
| Cable Grant/Non-Grant | Route each segment through the cable polylines (graph shortest path from A to B splice), split at splices and structures, classify each span by majority area, then apportion TOTAL by span length | Cells: FC072/FC144 8/8, FC048 6/8, FC096 4/8, FC024 0/8 (all within a few spans; R03 FC048 exact) |
| FOSC 450A-D | Splice reports `Enclosure Type`, area by splice location | Totals 4/4; 450B cells 6/8 (NMK-05131 is 23 ft from an edge), 450D 8/8 |
| Splitter 1x32 / 1x64 | Ratio from splice-report `PLC COUPLER` rows (fallback: address list). Network = ROUNDUP(passings/ratio). Grant = ROUNDUP(grant/ratio); Non-Grant = rest | 8/8 exact; matches report coupler count and address-list PONs |
| XGS SFP+ | ROUNDUP(ROUNDUP(column passings/32)/2) per column (design standard: Jumper Calculator / 2; superseded the 0.1 rule) | 8/8 exact (18 SFP for 15 PONs; flagged) |
| MDU enclosure | 1 per `FMMULTIADD` building | exact |
| OLM bundle, XM3.1 PSU, battery kit | 1 per `CX1_OLM`; Z-14 ped + ground enclosure + pedestal support per ground OLM; pole enclosure per aerial OLM (within 15 ft of an aerial pole) | exact |
| Batteries | 3 x OLM (3-battery enclosure) | exact |
| Transport BOM rows | 1 per OLM, in the OLM's column | exact |
| Jumper Calculator | Houses passed per column (sheet formulas do the rest) | 930/64/8/32/3 identical |
| Route miles / UG / aerial footage | Σ `CX1-FTG-N2` FTG labels on `RTE_UGTRENCH` / `RTE_AESTRAND` | INFERRED. Reference rows 6-10 are typed in and use a different method per network. |

## Rules added from the AutoCAD routines and the design standard (0.3.0)

| BOM line | Rule | Evidence |
|---|---|---|
| Total Drop Footage | Sum of FX_DROPS drop lines (`RTE_SpatialNet_UGDROP`, ped box edge to the address PED 6.6 ft off the address, `CX1-FTG-N2` label rounded to the nearest foot). The area follows the served address. The row carries Non-Grant only, matching the reference "total - grant". | R03 0.14% off; DMI 222 drops / 36,117 ft = labels |
| Route footage (rows 6-10) | `CalcFTG.lsp`: sum of `CX1-FTG-N2` FTG on `RTE_UGTRENCH` (or `GRANT FTG` / `NON-GRANT FTG`) inside the boundary | R02/R03/R05 network totals exact |
| 450B/450D trays | Trays per location ROUNDUP(fusion splices / 24 or 48); packages = ROUNDUP(sum of trays / 2) per column | 6 of 7 reference network totals |
| MAX10 +4 upgrade | One kit per 4 passings a MAX ped feeds above 4 (none in these designs) | No ped feeds more than 2 |
| SFP | ROUNDUP(ROUNDUP(passings/32)/2) per column (design standard: Jumper Calculator / 2) | 8/8 |
| Splitters | Designed count (splice reports). Grant = ROUNDUP(grant/ratio), the rest Non-Grant (design standard). The template's per-column ROUNDUP(/64) is overridden. | 8/8 |
| OLM equipment | Grant column unless the OLM has no grant passings (design standard) | 8/8 |

## Rules added by the forensic review (0.5.0)

| BOM line / check | Rule | Evidence | Status |
|---|---|---|---|
| Ground wire kit FE0-07264810 | One kit per splice location that meets any of the template note's conditions, counted once:<br>• the name ends in G;<br>• it is the first splice point on the routed path of each cable leaving the OLM hub (the splice point nearest the OLM block);<br>• the name ends in 0;<br>• it is an end of line (a cable ends there and none starts there). | Blank template L27: "Hand count for Grounds All splices with letter G at End, First in line, any ending in a zero, and also EOL Peds". NMK: 321 (R02 70, R03 85, R04 87, R05 79); DMI 126. G and end of line coincide for 243 of the 248 G splices in NMK. The Credit River reference (older template, no note) left the line blank. | INFERRED (customer note). Policy `ground_kits`: template_note / g_suffix / not_ordered |
| D basket FE0-R89279 | 0. The FOSC450-D6-6-NT-0-T3V closure ships with its tall basket. | Part code ("T") from the CommScope ordering guide; the reference orders 0 | VERIFIED |
| Closure capacity | WARN when one location needs more trays than a FOSC 450 holds with its basket (450B 6, 450D T3V 5) | Ordering guide (2004 edition); NMK-02001G and 03001G need 6 D trays | Design check |
| Ped size against cable | WARN when a MAX5 houses a splice on a cable above 48F (any role). INFO for a MAX10 at a mid-span or end splice on a cable of 48F or less. The splice goes to its nearest housing; FOSC-closure splices are excluded. | NMK and DMI: 0 MAX5 on a cable above 48F; MAX10 mid-span on a cable above 48F: 113 and 11 | Design check |
| Cross-network cable | Booked wholly to its A-end network; INFO CABLE_CROSS_NETWORK | Network totals agree with the reference with this convention | VERIFIED_TOTAL |
| Per-OLM job on a combined drawing | Other networks' labelled boundaries are excluded, not nearest-assigned. The transport corridor belongs to the OTN-fed network only. | Single-OLM runs equal the combined run on every cell (regression test) | VERIFIED |

## DWG → BOM chains (how each quantity is derived)

**MAX10 / MAX5 peds (CBP-MAX10DSM24, CBP-MAX5DSM24)**
1. `CX1-MAX10` / `CX1-MAX5` block inserts.
2. One ped per insert; its network is the boundary that contains it, and its column is Grant/Non-Grant by location.
3. The bonding jumper (×2), the ped bonding kit (×1) and the ped splice tray (×1) follow from template formulas.

**Fiber cable (FFA-F9xx)**
1. `fiberinfo.dwg` labels: SEGNUM "A TO B FCnnn", plus FTG / SLK / TOTAL / TTL / REQ.
2. One labelled segment per cable, with design length TOTAL = route + slack (equal to the splice report's Cable Design Length).
3. The segment belongs to the network of its A end.
4. It is routed through the cable polylines from splice A to splice B and split at every splice or structure; each span goes to its majority area.
5. TOTAL is apportioned by span length. Cables found only in a splice report (the 100 ft OLM tails) are added and flagged.

**FOSC 450 B/D closures and trays**
1. The splice report's Enclosure Type (FOSC 450 A–D; SPLICE CASE is not a closure line).
2. One closure per report; its column is the location of the MC_SPLICE point.
3. Trays per location = ROUNDUP(fusion splices / 24 for B, or / 48 for D).
4. Packages = ROUNDUP(column trays / 2), because each kit holds 2 trays.

**Splitters and SFP**
1. PLC COUPLER rows in the splice reports.
2. Ratio and designed count; a second ratio is written from its designed count.
3. Grant = ROUNDUP(grant passings / ratio); Non-Grant = the rest.
4. SFP per column = ROUNDUP(ROUNDUP(passings / 32) / 2), the Jumper Calculator divided by 2.

**Passings**
1. Address-list served rows give the network total.
2. HC / CC / MDUC count blocks give the category split.
3. GRANTADDRESS `FMRESADD2` blocks that match a served address give Grant residential.
4. Commercial and MDU are Grant when outside the Non-Grant polygons.

**Ground wire kits**
1. MC_SPLICE names and the cable topology.
2. The template note's conditions (see the table above).
3. One kit per qualifying location.

**Drops**
1. FX_DROPS lines on `RTE_SpatialNet_UGDROP` with their CX1-FTG-N2 labels.
2. The footage follows the served address's area; the row carries Non-Grant only.

**Route footage**
1. `CX1-FTG-N2` FTG labels on `RTE_UGTRENCH` / `RTE_AESTRAND` (as CalcFTG does) inside the boundary.
2. Rows 6–10 are filled from them.

## Not reproducible from the supplied data (left blank, flagged)

* **Heat-shrink sleeves:** the design standard says they aren't updated in the BOM; the audit shows the fusion-splice count.
* **GOAT peds, peds with taps, FTP/FST/MST/OTE taps, plenum lateral:** these designs have no symbol for them.
* **Route Grant/Non-Grant split (rows 6–10):** point, window and trench-length methods all fail to reproduce the reference; see FORENSIC_FINDINGS.md F6.

## Reference BOM errors / inconsistencies found

1. NMK-R04 FC024/FC048: the reference moves 5,187 ft from 24 ct to 48 ct. The drawing labels and splice reports agree with each other (FC024 = 34,586 + 100).
2. The OLM tail (100 ft FC024) is counted for R02/R03 but omitted for R04/R05.
3. UG footage (row 10) is computed four different ways across the four networks.
4. Drop footage rows are hand-typed "total - x" values with no traceable source.
