/**
 * Browser STT (Web Speech API) + TTS (speechSynthesis). English only.
 * Pauses mic while TTS speaks so the interviewer is not transcribed.
 */
type TranscriptCb = (text: string, isFinal: boolean) => void;

interface SpeechRecognitionLike {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
}

interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }>;
}

type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

/** Pause with no new speech before treating the answer as done. */
export const VOICE_SILENCE_MS = 5000;

function getSpeechRecognitionCtor(): SpeechRecognitionCtor | null {
  const w = window as Window & {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

export function isSttSupported(): boolean {
  return getSpeechRecognitionCtor() !== null;
}

export function isTtsSupported(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window;
}

let recognition: SpeechRecognitionLike | null = null;
let finalBuffer = '';
let silenceTimerId: number | null = null;
let onSilenceCallback: (() => void) | null = null;
let onTranscriptCb: TranscriptCb | null = null;
let onErrorCb: ((msg: string) => void) | null = null;
let resumeMicAfterTts = false;
let ttsPausedMic = false;

function clearSilenceTimer(): void {
  if (silenceTimerId !== null) {
    clearTimeout(silenceTimerId);
    silenceTimerId = null;
  }
}

function armSilenceTimer(): void {
  clearSilenceTimer();
  if (!onSilenceCallback || ttsPausedMic) return;
  silenceTimerId = window.setTimeout(() => {
    silenceTimerId = null;
    if (finalBuffer.trim().length < 5) return;
    const cb = onSilenceCallback;
    onSilenceCallback = null;
    cb?.();
  }, VOICE_SILENCE_MS);
}

export function isListening(): boolean {
  return recognition !== null;
}

export function startListening(
  onTranscript: TranscriptCb,
  onError?: (msg: string) => void,
  onSilenceDone?: () => void,
): boolean {
  const Ctor = getSpeechRecognitionCtor();
  if (!Ctor) {
    onError?.('Voice input is not supported in this browser. You can type your answers.');
    return false;
  }
  stopListening({ clearCallbacks: false });
  finalBuffer = '';
  onTranscriptCb = onTranscript;
  onErrorCb = onError || null;
  onSilenceCallback = onSilenceDone || null;
  resumeMicAfterTts = true;
  ttsPausedMic = false;
  return _startRecognition();
}

function _startRecognition(): boolean {
  const Ctor = getSpeechRecognitionCtor();
  if (!Ctor || !onTranscriptCb) return false;
  const rec = new Ctor();
  rec.continuous = true;
  rec.interimResults = true;
  rec.lang = 'en-US';
  rec.onresult = (event) => {
    if (ttsPausedMic) return;
    let interim = '';
    let finalChunk = '';
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const r = event.results[i];
      if (!r) continue;
      if (r.isFinal) finalChunk += r[0].transcript;
      else interim += r[0].transcript;
    }
    if (finalChunk) {
      finalBuffer += finalChunk;
      onTranscriptCb?.(finalBuffer + interim, true);
    } else if (interim) {
      onTranscriptCb?.(finalBuffer + interim, false);
    }
    armSilenceTimer();
  };
  rec.onerror = (e) => {
    const code = e?.error || 'error';
    const friendly: Record<string, string> = {
      'not-allowed': 'Microphone permission denied. Allow it in browser settings, or type your answer.',
      'no-speech': 'No speech detected. Try again or type your answer.',
      'audio-capture': 'No microphone found. Type your answer instead.',
      network: 'Speech service network error. Type your answer instead.',
    };
    onErrorCb?.(friendly[code] || `Voice error: ${code}`);
  };
  rec.onend = () => {
    recognition = null;
    clearSilenceTimer();
    if (ttsPausedMic && resumeMicAfterTts) {
      // Will resume from speakText onend
      return;
    }
  };
  try {
    rec.start();
    recognition = rec;
    return true;
  } catch (err) {
    const e = err as Error;
    if (e?.name !== 'InvalidStateError') {
      onErrorCb?.(e?.message || 'Could not start microphone.');
    }
    return false;
  }
}

export function stopListening(opts?: { clearCallbacks?: boolean }): void {
  clearSilenceTimer();
  const clearCbs = opts?.clearCallbacks !== false;
  if (clearCbs) {
    onSilenceCallback = null;
    onTranscriptCb = null;
    onErrorCb = null;
    resumeMicAfterTts = false;
    ttsPausedMic = false;
  }
  if (!recognition) return;
  try {
    recognition.stop();
  } catch {
    /* ignore */
  }
  recognition = null;
}

function pauseMicForTts(): void {
  if (!recognition && !onTranscriptCb) return;
  if (!recognition) return;
  ttsPausedMic = true;
  clearSilenceTimer();
  try {
    recognition.stop();
  } catch {
    /* ignore */
  }
  recognition = null;
}

function resumeMicAfterTtsIfNeeded(): void {
  if (!ttsPausedMic || !resumeMicAfterTts || !onTranscriptCb) {
    ttsPausedMic = false;
    return;
  }
  ttsPausedMic = false;
  _startRecognition();
}

export function speakText(text: string): void {
  if (!isTtsSupported() || !text.trim()) return;
  try {
    window.speechSynthesis.cancel();
    pauseMicForTts();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = 'en-US';
    u.rate = 1;
    u.onend = () => resumeMicAfterTtsIfNeeded();
    u.onerror = () => resumeMicAfterTtsIfNeeded();
    window.speechSynthesis.speak(u);
  } catch {
    resumeMicAfterTtsIfNeeded();
  }
}

export function stopSpeaking(): void {
  if (!isTtsSupported()) return;
  try {
    window.speechSynthesis.cancel();
  } catch {
    /* ignore */
  }
  resumeMicAfterTtsIfNeeded();
}
