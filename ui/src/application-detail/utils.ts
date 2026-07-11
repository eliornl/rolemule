export function ensureArray(value: unknown): unknown[] {
  if (Array.isArray(value)) return value;
  if (value === null || value === undefined) return [];
  if (typeof value === 'string') return value.trim() ? [value] : [];
  return [];
}

export function toTitleCase(s: string): string {
  return s ? s.replace(/\w\S*/g, (t) => t.charAt(0).toUpperCase() + t.slice(1).toLowerCase()) : s;
}

/**
 * Format YYYY-MM-DD or ISO into "Mon D, YYYY".
 * Returns '' if missing, unparseable, future, or before Jan 1 2026.
 */
export function formatPostedDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '';
  try {
    const parts = String(dateStr).match(/^(\d{4})-(\d{2})-(\d{2})/);
    const d = parts
      ? new Date(parseInt(parts[1], 10), parseInt(parts[2], 10) - 1, parseInt(parts[3], 10))
      : new Date(dateStr);
    if (Number.isNaN(d.getTime())) return '';
    const now = new Date();
    if (d > now) return '';
    if (d < new Date(2026, 0, 1)) return '';
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return '';
  }
}
