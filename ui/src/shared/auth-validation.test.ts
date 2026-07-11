import { describe, it, expect } from 'vitest';
import { validateLoginEmail, validateRegisterEmail } from './auth-validation';

describe('auth-validation', () => {
  it('validateLoginEmail catches typo domains', () => {
    const result = validateLoginEmail('user@gamil.com');
    expect(result.valid).toBe(false);
    expect(result.suggestion).toBe('user@gmail.com');
  });

  it('validateLoginEmail accepts valid email', () => {
    expect(validateLoginEmail('user@example.com').valid).toBe(true);
  });

  it('validateRegisterEmail suggests close domain match', () => {
    const result = validateRegisterEmail('user@gmai.com');
    expect(result.isValid).toBe(false);
    expect(result.suggestion).toContain('@gmail.com');
  });
});
