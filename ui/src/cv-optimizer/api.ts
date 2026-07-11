import { getAuthToken } from '../shared/auth';
import { decodeEntities } from '../shared/dom-security';
import {
  getApiKeyStatusLoaded,
  getHasAiConfigured,
  getOptimizedCv,
  getSessionId,
  setCoverLetter,
  setHasAiConfigured,
  setOptimizedCv,
  setUiState,
} from './state-access';
import { MIN_SCORE_THRESHOLD, MAX_SCORE_THRESHOLD } from './state';
import { el, showSection } from './dom';
import { notify } from './notify';
import { downloadTextFile } from './clipboard';
import { setStartBtnLoading, resetStartBtn } from './buttons';
import { checkApiKeyStatus, updateAiSetupUi } from './setup';
import { resetProgressView } from './render';

export async function handleStart(): Promise<void> {
  if (!getSessionId()) return;

  if (!getApiKeyStatusLoaded()) {
    await checkApiKeyStatus();
  }
  if (!getHasAiConfigured()) {
    updateAiSetupUi();
    notify(
      'Configure AI in Settings → AI Setup before starting optimization.',
      'warning',
    );
    return;
  }

  const maxIterEl = el('cvo-max-iterations') as HTMLInputElement | null;
  const maxIter = parseInt(maxIterEl?.value || '5', 10);
  const thresholdEl = el('cvo-score-threshold') as HTMLSelectElement | null;
  const threshold = parseFloat(thresholdEl?.value || '8.5');

  if (isNaN(maxIter) || maxIter < 2 || maxIter > 7) {
    notify('Max iterations must be 2–7', 'warning');
    return;
  }
  if (
    isNaN(threshold) ||
    threshold < MIN_SCORE_THRESHOLD ||
    threshold > MAX_SCORE_THRESHOLD
  ) {
    notify('Choose a stop score between 7.0 and 9.5', 'warning');
    return;
  }

  const btn = el('cvo-start-btn') as HTMLButtonElement | null;
  setStartBtnLoading(btn);

  try {
    const res = await fetch(
      `/api/v1/cv-optimizer/${encodeURIComponent(getSessionId()!)}/start`,
      {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          Authorization: `Bearer ${getAuthToken()}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          max_iterations: maxIter,
          score_threshold: threshold,
        }),
      },
    );

    const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;

    if (!res.ok) {
      const errorCode = String(body.error_code ?? '');
      const msg = String(body.message ?? body.detail ?? `Error ${res.status}`);
      const decodedMsg = decodeEntities(msg);

      if (errorCode === 'CFG_6001') {
        setHasAiConfigured(false);
        updateAiSetupUi();
        notify(
          'Configure AI in Settings → AI Setup before starting optimization.',
          'warning',
        );
      } else if (res.status === 429 || errorCode === 'RATE_4001') {
        notify(
          decodedMsg ||
            'You\u2019ve used all optimization runs for this hour. Try again shortly.',
          'error',
        );
      } else {
        notify(decodedMsg, 'error');
      }

      setUiState('not_started');
      showSection('cvo-setup');
      updateAiSetupUi();
      resetStartBtn(btn);
      return;
    }

    setUiState('running');
    resetStartBtn(btn);
    resetProgressView();
    showSection('cvo-progress');
  } catch (err) {
    console.error('[cv-optimizer] start failed', err);
    notify('Failed to start optimization. Please try again.', 'error');
    setUiState('not_started');
    showSection('cvo-setup');
    updateAiSetupUi();
    resetStartBtn(btn);
  }
}

export async function handleClear(): Promise<void> {
  if (!getSessionId()) return;

  try {
    await fetch(
      `/api/v1/cv-optimizer/${encodeURIComponent(getSessionId()!)}`,
      {
        method: 'DELETE',
        credentials: 'same-origin',
        headers: { Authorization: `Bearer ${getAuthToken()}` },
      },
    );
  } catch (err) {
    console.error('[cv-optimizer] clear failed', err);
  }

  setUiState('not_started');
  setOptimizedCv('');
  setCoverLetter('');
  resetProgressView();
  showSection('cvo-setup');
  updateAiSetupUi();
  resetStartBtn(el('cvo-start-btn') as HTMLButtonElement | null);
}

export function apiErrorMessage(
  body: unknown,
  fallback: string,
): string {
  if (!body || typeof body !== 'object') return fallback;
  const record = body as Record<string, unknown>;
  const raw =
    typeof record.message === 'string'
      ? record.message
      : typeof record.detail === 'string'
        ? record.detail
        : '';
  return raw.trim() ? decodeEntities(raw.trim()) : fallback;
}

export function filenameFromDisposition(
  disposition: string | null,
): string {
  if (!disposition) return 'optimized-cv.docx';
  const match = disposition.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i);
  if (!match?.[1]) return 'optimized-cv.docx';
  return decodeEntities(match[1].replace(/"/g, '').trim());
}

export async function handleDownloadOdt(): Promise<void> {
  if (!getSessionId()) return;

  const btn = el('cvo-download-odt-btn') as HTMLButtonElement | null;
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Generating…';
  }

  try {
    const res = await fetch(
      `/api/v1/cv-optimizer/${encodeURIComponent(getSessionId()! )}/download-cv`,
      {
        credentials: 'same-origin',
        headers: { Authorization: `Bearer ${getAuthToken()}` },
      },
    );

    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as Record<
        string,
        unknown
      >;
      const errorCode = String(body.error_code ?? '');
      const decodedMsg = apiErrorMessage(body, `Error ${res.status}`);

      if (errorCode === 'CFG_6001') {
        setHasAiConfigured(false);
        updateAiSetupUi();
        notify(
          'Configure AI in Settings \u2192 AI Setup before downloading your CV.',
          'warning',
        );
      } else if (res.status === 429 || errorCode === 'RATE_4001') {
        notify(
          decodedMsg ||
            'You\u2019ve used all CV downloads for this hour. Try again shortly.',
          'error',
        );
      } else if (getOptimizedCv() && res.status >= 500) {
        downloadTextFile(getOptimizedCv(), 'optimized-cv.md', 'text/markdown');
        notify(
          'Document export failed — downloaded your CV as Markdown instead.',
          'warning',
        );
      } else {
        notify(decodedMsg, 'error');
      }
      return;
    }

    const blob = await res.blob();
    const filename = filenameFromDisposition(
      res.headers.get('Content-Disposition'),
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    const ext = filename.split('.').pop() || 'docx';
    notify(`CV downloaded (.${ext}).`, 'success');
  } catch (err) {
    console.error('[cv-optimizer] CV download failed', err);
    if (getOptimizedCv()) {
      downloadTextFile(getOptimizedCv(), 'optimized-cv.md', 'text/markdown');
      notify(
        'Document export failed — downloaded your CV as Markdown instead.',
        'warning',
      );
    } else {
      notify('Failed to download CV. Please try again.', 'error');
    }
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<i class="fas fa-file-word"></i> Download CV';
    }
  }
}
