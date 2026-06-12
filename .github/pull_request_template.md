## Summary

<!-- What changed and why? Link related issues: Fixes #123 -->

## Type of change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing behavior to change)
- [ ] Documentation only
- [ ] Refactor (no user-facing behavior change)

## Related issue

<!-- Link the issue this addresses, or write "N/A" for small fixes discussed inline -->

Fixes #

## Test plan

<!-- How did you verify this works? Be specific — commands run, manual steps, screenshots. -->

- [ ] Unit/integration tests pass: `make test` / `just test`
- [ ] E2E smoke tests pass: `cd e2e && npm run test:smoke` (if UI or auth flows changed)
- [ ] Frontend builds cleanly: `make build-frontend` / `just build-frontend` (if JS/CSS changed)
- [ ] No new linter errors: `make lint` / `just lint`

## Code checklist

- [ ] No bare `HTTPException` — uses `APIError` / factory helpers from `utils/error_responses.py`
- [ ] All JSONB mutations include `flag_modified()`
- [ ] Background tasks use `get_session()`, not `get_database()`
- [ ] No `onclick=` / `onchange=` HTML attributes (event delegation + `data-action` instead)
- [ ] No `style="..."` HTML attributes (CSP blocks inline styles — use CSS classes)
- [ ] No `alert()` / `confirm()` — uses `notify()` / `window.showConfirm()`
- [ ] New/changed JS passes strict JSDoc checks (`jsconfig.json`)

## Screenshots / recordings

<!-- If UI changed, add before/after screenshots or a short recording. Delete this section if N/A. -->
