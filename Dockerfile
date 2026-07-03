# Report Guard MCP — production image.
# Must be built for linux/amd64 (PlayMCP in KC rejects arm64):
#   docker build --platform linux/amd64 -t report-guard-mcp .
FROM --platform=linux/amd64 python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080 \
    HOST=0.0.0.0

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml README.md ./
COPY src ./src

# Install the package. The online Naver speller is called via httpx (a core dep),
# so no extra is needed.
RUN pip install --upgrade pip && pip install "."

# Drop privileges.
RUN useradd --create-home --uid 10001 appuser

# Bake secrets into the image. PlayMCP/KakaoCloud builds this image from the PRIVATE
# git source and offers no runtime env-var injection, so `.env` is committed to that
# private repo and copied in here; app_server.main() loads it from WORKDIR on startup.
# Keep both the repo and any image registry PRIVATE — anyone with access can read
# these credentials — and rotate the Naver keys regularly.
COPY --chown=appuser:appuser .env ./.env

USER appuser

EXPOSE 8080

# Container healthcheck hits the /health endpoint.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health').status==200 else 1)"

CMD ["report-guard"]
