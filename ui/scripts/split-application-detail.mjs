#!/usr/bin/env node
/**
 * One-time extractor: splits application-detail.ts functions into modules.
 * Preserves function bodies; adds exports and import headers per module.
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(__dirname, '..');
const srcPath = path.join(root, 'src/pages/application-detail.ts');
const src = fs.readFileSync(srcPath, 'utf8');

/** Extract function body starting at `function name` or `async function name`. */
function extractFn(name) {
  const patterns = [
    new RegExp(`async function ${name}\\s*\\(`),
    new RegExp(`function ${name}\\s*\\(`),
  ];
  let start = -1;
  for (const re of patterns) {
    const m = re.exec(src);
    if (m) {
      start = m.index;
      break;
    }
  }
  if (start < 0) throw new Error(`Function not found: ${name}`);

  let i = src.indexOf('{', start);
  if (i < 0) throw new Error(`No brace for ${name}`);
  let depth = 0;
  const begin = start;
  for (; i < src.length; i++) {
    const ch = src[i];
    if (ch === '{') depth++;
    else if (ch === '}') {
      depth--;
      if (depth === 0) {
        return src.slice(begin, i + 1);
      }
    }
  }
  throw new Error(`Unclosed function ${name}`);
}

console.log('Extract test renderHeader length:', extractFn('renderHeader').length);
