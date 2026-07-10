/**
 * Cross-page workflow session tracking — badge dot + tracked sessions list.
 * Keys must stay in sync with dashboard-home and dashboard-new-application.
 */

export const TRACKED_SESSIONS_KEY = 'applypilot_tracked_sessions';
export const NAV_BADGE_KEY = 'applypilot_badge';
export const NOTIFIED_ANALYSES_KEY = 'applypilot_notified_analyses';

export interface TrackedSession {
  sessionId: string;
}

const DONE_STATUSES = new Set([
  'completed',
  'analysis_complete',
  'awaiting_confirmation',
  'failed',
]);

export function isWorkflowTerminalStatus(status: string | undefined): boolean {
  return DONE_STATUSES.has(String(status ?? '').toLowerCase());
}

export function getTrackedSessions(): TrackedSession[] {
  try {
    const raw = localStorage.getItem(TRACKED_SESSIONS_KEY) || '[]';
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (item): item is TrackedSession =>
        typeof item === 'object' &&
        item !== null &&
        typeof (item as TrackedSession).sessionId === 'string',
    );
  } catch {
    return [];
  }
}

export function saveTrackedSessions(list: TrackedSession[]): void {
  try {
    localStorage.setItem(TRACKED_SESSIONS_KEY, JSON.stringify(list));
  } catch {
    /* storage unavailable */
  }
}

/** Add a session to the tracked list (max 20, same as new-application submit). */
export function addTrackedSession(sessionId: string): void {
  if (!sessionId) return;
  const tracked = getTrackedSessions();
  tracked.push({ sessionId });
  if (tracked.length > 20) tracked.splice(0, tracked.length - 20);
  saveTrackedSessions(tracked);
}

export function removeTrackedSession(sessionId: string): void {
  saveTrackedSessions(getTrackedSessions().filter((t) => t.sessionId !== sessionId));
}

export function isWorkflowNotified(sessionId: string): boolean {
  try {
    const list = JSON.parse(localStorage.getItem(NOTIFIED_ANALYSES_KEY) || '[]') as unknown;
    if (!Array.isArray(list)) return false;
    return (
      list.includes(sessionId) ||
      list.includes(`c:${sessionId}`) ||
      list.includes(`f:${sessionId}`)
    );
  } catch {
    return false;
  }
}

export function setNavBadge(): void {
  try {
    localStorage.setItem(NAV_BADGE_KEY, '1');
  } catch {
    /* ignore */
  }
}

export function clearNavBadgeStorage(): void {
  try {
    localStorage.removeItem(NAV_BADGE_KEY);
  } catch {
    /* ignore */
  }
}

export function hasNavBadge(): boolean {
  return localStorage.getItem(NAV_BADGE_KEY) === '1';
}

export function updateNavBadgeDot(): void {
  const show = hasNavBadge();
  document.querySelectorAll('.nav-badge-dot').forEach((el) => {
    if (show) el.classList.remove('is-hidden');
    else el.classList.add('is-hidden');
  });
}
