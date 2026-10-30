"""Read-only decoder for the drawing objects of an AutoCAD 2013/2018 DWG (AC1027, AC1032).

Built on dwg_container (which decrypts and decompresses the file sections). It decodes only what
the design model needs:

  * LAYER and BLOCK_HEADER names,
  * INSERT (block reference: position, rotation, attributes) and ATTRIB (tag, value),
  * LWPOLYLINE and LINE (cable geometry),
  * TEXT and MTEXT values.

Every other object is skipped by its size, so an unknown object never breaks the read. The
decoder follows the published DWG format description (Open Design Alliance, "Open Design
Specification for .dwg files", R2007+ object layout with separate string and handle streams).
AC1024 (AutoCAD 2010) uses the same layout without the data-store flag; it is attempted but has
not been verified against a sample file. Older versions are refused: save the drawing as
AutoCAD 2013 or 2018 DWG, or export a DXF.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from .dwg_container import DwgContainer, DwgError

# object type numbers (fixed for these classes in every DWG version)
TEXT, ATTRIB, INSERT, LINE, MTEXT, BLOCK_HEADER, LAYER, LWPOLYLINE = 1, 2, 7, 19, 44, 49, 51, 77
DECODED = {TEXT, ATTRIB, INSERT, LINE, MTEXT, BLOCK_HEADER, LAYER, LWPOLYLINE}
OBJECT_DECODE_VERSIONS = ("AC1024", "AC1027", "AC1032")


class Bits:
    """Big-endian bit cursor over a byte buffer (DWG bit codes)."""
    __slots__ = ("b", "pos", "end")

    def __init__(self, data: bytes, pos_bits: int = 0, end_bits: int | None = None):
        self.b = data
        self.pos = pos_bits
        self.end = len(data) * 8 if end_bits is None else end_bits

    def B(self) -> int:
        p = self.pos
        self.pos += 1
        return (self.b[p >> 3] >> (7 - (p & 7))) & 1

    def bits(self, n: int) -> int:
        v = 0
        for _ in range(n):
            v = (v << 1) | self.B()
        return v

    def RC(self) -> int:
        p = self.pos
        self.pos += 8
        i, s = p >> 3, p & 7
        if s == 0:
            return self.b[i]
        return ((self.b[i] << s) | (self.b[i + 1] >> (8 - s))) & 0xFF

    def raw(self, n: int) -> bytes:
        if self.pos & 7 == 0:
            i = self.pos >> 3
            self.pos += 8 * n
            return self.b[i:i + n]
        return bytes(self.RC() for _ in range(n))

    def BB(self) -> int:
        return self.bits(2)

    def RS(self) -> int:
        return struct.unpack("<H", self.raw(2))[0]

    def RL(self) -> int:
        return struct.unpack("<I", self.raw(4))[0]

    def RD(self) -> float:
        return struct.unpack("<d", self.raw(8))[0]

    def BS(self) -> int:
        c = self.BB()
        if c == 0:
            return self.RS()
        if c == 1:
            return self.RC()
        return 0 if c == 2 else 256

    def BL(self) -> int:
        c = self.BB()
        if c == 0:
            return self.RL()
        if c == 1:
            return self.RC()
        if c == 2:
            return 0
        raise DwgError("invalid BL code")

    def BLL(self) -> int:
        n = self.bits(3)
        return sum(self.RC() << (8 * i) for i in range(n))

    def BD(self) -> float:
        c = self.BB()
        if c == 0:
            return self.RD()
        if c == 1:
            return 1.0
        if c == 2:
            return 0.0
        raise DwgError("invalid BD code")

    def DD(self, default: float) -> float:
        c = self.BB()
        if c == 0:
            return default
        if c == 3:
            return self.RD()
        raw = bytearray(struct.pack("<d", default))
        if c == 2:
            raw[4], raw[5] = self.RC(), self.RC()
        raw[0:4] = self.raw(4)
        return struct.unpack("<d", bytes(raw))[0]

    def BT(self) -> float:
        return 0.0 if self.B() else self.BD()

    def BE(self):
        if self.B():
            return (0.0, 0.0, 1.0)
        return (self.BD(), self.BD(), self.BD())

    def MC(self, signed: bool = True) -> int:
        v, shift = 0, 0
        while True:
            c = self.RC()
            if c & 0x80:
                v |= (c & 0x7F) << shift
                shift += 7
                continue
            if signed:
                v |= (c & 0x3F) << shift
                return -v if c & 0x40 else v
            return v | ((c & 0x7F) << shift)

    def MS(self) -> int:
        v, shift = 0, 0
        while True:
            w = self.RS()
            if w & 0x8000:
                v |= (w & 0x7FFF) << shift
                shift += 15
                continue
            return v | (w << shift)

    def H(self) -> tuple[int, int]:
        cs = self.RC()
        v = 0
        for _ in range(cs & 0x0F):
            v = (v << 8) | self.RC()
        return cs >> 4, v

    def BOT(self) -> int:
        c = self.BB()
        if c == 0:
            return self.RC()
        if c == 1:
            return self.RC() + 0x1F0
        return self.RS()

    def TU(self) -> str:
        n = self.BS()
        if n == 0:
            return ""
        return self.raw(2 * n).decode("utf-16le", "replace").rstrip("\x00")

    def ENC(self):
        """Entity colour (R2004+): returns flags; reads the optional RGB / transparency values."""
        raw = self.BS()
        flags = raw >> 8
        if flags & 0x80:
            self.BL()
        if flags & 0x20:
            self.BL()
        return flags


def handle_map(section: bytes) -> dict[int, int]:
    """AcDb:Handles -> {handle: byte offset of the object in AcDb:AcDbObjects}."""
    out, i = {}, 0
    while i + 2 <= len(section):
        size = struct.unpack(">H", section[i:i + 2])[0]
        if size <= 2:
            break
        b = Bits(section, (i + 2) * 8)
        end = (i + size) * 8
        h = off = 0
        while b.pos < end:
            h += b.MC(signed=False)
            off += b.MC(signed=True)
            out[h] = off
        i += size + 2          # + CRC
    return out


class _Obj:
    __slots__ = ("b", "s", "h", "handle", "type")

    def text(self) -> str:
        return self.s.TU() if self.s is not None else ""

    def ref(self) -> int:
        code, val = self.h.H()
        if code == 6:
            return self.handle + 1
        if code == 8:
            return self.handle - 1
        if code == 0xA:
            return self.handle + val
        if code == 0xC:
            return self.handle - val
        return val


def _open(buf: bytes, off: int) -> _Obj:
    o = _Obj()
    b = Bits(buf, off * 8)
    size = b.MS()
    hsize = b.MC(signed=False)
    start = b.pos
    o.type = b.BOT()
    bitsize = size * 8 - hsize            # data + string stream, measured after MS and handle-size MC
    o.h = Bits(buf, start + bitsize, start + size * 8)
    o.s = None
    p0 = start + bitsize - 1              # string-stream flag is the last data bit
    sb = Bits(buf, p0)
    if sb.B():
        sb.pos = p0 - 16
        ssize, endp = sb.RS(), p0 - 16
        if ssize & 0x8000:
            sb.pos = p0 - 32
            ssize = (ssize & 0x7FFF) | (sb.RS() << 15)
            endp = p0 - 32
        o.s = Bits(buf, endp - ssize, endp)
    o.b = b
    _, o.handle = b.H()
    while True:                            # extended entity data: skipped
        n = b.BS()
        if n == 0:
            break
        b.H()
        b.pos += 8 * n
    return o


def _entity_common(o: _Obj, has_ds: bool) -> dict:
    b = o.b
    if b.B():                              # graphic preview
        b.pos += 8 * b.BLL()
    ce = {"entmode": b.BB(), "nreact": b.BL(), "xdic_missing": b.B()}
    if has_ds:
        b.B()
    ce["color_flags"] = b.ENC()
    b.BD()                                 # linetype scale
    ce["lt"], ce["ps"], ce["mat"] = b.BB(), b.BB(), b.BB()
    b.RC()                                 # shadow flags
    ce["vs"] = (b.B(), b.B(), b.B())
    b.BS()                                 # invisibility
    b.RC()                                 # line weight
    return ce


def _entity_handles(o: _Obj, ce: dict) -> dict:
    out = {}
    if ce["entmode"] == 0:
        out["owner"] = o.ref()
    for _ in range(ce["nreact"]):
        o.ref()
    if not ce["xdic_missing"]:
        o.ref()
    if ce["color_flags"] & 0x40:
        o.ref()
    out["layer"] = o.ref()
    for k in ("lt", "mat", "ps"):
        if ce[k] == 3:
            o.ref()
    for flag in ce["vs"]:                  # visual styles (R2010+)
        if flag:
            o.ref()
    return out


def _text_fields(o: _Obj) -> dict:
    b = o.b
    df = b.RC()
    if not df & 1:
        b.RD()
    x, y = b.RD(), b.RD()
    if not df & 2:
        b.DD(x)
        b.DD(y)
    b.BE()
    b.BT()
    if not df & 4:
        b.RD()
    rot = 0.0 if df & 8 else b.RD()
    b.RD()                                 # height
    if not df & 0x10:
        b.RD()
    value = o.text()
    for flag in (0x20, 0x40, 0x80):
        if not df & flag:
            b.BS()
    return {"x": x, "y": y, "rot": rot, "text": value}


def decode_object(buf: bytes, off: int, version: str) -> dict | None:
    """Decode one object. Returns None for object types the design model does not use."""
    o = _open(buf, off)
    t = o.type
    if t not in DECODED:
        return None
    rec = {"handle": o.handle, "type": t}
    has_ds = version >= "AC1027"
    b = o.b
    if t in (BLOCK_HEADER, LAYER):
        b.BL()                             # reactors
        b.B()                              # xdic missing
        if has_ds:
            b.B()
        rec["name"] = o.text()
        return rec
    ce = _entity_common(o, has_ds)
    rec["entmode"] = ce["entmode"]
    if t in (TEXT, ATTRIB):
        rec.update(_text_fields(o))
        if t == ATTRIB:
            b.RC()                         # class version (R2010+)
            if version >= "AC1032":
                rec["atype"] = b.RC()     # R2018: 1 = single-line attribute
                rec["tag"] = o.text() if rec["atype"] <= 1 else None
            else:
                rec["tag"] = o.text()
    elif t == INSERT:
        rec["x"], rec["y"] = b.BD(), b.BD()
        b.BD()                             # z
        sf = b.BB()
        if sf == 1:
            b.DD(1.0)
            b.DD(1.0)
        elif sf == 2:
            b.RD()
        elif sf == 0:
            sx = b.RD()
            b.DD(sx)
            b.DD(sx)
        rec["rot"] = b.BD()
        b.BD()
        b.BD()
        b.BD()                             # extrusion
        has_att = b.B()
        n_owned = b.BL() if has_att else 0
        rec.update(_entity_handles(o, ce))
        rec["block"] = o.ref()
        rec["attribs"] = [o.ref() for _ in range(n_owned)]
        return rec
    elif t == MTEXT:
        rec["x"], rec["y"] = b.BD(), b.BD()
        b.BD()                             # z
        for _ in range(3):
            b.BD()                         # extrusion
        for _ in range(3):
            b.BD()                         # x-axis direction
        b.BD()
        b.BD()                             # rectangle width, height
        b.BD()                             # text height
        b.BS()
        b.BS()
        b.BD()
        b.BD()
        rec["text"] = o.text()
    elif t == LWPOLYLINE:
        fl = b.BS()
        if fl & 4:
            b.BD()
        if fl & 8:
            b.BD()
        if fl & 2:
            b.BD()
        if fl & 1:
            b.BD()
            b.BD()
            b.BD()
        n = b.BL()
        if fl & 16:
            b.BL()
        if fl & 1024:
            b.BL()
        if fl & 32:
            b.BL()
        px, py = b.RD(), b.RD()
        pts = [(px, py)]
        for _ in range(n - 1):
            px, py = b.DD(px), b.DD(py)
            pts.append((px, py))
        rec["points"] = pts
    elif t == LINE:
        z_zero = b.B()
        x1 = b.RD()
        x2 = b.DD(x1)
        y1 = b.RD()
        y2 = b.DD(y1)
        if not z_zero:
            z1 = b.RD()
            b.DD(z1)
        rec["points"] = [(x1, y1), (x2, y2)]
    rec.update(_entity_handles(o, ce))
    return rec


@dataclass
class DwgObjects:
    version: str
    records: dict[int, dict] = field(default_factory=dict)
    objects: int = 0
    errors: int = 0


def read_objects(container: DwgContainer) -> DwgObjects:
    """Decode the objects the design model uses. Unknown types are skipped; decoding errors are counted."""
    if container.version not in OBJECT_DECODE_VERSIONS:
        raise DwgError(f"object decoding supports {', '.join(OBJECT_DECODE_VERSIONS)} (AutoCAD 2010-2018 "
                       f"formats); this drawing is {container.version}. Save it as AutoCAD 2018 DWG or export "
                       f"a DXF.")
    buf = container.section("AcDb:AcDbObjects")
    hmap = handle_map(container.section("AcDb:Handles"))
    out = DwgObjects(container.version, objects=len(hmap))
    for h, off in hmap.items():
        try:
            rec = decode_object(buf, off, container.version)
        except (DwgError, IndexError, struct.error, ValueError):  # damaged or unexpected object
            out.errors += 1
            continue
        if rec is not None:
            out.records[h] = rec
    return out
