import { escapeHtml } from '../shared/dom-security';
import { getCurrentSessionId } from './state';
import type { GenerateDocKind, ResumeRecommendations } from './types';
import { ensureArray } from './utils';
import { asResumeRecord, extractLevel, fieldStr, strField } from './render-resume-helpers';

type GenerateHandler = (kind: GenerateDocKind, btn: HTMLButtonElement) => void;
let resumeGenerateHandler: GenerateHandler | null = null;

export function wireResumeGenerate(handler: GenerateHandler): void {
  resumeGenerateHandler = handler;
}

export function resumeTipsHasFailure(resume: ResumeRecommendations | null | undefined): boolean {
    if (!resume || typeof resume !== 'object' || Object.keys(resume).length === 0) {
        return true;
    }
    const advice = asResumeRecord(resume.comprehensive_advice ?? resume);
    return !!(resume.error || advice['error'] || advice['parse_error']);
}

export function renderResumeTipsEmptyState() {
    const subTabsEl = document.querySelector('.sub-tabs[data-parent="resume"]') as HTMLElement | null;
    if (subTabsEl) subTabsEl.style.display = 'none';
    document.querySelectorAll('#pane-resume .sub-pane').forEach((pane) => pane.classList.remove('active'));
    const overviewPane = document.getElementById('sub-resume-overview');
    if (!overviewPane) return;
    overviewPane.classList.add('active');
    overviewPane.innerHTML = `<div class="empty-state">
                <i class="fas fa-file-alt empty-state-icon"></i>
                <p class="empty-state-title">Resume Tips</p>
                <p class="empty-state-desc">Get targeted resume improvements, ATS keyword optimization, and formatting advice for this specific role.</p>
                ${getCurrentSessionId() ? `<button class="regen-btn" id="generateResumeBtn">
                    <span class="spinner"></span>
                    <span class="btn-text">Generate Resume Tips</span>
                </button>` : ''}
            </div>`;
    const genBtn2 = document.getElementById('generateResumeBtn') as HTMLButtonElement | null;
    if (genBtn2 && resumeGenerateHandler) genBtn2.addEventListener('click', () => resumeGenerateHandler!('resume', genBtn2));
}

export function renderResumeTips(resume: ResumeRecommendations): void {
    if (resumeTipsHasFailure(resume)) {
        renderResumeTipsEmptyState();
        return;
    }

    const advice = asResumeRecord(resume.comprehensive_advice ?? resume);
    const quickWins = ensureArray(advice['quick_wins'] ?? resume.quick_wins);
    const strategic = asResumeRecord(advice['strategic_assessment'] ?? resume.strategic_assessment);
    const skills = asResumeRecord(advice['skills_section'] ?? resume.skills_section);
    const profSummary = asResumeRecord(advice['professional_summary'] ?? resume.professional_summary);
    const atsOpt = asResumeRecord(advice['ats_optimization'] ?? resume.ats_optimization);
    const expOpt = asResumeRecord(advice['experience_optimization'] ?? resume.experience_optimization);
    const redFlags = ensureArray(advice['red_flags_to_fix'] ?? resume.red_flags_to_fix);
    const finalChecklistRaw = asResumeRecord(advice['final_checklist'] ?? resume.final_checklist);
    const checklistItems = ensureArray(
      finalChecklistRaw['before_submitting'] ?? finalChecklistRaw,
    );
    const fileFormat = String(finalChecklistRaw['file_format'] ?? '');
    const fileNaming = String(finalChecklistRaw['file_naming'] ?? '');

    const mustInclude = ensureArray(skills['must_include_skills']);
    const skillsToAdd = ensureArray(skills['skills_to_add']);
    const skillsToRemove = ensureArray(skills['skills_to_remove_or_deprioritize']);
    const missingKeywords = ensureArray(atsOpt['critical_keywords_missing']);
    const formatRecs = ensureArray(atsOpt['format_recommendations']);
    const sectionOrder = ensureArray(atsOpt['section_order_recommendation']);
    const rolesToHighlight = ensureArray(expOpt['roles_to_highlight']);
    const rolesToMinimize = ensureArray(expOpt['roles_to_minimize']);

    const subTabsEl = document.querySelector('.sub-tabs[data-parent="resume"]') as HTMLElement | null;

    if (subTabsEl) subTabsEl.style.display = '';

    // ── Helper: extract level token (HIGH/MEDIUM/LOW) from a string ──

    // ── Sub-pane 1: Overview ────────────────────────────────────
    let overviewHtml = '';

    if (Object.keys(strategic).length > 0) {
        if (strategic['ats_pass_likelihood'] || strategic['interview_likelihood']) {
            overviewHtml += `<div class="resume-score-cards">`;
            if (strategic['ats_pass_likelihood']) {
                const a = extractLevel(String(strategic['ats_pass_likelihood']));
                overviewHtml += `<div class="resume-score-card ${a.level}">
                    <div class="resume-score-icon-circle ${a.level}"><i class="fas fa-robot"></i></div>
                    <div class="resume-score-label">ATS Pass Rate</div>
                    <div class="resume-score-value ${a.level}">${escapeHtml(a.levelText)}</div>
                    ${a.note ? `<div class="resume-score-note">${escapeHtml(a.note)}</div>` : ''}
                </div>`;
            }
            if (strategic['interview_likelihood']) {
                const iv = extractLevel(String(strategic['interview_likelihood']));
                overviewHtml += `<div class="resume-score-card ${iv.level}">
                    <div class="resume-score-icon-circle ${iv.level}"><i class="fas fa-user-tie"></i></div>
                    <div class="resume-score-label">Interview Likelihood</div>
                    <div class="resume-score-value ${iv.level}">${escapeHtml(iv.levelText)}</div>
                    ${iv.note ? `<div class="resume-score-note">${escapeHtml(iv.note)}</div>` : ''}
                </div>`;
            }
            overviewHtml += `</div>`;
        }
        if (strategic['current_competitiveness']) {
            overviewHtml += `<p class="resume-flat-text">${escapeHtml(strField(strategic['current_competitiveness']))}</p>`;
        }
        if (strategic['biggest_opportunity']) {
            overviewHtml += `<div class="resume-flat-callout tip"><i class="fas fa-lightbulb"></i> <strong>Biggest Opportunity:</strong> ${escapeHtml(strField(strategic['biggest_opportunity']))}</div>`;
        }
        if (strategic['biggest_risk']) {
            overviewHtml += `<div class="resume-flat-callout warn"><i class="fas fa-exclamation-triangle"></i> <strong>Main Risk:</strong> ${escapeHtml(strField(strategic['biggest_risk']))}</div>`;
        }
    }

    if (quickWins.length) {
        overviewHtml += `<div class="section-title" style="margin-top:1.5rem"><i class="fas fa-bolt"></i> Quick Wins</div>`;
        overviewHtml += quickWins.slice(0, 5).map((w) => {
            const rec = asResumeRecord(w);
            const action = escapeHtml(fieldStr(w, 'action') || String(w ?? ''));
            const impactRaw = strField(rec['impact']);
            const impact = impactRaw
                ? `<span class="resume-flat-badge sm ${escapeHtml(impactRaw.toLowerCase())}">${escapeHtml(impactRaw)}</span>`
                : '';
            return `<div class="quick-win">
                <div class="quick-win-icon"><i class="fas fa-check"></i></div>
                <div class="quick-win-text" style="flex:1">${action}</div>
                ${impact ? `<div style="display:flex;align-items:center;flex-shrink:0">${impact}</div>` : ''}
            </div>`;
        }).join('');
    }

    if (redFlags.length) {
        overviewHtml += `<div class="section-title" style="margin-top:1.5rem"><i class="fas fa-exclamation-circle"></i> Fix Before Applying</div>`;
        overviewHtml += redFlags.slice(0, 4).map((r) => {
            const rec = asResumeRecord(r);
            const issue = escapeHtml(fieldStr(r, 'issue', 'flag') || String(r ?? ''));
            const currentState = strField(rec['current_state']);
            const fix = strField(rec['recommended_fix']);
            return `<div class="resume-flag-card">
                <div class="resume-flag-issue"><i class="fas fa-exclamation-circle"></i> ${issue}</div>
                ${currentState ? `<div class="resume-flag-current"><span class="resume-flag-label">Now:</span> ${escapeHtml(currentState)}</div>` : ''}
                ${fix ? `<div class="resume-flag-fix"><i class="fas fa-wrench"></i> ${escapeHtml(fix)}</div>` : ''}
            </div>`;
        }).join('');
    }

    if (!overviewHtml) overviewHtml = '<div class="empty-state"><i class="fas fa-chart-bar"></i><p>No assessment data available.</p></div>';
    const overviewEl = document.getElementById('sub-resume-overview');
    if (overviewEl) overviewEl.innerHTML = overviewHtml;

    // ── Sub-pane 2: Experience ──────────────────────────────────
    let expHtml = '';

    const hasExpStrategy = expOpt['prioritization_strategy'] || expOpt['experience_gap_strategy'] || rolesToMinimize.length;
    if (hasExpStrategy) {
        expHtml += `<div class="section-title"><i class="fas fa-chart-line"></i> Experience Strategy</div>`;
        if (expOpt['prioritization_strategy']) {
            expHtml += `<div class="resume-exp-strategy-box">
                <div class="resume-exp-strategy-label"><i class="fas fa-bullseye"></i> What to Emphasize</div>
                <p>${escapeHtml(strField(expOpt['prioritization_strategy']))}</p>
            </div>`;
        }
        if (expOpt['experience_gap_strategy']) {
            expHtml += `<div class="resume-exp-strategy-box gap">
                <div class="resume-exp-strategy-label"><i class="fas fa-link"></i> Bridging the Gap</div>
                <p>${escapeHtml(strField(expOpt['experience_gap_strategy']))}</p>
            </div>`;
        }
        if (rolesToMinimize.length) {
            expHtml += `<div class="resume-flat-label" style="margin-top:0.75rem">De-emphasize These Roles</div>
            <div class="resume-flat-tags">${rolesToMinimize.slice(0, 4).map(r => `<span class="resume-flat-tag muted">${escapeHtml(String(r))}</span>`).join('')}</div>`;
        }
    }

    if (rolesToHighlight.length) {
        expHtml += `<div class="section-title" style="margin-top:1.5rem"><i class="fas fa-pencil-alt"></i> Bullet Rewrites by Role</div>`;
        expHtml += rolesToHighlight.map((role) => {
            const rec = asResumeRecord(role);
            const roleTitle = escapeHtml(fieldStr(role, 'role', 'title'));
            const company = escapeHtml(strField(rec['company']));
            const whyRelevant = strField(rec['why_relevant']);
            const bullets = ensureArray(rec['bullet_point_suggestions']);
            const kws = ensureArray(rec['keywords_to_add']);
            if (!bullets.length) return '';
            return `<div class="resume-role-block">
                <div class="resume-role-header">
                    <div class="resume-role-title">${roleTitle}${company ? `<span class="resume-role-company"> @ ${company}</span>` : ''}</div>
                    ${whyRelevant ? `<div class="resume-role-why"><i class="fas fa-info-circle"></i> ${escapeHtml(whyRelevant)}</div>` : ''}
                </div>
                <ul class="resume-bullet-list">
                    ${bullets.slice(0, 3).map(b => `<li><i class="fas fa-check green"></i><span>${escapeHtml(String(b))}</span></li>`).join('')}
                </ul>
                ${kws.length ? `<div class="resume-role-keywords"><span class="resume-role-kw-label">Add these keywords:</span> ${kws.slice(0, 4).map(k => `<span class="resume-flat-tag sm">${escapeHtml(String(k))}</span>`).join('')}</div>` : ''}
            </div>`;
        }).join('');
    }

    if (!expHtml) expHtml = '<div class="empty-state"><i class="fas fa-briefcase"></i><p>No experience data available.</p></div>';
    const expEl = document.getElementById('sub-resume-experience');
    if (expEl) expEl.innerHTML = expHtml;

    // ── Sub-pane 3: Keywords & ATS ──────────────────────────────
    let kwHtml = '';

    if (mustInclude.length) {
        kwHtml += `<div class="section-title"><i class="fas fa-star"></i> Must Include</div>`;
        kwHtml += `<div class="resume-flat-tags">${mustInclude.slice(0, 8).map((s) => {
            const skill = fieldStr(s, 'skill') || String(s ?? '');
            const reason = strField(asResumeRecord(s)['reason']);
            return `<span class="resume-flat-tag" title="${escapeHtml(reason)}">${escapeHtml(skill)}</span>`;
        }).join('')}</div>`;
    }

    if (missingKeywords.length) {
        kwHtml += `<div class="section-title" style="margin-top:1.5rem"><i class="fas fa-search"></i> Missing Keywords</div>`;
        kwHtml += missingKeywords.slice(0, 6).map((k) => {
            const rec = asResumeRecord(k);
            const keyword = escapeHtml(fieldStr(k, 'keyword') || String(k ?? ''));
            const importance = strField(rec['importance']);
            const whereToAdd = strField(rec['where_to_add']);
            return `<div class="resume-flat-row"><span class="resume-flat-row-text"><strong>${keyword}</strong>${whereToAdd ? ` &mdash; <span class="resume-flat-muted">add to ${escapeHtml(whereToAdd)}</span>` : ''}</span>${importance ? `<span class="resume-flat-badge sm ${escapeHtml(importance.toLowerCase())}">${escapeHtml(importance)}</span>` : ''}</div>`;
        }).join('');
    }

    if (atsOpt['keyword_density_issues']) {
        kwHtml += `<div class="resume-flat-callout neutral" style="margin-top:0.75rem"><i class="fas fa-balance-scale"></i> <strong>Keyword Density:</strong> ${escapeHtml(strField(atsOpt['keyword_density_issues']))}</div>`;
    }

    if (formatRecs.length) {
        kwHtml += `<div class="section-title" style="margin-top:1.5rem"><i class="fas fa-robot"></i> ATS Format Tips</div>`;
        kwHtml += `<ul class="resume-format-tips">${formatRecs.slice(0, 4).map(f => `<li><i class="fas fa-check-circle"></i> ${escapeHtml(String(f))}</li>`).join('')}</ul>`;
    }

    if (sectionOrder.length) {
        kwHtml += `<div class="section-title" style="margin-top:1.5rem"><i class="fas fa-list-ol"></i> Recommended Section Order</div>`;
        kwHtml += `<div class="resume-section-order">${sectionOrder.map((s, i) => `<span class="section-order-item"><span class="section-order-num">${i + 1}</span>${escapeHtml(String(s))}</span>`).join('<i class="fas fa-arrow-right section-order-arrow"></i>')}</div>`;
    }

    if (skillsToAdd.length || skillsToRemove.length) {
        kwHtml += `<div class="section-title" style="margin-top:1.5rem"><i class="fas fa-tools"></i> Skills to Update</div>`;
        kwHtml += `<div class="resume-skills-cols">`;
        if (skillsToAdd.length) {
            kwHtml += `<div class="resume-skills-col add">
                <div class="resume-skills-col-label"><i class="fas fa-plus-circle"></i> Add to Resume</div>
                <div class="resume-flat-tags">${skillsToAdd.slice(0, 6).map(s => `<span class="resume-flat-tag add-tag">${escapeHtml(String(s))}</span>`).join('')}</div>
            </div>`;
        }
        if (skillsToRemove.length) {
            kwHtml += `<div class="resume-skills-col remove">
                <div class="resume-skills-col-label"><i class="fas fa-minus-circle"></i> Remove / Deprioritize</div>
                <div class="resume-flat-tags">${skillsToRemove.slice(0, 6).map(s => `<span class="resume-flat-tag remove-tag">${escapeHtml(String(s))}</span>`).join('')}</div>
            </div>`;
        }
        kwHtml += `</div>`;
    }

    if (!kwHtml) kwHtml = '<div class="empty-state"><i class="fas fa-key"></i><p>No keyword data available.</p></div>';
    const kwEl = document.getElementById('sub-resume-keywords');
    if (kwEl) kwEl.innerHTML = kwHtml;

    // ── Sub-pane 4: Summary ─────────────────────────────────────
    let summaryHtml = '';

    if (profSummary['recommended_summary'] || profSummary['current_assessment']) {
        summaryHtml += `<div class="section-title"><i class="fas fa-align-left"></i> Professional Summary</div>`;
        if (profSummary['current_assessment']) {
            summaryHtml += `<div class="resume-flat-callout warn sm"><i class="fas fa-exclamation-circle"></i> <strong>Current issue:</strong> ${escapeHtml(strField(profSummary['current_assessment']))}</div>`;
        }
        if (profSummary['recommended_summary']) {
            summaryHtml += `<div class="resume-summary-box">
                <div class="resume-summary-body">${escapeHtml(strField(profSummary['recommended_summary']))}</div>
                <div class="resume-summary-footer">
                    <button class="cl-copy-btn" data-action="copy-text" data-copy-text="${escapeHtml(strField(profSummary['recommended_summary']))}" aria-label="Copy recommended summary">
                        <i class="fas fa-copy"></i> Copy
                    </button>
                </div>
            </div>`;
        }
        const keyElements = ensureArray(profSummary['key_elements_included']);
        if (keyElements.length) {
            summaryHtml += `<div class="resume-flat-label" style="margin-top:0.75rem">Key elements in this summary</div>`;
            summaryHtml += `<div class="resume-flat-tags">${keyElements.slice(0, 6).map(e => `<span class="resume-flat-tag sm">${escapeHtml(String(e))}</span>`).join('')}</div>`;
        }
    }

    if (checklistItems.length || fileFormat || fileNaming) {
        summaryHtml += `<div class="section-title" style="margin-top:1.5rem"><i class="fas fa-check-circle"></i> Before You Submit</div>`;
        if (fileFormat || fileNaming) {
            summaryHtml += `<div class="resume-submission-meta">`;
            if (fileFormat) summaryHtml += `<div class="resume-submission-item"><i class="fas fa-file-pdf"></i><span><strong>File format:</strong> ${escapeHtml(fileFormat)}</span></div>`;
            if (fileNaming) summaryHtml += `<div class="resume-submission-item"><i class="fas fa-tag"></i><span><strong>File name:</strong> <code class="resume-filename">${escapeHtml(fileNaming)}</code></span></div>`;
            summaryHtml += `</div>`;
        }
        if (checklistItems.length) {
            summaryHtml += `<div class="resume-flat-checklist">${checklistItems.slice(0, 6).map(c =>
                `<label class="resume-flat-check"><input type="checkbox"><span>${escapeHtml(String(c))}</span></label>`
            ).join('')}</div>`;
        }
    }

    if (!summaryHtml) summaryHtml = '<div class="empty-state"><i class="fas fa-align-left"></i><p>No summary data available.</p></div>';
    const summaryEl = document.getElementById('sub-resume-summary');
    if (summaryEl) summaryEl.innerHTML = summaryHtml;

    // ── Regenerate button ───────────────────────────────────────
    const regenEl = document.getElementById('resumeRegenBtn');
    if (regenEl) regenEl.innerHTML = `
        <div class="resume-flat-regen">
            <button class="regen-btn" data-action="regen-resume" aria-label="Regenerate resume advice">
                <span class="spinner"></span>
                <span class="btn-text"><i class="fas fa-sync-alt"></i> Regenerate Resume Advice</span>
            </button>
        </div>`;
}