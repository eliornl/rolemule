import { getApiBase } from '../shared/auth';
import { getAuthHeaders } from './api';
import { loadInterviewPrep } from './load';
import {
  getPollAbortController,
  getSessionId,
  setPollAbortController,
} from './state-access';
import { disconnectWs } from './websocket';
import { showError, showState } from './ui';

export function stopPolling(): void {
  const controller = getPollAbortController();
  if (controller) {
    controller.abort();
    setPollAbortController(null);
  }
}

export function startPollingFallback(): void {
  stopPolling();
  const sessionId = getSessionId();
  if (!sessionId) return;

  const controller = new AbortController();
  setPollAbortController(controller);
  const signal = controller.signal;

  const maxAttempts = 60;
  let attempts = 0;
  let timeoutId = 0;

  const cancel = (): void => {
    clearTimeout(timeoutId);
  };
  signal.addEventListener('abort', cancel);

  const poll = async (): Promise<void> => {
    if (signal.aborted) return;
    attempts += 1;
    try {
      const response = await fetch(
        `${getApiBase()}/interview-prep/${sessionId}/status`,
        { headers: getAuthHeaders(), signal },
      );
      if (signal.aborted) return;
      if (response.ok) {
        const data = (await response.json()) as { has_interview_prep?: boolean };
        if (data.has_interview_prep) {
          stopPolling();
          disconnectWs();
          await loadInterviewPrep();
          return;
        }
      }
    } catch {
      if (signal.aborted) return;
    }
    if (attempts < maxAttempts) {
      timeoutId = window.setTimeout(() => {
        void poll();
      }, 5000);
    } else {
      showError('Generation timed out. Please try again.');
      showState('generate');
    }
  };

  void poll();
}
