#!/bin/bash
# Makes this arcade Pi join the arcade's own Wi-Fi (made by the host Pi) by
# itself. run.sh calls this every time the arcade starts, so you never have to
# do anything: no typing Wi-Fi passwords on the Pi.
#
# - Saves the network from ../host/network.conf (again only if it changed).
# - Is the arcade Wi-Fi around and are we not on it yet? Then it switches to it.
# - Not around (no host Pi switched on)? Then the Pi stays on its normal network.
# Switch it off for this Pi with  "arcade_wifi": false  in config.json.
# Needs NetworkManager (Raspberry Pi OS Bookworm or newer).

cd "$(dirname "$0")" || exit 0
CONF="../host/network.conf"
CON="nova-arcade"                       # the name of the saved network on this Pi
[ -f "$CONF" ] || exit 0

if [ -f config.json ] && python3 -c 'import json, sys
sys.exit(0 if json.load(open("config.json")).get("arcade_wifi", True) is False else 1)' 2>/dev/null; then
    echo "Arcade Wi-Fi: off (\"arcade_wifi\": false in config.json)."
    exit 0
fi
if ! command -v nmcli >/dev/null 2>&1; then
    echo "Arcade Wi-Fi: NetworkManager not found - skipped."
    exit 0
fi

# shellcheck source=../host/network.conf
. "$CONF"
if [ -z "$ARCADE_SSID" ] || [ ${#ARCADE_PASSWORD} -lt 8 ]; then
    echo "Arcade Wi-Fi: network.conf needs ARCADE_SSID and a password of 8+ characters."
    exit 0
fi

# changing network settings: allowed for the desktop user, or else via sudo
NM="nmcli"
if ! nmcli general permissions 2>/dev/null | grep -q "settings.modify.system.*yes"; then
    if sudo -n true 2>/dev/null; then NM="sudo -n nmcli"; else
        echo "Arcade Wi-Fi: no permission to change network settings - skipped."
        exit 0
    fi
fi

# 1) save the network (only when it's new or network.conf changed)
STAMP="$HOME/.cache/nova-arcade-wifi"
WANT="$(cat "$CONF" | sha1sum | cut -d' ' -f1)"
if [ "$(cat "$STAMP" 2>/dev/null)" != "$WANT" ] \
        || ! nmcli -t -f NAME connection show 2>/dev/null | grep -qx "$CON"; then
    $NM connection delete "$CON" >/dev/null 2>&1
    if $NM connection add type wifi con-name "$CON" ssid "$ARCADE_SSID" \
            wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$ARCADE_PASSWORD" \
            connection.autoconnect yes connection.autoconnect-priority 50 >/dev/null; then
        mkdir -p "$(dirname "$STAMP")"
        echo "$WANT" > "$STAMP"
        echo "Arcade Wi-Fi: saved network $ARCADE_SSID."
    else
        echo "Arcade Wi-Fi: could not save the network."
        exit 0
    fi
fi

# 2) the arcade Wi-Fi is here and we're not on it: switch to it
if nmcli -t -f NAME connection show --active 2>/dev/null | grep -qx "$CON"; then
    echo "Arcade Wi-Fi: connected to $ARCADE_SSID."
    exit 0
fi
if timeout 15 nmcli -t -f SSID device wifi list --rescan yes 2>/dev/null | grep -qxF "$ARCADE_SSID"; then
    echo "Arcade Wi-Fi: $ARCADE_SSID found - joining..."
    if timeout 30 $NM connection up "$CON" >/dev/null 2>&1; then
        echo "Arcade Wi-Fi: connected to $ARCADE_SSID."
    else
        echo "Arcade Wi-Fi: could not join $ARCADE_SSID (wrong password in network.conf?)."
    fi
else
    echo "Arcade Wi-Fi: $ARCADE_SSID not around (host Pi off?) - staying on this network."
fi
exit 0
