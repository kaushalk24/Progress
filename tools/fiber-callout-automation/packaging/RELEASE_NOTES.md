## FiberCallout Studio 2.1.0 (Windows x64)

Single-file desktop app that generates the magenta **DES_FIBER_SPL** fiber-number and BFO callouts of an FTTx design
from its splice reports and address lists.

**Install:** download `FiberCalloutStudio.exe` (or the zip) and run it. You don't need Python, AutoCAD or anything
else. The exe isn't code-signed, so if Windows SmartScreen appears, click *More info -> Run anyway*.

**Check the installation:** *Help -> Run self-test* (or `FiberCalloutStudio.exe --selftest`).

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
