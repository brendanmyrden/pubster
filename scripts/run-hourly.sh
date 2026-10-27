#!/bin/sh
set -eu
# Do not recreate paths on the internal disk if the external drive is absent.
[ -d /Volumes/SYYR/Pubster/.venv ] || exit 0
export PATH="/Users/brendanmyrden/.nvm/versions/node/v26.12.0/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
exec /Volumes/SYYR/Pubster/.venv/bin/python /Volumes/SYYR/Pubster/scripts/supervise.py
