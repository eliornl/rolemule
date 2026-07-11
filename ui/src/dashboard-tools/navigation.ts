import { el } from './dom';

export function showTool(toolName: string, evt?: MouseEvent): void {
  document.querySelectorAll('.tool-section').forEach((s) => {
    s.classList.remove('active');
  });
  document.querySelectorAll('.nav-link').forEach((l) => {
    l.classList.remove('active');
  });
  el(`${toolName}Section`)?.classList.add('active');
  const navTarget =
    (evt?.target as Element | null) ??
    document.querySelector(`.tools-nav a[data-tool="${toolName}"]`);
  navTarget?.closest('.nav-link')?.classList.add('active');
  const alertContainer = el('alertContainer');
  if (alertContainer) alertContainer.innerHTML = '';
}
