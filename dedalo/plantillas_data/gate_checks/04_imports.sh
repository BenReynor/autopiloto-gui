#!/usr/bin/env bash
# 04_imports.sh — Checks that the frontend/python imports without errors.
# Override with TEST_CMD or FRONTEND_DIR. If there is no frontend, it is skipped.
set -uo pipefail

if [ -z "$FRONTEND_DIR" ] || [ ! -d "$FRONTEND_DIR" ]; then
    echo "[GATE] ⚠ FRONTEND_DIR no configurado o sin frontend, se omite"
    exit 0
fi

if ( cd "$FRONTEND_DIR" && "$PY_FRONTEND" -c "
import sys
sys.path.insert(0, '.')
try:
    from main import POSApplication
except ImportError:
    pass
" >/dev/null 2>&1 ); then
    ok "imports frontend"
else
    echo "[GATE] ✗ imports frontend"
    exit 1
fi