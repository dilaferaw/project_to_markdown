# ============================================================================
# Docker image for project-to-markdown
# Multi-stage build: Python deps first (cacheable), then a minimal Alpine run.
# ============================================================================
FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir --prefix=/install uv \
 && uv lock --check \
 && uv sync --frozen --no-editable --prefix=/install

FROM alpine:3.22 AS runtime
RUN apk add --no-cache --virtual .run-deps \
      gcc g++ musl-dev linux-headers \
      libffi-dev openssl-dev \
 && apk add --no-cache tzdata su-exec \
 && python3 -m ensurepip \
 && rm -rf /root/.cache/pip

WORKDIR /app
COPY --from=builder /install /usr/local

RUN useradd -m -u 1000 ptm && chown -R ptm:ptm /app
USER ptm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PTM_CONFIG_DIR=/data/ptm
VOLUME ["/data"]

ARG BUILD_SHA
ENV BUILD_SHA=${BUILD_SHA:-unknown}

ENTRYPOINT ["/usr/local/bin/ptm"]
CMD ["--host", "0.0.0.0", "--port", "8765"]
