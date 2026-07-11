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

function transformBody(body, extraReplacements = []) {
  let s = body
    .replace(/^(\s*)function /m, '$1export function ')
    .replace(/^(\s*)async function /m, '$1export async function ')
    .replace(/\bapplicationData\b/g, 'getApplicationData()')
    .replace(/getApplicationData\(\)\s*=\s*/g, 'setApplicationData(')
    .replace(/\(getApplicationData\(\)\)\['([^']+)'\]\s*=/g, "patchApplicationData({ $1:")
    .replace(/getApplicationData\(\)\)\['([^']+)'\]/g, "getApplicationData()?.$1");

  // Fix setApplicationData patterns from `applicationData = x`
  s = s.replace(/getApplicationData\(\) = /g, 'setApplicationData(');
  // Fix `if (applicationData)` -> already getApplicationData()
  // Fix assignments like `(applicationData)['x'] =` - manual in actions

  for (const [from, to] of extraReplacements) {
    s = s.replaceAll(from, to);
  }
  return s;
}

console.log('Extract test renderHeader length:', extractFn('renderHeader').length);
