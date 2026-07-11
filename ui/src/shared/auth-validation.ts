/**
 * Email validation helpers for auth pages (login + register).
 */

export interface EmailValidationResult {
  valid: boolean;
  message?: string;
  suggestion?: string;
}

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const EMAIL_TYPO_DOMAINS: Record<string, string[]> = {
  'gmail.com': ['gmail.co', 'gamil.com', 'gmial.com', 'gmail.comm', 'gmail.con', 'gmail.om'],
  'yahoo.com': ['yahoo.co', 'yaho.com', 'yahooo.com', 'yahoo.con', 'yahoo.comm'],
  'outlook.com': ['outlook.co', 'outllok.com', 'outlook.con', 'outlook.comm'],
  'hotmail.com': ['hotmai.com', 'hotmial.com', 'hotmail.co', 'hotmail.con'],
  'aol.com': ['aol.co', 'aol.con', 'aol.comm'],
  'icloud.com': ['icloud.co', 'icloud.con', 'icloud.comm'],
};

const COMMON_DOMAINS = ['gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'icloud.com'];

/** Login-page email validation (typo domain list). */
export function validateLoginEmail(email: string): EmailValidationResult {
  if (!EMAIL_REGEX.test(email)) {
    return { valid: false, message: 'Please enter a valid email address' };
  }
  const parts = email.split('@');
  if (parts.length === 2) {
    const domain = parts[1].toLowerCase();
    for (const [correct, typos] of Object.entries(EMAIL_TYPO_DOMAINS)) {
      if (typos.includes(domain)) {
        return {
          valid: false,
          message: `Did you mean ${parts[0]}@${correct}?`,
          suggestion: `${parts[0]}@${correct}`,
        };
      }
    }
    if (!domain.includes('.')) {
      return {
        valid: false,
        message: 'Your email domain appears to be missing a TLD (e.g. .com, .org)',
      };
    }
    const tld = domain.split('.').pop();
    if (tld && tld.length < 2) {
      return { valid: false, message: 'Your email domain appears to have an invalid TLD' };
    }
  }
  return { valid: true };
}

export interface RegisterEmailResult {
  isValid: boolean;
  message: string;
  suggestion?: string;
}

function levenshteinDistance(a: string, b: string): number {
  const matrix: number[][] = [];
  for (let i = 0; i <= b.length; i++) matrix[i] = [i];
  for (let j = 0; j <= a.length; j++) matrix[0][j] = j;
  for (let i = 1; i <= b.length; i++) {
    for (let j = 1; j <= a.length; j++) {
      matrix[i][j] =
        b[i - 1] === a[j - 1]
          ? matrix[i - 1][j - 1]
          : Math.min(matrix[i - 1][j - 1] + 1, matrix[i][j - 1] + 1, matrix[i - 1][j] + 1);
    }
  }
  return matrix[b.length][a.length];
}

/** Register-page email validation (Levenshtein domain suggestions). */
export function validateRegisterEmail(email: string): RegisterEmailResult {
  if (!email || email.length === 0) {
    return { isValid: false, message: 'Email address is required' };
  }
  if (!EMAIL_REGEX.test(email)) {
    return {
      isValid: false,
      message: 'Please enter a valid email address (e.g., name@example.com)',
    };
  }

  const domainPart = email.split('@')[1];
  if (!domainPart || !domainPart.includes('.')) {
    return {
      isValid: false,
      message: 'Invalid domain format. Domain must include a TLD (e.g., .com)',
    };
  }

  for (const domain of COMMON_DOMAINS) {
    const distance = levenshteinDistance(domainPart, domain);
    if (distance > 0 && distance <= 2 && domainPart !== domain) {
      const correctedEmail = `${email.split('@')[0]}@${domain}`;
      return { isValid: false, message: 'Did you mean', suggestion: correctedEmail };
    }
  }
  return { isValid: true, message: '' };
}
