/**
 * CV Optimization Loop — tab logic for the application detail page.
 *
 * Handles the "Optimize CV" 9th tab: start/poll/render the iterative
 * CV optimization loop. Requires BYOK (CFG_6001 if no key).
 *
 * State machine:
 *   NOT_STARTED → RUNNING (per-iteration WebSocket events) → COMPLETE | ERROR
 *
 * Expects DOM elements with IDs defined in application.html pane-optimize.
 */

(function () {
  'use strict';

  // =============================================================================
  // HELPERS (required in every page-level JS file per frontend-js-strict.mdc)
  // =============================================================================

  /**
   * @param {string|null|undefined} str
   * @returns {string}
   */
  function escapeHtml(str) {
    if (str == null) return '';
    const decoded = String(str)
      .replace(/&amp;/g, '&')
      .replace(/&#x27;/g, "'")
      .replace(/&#039;/g, "'")
      .replace(/&quot;/g, '"')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>');
    return decoded
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }

  /** Decode HTML entities for .textContent assignments (no re-encoding step) */
  function decodeEntities(str) {
    if (str == null) return '';
    return String(str)
      .replace(/&amp;/g, '&')
      .replace(/&#x27;/g, "'")
      .replace(/&#039;/g, "'")
      .replace(/&quot;/g, '"')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>');
  }

  /**
   * Robust clipboard write — tries navigator.clipboard first, falls back to execCommand.
   * @param {string} text
   * @param {string} [successMsg]
   */
  function _clipboardWrite(text, successMsg) {
    const msg = successMsg || 'Copied to clipboard!';
    function showSuccess() {
      if (typeof window.showToast === 'function') window.showToast(msg, 'success');
    }
    function fallback() {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.className = 'clipboard-offscreen';
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      try {
        document.execCommand('copy');
        showSuccess();
      } catch (e) {
        console.error('Clipboard fallback failed', e);
      }
      document.body.removeChild(ta);
    }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(showSuccess, fallback);
    } else {
      fallback();
    }
  }

  /** @returns {string} */
  function _getAuthToken() {
    return (window.app && typeof window.app.getAuthToken === 'function')
      ? window.app.getAuthToken()
      : (localStorage.getItem('access_token') || localStorage.getItem('authToken') || '');
  }

  // =============================================================================
  // MODULE STATE
  // =============================================================================

  /** @type {string|null} current session ID */
  let _sessionId = null;

  /** @type {'not_started'|'running'|'complete'|'error'} */
  let _state = 'not_started';

  /** @type {string} optimized CV text (for copy button) */
  let _optimizedCv = '';

  /** @type {string} cover letter text (for copy button) */
  let _coverLetter = '';

  /** whether the WebSocket listener has been registered */
  let _wsListenerAttached = false;

  // =============================================================================
  // DOM HELPERS
  // =============================================================================

  /** @param {string} id @returns {HTMLElement|null} */
  function _el(id) { return document.getElementById(id); }

  /** @param {HTMLElement|null} el @param {boolean} hidden */
  function _setHidden(el, hidden) {
    if (!el) return;
    if (hidden) {
      el.classList.add('is-hidden');
    } else {
      el.classList.remove('is-hidden');
    }
  }

  function _showSection(sectionId) {
    ['cvo-setup', 'cvo-progress', 'cvo-results', 'cvo-error'].forEach(id => {
      _setHidden(_el(id), id !== sectionId);
    });
  }

  // =============================================================================
  // INIT
  // =============================================================================

  /**
   * Initialize the CV Optimizer tab for a given session.
   * Called by application-detail.js when the "optimize" tab is activated.
   *
   * @param {string} sessionId
   */
  function initCvOptimizerTab(sessionId) {
    _sessionId = sessionId;
    _attachEventListeners();
    _attachWsListener();
    _loadCvOptimizationStatus();
  }

  // =============================================================================
  // EVENT DELEGATION
  // =============================================================================

  function _attachEventListeners() {
    const pane = _el('cvOptimizeContent');
    if (!pane) return;

    pane.addEventListener('click', function (e) {
      const target = /** @type {HTMLElement} */ (e.target);
      const actionEl = /** @type {HTMLElement|null} */ (target.closest('[data-action]'));
      if (!actionEl) return;

      const action = actionEl.getAttribute('data-action');
      if (action === 'startCvOptimization') _handleStart();
      else if (action === 'clearCvOptimization') _handleClear();
      else if (action === 'resetCvOptimization') _handleReset();
      else if (action === 'copyOptimizedCv') _clipboardWrite(_optimizedCv, 'Optimized CV copied!');
      else if (action === 'copyCvoCoverLetter') _clipboardWrite(_coverLetter, 'Cover letter copied!');
      else if (action === 'downloadOptimizedCvOdt') _handleDownloadOdt();
    });
  }

  // =============================================================================
  // WEBSOCKET
  // =============================================================================

  function _onWsEvent(/** @type {CustomEvent} */ e) {
    const msg = /** @type {Record<string,any>} */ (e.detail || {});
    const type = String(msg['type'] || '');
    const sessionId = String(msg['session_id'] || '');
    if (!_sessionId || sessionId !== _sessionId) return;

    if (type === 'cv_optimization_started') {
      _state = 'running';
      _showSection('cvo-progress');
    } else if (type === 'cv_optimization_iteration') {
      const d = msg['data'] || {};
      _updateProgressView(d['iteration'], d['score'], d['strengths'], d['gaps'], d['action_items']);
    } else if (type === 'cv_optimization_complete') {
      _state = 'complete';
      _fetchAndRenderResult();
    } else if (type === 'cv_optimization_error') {
      _state = 'error';
      const errMsg = ((msg['data'] || {})['error']) || 'An error occurred during optimization.';
      _showErrorView(errMsg);
    }
  }

  function _attachWsListener() {
    if (_wsListenerAttached) return;
    window.addEventListener('applypilot:ws', _onWsEvent);
    _wsListenerAttached = true;
  }

  // =============================================================================
  // API CALLS
  // =============================================================================

  async function _loadCvOptimizationStatus() {
    if (!_sessionId) return;

    try {
      const res = await fetch(`/api/v1/cv-optimizer/${encodeURIComponent(_sessionId)}/status`, {
        credentials: 'same-origin',
        headers: { 'Authorization': `Bearer ${_getAuthToken()}` },
      });

      if (!res.ok) {
        if (res.status === 401) return; // Not logged in — ignore silently
        return;
      }

      const data = await res.json();

      if (data.is_running) {
        _state = 'running';
        _showSection('cvo-progress');
        return;
      }

      if (data.has_result) {
        _state = 'complete';
        _fetchAndRenderResult();
        return;
      }

      _state = 'not_started';
      _showSection('cvo-setup');
    } catch (err) {
      console.error('[cv-optimizer] status fetch failed', err);
      _showSection('cvo-setup');
    }
  }

  async function _fetchAndRenderResult() {
    if (!_sessionId) return;

    try {
      const res = await fetch(`/api/v1/cv-optimizer/${encodeURIComponent(_sessionId)}`, {
        credentials: 'same-origin',
        headers: { 'Authorization': `Bearer ${_getAuthToken()}` },
      });

      if (!res.ok) return;

      const data = await res.json();
      if (data.has_result && data.result) {
        const result = data.result.data || data.result;
        _renderResults(result);
      }
    } catch (err) {
      console.error('[cv-optimizer] result fetch failed', err);
    }
  }

  async function _handleStart() {
    if (!_sessionId) return;

    const maxIter = parseInt((_el('cvo-max-iterations') || {}).value || '5', 10);
    const threshold = parseFloat((_el('cvo-score-threshold') || {}).value || '8.5');

    if (isNaN(maxIter) || maxIter < 1 || maxIter > 7) {
      if (typeof window.showToast === 'function') window.showToast('Max iterations must be 1–7', 'warning');
      return;
    }
    if (isNaN(threshold) || threshold < 7.0 || threshold > 9.5) {
      if (typeof window.showToast === 'function') window.showToast('Score threshold must be 7.0–9.5', 'warning');
      return;
    }

    const btn = _el('cvo-start-btn');
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Starting…';
    }

    try {
      const res = await fetch(`/api/v1/cv-optimizer/${encodeURIComponent(_sessionId)}/start`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Authorization': `Bearer ${_getAuthToken()}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ max_iterations: maxIter, score_threshold: threshold }),
      });

      const body = await res.json().catch(() => ({}));

      if (!res.ok) {
        const errorCode = body.error_code || '';
        const msg = body.message || body.detail || `Error ${res.status}`;

        if (errorCode === 'CFG_6001') {
          _setHidden(_el('cvo-byok-warning'), false);
          if (typeof window.showToast === 'function') {
            window.showToast('Add your Gemini API key in Settings → AI Setup to use this feature.', 'warning');
          }
        } else {
          const errEl = _el('cvo-error-message');
          if (errEl) errEl.textContent = decodeEntities(msg);
          _state = 'error';
          _showSection('cvo-error');
        }

        if (btn) {
          btn.disabled = false;
          btn.innerHTML = '<i class="fas fa-play"></i> Start Optimization';
        }
        return;
      }

      // Started successfully — show progress view
      _state = 'running';
      _showSection('cvo-progress');
    } catch (err) {
      console.error('[cv-optimizer] start failed', err);
      if (typeof window.showToast === 'function') window.showToast('Failed to start optimization. Please try again.', 'error');
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-play"></i> Start Optimization';
      }
    }
  }

  async function _handleClear() {
    if (!_sessionId) return;

    try {
      await fetch(`/api/v1/cv-optimizer/${encodeURIComponent(_sessionId)}`, {
        method: 'DELETE',
        credentials: 'same-origin',
        headers: { 'Authorization': `Bearer ${_getAuthToken()}` },
      });
    } catch (err) {
      console.error('[cv-optimizer] clear failed', err);
    }

    _state = 'not_started';
    _optimizedCv = '';
    _coverLetter = '';
    _resetProgressView();
    _showSection('cvo-setup');

    const btn = _el('cvo-start-btn');
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<i class="fas fa-play"></i> Start Optimization';
    }
  }

  function _handleReset() {
    _state = 'not_started';
    _optimizedCv = '';
    _coverLetter = '';
    _resetProgressView();
    _showSection('cvo-setup');
  }

  async function _handleDownloadOdt() {
    if (!_sessionId) return;

    const btn = /** @type {HTMLButtonElement|null} */ (_el('cvo-download-odt-btn'));
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Generating…';
    }

    try {
      const res = await fetch(
        `/api/v1/cv-optimizer/${encodeURIComponent(_sessionId)}/download-cv`,
        {
          credentials: 'same-origin',
          headers: { 'Authorization': `Bearer ${_getAuthToken()}` },
        }
      );

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const msg = (body.message || body.detail) || `Error ${res.status}`;
        if (typeof window.showToast === 'function') {
          // @ts-ignore
          window.showToast(decodeEntities(msg), 'error');
        }
        return;
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'optimized-cv.odt';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('[cv-optimizer] ODT download failed', err);
      if (typeof window.showToast === 'function') {
        // @ts-ignore
        window.showToast('Failed to download ODT. Please try again.', 'error');
      }
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-file-alt"></i> Download ODT';
      }
    }
  }

  // =============================================================================
  // VIEW UPDATES
  // =============================================================================

  /**
   * Update the progress view after each iteration.
   *
   * @param {number} iteration
   * @param {number} score
   * @param {string[]} strengths
   * @param {string[]} gaps
   * @param {string[]} actionItems
   */
  function _updateProgressView(iteration, score, strengths, gaps, actionItems) {
    const counter = _el('cvo-iteration-counter');
    if (counter) counter.textContent = decodeEntities(`Iteration ${iteration + 1}`);

    const scoreEl = _el('cvo-current-score');
    if (scoreEl) scoreEl.textContent = typeof score === 'number' ? score.toFixed(1) : '–';

    const log = _el('cvo-iteration-log');
    if (!log) return;

    const card = document.createElement('div');
    card.className = 'cvo-iter-card';
    card.innerHTML = `
      <div class="cvo-iter-header">
        <span class="cvo-iter-label">Iteration ${escapeHtml(String(iteration + 1))}</span>
        <span class="cvo-iter-score ${_scoreClass(score)}">${typeof score === 'number' ? score.toFixed(1) : '–'}/10</span>
      </div>
      <details class="cvo-iter-details">
        <summary>Feedback</summary>
        <div class="cvo-iter-body">
          <div class="cvo-fb-section">
            <strong>Strengths</strong>
            <ul>${(strengths || []).map(s => `<li>${escapeHtml(s)}</li>`).join('')}</ul>
          </div>
          <div class="cvo-fb-section">
            <strong>Gaps</strong>
            <ul>${(gaps || []).map(g => `<li>${escapeHtml(g)}</li>`).join('')}</ul>
          </div>
          <div class="cvo-fb-section">
            <strong>Action items</strong>
            <ul>${(actionItems || []).map(a => `<li>${escapeHtml(a)}</li>`).join('')}</ul>
          </div>
        </div>
      </details>`;
    log.appendChild(card);
    log.scrollTop = log.scrollHeight;
  }

  /**
   * Render the completed optimization result.
   * @param {Record<string,any>} result
   */
  function _renderResults(result) {
    _optimizedCv = result.optimized_cv || '';
    _coverLetter = result.cover_letter || '';

    const finalScoreEl = _el('cvo-final-score');
    if (finalScoreEl) {
      finalScoreEl.textContent = typeof result.best_score === 'number'
        ? result.best_score.toFixed(1)
        : '–';
      finalScoreEl.className = `cvo-score-value ${_scoreClass(result.best_score)}`;
    }

    const stopBadge = _el('cvo-stop-reason-badge');
    if (stopBadge) {
      stopBadge.textContent = decodeEntities(_stopReasonLabel(result.stop_reason));
      stopBadge.className = `cvo-stop-badge cvo-stop-${escapeHtml(result.stop_reason || '')}`;
    }

    // Score chart (simple bar chart — heights set via JS, not style= attr, to satisfy CSP)
    const chartEl = _el('cvo-score-chart');
    if (chartEl && Array.isArray(result.iteration_history)) {
      const chart = document.createElement('div');
      chart.className = 'cvo-chart';
      result.iteration_history.forEach(r => {
        const pct = Math.round((r.score / 10) * 100);
        const wrap = document.createElement('div');
        wrap.className = 'cvo-chart-bar-wrap';
        const bar = document.createElement('div');
        bar.className = `cvo-chart-bar ${_scoreClass(r.score)}`;
        bar.style.height = `${pct}%`;
        const label = document.createElement('span');
        label.className = 'cvo-chart-label';
        label.textContent = typeof r.score === 'number' ? r.score.toFixed(1) : '–';
        wrap.appendChild(bar);
        wrap.appendChild(label);
        chart.appendChild(wrap);
      });
      chartEl.innerHTML = '';
      chartEl.appendChild(chart);
    }

    // Optimized CV
    const cvEl = _el('cvo-optimized-cv');
    if (cvEl) cvEl.textContent = decodeEntities(_optimizedCv);

    // Cover Letter
    const clEl = _el('cvo-cover-letter');
    if (clEl) clEl.textContent = decodeEntities(_coverLetter);

    // Gap analysis
    const gapList = _el('cvo-gap-list');
    if (gapList) {
      const gaps = result.gap_analysis || [];
      if (gaps.length === 0) {
        gapList.innerHTML = '<li class="cvo-no-gaps">No persistent gaps identified.</li>';
      } else {
        gapList.innerHTML = gaps.map(g => `<li>${escapeHtml(g)}</li>`).join('');
      }
    }

    // Iteration history accordion
    const accordion = _el('cvo-history-accordion');
    if (accordion && Array.isArray(result.iteration_history)) {
      accordion.innerHTML = result.iteration_history.map(r => {
        const best = r.iteration === result.best_iteration ? ' (best)' : '';
        return `<details class="cvo-history-item">
          <summary>Iteration ${escapeHtml(String(r.iteration + 1))} — ${typeof r.score === 'number' ? r.score.toFixed(1) : '–'}/10${escapeHtml(best)}</summary>
          <div class="cvo-fb-section"><strong>Strengths</strong>
            <ul>${(r.strengths || []).map(s => `<li>${escapeHtml(s)}</li>`).join('')}</ul>
          </div>
          <div class="cvo-fb-section"><strong>Gaps</strong>
            <ul>${(r.gaps || []).map(g => `<li>${escapeHtml(g)}</li>`).join('')}</ul>
          </div>
        </details>`;
      }).join('');
    }

    _showSection('cvo-results');
  }

  function _showErrorView(message) {
    const msgEl = _el('cvo-error-message');
    if (msgEl) msgEl.textContent = decodeEntities(message);
    _showSection('cvo-error');
  }

  function _resetProgressView() {
    const counter = _el('cvo-iteration-counter');
    if (counter) counter.textContent = 'Iteration 0';
    const scoreEl = _el('cvo-current-score');
    if (scoreEl) scoreEl.textContent = '–';
    const log = _el('cvo-iteration-log');
    if (log) log.innerHTML = '';
  }

  // =============================================================================
  // UTILITIES
  // =============================================================================

  /**
   * @param {number} score
   * @returns {string}
   */
  function _scoreClass(score) {
    if (score >= 8.5) return 'cvo-score-excellent';
    if (score >= 7.0) return 'cvo-score-good';
    if (score >= 5.0) return 'cvo-score-fair';
    return 'cvo-score-poor';
  }

  /**
   * @param {string|null|undefined} stopReason
   * @returns {string}
   */
  function _stopReasonLabel(stopReason) {
    switch (stopReason) {
      case 'score_threshold': return 'Score threshold reached';
      case 'score_decrease':  return 'Score decreased — kept best version';
      case 'score_plateau':   return 'Score plateaued';
      case 'max_iterations':  return 'Max iterations reached';
      default:                return stopReason || '';
    }
  }

  // =============================================================================
  // PUBLIC API
  // =============================================================================

  window.initCvOptimizerTab = initCvOptimizerTab;

}());
