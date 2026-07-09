import { describe, it, expect } from 'vitest';
import {
  isValidEmail,
  validateStrongPassword,
} from './auth-ui';

describe('auth-ui', () => {
  it('validates email format', () => {
    expect(isValidEmail('user@example.com')).toBe(true);
    expect(isValidEmail('not-an-email')).toBe(false);
  });

  it('validates strong password rules', () => {
    expect(validateStrongPassword('Abcd1234!')).toBe(true);
    expect(validateStrongPassword('short')).toBe(false);
    expect(validateStrongPassword('nouppercase1!')).toBe(false);
  });
});
