#!/bin/bash
# Installs everything Pi Tetris needs on Raspberry Pi OS (64-bit).
set -e
sudo apt update
sudo apt install -y python3-pygame python3-gpiozero python3-lgpio
chmod +x run.sh
echo
echo "Done! Start the game with:  ./run.sh"
