#!/usr/bin/env bash
# =============================================================================
# Builds a bootable Debian full-install ISO (based on official DVD-1)
# Customized for SC Node automation: preseed.cfg, late-commands.sh, & firstbooth.sh
#
# IMPORTANT SAFETY WARNING
# -----------------------
# This ISO is configured to **automatically begin installation** on boot
# with **no user interaction required**. The preseed file will:
#   - Partition, format, and encrypt the primary SSD
#   - Install Debian without prompts
#
# DO NOT boot this ISO on any system containing important data unless
# you intend to completely wipe the primary disk(s). Review preseed.cfg
# for full installation behavior and disk targeting details.
#
# Requirements:
#   - curl, rsync, xorriso (auto-installed if missing)
#   - ~16 GB free disk space
#
# Usage:
#   sudo ./sc-node/build-scnode-iso.sh
#   (must be run from the parent directory of the sc-node folder)
#
# Note:
#   The script runs inside sc-node/ but writes temporary files and the
#   final ISO to the parent directory (keeps repo folder clean).
# =============================================================================
set -euo pipefail

# ──────────────────────────────────────────────────────────────────────────────
# Enforce running as root
# ──────────────────────────────────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    echo "This script must be run as root"
    exit 1
fi

# ──────────────────────────────────────────────────────────────────────────────
# Verify the sc-node repo folder exists in current directory
# ──────────────────────────────────────────────────────────────────────────────
REPO_DIR="./sc-node"
if [[ ! -d "$REPO_DIR" || ! -f "$REPO_DIR/preseed.cfg" || ! -f "$REPO_DIR/setup.sh" ]]; then
    echo "Error: This script must be run from the parent directory of the sc-node repo: sudo ./sc-node/build-scnode-iso.sh"
    echo "Expected structure:"
    echo "  ./sc-node/build-scnode-iso.sh"
    echo "  ./sc-node/preseed.cfg"
    echo "  ./sc-node/setup.sh"
    echo "Current directory: $(pwd)"
    exit 1
fi

# Config
BASE_URL="https://cdimage.debian.org/debian-cd/current"
TEMP_DIR="./tmp-debian-files"
PRESEED_DEFAULT="${REPO_DIR}/preseed.cfg"
ARCHES=("amd64" "arm64" "riscv64") # User/Debian ISO architectures (what the user selects)
ALT_ARCHES=("x86_64" "aarch64" "riscv64") # Alternative architecture naming (used by BTC, AZC, etc.); Order MUST match ARCHES (above) exactly!

# ──────────────────────────────────────────────────────────────────────────────
# Update and upgrade
# ──────────────────────────────────────────────────────────────────────────────
echo "Updating and upgrading..."; sleep 2
apt update && apt upgrade -y

# ──────────────────────────────────────────────────────────────────────────────
# Check/install required packages
# ──────────────────────────────────────────────────────────────────────────────
echo "Checking/updating required tools..."

REQUIRED_PKGS=(
    curl        # downloads
    rsync       # copy ISO contents
    xorriso     # preferred for hybrid ISO
)

apt-get update -qq

for pkg in "${REQUIRED_PKGS[@]}"; do
    if ! dpkg -s "$pkg" &>/dev/null; then
        echo "Installing: $pkg"
        apt-get install -yqq "$pkg"
    fi
done

# ──────────────────────────────────────────────────────────────────────────────
# Select architecture
# ──────────────────────────────────────────────────────────────────────────────
echo "Select architecture:"
select ARCH in "${ARCHES[@]}"; do [[ -n "$ARCH" ]] && break; done

# ──────────────────────────────────────────────────────────────────────────────
# Dynamic Debian ISO
# ──────────────────────────────────────────────────────────────────────────────
DIR_URL="${BASE_URL}/${ARCH}/iso-dvd/"
ISO_NAME=$(curl -s "$DIR_URL" | grep -oP "debian-\K[0-9.]+\-${ARCH}-DVD-1\.iso" | head -1)
[[ -z "$ISO_NAME" ]] && { echo "No DVD ISO found for $ARCH." >&2; exit 1; }
ISO_NAME="debian-${ISO_NAME}"
ISO_URL="${DIR_URL}${ISO_NAME}"
HASH_URL="${DIR_URL}SHA256SUMS"

echo ""; echo "Download locations:"
echo " ISO:   $ISO_URL"
echo " SHA:   $HASH_URL"; echo ""

# ──────────────────────────────────────────────────────────────────────────────
# Download Debian ISO, checksum, and signature file
# ──────────────────────────────────────────────────────────────────────────────
mkdir -p "$TEMP_DIR"
cd "$TEMP_DIR"
echo "Downloading ISO, SHA256SUMS, signature..."
curl --fail -L -C - -O "$ISO_URL" || { echo "Download failed: $ISO_URL" >&2; exit 1; }
curl --fail -L -O "$HASH_URL" || { echo "Download failed: $HASH_URL" >&2; exit 1; }
grep -F "${ISO_NAME}" SHA256SUMS | sha256sum -c - || { echo "Debian ISO checksum failed" >&2; exit 1; }
echo "Debian ISO checksum verified."

# ──────────────────────────────────────────────────────────────────────────────
# Create MANIFEST-${ARCH} file and add Debian info to it
# ──────────────────────────────────────────────────────────────────────────────
MANIFEST_FILE="../MANIFEST-${ARCH}.txt"
DEBIAN_ISO_SHA256=$(grep -F "${ISO_NAME}" SHA256SUMS | awk '{print $1}')

# Create (or empty/truncate) the manifest file in the parent directory
: > "$MANIFEST_FILE"

cat >> "$MANIFEST_FILE" << EOF
Original Debian DVD-1 ISO (for ${ARCH})
File:               ${ISO_NAME}
SHA256 Checksum:    ${DEBIAN_ISO_SHA256}
EOF
echo "" >> "$MANIFEST_FILE"
echo "Debian DVD-1 ISO details added to the ${MANIFEST_FILE} file"

# ──────────────────────────────────────────────────────────────────────────────
# Extract ISO
# ──────────────────────────────────────────────────────────────────────────────
mkdir -p extracted mnt
mount -o loop "$ISO_NAME" mnt
rsync -a mnt/ extracted/
umount mnt

# ──────────────────────────────────────────────────────────────────────────────
# Copy repo contents into ISO at /sc-node/
# ──────────────────────────────────────────────────────────────────────────────
echo "Copying sc-node repo contents into ISO filesystem..."
rsync -a --exclude='.git' "../${REPO_DIR%/}/" extracted/sc-node
find extracted/sc-node -type d -exec chmod 755 {} +
find extracted/sc-node -type f -exec chmod 644 {} +
find extracted/sc-node -type f -name "*.sh" -exec chmod +x {} \;

# ──────────────────────────────────────────────────────────────────────────────
# Copy required files into ISO at /sc-node/
# ──────────────────────────────────────────────────────────────────────────────
echo "Copying required files into ISO filesystem..."

# Define the target directory in the extracted ISO
TARGET_DIR="extracted/sc-node"

# Create the directory if it doesn't exist
mkdir -p "$TARGET_DIR"

# List of files we actually want (relative to the repo root)
FILES=(
    "preseed.cfg"
    "late-commands.sh"
    "firstboot.sh"
)

# Copy only those files (will fail loudly if any are missing)
for file in "${FILES[@]}"; do
    if [[ -f "../${REPO_DIR%/}/$file" ]]; then
        cp -a "../${REPO_DIR%/}/$file" "$TARGET_DIR/"
        echo "  Copied: $file"
    else
        echo "ERROR: Required file not found: ../${REPO_DIR%/}/$file" >&2
        exit 1
    fi
done

# Set correct permissions
# Directories (just in case, though we only have one)
find "$TARGET_DIR" -type d -exec chmod 755 {} +

# Regular files: 644, but make .sh files executable
find "$TARGET_DIR" -type f -exec chmod 644 {} +
find "$TARGET_DIR" -type f -name "*.sh" -exec chmod +x {} \;

echo "Done copying required files to /sc-node/ in ISO."

# ──────────────────────────────────────────────────────────────────────────────
# Modify GRUB for preseeded auto-install
# ──────────────────────────────────────────────────────────────────────────────
echo "Modifying the boot configuration (grub.cfg) file..."; sleep 2
awk '
/^menuentry/ {
    if (!inserted) {
        print "set timeout=5"
        print "set default=0"
        print "menuentry \047Preseeded Auto Install\047 {"
        print " set background_color=black"
        print " linux /install.amd/vmlinuz vga=788 file=/cdrom/sc-node/preseed.cfg auto=true priority=high --- quiet"
        print " initrd /install.amd/initrd.gz"
        print "}"
        print "menuentry \047Debug Preseeded Install\047 {"
        print " set background_color=black"
        print " linux /install.amd/vmlinuz vga=788 DEBCONF_DEBUG=5 file=/cdrom/sc-node/preseed.cfg priority=low --- quiet"
        print " initrd /install.amd/initrd.gz"
        print "}"
        inserted=1
    }
}
{ print }
' extracted/boot/grub/grub.cfg > grub.tmp || { echo "awk failed" >&2; exit 1; }

# Move updated grub.cfg to proper location and ensure root ownership and read-only permissions are set
mv grub.tmp ./extracted/boot/grub/grub.cfg
chown root:root ./extracted/boot/grub/grub.cfg
chmod 444 ./extracted/boot/grub/grub.cfg

# Verify preseed
echo "Checking preseed syntax..."
debconf-set-selections -c "../${REPO_DIR}/preseed.cfg" || { echo "Preseed syntax FAILED"; exit 1; }
echo "Preseed OK"

# ──────────────────────────────────────────────────────────────────────────────
# Rebuild hybrid ISO (UEFI boot only)
# ──────────────────────────────────────────────────────────────────────────────
BUILD_DATE=$(date '+%Y-%m-%d')   # YYYY-MM-DD format
ISO_FILENAME="sc-node-installer-${BUILD_DATE}-${ARCH}.iso"

echo "Building hybrid ISO: ${ISO_FILENAME} ..."

xorriso -as mkisofs -o "../${ISO_FILENAME}" \
    -eltorito-alt-boot -e boot/grub/efi.img -no-emul-boot \
    -J -R -V 'SCNODE' extracted/

[[ -f "../${ISO_FILENAME}" ]] || { echo "ISO build failed" >&2; exit 1; }

echo "ISO built successfully: ../${ISO_FILENAME}"

# ──────────────────────────────────────────────────────────────────────────────
# Success message + display manifest contents via cat
# ──────────────────────────────────────────────────────────────────────────────
echo ""; cd ..
cat <<EOF
SC Node Installer ISO Created Successfully!

Output ISO:         $(pwd)/${ISO_FILENAME}
Size:               $(du -h "${ISO_FILENAME}" | cut -f1)
Manifest:           $(pwd)/MANIFEST-${ARCH}.txt

Cleanup (from parent directory): rm -rf tmp-debian-files

Manifest Contents:
───────────────────────────────────────────────
$(cat "MANIFEST-${ARCH}.txt")
───────────────────────────────────────────────
EOF