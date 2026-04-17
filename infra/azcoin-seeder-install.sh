#!/usr/bin/env bash
set -euo pipefail
# =============================================================================
# AZCoin Core Seeder Node Installation Script
# =============================================================================
# Purpose: AZCoin SEEDER node to help with bootstrapping and peer discovery of SC Nodes
#
# Key Characteristics:
#   • maxconnections=384
#   • blocksonly=1
#
# Role in the Ecosystem:
#   • Primary Seeder (1 only)
#     Public entry point via DNS on port 19333
#     Discovery disabled, short-lived connections only
#
#   • Supporting Seeders (many)
#     The main bootstrapping workhorses of the network. They accept long-lived connections
#     Deployed in larger numbers for redundancy
#
# Minimum deployment: 1 Primary + 1 Supporting Seeder
#
# Recommended hardware:
#   - Fast CPU
#   - At least 16 GB RAM (32 GB+ preferred)
#   - Fast NVMe SSD
#   - Fastest available network connection (PRIMARY BOTTLENECK)
#
# This script is designed for Debian-based Linux distributions
# See azcoin.txt file, prepared at bottom of this script, for more details
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

# ===================== DETERMINE SEEDER MODE =====================
if [[ "${1:-}" == "--primary" ]]; then
    IS_PRIMARY=true
    log "=== Installing as PRIMARY SEEDER (via --primary flag) ==="
else
    IS_PRIMARY=false
    log "=== Installing as SUPPORTING SEEDER (default mode) ==="

    echo ""
    echo "This is a SUPPORTING SEEDER installation."
    echo "To install as Primary Seeder instead, rerun with:  ./azcoin-seeder-install.sh --primary"
    echo ""
    echo "Continuing in 3 seconds..."
    sleep 3
fi

# ===================== SYSTEM UPDATE =====================
log "Updating system packages and installing curl..."
apt update -qq
apt install -y curl
apt full-upgrade -y
apt autoremove -y
apt autoclean -y

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
    LATEST_TAG=$(curl -s https://api.github.com/repos/satoshiware/azcoin/releases/latest | grep '"tag_name":' | cut -d '"' -f4)
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

TAR_NAME="azcoin-${VERSION}-${ARCH_SUFFIX}.tar.gz"
DOWNLOAD_URL="https://github.com/satoshiware/azcoin/releases/download/v${VERSION}/${TAR_NAME}"

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

# Convert to MiB (what AZCoin Core expects)
DBCACHE=$((DBCACHE_GB * 1024))

log "Detected system RAM: ${TOTAL_RAM_GB} GB"
log "Setting dbcache = ${DBCACHE_GB} GB (${DBCACHE} MB)"

# ===================== CONFIG =====================
if $IS_PRIMARY; then
    HEADER="PRIMARY SEEDER"
else
    HEADER="SUPPORTING SEEDER"
fi

if [[ ! -f /etc/azcoin/azcoin.conf ]]; then
    log "Creating azcoin.conf for seeder node..."

    mkdir -p /etc/azcoin
    chown azcoin:azcoin /etc/azcoin
    chmod 755 /etc/azcoin

    if $IS_PRIMARY; then
        DISCOVER_SETTING="0"
    else
        DISCOVER_SETTING="1"
    fi

    cat > /etc/azcoin/azcoin.conf << EOF
# AZCoin ${HEADER} Node Configuration

# Listening seeder node
listen=1

# Gossip Protocol enabled for Supporting Seeders only. Disable the Gossip Protocol for the Primary Seeder
discover=${DISCOVER_SETTING}

# Unlimited upload - critical for seeder role
maxuploadtarget=0

# Only relay blocks, not transactions
blocksonly=1

# Amount of RAM allocated to the UTXO cache (in MiB)
dbcache=${DBCACHE}

# Disable wallet (not needed for seeder nodes)
disablewallet=1

# Network settings
maxconnections=384

# Primary Seeder: Must be the default port of 19333
# Supporting Seeder: Can be most any number. If behind NAT, ensure internal and external port forward are the same
port=19333

# External IP configuration for Supporting Seeders only: If behind NAT, uncomment and add external static IP
# externalip=

# Fan-out to other seeders (maximum 8)
# addnode=
# addnode=
# addnode=
# addnode=
# addnode=
# addnode=
# addnode=
# addnode=
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
else
    log "azc alias already present"
fi

# ===================== INBOUND PROTECTION (PRIMARY SEEDER ONLY) =====================
if $IS_PRIMARY; then
    log "Installing Primary Seeder inbound protection (cron-based)..."

    cat > /usr/local/bin/azcoin-primary-protect.sh << 'PROTECT'
#!/usr/bin/env bash
# Primary Seeder Protection: Kick after 3 minutes, ban for 7 days

MAX_AGE=180      # 3 minutes
BAN_TIME=604800  # 7 days

peers=$(/usr/local/bin/azcoin-cli -conf=/etc/azcoin/azcoin.conf -datadir=/var/lib/azcoin getpeerinfo 2>/dev/null | \
        jq -r '.[] | select(.inbound==true) | "\(.addr) \(.conntime)"' 2>/dev/null || true)

while read -r addr conntime; do
    [[ -z "$addr" ]] && continue
    age=$(( $(date +%s) - conntime ))
    if [[ $age -gt $MAX_AGE ]]; then
        echo "[$(date)] Kicking old inbound: $addr (age ${age}s) → banning for 7 days"
        /usr/local/bin/azcoin-cli -conf=/etc/azcoin/azcoin.conf -datadir=/var/lib/azcoin addnode "$addr" "remove" >/dev/null 2>&1 || true
        /usr/local/bin/azcoin-cli -conf=/etc/azcoin/azcoin.conf -datadir=/var/lib/azcoin setban "$addr" "add" $BAN_TIME >/dev/null 2>&1 || true
    fi
done <<< "$peers"
PROTECT

    chmod +x /usr/local/bin/azcoin-primary-protect.sh

    # Cron job every 2 minutes
    crontab -l 2>/dev/null | grep -v "azcoin-primary-protect.sh" > /tmp/crontab.tmp 2>/dev/null || true
    echo "*/2 * * * * /usr/local/bin/azcoin-primary-protect.sh >> /var/log/azcoin/protect.log 2>&1" >> /tmp/crontab.tmp
    crontab /tmp/crontab.tmp
    rm -f /tmp/crontab.tmp

    log "Primary protection installed via cron (every 2 minutes)"
fi

# ===================== README =====================
log "Creating system-wide documentation README..."
mkdir -p /usr/local/share/doc

cat > /usr/local/share/doc/azcoin-seeder.txt << EOF
# AZCoin ${HEADER} Node

This is a dedicated high-capacity AZCoin ${HEADER} Node.
It runs as a full archival node to help with bootstrapping and peer discovery of SC Nodes.
Note: Upload bandwidth is usually the main bottleneck.

Basic status:
- azc getblockchaininfo        # Best overall command - shows sync progress
- azc getblockcount            # Current block height
- azc getpeerinfo              # List all connected peers
- azc getnetworkinfo           # Network info and connection count
- azc getconnectioncount       # Show number of connections

Service Management:
- systemctl status azcoind                  # Check if the service is running
- journalctl -u azcoind -f                  # Live tail of systemd logs
- sudo systemctl restart azcoind            # Restart after changing bitcoin.conf
- tail -n 100 /var/log/azcoin/debug.log     # View recent debug log

Resource Monitoring:
- free -h                      # RAM usage
- df -h /var/lib/azcoin        # Disk usage

Key Settings:
- dbcache                       # Amount of RAM allocated for the UTXO cache (higher = faster validation)
- externalip                    # If your Supporting Seeder is behind a NAT, set this to your external static ip (Supporting Seeder nodes only)
- port                          # Listening port: On Supporting Seeder nodes only, change if running multiple nodes on the same network (same IP address) and ensure internal and external port forwards are the same
- maxconnections                # Maximum number of peer connections. If you must, decrease to reduce bandwidth usage.
- addnode (x8)                  # Add other seeders (maximum 8)
Note: Restart azcoind after editing azcoin.conf

Key Paths:
- Config file:      /etc/azcoin/azcoin.conf
- Blockchain data:  /var/lib/azcoin
- Logs:             /var/log/azcoin/debug.log
EOF

# Add Primary Seeder Only section conditionally
if $IS_PRIMARY; then
    cat >> /usr/local/share/doc/azcoin-seeder.txt << 'EOF2'

Primary Seeder Only - Inbound Protection:
- Script location: /usr/local/bin/azcoin-primary-protect.sh
- Default settings:
    MAX_AGE=180     # 3 minutes  (kicks inbound connections older than this)
    BAN_TIME=604800 # 7 days     (bans offending IPs for this duration)
- Runs via cron every 2 minutes
- Log file: /var/log/azcoin/protect.log
- To view or change the cron job: sudo crontab -e
EOF2
fi
log "Created README at /usr/local/share/doc/azcoin.txt"

# Create symlink to README in azcoin user's home directory
ln -sfn /usr/local/share/doc/azcoin.txt /home/azcoin/readme.txt
chown -h azcoin:azcoin /home/azcoin/readme.txt
log "Created symlink: /home/azcoin/readme.txt"

log "AZCoin Seeder Node installation completed successfully!"
log "Review the log: ${LOG_FILE}"

# === REBOOT SECTION ===
echo ""; echo "WARNING: System will reboot in 5 seconds..."
for i in {5..1}; do
    echo -n "."
    sleep 1
done

echo ""; echo "Rebooting now..."
reboot