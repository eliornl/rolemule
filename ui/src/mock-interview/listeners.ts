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
  getLastDebriefRewrite,
  notify,
  renderDebrief,
  setCountdown,
  setInterviewerSpeak,
  setInterviewerTyping,
  appendInterviewerDelta,
  setStartBtnLoading,
  setThinking,
  setTip,
  setVoiceBanner,
  setWrappingUpUi,
  clearWrappingUpUi,
  showSection,
  appendTranscriptLine,
  setAnswerText,
} from './render';
import {
  clearPlanCoverage,
  getCountdownTimerId,
  getIsBusy,
  getLastSpeak,
  getPollTimeoutId,
  getSessionId,
  setCountdownTimerId,
  setIsBusy,
  setLastSpeak,
  setPlanCoverage,
  setPollTimeoutId,
  type MockStyle,
} from './state';
import { speakText, startListening, stopListening, stopSpeaking } from './voice';
import { isMockInterviewMessageForSession } from './ws-guard';

let autoFinishTriggered = false;
/** Timer hit zero while a turn was still in flight — finish after busy clears. */
let pendingTimeUp = false;
/** User chose End early while a turn was in flight — finish after busy clears. */
let pendingFinish = false;

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

function rememberPlanFromPayload(payload: Record<string, unknown>): void {
  const plan = Array.isArray(payload['plan'])
    ? (payload['plan'] as Array<Record<string, unknown>>)
    : [];
  const covered = Array.isArray(payload['covered_plan_ids'])
    ? (payload['covered_plan_ids'] as string[])
    : [];
  setPlanCoverage(plan, covered);
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
  pendingTimeUp = false;
  pendingFinish = false;
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
    if (sec <= 0 && !autoFinishTriggered) {
      if (getIsBusy()) {
        pendingTimeUp = true;
        return;
      }
      autoFinishTriggered = true;
      stopCountdown();
      void handleTimeUp();
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
      rememberPlanFromPayload(active);
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
      rememberPlanFromPayload(active);
      setTip(typeof active['last_tip'] === 'string' ? active['last_tip'] : null);
      startCountdownFromEndsAt(active['ends_at'] as string | undefined);
      setThinking(Boolean(data['is_thinking']));
      return;
    }
    const history = Array.isArray(data['history']) ? (data['history'] as Array<Record<string, unknown>>) : [];
    const completed = history.find((h) => h['status'] === 'complete' && h['debrief']);
    if (completed) {
      showSection('results');
      rememberPlanFromPayload(completed);
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
  setStartBtnLoading(true);
  try {
    startPollingFallback();
    // Switch into the live view immediately so the wait isn't a frozen setup screen
    showSection('active');
    clearTranscript();
    clearAnswer();
    setTip(null);
    clearPlanCoverage();
    setCountdown(null);
    setThinking(true);
    setInterviewerTyping();
    const result = await startMockInterview(
      sessionId,
      selectedStyle(),
      selectedDuration(),
    );
    const speak = String(result['speak'] || '');
    rememberPlanFromPayload(result);
    setThinking(false);
    setInterviewerSpeak(speak);
    setLastSpeak(speak);
    appendTranscriptLine('interviewer', speak);
    speakText(speak);
    startCountdownFromEndsAt(result['ends_at'] as string | undefined);
  } catch (err) {
    stopPolling();
    setThinking(false);
    showSection('setup');
    const e = err as Error & { error_code?: string };
    if (e.error_code === 'CFG_6001') {
      notify('Add your API key in Settings → AI Setup to start practice.', 'warning');
    } else {
      notify(e.message || 'Could not start practice interview', 'error');
    }
  } finally {
    setStartBtnLoading(false);
    setIsBusy(false);
  }
}

async function handleSubmit(source: 'typed' | 'stt'): Promise<boolean> {
  const sessionId = getSessionId();
  const answer = getAnswerText();
  if (!sessionId || getIsBusy()) return false;
  if (answer.length < 5) {
    notify('Write a fuller answer first.', 'warning');
    return false;
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
    // End-early was requested while this turn was in flight — skip next-question UI.
    if (pendingFinish) {
      if (result['status'] === 'complete') {
        pendingFinish = false;
        pendingTimeUp = false;
        stopPolling();
        stopCountdown();
        showSection('results');
        renderDebrief(result['debrief'] as Record<string, unknown>);
        return true;
      }
      return false;
    }
    const speak = String(result['speak'] || '');
    setThinking(false);
    setInterviewerSpeak(speak);
    setLastSpeak(speak);
    appendTranscriptLine('interviewer', speak);
    setTip(typeof result['tip'] === 'string' ? result['tip'] : null);
    rememberPlanFromPayload(result);
    speakText(speak);
    if (typeof result['seconds_remaining'] === 'number') {
      setCountdown(result['seconds_remaining'] as number);
    }
    if (result['status'] === 'complete') {
      pendingTimeUp = false;
      stopPolling();
      stopCountdown();
      showSection('results');
      renderDebrief(result['debrief'] as Record<string, unknown>);
      return true;
    }
    return false;
  } catch (err) {
    stopPolling();
    setThinking(false);
    const last = getLastSpeak();
    if (last) setInterviewerSpeak(last);
    else setInterviewerSpeak('');
    const e = err as Error;
    notify(e.message || 'Could not submit answer', 'error');
    return false;
  } finally {
    setIsBusy(false);
    if (pendingFinish) {
      pendingFinish = false;
      pendingTimeUp = false;
      autoFinishTriggered = true;
      stopCountdown();
      void handleFinish({ skipConfirm: true });
    } else if (pendingTimeUp && !autoFinishTriggered) {
      pendingTimeUp = false;
      autoFinishTriggered = true;
      stopCountdown();
      void handleTimeUp();
    }
  }
}

/** Time expired: include any draft answer in the debrief, then wrap up. */
async function handleTimeUp(): Promise<void> {
  const draft = getAnswerText();
  if (draft.length >= 5) {
    notify('Time is up — submitting your answer and wrapping up…', 'info');
  } else {
    notify('Time is up — wrapping up your practice…', 'info');
  }
  // Finish with final_answer (not /turn) so an unsubmitted draft is always scored,
  // even if a previous turn request failed or the clock hit zero mid-flight.
  await handleFinish({ skipConfirm: true });
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

function isBusyConflictError(err: unknown): boolean {
  const e = err as Error & { status?: number; error_code?: string };
  if (e.status === 409) return true;
  if (e.error_code === 'RES_3003') return true;
  return /busy/i.test(e.message || '');
}

async function finishMockInterviewWithRetry(
  sessionId: string,
  finalAnswer?: string,
): Promise<Record<string, unknown>> {
  const delaysMs = [800, 1500, 2000, 2500, 3000];
  let lastErr: unknown;
  for (let attempt = 0; attempt <= delaysMs.length; attempt += 1) {
    try {
      return await finishMockInterview(sessionId, finalAnswer);
    } catch (err) {
      lastErr = err;
      if (!isBusyConflictError(err) || attempt === delaysMs.length) throw err;
      await new Promise((resolve) => {
        window.setTimeout(resolve, delaysMs[attempt]);
      });
    }
  }
  throw lastErr;
}

async function handleFinish(opts?: { skipConfirm?: boolean }): Promise<void> {
  const sessionId = getSessionId();
  if (!sessionId) return;
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
  // Answer still processing — queue finish and show scoring UI immediately.
  if (getIsBusy()) {
    pendingFinish = true;
    pendingTimeUp = false;
    autoFinishTriggered = true;
    stopPolling();
    stopCountdown();
    setCountdown(null);
    setWrappingUpUi();
    notify('Waiting for your current answer to finish, then scoring…', 'info');
    return;
  }
  setIsBusy(true);
  setMicUiListening(false);
  stopListening();
  stopSpeaking();
  stopPolling();
  stopCountdown();
  setCountdown(null);
  setWrappingUpUi();
  const draft = getAnswerText();
  try {
    const result = await finishMockInterviewWithRetry(
      sessionId,
      draft.length >= 5 ? draft : undefined,
    );
    clearAnswer();
    clearWrappingUpUi();
    setThinking(false);
    showSection('results');
    renderDebrief(result['debrief'] as Record<string, unknown>);
  } catch (err) {
    if (opts?.skipConfirm) autoFinishTriggered = false;
    clearWrappingUpUi();
    setThinking(false);
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
    clearPlanCoverage();
    notify('Practice interview aborted', 'info');
  } catch (err) {
    const e = err as Error;
    notify(e.message || 'Could not abort', 'error');
  } finally {
    setIsBusy(false);
  }
}

function clipboardWrite(text: string, successMsg: string): void {
  const plain = text.trim();
  if (!plain) {
    notify('Nothing to copy yet.', 'info');
    return;
  }
  const fallback = (): void => {
    const ta = document.createElement('textarea');
    ta.value = plain;
    ta.setAttribute('readonly', '');
    ta.className = 'clipboard-offscreen';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    try {
      document.execCommand('copy');
      notify(successMsg, 'success');
    } catch (err) {
      console.error('Clipboard fallback failed', err);
      notify('Could not copy to clipboard', 'error');
    }
    document.body.removeChild(ta);
  };
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(plain).then(() => notify(successMsg, 'success'), fallback);
  } else {
    fallback();
  }
}

export function attachEventListeners(): void {
  const pane = document.getElementById('pane-practice');
  if (!pane) return;

  const closeMoreMenu = (): void => {
    const menu = document.getElementById('mi-more-menu');
    const toggle = pane.querySelector('[data-action="miMoreToggle"]') as HTMLElement | null;
    menu?.classList.add('is-hidden');
    toggle?.setAttribute('aria-expanded', 'false');
  };

  pane.addEventListener('click', (e) => {
    const target = (e.target as HTMLElement).closest('[data-action]') as HTMLElement | null;
    if (!target) {
      if (!(e.target as HTMLElement).closest('.mi-more-wrap')) closeMoreMenu();
      return;
    }
    const action = target.dataset.action;
    if (action === 'miStart') void handleStart();
    if (action === 'miSubmit') void handleSubmit('typed');
    if (action === 'miFinish') {
      closeMoreMenu();
      void handleFinish();
    }
    if (action === 'miAbort') {
      closeMoreMenu();
      void handleAbort();
    }
    if (action === 'miReplay') handleReplay();
    if (action === 'miMic') handleMicToggle();
    if (action === 'miStopAudio') {
      stopSpeaking();
      stopListening();
      setMicUiListening(false);
    }
    if (action === 'miMoreToggle') {
      e.stopPropagation();
      const menu = document.getElementById('mi-more-menu');
      if (!menu) return;
      const open = menu.classList.contains('is-hidden');
      menu.classList.toggle('is-hidden', !open);
      target.setAttribute('aria-expanded', open ? 'true' : 'false');
      return;
    }
    if (action === 'miToggleConversation') {
      const section = pane.querySelector('.mi-conversation-section');
      if (!section) return;
      const collapsed = section.classList.toggle('is-collapsed');
      target.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
      target.textContent = collapsed ? 'Show' : 'Hide';
      return;
    }
    if (action === 'miPracticeAgain') {
      setTip(null);
      clearPlanCoverage();
      showSection('setup');
    }
    if (action === 'miCopyRewrite') {
      const idxRaw = target.dataset.index;
      const idx = idxRaw != null && idxRaw !== '' ? parseInt(idxRaw, 10) : undefined;
      clipboardWrite(
        getLastDebriefRewrite(Number.isFinite(idx as number) ? (idx as number) : undefined),
        'Stronger answer copied!',
      );
    }
  });

  document.addEventListener('click', (e) => {
    if (!(e.target as HTMLElement).closest('#pane-practice .mi-more-wrap')) {
      closeMoreMenu();
    }
  });

  const answer = document.getElementById('mi-answer');
  answer?.addEventListener('keydown', (e) => handleAnswerKeydown(e as KeyboardEvent));
}

export function handleWsMessage(msg: Record<string, unknown>): void {
  if (!isMockInterviewMessageForSession(msg, getSessionId())) return;
  const type = String(msg['type'] || '');
  // While finishing/aborting, ignore turn-stream noise so the scoring UI stays stable.
  if (getIsBusy() && (type === 'mock_interview_thinking' || type === 'mock_interview_speak_delta' || type === 'mock_interview_utterance' || type === 'mock_interview_turn_scored')) {
    return;
  }
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
    stopCountdown();
    void loadAndRender();
  }
  if (type === 'mock_interview_error') {
    setThinking(false);
    clearWrappingUpUi();
    const data = msg['data'] as Record<string, unknown> | undefined;
    notify(String(data?.['error'] || 'Practice interview failed'), 'error');
  }
}
