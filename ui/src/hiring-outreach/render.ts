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

function confidenceClass(confidence: string | undefined): string {
  const c = (confidence || 'low').toLowerCase();
  if (c === 'high') return 'ho-badge-confidence-high';
  if (c === 'medium') return 'ho-badge-confidence-medium';
  return 'ho-badge-confidence-low';
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

  return `
    <article class="ho-contact-card" data-contact-index="${index}">
      <div class="ho-contact-header">
        <div>
          <p class="ho-contact-name">${escapeHtml(name)}</p>
          ${title ? `<p class="ho-contact-title">${escapeHtml(title)}</p>` : ''}
        </div>
        <div class="ho-contact-badges">
          <span class="ho-badge ${confidenceClass(confidence)}">${escapeHtml(confidence)} confidence</span>
          <span class="ho-badge ho-badge-role">${escapeHtml(roleType)}</span>
          ${sourceHint ? `<span class="ho-badge ho-badge-source">${escapeHtml(sourceHint)}</span>` : ''}
        </div>
      </div>
      ${why ? `<p class="ho-contact-meta"><span class="ho-contact-meta-label">Why them:</span> ${escapeHtml(why)}</p>` : ''}
      ${evidence ? `<p class="ho-contact-meta"><span class="ho-contact-meta-label">Evidence:</span> ${escapeHtml(evidence)}</p>` : ''}
      ${shortMsg ? `
        <div class="ho-draft-block">
          <div class="ho-draft-label">Short message</div>
          <p class="ho-draft-text">${escapeHtml(shortMsg)}</p>
          <div class="ho-draft-actions">
            <button type="button" class="cl-copy-btn" data-action="copyHoShort" data-index="${index}" aria-label="Copy short message">
              <i class="fas fa-copy" aria-hidden="true"></i> Copy note
            </button>
          </div>
        </div>` : ''}
      ${subject || body ? `
        <div class="ho-draft-block">
          <div class="ho-draft-label">Email draft</div>
          ${subject ? `<p class="ho-draft-text"><strong>Subject:</strong> ${escapeHtml(subject)}</p>` : ''}
          ${body ? `<p class="ho-draft-text">${escapeHtml(body)}</p>` : ''}
          <div class="ho-draft-actions">
            <button type="button" class="cl-copy-btn" data-action="copyHoEmail" data-index="${index}" aria-label="Copy email draft">
              <i class="fas fa-copy" aria-hidden="true"></i> Copy email
            </button>
          </div>
        </div>` : ''}
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

  bodyEl.innerHTML = `
    ${shortMsg ? `
      <div class="ho-draft-block">
        <div class="ho-draft-label">Short message</div>
        <p class="ho-draft-text">${escapeHtml(shortMsg)}</p>
        <div class="ho-draft-actions">
          <button type="button" class="cl-copy-btn" data-action="copyHoFallbackShort" aria-label="Copy generic short message">
            <i class="fas fa-copy" aria-hidden="true"></i> Copy note
          </button>
        </div>
      </div>` : ''}
    ${subject || body ? `
      <div class="ho-draft-block">
        <div class="ho-draft-label">Email draft</div>
        ${subject ? `<p class="ho-draft-text"><strong>Subject:</strong> ${escapeHtml(subject)}</p>` : ''}
        ${body ? `<p class="ho-draft-text">${escapeHtml(body)}</p>` : ''}
        <div class="ho-draft-actions">
          <button type="button" class="cl-copy-btn" data-action="copyHoFallbackEmail" aria-label="Copy generic email draft">
            <i class="fas fa-copy" aria-hidden="true"></i> Copy email
          </button>
        </div>
      </div>` : ''}`;
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
