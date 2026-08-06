#!/usr/bin/env bash
# Run the converter straight from a clone.
#
# Prefers the private virtualenv that install.sh creates, so the pinned
# dependencies are used when they exist; falls back to the system python3 for a
# quick one-off in a clone that was never installed.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

PY="$SCRIPT_DIR/.venv/bin/python"
if [ ! -x "$PY" ]; then
  PY="$(command -v python3 || true)"
  if [ -z "$PY" ]; then
    echo "error: python3 not found; install Python 3, then run ./install.sh" >&2
    exit 1
  fi
fi

# main.py owns the CLI: it prints --help, and with no arguments prints its usage
# to stderr and exits non-zero. Keeping the usage text in one place means this
# wrapper can never describe a stale set of flags.
exec "$PY" "$SCRIPT_DIR/main.py" "$@"
