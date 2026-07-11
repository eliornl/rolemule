import { escapeHtml } from '../shared/dom-security';
import { copyEmailParts } from './clipboard';
import { el, getVal, showOutput } from './dom';
import { postTool, splitCommaList } from './tool-request';

function displayReferenceResult(data: Record<string, unknown>): void {
  const subjEl = el('referenceSubject');
  if (subjEl) {
    subjEl.innerHTML =
      `<div class="followup-subject">${escapeHtml(String(data.subject_line ?? ''))}</div>`;
  }

  const bodyEl = el('referenceEmailBody');
  if (bodyEl) {
    bodyEl.innerHTML =
      `<div class="followup-body">${escapeHtml(String(data.email_body ?? ''))}</div>`;
  }

  const tpEl = el('talkingPoints');
  if (tpEl) {
    tpEl.innerHTML = (data.talking_points as string[] | undefined ?? []).map(
      (p) =>
        `<div class="rejection-item"><div class="rejection-item-icon"><i class="fas fa-comment"></i></div><span>${escapeHtml(String(p))}</span></div>`,
    ).join('');
  }

  const tipsEl = el('referenceTips');
  if (tipsEl) {
    tipsEl.innerHTML = (data.tips as string[] | undefined ?? []).map(
      (t) =>
        `<div class="rejection-item"><div class="rejection-item-icon"><i class="fas fa-lightbulb"></i></div><span>${escapeHtml(String(t))}</span></div>`,
    ).join('');
  }

  const timeEl = el('followUpTimeline');
  if (timeEl) timeEl.textContent = String(data.follow_up_timeline ?? '');

  showOutput('referenceOutput');
}

export async function handleReferenceSubmit(event: Event): Promise<void> {
  event.preventDefault();
  const raw = getVal('keyAccomplishments');
  await postTool(
    '/tools/reference-request',
    {
      reference_name: getVal('referenceName'),
      reference_relationship: getVal('referenceRelationship'),
      target_job_title: getVal('targetJobTitle') || null,
      target_company: getVal('targetCompany') || null,
      key_accomplishments: splitCommaList(raw),
      time_since_contact: getVal('timeSinceContact') || null,
    },
    {
      loadingMessage: 'Generating reference request...',
      successMessage: 'Reference request generated successfully!',
      failureMessage: 'Failed to generate reference request',
      retryMessage: 'Failed to generate reference request. Please try again.',
      onSuccess: displayReferenceResult,
    },
  );
}

export function copyReferenceEmail(): void {
  copyEmailParts('referenceSubject', 'referenceEmailBody');
}
