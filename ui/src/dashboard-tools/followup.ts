import { escapeHtml } from '../shared/dom-security';
import { copyEmailParts } from './clipboard';
import { el, getVal, showOutput } from './dom';
import { postTool, splitCommaList } from './tool-request';

function displayFollowupResult(data: Record<string, unknown>): void {
  const subjEl = el('followupSubject');
  if (subjEl) {
    subjEl.innerHTML =
      `<div class="followup-subject">${escapeHtml(String(data.subject_line ?? ''))}</div>`;
  }

  const bodyEl = el('followupEmailBody');
  if (bodyEl) {
    bodyEl.innerHTML =
      `<div class="followup-body">${escapeHtml(String(data.email_body ?? ''))}</div>`;
  }

  const timingEl = el('followupTimingAdvice');
  if (timingEl) timingEl.textContent = String(data.timing_advice ?? '');

  const stepsEl = el('followupNextSteps');
  if (stepsEl) stepsEl.textContent = String(data.next_steps ?? '');

  showOutput('followupOutput');
}

export async function handleFollowupSubmit(event: Event): Promise<void> {
  event.preventDefault();
  const rawPoints = getVal('followupKeyPoints');
  const daysVal = getVal('followupDays');
  await postTool(
    '/tools/followup',
    {
      stage: getVal('followupStage'),
      company_name: getVal('followupCompany'),
      job_title: getVal('followupJobTitle'),
      contact_name: getVal('followupContactName') || null,
      days_since_contact: daysVal ? parseInt(daysVal, 10) : null,
      key_points: splitCommaList(rawPoints),
    },
    {
      loadingMessage: 'Generating follow-up email...',
      successMessage: 'Follow-up email generated!',
      failureMessage: 'Failed to generate follow-up',
      retryMessage: 'Failed to generate follow-up email. Please try again.',
      onSuccess: displayFollowupResult,
    },
  );
}

export function copyFollowupEmail(): void {
  copyEmailParts('followupSubject', 'followupEmailBody');
}
