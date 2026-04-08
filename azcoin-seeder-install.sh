#!/usr/bin/env bash
set -euo pipefail
# =============================================================================
# AZCoin Core Seeder Node Installation Script
# =============================================================================
# Purpose: AZCoin node designed to act as a reliable bootstrap and seeder for
#          many SC Nodes on the AZCoin network.
#          Target: 500 SC Nodes / 1 AZCoin Seeder Node
#
# Key Characteristics:
#   • Extra high connection count
#   • blocks-only mode for better performance
#   • Unlimited upload capacity
#
# Role in the Ecosystem:
#   AZCoin seeder nodes are critical for new nodes to bootstrap and discover
#   peers. They are added manually in their azcoin.conf files
#
# Recommended hardware:
#   - Fast CPU
#   - At least 16 GB RAM (32 GB+ preferred)
#   - Fast NVMe SSD (SECONDARY BOTTLENECK)
#   - Fastest available network connection (PRIMARY BOTTLENECK)
#
# This script is designed for Debian-based Linux distributions
# =============================================================================

LOG_FILE="/var/log/azcoin-seeder-install.log"
log() {
    echo "$*" | tee -a "$LOG_FILE"
}

log "Starting AZCoin Core Seeder Node setup: $(date)"

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
log "Fetching recent AZCoin releases..."
API_RESPONSE=$(curl -s https://api.github.com/repos/satoshiware/azcoin/releases?per_page=8)

echo ""
echo "Recent AZCoin versions:"

# Extract tag_names, remove 'v' prefix if present, sort newest first, and display without numbers
echo "$API_RESPONSE" | grep '"tag_name":' | cut -d '"' -f4 \
    | sed 's/^v//' \
    | sort -V -r \
    | while read -r ver; do
        echo "   ${ver}"
      done

echo ""

read -p "Enter version number (e.g. 0.2.0) or press Enter for latest: " SELECTED_VERSION

if [[ -z "$SELECTED_VERSION" ]]; then
    VERSION=$(curl -s https://api.github.com/repos/satoshiware/azcoin/releases/latest | grep '"tag_name":' | cut -d '"' -f4)
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

TAR_NAME="azcoin-${VERSION}-${ARCH_SUFFIX}.tar.gz"
DOWNLOAD_URL="https://github.com/satoshiware/azcoin/releases/download/${VERSION}/${TAR_NAME}"

TMP_DOWNLOAD=$(mktemp -d)
cd "${TMP_DOWNLOAD}"

log "Downloading AZCoin $VERSION ($ARCH_SUFFIX)..."
if curl -L --fail --progress-bar -o "$TAR_NAME" "$DOWNLOAD_URL"; then
    TAR_FILE="${TMP_DOWNLOAD}/${TAR_NAME}"
    log "Download successful: $TAR_FILE"
else
    log "ERROR: Download failed for $DOWNLOAD_URL"
    exit 1
fi

# ===================== CREATE USER/GROUP =====================
if ! id "azcoin" &>/dev/null; then
    log "Creating system user/group: azcoin"
    groupadd --system azcoin
    useradd --system --gid azcoin --create-home --home-dir "/home/azcoin" \
            --shell /usr/sbin/nologin --comment "AZCoin Core Seeder daemon" azcoin
else
    log "User azcoin already exists."
fi

# ===================== EXTRACT & INSTALL BINARIES =====================
TMP_EXTRACT=$(mktemp -d)
trap 'rm -rf "${TMP_EXTRACT}" "${TMP_DOWNLOAD}"' EXIT
log "Extracting tarball..."
tar -xzf "${TAR_FILE}" -C "${TMP_EXTRACT}"
EXTRACTED_DIR=$(find "${TMP_EXTRACT}" -mindepth 1 -maxdepth 1 -type d | head -n 1)

log "Installing binaries..."
install -m 0755 -o root -g root "${EXTRACTED_DIR}/bin/azcoind"     /usr/local/bin/azcoind
install -m 0755 -o root -g root "${EXTRACTED_DIR}/bin/azcoin-cli"  /usr/local/bin/azcoin-cli
install -m 0755 -o root -g root "${EXTRACTED_DIR}/share/rpcauth/rpcauth.py" /usr/local/bin/rpcauth.py

# ===================== INTERACTIVE DBCACHE SELECTION =====================
TOTAL_RAM_GB=$(free --giga | awk '/^Mem:/ {print $2}' || echo "16")
RESERVED_GB=8
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
if [[ ! -f /etc/azcoin/azcoin.conf ]]; then
    log "Creating azcoin.conf for seeder node..."

    mkdir -p /etc/azcoin
    chown azcoin:azcoin /etc/azcoin
    chmod 755 /etc/azcoin

    cat > /etc/azcoin/azcoin.conf << EOF
# AZCoin Seeder Node Configuration

# High-capacity listening seeder node
listen=1
discover=1
maxconnections=768       # High value for powerful dedicated server
maxuploadtarget=0        # Unlimited upload - critical for seeder role

# Performance settings
blocksonly=1
dbcache=${DBCACHE}

# Disable wallet (not needed for seeder nodes)
disablewallet=1

# Connect to other known seeds
# Note: May resolve to itself 1 out of N times and simply drop the connection attempt (where N = number of backend seeders)
addnode=azcoin-seed.satoshiware.org
EOF

    chown azcoin:azcoin /etc/azcoin/azcoin.conf
    chmod 644 /etc/azcoin/azcoin.conf
fi

# ===================== SYMLINK FOR FHS-COMPLIANT LOG LOCATION =====================
LOG_SYMLINK="/var/log/azcoin/debug.log"
mkdir -p /var/log/azcoin
ln -sfn /var/lib/azcoin/debug.log "${LOG_SYMLINK}"
chown -h azcoin:azcoin "${LOG_SYMLINK}"
log "Created FHS log symlink: ${LOG_SYMLINK} → /var/lib/azcoin/debug.log"

# ===================== LOGROTATE =====================
log "Configuring logrotate..."
cat > /etc/logrotate.d/azcoin << EOF
/var/lib/azcoin/debug.log {
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

# ===================== SYSTEMD SERVICE =====================
log "Installing systemd service..."
cat > /etc/systemd/system/azcoind.service << EOF
[Unit]
Description=AZCoin Core Seeder daemon
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

ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
NoNewPrivileges=yes
StateDirectory=azcoin
StateDirectoryMode=0710

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable azcoind.service
log "Systemd service installed (lighter version)."

# ===================== FINAL PERMISSIONS & ALIAS =====================
log "Setting final permissions..."

mkdir -p /var/lib/azcoin
chown -R azcoin:azcoin /var/lib/azcoin
chmod 710 /var/lib/azcoin

# Ensure debug.log has correct permissions (in case it already exists)
touch /var/lib/azcoin/debug.log
chmod 640 /var/lib/azcoin/debug.log
chown azcoin:azcoin /var/lib/azcoin/debug.log

# Add azc alias
TARGET="/etc/bash.bashrc"
AZC_ALIAS="alias azc='sudo -u azcoin azcoin-cli -conf=/etc/azcoin/azcoin.conf -datadir=/var/lib/azcoin'"
if ! grep -Fxq "$AZC_ALIAS" "$TARGET"; then
    echo "$AZC_ALIAS" | tee -a "$TARGET" > /dev/null
    log "Added azc alias to $TARGET"
    source "$TARGET" && log "azc alias is now active"
else
    log "azc alias already present"
fi

# ===================== README =====================
log "Creating system-wide documentation README..."
mkdir -p /usr/local/share/doc

cat > /usr/local/share/doc/azcoin.txt << 'EOF'
# AZCoin Core Seeder Node

**Basic status:**
- azc getblockchaininfo        # Best overall command - shows sync progress
- azc getblockcount            # Current block height
- azc getpeerinfo              # List all connected peers
- azc getnetworkinfo           # Network info and connection count
- azc getconnectioncount       # Show number of connections

**Service & Logs**
- systemctl status azcoind     # Check if the service is running
- journalctl -u azcoind -f     # Live tail of systemd logs
- tail -n 100 /var/log/azcoin/debug.log   # View recent debug log

**Performance & Resources**
- free -h                      # RAM usage
- df -h /var/lib/azcoin        # Disk usage
- htop                         # CPU and memory usage

**Advanced / Troubleshooting**
- azc gettxoutsetinfo          # UTXO set size and stats
- azc getmempoolinfo           # Mempool status
- azc getconnectioncount       # Quick peer count
- azc uptime                   # How long the node has been running

## Key Paths
- Config:          /etc/azcoin/azcoin.conf
- Data:            /var/lib/azcoin
- Logs:            /var/log/azcoin/debug.log
- Readme:          /usr/local/share/doc/azcoin.txt
EOF
log "Created README at /usr/local/share/doc/azcoin.txt"

# Create symlink to README in azcoin user's home directory
ln -sfn /usr/local/share/doc/azcoin.txt /home/azcoin/readme.txt
chown -h azcoin:azcoin /home/azcoin/readme.txt
log "Created symlink: /home/azcoin/readme.txt"

log "AZCoin Seeder Node installation completed successfully!"
log "Review the log: ${LOG_FILE}"