# CareerEngine — Cloud Run container image (single-container: FastAPI + Next.js export).
#
# Stage 1 builds the Next.js static export; stage 2 runs FastAPI (uvicorn) and serves
# BOTH /api/* and the exported frontend at / — same origin, no CORS (10.7 / AD-16.10).
# The image installs the project EDITABLE so runtime data (templates/classic_resume.html)
# is present on disk — a non-editable wheel would omit it (see pyproject.toml note).
#
# Build locally:   docker build -t career-engine:local .
# Run locally:     docker run --rm -p 8080:8080 --env-file .env career-engine:local
# Cloud build:     gcloud builds submit --config=cloudbuild.yaml --substitutions=_IMAGE=<AR path>

# ── Stage 1: build the Next.js static export → /frontend/out ───────────────────
FROM node:20-slim AS web
WORKDIR /frontend

# Public client config (NEXT_PUBLIC_*) is baked into the static export AT BUILD TIME
# (output: export). Defaults here make the image build in CI without secrets; the
# deploy pipeline passes real per-env values via --build-arg.
#   - API base is EMPTY on purpose: same-origin single container → client fetches /api/…
#   - Firebase values are PUBLIC project config (not secrets); the qa/prod build must
#     pass its project's values or Google sign-in won't initialise.
ARG NEXT_PUBLIC_API_BASE_URL=""
ARG NEXT_PUBLIC_FIREBASE_API_KEY=""
ARG NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=""
ARG NEXT_PUBLIC_FIREBASE_PROJECT_ID=""
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL \
    NEXT_PUBLIC_FIREBASE_API_KEY=$NEXT_PUBLIC_FIREBASE_API_KEY \
    NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=$NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN \
    NEXT_PUBLIC_FIREBASE_PROJECT_ID=$NEXT_PUBLIC_FIREBASE_PROJECT_ID

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── Stage 2: FastAPI runtime (serves /api + the static frontend) ───────────────
FROM python:3.12-slim

# WeasyPrint (PDF export) native deps — Pango pulls HarfBuzz + fontconfig transitively.
# Same set the WeasyPrint 69 docs list for Debian/Ubuntu.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

# Python source tree (respecting .dockerignore — .env, tests, docs, infra, frontend
# node_modules/build excluded). Editable install keeps templates/ on disk + packages importable.
COPY . .
RUN python -m pip install --upgrade pip \
    && python -m pip install -e .

# The built static frontend from stage 1 → FastAPI serves it at '/' (api/frontend.py).
COPY --from=web /frontend/out ./frontend/out

# Run as a non-root user.
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

# Cloud Run injects $PORT; uvicorn serves the FastAPI app, which also serves the SPA.
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
