# ─── Stage 1: dependency builder ─────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

RUN pip install --no-cache-dir poetry==1.8.3

COPY pyproject.toml poetry.lock* ./

# Export dependencies to requirements.txt (no dev deps for production)
RUN poetry export --without dev --without-hashes -f requirements.txt -o requirements.txt

# ─── Stage 2: development (hot reload, includes dev deps) ────────────────────
FROM python:3.11-slim AS development

WORKDIR /app

# Install all deps including dev
RUN pip install --no-cache-dir poetry==1.8.3
COPY pyproject.toml poetry.lock* ./
RUN poetry config virtualenvs.in-project true && \
    poetry install --with dev --no-interaction --no-ansi

COPY . .

EXPOSE 8080

CMD ["poetry", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--reload", "--reload-dir", "/app/app"]

# ─── Stage 3: production runtime ─────────────────────────────────────────────
FROM python:3.11-slim AS production

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Install production dependencies from builder
COPY --from=builder /build/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY app/ ./app/
COPY scripts/ ./scripts/

# Install Playwright browsers (needed for image fallback)
RUN pip install playwright && playwright install chromium --with-deps

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

# Single worker — APScheduler must not run duplicate cron jobs across workers
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
