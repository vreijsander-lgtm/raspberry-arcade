#!/bin/bash
# Turns this Raspberry Pi into the arcade's HOST. Run once:
#     bash setup_host.sh
# (undo everything with:  bash undo_host.sh)
#
# What it does:
#   1. installs what the arcade needs (pygame, buttons),
#   2. makes the arcade's own Wi-Fi network (name and password in network.conf),
#      which the arcade Pis join by themselves,
#   3. starts the host screen by itself when the Pi boots (instead of the arcade).
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$DIR")"
CON="nova-arcade-hotspot"
# shellcheck source=network.conf
. "$DIR/network.conf"

if [ ${#ARCADE_PASSWORD} -lt 8 ] || [ ${#ARCADE_PASSWORD} -gt 63 ]; then
    echo "The password in network.conf must be 8 to 63 characters."
    exit 1
fi

echo "This makes this Pi the arcade HOST, with its own Wi-Fi: $ARCADE_SSID"
echo
echo "NOTE: the Wi-Fi of this Pi is then used for the arcade network, so this Pi"
echo "itself is no longer on your normal Wi-Fi. Plug in a network CABLE if the host"
echo "(and the arcades) should still have internet for updates from GitHub."
echo "Connected over SSH via Wi-Fi? Then that connection drops at step 2."
echo
read -r -p "Continue? [y/N] " answer
case "$answer" in [yYjJ]*) ;; *) echo "Stopped."; exit 0 ;; esac

echo
echo "== 1/3  Installing what the arcade needs"
sudo apt update
sudo apt install -y python3-pygame python3-gpiozero python3-lgpio
chmod +x "$ROOT"/main/*.sh "$DIR"/*.sh

echo
echo "== 2/3  Making the arcade Wi-Fi: $ARCADE_SSID"
if ! command -v nmcli >/dev/null 2>&1; then
    echo "NetworkManager not found: the Wi-Fi network needs Raspberry Pi OS Bookworm"
    echo "or newer. Skipped - the host still works on your normal network."
else
    sudo raspi-config nonint do_wifi_country "$ARCADE_COUNTRY" 2>/dev/null || true
    sudo rfkill unblock wifi 2>/dev/null || true
    # the host makes the network, it must never join it as a normal arcade
    sudo nmcli connection delete nova-arcade >/dev/null 2>&1 || true
    sudo nmcli connection delete "$CON" >/dev/null 2>&1 || true
    sudo nmcli connection add type wifi ifname wlan0 con-name "$CON" ssid "$ARCADE_SSID" \
        connection.autoconnect yes connection.autoconnect-priority 100 \
        802-11-wireless.mode ap 802-11-wireless.band bg \
        802-11-wireless.channel "$ARCADE_CHANNEL" \
        ipv4.method shared ipv4.addresses 10.42.0.1/24 ipv6.method ignore \
        wifi-sec.key-mgmt wpa-psk wifi-sec.proto rsn \
        wifi-sec.pairwise ccmp wifi-sec.group ccmp \
        wifi-sec.psk "$ARCADE_PASSWORD"
    sudo nmcli connection up "$CON"
    echo "Wi-Fi $ARCADE_SSID is on (this Pi is 10.42.0.1). It comes back by itself after a reboot."
fi

echo
echo "== 3/3  Starting as host when the Pi boots"
bash "$ROOT/main/disable_autostart.sh" >/dev/null 2>&1 || true    # not as an arcade
bash "$ROOT/main/enable_autostart.sh" "$DIR/run_host.sh"

echo
echo "Done! Reboot to start the host:  sudo reboot"
echo "The arcade Pis join $ARCADE_SSID by themselves the next time they start."
