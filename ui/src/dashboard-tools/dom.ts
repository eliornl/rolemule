export function el(id: string): HTMLElement | null {
  return document.getElementById(id);
}

export function getVal(id: string): string {
  const node = document.getElementById(id) as
    | HTMLInputElement
    | HTMLSelectElement
    | HTMLTextAreaElement
    | null;
  return node?.value ?? '';
}

export function showOutput(id: string): void {
  const out = el(id);
  if (!out) return;
  out.style.display = 'block';
  out.scrollIntoView({ behavior: 'smooth' });
}
