#!/bin/bash
# =============================================================================
# One-time first-boot setup wrapper for Sovereign Circle Node
# It launches the setup.sh script fully detached and independent from this wrapper
#
# Execution:
#   - Runs automatically via firstboot-setup.service on first boot only
#   - Note: firstboot-setup.service was created/enabled by preseed.cfg + late_commands.sh
#   - Self-disables and cleans up after successful run to prevent re-execution
#
# Logging: /var/log/firstboot.log
# =============================================================================
set -euo pipefail

FIRSTBOOT_LOG="/var/log/firstboot.log"
SETUP_SCRIPT="/root/sc_node/setup.sh"

echo "firstboot.sh started at $(date)" >> "$FIRSTBOOT_LOG" 2>&1
# =============================================================================
# Wait for internet in case setup.sh needs it (max = 60 seconds)
# =============================================================================
echo "Checking internet connectivity..." >> "$FIRSTBOOT_LOG" 2>&1
for i in {1..15}; do
    if curl -s --connect-timeout 5 http://www.google.com >/dev/null; then
        echo "Internet OK after $i attempts" >> "$FIRSTBOOT_LOG" 2>&1
        break
    fi
    echo "Attempt $i - no connection, retrying in 4s..." >> "$FIRSTBOOT_LOG" 2>&1
    sleep 4
done

if ! curl -s --connect-timeout 5 http://www.google.com >/dev/null; then
    echo "ERROR: No internet after 15 attempts (~60 seconds). Exiting." >> "$FIRSTBOOT_LOG" 2>&1
    exit 1
fi

# =============================================================================
# Launch setup.sh fully detached and independent
# =============================================================================
# Pre-check: script must exist and be executable
if [ ! -f "$SETUP_SCRIPT" ] || [ ! -x "$SETUP_SCRIPT" ]; then
    echo "ERROR: setup.sh not found or not executable at $SETUP_SCRIPT" >> "$FIRSTBOOT_LOG" 2>&1
    exit 1
fi

echo "Launching setup.sh at $(date)" >> "$FIRSTBOOT_LOG" 2>&1

# Launch detached with full output redirection
nohup "$SETUP_SCRIPT" >> "$FIRSTBOOT_LOG" 2>&1 < /dev/null &

# Immediately capture the PID of the background process
SETUP_PID=$!

# Give it a moment to start
sleep 1

# Check if the process is running
if ps -p $SETUP_PID > /dev/null 2>&1; then
    echo "setup.sh launched successfully (PID: $SETUP_PID) at $(date)" >> "$FIRSTBOOT_LOG" 2>&1
else
    echo "ERROR: setup.sh failed to launch (PID $SETUP_PID not found)" >> "$FIRSTBOOT_LOG" 2>&1
    exit 1
fi

# disown to fully detach from shell session
disown $SETUP_PID 2>/dev/null || true

# =============================================================================
# Self-disable and cleanup
# =============================================================================
echo "Disabling and removing firstboot-setup.service" >> "$FIRSTBOOT_LOG" 2>&1
systemctl disable firstboot-setup.service || true
rm -f /etc/systemd/system/firstboot-setup.service || true
systemctl daemon-reload || true
echo "firstboot-setup.service disabled and removed successfully" >> "$FIRSTBOOT_LOG" 2>&1
echo "firstboot.sh script completed at $(date)" >> "$FIRSTBOOT_LOG" 2>&1