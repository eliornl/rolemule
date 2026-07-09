/**
 * Unified frontend build:
 * 1) Legacy esbuild minify/hash for CSS + unconverted JS (build.mjs)
 * 2) Vite IIFE bundles for TypeScript entries (build-vite.mjs)
 * 3) Merge vite-manifest.json over legacy manifest (TS wins on same key)
 */
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync, unlinkSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const UI_ROOT = resolve(__dirname, '..');
const OUT_DIR = join(UI_ROOT, 'static/dist');
const MANIFEST = join(OUT_DIR, 'manifest.json');
const VITE_MANIFEST = join(OUT_DIR, 'vite-manifest.json');

function run(command, args) {
  const result = spawnSync(command, args, {
    cwd: UI_ROOT,
    stdio: 'inherit',
    shell: false,
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

// 1) Legacy pipeline (CSS always; JS for files not overridden by Vite)
run(process.execPath, ['build.mjs']);

// 2) Vite TS entries
run(process.execPath, ['scripts/build-vite.mjs']);

// 3) Merge manifests — Vite overrides legacy for the same key
const legacy = existsSync(MANIFEST)
  ? JSON.parse(readFileSync(MANIFEST, 'utf8'))
  : {};
const vite = existsSync(VITE_MANIFEST)
  ? JSON.parse(readFileSync(VITE_MANIFEST, 'utf8'))
  : {};

const viteKeys = new Set(Object.keys(vite));
const merged = { ...legacy, ...vite };

// Drop stale legacy hashed files from manifest awareness is enough;
// leftover files in dist are harmless. Optionally we could delete legacy
// outputs for overridden keys — do that to avoid confusion.
for (const key of viteKeys) {
  const legacyRel = legacy[key];
  if (legacyRel && legacyRel !== vite[key]) {
    const legacyPath = join(OUT_DIR, legacyRel);
    if (existsSync(legacyPath)) {
      try { unlinkSync(legacyPath); } catch { /* ignore */ }
    }
  }
}

writeFileSync(MANIFEST, JSON.stringify(merged, null, 2));
console.log(
  `✓ Merged manifest: ${Object.keys(merged).length} entries`
  + ` (${viteKeys.size} from Vite)`,
);
