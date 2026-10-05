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

# `ok` la define gate.sh al cargarnos con `source`. Si este check se ejecuta
# suelto (a mano, o desde otro script) no la tiene y `ok` sería "orden no
# encontrada" (rc=127); como aquí no hay `set -e`, el check seguiría y
# terminaría con exit 0, es decir, verde sin haber comprobado nada.
if ! command -v ok >/dev/null 2>&1; then
    ok() { echo "[GATE] ✓ $1"; }
fi

# endpoints.txt de la raíz manda
EPS=()
if [ -f "${PROYECTO:-}/endpoints.txt" ]; then
    while IFS= read -r e; do [ -n "$e" ] && EPS+=("$e"); done < "$PROYECTO/endpoints.txt"
else
    # ENDPOINTS viene de _env.sh separado por espacios
    for e in ${ENDPOINTS:-}; do EPS+=("$e"); done
fi

if [ -z "${SERVE_CMD:-}" ]; then
    echo "[GATE] ⚠ SERVE_CMD no configurado, se omite el check de backend"
    exit 0
fi

# --- HTTP con diagnóstico -------------------------------------------------
# `curl -s` devuelve 0 aunque la respuesta sea 404 o 500, así que sin mirar el
# código el check daba verde con el backend roto. Tampoco sirve poner -f a
# pelo: aborta con "HTTP 404" y tira el cuerpo, que es justo donde FastAPI y
# Django explican el motivo real ("detail": "no encontrado").
#
# _http <args de curl...> deja en HTTP_CODE el código y en HTTP_BODY el cuerpo.
# Un 000 significa que no hubo respuesta HTTP (conexión rechazada, timeout...).
HTTP_CODE="000"
HTTP_BODY=""
_http() {
    local salida
    salida="$(curl -s -w $'\n%{http_code}' "$@" 2>/dev/null)"
    HTTP_CODE="${salida##*$'\n'}"
    HTTP_BODY="${salida%$'\n'*}"
    [ -n "$HTTP_CODE" ] || HTTP_CODE="000"
}

# Cuerpo en una línea y recortado, para que el diagnóstico quepa en el log.
_resumen() {
    printf '%s' "${1:-}" | tr '\n' ' ' | cut -c1-200
}

# ¿Respondió el backend? Vale cualquier respuesta HTTP (200, 401, 404...):
# un 404 en la raíz es un servidor sano que sólo no tiene ruta "/", que es lo
# más normal en FastAPI/Express. Lo que indica que no arrancó es un 000.
_responde() {
    _http "$1"
    [ "$HTTP_CODE" != "000" ]
}

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
    _responde "$BASE_URL/" && break
    _espera=$((_espera + 1))
    sleep 1
done
if ! _responde "$BASE_URL/"; then
    echo "[GATE] ✗ backend no responde en $BASE_URL"
    exit 1
fi
ok "backend responde en $BASE_URL"

# Token (si hay TOKEN_URL configurado)
TOKEN=""
CONTENT_TYPE="application/json"
if [ -n "${TOKEN_URL:-}" ]; then
    BODY="{}"
    if [ -n "${USUARIO:-}" ]; then
        BODY="{\"username\":\"$USUARIO\",\"password\":\"${CLAVE:-}\"}"
    fi
    _http -X POST "$TOKEN_URL" -H "Content-Type: $CONTENT_TYPE" -d "$BODY"
    TOKEN="$(printf '%s' "$HTTP_BODY" | ( ${PY_BACKEND:-python3} -c "import sys,json
try:
    d=json.load(sys.stdin)
    print(d.get('access') or d.get('token') or d.get('token_type',''))
except Exception:
    print('')" 2>/dev/null ) )"
    if [ -z "$TOKEN" ]; then
        # Un 401 aquí significa normalmente credenciales malas: el cuerpo lo dice.
        echo "[GATE] ✗ no se obtuvo token en $TOKEN_URL (HTTP $HTTP_CODE)"
        [ -n "$HTTP_BODY" ] && echo "[GATE]   respuesta: $(_resumen "$HTTP_BODY")"
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
        _http -H "Authorization: Bearer $TOKEN" "$url"
    else
        _http "$url"
    fi
    # Sólo 2xx es un endpoint sano. 3xx suele ser una ruta mal escrita (falta la
    # barra final) y 4xx/5xx es un endpoint roto: en ambos casos, rojo.
    if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
        ok "$url"
    else
        echo "[GATE] ✗ $url (HTTP $HTTP_CODE)"
        [ -n "$HTTP_BODY" ] && echo "[GATE]   respuesta: $(_resumen "$HTTP_BODY")"
        ERR=1
    fi
done
[ "$ERR" -eq 1 ] && exit 1
exit 0