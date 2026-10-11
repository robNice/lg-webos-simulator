# LG webOS TV Simulator – container image (GHCR, see .github/workflows). Not a real LG TV.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LG_TV_SIM_CONFIG=/config/simulator.toml \
    LG_TV_SIM_CONFIG_TEMPLATE=/app/config/docker.toml \
    LG_TV_SIM_CONTAINER=1 \
    PUID=10001 \
    PGID=10001

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir . && rm -rf src build

COPY fixtures/synthetic/ fixtures/synthetic/
COPY fixtures/recorded/ fixtures/recorded/
COPY fixtures/scenarios/ fixtures/scenarios/
COPY config/docker.toml config/docker.toml
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# /config: simulator.toml, copied from the template on first start and never overwritten.
# /app/.simulator: runs, SSH host key, generated password (credentials), imported private fixtures.
RUN mkdir -p /config /app/.simulator
VOLUME ["/config", "/app/.simulator"]

EXPOSE 2222 8767

HEALTHCHECK --interval=60s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8767/', timeout=4)" || exit 1

# The entrypoint prepares /config and /app/.simulator as root and starts the simulator as PUID:PGID.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["lg-tv-sim", "serve"]
