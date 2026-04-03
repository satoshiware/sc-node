#!/usr/bin/env bash
set -euo pipefail
# =====================================================================================
# SC Node Stratum Setup (Bitcoin + AZCoin): Proxy, V1 to V2 Translator, Logger, Aggregator
#
# Details:
#   - Stratum V1 to Stratum V2 translator
#   - Aggregates all incoming (V1) to one outgoing (V2)
#   - Runs two independent instances. One for Bitcoin and one for AZCoin
#       → Bitcoin shows in processes (ps) as "stratum bitcoin"
#       → AZCoin shows in processes (ps) as "stratum azcoin"
#   - Provides per miner (worker) logging
#   - Includes logrotate with copytruncate (no data loss during rotation)
#       → Log rotation (daily or 100MB) with 14-day retention
#   - HTTP REST API
#       → monitoring_address = "127.0.0.1:9092"
#
# Ports:
#   - Bitcoin:  3333
#   - AZCoin:   3334
#
# Configuration:
#   - The user_identity includes the machine's serial number
#   - The base domain for the mining URLs is sourced from /etc/sc-server/domain
#   - The authority pubkey is sourced from the following files:
#       → BITCOIN: /etc/sc-server/btc-stratum-authority-pubkey
#       → AZCOIN: /etc/sc-server/azc-stratum-authority-pubkey
# =====================================================================================

INSTALL_LOG_FILE="/var/log/stratum-install.log"
SV2_BIN_PARENT="/root/sc-node"
BIN_DIR="/usr/local/bin"
CONFIG_DIR="/etc/stratum"
LOG_DIR="/var/log/stratum"

# Documentation
README_DIR="/usr/local/share/doc"
README_FILE="${README_DIR}/stratum.txt"

log() {
    echo "$*" | tee -a "$INSTALL_LOG_FILE"
}

log "Starting stratum setup (Bitcoin & AZCoin) [$(date)]"

# ===================== CHECKS =====================
if [[ $EUID -ne 0 ]]; then
    log "Error: Must run as root (sudo)."
    exit 1
fi

# ===================== CREATE SYSTEM USER =====================
if ! id "stratum" &>/dev/null; then
    log "Creating system user: stratum"
    groupadd --system stratum
    useradd --system --gid stratum --create-home --home-dir "/home/stratum" \
            --shell /usr/sbin/nologin --comment "Stratum Service" stratum
fi

# ===================== DOWNLOAD (if missing) =====================
# Find any existing miner-apps tarball
MINER_TAR=$(find "${SV2_BIN_PARENT}" -maxdepth 1 -name "miner-apps-*.tar.gz" -print -quit 2>/dev/null || true)

if [[ ! -f "${MINER_TAR}" ]]; then
    log "Downloading latest miner-apps tarball..."

    # Get latest tag
    LATEST_TAG=$(curl -s https://api.github.com/repos/stratum-mining/sv2-apps/releases/latest | grep '"tag_name":' | cut -d '"' -f4)
    if [[ -z "${LATEST_TAG}" ]]; then
        log "ERROR: Could not determine latest release."
        exit 1
    fi
    log "Latest release: ${LATEST_TAG}"

    # Determine architecture
    case $(uname -m) in
        x86_64)  ARCH_TARGET="x86_64" ;;
        aarch64|arm64) ARCH_TARGET="aarch64" ;;
        riscv64) ARCH_TARGET="riscv64" ;;
        *)
            log "ERROR: Unsupported architecture: $(uname -m)"
            exit 1
            ;;
    esac

    # Discover stratum miner-apps tarball filename
    TAR_FILENAME=$(curl -s https://api.github.com/repos/stratum-mining/sv2-apps/releases/latest \
        | grep -o 'miner-apps[^"]*'"${ARCH_TARGET}"'[^"]*linux[^"]*\.tar\.gz' \
        | head -n1)
    if [[ -z "$TAR_FILENAME" ]]; then
        log "ERROR: Could not find miner-apps tarball matching architecture ${ARCH_TARGET}."
        exit 1
    fi
    log "Found stratum miner-apps tarball filename: ${TAR_FILENAME}"

    # Download
    mkdir -p "${SV2_BIN_PARENT}"
    curl -L --fail --progress-bar -o "${SV2_BIN_PARENT}/${TAR_FILENAME}" "https://github.com/stratum-mining/sv2-apps/releases/download/${LATEST_TAG}/${TAR_FILENAME}" || {
        log "ERROR: Failed to download miner-apps"
        exit 1
    }

    MINER_TAR="${SV2_BIN_PARENT}/${TAR_FILENAME}"
else
    log "Using existing miner-apps tarball: ${MINER_TAR}"
fi
log "SHA256 of miner-apps tarball: $(sha256sum "${MINER_TAR}" | awk '{print $1}')"

# ===================== DIRECTORIES & FILES =====================
mkdir -p "$CONFIG_DIR" "$LOG_DIR"
chown -R stratum:stratum "$CONFIG_DIR" "$LOG_DIR"

touch "$LOG_DIR/stratum-bitcoin.log"
touch "$LOG_DIR/stratum-azcoin.log"
chown stratum:stratum "$LOG_DIR"/*.log
chmod 644 "$LOG_DIR"/*.log
log "Log files pre-created with 644 permissions"

# ===================== EXTRACT BINARY =====================
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

log "Extracting translator_sv2 binary..."
tar -xzf "${MINER_TAR}" -C "$TMP_DIR"
find "$TMP_DIR" -type f -name "translator_sv2" -exec cp -v {} "$BIN_DIR/translator_sv2" \;
chmod +x "$BIN_DIR/translator_sv2"

log "translator_sv2 binary installed to $BIN_DIR/translator_sv2"

# ===================== CREATE CONFIGS =====================
log "Creating configuration files..."

cat > "$CONFIG_DIR/stratum-bitcoin.toml" << EOF
# =============================================================================
# Stratum Bitcoin Configuration File
# =============================================================================
# ── Downstream Settings (V1 miners connect here) ──
# IP address to listen on
downstream_address = "0.0.0.0"

# Port your miners should point to
downstream_port = 3333

# Protocol version support
max_supported_version = 2
min_supported_version = 2

# Extranonce settings: 4 bytes is a good balance (2-16 allowed)
downstream_extranonce2_size = 4

# ── Upstream Identity ──
# This is the base user_identity sent to the upstream SV2 pool
# The translator will automatically append .0, .1, .2 etc. in aggregated mode
user_identity = "btc-$(dmidecode -s system-serial-number)"

# ── Channel Mode ──
# Enabled for all miners to share ONE upstream connection
aggregate_channels = true

# ── Log Output ──
log_file = "$LOG_DIR/stratum-bitcoin.log"

# ── Protocol Extensions ──
supported_extensions = [
    0x0002,   # Worker-Specific Hashrate Tracking
]

# ── Setup HTTP Monitoring Server ──
monitoring_address = "127.0.0.1:9092"
monitoring_cache_refresh_secs = 15

# ── Difficulty / Vardiff Configuration ──
[downstream_difficulty_config]
# Minimum expected hashrate (100 GH/s)
min_individual_miner_hashrate = 100_000_000_000.0

# Target share rate per miner (1 every 10 seconds is good)
shares_per_minute = 6.0

# Enable for the translator to manage per-miner difficulty
enable_vardiff = true

# ── Job Keepalive ──
# How often to send keepalive messages to the upstream pool (60 seconds is the recommended value)
job_keepalive_interval_secs = 60

# ── Upstream SV2 Pool Connection ──
[[upstreams]]
address = "btc.stratum.$(head -n 1 /etc/sc-server/domain)"
port = 3333

# The Noise Protocol Authentication is enabled (or disabled) entirely by the presence (or absence) of the authority_pubkey field
authority_pubkey = "$(head -n 1 /etc/sc-server/btc-stratum-authority-pubkey)"
EOF

cat > "$CONFIG_DIR/stratum-azcoin.toml" << EOF
# =============================================================================
# Stratum AZCoin Configuration File
# =============================================================================
# ── Downstream Settings (V1 miners connect here) ──
# IP address to listen on
downstream_address = "0.0.0.0"

# Port your miners should point to
downstream_port = 3334

# Protocol version support
max_supported_version = 2
min_supported_version = 2

# Extranonce settings: 4 bytes is a good balance (2-16 allowed)
downstream_extranonce2_size = 4

# ── Upstream Identity ──
# This is the base user_identity sent to the upstream SV2 pool
# The translator will automatically append .0, .1, .2 etc. in aggregated mode
user_identity = "azc-$(dmidecode -s system-serial-number)"

# ── Channel Mode ──
# Enabled for all miners to share ONE upstream connection
aggregate_channels = true

# ── Log Output ──
log_file = "$LOG_DIR/stratum-azcoin.log"

# ── Protocol Extensions ──
supported_extensions = [
    0x0002,   # Worker-Specific Hashrate Tracking
]

# ── Setup HTTP Monitoring Server ──
monitoring_address = "127.0.0.1:9092"
monitoring_cache_refresh_secs = 15

# ── Difficulty / Vardiff Configuration ──
[downstream_difficulty_config]
# Minimum expected hashrate (100 GH/s)
min_individual_miner_hashrate = 100_000_000_000.0

# Target share rate per miner (1 every 10 seconds is good)
shares_per_minute = 6.0

# Enable for the translator to manage per-miner difficulty
enable_vardiff = true

# ── Job Keepalive ──
# How often to send keepalive messages to the upstream pool (60 seconds is the recommended value)
job_keepalive_interval_secs = 60

# ── Upstream SV2 Pool Connection ──
[[upstreams]]
address = "azc.stratum.$(head -n 1 /etc/sc-server/domain)"
port = 3334

# The Noise Protocol Authentication is enabled (or disabled) entirely by the presence (or absence) of the authority_pubkey field
authority_pubkey = "$(head -n 1 /etc/sc-server/azc-stratum-authority-pubkey)"
EOF

log "Configs created in $CONFIG_DIR/"

# ===================== SYSTEMD SERVICES =====================
log "Creating systemd services with clear process names..."

cat > /etc/systemd/system/stratum-bitcoin.service << EOF
[Unit]
Description=Stratum - Bitcoin
After=network.target

[Service]
Type=simple
User=stratum
Group=stratum
ExecStart=/usr/bin/env RUST_LOG=debug $BIN_DIR/translator_sv2 -c $CONFIG_DIR/stratum-bitcoin.toml
# RUST_LOG Options: error, warn, info, debug, trace (Use "debug" in production to extract per miner shares)
Restart=always
RestartSec=5
StandardError=append:$LOG_DIR/stratum-bitcoin.log

# Hardening
ProtectSystem=full
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
NoNewPrivileges=yes
RestrictRealtime=yes
EOF

cat > /etc/systemd/system/stratum-azcoin.service << EOF
[Unit]
Description=Stratum - AZCoin
After=network.target

[Service]
Type=simple
User=stratum
Group=stratum
ExecStart=/usr/bin/env RUST_LOG=debug $BIN_DIR/translator_sv2 -c $CONFIG_DIR/stratum-azcoin.toml
# RUST_LOG Options: error, warn, info, debug, trace (Use "debug" in production to extract per miner shares)
Restart=always
RestartSec=5
StandardError=append:$LOG_DIR/stratum-azcoin.log

# Hardening
ProtectSystem=full
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
NoNewPrivileges=yes
RestrictRealtime=yes
EOF

systemctl daemon-reload
systemctl enable --now stratum-bitcoin stratum-azcoin

log "Services enabled and started."

# ======================================= LOGROTATE ============================================================================
# Logrotate runs with copytruncate, meaning the active log files are never renamed — it is copied and then truncated in place.
# This ensures continuous writers (the translators) and readers experience no data loss or broken file handles during rotation.
# Old logs are automatically compressed (.gz files) and kept for 14 days. Logs are rotated daily at midnight (00:00 server time)
# or when a log file reaches 100MB — whichever happens first.
# ==============================================================================================================================
Up to 14 old rotated logs are kept (compressed as .gz files).

log "Setting up logrotate..."
cat > /etc/logrotate.d/stratum << EOF
$LOG_DIR/stratum-*.log {
    daily
    rotate 14
    size 100M
    copytruncate
    missingok
    notifempty
    compress
    delaycompress
    create 644 stratum stratum
    sharedscripts
    postrotate
        systemctl kill -s USR1 stratum-bitcoin.service --kill-who=main 2>/dev/null || true
        systemctl kill -s USR1 stratum-azcoin.service --kill-who=main 2>/dev/null || true
    endscript
}
EOF

chmod 644 /etc/logrotate.d/stratum

# ===================== README =====================
log "Creating system-wide documentation for Stratum..."
mkdir -p "${README_DIR}"

cat > "${README_FILE}" << EOF
Stratum (Bitcoin + AZCoin) Proxy, V1 to V2 Translator, Logger, Aggregator

Details:
  - Stratum V1 to Stratum V2 translator
  - Aggregates all incoming (V1) to one outgoing (V2)
  - Runs two independent instances. One for Bitcoin and one for AZCoin
  - Provides per miner (worker) logging

Binary: $BIN_DIR/translator_sv2
  - For Bitcoin, it shows in processes (ps aux) as "stratum bitcoin"
  - For AZCoin, it shows in processes (ps aux) as "stratum azcoin"

Ports:
  - Bitcoin:  3333
  - AZCoin:   3334

Configuration Files:
  - $CONFIG_DIR/stratum-bitcoin.toml
  - $CONFIG_DIR/stratum-azcoin.toml

Key Configuration Settings:
  - SC Node's "user_identity"
  - Upstream pool's "address" & "port"
  - Upstream pool's "authority_pubkey"

Log Files:
  - Bitcoin: $LOG_DIR/stratum-bitcoin.log
  - AZCoin: $LOG_DIR/stratum-azcoin.log
  - Logrotate: /etc/logrotate.d/stratum

Logrotate Settings:
  - Rotates daily at midnight or when a file (AZCoin or Bitcoin) reaches 100MB
  - Uses copytruncate to ensure no data loss and no broken file handles during log rotation
  - Keeps 14 days of compressed logs (.gz files)

Management:
  - systemctl status stratum-bitcoin
  - systemctl status stratum-azcoin
  - journalctl -u stratum-bitcoin -f
  - journalctl -u stratum-azcoin -f

HTTP REST API Endpoints (monitoring_address = "127.0.0.1:9092")
  - Health
    → Health check                          /api/v1/health

  - Global
    → Global statistics                     /api/v1/global

  - Server
    → Server (upstream) monitoring          /api/v1/server
    → Server channels                       /api/v1/server/channels                 (paginated)

  - Clients
    → See all SV2 clients (downstream)      /api/v1/clients                         (metadata)
    → Single SV2 client by ID               /api/v1/clients/{client_id}             (metadata)
    → Channels for a specific SV2 client    /api/v1/clients/{client_id}/channels    (paginated)

  - SV1
    → Get SV1 clients                       /api/v1/sv1/clients
    → Get a single SV1 client by ID         /api/v1/sv1/clients/{client_id}
EOF

log "Setup complete!"
log "stratum-install setup log file: ${LOG_FILE}"
log "Readme file: ${README_FILE}"