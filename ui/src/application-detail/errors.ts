import { decodeEntities } from '../shared/dom-security';

const DETAIL_QUOTA_MSG =
  'The AI quota or rate limit for the configured API key was reached. Try again in a little while, review your plan and quotas for that key, or update your key under Settings \u2192 AI Setup.';

/** Application-detail variant — decodes entities on the final string. */
export function formatWorkflowFailureDetailForPage(raw: string | null | undefined): string {
  if (raw == null || typeof raw !== 'string') return '';
  let s = raw.trim();
  if (!s) return '';
  s = s.replace(/^\[[^\]]+\]\s*/u, '').trim();
  if (!s) return '';
  const upper = s.toUpperCase();
  const low = s.toLowerCase();
  if (upper.includes('RESOURCE_EXHAUSTED')) return DETAIL_QUOTA_MSG;
  if (s.includes('429') && (low.includes('quota') || low.includes('exceeded your current quota'))) {
    return DETAIL_QUOTA_MSG;
  }
  if (low.includes('free_tier') && low.includes('quota')) return DETAIL_QUOTA_MSG;
  return decodeEntities(s);
}

export function apiErrorMessage(errData: unknown, fallback: string): string {
  if (!errData || typeof errData !== 'object') return fallback;
  const body = errData as { message?: string; detail?: string };
  const raw =
    typeof body.message === 'string'
      ? body.message
      : typeof body.detail === 'string'
        ? body.detail
        : '';
  if (raw.trim()) {
    const formatted = formatWorkflowFailureDetailForPage(raw);
    return formatted || decodeEntities(raw.trim());
  }
  return fallback;
}

export function workflowFailureMessage(
  errorMessages: string[] | undefined | null,
  fallback: string,
): string {
  if (Array.isArray(errorMessages) && errorMessages.length > 0) {
    const formatted = formatWorkflowFailureDetailForPage(String(errorMessages[0] || ''));
    if (formatted) return formatted;
  }
  return fallback;
}
