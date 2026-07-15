import { escapeHtml } from '../shared/dom-security';
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
  if (startBtn) startBtn.disabled = !ready;
}

export function setInterviewerSpeak(text: string): void {
  const box = el('mi-interviewer-text');
  if (!box) return;
  box.classList.remove('mi-typing');
  box.textContent = text;
}

/** Placeholder while waiting for the first streamed speak characters. */
export function setInterviewerTyping(): void {
  const box = el('mi-interviewer-text');
  if (!box) return;
  box.classList.add('mi-typing');
  box.textContent = 'Interviewer is typing…';
}

export function appendInterviewerDelta(delta: string): void {
  if (!delta) return;
  const box = el('mi-interviewer-text');
  if (!box) return;
  if (box.classList.contains('mi-typing')) {
    box.classList.remove('mi-typing');
    box.textContent = delta;
    return;
  }
  box.textContent = (box.textContent || '') + delta;
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
  box.innerHTML = `<i class="fas fa-lightbulb me-2" aria-hidden="true"></i>${escapeHtml(text)}`;
  setHidden(box, false);
}

const CATEGORY_LABELS: Record<string, string> = {
  behavioral: 'Behavioral',
  technical: 'Technical',
  role_specific: 'Role',
  company_specific: 'Company',
};

export function renderCoverage(
  plan: Array<Record<string, unknown>> | null | undefined,
  coveredIds: string[] | null | undefined,
): void {
  const root = el('mi-coverage');
  if (!root) return;
  const items = Array.isArray(plan) ? plan : [];
  const covered = new Set((coveredIds || []).map(String));
  if (!items.length) {
    root.innerHTML = '<span class="mi-coverage-empty">Topics appear after the first question.</span>';
    return;
  }
  root.innerHTML = items
    .map((p) => {
      const id = String(p['id'] || '');
      const cat = String(p['category'] || 'behavioral');
      const label = CATEGORY_LABELS[cat] || cat;
      const done = covered.has(id);
      const icon = done ? 'fa-check-circle' : 'fa-circle';
      return `<span class="mi-coverage-item${done ? ' done' : ''}"><i class="fas ${icon}" aria-hidden="true"></i>${escapeHtml(label)}</span>`;
    })
    .join('');
}


export function setThinking(on: boolean): void {
  setHidden(el('mi-thinking'), !on);
  const status = el('mi-session-status');
  if (status && on) status.textContent = 'Interviewer is typing…';
  else if (status && !on) status.textContent = 'Practice in progress';
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
  setHidden(warn, seconds > 120);
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

export function renderDebrief(debrief: Record<string, unknown> | null | undefined): void {
  const root = el('mi-debrief');
  const scoreEl = el('mi-final-score');
  const recEl = el('mi-result-rec');
  const banner = el('mi-results-banner');
  const icon = el('mi-result-icon');
  if (!root) return;

  if (!debrief) {
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
  if (scoreEl) scoreEl.textContent = overall == null || Number.isNaN(overall) ? '–' : String(overall);
  if (recEl) recEl.textContent = String(debrief.summary || 'Practice complete');
  if (banner) {
    banner.classList.remove('apply-muted', 'apply-review', 'apply-poor', 'apply-good');
    banner.classList.add(tier.banner);
  }
  if (icon) icon.className = `fas ${tier.icon} apply-icon`;

  const scores = (debrief.scores || {}) as Record<string, number>;
  const strengths = Array.isArray(debrief.strengths) ? debrief.strengths : [];
  const improvements = Array.isArray(debrief.improvements) ? debrief.improvements : [];
  const rewrite = String(debrief.weakest_answer_rewrite || '');

  root.innerHTML = `
    <div class="content-section">
      <div class="section-title"><i class="fas fa-chart-bar" aria-hidden="true"></i> Score breakdown</div>
      <div class="mi-score-grid">
        <div class="mi-score-chip">Content<strong>${escapeHtml(String(scores.content ?? '—'))}</strong></div>
        <div class="mi-score-chip">Structure<strong>${escapeHtml(String(scores.structure ?? '—'))}</strong></div>
        <div class="mi-score-chip">Clarity<strong>${escapeHtml(String(scores.clarity ?? '—'))}</strong></div>
        <div class="mi-score-chip">Role fit<strong>${escapeHtml(String(scores.role_fit ?? '—'))}</strong></div>
        <div class="mi-score-chip">Style focus<strong>${escapeHtml(String(scores.style_focus ?? '—'))}</strong></div>
      </div>
      <p class="mi-summary">${escapeHtml(String(debrief.summary || ''))}</p>
    </div>
    <div class="content-section">
      <div class="section-title"><i class="fas fa-thumbs-up" aria-hidden="true"></i> Strengths</div>
      <ul class="content-list">${strengths.map((s) => `<li>${escapeHtml(String(s))}</li>`).join('') || '<li class="text-muted">None listed</li>'}</ul>
    </div>
    <div class="content-section">
      <div class="section-title"><i class="fas fa-lightbulb" aria-hidden="true"></i> Improvements</div>
      <ul class="content-list">${improvements.map((s) => `<li>${escapeHtml(String(s))}</li>`).join('') || '<li class="text-muted">None listed</li>'}</ul>
    </div>
    <div class="content-section">
      <div class="section-title"><i class="fas fa-pen" aria-hidden="true"></i> Stronger answer example</div>
      <div class="mi-rewrite">${escapeHtml(rewrite || 'No rewrite available.')}</div>
    </div>
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
