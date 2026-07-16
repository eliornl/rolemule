import { describe, it, expect } from 'vitest';
import { isMockInterviewMessageForSession } from './ws-guard';

describe('isMockInterviewMessageForSession', () => {
  it('accepts matching mock interview events', () => {
    expect(
      isMockInterviewMessageForSession(
        { type: 'mock_interview_utterance', session_id: 'abc' },
        'abc',
      ),
    ).toBe(true);
  });

  it('rejects other sessions', () => {
    expect(
      isMockInterviewMessageForSession(
        { type: 'mock_interview_speak_delta', session_id: 'other' },
        'abc',
      ),
    ).toBe(false);
  });

  it('rejects missing current session', () => {
    expect(
      isMockInterviewMessageForSession(
        { type: 'mock_interview_thinking', session_id: 'abc' },
        null,
      ),
    ).toBe(false);
  });

  it('rejects non mock interview types', () => {
    expect(
      isMockInterviewMessageForSession(
        { type: 'cv_optimization_complete', session_id: 'abc' },
        'abc',
      ),
    ).toBe(false);
  });
});
