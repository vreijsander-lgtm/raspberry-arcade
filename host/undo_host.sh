#!/bin/bash
# Undoes setup_host.sh: removes the arcade Wi-Fi from this Pi and stops starting
# as host. (To make it a normal arcade again: bash ../main/enable_autostart.sh)
DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$DIR")"
if command -v nmcli >/dev/null 2>&1; then
    sudo nmcli connection delete nova-arcade-hotspot >/dev/null 2>&1 \
        && echo "Arcade Wi-Fi removed from this Pi."
fi
bash "$ROOT/main/disable_autostart.sh"
echo "This Pi no longer starts as the arcade host."
