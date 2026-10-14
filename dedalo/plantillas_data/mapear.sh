#!/usr/bin/env bash
# mapear.sh — Genera mapeo.txt: mapa del proyecto (módulos -> tests).
# Lo usa dedalo.sh para que el agente sepa qué tests existen y dónde tocar.
#
# Autodetecta el stack (Python/Django, Node, Rust) y deja que el agente
# localice módulos y tests. Sobreescribible con BACKEND_DIR, FRONTEND_DIR,
# PY_BACKEND (ver _env.sh).
#
# Uso:  bash mapear.sh > mapeo.txt
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# _env.sh comparte la detección con gate.sh (puede estar en la raíz o en gate_checks/)
if [ -f "$SCRIPT_DIR/gate_checks/_env.sh" ]; then
    source "$SCRIPT_DIR/gate_checks/_env.sh"
elif [ -f "$SCRIPT_DIR/_env.sh" ]; then
    source "$SCRIPT_DIR/_env.sh"
fi
PROYECTO="${PROYECTO:-$SCRIPT_DIR}"

printf '# Mapeo del proyecto — %s\n' "$PROYECTO"
printf '# Generado por mapear.sh el %s.\n' "$(date '+%F %H:%M')"
echo '# Regla: al cambiar código, actualiza/corre su test ANTES de dar por terminado.'
if [ -n "${PY_BACKEND:-}" ]; then
    echo "# Verificación rápida: cd $BACKEND_DIR && $PY_BACKEND -m pytest <test> -q"
else
    echo "# Ejecuta los tests del módulo elegido antes de terminar."
fi
echo ""

# ---- Backend: detecta stack y lista módulos + tests ----
if [ -n "${BACKEND_DIR:-}" ] && [ -d "$BACKEND_DIR" ]; then
    # Python/Django: aplicaciones con models.py
    if [ -n "${PY_BACKEND:-}" ] && [ -f "$BACKEND_DIR/manage.py" ]; then
        echo "## Backend — aplicaciones y sus tests"
        for dir in "$BACKEND_DIR"/*/; do
            [ -f "$dir/models.py" ] || continue
            app="$(basename "$dir")"
            [[ "$app" == "venv" || "$app" == "__pycache__" ]] && continue
            tests=""
            if [ -d "$dir/tests" ]; then
                # `find -printf` es sólo GNU; glob + basename funciona en BSD.
                for tf in "$dir"/tests/test_*.py; do
                    [ -f "$tf" ] && tests="$tests$(basename "$tf") "
                done
            fi
            [ -f "$dir/tests.py" ] && tests="${tests}tests.py "
            if [ -n "${tests// /}" ]; then
                echo "  $app: ${tests% }"
            else
                echo "  $app: (sin tests)"
            fi
        done
    elif [ -f "$BACKEND_DIR/package.json" ]; then
        # Node: módulos en src/lib con sus .test.
        echo "## Backend (Node) — módulos y tests"
        ( cd "$BACKEND_DIR" && find src lib -type f \( -name '*.ts' -o -name '*.js' \) 2>/dev/null \
            | grep -vE '\.(test|spec)\.' | sort ) || true
        echo "  (tests: *.test.ts|*.spec.ts junto a cada módulo)"
    elif [ -f "$BACKEND_DIR/Cargo.toml" ]; then
        echo "## Backend (Rust) — módulos"
        ls "$BACKEND_DIR/src" 2>/dev/null || echo "  (sin src/)"
        echo "  (tests: en src/**/tests/ o tests/)"
    fi

    echo ""
    echo "## Tests — funciones por archivo"
    if [ -n "${PY_BACKEND:-}" ]; then
        while IFS= read -r tf; do
            rel="${tf#$PROYECTO/}"
            echo ""
            echo "  $rel:"
            grep -E '^[[:space:]]*def test_' "$tf" 2>/dev/null \
                | sed -E 's/^[[:space:]]*def (test_[a-zA-Z0-9_]+).*/\1/' \
                | while IFS= read -r t; do echo "    - $t"; done || true
        done < <(find "$BACKEND_DIR" -path '*/tests/test_*.py' -type f | head -200 | sort)
    fi
else
    echo "## Backend — (sin BACKEND_DIR detectado)"
fi

# ---- Frontend: archivos de código ----
echo ""
echo "## Frontend — archivos de código"
if [ -n "${FRONTEND_DIR:-}" ] && [ -d "$FRONTEND_DIR" ]; then
    if [ -n "${PY_FRONTEND:-}" ]; then
        ( cd "$FRONTEND_DIR" && find view services components data -name '*.py' 2>/dev/null | sort ) || true
    else
        ( cd "$FRONTEND_DIR" && find src components pages services -type f \( -name '*.ts' -o -name '*.js' -o -name '*.vue' \) 2>/dev/null | sort ) || true
    fi
else
    echo "  (sin directorio frontend)"
fi

# ---- URLs/rutas del stack ----
echo ""
echo "## Rutas definidas"
if [ -n "${BACKEND_DIR:-}" ] && [ -d "$BACKEND_DIR" ]; then
    if [ -f "$BACKEND_DIR/manage.py" ]; then
        ( cd "$BACKEND_DIR" && grep -rhnE "path\(['\"]" --include='urls.py' */urls.py 2>/dev/null \
            | sed -E "s/.*path\('([^']*)'.*/\1/" | sort -u | head -60 ) || true
    elif [ -f "$BACKEND_DIR/package.json" ]; then
        ( cd "$BACKEND_DIR" && grep -rnE "app\.(get|post|put|delete)\(" --include='*.ts' --include='*.js' src 2>/dev/null \
            | sed -E "s/.*(get|post|put|delete)\('([^']*)'.*/\2/" | sort -u | head -60 ) || true
    fi
else
    echo "  (sin backend)"
fi
echo ""