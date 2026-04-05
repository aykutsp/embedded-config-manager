#!/usr/bin/env bash
# Convenience script: create a revision from examples/config.example.json
# and apply it against a freshly started local agent.
set -euo pipefail

BASE="${ECM_BASE:-http://127.0.0.1:8080/api/v1}"
CONFIG_FILE="$(dirname "$0")/../examples/config.example.json"

payload=$(printf '{"author":"dev","note":"seed","config":%s}' "$(cat "$CONFIG_FILE")")

rev_id=$(curl -s -X POST "$BASE/revisions" \
  -H "content-type: application/json" \
  -d "$payload" | python -c "import sys,json;print(json.load(sys.stdin)['revision_id'])")

echo "created revision $rev_id"

curl -s -X POST "$BASE/revisions/$rev_id/apply" | python -m json.tool
