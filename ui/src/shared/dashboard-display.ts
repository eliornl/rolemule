/**
 * Job title / company display helpers — keep in sync across dashboard + application detail.
 */

const PLACEHOLDER_COMPANY_LITERALS = new Set([
  '-', '–', '—', '−',
  'n/a', 'na', 'unknown', 'null', 'none',
  'not specified', 'not stated', 'tbd', 'confidential', 'undisclosed',
  '...',
]);

const PLACEHOLDER_TITLE_LITERALS = new Set([
  'show more', 'show less', 'see more', 'easy apply', 'apply now',
  'show more options', 'share', 'save', 'hide', 'report', 'dismiss',
]);

export function isPlaceholderCompanyName(raw: unknown): boolean {
  if (raw == null) return true;
  const s = String(raw).trim();
  if (!s) return true;
  const lower = s.toLowerCase();
  if (PLACEHOLDER_COMPANY_LITERALS.has(lower)) return true;
  if (/^[\s\-–—−]+$/u.test(s)) return true;
  return false;
}

export function isPlaceholderJobTitle(raw: unknown): boolean {
  if (raw == null) return true;
  const s = String(raw).trim();
  if (!s) return true;
  return PLACEHOLDER_TITLE_LITERALS.has(s.toLowerCase());
}

export function displayCompanyNameOrUnknown(raw: unknown): string {
  if (isPlaceholderCompanyName(raw)) return 'Unknown';
  return String(raw).trim();
}
