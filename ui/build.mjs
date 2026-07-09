/**
 * ApplyPilot frontend build script.
 *
 * Uses esbuild to minify each JS and CSS file independently (no bundling —
 * the existing vanilla-JS global-scope architecture is preserved).
 * Each output file gets a content-hash suffix for permanent cache busting.
 * A manifest.json is written to ui/static/dist/ so Jinja2 can resolve the
 * hashed filenames at runtime via the asset_url() template global.
 *
 * Usage:
 *   npm run build           # one-shot build
 *   npm run build:watch     # rebuild on file changes (dev)
 *
 * Output: static/dist/{js,css}/<name>.<hash8>.<ext>
 *         static/dist/manifest.json
 */

import * as esbuild from 'esbuild';
import { createHash } from 'crypto';
import {
  writeFileSync, mkdirSync, readdirSync, statSync, existsSync, readFileSync,
} from 'fs';
import { join } from 'path';

// =============================================================================
// CONFIG
// =============================================================================

const WATCH = process.argv.includes('--watch');
const SRC_JS  = 'static/js';
const SRC_CSS = 'static/css';
const OUT_DIR = 'static/dist';
const VITE_ENTRIES_PATH = 'vite.entries.json';

/** Manifest keys owned by Vite/TS — skip legacy minify for these JS files. */
function loadViteOwnedKeys() {
  if (!existsSync(VITE_ENTRIES_PATH)) return new Set();
  try {
    return new Set(Object.keys(JSON.parse(readFileSync(VITE_ENTRIES_PATH, 'utf8'))));
  } catch {
    return new Set();
  }
}

// =============================================================================
// HELPERS
// =============================================================================

/** Recursively collect all files matching an extension under a directory. */
function collectFiles(dir, ext, base = '') {
  const results = [];
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

/** Generate an 8-character content hash for a string. */
function contentHash(text) {
  return createHash('md5').update(text).digest('hex').slice(0, 8);
}

// =============================================================================
// BUILD
// =============================================================================

async function build() {
  const startTime = Date.now();
  const manifest = {};

  mkdirSync(`${OUT_DIR}/js`,  { recursive: true });
  mkdirSync(`${OUT_DIR}/css`, { recursive: true });

  // ── JavaScript ─────────────────────────────────────────────────────────────
  const viteOwned = loadViteOwnedKeys();
  const jsFiles = collectFiles(SRC_JS, '.js');
  let jsCount = 0;
  let skipped = 0;

  for (const file of jsFiles) {
    const manifestKey = `js/${file}`;
    if (viteOwned.has(manifestKey)) {
      skipped++;
      continue; // TypeScript/Vite entry owns this key
    }

    const result = await esbuild.build({
      entryPoints: [join(SRC_JS, file)],
      bundle:   false,   // No import resolution — keeps global-scope intact
      minify:   true,
      write:    false,
      platform: 'browser',
      logLevel: 'silent',
    });

    const text     = result.outputFiles[0].text;
    const hash     = contentHash(text);
    const outName  = file.replace(/\.js$/, `.${hash}.js`);
    const outPath  = join(OUT_DIR, 'js', outName);

    mkdirSync(join(OUT_DIR, 'js', outName.split('/').slice(0, -1).join('/')), { recursive: true });
    writeFileSync(outPath, text);
    manifest[manifestKey] = `js/${outName}`;
    jsCount++;
  }

  // ── CSS ────────────────────────────────────────────────────────────────────
  const cssFiles = collectFiles(SRC_CSS, '.css');
  let cssCount = 0;

  for (const file of cssFiles) {
    const subdir = file.split('/').slice(0, -1).join('/');
    if (subdir) mkdirSync(join(OUT_DIR, 'css', subdir), { recursive: true });

    const result = await esbuild.build({
      entryPoints: [join(SRC_CSS, file)],
      bundle:  true,    // Bundle @import rules if any are present
      minify:  true,
      write:   false,
      logLevel: 'silent',
    });

    const text    = result.outputFiles[0].text;
    const hash    = contentHash(text);
    const outName = file.replace(/\.css$/, `.${hash}.css`);
    const outPath = join(OUT_DIR, 'css', outName);

    writeFileSync(outPath, text);
    manifest[`css/${file}`] = `css/${outName}`;
    cssCount++;
  }

  // ── Manifest ───────────────────────────────────────────────────────────────
  writeFileSync(
    join(OUT_DIR, 'manifest.json'),
    JSON.stringify(manifest, null, 2),
  );

  const elapsed = Date.now() - startTime;
  const skipMsg = skipped ? ` (skipped ${skipped} Vite-owned JS)` : '';
  console.log(
    `✓ Legacy built ${jsCount} JS + ${cssCount} CSS files in ${elapsed}ms${skipMsg} → ${OUT_DIR}/manifest.json`,
  );
}

// =============================================================================
// WATCH MODE
// =============================================================================

if (WATCH) {
  console.log('Watching for changes…');
  await build();

  // Simple polling watcher — re-build every 2s if any file changed
  const mtimes = new Map();
  const checkFile = (path) => {
    try { return statSync(path).mtimeMs; } catch { return 0; }
  };

  setInterval(async () => {
    const jsFiles  = collectFiles(SRC_JS,  '.js');
    const cssFiles = collectFiles(SRC_CSS, '.css');
    let changed = false;

    for (const f of [...jsFiles.map(f => join(SRC_JS, f)), ...cssFiles.map(f => join(SRC_CSS, f))]) {
      const mtime = checkFile(f);
      if (mtimes.get(f) !== mtime) { mtimes.set(f, mtime); changed = true; }
    }

    if (changed) {
      console.log('Changes detected, rebuilding…');
      await build();
    }
  }, 2000);
} else {
  await build();
}
