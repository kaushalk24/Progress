// DWG -> slim JSON converter for fttx_bom.
// Uses LibreDWG compiled to WebAssembly (@mlightcad/libredwg-web, pinned in package.json).
// Usage: node dwg2json.mjs <input.dwg> <output.json>
// Output keeps only what the BOM engine needs, plus a census of every entity
// type so unsupported objects are reported instead of silently dropped.
import { Dwg_File_Type, LibreDwg } from '@mlightcad/libredwg-web';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const here = path.dirname(fileURLToPath(import.meta.url));
const [, , inFile, outFile] = process.argv;
if (!inFile || !outFile) {
  console.error('usage: node dwg2json.mjs <input.dwg> <output.json>');
  process.exit(2);
}
const wasmDir = path.join(here, 'node_modules/@mlightcad/libredwg-web/wasm/');
const libredwg = await LibreDwg.create(wasmDir);
const buf = fs.readFileSync(inFile);
const dwg = libredwg.dwg_read_data(buf, Dwg_File_Type.DWG);
if (!dwg) {
  console.error('libredwg could not read ' + inFile);
  process.exit(3);
}
const db = libredwg.convert(dwg);

const pt = (p) => (p ? [p.x, p.y] : null);
const census = {};
const blockCensus = {};

function slim(e) {
  const base = { t: e.type, h: e.handle, l: e.layer };
  switch (e.type) {
    case 'INSERT':
      return {
        ...base,
        n: e.name,
        p: pt(e.insertionPoint),
        r: e.rotation || 0,
        sx: e.xScale ?? 1,
        sy: e.yScale ?? 1,
        a: (e.attribs || []).map((a) => [a.tag, a.text ? a.text.text : '', a.layer]),
      };
    case 'LWPOLYLINE':
      return {
        ...base,
        v: (e.vertices || []).map((v) => [v.x, v.y, v.bulge || 0]),
        f: e.flag || 0,
      };
    case 'LINE':
      return { ...base, v: [pt(e.startPoint), pt(e.endPoint)] };
    case 'POLYLINE2D':
    case 'POLYLINE':
      return { ...base, v: (e.vertices || []).map((v) => [v.point?.x ?? v.x, v.point?.y ?? v.y, v.bulge || 0]), f: e.flag || 0 };
    case 'TEXT':
      return { ...base, s: e.text, p: pt(e.startPoint) };
    case 'MTEXT':
      return { ...base, s: e.text, p: pt(e.insertionPoint) };
    case 'MULTILEADER':
      return { ...base, s: e.textContent || '' };
    case 'LEADER':
      return { ...base, v: (e.vertices || []).map(pt) };
    case 'CIRCLE':
      return { ...base, p: pt(e.center), rad: e.radius };
    case 'ACAD_PROXY_ENTITY':
      return { ...base, g: e.graphicsData || '', cls: e.originalDxfName || '' };
    default:
      return null;
  }
}

const entities = [];
for (const e of db.entities) {
  census[e.type] = (census[e.type] || 0) + 1;
  const s = slim(e);
  if (s) entities.push(s);
}
for (const b of db.tables?.BLOCK_RECORD?.entries || []) {
  const c = {};
  for (const e of b.entities || []) c[e.type] = (c[e.type] || 0) + 1;
  blockCensus[b.name] = c;
}
// Custom-class entities that the converter skips (e.g. Map/SpatialNet SNMPOLYGON boundary polygons when
// they are not stored as ACAD_PROXY_ENTITY): keep their drawable graphics (the entity "preview" carries the
// proxy graphics) so the Non-Grant and network boundaries are not silently lost.
const layerByHandle = new Map((db.tables?.LAYER?.entries || []).map((l) => [String(l.handle), l.name]));
const w = libredwg.wasmInstance;
const UNKNOWN_ENT = 65534;
let recovered = 0;
if (w && w.dwg_get_num_objects) {
  const n = w.dwg_get_num_objects(dwg);
  for (let i = 0; i < n; i++) {
    const obj = w.dwg_get_object(dwg, i);
    if (!obj || w.dwg_object_get_fixedtype(obj) !== UNKNOWN_ENT) continue;
    let dxf = 'UNKNOWN';
    try {  // class name from the classes section (type 500+n -> class n), e.g. SNMPOLYGON
      const cls = libredwg.dwg_get_class(dwg, w.dwg_object_get_type(obj) - 500);
      dxf = cls?.dxfname || (w.dwg_object_get_dxfname && w.dwg_object_get_dxfname(obj)) || 'UNKNOWN';
    } catch (err) { dxf = 'UNKNOWN'; }
    census['CUSTOM:' + dxf] = (census['CUSTOM:' + dxf] || 0) + 1;
    let g = null;
    try { g = libredwg.dwg_entity_get_preview(obj); } catch (err) { g = null; }
    if (!g || !g.length) continue;
    let layer = '';
    try {
      const ent = libredwg.dwg_object_to_entity(obj);
      const ref = libredwg.dwg_object_entity_get_layer_object_ref(ent);
      const hv = ref?.handleref?.value;
      layer = layerByHandle.get(String(hv)) ?? layerByHandle.get(Number(hv).toString(16).toUpperCase()) ?? '';
    } catch (err) { layer = ''; }
    let handle = '';
    try { const ho = libredwg.dwg_object_get_handle_object(obj); handle = (ho?.value ?? '').toString(16).toUpperCase(); } catch (err) { handle = ''; }
    entities.push({ t: 'ACAD_PROXY_ENTITY', h: handle || 'custom' + i, l: layer, g: Buffer.from(g).toString('hex'), cls: dxf });
    recovered++;
  }
}
const header = db.header || {};
const out = {
  source: path.basename(inFile),
  backend: 'libredwg-web@0.8.0',
  header: { INSUNITS: header.INSUNITS, LUNITS: header.LUNITS, MEASUREMENT: header.MEASUREMENT },
  layers: (db.tables?.LAYER?.entries || []).map((l) => l.name),
  census,
  blockCensus,
  entities,
};
fs.writeFileSync(outFile, JSON.stringify(out));
libredwg.dwg_free(dwg);
console.error(`ok: ${entities.length} entities kept of ${db.entities.length}; ${recovered} custom entities recovered from their graphics`);
