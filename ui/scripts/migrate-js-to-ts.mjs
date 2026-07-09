/**
 * Convert a legacy ui/static/js/<name>.js file into ui/src/pages/<name>.ts
 * (or ui/src/legacy/<name>.ts for shared globals) and register vite.entries.json.
 *
 * Usage: node scripts/migrate-js-to-ts.mjs <manifestKey...>
 * Example: node scripts/migrate-js-to-ts.mjs js/auth-login.js js/auth-register.js
 */
import {
  existsSync, mkdirSync, readFileSync, writeFileSync, unlinkSync,
} from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const UI_ROOT = resolve(__dirname, '..');
const ENTRIES_PATH = join(UI_ROOT, 'vite.entries.json');

function loadEntries() {
  if (!existsSync(ENTRIES_PATH)) return {};
  return JSON.parse(readFileSync(ENTRIES_PATH, 'utf8'));
}

function migrateOne(manifestKey) {
  if (!manifestKey.startsWith('js/') || !manifestKey.endsWith('.js')) {
    throw new Error(`Expected js/<file>.js, got ${manifestKey}`);
  }
  const file = manifestKey.slice(3); // auth-login.js
  const base = file.replace(/\.js$/, '');
  const legacyPath = join(UI_ROOT, 'static/js', file);
  if (!existsSync(legacyPath)) {
    // Already migrated?
    const entries = loadEntries();
    if (entries[manifestKey]) {
      console.log(`skip (already in vite.entries): ${manifestKey}`);
      return;
    }
    throw new Error(`Missing legacy file: ${legacyPath}`);
  }

  const raw = readFileSync(legacyPath, 'utf8');
  const outRel = `src/pages/${base}.ts`;
  const outPath = join(UI_ROOT, outRel);
  mkdirSync(dirname(outPath), { recursive: true });

  const banner = [
    '/**',
    ` * Migrated from ui/static/js/${file}`,
    ' * Behavior preserved 1:1. Typed gradually; @ts-nocheck until fully annotated.',
    ' */',
    '// @ts-nocheck',
    '',
  ].join('\n');

  // Keep IIFE / global scripts as side-effect modules (valid in Vite IIFE build).
  writeFileSync(outPath, banner + raw + (raw.endsWith('\n') ? '' : '\n'));

  const entries = loadEntries();
  entries[manifestKey] = outRel;
  writeFileSync(ENTRIES_PATH, JSON.stringify(entries, null, 2) + '\n');

  unlinkSync(legacyPath);
  console.log(`migrated ${manifestKey} → ${outRel}`);
}

const keys = process.argv.slice(2);
if (keys.length === 0) {
  console.error('Usage: node scripts/migrate-js-to-ts.mjs js/foo.js ...');
  process.exit(1);
}
for (const k of keys) migrateOne(k);
