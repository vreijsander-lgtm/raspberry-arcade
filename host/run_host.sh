#!/bin/bash
# Starts this Pi as the arcade's HOST (see README.md next to this file).
# It's the normal arcade start (with the update from GitHub), but in host mode.
exec bash "$(cd "$(dirname "$0")" && pwd)/../main/run.sh" --host
