#!/bin/bash
# Starts Pi Games. Safe to call twice: a second copy simply exits.
cd "$(dirname "$0")"
exec 9>/tmp/pi-games.lock
if ! flock -n 9; then
    echo "Pi Games is already running."
    exit 0
fi
# Output of the last run is kept in game.log (handy to find problems at boot).
python3 main.py 2>&1 | tee game.log
