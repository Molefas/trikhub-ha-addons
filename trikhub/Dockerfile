# TrikHub Home Assistant Addon
# Multi-arch build supporting aarch64, amd64, armv7

ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:3.19
FROM ${BUILD_FROM}

# Install Node.js, Python 3, and dependencies
RUN apk add --no-cache \
    nodejs \
    npm \
    python3 \
    py3-pip \
    bash \
    jq \
    git

# Create app directory
WORKDIR /app

# Cache bust arg - increment to force npm re-fetch
ARG TRIKHUB_VERSION=0.10.0

# Install TrikHub packages globally
# Server and CLI (dependencies like gateway, linter, manifest are pulled automatically)
RUN npm install -g @trikhub/server@${TRIKHUB_VERSION} @trikhub/cli@0.4.0

# Python packages for trik support
# - trikhub: Core Python SDK for running Python triks
# - anthropic, openai, httpx: Common LLM client libraries used by triks
RUN pip3 install --no-cache-dir --break-system-packages \
    trikhub \
    anthropic \
    openai \
    httpx

# Create data directories with proper permissions
# Create package.json for trik installations and .trikhub config
RUN mkdir -p /data/skills /data/.trikhub/storage /data/.trikhub/triks /data/node_modules && \
    echo '{"triks":[]}' > /data/.trikhub/config.json && \
    echo '{}' > /data/.trikhub/secrets.json && \
    echo '{"name":"trikhub-addon-triks","private":true,"type":"module"}' > /data/package.json

# Symlink /app to /data so trik install works (server runs with cwd=/app)
# Use -n flag to ensure symlinks are replaced, not nested
RUN ln -sfn /data/package.json /app/package.json && \
    ln -sfn /data/.trikhub /app/.trikhub && \
    ln -sfn /data/node_modules /app/node_modules

# Environment variables (overridden by S6 run script from HA config)
ENV NODE_ENV=production
ENV SKILLS_DIR=/data/skills
ENV CONFIG_PATH=/data/.trikhub/config.json
ENV PORT=3000
ENV HOST=0.0.0.0
ENV LOG_LEVEL=info
ENV LINT_ON_LOAD=true
# Python path for the gateway's Python worker
ENV TRIKHUB_PYTHON=python3

# Copy S6 service definitions
COPY rootfs /

# Build arguments for labels
ARG BUILD_ARCH
ARG BUILD_DATE
ARG BUILD_DESCRIPTION
ARG BUILD_NAME
ARG BUILD_REF
ARG BUILD_REPOSITORY
ARG BUILD_VERSION

# Labels
LABEL \
    io.hass.name="${BUILD_NAME}" \
    io.hass.description="${BUILD_DESCRIPTION}" \
    io.hass.arch="${BUILD_ARCH}" \
    io.hass.type="addon" \
    io.hass.version=${BUILD_VERSION} \
    maintainer="TrikHub Team <team@trikhub.com>" \
    org.opencontainers.image.title="${BUILD_NAME}" \
    org.opencontainers.image.description="${BUILD_DESCRIPTION}" \
    org.opencontainers.image.vendor="TrikHub" \
    org.opencontainers.image.authors="TrikHub Team <team@trikhub.com>" \
    org.opencontainers.image.licenses="MIT" \
    org.opencontainers.image.url="https://trikhub.com" \
    org.opencontainers.image.source="https://github.com/${BUILD_REPOSITORY}" \
    org.opencontainers.image.documentation="https://github.com/${BUILD_REPOSITORY}/blob/main/README.md" \
    org.opencontainers.image.created=${BUILD_DATE} \
    org.opencontainers.image.revision=${BUILD_REF} \
    org.opencontainers.image.version=${BUILD_VERSION}
