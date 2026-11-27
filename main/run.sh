#!/bin/bash
# Starts Pi Games. Safe to call twice: a second copy simply exits.
#
# Just before it starts, it gets the newest version from GitHub (if this Pi
# was installed with "git clone" and there is internet). No internet, or
# GitHub too slow? Then it starts the version it already has. Scores and
# settings (highscores*.json, config.json) are never touched by an update.
# Switch it off for this Pi with  "auto_update": false  in config.json.
#
# (Everything is inside functions, so bash has read the whole script before
#  an update can replace this file.)

update_from_github() {
    local root branch before after
    root="$(cd .. && pwd)"
    if [ ! -d "$root/.git" ] || ! command -v git >/dev/null 2>&1; then
        return 0                                   # not installed with git: nothing to do
    fi
    if [ -f config.json ] && python3 -c 'import json, sys
sys.exit(0 if json.load(open("config.json")).get("auto_update", True) is False else 1)' 2>/dev/null; then
        echo "Auto-update is off (\"auto_update\": false in config.json)."
        return 0
    fi
    # Right after boot the Wi-Fi is often not up yet: wait for it (max 45 s)
    # instead of giving up straight away and starting the old version.
    local waited=0
    while ! getent hosts github.com >/dev/null 2>&1 && [ "$waited" -lt 45 ]; do
        [ "$waited" -eq 0 ] && echo "Waiting for the network..."
        sleep 1
        waited=$((waited + 1))
    done
    echo "Checking GitHub for a newer version..."
    if ! timeout 15 git -C "$root" fetch -q origin 2>/dev/null; then
        echo "No connection to GitHub - starting the version we have."
        return 0
    fi
    branch="$(git -C "$root" rev-parse --abbrev-ref HEAD 2>/dev/null)"
    before="$(git -C "$root" rev-parse HEAD 2>/dev/null)"
    after="$(git -C "$root" rev-parse "origin/$branch" 2>/dev/null)" || return 0
    if [ -z "$after" ] || [ "$before" = "$after" ]; then
        echo "Already the newest version."
        return 0
    fi
    # The Pi always follows GitHub exactly (changes made to the code on the
    # Pi itself are replaced; scores and settings are not part of git).
    if git -C "$root" reset -q --hard "origin/$branch"; then
        echo "Updated to: $(git -C "$root" log -1 --format='%h %s')"
    else
        echo "Update failed - starting the version we have."
    fi
}

main() {
    cd "$(dirname "$0")" || exit 1
    exec 9>/tmp/pi-games.lock
    if ! flock -n 9; then
        echo "Pi Games is already running."
        exit 0
    fi
    # What the update did is kept in update.log (handy to see if it worked).
    update_from_github 2>&1 | tee update.log
    # Arcade Pis: remember the arcade's own Wi-Fi (made by the host Pi, see
    # host/README.md), so they join it by themselves. The host Pi skips this.
    if [ "$1" != "--host" ] && [ -f join_arcade_wifi.sh ]; then
        bash join_arcade_wifi.sh 2>&1 | tee -a update.log
    fi
    # Output of the last run is kept in game.log (handy to find problems at boot).
    # Right after boot the desktop's screen is sometimes not ready yet, and the
    # game stops at once with a screen error: then wait a bit and try again
    # (max 6 times). Quitting the game normally (Alt+F4) does not restart it.
    : > game.log
    local try start status
    for try in 1 2 3 4 5 6; do
        start=$SECONDS
        python3 main.py "$@" 2>&1 | tee -a game.log
        status=${PIPESTATUS[0]}
        if [ "$status" -eq 0 ] || [ $((SECONDS - start)) -gt 20 ]; then
            break
        fi
        echo "The game stopped right away (screen not ready?) - trying again in 5 s ($try/6)" | tee -a game.log
        sleep 5
    done
}

main "$@"
exit
