#!/usr/bin/env bash
# Start Skopos on the mock provider. No API keys required.
set -euo pipefail
export SKOPOS_PROVIDER="${SKOPOS_PROVIDER:-mock}"
exec python -m uvicorn app:app --host 127.0.0.1 --port 8077 "$@"
