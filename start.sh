#!/usr/bin/env bash
# Starts scout on this Mac: the Python service, then the iMessage bridge.
# Keeps the Mac awake while it runs. Ctrl-C stops everything.
#
# Needs .env (ANTHROPIC_API_KEY=...) here and bridge/.env (IMESSAGE_MODE=...).
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  echo "Create .env with ANTHROPIC_API_KEY=sk-ant-..." >&2
  exit 1
fi
set -a
source .env
set +a
: "${ANTHROPIC_API_KEY:?Set ANTHROPIC_API_KEY in .env}"

# Stop the server and caffeinate however this script ends.
trap 'kill $(jobs -p) 2>/dev/null' EXIT

# A sleeping Mac stops receiving texts. caffeinate exits when this script does.
caffeinate -dimsu -w $$ &

uv run scout-server &
server_pid=$!

echo "Waiting for the scout server..."
until curl -sf -o /dev/null http://127.0.0.1:8787/docs; do
  if ! kill -0 "$server_pid" 2>/dev/null; then
    echo "The scout server didn't start. See the errors above." >&2
    exit 1
  fi
  sleep 1
done

cd bridge
bun start
