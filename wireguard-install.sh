#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# WireGuard SC Node Setup Script
#
# Installs and configures WireGuard as a client.
#   WireGuard connects outbound (w/ encrypted tunnel) to the server and
#   exposes desired ports.
#
# IMPORTANT: WireGuard client (wg-quick@wg-client) runs as ROOT
#   wg-quick requires CAP_NET_ADMIN to create/modify network interfaces,
#     add routes, and manage firewall rules (via PostUp/PostDown if used).
#   Standard wg-quick@.service from wireguard-tools package runs as root.
#   This is the default, recommended, and most reliable approach on Debian.
#   Keys and config are owned root:root with strict permissions for security.
# =============================================================================

LOG_FILE="/var/log/wireguard-install.log"
log() {
    echo "$*" | tee -a "$LOG_FILE"
}

README_DIR="/usr/local/share/doc"
README_FILE="${README_DIR}/wireguard.txt"

log "Starting WireGuard Install: $(date)"

# ===================== CHECKS =====================
if [[ $EUID -ne 0 ]]; then
    log "Error: Must run as root (sudo)."
    exit 1
fi

# Install WireGuard if missing (assumes system is pre-updated)
if ! command -v wg >/dev/null 2>&1; then
    log "Installing wireguard-tools..."
    apt install -y wireguard
else
    log "WireGuard already installed."
fi

# ===================== CONFIG & KEYS =====================
mkdir -p "/etc/wireguard"
chown root:root "/etc/wireguard"
chmod 700 "/etc/wireguard"

if [[ ! -f "/etc/wireguard/wg-client.private" ]]; then
    log "Generating WireGuard keys..."
    umask 077
    wg genkey | tee "/etc/wireguard/wg-client.private" | wg pubkey > "/etc/wireguard/wg-client.public"
    umask 022
    chown root:root "/etc/wireguard/wg-client.private" "/etc/wireguard/wg-client.public"
    chmod 600 "/etc/wireguard/wg-client.private"      # belt-and-suspenders
    chmod 644 "/etc/wireguard/wg-client.public"       # belt-and-suspenders
    log "Keys generated:"
    log "  Private: /etc/wireguard/wg-client.private (600 root:root)"
    log "  Public:  /etc/wireguard/wg-client.public (644 root:root) — share with server"
else
    log "Keys already exist — skipping generation."
fi

# Create placeholder config if missing (NO PrivateKey line — loaded dynamically)
if [[ ! -f "/etc/wireguard/wg-client.conf" ]]; then
    log "Creating placeholder client config: /etc/wireguard/wg-client.conf"
    cat > "/etc/wireguard/wg-client.conf" << EOF
[Interface]
# Unique WireGuard tunnel IP (MUST be unique across all clients)
# UPDATE ADDRESS
Address = <TUNNEL_IP_HERE>/32

# Load the private key dynamically when the tunnel starts
# (Better security: private key is never stored in plain text inside the .conf file)
PostUp = wg set %i private-key /etc/wireguard/wg-client.private

[Peer]
# Server's WireGuard public key
# UPDATE PUBLICKEY
PublicKey = <SERVER_PUBLIC_KEY_HERE>

# Server's domain name + WireGuard port (default = 51820)
# UPDATE ENDPOINT
Endpoint = <SERVER_DOMAIN_HERE>:51820

# Route traffic for the server through this WireGuard tunnel IP
AllowedIPs = 10.66.66.1/32

# Send keepalive packets (helps when behind NAT or firewall)
PersistentKeepalive = 25

# Symmetric secret (PSK) shared between client & server for extra security
# UPDATE PRESHAREDKEY
PresharedKey = <PSK_HERE>
EOF
    chown root:root "/etc/wireguard/wg-client.conf"
    chmod 600 "/etc/wireguard/wg-client.conf"
    log "Config created (private key loaded dynamically)."
fi

# ===================== SYSTEMD SERVICE =====================
log "Installing hardening override for wg-quick@wg-client.service..."
mkdir -p /etc/systemd/system/wg-quick@wg-client.service.d
cat > /etc/systemd/system/wg-quick@wg-client.service.d/override.conf << EOF
[Service]
ProtectSystem=strict
PrivateTmp=yes
NoNewPrivileges=yes
RestrictNamespaces=yes
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_BIND_SERVICE
EOF

systemctl daemon-reload
systemctl enable wg-quick@wg-client.service
log "Systemd service enabled: wg-quick@wg-client.service (auto-starts on boot, runs as root)"

# ===================== README =====================
mkdir -p "${README_DIR}"

cat > "${README_FILE}" << EOF
# WireGuard Client Setup Readme

## Key Files
- /etc/wireguard/ (700 root:root)
  Main WireGuard configuration directory

- /etc/wireguard/wg-client.conf (600 root:root)
  Client configuration file

- /etc/wireguard/wg-client.private (600 root:root)
  WireGuard private key

- /etc/wireguard/wg-client.public (644 root:root)
  WireGuard public key

- /etc/systemd/system/wg-quick@wg-client.service.d/override.conf (644 root:root)
  Hardening override for the WireGuard client systemd service

## Management Commands
- Start tunnel:     sudo wg-quick up wg-client    or    sudo systemctl start wg-quick@wg-client
- Stop tunnel:      sudo wg-quick down wg-client  or    sudo systemctl stop wg-quick@wg-client
- Status:           sudo wg show wg-client
                    sudo systemctl status wg-quick@wg-client
- Logs:             journalctl -u wg-quick@wg-client -f   (live follow)
                    journalctl -u wg-quick@wg-client      (full history)
- Restart:          sudo systemctl restart wg-quick@wg-client (after config edits)

## wg Command Examples
- wg --help                             # General wg tool help
- wg show --help                        # Help for show command
- wg show wg-client                     # Show interface status, peers, handshake, transfer stats
- wg show wg-client latest-handshakes   # Show last handshake times (useful for debugging)

## Notes
- The service runs as root (required for interface/route management).
- After setup, edit /etc/wireguard/wg-client.conf, provide server details, and select a unique tunnel IP for this client.
- On the server side: Add this client's public key (/etc/wireguard/wg-client.public) and the unique tunnel IP for this client to its [Peer] section.
- Install log: ${LOG_FILE}
- WireGuard logs are in journalctl (no separate file by default). For kernel debug:
  echo 'module wireguard +p' | sudo tee /sys/kernel/debug/dynamic_debug/control
  Then view with journalctl -k or dmesg | grep wireguard
EOF

log "Setup complete!"
log "wg-client-install setup log file: ${LOG_FILE}"
log "Readme file: ${README_FILE}"