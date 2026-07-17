/**
 * Runs in the page MAIN world (see manifest content_scripts.world).
 * LinkedIn job search loads posting JSON via fetch/XHR; DOM `<main>` is often feed noise.
 * Persists parsed posting text in sessionStorage — readable from the isolated extractor.
 */
(function installRoleMuleLiNetworkHook() {
  'use strict';

  try {
    if (window.__roleMuleLiVoyagerHook) return;
    window.__roleMuleLiVoyagerHook = true;
  } catch (e0) {
    return;
  }

  var PREFIX = 'jaa_li_vp_';

  function currentJobIdFromUrl() {
    try {
      var id = new URL(location.href).searchParams.get('currentJobId');
      if (id && /^\d+$/.test(id)) return id;
    } catch (e) {
      /* ignore */
    }
    return '';
  }

  function stripJsonpNoise(s) {
    var t = String(s || '').trim();
    if (t.indexOf('while(1);') === 0) t = t.replace(/^while\(1\);/, '').trim();
    if (t.indexOf('for (;;);') === 0) t = t.replace(/^for\s*\(\s*;\s*;\s*\)\s*;/, '').trim();
    return t;
  }

  function parseJsonLenient(txt) {
    var t = stripJsonpNoise(txt);
    var data = tryParse(t);
    if (data) return data;
    /* LinkedIn sometimes returns huge payloads with leading bytes */
    var i = t.indexOf('{');
    while (i !== -1) {
      data = tryParse(t.slice(i));
      if (data) return data;
      i = t.indexOf('{', i + 1);
    }
    return null;
  }

  function tryParse(s) {
    try {
      return JSON.parse(s);
    } catch (e) {
      return null;
    }
  }

  function longestJobLikeString(obj) {
    var best = '';
    function walk(x, depth, keyHint) {
      if (!x || depth > 52) return;
      if (typeof x === 'string') {
        if (x.length <= best.length || x.length < 160) return;
        if (x.indexOf('urn:li:') !== -1 && x.length < 500) return;
        if (/\$type|"com\.linkedin/.test(x) && x.length < 600) return;
        var words = x.split(/\s+/).length;
        if (words < 12) return;
        best = x;
        return;
      }
      if (typeof x !== 'object') return;
      var k;
      for (k in x) {
        if (!Object.prototype.hasOwnProperty.call(x, k)) continue;
        var kl = k.toLowerCase();
        var prefer =
          /descrip|snippet|formatted|standardized|jobposting|sanitized|richtext/i.test(kl) ? 4000 : 0;
        walk(x[k], depth + 1, k);
        /* Prefer long strings under description-like keys */
        if (prefer && typeof x[k] === 'string') {
          var v = x[k];
          if (v.length > best.length && v.length >= 160 && v.split(/\s+/).length >= 12) best = v;
        }
      }
    }
    walk(obj, 0, '');
    return best;
  }

  function pickShortField(obj, reKey) {
    var found = '';
    function walk(x, depth) {
      if (!x || depth > 44 || found) return;
      if (typeof x === 'object') {
        var k;
        for (k in x) {
          if (!Object.prototype.hasOwnProperty.call(x, k)) continue;
          if (reKey.test(k) && typeof x[k] === 'string') {
            var s = x[k].trim();
            if (s && s.length > 2 && s.length < 320) {
              found = s;
              return;
            }
          }
          walk(x[k], depth + 1);
        }
      }
    }
    walk(obj, 0);
    return found;
  }

  function extractPack(data, jobId) {
    var blob = '';
    try {
      blob = JSON.stringify(data);
    } catch (e) {
      return null;
    }
    if (!jobId || blob.length < 80) return null;
    if (blob.indexOf(jobId) === -1) return null;

    var desc = longestJobLikeString(data);
    if (!desc || desc.length < 100) return null;

    var title =
      pickShortField(data, /^(title|jobTitle|jobPostingTitle|formattedTitle)$/i) ||
      pickShortField(data, /JobTitle$/i) ||
      '';
    var company =
      pickShortField(data, /^(companyName|universalName|displayName|companyNameWithId)$/i) ||
      pickShortField(data, /CompanyName$/i) ||
      '';

    return { title: title, company: company, desc: desc };
  }

  function resolveJobIdForPayload(txt, data) {
    var jidUrl = currentJobIdFromUrl();
    var blob = '';
    try {
      blob = typeof data === 'object' ? JSON.stringify(data) : txt;
    } catch (e2) {
      blob = txt;
    }

    if (jidUrl && blob.indexOf(jidUrl) !== -1) return jidUrl;

    var m = txt.match(/jobPosting[:\s]*(\d{6,22})/);
    if (m && m[1]) return m[1];

    var re = /"(\d{6,22})"/g;
    var match;
    var candidates = {};
    while ((match = re.exec(txt)) !== null) {
      candidates[match[1]] = true;
    }
    if (jidUrl && candidates[jidUrl]) return jidUrl;

    var keys = Object.keys(candidates);
    if (keys.length === 1) return keys[0];
    return jidUrl || '';
  }

  function persistFromJsonText(txt) {
    if (!txt || txt.length < 120) return;

    var data = parseJsonLenient(txt);
    if (!data) return;

    var jobId = resolveJobIdForPayload(txt, data);
    if (!jobId) return;

    var pack = extractPack(data, jobId);
    if (!pack || !pack.desc) return;

    try {
      sessionStorage.setItem(
        PREFIX + jobId,
        JSON.stringify({
          title: pack.title,
          company: pack.company,
          desc: pack.desc,
          ts: Date.now()
        })
      );
    } catch (se) {
      /* quota / private mode */
    }
  }

  function maybeHandleBody(txt) {
    if (!txt || txt.length < 120) return;

    var jidUrl = currentJobIdFromUrl();
    var looksJobish =
      /jobPosting|JobPosting|jobDescription|description\.text|standardizedDescription|included|graphql/i.test(
        txt
      );
    var mentionsFocusJob = jidUrl ? txt.indexOf(jidUrl) !== -1 : false;

    if (!looksJobish && !mentionsFocusJob) return;

    persistFromJsonText(txt);
  }

  /* fetch */
  var origFetch = window.fetch;
  if (typeof origFetch === 'function') {
    window.fetch = function () {
      return origFetch.apply(this, arguments).then(function (res) {
        try {
          var clone = res.clone();
          clone
            .text()
            .then(function (t) {
              maybeHandleBody(t);
            })
            .catch(function () {
              /* ignore */
            });
        } catch (e1) {
          /* ignore */
        }
        return res;
      });
    };
  }

  /* XHR */
  var XHR = XMLHttpRequest.prototype;
  var origSend = XHR.send;
  XHR.send = function () {
    this.addEventListener('load', function () {
      try {
        var txt = this.responseText;
        maybeHandleBody(txt);
      } catch (e2) {
        /* ignore */
      }
    });
    return origSend.apply(this, arguments);
  };
})();
