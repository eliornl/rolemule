export function showSection(sectionName: string, evt?: MouseEvent): void {
  document.querySelectorAll('.settings-section').forEach((s) => {
    s.classList.remove('active');
  });
  document.querySelectorAll('.nav-link').forEach((l) => {
    l.classList.remove('active');
  });
  document.getElementById(`${sectionName}Section`)?.classList.add('active');
  const navTarget =
    (evt?.target as HTMLElement | null) ??
    document.querySelector<HTMLElement>(
      `.settings-nav a[data-section="${sectionName}"], .settings-sidebar a[data-section="${sectionName}"]`,
    );
  navTarget?.classList.add('active');
  const alertContainer = document.getElementById('alertContainer');
  if (alertContainer) alertContainer.innerHTML = '';
}
