import {
  fetchHiringOutreach,
  fetchHiringOutreachStatus,
  generateHiringOutreach,
} from './api';
import { decodeEntities } from '../shared/dom-security';
import {
  checkApiKeyStatus,
  notify,
  renderResults,
  setGenerateBtnLoading,
  setRegenerateBtnLoading,
  showSection,
  updateAiSetupUi,
} from './render';
import {
  getApiKeyStatusLoaded,
  getCachedOutreach,
  getContactAt,
  getEventListenersAttached,
  getHasAiConfigured,
  getIsBusy,
  getPollTimeoutId,
  getSessionId,
  setCachedOutreach,
  setEventListenersAttached,
  setHasAiConfigured,
  setIsBusy,
  setPollTimeoutId,
  type HoOutreachData,
} from './state';

function stopPolling(): void {
  const id = getPollTimeoutId();
  if (id !== null) {
    clearTimeout(id);
    setPollTimeoutId(null);
  }
}

export function startPolling(): void {
  stopPolling();
  const sessionId = getSessionId();
  if (!sessionId) return;

  let attempts = 0;
  const maxAttempts = 120;

  const loop = async (): Promise<void> => {
    const currentId = getSessionId();
    if (!currentId) return;
    attempts += 1;

    try {
      const status = await fetchHiringOutreachStatus(currentId);
      if (status['is_generating']) {
        showSection('progress');
      } else if (status['has_hiring_outreach']) {
        stopPolling();
        const payload = await fetchHiringOutreach(currentId);
        const outreach = payload['hiring_outreach'] as HoOutreachData | null | undefined;
        if (outreach) {
          renderResults(outreach);
        } else {
          showSection('setup');
          updateAiSetupUi();
        }
        setIsBusy(false);
        setGenerateBtnLoading(false);
        setRegenerateBtnLoading(false);
        return;
      } else if (!status['is_generating']) {
        stopPolling();
        showSection('setup');
        updateAiSetupUi();
        setIsBusy(false);
        setGenerateBtnLoading(false);
        setRegenerateBtnLoading(false);
        return;
      }
    } catch (err) {
      console.debug('[hiring-outreach] poll failed', err);
    }

    if (attempts < maxAttempts) {
      setPollTimeoutId(window.setTimeout(() => {
        void loop();
      }, 5000));
    } else {
      notify('Generation is taking longer than expected. Check back shortly.', 'warning');
      setIsBusy(false);
      setGenerateBtnLoading(false);
      setRegenerateBtnLoading(false);
    }
  };

  void loop();
}

async function clipboardWrite(text: string, successMsg: string): Promise<void> {
  if (!text.trim()) {
    notify('Nothing to copy.', 'warning');
    return;
  }
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.cssText = 'position:fixed;top:-9999px;left:-9999px';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
    notify(successMsg, 'success');
  } catch {
    notify('Could not copy to clipboard.', 'error');
  }
}

async function handleGenerate(regenerate: boolean): Promise<void> {
  const sessionId = getSessionId();
  if (!sessionId || getIsBusy()) return;

  if (!getApiKeyStatusLoaded()) {
    await checkApiKeyStatus();
  }
  if (!getHasAiConfigured()) {
    updateAiSetupUi();
    notify('Add your API key in Settings → AI Setup to find contacts.', 'warning');
    return;
  }

  setIsBusy(true);
  if (regenerate) {
    setRegenerateBtnLoading(true);
  } else {
    setGenerateBtnLoading(true);
  }

  try {
    const result = await generateHiringOutreach(sessionId, regenerate);
    const status = String(result['status'] || '');

    if (status === 'exists') {
      const payload = await fetchHiringOutreach(sessionId);
      const outreach = payload['hiring_outreach'] as HoOutreachData | null | undefined;
      if (outreach) {
        renderResults(outreach);
      } else {
        showSection('setup');
        updateAiSetupUi();
      }
      setIsBusy(false);
      setGenerateBtnLoading(false);
      setRegenerateBtnLoading(false);
      return;
    }

    showSection('progress');
    startPolling();
  } catch (err) {
    const e = err as Error & { error_code?: string };
    const msg = decodeEntities(e.message || 'Could not start contact search');

    if (e.error_code === 'CFG_6001') {
      setHasAiConfigured(false);
      updateAiSetupUi();
      notify('Add your API key in Settings → AI Setup to find contacts.', 'warning');
    } else if (e.error_code === 'RATE_4001') {
      notify(msg, 'error');
    } else {
      notify(msg, 'error');
    }

    if (getCachedOutreach()) {
      showSection('results');
    } else {
      showSection('setup');
      updateAiSetupUi();
    }
    setIsBusy(false);
    setGenerateBtnLoading(false);
    setRegenerateBtnLoading(false);
  }
}

export async function loadAndRender(): Promise<void> {
  const sessionId = getSessionId();
  if (!sessionId) return;

  await checkApiKeyStatus();

  try {
    const status = await fetchHiringOutreachStatus(sessionId);
    if (status['is_generating']) {
      showSection('progress');
      setIsBusy(true);
      startPolling();
      return;
    }

    if (status['has_hiring_outreach']) {
      const payload = await fetchHiringOutreach(sessionId);
      const outreach = payload['hiring_outreach'] as HoOutreachData | null | undefined;
      if (outreach) {
        renderResults(outreach);
        return;
      }
    }

    setCachedOutreach(null);
    showSection('setup');
    updateAiSetupUi();
  } catch (err) {
    const e = err as Error;
    notify(decodeEntities(e.message || 'Failed to load outreach'), 'error');
    showSection('setup');
    updateAiSetupUi();
  }
}

export function attachEventListeners(): void {
  if (getEventListenersAttached()) return;
  const pane = document.getElementById('hiringOutreachContent');
  if (!pane) return;

  pane.addEventListener('click', (e) => {
    const target = e.target as HTMLElement;
    const actionEl = target.closest('[data-action]') as HTMLElement | null;
    if (!actionEl) return;

    const action = actionEl.getAttribute('data-action');
    if (action === 'generateHiringOutreach') {
      void handleGenerate(false);
    } else if (action === 'regenerateHiringOutreach') {
      void handleGenerate(true);
    } else if (action === 'copyHoShort') {
      const index = parseInt(actionEl.dataset['index'] || '-1', 10);
      const contact = getContactAt(index);
      void clipboardWrite(contact?.short_message || '', 'Short message copied!');
    } else if (action === 'copyHoEmail') {
      const index = parseInt(actionEl.dataset['index'] || '-1', 10);
      const contact = getContactAt(index);
      const subject = (contact?.subject_line || '').trim();
      const body = (contact?.email_body || '').trim();
      const combined = subject ? `Subject: ${subject}\n\n${body}` : body;
      void clipboardWrite(combined, 'Email draft copied!');
    } else if (action === 'copyHoFallbackShort') {
      const fallback = getCachedOutreach()?.fallback;
      void clipboardWrite(fallback?.short_message || '', 'Short message copied!');
    } else if (action === 'copyHoFallbackEmail') {
      const fallback = getCachedOutreach()?.fallback;
      const subject = (fallback?.subject_line || '').trim();
      const body = (fallback?.email_body || '').trim();
      const combined = subject ? `Subject: ${subject}\n\n${body}` : body;
      void clipboardWrite(combined, 'Email draft copied!');
    }
  });

  setEventListenersAttached(true);
}

export function onGenerationStarted(): void {
  showSection('progress');
  startPolling();
}

export function onGenerationComplete(): void {
  stopPolling();
  void loadAndRender().finally(() => {
    setIsBusy(false);
    setGenerateBtnLoading(false);
    setRegenerateBtnLoading(false);
  });
}

export function onGenerationError(message: string): void {
  stopPolling();
  setIsBusy(false);
  setGenerateBtnLoading(false);
  setRegenerateBtnLoading(false);

  if (getCachedOutreach()) {
    showSection('results');
  } else {
    showSection('setup');
    updateAiSetupUi();
  }
  notify(decodeEntities(message || 'Contact search failed. Please try again.'), 'error');
}
