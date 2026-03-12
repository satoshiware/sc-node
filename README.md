# SC Node
The SC Node (Sovereign Circle Node) is a low-cost, self-hosted mini-PC setup designed to run basic banking infrastructure (nodes, pools, exchanges, etc.) for its owner and members. Its successful operation depends on a constant connection with a bigger, more complete, node (i.e. “SC Cluster” Node) with technical support readily available. The SC Node only requires a wired ethernet internet connection and nothing more to just work. This repository contains all the resources to program and configure a new SC Node for future Sovereign Circle owners.

## Objectives and Key Functions
* Run a full AZCoin node to contribute to the broader AZCoin blockchain's decentralization with the ability to sweep AZCoin private keys.
* Integrate Bitcoin, AZCoin, and microcurrencies wallets that allow real-time visibility into incoming member deposits. Operate a Lightning Node with a channel to its “SC Cluster” Node.
* This Lightning node provides Lightning as a Service (LaaS) to the members of its Sovereign Circle via the Satoshiware mobile wallet app.
* The SC Node includes Stratum v1.0 mining servers for both Bitcoin and AZCoin (connected via Stratum v2.0 on the backend). This allows Sovereign Circle members to connect their miners to efficiently pool hashrate and earn AZCoin and Bitcoin mining rewards. Proceeds are deposited directly into their SC Node exchange accounts.
* Lightweight, self-hosted exchange service to enable seamless swapping between AZCoin (or the local microcurrency) and SATS.
* Owner Dashboard: A secure web interface enabling node owners to perform essential management tasks, including member administration, moving deposits and funds, and oversight of the SC Node's core components.
* Member Dashboard: A secure, user-friendly web interface enabling community members to interact with the SC Node's exchange, perform deposits and withdrawals, mining configuration, and manage basic account functions such as viewing transaction history, balances, and open orders.

## Hardware Specifications
* RAM: 32 GB
* SSD: 2 TB
* CPU: 4-core processor with fTPM 2.0 support (required for encrypted disk)
* Networking: Gigabit Ethernet
* Power: <50 W

## Architecture
### AZCoin Full Node w/ Basic Configuration
* ZeroMQ (ZMQ) Enabled for Push-Based Notifications
* API: Python w/ FastAPI (RESTful & WebSockets)
  * Single main wallet with accounting/labels — generate unique addresses per user, and track balances externally in the exchange database.
  * Static API Keys for Basic Internal Authorization (Rotate keys periodically for best security)
  * The ability to sweep private keys
* Backup/Restore: wallet.dat files
* Use the Assume Valid feature to speed up Initial Blockchain Download (IBD)

### Bitcoin Pruned Node w/ Basic Configuration
* ZeroMQ (ZMQ) Enabled for Push-Based Notifications
* API: Python w/ FastAPI (RESTful & WebSockets)
  * Main wallet with accounting/labels — generate unique addresses per user, and track balances externally in your database.
  * Static API Keys for Basic Internal Authorization (Rotate keys periodically for best security)
* Backup/Restore: wallet.dat file
* Prune=25000 (~25-100 GB); 6 months worth of Bitcoin Blockchain data to help keep Core Lightning in sync.
* Use the Assume Valid feature to speed up Initial Blockchain Download (IBD)

### Core Lightning Node
* Single large channel w/ the SC Cluster Node
* Auto balancing programmed with the trusted SC Cluster Node
* API: Python w/ FastAPI (RESTful & WebSockets)
  * Install reckless:cl-zmq plugin for local push notifications
  * Static API Keys for Basic Internal Authorization (Rotate keys periodically for best security)
* Backup/Restore: hsm_secret, lightningd.sqlite3, and emergency.recover files

### Stratum V2 Translation Proxy (SRI) (Bitcoin)
* Configure w/ High Verbosity (RUST_LOG=info or debug)
* API: Python w/ FastAPI (RESTful & WebSockets)
  * Use Python`s asyncio to tail the log file (or pipe stdout) in real time.
  * Process data as desired and store rolling windows to a lightweight DB (SQLite).
  * Static API Keys for Basic Internal Authorization (Rotate keys periodically for best security)
* Backup: None

### Stratum V2 Translation Proxy (SRI) (AZCoin)
* Configure w/ High Verbosity (RUST_LOG=info or debug)
* API: Python w/ FastAPI (RESTful & WebSockets)
  * Use Python`s asyncio to tail the log file (or pipe stdout) in real time.
  * Process data as desired and store rolling windows to a lightweight DB (SQLite).
  * Static API Keys for Basic Internal Authorization (Rotate keys periodically for best security)
* Backup: None

### Exchange: AZCoin (and/or the local microcurrency) w/ SATS
* Contains all member accounting (including deposit addresses)
* Connects w/ Bitcoin Core, AZCoin, and Core Lightning nodes to acquire and monitor deposit addresses
* Connects with Stratum Servers and updates accounts with mining payouts
* API: Python w/ FastAPI (RESTful & WebSockets)
  * Provide Lightning as a Service (LaaS)
  * Generate deposit addresses (or lightning invoices)
  * Has the ability to withdraw (send)

### Member Dashboard
* Shared login with BTCofAZ w/ Local 2FA
* Account Settings: Configure/Reset 2FA
* Mining Info: Stats, Histogram, and Payouts
* Wallet: See Totals, Make Deposits & Withdrawals, and Inspect History (w/ Addresses)
* Exchange: Limit Orders, Personal & Global History, Trading Interface, Charts, etc.
* SC Transparancy Audit

### Owner Dashboard
* Overall Health
* Upgrades
* Manage Members: Reset 2FA, Make Withdrawals, See Exchange/Account Info
* Cold Storage Management
* See Overall Mining Stats & Payouts

## Build & Release the Sovereign Circle Node ISO
Steps to create a custom, hands-free installation ISO for the Sovereign Circle Node.
It uses the build-scnode-iso.sh script found in the SC Node repository: https://github.com/satoshiware/sc-node.
This script always uses the tip of the master branch.

1. On Linux with **sudo** privileges, clone the repository:
- sudo apt update && sudo apt upgrade -y && sudo apt install -y git
- git clone https://github.com/satoshiware/sc-node

2. Run the build script:
- sudo chmod +x ./sc-node/build-scnode-iso.sh
- sudo ./sc-node/build-scnode-iso.sh

This script:
- Downloads the latest official **Debian** DVD-1 ISO (~4.7 GB base).
- Remasters it (no source compilation).
- Integrates `preseed.cfg` for fully automated install.
- Copies the entire `sc-node` repository to `/root/sc-node` in the target filesystem.
- Downloads and verifies required binaries (Bitcoin, AZCoin, Stratum, Lightning, etc.) that will be installed via the `setup.sh` script.
- Modifies ISO GRUB boot menu to offer preseeded **auto-install** (starts after 5 seconds) and **debug** options.

Once complete, the script outputs a non-versioned ISO w/ the chosen CPU type: e.g., `sc-node-X.X.X-amd64.iso`
It also outputs a MANIFEST-CPUTYPE (e.g. MANIFEST-amd64) file with the names of all included binaries (alongside the Debian DVD ISO), their checksums, and their signatures.

**WARNING!** Booting from this ISO will **automatically and without prompts** wipe the first non-removable disk and set up maximum encrypted LVM — use only on dedicated SC Node hardware!

Notable configurations by `preseed.cfg` (excluding `setup.sh` actions):
- Timezone: **UTC** (location-independent)
- Hostname: `sc-node`
- Domain: `internal`
- Root login: **disabled**
- User: `satoshi` (with sudo)
  - Password: `satoshi` (**CHANGE IMMEDIATELY** post-install!)
  - Name: Satoshi Nakamoto
- Partitioning: LUKS encryption on LVM
- Packages: `curl`, `tpm2-tools` (for TPM detection/binding in `setup.sh`)
- Runs late_commands.sh script to ensure `sc-node/setup.sh` runs via firstboot.sh script, on first boot

**Disk Encryption Notes (Automated via Preseed):**
- `setup.sh` (run by firstboot.sh) binds the partitioning encryption key to the fTPM 2.0 and enables headless auto-unlock.
- If TPM missing/not enabled, `setup.sh` halts with error (e.g., "TPM 2.0 not detected — enable fTPM/PTT in BIOS and reinstall").

### Requirements to Build the ISO
- A linux host system w/ **sudo** privileges
- ~16 GB free disk space (original ISO ≈ 4.7 GB + extracted contents + temporary files)
- Good Internet (for downloading ~4.7 GB ISO + tools/repo)
- Required packages (automatically installed if missing): `git`, `curl`, `gnupg`, `rsync`, `xorriso`

### Publish Release
- Run the ISO build script for **each supported CPU architecture**  to generate all variants
    Hey! It makes sense to use the same binary version for each run
- Verify signatures in the MANIFEST-\* files
- Rename each ISO to update the target version for release: e.g., `sc-node-X.X.X-amd64.iso` --> `sc-node-1.4.3-amd64.iso`
- Generate a checksum file for all ISOs and MANIFEST-\* files:
    sha256sum -- * 2>/dev/null | grep -v '  SHA256SUMS$' > SHA256SUMS # Run in same directory as iso files
    sha256sum -- MANIFEST* 2>/dev/null | grep -v '  SHA256SUMS$' >> SHA256SUMS
- Generate the signature file: SHA256SUMS.asc
    gpg --detach-sign --armor --local-user $LONGKEYID --output SHA256SUMS.asc SHA256SUMS
- Split the ISO files into 1G chunks (Github Release Assets are limited to 2GB file sizes)
    for f in *.iso; do split -b 1G -d --additional-suffix=.part "$f" "$f."; done
- Go to the github.com repository → **Releases** → **Draft a new release**
- Create a new tag (e.g., `v1.4.3`)
- Set the release title (e.g., `SC Node v1.4.3`)
- Add release notes - Include the contents of all the MANIFEST-\* file
- Attach assets: renamed `.iso` files, checksum file, signature file, and the MANIFEST-\* files
- Publish the release

## Create USB Install Stick
Dedicated USB with 8GB+ is required.
USB 3.0+ is highly recommended to shorten the setup time for each SC Node.

1. Download all the latest ISO files for the desired CPU: https://github.com/satoshiware/sc-node/releases
2. Combine the ISO files into a single ISO file
    cat sc-node-X.X.X-CPUTYPE.iso.\*.part > sc-node-X.X.X-CPUTYPE.iso
3. Verify ISO Checksum and Signature
4. Depending on your OS (Windows, Linux, or even Linux on Windows [WSL]), search for an online guide to correctly write an ISO to a USB drive so that it will boot and install as desired.
5. Label the USB stick accordingly

## SC Node Setup (w/ USB Install Stick)
To get a new Sovereign Circle Node up and running, follow these steps in order.

### Prerequisites
- Mini-PC to become the next SC Node that meets the [Hardware Specifications](#hardware-specifications)
- Wired Internet
- Latest USB Install Stick
- A USB barcode/QR scanner plugged into the SC Node
- One unique (pre-generated) **SC Node Key Card** (see [SC Node Key Card](#sc-node-key-card--design--contents) for details)

### Step 1: BIOS/UEFI Preparation (Mandatory)
Before booting from USB, configure the BIOS/UEFI on the target mini-PC:

1. Enter BIOS/UEFI Setup
2. Enable **fTPM / PTT** (firmware TPM 2.0)
3. Enable **Secure Boot**
4. Set the **supervisor/admin password** to match Satoshi's password printed on the SC Node Key Card
   - **CRITICAL** Ensure you scanned/entered the correct information from the SC Node Key Card!
5. Set boot priority:
   - Primary boot device → internal SSD/NVMe (Everything else is disabled)
   - Enable one-time boot override to USB
6. Save changes and exit.

**Important:** If fTPM/PTT is disabled, the setup will fail later — there is no fallback mode.

### Step 2: Boot from USB Install Stick
1. Insert the USB Install Stick into the SC Node
2. Power on (or reboot)
3. The GRUB menu appears → **auto-install** option starts in 5 seconds (or press Enter to begin immediately).
4. The preseeded Debian installer runs hands-free:
   - Wipes the first non-removable disk (SSD/NVMe) with no prompts
   - Partitions: unencrypted EFI + `/boot`, encrypted LVM for root (auto-generated random strong passphrase created during install)
   - Minimal Debian install + listed packages
   - Creates user `satoshi` with sudo rights and `satoshi` as a temporary password
   - Executes `late_commands.sh` to finalize base config, and configure firstbooth.sh and setup.sh to run next boot
5. Installation completes → system reboots automatically to the internal SSD

### Step 3: First Boot – Pairing & Final Configuration
After reboot, the system boots into the new Debian install:

1. `firstboot.sh` runs automatically (configurred by the preseeded config)
   - It launches the setup.sh script and then self-deletes from ever running again automatically
2. `setup.sh` launches and begins interactive setup:
   - Prompts you to scan contents from the **SC Node Key Card** using the connected barcode/QR scanner
   - Prompts for verification to ensure all information was entered correctly
3. The remaining `setup.sh` script is non-interactive
   - Binds the auto-generated LUKS key to fTPM 2.0
   - Regenerates initramfs for TPM auto-unlock on future boots
   - Installs and configures all core components: Bitcoin, AZCoin, Lightning, Stratum, etc.
4. Reboot to confirm headless TPM auto-unlock works (disk should unlock silently without passphrase)
5. Review logs: `/var/log/*.log`

Once finished, your SC Node is fully operational, paired with its unique Key Card, and ready to serve your Sovereign Circle.

## <<<<<<<<<<<<<<<<<<<< Key card stuff here <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

## Server (Hub) Specs – 800 Clients
Optimized, cost-effective server sufficient for 800 WireGuard clients (SC Nodes) under moderate load.

**Recommended Specs**
- CPUs: 8–16 cores
- RAM: 16–32 GB
- Storage: 256–512 GB SSD/NVMe
- Network: 1–10 Gbps uplink with 1 public IPv4
- Outbound transfer: ≥6 TB/month (or high-egress plan)