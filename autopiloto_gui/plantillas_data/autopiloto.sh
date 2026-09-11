#!/usr/bin/env bash
# autopiloto.sh — Bucle autónomo para agentes IA, con git por ramas.
#
# Workflow de ramas (por tarea):
#   autopiloto/<fecha>                  <- rama base del run (hija de RAMA_BASE)
#   └── autopiloto/<fecha>/t<N>         <- una rama por tarea
#        · gate OK + revisor PASS -> merge (--ff-only) a la base y se borra
#        · gate KO o revisor FAIL -> reintento; si agota, se borra sin tocar la base
#   master nunca recibe commits del loop.
#
# Por cada tarea de plan.md:
#   1. Crea la rama de la tarea y ejecuta el agente configurado (AGENTE_TAREA).
#   2. Verifica con gate.sh (DB, migraciones, backend, endpoints, imports, tests).
#   3. GATE DUAL: si pasó el gate, un segundo agente (AGENTE_REVISOR) revisa el
#      diff en frío y exige "VERDICT: PASS" antes de commitear.
#   4. Si pasa todo: commitea SOLO lo de esa tarea, fusiona y marca [x].
#   5. Si falla: renitenta y, al agotar, borra la rama y marca [B].
#
# Uso:
#   ./autopiloto.sh [plan] [--hasta HH:MM] [--push] [--padre <rama>]
#   MAX_ITER=60 ./autopiloto.sh plan.md
#
# Variables de entorno (opcional):
#   AGENTE_TAREA     agente que implementa (opencode | claude | codex).  def: opencode
#   MODELO_TAREA     modelo provider/model para la tarea (opencode --model).  def: vacío (usa config)
#   AGENTE_REVISOR   agente revisor del diff; vacío = auto (prefiere uno distinto).
#   MODELO_REVISOR   modelo provider/model para el revisor del diff.
#   REVISION_DUAL    "1" activa el gate dual (def), "0" lo apaga.
#   MAX_COSTO        presupuesto en USD (0 = sin límite). Costo estimado por iteración.
#   COSTO_POR_ITER   costo estimado USD por tarea+revisión (def 0.50).
#   VOZ              "1" activa alertas al bloquearte/terminar (notify-send, spd-say).
#
# Portátil: deduce su raíz de su propia ubicación; copia gate.sh, mapear.sh y
# autopiloto.sh a la raíz de cualquier proyecto.
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
AGENTE_TAREA="${AGENTE_TAREA:-opencode}"
MODELO_TAREA="${MODELO_TAREA:-}"
AGENTE_REVISOR="${AGENTE_REVISOR:-}"
MODELO_REVISOR="${MODELO_REVISOR:-}"
REVISION_DUAL="${REVISION_DUAL:-1}"
VOZ="${VOZ:-0}"
MAX_COSTO="${MAX_COSTO:-0}"
COSTO_POR_ITER="${COSTO_POR_ITER:-0.50}"
RAMA_BASE="${RAMA_BASE:-master}"
PUSH=""
HASTA=""
CONTROL="plan\.md|progreso\.log|gate\.sh|autopiloto\.sh|mapear\.sh|mapeo\.txt|endpoints\.txt"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --hasta) HASTA="${2:-}"; shift 2 ;;
        --push) PUSH="1"; shift ;;
        --padre) RAMA_BASE="${2:-}"; shift 2 ;;
        -h|--help) sed -n '1,22p' "$0"; exit 0 ;;
        *) PLAN="$1"; shift ;;
    esac
done
[[ "$PLAN" != /* ]] && PLAN="$PROYECTO/$PLAN"

FECHA="$(date +%Y-%m-%d)"
RAMA_RUN="autopiloto/$FECHA"

logx() { echo "[$(date '+%F %H:%M')] $*" >> "$LOG"; }
hora_limite() { [[ -n "$HASTA" && "$(date +%H:%M)" > "$HASTA" ]]; }

hay_internet() {
    local i
    for i in 1 2 3; do
        if ping -c1 -W2 8.8.8.8 >/dev/null 2>&1; then return 0; fi
        sleep 2
    done
    return 1
}

agente_disponible() { command -v "$1" >/dev/null 2>&1; }

alerta() {
    [ "$VOZ" = "1" ] || return 0
    command -v notify-send >/dev/null 2>&1 && notify-send "Autopiloto" "$1" 2>/dev/null
    command -v spd-say >/dev/null 2>&1 && spd-say "$1" >/dev/null 2>&1
    printf '\a' 2>/dev/null || true
}

run_agente() {
    local agente="$1" salida="$2" modelo="${3:-}"
    shift 3
    case "$agente" in
        opencode)
            if [ -n "$modelo" ]; then
                timeout "$TIMEOUT_POR_TAREA" "$CLI_OPENCODE" run --agent build --model "$modelo" "$@" > "$salida" 2>&1
            else
                timeout "$TIMEOUT_POR_TAREA" "$CLI_OPENCODE" run --agent build "$@" > "$salida" 2>&1
            fi ;;
        claude)
            timeout "$TIMEOUT_POR_TAREA" claude -p --dangerously-skip-permissions "$@" > "$salida" 2>&1 ;;
        codex)
            timeout "$TIMEOUT_POR_TAREA" codex exec --yolo "$@" > "$salida" 2>&1 ;;
        *)
            timeout "$TIMEOUT_POR_TAREA" "$agente" "$@" > "$salida" 2>&1 ;;
    esac
    return $?
}

elegir_revisor() {
    local preferido="${AGENTE_REVISOR:-}"
    for a in "$preferido" codex claude opencode; do
        [ -z "$a" ] && continue
        agente_disponible "$a" || continue
        [ "$a" != "$AGENTE_TAREA" ] && { echo "$a"; return 0; }
    done
    [ -n "$preferido" ] && agente_disponible "$preferido" && { echo "$preferido"; return 0; }
    agente_disponible "$AGENTE_TAREA" && { echo "$AGENTE_TAREA"; return 0; }
    echo ""
}

revisar_diff() {
    local rev="$1" rev_out vdiff
    rev_out="$(mktemp)"
    vdiff="$(git -C "$PROYECTO" diff --stat; echo '── diff ──'; git -C "$PROYECTO" diff)"
    local PROMPT_REV="Eres el REVISOR en modo autopiloto (skills autopiloto y veracidad).
Revisas el diff COMPLETO de una tarea, en frío, sin haber participado de ella.
Tarea: ${TAREA}

${vdiff}

Evalúa SOLO: (1) la tarea satisface su criterio, (2) no rompe nada obvio del proyecto,
(3) sin secretos, (4) sin scope creep (cambios ajenos a la tarea).
Responde con 2 o 3 líneas de razones y, EN LA ÚLTIMA LÍNEA, exactamente: VERDICT: PASS o VERDICT: FAIL"
    run_agente "$rev" "$rev_out" "$MODELO_REVISOR" "$PROMPT_REV"
    cat "$rev_out" >> "$LOG"
    if grep -q "VERDICT: PASS" "$rev_out"; then
        echo "[autopiloto] ✔ revisor ($rev): PASS"
        grep -iE "VERDICT:" "$rev_out" | tail -1
        rm -f "$rev_out"
        return 0
    fi
    echo "[autopiloto] ✗ revisor ($rev): FAIL"
    grep -iE "VERDICT:" "$rev_out" | tail -1
    rm -f "$rev_out"
    return 1
}

snapshot() {
    git -C "$PROYECTO" status --porcelain | sed 's/^...//' | sort > "$1"
}

revertir() {
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

REVISOR="$(elegir_revisor)"
COSTO_TOTAL=0
logx "== AUTOPILOTO INICIADO (agente=$AGENTE_TAREA, modelo=$MODELO_TAREA, revisor=${REVISOR:-ninguno}, modelo_rev=$MODELO_REVISOR, dual=$REVISION_DUAL, max_iter=$MAX_ITER, hasta=${HASTA:-sin limite}, base=$RAMA_BASE, costo_max=$MAX_COSTO) =="

echo "[autopiloto] Agente de tarea: ${AGENTE_TAREA} ${MODELO_TAREA:+($MODELO_TAREA)}"
echo "[autopiloto] Revisor dual:    ${REVISOR:-NINGUNO} ${MODELO_REVISOR:+($MODELO_REVISOR)} (dual=$REVISION_DUAL)"

echo "[autopiloto] Comprobando internet…"
if ! hay_internet; then
    echo "[autopiloto] ✗ SIN INTERNET. Los modelos IA no pueden responder; abortando."
    logx "ABORTADO: sin internet"
    alerta "Sin internet, se aborta el autopiloto"
    exit 4
fi
logx "Internet OK"

echo "[autopiloto] Baseline: gate.sh..."
if ! bash "$GATE"; then
    echo "El repo NO pasa la verificación baseline. Corrige y relanza."
    logx "ABORTADO: baseline falló"
    alerta "Baseline falló, el autopiloto no arranca"
    exit 1
fi
logx "Baseline GATE OK"

if [ -f "$MAPEAR" ]; then
    bash "$MAPEAR" > "$MAPA" 2>/dev/null && logx "mapeo.txt regenerado" || echo "[autopiloto] ⚠ no se pudo generar mapeo.txt"
fi

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
        alerta "Hora límite alcanzada"
        break
    fi
    if [ "$MAX_COSTO" -gt 0 ] && awk -v t="$COSTO_TOTAL" -v m="$MAX_COSTO" 'BEGIN{exit !(t>=m)}'; then
        logx "Presupuesto agotado (${COSTO_TOTAL}/${MAX_COSTO} USD)."
        echo "[autopiloto] 💸 Presupuesto agotado (${COSTO_TOTAL}/${MAX_COSTO} USD)."
        alerta "Presupuesto agotado"
        break
    fi

    if ! hay_internet; then
        logx "SIN INTERNET: loop detenido para no lanzar tareas sin modelo disponible."
        echo "[autopiloto] ✗ SIN INTERNET. Deteniendo el loop (los modelos IA no responden)."
        alerta "Sin internet, se detiene el autopiloto"
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

        run_agente "$AGENTE_TAREA" "$OUT" "$MODELO_TAREA" "$PROMPT"
        rc=$?
        if [ "$rc" -eq 124 ]; then
            echo "[autopiloto] ⚠ timeout: ${AGENTE_TAREA} tardó más de ${TIMEOUT_POR_TAREA}s" | tee -a "$LOG"
            alerta "Tiempo agotado en una tarea"
        elif [ "$rc" -ne 0 ]; then
            echo "[autopiloto] ⚠ ${AGENTE_TAREA} salió con rc=$rc" | tee -a "$LOG"
        fi
        cat "$OUT" >> "$LOG"
        cat "$OUT"

        if [ "$(git -C "$PROYECTO" branch --show-current)" != "$RAMA_TAREA" ]; then
            echo "[autopiloto] ✗✗ el agente cambió de rama. Abortando: requiere revisión humana." | tee -a "$LOG"
            logx "ABORTADO: se detectó cambio de rama no autorizado"
            alerta "El agente cambió de rama, se aborta el run"
            exit 3
        fi

        if bash "$GATE"; then
            if [ "$REVISION_DUAL" = "1" ] && [ -n "$REVISOR" ]; then
                if revisar_diff "$REVISOR"; then
                    hecho=1
                    break
                fi
                logx "REVISOR FAIL (intento $intento)"
                echo "[autopiloto] ✗ el revisor rechazó el diff (intento $intento/$MAX_REINTENTOS)"
            else
                hecho=1
                break
            fi
        else
            logx "GATE FALLÓ tras el agente (intento $intento)"
            echo "[autopiloto] ✗ la tarea no pasó el gate (intento $intento/$MAX_REINTENTOS)"
        fi
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
        alerta "Tarea bloqueada: $TAREA"
    fi

    COSTO_TOTAL="$(awk -v t="$COSTO_TOTAL" -v a="$COSTO_POR_ITER" 'BEGIN{printf "%.2f", t+a}')"
    logx "Costo estimado acumulado: $COSTO_TOTAL USD"
    echo "[autopiloto] 💰 Costo estimado acumulado: ${COSTO_TOTAL} USD"

    rm -f "$BEFORE" "$AFTER" "$OUT"
done

if [ -n "$PUSH" ]; then
    git -C "$PROYECTO" push -u origin "$RAMA_RUN" && logx "push: origin/$RAMA_RUN"
    echo "[autopiloto] push OK: origin/$RAMA_RUN"
    echo "[autopiloto] abre el PR de $RAMA_RUN -> $RAMA_BASE"
fi

echo ""
echo "== RESUMEN (final de progreso.log) =="
tail -25 "$LOG"
logx "== AUTOPILOTO FINALIZADO (iter=$iter, rama=$RAMA_RUN, costo≈$COSTO_TOTAL) =="
alerta "Autopiloto finalizado"
exit 0