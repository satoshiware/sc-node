#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# AZCoin Core Configuration: Full Contributing Node for SC Node
# =============================================================================
# Purpose: Provides the AZCoin wallet for SC Node
#
# Key Characteristics:
#   • Full node (not pruned) → helps other nodes with block propagation and IBD
#   • Accepts inbound connections (listening node)
#   • Fully validates every block and transaction
#   • Relays blocks and transactions to the AZCoin network
#
# Philosophy:
#   The AZCoin network is still relatively small and needs more full nodes.
#   Every SC Node therefore runs a complete, cooperating AZCoin node.
#
# Inbound Connections & Central Routing:
#   When many SC Nodes share a limited number of public IP addresses as inbound
#   connections are routed through centralized servers, the following two settings
#   must be correctly in configured (azcoin.conf) for this node to be reachable by
#   other AZCoin peers:
#
#      externalip=   → The central infrastructure's public IP or VPN exit IP
#
#      port=         → The unique P2P listening port assigned to this specific SC Node.
#                      When multiple nodes share the same public IP, each must use
#                      a different port.
#
#   These settings allow the central infrastructure to properly forward incoming
#   connections to this node. If they are incorrect, this node will not receive
#   any inbound connections.
#
# Seeder / Trusted Nodes:
#   Unlike Bitcoin, AZCoin has no built-in DNS seed nodes. A fresh AZCoin node
#   will remain isolated and unable to find peers unless it is given at least one
#   reliable node to connect to via the addnode= parameter in azcoin.conf.
#
#   Organizations or entities deploying AZCoin nodes will need to provide dedicated
#   "seeder nodes" with good uptime and connectivity. These seeder nodes serve as
#   bootstrap points so new SC Nodes can connect and then gossip to discover the rest
#   of the network.
#
#   This install script will point the AZCoin node to azcoin-seed.satoshiware.org,
#   which uses round-robin DNS and the Internet's BGP routing protocol to
#   distribute load across multiple backend seeder nodes.
#
# Recommended ratio: One dedicated seeder node for every 500 SC Nodes.
#   Start with 1:500 and adjust based on sync performance and network load.
#
# The companion seeder node installation script is located at:
#   sc-node/azcoin-seeder-install.sh
#
# Important Note for Seeder Nodes:
#   Be sure to configure each seeder node to connect with several other prominent
#   and well-established AZCoin nodes using the addnode= parameter in azcoin.conf to
#   help ensure all nodes remain well-connected.
# =============================================================================

LOG_FILE="/var/log/azcoin-install.log"
log() {
    echo "$*" | tee -a "$LOG_FILE"
}

# Installation source (tar.gz - used only during install phase)
AZCOIN_BIN_PARENT="/root/sc-node"

# Runtime / credential files (generated during setup)
RPC_PASSWORD_DIR="/home/azcoin"
RPC_PASSWORD_FILE="${RPC_PASSWORD_DIR}/rpcpassword"

# Documentation
README_DIR="/usr/local/share/doc"
README_FILE="${README_DIR}/azcoin.txt"

log "Starting AZCoin Core setup: $(date)"
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
log "Looking for AZCoin tarball in ${AZCOIN_BIN_PARENT}..."

TAR_FILE=$(find "${AZCOIN_BIN_PARENT}" -maxdepth 1 -type f -name 'azcoin-*-linux-gnu.tar.gz' -print -quit)
if [[ -z "${TAR_FILE}" ]]; then
    log "No local tarball found. Auto-detecting CPU architecture and downloading latest versioned AZCoin release (skipping 'Latest' meta-tag)..."

    # Create directory if it doesn't exist
    mkdir -p "${AZCOIN_BIN_PARENT}"
    cd "${AZCOIN_BIN_PARENT}"

    # Detect architecture
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

    # Get all releases and skip the "Latest" meta-tag, take the first real versioned one
    log "Fetching releases from GitHub and skipping meta-tag 'Latest'..."
    API_RESPONSE=$(curl -s https://api.github.com/repos/satoshiware/azcoin/releases)

    # Extract the first tag that is NOT exactly "Latest"
    LATEST_TAG=$(echo "$API_RESPONSE" | grep -o '"tag_name": "[^"]*"' | cut -d '"' -f4 | grep -v '^Latest$' | head -n 1)

    LATEST_VERSION=${LATEST_TAG#v}   # remove leading 'v' if present

    if [[ -z "${LATEST_VERSION}" || "${LATEST_VERSION}" == "null" ]]; then
        log "ERROR: Could not find any versioned release (only 'Latest' meta-tag found)."
        exit 1
    fi

    log "Latest versioned release detected: ${LATEST_TAG} → ${LATEST_VERSION} (${ARCH_SUFFIX})"

    # AZCoin naming pattern (as used in your releases)
    TAR_NAME="azcoin_azcoin-${LATEST_VERSION}-${ARCH_SUFFIX}.tar.gz"
    DOWNLOAD_URL="https://github.com/satoshiware/azcoin/releases/download/${LATEST_TAG}/${TAR_NAME}"

    log "Downloading ${TAR_NAME}..."
    if curl -L --fail --progress-bar -o "${TAR_NAME}" "${DOWNLOAD_URL}"; then
        TAR_FILE="${AZCOIN_BIN_PARENT}/${TAR_NAME}"
        log "Download successful: ${TAR_FILE}"
    else
        log "ERROR: Download failed for ${DOWNLOAD_URL}"
        log "Possible causes: asset name mismatch on GitHub or network issue."
        exit 1
    fi
else
    log "Using existing local tarball: ${TAR_FILE}"
fi

# ===================== CREATE USER/GROUP =====================
if ! id "azcoin" &>/dev/null; then
    log "Creating system user/group: azcoin/azcoin"
    groupadd --system azcoin
    useradd --system --gid azcoin --create-home --home-dir "/home/azcoin" \
            --shell /usr/sbin/nologin --comment "AZCoin Core daemon" "azcoin"
else
    log "User azcoin already exists."
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
if [[ ! -x "${EXTRACTED_DIR}/bin/azcoind" ]]; then
    log "Error: azcoind not found in ${EXTRACTED_DIR}/bin/ — cannot continue"
    exit 1
fi

if [[ ! -x "${EXTRACTED_DIR}/bin/azcoin-cli" ]]; then
    log "Error: azcoin-cli not found in ${EXTRACTED_DIR}/bin/ — required for this setup"
    exit 1
fi

if [[ ! -f "${EXTRACTED_DIR}/share/rpcauth/rpcauth.py" ]]; then
    log "Error: rpcauth.py not found in ${EXTRACTED_DIR}/share/rpcauth/ — required for secure RPC auth generation"
    exit 1
fi

log "All required files found — installing binaries..."

# Install azcoind
install -m 0755 -o root -g root -D "${EXTRACTED_DIR}/bin/azcoind" /usr/local/bin/azcoind
log "Installed azcoind (root:root, 755)"

# Install azcoin-cli
install -m 0755 -o root -g root -D "${EXTRACTED_DIR}/bin/azcoin-cli" /usr/local/bin/azcoin-cli
log "Installed azcoin-cli (root:root, 755)"

# Install rpcauth.py (utility script)
install -m 0755 -o root -g root -D "${EXTRACTED_DIR}/share/rpcauth/rpcauth.py" /usr/local/bin/rpcauth.py
log "Installed rpcauth.py to /usr/local/bin/ (root:root, 755)"

# ===================== CONFIG & RPC PASSWORD =====================
if [[ ! -f /etc/azcoin/azcoin.conf ]]; then
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
    chown azcoin:azcoin "${RPC_PASSWORD_FILE}"
    chmod 600 "${RPC_PASSWORD_FILE}"
    log "RPC password saved to ${RPC_PASSWORD_FILE} (600 perms)"

    log "Creating configuration directory: /etc/azcoin"
    mkdir -p /etc/azcoin
    chown azcoin:azcoin /etc/azcoin
    chmod 755 "/etc/azcoin" # owner rwx, group rx, others none — secure but readable by group if needed
    log "Config dir created with ownership azcoin:azcoin and chmod 755"

    log "Creating azcoin.conf..."
    cat > /etc/azcoin/azcoin.conf << EOF
# AZCoin configuration for SC Node (bare metal)
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

# IP address your node will advertise to the network so other nodes can connect inbound.
# Use your VPN exit IP, VPS public IP, or home public IP here. Update as needed.
externalip=192.0.2.1

# P2P listening port for incoming connections from other nodes/peers (Default is 19333)
port=12345

# Force persistent outbound connection to specific trusted peer(s)
addnode=azcoin-seed.satoshiware.org

# Auto-load our named wallet
wallet=wallet

# Walletnotify: trigger script on tx events (unconf, conf, sends, RBF)
# Logs to wallet_events.log in home dir
walletnotify=/usr/local/bin/azcoin_wallet_event_append.sh %s %w

# assumevalid: default enabled - uses built-in checkpoint
# Skips sig/script checks on old blocks → 2-5x faster initial sync
# Still verifies PoW, headers, UTXOs fully

# Limit total upload of old blocks to MiB/day
# Generous amount, but prevents abuse
maxuploadtarget=5000

# ZMQ: publish new block hash locally (for real-time monitoring)
zmqpubhashblock=tcp://127.0.0.1:29334

# UTXO cache: 2 GB for faster sync/validation
# Safe on 32+ GB RAM hosts; prevents OOM/swap
dbcache=2048
EOF

    chown azcoin:azcoin /etc/azcoin/azcoin.conf
    chmod 644 /etc/azcoin/azcoin.conf
fi

# ===================== WALLET NOTIFY SCRIPT =====================
log "Creating walletnotify script..."
cat > /usr/local/bin/azcoin_wallet_event_append.sh << EOF
#!/usr/bin/env bash
# azcoin_wallet_event_append.sh - Append-only logger for walletnotify

TIMESTAMP=\$(date -u +"%Y-%m-%dT%H:%M:%SZ")
TXID="\$1"
WALLET="\$2"

echo "\${TIMESTAMP} | \${TXID} | \${WALLET}" >> /var/log/azcoin/wallet_events.log

exit 0
EOF
chmod 755 /usr/local/bin/azcoin_wallet_event_append.sh

# ===================== SYMLINK FOR FHS-COMPLIANT LOG LOCATION =====================
LOG_SYMLINK="/var/log/azcoin/debug.log"
mkdir -p /var/log/azcoin
ln -sfn /var/lib/azcoin/debug.log "${LOG_SYMLINK}"
chown -h azcoin:azcoin "${LOG_SYMLINK}"
log "Created FHS log symlink: ${LOG_SYMLINK} → /var/lib/azcoin/debug.log"

# ===================== LOGROTATE =====================
log "Configuring logrotate..."
cat > /etc/logrotate.d/azcoin << EOF
${LOG_SYMLINK} {
    daily
    rotate 14
    compress
    missingok
    notifempty
    create 0640 azcoin azcoin
    sharedscripts
    postrotate
        killall -USR1 azcoind 2>/dev/null || true
    endscript
}
EOF

# ===================== SYSTEMD SERVICE (HARDENED + ENHANCED) =====================
log "Installing ultra-hardened systemd service..."
cat > /etc/systemd/system/azcoind.service << EOF
[Unit]
Description=AZCoin Core daemon (SC Node)
After=network.target

[Service]
ExecStart=/usr/local/bin/azcoind -conf=/etc/azcoin/azcoin.conf -datadir=/var/lib/azcoin
User=azcoin
Group=azcoin
Type=forking
PIDFile=/var/lib/azcoin/azcoind.pid
Restart=always
RestartSec=60
TimeoutSec=300
LimitNOFILE=65536

# Hardening / sandboxing (AZCoin Core compatible + advanced)
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
StateDirectory=azcoin
StateDirectoryMode=0710

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable azcoind.service
log "Systemd service installed (ultra-hardened). Check: systemd-analyze security azcoind"

# ===================== WALLET CREATION =====================
log "Starting azcoind temporarily to create wallet..."
systemctl start azcoind
sleep 2 # Brief wait for RPC socket

log "Waiting for azcoind RPC readiness (up to 300s)..."
READY=false
for i in {1..300}; do
    if sudo -u azcoin azcoin-cli -conf=/etc/azcoin/azcoin.conf -datadir=/var/lib/azcoin getblockchaininfo >/dev/null 2>&1; then
        READY=true
        log "azcoind RPC ready after ${i} seconds."
        break
    fi
    printf "."
    sleep 1
done
echo "" >> "$LOG_FILE"

if ! $READY; then
    log "ERROR: RPC not ready after 5 minutes. Failing install. Check debug.log and hardware/resources."
    systemctl stop azcoind
    exit 1
fi

log "Creating wallet 'wallet' if missing"
WALLET_OUTPUT=$(sudo -u azcoin azcoin-cli -conf=/etc/azcoin/azcoin.conf -datadir=/var/lib/azcoin createwallet wallet 2>&1)
if echo "$WALLET_OUTPUT" | grep -q '"name": "wallet"'; then
    log "Wallet 'wallet' created successfully."
elif echo "$WALLET_OUTPUT" | grep -q "Database already exists"; then
    log "Wallet 'wallet' already exists — skipping."
else
    log "ERROR: Wallet creation failed unexpectedly!"
    log "Output from azcoin-cli:"
    log "$WALLET_OUTPUT"
    log "Failing install. Check azcoin.conf, RPC settings, disk space, or permissions."
    systemctl stop azcoind
    exit 1
fi

log "azcoind is now running (systemctl start azcoind was issued). You can stop/restart as needed."

# ===================== Create/Update Files w/ Correct Owners/Permissions =====================
chmod 640 /var/lib/azcoin/debug.log
touch /var/log/azcoin/wallet_events.log
chown azcoin:azcoin /var/log/azcoin/wallet_events.log
chmod 640 /var/log/azcoin/wallet_events.log

# ===================== Add azc alias if it does not already exist =====================
TARGET="/etc/bash.bashrc"
AZC_ALIAS="alias azc='sudo -u azcoin azcoin-cli -conf=/etc/azcoin/azcoin.conf -datadir=/var/lib/azcoin'"
if ! grep -Fxq "$AZC_ALIAS" "$TARGET"; then
    echo "$AZC_ALIAS" | tee -a "$TARGET" > /dev/null
    log "Added azc alias to $TARGET"
else
    log "azc alias already present"
fi

# ===================== README =====================
log "Creating system-wide documentation README..."
mkdir -p "${README_DIR}"

cat > "${README_FILE}" << EOF
# SC Node - AZCoin Core (Bare Metal)
- Use the "azc" alias to invoke the command-line interface

## Key Files
- binaries directory: /usr/local/bin (755 root:root)
    azcoind (755 root:root)
    azcoin-cli (755 root:root)
    rpcauth.py (755 root:root)
    azcoin_wallet_event_append.sh (755 root:root)

- blockchain data directory: /var/lib/azcoin (710 azcoin:azcoin)
    .cookie (600 azcoin:azcoin)
    debug.log (640 azcoin:azcoin)
    wallet directory: /var/lib/azcoin/wallet (700 azcoin:azcoin)
        wallet.dat (600 azcoin:azcoin)

- configuration directory: /etc/azcoin (755 azcoin:azcoin)
    azcoin.conf: /etc/azcoin/azcoin.conf (644 azcoin:azcoin)

- log rotate configuration: /etc/logrotate.d/azcoin (644 root:root)

- log directory location: /var/log/azcoin (755 root:root)
    symlink to /var/lib/azcoin/debug.log (640 azcoin:azcoin)
    wallet_events.log (640 azcoin:azcoin)

- rpcpassword: ${RPC_PASSWORD_FILE} (600 azcoin:azcoin)
    rpcpassword directory: ${RPC_PASSWORD_DIR} (700 azcoin:azcoin)

- azcoin-install setup log file: ${LOG_FILE} (644 root:root)

- systemd service file: /etc/systemd/system/azcoind.service (644 root:root)

## Management
- Start/Stop: sudo systemctl start/stop azcoind
- Status/Logs: sudo systemctl status azcoind or sudo journalctl -u azcoind -f
- RPC Test (.cookie authentication): sudo -u azcoin azcoin-cli -conf=/etc/azcoin/azcoin.conf -datadir=/var/lib/azcoin getblockchaininfo
- RPC Test (rpcauth authentication):
    PASSWORD=$(sudo cat /home/azcoin/rpcpassword)
    curl --data-binary '{"jsonrpc":"1.0","id":"test","method":"getblockchaininfo","params":[]}' \
        -H 'content-type: text/plain;' \
        --user "satoshi:$PASSWORD" \
        http://127.0.0.1:19332/

## Notes
- Pruned (~128 GB final)
- RPC: localhost only (127.0.0.1:19332)
- P2P: Port 19333
- ZMQ New Block Hash (zmqpubhashblock): 127.0.0.1:29334
- Username: satoshi Password: sudo cat ${RPC_PASSWORD_FILE}
EOF

log "Setup complete!"
log "azcoin-install setup log file: ${LOG_FILE}"
log "Readme file: ${README_FILE}"