import { escapeHtml } from '../shared/dom-security';
import { el, getVal, showOutput } from './dom';
import {
  getJob3Visible,
  setJob3Visible,
} from './state-access';
import { postTool } from './tool-request';
import type { DecisionFactor, JobComparisonJobInput } from './types';

export function toggleJob3(): void {
  const next = !getJob3Visible();
  setJob3Visible(next);
  const body = el('job3Body');
  const icon = el('job3ToggleIcon');
  const text = el('job3ToggleText');
  if (body) body.style.display = next ? 'block' : 'none';
  if (icon) icon.className = next ? 'fas fa-minus me-1' : 'fas fa-plus me-1';
  if (text) text.textContent = next ? 'Remove' : 'Add';
}

function displayComparisonResult(data: Record<string, unknown>): void {
  const sumEl = el('comparisonSummary');
  if (sumEl) {
    const conf = String(data.recommendation_confidence ?? '').toLowerCase();
    const confClass = conf === 'high' ? 'high' : conf === 'low' ? 'low' : 'medium';
    sumEl.innerHTML = `
                <div class="comp-recommendation-card">
                    <div class="comp-recommendation-label">Recommendation</div>
                    <div class="comp-recommendation-value">
                        ${escapeHtml(String(data.recommended_job ?? ''))}
                        <span class="comp-confidence-badge comp-confidence-badge--${escapeHtml(confClass)}">${escapeHtml(confClass)} confidence</span>
                    </div>
                    <div class="comp-recommendation-text">${escapeHtml(String(data.executive_summary ?? ''))}</div>
                </div>`;
  }

  const jobsEl = el('jobCards');
  if (jobsEl) {
    const jobs = data.jobs_analysis as Record<string, unknown>[] | undefined ?? [];
    jobsEl.innerHTML = jobs
      .map((job) => {
        const isRec = job.job_identifier === data.recommended_job;
        const title = String(job.title ?? '');
        const company = String(job.company ?? '');
        const pros = job.pros as string[] | undefined ?? [];
        const cons = job.cons as string[] | undefined ?? [];
        const idealFor = String(job.ideal_for ?? '');
        const score = escapeHtml(String(job.overall_score ?? ''));
        return `
                <div class="comp-job-card${isRec ? ' comp-job-card--recommended' : ''}">
                    <div class="comp-job-body">
                        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:0.5rem;margin-bottom:0.75rem;">
                            <div class="comp-job-title-text" style="margin:0;">${escapeHtml(title)} <span style="font-weight:400;font-size:0.82rem;color:var(--text-muted);">(${escapeHtml(company)})</span></div>
                            <span class="comp-job-score-badge" style="flex-shrink:0;">${score}/100</span>
                        </div>
                        <div class="comp-pros-header"><i class="fas fa-plus"></i> Pros</div>
                        <ul class="comp-job-list">${pros.map((p) => `<li>${escapeHtml(String(p))}</li>`).join('')}</ul>
                        <div class="comp-cons-header"><i class="fas fa-minus"></i> Cons</div>
                        <ul class="comp-job-list">${cons.map((c) => `<li>${escapeHtml(String(c))}</li>`).join('')}</ul>
                        ${idealFor ? `<div class="comp-ideal-for">Ideal for: ${escapeHtml(idealFor)}</div>` : ''}
                    </div>
                </div>`;
      })
      .join('');
  }

  const dfEl = el('decisionFactors');
  if (dfEl) {
    const factors = data.decision_factors as DecisionFactor[] | undefined ?? [];
    dfEl.innerHTML =
      factors.length > 0
        ? factors
            .map((f) => {
              const imp = (f.importance ?? '').toLowerCase();
              const impClass = imp === 'high' ? 'high' : imp === 'low' ? 'low' : 'medium';
              return `<div class="decision-factor-row">
                        <div class="decision-factor-left">
                            <span class="decision-factor-name">${escapeHtml(String(f.factor ?? ''))}</span>
                            <span class="decision-factor-winner">${escapeHtml(String(f.winner ?? ''))}</span>
                            <span class="decision-factor-importance decision-factor-importance--${escapeHtml(impClass)}">${escapeHtml(imp)}</span>
                        </div>
                        <div class="decision-factor-explanation">${escapeHtml(String(f.explanation ?? ''))}</div>
                    </div>`;
            })
            .join('')
        : '<span style="color:var(--text-muted);font-size:0.875rem;">No decision factors available.</span>';
  }

  const qEl = el('questionsToAsk');
  if (qEl) {
    qEl.innerHTML = (data.questions_to_ask as string[] | undefined ?? [])
      .map(
        (q) =>
          `<div class="rejection-item"><div class="rejection-item-icon"><i class="fas fa-question-circle"></i></div><span>${escapeHtml(String(q))}</span></div>`,
      )
      .join('');
  }

  const advEl = el('comparisonAdvice');
  if (advEl) advEl.textContent = String(data.final_advice ?? '');

  showOutput('comparisonOutput');
}

export async function handleComparisonSubmit(event: Event): Promise<void> {
  event.preventDefault();
  const jobs: JobComparisonJobInput[] = [
    {
      title: getVal('job1Title'),
      company: getVal('job1Company'),
      description: getVal('job1Description') || null,
    },
    {
      title: getVal('job2Title'),
      company: getVal('job2Company'),
      description: getVal('job2Description') || null,
    },
  ];
  if (getJob3Visible() && getVal('job3Title') && getVal('job3Company')) {
    jobs.push({
      title: getVal('job3Title'),
      company: getVal('job3Company'),
      description: getVal('job3Description') || null,
    });
  }
  await postTool(
    '/tools/job-comparison',
    {
      jobs,
      user_context: { priorities: getVal('userPriorities') || null },
    },
    {
      loadingMessage: 'Comparing jobs...',
      successMessage: 'Job comparison complete!',
      failureMessage: 'Failed to compare jobs',
      retryMessage: 'Failed to compare jobs. Please try again.',
      onSuccess: displayComparisonResult,
    },
  );
}
