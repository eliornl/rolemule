/**
 * Landing page — scroll animations, navbar, screenshot tabs.
 * Kept in sync with ui/src/pages/landing.ts via scripts/sync_marketing_site_assets.sh
 */
function ssActivateTab(tabId) {
  var ssTabs = document.querySelectorAll('.ss-tab');
  var ssPanels = document.querySelectorAll('.ss-panel');
  var ssPanelsContainer = document.querySelector('.ss-panels');

  ssTabs.forEach(function (t) {
    var isActive = t.dataset.ssTab === tabId;
    t.classList.toggle('active', isActive);
    t.setAttribute('aria-selected', isActive ? 'true' : 'false');
  });
  ssPanels.forEach(function (p) {
    p.classList.toggle('active', p.id === 'ss-panel-' + tabId);
  });
  if (ssPanelsContainer) ssPanelsContainer.scrollTop = 0;
}

function initLandingPage() {
  var observer = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('animate-visible');
        }
      });
    },
    { threshold: 0.1, rootMargin: '0px 0px -50px 0px' }
  );

  document.querySelectorAll('.animate-fade-up').forEach(function (el) {
    observer.observe(el);
  });

  var navbar = document.querySelector('.navbar');
  if (navbar) {
    window.addEventListener('scroll', function () {
      if (window.scrollY > 50) {
        navbar.classList.add('navbar-scrolled');
      } else {
        navbar.classList.remove('navbar-scrolled');
      }
    });
  }

  var ssTabs = document.querySelectorAll('.ss-tab');
  if (ssTabs.length > 0) {
    ssTabs.forEach(function (tab) {
      tab.addEventListener('click', function () {
        var targetTab = tab.dataset.ssTab;
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
