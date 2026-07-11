# UI Static Assets

Static assets for the ApplyPilot web frontend.

> **Page scripts** live in **`ui/src/`** (TypeScript, Vite-bundled). This folder holds **CSS**, images, favicon, and build output.

## Layout

```
ui/
├── src/                    # TypeScript — pages, shared modules, feature folders
├── static/
│   ├── css/                # Source stylesheets (esbuild-minified at build)
│   ├── dist/               # Build output (gitignored) — hashed JS/CSS + manifest.json
│   ├── img/
│   └── favicon.ico
├── vite.entries.json       # manifest key → src/pages/*.ts
└── scripts/build-vite.mjs  # Vite IIFE bundles + hidden source maps
```

Templates still use logical keys: `{{ asset_url('js/dashboard-home.js') }}`. Vite emits hashed files under `static/dist/js/`.

## Build & checks

```bash
make build-frontend          # Vite (JS) + esbuild (CSS) → static/dist/
cd ui && npm run typecheck   # strict TypeScript (tsconfig.ci.json)
cd ui && npm run test        # Vitest (shared helpers)
```

See [CONTRIBUTING.md](../../CONTRIBUTING.md) and [.cursor/rules/frontend-build-pipeline.mdc](../../.cursor/rules/frontend-build-pipeline.mdc).
