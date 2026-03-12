#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# SC Node - AZCoin Core Installation Script (Bare Metal)
#
# Script Testing Prerequisites: Make sure azcoin .tar.gz is available
#   apt update && sudo apt full-upgrade -y && sudo apt autoremove -y && sudo apt autoclean
#   apt install -y curl python3 python-is-python3 # In WSL, Python is not installed by default (required for rpcauth.py script)
#   VERSION=0.1.2
#   curl -OL https://github.com/satoshiware/azcoin/releases/download/${VERSION}/azcoin_azcoin-x86_64-linux-gnu.tar.gz
# =============================================================================

LOG_FILE="/var/log/setup-azcoin.log"
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [azcoin-install] $*" | tee -a "$LOG_FILE"
}

# Installation source (tar.gz - used only during install phase)
AZCOIN_BIN_PARENT="/root/sc-node"

# Runtime / credential files (generated during setup)
RPC_PASSWORD_DIR="/home/azcoin"
RPC_PASSWORD_FILE="${RPC_PASSWORD_DIR}/rpcpassword"

# Documentation
README_DIR="/usr/local/share/doc"
README_FILE="${README_DIR}/azcoin.txt"

# ===================== CHECKS =====================
if [[ $EUID -ne 0 ]]; then
    log "Error: Must run as root (sudo)."
    exit 1
fi

# Check that 'python' command exists and points to python3
if ! command -v python >/dev/null 2>&1; then
    echo -e "Error! 'python' command not found"
    echo "   You need 'python' to point to python3 (common for rpcauth.py and many scripts)"
    echo "   Run: apt install -y python-is-python3"
    exit 1
elif ! python --version 2>&1 | grep -q "Python 3"; then
    echo -e "Error! 'python' command exists but is not Python 3"
    python --version
    echo "   You need Python 3 (rpcauth.py requires it)"
    exit 1
else
    echo -e "'python' command points to Python 3"
fi

log "Starting AZCoin Core setup..."

# Find the first azcoin*.tar.gz
TAR_FILE=$(find "${AZCOIN_BIN_PARENT}" -maxdepth 1 -type f -name 'azcoin*.tar.gz' -print -quit)
if [[ -z "${TAR_FILE}" ]]; then
    log "Error: No azcoin*.tar.gz found in ${AZCOIN_BIN_PARENT}"
    exit 1
fi
log "Using tarball: ${TAR_FILE}"

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
    RPCAUTH=$(echo "$RPCAUTH_OUTPUT" | grep -o '^rpcauth=satoshi:[0-9a-f]\+\$[0-9a-f]\+') # Extract rpcauth line (starts with rpcauth=)
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
    PASSWORD="CLEARING MEMORY!!!!!!!!!!!!!!!!!!!!!!!"
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