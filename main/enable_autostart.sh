#!/bin/bash
# Makes Pi Games start by itself when the Raspberry Pi boots to the desktop.
# Run once:  bash enable_autostart.sh      (undo with: bash disable_autostart.sh)
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
RUN="$DIR/run.sh"
chmod +x "$RUN"

# 1) Standard autostart entry (works on most Raspberry Pi OS desktops)
mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/pi-games.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Pi Games
Exec=$RUN
Terminal=false
DESKTOP
echo "Added ~/.config/autostart/pi-games.desktop"

# 2) labwc (the newer Wayland desktop). A personal autostart file replaces the
#    system one, so copy the system one first to keep the panel and wallpaper.
if [ -d /etc/xdg/labwc ] || [ -d "$HOME/.config/labwc" ]; then
    mkdir -p "$HOME/.config/labwc"
    LABWC="$HOME/.config/labwc/autostart"
    if [ ! -f "$LABWC" ] && [ -f /etc/xdg/labwc/autostart ]; then
        cp /etc/xdg/labwc/autostart "$LABWC"
    fi
    touch "$LABWC"
    if ! grep -qF "$RUN" "$LABWC"; then
        printf '\n%s &\n' "$RUN" >> "$LABWC"
    fi
    echo "Added to ~/.config/labwc/autostart"
fi

# 3) Wayfire (the older Wayland desktop)
WF="$HOME/.config/wayfire.ini"
if [ -f "$WF" ] && ! grep -qF "$RUN" "$WF"; then
    if grep -q '^\[autostart\]' "$WF"; then
        sed -i "/^\[autostart\]/a pi_games = $RUN" "$WF"
    else
        printf '\n[autostart]\npi_games = %s\n' "$RUN" >> "$WF"
    fi
    echo "Added to ~/.config/wayfire.ini"
fi

echo
echo "Done. Pi Games will now start when the Pi boots to the desktop."
echo "Tip: sudo raspi-config > System Options > Boot / Auto Login > Desktop Autologin"
echo "(so the Pi logs in by itself). It is safe if more than one entry exists:"
echo "the game never starts twice."
