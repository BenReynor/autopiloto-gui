#!/usr/bin/env bash
# 98_criterio.sh — JUEZ de criterio en lenguaje natural (patrón goal-worker).
#
# Autopiloto extrae la línea "criterio: ..." de la primera tarea pendiente del
# plan.md y la exporta como CRITERIO. Este check NO necesita scripts por
# proyecto: escribes la condición en lenguaje natural y un juez (modelo barato)
# evalúa contra el estado real del repo si se cumple.
#
#   · CRITERIO vacío → se omite (gate determinista normal).
#   · El juez usa opencode con MODELO_JUEZ (def: modelo barato) y devuelve
#     {"met": true|false, "reason": "..."} o VERDICT: PASS/FAIL.
#   · Máx 2 llamadas: si el juez no puede responder (cuota/timeout), falla
#     SUAVE (⚠) para no bloquear el loop por culpa del proveedor.
#
# Configurable vía entorno: CRITERIO, MODELO_JUEZ, OPENCODE_AGENT_JUEZ,
# CLI_OPENCODE, TIMEOUT_JUEZ (def 120 s).
set -uo pipefail

if [ -z "${CRITERIO:-}" ]; then
    echo "[GATE] ⚠ sin CRITERIO (no hay línea 'criterio:' en la tarea), se omite el juez"
    exit 0
fi

CLI="${CLI_OPENCODE:-opencode}"
[ -n "$CLI" ] && command -v "$CLI" >/dev/null 2>&1 || {
    echo "[GATE] ⚠ opencode no disponible para el juez; se omite (CRITERIO='${CRITERIO:0:60}…')"
    exit 0
}

TIMEOUT_JUEZ="${TIMEOUT_JUEZ:-120}"
MODELO_JUEZ="${MODELO_JUEZ:-opencode/nemotron-3.5-lightning-free}"
AGENTE="${OPENCODE_AGENT_JUEZ:-build}"
GATE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROYECTO_J="$GATE_DIR"
[ "$(basename "$PROYECTO_J")" = "gate_checks" ] && PROYECTO_J="$(dirname "$PROYECTO_J")"

# Estado actual del repo: diff pendiente + tests localizados, para que el juez
# evalúe contra hechos y no contra suposiciones.
ESTADO=""
if git -C "$PROYECTO_J" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    ESTADO="$(git -C "$PROYECTO_J" status --porcelain | head -30)"
fi
DETECTADO=""
[ -f "$PROYECTO_J/mapeo.txt" ] && DETECTADO="$(grep -E '^# ' "$PROYECTO_J/mapeo.txt" | head -5)"

PROMPT_JUEZ="Eres el JUEZ de una tarea del autopiloto. Evalúas si el CRITERIO de la tarea se cumple en el ESTADO ACTUAL del repo.
CRITERIO: ${CRITERIO}

ESTADO ACTUAL (git status):
${ESTADO:-<árbol limpio>}

${DETECTADO:+- Mapa del proyecto (mapeo.txt): 
$DETECTADO
}
Corre los tests relevantes (pytest/vitest/npm test...) si el criterio lo exige y lee los archivos clave. NO modifiques nada: solo evalúa.

Respondes ÚNICAMENTE con JSON en la última línea, sin markdown:
{\"met\": true, \"reason\": \"<por qué se cumple, máx 120 caracteres>\"}   o
{\"met\": false, \"reason\": \"<qué falta, máx 120 caracteres>\"}"

SALIDA="$(timeout "$TIMEOUT_JUEZ" "$CLI" run --agent "$AGENTE" --model "$MODELO_JUEZ" "$PROMPT_JUEZ" 2>&1)"
RC=$?

if [ "$RC" -eq 124 ]; then
    echo "[GATE] ⚠ juez agotó el timeout (${TIMEOUT_JUEZ}s); se omite (no bloqueante)"
    exit 0
fi
if [ "$RC" -ne 0 ]; then
    echo "[GATE] ⚠ juez salió con rc=$RC (¿cuota o red?); se omite (no bloqueante)"
    exit 0
fi

# Parsear veredicto: {"met": true|false} o VERDICT: PASS|FAIL
VEREDICTO="$(printf '%s\n' "$SALIDA" | grep -oE '"met"[[:space:]]*:[[:space:]]*(true|false)' | tail -1)"
if [ -z "$VEREDICTO" ]; then
    VEREDICTO="$(printf '%s\n' "$SALIDA" | grep -oE 'VERDICT[[:space:]]*:[[:space:]]*(PASS|FAIL)' | tail -1)"
fi
RAZON="$(printf '%s\n' "$SALIDA" | grep -oE '"reason"[[:space:]]*:[[:space:]]*"[^"]*"' | tail -1 | sed -E 's/"reason"[[:space:]]*:[[:space:]]*"//; s/"$//')"

case "$VEREDICTO" in
    *true*|*PASS*)
        echo "[GATE] ✓ juez: criterio cumplido{${RAZON:+ — $RAZON}}"
        exit 0
        ;;
    *false*|*FAIL*)
        echo "[GATE] ✗ juez: criterio NO cumplido (${RAZON:-sin detalle})"
        exit 1
        ;;
    *)
        echo "[GATE] ⚠ juez sin veredicto legible; se omite (no bloqueante)"
        exit 0
        ;;
esac