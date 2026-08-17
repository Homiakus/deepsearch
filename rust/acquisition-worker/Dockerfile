# Build stage
FROM rust:1.85-slim-bookworm AS builder

WORKDIR /usr/src/acquisition-worker

# Install build essentials and SSL dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config \
    libssl-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy cargo manifest
COPY Cargo.toml Cargo.lock* ./

# Copy source code
COPY src/ ./src/

# Build release binary
RUN cargo build --release --bin acquisition-worker

# Runtime stage
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN useradd -u 10001 -m -s /bin/sh appuser

WORKDIR /app
COPY --from=builder /usr/src/acquisition-worker/target/release/acquisition-worker /app/acquisition-worker

# Setup CAS and temporary data storage
RUN mkdir -p /app/data/cas && chown -R appuser:appuser /app

USER appuser

EXPOSE 8081

ENV RUST_LOG=info \
    PORT=8081 \
    HOST=0.0.0.0

HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
  CMD curl -f http://localhost:8081/v1/health || exit 1

ENTRYPOINT ["/app/acquisition-worker"]
