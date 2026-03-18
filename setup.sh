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
# System update & cleanup
# ────────────────────────────────────────────────
log "Updating system packages..."
apt update -y
apt upgrade -y
apt autoremove -y
apt autoclean -y
log "System update complete"












# =============================================================================
# Called automatically from preseed late_command during Debian Trixie install.
# Runs in the target's chroot environment (/target).
#
# Purpose (post-TPM-split):
# - Validates LUKS device existence right after partitioning (early fail-fast)
# - Configures passwordless sudo for user 'satoshi'
# - Creates and enables a one-time first-boot systemd service
#   to run /root/sc-node/firstboot.sh (which handles TPM2 enrollment,
#   dracut regeneration with tpm2-tss, GRUB updates for rd.luks.options,
#   and any other post-boot finalization)
#
# IMPORTANT: TPM2 enrollment is NOW deferred to firstboot.sh because:
#   - TPM device (/dev/tpm0 or /dev/tpmrm0) is often not visible/usable in installer chroot.
#   - Enrollment in chroot can fail silently (no TPM modules loaded, PCR state issues, etc.).
#   - First boot allows reliable access after full kernel/modules init.
#   → This means FIRST BOOT requires manual entry of the temp passphrase (short/weak OK via preseed).
#     After firstboot.sh runs → next reboot should auto-unlock via TPM.
#
# Logging:
# - Installer syslog (during install): tag "late-commands"
#   → grep late-commands /var/log/installer/syslog (Alt+F4 during install)
#   → Disappears after first boot
# - Persistent log: /var/log/late-commands.log (survives to installed system)
#   → cat /var/log/late-commands.log after first boot
#
# Debugging tips:
# - During install: Switch to Alt+F4 console → watch live logs
# - After failed install: Check installer logs on USB/media
# - Post-install issues: /var/log/late-commands.log + journalctl -u firstboot-setup.service
# - Verify TPM post-firstboot: systemd-cryptenroll --status $LUKSDEV
# - Check initramfs for TPM support: lsinitrd /boot/initrd.img-* | grep -i tpm2
# - If TPM auto-unlock fails later: Boot with rd.break, check dmesg/journalctl, rdsosreport.txt
#
# Assumptions / Requirements:
# - fTPM 2.0 enabled in UEFI + Secure Boot enabled (for measured boot integrity)
# - Temporary passphrase set short/weak in preseed (with partman-crypto/weak_passphrase true)
# - /root/sc-node/firstboot.sh exists and is executable (copied via preseed late_command or pkg)
# - firstboot.sh will: re-detect LUKSDEV, enroll TPM with temp pass, regenerate dracut/GRUB
# =============================================================================

# Install requireed packages
apt install -y libtss2-esys-3.0.2-0 libtss2-fapi1 libtss2-tctildr0 tpm-udev dracut

sleep 10
exit 0

# Detect LUKS device (reliable in chroot post-partitioning)
LUKSDEV=$(blkid -t TYPE=crypto_LUKS -o device | head -n1)
if [ -z "$LUKSDEV" ]; then
    log "ERROR: No LUKS device found"
    exit 1
fi
log "Detected LUKS device: $LUKSDEV"

# TPM2 enrollment
TEMP_PASS="finney" # Need passphrase to register TMP2 - Update to always match in preseed.cfg
echo "$TEMP_PASS" | systemd-cryptenroll --tpm2-device=auto --tpm2-pcrs=0+7 "$LUKSDEV" || {
    log "ERROR: TPM2 enrollment failed on $LUKSDEV"
    exit 1
}
log "TPM2 enrollment succeeded on $LUKSDEV"

# Wipe the password keyslot
systemd-cryptenroll --wipe-slot=password "$LUKSDEV" || {
    log "Error: Passphrase wipe failed"
    exit 1
}
log "Temporary Passphrase Wiped"

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










