import { decodeEntities, escapeHtml } from '../shared/dom-security';
import { getAuthToken } from '../shared/auth';
import type { HoContact, HoFallback, HoOutreachData } from './state';
import {
  getHasAiConfigured,
  setApiKeyStatusLoaded,
  setCachedOutreach,
  setHasAiConfigured,
} from './state';

function el(id: string): HTMLElement | null {
  return document.getElementById(id);
}

export function setHidden(node: HTMLElement | null, hidden: boolean): void {
  if (!node) return;
  node.classList.toggle('is-hidden', hidden);
}

export function showSection(which: 'setup' | 'progress' | 'results'): void {
  setHidden(el('ho-setup'), which !== 'setup');
  setHidden(el('ho-progress'), which !== 'progress');
  setHidden(el('ho-results'), which !== 'results');
}

export function notify(
  msg: string,
  type: 'success' | 'error' | 'warning' | 'info' = 'info',
): void {
  const toastType = type === 'success' ? 'success' : 'error';
  if (typeof window.showApplicationToast === 'function') {
    window.showApplicationToast(msg, toastType);
    return;
  }
  const alertContainer = document.getElementById('alertContainer');
  if (!alertContainer) return;
  const alertType =
    type === 'error' ? 'danger' : type === 'warning' ? 'warning' : type;
  const div = document.createElement('div');
  div.className = `alert alert-${alertType} alert-dismissible fade show`;
  div.innerHTML = `${escapeHtml(msg)}<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>`;
  alertContainer.appendChild(div);
  window.setTimeout(() => div.remove(), 8000);
}

export async function checkApiKeyStatus(): Promise<void> {
  try {
    const res = await fetch('/api/v1/profile/api-key/status', {
      credentials: 'same-origin',
      headers: { Authorization: `Bearer ${getAuthToken()}` },
    });
    if (!res.ok) return;
    const data = (await res.json()) as Record<string, unknown>;
    const ready = !!(
      data.has_credentials ||
      data.has_user_key ||
      data.use_vertex_ai
    );
    setHasAiConfigured(ready);
    setApiKeyStatusLoaded(true);
    updateAiSetupUi(ready);
  } catch (err) {
    console.debug('[hiring-outreach] api-key status check failed', err);
  }
}

export function updateAiSetupUi(ready?: boolean): void {
  const configured = ready ?? getHasAiConfigured();
  setHidden(el('ho-ai-setup-warning'), configured);
  const generateBtn = el('ho-generate-btn') as HTMLButtonElement | null;
  const setupEl = el('ho-setup');
  if (generateBtn && setupEl && !setupEl.classList.contains('is-hidden')) {
    generateBtn.disabled = !configured;
  }
}

export function setGenerateBtnLoading(loading: boolean): void {
  const btn = el('ho-generate-btn') as HTMLButtonElement | null;
  if (!btn) return;
  btn.classList.toggle('loading', loading);
  btn.disabled = loading || !getHasAiConfigured();
}

export function setRegenerateBtnLoading(loading: boolean): void {
  const btn = document.querySelector(
    '[data-action="regenerateHiringOutreach"]',
  ) as HTMLButtonElement | null;
  if (!btn) return;
  btn.classList.toggle('loading', loading);
  btn.disabled = loading;
}

const ROLE_LABELS: Record<string, string> = {
  hiring_manager: 'Hiring manager',
  recruiter: 'Recruiter',
  team_peer: 'Team peer',
  generic: 'Contact',
};

const SOURCE_LABELS: Record<string, string> = {
  'company website': 'Company website',
  news: 'News',
  other_public: 'Public web',
};

function formatRoleType(roleType: string | undefined): string {
  if (!roleType) return 'Contact';
  return ROLE_LABELS[roleType] || roleType.replace(/_/g, ' ');
}

function confidenceBadgeClass(confidence: string | undefined): string {
  const c = (confidence || 'low').toLowerCase();
  if (c === 'high') return 'badge-good';
  if (c === 'medium') return 'badge-review';
  return 'badge-muted';
}

function confidenceLabel(confidence: string | undefined): string {
  const c = (confidence || 'low').toLowerCase();
  if (c === 'high') return 'High confidence';
  if (c === 'medium') return 'Medium confidence';
  return 'Low confidence';
}

function renderDraftBox(
  label: string,
  bodyHtml: string,
  copyAction: string,
  copyLabel: string,
  indexAttr: string,
): string {
  return `
    <div class="ho-draft-block">
      <div class="section-title">${escapeHtml(label)}</div>
      <div class="cover-letter-wrapper">
        <div class="cover-letter-box">
          <div class="cover-letter-body">${bodyHtml}</div>
          <div class="cover-letter-box-footer">
            <div class="cl-footer-meta">
              <span><i class="fas fa-paper-plane" aria-hidden="true"></i> ${escapeHtml(label)}</span>
            </div>
            <div class="cl-footer-actions">
              <button type="button" class="cl-copy-btn" data-action="${escapeHtml(copyAction)}"${indexAttr} aria-label="${escapeHtml(copyLabel)}">
                <i class="fas fa-copy" aria-hidden="true"></i> ${escapeHtml(copyLabel)}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>`;
}

function renderInsights(why: string, evidence: string): string {
  if (!why && !evidence) return '';
  return `
    <details class="ho-contact-insights">
      <summary>Why this contact</summary>
      <div class="ho-contact-insights-body">
        ${why ? `<p class="ho-contact-meta"><span class="ho-contact-meta-label">Why them:</span> ${escapeHtml(why)}</p>` : ''}
        ${evidence ? `<p class="ho-contact-meta"><span class="ho-contact-meta-label">Evidence:</span> ${escapeHtml(evidence)}</p>` : ''}
      </div>
    </details>`;
}

function renderContactCard(contact: HoContact, index: number): string {
  const name = (contact.name || '').trim() || 'Unknown contact';
  const title = (contact.likely_title || '').trim();
  const confidence = (contact.confidence || 'low').toLowerCase();
  const roleType = formatRoleType(contact.role_type);
  const sourceHint = contact.source_hint
    ? SOURCE_LABELS[contact.source_hint] || contact.source_hint
    : '';

  const why = contact.why_them || '';
  const evidence = contact.evidence || '';
  const shortMsg = contact.short_message || '';
  const subject = contact.subject_line || '';
  const body = contact.email_body || '';
  const indexAttr = ` data-index="${index}"`;

  const emailBodyParts: string[] = [];
  if (subject) {
    emailBodyParts.push(`<strong>Subject:</strong> ${escapeHtml(subject)}`);
  }
  if (body) {
    emailBodyParts.push(escapeHtml(body));
  }

  return `
    <article class="ho-contact-card" data-contact-index="${index}">
      <div class="ho-contact-header">
        <div>
          <p class="ho-contact-name">${escapeHtml(name)}</p>
          ${title ? `<p class="ho-contact-title">${escapeHtml(title)}</p>` : ''}
        </div>
        <div class="ho-contact-badges">
          <span class="fit-badge ${confidenceBadgeClass(confidence)}">${escapeHtml(confidenceLabel(confidence))}</span>
          <span class="fit-badge badge-muted">${escapeHtml(roleType)}</span>
          ${sourceHint ? `<span class="fit-badge badge-muted">${escapeHtml(sourceHint)}</span>` : ''}
        </div>
      </div>
      ${renderInsights(why, evidence)}
      ${shortMsg
        ? renderDraftBox(
            'Short message',
            escapeHtml(shortMsg),
            'copyHoShort',
            'Copy note',
            indexAttr,
          )
        : ''}
      ${subject || body
        ? renderDraftBox(
            'Email draft',
            emailBodyParts.join('\n\n'),
            'copyHoEmail',
            'Copy email',
            indexAttr,
          )
        : ''}
    </article>`;
}

function renderFallbackSection(fallback: HoFallback | undefined): void {
  const section = el('ho-fallback');
  const reasonEl = el('ho-fallback-reason');
  const bodyEl = el('ho-fallback-body');
  if (!section || !reasonEl || !bodyEl) return;

  if (!fallback?.used) {
    setHidden(section, true);
    return;
  }

  setHidden(section, false);
  const reason = (fallback.reason || '').trim();
  reasonEl.textContent = reason
    ? decodeEntities(reason)
    : 'No named contacts were found from public sources. Use this generic draft instead.';

  const shortMsg = fallback.short_message || '';
  const subject = fallback.subject_line || '';
  const body = fallback.email_body || '';

  const emailBodyParts: string[] = [];
  if (subject) {
    emailBodyParts.push(`<strong>Subject:</strong> ${escapeHtml(subject)}`);
  }
  if (body) {
    emailBodyParts.push(escapeHtml(body));
  }

  bodyEl.innerHTML = `
    ${shortMsg
      ? renderDraftBox(
          'Short message',
          escapeHtml(shortMsg),
          'copyHoFallbackShort',
          'Copy note',
          '',
        )
      : ''}
    ${subject || body
      ? renderDraftBox(
          'Email draft',
          emailBodyParts.join('\n\n'),
          'copyHoFallbackEmail',
          'Copy email',
          '',
        )
      : ''}`;
}

export function renderResults(data: HoOutreachData): void {
  setCachedOutreach(data);

  const summaryEl = el('ho-summary');
  if (summaryEl) {
    summaryEl.textContent = decodeEntities(data.summary || '');
  }

  const contactsEl = el('ho-contacts');
  const contacts = Array.isArray(data.contacts) ? data.contacts : [];
  if (contactsEl) {
    if (!contacts.length) {
      contactsEl.innerHTML =
        '<p class="ho-contacts-empty">No named contacts were identified from public sources.</p>';
    } else {
      contactsEl.innerHTML = contacts
        .map((c, i) => renderContactCard(c, i))
        .join('');
    }
  }

  renderFallbackSection(data.fallback);
  showSection('results');
  updateAiSetupUi();
}
