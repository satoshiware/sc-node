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
* CPU: 4 Cores (Must Support Virtualization, i.e., Hyper-V Capable)
* Networking: Gigabit Ethernet
* Power: Low-Power Consumption (<50W)

## Proxmox VE
Proxmox VE serves as the foundational hypervisor for the SC Node, providing robust virtualization capabilities for running all associated software components efficiently on a single hardware platform. To ensure secure and simplified network exposure, the SC Node is configured with NAT addressing, presenting only a single external IP address to the broader network while handling internal traffic for VMs and containers. By default, the device name is set to "SC Node", but can be easily configured in the SC Node install script.

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

## Build Installation ISO
Download and execute the sc_node/build-scnode-iso.sh script, on linux, in any $USER directory w/ sudo privileges. Once complete, the iso (named "modified.iso") will have been remastered into the execution directory. *Note: This project does **not** involve traditional compilation of source code.  Instead, it **remasters** an official Debian DVD-1 ISO (stable release) with the following changes:*

- sc_node`s preseed file (sc_node/preseed.cfg) is configured for full automated installation
- The entire `sc_node` repository is added to the target filesystem (/root/sc_node)
- GRUB boot menu is configured to offer preseeded auto-install (and debug) options where the auto-install will auto run within 5 seconds

The end result is a bootable ISO that performs a hands-free Debian installation tailored to be a Sovereign Circle Node. As the install is completed on a new SC Node, the system is configured to run the setup script (sc_node/setup.sh), launched by the firstboot.sh script, on first boot. The preseed.cfg and late_commands.sh files govern this configuration. **WARNING! A USB with this ISO will delete the first non-removable disk with maximum LVM partition automatically and without any prompts!!!**

Notable configurations by the preseed.cfg file, **not including the setup.sh script**:

- **UTC** timezone (location-independent)
- **hostname**: sc-node
- **domain**: internal
- **root** login disabled
- **user**: satoshi (w/ sudo rights)
    - **passwd**: satoshi
    - **name**: Satoshi Nakamoto
- **curl** utility installed

### Requirements
- A linux host system w/ **sudo** privileges
- ~16 GB free disk space (original ISO ≈ 4.7 GB + extracted contents + temporary files)
- Good Internet (for downloading ~4.7 GB ISO + tools/repo)
- Required packages (automatically installed if missing): `git`, `curl`, `gnupg`, `rsync`, `xorriso`

## Create USB Install Stick
Dedicated USB with 8GB+ is required.
USB 3.0+ is highly recommended to shorten install times.

1. Download the latest ISO for your CPU from the GitHub release page: https://github.com/satoshiware/sc_node/releases

2. Verify Checksum and Signatures

3. Depending on your OS (Windows, Linux, or even Linux on Windows [WSL]), search for an online guide to correctly write an ISO to a USB drive so that it will boot and install as desired.

*Note: Be sure the target machine has wired internet; otherwise, the setup will prompt for networking configuration during install. It’s recommended the install process has internet access to ensure the most up-to-date Debian install files. Also, the setup.sh script run first boot requires it!*

*******************************************************************************************************

# Satoshiware Dashboard 

Quick scaffold to run a Coinbase-style Satoshiware dashboard UI using Vite, React and Tailwind.

Install and run:

```bash
npm install
npm run dev
```