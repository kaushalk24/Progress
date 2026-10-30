"""Decode AutoCAD proxy-entity graphics into polylines.

Map/SpatialNet polygons ("LWPolygon", class ACDBDICTIONARYWDFLT) are stored as
ACAD_PROXY_ENTITY objects. Their only portable geometry is the proxy graphics
stream: [RL total size][RL command count] then commands of
[RL size][RL opcode][data]. Opcode 33 is an embedded bit-coded LWPOLYLINE,
opcode 6/7 are plain polyline/polygon point lists.
"""
from __future__ import annotations

import struct

OP_POLYLINE = 6
OP_POLYGON = 7
OP_LWPOLYLINE = 33


class BitReader:
    """Minimal DWG bit-stream reader (MSB-first bit order, little-endian words)."""

    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def bit(self) -> int:
        byte = self.data[self.pos >> 3]
        v = (byte >> (7 - (self.pos & 7))) & 1
        self.pos += 1
        return v

    def bits(self, n: int) -> int:
        v = 0
        for _ in range(n):
            v = (v << 1) | self.bit()
        return v

    def raw(self, n: int) -> bytes:
        return bytes(self.bits(8) for _ in range(n))

    def rs(self) -> int:
        return struct.unpack("<H", self.raw(2))[0]

    def rl(self) -> int:
        return struct.unpack("<I", self.raw(4))[0]

    def rd(self) -> float:
        return struct.unpack("<d", self.raw(8))[0]

    def bs(self) -> int:
        code = self.bits(2)
        if code == 0:
            return self.rs()
        if code == 1:
            return self.bits(8)
        return 0 if code == 2 else 256

    def bl(self) -> int:
        code = self.bits(2)
        if code == 0:
            return self.rl()
        if code == 1:
            return self.bits(8)
        if code == 2:
            return 0
        raise ValueError("invalid BL code 3")

    def bd(self) -> float:
        code = self.bits(2)
        if code == 0:
            return self.rd()
        if code == 1:
            return 1.0
        if code == 2:
            return 0.0
        raise ValueError("invalid BD code 3")

    def dd(self, default: float) -> float:
        code = self.bits(2)
        if code == 0:
            return default
        if code == 3:
            return self.rd()
        d = bytearray(struct.pack("<d", default))
        if code == 1:
            d[0:4] = self.raw(4)
        else:
            hi = self.raw(2)
            lo = self.raw(4)
            d[4:6] = hi
            d[0:4] = lo
        return struct.unpack("<d", bytes(d))[0]


def decode_lwpolyline(data: bytes) -> tuple[list[tuple[float, float]], bool]:
    """Decode an R2000+ bit-coded LWPOLYLINE body. Returns (points, closed)."""
    r = BitReader(data)
    flag = r.bs()
    if flag & 4:
        r.bd()  # constant width
    if flag & 8:
        r.bd()  # elevation
    if flag & 2:
        r.bd()  # thickness
    if flag & 1:
        r.bd(), r.bd(), r.bd()  # normal
    n = r.bl()
    if flag & 16:
        r.bl()  # bulge count
    if flag & 1024:
        r.bl()  # vertex id count
    if flag & 32:
        r.bl()  # width count
    pts: list[tuple[float, float]] = []
    if n:
        pts.append((r.rd(), r.rd()))
        for _ in range(1, n):
            px, py = pts[-1]
            pts.append((r.dd(px), r.dd(py)))
    closed = bool(flag & 512)
    return pts, closed


def proxy_polylines(graphics: bytes) -> list[tuple[list[tuple[float, float]], bool]]:
    """Return every polyline/polygon found in a proxy graphics stream."""
    out = []
    if len(graphics) < 8:
        return out
    _total, ncmd = struct.unpack_from("<II", graphics, 0)
    off = 8
    for _ in range(ncmd):
        if off + 8 > len(graphics):
            break
        size, op = struct.unpack_from("<II", graphics, off)
        if size < 8:
            break
        body = graphics[off + 8 : off + size]
        off += size
        if op == OP_LWPOLYLINE and len(body) >= 4:
            ln = struct.unpack_from("<I", body, 0)[0]
            out.append(decode_lwpolyline(body[4 : 4 + ln]))
        elif op in (OP_POLYLINE, OP_POLYGON) and len(body) >= 4:
            n = struct.unpack_from("<I", body, 0)[0]
            pts = [struct.unpack_from("<ddd", body, 4 + 24 * i)[:2] for i in range(n) if 4 + 24 * (i + 1) <= len(body)]
            out.append((pts, op == OP_POLYGON))
    return out
