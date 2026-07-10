export function el(id: string): HTMLElement | null {
  return document.getElementById(id);
}

export function inputEl(id: string): HTMLInputElement | null {
  return document.getElementById(id) as HTMLInputElement | null;
}

export function selectEl(id: string): HTMLSelectElement | null {
  return document.getElementById(id) as HTMLSelectElement | null;
}
