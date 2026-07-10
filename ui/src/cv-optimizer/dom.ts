export function el(id: string): HTMLElement | null {
  return document.getElementById(id);
}

export function setHidden(element: HTMLElement | null, hidden: boolean): void {
  if (!element) return;
  if (hidden) {
    element.classList.add('is-hidden');
  } else {
    element.classList.remove('is-hidden');
  }
}

export function showSection(sectionId: string): void {
  ['cvo-setup', 'cvo-progress', 'cvo-results'].forEach((id) => {
    setHidden(el(id), id !== sectionId);
  });
}
