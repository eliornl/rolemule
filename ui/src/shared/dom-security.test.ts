import { describe, it, expect } from 'vitest';
import {
  decodeEntities,
  escapeHtml,
  validateRelativeRedirectPath,
  sanitizeLogValue,
} from './dom-security';

describe('decodeEntities', () => {
  it('decodes &amp; first so compound entities resolve', () => {
    expect(decodeEntities('&amp;#x27;')).toBe("'");
    expect(decodeEntities('&amp;quot;')).toBe('"');
  });

  it('handles named and numeric quotes', () => {
    expect(decodeEntities('&#x27;')).toBe("'");
    expect(decodeEntities('&#039;')).toBe("'");
    expect(decodeEntities('&quot;Hi&quot;')).toBe('"Hi"');
  });
});

describe('escapeHtml', () => {
  it('escapes after decode', () => {
    expect(escapeHtml('<script>')).toBe('&lt;script&gt;');
    expect(escapeHtml('&amp;#x27;')).toContain('&#'); // re-encoded quote
  });

  it('returns empty for nullish', () => {
    expect(escapeHtml(null)).toBe('');
    expect(escapeHtml(undefined)).toBe('');
  });
});

describe('validateRelativeRedirectPath', () => {
  it('allows same-origin relative paths', () => {
    expect(validateRelativeRedirectPath('/dashboard')).toBe('/dashboard');
    expect(validateRelativeRedirectPath('/auth/login?x=1')).toBe('/auth/login?x=1');
  });

  it('rejects open redirects', () => {
    expect(validateRelativeRedirectPath('https://evil.com')).toBeNull();
    expect(validateRelativeRedirectPath('//evil.com')).toBeNull();
    expect(validateRelativeRedirectPath('')).toBeNull();
  });
});

describe('sanitizeLogValue', () => {
  it('strips control characters', () => {
    expect(sanitizeLogValue('a\nb\rc')).toBe('a b c');
  });
});
