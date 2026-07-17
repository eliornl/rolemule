/**
 * RoleMule - Content Script
 * Injected into job-related pages to enable content extraction
 * and provide visual feedback to the user
 */

// =============================================================================
// CONFIGURATION
// =============================================================================

const JAA_CONFIG = {
  // Debounce delay for mutations
  MUTATION_DEBOUNCE: 500
};

// =============================================================================
// STATE
// =============================================================================

let jaaState = {
  isInitialized: false,
  jobDetected: false
};

// =============================================================================
// INITIALIZATION
// =============================================================================

function initContentScript() {
  if (jaaState.isInitialized) return;
  jaaState.isInitialized = true;
  
  // Detect if this is a job page
  detectJobPage();
  
  // Listen for messages from popup/background
  chrome.runtime.onMessage.addListener(handleMessage);
  
  // Observe DOM changes for SPAs
  observeDOMChanges();
  
  console.log('[JAA] Content script initialized');
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initContentScript);
} else {
  initContentScript();
}

// =============================================================================
// JOB DETECTION
// =============================================================================

function detectJobPage() {
  const url = window.location.href;
  const hostname = window.location.hostname;
  
  // Check URL patterns
  const isJobURL = isJobRelatedURL(url);
  
  // Check page content for job-related keywords
  const pageText = document.body?.textContent?.toLowerCase() || '';
  const jobKeywords = [
    'job description',
    'responsibilities',
    'requirements',
    'qualifications',
    'apply now',
    'about the role',
    'what you\'ll do',
    'what we\'re looking for',
    'experience required',
    'full-time',
    'part-time',
    'remote',
    'hybrid'
  ];
  
  const hasJobContent = jobKeywords.some(keyword => pageText.includes(keyword));
  
  jaaState.jobDetected = isJobURL || hasJobContent;
  
  if (jaaState.jobDetected) {
    console.log('[JAA] Job page detected:', hostname);
    // Notify background script
    chrome.runtime.sendMessage({
      type: 'JOB_DETECTED',
      url: url,
      hostname: hostname
    }).catch(() => {});
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
// CONTENT EXTRACTION (simple, no per-site selectors)
// =============================================================================

function extractJobTitle() {
  // Just grab the first h1 — the AI will figure out the rest
  const h1 = document.querySelector('h1');
  if (h1) {
    const text = h1.textContent.trim();
    if (text.length > 0 && text.length < 200) return text;
  }
  return document.title.split(' - ')[0].trim();
}

function extractCompanyName() {
  // Try meta tag first (most reliable), then generic selectors
  const ogSite = document.querySelector('meta[property="og:site_name"]');
  if (ogSite) {
    const content = ogSite.getAttribute('content');
    if (content && content.length < 100) return content;
  }

  for (const sel of ['[class*="company-name"]', '[class*="companyName"]', '[class*="employer"]']) {
    const el = document.querySelector(sel);
    if (el) {
      const text = el.textContent.trim();
      if (text.length > 0 && text.length < 100) return text;
    }
  }

  return '';
}

// =============================================================================
// MESSAGE HANDLING
// =============================================================================

function handleMessage(message, sender, sendResponse) {
  switch (message.type) {
    case 'GET_JOB_INFO':
      sendResponse({
        success: true,
        data: {
          title: extractJobTitle(),
          company: extractCompanyName(),
          isJobPage: jaaState.jobDetected,
          url: window.location.href
        }
      });
      break;
      
    case 'IS_JOB_PAGE':
      sendResponse({ isJobPage: jaaState.jobDetected });
      break;
      
    case 'PING':
      sendResponse({ pong: true });
      break;
      
    default:
      sendResponse({ success: false, error: 'Unknown message type' });
  }
  
  return true; // Keep channel open for async response
}

// =============================================================================
// DOM OBSERVATION (for SPAs)
// =============================================================================

function observeDOMChanges() {
  let debounceTimer = null;
  
  const observer = new MutationObserver((mutations) => {
    // Check if any mutation affects the main content area
    const hasSignificantChange = mutations.some(mutation => {
      return mutation.type === 'childList' && mutation.addedNodes.length > 0;
    });
    
    if (hasSignificantChange) {
      // Debounce to avoid excessive processing
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        detectJobPage();
      }, JAA_CONFIG.MUTATION_DEBOUNCE);
    }
  });
  
  observer.observe(document.body, {
    childList: true,
    subtree: true
  });
}

// =============================================================================
// VISUAL INDICATOR (optional)
// =============================================================================

function showExtractIndicator() {
  // Remove existing indicator
  const existing = document.getElementById('jaa-extract-indicator');
  if (existing) existing.remove();
  
  const indicator = document.createElement('div');
  indicator.id = 'jaa-extract-indicator';
  indicator.innerHTML = `
    <div style="
      position: fixed;
      top: 20px;
      right: 20px;
      background: linear-gradient(135deg, #00d4ff 0%, #7c3aed 100%);
      color: white;
      padding: 12px 20px;
      border-radius: 8px;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      font-size: 14px;
      font-weight: 500;
      box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
      z-index: 999999;
      display: flex;
      align-items: center;
      gap: 10px;
      animation: jaaSlideIn 0.3s ease-out;
    ">
      <span style="font-size: 18px;">📋</span>
      <span>Job extracted successfully!</span>
    </div>
    <style>
      @keyframes jaaSlideIn {
        from {
          opacity: 0;
          transform: translateX(100px);
        }
        to {
          opacity: 1;
          transform: translateX(0);
        }
      }
    </style>
  `;
  
  document.body.appendChild(indicator);
  
  // Auto-remove after 3 seconds
  setTimeout(() => {
    indicator.style.opacity = '0';
    indicator.style.transition = 'opacity 0.3s ease';
    setTimeout(() => indicator.remove(), 300);
  }, 3000);
}

// Note: showExtractIndicator is called internally, not exposed to page context
// to avoid triggering extension detection scripts on some websites

// =============================================================================
// AUTH SYNC (listen for login events from the web app)
// =============================================================================

window.addEventListener('message', (event) => {
  // Only accept messages from the same origin (our web app)
  if (event.origin !== window.location.origin) return;
  
  const message = event.data;
  if (!message || message.type !== 'JAA_AUTH_SUCCESS') return;
  
  console.log('[JAA] Received auth token from web app');
  
  // Relay to the extension's service worker
  chrome.runtime.sendMessage({
    type: 'SAVE_CREDENTIALS',
    token: message.token,
    user: message.user,
    apiUrl: message.apiUrl
  }).then(() => {
    console.log('[JAA] Auth token synced to extension');
  }).catch((error) => {
    console.error('[JAA] Failed to sync auth token:', error);
  });
});


