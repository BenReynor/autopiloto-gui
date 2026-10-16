#!/usr/bin/env bash
# 02_migrations.sh — Migrations up to date (configurable command)
# Override with the MIGRATE_CHECK env var. E.g. (Django):
#   "cd <backend> && python manage.py migrate --check"
set -uo pipefail

if [ -n "$MIGRATE_CHECK" ]; then
    if eval "$MIGRATE_CHECK" >/dev/null 2>&1; then
        ok "migraciones al día"
    else
        echo "[GATE] ✗ migraciones pendientes (MIGRATE_CHECK falló)"
        exit 1
    fi
else
    echo "[GATE] ⚠ MIGRATE_CHECK no configurado, se omite"
fi