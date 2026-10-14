#!/usr/bin/env python3
"""Agentes del loop nativo (port de autopiloto.sh): ejecutar al agente de
tarea, navegador y revisor; detección de auth/tokens; métricas a
metrics.jsonl; elección de revisor. Sin dependencias de PySide.

El objeto `cfg` es la Configuración definida en loop.py (lee el entorno como
el script). Aquí sólo se leen atributos, sin importar loop.py (sin ciclos).
"""

import datetime
import json
import os
import re
import shutil

from .loop_proceso import run_con_timeout
from .loop_util import ahora_ms, logx

UTC = datetime.timezone.utc

# Patrón DE ALTA CONFIANZA de falta de auth (sin "401" suelto ni
# "unauthorized" en narrativa). Igual que sin_autenticacion().
_PATRON_AUTH = re.compile(
    r"(Please run .*/login|Please run .* login|run .* auth login|"
    r"Authentication Error|authentication_error|invalid[ _.-]?api[ _.-]?key|"
    r"missing[ _.-]?api[ _.-]?key|401 Unauthorized|HTTP 401|"
    r"Please set your api key)", re.IGNORECASE)

_PATRON_TOKENS = re.compile(
    r"insufficient_quota|rate_limit_exceeded|quota\.exceeded|"
    r"credit\.balance\.is\.too\.low|billing\.hard\.limit|RESOURCE_EXHAUSTED|"
    r"tokens?\.exhausted|out\.of\.tokens|no\.quota|quota\.depleted|"
    r"monthly\.limit|usage\.limit", re.IGNORECASE)

_USAGE = re.compile(
    r"\"usage\":\s*\{[^}]*\"input_tokens\":\s*(\d+)[^}]*"
    r"\"output_tokens\":\s*(\d+)")


def cli_agente(agente, cfg):
    """Binario del agente según CLI_* (igual que cli_agente())."""
    if agente == "opencode":
        return cfg.environ.get("CLI_OPENCODE") or "opencode"
    if agente == "codex":
        return cfg.environ.get("CLI_CODEX") or "codex"
    if agente == "claude":
        return cfg.environ.get("CLI_CLAUDE") or "claude"
    return ""


def agente_ok(agente, cfg):
    """¿El binario del agente existe y es ejecutable? (command -v)."""
    binario = cli_agente(agente, cfg)
    if not binario:
        return False
    resolved = shutil.which(binario) if os.sep not in binario else binario
    return resolved is not None and os.access(resolved, os.X_OK)


def detectar_agente(cfg):
    """Primer agente disponible según AGENTES_PREFERIDOS (opencode→codex→
    claude), igual que el script."""
    for a in (cfg.agentes_preferidos or "opencode codex claude").split():
        if a == "auto":
            continue
        if agente_ok(a, cfg):
            return a
    return ""


def elegir_revisor(cfg):
    """Revisor: preferido si es uno concreto; si es "auto"/vacío, otro agente
    distinto al de tarea; en último caso el mismo."""
    tarea = cfg.agente_tarea or ""
    preferido = cfg.agente_revisor or ""
    if preferido and preferido != "auto":
        if agente_ok(preferido, cfg):
            return preferido
    for a in (cfg.agentes_preferidos or "opencode codex claude").split():
        if not a or a == "auto":
            continue
        if agente_ok(a, cfg) and a != tarea:
            return a
    if tarea and agente_ok(tarea, cfg):
        return tarea
    return ""


def sin_autenticacion(stderr_file, stdout_file, corroborar):
    """Sospecha de auth REAL: patrón en stderr completo o en las últimas 40
    líneas de stdout, corroborado con iteración sin trabajo."""

    def _detecta(ruta, slceroh=False, cola=40):
        try:
            with open(ruta, encoding="utf-8", errors="replace") as f:
                if cola is None:
                    texto = f.read()
                else:
                    texto = "".join(f.readlines()[-cola:])
        except OSError:
            return False
        return bool(_PATRON_AUTH.search(texto))

    detectado = (_detecta(stderr_file, cola=None)  # stderr completo
                 or (stdout_file and os.path.exists(stdout_file)
                     and _detecta(stdout_file, cola=40)))
    return detectado and bool(corroborar)


def tokens_agotados(archivo):
    """¿La salida del agente indica cuota/tokens agotados? (grep -qiE)."""
    try:
        with open(archivo, encoding="utf-8", errors="replace") as f:
            texto = f.read()
    except OSError:
        return False
    return bool(_PATRON_TOKENS.search(texto))


def costo_por_modelo(modelo, tokens_in, tokens_out):
    """Mismo caso (modelo → tarifa) que _registrar_metrica del script
    (USD, sin escalar; el %.6f lo hace quien escribe la métrica)."""
    if any(m in (modelo or "") for m in ("opus", "sonnet", "haiku")):
        return (tokens_in * 15 + tokens_out * 75) / 1_000_000
    if "gpt-4" in (modelo or "") or "gpt-4o" in (modelo or ""):
        return (tokens_in * 30 + tokens_out * 60) / 1_000_000
    if "gpt-3.5" in (modelo or ""):
        return (tokens_in * 0.5 + tokens_out * 1.5) / 1_000_000
    return (tokens_in * 1 + tokens_out * 3) / 1_000_000


def _leer_fichero(ruta):
    try:
        with open(ruta, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def extraer_tokens(texto, agente):
    """(tokens_in, tokens_out) desde la salida, como hace el grep del script."""
    tin = tout = 0
    if agente == "codex":
        m = list(re.finditer(r"tokens_used:\s*(\d+)", texto))
        if m:
            tout = int(m[-1].group(1))
        return tin, tout
    usos = list(_USAGE.finditer(texto))
    if usos:
        m = usos[-1]  # tail -1
        tin, tout = int(m.group(1)), int(m.group(2))
    return tin, tout


def registrar_metrica(cfg, agente, modelo, dur_ms, rc, salida, tarea, iteracion):
    """Append de una línea al metrics.jsonl (6 decimales y ts UTC, como el
    printf del script; sin depender del locale)."""
    texto = _leer_fichero(salida)
    tin, tout = extraer_tokens(texto, agente)
    costo = costo_por_modelo(modelo, tin, tout)
    ts = datetime.datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    linea = json.dumps({
        "ts": ts, "iter": int(iteracion), "agente": agente,
        "modelo": modelo or "default", "dur_ms": int(dur_ms), "rc": int(rc),
        "tokens_in": int(tin), "tokens_out": int(tout),
        "costo_usd": round(costo, 6), "tarea": tarea,
    }, ensure_ascii=False)
    try:
        with open(cfg.metrics, "a", encoding="utf-8") as f:
            f.write(linea + "\n")
    except OSError:
        pass


def run_agente(cfg, agente, salida, modelo, prompt, tarea, iteracion):
    """Ejecuta una tarea con un agente y devuelve su exit code (run_agente).

    Abre los archivos de salida (stdout/salida, stderr/salida.err) como el
    redirect `> "$salida" 2> "$salida_err"` del script, registra la métrica y
    pasa el proc por `vivo` para que las señales lo maten. Devuelve
    (rc, agente_pid_dict).
    """
    agente = (agente or cfg.agente_tarea or "").strip()
    if not agente or agente == "auto":
        agente = detectar_agente(cfg) or ""
    binario = cli_agente(agente, cfg)
    if not binario or not agente_ok(agente, cfg):
        logx(cfg.log, f"ABORTADO: agente no disponible ({agente})")
        return 2, None
    flags = (cfg.environ.get("CODEX_FLAGS") or "").split() \
        if agente == "codex" else []
    claude_flags = (cfg.environ.get("CLAUDE_FLAGS") or "").split() \
        if agente == "claude" else []
    if agente == "opencode":
        if modelo:
            cmd = [binario, "run",
                   "--agent", cfg.environ.get("OPENCODE_AGENT_TAREA") or "build",
                   "--model", modelo, prompt]
        else:
            cmd = [binario, "run",
                   "--agent", cfg.environ.get("OPENCODE_AGENT_TAREA") or "build",
                   prompt]
    elif agente == "codex":
        cmd = [binario, "exec", "--skip-git-repo-check",
               *flags, prompt]
    elif agente == "claude":
        cmd = [binario, "-p", "--output-format", "text", *claude_flags, prompt]
    else:
        logx(cfg.log, f"ABORTADO: agente desconocido ({agente})")
        return 2, None

    salida_err = salida + ".err"
    vivo = {}
    t0 = ahora_ms()
    with open(salida, "wb") as fout, open(salida_err, "wb") as ferr:
        rc, _salida, _t = run_con_timeout(
            cmd, cfg.timeout_por_tarea, env=cfg.environ,
            cwd=cfg.proyecto, stdout=fout, stderr=ferr, vivo=vivo)
    dur = ahora_ms() - t0
    registrar_metrica(cfg, agente, modelo, dur, rc, salida, tarea, iteracion)
    return rc, vivo


def run_navegador(cfg, salida, modelo, tarea, agente):
    """Navegador de contexto previo a la tarea; rc del agente (run_navegador).
    Un fallo aquí solo significa menos contexto: no aborta el loop."""
    binario = cli_agente(agente, cfg)
    if not binario or not agente_ok(agente, cfg):
        return 1, {}
    prompt = (f"Tarea: {tarea}\n"
              f"Repo: {cfg.proyecto}\n"
              "Encuentra archivos, tests y endpoints relevantes. Lista concisa "
              "(máx 30 líneas):\n"
              "ARCHIVOS: ruta/archivo.py\n"
              "TESTS: ruta/test.py::test_x\n"
              "ENDPOINTS: GET /api/...\n"
              "MODELOS: Modulo.servicio")
    if agente == "opencode":
        cmd = [binario, "run",
               "--agent", cfg.environ.get("OPENCODE_AGENT_NAV") or "navigate",
               "--model", modelo, prompt]
    elif agente == "codex":
        cmd = [binario, "exec", "--skip-git-repo-check", prompt]
    elif agente == "claude":
        cmd = [binario, "-p", "--output-format", "text", prompt]
    else:
        return 1, {}
    salida_err = salida + ".err"
    vivo = {}
    t0 = ahora_ms()
    with open(salida, "wb") as fout, open(salida_err, "wb") as ferr:
        rc, _s, _t = run_con_timeout(
            cmd, cfg.timeout_navegador, env=cfg.environ, cwd=cfg.proyecto,
            stdout=fout, stderr=ferr, vivo=vivo)
    dur = ahora_ms() - t0
    registrar_metrica(cfg, agente, modelo, dur, rc, salida, tarea, 0)
    return rc, vivo


def revisar_diff(cfg, rev, tarea, vdiff):
    """Revisor dual del diff (revisar_diff + cola del script).

    Devuelve (resultado, feedback):
      resultado: "pass" | "fail" | "sin_auth" | "sin_tokens"
      feedback:  razones previas al VERDICT (para inyectar en el próximo
                 intento) cuando fail.
    """
    rev_out = cfg.tmp("rev_out")
    ruta_ctx = getattr(cfg, "contexto", "")
    contexto = _leer_fichero(ruta_ctx).strip() if ruta_ctx else ""
    contexto_block = (f"Contexto del proyecto (respétalo al juzgar):\n"
                      f"{contexto}\n\n" if contexto else "")
    prompt = ("Eres el REVISOR en modo autopiloto. Usa únicamente las skills "
              "que tu sesión ya tenga cargadas; no intentes cargar ninguna otra.\n"
              "Revisas el diff COMPLETO de una tarea, en frío, sin haber "
              "participado de ella.\n"
              f"{contexto_block}"
              f"Tarea: {tarea}\n\n{vdiff}\n\n"
              "Evalúa SOLO: (1) la tarea satisface su criterio, (2) no rompe "
              "nada obvio del proyecto,\n(3) sin secretos, (4) sin scope creep "
              "(cambios ajenos a la tarea).\n"
              "Responde con 2 o 3 líneas de razones y, EN LA ÚLTIMA LÍNEA, "
              "exactamente: VERDICT: PASS o VERDICT: FAIL")
    rc, _vivo = run_agente(cfg, rev, rev_out, cfg.modelo_revisor,
                           prompt, tarea, 0)
    texto = _leer_fichero(rev_out)
    sin_veredicto = "VERDICT:" not in texto
    if sin_autenticacion(rev_out + ".err", rev_out, int(sin_veredicto)):
        logx(cfg.log, f"ABORTADO: revisor sin autenticacion ({rev})")
        return "sin_auth", None
    if tokens_agotados(rev_out) or tokens_agotados(rev_out + ".err"):
        logx(cfg.log, "ABORTADO: tokens/cuota agotados (revisor)")
        return "sin_tokens", None
    if re.search(r"VERDICT:\s*PASS", texto):
        return "pass", None
    veredicto = ""
    for linea in reversed(texto.splitlines()):
        if re.search(r"VERDICT:", linea):
            veredicto = linea
            break
    razones = [li for li in texto.splitlines()
               if re.search(r"VERDICT:", li) is None]
    feedback = " ".join(li for li in razones if li.strip()).strip()
    return "fail", feedback or (veredicto or "sin veredicto claro")
