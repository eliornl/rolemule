import {
  getSessionId,
  getWsListenerAttached,
  setUiState,
  setWsListenerAttached,
} from './state-access';
import { decodeEntities } from '../shared/dom-security';
import { el, showSection } from './dom';
import { resetStartBtn } from './buttons';
import { notify } from './notify';
import { fetchAndRenderResult, resetProgressView, updateProgressView } from './render';
import { startPolling, stopPolling } from './poll';
import { updateAiSetupUi } from './setup';

export function onWsEvent(e: Event): void {
  const msg = ((e as CustomEvent).detail ?? {}) as Record<string, unknown>;
  const type = String(msg.type ?? '');
  const sessionId = String(msg.session_id ?? '');
  const currentId = getSessionId();
  if (!currentId || sessionId !== currentId) return;

  if (type === 'cv_optimization_started') {
    setUiState('running');
    resetProgressView();
    showSection('cvo-progress');
    startPolling();
  } else if (type === 'cv_optimization_iteration') {
    const d = (msg.data ?? {}) as Record<string, unknown>;
    updateProgressView(
      Number(d.iteration ?? 0),
      Number(d.score ?? NaN),
      (d.strengths as string[] | undefined) ?? [],
      (d.gaps as string[] | undefined) ?? [],
      (d.action_items as string[] | undefined) ?? [],
    );
  } else if (type === 'cv_optimization_complete') {
    stopPolling();
    setUiState('complete');
    void fetchAndRenderResult();
  } else if (type === 'cv_optimization_error') {
    stopPolling();
    setUiState('not_started');
    const data = (msg.data ?? {}) as Record<string, unknown>;
    const errMsg =
      (typeof data.error === 'string' && data.error) ||
      'Optimization failed. Please try again.';
    resetProgressView();
    showSection('cvo-setup');
    updateAiSetupUi();
    resetStartBtn(el('cvo-start-btn') as HTMLButtonElement | null);
    notify(decodeEntities(String(errMsg)), 'error');
  }
}

export function attachWsListener(): void {
  if (getWsListenerAttached()) return;
  window.addEventListener('applypilot:ws', onWsEvent);
  setWsListenerAttached(true);
}
