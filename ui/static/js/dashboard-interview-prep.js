(function () {
    'use strict';

    const API_BASE = (window.APP_CONFIG && window.APP_CONFIG.apiBase) || '/api/v1';

    /** @type {string|null} */
    let sessionId = null;
    /** @type {Record<string,unknown>|null} */
    let interviewPrepData = null;
    /** @type {AbortController|null} */
    let pollAbortController = null;
    /** @type {WebSocket|null} */
    let ws = null;
    /** @type {number|null} */
    let wsReconnectTimer = null;
    let wsReconnectAttempts = 0;
    const WS_MAX_RECONNECT_ATTEMPTS = 8;
    const WS_RECONNECT_BASE_MS = 1000;

    /** @returns {boolean} */
    function requireLogin() {
        // @ts-ignore
        const authenticated = window.app ? window.app.isAuthenticated() : !!(localStorage.getItem('access_token') || localStorage.getItem('authToken'));
        if (!authenticated) {
            window.location.href = (window.APP_CONFIG && window.APP_CONFIG.loginUrl) || '/auth/login';
            return false;
        }
        return true;
    }

    document.addEventListener('DOMContentLoaded', async function () {
        if (!requireLogin()) return;
        if (typeof window.syncProfileCompletionFromApi !== 'function' || !(await window.syncProfileCompletionFromApi())) return;

        const pathParts = window.location.pathname.split('/');
        sessionId = pathParts[pathParts.length - 1];
        if (sessionId) loadInterviewPrep();
        else showError('No session ID provided');

        // Delegated handler for data-action buttons (replaces inline onclick attributes)
        document.addEventListener('click', function (e) {
            const el = /** @type {HTMLElement} */ (e.target);
            const actionEl = /** @type {HTMLElement|null} */ (el.closest('[data-action]'));
            if (!actionEl) return;
            switch (actionEl.dataset['action']) {
                case 'generate-interview-prep': generateInterviewPrep(); break;
                case 'regenerate-interview-prep': regenerateInterviewPrep(); break;
                case 'print-page': window.print(); break;
            }
        });
    });

    window.addEventListener('beforeunload', function () {
        if (pollAbortController) pollAbortController.abort();
        disconnectWs();
    });

    function getAuthHeaders() {
        const token = localStorage.getItem('access_token') || localStorage.getItem('authToken');
        return { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };
    }

    async function loadInterviewPrep() {
        showState('loading');
        try {
            const response = await fetch(`${API_BASE}/interview-prep/${sessionId}`, { headers: getAuthHeaders() });
            if (!response.ok) {
                if (response.status === 404) { showError('Session not found'); return; }
                throw new Error('Failed to load interview prep');
            }
            const data = await response.json();
            if (data.has_interview_prep && data.interview_prep) {
                interviewPrepData = data.interview_prep;
                await loadJobInfo();
                renderInterviewPrep();
                showState('content');
            } else {
                showState('generate');
            }
        } catch (error) {
            const err = /** @type {Error} */ (error);
            console.error('Error loading interview prep:', err);
            showError('Failed to load interview prep: ' + err.message);
        }
    }

    async function loadJobInfo() {
        try {
            const response = await fetch(`${API_BASE}/workflow/results/${sessionId}`, { headers: getAuthHeaders() });
            if (response.ok) {
                const data = await response.json();
                if (data.job_analysis) {
                    const titleEl = document.getElementById('jobTitle');
                    const compEl  = document.getElementById('companyName');
                    if (titleEl) titleEl.textContent = `Interview Prep: ${data.job_analysis.job_title || 'Position'}`;
                    if (compEl)  compEl.textContent  = data.job_analysis.company_name || '';
                }
            }
        } catch (error) { console.error('Error loading job info:', error); }
    }

    function getAuthToken() {
        // @ts-ignore
        return (window.app && typeof window.app.getAuthToken === 'function')
            ? window.app.getAuthToken()
            : (localStorage.getItem('access_token') || localStorage.getItem('authToken'));
    }

    function connectWs() {
        if (!sessionId) return;
        const token = getAuthToken();
        if (!token || typeof WebSocket === 'undefined') return;

        disconnectWs();

        const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
        const url = `${proto}://${window.location.host}/api/v1/ws/workflow/${encodeURIComponent(sessionId)}?token=${encodeURIComponent(token)}`;

        try {
            ws = new WebSocket(url);
        } catch (e) {
            console.warn('WebSocket connection failed, falling back to polling:', e);
            return;
        }

        ws.onopen = function () {
            wsReconnectAttempts = 0;
        };

        ws.onmessage = function (event) {
            try {
                const msg = /** @type {Record<string,any>} */ (JSON.parse(event.data));
                handleWsMessage(msg);
            } catch (e) {
                console.error('Failed to parse WebSocket message:', e);
            }
        };

        ws.onerror = function () {
            console.warn('Interview prep WebSocket error — polling fallback active');
        };

        ws.onclose = function (event) {
            ws = null;
            // Don't reconnect on intentional close (1000) or auth failure (1008/4001)
            const noRetry = event.code === 1000 || event.code === 1008 || event.code === 4001;
            if (!noRetry && wsReconnectAttempts < WS_MAX_RECONNECT_ATTEMPTS) {
                const delay = Math.min(WS_RECONNECT_BASE_MS * Math.pow(2, wsReconnectAttempts), 30000);
                wsReconnectAttempts++;
                wsReconnectTimer = setTimeout(connectWs, delay);
            }
        };
    }

    function disconnectWs() {
        if (wsReconnectTimer !== null) { clearTimeout(wsReconnectTimer); wsReconnectTimer = null; }
        if (ws) {
            try { ws.close(); } catch (e) { /* ignore */ }
            ws = null;
        }
    }

    /** @param {Record<string,any>} msg */
    function handleWsMessage(msg) {
        if (!msg || typeof msg.type !== 'string') return;
        switch (msg.type) {
            case 'interview_prep_complete':
                stopPolling();
                disconnectWs();
                loadInterviewPrep();
                break;
            case 'interview_prep_error':
                stopPolling();
                disconnectWs();
                showError('Generation failed. Please try again.');
                showState('generate');
                break;
            default:
                break;
        }
    }

    function stopPolling() {
        if (pollAbortController) { pollAbortController.abort(); pollAbortController = null; }
    }

    /**
     * Start a polling fallback that fires every 5 s (slower than before because WS covers
     * the fast path). Aborts itself once the prep appears or maxAttempts is reached.
     */
    function startPollingFallback() {
        stopPolling();
        pollAbortController = new AbortController();
        const signal = pollAbortController.signal;

        const maxAttempts = 60;
        let attempts = 0;
        /** @type {number} */
        let timeoutId = 0;

        const cancel = () => { clearTimeout(timeoutId); };
        signal.addEventListener('abort', cancel);

        const poll = async () => {
            if (signal.aborted) return;
            attempts++;
            try {
                const response = await fetch(`${API_BASE}/interview-prep/${sessionId}/status`, { headers: getAuthHeaders(), signal });
                if (signal.aborted) return;
                if (response.ok) {
                    const data = await response.json();
                    if (data.has_interview_prep) { stopPolling(); disconnectWs(); loadInterviewPrep(); return; }
                }
            } catch (err) {
                if (signal.aborted) return;
            }
            if (attempts < maxAttempts) { timeoutId = window.setTimeout(poll, 5000); }
            else { showError('Generation timed out. Please try again.'); showState('generate'); }
        };
        poll();
    }

    async function generateInterviewPrep() {
        showState('generating');
        // Open WebSocket before triggering the task so we don't miss the completion event
        connectWs();
        try {
            const response = await fetch(`${API_BASE}/interview-prep/${sessionId}/generate`, {
                method: 'POST', headers: getAuthHeaders()
            });
            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.message || errData.detail || 'Failed to generate interview prep');
            }
            // WS is primary; poll as fallback in case WS is unavailable
            startPollingFallback();
        } catch (error) {
            const err = /** @type {Error} */ (error);
            console.error('Error generating interview prep:', err);
            disconnectWs();
            stopPolling();
            showError('Failed to generate: ' + err.message);
            showState('generate');
        }
    }

    async function regenerateInterviewPrep() {
        const confirmed = await window.showConfirm({
            title: 'Regenerate Interview Prep',
            message: 'This will replace the existing content. Are you sure?',
            confirmText: 'Regenerate',
            type: 'warning',
        });
        if (!confirmed) return;
        showState('generating');
        connectWs();
        try {
            const response = await fetch(`${API_BASE}/interview-prep/${sessionId}/generate?regenerate=true`, {
                method: 'POST', headers: getAuthHeaders()
            });
            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.message || errData.detail || 'Failed to regenerate');
            }
            startPollingFallback();
        } catch (error) {
            const err = /** @type {Error} */ (error);
            console.error('Error regenerating:', err);
            disconnectWs();
            stopPolling();
            showError('Failed to regenerate: ' + err.message);
            showState('content');
        }
    }

    /** @param {string} state */
    function showState(state) {
        const set = /** @param {string} id @param {boolean} show */ (id, show) => {
            const el = /** @type {HTMLElement|null} */ (document.getElementById(id));
            if (el) el.style.display = show ? 'block' : 'none';
        };
        set('loadingState',    state === 'loading');
        set('generateState',   state === 'generate');
        set('generatingState', state === 'generating');
        set('mainContent',     state === 'content');
    }

    /** @param {string} message */
    function showError(message) {
        showState('generate');
        const container = document.getElementById('generateState')?.querySelector('.section-card');
        if (container) {
            container.innerHTML = `
                <div class="text-center py-5">
                    <i class="fas fa-exclamation-triangle fa-4x text-danger mb-4"></i>
                    <h3>Error</h3>
                    <p class="text-muted mb-4">${escapeHtml(message)}</p>
                    <a href="/dashboard" class="btn btn-primary"><i class="fas fa-arrow-left me-2"></i>Back to Dashboard</a>
                </div>`;
        }
    }

    function renderInterviewPrep() {
        if (!interviewPrepData) return;
        if (interviewPrepData['generated_at']) {
            const el = document.getElementById('generatedAt');
            if (el) el.textContent = new Date(/** @type {string} */ (interviewPrepData['generated_at'])).toLocaleString();
        }
        renderInterviewProcess();
        const pq = /** @type {Record<string,unknown[]>} */ (interviewPrepData['predicted_questions'] ?? {});
        renderQuestions('behavioral',     /** @type {Record<string,unknown>[]} */ (pq['behavioral']       ?? []));
        renderQuestions('technical',      /** @type {Record<string,unknown>[]} */ (pq['technical']        ?? []));
        renderQuestions('roleSpecific',   /** @type {Record<string,unknown>[]} */ (pq['role_specific']    ?? []));
        renderQuestions('companySpecific',/** @type {Record<string,unknown>[]} */ (pq['company_specific'] ?? []));
        renderConcerns();
        renderQuestionsToAsk();
        renderChecklist();
        renderLogistics();
        renderConfidenceBoosters();
        renderQuickReference();
    }

    function renderInterviewProcess() {
        const process = /** @type {Record<string,unknown>|undefined} */ (/** @type {Record<string,unknown>} */ (interviewPrepData ?? {})['interview_process']);
        const el = document.getElementById('interviewProcess');
        if (!process) { if (el) el.style.display = 'none'; return; }

        let html = '';
        if (process['total_timeline'] || process['format_prediction']) {
            html += `<div class="mb-4">
                ${process['total_timeline']     ? `<p><i class="fas fa-calendar-alt me-2 text-primary"></i><strong>Expected Timeline:</strong> ${escapeHtml(String(process['total_timeline']))}</p>` : ''}
                ${process['format_prediction']  ? `<p><i class="fas fa-video me-2 text-primary"></i><strong>Format:</strong> ${escapeHtml(String(process['format_prediction']))}</p>` : ''}
                ${process['preparation_time_needed'] ? `<p><i class="fas fa-hourglass-half me-2 text-primary"></i><strong>Prep Time Needed:</strong> ${escapeHtml(String(process['preparation_time_needed']))}</p>` : ''}
            </div>`;
        }
        const rounds = /** @type {Record<string,unknown>[]} */ (process['typical_rounds'] ?? []);
        if (rounds.length > 0) {
            html += `<div class="round-timeline">`;
            rounds.forEach((round, i) => {
                html += `<div class="round-item"><div class="round-content">
                    <div class="d-flex justify-content-between align-items-start mb-2">
                        <strong>Round ${round['round'] || i + 1}: ${escapeHtml(String(round['type'] || 'Interview'))}</strong>
                        <span class="badge bg-secondary">${escapeHtml(String(round['duration'] || ''))}</span>
                    </div>
                    <p class="mb-1 text-muted"><i class="fas fa-user me-1"></i>${escapeHtml(String(round['with'] || 'Interviewer'))}</p>
                    <p class="mb-1"><strong>Focus:</strong> ${escapeHtml(String(round['focus'] || ''))}</p>
                    ${round['tips'] ? `<p class="mb-0 text-success"><i class="fas fa-lightbulb me-1"></i>${escapeHtml(String(round['tips']))}</p>` : ''}
                </div></div>`;
            });
            html += `</div>`;
        }
        const contentEl = document.getElementById('processContent');
        if (contentEl) contentEl.innerHTML = html || "<p class='text-muted'>No interview process information available.</p>";
    }

    /**
     * @param {string} containerId
     * @param {Record<string,unknown>[]} questions
     */
    function renderQuestions(containerId, questions) {
        const container = document.getElementById(containerId);
        if (!container) return;
        if (!questions || questions.length === 0) {
            container.innerHTML = "<p class='text-muted'>No questions in this category.</p>"; return;
        }
        let html = '';
        questions.forEach(q => {
            html += `<div class="question-card">`;
            html += `<div class="question-text">${escapeHtml(String(q['question'] ?? ''))}</div>`;
            if (q['why_likely']) html += `<div class="question-meta"><i class="fas fa-info-circle me-1"></i>${escapeHtml(String(q['why_likely']))}</div>`;
            const story = /** @type {Record<string,unknown>} */ (q['your_story']);
            if (story) {
                html += `<div class="star-section"><div class="star-label">Your STAR Answer</div>`;
                if (story['use_this_experience']) html += `<p class="mb-2"><strong>Use:</strong> ${escapeHtml(String(story['use_this_experience']))}</p>`;
                if (story['situation']) html += `<p class="mb-1"><span class="badge bg-primary me-2">S</span>${escapeHtml(String(story['situation']))}</p>`;
                if (story['task'])     html += `<p class="mb-1"><span class="badge bg-primary me-2">T</span>${escapeHtml(String(story['task']))}</p>`;
                if (story['action'])   html += `<p class="mb-1"><span class="badge bg-primary me-2">A</span>${escapeHtml(String(story['action']))}</p>`;
                if (story['result'])   html += `<p class="mb-0"><span class="badge bg-primary me-2">R</span>${escapeHtml(String(story['result']))}</p>`;
                html += `</div>`;
            }
            if (q['preparation_approach']) {
                html += `<div class="star-section"><p class="mb-2"><strong>Preparation:</strong> ${escapeHtml(String(q['preparation_approach']))}</p>`;
                const kp = /** @type {string[]} */ (q['key_points_to_cover'] ?? []);
                if (kp.length > 0) { html += `<p class="mb-1"><strong>Key Points:</strong></p><ul class="mb-0">${kp.map(p=>`<li>${escapeHtml(p)}</li>`).join('')}</ul>`; }
                html += `</div>`;
            }
            if (q['answer_strategy'])    html += `<div class="star-section"><p class="mb-0"><strong>Strategy:</strong> ${escapeHtml(String(q['answer_strategy']))}</p></div>`;
            if (q['personalized_answer'])html += `<div class="star-section"><p class="mb-0"><strong>Your Answer:</strong> ${escapeHtml(String(q['personalized_answer']))}</p></div>`;
            if (q['what_they_evaluate']) html += `<div class="mt-2 text-muted small"><i class="fas fa-search me-1"></i>They're evaluating: ${escapeHtml(String(q['what_they_evaluate']))}</div>`;
            if (q['danger_zone']) {
                html += `<div class="danger-zone"><div class="danger-zone-label"><i class="fas fa-exclamation-triangle me-1"></i>Don't Say</div><div>${escapeHtml(String(q['danger_zone']))}</div></div>`;
            }
            html += `</div>`;
        });
        container.innerHTML = html;
    }

    function renderConcerns() {
        const concerns   = /** @type {Record<string,unknown>[]} */ (/** @type {Record<string,unknown>} */ (interviewPrepData ?? {})['addressing_concerns'] ?? []);
        const container  = document.getElementById('concernsContent');
        if (!container) return;
        if (concerns.length === 0) {
            container.innerHTML = `<div class="empty-state"><i class="fas fa-check-circle text-success"></i><p>No significant concerns identified. You're well-matched for this role!</p></div>`;
            return;
        }
        container.innerHTML = concerns.map(concern => {
            let html = `<div class="concern-card"><div class="concern-title"><i class="fas fa-exclamation-circle me-2"></i>${escapeHtml(String(concern['concern'] ?? ''))}</div>`;
            if (concern['why_its_a_concern'])    html += `<p class="text-muted mb-2"><strong>What they might think:</strong> ${escapeHtml(String(concern['why_its_a_concern']))}</p>`;
            if (concern['your_counter_narrative'])html += `<p class="mb-2"><strong>Your counter-narrative:</strong> ${escapeHtml(String(concern['your_counter_narrative']))}</p>`;
            const pts = /** @type {string[]} */ (concern['talking_points'] ?? []);
            if (pts.length > 0) html += `<div class="talking-point"><strong>Talking Points:</strong><ul class="mb-0 mt-1">${pts.map(p=>`<li>${escapeHtml(p)}</li>`).join('')}</ul></div>`;
            if (concern['when_to_bring_up']) html += `<p class="mt-2 mb-0 text-info"><i class="fas fa-clock me-1"></i><strong>When:</strong> ${escapeHtml(String(concern['when_to_bring_up']))}</p>`;
            return html + `</div>`;
        }).join('');
    }

    function renderQuestionsToAsk() {
        const questions = /** @type {Record<string,unknown[]>} */ (/** @type {Record<string,unknown>} */ (interviewPrepData ?? {})['questions_for_them'] ?? {});
        const container = document.getElementById('askContent');
        if (!container) return;
        const categories = [
            { key: 'for_recruiter',      title: 'For the Recruiter',       icon: 'fa-phone' },
            { key: 'for_hiring_manager', title: 'For the Hiring Manager',  icon: 'fa-user-tie' },
            { key: 'for_team_members',   title: 'For Team Members',        icon: 'fa-users' },
            { key: 'red_flag_questions', title: 'Red Flag Questions',      icon: 'fa-flag' }
        ];
        let html = '';
        categories.forEach(cat => {
            const qs = /** @type {Record<string,unknown>[]} */ (questions[cat.key] ?? []);
            if (qs.length > 0) {
                html += `<h6 class="mt-4 mb-3"><i class="fas ${cat.icon} me-2"></i>${cat.title}</h6>`;
                qs.forEach(q => {
                    html += `<div class="ask-question-card"><div class="fw-bold mb-2">"${escapeHtml(String(q['question'] ?? ''))}"</div>`;
                    if (q['why_good'])  html += `<p class="text-muted mb-1"><i class="fas fa-lightbulb me-1"></i>${escapeHtml(String(q['why_good']))}</p>`;
                    if (q['listen_for'])html += `<p class="mb-0 text-success"><i class="fas fa-ear-listen me-1"></i><strong>Listen for:</strong> ${escapeHtml(String(q['listen_for']))}</p>`;
                    if (q['when_to_ask'])html += `<p class="mb-0 text-info"><i class="fas fa-clock me-1"></i><strong>When:</strong> ${escapeHtml(String(q['when_to_ask']))}</p>`;
                    html += `</div>`;
                });
            }
        });
        container.innerHTML = html || "<p class='text-muted'>No questions to ask available.</p>";
    }

    function renderChecklist() {
        const checklist = /** @type {string[]} */ (/** @type {Record<string,unknown>} */ (interviewPrepData ?? {})['day_before_checklist'] ?? []);
        const container = document.getElementById('checklistContent');
        if (!container) return;
        if (checklist.length === 0) { container.innerHTML = "<p class='text-muted'>No checklist available.</p>"; return; }
        container.innerHTML = checklist.map(item => `<div class="checklist-item"><i class="fas fa-check-square"></i><span>${escapeHtml(item)}</span></div>`).join('');
    }

    function renderLogistics() {
        const logistics = /** @type {Record<string,unknown>} */ (/** @type {Record<string,unknown>} */ (interviewPrepData ?? {})['logistics'] ?? {});
        const container = document.getElementById('logisticsContent');
        if (!container) return;
        let html = '';
        if (logistics['dress_code']) html += `<div class="logistics-item"><div class="logistics-icon"><i class="fas fa-tshirt"></i></div><div><strong>Dress Code:</strong> ${escapeHtml(String(logistics['dress_code']))}</div></div>`;
        const timing = /** @type {Record<string,string>} */ (logistics['timing']);
        if (timing) {
            html += `<div class="logistics-item"><div class="logistics-icon"><i class="fas fa-clock"></i></div><div><strong>Arrive:</strong> ${escapeHtml(timing['arrive'] ?? '')}`;
            if (timing['expected_duration']) html += `<br><strong>Duration:</strong> ${escapeHtml(timing['expected_duration'])}`;
            html += `</div></div>`;
        }
        const bring = /** @type {string[]} */ (logistics['what_to_bring'] ?? []);
        if (bring.length > 0) html += `<div class="logistics-item"><div class="logistics-icon"><i class="fas fa-briefcase"></i></div><div><strong>Bring:</strong> ${bring.map(escapeHtml).join(', ')}</div></div>`;
        const vTips = /** @type {string[]} */ (logistics['virtual_interview_tips'] ?? []);
        if (vTips.length > 0) html += `<div class="logistics-item"><div class="logistics-icon"><i class="fas fa-video"></i></div><div><strong>Virtual Tips:</strong><ul class="mb-0 mt-1">${vTips.map(t=>`<li>${escapeHtml(t)}</li>`).join('')}</ul></div></div>`;
        const post = /** @type {Record<string,string>} */ (logistics['post_interview']);
        if (post) {
            html += `<div class="logistics-item"><div class="logistics-icon"><i class="fas fa-envelope"></i></div><div><strong>After:</strong> ${escapeHtml(post['thank_you_note'] ?? '')}`;
            if (post['follow_up_timeline']) html += `<br><strong>Follow up:</strong> ${escapeHtml(post['follow_up_timeline'])}`;
            html += `</div></div>`;
        }
        container.innerHTML = html || "<p class='text-muted'>No logistics information available.</p>";
    }

    function renderConfidenceBoosters() {
        const boosters = /** @type {string[]} */ (/** @type {Record<string,unknown>} */ (interviewPrepData ?? {})['confidence_boosters'] ?? []);
        const container = document.getElementById('confidenceContent');
        if (!container) return;
        if (boosters.length === 0) { container.innerHTML = "<p class='text-muted'>No confidence boosters available.</p>"; return; }
        container.innerHTML = boosters.map(b => `<div class="confidence-booster"><i class="fas fa-star me-2"></i>${escapeHtml(b)}</div>`).join('');
    }

    function renderQuickReference() {
        const ref = /** @type {Record<string,unknown>} */ (/** @type {Record<string,unknown>} */ (interviewPrepData ?? {})['quick_reference_card'] ?? {});
        const container = document.getElementById('referenceContent');
        if (!container) return;
        let html = '';
        if (ref['elevator_pitch']) html += `<div class="reference-item"><div class="reference-label">Elevator Pitch (30 sec)</div><div>${escapeHtml(String(ref['elevator_pitch']))}</div></div>`;
        const selling = /** @type {string[]} */ (ref['three_key_selling_points'] ?? []);
        if (selling.length > 0) html += `<div class="reference-item"><div class="reference-label">Your 3 Key Selling Points</div><ol class="mb-0">${selling.map(p=>`<li>${escapeHtml(p)}</li>`).join('')}</ol></div>`;
        const wa = /** @type {Record<string,string>} */ (ref['weakness_answer']);
        if (wa?.['weakness']) {
            html += `<div class="reference-item"><div class="reference-label">Weakness Answer</div><div><strong>${escapeHtml(wa['weakness'])}</strong>`;
            if (wa['how_addressing']) html += ` - ${escapeHtml(wa['how_addressing'])}`;
            html += `</div></div>`;
        }
        if (ref['why_this_company']) html += `<div class="reference-item"><div class="reference-label">Why This Company?</div><div>${escapeHtml(String(ref['why_this_company']))}</div></div>`;
        const sd = /** @type {Record<string,string>} */ (ref['salary_discussion']);
        if (sd?.['anchor_range']) {
            html += `<div class="reference-item"><div class="reference-label">Salary Discussion</div><div><strong>Target:</strong> ${escapeHtml(sd['anchor_range'])}`;
            if (sd['deflection_phrase']) html += `<br><strong>If asked early:</strong> "${escapeHtml(sd['deflection_phrase'])}"`;
            html += `</div></div>`;
        }
        if (ref['closing_statement']) html += `<div class="reference-item"><div class="reference-label">Closing Statement</div><div>${escapeHtml(String(ref['closing_statement']))}</div></div>`;
        container.innerHTML = html || "<p class='opacity-75'>No quick reference available.</p>";
    }

    /** @param {unknown} text */
    function escapeHtml(text) {
        if (!text) return '';
        // @ts-ignore
        const app = window.app;
        if (app && typeof app.escapeHtml === 'function') return app.escapeHtml(String(text));
        const div = document.createElement('div');
        div.textContent = String(text);
        return div.innerHTML;
    }

    // Public API
    // @ts-ignore
    window.generateInterviewPrep   = generateInterviewPrep;
    // @ts-ignore
    window.regenerateInterviewPrep = regenerateInterviewPrep;

}());
