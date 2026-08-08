# Aria — sovereign-agent Docker image
# Multi-stage build: keeps the final image lean.
#
# Build:  docker build -t sovereign-agent:latest .
# Run:    docker compose up
#
# Data persists in Docker volumes: config/ and data/
# To access the TUI cockpit: docker exec -it aria sov-chat

# ── Stage 1: builder ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# System deps for native extensions (sqlite-vec, cryptography)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src/ src/
COPY uv.lock* ./

# Install into a prefix we can copy to the final image
RUN pip install --no-cache-dir --prefix /install -e . 2>&1 | tail -5

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="Aria — Sovereign Agent"
LABEL org.opencontainers.image.description="Safety-first local AI agent. Kernel: Safety · Love · Flourishing."
LABEL org.opencontainers.image.source="https://github.com/Cyber-Chaqar-KevinMonette/sovereign-agent"

WORKDIR /app

# Runtime deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libffi8 libssl3 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy source for editable-install awareness
COPY src/ src/
COPY pyproject.toml ./

# Install again in runtime (editable, so src/ changes take effect)
RUN pip install --no-cache-dir -e . -q

# XDG dirs — mounted as volumes at runtime
ENV XDG_CONFIG_HOME=/data/config
ENV XDG_DATA_HOME=/data/storage
ENV HOME=/data/home

# MCP server port (SSE transport)
EXPOSE 8765

# Default user — non-root
RUN useradd -m -u 1000 aria && \
    mkdir -p /data/config /data/storage /data/home && \
    chown -R aria:aria /data /app
USER aria

# Healthcheck: sov info returns 0 when Aria is operational
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD sov info --json 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d else 1)" || exit 1

# Default: launch the MCP server (SSE mode) for networked access
# Override with: docker run ... sov-chat (TUI cockpit)
CMD ["sov-mcp", "--transport", "sse", "--host", "0.0.0.0", "--port", "8765"]
