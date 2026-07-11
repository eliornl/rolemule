/**
 * ApplyPilot legacy CSS build script.
 *
 * Minifies and content-hashes CSS under ui/static/css/.
 * Page JavaScript is built by Vite from ui/src/ (see scripts/build-vite.mjs).
 *
 * Usage:
 *   node build.mjs           # one-shot build
 *   node build.mjs --watch   # rebuild on CSS changes (dev)
 *
 * Output: static/dist/css/<name>.<hash8>.css
 *         static/dist/manifest.json (CSS keys only; merged with Vite in build-all.mjs)
 */

import * as esbuild from 'esbuild';
import { createHash } from 'crypto';
import {
  writeFileSync, mkdirSync, readdirSync, statSync, existsSync,
} from 'fs';
import { join } from 'path';

const WATCH = process.argv.includes('--watch');
const SRC_CSS = 'static/css';
const OUT_DIR = 'static/dist';

function collectFiles(dir, ext, base = '') {
  const results = [];
  if (!existsSync(join(dir, base))) return results;
  for (const entry of readdirSync(join(dir, base), { withFileTypes: true })) {
    const rel = base ? `${base}/${entry.name}` : entry.name;
    if (entry.isDirectory()) {
      results.push(...collectFiles(dir, ext, rel));
    } else if (entry.name.endsWith(ext)) {
      results.push(rel);
    }
  }
  return results;
}

function contentHash(text) {
  return createHash('md5').update(text).digest('hex').slice(0, 8);
}

async function build() {
  const startTime = Date.now();
  const manifest = {};

  mkdirSync(`${OUT_DIR}/css`, { recursive: true });

  const cssFiles = collectFiles(SRC_CSS, '.css');
  let cssCount = 0;

  for (const file of cssFiles) {
    const subdir = file.split('/').slice(0, -1).join('/');
    if (subdir) mkdirSync(join(OUT_DIR, 'css', subdir), { recursive: true });

    const result = await esbuild.build({
      entryPoints: [join(SRC_CSS, file)],
      bundle: true,
      minify: true,
      write: false,
      logLevel: 'silent',
    });

    const text = result.outputFiles[0].text;
    const hash = contentHash(text);
    const outName = file.replace(/\.css$/, `.${hash}.css`);
    const outPath = join(OUT_DIR, 'css', outName);

    writeFileSync(outPath, text);
    manifest[`css/${file}`] = `css/${outName}`;
    cssCount++;
  }

  writeFileSync(join(OUT_DIR, 'manifest.json'), JSON.stringify(manifest, null, 2));

  const elapsed = Date.now() - startTime;
  console.log(`✓ Legacy built ${cssCount} CSS files in ${elapsed}ms → ${OUT_DIR}/manifest.json`);
}

if (WATCH) {
  console.log('Watching CSS for changes…');
  await build();

  const mtimes = new Map();
  const checkFile = (path) => {
    try { return statSync(path).mtimeMs; } catch { return 0; }
  };

  setInterval(async () => {
    const cssFiles = collectFiles(SRC_CSS, '.css');
    let changed = false;
    for (const f of cssFiles.map((rel) => join(SRC_CSS, rel))) {
      const mtime = checkFile(f);
      if (mtimes.get(f) !== mtime) { mtimes.set(f, mtime); changed = true; }
    }
    if (changed) {
      console.log('CSS changed, rebuilding…');
      await build();
    }
  }, 2000);
} else {
  await build();
}
