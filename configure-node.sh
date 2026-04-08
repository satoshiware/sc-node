#!/bin/bash
# =============================================================================
# Generic SC Node Configuration Script
# Supports: no-spaces, spaces, toml
# Usage: ./configure-node.sh [node-config.cfg]
# =============================================================================

set -e

CONFIG_FILE="${1:-node-config.cfg}"

echo "=== Generic SC Node Configuration Script ==="

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Configuration file '$CONFIG_FILE' not found!"
    echo "Please copy node-config-example.cfg to $CONFIG_FILE first."
    exit 1
fi

source "$CONFIG_FILE"

echo "Applying configurations from: $CONFIG_FILE"

for target_var in $(compgen -v | grep '_TARGET_CONFIG$'); do
    TARGET_CONFIG="${!target_var}"
    SECTION="${target_var%_TARGET_CONFIG}"
    FORMAT_VAR="${SECTION}_FORMAT"
    FORMAT_STYLE="${!FORMAT_VAR:-no-spaces}"

    if [ -z "$TARGET_CONFIG" ] || [ ! -f "$TARGET_CONFIG" ]; then
        echo "Skipping ${SECTION}: Target file not found"
        continue
    fi

    echo ""
    echo "→ Configuring ${SECTION} (${FORMAT_STYLE}) → $TARGET_CONFIG"

    BACKUP_FILE="${TARGET_CONFIG}.bak.$(date +%Y%m%d-%H%M%S)"
    cp "$TARGET_CONFIG" "$BACKUP_FILE"
    echo "   Backup created: $BACKUP_FILE"

    # Get all parameters for this section
    params=$(compgen -v | grep "^${SECTION}_" | grep -vE '(_TARGET_CONFIG|_FORMAT)$')

    for param_var in $params; do
        param="${param_var#${SECTION}_}"
        value="${!param_var}"

        if [ -z "$value" ]; then
            # Comment out the line
            if [ "$FORMAT_STYLE" = "no-spaces" ]; then
                sed -i "/^# UPDATE ${param}/,/^[^#]/ s|^${param}=.*|#${param}=|" "$TARGET_CONFIG"
            else
                sed -i "/# UPDATE ${param}/,/^[^#]/ s|^\s*${param}\s*=\s*.*|  # ${param} = \"\"|" "$TARGET_CONFIG"
            fi
            echo "   ${param} → commented out"
        else
            # Apply value according to format style
            if [ "$FORMAT_STYLE" = "no-spaces" ]; then
                sed -i "/^# UPDATE ${param}/,/^[^#]/ s|^#${param}=.*|${param}=${value}|" "$TARGET_CONFIG"
                echo "   ${param} = ${value}"
            elif [ "$FORMAT_STYLE" = "toml" ]; then
                sed -i "/# UPDATE ${param}/,/^[^#]/ s|^\s*${param}\s*=\s*.*|  ${param} = \"${value}\"|" "$TARGET_CONFIG"
                echo "   ${param} = \"${value}\""
            else
                # spaces (WireGuard)
                sed -i "/# UPDATE ${param}/,/^[^#]/ s|^\s*${param}\s*=\s*.*|  ${param} = ${value}|" "$TARGET_CONFIG"
                echo "   ${param} = ${value}"
            fi
        fi
    done

    echo "   Done with ${SECTION}"
done

echo ""
echo "✅ All configurations applied successfully!"
echo ""
echo "Restart services as needed:"
echo "   systemctl restart azcoind bitcoind stratum-azcoin stratum-bitcoin wg-quick@wg-client"
echo ""