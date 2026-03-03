#!/usr/bin/env bash
# =============================================================================
# Docker entrypoint for SC Node Bitcoin Core
# Mirrors bitcoin-install.sh: generate rpcauth/config if missing, create
# wallet "wallet" on first run, then run bitcoind as bitcoin user.
#
# SYNC: Config options (bitcoin.conf) and paths must be kept in sync with
# bitcoin-install.sh manually when that script is updated.
# =============================================================================
set -euo pipefail

BITCOIN_DATA="${BITCOIN_DATA:-/var/lib/bitcoin}"
BITCOIN_CONF_DIR="${BITCOIN_CONF_DIR:-/etc/bitcoin}"
BITCOIN_LOG_DIR="${BITCOIN_LOG_DIR:-/var/log/bitcoin}"
BITCOIN_CONF="${BITCOIN_CONF_DIR}/bitcoin.conf"
RPC_PASSWORD_FILE="${RPC_PASSWORD_FILE:-/home/bitcoin/rpcpassword}"

# Bind RPC/ZMQ to Docker network (e.g. aznet): set RPC_BIND=0.0.0.0, ZMQ_BIND=0.0.0.0, RPC_ALLOW_IP to network CIDR
RPC_BIND="${BITCOIN_RPC_BIND:-127.0.0.1}"
ZMQ_BIND="${BITCOIN_ZMQ_BIND:-127.0.0.1}"
RPC_ALLOW_IP="${BITCOIN_RPC_ALLOW_IP:-127.0.0.1}"

# Ensure volume dirs are owned by bitcoin (when using named volumes)
if [[ "$(id -u)" = "0" ]]; then
    chown -R bitcoin:bitcoin "${BITCOIN_DATA}" "${BITCOIN_CONF_DIR}" "${BITCOIN_LOG_DIR}" 2>/dev/null || true
fi

# Generate bitcoin.conf with rpcauth if not present (mirrors bitcoin-install.sh)
if [[ ! -f "${BITCOIN_CONF}" ]]; then
    RPCAUTH_OUTPUT=$(python3 /usr/local/bin/rpcauth.py satoshi 2>&1)
    RPCAUTH=$(echo "$RPCAUTH_OUTPUT" | grep -o '^rpcauth=satoshi:[0-9a-f]*\$[0-9a-f]*' || true)
    PASSWORD=$(echo "$RPCAUTH_OUTPUT" | tail -n 1 | tr -d '\r\n \t')

    if [[ -z "${RPCAUTH}" || -z "${PASSWORD}" ]]; then
        echo "ERROR: Failed to parse rpcauth.py output" >&2
        echo "$RPCAUTH_OUTPUT" >&2
        exit 1
    fi

    echo "${PASSWORD}" > "${RPC_PASSWORD_FILE}"
    chmod 600 "${RPC_PASSWORD_FILE}"
    [[ "$(id -u)" = "0" ]] && chown bitcoin:bitcoin "${RPC_PASSWORD_FILE}" "${BITCOIN_CONF}" 2>/dev/null || true

    # Same options as bitcoin-install.sh; daemon=0 for container foreground. RPC/ZMQ bind from env (see BITCOIN_RPC_BIND, BITCOIN_ZMQ_BIND, BITCOIN_RPC_ALLOW_IP).
    cat > "${BITCOIN_CONF}" << EOF
# Bitcoin configuration for SC Node (Docker - mirrors bitcoin-install.sh)
daemon=0
server=1
${RPCAUTH}
rpcbind=${RPC_BIND}
rpcallowip=${RPC_ALLOW_IP}
wallet=wallet
walletnotify=/usr/local/bin/wallet_event_append.sh %s %w
prune=131072
listen=0
zmqpubhashblock=tcp://${ZMQ_BIND}:28332
dbcache=4096
EOF
fi

# If no wallet exists yet, start bitcoind briefly to create "wallet" (mirrors install script).
# Run as bitcoin user so settings.json and all datadir files are owned by bitcoin (avoids permission errors).
if [[ ! -d "${BITCOIN_DATA}/wallets/wallet" && ! -d "${BITCOIN_DATA}/wallet" ]]; then
    run_btc() { if [[ "$(id -u)" = "0" ]]; then gosu bitcoin "$@"; else "$@"; fi; }
    run_btc bitcoind -conf="${BITCOIN_CONF}" -datadir="${BITCOIN_DATA}" &
    PID=$!
    READY=false
    for i in $(seq 1 300); do
        if run_btc bitcoin-cli -conf="${BITCOIN_CONF}" -datadir="${BITCOIN_DATA}" getblockchaininfo >/dev/null 2>&1; then
            READY=true
            break
        fi
        sleep 1
    done
    if ! $READY; then
        kill $PID 2>/dev/null || true
        echo "ERROR: RPC not ready; cannot create wallet" >&2
        exit 1
    fi
    run_btc bitcoin-cli -conf="${BITCOIN_CONF}" -datadir="${BITCOIN_DATA}" createwallet wallet 2>&1 || true
    run_btc bitcoin-cli -conf="${BITCOIN_CONF}" -datadir="${BITCOIN_DATA}" stop 2>/dev/null || true
    wait $PID 2>/dev/null || true
fi

# Ensure datadir is owned by bitcoin (fixes any files created as root, e.g. from earlier runs)
if [[ "$(id -u)" = "0" ]]; then
    chown -R bitcoin:bitcoin "${BITCOIN_DATA}" "${BITCOIN_LOG_DIR}" 2>/dev/null || true
fi

# Run as bitcoin user (gosu when entrypoint runs as root)
if [[ "$(id -u)" = "0" ]]; then
    exec gosu bitcoin "$@"
else
    exec "$@"
fi
