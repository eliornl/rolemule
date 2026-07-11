import { escapeHtml } from '../shared/dom-security';
import { copyEmailParts } from './clipboard';
import { el, getVal, showOutput } from './dom';
import { postTool, splitCommaList } from './tool-request';

function displayThankYouResult(data: Record<string, unknown>): void {
  const subjEl = el('thankYouSubject');
  if (subjEl) {
    subjEl.innerHTML =
      `<div class="followup-subject">${escapeHtml(String(data.subject_line ?? ''))}</div>`;
  }

  const bodyEl = el('thankYouEmailBody');
  if (bodyEl) {
    bodyEl.innerHTML =
      `<div class="followup-body">${escapeHtml(String(data.email_body ?? ''))}</div>`;
  }

  showOutput('thankYouOutput');
}

export async function handleThankYouSubmit(event: Event): Promise<void> {
  event.preventDefault();
  const rawPoints = getVal('discussionPoints');
  await postTool(
    '/tools/thank-you',
    {
      interviewer_name: getVal('interviewerName'),
      interviewer_role: getVal('interviewerRole') || null,
      interview_type: getVal('interviewType'),
      company_name: getVal('companyName'),
      job_title: getVal('jobTitle'),
      key_discussion_points: splitCommaList(rawPoints),
      additional_notes: getVal('additionalNotes') || null,
    },
    {
      loadingMessage: 'Generating thank you note...',
      successMessage: 'Thank you note generated successfully!',
      failureMessage: 'Failed to generate thank you note',
      retryMessage: 'Failed to generate thank you note. Please try again.',
      onSuccess: displayThankYouResult,
    },
  );
}

export function copyThankYouNote(): void {
  copyEmailParts('thankYouSubject', 'thankYouEmailBody');
}
