# =============================================================================
# SC Node - Bitcoin Core Docker Image
# Mirrors bitcoin-install.sh: same binaries, config layout, and behavior.
# Uses official Bitcoin Core tarball (no compilation).
#
# SYNC: Changes to bitcoin-install.sh (paths, options, version) are NOT
# reflected here automatically. Update this Dockerfile and docker-entrypoint.sh
# to match when you change the bare-metal script.
# =============================================================================
ARG BITCOIN_VERSION=30.2
FROM debian:bookworm-slim AS builder

ARG BITCOIN_VERSION
ENV BITCOIN_VERSION=${BITCOIN_VERSION}
ENV BITCOIN_TARBALL="bitcoin-${BITCOIN_VERSION}-x86_64-linux-gnu.tar.gz"
ENV BITCOIN_URL="https://bitcoincore.org/bin/bitcoin-core-${BITCOIN_VERSION}/${BITCOIN_TARBALL}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /tmp/bitcoin

RUN curl -# -L -O "${BITCOIN_URL}" \
    && tar -xzf "${BITCOIN_TARBALL}" \
    && rm "${BITCOIN_TARBALL}"

# -----------------------------------------------------------------------------
# Final stage: minimal runtime image
# -----------------------------------------------------------------------------
FROM debian:bookworm-slim

ARG BITCOIN_VERSION
ENV BITCOIN_VERSION=${BITCOIN_VERSION}

# Install runtime deps (python3 for rpcauth.py; gosu to drop privileges in entrypoint)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    gosu \
    python3 \
    && rm -rf /var/lib/apt/lists/*

# Create bitcoin user/group (matches bitcoin-install.sh)
RUN groupadd --system bitcoin \
    && useradd --system --gid bitcoin --create-home --home-dir /home/bitcoin \
        --shell /usr/sbin/nologin --comment "Bitcoin Core daemon" bitcoin

# Copy binaries from builder (same paths as bitcoin-install.sh)
COPY --from=builder /tmp/bitcoin/bitcoin-*/bin/bitcoind /usr/local/bin/bitcoind
COPY --from=builder /tmp/bitcoin/bitcoin-*/bin/bitcoin-cli /usr/local/bin/bitcoin-cli
COPY --from=builder /tmp/bitcoin/bitcoin-*/share/rpcauth/rpcauth.py /usr/local/bin/rpcauth.py
RUN chmod 755 /usr/local/bin/bitcoind /usr/local/bin/bitcoin-cli /usr/local/bin/rpcauth.py

# Wallet notify script (matches script from bitcoin-install.sh; in container we log to stdout)
RUN echo '#!/usr/bin/env bash\n\
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")\n\
TXID="$1"\n\
WALLET="$2"\n\
echo "${TIMESTAMP} | ${TXID} | ${WALLET}" >> /var/log/bitcoin/bitcoin_wallet_events.log\n\
exit 0' > /usr/local/bin/wallet_event_append.sh \
    && chmod 755 /usr/local/bin/wallet_event_append.sh

# Directories (FHS-style, same as bitcoin-install.sh)
ENV BITCOIN_DATA=/var/lib/bitcoin
ENV BITCOIN_CONF_DIR=/etc/bitcoin
ENV BITCOIN_LOG_DIR=/var/log/bitcoin

RUN mkdir -p "${BITCOIN_DATA}" "${BITCOIN_CONF_DIR}" "${BITCOIN_LOG_DIR}" \
    && chown -R bitcoin:bitcoin "${BITCOIN_DATA}" "${BITCOIN_CONF_DIR}" "${BITCOIN_LOG_DIR}"

# RPC password file location (same as script)
ENV RPC_PASSWORD_FILE=/home/bitcoin/rpcpassword

COPY docker-entrypoint.sh /usr/local/bin/
# Strip CRLF (Windows line endings) so script works when run directly
RUN sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh && chmod 755 /usr/local/bin/docker-entrypoint.sh

# Expose RPC (8332) and ZMQ hashblock (28332) for optional host mapping
EXPOSE 8332 28332

VOLUME ["/var/lib/bitcoin", "/var/log/bitcoin"]
# Use bash explicitly so entrypoint runs even if file had CRLF (avoids shebang "bash\r" error)
ENTRYPOINT ["/usr/bin/env", "bash", "/usr/local/bin/docker-entrypoint.sh"]
CMD ["bitcoind", "-conf=/etc/bitcoin/bitcoin.conf", "-datadir=/var/lib/bitcoin"]
