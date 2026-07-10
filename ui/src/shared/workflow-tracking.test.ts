import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  NAV_BADGE_KEY,
  NOTIFIED_ANALYSES_KEY,
  TRACKED_SESSIONS_KEY,
  addTrackedSession,
  getTrackedSessions,
  hasNavBadge,
  isWorkflowNotified,
  isWorkflowTerminalStatus,
  setNavBadge,
} from './workflow-tracking';

function createStorageMock(): Storage {
  const store = new Map<string, string>();
  return {
    get length() {
      return store.size;
    },
    clear() {
      store.clear();
    },
    getItem(key: string) {
      return store.get(key) ?? null;
    },
    key() {
      return null;
    },
    removeItem(key: string) {
      store.delete(key);
    },
    setItem(key: string, value: string) {
      store.set(key, value);
    },
  };
}

describe('workflow-tracking', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', createStorageMock());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('detects terminal workflow statuses', () => {
    expect(isWorkflowTerminalStatus('completed')).toBe(true);
    expect(isWorkflowTerminalStatus('processing')).toBe(false);
  });

  it('caps tracked sessions at 20', () => {
    for (let i = 0; i < 25; i++) addTrackedSession(`s-${i}`);
    expect(getTrackedSessions()).toHaveLength(20);
    expect(getTrackedSessions()[0]?.sessionId).toBe('s-5');
  });

  it('reads notified keys including c:/f: prefixes', () => {
    localStorage.setItem(NOTIFIED_ANALYSES_KEY, JSON.stringify(['c:abc']));
    expect(isWorkflowNotified('abc')).toBe(true);
    expect(isWorkflowNotified('xyz')).toBe(false);
  });

  it('sets navbar badge flag', () => {
    setNavBadge();
    expect(localStorage.getItem(NAV_BADGE_KEY)).toBe('1');
    expect(hasNavBadge()).toBe(true);
  });

  it('stores tracked sessions JSON', () => {
    addTrackedSession('sess-1');
    expect(JSON.parse(localStorage.getItem(TRACKED_SESSIONS_KEY) || '[]')).toEqual([
      { sessionId: 'sess-1' },
    ]);
  });
});
