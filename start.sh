#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_BIN="python3"
if [[ -x "$SCRIPT_DIR/venv/bin/python" ]]; then
    PYTHON_BIN="$SCRIPT_DIR/venv/bin/python"
fi

echo "================================"
echo "Starvell Cardinal"
echo "================================"
echo

exec "$PYTHON_BIN" "$SCRIPT_DIR/main.py"
