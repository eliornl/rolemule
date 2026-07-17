/**
 * Dashboard home — application list, filters, stats, WebSocket updates.
 */
import {
  getApiBase,
  getLoginUrl,
  isAuthenticated,
  logout,
} from '../shared/auth';
import {
  displayCompanyNameOrUnknown,
  isPlaceholderCompanyName,
  isPlaceholderJobTitle,
} from '../shared/dashboard-display';
import { escapeHtml } from '../shared/dom-security';
import { notify } from '../shared/notify';
import { formatWorkflowFailureDetail } from '../shared/workflow-errors';
import type {
  ApplicationStatsResponse,
  ApplicationsListResponse,
  DashboardApplication,
  WorkflowStatusResponse,
} from '../shared/types';

// =============================================================================
// CONSTANTS
// =============================================================================

const API_BASE = getApiBase();
const PER_PAGE = 10;
const SESSION_KEY = 'dash_filter_state';
const FOLLOW_UP_DAYS = 14;
const POLL_INTERVAL_MS = 5000;
const WS_MAX_RECONNECT = 8;

const STORAGE_KEYS = {
  AUTH_TOKEN: 'access_token',
  AUTH_TOKEN_LEGACY: 'authToken',
} as const;

// =============================================================================
// STATE
// =============================================================================

let _loadedApps: DashboardApplication[] = [];
let _totalCount = 0;
let _nextPage = 1;
let _isLoading = false;
let _pendingLoadApplicationsReset = false;
let _loadApplicationsInFlight: Promise<void> | null = null;
const _selected = new Set<string>();
let _search = '';
let _status = '';
let _days = '';
let _sort = 'created_desc';
let _searchTimer: number | null = null;
let _firstLoad = true;

interface ProcessingAppInfo {
  detailId: string;
  jobTitle: string;
  companyName: string;
}

const _processingApps = new Map<string, ProcessingAppInfo>();
let _pollTimer: number | null = null;
let _ws: WebSocket | null = null;
let _wsReconnectAttempts = 0;
const _submittedToastShownForSession = new Set<string>();

function rememberSubmittedToast(sessionId: string): void {
  if (!sessionId) return;
  _submittedToastShownForSession.add(sessionId);
}

function hasSubmittedToastForSession(sessionId: string): boolean {
  return Boolean(sessionId) && _submittedToastShownForSession.has(sessionId);
}

function getAuthToken(): string | null {
  if (window.app && typeof window.app.getAuthToken === 'function') {
    return window.app.getAuthToken();
  }
  const urlParams = new URLSearchParams(window.location.search);
  const urlToken = urlParams.get('token') || urlParams.get('access_token');
  if (urlToken) {
    setAuthToken(urlToken);
    return urlToken;
  }
  return (
    localStorage.getItem(STORAGE_KEYS.AUTH_TOKEN) ||
    localStorage.getItem(STORAGE_KEYS.AUTH_TOKEN_LEGACY)
  );
}

function setAuthToken(token: string | null): void {
  if (!token) {
    localStorage.removeItem(STORAGE_KEYS.AUTH_TOKEN);
    localStorage.removeItem(STORAGE_KEYS.AUTH_TOKEN_LEGACY);
    return;
  }
  localStorage.setItem(STORAGE_KEYS.AUTH_TOKEN, token);
  localStorage.setItem(STORAGE_KEYS.AUTH_TOKEN_LEGACY, token);
  try {
    window.postMessage(
      {
        type: 'JAA_AUTH_SUCCESS',
        token,
        user: JSON.parse(localStorage.getItem('user') || '{}') as Record<string, unknown>,
        apiUrl: window.location.origin + API_BASE,
      },
      window.location.origin,
    );
  } catch {
    /* extension not installed */
  }
}

    // =============================================================================
    // HELPERS — dates
    // =============================================================================

    function relativeTime(dateStr: string): string {
        const diff = new Date().getTime() - new Date(dateStr).getTime();
        const days = Math.floor(diff / 86400000);
        if (days === 0) return 'Today';
        if (days === 1) return 'Yesterday';
        if (days < 7)  return `${days} days ago`;
        if (days < 30) return `${Math.floor(days / 7)} week${Math.floor(days / 7) > 1 ? 's' : ''} ago`;
        if (days < 365) return `${Math.floor(days / 30)} month${Math.floor(days / 30) > 1 ? 's' : ''} ago`;
        return `${Math.floor(days / 365)} year${Math.floor(days / 365) > 1 ? 's' : ''} ago`;
    }

    function fullDate(dateStr: string): string {
        return new Date(dateStr).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
    }

    function needsFollowUp(app: DashboardApplication): boolean {
        if (String(app.status ?? '').toLowerCase() !== 'applied') return false;
        const updated = new Date(app.updated_at ?? '');
        return (new Date().getTime() - updated.getTime()) / 86400000 >= FOLLOW_UP_DAYS;
    }

    // =============================================================================
    // HELPERS — status
    // =============================================================================

    function formatStatus(status: string): string {
        const map: Record<string, string> = {
            draft: 'Draft', processing: 'Processing', ready: 'Ready',
            completed: 'Completed', applied: 'Applied', interview: 'Interview',
            rejected: 'Rejected', accepted: 'Accepted', failed: 'Failed',
            DRAFT: 'Draft', PROCESSING: 'Processing', READY: 'Ready',
            COMPLETED: 'Completed', APPLIED: 'Applied', INTERVIEW: 'Interview',
            REJECTED: 'Rejected', ACCEPTED: 'Accepted', FAILED: 'Failed',
        };
        return map[status] ?? status;
    }

    function aiStatusBadge(status: string): string {
        if (status === 'processing') {
            return `<span class="card-ai-badge ai-processing"><i class="fas fa-spinner fa-spin me-1" aria-hidden="true"></i>Analyzing</span>`;
        }
        if (status === 'failed') {
            return `<span class="card-ai-badge ai-failed"><i class="fas fa-exclamation-circle me-1" aria-hidden="true"></i>Failed</span>`;
        }
        if (status === 'draft') {
            return `<span class="card-ai-badge ai-draft">Draft</span>`;
        }
        // analysis complete (completed, applied, interview, accepted, rejected, etc.)
        return `<span class="card-ai-badge ai-ready"><i class="fas fa-check me-1" aria-hidden="true"></i>Ready</span>`;
    }

    function trackingButtonsHtml(status: string, appId: string): string {
        const systemStatuses = ['draft', 'processing', 'failed'];
        if (systemStatuses.includes(status)) return '';

        const safeId = escapeHtml(appId);
        const buttons = [
            { v: 'applied',   l: 'Applied',   cls: 'track-applied'   },
            { v: 'interview', l: 'Interview',  cls: 'track-interview'  },
            { v: 'accepted',  l: 'Offer',      cls: 'track-accepted'   },
            { v: 'rejected',  l: 'Rejected',   cls: 'track-rejected'   },
        ].map(btn => {
            const active = status === btn.v ? ' track-btn-active' : '';
            return `<button class="track-btn ${btn.cls}${active}" data-action="set-tracking" data-id="${safeId}" data-value="${btn.v}" aria-pressed="${status === btn.v}">${btn.l}</button>`;
        }).join('');

        return `<div class="card-tracking-row">${buttons}</div>`;
    }

    // =============================================================================
    // SESSION STORAGE — save / restore filter state + scroll
    // =============================================================================

    function saveFilterState() {
        try {
            sessionStorage.setItem(SESSION_KEY, JSON.stringify({
                search: _search, status: _status, days: _days, sort: _sort,
                scrollY: window.scrollY,
            }));
        } catch (e) { /* storage unavailable */ }
    }

    function restoreFilterState(): number {
        try {
            const raw = sessionStorage.getItem(SESSION_KEY);
            if (!raw) return 0;
            const state = JSON.parse(raw) as {
                search?: string;
                status?: string;
                days?: string;
                sort?: string;
                scrollY?: number;
            };

            _search = state.search || '';
            _status = state.status || '';
            _days   = state.days   || '';
            _sort   = state.sort   || 'created_desc';

            const searchEl = document.getElementById('searchInput') as HTMLInputElement | null;
            const statusEl = document.getElementById('statusFilter') as HTMLSelectElement | null;
            const dateEl = document.getElementById('dateFilter') as HTMLSelectElement | null;
            const sortEl = document.getElementById('sortFilter') as HTMLSelectElement | null;

            if (searchEl) searchEl.value = _search;
            if (statusEl) statusEl.value = _status;
            if (dateEl)   dateEl.value   = _days;
            if (sortEl)   sortEl.value   = _sort;

            return state.scrollY || 0;
        } catch (e) {
            return 0;
        }
    }

    function dedupeApplicationsById(apps: DashboardApplication[]): DashboardApplication[] {
        const seen = new Set<string>();
        const out: DashboardApplication[] = [];
        for (const a of apps) {
            const id = String(a.id ?? '');
            if (!id || seen.has(id)) continue;
            seen.add(id);
            out.push(a);
        }
        return out;
    }

    function mergeApplicationsPage(
        existing: DashboardApplication[],
        incoming: DashboardApplication[],
    ): { merged: DashboardApplication[]; appended: DashboardApplication[] } {
        const seen = new Set(existing.map((a) => String(a.id ?? '')));
        const appended: DashboardApplication[] = [];
        for (const a of incoming) {
            const id = String(a.id ?? '');
            if (!id || seen.has(id)) continue;
            seen.add(id);
            appended.push(a);
        }
        return {
            merged: appended.length ? [...existing, ...appended] : existing,
            appended,
        };
    }

    // =============================================================================
    // RENDER — single application card
    // =============================================================================

    function renderCard(app: DashboardApplication): string {
        const appId      = String(app.id ?? '');
        const detailId   = String(app.workflow_session_id || app.id || '');
        const status     = String(app.status ?? '').toLowerCase();
        const safeAppId  = escapeHtml(appId);
        const safeDetail = escapeHtml(detailId);

        const createdAt = String(app.created_at ?? '');
        const relTime   = createdAt ? relativeTime(createdAt) : '';
        const absTime   = createdAt ? fullDate(createdAt) : '';

        const matchScore = app.match_score != null
            ? `<span><i class="fas fa-chart-line me-1" aria-hidden="true"></i>${Math.round(app.match_score * 100)}% match</span>`
            : '';

        const followUpIcon = needsFollowUp(app)
            ? `<span class="follow-up-badge" title="No status change in ${FOLLOW_UP_DAYS}+ days — consider following up"><i class="fas fa-clock" aria-hidden="true"></i></span>`
            : '';

        const isProcessing = status === 'processing';
        const hasRealTitle = app.job_title && !isPlaceholderJobTitle(app.job_title);
        const titleHtml = hasRealTitle
            ? `<h6 class="application-title">${escapeHtml(String(app.job_title))}</h6>`
            : isProcessing
                ? `<div class="skeleton-line skeleton-title" aria-hidden="true"></div>`
                : `<h6 class="application-title">Job Application</h6>`;
        const companyHtml = app.company_name && !isPlaceholderCompanyName(app.company_name)
            ? `<div class="company-name">${escapeHtml(String(app.company_name))}</div>`
            : isProcessing
                ? `<div class="skeleton-line skeleton-subtitle" aria-hidden="true"></div>`
                : `<div class="company-name">Unknown</div>`;

        return `
<div class="application-card border-status-${escapeHtml(status)} cursor-pointer" data-card-id="${safeDetail}" role="listitem">
    <div class="card-layout">
        <div class="card-left">
            ${titleHtml}
            ${companyHtml}
            <div class="application-meta">
                <span title="${escapeHtml(absTime)}"><i class="fas fa-calendar me-1" aria-hidden="true"></i>${escapeHtml(relTime)}</span>
                ${matchScore}
            </div>
        </div>
        <div class="card-right">
            <div class="card-right-top">
                ${followUpIcon}
                ${aiStatusBadge(status)}
            </div>
            <div class="card-right-bottom">
                ${trackingButtonsHtml(status, appId)}
                <button class="card-delete-btn" data-action="delete" data-id="${safeAppId}" aria-label="Delete application">
                    <i class="fas fa-trash-alt" aria-hidden="true"></i>
                </button>
            </div>
        </div>
    </div>
</div>`;
    }

    // =============================================================================
    // RENDER — list
    // =============================================================================

    function renderApplications(reset: boolean, pageChunk?: DashboardApplication[]): void {
        const list = document.getElementById('applicationsList');
        if (!list) return;

        if (_loadedApps.length === 0) {
            list.innerHTML = `
                <div class="empty-state" role="status">
                    <i class="fas fa-file-alt" aria-hidden="true"></i>
                    <h5>No applications yet</h5>
                    <p>Start tracking your job applications by clicking <strong>New Application</strong> above.</p>
                </div>`;
            return;
        }

        if (reset) {
            list.innerHTML = _loadedApps.map(renderCard).join('');
        } else {
            const chunk = pageChunk || [];
            const html = chunk.map(renderCard).join('');
            if (html) list.insertAdjacentHTML('beforeend', html);
        }
    }

    // =============================================================================
    // UI STATE UPDATES
    // =============================================================================

    function updateResultsCount() {
        const el = document.getElementById('resultsCount');
        if (el) el.classList.add('is-hidden');
    }

    function updateFilterIndicator() { /* no indicator needed */ }

    function updateLoadMoreButton() {
        const wrapper = document.getElementById('loadMoreWrapper');
        if (!wrapper) return;
        const hasMore = _loadedApps.length < _totalCount;
        wrapper.classList.toggle('is-hidden', !hasMore);
        const btn = document.getElementById('loadMoreBtn');
        if (btn) btn.textContent = `Load more (${_totalCount - _loadedApps.length} remaining)`;
    }

    function updateBulkBar() {
        const bar    = document.getElementById('bulkActionsBar');
        const count  = document.getElementById('selectedCount');
        const selAll = document.getElementById('selectAllCheckbox') as HTMLInputElement | null;
        if (!bar) return;

        const n = _selected.size;
        bar.classList.toggle('is-hidden', n === 0);
        if (count) count.textContent = `${n} selected`;

        if (selAll) {
            const visibleIds = _loadedApps.map((a) => String(a.id ?? ''));
            const allVisible = visibleIds.length > 0 && visibleIds.every(id => _selected.has(id));
            selAll.checked = allVisible;
            selAll.indeterminate = n > 0 && !allVisible;
        }
    }

    // =============================================================================
    // DATA LOADING
    // =============================================================================

    /**
     * @param {boolean} [reset] — true starts from page 1 and replaces the list
     */
    async function loadApplications(reset = true) {
        if (_isLoading) {
            if (reset) _pendingLoadApplicationsReset = true;
            return _loadApplicationsInFlight ?? Promise.resolve();
        }

        const run = (async () => {
            let passReset = reset;
            _isLoading = true;
            try {
                for (;;) {
                    await _loadApplicationsSinglePass(passReset);
                    if (_pendingLoadApplicationsReset) {
                        _pendingLoadApplicationsReset = false;
                        passReset = true;
                        continue;
                    }
                    break;
                }
            } finally {
                _isLoading = false;
            }
        })();

        _loadApplicationsInFlight = run;
        try {
            await run;
        } finally {
            _loadApplicationsInFlight = null;
        }
    }

    async function _loadApplicationsSinglePass(reset: boolean): Promise<void> {
        const list = document.getElementById('applicationsList');
        if (!list) return;

        if (reset) {
            _nextPage   = 1;
            _loadedApps = [];
            _selected.clear();
            updateBulkBar();
            if (_firstLoad) {
                // skeleton is already in the template HTML; leave it as-is
            } else {
                list.classList.add('list-refreshing');
            }
        }

        const loadMoreBtn = document.getElementById('loadMoreBtn');
        if (loadMoreBtn && !reset) {
            loadMoreBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2" aria-hidden="true"></i>Loading…';
            loadMoreBtn.setAttribute('disabled', 'disabled');
        }

        try {
            const token = getAuthToken();
            if (!token) {
                list.innerHTML = `<div class="alert alert-warning"><i class="fas fa-exclamation-triangle me-2" aria-hidden="true"></i>Authentication error. Please <a href="#" id="dashLogoutLink">log out</a> and log in again.</div>`;
                document.getElementById('dashLogoutLink')?.addEventListener('click', (e) => { e.preventDefault(); logout(); });
                return;
            }

            const params = new URLSearchParams({
                page:     String(_nextPage),
                per_page: String(PER_PAGE),
                sort:     _sort,
            });
            if (_search) params.set('search', _search);
            if (_status) params.set('status_filter', _status.toUpperCase());
            if (_days)   params.set('days', _days);

            const response = await fetch(`${API_BASE}/applications/?${params}`, {
                headers: { Authorization: `Bearer ${token}` },
            });

            if (response.ok) {
                const data = (await response.json()) as ApplicationsListResponse;
                _totalCount = data.total || 0;
                const pageApps = dedupeApplicationsById(data.applications || []);
                if (reset) {
                    _loadedApps = pageApps;
                    renderApplications(true);
                } else {
                    const { merged, appended } = mergeApplicationsPage(_loadedApps, pageApps);
                    _loadedApps = merged;
                    renderApplications(false, appended);
                }
                _nextPage++;
                syncProcessingApps();
                if (_firstLoad) _firstLoad = false;
                updateResultsCount();
                updateFilterIndicator();
                updateLoadMoreButton();
                saveFilterState();

            } else if (response.status === 401) {
                logout();
            } else if (response.status === 403) {
                list.innerHTML = `
                    <div class="text-center py-5">
                        <i class="fas fa-user-circle fa-3x text-muted mb-3" aria-hidden="true"></i>
                        <h5>Profile setup required</h5>
                        <p class="text-muted">Complete your profile to start tracking job applications.</p>
                        <a href="/profile/setup" class="btn btn-primary mt-2">Finish Setup</a>
                    </div>`;
            } else {
                const errData = await response.json().catch(() => ({}));
                notify(errData.message || errData.detail || 'Failed to load applications.', 'error');
            }
        } catch (error) {
            const err = /** @type {Error} */ (error);
            console.error('Error loading applications:', err);
            if (list && reset) {
                list.innerHTML = `<div class="alert alert-danger"><i class="fas fa-exclamation-triangle me-2" aria-hidden="true"></i>Error loading applications. Please try again.</div>`;
            } else {
                notify('Error loading more applications. Please try again.', 'error');
            }
        } finally {
            if (reset) list.classList.remove('list-refreshing');
            if (loadMoreBtn && !reset) {
                loadMoreBtn.removeAttribute('disabled');
                updateLoadMoreButton();
            }
        }
    }

    // =============================================================================
    // BACKGROUND PROCESSING POLL
    // =============================================================================

    /** Scans _loadedApps for any in 'processing' state and registers them for polling. */
    function syncProcessingApps() {
        const doneStatuses = ['completed', 'analysis_complete', 'awaiting_confirmation'];
        for (const app of _loadedApps) {
            const status = String(app.status ?? '').toLowerCase();
            const sessionId = String(app.workflow_session_id || app.id || '');

            if (status === 'processing') {
                const id = String(app.id ?? '');
                if (!_processingApps.has(id)) {
                    _processingApps.set(id, {
                        detailId:    sessionId,
                        jobTitle:    String(app.job_title    || 'Job Application'),
                        companyName: displayCompanyNameOrUnknown(app.company_name),
                    });
                }
            } else if (doneStatuses.includes(status) && sessionId && !_isAnalysisNotified(sessionId, false)) {
                notifyReady(
                    String(app.job_title    || 'Job Application'),
                    displayCompanyNameOrUnknown(app.company_name),
                    sessionId,
                    false,
                    '',
                );
            }
        }
        if (_processingApps.size > 0 && _pollTimer === null) {
            _pollTimer = window.setInterval(pollProcessingApps, POLL_INTERVAL_MS);
        }
    }

    /** Polls workflow status for each tracked processing app and fires notifications on completion. */
    async function pollProcessingApps() {
        if (_processingApps.size === 0) {
            if (_pollTimer !== null) { clearInterval(_pollTimer); _pollTimer = null; }
            return;
        }
        const token = getAuthToken();
        if (!token) return;

        const finished: Array<{
            id: string;
            detailId: string;
            jobTitle: string;
            companyName: string;
            failed: boolean;
            failureDetail: string;
        }> = [];

        for (const [id, info] of _processingApps) {
            try {
                const res = await fetch(`${API_BASE}/workflow/status/${encodeURIComponent(info.detailId)}`, {
                    headers: { Authorization: `Bearer ${token}` },
                });
                if (!res.ok) continue;
                const data = (await res.json()) as WorkflowStatusResponse;
                const wfStatus = String(data.status || '').toLowerCase();
                const done  = ['completed', 'analysis_complete', 'awaiting_confirmation'].includes(wfStatus);
                const failed = wfStatus === 'failed';
                let failureDetail = '';
                if (failed && Array.isArray(data.error_messages) && data.error_messages.length > 0) {
                    failureDetail = String(data.error_messages[0] || '');
                }
                if (done || failed) {
                    finished.push({ id, ...info, failed, failureDetail });
                    _processingApps.delete(id);
                }
            } catch (_e) { /* network hiccup — retry next tick */ }
        }

        for (const app of finished) {
            // Skip if the WebSocket handler already fired this notification.
            if (!_isAnalysisNotified(app.detailId, app.failed)) {
                notifyReady(app.jobTitle, app.companyName, app.detailId, app.failed, app.failureDetail);
            }
        }

        if (finished.length > 0) {
            loadApplications(true);
            loadStats();
        }

        if (_processingApps.size === 0 && _pollTimer !== null) {
            clearInterval(_pollTimer);
            _pollTimer = null;
        }
    }

    function _terminalNotifyKey(sessionId: string, failed: boolean): string {
        return failed ? `f:${sessionId}` : `c:${sessionId}`;
    }

    function notifyReady(
        jobTitle: string,
        companyName: string,
        detailId: string,
        failed: boolean,
        failureDetail = '',
    ): void {
        // Guard: if already notified for this outcome (e.g. WS + poll race), bail out.
        if (detailId && _isAnalysisNotified(detailId, failed)) return;

        const container = document.getElementById('alertContainer');
        if (!container) return;

        // Mark BEFORE creating the DOM element so any concurrent call that
        // checks _isAnalysisNotified sees it as already handled.
        _markAnalysisNotified(detailId, failed);

        // Dismiss any lingering "Application submitted" toast
        container.querySelectorAll('.alert').forEach(el => {
            if (el.textContent && el.textContent.includes('analyzing it in the background')) {
                el.classList.remove('show');
                setTimeout(() => el.remove(), 200);
            }
        });

        const detail = formatWorkflowFailureDetail(
            typeof failureDetail === 'string' ? failureDetail.trim() : ''
        );
        const shortDetail = detail.length > 220 ? `${detail.slice(0, 217)}…` : detail;

        const isDuplicateJob =
            failed && /already have an application for this job/i.test(shortDetail);

        let subline = '';
        if (!failed) {
            subline = `${escapeHtml(jobTitle)} at ${escapeHtml(companyName)}`;
        } else if (shortDetail) {
            subline = escapeHtml(shortDetail);
        } else if (jobTitle === 'Job Application' && (companyName === 'Company' || companyName === 'Unknown')) {
            subline = escapeHtml(
                'No job title or company was extracted. Try again with more detail, or check AI Setup.'
            );
        } else {
            subline = `${escapeHtml(jobTitle)} at ${escapeHtml(companyName)}`;
        }

        const headline = !failed
            ? 'Analysis ready!'
            : isDuplicateJob
                ? 'Duplicate job — not added'
                : 'Analysis failed';

        // Failed / incomplete: no navigation — analyses that errored are not listed.
        const detailBtn = failed
            ? ''
            : `<a href="/dashboard/application/${encodeURIComponent(detailId)}" class="btn btn-sm btn-primary flex-shrink-0">View Results</a>`;

        const div = document.createElement('div');
        div.className = `alert alert-${failed ? 'warning' : 'success'} fade show`;
        div.setAttribute('role', 'alert');
        div.innerHTML = `
            <div class="d-flex align-items-center gap-2 w-100">
                <i class="fas ${failed ? 'fa-exclamation-circle' : 'fa-check-circle'} flex-shrink-0" aria-hidden="true"></i>
                <div class="flex-grow-1">
                    <strong>${headline}</strong>
                    <div class="notify-ready-sub">${subline}</div>
                </div>
                ${detailBtn}
                <button type="button" class="btn-close ms-2 flex-shrink-0" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>`;
        container.appendChild(div);
    }

    function _markAnalysisNotified(sessionId: string, failed: boolean): void {
        if (!sessionId) return;
        try {
            const raw = localStorage.getItem('rolemule_notified_analyses') || '[]';
            const set = /** @type {string[]} */ (JSON.parse(raw));
            const key = _terminalNotifyKey(sessionId, failed);
            if (!set.includes(key)) {
                set.push(key);
                // Keep only last 80 entries (c: + f: keys) to avoid unbounded growth
                if (set.length > 80) set.splice(0, set.length - 80);
                localStorage.setItem('rolemule_notified_analyses', JSON.stringify(set));
            }
        } catch (_e) {}
    }

    function _isAnalysisNotified(sessionId: string, failed: boolean): boolean {
        try {
            const raw = localStorage.getItem('rolemule_notified_analyses') || '[]';
            const set = /** @type {string[]} */ (JSON.parse(raw));
            const key = _terminalNotifyKey(sessionId, failed);
            if (set.includes(key)) return true;
            // Legacy: bare id meant "completion" toast already shown
            if (!failed && set.includes(sessionId)) return true;
            return false;
        } catch (_e) { return false; }
    }

    // =============================================================================
    // USER-LEVEL WEBSOCKET
    // =============================================================================

    function connectUserWs() {
        const token = getAuthToken();
        if (!token || typeof WebSocket === 'undefined') return;

        const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
        _ws = new WebSocket(
            `${proto}://${window.location.host}/api/v1/ws/user?token=${encodeURIComponent(token)}`
        );

        _ws.onopen = () => { _wsReconnectAttempts = 0; };

        _ws.onmessage = (event) => {
            try { handleUserWsMessage(/** @type {Record<string,any>} */ (JSON.parse(event.data))); }
            catch (_e) {}
        };

        _ws.onclose = (event) => {
            _ws = null;
            const noRetry = [1000, 1008, 4001];
            if (noRetry.includes(event.code) || _wsReconnectAttempts >= WS_MAX_RECONNECT) return;
            const delay = Math.min(1000 * Math.pow(2, _wsReconnectAttempts), 30000);
            _wsReconnectAttempts++;
            setTimeout(connectUserWs, delay);
        };

        _ws.onerror = () => {}; // onclose fires after onerror — handled there
    }

    async function handleUserWsMessage(msg: Record<string, unknown>): Promise<void> {
        const type      = String(msg.type || '');
        const sessionId = String(msg.session_id || '');
        if (type !== 'workflow_complete' && type !== 'workflow_error' && type !== 'agent_update') return;

        const appBefore = _loadedApps.find(
            (a) => String(a.workflow_session_id || a.id) === sessionId,
        );

        // A new session started (e.g. submitted from the extension in another tab) —
        // show one submitted toast and refresh so the card appears immediately.
        if (type === 'agent_update' && !appBefore) {
            if (!hasSubmittedToastForSession(sessionId)) {
                rememberSubmittedToast(sessionId);
                notify('Application submitted! AI agents are analyzing it in the background.', 'success', true);
            }
            loadApplications(true);
            loadStats();
            return;
        }

        if (type !== 'workflow_complete' && type !== 'workflow_error') return;

        // Remove from polling fallback map — WS beat the poll
        if (appBefore) _processingApps.delete(String(appBefore.id ?? ''));

        await loadApplications(true);
        loadStats();

        const appAfter = _loadedApps.find(
            (a) => String(a.workflow_session_id || a.id) === sessionId,
        );
        const jobTitle = appAfter ? String(appAfter.job_title || 'Job Application') : 'Job Application';
        const companyName = appAfter
            ? displayCompanyNameOrUnknown(appAfter.company_name)
            : 'Unknown';

        let wsFailureDetail = '';
        if (type === 'workflow_error') {
            const d = msg.data;
            // `d &&` already excludes null; avoid `d !== null` (CodeQL incompatible-types).
            if (d && typeof d === 'object' && 'error' in d) {
                wsFailureDetail = String((d as { error?: unknown }).error ?? '');
            }
        }

        notifyReady(jobTitle, companyName, sessionId, type === 'workflow_error', wsFailureDetail);
    }

    // =============================================================================
    // FILTER HELPERS
    // =============================================================================

    function applyFilters(): void {
        const searchEl = document.getElementById('searchInput') as HTMLInputElement | null;
        const statusEl = document.getElementById('statusFilter') as HTMLSelectElement | null;
        const dateEl = document.getElementById('dateFilter') as HTMLSelectElement | null;
        const sortEl = document.getElementById('sortFilter') as HTMLSelectElement | null;

        _search = searchEl?.value.trim() ?? '';
        _status = statusEl?.value ?? '';
        _days   = dateEl?.value   ?? '';
        _sort   = sortEl?.value   ?? 'created_desc';

        loadApplications(true);
    }

    function clearFilters(): void {
        _search = ''; _status = ''; _days = ''; _sort = 'created_desc';

        const searchEl = document.getElementById('searchInput') as HTMLInputElement | null;
        const statusEl = document.getElementById('statusFilter') as HTMLSelectElement | null;
        const dateEl = document.getElementById('dateFilter') as HTMLSelectElement | null;
        const sortEl = document.getElementById('sortFilter') as HTMLSelectElement | null;

        if (searchEl) searchEl.value = '';
        if (statusEl) statusEl.value = '';
        if (dateEl)   dateEl.value   = '';
        if (sortEl)   sortEl.value   = 'created_desc';

        loadApplications(true);
    }

    // =============================================================================
    // SELECTION
    // =============================================================================

    function toggleSelectAll() {
        const selAll = document.getElementById('selectAllCheckbox') as HTMLInputElement | null;
        const visibleIds = _loadedApps.map((a) => String(a.id ?? ''));

        if (selAll?.checked) {
            visibleIds.forEach(id => _selected.add(id));
        } else {
            visibleIds.forEach(id => _selected.delete(id));
        }

        // Sync checkboxes in the DOM
        document.querySelectorAll('.app-checkbox').forEach((cb) => {
            const checkbox = cb as HTMLInputElement;
            checkbox.checked = _selected.has(checkbox.dataset.id ?? '');
        });

        updateBulkBar();
    }

    // =============================================================================
    // APPLICATION ACTIONS
    // =============================================================================

    function viewApplication(id: string): void {
        const app = _loadedApps.find(
            (a) => String(a.workflow_session_id || a.id) === id,
        );
        if (app && String(app.status ?? '').toLowerCase() === 'processing') {
            notify('Still analyzing — we\'ll notify you here when it\'s ready.', 'info');
            return;
        }
        saveFilterState();
        window.location.href = `/dashboard/application/${encodeURIComponent(id)}`;
    }

    async function updateApplicationStatus(applicationId: string, newStatus: string): Promise<void> {
        const token = getAuthToken();
        try {
            const response = await fetch(`${API_BASE}/applications/${applicationId}/status`, {
                method: 'PATCH',
                headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_status: newStatus }),
            });
            if (response.ok) {
                // Update in-memory so badge + relative time refresh without a full reload
                const app = _loadedApps.find((a) => String(a.id) === applicationId);
                if (app) {
                    app.status = newStatus;
                    app.updated_at = new Date().toISOString();
                }
                renderApplications(true);
                updateResultsCount();
                updateFilterIndicator();
                updateLoadMoreButton();
                loadStats();
                const trackingStatuses = ['applied', 'interview', 'accepted', 'rejected'];
                const msg = trackingStatuses.includes(newStatus.toLowerCase())
                    ? `Marked as ${formatStatus(newStatus)}.`
                    : 'Stage cleared.';
                notify(msg, 'success');
            } else {
                const errData = await response.json().catch(() => ({}));
                throw new Error(errData.message || errData.detail || 'Failed to update status');
            }
        } catch (error) {
            const err = error instanceof Error ? error : new Error(String(error));
            console.error('Error updating status:', err);
            notify(err.message || 'Failed to update status. Please try again.', 'error');
            // Re-render to reset the dropdown to its previous value
            renderApplications(true);
        }
    }

    async function deleteApplication(applicationId: string): Promise<void> {
        if (!window.showConfirm) return;
        const confirmed = await window.showConfirm({
            title: 'Delete Application',
            message: 'Are you sure you want to delete this application? This action cannot be undone.',
            confirmText: 'Delete',
            type: 'danger',
        });
        if (!confirmed) return;

        const token = getAuthToken();
        try {
            const response = await fetch(`${API_BASE}/applications/${applicationId}`, {
                method: 'DELETE',
                headers: { Authorization: `Bearer ${token}` },
            });
            if (response.ok) {
                _loadedApps = _loadedApps.filter((a) => String(a.id) !== applicationId);
                _totalCount = Math.max(0, _totalCount - 1);
                _selected.delete(applicationId);
                renderApplications(true);
                updateResultsCount();
                updateFilterIndicator();
                updateLoadMoreButton();
                updateBulkBar();
                loadStats();
                notify('Application deleted.', 'success');
            } else {
                const errData = await response.json().catch(() => ({}));
                throw new Error(errData.message || errData.detail || 'Failed to delete application');
            }
        } catch (error) {
            const err = error instanceof Error ? error : new Error(String(error));
            console.error('Error deleting application:', err);
            notify(err.message || 'Failed to delete application. Please try again.', 'error');
        }
    }

    async function bulkDelete() {
        const ids = Array.from(_selected);
        if (ids.length === 0) return;

        if (!window.showConfirm) return;
        const confirmed = await window.showConfirm({
            title: 'Delete Applications',
            message: `Are you sure you want to delete ${ids.length} application${ids.length > 1 ? 's' : ''}? This action cannot be undone.`,
            confirmText: `Delete ${ids.length}`,
            type: 'danger',
        });
        if (!confirmed) return;

        const token = getAuthToken();
        const errors: string[] = [];
        await Promise.all(ids.map(async id => {
            try {
                const r = await fetch(`${API_BASE}/applications/${id}`, {
                    method: 'DELETE',
                    headers: { Authorization: `Bearer ${token}` },
                });
                if (!r.ok) errors.push(id);
            } catch (e) { errors.push(id); }
        }));

        if (errors.length > 0) {
            notify(`${errors.length} deletion${errors.length > 1 ? 's' : ''} failed. Please try again.`, 'error');
        } else {
            notify(`${ids.length} application${ids.length > 1 ? 's' : ''} deleted.`, 'success');
        }

        _selected.clear();
        loadApplications(true);
        loadStats();
    }

    // =============================================================================
    // STATS
    // =============================================================================

    async function loadStats() {
        const token = getAuthToken();
        if (!token) return;
        try {
            const response = await fetch(`${API_BASE}/applications/stats/overview`, {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (response.ok) {
                const stats = (await response.json()) as ApplicationStatsResponse;
                const set = (id: string, val: unknown): void => {
                    const el = document.getElementById(id);
                    if (el) el.textContent = String(val ?? 0);
                };
                set('totalApplications', stats.total);
                set('appliedCount',      stats.applied);
                set('interviewCount',    stats.interviews);
                const rateEl = document.getElementById('responseRate');
                if (rateEl) rateEl.textContent = `${stats.response_rate || 0}%`;
            }
        } catch (error) {
            console.error('Error loading stats:', error);
        }
    }

    // =============================================================================
    // AUTH CHECK + USER DATA
    // =============================================================================

    function checkAuthentication(): boolean {
        if (!isAuthenticated()) {
            window.location.href = getLoginUrl();
            return false;
        }
        return true;
    }

    async function loadUserData(): Promise<boolean> {
        const token = getAuthToken();
        if (!token) {
            window.location.href = getLoginUrl();
            return false;
        }
        try {
            const response = await fetch(`${API_BASE}/profile/`, { headers: { Authorization: `Bearer ${token}` } });
            if (response.ok) {
                const data = (await response.json()) as {
                    completion_status?: { profile_completed?: boolean };
                    user_info?: { full_name?: string };
                };
                const completed = Boolean(data.completion_status?.profile_completed);
                localStorage.setItem('profile_completed', completed ? 'true' : 'false');
                if (!completed) {
                    window.location.href = '/profile/setup?edit=true';
                    return false;
                }
                const fullName   = data.user_info?.full_name || 'User';
                const userNameEl = document.getElementById('userName');
                if (userNameEl) userNameEl.textContent = fullName;
                else {
                    const welcomeEl = document.getElementById('welcomeMessage');
                    if (welcomeEl) welcomeEl.textContent = `Welcome back, ${fullName}!`;
                }
                const avatarEl = document.getElementById('userAvatar');
                if (avatarEl) avatarEl.textContent = fullName[0].toUpperCase();
                return true;
            } else if (response.status === 401) {
                logout();
                return false;
            } else if (response.status === 404) {
                window.location.href = '/profile/setup?edit=true';
                return false;
            }
            return false;
        } catch (error) {
            console.error('Error loading user data:', error);
            return false;
        }
    }

    // =============================================================================
    // OAUTH EXCHANGE
    // =============================================================================

    async function exchangeOAuthCodeIfPresent(): Promise<void> {
        const urlParams = new URLSearchParams(window.location.search);
        const code = urlParams.get('code');
        if (!code) return;

        urlParams.delete('code');
        const newSearch = urlParams.toString();
        history.replaceState(null, '', window.location.pathname + (newSearch ? '?' + newSearch : ''));

        try {
            const response = await fetch(`${API_BASE}/auth/oauth/exchange-code`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code }),
            });
            if (!response.ok) return;
            const data = (await response.json()) as { access_token?: string };
            const token = data.access_token;
            if (token) setAuthToken(token);
        } catch (err) {
            const error = err instanceof Error ? err : new Error(String(err));
            console.error('OAuth code exchange failed:', error.message);
        }
    }

    // =============================================================================
    // EVENT WIRING
    // =============================================================================

    document.addEventListener('DOMContentLoaded', async function () {
        await exchangeOAuthCodeIfPresent();
        if (!checkAuthentication()) return;

        const profileOk = await loadUserData();
        if (!profileOk) return;

        connectUserWs();

        // Clear the navbar badge dot — user is on the dashboard, toasts appear natively
        if (typeof window.clearNavBadge === 'function') window.clearNavBadge();

        // Show toast if redirected here after submitting a new application
        const newAppToast = sessionStorage.getItem('new_application_toast');
        const newAppSid = sessionStorage.getItem('new_application_session_id');
        if (newAppToast) {
            sessionStorage.removeItem('new_application_toast');
            sessionStorage.removeItem('new_application_session_id');
            if (newAppSid) rememberSubmittedToast(newAppSid);
            notify(newAppToast, 'success', true);
        }

        // Restore filter state from sessionStorage (browser back navigation)
        const savedScrollY = restoreFilterState();

        loadStats();

        // Initial load — use restored filters
        await loadApplications(true);

        // After first render, scroll to saved position
        if (savedScrollY > 0) {
            requestAnimationFrame(() => { window.scrollTo(0, savedScrollY); });
        }

        // ── Filter controls ──────────────────────────────────────────────────────
        document.getElementById('statusFilter')?.addEventListener('change', applyFilters);
        document.getElementById('dateFilter')?.addEventListener('change', applyFilters);
        document.getElementById('sortFilter')?.addEventListener('change', applyFilters);

        // Search — debounced 300 ms
        document.getElementById('searchInput')?.addEventListener('input', function () {
            if (_searchTimer !== null) clearTimeout(_searchTimer);
            _searchTimer = window.setTimeout(applyFilters, 300);
        });

        // Escape key clears search
        document.getElementById('searchInput')?.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && e.target instanceof HTMLInputElement) {
                if (e.target.value !== '') {
                    e.target.value = '';
                    applyFilters();
                }
            }
        });

        document.addEventListener('click', (e) => {
            const el = e.target;
            if (!(el instanceof HTMLElement)) return;
            const actionEl = el.closest('[data-action]') as HTMLElement | null;
            if (!actionEl) return;
            switch (actionEl.dataset['action']) {
                case 'clear-filters':  clearFilters();   break;
                case 'load-more':      loadApplications(false); break;
                case 'bulk-delete':    bulkDelete();     break;
                case 'logout':         e.preventDefault(); logout(); break;
            }
        });

        // ── Delegated clicks on dynamically rendered cards ────────────────────────
        const list = document.getElementById('applicationsList');
        if (list) {
            list.addEventListener('click', (e) => {
                const el = e.target;
                if (!(el instanceof HTMLElement)) return;

                if (el.closest('input')) {
                    e.stopPropagation();
                    return;
                }

                const actionEl = el.closest('[data-action]') as HTMLElement | null;
                if (actionEl) {
                    e.stopPropagation();
                    const id = actionEl.dataset.id ?? '';
                    const action = actionEl.dataset.action ?? '';
                    if (action === 'delete') void deleteApplication(id);
                    if (action === 'set-tracking') {
                        const chosen = actionEl.dataset.value ?? '';
                        const existingApp = _loadedApps.find((a) => String(a.id) === id);
                        const currentStatus = existingApp
                            ? String(existingApp.status || '').toLowerCase()
                            : '';
                        void updateApplicationStatus(
                            id,
                            currentStatus === chosen ? 'completed' : chosen,
                        );
                    }
                    return;
                }

                const card = el.closest('[data-card-id]') as HTMLElement | null;
                if (card) viewApplication(card.dataset.cardId ?? '');
            });

            list.addEventListener('change', (e) => {
                const el = e.target;
                if (!(el instanceof HTMLInputElement)) return;
                const action = el.dataset.action;

                if (action === 'toggle-select') {
                    if (el.checked) _selected.add(el.dataset.id ?? '');
                    else _selected.delete(el.dataset.id ?? '');
                    updateBulkBar();
                }
            });
        }

        // ── Select all checkbox ───────────────────────────────────────────────────
        document.getElementById('selectAllCheckbox')?.addEventListener('change', toggleSelectAll);

        // ── Navbar logout (app.js not loaded on dashboard pages) ─────────────────
        // (handled by the document-level click delegation above)

        // ── Clean up WS and poll timer on navigation ─────────────────────────────
        window.addEventListener('beforeunload', () => {
            if (_ws) { _ws.onclose = null; _ws.close(1000); _ws = null; }
            if (_pollTimer !== null) { clearInterval(_pollTimer); _pollTimer = null; }
        });
    });

    // =============================================================================
    // PUBLIC API
    // =============================================================================
window.logout = logout;

