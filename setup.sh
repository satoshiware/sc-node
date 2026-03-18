#!/usr/bin/env bash
# =============================================================================
# setup.sh – One-time first-boot SC Node installations, configurations, & verifications
#
# Run as root via firstboot-setup.service
#
# Purpose:
#   - Wait for full network connectivity (2 minutes max)
#   - System update + python symlink
#   - Strict ufw lockdown (inbound fully blocked)
#   - Execute SC Node install scripts: bitcoin, azcoin, wireguard, etc.
# =============================================================================
set -euo pipefail

LOG_FILE="/var/log/setup.log"

log() {
    echo "$*" | tee -a "$LOG_FILE"
}

log "=== setup.sh started ==="

# ────────────────────────────────────────────────
# Safety checks
# ────────────────────────────────────────────────
if [ "$(id -u)" -ne 0 ]; then
    log "ERROR: Must run as root."
    exit 1
fi

command -v curl >/dev/null 2>&1 || { log "ERROR: curl not found."; exit 1; }
command -v python3 >/dev/null 2>&1 || { log "ERROR: python3 not found."; exit 1; }

# ────────────────────────────────────────────────
# Wait for full network connectivity (2 minutes max)
# ────────────────────────────────────────────────
log "Waiting for network connectivity before proceeding..."

MAX_ATTEMPTS=24  # 120 * 5s = 10 minutes
for i in $(seq 1 $MAX_ATTEMPTS); do
    if ping -c 1 -W 3 8.8.8.8 >/dev/null 2>&1 || \
       curl -s --connect-timeout 5 --head http://deb.debian.org >/dev/null; then
        log "Network is up after $i attempts!"
        break
    fi
    log "Network not ready yet... attempt $i/$MAX_ATTEMPTS"
    sleep 5
done

if ! ping -c 1 8.8.8.8 >/dev/null 2>&1; then
    log "ERROR: Network never became available after ${MAX_ATTEMPTS}*5s wait."
    exit 1
else
    log "Network confirmed good — proceeding with updates and setup."
fi

# ────────────────────────────────────────────────
# System update & cleanup
# ────────────────────────────────────────────────
log "Updating system packages..."
apt update -y
apt upgrade -y
apt autoremove -y
apt autoclean -y
log "System update complete"

# ────────────────────────────────────────────────
# Python symlink (python → python3)
# ────────────────────────────────────────────────
log "Installing python-is-python3..."
apt install -y python-is-python3
log "python → python3 symlink ready"

# ────────────────────────────────────────────────
# Strict ufw lockdown (inbound fully blocked)
# ────────────────────────────────────────────────
log "Configuring strict ufw firewall..."
apt install -y ufw
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw --force enable
log "ufw enabled — inbound completely blocked"
ufw status verbose >> "$LOG_FILE" 2>&1

# ────────────────────────────────────────────────
# Bitcoin installer
# ────────────────────────────────────────────────
BITCOIN_INSTALL="/root/sc-node/bitcoin-install.sh"
log "Running Bitcoin installer: $BITCOIN_INSTALL"

if [ -f "$BITCOIN_INSTALL" ] && [ -x "$BITCOIN_INSTALL" ]; then
    if "$BITCOIN_INSTALL" >>"$LOG_FILE" 2>&1; then
        log "Bitcoin installer succeeded"
    else
        log "ERROR: Bitcoin installer failed"
        exit 1
    fi
else
    log "ERROR: Bitcoin installer missing or not executable: $BITCOIN_INSTALL"
    exit 1
fi

# ────────────────────────────────────────────────
# AZCoin installer
# ────────────────────────────────────────────────
AZCOIN_INSTALL="/root/sc-node/azcoin-install.sh"
log "Running AZCoin installer: $AZCOIN_INSTALL"

if [ -f "$AZCOIN_INSTALL" ] && [ -x "$AZCOIN_INSTALL" ]; then
    if "$AZCOIN_INSTALL" >>"$LOG_FILE" 2>&1; then
        log "AZCoin installer succeeded"
    else
        log "ERROR: AZCoin installer failed"
        exit 1
    fi
else
    log "ERROR: AZCoin installer missing or not executable: $AZCOIN_INSTALL"
    exit 1
fi

# ────────────────────────────────────────────────
# WireGuard installer
# ────────────────────────────────────────────────

# ────────────────────────────────────────────────
# Lightning installer
# ────────────────────────────────────────────────

# ────────────────────────────────────────────────
# Stratum installer
# ────────────────────────────────────────────────

# ────────────────────────────────────────────────
# Done!!
# ────────────────────────────────────────────────
log "=== setup.sh completed successfully ==="
exit 0