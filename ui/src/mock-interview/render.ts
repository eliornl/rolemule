import { decodeEntities, escapeHtml } from '../shared/dom-security';
import { getAuthToken } from '../shared/auth';
import { isSttSupported } from './voice';

function el(id: string): HTMLElement | null {
  return document.getElementById(id);
}

function setHidden(node: HTMLElement | null, hidden: boolean): void {
  node?.classList.toggle('is-hidden', hidden);
}

export function showSection(which: 'setup' | 'active' | 'results'): void {
  const setup = el('mi-setup');
  const active = el('mi-active');
  const results = el('mi-results');
  setup?.classList.toggle('is-hidden', which !== 'setup');
  active?.classList.toggle('is-hidden', which !== 'active');
  results?.classList.toggle('is-hidden', which !== 'results');
}

export function setVoiceBanner(): void {
  const banner = el('mi-voice-banner');
  if (!banner) return;
  setHidden(banner, isSttSupported());
}

export async function checkApiKeyStatus(): Promise<void> {
  try {
    const res = await fetch('/api/v1/profile/api-key/status', {
      credentials: 'same-origin',
      headers: { Authorization: `Bearer ${getAuthToken()}` },
    });
    if (!res.ok) return;
    const data = (await res.json()) as Record<string, unknown>;
    const ready = !!(data.has_credentials || data.has_user_key || data.use_vertex_ai);
    updateAiSetupUi(ready);
  } catch (err) {
    console.debug('[mock-interview] api-key status check failed', err);
  }
}

export function updateAiSetupUi(ready: boolean): void {
  setHidden(el('mi-ai-setup-warning'), ready);
  const startBtn = el('mi-start-btn') as HTMLButtonElement | null;
  if (startBtn && !startBtn.classList.contains('loading')) {
    startBtn.disabled = !ready;
  }
}

export function setStartBtnLoading(loading: boolean): void {
  const btn = el('mi-start-btn') as HTMLButtonElement | null;
  if (!btn) return;
  btn.classList.toggle('loading', loading);
  if (loading) {
    btn.disabled = true;
    return;
  }
  // Restore based on whether the warning is hidden (AI ready)
  const warning = el('mi-ai-setup-warning');
  const ready = !warning || warning.classList.contains('is-hidden');
  btn.disabled = !ready;
}

export function setInterviewerSpeak(text: string): void {
  const box = el('mi-interviewer-text');
  if (!box) return;
  box.classList.remove('mi-typing');
  const plain = decodeEntities(text);
  delete box.dataset['miRaw'];
  box.textContent = plain;
}

/** Placeholder while waiting for the first streamed speak characters. */
export function setInterviewerTyping(message?: string): void {
  const box = el('mi-interviewer-text');
  if (!box) return;
  box.classList.add('mi-typing');
  delete box.dataset['miRaw'];
  box.textContent = message || 'Loading…';
}

export function appendInterviewerDelta(delta: string): void {
  if (!delta) return;
  const box = el('mi-interviewer-text');
  if (!box) return;
  // Accumulate raw, then decode once so split entities (e.g. &#x27;) still resolve.
  const rawPrev = box.dataset['miRaw'] || (box.classList.contains('mi-typing') ? '' : box.textContent || '');
  const raw = rawPrev + delta;
  box.dataset['miRaw'] = raw;
  if (box.classList.contains('mi-typing')) {
    box.classList.remove('mi-typing');
  }
  box.textContent = decodeEntities(raw);
}

export function setTip(tip: string | null | undefined): void {
  const box = el('mi-tip');
  if (!box) return;
  const text = (tip || '').trim();
  if (!text) {
    box.textContent = '';
    setHidden(box, true);
    return;
  }
  box.innerHTML = `<i class="fas fa-lightbulb" aria-hidden="true"></i><span>${escapeHtml(text)}</span>`;
  setHidden(box, false);
}

function shortVerdict(summary: string, overall: number | null): string {
  const cleaned = decodeEntities(summary).trim();
  if (cleaned) return cleaned;
  return overall == null || Number.isNaN(overall)
    ? 'Practice complete'
    : `Practice complete — ${overall}/10`;
}

const SCORE_HELP: Record<string, string> = {
  content: 'How specific and evidence-based your answers were for this role.',
  structure: 'How clearly you organized answers (situation → action → result).',
  clarity: 'How easy it was to follow what you meant, without fluff.',
  role_fit: 'How well your examples mapped to this job’s real needs.',
  style_focus: 'How well you hit what this interviewer style cares about most.',
};

function scoreGlance(
  key: string,
  label: string,
  icon: string,
  value: number | string | undefined,
): string {
  const help = SCORE_HELP[key] || '';
  return `
    <div class="jd-glance-item mi-score-item">
      <div class="jd-glance-icon"><i class="fas ${icon}" aria-hidden="true"></i></div>
      <div class="jd-glance-body">
        <div class="mi-score-top">
          <div class="jd-glance-label">${escapeHtml(label)}</div>
          <div class="jd-glance-value">${escapeHtml(String(value ?? '—'))}</div>
        </div>
        ${help ? `<p class="mi-score-help">${escapeHtml(help)}</p>` : ''}
      </div>
    </div>`;
}

function bulletList(
  items: unknown[],
  iconClass: string,
  iconName: string,
): string {
  if (!items.length) {
    return '<ul class="content-list"><li class="text-muted">None listed</li></ul>';
  }
  return `<ul class="content-list">${items
    .map(
      (s) =>
        `<li><i class="fas ${iconName} ${iconClass}" aria-hidden="true"></i><span>${escapeHtml(String(s))}</span></li>`,
    )
    .join('')}</ul>`;
}

let lastDebriefRewrite = '';
let lastAnswerRewrites: string[] = [];

export function getLastDebriefRewrite(index?: number): string {
  if (typeof index === 'number' && index >= 0 && index < lastAnswerRewrites.length) {
    return lastAnswerRewrites[index] || '';
  }
  return lastDebriefRewrite;
}

function answerReviewsHtml(reviews: Array<Record<string, unknown>>): string {
  if (!reviews.length) return '';
  const cards = reviews
    .map((r, idx) => {
      const question = decodeEntities(String(r['question'] || ''));
      const yours = decodeEntities(String(r['your_answer'] || ''));
      const stronger = decodeEntities(String(r['stronger_answer'] || ''));
      const scoreRaw = r['answer_score'];
      const score =
        typeof scoreRaw === 'number'
          ? scoreRaw
          : typeof scoreRaw === 'string'
            ? Number(scoreRaw)
            : null;
      const scoreLabel =
        score == null || Number.isNaN(score) ? '' : `<span class="mi-answer-score">${escapeHtml(String(score))}/10</span>`;
      return `
        <div class="mi-answer-review">
          <div class="mi-answer-review-head">
            <div class="mi-answer-review-label">Answer ${idx + 1}</div>
            ${scoreLabel}
          </div>
          ${question ? `<p class="mi-answer-q"><span class="mi-answer-kicker">Question</span> ${escapeHtml(question)}</p>` : ''}
          ${yours ? `<p class="mi-answer-yours"><span class="mi-answer-kicker">Your answer</span> ${escapeHtml(yours)}</p>` : ''}
          <div class="cover-letter-wrapper mi-rewrite-box">
            <div class="cover-letter-box">
              <div class="cover-letter-body">${escapeHtml(stronger || 'No stronger sample for this turn.')}</div>
              <div class="cover-letter-box-footer">
                <div class="cl-footer-meta"><span><i class="fas fa-magic" aria-hidden="true"></i> Stronger sample</span></div>
                <div class="cl-footer-actions">
                  <button type="button" class="cl-copy-btn" data-action="miCopyRewrite" data-index="${idx}" ${stronger ? '' : 'disabled'}>
                    <i class="fas fa-copy" aria-hidden="true"></i> Copy
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>`;
    })
    .join('');
  return `
    <div class="content-section">
      <div class="section-title"><i class="fas fa-comments" aria-hidden="true"></i> Stronger samples for your answers</div>
      <p class="mi-answer-reviews-note">A model rewrite for each answer you gave — use these as practice scripts, not scripts to memorize word-for-word.</p>
      <div class="mi-answer-reviews">${cards}</div>
    </div>`;
}

export function setThinking(on: boolean, badgeText = 'Loading…'): void {
  const badge = el('mi-thinking');
  if (badge && on) badge.textContent = badgeText;
  setHidden(badge, !on);
  const status = el('mi-session-status');
  if (status && on) {
    status.textContent = badgeText === 'Scoring…'
      ? 'Generating your debrief…'
      : 'Loading…';
  } else if (status && !on) {
    status.textContent = 'Practice in progress';
  }
}

/** Freeze the live UI while the debrief is being generated. */
export function setWrappingUpUi(): void {
  setThinking(true, 'Scoring…');
  setInterviewerTyping('Scoring your practice interview…');
  const ta = el('mi-answer') as HTMLTextAreaElement | null;
  if (ta) {
    ta.disabled = true;
    ta.placeholder = 'Scoring in progress…';
  }
  const submit = document.querySelector(
    '#pane-practice [data-action="miSubmit"]',
  ) as HTMLButtonElement | null;
  const mic = el('mi-mic-btn') as HTMLButtonElement | null;
  if (submit) submit.disabled = true;
  if (mic) mic.disabled = true;
}

export function clearWrappingUpUi(): void {
  const ta = el('mi-answer') as HTMLTextAreaElement | null;
  if (ta) {
    ta.disabled = false;
    ta.placeholder =
      'Type or speak your answer… Enter to send · Shift+Enter for a new line';
  }
  const submit = document.querySelector(
    '#pane-practice [data-action="miSubmit"]',
  ) as HTMLButtonElement | null;
  const mic = el('mi-mic-btn') as HTMLButtonElement | null;
  if (submit) submit.disabled = false;
  if (mic) mic.disabled = false;
}

function sessionBannerClasses(seconds: number | null): void {
  const banner = el('mi-session-banner');
  if (!banner) return;
  banner.classList.remove('apply-muted', 'apply-review', 'apply-poor', 'apply-good');
  if (seconds == null) {
    banner.classList.add('apply-muted');
    return;
  }
  if (seconds <= 0) banner.classList.add('apply-poor');
  else if (seconds <= 120) banner.classList.add('apply-review');
  else banner.classList.add('apply-muted');
}

export function setCountdown(seconds: number | null | undefined): void {
  const elTimer = el('mi-countdown');
  const warn = el('mi-time-warning');
  const thinking = el('mi-thinking');
  const status = el('mi-session-status');
  if (!elTimer) return;
  if (seconds == null) {
    elTimer.textContent = '—';
    setHidden(warn, true);
    sessionBannerClasses(null);
    return;
  }
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  elTimer.textContent = `${m}:${String(s).padStart(2, '0')}`;
  setHidden(warn, seconds > 120 || seconds <= 0);
  sessionBannerClasses(seconds);
  if (status && thinking?.classList.contains('is-hidden')) {
    status.textContent = seconds <= 120 ? 'Wrap up soon' : 'Practice in progress';
  }
}

export function setAnswerText(text: string): void {
  const ta = el('mi-answer') as HTMLTextAreaElement | null;
  if (ta) ta.value = text;
}

export function getAnswerText(): string {
  const ta = el('mi-answer') as HTMLTextAreaElement | null;
  return (ta?.value || '').trim();
}

export function clearAnswer(): void {
  setAnswerText('');
}

export function appendTranscriptLine(role: string, text: string): void {
  const list = el('mi-transcript');
  if (!list) return;
  const row = document.createElement('div');
  row.className = `mi-turn mi-turn-${role === 'interviewer' ? 'ai' : 'you'}`;
  const roleLabel = role === 'interviewer' ? 'Interviewer' : 'You';
  row.innerHTML = `<span class="mi-turn-role">${escapeHtml(roleLabel)}</span><span class="mi-turn-text">${escapeHtml(text)}</span>`;
  list.appendChild(row);
  list.scrollTop = list.scrollHeight;
}

export function clearTranscript(): void {
  const list = el('mi-transcript');
  if (list) list.innerHTML = '';
}

function debriefTier(score: number | null): { banner: string; icon: string } {
  if (score == null || Number.isNaN(score)) {
    return { banner: 'apply-muted', icon: 'fa-flag-checkered' };
  }
  if (score >= 8) return { banner: 'apply-good', icon: 'fa-check-circle' };
  if (score >= 5) return { banner: 'apply-review', icon: 'fa-chart-line' };
  return { banner: 'apply-poor', icon: 'fa-exclamation-circle' };
}

export function renderDebrief(
  debrief: Record<string, unknown> | null | undefined,
): void {
  const root = el('mi-debrief');
  const scoreEl = el('mi-final-score');
  const recEl = el('mi-result-rec');
  const banner = el('mi-results-banner');
  const icon = el('mi-result-icon');
  if (!root) return;

  if (!debrief) {
    lastDebriefRewrite = '';
    lastAnswerRewrites = [];
    if (scoreEl) scoreEl.textContent = '–';
    if (recEl) recEl.textContent = 'No debrief available';
    root.innerHTML = '<p class="text-muted">No debrief available.</p>';
    return;
  }

  const overallRaw = debrief.overall_score;
  const overall =
    typeof overallRaw === 'number'
      ? overallRaw
      : typeof overallRaw === 'string'
        ? Number(overallRaw)
        : null;
  const tier = debriefTier(overall);
  const summary = decodeEntities(String(debrief.summary || ''));
  if (scoreEl) scoreEl.textContent = overall == null || Number.isNaN(overall) ? '–' : String(overall);
  if (recEl) recEl.textContent = shortVerdict(summary, overall);
  if (banner) {
    banner.classList.remove('apply-muted', 'apply-review', 'apply-poor', 'apply-good');
    banner.classList.add(tier.banner);
  }
  if (icon) icon.className = `fas ${tier.icon} apply-icon`;

  const scores = (debrief.scores || {}) as Record<string, number>;
  const strengths = Array.isArray(debrief.strengths) ? debrief.strengths : [];
  const improvements = Array.isArray(debrief.improvements) ? debrief.improvements : [];
  const rewrite = decodeEntities(String(debrief.weakest_answer_rewrite || ''));
  lastDebriefRewrite = rewrite;
  const reviewsRaw = Array.isArray(debrief.answer_reviews)
    ? (debrief.answer_reviews as Array<Record<string, unknown>>)
    : [];
  // Legacy debriefs only had weakest_answer_rewrite — show that as a single review.
  const reviews =
    reviewsRaw.length > 0
      ? reviewsRaw
      : rewrite
        ? [
            {
              question: '',
              your_answer: '',
              answer_score: '',
              stronger_answer: rewrite,
            },
          ]
        : [];
  lastAnswerRewrites = reviews.map((r) => decodeEntities(String(r['stronger_answer'] || '')));

  root.innerHTML = `
    <div class="content-section">
      <div class="section-title"><i class="fas fa-chart-bar" aria-hidden="true"></i> Score breakdown</div>
      <div class="jd-glance-grid mi-score-grid">
        ${scoreGlance('content', 'Content', 'fa-align-left', scores.content)}
        ${scoreGlance('structure', 'Structure', 'fa-layer-group', scores.structure)}
        ${scoreGlance('clarity', 'Clarity', 'fa-comment', scores.clarity)}
        ${scoreGlance('role_fit', 'Role fit', 'fa-briefcase', scores.role_fit)}
        ${scoreGlance('style_focus', 'Style focus', 'fa-bullseye', scores.style_focus)}
      </div>
    </div>
    <div class="content-section">
      <div class="section-title"><i class="fas fa-thumbs-up" aria-hidden="true"></i> Strengths</div>
      ${bulletList(strengths, 'green', 'fa-check')}
    </div>
    <div class="content-section">
      <div class="section-title"><i class="fas fa-lightbulb" aria-hidden="true"></i> Improvements</div>
      ${bulletList(improvements, 'amber', 'fa-arrow-up')}
    </div>
    ${answerReviewsHtml(reviews)}
  `;
}

export function notify(msg: string, type: 'success' | 'error' | 'warning' | 'info' = 'info'): void {
  const w = window as Window & {
    showApplicationToast?: (m: string, t?: string) => void;
    app?: { showNotification?: (m: string, t?: string) => void };
  };
  if (typeof w.showApplicationToast === 'function') {
    w.showApplicationToast(msg, type);
    return;
  }
  if (w.app?.showNotification) {
    w.app.showNotification(msg, type);
  }
}
