/**
 * ApplyPilot - Background Service Worker
 * Handles API communication, authentication, and cross-tab messaging
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
  },
  // Token refresh interval (55 minutes)
  TOKEN_REFRESH_INTERVAL: 55 * 60 * 1000
};

/** Same injected script as `popup.js` — generic page extraction + selection override. */
const JAA_EXTRACT_FILE = 'lib/extract-page-content.js';
/** MAIN world hook for LinkedIn Voyager responses (job search JSON). */
const JAA_LI_MAIN_HOOK_FILE = 'lib/linkedin-voyager-hook.js';
const JAA_LI_GUEST_PREFETCH_FILE = 'lib/linkedin-guest-prefetch.js';

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

// =============================================================================
// STATE
// =============================================================================

let state = {
  token: null,
  user: null,
  refreshTimer: null
};

// =============================================================================
// INITIALIZATION
// =============================================================================

// Initialize on install
chrome.runtime.onInstalled.addListener(async (details) => {
  console.log('[JAA] Extension installed:', details.reason);
  
  if (details.reason === 'install') {
    // Open welcome page or dashboard
    chrome.tabs.create({
      url: `${CONFIG.APP_URL}/auth/login?source=extension`
    });
  }
  
  await loadCredentials();
});

// Initialize on startup
chrome.runtime.onStartup.addListener(async () => {
  console.log('[JAA] Extension started');
  await loadCredentials();
});

// =============================================================================
// CREDENTIALS MANAGEMENT
// =============================================================================

async function loadCredentials() {
  try {
    const result = await chrome.storage.local.get([
      CONFIG.STORAGE_KEYS.TOKEN,
      CONFIG.STORAGE_KEYS.USER,
      CONFIG.STORAGE_KEYS.API_URL
    ]);
    
    if (result[CONFIG.STORAGE_KEYS.TOKEN]) {
      state.token = result[CONFIG.STORAGE_KEYS.TOKEN];
      state.user = result[CONFIG.STORAGE_KEYS.USER];
      
      if (result[CONFIG.STORAGE_KEYS.API_URL]) {
        CONFIG.API_BASE_URL = result[CONFIG.STORAGE_KEYS.API_URL];
        CONFIG.APP_URL = CONFIG.API_BASE_URL.replace(/\/api\/v1$/, '').replace(/\/api$/, '');
        CONFIG.DASHBOARD_URL = CONFIG.APP_URL + '/dashboard';
      }
      
      // Verify token is still valid
      const isValid = await verifyToken();
      if (isValid) {
        setupTokenRefresh();
      } else {
        await clearCredentials();
      }
    }
  } catch (error) {
    console.error('[JAA] Failed to load credentials:', error);
  }
}

async function saveCredentials(token, user, apiUrl = null) {
  try {
    const data = {
      [CONFIG.STORAGE_KEYS.TOKEN]: token,
      [CONFIG.STORAGE_KEYS.USER]: user
    };
    
    if (apiUrl) {
      data[CONFIG.STORAGE_KEYS.API_URL] = apiUrl;
      CONFIG.API_BASE_URL = apiUrl;
      CONFIG.APP_URL = apiUrl.replace(/\/api\/v1$/, '').replace(/\/api$/, '');
      CONFIG.DASHBOARD_URL = CONFIG.APP_URL + '/dashboard';
    }
    
    await chrome.storage.local.set(data);
    
    state.token = token;
    state.user = user;
    
    setupTokenRefresh();
    
    console.log('[JAA] Credentials saved');
  } catch (error) {
    console.error('[JAA] Failed to save credentials:', error);
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
    
    if (state.refreshTimer) {
      clearInterval(state.refreshTimer);
      state.refreshTimer = null;
    }
    
    console.log('[JAA] Credentials cleared');
  } catch (error) {
    console.error('[JAA] Failed to clear credentials:', error);
  }
}

// =============================================================================
// TOKEN MANAGEMENT
// =============================================================================

async function verifyToken() {
  if (!state.token) return false;
  
  try {
    const response = await fetch(`${CONFIG.API_BASE_URL}/auth/extension-status`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${state.token}`,
        'Content-Type': 'application/json'
      }
    });
    
    return response.ok;
  } catch (error) {
    console.error('[JAA] Token verification failed:', error);
    return false;
  }
}

async function refreshToken() {
  if (!state.token) return false;
  
  try {
    const response = await fetch(`${CONFIG.API_BASE_URL}/auth/refresh`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${state.token}`,
        'Content-Type': 'application/json'
      }
    });
    
    if (response.ok) {
      const data = await response.json();
      await saveCredentials(data.access_token, state.user);
      console.log('[JAA] Token refreshed successfully');
      return true;
    } else {
      console.warn('[JAA] Token refresh failed, clearing credentials');
      await clearCredentials();
      return false;
    }
  } catch (error) {
    console.error('[JAA] Token refresh error:', error);
    return false;
  }
}

function setupTokenRefresh() {
  if (state.refreshTimer) {
    clearInterval(state.refreshTimer);
  }
  
  state.refreshTimer = setInterval(async () => {
    if (state.token) {
      await refreshToken();
    }
  }, CONFIG.TOKEN_REFRESH_INTERVAL);
}

// =============================================================================
// API CALLS
// =============================================================================

async function apiCall(endpoint, method = 'GET', data = null) {
  const url = `${CONFIG.API_BASE_URL}${endpoint}`;
  
  const config = {
    method,
    headers: {
      'Content-Type': 'application/json'
    }
  };
  
  if (state.token) {
    config.headers['Authorization'] = `Bearer ${state.token}`;
  }
  
  if (data && method !== 'GET') {
    config.body = JSON.stringify(data);
  }
  
  try {
    const response = await fetch(url, config);
    
    // Handle token expiration
    if (response.status === 401 && !endpoint.includes('/auth/')) {
      const refreshed = await refreshToken();
      if (refreshed) {
        // Retry with new token
        config.headers['Authorization'] = `Bearer ${state.token}`;
        return fetch(url, config);
      }
    }
    
    return response;
  } catch (error) {
    console.error('[JAA] API call failed:', error);
    throw error;
  }
}

async function startWorkflow(jobContent, sourceUrl, metadata = {}) {
  if (!state.token) {
    throw new Error('Not authenticated');
  }
  
  const response = await apiCall('/workflow/start', 'POST', {
    job_text: jobContent,
    source: 'extension',
    source_url: sourceUrl,
    ...metadata
  });
  
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    let msg = errorData.detail || errorData.message || `API error: ${response.status}`;
    if (errorData.error_code === 'RES_3002') {
      msg =
        errorData.message ||
        'You already have this role and company on your applications list. Open your dashboard—you do not need to add the same job twice.';
    }
    throw new Error(msg);
  }
  
  return response.json();
}

// =============================================================================
// MESSAGE HANDLING
// =============================================================================

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  handleMessage(message, sender).then(sendResponse).catch(error => {
    sendResponse({ success: false, error: error.message });
  });
  
  return true; // Keep channel open for async response
});

async function handleMessage(message, sender) {
  switch (message.type) {
    // Authentication
    case 'GET_AUTH_STATUS':
      return {
        success: true,
        isAuthenticated: !!state.token,
        user: state.user
      };
      
    case 'SAVE_CREDENTIALS':
      await saveCredentials(message.token, message.user, message.apiUrl);
      return { success: true };
      
    case 'LOGOUT':
      await clearCredentials();
      return { success: true };
      
    // Workflow
    case 'START_WORKFLOW':
      const result = await startWorkflow(
        message.jobContent,
        message.sourceUrl,
        message.metadata
      );
      return { success: true, data: result };
      
    // Job detection notification
    case 'JOB_DETECTED':
      // Update badge or icon when job is detected
      if (sender.tab) {
        chrome.action.setBadgeText({ 
          text: '!', 
          tabId: sender.tab.id 
        });
        chrome.action.setBadgeBackgroundColor({ 
          color: '#00d4ff',
          tabId: sender.tab.id
        });
      }
      return { success: true };
      
    // API proxy
    case 'API_CALL':
      const response = await apiCall(message.endpoint, message.method, message.data);
      const responseData = await response.json().catch(() => null);
      return { 
        success: response.ok, 
        status: response.status,
        data: responseData 
      };
      
    default:
      throw new Error(`Unknown message type: ${message.type}`);
  }
}

// =============================================================================
// TAB MANAGEMENT
// =============================================================================

// Listen for tab updates to auto-sync auth from web app
// NOTE: We no longer auto-detect job pages to avoid triggering website extension detection
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url) {
    // --- Auto-sync auth token from the web app ---
    // When user navigates to dashboard or profile setup (login success),
    // inject a script to grab the token from localStorage.
    const appUrl = CONFIG.APP_URL;
    const isAppPage = tab.url.startsWith(appUrl) && 
        (tab.url.includes('/dashboard') || tab.url.includes('/profile/setup'));
    
    if (isAppPage) {
      // Check storage (not just in-memory state, since service worker may have restarted)
      const stored = await chrome.storage.local.get([CONFIG.STORAGE_KEYS.TOKEN]);
      const hasToken = !!(state.token || stored[CONFIG.STORAGE_KEYS.TOKEN]);
      
      if (!hasToken) {
        try {
          const results = await chrome.scripting.executeScript({
            target: { tabId: tabId },
            func: () => {
              const token = localStorage.getItem('access_token') || localStorage.getItem('authToken');
              const userStr = localStorage.getItem('user');
              let user = null;
              try { user = userStr ? JSON.parse(userStr) : null; } catch(e) {}
              return { token, user };
            }
          });
          
          if (results && results[0] && results[0].result && results[0].result.token) {
            const { token, user } = results[0].result;
            await saveCredentials(token, user, appUrl + '/api/v1');
            console.log('[JAA] Auth token auto-synced from web app');
          }
        } catch (e) {
          // Silently fail - page might not allow script injection
          console.debug('[JAA] Auto-sync skipped:', e.message);
        }
      }
    }
  }
});

// =============================================================================
// CONTEXT MENU (Right-click menu)
// =============================================================================

// Create context menu on install
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: 'jaa-extract',
    title: 'Extract job with Job Assistant',
    contexts: ['page', 'selection']
  });
});

// Handle context menu clicks
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === 'jaa-extract') {
    if (!state.token) {
      // Open login page
      chrome.tabs.create({
        url: `${CONFIG.APP_URL}/auth/login?source=extension`
      });
      return;
    }
    
    // Execute shared extractor (same logic as popup — selection-first, generic DOM scoring)
    try {
      let forceDiag = IS_DEV;
      try {
        const st = await chrome.storage.local.get(['extract_diagnostics']);
        if (st.extract_diagnostics === true) forceDiag = true;
      } catch (e) {
        /* ignore */
      }

      try {
        if (tab.url && isLinkedInJobsUrl(tab.url)) {
          await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            files: [JAA_LI_MAIN_HOOK_FILE],
            world: 'MAIN'
          });
          await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            files: [JAA_LI_GUEST_PREFETCH_FILE],
            world: 'MAIN'
          });
          await new Promise(function (r) {
            setTimeout(r, 750);
          });
        }
      } catch (eHook) {
        /* ignore */
      }

      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: [JAA_EXTRACT_FILE]
      });
      const results = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: async (forceDiag) => {
          try {
            if (forceDiag) window.__JAA_EXTRACT_DEBUG = true;
          } catch (e) {
            /* ignore */
          }
          const runAsync = window.__jaaExtractPageContentAsync;
          let r;
          if (typeof runAsync === 'function') {
            r = await runAsync();
          } else {
            const fn = window.__jaaExtractPageContent;
            if (typeof fn !== 'function') {
              return {
                content: '',
                title: document.title || '',
                company: '',
                url: window.location.href,
                error: 'extractor_missing'
              };
            }
            r = fn();
          }
          return {
            content: r.content,
            title: r.title,
            company: '',
            url: window.location.href,
            diagnostics: r.diagnostics
          };
        },
        args: [forceDiag]
      });
      
      if (results && results[0] && results[0].result) {
        const data = results[0].result;

        if (data.diagnostics) {
          console.info('[JAA] extract diagnostics', data.diagnostics);
        }

        if (data.error || !data.content || data.content.length < 100) {
          chrome.notifications.create({
            type: 'basic',
            iconUrl: chrome.runtime.getURL('icons/icon128.png'),
            title: 'Extraction Failed',
            message:
              'Could not read enough job text. Try highlighting the job description, then use Extract again.',
            priority: 2
          });
          return;
        }

        // Start workflow
        await startWorkflow(data.content, data.url, {
          detected_title: data.title,
          detected_company: data.company
        });
        
        // Show success notification
        chrome.notifications.create({
          type: 'basic',
          iconUrl: chrome.runtime.getURL('icons/icon128.png'),
          title: 'Job Submitted!',
          message: 'Check your dashboard for analysis results.',
          priority: 2
        });
      }
    } catch (error) {
      console.error('[JAA] Context menu extraction failed:', error);
      
      chrome.notifications.create({
        type: 'basic',
        iconUrl: chrome.runtime.getURL('icons/icon128.png'),
        title: 'Extraction Failed',
        message: error.message || 'Please try again or use the extension popup.',
        priority: 2
      });
    }
  }
});

// =============================================================================
// EXTERNAL MESSAGE HANDLING (from web app)
// =============================================================================

// Allow the web app to communicate with the extension
chrome.runtime.onMessageExternal.addListener((message, sender, sendResponse) => {
  // Verify sender is from our app - allow the currently configured app URL
  const allowedOrigins = [CONFIG.APP_URL];
  
  if (!allowedOrigins.some(origin => sender.url?.startsWith(origin))) {
    sendResponse({ success: false, error: 'Unauthorized origin' });
    return;
  }
  
  handleMessage(message, sender).then(sendResponse).catch(error => {
    sendResponse({ success: false, error: error.message });
  });
  
  return true;
});

// =============================================================================
// NOTIFICATIONS
// =============================================================================

chrome.notifications.onClicked.addListener((notificationId) => {
  // Open dashboard when notification is clicked
  chrome.tabs.create({ url: CONFIG.DASHBOARD_URL });
  chrome.notifications.clear(notificationId);
});

console.log('[JAA] Background service worker loaded');


