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
gpg --keyserver keyring.debian.org --recv-keys $DEBIAN_KEY_ID
gpg --verify SHA256SUMS.sign SHA256SUMS || { echo "GPG failed!"; exit 1; }
grep -- "$ISO_NAME" SHA256SUMS | sha256sum -c - || { echo "Checksum failed!"; exit 1; }
echo "Verification passed."

# ──────────────────────────────────────────────────────────────────────────────
# Add sc_node repo (including the preseed.cfg file) and modify the boot configuration (grub.cfg)
# ──────────────────────────────────────────────────────────────────────────────
mkdir -p extracted mnt
sudo mount -o loop "$ISO_NAME" mnt
sudo rsync -a mnt/ extracted/
sudo umount mnt

# Clone sc_node repository to add to the iso. Used for installing and configuring new Sovereign Circle Nodes after Debian install.
echo "Cloning SC_Node repository from GitHub..."
sudo git clone https://github.com/satoshiware/sc_node.git sc_node || {
    echo "Error: Failed to clone https://github.com/satoshiware/sc_node" >&2
    exit 1
}

# Copy sc_node cloned repo into the extracted filesystem (i.e. base directory of the future installed system).
echo "Copying SC_Node repo contents (including the preseed.cfg file) into base directory..."
sudo rsync -a --exclude='.git' sc_node/ extracted/sc_node

# Set all directories w/ readable + executable/traversable permissions
sudo find extracted/sc_node -type d -exec chmod 755 {} +

# Set all files to read-only
sudo find extracted/sc_node -type f -exec chmod 644 {} +

# Make all .sh files executable (recursively)
find extracted/sc_node -type f -name "*.sh" -exec sudo chmod +x {} \;

# Inject GRUB auto-install params before the line with the first menuentry
echo "Modifying the boot configuration (grub.cfg) file..."; sleep 2
awk '
/^menuentry/ {
    if (!inserted) {
        print "set timeout=5"
        print "set default=0"
        print "menuentry \047Preseeded Auto Install\047 {"
        print "    set background_color=black"
        print "    linux    /install.amd/vmlinuz vga=788 file=/cdrom/sc_node/preseed.cfg auto=true priority=high --- quiet"
        print "    initrd   /install.amd/initrd.gz"
        print "}"
        print "menuentry \047Debug Preseeded Install\047 {"
        print "    set background_color=black"
        print "    linux    /install.amd/vmlinuz vga=788 DEBCONF_DEBUG=5 file=/cdrom/sc_node/preseed.cfg priority=low --- quiet"
        print "    initrd   /install.amd/initrd.gz"
        print "}"
        inserted=1
    }
}
{ print }
' extracted/boot/grub/grub.cfg > grub.tmp || { echo "awk failed" >&2; exit 1; }

# Move updated grub.cfg to proper location and ensure root ownership and read-only permissions are set
sudo mv grub.tmp ./extracted/boot/grub/grub.cfg
sudo chown root:root ./extracted/boot/grub/grub.cfg
sudo chmod 444 ./extracted/boot/grub/grub.cfg

# Verify preseed.cfg syntax
echo "Checking preseed syntax ... "
debconf-set-selections -c ./extracted/sc_node/preseed.cfg || { echo "Preseed syntax validation FAILED!"; cat preseed-validate.err; exit 1; } && echo "Preseed OK"

# ──────────────────────────────────────────────────────────────────────────────
# Rebuild hybrid ISO (UEFI boot only)
# ──────────────────────────────────────────────────────────────────────────────
echo "Building modified ISO..."
xorriso -as mkisofs -o ../modified.iso \
    -eltorito-alt-boot -e boot/grub/efi.img -no-emul-boot \
    -J -R -V 'Debian Preseed Installer' extracted/

[[ -f ../modified.iso ]] || { echo "ISO build failed"; exit 1; }

# ──────────────────────────────────────────────────────────────────────────────
# Inform user of success
# ──────────────────────────────────────────────────────────────────────────────
cd ..; cat <<EOF
=============================================================================
  SC Node Preseeded Debian Installer ISO successfully created!
=============================================================================
Output file: $(pwd)/modified.iso
Size:       $(du -h modified.iso | cut -f1)

IMPORTANT NOTES:
  • Temporary files (tmp-debian-files/, extracted/, sc-node/, mnt/) are NOT deleted.
EOF