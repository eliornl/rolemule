import { getAuthToken } from '../shared/auth';
import { getSessionId, setUiState } from './state-access';
import { showSection } from './dom';
import { updateAiSetupUi } from './setup';
import { startPolling } from './poll';
import { fetchAndRenderResult } from './render';

export async function loadCvOptimizationStatus(): Promise<void> {
  const sessionId = getSessionId();
  if (!sessionId) return;

  try {
    const res = await fetch(
      `/api/v1/cv-optimizer/${encodeURIComponent(sessionId)}/status`,
      {
        credentials: 'same-origin',
        headers: { Authorization: `Bearer ${getAuthToken()}` },
      },
    );

    if (!res.ok) {
      if (res.status === 401) return;
      return;
    }

    const data = (await res.json()) as Record<string, unknown>;

    if (data.is_running) {
      setUiState('running');
      showSection('cvo-progress');
      startPolling();
      return;
    }

    if (data.has_result) {
      setUiState('complete');
      await fetchAndRenderResult();
      return;
    }

    setUiState('not_started');
    showSection('cvo-setup');
    updateAiSetupUi();
  } catch (err) {
    console.error('[cv-optimizer] status fetch failed', err);
    showSection('cvo-setup');
    updateAiSetupUi();
  }
}
