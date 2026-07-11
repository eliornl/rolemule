import { getAuthToken } from '../shared/auth';
import {
  getPollAbortController,
  getPollTimeoutId,
  getSessionId,
  setPollAbortController,
  setPollTimeoutId,
  setUiState,
} from './state-access';
import { fetchAndRenderResult } from './render';
import { showSection } from './dom';
import { updateAiSetupUi } from './setup';

export function stopPolling(): void {
  const controller = getPollAbortController();
  if (controller) {
    controller.abort();
    setPollAbortController(null);
  }
  const timeoutId = getPollTimeoutId();
  if (timeoutId !== null) {
    clearTimeout(timeoutId);
    setPollTimeoutId(null);
  }
}

export function startPolling(): void {
  stopPolling();
  const controller = new AbortController();
  setPollAbortController(controller);
  const signal = controller.signal;
  const maxAttempts = 60;
  let attempts = 0;

  const poll = async (): Promise<void> => {
    const sessionId = getSessionId();
    if (signal.aborted || !sessionId) return;
    attempts++;
    try {
      const res = await fetch(
        `/api/v1/cv-optimizer/${encodeURIComponent(sessionId)}/status`,
        {
          credentials: 'same-origin',
          headers: { Authorization: `Bearer ${getAuthToken()}` },
          signal,
        },
      );
      if (res.ok) {
        const data = (await res.json()) as Record<string, unknown>;
        if (data.has_result) {
          stopPolling();
          setUiState('complete');
          await fetchAndRenderResult();
          return;
        }
        if (!data.is_running) {
          stopPolling();
          setUiState('not_started');
          showSection('cvo-setup');
          updateAiSetupUi();
          return;
        }
      }
    } catch {
      if (signal.aborted) return;
    }
    if (attempts < maxAttempts) {
      setPollTimeoutId(window.setTimeout(() => {
        void poll();
      }, 5000));
    }
  };
  void poll();
}
