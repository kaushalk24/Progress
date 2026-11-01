"""Bit-level object decoder for DWG R2010+ (AC1024..AC1032). Analysis use only."""
import struct, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dwgcontainer import DwgContainer

class BitReader:
    def __init__(self, data, bitpos=0, bitend=None):
        self.d = data
        self.p = bitpos
        self.end = bitend if bitend is not None else len(data) * 8

    def B(self):
        byte = self.d[self.p >> 3]
        v = (byte >> (7 - (self.p & 7))) & 1
        self.p += 1
        return v

    def bits(self, n):
        if n == 0:
            return 0
        p = self.p
        off = p & 7
        nb = (off + n + 7) >> 3
        bi = p >> 3
        chunk = int.from_bytes(self.d[bi:bi + nb], 'big')
        if bi + nb > len(self.d):
            raise IndexError('read past end')
        self.p = p + n
        return (chunk >> (nb * 8 - off - n)) & ((1 << n) - 1)

    def RC(self):
        if self.p & 7 == 0:
            v = self.d[self.p >> 3]; self.p += 8; return v
        return self.bits(8)

    def rawbytes(self, n):
        if self.p & 7 == 0:
            s = self.p >> 3; self.p += 8 * n
            return bytes(self.d[s:s + n])
        return self.bits(8 * n).to_bytes(n, 'big') if n else b''

    def RS(self): return struct.unpack('<H', self.rawbytes(2))[0]
    def RL(self): return struct.unpack('<I', self.rawbytes(4))[0]
    def RD(self): return struct.unpack('<d', self.rawbytes(8))[0]
    def BB(self): return self.bits(2)

    def BS(self):
        c = self.BB()
        if c == 0: return self.RS()
        if c == 1: return self.RC()
        if c == 2: return 0
        return 256

    def BL(self):
        c = self.BB()
        if c == 0: return self.RL()
        if c == 1: return self.RC()
        if c == 2: return 0
        raise ValueError('bad BL code')

    def BLd(self):
        v = self.BL()
        return v - (1 << 32) if v & 0x80000000 else v

    def BD(self):
        c = self.BB()
        if c == 0: return self.RD()
        if c == 1: return 1.0
        if c == 2: return 0.0
        raise ValueError('bad BD code at bit %d' % self.p)

    def BLL(self):
        n = self.bits(3)
        return int.from_bytes(self.rawbytes(n), 'little') if n else 0

    def DD(self, default):
        c = self.BB()
        if c == 0: return default
        b = bytearray(struct.pack('<d', default))
        if c == 1:
            b[0:4] = self.rawbytes(4)
        elif c == 2:
            x = self.rawbytes(6)
            b[4:6] = x[0:2]; b[0:4] = x[2:6]
        else:
            return self.RD()
        return struct.unpack('<d', bytes(b))[0]

    def BT(self):
        return 0.0 if self.B() else self.BD()

    def BE(self):
        if self.B(): return (0.0, 0.0, 1.0)
        return (self.BD(), self.BD(), self.BD())

    def P3BD(self): return (self.BD(), self.BD(), self.BD())
    def P2RD(self): return (self.RD(), self.RD())

    def H(self, ref=0):
        code = self.bits(4); cnt = self.bits(4)
        v = int.from_bytes(self.rawbytes(cnt), 'big') if cnt else 0
        if code <= 5: return (code, v)
        if code == 6: return (code, ref + 1)
        if code == 8: return (code, ref - 1)
        if code == 0xA: return (code, ref + v)
        if code == 0xC: return (code, ref - v)
        return (code, v)

    def TU(self):
        n = self.BS()
        raw = self.rawbytes(2 * n)
        return raw.decode('utf-16-le', 'replace').rstrip('\0')

    def MC_signed(self):
        # byte aligned modular char
        result = 0; shift = 0
        while True:
            b = self.RC()
            if b & 0x80:
                result |= (b & 0x7F) << shift; shift += 7
            else:
                neg = b & 0x40
                result |= (b & 0x3F) << shift
                return -result if neg else result

    def UMC(self):
        result = 0; shift = 0
        while True:
            b = self.RC()
            result |= (b & 0x7F) << shift; shift += 7
            if not b & 0x80:
                return result

    def MS(self):
        result = 0; shift = 0
        while True:
            w = self.RS()
            result |= (w & 0x7FFF) << shift; shift += 15
            if not w & 0x8000:
                return result


def read_object_map(data):
    omap = {}
    pos = 0
    n = len(data)
    while pos + 2 <= n:
        size = struct.unpack_from('>H', data, pos)[0]
        if size == 2:
            break
        start = pos
        pos += 2
        lh = 0; lo = 0
        br = BitReader(data, pos * 8)
        while (br.p >> 3) < start + size:
            lh += br.UMC()
            lo += br.MC_signed()
            omap[lh] = lo
        pos = start + size + 2  # skip CRC
    return omap


class ObjHeader:
    pass


def string_stream(br, endbit):
    """Locate the R2007+ string stream inside [0,endbit). Returns BitReader or None."""
    p = endbit - 1
    r = BitReader(br.d, p)
    if not r.B():
        return None
    p -= 16
    r = BitReader(br.d, p)
    size = r.RS()
    if size & 0x8000:
        p -= 16
        r = BitReader(br.d, p)
        hi = r.RS()
        size = (size & 0x7FFF) | (hi << 15)
    p -= size
    return BitReader(br.d, p)


class Dwg:
    def __init__(self, path):
        self.c = DwgContainer(path)
        self.objs = self.c.section('AcDb:AcDbObjects')
        self.omap = read_object_map(self.c.section('AcDb:Handles'))
        self.classes = self._read_classes()

    def _read_classes(self):
        data = self.c.section('AcDb:Classes')
        br = BitReader(data, 16 * 8)
        size = br.RL()
        hsize = br.RL()
        bitsize = br.RL()
        ss = string_stream(br, 192 + bitsize)
        max_num = br.BS(); br.RC(); br.RC(); br.B()
        classes = {}
        while br.p < 192 + bitsize:
            num = br.BS()
            pflags = br.BS()
            app = ss.TU(); cpp = ss.TU(); dxf = ss.TU()
            zombie = br.B(); itemid = br.BS()
            ninst = br.BL(); dv = br.BL(); mv = br.BL(); br.BL(); br.BL()
            classes[num] = dict(dxf=dxf, cpp=cpp, app=app, item=itemid, n=ninst, proxyflags=pflags)
            if num >= max_num:
                break
        return classes

    def header(self, handle):
        loc = self.omap[handle]
        br = BitReader(self.objs, loc * 8)
        size = br.MS()
        hsize = br.UMC()
        o = ObjHeader()
        o.loc = loc
        o.start = br.p
        o.size = size
        o.hsize = hsize
        o.endbit = br.p + size * 8 - hsize   # end of main data + strings
        c = br.BB()
        if c == 0: t = br.RC()
        elif c == 1: t = br.RC() + 0x1F0
        else: t = br.RS()
        o.type = t
        o.handle = br.H()[1]
        # EED
        o.eed = []
        while True:
            esz = br.BS()
            if esz == 0: break
            app = br.H()[1]
            o.eed.append((app, br.rawbytes(esz)))
        o.br = br
        return o

    def typename(self, t):
        if t >= 500:
            c = self.classes.get(t)
            return c['dxf'] if c else 'CLASS%d' % t
        return FIXED_TYPES.get(t, 'TYPE%d' % t)


FIXED_TYPES = {1: 'TEXT', 2: 'ATTRIB', 3: 'ATTDEF', 4: 'BLOCK', 5: 'ENDBLK', 6: 'SEQEND', 7: 'INSERT', 8: 'MINSERT',
               10: 'VERTEX_2D', 11: 'VERTEX_3D', 15: 'POLYLINE_2D', 16: 'POLYLINE_3D', 17: 'ARC', 18: 'CIRCLE', 19: 'LINE',
               20: 'DIMENSION_ORDINATE', 21: 'DIMENSION_LINEAR', 22: 'DIMENSION_ALIGNED', 23: 'DIMENSION_ANG3PT',
               24: 'DIMENSION_ANG2LN', 25: 'DIMENSION_RADIUS', 26: 'DIMENSION_DIAMETER', 27: 'POINT', 28: '3DFACE',
               31: 'SOLID', 34: 'VIEWPORT', 35: 'ELLIPSE', 36: 'SPLINE', 40: 'RAY', 41: 'XLINE', 42: 'DICTIONARY',
               44: 'MTEXT', 45: 'LEADER', 46: 'TOLERANCE', 47: 'MLINE', 48: 'BLOCK_CONTROL', 49: 'BLOCK_HEADER',
               50: 'LAYER_CONTROL', 51: 'LAYER', 52: 'STYLE_CONTROL', 53: 'STYLE', 56: 'LTYPE_CONTROL', 57: 'LTYPE',
               60: 'VIEW_CONTROL', 61: 'VIEW', 62: 'UCS_CONTROL', 63: 'UCS', 64: 'VPORT_CONTROL', 65: 'VPORT',
               66: 'APPID_CONTROL', 67: 'APPID', 68: 'DIMSTYLE_CONTROL', 69: 'DIMSTYLE', 70: 'VP_ENT_HDR_CONTROL',
               71: 'VP_ENT_HDR', 72: 'GROUP', 73: 'MLINESTYLE', 74: 'OLE2FRAME', 76: 'LONG_TRANSACTION',
               77: 'LWPOLYLINE', 78: 'HATCH', 79: 'XRECORD', 80: 'ACDBPLACEHOLDER', 81: 'VBA_PROJECT', 82: 'LAYOUT'}
ENTITY_TYPES = {1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 31, 34, 35, 36,
                40, 41, 44, 45, 46, 47, 74, 77, 78}

if __name__ == '__main__':
    import sys, collections
    d = Dwg(sys.argv[1])
    print('objects in map:', len(d.omap))
    print('classes:', {k: v['dxf'] for k, v in d.classes.items() if isinstance(v, dict)})
    cnt = collections.Counter()
    bad = 0
    for h in d.omap:
        try:
            o = d.header(h)
            if o.handle != h: bad += 1
            cnt[d.typename(o.type)] += 1
        except Exception as e:
            bad += 1
    print('bad', bad)
    for k, v in cnt.most_common():
        print('%-28s %d' % (k, v))
