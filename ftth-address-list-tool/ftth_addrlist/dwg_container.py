"""Minimal, read-only reader for the AutoCAD R2004+ DWG container (AC1018, AC1024, AC1027, AC1032).

It decrypts the file header, reads the page and section maps and decompresses named sections.
It does NOT decode drawing objects (entities, geometry, attribute/tag pairing). Text is recovered
by scanning the decompressed object stream for UTF-16 strings at every bit offset, which finds
most - not all - text values. Use it for an identifier inventory only; for full drawing content
export a DXF (see docs/INPUT_REQUIREMENTS.md).
"""

from __future__ import annotations

import re
import struct
from pathlib import Path


class DwgError(Exception):
    pass


def _decrypt_header(b: bytes) -> bytes:
    out = bytearray(len(b))
    seed = 1
    for i, x in enumerate(b):
        seed = (seed * 0x343FD + 0x269EC3) & 0xFFFFFFFF
        out[i] = x ^ ((seed >> 16) & 0xFF)
    return bytes(out)


def decompress(src: bytes) -> bytes:
    """R2004 LZ77 variant used for DWG section pages."""
    dst = bytearray()
    i = 0

    def rd():
        nonlocal i
        b = src[i]
        i += 1
        return b

    def lit_len(op):
        if op:
            return op + 3
        total, b = 0x0F, rd()
        while b == 0:
            total += 0xFF
            b = rd()
        return total + b + 3

    def long_count():
        total, b = 0, rd()
        while b == 0:
            total += 0xFF
            b = rd()
        return total + b

    def two_byte():
        b1, b2 = rd(), rd()
        return (b1 >> 2) | (b2 << 6), b1 & 3

    op = rd()
    if op < 0x10:
        n = lit_len(op)
        dst += src[i:i + n]
        i += n
        op = rd()
    while op != 0x11:
        if op < 0x10:
            raise DwgError(f"invalid opcode {op:#x}")
        if op == 0x10:
            cb = long_count() + 9
            off, lit = two_byte()
            off += 0x3FFF
        elif op < 0x20:
            cb = (op & 0x0F) + 2
            off, lit = two_byte()
            off += 0x3FFF
        elif op == 0x20:
            cb = long_count() + 0x21
            off, lit = two_byte()
        elif op < 0x40:
            cb = op - 0x1E
            off, lit = two_byte()
        else:
            cb = ((op & 0xF0) >> 4) - 1
            off = (rd() << 2) | ((op & 0x0C) >> 2)
            lit = op & 3
        start = len(dst) - off - 1
        if start < 0:
            raise DwgError("invalid back-reference")
        for k in range(cb):
            dst.append(dst[start + k])
        if lit == 0:
            op = rd()
            if op < 0x10:
                lit = lit_len(op)
                dst += src[i:i + lit]
                i += lit
                op = rd()
        else:
            dst += src[i:i + lit]
            i += lit
            op = rd()
    return bytes(dst)


class DwgContainer:
    SUPPORTED = ("AC1018", "AC1024", "AC1027", "AC1032")

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data = self.path.read_bytes()
        self.version = self.data[:6].decode("ascii", "replace")
        if self.version not in self.SUPPORTED:
            raise DwgError(f"DWG version {self.version} not supported by the built-in reader "
                           f"(supported: {', '.join(self.SUPPORTED)}); export a DXF instead")
        h = _decrypt_header(self.data[0x80:0x80 + 0x6C])
        if not h.startswith(b"AcFssFcAJMB"):
            raise DwgError("DWG file header could not be decoded (file damaged or encrypted)")
        self.page_map_addr = struct.unpack_from("<Q", h, 0x54)[0] + 0x100
        self.section_map_id = struct.unpack_from("<I", h, 0x5C)[0]
        self.pages = self._read_page_map()
        self.sections = self._read_section_map()

    def _system_page(self, addr: int) -> bytes:
        _typ, dsize, csize, ctype, _chk = struct.unpack_from("<IIIII", self.data, addr)
        raw = self.data[addr + 20: addr + 20 + csize]
        return decompress(raw)[:dsize] if ctype == 2 else raw

    def _read_page_map(self) -> dict[int, int]:
        d = self._system_page(self.page_map_addr)
        pages, addr, i = {}, 0x100, 0
        while i + 8 <= len(d):
            num, size = struct.unpack_from("<iI", d, i)
            i += 8
            if num < 0:
                i += 16
            else:
                pages[num] = addr
            addr += size
        return pages

    def _read_section_map(self) -> dict[str, dict]:
        d = self._system_page(self.pages[self.section_map_id])
        nsec = struct.unpack_from("<I", d, 0)[0]
        i, secs = 20, {}
        for _ in range(nsec):
            size, pcount, _maxdec, _unk, comp, sid, enc = struct.unpack_from("<QIIIIII", d, i)
            i += 32
            name = d[i:i + 64].split(b"\0")[0].decode("ascii", "replace")
            i += 64
            plist = []
            for _ in range(pcount):
                pn, _dsz, off = struct.unpack_from("<IIQ", d, i)
                i += 16
                plist.append((pn, off))
            secs[name] = {"size": size, "comp": comp, "id": sid, "enc": enc, "pages": plist}
        return secs

    def section(self, name: str) -> bytes:
        s = self.sections[name]
        if s["enc"] == 1:
            raise DwgError(f"section {name} is encrypted")
        out = bytearray(s["size"])
        for pn, off in s["pages"]:
            addr = self.pages[pn]
            mask = 0x4164536B ^ addr
            hdr = [x ^ mask for x in struct.unpack_from("<8I", self.data, addr)]
            raw = self.data[addr + 32: addr + 32 + hdr[2]]
            dec = decompress(raw) if s["comp"] == 2 else raw
            n = max(0, min(len(dec), s["size"] - off))
            out[off:off + n] = dec[:n]
        return bytes(out)

    def app_info(self) -> list[str]:
        try:
            b = self.section("AcDb:AppInfo")
        except (KeyError, DwgError):
            return []
        return [m.group().decode("utf-16le") for m in re.finditer(rb"(?:[\x20-\x7e]\x00){4,}", b)]

    def text_strings(self, min_len: int = 3) -> list[str]:
        """UTF-16LE strings from the object stream, scanned at all 8 bit phases (R2007+ strings are
        bit-aligned). Includes some noise; filter with identifier patterns."""
        buf = self.section("AcDb:AcDbObjects")
        big = int.from_bytes(buf, "big")
        mask = (1 << (len(buf) * 8)) - 1
        pat = re.compile(rb"(?:[\x20-\x7e]\x00){%d,}" % min_len)
        found = []
        for shift in range(8):
            shifted = ((big << shift) & mask).to_bytes(len(buf), "big")
            found.extend(m.group().decode("utf-16le") for m in pat.finditer(shifted))
        return found
