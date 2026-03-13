#!/usr/bin/env bash
# =============================================================================
# Builds a bootable Debian full-install ISO (based on official DVD-1)
# Customized for SC Node automation:
#   - Preseeded with preseed.cfg for fully unattended installation
#   - Injects sc-node repository contents into the ISO filesystem
#
# IMPORTANT SAFETY WARNING
# -----------------------
# This ISO is configured to **automatically begin installation** on boot
# with **no user interaction required**. The preseed file will:
#   - Partition, format, and encrypt the primary SSD
#   - Install Debian without prompts
#   - Proceed with SC Node setup steps
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
DEBIAN_KEY_ID="0x6294BE9B"
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

# Translate selected Debian arch to alternative arch name
ALT_ARCH=""
for i in "${!ARCHES[@]}"; do
    if [[ "${ARCHES[$i]}" == "$ARCH" ]]; then
        ALT_ARCH="${ALT_ARCHES[$i]}"
        break
    fi
done

if [[ -z "$ALT_ARCH" ]]; then
    echo "Error: No alternative arch mapping for selected architecture '$ARCH'" >&2
    exit 1
fi

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
SC Node ISO Manifest - Verified Hashes of Critical Files

Debian DVD-1 ISO (for ${ARCH})
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
# Bitcoin download + checksum verification
# ──────────────────────────────────────────────────────────────────────────────
echo ""; echo "Fetching available Bitcoin Core versions from bitcoincore.org..."

BITCOIN_URL="https://bitcoincore.org/bin"

# Fetch versions, sort descending (newest first), limit to top 8 for menu readability
BTC_VERSIONS=($(curl -s --fail "$BITCOIN_URL/" \
    | grep -oP 'bitcoin-core-\K[0-9.]+(?=/)' \
    | sort -Vru \
    | head -n 8))

if [[ ${#BTC_VERSIONS[@]} -eq 0 ]]; then
    echo "Error: Could not fetch any Bitcoin Core versions." >&2
    exit 1
fi

echo ""
echo "Available recent versions (newest first):"
PS3="Enter a number (1-${#BTC_VERSIONS[@]}) to select, or type a version directly (e.g., 28.0): "
select BTC_SELECTED_VER in "${BTC_VERSIONS[@]}"; do
    if [[ -n "$BTC_SELECTED_VER" ]]; then
        # User picked from list → good
        break
    elif [[ -n "$REPLY" ]]; then
        # User typed something not in list → treat as custom version
        BTC_SELECTED_VER="$REPLY"
        # Basic format check: digits and dots only, no leading/trailing dots
        if ! [[ "$BTC_SELECTED_VER" =~ ^[0-9]+(\.[0-9]+)+$ ]]; then
            echo "Invalid format. Use something like 28.0, 27.1, etc." >&2
            continue  # let them try again
        fi
        # Quick existence check (HEAD request to dir)
        CUSTOM_URL="${BITCOIN_URL}/bitcoin-core-${BTC_SELECTED_VER}/"
        if ! curl -s --head --fail "$CUSTOM_URL" >/dev/null; then
            echo "Version ${BTC_SELECTED_VER} not found at ${CUSTOM_URL}" >&2
            continue
        fi
        # If we reach here → valid custom
        break
    else
        echo "Please enter a number or version string."
    fi
done

echo "Using Bitcoin Core: v${BTC_SELECTED_VER} (${ALT_ARCH})"

# Proceed with download using $BTC_SELECTED_VER
BITCOIN_URL_DIR="${BITCOIN_URL}/bitcoin-core-${BTC_SELECTED_VER}"
BITCOIN_TAR_NAME="bitcoin-${BTC_SELECTED_VER}-${ALT_ARCH}-linux-gnu.tar.gz"
BITCOIN_SHA256_URL="${BITCOIN_URL_DIR}/SHA256SUMS"

# Download the tarball into the ISO extraction path
curl --fail -L -o "extracted/sc-node/${BITCOIN_TAR_NAME}" "${BITCOIN_URL_DIR}/${BITCOIN_TAR_NAME}" || { echo "Download failed: ${BITCOIN_TAR_NAME} (missing for this version/arch?)" >&2; exit 1; }

# Download checksums/signature to current dir ($TEMP_DIR)
curl --fail -L -O "$BITCOIN_SHA256_URL" || { echo "Download failed: SHA256SUMS" >&2; exit 1; }

# Verify checksum
ln -sf "extracted/sc-node/${BITCOIN_TAR_NAME}" "./${BITCOIN_TAR_NAME}" || { echo "Symlink for verification failed" >&2; exit 1; } # Symlink the tarball into current dir ($TEMP_DIR) so sha256sum -c can find it easily
if ! grep -F "${BITCOIN_TAR_NAME}" SHA256SUMS | sha256sum -c -; then # Verify (now the symlink makes the file appear local)
    echo "Bitcoin Core checksum failed for ${BITCOIN_TAR_NAME}" >&2
    rm -f "./${BITCOIN_TAR_NAME}"
    exit 1
fi
rm -f "./${BITCOIN_TAR_NAME}"  # remove symlink (file itself is untouched)
echo "Bitcoin Core v${BTC_SELECTED_VER} checksum verified."

# Append Bitcoin Core info to manifest
BTC_TAR_SHA256=$(grep -F "${BITCOIN_TAR_NAME}" SHA256SUMS | awk '{print $1}')

cat >> "$MANIFEST_FILE" << EOF
Bitcoin Core (for ${ALT_ARCH})
File:               ${BITCOIN_TAR_NAME}
SHA256 Checksum:    ${BTC_TAR_SHA256}
EOF
echo "" >> "$MANIFEST_FILE"
echo "Bitcoin Core details added to the ${MANIFEST_FILE} file"

# ──────────────────────────────────────────────────────────────────────────────
# AZCoin download + checksum verification
# ──────────────────────────────────────────────────────────────────────────────
echo ""; echo "Fetching available AZCoin release versions from GitHub..."

AZCOIN_REPO_URL="https://github.com/satoshiware/azcoin/releases"
AZCOIN_VERSIONS=($(curl -s --fail "$AZCOIN_REPO_URL" \
    | grep -oP 'v\K[0-9.]+(?=</a>)' \
    | sort -Vru \
    | head -n 8))

if [[ ${#AZCOIN_VERSIONS[@]} -eq 0 ]]; then
    echo "Error: Could not fetch AZCoin versions from GitHub." >&2
    exit 1
fi

echo ""
echo "Available recent versions (newest first):"
PS3="Enter a number (1-${#AZCOIN_VERSIONS[@]}) or type a version directly (e.g., 0.2.0): "
select AZCOIN_SELECTED_VER in "${AZCOIN_VERSIONS[@]}"; do
    if [[ -n "$AZCOIN_SELECTED_VER" ]]; then
        break
    elif [[ -n "$REPLY" ]]; then
        AZCOIN_SELECTED_VER="$REPLY"
        if ! [[ "$AZCOIN_SELECTED_VER" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            echo "Invalid format. Use something like 0.2.0, 0.1.5, etc." >&2
            continue
        fi
        CUSTOM_URL="${AZCOIN_REPO_URL}/download/v${AZCOIN_SELECTED_VER}/"
        if ! curl -s --head --fail "$CUSTOM_URL" >/dev/null; then
            echo "Version v${AZCOIN_SELECTED_VER} not found at ${CUSTOM_URL}" >&2
            continue
        fi
        break
    else
        echo "Please enter a number or version string."
    fi
done

echo "Using AZCoin: v${AZCOIN_SELECTED_VER} (${ALT_ARCH})"

AZCOIN_URL_DIR="${AZCOIN_REPO_URL}/download/v${AZCOIN_SELECTED_VER}"
AZCOIN_TAR_NAME="azcoin-${AZCOIN_SELECTED_VER}-${ALT_ARCH}-linux-gnu.tar.gz"
AZCOIN_SHA256_URL="${AZCOIN_URL_DIR}/SHA256SUMS"

# Download the tarball into the ISO extraction path
curl --fail -L -o "extracted/sc-node/${AZCOIN_TAR_NAME}" "${AZCOIN_URL_DIR}/${AZCOIN_TAR_NAME}" || { echo "Download failed: ${AZCOIN_TAR_NAME} (missing for this version/arch?)" >&2; exit 1; }

# Download checksum file to current dir ($TEMP_DIR)
curl --fail -L -O "$AZCOIN_SHA256_URL" || { echo "Download failed: SHA256SUMS" >&2; exit 1; }

# Verify checksum
ln -sf "extracted/sc-node/${AZCOIN_TAR_NAME}" "./${AZCOIN_TAR_NAME}" || { echo "Symlink for verification failed" >&2; exit 1; } # Symlink the tarball into current dir ($TEMP_DIR) so sha256sum -c can find it easily
if ! grep -F "${AZCOIN_TAR_NAME}" SHA256SUMS | sha256sum -c -; then # Verify (now the symlink makes the file appear local)
    echo "AZCoin checksum failed for ${AZCOIN_TAR_NAME}" >&2
    rm -f "./${AZCOIN_TAR_NAME}"
    exit 1
fi
rm -f "./${AZCOIN_TAR_NAME}" # remove symlink (file itself is untouched)
echo "AZCoin v${AZCOIN_SELECTED_VER} checksum verified."

# Append AZCoin Core info to manifest
AZCOIN_TAR_SHA256=$(grep -F "${AZCOIN_TAR_NAME}" SHA256SUMS | awk '{print $1}')

cat >> "$MANIFEST_FILE" << EOF
AZCoin Core (for ${ALT_ARCH})
File:               ${AZCOIN_TAR_NAME}
SHA256 Checksum:    ${AZCOIN_TAR_SHA256}
EOF
echo "" >> "$MANIFEST_FILE"
echo "AZCoin Core details added to the ${MANIFEST_FILE} file"

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