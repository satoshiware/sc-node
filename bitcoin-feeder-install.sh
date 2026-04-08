#!/usr/bin/env bash
set -euo pipefail
# =============================================================================
# Bitcoin Core Feeder Node Installation Script (Full Archival)
# =============================================================================
# Purpose: This script installs a full, non-pruned, listening Bitcoin Core node.
#
# Key Characteristics:
#   • Full archival node (prune=0)
#   • Listening node (accepts inbound connections)
#   • blocks-only mode for better performance
#   • High connection count and unlimited upload capacity
#
# Role in the Ecosystem:
#   Acts as a "giver" node to offset the many pruned, outbound-only "taker"
#   SC Nodes being deployed. It helps both directly (assisting SC Nodes with IBD)
#   and indirectly (contributing to overall Bitcoin network health).
#
# Recommended hardware:
#   - Fast CPU
#   - At least 16 GB RAM (32 GB+ strongly preferred)
#   - Fast NVMe SSD (SECONDARY BOTTLENECK)
#   - Fastest available network connection (PRIMARY BOTTLENECK)
#
# This script is designed for Debian-based Linux distributions
# =============================================================================

LOG_FILE="/var/log/bitcoin-feeder-install.log"
log() {
    echo "$*" | tee -a "$LOG_FILE"
}

log "Starting Bitcoin Core Feeder Node setup: $(date)"

# ===================== ROOT CHECK =====================
if [[ $EUID -ne 0 ]]; then
    log "Error: Must run as root (sudo)."
    exit 1
fi

# ===================== SYSTEM UPDATE =====================
log "Updating and upgrading system packages..."
apt-get update -qq
apt-get full-upgrade -y
apt-get autoremove -y
apt-get autoclean

# ===================== PYTHON CHECK =====================
if ! command -v python >/dev/null 2>&1; then
    log "'python' command not found. Installing python-is-python3..."
    apt-get install -y python-is-python3
    if ! command -v python >/dev/null 2>&1; then
        log "ERROR: Failed to install python-is-python3. Cannot continue."
        exit 1
    fi
    log "'python' command successfully installed and linked to Python 3."
elif ! python --version 2>&1 | grep -q "Python 3"; then
    log "Warning: 'python' command exists but is not Python 3. Installing python-is-python3..."
    apt-get install -y python-is-python3
    if ! python --version 2>&1 | grep -q "Python 3"; then
        log "ERROR: Still cannot get Python 3 via 'python' command."
        exit 1
    fi
    log "'python' now correctly points to Python 3."
else
    log "'python' command points to Python 3. Good!"
fi

# ===================== INTERACTIVE VERSION SELECTION =====================
log "Fetching recent Bitcoin Core releases..."
API_RESPONSE=$(curl -s https://api.github.com/repos/bitcoin/bitcoin/releases?per_page=8)

echo ""
echo "Recent Bitcoin Core versions:"

# Extract versions, clean 'v' prefix, sort newest first, display without numbers
echo "$API_RESPONSE" | grep '"tag_name":' | cut -d '"' -f4 \
    | sed 's/^v//' \
    | sort -V -r \
    | while read -r ver; do
        echo "   ${ver}"
      done

echo ""

read -p "Enter version number (e.g. 30.2) or press Enter for latest: " SELECTED_VERSION

if [[ -z "$SELECTED_VERSION" ]]; then
    LATEST_TAG=$(curl -s https://api.github.com/repos/bitcoin/bitcoin/releases/latest | grep '"tag_name":' | cut -d '"' -f4)
    VERSION=${LATEST_TAG#v}
    log "Using latest version: $VERSION"
else
    VERSION="$SELECTED_VERSION"
    log "Using selected version: $VERSION"
fi

# ===================== ARCHITECTURE & DOWNLOAD =====================
case $(uname -m) in
    x86_64)          ARCH_SUFFIX="x86_64-linux-gnu" ;;
    aarch64|arm64)   ARCH_SUFFIX="aarch64-linux-gnu" ;;
    riscv64)         ARCH_SUFFIX="riscv64-linux-gnu" ;;
    *)
        log "ERROR: Unsupported CPU architecture: $(uname -m)"
        exit 1
        ;;
esac

TAR_NAME="bitcoin-${VERSION}-${ARCH_SUFFIX}.tar.gz"
DOWNLOAD_URL="https://bitcoincore.org/bin/bitcoin-core-${VERSION}/${TAR_NAME}"

TMP_DOWNLOAD=$(mktemp -d)
cd "${TMP_DOWNLOAD}"

log "Downloading Bitcoin Core $VERSION ($ARCH_SUFFIX)..."
if curl -L --fail --progress-bar -o "$TAR_NAME" "$DOWNLOAD_URL"; then
    TAR_FILE="${TMP_DOWNLOAD}/${TAR_NAME}"
    log "Download successful: $TAR_FILE"
else
    log "ERROR: Download failed for $DOWNLOAD_URL"
    exit 1
fi

# ===================== CREATE USER/GROUP =====================
if ! id "bitcoin" &>/dev/null; then
    log "Creating system user/group: bitcoin"
    groupadd --system bitcoin
    useradd --system --gid bitcoin --create-home --home-dir "/home/bitcoin" \
            --shell /usr/sbin/nologin --comment "Bitcoin Core Feeder daemon" bitcoin
else
    log "User bitcoin already exists."
fi

# ===================== EXTRACT & INSTALL BINARIES =====================
TMP_EXTRACT=$(mktemp -d)
trap 'rm -rf "${TMP_EXTRACT}" "${TMP_DOWNLOAD}"' EXIT
log "Extracting tarball..."
tar -xzf "${TAR_FILE}" -C "${TMP_EXTRACT}"
EXTRACTED_DIR=$(find "${TMP_EXTRACT}" -mindepth 1 -maxdepth 1 -type d | head -n 1)

log "Installing binaries..."
install -m 0755 -o root -g root "${EXTRACTED_DIR}/bin/bitcoind"     /usr/local/bin/bitcoind
install -m 0755 -o root -g root "${EXTRACTED_DIR}/bin/bitcoin-cli"  /usr/local/bin/bitcoin-cli
install -m 0755 -o root -g root "${EXTRACTED_DIR}/share/rpcauth/rpcauth.py" /usr/local/bin/rpcauth.py

# ===================== INTERACTIVE DBCACHE SELECTION =====================
TOTAL_RAM_GB=$(free --giga | awk '/^Mem:/ {print $2}' || echo "16")
RESERVED_GB=4
AVAILABLE_GB=$((TOTAL_RAM_GB - RESERVED_GB))

log "Detected system RAM: ${TOTAL_RAM_GB} GB (reserving ${RESERVED_GB} GB for OS)"

echo ""
echo "Recommended dbcache (4 GB increments - aggressive for dedicated feeder):"
for i in $(seq 4 $((AVAILABLE_GB / 4))); do
    echo "   $((i*4)) GB"
done
echo ""

read -p "Enter dbcache value in GB [default: ${AVAILABLE_GB} ]: " DBCACHE_GB_INPUT
DBCACHE_GB=${DBCACHE_GB_INPUT:-$AVAILABLE_GB}
DBCACHE=$((DBCACHE_GB * 1024))

log "Using dbcache=${DBCACHE} MB"

# ===================== CONFIG =====================
if [[ ! -f /etc/bitcoin/bitcoin.conf ]]; then
    log "Creating bitcoin.conf for feeder node..."

    mkdir -p /etc/bitcoin
    chown bitcoin:bitcoin /etc/bitcoin
    chmod 755 /etc/bitcoin

    cat > /etc/bitcoin/bitcoin.conf << EOF
# Bitcoin Feeder Node Configuration

# Full archival node
prune=0

# High-capacity listening feeder node
listen=1
discover=1
maxconnections=125
maxuploadtarget=0        # Unlimited upload - critical for feeder role

# Performance settings
blocksonly=1
dbcache=${DBCACHE}

# Disable wallet (not needed for feeder nodes)
disablewallet=1
EOF

    chown bitcoin:bitcoin /etc/bitcoin/bitcoin.conf
    chmod 644 /etc/bitcoin/bitcoin.conf
fi

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

# ===================== SYSTEMD SERVICE =====================
log "Installing systemd service..."
cat > /etc/systemd/system/bitcoind.service << EOF
[Unit]
Description=Bitcoin Core Feeder daemon (Full Archival)
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

# Lighter hardening suitable for a dedicated feeder node
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
NoNewPrivileges=yes
StateDirectory=bitcoin
StateDirectoryMode=0710

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable bitcoind.service
log "Systemd service installed (lighter version)."

# ===================== FINAL PERMISSIONS & ALIAS =====================
log "Setting final permissions..."

mkdir -p /var/lib/bitcoin
chown -R bitcoin:bitcoin /var/lib/bitcoin
chmod 710 /var/lib/bitcoin

# Ensure debug.log has correct permissions (in case it already exists)
touch /var/lib/bitcoin/debug.log
chmod 640 /var/lib/bitcoin/debug.log
chown bitcoin:bitcoin /var/lib/bitcoin/debug.log

# Add btc alias
TARGET="/etc/bash.bashrc"
BTC_ALIAS="alias btc='sudo -u bitcoin bitcoin-cli -conf=/etc/bitcoin/bitcoin.conf -datadir=/var/lib/bitcoin'"
if ! grep -Fxq "$BTC_ALIAS" "$TARGET"; then
    echo "$BTC_ALIAS" | tee -a "$TARGET" > /dev/null
    log "Added btc alias to $TARGET"
else
    log "btc alias already present"
fi

# ===================== README =====================
log "Creating system-wide documentation README..."
mkdir -p /usr/local/share/doc

cat > /usr/local/share/doc/bitcoin.txt << EOF
# Bitcoin Core Feeder Node (Full Archival)

**Basic status:**
- btc getblockchaininfo          # Show sync progress and block height
- btc getnetworkinfo             # Show peer count and network status
- btc getpeerinfo                # Detailed list of connected peers
- btc getblockcount              # Get block count
- btc getconnectioncount         # Show number of connections

**Service & Logs**
- systemctl status bitcoind      # Check if service is running
- journalctl -u bitcoind -f      # Live tail of systemd logs
- tail -n 100 /var/log/bitcoin/debug.log   # View recent debug log

**Disk & Performance:**
- df -h /var/lib/bitcoin         # Check disk usage
- free -h                        # Check RAM usage
- htop                           # CPU and memory usage

**Advanced / Troubleshooting**
- btc gettxoutsetinfo          # UTXO set size and stats
- btc getmempoolinfo           # Mempool status
- btc getconnectioncount       # Quick peer count
- btc uptime                   # How long the node has been running

## Key Paths
- Config:          /etc/bitcoin/bitcoin.conf
- Data:            /var/lib/bitcoin (full chain)
- Log:             /var/log/bitcoin/debug.log
- This Readme:     /usr/local/share/doc/bitcoin.txt
EOF
log "Created README at /usr/local/share/doc/bitcoin.txt"

# Create symlink to README in bitcoin user's home directory
ln -sfn /usr/local/share/doc/bitcoin.txt /home/bitcoin/readme.txt
chown -h bitcoin:bitcoin /home/bitcoin/readme.txt
log "Created symlink: /home/bitcoin/readme.txt"

log "Bitcoin Feeder Node installation completed successfully!"
log "Review the log: ${LOG_FILE}"

# === REBOOT SECTION ===
echo ""; echo "WARNING: System will reboot in 5 seconds..."
for i in {5..1}; do
    echo -n "."
    sleep 1
done

echo ""; echo "Rebooting now..."
reboot