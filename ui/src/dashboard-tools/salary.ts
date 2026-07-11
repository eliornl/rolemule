import { escapeHtml } from '../shared/dom-security';
import { notify } from './notify';
import { el, getVal, showOutput } from './dom';
import { postTool } from './tool-request';
import type { AlternativeAsk, PushbackResponse, SalaryScriptSection } from './types';

const SCRIPT_SECTIONS: SalaryScriptSection[] = [
  { label: 'Opening', key: 'opening', icon: 'fas fa-door-open' },
  { label: 'Value Statement', key: 'value_statement', icon: 'fas fa-star' },
  { label: 'Counter Offer', key: 'counter_offer', icon: 'fas fa-comments-dollar' },
  { label: 'Closing', key: 'closing', icon: 'fas fa-handshake' },
];

function displaySalaryResult(data: Record<string, unknown>): void {
  const ma = (data.market_analysis ?? {}) as Record<string, string>;
  const maEl = el('marketAnalysis');
  if (maEl) {
    maEl.innerHTML = `
            <div class="salary-market-grid">
                <div class="salary-stat-card">
                    <div class="salary-stat-label"><i class="fas fa-chart-bar"></i>Assessment</div>
                    <div class="salary-stat-value">${escapeHtml(ma.salary_assessment ?? '')}</div>
                </div>
                <div class="salary-stat-card">
                    <div class="salary-stat-label"><i class="fas fa-map-marker-alt"></i>Market Position</div>
                    <div class="salary-stat-value">${escapeHtml(ma.market_position ?? '')}</div>
                </div>
                <div class="salary-stat-card salary-stat-card--highlight">
                    <div class="salary-stat-label"><i class="fas fa-bullseye"></i>Recommended Target</div>
                    <div class="salary-stat-value salary-stat-target">${escapeHtml(ma.recommended_target ?? '')}</div>
                </div>
                <div class="salary-stat-card">
                    <div class="salary-stat-label"><i class="fas fa-arrows-alt-h"></i>Negotiation Room</div>
                    <div class="salary-stat-value">${escapeHtml(ma.negotiation_room ?? '')}</div>
                </div>
            </div>`;
  }

  const so = (data.strategy_overview ?? {}) as Record<string, string>;
  const stratCard = el('strategyCard');
  if (stratCard) {
    const confRaw = (so.confidence_level ?? '').toUpperCase();
    const confClass = confRaw.includes('HIGH')
      ? 'high'
      : confRaw.includes('LOW')
        ? 'low'
        : 'medium';
    stratCard.innerHTML = `
                <p class="salary-strategy-text">${escapeHtml(so.approach ?? '')}</p>
                <span class="salary-confidence-badge salary-confidence-badge--${escapeHtml(confClass)}">
                    <i class="fas fa-signal"></i>${escapeHtml(confRaw)}
                </span>`;
  }

  const script = (data.main_script ?? {}) as Record<string, string>;
  const msEl = el('mainScript');
  if (msEl) {
    msEl.innerHTML = SCRIPT_SECTIONS.map(
      (s) => `
                <div class="salary-script-section">
                    <div class="salary-script-label"><i class="${escapeHtml(s.icon)}"></i>${escapeHtml(s.label)}</div>
                    <div class="salary-script-text">${escapeHtml(script[s.key] ?? '')}</div>
                </div>`,
    ).join('');
  }

  const pbEl = el('pushbackResponses');
  if (pbEl) {
    pbEl.innerHTML = (data.pushback_responses as PushbackResponse[] | undefined ?? [])
      .map(
        (pb) => `
            <div class="pushback-card">
                <div class="pushback-scenario">"${escapeHtml(pb.scenario ?? '')}"</div>
                <div class="pushback-response">${escapeHtml(pb.response_script ?? '')}</div>
            </div>`,
      )
      .join('');
  }

  const altEl = el('alternativeAsks');
  if (altEl) {
    altEl.innerHTML = (data.alternative_asks as AlternativeAsk[] | undefined ?? [])
      .map((a) => {
        const lik = (a.likelihood ?? '').toLowerCase();
        const likClass = lik.includes('high')
          ? 'high'
          : lik.includes('low')
            ? 'low'
            : 'medium';
        return `<div class="alt-ask-card">
                <div class="alt-ask-left">
                    <div class="alt-ask-icon"><i class="fas fa-hand-holding-usd"></i></div>
                    <div class="alt-ask-info">
                        <div class="alt-ask-name">${escapeHtml(a.item ?? '')}</div>
                        <div class="alt-ask-value">${escapeHtml(a.value ?? '')}</div>
                    </div>
                </div>
                <span class="alt-ask-likelihood alt-ask-likelihood--${escapeHtml(likClass)}">${escapeHtml(a.likelihood ?? '')} likelihood</span>
            </div>`;
      })
      .join('');
  }

  const dnEl = (data.dos_and_donts ?? {}) as Record<string, string[]>;
  const dosEl = el('dosList');
  if (dosEl) {
    dosEl.innerHTML = (dnEl.dos ?? [])
      .map(
        (d) =>
          `<div class="dos-item"><i class="fas fa-check"></i><span>${escapeHtml(String(d))}</span></div>`,
      )
      .join('');
  }
  const dontEl = el('dontsList');
  if (dontEl) {
    dontEl.innerHTML = (dnEl.donts ?? [])
      .map(
        (d) =>
          `<div class="dont-item"><i class="fas fa-times"></i><span>${escapeHtml(String(d))}</span></div>`,
      )
      .join('');
  }

  const waEl = el('walkAwayPoint');
  if (waEl) {
    waEl.innerHTML = `
            <div class="walk-away-card">
                <div class="walk-away-header"><i class="fas fa-door-open"></i>Walk Away Point</div>
                <div class="walk-away-text">${escapeHtml(String(data.walk_away_point ?? ''))}</div>
            </div>`;
  }

  showOutput('salaryOutput');
}

export async function handleSalarySubmit(event: Event): Promise<void> {
  event.preventDefault();
  await postTool(
    '/tools/salary-coach',
    {
      job_title: getVal('salaryJobTitle'),
      company_name: getVal('salaryCompany'),
      offered_salary: getVal('offeredSalary'),
      additional_context: getVal('salaryDetails') || null,
    },
    {
      loadingMessage: 'Generating negotiation strategy...',
      successMessage: 'Negotiation strategy generated!',
      failureMessage: 'Failed to generate strategy',
      retryMessage: 'Failed to generate negotiation strategy. Please try again.',
      rateLimitMessage: 'Rate limit exceeded. Maximum 5 coaching sessions per hour.',
      onSuccess: displaySalaryResult,
    },
  );
}

export function copyAllScripts(): void {
  const app = window.app;
  const container = el('mainScript');
  const sections = container
    ? Array.from(container.querySelectorAll('.salary-script-section'))
    : [];
  const text = sections
    .map((section) => {
      const label = section.querySelector<HTMLElement>('.salary-script-label');
      const body = section.querySelector<HTMLElement>('.salary-script-text');
      const labelText = (label?.textContent ?? '').trim();
      const bodyText = (body?.textContent ?? '').trim();
      return `${labelText.toUpperCase()}\n${bodyText}`;
    })
    .join('\n\n');
  if (app && typeof app.copyToClipboard === 'function') {
    app.copyToClipboard(text);
    return;
  }
  navigator.clipboard
    .writeText(text)
    .then(() => notify('Script copied to clipboard!', 'success'))
    .catch((err) => {
      console.error('Failed to copy:', err);
      notify('Failed to copy to clipboard', 'danger');
    });
}
