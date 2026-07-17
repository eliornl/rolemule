/**
 * RoleMule - Chrome Extension Popup
 * Handles user authentication, job extraction, and API communication
 */

// =============================================================================
// CONFIGURATION
// =============================================================================

// ⚠️  BEFORE PUBLISHING: Set IS_DEV = false and fill in PRODUCTION_URL below.
const IS_DEV = true;
const DEV_URL = 'http://localhost:8000';
const PRODUCTION_URL = 'https://YOUR_CLOUD_RUN_URL.a.run.app';
const BASE_URL = IS_DEV ? DEV_URL : PRODUCTION_URL;

const CONFIG = {
  API_BASE_URL: `${BASE_URL}/api/v1`,
  DASHBOARD_URL: `${BASE_URL}/dashboard`,
  APP_URL: BASE_URL,
  STORAGE_KEYS: {
    TOKEN: 'jaa_token',
    USER: 'jaa_user',
    API_URL: 'jaa_api_url'
  }
};

/** Injected into the page tab; shared with the background context menu path. */
const JAA_EXTRACT_FILE = 'lib/extract-page-content.js';
/** Form field serialize + apply (main document MVP). */
const JAA_FORM_AUTOFILL_FILE = 'lib/form-autofill.js';
/** MAIN world: hooks fetch/XHR on job search so Voyager JSON can be cached for extraction */
const JAA_LI_MAIN_HOOK_FILE = 'lib/linkedin-voyager-hook.js';
/** MAIN world: prefetch jobs-guest API body into sessionStorage (isolated extractor reads it). */
const JAA_LI_GUEST_PREFETCH_FILE = 'lib/linkedin-guest-prefetch.js';

/**
 * Loads the page extractor and returns `{ content, title, source?, diagnostics? }` from the tab.
 * `@param {{ forceDiagnostics?: boolean }} options` — when true, sets debug before extract (page `localStorage`
 * alone does not reach the extension isolated world where the extractor runs).
 * @param {number} tabId
 * @returns {Promise<{ content: string, title: string, source?: string, diagnostics?: object, error?: string }>}
 */
async function runExtractPageContent(tabId, options = {}) {
  let forceDiagnostics = !!options.forceDiagnostics;
  if (!forceDiagnostics) {
    try {
      const st = await chrome.storage.local.get(['extract_diagnostics']);
      if (st.extract_diagnostics === true) forceDiagnostics = true;
    } catch (e) {
      /* ignore */
    }
  }
  if (!forceDiagnostics) forceDiagnostics = IS_DEV;

  try {
    const tabInfo = await chrome.tabs.get(tabId);
    const tabUrl = tabInfo.url || '';
    if (isLinkedInJobsUrl(tabUrl)) {
      await chrome.scripting.executeScript({
        target: { tabId },
        files: [JAA_LI_MAIN_HOOK_FILE],
        world: 'MAIN'
      });
      await chrome.scripting.executeScript({
        target: { tabId },
        files: [JAA_LI_GUEST_PREFETCH_FILE],
        world: 'MAIN'
      });
      await new Promise(function (r) {
        setTimeout(r, 750);
      });
    }
  } catch (eHook) {
    /* ignore — tab closed or no permission */
  }

  await chrome.scripting.executeScript({
    target: { tabId },
    files: [JAA_EXTRACT_FILE]
  });
  const [exec] = await chrome.scripting.executeScript({
    target: { tabId },
    func: async (diag) => {
      try {
        if (diag) window.__JAA_EXTRACT_DEBUG = true;
      } catch (e) {
        /* ignore */
      }
      const runAsync = window.__jaaExtractPageContentAsync;
      if (typeof runAsync === 'function') {
        return await runAsync();
      }
      const fn = window.__jaaExtractPageContent;
      if (typeof fn !== 'function') {
        return {
          content: '',
          title: document.title || '',
          error: 'extractor_missing'
        };
      }
      return fn();
    },
    args: [forceDiagnostics]
  });
  return exec.result;
}

/**
 * @param {number} tabId
 * @returns {Promise<{ fields: Array<Record<string, unknown>>, page_url: string, warnings?: string[] }>}
 */
async function runSerializeAutofill(tabId, educationCount) {
  await chrome.scripting.executeScript({
    target: { tabId },
    files: [JAA_FORM_AUTOFILL_FILE]
  });
  const [exec] = await chrome.scripting.executeScript({
    target: { tabId },
    func: async (eduCount) => {
      var result;
      if (typeof window.__jaaSerializeAutofillFieldsAsync === 'function') {
        result = await window.__jaaSerializeAutofillFieldsAsync(eduCount);
      } else if (typeof window.__jaaSerializeAutofillFields === 'function') {
        result = window.__jaaSerializeAutofillFields();
      } else {
        return { fields: [], page_url: String(location.href || ''), warnings: ['Serializer not loaded'] };
      }
      try {
        var n = result && result.fields ? result.fields.length : 0;
        console.warn('[RoleMule] scan found ' + n + ' field(s)');
        if (result && result.fields) {
          console.warn(
            '[RoleMule] scan labels:',
            result.fields.map(function (f) {
              return (f.input_type || f.tag || '?') + ': ' + String(f.label_text || '').slice(0, 100);
            })
          );
        }
        if (result && result.education_expand) {
          console.warn('[RoleMule] education expand:', result.education_expand);
        }
        if (result && result.scan_debug) {
          console.warn('[RoleMule] scan debug:', result.scan_debug);
          console.warn(
            '[RoleMule] scan debug — sponsorship in fields:',
            result.scan_debug.sponsorship_in_fields,
            '| minimal Yes/No containers:',
            result.scan_debug.minimal_pair_containers
              ? result.scan_debug.minimal_pair_containers.length
              : 0,
            '| text hits:',
            result.scan_debug.sponsorship_text_hits
          );
        } else {
          console.warn(
            '[RoleMule] scan debug: (missing — reload extension at chrome://extensions)'
          );
        }
      } catch (logErr) {
        /* ignore */
      }
      return result;
    },
    args: [typeof educationCount === 'number' ? educationCount : 0]
  });
  return exec.result;
}

/**
 * @param {number} tabId
 * @param {Array<{ field_uid: string, value: string }>} assignments
 * @returns {Promise<{ applied: number, failed: number }>}
 */
async function runApplyAutofill(tabId, assignments, educationCount) {
  await chrome.scripting.executeScript({
    target: { tabId },
    files: [JAA_FORM_AUTOFILL_FILE]
  });
  const [exec] = await chrome.scripting.executeScript({
    target: { tabId },
    func: async (payload) => {
      if (typeof window.__jaaApplyAutofillWithRematch === 'function') {
        return await window.__jaaApplyAutofillWithRematch(
          payload.assignments,
          payload.educationCount
        );
      }
      if (typeof window.__jaaApplyAutofillWithRematchSync === 'function') {
        return window.__jaaApplyAutofillWithRematchSync(
          payload.assignments,
          payload.educationCount
        );
      }
      if (typeof window.__jaaApplyAutofillAssignments === 'function') {
        return window.__jaaApplyAutofillAssignments(payload.assignments);
      }
      return { applied: 0, failed: 0 };
    },
    args: [
      {
        assignments: assignments,
        educationCount: typeof educationCount === 'number' ? educationCount : 0
      }
    ]
  });
  return exec.result;
}

/**
 * Name/email assignments only — used to restore profile identity after Ashby resume parsing.
 * @param {Array<{ field_uid: string, value: string, label_text?: string, duplicate_label_index?: number }>} mapped
 * @returns {Array<{ field_uid: string, value: string, label_text?: string, duplicate_label_index?: number }>}
 */
function identityAutofillAssignments(mapped) {
  if (!Array.isArray(mapped)) return [];
  return mapped.filter(function (a) {
    if (!a || !a.value) return false;
    var lab = String(a.label_text || '').toLowerCase();
    if (/company|employer|school|university|reference|hiring\s+manager/.test(lab)) {
      return false;
    }
    if (/\bemail\b/.test(lab)) return true;
    if (/\bname\b/.test(lab) || /^first(\s+|-)?name/.test(lab) || /^last(\s+|-)?name/.test(lab)) {
      return true;
    }
    return false;
  });
}

/**
 * Ashby's resume parser overwrites name/email after upload — re-apply profile values once.
 * @param {number} tabId
 * @param {Array<{ field_uid: string, value: string, label_text?: string }>} mapped
 * @returns {Promise<void>}
 */
async function reapplyAshbyIdentityAfterResume(tabId, mapped) {
  var subset = identityAutofillAssignments(mapped);
  if (!subset.length) return;
  await new Promise(function (resolve) {
    setTimeout(resolve, 1200);
  });
  await runApplyAutofill(tabId, subset, 0);
}

/**
 * Hide Ashby "Autofill from resume" UI in the active tab (profile is source of truth).
 * @param {number} tabId
 * @returns {Promise<void>}
 */
async function suppressAshbyResumeAutofillOnTab(tabId) {
  await chrome.scripting.executeScript({
    target: { tabId },
    files: [JAA_FORM_AUTOFILL_FILE]
  });
  await chrome.scripting.executeScript({
    target: { tabId },
    func: () => {
      if (typeof window.__jaaRestoreAshbyOverhidden === 'function') {
        window.__jaaRestoreAshbyOverhidden();
      }
      if (typeof window.__jaaSuppressAshbyResumeAutofill === 'function') {
        return window.__jaaSuppressAshbyResumeAutofill();
      }
      return { hidden_sections: 0, hidden_banners: 0 };
    }
  });
}

/**
 * @param {number} tabId
 * @returns {Promise<{ attached: number, ashby_upload_failed: boolean }>}
 */
async function attachStoredResumeToTab(tabId) {
  const res = await fetch(`${CONFIG.API_BASE_URL}/profile/resume`, {
    headers: { Authorization: 'Bearer ' + state.token }
  });
  if (!res.ok) return { attached: 0, ashby_upload_failed: false };
  const blob = await res.blob();
  const buf = await blob.arrayBuffer();
  const bytes = new Uint8Array(buf);
  let binary = '';
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  const base64 = btoa(binary);
  let filename = 'resume.pdf';
  const cd = res.headers.get('Content-Disposition') || '';
  const fnMatch = /filename\*?=(?:UTF-8''|")?([^";\n]+)/i.exec(cd);
  if (fnMatch && fnMatch[1]) {
    filename = fnMatch[1].replace(/"/g, '').trim();
  }
  const mimeType = blob.type || 'application/pdf';

  await chrome.scripting.executeScript({
    target: { tabId },
    files: [JAA_FORM_AUTOFILL_FILE]
  });
  const [exec] = await chrome.scripting.executeScript({
    target: { tabId },
    func: (payload) => {
      if (typeof window.__jaaAttachResumeFile === 'function') {
        return window.__jaaAttachResumeFile(payload);
      }
      return { attached: 0 };
    },
    args: [{ base64: base64, filename: filename, mimeType: mimeType }]
  });
  const r = exec && exec.result;
  const attached = r && typeof r.attached === 'number' ? r.attached : 0;
  return {
    attached: attached,
    ashby_upload_failed: !!(r && r.ashby_upload_failed)
  };
}

/**
 * Ashby uploads the file to their servers asynchronously after the input is set.
 * @param {number} tabId
 * @returns {Promise<boolean>}
 */
async function ashbyResumeUploadFailedOnTab(tabId) {
  await new Promise(function (resolve) {
    setTimeout(resolve, 2800);
  });
  await chrome.scripting.executeScript({
    target: { tabId },
    files: [JAA_FORM_AUTOFILL_FILE]
  });
  const [exec] = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => {
      return typeof window.__jaaAshbyResumeUploadFailed === 'function' && window.__jaaAshbyResumeUploadFailed();
    }
  });
  return !!(exec && exec.result);
}

/**
 * @returns {Promise<number>}
 */
async function fetchProfileEducationCount() {
  try {
    const res = await fetch(`${CONFIG.API_BASE_URL}/profile`, {
      headers: { Authorization: 'Bearer ' + state.token }
    });
    if (!res.ok) return 0;
    const data = await res.json();
    const prof = data.profile_data || data.profile || data;
    const edu = prof && prof.education;
    return Array.isArray(edu) ? edu.length : 0;
  } catch (e) {
    console.debug('Education count fetch skipped:', e);
    return 0;
  }
}

// =============================================================================
// DOM ELEMENTS
// =============================================================================

const elements = {
  // Views
  notAuthView: document.getElementById('notAuthView'),
  authView: document.getElementById('authView'),

  // Auth status
  statusDot: document.querySelector('.status-dot'),

  // Login form
  loginForm: document.getElementById('loginForm'),
  loginEmail: document.getElementById('loginEmail'),
  loginPassword: document.getElementById('loginPassword'),
  loginSubmitBtn: document.getElementById('loginSubmitBtn'),
  loginError: document.getElementById('loginError'),
  openRegisterBtn: document.getElementById('openRegisterBtn'),

  // User info
  userInitials: document.getElementById('userInitials'),
  userName: document.getElementById('userName'),
  userEmail: document.getElementById('userEmail'),

  // Job detection
  jobDetection: document.getElementById('jobDetection'),
  detectedSource: document.getElementById('detectedSource'),

  // Buttons
  extractBtn: document.getElementById('extractBtn'),
  copyBtn: document.getElementById('copyBtn'),
  openDashboardBtn: document.getElementById('openDashboardBtn'),
  retryBtn: document.getElementById('retryBtn'),

  // Status displays
  extractionStatus: document.getElementById('extractionStatus'),
  statusText: document.getElementById('statusText'),
  successMessage: document.getElementById('successMessage'),
  errorMessage: document.getElementById('errorMessage'),
  errorTitle: document.getElementById('errorTitle'),
  errorText: document.getElementById('errorText'),

  // Quick links
  dashboardLink: document.getElementById('dashboardLink'),
  settingsLink: document.getElementById('settingsLink'),
  logoutLink: document.getElementById('logoutLink'),
  helpLink: document.getElementById('helpLink'),
  helpLinkFooter: document.getElementById('helpLinkFooter'),

  authMainFlow: document.getElementById('authMainFlow'),
  primaryActionsBlock: document.getElementById('primaryActionsBlock'),
  matchProfileBtn: document.getElementById('matchProfileBtn')
};

// =============================================================================
// STATE
// =============================================================================

let state = {
  isAuthenticated: false,
  user: null,
  token: null,
  currentTab: null,
  detectedJob: null,
  isExtracting: false,
  isLoggingIn: false,
  isAutofillScanning: false
};

// =============================================================================
// INITIALIZATION
// =============================================================================

document.addEventListener('DOMContentLoaded', async () => {
  await initialize();
});

async function initialize() {
  // Load stored credentials
  await loadStoredCredentials();

  // Update UI based on auth state
  updateAuthUI();

  // If authenticated, detect job on current page
  if (state.isAuthenticated) {
    await detectJobOnCurrentPage();
  }

  // Setup event listeners
  setupEventListeners();
}

// =============================================================================
// AUTHENTICATION - Direct Login
// =============================================================================

async function handleLogin(email, password) {
  if (state.isLoggingIn) return;
  state.isLoggingIn = true;

  // Update button state
  elements.loginSubmitBtn.disabled = true;
  elements.loginSubmitBtn.textContent = 'Signing in...';
  elements.loginError.classList.add('hidden');

  try {
    const response = await fetch(`${CONFIG.API_BASE_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });

    const data = await response.json().catch(() => null);

    if (!response.ok) {
      const msg = data?.detail || data?.message || 'Invalid email or password';
      throw new Error(msg);
    }

    if (!data || !data.access_token) {
      throw new Error('No token received from server');
    }

    // Build user object from response
    const user = data.user || {
      email: email,
      full_name: data.full_name || email.split('@')[0]
    };

    // Save credentials
    await saveCredentials(data.access_token, user);

    // Update UI
    updateAuthUI();
    showToast('Signed in successfully!', 'success');

    // Detect job on current page
    await detectJobOnCurrentPage();

  } catch (error) {
    console.error('Login failed:', error);
    elements.loginError.textContent = error.message;
    elements.loginError.classList.remove('hidden');
  } finally {
    state.isLoggingIn = false;
    elements.loginSubmitBtn.disabled = false;
    elements.loginSubmitBtn.textContent = 'Sign In';
  }
}

// =============================================================================
// CREDENTIALS MANAGEMENT
// =============================================================================

async function loadStoredCredentials() {
  try {
    const result = await chrome.storage.local.get([
      CONFIG.STORAGE_KEYS.TOKEN,
      CONFIG.STORAGE_KEYS.USER,
      CONFIG.STORAGE_KEYS.API_URL
    ]);

    if (result[CONFIG.STORAGE_KEYS.API_URL]) {
      CONFIG.API_BASE_URL = result[CONFIG.STORAGE_KEYS.API_URL];
      CONFIG.APP_URL = CONFIG.API_BASE_URL.replace(/\/api\/v1$/, '').replace(/\/api$/, '');
      CONFIG.DASHBOARD_URL = `${CONFIG.APP_URL}/dashboard`;
    }

    if (result[CONFIG.STORAGE_KEYS.TOKEN]) {
      state.token = result[CONFIG.STORAGE_KEYS.TOKEN];
      state.user = result[CONFIG.STORAGE_KEYS.USER] || null;

      // Verify token is still valid
      const isValid = await verifyToken();
      state.isAuthenticated = isValid;

      if (!isValid) {
        await clearCredentials();
      }
    }
  } catch (error) {
    console.error('Failed to load credentials:', error);
  }
}

async function verifyToken() {
  try {
    const response = await fetch(`${CONFIG.API_BASE_URL}/auth/extension-status`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${state.token}`,
        'Content-Type': 'application/json'
      }
    });

    if (response.ok) {
      // Update user info from extension-status response
      const data = await response.json().catch(() => null);
      if (data && data.user) {
        state.user = data.user;
        // Also update storage with latest user info
        await chrome.storage.local.set({
          [CONFIG.STORAGE_KEYS.USER]: data.user
        });
      }
    }

    return response.ok;
  } catch (error) {
    console.error('Token verification failed:', error);
    return false;
  }
}

async function saveCredentials(token, user) {
  try {
    await chrome.storage.local.set({
      [CONFIG.STORAGE_KEYS.TOKEN]: token,
      [CONFIG.STORAGE_KEYS.USER]: user
    });

    state.token = token;
    state.user = user;
    state.isAuthenticated = true;
  } catch (error) {
    console.error('Failed to save credentials:', error);
  }
}

async function clearCredentials() {
  try {
    await chrome.storage.local.remove([
      CONFIG.STORAGE_KEYS.TOKEN,
      CONFIG.STORAGE_KEYS.USER
    ]);

    state.token = null;
    state.user = null;
    state.isAuthenticated = false;
  } catch (error) {
    console.error('Failed to clear credentials:', error);
  }
}

async function logout() {
  try {
    if (state.token) {
      await fetch(`${CONFIG.API_BASE_URL}/auth/logout`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${state.token}`,
          'Content-Type': 'application/json'
        }
      }).catch(() => {});
    }
  } catch (error) {
    console.error('Logout error:', error);
  } finally {
    await clearCredentials();
    updateAuthUI();
    showToast('Logged out successfully', 'success');
  }
}

// =============================================================================
// UI UPDATES
// =============================================================================

function updateAuthUI() {
  if (state.isAuthenticated && state.user) {
    elements.notAuthView.classList.add('hidden');
    elements.authView.classList.remove('hidden');
    elements.statusDot.classList.add('connected');
    elements.statusDot.classList.remove('disconnected');

    const name = state.user.full_name || state.user.email || 'User';
    const initials = getInitials(name);
    elements.userInitials.textContent = initials;
    elements.userName.textContent = name;
    elements.userEmail.textContent = state.user.email || '';
  } else {
    elements.notAuthView.classList.remove('hidden');
    elements.authView.classList.add('hidden');
    elements.statusDot.classList.remove('connected');
    elements.statusDot.classList.add('disconnected');
  }
}

function getInitials(name) {
  const parts = name.split(' ').filter(Boolean);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return (name[0] || '?').toUpperCase();
}

function exitAutofillPreview() {
  state.isAutofillScanning = false;
  if (elements.matchProfileBtn) elements.matchProfileBtn.disabled = false;
}

/**
 * Writes LLM assignments into the active tab (re-injects `form-autofill.js` as needed).
 * @param {number} tabId
 * @param {Array<{ field_uid: string, value: string, label_text?: string }>} mapped
 * @returns {Promise<void>}
 */
async function applyAutofillAssignmentsToTab(tabId, mapped, scanCount, educationCount) {
  const mapFn = mapped.map(function (a) {
    return {
      field_uid: a.field_uid,
      value: a.value,
      label_text: a.label_text || '',
      duplicate_label_index:
        typeof a.duplicate_label_index === 'number' ? a.duplicate_label_index : 0
    };
  });
  const result = await runApplyAutofill(tabId, mapFn, educationCount);
  const n = result && typeof result.applied === 'number' ? result.applied : 0;
  const f = result && typeof result.failed === 'number' ? result.failed : 0;
  const scanned = typeof scanCount === 'number' ? scanCount : 0;
  let msg = 'Scanned ' + scanned + ' field(s), filled ' + n + '. Review before submit.';
  if (f > 0) {
    msg += ' (' + f + ' failed)';
  }
  showToast(msg, f > 0 ? 'info' : 'success', 10000);

  console.log('[RoleMule popup] autofill result', {
    scanned: scanned,
    applied: n,
    failed: f,
    debug: result && result.debug ? result.debug : null
  });

  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      func: (debugPayload) => {
        try {
          if (debugPayload) {
            console.warn('[RoleMule] apply debug — field count: ' + (debugPayload.scanned_field_count || 0));
            console.warn('[RoleMule] apply details:', debugPayload);
          } else if (window.__jaaLastAutofillDebug) {
            console.warn('[RoleMule] apply debug (cached):', window.__jaaLastAutofillDebug);
          } else {
            console.warn('[RoleMule] apply finished but no debug payload was returned.');
          }
        } catch (e) {
          console.warn('[RoleMule] apply debug log error', e);
        }
      },
      args: [result && result.debug ? result.debug : null]
    });
  } catch (logErr) {
    console.debug('Autofill debug log skipped:', logErr);
  }
  return result;
}

async function matchFormToProfile() {
  if (!state.token || state.isExtracting || state.isAutofillScanning) return;
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || tab.id == null) {
    showToast('No active tab found.', 'error');
    return;
  }
  const u = tab.url || '';
  if (u.startsWith('chrome://') || u.startsWith('chrome-extension://') || u.startsWith('edge://')) {
    showToast('Open a job or careers page in a normal browser tab first.', 'info');
    return;
  }

  state.isAutofillScanning = true;
  if (elements.matchProfileBtn) elements.matchProfileBtn.disabled = true;

  try {
    let resumeAttached = 0;
    let ashbyResumeUploadFailed = false;
    const isAshby = /ashbyhq\.com|jobs\.ashby/i.test(u);

    if (isAshby) {
      try {
        await suppressAshbyResumeAutofillOnTab(tab.id);
      } catch (suppressErr) {
        console.debug('Ashby autofill suppress skipped:', suppressErr);
      }
    }

    const eduCount = await fetchProfileEducationCount();

    const serialized = await runSerializeAutofill(tab.id, eduCount);
    const fields = serialized && serialized.fields ? serialized.fields : [];
    if (!fields.length) {
      showToast(
        'No fillable fields found on this page. If the form is inside a frame, open the apply step in the main page.',
        'info',
        8000
      );
      return;
    }

    const res = await fetch(`${CONFIG.API_BASE_URL}/extension/autofill/map`, {
      method: 'POST',
      headers: {
        Authorization: 'Bearer ' + state.token,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        fields: fields,
        page_url: serialized.page_url || u
      })
    });

    const data = await res.json().catch(() => (/** @type {Record<string, any>} */ ({})));
    if (!res.ok) {
      if (res.status === 401) {
        showToast('Session expired. Sign in again from the extension.', 'info', 8000);
        return;
      }
      if (data.error_code === 'CFG_6001') {
        showToast('Add your API key under Settings → AI Setup, then try again.', 'info', 8000);
        return;
      }
      if (res.status === 429 || data.error_code === 'RATE_4001') {
        const retrySec = parseInt(res.headers.get('Retry-After') || '0', 10);
        const waitMsg =
          retrySec > 0
            ? ' Try again in ' + Math.ceil(retrySec / 60) + ' min (' + retrySec + ' s).'
            : '';
        showToast(
          (data.message || 'Autofill rate limit reached.') + waitMsg,
          'info',
          12000
        );
        return;
      }
      if (res.status === 403) {
        showToast(data.message || 'Finish your profile setup on the dashboard first.', 'info', 8000);
        return;
      }
      throw new Error(data.message || data.detail || 'Autofill request failed');
    }

    const assignments = Array.isArray(data.assignments) ? data.assignments : [];
    if (!assignments.length) {
      showToast('No suggestions returned. Try a different step of the form or update your profile.', 'info', 7000);
      return;
    }

    const mapped = assignments.map(function (x) {
      return {
        field_uid: x.field_uid,
        value: x.value,
        label_text: x.label_text,
        duplicate_label_index:
          typeof x.duplicate_label_index === 'number' ? x.duplicate_label_index : 0
      };
    });
    try {
      await applyAutofillAssignmentsToTab(tab.id, mapped, fields.length, eduCount);
      const apiWarnings = Array.isArray(data.warnings) ? data.warnings : [];
      const missingRequired = apiWarnings.find(function (w) {
        return typeof w === 'string' && w.indexOf('required field(s) could not be auto-filled') >= 0;
      });
      if (missingRequired) {
        showToast(missingRequired, 'info', 10000);
      }
      // Attach resume after profile apply (Ashby resume parser can overwrite name/email).
      try {
        await new Promise(function (resolve) {
          setTimeout(resolve, isAshby ? 200 : 400);
        });
        const attachedAfter = await attachStoredResumeToTab(tab.id);
        if (attachedAfter.attached > resumeAttached) {
          resumeAttached = attachedAfter.attached;
        }
        if (attachedAfter.ashby_upload_failed) {
          ashbyResumeUploadFailed = true;
        }
        if (isAshby) {
          try {
            await suppressAshbyResumeAutofillOnTab(tab.id);
          } catch (suppressAfterErr) {
            console.debug('Ashby autofill suppress after attach skipped:', suppressAfterErr);
          }
        }
        if (isAshby && resumeAttached > 0) {
          await reapplyAshbyIdentityAfterResume(tab.id, mapped);
          if (await ashbyResumeUploadFailedOnTab(tab.id)) {
            ashbyResumeUploadFailed = true;
          }
        }
        if (resumeAttached === 0) {
          await new Promise(function (resolve) {
            setTimeout(resolve, 600);
          });
          const attachedRetry = await attachStoredResumeToTab(tab.id);
          if (attachedRetry.attached > resumeAttached) {
            resumeAttached = attachedRetry.attached;
          }
          if (attachedRetry.ashby_upload_failed) {
            ashbyResumeUploadFailed = true;
          }
          if (isAshby) {
            try {
              await suppressAshbyResumeAutofillOnTab(tab.id);
            } catch (suppressRetryErr) {
              console.debug('Ashby autofill suppress retry skipped:', suppressRetryErr);
            }
          }
          if (isAshby && resumeAttached > 0) {
            await reapplyAshbyIdentityAfterResume(tab.id, mapped);
            if (await ashbyResumeUploadFailedOnTab(tab.id)) {
              ashbyResumeUploadFailed = true;
            }
          }
        }
      } catch (resumeAfterErr) {
        console.debug('Post-apply resume attach skipped:', resumeAfterErr);
      }
      if (ashbyResumeUploadFailed) {
        showToast(
          'Profile fields filled. Ashby could not save the resume on their servers (502). Click Replace and choose your PDF again, or try later.',
          'info',
          12000
        );
      } else if (resumeAttached === 0) {
        const hasResumeField = fields.some(function (f) {
          return f && f.input_type === 'file' && /resume|cv/i.test(String(f.label_text || ''));
        });
        if (hasResumeField) {
          showToast(
            'Fields filled. Upload a resume in Profile Setup to autofill resume file fields.',
            'info',
            8000
          );
        }
      }
    } catch (applyErr) {
      console.error('Autofill apply failed:', applyErr);
      showToast('Could not fill fields on this page.', 'error', 5000);
    }
  } catch (err) {
    console.error('Autofill match failed:', err);
    showToast(err.message || 'Could not get suggestions.', 'error', 5000);
  } finally {
    state.isAutofillScanning = false;
    if (elements.matchProfileBtn) elements.matchProfileBtn.disabled = false;
  }
}

function showExtracting() {
  elements.extractBtn.disabled = true;
  if (elements.copyBtn) elements.copyBtn.disabled = true;
  if (elements.matchProfileBtn) elements.matchProfileBtn.disabled = true;
  elements.extractionStatus.classList.remove('hidden');
  elements.successMessage.classList.add('hidden');
  elements.errorMessage.classList.add('hidden');
  state.isExtracting = true;
}

function hideExtracting() {
  elements.extractBtn.disabled = false;
  if (elements.copyBtn) elements.copyBtn.disabled = false;
  if (elements.matchProfileBtn) elements.matchProfileBtn.disabled = false;
  elements.extractionStatus.classList.add('hidden');
  state.isExtracting = false;
}

function showSuccess() {
  hideExtracting();
  elements.successMessage.classList.remove('hidden');
  const primary = elements.primaryActionsBlock;
  if (primary) primary.classList.add('hidden');
  elements.jobDetection.classList.add('hidden');
}

function showError(title, message) {
  hideExtracting();
  exitAutofillPreview();
  elements.errorTitle.textContent = title;
  elements.errorText.textContent = message;
  elements.errorMessage.classList.remove('hidden');
}

function resetView() {
  hideExtracting();
  elements.successMessage.classList.add('hidden');
  elements.errorMessage.classList.add('hidden');
  const primary = elements.primaryActionsBlock;
  if (primary) primary.classList.remove('hidden');
  elements.jobDetection.classList.remove('hidden');
  exitAutofillPreview();
}

let _notifTimer = null;

/**
 * @param {string} message
 * @param {'success'|'error'|'info'} [type]
 * @param {number} [durationMs] Defaults to 3000; use longer for multi-line tips.
 */
function showToast(message, type = 'info', durationMs = 3000) {
  const bar = document.getElementById('popupNotification');
  if (!bar) return;

  const icons = { success: 'fa-circle-check', error: 'fa-circle-xmark', info: 'fa-circle-info' };
  const icon = icons[type] ?? icons.info;

  if (_notifTimer) { clearTimeout(_notifTimer); _notifTimer = null; }

  bar.className = `popup-notification ${type}`;
  bar.innerHTML = `<i class="fas ${icon} notif-icon"></i><span></span>`;
  const span = bar.querySelector('span');
  if (span) span.textContent = message;

  _notifTimer = setTimeout(() => {
    bar.classList.add('hidden');
    _notifTimer = null;
  }, durationMs);
}

/**
 * Last-mile UX: when heuristics say extraction may be noisy, nudge user toward selection fallback.
 * @param {{ confidence?: string } | null | undefined} extracted
 */
function maybeShowExtractionQualityTip(extracted) {
  const conf = extracted && extracted.confidence;
  if (conf === 'low') {
    showToast(
      'Tip: If the role or company look wrong on your dashboard, highlight the full job description on the page, then tap Analyze again.',
      'info',
      14000
    );
  } else if (conf === 'medium') {
    showToast(
      'Tip: On split job lists, wrong title or company? Select only the job description text, then analyze.',
      'info',
      8000
    );
  }
}

// =============================================================================
// JOB DETECTION
// =============================================================================

async function detectJobOnCurrentPage() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    state.currentTab = tab;

    if (!tab || !tab.url) {
      elements.jobDetection.style.display = 'none';
      return;
    }

    try {
      const hostname = new URL(tab.url).hostname.replace(/^www\./, '');
      elements.detectedSource.textContent = hostname;
    } catch (e) {
      elements.detectedSource.textContent = 'this page';
    }
  } catch (error) {
    console.error('Failed to detect job:', error);
    elements.jobDetection.style.display = 'none';
  }
}

function parseUrlParts(url) {
  try {
    const parsed = new URL(url);
    return { pathname: parsed.pathname, hostname: parsed.hostname };
  } catch (_e) {
    return null;
  }
}

function isLinkedInJobsUrl(url) {
  const parts = parseUrlParts(url);
  if (!parts) return false;
  const host = parts.hostname.replace(/^www\./i, '');
  return /(?:^|\.)linkedin\.com$/i.test(host) && /^\/jobs/i.test(parts.pathname);
}

function isJobRelatedURL(url) {
  if (!url) return false;
  const parts = parseUrlParts(url);
  if (!parts) return false;

  const pathPatterns = [
    /^\/careers?\//i,
    /^\/jobs?\//i,
    /^\/job-/i,
    /^\/positions?\//i,
    /^\/openings?\//i,
    /^\/vacancies?\//i,
    /^\/apply\//i,
    /^\/hiring\//i,
    /^\/opportunities?\//i,
  ];
  const hostPatterns = [
    /(?:^|\.)workday\.com$/i,
    /(?:^|\.)greenhouse\.io$/i,
    /(?:^|\.)lever\.co$/i,
    /(?:^|\.)ashbyhq\.com$/i,
    /(?:^|\.)bamboohr\.com$/i,
    /(?:^|\.)smartrecruiters\.com$/i,
    /(?:^|\.)icims\.com$/i,
    /(?:^|\.)jobvite\.com$/i,
  ];

  return pathPatterns.some((pattern) => pattern.test(parts.pathname))
    || hostPatterns.some((pattern) => pattern.test(parts.hostname));
}

// =============================================================================
// JOB EXTRACTION
// =============================================================================

/**
 * @param {string} title
 * @returns {boolean}
 */
function isUnreliableBrowserTabTitle(title) {
  if (!title) return true;
  const s = String(title).trim();
  if (s.length < 3) return true;
  if (/(linkedin|indeed|glassdoor|ziprecruiter|monster|careerbuilder)/i.test(s)) return true;
  if (/^\(\d+\)/.test(s)) return true;
  if (/^search\s*\|/i.test(s)) return true;
  return false;
}

/** @param {string} title */
function isPlausibleJobTitle(title) {
  if (!title) return false;
  const s = String(title).trim();
  if (s.length < 4 || s.length > 200) return false;
  const lower = s.toLowerCase();
  if (/^(about|at |we |join |since |our |the |as a )/.test(lower)) return false;
  if (/^show\s+(more|less)\b/.test(lower)) return false;
  if (/^(see\s+more|easy\s+apply|apply\s+now)$/.test(lower)) return false;
  if ((s.match(/[.!]/g) || []).length > 1) return false;
  return true;
}

/**
 * @param {Record<string, unknown>|null|undefined} extracted
 * @param {string} tabUrl
 * @returns {FormData}
 */
function buildExtensionWorkflowFormData(extracted, tabUrl) {
  const formData = new FormData();
  formData.append('job_text', String(extracted?.content || ''));
  formData.append('source', 'extension');
  if (tabUrl) formData.append('source_url', tabUrl);

  const detectedTitle = String(
    extracted?.detectedTitle || extracted?.jobTitle || ''
  ).trim();
  const detectedCompany = String(
    extracted?.detectedCompany || extracted?.companyName || ''
  ).trim();

  if (detectedTitle && !isUnreliableBrowserTabTitle(detectedTitle) && isPlausibleJobTitle(detectedTitle)) {
    formData.append('detected_title', detectedTitle);
  }
  if (detectedCompany && detectedCompany.length <= 200) {
    formData.append('detected_company', detectedCompany);
  }
  return formData;
}

async function extractAndSubmitJob() {
  if (state.isExtracting) return;

  showExtracting();
  elements.statusText.textContent = 'Extracting page content...';

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab) throw new Error('No active tab found');

    const extracted = await runExtractPageContent(tab.id);

    if (!extracted || extracted.error || !extracted.content) {
      throw new Error('Failed to extract content from page');
    }

    if (extracted.diagnostics) {
      console.info('[RoleMule] extract diagnostics — copy this object when reporting bugs:', extracted.diagnostics);
    }

    const { content } = extracted;

    if (content.length < 100) {
      throw new Error('Page content is too short. Make sure the job posting is fully loaded.');
    }

    elements.statusText.textContent = 'Sending to AI for analysis...';

    const formData = buildExtensionWorkflowFormData(extracted, tab.url || '');

    const response = await fetch(`${CONFIG.API_BASE_URL}/workflow/start`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${state.token}`
      },
      body: formData
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => (/** @type {Record<string, any>} */ ({})));
      if (errorData.error_code === 'RES_3002') {
        hideExtracting();
        const dupMsg =
          errorData.message ||
          'You already have this role and company on your list. Open your dashboard to view that application.';
        showToast(dupMsg, 'info');
        return;
      }
      throw new Error(errorData.detail || errorData.message || `API error: ${response.status}`);
    }

    showSuccess();
    maybeShowExtractionQualityTip(extracted);

  } catch (error) {
    console.error('Extraction failed:', error);
    showError('Extraction Failed', error.message || 'Please try again.');
  }
}

async function copyPageContent() {
  if (state.isExtracting) return;

  try {
    elements.copyBtn.disabled = true;

    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab) throw new Error('No active tab found');

    const extracted = await runExtractPageContent(tab.id);

    if (!extracted || extracted.error || !extracted.content) {
      throw new Error('Failed to extract content from page');
    }

    if (extracted.diagnostics) {
      console.info('[RoleMule] extract diagnostics — copy this object when reporting bugs:', extracted.diagnostics);
    }

    await navigator.clipboard.writeText(extracted.content);
    showToast('Copied to clipboard!', 'success');

    // Brief visual feedback on icon
    elements.copyBtn.classList.add('copied');
    setTimeout(() => {
      elements.copyBtn.classList.remove('copied');
    }, 2000);

  } catch (error) {
    console.error('Copy failed:', error);
    showToast('Failed to copy content', 'error');
  } finally {
    elements.copyBtn.disabled = false;
  }
}

// =============================================================================
// EVENT LISTENERS
// =============================================================================

function setupEventListeners() {
  // Login form submission
  elements.loginForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const email = elements.loginEmail.value.trim();
    const password = elements.loginPassword.value;

    if (!email || !password) {
      elements.loginError.textContent = 'Please enter email and password';
      elements.loginError.classList.remove('hidden');
      return;
    }

    handleLogin(email, password);
  });

  // Register link
  elements.openRegisterBtn.addEventListener('click', (e) => {
    e.preventDefault();
    chrome.tabs.create({ url: `${CONFIG.APP_URL}/auth/register` });
  });

  // Extract & copy buttons
  elements.extractBtn.addEventListener('click', () => extractAndSubmitJob());
  if (elements.copyBtn) {
    elements.copyBtn.addEventListener('click', () => copyPageContent());
  }

  // Open dashboard
  elements.openDashboardBtn.addEventListener('click', () => {
    chrome.tabs.create({ url: CONFIG.DASHBOARD_URL });
  });

  // Retry
  elements.retryBtn.addEventListener('click', () => {
    resetView();
    detectJobOnCurrentPage();
  });

  // Quick links
  elements.dashboardLink.addEventListener('click', (e) => {
    e.preventDefault();
    chrome.tabs.create({ url: CONFIG.DASHBOARD_URL });
  });

  elements.settingsLink.addEventListener('click', (e) => {
    e.preventDefault();
    chrome.tabs.create({ url: `${CONFIG.DASHBOARD_URL}/settings` });
  });

  elements.logoutLink.addEventListener('click', async (e) => {
    e.preventDefault();
    await logout();
  });

  elements.helpLink.addEventListener('click', (e) => {
    e.preventDefault();
    chrome.tabs.create({ url: `${CONFIG.APP_URL}/help` });
  });

  if (elements.helpLinkFooter) {
    elements.helpLinkFooter.addEventListener('click', (e) => {
      e.preventDefault();
      chrome.tabs.create({ url: `${CONFIG.APP_URL}/help` });
    });
  }

  if (elements.matchProfileBtn) {
    elements.matchProfileBtn.addEventListener('click', () => matchFormToProfile());
  }
}

// =============================================================================
// MESSAGE HANDLING
// =============================================================================

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'AUTH_SUCCESS') {
    saveCredentials(message.token, message.user).then(() => {
      updateAuthUI();
      detectJobOnCurrentPage();
      showToast('Signed in!', 'success');
    });
    sendResponse({ success: true });
  } else if (message.type === 'AUTH_LOGOUT') {
    clearCredentials().then(() => {
      updateAuthUI();
      showToast('Logged out', 'info');
    });
    sendResponse({ success: true });
  }

  return true;
});
