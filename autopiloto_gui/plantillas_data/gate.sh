#!/usr/bin/env bash
# gate.sh — Verificación (gate) para el modo autopiloto.
# Comprueba DB, migraciones, backend, endpoints, imports y tests.
# Devuelve 0 si TODO pasa; 1 con el motivo si algo falla.
# No deja procesos corriendo al terminar.
#
# Portátil por diseño: deduce su propia raíz (SCRIPT_DIR) y descubre los
# venv/directorios. Sobreescribibles con variables de entorno:
#   BACKEND_DIR, FRONTEND_DIR, PY_BACKEND, PY_FRONTEND,
#   URL_TOKEN, USUARIO, CLAVE
# Si existe "endpoints.txt" en la raíz, usa esos endpoints en vez de la
# lista por defecto (POS).
set -uo pipefail

PROYECTO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

BACKEND_DIR="${BACKEND_DIR:-}"
[ -z "$BACKEND_DIR" ] && [ -d "$PROYECTO/Backend" ] && BACKEND_DIR="$PROYECTO/Backend"
[ -z "$BACKEND_DIR" ] && BACKEND_DIR="$PROYECTO"

FRONTEND_DIR="${FRONTEND_DIR:-}"
[ -z "$FRONTEND_DIR" ] && [ -d "$PROYECTO/frontend" ] && FRONTEND_DIR="$PROYECTO/frontend"

PY_BACKEND="${PY_BACKEND:-}"
[ -z "$PY_BACKEND" ] && [ -x "$PROYECTO/.venv/bin/python" ] && PY_BACKEND="$PROYECTO/.venv/bin/python"
[ -z "$PY_BACKEND" ] && [ -x "$BACKEND_DIR/venv/bin/python" ] && PY_BACKEND="$BACKEND_DIR/venv/bin/python"
[ -z "$PY_BACKEND" ] && [ -x "$BACKEND_DIR/.venv/bin/python" ] && PY_BACKEND="$BACKEND_DIR/.venv/bin/python"
[ -z "$PY_BACKEND" ] && PY_BACKEND="python3"

if [ -n "$FRONTEND_DIR" ]; then
    PY_FRONTEND="${PY_FRONTEND:-}"
    [ -z "$PY_FRONTEND" ] && [ -x "$FRONTEND_DIR/venv/bin/python" ] && PY_FRONTEND="$FRONTEND_DIR/venv/bin/python"
    [ -z "$PY_FRONTEND" ] && PY_FRONTEND="$PY_BACKEND"
else
    PY_FRONTEND="$PY_BACKEND"
fi

URL_TOKEN="${URL_TOKEN:-http://localhost:8000/api/token/}"
USUARIO="${USUARIO:-admin}"
CLAVE="${CLAVE:-admin123}"

fail() { echo "[GATE] ✗ $1"; exit 1; }
ok()   { echo "[GATE] ✓ $1"; }

# ---- 0. Frontend endpoints (endpoints.txt de la raíz o el default POS) ----
ENDPOINTS=()
if [ -f "$PROYECTO/endpoints.txt" ]; then
    while IFS= read -r e; do [ -n "$e" ] && ENDPOINTS+=("$e"); done < "$PROYECTO/endpoints.txt"
else
    ENDPOINTS=("productos/productos/" "ventas/clientes/" "usuarios/usuarios/" "caja/caja/" "kardex/movimientos/" "compras/compras/" "config/config/")
fi

# ---- 1. PostgreSQL ----
if command -v pg_isready >/dev/null 2>&1; then
    pg_isready -q 2>/dev/null
    if [ $? -ne 0 ]; then
        echo "[GATE] ⚠ pg_isready no confirma conexión"
    else
        ok "PostgreSQL disponible"
    fi
else
    [ -n "${PGOPT:-}" ] && echo "[GATE] ⚠ pg_isready no instalado; lo confirma el backend"
fi

# ---- 2. Migraciones al día ----
cd "$BACKEND_DIR"
"$PY_BACKEND" manage.py migrate --check >/dev/null 2>&1 || fail "migraciones pendientes"
ok "migraciones al día"

# ---- 3. Backend temporal + endpoints ----
if lsof -ti :8000 >/dev/null 2>&1; then
    echo "[GATE] ⚠ puerto 8000 ocupado, liberando"
    lsof -ti :8000 | xargs kill -9 2>/dev/null
    sleep 1
fi

"$PY_BACKEND" manage.py runserver 8000 --noreload >/dev/null 2>&1 &
BPID=$!

BASE_URL="http://localhost:8000"
for i in $(seq 1 15); do
    curl -s "$BASE_URL/api/productos/productos/" >/dev/null 2>&1 && break
    sleep 1
done
if ! curl -s "$BASE_URL/api/productos/productos/" >/dev/null 2>&1; then
    kill "$BPID" 2>/dev/null
    wait "$BPID" 2>/dev/null
    fail "backend no responde en :8000"
fi
ok "backend responde en :8000"

TOKEN=$(curl -s -X POST "$URL_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"$USUARIO\",\"password\":\"$CLAVE\"}" \
    | "$PY_BACKEND" -c "import sys,json; print(json.load(sys.stdin)['access'])" 2>/dev/null)

ERR=0
if [ -z "$TOKEN" ]; then
    echo "[GATE] ✗ token JWT ($URL_TOKEN)"
    ERR=1
else
    for ep in "${ENDPOINTS[@]}"; do
        if curl -s -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/$ep" >/dev/null 2>&1; then
            ok "/api/$ep"
        else
            echo "[GATE] ✗ /api/$ep"
            ERR=1
        fi
    done
fi

kill "$BPID" 2>/dev/null
wait "$BPID" 2>/dev/null
[ "$ERR" -eq 1 ] && fail "endpoints con errores"

# ---- 4. Imports Frontend ----
if [ -n "$FRONTEND_DIR" ] && [ -d "$FRONTEND_DIR" ]; then
    cd "$FRONTEND_DIR"
    "$PY_FRONTEND" -c "
import sys
sys.path.insert(0, '.')
try:
    from main import POSApplication
except ImportError:
    pass
" >/dev/null 2>&1 || fail "imports frontend"
    ok "imports frontend"
else
    echo "[GATE] ⚠ sin directorio frontend, se omite"
fi

# ---- 5. Test suite (el exit code de pytest decide) ----
cd "$BACKEND_DIR"
"$PY_BACKEND" -m pytest -q 2>&1 | tail -6
if [ "${PIPESTATUS[0]}" -ne 0 ]; then
    fail "test suite en ROJO"
fi
ok "test suite en verde"

echo ""
echo "[GATE] ✅ TODO OK"
exit 0