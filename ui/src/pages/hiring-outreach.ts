/**
 * Hiring Outreach tab entry — called from application-detail when Outreach tab opens.
 */
import { attachEventListeners, loadAndRender } from '../hiring-outreach/listeners';
import { attachWsListener } from '../hiring-outreach/websocket';
import { getEventListenersAttached, setSessionId } from '../hiring-outreach/state';

export function initHiringOutreachTab(sessionId: string | null): void {
  setSessionId(sessionId);
  if (!sessionId) return;
  if (!getEventListenersAttached()) {
    attachEventListeners();
  }
  attachWsListener();
  void loadAndRender();
}

window.initHiringOutreachTab = initHiringOutreachTab;
