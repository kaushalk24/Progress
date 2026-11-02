// Self-test of the DWG reader: loads LibreDWG (WebAssembly) and exits 0. Used by the packaged app's --selftest.
import { LibreDwg } from '@mlightcad/libredwg-web';
import path from 'path';
import { fileURLToPath } from 'url';

const here = path.dirname(fileURLToPath(import.meta.url));
await LibreDwg.create(path.join(here, 'node_modules/@mlightcad/libredwg-web/wasm/'));
console.log('dwg reader ok');
