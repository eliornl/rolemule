export function el(id: string): HTMLElement | null {
  return document.getElementById(id);
}

export function setVisible(id: string, show: boolean): void {
  const node = el(id);
  if (node) node.style.display = show ? 'block' : 'none';
}
