# AZCoin Mining Pool
This repository contains the installation scripts and tools to deploy and manage an **AZCoin Mining Pool**.
It is a **headless** backend system (no GUI) designed to serve as the core infrastructure for SC Node AZCoin mining operations.
---
## Architecture

### 1. Core Components
| Component           | Deployment           | Role / Responsibility                              | Key Technology                                   |
|---------------------|----------------------|----------------------------------------------------|--------------------------------------------------|
| Pool Backend        | Single Dedicated VM  | Central Brain & Payout Logic                       | AZCoin Core + Template Provider + Payout Engine  |
| Pool Instances      | Multiple VMs         | Stratum V1 & Stratum V2 (SC Nodes) Mining Pool     | SV2 Pool + Translator + Coinbase Updater Script  |
| Connectivity        | Between All Machines | Secure Encrypted Tunnel                            | WireGuard VPN                                    |
---
### 2. Mining Hierarchy & Management
| Layer            | Description                                                                             | Managed By      | Connection Type        |
|------------------|-----------------------------------------------------------------------------------------|-----------------|------------------------|
| Pool Miners      | Individual miners connecting directly to the pool.                                      | Pool Instances  | Stratum V1             |
|                  | Mainly for testing purposes, not intended for continuous use but it can be.             |                 |                        |
| SC Node Miners   | Individual miners connecting to SC Nodes                                                | SC Nodes        | Stratum V1             |
| SC Nodes         | Nodes that run SV1 → SV2 translators for groups of miners                               | SC Node Owner   | Stratum V1/V2 (In/Out) |
| SC Node Backend  | API service the SC Nodes use to change their mining payout address.                     | Cluster Admin   | WireGuard VPN          |
|                  | The API updates its internal database and forwards changes to the Pool's Payout Engine. |                 |                        |
---
## Installation Scripts & Configuration
Major settings for the installation are stored in two `.env` files:
- `azpool-backend.env` — Configuration for the Pool Backend
- `azpool-instance.env` — Configuration for each Pool Instance

These files are loaded automatically by the setup scripts.

**Please review both files carefully before running the installers.**
Verify all download URLs, hashes, and signatures. Adjust ports, credentials, settings, and any other values as desired.
---
### Pool Backend
| Script                        | Purpose                                   | Calls / Installs  |
|-------------------------------|-------------------------------------------|-------------------|
| `azpool-backend-setup.sh`     | Main entry point                          | All Scripts Below |
| `azcoin-install.azpool.sh`    | Installs AZCoin Core                      |        —          |
| `templar-install.sh`          | Installs SV2 Template Provider            |        —          |
| `payouts-install.azpool.sh`   | Installs Payout Engine for AZ Pool        |        —          |
> Also installs/configures WireGuard, UFW firewall, etc.
---
### Pool Instance
| Script                          | Purpose                                 | Calls / Installs  |
|---------------------------------|-----------------------------------------|-------------------|
| `azpool-instance-setup.sh`      | Main entry point                        | All Scripts Below |
| `azpool-install.sh`             | Installs the SV2 Pool                   |        —          |
| `translator-install.azcoin.sh`  | Installs the Pool Level Translator      |        —          |
> Also installs/configures WireGuard, UFW firewall, Coinbase Updater Script, etc.
---
### Configuration Files
Major settings for the installation are stored in two `.env` files:
- `azpool-backend.env` — Configuration for the Pool Backend
- `azpool-instance.env` — Configuration for each Pool Instance

These files are loaded automatically by the setup scripts.
**Please review both files carefully before running the installers.**
Verify all download URLs, hashes, and signatures. Adjust ports, credentials, settings, and any other values as desired.
---
## Data Flow & Security
Communication between Pool/SC-Node Miners, SC Node Translators, The Pool Translator, and Pool Instances uses the standard Stratum V1 (SV1) and Stratum V2 (SV2) protocols.
SV2 connections are encrypted using the Noise Protocol. All other internal communications are covered in the sections below.
---
### Coinbase Updater
A simple bash script `az-coinbase-updater.sh` installed at /usr/local/bin/.
It runs periodically via cron and ensures its Pool Instance always uses a fresh, unspent coinbase payout address.
It performs the following tasks:

- Checks the current coinbase payout address with AZCoin Core - JSON-RPC (via Wireguard) using whitelisted "coinbase" user
- Updates the coinbase in the pool’s config file if a new unspent address is needed
- Occasionally restarts the pool service (30–90 seconds disruption) to apply the new coinbase address
---
### Payout Engine
The Payout Engine is the core component responsible for calculating and distributing rewards to all registered SC Node usernames in the AZCoin pool.
It is custom-built for this AZCoin pool. With regard to "Data Flow & Security", its interactions with other components are as follows:

- Payout Engine ---> Pool Instances - HTTP REST API (via Wireguard) periodically polls and collects all usernames and share data (excluding pool translator) to calculate and update payout distributions
- Payout Engine ---> AZCoin Core - JSON-RPC to create distribution txs and send payouts
- Linux Kernel (inotify) ---> Payout Engine - /var/log/azcoin/wallet_events.log file change notification potentially triggering the payout process
- "SC Node Manager" ---> Payout Engine - HTTP REST API (via Wireguard) to update permitted usernames along with their payout addresses. Query current username-to-address mappings. Retrieve payout history

Repository Location: `sc-node/azpool/az-payouts/`
Binrary Location: [sc-node releases](https://github.com/satoshiware/sc-node/releases)
---
### SV2 Template Provider
The communication between the Pool and the Template Provider (TP) uses the Stratum V2 Template Distribution Protocol (TDP).
The Template Provider acts as the authoritative middleman. It listens for new blocks and significant mempool updates from AZCoin Core via ZMQ (with infrequent JSON-RPC polling to verify its working),
then proactively pushes fresh block templates to the connected SV2 Pool. The pool receives these updates and returns solved blocks via SubmitSolution.
It is custom-built for this AZCoin pool.

- AZCoin Core ---> SV2 Template Provider - ZMQ block and mempool interrupting updates
- SV2 Template Provider ---> AZCoin Core - JSON-RPC polling to verify everything is functioning
- SV2 Template Provider ---> SV2 Pool - TDP push new/updated block templates
- SV2 Pool ---> SV2 Template Provider - TDP submit block solution

Repository Location: `sc-node/azpool/templar/`
Binrary Location: [sc-node releases](https://github.com/satoshiware/sc-node/releases)



#Todo Notes (messy):
## Wireguard Updating -- manual process -- adding/removing pools -- initial configuration -- WORK IN PROGRESS

 Update rpcauth user "coinbase" with list of whitelisted commands<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
 Each pool instance shares the same noise protocol private key. That way, it doesn't matter.
 Each pool instance has its own ip address, domain name round robin and bgp protocol.