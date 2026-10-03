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
#   TIMEOUT_REVISION_MANUAL  segundos máximos esperando la aprobación manual antes
#                     de marcar la tarea [B] y seguir (0 = esperar indefinidamente). def: 1800.
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

# Este script escribe JSON (metrics.jsonl) y hace aritmética con decimales, así
# que NO debe depender del locale del usuario: con es_ES, bash y awk imprimen
# "0,500000" y "printf" rechaza "0.500000" ("número no válido"), lo que dejaba
# metrics.jsonl como JSON inválido y el tope de coste sin contar.
# LC_ALL=C no cambia ningún formato que usemos (fechas numéricas) y hace
# comparables los `sort` de listas de ficheros.
export LC_ALL=C

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
TIMEOUT_REVISION_MANUAL="${TIMEOUT_REVISION_MANUAL:-1800}"
VOZ="${VOZ:-0}"
MAX_COSTO="${MAX_COSTO:-0}"
COSTO_POR_ITER="${COSTO_POR_ITER:-0.50}"
RAMA_BASE="${RAMA_BASE:-master}"
PUSH=""
HASTA=""
CONTROL="plan\.md|lecciones\.md|progreso\.log|gate\.sh|autopiloto\.sh|mapear\.sh|mapeo\.txt|endpoints\.txt|metrics\.jsonl|gate_checks(/.*)?|\.autopiloto_review(/.*)?"

# ---------------------------------------------------------------------------
# Utilidades POSIX (funcionan igual en GNU/Linux y en BSD/macOS)
# ---------------------------------------------------------------------------

# awk con locale C para formatear decimales. Necesario aunque el script ya
# exporte LC_ALL=C: si el script se sourcea desde otro proceso con su propio
# LC_ALL, la precedencia se invierte. OJO: `export LC_NUMERIC=C` NO sirve,
# porque LC_ALL tiene prioridad sobre LC_NUMERIC en los procesos hijos.
num() { LC_ALL=C awk "$@"; }

# Epoch en milisegundos. GNU `date +%s%3N` da nanosegundos; el date de BSD no
# conoce %N y devuelve el literal "%3N", así que se detecta y se degrada a
# perl (Time::HiRes) o a segundos con sufijo de ceros.
ahora_ms() {
    local ns
    ns="$(date +%s%3N 2>/dev/null || true)"
    case "$ns" in
        ''|*%N*) ns="" ;;
    esac
    if [ -n "$ns" ]; then printf '%s\n' "$ns"; return 0; fi
    if command -v perl >/dev/null 2>&1; then
        perl -MTime::HiRes=time -e 'printf "%d\n", time * 1000' 2>/dev/null && return 0
    fi
    printf '%s000\n' "$(date +%s)"
}

# `ping -W` significa SEGUNDOS en GNU y MILISEGUNDOS en BSD: se decide una vez
# según el SO para no dejar un ping colgado 2000 s en Linux.
PING_FLAGS="-c1 -W2"
case "$(uname -s 2>/dev/null || echo unknown)" in
    Darwin) PING_FLAGS="-c1 -W2000" ;;
esac

un_ping() {
    command -v ping >/dev/null 2>&1 || return 1
    # shellcheck disable=SC2086
    ping $PING_FLAGS 8.8.8.8 >/dev/null 2>&1
}

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

# Marca de inicio del run (epoch ms) para la limpieza de sesiones de opencode.
INICIO_MS="$(ahora_ms)"
SESIONES_LIMPIADAS=0

logx() { echo "[$(date '+%F %H:%M:%S')] $*" >> "$LOG"; }
hora_limite() { [[ -n "$HASTA" && "$(date +%H:%M)" > "$HASTA" ]]; }

hay_internet() {
    local i
    for i in 1 2 3; do
        un_ping && return 0
        # Si no hay binario `ping` (o está capado por permisos), probar HTTP.
        if ! command -v ping >/dev/null 2>&1; then
            command -v curl >/dev/null 2>&1 \
                && curl -s -m 3 https://1.1.1.1 >/dev/null 2>&1 && return 0
        fi
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

# Detecta si la salida del agente es "no autenticado / sin credenciales".
# Un CLI instalado pero sin sesión (p. ej. `claude` sin /login) devuelve un
# mensaje, NO un error de código: el loop lo marcaría [B] en bucle. Se
# distingue de la cuota agotada (tokens_agotados) para dar un mensaje útil.
sin_autenticacion() {
    local archivo="$1"
    grep -qiE \
        -e "not logged in" \
        -e "please run /login" \
        -e "not authenticated" \
        -e "unauthorized" \
        -e "401" \
        -e "authentication_error" \
        -e "invalid.?api.?key" \
        -e "missing.?api.?key" \
        -e "OPENAI_API_KEY" \
        -e "ANTHROPIC_API_KEY" \
        -e "please set your api key" \
        -e "run .codex login" \
        "$archivo" >/dev/null 2>&1
}

# Detecta el primer agente disponible (opencode -> codex -> claude).
# El orden y los binarios son configurables:
#   AGENTES_PREFERIDOS="codex opencode"  (orden de preferencia)
#   CLI_OPENCODE/CLI_CODEX/CLI_CLAUDE      (binario de cada agente)
detectar_agente() {
    local i
    for i in ${AGENTES_PREFERIDOS:-opencode codex claude}; do
        [ "$i" = "auto" ] && continue
        # agente_ok, NO cli_agente: este último sólo devuelve el nombre y
        # siempre sale con rc=0, así que "detectaba" el primero de la lista
        # aunque no estuviera instalado (y luego el agente_ok final abortaba).
        agente_ok "$i" && { echo "$i"; return 0; }
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

# Limpia las sesiones de opencode que este run haya creado en el proyecto.
# Criterio: directory == PROYECTO y time_created >= INICIO_MS del run.
# Se ejecuta al salir (loop completo, break, error o detención manual).
limpiar_sesiones() {
    local bin ids id n=0
    bin="$(cli_agente opencode)"
    [ -n "$bin" ] || return 0
    command -v "$bin" >/dev/null 2>&1 || return 0
    command -v jq >/dev/null 2>&1 || return 0
    ids="$("$bin" session list --format json 2>/dev/null | jq -r \
        --arg dir "$PROYECTO" --argjson desde "$INICIO_MS" \
        '.[] | select(.directory == $dir and .created >= $desde) | .id')"
    [ -n "$ids" ] || return 0
    while IFS= read -r id; do
        [ -z "$id" ] && continue
        "$bin" session delete "$id" >/dev/null 2>&1
        n=$((n + 1))
    done <<< "$ids"
    SESIONES_LIMPIADAS=$n
    [ "$n" -gt 0 ] && echo "[autopiloto] 🧹 Sesiones opencode eliminadas: $n" | tee -a "$LOG"
}
trap limpiar_sesiones EXIT TERM INT

# Ejecuta una tarea con cualquier agente. Devuelve su exit code.
#   $1 = agente (opencode|codex|claude)
#   $2 = archivo salida
#   $3 = modelo (sólo opencode; vacío = usa config)
#   "$@" = prompt (string)
run_agente() {
    local agente="$1" salida="$2" modelo="${3:-}" bin
    shift 3
    # "auto" aquí solo llega si alguien invoca run_agente directamente: se
    # resuelve como el agente de tarea ya detectado (o el primero disponible).
    if [ -z "$agente" ] || [ "$agente" = "auto" ]; then
        agente="${AGENTE_TAREA:-}"
        [ -z "$agente" ] || [ "$agente" = "auto" ] && agente="$(detectar_agente)"
    fi
    bin="$(cli_agente "$agente")"
    [ -n "$bin" ] || { echo "[autopiloto] ✗ agente desconocido: $agente" | tee -a "$LOG"; return 1; }
    local t0 t1 dur rc=0
    t0=$(ahora_ms)
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
            # OJO: los flags van en un array. "${CODEX_FLAGS:-}" entrecomillado
            # añadiría un argumento VACÍO al final y el CLI lo tomaría como el
            # prompt, dejando el prompt real como segundo posicional.
            local -a flags=()
            [ -n "${CODEX_FLAGS:-}" ] && read -r -a flags <<< "$CODEX_FLAGS"
            timeout "$TIMEOUT_POR_TAREA" "$bin" exec --skip-git-repo-check \
                ${flags[@]+"${flags[@]}"} "$@" > "$salida" 2>&1
            rc=$?
            ;;
        claude)
            local -a flags=()
            [ -n "${CLAUDE_FLAGS:-}" ] && read -r -a flags <<< "$CLAUDE_FLAGS"
            timeout "$TIMEOUT_POR_TAREA" "$bin" -p --output-format text \
                ${flags[@]+"${flags[@]}"} "$@" > "$salida" 2>&1
            rc=$?
            ;;
        *)
            echo "[autopiloto] ✗ agente desconocido: $agente" | tee -a "$LOG"
            return 1
            ;;
    esac
    t1=$(ahora_ms)
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
        *opus*|*sonnet*|*haiku*) costo=$(num -v ti="$tokens_in" -v to="$tokens_out" 'BEGIN{printf "%.6f", (ti*15 + to*75)/1000000}') ;;
        *gpt-4*|*gpt-4o*) costo=$(num -v ti="$tokens_in" -v to="$tokens_out" 'BEGIN{printf "%.6f", (ti*30 + to*60)/1000000}') ;;
        *gpt-3.5*) costo=$(num -v ti="$tokens_in" -v to="$tokens_out" 'BEGIN{printf "%.6f", (ti*0.5 + to*1.5)/1000000}') ;;
        *) costo=$(num -v ti="$tokens_in" -v to="$tokens_out" 'BEGIN{printf "%.6f", (ti*1 + to*3)/1000000}') ;;
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
    t0=$(ahora_ms)
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
    t1=$(ahora_ms)
    dur=$((t1 - t0))
    _registrar_metrica "$agente" "$modelo" "$dur" "$rc" "$salida"
    return $rc
}

elegir_revisor() {
    local preferido="${AGENTE_REVISOR:-}"
    local tarea="${AGENTE_TAREA:-}"
    local a
    # Elección explícita (la GUI envía el agente detectado al resolver "auto"):
    # gana aunque sea el mismo que implementa, porque es lo que pidió el
    # usuario; no lo sustituimos por otro.
    if [ -n "$preferido" ] && [ "$preferido" != "auto" ]; then
        agente_ok "$preferido" && { echo "$preferido"; return 0; }
    fi
    # "auto" o vacío = ojos frescos: otro agente distinto al de tarea.
    for a in ${AGENTES_PREFERIDOS:-codex claude opencode}; do
        [ -z "$a" ] && continue
        [ "$a" = "auto" ] && continue
        agente_ok "$a" || continue
        [ "$a" != "$tarea" ] && { echo "$a"; return 0; }
    done
    # Sólo hay un agente disponible: que revise el mismo que implementó, o el
    # gate se quedaría sin revisión.
    agente_ok "$tarea" && { echo "$tarea"; return 0; }
    echo ""
}

diff_revision() {
    # Diff de la iteración para el revisor, excluyendo los archivos CONTROL
    # del framework (plan.md, progreso.log, mapeo.txt…): son trazabilidad del
    # propio autopiloto, no "cambios ajenos" a la tarea.
    # Los archivos nuevos se marcan intent-to-add (git add -N) para que
    # `git diff` los incluya; si no, el revisor sólo veía archivos tracked.
    local -a archivos=()
    local linea
    git -C "$PROYECTO" add -N -A 2>/dev/null
    # OJO: las rutas van como pathspec SEPARADOS. Pasar la lista multilínea
    # como un único argumento entrecomillado ("$ARCHIVOS_DIFF") la convierte en
    # un pathspec literal con saltos de línea, que no casa con ningún fichero:
    # con dos o más ficheros modificados el revisor recibía un diff VACÍO y
    # aprobaba sin haber visto nada. Ver tests/test_revisor_diff.py.
    # Y OJO: `read -a` parte por espacios SÓLO la línea que lee, así que con
    # `<<<` sobre una lista multilínea se quedaría con el primer fichero.
    while IFS= read -r linea; do
        [ -n "$linea" ] || continue
        archivos+=("$linea")
    done < <(git -C "$PROYECTO" diff --name-only | grep -vE "^($CONTROL)$")
    if [ ${#archivos[@]} -eq 0 ]; then
        echo "(sin cambios fuera de archivos CONTROL)"
        return 0
    fi
    git -C "$PROYECTO" diff --stat -- ${archivos[@]+"${archivos[@]}"}
    echo '#----- diff (excluye archivos CONTROL del framework) -----#'
    git -C "$PROYECTO" diff -- ${archivos[@]+"${archivos[@]}"}
}

revisar_diff() {
    local rev="$1" rev_out vdiff
    rev_out="$(mktemp)"
    vdiff="$(diff_revision)"
    local PROMPT_REV="Eres el REVISOR en modo autopiloto. Usa únicamente las skills que tu sesión ya tenga cargadas; no intentes cargar ninguna otra.
Revisas el diff COMPLETO de una tarea, en frío, sin haber participado de ella.
Tarea: ${TAREA}

${vdiff}

Evalúa SOLO: (1) la tarea satisface su criterio, (2) no rompe nada obvio del proyecto,
(3) sin secretos, (4) sin scope creep (cambios ajenos a la tarea).
Responde con 2 o 3 líneas de razones y, EN LA ÚLTIMA LÍNEA, exactamente: VERDICT: PASS o VERDICT: FAIL"
    run_agente "$rev" "$rev_out" "$MODELO_REVISOR" "$PROMPT_REV"
    cat "$rev_out" >> "$LOG"

    # El revisor sin sesión: mismo criterio que el agente de tarea.
    if sin_autenticacion "$rev_out"; then
        echo "[autopiloto] ✗✗ revisor ($rev) no está autenticado — deteniendo loop" | tee -a "$LOG"
        logx "ABORTADO: revisor sin autenticacion ($rev)"
        alerta "El revisor no está autenticado"
        exit 7
    fi

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
    REVISOR_FEEDBACK="$(sed -n '1,/VERDICT:/p' "$rev_out" | sed '$d' | sed '/^[[:space:]]*$/d' | paste -sd ' ' -)"
    rm -f "$rev_out"
    return 1
}

snapshot() {
    # Excluye compilados/caches (pág. .gitignore) para que nunca entren en el
    # diff ni se commiteen aunque el proyecto no tenga .gitignore.
    # core.quotepath=false evita que git status --porcelain entrecomille
    # nombres con espacios, que luego rompen revertir().
    git -C "$PROYECTO" -c core.quotepath=false status --porcelain \
        | sed 's/^...//' \
        | grep -vE '(^|/)(__pycache__|\.pytest_cache|\.mypy_cache|node_modules|\.venv|venv)/|\.pyc$|\.pyo$' \
        | sort > "$1"
}

revertir() {
    # Revert all working-tree changes on the task branch back to the base commit.
    # The task branch was created from the base, so HEAD == base commit.
    # Use git status --porcelain (v1 format). Parse: first 3 chars = status,
    # rest = path (may be quoted if it contains spaces).
    # Change types:
    #   ??  untracked (new file by agent) → remove
    #    D / D  deleted in worktree → restore from HEAD
    #    M / M  / T / etc. modified → restore from HEAD
    # Skip CONTROL files (plan.md, progreso.log, etc.)
    git -C "$PROYECTO" status --porcelain \
        | grep -vE "^.. ($CONTROL)$" \
        | while IFS= read -r line; do
            status="${line:0:2}"
            file="${line:3}"
            # Strip surrounding double quotes if present (git quotes paths with spaces)
            file="${file#\"}"; file="${file%\"}"
            case "$status" in
                "??")
                    # Nuevo archivo creado por el agente (untracked): borrarlo
                    rm -rf "$PROYECTO/$file" 2>/dev/null
                    ;;
                " D"|"D "|"D")
                    # Archivo borrado por el agente: restaurar desde HEAD
                    git -C "$PROYECTO" checkout -- "$file" 2>/dev/null
                    ;;
                *)
                    # Cualquier otra modificación en worktree (M, T, etc.): restaurar
                    git -C "$PROYECTO" checkout -- "$file" 2>/dev/null
                    ;;
            esac
        done
}

# --- Integridad del gate: el agente no debe poder alterar gate.sh/gate_checks ---
# Se respalda el gate prístino al inicio del run; si el agente lo modifica,
# se restaura y se anula el intento (el gate es código del framework, no del proyecto).
GATE_BACKUP_DIR="$(mktemp -d)"
backup_gate() {
    rm -rf "$GATE_BACKUP_DIR"
    mkdir -p "$GATE_BACKUP_DIR"
    cp -f "$GATE" "$GATE_BACKUP_DIR/" 2>/dev/null
    [ -d "$PROYECTO/gate_checks" ] && cp -rf "$PROYECTO/gate_checks" "$GATE_BACKUP_DIR/" 2>/dev/null
}

gate_intacto() {
    diff -q "$GATE" "$GATE_BACKUP_DIR/gate.sh" >/dev/null 2>&1 || return 1
    local f
    for f in "$PROYECTO"/gate_checks/*.sh; do
        [ -f "$f" ] || continue
        diff -q "$f" "$GATE_BACKUP_DIR/gate_checks/$(basename "$f")" >/dev/null 2>&1 || return 1
    done
    return 0
}

restaurar_gate() {
    cp -f "$GATE_BACKUP_DIR/gate.sh" "$GATE" 2>/dev/null
    [ -d "$GATE_BACKUP_DIR/gate_checks" ] && cp -rf "$GATE_BACKUP_DIR/gate_checks/." "$PROYECTO/gate_checks/" 2>/dev/null
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

    local decision="" esperado=0
    while [ ! -f "$dir_revision/decision" ]; do
        sleep 2
        esperado=$((esperado + 2))

        # Criterio de infraestructura: si se cae la red, abortar como el resto del loop.
        if [ $((esperado % 30)) -eq 0 ] && ! hay_internet; then
            echo "[autopiloto] ✗ sin internet durante la revisión manual: abortando." | tee -a "$LOG"
            logx "ABORTADO: sin internet durante revisión manual"
            alerta "Sin internet, se aborta el autopiloto"
            rm -f "$dir_revision/waiting" "$dir_revision/decision"
            exit 4
        fi

        if [ "$TIMEOUT_REVISION_MANUAL" -gt 0 ] && [ "$esperado" -ge "$TIMEOUT_REVISION_MANUAL" ]; then
            echo "[autopiloto] ✗ timeout de revisión manual (${TIMEOUT_REVISION_MANUAL}s): tarea bloqueada." | tee -a "$LOG"
            logx "REVISIÓN MANUAL: timeout sin respuesta"
            alerta "Revisión manual sin respuesta, tarea marcada como bloqueada"
            rm -f "$dir_revision/waiting" "$dir_revision/decision"
            return 2
        fi
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

# ---- Autodetección de agente si no se especificó (o se pidió "auto") ----
# "auto" y vacío significan lo mismo: usar el primer agente disponible según
# AGENTES_PREFERIDOS. La GUI manda "auto" por defecto, así que resolver solo el
# caso vacío dejaba el loop sin agente (agente_ok "auto" → aborta con exit 2).
if [ -z "$AGENTE_TAREA" ] || [ "$AGENTE_TAREA" = "auto" ]; then
    AGENTE_TAREA="$(detectar_agente)"
    if [ -z "$AGENTE_TAREA" ]; then
        echo "[autopiloto] ✗ No se encontró ningún agente (opencode, codex, claude)." | tee -a "$LOG"
        exit 2
    fi
    echo "[autopiloto] Agente autodetectado: $AGENTE_TAREA"
fi

# Antes de lanzar el loop: si el binario del agente no existe, abortar ya.
if ! agente_ok "$AGENTE_TAREA"; then
    BIN="$(cli_agente "$AGENTE_TAREA")"
    # ${VAR^^} es bash 4+; el /bin/bash de macOS es 3.2. `tr` es POSIX.
    CLI_ENV="$(printf '%s' "$AGENTE_TAREA" | tr '[:lower:]' '[:upper:]')"
    echo "[autopiloto] ✗✗ agente '$AGENTE_TAREA' no encontrado (busqué '$BIN')." \
         "Instálalo o configura el PATH (o CLI_${CLI_ENV}) y relanza." | tee -a "$LOG"
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

# Respaldo del gate prístino ANTES de que el agente pueda tocar nada.
backup_gate

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
    if [ "$MAX_COSTO" -gt 0 ] && num -v t="$COSTO_TOTAL" -v m="$MAX_COSTO" 'BEGIN{exit !(t>=m)}'; then
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
    # `seq` no existe en BSD/macOS. El contador sube al ENTRAR del bucle para
    # que un `continue` siga avanzando la intento.
    intento=0
    while [ "$intento" -lt "$MAX_REINTENTOS" ]; do
        intento=$((intento + 1))
        PRE=""
        [ "$intento" -gt 1 ] && PRE="El intento anterior no pasó la verificación: no repitas tu cambio, corrígelo. "
        COSTO_ITER_ACTUAL="$(num -v t="$COSTO_ITER_ACTUAL" -v a="$COSTO_POR_ITER" 'BEGIN{printf "%.2f", t+a}')"

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

        # Agente instalado pero SIN sesión: no es un fallo de la tarea, es
        # configuración. Sin este corte el loop marcaría cada tarea [B] y
        # seguiría gastando iteraciones sin poder trabajar nunca.
        if sin_autenticacion "$OUT"; then
            echo "[autopiloto] ✗✗ $AGENTE_TAREA no está autenticado (CLI instalado, sin sesión)." \
                 "Haz login del agente y relanza (opencode: 'opencode auth login' · claude: '/login' · codex: 'codex login')." | tee -a "$LOG"
            logx "ABORTADO: agente sin autenticacion ($AGENTE_TAREA)"
            alerta "El agente no está autenticado; revisa su login"
            exit 7
        fi

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

        # Integridad del gate: si el agente alteró gate.sh/gate_checks/*.sh,
        # restaurar el prístino y anular este intento (no se ejecuta el gate
        # contaminado; es un vector de inyección de código).
        if ! gate_intacto; then
            restaurar_gate
            echo "[autopiloto] ✗ el agente alteró gate.sh/gate_checks: gate restaurado, intento anulado." | tee -a "$LOG"
            logx "GATE ALTERADO por el agente (intento $intento), restaurado"
            PRE="No edites gate.sh ni gate_checks/*.sh (son del framework). Tu cambio a esos archivos se descartó. "
            continue
        fi

        logx "GATE: ejecutando gate.sh (intento $intento)"
        GATE_OUT="$(mktemp)"
        # tee: la salida del gate se ve en vivo Y se guarda para el feedback
        if bash "$GATE" 2>&1 | tee "$GATE_OUT"; then
            if [ "$REVISION_DUAL" = "1" ] && [ -n "$REVISOR" ]; then
                COSTO_ITER_ACTUAL="$(num -v t="$COSTO_ITER_ACTUAL" -v a="$COSTO_POR_ITER" 'BEGIN{printf "%.2f", t+a/2}')"
                if revisar_diff "$REVISOR"; then
                    # Gate dual pasó, ahora verificar revisión manual si está activada
                    esperar_revision_manual
                    rc_rev=$?
                    if [ "$rc_rev" -eq 0 ]; then
                        hecho=1
                        break
                    elif [ "$rc_rev" -eq 2 ]; then
                        logx "Revisión manual: timeout, tarea marcada [B]"
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
                esperar_revision_manual
                rc_rev=$?
                if [ "$rc_rev" -eq 0 ]; then
                    hecho=1
                    break
                elif [ "$rc_rev" -eq 2 ]; then
                    logx "Revisión manual: timeout, tarea marcada [B]"
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

    COSTO_TOTAL="$(num -v t="$COSTO_TOTAL" -v a="$COSTO_POR_ITER" 'BEGIN{printf "%.2f", t+a}')"
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

# Intentar crear repo en GitHub si hay credenciales y no hay remote origin
# Vía preferida: CLI gh (usa credenciales del keyring, sin token en línea de
# comandos ni en logs). Fallback: GITHUB_TOKEN vía API.
_asegurar_remote_origin() {
    if ! git -C "$PROYECTO" remote get-url origin >/dev/null 2>&1; then
        local repo_name="$(basename "$PROYECTO")"
        local owner=""
        if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
            owner="$(gh api user --jq .login 2>/dev/null)"
            if [ -n "$owner" ] && gh repo create "$owner/$repo_name" --private >/dev/null 2>&1; then
                echo "[autopiloto] ✔ repo creado en GitHub: $owner/$repo_name"
                # remote https: usa el credential helper de gh (keyring), no SSH.
                git -C "$PROYECTO" remote add origin "https://github.com/$owner/$repo_name.git"
                logx "repo creado y remote origin configurado: https://github.com/$owner/$repo_name.git"
                return 0
            fi
            echo "[autopiloto] ⚠ no se pudo crear repo con gh (respuesta API)" | tee -a "$LOG"
        elif [ -n "${GITHUB_TOKEN:-}" ]; then
            owner="$(curl -s -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/user | grep -o '"login":"[^"]*"' | cut -d'"' -f4)"
            if [ -n "$owner" ]; then
                echo "[autopiloto] Creando repo GitHub: $owner/$repo_name ..."
                local create_resp="$(curl -s -X POST -H "Authorization: Bearer $GITHUB_TOKEN" \
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
                echo "[autopiloto] ⚠ no se pudo crear repo (respuesta API: $create_resp)" | tee -a "$LOG"
            fi
        else
            registrar_leccion \
                "GitHub: remote origin ausente" \
                "No hay gh autenticado ni GITHUB_TOKEN para crear repo automático." \
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