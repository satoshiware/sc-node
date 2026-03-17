#!/bin/sh
# =============================================================================
# Called automatically from preseed late_command during Debian Trixie install.
# Runs in the target's chroot environment (/target).
#
# Purpose:
#   - Enrolls TPM2 key for LUKS auto-unlock (PCRs 0+7) using systemd-cryptenroll
#   - Configures dracut to include tpm2-tss + crypt modules in initramfs
#   - Appends rd.luks.options=tpm2-device=auto to GRUB_CMDLINE_LINUX
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
#   - Verify TPM enrollment: systemd-cryptenroll --status <LUKSDEV>
#   - Check initramfs: lsinitramfs /boot/initrd.img-* | grep tpm2
#
# Assumptions:
#   - fTPM 2.0 enabled in UEFI + Secure Boot on
#   - Temporary passphrase matches the one set in preseed.cfg
# =============================================================================
set -e

# Logging helper: syslog + persistent file, no levels, no per-line timestamp
LOGFILE="/var/log/late-commands.sh.log"
log() {
    local message="$1"
    echo "$message" >> "$LOGFILE"
    logger -t late-commands "$message"
}

# Log start
log "late-commands.sh started at $(date)"

# Detect LUKS device (reliable in chroot post-partitioning)
LUKSDEV=$(blkid -t TYPE=crypto_LUKS -o device | head -n1)
if [ -z "$LUKSDEV" ]; then
    log "ERROR: No LUKS device found"
    exit 1
fi
log "Detected LUKS device: $LUKSDEV"

# TPM2 enrollment
TEMP_PASS="SatoshiIsMyWitness123!" # Need passphrase to register TMP2 - Update to always match in preseed.cfg
echo "$TEMP_PASS" | systemd-cryptenroll --tpm2-device=auto --tpm2-pcrs=0+7 "$LUKSDEV" || {
    log "ERROR: TPM2 enrollment failed on $LUKSDEV"
    exit 1
}
log "TPM2 enrollment succeeded on $LUKSDEV"

# dracut config – ensure TPM modules in initramfs
echo 'add_dracutmodules+=" tpm2-tss crypt "' > /etc/dracut.conf.d/tpm2.conf || {
    log "Error: Failed to write dracut.conf"
    exit 1
}
log "dracut config written"

# Regenerate all initramfs (critical for TPM early unlock)
dracut -f --regenerate-all || {
    log "Error: dracut regeneration failed"
    exit 1
}
log "dracut regeneration completed"

# GRUB: append rd.luks.options for cryptsetup to use TPM auto-unlock
sed -i '/^GRUB_CMDLINE_LINUX=/ s/"$/ rd.luks.options=tpm2-device=auto"/' /etc/default/grub || {
    log "Error: Failed to modify GRUB_CMDLINE_LINUX"
    exit 1
}
log "GRUB rd.luks.options appended"

# Update GRUB configuration (applies rd.luks.options for TPM auto-unlock)
update-grub || {
    log "Error: update-grub failed"
    exit 1
}
log "GRUB configuration updated successfully"

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