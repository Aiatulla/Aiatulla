# Multi-stage: the build stage carries uv and build tooling, the runtime stage
# does not. A smaller runtime image is also a smaller attack surface.
FROM python:3.11-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /build

# UV_PROJECT_ENVIRONMENT, not VIRTUAL_ENV: uv sync manages the project's own
# .venv and ignores VIRTUAL_ENV, so setting only that installs into /build/.venv
# and leaves the copied /opt/venv holding nothing but a Python binary.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

# Dependencies before source, so editing application code does not invalidate
# the dependency layer on every rebuild.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN uv sync --frozen --no-dev


FROM python:3.11-slim AS runtime

# git is a runtime dependency, not a build one: the cloner shells out to it.
RUN apt-get update && \
    apt-get install --no-install-recommends -y git && \
    rm -rf /var/lib/apt/lists/*

# A non-root user, because this process clones untrusted repositories. If
# anything ever escapes the workspace, it should not be root that it escapes as.
RUN useradd --create-home --uid 1000 appuser

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY --chown=appuser:appuser backend_entrypoint.sh /usr/local/bin/entrypoint.sh
COPY --from=builder --chown=appuser:appuser /build/app ./app
COPY --from=builder --chown=appuser:appuser /build/alembic ./alembic
COPY --from=builder --chown=appuser:appuser /build/alembic.ini ./

RUN chmod +x /usr/local/bin/entrypoint.sh
USER appuser

EXPOSE 8000

# Liveness only: this endpoint deliberately does not touch the database, so a
# brief database blip does not restart a process that is working fine.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')"

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
