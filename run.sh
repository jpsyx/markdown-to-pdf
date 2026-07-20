#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [ "$#" -lt 1 ]; then
  echo "Usage: markdown-to-pdf <file.md> [--out <output.pdf>]" >&2
  exit 1
fi

exec python3 "$SCRIPT_DIR/main.py" "$@"
