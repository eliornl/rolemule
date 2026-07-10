import { escapeHtml } from '../shared/dom-security';
import { isPlaceholderCompanyName, resolveEffectiveCompanyName } from '../shared/dashboard-display';
import { asResumeRecord, strField } from './render-resume-helpers';
import { getCurrentSessionId, getWorkflowStatus } from './state';
import type { CompanyResearch, JobAnalysis, ProfileMatching } from './types';
import { ensureArray, formatPostedDate, toTitleCase } from './utils';

function skillLabel(s: unknown): string {
  if (typeof s === 'string') return s;
  const rec = asResumeRecord(s);
  return strField(rec['skill'] ?? rec['name']);
}

function toPercent(val: unknown): number {
  const n = typeof val === 'number' ? val : Number(val);
  if (Number.isNaN(n)) return 0;
  return n > 1 ? Math.round(n) : Math.round(n * 100);
}

function getBarClass(v: unknown): string {
  const n = typeof v === 'number' ? v : Number(v);
  const p = Number.isNaN(n) ? 0 : n > 1 ? n : n * 100;
  return p >= 70 ? 'good' : p >= 40 ? 'medium' : 'low';
}

function displayMissionVision(missionVision: unknown, effectiveCompanyName: string): string {
  const mv = strField(missionVision);
  if (!mv) return '';
  if (
    effectiveCompanyName &&
    /Unable to complete research for Employer not stated in posting/i.test(mv)
  ) {
    return '';
  }
  if (effectiveCompanyName && /^Unable to complete research for /i.test(mv)) {
    return `We couldn't automatically load company research for ${effectiveCompanyName}. Consider reviewing their website before your interview.`;
  }
  return mv;
}

function dbCheckItemHtml(label: string, item: Record<string, unknown>): string {
  const passed = Boolean(item['passed']);
  const status = strField(item['status']);
  const notes = strField(item['notes']);
  const statusText = status || (passed ? '✓ OK' : '⚠ Issue');
  return `<div class="deal-breaker-item"><div class="db-label">${label}</div><div class="db-value ${passed ? 'pass' : 'fail'}">${escapeHtml(statusText)}</div>${notes ? `<div class="db-notes">${escapeHtml(notes)}</div>` : ''}</div>`;
}

function breakdownScoreHtml(label: string, score: unknown, desc: string): string {
  if (score === undefined) return '';
  return `<div class="breakdown-item"><div class="breakdown-label">${label}</div><div class="breakdown-bar-container"><div class="breakdown-bar-fill ${getBarClass(score)}" data-pct="${toPercent(score)}"></div></div><div class="breakdown-score">${toPercent(score)}%</div><div class="breakdown-desc">${desc}</div></div>`;
}

type ContinueWorkflowHandler = () => void;

let continueWorkflowHandler: ContinueWorkflowHandler | null = null;

/** Wire after `continueWorkflow` is defined in the page entry (avoids circular imports). */
export function wireContinueWorkflow(handler: ContinueWorkflowHandler): void {
  continueWorkflowHandler = handler;
}

export function renderMainContent(
    job: JobAnalysis,
    company: CompanyResearch,
    match: ProfileMatching,
): void {
    // Merge skills
    const allSkillsSet = new Set<string>();
    const addSkills = (arr: unknown): void => {
        ensureArray(arr).forEach((s) => {
            const rec = asResumeRecord(s);
            const skill = typeof s === 'string' ? s : strField(rec['skill'] ?? rec['name']);
            if (skill) allSkillsSet.add(skill);
        });
    };
    addSkills(job.required_skills);
    addSkills(job.ats_keywords);
    addSkills(job.keywords);

    const qualifications = ensureArray(job.required_qualifications);
    const responsibilities = ensureArray(job.responsibilities).filter((r) => {
        const rec = asResumeRecord(r);
        const s = typeof r === 'string' ? r : strField(rec['text'] ?? rec['duty'] ?? rec['responsibility']);
        return s.trim().length > 0;
    });
    const preferredQuals = ensureArray(job.preferred_qualifications);
    const softSkills = ensureArray(job.soft_skills);

    // Match data
    const exec = asResumeRecord(match.executive_summary);
    const qa = asResumeRecord(match.quantified_assessment ?? match.final_scores);
    const detailed = asResumeRecord(match.detailed_analysis);
    const strengths = ensureArray(detailed['key_strengths'] ?? match.key_strengths);
    const gaps = ensureArray(detailed['critical_gaps'] ?? match.critical_gaps ?? match.gaps);

    const appStrategy = asResumeRecord(match.application_strategy);
    const competitive = asResumeRecord(match.competitive_positioning);
    const riskAssessment = asResumeRecord(match.risk_assessment);
    const dealBreakers = asResumeRecord(match.deal_breaker_analysis);
    const aiInsights = asResumeRecord(match.ai_insights);
    const qualAnalysis = asResumeRecord(match.qualification_analysis);
    const prefAnalysis = asResumeRecord(match.preference_analysis);

    // Company data
    const coreValues = ensureArray(company.core_values);
    const keyProducts = ensureArray(company.key_products);
    const appInsights = asResumeRecord(company.application_insights);
    const whatToEmphasize = ensureArray(company.what_to_emphasize ?? appInsights['what_to_emphasize']);
    const leadership = ensureArray(company.leadership_info);
    const competitors = ensureArray(company.competitors);
    const cultureFitSignals = ensureArray(appInsights['culture_fit_signals']);
    const redFlagsToWatch = ensureArray(appInsights['red_flags_to_watch']);
    const competitiveAdvantages = ensureArray(company.competitive_advantages);
    const growthOpportunities = ensureArray(company.growth_opportunities);
    const employeeBenefits = ensureArray(company.employee_benefits);

    const effectiveCompanyName = resolveEffectiveCompanyName({
        analysisCompanyName: job.company_name,
        applicationCompanyName: job.application_company_name,
        detectedCompany: job.detected_company,
    });
    const aboutCompanyHeading = effectiveCompanyName
        ? escapeHtml(effectiveCompanyName)
        : 'this opportunity';

    const researchQuality = String(company.research_quality || '').toLowerCase();
    const confidenceAssessment = asResumeRecord(company.confidence_assessment);
    const confidenceOverall = strField(confidenceAssessment['overall_confidence']).toUpperCase();
    const showUncertaintyBanner =
        researchQuality === 'uncertain' ||
        confidenceOverall === 'LOW';
    const showPostingOnlyBanner = researchQuality === 'posting_only';
    const missionVisionText = displayMissionVision(company.mission_vision, effectiveCompanyName);
    const recruitingAgencyLabel =
        effectiveCompanyName &&
        isPlaceholderCompanyName(job.company_name)
            ? effectiveCompanyName
            : '';

    // ========== SUB-PANE 1: COMPANY INFO ==========
    let companyHtml = '';
    if (company && Object.keys(company).length > 0) {
        let researchNoticeHtml = '';
        if (recruitingAgencyLabel) {
            researchNoticeHtml = `
                <div class="company-research-notice company-research-notice--posting-only" role="status">
                    <i class="fas fa-info-circle" aria-hidden="true"></i>
                    <div class="company-research-notice-body">
                        <strong>Posted by ${escapeHtml(recruitingAgencyLabel)} (recruiting agency).</strong>
                        <span>The actual hiring employer is not named in this posting. Details below are about the agency unless noted otherwise.</span>
                    </div>
                </div>`;
        } else if (showUncertaintyBanner) {
            researchNoticeHtml = `
                <div class="company-research-notice company-research-notice--uncertain" role="status">
                    <i class="fas fa-info-circle" aria-hidden="true"></i>
                    <div class="company-research-notice-body">
                        <strong>Company research may not match this employer.</strong>
                        <span>Details are based on the job posting where needed. Verify before interviews.</span>
                    </div>
                </div>`;
        } else if (showPostingOnlyBanner) {
            const noticeBody = `<strong>Employer not named in this posting.</strong>
                        <span>Guidance below is tailored to this role and industry, not a specific company.</span>`;
            researchNoticeHtml = `
                <div class="company-research-notice company-research-notice--posting-only" role="status">
                    <i class="fas fa-info-circle" aria-hidden="true"></i>
                    <div class="company-research-notice-body">
                        ${noticeBody}
                    </div>
                </div>`;
        }
        const _rawWebsite = company.website || '';
        const _validWebsite = /^https?:\/\//i.test(_rawWebsite) ? _rawWebsite : '';
        const safeWebsiteHref   = encodeURI(_validWebsite).replace(/"/g, '%22');
        const safeWebsiteLabel  = escapeHtml(_validWebsite ? _validWebsite.replace('https://', '').replace('http://', '') : '');
        companyHtml += `
            ${researchNoticeHtml}
            <div class="content-section">
                <h2 class="section-title"><i class="fas fa-building"></i> About ${aboutCompanyHeading}</h2>
                <div class="company-card">
                    <div class="company-stats">
                        <div class="company-stat">
                            <span class="stat-label">Industry</span>
                            <span class="stat-value">${escapeHtml(strField(company.industry) || 'Technology')}</span>
                        </div>
                        <div class="company-stat">
                            <span class="stat-label">Size</span>
                            <span class="stat-value">${escapeHtml(strField(company.company_size) || 'Not specified')}</span>
                        </div>
                        ${strField(company.headquarters) ? `<div class="company-stat"><span class="stat-label">Location</span><span class="stat-value">${escapeHtml(strField(company.headquarters))}</span></div>` : ''}
                        ${_validWebsite ? `<div class="company-stat"><span class="stat-label">Website</span><span class="stat-value"><a href="${safeWebsiteHref}" target="_blank" rel="noopener noreferrer" style="color: var(--accent-primary);">${safeWebsiteLabel}</a></span></div>` : ''}
                        ${company.founded_year ? `<div class="company-stat"><span class="stat-label">Founded</span><span class="stat-value">${escapeHtml(String(company.founded_year))}</span></div>` : ''}
                        ${strField(company.hiring_timeline) ? `<div class="company-stat"><span class="stat-label">Hiring Timeline</span><span class="stat-value">${escapeHtml(strField(company.hiring_timeline))} <span class="stat-estimated">(estimated)</span></span></div>` : ''}
                    </div>
                </div>
                ${missionVisionText ? `<div class="section-subtitle">Mission &amp; Vision</div><div class="mission-box"><i class="fas fa-bullseye"></i><span>${escapeHtml(missionVisionText)}</span></div>` : ''}
                ${keyProducts.length ? `<div class="section-subtitle">Key Products &amp; Services</div><div class="tags-grid">${keyProducts.slice(0, 8).map(p => `<span class="tag product">${escapeHtml(String(p))}</span>`).join('')}</div>` : ''}
                ${coreValues.length ? `<div class="section-subtitle">Values</div><div class="values-grid">${coreValues.map(v => {
                    const s = String(v);
                    const colonIdx = s.indexOf(':');
                    if (colonIdx > 0 && colonIdx < 40) {
                        const name = s.slice(0, colonIdx).trim();
                        const desc = s.slice(colonIdx + 1).trim();
                        return `<div class="value-card"><div class="value-name">${escapeHtml(name)}</div><div class="value-desc">${escapeHtml(desc)}</div></div>`;
                    }
                    return `<div class="value-card"><div class="value-name">${escapeHtml(s)}</div></div>`;
                }).join('')}</div>` : ''}
                ${(company.work_environment || company.diversity_inclusion || company.remote_work_policy || company.employee_satisfaction) ? `
                <div class="section-subtitle">Workplace Culture</div>
                <div class="company-detail-grid">
                    ${strField(company.work_environment) ? `<div class="company-detail-item"><div class="detail-label"><i class="fas fa-users"></i> Work Environment</div><div class="detail-value">${escapeHtml(strField(company.work_environment))}</div></div>` : ''}
                    ${strField(company.remote_work_policy) ? `<div class="company-detail-item"><div class="detail-label"><i class="fas fa-laptop-house"></i> Remote Policy</div><div class="detail-value">${escapeHtml(strField(company.remote_work_policy))}</div></div>` : ''}
                    ${strField(company.diversity_inclusion) ? `<div class="company-detail-item"><div class="detail-label"><i class="fas fa-globe"></i> Diversity &amp; Inclusion</div><div class="detail-value">${escapeHtml(strField(company.diversity_inclusion))}</div></div>` : ''}
                    ${strField(company.employee_satisfaction) ? `<div class="company-detail-item"><div class="detail-label"><i class="fas fa-smile"></i> Employee Satisfaction</div><div class="detail-value">${escapeHtml(strField(company.employee_satisfaction))}</div></div>` : ''}
                </div>` : ''}
                ${leadership.length ? `<div class="section-subtitle">Leadership</div><div class="leadership-grid">${leadership.slice(0, 3).map((rawL) => {
                    const l = asResumeRecord(rawL);
                    const bg = strField(l['background']);
                    return `<div class="leadership-card"><div class="leader-name">${escapeHtml(strField(l['name']) || 'Unknown')}</div><div class="leader-title">${escapeHtml(strField(l['title']))}</div>${bg ? `<div class="leader-bg">${escapeHtml(bg.substring(0, 100))}${bg.length > 100 ? '...' : ''}</div>` : ''}</div>`;
                }).join('')}</div>` : ''}
                ${employeeBenefits.length ? `<div class="section-subtitle">Benefits</div><div class="tags-grid">${employeeBenefits.slice(0, 8).map((b) => `<span class="tag benefit">${escapeHtml(String(b))}</span>`).join('')}</div>` : ''}
                ${(competitors.length || company.market_position || competitiveAdvantages.length || growthOpportunities.length || company.recent_developments) ? `
                <div class="section-subtitle">Market Context</div>
                ${competitors.length ? `<div class="context-row"><span class="context-label">Competitors</span><div class="tags-grid inline">${competitors.slice(0, 6).map(c => `<span class="tag competitor">${escapeHtml(String(c))}</span>`).join('')}</div></div>` : ''}
                ${strField(company.market_position) ? `<div class="context-row"><span class="context-label">Position</span><span class="context-value">${escapeHtml(strField(company.market_position))}</span></div>` : ''}
                ${competitiveAdvantages.length ? `<ul class="content-list" style="margin-top:0.5rem">${competitiveAdvantages.slice(0, 4).map(a => `<li><i class="fas fa-shield-alt green"></i><span>${escapeHtml(String(a))}</span></li>`).join('')}</ul>` : ''}
                ${growthOpportunities.length ? `<div class="section-subtitle" style="margin-top:0.75rem">Growth Opportunities</div><ul class="content-list">${growthOpportunities.slice(0, 3).map(g => `<li><i class="fas fa-chart-line green"></i><span>${escapeHtml(String(g))}</span></li>`).join('')}</ul>` : ''}
                ${strField(company.recent_developments) ? `<div class="recent-dev-box"><i class="fas fa-newspaper"></i><div><div class="recent-dev-label">Recent Developments${strField(company.research_date) ? ` <span class="recent-dev-date">as of ${escapeHtml(strField(company.research_date))}</span>` : ''}</div><div class="recent-dev-text">${escapeHtml(strField(company.recent_developments))}</div></div></div>` : ''}
                ` : ''}
                ${whatToEmphasize.length ? `<div class="section-subtitle">What They Look For</div><ul class="content-list">${whatToEmphasize.slice(0, 6).map(w => `<li><i class="fas fa-crosshairs orange"></i><span>${escapeHtml(String(w))}</span></li>`).join('')}</ul>` : ''}
                ${cultureFitSignals.length ? `<div class="section-subtitle">How to Show Culture Fit</div><ul class="content-list">${cultureFitSignals.slice(0, 4).map(c => `<li><i class="fas fa-lightbulb green"></i><span>${escapeHtml(String(c))}</span></li>`).join('')}</ul>` : ''}
                ${redFlagsToWatch.length ? `<div class="section-subtitle watch-out-title"><i class="fas fa-exclamation-triangle"></i> Things to Be Aware Of</div><div class="watch-out-note">Keep these in mind — they are patterns that tend to not land well at this company.</div><ul class="content-list warning-list">${redFlagsToWatch.slice(0, 4).map(r => `<li><i class="fas fa-minus-circle amber"></i><span>${escapeHtml(String(r))}</span></li>`).join('')}</ul>` : ''}
            </div>`;
    } else {
        const isBelowGate = getWorkflowStatus() === 'awaiting_confirmation';
        const matchRec = strField(exec['recommendation'] ?? match.recommendation).toUpperCase();
        const isWeakMatch = matchRec === 'NOT_RECOMMENDED' || matchRec === 'WEAK_MATCH';
        if (isBelowGate || isWeakMatch) {
            companyHtml = `
                <div class="empty-state">
                    <i class="fas fa-building empty-state-icon"></i>
                    <p class="empty-state-title">Company Research</p>
                    <p class="empty-state-desc">Company research was skipped due to a low match score. You can still continue — company research, cover letter, and resume tips will all be generated.</p>
                    ${getCurrentSessionId() ? `<button class="regen-btn" id="continueWorkflowBtn" data-action="continue-workflow">
                        <span class="spinner"></span>
                        <span class="btn-text">Run Full Analysis Anyway</span>
                    </button>` : ''}
                </div>`;
        } else {
            companyHtml = '<div class="empty-state"><i class="fas fa-building"></i><p>Company information not available.</p></div>';
        }
    }
    const ccEl = document.getElementById('companyContent');
    if (ccEl) ccEl.innerHTML = companyHtml;
    const continueBtn = document.getElementById('continueWorkflowBtn');
    if (continueBtn && continueWorkflowHandler) {
        continueBtn.addEventListener('click', continueWorkflowHandler);
    }

    // ========== SUB-PANE 2: YOUR FIT ==========
    const verdict = strField(exec['one_line_verdict'] ?? exec['fit_assessment'] ?? match.fit_assessment);
    const qualScore = qa['qualification_match_score'] ?? match.qualification_score ?? 0;
    const prefScore = qa['preference_match_score'] ?? match.preference_score ?? 0;
    const overallScore = qa['overall_match_score'] ?? match.overall_match_score ?? match.overall_score ?? 0;
    const recommendation = strField(exec['recommendation']).toUpperCase();
    const confidenceLevel = strField(exec['confidence_level']).toUpperCase();

    // Apply decision data
    const shouldApply = appStrategy['should_apply'];
    const applyPriority = strField(appStrategy['application_priority']).toUpperCase();
    const successProb = strField(appStrategy['success_probability']).toUpperCase();

    // Deal breaker data
    const dealBreakersPass = dealBreakers['all_passed'];
    const visaStatus = asResumeRecord(dealBreakers['visa_sponsorship']);
    const locationReqs = asResumeRecord(dealBreakers['location_requirements']);
    const securityClearance = asResumeRecord(dealBreakers['security_clearance']);
    const hasDealBreakers = Object.keys(dealBreakers).length > 0;

    // Competitive positioning
    const percentile = competitive['estimated_candidate_pool_percentile'];
    const uvp = strField(competitive['unique_value_proposition']);
    const strengthsVsTypical = ensureArray(competitive['strengths_vs_typical_applicant']);
    const weaknessesVsTypical = ensureArray(competitive['weaknesses_vs_typical_applicant']);

    // Risk / concerns
    const employerConcerns = ensureArray(riskAssessment['red_flags_for_employer']);

    // AI insights
    const careerAdvice = strField(aiInsights['career_advice']);
    const altRoles = ensureArray(aiInsights['alternative_roles']);
    const skillsToBuild = ensureArray(aiInsights['skill_development_priority']);

    // Cert gaps
    const certA = asResumeRecord(qualAnalysis['certification_assessment']);
    const missingCerts = ensureArray(certA['missing_required']);

    // Helpers for label styling
    const priorityClass = (p: string): string => ({ HIGH: 'good', MEDIUM: 'review', LOW: 'muted', SKIP: 'poor' } as Record<string, string>)[p] ?? 'muted';
    const probClass = (p: string): string => ({ HIGH: 'good', MEDIUM: 'review', LOW: 'poor', VERY_LOW: 'poor' } as Record<string, string>)[p] ?? 'muted';
    const recLabel = (r: string): string => ({
        STRONG_MATCH: 'Strong Match', GOOD_MATCH: 'Good Match',
        MODERATE_MATCH: 'Moderate Match', WEAK_MATCH: 'Weak Match', NOT_RECOMMENDED: 'Not Recommended'
    } as Record<string, string>)[r] ?? r.replace(/_/g, ' ');

    // --- Section 1: Apply Decision Banner ---
    const hasApplyDecision = shouldApply !== undefined || applyPriority || successProb;
    const applyBannerClass = shouldApply === false ? 'poor' : (applyPriority === 'HIGH' ? 'good' : applyPriority === 'SKIP' ? 'poor' : 'review');
    const applyIcon = shouldApply === false ? 'fa-times-circle' : shouldApply === true ? 'fa-check-circle' : 'fa-question-circle';
    const applyText = shouldApply === false ? 'Do Not Apply' : shouldApply === true ? 'Apply to This Role' : 'Consider Applying';

    // --- Section 2: Deal Breaker summary ---
    const dbSummary = hasDealBreakers ? (() => {
        const items = [visaStatus, locationReqs, securityClearance].filter(Boolean);
        if (items.length === 0 && dealBreakersPass !== false) return '';
        return `
            <div class="content-section">
                <h2 class="section-title"><i class="fas fa-shield-alt"></i> Deal Breaker Check</h2>
                <div class="deal-breaker-status ${dealBreakersPass ? 'passed' : 'warning'}">
                    <i class="fas ${dealBreakersPass ? 'fa-check-circle' : 'fa-exclamation-triangle'}"></i>
                    <span>${dealBreakersPass ? 'All requirements met — no blockers found.' : 'Potential blockers detected — review before applying.'}</span>
                </div>
                ${items.length ? `<div class="deal-breaker-grid">
                    ${Object.keys(visaStatus).length ? dbCheckItemHtml('Visa Sponsorship', visaStatus) : ''}
                    ${Object.keys(locationReqs).length ? dbCheckItemHtml('Location', locationReqs) : ''}
                    ${Object.keys(securityClearance).length ? dbCheckItemHtml('Security Clearance', securityClearance) : ''}
                </div>` : ''}
            </div>`;
    })() : '';

    let fitHtml = `
        ${hasApplyDecision ? `
        <div class="apply-decision-banner apply-${applyBannerClass}">
            <div class="apply-main">
                <i class="fas ${applyIcon} apply-icon"></i>
                <div>
                    <div class="apply-answer">${applyText}</div>
                    ${recommendation ? `<div class="apply-rec">${recLabel(recommendation)}</div>` : ''}
                </div>
            </div>
            <div class="apply-badges">
                ${applyPriority ? `<span class="fit-badge badge-${priorityClass(applyPriority)}"><i class="fas fa-flag"></i> Priority: ${applyPriority.charAt(0) + applyPriority.slice(1).toLowerCase()}</span>` : ''}
                ${successProb ? `<span class="fit-badge badge-${probClass(successProb)}"><i class="fas fa-chart-line"></i> Success: ${successProb.replace('_', ' ').charAt(0) + successProb.replace('_', ' ').slice(1).toLowerCase()}</span>` : ''}
                ${confidenceLevel ? `<span class="fit-badge badge-muted"><i class="fas fa-brain"></i> Confidence: ${confidenceLevel.charAt(0) + confidenceLevel.slice(1).toLowerCase()}</span>` : ''}
            </div>
        </div>` : ''}

        ${dbSummary}

        <div class="content-section">
            <h2 class="section-title"><i class="fas fa-user-check"></i> Your Fit</h2>
            ${verdict ? `
            <div class="match-card">
                <div class="match-verdict">${escapeHtml(verdict)}</div>
                <div class="match-scores">
                    <div class="score-item"><div class="score-item-value">${toPercent(overallScore)}%</div><div class="score-item-label">Overall</div><div class="breakdown-desc">Weighted combination of all scores below</div></div>
                    <div class="score-item"><div class="score-item-value">${toPercent(qualScore)}%</div><div class="score-item-label">Qualifications</div><div class="breakdown-desc">Skills, experience &amp; education match</div></div>
                    <div class="score-item"><div class="score-item-value">${toPercent(prefScore)}%</div><div class="score-item-label">Preferences</div><div class="breakdown-desc">Salary, location &amp; work style fit</div></div>
                </div>
            </div>` : ''}

            ${(() => {
                const skillsA = asResumeRecord(qualAnalysis['skills_assessment']);
                const expA = asResumeRecord(qualAnalysis['experience_assessment']);
                const eduA = asResumeRecord(qualAnalysis['education_assessment']);
                if (skillsA['score'] === undefined && expA['score'] === undefined && eduA['score'] === undefined) return '';
                const skillGapNote = strField(skillsA['skill_gaps_analysis']);
                return `<div class="section-subtitle">Qualification Breakdown</div><div class="breakdown-grid">
                    ${breakdownScoreHtml('Skills', skillsA['score'], 'How well your listed skills match the required and preferred skills for this role')}
                    ${breakdownScoreHtml('Experience', expA['score'], 'Relevance and depth of your work history relative to what this role demands')}
                    ${breakdownScoreHtml('Education', eduA['score'], 'Degree level, field of study, and certification alignment with stated requirements')}
                </div>
                ${skillGapNote ? `<div class="skill-gap-note"><i class="fas fa-info-circle"></i> ${escapeHtml(skillGapNote)}</div>` : ''}
                ${missingCerts.length ? `<div class="section-subtitle" style="margin-top:0.75rem">Missing Certifications</div><ul class="content-list">${missingCerts.slice(0, 4).map((c) => `<li><i class="fas fa-certificate orange"></i><span>${escapeHtml(String(c))}</span></li>`).join('')}</ul>` : ''}`;
            })()}

            ${(() => {
                const salaryF = asResumeRecord(prefAnalysis['salary_fit']);
                const workF = asResumeRecord(prefAnalysis['work_arrangement_fit']);
                const sizeF = asResumeRecord(prefAnalysis['company_size_fit']);
                const locF = asResumeRecord(prefAnalysis['location_fit']);
                if (salaryF['score'] === undefined && workF['score'] === undefined && sizeF['score'] === undefined && locF['score'] === undefined) return '';
                const salaryUnknown = strField(salaryF['assessment']).toUpperCase() === 'UNKNOWN';
                const salaryBlock = salaryF['score'] !== undefined
                    ? `<div class="breakdown-item"><div class="breakdown-label">Salary</div>${salaryUnknown ? '<div class="breakdown-na">N/A — salary not listed in posting</div>' : `<div class="breakdown-bar-container"><div class="breakdown-bar-fill ${getBarClass(salaryF['score'])}" data-pct="${toPercent(salaryF['score'])}"></div></div><div class="breakdown-score">${toPercent(salaryF['score'])}%</div>`}<div class="breakdown-desc">Whether the offered compensation aligns with your desired salary range</div></div>`
                    : '';
                return `<div class="section-subtitle">Preference Fit</div><div class="breakdown-grid">
                    ${salaryBlock}
                    ${breakdownScoreHtml('Work Type', workF['score'], 'Remote, hybrid, or on-site arrangement vs. your stated preference')}
                    ${breakdownScoreHtml('Company Size', sizeF['score'], 'Startup vs. enterprise environment fit based on your preferred company scale')}
                    ${breakdownScoreHtml('Location', locF['score'], 'Geographic match — considers same city, metro-area proximity, and commute viability')}
                </div>`;
            })()}

            ${(percentile !== undefined || uvp) ? `
            <div class="section-subtitle">Competitive Position</div>
            <div class="competitive-card">
                ${percentile !== undefined ? `
                <div class="percentile-section">
                    <div class="percentile-header">
                        <span class="percentile-number">${percentile}<sup>th</sup></span>
                        <span class="percentile-label">percentile vs. typical applicants</span>
                    </div>
                    <div class="percentile-track"><div class="percentile-fill" data-pct="${Math.min(typeof percentile === 'number' ? percentile : Number(percentile) || 0, 100)}"></div><div class="percentile-marker" data-pct="${Math.min(typeof percentile === 'number' ? percentile : Number(percentile) || 0, 100)}"></div></div>
                    <div class="percentile-scale"><span>0</span><span>50</span><span>100</span></div>
                </div>` : ''}
                ${uvp ? `<div class="uvp-box"><div class="uvp-label"><i class="fas fa-fingerprint"></i> Your Unique Value</div><div class="uvp-text">${escapeHtml(uvp)}</div></div>` : ''}
                ${strengthsVsTypical.length ? `<div class="vs-typical"><div class="vs-label green"><i class="fas fa-arrow-up"></i> Edge over typical applicants</div><ul class="content-list">${strengthsVsTypical.slice(0, 3).map(s => `<li><i class="fas fa-check green"></i><span>${escapeHtml(String(s))}</span></li>`).join('')}</ul></div>` : ''}
                ${weaknessesVsTypical.length ? `<div class="vs-typical"><div class="vs-label orange"><i class="fas fa-arrow-down"></i> Where typical applicants have more</div><ul class="content-list">${weaknessesVsTypical.slice(0, 3).map(w => `<li><i class="fas fa-arrow-down orange"></i><span>${escapeHtml(String(w))}</span></li>`).join('')}</ul></div>` : ''}
            </div>` : ''}

            ${strengths.length ? `<div class="section-subtitle">Your Strengths</div><ul class="content-list">${strengths.slice(0, 5).map((rawS) => {
                const s = asResumeRecord(rawS);
                const label = strField(s['strength']) || String(rawS);
                const evidence = strField(s['evidence']);
                return `<li><i class="fas fa-star green"></i><span><strong>${escapeHtml(label)}</strong>${evidence ? ` — ${escapeHtml(evidence)}` : ''}</span></li>`;
            }).join('')}</ul>` : ''}
            ${gaps.length ? `<div class="section-subtitle">Areas to Address</div><ul class="content-list">${gaps.slice(0, 5).map((rawG) => {
                const g = asResumeRecord(rawG);
                const label = strField(g['gap']) || String(rawG);
                const mitigation = strField(g['mitigation_strategy']);
                return `<li><i class="fas fa-exclamation-triangle orange"></i><span><strong>${escapeHtml(label)}</strong>${mitigation ? `<div class="mitigation-tip"><i class="fas fa-lightbulb"></i> ${escapeHtml(mitigation)}</div>` : ''}</span></li>`;
            }).join('')}</ul>` : ''}

            ${employerConcerns.length ? `
            <div class="section-subtitle watch-out-title"><i class="fas fa-eye"></i> Potential Employer Concerns</div>
            <div class="watch-out-note">The hiring manager might raise these objections. Be ready to address them in your cover letter or interview.</div>
            <ul class="content-list warning-list">${employerConcerns.slice(0, 4).map(c => `<li><i class="fas fa-minus-circle amber"></i><span>${escapeHtml(String(c))}</span></li>`).join('')}</ul>` : ''}

            ${(careerAdvice || altRoles.length || skillsToBuild.length) ? `
            <div class="ai-insights-block">
                <div class="ai-insights-header"><i class="fas fa-robot"></i> AI Insights</div>
                ${careerAdvice ? `<div class="ai-career-advice">${escapeHtml(careerAdvice)}</div>` : ''}
                ${skillsToBuild.length ? `<div class="ai-sub-label">Skills to Build</div><div class="tags-grid">${skillsToBuild.slice(0, 6).map(s => `<span class="tag skill-build">${escapeHtml(String(s))}</span>`).join('')}</div>` : ''}
                ${altRoles.length ? `<div class="ai-sub-label">You Also Fit</div><div class="tags-grid">${altRoles.slice(0, 5).map(r => `<span class="tag alt-role">${escapeHtml(String(r))}</span>`).join('')}</div>` : ''}
            </div>` : ''}
        </div>`;

    const fcEl = document.getElementById('fitContent');
    if (fcEl) {
        fcEl.innerHTML = fitHtml;
        fcEl.querySelectorAll('.breakdown-bar-fill[data-pct], .percentile-fill[data-pct]').forEach((el) => {
            const h = el as HTMLElement;
            const p = h.dataset['pct'];
            if (p !== undefined) h.style.width = p + '%';
        });
        const marker = fcEl.querySelector('.percentile-marker[data-pct]') as HTMLElement | null;
        if (marker) marker.style.left = marker.dataset['pct'] + '%';
    }

    // ========== SUB-PANE 3: STRATEGY ==========
    let strategyHtml = '';

    // Application Strategy fields
    const talkingPoints = ensureArray(appStrategy['key_talking_points']);
    const coverLetterAngle = strField(appStrategy['cover_letter_angle']);
    const addressConcerns = ensureArray(appStrategy['address_these_concerns']);
    const resumeTips = ensureArray(appStrategy['resume_optimization_tips']);
    const interviewPrep = ensureArray(appStrategy['interview_preparation']);
    const networkingSuggestions = strField(appStrategy['networking_suggestions']);

    // Risk Assessment — correct field names from the agent schema
    const candidateRisks = ensureArray(riskAssessment['candidate_risks']);
    const roleRisks = ensureArray(riskAssessment['role_risks']);
    const yellowFlagsForCandidate = ensureArray(riskAssessment['yellow_flags_for_candidate']);

    // ── Section 1: Your Action Plan ────────────────────────────
    if (talkingPoints.length || coverLetterAngle) {
        strategyHtml += `
            <div class="content-section">
                <h2 class="section-title"><i class="fas fa-bullseye"></i> Your Action Plan</h2>
                ${talkingPoints.length ? `
                <div class="section-subtitle">Key Talking Points</div>
                <div class="talking-points-grid">
                    ${talkingPoints.slice(0, 5).map((p, i) => `
                    <div class="talking-point-card">
                        <div class="tp-number">${i + 1}</div>
                        <div class="tp-text">${escapeHtml(String(p))}</div>
                    </div>`).join('')}
                </div>` : ''}
                ${coverLetterAngle ? `
                <div class="section-subtitle">Cover Letter Angle</div>
                <div class="cover-angle-box">
                    <div class="cover-angle-label"><i class="fas fa-pen-fancy"></i> The Story to Tell</div>
                    <div class="cover-angle-text">${escapeHtml(coverLetterAngle)}</div>
                </div>` : ''}
            </div>`;
    }

    // ── Section 2: Resume Optimization ─────────────────────────
    if (resumeTips.length) {
        strategyHtml += `
            <div class="content-section">
                <h2 class="section-title"><i class="fas fa-file-edit"></i> Resume Optimization</h2>
                <p class="section-intro">Specific changes to make to your resume before applying to this role.</p>
                <ol class="resume-tips-list">
                    ${resumeTips.slice(0, 6).map(t => `<li><span>${escapeHtml(String(t))}</span></li>`).join('')}
                </ol>
            </div>`;
    }

    // ── Section 3: Address These Concerns ──────────────────────
    if (addressConcerns.length) {
        strategyHtml += `
            <div class="content-section">
                <h2 class="section-title"><i class="fas fa-shield-alt"></i> Address These Concerns</h2>
                <p class="section-intro">Objections the employer is likely to have — and how to get ahead of them.</p>
                <div class="concerns-list">
                    ${addressConcerns.slice(0, 4).map((rawC) => {
                        const c = asResumeRecord(rawC);
                        const concern = strField(c['concern'] ?? c['issue']) || String(rawC);
                        const how = strField(c['how_to_address']);
                        return `<div class="concern-card">
                            <div class="concern-problem"><i class="fas fa-exclamation-circle orange"></i> <strong>${escapeHtml(concern)}</strong></div>
                            ${how ? `<div class="concern-solution"><i class="fas fa-arrow-right"></i> ${escapeHtml(how)}</div>` : ''}
                        </div>`;
                    }).join('')}
                </div>
            </div>`;
    }

    // ── Section 4: Interview Preparation ───────────────────────
    if (interviewPrep.length) {
        strategyHtml += `
            <div class="content-section">
                <h2 class="section-title"><i class="fas fa-comments"></i> Likely Interview Questions</h2>
                <p class="section-intro">Questions to expect based on your profile gaps and this company's priorities.</p>
                <div class="interview-prep-list">
                    ${interviewPrep.slice(0, 5).map((rawQ) => {
                        const q = asResumeRecord(rawQ);
                        const question = strField(q['likely_question']) || String(rawQ);
                        const strategy = strField(q['suggested_answer_strategy']);
                        return `<div class="prep-card">
                            <div class="prep-question"><i class="fas fa-question-circle"></i> ${escapeHtml(question)}</div>
                            ${strategy ? `<div class="prep-strategy"><i class="fas fa-lightbulb"></i> ${escapeHtml(strategy)}</div>` : ''}
                        </div>`;
                    }).join('')}
                </div>
            </div>`;
    }

    // ── Section 5: Networking ───────────────────────────────────
    if (networkingSuggestions) {
        strategyHtml += `
            <div class="content-section">
                <h2 class="section-title"><i class="fas fa-network-wired"></i> Networking In</h2>
                <div class="networking-box">
                    <i class="fas fa-users"></i>
                    <p>${escapeHtml(networkingSuggestions)}</p>
                </div>
            </div>`;
    }

    // ── Section 6: Risk Assessment ──────────────────────────────
    if (candidateRisks.length || roleRisks.length || yellowFlagsForCandidate.length) {
        strategyHtml += `
            <div class="content-section">
                <h2 class="section-title"><i class="fas fa-shield-halved"></i> Risk Assessment</h2>
                ${candidateRisks.length ? `
                <div class="section-subtitle">Employer Concerns</div>
                <div class="risk-list">
                    ${candidateRisks.slice(0, 4).map((rawR) => {
                        const r = asResumeRecord(rawR);
                        const risk = strField(r['risk']) || String(rawR);
                        const mit = strField(r['mitigation']);
                        return `<div class="risk-card employer-risk">
                            <div class="risk-label"><i class="fas fa-user-tie orange"></i> Employer concern</div>
                            <div class="risk-text">${escapeHtml(risk)}</div>
                            ${mit ? `<div class="risk-mitigation"><i class="fas fa-tools"></i> ${escapeHtml(mit)}</div>` : ''}
                        </div>`;
                    }).join('')}
                </div>` : ''}
                ${roleRisks.length ? `
                <div class="section-subtitle" style="margin-top:1rem">Risks for You</div>
                <div class="risk-list">
                    ${roleRisks.slice(0, 3).map((rawR) => {
                        const r = asResumeRecord(rawR);
                        const risk = strField(r['risk']) || String(rawR);
                        const consideration = strField(r['consideration']);
                        return `<div class="risk-card role-risk">
                            <div class="risk-label"><i class="fas fa-user orange"></i> Consider this</div>
                            <div class="risk-text">${escapeHtml(risk)}</div>
                            ${consideration ? `<div class="risk-mitigation"><i class="fas fa-lightbulb"></i> ${escapeHtml(consideration)}</div>` : ''}
                        </div>`;
                    }).join('')}
                </div>` : ''}
                ${yellowFlagsForCandidate.length ? `
                <div class="section-subtitle" style="margin-top:1rem">Things to Investigate</div>
                <div class="investigate-list">${yellowFlagsForCandidate.slice(0, 4).map(f => `<div class="investigate-item"><i class="fas fa-search"></i><span>${escapeHtml(String(f))}</span></div>`).join('')}</div>` : ''}
            </div>`;
    }

    if (!strategyHtml) {
        strategyHtml = '<div class="empty-state"><i class="fas fa-bullseye"></i><p>Strategy information not available.</p></div>';
    }
    const scEl = document.getElementById('strategyContent');
    if (scEl) scEl.innerHTML = strategyHtml;

    // ========== SUB-PANE 4: JOB DETAILS ==========
    const benefits = ensureArray(job.benefits);
    const deadline = job.application_deadline;
    const postedDate = formatPostedDate(job.posted_date);
    const yearsRequired = job.years_experience_required;
    const educationReqs = job.education_requirements;
    const teamInfo = job.team_info;
    const reportingTo = job.reporting_to;
    const visaSponsorship = job.visa_sponsorship;
    const securityRequired = job.security_clearance;
    const contactInfo = job.contact_information;
    const languageReqs = ensureArray(job.language_requirements);
    const roleClass = job.role_classification;
    const workArrangement = job.work_arrangement;
    const employmentType = job.employment_type;
    const industry = job.industry;
    const travelPref = (() => {
        const raw = job.max_travel_preference;
        if (!raw && raw !== 0) return '';
        const str = String(raw).trim();
        // Bare number → append %; already has % or is descriptive → keep as-is
        return /^\d+$/.test(str) ? `${str}%` : str;
    })();
    const _jdExtraLocations = Array.isArray(job.additional_locations) ? job.additional_locations.filter(Boolean) : [];
    const _jdPrimaryLocation = [job.job_city, job.job_state, job.job_country].filter(Boolean).join(', ');
    const jobLocation = [_jdPrimaryLocation, ..._jdExtraLocations].filter(Boolean).join(' | ');

    // Salary display (reuse already-computed header value or rebuild)
    const _currencySymbols: Record<string, string> = { USD: '$', EUR: '€', GBP: '£', CAD: 'CA$', AUD: 'AU$', NZD: 'NZ$', CHF: 'CHF ', JPY: '¥', CNY: '¥', INR: '₹', BRL: 'R$', MXN: 'MX$', SGD: 'S$', HKD: 'HK$', SEK: 'kr', NOK: 'kr', DKK: 'kr' };
    const _currSymbol = (code: string) => _currencySymbols[(code || '').toUpperCase()] ?? (code ? code + '\u00a0' : '$');
    let jdSalaryDisplay = '';
    const salaryRange = asResumeRecord(job.salary_range);
    if (job.salary_range && typeof job.salary_range === 'object') {
        const min = typeof salaryRange['min'] === 'number' ? salaryRange['min'] : 0;
        const max = typeof salaryRange['max'] === 'number' ? salaryRange['max'] : 0;
        if (min || max) {
            const curr = _currSymbol(strField(salaryRange['currency']));
            const mn = min ? `${curr}${(min / 1000).toFixed(0)}K` : '';
            const mx = max ? `${curr}${(max / 1000).toFixed(0)}K` : '';
            jdSalaryDisplay = mn && mx ? `${mn} – ${mx}` : mn || mx;
        }
    } else if (typeof job.salary_range === 'string' && job.salary_range) {
        jdSalaryDisplay = job.salary_range;
    }

    // Visa: normalize boolean / string into readable text
    const visaText = (() => {
        if (visaSponsorship === null || visaSponsorship === undefined || visaSponsorship === '') return '';
        if (typeof visaSponsorship === 'boolean') return visaSponsorship ? 'Sponsorship available' : 'No sponsorship';
        const v = String(visaSponsorship).toLowerCase();
        if (v === 'true' || v === 'yes' || v === 'available') return 'Sponsorship available';
        if (v === 'false' || v === 'no' || v === 'not available') return 'No sponsorship';
        return escapeHtml(String(visaSponsorship));
    })();

    // Split skills: required_skills for the main skills section; ats_keywords separately
    const requiredSkillsArr = ensureArray(job.required_skills).map(skillLabel).filter(Boolean);
    const atsKeywordsArr = ensureArray(job.ats_keywords).map(skillLabel).filter(Boolean);

    let jobDetailsHtml = '';

    // ── Section 1: At a Glance ──────────────────────────────────
    const hasGlance = jobLocation || workArrangement || jdSalaryDisplay || employmentType ||
        yearsRequired || educationReqs || industry || roleClass || visaText ||
        securityRequired || travelPref || postedDate || deadline;

    if (hasGlance) {
        const educLabel = (() => {
            if (!educationReqs) return '';
            if (typeof educationReqs === 'object' && educationReqs !== null) {
                const edu = asResumeRecord(educationReqs);
                if (edu['required'] === false) return '';
                const deg = strField(edu['degree']).trim();
                const field = strField(edu['field']).trim();
                if (!deg && !field) return 'Not specified';
                return escapeHtml(`${deg}${field ? ` in ${field}` : ''}`).trim();
            }
            const s = String(educationReqs).trim().toLowerCase();
            if (s === 'required' || s === 'true' || s === 'yes') return 'Not specified';
            return escapeHtml(String(educationReqs));
        })();

        jobDetailsHtml += `
            <div class="content-section">
                <h2 class="section-title"><i class="fas fa-briefcase"></i> At a Glance</h2>
                <div class="jd-glance-grid">
                    ${jobLocation ? `<div class="jd-glance-item"><div class="jd-glance-icon"><i class="fas fa-map-marker-alt"></i></div><div class="jd-glance-body"><div class="jd-glance-label">Location</div><div class="jd-glance-value">${escapeHtml(jobLocation)}</div></div></div>` : ''}
                    ${workArrangement ? `<div class="jd-glance-item"><div class="jd-glance-icon"><i class="fas fa-laptop-house"></i></div><div class="jd-glance-body"><div class="jd-glance-label">Work Style</div><div class="jd-glance-value">${escapeHtml(toTitleCase(strField(workArrangement)))}</div></div></div>` : ''}
                    ${jdSalaryDisplay ? `<div class="jd-glance-item"><div class="jd-glance-icon"><i class="fas fa-dollar-sign"></i></div><div class="jd-glance-body"><div class="jd-glance-label">Salary</div><div class="jd-glance-value">${escapeHtml(jdSalaryDisplay)}</div></div></div>` : ''}
                    ${employmentType ? `<div class="jd-glance-item"><div class="jd-glance-icon"><i class="fas fa-clock"></i></div><div class="jd-glance-body"><div class="jd-glance-label">Employment</div><div class="jd-glance-value">${escapeHtml(toTitleCase(strField(employmentType)))}</div></div></div>` : ''}
                    ${yearsRequired ? `<div class="jd-glance-item"><div class="jd-glance-icon"><i class="fas fa-hourglass-half"></i></div><div class="jd-glance-body"><div class="jd-glance-label">Experience</div><div class="jd-glance-value">${escapeHtml(String(yearsRequired))}+ years</div></div></div>` : ''}
                    ${educLabel ? `<div class="jd-glance-item"><div class="jd-glance-icon"><i class="fas fa-graduation-cap"></i></div><div class="jd-glance-body"><div class="jd-glance-label">Education</div><div class="jd-glance-value">${educLabel}</div></div></div>` : ''}
                    ${industry ? `<div class="jd-glance-item"><div class="jd-glance-icon"><i class="fas fa-industry"></i></div><div class="jd-glance-body"><div class="jd-glance-label">Industry</div><div class="jd-glance-value">${escapeHtml(strField(industry))}</div></div></div>` : ''}
                    ${roleClass ? `<div class="jd-glance-item"><div class="jd-glance-icon"><i class="fas fa-sitemap"></i></div><div class="jd-glance-body"><div class="jd-glance-label">Role Type</div><div class="jd-glance-value">${escapeHtml(strField(roleClass))}</div></div></div>` : ''}
                    ${visaText ? `<div class="jd-glance-item"><div class="jd-glance-icon"><i class="fas fa-passport"></i></div><div class="jd-glance-body"><div class="jd-glance-label">Visa</div><div class="jd-glance-value">${visaText}</div></div></div>` : ''}
                    ${securityRequired ? `<div class="jd-glance-item"><div class="jd-glance-icon"><i class="fas fa-shield-alt"></i></div><div class="jd-glance-body"><div class="jd-glance-label">Clearance</div><div class="jd-glance-value">${escapeHtml(String(securityRequired))}</div></div></div>` : ''}
                    ${travelPref ? `<div class="jd-glance-item"><div class="jd-glance-icon"><i class="fas fa-plane"></i></div><div class="jd-glance-body"><div class="jd-glance-label">Travel</div><div class="jd-glance-value">${escapeHtml(travelPref)}</div></div></div>` : ''}
                    ${postedDate ? `<div class="jd-glance-item"><div class="jd-glance-icon"><i class="fas fa-calendar-plus"></i></div><div class="jd-glance-body"><div class="jd-glance-label">Posted</div><div class="jd-glance-value">${escapeHtml(postedDate)}</div></div></div>` : ''}
                    ${deadline ? `<div class="jd-glance-item jd-glance-deadline"><div class="jd-glance-icon"><i class="fas fa-calendar-times"></i></div><div class="jd-glance-body"><div class="jd-glance-label">Apply By</div><div class="jd-glance-value">${escapeHtml(String(deadline))}</div></div></div>` : ''}
                </div>
            </div>`;
    }

    // ── Section 2: Team Context ─────────────────────────────────
    if (teamInfo || reportingTo) {
        jobDetailsHtml += `
            <div class="content-section">
                <h2 class="section-title"><i class="fas fa-users"></i> Team Context</h2>
                ${teamInfo ? `<div class="team-context-box"><p>${escapeHtml(strField(teamInfo))}</p></div>` : ''}
                ${reportingTo ? `<div class="reports-to-row"><i class="fas fa-level-up-alt"></i><span><strong>Reports to:</strong> ${escapeHtml(strField(reportingTo))}</span></div>` : ''}
            </div>`;
    }

    // ── Section 3: What You'll Do ───────────────────────────────
    if (responsibilities.length) {
        jobDetailsHtml += `
            <div class="content-section">
                <h2 class="section-title"><i class="fas fa-tasks"></i> What You'll Do</h2>
                <ul class="content-list resp-list">
                    ${responsibilities.map((r) => {
                        const rec = asResumeRecord(r);
                        const line = typeof r === 'string' ? r : strField(rec['text'] ?? rec['duty'] ?? rec['responsibility']);
                        return `<li><i class="fas fa-arrow-right"></i><span>${escapeHtml(line)}</span></li>`;
                    }).join('')}
                </ul>
            </div>`;
    }

    // ── Section 4: Requirements ─────────────────────────────────
    if (qualifications.length) {
        jobDetailsHtml += `
            <div class="content-section">
                <h2 class="section-title"><i class="fas fa-check-double"></i> Requirements</h2>
                <p class="section-intro">Must-haves — you need these to be considered.</p>
                <ul class="content-list">
                    ${qualifications.map(q => `<li><i class="fas fa-check green"></i><span>${escapeHtml(String((typeof q === 'object' && q !== null ? strField(asResumeRecord(q)['qualification'] ?? asResumeRecord(q)['requirement']) : String(q))))}</span></li>`).join('')}
                </ul>
            </div>`;
    }

    // ── Section 5: Nice to Have ─────────────────────────────────
    if (preferredQuals.length) {
        jobDetailsHtml += `
            <div class="content-section">
                <h2 class="section-title"><i class="fas fa-star"></i> Nice to Have</h2>
                <p class="section-intro">Preferred qualifications — strong candidates will have some of these.</p>
                <ul class="content-list">
                    ${preferredQuals.map(q => `<li><i class="fas fa-plus-circle orange"></i><span>${escapeHtml(String((typeof q === 'object' && q !== null ? strField(asResumeRecord(q)['qualification'] ?? asResumeRecord(q)['requirement']) : String(q))))}</span></li>`).join('')}
                </ul>
            </div>`;
    }

    // ── Section 6: Skills & Technologies ───────────────────────
    if (requiredSkillsArr.length) {
        jobDetailsHtml += `
            <div class="content-section">
                <h2 class="section-title"><i class="fas fa-code"></i> Skills &amp; Technologies</h2>
                <div class="tags-grid">${requiredSkillsArr.map(s => `<span class="tag">${escapeHtml(s)}</span>`).join('')}</div>
            </div>`;
    }

    // ── Section 7: ATS Keywords ─────────────────────────────────
    if (atsKeywordsArr.length) {
        jobDetailsHtml += `
            <div class="content-section">
                <h2 class="section-title"><i class="fas fa-key"></i> ATS Keywords</h2>
                <p class="section-intro">Mirror these exact words in your resume and cover letter — applicant tracking systems scan for them.</p>
                <div class="tags-grid ats-grid">${atsKeywordsArr.map(s => `<span class="tag ats-keyword">${escapeHtml(s)}</span>`).join('')}</div>
            </div>`;
    }

    // ── Section 8: Soft Skills ──────────────────────────────────
    if (softSkills.length) {
        jobDetailsHtml += `
            <div class="content-section">
                <h2 class="section-title"><i class="fas fa-handshake"></i> Soft Skills</h2>
                <div class="tags-grid">${softSkills.map(s => `<span class="tag soft">${escapeHtml(String(s))}</span>`).join('')}</div>
            </div>`;
    }

    // ── Section 9: Language Requirements ───────────────────────
    if (languageReqs.length) {
        jobDetailsHtml += `
            <div class="content-section">
                <h2 class="section-title"><i class="fas fa-language"></i> Language Requirements</h2>
                <div class="tags-grid">${languageReqs.map(l => `<span class="tag">${escapeHtml(String((typeof l === 'object' && l !== null ? `${strField(asResumeRecord(l)['language'] ?? asResumeRecord(l)['name'])}${strField(asResumeRecord(l)['proficiency']) ? ` (${strField(asResumeRecord(l)['proficiency'])})` : ''}` : String(l))))}</span>`).join('')}</div>
            </div>`;
    }

    // ── Section 10: Benefits & Perks ────────────────────────────
    if (benefits.length) {
        jobDetailsHtml += `
            <div class="content-section">
                <h2 class="section-title"><i class="fas fa-gift"></i> Benefits &amp; Perks</h2>
                <div class="tags-grid">${benefits.map(b => `<span class="tag benefit">${escapeHtml(String(b))}</span>`).join('')}</div>
            </div>`;
    }

    // ── Section 11: Contact / Apply ─────────────────────────────
    if (contactInfo) {
        jobDetailsHtml += `
            <div class="content-section">
                <h2 class="section-title"><i class="fas fa-envelope"></i> Contact</h2>
                <div class="contact-info"><i class="fas fa-envelope"></i><span>${escapeHtml(String(contactInfo))}</span></div>
            </div>`;
    }

    if (!jobDetailsHtml) {
        jobDetailsHtml = '<div class="empty-state"><i class="fas fa-briefcase"></i><p>Job details not available.</p></div>';
    }
    const jdEl = document.getElementById('jobDetailsContent');
    if (jdEl) jdEl.innerHTML = jobDetailsHtml;
}

