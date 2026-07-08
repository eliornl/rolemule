/**
 * ApplyPilot — page extraction (injected into the active tab).
 * Priority: user selection → schema.org JobPosting (JSON-LD) → site connectors → generic DOM heuristics.
 * Assigned on window so chrome.scripting.executeScript can invoke it after this file loads.
 */
(function registerJaaExtract() {
  'use strict';

  var MIN_SELECTION_CHARS = 100;
  var MIN_CANDIDATE_CHARS = 120;
  /** Minimum formatted size to prefer JSON-LD over DOM (many ATS pages embed full description here). */
  var MIN_JSON_LD_CHARS = 180;
  var MAX_EXTRACT_CHARS = 50000;

  /** Bump when extractor behavior changes (shown in diagnostics to confirm reload). */
  var EXTRACTOR_BUILD_ID = 'li-guest-api-v12';

  /** Last LinkedIn jobs-guest attempt (shown in diagnostics when debug on). */
  var lastLinkedInGuestApiDiag = null;

  /** Set by LinkedIn DOM resolution; read when `jaa_debug_extract` / `__JAA_EXTRACT_DEBUG` is on. */
  var lastLinkedInRootPath = null;
  var lastLinkedInDetailRootHint = '';

  function noteLinkedInRoot(el, pathKey) {
    lastLinkedInRootPath = pathKey || null;
    try {
      lastLinkedInDetailRootHint =
        el && el.tagName ? el.tagName + ' ' + String(el.className || '').slice(0, 160) : '';
    } catch (e) {
      lastLinkedInDetailRootHint = '';
    }
  }

  function attachExtractDiagnostics(out) {
    if (!out || typeof out !== 'object') return out;
    /* Page-console localStorage often does NOT apply here: chrome.scripting runs in an isolated world. */
    var enabled = false;
    try {
      enabled = typeof window !== 'undefined' && window.__JAA_EXTRACT_DEBUG === true;
    } catch (e0) {
      enabled = false;
    }
    if (!enabled) {
      try {
        enabled = typeof localStorage !== 'undefined' && localStorage.getItem('jaa_debug_extract') === '1';
      } catch (e1) {
        enabled = false;
      }
    }
    if (!enabled) return out;
    try {
      var c = String(out.content || '');
      out.diagnostics = {
        extractorBuild: EXTRACTOR_BUILD_ID,
        url: String(window.location.href || ''),
        hostPath: String(window.location.hostname || '') + String(window.location.pathname || '').slice(0, 120),
        currentJobId: linkedInUrlJobId(),
        linkedInRootPath: lastLinkedInRootPath,
        linkedInRootHint: lastLinkedInDetailRootHint,
        source: out.source,
        confidence: out.confidence,
        contentLength: c.length,
        contentHead: c.slice(0, 1800),
        contentTail: c.length > 2000 ? c.slice(-900) : ''
      };
      try {
        if (/(?:^|\.)linkedin\.com$/i.test(String(window.location.hostname || '').replace(/^www\./i, ''))) {
          var vk = [];
          var si;
          for (si = 0; si < sessionStorage.length; si++) {
            var sk = sessionStorage.key(si);
            if (sk && sk.indexOf('jaa_li_vp_') === 0) vk.push(sk);
          }
          out.diagnostics.voyagerSessionKeys = vk;
        }
      } catch (eVk) {
        /* ignore */
      }
      try {
        if (lastLinkedInGuestApiDiag && typeof lastLinkedInGuestApiDiag === 'object') {
          out.diagnostics.linkedinGuestApi = lastLinkedInGuestApiDiag;
        }
      } catch (eGa) {
        /* ignore */
      }
    } catch (e2) {
      /* skip */
    }
    return out;
  }

  /**
   * Hostname → extra root selectors for known career sites / ATS boards.
   * Maintained as URLs/DOM change; fall back to generic scoring if no match.
   */
  var SITE_CONNECTOR_ROOTS = [
    { re: /^boards\.greenhouse\.io$/i, selectors: ['#app_body', '[class*="job__description"]', 'main'] },
    { re: /^jobs\.lever\.co$/i, selectors: ['.posting', '.content', 'main'] },
    { re: /^jobs\.ashbyhq\.com$/i, selectors: ['main', '[class*="ashby"]', '[class*="JobPosting"]'] },
    { re: /(^|\.)myworkdayjobs\.com$/i, selectors: ['[data-automation-id="jobPostingDescription"]', '[data-automation-id="richTextArea"]', 'main'] },
    { re: /^(www\.)?indeed\.com$/i, selectors: ['#jobDescriptionText', '[data-testid="job-description"]', '[id*="jobDescription"]'] },
    { re: /^(www\.)?glassdoor\.com$/i, selectors: ['[data-test="jobDescription"]', '[class*="JobDescription"]', 'main'] },
    { re: /^(www\.)?ziprecruiter\.com$/i, selectors: ['[data-test-id="job-description"]', 'article', 'main'] },
    { re: /^(www\.)?monster\.com$/i, selectors: ['[data-testid="job-description"]', '#JobDescription', 'main'] },
    { re: /^(www\.)?careerbuilder\.com$/i, selectors: ['[data-testid="job-description"]', '.job-description', 'main'] }
  ];

  var JOB_KEYWORDS = [
    'responsibilit',
    'requirement',
    'qualification',
    'job description',
    'about the role',
    'about the position',
    'about this role',
    'what you',
    'what we',
    'experience',
    'skills',
    'benefits',
    'compensation',
    'salary',
    'apply',
    'full-time',
    'part-time',
    'remote',
    'hybrid'
  ];

  function addHostnameHints(host, path, add) {
    if (!/linkedin\.(com|cn)$/i.test(host || '') || !/\/jobs/i.test(path || '')) {
      return;
    }
    [
      '.jobs-search__job-details-body',
      '.jobs-details__main-content',
      'article.jobs-description__container'
    ].forEach(function trySel(sel) {
      try {
        document.querySelectorAll(sel).forEach(add);
      } catch (e) {
        /* skip invalid selector in old browsers */
      }
    });
  }

  function addSiteConnectorRoots(host, add) {
    if (!host) return;
    var i;
    var j;
    for (i = 0; i < SITE_CONNECTOR_ROOTS.length; i++) {
      var row = SITE_CONNECTOR_ROOTS[i];
      if (!row.re.test(host)) continue;
      for (j = 0; j < row.selectors.length; j++) {
        try {
          document.querySelectorAll(row.selectors[j]).forEach(add);
        } catch (e) {
          /* invalid selector */
        }
      }
    }
  }

  function htmlToPlainText(html) {
    if (!html) return '';
    var s = String(html);
    try {
      var d = document.createElement('div');
      d.innerHTML = s;
      return (d.innerText || d.textContent || '').trim();
    } catch (e) {
      return s.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
    }
  }

  function isJobPostingType(o) {
    if (!o || typeof o !== 'object') return false;
    var ty = o['@type'];
    if (!ty) return false;
    if (Array.isArray(ty)) {
      return ty.some(function (t) {
        return /JobPosting/i.test(String(t));
      });
    }
    return /JobPosting/i.test(String(ty));
  }

  function collectJobPostingObjects(node, out) {
    if (!node) return;
    if (Array.isArray(node)) {
      var i;
      for (i = 0; i < node.length; i++) collectJobPostingObjects(node[i], out);
      return;
    }
    if (typeof node !== 'object') return;
    if (isJobPostingType(node)) out.push(node);
    if (node['@graph']) collectJobPostingObjects(node['@graph'], out);
    var k;
    for (k in node) {
      if (!Object.prototype.hasOwnProperty.call(node, k)) continue;
      if (k === '@context' || k === '@id') continue;
      var v = node[k];
      if (v && typeof v === 'object') collectJobPostingObjects(v, out);
    }
  }

  /**
   * Schema.org JobPosting.baseSalary is often MonetaryAmount with value as QuantitativeValue
   * (minValue / maxValue / unitText). Ashby and other ATS pages use this shape; String(obj) is wrong.
   */
  function formatJsonLdSalaryField(obj) {
    if (obj == null) return '';
    if (typeof obj === 'number' && !isNaN(obj)) return String(obj);
    if (typeof obj === 'string') return obj.trim();
    if (typeof obj !== 'object') return '';

    var currency = String(obj.currency || obj.salaryCurrency || '')
      .trim()
      .toUpperCase();

    function quantitativeToText(q) {
      if (q == null) return '';
      if (typeof q === 'number' && !isNaN(q)) return String(q);
      if (typeof q === 'string') return q.trim();
      if (typeof q !== 'object') return '';
      var minV = q.minValue;
      var maxV = q.maxValue;
      var single = q.value;
      var span = '';
      if (minV != null && maxV != null && String(minV) !== String(maxV)) {
        span = String(minV) + ' – ' + String(maxV);
      } else if (single != null && single !== '') {
        span = typeof single === 'object' ? quantitativeToText(single) : String(single).trim();
      } else if (minV != null) {
        span = String(minV);
      } else if (maxV != null) {
        span = String(maxV);
      }
      if (!span) return '';
      var ut = q.unitText || q.unitCode;
      if (ut) span += ' (' + String(ut).trim() + ')';
      return span;
    }

    var inner =
      obj.value != null && obj.value !== ''
        ? quantitativeToText(obj.value)
        : quantitativeToText(obj);
    if (!inner) return '';
    return inner + (currency ? ' ' + currency : '');
  }

  function formatOneJobPosting(job) {
    var lines = [];
    if (job.title) lines.push(String(job.title).trim());
    var org = job.hiringOrganization;
    if (org) {
      if (typeof org === 'object' && org.name) lines.push('Company: ' + String(org.name).trim());
      else if (typeof org === 'string') lines.push('Company: ' + org.trim());
    }
    if (job.datePosted) lines.push('Posted: ' + String(job.datePosted));
    if (job.employmentType) {
      var et = job.employmentType;
      lines.push('Employment: ' + (Array.isArray(et) ? et.join(', ') : String(et)));
    }
    if (job.industry) lines.push('Industry: ' + String(job.industry));
    var jl = job.jobLocation;
    if (jl) {
      var locStr = '';
      if (typeof jl === 'object') {
        if (jl.address && typeof jl.address === 'object') {
          var a = jl.address;
          locStr = [a.addressLocality, a.addressRegion, a.addressCountry].filter(Boolean).join(', ');
        } else if (jl.address && typeof jl.address === 'string') {
          locStr = jl.address;
        } else {
          locStr = jl.name || jl.description || '';
        }
      } else {
        locStr = String(jl);
      }
      if (locStr) lines.push('Location: ' + locStr.trim());
    }
    if (job.baseSalary) {
      var sal = formatJsonLdSalaryField(job.baseSalary);
      if (sal) lines.push('Salary: ' + sal);
    } else if (job.estimatedSalary) {
      var es = formatJsonLdSalaryField(job.estimatedSalary);
      if (es) lines.push('Salary: ' + es);
    }
    if (job.skills) {
      var sk = job.skills;
      if (typeof sk === 'string') {
        lines.push('Skills: ' + sk.trim());
      } else if (Array.isArray(sk)) {
        var names = sk
          .map(function (s) {
            return typeof s === 'object' && s && s.name ? s.name : String(s);
          })
          .filter(Boolean);
        if (names.length) lines.push('Skills: ' + names.join(', '));
      }
    }
    if (job.description) {
      lines.push('');
      lines.push(htmlToPlainText(String(job.description)));
    }
    return lines.join('\n').trim();
  }

  function extractJobPostingFromJsonLd() {
    var scripts = document.querySelectorAll('script[type="application/ld+json"]');
    var postings = [];
    var si;
    for (si = 0; si < scripts.length; si++) {
      try {
        var data = JSON.parse(scripts[si].textContent);
        collectJobPostingObjects(data, postings);
      } catch (e) {
        /* invalid JSON */
      }
    }
    if (postings.length === 0) return '';
    var best = '';
    var pi;
    for (pi = 0; pi < postings.length; pi++) {
      var formatted = formatOneJobPosting(postings[pi]);
      if (formatted.length > best.length) best = formatted;
    }
    return cleanText(best);
  }

  function capContent(s) {
    if (!s) return '';
    return s.length > MAX_EXTRACT_CHARS ? s.substring(0, MAX_EXTRACT_CHARS) : s;
  }

  function normalizeWs(t) {
    return (t || '').replace(/\s+/g, ' ').trim();
  }

  /** True if DOM text already contains the structured LD snippet (avoid duplicate blocks). */
  function isDomSupersetOfLd(ld, dom) {
    if (!ld || !dom || ld.length < 40) return false;
    var sample = normalizeWs(ld).substring(0, 140);
    if (sample.length < 40) return false;
    return normalizeWs(dom).indexOf(sample) !== -1;
  }

  function getMetaJobDescription() {
    var og = document.querySelector('meta[property="og:description"]');
    if (og) {
      var c = og.getAttribute('content');
      if (c && c.trim()) return c.trim();
    }
    var tw = document.querySelector('meta[name="twitter:description"]');
    if (tw) {
      var t = tw.getAttribute('content');
      if (t && t.trim()) return t.trim();
    }
    var d = document.querySelector('meta[name="description"]');
    if (d) {
      var m = d.getAttribute('content');
      if (m && m.trim()) return m.trim();
    }
    return '';
  }

  function maybeAppendMetaDescription(content) {
    if (!content || content.length >= 280) return content;
    var meta = getMetaJobDescription();
    if (meta.length < 50) return content;
    var n1 = normalizeWs(content).toLowerCase();
    var n2 = normalizeWs(meta).toLowerCase();
    if (n1.indexOf(n2.substring(0, Math.min(80, n2.length))) !== -1) return content;
    return capContent(content + '\n\n---\n\n' + meta);
  }

  function buildDomExtractedText() {
    var rootEl = pickBestContentRoot();
    var bodyClone = rootEl.cloneNode(true);
    removeSplitViewListRails(bodyClone);
    removeUnwantedElements(bodyClone);
    var text = cleanText(bodyClone.innerText || bodyClone.textContent || '');
    text = text.replace(/\{"[^}]{500,}\}/g, '');
    text = text.replace(/\[[^\]]{500,}\]/g, '');
    return capContent(text);
  }

  /**
   * Split job-search UIs: left column = compact cards (often wrong company if we "win" that node).
   * `/jobs/collections/*` uses different wrappers than `/jobs/search` — include list/card patterns.
   */
  function isInsideSearchResultsRail(el) {
    if (!el || !el.closest) return false;
    /* Do NOT use bare `[class*="jobs-search-results"]` — LinkedIn wraps the whole split view (list + detail)
     * in shells like `jobs-search-results-*`, which would mark the real job-detail pane as "rail" and skip it. */
    if (el.closest('[class*="jobs-search-results__list"]')) return true;
    if (el.closest('[class*="jobs-search-results-list"]')) return true;
    if (el.closest('[class*="search-results__list-item"]')) return true;
    if (el.closest('[class*="scaffold-layout__list"]')) return true;
    if (el.closest('[class*="jobs-feed-card-list"]')) return true;
    if (el.closest('[class*="job-card-list"]')) return true;
    /* LinkedIn collections / recommended left column rows (not the open job pane) */
    if (el.closest('[class*="reusable-search__result-container"]')) return true;
    return false;
  }

  /**
   * Compact list rows (e.g. a card in the left rail) use job-card-* classes; the open posting is in the right rail.
   */
  function isInsideCompactListJobCard(el) {
    if (!el || !el.closest) return false;
    if (el.closest('[class*="jobs-search__right-rail"]')) return false;
    if (el.closest('[class*="jobs-search__job-details--wrapper"]')) return false;
    if (el.closest('[class*="jobs-unified-top-card"]')) return false;
    if (el.closest('[class*="job-card-container"]')) return true;
    if (el.closest('[class*="job-card-list__"]')) return true;
    return false;
  }

  function isLinkedInJobsPage() {
    return /linkedin\.(com|cn)$/i.test(window.location.hostname || '') && /\/jobs/i.test(window.location.pathname || '');
  }

  /**
   * LinkedIn often embeds multiple JobPosting blobs or a feed — the first/longest is not the focused job.
   * DOM + layout is more reliable on /jobs (especially with currentJobId in the URL).
   */
  function shouldSkipJsonLdForLinkedInJobs() {
    return isLinkedInJobsPage();
  }

  /**
   * Split view: the open job description is in the right column — highest getBoundingClientRect().left wins.
   * When `requireJobIdMatch` is true (URL has currentJobId), only consider nodes whose HTML references that posting.
   */
  function getLinkedInRightmostDetailBody(requireJobIdMatch) {
    if (!isLinkedInJobsPage()) return null;
    var jid = linkedInUrlJobId();
    var needles = jid ? linkedInJobPostingNeedles(jid) : [];
    var mustMatch = !!requireJobIdMatch && needles.length > 0;
    var selectors = [
      '.jobs-search__job-details-body',
      'article.jobs-description__container',
      '[class*="jobs-details__main-content"]',
      '[class*="job-details-body"]'
    ];
    var best = null;
    var bestLeft = -Infinity;
    var si;
    var nodes;
    var ni;
    var el;
    var t;
    var rect;
    var blob;
    for (si = 0; si < selectors.length; si++) {
      try {
        nodes = document.querySelectorAll(selectors[si]);
      } catch (e) {
        nodes = [];
      }
      for (ni = 0; ni < nodes.length; ni++) {
        el = nodes[ni];
        if (isInsideSearchResultsRail(el) || isInsideCompactListJobCard(el)) continue;
        blob = (el.innerHTML || '') + (el.outerHTML || '').slice(0, 80000);
        if (mustMatch && !blobMatchesLinkedInJobNeedles(blob, needles)) continue;
        t = (el.innerText || '').trim();
        if (t.length < MIN_CANDIDATE_CHARS) continue;
        if (looksLikeLinkedInHomeJobsRail(t.slice(0, 1600))) continue;
        try {
          rect = el.getBoundingClientRect();
        } catch (e2) {
          continue;
        }
        if (rect.width < 40 || rect.height < 40) continue;
        if (rect.left > bestLeft) {
          bestLeft = rect.left;
          best = el;
        }
      }
    }
    return best;
  }

  /**
   * Prefer the real job-detail body (right pane). When URL has currentJobId, boost nodes that
   * reference it so we never "win" the longest list-card article (e.g. first row = wrong company).
   */
  function getLinkedInAnchoredDetailRoot() {
    if (!isLinkedInJobsPage()) return null;
    var jid = linkedInUrlJobId();
    var detailSelectors = [
      '.jobs-search__job-details-body',
      'article.jobs-description__container',
      '[class*="jobs-details__main-content"]',
      '[class*="job-details-body"]'
    ];
    var scored = [];
    var si;
    var nodes;
    var ni;
    var el;
    var t;
    var blob;
    for (si = 0; si < detailSelectors.length; si++) {
      try {
        nodes = document.querySelectorAll(detailSelectors[si]);
      } catch (e) {
        nodes = [];
      }
      for (ni = 0; ni < nodes.length; ni++) {
        el = nodes[ni];
        if (isInsideSearchResultsRail(el) || isInsideCompactListJobCard(el)) continue;
        t = (el.innerText || '').trim();
        if (t.length < MIN_CANDIDATE_CHARS) continue;
        if (looksLikeLinkedInHomeJobsRail(t.slice(0, 1600))) continue;
        blob = (el.innerHTML || '') + (el.outerHTML || '').slice(0, 60000) + t;
        var score = t.length;
        if (jid && blobMatchesLinkedInJobNeedles(blob, linkedInJobPostingNeedles(jid))) {
          score += 80000;
        }
        scored.push({ el: el, score: score });
      }
    }
    if (scored.length === 0) return null;
    scored.sort(function (a, b) {
      return b.score - a.score;
    });
    return scored[0].el;
  }

  /**
   * LinkedIn: the selected job copy lives in the right column — NOT in the scrollable card list.
   * Use querySelectorAll + longest match so the first DOM match is never a false-positive rail.
   */
  function getLinkedInOpenJobPaneRoot() {
    if (!isLinkedInJobsPage()) return null;

    var jid = linkedInUrlJobId();
    var needles = linkedInJobPostingNeedles(jid || '');

    function bestByTextLength(selectors, preferMatchingJobIdInBlob) {
      var best = null;
      var bestLen = 0;
      var si;
      var nodes;
      var ni;
      var r;
      var txt;
      var blob;
      for (si = 0; si < selectors.length; si++) {
        try {
          nodes = document.querySelectorAll(selectors[si]);
        } catch (e) {
          nodes = [];
        }
        for (ni = 0; ni < nodes.length; ni++) {
          r = nodes[ni];
          if (!r || isInsideSearchResultsRail(r) || isInsideCompactListJobCard(r)) continue;
          blob = (r.innerHTML || '') + (r.innerText || '').slice(0, 120000);
          if (
            preferMatchingJobIdInBlob &&
            jid &&
            needles.length &&
            !blobMatchesLinkedInJobNeedles(blob, needles)
          ) {
            continue;
          }
          txt = (r.innerText || '').trim();
          if (looksLikeLinkedInHomeJobsRail(txt.slice(0, 1600))) continue;
          if (txt.length >= MIN_CANDIDATE_CHARS && txt.length > bestLen) {
            bestLen = txt.length;
            best = r;
          }
        }
      }
      return best;
    }

    var railSelectors = [
      '.jobs-search__right-rail',
      '[class*="jobs-search__right-rail"]',
      '[class*="jobs-split-view__right-rail"]',
      '[class*="scaffold-layout__detail"]'
    ];
    var railFirst =
      jid && needles.length ? bestByTextLength(railSelectors, true) : null;
    if (!railFirst) railFirst = bestByTextLength(railSelectors, false);
    if (railFirst) return railFirst;

    var wrappers = [
      '.jobs-search__job-details--wrapper',
      '[class*="jobs-search__job-details--wrapper"]',
      '[class*="job-details-jobs-unified-top-card"]'
    ];
    var w;
    var wi;
    var wj;
    var wnodes;
    var bestInner = null;
    var bestInnerLen = 0;
    for (wi = 0; wi < wrappers.length; wi++) {
      wnodes = [];
      try {
        wnodes = document.querySelectorAll(wrappers[wi]);
      } catch (e2) {
        /* invalid selector */
      }
      for (wj = 0; wj < wnodes.length; wj++) {
        w = wnodes[wj];
        if (isInsideSearchResultsRail(w) || isInsideCompactListJobCard(w)) continue;
        var inner = w.querySelector(
          '.jobs-search__job-details-body, article.jobs-description__container, [class*="jobs-details__main-content"]'
        );
        var tInner = inner ? (inner.innerText || '').trim() : '';
        if (
          inner &&
          tInner.length >= MIN_CANDIDATE_CHARS &&
          !looksLikeLinkedInHomeJobsRail(tInner.slice(0, 1600)) &&
          tInner.length > bestInnerLen
        ) {
          bestInnerLen = tInner.length;
          bestInner = inner;
        }
      }
    }
    if (bestInner) return bestInner;

    for (wi = 0; wi < wrappers.length; wi++) {
      wnodes = [];
      try {
        wnodes = document.querySelectorAll(wrappers[wi]);
      } catch (e3) {
        wnodes = [];
      }
      for (wj = 0; wj < wnodes.length; wj++) {
        w = wnodes[wj];
        if (isInsideSearchResultsRail(w) || isInsideCompactListJobCard(w)) continue;
        var tWrap = (w.innerText || '').trim();
        if (tWrap.length >= MIN_CANDIDATE_CHARS && !looksLikeLinkedInHomeJobsRail(tWrap.slice(0, 1600))) return w;
      }
    }

    return null;
  }

  function linkedInUrlJobId() {
    try {
      var u = new URL(window.location.href);
      var id = u.searchParams.get('currentJobId');
      if (id && /^\d+$/.test(String(id))) return String(id);
    } catch (e) {
      /* skip */
    }
    return null;
  }

  /** DOM / JSON-LD often use `urn:li:jobPosting:4393453758`, not the bare id — match all shapes. */
  function linkedInJobPostingNeedles(jid) {
    if (!jid) return [];
    return [jid, 'urn:li:jobPosting:' + jid, 'jobPosting:' + jid];
  }

  function blobMatchesLinkedInJobNeedles(blob, needles) {
    if (!blob || !needles.length) return false;
    var i;
    for (i = 0; i < needles.length; i++) {
      if (blob.indexOf(needles[i]) !== -1) return true;
    }
    return false;
  }

  function isElementVisiblyRendered(el) {
    if (!el || el.nodeType !== 1) return false;
    if (el.hasAttribute && el.hasAttribute('hidden')) return false;
    if (el.getAttribute('aria-hidden') === 'true') return false;
    try {
      var st = window.getComputedStyle(el);
      if (st.display === 'none' || st.visibility === 'hidden' || parseFloat(st.opacity) < 0.03) return false;
      var r = el.getBoundingClientRect();
      if (r.width < 24 || r.height < 24) return false;
      return true;
    } catch (e) {
      return false;
    }
  }

  /**
   * Full right-hand job pane: title, comp, location, "About the job", bullets, qualifications.
   * The inner `.jobs-search__job-details-body` / `article.jobs-description__container` nodes are often only
   * part of the story; structured fields in the dashboard go sparse if we clip to that subtree alone.
   */
  function getLinkedInVisibleJobDetailsWrapper() {
    if (!isLinkedInJobsPage() || !linkedInUrlJobId()) return null;
    var vw = Math.max(window.innerWidth || document.documentElement.clientWidth || 800, 320);
    var wrapperSelectors = [
      '[class*="scaffold-layout__detail"]',
      '.jobs-search__job-details--wrapper',
      '[class*="jobs-search__job-details--wrapper"]',
      '[class*="jobs-search-two-pane__details"]',
      '[class*="jobs-details-serp-page__job-details"]',
      '[class*="jobs-unified-structure"]',
      '[class*="jobs-search-job-details"]',
      '[class*="jobs-details-two-column"]'
    ];
    function pickWithMinLeft(minLeftPx) {
      var best = null;
      var bestLen = 0;
      var si;
      var ni;
      var nodes;
      var el;
      var t;
      var r;
      for (si = 0; si < wrapperSelectors.length; si++) {
        try {
          nodes = document.querySelectorAll(wrapperSelectors[si]);
        } catch (e) {
          nodes = [];
        }
        for (ni = 0; ni < nodes.length; ni++) {
          el = nodes[ni];
          if (isInsideSearchResultsRail(el) || isInsideCompactListJobCard(el)) continue;
          if (!isElementVisiblyRendered(el)) continue;
          try {
            r = el.getBoundingClientRect();
          } catch (e2) {
            continue;
          }
          if (r.left < minLeftPx) continue;
          t = (el.innerText || '').trim();
          if (t.length < MIN_CANDIDATE_CHARS) continue;
          /* Outer shells (e.g. jobs-unified-structure) can span list + feed + detail — longest text wins the wrong node. */
          if (looksLikeLinkedInHomeJobsRail(t.slice(0, 1600))) continue;
          if (t.length > bestLen) {
            bestLen = t.length;
            best = el;
          }
        }
      }
      return best;
    }
    /* Prefer right column first; never minLeft 0 on desktop — that re-introduces whole-page shells. */
    var fractions = [0.38, 0.28, 0.2, 0.14, 0.08];
    if (vw < 768) {
      fractions.push(0);
    }
    var fi;
    var w;
    for (fi = 0; fi < fractions.length; fi++) {
      w = pickWithMinLeft(vw * fractions[fi]);
      if (w) return w;
    }
    return null;
  }

  /** Opening text of the homepage / jobs-activity rail (not the focused job-detail column). */
  function looksLikeLinkedInHomeJobsRail(text) {
    var h = (text || '').slice(0, 1400);
    return (
      /Jobs based on your activity/i.test(h) ||
      /Show your interest in these companies/i.test(h) ||
      /Recent job searches/i.test(h) ||
      /Reactivate Premium/i.test(h) ||
      /Jobs where you('|’)re more likely to hear back/i.test(h)
    );
  }

  /**
   * Same approach as common MIT-style extensions (e.g. GitHub "LinkedIn-Job-Extractor"):
   * wait for stable job-description / top-card nodes — not inference from `<main>` text.
   */
  function tryLinkedInJobsSearchCompositeText() {
    if (!isLinkedInJobsPage() || !linkedInUrlJobId()) return '';

    function longestAcross(selectorsCsv) {
      var parts = selectorsCsv.split(',');
      var si;
      var pi;
      var nodes;
      var best = '';
      var t;
      for (si = 0; si < parts.length; si++) {
        try {
          nodes = document.querySelectorAll(parts[si].trim());
        } catch (e) {
          nodes = [];
        }
        for (pi = 0; pi < nodes.length; pi++) {
          t = (nodes[pi].innerText || '').trim();
          if (t.length > best.length) best = t;
        }
      }
      return best;
    }

    function firstNonEmpty(selectorsCsv) {
      var parts = selectorsCsv.split(',');
      var si;
      var el;
      var t;
      for (si = 0; si < parts.length; si++) {
        try {
          el = document.querySelector(parts[si].trim());
        } catch (e2) {
          el = null;
        }
        if (!el) continue;
        t = (el.innerText || '').trim();
        if (t) return t;
      }
      return '';
    }

    var title = firstNonEmpty(
      '.jobs-unified-top-card__job-title, .job-details-jobs-unified-top-card__job-title, .jobs-details-top-card__job-title, h1[class*="job-title"]'
    );
    var company = firstNonEmpty(
      '.jobs-unified-top-card__company-name, .job-details-jobs-unified-top-card__company-name, [class*="jobs-unified-top-card__company-name"], [class*="jobs-details-top-card__company-name"]'
    );
    var desc = longestAcross(
      '.jobs-description-content__text, .jobs-box__html-content, .jobs-search__job-details-body, article.jobs-description__container, .jobs-description__container, [class*="jobs-description-content"], [class*="jobs-details__main-content"], [class*="job-details-body"]'
    );

    var chunks = [];
    if (title) chunks.push(title);
    if (company) chunks.push('Company: ' + company);
    if (desc) {
      chunks.push('');
      chunks.push(desc);
    }
    return chunks.join('\n').trim();
  }

  /**
   * Right-column job-detail shell (list item excluded). Used to scope top-card queries —
   * global `.jobs-unified-top-card` often misses or hits the wrong column after DOM changes.
   */
  function findLinkedInJobDetailPaneRoot() {
    var vw = Math.max(window.innerWidth || document.documentElement.clientWidth || 800, 320);
    var minLeftPx = vw < 520 ? 0 : Math.max(96, vw * 0.11);
    var wrapperSelectors = [
      '[class*="jobs-search__job-details--wrapper"]',
      '[class*="jobs-search-two-pane__details"]',
      '[class*="jobs-details-serp-page__job-details"]',
      '[class*="jobs-details-two-column"]',
      '[class*="job-details-reader"]',
      '[class*="jobs-search__job-details--container"]',
      '[class*="scaffold-layout__detail"]'
    ];
    var best = null;
    var bestScore = -1;
    var si;
    var wi;
    for (si = 0; si < wrapperSelectors.length; si++) {
      var wraps;
      try {
        wraps = document.querySelectorAll(wrapperSelectors[si]);
      } catch (e) {
        wraps = [];
      }
      for (wi = 0; wi < wraps.length; wi++) {
        var w = wraps[wi];
        try {
          if (isInsideSearchResultsRail(w)) continue;
          var r = w.getBoundingClientRect();
          if (r.width < 200 || r.height < 160) continue;
          if (r.left < minLeftPx && vw >= 520) continue;
          var score = r.width * Math.min(r.height, 1600) + r.left * 2;
          if (score > bestScore) {
            bestScore = score;
            best = w;
          }
        } catch (e2) {
          continue;
        }
      }
    }
    return best;
  }

  /** Last resort: an h1 in the right band that looks like a job title, climb to a small header subtree. */
  function pickLinkedInTopCardNearJobTitleH1() {
    var vw = Math.max(window.innerWidth || document.documentElement.clientWidth || 800, 320);
    var minLeftPx = vw < 520 ? 0 : vw * 0.14;
    var h1s;
    try {
      h1s = document.querySelectorAll('h1');
    } catch (eH) {
      return null;
    }
    var hi;
    for (hi = 0; hi < h1s.length; hi++) {
      var h = h1s[hi];
      try {
        var r = h.getBoundingClientRect();
        if (r.left < minLeftPx && vw >= 560) continue;
        var ht = String(h.innerText || '').trim();
        if (!ht || ht.length > 280) continue;
        var card = h.closest(
          '[class*="top-card"], [class*="job-details-header"], [class*="JobDetails"]'
        );
        if (!card) card = h.parentElement && h.parentElement.parentElement;
        if (!card) continue;
        var blob = String(card.innerText || '').trim();
        if (blob.length > 8000) continue;
        var rr = card.getBoundingClientRect();
        if (rr.height > 640) continue;
        return card;
      } catch (e1) {
        continue;
      }
    }
    return null;
  }

  /**
   * Top-card in the job-detail column (right pane). `querySelector` on `.jobs-unified-top-card`
   * often hits the left-rail compact card first — score by geometry.
   */
  function pickLinkedInDetailTopCardElement() {
    var cardSel =
      '.job-details-jobs-unified-top-card, .jobs-unified-top-card, [class*="jobs-details-top-card"], [class*="top-card-layout"], [class*="jobs-details-top-card-wrapper"]';

    var pane = findLinkedInJobDetailPaneRoot();
    if (pane) {
      try {
        var scoped = pane.querySelector(cardSel);
        if (scoped) return scoped;
      } catch (eSc) {
        /* continue */
      }
    }

    try {
      var art = document.querySelector(
        'article.jobs-description__container, [class*="jobs-description__container"], .jobs-description-content__text'
      );
      if (art) {
        var wrap = art.closest(
          '[class*="jobs-search__job-details"], [class*="job-details-reader"], [class*="jobs-details-serp"], [class*="jobs-search-two-pane"]'
        );
        if (wrap) {
          var near = wrap.querySelector(cardSel);
          if (near) return near;
        }
      }
    } catch (eArt) {
      /* skip */
    }

    var vw = Math.max(window.innerWidth || document.documentElement.clientWidth || 800, 320);
    var minLeftPx = vw < 520 ? 0 : Math.max(96, vw * 0.14);

    var selStr = cardSel;
    var parts = selStr.split(',');
    var candidates = [];
    var si;
    var pi;
    var nodes;
    for (si = 0; si < parts.length; si++) {
      try {
        nodes = document.querySelectorAll(parts[si].trim());
      } catch (e) {
        nodes = [];
      }
      for (pi = 0; pi < nodes.length; pi++) {
        var el = nodes[pi];
        try {
          if (!el || !el.getBoundingClientRect) continue;
          if (isInsideSearchResultsRail(el)) continue;
          if (isInsideCompactListJobCard(el)) continue;
          var r = el.getBoundingClientRect();
          if (r.width < 64 || r.height < 36) continue;
          if (r.left < minLeftPx && vw >= 520) continue;
          candidates.push(el);
        } catch (e2) {
          continue;
        }
      }
    }

    if (!candidates.length) {
      return pickLinkedInTopCardNearJobTitleH1();
    }

    var best = null;
    var bestScore = -1;
    var ci;
    for (ci = 0; ci < candidates.length; ci++) {
      var c = candidates[ci];
      var rr = c.getBoundingClientRect();
      var score = rr.width * rr.height + rr.left * 1.5;
      if (score > bestScore) {
        bestScore = score;
        best = c;
      }
    }
    return best || pickLinkedInTopCardNearJobTitleH1();
  }

  /**
   * LinkedIn often omits the bare `job-details-jobs-unified-top-card` block node — only BEM leaves
   * (`__company-name`, `__job-title`, `fit-level-preferences`, …) exist. Climb from a known leaf.
   */
  function resolveLinkedInUnifiedTopCardRoot() {
    if (!isLinkedInJobsPage() || !linkedInUrlJobId()) return null;

    var seeds = [];
    try {
      var f = document.querySelector(
        '.job-details-fit-level-preferences, [class*="job-details-fit-level"], [class*="fit-level-preferences"]'
      );
      if (f) seeds.push(f);
    } catch (e0) {
      /* skip */
    }
    try {
      var jt = document.querySelector(
        '[class*="job-details-jobs-unified-top-card__job-title"], .job-details-jobs-unified-top-card__job-title'
      );
      if (jt) seeds.push(jt);
    } catch (e1) {
      /* skip */
    }
    try {
      var cn = document.querySelector('[class*="job-details-jobs-unified-top-card__company-name"]');
      if (cn) seeds.push(cn);
    } catch (e2) {
      /* skip */
    }

    var si;
    for (si = 0; si < seeds.length; si++) {
      var seed = seeds[si];
      if (!seed) continue;
      var p = seed;
      var depth = 0;
      while (p && depth < 18) {
        try {
          var r = p.getBoundingClientRect();
          var blob = String(p.innerText || '').trim();
          var hasH1 = p.querySelector && p.querySelector('h1');
          var hasCo =
            p.querySelector &&
            (p.querySelector('[class*="company-name"]') || p.querySelector('a[href*="/company/"]'));
          if (
            hasH1 &&
            hasCo &&
            r.width > 140 &&
            r.height > 64 &&
            r.height < 1800 &&
            blob.length > 24 &&
            blob.length < 14000
          ) {
            return p;
          }
        } catch (e3) {
          /* skip */
        }
        p = p.parentElement;
        depth++;
      }
    }

    try {
      var bare = document.querySelector('.job-details-jobs-unified-top-card, .jobs-unified-top-card');
      return bare || null;
    } catch (e4) {
      return null;
    }
  }

  function findLinkedInTopCardElement() {
    return (
      resolveLinkedInUnifiedTopCardRoot() ||
      pickLinkedInDetailTopCardElement() ||
      (function () {
        var pane = getLinkedInVisibleJobDetailsWrapper();
        var scope = pane;
        if (!scope) {
          try {
            scope = document.querySelector('[class*="jobs-search__job-details"]') || document.body;
          } catch (eScope) {
            scope = document.body;
          }
        }
        try {
          return scope.querySelector(
            '.job-details-jobs-unified-top-card, .jobs-unified-top-card, [class*="jobs-details-top-card"]'
          );
        } catch (eF) {
          return null;
        }
      })()
    );
  }

  function readLinkedInTitleCompanyFromCard(card) {
    if (!card) return { title: '', company: '' };

    function textOf(sel) {
      try {
        var el = card.querySelector(sel);
        return el
          ? String(el.innerText || '')
              .trim()
              .replace(/\s+/g, ' ')
          : '';
      } catch (eTxt) {
        return '';
      }
    }

    var company = textOf(
      '[class*="jobs-unified-top-card__company-name"], [class*="job-details-jobs-unified-top-card__company-name"]'
    );
    if (!company) {
      try {
        var ca = card.querySelector('a[href*="/company/"]');
        if (ca) company = String(ca.innerText || '').trim().replace(/\s+/g, ' ');
      } catch (eCo) {
        company = '';
      }
    }
    if (!company) {
      company = textOf('[class*="company-name"] a, a[data-tracking-control-name*="company"]');
    }

    var title = textOf(
      '[class*="jobs-unified-top-card__job-title"], [class*="job-details-jobs-unified-top-card__job-title"], h1[class*="job-title"], [data-test-job-title]'
    );
    if (!title) title = textOf('h1');

    return { title: title, company: company };
  }

  function tryLinkedInVoyagerDetectedFields() {
    var jid = linkedInUrlJobId();
    if (!jid) return { title: '', company: '' };
    try {
      var raw = sessionStorage.getItem('jaa_li_vp_' + jid);
      if (!raw) return { title: '', company: '' };
      var o = JSON.parse(raw);
      return {
        title: o.title ? String(o.title).trim() : '',
        company: o.company ? String(o.company).trim() : ''
      };
    } catch (e) {
      return { title: '', company: '' };
    }
  }

  function pickDetectedLinkedInTitleCompany(metaBlock) {
    var dom = readLinkedInTitleCompanyFromCard(findLinkedInTopCardElement());
    var voyager = tryLinkedInVoyagerDetectedFields();
    var parsed = parseDetectedTitleCompanyFromMetaBlock(metaBlock);
    var title = '';
    var company = '';
    var candidates = [dom.title, voyager.title, parsed.title];
    var ci;
    for (ci = 0; ci < candidates.length; ci++) {
      if (isPlausibleJobTitle(candidates[ci])) {
        title = candidates[ci];
        break;
      }
    }
    var companyCandidates = [dom.company, voyager.company, parsed.company];
    for (ci = 0; ci < companyCandidates.length; ci++) {
      var c = String(companyCandidates[ci] || '').trim();
      if (c && c.length <= MAX_DETECTED_COMPANY_LEN) {
        company = c;
        break;
      }
    }
    return { title: title, company: company };
  }

  /**
   * Visible right-pane top card: employer, title, location/date line, promoted line, salary & job-type pills.
   * jobs-guest HTML often omits these; merge so downstream analysis sees comp + arrangement signals.
   */
  function getLinkedInLiveTopCardMetadataText() {
    if (!isLinkedInJobsPage() || !linkedInUrlJobId()) return '';

    var jidTc = linkedInUrlJobId();
    /* MAIN script may write from an iframe; use top sessionStorage (per-frame storage differs). */
    try {
      var stTop = window.top.sessionStorage;
      var topCached = stTop.getItem('jaa_li_topcard_' + jidTc);
      if (topCached && topCached.replace(/\s+/g, '').length >= 12) {
        return topCached.trim();
      }
    } catch (eTop) {
      /* ignore */
    }
    try {
      var mainCached = sessionStorage.getItem('jaa_li_topcard_' + jidTc);
      if (mainCached && mainCached.replace(/\s+/g, '').length >= 12) {
        return mainCached.trim();
      }
    } catch (eSs) {
      /* ignore */
    }

    var card = findLinkedInTopCardElement();

    if (!card) return '';

    function textOf(sel) {
      try {
        var el = card.querySelector(sel);
        return el ? String(el.innerText || '')
          .trim()
          .replace(/\s+/g, ' ') : '';
      } catch (eTxt) {
        return '';
      }
    }

    var lines = [];
    var seen = {};

    var company = textOf(
      '[class*="jobs-unified-top-card__company-name"], [class*="job-details-jobs-unified-top-card__company-name"]'
    );
    if (!company) {
      try {
        var ca = card.querySelector('a[href*="/company/"]');
        if (ca) company = String(ca.innerText || '').trim().replace(/\s+/g, ' ');
      } catch (eCo) {
        company = '';
      }
    }
    if (!company) {
      company = textOf('[class*="company-name"] a, a[data-tracking-control-name*="company"]');
    }

    var title = textOf(
      '[class*="jobs-unified-top-card__job-title"], [class*="job-details-jobs-unified-top-card__job-title"], h1[class*="job-title"]'
    );
    if (!title) title = textOf('h1');

    var primary = textOf('[class*="primary-description"]');
    var secondary = textOf('[class*="secondary-description"]');
    var tertiary = textOf('[class*="tertiary-description"]');

    if (company) lines.push('Company: ' + company);
    if (title) lines.push(title);
    if (primary) lines.push(primary);
    if (secondary) lines.push(secondary);
    if (tertiary) lines.push(tertiary);

    try {
      card
        .querySelectorAll(
          'ul[class*="job-insight"] li, li[class*="job-insight"], [class*="job-insight-view-model"] span, [class*="topcard__flavor"] li'
        )
        .forEach(function(li) {
          var t = String(li.innerText || '')
            .trim()
            .replace(/\s+/g, ' ');
          if (t && t.length < 280 && !seen[t]) {
            seen[t] = true;
            lines.push(t);
          }
        });
    } catch (eLi) {
      /* skip */
    }

    /* Salary / Hybrid / Full-time — modern layout uses buttons in job-details-fit-level-preferences (not ul.job-insight). */
    try {
      card
        .querySelectorAll(
          '.job-details-fit-level-preferences button, [class*="fit-level-preferences"] button, [class*="job-details-fit-level"] button'
        )
        .forEach(function(btn) {
          var t = String(btn.innerText || '')
            .trim()
            .replace(/\s+/g, ' ');
          if (!t || t.length > 220) return;
          if (!seen[t]) {
            seen[t] = true;
            lines.push(t);
          }
        });
    } catch (eFit) {
      /* skip */
    }

    if (lines.length < 5) {
      try {
        card.querySelectorAll('[class*="job-criteria"], [class*="tvm__text"]').forEach(function(el) {
          var t = String(el.innerText || '')
            .trim()
            .replace(/\s+/g, ' ');
          if (!t || t.length > 220 || t.length < 2) return;
          if (/see application/i.test(t)) return;
          if (!seen[t]) {
            seen[t] = true;
            lines.push(t);
          }
        });
      } catch (eCrit) {
        /* skip */
      }
    }

    /* Structured selectors miss A/B-tested UIs — take header lines until "About the job". */
    if (lines.length < 3) {
      try {
        var rawLines = String(card.innerText || '')
          .split(/\r?\n/)
          .map(function(s) {
            return s.trim();
          })
          .filter(Boolean);
        var ri;
        for (ri = 0; ri < rawLines.length && ri < 22; ri++) {
          var ln = rawLines[ri];
          if (/^about the job\b/i.test(ln)) break;
          if (/^show\s+(more|less)\b/i.test(ln)) continue;
          if (/^show more options\b/i.test(ln)) continue;
          if (/^(share|save|hide|report|dismiss)$/i.test(ln)) continue;
          if (ln.length > 300) continue;
          if (!seen[ln]) {
            seen[ln] = true;
            lines.push(ln);
          }
          if (lines.length >= 14) break;
        }
      } catch (eRaw) {
        /* skip */
      }
    }

    return lines.join('\n').trim();
  }

  function prependLinkedInTopCardMetaIfNeeded(body, metaBlock) {
    if (!body || !metaBlock || metaBlock.length < 10) return body;
    var headNorm = String(body.slice(0, 2000))
      .toLowerCase()
      .replace(/\s+/g, ' ');
    var parts = String(metaBlock)
      .split(/\r?\n/)
      .map(function(s) {
        return s.trim();
      })
      .filter(Boolean);
    var onlyAdd = [];
    var pi;
    for (pi = 0; pi < parts.length; pi++) {
      var p = parts[pi];
      var key = p
        .toLowerCase()
        .replace(/\s+/g, ' ')
        .slice(0, 56);
      if (key.length < 4) continue;
      if (headNorm.indexOf(key) !== -1) continue;
      onlyAdd.push(p);
    }
    if (!onlyAdd.length) return body;
    return onlyAdd.join('\n') + '\n\n---\n\n' + body;
  }

  var LINKEDIN_METADATA_LINE_RE =
    /^(full-time|part-time|contract|hybrid|remote|on-site|onsite|reposted|promoted|\$|usd|eur|gbp|\d+\s+applicant)/i;
  var MAX_DETECTED_TITLE_LEN = 200;
  var MAX_DETECTED_COMPANY_LEN = 200;

  function isPlausibleJobTitle(line) {
    if (!line) return false;
    var s = String(line).trim();
    if (s.length < 4 || s.length > MAX_DETECTED_TITLE_LEN) return false;
    if (LINKEDIN_METADATA_LINE_RE.test(s)) return false;
    var lower = s.toLowerCase();
    if (/^(about|at |we |join |since |our |the |as a )/.test(lower)) return false;
    if (/^show\s+(more|less)\b/.test(lower)) return false;
    if (/^(see\s+more|easy\s+apply|apply\s+now|share|save|hide|report|dismiss)$/.test(lower)) return false;
    if ((s.match(/[.!]/g) || []).length > 1) return false;
    return true;
  }

  function isUnreliableBrowserTabTitle(t) {
    if (!t) return true;
    var s = String(t).trim();
    if (s.length < 3) return true;
    if (/(linkedin|indeed|glassdoor|ziprecruiter|monster|careerbuilder)/i.test(s)) return true;
    if (/^\(\d+\)/.test(s)) return true;
    if (/^search\s*\|/i.test(s)) return true;
    return false;
  }

  function parseDetectedTitleCompanyFromMetaBlock(metaBlock) {
    if (!metaBlock) return { title: '', company: '' };
    var lines = String(metaBlock)
      .split(/\r?\n/)
      .map(function (s) {
        return s.trim();
      })
      .filter(Boolean);
    var title = '';
    var company = '';
    var i;
    for (i = 0; i < lines.length; i++) {
      var line = lines[i];
      if (/^company:\s*/i.test(line)) {
        company = line.replace(/^company:\s*/i, '').trim();
        continue;
      }
      if (
        !title &&
        isPlausibleJobTitle(line) &&
        !/^company:/i.test(line) &&
        !/^posted:/i.test(line) &&
        !/^location:/i.test(line)
      ) {
        title = line;
      }
    }
    if (company.length > MAX_DETECTED_COMPANY_LEN) {
      company = company.slice(0, MAX_DETECTED_COMPANY_LEN).trim();
    }
    return { title: title, company: company };
  }

  function applyLinkedInMetaEnrichment(result, metaBlock) {
    if (!result || typeof result !== 'object') return result;
    if (!isLinkedInJobsPage() || !linkedInUrlJobId()) return result;

    if (metaBlock) {
      result.content = prependLinkedInTopCardMetaIfNeeded(result.content || '', metaBlock);
    }

    var detected = pickDetectedLinkedInTitleCompany(metaBlock);
    if (detected.title) result.detectedTitle = detected.title;
    if (detected.company) result.detectedCompany = detected.company;

    if (!result.detectedTitle && result.content) {
      var headParsed = parseDetectedTitleCompanyFromMetaBlock(
        String(result.content).split(/\r?\n/).slice(0, 10).join('\n')
      );
      if (isPlausibleJobTitle(headParsed.title)) result.detectedTitle = headParsed.title;
      if (headParsed.company && !result.detectedCompany) {
        result.detectedCompany = headParsed.company;
      }
    }

    var tabTitle = result.title || '';
    if (
      !result.detectedTitle &&
      tabTitle &&
      !isUnreliableBrowserTabTitle(tabTitle) &&
      isPlausibleJobTitle(tabTitle)
    ) {
      result.detectedTitle = String(tabTitle).trim();
    }

    return result;
  }

  async function enrichExtractResultWithLinkedInMeta(result) {
    if (!result || typeof result !== 'object') return result;
    if (!isLinkedInJobsPage() || !linkedInUrlJobId()) return result;

    var metaBlock = '';
    var ta;
    for (ta = 0; ta < 10; ta++) {
      metaBlock = getLinkedInLiveTopCardMetadataText();
      if (metaBlock && metaBlock.replace(/\s+/g, '').length >= 14) break;
      if (ta < 9) {
        await new Promise(function (res) {
          setTimeout(res, 150);
        });
      }
    }
    return applyLinkedInMetaEnrichment(result, metaBlock);
  }

  /**
   * MAIN-world hook (`linkedin-voyager-hook.js`) writes parsed posting text to sessionStorage per job id.
   * Same tab storage is visible here (isolated-world extractor).
   */
  function tryLinkedInVoyagerSessionStorage() {
    var jid = linkedInUrlJobId();
    if (!jid) return '';
    try {
      var raw = sessionStorage.getItem('jaa_li_vp_' + jid);
      if (!raw) return '';
      var o = JSON.parse(raw);
      var desc = o.desc ? String(o.desc).trim() : '';
      if (!desc || desc.length < 80) return '';
      var parts = [];
      if (o.title) parts.push(String(o.title).trim());
      if (o.company) parts.push('Company: ' + String(o.company).trim());
      parts.push('');
      parts.push(desc);
      var out = parts.join('\n').trim();
      var head = out.slice(0, 1800);
      if (looksLikeLinkedInHomeJobsRail(head)) return '';
      return out;
    } catch (e) {
      return '';
    }
  }

  function linkedInGuestExtractLongestBody(obj) {
    var best = '';
    function walk(x, depth) {
      if (!x || depth > 48) return;
      if (typeof x === 'string') {
        if (x.length > best.length && x.length >= 160 && x.split(/\s+/).length >= 14) best = x;
        return;
      }
      if (typeof x !== 'object') return;
      var k;
      for (k in x) {
        if (!Object.prototype.hasOwnProperty.call(x, k)) continue;
        var kl = k.toLowerCase();
        if (typeof x[k] === 'string' && /descrip|snippet|sanitized|formatted|plaintext|criteria/i.test(kl)) {
          if (x[k].length > best.length) best = x[k];
        }
        walk(x[k], depth + 1);
      }
    }
    walk(obj, 0);
    return best;
  }

  function linkedInPageCsrfToken() {
    try {
      var m = document.querySelector('meta[name="csrf-token"]');
      if (m) return (m.getAttribute('content') || '').trim();
    } catch (e) {
      /* ignore */
    }
    return '';
  }

  /** Voyager-style envelopes nest the posting under `included` / `data`. */
  function unwindGuestJobPayload(data, jid) {
    if (!data || typeof data !== 'object') return data;
    var needle = 'jobPosting:' + jid;

    var inc = data.included;
    if (Array.isArray(inc)) {
      var i;
      var row;
      for (i = 0; i < inc.length; i++) {
        row = inc[i];
        if (!row || typeof row !== 'object') continue;
        var urn = String(row.entityUrn || row.trackingUrn || '');
        if (urn.indexOf(needle) !== -1) return row;
      }
      for (i = 0; i < inc.length; i++) {
        row = inc[i];
        if (!row || typeof row !== 'object') continue;
        var blob = '';
        try {
          blob = JSON.stringify(row);
        } catch (e2) {
          blob = '';
        }
        if (
          blob.indexOf(jid) !== -1 &&
          (row.description || row.title || row.jobPostingTitle || row.formattedDescription)
        ) {
          return row;
        }
      }
    }

    var d = data.data;
    if (d && typeof d === 'object') {
      if (d.jobPosting && typeof d.jobPosting === 'object') return d.jobPosting;
      if (Array.isArray(d.elements) && d.elements[0]) return d.elements[0];
    }
    return data;
  }

  /**
   * jobs-guest often returns HTTP 200 with an HTML fragment (not JSON). Parse JSON-LD JobPosting + description DOM.
   */
  function extractJobPostingFromGuestHtml(htmlStr, jid) {
    if (!htmlStr || htmlStr.length < 80) return null;
    try {
      var parser = new DOMParser();
      var doc = parser.parseFromString(htmlStr, 'text/html');
      if (!doc || !doc.body) return null;

      var needles = jid ? linkedInJobPostingNeedles(jid) : [];

      var scripts = doc.querySelectorAll('script[type="application/ld+json"]');
      var postings = [];
      var si;
      for (si = 0; si < scripts.length; si++) {
        try {
          var ldData = JSON.parse(scripts[si].textContent || '');
          collectJobPostingObjects(ldData, postings);
        } catch (e0) {
          /* skip invalid */
        }
      }

      function postingMatchesBlob(job) {
        if (!jid || !needles.length) return true;
        var blob = '';
        try {
          blob = JSON.stringify(job);
        } catch (e1) {
          return false;
        }
        var ni;
        for (ni = 0; ni < needles.length; ni++) {
          if (blob.indexOf(needles[ni]) !== -1) return true;
        }
        return false;
      }

      var filtered = postings.filter(postingMatchesBlob);
      var useList = filtered.length ? filtered : postings;

      var bestLd = '';
      var pi;
      for (pi = 0; pi < useList.length; pi++) {
        var formatted = formatOneJobPosting(useList[pi]);
        if (formatted.length > bestLd.length) bestLd = formatted;
      }

      if (
        bestLd.length >= MIN_CANDIDATE_CHARS &&
        !looksLikeLinkedInHomeJobsRail(bestLd.slice(0, 1700))
      ) {
        return {
          text: bestLd,
          titleLen: 0,
          descLen: bestLd.length,
          htmlSource: 'jsonld'
        };
      }

      var descCandidates = [];
      var selectors = [
        '.description__text',
        '.show-more-less-html__markup',
        '.jobs-description-content__text',
        '.jobs-box__html-content',
        '[class*="description-content"]',
        '[class*="jobs-description"]',
        '[class*="job-details"]'
      ];
      var sj;
      for (sj = 0; sj < selectors.length; sj++) {
        try {
          doc.querySelectorAll(selectors[sj]).forEach(function (el) {
            var inner = (el.innerText || '').trim();
            if (inner.length > 200) descCandidates.push(inner);
          });
        } catch (e2) {
          /* skip */
        }
      }
      descCandidates.sort(function (a, b) {
        return b.length - a.length;
      });
      var bodyText = descCandidates.length ? descCandidates[0] : '';

      var titleText = '';
      try {
        var h = doc.querySelector(
          'h1.top-card-layout__title, h1[class*="job-title"], .job-details-jobs-unified-top-card__job-title, h1'
        );
        if (h) titleText = (h.innerText || '').trim().split('\n')[0].trim();
      } catch (e3) {
        /* skip */
      }

      var companyText = '';
      try {
        var ca = doc.querySelector(
          'a.topcard__org-name-link, .jobs-unified-top-card__company-name a, [class*="top-card"] a[data-tracking-control-name]'
        );
        if (ca) companyText = (ca.innerText || '').trim();
      } catch (e4) {
        /* skip */
      }

      var assembled = '';
      if (titleText) assembled += titleText + '\n';
      if (companyText) assembled += 'Company: ' + companyText + '\n';
      if (bodyText) {
        if (assembled) assembled += '\n';
        assembled += bodyText;
      }

      assembled = assembled.trim();
      if (
        assembled.length >= MIN_CANDIDATE_CHARS &&
        !looksLikeLinkedInHomeJobsRail(assembled.slice(0, 1700))
      ) {
        return {
          text: assembled,
          htmlSource: 'dom',
          titleLen: titleText.length,
          descLen: bodyText.length
        };
      }

      return null;
    } catch (e5) {
      return null;
    }
  }

  function parseGuestJobPostingPayload(txt, jid) {
    if (!txt || txt.length < 20) return null;
    var t = String(txt).trim();
    if (t.charAt(0) === '<' || /^\s*<!DOCTYPE/i.test(t)) {
      return extractJobPostingFromGuestHtml(t, jid);
    }

    var data = null;
    try {
      data = JSON.parse(t);
    } catch (e0) {
      var i = t.indexOf('{');
      while (i !== -1) {
        try {
          data = JSON.parse(t.slice(i));
          break;
        } catch (e1) {
          i = t.indexOf('{', i + 1);
        }
      }
    }
    if (!data || typeof data !== 'object') return null;

    var row = unwindGuestJobPayload(data, jid);

    var title =
      row.title ||
      row.jobTitle ||
      (row.jobPostingTitle && (row.jobPostingTitle.text || row.jobPostingTitle)) ||
      '';
    if (typeof title === 'object' && title !== null)
      title = title.text || title.name || '';

    var company = '';
    if (typeof row.companyName === 'string') company = row.companyName;
    else if (row.company && typeof row.company === 'string') company = row.company;
    else if (row.company && row.company.name) company = String(row.company.name);

    var desc = '';
    if (typeof row.description === 'string') desc = row.description;
    else if (row.description && typeof row.description.text === 'string') desc = row.description.text;
    else if (typeof row.descriptionHtml === 'string') desc = htmlToPlainText(row.descriptionHtml);
    else if (row.description && typeof row.description === 'object') {
      desc =
        row.description.text ||
        row.description.plain ||
        row.description.combined ||
        row.description.attributes ||
        '';
      if (typeof desc !== 'string') desc = '';
    }
    if (row.formattedDescription && typeof row.formattedDescription === 'string') {
      desc = desc || htmlToPlainText(row.formattedDescription);
    }
    if (!desc || desc.length < 60) {
      desc = linkedInGuestExtractLongestBody(row);
    }

    title = String(title || '').trim();
    company = String(company || '').trim();
    desc = String(desc || '').trim();

    var chunks = [];
    if (title) chunks.push(title);
    if (company) chunks.push('Company: ' + company);
    if (desc) {
      chunks.push('');
      chunks.push(desc);
    }
    var out = chunks.join('\n').trim();
    if (!out) return null;
    return { text: out, titleLen: title.length, descLen: desc.length };
  }

  /**
   * Public jobs-guest JSON by posting id — prefers MAIN prefetch in sessionStorage (see linkedin-guest-prefetch.js).
   */
  async function tryLinkedInGuestApiJobPostingText() {
    var jid = linkedInUrlJobId();
    if (!jid || !isLinkedInJobsPage()) {
      lastLinkedInGuestApiDiag = { skip: true, reason: 'no_jid_or_not_jobs' };
      return '';
    }

    var url =
      'https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/' +
      encodeURIComponent(jid);

    var txt = '';
    var source = '';
    var meta = null;

    try {
      var rawBody = sessionStorage.getItem('jaa_li_guest_body_' + jid);
      var rawMeta = sessionStorage.getItem('jaa_li_guest_meta_' + jid);
      if (rawMeta) {
        try {
          meta = JSON.parse(rawMeta);
        } catch (em) {
          meta = null;
        }
      }
      if (rawBody && rawBody.length > 20) {
        txt = rawBody;
        source = 'prefetch_sessionStorage';
      }
    } catch (eS) {
      /* ignore */
    }

    if (!txt) {
      try {
        var hdr = {
          Accept: 'application/json,text/plain,*/*',
          Referer: typeof location !== 'undefined' ? location.href : 'https://www.linkedin.com/jobs/'
        };
        var csrf = linkedInPageCsrfToken();
        if (csrf) hdr['csrf-token'] = csrf;

        var res = await fetch(url, {
          credentials: 'include',
          cache: 'no-store',
          mode: 'cors',
          headers: hdr
        });

        meta = { status: res.status, ok: res.ok, len: 0 };
        txt = await res.text();
        meta.len = txt ? txt.length : 0;
        source = 'isolated_fetch';
      } catch (e2) {
        lastLinkedInGuestApiDiag = {
          source: source || 'none',
          error: String(e2 && e2.message ? e2.message : e2),
          meta: meta
        };
        return '';
      }
    }

    var parsed = parseGuestJobPostingPayload(txt, jid);

    if (!parsed || !parsed.text) {
      lastLinkedInGuestApiDiag = {
        source: source,
        meta: meta,
        fail: 'parse_or_empty',
        bodyLen: txt ? txt.length : 0,
        bodyHead: txt ? String(txt).slice(0, 280) : ''
      };
      return '';
    }

    var beforeMetaMerge = parsed.text;
    /* MAIN-world may write jaa_li_topcard_* on a delay; detail pane can hydrate late. */
    var metaBlock = '';
    var ta;
    for (ta = 0; ta < 12; ta++) {
      metaBlock = getLinkedInLiveTopCardMetadataText();
      if (metaBlock && metaBlock.replace(/\s+/g, '').length >= 14) break;
      if (ta < 11) await new Promise(function(res) { setTimeout(res, 150); });
    }
    var out = prependLinkedInTopCardMetaIfNeeded(beforeMetaMerge, metaBlock);
    var topCardPrepended = out !== beforeMetaMerge;

    if (out.length < MIN_CANDIDATE_CHARS) {
      lastLinkedInGuestApiDiag = {
        source: source,
        meta: meta,
        fail: 'short_text',
        outLen: out.length,
        titleLen: parsed.titleLen,
        descLen: parsed.descLen
      };
      return '';
    }
    if (looksLikeLinkedInHomeJobsRail(out.slice(0, 1800))) {
      lastLinkedInGuestApiDiag = {
        source: source,
        meta: meta,
        fail: 'looks_like_feed_rail'
      };
      return '';
    }

    lastLinkedInGuestApiDiag = {
      source: source,
      meta: meta,
      ok: true,
      outLen: out.length,
      htmlSource: parsed.htmlSource || undefined,
      topCardPrepended: topCardPrepended
    };
    return out;
  }

  /**
   * LinkedIn A/B tests often ship hashed class names — no `[class*="jobs-…"]` hooks match.
   * Sample pixels in the likely detail column and score ancestors (geometry + URL job id in HTML).
   */
  function getLinkedInDetailRootFromViewportSample() {
    if (!isLinkedInJobsPage() || !linkedInUrlJobId()) return null;
    var vw = Math.max(window.innerWidth || document.documentElement.clientWidth || 800, 320);
    var vh = Math.max(window.innerHeight || document.documentElement.clientHeight || 500, 400);
    if (vw < 480) return null;

    var jidNeedles = linkedInJobPostingNeedles(linkedInUrlJobId());
    /* ~0.40 was too strict: a wide left list pushes the detail pane to < 40% vw; then no node passes. */
    var minLeftPx = Math.max(200, vw * 0.28);

    function bestAncestorAlongChain(hitEl) {
      if (!hitEl || hitEl.nodeType !== 1) return null;
      var q = hitEl;
      var depth = 0;
      var bestEl = null;
      var bestScore = -Infinity;
      while (q && depth < 34) {
        if (q.nodeType === 1) {
          var tag = q.tagName ? q.tagName.toUpperCase() : '';
          if (tag !== 'HTML' && tag !== 'BODY') {
            if (!/^HEADER$|^FOOTER$|^NAV$|^ASIDE$/i.test(tag)) {
              if (!isInsideSearchResultsRail(q) && !isInsideCompactListJobCard(q)) {
                var r;
                try {
                  r = q.getBoundingClientRect();
                } catch (eR) {
                  q = q.parentElement;
                  depth++;
                  continue;
                }
                if (r.width >= 72 && r.height >= 48 && r.left >= minLeftPx) {
                  var t = (q.innerText || '').trim();
                  if (t.length >= MIN_CANDIDATE_CHARS && !looksLikeLinkedInHomeJobsRail(t.slice(0, 1600))) {
                    var blob = (q.innerHTML || '').slice(0, 120000);
                    var score = Math.min(t.length, 24000) + r.left * 0.14 + Math.min(r.width, 920) * 0.06;
                    if (jidNeedles.length && blobMatchesLinkedInJobNeedles(blob, jidNeedles)) score += 520000;
                    if (/About the job|Job description|Qualificat|Responsibilit|Easy Apply|Posted \d+/i.test(t))
                      score += 12000;
                    if (score > bestScore) {
                      bestScore = score;
                      bestEl = q;
                    }
                  }
                }
              }
            }
          }
        }
        q = q.parentElement;
        depth++;
      }
      if (!bestEl) return null;
      return { el: bestEl, score: bestScore };
    }

    var xi;
    var yi;
    var xCoords = [
      Math.min(vw * 0.88, vw - 10),
      Math.min(vw * 0.78, vw - 16),
      Math.min(vw * 0.65, vw - 16),
      Math.min(vw * 0.52, vw - 16),
      Math.min(vw * 0.42, vw - 12)
    ];
    var yCoords = [vh * 0.18, vh * 0.3, vh * 0.42, vh * 0.55, vh * 0.68];
    var globalBest = null;
    var globalScore = -Infinity;

    /* vx/vy always main-viewport coords so nested iframe piercing stays consistent */
    function scoreStackElements(stack, vx, vy) {
      if (!stack || !stack.length) return;
      var ki;
      for (ki = 0; ki < Math.min(stack.length, 34); ki++) {
        var elHit = stack[ki];
        if (elHit && elHit.tagName === 'IFRAME' && elHit.contentDocument) {
          try {
            var br = elHit.getBoundingClientRect();
            var ix = vx - br.left;
            var iy = vy - br.top;
            if (ix >= 0 && iy >= 0 && ix <= br.width && iy <= br.height) {
              var inner = elHit.contentDocument.elementsFromPoint(ix, iy);
              scoreStackElements(inner, vx, vy);
            }
          } catch (eIf) {
            /* cross-origin iframe */
          }
          continue;
        }
        var pair = bestAncestorAlongChain(elHit);
        if (pair && pair.score > globalScore) {
          globalScore = pair.score;
          globalBest = pair.el;
        }
      }
    }

    for (yi = 0; yi < yCoords.length; yi++) {
      for (xi = 0; xi < xCoords.length; xi++) {
        var px = xCoords[xi];
        var py = yCoords[yi];
        var stack;
        try {
          stack = document.elementsFromPoint(px, py);
        } catch (eP) {
          continue;
        }
        scoreStackElements(stack, px, py);
      }
    }
    return globalBest;
  }

  /**
   * Full enumeration of `<main>` subtrees whose layout box sits right of the list column — no pointer hit-testing.
   * Covers cases where `elementsFromPoint` misses (overlays, shadow, split compositor quirks).
   */
  function getLinkedInGeometricRightBandPane() {
    if (!isLinkedInJobsPage() || !linkedInUrlJobId()) return null;
    var scope = document.querySelector('main');
    if (!scope) scope = document.body;
    if (!scope) return null;

    var vw = Math.max(window.innerWidth || document.documentElement.clientWidth || 800, 320);
    var jidNeedles = linkedInJobPostingNeedles(linkedInUrlJobId());
    /* ~33% vw is usually past the narrow job-card list on desktop */
    var minLeftPx = Math.max(Math.round(vw * 0.33), 200);

    var nodes;
    try {
      nodes = scope.querySelectorAll('div, section, article, aside');
    } catch (eN) {
      nodes = [];
    }

    var bestEl = null;
    var bestScore = -Infinity;
    var ni;
    var el;
    var r;
    var t;
    var blob;
    var head;

    for (ni = 0; ni < nodes.length; ni++) {
      el = nodes[ni];
      if (isInsideCompactListJobCard(el)) continue;
      if (isInsideSearchResultsRail(el)) continue;
      try {
        r = el.getBoundingClientRect();
      } catch (eR) {
        continue;
      }
      if (r.width < 150 || r.height < 64) continue;
      if (r.left < minLeftPx) continue;
      t = (el.innerText || '').trim();
      if (t.length < MIN_CANDIDATE_CHARS) continue;
      head = t.slice(0, 1700);
      if (looksLikeLinkedInHomeJobsRail(head)) continue;
      blob = (el.innerHTML || '').slice(0, 120000);
      var score = Math.min(t.length, 28000) + r.left * 0.07 + Math.min(r.width, 980) * 0.045;
      if (jidNeedles.length && blobMatchesLinkedInJobNeedles(blob, jidNeedles)) score += 520000;
      if (/About the job|Job description|Qualificat|Responsibilit|Easy Apply|Posted on|yr ·|employees ·/i.test(t))
        score += 16000;
      if (score > bestScore) {
        bestScore = score;
        bestEl = el;
      }
    }
    return bestEl;
  }

  /**
   * Climb from any link that references `currentJobId` to a large ancestor in the detail column.
   * Works when class names are fully hashed (no stable "job-details" substring).
   */
  function getLinkedInPaneFromJobIdLinks() {
    var jid = linkedInUrlJobId();
    if (!jid || !isLinkedInJobsPage()) return null;
    var jidNeedles = linkedInJobPostingNeedles(jid);
    var vw = Math.max(window.innerWidth || document.documentElement.clientWidth || 800, 320);
    var scored = [];
    try {
      document.querySelectorAll('a[href*="' + jid + '"]').forEach(function (a) {
        var linkPos;
        try {
          linkPos = a.getBoundingClientRect();
        } catch (eLink) {
          return;
        }
        /* List-column job cards use the same currentJobId in href; climbing yields <main> + feed text. */
        if (vw >= 640 && linkPos.left < vw * 0.28) {
          return;
        }
        var p = a;
        var depth = 0;
        while (p && depth < 22) {
          var t = (p.innerText || '').trim();
          var r = p.getBoundingClientRect();
          if (t.length > 420 && r.width > 110 && r.height > 70 && r.left > 120) {
            var head = t.slice(0, 1200);
            if (!looksLikeLinkedInHomeJobsRail(head)) {
              var blob = (p.innerHTML || '').slice(0, 120000);
              var score =
                Math.min(t.length, 18000) +
                Math.min(r.left, 1600) * 0.45 +
                Math.min(r.width, 1400) * 0.08;
              if (jidNeedles.length && blobMatchesLinkedInJobNeedles(blob, jidNeedles)) score += 900000;
              if (/About the job|Job description|What you|Responsibilit|Qualificat/i.test(t)) score += 12000;
              scored.push({ el: p, score: score });
            }
          }
          p = p.parentElement;
          depth++;
        }
      });
    } catch (e) {
      /* skip */
    }
    if (scored.length === 0) return null;
    scored.sort(function (a, b) {
      return b.score - a.score;
    });
    return scored[0].el;
  }

  /**
   * Walk `main` / `[role="main"]` for large right-column blocks whose opening text is not the activity rail.
   */
  function getLinkedInDomWalkDetailPane() {
    if (!isLinkedInJobsPage() || !linkedInUrlJobId()) return null;
    var jidNeedles = linkedInJobPostingNeedles(linkedInUrlJobId());
    var vw = Math.max(window.innerWidth || document.documentElement.clientWidth || 900, 600);
    var roots = [];
    try {
      if (document.querySelector('main')) roots.push(document.querySelector('main'));
      document.querySelectorAll('[role="main"]').forEach(function (n) {
        roots.push(n);
      });
    } catch (e) {
      /* skip */
    }
    var seen = [];
    var best = null;
    var bestScore = -Infinity;
    var ri;
    var root;
    var nodes;
    var ni;
    var el;
    var r;
    var t;
    var blob;
    var head;
    var score;

    for (ri = 0; ri < roots.length; ri++) {
      root = roots[ri];
      if (!root || seen.indexOf(root) !== -1) continue;
      seen.push(root);
      try {
        nodes = root.querySelectorAll('div, section, article, aside');
      } catch (e2) {
        nodes = [];
      }
      for (ni = 0; ni < nodes.length; ni++) {
        el = nodes[ni];
        if (isInsideCompactListJobCard(el)) continue;
        if (isInsideSearchResultsRail(el)) continue;
        try {
          r = el.getBoundingClientRect();
        } catch (e3) {
          continue;
        }
        if (r.width < 95 || r.height < 65) continue;
        if (r.left < (vw >= 880 ? vw * 0.33 : vw >= 640 ? vw * 0.2 : vw * 0.06)) continue;
        t = (el.innerText || '').trim();
        if (t.length < MIN_CANDIDATE_CHARS) continue;
        head = t.slice(0, 1200);
        if (looksLikeLinkedInHomeJobsRail(head)) continue;
        blob = (el.innerHTML || '').slice(0, 120000);
        score = Math.min(t.length, 20000) + r.left * 0.35 + r.width * 0.06;
        if (jidNeedles.length && blobMatchesLinkedInJobNeedles(blob, jidNeedles)) score += 900000;
        if (/About the job|Job description|Easy Apply|What you|Responsibilit/i.test(t)) score += 8000;
        if (score > bestScore) {
          bestScore = score;
          best = el;
        }
      }
    }
    return best;
  }

  /**
   * Last resort when LinkedIn renames classes: score broad detail-region selectors by width + URL job id match.
   * Avoids falling through to `<main>` (feed + "Jobs based on your activity" + promoted listings).
   */
  function getLinkedInBroadDetailFallback() {
    if (!isLinkedInJobsPage() || !linkedInUrlJobId()) return null;
    var jidNeedles = linkedInJobPostingNeedles(linkedInUrlJobId());
    var broadSelectors = [
      '[class*="scaffold-layout__detail"]',
      '[class*="jobs-search__job-details--wrapper"]',
      '[class*="jobs-search-two-pane__details"]',
      '[class*="jobs-details-serp-page__job-details"]',
      '[class*="jobs-unified-structure"]',
      '[class*="jobs-search-job-details"]',
      '[class*="jobs-details-two-column"]',
      '[class*="job-details-main"]'
    ];
    var scored = [];
    var si;
    var ni;
    var nodes;
    var el;
    var r;
    var t;
    var blob;
    var vw = Math.max(window.innerWidth || document.documentElement.clientWidth || 800, 320);

    function isLeftListOnlyRail(el) {
      if (!el || !el.closest) return false;
      if (el.closest('[class*="jobs-search__right-rail"]')) return false;
      if (el.closest('[class*="scaffold-layout__detail"]')) return false;
      if (el.closest('[class*="jobs-search__job-details"]')) return false;
      return !!el.closest('[class*="scaffold-layout__list"]');
    }

    for (si = 0; si < broadSelectors.length; si++) {
      try {
        nodes = document.querySelectorAll(broadSelectors[si]);
      } catch (e) {
        nodes = [];
      }
      for (ni = 0; ni < nodes.length; ni++) {
        el = nodes[ni];
        if (isInsideCompactListJobCard(el)) continue;
        if (isLeftListOnlyRail(el)) continue;
        try {
          r = el.getBoundingClientRect();
        } catch (e2) {
          continue;
        }
        if (r.width < 50 || r.height < 60) continue;
        try {
          var st = window.getComputedStyle(el);
          if (st.display === 'none' || st.visibility === 'hidden') continue;
        } catch (e3) {
          continue;
        }
        t = (el.innerText || '').trim();
        if (t.length < 80) continue;
        if (looksLikeLinkedInHomeJobsRail(t.slice(0, 1400))) continue;
        blob = (el.innerHTML || '') + (el.outerHTML || '').slice(0, 90000);
        var score = Math.min(t.length, 25000) + Math.min(r.left, vw) * 0.5 + Math.min(r.width, vw) * 0.15;
        if (jidNeedles.length && blobMatchesLinkedInJobNeedles(blob, jidNeedles)) score += 500000;
        scored.push({ el: el, score: score });
      }
    }
    if (scored.length === 0) return null;
    scored.sort(function (a, b) {
      return b.score - a.score;
    });
    return scored[0].el;
  }

  /**
   * The focused job's `data-job-id` is often ONLY on the left list row — the detail pane may not repeat it.
   * URN strings may also be absent from description innerHTML. What always matches the user's focus is the
   * visible description block in the split-view **detail column** (right side), not list cards or cached nodes.
   */
  function getLinkedInVisibleDetailColumnBody() {
    if (!isLinkedInJobsPage() || !linkedInUrlJobId()) return null;
    var vw = Math.max(window.innerWidth || document.documentElement.clientWidth || 800, 320);
    var selectors = [
      '.jobs-search__job-details-body',
      'article.jobs-description__container',
      '[class*="jobs-details__main-content"]',
      '[class*="job-details-body"]',
      '[class*="jobs-description-content"]',
      '[class*="jobs-box__html-content"]'
    ];
    function pickBodiesWithMinLeft(minLeftPx) {
      var best = null;
      var bestLen = 0;
      var si;
      var ni;
      var nodes;
      var el;
      var t;
      var r;
      for (si = 0; si < selectors.length; si++) {
        try {
          nodes = document.querySelectorAll(selectors[si]);
        } catch (e) {
          nodes = [];
        }
        for (ni = 0; ni < nodes.length; ni++) {
          el = nodes[ni];
          if (isInsideSearchResultsRail(el) || isInsideCompactListJobCard(el)) continue;
          if (!isElementVisiblyRendered(el)) continue;
          try {
            r = el.getBoundingClientRect();
          } catch (e2) {
            continue;
          }
          if (r.left < minLeftPx) continue;
          t = (el.innerText || '').trim();
          if (t.length < MIN_CANDIDATE_CHARS) continue;
          if (looksLikeLinkedInHomeJobsRail(t.slice(0, 1600))) continue;
          if (t.length > bestLen) {
            bestLen = t.length;
            best = el;
          }
        }
      }
      return best;
    }
    var fractions = [0.38, 0.28, 0.2, 0.14, 0.08];
    if (vw < 768) {
      fractions.push(0);
    }
    var fi;
    var picked;
    for (fi = 0; fi < fractions.length; fi++) {
      picked = pickBodiesWithMinLeft(vw * fractions[fi]);
      if (picked) return picked;
    }
    return null;
  }

  /** If an inner description node matched, upgrade to the parent wrapper when it contains substantially more text. */
  function expandLinkedInDetailRootIfRicher(innerEl) {
    if (!innerEl || !isLinkedInJobsPage()) return innerEl;
    var wrap = innerEl.closest(
      '[class*="jobs-search__job-details--wrapper"], [class*="jobs-search-two-pane__details"], [class*="jobs-details-serp-page__job-details"]'
    );
    if (!wrap || wrap === innerEl) return innerEl;
    var a = ((innerEl.innerText || '').trim()).length;
    var b = ((wrap.innerText || '').trim()).length;
    if (b >= a + 100) return wrap;
    return innerEl;
  }

  /**
   * Prefer description nodes whose subtree references the URL job id (Li URN or numeric).
   * Runs before geometry heuristics so we never pick a longer unrelated pane or another listing.
   */
  function findLinkedInDetailBodyMatchingUrlJobId() {
    var jid = linkedInUrlJobId();
    if (!jid) return null;
    var needles = linkedInJobPostingNeedles(jid);
    var selectors = [
      '.jobs-search__job-details-body',
      'article.jobs-description__container',
      '[class*="jobs-details__main-content"]',
      '[class*="job-details-body"]'
    ];
    var best = null;
    var bestLen = 0;
    var si;
    var ni;
    var nodes;
    var el;
    var t;
    var blob;
    for (si = 0; si < selectors.length; si++) {
      try {
        nodes = document.querySelectorAll(selectors[si]);
      } catch (e) {
        nodes = [];
      }
      for (ni = 0; ni < nodes.length; ni++) {
        el = nodes[ni];
        if (isInsideSearchResultsRail(el) || isInsideCompactListJobCard(el)) continue;
        blob = (el.innerHTML || '') + '\n' + (el.outerHTML || '').slice(0, 80000);
        if (!blobMatchesLinkedInJobNeedles(blob, needles)) continue;
        t = (el.innerText || '').trim();
        if (t.length < MIN_CANDIDATE_CHARS) continue;
        if (t.length > bestLen) {
          bestLen = t.length;
          best = el;
        }
      }
    }
    return best ? expandLinkedInDetailRootIfRicher(best) : null;
  }

  function getLinkedInRootMatchingUrlJobId() {
    var jid = linkedInUrlJobId();
    if (!jid || !isLinkedInJobsPage()) return null;

    var detailColSelector = [
      '[class*="jobs-search__right-rail"]',
      '[class*="scaffold-layout__detail"]',
      '[class*="jobs-split-view__detail"]',
      '[class*="jobs-search__job-details"]',
      '[class*="jobs-unified-top-card"]'
    ].join(', ');

    var candidates = [];
    try {
      document.querySelectorAll('[data-job-id="' + jid + '"]').forEach(function (n) {
        candidates.push(n);
      });
    } catch (e) {
      /* skip */
    }

    try {
      document.querySelectorAll('[data-entity-urn*="jobPosting:' + jid + '"]').forEach(function (n) {
        candidates.push(n);
      });
    } catch (e2) {
      /* skip */
    }

    var i;
    var el;
    var detail;
    var td;
    var best = null;
    var bestLen = 0;

    for (i = 0; i < candidates.length; i++) {
      el = candidates[i];
      /* Left-list rows also carry data-job-id — ignore markers that sit only in the list column. */
      if (el.closest('[class*="scaffold-layout__list"]') && !el.closest(detailColSelector)) continue;
      detail = el.closest(detailColSelector + ', article.jobs-description__container');
      if (!detail) {
        detail = el.closest('[class*="jobs-search__job-details"], [class*="jobs-unified"]');
      }
      if (!detail) continue;
      var wrapLevel = el.closest(
        '[class*="jobs-search__job-details--wrapper"], [class*="jobs-search-two-pane__details"], [class*="jobs-details-serp-page__job-details"]'
      );
      if (wrapLevel && ((wrapLevel.innerText || '').trim()).length >= MIN_CANDIDATE_CHARS) {
        detail = wrapLevel;
      } else {
        detail =
          detail.querySelector('.jobs-search__job-details-body, article.jobs-description__container') ||
          detail;
      }
      td = (detail.innerText || '').trim();
      if (td.length >= MIN_CANDIDATE_CHARS && td.length > bestLen) {
        bestLen = td.length;
        best = detail;
      }
    }
    return best;
  }

  function getBestSplitViewDetailRoot() {
    lastLinkedInRootPath = null;
    lastLinkedInDetailRootHint = '';

    if (isLinkedInJobsPage()) {
      /* Whole right-hand job pane — not only the inner description div (misses sections + skills). */
      var wrapperPane = getLinkedInVisibleJobDetailsWrapper();
      if (wrapperPane) {
        noteLinkedInRoot(wrapperPane, 'linkedIn:wrapperPane');
        return wrapperPane;
      }
      /* Visible detail column: list rows hold data-job-id; detail often does not; URNs may be missing from HTML. */
      var visibleDetail = getLinkedInVisibleDetailColumnBody();
      if (visibleDetail) {
        noteLinkedInRoot(visibleDetail, 'linkedIn:visibleDetailColumnBody');
        return visibleDetail;
      }
      /* URL wins: focused job is tied to currentJobId / urn:li:jobPosting — not max width or max length. */
      var urlMatchedBody = findLinkedInDetailBodyMatchingUrlJobId();
      if (urlMatchedBody) {
        noteLinkedInRoot(urlMatchedBody, 'linkedIn:urlUrnMatch');
        return urlMatchedBody;
      }
      var linkedInId = getLinkedInRootMatchingUrlJobId();
      if (linkedInId) {
        noteLinkedInRoot(linkedInId, 'linkedIn:dataJobIdOrEntityUrn');
        return linkedInId;
      }
      var anchored = getLinkedInAnchoredDetailRoot();
      if (anchored) {
        noteLinkedInRoot(anchored, 'linkedIn:anchoredScore');
        return anchored;
      }
      var rmFiltered = getLinkedInRightmostDetailBody(true);
      var rightmostRm = rmFiltered || getLinkedInRightmostDetailBody(false);
      if (rightmostRm) {
        noteLinkedInRoot(rightmostRm, rmFiltered ? 'linkedIn:rightmostJobIdFiltered' : 'linkedIn:rightmostUnfiltered');
        return rightmostRm;
      }
      var paneFromLinks = getLinkedInPaneFromJobIdLinks();
      if (paneFromLinks) {
        noteLinkedInRoot(paneFromLinks, 'linkedIn:paneFromJobIdLinks');
        return paneFromLinks;
      }
      var domWalkPane = getLinkedInDomWalkDetailPane();
      if (domWalkPane) {
        noteLinkedInRoot(domWalkPane, 'linkedIn:domWalkDetailPane');
        return domWalkPane;
      }
      var broadFb = getLinkedInBroadDetailFallback();
      if (broadFb) {
        noteLinkedInRoot(broadFb, 'linkedIn:broadDetailFallback');
        return broadFb;
      }
      var geometricPane = getLinkedInGeometricRightBandPane();
      if (geometricPane) {
        noteLinkedInRoot(geometricPane, 'linkedIn:geometricRightBand');
        return geometricPane;
      }
      var viewportPane = getLinkedInDetailRootFromViewportSample();
      if (viewportPane) {
        noteLinkedInRoot(viewportPane, 'linkedIn:viewportPointSample');
        return viewportPane;
      }
      noteLinkedInRoot(null, 'linkedIn:splitStrategiesMissed');
    }

    var linkedInRail = getLinkedInOpenJobPaneRoot();
    if (linkedInRail) {
      noteLinkedInRoot(linkedInRail, 'linkedIn:openJobPaneRail');
      return linkedInRail;
    }

    var selectors = [
      '.jobs-search__job-details-body',
      '.jobs-details__main-content',
      '[class*="jobs-search__job-details"]',
      '[class*="jobs-details__main"]',
      '[class*="job-details-body"]',
      'article.jobs-description__container'
    ];
    var best = null;
    var bestLen = 0;
    var i;
    var j;
    for (i = 0; i < selectors.length; i++) {
      try {
        var found = document.querySelectorAll(selectors[i]);
        for (j = 0; j < found.length; j++) {
          var el = found[j];
          if (isInsideSearchResultsRail(el)) continue;
          if (isInsideCompactListJobCard(el)) continue;
          var t = (el.innerText || '').trim();
          if (looksLikeLinkedInHomeJobsRail(t.slice(0, 1600))) continue;
          if (t.length >= MIN_CANDIDATE_CHARS && t.length > bestLen) {
            bestLen = t.length;
            best = el;
          }
        }
      } catch (e) {
        /* skip */
      }
    }
    if (best && isLinkedInJobsPage()) {
      noteLinkedInRoot(best, 'linkedIn:longestGlobDetailSelector');
    }
    return best;
  }

  function collectCandidateRoots() {
    var seen = new WeakSet();
    var list = [];

    function add(el) {
      if (!el || el.nodeType !== 1) return;
      if (isInsideSearchResultsRail(el)) return;
      if (isInsideCompactListJobCard(el)) return;
      if (seen.has(el)) return;
      seen.add(el);
      list.push(el);
    }

    add(document.querySelector('main'));
    document.querySelectorAll('[role="main"]').forEach(add);

    var genericSelectors = [
      '[class*="job-description"]',
      '[class*="job-details"]',
      '[class*="JobDescription"]',
      '[class*="posting-body"]',
      '[id*="job-description"]',
      '[data-testid*="job"]'
    ];
    genericSelectors.forEach(function (sel) {
      try {
        document.querySelectorAll(sel).forEach(add);
      } catch (e) {
        /* skip */
      }
    });

    document.querySelectorAll('article').forEach(function (a) {
      var t = (a.innerText || '').trim();
      if (t.length >= MIN_CANDIDATE_CHARS && !isInsideCompactListJobCard(a)) add(a);
    });

    addHostnameHints(window.location.hostname, window.location.pathname, add);
    addSiteConnectorRoots(window.location.hostname || '', add);

    return list;
  }

  function scoreRoot(el, text) {
    var lower = text.toLowerCase();
    var s = 0;
    s += Math.min(text.length, 40000) * 0.002;
    var k;
    for (k = 0; k < JOB_KEYWORDS.length; k++) {
      if (lower.indexOf(JOB_KEYWORDS[k]) !== -1) s += 40;
    }
    var pCount = el.querySelectorAll('p').length;
    s += Math.min(pCount, 40) * 8;

    var lines = text.split('\n').map(function (l) {
      return l.trim();
    }).filter(Boolean);
    if (lines.length > 8) {
      var shortLines = lines.filter(function (l) {
        return l.length < 55;
      }).length;
      var ratio = shortLines / lines.length;
      if (ratio > 0.82) s -= 400;
    }

    return s;
  }

  function pickBestContentRoot() {
    var splitDetail = getBestSplitViewDetailRoot();
    if (splitDetail) {
      return splitDetail;
    }

    var candidates = collectCandidateRoots();
    var best = null;
    var bestScore = -Infinity;
    var i;
    for (i = 0; i < candidates.length; i++) {
      var el = candidates[i];
      var text = (el.innerText || '').trim();
      if (text.length < MIN_CANDIDATE_CHARS) continue;
      var sc = scoreRoot(el, text);
      if (el.tagName === 'MAIN' && document.querySelector('[class*="jobs-search-results"]')) {
        sc -= 300;
      }
      if (
        el.tagName === 'MAIN' &&
        isLinkedInJobsPage() &&
        linkedInUrlJobId() &&
        document.querySelector(
          '[class*="jobs-search-two-pane"], [class*="jobs-split-view"], [class*="scaffold-layout__list-container"]'
        )
      ) {
        sc -= 900;
      }
      if (sc > bestScore) {
        bestScore = sc;
        best = el;
      }
    }
    var pickedRoot = best || document.body;
    if (isLinkedInJobsPage() && linkedInUrlJobId()) {
      var rescuePane =
        getLinkedInGeometricRightBandPane() ||
        getLinkedInDetailRootFromViewportSample() ||
        getLinkedInPaneFromJobIdLinks() ||
        getLinkedInDomWalkDetailPane() ||
        getLinkedInBroadDetailFallback();
      if (
        rescuePane &&
        (pickedRoot.tagName === 'MAIN' ||
          pickedRoot === document.body ||
          pickedRoot === document.documentElement)
      ) {
        noteLinkedInRoot(rescuePane, 'linkedIn:rescueFromMainComposite');
        return rescuePane;
      }
    }
    if (isLinkedInJobsPage()) {
      noteLinkedInRoot(pickedRoot, 'linkedIn:candidateScore_' + (pickedRoot.tagName || '?'));
    }
    return pickedRoot;
  }

  function removeSplitViewListRails(node) {
    try {
      node.querySelectorAll('[class*="jobs-search-results"]').forEach(function (el) {
        el.remove();
      });
      node.querySelectorAll('[class*="scaffold-layout__list"]').forEach(function (el) {
        el.remove();
      });
      node.querySelectorAll('[class*="search-results__list"]').forEach(function (el) {
        el.remove();
      });
      node.querySelectorAll('[class*="job-card-list"]').forEach(function (el) {
        el.remove();
      });
      node.querySelectorAll('[class*="reusable-search__result-container"]').forEach(function (el) {
        el.remove();
      });
      node.querySelectorAll('[class*="job-card-container"]').forEach(function (el) {
        if (el.closest('[class*="jobs-search__right-rail"]')) return;
        if (el.closest('[class*="jobs-search__job-details--wrapper"]')) return;
        if (el.closest('[class*="jobs-unified-top-card"]')) return;
        if (el.closest('[class*="jobs-unified"]')) return;
        el.remove();
      });
    } catch (e) {
      /* skip */
    }
    return node;
  }

  var REMOVE_SELECTORS = [
    'script',
    'style',
    'noscript',
    'iframe',
    'svg',
    'canvas',
    'template',
    'link',
    'meta',
    'code',
    'pre',
    '[type="application/json"]',
    '[type="application/ld+json"]',
    'header',
    'footer',
    'nav',
    'aside',
    '[role="navigation"]',
    '[role="banner"]',
    '[role="contentinfo"]',
    '[role="complementary"]',
    '[aria-hidden="true"]',
    '[hidden]',
    '.hidden',
    '.visually-hidden',
    '[style*="display: none"]',
    '[style*="display:none"]',
    '.cookie-banner',
    '.cookie-consent',
    '[class*="cookie"]',
    '.popup',
    '.modal',
    '.overlay',
    '.dialog',
    '[role="dialog"]',
    '.advertisement',
    '.ad-container',
    '[class*="advert"]',
    '[id*="google_ads"]',
    '[class*="sponsored"]',
    '[class*="promo"]',
    '.social-share',
    '.share-buttons',
    '.comments',
    '.comment-section',
    '[class*="chat-widget"]',
    '[class*="intercom"]',
    '[class*="drift"]',
    '[class*="zendesk"]'
  ];

  function cleanText(raw) {
    var text = raw
      .replace(/\t/g, ' ')
      .replace(/[ ]{2,}/g, ' ')
      .replace(/\n{3,}/g, '\n\n')
      .replace(/^\s+$/gm, '')
      .trim();

    text = text.replace(/\s*\(Verified job\)\s*/gi, ' ');
    text = text.replace(/\s*\(Promoted\)\s*/gi, ' ');

    text = text
      .split('\n')
      .filter(function (line) {
        var trimmed = line.trim();
        if (trimmed.startsWith('{') && trimmed.indexOf('"$type"') !== -1) return false;
        if (trimmed.startsWith('[') && trimmed.indexOf('"$type"') !== -1) return false;
        if (trimmed.indexOf('urn:li:') !== -1) return false;
        if (trimmed.indexOf('entityUrn') !== -1) return false;
        if (trimmed.indexOf('chameleon') !== -1) return false;
        if (trimmed.indexOf('lixTracking') !== -1) return false;
        if (trimmed.length > 500 && trimmed.indexOf(' ') === -1) return false;
        return true;
      })
      .join('\n');

    return text.trim();
  }

  function removeUnwantedElements(node) {
    REMOVE_SELECTORS.forEach(function (selector) {
      try {
        node.querySelectorAll(selector).forEach(function (el) {
          el.remove();
        });
      } catch (e) {
        /* skip */
      }
    });
    try {
      node.querySelectorAll('[data-entity-hovercard-id]').forEach(function (el) {
        el.remove();
      });
      node.querySelectorAll('[data-tracking-control-name]').forEach(function (el) {
        el.remove();
      });
    } catch (e2) {
      /* skip */
    }
    return node;
  }

  /**
   * Heuristic for popup UX (tips when extraction may be noisy). Not used server-side.
   */
  function computeExtractionConfidence(content, source) {
    var c = content || '';
    var len = c.length;
    var lines = c.split(/\r?\n/).map(function (l) {
      return l.trim();
    }).filter(Boolean).length;
    if (source === 'ashby-api') {
      if (len >= 800 && lines >= 10) return 'high';
      if (len < 400) return 'low';
      return 'medium';
    }
    if (source === 'linkedin-guest-api') {
      if (len < 350) return 'low';
      /* Guest HTML is job-scoped (currentJobId) and rail-filtered before this source is set. */
      /* Dense JDs often have few newlines — do not require lines >= 8 when text is already long. */
      if (len >= 1000 || (len >= 700 && lines >= 8)) return 'high';
      return 'medium';
    }
    if (source === 'selection') return 'high';
    if (!c) return 'low';
    if (source === 'json-ld' || source === 'json-ld+dom') {
      if (len >= 550 && lines >= 8) return 'high';
      if (len < 320) return 'low';
      return lines >= 5 ? 'medium' : 'low';
    }
    if (len >= 2800 && lines >= 14) return 'high';
    if (len < 380) return 'low';
    if (lines < 5 && len < 2200) return 'low';
    if (source === 'dom' && len < 1100) return 'medium';
    return 'medium';
  }

  function finalizeExtractResult(result) {
    if (result && isLinkedInJobsPage() && linkedInUrlJobId()) {
      result = applyLinkedInMetaEnrichment(result, getLinkedInLiveTopCardMetadataText());
    }
    result.confidence = computeExtractionConfidence(result.content, result.source);
    return result;
  }

  /** Ashby embed pages (e.g. marketing site + `?ashby_jid=`) load listing via script; DOM is mostly chrome. */
  function getAshbyJidFromSearchParams() {
    try {
      var u = new URL(window.location.href);
      var jid = (u.searchParams.get('ashby_jid') || '').trim();
      if (!/^[0-9a-f-]{36}$/i.test(jid)) return '';
      return jid.toLowerCase();
    } catch (e) {
      return '';
    }
  }

  /** `<script src="https://jobs.ashbyhq.com/{slug}/embed">` */
  function detectAshbyEmbedBoardSlugFromDom() {
    var scripts = document.querySelectorAll('script[src*="ashbyhq.com"]');
    var i;
    var src;
    var m;
    for (i = 0; i < scripts.length; i++) {
      src = scripts[i].getAttribute('src') || '';
      m = src.match(/jobs\.ashbyhq\.com\/([^/?#]+)\/embed/i);
      if (m && m[1]) return m[1];
    }
    return '';
  }

  function ashbyBoardSlugFallbackForHostname(host) {
    var h = (host || '').toLowerCase();
    if (/^(www\.)?clay\.com$/i.test(h)) return 'claylabs';
    return '';
  }

  function formatAshbyPublicJobPlain(job) {
    if (!job || typeof job !== 'object') return '';
    var lines = [];
    if (job.title) lines.push(String(job.title).trim());
    if (job.team) lines.push('Team: ' + String(job.team).trim());
    if (job.department) lines.push('Department: ' + String(job.department).trim());
    if (job.location) lines.push('Location: ' + String(job.location).trim());
    if (job.workplaceType) lines.push('Workplace: ' + String(job.workplaceType));
    if (job.employmentType) lines.push('Employment: ' + String(job.employmentType));
    var desc = job.descriptionPlain;
    if (desc) {
      lines.push('');
      lines.push(String(desc).trim());
    } else if (job.descriptionHtml) {
      lines.push('');
      lines.push(htmlToPlainText(String(job.descriptionHtml)));
    }
    return lines.join('\n').trim();
  }

  /**
   * Fetches the public Ashby job board JSON and returns the posting matching `ashby_jid` in the URL.
   * Requires manifest host permission `https://api.ashbyhq.com/*`.
   */
  async function tryAshbyPublicPostingFromEmbedPage() {
    var jid = getAshbyJidFromSearchParams();
    if (!jid) return '';
    var slug = detectAshbyEmbedBoardSlugFromDom() || ashbyBoardSlugFallbackForHostname(window.location.hostname || '');
    if (!slug) return '';
    var apiUrl = 'https://api.ashbyhq.com/posting-api/job-board/' + encodeURIComponent(slug);
    try {
      var res = await fetch(apiUrl, { credentials: 'omit', cache: 'no-store' });
      if (!res.ok) return '';
      var data = await res.json();
      var jobs = data && data.jobs;
      if (!Array.isArray(jobs)) return '';
      var i;
      var id;
      for (i = 0; i < jobs.length; i++) {
        id = jobs[i] && jobs[i].id;
        if (id && String(id).toLowerCase() === jid) return formatAshbyPublicJobPlain(jobs[i]);
      }
    } catch (e) {
      /* network / parse — fall back to DOM */
    }
    return '';
  }

  function extractPageContent() {
    var result = { content: '', title: document.title || '', source: 'dom' };

    var selection = window.getSelection().toString().trim();
    if (selection.length >= MIN_SELECTION_CHARS) {
      result.content = capContent(cleanText(selection));
      result.source = 'selection';
      return finalizeExtractResult(result);
    }

    if (isLinkedInJobsPage() && linkedInUrlJobId()) {
      var liVoyager = tryLinkedInVoyagerSessionStorage();
      if (
        liVoyager &&
        liVoyager.length >= MIN_CANDIDATE_CHARS &&
        !looksLikeLinkedInHomeJobsRail(liVoyager.slice(0, 1700))
      ) {
        noteLinkedInRoot(null, 'linkedIn:voyagerSessionStorage');
        result.content = maybeAppendMetaDescription(capContent(cleanText(liVoyager)));
        result.source = 'dom';
        return finalizeExtractResult(result);
      }

      var liStructured = tryLinkedInJobsSearchCompositeText();
      var liHead = liStructured ? liStructured.slice(0, 1700) : '';
      if (
        liStructured &&
        liStructured.length >= MIN_CANDIDATE_CHARS &&
        !looksLikeLinkedInHomeJobsRail(liHead)
      ) {
        var diagEl =
          document.querySelector(
            '.jobs-description-content__text, .jobs-box__html-content, article.jobs-description__container'
          ) || document.querySelector('[class*="jobs-description-content"]');
        noteLinkedInRoot(diagEl || document.querySelector('main'), 'linkedIn:structuredSelectors');
        result.content = maybeAppendMetaDescription(capContent(cleanText(liStructured)));
        result.source = 'dom';
        return finalizeExtractResult(result);
      }
    }

    var ldText = shouldSkipJsonLdForLinkedInJobs() ? '' : extractJobPostingFromJsonLd();
    var domText = buildDomExtractedText();

    if (ldText.length >= MIN_JSON_LD_CHARS) {
      if (isDomSupersetOfLd(ldText, domText) && domText.length >= ldText.length) {
        result.content = maybeAppendMetaDescription(domText);
        result.source = 'dom';
        return finalizeExtractResult(result);
      }
      result.content = maybeAppendMetaDescription(capContent(ldText));
      result.source = 'json-ld';
      return finalizeExtractResult(result);
    }

    if (ldText.length >= 40) {
      if (domText.length < 80) {
        result.content = maybeAppendMetaDescription(capContent(ldText));
        result.source = 'json-ld';
        return finalizeExtractResult(result);
      }
      if (isDomSupersetOfLd(ldText, domText)) {
        result.content = maybeAppendMetaDescription(domText);
        result.source = 'dom';
        return finalizeExtractResult(result);
      }
      result.content = maybeAppendMetaDescription(capContent(ldText + '\n\n---\n\n' + domText));
      result.source = 'json-ld+dom';
      return finalizeExtractResult(result);
    }

    result.content = maybeAppendMetaDescription(domText);
    result.source = 'dom';
    return finalizeExtractResult(result);
  }

  /**
   * SPA / lazy panels: run twice after a delay and keep the richer extraction.
   * Ashby embed on third-party sites: resolve full description via public posting API.
   */
  window.__jaaExtractPageContentAsync = async function () {
    var ashbyApiText = await tryAshbyPublicPostingFromEmbedPage();

    if (isLinkedInJobsPage() && linkedInUrlJobId()) {
      var guestTxt = await tryLinkedInGuestApiJobPostingText();
      if (
        guestTxt &&
        guestTxt.length >= MIN_CANDIDATE_CHARS &&
        !looksLikeLinkedInHomeJobsRail(guestTxt.slice(0, 1800))
      ) {
        noteLinkedInRoot(null, 'linkedIn:guestJobPostingApi');
        return attachExtractDiagnostics(
          finalizeExtractResult({
            content: maybeAppendMetaDescription(capContent(cleanText(guestTxt))),
            title: document.title || '',
            source: 'linkedin-guest-api'
          })
        );
      }
    }

    /* SPA + network: DOM selectors often miss; Voyager JSON lands on fetch/XHR — poll both */
    if (isLinkedInJobsPage() && linkedInUrlJobId()) {
      var pollDeadline = Date.now() + 8000;
      while (Date.now() < pollDeadline) {
        var vz = tryLinkedInVoyagerSessionStorage();
        if (
          vz &&
          vz.length >= MIN_CANDIDATE_CHARS &&
          !looksLikeLinkedInHomeJobsRail(vz.slice(0, 1700))
        ) {
          break;
        }
        var trial = tryLinkedInJobsSearchCompositeText();
        if (
          trial &&
          trial.length >= MIN_CANDIDATE_CHARS &&
          !looksLikeLinkedInHomeJobsRail(trial.slice(0, 1700))
        ) {
          break;
        }
        await new Promise(function (r) {
          setTimeout(r, 200);
        });
      }
    }

    var first = extractPageContent();
    if (first && first.source === 'selection' && (first.content || '').length >= MIN_SELECTION_CHARS) {
      return attachExtractDiagnostics(first);
    }

    await new Promise(function (resolve) {
      setTimeout(resolve, 500);
    });
    var second = extractPageContent();
    if (second && second.source === 'selection' && (second.content || '').length >= MIN_SELECTION_CHARS) {
      return attachExtractDiagnostics(second);
    }

    var a = (first && first.content) || '';
    var b = (second && second.content) || '';
    var domBest = b.length > a.length + 120 ? second : first;

    if (ashbyApiText && ashbyApiText.length > (domBest.content || '').length + 50) {
      return attachExtractDiagnostics(
        finalizeExtractResult({
          content: capContent(cleanText(ashbyApiText)),
          title: document.title || '',
          source: 'ashby-api'
        })
      );
    }
    return attachExtractDiagnostics(await enrichExtractResultWithLinkedInMeta(domBest));
  };

  window.__jaaPeekLinkedInExtractDebug = function () {
    return { linkedInRootPath: lastLinkedInRootPath, linkedInRootHint: lastLinkedInDetailRootHint };
  };

  window.__jaaExtractPageContent = extractPageContent;
})();
