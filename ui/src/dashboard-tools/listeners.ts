import { toggleJob3, handleComparisonSubmit } from './comparison';
import { copyToClipboard } from './clipboard';
import { el } from './dom';
import { handleFollowupSubmit, copyFollowupEmail } from './followup';
import { showTool } from './navigation';
import { handleReferenceSubmit, copyReferenceEmail } from './reference';
import { handleRejectionSubmit, copyFollowUpTemplate } from './rejection';
import { copyAllScripts, handleSalarySubmit } from './salary';
import { copyThankYouNote, handleThankYouSubmit } from './thank-you';

const JOB_DESC_IDS = ['job1Description', 'job2Description', 'job3Description'] as const;

function attachCharacterCounters(): void {
  for (const id of JOB_DESC_IDS) {
    const ta = el(id) as HTMLTextAreaElement | null;
    const counter = el(id.replace('Description', 'DescCount'));
    if (!ta || !counter) continue;
    ta.addEventListener('input', () => {
      const len = ta.value.length;
      counter.textContent = len.toLocaleString();
      const wrap = counter.parentElement;
      if (!wrap) return;
      wrap.classList.toggle('char-near-limit', len >= 4000 && len < 5000);
      wrap.classList.toggle('char-at-limit', len >= 5000);
    });
  }
}

export function attachEventListeners(): void {
  attachCharacterCounters();

  el('thankYouForm')?.addEventListener('submit', (e) => {
    void handleThankYouSubmit(e);
  });
  el('rejectionForm')?.addEventListener('submit', (e) => {
    void handleRejectionSubmit(e);
  });
  el('referenceForm')?.addEventListener('submit', (e) => {
    void handleReferenceSubmit(e);
  });
  el('comparisonForm')?.addEventListener('submit', (e) => {
    void handleComparisonSubmit(e);
  });
  el('followupForm')?.addEventListener('submit', (e) => {
    void handleFollowupSubmit(e);
  });
  el('salaryForm')?.addEventListener('submit', (e) => {
    void handleSalarySubmit(e);
  });

  document.querySelector('.tools-nav')?.addEventListener('click', (e) => {
    const link = (e.target as HTMLElement).closest<HTMLElement>('a[data-tool]');
    if (!link) return;
    e.preventDefault();
    showTool(link.dataset.tool ?? '', e as MouseEvent);
  });

  document.querySelector('.tools-content')?.addEventListener('click', (e) => {
    const target = e.target as HTMLElement;

    const copyBtn = target.closest<HTMLElement>('[data-copy]');
    if (copyBtn) {
      e.preventDefault();
      copyToClipboard(copyBtn.dataset.copy ?? '');
      return;
    }

    const actionBtn = target.closest<HTMLElement>('[data-action]');
    if (!actionBtn) return;
    const action = actionBtn.dataset.action;
    switch (action) {
      case 'toggleJob3':
        e.preventDefault();
        toggleJob3();
        break;
      case 'copyAllScripts':
        e.preventDefault();
        copyAllScripts();
        break;
      case 'copyFollowupEmail':
        e.preventDefault();
        copyFollowupEmail();
        break;
      case 'copyThankYouNote':
        e.preventDefault();
        copyThankYouNote();
        break;
      case 'copyFollowUpTemplate':
        e.preventDefault();
        copyFollowUpTemplate();
        break;
      case 'copyReferenceEmail':
        e.preventDefault();
        copyReferenceEmail();
        break;
      default:
        break;
    }
  });
}
