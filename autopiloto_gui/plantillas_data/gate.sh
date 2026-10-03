#!/usr/bin/env bash
# gate.sh — Orquestador de checks (plugin-based).
# Cada check en gate_checks/*.sh devuelve 0=OK, 1=FAIL e imprime [GATE] ✓/✗.
# Orden: numérico por prefijo (01_, 02_, ...). Añade/limpia checks libremente.
#
# La detección de entorno (Python, venv, comandos de DB/migraciones/tests/
# backend) está centralizada en gate_checks/_env.sh y es sobreescribible.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECKS_DIR="$SCRIPT_DIR/gate_checks"

# Carga el entorno compartido (PROYECTO, PY_BACKEND, comandos...)
if [ -f "$CHECKS_DIR/_env.sh" ]; then
    source "$CHECKS_DIR/_env.sh"
elif [ -f "$SCRIPT_DIR/_env.sh" ]; then
    source "$SCRIPT_DIR/_env.sh"
else
    # Retrocompat: sin _env.sh definimos lo mínimo.
    # fail/ok también son obligatorios: sin ellos, un check que falla provoca
    # "fail: orden no encontrada" (rc=127) que el bucle ignora (no hay set -e)
    # y el gate terminaba imprimiendo "✅ TODO OK" con rc=0.
    PROYECTO="$SCRIPT_DIR"
    fail() { echo "[GATE] ✗ $1"; exit 1; }
    ok()   { echo "[GATE] ✓ $1"; }
fi

export PROYECTO

# ---- Cargar checks ----
if [ ! -d "$CHECKS_DIR" ]; then
    echo "[GATE] ⚠ No existe $CHECKS_DIR — se asume OK"
    exit 0
fi

shopt -s nullglob
checks=("$CHECKS_DIR"/*.sh)
shopt -u nullglob

# Excluir _env.sh (no es un check)
impl=()
for c in "${checks[@]}"; do
    [ "$(basename "$c")" != "_env.sh" ] && impl+=("$c")
done
checks=("${impl[@]}")

if [ ${#checks[@]} -eq 0 ]; then
    echo "[GATE] ⚠ Sin checks en $CHECKS_DIR — se asume OK"
    exit 0
fi

# ---- Ejecutar checks en orden (subshell aísla variables por check) ----
for check in "${checks[@]}"; do
    nombre="$(basename "$check")"
    if ( source "$check" ); then
        :
    else
        rc=$?
        [ $rc -eq 0 ] || fail "Check falló: $nombre"
    fi
done

echo ""
echo "[GATE] ✅ TODO OK"
exit 0