#!/usr/bin/env bash
# autopiloto.sh — Bucle autónomo para opencode, con git por ramas.
#
# Workflow de ramas (por tarea):
#   autopiloto/<fecha>                  <- rama base del run (hija de RAMA_BASE)
#   └── autopiloto/<fecha>/t<N>         <- una rama por tarea
#        · gate OK  -> merge (--ff-only) a la rama base y se borra
#        · gate KO  -> se borra con sus commits, nada toca la base
#   master nunca recibe commits del loop.
#
# Por cada tarea de plan.md:
#   1. Crea la rama de la tarea y lanza opencode en headless (--agent build).
#   2. Verifica con gate.sh (DB, migraciones, backend, endpoints, imports, tests).
#   3. Si el gate pasa: commitea SOLO lo de esa tarea, fusiona y marca [x].
#   4. Si el gate falla: borra la rama de la tarea y la marca [B].
#
# Uso:
#   ./autopiloto.sh [archivo_plan] [--hasta HH:MM] [--push] [--padre <rama>]
#   MAX_ITER=60 ./autopiloto.sh plan.md
#
# Portátil: deduce su raíz de su propia ubicación; funciona en cualquier
# proyecto copiando gate.sh, mapear.sh y autopiloto.sh a su raíz.
#
# Requisitos:
#   - PostgreSQL corriendo, .venv y frontend/venv con dependencias.
#   - opencode en el PATH (si pide confirmaciones, añade --auto a CLI_OPENCODE).
#   - Árbol de trabajo razonablemente limpio (los archivos sucios se llevan a
#     la rama base y pueden impedir el checkout si difieren).
set -uo pipefail

PROYECTO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$PROYECTO/gate.sh"
MAPEAR="$PROYECTO/mapear.sh"
MAPA="$PROYECTO/mapeo.txt"
LOG="$PROYECTO/progreso.log"
PLAN="$PROYECTO/plan.md"
MAX_ITER="${MAX_ITER:-40}"
TIMEOUT_POR_TAREA="${TIMEOUT_POR_TAREA:-900}"
MAX_REINTENTOS=2
CLI_OPENCODE="${CLI_OPENCODE:-opencode}"
RAMA_BASE="${RAMA_BASE:-master}"
PUSH=""
HASTA=""
CONTROL="plan\.md|progreso\.log|gate\.sh|autopiloto\.sh|mapear\.sh|mapeo\.txt|endpoints\.txt"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --hasta) HASTA="${2:-}"; shift 2 ;;
        --push) PUSH="1"; shift ;;
        --padre) RAMA_BASE="${2:-}"; shift 2 ;;
        -h|--help) sed -n '1,18p' "$0"; exit 0 ;;
        *) PLAN="$1"; shift ;;
    esac
done
[[ "$PLAN" != /* ]] && PLAN="$PROYECTO/$PLAN"

FECHA="$(date +%Y-%m-%d)"
RAMA_RUN="autopiloto/$FECHA"

logx() { echo "[$(date '+%F %H:%M')] $*" >> "$LOG"; }
hora_limite() { [[ -n "$HASTA" && "$(date +%H:%M)" > "$HASTA" ]]; }

snapshot() {
    git -C "$PROYECTO" status --porcelain | sed 's/^...//' | sort > "$1"
}

revertir() {
    # Revierte/borra solo los archivos que cambiaron durante la tarea,
    # preservando los archivos de control.
    comm -13 <(sort "$1") <(sort "$2") \
        | grep -vE "^($CONTROL)$" \
        | while IFS= read -r f; do
            git -C "$PROYECTO" checkout -- "$f" 2>/dev/null
            rm -rf "$f" 2>/dev/null
        done
}

proxima_tarea() {
    local l
    while IFS= read -r l; do
        if [[ "$l" == "- [ ] "* ]]; then
            echo "${l#- [ ] }"
            return 0
        fi
    done < "$PLAN"
    return 1
}

logx "== AUTOPILOTO INICIADO (max_iter=$MAX_ITER, hasta=${HASTA:-sin limite}, base=$RAMA_BASE) =="

echo "[autopiloto] Baseline: gate.sh..."
if ! bash "$GATE"; then
    echo "El repo NO pasa la verificación baseline. Corrige y relanza."
    logx "ABORTADO: baseline falló"
    exit 1
fi
logx "Baseline GATE OK"

# ---- Mapa módulos -> tests (estilo test_map) ----
if [ -f "$MAPEAR" ]; then
    bash "$MAPEAR" > "$MAPA" 2>/dev/null && logx "mapeo.txt regenerado" || echo "[autopiloto] ⚠ no se pudo generar mapeo.txt"
fi

# ---- Rama base del run ----
if git -C "$PROYECTO" rev-parse --verify "$RAMA_RUN" >/dev/null 2>&1; then
    git -C "$PROYECTO" checkout -q "$RAMA_RUN"
    echo "[autopiloto] Reusando rama $RAMA_RUN"
else
    if ! git -C "$PROYECTO" checkout -q -b "$RAMA_RUN" "$RAMA_BASE"; then
        echo "[autopiloto] ✗ no se pudo crear $RAMA_RUN desde $RAMA_BASE (¿árbol sucio?)."
        logx "ABORTADO: no se pudo crear la rama base"
        exit 1
    fi
    echo "[autopiloto] Rama base: $RAMA_RUN (desde $RAMA_BASE)"
fi
logx "Rama base: $RAMA_RUN"

iter=0
while (( iter < MAX_ITER )); do
    if hora_limite; then
        logx "Hora límite ($HASTA) alcanzada."
        echo "[autopiloto] ⏰ Hora límite alcanzada."
        break
    fi

    if ! TAREA="$(proxima_tarea)"; then
        logx "No quedan tareas pendientes en $(basename "$PLAN")."
        echo "[autopiloto] ✔ No quedan tareas pendientes."
        break
    fi

    iter=$((iter + 1))
    RAMA_TAREA="autopiloto/$FECHA/t$iter"
    logx "== Iteración $iter: $TAREA (rama $RAMA_TAREA) =="
    echo "[autopiloto] [$iter/$MAX_ITER] $TAREA -> $RAMA_TAREA"

    git -C "$PROYECTO" checkout -q -b "$RAMA_TAREA" "$RAMA_RUN"
    BEFORE="$(mktemp)"; AFTER="$(mktemp)"; OUT="$(mktemp)"
    snapshot "$BEFORE"

    hecho=0
    for intento in $(seq 1 "$MAX_REINTENTOS"); do
        PRE=""
        [ "$intento" -gt 1 ] && PRE="El intento anterior no pasó la verificación: no repitas tu cambio, corrígelo. "

        PROMPT="Estás en MODO AUTOPILOTO (aplica las skills autopiloto y veracidad).
Tarea actual (solo esta): ${TAREA}
${PRE}Lee plan.md y progreso.log antes de tocar nada. Lee también mapeo.txt (mapa módulos→tests): localiza el/los test del código que vas a tocar y úsalos como contrato.
Ejecuta ÚNICAMENTE esta tarea.
NO hagas commits, NO crees, cambies ni borres ramas: el script gestiona git.
NO edites autopiloto.sh, gate.sh, mapear.sh, mapeo.txt, plan.md, progreso.log, endpoints.txt, .env ni SECURITY.md.
Al terminar, responde con un resumen conciso de qué cambiaste y qué tests corriste."

        timeout "$TIMEOUT_POR_TAREA" "$CLI_OPENCODE" run --agent build "$PROMPT" > "$OUT" 2>&1
        rc=$?
        if [ "$rc" -eq 124 ]; then
            echo "[autopiloto] ⚠ timeout: la tarea tardó más de ${TIMEOUT_POR_TAREA}s" | tee -a "$LOG"
        elif [ "$rc" -ne 0 ]; then
            echo "[autopiloto] ⚠ opencode salió con rc=$rc" | tee -a "$LOG"
        fi
        cat "$OUT" >> "$LOG"
        cat "$OUT"

        # Guardia: opencode no debe haberse movido de rama
        if [ "$(git -C "$PROYECTO" branch --show-current)" != "$RAMA_TAREA" ]; then
            echo "[autopiloto] ✗✗ opencode cambió de rama. Abortando el run: requiere revisión humana." | tee -a "$LOG"
            echo "[autopiloto] rama actual: $(git -C "$PROYECTO" branch --show-current)"
            logx "ABORTADO: se detectó cambio de rama no autorizado"
            exit 3
        fi

        if bash "$GATE"; then
            hecho=1
            break
        fi
        logx "GATE FALLÓ tras opencode (intento $intento)"
        echo "[autopiloto] ✗ la tarea no pasó el gate (intento $intento/$MAX_REINTENTOS)"
    done

    snapshot "$AFTER"

    if [ "$hecho" -eq 1 ]; then
        CHANGED="$(comm -13 <(sort "$BEFORE") <(sort "$AFTER") | grep -vE "^($CONTROL)$")"
        if [ -n "$CHANGED" ]; then
            if ( cd "$PROYECTO" && git add -- $CHANGED && git commit -q -m "autopiloto: $TAREA" ); then
                logx "commit en $RAMA_TAREA: $TAREA"
                echo "[autopiloto] ✔ commit: $TAREA"
            fi
        else
            logx "tarea completada sin cambios nuevos"
            echo "[autopiloto] ✔ tarea completada sin cambios nuevos"
        fi
        if git -C "$PROYECTO" checkout -q "$RAMA_RUN" \
            && git -C "$PROYECTO" merge -q --ff-only "$RAMA_TAREA" 2>/dev/null; then
            git -C "$PROYECTO" branch -q -d "$RAMA_TAREA"
            logx "mergeada $RAMA_TAREA -> $RAMA_RUN"
        else
            echo "[autopiloto] ⚠ no se pudo fusionar $RAMA_TAREA; sigue creada." | tee -a "$LOG"
        fi
        sed -i "0,/^- \[ \]/s//- [x]/" "$PLAN"
    else
        git -C "$PROYECTO" checkout -q "$RAMA_RUN"
        git -C "$PROYECTO" branch -q -D "$RAMA_TAREA"
        revertir "$BEFORE" "$AFTER"
        sed -i "0,/^- \[ \]/s//- [B]/" "$PLAN"
        logx "tarea BLOQUEADA: $TAREA (rama $RAMA_TAREA descartada)"
        echo "[autopiloto] ✗ tarea bloqueada tras $MAX_REINTENTOS intentos. Marcada [B] en plan.md"
    fi

    rm -f "$BEFORE" "$AFTER" "$OUT"
done

# ---- Push opcional de la rama base ----
if [ -n "$PUSH" ]; then
    git -C "$PROYECTO" push -u origin "$RAMA_RUN" && logx "push: origin/$RAMA_RUN"
    echo "[autopiloto] push OK: origin/$RAMA_RUN"
    echo "[autopiloto] abre el PR de $RAMA_RUN -> $RAMA_BASE"
fi

echo ""
echo "== RESUMEN (final de progreso.log) =="
tail -25 "$LOG"
logx "== AUTOPILOTO FINALIZADO (iter=$iter, rama=$RAMA_RUN) =="
exit 0