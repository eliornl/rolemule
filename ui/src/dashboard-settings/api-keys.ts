import { escapeHtml } from '../shared/dom-security';
import { getApiBase, getAuthToken, getLoginUrl } from '../shared/auth';
import { el, inputEl } from './dom';
import { loadModelPreference } from './preferences';
import { showAlert } from './notify';
import type { ApiKeyStatusResponse, ApiKeyValidateResponse } from './types';

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

export function updateApiKeyStatusUI(data: ApiKeyStatusResponse): void {
  const serverNotice = el('serverKeyNotice');
  const byokNotice = el('byokNotice');
  const userKeyNotice = el('userKeyNotice');
  const statusText = el('apiKeyStatusText');
  const userKeyIcon = el('userKeyIcon');
  const modelCard = el('modelSelectorCard');

  if (serverNotice) serverNotice.style.display = 'none';
  if (byokNotice) byokNotice.style.display = 'none';
  if (userKeyNotice) userKeyNotice.style.display = 'none';

  const hasUserKey = Boolean(data.has_user_key || data.has_api_key);
  const useVertexAI = Boolean(data.use_vertex_ai);
  const serverHasKey = Boolean(data.server_has_key);

  if (hasUserKey) {
    if (userKeyNotice) userKeyNotice.style.display = 'block';

    if (useVertexAI) {
      if (statusText) {
        statusText.textContent =
          `Key ${data.key_preview || '****'} is saved but not used — this server handles AI internally. You can safely remove it.`;
      }
      if (userKeyIcon) userKeyIcon.className = 'account-icon account-icon--amber';
      userKeyNotice?.classList.add('account-card--warning');
    } else {
      if (statusText) statusText.textContent = `Active: ${data.key_preview || '****'}`;
      if (userKeyIcon) userKeyIcon.className = 'account-icon account-icon--cyan';
      userKeyNotice?.classList.remove('account-card--warning');
    }
  } else if (serverHasKey) {
    if (serverNotice) serverNotice.style.display = 'block';
  } else if (byokNotice) {
    byokNotice.style.display = 'block';
  }

  if (modelCard) {
    const showModel = hasUserKey && !useVertexAI;
    modelCard.style.display = showModel ? 'block' : 'none';
    if (showModel) void loadModelPreference();
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
  if (!apiKey) {
    showAlert('Please enter an API key to validate.', 'warning');
    return;
  }
  if (!resultDiv) return;

  resultDiv.style.display = 'block';
  resultDiv.innerHTML =
    '<div class="alert alert-info"><i class="fas fa-spinner fa-spin me-2"></i>Validating API key...</div>';

  try {
    const response = await fetch(`${getApiBase()}/profile/api-key/validate`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${getAuthToken()}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ api_key: apiKey }),
    });
    const data = (await response.json()) as ApiKeyValidateResponse;
    if (response.ok && data.valid) {
      resultDiv.innerHTML =
        `<div class="alert alert-success"><i class="fas fa-check-circle me-2"></i>` +
        `<strong>Valid!</strong> API key works correctly. ${escapeHtml(String(data.models_available))} models available.</div>`;
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
      body: JSON.stringify({ api_key: apiKey }),
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
  const confirmed = await showConfirm({
    title: 'Remove API Key',
    message: 'Are you sure? You will need to add a new key to use AI features.',
    confirmText: 'Remove',
    type: 'danger',
  });
  if (!confirmed) return;
  try {
    const response = await fetch(`${getApiBase()}/profile/api-key`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${getAuthToken()}` },
    });
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
