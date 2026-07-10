import { decodeEntities, escapeHtml } from '../shared/dom-security';
import { el, setHidden } from './dom';
import {
  chartScoreClass,
  progressAnswerText,
  resultBannerClass,
  resultBannerIcon,
  scoreClass,
  scoreTier,
  stopReasonLabel,
} from './labels';
import { showSection } from './dom';
import { getAuthToken } from '../shared/auth';
import { getSessionId, setCoverLetter, setOptimizedCv, getCoverLetter, getOptimizedCv } from './state-access';
import type { CvOptimizationResult, CvOptimizerResultResponse } from './types';

export function buildIterationAccordionHtml(
  iteration: number,
  score: number,
  strengths: string[],
  gaps: string[],
  actionItems: string[],
  summarySuffix?: string,
): string {
  const scoreText = typeof score === 'number' ? score.toFixed(1) : '–';
  const suffix = summarySuffix ? escapeHtml(summarySuffix) : '';
  const actions = actionItems || [];
  const actionsHtml = actions.length > 0
    ? `<div class="cvo-fb-section"><strong>Action items</strong>
      <ul>${actions.map(a => `<li>${escapeHtml(a)}</li>`).join('')}</ul>
    </div>`
    : '';
  return `<details class="cvo-history-item">
    <summary>Iteration ${escapeHtml(String(iteration + 1))} — <span class="cvo-history-score ${scoreClass(score)}">${scoreText}/10</span>${suffix}</summary>
    <div class="cvo-fb-section"><strong>Strengths</strong>
      <ul>${(strengths || []).map(s => `<li>${escapeHtml(s)}</li>`).join('')}</ul>
    </div>
    <div class="cvo-fb-section"><strong>Gaps</strong>
      <ul>${(gaps || []).map(g => `<li>${escapeHtml(g)}</li>`).join('')}</ul>
    </div>
    ${actionsHtml}
  </details>`;
}

export function updateProgressView(
  iteration: number,
  score: number,
  strengths: string[],
  gaps: string[],
  actionItems: string[],
): void {
  const counter = el('cvo-iteration-counter');
  if (counter) counter.textContent = decodeEntities(`Iteration ${iteration + 1}`);

  const answerEl = el('cvo-progress-answer');
  if (answerEl) answerEl.textContent = progressAnswerText(score);

  const tier = scoreTier(score);
  const banner = el('cvo-score-display');
  if (banner) {
    banner.className = 'apply-decision-banner cvo-progress-banner ' + tier.bannerClass;
  }

  const iconEl = el('cvo-progress-icon');
  if (iconEl) {
    iconEl.className = 'fas ' + tier.icon + ' apply-icon' + (tier.spinning ? ' fa-spin' : '');
  }

  const statusEl = el('cvo-progress-status');
  if (statusEl) {
    statusEl.textContent = typeof score === 'number'
      ? `Iteration ${iteration + 1} complete — revising CV…`
      : 'Waiting for first evaluation…';
  }

  const log = el('cvo-iteration-log');
  if (!log) return;

  const wrap = document.createElement('div');
  wrap.innerHTML = buildIterationAccordionHtml(iteration, score, strengths, gaps, actionItems, '');
  const item = wrap.firstElementChild;
  if (item) {
    log.appendChild(item);
    log.scrollTop = log.scrollHeight;
  }
}

export function renderResults(result: CvOptimizationResult): void {
  setOptimizedCv(result.optimized_cv || '');
  setCoverLetter(result.cover_letter || '');

  const banner = el('cvo-results-banner');
  const iconEl = el('cvo-result-icon');
  const bannerClass = resultBannerClass(result.stop_reason);
  if (banner) {
    banner.className = 'apply-decision-banner cvo-results-banner ' + bannerClass;
  }
  if (iconEl) {
    iconEl.className = 'fas ' + resultBannerIcon(result.stop_reason) + ' apply-icon';
  }

  const finalScoreEl = el('cvo-final-score');
  if (finalScoreEl) {
    finalScoreEl.textContent = typeof result.best_score === 'number'
      ? result.best_score.toFixed(1)
      : '–';
  }

  const stopBadge = el('cvo-stop-reason-badge');
  if (stopBadge) {
    stopBadge.textContent = decodeEntities(stopReasonLabel(result.stop_reason));
  }

  const noticeText = el('cvo-results-notice-text');
  if (noticeText) {
    noticeText.textContent = result.stop_reason === 'api_rate_limit'
      ? 'The AI quota or rate limit was reached before the run could finish. The results below show your best progress so far — try again later or review your API key under Settings \u2192 AI Setup.'
      : 'Review carefully before submitting — verify every claim matches your profile and experience.';
  }

  const chartEl = el('cvo-score-chart');
  if (chartEl && Array.isArray(result.iteration_history)) {
    const chart = document.createElement('div');
    chart.className = 'cvo-chart';
    result.iteration_history.forEach(r => {
      const wrap = document.createElement('div');
      wrap.className = 'cvo-chart-bar-wrap';
      const bar = document.createElement('div');
      bar.className = 'cvo-chart-bar ' + chartScoreClass(r.score);
      bar.setAttribute('data-score', String(Math.round(r.score)));
      const label = document.createElement('span');
      label.className = 'cvo-chart-label';
      label.textContent = typeof r.score === 'number' ? r.score.toFixed(1) : '–';
      const iterLabel = document.createElement('span');
      iterLabel.className = 'cvo-chart-iter';
      iterLabel.textContent = 'Iter ' + String(r.iteration + 1);
      wrap.appendChild(iterLabel);
      wrap.appendChild(bar);
      wrap.appendChild(label);
      chart.appendChild(wrap);
    });
    chartEl.innerHTML = '';
    chartEl.appendChild(chart);
  }

  const cvEl = el('cvo-optimized-cv');
  if (cvEl) cvEl.textContent = decodeEntities(getOptimizedCv());

  const clEl = el('cvo-cover-letter');
  const clMissing = el('cvo-cover-letter-missing');
  const clDoc = el('cvo-cover-letter-doc');
  if (getCoverLetter()) {
    if (clEl) clEl.textContent = decodeEntities(getCoverLetter());
    setHidden(clMissing, true);
    setHidden(clDoc, false);
    updateDocFooterMeta('cvo-cl-word-count', 'cvo-cl-generated-at', getCoverLetter(), result.completed_at);
  } else {
    if (clEl) clEl.textContent = '';
    setHidden(clMissing, false);
    setHidden(clDoc, true);
  }

  updateDocFooterMeta('cvo-cv-word-count', 'cvo-cv-generated-at', getOptimizedCv(), result.completed_at);

  const gapList = el('cvo-gap-list');
  if (gapList) {
    const gaps = result.gap_analysis || [];
    if (gaps.length === 0) {
      gapList.innerHTML = '<li><i class="fas fa-check green"></i><span>No persistent gaps identified.</span></li>';
    } else {
      gapList.innerHTML = gaps.map((g: string) => {
        return '<li><i class="fas fa-minus-circle amber"></i><span>' + escapeHtml(g) + '</span></li>';
      }).join('');
    }
  }

  // Iteration history accordion
  const accordion = el('cvo-history-accordion');
  if (accordion && Array.isArray(result.iteration_history)) {
    accordion.innerHTML = result.iteration_history.map(r => {
      const best = r.iteration === result.best_iteration ? ' (best)' : '';
      return buildIterationAccordionHtml(
        r.iteration,
        r.score,
        r.strengths || [],
        r.gaps || [],
        [],
        best
      );
    }).join('');
  }

  showSection('cvo-results');
}

export async function fetchAndRenderResult(): Promise<void> {
  const sessionId = getSessionId();
  if (!sessionId) return;

  try {
    const res = await fetch(
      `/api/v1/cv-optimizer/${encodeURIComponent(sessionId)}`,
      {
        credentials: 'same-origin',
        headers: { Authorization: `Bearer ${getAuthToken()}` },
      },
    );

    if (!res.ok) return;

    const data = (await res.json()) as CvOptimizerResultResponse;
    if (data.has_result && data.result) {
      renderResults(data.result);
    }
  } catch (err) {
    console.error('[cv-optimizer] result fetch failed', err);
  }
}

export function resetProgressView(): void {
  const counter = el('cvo-iteration-counter');
  if (counter) counter.textContent = 'Starting…';
  const answerEl = el('cvo-progress-answer');
  if (answerEl) answerEl.textContent = 'Evaluating…';
  const banner = el('cvo-score-display');
  if (banner) banner.className = 'apply-decision-banner apply-muted cvo-progress-banner';
  const iconEl = el('cvo-progress-icon');
  if (iconEl) iconEl.className = 'fas fa-chart-line apply-icon';
  const statusEl = el('cvo-progress-status');
  if (statusEl) statusEl.textContent = 'Waiting for first evaluation…';
  const log = el('cvo-iteration-log');
  if (log) log.innerHTML = '';
}

export function wordCount(text: string): number {
  if (!text || !String(text).trim()) return 0;
  return String(text).trim().split(/\s+/).filter(Boolean).length;
}

export function formatGeneratedDate(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

export function updateDocFooterMeta(
  wordCountId: string,
  generatedId: string,
  text: string,
  completedAt: string | null | undefined,
): void {
  const wordEl = el(wordCountId);
  if (wordEl) {
    wordEl.innerHTML = '<i class="fas fa-align-left"></i> ' + String(wordCount(text)) + ' words';
  }
  const genEl = el(generatedId);
  if (genEl) {
    const formatted = formatGeneratedDate(completedAt);
    if (formatted) {
      genEl.innerHTML = '<i class="fas fa-clock"></i> Generated ' + escapeHtml(formatted);
      genEl.classList.remove('is-hidden');
    } else {
      genEl.textContent = '';
      genEl.classList.add('is-hidden');
    }
  }
}
