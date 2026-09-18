#!/usr/bin/env bash
# Start sudo mn-gui on this machine with a new lab file, then run
# gui-api-check.sh against it. Used by CI on native Ubuntu runners.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PORT="${PORT:-8765}"
TOKEN="ci-$(od -An -tx1 -N16 /dev/urandom | tr -d ' \n')"
WORK="$(mktemp -d)"
cd "$WORK"

# The log is written by us, not root, on purpose
# shellcheck disable=SC2024
sudo env MININET_GUI_TOKEN="$TOKEN" mn-gui --config lab.yaml \
    --port "$PORT" > gui.log 2>&1 &
PID=$!
cleanup() {
    sudo kill "$PID" 2> /dev/null || true
    sleep 2
    sudo mn -c > /dev/null 2>&1 || true
    echo "--- mn-gui log"
    cat gui.log
}
trap cleanup EXIT

"$HERE/gui-api-check.sh" "http://localhost:$PORT" "$TOKEN"

# The lab file mn-gui created belongs to us, not root
[ "$(stat -c %U lab.yaml)" = "$(id -un)" ]
# The token never appears in the log except in the startup URL
[ "$(grep -c "$TOKEN" gui.log)" -eq 1 ]
echo "mn-gui smoke test passed"
