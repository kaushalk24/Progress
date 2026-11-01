# DWG analysis toolkit (read-only)

Pure-Python decoder for AutoCAD DWG R2004+ files (AC1018, AC1024, AC1027, AC1032) written from the Open Design
Specification for the Phase 1 reverse-engineering. It is **not** used by the production tool (which works on DXF via
ezdxf and converts DWG with the ODA File Converter); it exists so the analysis can be reproduced.

| Module | Scope |
|---|---|
| `dwgcontainer.py` | file header decryption, page map, section map, LZ77 page decompression |
| `dwgobjects.py` | bit reader (B/BB/BS/BL/BD/DD/BT/BE/H/TU/MC/MS), object map, class map, object headers, R2007+ string streams |
| `dwgentities.py` | LAYER, STYLE, LTYPE, BLOCK_HEADER, APPID tables; TEXT, ATTRIB, ATTDEF, MTEXT, INSERT, LWPOLYLINE, LINE, POINT, CIRCLE, LEADER (points), MULTILEADER (full AnnotContext) |

Dump everything to JSON:

```bash
python dwgentities.py drawing.dwg dump.json
```

Census of object types:

```bash
python dwgobjects.py drawing.dwg
```

Each entity in the dump carries `_bitgap` = bits left between the end of the decoded fields and the start of the
object's string stream; `0` means the object was decoded bit-exactly (all TEXT, ATTRIB and MULTILEADER objects of
the Credit River drawing). The R2018 table-entry prefix observed in that file is 2 bits (64-flag, xdep).
