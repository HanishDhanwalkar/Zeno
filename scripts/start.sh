#!/usr/bin/env bash
# Thin wrapper around the cross-platform Node launcher.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec node "$DIR/scripts/start.js" "$@"
