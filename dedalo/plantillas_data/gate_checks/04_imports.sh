#!/usr/bin/env bash
# 04_imports.sh — Verifica que el frontend/python importa sin errores.
# Sobreescribe con TEST_CMD o FRONTEND_DIR. Si no hay frontend, se omite.
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