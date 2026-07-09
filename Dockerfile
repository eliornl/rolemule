# =============================================================================
# DOCKERFILE — Multi-stage build for smaller image size
#
# Build: docker build -t applypilot .
# Run:   docker run -p 8000:8000 --env-file .env applypilot
# =============================================================================

# -----------------------------------------------------------------------------
# STAGE 0: Frontend asset build (legacy esbuild + Vite/TS page entries)
# -----------------------------------------------------------------------------
FROM node:22-slim AS frontend-builder

WORKDIR /app/ui

# Install deps (esbuild, vite, typescript, vitest)
COPY ui/package.json ui/package-lock.json ./
RUN npm ci --include=dev --no-audit --no-fund

# Copy source assets, TS sources, and build scripts/config
COPY ui/static/js  ./static/js
COPY ui/static/css ./static/css
COPY ui/src        ./src
COPY ui/build.mjs  ./
COPY ui/scripts    ./scripts
COPY ui/tsconfig.json ./
COPY ui/vite.config.ts ./
COPY ui/vite.entries.json ./

# Build → generates static/dist/ with hashed filenames + merged manifest.json
RUN npm run build

# -----------------------------------------------------------------------------
# STAGE 1: Builder
# -----------------------------------------------------------------------------
FROM python:3.13-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# -----------------------------------------------------------------------------
# STAGE 2: Runtime
# -----------------------------------------------------------------------------
FROM python:3.13-slim AS runtime

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    libreoffice-writer \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

# Copy Python packages from builder
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

# Copy application code
COPY --chown=appuser:appuser . .

# Copy the built frontend assets from the Node stage (overwrites empty dist/)
COPY --from=frontend-builder --chown=appuser:appuser /app/ui/static/dist ./ui/static/dist

# Alembic runs before uvicorn (see docker-entrypoint.sh) so `docker compose up` needs no separate migrate step.
RUN chmod +x /app/docker-entrypoint.sh

# Switch to non-root user
USER appuser

ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Default port — override with PORT env var or docker run -p
ENV PORT=8000
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose port
EXPOSE 8000

# Health check (uses unauthenticated /health endpoint)
# Longer start-period: migration runs before uvicorn binds (fresh DB can take a few seconds).
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
# workers=1: scale by running more containers; timeout=300s for long LLM calls
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-keep-alive", "300"]
