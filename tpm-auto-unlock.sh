#!/bin/bash
# =============================================================================
# TPM2 Auto-Unlock Configuration (Clevis + Dracut)
#
# Purpose:
#   - script to configure TPM2-based auto-unlock
#   - Installs required packages
#   - Binds TPM2 to LUKS root via Clevis (PCRs 0+7)
#   - Configures dracut for Clevis/TPM support
#   - Wipe passphrase & verify passphrase has been wiped
#
# Log: /var/log/tpm-auto-unlock.log
# =============================================================================
set -euo pipefail

LOGFILE="/var/log/tpm-auto-unlock.log"

log() {
    echo "$1" | tee -a "$LOGFILE"
}

log "[$(date '+%Y-%m-%d %H:%M:%S')] Starting TPM auto-unlock configuration"

# ─── 1. Install required packages ────────────────────────────────────────────
log "Installing Clevis, Dracut, TPM tools..."
DEBIAN_FRONTEND=noninteractive apt install -y clevis clevis-luks clevis-tpm2 clevis-dracut dracut tpm2-tools || { log "ERROR: Package install failed"; exit 1; }
log "Packages installed"

# ─── 2. Detect LUKS root device ──────────────────────────────────────────────
LUKSDEV=$(lsblk -o NAME,TYPE,MOUNTPOINT | awk '$3=="/" && $2=="crypt" {print "/dev/"$1}' | head -n1)
[ -z "$LUKSDEV" ] && { log "ERROR: No LUKS root found"; exit 1; }
log "LUKS root device: $LUKSDEV"

# ─── 3. Check if TPM2 binding already exists ────────────────────
log "Checking for existing Clevis TPM2 binding..."
if clevis luks list -d "$LUKSDEV" | grep -q tpm2; then
    log "TPM2 binding already present — skipping bind and regeneration steps."
    SKIP_BIND=1
else
    log "No TPM2 binding found — proceeding with configuration."
    SKIP_BIND=0
fi

# ─── 4. Bind TPM2 via Clevis (only if not already bound) ─────────────────────
TEMP_PASS="halfinney" # ← Must match preseed passphrase
if [ "$SKIP_BIND" -eq 0 ]; then
    log "Binding TPM2 via Clevis (PCRs 0+7)..."
    echo "$TEMP_PASS" | clevis luks bind -y -d "$LUKSDEV" tpm2 '{"pcr_bank":"sha256","pcr_ids":"0,7"}' || {
        log "ERROR: Clevis bind failed"; exit 1;
    }
    log "TPM2 bound successfully"
fi

# ─── 5. Dracut configuration (run even if bound, in case modules missing) ────
log "Configuring dracut for Clevis + TPM support..."
cat > /etc/dracut.conf.d/clevis.conf << EOF
add_dracutmodules+=" clevis crypt tpm2 "
install_items+=" /usr/bin/clevis /usr/lib/clevis /usr/lib64/clevis "
EOF

log "Regenerating all initramfs images..."
dracut -f --regenerate-all || { log "ERROR: dracut regeneration failed"; exit 1; }
log "Dracut regeneration completed"

# ─── 6. GRUB cmdline update (optional safety net) ────────────────────────────
log "Updating GRUB cmdline (for compatibility)..."
sed -i '/^GRUB_CMDLINE_LINUX=/ s/"$/ rd.luks.options=tpm2-device=auto"/' /etc/default/grub || true
update-grub || log "WARNING: update-grub failed (check manually)"

# ─── 7. Verification steps ───────────────────────────────────────────────────
log "Verifying configuration..."

if clevis luks list -d "$LUKSDEV" | grep -q tpm2; then
    log "OK: Clevis TPM2 binding present"
else
    log "ERROR: No Clevis TPM2 binding detected"; exit 1;
fi

if lsmod | grep -Eq 'tpm|tpm_tis|tpm_crb'; then
    log "OK: TPM kernel modules loaded in current session"
else
    log "NOTE: TPM modules expected to load on next boot"
fi

# ─── 8. Passphrase wipe + pre/post verification ──────────────────────────────
log "Preparing to wipe temporary passphrase slot (slot 0)..."

# Pre-wipe snapshot: Log current state for comparison
log "PRE-WIPE SNAPSHOT: Clevis luks list output"
clevis luks list -d "$LUKSDEV" | tee -a "$LOGFILE"

log "PRE-WIPE SNAPSHOT: cryptsetup luksDump (Keyslots section)"
cryptsetup luksDump "$LUKSDEV" | grep -A 10 '^Keyslots:' | tee -a "$LOGFILE" || log "luksDump failed (may not be LUKS2)"

# Actual wipe attempt
log "Wiping temporary passphrase slot (slot 0)..."
cryptsetup luksKillSlot "$LUKSDEV" 0 <<< "$TEMP_PASS" || {
    log "WARNING: Slot wipe failed (may already be gone, wrong slot, or wrong passphrase)"
}
log "Temporary passphrase slot wipe attempted"

# ─── 9. Verify passphrase slot was wiped (fail-safe check) ────────────────────
log "Verifying temporary passphrase slot (0) was wiped..."

# Method 1: Clevis list — should NOT show slot 0 anymore
if clevis luks list -d "$LUKSDEV" | grep -q '^0:'; then
    log "ERROR: Slot 0 still appears in Clevis list — wipe may have failed!"
    log "POST-WIPE Clevis output:"
    clevis luks list -d "$LUKSDEV" | tee -a "$LOGFILE"
    exit 1
else
    log "OK: No slot 0 found in Clevis list (post-wipe)"
fi

# Method 2: cryptsetup luksDump — confirm no keyslot 0 exists
if cryptsetup luksDump "$LUKSDEV" | grep -q '^  0:'; then
    log "ERROR: Keyslot 0 still exists in luksDump output — wipe failed!"
    log "POST-WIPE luksDump excerpt:"
    cryptsetup luksDump "$LUKSDEV" | grep -A 5 '^Keyslots:' | tee -a "$LOGFILE"
    exit 1
else
    log "OK: No keyslot 0 found in luksDump (post-wipe)"
fi

log "Passphrase slot wipe verified successfully — slot 0 is gone."
log "Compare PRE-WIPE snapshots above with POST-WIPE results in this log."