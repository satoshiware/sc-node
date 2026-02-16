#!/bin/sh
# =============================================================================
# This script is called at that the end of the preseed.cfg (SC Debian installation)
#
# Called automatically from preseed late_command during Debian install.
# Runs in the target's chroot environment.
#
# Purpose:
#   - Configures passwordless sudo for user 'satoshi'
#   - Creates and enables a one-time first-boot systemd service
#     that runs setup.sh on first boot
#
# Logging:
#   - Syslog: tag "scnode-late" (grep scnode-late /var/log/syslog)
#   - File: /root/late-commands.log (easy to check post-install)
# =============================================================================
set -e

# Log start
logger -t late-commands "late-commands.sh started at $(date)"

# Configure passwordless sudo for satoshi
echo "satoshi ALL=(ALL:ALL) NOPASSWD:ALL" > /etc/sudoers.d/satoshi
chmod 0440 /etc/sudoers.d/satoshi
logger -t late-commands "Passwordless sudo configured for satoshi"

# Create + enable first-boot systemd service
cat > /etc/systemd/system/firstboot-setup.service << EOF
[Unit]
Description=One-time first-boot Debian setup
After=network-online.target sshd.service
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/root/sc_node/firstboot.sh
RemainAfterExit=true
StandardOutput=journal+console
StandardError=journal+console

[Install]
WantedBy=multi-user.target
EOF
logger -t late-commands "firstboot-setup.service file created"

# Reload and enable the first-boot service
systemctl daemon-reload
systemctl enable firstboot-setup.service
logger -t late-commands "firstboot-setup.service enabled"

# Log completion
logger -t late-commands "late-commands.sh completed successfully at $(date)"