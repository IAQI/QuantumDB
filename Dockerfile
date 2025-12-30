FROM rust:latest as builder

WORKDIR /usr/src/app
RUN apt-get update && apt-get install -y \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Create blank project with both bin and lib
RUN cargo new --bin quantumdb
WORKDIR /usr/src/app/quantumdb

# Copy manifests
COPY Cargo.toml Cargo.lock ./

# Create a dummy lib.rs for dependency caching (project has lib crate)
RUN echo "pub fn dummy() {}" > src/lib.rs

# Cache dependencies
RUN cargo build --release

# Remove dummy source and ALL cached build artifacts for the crate itself
RUN rm -rf src/*
RUN rm -rf ./target/release/deps/quantumdb* ./target/release/deps/libquantumdb* ./target/release/.fingerprint/quantumdb*

# Copy source code
COPY src ./src
COPY migrations ./migrations
COPY .sqlx ./.sqlx

# Build for release with SQLX_OFFLINE mode
ENV SQLX_OFFLINE=true
RUN cargo build --release

# Runtime stage
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y \
    ca-certificates \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/src/app/quantumdb/target/release/quantumdb /usr/local/bin/

ENV RUST_LOG=info
EXPOSE 3000

CMD ["quantumdb"]
