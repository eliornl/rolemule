import { getAuthToken } from '../shared/auth';
import {
  getHasAiConfigured,
  getUiState,
  setApiKeyStatusLoaded,
  setHasAiConfigured,
} from './state-access';
import { el, setHidden } from './dom';

export async function checkApiKeyStatus(): Promise<void> {
  try {
    const res = await fetch('/api/v1/profile/api-key/status', {
      credentials: 'same-origin',
      headers: { Authorization: `Bearer ${getAuthToken()}` },
    });
    if (!res.ok) return;

    const data = (await res.json()) as Record<string, unknown>;
    setHasAiConfigured(
      !!(
        data.has_user_key ||
        data.server_has_key ||
        data.use_vertex_ai
      ),
    );
    setApiKeyStatusLoaded(true);
    updateAiSetupUi();
  } catch (err) {
    console.debug('[cv-optimizer] api-key status check failed', err);
  }
}

export function updateAiSetupUi(): void {
  const warning = el('cvo-ai-setup-warning');
  if (warning) {
    setHidden(warning, getHasAiConfigured());
  }

  const startBtn = el('cvo-start-btn') as HTMLButtonElement | null;
  if (startBtn && getUiState() === 'not_started') {
    startBtn.disabled = !getHasAiConfigured();
  }
}
