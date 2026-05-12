(function () {
    'use strict';

    // Constants
    const API_BASE = (window.APP_CONFIG && window.APP_CONFIG.apiBase) || '/api/v1';

    /** @param {string|null|undefined} str */
    function escapeHtml(str) {
        if (str == null) return '';
        // &amp;amp; is the bleach double-encode of a literal & (& → &amp; via html.escape → &amp;amp; via bleach).
        // Decode that first, then the remaining &amp; covers entities like &amp;#x27; → &#x27; → '.
        const decoded = String(str)
            .replace(/&amp;amp;/g, '&')
            .replace(/&amp;/g, '&')
            .replace(/&#x27;/g, "'")
            .replace(/&#039;/g, "'")
            .replace(/&quot;/g, '"')
            .replace(/&lt;/g, '<')
            .replace(/&gt;/g, '>');
        return decoded
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    /** Decode HTML entities for use with .textContent (doesn't re-encode) */
    function decodeEntities(str) {
        if (str == null) return '';
        return String(str)
            .replace(/&amp;amp;/g, '&')
            .replace(/&amp;/g, '&')
            .replace(/&#x27;/g, "'")
            .replace(/&#039;/g, "'")
            .replace(/&quot;/g, '"')
            .replace(/&lt;/g, '<')
            .replace(/&gt;/g, '>');
    }

    /**
     * True when job analysis has no real employer string (empty, N/A, dash placeholders from the LLM).
     * Mirrors the intent of `_has_usable_company_name` in `agents/company_research.py` (inverse).
     * @param {unknown} raw
     * @returns {boolean}
     */
    function isPlaceholderCompanyName(raw) {
        if (raw == null) return true;
        const s = String(raw).trim();
        if (!s) return true;
        const lower = s.toLowerCase();
        /** @type {Set<string>} */
        const literals = new Set([
            '-', '–', '—', '−',
            'n/a', 'na', 'unknown', 'null', 'none',
            'not specified', 'not stated', 'tbd', 'confidential', 'undisclosed',
            '...',
        ]);
        if (literals.has(lower)) return true;
        if (/^[\s\-–—−]+$/u.test(s)) return true;
        return false;
    }

    /**
     * Format a raw date string (YYYY-MM-DD or ISO) into "Mon D, YYYY".
     * Returns '' if the input is missing or unparseable — callers must hide the
     * card when an empty string is returned.
     * @param {string|null|undefined} dateStr
     * @returns {string}
     */
    function formatPostedDate(dateStr) {
        if (!dateStr) return '';
        try {
            // Parse YYYY-MM-DD without timezone shift by treating parts as local date
            const parts = String(dateStr).match(/^(\d{4})-(\d{2})-(\d{2})/);
            const d = parts
                ? new Date(parseInt(parts[1]), parseInt(parts[2]) - 1, parseInt(parts[3]))
                : new Date(dateStr);
            if (isNaN(d.getTime())) return '';
            const now = new Date();
            // Reject future dates
            if (d > now) return '';
            // Reject dates before Jan 1 2026 (stale / LLM hallucination)
            if (d < new Date(2026, 0, 1)) return '';
            return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
        } catch (_e) {
            return '';
        }
    }

    function getAuthToken() {
        // @ts-ignore
        return (window.app && typeof window.app.getAuthToken === 'function')
            ? window.app.getAuthToken()
            : (localStorage.getItem('access_token') || localStorage.getItem('authToken'));
    }

    /** @type {Record<string,unknown>|null} */
    let applicationData = null;
    /** @type {string|null} */
    let currentSessionId = null;
    /** @type {string|null} */
    let currentApplicationId = null;
    /** Timeout IDs for clearable timers */
    let _processingRefreshTimer = /** @type {number|null} */ (null);
    /** @type {number|null} */
    let _toastOutTimer = /** @type {number|null} */ (null);
    /** @type {number|null} */
    let _toastRemoveTimer = /** @type {number|null} */ (null);
    /** In-flight guards prevent duplicate concurrent API calls */
    let _regeneratingCoverLetter = false;
    let _regeneratingResume = false;
    let _generatingInterviewPrep = false;
    let _continuingWorkflow = false;
    /** @type {string|null} */
    let workflowStatus = null;

    /**
     * @param {any} value
     * @returns {any[]}
     */
    function ensureArray(value) {
        if (Array.isArray(value)) return value;
        if (value === null || value === undefined) return [];
        if (typeof value === 'string') return value.trim() ? [value] : [];
        return [];
    }

    /** @param {string} s @returns {string} */
    function toTitleCase(s) {
        return s ? s.replace(/\w\S*/g, t => t.charAt(0).toUpperCase() + t.slice(1).toLowerCase()) : s;
    }

    // Initialize
    document.addEventListener('DOMContentLoaded', async () => {
        if (!checkAuth()) return;
        if (typeof window.syncProfileCompletionFromApi !== 'function' || !(await window.syncProfileCompletionFromApi())) return;

        // Get session ID from URL
        const pathParts = window.location.pathname.split('/');
        currentSessionId = pathParts[pathParts.length - 1];

        if (currentSessionId) {
            loadApplicationData();
        } else {
            showError('No application ID provided');
        }

        // React to real-time WebSocket events broadcast by navbar-notifications.js.
        // This eliminates the polling delay — the page updates the instant the backend
        // fires; the 3-second poll in showProcessing() acts only as a fallback when WS
        // is unavailable (e.g. proxy stripping upgrade headers).
        window.addEventListener('applypilot:ws', (/** @type {CustomEvent} */ e) => {
            const msg       = /** @type {Record<string,any>} */ (e.detail || {});
            const type      = String(msg['type']       || '');
            const sessionId = String(msg['session_id'] || '');

            if (!currentSessionId || sessionId !== currentSessionId) return;

            if (type === 'workflow_complete' || type === 'workflow_error') {
                // Cancel the poll timer — WS beat it.
                if (_processingRefreshTimer !== null) {
                    clearTimeout(_processingRefreshTimer);
                    _processingRefreshTimer = null;
                }
                loadApplicationData();
            } else if (type === 'agent_update') {
                // Advance the step indicator without a full reload.
                const agentName = String((msg['data'] && msg['data']['agent']) || '');
                const agentStatus = String((msg['data'] && msg['data']['status']) || '');
                if (agentName && agentStatus === 'running') {
                    // Re-render the processing screen with the now-active agent.
                    showProcessing(agentName);
                }
            }
        });

        // Clear pending timers on navigation to prevent ghost callbacks
        window.addEventListener('beforeunload', () => {
            if (_processingRefreshTimer !== null) clearTimeout(_processingRefreshTimer);
            if (_toastOutTimer !== null) clearTimeout(_toastOutTimer);
            if (_toastRemoveTimer !== null) clearTimeout(_toastRemoveTimer);
        });

        // Page tab navigation
        document.querySelectorAll('.page-tab').forEach(btn => {
            btn.addEventListener('click', () => {
                const tabId = /** @type {HTMLElement} */ (btn).dataset.tab;
                switchTab(tabId);
                if (tabId === 'optimize' && typeof window.initCvOptimizerTab === 'function') {
                    window.initCvOptimizerTab(currentSessionId);
                }
            });
        });

        // Sub-tab navigation
        document.querySelectorAll('.sub-tab').forEach(btn => {
            btn.addEventListener('click', () => {
                const subTabsEl = /** @type {HTMLElement|null} */ (btn.closest('.sub-tabs'));
                const parentId = subTabsEl?.dataset.parent;
                switchSubTab(parentId, /** @type {HTMLElement} */ (btn).dataset.subtab);
            });
        });

        // Event delegation for dynamically generated action buttons
        /** @param {MouseEvent} e */
        const handleDynamicAction = (e) => {
            const btn = /** @type {HTMLElement|null} */ (/** @type {HTMLElement} */ (e.target).closest('[data-action]'));
            if (!btn) return;
            const action = /** @type {HTMLElement} */ (btn).dataset.action;
            if (action === 'regen-cover')    regenerateCoverLetter(/** @type {HTMLButtonElement} */ (btn));
            if (action === 'regen-resume')   regenerateResume(/** @type {HTMLButtonElement} */ (btn));
            if (action === 'gen-interview')  generateInterviewPrep(/** @type {HTMLButtonElement} */ (btn));
            if (action === 'copy-text')      copyText(/** @type {HTMLButtonElement} */ (btn), /** @type {HTMLElement} */ (btn).dataset.copyText || '');
            if (action === 'copy-cover') {
                const textEl = /** @type {HTMLElement|null} */ (document.querySelector('.cover-letter-body'));
                const text = textEl ? (textEl.textContent || '') : '';
                navigator.clipboard.writeText(text).then(() => {
                    /** @type {HTMLElement} */ (btn).innerHTML = '<i class="fas fa-check"></i> Copied!';
                    setTimeout(() => { /** @type {HTMLElement} */ (btn).innerHTML = '<i class="fas fa-copy"></i> Copy'; }, 2000);
                }).catch(() => notify('Could not copy to clipboard', 'error'));
            }
        };
        document.getElementById('pane-cover')?.addEventListener('click', handleDynamicAction);
        document.getElementById('pane-resume')?.addEventListener('click', handleDynamicAction);
        document.getElementById('pane-interview')?.addEventListener('click', handleDynamicAction);
    });

    /** @returns {boolean} */
    function checkAuth() {
        // @ts-ignore
        const authenticated = window.app ? window.app.isAuthenticated() : !!getAuthToken();
        if (!authenticated) {
            window.location.href = (window.APP_CONFIG && window.APP_CONFIG.loginUrl) || '/auth/login';
            return false;
        }
        return true;
    }

    async function loadApplicationData() {
        try {
            const statusRes = await fetch(`${API_BASE}/workflow/status/${currentSessionId}`, {
                headers: { 'Authorization': `Bearer ${getAuthToken()}` }
            });

            if (statusRes.status === 404) {
                showError('Application not found');
                return;
            }
            if (statusRes.status === 401) {
                window.location.href = (window.APP_CONFIG && window.APP_CONFIG.loginUrl) || '/auth/login';
                return;
            }
            if (!statusRes.ok) throw new Error('Failed to load status');

            const statusData = await statusRes.json();
            workflowStatus = statusData.status || null;

            if (statusData.status === 'in_progress' || statusData.status === 'initialized' || statusData.status === 'pending') {
                applicationData = statusData;
                showProcessing(statusData.current_agent || null);
                return;
            }

            const resultsRes = await fetch(`${API_BASE}/workflow/results/${currentSessionId}`, {
                headers: { 'Authorization': `Bearer ${getAuthToken()}` }
            });

            if (resultsRes.ok) {
                applicationData = await resultsRes.json();
            } else {
                applicationData = statusData;
            }

            renderApplication();

        } catch (error) {
            const err = /** @type {Error} */ (error);
            console.error('Error loading application:', err);
            showError(err.message);
        }
    }

    /** @param {string} message */
    function showError(message) {
        const ls = document.getElementById('loadingState');
        const es = document.getElementById('errorState');
        const em = document.getElementById('errorMessage');
        if (ls) ls.style.display = 'none';
        if (es) es.style.display = 'block';
        if (em) em.textContent = message;
    }

    /** @param {string|null} [currentAgent] */
    function showProcessing(currentAgent) {
        const ls = document.getElementById('loadingState');
        if (!ls) return;

        const STEPS = [
            { id: 'job_analyzer',        label: 'Analyzing job requirements',   icon: 'fa-search' },
            { id: 'profile_matching',    label: 'Matching your profile',        icon: 'fa-user-check' },
            { id: 'company_research',    label: 'Researching the company',      icon: 'fa-building' },
            { id: 'cover_letter_writer', label: 'Writing cover letter',         icon: 'fa-envelope' },
            { id: 'resume_advisor',      label: 'Generating resume tips',       icon: 'fa-file-alt' },
        ];

        const stepOrder = STEPS.map(s => s.id);
        const currentIdx = currentAgent ? stepOrder.indexOf(currentAgent) : 0;

        const stepsHtml = STEPS.map((step, idx) => {
            let stateClass, iconHtml;
            if (idx < currentIdx) {
                stateClass = 'done';
                iconHtml = '<i class="fas fa-check"></i>';
            } else if (idx === currentIdx) {
                stateClass = 'active';
                iconHtml = '<div class="agent-step-spinner"></div>';
            } else {
                stateClass = '';
                iconHtml = `<i class="fas ${step.icon}"></i>`;
            }
            return `<div class="agent-step ${stateClass}">
                <div class="agent-step-icon">${iconHtml}</div>
                <span class="agent-step-label">${step.label}</span>
            </div>`;
        }).join('');

        ls.innerHTML = `
            <div class="agent-progress-card">
                <div class="agent-progress-header">
                    <i class="fas fa-robot agent-progress-icon"></i>
                    <h3 class="agent-progress-title">AI Agents Working</h3>
                    <p class="agent-progress-subtitle">This takes about 30 seconds — you don't need to wait here</p>
                </div>
                <div class="agent-steps">${stepsHtml}</div>
                <div class="agent-progress-footer">
                    <a href="/dashboard" class="btn btn-secondary btn-sm">
                        <i class="fas fa-arrow-left me-2"></i>Back to Dashboard
                    </a>
                    <span class="agent-progress-footer-note">This page updates automatically</span>
                </div>
            </div>
        `;

        if (_processingRefreshTimer !== null) clearTimeout(_processingRefreshTimer);
        _processingRefreshTimer = window.setTimeout(() => { _processingRefreshTimer = null; loadApplicationData(); }, 3000);
    }

    function renderApplication() {
        const ls = document.getElementById('loadingState');
        const mc = document.getElementById('mainContent');
        if (ls) ls.style.display = 'none';
        if (mc) mc.style.display = 'block';
        if (!applicationData) return;

        const data = /** @type {Record<string,any>} */ (applicationData);
        const job = data['job_analysis'] || {};
        const match = data['profile_matching'] || {};
        const company = data['company_research'] || {};
        const resume = data['resume_recommendations'] || {};
        const cover = data['cover_letter'] || {};

        // Store job URL and application ID
        currentApplicationId = data['application_id'] || null;

        // Render header
        renderHeader(job, match);

        // Render all tabs
        renderMainContent(job, company, match);
        renderCoverLetter(cover, job);
        renderResumeTips(resume);
        renderInterviewPrep(company, job);
    }

    /**
     * @param {any} job
     * @param {any} match
     */
    function renderHeader(job, match) {
        // Job info
        const jtEl = document.getElementById('jobTitle');
        const cnEl = document.getElementById('companyName');
        const cdEl = document.getElementById('createdDate');
        if (jtEl) jtEl.textContent = decodeEntities(job.job_title || 'Job Application');
        if (cnEl) {
            const companyTrimmed = job.company_name && String(job.company_name).trim();
            cnEl.textContent =
                companyTrimmed && !isPlaceholderCompanyName(job.company_name)
                    ? decodeEntities(companyTrimmed)
                    : 'Unknown';
        }
        if (cdEl) cdEl.textContent = new Date().toLocaleDateString();

        // Location
        const location = [job.job_city, job.job_state, job.job_country].filter(Boolean).join(', ');
        if (location) {
            const jlEl = document.getElementById('jobLocation');
            const lmEl = document.getElementById('locationMeta');
            if (jlEl) jlEl.textContent = location;
            if (lmEl) lmEl.style.display = 'flex';
        }

        // Posted date
        const _formattedPostedDate = formatPostedDate(job.posted_date);
        if (_formattedPostedDate) {
            const pdEl = document.getElementById('postedDateText');
            const pmEl = document.getElementById('postedDateMeta');
            if (pdEl) pdEl.textContent = _formattedPostedDate;
            if (pmEl) pmEl.style.display = 'flex';
        }

        // Salary — only show badge when there's an actual number to display
        let salaryDisplay = null;
        if (job.salary_range && typeof job.salary_range === 'object') {
            if (job.salary_range.min || job.salary_range.max) {
                const curr = job.salary_range.currency || '$';
                const min = job.salary_range.min ? `${curr}${(job.salary_range.min/1000).toFixed(0)}K` : '';
                const max = job.salary_range.max ? `${curr}${(job.salary_range.max/1000).toFixed(0)}K` : '';
                if (min && max) salaryDisplay = `${min} - ${max}`;
                else if (min) salaryDisplay = `${min}+`;
                else if (max) salaryDisplay = `Up to ${max}`;
            }
        } else if (typeof job.salary_range === 'string') {
            // Only use string value if it contains an actual number (not just a currency symbol)
            const trimmed = job.salary_range.trim();
            if (trimmed && /\d/.test(trimmed)) salaryDisplay = trimmed;
        }
        if (salaryDisplay) {
            const srEl = document.getElementById('salaryRange');
            const sbEl = document.getElementById('salaryBadge');
            if (srEl) srEl.textContent = salaryDisplay;
            if (sbEl) sbEl.style.display = 'inline-flex';
        }

        // Employment type
        if (job.employment_type) {
            const etEl = document.getElementById('employmentType');
            const tbEl = document.getElementById('typeBadge');
            if (etEl) etEl.textContent = toTitleCase(decodeEntities(job.employment_type));
            if (tbEl) tbEl.style.display = 'inline-flex';
        }

        // Work arrangement
        if (job.work_arrangement) {
            const wtEl = document.getElementById('workType');
            const wbEl = document.getElementById('workBadge');
            if (wtEl) wtEl.textContent = toTitleCase(decodeEntities(job.work_arrangement));
            if (wbEl) wbEl.style.display = 'inline-flex';
        }

        // Match score
        const qa = match.quantified_assessment || match.final_scores || {};
        const matchScore = qa.overall_match_score || match.overall_match_score || match.overall_score || 0;
        const scorePercent = matchScore > 1 ? Math.round(matchScore) : Math.round(matchScore * 100);

        const msEl = document.getElementById('matchScore');
        const mcEl = document.getElementById('matchCircle');
        if (msEl) msEl.textContent = `${scorePercent}%`;
        if (mcEl) mcEl.style.setProperty('--score', String(scorePercent));

        // Match status
        const exec = match.executive_summary || {};
        const rec = (exec.recommendation || match.recommendation || 'REVIEW').toUpperCase();
        const statusEl = document.getElementById('matchStatus');

        if (statusEl) {
            if (rec.includes('GOOD') || rec.includes('STRONG')) {
                statusEl.textContent = 'Good Match';
                statusEl.className = 'match-status good';
            } else if (rec.includes('POOR') || rec.includes('PASS')) {
                statusEl.textContent = 'Weak Match';
                statusEl.className = 'match-status poor';
            } else {
                statusEl.textContent = 'Review';
                statusEl.className = 'match-status review';
            }
        }
    }

    /**
     * @param {any} job
     * @param {any} company
     * @param {any} match
     */
    function renderMainContent(job, company, match) {
        // Merge skills
        const allSkillsSet = new Set();
        const addSkills = (/** @type {any[]} */ arr) => {
            (arr || []).forEach((/** @type {any} */ s) => {
                const skill = typeof s === 'object' ? (s.skill || s.name || '') : s;
                if (skill) allSkillsSet.add(skill);
            });
        };
        addSkills(job.required_skills);
        addSkills(job.ats_keywords);
        addSkills(job.keywords);
        const allSkills = Array.from(allSkillsSet);

        const qualifications = ensureArray(job.required_qualifications);
        const responsibilities = ensureArray(job.responsibilities).filter(r => {
            const s =
                typeof r === 'object' && r !== null
                    ? String(r.text ?? r.duty ?? r.responsibility ?? '').trim()
                    : String(r).trim();
            return s.length > 0;
        });
        const preferredQuals = ensureArray(job.preferred_qualifications);
        const softSkills = ensureArray(job.soft_skills);

        // Match data
        const exec = match.executive_summary || {};
        const qa = match.quantified_assessment || match.final_scores || {};
        const strengths = ensureArray(match.detailed_analysis?.key_strengths || match.key_strengths);
        const gaps = ensureArray(match.detailed_analysis?.critical_gaps || match.critical_gaps || match.gaps);

        const appStrategy = match.application_strategy || {};
        const competitive = match.competitive_positioning || {};
        const riskAssessment = match.risk_assessment || {};
        const dealBreakers = match.deal_breaker_analysis || {};
        const aiInsights = match.ai_insights || {};
        const qualAnalysis = match.qualification_analysis || {};
        const prefAnalysis = match.preference_analysis || {};

        // Company data
        const coreValues = ensureArray(company.core_values);
        const keyProducts = ensureArray(company.key_products);
        const whatToEmphasize = ensureArray(company.what_to_emphasize || company.application_insights?.what_to_emphasize);
        const leadership = ensureArray(company.leadership_info);
        const competitors = ensureArray(company.competitors);
        const cultureFitSignals = ensureArray(company.application_insights?.culture_fit_signals);
        const redFlagsToWatch = ensureArray(company.application_insights?.red_flags_to_watch);
        const competitiveAdvantages = ensureArray(company.competitive_advantages);
        const growthOpportunities = ensureArray(company.growth_opportunities);

        const toPercent = (/** @type {number} */ val) => val > 1 ? Math.round(val) : Math.round(val * 100);
        const getBarClass = (/** @type {number} */ v) => { const p = v > 1 ? v : v * 100; return p >= 70 ? 'good' : p >= 40 ? 'medium' : 'low'; };

        const companyNameTrimmed = job.company_name && String(job.company_name).trim();
        const aboutCompanyHeading =
            companyNameTrimmed && !isPlaceholderCompanyName(job.company_name)
                ? escapeHtml(companyNameTrimmed)
                : 'this opportunity';

        // ========== SUB-PANE 1: COMPANY INFO ==========
        let companyHtml = '';
        if (company && Object.keys(company).length > 0) {
            const _rawWebsite = company.website || '';
            const _validWebsite = /^https?:\/\//i.test(_rawWebsite) ? _rawWebsite : '';
            const safeWebsiteHref   = encodeURI(_validWebsite).replace(/"/g, '%22');
            const safeWebsiteLabel  = escapeHtml(_validWebsite ? _validWebsite.replace('https://', '').replace('http://', '') : '');
            companyHtml += `
                <div class="content-section">
                    <h2 class="section-title"><i class="fas fa-building"></i> About ${aboutCompanyHeading}</h2>
                    <div class="company-card">
                        <div class="company-stats">
                            <div class="company-stat">
                                <span class="stat-label">Industry</span>
                                <span class="stat-value">${escapeHtml(company.industry) || 'Technology'}</span>
                            </div>
                            <div class="company-stat">
                                <span class="stat-label">Size</span>
                                <span class="stat-value">${escapeHtml(company.company_size || 'Not specified')}</span>
                            </div>
                            ${company.headquarters ? `<div class="company-stat"><span class="stat-label">Location</span><span class="stat-value">${escapeHtml(company.headquarters)}</span></div>` : ''}
                            ${_validWebsite ? `<div class="company-stat"><span class="stat-label">Website</span><span class="stat-value"><a href="${safeWebsiteHref}" target="_blank" rel="noopener noreferrer" style="color: var(--accent-primary);">${safeWebsiteLabel}</a></span></div>` : ''}
                            ${company.founded_year ? `<div class="company-stat"><span class="stat-label">Founded</span><span class="stat-value">${escapeHtml(String(company.founded_year))}</span></div>` : ''}
                            ${company.hiring_timeline ? `<div class="company-stat"><span class="stat-label">Hiring Timeline</span><span class="stat-value">${escapeHtml(company.hiring_timeline)} <span class="stat-estimated">(estimated)</span></span></div>` : ''}
                        </div>
                    </div>
                    ${company.mission_vision ? `<div class="section-subtitle">Mission &amp; Vision</div><div class="mission-box"><i class="fas fa-bullseye"></i><span>${escapeHtml(company.mission_vision)}</span></div>` : ''}
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
                        ${company.work_environment ? `<div class="company-detail-item"><div class="detail-label"><i class="fas fa-users"></i> Work Environment</div><div class="detail-value">${escapeHtml(company.work_environment)}</div></div>` : ''}
                        ${company.remote_work_policy ? `<div class="company-detail-item"><div class="detail-label"><i class="fas fa-laptop-house"></i> Remote Policy</div><div class="detail-value">${escapeHtml(company.remote_work_policy)}</div></div>` : ''}
                        ${company.diversity_inclusion ? `<div class="company-detail-item"><div class="detail-label"><i class="fas fa-globe"></i> Diversity &amp; Inclusion</div><div class="detail-value">${escapeHtml(company.diversity_inclusion)}</div></div>` : ''}
                        ${company.employee_satisfaction ? `<div class="company-detail-item"><div class="detail-label"><i class="fas fa-smile"></i> Employee Satisfaction</div><div class="detail-value">${escapeHtml(company.employee_satisfaction)}</div></div>` : ''}
                    </div>` : ''}
                    ${leadership.length ? `<div class="section-subtitle">Leadership</div><div class="leadership-grid">${leadership.slice(0, 3).map(l => `<div class="leadership-card"><div class="leader-name">${escapeHtml(l.name || 'Unknown')}</div><div class="leader-title">${escapeHtml(l.title || '')}</div>${l.background ? `<div class="leader-bg">${escapeHtml(String(l.background).substring(0, 100))}${l.background.length > 100 ? '...' : ''}</div>` : ''}</div>`).join('')}</div>` : ''}
                    ${company.employee_benefits?.length ? `<div class="section-subtitle">Benefits</div><div class="tags-grid">${company.employee_benefits.slice(0, 8).map((/** @type {any} */ b) => `<span class="tag benefit">${escapeHtml(String(b))}</span>`).join('')}</div>` : ''}
                    ${(competitors.length || company.market_position || competitiveAdvantages.length || growthOpportunities.length || company.recent_developments) ? `
                    <div class="section-subtitle">Market Context</div>
                    ${competitors.length ? `<div class="context-row"><span class="context-label">Competitors</span><div class="tags-grid inline">${competitors.slice(0, 6).map(c => `<span class="tag competitor">${escapeHtml(String(c))}</span>`).join('')}</div></div>` : ''}
                    ${company.market_position ? `<div class="context-row"><span class="context-label">Position</span><span class="context-value">${escapeHtml(company.market_position)}</span></div>` : ''}
                    ${competitiveAdvantages.length ? `<ul class="content-list" style="margin-top:0.5rem">${competitiveAdvantages.slice(0, 4).map(a => `<li><i class="fas fa-shield-alt green"></i><span>${escapeHtml(String(a))}</span></li>`).join('')}</ul>` : ''}
                    ${growthOpportunities.length ? `<div class="section-subtitle" style="margin-top:0.75rem">Growth Opportunities</div><ul class="content-list">${growthOpportunities.slice(0, 3).map(g => `<li><i class="fas fa-chart-line green"></i><span>${escapeHtml(String(g))}</span></li>`).join('')}</ul>` : ''}
                    ${company.recent_developments ? `<div class="recent-dev-box"><i class="fas fa-newspaper"></i><div><div class="recent-dev-label">Recent Developments${company.research_date ? ` <span class="recent-dev-date">as of ${escapeHtml(company.research_date)}</span>` : ''}</div><div class="recent-dev-text">${escapeHtml(company.recent_developments)}</div></div></div>` : ''}
                    ` : ''}
                    ${whatToEmphasize.length ? `<div class="section-subtitle">What They Look For</div><ul class="content-list">${whatToEmphasize.slice(0, 6).map(w => `<li><i class="fas fa-crosshairs orange"></i><span>${escapeHtml(String(w))}</span></li>`).join('')}</ul>` : ''}
                    ${cultureFitSignals.length ? `<div class="section-subtitle">How to Show Culture Fit</div><ul class="content-list">${cultureFitSignals.slice(0, 4).map(c => `<li><i class="fas fa-lightbulb green"></i><span>${escapeHtml(String(c))}</span></li>`).join('')}</ul>` : ''}
                    ${redFlagsToWatch.length ? `<div class="section-subtitle watch-out-title"><i class="fas fa-exclamation-triangle"></i> Things to Be Aware Of</div><div class="watch-out-note">Keep these in mind — they are patterns that tend to not land well at this company.</div><ul class="content-list warning-list">${redFlagsToWatch.slice(0, 4).map(r => `<li><i class="fas fa-minus-circle amber"></i><span>${escapeHtml(String(r))}</span></li>`).join('')}</ul>` : ''}
                </div>`;
        } else {
            const isBelowGate = workflowStatus === 'awaiting_confirmation';
            const matchRec = ((match.executive_summary || {}).recommendation || match.recommendation || '').toUpperCase();
            const isWeakMatch = matchRec === 'NOT_RECOMMENDED' || matchRec === 'WEAK_MATCH';
            if (isBelowGate || isWeakMatch) {
                companyHtml = `
                    <div class="empty-state">
                        <i class="fas fa-building empty-state-icon"></i>
                        <p class="empty-state-title">Company Research</p>
                        <p class="empty-state-desc">Company research was skipped due to a low match score. You can still continue — company research, cover letter, and resume tips will all be generated.</p>
                        ${currentSessionId ? `<button class="regen-btn" id="continueWorkflowBtn" data-action="continue-workflow">
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
        if (continueBtn) continueBtn.addEventListener('click', continueWorkflow);

        // ========== SUB-PANE 2: YOUR FIT ==========
        const verdict = exec.one_line_verdict || exec.fit_assessment || match.fit_assessment || '';
        const qualScore = qa.qualification_match_score || match.qualification_score || 0;
        const prefScore = qa.preference_match_score || match.preference_score || 0;
        const overallScore = qa.overall_match_score || match.overall_match_score || match.overall_score || 0;
        const recommendation = (exec.recommendation || '').toUpperCase();
        const confidenceLevel = (exec.confidence_level || '').toUpperCase();

        // Apply decision data
        const shouldApply = appStrategy.should_apply;
        const applyPriority = (appStrategy.application_priority || '').toUpperCase();
        const successProb = (appStrategy.success_probability || '').toUpperCase();

        // Deal breaker data
        const dealBreakersPass = dealBreakers.all_passed;
        const visaStatus = dealBreakers.visa_sponsorship;
        const locationReqs = dealBreakers.location_requirements;
        const securityClearance = dealBreakers.security_clearance;
        const hasDealBreakers = Object.keys(dealBreakers).length > 0;

        // Competitive positioning
        const percentile = competitive.estimated_candidate_pool_percentile;
        const uvp = competitive.unique_value_proposition || '';
        const strengthsVsTypical = ensureArray(competitive.strengths_vs_typical_applicant);
        const weaknessesVsTypical = ensureArray(competitive.weaknesses_vs_typical_applicant);

        // Risk / concerns
        const employerConcerns = ensureArray(riskAssessment.red_flags_for_employer);

        // AI insights
        const careerAdvice = aiInsights.career_advice || '';
        const altRoles = ensureArray(aiInsights.alternative_roles);
        const skillsToBuild = ensureArray(aiInsights.skill_development_priority);

        // Cert gaps
        const certA = (qualAnalysis || {}).certification_assessment || {};
        const missingCerts = ensureArray(certA.missing_required);

        // Helpers for label styling
        const priorityClass = (/** @type {string} */ p) => ({ HIGH: 'good', MEDIUM: 'review', LOW: 'muted', SKIP: 'poor' })[p] || 'muted';
        const probClass = (/** @type {string} */ p) => ({ HIGH: 'good', MEDIUM: 'review', LOW: 'poor', VERY_LOW: 'poor' })[p] || 'muted';
        const recLabel = (/** @type {string} */ r) => ({
            STRONG_MATCH: 'Strong Match', GOOD_MATCH: 'Good Match',
            MODERATE_MATCH: 'Moderate Match', WEAK_MATCH: 'Weak Match', NOT_RECOMMENDED: 'Not Recommended'
        })[r] || r.replace(/_/g, ' ');

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
                        ${visaStatus ? `<div class="deal-breaker-item"><div class="db-label">Visa Sponsorship</div><div class="db-value ${visaStatus.passed ? 'pass' : 'fail'}">${escapeHtml(visaStatus.status) || (visaStatus.passed ? '✓ OK' : '⚠ Issue')}</div>${visaStatus.notes ? `<div class="db-notes">${escapeHtml(visaStatus.notes)}</div>` : ''}</div>` : ''}
                        ${locationReqs ? `<div class="deal-breaker-item"><div class="db-label">Location</div><div class="db-value ${locationReqs.passed ? 'pass' : 'fail'}">${escapeHtml(locationReqs.status) || (locationReqs.passed ? '✓ OK' : '⚠ Issue')}</div>${locationReqs.notes ? `<div class="db-notes">${escapeHtml(locationReqs.notes)}</div>` : ''}</div>` : ''}
                        ${securityClearance ? `<div class="deal-breaker-item"><div class="db-label">Security Clearance</div><div class="db-value ${securityClearance.passed ? 'pass' : 'fail'}">${escapeHtml(securityClearance.status) || (securityClearance.passed ? '✓ OK' : '⚠ Issue')}</div>${securityClearance.notes ? `<div class="db-notes">${escapeHtml(securityClearance.notes)}</div>` : ''}</div>` : ''}
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
                    const qa2 = qualAnalysis || {};
                    const skillsA = qa2.skills_assessment || {};
                    const expA = qa2.experience_assessment || {};
                    const eduA = qa2.education_assessment || {};
                    if (!skillsA.score && !expA.score && !eduA.score) return '';
                    const skillGapNote = skillsA.skill_gaps_analysis || '';
                    return `<div class="section-subtitle">Qualification Breakdown</div><div class="breakdown-grid">
                        ${skillsA.score !== undefined ? `<div class="breakdown-item"><div class="breakdown-label">Skills</div><div class="breakdown-bar-container"><div class="breakdown-bar-fill ${getBarClass(skillsA.score)}" data-pct="${toPercent(skillsA.score)}"></div></div><div class="breakdown-score">${toPercent(skillsA.score)}%</div><div class="breakdown-desc">How well your listed skills match the required and preferred skills for this role</div></div>` : ''}
                        ${expA.score !== undefined ? `<div class="breakdown-item"><div class="breakdown-label">Experience</div><div class="breakdown-bar-container"><div class="breakdown-bar-fill ${getBarClass(expA.score)}" data-pct="${toPercent(expA.score)}"></div></div><div class="breakdown-score">${toPercent(expA.score)}%</div><div class="breakdown-desc">Relevance and depth of your work history relative to what this role demands</div></div>` : ''}
                        ${eduA.score !== undefined ? `<div class="breakdown-item"><div class="breakdown-label">Education</div><div class="breakdown-bar-container"><div class="breakdown-bar-fill ${getBarClass(eduA.score)}" data-pct="${toPercent(eduA.score)}"></div></div><div class="breakdown-score">${toPercent(eduA.score)}%</div><div class="breakdown-desc">Degree level, field of study, and certification alignment with stated requirements</div></div>` : ''}
                    </div>
                    ${skillGapNote ? `<div class="skill-gap-note"><i class="fas fa-info-circle"></i> ${escapeHtml(skillGapNote)}</div>` : ''}
                    ${missingCerts.length ? `<div class="section-subtitle" style="margin-top:0.75rem">Missing Certifications</div><ul class="content-list">${missingCerts.slice(0, 4).map(c => `<li><i class="fas fa-certificate orange"></i><span>${escapeHtml(String(c))}</span></li>`).join('')}</ul>` : ''}`;
                })()}

                ${(() => {
                    const pa = prefAnalysis || {};
                    const salaryF = pa.salary_fit || {};
                    const workF = pa.work_arrangement_fit || {};
                    const sizeF = pa.company_size_fit || {};
                    const locF = pa.location_fit || {};
                    if (!salaryF.score && !workF.score && !sizeF.score && !locF.score) return '';
                    const salaryUnknown = (salaryF.assessment || '').toUpperCase() === 'UNKNOWN';
                    return `<div class="section-subtitle">Preference Fit</div><div class="breakdown-grid">
                        ${salaryF.score !== undefined ? `<div class="breakdown-item"><div class="breakdown-label">Salary</div>${salaryUnknown ? `<div class="breakdown-na">N/A — salary not listed in posting</div>` : `<div class="breakdown-bar-container"><div class="breakdown-bar-fill ${getBarClass(salaryF.score)}" data-pct="${toPercent(salaryF.score)}"></div></div><div class="breakdown-score">${toPercent(salaryF.score)}%</div>`}<div class="breakdown-desc">Whether the offered compensation aligns with your desired salary range</div></div>` : ''}
                        ${workF.score !== undefined ? `<div class="breakdown-item"><div class="breakdown-label">Work Type</div><div class="breakdown-bar-container"><div class="breakdown-bar-fill ${getBarClass(workF.score)}" data-pct="${toPercent(workF.score)}"></div></div><div class="breakdown-score">${toPercent(workF.score)}%</div><div class="breakdown-desc">Remote, hybrid, or on-site arrangement vs. your stated preference</div></div>` : ''}
                        ${sizeF.score !== undefined ? `<div class="breakdown-item"><div class="breakdown-label">Company Size</div><div class="breakdown-bar-container"><div class="breakdown-bar-fill ${getBarClass(sizeF.score)}" data-pct="${toPercent(sizeF.score)}"></div></div><div class="breakdown-score">${toPercent(sizeF.score)}%</div><div class="breakdown-desc">Startup vs. enterprise environment fit based on your preferred company scale</div></div>` : ''}
                        ${locF.score !== undefined ? `<div class="breakdown-item"><div class="breakdown-label">Location</div><div class="breakdown-bar-container"><div class="breakdown-bar-fill ${getBarClass(locF.score)}" data-pct="${toPercent(locF.score)}"></div></div><div class="breakdown-score">${toPercent(locF.score)}%</div><div class="breakdown-desc">Geographic match — considers same city, metro-area proximity, and commute viability</div></div>` : ''}
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
                        <div class="percentile-track"><div class="percentile-fill" data-pct="${Math.min(percentile, 100)}"></div><div class="percentile-marker" data-pct="${Math.min(percentile, 100)}"></div></div>
                        <div class="percentile-scale"><span>0</span><span>50</span><span>100</span></div>
                    </div>` : ''}
                    ${uvp ? `<div class="uvp-box"><div class="uvp-label"><i class="fas fa-fingerprint"></i> Your Unique Value</div><div class="uvp-text">${escapeHtml(uvp)}</div></div>` : ''}
                    ${strengthsVsTypical.length ? `<div class="vs-typical"><div class="vs-label green"><i class="fas fa-arrow-up"></i> Edge over typical applicants</div><ul class="content-list">${strengthsVsTypical.slice(0, 3).map(s => `<li><i class="fas fa-check green"></i><span>${escapeHtml(String(s))}</span></li>`).join('')}</ul></div>` : ''}
                    ${weaknessesVsTypical.length ? `<div class="vs-typical"><div class="vs-label orange"><i class="fas fa-arrow-down"></i> Where typical applicants have more</div><ul class="content-list">${weaknessesVsTypical.slice(0, 3).map(w => `<li><i class="fas fa-arrow-down orange"></i><span>${escapeHtml(String(w))}</span></li>`).join('')}</ul></div>` : ''}
                </div>` : ''}

                ${strengths.length ? `<div class="section-subtitle">Your Strengths</div><ul class="content-list">${strengths.slice(0, 5).map(s => `<li><i class="fas fa-star green"></i><span><strong>${escapeHtml(s.strength || String(s))}</strong>${s.evidence ? ` — ${escapeHtml(s.evidence)}` : ''}</span></li>`).join('')}</ul>` : ''}
                ${gaps.length ? `<div class="section-subtitle">Areas to Address</div><ul class="content-list">${gaps.slice(0, 5).map(g => `<li><i class="fas fa-exclamation-triangle orange"></i><span><strong>${escapeHtml(g.gap || String(g))}</strong>${g.mitigation_strategy ? `<div class="mitigation-tip"><i class="fas fa-lightbulb"></i> ${escapeHtml(g.mitigation_strategy)}</div>` : ''}</span></li>`).join('')}</ul>` : ''}

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
                const h = /** @type {HTMLElement} */ (el);
                const p = h.dataset['pct'];
                if (p !== undefined) h.style.width = p + '%';
            });
            const marker = /** @type {HTMLElement|null} */ (fcEl.querySelector('.percentile-marker[data-pct]'));
            if (marker) marker.style.left = marker.dataset['pct'] + '%';
        }

        // ========== SUB-PANE 3: STRATEGY ==========
        let strategyHtml = '';

        // Application Strategy fields
        const talkingPoints = ensureArray(appStrategy.key_talking_points);
        const coverLetterAngle = appStrategy.cover_letter_angle || '';
        const addressConcerns = ensureArray(appStrategy.address_these_concerns);
        const resumeTips = ensureArray(appStrategy.resume_optimization_tips);
        const interviewPrep = ensureArray(appStrategy.interview_preparation);
        const networkingSuggestions = appStrategy.networking_suggestions || '';

        // Risk Assessment — correct field names from the agent schema
        const candidateRisks = ensureArray(riskAssessment.candidate_risks);
        const roleRisks = ensureArray(riskAssessment.role_risks);
        const yellowFlagsForCandidate = ensureArray(riskAssessment.yellow_flags_for_candidate);

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
                        ${addressConcerns.slice(0, 4).map(c => {
                            const concern = typeof c === 'object' ? (c.concern || c.issue || String(c)) : String(c);
                            const how = typeof c === 'object' ? (c.how_to_address || '') : '';
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
                        ${interviewPrep.slice(0, 5).map(q => {
                            const question = typeof q === 'object' ? (q.likely_question || String(q)) : String(q);
                            const strategy = typeof q === 'object' ? (q.suggested_answer_strategy || '') : '';
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
                        ${candidateRisks.slice(0, 4).map(r => {
                            const risk = typeof r === 'object' ? (r.risk || String(r)) : String(r);
                            const mit = typeof r === 'object' ? (r.mitigation || '') : '';
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
                        ${roleRisks.slice(0, 3).map(r => {
                            const risk = typeof r === 'object' ? (r.risk || String(r)) : String(r);
                            const consideration = typeof r === 'object' ? (r.consideration || '') : '';
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
        const jobLocation = [job.job_city, job.job_state, job.job_country].filter(Boolean).join(', ');

        // Salary display (reuse already-computed header value or rebuild)
        /** @type {Record<string,string>} */
        const _currencySymbols = { USD: '$', EUR: '€', GBP: '£', CAD: 'CA$', AUD: 'AU$', NZD: 'NZ$', CHF: 'CHF ', JPY: '¥', CNY: '¥', INR: '₹', BRL: 'R$', MXN: 'MX$', SGD: 'S$', HKD: 'HK$', SEK: 'kr', NOK: 'kr', DKK: 'kr' };
        const _currSymbol = (/** @type {string} */ code) => _currencySymbols[(code || '').toUpperCase()] || (code ? code + '\u00a0' : '$');
        let jdSalaryDisplay = '';
        if (job.salary_range && typeof job.salary_range === 'object') {
            if (job.salary_range.min || job.salary_range.max) {
                const curr = _currSymbol(job.salary_range.currency);
                const mn = job.salary_range.min ? `${curr}${(job.salary_range.min / 1000).toFixed(0)}K` : '';
                const mx = job.salary_range.max ? `${curr}${(job.salary_range.max / 1000).toFixed(0)}K` : '';
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
        const requiredSkillsArr = ensureArray(job.required_skills).map(s =>
            typeof s === 'object' ? (s.skill || s.name || '') : String(s)).filter(Boolean);
        const atsKeywordsArr = ensureArray(job.ats_keywords).map(s =>
            typeof s === 'object' ? (s.skill || s.name || '') : String(s)).filter(Boolean);

        let jobDetailsHtml = '';

        // ── Section 1: At a Glance ──────────────────────────────────
        const hasGlance = jobLocation || workArrangement || jdSalaryDisplay || employmentType ||
            yearsRequired || educationReqs || industry || roleClass || visaText ||
            securityRequired || travelPref || postedDate || deadline;

        if (hasGlance) {
            const educLabel = (() => {
                if (!educationReqs) return '';
                if (typeof educationReqs === 'object') {
                    if (educationReqs.required === false) return '';
                    const deg = (educationReqs.degree || '').trim();
                    const field = (educationReqs.field || '').trim();
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
                        ${workArrangement ? `<div class="jd-glance-item"><div class="jd-glance-icon"><i class="fas fa-laptop-house"></i></div><div class="jd-glance-body"><div class="jd-glance-label">Work Style</div><div class="jd-glance-value">${escapeHtml(toTitleCase(workArrangement))}</div></div></div>` : ''}
                        ${jdSalaryDisplay ? `<div class="jd-glance-item"><div class="jd-glance-icon"><i class="fas fa-dollar-sign"></i></div><div class="jd-glance-body"><div class="jd-glance-label">Salary</div><div class="jd-glance-value">${escapeHtml(jdSalaryDisplay)}</div></div></div>` : ''}
                        ${employmentType ? `<div class="jd-glance-item"><div class="jd-glance-icon"><i class="fas fa-clock"></i></div><div class="jd-glance-body"><div class="jd-glance-label">Employment</div><div class="jd-glance-value">${escapeHtml(toTitleCase(employmentType))}</div></div></div>` : ''}
                        ${yearsRequired ? `<div class="jd-glance-item"><div class="jd-glance-icon"><i class="fas fa-hourglass-half"></i></div><div class="jd-glance-body"><div class="jd-glance-label">Experience</div><div class="jd-glance-value">${escapeHtml(String(yearsRequired))}+ years</div></div></div>` : ''}
                        ${educLabel ? `<div class="jd-glance-item"><div class="jd-glance-icon"><i class="fas fa-graduation-cap"></i></div><div class="jd-glance-body"><div class="jd-glance-label">Education</div><div class="jd-glance-value">${educLabel}</div></div></div>` : ''}
                        ${industry ? `<div class="jd-glance-item"><div class="jd-glance-icon"><i class="fas fa-industry"></i></div><div class="jd-glance-body"><div class="jd-glance-label">Industry</div><div class="jd-glance-value">${escapeHtml(industry)}</div></div></div>` : ''}
                        ${roleClass ? `<div class="jd-glance-item"><div class="jd-glance-icon"><i class="fas fa-sitemap"></i></div><div class="jd-glance-body"><div class="jd-glance-label">Role Type</div><div class="jd-glance-value">${escapeHtml(roleClass)}</div></div></div>` : ''}
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
                    ${teamInfo ? `<div class="team-context-box"><p>${escapeHtml(teamInfo)}</p></div>` : ''}
                    ${reportingTo ? `<div class="reports-to-row"><i class="fas fa-level-up-alt"></i><span><strong>Reports to:</strong> ${escapeHtml(reportingTo)}</span></div>` : ''}
                </div>`;
        }

        // ── Section 3: What You'll Do ───────────────────────────────
        if (responsibilities.length) {
            jobDetailsHtml += `
                <div class="content-section">
                    <h2 class="section-title"><i class="fas fa-tasks"></i> What You'll Do</h2>
                    <ul class="content-list resp-list">
                        ${responsibilities.map(r => {
                            const line =
                                typeof r === 'object' && r !== null
                                    ? String(r.text ?? r.duty ?? r.responsibility ?? '')
                                    : String(r);
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
                        ${qualifications.map(q => `<li><i class="fas fa-check green"></i><span>${escapeHtml(String(typeof q === 'object' ? q.qualification || q.requirement : q))}</span></li>`).join('')}
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
                        ${preferredQuals.map(q => `<li><i class="fas fa-plus-circle orange"></i><span>${escapeHtml(String(typeof q === 'object' ? q.qualification || q.requirement : q))}</span></li>`).join('')}
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
                    <div class="tags-grid">${languageReqs.map(l => `<span class="tag">${escapeHtml(String(typeof l === 'object' ? `${l.language || l.name}${l.proficiency ? ` (${l.proficiency})` : ''}` : l))}</span>`).join('')}</div>
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

    /**
     * @param {any} cover
     * @param {any} [job]
     */
    function renderCoverLetter(cover, job) {
        const letter = cover.content || cover.cover_letter_text || cover.letter || cover.cover_letter || '';

        const coverEl = document.getElementById('coverContent');
        if (!coverEl) return;
        if (!letter) {
            coverEl.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-envelope empty-state-icon"></i>
                    <p class="empty-state-title">Cover Letter</p>
                    <p class="empty-state-desc">Generate a tailored cover letter based on the job requirements and your profile.</p>
                    ${currentSessionId ? `<button class="regen-btn" id="generateCoverBtn">
                        <span class="spinner"></span>
                        <span class="btn-text">Generate Cover Letter</span>
                    </button>` : ''}
                </div>
            `;
            const genCoverBtn = /** @type {HTMLButtonElement|null} */ (document.getElementById('generateCoverBtn'));
            if (genCoverBtn) genCoverBtn.addEventListener('click', () => generateSingle('cover', genCoverBtn));
            return;
        }

        const wordCount = letter.trim().split(/\s+/).filter(Boolean).length;
        const jobTitle = job ? (job.job_title || '').replace(/\s*[-–—].*$/, '').trim() : '';
        const companyName =
            job && !isPlaceholderCompanyName(job.company_name) ? String(job.company_name).trim() : '';
        const headerParts = [jobTitle, companyName].filter(Boolean);
        const headerLabel = headerParts.length ? headerParts.join(' · ') : 'Cover Letter';

        const generatedAt = cover.generated_at
            ? new Date(cover.generated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
            : '';

        coverEl.innerHTML = `
            <div class="cover-letter-wrapper">
                <div class="cover-letter-box">
                    <div class="cover-letter-body" id="coverLetterText"></div>
                    <div class="cover-letter-box-footer">
                        <div class="cl-footer-meta">
                            <span><i class="fas fa-align-left"></i> ${wordCount} words</span>
                            ${generatedAt ? `<span><i class="fas fa-clock"></i> Generated ${escapeHtml(generatedAt)}</span>` : ''}
                        </div>
                        <div class="cl-footer-actions">
                            <button class="cl-copy-btn" data-action="copy-cover" aria-label="Copy cover letter">
                                <i class="fas fa-copy"></i> Copy
                            </button>
                            <button class="cl-copy-btn regen-btn" data-action="regen-cover" aria-label="Regenerate cover letter">
                                <span class="spinner"></span>
                                <span class="btn-text"><i class="fas fa-sync-alt"></i> Regenerate</span>
                            </button>
                        </div>
                    </div>
                </div>
            </div>`;
        const cltEl = document.getElementById('coverLetterText');
        if (cltEl) cltEl.textContent = decodeEntities(letter);
    }

    /** @param {any} resume */
    function renderResumeTips(resume) {
        const advice = resume.comprehensive_advice || resume;
        const quickWins = ensureArray(advice.quick_wins || resume.quick_wins);
        const strategic = advice.strategic_assessment || resume.strategic_assessment || {};
        const skills = advice.skills_section || resume.skills_section || {};
        const profSummary = advice.professional_summary || resume.professional_summary || {};
        const atsOpt = advice.ats_optimization || resume.ats_optimization || {};
        const expOpt = advice.experience_optimization || resume.experience_optimization || {};
        const redFlags = ensureArray(advice.red_flags_to_fix || resume.red_flags_to_fix);
        const finalChecklistRaw = advice.final_checklist || resume.final_checklist;
        const checklistItems = ensureArray(finalChecklistRaw?.before_submitting || finalChecklistRaw);
        const fileFormat = finalChecklistRaw?.file_format || '';
        const fileNaming = finalChecklistRaw?.file_naming || '';

        const mustInclude = ensureArray(skills.must_include_skills);
        const skillsToAdd = ensureArray(skills.skills_to_add);
        const skillsToRemove = ensureArray(skills.skills_to_remove_or_deprioritize);
        const missingKeywords = ensureArray(atsOpt.critical_keywords_missing);
        const formatRecs = ensureArray(atsOpt.format_recommendations);
        const sectionOrder = ensureArray(atsOpt.section_order_recommendation);
        const rolesToHighlight = ensureArray(expOpt.roles_to_highlight);
        const rolesToMinimize = ensureArray(expOpt.roles_to_minimize);

        const subTabsEl = /** @type {HTMLElement|null} */ (document.querySelector('.sub-tabs[data-parent="resume"]'));

        if (!resume || Object.keys(resume).length === 0 || resume.error) {
            if (subTabsEl) subTabsEl.style.display = 'none';
            document.querySelectorAll('#pane-resume .sub-pane').forEach(p => p.classList.remove('active'));
            const overviewPane = document.getElementById('sub-resume-overview');
            if (overviewPane) {
                overviewPane.classList.add('active');
                const resumeErrMsg = resume?.error_message || '';
                overviewPane.innerHTML = resumeErrMsg
                    ? `<div class="empty-state"><i class="fas fa-file-alt"></i><p>${escapeHtml(resumeErrMsg)}</p></div>`
                    : `<div class="empty-state">
                    <i class="fas fa-file-alt empty-state-icon"></i>
                    <p class="empty-state-title">Resume Tips</p>
                    <p class="empty-state-desc">Get targeted resume improvements, ATS keyword optimization, and formatting advice for this specific role.</p>
                    ${currentSessionId ? `<button class="regen-btn" id="generateResumeBtn">
                        <span class="spinner"></span>
                        <span class="btn-text">Generate Resume Tips</span>
                    </button>` : ''}
                </div>`;
                const genBtn2 = /** @type {HTMLButtonElement|null} */ (document.getElementById('generateResumeBtn'));
                if (genBtn2) genBtn2.addEventListener('click', () => generateSingle('resume', genBtn2));
            }
            return;
        }

        if (subTabsEl) subTabsEl.style.display = '';

        // ── Helper: extract level token (HIGH/MEDIUM/LOW) from a string ──
        /**
         * @param {string} str
         * @returns {{ level: string, levelText: string, note: string }}
         */
        function extractLevel(str) {
            const m = str.match(/^(HIGH|MEDIUM|LOW|STRONG|MODERATE)/i);
            if (!m) return { level: 'medium', levelText: str, note: '' };
            return {
                level: m[1].toLowerCase(),
                levelText: m[1].toUpperCase(),
                note: str.slice(m[0].length).replace(/^\s*[-–—]\s*/, '').trim()
            };
        }

        // ── Sub-pane 1: Overview ────────────────────────────────────
        let overviewHtml = '';

        if (Object.keys(strategic).length > 0) {
            if (strategic.ats_pass_likelihood || strategic.interview_likelihood) {
                overviewHtml += `<div class="resume-score-cards">`;
                if (strategic.ats_pass_likelihood) {
                    const a = extractLevel(String(strategic.ats_pass_likelihood));
                    overviewHtml += `<div class="resume-score-card ${a.level}">
                        <div class="resume-score-icon-circle ${a.level}"><i class="fas fa-robot"></i></div>
                        <div class="resume-score-label">ATS Pass Rate</div>
                        <div class="resume-score-value ${a.level}">${escapeHtml(a.levelText)}</div>
                        ${a.note ? `<div class="resume-score-note">${escapeHtml(a.note)}</div>` : ''}
                    </div>`;
                }
                if (strategic.interview_likelihood) {
                    const iv = extractLevel(String(strategic.interview_likelihood));
                    overviewHtml += `<div class="resume-score-card ${iv.level}">
                        <div class="resume-score-icon-circle ${iv.level}"><i class="fas fa-user-tie"></i></div>
                        <div class="resume-score-label">Interview Likelihood</div>
                        <div class="resume-score-value ${iv.level}">${escapeHtml(iv.levelText)}</div>
                        ${iv.note ? `<div class="resume-score-note">${escapeHtml(iv.note)}</div>` : ''}
                    </div>`;
                }
                overviewHtml += `</div>`;
            }
            if (strategic.current_competitiveness) {
                overviewHtml += `<p class="resume-flat-text">${escapeHtml(strategic.current_competitiveness)}</p>`;
            }
            if (strategic.biggest_opportunity) {
                overviewHtml += `<div class="resume-flat-callout tip"><i class="fas fa-lightbulb"></i> <strong>Biggest Opportunity:</strong> ${escapeHtml(strategic.biggest_opportunity)}</div>`;
            }
            if (strategic.biggest_risk) {
                overviewHtml += `<div class="resume-flat-callout warn"><i class="fas fa-exclamation-triangle"></i> <strong>Main Risk:</strong> ${escapeHtml(strategic.biggest_risk)}</div>`;
            }
        }

        if (quickWins.length) {
            overviewHtml += `<div class="section-title" style="margin-top:1.5rem"><i class="fas fa-bolt"></i> Quick Wins</div>`;
            overviewHtml += quickWins.slice(0, 5).map(w => {
                const action = escapeHtml(String(w.action || w));
                const impact = w.impact ? `<span class="resume-flat-badge sm ${escapeHtml(w.impact.toLowerCase())}">${escapeHtml(w.impact)}</span>` : '';
                return `<div class="quick-win">
                    <div class="quick-win-icon"><i class="fas fa-check"></i></div>
                    <div class="quick-win-text" style="flex:1">${action}</div>
                    ${impact ? `<div style="display:flex;align-items:center;flex-shrink:0">${impact}</div>` : ''}
                </div>`;
            }).join('');
        }

        if (redFlags.length) {
            overviewHtml += `<div class="section-title" style="margin-top:1.5rem"><i class="fas fa-exclamation-circle"></i> Fix Before Applying</div>`;
            overviewHtml += redFlags.slice(0, 4).map(r => {
                const issue        = escapeHtml(String(typeof r === 'object' ? r.issue || r.flag || r : r));
                const currentState = typeof r === 'object' ? r.current_state || '' : '';
                const fix          = typeof r === 'object' ? r.recommended_fix || '' : '';
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

        const hasExpStrategy = expOpt.prioritization_strategy || expOpt.experience_gap_strategy || rolesToMinimize.length;
        if (hasExpStrategy) {
            expHtml += `<div class="section-title"><i class="fas fa-chart-line"></i> Experience Strategy</div>`;
            if (expOpt.prioritization_strategy) {
                expHtml += `<div class="resume-exp-strategy-box">
                    <div class="resume-exp-strategy-label"><i class="fas fa-bullseye"></i> What to Emphasize</div>
                    <p>${escapeHtml(expOpt.prioritization_strategy)}</p>
                </div>`;
            }
            if (expOpt.experience_gap_strategy) {
                expHtml += `<div class="resume-exp-strategy-box gap">
                    <div class="resume-exp-strategy-label"><i class="fas fa-link"></i> Bridging the Gap</div>
                    <p>${escapeHtml(expOpt.experience_gap_strategy)}</p>
                </div>`;
            }
            if (rolesToMinimize.length) {
                expHtml += `<div class="resume-flat-label" style="margin-top:0.75rem">De-emphasize These Roles</div>
                <div class="resume-flat-tags">${rolesToMinimize.slice(0, 4).map(r => `<span class="resume-flat-tag muted">${escapeHtml(String(r))}</span>`).join('')}</div>`;
            }
        }

        if (rolesToHighlight.length) {
            expHtml += `<div class="section-title" style="margin-top:1.5rem"><i class="fas fa-pencil-alt"></i> Bullet Rewrites by Role</div>`;
            expHtml += rolesToHighlight.map(role => {
                const roleTitle   = escapeHtml(role.role || role.title || '');
                const company     = escapeHtml(role.company || '');
                const whyRelevant = role.why_relevant ? escapeHtml(role.why_relevant) : '';
                const bullets     = ensureArray(role.bullet_point_suggestions);
                const kws         = ensureArray(role.keywords_to_add);
                if (!bullets.length) return '';
                return `<div class="resume-role-block">
                    <div class="resume-role-header">
                        <div class="resume-role-title">${roleTitle}${company ? `<span class="resume-role-company"> @ ${company}</span>` : ''}</div>
                        ${whyRelevant ? `<div class="resume-role-why"><i class="fas fa-info-circle"></i> ${whyRelevant}</div>` : ''}
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
            kwHtml += `<div class="resume-flat-tags">${mustInclude.slice(0, 8).map(s => {
                const skill  = typeof s === 'object' ? s.skill : s;
                const reason = typeof s === 'object' ? s.reason || '' : '';
                return `<span class="resume-flat-tag" title="${escapeHtml(reason)}">${escapeHtml(String(skill))}</span>`;
            }).join('')}</div>`;
        }

        if (missingKeywords.length) {
            kwHtml += `<div class="section-title" style="margin-top:1.5rem"><i class="fas fa-search"></i> Missing Keywords</div>`;
            kwHtml += missingKeywords.slice(0, 6).map(k => {
                const keyword    = escapeHtml(String(typeof k === 'object' ? k.keyword : k));
                const importance = typeof k === 'object' ? (k.importance || '') : '';
                const whereToAdd = typeof k === 'object' ? (k.where_to_add || '') : '';
                return `<div class="resume-flat-row"><span class="resume-flat-row-text"><strong>${keyword}</strong>${whereToAdd ? ` &mdash; <span class="resume-flat-muted">add to ${escapeHtml(whereToAdd)}</span>` : ''}</span>${importance ? `<span class="resume-flat-badge sm ${escapeHtml(importance.toLowerCase())}">${escapeHtml(importance)}</span>` : ''}</div>`;
            }).join('');
        }

        if (atsOpt.keyword_density_issues) {
            kwHtml += `<div class="resume-flat-callout neutral" style="margin-top:0.75rem"><i class="fas fa-balance-scale"></i> <strong>Keyword Density:</strong> ${escapeHtml(atsOpt.keyword_density_issues)}</div>`;
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

        if (profSummary.recommended_summary || profSummary.current_assessment) {
            summaryHtml += `<div class="section-title"><i class="fas fa-align-left"></i> Professional Summary</div>`;
            if (profSummary.current_assessment) {
                summaryHtml += `<div class="resume-flat-callout warn sm"><i class="fas fa-exclamation-circle"></i> <strong>Current issue:</strong> ${escapeHtml(profSummary.current_assessment)}</div>`;
            }
            if (profSummary.recommended_summary) {
                summaryHtml += `<div class="resume-summary-box">
                    <div class="resume-summary-body">${escapeHtml(profSummary.recommended_summary)}</div>
                    <div class="resume-summary-footer">
                        <button class="cl-copy-btn" data-action="copy-text" data-copy-text="${escapeHtml(profSummary.recommended_summary)}" aria-label="Copy recommended summary">
                            <i class="fas fa-copy"></i> Copy
                        </button>
                    </div>
                </div>`;
            }
            const keyElements = ensureArray(profSummary.key_elements_included);
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

    /**
     * @param {HTMLElement} btn
     * @param {string} text
     */
    function copyText(btn, text) {
        const onSuccess = () => {
            btn.innerHTML = '<i class="fas fa-check"></i> Copied!';
            setTimeout(() => { btn.innerHTML = '<i class="fas fa-copy"></i> Copy'; }, 2000);
        };
        // @ts-ignore
        const app = window.app;
        if (app && typeof app.copyToClipboard === 'function') {
            app.copyToClipboard(text).then(onSuccess).catch(() => {});
            return;
        }
        navigator.clipboard.writeText(text).then(onSuccess);
    }

    /**
     * @param {any} company
     * @param {any} job
     */
    function renderInterviewPrep(company, job) {
        const prep = company.interview_preparation;
        if (prep && !prep.parse_error) {
            renderRichInterviewPrep(prep);
            return;
        }

        // Fall back to basic company research data
        const interviewProcess = ensureArray(company.typical_interview_process);
        const commonQuestions = ensureArray(company.common_questions || company.interview_intelligence?.common_questions);
        const tips = ensureArray(company.preparation_tips || company.talking_points_for_interview || company.interview_intelligence?.tips_for_success);
        const assessmentMethods = ensureArray(company.assessment_methods || company.interview_intelligence?.assessment_methods);
        const interviewFormat = company.interview_format || company.interview_intelligence?.interview_format;
        const timeline = company.hiring_timeline || company.interview_intelligence?.timeline;
        const whatTheyLookFor = ensureArray(company.interview_intelligence?.what_they_look_for);
        const questionsToAsk = ensureArray(company.questions_to_ask_them);

        const hasBasicData = interviewProcess.length || commonQuestions.length || tips.length;

        if (!hasBasicData) {
            // Hide sub-tabs, show empty state in first sub-pane
            const subTabsEl = /** @type {HTMLElement|null} */ (document.querySelector('.sub-tabs[data-parent="interview"]'));
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
        const subTabsBar = /** @type {HTMLElement|null} */ (document.querySelector('.sub-tabs[data-parent="interview"]'));
        if (subTabsBar) subTabsBar.style.display = '';

        // Process sub-pane — banner first, then basic content
        const basicNoticeBanner = currentSessionId ? `
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

    /** @param {any} prep */
    function renderRichInterviewPrep(prep) {
        // Ensure sub-tabs are visible
        const subTabsBar = /** @type {HTMLElement|null} */ (document.querySelector('.sub-tabs[data-parent="interview"]'));
        if (subTabsBar) subTabsBar.style.display = '';

        // ── Schema detection: support both new (v2) and old (v1) schemas ──
        // New schema: prep.interview_process, prep.predicted_questions, etc.
        // Old schema: prep.interview_stages, prep.likely_questions, etc.
        const isNewSchema = !!(prep.interview_process || prep.predicted_questions || prep.questions_for_them);

        const iProcess   = prep.interview_process   || {};
        const predicted  = prep.predicted_questions || {};
        const qForThem   = prep.questions_for_them  || {};
        const concerns   = ensureArray(prep.addressing_concerns);
        const qrc        = prep.quick_reference_card || {};
        const logistics  = prep.logistics || {};
        // day_before_checklist (new) → preparation_checklist (old) → day_of_tips (old)
        const dayBefore  = ensureArray(prep.day_before_checklist || prep.preparation_checklist || prep.day_of_tips);
        const boostrs    = ensureArray(prep.confidence_boosters);

        // New schema rounds; fall back to old interview_stages
        const rounds         = ensureArray(iProcess.typical_rounds || prep.interview_stages);

        // New predicted_questions buckets; for old schema, bucket by category field
        const oldQuestions   = ensureArray(prep.likely_questions);
        /** @param {string} cat */
        const oldByCategory  = (cat) => oldQuestions.filter(q => (q.category || '').toLowerCase() === cat.toLowerCase());

        const behaviorals    = ensureArray(predicted.behavioral)    .length ? ensureArray(predicted.behavioral)    : oldByCategory('behavioral');
        const technicals     = ensureArray(predicted.technical)     .length ? ensureArray(predicted.technical)     : oldByCategory('technical');
        const roleSpecific   = ensureArray(predicted.role_specific) .length ? ensureArray(predicted.role_specific) : oldByCategory('role-specific');
        const companySpecific= ensureArray(predicted.company_specific).length ? ensureArray(predicted.company_specific) : oldByCategory('company-specific');
        // Any old questions not matched by category (situational, general, etc.)
        const otherOldQs     = isNewSchema ? [] : oldQuestions.filter(q => {
            const c = (q.category || '').toLowerCase();
            return !['behavioral','technical','role-specific','company-specific'].includes(c);
        });

        // ── Category badge helper ───────────────────────────────────
        /** @param {string} cat */
        const catBadge = (cat) => {
            const colors = /** @type {Record<string,string>} */ ({
                behavioral: '#667eea', technical: '#f093fb',
                'role-specific': '#4facfe', 'company-specific': '#43e97b', situational: '#fda085'
            });
            const c = escapeHtml(colors[cat.toLowerCase()] || '#8b8fa8');
            return `<span class="iv-cat-badge" style="background:${c}22;color:${c}">${escapeHtml(cat.toUpperCase())}</span>`;
        };

        // ===== SUB-PANE 1: PROCESS ==============================================
        let processHtml = '';

        // Overview bar — new fields fall back to old-schema equivalents
        const totalTimeline   = iProcess.total_timeline       || prep.hiring_timeline   || '';
        const prepTime        = iProcess.preparation_time_needed || '';
        const formatPred      = iProcess.format_prediction    || prep.interview_format  || '';
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
            processHtml += rounds.map((r, i) => `
                <div class="iv-round-card">
                    <div class="iv-round-header">
                        <div class="iv-round-num">${i + 1}</div>
                        <div class="iv-round-meta">
                            <div class="iv-round-type">${escapeHtml(String(r.type || r.stage || `Round ${i + 1}`))}</div>
                            <div class="iv-round-details">
                                ${r.duration ? `<span><i class="fas fa-clock"></i> ${escapeHtml(String(r.duration))}</span>` : ''}
                                ${r.with ? `<span><i class="fas fa-user"></i> ${escapeHtml(String(r.with))}</span>` : ''}
                            </div>
                        </div>
                    </div>
                    ${(r.focus || r.description) ? `<div class="iv-round-focus"><strong>Focus:</strong> ${escapeHtml(String(r.focus || r.description))}</div>` : ''}
                    ${r.tips ? `<div class="iv-round-tip"><i class="fas fa-lightbulb"></i> ${Array.isArray(r.tips) ? ensureArray(r.tips).map(t => escapeHtml(String(t))).join(' · ') : escapeHtml(String(r.tips))}</div>` : ''}
                </div>`).join('');
            processHtml += `</div>`;
        }

        if (!processHtml) processHtml = '<div class="empty-state"><i class="fas fa-route"></i><p>No process information available.</p></div>';
        const richSipEl = document.getElementById('sub-interview-process');
        if (richSipEl) richSipEl.innerHTML = processHtml;

        // ===== SUB-PANE 2: QUESTIONS ============================================
        let questionsHtml = '';

        // ── Shared question card renderer (works for both schema versions) ──
        /** @param {Record<string,any>} q @param {string} badgeCat */
        const renderQuestionCard = (q, badgeCat) => {
            // new schema: q.why_likely | old schema: q.why_they_ask
            const whyText  = q.why_likely || q.why_they_ask || '';
            // new schema: specific sub-fields | old schema: q.suggested_approach
            const approach = q.preparation_approach || q.answer_strategy || q.personalized_answer || q.suggested_approach || '';
            const story    = q.your_story || {};
            const keyPts   = ensureArray(q.key_points_to_cover);
            const followUps= ensureArray(q.follow_up_questions);
            const incorpExp= q.incorporate_your_experience || '';
            return `<div class="iv-question-card">
                ${catBadge(badgeCat)}
                <div class="iv-question-text">${escapeHtml(q.question || String(q))}</div>
                ${whyText  ? `<div class="iv-question-why"><em>Why they ask:</em> ${escapeHtml(whyText)}</div>` : ''}
                ${(story.use_this_experience || story.situation) ? `
                <div class="iv-star-block">
                    <div class="iv-star-label"><i class="fas fa-star"></i> Your Answer — STAR Framework</div>
                    ${story.use_this_experience ? `<div class="iv-star-source"><i class="fas fa-briefcase"></i> Use your experience at: <strong>${escapeHtml(story.use_this_experience)}</strong></div>` : ''}
                    <div class="iv-star-grid">
                        ${story.situation ? `<div class="iv-star-item"><div class="iv-star-letter">S</div><div><div class="iv-star-name">Situation</div><div class="iv-star-desc">${escapeHtml(story.situation)}</div></div></div>` : ''}
                        ${story.task ?      `<div class="iv-star-item"><div class="iv-star-letter">T</div><div><div class="iv-star-name">Task</div><div class="iv-star-desc">${escapeHtml(story.task)}</div></div></div>` : ''}
                        ${story.action ?    `<div class="iv-star-item"><div class="iv-star-letter">A</div><div><div class="iv-star-name">Action</div><div class="iv-star-desc">${escapeHtml(story.action)}</div></div></div>` : ''}
                        ${story.result ?    `<div class="iv-star-item"><div class="iv-star-letter iv-star-r">R</div><div><div class="iv-star-name">Result</div><div class="iv-star-desc">${escapeHtml(story.result)}</div></div></div>` : ''}
                    </div>
                </div>` : ''}
                ${approach  ? `<div class="iv-tech-approach"><i class="fas fa-lightbulb"></i> ${escapeHtml(approach)}</div>` : ''}
                ${keyPts.length ? `<div class="iv-key-points"><div class="iv-key-points-label">Cover these points:</div><ul>${keyPts.map(p => `<li>${escapeHtml(String(p))}</li>`).join('')}</ul></div>` : ''}
                ${followUps.length ? `<div class="iv-followups"><i class="fas fa-angle-double-right"></i> <strong>Likely follow-ups:</strong> ${followUps.map(f => `<span class="iv-followup-tag">${escapeHtml(String(f))}</span>`).join('')}</div>` : ''}
                ${q.what_they_evaluate ? `<div class="iv-question-evaluate"><i class="fas fa-search"></i> <strong>They're evaluating:</strong> ${escapeHtml(q.what_they_evaluate)}</div>` : ''}
                ${incorpExp ? `<div class="iv-question-evaluate"><i class="fas fa-briefcase"></i> Reference: <strong>${escapeHtml(incorpExp)}</strong></div>` : ''}
                ${q.danger_zone ? `<div class="iv-danger-zone"><i class="fas fa-ban"></i> <strong>Don't say:</strong> ${escapeHtml(q.danger_zone)}</div>` : ''}
            </div>`;
        };

        /** @param {string} icon @param {string} label @param {boolean} [first] */
        const qSectionHeader = (icon, label, first = false) =>
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
            questionsHtml += otherOldQs.map(q => renderQuestionCard(q, q.category || 'general')).join('');
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
                questionsHtml += items.slice(0, 3).map(q => {
                    const question = escapeHtml(q.question || String(q));
                    const why      = escapeHtml(q.why_good || q.why || '');
                    const listen   = escapeHtml(q.listen_for || q.what_youre_checking || '');
                    const when     = escapeHtml(q.when_to_ask || '');
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
            questionsHtml += oldQToAsk.map(q => {
                const question = escapeHtml(q.question || String(q));
                const why  = escapeHtml(q.why || '');
                const when = escapeHtml(q.when || '');
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
        const hasQrc = qrc.elevator_pitch || qrc.three_key_selling_points?.length || qrc.weakness_answer || qrc.why_this_company || qrc.closing_statement || qrc.salary_discussion;
        if (hasQrc) {
            prepHtml += `<h3 class="section-subtitle"><i class="fas fa-id-card"></i> Quick Reference Card</h3>
            <div class="iv-qrc-block">
                <div class="iv-qrc-header"><i class="fas fa-bolt"></i> Review this 5 minutes before walking in</div>`;

            if (qrc.elevator_pitch) {
                prepHtml += `<div class="iv-qrc-section">
                    <div class="iv-qrc-label">Your 30-Second Pitch</div>
                    <div class="iv-qrc-pitch">${escapeHtml(qrc.elevator_pitch)}</div>
                </div>`;
            }
            const selling = ensureArray(qrc.three_key_selling_points);
            if (selling.length) {
                prepHtml += `<div class="iv-qrc-section">
                    <div class="iv-qrc-label">3 Key Selling Points</div>
                    ${selling.map((p, i) => `<div class="iv-selling-point"><span class="iv-sp-num">${i + 1}</span><span>${escapeHtml(String(p))}</span></div>`).join('')}
                </div>`;
            }
            if (qrc.weakness_answer) {
                const wa = qrc.weakness_answer;
                prepHtml += `<div class="iv-qrc-section">
                    <div class="iv-qrc-label">Weakness Answer</div>
                    <div class="iv-weakness-block">
                        ${wa.weakness     ? `<div class="iv-weakness-row"><strong>Weakness:</strong> ${escapeHtml(wa.weakness)}</div>` : ''}
                        ${wa.how_addressing ? `<div class="iv-weakness-row"><strong>What I'm doing:</strong> ${escapeHtml(wa.how_addressing)}</div>` : ''}
                        ${wa.example      ? `<div class="iv-weakness-row"><strong>Example:</strong> ${escapeHtml(wa.example)}</div>` : ''}
                    </div>
                </div>`;
            }
            if (qrc.why_this_company) {
                prepHtml += `<div class="iv-qrc-section">
                    <div class="iv-qrc-label">Why This Company</div>
                    <div class="iv-qrc-text">${escapeHtml(qrc.why_this_company)}</div>
                </div>`;
            }
            if (qrc.salary_discussion) {
                const sal = qrc.salary_discussion;
                prepHtml += `<div class="iv-qrc-section">
                    <div class="iv-qrc-label"><i class="fas fa-dollar-sign"></i> Salary Discussion</div>
                    ${sal.anchor_range    ? `<div class="iv-weakness-row"><strong>Range to anchor:</strong> <span class="iv-salary-range">${escapeHtml(sal.anchor_range)}</span></div>` : ''}
                    ${sal.strategy        ? `<div class="iv-weakness-row"><strong>Strategy:</strong> ${escapeHtml(sal.strategy)}</div>` : ''}
                    ${sal.deflection_phrase ? `<div class="iv-weakness-row"><strong>If asked too early:</strong> <em>"${escapeHtml(sal.deflection_phrase)}"</em></div>` : ''}
                </div>`;
            }
            if (qrc.closing_statement) {
                prepHtml += `<div class="iv-qrc-section">
                    <div class="iv-qrc-label">Strong Closing</div>
                    <div class="iv-qrc-text iv-closing">"${escapeHtml(qrc.closing_statement)}"</div>
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
                prepHtml += oldGaps.map(g => `<div class="iv-concern-card">
                    <div class="iv-concern-issue"><i class="fas fa-exclamation-triangle"></i> ${escapeHtml(g.gap || String(g))}</div>
                    ${g.strategy ? `<div class="iv-concern-counter"><i class="fas fa-reply"></i> <strong>Strategy:</strong> ${escapeHtml(g.strategy)}</div>` : ''}
                </div>`).join('');
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
            prepHtml += concerns.map(c => {
                const tps   = ensureArray(c.talking_points);
                const proof = ensureArray(c.proof_points_from_experience);
                return `<div class="iv-concern-card">
                    <div class="iv-concern-issue"><i class="fas fa-exclamation-triangle"></i> ${escapeHtml(c.concern || '')}</div>
                    ${c.why_its_a_concern ? `<div class="iv-concern-why"><em>What they think:</em> ${escapeHtml(c.why_its_a_concern)}</div>` : ''}
                    ${c.your_counter_narrative ? `<div class="iv-concern-counter"><i class="fas fa-reply"></i> <strong>Your reframe:</strong> ${escapeHtml(c.your_counter_narrative)}</div>` : ''}
                    ${tps.length ? `<div class="iv-concern-points"><strong>Talking points:</strong><ul>${tps.map(p => `<li>${escapeHtml(String(p))}</li>`).join('')}</ul></div>` : ''}
                    ${proof.length ? `<div class="iv-concern-proof"><strong>Proof from your background:</strong><ul>${proof.map(p => `<li><i class="fas fa-check green"></i> ${escapeHtml(String(p))}</li>`).join('')}</ul></div>` : ''}
                    ${c.when_to_bring_up ? `<div class="iv-concern-when"><i class="fas fa-clock"></i> <strong>When to raise it:</strong> ${escapeHtml(c.when_to_bring_up)}</div>` : ''}
                </div>`;
            }).join('');
        }

        // ── Logistics ─────────────────────────────────────────────────
        const logItems = ensureArray(logistics.what_to_bring);
        const virtTips = ensureArray(logistics.virtual_interview_tips);
        const postInter = logistics.post_interview || {};
        const hasLogistics = logistics.dress_code || logItems.length || virtTips.length || postInter.thank_you_note;
        if (hasLogistics) {
            prepHtml += `<h3 class="section-subtitle"><i class="fas fa-map-signs"></i> Logistics</h3>
            <div class="iv-logistics-grid">`;
            if (logistics.dress_code) {
                prepHtml += `<div class="iv-logistics-item"><i class="fas fa-tshirt"></i><div><div class="iv-logistics-label">Dress Code</div><div>${escapeHtml(logistics.dress_code)}</div></div></div>`;
            }
            if (logistics.timing?.arrive) {
                prepHtml += `<div class="iv-logistics-item"><i class="fas fa-clock"></i><div><div class="iv-logistics-label">Arrive</div><div>${escapeHtml(logistics.timing.arrive)}</div></div></div>`;
            }
            if (logistics.timing?.expected_duration) {
                prepHtml += `<div class="iv-logistics-item"><i class="fas fa-hourglass-half"></i><div><div class="iv-logistics-label">Block</div><div>${escapeHtml(logistics.timing.expected_duration)}</div></div></div>`;
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
            if (postInter.thank_you_note || postInter.follow_up_timeline) {
                prepHtml += `<div class="iv-logistics-label" style="margin:0.75rem 0 0.35rem">After the Interview</div>
                <div class="iv-post-interview">`;
                if (postInter.thank_you_note) prepHtml += `<div class="iv-logistics-item"><i class="fas fa-envelope"></i><div><div class="iv-logistics-label">Thank-you note</div><div>${escapeHtml(postInter.thank_you_note)}</div></div></div>`;
                if (postInter.follow_up_timeline) prepHtml += `<div class="iv-logistics-item"><i class="fas fa-calendar-check"></i><div><div class="iv-logistics-label">Follow up</div><div>${escapeHtml(postInter.follow_up_timeline)}</div></div></div>`;
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

    /** @param {string|null|undefined} tabId */
    function switchTab(tabId) {
        document.querySelectorAll('.page-tab').forEach(btn => {
            btn.classList.toggle('active', /** @type {HTMLElement} */ (btn).dataset.tab === tabId);
        });
        document.querySelectorAll('.tab-pane').forEach(pane => {
            pane.classList.toggle('active', pane.id === `pane-${tabId}`);
        });
    }

    /**
     * @param {string|null|undefined} parentId
     * @param {string|null|undefined} subTabId
     */
    function switchSubTab(parentId, subTabId) {
        const parent = document.getElementById(`pane-${parentId}`) || document.getElementById(`${parentId}Content`);
        if (!parent) return;
        parent.querySelectorAll(`.sub-tabs[data-parent="${parentId}"] .sub-tab`).forEach(btn => {
            btn.classList.toggle('active', /** @type {HTMLElement} */ (btn).dataset.subtab === subTabId);
        });
        parent.querySelectorAll('.sub-pane').forEach(pane => {
            pane.classList.toggle('active', pane.id === `sub-${parentId}-${subTabId}`);
        });
    }

    function copyCoverLetter() {
        const text = document.getElementById('coverLetterText')?.innerText || '';
        // @ts-ignore
        const app = window.app;
        if (app && typeof app.copyToClipboard === 'function') { app.copyToClipboard(text); return; }
        navigator.clipboard.writeText(text).then(() => showToast('Copied to clipboard!')).catch(() => showToast('Failed to copy', 'error'));
    }

    /**
     * @param {string} message
     * @param {string} [type]
     */
    function showToast(message, type = 'success') {
        // @ts-ignore
        const app = window.app;
        const notifType = type === 'success' ? 'success' : 'error';
        // @ts-ignore
        const bus = window.eventBus; const busEvents = window.BusEvents;
        if (bus && busEvents) {
            /** @type {Record<string,string>} */ const evtMap = { success: busEvents.NOTIFY_SUCCESS, error: busEvents.NOTIFY_ERROR };
            bus.emit(evtMap[notifType] ?? busEvents.NOTIFY_INFO, { message });
        }
        if (app && typeof app.showNotification === 'function') {
            app.showNotification(message, notifType);
            return;
        }
        // Fallback: inline toast
        const toast = document.createElement('div');
        toast.style.cssText = `position:fixed;bottom:20px;right:20px;background:${type === 'success' ? '#10b981' : '#ef4444'};color:white;padding:.75rem 1.25rem;border-radius:8px;z-index:9999;font-size:.85rem;animation:slideIn .3s ease`;
        toast.textContent = message;
        document.body.appendChild(toast);
        if (_toastOutTimer !== null) clearTimeout(_toastOutTimer);
        if (_toastRemoveTimer !== null) clearTimeout(_toastRemoveTimer);
        _toastOutTimer = window.setTimeout(() => {
            toast.style.animation = 'slideOut .3s ease';
            _toastRemoveTimer = window.setTimeout(() => { toast.remove(); _toastRemoveTimer = null; }, 300);
            _toastOutTimer = null;
        }, 2000);
    }

    /** @param {string|null} paneId */
    function copyTabContent(paneId) {
        if (!paneId) return;
        const pane = document.getElementById(paneId);
        if (!pane) return;
        const subPanes = pane.querySelectorAll('.sub-pane');
        let text = '';
        if (subPanes.length > 0) {
            subPanes.forEach(sp => {
                const content = /** @type {HTMLElement} */ (sp).innerText || sp.textContent || '';
                if (content.trim()) text += content.trim() + '\n\n';
            });
        } else {
            text = pane.innerText || pane.textContent || '';
        }
        // @ts-ignore
        const app = window.app;
        if (app && typeof app.copyToClipboard === 'function') { app.copyToClipboard(text.trim()); return; }
        navigator.clipboard.writeText(text.trim()).then(() => showToast('Copied to clipboard!')).catch(() => showToast('Failed to copy', 'error'));
    }

    /**
     * Generate only cover letter or only resume tips (for analysis_complete sessions).
     * @param {'cover'|'resume'} which
     * @param {HTMLButtonElement} btn
     */
    async function generateSingle(which, btn) {
        if (!currentSessionId) return;
        btn.disabled = true;
        btn.classList.add('loading');
        const endpoint = which === 'cover'
            ? `${API_BASE}/workflow/regenerate-cover-letter/${currentSessionId}`
            : `${API_BASE}/workflow/regenerate-resume/${currentSessionId}`;
        try {
            const res = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${getAuthToken()}`, 'Content-Type': 'application/json' },
            });
            if (res.status === 429) { showToast('Rate limit reached. Try again in a few minutes.', 'error'); return; }
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(/** @type {any} */ (errData).message || /** @type {any} */ (errData).detail || 'Generation failed');
            }
            showToast(which === 'cover' ? 'Cover letter generated!' : 'Resume tips generated!');
            loadApplicationData();
        } catch (error) {
            const err = /** @type {Error} */ (error);
            showToast(err.message || 'Generation failed', 'error');
            btn.disabled = false;
            btn.classList.remove('loading');
        }
    }

    async function continueWorkflow() {
        if (!currentSessionId || _continuingWorkflow) return;
        _continuingWorkflow = true;

        const btn = /** @type {HTMLButtonElement|null} */ (document.getElementById('continueWorkflowBtn'));
        if (btn) { btn.disabled = true; btn.classList.add('loading'); }

        showToast('Running full analysis — this may take a minute…');

        try {
            const res = await fetch(`${API_BASE}/workflow/continue/${currentSessionId}`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${getAuthToken()}`,
                    'Content-Type': 'application/json',
                },
            });

            if (res.status === 429) {
                showToast('Rate limit reached. Please try again later.', 'error');
                return;
            }
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(/** @type {any} */ (errData).message || /** @type {any} */ (errData).detail || 'Failed to continue workflow');
            }

            // Poll until completed or failed
            let attempts = 0;
            const maxAttempts = 40;
            const poll = async () => {
                if (attempts >= maxAttempts) {
                    showToast('Analysis is taking longer than expected. Refresh the page to check progress.', 'error');
                    _continuingWorkflow = false;
                    return;
                }
                attempts++;
                try {
                    const sr = await fetch(`${API_BASE}/workflow/status/${currentSessionId}`, {
                        headers: { 'Authorization': `Bearer ${getAuthToken()}` }
                    });
                    if (sr.ok) {
                        const sd = await sr.json();
                        if (sd.status === 'completed' || sd.status === 'analysis_complete') {
                            showToast('Analysis complete!');
                            _continuingWorkflow = false;
                            workflowStatus = sd.status;
                            loadApplicationData();
                            return;
                        }
                        if (sd.status === 'failed') {
                            showToast('Analysis failed. Please try again.', 'error');
                            _continuingWorkflow = false;
                            if (btn) { btn.disabled = false; btn.classList.remove('loading'); }
                            return;
                        }
                    }
                } catch (_) { /* ignore poll errors */ }
                if (_processingRefreshTimer !== null) clearTimeout(_processingRefreshTimer);
                _processingRefreshTimer = window.setTimeout(poll, 3000);
            };
            if (_processingRefreshTimer !== null) clearTimeout(_processingRefreshTimer);
            _processingRefreshTimer = window.setTimeout(poll, 3000);

        } catch (error) {
            const err = /** @type {Error} */ (error);
            showToast(err.message || 'Failed to continue workflow', 'error');
            _continuingWorkflow = false;
            if (btn) { btn.disabled = false; btn.classList.remove('loading'); }
        }
    }

    /** @param {HTMLButtonElement} btn */
    async function regenerateCoverLetter(btn) {
        if (!currentSessionId || _regeneratingCoverLetter) return;
        _regeneratingCoverLetter = true;

        btn.classList.add('loading');
        btn.disabled = true;

        try {
            const res = await fetch(`${API_BASE}/workflow/regenerate-cover-letter/${currentSessionId}`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${getAuthToken()}`,
                    'Content-Type': 'application/json',
                },
            });

            if (res.status === 429) {
                showToast('Rate limit reached. Try again in a few minutes.', 'error');
                return;
            }

            if (!res.ok) throw new Error('Failed to regenerate');

            const data = await res.json();
            const newLetter = data.cover_letter?.content || data.cover_letter?.cover_letter_text || '';

            if (newLetter) {
                const cltEl = document.getElementById('coverLetterText');
                if (cltEl) cltEl.textContent = newLetter;
                if (applicationData) (/** @type {Record<string,unknown>} */ (applicationData))['cover_letter'] = data.cover_letter;
                showToast('Cover letter regenerated!');
            } else {
                showToast('Regeneration returned empty result', 'error');
            }
        } catch (error) {
            console.error('Error regenerating:', error);
            showToast('Failed to regenerate cover letter', 'error');
        } finally {
            btn.classList.remove('loading');
            btn.disabled = false;
            _regeneratingCoverLetter = false;
        }
    }

    /** @param {HTMLButtonElement} btn */
    async function regenerateResume(btn) {
        if (!currentSessionId || _regeneratingResume) return;
        _regeneratingResume = true;

        btn.classList.add('loading');
        btn.disabled = true;

        try {
            const res = await fetch(`${API_BASE}/workflow/regenerate-resume/${currentSessionId}`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${getAuthToken()}`,
                    'Content-Type': 'application/json',
                },
            });

            if (res.status === 429) {
                showToast('Rate limit reached. Try again in a few minutes.', 'error');
                return;
            }

            if (!res.ok) throw new Error('Failed to regenerate');

            const data = await res.json();
            if (applicationData) (/** @type {Record<string,unknown>} */ (applicationData))['resume_recommendations'] = data.result;
            renderResumeTips(data.result);
            showToast('Resume advice regenerated!');
        } catch (error) {
            console.error('Error regenerating resume:', error);
            showToast('Failed to regenerate resume advice', 'error');
        } finally {
            btn.classList.remove('loading');
            btn.disabled = false;
            _regeneratingResume = false;
        }
    }

    async function generateDocuments() {
        if (!currentSessionId) return;
        const btns = /** @type {NodeListOf<HTMLButtonElement>} */ (document.querySelectorAll('#generateDocsBtn, #generateDocsBtnResume'));
        btns.forEach(b => { b.disabled = true; b.classList.add('loading'); });
        try {
            const res = await fetch(`${API_BASE}/workflow/generate-documents/${currentSessionId}`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${getAuthToken()}`, 'Content-Type': 'application/json' },
            });
            if (res.status === 429) { showToast('Rate limit reached. Try again in a few minutes.', 'error'); return; }
            if (!res.ok) throw new Error('Failed to start generation');
            showToast('Generating your documents… this may take a minute.');
            // Poll for completion
            let attempts = 0;
            const poll = async () => {
                if (attempts++ > 40) { showToast('Generation is taking longer than expected. Refresh the page to check.', 'error'); return; }
                await new Promise(r => setTimeout(r, 3000));
                try {
                    const r2 = await fetch(`${API_BASE}/workflow/status/${currentSessionId}`, { headers: { 'Authorization': `Bearer ${getAuthToken()}` } });
                    if (!r2.ok) { setTimeout(poll, 3000); return; }
                    const status = await r2.json();
                    if (status.status === 'completed') {
                        await loadApplicationData();
                        showToast('Documents generated!');
                    } else if (status.status === 'failed') {
                        showToast('Generation failed. Please try again.', 'error');
                        btns.forEach(b => { b.disabled = false; b.classList.remove('loading'); });
                    } else {
                        setTimeout(poll, 3000);
                    }
                } catch { setTimeout(poll, 3000); }
            };
            setTimeout(poll, 3000);
        } catch (error) {
            console.error('Error generating documents:', error);
            showToast('Failed to start generation', 'error');
            btns.forEach(b => { b.disabled = false; b.classList.remove('loading'); });
        }
    }

    /** @param {HTMLButtonElement} btn */
    async function generateInterviewPrep(btn) {
        if (!currentSessionId || _generatingInterviewPrep) return;
        _generatingInterviewPrep = true;

        btn.classList.add('loading');
        btn.disabled = true;

        try {
            const res = await fetch(`${API_BASE}/workflow/generate-interview-prep/${currentSessionId}`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${getAuthToken()}`,
                    'Content-Type': 'application/json',
                },
            });

            if (res.status === 429) {
                showToast('Rate limit reached. Try again in a few minutes.', 'error');
                return;
            }

            if (!res.ok) throw new Error('Failed to generate');

            const data = await res.json();
            // Store the interview prep in local data
            if (applicationData) {
                const appD = /** @type {Record<string,any>} */ (applicationData);
                if (!appD['company_research']) appD['company_research'] = {};
                appD['company_research']['interview_preparation'] = data.result;
            }
            renderRichInterviewPrep(data.result);
            showToast('Interview preparation generated!');
        } catch (error) {
            console.error('Error generating interview prep:', error);
            showToast('Failed to generate interview preparation', 'error');
        } finally {
            btn.classList.remove('loading');
            btn.disabled = false;
            _generatingInterviewPrep = false;
        }
    }

    // Add animation keyframes
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        @keyframes slideOut {
            from { transform: translateX(0); opacity: 1; }
            to { transform: translateX(100%); opacity: 0; }
        }
    `;
    document.head.appendChild(style);

    // ---- Public API: functions accessible from inline HTML handlers ----
    // @ts-ignore
    window.copyCoverLetter = copyCoverLetter;
    // @ts-ignore
    window.copyTabContent = copyTabContent;
    // @ts-ignore
    window.copyText = copyText;
    // @ts-ignore
    window.regenerateCoverLetter = regenerateCoverLetter;
    // @ts-ignore
    window.regenerateResume = regenerateResume;
    // @ts-ignore
    window.generateInterviewPrep = generateInterviewPrep;

}());
