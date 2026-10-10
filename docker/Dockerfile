# ============================================================================
# Docker image for project-to-markdown
#
# Multi-stage build.  Stage one installs the Python dependencies into an
# isolated prefix; stage two is a clean image that only contains the runtime
# interpreter plus the application source.
# ============================================================================
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim AS runtime

WORKDIR /app

# Installed packages from the builder stage.
COPY --from=builder /install /usr/local

# Application source.
COPY main.py server.py utils.py ./
COPY core/ ./core/
COPY web/ ./web/

# Non-root user and a writable /data mount point for config persistence.
RUN useradd -m -u 1000 ptm \
 && mkdir -p /data \
 && chown -R ptm:ptm /app /data

USER ptm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PTM_CONFIG_DIR=/data/ptm

VOLUME ["/data"]
EXPOSE 8765

ARG BUILD_SHA=unknown
ENV BUILD_SHA=${BUILD_SHA}

ENTRYPOINT ["python3", "main.py"]
CMD ["--host", "0.0.0.0", "--port", "8765"]