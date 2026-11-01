"""Minimal pure-Python reader for the DWG R2004+ (AC1018/AC1024/AC1027/AC1032) container.
Written from the ODA Open Design Specification; read-only, analysis use only."""
import struct

def _decrypt_header(data):
    out = bytearray(len(data))
    seed = 1
    for i, b in enumerate(data):
        seed = (seed * 0x343FD + 0x269EC3) & 0xFFFFFFFF
        out[i] = b ^ ((seed >> 16) & 0xFF)
    return bytes(out)

def decompress(src, out_size):
    out = bytearray()
    pos = 0
    n = len(src)

    def nextb():
        nonlocal pos
        b = src[pos]; pos += 1
        return b

    def lit_len(op):
        if op == 0:
            total = 0x0F
            b = nextb()
            while b == 0:
                total += 0xFF
                b = nextb()
            return total + b + 3
        return op + 3

    def long_off():
        b = nextb()
        if b == 0:
            total = 0xFF
            b = nextb()
            while b == 0:
                total += 0xFF
                b = nextb()
            return total + b
        return b

    def two_byte():
        b1 = nextb(); b2 = nextb()
        return (b1 >> 2) | (b2 << 6), b1 & 0x03

    op = nextb()
    if (op & 0xF0) == 0:
        L = lit_len(op)
        out += src[pos:pos + L]; pos += L
        op = nextb()
    while pos <= n:
        if op == 0x11:
            break
        if op == 0x10:
            cb = long_off() + 9
            off, lit = two_byte(); off += 0x3FFF
        elif 0x12 <= op <= 0x1F:
            cb = (op & 0x0F) + 2
            off, lit = two_byte(); off += 0x3FFF
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
            raise ValueError("bad opcode %#x at %d" % (op, pos))
        start = len(out) - off - 1
        if start < 0:
            raise ValueError("bad back-reference")
        for k in range(cb):
            out.append(out[start + k])
        if lit == 0:
            if pos >= n:
                break
            op = nextb()
            if op < 0x10:
                L = lit_len(op)
                out += src[pos:pos + L]; pos += L
                if pos >= n:
                    break
                op = nextb()
        else:
            out += src[pos:pos + lit]; pos += lit
            if pos >= n:
                break
            op = nextb()
    return bytes(out)

class DwgContainer:
    def __init__(self, path):
        with open(path, 'rb') as f:
            self.raw = f.read()
        self.version = self.raw[0:6].decode('ascii')
        self.maint = self.raw[0x0B]
        self.codepage = struct.unpack_from('<H', self.raw, 0x13)[0]
        hdr = _decrypt_header(self.raw[0x80:0x80 + 0x6C])
        if not hdr.startswith(b'AcFssFcAJMB'):
            raise ValueError('not an R2004+ DWG')
        self.page_map_id = struct.unpack_from('<I', hdr, 0x50)[0]
        self.page_map_addr = struct.unpack_from('<Q', hdr, 0x54)[0] + 0x100
        self.section_map_id = struct.unpack_from('<I', hdr, 0x5C)[0]
        self._read_page_map()
        self._read_section_map()

    def _system_page(self, addr, expect):
        ptype, dsize, csize, ctype, crc = struct.unpack_from('<IIIII', self.raw, addr)
        if ptype != expect:
            raise ValueError('page type %#x != %#x' % (ptype, expect))
        data = self.raw[addr + 20: addr + 20 + csize]
        if ctype == 2:
            data = decompress(data, dsize)
        return data[:dsize]

    def _read_page_map(self):
        data = self._system_page(self.page_map_addr, 0x41630E3B)
        self.pages = {}
        addr = 0x100
        i = 0
        while i + 8 <= len(data):
            num, size = struct.unpack_from('<iI', data, i); i += 8
            if num < 0:
                i += 16
            else:
                self.pages[num] = (addr, size)
            addr += size

    def _read_section_map(self):
        addr, _ = self.pages[self.section_map_id]
        data = self._system_page(addr, 0x4163003B)
        ndesc = struct.unpack_from('<I', data, 0)[0]
        i = 20
        self.sections = {}
        for _ in range(ndesc):
            size, = struct.unpack_from('<Q', data, i); i += 8
            pcount, maxsize, _u, comp, sid, enc = struct.unpack_from('<IIIIII', data, i); i += 24
            name = data[i:i + 64].split(b'\0')[0].decode('ascii', 'replace'); i += 64
            pages = []
            for _p in range(pcount):
                pn, dsz, off = struct.unpack_from('<IIQ', data, i); i += 16
                pages.append((pn, dsz, off))
            self.sections[name] = dict(size=size, maxsize=maxsize, comp=comp, id=sid, enc=enc, pages=pages)

    def section(self, name):
        s = self.sections[name]
        buf = bytearray(s['size'] if s['size'] else 0)
        for pn, dsz, off in s['pages']:
            paddr, _psize = self.pages[pn]
            mask = 0x4164536B ^ paddr
            h = struct.unpack_from('<8I', self.raw, paddr)
            h = [v ^ mask for v in h]
            ptype, secnum, datasize, pagesize, startoff = h[0], h[1], h[2], h[3], h[4]
            if ptype != 0x4163043B:
                raise ValueError('bad data page type %#x' % ptype)
            cdata = self.raw[paddr + 32: paddr + 32 + datasize]
            ddata = decompress(cdata, s['maxsize']) if s['comp'] == 2 else cdata
            end = off + len(ddata)
            if end > len(buf):
                buf.extend(b'\0' * (end - len(buf)))
            buf[off:end] = ddata
        return bytes(buf[:s['size']]) if s['size'] else bytes(buf)

if __name__ == '__main__':
    import sys
    c = DwgContainer(sys.argv[1])
    print(c.version, 'maint', c.maint, 'codepage', c.codepage, 'pages', len(c.pages))
    for k, v in c.sections.items():
        print('%-28s size=%-9d pages=%-4d comp=%d enc=%d' % (k, v['size'], len(v['pages']), v['comp'], v['enc']))
    for name in ('AcDb:Header', 'AcDb:Classes', 'AcDb:Handles', 'AcDb:AcDbObjects'):
        d = c.section(name)
        print(name, len(d), d[:32].hex())
