#!/bin/bash
# Removes everything enable_autostart.sh added.
DIR="$(cd "$(dirname "$0")" && pwd)"
RUN="$DIR/run.sh"
rm -f "$HOME/.config/autostart/pi-games.desktop"
for f in "$HOME/.config/labwc/autostart" "$HOME/.config/wayfire.ini"; do
    [ -f "$f" ] && sed -i "\|$RUN|d" "$f"
done
echo "Autostart removed. Pi Games will no longer start at boot."
