import {
  abortMockInterview,
  fetchMockInterview,
  fetchMockStatus,
  finishMockInterview,
  startMockInterview,
  submitTurn,
} from './api';
import {
  checkApiKeyStatus,
  clearAnswer,
  clearTranscript,
  getAnswerText,
  notify,
  renderCoverage,
  renderDebrief,
  setCountdown,
  setInterviewerSpeak,
  setInterviewerTyping,
  appendInterviewerDelta,
  setThinking,
  setTip,
  setVoiceBanner,
  showSection,
  appendTranscriptLine,
  setAnswerText,
} from './render';
import {
  getCountdownTimerId,
  getIsBusy,
  getLastSpeak,
  getPollTimeoutId,
  getSessionId,
  setCountdownTimerId,
  setIsBusy,
  setLastSpeak,
  setPollTimeoutId,
  type MockStyle,
} from './state';
import { speakText, startListening, stopListening, stopSpeaking } from './voice';
import { isMockInterviewMessageForSession } from './ws-guard';

let autoFinishTriggered = false;

function selectedStyle(): MockStyle {
  const sel = document.getElementById('mi-style') as HTMLSelectElement | null;
  const v = (sel?.value || 'hr') as MockStyle;
  return v === 'pro' || v === 'manager' ? v : 'hr';
}

function selectedDuration(): number {
  const sel = document.getElementById('mi-duration') as HTMLSelectElement | null;
  const n = parseInt(sel?.value || '15', 10);
  return n === 10 || n === 20 ? n : 15;
}

function selectedStarCoach(): boolean {
  const box = document.getElementById('mi-star-coach') as HTMLInputElement | null;
  return Boolean(box?.checked);
}

function applyPlanFromPayload(payload: Record<string, unknown>): void {
  const plan = Array.isArray(payload['plan'])
    ? (payload['plan'] as Array<Record<string, unknown>>)
    : [];
  const covered = Array.isArray(payload['covered_plan_ids'])
    ? (payload['covered_plan_ids'] as string[])
    : [];
  renderCoverage(plan, covered);
}

function stopCountdown(): void {
  const id = getCountdownTimerId();
  if (id !== null) {
    clearInterval(id);
    setCountdownTimerId(null);
  }
}

function startCountdownFromEndsAt(endsAt: string | undefined | null): void {
  stopCountdown();
  autoFinishTriggered = false;
  if (!endsAt) {
    setCountdown(null);
    return;
  }
  const tick = () => {
    const ends = Date.parse(endsAt);
    if (Number.isNaN(ends)) {
      setCountdown(null);
      return;
    }
    const sec = Math.max(0, Math.floor((ends - Date.now()) / 1000));
    setCountdown(sec);
    if (sec <= 0 && !autoFinishTriggered && !getIsBusy()) {
      autoFinishTriggered = true;
      stopCountdown();
      notify('Time is up — wrapping up your practice…', 'info');
      void handleFinish({ skipConfirm: true });
    }
  };
  tick();
  setCountdownTimerId(window.setInterval(tick, 1000));
}

function stopPolling(): void {
  const id = getPollTimeoutId();
  if (id !== null) {
    clearTimeout(id);
    setPollTimeoutId(null);
  }
}

export function startPollingFallback(): void {
  stopPolling();
  const sessionId = getSessionId();
  if (!sessionId) return;
  let attempts = 0;
  const loop = async () => {
    attempts += 1;
    if (attempts > 120) {
      stopPolling();
      return;
    }
    try {
      const status = await fetchMockStatus(sessionId);
      if (status['is_thinking']) setThinking(true);
      else setThinking(false);
      if (typeof status['seconds_remaining'] === 'number') {
        setCountdown(status['seconds_remaining'] as number);
      }
      if (status['status'] === 'complete') {
        stopPolling();
        await loadAndRender();
        return;
      }
    } catch {
      /* ignore poll errors */
    }
    setPollTimeoutId(window.setTimeout(() => void loop(), 5000));
  };
  setPollTimeoutId(window.setTimeout(() => void loop(), 5000));
}

export async function loadAndRender(): Promise<void> {
  const sessionId = getSessionId();
  if (!sessionId) return;
  setVoiceBanner();
  void checkApiKeyStatus();
  try {
    const data = await fetchMockInterview(sessionId);
    const active = data['active'] as Record<string, unknown> | null | undefined;
    if (active && active['status'] === 'complete' && active['debrief']) {
      showSection('results');
      renderDebrief(active['debrief'] as Record<string, unknown>);
      stopCountdown();
      return;
    }
    if (active && (active['status'] === 'asking' || active['status'] === 'listening' || active['status'] === 'thinking')) {
      showSection('active');
      clearTranscript();
      const turns = Array.isArray(active['turns']) ? (active['turns'] as Array<Record<string, unknown>>) : [];
      for (const t of turns) {
        appendTranscriptLine(String(t['role'] || ''), String(t['text'] || ''));
      }
      const lastAi = [...turns].reverse().find((t) => t['role'] === 'interviewer');
      if (lastAi) {
        const speak = String(lastAi['text'] || '');
        setInterviewerSpeak(speak);
        setLastSpeak(speak);
      }
      applyPlanFromPayload(active);
      setTip(typeof active['last_tip'] === 'string' ? active['last_tip'] : null);
      startCountdownFromEndsAt(active['ends_at'] as string | undefined);
      setThinking(Boolean(data['is_thinking']));
      return;
    }
    const history = Array.isArray(data['history']) ? (data['history'] as Array<Record<string, unknown>>) : [];
    const completed = history.find((h) => h['status'] === 'complete' && h['debrief']);
    if (completed) {
      showSection('results');
      renderDebrief(completed['debrief'] as Record<string, unknown>);
      stopCountdown();
      return;
    }
    showSection('setup');
    setTip(null);
    stopCountdown();
  } catch (err) {
    const e = err as Error;
    notify(e.message || 'Failed to load practice interview', 'error');
    showSection('setup');
  }
}

async function handleStart(): Promise<void> {
  const sessionId = getSessionId();
  if (!sessionId || getIsBusy()) return;
  setIsBusy(true);
  try {
    startPollingFallback();
    setThinking(true);
    setInterviewerTyping();
    const result = await startMockInterview(
      sessionId,
      selectedStyle(),
      selectedDuration(),
      selectedStarCoach(),
    );
    const speak = String(result['speak'] || '');
    showSection('active');
    clearTranscript();
    clearAnswer();
    setTip(null);
    applyPlanFromPayload(result);
    setThinking(false);
    setInterviewerSpeak(speak);
    setLastSpeak(speak);
    appendTranscriptLine('interviewer', speak);
    speakText(speak);
    startCountdownFromEndsAt(result['ends_at'] as string | undefined);
  } catch (err) {
    stopPolling();
    setThinking(false);
    const e = err as Error & { error_code?: string };
    if (e.error_code === 'CFG_6001') {
      notify('Add your API key in Settings → AI Setup to start practice.', 'warning');
    } else {
      notify(e.message || 'Could not start practice interview', 'error');
    }
  } finally {
    setIsBusy(false);
  }
}

async function handleSubmit(source: 'typed' | 'stt'): Promise<void> {
  const sessionId = getSessionId();
  const answer = getAnswerText();
  if (!sessionId || getIsBusy()) return;
  if (answer.length < 5) {
    notify('Write a fuller answer first.', 'warning');
    return;
  }
  setIsBusy(true);
  setMicUiListening(false);
  stopListening();
  stopSpeaking();
  setThinking(true);
  setInterviewerTyping();
  try {
    startPollingFallback();
    const result = await submitTurn(sessionId, answer, source);
    appendTranscriptLine('candidate', answer);
    clearAnswer();
    const speak = String(result['speak'] || '');
    setThinking(false);
    setInterviewerSpeak(speak);
    setLastSpeak(speak);
    appendTranscriptLine('interviewer', speak);
    setTip(typeof result['tip'] === 'string' ? result['tip'] : null);
    applyPlanFromPayload(result);
    speakText(speak);
    if (typeof result['seconds_remaining'] === 'number') {
      setCountdown(result['seconds_remaining'] as number);
    }
    if (result['status'] === 'complete') {
      stopPolling();
      stopCountdown();
      showSection('results');
      renderDebrief(result['debrief'] as Record<string, unknown>);
    }
  } catch (err) {
    stopPolling();
    setThinking(false);
    const last = getLastSpeak();
    if (last) setInterviewerSpeak(last);
    else setInterviewerSpeak('');
    const e = err as Error;
    notify(e.message || 'Could not submit answer', 'error');
  } finally {
    setIsBusy(false);
  }
}

function setMicUiListening(on: boolean): void {
  const btn = document.getElementById('mi-mic-btn');
  btn?.classList.toggle('mi-listening', on);
  btn?.setAttribute('aria-pressed', on ? 'true' : 'false');
}

function handleMicToggle(): void {
  const btn = document.getElementById('mi-mic-btn');
  const listening = btn?.classList.contains('mi-listening');
  if (listening) {
    stopListening();
    setMicUiListening(false);
    return;
  }
  stopSpeaking();
  const ok = startListening(
    (text) => setAnswerText(text),
    (msg) => {
      notify(msg, 'warning');
      setMicUiListening(false);
    },
    () => {
      setMicUiListening(false);
      stopListening();
      void handleSubmit('stt');
    },
  );
  if (ok) setMicUiListening(true);
}

function handleAnswerKeydown(e: KeyboardEvent): void {
  if (e.key !== 'Enter') return;
  if (e.shiftKey) return;
  e.preventDefault();
  void handleSubmit('typed');
}

function handleReplay(): void {
  const speak = getLastSpeak();
  if (!speak) {
    notify('Nothing to replay yet.', 'info');
    return;
  }
  speakText(speak);
}

async function handleFinish(opts?: { skipConfirm?: boolean }): Promise<void> {
  const sessionId = getSessionId();
  if (!sessionId || getIsBusy()) return;
  if (!opts?.skipConfirm) {
    const confirmFn = window.showConfirm;
    if (typeof confirmFn === 'function') {
      const ok = await confirmFn({
        title: 'End practice early?',
        message: 'We’ll wrap up and generate your scored debrief from what you’ve practiced so far.',
        confirmText: 'End & score',
        cancelText: 'Keep practicing',
        type: 'warning',
      });
      if (!ok) return;
    }
  }
  setIsBusy(true);
  setMicUiListening(false);
  stopListening();
  stopSpeaking();
  try {
    const result = await finishMockInterview(sessionId);
    stopPolling();
    stopCountdown();
    showSection('results');
    renderDebrief(result['debrief'] as Record<string, unknown>);
  } catch (err) {
    if (opts?.skipConfirm) autoFinishTriggered = false;
    const e = err as Error;
    notify(e.message || 'Could not finish', 'error');
  } finally {
    setIsBusy(false);
  }
}

async function handleAbort(): Promise<void> {
  const sessionId = getSessionId();
  if (!sessionId || getIsBusy()) return;
  const confirmFn = window.showConfirm;
  if (typeof confirmFn === 'function') {
    const ok = await confirmFn({
      title: 'Abort practice interview?',
      message: 'Your current practice run will end without a scored debrief.',
      confirmText: 'Abort',
      cancelText: 'Keep practicing',
      type: 'danger',
    });
    if (!ok) return;
  }
  setIsBusy(true);
  setMicUiListening(false);
  stopListening();
  stopSpeaking();
  try {
    await abortMockInterview(sessionId);
    stopPolling();
    stopCountdown();
    showSection('setup');
    setTip(null);
    notify('Practice interview aborted', 'info');
  } catch (err) {
    const e = err as Error;
    notify(e.message || 'Could not abort', 'error');
  } finally {
    setIsBusy(false);
  }
}

export function attachEventListeners(): void {
  const pane = document.getElementById('pane-practice');
  if (!pane) return;
  pane.addEventListener('click', (e) => {
    const target = (e.target as HTMLElement).closest('[data-action]') as HTMLElement | null;
    if (!target) return;
    const action = target.dataset.action;
    if (action === 'miStart') void handleStart();
    if (action === 'miSubmit') void handleSubmit('typed');
    if (action === 'miFinish') void handleFinish();
    if (action === 'miAbort') void handleAbort();
    if (action === 'miReplay') handleReplay();
    if (action === 'miMic') handleMicToggle();
    if (action === 'miStopAudio') {
      stopSpeaking();
      stopListening();
      setMicUiListening(false);
    }
    if (action === 'miPracticeAgain') {
      setTip(null);
      showSection('setup');
    }
  });
  const answer = document.getElementById('mi-answer');
  answer?.addEventListener('keydown', (e) => handleAnswerKeydown(e as KeyboardEvent));
}

export function handleWsMessage(msg: Record<string, unknown>): void {
  if (!isMockInterviewMessageForSession(msg, getSessionId())) return;
  const type = String(msg['type'] || '');
  if (type === 'mock_interview_thinking') {
    setThinking(true);
    setInterviewerTyping();
  }
  if (type === 'mock_interview_speak_delta') {
    setThinking(false);
    const data = msg['data'] as Record<string, unknown> | undefined;
    const delta = String(data?.['delta'] || '');
    if (delta) appendInterviewerDelta(delta);
  }
  if (type === 'mock_interview_utterance') {
    setThinking(false);
    const data = msg['data'] as Record<string, unknown> | undefined;
    const speak = String(data?.['speak'] || '');
    if (speak) {
      setInterviewerSpeak(speak);
      setLastSpeak(speak);
    }
  }
  if (type === 'mock_interview_turn_scored') {
    const data = msg['data'] as Record<string, unknown> | undefined;
    if (typeof data?.['tip'] === 'string' && data['tip']) {
      setTip(data['tip']);
    }
  }
  if (type === 'mock_interview_complete') {
    setThinking(false);
    stopPolling();
    void loadAndRender();
  }
  if (type === 'mock_interview_error') {
    setThinking(false);
    const data = msg['data'] as Record<string, unknown> | undefined;
    notify(String(data?.['error'] || 'Practice interview failed'), 'error');
  }
}
