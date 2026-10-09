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
# Configurable vía entorno: CRITERIO, AGENTE_JUEZ (opencode|codex|claude|auto),
# MODELO_JUEZ (sólo opencode), OPENCODE_AGENT_JUEZ, CLI_OPENCODE/CLI_CODEX/
# CLI_CLAUDE, AGENTE_TAREA, AGENTES_PREFERIDOS, TIMEOUT_JUEZ (def 120 s).
set -uo pipefail

if [ -z "${CRITERIO:-}" ]; then
    echo "[GATE] ⚠ sin CRITERIO (no hay línea 'criterio:' en la tarea), se omite el juez"
    exit 0
fi

TIMEOUT_JUEZ="${TIMEOUT_JUEZ:-120}"
MODELO_JUEZ="${MODELO_JUEZ:-opencode/nemotron-3.5-lightning-free}"
OPENCODE_AGENT="${OPENCODE_AGENT_JUEZ:-build}"

# Agente del juez: AGENTE_JUEZ (opencode|codex|claude|auto). "auto" y vacío
# siguen al agente de tarea si su CLI está disponible, y si no, al primero
# disponible. MODELO_JUEZ sólo aplica a opencode.
AGENTE="${AGENTE_JUEZ:-auto}"
case "$AGENTE" in
    auto|"")
        if [ -n "${AGENTE_TAREA:-}" ] && [ "${AGENTE_TAREA}" != "auto" ]; then
            _cand="$AGENTE_TAREA"
        else
            _cand=""
        fi
        _pick=""
        for _a in $_cand ${AGENTES_PREFERIDOS:-opencode codex claude}; do
            [ -z "$_a" ] || [ "$_a" = "auto" ] && continue
            case "$_a" in
                opencode) _b="${CLI_OPENCODE:-opencode}" ;;
                codex)    _b="${CLI_CODEX:-codex}" ;;
                claude)   _b="${CLI_CLAUDE:-claude}" ;;
                *)        continue ;;
            esac
            command -v "$_b" >/dev/null 2>&1 && { _pick="$_a"; break; }
        done
        # _cand primero SÓLO si su CLI existe; si no, cae a la lista.
        if [ -z "$_pick" ] && [ -n "$_cand" ]; then
            case "$_cand" in
                opencode) command -v "${CLI_OPENCODE:-opencode}" >/dev/null 2>&1 && _pick="$_cand" ;;
                codex)    command -v "${CLI_CODEX:-codex}" >/dev/null 2>&1 && _pick="$_cand" ;;
                claude)   command -v "${CLI_CLAUDE:-claude}" >/dev/null 2>&1 && _pick="$_cand" ;;
            esac
        fi
        AGENTE="${_pick:-opencode}"
        ;;
esac

case "$AGENTE" in
    opencode) CLI="${CLI_OPENCODE:-opencode}" ;;
    codex)    CLI="${CLI_CODEX:-codex}" ;;
    claude)   CLI="${CLI_CLAUDE:-claude}" ;;
    *)        CLI="${CLI_OPENCODE:-opencode}"; AGENTE="opencode" ;;
esac

if ! command -v "$CLI" >/dev/null 2>&1; then
    echo "[GATE] ⚠ $AGENTE no disponible para el juez; se omite (CRITERIO='${CRITERIO:0:60}…')"
    exit 0
fi
if [ "$AGENTE" != "opencode" ]; then
    echo "[GATE] juez: agente=$AGENTE (MODELO_JUEZ no aplica a $AGENTE)"
fi
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

# Límite de tiempo portátil, mismo criterio que _timeout() en autopiloto.sh:
# GNU timeout > gtimeout (Homebrew) > respaldo en bash puro (macOS base no
# trae ninguno y un `timeout` directo saldría con rc=127: el juez se omitiría
# siempre). El respaldo devuelve 124 (como GNU) cuando se agota el tope.
_juez_timeout() {
    local segs="$1" pid i=0
    shift
    if command -v timeout >/dev/null 2>&1; then
        timeout "$segs" "$@"
    elif command -v gtimeout >/dev/null 2>&1; then
        gtimeout "$segs" "$@"
    else
        "$@" &
        pid=$!
        while kill -0 "$pid" 2>/dev/null; do
            [ "$i" -ge "$segs" ] && break
            i=$((i + 1))
            sleep 1
        done
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            wait "$pid" 2>/dev/null || true
            return 124
        fi
        wait "$pid"
        return $?
    fi
}

# Invocación según el agente del juez. El modelo (--model) sólo existe en
# opencode; codex y claude se configuran por su cuenta y no aceptan la flag,
# así que se les ignora MODELO_JUEZ.
run_juez() {
    case "$AGENTE" in
        opencode)
            if [ -n "$MODELO_JUEZ" ]; then
                _juez_timeout "$TIMEOUT_JUEZ" "$CLI" run --agent "$OPENCODE_AGENT" --model "$MODELO_JUEZ" "$PROMPT_JUEZ" 2>&1
            else
                _juez_timeout "$TIMEOUT_JUEZ" "$CLI" run --agent "$OPENCODE_AGENT" "$PROMPT_JUEZ" 2>&1
            fi
            ;;
        codex)
            # Los flags van en un array: entrecomillar "${CODEX_FLAGS:-}"
            # pasaría un argumento vacío que el CLI tomaría como el prompt.
            local -a flags=()
            [ -n "${CODEX_FLAGS:-}" ] && read -r -a flags <<< "$CODEX_FLAGS"
            _juez_timeout "$TIMEOUT_JUEZ" "$CLI" exec --skip-git-repo-check \
                ${flags[@]+"${flags[@]}"} "$PROMPT_JUEZ" 2>&1
            ;;
        claude)
            local -a flags=()
            [ -n "${CLAUDE_FLAGS:-}" ] && read -r -a flags <<< "$CLAUDE_FLAGS"
            _juez_timeout "$TIMEOUT_JUEZ" "$CLI" -p --output-format text \
                ${flags[@]+"${flags[@]}"} "$PROMPT_JUEZ" 2>&1
            ;;
        *)
            _juez_timeout "$TIMEOUT_JUEZ" "$CLI" run --agent "$OPENCODE_AGENT" "$PROMPT_JUEZ" 2>&1
            ;;
    esac
}

SALIDA="$(run_juez)"
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