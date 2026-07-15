/**
 * Application detail page entry — DOM init, copy helpers, global exports.
 */
import { requireLogin } from '../shared/auth';
import { notify } from '../shared/notify';
import {
  continueWorkflow,
  generateInterviewPrep,
  generateSingle,
  regenerateCoverLetter,
  regenerateResume,
} from '../application-detail/actions';
import {
  loadApplicationData,
  showError,
  showProcessing,
} from '../application-detail/load';
import { wireCoverLetterGenerate } from '../application-detail/render-cover-letter';
import { wireResumeGenerate } from '../application-detail/render-resume';
import { wireContinueWorkflow } from '../application-detail/render-overview';
import {
  getCurrentSessionId,
  getProcessingRefreshTimer,
  getToastOutTimer,
  getToastRemoveTimer,
  setCurrentSessionId,
  setProcessingRefreshTimer,
} from '../application-detail/state';
import { switchSubTab, switchTab } from '../application-detail/tabs';
import {
  installToastAnimations,
  showApplicationToast,
} from '../application-detail/toast';

const showToast = showApplicationToast;

document.addEventListener('DOMContentLoaded', async () => {
  if (!requireLogin()) return;
  if (
    typeof window.syncProfileCompletionFromApi !== 'function' ||
    !(await window.syncProfileCompletionFromApi())
  ) {
    return;
  }

  const pathParts = window.location.pathname.split('/');
  setCurrentSessionId(pathParts[pathParts.length - 1] ?? null);

  if (getCurrentSessionId()) {
    void loadApplicationData();
  } else {
    showError('No application ID provided');
  }

  window.addEventListener('applypilot:ws', (e) => {
    const msg = (e as CustomEvent).detail as Record<string, unknown> | undefined;
    const type = String(msg?.type ?? '');
    const sessionId = String(msg?.session_id ?? '');

    if (!getCurrentSessionId() || sessionId !== getCurrentSessionId()) return;

    if (type === 'workflow_complete' || type === 'workflow_error') {
      const timer = getProcessingRefreshTimer();
      if (timer !== null) {
        clearTimeout(timer);
        setProcessingRefreshTimer(null);
      }
      void loadApplicationData();
    } else if (type === 'agent_update') {
      const data = msg?.data as Record<string, unknown> | undefined;
      const agentName = String(data?.agent ?? '');
      const agentStatus = String(data?.status ?? '');
      if (agentName && agentStatus === 'running') {
        showProcessing(agentName);
      }
    }
  });

  window.addEventListener('beforeunload', () => {
    const procTimer = getProcessingRefreshTimer();
    if (procTimer !== null) clearTimeout(procTimer);
    const toastOut = getToastOutTimer();
    if (toastOut !== null) clearTimeout(toastOut);
    const toastRemove = getToastRemoveTimer();
    if (toastRemove !== null) clearTimeout(toastRemove);
  });

  document.querySelectorAll('.page-tab').forEach((btn) => {
    btn.addEventListener('click', () => {
      const tabId = (btn as HTMLElement).dataset.tab;
      switchTab(tabId);
      if (tabId === 'optimize' && typeof window.initCvOptimizerTab === 'function') {
        window.initCvOptimizerTab(getCurrentSessionId());
      }
      if (tabId === 'practice' && typeof window.initMockInterviewTab === 'function') {
        window.initMockInterviewTab(getCurrentSessionId());
      }
      if (tabId === 'outreach' && typeof window.initHiringOutreachTab === 'function') {
        window.initHiringOutreachTab(getCurrentSessionId());
      }
    });
  });

  document.querySelectorAll('.sub-tab').forEach((btn) => {
    btn.addEventListener('click', () => {
      const subTabsEl = btn.closest('.sub-tabs') as HTMLElement | null;
      const parentId = subTabsEl?.dataset.parent;
      switchSubTab(parentId, (btn as HTMLElement).dataset.subtab);
    });
  });

  const handleDynamicAction = (e: MouseEvent) => {
    const btn = (e.target as HTMLElement).closest('[data-action]') as HTMLElement | null;
    if (!btn) return;
    const action = btn.dataset.action;
    if (action === 'regen-cover') regenerateCoverLetter(btn as HTMLButtonElement);
    if (action === 'regen-resume') regenerateResume(btn as HTMLButtonElement);
    if (action === 'gen-interview') generateInterviewPrep(btn as HTMLButtonElement);
    if (action === 'copy-text') copyText(btn, btn.dataset.copyText || '');
    if (action === 'copy-cover') {
      const textEl = document.querySelector('.cover-letter-body');
      const text = textEl ? textEl.textContent || '' : '';
      navigator.clipboard
        .writeText(text)
        .then(() => {
          btn.innerHTML = '<i class="fas fa-check"></i> Copied!';
          setTimeout(() => {
            btn.innerHTML = '<i class="fas fa-copy"></i> Copy';
          }, 2000);
        })
        .catch(() => notify('Could not copy to clipboard', 'error'));
    }
  };

  document.getElementById('pane-cover')?.addEventListener('click', handleDynamicAction);
  document.getElementById('pane-resume')?.addEventListener('click', handleDynamicAction);
  document.getElementById('pane-interview')?.addEventListener('click', handleDynamicAction);
});

function copyText(btn: HTMLElement, text: string): void {
  const onSuccess = () => {
    btn.innerHTML = '<i class="fas fa-check"></i> Copied!';
    setTimeout(() => {
      btn.innerHTML = '<i class="fas fa-copy"></i> Copy';
    }, 2000);
  };
  const app = window.app;
  if (app && typeof app.copyToClipboard === 'function') {
    app.copyToClipboard(text).then(onSuccess).catch(() => {});
    return;
  }
  navigator.clipboard.writeText(text).then(onSuccess);
}

function copyCoverLetter(): void {
  const text = document.getElementById('coverLetterText')?.innerText || '';
  const app = window.app;
  if (app && typeof app.copyToClipboard === 'function') {
    app.copyToClipboard(text);
    return;
  }
  navigator.clipboard
    .writeText(text)
    .then(() => showToast('Copied to clipboard!'))
    .catch(() => showToast('Failed to copy', 'error'));
}

function copyTabContent(paneId: string | null): void {
  if (!paneId) return;
  const pane = document.getElementById(paneId);
  if (!pane) return;
  const subPanes = pane.querySelectorAll('.sub-pane');
  let text = '';
  if (subPanes.length > 0) {
    subPanes.forEach((sp) => {
      const content = (sp as HTMLElement).innerText || sp.textContent || '';
      if (content.trim()) text += content.trim() + '\n\n';
    });
  } else {
    text = pane.innerText || pane.textContent || '';
  }
  const app = window.app;
  if (app && typeof app.copyToClipboard === 'function') {
    app.copyToClipboard(text.trim());
    return;
  }
  navigator.clipboard
    .writeText(text.trim())
    .then(() => showToast('Copied to clipboard!'))
    .catch(() => showToast('Failed to copy', 'error'));
}

wireCoverLetterGenerate(generateSingle);
wireResumeGenerate(generateSingle);
wireContinueWorkflow(continueWorkflow);

installToastAnimations();

window.showApplicationToast = showApplicationToast;
window.copyCoverLetter = copyCoverLetter;
window.copyTabContent = copyTabContent;
window.copyText = copyText;
window.regenerateCoverLetter = regenerateCoverLetter;
window.regenerateResume = regenerateResume;
window.generateInterviewPrep = generateInterviewPrep;
