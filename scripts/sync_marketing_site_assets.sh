#!/usr/bin/env bash
# Sync CSS / images / Font Awesome / landing.js into site/assets/ for GitHub Pages.
# Does not overwrite site/index.html or site/llms.txt (marketing CTAs stay hand-tuned).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/ui/static"
DEST="$ROOT/site/assets"

mkdir -p \
  "$DEST/css/base" \
  "$DEST/js" \
  "$DEST/img/screenshots" \
  "$DEST/vendor/fontawesome"

cp "$SRC/css/base/variables.css" "$DEST/css/base/variables.css"
cp "$SRC/css/landing.css" "$DEST/css/landing.css"
cp "$SRC/css/app.css" "$DEST/css/app.css"

cp "$SRC/img/rolemule-icon.png" "$DEST/img/rolemule-icon.png"
cp "$SRC/img/favicon.svg" "$DEST/img/favicon.svg"
cp "$SRC/img/favicon.png" "$DEST/img/favicon.png" 2>/dev/null || cp "$SRC/favicon.png" "$DEST/img/favicon.png"
cp "$SRC/favicon.ico" "$DEST/favicon.ico" 2>/dev/null || true
cp "$SRC/favicon.png" "$DEST/favicon.png" 2>/dev/null || true

# Screenshots (skip macOS junk)
find "$SRC/img/screenshots" -maxdepth 1 -type f -name 'tab-*.png' -exec cp {} "$DEST/img/screenshots/" \;

rsync -a --delete \
  "$SRC/vendor/fontawesome/css/" "$DEST/vendor/fontawesome/css/"
rsync -a --delete \
  "$SRC/vendor/fontawesome/webfonts/" "$DEST/vendor/fontawesome/webfonts/"

# Plain JS (no Vite hash) — keep in sync with ui/src/pages/landing.ts behavior
cat > "$DEST/js/landing.js" <<'EOF'
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
EOF

echo "Synced marketing assets → site/assets/"
