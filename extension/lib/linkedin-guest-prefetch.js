/**
 * MAIN world — runs before the isolated extractor (see popup / service worker).
 * Fetches jobs-guest JSON into sessionStorage; isolated script shares sessionStorage with the tab.
 */
(function roleMuleLinkedInGuestPrefetch() {
  'use strict';

  async function run() {
    var jid = '';
    try {
      jid = new URL(location.href).searchParams.get('currentJobId') || '';
    } catch (e0) {
      return;
    }
    if (!jid || !/^\d+$/.test(jid)) return;

    /* Run in parallel with guest fetch — do not wait on network or top-card reads miss the extractor window. */
    scheduleLinkedInTopCardCapture(jid);

    var url =
      'https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/' +
      encodeURIComponent(jid);

    try {
      var res = await fetch(url, {
        credentials: 'include',
        cache: 'no-store',
        headers: {
          Accept: 'application/json,text/plain,*/*',
          Referer: location.href
        }
      });

      var txt = await res.text();
      try {
        sessionStorage.setItem(
          'jaa_li_guest_meta_' + jid,
          JSON.stringify({
            status: res.status,
            ok: res.ok,
            len: txt ? txt.length : 0,
            ts: Date.now()
          })
        );
        sessionStorage.setItem('jaa_li_guest_body_' + jid, txt || '');
      } catch (se) {
        /* quota */
      }
    } catch (e1) {
      try {
        sessionStorage.setItem('jaa_li_guest_err_' + jid, String(e1 && e1.message ? e1.message : e1));
      } catch (se2) {
        /* ignore */
      }
    }
  }

  function sessionStorageTop() {
    try {
      return window.top.sessionStorage;
    } catch (e) {
      return sessionStorage;
    }
  }

  /** Build header text from one document (top page or same-origin iframe). */
  function buildTopCardText(doc) {
    var lines = [];
    var seen = {};
    function add(raw) {
      var s = String(raw || '')
        .trim()
        .replace(/\s+/g, ' ');
      if (!s || seen[s]) return;
      seen[s] = true;
      lines.push(s);
    }

    var coSel =
      '[class*="job-details-jobs-unified-top-card__company-name"] a, [class*="job-details-jobs-unified-top-card__company-name"]';
    var co = doc.querySelector(coSel);
    if (co) {
      var ct = co.textContent ? co.textContent.trim() : '';
      if (ct) add('Company: ' + ct);
    }

    var ti = doc.querySelector(
      '[class*="job-details-jobs-unified-top-card__job-title"] h1 a, [class*="job-details-jobs-unified-top-card__job-title"] h1'
    );
    if (ti) add(ti.textContent.trim());

    var meta = doc.querySelector(
      '[class*="job-details-jobs-unified-top-card__primary-description-container"], [class*="tertiary-description-container"]'
    );
    if (meta) add(meta.innerText.trim().replace(/\s+/g, ' '));

    var btns = doc.querySelectorAll(
      '.job-details-fit-level-preferences button, [class*="job-details-fit-level"] button, [class*="fit-level-preferences"] button'
    );
    var bi;
    for (bi = 0; bi < btns.length; bi++) {
      add(btns[bi].innerText);
    }

    return lines.join('\n').trim();
  }

  function walkSameOriginFrames(win, depth, visitor) {
    if (!win || depth > 14) return;
    try {
      visitor(win);
    } catch (e0) {
      /* ignore */
    }
    try {
      var ifr = win.document.querySelectorAll('iframe');
      var i;
      for (i = 0; i < ifr.length; i++) {
        try {
          var ch = ifr[i].contentWindow;
          if (ch) walkSameOriginFrames(ch, depth + 1, visitor);
        } catch (e1) {
          /* cross-origin */
        }
      }
    } catch (e2) {
      /* ignore */
    }
  }

  /**
   * Writes `window.top.sessionStorage[jaa_li_topcard_${jid}]` so the isolated injector (main frame)
   * can read it even when the job UI lives in a same-origin iframe (per-frame sessionStorage differs).
   */
  function scheduleLinkedInTopCardCapture(jid) {
    function captureOnce() {
      try {
        var best = '';
        var bestN = 0;
        walkSameOriginFrames(window, 0, function(w) {
          try {
            var out = buildTopCardText(w.document);
            var n = out.replace(/\s+/g, '').length;
            if (n > bestN) {
              bestN = n;
              best = out;
            }
          } catch (eDoc) {
            /* ignore */
          }
        });

        if (bestN >= 12) {
          sessionStorageTop().setItem('jaa_li_topcard_' + jid, best);
        }
      } catch (eCap) {
        /* ignore */
      }
    }

    setTimeout(captureOnce, 0);
    setTimeout(captureOnce, 400);
    setTimeout(captureOnce, 950);
    setTimeout(captureOnce, 1450);
    setTimeout(captureOnce, 2300);
  }

  run();
})();
