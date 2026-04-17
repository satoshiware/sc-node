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
It's accessible via DNS (e.g. azcoin-seed.example.com), its gossip ability is diabled (discovery=0), and it must use the default port (19333)!
It accepts short-lived inbound connections (enough time to download peer info') with a lightweight protection script that kicks connections older than a few minutes (offending IPs are banned for a time).

### Supporting Seeders
A Supporting Seeder is the workhorse of an organization's AZCoin Seeder Network.
Unlike the Primary Seeder, Supporting Seeders:
- Are not publicly accessible via DNS (they use the gossip protocol only)
- Can run on any port (not just 19333)
- Allow normal, long-lived connections from SC Nodes w/ no inbound protection script
- Can be numerous (more than 1)

Note: These nodes are not traditional seeders. They are designated as "Supporting Seeders" because they are simple nodes manually linked (via addnode=) from the Primary Seeder.

### Seeder Hardware Requirements
- 32 GB+ RAM
- Fast NVMe SSD
- High Internet Bandwidth (Primary Bottleneck)

### Configuration & Networking Notes
- **Configuration file**: `/etc/azcoin/azcoin.conf`
- **dbcache**: Controls UTXO cache size. Default configuration:  **Total RAM - 8 GB** (minimum 4 GB). Higher values improve validation speed.
- **Port**: On Supporting Seeder nodes only, change the listening port if running multiple nodes on the same network (same IP address)
- **maxconnections**: Default (target) value is `384`. May need to decrease if bandwidth becomes overly saturated.
- **externalip**: Gossiped external ip (Supporting Seeders only). Uncomment and change this if behind NAT to your external static ip
- **addnode**: The seeder network is manually interconnected. Each seeder connects outbound to (maximum 8) other Supporting Seeder nodes using addnode= lines.

After editing `azcoin.conf`, restart the service with:```bash sudo systemctl restart azcoind```

Reminder: if behind NAT, the internal and external ports must be the same and properly forwarded. Primary Seeder requires external port 19333!

Tip: When setting up your initial Supporting Seeders, it is highly recommended to addnode= other Supporting Seeder nodes from other organizations.
This greatly improves network resilience right from the start.

Observation: Seeders on the same LAN can use addnode= with private IPs (e.g. 192.168.x.x) to interconnect to each other with no problem. The external IP set in externalip= will still be properly gossiped outward.

Important: Static public IPs are strongly recommended for all seeders. If the public IP changes:
- The externalip= setting must be manually updated in this node's azcoin.conf (then restart azcoind)
- Any addnode= entries pointing to this node on other seeders must also be updated (then restart azcoind)
Note: The Primary Seeder is more tolerant of IP changes as it has no static inbound connection, assuming it uses dynamic DNS.

### Deployment Guideline:
- **Lab / Early phase** (first 10 to 100 SC Nodes): Single Primary Seeder and one Supporting Seeder may share a single NAT'd internet connection w/ a non-static IP (know the downsides)
- **Initial phase** (first 5,000 SC Nodes): Deploy 1 seeder per 1,000 SC Nodes
- **Growth phase** (up to 30,000 SC Nodes): Deploy 1 seeder per 2,500 SC Nodes
- **Mature phase** (above 30,000 SC Nodes): Deploy 1 seeder per 5,000 SC Nodes

**Critical Note on IP Addressing:**
As the network grows beyond the early lab stage, individual static public IPs become increasingly necessary for stable bandwidth and easier management.

### SC \[AZCoin\] Node Deployment
For the fastest Initial Block Download (IBD), run at least one "Supporting Seeder" on the same local network as your SC Nodes.
Make sure it has at least one outbound connection (addnode=) to a reliable node.
Keep the P2P port firewalled unless you intentionally want to accept inbound connections.
Now, just TEMPORARILY point your new SC Nodes to this local node using addnode.

From time to time, avoid using the local node to bootstrap the new SC Nodes to test the Seeder Network.
On initial boot, if you see no peers (azc getpeerinfo), restart the node with: `sudo systemctl restart azcoind`.
If you still see no peers, there are issues. Time to troubleshoot your AZCoin Seeder Network.
Note: If the SC Node is sharing the same extrenal IP as the seeder (Primary or Supporting) on a private network, it will not connect.

## Bitcoin Feeder / AZCoin Seeder Monitoring
To confirm your AZCoin Seeder or Bitcoin Feeder is working as intended (and not using too much bandwidth),
it's recommended to periodically check (via script + cron or monitoring tool) and send alerts to yourself (email, webhook, etc.).
Items of potential interest:
- `systemctl status azcoind`
- `btc/azc getblockchaininfo`
- `btc/azc getpeerinfo`
- `btc/azc getnetworkinfo`
- `btc/azc getnettotals`

- `free -h # RAM usage`
- `df -h /var/lib/(azcoin|bitcoin) # Disk usage`

- View `externalip` in Bitcoin configuration file

Suggested Alert Triggers:
- Service is not running for ? minutes
- Peer count drops to 0 for ? minutes
- Node falls more than ? blocks behind