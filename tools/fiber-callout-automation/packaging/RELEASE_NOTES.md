## FiberCallout Studio 2.2.0 (Windows x64)

Single-file desktop app that generates the magenta **DES_FIBER_SPL** fiber-number and BFO callouts of an FTTx design
from its splice reports and address lists.

**Install:** download `FiberCalloutStudio.exe` (or the zip) and run it. You don't need Python, AutoCAD or anything
else. The exe isn't code-signed, so if Windows SmartScreen appears, click *More info -> Run anyway*.

**Check the installation:** *Help -> Run self-test* (or `FiberCalloutStudio.exe --selftest`).

What's new in 2.2
- **BFO callouts only at cable junctions.** A closure gets BFO callouts only where 3 or more cable segments meet
  (for example 72F in, 24F + 48F out, or a 144F passing through with a 24F branch). Pigtails and short terminal
  tails don't count. Pass-through closures (one cable in, one out) no longer get a BFO callout, even where the cable
  tapers. On Credit River this leaves out exactly the 2 pass-through closures that have no BFO in the reference.
- **Clear** button (Ctrl+N) empties the drawing, the data list and the results to start the next region. The Delete
  key removes the selected list items. Adding a region folder that contains exactly one drawing fills in the drawing
  field.
- **Every input format reads the same.** `.xlsx`, `.xlsm`, `.xls`, `.csv` and tab-delimited `.txt` (including
  Excel's "Unicode Text") give identical callouts. CSV encoding (UTF-8, UTF-8 BOM, UTF-16, Windows-1252), delimiter
  (comma, semicolon, tab, pipe), comma decimals, Excel's `sep=` line and `="00123"` cells are handled.
- **Copy/paste at the right size.** The callouts DXF now carries the design's own drawing units (`$INSUNITS`, also
  read from DWG files), so AutoCAD doesn't rescale the callouts on PASTEORIG. A design whose units are set to
  inches (the AutoCAD template default, as in Credit River) is treated as feet. Before this fix, a DXF design with
  units set to inches got callouts 12x too large.
- Fixes:
  - `.xlsx` files whose stored used range is wrong were read as a single row; they're now read in full.
  - Hidden sheets are skipped.
  - Splice reports saved as `.txt` were ignored; they're now read.
  - A splice report without a "Splice name" row now takes the closure name from its file name.
  - Segment ends written like `NMK-02001G (HH 12)` are now recognised.
  - Identical rows repeated across address lists are merged instead of being reported as duplicate-number errors.
  - A non-address sheet in an address workbook is skipped instead of raising an error.
  - A missing closure is reported once.
  - Control characters in the input can no longer break the QA workbook.
  - The DWG reader now also reads 3D polylines, which GIS exports often use for cables.

What's new in 2.1
- Two-step interface: **Inputs** (drawing, one list for all splice reports and address lists, output folder) and
  **Results**. Removed the column-mapping, CAD-mapping and callout-style pages. Removed the existing-callouts, DWG
  reader, ODA File Converter, DWG output and drawing-units options. Everything is detected from the files on every run.
- Output is always a **callouts DXF** at the drawing's own coordinates plus the QA/QC workbook. In AutoCAD, open the
  DXF, press Ctrl+A then Ctrl+C, switch to the design and type PASTEORIG.
- Splice reports and address lists can be mixed in one list. They're told apart automatically and duplicate files
  are ignored.
- Generate after Validate reuses the analysis when the inputs haven't changed.
- Fixes: DWG dynamic (anonymous `*U`) closure and handhole blocks are now resolved to their block family.
  Closure-name attributes with extra text around the name are now matched. An existing callout in the drawing no
  longer pushes the new callouts aside. Splice reports placed with the address lists no longer raise false
  "address list" errors.

Highlights
- Reads AutoCAD DWG 2010-2025 natively and also reads DXF.
- Auto-detects the network in any region: splice closures and their name attribute, handholes, cable layers,
  address-list columns, splitter size and drawing units.
- Callouts match the reference standard: MULTILEADER, layer DES_FIBER_SPL ACI 6, Standard/txt, height 4.0, arrow
  4.0, dogleg 0.36, landing gap 0.09, underlined top line.
- QA/QC workbook with every callout, its source calculation and every data issue found.
