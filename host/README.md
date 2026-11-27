# The arcade host Pi 📡

The host is an extra Raspberry Pi that **doesn't play**. Its screen shows **everybody's game
live** while the arcades play against each other. It also makes the arcade's **own Wi-Fi
network**, which the arcade Pis join by themselves, so nobody has to type a Wi-Fi password
on any Pi.

```
            ┌──────────────┐   cable (optional: internet for updates)
            │   HOST Pi    │──────────────────── your router
            │ Wi-Fi: NOVA- │
            │    ARCADE    │
            └──────┬───────┘
        ┌──────────┼──────────┐   the arcades join by themselves
   ┌────┴───┐ ┌────┴───┐ ┌────┴───┐
   │arcade 1│ │arcade 2│ │arcade 3│
   └────────┘ └────────┘ └────────┘
```

## Setting up the host (once)

You need a Raspberry Pi with **Raspberry Pi OS Bookworm or newer** (64-bit), a screen, and a
controller or keyboard.

1. Install the arcade on it the normal way (`git clone`, see the main [README](../README.md)).
2. *(Optional)* change the Wi-Fi name or password in [network.conf](network.conf) **first**.
3. Run:
   ```
   cd ~/picade/host
   bash setup_host.sh
   ```
   This installs what's needed, makes the Wi-Fi network, and starts the host by itself
   at boot.
4. Reboot: `sudo reboot`.

The host now starts on **ARCADE HOST: pick a game to host**.

> **Internet:** the host's Wi-Fi now runs the arcade network, so the host itself is no longer
> on your normal Wi-Fi. **Plug a network cable into the host** if you want internet. The host
> then shares it with the arcades too, so they keep getting updates from GitHub. Without a
> cable everything still works, just without updates.

## The arcade Pis: nothing to do

Every arcade Pi saves the arcade Wi-Fi by itself the next time it starts with internet
(after it gets this version from GitHub). After that:

- **Host switched on?** The arcade joins **NOVA-ARCADE** by itself when it starts.
- **Host off?** The arcade stays on its normal Wi-Fi, so playing alone and PLAY WITHOUT HOST
  still work.

Is the arcade already running when you switch the host on? Restart the arcade so it switches
over. To keep one arcade off the arcade Wi-Fi, put `"arcade_wifi": false` in its
`main/config.json`.

## Playing

1. **Host:** pick a game (B2). The lobby shows who has joined. LEFT / RIGHT picks the mode.
2. **Arcades:** open the same game → **MULTIPLAYER → JOIN A GAME** → pick **ARCADE HOST**.
3. **Host:** **B2 = START GAME**. The host screen shows everyone live.
4. After the round, B1/B2 goes back to the lobby. **B1** in the lobby goes back to the game list.

## Files in this folder

| File | What it does |
|------|--------------|
| `setup_host.sh` | makes this Pi the host (run once) |
| `undo_host.sh` | undoes it: removes the Wi-Fi network and the host autostart |
| `run_host.sh` | starts the host (the autostart runs it) |
| `network.conf` | the Wi-Fi name and password, shared by the host and all arcades |

## If something doesn't work

| Problem | Fix |
|---------|-----|
| The Wi-Fi doesn't appear | Check that `ARCADE_COUNTRY` in network.conf is your country. Then `nmcli connection up nova-arcade-hotspot` and look at the error. |
| An arcade doesn't join | Look at `main/update.log` on that arcade (lines starting with *Arcade Wi-Fi*). Has it had internet once since the update? |
| The arcade doesn't see the host in JOIN A GAME | Is the host in its lobby (not in a game)? Did the arcade pick the same game? |
| The host waits about 45 s at boot | It's looking for internet for updates. Plug in a cable, or put `"auto_update": false` in the host's `main/config.json`. |
