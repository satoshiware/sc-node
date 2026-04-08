#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Bitcoin Core Configuration: Pruned, Outbound-Only, and a Silent Contributor
# =============================================================================
# Purpose: Provides the BTC wallet for the SC Node
#
# Key Characteristics:
#   • Pruned mode → low disk usage, fast deployment
#   • Outbound-only (listen=0 + discover=0) → zero inbound connections
#   • Fully validates every block and transaction
#   • Relays new blocks and transactions to the network
#
# Compensation Strategy:
#   Because this node is pruned, outbound-only, and silent, it cannot serve
#   historical blocks to other nodes during their Initial Block Download (IBD).
#   It is therefore more of a "taker" than a "giver" to the broader network.
#
#   Any organization deploying hundreds or thousands of SC Nodes is strongly
#   encouraged to run additional full archival (non-pruned, listening) Bitcoin
#   nodes to help offset this. Example ratio: one full archival Bitcoin node
#   for every 1000 pruned SC Nodes. Use the sc-node/bitcoin-feeder-install.sh
#   install script to set up one of these nodes with the proper configuration.
#
# IBD Acceleration:
#   bitcoin.conf options: blocksonly=1, higher dbcache, and local connect
# =============================================================================

LOG_FILE="/var/log/bitcoin-install.log"
log() {
    echo "$*" | tee -a "$LOG_FILE"
}

# Installation source (tar.gz - used only during install phase)
BITCOIN_BIN_PARENT="/root/sc-node"

# Runtime / credential files (generated during setup)
RPC_PASSWORD_DIR="/home/bitcoin"
RPC_PASSWORD_FILE="${RPC_PASSWORD_DIR}/rpcpassword"

# Documentation
README_DIR="/usr/local/share/doc"
README_FILE="${README_DIR}/bitcoin.txt"

log "Starting Bitcoin Core setup: $(date)"
# ===================== CHECKS =====================
if [[ $EUID -ne 0 ]]; then
    log "Error: Must run as root (sudo)."
    exit 1
fi

# Checking for 'python' command (required for rpcauth.py)
if ! command -v python >/dev/null 2>&1; then
    log "'python' command not found. Installing python-is-python3..."
    apt-get update -qq
    apt-get install -y python-is-python3
    if ! command -v python >/dev/null 2>&1; then
        log "ERROR: Failed to install python-is-python3. Cannot continue."
        exit 1
    fi
    log "'python' command successfully installed and linked to Python 3."
elif ! python --version 2>&1 | grep -q "Python 3"; then
    log "Warning: 'python' command exists but is not Python 3. Installing python-is-python3..."
    apt-get update -qq
    apt-get install -y python-is-python3
    if ! python --version 2>&1 | grep -q "Python 3"; then
        log "ERROR: Still cannot get Python 3 via 'python' command."
        exit 1
    fi
    log "'python' now correctly points to Python 3."
else
    log "'python' command points to Python 3. Good!"
fi

# ===================== TAR FILE CHECK & AUTO-DOWNLOAD LATEST =====================
log "Looking for Bitcoin Core tarball in ${BITCOIN_BIN_PARENT}..."

TAR_FILE=$(find "${BITCOIN_BIN_PARENT}" -maxdepth 1 -type f -name 'bitcoin-*-linux-gnu.tar.gz' -print -quit)
if [[ -z "${TAR_FILE}" ]]; then
    log "No local tarball found. Auto-detecting CPU architecture and downloading latest Bitcoin Core..."

    # Create directory if it doesn't exist
    mkdir -p "${BITCOIN_BIN_PARENT}"
    cd "${BITCOIN_BIN_PARENT}"

    # Detect architecture (x86_64, aarch64, and riscv64)
    case $(uname -m) in
        x86_64)
            ARCH_SUFFIX="x86_64-linux-gnu"
            ;;
        aarch64|arm64)
            ARCH_SUFFIX="aarch64-linux-gnu"
            ;;
        riscv64)
            ARCH_SUFFIX="riscv64-linux-gnu"
            ;;
        *)
            log "ERROR: Unsupported CPU architecture: $(uname -m)"
            log "Supported architectures: x86_64, aarch64/arm64, riscv64"
            exit 1
            ;;
    esac

    # Get latest version from GitHub API (always current, no hard-coded version)
    log "Fetching latest version from GitHub..."
    LATEST_TAG=$(curl -s https://api.github.com/repos/bitcoin/bitcoin/releases/latest | grep '"tag_name":' | cut -d '"' -f4)
    LATEST_VERSION=${LATEST_TAG#v}   # remove leading 'v' if present

    if [[ -z "${LATEST_VERSION}" ]]; then
        log "ERROR: Could not determine latest Bitcoin Core version."
        exit 1
    fi

    log "Latest version detected: ${LATEST_VERSION} (${ARCH_SUFFIX})"

    TAR_NAME="bitcoin-${LATEST_VERSION}-${ARCH_SUFFIX}.tar.gz"
    DOWNLOAD_URL="https://bitcoincore.org/bin/bitcoin-core-${LATEST_VERSION}/${TAR_NAME}"

    log "Downloading ${TAR_NAME}..."
    if curl -L --fail --progress-bar -o "${TAR_NAME}" "${DOWNLOAD_URL}"; then
        TAR_FILE="${BITCOIN_BIN_PARENT}/${TAR_NAME}"
        log "Download successful: ${TAR_FILE}"
    else
        log "ERROR: Download failed for ${DOWNLOAD_URL}"
        log "Check internet connection or if the architecture is supported."
        exit 1
    fi
else
    log "Using existing local tarball: ${TAR_FILE}"
fi

# ===================== CREATE USER/GROUP =====================
if ! id "bitcoin" &>/dev/null; then
    log "Creating system user/group: bitcoin/bitcoin"
    groupadd --system bitcoin
    useradd --system --gid bitcoin --create-home --home-dir "/home/bitcoin" \
            --shell /usr/sbin/nologin --comment "Bitcoin Core daemon" "bitcoin"
else
    log "User bitcoin already exists."
fi

# ===================== EXTRACT & INSTALL BINARIES =====================
TMP_EXTRACT=$(mktemp -d)
trap 'rm -rf "${TMP_EXTRACT}"' EXIT

log "Extracting tarball..."
tar -xzf "${TAR_FILE}" -C "${TMP_EXTRACT}"

EXTRACTED_DIR=$(find "${TMP_EXTRACT}" -mindepth 1 -maxdepth 1 -type d | head -n 1)
if [[ ! -d "${EXTRACTED_DIR}" ]]; then
    log "Error: Could not find extracted directory after tar extraction"
    exit 1
fi

# Check required binaries/scripts
if [[ ! -x "${EXTRACTED_DIR}/bin/bitcoind" ]]; then
    log "Error: bitcoind not found in ${EXTRACTED_DIR}/bin/ — cannot continue"
    exit 1
fi

if [[ ! -x "${EXTRACTED_DIR}/bin/bitcoin-cli" ]]; then
    log "Error: bitcoin-cli not found in ${EXTRACTED_DIR}/bin/ — required for this setup"
    exit 1
fi

if [[ ! -f "${EXTRACTED_DIR}/share/rpcauth/rpcauth.py" ]]; then
    log "Error: rpcauth.py not found in ${EXTRACTED_DIR}/share/rpcauth/ — required for secure RPC auth generation"
    exit 1
fi

log "All required files found — installing binaries..."

# Install bitcoind
install -m 0755 -o root -g root -D "${EXTRACTED_DIR}/bin/bitcoind" /usr/local/bin/bitcoind
log "Installed bitcoind (root:root, 755)"

# Install bitcoin-cli
install -m 0755 -o root -g root -D "${EXTRACTED_DIR}/bin/bitcoin-cli" /usr/local/bin/bitcoin-cli
log "Installed bitcoin-cli (root:root, 755)"

# Install rpcauth.py (utility script)
install -m 0755 -o root -g root -D "${EXTRACTED_DIR}/share/rpcauth/rpcauth.py" /usr/local/bin/rpcauth.py
log "Installed rpcauth.py to /usr/local/bin/ (root:root, 755)"

# ===================== CONFIG & RPC PASSWORD =====================
if [[ ! -f /etc/bitcoin/bitcoin.conf ]]; then
    RPCAUTH_OUTPUT=$(python /usr/local/bin/rpcauth.py satoshi 2>&1) # Run rpcauth.py directly (shebang handles python invocation)
    RPCAUTH=$(echo "$RPCAUTH_OUTPUT" | grep -o '^rpcauth=satoshi:.*') # Extract rpcauth line (starts with rpcauth=)
    PASSWORD=$(echo "$RPCAUTH_OUTPUT" | tail -n 1 | tr -d '\r\n \t')

    # Safety check — fail if parsing didn't work
    if [[ -z "$RPCAUTH" || -z "$PASSWORD" ]]; then
        log "ERROR: Failed to parse rpcauth.py output — cannot continue"
        log "Full output from rpcauth.py:"
        log "$RPCAUTH_OUTPUT"
        exit 1
    fi
    log "rpcauth.py generated successfully: $RPCAUTH"

    umask 077 # umask 077 → new files get 0600 (rw-------), dirs 0700 (rwx------)
    echo "${PASSWORD}" > "${RPC_PASSWORD_FILE}"
    umask 02 # Restore standard umask (files 0644, dirs 0755)
    chown bitcoin:bitcoin "${RPC_PASSWORD_FILE}"
    chmod 600 "${RPC_PASSWORD_FILE}"
    log "RPC password saved to ${RPC_PASSWORD_FILE} (600 perms)"

    log "Creating configuration directory: /etc/bitcoin"
    mkdir -p /etc/bitcoin
    chown bitcoin:bitcoin /etc/bitcoin
    chmod 755 "/etc/bitcoin" # owner rwx, group rx, others none — secure but readable by group if needed
    log "Config dir created with ownership bitcoin:bitcoin and chmod 755"

    log "Creating bitcoin.conf..."
    cat > /etc/bitcoin/bitcoin.conf << EOF
# Bitcoin configuration for SC Node (pruned mode, bare metal)
# Non-default settings with rationale

# Run as daemon (background) - required for systemd/headless operation
daemon=1

# Enable RPC for local tools/monitoring
server=1

# Hashed RPC auth (secure, no plain password here)
${RPCAUTH}

# Bind RPC to localhost only - critical security measure on bare metal
rpcbind=127.0.0.1

# Restrict RPC callers to localhost
rpcallowip=127.0.0.1

# Control network/internet traffic during IBD
# Disabled all other p2p connections
# UPDATE CONNECT
#connect=bitcoin-ibd.internal

# Auto-load our named wallet
wallet=wallet

# Walletnotify: trigger script on tx events (unconf, conf, sends, RBF)
# Logs to wallet_events.log in home dir
walletnotify=/usr/local/bin/bitcoin_wallet_event_append.sh %s %w

# assumevalid: default enabled - uses built-in checkpoint
# Skips sig/script checks on old blocks → 2-5x faster initial sync
# Still verifies PoW, headers, UTXOs fully

# Pruning: retain ~128 GB recent blocks + chainstate
# Saves disk vs full chain (~650+ GB); full validation preserved
prune=131072

# Outbound-only (no incoming connections)
# Minimizes bandwidth (~20-50 GB/mo outbound), no public port needed
listen=0

# Do not advertise our IP address
# Makes the node invisible to node crawlers and the broader network
discover=0

# Limit total upload of old blocks to MiB/day
# Generous amount, but prevents abuse
maxuploadtarget=5000

# ZMQ: publish new block hash locally (for real-time monitoring)
zmqpubhashblock=tcp://127.0.0.1:28332

# UTXO cache: 6 GB for faster sync/validation; Safe on 32+ GB RAM hosts; prevents OOM/swap
# Use more RAM (e.g. 8192 to 16384) to speed up IBD
# UPDATE DBCACHE
dbcache=6144

# Set to 1 to skip transaction relay during IBD → much faster sync
# UPDATE BLOCKSONLY
blocksonly=0
EOF

    chown bitcoin:bitcoin /etc/bitcoin/bitcoin.conf
    chmod 644 /etc/bitcoin/bitcoin.conf
fi

# ===================== WALLET NOTIFY SCRIPT =====================
log "Creating walletnotify script..."
cat > /usr/local/bin/bitcoin_wallet_event_append.sh << EOF
#!/usr/bin/env bash
# bitcoin_wallet_event_append.sh - Append-only logger for walletnotify

TIMESTAMP=\$(date -u +"%Y-%m-%dT%H:%M:%SZ")
TXID="\$1"
WALLET="\$2"

echo "\${TIMESTAMP} | \${TXID} | \${WALLET}" >> /var/log/bitcoin/wallet_events.log

exit 0
EOF
chmod 755 /usr/local/bin/bitcoin_wallet_event_append.sh

# ===================== SYMLINK FOR FHS-COMPLIANT LOG LOCATION =====================
LOG_SYMLINK="/var/log/bitcoin/debug.log"
mkdir -p /var/log/bitcoin
ln -sfn /var/lib/bitcoin/debug.log "${LOG_SYMLINK}"
chown -h bitcoin:bitcoin "${LOG_SYMLINK}"
log "Created FHS log symlink: ${LOG_SYMLINK} → /var/lib/bitcoin/debug.log"

# ===================== LOGROTATE =====================
log "Configuring logrotate..."
cat > /etc/logrotate.d/bitcoin << EOF
/var/lib/bitcoin/debug.log {
    daily
    rotate 14
    compress
    missingok
    notifempty
    create 0640 bitcoin bitcoin
    sharedscripts
    postrotate
        killall -USR1 bitcoind 2>/dev/null || true
    endscript
}
EOF

# ===================== SYSTEMD SERVICE (HARDENED + ENHANCED) =====================
log "Installing ultra-hardened systemd service..."
cat > /etc/systemd/system/bitcoind.service << EOF
[Unit]
Description=Bitcoin Core daemon (SC Node - pruned)
After=network.target

[Service]
ExecStart=/usr/local/bin/bitcoind -conf=/etc/bitcoin/bitcoin.conf -datadir=/var/lib/bitcoin
User=bitcoin
Group=bitcoin
Type=forking
PIDFile=/var/lib/bitcoin/bitcoind.pid
Restart=always
RestartSec=60
TimeoutSec=300
LimitNOFILE=65536

# Hardening / sandboxing (Bitcoin Core compatible + advanced)
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
NoNewPrivileges=yes
RestrictNamespaces=yes
RestrictRealtime=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
MemoryDenyWriteExecute=yes
ProtectHostname=yes
PrivateUsers=yes
CapabilityBoundingSet=
StateDirectory=bitcoin
StateDirectoryMode=0710

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable bitcoind.service
log "Systemd service installed (ultra-hardened). Check: systemd-analyze security bitcoind"

# ===================== WALLET CREATION =====================
log "Starting bitcoind temporarily to create wallet..."
systemctl start bitcoind
sleep 2  # Brief wait for RPC socket

log "Waiting for bitcoind RPC readiness (up to 300s)..."
READY=false
for i in {1..300}; do
    if sudo -u bitcoin bitcoin-cli -conf=/etc/bitcoin/bitcoin.conf -datadir=/var/lib/bitcoin getblockchaininfo >/dev/null 2>&1; then
        READY=true
        log "bitcoind RPC ready after ${i} seconds."
        break
    fi
    printf "."
    sleep 1
done
echo "" >> "$LOG_FILE"

if ! $READY; then
    log "ERROR: RPC not ready after 5 minutes. Failing install. Check debug.log and hardware/resources."
    systemctl stop bitcoind
    exit 1
fi

log "Creating wallet 'wallet' if missing"
WALLET_OUTPUT=$(sudo -u bitcoin bitcoin-cli -conf=/etc/bitcoin/bitcoin.conf -datadir=/var/lib/bitcoin createwallet wallet 2>&1)
if echo "$WALLET_OUTPUT" | grep -q '"name": "wallet"'; then
    log "Wallet 'wallet' created successfully."
elif echo "$WALLET_OUTPUT" | grep -q "Database already exists"; then
    log "Wallet 'wallet' already exists — skipping."
else
    log "ERROR: Wallet creation failed unexpectedly!"
    log "Output from bitcoin-cli:"
    log "$WALLET_OUTPUT"
    log "Failing install. Check bitcoin.conf, RPC settings, disk space, or permissions."
    systemctl stop bitcoind
    exit 1
fi

log "bitcoind is now running (systemctl start bitcoind was issued). You can stop/restart as needed."

# ===================== Create/Update Files w/ Correct Owners/Permissions =====================
chmod 640 /var/lib/bitcoin/debug.log
touch /var/log/bitcoin/wallet_events.log
chown bitcoin:bitcoin /var/log/bitcoin/wallet_events.log
chmod 640 /var/log/bitcoin/wallet_events.log

# ===================== Add btc alias if it does not already exist =====================
TARGET="/etc/bash.bashrc"
BTC_ALIAS="alias btc='sudo -u bitcoin bitcoin-cli -conf=/etc/bitcoin/bitcoin.conf -datadir=/var/lib/bitcoin'"
if ! grep -Fxq "$BTC_ALIAS" "$TARGET"; then
    echo "$BTC_ALIAS" | tee -a "$TARGET" > /dev/null
    log  "Added btc alias to $TARGET"
else
    log  "btc alias already present"
fi

# ===================== README =====================
log "Creating system-wide documentation README..."
mkdir -p "${README_DIR}"

cat > "${README_FILE}" << EOF
# SC Node - Bitcoin Core (Bare Metal)
- Use the "btc" alias to invoke the command-line interface

## Key Files
- binaries directory: /usr/local/bin (755 root:root)
    bitcoind (755 root:root)
    bitcoin-cli (755 root:root)
    rpcauth.py (755 root:root)
    bitcoin_wallet_event_append.sh (755 root:root)

- blockchain data directory: /var/lib/bitcoin (710 bitcoin:bitcoin)
    .cookie (600 bitcoin:bitcoin)
    debug.log (640 bitcoin:bitcoin)
    wallet directory: /var/lib/bitcoin/wallet (700 bitcoin:bitcoin)
        wallet.dat (600 bitcoin:bitcoin)

- configuration directory: /etc/bitcoin (755 bitcoin:bitcoin)
    bitcoin.conf: /etc/bitcoin/bitcoin.conf (644 bitcoin:bitcoin)

- log rotate configuration: /etc/logrotate.d/bitcoin (644 root:root)

- log directory location: /var/log/bitcoin (755 root:root)
    symlink to /var/lib/bitcoin/debug.log (640 bitcoin:bitcoin)
    wallet_events.log (640 bitcoin:bitcoin)

- rpcpassword directory: ${RPC_PASSWORD_DIR} (700 bitcoin:bitcoin)
    rpcpassword: ${RPC_PASSWORD_FILE} (600 bitcoin:bitcoin)

- bitcoin-install setup log file: ${LOG_FILE} (644 root:root)

- systemd service file: /etc/systemd/system/bitcoind.service (644 root:root)

## Management
- Start/Stop: sudo systemctl start/stop bitcoind
- Status/Logs: sudo systemctl status bitcoind   or   sudo journalctl -u bitcoind -f
- RPC Test (.cookie authentication): sudo -u bitcoin bitcoin-cli -conf=/etc/bitcoin/bitcoin.conf -datadir=/var/lib/bitcoin getblockchaininfo
- RPC Test (rpcauth authentication):
    PASSWORD=\$(sudo cat /home/bitcoin/rpcpassword)
    curl --data-binary '{"jsonrpc":"1.0","id":"test","method":"getblockchaininfo","params":[]}' \
        -H 'content-type: text/plain;' \
        --user "satoshi:\$PASSWORD" \
        http://127.0.0.1:8332/

## Notes
- Pruned (~128 GB final)
- RPC: localhost only (127.0.0.1:8332)
- ZMQ New Block Hash (zmqpubhashblock): 127.0.0.1:28332
- Username: satoshi   Password: sudo cat ${RPC_PASSWORD_FILE}
EOF

log "Setup complete!"
log "bitcoin-install setup log file: ${LOG_FILE}"
log "Readme file: ${README_FILE}"