import { escapeHtml } from '../shared/dom-security';
import { getApiBase, getAuthToken, getLoginUrl } from '../shared/auth';
import { el, inputEl } from './dom';
import { loadModelPreference, populateModelSelect } from './preferences';
import { showAlert } from './notify';
import type { ApiKeyStatusResponse, ApiKeyValidateResponse } from './types';

const PROVIDER_KEY_LINKS: Record<string, { label: string; href: string; subtitle: string }> = {
  gemini: {
    label: 'Get API Key',
    href: 'https://aistudio.google.com/app/apikey',
    subtitle: 'Add your Google AI Studio / Gemini API key',
  },
  openai: {
    label: 'Get API Key',
    href: 'https://platform.openai.com/api-keys',
    subtitle: 'Add your OpenAI API key (starts with sk-)',
  },
  anthropic: {
    label: 'Get API Key',
    href: 'https://console.anthropic.com/settings/keys',
    subtitle: 'Add your Anthropic API key (starts with sk-ant-)',
  },
};

let _lastStatus: ApiKeyStatusResponse | null = null;
let _providerSaveTimer: number | null = null;

export function getLastApiKeyStatus(): ApiKeyStatusResponse | null {
  return _lastStatus;
}

export async function loadApiKeyStatus(): Promise<void> {
  try {
    const response = await fetch(`${getApiBase()}/profile/api-key/status`, {
      headers: { Authorization: `Bearer ${getAuthToken()}` },
    });
    if (response.ok) {
      updateApiKeyStatusUI((await response.json()) as ApiKeyStatusResponse);
    } else if (response.status === 401) {
      window.location.href = getLoginUrl();
    }
  } catch (error) {
    console.error('Error loading API key status:', error);
    const statusEl = el('apiKeyStatusText');
    if (statusEl) statusEl.textContent = 'Error loading status';
  }
}

function _hide(card: HTMLElement | null): void {
  if (!card) return;
  card.classList.add('is-hidden');
  card.style.display = 'none';
}

function _show(card: HTMLElement | null): void {
  if (!card) return;
  card.classList.remove('is-hidden');
  card.style.display = 'block';
}

export function updateApiKeyStatusUI(data: ApiKeyStatusResponse): void {
  _lastStatus = data;
  const serverNotice = el('serverKeyNotice');
  const byokNotice = el('byokNotice');
  const userKeyNotice = el('userKeyNotice');
  const ollamaNotice = el('ollamaNotice');
  const statusText = el('apiKeyStatusText');
  const userKeyIcon = el('userKeyIcon');
  const modelCard = el('modelSelectorCard');
  const providerSelect = inputEl('preferredProviderSelect') as HTMLSelectElement | null;

  _hide(serverNotice);
  _hide(byokNotice);
  _hide(userKeyNotice);
  _hide(ollamaNotice);

  const useVertexAI = Boolean(data.use_vertex_ai);
  const preferred = data.preferred_provider || '';
  const hasCredentials = Boolean(data.has_credentials ?? data.has_user_key ?? data.has_api_key);

  if (providerSelect && preferred) {
    providerSelect.value = preferred;
  }

  if (useVertexAI) {
    _show(serverNotice);
    if (modelCard) {
      modelCard.classList.add('is-hidden');
      modelCard.style.display = 'none';
    }
    return;
  }

  if (!preferred) {
    // No provider yet — only the provider card should show
    if (modelCard) {
      modelCard.classList.add('is-hidden');
      modelCard.style.display = 'none';
    }
    return;
  }

  if (preferred === 'ollama') {
    _show(ollamaNotice);
    if (modelCard) {
      modelCard.classList.remove('is-hidden');
      modelCard.style.display = 'block';
      populateModelSelect(data.models?.ollama || [], null);
      void loadModelPreference();
    }
    return;
  }

  const providerStatus = data.providers?.[preferred];
  const hasKey = Boolean(providerStatus?.has_key);
  const preview = providerStatus?.key_preview || data.key_preview;

  if (hasKey || hasCredentials) {
    _show(userKeyNotice);
    if (statusText) statusText.textContent = `Active (${preferred}): ${preview || '****'}`;
    if (userKeyIcon) userKeyIcon.className = 'account-icon account-icon--cyan';
    userKeyNotice?.classList.remove('account-card--warning');
  } else {
    _show(byokNotice);
    const meta = PROVIDER_KEY_LINKS[preferred];
    const sub = el('byokSubtitle');
    if (sub) sub.textContent = meta?.subtitle || 'Add your API key for the selected provider';
    const link = el('byokGetKeyLink') as HTMLAnchorElement | null;
    if (link && meta) {
      link.href = meta.href;
      link.textContent = meta.label;
      link.classList.remove('is-hidden');
    }
  }

  if (modelCard) {
    const showModel = hasKey || hasCredentials;
    if (showModel) {
      modelCard.classList.remove('is-hidden');
      modelCard.style.display = 'block';
      populateModelSelect(data.models?.[preferred] || [], null);
      void loadModelPreference();
    } else {
      modelCard.classList.add('is-hidden');
      modelCard.style.display = 'none';
    }
  }
}

export function scheduleProviderSave(): void {
  if (_providerSaveTimer !== null) window.clearTimeout(_providerSaveTimer);
  _providerSaveTimer = window.setTimeout(() => {
    void savePreferredProvider();
  }, 400);
}

export async function savePreferredProvider(): Promise<void> {
  const sel = inputEl('preferredProviderSelect') as HTMLSelectElement | null;
  if (!sel) return;
  const provider = sel.value || null;
  try {
    const response = await fetch(`${getApiBase()}/profile/preferences`, {
      method: 'PATCH',
      headers: {
        Authorization: `Bearer ${getAuthToken()}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ preferred_provider: provider }),
    });
    if (!response.ok) {
      const errData = (await response.json()) as { message?: string; detail?: string };
      throw new Error(errData.message || errData.detail || 'Failed to save provider');
    }
    const indicator = el('providerSavedIndicator');
    if (indicator) {
      indicator.style.opacity = '1';
      window.setTimeout(() => {
        indicator.style.opacity = '0';
      }, 2000);
    }
    await loadApiKeyStatus();
  } catch (error) {
    const err = error as Error;
    console.error('Error saving provider:', err);
    showAlert(err.message || 'Error saving provider.', 'danger');
  }
}

export function toggleApiKeyVisibility(): void {
  const input = inputEl('geminiApiKey');
  const icon = el('toggleApiKeyIcon');
  if (!input || !icon) return;
  if (input.type === 'password') {
    input.type = 'text';
    icon.classList.replace('fa-eye', 'fa-eye-slash');
  } else {
    input.type = 'password';
    icon.classList.replace('fa-eye-slash', 'fa-eye');
  }
}

export async function validateApiKey(): Promise<void> {
  const input = inputEl('geminiApiKey');
  const resultDiv = el('apiKeyValidationResult');
  const apiKey = input?.value.trim() ?? '';
  const provider =
    (inputEl('preferredProviderSelect') as HTMLSelectElement | null)?.value || 'gemini';
  if (!apiKey) {
    showAlert('Please enter an API key to validate.', 'warning');
    return;
  }
  if (!resultDiv) return;

  resultDiv.style.display = 'block';
  resultDiv.classList.remove('is-hidden');
  resultDiv.innerHTML =
    '<div class="alert alert-info"><i class="fas fa-spinner fa-spin me-2"></i>Validating API key...</div>';

  try {
    const response = await fetch(`${getApiBase()}/profile/api-key/validate`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${getAuthToken()}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ api_key: apiKey, provider }),
    });
    const data = (await response.json()) as ApiKeyValidateResponse;
    if (response.ok && data.valid) {
      resultDiv.innerHTML =
        `<div class="alert alert-success"><i class="fas fa-check-circle me-2"></i>` +
        `<strong>Valid!</strong> API key works correctly.` +
        (data.models_available != null
          ? ` ${escapeHtml(String(data.models_available))} models available.`
          : '') +
        `</div>`;
    } else {
      resultDiv.innerHTML =
        `<div class="alert alert-danger"><i class="fas fa-times-circle me-2"></i>` +
        `<strong>Invalid:</strong> ${escapeHtml(data.message || data.detail || 'API key validation failed')}</div>`;
    }
  } catch (error) {
    console.error('Error validating API key:', error);
    resultDiv.innerHTML =
      '<div class="alert alert-danger"><i class="fas fa-times-circle me-2"></i>Failed to validate API key. Please try again.</div>';
  }
}

export async function handleApiKeySave(event: Event): Promise<void> {
  event.preventDefault();
  const input = inputEl('geminiApiKey');
  const apiKey = input?.value.trim() ?? '';
  const provider =
    (inputEl('preferredProviderSelect') as HTMLSelectElement | null)?.value || '';
  if (!provider || provider === 'ollama') {
    showAlert('Select Gemini, OpenAI, or Anthropic before saving a key.', 'warning');
    return;
  }
  if (!apiKey) {
    showAlert('Please enter an API key.', 'warning');
    return;
  }

  try {
    const response = await fetch(`${getApiBase()}/profile/api-key`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${getAuthToken()}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ api_key: apiKey, provider }),
    });
    if (response.ok) {
      showAlert('API key saved successfully!', 'success');
      if (input) input.value = '';
      const resultDiv = el('apiKeyValidationResult');
      if (resultDiv) resultDiv.style.display = 'none';
      await loadApiKeyStatus();
    } else {
      const errData = (await response.json()) as { message?: string; detail?: string };
      throw new Error(errData.message || errData.detail || 'Failed to save API key');
    }
  } catch (error) {
    const err = error as Error;
    console.error('Error saving API key:', err);
    showAlert(err.message || 'Error saving API key. Please try again.', 'danger');
  }
}

export async function deleteApiKey(): Promise<void> {
  const showConfirm = window.showConfirm;
  if (!showConfirm) return;
  const provider =
    (inputEl('preferredProviderSelect') as HTMLSelectElement | null)?.value || 'gemini';
  const confirmed = await showConfirm({
    title: 'Remove API Key',
    message: 'Are you sure? You will need to add a new key to use AI features.',
    confirmText: 'Remove',
    type: 'danger',
  });
  if (!confirmed) return;
  try {
    const response = await fetch(
      `${getApiBase()}/profile/api-key?provider=${encodeURIComponent(provider)}`,
      {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${getAuthToken()}` },
      },
    );
    if (response.ok) {
      showAlert('API key deleted successfully.', 'success');
      const resultDiv = el('apiKeyValidationResult');
      if (resultDiv) resultDiv.style.display = 'none';
      await loadApiKeyStatus();
    } else {
      throw new Error('Failed to delete API key');
    }
  } catch (error) {
    console.error('Error deleting API key:', error);
    showAlert('Error deleting API key. Please try again.', 'danger');
  }
}
