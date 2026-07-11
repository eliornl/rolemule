/** Small helpers for resume tips JSON blobs from the Resume Advisor agent. */

export function asResumeRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object'
    ? (value as Record<string, unknown>)
    : {};
}

/** Coerce agent JSON values to strings for display / escapeHtml. */
export function strField(value: unknown): string {
  if (value == null) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return '';
}

export function fieldStr(value: unknown, ...keys: string[]): string {
  const rec = asResumeRecord(value);
  for (const key of keys) {
    const v = rec[key];
    if (typeof v === 'string' && v) return v;
  }
  if (typeof value === 'string') return value;
  return '';
}

export interface LevelExtract {
  level: string;
  levelText: string;
  note: string;
}

export function extractLevel(str: string): LevelExtract {
  const m = str.match(/^(HIGH|MEDIUM|LOW|STRONG|MODERATE)/i);
  if (!m) return { level: 'medium', levelText: str, note: '' };
  return {
    level: m[1].toLowerCase(),
    levelText: m[1].toUpperCase(),
    note: str.slice(m[0].length).replace(/^\s*[-–—]\s*/, '').trim(),
  };
}
