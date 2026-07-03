# CareerEngine — Cloud Run container image.
#
# Serves the Streamlit web workspace on $PORT (Cloud Run injects it; default 8080).
# The image COPYs the whole source tree and installs the project EDITABLE, so
# runtime data (templates/classic_resume.html) is present on disk — a non-editable
# wheel would omit it (see pyproject.toml note).
#
# Build locally:   docker build -t career-engine:local .
# Run locally:     docker run --rm -p 8080:8080 --env-file .env career-engine:local
# Cloud build:     gcloud builds submit --config=cloudbuild.yaml --substitutions=_IMAGE=<AR path>

FROM python:3.12-slim

# WeasyPrint (PDF renderer) native deps — Pango pulls HarfBuzz + fontconfig
# transitively. Same set the WeasyPrint 69 docs list for Debian/Ubuntu.
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

# Full source tree (respecting .dockerignore — .env, tests, docs, infra excluded).
COPY . .

# Runtime deps + editable project install (keeps templates on disk, packages importable).
RUN python -m pip install --upgrade pip \
    && python -m pip install -e .

# Run as a non-root user.
RUN chmod +x /app/docker-entrypoint.sh \
    && useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

# Entrypoint materializes .streamlit/secrets.toml from env (OIDC auth) then runs CMD.
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Cloud Run routes traffic to $PORT; Streamlit must bind 0.0.0.0 and run headless.
CMD ["sh", "-c", "streamlit run web/streamlit_app.py --server.port=${PORT} --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false"]
