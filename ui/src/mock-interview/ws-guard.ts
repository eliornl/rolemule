/** True when a mock-interview WS event belongs to the open application session. */
export function isMockInterviewMessageForSession(
  msg: Record<string, unknown>,
  currentSessionId: string | null,
): boolean {
  const type = String(msg['type'] || '');
  if (!type.startsWith('mock_interview_')) return false;
  if (!currentSessionId) return false;
  return String(msg['session_id'] || '') === currentSessionId;
}
