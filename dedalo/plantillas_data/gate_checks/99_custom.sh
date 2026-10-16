#!/usr/bin/env bash
# 99_custom.sh — User's custom checks.
# Returns 0=OK, 1=FAIL. Put your own verifications here:
# lint, typecheck, security, build, quality gates, etc.
#
# Some ready-to-uncomment/adapt examples:
set -uo pipefail

# ── Lint: ruff (Python) ──
if command -v ruff >/dev/null 2>&1 && [ -z "${SKIP_RUFF:-}" ]; then
    if ( cd "$BACKEND_DIR" && ruff check . >/dev/null 2>&1 ); then
        ok "ruff OK"
    else
        echo "[GATE] ✗ ruff encontró problemas (SKIP_RUFF=1 para omitir)"
        exit 1
    fi
else
    echo "[GATE] ⚠ ruff no instalado o SKIP_RUFF=1, se omite"
fi

# ── Typecheck: mypy (Python) ──
# if [ -n "$PY_BACKEND" ] && "$PY_BACKEND" -c 'import mypy' >/dev/null 2>&1; then
#     if ( cd "$BACKEND_DIR" && "$PY_BACKEND" -m mypy . >/dev/null 2>&1 ); then
#         ok "mypy OK"
#     else
#         echo "[GATE] ✗ mypy encontró errores de tipos"
#         exit 1
#     fi
# fi

# ── Build frontend (Node) ──
# if [ -n "$FRONTEND_DIR" ] && [ -f "$FRONTEND_DIR/package.json" ] && command -v npm >/dev/null 2>&1; then
#     if ( cd "$FRONTEND_DIR" && npm run build >/dev/null 2>&1 ); then
#         ok "build frontend OK"
#     else
#         echo "[GATE] ✗ el build del frontend falló"
#         exit 1
#     fi
# fi

# ── Security: bandit (Python) ──
# if command -v bandit >/dev/null 2>&1; then
#     if ( cd "$BACKEND_DIR" && bandit -r . -q >/dev/null 2>&1 ); then
#         ok "bandit OK"
#     else
#         echo "[GATE] ✗ bandit encontró vulnerabilidades"
#         exit 1
#     fi
# fi

# ── Any custom command ──
# If you need something specific, put it here. Example:
# if ! [ -f "$PROYECTO/.env.ok" ]; then
#     echo "[GATE] ✗ falta .env.ok"
#     exit 1
# fi

echo "[GATE] ✓ custom checks (ruff)"