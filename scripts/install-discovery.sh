#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
. "$ROOT/scripts/quality-env.sh"
mkdir -p "$TMPDIR" "$PIP_CACHE_DIR"
[ -x "$ROOT/.quality/discovery-venv/bin/python" ] || /usr/local/bin/python3.13 -m venv "$ROOT/.quality/discovery-venv"
"$ROOT/.quality/discovery-venv/bin/python" -m pip install --only-binary=:all: -r "$ROOT/services/discovery/requirements.lock"
