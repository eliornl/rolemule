import { getApiBase, getAuthToken } from '../shared/auth';
import { hideLoading, showLoading } from './loading';
import { showAlert } from './notify';
import {
  getToolSubmitting,
  setToolSubmitting,
} from './state-access';
import type { ToolErrorResponse } from './types';

export interface PostToolOptions {
  loadingMessage: string;
  successMessage: string;
  failureMessage: string;
  retryMessage: string;
  rateLimitMessage?: string;
  onSuccess: (data: Record<string, unknown>) => void;
}

export async function postTool(
  path: string,
  payload: Record<string, unknown>,
  options: PostToolOptions,
): Promise<void> {
  if (getToolSubmitting()) return;
  setToolSubmitting(true);
  showLoading(options.loadingMessage);
  try {
    const response = await fetch(`${getApiBase()}${path}`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${getAuthToken()}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });
    if (response.ok) {
      options.onSuccess((await response.json()) as Record<string, unknown>);
      showAlert(options.successMessage, 'success');
    } else if (response.status === 429) {
      showAlert(
        options.rateLimitMessage ?? 'Rate limit exceeded. Please wait before trying again.',
        'warning',
      );
    } else {
      const errData = (await response.json()) as ToolErrorResponse;
      showAlert(
        errData.message || errData.detail || options.failureMessage,
        response.status === 400 ? 'warning' : 'danger',
      );
    }
  } catch (error) {
    console.error('Error:', error);
    showAlert(options.retryMessage, 'danger');
  } finally {
    hideLoading();
    setToolSubmitting(false);
  }
}

export function splitCommaList(raw: string): string[] | null {
  if (!raw) return null;
  const items = raw.split(',').map((p) => p.trim()).filter(Boolean);
  return items.length > 0 ? items : null;
}
