/**
 * DOM / log sanitization helpers.
 * Decode &amp; FIRST (bleach double-encodes entities from Python html.escape).
 */

export function sanitizeLogValue(value: unknown): string {
  if (value == null) return '';
  return String(value).replace(/[\r\n\x00-\x1f\x7f]/g, ' ');
}

export function decodeEntities(str: string | null | undefined): string {
  if (str == null) return '';
  let s = String(str);
  for (let i = 0; i < 5 && s.includes('&amp;'); i++) {
    s = s.replace(/&amp;/g, '&');
  }
  return s
    .replace(/&#x27;/gi, "'")
    .replace(/&#39;/g, "'")
    .replace(/&#039;/g, "'")
    .replace(/&apos;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>');
}

/**
 * Decode entities then escape for safe insertion into HTML.
 * Uses textContent → innerHTML so the browser handles encoding.
 */
export function escapeHtml(str: string | null | undefined): string {
  if (str == null) return '';
  const decoded = decodeEntities(str);
  if (typeof document === 'undefined') {
    // Node/Vitest fallback (no DOM)
    return decoded
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
  const div = document.createElement('div');
  div.textContent = decoded;
  return div.innerHTML;
}

export function stripHtmlForAlert(text: string | null | undefined): string {
  if (text == null) return '';
  return String(text).replace(/<[^>]*>/g, '');
}

/** Allow only same-origin relative paths for post-auth redirects. */
export function validateRelativeRedirectPath(
  path: string | null | undefined,
): string | null {
  if (typeof path !== 'string' || path.length === 0) {
    return null;
  }
  if (!/^\/(?!\/)/.test(path)) {
    return null;
  }
  return path;
}

/** Attach helpers on window for legacy classic scripts still on the page. */
export function installDomSecurityGlobals(): void {
  window.sanitizeLogValue = sanitizeLogValue;
  window.escapeHtml = escapeHtml;
  window.decodeEntities = decodeEntities;
  window.stripHtmlForAlert = stripHtmlForAlert;
  window.validateRelativeRedirectPath = validateRelativeRedirectPath;
}
