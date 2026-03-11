#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

APP_CMD="$SCRIPT_DIR/.venv/bin/python webapp.py"
LOG_FILE="$LOG_DIR/webapp.log"

echo "[INFO] Checking existing webapp.py processes..."

# Find webapp.py processes while excluding this script's grep process.
PIDS="$(ps -eo pid=,command= | grep -Ei '[p]ython(3)? .*webapp\.py( |$)' | awk '{print $1}' || true)"

if [[ -n "$PIDS" ]]; then
  echo "[INFO] Found old process(es): $PIDS"
  # shellcheck disable=SC2086
  kill $PIDS || true
  sleep 1

  REMAINING="$(ps -eo pid=,command= | grep -Ei '[p]ython(3)? .*webapp\.py( |$)' | awk '{print $1}' || true)"
  if [[ -n "$REMAINING" ]]; then
    echo "[WARN] Force killing remaining process(es): $REMAINING"
    # shellcheck disable=SC2086
    kill -9 $REMAINING || true
  fi
else
  echo "[INFO] No old webapp.py process found."
fi

echo "[INFO] Starting new webapp.py process in background..."

# Run in background and write stdout/stderr to one log file.
nohup $APP_CMD >> "$LOG_FILE" 2>&1 &
NEW_PID=$!

echo "[INFO] Started webapp.py, PID=$NEW_PID"
echo "[INFO] Log file: $LOG_FILE"
