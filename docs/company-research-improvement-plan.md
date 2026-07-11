# Company Research Improvement — Agent Execution Spec

**Status:** Implemented on branch `feat/company-research-disambiguation`  
**Owner:** Engineering  
**Last updated:** 2026-07-08  

This document is the **single source of truth** for fixing wrong-company research in ApplyPilot. An agent (or developer) should execute phases **in order**, run the listed tests after each phase, and not ship until the Pre-Ship Checklist is complete.

---

## 0. Agent instructions (read first)

### 0.1 Goal

Ensure **Company Research** describes the employer **for this specific job posting**, not a different company with the same name. Warn users when confidence is low.

### 0.2 Non-negotiables (from `.cursorrules`)

- Never raise bare `HTTPException` — use `APIError` / helpers from `utils/error_responses.py`
- All `run_in_executor` LLM calls wrapped in `asyncio.wait_for()`
- `thinking_budget=0` in every `GenerateContentConfig`
- Never fetch user-supplied URLs server-side (SSRF) — **parse hostname/slug only**
- Never add inline `style=` in templates; use CSS classes + nonce on `<style>` blocks
- Never use native `confirm()` / `alert()` in JS
- Integration tests live in `tests/test_api/`; agent unit tests in `tests/test_agents/`
- After bulk Python edits, validate with `ast.parse()` on touched files

### 0.3 Rules to read before coding

| Area | File |
|------|------|
| Core / workflow failure | `.cursor/rules/applypilot-core.mdc` |
| Agents | `.cursor/rules/agent-patterns.mdc` |
| LLM / grounding | `.cursor/rules/llm-integration.mdc` |
| Cache | `.cursor/rules/caching-redis.mdc` |
| Company tab UI | `.cursor/rules/ui-application-detail.mdc` |
| Frontend JS | `.cursor/rules/frontend-js-strict.mdc` |
| Unit tests | `.cursor/rules/unit-testing.mdc` |

### 0.4 Current broken behavior (baseline)

**File:** `agents/company_research.py`

When `job_analysis.company_name` is usable, research calls:

```python
prompt = COMPANY_RESEARCH_PROMPT.format(company_name=company_name)
```

No job context, no URL domain, no disambiguation. Cache key is **name-only** (`utils/cache.py` → `_get_company_research_cache_key`).

### 0.5 Implementation map (all 7 items)

| ID | Item | Phase |
|----|------|-------|
| **#1** | Job posting context in every research prompt | 1 |
| **#2** | Job URL / ATS domain hints (parse only) | 1 |
| **#3** | Disambiguation pre-step (resolve employer before research) | 3 |
| **#4** | Better `company_name` extraction in job analyzer | 2 |
| **#5** | Context-aware cache keys + skip generic names | 1 |
| **#6** | Google Search grounding (feature-flagged) | 4 |
| **#7** | UI warning for LOW confidence / uncertain research | 5 |

**Dependency rule:** Do **not** enable #6 in production until #1, #2, #3, and #5 are merged. #7 is most useful after #3.

### 0.6 Execution order

```
Phase 0 (prep) → Phase 1 (#1,#2,#5) → Phase 2 (#4) → Phase 3 (#3) → Phase 5 (#7) → Phase 4 (#6)
```

Phase 4 (#6) is **last** intentionally (cost + needs rails).

---

## 1. Phase 0 — Prep (0.5 day)

### 1.1 Tasks

- [ ] Create branch: `feat/company-research-disambiguation`
- [ ] Skim failing examples (if any) from product/QA; tag each as:
  - `wrong_name` — analyzer stored wrong string
  - `same_name_diff_company` — two employers, one name
  - `confident_but_wrong` — HIGH confidence, wrong facts
  - `staffing_agency` — recruiter listed as employer
- [ ] Confirm default model: `config/settings.py` → `gemini_model = "gemini-3.5-flash"`

### 1.2 No code required

Document findings in PR description; optional appendix in this file.

---

## 2. Phase 1 — Foundation (#1, #2, #5)

**Estimated effort:** 2 days  
**Shippable alone:** Yes (recommended first PR)

### 2.1 New module: `utils/employer_disambiguation.py`

Create pure functions (no LLM, fully unit-testable):

```python
@dataclass
class EmployerUrlSignals:
    hostname: str
    registrable_domain: str  # e.g. acme.com
    ats_platform: Optional[str]  # lever | greenhouse | workday | icims | ashby | unknown
    ats_slug: Optional[str]    # e.g. acme from jobs.lever.co/acme
    is_job_board_host: bool    # True for generic boards where hostname ≠ employer

def parse_job_url_signals(job_url: Optional[str]) -> Optional[EmployerUrlSignals]: ...

def build_primary_location(job_analysis: Dict[str, Any]) -> str:
    """city, state, country + additional_locations excerpt."""

def is_generic_company_name(name: str) -> bool:
    """
    True for short names (<=8 chars after strip), blocklist tokens
    (Atlas, Summit, Meridian, Apex, Nova, …), or single common word.
    """

def build_company_research_cache_disambiguators(
    company_name: str,
    job_analysis: Dict[str, Any],
    job_input_data: Dict[str, Any],
) -> Dict[str, str]:
    """
    Returns stable key parts: normalized_name, url_domain, industry, primary_location.
    Used by cache key builder.
    """
```

**ATS hostname patterns (minimum):**

| Platform | Host pattern | Slug extraction |
|----------|--------------|-----------------|
| Lever | `jobs.lever.co` | first path segment |
| Greenhouse | `boards.greenhouse.io` | first path segment |
| Workday | `*.myworkdayjobs.com` | first path segment after locale if present |
| Ashby | `jobs.ashbyhq.com` | first path segment |

**Do not HTTP-fetch URLs.** Parse with `urllib.parse.urlparse` only. Reject non-`http(s)`.

### 2.2 Update `agents/company_research.py`

#### 2.2.1 Replace context formatter

Rename `_format_job_context_for_unnamed_employer` → `_format_job_context_for_research(job_analysis, job_input_data)`:

Include (truncate long fields):

- `job_title`, primary location, `additional_locations` (first 3)
- `industry`, `role_classification`, `company_size` (from posting)
- `team_info`, `reporting_to`
- `responsibilities` (first 15 bullets, 500 chars each)
- `required_skills` + `keywords` (first 20)
- `employer_url_signals` summary from #2

#### 2.2.2 New prompt prefix (named + unnamed)

Add constant `COMPANY_RESEARCH_DISAMBIGUATION_RULES`:

```
### DISAMBIGUATION RULES (mandatory)
- Research the employer FOR THIS JOB POSTING only.
- Cross-check: industry, location, and products in your answer MUST align with JOB CONTEXT below.
- If JOB CONTEXT contradicts your knowledge of the named company, set confidence_assessment.overall_confidence to LOW
  and explain the mismatch in uncertain_areas.
- Do NOT substitute a famous namesake company.
- Do NOT invent company names, websites, or leadership not supported by JOB CONTEXT or verified knowledge.
```

For **named** companies, build prompt as:

```
{COMPANY_RESEARCH_DISAMBIGUATION_RULES}

### EMPLOYER NAME (from job analysis)
{company_name}

### JOB CONTEXT
{formatted_context}

### POSTING URL SIGNALS
{url_signals_block or "Not available"}

---

{COMPANY_RESEARCH_PROMPT.format(company_name=company_name)}
```

Unnamed path keeps existing `EMPLOYER NOT NAMED IN POSTING` block + same JOB CONTEXT.

#### 2.2.3 Wire `process()` to pass context

Update `_research_company_with_llm` signature:

```python
async def _research_company_with_llm(
    self,
    company_name: str,
    *,
    job_analysis: Optional[Dict[str, Any]] = None,
    job_input_data: Optional[Dict[str, Any]] = None,
    unnamed_job_analysis: Optional[Dict[str, Any]] = None,  # keep for compat; prefer job_analysis
) -> CompanyResearchResult:
```

In `process()`:

- Read `job_input_data = state.get("job_input_data") or {}`
- Pass both `job_analysis` and `job_input_data` on **every** research path (cache miss and hit skip LLM)

### 2.3 Update `utils/cache.py` (#5)

#### 2.3.1 New cache key function

Replace name-only key with:

```python
def _get_company_research_cache_key(
    company_name: str,
    *,
    disambiguators: Optional[Dict[str, str]] = None,
) -> str:
```

Key material: `normalized_name | url_domain | industry | primary_location` (lowercase, stripped), then `generate_hash`.

Update signatures:

```python
async def get_cached_company_research(company_name: str, *, disambiguators: Optional[Dict[str, str]] = None) -> ...
async def cache_company_research(company_name: str, research: Dict[str, Any], *, disambiguators: Optional[Dict[str, str]] = None) -> ...
async def invalidate_company_research(company_name: str, *, disambiguators: Optional[Dict[str, str]] = None) -> ...
```

#### 2.3.2 Skip cache for generic names

In `CompanyResearchAgent.process()`:

```python
from utils.employer_disambiguation import (
    build_company_research_cache_disambiguators,
    is_generic_company_name,
)

disambiguators = build_company_research_cache_disambiguators(
    company_name, job_analysis, job_input_data
)
skip_cache = is_generic_company_name(company_name) and not disambiguators.get("url_domain")
```

If `skip_cache`: bypass `get_cached_company_research` / `cache_company_research` (still use compute lock keyed on full disambiguator hash).

#### 2.3.3 Cache version

Bump `CACHE_VERSION` in settings/env **or** change prefix to `company_research_v2` in `CACHE_PREFIX_COMPANY_RESEARCH` so stale wrong entries are not served.

Document in PR: deploy flushes old company research cache entries.

### 2.4 Phase 1 tests

**New file:** `tests/test_utils/test_employer_disambiguation.py`

| Test | Assert |
|------|--------|
| `test_lever_url_extracts_slug` | `jobs.lever.co/notion` → slug `notion` |
| `test_workday_url_extracts_slug` | `acme.wd5.myworkdayjobs.com/en-US/acme/job/...` → slug `acme` |
| `test_invalid_url_returns_none` | `javascript:alert(1)` → None |
| `test_generic_name_atlas` | `is_generic_company_name("Atlas")` is True |
| `test_specific_name_datadog` | `is_generic_company_name("Datadog")` is False |
| `test_cache_disambiguators_differ_by_domain` | Same "Acme", different domains → different dicts |

**Update:** `tests/test_agents/test_company_research.py`

- Assert mock `gemini_client.generate` prompt contains `JOB CONTEXT` and job title for named company path
- Assert two process calls with same name, different `job_url` in state → `cache_company_research` called with different disambiguators (mock side_effect capture)

**Update:** `tests/test_utils/test_cache.py`

- `_get_company_research_cache_key` differs when disambiguators differ

**Run:**

```bash
pytest tests/test_utils/test_employer_disambiguation.py tests/test_utils/test_cache.py \
       tests/test_agents/test_company_research.py -v
```

### 2.5 Phase 1 acceptance criteria

- [ ] Named-company research prompt includes job title, industry, location, responsibilities excerpt
- [ ] Posting URL hostname/slug appears in prompt when `job_input_data.job_url` is set
- [ ] Two jobs with same `company_name` but different URL domains do **not** share cache
- [ ] Generic name without URL domain skips cache
- [ ] All Phase 1 tests pass
- [ ] No SSRF: grep confirms no `httpx`/`requests` fetch of `job_url` in new code

---

## 3. Phase 2 — Job analyzer (#4)

**Estimated effort:** 1.5 days  
**Depends on:** Phase 1 merged (optional but recommended)

### 3.1 Prompt changes — `agents/job_analyzer.py`

Extend `JOB_ANALYSIS_PROMPT` extraction rules:

```
11. company_name — prefer the ACTUAL HIRING EMPLOYER:
    - Use legal entity / careers branding in posting body, not the ATS vendor (Greenhouse, Lever, Workday).
    - If posted by a staffing agency "on behalf of" a client and client is unnamed → company_name: null.
    - If both agency and client named → use the CLIENT, not the agency.
    - Product/division names (Instagram, YouTube) → prefer parent legal entity when footer says so.
    - Never use job board site name as company_name.
12. employer_type: "direct" | "staffing_agency" | "confidential" | null if unclear.
13. company_name_confidence: "HIGH" | "MEDIUM" | "LOW" — LOW when name is generic or ambiguous.
```

Add fields to JSON schema in prompt (nullable).

### 3.2 Schema — `workflows/state_schema.py`

Add optional fields on `JobAnalysisResult`:

```python
employer_type: Optional[str] = None  # direct | staffing_agency | confidential
company_name_confidence: Optional[str] = None  # HIGH | MEDIUM | LOW
```

Update `_map_parsed_to_result` (or equivalent) in `job_analyzer.py` to read these fields. Validate allowed enum values; invalid → None.

**Do not break API clients:** fields are additive.

### 3.3 Company research integration

In `company_research.py` `process()`:

- If `employer_type == "staffing_agency"` OR `company_name_confidence == "LOW"` with generic name → treat like weak name (extra disambiguation rules in prompt; consider forcing LOW cap in Phase 3)
- If `employer_type == "confidential"` and name empty → unnamed path

### 3.4 Phase 2 tests

**Update:** `tests/test_agents/test_job_analyzer.py`

Add mocked LLM fixtures (JSON strings) for:

| Fixture ID | Input snippet | Expected |
|------------|---------------|----------|
| JA-01 | "Randstad is hiring for our client…" | `company_name` null, `employer_type` staffing_agency |
| JA-02 | "Hired partners with Notion…" | `company_name` "Notion" |
| JA-03 | Greenhouse header, Stripe in body | `company_name` "Stripe" |
| JA-04 | Stealth startup, no legal name | `company_name` null, `employer_type` confidential |

**Run:**

```bash
pytest tests/test_agents/test_job_analyzer.py -v
```

### 3.5 Phase 2 acceptance criteria

- [ ] Staffing posts no longer store agency as `company_name` when client unnamed
- [ ] New fields persisted in `workflow_sessions.job_analysis` JSONB (no migration needed)
- [ ] Company research receives improved names on subsequent runs
- [ ] All job analyzer tests pass

---

## 4. Phase 3 — Disambiguation step (#3)

**Estimated effort:** 1.5 days  
**Depends on:** Phase 1

### 4.1 New prompt — `agents/company_research.py`

Add `EMPLOYER_DISAMBIGUATION_PROMPT` — small JSON-only response:

```json
{
  "resolved_company_name": "<best employer name for THIS posting or null>",
  "confidence": "HIGH | MEDIUM | LOW",
  "employer_type": "direct | staffing_agency | confidential | unknown",
  "disambiguation_signals": ["<signal 1>", "<signal 2>"],
  "rejected_matches": ["<wrong famous company rejected because...>"],
  "notes": "<one sentence>"
}
```

Call via `gemini_client.generate()` **before** main research when:

- Always for generic names, OR
- `company_name_confidence` is LOW/MEDIUM, OR
- `employer_type` is staffing_agency

For HIGH confidence + specific name + strong URL domain → skip Step A (config flag `COMPANY_RESEARCH_SKIP_DISAMBIGuation_when_high_confidence=true` default True).

### 4.2 Schema — `CompanyResearchResult`

Add optional fields in `workflows/state_schema.py`:

```python
resolved_company_name: Optional[str] = None
employer_type: Optional[str] = None
disambiguation_notes: Optional[str] = None
research_quality: Optional[str] = None  # verified | uncertain | posting_only
```

Set `research_quality`:

| Condition | Value |
|-----------|-------|
| Unnamed employer path | `posting_only` |
| Step A confidence LOW OR main `confidence_assessment.overall_confidence` LOW | `uncertain` |
| Otherwise | `verified` |

**Cap rule:** If Step A confidence is LOW, force final `confidence_assessment.overall_confidence` to LOW even if Step B says HIGH.

### 4.3 Phase 3 tests

**Update:** `tests/test_agents/test_company_research.py`

- Mock two sequential `generate` calls (disambiguation + research)
- Generic "Meridian" + healthcare context → Step A returns LOW, final confidence LOW
- Specific "Datadog" + matching URL → Step A skipped or HIGH

**New:** `tests/fixtures/company_research_disambiguation.json` — frozen inputs/outputs for golden tests

**Run:**

```bash
pytest tests/test_agents/test_company_research.py -v -k disambiguation
```

### 4.4 Phase 3 acceptance criteria

- [ ] Ambiguous names trigger disambiguation step
- [ ] `research_quality` and `resolved_company_name` stored in `company_research` JSONB
- [ ] LOW confidence cannot be overridden to HIGH by main research alone
- [ ] Tests pass

---

## 5. Phase 5 — UI warning (#7)

**Estimated effort:** 1.5 days  
**Depends on:** Phase 3 (for reliable `research_quality` / LOW flags)

> **Note:** Phase number 5 in doc = UI phase; implement **before** Phase 4 (#6 grounding).

### 5.1 Backend

No new endpoint required — fields already in `company_research` JSON returned by applications API.

Ensure `research_quality` and `confidence_assessment.overall_confidence` are included in API responses (they flow via existing JSONB serialization).

### 5.2 Frontend — `ui/src/application-detail/`

In `renderMainContent()` company tab block (~line 560), **before** company stats card:

```javascript
const researchQuality = (company.research_quality || '').toLowerCase();
const confidenceOverall = (company.confidence_assessment?.overall_confidence || '').toUpperCase();
const showUncertaintyBanner =
    researchQuality === 'uncertain' ||
    confidenceOverall === 'LOW' ||
    researchQuality === 'posting_only';
```

Render banner (use existing alert pattern, no inline styles):

```html
<div class="company-research-notice company-research-notice--uncertain" role="status">
  <i class="fas fa-info-circle" aria-hidden="true"></i>
  <div>
    <strong>Company research may not match this employer.</strong>
    <span>Details are based on the job posting where needed. Verify before interviews.</span>
  </div>
</div>
```

Variant for `posting_only`: softer copy — "Employer not named in posting; guidance is tailored to this role."

### 5.3 CSS — `ui/templates/application.html`

Add nonce-gated styles:

```css
.company-research-notice { ... }  /* amber/info border, flex row */
.company-research-notice--posting-only { ... }  /* info, not warning */
.company-research-notice.is-hidden { display: none; }
```

**No `style=` attributes.** Run `make build-frontend` after JS/CSS changes.

### 5.4 Phase 5 tests

**Agent unit:** N/A for JS (unless adding small extractable helper)

**Manual / E2E (optional):** `e2e/application-detail.spec.js`

- Mock API: `company_research.research_quality: "uncertain"` → banner visible
- Mock API: `research_quality: "verified"`, confidence HIGH → banner hidden

**Run frontend build:**

```bash
make build-frontend
```

### 5.5 Phase 5 acceptance criteria

- [ ] LOW confidence shows visible banner on Company tab
- [ ] Unnamed/confidential shows informational banner (not error styling)
- [ ] Banner uses `escapeHtml` / `decodeEntities` correctly
- [ ] WCAG: banner has `role="status"`, visible text (not icon-only)
- [ ] CSP: no inline styles in template strings

---

## 6. Phase 4 — Google Search grounding (#6)

**Estimated effort:** 3–4 days  
**Depends on:** Phases 1, 3, 5 merged and validated on staging  
**Feature-flagged:** OFF by default

### 6.1 Settings — `config/settings.py`

```python
company_research_grounding_enabled: bool = Field(
    default=False,
    description="Enable Google Search grounding for company research (Vertex/BYOK)",
)
company_research_grounding_min_confidence: str = Field(
    default="MEDIUM",
    description="Only ground when disambiguation confidence <= this (HIGH|MEDIUM|LOW)",
)
```

Env vars:

```bash
COMPANY_RESEARCH_GROUNDING_ENABLED=false
COMPANY_RESEARCH_GROUNDING_MIN_CONFIDENCE=MEDIUM
```

### 6.2 LLM client — `utils/llm_client.py`

Add optional parameter to `generate()`:

```python
use_google_search_grounding: bool = False,
```

When True and backend supports it, attach Google Search tool to `GenerateContentConfig` per `google-genai` docs:

```python
from google.genai import types

tools = [types.Tool(google_search=types.GoogleSearch())]
config = types.GenerateContentConfig(
    ...,
    thinking_config=types.ThinkingConfig(thinking_budget=0),
    tools=tools,
)
```

**Requirements:**

- Wrap in `asyncio.wait_for()` (existing pattern)
- Log when grounding enabled (no API keys in logs)
- On unsupported backend (missing permission), log warning and fall back to non-grounded call — do not fail workflow

**Cost reference (Gemini 3.5 Flash, paid tier):**

- 5,000 search queries/month free (Gemini 3 family)
- Then ~$14 / 1,000 search queries
- Retrieved search context not billed as input tokens
- Typical company research: 1–3 queries per cache miss → ~$0.03–0.06 tokens + $0–0.042 search

### 6.3 Company research integration

Enable grounding only when:

- `settings.company_research_grounding_enabled`
- Cache miss (grounding on cache hit wastes money)
- Not `skip_cache` generic without domain OR always ground for generic (product choice: **ground when generic**)

Update main research prompt footer:

```
Use Google Search to verify company facts. Search queries MUST include:
employer name + industry + job title + posting domain when available.
Do not search name alone for ambiguous employers.
```

Pass `use_google_search_grounding=True` to `generate()` for Step B only (optional: Step A without grounding).

### 6.4 Phase 4 tests

**Unit (mocked):**

- `generate()` called with `use_google_search_grounding=True` when flag on + cache miss
- `generate()` called with `use_google_search_grounding=False` when flag off
- Cache hit → no LLM call

**Optional live test** (skip CI):

```python
@pytest.mark.live_llm
@pytest.mark.skipif(not os.getenv("RUN_LIVE_LLM"), reason="manual")
async def test_grounding_finds_real_startup(): ...
```

**Run:**

```bash
pytest tests/test_agents/test_company_research.py tests/test_utils/test_llm_client.py -v -k grounding
```

### 6.5 Phase 4 acceptance criteria

- [ ] Flag defaults OFF; production unchanged until explicitly enabled
- [ ] Grounding only on cache miss
- [ ] Fallback when grounding unavailable
- [ ] Staging manual test: small startup gets correct website (see §8)
- [ ] Monitor search query volume after enable

---

## 7. Golden fixture suite (add with Phase 1, expand each phase)

**File:** `tests/fixtures/company_research_cases.json`  
**File:** `tests/test_agents/test_company_research_golden.py`

| ID | Scenario | Phase | Assert |
|----|----------|-------|--------|
| CR-01 | Same "Acme", different Workday domains | 1 | Different cache keys |
| CR-02 | Same Acme + same domain | 1 | Cache hit on second call |
| CR-03 | "Meridian" healthcare vs fintech job context | 1+3 | Different keys; LOW for mismatch |
| CR-04 | Staffing post → null name | 2 | Unnamed research path |
| CR-05 | Lever URL slug in prompt | 1 | Prompt contains slug |
| CR-06 | "Atlas" no URL | 1 | skip_cache True |
| CR-07 | v1 cache key ≠ v2 cache key | 1 | Old key not used after bump |
| CR-08 | LOW confidence → research_quality uncertain | 3 | Field set |
| CR-09 | Grounding flag off | 4 | No tools in config |
| CR-10 | Grounding flag on | 4 | Tools in config |

Use mocked LLM — deterministic, CI-safe.

**Run:**

```bash
pytest tests/test_agents/test_company_research_golden.py -v
```

---

## 8. Pre-ship testing (mandatory)

### 8.1 Automated CI gate

```bash
# Agent + utils
pytest tests/test_agents/test_company_research.py \
       tests/test_agents/test_company_research_golden.py \
       tests/test_agents/test_job_analyzer.py \
       tests/test_utils/test_employer_disambiguation.py \
       tests/test_utils/test_cache.py \
       tests/test_workflows/test_job_application_workflow.py -v

# API integration
pytest tests/test_api/test_workflow_extended.py -v --override-ini="addopts="
```

All must pass.

### 8.2 Staging manual matrix (human sign-off)

Enable on staging: Phases 1–5; Phase 4 flag ON only for rows 5–6.

| # | Scenario | Pass criteria |
|---|----------|---------------|
| M1 | Large well-known company | Correct HQ, industry, website |
| M2 | Two saved jobs, same name, different careers URLs | Different research; no cross-cache |
| M3 | Staffing/recruiter post | No agency culture/interview info; banner if uncertain |
| M4 | Confidential / no company name | posting_only banner; no invented CEO |
| M5 | Small startup (<50 employees) | Grounding finds real site (Phase 4) |
| M6 | Cover letter + interview tabs | Mention correct company/industry |

Record session IDs + screenshots in PR.

### 8.3 Regression checks

- [ ] Website stat hidden when value is not `http(s)://` (existing rule)
- [ ] Workflow failure still clears agent JSONB on failed runs
- [ ] `isPlaceholderCompanyName()` still shows "Unknown" in header
- [ ] Downstream agents (cover letter, interview prep) receive same `company_research` blob

---

## 9. Ship plan

### 9.1 PR strategy (recommended)

| PR | Contents | Enable in prod |
|----|----------|----------------|
| PR1 | Phase 1 (#1,#2,#5) + golden tests | Immediately |
| PR2 | Phase 2 (#4) | Immediately |
| PR3 | Phase 3 (#3) + Phase 5 (#7) | Immediately |
| PR4 | Phase 4 (#6) flag OFF | Staging first; prod when M5 passes |

### 9.2 Deploy steps

1. Merge PR1 → bump cache version → deploy
2. Merge PR2–PR3 → deploy
3. Staging: run manual matrix §8.2
4. PR4: enable `COMPANY_RESEARCH_GROUNDING_ENABLED=true` on staging only
5. After sign-off, enable grounding in prod + monitor query volume

### 9.3 Rollback

| Issue | Action |
|-------|--------|
| Wrong research after deploy | Revert PR; cache version bump clears bad entries |
| Grounding cost spike | Set `COMPANY_RESEARCH_GROUNDING_ENABLED=false` |
| UI banner too aggressive | Adjust `research_quality` thresholds in backend only (no DB migration) |

---

## 10. Files touched (checklist)

| File | Phases |
|------|--------|
| `utils/employer_disambiguation.py` | 1 (new) |
| `agents/company_research.py` | 1, 3, 4 |
| `utils/cache.py` | 1 |
| `agents/job_analyzer.py` | 2 |
| `workflows/state_schema.py` | 2, 3 |
| `utils/llm_client.py` | 4 |
| `config/settings.py` | 4 |
| `ui/src/application-detail/` | 5 |
| `ui/templates/application.html` | 5 |
| `tests/test_utils/test_employer_disambiguation.py` | 1 (new) |
| `tests/test_agents/test_company_research_golden.py` | 1+ (new) |
| `tests/fixtures/company_research_cases.json` | 1+ (new) |
| `tests/test_agents/test_company_research.py` | 1, 3, 4 |
| `tests/test_agents/test_job_analyzer.py` | 2 |
| `tests/test_utils/test_cache.py` | 1 |

Optional doc update after ship: `.cursor/rules/agent-patterns.mdc` — Company Research section.

---

## 11. Out of scope (do not implement in this effort)

- Fetching job description HTML from pasted URLs (removed product feature)
- User-editable "correct this company" UI (future)
- Changing cache TTL (keep 7 days)
- Mentioning specific job board names in user-facing copy
- Adding `google-generativeai` package

---

## 12. Agent completion report template

When finished, the agent should post:

```markdown
## Company Research Improvement — Done

### Shipped phases
- [ ] Phase 1 #1,#2,#5
- [ ] Phase 2 #4
- [ ] Phase 3 #3
- [ ] Phase 5 #7
- [ ] Phase 4 #6 (flag: ON/OFF)

### Tests
- pytest: <pass count> / <total>
- Golden fixtures: CR-01 … CR-10

### Staging manual matrix
- M1–M6: pass/fail + notes

### Flags
- COMPANY_RESEARCH_GROUNDING_ENABLED=<value>

### Known limitations
- ...
```

---

*End of spec.*
