/**
 * Find jobs transcript + job picker rendering.
 */
import { decodeEntities, escapeHtml } from '../shared/dom-security';
import type { JobFinderJob, JobFinderMessage } from './api';

/** Escape then light markdown: **bold** and newlines. */
export function formatMessageHtml(content: string): string {
  const escaped = escapeHtml(content);
  return escaped
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>');
}

/** Safe plain text for .textContent assignments. */
export function plainText(value: string | null | undefined): string {
  return decodeEntities(value);
}

export function renderJobPicker(jobs: JobFinderJob[]): string {
  if (!jobs.length) return '';

  const cards = jobs
    .map((job) => {
      const id = escapeHtml(job.id);
      const title = escapeHtml(job.title || 'Untitled role');
      const company = escapeHtml(job.company || '');
      const location = escapeHtml(job.location || '');
      const metaParts = [company, location].filter(Boolean).join(' · ');
      return `
        <label class="jf-job-card">
          <input type="checkbox" data-job-id="${id}" aria-label="Select ${title}">
          <div class="jf-job-body">
            <p class="jf-job-title">${title}</p>
            ${metaParts ? `<p class="jf-job-meta">${metaParts}</p>` : ''}
            <span class="jf-job-badge">Careers</span>
          </div>
        </label>`;
    })
    .join('');

  return `
    <div class="jf-picker" role="group" aria-label="Open roles">
      ${cards}
      <div class="jf-picker-actions">
        <button type="button" class="btn btn-primary btn-sm" data-action="jf-add-selected">
          <i class="fas fa-plus me-1" aria-hidden="true"></i>Add to applications
        </button>
      </div>
    </div>`;
}

function renderOneMessage(msg: JobFinderMessage): string {
  const role = msg.role === 'user' ? 'user' : 'assistant';
  const roleClass = role === 'user' ? 'jf-msg-user' : 'jf-msg-assistant';
  const body = formatMessageHtml(msg.content || '');
  const jobs = msg.meta?.type === 'job_picker' && Array.isArray(msg.meta.jobs) ? msg.meta.jobs : [];
  const picker = jobs.length ? renderJobPicker(jobs) : '';

  return `
    <div class="jf-msg ${roleClass}" data-msg-id="${escapeHtml(msg.id || '')}">
      <div class="jf-msg-content">${body}</div>
      ${picker}
    </div>`;
}

export function renderMessages(
  container: HTMLElement,
  messages: JobFinderMessage[],
): void {
  const empty = document.getElementById('jfEmpty');
  if (empty) empty.remove();

  if (!messages.length) {
    container.innerHTML = `
      <div class="jf-empty" id="jfEmpty">
        <i class="fas fa-comments" aria-hidden="true"></i>
        <p>Say hello to start finding roles on company careers pages.</p>
      </div>`;
    return;
  }

  container.innerHTML = messages.map(renderOneMessage).join('');
  container.scrollTop = container.scrollHeight;
}

export function renderFilterChips(
  container: HTMLElement,
  filters: Record<string, unknown>,
  phase: string,
): void {
  const chips: string[] = [];

  const title = typeof filters['title'] === 'string' ? filters['title'].trim() : '';
  if (title) {
    chips.push(
      `<span class="jf-chip"><i class="fas fa-briefcase" aria-hidden="true"></i>${escapeHtml(title)}</span>`,
    );
  }

  const arrangements = Array.isArray(filters['work_arrangements'])
    ? (filters['work_arrangements'] as unknown[]).filter((x) => typeof x === 'string')
    : [];
  for (const a of arrangements) {
    chips.push(
      `<span class="jf-chip"><i class="fas fa-house" aria-hidden="true"></i>${escapeHtml(String(a))}</span>`,
    );
  }

  const jobTypes = Array.isArray(filters['job_types'])
    ? (filters['job_types'] as unknown[]).filter((x) => typeof x === 'string')
    : [];
  for (const t of jobTypes) {
    chips.push(
      `<span class="jf-chip"><i class="fas fa-clock" aria-hidden="true"></i>${escapeHtml(String(t))}</span>`,
    );
  }

  const locations = Array.isArray(filters['locations'])
    ? (filters['locations'] as unknown[]).filter((x) => typeof x === 'string')
    : [];
  if (locations.length) {
    chips.push(
      `<span class="jf-chip"><i class="fas fa-map-marker-alt" aria-hidden="true"></i>${escapeHtml(locations.join(' · '))}</span>`,
    );
  }

  const keywords = Array.isArray(filters['keywords'])
    ? (filters['keywords'] as unknown[]).filter((x) => typeof x === 'string')
    : [];
  for (const k of keywords) {
    chips.push(
      `<span class="jf-chip"><i class="fas fa-tag" aria-hidden="true"></i>${escapeHtml(String(k))}</span>`,
    );
  }

  if (phase === 'await_filter_confirm') {
    chips.push(
      `<button type="button" class="jf-chip jf-chip-action" data-action="jf-confirm-filters">
        <i class="fas fa-check" aria-hidden="true"></i>Looks good
      </button>`,
    );
  }

  container.innerHTML = chips.join('');
}
