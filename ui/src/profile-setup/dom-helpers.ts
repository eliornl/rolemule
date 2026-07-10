/** Typed DOM lookups for profile setup forms. */

export function inputEl(id: string): HTMLInputElement | null {
  return document.getElementById(id) as HTMLInputElement | null;
}

export function textareaEl(id: string): HTMLTextAreaElement | null {
  return document.getElementById(id) as HTMLTextAreaElement | null;
}

export function checkboxEl(id: string): HTMLInputElement | null {
  return document.getElementById(id) as HTMLInputElement | null;
}

export function checkedInput(
  selector: string,
): HTMLInputElement | null {
  const el = document.querySelector(selector);
  return el instanceof HTMLInputElement ? el : null;
}
