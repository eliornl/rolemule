import { getApiBase } from '../shared/auth';
import { getAuthHeaders } from './api';
import { getSessionId } from './state-access';
import { connectWs, disconnectWs } from './websocket';
import { startPollingFallback, stopPolling } from './poll';
import { showError, showState } from './ui';

export async function generateInterviewPrep(): Promise<void> {
  const sessionId = getSessionId();
  if (!sessionId) return;
  showState('generating');
  connectWs();
  try {
    const response = await fetch(
      `${getApiBase()}/interview-prep/${sessionId}/generate`,
      { method: 'POST', headers: getAuthHeaders() },
    );
    if (!response.ok) {
      const errData = (await response.json()) as { message?: string; detail?: string };
      throw new Error(
        errData.message || errData.detail || 'Failed to generate interview prep',
      );
    }
    startPollingFallback();
  } catch (error) {
    const err = error as Error;
    console.error('Error generating interview prep:', err);
    disconnectWs();
    stopPolling();
    showError(`Failed to generate: ${err.message}`);
    showState('generate');
  }
}

export async function regenerateInterviewPrep(): Promise<void> {
  const sessionId = getSessionId();
  if (!sessionId) return;
  const showConfirm = window.showConfirm;
  if (!showConfirm) return;
  const confirmed = await showConfirm({
    title: 'Regenerate Interview Prep',
    message: 'This will replace the existing content. Are you sure?',
    confirmText: 'Regenerate',
    type: 'warning',
  });
  if (!confirmed) return;
  showState('generating');
  connectWs();
  try {
    const response = await fetch(
      `${getApiBase()}/interview-prep/${sessionId}/generate?regenerate=true`,
      { method: 'POST', headers: getAuthHeaders() },
    );
    if (!response.ok) {
      const errData = (await response.json()) as { message?: string; detail?: string };
      throw new Error(errData.message || errData.detail || 'Failed to regenerate');
    }
    startPollingFallback();
  } catch (error) {
    const err = error as Error;
    console.error('Error regenerating:', err);
    disconnectWs();
    stopPolling();
    showError(`Failed to regenerate: ${err.message}`);
    showState('content');
  }
}
