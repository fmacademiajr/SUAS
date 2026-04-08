# ─── Stage 1: backend dependency builder ─────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

RUN pip install --no-cache-dir poetry==1.8.3

COPY backend/pyproject.toml backend/poetry.lock* ./

# Export dependencies to requirements.txt (no dev deps for production)
RUN poetry export --without dev --without-hashes -f requirements.txt -o requirements.txt

# ─── Stage 2: frontend builder ───────────────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

COPY frontend/ ./

# Firebase config passed as build args
ARG VITE_FIREBASE_API_KEY
ARG VITE_FIREBASE_AUTH_DOMAIN
ARG VITE_FIREBASE_PROJECT_ID
ARG VITE_FIREBASE_STORAGE_BUCKET
ARG VITE_FIREBASE_MESSAGING_SENDER_ID
ARG VITE_FIREBASE_APP_ID
ENV VITE_API_URL=""

RUN npm run build

# ─── Stage 3: production runtime ─────────────────────────────────────────────
FROM python:3.11-slim AS production

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Install production dependencies from builder
COPY --from=builder /build/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application source
COPY backend/app/ ./app/

# Copy built frontend into static/
COPY --from=frontend-builder /frontend/dist ./static/

# Install Playwright browsers (needed for image fallback)
RUN pip install playwright && playwright install chromium --with-deps

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

# Single worker — APScheduler must not run duplicate cron jobs across workers
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
