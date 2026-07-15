/**
 * Practice Interview tab entry — called from application-detail when Practice tab opens.
 */
import { attachEventListeners, loadAndRender } from '../mock-interview/listeners';
import { attachWsListener } from '../mock-interview/websocket';
import { getEventListenersAttached, setEventListenersAttached, setSessionId } from '../mock-interview/state';

export function initMockInterviewTab(sessionId: string | null): void {
  setSessionId(sessionId);
  if (!sessionId) return;
  if (!getEventListenersAttached()) {
    attachEventListeners();
    setEventListenersAttached(true);
  }
  attachWsListener();
  void loadAndRender();
}

window.initMockInterviewTab = initMockInterviewTab;
