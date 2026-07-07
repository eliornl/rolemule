/**
 * CV Optimization Loop — tab logic for the application detail page.
 *
 * Handles the "Optimize CV" 9th tab: start/poll/render the iterative
 * CV optimization loop. Uses the same AI credentials as the rest of the app (CFG_6001 if none configured).
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
    const decoded = decodeEntities(str);
    return decoded
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }

  /** Decode HTML entities for .textContent assignments (no re-encoding step) */
  function decodeEntities(str) {
    if (str == null) return '';
    const textarea = document.createElement('textarea');
    textarea.innerHTML = String(str);
    return textarea.value;
  }

  /**
   * Show a notification — delegates to application-detail showToast when available.
   * @param {string} message
   * @param {'success'|'error'|'warning'|'info'} [type]
   */
  function _notify(message, type) {
    const toastType = type === 'success' ? 'success' : 'error';
    if (typeof window.showApplicationToast === 'function') {
      window.showApplicationToast(message, toastType);
      return;
    }
    // Fallback if application-detail.js has not loaded yet
    const dismissMs = toastType === 'success' ? 4000 : 8000;
    const toast = document.createElement('div');
    toast.style.cssText = 'position:fixed;bottom:20px;right:20px;max-width:min(420px,calc(100vw - 2rem));'
      + 'line-height:1.5;background:'
      + (toastType === 'success' ? '#10b981' : '#ef4444')
      + ';color:white;padding:.75rem 1.25rem;border-radius:8px;z-index:9999;font-size:.85rem;'
      + 'box-shadow:0 4px 16px rgba(0,0,0,.35)';
    toast.textContent = message;
    document.body.appendChild(toast);
    window.setTimeout(function () { toast.remove(); }, dismissMs);
  }

  /**
   * @param {string} text
   * @param {string} filename
   * @param {string} mimeType
   */
  function _downloadTextFile(text, filename, mimeType) {
    const blob = new Blob([text], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  /**
   * Robust clipboard write — tries navigator.clipboard first, falls back to execCommand.
   * @param {string} text
   * @param {string} [successMsg]
   */
  function _clipboardWrite(text, successMsg) {
    const msg = successMsg || 'Copied to clipboard!';
    function showSuccess() {
      _notify(msg, 'success');
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

  /** @type {AbortController|null} cancels the status-poll loop */
  let _pollAbortController = null;

  /** @type {ReturnType<typeof setTimeout>|null} */
  let _pollTimeoutId = null;

  /** whether click delegation has been registered */
  let _eventListenersAttached = false;

  /** Whether user BYOK, server key, or Vertex AI is available */
  let _hasAiConfigured = true;

  /** @type {boolean} */
  let _apiKeyStatusLoaded = false;

  const _MIN_SCORE_THRESHOLD = 7.0;
  const _MAX_SCORE_THRESHOLD = 9.5;

  /** @param {HTMLButtonElement|null|undefined} btn */
  function _setStartBtnLoading(btn) {
    if (!btn) return;
    btn.disabled = true;
    btn.classList.add('loading');
  }

  /** @param {HTMLButtonElement|null|undefined} btn */
  function _resetStartBtn(btn) {
    if (!btn) return;
    btn.classList.remove('loading');
    btn.disabled = !_hasAiConfigured;
  }

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
    ['cvo-setup', 'cvo-progress', 'cvo-results'].forEach(id => {
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
    _checkApiKeyStatus();
    _loadCvOptimizationStatus();
  }

  /**
   * Fetch AI credential status (same gate as workflow / interview prep).
   * @returns {Promise<void>}
   */
  async function _checkApiKeyStatus() {
    try {
      const res = await fetch('/api/v1/profile/api-key/status', {
        credentials: 'same-origin',
        headers: { 'Authorization': `Bearer ${_getAuthToken()}` },
      });
      if (!res.ok) return;

      const data = await res.json();
      _hasAiConfigured = !!(
        data.has_user_key || data.server_has_key || data.use_vertex_ai
      );
      _apiKeyStatusLoaded = true;
      _updateAiSetupUi();
    } catch (err) {
      console.debug('[cv-optimizer] api-key status check failed', err);
    }
  }

  /** Show or hide the setup warning and enable/disable Start when AI is not configured. */
  function _updateAiSetupUi() {
    const warning = _el('cvo-ai-setup-warning');
    if (warning) {
      _setHidden(warning, _hasAiConfigured);
    }

    const startBtn = /** @type {HTMLButtonElement|null} */ (_el('cvo-start-btn'));
    if (startBtn && _state === 'not_started') {
      startBtn.disabled = !_hasAiConfigured;
    }
  }

  // =============================================================================
  // EVENT DELEGATION
  // =============================================================================

  function _attachEventListeners() {
    if (_eventListenersAttached) return;
    const pane = _el('cvOptimizeContent');
    if (!pane) return;

    pane.addEventListener('click', function (e) {
      const target = /** @type {HTMLElement} */ (e.target);
      const actionEl = /** @type {HTMLElement|null} */ (target.closest('[data-action]'));
      if (!actionEl) return;

      const action = actionEl.getAttribute('data-action');
      if (action === 'startCvOptimization') _handleStart();
      else if (action === 'clearCvOptimization') _handleClear();
      else if (action === 'copyOptimizedCv') _clipboardWrite(_optimizedCv, 'Optimized CV copied!');
      else if (action === 'copyCvoCoverLetter') _clipboardWrite(_coverLetter, 'Cover letter copied!');
      else if (action === 'downloadOptimizedCvOdt') _handleDownloadOdt();
    });
    _eventListenersAttached = true;
  }

  // =============================================================================
  // POLLING FALLBACK
  // =============================================================================

  function _stopPolling() {
    if (_pollAbortController) { _pollAbortController.abort(); _pollAbortController = null; }
    if (_pollTimeoutId !== null) { clearTimeout(_pollTimeoutId); _pollTimeoutId = null; }
  }

  function _startPolling() {
    _stopPolling();
    _pollAbortController = new AbortController();
    const signal = _pollAbortController.signal;
    const maxAttempts = 60;
    let attempts = 0;

    const poll = async () => {
      if (signal.aborted || !_sessionId) return;
      attempts++;
      try {
        const res = await fetch(
          `/api/v1/cv-optimizer/${encodeURIComponent(_sessionId)}/status`,
          { credentials: 'same-origin', headers: { 'Authorization': `Bearer ${_getAuthToken()}` }, signal }
        );
        if (res.ok) {
          const data = await res.json();
          if (data.has_result) {
            _stopPolling();
            _state = 'complete';
            _fetchAndRenderResult();
            return;
          }
          if (!data.is_running) {
            _stopPolling();
            _state = 'not_started';
            _showSection('cvo-setup');
            _updateAiSetupUi();
            return;
          }
        }
      } catch (err) {
        if (signal.aborted) return;
      }
      if (attempts < maxAttempts) {
        _pollTimeoutId = window.setTimeout(poll, 5000);
      }
    };
    poll();
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
      _resetProgressView();
      _showSection('cvo-progress');
      _startPolling();
    } else if (type === 'cv_optimization_iteration') {
      const d = msg['data'] || {};
      _updateProgressView(d['iteration'], d['score'], d['strengths'], d['gaps'], d['action_items']);
    } else if (type === 'cv_optimization_complete') {
      _stopPolling();
      _state = 'complete';
      _fetchAndRenderResult();
    } else if (type === 'cv_optimization_error') {
      _stopPolling();
      _state = 'not_started';
      const errMsg = ((msg['data'] || {})['error']) || 'Optimization failed. Please try again.';
      _resetProgressView();
      _showSection('cvo-setup');
      _updateAiSetupUi();
      _resetStartBtn(/** @type {HTMLButtonElement|null} */ (_el('cvo-start-btn')));
      _notify(decodeEntities(String(errMsg)), 'error');
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
        _startPolling();
        return;
      }

      if (data.has_result) {
        _state = 'complete';
        _fetchAndRenderResult();
        return;
      }

      _state = 'not_started';
      _showSection('cvo-setup');
      _updateAiSetupUi();
    } catch (err) {
      console.error('[cv-optimizer] status fetch failed', err);
      _showSection('cvo-setup');
      _updateAiSetupUi();
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
        const result = data.result;
        _renderResults(result);
      }
    } catch (err) {
      console.error('[cv-optimizer] result fetch failed', err);
    }
  }

  async function _handleStart() {
    if (!_sessionId) return;

    if (!_apiKeyStatusLoaded) {
      await _checkApiKeyStatus();
    }
    if (!_hasAiConfigured) {
      _updateAiSetupUi();
      _notify(
        'Configure AI in Settings → AI Setup before starting optimization.',
        'warning'
      );
      return;
    }

    const maxIter = parseInt((_el('cvo-max-iterations') || {}).value || '5', 10);
    const thresholdEl = /** @type {HTMLSelectElement|null} */ (_el('cvo-score-threshold'));
    const threshold = parseFloat(thresholdEl ? thresholdEl.value : '8.5');

    if (isNaN(maxIter) || maxIter < 2 || maxIter > 7) {
      _notify('Max iterations must be 2–7', 'warning');
      return;
    }
    if (isNaN(threshold) || threshold < _MIN_SCORE_THRESHOLD || threshold > _MAX_SCORE_THRESHOLD) {
      _notify('Choose a stop score between 7.0 and 9.5', 'warning');
      return;
    }

    const btn = /** @type {HTMLButtonElement|null} */ (_el('cvo-start-btn'));
    _setStartBtnLoading(btn);

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
        const decodedMsg = decodeEntities(String(msg));

        if (errorCode === 'CFG_6001') {
          _hasAiConfigured = false;
          _updateAiSetupUi();
          _notify(
            'Configure AI in Settings → AI Setup before starting optimization.',
            'warning'
          );
        } else if (res.status === 429 || errorCode === 'RATE_4001') {
          _notify(
            decodedMsg || 'You\u2019ve used all optimization runs for this hour. Try again shortly.',
            'error'
          );
        } else {
          _notify(decodedMsg, 'error');
        }

        _state = 'not_started';
        _showSection('cvo-setup');
        _updateAiSetupUi();

        _resetStartBtn(btn);
        return;
      }

      // Started successfully — show progress view
      _state = 'running';
      _resetStartBtn(btn);
      _resetProgressView();
      _showSection('cvo-progress');
    } catch (err) {
      console.error('[cv-optimizer] start failed', err);
      _notify('Failed to start optimization. Please try again.', 'error');
      _state = 'not_started';
      _showSection('cvo-setup');
      _updateAiSetupUi();
      _resetStartBtn(btn);
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
    _updateAiSetupUi();

    _resetStartBtn(/** @type {HTMLButtonElement|null} */ (_el('cvo-start-btn')));
  }

  /**
   * @param {any} body
   * @param {string} fallback
   * @returns {string}
   */
  function _apiErrorMessage(body, fallback) {
    if (!body || typeof body !== 'object') return fallback;
    const raw = typeof body.message === 'string'
      ? body.message
      : (typeof body.detail === 'string' ? body.detail : '');
    return raw.trim() ? decodeEntities(raw.trim()) : fallback;
  }

  /**
   * Parse filename from Content-Disposition header.
   * @param {string|null|undefined} disposition
   * @returns {string}
   */
  function _filenameFromDisposition(disposition) {
    if (!disposition) return 'optimized-cv.docx';
    const match = disposition.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i);
    if (!match || !match[1]) return 'optimized-cv.docx';
    return decodeEntities(match[1].replace(/"/g, '').trim());
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
        const errorCode = body.error_code || '';
        const decodedMsg = _apiErrorMessage(body, `Error ${res.status}`);

        if (errorCode === 'CFG_6001') {
          _hasAiConfigured = false;
          _updateAiSetupUi();
          _notify(
            'Configure AI in Settings \u2192 AI Setup before downloading your CV.',
            'warning'
          );
        } else if (res.status === 429 || errorCode === 'RATE_4001') {
          _notify(
            decodedMsg || 'You\u2019ve used all CV downloads for this hour. Try again shortly.',
            'error'
          );
        } else if (_optimizedCv && res.status >= 500) {
          _downloadTextFile(_optimizedCv, 'optimized-cv.md', 'text/markdown');
          _notify(
            'Document export failed — downloaded your CV as Markdown instead.',
            'warning'
          );
        } else {
          _notify(decodedMsg, 'error');
        }
        return;
      }

      const blob = await res.blob();
      const filename = _filenameFromDisposition(res.headers.get('Content-Disposition'));
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      const ext = filename.split('.').pop() || 'docx';
      _notify(`CV downloaded (.${ext}).`, 'success');
    } catch (err) {
      console.error('[cv-optimizer] CV download failed', err);
      if (_optimizedCv) {
        _downloadTextFile(_optimizedCv, 'optimized-cv.md', 'text/markdown');
        _notify(
          'Document export failed — downloaded your CV as Markdown instead.',
          'warning'
        );
      } else {
        _notify('Failed to download CV. Please try again.', 'error');
      }
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-file-word"></i> Download CV';
      }
    }
  }

  // =============================================================================
  // VIEW UPDATES
  // =============================================================================

  /**
   * @param {number} iteration
   * @param {number} score
   * @param {string[]} strengths
   * @param {string[]} gaps
   * @param {string[]} actionItems
   * @param {string} [summarySuffix]
   * @returns {string}
   */
  function _buildIterationAccordionHtml(iteration, score, strengths, gaps, actionItems, summarySuffix) {
    const scoreText = typeof score === 'number' ? score.toFixed(1) : '–';
    const suffix = summarySuffix ? escapeHtml(summarySuffix) : '';
    const actions = actionItems || [];
    const actionsHtml = actions.length > 0
      ? `<div class="cvo-fb-section"><strong>Action items</strong>
        <ul>${actions.map(a => `<li>${escapeHtml(a)}</li>`).join('')}</ul>
      </div>`
      : '';
    return `<details class="cvo-history-item">
      <summary>Iteration ${escapeHtml(String(iteration + 1))} — <span class="cvo-history-score ${_scoreClass(score)}">${scoreText}/10</span>${suffix}</summary>
      <div class="cvo-fb-section"><strong>Strengths</strong>
        <ul>${(strengths || []).map(s => `<li>${escapeHtml(s)}</li>`).join('')}</ul>
      </div>
      <div class="cvo-fb-section"><strong>Gaps</strong>
        <ul>${(gaps || []).map(g => `<li>${escapeHtml(g)}</li>`).join('')}</ul>
      </div>
      ${actionsHtml}
    </details>`;
  }

  /**
   * Shared score tiers for banner, accordion, and icons.
   * @param {number|undefined|null} score
   * @returns {{ bannerClass: string, icon: string, scoreClass: string, spinning: boolean }}
   */
  function _scoreTier(score) {
    if (typeof score !== 'number') {
      return { bannerClass: 'apply-muted', icon: 'fa-chart-line', scoreClass: '', spinning: false };
    }
    if (score >= 8.5) {
      return { bannerClass: 'apply-good', icon: 'fa-check-circle', scoreClass: 'cvo-score-excellent', spinning: false };
    }
    if (score >= 5.0) {
      return { bannerClass: 'apply-review', icon: 'fa-chart-line', scoreClass: 'cvo-score-fair', spinning: false };
    }
    return { bannerClass: 'apply-poor', icon: 'fa-exclamation-circle', scoreClass: 'cvo-score-poor', spinning: false };
  }

  /**
   * @param {number|undefined|null} score
   * @returns {string}
   */
  function _progressAnswerText(score) {
    return typeof score === 'number' ? `${score.toFixed(1)} / 10` : 'Evaluating…';
  }

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

    const answerEl = _el('cvo-progress-answer');
    if (answerEl) answerEl.textContent = _progressAnswerText(score);

    const tier = _scoreTier(score);
    const banner = _el('cvo-score-display');
    if (banner) {
      banner.className = 'apply-decision-banner cvo-progress-banner ' + tier.bannerClass;
    }

    const iconEl = _el('cvo-progress-icon');
    if (iconEl) {
      iconEl.className = 'fas ' + tier.icon + ' apply-icon' + (tier.spinning ? ' fa-spin' : '');
    }

    const statusEl = _el('cvo-progress-status');
    if (statusEl) {
      statusEl.textContent = typeof score === 'number'
        ? `Iteration ${iteration + 1} complete — revising CV…`
        : 'Waiting for first evaluation…';
    }

    const log = _el('cvo-iteration-log');
    if (!log) return;

    const wrap = document.createElement('div');
    wrap.innerHTML = _buildIterationAccordionHtml(iteration, score, strengths, gaps, actionItems, '');
    const item = wrap.firstElementChild;
    if (item) {
      log.appendChild(item);
      log.scrollTop = log.scrollHeight;
    }
  }

  /**
   * Render the completed optimization result.
   * @param {Record<string,any>} result
   */
  function _renderResults(result) {
    _optimizedCv = result.optimized_cv || '';
    _coverLetter = result.cover_letter || '';

    const banner = _el('cvo-results-banner');
    const iconEl = _el('cvo-result-icon');
    const bannerClass = _resultBannerClass(result.stop_reason);
    if (banner) {
      banner.className = 'apply-decision-banner cvo-results-banner ' + bannerClass;
    }
    if (iconEl) {
      iconEl.className = 'fas ' + _resultBannerIcon(result.stop_reason) + ' apply-icon';
    }

    const finalScoreEl = _el('cvo-final-score');
    if (finalScoreEl) {
      finalScoreEl.textContent = typeof result.best_score === 'number'
        ? result.best_score.toFixed(1)
        : '–';
    }

    const stopBadge = _el('cvo-stop-reason-badge');
    if (stopBadge) {
      stopBadge.textContent = decodeEntities(_stopReasonLabel(result.stop_reason));
    }

    const noticeText = _el('cvo-results-notice-text');
    if (noticeText) {
      noticeText.textContent = result.stop_reason === 'api_rate_limit'
        ? 'The AI quota or rate limit was reached before the run could finish. The results below show your best progress so far — try again later or review your API key under Settings \u2192 AI Setup.'
        : 'Review carefully before submitting — verify every claim matches your profile and experience.';
    }

    const chartEl = _el('cvo-score-chart');
    if (chartEl && Array.isArray(result.iteration_history)) {
      const chart = document.createElement('div');
      chart.className = 'cvo-chart';
      result.iteration_history.forEach(r => {
        const wrap = document.createElement('div');
        wrap.className = 'cvo-chart-bar-wrap';
        const bar = document.createElement('div');
        bar.className = 'cvo-chart-bar ' + _chartScoreClass(r.score);
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

    const cvEl = _el('cvo-optimized-cv');
    if (cvEl) cvEl.textContent = decodeEntities(_optimizedCv);

    const clEl = _el('cvo-cover-letter');
    const clMissing = _el('cvo-cover-letter-missing');
    const clDoc = _el('cvo-cover-letter-doc');
    if (_coverLetter) {
      if (clEl) clEl.textContent = decodeEntities(_coverLetter);
      _setHidden(clMissing, true);
      _setHidden(clDoc, false);
      _updateDocFooterMeta('cvo-cl-word-count', 'cvo-cl-generated-at', _coverLetter, result.completed_at);
    } else {
      if (clEl) clEl.textContent = '';
      _setHidden(clMissing, false);
      _setHidden(clDoc, true);
    }

    _updateDocFooterMeta('cvo-cv-word-count', 'cvo-cv-generated-at', _optimizedCv, result.completed_at);

    const gapList = _el('cvo-gap-list');
    if (gapList) {
      const gaps = result.gap_analysis || [];
      if (gaps.length === 0) {
        gapList.innerHTML = '<li><i class="fas fa-check green"></i><span>No persistent gaps identified.</span></li>';
      } else {
        gapList.innerHTML = gaps.map(function (g) {
          return '<li><i class="fas fa-minus-circle amber"></i><span>' + escapeHtml(g) + '</span></li>';
        }).join('');
      }
    }

    // Iteration history accordion
    const accordion = _el('cvo-history-accordion');
    if (accordion && Array.isArray(result.iteration_history)) {
      accordion.innerHTML = result.iteration_history.map(r => {
        const best = r.iteration === result.best_iteration ? ' (best)' : '';
        return _buildIterationAccordionHtml(
          r.iteration,
          r.score,
          r.strengths || [],
          r.gaps || [],
          [],
          best
        );
      }).join('');
    }

    _showSection('cvo-results');
  }

  function _resetProgressView() {
    const counter = _el('cvo-iteration-counter');
    if (counter) counter.textContent = 'Starting…';
    const answerEl = _el('cvo-progress-answer');
    if (answerEl) answerEl.textContent = 'Evaluating…';
    const banner = _el('cvo-score-display');
    if (banner) banner.className = 'apply-decision-banner apply-muted cvo-progress-banner';
    const iconEl = _el('cvo-progress-icon');
    if (iconEl) iconEl.className = 'fas fa-chart-line apply-icon';
    const statusEl = _el('cvo-progress-status');
    if (statusEl) statusEl.textContent = 'Waiting for first evaluation…';
    const log = _el('cvo-iteration-log');
    if (log) log.innerHTML = '';
  }

  // =============================================================================
  // UTILITIES
  // =============================================================================

  /**
   * @param {string} text
   * @returns {number}
   */
  function _wordCount(text) {
    if (!text || !String(text).trim()) return 0;
    return String(text).trim().split(/\s+/).filter(Boolean).length;
  }

  /**
   * @param {string|null|undefined} iso
   * @returns {string}
   */
  function _formatGeneratedDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  }

  /**
   * Update cover-letter-box footer meta (word count + generated date).
   * @param {string} wordCountId
   * @param {string} generatedId
   * @param {string} text
   * @param {string|null|undefined} completedAt
   */
  function _updateDocFooterMeta(wordCountId, generatedId, text, completedAt) {
    const wordEl = _el(wordCountId);
    if (wordEl) {
      wordEl.innerHTML = '<i class="fas fa-align-left"></i> ' + String(_wordCount(text)) + ' words';
    }
    const genEl = _el(generatedId);
    if (genEl) {
      const formatted = _formatGeneratedDate(completedAt);
      if (formatted) {
        genEl.innerHTML = '<i class="fas fa-clock"></i> Generated ' + escapeHtml(formatted);
        genEl.classList.remove('is-hidden');
      } else {
        genEl.textContent = '';
        genEl.classList.add('is-hidden');
      }
    }
  }

  /**
   * @param {number} score
   * @returns {string}
   */
  function _scoreClass(score) {
    if (typeof score !== 'number') return '';
    return _scoreTier(score).scoreClass;
  }

  /**
   * Chart bar tiers — matches resume-score-card high / medium / low colours.
   * @param {number} score
   * @returns {string}
   */
  function _chartScoreClass(score) {
    if (typeof score !== 'number') return '';
    if (score >= 8.5) return 'cvo-score-high';
    if (score >= 7.0) return 'cvo-score-medium';
    return 'cvo-score-low';
  }

  /**
   * @param {string|null|undefined} stopReason
   * @returns {string}
   */
  function _resultBannerClass(stopReason) {
    switch (stopReason) {
      case 'score_threshold': return 'apply-good';
      case 'score_plateau':   return 'apply-review';
      case 'api_rate_limit':    return 'apply-review';
      case 'score_decrease':  return 'apply-poor';
      default:                return 'apply-muted';
    }
  }

  /**
   * @param {string|null|undefined} stopReason
   * @returns {string}
   */
  function _resultBannerIcon(stopReason) {
    switch (stopReason) {
      case 'score_threshold': return 'fa-check-circle';
      case 'score_plateau':   return 'fa-pause-circle';
      case 'api_rate_limit':    return 'fa-hourglass-half';
      case 'score_decrease':  return 'fa-arrow-down';
      default:                return 'fa-flag-checkered';
    }
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
      case 'api_rate_limit':    return 'AI rate limit reached — best progress saved';
      case 'max_iterations':  return 'Max iterations reached';
      default:                return stopReason || '';
    }
  }

  // =============================================================================
  // PUBLIC API
  // =============================================================================

  window.initCvOptimizerTab = initCvOptimizerTab;

}());
