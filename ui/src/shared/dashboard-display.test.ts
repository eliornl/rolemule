import { describe, expect, it } from 'vitest';
import {
  displayCompanyNameOrUnknown,
  isPlaceholderCompanyName,
  isPlaceholderJobTitle,
  resolveEffectiveCompanyName,
} from './dashboard-display';
import { formatWorkflowFailureDetail } from './workflow-errors';

describe('dashboard-display', () => {
  it('treats dash-only company names as placeholders', () => {
    expect(isPlaceholderCompanyName('—')).toBe(true);
    expect(displayCompanyNameOrUnknown('—')).toBe('Unknown');
    expect(displayCompanyNameOrUnknown('Acme Corp')).toBe('Acme Corp');
  });

  it('falls back to application company when analyzer employer is absent', () => {
    expect(
      resolveEffectiveCompanyName({
        analysisCompanyName: null,
        applicationCompanyName: 'Syndesus, Inc.',
      }),
    ).toBe('Syndesus, Inc.');
    expect(
      resolveEffectiveCompanyName({
        analysisCompanyName: 'Acme Corp',
        applicationCompanyName: 'Syndesus, Inc.',
      }),
    ).toBe('Acme Corp');
  });

  it('flags UI chrome as placeholder job titles', () => {
    expect(isPlaceholderJobTitle('Easy Apply')).toBe(true);
    expect(isPlaceholderJobTitle('Software Engineer')).toBe(false);
  });
});

describe('formatWorkflowFailureDetail', () => {
  it('shortens quota errors for dashboard toasts', () => {
    const raw = '[job_analyzer] 429 RESOURCE_EXHAUSTED';
    expect(formatWorkflowFailureDetail(raw)).toContain('quota or rate limit');
  });
});
