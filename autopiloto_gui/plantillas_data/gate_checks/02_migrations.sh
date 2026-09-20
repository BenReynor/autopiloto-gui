#!/usr/bin/env bash
# 02_migrations.sh — Migraciones al día (comando configurable)
# Sobreescribe con MIGRATE_CHECK env. Ej (Django):
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