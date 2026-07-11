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

/**
 * Same company label as the dashboard card: prefer Job Analyzer employer, else
 * application/detected header (e.g. recruiting agency on a staffing post).
 */
export function resolveEffectiveCompanyName(options: {
  analysisCompanyName?: unknown;
  applicationCompanyName?: unknown;
  detectedCompany?: unknown;
}): string {
  const { analysisCompanyName, applicationCompanyName, detectedCompany } = options;
  if (!isPlaceholderCompanyName(analysisCompanyName)) {
    return String(analysisCompanyName).trim();
  }
  for (const candidate of [applicationCompanyName, detectedCompany]) {
    if (!isPlaceholderCompanyName(candidate)) {
      return String(candidate).trim();
    }
  }
  return '';
}
