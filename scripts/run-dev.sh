#!/usr/bin/env bash
# Run the agent locally in dry-run mode. Writes to ./var/sandbox rather
# than real system paths — safe for development on any machine.
set -euo pipefail

cd "$(dirname "$0")/.."

export ECM_DRY_RUN=1
export ECM_ROOT="$(pwd)"
export ECM_DATA_DIR="$(pwd)/var"

exec python -m agent.main
