/**
 * Find jobs chat page — discover roles on company careers pages.
 */
import {
  ApiError,
  getOrCreateSession,
  getSession,
  postMessage,
  selectJobs,
  type JobFinderMessage,
  type JobFinderSession,
} from '../job-finder/api';
import { renderFilterChips, renderMessages } from '../job-finder/render';
import {
  getConfirmedFilters,
  getMessages,
  getPhase,
  getSessionId,
  getWsListenerAttached,
  isBusy,
  setBusy,
  setConfirmedFilters,
  setMessages,
  setPhase,
  setSessionId,
  setWsListenerAttached,
} from '../job-finder/state';
import { logout, requireLogin } from '../shared/auth';
import { notify } from '../shared/notify';
import { syncProfileCompletionFromApi } from '../shared/profile-completion';
import { addTrackedSession } from '../shared/workflow-tracking';

function showApiKeyAlert(): void {
  const container = document.getElementById('alertContainer');
  if (!container) return;
  container.innerHTML = `
    <div class="alert alert-warning alert-dismissible fade show" role="alert">
      <i class="fas fa-key me-2"></i>
      <strong>API key required.</strong>
      To use Find jobs, choose a provider and add your API key in
      <a href="/dashboard/settings?tab=ai-setup" class="alert-link">Settings &rarr; AI Setup</a>
      (or select Ollama / ask your admin about Vertex AI).
      <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    </div>`;
}

function clearAlerts(): void {
  const container = document.getElementById('alertContainer');
  if (container) container.innerHTML = '';
}

function setTyping(visible: boolean): void {
  const el = document.getElementById('jfTyping');
  if (!el) return;
  if (visible) {
    el.classList.remove('is-hidden');
    el.setAttribute('aria-hidden', 'false');
  } else {
    el.classList.add('is-hidden');
    el.setAttribute('aria-hidden', 'true');
  }
}

function setComposerEnabled(enabled: boolean): void {
  const input = document.getElementById('jfInput') as HTMLTextAreaElement | null;
  const btn = document.getElementById('jfSendBtn') as HTMLButtonElement | null;
  if (input) input.disabled = !enabled;
  if (btn) btn.disabled = !enabled;
}

function applySession(session: JobFinderSession): void {
  setSessionId(session.id);
  setPhase(session.phase || '');
  setMessages(Array.isArray(session.messages) ? session.messages : []);
  setConfirmedFilters(
    session.confirmed_filters && typeof session.confirmed_filters === 'object'
      ? session.confirmed_filters
      : {},
  );

  const transcript = document.getElementById('jfTranscript');
  if (transcript) renderMessages(transcript, getMessages());

  const chips = document.getElementById('jfFilterChips');
  if (chips) renderFilterChips(chips, getConfirmedFilters(), getPhase());
}

function handleApiError(err: unknown, fallback: string): void {
  if (err instanceof ApiError) {
    if (err.errorCode === 'CFG_6001') {
      showApiKeyAlert();
      return;
    }
    if (err.errorCode === 'RES_3002') {
      notify(
        err.message ||
          'You already have this role and company on your applications list.',
        'warning',
      );
      return;
    }
    notify(err.message || fallback, 'error');
    return;
  }
  const e = err instanceof Error ? err : new Error(String(err));
  notify(e.message || fallback, 'error');
}

async function bootstrapSession(): Promise<void> {
  setBusy(true);
  setTyping(true);
  setComposerEnabled(false);
  try {
    const session = await getOrCreateSession();
    applySession(session);
    clearAlerts();
  } catch (err) {
    handleApiError(err, 'Could not start Find jobs. Please try again.');
    const transcript = document.getElementById('jfTranscript');
    if (transcript) {
      transcript.innerHTML = `
        <div class="jf-empty" id="jfEmpty">
          <i class="fas fa-exclamation-circle" aria-hidden="true"></i>
          <p>Unable to load Find jobs. Refresh the page or check AI Setup.</p>
        </div>`;
    }
  } finally {
    setBusy(false);
    setTyping(false);
    setComposerEnabled(true);
    document.getElementById('jfInput')?.focus();
  }
}

async function sendUserText(raw: string): Promise<void> {
  const text = raw.trim();
  if (!text || isBusy()) return;

  const sessionId = getSessionId();
  if (!sessionId) {
    notify('Session not ready yet. Please wait a moment.', 'warning');
    return;
  }

  clearAlerts();
  setBusy(true);
  setTyping(true);
  setComposerEnabled(false);

  const input = document.getElementById('jfInput') as HTMLTextAreaElement | null;
  if (input) input.value = '';

  // Optimistic user bubble
  const optimistic: JobFinderMessage = {
    id: `local-${Date.now()}`,
    role: 'user',
    content: text,
    meta: { type: 'text' },
  };
  const prev = getMessages();
  setMessages([...prev, optimistic]);
  const transcript = document.getElementById('jfTranscript');
  if (transcript) renderMessages(transcript, getMessages());

  try {
    const session = await postMessage(sessionId, text);
    applySession(session);
  } catch (err) {
    setMessages(prev);
    if (transcript) renderMessages(transcript, prev);
    handleApiError(err, 'Message failed. Please try again.');
  } finally {
    setBusy(false);
    setTyping(false);
    setComposerEnabled(true);
    input?.focus();
  }
}

async function handleSend(): Promise<void> {
  const input = document.getElementById('jfInput') as HTMLTextAreaElement | null;
  await sendUserText(input?.value ?? '');
}

async function handleAddSelected(): Promise<void> {
  if (isBusy()) return;
  const sessionId = getSessionId();
  if (!sessionId) return;

  const checked = Array.from(
    document.querySelectorAll<HTMLInputElement>('#jfTranscript input[data-job-id]:checked'),
  );
  const jobIds = checked
    .map((el) => el.getAttribute('data-job-id') || '')
    .filter(Boolean);

  if (!jobIds.length) {
    notify('Select at least one role to add.', 'warning');
    return;
  }

  clearAlerts();
  setBusy(true);
  setTyping(true);
  setComposerEnabled(false);

  const total = jobIds.length;
  if (total > 1) {
    notify(`Adding 1 of ${total}…`, 'info');
  }

  try {
    const result = await selectJobs(sessionId, jobIds);

    for (const item of result.results) {
      if (item.ok && item.session_id) {
        addTrackedSession(item.session_id);
      }
      if (!item.ok && item.error_code === 'RES_3002') {
        notify(
          item.message ||
            'You already have this role and company on your applications list.',
          'warning',
        );
      } else if (!item.ok && item.error_code === 'CFG_6001') {
        showApiKeyAlert();
      } else if (!item.ok && item.message) {
        notify(item.message, 'error');
      }
    }

    if (result.started > 0) {
      notify(
        `Started analysis for ${result.started} role${result.started === 1 ? '' : 's'}. They’ll appear under Applications.`,
        'success',
      );

      const goToApps = await window.showConfirm?.({
        title: 'Roles added',
        message: `${result.started} role${result.started === 1 ? '' : 's'} started analysis. View them on Applications, or keep finding more companies?`,
        confirmText: 'View Applications',
        cancelText: 'Keep finding',
        type: 'primary',
      });

      if (goToApps === true) {
        window.location.href = '/dashboard';
        return;
      }
    } else if (result.failed > 0 && result.started === 0) {
      notify('Could not start analysis for the selected roles.', 'error');
    }

    // Refresh session for follow-up assistant message
    try {
      const session = await getSession(sessionId);
      applySession(session);
    } catch {
      /* non-fatal — select already succeeded */
    }
  } catch (err) {
    handleApiError(err, 'Could not add roles. Please try again.');
  } finally {
    setBusy(false);
    setTyping(false);
    setComposerEnabled(true);
  }
}

function attachWsListener(): void {
  if (getWsListenerAttached()) return;
  setWsListenerAttached(true);

  window.addEventListener('rolemule:ws', ((event: Event) => {
    const ce = event as CustomEvent<Record<string, unknown>>;
    const msg = ce.detail;
    if (!msg || typeof msg !== 'object') return;

    const type = String(msg['type'] ?? '');
    if (!type.startsWith('job_finder_')) return;

    const sid = String(msg['session_id'] ?? '');
    const current = getSessionId();
    if (!current || sid !== current) return;

    if (type === 'job_finder_status') {
      setTyping(true);
      return;
    }

    if (type === 'job_finder_error') {
      setTyping(false);
      const data = (msg['data'] ?? {}) as Record<string, unknown>;
      const errMsg =
        typeof data['error'] === 'string'
          ? data['error']
          : 'Something went wrong. Please try again.';
      notify(errMsg, 'error');
      return;
    }

    if (type === 'job_finder_message') {
      // Full session refresh keeps transcript consistent with server state
      void getSession(current)
        .then((session) => {
          applySession(session);
          setTyping(false);
        })
        .catch(() => {
          setTyping(false);
        });
    }
  }) as EventListener);
}

function autoResizeTextarea(el: HTMLTextAreaElement): void {
  el.style.height = 'auto';
  el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
}

function initJobFinderPage(): void {
  attachWsListener();

  document.addEventListener('click', (e) => {
    const target = e.target as Element | null;
    const actionEl = target?.closest('[data-action]') as HTMLElement | null;
    if (!actionEl) return;
    const action = actionEl.dataset['action'];

    if (action === 'logout') {
      e.preventDefault();
      logout();
      return;
    }
    if (action === 'jf-send') {
      e.preventDefault();
      void handleSend();
      return;
    }
    if (action === 'jf-add-selected') {
      e.preventDefault();
      void handleAddSelected();
      return;
    }
    if (action === 'jf-confirm-filters') {
      e.preventDefault();
      void sendUserText('yes');
    }
  });

  const input = document.getElementById('jfInput') as HTMLTextAreaElement | null;
  if (input) {
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        void handleSend();
      }
    });
    input.addEventListener('input', () => autoResizeTextarea(input));
  }

  void bootstrapSession();
}

document.addEventListener('DOMContentLoaded', async () => {
  if (!requireLogin()) return;
  if (!(await syncProfileCompletionFromApi())) return;
  initJobFinderPage();
});
