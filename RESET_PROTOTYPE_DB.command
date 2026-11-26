#!/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
printf '\n[Local Agent] This will replace the legacy prototype SQLite database with Schema v2.0.\n'
read -r -p 'Type RESET to continue: ' CONFIRM
if [ "$CONFIRM" != "RESET" ]; then
  echo 'Cancelled. No database files were changed.'
  read -r -p 'Press Return to close...' _
  exit 0
fi
if [ -x "$ROOT/.venv/bin/python" ]; then
  "$ROOT/.venv/bin/python" -m backend.db.bootstrap --reset-prototype
else
  python3 -m backend.db.bootstrap --reset-prototype
fi
printf '\nDatabase reset and initialised successfully.\n'
read -r -p 'Press Return to close...' _
