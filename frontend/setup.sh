#!/bin/bash
#################
# Executed from firstboot.sh script where stdout is redirected to firstboot's logging (var/log/firstboot.log)
################
set -euo pipefail

echo "Updating and upgrading..."; sleep 2
sudo apt update && sudo apt upgrade -y

echo "setup.sh completed at $(date)" >> /var/log/setup.log
