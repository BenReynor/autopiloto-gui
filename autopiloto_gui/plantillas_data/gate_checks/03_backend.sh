#!/usr/bin/env bash
# 03_backend.sh — Levanta el backend y verifica que responde + endpoints.
#
# Configurable vía _env.sh / entorno:
#   SERVE_CMD    comando para arrancar el backend ("" = se omite el check)
#   SERVE_URL    URL base a la que llamar (ej: http://localhost:8000)
#   TOKEN_URL    endpoint de login para obtener token ("" = sin auth)
#   USUARIO/CLAVE credenciales de login
#   ENDPOINTS    lista "ep1 ep2 ..." (se unen como $SERVE_URL/api/$ep)
#
# Si existe endpoints.txt en la raíz, tiene prioridad sobre ENDPOINTS.
set -uo pipefail

# endpoints.txt de la raíz manda
EPS=()
if [ -f "$PROYECTO/endpoints.txt" ]; then
    while IFS= read -r e; do [ -n "$e" ] && EPS+=("$e"); done < "$PROYECTO/endpoints.txt"
else
    # ENDPOINTS viene de _env.sh separado por espacios
    for e in $ENDPOINTS; do EPS+=("$e"); done
fi

if [ -z "$SERVE_CMD" ]; then
    echo "[GATE] ⚠ SERVE_CMD no configurado, se omite el check de backend"
    exit 0
fi

# Liberar el puerto de SERVE_URL si está ocupado por otro proceso del gate
PUERTO="$(echo "$SERVE_URL" | sed -E 's|.*:([0-9]+).*|\1|')"
if [ "$PUERTO" = "$SERVE_URL" ]; then PUERTO=""; fi
if [ -n "$PUERTO" ] && command -v lsof >/dev/null 2>&1; then
    if lsof -ti :"$PUERTO" >/dev/null 2>&1; then
        echo "[GATE] ⚠ puerto $PUERTO ocupado, liberando"
        lsof -ti :"$PUERTO" | xargs kill -9 2>/dev/null
        sleep 1
    fi
fi

eval "$SERVE_CMD" >/dev/null 2>&1 &
BPID=$!
trap 'kill $BPID 2>/dev/null; wait $BPID 2>/dev/null' EXIT

# Esperar a que responda (hasta 15 s). `seq` no existe en BSD/macOS.
BASE_URL="${SERVE_URL:-http://localhost:8000}"
_espera=0
while [ "$_espera" -lt 15 ]; do
    curl -s "$BASE_URL/" >/dev/null 2>&1 && break
    _espera=$((_espera + 1))
    sleep 1
done
if ! curl -s "$BASE_URL/" >/dev/null 2>&1; then
    echo "[GATE] ✗ backend no responde en $BASE_URL"
    exit 1
fi
ok "backend responde en $BASE_URL"

# Token (si hay TOKEN_URL configurado)
TOKEN=""
CONTENT_TYPE="application/json"
if [ -n "$TOKEN_URL" ]; then
    BODY="{}"
    if [ -n "$USUARIO" ]; then
        BODY="{\"username\":\"$USUARIO\",\"password\":\"$CLAVE\"}"
    fi
    TOKEN="$(curl -s -X POST "$TOKEN_URL" -H "Content-Type: $CONTENT_TYPE" -d "$BODY" \
        | ( "$PY_BACKEND" -c "import sys,json
try:
    d=json.load(sys.stdin)
    print(d.get('access') or d.get('token') or d.get('token_type',''))
except Exception:
    print('')" 2>/dev/null ) )"
    if [ -z "$TOKEN" ]; then
        echo "[GATE] ✗ no se obtuvo token en $TOKEN_URL"
        exit 1
    fi
    ok "token JWT en $TOKEN_URL"
fi

# Probar endpoints
if [ ${#EPS[@]} -eq 0 ]; then
    echo "[GATE] ⚠ sin endpoints configurados; solo comprobación de arranque"
    exit 0
fi
ERR=0
for ep in "${EPS[@]}"; do
    # Soporta URLs absolutas o relativas (se antepone /api/)
    case "$ep" in
        http*) url="$ep" ;;
        *) url="$BASE_URL/api/$ep" ;;
    esac
    if [ -n "$TOKEN" ]; then
        curl -s -H "Authorization: Bearer $TOKEN" "$url" >/dev/null 2>&1 && ok "$url" \
            || { echo "[GATE] ✗ $url"; ERR=1; }
    else
        curl -s "$url" >/dev/null 2>&1 && ok "$url" \
            || { echo "[GATE] ✗ $url"; ERR=1; }
    fi
done
[ "$ERR" -eq 1 ] && exit 1
exit 0