/**
 * Build each Vite/TS page entry as a standalone IIFE bundle.
 * Reads ui/vite.entries.json: { "js/help.js": "src/pages/help.ts", ... }
 * Writes hashed files under static/dist/js/ and vite-manifest.json for merge.
 */
import { build } from 'vite';
import { createHash } from 'node:crypto';
import {
  existsSync, mkdirSync, readFileSync, writeFileSync, rmSync,
} from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const UI_ROOT = resolve(__dirname, '..');
const OUT_DIR = join(UI_ROOT, 'static/dist');
const ENTRIES_PATH = join(UI_ROOT, 'vite.entries.json');
const TMP_DIR = join(OUT_DIR, 'js', '_vite_tmp');

function contentHash(text) {
  return createHash('md5').update(text).digest('hex').slice(0, 8);
}

function loadEntries() {
  if (!existsSync(ENTRIES_PATH)) return {};
  return JSON.parse(readFileSync(ENTRIES_PATH, 'utf8'));
}

async function buildEntry(manifestKey, relSrc) {
  const absSrc = resolve(UI_ROOT, relSrc);
  if (!existsSync(absSrc)) {
    throw new Error(`Missing Vite entry source for ${manifestKey}: ${relSrc}`);
  }

  const inputName = manifestKey.replace(/^js\//, '').replace(/\.js$/, '');
  const entryOutDir = join(TMP_DIR, inputName);
  mkdirSync(entryOutDir, { recursive: true });

  await build({
    configFile: false,
    root: UI_ROOT,
    publicDir: false,
    logLevel: 'warn',
    resolve: {
      alias: { '@': resolve(UI_ROOT, 'src') },
    },
    build: {
      outDir: entryOutDir,
      emptyOutDir: true,
      sourcemap: false,
      cssCodeSplit: false,
      lib: {
        entry: absSrc,
        name: `ApplyPilot_${inputName.replace(/[^a-zA-Z0-9]/g, '_')}`,
        formats: ['iife'],
        fileName: () => `${inputName}.js`,
      },
      rollupOptions: {
        output: {
          inlineDynamicImports: true,
          assetFileNames: 'assets/[name][extname]',
        },
      },
    },
  });

  const builtPath = join(entryOutDir, `${inputName}.js`);
  if (!existsSync(builtPath)) {
    throw new Error(`Vite did not emit ${builtPath}`);
  }
  return { manifestKey, inputName, builtPath };
}

async function main() {
  const entries = loadEntries();
  const keys = Object.keys(entries);
  mkdirSync(join(OUT_DIR, 'js'), { recursive: true });

  if (keys.length === 0) {
    writeFileSync(join(OUT_DIR, 'vite-manifest.json'), JSON.stringify({}, null, 2));
    console.log('✓ Vite: no entries in vite.entries.json (skip)');
    return;
  }

  if (existsSync(TMP_DIR)) rmSync(TMP_DIR, { recursive: true, force: true });
  mkdirSync(TMP_DIR, { recursive: true });

  const fragment = {};
  for (const [manifestKey, relSrc] of Object.entries(entries)) {
    const { inputName, builtPath } = await buildEntry(manifestKey, relSrc);
    const text = readFileSync(builtPath, 'utf8');
    const hash = contentHash(text);
    const outName = `${inputName}.${hash}.js`;
    const outRel = `js/${outName}`;
    writeFileSync(join(OUT_DIR, 'js', outName), text);
    fragment[manifestKey] = outRel;
    console.log(`  vite ${manifestKey} → ${outRel}`);
  }

  writeFileSync(join(OUT_DIR, 'vite-manifest.json'), JSON.stringify(fragment, null, 2));
  rmSync(TMP_DIR, { recursive: true, force: true });
  console.log(`✓ Vite: built ${keys.length} TS entr${keys.length === 1 ? 'y' : 'ies'}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
