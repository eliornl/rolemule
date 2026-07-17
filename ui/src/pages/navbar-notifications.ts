/**
 * Cross-page analysis completion notifications for dashboard subpages.
 * Dashboard home handles toasts natively; this script sets the navbar badge dot elsewhere.
 */
import { getApiBase, getAuthToken } from '../shared/auth';
import type { WorkflowStatusResponse } from '../shared/types';
import {
  NAV_BADGE_KEY,
  NOTIFIED_ANALYSES_KEY,
  clearNavBadgeStorage,
  getTrackedSessions,
  isWorkflowNotified,
  isWorkflowTerminalStatus,
  removeTrackedSession,
  saveTrackedSessions,
  setNavBadge,
  updateNavBadgeDot,
} from '../shared/workflow-tracking';

const WS_MAX_RECONNECT = 5;

let ws: WebSocket | null = null;
let wsReconnectAttempts = 0;

async function checkTrackedOnLoad(): Promise<void> {
  const tracked = getTrackedSessions();
  if (!tracked.length) return;

  const token = getAuthToken();
  if (!token) return;

  const remaining = [];

  for (const entry of tracked) {
    const sessionId = entry.sessionId;
    if (isWorkflowNotified(sessionId)) continue;

    try {
      const res = await fetch(
        `${getApiBase()}/workflow/status/${encodeURIComponent(sessionId)}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (!res.ok) {
        remaining.push(entry);
        continue;
      }

      const data = (await res.json()) as WorkflowStatusResponse;
      if (!isWorkflowTerminalStatus(data.status)) {
        remaining.push(entry);
      } else {
        setNavBadge();
        updateNavBadgeDot();
      }
    } catch {
      remaining.push(entry);
    }
  }

  saveTrackedSessions(remaining);
}

function connectWs(): void {
  const token = getAuthToken();
  if (!token || typeof WebSocket === 'undefined') return;

  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(
    `${proto}://${window.location.host}/api/v1/ws/user?token=${encodeURIComponent(token)}`,
  );

  ws.onopen = () => {
    wsReconnectAttempts = 0;
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data) as Record<string, unknown>;

      window.dispatchEvent(new CustomEvent('rolemule:ws', { detail: msg }));

      const type = String(msg.type || '');
      const sessionId = String(msg.session_id || '');

      if (type !== 'workflow_complete' && type !== 'workflow_error') return;
      if (!sessionId || isWorkflowNotified(sessionId)) return;

      setNavBadge();
      updateNavBadgeDot();
      removeTrackedSession(sessionId);
    } catch {
      /* malformed WS payload */
    }
  };

  ws.onclose = (event) => {
    ws = null;
    const noRetry = [1000, 1008, 4001];
    if (noRetry.includes(event.code) || wsReconnectAttempts >= WS_MAX_RECONNECT) return;
    const delay = Math.min(1000 * 2 ** wsReconnectAttempts, 30000);
    wsReconnectAttempts += 1;
    window.setTimeout(connectWs, delay);
  };

  ws.onerror = () => {
    /* onclose fires after onerror */
  };
}

function initNavbarNotifications(): void {
  if (window.location.pathname === '/dashboard') {
    clearNavBadgeStorage();
    updateNavBadgeDot();
    return;
  }

  updateNavBadgeDot();
  void checkTrackedOnLoad();
  connectWs();

  window.addEventListener('storage', (e) => {
    if (e.key === NAV_BADGE_KEY || e.key === NOTIFIED_ANALYSES_KEY) {
      updateNavBadgeDot();
    }
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initNavbarNotifications);
} else {
  initNavbarNotifications();
}

window.clearNavBadge = () => {
  clearNavBadgeStorage();
  updateNavBadgeDot();
};
