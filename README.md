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

## Bitcoin Feeder Nodes

SC \[Bitcoin\] Nodes are intentionally configured to stay lightweight and conserve bandwidth.
As a result, they tend to "take" more from the network than they give back.

**Bitcoin Feeder Nodes** help balance the Bitcoin ecosystem by acting as high-capacity **givers**.
They provide valuable service to the broader Bitcoin network.

### Key Characteristics
- Full archival node (`prune=0`) — keeps the complete blockchain history
- Listening node — accepts inbound connections from other nodes
- Blocks-only mode — optimized for better performance and lower resource usage
- Recommended ratio: **1 well-provisioned feeder per ~1000 SC Nodes**

After installation, refer to the local documentation on the node itself: `/usr/local/share/doc/bitcoin-feeder.txt`;
It contains quick commands, key settings, and instructions for the IP updater.

### Hardware Requirements
- Fast NVMe SSD (≥2 TB strongly recommended)
- **64 GB+ RAM**
- High Internet Bandwidth (Primary Bottleneck)

### SC \[Bitcoin\] Node Deployment
When new SC Nodes need to complete their Initial Block Download (IBD), it is best to keep that heavy traffic local.
We recommend running at least one Feeder Node on the **same local network** where SC Nodes are being provisioned.
Note: In some cases, you may want this Feeder solely for your local SC Nodes (for fast IBD) without exposing it to the public internet.
Keep the P2P port firewalled to prevent upload bandwidth from being used by random external peers.

### Network Connectivity
Feeder Nodes do not connect directly to SC Nodes, and no VPN or special tunnel is required.
Therefore, the `externalip=` and port settings are determined entirely by the Feeder Node’s own local internet connection and router configuration.
In other words, Feeders connect straight to the public internet — whether in a data center or on a stable business-grade home connection.

### Configuration & Networking Notes
- **Bitcoin Feeder Setup Script**: `bitcoin-feeder-install.sh`
- **Configuration file**: `/etc/bitcoin/bitcoin.conf`
- **dbcache**: Controls UTXO cache size. Default configuration:  **Total RAM - 8 GB** (minimum 4 GB). Higher values improve validation speed.
- **Port**: Default is `8333`. When running multiple feeders on the same network, assign a unique port to each and update your router/firewall port-forwarding rules accordingly ensuring internal and external port forwards are the same.
- **maxconnections**: Default is `125`. To support the 1:1000 ratio this needs to be increased (e.g. 300–600).
  **Note**: Even 125 connections can saturate upload bandwidth in some cases. Lower the value if you experience bandwidth issues or slow performance.

After editing `bitcoin.conf`, restart the service with:```bash sudo systemctl restart bitcoind```

### External IP Updater
This script is installed by the `bitcoin-feeder-install.sh` script and **enabled by default** to run 4 times per day via Cron.
It automatically checks the current public (external) IP address.
If it differs from the `externalip=` setting in `bitcoin.conf`, the script updates the file and restarts Bitcoin Core.

This is especially useful on NAT'd connections and dynamic IPs.
**Script location:** `/usr/local/bin/btc-externalip-updater.sh`
Manual run: `btc-externalip-updater.sh`
Enable/disable cron: `btc-externalip-updater.sh --enable` or `--disable`

**Important Networking Note (Multi-WAN / Load Balancing)**
If your router uses multiple internet connections with load balancing, this can cause problems for a listening Bitcoin node (inconsistent external IP or broken inbound connections).
For best results, configure the router so that **inbound and outbound traffic for the Bitcoin node uses a single consistent path** (e.g., pin the feeder’s traffic to one WAN interface).

## AZCoin Seeder Network
An AZCoin Seeder Network helps bootstrap new SC \[AZCoin\] Nodes by providing reliable initial peer discovery.

### Design Overview
Each AZCoin Seeder Network is sponsored and maintained by a single organization.
It uses a simple hierarchical structure with one Primary Seeder acting as the main public entry point and multiple Supporting Seeders acting as the backbone.

Seeders (i.e. AZCoin node w/ specialized configurations) run in blocks-only mode — optimized for better performance and lower resource usage.
At minimum, each network must start with:
- 1 Primary Seeder (the single public entry point)
- At least 1 Supporting Seeder

After installation (using the `azcoin-seeder-install.sh` script), refer to the local documentation on the node itself: `/usr/local/share/doc/azcoin-seeder.txt`;
It contains quick commands, key settings, and instructions.

### Primary Seeder
The Primary Seeder is one single node by itself that serves as the main public "front door" for an organization's AZCoin network.
It's accessible via DNS (e.g. azcoin-seed.example.com), its gossip ability is purposely handicapped (externalip=0.0.0.0), and it must use the default port (19333)!
It accepts short-lived inbound connections (enough time to download peer info') with a lightweight protection script that kicks connections older than a few minutes (offending IPs are banned for a time).

### Supporting Seeders
A Supporting Seeder is the workhorse of an organization's AZCoin Seeder Network.
Unlike the Primary Seeder, Supporting Seeders:
- Are not publicly advertised via DNS (they use the gossip protocol only)
- Can run on any port (not just 19333)
- Allow normal, long-lived connections from SC Nodes w/ no inbound protection script
- Can be numerous (more than 1)

Note: These nodes are not traditional seeders. They are designated as "Supporting Seeders" because they are manually linked (via addnode=) to the Primary Seeder.

### Seeder Hardware Requirements
- 32 GB+ RAM
- Fast NVMe SSD
- High Internet Bandwidth (Primary Bottleneck)

### Configuration & Networking Notes
- **Configuration file**: `/etc/azcoin/azcoin.conf`
- **dbcache**: Controls UTXO cache size. Default configuration:  **Total RAM - 8 GB** (minimum 4 GB). Higher values improve validation speed.
- **Port**: On Supporting Seeder nodes only, change the listening port if running multiple nodes on the same network (same IP address)
- **maxconnections**: Default (target) value is `384`. May need to decrease if bandwidth becomes overly saturated.
- **externalip**: Gossiped external ip (Must be 0.0.0.0 for Primary Seeder). Uncomment and change this if behind NAT to your external static ip
- **addnode**: The seeder network is manually interconnected. Each seeder connects outbound to (maximum 8) other Supporting Seeder nodes using addnode= lines.

After editing `azcoin.conf`, restart the service with:```bash sudo systemctl restart azcoind```

Reminder: if behind NAT, the internal and external ports must be the same and properly forwarded. Primary Seeder requires external port 19333!

Tip: When setting up your initial Supporting Seeders, it is highly recommended to addnode= other Supporting Seeder nodes from other organizations.
This greatly improves network resilience right from the start.

Observation: Seeders on the same LAN can use addnode= with private IPs (e.g. 192.168.x.x) with no problem. The external IP set in externalip= will still be properly gossiped outward.

Important: Static public IPs are strongly recommended for all seeders. If the public IP changes:
- The externalip= setting must be manually updated in this node's azcoin.conf (then restart azcoind)
- Any addnode= entries pointing to this node on other seeders must also be updated (then restart azcoind)
Note: The Primary Seeder is more tolerant of IP changes as it has no static inbound connection, assuming it uses dynamic DNS.

### Deployment Guideline:
    Initial phase (first 5,000 SC Nodes): Deploy 1 seeder per 1,000 SC Nodes
    Growth phase (up to 30,000 SC Nodes): Deploy 1 seeder per 2,500 SC Nodes
    Mature phase (above 30,000 SC Nodes): Deploy 1 seeder per 5,000 SC Nodes
Note: be sure to fan out to the max (8 per node) before going deeper.



### Deployment Guideline:
- **Lab / Early phase** (first 10 to 100 SC Nodes): Single Primary Seeder and one Supporting Seeder may share a single NAT'd internet connection w/ a non-static IP
- **Initial phase** (first 5,000 SC Nodes): Deploy 1 seeder per 1,000 SC Nodes
- **Growth phase** (up to 30,000 SC Nodes): Deploy 1 seeder per 2,500 SC Nodes
- **Mature phase** (above 30,000 SC Nodes): Deploy 1 seeder per 5,000 SC Nodes

**Critical Note on IP Addressing:**
As the network grows beyond the early lab stage, individual static public IPs become increasingly necessary for stable bandwidth and easier management.

### SC \[AZCoin\] Node Deployment
For the fastest Initial Block Download (IBD), run at least one "Supporting Seeder" on the same local network as your SC Nodes.
Make sure it has at least one outbound connection (addnode=) to a reliable node.
Keep the P2P port firewalled unless you intentionally want to accept inbound connections.
Now, just temporarily point your new SC Nodes to this local node using addnode.

From time to time, avoid using the local node to bootstrap the new SC Nodes to test the Seeder Network.
On initial boot, if you see no peers (azc getpeerinfo), restart the node with: `sudo systemctl restart azcoind`.
If you still see no peers, there are issues. Time to troubleshoot your AZCoin Seeder Network.

## Bitcoin Feeder / AZCoin Seeder Monitoring
To confirm your AZCoin Seeder or Bitcoin Feeder is working as intended,
it's recommended to periodically check (via script + cron or monitoring tool) and send alerts to yourself (email, webhook, etc.).
Items of potential interest:
- `systemctl status azcoind`
- `btc/azc getblockchaininfo`
- `btc/azc getpeerinfo`
- `btc/azc getnetworkinfo`
- `btc/azc getnettotals`

- `free -h # RAM usage`
- `df -h /var/lib/(azcoin|bitcoin) # Disk usage`

- View `externalip` in configuration file

Suggested Alert Triggers:
- Service is not running for ? minutes
- Peer count drops to 0 for ? minutes
- Node falls more than ? blocks behind