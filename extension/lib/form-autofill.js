/**
 * ApplyPilot — serialize visible form fields and apply autofill assignments (main document MVP).
 * Injected into the active tab via chrome.scripting.executeScript; exposes globals on window.
 */
(function () {
  'use strict';

  var MAX_FIELDS = 80;
  var SKIP_INPUT_TYPES = {
    button: true,
    submit: true,
    reset: true,
    image: true,
    password: true
  };

  var RESUME_LABEL_RE = /\b(resume|cv|curriculum\s*vitae)\b/i;
  var RESUME_SECTION_RE = /resume\s*\/?\s*cv|resume\/cv/i;
  var COVER_LABEL_RE = /\b(cover\s*letter)\b/i;
  var SUPPLEMENTAL_FILE_RE =
    /\b(upload\s+anything|side\s+projects?|fun\s+facts|recent\s+poetry|references|past\s+work|optional\s+upload|additional\s+materials?)\b/i;
  var VISA_SPONSORSHIP_LABEL_RE =
    /require.*(visa|employment).*sponsorship|visa\s+sponsorship|h[- ]?1b\s+sponsorship|need\s+(visa|employment)\s+sponsorship|sponsor you for an employment visa|sponsor\b[^\n]{0,80}employment\s+visa|(?:require|need)\b[^\n]{0,160}\bsponsor\b[^\n]{0,100}\bvisa\b|require\s+sponsorship|sponsorship\s+to\s+work|(?:now|future)[^\n]{0,48}require\s+sponsorship/i;
  var LOCATION_CITY_LABEL_RE =
    /location\s*\(\s*city|^location\s*\*?\s*$|current\s+(city|location)|your\s+(city|location)|where (are you|do you) (located|live|based)/i;
  /** US state abbreviations → full name (Greenhouse geocode options use full names). */
  var US_STATE_ABBR_TO_NAME = {
    al: 'Alabama',
    ak: 'Alaska',
    az: 'Arizona',
    ar: 'Arkansas',
    ca: 'California',
    co: 'Colorado',
    ct: 'Connecticut',
    de: 'Delaware',
    dc: 'District of Columbia',
    fl: 'Florida',
    ga: 'Georgia',
    hi: 'Hawaii',
    id: 'Idaho',
    il: 'Illinois',
    in: 'Indiana',
    ia: 'Iowa',
    ks: 'Kansas',
    ky: 'Kentucky',
    la: 'Louisiana',
    me: 'Maine',
    md: 'Maryland',
    ma: 'Massachusetts',
    mi: 'Michigan',
    mn: 'Minnesota',
    ms: 'Mississippi',
    mo: 'Missouri',
    mt: 'Montana',
    ne: 'Nebraska',
    nv: 'Nevada',
    nh: 'New Hampshire',
    nj: 'New Jersey',
    nm: 'New Mexico',
    ny: 'New York',
    nc: 'North Carolina',
    nd: 'North Dakota',
    oh: 'Ohio',
    ok: 'Oklahoma',
    or: 'Oregon',
    pa: 'Pennsylvania',
    ri: 'Rhode Island',
    sc: 'South Carolina',
    sd: 'South Dakota',
    tn: 'Tennessee',
    tx: 'Texas',
    ut: 'Utah',
    vt: 'Vermont',
    va: 'Virginia',
    wa: 'Washington',
    wv: 'West Virginia',
    wi: 'Wisconsin',
    wy: 'Wyoming'
  };
  var ASHBY_HOST_RE = /(?:^|\.)ashbyhq\.com$|^jobs\.ashby$/i;
  var GREENHOUSE_HOST_RE = /(?:^|\.)greenhouse\.io$/i;
  var ASHBY_RESUME_AUTOFILL_RE = /autofill\s+from\s+resume/i;
  var ASHBY_AUTOFILL_DONE_RE = /autofill\s+completed/i;
  var EEO_CHECKBOX_RE =
    /\b(eeo|equal employment|veteran|disability|race|ethnicity|gender identity|demographic|self[- ]?identify)\b/i;
  var CONSENT_CHECKBOX_RE =
    /by checking this box|i agree to allow|store and process my data|retain my data|processing my (personal )?data|data for the purpose|future opportunities for employment|privacy (policy|notice)|consent to (the )?(processing|storage|collection)|acknowledge.*agree|confirm.*agree|agree to the following/i;
  var MARKETING_OPT_IN_RE =
    /\b(newsletter|marketing emails?|promotional offers?|send me (job )?alerts)\b/i;
  var PLACEHOLDER_LABEL_RE = /^(start typing|select\.\.\.|select\.|search\.\.\.|choose|type to search)/i;

  function visible(el) {
    if (!(el instanceof HTMLElement)) return false;
    if (el.disabled) return false;
    var st = window.getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden' || Number(st.opacity) === 0) return false;
    var r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }

  /** Ashby and similar ATS hide native radios but keep them in a visible question block. */
  function visibleForSerialize(el) {
    if (visible(el)) return true;
    if (!(el instanceof HTMLElement)) return false;
    var tag = el.tagName.toLowerCase();
    var inputType = (el.type || '').toLowerCase();
    if (tag === 'input' && inputType === 'radio') {
      var block = el.closest(
        'fieldset, [role="group"], [role="radiogroup"], [class*="field"], [class*="Field"], [class*="question"], [class*="Question"], [class*="application"]'
      );
      if (block instanceof HTMLElement && visible(block)) return true;
    }
    if (tag === 'input' && inputType === 'file' && isResumeFileInput(el)) {
      var resumeBlock = el.closest(
        'fieldset, [class*="field"], [class*="Field"], [class*="question"], [class*="application"], form, main'
      );
      if (resumeBlock instanceof HTMLElement && visible(resumeBlock)) return true;
    }
    return false;
  }

  /** Greenhouse and similar ATS use react-select style comboboxes (text input + listbox). */
  function isComboboxInput(el) {
    if (!(el instanceof HTMLElement)) return false;
    if (el.getAttribute('role') === 'combobox') return true;
    if (el.getAttribute('aria-haspopup') === 'listbox') return true;
    if (el.getAttribute('aria-autocomplete') === 'list') return true;
    var parent = el.closest(
      '[class*="select__"], [class*="Select__"], [class*="select-control"], [class*="Select-control"], [class*="combobox"], [class*="Combobox"]'
    );
    return !!parent;
  }

  function labelTextFor(el) {
    var parts = [];
    try {
      if (el.labels && el.labels.length) {
        for (var i = 0; i < el.labels.length; i++) {
          var t = (el.labels[i].innerText || '').replace(/\s+/g, ' ').trim();
          if (t) parts.push(t);
        }
      }
    } catch (e) {
      /* ignore */
    }
    if (el.getAttribute('aria-label')) {
      parts.push(String(el.getAttribute('aria-label')).trim());
    }
    if (el.getAttribute('placeholder')) {
      parts.push(String(el.getAttribute('placeholder')).trim());
    }
    var joined = parts.filter(Boolean).join(' — ');
    if (joined.length > 600) joined = joined.slice(0, 597) + '…';
    return joined;
  }

  function containerText(container, maxLen) {
    if (!(container instanceof HTMLElement)) return '';
    var t = (container.innerText || container.textContent || '').replace(/\s+/g, ' ').trim();
    if (maxLen && t.length > maxLen) t = t.slice(0, maxLen);
    return t;
  }

  function isAshbyHost() {
    try {
      return ASHBY_HOST_RE.test(String(location.hostname || ''));
    } catch (eHost) {
      return false;
    }
  }

  /** Step-by-step notes for console `scan debug` (cleared each serialize). */
  var scanDebugTraceLog = [];

  function resetScanDebugTrace() {
    scanDebugTraceLog = [];
  }

  function recordScanDebugTrace(step, detail) {
    try {
      scanDebugTraceLog.push({
        step: String(step || ''),
        detail: detail == null ? null : detail
      });
    } catch (eDbg) {
      /* ignore */
    }
  }

  /**
   * DOM probe after serialize — explains missing Ashby Yes/No (e.g. sponsorship).
   * @param {Array} fields
   * @returns {object}
   */
  function collectScanDebugReport(fields) {
    var report = {
      ashby_host: isAshbyHost(),
      page_host: String(location.hostname || ''),
      field_count: fields ? fields.length : 0,
      sponsorship_in_fields: fields ? fieldsIncludeVisaSponsorshipQuestion(fields) : false,
      yes_no_field_labels: [],
      minimal_pair_containers: [],
      yes_no_clickables_sample: [],
      sponsorship_text_hits: [],
      radiogroup_summary: [],
      trace: scanDebugTraceLog.slice(0, 50)
    };
    if (fields) {
      for (var fi = 0; fi < fields.length; fi++) {
        var f = fields[fi];
        if (!f || f.input_type !== 'yes_no_buttons') continue;
        report.yes_no_field_labels.push(String(f.label_text || '').slice(0, 140));
      }
    }
    try {
      var containers = enumerateMinimalYesNoContainers();
      for (var ci = 0; ci < containers.length && ci < 12; ci++) {
        var c = containers[ci];
        report.minimal_pair_containers.push({
          label: labelFromYesNoBlock(c, containerText(c, 500)).slice(0, 140),
          yes_no_count: yesNoChoiceCount(c),
          has_pair: !!getYesNoPair(c)
        });
      }
    } catch (eMin) {
      report.minimal_pair_containers = [{ error: String(eMin && eMin.message ? eMin.message : eMin) }];
    }
    try {
      var clickables = document.querySelectorAll(
        'button, [role="button"], [role="radio"], input[type="radio"], label'
      );
      for (var bi = 0; bi < clickables.length && report.yes_no_clickables_sample.length < 16; bi++) {
        var b = clickables[bi];
        if (!visible(b)) continue;
        var yn = normalizeYesNoChoiceText(b);
        if (!yn) continue;
        var pairParent = containerForYesNoPair(b);
        report.yes_no_clickables_sample.push({
          yn: yn,
          tag: (b.tagName || '').toLowerCase(),
          role: b.getAttribute('role') || '',
          pair_parent: pairParent ? 'yes' : 'no',
          parent_yn_count: pairParent ? yesNoChoiceCount(pairParent) : -1
        });
      }
    } catch (eClick) {
      report.yes_no_clickables_sample = [{ error: String(eClick && eClick.message ? eClick.message : eClick) }];
    }
    try {
      var textNodes = document.querySelectorAll(
        'label, legend, p, span, h3, h4, h5, [class*="question"], [class*="field"]'
      );
      for (var ti = 0; ti < textNodes.length && report.sponsorship_text_hits.length < 8; ti++) {
        var el = textNodes[ti];
        if (!(el instanceof HTMLElement) || !visible(el)) continue;
        var txt = normalizeBtnText(el);
        if (txt.length < 12 || txt.length > 320 || txt.indexOf('?') < 0) continue;
        if (!textLooksLikeSponsorshipScreening(txt)) continue;
        var hit = { text: txt.slice(0, 140), block_has_controls: false, tight_block: false };
        var walk = el;
        for (var d = 0; d < 12 && walk; d++) {
          if (blockHasYesNoControls(walk)) {
            hit.block_has_controls = true;
            hit.tight_block = !!findTightestYesNoControlBlock(walk);
            break;
          }
          walk = walk.parentElement;
        }
        report.sponsorship_text_hits.push(hit);
      }
    } catch (eText) {
      report.sponsorship_text_hits = [{ error: String(eText && eText.message ? eText.message : eText) }];
    }
    try {
      var groups = document.querySelectorAll('[role="radiogroup"]');
      for (var gi = 0; gi < groups.length && gi < 10; gi++) {
        var g = groups[gi];
        if (!(g instanceof HTMLElement) || !visible(g)) continue;
        report.radiogroup_summary.push({
          yn_count: yesNoChoiceCount(g),
          radio_children: g.querySelectorAll('[role="radio"], input[type="radio"]').length,
          text: containerText(g, 200).slice(0, 120)
        });
      }
    } catch (eGrp) {
      report.radiogroup_summary = [{ error: String(eGrp && eGrp.message ? eGrp.message : eGrp) }];
    }
    return report;
  }

  function isGreenhouseHost() {
    try {
      return GREENHOUSE_HOST_RE.test(String(location.hostname || ''));
    } catch (eGh) {
      return false;
    }
  }

  /** Ashby/Greenhouse lazy-mount sections; deep scroll can break other ATS (e.g. Lever). */
  function needsDeepScrollSerialize() {
    return isAshbyHost() || isGreenhouseHost();
  }

  function ashbyFieldBlockHasApplicationInputs(block) {
    if (!(block instanceof HTMLElement)) return false;
    var textInputs;
    try {
      textInputs = block.querySelectorAll(
        'input:not([type="file"]):not([type="hidden"]):not([type="radio"]):not([type="checkbox"]), textarea'
      );
    } catch (eQuery) {
      return false;
    }
    for (var i = 0; i < textInputs.length; i++) {
      if (visible(textInputs[i])) return true;
    }
    return false;
  }

  function ashbyNearestFieldBlock(el) {
    if (!(el instanceof HTMLElement)) return null;
    return (
      el.closest(
        '[class*="field"]:not([class*="fields"]), fieldset, [role="group"], [data-testid*="field"]'
      ) || el.parentElement
    );
  }

  /**
   * Ashby's top "Autofill from resume" widget — not the required Resume* application field.
   * @param {HTMLInputElement} inp
   * @returns {boolean}
   */
  function isAshbyResumeAutofillInput(inp) {
    if (!isAshbyHost() || !inp) return false;
    var block = ashbyNearestFieldBlock(inp);
    if (!(block instanceof HTMLElement)) return false;
    if (ashbyFieldBlockHasApplicationInputs(block)) return false;
    var chunk = containerText(block, 450).toLowerCase();
    return ASHBY_RESUME_AUTOFILL_RE.test(chunk);
  }

  function hideAshbyAutofillNode(el) {
    if (!(el instanceof HTMLElement)) return;
    if (el.getAttribute('data-jaa-ashby-autofill-hidden') === '1') return;
    el.style.display = 'none';
    el.setAttribute('data-jaa-ashby-autofill-hidden', '1');
    el.setAttribute('aria-hidden', 'true');
  }

  /**
   * Smallest wrapper around Ashby's autofill file input (never the whole application form).
   * @param {HTMLInputElement} inp
   * @returns {HTMLElement|null}
   */
  function ashbyAutofillSectionRootFromInput(inp) {
    var block = ashbyNearestFieldBlock(inp);
    if (!(block instanceof HTMLElement)) return null;
    if (ashbyFieldBlockHasApplicationInputs(block)) return null;
    var chunk = containerText(block, 450).toLowerCase();
    if (!ASHBY_RESUME_AUTOFILL_RE.test(chunk)) return null;
    var root = block;
    var parent = block.parentElement;
    for (var d = 0; d < 3 && parent instanceof HTMLElement; d++) {
      var pt = containerText(parent, 500).toLowerCase();
      if (!ASHBY_RESUME_AUTOFILL_RE.test(pt)) break;
      if (ashbyFieldBlockHasApplicationInputs(parent)) break;
      if (pt.indexOf('linkedin') >= 0 || pt.indexOf('require sponsorship') >= 0) break;
      root = parent;
      parent = parent.parentElement;
    }
    return root;
  }

  /**
   * Hide Ashby's native resume autofill UI so only ApplyPilot profile data is used.
   * @returns {{ hidden_sections: number, hidden_banners: number }}
   */
  function suppressAshbyResumeAutofillUI() {
    var hiddenSections = 0;
    var hiddenBanners = 0;
    if (!isAshbyHost()) {
      return { hidden_sections: 0, hidden_banners: 0 };
    }
    var hiddenRoots = new Set();
    var fileInputs;
    try {
      fileInputs = document.querySelectorAll('input[type="file"]');
    } catch (eFiles) {
      fileInputs = [];
    }
    for (var fi = 0; fi < fileInputs.length; fi++) {
      var inp = fileInputs[fi];
      if (!isAshbyResumeAutofillInput(inp)) continue;
      var root = ashbyAutofillSectionRootFromInput(inp);
      if (!(root instanceof HTMLElement) || hiddenRoots.has(root)) continue;
      hiddenRoots.add(root);
      hideAshbyAutofillNode(root);
      hiddenSections++;
    }

    var nodes;
    try {
      nodes = document.querySelectorAll('p, span, div, label, h2, h3, h4');
    } catch (eQuery) {
      return { hidden_sections: hiddenSections, hidden_banners: hiddenBanners };
    }
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      if (!(n instanceof HTMLElement)) continue;
      if (n.getAttribute('data-jaa-ashby-autofill-hidden') === '1') continue;
      var raw = normalizeBtnText(n).toLowerCase();
      if (!ASHBY_AUTOFILL_DONE_RE.test(raw) || raw.indexOf('review') < 0) continue;
      var bannerRoot = n;
      var parent = n.parentElement;
      for (var bd = 0; bd < 4 && parent instanceof HTMLElement; bd++) {
        var pt = containerText(parent, 320).toLowerCase();
        if (ashbyFieldBlockHasApplicationInputs(parent)) break;
        if (pt.length > 320) break;
        bannerRoot = parent;
        parent = parent.parentElement;
      }
      if (hiddenRoots.has(bannerRoot)) continue;
      if (ashbyFieldBlockHasApplicationInputs(bannerRoot)) continue;
      hiddenRoots.add(bannerRoot);
      hideAshbyAutofillNode(bannerRoot);
      hiddenBanners++;
    }
    return { hidden_sections: hiddenSections, hidden_banners: hiddenBanners };
  }

  /**
   * Undo mistaken hides from older suppress logic (e.g. entire form wrapper).
   */
  function restoreAshbyOverhiddenSections() {
    if (!isAshbyHost()) return 0;
    var nodes;
    try {
      nodes = document.querySelectorAll('[data-jaa-ashby-autofill-hidden="1"]');
    } catch (eQuery) {
      return 0;
    }
    var restored = 0;
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      if (!(el instanceof HTMLElement)) continue;
      if (ashbyFieldBlockHasApplicationInputs(el)) {
        el.style.display = '';
        el.removeAttribute('data-jaa-ashby-autofill-hidden');
        el.removeAttribute('aria-hidden');
        restored++;
      }
    }
    return restored;
  }

  function fileInputDirectLabel(inp) {
    if (!(inp instanceof HTMLElement)) return '';
    return labelForInputEl(inp) || '';
  }

  function isSupplementalFileInput(inp) {
    var lab = fileInputDirectLabel(inp);
    if (SUPPLEMENTAL_FILE_RE.test(lab)) return true;
    var idn = (
      (inp.id || '') +
      ' ' +
      (inp.name || '') +
      ' ' +
      (inp.getAttribute('aria-label') || '')
    ).toLowerCase();
    return SUPPLEMENTAL_FILE_RE.test(idn);
  }

  /** 0–100: higher = more likely the primary resume/CV upload. */
  function resumeFileInputScore(inp) {
    if (!inp || (inp.type || '').toLowerCase() !== 'file') return -100;
    if (isAshbyResumeAutofillInput(inp)) return -100;
    if (isSupplementalFileInput(inp)) return -100;
    var direct = fileInputDirectLabel(inp);
    var directLow = direct.toLowerCase();
    if (COVER_LABEL_RE.test(directLow) || directLow.indexOf('cover') >= 0) return -100;
    if (RESUME_LABEL_RE.test(directLow)) return 100;
    if (directLow.indexOf('resume') >= 0 || directLow.indexOf('cv') >= 0) return 90;
    var idn = (
      (inp.id || '') +
      ' ' +
      (inp.name || '') +
      ' ' +
      (inp.getAttribute('aria-label') || '') +
      ' ' +
      (inp.getAttribute('data-field') || '')
    ).toLowerCase();
    if (RESUME_LABEL_RE.test(idn) || idn.indexOf('resume') >= 0) return 85;
    var node = inp.parentElement;
    for (var d = 0; d < 5 && node; d++) {
      var chunk = containerText(node, 280);
      if (SUPPLEMENTAL_FILE_RE.test(chunk) && !RESUME_LABEL_RE.test(chunk)) return -50;
      if (COVER_LABEL_RE.test(chunk) && !RESUME_LABEL_RE.test(chunk.split(/cover/i)[0] || '')) {
        if (/cover\s*letter/i.test(chunk) && !RESUME_SECTION_RE.test(chunk)) return -100;
      }
      if (RESUME_SECTION_RE.test(chunk) || (RESUME_LABEL_RE.test(chunk) && !/cover\s*letter/i.test(chunk))) {
        return 55 - d * 5;
      }
      node = node.parentElement;
    }
    return 0;
  }

  function isResumeFileInput(inp) {
    return resumeFileInputScore(inp) >= 50;
  }

  function questionLabelForContainer(container) {
    if (!(container instanceof HTMLElement)) return '';
    var label = container.querySelector('label, legend');
    if (label) {
      var lt = (label.innerText || '').replace(/\s+/g, ' ').trim();
      if (lt) return lt;
    }
    var heading = container.querySelector(
      'h1, h2, h3, h4, h5, h6, [class*="label"], [class*="Label"], [class*="title"], [class*="Title"], [class*="prompt"], [class*="Prompt"]'
    );
    if (heading) {
      var ht = (heading.innerText || '').replace(/\s+/g, ' ').trim();
      if (ht && ht.length > 3) return ht;
    }
    var node = container;
    for (var d = 0; d < 4 && node; d++) {
      var prev = node.previousElementSibling;
      if (prev instanceof HTMLElement) {
        var pt = (prev.innerText || '').replace(/\s+/g, ' ').trim();
        if (pt && pt.indexOf('?') >= 0 && pt.length < 500) return pt;
      }
      node = node.parentElement;
    }
    var aria = container.getAttribute('aria-label') || container.getAttribute('aria-labelledby');
    if (aria) {
      var byId = document.getElementById(aria);
      if (byId) {
        var at = (byId.innerText || '').replace(/\s+/g, ' ').trim();
        if (at) return at;
      }
    }
    return '';
  }

  /**
   * Prefer the short question ending in "?" (Ashby puts long helper copy in the same block).
   * @param {HTMLElement} container
   * @returns {string}
   */
  function questionPromptFromContainer(container) {
    if (!(container instanceof HTMLElement)) return '';
    var candidates = [];

    function tryAdd(text) {
      var t = String(text || '').replace(/\s+/g, ' ').trim();
      if (t.indexOf('?') < 0 || t.length < 8) return;
      var m = t.match(/(.+?\?)/);
      var q = m ? m[1].trim() : t.split('?')[0].trim() + '?';
      if (q.length >= 8 && q.length <= 350) candidates.push(q);
    }

    tryAdd(questionLabelForContainer(container));

    var nodes;
    try {
      nodes = container.querySelectorAll(
        'label, legend, [class*="label"], [class*="Label"], [class*="title"], [class*="Title"], [class*="prompt"], [class*="Prompt"], p, span, h1, h2, h3, h4, h5, h6'
      );
    } catch (e) {
      nodes = [];
    }
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      if (!(n instanceof HTMLElement)) continue;
      tryAdd(n.innerText || n.textContent);
    }

    if (container.previousElementSibling instanceof HTMLElement) {
      tryAdd(container.previousElementSibling.innerText);
    }

    if (!candidates.length) {
      var ct = containerText(container, 500);
      var matches = ct.match(/[^?]{8,350}\?/g);
      if (matches) {
        for (var mi = 0; mi < matches.length; mi++) {
          tryAdd(matches[mi]);
        }
      }
    }
    if (!candidates.length) return '';
    candidates.sort(function (a, b) {
      return a.length - b.length;
    });
    return candidates[0];
  }

  /**
   * Ashby puts Yes/No toggles in a nested div; the "?" prompt is usually on a parent field block.
   * @param {HTMLElement} toggleContainer
   * @returns {string}
   */
  function questionForYesNoContainer(toggleContainer) {
    if (!(toggleContainer instanceof HTMLElement)) return '';
    var node = toggleContainer;
    for (var d = 0; d < 10 && node; d++) {
      var q = questionPromptFromContainer(node);
      if (q && q.indexOf('?') >= 0) return q;
      node = node.parentElement;
    }
    node = toggleContainer;
    for (var d2 = 0; d2 < 10 && node; d2++) {
      var blob = containerText(node, 900);
      var prep = blob.match(/[^.?!\n]{10,220}\?/g);
      if (prep && prep.length) {
        if (prep.length === 1) return prep[0].replace(/\s+/g, ' ').trim();
        var best = prep[0];
        var bestScore = -1;
        for (var pi = 0; pi < prep.length; pi++) {
          var cand = prep[pi].replace(/\s+/g, ' ').trim();
          var score = 0;
          if (isVisaSponsorshipQuestion(cand)) score += 4;
          if (/\b(comfortable|in[- ]?office|commute|tri[- ]?state)\b/i.test(cand)) score += 2;
          if (node.contains(toggleContainer)) score += 1;
          if (score > bestScore) {
            bestScore = score;
            best = cand;
          }
        }
        return best;
      }
      node = node.parentElement;
    }
    return '';
  }

  function questionStemFromLabel(label) {
    var key = normalizeLabelKey(label);
    var m = key.match(/(.+?\?)/);
    return m ? m[1].trim() : key.slice(0, 100);
  }

  function fieldStemAlreadySeen(fields, label) {
    var stem = questionStemFromLabel(label);
    if (!stem) return false;
    for (var i = 0; i < fields.length; i++) {
      if (questionStemFromLabel(fields[i].label_text) === stem) return true;
    }
    return false;
  }

  function isMultiOptionRadioBlock(container) {
    if (!(container instanceof HTMLElement)) return false;
    var groups;
    try {
      groups = container.querySelectorAll('[role="radiogroup"]');
    } catch (e) {
      groups = [];
    }
    for (var g = 0; g < groups.length; g++) {
      var radios = groups[g].querySelectorAll('[role="radio"]');
      var opts = [];
      for (var r = 0; r < radios.length; r++) {
        if (!visible(radios[r])) continue;
        var rt = normalizeBtnText(radios[r]);
        if (rt) opts.push(rt);
      }
      if (opts.length > 2 && !isYesNoOptions(opts.map(function (t) { return { text: t, value: t }; }))) {
        return true;
      }
    }
    var nativeRadios = container.querySelectorAll('input[type="radio"]');
    if (nativeRadios.length > 2) return true;
    return false;
  }

  function containerLooksRequired(container) {
    if (!(container instanceof HTMLElement)) return false;
    var label = questionLabelForContainer(container);
    if (label.indexOf('*') >= 0) return true;
    try {
      if (container.querySelector('[required], [aria-required="true"]')) return true;
      if (container.closest('[aria-required="true"]')) return true;
      var reqHint = container.querySelector('[class*="required"], [class*="Required"]');
      if (reqHint && (reqHint.innerText || '').indexOf('*') >= 0) return true;
    } catch (e) {
      /* ignore */
    }
    return false;
  }

  function clearPreviousMarkers() {
    try {
      document.querySelectorAll('[data-jaa-fid]').forEach(function (n) {
        n.removeAttribute('data-jaa-fid');
      });
    } catch (e) {
      /* ignore */
    }
  }

  function normalizeBtnText(el) {
    return (el.innerText || el.textContent || el.getAttribute('aria-label') || '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  /** @returns {'yes'|'no'|''} */
  function normalizeYesNoChoiceText(el) {
    var t = normalizeBtnText(el).toLowerCase();
    if (t === 'yes' || t === 'y') return 'yes';
    if (t === 'no' || t === 'n') return 'no';
    return '';
  }

  function yesNoChoiceCount(container) {
    if (!(container instanceof HTMLElement)) return 0;
    var yes = 0;
    var no = 0;
    var buttons;
    try {
      buttons = container.querySelectorAll(
        'button, [role="button"], [role="radio"], label, [class*="toggle"], [class*="Toggle"], input[type="radio"], [class*="option"], [class*="Option"], [class*="segment"]'
      );
    } catch (e) {
      return 0;
    }
    for (var i = 0; i < buttons.length; i++) {
      var b = buttons[i];
      if (!visible(b) && !(b instanceof HTMLInputElement && b.type === 'radio')) continue;
      var yn = normalizeYesNoChoiceText(b);
      if (!yn && b instanceof HTMLInputElement && b.type === 'radio') {
        yn = normalizeYesNoChoiceText(labelTextFor(b) || String(b.value || ''));
      }
      if (yn === 'yes') yes++;
      else if (yn === 'no') no++;
    }
    return yes + no;
  }

  function getYesNoPair(container) {
    if (!(container instanceof HTMLElement)) return null;
    var yesBtn = null;
    var noBtn = null;
    var buttons;
    try {
      buttons = container.querySelectorAll(
        'button, [role="button"], [role="radio"], label, [class*="toggle"], [class*="Toggle"], input[type="radio"], [class*="option"], [class*="Option"], [class*="segment"]'
      );
    } catch (e) {
      return null;
    }
    for (var i = 0; i < buttons.length; i++) {
      var b = buttons[i];
      if (!visible(b) && !(b instanceof HTMLInputElement && b.type === 'radio')) continue;
      var yn = normalizeYesNoChoiceText(b);
      if (!yn && b instanceof HTMLInputElement && b.type === 'radio') {
        yn = normalizeYesNoChoiceText(labelTextFor(b) || String(b.value || ''));
      }
      if (yn === 'yes') {
        yesBtn = b;
      } else if (yn === 'no') {
        noBtn = b;
      }
    }
    if (yesBtn && noBtn) {
      return { yes: yesBtn, no: noBtn, container: container };
    }
    return null;
  }

  function findYesNoContainerForVisaSponsorship() {
    var blocks;
    try {
      blocks = document.querySelectorAll(
        '[data-jaa-control="yes_no_buttons"], [data-jaa-control="role_radio"]'
      );
    } catch (eQuery) {
      return null;
    }
    for (var i = 0; i < blocks.length; i++) {
      var block = blocks[i];
      if (!(block instanceof HTMLElement) || !visible(block)) continue;
      var control = block.getAttribute('data-jaa-control') || '';
      var q =
        control === 'role_radio'
          ? questionPromptFromContainer(block)
          : questionForYesNoContainer(block);
      if (isVisaSponsorshipQuestion(q)) return block;
    }
    return null;
  }

  function containerForYesNoPair(btn) {
    var node = btn.parentElement;
    for (var d = 0; d < 16 && node; d++) {
      if (node === document.body || node === document.documentElement) break;
      if (getYesNoPair(node) && yesNoChoiceCount(node) === 2) return node;
      node = node.parentElement;
    }
    return null;
  }

  function lowestCommonAncestorYesNoPair(el1, el2) {
    if (!(el1 instanceof HTMLElement) || !(el2 instanceof HTMLElement)) return null;
    var ancestors = [];
    var node = el1;
    for (var d = 0; d < 18 && node; d++) {
      ancestors.push(node);
      node = node.parentElement;
    }
    node = el2;
    for (var d2 = 0; d2 < 18 && node; d2++) {
      if (ancestors.indexOf(node) >= 0 && yesNoChoiceCount(node) === 2 && getYesNoPair(node)) {
        return node;
      }
      node = node.parentElement;
    }
    return null;
  }

  /**
   * Every minimal Yes/No pair on the page (two Ashby screening questions = two containers).
   * @returns {HTMLElement[]}
   */
  function enumerateMinimalYesNoContainers() {
    var seen = new Set();
    var out = [];

    function addContainer(parent) {
      if (!(parent instanceof HTMLElement) || seen.has(parent)) return;
      if (parent === document.body || parent === document.documentElement) return;
      seen.add(parent);
      out.push(parent);
    }

    var buttons;
    try {
      buttons = document.querySelectorAll(
        'button, [role="button"], [role="radio"], input[type="radio"], label, [class*="toggle"], [class*="Toggle"], [class*="option"], [class*="Option"], [class*="segment"]'
      );
    } catch (eBtn) {
      buttons = [];
    }
    for (var i = 0; i < buttons.length; i++) {
      var b = buttons[i];
      if (!visible(b)) continue;
      if (!normalizeYesNoChoiceText(b)) continue;
      var parent = containerForYesNoPair(b);
      if (parent) addContainer(parent);
    }

    var groups;
    try {
      groups = document.querySelectorAll('[role="radiogroup"]');
    } catch (eGrp) {
      return out;
    }
    for (var gi = 0; gi < groups.length; gi++) {
      var group = groups[gi];
      if (!(group instanceof HTMLElement) || !visible(group)) continue;
      var ynRadios = [];
      var radios = group.querySelectorAll('[role="radio"], input[type="radio"]');
      for (var ri = 0; ri < radios.length; ri++) {
        var r = radios[ri];
        if (!visible(r) && !(r instanceof HTMLInputElement && r.type === 'radio')) continue;
        if (!normalizeYesNoChoiceText(r)) {
          var viaLabel = normalizeYesNoChoiceText(labelTextFor(r) || '');
          if (!viaLabel) continue;
        }
        ynRadios.push(r);
      }
      if (ynRadios.length < 2) continue;
      for (var pi = 0; pi + 1 < ynRadios.length; pi += 2) {
        var pairRoot =
          lowestCommonAncestorYesNoPair(ynRadios[pi], ynRadios[pi + 1]) ||
          containerForYesNoPair(ynRadios[pi]) ||
          ynRadios[pi].parentElement;
        if (pairRoot instanceof HTMLElement && getYesNoPair(pairRoot)) {
          addContainer(pairRoot);
        }
      }
    }
    return out;
  }

  function isConsentCheckboxLabel(text) {
    var t = String(text || '').replace(/\s+/g, ' ').trim();
    if (t.length < 12) return false;
    if (EEO_CHECKBOX_RE.test(t)) return false;
    if (MARKETING_OPT_IN_RE.test(t)) return false;
    return CONSENT_CHECKBOX_RE.test(t);
  }

  function consentCheckboxLabel(el) {
    if (!(el instanceof HTMLElement)) return '';
    var lab = labelForInputEl(el);
    if (lab && lab.length > 12) return lab;
    var wrap = el.closest(
      'label, fieldset, [class*="field"], [class*="question"], [class*="Field"], [class*="Question"], li, div'
    );
    for (var d = 0; d < 8 && wrap instanceof HTMLElement; d++) {
      var qt = questionPromptFromContainer(wrap) || questionLabelForContainer(wrap);
      if (qt && qt.length > 12) return qt;
      var innerLabel = wrap.querySelector('label');
      if (innerLabel) {
        var lt = (innerLabel.innerText || '').replace(/\s+/g, ' ').trim();
        if (lt.length > 12) return lt;
      }
      wrap = wrap.parentElement;
    }
    return lab;
  }

  /**
   * @param {HTMLInputElement} inp
   * @param {string} value
   * @returns {boolean}
   */
  function applyCheckbox(inp, value) {
    if (!(inp instanceof HTMLInputElement) || (inp.type || '').toLowerCase() !== 'checkbox') {
      return false;
    }
    var raw = String(value || '').toLowerCase().trim();
    var want =
      raw === 'checked' ||
      raw === 'true' ||
      raw === '1' ||
      raw === 'on' ||
      raw === 'yes' ||
      raw.indexOf('agree') >= 0;
    if (inp.checked === want) return true;
    try {
      inp.focus();
    } catch (eFocus) {
      /* ignore */
    }
    inp.checked = want;
    inp.dispatchEvent(new Event('input', { bubbles: true }));
    inp.dispatchEvent(new Event('change', { bubbles: true }));
    clickChoiceElement(inp);
    return inp.checked === want;
  }

  function isPlaceholderLikeLabel(text, el) {
    var t = String(text || '').trim();
    if (!t) return true;
    if (PLACEHOLDER_LABEL_RE.test(t)) return true;
    if (el instanceof HTMLElement && el.placeholder) {
      var ph = String(el.placeholder).trim();
      if (t === ph) return true;
    }
    return false;
  }

  function fieldMetaBlobFromParts(labelText, placeholder, nameAttr, idAttr, el) {
    var extra = '';
    if (el instanceof HTMLElement) {
      extra =
        ' ' +
        (el.getAttribute('data-field') || '') +
        ' ' +
        (el.getAttribute('autocomplete') || '');
    }
    return [labelText, placeholder, nameAttr, idAttr, extra].join(' ');
  }

  function fieldMetaBlobFromRow(row, el) {
    if (!row) return '';
    return fieldMetaBlobFromParts(
      row.label_text,
      row.placeholder,
      row.name_attr,
      row.id_attr,
      el
    );
  }

  function labelAssociatedWithInput(el) {
    if (!(el instanceof HTMLElement)) return '';
    var id = el.id;
    if (id) {
      try {
        var forLab = document.querySelector('label[for="' + CSS.escape(id) + '"]');
        if (forLab instanceof HTMLElement) {
          var ft = (forLab.innerText || '').replace(/\s+/g, ' ').trim().replace(/\*+$/, '');
          if (ft && !isPlaceholderLikeLabel(ft, el)) return ft;
        }
      } catch (eFor) {
        /* ignore */
      }
    }
    var labelledBy = el.getAttribute('aria-labelledby');
    if (labelledBy) {
      var ids = labelledBy.split(/\s+/);
      for (var ai = 0; ai < ids.length; ai++) {
        var ref = document.getElementById(ids[ai].trim());
        if (!(ref instanceof HTMLElement)) continue;
        var at = (ref.innerText || ref.textContent || '').replace(/\s+/g, ' ').trim().replace(/\*+$/, '');
        if (at && !isPlaceholderLikeLabel(at, el)) return at;
      }
    }
    return '';
  }

  function enrichSerializedLabel(el, row) {
    var lab = row && row.label_text ? String(row.label_text).trim() : '';
    if (lab && !isPlaceholderLikeLabel(lab, el)) return lab.replace(/\*+$/, '').trim();
    var associated = labelAssociatedWithInput(el);
    if (associated) return associated;
    var wrap = el.closest(
      'fieldset, [role="group"], [role="radiogroup"], [class*="field"], [class*="question"], [class*="Field"], [class*="Question"]'
    );
    if (wrap instanceof HTMLElement) {
      var qt = questionLabelForContainer(wrap);
      if (qt && !isPlaceholderLikeLabel(qt, el)) return qt.replace(/\*+$/, '').trim();
    }
    var meta = fieldMetaBlobFromRow(row, el);
    if (/\blocation\b/i.test(meta) && !/relocation|learn about|job source/i.test(meta)) {
      return 'Location';
    }
    return lab;
  }

  function labelForInputEl(el) {
    var wrap = el.closest(
      'fieldset, [role="group"], [role="radiogroup"], [class*="field"], [class*="question"], [class*="Field"], [class*="Question"]'
    );
    if (wrap instanceof HTMLElement) {
      var qt = questionLabelForContainer(wrap);
      if (qt && qt.length > 1 && !isPlaceholderLikeLabel(qt, el)) {
        return qt.replace(/\*+$/, '').trim();
      }
    }
    var lt = labelTextFor(el);
    if (lt && lt.length > 1 && !isPlaceholderLikeLabel(lt, el)) return lt;
    if (wrap instanceof HTMLElement) {
      var enriched = enrichSerializedLabel(el, {
        label_text: lt,
        placeholder: el.getAttribute('placeholder'),
        name_attr: el.name,
        id_attr: el.id
      });
      if (enriched) return enriched;
    }
    return lt || '';
  }

  function elementLooksLikeApplicantLocationField(el) {
    if (!(el instanceof HTMLElement)) return false;
    var meta = fieldMetaBlobFromParts('', el.placeholder, el.name, el.id, el);
    if (/\blocation\b/i.test(meta) && !/relocation|learn about|job source/i.test(meta)) {
      return true;
    }
    return isProfileApplicantLocationLabel(labelForInputEl(el));
  }

  function isCountryFieldLabel(labelText) {
    var lab = String(labelText || '').replace(/\*/g, '').trim();
    if (/^country$/i.test(lab)) return true;
    if (/\bcountry\b/i.test(lab) && /\b(location|city|phone)\b/i.test(lab)) return false;
    return /\b(country|country\/region|country of residence)\b/i.test(lab);
  }

  function assignmentTargetsApplicantLocation(assignment) {
    if (!assignment) return false;
    if (isCountryFieldLabel(assignment.label_text)) return false;
    if (isProfileApplicantLocationLabel(assignment.label_text)) return true;
    var val = String(assignment.value || '').trim();
    if (!val || isVisaSponsorshipQuestion(assignment.label_text)) return false;
    if (/^yes$/i.test(val) || /^no$/i.test(val)) return false;
    return /,.+/.test(val);
  }

  function scrollToTopForApply() {
    scrollAllScrollableContainers(0);
    try {
      window.scrollTo(0, 0);
    } catch (eTop) {
      /* ignore */
    }
  }

  function countExistingEducationRows() {
    return findEducationBlocks().length || countExistingEducationRowsByDegreeLabels();
  }

  function countExistingEducationRowsByDegreeLabels() {
    var count = 0;
    var candidates;
    try {
      candidates = document.querySelectorAll('input, textarea, select');
    } catch (e) {
      return 0;
    }
    for (var i = 0; i < candidates.length; i++) {
      var c = candidates[i];
      if (!(c instanceof HTMLElement)) continue;
      if (!visibleForSerialize(c)) continue;
      var cl = normalizeLabelKey(labelForInputEl(c));
      if (cl === 'degree' || cl.indexOf('degree') === 0) count++;
    }
    return count;
  }

  /**
   * One education row = smallest container holding a single Degree input.
   * Order matches document order (same as scan duplicate_label_index).
   * @returns {HTMLElement[]}
   */
  function sortElementsByDocumentOrder(elements) {
    return elements.slice().sort(function (a, b) {
      if (a === b) return 0;
      var pos = a.compareDocumentPosition(b);
      if (pos & Node.DOCUMENT_POSITION_FOLLOWING) return -1;
      if (pos & Node.DOCUMENT_POSITION_PRECEDING) return 1;
      try {
        return a.getBoundingClientRect().top - b.getBoundingClientRect().top;
      } catch (eRect) {
        return 0;
      }
    });
  }

  function findEducationBlocks() {
    var blocks = [];
    var seen = new Set();
    var candidates;
    try {
      candidates = document.querySelectorAll('input, textarea, select');
    } catch (e) {
      return blocks;
    }
    for (var i = 0; i < candidates.length; i++) {
      var inp = candidates[i];
      if (!(inp instanceof HTMLElement)) continue;
      if (!visibleForSerialize(inp)) continue;
      var lab = normalizeLabelKey(labelForInputEl(inp));
      if (lab !== 'degree' && lab.indexOf('degree') !== 0) continue;
      var container = inp.parentElement;
      var best = null;
      for (var d = 0; d < 14 && container; d++) {
        var degCount = countDegreeInputsIn(container);
        if (degCount === 1) {
          best = container;
          break;
        }
        if (degCount > 1) {
          best = null;
          break;
        }
        container = container.parentElement;
      }
      if (!(best instanceof HTMLElement)) {
        var fallback = inp.closest(
          'fieldset, [role="group"], [class*="field"], [class*="Field"], [class*="question"]'
        );
        best = fallback instanceof HTMLElement ? fallback : inp.parentElement;
      }
      if (best instanceof HTMLElement && !seen.has(best)) {
        seen.add(best);
        blocks.push(best);
      }
    }
    return sortElementsByDocumentOrder(blocks);
  }

  function resolveEducationFieldInBlock(kind, blockIndex) {
    var blocks = findEducationBlocks();
    if (blockIndex < 0 || blockIndex >= blocks.length) return null;
    var block = blocks[blockIndex];
    var inputs = block.querySelectorAll('input, textarea, select');
    for (var i = 0; i < inputs.length; i++) {
      var inp = inputs[i];
      if (!(inp instanceof HTMLElement)) continue;
      if (!visibleForSerialize(inp)) continue;
      var lab = normalizeLabelKey(labelForInputEl(inp));
      if (kind === 'degree' && (lab === 'degree' || lab.indexOf('degree') === 0)) return inp;
      if (kind === 'discipline' && (lab === 'discipline' || lab.indexOf('discipline') === 0)) {
        return inp;
      }
    }
    return null;
  }

  function scrollEducationBlockIntoView(blockIndex) {
    var blocks = findEducationBlocks();
    if (blockIndex < 0 || blockIndex >= blocks.length) return;
    try {
      blocks[blockIndex].scrollIntoView({ block: 'center', behavior: 'instant' });
    } catch (_eScroll) {
      try {
        blocks[blockIndex].scrollIntoView();
      } catch (_eScroll2) {
        /* ignore */
      }
    }
  }

  function isEducationDegreeOrDisciplineLabel(label) {
    var norm = normalizeLabelKey(label || '');
    return (
      norm === 'degree' ||
      norm === 'discipline' ||
      norm.indexOf('degree') === 0 ||
      norm.indexOf('discipline') === 0
    );
  }

  function educationAssignmentSortRank(assignment) {
    if (!assignment) return 500;
    var label = normalizeLabelKey(assignment.label_text || '');
    var idx =
      typeof assignment.duplicate_label_index === 'number' ? assignment.duplicate_label_index : 0;
    if (label === 'degree' || label.indexOf('degree') === 0) return 40 + idx * 4;
    if (label === 'discipline' || label.indexOf('discipline') === 0) return 41 + idx * 4;
    return 500;
  }

  function labelMatchesAssignment(clExact, clStem, wantExact, wantShort, wantStem) {
    if (wantExact && clExact === wantExact) return true;
    if (wantShort && clExact === wantShort) return true;
    if (wantStem && clStem === wantStem) return true;
    if (wantStem && clExact.indexOf(wantStem.replace(/\?/g, '').trim()) >= 0) return true;
    return false;
  }

  /**
   * Find a form control by label (primary) or stale data-jaa-fid (fallback).
   * @param {{ field_uid?: string, label_text?: string, value?: string, duplicate_label_index?: number }} assignment
   * @returns {HTMLElement|null}
   */
  function fidElementMatchesScreeningAssignment(el, assignment) {
    if (!(el instanceof HTMLElement) || !assignment || !assignment.label_text) return true;
    var cl = labelForInputEl(el);
    if (isVisaSponsorshipQuestion(assignment.label_text)) {
      return isVisaSponsorshipQuestion(cl);
    }
    if (isWorkAuthorizationQuestion(assignment.label_text)) {
      return isWorkAuthorizationQuestion(cl);
    }
    return true;
  }

  function resolveAssignmentElement(assignment) {
    if (!assignment) return null;
    var uidRaw = assignment.field_uid != null ? String(assignment.field_uid) : '';
    if (/^\d+$/.test(uidRaw)) {
      var byFid = document.querySelector('[data-jaa-fid="' + uidRaw + '"]');
      if (byFid instanceof HTMLElement && fidElementMatchesScreeningAssignment(byFid, assignment)) {
        return byFid;
      }
    }

    var yesNoBlock = resolveYesNoContainerForAssignment(assignment);
    if (yesNoBlock) return yesNoBlock;

    var label = assignment.label_text ? String(assignment.label_text) : '';
    if (!label) return null;
    var wantExact = normalizeLabelKey(label);
    var wantStem = questionStem(label);
    var wantShort = normalizeLabelKey(label.split('—')[0] || label);
    var dupIdx =
      typeof assignment.duplicate_label_index === 'number'
        ? assignment.duplicate_label_index
        : 0;

    if (isEducationDegreeOrDisciplineLabel(wantShort || wantExact)) {
      if (wantShort === 'degree' || wantExact === 'degree' || wantExact.indexOf('degree') === 0) {
        var degBlockEl = resolveEducationFieldInBlock('degree', dupIdx);
        if (degBlockEl) return degBlockEl;
      }
      if (
        wantShort === 'discipline' ||
        wantExact === 'discipline' ||
        wantExact.indexOf('discipline') === 0
      ) {
        var disBlockEl = resolveEducationFieldInBlock('discipline', dupIdx);
        if (disBlockEl) return disBlockEl;
      }
    }

    var candidates;
    try {
      candidates = document.querySelectorAll('input, textarea, select');
    } catch (e) {
      return null;
    }

    var labelMatches = [];
    var best = null;
    var bestScore = 0;
    for (var i = 0; i < candidates.length; i++) {
      var c = candidates[i];
      if (!(c instanceof HTMLElement)) continue;
      if (!visibleForSerialize(c)) continue;
      var tag = c.tagName.toLowerCase();
      var inputType = (c.type || '').toLowerCase();
      if (tag === 'input' && SKIP_INPUT_TYPES[inputType]) continue;

      var cl = labelForInputEl(c);
      if (!cl) continue;
      var clExact = normalizeLabelKey(cl);
      var clStem = questionStem(cl);
      if (labelMatchesAssignment(clExact, clStem, wantExact, wantShort, wantStem)) {
        labelMatches.push(c);
        continue;
      }

      var score = 0;
      var words = wantStem.split(' ').filter(function (w) {
        return w.length > 3;
      });
      for (var wi = 0; wi < words.length; wi++) {
        if (clExact.indexOf(words[wi]) >= 0) score++;
      }
      if (score > bestScore) {
        bestScore = score;
        best = c;
      }
    }
    if (labelMatches.length) {
      if (dupIdx >= 0 && dupIdx < labelMatches.length) return labelMatches[dupIdx];
      return labelMatches[0];
    }
    if (bestScore >= 2 && best) return best;
    return null;
  }

  function scrollToRevealFormFields() {
    try {
      var y = window.scrollY || 0;
      var maxScroll = Math.max(
        document.documentElement.scrollHeight - window.innerHeight,
        0
      );
      var step = Math.max(Math.floor(window.innerHeight * 0.85), 320);
      for (var pos = 0; pos <= maxScroll; pos += step) {
        window.scrollTo(0, pos);
      }
      window.scrollTo(0, maxScroll);
      window.scrollTo(0, y);
    } catch (e) {
      /* ignore */
    }
  }

  function listScrollableContainers() {
    var out = [];
    var seen = new Set();
    function add(el) {
      if (el instanceof HTMLElement && !seen.has(el)) {
        seen.add(el);
        out.push(el);
      }
    }
    add(document.documentElement);
    add(document.body);
    var nodes;
    try {
      nodes = document.querySelectorAll('main, [role="main"], form, section, article, div');
    } catch (e) {
      return out;
    }
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      if (!(el instanceof HTMLElement)) continue;
      var st = window.getComputedStyle(el);
      var scrollableY =
        (st.overflowY === 'auto' || st.overflowY === 'scroll') &&
        el.scrollHeight > el.clientHeight + 8;
      var scrollableX =
        (st.overflowX === 'auto' || st.overflowX === 'scroll') &&
        el.scrollWidth > el.clientWidth + 8;
      if (scrollableY || scrollableX) add(el);
    }
    return out;
  }

  function scrollAllScrollableContainers(fraction) {
    var frac = typeof fraction === 'number' ? Math.min(Math.max(fraction, 0), 1) : 1;
    var containers = listScrollableContainers();
    for (var i = 0; i < containers.length; i++) {
      var cont = containers[i];
      var maxY = Math.max(cont.scrollHeight - cont.clientHeight, 0);
      var maxX = Math.max(cont.scrollWidth - cont.clientWidth, 0);
      cont.scrollTop = Math.floor(maxY * frac);
      cont.scrollLeft = Math.floor(maxX * frac);
    }
    try {
      var maxWin = Math.max(document.documentElement.scrollHeight - window.innerHeight, 0);
      window.scrollTo(0, Math.floor(maxWin * frac));
    } catch (eWin) {
      /* ignore */
    }
  }

  /**
   * Ashby lazy-mounts screening questions — scroll every pane and wait between passes.
   * @returns {Promise<void>}
   */
  function revealAllFormContentAsync() {
    var steps = 12;
    var delayMs = 110;
    var chain = Promise.resolve();
    for (var p = 0; p <= steps; p++) {
      (function (frac) {
        chain = chain.then(function () {
          scrollAllScrollableContainers(frac);
          return new Promise(function (resolve) {
            setTimeout(resolve, delayMs);
          });
        });
      })(p / steps);
    }
    return chain.then(function () {
      scrollAllScrollableContainers(1);
      return new Promise(function (resolve) {
        setTimeout(resolve, 220);
      });
    });
  }

  function isYesNoOptions(opts) {
    if (!opts || opts.length !== 2) return false;
    var a = String(opts[0].text || opts[0].value || '').toLowerCase();
    var b = String(opts[1].text || opts[1].value || '').toLowerCase();
    return (a === 'yes' && b === 'no') || (a === 'no' && b === 'yes');
  }

  function serializeRoleRadioGroups(fields, radioGroupsSeen) {
    var groups;
    try {
      groups = document.querySelectorAll('[role="radiogroup"]');
    } catch (e) {
      return;
    }
    for (var gi = 0; gi < groups.length && fields.length < MAX_FIELDS; gi++) {
      var group = groups[gi];
      if (!(group instanceof HTMLElement) || !visible(group)) continue;
      if (group.getAttribute('data-jaa-fid')) continue;
      var radios = group.querySelectorAll('[role="radio"]');
      if (!radios.length) continue;
      var opts = [];
      for (var ri = 0; ri < radios.length && ri < 12; ri++) {
        var r = radios[ri];
        if (!visible(r)) continue;
        var rt = normalizeBtnText(r);
        if (!rt) continue;
        opts.push({ value: rt, text: rt });
      }
      if (opts.length < 2) continue;
      var gkey = 'rr-' + gi + '-' + opts[0].text.slice(0, 24);
      if (radioGroupsSeen[gkey]) continue;
      radioGroupsSeen[gkey] = true;
      var label = questionPromptFromContainer(group) || containerText(group, 400);
      if (!label || label.length < 8) continue;
      if (fieldStemAlreadySeen(fields, label)) continue;
      var yesNo = isYesNoOptions(opts);
      pushField(
        fields,
        group,
        {
          field_uid: '',
          tag: 'div',
          input_type: yesNo ? 'yes_no_buttons' : 'role_radio',
          name_attr: null,
          id_attr: null,
          label_text: label,
          placeholder: null,
          aria_label: group.getAttribute('aria-label') || null,
          required: containerLooksRequired(group),
          max_length: null,
          options: yesNo
            ? [
                { value: 'Yes', text: 'Yes' },
                { value: 'No', text: 'No' }
              ]
            : opts
        },
        yesNo ? 'yes_no_buttons' : 'role_radio'
      );
    }
  }

  function pushField(fields, el, row, controlKind) {
    if (fields.length >= MAX_FIELDS) return;
    var uid = String(fields.length);
    el.setAttribute('data-jaa-fid', uid);
    if (controlKind) el.setAttribute('data-jaa-control', controlKind);
    row.field_uid = uid;
    fields.push(row);
  }

  function fieldsIncludeVisaSponsorshipQuestion(fields) {
    for (var i = 0; i < fields.length; i++) {
      if (fields[i] && isVisaSponsorshipQuestion(fields[i].label_text)) return true;
    }
    return false;
  }

  /**
   * Ashby sometimes nests screening toggles so the generic button walk misses visa sponsorship.
   * @param {(text: string) => boolean} matcher
   * @returns {HTMLElement|null}
   */
  function ashbyBlockHasRadioYesNo(block) {
    if (!(block instanceof HTMLElement)) return false;
    var radios = block.querySelectorAll('input[type="radio"]');
    if (radios.length !== 2) return false;
    var opts = [];
    for (var ri = 0; ri < 2; ri++) {
      var r = radios[ri];
      if (!visibleForSerialize(r)) return false;
      var rt = labelTextFor(r) || String(r.value || '');
      if (rt) opts.push({ value: rt, text: rt });
    }
    return opts.length === 2 && isYesNoOptions(opts);
  }

  function blockHasYesNoControls(block) {
    if (!(block instanceof HTMLElement)) return false;
    if (yesNoChoiceCount(block) >= 2 && getYesNoPair(block)) return true;
    return ashbyBlockHasRadioYesNo(block);
  }

  /** Smallest descendant (or self) that contains a single Yes/No control pair. */
  function findTightestYesNoControlBlock(node, depth) {
    if (depth == null) depth = 0;
    if (depth > 16 || !(node instanceof HTMLElement) || !visible(node)) return null;
    for (var i = 0; i < node.children.length; i++) {
      var ch = node.children[i];
      if (!(ch instanceof HTMLElement)) continue;
      var sub = findTightestYesNoControlBlock(ch, depth + 1);
      if (sub) return sub;
    }
    if (yesNoChoiceCount(node) === 2 && getYesNoPair(node)) return node;
    if (ashbyBlockHasRadioYesNo(node)) return node;
    return null;
  }

  function labelFromYesNoBlock(block, blob) {
    var label = questionForYesNoContainer(block) || questionPromptFromContainer(block);
    if (label && label.indexOf('?') >= 0) return label;
    var text = blob || containerText(block, 600);
    var qmatches = text.match(/[^.?!\n]{10,240}\?/g);
    if (!qmatches || !qmatches.length) return label || '';
    if (qmatches.length === 1) return qmatches[0].replace(/\s+/g, ' ').trim();
    for (var qi = 0; qi < qmatches.length; qi++) {
      var cand = qmatches[qi].replace(/\s+/g, ' ').trim();
      if (isVisaSponsorshipQuestion(cand)) return cand;
    }
    for (var qj = 0; qj < qmatches.length; qj++) {
      var cand2 = qmatches[qj].replace(/\s+/g, ' ').trim();
      if (/\b(comfortable|in[- ]?office|commute)\b/i.test(cand2)) return cand2;
    }
    return qmatches[qmatches.length - 1].replace(/\s+/g, ' ').trim();
  }

  /**
   * Ashby screening: one field block per Yes/No question (in-office + sponsorship, etc.).
   * Only walks Ashby field wrappers — never the whole document tree (stack overflow risk).
   */
  function serializeAshbyScreeningFieldBlocks(fields) {
    if (!isAshbyHost() || fields.length >= MAX_FIELDS) return;
    try {
      var blocks;
      try {
        blocks = document.querySelectorAll(
          '[class*="field"]:not([class*="fields"]), fieldset, [data-testid*="field"], [role="group"]'
        );
      } catch (eQuery) {
        return;
      }
      var seenTargets = new Set();
      var minimal = enumerateMinimalYesNoContainers();
      for (var mi = 0; mi < minimal.length && fields.length < MAX_FIELDS; mi++) {
        var target = minimal[mi];
        if (!(target instanceof HTMLElement) || seenTargets.has(target)) continue;
        if (target.getAttribute('data-jaa-fid')) continue;
        var blob = containerText(target, 650);
        var label = labelFromYesNoBlock(target, blob);
        if (!label || label.length < 8 || fieldStemAlreadySeen(fields, label)) continue;
        seenTargets.add(target);
        pushYesNoScreeningField(fields, target, label);
      }
      for (var bi = 0; bi < blocks.length && fields.length < MAX_FIELDS; bi++) {
        var block = blocks[bi];
        if (!(block instanceof HTMLElement) || !visible(block)) continue;
        var blob = containerText(block, 650);
        var qHint = questionPromptFromContainer(block);
        if (blob.indexOf('?') < 0 && (!qHint || qHint.indexOf('?') < 0)) continue;
        var target = findTightestYesNoControlBlock(block);
        if (!(target instanceof HTMLElement) || seenTargets.has(target)) continue;
        if (target.getAttribute('data-jaa-fid')) continue;
        var label = labelFromYesNoBlock(target, blob) || qHint;
        if (!label || label.length < 8 || fieldStemAlreadySeen(fields, label)) continue;
        seenTargets.add(target);
        pushYesNoScreeningField(fields, target, label);
      }
    } catch (eAshbyScan) {
      try {
        console.debug('[ApplyPilot] Ashby screening scan skipped', eAshbyScan);
      } catch (eLog) {
        /* ignore */
      }
    }
  }

  function findYesNoBlockForQuestionMatcher(matcher) {
    var roots;
    try {
      roots = document.querySelectorAll(
        'label, legend, [class*="question"], [class*="Question"], [class*="field"], [class*="Field"], fieldset, [role="group"]'
      );
    } catch (eQuery) {
      return null;
    }
    var best = null;
    var bestLen = Infinity;
    for (var i = 0; i < roots.length; i++) {
      var el = roots[i];
      if (!(el instanceof HTMLElement) || !visible(el)) continue;
      var text = containerText(el, 800);
      if (!matcher(text)) continue;
      var block = el;
      for (var d = 0; d < 12 && block; d++) {
        if (blockHasYesNoControls(block)) {
          var tight = findTightestYesNoControlBlock(block) || block;
          var blen = containerText(tight, 800).length;
          if (blen < bestLen) {
            bestLen = blen;
            best = tight;
          }
          break;
        }
        block = block.parentElement;
      }
    }
    return best;
  }

  function labelForMinimalYesNoContainer(container) {
    if (!(container instanceof HTMLElement)) return '';
    var blob = containerText(container, 500);
    var qs = blob.match(/[^.?!\n]{10,240}\?/g);
    if (!qs || !qs.length) {
      return questionForYesNoContainer(container) || questionPromptFromContainer(container) || '';
    }
    if (qs.length === 1) return qs[0].replace(/\s+/g, ' ').trim();
    for (var i = 0; i < qs.length; i++) {
      var cand = qs[i].replace(/\s+/g, ' ').trim();
      if (textLooksLikeSponsorshipScreening(cand)) return cand;
    }
    for (var j = 0; j < qs.length; j++) {
      var cand2 = qs[j].replace(/\s+/g, ' ').trim();
      if (/\b(comfortable|in[- ]?office|commute)\b/i.test(cand2)) return cand2;
    }
    return qs[qs.length - 1].replace(/\s+/g, ' ').trim();
  }

  function pushYesNoScreeningField(fields, block, fallbackLabel) {
    if (!(block instanceof HTMLElement) || fields.length >= MAX_FIELDS) return false;
    if (block.getAttribute('data-jaa-fid')) {
      recordScanDebugTrace('yes_no_push_skip_has_fid', {
        label: String(fallbackLabel || '').slice(0, 80)
      });
      return false;
    }
    var label = String(fallbackLabel || '').trim();
    var qm = label.match(/(.+?\?)/);
    if (qm && qm[1]) label = qm[1].trim();
    if (!label || label.length < 8 || label.indexOf('?') < 0) {
      label = labelForMinimalYesNoContainer(block);
    }
    if (!label || label.length < 8) {
      label = questionForYesNoContainer(block) || questionPromptFromContainer(block);
    }
    if (!label || label.length < 8) {
      recordScanDebugTrace('yes_no_push_skip_short_label', {
        label: String(label || '').slice(0, 80)
      });
      return false;
    }
    if (fieldStemAlreadySeen(fields, label)) {
      recordScanDebugTrace('yes_no_push_skip_stem_seen', { label: label.slice(0, 120) });
      return false;
    }
    recordScanDebugTrace('yes_no_push_ok', { label: label.slice(0, 120) });
    pushField(
      fields,
      block,
      {
        field_uid: '',
        tag: 'div',
        input_type: 'yes_no_buttons',
        name_attr: null,
        id_attr: null,
        label_text: label,
        placeholder: null,
        aria_label: null,
        required: containerLooksRequired(block),
        max_length: null,
        options: [
          { value: 'Yes', text: 'Yes' },
          { value: 'No', text: 'No' }
        ]
      },
      'yes_no_buttons'
    );
    return true;
  }

  function textLooksLikeSponsorshipScreening(text) {
    var t = String(text || '');
    if (isVisaSponsorshipQuestion(t)) return true;
    return /\bsponsorship\b/i.test(t) && /\b(require|will you|future)\b/i.test(t);
  }

  function serializeSponsorshipFromMinimalContainers(fields) {
    if (fieldsIncludeVisaSponsorshipQuestion(fields) || fields.length >= MAX_FIELDS) return;
    var containers = enumerateMinimalYesNoContainers();
    for (var i = 0; i < containers.length; i++) {
      var c = containers[i];
      if (!(c instanceof HTMLElement) || c.getAttribute('data-jaa-fid')) continue;
      var blob = containerText(c, 500);
      if (!textLooksLikeSponsorshipScreening(blob)) continue;
      var label = labelForMinimalYesNoContainer(c);
      var pushed = pushYesNoScreeningField(fields, c, label);
      recordScanDebugTrace('sponsorship_from_minimal_container', {
        label: label.slice(0, 120),
        pushed: pushed
      });
      return;
    }
  }

  function serializeSponsorshipYesNoByTextAnchor(fields) {
    if (fieldsIncludeVisaSponsorshipQuestion(fields)) {
      recordScanDebugTrace('sponsorship_anchor_skip_already_in_fields', null);
      return;
    }
    if (fields.length >= MAX_FIELDS) {
      recordScanDebugTrace('sponsorship_anchor_skip_max_fields', null);
      return;
    }
    var nodes;
    try {
      nodes = document.querySelectorAll(
        'label, legend, p, span, h3, h4, h5, [class*="question"], [class*="Question"], [class*="field"], [class*="Field"]'
      );
    } catch (eNodes) {
      recordScanDebugTrace('sponsorship_anchor_query_failed', String(eNodes));
      return;
    }
    var hits = 0;
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      if (!(el instanceof HTMLElement) || !visible(el)) continue;
      var t = normalizeBtnText(el);
      if (t.length < 12 || t.length > 320 || t.indexOf('?') < 0) continue;
      if (!textLooksLikeSponsorshipScreening(t)) continue;
      hits++;
      recordScanDebugTrace('sponsorship_anchor_text_hit', { text: t.slice(0, 120) });
      var walk = el;
      for (var d = 0; d < 12 && walk; d++) {
        if (blockHasYesNoControls(walk)) {
          var target = findTightestYesNoControlBlock(walk) || walk;
          if (target.getAttribute('data-jaa-fid')) {
            var alts = enumerateMinimalYesNoContainers();
            for (var ai = 0; ai < alts.length; ai++) {
              var alt = alts[ai];
              if (!(alt instanceof HTMLElement) || alt.getAttribute('data-jaa-fid')) continue;
              if (!textLooksLikeSponsorshipScreening(containerText(alt, 500))) continue;
              target = alt;
              break;
            }
          }
          var pushed = pushYesNoScreeningField(fields, target, t);
          recordScanDebugTrace('sponsorship_anchor_push', { pushed: pushed, depth: d });
          return;
        }
        walk = walk.parentElement;
      }
      recordScanDebugTrace('sponsorship_anchor_no_controls_near_text', { text: t.slice(0, 120) });
    }
    if (!hits) {
      recordScanDebugTrace('sponsorship_anchor_no_text_hit', null);
    }
  }

  function serializeVisaSponsorshipYesNoIfMissing(fields) {
    if (fields.length >= MAX_FIELDS) return;
    serializeSponsorshipYesNoByTextAnchor(fields);
    if (fieldsIncludeVisaSponsorshipQuestion(fields) || fields.length >= MAX_FIELDS) return;
    var block = findYesNoBlockForQuestionMatcher(function (text) {
      return textLooksLikeSponsorshipScreening(text);
    });
    if (!(block instanceof HTMLElement)) return;
    pushYesNoScreeningField(fields, block, containerText(block, 600));
  }

  function serializeYesNoButtonGroups(fields) {
    var seenStems = new Set();
    var containers = enumerateMinimalYesNoContainers();
    recordScanDebugTrace('yes_no_minimal_containers', { count: containers.length });
    for (var i = 0; i < containers.length && fields.length < MAX_FIELDS; i++) {
      var parent = containers[i];
      var label = labelForMinimalYesNoContainer(parent);
      if (isMultiOptionRadioBlock(parent)) {
        recordScanDebugTrace('yes_no_skip_multi_option', { label: String(label || '').slice(0, 80) });
        continue;
      }
      if (parent.getAttribute && parent.getAttribute('data-jaa-fid')) {
        recordScanDebugTrace('yes_no_skip_marked', { label: String(label || '').slice(0, 80) });
        continue;
      }
      var parentRadioGroup = parent.closest('[role="radiogroup"]');
      if (
        parentRadioGroup &&
        parentRadioGroup.getAttribute('data-jaa-fid') &&
        parent === parentRadioGroup
      ) {
        recordScanDebugTrace('yes_no_skip_radiogroup_fid', { label: String(label || '').slice(0, 80) });
        continue;
      }
      var ptag = (parent.tagName || '').toUpperCase();
      if (ptag === 'FORM' || ptag === 'BODY' || ptag === 'HTML') {
        recordScanDebugTrace('yes_no_skip_root_tag', { tag: ptag });
        continue;
      }
      if (!label || label.length < 8) {
        recordScanDebugTrace('yes_no_skip_short_label', { blob: blob.slice(0, 80) });
        continue;
      }
      var stemKey = normalizeLabelKey(label);
      if (seenStems.has(stemKey) || fieldStemAlreadySeen(fields, label)) {
        recordScanDebugTrace('yes_no_skip_duplicate_stem', { label: label.slice(0, 120) });
        continue;
      }
      seenStems.add(stemKey);
      pushYesNoScreeningField(fields, parent, label);
    }
  }

  function attachScanDebug(result) {
    if (!result || typeof result !== 'object') return result;
    try {
      result.scan_debug = collectScanDebugReport(result.fields || []);
      window.__jaaLastScanDebug = result.scan_debug;
    } catch (eDbgAttach) {
      result.scan_debug = { error: String(eDbgAttach && eDbgAttach.message ? eDbgAttach.message : eDbgAttach) };
    }
    return result;
  }

  function serializeCollectOnly(warnings) {
    if (!warnings) warnings = [];
    warnings.push('Only fields in this page document are included (not inside iframes).');
    resetScanDebugTrace();
    recordScanDebugTrace('serialize_start', { ashby: isAshbyHost() });

    try {
      return attachScanDebug(serializeCollectOnlyBody(warnings));
    } catch (eSerialize) {
      try {
        console.debug('[ApplyPilot] serialize failed', eSerialize);
      } catch (eLog) {
        /* ignore */
      }
      return attachScanDebug({
        fields: [],
        page_url: String(location.href || ''),
        warnings: warnings.concat(['Field scan failed on this page.'])
      });
    }
  }

  function serializeCollectOnlyBody(warnings) {
    var candidates = [];
    try {
      candidates = Array.prototype.slice.call(document.querySelectorAll('input, textarea, select'));
    } catch (e2) {
      return { fields: [], page_url: String(location.href || ''), warnings: warnings.concat(['Could not query form elements.']) };
    }

    var fields = [];
    var radioGroupsSeen = {};
    var labelCounts = {};
    for (var i = 0; i < candidates.length && fields.length < MAX_FIELDS; i++) {
      var el = candidates[i];
      if (!visibleForSerialize(el)) continue;
      var tag = el.tagName.toLowerCase();
      var inputType = (el.type || '').toLowerCase();
      if (tag === 'input' && SKIP_INPUT_TYPES[inputType]) continue;

      var row = {
        field_uid: '',
        tag: tag,
        input_type: tag === 'input' ? inputType : null,
        name_attr: el.name || null,
        id_attr: el.id || null,
        label_text: labelForInputEl(el),
        placeholder: el.getAttribute('placeholder') || null,
        aria_label: el.getAttribute('aria-label') || null,
        required: !!el.required,
        max_length: el.maxLength > 0 ? el.maxLength : null,
        options: null,
        duplicate_label_index: 0
      };
      row.label_text = enrichSerializedLabel(el, row);

      if (tag === 'input' && inputType === 'file') {
        if (isAshbyResumeAutofillInput(el)) continue;
        if (isSupplementalFileInput(el)) continue;
        if (!isResumeFileInput(el)) {
          var fileLabel = row.label_text || row.aria_label || '';
          if (!RESUME_LABEL_RE.test(fileLabel) && !COVER_LABEL_RE.test(fileLabel)) {
            var near = el.closest('fieldset, [class*="field"], [class*="question"], div');
            if (near) fileLabel = questionLabelForContainer(near) || fileLabel;
          }
          if (!RESUME_LABEL_RE.test(fileLabel) && !COVER_LABEL_RE.test(fileLabel)) continue;
        }
        row.label_text = row.label_text || row.aria_label || 'Resume';
        row.input_type = 'file';
      }

      if (tag === 'input' && (inputType === 'text' || inputType === 'search') && isComboboxInput(el)) {
        row.input_type = 'combobox';
      }

      if (tag === 'input' && inputType === 'checkbox') {
        var consentLab = consentCheckboxLabel(el);
        if (!isConsentCheckboxLabel(consentLab)) continue;
        row.label_text = consentLab;
        row.input_type = 'checkbox';
        var consentWrap = el.closest(
          'fieldset, [class*="field"], [class*="question"], [class*="Field"], [class*="Question"]'
        );
        if (consentWrap && containerLooksRequired(consentWrap)) row.required = true;
        pushField(fields, el, row, 'checkbox');
        continue;
      }

      if (tag === 'select') {
        var opts = [];
        for (var j = 0; j < el.options.length && j < 40; j++) {
          var o = el.options[j];
          opts.push({
            value: String(o.value || ''),
            text: String(o.text || '').slice(0, 200)
          });
        }
        row.options = opts;
        if (fieldStemAlreadySeen(fields, row.label_text)) continue;
        if (fieldsAlreadyHaveNycCommuteYesNo(fields) && selectLooksLikeNycCommuteDuplicate(row)) {
          continue;
        }
      }

      if (tag === 'input' && inputType === 'radio') {
        var gname = el.name || el.id || 'radio-' + i;
        if (radioGroupsSeen[gname]) continue;
        radioGroupsSeen[gname] = true;
        var radioLabel = labelForInputEl(el);
        var fieldset = el.closest('fieldset');
        var radioWrap = el.closest(
          '[class*="field"], [class*="question"], [class*="Field"], [class*="Question"], [role="group"], [role="radiogroup"]'
        );
        if (fieldset) {
          var fl = questionPromptFromContainer(fieldset) || questionLabelForContainer(fieldset);
          if (fl) radioLabel = fl;
          if (containerLooksRequired(fieldset)) row.required = true;
        } else if (radioWrap) {
          var wl = questionPromptFromContainer(radioWrap) || questionLabelForContainer(radioWrap);
          if (wl) radioLabel = wl;
          if (containerLooksRequired(radioWrap)) row.required = true;
        }
        if (fieldStemAlreadySeen(fields, radioLabel)) continue;
        row.label_text = radioLabel;
        var groupOpts = [];
        var groupEls;
        try {
          groupEls = el.name
            ? document.querySelectorAll('input[type="radio"][name="' + CSS.escape(el.name) + '"]')
            : [el];
        } catch (eG) {
          groupEls = document.querySelectorAll('input[type="radio"][name="' + String(el.name).replace(/"/g, '') + '"]');
        }
        for (var gi = 0; gi < groupEls.length && gi < 12; gi++) {
          var gr = groupEls[gi];
          groupOpts.push({
            value: String(gr.value || ''),
            text: labelTextFor(gr) || String(gr.value || '')
          });
        }
        row.options = groupOpts;
        pushField(fields, el, row, 'radio');
        continue;
      }

      var labelKey = normalizeLabelKey(row.label_text);
      if (labelKey) {
        row.duplicate_label_index = labelCounts[labelKey] || 0;
        labelCounts[labelKey] = row.duplicate_label_index + 1;
      }

      var controlKind = row.input_type === 'combobox' ? 'combobox' : null;
      pushField(fields, el, row, controlKind);
    }

    if (fields.length < MAX_FIELDS) {
      serializeRoleRadioGroups(fields, radioGroupsSeen);
    }
    if (fields.length < MAX_FIELDS) {
      serializeYesNoButtonGroups(fields);
    }
    if (fields.length < MAX_FIELDS) {
      serializeSponsorshipFromMinimalContainers(fields);
    }
    if (fields.length < MAX_FIELDS) {
      serializeAshbyScreeningFieldBlocks(fields);
    }
    if (fields.length < MAX_FIELDS) {
      serializeVisaSponsorshipYesNoIfMissing(fields);
    }

    recordScanDebugTrace('serialize_done', {
      field_count: fields.length,
      sponsorship_in_fields: fieldsIncludeVisaSponsorshipQuestion(fields)
    });
    return {
      fields: fields,
      page_url: String(location.href || ''),
      warnings: warnings
    };
  }

  function serialize() {
    clearPreviousMarkers();
    scrollToRevealFormFields();
    scrollAllScrollableContainers(1);
    return serializeCollectOnly([]);
  }

  /**
   * Scroll lazy-loaded ATS fields into the DOM, then serialize (Ashby, etc.).
   * @param {number} [educationExpandCount] profile education entries — clicks "Add another" after scroll
   * @returns {Promise<{ fields: Array, page_url: string, warnings: string[] }>}
   */
  function serializeAsync(educationExpandCount) {
    if (!needsDeepScrollSerialize()) {
      return Promise.resolve(serialize());
    }
    if (isAshbyHost()) {
      restoreAshbyOverhiddenSections();
      suppressAshbyResumeAutofillUI();
    }
    return revealAllFormContentAsync().then(function () {
      clearPreviousMarkers();
      var expandCount =
        typeof educationExpandCount === 'number' ? educationExpandCount : 0;
      if (expandCount > 1) {
        return expandEducationRowsAsync(expandCount).then(function (expandResult) {
          var result = serializeCollectOnly([]);
          result.warnings.push(
            'Deep scroll pass completed to include below-the-fold application questions.'
          );
          result.education_expand = expandResult;
          return result;
        });
      }
      var result = serializeCollectOnly([]);
      result.warnings.push(
        'Deep scroll pass completed to include below-the-fold application questions.'
      );
      return result;
    });
  }

  function decodeHtmlEntities(str) {
    if (str == null) return '';
    var s = String(str);
    s = s.replace(/&#x([0-9a-fA-F]+);/g, function (_match, hex) {
      return String.fromCodePoint(parseInt(hex, 16));
    });
    s = s.replace(/&#(\d+);/g, function (_match, num) {
      return String.fromCodePoint(parseInt(num, 10));
    });
    s = s.replace(/&amp;/g, '&');
    s = s.replace(/&#x27;/g, "'");
    s = s.replace(/&#039;/g, "'");
    s = s.replace(/&apos;/g, "'");
    s = s.replace(/&quot;/g, '"');
    s = s.replace(/&lt;/g, '<');
    s = s.replace(/&gt;/g, '>');
    return s;
  }

  function setNativeValue(el, value) {
    var plain = decodeHtmlEntities(value);
    try {
      var proto = Object.getPrototypeOf(el);
      var desc = Object.getOwnPropertyDescriptor(proto, 'value');
      if (desc && desc.set) {
        desc.set.call(el, plain);
      } else {
        el.value = plain;
      }
    } catch (e) {
      try {
        el.value = plain;
      } catch (e2) {
        /* ignore */
      }
    }
    try {
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    } catch (e3) {
      /* ignore */
    }
  }

  function applySelect(el, value) {
    var v = String(value);
    el.value = v;
    if (el.value === v) {
      setNativeValue(el, v);
      return true;
    }
    var lower = v.toLowerCase();
    for (var i = 0; i < el.options.length; i++) {
      var o = el.options[i];
      if (String(o.text).toLowerCase().trim() === lower || String(o.value).toLowerCase() === lower) {
        el.selectedIndex = i;
        setNativeValue(el, o.value);
        return true;
      }
    }
    return false;
  }

  /** @returns {'yes'|'no'|null} */
  function exactYesNoOptionText(optionText) {
    var ot = String(optionText || '').toLowerCase().trim();
    if (ot === 'yes' || ot === 'no') return ot;
    return null;
  }

  function comboboxDisplaysYesNoTarget(el, target) {
    var want = String(target || '').toLowerCase().trim();
    if (want !== 'yes' && want !== 'no') return comboboxShowsValue(el, target);
    var shown = exactYesNoOptionText(comboboxSelectedText(el));
    return shown === want;
  }

  function comboboxOptionMatches(optionText, targetValue) {
    var ot = String(optionText || '').toLowerCase().trim();
    var tv = String(targetValue || '').toLowerCase().trim();
    if (!ot || !tv) return false;
    if (ot === tv) return true;
    if (tv === 'yes' || tv === 'no') {
      return exactYesNoOptionText(ot) === tv;
    }
    if (/^\d+$/.test(tv) && ot === tv) return true;
    var rangeMatch = ot.match(/^(\d+)\s*[-–]\s*(\d+)$/);
    if (rangeMatch && /^\d+$/.test(tv)) {
      var y = parseInt(tv, 10);
      var lo = parseInt(rangeMatch[1], 10);
      var hi = parseInt(rangeMatch[2], 10);
      if (!isNaN(y) && !isNaN(lo) && !isNaN(hi) && y >= lo && y <= hi) return true;
    }
    if ((tv === 'nyc' || tv.indexOf('new york') >= 0) && (ot === 'nyc' || ot.indexOf('new york') >= 0)) {
      return true;
    }
    if (ot.indexOf(tv) >= 0 || tv.indexOf(ot) >= 0) return true;
    if (tv.indexOf('currently local') >= 0 && ot.indexOf('currently local') >= 0) return true;
    if (tv.indexOf('metro area') >= 0 && ot.indexOf('metro') >= 0) return true;
    if (tv.indexOf('willing to relocate') >= 0 && ot.indexOf('relocate') >= 0) return true;
    if (tv.indexOf('commuting') >= 0 && ot.indexOf('commuting') >= 0) return true;
    if (tv.indexOf('n/a') >= 0 && ot.indexOf('n/a') >= 0) return true;
    if (
      (tv.indexOf('llb') >= 0 || tv.indexOf('bachelor of laws') >= 0) &&
      (ot.indexOf('juris doctor') >= 0 || ot.indexOf('j.d') >= 0 || ot.indexOf('bachelor of laws') >= 0 ||
        ot.indexOf("bachelor's degree") >= 0 || ot.indexOf('bachelors degree') >= 0)
    ) {
      return true;
    }
    if (
      (tv.indexOf('juris doctor') >= 0 || tv.indexOf('j.d') >= 0 || tv.indexOf(' jd') >= 0 || tv === 'jd') &&
      (ot.indexOf('juris doctor') >= 0 || ot.indexOf('j.d') >= 0 ||
        ot.indexOf("bachelor's degree") >= 0 || ot.indexOf('bachelors degree') >= 0)
    ) {
      return true;
    }
    if (
      (tv.indexOf(' ba') >= 0 || tv === 'ba' || tv.indexOf('bachelor of arts') >= 0 || tv.indexOf(' arts') >= 0) &&
      (ot.indexOf('bachelor of arts') >= 0 || ot.indexOf('(ba)') >= 0 ||
        ot.indexOf("bachelor's degree") >= 0 || ot.indexOf('bachelors degree') >= 0)
    ) {
      return true;
    }
    if (
      (tv.indexOf(' bs') >= 0 || tv === 'bs' || tv.indexOf('bsc') >= 0 || tv.indexOf('bachelor of science') >= 0) &&
      (ot.indexOf('bachelor of science') >= 0 || ot.indexOf('(bs)') >= 0 || ot.indexOf('(bsc)') >= 0 ||
        ot.indexOf("bachelor's degree") >= 0 || ot.indexOf('bachelors degree') >= 0)
    ) {
      return true;
    }
    if (
      (tv.indexOf('mba') >= 0 || tv.indexOf('master of business') >= 0) &&
      (ot.indexOf('business administration') >= 0 || ot.indexOf('mba') >= 0 || ot.indexOf('m.b.a') >= 0)
    ) {
      return true;
    }
    if (
      (tv.indexOf('ph.d') >= 0 || tv.indexOf('phd') >= 0 || tv.indexOf('doctor of philosophy') >= 0) &&
      (ot.indexOf('doctor of philosophy') >= 0 || ot.indexOf('ph.d') >= 0 || ot.indexOf('phd') >= 0)
    ) {
      return true;
    }
    if (tv.indexOf('associate') >= 0 && ot.indexOf('associate') >= 0) return true;
    if (tv.indexOf('bachelor') >= 0 && ot.indexOf('bachelor') >= 0) {
      if (ot.indexOf("bachelor's degree") >= 0 || ot.indexOf('bachelors degree') >= 0) {
        return true;
      }
      var tokens = ['arts', 'science', 'laws', 'law', 'business', 'engineering', 'economics'];
      for (var ti = 0; ti < tokens.length; ti++) {
        var tok = tokens[ti];
        if (tv.indexOf(tok) >= 0 && ot.indexOf(tok) < 0) return false;
      }
      return true;
    }
    if (tv.indexOf('master') >= 0 && ot.indexOf('master') >= 0) {
      if (ot.indexOf("master's degree") >= 0 || ot.indexOf('masters degree') >= 0) {
        return true;
      }
      return true;
    }
    if (tv.indexOf('economics') >= 0 && ot.indexOf('economics') >= 0) return true;
    if (tv.indexOf('computer') >= 0 && ot.indexOf('computer') >= 0) return true;
    if ((tv === 'yes' || tv.indexOf('i agree') >= 0 || tv.indexOf('acknowledge') >= 0) &&
      (ot === 'yes' || ot.indexOf('agree') >= 0 || ot.indexOf('confirm') >= 0 || ot.indexOf('acknowledge') >= 0)) {
      return true;
    }
    if (tv === 'no' && (ot === 'no' || ot.indexOf('no,') === 0)) return true;
    var words = tv.split(/\s+/).filter(function (w) {
      return w.length > 3;
    });
    if (!words.length) return false;
    var hits = 0;
    for (var wi = 0; wi < words.length; wi++) {
      if (ot.indexOf(words[wi]) >= 0) hits++;
    }
    return hits >= Math.min(3, words.length);
  }

  function countDegreeInputsIn(container) {
    if (!(container instanceof HTMLElement)) return 0;
    var count = 0;
    var inputs = container.querySelectorAll('input, textarea, select');
    for (var i = 0; i < inputs.length; i++) {
      var lab = normalizeLabelKey(labelForInputEl(inputs[i]));
      if (lab === 'degree' || lab.indexOf('degree') === 0) count++;
    }
    return count;
  }

  function closeComboboxMenu(el) {
    if (!(el instanceof HTMLElement)) return;
    try {
      el.focus();
    } catch (eFocus) {
      /* ignore */
    }
    try {
      el.dispatchEvent(
        new KeyboardEvent('keydown', {
          key: 'Escape',
          code: 'Escape',
          keyCode: 27,
          which: 27,
          bubbles: true,
          cancelable: true
        })
      );
    } catch (eEsc) {
      /* ignore */
    }
    try {
      el.blur();
    } catch (eBlur) {
      /* ignore */
    }
  }

  function dismissOpenSelectMenus() {
    closeAllComboboxMenus();
    var expanded;
    try {
      expanded = document.querySelectorAll('input[aria-expanded="true"], [role="combobox"][aria-expanded="true"]');
    } catch (eQuery) {
      expanded = [];
    }
    for (var i = 0; i < expanded.length; i++) {
      closeComboboxMenu(expanded[i]);
    }
    try {
      var anchor = document.querySelector('h1, h2, form legend, [class*="application"]');
      if (anchor instanceof HTMLElement) {
        anchor.dispatchEvent(
          new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window })
        );
        anchor.dispatchEvent(
          new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window })
        );
      }
    } catch (eAnchor) {
      /* ignore */
    }
  }

  function comboboxSelectedText(el) {
    if (!(el instanceof HTMLElement)) return '';
    var root = el.closest(
      '[class*="select__container"], [class*="select__control"], [class*="Select"], [class*="select"]'
    );
    if (root instanceof HTMLElement) {
      var sv = root.querySelector(
        '[class*="single-value"], [class*="SingleValue"], [class*="select__single-value"]'
      );
      if (sv) return normalizeBtnText(sv);
    }
    return normalizeBtnText(el);
  }

  function comboboxShowsValue(el, value) {
    var shown = comboboxSelectedText(el);
    if (!shown) return false;
    return comboboxOptionMatches(shown, value);
  }

  function closeAllComboboxMenus() {
    try {
      document.dispatchEvent(
        new KeyboardEvent('keydown', {
          key: 'Escape',
          code: 'Escape',
          keyCode: 27,
          which: 27,
          bubbles: true,
          cancelable: true
        })
      );
    } catch (eDocEsc) {
      /* ignore */
    }
    var expanded;
    try {
      expanded = document.querySelectorAll(
        'input[aria-expanded="true"], [role="combobox"][aria-expanded="true"]'
      );
    } catch (eQuery) {
      expanded = [];
    }
    for (var i = 0; i < expanded.length; i++) {
      closeComboboxMenu(expanded[i]);
    }
  }

  function isEeoFieldLabel(labelText) {
    var lab = normalizeLabelKey(labelText || '').toLowerCase();
    return (
      lab.indexOf('gender') >= 0 ||
      lab.indexOf('hispanic') >= 0 ||
      lab.indexOf('latino') >= 0 ||
      lab.indexOf('veteran') >= 0 ||
      lab.indexOf('disability') >= 0
    );
  }

  function comboboxListboxForInput(el) {
    if (!(el instanceof HTMLElement)) return null;
    var controlsId = el.getAttribute('aria-controls');
    if (controlsId) {
      var node = document.getElementById(controlsId);
      if (node instanceof HTMLElement) return node;
    }
    var owns = el.getAttribute('aria-owns');
    if (owns) {
      var parts = owns.split(/\s+/);
      for (var oi = 0; oi < parts.length; oi++) {
        var owned = document.getElementById(parts[oi].trim());
        if (owned instanceof HTMLElement) return owned;
      }
    }
    var local = el.closest(
      '[class*="select__container"], [class*="select__control"], [class*="Select"], [class*="select"]'
    );
    if (local instanceof HTMLElement) {
      var lb = local.querySelector('[role="listbox"]');
      if (lb instanceof HTMLElement) return lb;
    }
    return null;
  }

  function comboboxOptionSelector() {
    return '[role="option"], .select__option, [class*="select__option"], [class*="Select-option"]';
  }

  function findComboboxOptionsForElement(el) {
    if (!(el instanceof HTMLElement)) return [];
    var out = [];
    var seenText = new Set();
    var listbox = comboboxListboxForInput(el);
    if (!listbox) {
      var allLb;
      try {
        allLb = document.querySelectorAll('[role="listbox"]');
      } catch (eAll) {
        allLb = [];
      }
      var visibleLb = [];
      for (var li = 0; li < allLb.length; li++) {
        if (allLb[li] instanceof HTMLElement && visible(allLb[li])) {
          visibleLb.push(allLb[li]);
        }
      }
      if (visibleLb.length === 1) {
        listbox = visibleLb[0];
      }
    }
    var roots = [];
    if (listbox instanceof HTMLElement) {
      roots.push(listbox);
    } else {
      var local = el.closest(
        '[class*="select__container"], [class*="select__control"], [class*="Select"], [class*="select"]'
      );
      if (local instanceof HTMLElement) roots.push(local);
    }
    for (var ri = 0; ri < roots.length; ri++) {
      var nodes;
      try {
        nodes = roots[ri].querySelectorAll(comboboxOptionSelector());
      } catch (eQuery) {
        continue;
      }
      for (var i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        if (!(n instanceof HTMLElement)) continue;
        if (!visible(n)) continue;
        var t = normalizeBtnText(n);
        if (!t || isNoOptionsPlaceholder(t) || seenText.has(t)) continue;
        seenText.add(t);
        out.push({ el: n, text: t });
      }
    }
    return out;
  }

  function openComboboxMenu(el) {
    if (!(el instanceof HTMLElement)) return;
    var clickTarget = el;
    var wrap = el.closest(
      '[class*="select__control"], [class*="select-control"], [class*="Select-control"]'
    );
    if (wrap instanceof HTMLElement) clickTarget = wrap;
    try {
      el.focus();
    } catch (eFocus) {
      /* ignore */
    }
    clickChoiceElement(clickTarget);
  }

  function isNoOptionsPlaceholder(text) {
    var t = String(text || '').toLowerCase().trim();
    return t === 'no options' || t === 'no results' || t === 'no matches';
  }

  function isDegreeFieldLabel(labelText) {
    var lab = normalizeLabelKey(labelText || '');
    return lab === 'degree' || lab.indexOf('degree') === 0;
  }

  function isYesNoComboboxValue(value) {
    var low = String(value || '').toLowerCase().trim();
    if (low === 'yes' || low === 'no') return true;
    if (low.indexOf('yes,') === 0 || low.indexOf('no,') === 0) return true;
    return false;
  }

  /** Greenhouse "Do you have 5+ years of experience?" — Yes/No only, never type-ahead. */
  function isPlusYearsYesNoQuestion(labelText) {
    return /do you have\s+\d+\+\s*years|\d+\+\s*years of experience/i.test(String(labelText || ''));
  }

  function isVisaSponsorshipQuestion(labelText) {
    return VISA_SPONSORSHIP_LABEL_RE.test(String(labelText || ''));
  }

  function isWorkAuthorizationQuestion(labelText) {
    var t = String(labelText || '');
    if (!t || isVisaSponsorshipQuestion(t)) return false;
    return /\b(authorized to work|legally authorized|authorization to work)\b/i.test(t);
  }

  function isGreenhouseYesNoScreeningAssignment(assignment) {
    if (!assignment || !assignmentValueIsYesNo(assignment.value)) return false;
    return (
      isVisaSponsorshipQuestion(assignment.label_text) ||
      isWorkAuthorizationQuestion(assignment.label_text)
    );
  }

  function assignmentUidStillValid(assignment, fields) {
    var uid = assignment.field_uid;
    if (!uid || !assignment.label_text) return false;
    for (var i = 0; i < fields.length; i++) {
      var f = fields[i];
      if (!f || f.field_uid !== uid) continue;
      if (isVisaSponsorshipQuestion(assignment.label_text)) {
        return isVisaSponsorshipQuestion(f.label_text);
      }
      if (isWorkAuthorizationQuestion(assignment.label_text)) {
        return isWorkAuthorizationQuestion(f.label_text);
      }
      var aStem = questionStem(assignment.label_text);
      var fStem = questionStem(f.label_text);
      return !!(aStem && fStem && aStem === fStem);
    }
    return false;
  }

  /** NYC / tri-state commute screening (Lever, Greenhouse, etc.). */
  function isNycCommuteScreeningLabel(labelText) {
    var t = String(labelText || '').toLowerCase();
    if (!t) return false;
    if (/tri[- ]?state/.test(t)) return true;
    if (/based in nyc/.test(t) && /\blocated\b/.test(t)) return true;
    if (/\bcommute\b/.test(t) && /\b(office|nyc|new york)\b/.test(t)) return true;
    return false;
  }

  function assignmentValueIsYesNo(value) {
    var v = String(value || '').toLowerCase().trim();
    return v === 'yes' || v === 'no';
  }

  function isRadioLikeInputType(inputType) {
    return inputType === 'radio' || inputType === 'yes_no_buttons' || inputType === 'role_radio';
  }

  function fieldsAlreadyHaveNycCommuteYesNo(fields) {
    for (var i = 0; i < fields.length; i++) {
      var f = fields[i];
      if (!f || !isNycCommuteScreeningLabel(f.label_text)) continue;
      if (isRadioLikeInputType(f.input_type)) return true;
    }
    return false;
  }

  function selectLooksLikeNycCommuteDuplicate(row) {
    if (!row.options) return false;
    if (isNycCommuteScreeningLabel(row.label_text)) return true;
    var lab = String(row.label_text || '').toLowerCase();
    if (/\bnyc\b/.test(lab) && /\bhq\b/.test(lab) && isYesNoOptions(row.options)) return true;
    return false;
  }

  /** Applicant city/location (Greenhouse Location (City), Ashby Location, etc.). */
  function isProfileApplicantLocationLabel(labelText) {
    var lab = String(labelText || '').replace(/\*/g, '').trim();
    if (
      /relocation|relocate|office location|location preference|where did you learn|learn about this job|hear about this job|job source/i.test(
        lab
      )
    ) {
      return false;
    }
    if (/^location$/i.test(lab)) return true;
    return LOCATION_CITY_LABEL_RE.test(lab) || (/\blocation\b/i.test(lab) && /\bcity\b/i.test(lab));
  }

  function expandUsStateName(statePart) {
    var s = String(statePart || '').trim();
    if (!s) return '';
    if (s.length === 2) {
      var full = US_STATE_ABBR_TO_NAME[s.toLowerCase()];
      return full || s;
    }
    return s;
  }

  function dispatchComboboxKey(el, key) {
    if (!(el instanceof HTMLElement)) return;
    var keyCode = key === 'Enter' ? 13 : key === 'ArrowDown' ? 40 : 0;
    if (!keyCode) return;
    try {
      el.dispatchEvent(
        new KeyboardEvent('keydown', {
          key: key,
          code: key,
          keyCode: keyCode,
          which: keyCode,
          bubbles: true,
          cancelable: true
        })
      );
      el.dispatchEvent(
        new KeyboardEvent('keyup', {
          key: key,
          code: key,
          keyCode: keyCode,
          which: keyCode,
          bubbles: true,
          cancelable: true
        })
      );
    } catch (eKey) {
      /* ignore */
    }
  }

  function greenhouseLocationLatLonFilled(el) {
    if (!(el instanceof HTMLElement)) return false;
    var root = el.closest('form');
    if (!(root instanceof HTMLElement)) {
      root = el.closest('[class*="application"], [class*="job-application"], main');
    }
    if (!(root instanceof HTMLElement)) root = document.body;
    var lat;
    var lon;
    try {
      lat = root.querySelector(
        'input[name*="latitude"], input[id*="latitude"], input[name*="Latitude"]'
      );
      lon = root.querySelector(
        'input[name*="longitude"], input[id*="longitude"], input[name*="Longitude"]'
      );
    } catch (eQuery) {
      return false;
    }
    if (!(lat instanceof HTMLInputElement) || !(lon instanceof HTMLInputElement)) return false;
    return !!String(lat.value || '').trim() && !!String(lon.value || '').trim();
  }

  function isLikelyLocationSuggestion(text, cityPart) {
    var t = String(text || '').toLowerCase().trim();
    if (!t || isNoOptionsPlaceholder(t)) return false;
    if (isEeoFieldLabel(t)) return false;
    var city = String(cityPart || '').toLowerCase().trim();
    if (city && t.indexOf(city) >= 0) return true;
    return /,.+,.+/.test(t) || t.indexOf('united states') >= 0;
  }

  function collectLocationOptionNodes(roots, cityPart, seenText, out) {
    for (var ri = 0; ri < roots.length; ri++) {
      var root = roots[ri];
      if (!(root instanceof HTMLElement)) continue;
      var nodes;
      try {
        nodes = root.querySelectorAll(
          '[role="option"], [class*="typeahead"] li, [class*="Typeahead"] li, [class*="menu"] [class*="item"], [class*="MenuItem"], [class*="menuItem"], [data-option-index]'
        );
      } catch (eQuery) {
        continue;
      }
      for (var i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        if (!(n instanceof HTMLElement) || !visible(n)) continue;
        var t = normalizeBtnText(n);
        if (!t || seenText.has(t) || !isLikelyLocationSuggestion(t, cityPart)) continue;
        seenText.add(t);
        out.push({ el: n, text: t });
      }
    }
  }

  function findLocationAutocompleteOptions(el, cityPart) {
    var opts = findComboboxOptionsForElement(el);
    if (opts.length) {
      var filtered = [];
      for (var fi = 0; fi < opts.length; fi++) {
        if (isLikelyLocationSuggestion(opts[fi].text, cityPart)) filtered.push(opts[fi]);
      }
      if (filtered.length) return filtered;
      return opts;
    }
    var out = [];
    var seenText = new Set();
    var local = el.closest(
      '[class*="field"], [class*="Field"], [class*="question"], [class*="Question"], form'
    );
    var roots = [];
    if (local instanceof HTMLElement) roots.push(local);
    roots.push(document.body);
    collectLocationOptionNodes(roots, cityPart, seenText, out);
    if (!out.length) {
      var nodes;
      try {
        nodes = document.querySelectorAll('[role="option"]');
      } catch (eAll) {
        nodes = [];
      }
      for (var i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        if (!(n instanceof HTMLElement) || !visible(n)) continue;
        var t = normalizeBtnText(n);
        if (!t || seenText.has(t) || !isLikelyLocationSuggestion(t, cityPart)) continue;
        seenText.add(t);
        out.push({ el: n, text: t });
      }
    }
    return out;
  }

  function scoreLocationSuggestion(optionText, cityPart, statePart, stateFull, target) {
    var ot = String(optionText || '').toLowerCase().trim();
    var city = String(cityPart || '').toLowerCase().trim();
    if (!ot || !city || ot.indexOf(city) < 0) return 0;
    var score = 55;
    if (stateFull && ot.indexOf(stateFull.toLowerCase()) >= 0) score += 35;
    else if (statePart && ot.indexOf(statePart.toLowerCase()) >= 0) score += 25;
    if (ot.indexOf('united states') >= 0) score += 10;
    if (comboboxOptionMatches(optionText, target)) score += 15;
    return score;
  }

  function pickLocationComboboxOption(options, cityPart, statePart, stateFull, target) {
    var best = null;
    var bestScore = 0;
    for (var i = 0; i < options.length; i++) {
      var sc = scoreLocationSuggestion(options[i].text, cityPart, statePart, stateFull, target);
      if (sc > bestScore) {
        bestScore = sc;
        best = options[i].el;
      }
    }
    if (bestScore >= 55) return best;
    var cityLow = String(cityPart || '').toLowerCase();
    for (var j = 0; j < options.length; j++) {
      if (options[j].text.toLowerCase().indexOf(cityLow) >= 0) return options[j].el;
    }
    return options.length === 1 ? options[0].el : null;
  }

  function locationSelectionCommitted(el, cityPart, stateFull) {
    if (greenhouseLocationLatLonFilled(el)) return true;
    var shown = comboboxSelectedText(el);
    if (!shown || !cityPart) return false;
    var low = shown.toLowerCase().trim();
    if (/start typing/i.test(low)) return false;
    var cityLow = String(cityPart).toLowerCase().trim();
    if (low.indexOf(cityLow) < 0) return false;
    if (isComboboxFilterStub(low) || isNoOptionsPlaceholder(low)) return false;
    if (low === cityLow) return false;
    if (stateFull) {
      var stateLow = stateFull.toLowerCase();
      if (low.indexOf(stateLow) >= 0) return true;
    }
    if (isAshbyHost()) {
      return low.split(',').length >= 2 || low.length > cityLow.length + 4;
    }
    return low.split(',').length >= 2 || /united states/i.test(shown);
  }

  function waitForLocationAutocompleteOptions(el, cityPart, maxWaitMs, intervalMs) {
    var maxMs = typeof maxWaitMs === 'number' ? maxWaitMs : 1400;
    var step = typeof intervalMs === 'number' ? intervalMs : 120;
    return new Promise(function (resolve) {
      var start = Date.now();
      function poll() {
        var opts = findLocationAutocompleteOptions(el, cityPart);
        if (opts.length > 0) {
          resolve(opts);
          return;
        }
        if (Date.now() - start >= maxMs) {
          resolve([]);
          return;
        }
        setTimeout(poll, step);
      }
      poll();
    });
  }

  function clickLocationComboboxOption(el, pickedEl, cityPart, stateFull, settleMs) {
    return new Promise(function (resolve) {
      try {
        pickedEl.scrollIntoView({ block: 'nearest' });
      } catch (eScroll) {
        /* ignore */
      }
      clickChoiceElement(pickedEl);
      try {
        el.focus();
      } catch (eFocus) {
        /* ignore */
      }
      dispatchComboboxKey(el, 'Enter');
      setTimeout(function () {
        dismissOpenSelectMenus();
        resolve(locationSelectionCommitted(el, cityPart, stateFull));
      }, typeof settleMs === 'number' ? settleMs : 480);
    });
  }

  /**
   * Greenhouse location autocomplete (geocode-earth): type city, wait for listbox, click option.
   * Typing alone does not commit hidden lat/lon — a list selection is required.
   * @param {HTMLElement} el
   * @param {string} value
   * @param {number} [extraDelayMs]
   * @returns {Promise<boolean>}
   */
  function applyLocationCityComboboxAsync(el, value, extraDelayMs) {
    var settleMs = typeof extraDelayMs === 'number' ? extraDelayMs : 520;
    var target = String(value || '').trim();
    if (!target) return Promise.resolve(false);
    var commaParts = target.split(',');
    var cityPart = commaParts[0].trim();
    var statePart = commaParts.length > 1 ? commaParts[1].trim() : '';
    var stateFull = expandUsStateName(statePart);
    var typeVariants = [cityPart];
    if (statePart) {
      typeVariants.push(cityPart + ', ' + statePart);
      if (stateFull && stateFull !== statePart) {
        typeVariants.push(cityPart + ', ' + stateFull);
      }
    }

    function tryKeyboardCommit() {
      return new Promise(function (resolve) {
        dispatchComboboxKey(el, 'ArrowDown');
        setTimeout(function () {
          dispatchComboboxKey(el, 'Enter');
          setTimeout(function () {
            dismissOpenSelectMenus();
            resolve(locationSelectionCommitted(el, cityPart, stateFull));
          }, settleMs);
        }, 160);
      });
    }

    function tryTypeVariant(variantIndex) {
      if (variantIndex >= typeVariants.length) {
        return tryKeyboardCommit();
      }
      var typeText = typeVariants[variantIndex];
      return new Promise(function (resolve) {
        dismissOpenSelectMenus();
        setTimeout(function () {
          clearComboboxInputValue(el);
          try {
            el.focus();
            setNativeValue(el, typeText);
            el.dispatchEvent(new Event('input', { bubbles: true }));
          } catch (eSet) {
            /* ignore */
          }
          openComboboxMenu(el);
          var waitMs = variantIndex === 0 ? (isAshbyHost() ? 2200 : 1500) : isAshbyHost() ? 1600 : 1200;
          waitForLocationAutocompleteOptions(el, cityPart, waitMs, 110).then(function (options) {
            if (!options.length && isAshbyHost()) {
              tryKeyboardCommit().then(function (kbOk) {
                if (kbOk) {
                  resolve(true);
                  return;
                }
                tryTypeVariant(variantIndex + 1).then(resolve);
              });
              return;
            }
            if (!options.length) {
              tryTypeVariant(variantIndex + 1).then(resolve);
              return;
            }
            var pickedEl = pickLocationComboboxOption(
              options,
              cityPart,
              statePart,
              stateFull,
              target
            );
            if (!pickedEl) {
              tryTypeVariant(variantIndex + 1).then(resolve);
              return;
            }
            clickLocationComboboxOption(el, pickedEl, cityPart, stateFull, settleMs).then(function (ok) {
              if (ok) {
                resolve(true);
                return;
              }
              if (options.length >= 1) {
                clickLocationComboboxOption(el, options[0].el, cityPart, stateFull, settleMs).then(
                  function (okFirst) {
                    if (okFirst) {
                      resolve(true);
                      return;
                    }
                    tryTypeVariant(variantIndex + 1).then(resolve);
                  }
                );
                return;
              }
              tryTypeVariant(variantIndex + 1).then(resolve);
            });
          });
        }, 90);
      });
    }

    return tryTypeVariant(0);
  }

  function acknowledgementComboboxDisplaysTarget(shown, value, labelText) {
    var s = String(shown || '').trim().toLowerCase();
    if (!s || isComboboxFilterStub(s)) return false;
    var v = String(value || '').trim().toLowerCase();
    if (v && (s === v || s.indexOf(v) >= 0 || v.indexOf(s) >= 0)) return true;
    if (s.indexOf('yes') === 0 && s.indexOf('acknowledge') >= 0) return true;
    if (isAcknowledgementComboboxLabel(labelText) && s.indexOf('acknowledge') >= 0) return true;
    return comboboxOptionMatches(shown, value);
  }

  function comboboxFilterPrefix(value, labelText) {
    var v = String(value || '').trim();
    if (!v) return '';
    if (isAcknowledgementComboboxLabel(labelText)) return '';
    if (isYesNoComboboxValue(v) || isPlusYearsYesNoQuestion(labelText)) {
      return '';
    }
    var low = v.toLowerCase();
    if (isDegreeFieldLabel(labelText)) {
      if (low.indexOf('bachelor') >= 0) return 'bachelor';
      if (low.indexOf('master') >= 0) return 'master';
      if (low.indexOf('associate') >= 0) return 'associate';
      if (low.indexOf('doctor') >= 0 || low.indexOf('ph.d') >= 0) return 'doctor';
    }
    if (/^\d/.test(v)) {
      return v.replace(/[^\d-–+].*/, '').slice(0, 2);
    }
    var paren = v.match(/\(([^)]+)\)/);
    if (paren && paren[1] && paren[1].length >= 2) {
      return paren[1].slice(0, 4);
    }
    var words = v.split(/\s+/).filter(function (w) {
      return w.length > 2;
    });
    if (words.length) return words[0].slice(0, 5).toLowerCase();
    return v.slice(0, 4).toLowerCase();
  }

  function degreeFilterPrefixes(value) {
    var prefixes = [];
    var seen = new Set();
    function add(p) {
      var key = String(p || '').toLowerCase();
      if (!key || seen.has(key)) return;
      seen.add(key);
      prefixes.push(p);
    }
    var low = String(value || '').toLowerCase();
    if (low.indexOf('bachelor') >= 0) add('bachelor');
    if (low.indexOf('master') >= 0) add('master');
    if (low.indexOf('associate') >= 0) add('associate');
    if (low.indexOf('doctor of philosophy') >= 0 || low.indexOf('ph.d') >= 0 || low.indexOf('phd') >= 0) {
      add('phd');
      add('philosophy');
    }
    if (low.indexOf('llb') >= 0 || low.indexOf('juris') >= 0 || low.indexOf('bachelor of laws') >= 0) {
      add('juris');
      add('law');
    }
    if (low.indexOf('mba') >= 0 || low.indexOf('business administration') >= 0) {
      add('mba');
      add('business');
    }
    if (low.indexOf('arts') >= 0 || low.indexOf(' ba') >= 0 || low === 'ba') add('arts');
    if (low.indexOf('science') >= 0 || low.indexOf(' bs') >= 0 || low === 'bs' || low.indexOf('bsc') >= 0) {
      add('science');
    }
    if (low.indexOf('economics') >= 0) add('econ');
    if (low.indexOf('law') >= 0) add('law');
    add(comboboxFilterPrefix(value, 'degree'));
    return prefixes;
  }

  function applyComboboxTypeFilter(el, prefix, menuAlreadyOpen) {
    if (!(el instanceof HTMLElement) || !prefix) return;
    if (!menuAlreadyOpen) {
      dismissOpenSelectMenus();
      openComboboxMenu(el);
    }
    try {
      setNativeValue(el, prefix);
      el.dispatchEvent(new Event('input', { bubbles: true }));
    } catch (eSet) {
      /* ignore */
    }
  }

  function shouldUseComboboxFilter(labelText, pickedEl, value) {
    if (isDegreeFieldLabel(labelText)) return true;
    if (pickedEl) return false;
    if (isPlusYearsYesNoQuestion(labelText) || isYesNoComboboxValue(value)) {
      return false;
    }
    if (isEducationDegreeOrDisciplineLabel(labelText || '')) {
      return true;
    }
    if (/years of (industry )?experience/i.test(String(labelText || ''))) {
      return /^\d/.test(String(value || '').trim());
    }
    return false;
  }

  function filterPrefixForAttempt(value, labelText, attempt) {
    var prefixes = [];
    if (isAcknowledgementComboboxLabel(labelText)) return '';
    if (isYesNoComboboxValue(value) || isPlusYearsYesNoQuestion(labelText)) {
      return '';
    }
    if (isDegreeFieldLabel(labelText)) {
      if (attempt === 0) return '';
      prefixes = degreeFilterPrefixes(value);
      var prefixIdx = attempt - 1;
      if (prefixIdx < 0 || prefixIdx >= prefixes.length) return '';
      return prefixes[prefixIdx];
    }
    if (shouldUseComboboxFilter(labelText, null, value)) {
      prefixes = [comboboxFilterPrefix(value, labelText)];
    }
    if (!prefixes.length) return '';
    var idx = Math.min(attempt, prefixes.length - 1);
    return prefixes[idx];
  }

  function maxComboboxApplyAttempts(value, labelText) {
    if (isDegreeFieldLabel(labelText)) {
      return Math.max(3, degreeFilterPrefixes(value).length + 1);
    }
    return 3;
  }

  var COMBOBOX_FILTER_STUBS = {
    bachelor: true,
    master: true,
    associate: true,
    juris: true,
    doctor: true,
    science: true,
    arts: true,
    law: true,
    econ: true,
    mba: true,
    phd: true,
    philosophy: true,
    business: true
  };

  function isComboboxFilterStub(text) {
    var t = String(text || '').toLowerCase().trim();
    if (COMBOBOX_FILTER_STUBS[t]) return true;
    if (/^\d{1,2}-?$/.test(t)) return true;
    return false;
  }

  function clearComboboxInputValue(el) {
    if (!(el instanceof HTMLElement)) return;
    try {
      setNativeValue(el, '');
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    } catch (eClear) {
      /* ignore */
    }
    closeComboboxMenu(el);
  }

  function comboboxHasRealSelection(el) {
    var shown = comboboxSelectedText(el);
    if (!shown) return false;
    var low = shown.toLowerCase();
    if (isComboboxFilterStub(low)) return false;
    return low !== 'select...' && low !== 'select' && !isNoOptionsPlaceholder(low);
  }

  function scoreEducationFuzzy(optionText, targetValue) {
    var ot = String(optionText || '').toLowerCase();
    var tv = String(targetValue || '').toLowerCase();
    if (!ot || !tv) return 0;
    var words = tv.split(/[^a-z0-9]+/).filter(function (w) {
      return w.length > 2;
    });
    if (!words.length) return 0;
    var hits = 0;
    for (var i = 0; i < words.length; i++) {
      if (ot.indexOf(words[i]) >= 0) hits++;
    }
    if (hits >= 2) return 35 + hits * 15;
    if (hits === 1 && words.length === 1) return 30;
    return 0;
  }

  function scoreComboboxOption(optionText, targetValue, labelText) {
    var fuzzy = scoreComboboxOptionStrict(optionText, targetValue);
    if (fuzzy > 0) return fuzzy;
    if (isEducationDegreeOrDisciplineLabel(labelText || '')) {
      return scoreEducationFuzzy(optionText, targetValue);
    }
    return 0;
  }

  function scoreComboboxOptionStrict(optionText, targetValue) {
    var ot = String(optionText || '').toLowerCase().trim();
    var tv = String(targetValue || '').toLowerCase().trim();
    if (tv === 'yes' || tv === 'no') {
      return exactYesNoOptionText(ot) === tv ? 100 : 0;
    }
    if (!comboboxOptionMatches(optionText, targetValue)) return 0;
    if (ot === tv) return 100;
    if (ot.indexOf(tv) >= 0 || tv.indexOf(ot) >= 0) return 85;
    var words = tv.split(/\s+/).filter(function (w) {
      return w.length > 2;
    });
    var hits = 0;
    for (var wi = 0; wi < words.length; wi++) {
      if (ot.indexOf(words[wi]) >= 0) hits++;
    }
    return 50 + hits * 10;
  }

  function pickNearestRangeOption(options, value) {
    var target = String(value).trim();
    var rangeFromValue = target.match(/^(\d+)\s*[-–]\s*(\d+)$/);
    var y = parseInt(target, 10);
    if (isNaN(y)) {
      if (rangeFromValue) y = parseInt(rangeFromValue[1], 10);
      else return null;
    }
    var best = null;
    var bestDist = Infinity;
    for (var i = 0; i < options.length; i++) {
      var t = options[i].text.trim();
      if (t === target || t.replace(/\s/g, '') === target.replace(/\s/g, '')) return options[i].el;
      var m = t.match(/^(\d+)\s*[-–]\s*(\d+)$/);
      if (m) {
        var lo = parseInt(m[1], 10);
        var hi = parseInt(m[2], 10);
        if (y >= lo && y <= hi) return options[i].el;
        var dist = y < lo ? lo - y : y > hi ? y - hi : 0;
        if (dist < bestDist) {
          bestDist = dist;
          best = options[i].el;
        }
        continue;
      }
      var plus = t.match(/^(\d+)\+$/);
      if (plus && y >= parseInt(plus[1], 10)) return options[i].el;
    }
    return best;
  }

  function degreeTargetValues(value, labelText) {
    var primary = String(value || '').trim();
    var targets = primary ? [primary] : [];
    if (!isDegreeFieldLabel(labelText) || !primary) return targets;
    var low = primary.toLowerCase();
    if (
      low.indexOf('llb') >= 0 ||
      low.indexOf('bachelor of laws') >= 0 ||
      low.indexOf('juris doctor') >= 0 ||
      low.indexOf('j.d') >= 0 ||
      low === 'law' ||
      low === 'laws'
    ) {
      if (targets.indexOf("Bachelor's Degree") < 0) targets.push("Bachelor's Degree");
    }
    return targets;
  }

  function tryPickComboboxOption(options, value, labelText) {
    var pickedEl = pickComboboxOption(options, value, labelText);
    if (!pickedEl) {
      for (var i = 0; i < options.length; i++) {
        if (options[i].text.trim() === String(value).trim()) {
          pickedEl = options[i].el;
          break;
        }
      }
    }
    return pickedEl;
  }

  function isAcknowledgementComboboxLabel(labelText) {
    var t = String(labelText || '').toLowerCase();
    if (!t) return false;
    if (/acknowledge.*work\s+location|work\s+location\s+expectations/.test(t)) return true;
    return CONSENT_CHECKBOX_RE.test(t);
  }

  function pickAcknowledgementComboboxOptionEl(options, value, labelText) {
    if (!isAcknowledgementComboboxLabel(labelText)) return null;
    var tv = String(value || '').trim().toLowerCase();
    for (var i = 0; i < options.length; i++) {
      var raw = options[i].text.trim();
      var ot = raw.toLowerCase();
      if (tv && (ot === tv || ot.indexOf(tv) >= 0 || tv.indexOf(ot) >= 0)) return options[i].el;
    }
    for (var j = 0; j < options.length; j++) {
      var opt = options[j].text.trim().toLowerCase();
      if (
        opt.indexOf('yes') === 0 &&
        (opt.indexOf('acknowledge') >= 0 || opt.indexOf('agree') >= 0)
      ) {
        return options[j].el;
      }
    }
    return null;
  }

  function tryPickComboboxOptionForTargets(options, value, labelText) {
    var ackPick = pickAcknowledgementComboboxOptionEl(options, value, labelText);
    if (ackPick) return ackPick;
    var targets = isDegreeFieldLabel(labelText) ? degreeTargetValues(value, labelText) : [value];
    for (var ti = 0; ti < targets.length; ti++) {
      var picked = tryPickComboboxOption(options, targets[ti], labelText);
      if (picked) return picked;
    }
    return null;
  }

  function pickComboboxOption(options, value, labelText) {
    var best = null;
    var bestScore = 0;
    for (var i = 0; i < options.length; i++) {
      var score = scoreComboboxOption(options[i].text, value, labelText);
      if (score > bestScore) {
        bestScore = score;
        best = options[i].el;
      }
    }
    if (bestScore > 0) return best;
    return pickNearestRangeOption(options, value);
  }

  /**
   * Greenhouse / react-select: open listbox and click matching option (do not type full strings).
   * @param {HTMLElement} el
   * @param {string} value
   * @returns {boolean}
   */
  function applyCombobox(el, value) {
    if (!(el instanceof HTMLElement)) return false;
    var target = String(value || '').trim();
    if (!target) return false;

    closeAllComboboxMenus();
    openComboboxMenu(el);
    var options = findComboboxOptionsForElement(el);
    var picked = pickComboboxOption(options, target);
    if (picked) {
      clickChoiceElement(picked);
      closeComboboxMenu(el);
      closeAllComboboxMenus();
      return true;
    }

    for (var i = 0; i < options.length; i++) {
      if (options[i].text.trim() === target) {
        clickChoiceElement(options[i].el);
        closeComboboxMenu(el);
        closeAllComboboxMenus();
        return true;
      }
    }

    closeComboboxMenu(el);
    closeAllComboboxMenus();
    return false;
  }

  function radioChoiceMatchesValue(r, lower) {
    var rv = String(r.value || '').toLowerCase();
    var rl = labelTextFor(r).toLowerCase();
    return (
      rv === lower ||
      rl === lower ||
      rl.indexOf(lower) >= 0 ||
      lower.indexOf(rl) >= 0 ||
      (lower === 'yes' && (rv === 'true' || rv === '1')) ||
      (lower === 'no' && (rv === 'false' || rv === '0'))
    );
  }

  function clickYesNoInContainer(container, value) {
    if (!(container instanceof HTMLElement)) return false;
    var lower = String(value).toLowerCase().trim();
    if (lower !== 'yes' && lower !== 'no') return false;
    var nodes = container.querySelectorAll(
      'label, span, div, button, li, [role="radio"]'
    );
    for (var i = 0; i < nodes.length; i++) {
      var node = nodes[i];
      if (!visible(node)) continue;
      var txt = normalizeBtnText(node);
      if (txt.toLowerCase() !== lower) continue;
      clickChoiceElement(node);
      if (node.htmlFor) {
        var linked = document.getElementById(node.htmlFor);
        if (linked && linked.type === 'radio') clickChoiceElement(linked);
      }
      var nested = node.querySelector('input[type="radio"]');
      if (nested) clickChoiceElement(nested);
      return true;
    }
    return false;
  }

  function applyRadioGroup(el, value) {
    var lower = String(value).toLowerCase().trim();
    var name = el.name;
    var group = [];
    if (name) {
      try {
        group = document.querySelectorAll('input[type="radio"][name="' + CSS.escape(name) + '"]');
      } catch (e) {
        group = document.querySelectorAll(
          'input[type="radio"][name="' + name.replace(/"/g, '') + '"]'
        );
      }
    } else {
      var wrap = el.closest(
        'fieldset, .application-field, .application-question, [class*="field"], [class*="question"], li'
      );
      if (wrap) {
        group = wrap.querySelectorAll('input[type="radio"]');
      } else {
        group = [el];
      }
    }
    for (var i = 0; i < group.length; i++) {
      if (radioChoiceMatchesValue(group[i], lower)) {
        clickChoiceElement(group[i]);
        return true;
      }
    }
    var container = el.closest(
      'fieldset, .application-field, .application-question, [class*="field"], [class*="question"], li'
    );
    return clickYesNoInContainer(container, value);
  }

  function clickChoiceElement(el) {
    if (!(el instanceof HTMLElement)) return;
    try {
      el.focus();
    } catch (eFocus) {
      /* ignore */
    }
    try {
      el.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true }));
      el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
      el.click();
      el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }));
      el.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, cancelable: true }));
      if (el.getAttribute('role') === 'radio') {
        el.setAttribute('aria-checked', 'true');
      }
      if (el.getAttribute('role') === 'button') {
        el.setAttribute('aria-pressed', 'true');
      }
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    } catch (e) {
      try {
        el.click();
      } catch (e2) {
        /* ignore */
      }
    }
  }

  function resolveYesNoContainerForAssignment(assignment) {
    if (!assignment) return null;
    var label = assignment.label_text ? String(assignment.label_text) : '';
    if (!label) return null;
    var wantStem = questionStem(label);
    var wantExact = normalizeLabelKey(label);
    var blocks;
    try {
      blocks = document.querySelectorAll(
        '[data-jaa-control="yes_no_buttons"], [data-jaa-control="role_radio"]'
      );
    } catch (eQuery) {
      return null;
    }
    for (var i = 0; i < blocks.length; i++) {
      var block = blocks[i];
      if (!(block instanceof HTMLElement) || !visible(block)) continue;
      var control = block.getAttribute('data-jaa-control') || '';
      var q =
        control === 'role_radio'
          ? questionPromptFromContainer(block)
          : questionForYesNoContainer(block);
      if (!q) continue;
      if (wantStem && questionStem(q) === wantStem) return block;
      if (wantExact && normalizeLabelKey(q) === wantExact) return block;
      if (isVisaSponsorshipQuestion(label) && isVisaSponsorshipQuestion(q)) return block;
      if (isNycCommuteScreeningLabel(label) && isNycCommuteScreeningLabel(q)) return block;
    }
    return null;
  }

  function applyYesNoButtons(container, value) {
    if (!(container instanceof HTMLElement)) return false;
    var target = String(value).toLowerCase().trim();
    if (target !== 'yes' && target !== 'no') return false;
    var pair = getYesNoPair(container);
    if (pair) {
      var chosen = target === 'yes' ? pair.yes : pair.no;
      if (chosen) {
        clickChoiceElement(chosen);
        return true;
      }
    }
    var selectors =
      'button, [role="button"], [role="radio"], label, [tabindex], [class*="toggle"], [class*="Toggle"]';
    var buttons = container.querySelectorAll(selectors);
    for (var i = 0; i < buttons.length; i++) {
      var b = buttons[i];
      if (!visible(b)) continue;
      if (normalizeYesNoChoiceText(b) === target) {
        clickChoiceElement(b);
        return true;
      }
    }
    var walkNode = container;
    for (var d = 0; d < 4 && walkNode; d++) {
      var sib = walkNode.querySelectorAll(selectors);
      for (var j = 0; j < sib.length; j++) {
        var sb = sib[j];
        if (!visible(sb)) continue;
        if (normalizeYesNoChoiceText(sb) === target) {
          clickChoiceElement(sb);
          return true;
        }
      }
      walkNode = walkNode.parentElement;
    }
    return false;
  }

  function roleRadioMatchesChoice(choiceText, targetValue) {
    var rt = String(choiceText || '').toLowerCase().trim();
    var lower = String(targetValue || '').toLowerCase().trim();
    if (!rt || !lower) return false;
    if (rt === lower || rt.indexOf(lower) >= 0 || lower.indexOf(rt) >= 0) return true;
    if (lower.indexOf('currently live') >= 0 && rt.indexOf('currently live') >= 0) return true;
    if (lower.indexOf('metropolitan') >= 0 && rt.indexOf('metropolitan') >= 0) return true;
    if (lower.indexOf('relocation') >= 0 && rt.indexOf('relocation') >= 0) return true;
    if (lower.indexOf('cannot work') >= 0 && rt.indexOf('cannot work') >= 0) return true;
    return false;
  }

  function applyRoleRadioGroup(container, value) {
    if (!(container instanceof HTMLElement)) return false;
    var radios = container.querySelectorAll('[role="radio"], input[type="radio"]');
    for (var i = 0; i < radios.length; i++) {
      var r = radios[i];
      if (!visible(r)) continue;
      var rt = labelTextFor(r) || normalizeBtnText(r);
      if (roleRadioMatchesChoice(rt, value)) {
        clickChoiceElement(r);
        return true;
      }
    }
    var labels = container.querySelectorAll('label');
    for (var li = 0; li < labels.length; li++) {
      var lab = labels[li];
      if (!visible(lab)) continue;
      if (roleRadioMatchesChoice(normalizeBtnText(lab), value)) {
        clickChoiceElement(lab);
        return true;
      }
    }
    return false;
  }

  function normalizeLabelKey(label) {
    return String(label || '')
      .replace(/\*/g, '')
      .replace(/\s+/g, ' ')
      .trim()
      .toLowerCase();
  }

  /** First sentence ending in ? — stable key for Ashby screening questions. */
  function questionStem(label) {
    var t = normalizeLabelKey(label);
    if (!t) return '';
    var qm = t.match(/^(.+?\?)/);
    if (qm && qm[1]) return qm[1].trim();
    return t.slice(0, 100);
  }

  function findFieldUidForAssignment(assignment, fields) {
    if (assignmentUidStillValid(assignment, fields)) {
      return assignment.field_uid;
    }
    var exact = normalizeLabelKey(assignment.label_text);
    var stem = questionStem(assignment.label_text);
    var screeningYn = isGreenhouseYesNoScreeningAssignment(assignment);
    var dupIdx =
      typeof assignment.duplicate_label_index === 'number'
        ? assignment.duplicate_label_index
        : 0;
    var exactMatches = [];
    var stemMatches = [];
    var locationMatches = [];
    var countryMatches = [];
    var workAuthMatches = [];
    var sponsorshipMatches = [];
    var commuteMatches = [];
    var bestUid = null;
    var bestScore = 0;

    for (var i = 0; i < fields.length; i++) {
      var f = fields[i];
      if (!f || !f.field_uid) continue;
      var fMeta = fieldMetaBlobFromParts(
        f.label_text,
        f.placeholder,
        f.name_attr,
        f.id_attr,
        null
      );
      var fExact = normalizeLabelKey(f.label_text);
      var fStem = questionStem(f.label_text);
      if (isCountryFieldLabel(assignment.label_text)) {
        if (
          isCountryFieldLabel(f.label_text) ||
          isCountryFieldLabel(fMeta) ||
          (/\bcountry\b/i.test(fMeta) && !/\b(city|location\s*\(|phone)\b/i.test(fMeta))
        ) {
          countryMatches.push(f);
        }
      }
      if (assignmentTargetsApplicantLocation(assignment)) {
        if (
          /\blocation\b/i.test(fMeta) &&
          !/learn about|job source|relocation/i.test(fMeta) &&
          (f.input_type === 'combobox' || f.input_type === 'text' || f.input_type === 'search')
        ) {
          locationMatches.push(f);
        }
      }
      if (isWorkAuthorizationQuestion(assignment.label_text)) {
        if (isWorkAuthorizationQuestion(f.label_text) || isWorkAuthorizationQuestion(fMeta)) {
          workAuthMatches.push(f);
        }
      }
      if (isVisaSponsorshipQuestion(assignment.label_text)) {
        if (isVisaSponsorshipQuestion(f.label_text) || isVisaSponsorshipQuestion(fMeta)) {
          sponsorshipMatches.push(f);
        }
      }
      if (
        isNycCommuteScreeningLabel(assignment.label_text) &&
        assignmentValueIsYesNo(assignment.value)
      ) {
        if (
          isRadioLikeInputType(f.input_type) &&
          (isNycCommuteScreeningLabel(f.label_text) ||
            isNycCommuteScreeningLabel(fMeta) ||
            (stem && fStem === stem) ||
            (stem && fExact.indexOf(stem) >= 0))
        ) {
          commuteMatches.push(f);
        }
      }
      if (exact && fExact === exact) exactMatches.push(f);
      if (stem && fStem === stem) stemMatches.push(f);
      if (stem && fExact.indexOf(stem) >= 0) stemMatches.push(f);
      if (stem && fStem && (fStem.indexOf(stem) >= 0 || stem.indexOf(fStem) >= 0)) {
        stemMatches.push(f);
      }
      if (!screeningYn && stem && fExact) {
        var score = 0;
        var words = stem.split(' ').filter(function (w) {
          return w.length > 3;
        });
        for (var wi = 0; wi < words.length; wi++) {
          if (fExact.indexOf(words[wi]) >= 0) score++;
        }
        if (score > bestScore) {
          bestScore = score;
          bestUid = f.field_uid;
        }
      }
    }
    if (countryMatches.length) {
      if (dupIdx >= 0 && dupIdx < countryMatches.length) return countryMatches[dupIdx].field_uid;
      return countryMatches[0].field_uid;
    }
    if (locationMatches.length) {
      if (dupIdx >= 0 && dupIdx < locationMatches.length) return locationMatches[dupIdx].field_uid;
      return locationMatches[0].field_uid;
    }
    if (workAuthMatches.length) {
      if (dupIdx >= 0 && dupIdx < workAuthMatches.length) return workAuthMatches[dupIdx].field_uid;
      return workAuthMatches[0].field_uid;
    }
    if (sponsorshipMatches.length) {
      if (dupIdx >= 0 && dupIdx < sponsorshipMatches.length) {
        return sponsorshipMatches[dupIdx].field_uid;
      }
      return sponsorshipMatches[0].field_uid;
    }
    if (commuteMatches.length) {
      if (dupIdx >= 0 && dupIdx < commuteMatches.length) return commuteMatches[dupIdx].field_uid;
      return commuteMatches[0].field_uid;
    }
    if (exactMatches.length) {
      if (dupIdx >= 0 && dupIdx < exactMatches.length) return exactMatches[dupIdx].field_uid;
      return exactMatches[0].field_uid;
    }
    if (stemMatches.length) {
      if (dupIdx >= 0 && dupIdx < stemMatches.length) return stemMatches[dupIdx].field_uid;
      return stemMatches[0].field_uid;
    }
    if (bestScore >= 3 && bestUid) return bestUid;
    return assignment.field_uid;
  }

  /** Apply work-authorization before visa sponsorship (Greenhouse react-select). */
  function greenhouseScreeningAssignmentRank(assignment) {
    if (!assignment) return 0;
    if (isVisaSponsorshipQuestion(assignment.label_text)) return 2;
    if (isWorkAuthorizationQuestion(assignment.label_text)) return 1;
    return 0;
  }

  function assignmentSortRank(el) {
    if (!(el instanceof HTMLElement)) return 50;
    var control = el.getAttribute('data-jaa-control') || '';
    if (control === 'yes_no_buttons' || control === 'role_radio') return 80;
    if (control === 'combobox') return 20;
    if (control === 'radio') return 80;
    var tag = el.tagName.toLowerCase();
    var inputType = (el.type || '').toLowerCase();
    if (tag === 'input' && inputType === 'file') return 100;
    if (tag === 'input' && inputType === 'radio') return 80;
    return 10;
  }

  function shouldUseYesNoComboboxPath(value, labelText, el) {
    if (!(el instanceof HTMLElement)) return false;
    var isCombo =
      isComboboxInput(el) || el.getAttribute('data-jaa-control') === 'combobox';
    if (!isCombo) return false;
    return (
      isYesNoComboboxValue(value) ||
      isPlusYearsYesNoQuestion(labelText) ||
      isVisaSponsorshipQuestion(labelText) ||
      isWorkAuthorizationQuestion(labelText)
    );
  }

  /**
   * Greenhouse Yes/No react-select: open menu, exact option click, wait before dismiss.
   * @param {HTMLElement} el
   * @param {string} value
   * @param {number} [extraDelayMs]
   * @returns {Promise<boolean>}
   */
  function pickYesNoComboboxOptionEl(options, target) {
    for (var i = 0; i < options.length; i++) {
      if (exactYesNoOptionText(options[i].text) === target) return options[i].el;
    }
    return null;
  }

  function applyYesNoComboboxAsync(el, value, extraDelayMs) {
    var delay = typeof extraDelayMs === 'number' ? extraDelayMs : 420;
    var target = String(value || '').toLowerCase().trim();
    if (target !== 'yes' && target !== 'no') return Promise.resolve(false);

    return new Promise(function (resolve) {
      dismissOpenSelectMenus();
      setTimeout(function () {
        clearComboboxInputValue(el);
        openComboboxMenu(el);
        setTimeout(function () {
          var options = findComboboxOptionsForElement(el);
          var pickedEl = pickYesNoComboboxOptionEl(options, target);
          if (!pickedEl) {
            dismissOpenSelectMenus();
            resolve(false);
            return;
          }
          try {
            pickedEl.scrollIntoView({ block: 'nearest' });
          } catch (eScroll) {
            /* ignore */
          }
          clickChoiceElement(pickedEl);
          try {
            el.focus();
            el.dispatchEvent(
              new KeyboardEvent('keydown', {
                key: 'Enter',
                code: 'Enter',
                keyCode: 13,
                which: 13,
                bubbles: true
              })
            );
            el.dispatchEvent(
              new KeyboardEvent('keyup', {
                key: 'Enter',
                code: 'Enter',
                keyCode: 13,
                which: 13,
                bubbles: true
              })
            );
          } catch (eKey) {
            /* ignore */
          }
          setTimeout(function () {
            var ok = comboboxDisplaysYesNoTarget(el, target);
            dismissOpenSelectMenus();
            if (!ok) {
              closeAllComboboxMenus();
              openComboboxMenu(el);
              setTimeout(function () {
                var retryOpts = findComboboxOptionsForElement(el);
                var retryEl = pickYesNoComboboxOptionEl(retryOpts, target);
                if (retryEl) clickChoiceElement(retryEl);
                setTimeout(function () {
                  dismissOpenSelectMenus();
                  resolve(comboboxDisplaysYesNoTarget(el, target));
                }, delay);
              }, 160);
              return;
            }
            resolve(true);
          }, delay);
        }, 140);
      }, 90);
    });
  }

  /**
   * Greenhouse long-form Yes/acknowledge react-select (work location, consent statements).
   * @param {HTMLElement} el
   * @param {string} value
   * @param {string} labelText
   * @param {number} [extraDelayMs]
   * @returns {Promise<boolean>}
   */
  function applyAcknowledgementComboboxAsync(el, value, labelText, extraDelayMs) {
    var delay = typeof extraDelayMs === 'number' ? extraDelayMs : 550;
    return new Promise(function (resolve) {
      dismissOpenSelectMenus();
      setTimeout(function () {
        openComboboxMenu(el);
        setTimeout(function () {
          var options = findComboboxOptionsForElement(el);
          var pickedEl = pickAcknowledgementComboboxOptionEl(options, value, labelText);
          if (!pickedEl) {
            dismissOpenSelectMenus();
            resolve(false);
            return;
          }
          try {
            pickedEl.scrollIntoView({ block: 'nearest' });
          } catch (eScroll) {
            /* ignore */
          }
          clickChoiceElement(pickedEl);
          setTimeout(function () {
            dismissOpenSelectMenus();
            var shown = comboboxSelectedText(el);
            resolve(acknowledgementComboboxDisplaysTarget(shown, value, labelText));
          }, delay);
        }, 200);
      }, 100);
    });
  }

  function applyComboboxAsync(el, value, extraDelayMs, labelText) {
    var delay = typeof extraDelayMs === 'number' ? extraDelayMs : 300;
    var beforeText = comboboxSelectedText(el);
    var maxAttempts = maxComboboxApplyAttempts(value, labelText);

    function tryOnce(attempt) {
      return new Promise(function (resolve) {
        dismissOpenSelectMenus();
        setTimeout(function () {
          openComboboxMenu(el);
          var prefix = filterPrefixForAttempt(value, labelText, attempt);
          if (prefix) {
            applyComboboxTypeFilter(el, prefix, true);
          } else if (attempt > 0) {
            clearComboboxInputValue(el);
            openComboboxMenu(el);
          }
          var readDelay = prefix ? Math.min(delay, 220) : delay;
          setTimeout(function () {
            var options = findComboboxOptionsForElement(el);
            var pickedEl =
              pickAcknowledgementComboboxOptionEl(options, value, labelText) ||
              tryPickComboboxOptionForTargets(options, value, labelText);
            if (!pickedEl && attempt < maxAttempts - 1) {
              tryOnce(attempt + 1).then(resolve);
              return;
            }
            if (!pickedEl) {
              clearComboboxInputValue(el);
              dismissOpenSelectMenus();
              resolve(false);
              return;
            }
            try {
              pickedEl.scrollIntoView({ block: 'nearest' });
            } catch (eScroll) {
              /* ignore */
            }
            clickChoiceElement(pickedEl);
            setTimeout(function () {
              dismissOpenSelectMenus();
              var shown = comboboxSelectedText(el);
              if (isComboboxFilterStub(shown)) {
                clearComboboxInputValue(el);
                resolve(false);
                return;
              }
              var ok = false;
              var shownAfter = comboboxSelectedText(el);
              if (isAcknowledgementComboboxLabel(labelText)) {
                ok = acknowledgementComboboxDisplaysTarget(shownAfter, value, labelText);
              } else {
                var verifyTargets = isDegreeFieldLabel(labelText)
                  ? degreeTargetValues(value, labelText)
                  : [value];
                for (var vi = 0; vi < verifyTargets.length && !ok; vi++) {
                  if (comboboxShowsValue(el, verifyTargets[vi])) ok = true;
                }
                if (
                  !ok &&
                  (comboboxHasRealSelection(el) ||
                    (shownAfter !== beforeText && !isComboboxFilterStub(shownAfter)))
                ) {
                  ok = true;
                }
              }
              if (!ok && isComboboxFilterStub(comboboxSelectedText(el))) {
                clearComboboxInputValue(el);
              }
              resolve(ok);
            }, 250);
          }, readDelay);
        }, attempt === 0 ? 80 : 160);
      });
    }
    return tryOnce(0);
  }

  /**
   * @param {{ field_uid?: string, label_text?: string, value?: string }} a
   * @returns {Promise<{ field_uid?: string, label_text: string, value: string, ok: boolean, reason: string, control?: string }>}
   */
  function applyOneAssignmentAsync(a) {
    return new Promise(function (resolve) {
      var detail = {
        field_uid: a && a.field_uid,
        label_text: a && a.label_text ? String(a.label_text).slice(0, 200) : '',
        value: a && a.value != null ? String(a.value).slice(0, 120) : '',
        ok: false,
        reason: ''
      };
      if (!a || a.field_uid == null || a.field_uid === '') {
        detail.reason = 'invalid_assignment';
        resolve(detail);
        return;
      }
      detail.field_uid = String(a.field_uid);
      detail.duplicate_label_index =
        typeof a.duplicate_label_index === 'number' ? a.duplicate_label_index : 0;
      if (isEducationDegreeOrDisciplineLabel(a.label_text)) {
        scrollEducationBlockIntoView(detail.duplicate_label_index);
      }
      var el = resolveAssignmentElement(a);
      if (!el) {
        detail.reason = 'element_not_found';
        resolve(detail);
        return;
      }
      try {
        el.scrollIntoView({ block: 'center', behavior: 'instant' });
      } catch (eScroll) {
        try {
          el.scrollIntoView();
        } catch (eScroll2) {
          /* ignore */
        }
      }
      var val = a.value == null ? '' : String(a.value);
      var tag = el.tagName.toLowerCase();
      var inputType = (el.type || '').toLowerCase();
      var control = el.getAttribute('data-jaa-control') || '';
      if (!control && tag === 'input' && isComboboxInput(el)) control = 'combobox';
      detail.control = control || tag + (inputType ? ':' + inputType : '');

      function finish(ok, reason) {
        if (ok) {
          detail.ok = true;
        } else {
          detail.reason = reason || 'apply_failed';
        }
        resolve(detail);
      }

      try {
        if (control === 'yes_no_buttons') {
          var yesOk = applyYesNoButtons(el, val);
          if (!yesOk && a.label_text) {
            var altYn = resolveYesNoContainerForAssignment(a);
            if (altYn && altYn !== el) yesOk = applyYesNoButtons(altYn, val);
          }
          if (!yesOk) {
            var nativeRadio = el.querySelector('input[type="radio"]');
            if (nativeRadio) yesOk = applyRadioGroup(nativeRadio, val);
          }
          if (!yesOk && isVisaSponsorshipQuestion(a.label_text)) {
            var visaYn = findYesNoContainerForVisaSponsorship();
            if (visaYn && visaYn !== el) {
              yesOk =
                applyYesNoButtons(visaYn, val) ||
                applyRadioGroup(visaYn.querySelector('input[type="radio"]') || visaYn, val);
            }
          }
          finish(yesOk, 'yes_no_click_failed');
        } else if (control === 'role_radio') {
          var radioOk = applyRoleRadioGroup(el, val);
          if (!radioOk && isVisaSponsorshipQuestion(a.label_text)) {
            var visaRadio = findYesNoContainerForVisaSponsorship();
            if (visaRadio && visaRadio !== el) radioOk = applyRoleRadioGroup(visaRadio, val);
          }
          if (!radioOk && (val.toLowerCase() === 'yes' || val.toLowerCase() === 'no')) {
            var altRadio = resolveYesNoContainerForAssignment(a);
            if (altRadio) radioOk = applyRoleRadioGroup(altRadio, val) || applyYesNoButtons(altRadio, val);
          }
          finish(radioOk, 'role_radio_click_failed');
        } else if (control === 'combobox' || (tag === 'input' && isComboboxInput(el))) {
          var comboDelay = isEducationDegreeOrDisciplineLabel(a.label_text) ? 450 : 300;
          var preComboDelay = isEducationDegreeOrDisciplineLabel(a.label_text) ? 220 : 0;
          var runCombo = function () {
            var applyFn = applyComboboxAsync;
            var locLabel = a.label_text;
            var args = [el, val, comboDelay, locLabel];
            if (
              isProfileApplicantLocationLabel(locLabel) ||
              elementLooksLikeApplicantLocationField(el)
            ) {
              applyFn = applyLocationCityComboboxAsync;
              args = [el, val, isAshbyHost() ? 700 : 600];
            } else if (isAcknowledgementComboboxLabel(locLabel)) {
              applyFn = applyAcknowledgementComboboxAsync;
              args = [el, val, locLabel, 580];
            } else if (shouldUseYesNoComboboxPath(val, a.label_text, el)) {
              applyFn = applyYesNoComboboxAsync;
              args = [el, val, 450];
            }
            applyFn.apply(null, args).then(function (ok) {
              finish(ok, ok ? '' : 'combobox_match_failed');
            });
          };
          if (preComboDelay > 0) {
            setTimeout(runCombo, preComboDelay);
          } else {
            runCombo();
          }
        } else if (tag === 'select') {
          finish(applySelect(el, val), 'select_match_failed');
        } else if (tag === 'input' && (inputType === 'radio' || control === 'radio')) {
          var nativeRadioOk = applyRadioGroup(el, val);
          if (!nativeRadioOk && isNycCommuteScreeningLabel(a.label_text)) {
            var commuteAlt = resolveYesNoContainerForAssignment(a);
            if (commuteAlt) {
              nativeRadioOk =
                applyRoleRadioGroup(commuteAlt, val) || applyYesNoButtons(commuteAlt, val);
            }
          }
          finish(nativeRadioOk, 'radio_click_failed');
        } else if (tag === 'input' && inputType === 'file') {
          detail.reason = 'file_skipped';
          resolve(detail);
        } else if (tag === 'input' && inputType === 'checkbox') {
          finish(applyCheckbox(el, val), 'checkbox_apply_failed');
        } else {
          setNativeValue(el, val);
          finish(true, '');
        }
      } catch (e) {
        detail.reason = 'exception';
        resolve(detail);
      }
    });
  }

  /**
   * @param {{ field_uid?: string, label_text?: string, value?: string }} a
   * @returns {{ field_uid?: string, label_text: string, value: string, ok: boolean, reason: string, control?: string }}
   */
  function applyOneAssignment(a) {
    var detail = {
      field_uid: a && a.field_uid,
      label_text: a && a.label_text ? String(a.label_text).slice(0, 200) : '',
      value: a && a.value != null ? String(a.value).slice(0, 120) : '',
      ok: false,
      reason: ''
    };
    if (!a || a.field_uid == null || a.field_uid === '') {
      detail.reason = 'invalid_assignment';
      return detail;
    }
    detail.field_uid = String(a.field_uid);
    var el = resolveAssignmentElement(a);
    if (!el) {
      detail.reason = 'element_not_found';
      return detail;
    }
    var val = a.value == null ? '' : String(a.value);
    var tag = el.tagName.toLowerCase();
    var inputType = (el.type || '').toLowerCase();
    var control = el.getAttribute('data-jaa-control') || '';
    if (!control && tag === 'input' && isComboboxInput(el)) control = 'combobox';
    detail.control = control || tag + (inputType ? ':' + inputType : '');
    try {
      var ok = false;
      if (control === 'yes_no_buttons') {
        ok = applyYesNoButtons(el, val);
        if (!ok) detail.reason = 'yes_no_click_failed';
      } else if (control === 'role_radio') {
        ok = applyRoleRadioGroup(el, val);
        if (!ok) detail.reason = 'role_radio_click_failed';
      } else if (control === 'combobox' || (tag === 'input' && isComboboxInput(el))) {
        ok = applyCombobox(el, val);
        if (!ok) detail.reason = 'combobox_match_failed';
      } else if (tag === 'select') {
        ok = applySelect(el, val);
        if (!ok) detail.reason = 'select_match_failed';
      } else if (tag === 'input' && (inputType === 'radio' || control === 'radio')) {
        ok = applyRadioGroup(el, val);
        if (!ok) detail.reason = 'radio_click_failed';
      } else if (tag === 'input' && inputType === 'file') {
        detail.reason = 'file_skipped';
      } else if (tag === 'input' && inputType === 'checkbox') {
        ok = applyCheckbox(el, val);
        if (!ok) detail.reason = 'checkbox_apply_failed';
      } else {
        setNativeValue(el, val);
        ok = true;
      }
      if (ok) detail.ok = true;
      else if (!detail.reason) detail.reason = 'apply_failed';
    } catch (e) {
      detail.reason = 'exception';
    }
    return detail;
  }

  /**
   * @param {Array<{ field_uid: string, value: string, label_text?: string }>} assignments
   * @returns {{ applied: number, failed: number, details: Array }}
   */
  function applyAssignments(assignments) {
    var applied = 0;
    var failed = 0;
    var details = [];
    if (!Array.isArray(assignments)) return { applied: 0, failed: 0, details: details };

    for (var i = 0; i < assignments.length; i++) {
      var detail = applyOneAssignment(assignments[i]);
      details.push(detail);
      if (detail.ok) applied++;
      else failed++;
    }
    return { applied: applied, failed: failed, details: details };
  }

  /**
   * Apply with short delays between combobox fields (Greenhouse listbox mount).
   * @param {Array<{ field_uid: string, value: string, label_text?: string }>} assignments
   * @returns {Promise<{ applied: number, failed: number, details: Array }>}
   */
  function applyAssignmentsAsync(assignments) {
    if (!Array.isArray(assignments) || !assignments.length) {
      return Promise.resolve({ applied: 0, failed: 0, details: [] });
    }
    var applied = 0;
    var failed = 0;
    var details = [];
    var chain = Promise.resolve();
    for (var i = 0; i < assignments.length; i++) {
      (function (a) {
        chain = chain.then(function () {
          return applyOneAssignmentAsync(a);
        }).then(function (detail) {
          details.push(detail);
          if (detail.ok) applied++;
          else failed++;
        });
      })(assignments[i]);
    }
    return chain.then(function () {
      return { applied: applied, failed: failed, details: details };
    });
  }

  function applyAssignmentsWithRematchBody(assignments, fresh) {
    var fields = fresh.fields || [];
    var remapped = [];
    var rematchLog = [];

    for (var ai = 0; ai < assignments.length; ai++) {
      var a = assignments[ai];
      if (!a) continue;
      var fromUid = a.field_uid;
      var toUid = findFieldUidForAssignment(a, fields);
      rematchLog.push({
        label_text: a.label_text || '',
        from_uid: fromUid,
        to_uid: toUid,
        rematched: String(fromUid) !== String(toUid)
      });
      remapped.push({
        field_uid: toUid,
        value: a.value,
        label_text: a.label_text,
        duplicate_label_index:
          typeof a.duplicate_label_index === 'number' ? a.duplicate_label_index : 0
      });
    }
    remapped.sort(function (x, y) {
      var eduX = educationAssignmentSortRank(x);
      var eduY = educationAssignmentSortRank(y);
      if (eduX !== eduY) return eduX - eduY;
      var ghX = greenhouseScreeningAssignmentRank(x);
      var ghY = greenhouseScreeningAssignmentRank(y);
      if (ghX !== ghY) return ghX - ghY;
      var ex = resolveAssignmentElement(x);
      var ey = resolveAssignmentElement(y);
      return assignmentSortRank(ex) - assignmentSortRank(ey);
    });
    var debug = {
      page_url: fresh.page_url,
      scanned_field_count: fields.length,
      scanned_fields: fields.map(function (f) {
        return {
          field_uid: f.field_uid,
          input_type: f.input_type,
          required: !!f.required,
          label_text: String(f.label_text || '').slice(0, 220)
        };
      }),
      rematch: rematchLog,
      apply: []
    };
    return { remapped: remapped, debug: debug };
  }

  function finishRematchResult(result, debug) {
    dismissOpenSelectMenus();
    debug.apply = result.details || [];
    try {
      window.__jaaLastAutofillDebug = debug;
    } catch (eDbg) {
      /* ignore */
    }
    result.debug = debug;
    return result;
  }

  function applyAssignmentsWithRematchBodySync(assignments, fresh) {
    var prep = applyAssignmentsWithRematchBody(assignments, fresh);
    var out = applyAssignments(prep.remapped);
    return finishRematchResult(out, prep.debug);
  }

  function applyAssignmentsWithRematchBodyAsync(assignments, fresh) {
    var prep = applyAssignmentsWithRematchBody(assignments, fresh);
    var sorted = prep.remapped.slice().sort(function (x, y) {
      var eduX = educationAssignmentSortRank(x);
      var eduY = educationAssignmentSortRank(y);
      if (eduX !== eduY) return eduX - eduY;
      var ghX = greenhouseScreeningAssignmentRank(x);
      var ghY = greenhouseScreeningAssignmentRank(y);
      if (ghX !== ghY) return ghX - ghY;
      var ex = resolveAssignmentElement(x);
      var ey = resolveAssignmentElement(y);
      return assignmentSortRank(ex) - assignmentSortRank(ey);
    });
    return applyAssignmentsAsync(sorted).then(function (out) {
      return finishRematchResult(out, prep.debug);
    });
  }

  /**
   * Re-scan the DOM and match assignments by label so stale data-jaa-fid ids still apply.
   * @param {Array<{ field_uid: string, value: string, label_text?: string }>} assignments
   * @returns {{ applied: number, failed: number, details: Array, debug: object|null }}
   */
  function applyAssignmentsWithRematch(assignments) {
    if (!Array.isArray(assignments) || !assignments.length) {
      return { applied: 0, failed: 0, details: [], debug: null };
    }
    clearPreviousMarkers();
    scrollAllScrollableContainers(1);
    var fresh = serializeCollectOnly([]);
    return applyAssignmentsWithRematchBodySync(assignments, fresh);
  }

  /**
   * Deep-scroll then apply (Ashby lazy-mounted screening questions).
   * @param {Array<{ field_uid: string, value: string, label_text?: string }>} assignments
   * @returns {Promise<{ applied: number, failed: number, details: Array, debug: object|null }>}
   */
  function applyAssignmentsWithRematchAsync(assignments, educationExpandCount) {
    if (!Array.isArray(assignments) || !assignments.length) {
      return Promise.resolve({ applied: 0, failed: 0, details: [], debug: null });
    }
    if (!needsDeepScrollSerialize()) {
      clearPreviousMarkers();
      scrollToRevealFormFields();
      return Promise.resolve(applyAssignmentsWithRematchBodySync(assignments, serializeCollectOnly([])));
    }
    if (isAshbyHost()) {
      restoreAshbyOverhiddenSections();
      suppressAshbyResumeAutofillUI();
    }
    var expandCount =
      typeof educationExpandCount === 'number' ? educationExpandCount : 0;
    return revealAllFormContentAsync().then(function () {
      scrollToTopForApply();
      var expandChain =
        expandCount > 1
          ? expandEducationRowsAsync(expandCount)
          : Promise.resolve({ clicked: 0, needed: 0 });
      return expandChain.then(function () {
        clearPreviousMarkers();
        var fresh = serializeCollectOnly([]);
        return applyAssignmentsWithRematchBodyAsync(assignments, fresh);
      });
    });
  }

  /**
   * Run serialize only — for manual debugging in DevTools.
   * @returns {Promise<{ fields: Array, page_url: string, warnings: string[] }>}
   */
  function debugScanFields() {
    return serializeAsync();
  }

  function scrollEducationSectionIntoView() {
    var nodes;
    try {
      nodes = document.querySelectorAll('h1, h2, h3, h4, h5, h6, label, legend, p, span, div');
    } catch (e) {
      return;
    }
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      if (!(n instanceof HTMLElement)) continue;
      var t = normalizeBtnText(n).toLowerCase();
      if (t === 'education' || t.indexOf('education') === 0) {
        try {
          n.scrollIntoView({ block: 'center', behavior: 'instant' });
        } catch (eScroll) {
          try {
            n.scrollIntoView();
          } catch (eScroll2) {
            /* ignore */
          }
        }
        return;
      }
    }
    scrollAllScrollableContainers(0.45);
  }

  function findEducationAddAnotherLink() {
    var links;
    try {
      links = document.querySelectorAll('a, button, [role="button"]');
    } catch (e) {
      return null;
    }
    for (var i = 0; i < links.length; i++) {
      var link = links[i];
      if (!(link instanceof HTMLElement)) continue;
      var t = normalizeBtnText(link).toLowerCase();
      if (t !== 'add another' && t.indexOf('add another') < 0) continue;
      var node = link;
      for (var d = 0; d < 14 && node; d++) {
        var blob = containerText(node, 700).toLowerCase();
        if (
          blob.indexOf('degree') >= 0 ||
          blob.indexOf('discipline') >= 0 ||
          blob.indexOf('education') >= 0 ||
          blob.indexOf('school') >= 0
        ) {
          return link;
        }
        node = node.parentElement;
      }
    }
    return null;
  }

  /**
   * Click Greenhouse "Add another" until enough education rows exist.
   * @param {number} targetCount
   * @returns {{ clicked: number, needed: number }}
   */
  function expandEducationRows(targetCount) {
    var existing = countExistingEducationRows();
    var need = Math.max(0, (targetCount || 0) - existing);
    var clicked = 0;
    if (!need) return { clicked: 0, needed: 0, existing: existing };

    scrollEducationSectionIntoView();
    for (var round = 0; round < need * 3 && clicked < need; round++) {
      var link = findEducationAddAnotherLink();
      if (!link) break;
      try {
        link.scrollIntoView({ block: 'center', behavior: 'instant' });
      } catch (eSv) {
        try {
          link.scrollIntoView();
        } catch (eSv2) {
          /* ignore */
        }
      }
      clickChoiceElement(link);
      clicked++;
    }
    return { clicked: clicked, needed: need, existing: existing };
  }

  /**
   * Async expand with pauses so Greenhouse can mount new Degree/Discipline rows.
   * @param {number} targetCount
   * @returns {Promise<{ clicked: number, needed: number, existing: number }>}
   */
  function expandEducationRowsAsync(targetCount) {
    var existing = countExistingEducationRows();
    var need = Math.max(0, (targetCount || 0) - existing);
    if (!need) return Promise.resolve({ clicked: 0, needed: 0, existing: existing });

    var clicked = 0;
    var chain = Promise.resolve();
    for (var n = 0; n < need; n++) {
      chain = chain
        .then(function () {
          scrollEducationSectionIntoView();
          return new Promise(function (resolve) {
            setTimeout(resolve, 280);
          });
        })
        .then(function () {
          var link = findEducationAddAnotherLink();
          if (link) {
            try {
              link.scrollIntoView({ block: 'center', behavior: 'instant' });
            } catch (eSv) {
              try {
                link.scrollIntoView();
              } catch (eSv2) {
                /* ignore */
              }
            }
            clickChoiceElement(link);
            clicked++;
          }
          return new Promise(function (resolve) {
            setTimeout(resolve, 450);
          });
        });
    }
    return chain.then(function () {
      return { clicked: clicked, needed: need, existing: existing };
    });
  }

  function dispatchFileInputEvents(inp) {
    if (!(inp instanceof HTMLElement)) return;
    try {
      inp.focus();
    } catch (eFocus) {
      /* ignore */
    }
    try {
      inp.dispatchEvent(
        new InputEvent('input', { bubbles: true, cancelable: true, composed: true })
      );
    } catch (eInput) {
      try {
        inp.dispatchEvent(new Event('input', { bubbles: true }));
      } catch (eInput2) {
        /* ignore */
      }
    }
    try {
      inp.dispatchEvent(new Event('change', { bubbles: true }));
    } catch (eChange) {
      /* ignore */
    }
  }

  /**
   * Ashby shows a red toast when their cloud upload API fails after we set the file input.
   * @returns {boolean}
   */
  function ashbyResumeUploadFailed() {
    if (!isAshbyHost()) return false;
    var text = '';
    try {
      text = (document.body && document.body.innerText) || '';
    } catch (eBody) {
      return false;
    }
    return /failed to upload/i.test(text);
  }

  /**
   * Attach resume bytes to resume/CV file inputs (including hidden Greenhouse inputs).
   * @param {{ base64: string, filename: string, mimeType: string }} payload
   * @returns {{ attached: number, ashby_upload_failed?: boolean }}
   */
  function attachResumeFile(payload) {
    var attached = 0;
    if (!payload || !payload.base64) return { attached: 0 };
    var binary;
    try {
      binary = atob(payload.base64);
    } catch (e) {
      return { attached: 0 };
    }
    var bytes = new Uint8Array(binary.length);
    for (var i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    var file;
    try {
      file = new File([bytes], payload.filename || 'resume.pdf', {
        type: payload.mimeType || 'application/pdf'
      });
    } catch (e2) {
      return { attached: 0 };
    }
    var inputs;
    try {
      inputs = document.querySelectorAll('input[type="file"]');
    } catch (e3) {
      return { attached: 0 };
    }
    var bestInp = null;
    var bestScore = 49;
    for (var j = 0; j < inputs.length; j++) {
      var cand = inputs[j];
      if (isAshbyHost() && isAshbyResumeAutofillInput(cand)) continue;
      var sc = resumeFileInputScore(cand);
      if (sc > bestScore) {
        bestScore = sc;
        bestInp = cand;
      }
    }
    if (bestInp) {
      try {
        bestInp.scrollIntoView({ block: 'center', behavior: 'instant' });
      } catch (eScroll) {
        try {
          bestInp.scrollIntoView();
        } catch (eScroll2) {
          /* ignore */
        }
      }
      try {
        var dt = new DataTransfer();
        dt.items.add(file);
        bestInp.files = dt.files;
        dispatchFileInputEvents(bestInp);
        attached = 1;
        if (isAshbyHost()) {
          suppressAshbyResumeAutofillUI();
        }
      } catch (e4) {
        /* ignore */
      }
    }
    var out = { attached: attached };
    if (isAshbyHost() && attached > 0) {
      out.ashby_upload_failed = ashbyResumeUploadFailed();
    }
    return out;
  }

  window.__jaaSerializeAutofillFields = serialize;
  window.__jaaSerializeAutofillFieldsAsync = serializeAsync;
  window.__jaaApplyAutofillAssignments = applyAssignments;
  window.__jaaApplyAutofillWithRematch = applyAssignmentsWithRematchAsync;
  window.__jaaApplyAutofillWithRematchSync = applyAssignmentsWithRematch;
  window.__jaaDebugScanAutofillFields = debugScanFields;
  /** In DevTools on the application tab: `copy(JSON.stringify(__jaaLastScanDebug, null, 2))` */
  window.__jaaLastScanDebug = null;
  window.__jaaAttachResumeFile = attachResumeFile;
  window.__jaaAshbyResumeUploadFailed = ashbyResumeUploadFailed;
  window.__jaaSuppressAshbyResumeAutofill = suppressAshbyResumeAutofillUI;
  window.__jaaRestoreAshbyOverhidden = restoreAshbyOverhiddenSections;
  window.__jaaExpandEducationRows = expandEducationRows;
  window.decodeHtmlEntities = decodeHtmlEntities;
})();
