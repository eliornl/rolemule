# LLM Multi-Provider Abstraction — Agent Execution Spec

**Status:** Merged / complete (historical execution spec)  
**Owner:** Engineering  
**Last updated:** 2026-07-13  

All four providers (`gemini`, `openai`, `anthropic`, `ollama`) ship behind `utils/llm/` and `LLM_PROVIDER`. This document remains as the historical phase checklist — do not re-execute phases on `main`. See `.cursor/rules/llm-integration.mdc` for current patterns.

**Post-ship (user BYOK multi-provider):** Users must choose `preferred_provider` and add a BYOK key (except Ollama). Server `LLM_PROVIDER` / server keys are health/admin only; Vertex remains the no-key admin escape hatch. Company Research uses real web search on Gemini, OpenAI Responses `web_search`, and Anthropic `web_search`. Do not re-open completed phases below as unchecked.

---

## 0. Agent instructions (read first)

### 0.1 Goal

Introduce a clear, high-performance provider abstraction so agents call one stable API. **Delivered:** Gemini (Google AI Studio + optional Vertex), OpenAI, Anthropic, and Ollama all route through `get_llm_client()` / `utils/llm/`.

### 0.2 Non-negotiables

- Never raise bare `HTTPException` — use `APIError` / helpers from `utils/error_responses.py`
- All sync SDK calls wrapped in `asyncio.wait_for()` (default 180s)
- Gemini path: always `thinking_budget=0` in `GenerateContentConfig`
- Never log API keys; use `sanitize_log_value()` for dynamic log args
- Keep `utils.llm_client` public imports working (compat shim) so agents/tests don’t churn
- Stable generate response shape: `{ "response": str, "done": bool, "model"?: str, "filtered"?: bool, "from_cache"?: bool }`
- Prefer httpx AsyncClient for OpenAI/Anthropic/Ollama (native async) — no thread-pool for those
- Vertex AI: **keep if cheap** (Gemini adapter branch only); do not expand product surface

### 0.3 Rules to read before coding

| Area | File |
|------|------|
| LLM | `.cursor/rules/llm-integration.mdc` |
| Agents / BYOK | `.cursor/rules/agent-patterns.mdc` |
| Settings / env | `.cursor/rules/settings-and-env.mdc` |
| Settings UI | `.cursor/rules/settings-page.mdc` |
| Unit tests | `.cursor/rules/unit-testing.mdc` |
| Core | `.cursor/rules/rolemule-core.mdc` |

### 0.4 Design principles

| Principle | How |
|-----------|-----|
| **Clear** | One `LLMProvider` protocol; one `LLMClient` facade (cache + retry + route) |
| **Maintainable** | Providers isolated under `utils/llm/providers/`; no agent changes for new providers |
| **Efficient** | Shared Redis LLM cache on facade; provider resolution cached on singleton |
| **Scalable** | Registry map `name → factory`; no if/elif sprawl in agents |
| **High performance** | Async SDKs where available; bounded timeouts; tenacity only on transient failures |
| **Testable** | Unit-test each adapter with mocked HTTP/SDK; keep Gemini regression suite green |

### 0.5 Target layout

```
utils/llm/
  __init__.py              # public: get_llm_client, LLMError, constants
  constants.py             # DEFAULT_MAX_TOKENS, timeouts, retries
  errors.py                # LLMError (+ GeminiError alias), user-facing messages
  types.py                 # ProviderName, GenerateResult
  base.py                  # LLMProvider Protocol
  registry.py              # resolve + create provider
  client.py                # LLMClient facade (cache, retry, route)
  providers/
    __init__.py
    gemini.py              # Phase 1 — AI Studio + Vertex
    openai.py              # Phase 2
    anthropic.py           # Phase 3
    ollama.py              # Phase 4
utils/llm_client.py        # thin re-exports (backward compatible)
```

### 0.6 Provider resolution (Phase 1 → later)

```
1. Explicit `provider=` on generate() if passed (future)
2. settings.llm_provider (default: "gemini")
3. Fallback: gemini
```

BYOK keys were Gemini-only through Phases 2–4; Phase 5 / post-ship work added multi-provider user keys in Settings.

### 0.7 Execution order

```
Phase 1 (abstraction + Gemini) → Phase 2 (OpenAI) → Phase 3 (Anthropic)
  → Phase 4 (Ollama) → Phase 5 (docs/rules + full suite + optional Settings prefs)
```

---

## 1. Phase 1 — Provider abstraction + Gemini

**Goal:** Behavior-identical Gemini path behind `LLMProvider` + `LLMClient`. Vertex kept as Gemini backend branch.

### 1.1 Tasks

- [x] Create package `utils/llm/` with constants, errors, types, base Protocol
- [x] Extract `GeminiProvider` from current `GeminiClient` (AI Studio + Vertex + health)
- [x] Implement `LLMClient` facade: cache → retry → `provider.generate()`
- [x] Registry: `gemini` only; `get_llm_client()` / `get_gemini_client()` aliases
- [x] `utils/llm_client.py` re-exports all previous public symbols
- [x] Keep `GeminiError` as alias of `LLMError`
- [x] Settings: add `llm_provider: str = "gemini"` (validated allowlist)
- [x] Update / extend unit tests; fix patch paths if modules move
- [x] Code review checklist (below)
- [x] Mark Phase 1 tasks done in this doc

### 1.2 Tests to run

```bash
pytest tests/test_utils/test_llm_client.py tests/test_agents/test_llm_user_facing_message.py -v --override-ini="addopts="
pytest tests/test_utils/test_settings.py -v --override-ini="addopts="
```

### 1.3 Code review checklist

- [x] No API key in logs
- [x] `asyncio.wait_for` on all sync Gemini SDK calls
- [x] `thinking_budget=0` unchanged
- [x] Response shape unchanged
- [x] Singleton reset helpers work (`reset_gemini_client` / `reset_llm_client`)
- [x] Importing `from utils.llm_client import get_gemini_client, GeminiError, DEFAULT_MAX_TOKENS` still works

### 1.4 Exit criteria

Gemini generate + health + cache + quota messaging behave as before; new structure is importable for Phase 2.

---

## 2. Phase 2 — OpenAI adapter

**Goal:** Second real provider behind the same interface. Server key via env; optional BYOK later in Phase 5.

### 2.1 Tasks

- [x] Add settings: `openai_api_key`, `openai_model` (default `gpt-5.6-luna`)
- [x] Implement `OpenAIProvider` with **httpx AsyncClient** (Chat Completions or Responses API)
- [x] Map system + user messages; map max_tokens / temperature
- [x] `use_google_search_grounding=True` → ignore with debug log (Gemini-only)
- [x] Register `openai` in registry; allow `LLM_PROVIDER=openai`
- [x] Quota/rate-limit detection for OpenAI in `errors.py`
- [x] Unit tests with mocked httpx
- [x] Code review + mark done

### 2.2 Tests

```bash
pytest tests/test_utils/test_llm_client.py tests/test_utils/test_llm_openai.py -v --override-ini="addopts="
```

### 2.3 Exit criteria

With `LLM_PROVIDER=openai` + `OPENAI_API_KEY`, `LLMClient.generate()` returns the standard shape.

---

## 3. Phase 3 — Anthropic adapter

**Goal:** Anthropic Messages API behind the same interface.

### 3.1 Tasks

- [x] Settings: `anthropic_api_key`, `anthropic_model` (default `claude-sonnet-5`)
- [x] `AnthropicProvider` via httpx AsyncClient
- [x] System prompt as top-level `system`; user content in messages
- [x] Grounding flag ignored (debug log)
- [x] Register `anthropic`; quota mapping
- [x] Unit tests + code review + mark done

### 3.2 Tests

```bash
pytest tests/test_utils/test_llm_anthropic.py tests/test_utils/test_llm_client.py -v --override-ini="addopts="
```

---

## 4. Phase 4 — Ollama adapter

**Goal:** Local/self-hosted Ollama via OpenAI-compatible or native chat API.

### 4.1 Tasks

- [x] Settings: `ollama_base_url` (default `http://127.0.0.1:11434`), `ollama_model`
- [x] `OllamaProvider` via httpx; short connect timeout; clear errors if unreachable
- [x] No API key required (optional bearer if configured later)
- [x] Register `ollama`
- [x] Unit tests (mocked) + code review + mark done

### 4.2 Tests

```bash
pytest tests/test_utils/test_llm_ollama.py -v --override-ini="addopts="
```

---

## 5. Phase 5 — Docs, rules, Settings readiness, full verification

**Goal:** Documentation matches code; full regression; optional minimal Settings hooks for future BYOK multi-key (without forcing UI rewrite if deferred).

### 5.1 Tasks

- [x] Update `.cursor/rules/llm-integration.mdc` (+ `.claude/rules` mirror if present)
- [x] Update `settings-and-env.mdc`, `agent-patterns.mdc`, `CLAUDE.md` / `.cursorrules` index rows if needed
- [x] Update `.env.local.example` with new LLM_* vars
- [x] Prefer `get_llm_client()` in new code; keep `get_gemini_client` as alias
- [x] Optional: `preferred_provider` on preferences (nullable, default null = settings) — only if low-risk
- [x] Run full unit + API test suites (see below)
- [x] Mark all phases complete in this doc; set Status to Implemented

### 5.2 Full verification

```bash
pytest tests/test_utils/ tests/test_agents/ -v --override-ini="addopts="
pytest tests/test_api/ -v --override-ini="addopts="
# Optional if DB available:
# make test / CI-equivalent
```

### 5.3 Pre-ship checklist

- [x] Gemini default path unchanged for existing deployments
- [x] Vertex still works when `USE_VERTEX_AI=true` + project set
- [x] No secrets in repo / logs
- [x] Docs and cursor rules updated
- [x] Plan doc tasks checked off

---

## 6. Out of scope (explicit) — original plan

These were deferred at ship time; **multi-provider BYOK + grounding are now delivered** (see header note):

- ~~Full Settings UI for multi-provider BYOK key vault~~ — done (Settings → AI Setup)
- ~~Replacing Company Research Google Search grounding with OpenAI/Anthropic web tools~~ — done
- Migrating every agent call site from `get_gemini_client` → `get_llm_client` in one shot (alias is enough)
- Dropping Vertex (kept as Gemini-only admin backend)

**Follow-up (shipped):** `LLMClient.generate_stream` + provider streams + `SpeakFieldStreamer` for Practice Interview speak deltas — see `llm-integration.mdc` / `mock-interview-feature.mdc`.

---

## 7. Risk register

| Risk | Mitigation |
|------|------------|
| Test patch paths break | Compat shim + update patches to `utils.llm.providers.gemini` |
| Provider-specific JSON quirks | Keep `parse_json_from_llm_response` at agent layer |
| Accidental provider switch in prod | Default `llm_provider=gemini`; validate allowlist |
| Ollama hangs | Aggressive connect timeout + clear `LLMError` |
