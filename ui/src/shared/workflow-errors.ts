/**
 * Shorten noisy Gemini quota / rate-limit errors for dashboard toasts.
 */
export function formatWorkflowFailureDetail(raw: string | null | undefined): string {
  if (raw == null || typeof raw !== 'string') return '';
  let s = raw.trim();
  if (!s) return '';
  // Legacy rows: "[job_analyzer] …" — users do not need agent names in toasts
  s = s.replace(/^\[[^\]]+\]\s*/u, '').trim();
  if (!s) return '';
  const upper = s.toUpperCase();
  const low = s.toLowerCase();
  const quotaMsg =
    'The AI quota or rate limit for the configured API key was reached. Try again later, or review your key under Settings → AI Setup.';
  if (upper.includes('RESOURCE_EXHAUSTED')) return quotaMsg;
  if (s.includes('429') && (low.includes('quota') || low.includes('exceeded your current quota'))) {
    return quotaMsg;
  }
  if (low.includes('free_tier') && low.includes('quota')) return quotaMsg;
  return s;
}
