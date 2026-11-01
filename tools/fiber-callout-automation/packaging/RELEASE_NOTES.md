## FiberCallout Studio 2.0.0 (Windows x64)

Single-file desktop app that generates the magenta **DES_FIBER_SPL** fiber-number callouts of an FTTx design from its
splice reports and address lists.

**Install:** download `FiberCalloutStudio.exe` (or the zip) and run it - no Python or other installation needed.
The exe is not code-signed: if Windows SmartScreen appears, click *More info -> Run anyway*.

**Check the installation:** *Tools -> Run built-in self-test* (or `FiberCalloutStudio.exe --selftest`).

Highlights
- Reads AutoCAD DWG 2010-2025 natively (no AutoCAD / ODA needed) and DXF; uses the free ODA File Converter
  automatically when installed to write the complete DWG.
- Auto-detects the network in any region: splice closures + name attribute, handholes, cable layers, address-list
  columns, splitter size and drawing units.
- Callouts identical to the reference standard (MULTILEADER, layer DES_FIBER_SPL ACI 6, Standard/txt, height 4.0,
  arrow 4.0, dogleg 0.36, landing gap 0.09, underlined top line).
- QA/QC workbook with every callout, its source calculation and all data issues found.
