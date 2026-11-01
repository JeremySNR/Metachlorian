# Metachlorian core: API, MCP, web app and analysis workers in one image.
# Build:  docker build -t metachlorian .
# Run:    see deploy/docker-compose.yml
FROM node:22-bookworm-slim AS web
WORKDIR /src/app
COPY app/package*.json ./
RUN npm ci --no-audit --no-fund
COPY app/ ./
RUN npm run build

FROM python:3.11-slim-bookworm
LABEL org.opencontainers.image.source=https://github.com/JeremySNR/Metachlorian \
      org.opencontainers.image.description="Self-hosted, shot-level video search for AI agents and editors" \
      org.opencontainers.image.licenses=Apache-2.0
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    METACHLORIAN_DATA=/data METACHLORIAN_MODELS=/models METACHLORIAN_APP_DIST=/opt/metachlorian/app/dist \
    METACHLORIAN_HOST=0.0.0.0 METACHLORIAN_REQUIRE_AUTH=true
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libimage-exiftool-perl ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* && useradd -r -u 1000 -m metachlorian
WORKDIR /opt/metachlorian
COPY core/ core/
COPY docs/integration/cutawan-package.schema.json docs/integration/cutawan-package.schema.json
RUN pip install --no-cache-dir "./core[analysis,s3]"
COPY --from=web /src/app/dist app/dist
COPY deploy/entrypoint.sh /usr/local/bin/metachlorian-entrypoint
RUN chmod +x /usr/local/bin/metachlorian-entrypoint && mkdir -p /data /models && chown -R metachlorian /data /models
USER metachlorian
VOLUME ["/data", "/models"]
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s CMD curl -fs http://127.0.0.1:8765/api/health || exit 1
ENTRYPOINT ["metachlorian-entrypoint"]
CMD ["serve"]
