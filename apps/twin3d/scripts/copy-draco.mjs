// The Draco decoder that GLTFLoader needs, copied from three so the app works offline (no CDN).
import { cpSync, existsSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';

const require = createRequire(import.meta.url);
const here = dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'));
const threeDir = join(dirname(require.resolve('three')), '..'); // .../three/build/three.cjs -> .../three
const from = join(threeDir, 'examples', 'jsm', 'libs', 'draco', 'gltf');
const to = join(here, '..', 'public', 'draco');
if (!existsSync(from)) throw new Error(`Draco decoder not found at ${from}`);
mkdirSync(to, { recursive: true });
cpSync(from, to, { recursive: true });
console.log('draco decoder copied to', to);
