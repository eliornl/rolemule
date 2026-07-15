import {
  onGenerationComplete,
  onGenerationError,
  onGenerationStarted,
} from './listeners';
import { getSessionId, getWsListenerAttached, setWsListenerAttached } from './state';

export function handleWsMessage(msg: Record<string, unknown>): void {
  const type = String(msg['type'] ?? '');
  const sessionId = String(msg['session_id'] ?? '');
  const currentId = getSessionId();
  if (!currentId || sessionId !== currentId) return;

  if (type === 'hiring_outreach_started') {
    onGenerationStarted();
  } else if (type === 'hiring_outreach_complete') {
    onGenerationComplete();
  } else if (type === 'hiring_outreach_error') {
    const data = (msg['data'] ?? {}) as Record<string, unknown>;
    const errMsg =
      typeof data['error'] === 'string'
        ? data['error']
        : 'Contact search failed. Please try again.';
    onGenerationError(errMsg);
  }
}

export function attachWsListener(): void {
  if (getWsListenerAttached()) return;
  setWsListenerAttached(true);
  window.addEventListener('applypilot:ws', ((event: Event) => {
    const ce = event as CustomEvent<Record<string, unknown>>;
    const msg = ce.detail;
    if (msg && typeof msg === 'object') handleWsMessage(msg);
  }) as EventListener);
}
