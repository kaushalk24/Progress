"""Entity/table decoders on top of dwgobjects (R2013/R2018 bit layout). Analysis use only."""
import sys, os, math, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dwgobjects import Dwg, BitReader, string_stream, ENTITY_TYPES


def cmc_obj(br, ss):
    idx = br.BS(); rgb = br.BL(); flag = br.RC()
    name = book = None
    if flag & 1: name = ss.TU()
    if flag & 2: book = ss.TU()
    return color_from_rgb(rgb, idx)


def color_from_rgb(rgb, idx=None):
    method = rgb >> 24
    if method == 0xC0: return {'kind': 'ByBlock', 'aci': 0}
    if method == 0xC1: return {'kind': 'ByLayer', 'aci': 256}
    if method == 0xC2: return {'kind': 'TrueColor', 'rgb': '#%06X' % (rgb & 0xFFFFFF)}
    if method == 0xC3: return {'kind': 'ACI', 'aci': rgb & 0xFF}
    if method == 0xC8: return {'kind': 'None'}
    return {'kind': 'raw', 'rgb': rgb, 'idx': idx}


def enc(br):
    raw = br.BS()
    flags = raw >> 8
    index = raw & 0x1FF
    out = {'aci': index}
    if flags & 0x80:
        rgb = br.BL()
        out = color_from_rgb(rgb)
    if flags & 0x20:
        out['transparency'] = br.BL()
    out['_book'] = bool(flags & 0x40)
    return out


def parse_eed(dwg, eed_list, appnames):
    res = []
    for app, raw in eed_list:
        items = []
        i = 0
        try:
            while i < len(raw):
                code = raw[i]; i += 1
                if code == 0:
                    n = struct.unpack_from('<H', raw, i)[0]; i += 2
                    items.append((1000, raw[i:i + 2 * n].decode('utf-16-le', 'replace'))); i += 2 * n
                elif code == 2:
                    items.append((1002, '{' if raw[i] == 0 else '}')); i += 1
                elif code in (3, 5):
                    items.append((1000 + code, raw[i:i + 8].hex().lstrip('0').upper())); i += 8
                elif code == 4:
                    n = raw[i]; i += 1
                    items.append((1004, raw[i:i + n].hex())); i += n
                elif 10 <= code <= 13:
                    items.append((1000 + code, struct.unpack_from('<3d', raw, i))); i += 24
                elif 40 <= code <= 42:
                    items.append((1000 + code, struct.unpack_from('<d', raw, i)[0])); i += 8
                elif code == 70:
                    items.append((1070, struct.unpack_from('<h', raw, i)[0])); i += 2
                elif code == 71:
                    items.append((1071, struct.unpack_from('<i', raw, i)[0])); i += 4
                else:
                    items.append(('?', raw[i - 1:].hex())); break
        except Exception as e:
            items.append(('err', str(e)))
        res.append((appnames.get(app, hex(app)), items))
    return res


class Reader:
    def __init__(self, path):
        self.d = Dwg(path)
        self.layers = {}
        self.styles = {}
        self.ltypes = {}
        self.blocks = {}
        self.appids = {}
        self.mlstyles = {}
        self._tables()

    # ---------- common ----------
    def _nonent_common(self, o):
        br = o.br
        o.nreact = br.BL()
        o.xdic_missing = br.B()
        o.has_ds = br.B()
        o.ss = string_stream(br, o.endbit)
        o.hs = BitReader(self.d.objs, o.endbit, o.start + o.size * 8)

    def _table_name(self, o):
        name = o.ss.TU() if o.ss else ''
        o.br.B(); o.br.B()
        return name

    def _obj_handles_common(self, o):
        hs = o.hs
        owner = hs.H(o.handle)[1]
        for _ in range(o.nreact): hs.H(o.handle)
        if not o.xdic_missing: hs.H(o.handle)
        return owner

    def _tables(self):
        d = self.d
        for h in d.omap:
            o = d.header(h)
            t = o.type
            if t in (51, 53, 57, 49, 67):
                self._nonent_common(o)
                name = self._table_name(o)
                br = o.br
                if t == 51:
                    flags = br.BS()
                    col = cmc_obj(br, o.ss)
                    hs = o.hs
                    self._obj_handles_common(o)
                    hs.H(h)  # xref block
                    hs.H(h)  # plotstyle
                    hs.H(h)  # material
                    lt = hs.H(h)[1]
                    self.layers[h] = dict(name=name, flags=flags, frozen=bool(flags & 1), off=bool(flags & 2),
                                          locked=bool(flags & 8), plot=bool(flags & 16),
                                          lineweight=(flags & 0x3E0) >> 5, color=col, ltype_h=lt)
                elif t == 53:
                    vertical = br.B(); shape = br.B()
                    fixed_h = br.BD(); wf = br.BD(); obl = br.BD(); gen = br.RC(); last_h = br.BD()
                    font = o.ss.TU(); bigfont = o.ss.TU()
                    self.styles[h] = dict(name=name, fixed_height=fixed_h, width_factor=wf, oblique=obl,
                                          generation=gen, last_height=last_h, font=font, bigfont=bigfont,
                                          vertical=vertical, shape=shape)
                elif t == 57:
                    self.ltypes[h] = name
                elif t == 49:
                    self.blocks[h] = name
                elif t == 67:
                    self.appids[h] = name
        for v in self.layers.values():
            v['linetype'] = self.ltypes.get(v.pop('ltype_h'), '?')

    def entity(self, h):
        d = self.d
        o = d.header(h)
        t = o.type
        tn = d.typename(t)
        if not (t in ENTITY_TYPES or (t >= 500 and d.classes.get(t, {}).get('item') == 0x1F2) or t == 498):
            return None
        br = o.br
        e = {'handle': '%X' % h, 'type': tn}
        if br.B():
            gsize = br.BLL()
            br.p += gsize * 8
        o.entmode = br.BB()
        o.nreact = br.BL()
        o.xdic_missing = br.B()
        o.has_ds = br.B()
        e['color'] = enc(br)
        e['ltscale'] = br.BD()
        ltf = br.BB(); psf = br.BB(); mtf = br.BB(); br.RC()
        fvs = br.B(); fcvs = br.B(); evs = br.B()
        e['invisible'] = br.BS()
        lw = br.RC()
        e['lineweight_raw'] = lw
        e['space'] = {0: 'block', 1: 'paper', 2: 'model'}.get(o.entmode, '?')
        ss = string_stream(br, o.endbit)
        hs = BitReader(d.objs, o.endbit, o.start + o.size * 8)
        if o.entmode == 0:
            e['owner'] = '%X' % hs.H(h)[1]
        reactors = [hs.H(h)[1] for _ in range(o.nreact)]
        if reactors: e['reactors'] = ['%X' % r for r in reactors]
        if not o.xdic_missing: e['xdic'] = '%X' % hs.H(h)[1]
        layer_h = hs.H(h)[1]
        e['layer'] = self.layers.get(layer_h, {}).get('name', '?%X' % layer_h)
        if ltf == 3: e['linetype'] = self.ltypes.get(hs.H(h)[1], '?')
        else: e['linetype'] = {0: 'ByLayer', 1: 'ByBlock', 2: 'Continuous'}[ltf]
        if mtf == 3: hs.H(h)
        if psf == 3: hs.H(h)
        if fvs: hs.H(h)
        if fcvs: hs.H(h)
        if evs: hs.H(h)
        if o.eed:
            e['eed'] = parse_eed(d, o.eed, self.appids)
        ss_start = ss.p if ss else o.endbit
        try:
            fn = getattr(self, '_e_' + tn, None)
            if fn:
                fn(e, br, ss, hs, h)
                e['_bitgap'] = ss_start - br.p
        except Exception as ex:
            e['decode_error'] = repr(ex)
        return e

    # ---------- per type ----------
    def _text_common(self, e, br, ss):
        df = br.RC()
        elev = 0.0 if df & 1 else br.RD()
        ins = br.P2RD()
        align = br.P2RD() if False else None
        if not df & 2:
            align = (br.DD(ins[0]), br.DD(ins[1]))
        e['extrusion'] = br.BE()
        e['thickness'] = br.BT()
        e['oblique'] = 0.0 if df & 4 else br.RD()
        e['rotation_deg'] = 0.0 if df & 8 else math.degrees(br.RD())
        e['height'] = br.RD()
        e['width_factor'] = 1.0 if df & 0x10 else br.RD()
        e['text'] = ss.TU()
        e['generation'] = 0 if df & 0x20 else br.BS()
        e['halign'] = 0 if df & 0x40 else br.BS()
        e['valign'] = 0 if df & 0x80 else br.BS()
        e['insert'] = (ins[0], ins[1], elev)
        e['align_pt'] = align

    def _e_TEXT(self, e, br, ss, hs, h):
        self._text_common(e, br, ss)
        e['style'] = self.styles.get(hs.H(h)[1], {}).get('name', '?')

    def _e_ATTRIB(self, e, br, ss, hs, h):
        self._text_common(e, br, ss)
        e['class_version'] = br.RC()
        atype = br.RC()
        e['attr_type'] = atype
        if atype > 1:
            e['note'] = 'multiline attribute (not decoded)'
            return
        e['tag'] = ss.TU()
        br.BS(); e['attr_flags'] = br.RC(); br.B()
        e['style'] = self.styles.get(hs.H(h)[1], {}).get('name', '?')

    def _e_ATTDEF(self, e, br, ss, hs, h):
        self._e_ATTRIB(e, br, ss, hs, h)

    def _e_INSERT(self, e, br, ss, hs, h):
        ins = br.P3BD()
        sf = br.BB()
        if sf == 3: sc = (1.0, 1.0, 1.0)
        elif sf == 1:
            sc = (1.0, br.DD(1.0), br.DD(1.0))
        elif sf == 2:
            x = br.RD(); sc = (x, x, x)
        else:
            x = br.RD(); sc = (x, br.DD(x), br.DD(x))
        e['insert'] = ins
        e['scale'] = sc
        e['rotation_deg'] = math.degrees(br.BD())
        e['extrusion'] = br.P3BD()
        has_att = br.B()
        nown = br.BL() if has_att else 0
        bh = hs.H(h)[1]
        e['block'] = self.blocks.get(bh, '?%X' % bh)
        if has_att:
            e['attribs'] = ['%X' % hs.H(h)[1] for _ in range(nown)]
            e['seqend'] = '%X' % hs.H(h)[1]

    def _e_MTEXT(self, e, br, ss, hs, h):
        e['insert'] = br.P3BD()
        e['extrusion'] = br.P3BD()
        xd = br.P3BD()
        e['xdir'] = xd
        e['rotation_deg'] = math.degrees(math.atan2(xd[1], xd[0]))
        e['rect_width'] = br.BD()
        e['rect_height'] = br.BD()
        e['height'] = br.BD()
        e['attachment'] = br.BS()
        e['flow_dir'] = br.BS()
        e['ext_height'] = br.BD(); e['ext_width'] = br.BD()
        e['text'] = ss.TU()
        e['linespacing_style'] = br.BS(); e['linespacing_factor'] = br.BD(); br.B()
        bg = br.BL()
        e['bg_flags'] = bg
        if bg & 0x11:
            e['bg_scale'] = br.BD(); e['bg_color'] = cmc_obj(br, ss); e['bg_transp'] = br.BL()
        e['style'] = self.styles.get(hs.H(h)[1], {}).get('name', '?')

    def _e_LEADER(self, e, br, ss, hs, h):
        br.B()
        e['path_type'] = br.BS(); e['annot_type'] = br.BS()
        n = br.BL()
        e['points'] = [br.P3BD() for _ in range(n)]
        br.P3BD(); br.P3BD(); br.P3BD(); br.P3BD(); br.P3BD()
        e['box_h'] = br.BD(); e['box_w'] = br.BD()
        br.B(); e['arrowhead_on'] = br.B()
        br.BS(); br.B(); br.B()
        ah = hs.H(h)[1]
        e['annotation'] = '%X' % ah if ah else None
        e['dimstyle_h'] = '%X' % hs.H(h)[1]

    def _e_LWPOLYLINE(self, e, br, ss, hs, h):
        fl = br.BS()
        if fl & 4: e['const_width'] = br.BD()
        if fl & 8: e['elevation'] = br.BD()
        if fl & 2: br.BD()
        if fl & 1: br.P3BD()
        n = br.BL()
        nb = br.BL() if fl & 16 else 0
        nid = br.BL() if fl & 1024 else 0
        nw = br.BL() if fl & 32 else 0
        pts = []
        if n:
            p = br.P2RD(); pts.append(p)
            for _ in range(n - 1):
                p = (br.DD(p[0]), br.DD(p[1])); pts.append(p)
        e['closed'] = bool(fl & 512)
        e['points'] = pts

    def _e_LINE(self, e, br, ss, hs, h):
        zflag = br.B()
        x1 = br.RD(); x2 = br.DD(x1); y1 = br.RD(); y2 = br.DD(y1)
        z1 = z2 = 0.0
        if not zflag:
            z1 = br.RD(); z2 = br.DD(z1)
        e['points'] = [(x1, y1, z1), (x2, y2, z2)]

    def _e_POINT(self, e, br, ss, hs, h):
        e['insert'] = br.P3BD()

    def _e_CIRCLE(self, e, br, ss, hs, h):
        e['center'] = br.P3BD(); e['radius'] = br.BD()

    def _e_MULTILEADER(self, e, br, ss, hs, h):
        e['class_version'] = br.BS()
        nlead = br.BL()
        leaders = []
        for _ in range(nlead):
            L = {}
            has_last = br.B(); has_dog = br.B()
            if has_last: L['last_pt'] = br.P3BD()
            if has_dog: L['dogleg_vec'] = br.P3BD()
            nbr = br.BL()
            for _b in range(nbr): br.P3BD(); br.P3BD()
            L['branch_index'] = br.BL()
            L['dogleg_len'] = br.BD()
            nl = br.BL()
            lines = []
            for _l in range(nl):
                np_ = br.BL()
                pts = [br.P3BD() for _p in range(np_)]
                nb = br.BL()
                if nb:
                    br.BL()
                    for _b in range(nb): br.P3BD(); br.P3BD()
                br.BL()
                ltype = br.BS(); col = cmc_obj(br, ss); hs.H(h); lw = br.BLd(); asz = br.BD(); hs.H(h); fl = br.BL()
                lines.append({'points': pts, 'type': ltype, 'color': col, 'lw': lw, 'arrow_size': asz})
            L['lines'] = lines
            L['attach_dir'] = br.BS()
            leaders.append(L)
        e['leaders'] = leaders
        ctx = {}
        ctx['scale'] = br.BD(); ctx['content_base'] = br.P3BD(); ctx['text_height'] = br.BD()
        ctx['arrow_size'] = br.BD(); ctx['landing_gap'] = br.BD()
        ctx['text_left'] = br.BS(); ctx['text_right'] = br.BS(); ctx['text_angletype'] = br.BS(); ctx['text_alignment'] = br.BS()
        has_txt = br.B()
        if has_txt:
            ctx['text'] = ss.TU()
            ctx['normal'] = br.P3BD()
            sh = hs.H(h)[1]
            ctx['text_style'] = self.styles.get(sh, {}).get('name', '?%X' % sh)
            ctx['location'] = br.P3BD(); ctx['direction'] = br.P3BD()
            ctx['rotation_deg'] = math.degrees(br.BD()); ctx['width'] = br.BD(); ctx['height'] = br.BD()
            ctx['ls_factor'] = br.BD(); ctx['ls_style'] = br.BS(); ctx['color'] = cmc_obj(br, ss)
            ctx['alignment'] = br.BS(); ctx['flow'] = br.BS(); ctx['bg_color'] = cmc_obj(br, ss)
            ctx['bg_scale'] = br.BD(); ctx['bg_transp'] = br.BL(); ctx['bg_fill'] = br.B(); ctx['bg_mask_fill'] = br.B()
            ctx['col_type'] = br.BS(); br.B(); br.BD(); br.BD(); br.B()
            nc = br.BL()
            for _c in range(nc): br.BD()
            br.B(); br.B()
        else:
            has_blk = br.B()
            ctx['has_block'] = has_blk
            if has_blk:
                bh = hs.H(h)[1]
                ctx['block'] = self.blocks.get(bh, '?%X' % bh)
                br.P3BD(); ctx['location'] = br.P3BD(); ctx['blk_scale'] = br.P3BD()
                ctx['rotation_deg'] = math.degrees(br.BD()); ctx['color'] = cmc_obj(br, ss)
                for _i in range(16): br.BD()
        ctx['base'] = br.P3BD(); ctx['base_dir'] = br.P3BD(); ctx['base_vert'] = br.P3BD()
        br.B(); ctx['text_top'] = br.BS(); ctx['text_bottom'] = br.BS()
        e['ctx'] = ctx
        ml = hs.H(h)[1]
        e['mleaderstyle_h'] = '%X' % ml
        e['override_flags'] = br.BL()
        e['leader_type'] = br.BS()
        e['line_color'] = cmc_obj(br, ss)
        lth = hs.H(h)[1]
        e['line_ltype'] = self.ltypes.get(lth, '%X' % lth)
        e['line_lw'] = br.BLd()
        e['has_landing'] = br.B(); e['has_dogleg'] = br.B(); e['landing_dist'] = br.BD()
        ah = hs.H(h)[1]; e['arrow_block'] = self.blocks.get(ah, '%X' % ah if ah else 'default(closed filled)')
        e['arrow_size'] = br.BD()
        e['content_type'] = br.BS()
        tsh = hs.H(h)[1]; e['text_style'] = self.styles.get(tsh, {}).get('name', '%X' % tsh)
        e['text_left'] = br.BS(); e['text_right'] = br.BS(); e['text_angletype'] = br.BS(); e['text_alignment'] = br.BS()
        e['text_color'] = cmc_obj(br, ss)
        e['text_frame'] = br.B()
        bsh = hs.H(h)[1]; e['block_style'] = self.blocks.get(bsh, '%X' % bsh)
        e['block_color'] = cmc_obj(br, ss); e['block_scale'] = br.P3BD(); e['block_rot'] = br.BD()
        e['style_attachment'] = br.BS(); e['annotative'] = br.B()
        na = br.BL()
        for _a in range(na): br.B(); hs.H(h)
        e['neg_textdir'] = br.B(); e['ipe_align'] = br.BS(); e['justification'] = br.BS(); e['scale_factor'] = br.BD()
        e['attach_dir'] = br.BS(); e['attach_top'] = br.BS(); e['attach_bottom'] = br.BS()
        e['text_extended'] = br.B()
        e['_main_end_ok'] = True


def all_entities(r):
    out = []
    for h in r.d.omap:
        try:
            e = r.entity(h)
        except Exception as ex:
            e = {'handle': '%X' % h, 'type': 'ERR', 'decode_error': repr(ex)}
        if e is not None:
            out.append(e)
    return out


if __name__ == '__main__':
    import json, collections, time
    t = time.time()
    r = Reader(sys.argv[1])
    print('layers', len(r.layers), 'styles', r.styles, 'appids', list(r.appids.values()))
    ents = all_entities(r)
    print('entities', len(ents), 'time', round(time.time() - t, 1))
    errs = [e for e in ents if 'decode_error' in e]
    print('decode errors', len(errs), collections.Counter(e['type'] for e in errs))
    for e in errs[:5]: print(e)
    with open(sys.argv[2], 'w') as f:
        json.dump({'layers': {('%X' % k): v for k, v in r.layers.items()}, 'styles': {('%X' % k): v for k, v in r.styles.items()},
                   'blocks': {('%X' % k): v for k, v in r.blocks.items()}, 'classes': {str(k): v for k, v in r.d.classes.items()},
                   'entities': ents}, f, default=str)
