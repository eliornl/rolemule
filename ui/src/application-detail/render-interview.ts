import { escapeHtml } from '../shared/dom-security';
import { asResumeRecord, strField } from './render-resume-helpers';
import { getCurrentSessionId } from './state';
import type { CompanyResearch, InterviewPrep, JobAnalysis } from './types';
import { ensureArray } from './utils';

export function renderInterviewPrep(company: CompanyResearch, _job?: JobAnalysis) {
    const prep = company.interview_preparation;
    if (prep && !prep.parse_error) {
        renderRichInterviewPrep(prep);
        return;
    }

    // Fall back to basic company research data
    const intel = asResumeRecord(company.interview_intelligence);
    const interviewProcess = ensureArray(company.typical_interview_process);
    const commonQuestions = ensureArray(company.common_questions ?? intel['common_questions']);
    const tips = ensureArray(
        company.preparation_tips ?? company.talking_points_for_interview ?? intel['tips_for_success'],
    );
    const assessmentMethods = ensureArray(company.assessment_methods ?? intel['assessment_methods']);
    const interviewFormat = company.interview_format ?? intel['interview_format'];
    const timeline = company.hiring_timeline ?? intel['timeline'];
    const whatTheyLookFor = ensureArray(intel['what_they_look_for']);
    const questionsToAsk = ensureArray(company.questions_to_ask_them);

    const hasBasicData = interviewProcess.length || commonQuestions.length || tips.length;

    if (!hasBasicData) {
        // Hide sub-tabs, show empty state in first sub-pane
        const subTabsEl = document.querySelector('.sub-tabs[data-parent="interview"]') as HTMLElement | null;
        if (subTabsEl) subTabsEl.style.display = 'none';
        document.querySelectorAll('#pane-interview .sub-pane').forEach(p => p.classList.remove('active'));
        const processPane = document.getElementById('sub-interview-process');
        if (processPane) {
            processPane.classList.add('active');
            processPane.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-chalkboard-teacher empty-state-icon"></i>
                    <p class="empty-state-title">Interview Preparation</p>
                    <p class="empty-state-desc">Generate personalized interview prep including likely questions, stage-by-stage guidance, and strategies tailored to your profile.</p>
                    <button class="regen-btn" data-action="gen-interview" aria-label="Generate interview prep">
                        <span class="spinner"></span>
                        <span class="btn-text">Generate Interview Prep</span>
                    </button>
                </div>`;
        }
        const irbEl = document.getElementById('interviewRegenBtn');
        if (irbEl) irbEl.innerHTML = '';
        return;
    }

    // Ensure sub-tabs are visible
    const subTabsBar = document.querySelector('.sub-tabs[data-parent="interview"]') as HTMLElement | null;
    if (subTabsBar) subTabsBar.style.display = '';

    // Process sub-pane — banner first, then basic content
    const basicNoticeBanner = getCurrentSessionId() ? `
        <div class="iv-basic-notice">
            <div class="iv-basic-notice-body">
                <i class="fas fa-info-circle"></i>
                <div>
                    <div class="iv-basic-notice-title">This is basic info from the job posting</div>
                    <div class="iv-basic-notice-desc">Generate AI-powered prep for predicted questions with STAR story guidance, personalized answer strategies, a day-before checklist, and more — all tailored to your profile.</div>
                </div>
            </div>
            <button class="regen-btn" data-action="gen-interview" aria-label="Generate full interview prep" style="flex-shrink:0">
                <span class="spinner"></span>
                <span class="btn-text"><i class="fas fa-magic"></i> Generate Full Prep</span>
            </button>
        </div>` : '';

    let processHtml = basicNoticeBanner;
    if (timeline || interviewFormat) {
        processHtml += `<div class="interview-overview">`;
        if (timeline)       processHtml += `<div class="overview-item"><i class="fas fa-clock"></i><span><strong>Timeline:</strong> ${escapeHtml(String(timeline))}</span></div>`;
        if (interviewFormat) processHtml += `<div class="overview-item"><i class="fas fa-video"></i><span><strong>Format:</strong> ${escapeHtml(String(interviewFormat))}</span></div>`;
        processHtml += `</div>`;
    }
    if (interviewProcess.length) {
        processHtml += `<div class="section-subtitle">Interview Process</div><div class="process-steps">`;
        processHtml += interviewProcess.slice(0, 5).map((step) => `<div class="process-step"><span class="step-text">${escapeHtml(String(step))}</span></div>`).join('');
        processHtml += `</div>`;
    }
    if (assessmentMethods.length) {
        processHtml += `<div class="section-subtitle">What to Expect</div><div class="assessment-badges">`;
        processHtml += assessmentMethods.slice(0, 5).map(a => `<span class="assessment-badge"><i class="fas fa-clipboard-check"></i>${escapeHtml(String(a))}</span>`).join('');
        processHtml += `</div>`;
    }
    if (whatTheyLookFor.length) {
        processHtml += `<div class="section-subtitle">What They Look For</div><div class="tags-grid">`;
        processHtml += whatTheyLookFor.slice(0, 6).map(w => `<span class="tag lookfor">${escapeHtml(String(w))}</span>`).join('');
        processHtml += `</div>`;
    }
    if (!processHtml) processHtml = '<div class="empty-state"><i class="fas fa-route"></i><p>No process information available.</p></div>';
    const sipEl = document.getElementById('sub-interview-process');
    if (sipEl) sipEl.innerHTML = processHtml;

    // Questions sub-pane
    let questionsHtml = '';
    if (commonQuestions.length) {
        questionsHtml += `<div class="section-subtitle">Likely Questions</div><ul class="questions-list">`;
        questionsHtml += commonQuestions.slice(0, 5).map(q => `<li><i class="fas fa-question-circle"></i><span>${escapeHtml(String(q))}</span></li>`).join('');
        questionsHtml += `</ul>`;
    }
    if (questionsToAsk.length) {
        questionsHtml += `<div class="section-subtitle">Questions to Ask Them</div><ul class="ask-questions-list">`;
        questionsHtml += questionsToAsk.slice(0, 4).map(q => `<li><i class="fas fa-hand-point-right green"></i><span>${escapeHtml(String(q))}</span></li>`).join('');
        questionsHtml += `</ul>`;
    }
    if (!questionsHtml) questionsHtml = '<div class="empty-state"><i class="fas fa-question-circle"></i><p>No questions available.</p></div>';
    const siqEl = document.getElementById('sub-interview-questions');
    if (siqEl) siqEl.innerHTML = questionsHtml;

    // Preparation sub-pane
    let prepHtml = '';
    if (tips.length) {
        prepHtml += `<div class="section-subtitle">Preparation Tips</div>`;
        prepHtml += tips.slice(0, 4).map(t => `<div class="quick-win"><div class="quick-win-icon"><i class="fas fa-lightbulb"></i></div><div class="quick-win-text">${escapeHtml(String(t))}</div></div>`).join('');
    }
    if (!prepHtml) prepHtml = '<div class="empty-state"><i class="fas fa-tasks"></i><p>No preparation tips available.</p></div>';
    const sippEl = document.getElementById('sub-interview-preparation');
    if (sippEl) sippEl.innerHTML = prepHtml;

    // No bottom button — the generate prompt is already at the top of the Process pane
    const irgEl = document.getElementById('interviewRegenBtn');
    if (irgEl) irgEl.innerHTML = '';
}

export function renderRichInterviewPrep(prep: InterviewPrep): void {
    // Ensure sub-tabs are visible
    const subTabsBar = document.querySelector('.sub-tabs[data-parent="interview"]') as HTMLElement | null;
    if (subTabsBar) subTabsBar.style.display = '';

    // ── Schema detection: support both new (v2) and old (v1) schemas ──
    // New schema: prep.interview_process, prep.predicted_questions, etc.
    // Old schema: prep.interview_stages, prep.likely_questions, etc.
    const isNewSchema = !!(prep.interview_process || prep.predicted_questions || prep.questions_for_them);

    const iProcess = asResumeRecord(prep.interview_process);
    const predicted = asResumeRecord(prep.predicted_questions);
    const qForThem = asResumeRecord(prep.questions_for_them);
    const concerns = ensureArray(prep.addressing_concerns);
    const qrc = asResumeRecord(prep.quick_reference_card);
    const logistics = asResumeRecord(prep.logistics);
    // day_before_checklist (new) → preparation_checklist (old) → day_of_tips (old)
    const dayBefore  = ensureArray(prep.day_before_checklist || prep.preparation_checklist || prep.day_of_tips);
    const boostrs    = ensureArray(prep.confidence_boosters);

    // New schema rounds; fall back to old interview_stages
    const rounds = ensureArray(iProcess['typical_rounds'] ?? prep.interview_stages);

    // New predicted_questions buckets; for old schema, bucket by category field
    const oldQuestions   = ensureArray(prep.likely_questions);
    const oldByCategory = (cat: string): unknown[] =>
        oldQuestions.filter((q) => {
            const rec = asResumeRecord(q);
            return strField(rec['category']).toLowerCase() === cat.toLowerCase();
        });

    const behaviorals    = ensureArray(predicted['behavioral'])    .length ? ensureArray(predicted['behavioral'])    : oldByCategory('behavioral');
    const technicals     = ensureArray(predicted['technical'])     .length ? ensureArray(predicted['technical'])     : oldByCategory('technical');
    const roleSpecific   = ensureArray(predicted['role_specific']) .length ? ensureArray(predicted['role_specific']) : oldByCategory('role-specific');
    const companySpecific= ensureArray(predicted['company_specific']).length ? ensureArray(predicted['company_specific']) : oldByCategory('company-specific');
    // Any old questions not matched by category (situational, general, etc.)
    const otherOldQs = isNewSchema
        ? []
        : oldQuestions.filter((q) => {
            const rec = asResumeRecord(q);
            const c = strField(rec['category']).toLowerCase();
            return !['behavioral', 'technical', 'role-specific', 'company-specific'].includes(c);
        });

    // ── Category badge helper ───────────────────────────────────
    const catBadge = (cat: string): string => {
        const colors: Record<string, string> = {
            behavioral: '#667eea', technical: '#f093fb',
            'role-specific': '#4facfe', 'company-specific': '#43e97b', situational: '#fda085',
        };
        const c = escapeHtml(colors[cat.toLowerCase()] ?? '#8b8fa8');
        return `<span class="iv-cat-badge" style="background:${c}22;color:${c}">${escapeHtml(cat.toUpperCase())}</span>`;
    };

    // ===== SUB-PANE 1: PROCESS ==============================================
    let processHtml = '';

    // Overview bar — new fields fall back to old-schema equivalents
    const totalTimeline = strField(iProcess['total_timeline'] ?? prep.hiring_timeline);
    const prepTime = strField(iProcess['preparation_time_needed']);
    const formatPred = strField(iProcess['format_prediction'] ?? prep.interview_format);
    if (totalTimeline || prepTime || formatPred) {
        processHtml += `<div class="interview-overview">
            ${totalTimeline ? `<div class="overview-item"><i class="fas fa-clock"></i><span><strong>Timeline to offer:</strong> ${escapeHtml(totalTimeline)}</span></div>` : ''}
            ${prepTime ? `<div class="overview-item"><i class="fas fa-book-open"></i><span><strong>Prep time needed:</strong> ${escapeHtml(prepTime)}</span></div>` : ''}
            ${formatPred ? `<div class="overview-item"><i class="fas fa-video"></i><span><strong>Format:</strong> ${escapeHtml(formatPred)}</span></div>` : ''}
        </div>`;
    }

    // Interview rounds
    if (rounds.length) {
        processHtml += `<h3 class="section-subtitle"><i class="fas fa-route"></i> Interview Stages</h3>
        <div class="iv-rounds-list">`;
        processHtml += rounds.map((rawRound, i) => {
            const r = asResumeRecord(rawRound);
            return `
            <div class="iv-round-card">
                <div class="iv-round-header">
                    <div class="iv-round-num">${i + 1}</div>
                    <div class="iv-round-meta">
                        <div class="iv-round-type">${escapeHtml(String(r['type'] ?? r['stage'] ?? `Round ${i + 1}`))}</div>
                        <div class="iv-round-details">
                            ${r['duration'] ? `<span><i class="fas fa-clock"></i> ${escapeHtml(String(r['duration']))}</span>` : ''}
                            ${r['with'] ? `<span><i class="fas fa-user"></i> ${escapeHtml(String(r['with']))}</span>` : ''}
                        </div>
                    </div>
                </div>
                ${(r['focus'] || r['description']) ? `<div class="iv-round-focus"><strong>Focus:</strong> ${escapeHtml(String(r['focus'] ?? r['description']))}</div>` : ''}
                ${r['tips'] ? `<div class="iv-round-tip"><i class="fas fa-lightbulb"></i> ${Array.isArray(r['tips']) ? ensureArray(r['tips']).map((t) => escapeHtml(String(t))).join(' · ') : escapeHtml(String(r['tips']))}</div>` : ''}
            </div>`;
        }).join('');
        processHtml += `</div>`;
    }

    if (!processHtml) processHtml = '<div class="empty-state"><i class="fas fa-route"></i><p>No process information available.</p></div>';
    const richSipEl = document.getElementById('sub-interview-process');
    if (richSipEl) richSipEl.innerHTML = processHtml;

    // ===== SUB-PANE 2: QUESTIONS ============================================
    let questionsHtml = '';

    const renderQuestionCard = (rawQ: unknown, badgeCat: string): string => {
        const q = asResumeRecord(rawQ);
        const whyText = strField(q['why_likely'] ?? q['why_they_ask']);
        const approach = strField(
            q['preparation_approach'] ?? q['answer_strategy'] ?? q['personalized_answer'] ?? q['suggested_approach'],
        );
        const story = asResumeRecord(q['your_story']);
        const keyPts = ensureArray(q['key_points_to_cover']);
        const followUps = ensureArray(q['follow_up_questions']);
        const incorpExp = strField(q['incorporate_your_experience']);
        const questionText = strField(q['question']) || String(rawQ);
        return `<div class="iv-question-card">
            ${catBadge(badgeCat)}
            <div class="iv-question-text">${escapeHtml(questionText)}</div>
            ${whyText ? `<div class="iv-question-why"><em>Why they ask:</em> ${escapeHtml(whyText)}</div>` : ''}
            ${(story['use_this_experience'] || story['situation']) ? `
            <div class="iv-star-block">
                <div class="iv-star-label"><i class="fas fa-star"></i> Your Answer — STAR Framework</div>
                ${story['use_this_experience'] ? `<div class="iv-star-source"><i class="fas fa-briefcase"></i> Use your experience at: <strong>${escapeHtml(strField(story['use_this_experience']))}</strong></div>` : ''}
                <div class="iv-star-grid">
                    ${story['situation'] ? `<div class="iv-star-item"><div class="iv-star-letter">S</div><div><div class="iv-star-name">Situation</div><div class="iv-star-desc">${escapeHtml(strField(story['situation']))}</div></div></div>` : ''}
                    ${story['task'] ? `<div class="iv-star-item"><div class="iv-star-letter">T</div><div><div class="iv-star-name">Task</div><div class="iv-star-desc">${escapeHtml(strField(story['task']))}</div></div></div>` : ''}
                    ${story['action'] ? `<div class="iv-star-item"><div class="iv-star-letter">A</div><div><div class="iv-star-name">Action</div><div class="iv-star-desc">${escapeHtml(strField(story['action']))}</div></div></div>` : ''}
                    ${story['result'] ? `<div class="iv-star-item"><div class="iv-star-letter iv-star-r">R</div><div><div class="iv-star-name">Result</div><div class="iv-star-desc">${escapeHtml(strField(story['result']))}</div></div></div>` : ''}
                </div>
            </div>` : ''}
            ${approach ? `<div class="iv-tech-approach"><i class="fas fa-lightbulb"></i> ${escapeHtml(approach)}</div>` : ''}
            ${keyPts.length ? `<div class="iv-key-points"><div class="iv-key-points-label">Cover these points:</div><ul>${keyPts.map((pt) => `<li>${escapeHtml(String(pt))}</li>`).join('')}</ul></div>` : ''}
            ${followUps.length ? `<div class="iv-followups"><i class="fas fa-angle-double-right"></i> <strong>Likely follow-ups:</strong> ${followUps.map((f) => `<span class="iv-followup-tag">${escapeHtml(String(f))}</span>`).join('')}</div>` : ''}
            ${q['what_they_evaluate'] ? `<div class="iv-question-evaluate"><i class="fas fa-search"></i> <strong>They're evaluating:</strong> ${escapeHtml(strField(q['what_they_evaluate']))}</div>` : ''}
            ${incorpExp ? `<div class="iv-question-evaluate"><i class="fas fa-briefcase"></i> Reference: <strong>${escapeHtml(incorpExp)}</strong></div>` : ''}
            ${q['danger_zone'] ? `<div class="iv-danger-zone"><i class="fas fa-ban"></i> <strong>Don't say:</strong> ${escapeHtml(strField(q['danger_zone']))}</div>` : ''}
        </div>`;
    };

    const qSectionHeader = (icon: string, label: string, first = false): string =>
        `<h3 class="section-subtitle iv-q-section-header${first ? ' first' : ''}"><i class="fas ${icon}"></i> ${label}</h3>`;

    let isFirstQSection = true;

    // ── Behavioral ────────────────────────────────────────────────
    if (behaviorals.length) {
        questionsHtml += qSectionHeader('fa-comments', 'Behavioral Questions', isFirstQSection);
        isFirstQSection = false;
        questionsHtml += behaviorals.map(q => renderQuestionCard(q, 'behavioral')).join('');
    }

    // ── Technical ─────────────────────────────────────────────────
    if (technicals.length) {
        questionsHtml += qSectionHeader('fa-code', 'Technical Questions', isFirstQSection);
        isFirstQSection = false;
        questionsHtml += technicals.map(q => renderQuestionCard(q, 'technical')).join('');
    }

    // ── Role-Specific ─────────────────────────────────────────────
    if (roleSpecific.length) {
        questionsHtml += qSectionHeader('fa-user-tie', 'Role-Specific Questions', isFirstQSection);
        isFirstQSection = false;
        questionsHtml += roleSpecific.map(q => renderQuestionCard(q, 'role-specific')).join('');
    }

    // ── Company-Specific ─────────────────────────────────────────
    if (companySpecific.length) {
        questionsHtml += qSectionHeader('fa-building', 'Company-Specific Questions', isFirstQSection);
        isFirstQSection = false;
        questionsHtml += companySpecific.map(q => renderQuestionCard(q, 'company-specific')).join('');
    }

    // ── Old-schema uncategorised questions (situational, general, etc.) ──
    if (otherOldQs.length) {
        questionsHtml += qSectionHeader('fa-question-circle', 'Other Questions', isFirstQSection);
        isFirstQSection = false;
        questionsHtml += otherOldQs.map((q) => renderQuestionCard(q, strField(asResumeRecord(q)['category']) || 'general')).join('');
    }

    // ── Questions to Ask Them ─────────────────────────────────────
    const qGroups = [
        { key: 'for_recruiter',     label: 'For the Recruiter',     icon: 'fa-phone' },
        { key: 'for_hiring_manager',label: 'For the Hiring Manager', icon: 'fa-user-tie' },
        { key: 'for_team_members',  label: 'For Team Members',       icon: 'fa-users' },
        { key: 'red_flag_questions',label: 'Red Flag Questions',      icon: 'fa-flag', red: true }
    ];
    const hasQForThem = qGroups.some(g => ensureArray(qForThem[g.key]).length > 0);
    const oldQToAsk   = ensureArray(prep.questions_to_ask);
    if (hasQForThem) {
        questionsHtml += qSectionHeader('fa-hand-point-right', 'Questions to Ask Them', isFirstQSection);
        qGroups.forEach(g => {
            const items = ensureArray(qForThem[g.key]);
            if (!items.length) return;
            questionsHtml += `<div class="iv-ask-group">
                <div class="iv-ask-group-label ${g.red ? 'red' : ''}"><i class="fas ${g.icon}"></i> ${g.label}</div>`;
            questionsHtml += items.slice(0, 3).map((rawItem) => {
                const q = asResumeRecord(rawItem);
                const question = escapeHtml(strField(q['question']) || String(rawItem));
                const why = escapeHtml(strField(q['why_good'] ?? q['why']));
                const listen = escapeHtml(strField(q['listen_for'] ?? q['what_youre_checking']));
                const when = escapeHtml(strField(q['when_to_ask']));
                return `<div class="iv-ask-card">
                    <div class="iv-ask-question">${question}</div>
                    ${why    ? `<div class="iv-ask-meta"><i class="fas fa-info-circle"></i> ${why}</div>` : ''}
                    ${listen ? `<div class="iv-ask-listen"><i class="fas fa-ear-listen"></i> Listen for: ${listen}</div>` : ''}
                    ${when   ? `<div class="iv-ask-meta"><i class="fas fa-clock"></i> When: ${when}</div>` : ''}
                </div>`;
            }).join('');
            questionsHtml += `</div>`;
        });
    } else if (oldQToAsk.length) {
        questionsHtml += qSectionHeader('fa-hand-point-right', 'Questions to Ask Them', isFirstQSection);
        questionsHtml += `<div class="iv-ask-group">`;
        questionsHtml += oldQToAsk.map((rawItem) => {
            const q = asResumeRecord(rawItem);
            const question = escapeHtml(strField(q['question']) || String(rawItem));
            const why = escapeHtml(strField(q['why']));
            const when = escapeHtml(strField(q['when']));
            return `<div class="iv-ask-card">
                <div class="iv-ask-question">${question}</div>
                ${why  ? `<div class="iv-ask-meta"><i class="fas fa-info-circle"></i> ${why}</div>` : ''}
                ${when ? `<div class="iv-ask-meta"><i class="fas fa-clock"></i> When: ${when}</div>` : ''}
            </div>`;
        }).join('');
        questionsHtml += `</div>`;
    }

    if (!questionsHtml) questionsHtml = '<div class="empty-state"><i class="fas fa-question-circle"></i><p>No questions available.</p></div>';
    const richSiqEl = document.getElementById('sub-interview-questions');
    if (richSiqEl) richSiqEl.innerHTML = questionsHtml;

    // ===== SUB-PANE 3: PREPARATION ==========================================
    let prepHtml = '';

    // ── Quick Reference Card (review 5 min before) ────────────────
    const sellingPts = ensureArray(qrc['three_key_selling_points']);
    const hasQrc =
        qrc['elevator_pitch'] ||
        sellingPts.length ||
        qrc['weakness_answer'] ||
        qrc['why_this_company'] ||
        qrc['closing_statement'] ||
        qrc['salary_discussion'];
    if (hasQrc) {
        prepHtml += `<h3 class="section-subtitle"><i class="fas fa-id-card"></i> Quick Reference Card</h3>
        <div class="iv-qrc-block">
            <div class="iv-qrc-header"><i class="fas fa-bolt"></i> Review this 5 minutes before walking in</div>`;

        if (qrc['elevator_pitch']) {
            prepHtml += `<div class="iv-qrc-section">
                <div class="iv-qrc-label">Your 30-Second Pitch</div>
                <div class="iv-qrc-pitch">${escapeHtml(strField(qrc['elevator_pitch']))}</div>
            </div>`;
        }
        const selling = sellingPts.length ? sellingPts : ensureArray(qrc['three_key_selling_points']);
        if (selling.length) {
            prepHtml += `<div class="iv-qrc-section">
                <div class="iv-qrc-label">3 Key Selling Points</div>
                ${selling.map((p, i) => `<div class="iv-selling-point"><span class="iv-sp-num">${i + 1}</span><span>${escapeHtml(String(p))}</span></div>`).join('')}
            </div>`;
        }
        if (qrc['weakness_answer']) {
            const wa = asResumeRecord(qrc['weakness_answer']);
            prepHtml += `<div class="iv-qrc-section">
                <div class="iv-qrc-label">Weakness Answer</div>
                <div class="iv-weakness-block">
                    ${wa['weakness'] ? `<div class="iv-weakness-row"><strong>Weakness:</strong> ${escapeHtml(strField(wa['weakness']))}</div>` : ''}
                    ${wa['how_addressing'] ? `<div class="iv-weakness-row"><strong>What I'm doing:</strong> ${escapeHtml(strField(wa['how_addressing']))}</div>` : ''}
                    ${wa['example'] ? `<div class="iv-weakness-row"><strong>Example:</strong> ${escapeHtml(strField(wa['example']))}</div>` : ''}
                </div>
            </div>`;
        }
        if (qrc['why_this_company']) {
            prepHtml += `<div class="iv-qrc-section">
                <div class="iv-qrc-label">Why This Company</div>
                <div class="iv-qrc-text">${escapeHtml(strField(qrc['why_this_company']))}</div>
            </div>`;
        }
        if (qrc['salary_discussion']) {
            const sal = asResumeRecord(qrc['salary_discussion']);
            prepHtml += `<div class="iv-qrc-section">
                <div class="iv-qrc-label"><i class="fas fa-dollar-sign"></i> Salary Discussion</div>
                ${sal['anchor_range'] ? `<div class="iv-weakness-row"><strong>Range to anchor:</strong> <span class="iv-salary-range">${escapeHtml(strField(sal['anchor_range']))}</span></div>` : ''}
                ${sal['strategy'] ? `<div class="iv-weakness-row"><strong>Strategy:</strong> ${escapeHtml(strField(sal['strategy']))}</div>` : ''}
                ${sal['deflection_phrase'] ? `<div class="iv-weakness-row"><strong>If asked too early:</strong> <em>"${escapeHtml(strField(sal['deflection_phrase']))}"</em></div>` : ''}
            </div>`;
        }
        if (qrc['closing_statement']) {
            prepHtml += `<div class="iv-qrc-section">
                <div class="iv-qrc-label">Strong Closing</div>
                <div class="iv-qrc-text iv-closing">"${escapeHtml(strField(qrc['closing_statement']))}"</div>
            </div>`;
        }
        prepHtml += `</div>`;
    }

    // ── Old-schema: Strengths & Gaps (when new addressing_concerns missing) ──
    const oldStrengths = ensureArray(prep.your_strengths_to_highlight);
    const oldGaps      = ensureArray(prep.gaps_to_address);
    const oldTechTopics= ensureArray(prep.technical_topics);
    if (!concerns.length && (oldStrengths.length || oldGaps.length || oldTechTopics.length)) {
        if (oldStrengths.length) {
            prepHtml += `<h3 class="section-subtitle"><i class="fas fa-fire"></i> Your Strengths to Highlight</h3>
            <div class="iv-boosters">
                ${oldStrengths.map(s => `<div class="iv-booster-item"><i class="fas fa-check-circle"></i> ${escapeHtml(String(s))}</div>`).join('')}
            </div>`;
        }
        if (oldGaps.length) {
            prepHtml += `<h3 class="section-subtitle"><i class="fas fa-shield-alt"></i> Addressing Gaps</h3>`;
            prepHtml += oldGaps.map((rawG) => {
                const g = asResumeRecord(rawG);
                return `<div class="iv-concern-card">
                <div class="iv-concern-issue"><i class="fas fa-exclamation-triangle"></i> ${escapeHtml(strField(g['gap']) || String(rawG))}</div>
                ${g['strategy'] ? `<div class="iv-concern-counter"><i class="fas fa-reply"></i> <strong>Strategy:</strong> ${escapeHtml(strField(g['strategy']))}</div>` : ''}
            </div>`;
            }).join('');
        }
        if (oldTechTopics.length) {
            prepHtml += `<h3 class="section-subtitle"><i class="fas fa-code"></i> Technical Topics to Review</h3>
            <div class="iv-tech-topics-grid">
                ${oldTechTopics.map(t => `<span class="iv-tech-topic-tag"><i class="fas fa-microchip"></i> ${escapeHtml(String(t))}</span>`).join('')}
            </div>`;
        }
    }

    // ── Addressing Concerns ───────────────────────────────────────
    if (concerns.length) {
        prepHtml += `<h3 class="section-subtitle"><i class="fas fa-shield-alt"></i> Addressing Concerns</h3>`;
        prepHtml += concerns.map((rawC) => {
            const c = asResumeRecord(rawC);
            const tps = ensureArray(c['talking_points']);
            const proof = ensureArray(c['proof_points_from_experience']);
            return `<div class="iv-concern-card">
                <div class="iv-concern-issue"><i class="fas fa-exclamation-triangle"></i> ${escapeHtml(strField(c['concern']))}</div>
                ${c['why_its_a_concern'] ? `<div class="iv-concern-why"><em>What they think:</em> ${escapeHtml(strField(c['why_its_a_concern']))}</div>` : ''}
                ${c['your_counter_narrative'] ? `<div class="iv-concern-counter"><i class="fas fa-reply"></i> <strong>Your reframe:</strong> ${escapeHtml(strField(c['your_counter_narrative']))}</div>` : ''}
                ${tps.length ? `<div class="iv-concern-points"><strong>Talking points:</strong><ul>${tps.map((pt) => `<li>${escapeHtml(String(pt))}</li>`).join('')}</ul></div>` : ''}
                ${proof.length ? `<div class="iv-concern-proof"><strong>Proof from your background:</strong><ul>${proof.map((pt) => `<li><i class="fas fa-check green"></i> ${escapeHtml(String(pt))}</li>`).join('')}</ul></div>` : ''}
                ${c['when_to_bring_up'] ? `<div class="iv-concern-when"><i class="fas fa-clock"></i> <strong>When to raise it:</strong> ${escapeHtml(strField(c['when_to_bring_up']))}</div>` : ''}
            </div>`;
        }).join('');
    }

    // ── Logistics ─────────────────────────────────────────────────
    const logItems = ensureArray(logistics['what_to_bring']);
    const virtTips = ensureArray(logistics['virtual_interview_tips']);
    const postInter = asResumeRecord(logistics['post_interview']);
    const timing = asResumeRecord(logistics['timing']);
    const hasLogistics =
        logistics['dress_code'] || logItems.length || virtTips.length || postInter['thank_you_note'];
    if (hasLogistics) {
        prepHtml += `<h3 class="section-subtitle"><i class="fas fa-map-signs"></i> Logistics</h3>
        <div class="iv-logistics-grid">`;
        if (logistics['dress_code']) {
            prepHtml += `<div class="iv-logistics-item"><i class="fas fa-tshirt"></i><div><div class="iv-logistics-label">Dress Code</div><div>${escapeHtml(strField(logistics['dress_code']))}</div></div></div>`;
        }
        if (timing['arrive']) {
            prepHtml += `<div class="iv-logistics-item"><i class="fas fa-clock"></i><div><div class="iv-logistics-label">Arrive</div><div>${escapeHtml(strField(timing['arrive']))}</div></div></div>`;
        }
        if (timing['expected_duration']) {
            prepHtml += `<div class="iv-logistics-item"><i class="fas fa-hourglass-half"></i><div><div class="iv-logistics-label">Block</div><div>${escapeHtml(strField(timing['expected_duration']))}</div></div></div>`;
        }
        prepHtml += `</div>`;
        if (logItems.length) {
            prepHtml += `<div class="iv-logistics-label" style="margin:0.75rem 0 0.35rem">What to Bring</div>
            <ul class="iv-bring-list">${logItems.map(b => `<li><i class="fas fa-check-circle"></i> ${escapeHtml(String(b))}</li>`).join('')}</ul>`;
        }
        if (virtTips.length) {
            prepHtml += `<div class="iv-logistics-label" style="margin:0.75rem 0 0.35rem">Virtual Interview Tips</div>
            <ul class="iv-bring-list">${virtTips.map(t => `<li><i class="fas fa-video"></i> ${escapeHtml(String(t))}</li>`).join('')}</ul>`;
        }
        if (postInter['thank_you_note'] || postInter['follow_up_timeline']) {
            prepHtml += `<div class="iv-logistics-label" style="margin:0.75rem 0 0.35rem">After the Interview</div>
            <div class="iv-post-interview">`;
            if (postInter['thank_you_note']) prepHtml += `<div class="iv-logistics-item"><i class="fas fa-envelope"></i><div><div class="iv-logistics-label">Thank-you note</div><div>${escapeHtml(strField(postInter['thank_you_note']))}</div></div></div>`;
            if (postInter['follow_up_timeline']) prepHtml += `<div class="iv-logistics-item"><i class="fas fa-calendar-check"></i><div><div class="iv-logistics-label">Follow up</div><div>${escapeHtml(strField(postInter['follow_up_timeline']))}</div></div></div>`;
            prepHtml += `</div>`;
        }
    }

    // ── Day-Before Checklist ──────────────────────────────────────
    if (dayBefore.length) {
        prepHtml += `<h3 class="section-subtitle"><i class="fas fa-tasks"></i> Day-Before Checklist</h3>
        <div class="iv-day-checklist">
            ${dayBefore.map(c => `<label class="iv-day-check"><input type="checkbox"><span>${escapeHtml(String(c))}</span></label>`).join('')}
        </div>`;
    }

    // ── Confidence Boosters (new) / What They Evaluate (old fallback) ──
    const oldWTE = ensureArray(prep.what_they_evaluate);
    const displayBoostrs = boostrs.length ? boostrs : (oldStrengths.length ? [] : oldWTE);
    if (displayBoostrs.length) {
        prepHtml += `<h3 class="section-subtitle"><i class="fas fa-fire"></i> Remember Your Strengths</h3>
        <div class="iv-boosters">
            ${displayBoostrs.map(b => `<div class="iv-booster-item"><i class="fas fa-check-circle"></i> ${escapeHtml(String(b))}</div>`).join('')}
        </div>`;
    }

    if (!prepHtml) prepHtml = '<div class="empty-state"><i class="fas fa-tasks"></i><p>No preparation tips available.</p></div>';
    const richSippEl = document.getElementById('sub-interview-preparation');
    if (richSippEl) richSippEl.innerHTML = prepHtml;

    // Regenerate button
    const richIrbEl = document.getElementById('interviewRegenBtn');
    if (richIrbEl) richIrbEl.innerHTML = `
        <div style="margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid var(--border-color);">
            <button class="regen-btn" data-action="gen-interview" aria-label="Regenerate interview prep">
                <span class="spinner"></span>
                <span class="btn-text"><i class="fas fa-sync-alt"></i> Regenerate</span>
            </button>
        </div>`;
}

