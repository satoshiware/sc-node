# SC Node
The SC Node (Sovereign Circle Node) is a low-cost, self-hosted mini-PC setup designed to run basic banking infrastructure (nodes, pools, exchanges, etc.) for its owner and members. Its successful operation depends on a constant connection with a bigger, more complete, node (i.e. “SC Cluster” or "Mega" Server) with technical support readily available. The SC Node only requires a wired ethernet internet connection and nothing more to just work. This repository contains all the resources to program and configure a new SC Node for future Sovereign Circle owners.

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
Use the `build-scnode-iso.sh` linux script to create a hands-free installation Debian ISO used to prepare the foundational OS for the SC Node.

To run, on Linux machine (i.e. Debian) with **sudo** privileges execute the following:<br>
`sudo apt update && sudo apt upgrade -y && sudo apt install -y git`<br>
`git clone https://github.com/satoshiware/sc-node`<br>
`sudo bash ./sc-node/build-scnode-iso.sh`<br>

This script:
- Downloads the latest official **Debian** DVD-1 ISO (~4.7 GB base)
- Copies sc-node files (from the tip of the main branch): `preseed.cfg`, `late-commands.sh`, and `firstboot.sh` scripts
- Modifies GRUB boot menu to offer preseeded **auto-install** (starts automatically after 5 seconds) and **debug** options.
- Remasters the ISO
- Outputs a MANIFEST-CPUTYPE (e.g. MANIFEST-amd64) file containing the original ISO file-name and its SHA256 hash for manual verification

Once complete, the script outputs a non-versioned ISO w/ the chosen CPU type: e.g., `sc-node-X.X.X-amd64.iso`

**WARNING!** Booting from this ISO will **automatically and without prompts** wipe the first non-removable disk — use only on dedicated SC Node hardware!

Notable configurations in the `preseed.cfg` file:
- Timezone: **UTC** (location-independent)
- Hostname: `sc-node`
- Domain: `internal`
- Root login: **disabled**
- User: `satoshi` (with sudo)
    Password: `satoshi`
    Name: Satoshi Nakamoto
- Partitioning: Full disk LVM
- Packages: `curl`, `sudo`, `ssh`
- Runs `late_commands.sh` script to finalize base config, and configure `firstbooth.sh` to run next boot

### Requirements to Build the ISO
- A linux host system w/ **sudo** privileges
- ~16 GB free disk space (original ISO ≈ 4.7 GB + extracted contents + temporary files)
- Good Internet (for downloading ~4.7 GB ISO + tools/repo)
- Required packages (automatically installed if missing): `curl`, `rsync`, `xorriso`

### Prerequisites: Running the installation ISO on a new SC Node
- Internet (Wired connection preferred for full automation)
- Sovereign Circle Node Installation ISO (PXE server or USB 3+ Drive)
- Keyboard and Monitor if UEFI needs configured
- UEFI Configured to Boot from the medium of choice

***Once installation is complete, the system reboots automatically and runs the firstboot.sh script (only on the first boot).
The firstboot.sh script hardens the system via ufw configuration, updates/upgrades the system, and configures SSH access.
SSH is configured to allow passwords, meaning one can login with satoshi:satoshi. INSECURE!!!
Further installation and configuration will be handled remotely (e.g. Ansibel) where this short-lived security hole is removed.
Note: don't forget to review the logs: `/var/log/*.log`***

## Server-Side Nodes: BTC Feeder & AZC Seeder

The two install scripts, `bitcoin-feeder-install.sh` and `azcoin-seeder-install.sh` are **not** for regular SC Nodes.
They are used on dedicated powerful servers to support the large number of SC Nodes.

### Bitcoin Feeder Nodes

SC (Bitcoin) Nodes are intentionally configured to stay lightweight and conserve bandwidth.
As a result, they tend to "take" more from the network than they give back.

**Bitcoin Feeder Nodes** help balance the ecosystem by acting as high-capacity **givers**.
They provide valuable service to the broader Bitcoin network.

#### Key Characteristics
- Full archival node (`prune=0`) — keeps the complete blockchain history
- Listening node — accepts inbound connections from other nodes
- Blocks-only mode — optimized for better performance and lower resource usage
- Recommended ratio: **1 well-provisioned feeder per ~1000 SC Nodes**

#### Hardware Requirements
- Fast CPU
- Fast NVMe SSD (≥2 TB strongly recommended)
- **64 GB+ RAM**
- Strong upload bandwidth (this is usually the primary bottleneck)

#### SC Node Deployment
When new SC Nodes need to complete their Initial Block Download (IBD), it is best to keep that heavy traffic local.
We recommend running at least one Feeder Node on the **same local network** where SC Nodes are being provisioned.

#### Network Connectivity
Feeder Nodes do not connect directly to SC Nodes, and no VPN or special tunnel is required.
Therefore, the `externalip=` and port settings are determined entirely by the Feeder Node’s own local internet connection and router configuration.
In other words, Feeders connect straight to the public internet — whether in a data center or on a stable business-grade home connection.

#### Configuration & Networking Notes
- **Configuration file**: `/etc/bitcoin/bitcoin.conf`
- **dbcache**: Controls UTXO cache size. Default configuration:  **Total RAM - 8 GB** (minimum 4 GB). Higher values improve validation speed.
- **Port**: Default is `8333`. When running multiple feeders on the same network, assign a unique port to each and update your router/firewall port-forwarding rules accordingly.
- **maxconnections**: Default is `125`. For the recommended 1:1000 ratio this value needs to be increased.
  **Warning**: Higher values increase RAM, CPU, open file limits, and bandwidth usage. Increase gradually and monitor system resources.

After editing `bitcoin.conf`, restart the service with:```bash sudo systemctl restart bitcoind```

#### External IP Updater
This script is **enabled by default** and runs 4 times per day.
It automatically checks the current public (external) IP address.
If it differs from the `externalip=` setting in `bitcoin.conf`, the script updates the file and restarts Bitcoin Core.

This is especially useful on NAT'd connections and dynamic IPs.
**Script location:** `/usr/local/bin/btc-externalip-updater.sh`
Manual run: `btc-externalip-updater.sh`
Enable/disable cron: `btc-externalip-updater.sh --enable` or `--disable`

**Important Networking Note (Multi-WAN / Load Balancing)**
If your router uses multiple internet connections with load balancing, this can cause problems for a listening Bitcoin node (inconsistent external IP or broken inbound connections).
For best results, configure the router so that **inbound and outbound traffic for the Bitcoin node uses a single consistent path** (e.g., pin the feeder’s traffic to one WAN interface).

### AZCoin Seeder Nodes
- Acts as bootstrap/seeder node for the AZCoin network
- They use round-robin DNS and BGP routing protocol
- Address: azcoin-seed.satoshiware.org
- Recommended ratio: **1 feeder per 500 SC Nodes**

**Hardware Requirements (both):**
Fast CPU, fast NVMe SSD, 32 GB+ RAM recommended, and strong network upload bandwidth (biggest bottleneck).