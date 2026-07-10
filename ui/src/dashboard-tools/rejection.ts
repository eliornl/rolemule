import { escapeHtml } from '../shared/dom-security';
import { copyEmailParts } from './clipboard';
import { el, getVal, showOutput } from './dom';
import { postTool } from './tool-request';

function displayRejectionResult(data: Record<string, unknown>): void {
  const summaryEl = el('rejectionSummary');
  if (summaryEl) {
    summaryEl.innerHTML =
      `<div class="rejection-summary">${escapeHtml(String(data.analysis_summary ?? ''))}</div>`;
  }

  const reasonsEl = el('likelyReasons');
  if (reasonsEl) {
    reasonsEl.innerHTML = (data.likely_reasons as string[] | undefined ?? []).map(
      (r) =>
        `<div class="rejection-item"><div class="rejection-item-icon"><i class="fas fa-angle-right"></i></div><span>${escapeHtml(String(r))}</span></div>`,
    ).join('');
  }

  const suggestEl = el('improvementSuggestions');
  if (suggestEl) {
    suggestEl.innerHTML = (data.improvement_suggestions as string[] | undefined ?? []).map(
      (s) =>
        `<div class="rejection-item"><div class="rejection-item-icon"><i class="fas fa-check"></i></div><span>${escapeHtml(String(s))}</span></div>`,
    ).join('');
  }

  const posDiv = el('positiveSignals');
  if (posDiv) {
    const signals = data.positive_signals as string[] | undefined ?? [];
    posDiv.innerHTML =
      signals.length > 0
        ? signals
            .map(
              (s) =>
                `<div class="rejection-positive-card"><i class="fas fa-star"></i><span>${escapeHtml(String(s))}</span></div>`,
            )
            .join('')
        : '<span style="color:var(--text-muted);font-size:0.875rem;">No specific positive signals identified.</span>';
  }

  const followUpSection = el('followUpSection');
  if (followUpSection) {
    if (data.follow_up_recommended && (data.follow_up_body || data.follow_up_subject)) {
      const subjEl = el('followUpSubject');
      if (subjEl) {
        subjEl.innerHTML =
          `<div class="followup-subject">${escapeHtml(String(data.follow_up_subject ?? ''))}</div>`;
      }
      const tmplEl = el('followUpTemplate');
      if (tmplEl) {
        tmplEl.innerHTML =
          `<div class="followup-body">${escapeHtml(String(data.follow_up_body ?? ''))}</div>`;
      }
      followUpSection.style.display = 'block';
    } else {
      followUpSection.style.display = 'none';
    }
  }

  const encourageEl = el('encouragementText');
  if (encourageEl) encourageEl.textContent = String(data.encouragement ?? '');

  showOutput('rejectionOutput');
}

export async function handleRejectionSubmit(event: Event): Promise<void> {
  event.preventDefault();
  await postTool(
    '/tools/rejection-analysis',
    {
      rejection_email: getVal('rejectionEmail'),
      job_title: getVal('rejectionJobTitle') || null,
      company_name: getVal('rejectionCompany') || null,
      interview_stage: getVal('interviewStage') || null,
    },
    {
      loadingMessage: 'Analyzing rejection...',
      successMessage: 'Analysis complete!',
      failureMessage: 'Failed to analyze rejection',
      retryMessage: 'Failed to analyze rejection. Please try again.',
      onSuccess: displayRejectionResult,
    },
  );
}

export function copyFollowUpTemplate(): void {
  copyEmailParts('followUpSubject', 'followUpTemplate');
}
