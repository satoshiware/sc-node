#!/usr/bin/env bash
# =============================================================================
# setup.sh – One-time first-boot configuration & verification
#
# Runs as root via firstboot-setup.service
# Purpose:
#   - Verify LUKS + TPM2 auto-unlock actually worked
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
# Verify encrypted SSD + TPM2 auto-unlock
# ────────────────────────────────────────────────
log "Verifying LUKS + TPM2 auto-unlock"
LUKS_DEV=$(lsblk -o NAME,TYPE,MOUNTPOINT | awk '$3=="/" && $2=="crypt" {print "/dev/"$1}' | head -n1)
if [ -z "$LUKS_DEV" ]; then
    log "ERROR: Root filesystem is NOT encrypted (no crypto device for /)"
    exit 1
fi
log "Root is encrypted: $LUKS_DEV"

# TPM2 keyslot present?
if systemd-cryptenroll --status "$LUKS_DEV" 2>/dev/null | grep -q "tpm2"; then
    log "OK: TPM2 keyslot found"
else
    log "ERROR: No TPM2 keyslot found in LUKS header"
    exit 1
fi

# This boot auto-unlocked?
if journalctl -b -u "systemd-cryptsetup@$LUKS_DEV.service" -n 50 | grep -qi "unlocked"; then
    log "SUCCESS: Auto-unlocked on this boot"
else
    log "ERROR: No auto-unlock evidence in cryptsetup journal"
    exit 1
fi

# TPM modules loaded?
if lsmod | grep -q tpm; then
    log "OK: TPM kernel modules loaded"
else
    log "Error: No TPM kernel modules loaded (tpm_tis or tpm_crb expected)"
    exit 1
fi

log "LUKS/TPM verification passed"

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
# Done!!
# ────────────────────────────────────────────────
log "=== setup.sh completed successfully ==="
exit 0