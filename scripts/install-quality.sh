#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
[ -d /Volumes/SYYR/Pubster ] || { echo 'SYYR project must be mounted'; exit 1; }
mkdir -p "$ROOT/.quality/tmp" "$ROOT/.quality/cache" "$ROOT/.quality/reports" "$ROOT/.quality/downloads"
. "$ROOT/scripts/quality-env.sh"
# 3.13 handles disappearing exFAT AppleDouble entries during build cleanup.
PYTHON=${PUBSTER_QUALITY_PYTHON:-/usr/local/bin/python3.13}
[ -x "$ROOT/.quality/venv/bin/python" ] || "$PYTHON" -m venv "$ROOT/.quality/venv"
"$ROOT/.quality/venv/bin/python" -m pip install --prefer-binary -r "$ROOT/services/data-quality/build-requirements.lock"
"$ROOT/.quality/venv/bin/python" "$ROOT/scripts/quality-build-compat.py"
"$ROOT/.quality/venv/bin/python" -m pip install --no-build-isolation --prefer-binary --only-binary=cryptography -r "$ROOT/services/data-quality/requirements.lock"
"$ROOT/.quality/venv/bin/python" "$ROOT/scripts/quality-metadata-compat.py"
"$ROOT/.quality/venv/bin/python" -m pip check
