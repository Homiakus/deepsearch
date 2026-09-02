# Multi-stage hardened production Dockerfile (§DS-24)
# Stage 1: Build virtual environment with uv
FROM ghcr.io/astral-sh/uv:0.5.21 AS uv-bin
FROM python:3.12-slim-bookworm AS builder

COPY --from=uv-bin /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy dependency manifests
COPY pyproject.toml uv.lock README.md ./

# Install locked production dependencies into /app/.venv without editable mode or dev dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# Stage 2: Minimal hardened non-root runtime image
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PORT=8080

WORKDIR /app

# Create unprivileged system user and data directories
RUN groupadd -g 10001 deepsearch \
    && useradd -r -u 10001 -g deepsearch -d /app -s /sbin/nologin deepsearch \
    && mkdir -p /app/data /data/storage \
    && chown -R deepsearch:deepsearch /app /data/storage

# Copy virtual environment from builder stage
COPY --from=builder --chown=deepsearch:deepsearch /app/.venv /app/.venv

# Copy application source code and migrations
COPY --chown=deepsearch:deepsearch scraper /app/scraper
COPY --chown=deepsearch:deepsearch alembic.ini /app/alembic.ini
COPY --chown=deepsearch:deepsearch migrations /app/migrations

USER deepsearch:deepsearch

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health')" || exit 1

ENTRYPOINT ["uvicorn", "scraper.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
