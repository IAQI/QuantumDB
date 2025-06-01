FROM rust:latest as builder

WORKDIR /usr/src/app
RUN apt-get update && apt-get install -y \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Create blank project
RUN cargo new --bin quantumdb
WORKDIR /usr/src/app/quantumdb

# Copy manifests
COPY Cargo.toml Cargo.lock ./

# Cache dependencies
RUN cargo build --release
RUN rm src/*.rs

# Copy source code
COPY src ./src
COPY migrations ./migrations
COPY .sqlx ./.sqlx

# Build for release with SQLX_OFFLINE mode
ENV SQLX_OFFLINE=true
RUN rm ./target/release/deps/quantumdb*
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