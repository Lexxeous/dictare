#!/usr/bin/env bash
# Start the complete native development app from this checkout.
set -euo pipefail
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${1:-}" == stop ]]; then
    shift
    exec "$ROOT_DIR/scripts/dev.sh" native-stop "$@"
fi
exec "$ROOT_DIR/scripts/dev.sh" native "$@"
