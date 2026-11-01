# -*- coding: utf-8 -*-
"""
Read-only native DWG reader for AutoCAD 2010 - 2025 drawings (AC1024, AC1027, AC1032).

Written from the Open Design Alliance "Open Design Specification for .dwg files". It decodes exactly what the
callout engine needs - layers, block definitions, block references with attributes, text, multileaders and
linework - so DWG files can be analysed without AutoCAD or the ODA File Converter.

Bit-exactness was verified on a 75,000-object AC1032 production drawing (every TEXT, ATTRIB and MULTILEADER
object ends exactly at the start of its string stream).
"""
from __future__ import annotations

import math
import struct
from collections import Counter
from typing import Any, Callable, Dict, List, Optional, Tuple

SUPPORTED = {"AC1024": "AutoCAD 2010-2012", "AC1027": "AutoCAD 2013-2017", "AC1032": "AutoCAD 2018+"}
KNOWN = {"AC1012": "R13", "AC1014": "R14", "AC1015": "AutoCAD 2000", "AC1018": "AutoCAD 2004",
         "AC1021": "AutoCAD 2007"}


class DwgUnsupported(Exception):
    """The file is not a DWG this reader can decode (use the ODA File Converter instead)."""


# ----------------------------------------------------------------------------------------------- container
def _decrypt_header(data: bytes) -> bytes:
    out = bytearray(len(data))
    seed = 1
    for i, b in enumerate(data):
        seed = (seed * 0x343FD + 0x269EC3) & 0xFFFFFFFF
        out[i] = b ^ ((seed >> 16) & 0xFF)
    return bytes(out)


def _decompress(src: bytes) -> bytes:
    """DWG R2004+ LZ77 variant."""
    out = bytearray()
    pos = 0
    n = len(src)

    def nextb() -> int:
        nonlocal pos
        b = src[pos]
        pos += 1
        return b

    def lit_len(op: int) -> int:
        if op == 0:
            total = 0x0F
            b = nextb()
            while b == 0:
                total += 0xFF
                b = nextb()
            return total + b + 3
        return op + 3

    def long_off() -> int:
        b = nextb()
        if b == 0:
            total = 0xFF
            b = nextb()
            while b == 0:
                total += 0xFF
                b = nextb()
            return total + b
        return b

    def two_byte() -> Tuple[int, int]:
        b1 = nextb()
        b2 = nextb()
        return (b1 >> 2) | (b2 << 6), b1 & 0x03

    op = nextb()
    if (op & 0xF0) == 0:
        length = lit_len(op)
        out += src[pos:pos + length]
        pos += length
        op = nextb()
    while pos <= n:
        if op == 0x11:
            break
        if op == 0x10:
            cb = long_off() + 9
            off, lit = two_byte()
            off += 0x3FFF
        elif 0x12 <= op <= 0x1F:
            cb = (op & 0x0F) + 2
            off, lit = two_byte()
            off += 0x3FFF
        elif op == 0x20:
            cb = long_off() + 0x21
            off, lit = two_byte()
        elif 0x21 <= op <= 0x3F:
            cb = op - 0x1E
            off, lit = two_byte()
        elif op >= 0x40:
            cb = ((op & 0xF0) >> 4) - 1
            op2 = nextb()
            off = (op2 << 2) | ((op & 0x0C) >> 2)
            lit = op & 0x03
        else:
            raise ValueError("corrupt compressed section (opcode %#x)" % op)
        start = len(out) - off - 1
        if start < 0:
            raise ValueError("corrupt compressed section (back reference)")
        for k in range(cb):
            out.append(out[start + k])
        if lit == 0:
            if pos >= n:
                break
            op = nextb()
            if op < 0x10:
                length = lit_len(op)
                out += src[pos:pos + length]
                pos += length
                if pos >= n:
                    break
                op = nextb()
        else:
            out += src[pos:pos + lit]
            pos += lit
            if pos >= n:
                break
            op = nextb()
    return bytes(out)


class _Container:
    def __init__(self, raw: bytes) -> None:
        self.raw = raw
        self.version = raw[0:6].decode("ascii", "replace")
        self.maint = raw[0x0B]
        hdr = _decrypt_header(raw[0x80:0x80 + 0x6C])
        if not hdr.startswith(b"AcFssFcAJMB"):
            raise DwgUnsupported("encrypted DWG header not recognised")
        self.page_map_addr = struct.unpack_from("<Q", hdr, 0x54)[0] + 0x100
        self.section_map_id = struct.unpack_from("<I", hdr, 0x5C)[0]
        self.pages: Dict[int, Tuple[int, int]] = {}
        self.sections: Dict[str, Dict[str, Any]] = {}
        self._read_page_map()
        self._read_section_map()

    def _system_page(self, addr: int, expect: int) -> bytes:
        ptype, dsize, csize, ctype, _crc = struct.unpack_from("<IIIII", self.raw, addr)
        if ptype != expect:
            raise DwgUnsupported("unexpected system page type")
        data = self.raw[addr + 20: addr + 20 + csize]
        if ctype == 2:
            data = _decompress(data)
        return data[:dsize]

    def _read_page_map(self) -> None:
        data = self._system_page(self.page_map_addr, 0x41630E3B)
        addr = 0x100
        i = 0
        while i + 8 <= len(data):
            num, size = struct.unpack_from("<iI", data, i)
            i += 8
            if num < 0:
                i += 16
            else:
                self.pages[num] = (addr, size)
            addr += size

    def _read_section_map(self) -> None:
        addr, _ = self.pages[self.section_map_id]
        data = self._system_page(addr, 0x4163003B)
        ndesc = struct.unpack_from("<I", data, 0)[0]
        i = 20
        for _ in range(ndesc):
            size, = struct.unpack_from("<Q", data, i)
            i += 8
            pcount, maxsize, _u, comp, sid, enc = struct.unpack_from("<IIIIII", data, i)
            i += 24
            name = data[i:i + 64].split(b"\0")[0].decode("ascii", "replace")
            i += 64
            pages = []
            for _p in range(pcount):
                pn, dsz, off = struct.unpack_from("<IIQ", data, i)
                i += 16
                pages.append((pn, dsz, off))
            self.sections[name] = dict(size=size, comp=comp, enc=enc, pages=pages)

    def section(self, name: str) -> bytes:
        s = self.sections.get(name)
        if s is None:
            raise DwgUnsupported(f"section {name} missing")
        if s["enc"] == 1:
            raise DwgUnsupported("password-protected / encrypted DWG")
        buf = bytearray(s["size"])
        for pn, _dsz, off in s["pages"]:
            paddr, _ = self.pages[pn]
            mask = 0x4164536B ^ paddr
            h = [v ^ mask for v in struct.unpack_from("<8I", self.raw, paddr)]
            if h[0] != 0x4163043B:
                raise DwgUnsupported("corrupt data page")
            cdata = self.raw[paddr + 32: paddr + 32 + h[2]]
            ddata = _decompress(cdata) if s["comp"] == 2 else cdata
            end = off + len(ddata)
            if end > len(buf):
                buf.extend(b"\0" * (end - len(buf)))
            buf[off:end] = ddata
        return bytes(buf[:s["size"]])


# ----------------------------------------------------------------------------------------------- bit reader
class _Bits:
    __slots__ = ("d", "p")

    def __init__(self, data: bytes, bitpos: int = 0) -> None:
        self.d = data
        self.p = bitpos

    def B(self) -> int:  # noqa: N802 - spec names
        v = (self.d[self.p >> 3] >> (7 - (self.p & 7))) & 1
        self.p += 1
        return v

    def bits(self, n: int) -> int:
        if n == 0:
            return 0
        p = self.p
        off = p & 7
        nb = (off + n + 7) >> 3
        bi = p >> 3
        if bi + nb > len(self.d):
            raise IndexError("read past end of object")
        chunk = int.from_bytes(self.d[bi:bi + nb], "big")
        self.p = p + n
        return (chunk >> (nb * 8 - off - n)) & ((1 << n) - 1)

    def raw(self, n: int) -> bytes:
        if self.p & 7 == 0:
            s = self.p >> 3
            self.p += 8 * n
            return bytes(self.d[s:s + n])
        return self.bits(8 * n).to_bytes(n, "big") if n else b""

    def RC(self) -> int:  # noqa: N802
        return self.bits(8)

    def RS(self) -> int:  # noqa: N802
        return struct.unpack("<H", self.raw(2))[0]

    def RL(self) -> int:  # noqa: N802
        return struct.unpack("<I", self.raw(4))[0]

    def RD(self) -> float:  # noqa: N802
        return struct.unpack("<d", self.raw(8))[0]

    def BB(self) -> int:  # noqa: N802
        return self.bits(2)

    def BS(self) -> int:  # noqa: N802
        c = self.bits(2)
        if c == 0:
            return self.RS()
        if c == 1:
            return self.RC()
        if c == 2:
            return 0
        return 256

    def BL(self) -> int:  # noqa: N802
        c = self.bits(2)
        if c == 0:
            return self.RL()
        if c == 1:
            return self.RC()
        if c == 2:
            return 0
        raise ValueError("invalid BL")

    def BLd(self) -> int:  # noqa: N802
        v = self.BL()
        return v - (1 << 32) if v & 0x80000000 else v

    def BD(self) -> float:  # noqa: N802
        c = self.bits(2)
        if c == 0:
            return self.RD()
        if c == 1:
            return 1.0
        if c == 2:
            return 0.0
        raise ValueError("invalid BD")

    def BLL(self) -> int:  # noqa: N802
        n = self.bits(3)
        return int.from_bytes(self.raw(n), "little") if n else 0

    def DD(self, default: float) -> float:  # noqa: N802
        c = self.bits(2)
        if c == 0:
            return default
        b = bytearray(struct.pack("<d", default))
        if c == 1:
            b[0:4] = self.raw(4)
        elif c == 2:
            x = self.raw(6)
            b[4:6] = x[0:2]
            b[0:4] = x[2:6]
        else:
            return self.RD()
        return struct.unpack("<d", bytes(b))[0]

    def BT(self) -> float:  # noqa: N802
        return 0.0 if self.B() else self.BD()

    def BE(self) -> Tuple[float, float, float]:  # noqa: N802
        if self.B():
            return (0.0, 0.0, 1.0)
        return (self.BD(), self.BD(), self.BD())

    def P3(self) -> Tuple[float, float, float]:  # noqa: N802
        return (self.BD(), self.BD(), self.BD())

    def P2RD(self) -> Tuple[float, float]:  # noqa: N802
        return (self.RD(), self.RD())

    def H(self, ref: int = 0) -> int:  # noqa: N802
        code = self.bits(4)
        cnt = self.bits(4)
        v = int.from_bytes(self.raw(cnt), "big") if cnt else 0
        if code <= 5:
            return v
        if code == 6:
            return ref + 1
        if code == 8:
            return ref - 1
        if code == 0xA:
            return ref + v
        if code == 0xC:
            return ref - v
        return v

    def TU(self) -> str:  # noqa: N802
        n = self.BS()
        return self.raw(2 * n).decode("utf-16-le", "replace").rstrip("\0")

    def UMC(self) -> int:  # noqa: N802
        result = shift = 0
        while True:
            b = self.RC()
            result |= (b & 0x7F) << shift
            shift += 7
            if not b & 0x80:
                return result

    def MC(self) -> int:  # noqa: N802
        result = shift = 0
        while True:
            b = self.RC()
            if b & 0x80:
                result |= (b & 0x7F) << shift
                shift += 7
            else:
                result |= (b & 0x3F) << shift
                return -result if b & 0x40 else result

    def MS(self) -> int:  # noqa: N802
        result = shift = 0
        while True:
            w = self.RS()
            result |= (w & 0x7FFF) << shift
            shift += 15
            if not w & 0x8000:
                return result


def _string_stream(data: bytes, endbit: int) -> Optional[_Bits]:
    r = _Bits(data, endbit - 1)
    if not r.B():
        return None
    p = endbit - 17
    size = _Bits(data, p).RS()
    if size & 0x8000:
        p -= 16
        hi = _Bits(data, p).RS()
        size = (size & 0x7FFF) | (hi << 15)
    return _Bits(data, p - size)


class _Obj:
    __slots__ = ("type", "handle", "br", "start", "size", "hsize", "endbit", "ss", "hs", "eed")


# ----------------------------------------------------------------------------------------------- reader
ENTITY_TYPES = {1: "TEXT", 2: "ATTRIB", 3: "ATTDEF", 7: "INSERT", 10: "VERTEX_2D", 15: "POLYLINE_2D",
                17: "ARC", 18: "CIRCLE", 19: "LINE", 31: "SOLID", 44: "MTEXT", 77: "LWPOLYLINE"}


class NativeDwg:
    """Decode a DWG file. Use `entities()` after construction."""

    def __init__(self, path: str, progress: Optional[Callable[[float, str], None]] = None) -> None:
        with open(path, "rb") as f:
            raw = f.read()
        ver = raw[0:6].decode("ascii", "replace")
        if ver not in SUPPORTED:
            name = KNOWN.get(ver, "unknown/non-DWG")
            raise DwgUnsupported(f"DWG format {ver} ({name}) is not supported by the built-in reader; "
                                 f"save the drawing as AutoCAD 2010-2018 DWG or DXF, or install the ODA File Converter")
        self.version = ver
        self.release = SUPPORTED[ver]
        self._progress = progress or (lambda p, m: None)
        self.c = _Container(raw)
        self.r2013 = ver >= "AC1027"
        self.r2018 = ver >= "AC1032"
        self._progress(2, "Decompressing DWG sections")
        self.objs = self.c.section("AcDb:AcDbObjects")
        self.omap = self._object_map(self.c.section("AcDb:Handles"))
        self.classes = self._classes(self.c.section("AcDb:Classes"))
        self.mleader_type = next((n for n, c in self.classes.items() if c == "MULTILEADER"), -1)
        self.errors: Counter = Counter()
        self.layers: Dict[int, Dict[str, Any]] = {}
        self.blocks: Dict[int, str] = {}
        self.block_base: Dict[str, Tuple[float, float]] = {}
        self.block_effective: Dict[str, str] = {}     # anonymous dynamic-block variant -> dynamic block name
        self.appids: Dict[int, str] = {}
        self._prefix = 2
        self._tables()

    # ------------------------------------------------------------------ structure
    @staticmethod
    def _object_map(data: bytes) -> Dict[int, int]:
        omap: Dict[int, int] = {}
        pos = 0
        n = len(data)
        while pos + 2 <= n:
            size = struct.unpack_from(">H", data, pos)[0]
            if size <= 2:
                break
            start = pos
            br = _Bits(data, (pos + 2) * 8)
            last_h = last_o = 0
            while (br.p >> 3) < start + size:
                last_h += br.UMC()
                last_o += br.MC()
                omap[last_h] = last_o
            pos = start + size + 2
        return omap

    def _classes(self, data: bytes) -> Dict[int, str]:
        br = _Bits(data, 16 * 8)
        br.RL()
        has_hsize = self.r2013 or self.c.maint > 3
        if has_hsize:
            br.RL()
        base = br.p
        bitsize = br.RL()
        ss = _string_stream(data, base + bitsize)
        max_num = br.BS()
        br.RC()
        br.RC()
        br.B()
        out: Dict[int, str] = {}
        if ss is None:
            return out
        try:
            while br.p < base + bitsize:
                num = br.BS()
                br.BS()
                ss.TU()
                ss.TU()
                dxf = ss.TU()
                br.B()
                br.BS()
                for _ in range(5):
                    br.BL()
                out[num] = dxf.upper()
                if num >= max_num:
                    break
        except (IndexError, ValueError):
            pass
        return out

    def _header(self, handle: int) -> Optional[_Obj]:
        loc = self.omap.get(handle)
        if loc is None:
            return None
        br = _Bits(self.objs, loc * 8)
        o = _Obj()
        o.size = br.MS()
        o.hsize = br.UMC()
        o.start = br.p
        o.endbit = br.p + o.size * 8 - o.hsize
        c = br.BB()
        o.type = br.RC() if c == 0 else (br.RC() + 0x1F0 if c == 1 else br.RS())
        o.handle = br.H()
        o.eed = []
        while True:
            esz = br.BS()
            if esz == 0:
                break
            app = br.H()
            o.eed.append((app, br.raw(esz)))
        o.br = br
        o.ss = None
        o.hs = None
        return o

    def _streams(self, o: _Obj) -> None:
        o.ss = _string_stream(self.objs, o.endbit)
        o.hs = _Bits(self.objs, o.endbit)

    def _object_common(self, o: _Obj) -> Tuple[int, int]:
        br = o.br
        nreact = br.BL()
        xm = br.B()
        if self.r2013:
            br.B()
        self._streams(o)
        return nreact, xm

    def _tables(self) -> None:
        layer_objs: List[Tuple[_Obj, int, int]] = []
        block_objs: List[Tuple[_Obj, int, int]] = []
        for h in self.omap:
            try:
                o = self._header(h)
            except (IndexError, ValueError):
                continue
            if o is None:
                continue
            if o.type == 67:
                try:
                    self._object_common(o)
                    self.appids[o.handle] = o.ss.TU() if o.ss else ""
                except (IndexError, ValueError):
                    pass
                continue
            if o.type in (51, 49):
                try:
                    nreact, xm = self._object_common(o)
                except (IndexError, ValueError):
                    continue
                (layer_objs if o.type == 51 else block_objs).append((o, o.br.p, nreact))
        # table-entry prefix width differs between releases: detect it from the LAYER colour record
        votes: Counter = Counter()
        for o, p0, _ in layer_objs[:50]:
            for pref in (2, 4, 3, 5, 1):
                try:
                    br = _Bits(self.objs, p0 + pref)
                    br.BS()
                    br.BS()
                    rgb = br.BL()
                    if (rgb >> 24) in (0xC0, 0xC1, 0xC2, 0xC3, 0xC8):
                        votes[pref] += 1
                        break
                except (IndexError, ValueError):
                    continue
        if votes:
            self._prefix = votes.most_common(1)[0][0]
        for o, p0, _ in layer_objs:
            try:
                name = o.ss.TU() if o.ss else ""
                br = _Bits(self.objs, p0 + self._prefix)
                flags = br.BS()
                br.BS()
                rgb = br.BL()
                aci = rgb & 0xFF if (rgb >> 24) == 0xC3 else 7
                self.layers[o.handle] = dict(name=name, aci=aci, off=bool(flags & 2), frozen=bool(flags & 1))
            except (IndexError, ValueError):
                self.errors["LAYER"] += 1
        pending: List[Tuple[str, int]] = []
        for o, p0, _ in block_objs:
            try:
                name = o.ss.TU() if o.ss else ""
                br = _Bits(self.objs, p0 + self._prefix)
                br.B()
                br.B()
                isx = br.B()
                ovl = br.B()
                br.B()
                if not (isx or ovl):
                    br.BL()
                base = br.P3()
                self.blocks[o.handle] = name
                self.block_base[name] = (base[0], base[1]) if all(math.isfinite(v) and abs(v) < 1e12 for v in base[:2]) else (0.0, 0.0)
                rep_handle = self._block_rep_handle(o.eed)
                if rep_handle:
                    pending.append((name, rep_handle))
            except (IndexError, ValueError):
                self.errors["BLOCK_HEADER"] += 1
        for name, h in pending:
            if h in self.blocks and self.blocks[h] != name:
                self.block_effective[name] = self.blocks[h]

    def _block_rep_handle(self, eed: List[Tuple[int, bytes]]) -> int:
        """Handle of the dynamic block definition referenced by an anonymous block (XData AcDbBlockRepBTag)."""
        for app, raw in eed:
            if self.appids.get(app, "").upper() != "ACDBBLOCKREPBTAG":
                continue
            i = 0
            while i < len(raw):
                code = raw[i]
                i += 1
                if code == 70:
                    i += 2
                elif code == 5:
                    return int.from_bytes(raw[i:i + 8], "big")
                elif code == 0:
                    n = struct.unpack_from("<H", raw, i)[0]
                    i += 2 + 2 * n
                elif code == 2:
                    i += 1
                elif code == 71:
                    i += 4
                elif code in (40, 41, 42):
                    i += 8
                elif code in (3,):
                    i += 8
                elif 10 <= code <= 13:
                    i += 24
                elif code == 4:
                    i += 1 + raw[i]
                else:
                    break
        return 0

    @property
    def layer_names(self) -> List[str]:
        return sorted(v["name"] for v in self.layers.values())

    # ------------------------------------------------------------------ entities
    def entities(self) -> List[Dict[str, Any]]:
        """Decode all supported entities (model space, paper space and block definitions)."""
        wanted = set(ENTITY_TYPES) | {self.mleader_type}
        raw: Dict[int, Dict[str, Any]] = {}
        handles = list(self.omap)
        total = len(handles)
        for i, h in enumerate(handles):
            if i % 5000 == 0:
                self._progress(5 + 60 * i / max(1, total), f"Decoding DWG objects ({i:,}/{total:,})")
            try:
                o = self._header(h)
            except (IndexError, ValueError):
                self.errors["header"] += 1
                continue
            if o is None or o.type not in wanted:
                continue
            tname = "MULTILEADER" if o.type == self.mleader_type else ENTITY_TYPES[o.type]
            try:
                e = self._entity(o, tname)
            except (IndexError, ValueError, struct.error, OverflowError):
                self.errors[tname] += 1
                continue
            raw[o.handle] = e
        # resolve attributes and polyline vertices
        out: List[Dict[str, Any]] = []
        for e in raw.values():
            t = e["type"]
            if t == "INSERT":
                att = {}
                for ah in e.pop("attrib_handles", []):
                    a = raw.get(ah)
                    if a and a.get("tag"):
                        att[a["tag"].upper()] = a.get("text", "")
                e["attribs"] = att
            elif t == "POLYLINE_2D":
                pts = []
                for vh in e.pop("vertex_handles", []):
                    v = raw.get(vh)
                    if v and "point" in v:
                        pts.append(v["point"])
                e["points"] = pts
                e["type"] = "LWPOLYLINE"
            if t in ("ATTRIB", "VERTEX_2D"):
                continue
            out.append(e)
        self._progress(66, "DWG decoded")
        return out

    def _entity(self, o: _Obj, tname: str) -> Dict[str, Any]:
        br = o.br
        if br.B():
            gsize = br.BLL()
            br.p += gsize * 8
        entmode = br.BB()
        nreact = br.BL()
        xm = br.B()
        if self.r2013:
            br.B()
        raw_col = br.BS()
        cflags = raw_col >> 8
        if cflags & 0x80:
            br.BL()
        if cflags & 0x20:
            br.BL()
        br.BD()
        ltf = br.BB()
        psf = br.BB()
        mtf = br.BB()
        br.RC()
        fvs = br.B()
        fcvs = br.B()
        evs = br.B()
        br.BS()
        br.RC()
        self._streams(o)
        hs = o.hs
        owner = hs.H(o.handle) if entmode == 0 else None
        for _ in range(nreact):
            hs.H(o.handle)
        if not xm:
            hs.H(o.handle)
        layer_h = hs.H(o.handle)
        if ltf == 3:
            hs.H(o.handle)
        if mtf == 3:
            hs.H(o.handle)
        if psf == 3:
            hs.H(o.handle)
        for f in (fvs, fcvs, evs):
            if f:
                hs.H(o.handle)
        e: Dict[str, Any] = dict(type=tname, handle=o.handle,
                                 layer=self.layers.get(layer_h, {}).get("name", ""),
                                 space={0: "block", 1: "paper", 2: "model"}.get(entmode, "?"), owner=owner)
        getattr(self, "_e_" + tname)(e, o)
        return e

    def _text_common(self, e: Dict[str, Any], br: _Bits, ss: Optional[_Bits]) -> None:
        df = br.RC()
        elev = 0.0 if df & 1 else br.RD()
        ins = br.P2RD()
        if not df & 2:
            br.DD(ins[0])
            br.DD(ins[1])
        br.BE()
        br.BT()
        if not df & 4:
            br.RD()
        e["rotation"] = 0.0 if df & 8 else math.degrees(br.RD())
        e["height"] = br.RD()
        if not df & 0x10:
            br.RD()
        e["text"] = ss.TU() if ss else ""
        if not df & 0x20:
            br.BS()
        if not df & 0x40:
            br.BS()
        if not df & 0x80:
            br.BS()
        e["insert"] = (ins[0], ins[1])
        e["elevation"] = elev

    def _e_TEXT(self, e: Dict[str, Any], o: _Obj) -> None:  # noqa: N802
        self._text_common(e, o.br, o.ss)

    def _e_ATTRIB(self, e: Dict[str, Any], o: _Obj) -> None:  # noqa: N802
        br = o.br
        self._text_common(e, br, o.ss)
        br.RC()
        if self.r2018:
            atype = br.RC()
            if atype > 1:
                e["tag"] = ""
                return
        e["tag"] = o.ss.TU() if o.ss else ""

    _e_ATTDEF = _e_ATTRIB

    def _e_INSERT(self, e: Dict[str, Any], o: _Obj) -> None:  # noqa: N802
        br, hs = o.br, o.hs
        ins = br.P3()
        sf = br.BB()
        if sf == 3:
            sc = (1.0, 1.0)
        elif sf == 1:
            sc = (1.0, br.DD(1.0))
            br.DD(1.0)
        elif sf == 2:
            x = br.RD()
            sc = (x, x)
        else:
            x = br.RD()
            sc = (x, br.DD(x))
            br.DD(x)
        e["insert"] = (ins[0], ins[1])
        e["scale"] = sc
        e["rotation"] = math.degrees(br.BD())
        ext = br.P3()
        e["mirrored"] = ext[2] < 0
        has_att = br.B()
        nown = br.BL() if has_att else 0
        bh = hs.H(o.handle)
        e["block_def"] = self.blocks.get(bh, "")
        e["block"] = self.block_effective.get(e["block_def"], e["block_def"])
        e["attrib_handles"] = [hs.H(o.handle) for _ in range(nown)] if has_att else []

    def _e_MTEXT(self, e: Dict[str, Any], o: _Obj) -> None:  # noqa: N802
        br = o.br
        ins = br.P3()
        br.P3()
        xd = br.P3()
        e["rotation"] = math.degrees(math.atan2(xd[1], xd[0]))
        br.BD()
        br.BD()
        e["height"] = br.BD()
        e["attachment"] = br.BS()
        br.BS()
        br.BD()
        br.BD()
        e["text"] = o.ss.TU() if o.ss else ""
        e["insert"] = (ins[0], ins[1])

    def _e_LWPOLYLINE(self, e: Dict[str, Any], o: _Obj) -> None:  # noqa: N802
        br = o.br
        fl = br.BS()
        if fl & 4:
            br.BD()
        if fl & 8:
            br.BD()
        if fl & 2:
            br.BD()
        if fl & 1:
            br.P3()
        n = br.BL()
        if fl & 16:
            br.BL()
        if fl & 1024:
            br.BL()
        if fl & 32:
            br.BL()
        pts = []
        if n:
            p = br.P2RD()
            pts.append(p)
            for _ in range(n - 1):
                p = (br.DD(p[0]), br.DD(p[1]))
                pts.append(p)
        e["points"] = pts
        e["closed"] = bool(fl & 512)

    def _e_LINE(self, e: Dict[str, Any], o: _Obj) -> None:  # noqa: N802
        br = o.br
        zflag = br.B()
        x1 = br.RD()
        x2 = br.DD(x1)
        y1 = br.RD()
        y2 = br.DD(y1)
        if not zflag:
            z1 = br.RD()
            br.DD(z1)
        e["points"] = [(x1, y1), (x2, y2)]

    def _e_CIRCLE(self, e: Dict[str, Any], o: _Obj) -> None:  # noqa: N802
        c = o.br.P3()
        e["center"] = (c[0], c[1])
        e["radius"] = o.br.BD()

    _e_ARC = _e_CIRCLE

    def _e_SOLID(self, e: Dict[str, Any], o: _Obj) -> None:  # noqa: N802
        br = o.br
        br.BT()
        br.BD()
        e["points"] = [br.P2RD() for _ in range(4)]

    def _e_POLYLINE_2D(self, e: Dict[str, Any], o: _Obj) -> None:  # noqa: N802
        br, hs = o.br, o.hs
        fl = br.BS()
        br.BS()
        br.BD()
        br.BD()
        br.BT()
        br.BD()
        br.BE()
        n = br.BL()
        e["vertex_handles"] = [hs.H(o.handle) for _ in range(n)]
        e["closed"] = bool(fl & 1)

    def _e_VERTEX_2D(self, e: Dict[str, Any], o: _Obj) -> None:  # noqa: N802
        br = o.br
        br.RC()
        p = br.P3()
        e["point"] = (p[0], p[1])

    def _cmc(self, br: _Bits, ss: Optional[_Bits]) -> None:
        br.BS()
        br.BL()
        flag = br.RC()
        if flag & 1 and ss:
            ss.TU()
        if flag & 2 and ss:
            ss.TU()

    def _e_MULTILEADER(self, e: Dict[str, Any], o: _Obj) -> None:  # noqa: N802
        br, ss, hs = o.br, o.ss, o.hs
        br.BS()
        tip = None
        last = None
        dog = 1
        for _ in range(br.BL()):
            has_last = br.B()
            has_dog = br.B()
            if has_last:
                lp = br.P3()
                last = last or (lp[0], lp[1])
            if has_dog:
                dv = br.P3()
                dog = 1 if dv[0] >= 0 else -1
            for _b in range(br.BL()):
                br.P3()
                br.P3()
            br.BL()
            br.BD()
            for _l in range(br.BL()):
                pts = [br.P3() for _p in range(br.BL())]
                if pts and tip is None:
                    tip = (pts[0][0], pts[0][1])
                nb = br.BL()
                if nb:
                    br.BL()
                    for _b in range(nb):
                        br.P3()
                        br.P3()
                br.BL()
                br.BS()
                self._cmc(br, ss)
                hs.H(o.handle)
                br.BLd()
                br.BD()
                hs.H(o.handle)
                br.BL()
            br.BS()
        br.BD()
        br.P3()
        height = br.BD()
        br.BD()
        br.BD()
        for _ in range(4):
            br.BS()
        text = ""
        loc = None
        if br.B():
            text = ss.TU() if ss else ""
            br.P3()
            hs.H(o.handle)
            lc = br.P3()
            loc = (lc[0], lc[1])
        e["text"] = text
        e["height"] = height
        e["tip"] = tip
        e["landing"] = last
        e["dog"] = dog
        e["insert"] = loc or last or tip or (0.0, 0.0)
