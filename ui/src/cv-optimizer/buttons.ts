import { getHasAiConfigured } from './state-access';

export function setStartBtnLoading(
  btn: HTMLButtonElement | null | undefined,
): void {
  if (!btn) return;
  btn.disabled = true;
  btn.classList.add('loading');
}

export function resetStartBtn(
  btn: HTMLButtonElement | null | undefined,
): void {
  if (!btn) return;
  btn.classList.remove('loading');
  btn.disabled = !getHasAiConfigured();
}
