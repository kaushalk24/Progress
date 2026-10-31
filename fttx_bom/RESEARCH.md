# Technical research behind the BOM rules

This file records what external sources support each BOM rule, and what could not be verified. Every claim below either names a document that was opened in this session, or is marked **snippet only** (seen in a search-result summary, not opened) or **inference**.

## Limits of this research

- **Blocked hosts.** The session's network policy blocks the main vendor and government sites: commscope.com, raddnetwork.com, nokia.com, amt.com, ntia.gov, ecfr.gov, autodesk.com and corning.com. Only github.com, raw.githubusercontent.com and public S3 buckets could be opened.
- **To verify more,** add those hosts under Network access in the cloud environment settings and rerun the research.

The research log is kept outside the repository, because it contains local file paths. It holds one entry per claim with the URL and the category: manufacturer/standard fact, industry practice, or inference.

## 1. CommScope FOSC 450 closures and trays: used in the rules

**Source opened:** *FOSC 450 Splice Closures Ordering Guide for Closures and Accessories*, Tyco Electronics #1654571 (2004 edition; FOSC is now CommScope). The copy that was opened is a vendor-hosted PDF on S3:
`https://voomi-assets-public.s3.amazonaws.com/products/2024-08-24/voomi_COMMSCOPE_056395000FOSCACCDBASKETTALL_documents_selection_guide_c3c2810a1dcdb0c053394ebec14e0899875004.pdf`

| Finding | Use in the tool |
|---|---|
| **B tray kit:** FOSC-ACC-B-TRAY-24 (863927-000) has standard order quantity (SOQ) 2: "B-size fiber splice trays (2)", each with two SM12 modules, so 24 splices per tray. | Confirms the template's `FE0-R863927` "order 2/pkg". The tray rule is 24 splices per B tray and 2 trays per package. |
| **D tray kit:** FOSC-ACC-D-TRAY-48 (579575-000) has SOQ 2: "D-size fiber splice trays (2)". | Confirms 48 splices per D tray and 2 trays per package (`FE0-R579575`). |
| **Part code:** `FOSC450-B6-6-NT-0-B3V` / `-D6-6-NT-0-T3V`. NT means no trays and 0 means none pre-installed; B is the B basket ("limit 6 trays") and T is the Tall basket ("limit 5 trays"); 3 means 3 ground lugs; V means valved. | Trays are always ordered separately. **New rule:** D basket `FE0-R89279` = 0, because the T3V closure ships with its tall basket. The approved BOM also orders 0. |
| Tray positions with the basket in place: a 450B takes 6 trays (144 splices) and a 450D T3V takes 5 (240 splices). | **New check** CLOSURE_OVER_CAPACITY. NMK-02001G (242 splices) and NMK-03001G (255) need 6 D trays, more than the 2004 guide allows for a T3V. The message asks the user to verify the closure configuration. The current CommScope datasheets could not be opened, so this is a WARN. |
| Grounded closures include the hardware to bond shielded cable to their 3 ground lugs. Separate kits exist only for bonding cables in common (FOSC-ACC-450-COMMON-GRD). | Closures need no separate ground kit. The ground wire kit line is for the **peds** (see section 5). |

## 2. LibreDWG and ezdxf: limits of DWG extraction

All primary sources opened on raw.githubusercontent.com:

| Source | Finding | Use in the tool |
|---|---|---|
| LibreDWG `README` | It reads all DWG versions (R2018 included), but "some very advanced R2010+ objects fail to read and are skipped over"; writing R2010–R2018 gives CRC errors. | The tool reads only and never writes a DWG. The LibreDWG read status and a per-type entity census go into the audit, so skipped objects are visible. |
| LibreDWG `src/classes.inc` | Stable classes: MULTILEADER, FIELD. Unstable: dynamic-block parameters, BLOCKREPRESENTATION, PROXY_OBJECT, ACAD_TABLE. Unhandled: AECC_* (Civil 3D). | Quantities come from block names and attributes, not from dynamic-block visibility states or DWG tables. The SpatialNet LWPolygons, which are proxies, are decoded from their proxy graphics (`extract/proxy.py`). |
| LibreDWG `NEWS` | 0.14.1 fixes heap overflows in the R2004/R2007 decoders. | **Open action:** the pinned WASM build (`@mlightcad/libredwg-web@0.8.0`) should be checked against the LibreDWG version it bundles. |
| ezdxf `acad_proxy_entity.rst` and `proxygraphic.py` | Only the proxy graphic of a proxy entity can be read, and unsupported primitives are logged at debug level only. | The DXF route can return partial Non-Grant geometry with no error. The deep check reports Non-Grant polygon counts and tiny polygons. |
| ezdxf `odafc.py` | ODA File Converter command line: `ODAFileConverter in out ACAD2018 DXF 0 0`. | This is the documented fallback for producing a DXF (README). |

## 3. Splice slack: not used for quantities

- **Opened:** two construction specifications on S3, a federal operations-and-maintenance spec and a 2021 Virginia broadband RFP. Neither gives an OSP slack-loop length. The RFP prices fiber "including slack in each vault" per foot. This supports the tool's model: cable design length = route + slack, taken from the label `TOTAL = FTG + SLK`.
- **Snippet only:**
  - FOA: 30–60 ft at splice ends, and slack adds about 2%.
  - A USAC E-rate specification: 30 ft per handhole.
- **Conclusion:** slack is a design parameter that the designer puts on the label. The tool reads it and doesn't invent it.

## 4. BEAD Grant / Non-Grant cost split: method is not prescribed

- **Opened:** Texas BEAD Initial Proposal Vol. II and the Final Proposal draft (on S3). Projects are compared by cost per location and cost per route mile, but no allocation key for shared plant is given.
- **Snippet only:** NTIA BEAD FAQs (v18, v21) and the Final Proposal guidance. Shared costs must be allocated by "standard cost allocation practices", with a pro-rated share, under 2 CFR 200.405.
- **Conclusion:** no source prescribes splitting by passings or by footage.
  - The tool splits by **location**: dedicated items by where they are, cable by routed spans.
  - The Credit River BOM matches this on 292 of 360 cells.
  - Forensic test F4 (FORENSIC_FINDINGS.md) rejected allocation by passings carried, with 86,323 ft error against 2,497 ft for the span method.
  - The method used is recorded in the audit's *Policies* sheet.

## 5. Pedestal grounding: no public rule, so the customer's template note is used

- **Snippet only:** pedestal vendors pre-install a bonding plate. The NEC 770.100 practice is to bond cable armor where it is opened.
- **No public estimating rule was found.**
- **Rule used:** the customer's own blank template note on FE0-07264810: "Hand count for grounds: all splices with letter G at end, first in line, any ending in a zero, and also EOL peds". It is a customer specification, which ranks above general practice.

## 6. Pedestals (RaDD MAX5 / MAX10) and OLM (Nokia SF-8M): not verifiable

- **Blocked.** Snippets describe the MAX10's mid-span backplane options.
- **Not found anywhere:** the part numbers MAX5DSM24, MAX10DSM24 and MAX10EXP4, and the +4 kit rules.
- **The template's descriptions remain the only source:** "M Peds Stock 4 upgrade to 8".
- **SF-8M (snippet only):** 8 PON cages, coax / AC / DC / RFT-V power. Licensing and bundled optics were not found.

## 7. Split ratios: consistent with the design

- **Snippet only:**
  - 1:32 loses about 17–18 dB and 1:64 about 20.5–21.5 dB.
  - The XGS-PON N1 budget is 29 dB.
- **Inference:** one PON port, one SFP+ and one splitter per tree. This is consistent with the SME's SFP rule and with the designed splitter counts the tool uses.

## Research findings that changed the code

| Finding | Change |
|---|---|
| T3V includes the tall basket | Rule FE0-R89279 = 0 (VERIFIED; the reference is 0) |
| 2 trays per package, 24 or 48 splices per tray | Confirms the existing tray rule; the source is now cited in the code |
| Tray limit per closure | New WARN CLOSURE_OVER_CAPACITY |
| LibreDWG skips some R2010+ objects without warning | Reader status and census already surfaced; the version check is listed as an open action |
| No prescribed BEAD split | Location-based split kept; the method is recorded in the audit |
