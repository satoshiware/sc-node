#!/bin/sh
# =============================================================================
# Called automatically from preseed late_command during Debian Trixie install.
# Runs in the target's chroot environment (/target).
#
# Purpose:
#   - Validates LUKS device existence right after partitioning
#   - Sets up passwordless sudo for user 'satoshi'
#   - Creates and enables a one-time first-boot systemd service
#     to run /root/sc-node/firstboot.sh
#
# Logging:
#   - Installer syslog (during install): tag "late-commands"
#     → grep late-commands /var/log/installer/syslog
#     → syslog disappears on first boot
#   - Persistent log: /var/log/late-commands.log
#     → cat /var/log/late-commands.log after first boot
#
# Debugging tips:
#   - During install: Alt+F4 → see live logs
#   - After reboot: check /var/log/late-commands.log
# =============================================================================
set -e

# Logging helper: syslog + persistent file, no levels, no per-line timestamp
LOGFILE="/var/log/late-commands.log"
log() {
    local message="$1"
    echo "$message" >> "$LOGFILE"
    logger -t late-commands "$message"
}

# Log start
log "late-commands.sh started at $(date)"

# Fail-fast: Abort if no crypto_LUKS found (post-partman validation + log)
LUKSDEV=$(blkid -t TYPE=crypto_LUKS -o device | head -n1)
if [ -z "$LUKSDEV" ]; then
    log "ERROR: No LUKS device found"
    exit 1
fi
log "Detected LUKS device: $LUKSDEV"

# Configure passwordless sudo for satoshi
echo "satoshi ALL=(ALL:ALL) NOPASSWD:ALL" > /etc/sudoers.d/satoshi
chmod 0440 /etc/sudoers.d/satoshi
log "Passwordless sudo configured for satoshi"

# Create + enable first-boot systemd service
cat > /etc/systemd/system/firstboot-setup.service << EOF
[Unit]
Description=One-time first-boot Debian setup
After=network-online.target sshd.service
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/root/sc-node/firstboot.sh
RemainAfterExit=true
StandardOutput=journal+console
StandardError=journal+console

[Install]
WantedBy=multi-user.target
EOF
log "firstboot-setup.service file created"

# Reload and enable the first-boot service
systemctl daemon-reload
systemctl enable firstboot-setup.service
log "firstboot-setup.service enabled"

# Log completion
log "late-commands.sh completed successfully at $(date)"