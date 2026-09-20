#!/usr/bin/env bash
# 01_db.sh — Verifica la base de datos (comando configurable)
# Sobreescribe con DB_CHECK_CMD env. Ej: pg_isready -q, mysqladmin ping, ""
set -uo pipefail

if [ -n "$DB_CHECK_CMD" ]; then
    if eval "$DB_CHECK_CMD" >/dev/null 2>&1; then
        ok "Base de datos disponible"
    else
        echo "[GATE] ✗ la base de datos no responde (DB_CHECK_CMD='$DB_CHECK_CMD')"
        exit 1
    fi
else
    echo "[GATE] ⚠ DB_CHECK_CMD no configurado; lo confirma el backend"
fi