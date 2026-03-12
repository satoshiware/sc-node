#!/usr/bin/env bash
# =============================================================================
# Creates a bootable Debian full install .iso (based on Debian's DVD-1)
# Modified for SC Node setup automation:
#   Preseeded with preseed.cfg
#   Injects sc-node repo contents + binaries into the ISO filesystem
#
# REQUIRES:
#   curl gnupg rsync xorriso (auto-installed if missing)
#   16 GB of free space
#
# RUN FROM THE PARENT DIRECTORY like this:
#   sudo ./sc-node/build-scnode-iso.sh
#
# The script lives inside the sc-node/ folder but writes temp files and the
# final ISO to the parent directory (keeps repo folder clean).
# =============================================================================
set -euo pipefail # Catch and exit on all errors

# ──────────────────────────────────────────────────────────────────────────────
# Enforce running as root
# ──────────────────────────────────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    echo "This script must be run as root (sudo ./sc-node/build-scnode-iso.sh)"
    exit 1
fi

# ──────────────────────────────────────────────────────────────────────────────
# Verify the sc-node repo folder exists in current directory
# ──────────────────────────────────────────────────────────────────────────────
REPO_DIR="./sc-node"
if [[ ! -d "$REPO_DIR" || ! -f "$REPO_DIR/preseed.cfg" || ! -f "$REPO_DIR/setup.sh" ]]; then
    echo "Error: This script must be run from the parent directory of the sc-node repo."
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
DEBIAN_KEY_ID="0x6294BE9B"
ARCHES=("amd64" "arm64" "ppc64el" "riscv64" "s390x")

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
    gnupg       # gpg verification
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
SIG_URL="${HASH_URL}.sign"

echo ""; echo "Download locations:"
echo " ISO:   $ISO_URL"
echo " SHA:   $HASH_URL"
echo " SIG:   $SIG_URL"; echo ""

# ──────────────────────────────────────────────────────────────────────────────
# Download & verify Debian ISO
# ──────────────────────────────────────────────────────────────────────────────
mkdir -p "$TEMP_DIR"
cd "$TEMP_DIR"
echo "Downloading ISO, SHA256SUMS, signature..."
curl -LO -C - "$ISO_URL"
curl -LO "$HASH_URL"
curl -LO "$SIG_URL"

gpg --keyserver keyring.debian.org --recv-keys "$DEBIAN_KEY_ID"
gpg --verify SHA256SUMS.sign SHA256SUMS || { echo "GPG verify failed"; exit 1; }
grep -- "$ISO_NAME" SHA256SUMS | sha256sum -c - || { echo "Checksum failed"; exit 1; }
echo "Debian ISO verified."

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
# Bitcoin Core binaries (unchanged from previous version)
# ──────────────────────────────────────────────────────────────────────────────
echo "Downloading and verifying latest Bitcoin Core binaries..."
BITCOIN_BASE="https://bitcoincore.org/bin"
LATEST_VER=$(curl -s "$BITCOIN_BASE/" | grep -oP 'bitcoin-core-\K[0-9.]+(?=/)' | sort -V | tail -1)
[[ -z "$LATEST_VER" ]] && { echo "Could not detect latest Bitcoin Core version"; exit 1; }

BITCOIN_DIR="$BITCOIN_BASE/bitcoin-core-${LATEST_VER}"
BIN_NAME="bitcoin-${LATEST_VER}-${ARCH}-linux-gnu.tar.gz"
SHA256_URL="${BITCOIN_DIR}/SHA256SUMS"
SIG_URL="${BITCOIN_DIR}/SHA256SUMS.asc"

mkdir -p binaries/bitcoin-core
cd binaries/bitcoin-core
curl -LO "${BITCOIN_DIR}/${BIN_NAME}"
curl -LO "$SHA256_URL"
curl -LO "$SIG_URL"

gpg --keyserver hkps://keys.openpgp.org --recv-keys 01EA5486DE18A882D4C2684590C8019E36C2E964
gpg --verify SHA256SUMS.asc SHA256SUMS || { echo "Bitcoin SHA256SUMS sig failed"; exit 1; }
grep "${BIN_NAME}" SHA256SUMS | sha256sum -c - || { echo "Bitcoin Core checksum failed"; exit 1; }

echo "Bitcoin Core v${LATEST_VER} verified."
tar -xzf "${BIN_NAME}"
mkdir -p ../../extracted/sc-node/binaries/bitcoin-core
cp -r bitcoin-${LATEST_VER}/* ../../extracted/sc-node/binaries/bitcoin-core/
cd - >/dev/null

# ──────────────────────────────────────────────────────────────────────────────
# AZCoin placeholder
# ──────────────────────────────────────────────────────────────────────────────
echo "AZCoin: No pre-built binaries yet[](https://github.com/satoshiware/azcoin)"
echo "Latest release (v0.2.0) has no attached assets — build from source using cross-compile.sh."
echo "After building, place the binaries (e.g., azcoin-0.2.0-${ARCH}-linux-gnu.tar.gz) and any SHA256SUMS in ../azcoin-binaries/"
echo "They will be copied to ISO at /sc-node/binaries/azcoin/"

if [ -d "../azcoin-binaries" ]; then
    mkdir -p extracted/sc-node/binaries/azcoin
    rsync -a ../azcoin-binaries/ extracted/sc-node/binaries/azcoin/
    echo "AZCoin binaries copied."
else
    echo "No ../azcoin-binaries/ — skipping."
fi

# ──────────────────────────────────────────────────────────────────────────────
# Get short commit hash from current repo state (master/main tip)
# ──────────────────────────────────────────────────────────────────────────────
if command -v git >/dev/null && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    COMMIT_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
else
    COMMIT_HASH="no-git"
    echo "Warning: git not found or not in a git repo — using 'no-git' in filename."
fi

# ──────────────────────────────────────────────────────────────────────────────
# Define output ISO name using commit hash
# ──────────────────────────────────────────────────────────────────────────────
OUTPUT_ISO="../sc-node-${COMMIT_HASH}-${ARCH}.iso"

echo "Building modified ISO as ${OUTPUT_ISO}..."
xorriso -as mkisofs -o "$OUTPUT_ISO" \
    -eltorito-alt-boot -e boot/grub/efi.img -no-emul-boot \
    -J -R -V 'Debian Preseed Installer' extracted/
[[ -f "$OUTPUT_ISO" ]] || { echo "ISO build failed"; exit 1; }

# ──────────────────────────────────────────────────────────────────────────────
# Success message
# ──────────────────────────────────────────────────────────────────────────────
cd ..
cat <<EOF
=============================================================================
  SC Node Preseeded Debian Installer ISO created!
=============================================================================
Output: $(pwd)/$(basename "$OUTPUT_ISO")
Size: $(du -h "$OUTPUT_ISO" | cut -f1)

Commit: ${COMMIT_HASH}
Binaries included:
- Bitcoin Core v${LATEST_VER} (verified)
- AZCoin v0.2.0 (checksum verified where available)

Cleanup (from parent directory): rm -rf tmp-debian-files extracted mnt
EOF