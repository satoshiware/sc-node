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
#
# Role in the Ecosystem:
#   Acts as a "giver" node to offset the many pruned, outbound-only "taker"
#   SC Nodes being deployed. It helps both directly (assisting SC Nodes with IBD)
#   and indirectly (contributing to overall Bitcoin network health).
#
# Recommended hardware:
#   - Fast CPU
#   - 64 GB+ RAM
#   - Fast 2 TB NVMe SSD
#   - Fastest available network connection (PRIMARY BOTTLENECK)
#
# This script is designed for Debian-based Linux distributions
# See bitcoin.txt file, prepared at bottom of this script, for more details.
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
log "Updating system packages and installing curl..."
apt update -qq
apt install -y curl
apt full-upgrade -y
apt autoremove -y
apt autoclean -y

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

# ===================== DBCACHE CALCULATION =====================
TOTAL_RAM_GB=$(free --giga | awk '/^Mem:/ {print $2}' || echo "16")

# Minimum 4 GB, target = Total RAM - 8 GB
MIN_DBCACHE_GB=4
TARGET_DBCACHE_GB=$((TOTAL_RAM_GB - 8))

# Ensure we never go below minimum
if [[ $TARGET_DBCACHE_GB -lt $MIN_DBCACHE_GB ]]; then
    DBCACHE_GB=$MIN_DBCACHE_GB
else
    DBCACHE_GB=$TARGET_DBCACHE_GB
fi

# Convert to MiB (what Bitcoin Core expects)
DBCACHE=$((DBCACHE_GB * 1024))

log "Detected system RAM: ${TOTAL_RAM_GB} GB"
log "Setting dbcache = ${DBCACHE_GB} GB (${DBCACHE} MB)"

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

# Listening feeder node
listen=1
discover=1

# Unlimited upload - critical for feeder role
maxuploadtarget=0

# Only relay blocks, not transactions
blocksonly=1

# Amount of RAM allocated to the UTXO cache (in MiB)
dbcache=${DBCACHE}

# Disable wallet (not needed for feeder nodes)
disablewallet=1

# Network settings
maxconnections=125
port=8333

# IMPORTANT: Replace with your actual public IP if behind NAT
# The btc-externalip-updater service can manage this automatically if enabled
externalip=CHANGEME
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
log "Systemd service installed and enabled."

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

# ===================== INSTALL EXTERNAL IP UPDATER =====================
log "Installing btc-externalip-updater script..."

# Create the updater script
cat > /usr/local/bin/btc-externalip-updater.sh << 'EOF'
#!/bin/bash
# btc-externalip-updater.sh - Bitcoin Feeder external IP updater

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: This script must be run as root (or with sudo)" >&2
    exit 1
fi

CONFIG_FILE="/etc/bitcoin/bitcoin.conf"
LOG_FILE="/var/log/bitcoin/externalip-updater.log"
SERVICE_NAME="bitcoind"

PLACEHOLDER="CHANGEME" # Placeholder value replaced by updater on first run

# ===================== CRON MANAGEMENT =====================
if [[ "$1" == "--enable" ]]; then
    echo "Enabling btc-externalip-updater cron job..."
    crontab -l 2>/dev/null | grep -v "btc-externalip-updater.sh" > /tmp/crontab.tmp 2>/dev/null || true
    echo "0 */6 * * * /usr/local/bin/btc-externalip-updater.sh >> /var/log/bitcoin/externalip-updater.log 2>&1" >> /tmp/crontab.tmp
    crontab /tmp/crontab.tmp
    rm -f /tmp/crontab.tmp
    echo "Cron job enabled (runs every 6 hours)"
    exit 0
fi

if [[ "$1" == "--disable" ]]; then
    echo "Disabling btc-externalip-updater cron job..."
    crontab -l 2>/dev/null | grep -v "btc-externalip-updater.sh" > /tmp/crontab.tmp 2>/dev/null || true
    crontab /tmp/crontab.tmp
    rm -f /tmp/crontab.tmp
    echo "Cron job disabled successfully"
    exit 0
fi

# ===================== NORMAL IP CHECK =====================
# List of reliable IPv4 public IP providers (in order of preference)
IP_PROVIDERS=(
    "https://api.ipify.org"
    "https://ifconfig.me"
    "https://icanhazip.com"
    "https://ipecho.net/plain"
    "https://api-ipv4.ip.sb/ip"
    "https://checkip.amazonaws.com"
    "https://ipv4.seeip.org"
    "https://ipv4.icanhazip.com"
    "https://4.ifconfig.co"
    "https://api.ip.sb/ip"
    "https://ip4.me/api"
)

get_public_ip() {
    for provider in "${IP_PROVIDERS[@]}"; do
        IP=$(curl -s -m 10 -4 "$provider" 2>/dev/null | tr -d ' \n')
        if [[ $IP =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            echo "$IP"
            return 0
        else
            log "Failed to get IP from $provider"
        fi
    done
    echo ""
}

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=== Starting external IP check ==="

CURRENT_IP=$(get_public_ip)

if [[ -z "$CURRENT_IP" ]]; then
    log "ERROR: Could not detect public IPv4 address from any provider."
    exit 1
fi

CONFIG_IP=$(grep -E '^externalip=' "$CONFIG_FILE" 2>/dev/null | cut -d'=' -f2 | tr -d ' ')

log "Current public IPv4 : $CURRENT_IP"
log "Config externalip   : ${CONFIG_IP:-NONE}"

if [[ "$CURRENT_IP" != "$CONFIG_IP" ]]; then
    log "IP changed. Updating bitcoin.conf..."

    # Remove old externalip line and add the new one (no backup)
    sed -i '/^externalip=/d' "$CONFIG_FILE"
    echo "externalip=$CURRENT_IP" >> "$CONFIG_FILE"

    log "Updated externalip=$CURRENT_IP"

    # Skip restart if we just replaced the placeholder on first install
    if [[ "$CONFIG_IP" == "$PLACEHOLDER" ]]; then
        log "Placeholder (CHANGEME) replaced - skipping bitcoind restart on initial setup."
    else
        log "Restarting $SERVICE_NAME..."
        systemctl restart "$SERVICE_NAME"

        if systemctl is-active --quiet "$SERVICE_NAME"; then
            log "SUCCESS: $SERVICE_NAME restarted with new IP."
        else
            log "ERROR: Failed to restart $SERVICE_NAME!"
        fi
    fi
else
    log "No change - public IP matches configuration."
fi

log "=== IP check completed ==="
EOF

# Set correct permissions
chmod 755 /usr/local/bin/btc-externalip-updater.sh
chown root:root /usr/local/bin/btc-externalip-updater.sh

# Finalize External IP Updater
log "Running btc-externalip-updater for the first time to detect and set externalip..."
/usr/local/bin/btc-externalip-updater.sh

log "Adding cron job using --enable parameter..."
/usr/local/bin/btc-externalip-updater.sh --enable

if [ $? -eq 0 ]; then
    log "Cron job added successfully (runs every 6 hours)"
else
    log "WARNING: Failed to add cron job via --enable"
fi

log "External IP updater installation completed."

# ===================== README =====================
log "Creating system-wide documentation README..."
mkdir -p /usr/local/share/doc

cat > /usr/local/share/doc/bitcoin.txt << 'EOF'
Bitcoin Feeder Node - Full Archival

This is a dedicated high-capacity Bitcoin Feeder Node.
It runs as a full archival node to "give back" to the Bitcoin network what regular SC Nodes "take".
Note: Upload bandwidth is usually the main bottleneck.

Quick Status Commands:
- btc getblockchaininfo         # Show sync progress and current block height
- btc getblockcount             # Quick current block count
- btc getnetworkinfo            # Peer count, version, and network status
- btc getpeerinfo               # Detailed list of connected peers
- btc getconnectioncount        # Number of connected peers

Service Management:
- systemctl status bitcoind                 # Check if the service is running
- journalctl -u bitcoind -f                 # Live tail of logs
- sudo systemctl restart bitcoind           # Restart after changing bitcoin.conf
- tail -n 100 /var/log/bitcoin/debug.log    # View recent debug log

Resource Monitoring:
- df -h /var/lib/bitcoin        # Check blockchain disk usage
- free -h                       # Check RAM usage
- htop                          # CPU and memory usage

Key Settings:
- dbcache                       # Amount of RAM allocated for the UTXO cache (higher = faster validation)
- externalip                    # Your public IP address. Change this if behind NAT or if your IP changes
- port                          # Listening port. Change if running multiple nodes on the same network (same IP address)
- maxconnections                # Maximum number of peer connections. Increase for better feeder performance. Warning, increase w/ caution!
Note: Restart bitcoind after editing bitcoin.conf

External IP Updater Script:
Automatically checks the current public IPv4 4 times daily (enabled by default)
If the IP differs from the one in bitcoin.conf, it updates the file and restarts Bitcoin Core
- Location:         /usr/local/bin/btc-externalip-updater.sh
- Manually run:     btc-externalip-updater.sh
- Enable cron:      btc-externalip-updater.sh --enable
- Disable cron:     btc-externalip-updater.sh --disable

Key Paths:
- Config file:      /etc/bitcoin/bitcoin.conf
- Blockchain data:  /var/lib/bitcoin
- Logs:             /var/log/bitcoin/debug.log
- IP Updater Log:   /var/log/bitcoin/externalip-updater.log
EOF
log "Created feeder documentation at /usr/local/share/doc/bitcoin.txt"

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