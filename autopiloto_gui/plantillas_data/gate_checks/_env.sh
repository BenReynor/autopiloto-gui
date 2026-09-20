#!/usr/bin/env bash
# _env.sh — Detección centralizada de entorno. NO se ejecuta solo.
#
# Este script se "sourcea" desde gate.sh, mapear.sh y los checks para que todos
# compartan las mismas variables. Todo es sobreescribible por entorno: si tu
# proyecto no es Python/Django, exporta tus propias rutas/comandos.
#
# Variables que define (y sobreescribe el usuario si quiere):
#   PROYECTO        raíz del proyecto
#   BACKEND_DIR     raíz del backend (aplica migrate/migraciones/tests)
#   FRONTEND_DIR    raíz del frontend (opcional; "" = sin frontend)
#   PY_BACKEND      intérprete Python del backend
#   PY_FRONTEND     intérprete Python del frontend
#   DB_CHECK_CMD    comando de verificación de DB ("" = ninguno)
#   MIGRATE_CHECK   comando de migraciones ("" = ninguna)
#   TEST_CMD        comando de tests ("" = ninguno)
#   SERVE_CMD       comando que levanta el backend para probar endpoints
#   SERVE_URL       URL base para probar endpoints ("" = no se prueban)
#   TOKEN_URL       URL de login para token ("" = sin token)
#   USUARIO/CLAVE   credenciales de login ("" = sin auth)
#   ENDPOINTS       lista de endpoints ("/api/...") separados por espacio

if [ -z "${PROYECTO:-}" ] || [ "$PROYECTO" = "" ]; then
    PROYECTO="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
    [ "$(basename "$PROYECTO")" = "gate_checks" ] && PROYECTO="$(dirname "$PROYECTO")"
    PROYECTO="${PROYECTO:-$(pwd)}"
fi
export PROYECTO

# ---- Backend / Frontend ----
BACKEND_DIR="${BACKEND_DIR:-}"
[ -z "$BACKEND_DIR" ] && [ -d "$PROYECTO/Backend" ] && BACKEND_DIR="$PROYECTO/Backend"
[ -z "$BACKEND_DIR" ] && BACKEND_DIR="$PROYECTO"

FRONTEND_DIR="${FRONTEND_DIR:-}"
[ -z "$FRONTEND_DIR" ] && [ -d "$PROYECTO/frontend" ] && FRONTEND_DIR="$PROYECTO/frontend"

# ---- Python ----
PY_BACKEND="${PY_BACKEND:-}"
[ -z "$PY_BACKEND" ] && [ -x "$PROYECTO/.venv/bin/python" ] && PY_BACKEND="$PROYECTO/.venv/bin/python"
[ -z "$PY_BACKEND" ] && [ -x "$BACKEND_DIR/venv/bin/python" ] && PY_BACKEND="$BACKEND_DIR/venv/bin/python"
[ -z "$PY_BACKEND" ] && [ -x "$BACKEND_DIR/.venv/bin/python" ] && PY_BACKEND="$BACKEND_DIR/.venv/bin/python"
[ -z "$PY_BACKEND" ] && command -v python3 >/dev/null 2>&1 && PY_BACKEND="python3"

PY_FRONTEND="${PY_FRONTEND:-}"
[ -z "$PY_FRONTEND" ] && [ -x "$FRONTEND_DIR/venv/bin/python" ] && PY_FRONTEND="$FRONTEND_DIR/venv/bin/python"
[ -z "$PY_FRONTEND" ] && PY_FRONTEND="${PY_BACKEND:-python3}"

# ---- Comandos opcionales (sobreescribibles) ----
DB_CHECK_CMD="${DB_CHECK_CMD:-}"
MIGRATE_CHECK="${MIGRATE_CHECK:-}"
TEST_CMD="${TEST_CMD:-}"
SERVE_CMD="${SERVE_CMD:-}"
SERVE_URL="${SERVE_URL:-}"
TOKEN_URL="${TOKEN_URL:-}"
USUARIO="${USUARIO:-}"
CLAVE="${CLAVE:-}"
ENDPOINTS="${ENDPOINTS:-}"

# Autodetección de stack (solo si no se configuró nada manualmente)
if [ -n "$PY_BACKEND" ] && [ -f "$BACKEND_DIR/manage.py" ]; then
    # Django
    MIGRATE_CHECK="${MIGRATE_CHECK:-cd \"$BACKEND_DIR\" && \"$PY_BACKEND\" manage.py migrate --check}"
    TEST_CMD="${TEST_CMD:-cd \"$BACKEND_DIR\" && \"$PY_BACKEND\" -m pytest -q}"
    DB_CHECK_CMD="${DB_CHECK_CMD:-command -v pg_isready >/dev/null 2>&1 && pg_isready -q}"
    if [ -z "$SERVE_CMD" ] && [ -z "$ENDPOINTS" ]; then
        SERVE_CMD="cd \"$BACKEND_DIR\" && \"$PY_BACKEND\" manage.py runserver 8000 --noreload"
        SERVE_URL="${SERVE_URL:-http://localhost:8000}"
        TOKEN_URL="${TOKEN_URL:-http://localhost:8000/api/token/}"
        USUARIO="${USUARIO:-admin}"
        CLAVE="${CLAVE:-admin123}"
        ENDPOINTS="${ENDPOINTS:-productos/productos/ ventas/clientes/ usuarios/usuarios/ caja/caja/ kardex/movimientos/ compras/compras/ config/config/}"
    fi
elif [ -n "$PY_BACKEND" ]; then
    # Python genérico
    TEST_CMD="${TEST_CMD:-cd \"$BACKEND_DIR\" && \"$PY_BACKEND\" -m pytest -q}"
fi

export BACKEND_DIR FRONTEND_DIR PY_BACKEND PY_FRONTEND
export DB_CHECK_CMD MIGRATE_CHECK TEST_CMD SERVE_CMD SERVE_URL TOKEN_URL
export USUARIO CLAVE ENDPOINTS

# Utilidades compartidas por checks/scripts
fail() { echo "[GATE] ✗ $1"; exit 1; }
ok()   { echo "[GATE] ✓ $1"; }

# Ejecuta una lista separada por espacios / líneas de puntos o comandos.
# Uso: run_cmds "nombre" "lista"
run_cmds() {
    local nombre="$1" lista="$2" cmd rc
    if [ -z "$lista" ]; then
        echo "[GATE] ⚠ $nombre: sin comando configurado, se omite"
        return 0
    fi
    while IFS= read -r cmd; do
        [ -z "$cmd" ] && continue
        # Permite "comando|mensaje_ok" y "(comando) || falla"
        if eval "$cmd" >/dev/null 2>&1; then
            ok "OK"
        else
            rc=$?
            # El comando ya imprimió el error si lo hizo; si no, genérico
            echo "[GATE] ✗ $nombre"
            return 1
        fi
    done <<< "$lista"
    return 0
}