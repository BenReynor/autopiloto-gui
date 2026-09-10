#!/usr/bin/env bash
# mapear.sh — Genera mapeo.txt: mapa del proyecto (módulos -> tests),
# estilo test_map de TDAD. Lo usa autopiloto.sh para que el agente sepa
# qué tests existen y donde tocar antes de escribir código.
#
# Uso:  bash mapear.sh > mapeo.txt
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
[ -z "$PY_BACKEND" ] && PY_BACKEND="python3"

printf '# MApeo del proyecto — %s\n' "$PROYECTO"
printf '# Generado por mapear.sh el %s.\n' "$(date '+%F %H:%M')"
echo '# Regla: al cambiar código, actualiza/corre su test ANTES de dar por terminado.'
echo "# Verificación rápida: cd $BACKEND_DIR && $PY_BACKEND -m pytest <test> -q"
echo ""

echo "## Backend — aplicaciones y sus tests"
for dir in "$BACKEND_DIR"/*/; do
    [ -f "$dir/models.py" ] || continue
    app="$(basename "$dir")"
    [[ "$app" == "venv" || "$app" == "__pycache__" ]] && continue
    tests=""
    if [ -d "$dir/tests" ]; then
        tests="$(find "$dir/tests" -maxdepth 1 -name 'test_*.py' -printf '%f ' 2>/dev/null)"
    fi
    [ -f "$dir/tests.py" ] && tests="${tests}tests.py "
    if [ -n "${tests// /}" ]; then
        echo "  $app: ${tests% }"
    else
        echo "  $app: (sin tests)"
    fi
done

echo ""
echo "## Tests — funciones por archivo"
while IFS= read -r tf; do
    rel="${tf#$PROYECTO/}"
    echo ""
    echo "  $rel:"
    grep -E '^[[:space:]]*def test_' "$tf" \
        | sed -E 's/^[[:space:]]*def (test_[a-zA-Z0-9_]+).*/\1/' \
        | while IFS= read -r t; do echo "    - $t"; done || true
done < <(find "$BACKEND_DIR" -path '*/tests/test_*.py' -type f | sort)

echo ""
echo "## Frontend — archivos de código"
if [ -n "$FRONTEND_DIR" ] && [ -d "$FRONTEND_DIR" ]; then
    ( cd "$FRONTEND_DIR" && find view services components data -name '*.py' 2>/dev/null | sort )
else
    echo "  (sin directorio frontend)"
fi
echo ""
echo "## Endpoints definidos en urls.py"
( cd "$BACKEND_DIR" && grep -rhnE "path\(['\"]" --include='urls.py' */urls.py 2>/dev/null | sed -E "s/.*path\('([^']*)'.*/\1/" | sort -u | head -60 ) || true