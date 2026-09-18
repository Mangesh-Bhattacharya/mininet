#!/usr/bin/env bash
# Drive a running mn-gui through its JSON API against a real network:
# security refusals, start, ping all, a command, iperf, stop.
#
# Usage: scripts/ci/gui-api-check.sh BASE_URL TOKEN
#   e.g. scripts/ci/gui-api-check.sh http://localhost:8765 "$TOKEN"

set -euo pipefail

BASE="$1"
TOKEN="$2"

status() {  # print the HTTP status of a request
    curl -s -o /dev/null -w '%{http_code}' "$@"
}

api() {
    curl -fsS -H "Authorization: Bearer $TOKEN" \
         -H 'Content-Type: application/json' "$@"
}

check() {  # check <python expression over r> < json
    python3 -c "import json, sys; r = json.load(sys.stdin); print(r); assert $1, r"
}

echo "Waiting for $BASE"
for _ in $(seq 60); do
    if curl -fsS -o /dev/null "$BASE/"; then break; fi
    sleep 1
done

echo "Security checks"
[ "$(status "$BASE/api/status")" = 401 ]
[ "$(status -H 'Authorization: Bearer wrong-token-000000000' \
      "$BASE/api/status")" = 401 ]
[ "$(status -H "Authorization: Bearer $TOKEN" -H 'Host: evil.example' \
      "$BASE/api/status")" = 421 ]
[ "$(status -X POST -H "Authorization: Bearer $TOKEN" \
      -H 'Content-Type: application/x-www-form-urlencoded' -d 'a=b' \
      "$BASE/api/start")" = 415 ]
curl -fsS -D - -o /dev/null "$BASE/" | grep -qi "content-security-policy: default-src 'none'"

echo "Network lifecycle"
api "$BASE/api/status" | check 'r["root"] and not r["running"] and r["name"]'
api -X POST -d '{}' "$BASE/api/start" | check '"startup" in r'
api "$BASE/api/status" | check 'r["running"] and len(r["hosts"]) >= 2'
api -X POST -d '{}' "$BASE/api/pingall" | check 'r["loss"] == 0'
host=$(api "$BASE/api/status" | python3 -c 'import json, sys; print(json.load(sys.stdin)["hosts"][0])')
api -X POST -d "{\"node\": \"$host\", \"command\": \"ip -brief address\"}" \
    "$BASE/api/exec" | check 'r["exitCode"] == 0 and "eth0" in r["output"]'
api -X POST -d '{"src": "h1", "dst": "h2"}' "$BASE/api/iperf" | check '"bits" in r["server"]'
api -X POST -d '{}' "$BASE/api/stop" | check 'r["ok"]'
api "$BASE/api/status" | check 'not r["running"]'
echo "mn-gui API check passed"
