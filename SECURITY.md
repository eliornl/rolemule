# Security Policy

RoleMule is a self-hosted application that handles authentication, user profiles, resume uploads, and encrypted BYOK (bring-your-own-key) API keys. We take security reports seriously.

## Supported Versions

Security fixes are applied to the latest release on the `main` branch. Older tags and forks are not actively supported unless noted in a release announcement.

| Version | Supported |
| ------- | --------- |
| Latest on `main` | ✅ |
| Older releases | ❌ |

If you are running a fork or a pinned older commit, please upgrade to the latest `main` before reporting an issue that may already be fixed.

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Report security issues privately using one of these channels:

1. **[GitHub Security Advisories](https://github.com/eliornl/rolemule/security/advisories/new)** (preferred) — use **Report a vulnerability** on the [Security tab](https://github.com/eliornl/rolemule/security).
2. **Direct contact** — message the repository maintainer privately via their [GitHub profile](https://github.com/eliornl).

Public issues for security problems may be deleted or converted to private advisories without notice.

## What to Include

A helpful report includes:

1. **Summary** — what is vulnerable and the potential impact (e.g. auth bypass, data exposure, injection, privilege escalation).
2. **Affected area** — API route, UI page, Chrome extension, workflow agent, etc.
3. **Steps to reproduce** — minimal sequence from a clean install when possible.
4. **Environment** — OS, Docker vs local dev, browser (for UI/extension issues), and relevant config (redact secrets).
5. **Proof of concept** — exploit details, request/response samples, or screenshots (please redact personal data and API keys).

## Scope

In scope for this policy:

- Authentication, authorization, and session handling
- JWT validation, token revocation, and account lockout
- BYOK key encryption, storage, and transmission
- File upload validation (resumes, job description files)
- XSS, CSRF, SSRF, injection, and path traversal in the web app or extension
- Redis/PostgreSQL data exposure or privilege escalation
- CSP, CORS, and middleware misconfiguration with demonstrable impact
- Rate limiting bypass with security impact

Generally out of scope (unless chained with a vulnerability above):

- Missing security headers with no exploitable impact
- Denial-of-service requiring unrealistic resource exhaustion
- Issues in third-party services (Google Gemini, Google OAuth) — report those to the vendor
- Social engineering or physical access attacks
- Vulnerabilities in dependencies already fixed upstream — please confirm you are on the latest `main`

## Response Timeline

We aim to:

- **Acknowledge** reports as soon as possible — typically within a few business days
- **Assess severity** and ask follow-up questions if needed
- **Ship a fix** for confirmed issues as soon as practicable; critical issues on `main` are prioritized
- **Credit** reporters in the advisory or release notes when they wish to be named

Complex issues may take longer. We will keep you informed of progress.

## Safe Harbor

We support good-faith security research. If you follow this policy — private disclosure, no data destruction, no access beyond what is needed to demonstrate the issue, and no public disclosure before a fix or agreed timeline — we will not pursue legal action against you for your research.

## Security Best Practices for Self-Hosters

When running your own instance:

- Keep `DEBUG=false` in any shared or production environment
- Set strong, unique values for `JWT_SECRET` and `ENCRYPTION_KEY` (generated automatically by `make setup` / `make start`)
- Do not commit `.env` files or expose the app to the public internet without TLS and a reverse proxy
- Rotate `JWT_SECRET` only after confirming `ENCRYPTION_KEY` is set — rotating JWT without encryption key corrupts stored BYOK keys
- Review the [README](README.md) environment variables section and [`.env.local.example`](.env.local.example)

## Automated Security Scanning

RoleMule runs continuous security checks on `main`:

| Check | Where | Notes |
|-------|-------|-------|
| **CodeQL** | [Code scanning](https://github.com/eliornl/rolemule/security/code-scanning) | Python + TypeScript/JavaScript (`ui/src/`, `extension/`); config in [`.github/codeql/codeql-config.yml`](.github/codeql/codeql-config.yml) |
| **Secret scanning** | [Secret scanning](https://github.com/eliornl/rolemule/security/secret-scanning) | Flags leaked API keys; use non-`AIza` test keys in tests |
| **Dependabot** | [Dependabot alerts](https://github.com/eliornl/rolemule/security/dependabot) | CVE alerts + automated security update PRs |
| **Ruff lint** | GitHub Actions [`ci.yml`](.github/workflows/ci.yml) | Style + unused-import checks on every push |
| **Security grep** | GitHub Actions [`ci.yml`](.github/workflows/ci.yml) | Convention checks via `scripts/ci-security-grep.sh` |
| **E2E (live)** | GitHub Actions [`ci.yml`](.github/workflows/ci.yml) | Full Playwright suite when UI/backend/e2e paths change |

Contributors: run `ruff check .` locally before pushing. Dashboard XSS helpers live in `ui/src/shared/dom-security.ts`. Dynamic Python log values must use `sanitize_log_value()` / `mask_email()` — see [`.cursor/rules/codeql-security-scanning.mdc`](.cursor/rules/codeql-security-scanning.mdc).

For general contribution and bug-reporting guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md).
