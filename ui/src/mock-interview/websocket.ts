import { handleWsMessage } from './listeners';
import { getWsListenerAttached, setWsListenerAttached } from './state';

export function attachWsListener(): void {
  if (getWsListenerAttached()) return;
  setWsListenerAttached(true);
  window.addEventListener('applypilot:ws', ((event: Event) => {
    const ce = event as CustomEvent<Record<string, unknown>>;
    const msg = ce.detail;
    if (msg && typeof msg === 'object') handleWsMessage(msg);
  }) as EventListener);
}
