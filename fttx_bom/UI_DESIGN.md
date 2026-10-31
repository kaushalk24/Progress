# FTTx BOM Tool: user interface

## Goals

1. Generate a correct OLM BOM from the design drawing and its inputs, with the fewest possible steps.
2. Make it obvious which numbers can be trusted and which must be checked before ordering.
3. Show every problem with a concrete fix, located in the drawing.
4. Run entirely on the user's computer. No file leaves it.

## Users

**Primary:** FTTx design engineers who produce BOMs for each OLM.

**Secondary:** the reviewer who signs off a BOM, and the lead who runs many networks at once.

## Navigation

A sidebar holds four pages, plus version and job-folder information.

| Page | Purpose |
|---|---|
| **New BOM** | One job, run as three steps on one page: Inputs, Generate, Results |
| **Batch** | Many networks: one sub-folder per job, with one summary |
| **Design standards** | How every BOM line is derived (rule table and standards document) |
| **Settings** | Conventions the drawing cannot settle (options, evidence, restore standard) |

## New BOM

### Step 1: Inputs

- **Source**, chosen with a segmented control:
  - *Upload files*: drag and drop, with multiple files and zips accepted.
  - *Folders on this computer*: one path per line, for large drawings.
- **What to supply:** the drawing (DWG/DXF), address list(s), splice reports and the blank BOM template. Optionally, an approved BOM to compare against.
- **Detection:** each file's role is detected from its content, so names don't matter.
- **Project name and number** are pre-filled from the drawing file name. **System** is picked from a list.
- **Advanced** (collapsed): formula recalculation with LibreOffice, and learning conventions from an approved BOM.

### Step 2: Generate

- The primary button is disabled until inputs are present.
- A status panel shows:
  - the detected-files table (file → recognised role, or why it is not used);
  - the current stage;
  - the final state: complete, inputs incomplete, or failed with the error.

### Step 3: Results

**Header KPIs:**
- passings;
- low-confidence cells;
- cells to review;
- design errors and design warnings;
- workbook check (passed / failed).

**Tabs, one set per BOM file** (one OLM per BOM):

1. **BOM preview:** every written line with its Grant / Non-Grant values per network, and a status column (● low confidence, ● review, ✓).
2. **Cells to check:** each flagged cell with its value, level and plain-language reason. It can be filtered to "low confidence only".
3. **Design check:** problems by severity with a "how to fix", plus a note on the AutoCAD script that circles each located problem.
4. **Excluded plant:** objects in the drawing that are not part of this design, with the reason.
5. **Downloads:** BOM workbook, audit workbook, comparison with the approved BOM, design check (CSV), AutoCAD issue script, and everything as a zip.

## Confidence in the BOM workbook

The same rating appears in the app and in the generated Excel BOM.

| Level | Colour | Meaning |
|---|---|---|
| Low confidence | light red fill, dark red bold value | Do not order without checking. The value could not be derived, a key input is missing, or a blocking design issue affects it. |
| Review | light amber fill, dark amber bold value | Check before ordering. The value comes from an inferred rule or an unsettled convention, or a design warning affects it. |
| No highlight | template formatting | Derived by the design standard from complete inputs |

- Every flagged cell carries a comment explaining why.
- A **BOM Review** sheet at the end of the workbook lists all flagged cells.
- The audit's *Review* sheet repeats the list.

## States and errors

| Situation | What the user sees |
|---|---|
| No inputs | Generate button disabled |
| Inputs incomplete (no drawing or template) | Red status with the missing item |
| Missing address list or splice reports | BOM still produced; affected cells marked low confidence |
| Unexpected failure | Red status and the error detail, never a blank page |

## Visual style

- Wide layout with a maximum content width.
- Neutral typography, with small uppercase step labels.
- Colour is used only for meaning: confidence and severity. The confidence colours are the same in the app and in Excel.
- No technical identifiers in user-facing text, except issue codes in the design-check table, which are useful for filtering.
