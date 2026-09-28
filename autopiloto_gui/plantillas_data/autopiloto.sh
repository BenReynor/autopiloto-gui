#!/usr/bin/env bash
# autopiloto.sh — Bucle autónomo para agentes IA, con git por ramas.
#
# Workflow de ramas (por tarea):
#   autopiloto/<fecha>                          <- rama base del run (hija de RAMA_BASE)
#   └── autopiloto/tareas/<fecha>/t<N>          <- una rama por tarea (git no
#                                                  permite ramas bajo el nombre
#                                                  autopiloto/<fecha>, que ya
#                                                  existe como ref, así que se
#                                                  agrupan en autopiloto/tareas/)
#        · gate OK + revisor PASS -> merge (--ff-only) a la base y se borra
#        · gate KO o revisor FAIL -> reintento; si agota, se borra sin tocar la base
#   master nunca recibe commits del loop.
#
# Por cada tarea de plan.md:
#   1. Crea la rama de la tarea y ejecuta el agente configurado (AGENTE_TAREA).
#   2. Verifica con gate.sh (checks en gate_checks/*.sh).
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
#   AGENTE_TAREA      agente que implementa (opencode|codex|claude). def: auto
#   AGENTES_PREFERIDOS orden de preferencia para auto y revisor. def: "opencode codex claude"
#   CLI_OPENCODE      binario de opencode (def: opencode)
#   CLI_CODEX         binario de codex (def: codex)
#   CLI_CLAUDE        binario de claude (def: claude)
#   MODELO_TAREA      modelo provider/model para la tarea (sólo opencode). def: vacío
#   AGENTE_REVISOR    agente revisor del diff; vacío = auto (prefiere uno distinto).
#   MODELO_REVISOR    modelo provider/model para el revisor del diff (sólo opencode).
#   MODELO_JUEZ       modelo barato del juez de criterio (98_criterio.sh, opencode).
#                     def: opencode/nemotron-3.5-lightning-free
#   OPENCODE_AGENT_JUEZ agente de opencode para el juez (def: build)
#   CRITERIO          se extrae del plan.md (línea "criterio:" bajo la tarea) y
#                     se exporta al gate para verse en los checks.
#   NAVEGADOR         "1" activa navegador automático antes de cada tarea.
#   MODELO_NAVEGADOR  modelo provider/model para el navegador (sólo opencode).
#   OPENCODE_AGENT_TAREA agente de opencode para la tarea (def: build)
#   OPENCODE_AGENT_NAV   agente de opencode para navegador (def: navigate)
#   CODEX_FLAGS       flags extra para codex exec ("" por defecto)
#   CLAUDE_FLAGS      flags extra para claude -p ("" por defecto)
#   REVISION_DUAL     "1" activa el gate dual (def), "0" lo apaga.
#   REVISION_MANUAL   "1" pausa antes de commit y espera aprobación GUI, "0" automático.
#   MAX_COSTO         presupuesto en USD (0 = sin límite). Costo estimado por iteración.
#   COSTO_POR_ITER    costo estimado USD por tarea+revisión (def 0.50).
#   VOZ               "1" activa alertas al bloquearte/terminar (notify-send, spd-say).
#
# Memoria del proyecto (lecciones.md):
#   · Se inyecta al agente antes de cada tarea para no repetir errores pasados
#     (corrección única de errores).
#   · Cuando una tarea queda bloqueada se añade una lección automática.
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
LECCIONES="$PROYECTO/lecciones.md"
MAX_ITER="${MAX_ITER:-40}"
TIMEOUT_POR_TAREA="${TIMEOUT_POR_TAREA:-900}"
TIMEOUT_NAVEGADOR="${TIMEOUT_NAVEGADOR:-60}"
MAX_REINTENTOS=2
AGENTE_TAREA="${AGENTE_TAREA:-}"
AGENTES_PREFERIDOS="${AGENTES_PREFERIDOS:-opencode codex claude}"
MODELO_TAREA="${MODELO_TAREA:-}"
MODELO_NAVEGADOR="${MODELO_NAVEGADOR:-opencode/big-pickle}"
NAVEGADOR="${NAVEGADOR:-0}"
AGENTE_REVISOR="${AGENTE_REVISOR:-}"
MODELO_REVISOR="${MODELO_REVISOR:-}"
MODELO_JUEZ="${MODELO_JUEZ:-opencode/nemotron-3.5-lightning-free}"
JUEZ_AGENTE_JUEZ="${OPENCODE_AGENT_JUEZ:-build}"
REVISION_DUAL="${REVISION_DUAL:-1}"
REVISION_MANUAL="${REVISION_MANUAL:-0}"
VOZ="${VOZ:-0}"
MAX_COSTO="${MAX_COSTO:-0}"
COSTO_POR_ITER="${COSTO_POR_ITER:-0.50}"
RAMA_BASE="${RAMA_BASE:-master}"
PUSH=""
HASTA=""
CONTROL="plan\.md|lecciones\.md|progreso\.log|gate\.sh|autopiloto\.sh|mapear\.sh|mapeo\.txt|endpoints\.txt"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --hasta) HASTA="${2:-}"; shift 2 ;;
        --push) PUSH="1"; shift ;;
        --padre) RAMA_BASE="${2:-}"; shift 2 ;;
        --trabajo) RAMA_TRABAJO="${2:-}"; shift 2 ;;
        -h|--help) sed -n '1,22p' "$0"; exit 0 ;;
        *) PLAN="$1"; shift ;;
    esac
done
[[ "$PLAN" != /* ]] && PLAN="$PROYECTO/$PLAN"

FECHA="$(date +%Y-%m-%d)"
RAMA_RUN="autopiloto/$FECHA"
RAMA_TRABAJO="${RAMA_TRABAJO:-}"

logx() { echo "[$(date '+%F %H:%M:%S')] $*" >> "$LOG"; }
hora_limite() { [[ -n "$HASTA" && "$(date +%H:%M)" > "$HASTA" ]]; }

hay_internet() {
    local i
    for i in 1 2 3; do
        if ping -c1 -W2 8.8.8.8 >/dev/null 2>&1; then return 0; fi
        sleep 2
    done
    return 1
}

alerta() {
    [ "$VOZ" = "1" ] || return 0
    command -v notify-send >/dev/null 2>&1 && notify-send "Autopiloto" "$1" 2>/dev/null
    command -v spd-say >/dev/null 2>&1 && spd-say "$1" >/dev/null 2>&1
    printf '\a' 2>/dev/null || true
}

# Verifica si la salida indica agotamiento de tokens/cuota del proveedor IA.
tokens_agotados() {
    local archivo="$1"
    grep -qiE \
        -e "insufficient_quota" \
        -e "rate_limit_exceeded" \
        -e "quota.exceeded" \
        -e "credit.balance.is.too.low" \
        -e "billing.hard.limit" \
        -e "RESOURCE_EXHAUSTED" \
        -e "tokens?.exhausted" \
        -e "out.of.tokens" \
        -e "no.quota" \
        -e "quota.depleted" \
        -e "monthly.limit" \
        -e "usage.limit" \
        "$archivo" >/dev/null 2>&1
}

# Detecta el primer agente disponible (opencode -> codex -> claude).
# El orden y los binarios son configurables:
#   AGENTES_PREFERIDOS="codex opencode"  (orden de preferencia)
#   CLI_OPENCODE/CLI_CODEX/CLI_CLAUDE      (binario de cada agente)
detectar_agente() {
    local i
    for i in ${AGENTES_PREFERIDOS:-opencode codex claude}; do
        cli_agente "$i" >/dev/null 2>&1 && { echo "$i"; return 0; }
    done
    echo ""
}

# Devuelve el binario de un agente (o vacío si no está instalado).
cli_agente() {
    local agente="$1"
    case "$agente" in
        opencode) echo "${CLI_OPENCODE:-opencode}" ;;
        codex)    echo "${CLI_CODEX:-codex}" ;;
        claude)   echo "${CLI_CLAUDE:-claude}" ;;
        *) echo "" ;;
    esac
}

agente_ok() {
    local bin
    bin="$(cli_agente "$1")" || return 1
    [ -n "$bin" ] && command -v "$bin" >/dev/null 2>&1
}

# Ejecuta una tarea con cualquier agente. Devuelve su exit code.
#   $1 = agente (opencode|codex|claude)
#   $2 = archivo salida
#   $3 = modelo (sólo opencode; vacío = usa config)
#   "$@" = prompt (string)
run_agente() {
    local agente="$1" salida="$2" modelo="${3:-}" bin
    shift 3
    bin="$(cli_agente "$agente")"
    [ -n "$bin" ] || { echo "[autopiloto] ✗ agente desconocido: $agente" | tee -a "$LOG"; return 1; }
    local t0 t1 dur rc=0
    t0=$(date +%s%3N)
    case "$agente" in
        opencode)
            if [ -n "$modelo" ]; then
                timeout "$TIMEOUT_POR_TAREA" "$bin" run --agent "${OPENCODE_AGENT_TAREA:-build}" --model "$modelo" "$@" > "$salida" 2>&1
            else
                timeout "$TIMEOUT_POR_TAREA" "$bin" run --agent "${OPENCODE_AGENT_TAREA:-build}" "$@" > "$salida" 2>&1
            fi
            rc=$?
            ;;
        codex)
            timeout "$TIMEOUT_POR_TAREA" "$bin" exec --skip-git-repo-check "${CODEX_FLAGS:-}" "$@" > "$salida" 2>&1
            rc=$?
            ;;
        claude)
            timeout "$TIMEOUT_POR_TAREA" "$bin" -p --output-format text "${CLAUDE_FLAGS:-}" "$@" > "$salida" 2>&1
            rc=$?
            ;;
        *)
            echo "[autopiloto] ✗ agente desconocido: $agente" | tee -a "$LOG"
            return 1
            ;;
    esac
    t1=$(date +%s%3N)
    dur=$((t1 - t0))
    _registrar_metrica "$agente" "$modelo" "$dur" "$rc" "$salida"
    return $rc
}

_registrar_metrica() {
    local agente="$1" modelo="$2" dur_ms="$3" rc="$4" salida="$5"
    local metric_file="$PROYECTO/metrics.jsonl"
    local tokens_in=0 tokens_out=0 costo=0
    case "$agente" in
        opencode)
            local usage="$(grep -o '"usage":{"input_tokens":[0-9]*,"output_tokens":[0-9]*}' "$salida" 2>/dev/null | tail -1)"
            if [ -n "$usage" ]; then
                tokens_in=$(echo "$usage" | grep -o '"input_tokens":[0-9]*' | cut -d: -f2)
                tokens_out=$(echo "$usage" | grep -o '"output_tokens":[0-9]*' | cut -d: -f2)
            fi
            ;;
        codex)
            local usage="$(grep -o 'tokens_used: [0-9]*' "$salida" 2>/dev/null | tail -1)"
            if [ -n "$usage" ]; then
                tokens_out=$(echo "$usage" | cut -d' ' -f2)
            fi
            ;;
        claude)
            local usage="$(grep -o '"usage":{"input_tokens":[0-9]*,"output_tokens":[0-9]*}' "$salida" 2>/dev/null | tail -1)"
            if [ -n "$usage" ]; then
                tokens_in=$(echo "$usage" | grep -o '"input_tokens":[0-9]*' | cut -d: -f2)
                tokens_out=$(echo "$usage" | grep -o '"output_tokens":[0-9]*' | cut -d: -f2)
            fi
            ;;
    esac
    case "$modelo" in
        *opus*|*sonnet*|*haiku*) costo=$(awk -v ti="$tokens_in" -v to="$tokens_out" 'BEGIN{printf "%.6f", (ti*15 + to*75)/1000000}') ;;
        *gpt-4*|*gpt-4o*) costo=$(awk -v ti="$tokens_in" -v to="$tokens_out" 'BEGIN{printf "%.6f", (ti*30 + to*60)/1000000}') ;;
        *gpt-3.5*) costo=$(awk -v ti="$tokens_in" -v to="$tokens_out" 'BEGIN{printf "%.6f", (ti*0.5 + to*1.5)/1000000}') ;;
        *) costo=$(awk -v ti="$tokens_in" -v to="$tokens_out" 'BEGIN{printf "%.6f", (ti*1 + to*3)/1000000}') ;;
    esac
    printf '{"ts":"%s","iter":%s,"agente":"%s","modelo":"%s","dur_ms":%d,"rc":%d,"tokens_in":%d,"tokens_out":%d,"costo_usd":%.6f,"tarea":"%s"}\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${iter:-0}" "$agente" "${modelo:-default}" "$dur_ms" "$rc" "$tokens_in" "$tokens_out" "$costo" "${TAREA:-}" \
        >> "$metric_file"
}

# Navegador de contexto previo a la tarea (agnóstico de agente).
run_navegador() {
    local salida="$1" modelo="$2" tarea="$3" agente="${4:-$AGENTE_TAREA}" bin extra
    local prompt="Tarea: ${tarea}
Repo: ${PROYECTO}
Encuentra archivos, tests y endpoints relevantes. Lista concisa (máx 30 líneas):
ARCHIVOS: ruta/archivo.py
TESTS: ruta/test.py::test_x
ENDPOINTS: GET /api/...
MODELOS: Modulo.servicio"
    bin="$(cli_agente "$agente")"
    [ -n "$bin" ] || return 1
    local t0 t1 dur rc=0
    t0=$(date +%s%3N)
    case "$agente" in
        opencode)
            timeout "$TIMEOUT_NAVEGADOR" "$bin" run --agent "${OPENCODE_AGENT_NAV:-navigate}" --model "$modelo" "$prompt" > "$salida" 2>&1
            rc=$?
            ;;
        codex)
            timeout "$TIMEOUT_NAVEGADOR" "$bin" exec --skip-git-repo-check "$prompt" > "$salida" 2>&1
            rc=$?
            ;;
        claude)
            timeout "$TIMEOUT_NAVEGADOR" "$bin" -p --output-format text "$prompt" > "$salida" 2>&1
            rc=$?
            ;;
        *)
            return 1
            ;;
    esac
    t1=$(date +%s%3N)
    dur=$((t1 - t0))
    _registrar_metrica "$agente" "$modelo" "$dur" "$rc" "$salida"
    return $rc
}

elegir_revisor() {
    local preferido="${AGENTE_REVISOR:-}"
    local tarea="${AGENTE_TAREA:-}"
    local a
    for a in $preferido ${AGENTES_PREFERIDOS:-codex claude opencode}; do
        [ -z "$a" ] && continue
        agente_ok "$a" || continue
        [ "$a" != "$tarea" ] && { echo "$a"; return 0; }
    done
    [ -n "$preferido" ] && agente_ok "$preferido" && { echo "$preferido"; return 0; }
    agente_ok "$tarea" && { echo "$tarea"; return 0; }
    echo ""
}

revisar_diff() {
    local rev="$1" rev_out vdiff
    rev_out="$(mktemp)"
    # El diff que ve el revisor excluye los archivos CONTROL del framework:
    # plan.md, progreso.log, mapeo.txt, etc. son trazabilidad del propio
    # autopiloto (marca [x], escribe progreso) y no deben leerse como "cambios
    # ajenos" al alcance de la tarea (el commit ya los excluye con $CONTROL).
    # Además se marcan los archivos nuevos como intent-to-add (git add -N) para
    # que `git diff` los incluya; si no, el revisor solo veía archivos tracked.
    git -C "$PROYECTO" add -N -A 2>/dev/null
    local ARCHIVOS_DIFF
    ARCHIVOS_DIFF="$(git -C "$PROYECTO" diff --name-only | grep -vE "^($CONTROL)$")"
    if [ -n "$ARCHIVOS_DIFF" ]; then
        vdiff="$(git -C "$PROYECTO" diff --stat -- "$ARCHIVOS_DIFF"; echo '#----- diff (excluye archivos CONTROL del framework) -----#'; git -C "$PROYECTO" diff -- "$ARCHIVOS_DIFF")"
    else
        vdiff="(sin cambios fuera de archivos CONTROL)"
    fi
    local PROMPT_REV="Eres el REVISOR en modo autopiloto. Usa únicamente las skills que tu sesión ya tenga cargadas; no intentes cargar ninguna otra.
Revisas el diff COMPLETO de una tarea, en frío, sin haber participado de ella.
Tarea: ${TAREA}

${vdiff}

Evalúa SOLO: (1) la tarea satisface su criterio, (2) no rompe nada obvio del proyecto,
(3) sin secretos, (4) sin scope creep (cambios ajenos a la tarea).
Responde con 2 o 3 líneas de razones y, EN LA ÚLTIMA LÍNEA, exactamente: VERDICT: PASS o VERDICT: FAIL"
    run_agente "$rev" "$rev_out" "$MODELO_REVISOR" "$PROMPT_REV"
    cat "$rev_out" >> "$LOG"

    # Comprobar agotamiento de tokens/cuota en la salida del revisor
    if tokens_agotados "$rev_out"; then
        echo "[autopiloto] ✗ Tokens/cuota agotados del proveedor IA (revisor) — deteniendo loop" | tee -a "$LOG"
        logx "ABORTADO: tokens/cuota agotados (revisor)"
        alerta "Tokens agotados, se detiene el autopiloto"
        exit 5
    fi

    if grep -q "VERDICT: PASS" "$rev_out"; then
        echo "[autopiloto] ✔ revisor ($rev): PASS"
        grep -iE "VERDICT:" "$rev_out" | tail -1
        rm -f "$rev_out"
        REVISOR_FEEDBACK=""
        return 0
    fi
    echo "[autopiloto] ✗ revisor ($rev): FAIL"
    local veredicto_linea
    veredicto_linea="$(grep -iE "VERDICT:" "$rev_out" | tail -1)"
    echo "$veredicto_linea"
    # Extraer feedback (todo lo que está antes del VERDICT)
    REVISOR_FEEDBACK="$(sed -n '1,/VERDICT:/p' "$rev_out" | head -n -1 | sed '/^\s*$/d' | paste -sd ' ' -)"
    rm -f "$rev_out"
    return 1
}

snapshot() {
    # Excluye compilados/caches (pág. .gitignore) para que nunca entren en el
    # diff ni se commiteen aunque el proyecto no tenga .gitignore.
    git -C "$PROYECTO" status --porcelain \
        | sed 's/^...//' \
        | grep -vE '(^|/)(__pycache__|\.pytest_cache|\.mypy_cache|node_modules|\.venv|venv)/|\.pyc$|\.pyo$' \
        | sort > "$1"
}

revertir() {
    comm -13 <(sort "$1") <(sort "$2") \
        | grep -vE "^($CONTROL)$" \
        | while IFS= read -r f; do
            git -C "$PROYECTO" checkout -- "$f" 2>/dev/null
            rm -rf "$f" 2>/dev/null
        done
}

# Memoria del proyecto: añade una lección a lecciones.md (corrección única de
# errores). La usa el agente en la siguiente tarea para no repetir el fallo.
registrar_leccion() {
    local titulo="$1" sintoma="$2" causa="$3" prevencion="$4"
    {   printf '\n## %s — %s\n- Síntoma: %s\n- Causa: %s\n- Prevención: %s\n' \
            "$(date '+%Y-%m-%d %H:%M')" "$titulo" "$sintoma" "$causa" "$prevencion"
    } >> "$LECCIONES"
}

proxima_tarea() {
    local l
    while IFS= read -r l || [ -n "$l" ]; do
        if [[ "$l" == "- [ ] "* ]]; then
            echo "${l#- \[ \] }"
            return 0
        fi
    done < "$PLAN"
    return 1
}

# Devuelve el criterio de aceptación de la PRIMERA tarea pendiente (- [ ]).
# Formato del plan.md: línea "criterio: ..." indentada bajo la tarea.
criterio_tarea() {
    local l en_tarea=0
    while IFS= read -r l || [ -n "$l" ]; do
        if [[ "$l" == "- [ ] "* ]]; then
            # Criterio inline en la misma línea de la tarea
            if [[ "$l" =~ criterio:[[:space:]]+(.*)$ ]]; then
                echo "${BASH_REMATCH[1]}"
                return 0
            fi
            en_tarea=1
            continue
        fi
        if [[ "$l" == "- ["* ]]; then
            [ "$en_tarea" -eq 1 ] && return 1
            continue
        fi
        if [ "$en_tarea" -eq 1 ]; then
            # Línea sin indentar corta el bloque de la tarea
            [[ "$l" =~ ^[[:space:]] ]] || return 1
            if [[ "$l" =~ criterio:[[:space:]]*(.*)$ ]]; then
                echo "${BASH_REMATCH[1]}"
                return 0
            fi
        fi
    done < "$PLAN"
    return 1
}

esperar_revision_manual() {
    # Solo si REVISION_MANUAL=1
    [ "$REVISION_MANUAL" = "1" ] || return 0

    local dir_revision="$PROYECTO/.autopiloto_review"
    mkdir -p "$dir_revision"

    # Escribir diff y tarea para la GUI
    git -C "$PROYECTO" diff --stat > "$dir_revision/diff.txt"
    git -C "$PROYECTO" diff >> "$dir_revision/diff.txt"
    echo "$TAREA" > "$dir_revision/tarea.txt"
    echo "waiting" > "$dir_revision/waiting"

    echo "[autopiloto] ⏸ Esperando revisión manual en $dir_revision..."
    logx "ESPERANDO REVISIÓN MANUAL: $TAREA"

    local decision=""
    while [ ! -f "$dir_revision/decision" ]; do
        sleep 2
    done
    decision="$(cat "$dir_revision/decision")"
    rm -f "$dir_revision/waiting" "$dir_revision/decision"

    case "$decision" in
        APPROVE*)
            echo "[autopiloto] ✔ Diff aprobado manualmente"
            logx "REVISIÓN MANUAL: APROBADO"
            return 0
            ;;
        REJECT*)
            local motivo="${decision#REJECT}"
            motivo="${motivo#$'\n'}"
            echo "[autopiloto] ✗ Diff rechazado: $motivo"
            logx "REVISIÓN MANUAL: RECHAZADO - $motivo"
            RECHAZO_MOTIVO="$motivo"
            return 1
            ;;
        *)
            echo "[autopiloto] ⚠ Decisión desconocida: $decision"
            return 1
            ;;
    esac
}

# ---- Autodetección de agente si no se especificó ----
if [ -z "$AGENTE_TAREA" ]; then
    AGENTE_TAREA="$(detectar_agente)"
    if [ -z "$AGENTE_TAREA" ]; then
        echo "[autopiloto] ✗ No se encontró ningún agente (opencode, codex, claude)." | tee -a "$LOG"
        exit 2
    fi
fi

# Antes de lanzar el loop: si el binario del agente no existe, abortar ya.
if ! agente_ok "$AGENTE_TAREA"; then
    BIN="$(cli_agente "$AGENTE_TAREA")"
    echo "[autopiloto] ✗✗ agente '$AGENTE_TAREA' no encontrado (busqué '$BIN')." \
         "Instálalo o configura el PATH (o CLI_${AGENTE_TAREA^^}) y relanza." | tee -a "$LOG"
    logx "ABORTADO: agente no disponible ($AGENTE_TAREA)"
    exit 2
fi

REVISOR="$(elegir_revisor)"
COSTO_TOTAL=0
RECHAZO_MOTIVO=""
logx "== AUTOPILOTO INICIADO (agente=$AGENTE_TAREA, modelo=$MODELO_TAREA, revisor=${REVISOR:-ninguno}, modelo_rev=$MODELO_REVISOR, dual=$REVISION_DUAL, manual=$REVISION_MANUAL, max_iter=$MAX_ITER, hasta=${HASTA:-sin limite}, base=$RAMA_BASE, costo_max=$MAX_COSTO) =="

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

# --- Rama de trabajo (--trabajo): dónde se hace el trabajo real ---
#   · si coincide con la rama principal (master/main) → se trabaja ahí mismo
#   · si no existe → se crea desde la rama base (padre)
#   · si existe (local u origin) → se usa tal cual
#   · si la borran a mitad del run → se vuelve a la rama base para terminar
if [[ -n "${RAMA_TRABAJO:-}" && "$RAMA_TRABAJO" != "$RAMA_RUN" ]]; then
    if [[ "$RAMA_TRABAJO" == "master" || "$RAMA_TRABAJO" == "main" ]]; then
        git -C "$PROYECTO" checkout -q "$RAMA_TRABAJO" 2>/dev/null \
            || git -C "$PROYECTO" checkout -q -b "$RAMA_TRABAJO" "$RAMA_RUN"
        echo "[autopiloto] Trabajando en la rama principal $RAMA_TRABAJO (sin rama paralela)"
    elif git -C "$PROYECTO" rev-parse --verify -q "$RAMA_TRABAJO" >/dev/null 2>&1; then
        git -C "$PROYECTO" checkout -q "$RAMA_TRABAJO"
        echo "[autopiloto] Trabajando en la rama existente $RAMA_TRABAJO"
    elif git -C "$PROYECTO" rev-parse --verify -q "origin/$RAMA_TRABAJO" >/dev/null 2>&1; then
        git -C "$PROYECTO" checkout -q -b "$RAMA_TRABAJO" "origin/$RAMA_TRABAJO"
        echo "[autopiloto] Trabajando en $RAMA_TRABAJO (seguimiento de origin/$RAMA_TRABAJO)"
    else
        git -C "$PROYECTO" checkout -q -b "$RAMA_TRABAJO" "$RAMA_RUN"
        echo "[autopiloto] Creada la rama de trabajo $RAMA_TRABAJO (desde $RAMA_RUN)"
    fi
    logx "Rama de trabajo: $RAMA_TRABAJO"
else
    RAMA_TRABAJO="$RAMA_RUN"
    logx "Rama de trabajo (default): $RAMA_TRABAJO"
fi

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
    COSTO_ITER_ACTUAL=0
    RAMA_TAREA="autopiloto/tareas/$FECHA/t$iter"
    CRITERIO="$(criterio_tarea || true)"
    logx "== Iteración $iter: $TAREA (rama $RAMA_TAREA)${CRITERIO:+ | criterio: $CRITERIO} =="
    echo "[autopiloto] [$iter/$MAX_ITER] $TAREA -> $RAMA_TAREA"
    [ -n "$CRITERIO" ] && echo "[autopiloto]   criterio: $CRITERIO"

    git -C "$PROYECTO" checkout -q "$RAMA_RUN" 2>/dev/null
    if git -C "$PROYECTO" rev-parse --verify -q "$RAMA_TAREA" >/dev/null 2>&1 \
            && [ "$(git -C "$PROYECTO" branch --show-current)" != "$RAMA_TAREA" ]; then
        git -C "$PROYECTO" branch -q -D "$RAMA_TAREA"
        echo "[autopiloto] ⚠ rama huérfana $RAMA_TAREA eliminada (run anterior)"
    fi
    git -C "$PROYECTO" checkout -q -b "$RAMA_TAREA" "$RAMA_RUN"
    BEFORE="$(mktemp)"; AFTER="$(mktemp)"; OUT="$(mktemp)"
    snapshot "$BEFORE"

    hecho=0
    for intento in $(seq 1 "$MAX_REINTENTOS"); do
        PRE=""
        [ "$intento" -gt 1 ] && PRE="El intento anterior no pasó la verificación: no repitas tu cambio, corrígelo. "
        COSTO_ITER_ACTUAL="$(awk -v t="$COSTO_ITER_ACTUAL" -v a="$COSTO_POR_ITER" 'BEGIN{printf "%.2f", t+a}')"

        # --- MEMORIA DEL PROYECTO (corrección única de errores) ---
        LECCIONES_CONTEXTO=""
        if [ -f "$LECCIONES" ] && [ -s "$LECCIONES" ]; then
            LECCIONES_CONTEXTO="$(cat "$LECCIONES")"
        fi

        # --- NAVEGADOR AUTOMÁTICO (busca contexto antes de la tarea) ---
        if [ "$NAVEGADOR" = "1" ] && agente_ok "$AGENTE_TAREA" && [ -n "$MODELO_NAVEGADOR" ]; then
            NAV_OUT="$(mktemp)"
            run_navegador "$NAV_OUT" "$MODELO_NAVEGADOR" "$TAREA" "$AGENTE_TAREA"
            if [ -s "$NAV_OUT" ]; then
                NAV_CONTEXTO="$(cat "$NAV_OUT")"
            else
                NAV_CONTEXTO=""
            fi
            rm -f "$NAV_OUT"
        else
            NAV_CONTEXTO=""
        fi

        PROMPT="Estás en MODO AUTOPILOTO. Usa únicamente las skills que tu sesión ya tenga cargadas; no intentes cargar ninguna otra.
Tarea actual (solo esta): ${TAREA}
${PRE}Criterio de aceptación que debe cumplir tu trabajo (el gate lo verificará): ${CRITERIO:-<sin criterio explícito; usa los tests/mapeo.txt como contrato>}
Lee plan.md y progreso.log antes de tocar nada. Lee también mapeo.txt (mapa módulos→tests): localiza el/los test del código que vas a tocar y úsalos como contrato.
${NAV_CONTEXTO}${LECCIONES_CONTEXTO:+MEMORIA DEL PROYECTO (lecciones aprendidas, evita repetir estos errores):
${LECCIONES_CONTEXTO}
}
Ejecuta ÚNICAMENTE esta tarea.
NO hagas commits, NO crees, cambies ni borres ramas: el script gestiona git.
NO edites autopiloto.sh, gate.sh, mapear.sh, mapeo.txt, plan.md, progreso.log, lecciones.md, endpoints.txt, .env ni SECURITY.md.
Al terminar, responde con un resumen conciso de qué cambiaste y qué tests corriste."

        run_agente "$AGENTE_TAREA" "$OUT" "$MODELO_TAREA" "$PROMPT"
        rc=$?
        if [ "$rc" -eq 124 ]; then
            echo "[autopiloto] ⚠ timeout: ${AGENTE_TAREA} tardó más de ${TIMEOUT_POR_TAREA}s" | tee -a "$LOG"
            alerta "Tiempo agotado en una tarea"
        elif [ "$rc" -eq 126 ] || [ "$rc" -eq 127 ]; then
            # El binario del agente no existe o no es ejecutable: sin agente no
            # hay loop. Antes se seguía y se marcaba la tarea [x] sin trabajo.
            echo "[autopiloto] ✗✗ ${AGENTE_TAREA} no se pudo ejecutar (rc=$rc):" \
                 "binario no encontrado o sin permisos de ejecución." | tee -a "$LOG"
            logx "ABORTADO: agente no ejecutable (rc=$rc)"
            alerta "El agente no se pudo ejecutar; revisa PATH/instalación"
            exit 6
        elif [ "$rc" -ne 0 ]; then
            echo "[autopiloto] ⚠ ${AGENTE_TAREA} salió con rc=$rc" | tee -a "$LOG"
        fi
        cat "$OUT" >> "$LOG"
        cat "$OUT"

        # Comprobar agotamiento de tokens/cuota en la salida del agente
        if tokens_agotados "$OUT"; then
            echo "[autopiloto] ✗ Tokens/cuota agotados del proveedor IA — deteniendo loop" | tee -a "$LOG"
            logx "ABORTADO: tokens/cuota agotados"
            alerta "Tokens agotados, se detiene el autopiloto"
            exit 5
        fi

        # Snapshot del árbol tras el agente: permite revertir este intento
        # si el revisor dual o la revisión manual lo rechazan.
        snapshot "$AFTER"

        if [ "$(git -C "$PROYECTO" branch --show-current)" != "$RAMA_TAREA" ]; then
            echo "[autopiloto] ✗✗ el agente cambió de rama. Abortando: requiere revisión humana." | tee -a "$LOG"
            logx "ABORTADO: se detectó cambio de rama no autorizado"
            alerta "El agente cambió de rama, se aborta el run"
            exit 3
        fi

        # CRITERIO y MODELO_JUEZ viajan al gate (los lee 98_criterio.sh)
        export CRITERIO MODELO_JUEZ OPENCODE_AGENT_JUEZ
        logx "GATE: ejecutando gate.sh (intento $intento)"
        GATE_OUT="$(mktemp)"
        # tee: la salida del gate se ve en vivo Y se guarda para el feedback
        if bash "$GATE" 2>&1 | tee "$GATE_OUT"; then
            if [ "$REVISION_DUAL" = "1" ] && [ -n "$REVISOR" ]; then
                COSTO_ITER_ACTUAL="$(awk -v t="$COSTO_ITER_ACTUAL" -v a="$COSTO_POR_ITER" 'BEGIN{printf "%.2f", t+a/2}')"
                if revisar_diff "$REVISOR"; then
                    # Gate dual pasó, ahora verificar revisión manual si está activada
                    if esperar_revision_manual; then
                        hecho=1
                        break
                    else
                        # Rechazado: revertir cambios antes de reintentar
                        revertir "$BEFORE" "$AFTER"
                        PRE="El diff fue rechazado en revisión manual: ${RECHAZO_MOTIVO}. Corrige esto en tu siguiente intento. "
                        logx "REVISIÓN MANUAL RECHAZADO, reintentando..."
                    fi
                else
                    logx "REVISOR FAIL (intento $intento)"
                    echo "[autopiloto] ✗ el revisor rechazó el diff (intento $intento/$MAX_REINTENTOS)"
                    # Inyectar feedback del revisor en el siguiente intento
                    if [ -n "$REVISOR_FEEDBACK" ]; then
                        PRE="El revisor rechazó el diff anterior: ${REVISOR_FEEDBACK}. Corrige esto en tu siguiente intento. "
                        logx "Feedback del revisor inyectado para siguiente intento"
                    fi
                fi
            else
                # Sin gate dual, verificar revisión manual
                if esperar_revision_manual; then
                    hecho=1
                    break
                else
                    revertir "$BEFORE" "$AFTER"
                    PRE="El diff fue rechazado en revisión manual: ${RECHAZO_MOTIVO}. Corrige esto en tu siguiente intento. "
                    logx "REVISIÓN MANUAL RECHAZADO, reintentando..."
                fi
            fi
        else
            logx "GATE FALLÓ tras el agente (intento $intento)"
            echo "[autopiloto] ✗ la tarea no pasó el gate (intento $intento/$MAX_REINTENTOS)"
            # Capturar la salida del gate para dársela al agente en el
            # siguiente intento (patrón "pipe_output"): que sepa QUÉ falló.
            cat "$GATE_OUT" >> "$LOG"
            GATE_FEEDBACK="$(grep -vE '^\[GATE\] (✓|⚠)' "$GATE_OUT" | tail -15 | tr '\n' ' ' | cut -c1-500)"
            if [ -n "$GATE_FEEDBACK" ]; then
                PRE="El gate falló con: ${GATE_FEEDBACK}. El detalle completo está en progreso.log. Corrige esto en tu siguiente intento. "
                logx "Feedback del gate inyectado para siguiente intento"
            fi
        fi
        rm -f "$GATE_OUT"
    done

    logx "Costo iteración ${iter}: ${COSTO_ITER_ACTUAL} USD"
    snapshot "$AFTER"

    if [ "$hecho" -eq 1 ]; then
        CHANGED="$(comm -13 <(sort "$BEFORE") <(sort "$AFTER") | grep -vE "^($CONTROL)$")"
        if [ -n "$CHANGED" ]; then
            # Subject corto (<50 chars, pág. git) + cuerpo con la tarea completa
            SUBJETO="autopiloto: $(printf '%s' "$TAREA" | cut -c1-40)"
            if ( cd "$PROYECTO" && git add -- $CHANGED && git commit -q -m "$SUBJETO" -m "$TAREA" ); then
                logx "commit en $RAMA_TAREA: $SUBJETO"
                echo "[autopiloto] ✔ commit: $SUBJETO"
            fi
        else
            logx "tarea completada sin cambios nuevos"
            echo "[autopiloto] ✔ tarea completada sin cambios nuevos"
        fi
        if git -C "$PROYECTO" checkout -q "$RAMA_RUN" \
            && git -C "$PROYECTO" merge -q --ff-only "$RAMA_TAREA" 2>/dev/null; then
            git -C "$PROYECTO" branch -q -d "$RAMA_TAREA"
            logx "mergeada $RAMA_TAREA -> $RAMA_RUN"
            # Actualizar mapeo.txt automáticamente tras tarea completada
            bash "$MAPEAR" > "$MAPA" 2>/dev/null && logx "mapeo.txt actualizado tras $TAREA"
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
        registrar_leccion \
            "Tarea bloqueada: ${TAREA}" \
            "El agente no cumplió el criterio tras $MAX_REINTENTOS intentos." \
            "gate.sh/revisor fallaron en la iteración ${iter}." \
            "Reformular la tarea en plan.md, dividirla en pasos más pequeños o revisar los criterios."
        logx "lección registrada en lecciones.md (tarea bloqueada)"
    fi

    COSTO_TOTAL="$(awk -v t="$COSTO_TOTAL" -v a="$COSTO_POR_ITER" 'BEGIN{printf "%.2f", t+a}')"
    logx "Costo estimado acumulado: $COSTO_TOTAL USD"
    echo "[autopiloto] 💰 Costo estimado acumulado: ${COSTO_TOTAL} USD"

    rm -f "$BEFORE" "$AFTER" "$OUT"
done

# --- Integrar el trabajo en la rama destino (--trabajo distinta de la run) ---
# El loop commitea en RAMA_RUN (rama base del run); si se pidió trabajar en
# otra rama, se deja todo el run integrado allí al terminar.
if [ -n "${RAMA_TRABAJO:-}" ] && [ "$RAMA_TRABAJO" != "$RAMA_RUN" ]; then
    echo "[autopiloto] Integrando $RAMA_RUN -> $RAMA_TRABAJO"
    if git -C "$PROYECTO" checkout -q "$RAMA_TRABAJO" && \
       git -C "$PROYECTO" merge -q --no-ff "$RAMA_RUN" -m "autopiloto: integrar $RAMA_RUN" 2>/dev/null; then
        logx "integrado $RAMA_RUN -> $RAMA_TRABAJO"
    else
        echo "[autopiloto] ⚠ no se pudo integrar en $RAMA_TRABAJO; el trabajo queda en $RAMA_RUN" | tee -a "$LOG"
    fi
fi

# Intentar crear repo en GitHub si hay token y no hay remote origin
_asegurar_remote_origin() {
    if ! git -C "$PROYECTO" remote get-url origin >/dev/null 2>&1; then
        local token="${GITHUB_TOKEN:-}"
        if [ -z "$token" ] && command -v gh >/dev/null 2>&1; then
            token="$(gh auth token 2>/dev/null || echo "")"
        fi
        if [ -n "$token" ]; then
            local repo_name="$(basename "$PROYECTO")"
            local owner="$(curl -s -H "Authorization: Bearer $token" https://api.github.com/user | grep -o '"login":"[^"]*"' | cut -d'"' -f4)"
            if [ -n "$owner" ]; then
                echo "[autopiloto] Creando repo GitHub: $owner/$repo_name ..."
                local create_resp="$(curl -s -X POST -H "Authorization: Bearer $token" \
                    -H "Accept: application/vnd.github+json" \
                    "https://api.github.com/user/repos" \
                    -d "{\"name\":\"$repo_name\",\"private\":true,\"auto_init\":false}")"
                if echo "$create_resp" | grep -q '"ssh_url"'; then
                    local ssh_url="$(echo "$create_resp" | grep -o '"ssh_url":"[^"]*"' | cut -d'"' -f4)"
                    git -C "$PROYECTO" remote add origin "$ssh_url"
                    logx "repo creado y remote origin configurado: $ssh_url"
                    echo "[autopiloto] ✔ repo creado en GitHub: $owner/$repo_name"
                    return 0
                fi
            fi
            echo "[autopiloto] ⚠ no se pudo crear repo (respuesta API: $create_resp)" | tee -a "$LOG"
        else
            registrar_leccion \
                "GitHub: remote origin ausente" \
                "No hay GITHUB_TOKEN ni 'gh auth token' para crear repo automático." \
                "Crea el repo manualmente en GitHub y ejecuta: git remote add origin <url>"
            logx "lección registrada: remote origin ausente (sin credenciales)"
        fi
    fi
}

if [ -n "$PUSH" ]; then
    _asegurar_remote_origin
    PUSH_RAMA="${RAMA_TRABAJO:-$RAMA_RUN}"
    if git -C "$PROYECTO" remote get-url origin >/dev/null 2>&1; then
        if git -C "$PROYECTO" push -u origin "$PUSH_RAMA"; then
            logx "push: origin/$PUSH_RAMA"
            echo "[autopiloto] ✔ push OK: origin/$PUSH_RAMA"
            if [ "$PUSH_RAMA" != "$RAMA_RUN" ]; then
                echo "[autopiloto] abre el PR de $PUSH_RAMA -> $RAMA_BASE"
            else
                echo "[autopiloto] abre el PR de $RAMA_RUN -> $RAMA_BASE"
            fi
        else
            echo "[autopiloto] ⚠ falló el push a origin/$PUSH_RAMA. El trabajo queda local." | tee -a "$LOG"
        fi
    else
        echo "[autopiloto] ℹ sin remote origin (repo no creado). Trabajo queda local." | tee -a "$LOG"
    fi
fi

echo ""
echo "== RESUMEN (final de progreso.log) =="
tail -25 "$LOG"
logx "== AUTOPILOTO FINALIZADO (iter=$iter, rama=$RAMA_RUN, costo≈$COSTO_TOTAL) =="
alerta "Autopiloto finalizado"
exit 0