#!/usr/bin/env bash
# =============================================================================
# firstboot.sh – Sovereign Circle Node One-Time First-Boot Setup
#
# Performs initial system hardening, updates/upgrades the system, and configures SSH access
#
# Execution:
#   - Triggered automatically via systemd oneshot service (firstboot.service)
#     created/enabled during preseed.cfg install (in late_commands.sh)
#   - Runs as root
#   - Self-disables and removes the service file, this script, and late-commands.sh after successful completion
#   - Logs everything to /var/log/firstboot.log
# =============================================================================
set -euo pipefail

# ────────────────────────────────────────────────
# Configuration
# ────────────────────────────────────────────────
LOG_FILE="/var/log/firstboot.log"
MAX_NETWORK_WAIT=120 # 2 minutes
REBOOT_DELAY_MINUTES=1 # Grace period before reboot

# ────────────────────────────────────────────────
# Logging
# ────────────────────────────────────────────────
log() {
    echo "$*" | tee -a "$LOG_FILE"
}

log "firstboot.sh started at $(date)"

# ────────────────────────────────────────────────
# Safety checks
# ────────────────────────────────────────────────
if [ "$(id -u)" -ne 0 ]; then
    log "ERROR: This script must run as root."
    exit 1
fi

for cmd in curl apt ping systemctl; do
    command -v "$cmd" >/dev/null 2>&1 || {
        log "ERROR: Required command not found: $cmd"
        exit 1
    }
done

# Check if the ssh.service unit file exists
log "Checking for ssh.service unit file..."
if [ ! -f /lib/systemd/system/ssh.service ]; then
    log "ERROR: ssh.service unit file missing — ssh is NOT installed"
    exit 1
fi

# Ensure the ssh service is enabled
log "Ensuring ssh.service is enabled"
if ! systemctl enable ssh --quiet 2>/dev/null; then
    log "ERROR: Failed to enable ssh.service"
    exit 1
fi
log "ssh.service successfully enabled (or was already enabled)"

# ────────────────────────────────────────────────
# Wait for network connectivity
# ────────────────────────────────────────────────
log "Waiting for network connectivity (max ${MAX_NETWORK_WAIT}s)..."

elapsed=0
interval=5

while [ $elapsed -lt $MAX_NETWORK_WAIT ]; do
    if ping -c 1 -W 3 8.8.8.8 >/dev/null 2>&1 || \
       curl -s --connect-timeout 5 --head http://deb.debian.org >/dev/null 2>&1; then
        log "Network is up after ${elapsed}s."
        break
    fi

    log "Network not ready yet... (${elapsed}s elapsed)"
    sleep "$interval"
    ((elapsed += interval))
done

if [ $elapsed -ge $MAX_NETWORK_WAIT ]; then
    log "ERROR: Network not available after ${MAX_NETWORK_WAIT} seconds. Aborting."
    exit 1
fi

# ────────────────────────────────────────────────
# System update & cleanup
# ────────────────────────────────────────────────
log "Starting full system update..."

apt update -y     && log "apt update completed"     || { log "ERROR: apt update failed"; exit 1; }
apt upgrade -y    && log "apt upgrade completed"    || { log "ERROR: apt upgrade failed"; exit 1; }
apt autoremove -y && log "apt autoremove completed" || { log "ERROR: apt autoremove failed"; exit 1; }
apt autoclean -y  && log "apt autoclean completed"  || { log "ERROR: apt autoclean failed"; exit 1; }

log "System update sequence finished."

# ────────────────────────────────────────────────
# Python compatibility symlink
# ────────────────────────────────────────────────
log "Setting up python → python3 compatibility..."
apt install -y python-is-python3
log "python-is-python3 installed."

# ─────────────────────────────────────────────────────────────────────────────
# Ensure SSH server is running and configured for password login
# ─────────────────────────────────────────────────────────────────────────────
log "Configuring SSH for password authentication"

# Enable PasswordAuthentication
sed -i 's/^#PasswordAuthentication.*$/PasswordAuthentication yes/' /etc/ssh/sshd_config || true
sed -i 's/^PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config || true

# Quick status check
if systemctl is-active --quiet ssh; then
    log "SSH service is active and listening"
    ss -tuln | grep ':22' >> "$LOGFILE" 2>&1 || true
else
    log "ERROR: SSH service is not active after restart"
fi

# ────────────────────────────────────────────────
# Strict UFW lockdown + allow SSH for post-install
# ────────────────────────────────────────────────
log "Configuring strict UFW firewall with SSH exception..."
apt install -y ufw
ufw --force reset
ufw default deny incoming
ufw default allow outgoing

# Allow SSH (port 22) so you can connect remotely after first boot
ufw allow OpenSSH comment 'Allow SSH temporarily for post-install setup' || { log "ERROR: Failed to allow SSH (port 22) in UFW"; exit 1; }

ufw --force enable
ufw reload

log "UFW enabled with SSH (port 22) allowed."
ufw status verbose >> "$LOG_FILE" 2>&1

# ────────────────────────────────────────────────
# Self-cleanup: Disable and remove the triggering service
# ────────────────────────────────────────────────
log "Disabling and removing firstboot.service..."

systemctl disable firstboot.service 2>/dev/null || true
rm -f /etc/systemd/system/firstboot.service 2>/dev/null || true
systemctl daemon-reload 2>/dev/null || true

log "firstboot.service removed successfully."

# ────────────────────────────────────────────────
# Final cleanup: Remove this script, late-commands.sh, and /root/setup
# ────────────────────────────────────────────────
log "Performing final self-cleanup..."
rm -f /root/setup/firstboot.sh \
      /root/setup/late-commands.sh \
      2>/dev/null || true
rm -rf /root/setup 2>/dev/null || true
log "Self-cleanup complete: /root/setup and scripts removed."

# ────────────────────────────────────────────────
# Finalize
# ────────────────────────────────────────────────
log "firstboot.sh completed successfully at $(date)"
log "Rebooting system in ${REBOOT_DELAY_MINUTES} minutes"

shutdown -r "+${REBOOT_DELAY_MINUTES}" "firstboot.sh complete — rebooting in ${REBOOT_DELAY_MINUTES} minutes" || {
    log "WARNING: shutdown command failed — system will NOT auto-reboot"
}

exit 0