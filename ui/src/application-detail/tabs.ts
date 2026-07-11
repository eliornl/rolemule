export function switchTab(tabId: string | null | undefined): void {
  if (!tabId) return;
  document.querySelectorAll('.page-tab').forEach((btn) => {
    btn.classList.toggle('active', (btn as HTMLElement).dataset.tab === tabId);
  });
  document.querySelectorAll('.tab-pane').forEach((pane) => {
    pane.classList.toggle('active', pane.id === `pane-${tabId}`);
  });
}

export function switchSubTab(
  parentId: string | null | undefined,
  subTabId: string | null | undefined,
): void {
  if (!parentId || !subTabId) return;
  const parent =
    document.getElementById(`pane-${parentId}`) ||
    document.getElementById(`${parentId}Content`);
  if (!parent) return;
  parent.querySelectorAll(`.sub-tabs[data-parent="${parentId}"] .sub-tab`).forEach((btn) => {
    btn.classList.toggle('active', (btn as HTMLElement).dataset.subtab === subTabId);
  });
  parent.querySelectorAll('.sub-pane').forEach((pane) => {
    pane.classList.toggle('active', pane.id === `sub-${parentId}-${subTabId}`);
  });
}
