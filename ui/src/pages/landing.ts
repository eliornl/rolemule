/**
 * Landing page — scroll animations, navbar, screenshot tabs.
 */
function ssActivateTab(tabId: string): void {
  const ssTabs = document.querySelectorAll('.ss-tab');
  const ssPanels = document.querySelectorAll('.ss-panel');
  const ssPanelsContainer = document.querySelector('.ss-panels') as HTMLElement | null;

  ssTabs.forEach((t) => {
    const tel = t as HTMLElement;
    const isActive = tel.dataset['ssTab'] === tabId;
    t.classList.toggle('active', isActive);
    t.setAttribute('aria-selected', isActive ? 'true' : 'false');
  });
  ssPanels.forEach((p) => {
    p.classList.toggle('active', p.id === `ss-panel-${tabId}`);
  });
  if (ssPanelsContainer) ssPanelsContainer.scrollTop = 0;
}

function initLandingPage(): void {
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('animate-visible');
        }
      });
    },
    { threshold: 0.1, rootMargin: '0px 0px -50px 0px' },
  );

  document.querySelectorAll('.animate-fade-up').forEach((el) => observer.observe(el));

  const navbar = document.querySelector('.navbar');
  if (navbar) {
    window.addEventListener('scroll', () => {
      if (window.scrollY > 50) {
        navbar.classList.add('navbar-scrolled');
      } else {
        navbar.classList.remove('navbar-scrolled');
      }
    });
  }

  const ssTabs = document.querySelectorAll('.ss-tab');
  if (ssTabs.length > 0) {
    ssTabs.forEach((tab) => {
      tab.addEventListener('click', () => {
        const targetTab = (tab as HTMLElement).dataset['ssTab'];
        if (targetTab) ssActivateTab(targetTab);
      });
    });
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initLandingPage);
} else {
  initLandingPage();
}
