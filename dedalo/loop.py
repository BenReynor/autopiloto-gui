#!/usr/bin/env python3
"""Motor del bucle de dedalo en Python (port de dedalo.sh, W2 F3).

Sustituye al script bash manteniendo el MISMO contrato de log (lo parsea la
GUI con las regex de metricas.py) y el mismo comportamiento observable. El
gate se ejecuta como subproceso Python portable (dedalo.gate): corre
los checks .py y delega en bash los .sh si existe (así en Unix se conserva el
comportamiento de siempre y en Windows funciona sin Git Bash). gate.sh y
gate_checks/ siguen siendo código del framework.

Uso (directo y desde la GUI; directorio actual = proyecto):
    python -m dedalo.loop [plan.md] [--hasta HH:MM] [--push]
                                  [--padre rama] [--trabajo rama]

Sin dependencias de PySide (ningún loop_* importa Qt): el motor corre también
en Windows con el mismo python que empaqueta la GUI, sin Git Bash.
"""

import filecmp
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

from . import net
from .gate import argv_gate
from .loop_agentes import (
    agente_ok,
    cli_agente,
    detectar_agente,
    elegir_revisor,
    revisar_diff,
    run_agente,
    run_navegador,
    sin_autenticacion,
    tokens_agotados,
)
from .loop_args import parse_args
from .loop_git import (
    borrar_rama,
    cambios_entre,
    checkout,
    commit_tarea,
    diff_para_revisor,
    merge_ff,
    preparar_ramas,
    rama_existe,
    registrar_leccion,
    revertir,
    run_git,
    snapshot,
)
from .loop_proceso import limpiar_sesiones, matar_grupo, run_con_timeout
from .loop_util import ahora_ms, alerta, hora_limite, incidencia, logx, suma_coste
from .plan import Plan

GATE_TIMEOUT = 43200  # 12 h: el gate bash no tiene tope propio (como el script)
HIJO = {"proc": None}  # proceso agente/gate actual (lo matan las señales)
_RECHAZO_MOTIVO = {"txt": ""}  # variable global estilo ${RECHAZO_MOTIVO} del script


class Config:
    """Configuración del run leída del entorno (mismos defaults que el
    script). Se instancia en main() y se pasa a todas las funciones."""

    def __init__(self, args, environ=None, proyecto=None):
        env = environ if environ is not None else os.environ
        self.environ = env
        self.proyecto = str(proyecto) if proyecto else os.getcwd()
        self.plan_md = args.plan
        self.gate = os.path.join(self.proyecto, "gate.sh")
        self.mapear = os.path.join(self.proyecto, "mapear.sh")
        self.mapa = os.path.join(self.proyecto, "mapeo.txt")
        self.log = os.path.join(self.proyecto, "progreso.log")
        self.lecciones = os.path.join(self.proyecto, "lecciones.md")
        self.contexto = os.path.join(self.proyecto, "CONTEXTO.md")
        self.incidencias = os.path.join(self.proyecto, "incidencias.jsonl")
        self.metrics = os.path.join(self.proyecto, "metrics.jsonl")
        self.ultimo_motivo = None  # dict del último fallo de la tarea actual

        self.max_iter = int(env.get("MAX_ITER", "40"))
        self.timeout_por_tarea = int(env.get("TIMEOUT_POR_TAREA", "900"))
        self.timeout_navegador = int(env.get("TIMEOUT_NAVEGADOR", "60"))
        self.max_reintentos = 2  # hardcode del script (no llega por env)
        self.agente_tarea = env.get("AGENTE_TAREA", "") or ""
        self.agentes_preferidos = env.get("AGENTES_PREFERIDOS",
                                          "opencode codex claude") or ""
        self.modelo_tarea = env.get("MODELO_TAREA", "") or ""
        self.modelo_navegador = env.get("MODELO_NAVEGADOR",
                                        "opencode/big-pickle") or ""
        self.navegador = env.get("NAVEGADOR", "0")
        self.agente_revisor = env.get("AGENTE_REVISOR", "") or ""
        self.revisor = ""  # resuelto en run() (elegir_revisor)
        self.modelo_revisor = env.get("MODELO_REVISOR", "") or ""
        self.modelo_juez = env.get(
            "MODELO_JUEZ", "opencode/nemotron-3.5-lightning-free") or ""
        self.opencode_agente_juez = env.get("OPENCODE_AGENT_JUEZ", "build") or ""
        self.revision_dual = env.get("REVISION_DUAL", "1")
        self.revision_manual = env.get("REVISION_MANUAL", "0")
        self.timeout_revision_manual = int(
            env.get("TIMEOUT_REVISION_MANUAL", "1800"))
        self.voz = env.get("VOZ", "0")
        self.max_costo = float(env.get("MAX_COSTO", "0") or 0)
        self.costo_por_iter = env.get("COSTO_POR_ITER", "0.50")
        self.rama_base = args.padre or env.get("RAMA_BASE", "master") or "master"
        self.push = args.push
        self.hasta = args.hasta or ""
        self.rama_trabajo = args.trabajo or ""
        self.inicio_ms = ahora_ms()

    def tmp(self, sufijo=""):
        """Ruta temporal nueva (equivalente a mktemp; única por llamada)."""
        fd, ruta = tempfile.mkstemp(suffix=("-" + sufijo if sufijo else ""))
        os.close(fd)
        return ruta


def _leer(ruta):
    try:
        with open(ruta, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _append_log(cfg, texto):
    """Equivalente a `cat << EOF >> "$LOG"` (sin timestamp, raw)."""
    try:
        with open(cfg.log, "a", encoding="utf-8") as f:
            f.write(texto if texto.endswith("\n") else texto + "\n")
    except OSError:
        pass


def _incidencia(cfg, tipo, motivo, tarea="", iteracion=0, rama=""):
    """Registra una incidencia estructurada y recuerda el último motivo.

    `incidencias.jsonl` es independiente de `progreso.log` (prosa): una línea
    JSON por fallo/aborto, para el panel de incidencias de la GUI y el resumen
    final. `cfg.ultimo_motivo` permite que una tarea bloqueada herede el porqué
    real de su último fallo (gate/revisor), en vez de un texto genérico."""
    incidencia(cfg.incidencias, tipo, motivo, tarea, iteracion, rama)
    cfg.ultimo_motivo = {"tipo": tipo, "motivo": motivo or "",
                         "iteracion": iteracion, "tarea": tarea or ""}


def mensaje(cfg, s):
    """Equivalente a `echo "<s>" | tee -a "$LOG"` del script: consola + log."""
    print(s)
    _append_log(cfg, s)


def _proteger_salidas():
    """En un binario --windowed (Windows) sys.stdout/stderr son None y el
    primer print() reventaría. Se redirigen a devnull; lo que importa (el
    log con timestamp) ya va a progreso.log. No-op cuando hay consola.

    Con consola heredada (Git Bash/cmd/PowerShell en Windows) los streams
    NO son None pero su encoding es la locale (cp1252) y el primer ✗ del
    motor moría con UnicodeEncodeError: se pasan a utf-8 con
    errors="replace" para que ningún print mate al proceso."""
    for nombre in ("stdout", "stderr"):
        s = getattr(sys, nombre, None)
        if s is None:
            setattr(sys, nombre, open(
                os.devnull, "w", encoding="utf-8", errors="replace"))
        elif hasattr(s, "reconfigure"):
            try:
                s.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def rama_run_nombre():
    """`dedalo/$(date +%Y-%m-%d_%H-%M-%S)` del script."""
    return "dedalo/" + time.strftime("%Y-%m-%d_%H-%M-%S")


def _mapear(cfg):
    """`bash "$MAPEAR" > "$MAPA" 2>/dev/null` (mapeo.txt, silencioso)."""
    if not os.path.exists(cfg.mapear):
        return
    try:
        with open(cfg.mapa, "wb") as f:
            subprocess.run(["bash", cfg.mapear], cwd=cfg.proyecto,
                           stdout=f, stderr=subprocess.DEVNULL,
                           env=cfg.environ, timeout=120)
    except OSError:
        pass


def backup_gate(cfg):
    """Copia gate.sh y gate_checks/ a un dir temporal (backup_gate())."""
    dir_backup = tempfile.mkdtemp(prefix="dedalo-gate-")
    if os.path.exists(cfg.gate):
        shutil.copyfile(cfg.gate, os.path.join(dir_backup, "gate.sh"))
    src = os.path.join(cfg.proyecto, "gate_checks")
    if os.path.isdir(src):
        shutil.copytree(src, os.path.join(dir_backup, "gate_checks"))
    return dir_backup


def gate_intacto(dir_backup, cfg):
    """¿El agente alteró gate.sh o gate_checks/*.{sh,py}? (gate_intacto())."""
    backup_gate_sh = os.path.join(dir_backup, "gate.sh")
    if os.path.exists(cfg.gate) != os.path.exists(backup_gate_sh):
        return False
    if os.path.exists(cfg.gate) and not filecmp.cmp(
            cfg.gate, backup_gate_sh, shallow=False):
        return False
    proyecto_checks = os.path.join(cfg.proyecto, "gate_checks")
    backup_checks = os.path.join(dir_backup, "gate_checks")
    if not os.path.isdir(backup_checks):
        return True
    for f in sorted(os.listdir(backup_checks)):
        # Cubre tanto los checks bash como los del port Python (Windows).
        if not f.endswith((".sh", ".py")):
            continue
        original = os.path.join(backup_checks, f)
        if not os.path.isfile(original):
            continue
        actual = os.path.join(proyecto_checks, f)
        if not os.path.exists(actual) or not filecmp.cmp(actual, original,
                                                         shallow=False):
            return False
    return True


def restaurar_gate(dir_backup, cfg):
    """Restaura gate.sh/gate_checks desde el backup (restaurar_gate())."""
    backup_gate_sh = os.path.join(dir_backup, "gate.sh")
    if os.path.exists(backup_gate_sh):
        shutil.copyfile(backup_gate_sh, cfg.gate)
    backup_checks = os.path.join(dir_backup, "gate_checks")
    if os.path.isdir(backup_checks):
        shutil.rmtree(os.path.join(cfg.proyecto, "gate_checks"),
                      ignore_errors=True)
        shutil.copytree(backup_checks, os.path.join(cfg.proyecto, "gate_checks"))


def _run_gate(cfg, criterio):
    """`python -m dedalo.gate 2>&1 | tee "$GATE_OUT"`.

    Devuelve (rc, ruta_con_la_salida_del_gate). La salida se ve en consola y
    se usa como feedback al agente si el gate falla. El gate muta el
    repositorio (p. ej. 98_criterio lanza el juez).

    El gate es el orquestador portable (gate.py): corre los checks .py y, si
    hay bash, prefiere los .sh equivalentes. En el binario congelado se lanza
    como `dedalo --dedalo-gate`.
    """
    gate_out = cfg.tmp("gate")
    env = dict(cfg.environ)
    env["CRITERIO"] = criterio or ""
    env["MODELO_JUEZ"] = cfg.modelo_juez
    env["OPENCODE_AGENT_JUEZ"] = cfg.opencode_agente_juez
    if not getattr(sys, "frozen", False):
        # `python -m dedalo.gate` arranca con cwd=proyecto: sin esto,
        # un intérprete sin el paquete instalado (desarrollo) no lo encuentra.
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env["PYTHONPATH"] = raiz + (
            os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    with open(gate_out, "wb") as ftee:
        rc, _salida, _t = run_con_timeout(
            argv_gate(), GATE_TIMEOUT, env=env, cwd=cfg.proyecto,
            stdout=ftee, stderr=subprocess.STDOUT, vivo=HIJO)
    contenido = _leer(gate_out)
    if contenido:
        sys.stdout.write(contenido)
        if contenido[-1] != "\n":
            print()
    return rc, gate_out


def proxima_tarea(plan_md):
    """Primera línea `- [ ] ` (columna 0) sin el prefijo; None si no quedan."""
    for linea in _leer(plan_md).splitlines():
        if linea.startswith("- [ ] "):
            return linea[len("- [ ] "):]
    return None


def criterio_tarea(plan_md):
    """Criterio de la PRIMERA tarea pendiente (inline o indentado), port de
    criterio_tarea(): `- [ ] ` caja con criterio inline, o línea indentada
    bajo la primera pendiente; corte al ver `- [x]`/`- [B]` o línea sin
    indentar."""
    en_tarea = 0
    rx_inline = re.compile(r"criterio:[ \t]+(.*)$")
    rx_indent = re.compile(r"criterio:[ \t]*(.*)$")
    for linea in _leer(plan_md).splitlines():
        if linea.startswith("- [ ] "):
            m = rx_inline.search(linea)
            if m:
                return m.group(1).strip()
            en_tarea = 1
            continue
        if linea.startswith("- ["):
            if en_tarea:
                return None
            continue
        if en_tarea:
            if not re.match(r"[ \t]", linea):
                return None
            m = rx_indent.search(linea)
            if m:
                return m.group(1).strip()
    return None


def _instalar_senales(cfg):
    """SIGTERM→143 / SIGINT→130 (como los traps del script): mata al grupo
    del proceso actual, limpia sesiones de opencode y sale."""
    if threading.current_thread() is not threading.main_thread():
        return

    def _manejar(sig, _frame):
        try:
            proc = HIJO.get("proc")
            if proc is not None and proc.poll() is None:
                matar_grupo(proc, espera=0)
            limpiar_sesiones(cli_agente("opencode", cfg), cfg.proyecto,
                             cfg.inicio_ms, cfg.log)
        finally:
            os._exit(128 + sig)

    signal.signal(signal.SIGTERM, _manejar)
    signal.signal(signal.SIGINT, _manejar)


def _marcar(cfg, estado):
    """marcar_primera en el plan (marcar_plan del script)."""
    p = Plan(cfg.plan_md)
    p.cargar()
    return p.marcar_primera(estado)


def _resumen_bloqueadas(cfg):
    """Líneas de resumen de las tareas [B] de plan.md con su último motivo.

    El motivo se busca en `incidencias.jsonl` (última incidencia por tarea), así
    el cierre responde "qué quedó sin hacer y por qué" sin bucear en el log."""
    try:
        p = Plan(cfg.plan_md)
        p.cargar()
        bloqueadas = [t["texto"] for t in p.tareas
                      if t["estado"] == "bloqueada"]
    except Exception:
        bloqueadas = []
    if not bloqueadas:
        return []
    motivos = {}
    for li in _leer(cfg.incidencias).splitlines():
        try:
            d = json.loads(li)
        except ValueError:
            continue
        if d.get("tarea"):
            motivos[d["tarea"]] = d.get("motivo", "")
    lineas = ["", "== TAREAS SIN COMPLETAR =="]
    for t in bloqueadas:
        m = motivos.get(t, "")
        lineas.append(f"- [B] {t}" + (f" — {m}" if m else ""))
    return lineas


def run(cfg):
    """Bucle completo; devuelve el código de salida (0-7, como el script)."""
    _proteger_salidas()
    _RECHAZO_MOTIVO["txt"] = ""
    _instalar_senales(cfg)

    # Autodetección: "auto" y vacío = primer agente disponible.
    if not cfg.agente_tarea or cfg.agente_tarea == "auto":
        cfg.agente_tarea = detectar_agente(cfg)
        if not cfg.agente_tarea:
            mensaje(cfg, "[dedalo] ✗ No se encontró ningún agente "
                         "(opencode, codex, claude).")
            return 2
        print(f"[dedalo] Agente autodetectado: {cfg.agente_tarea}")

    if not agente_ok(cfg.agente_tarea, cfg):
        binario = cli_agente(cfg.agente_tarea, cfg)
        cli_env = cfg.agente_tarea.upper()
        mensaje(cfg, f"[dedalo] ✗✗ agente '{cfg.agente_tarea}' no "
                     f"encontrado (busqué '{binario}'). Instálalo o configura "
                     f"el PATH (o CLI_{cli_env}) y relanza.")
        logx(cfg.log, f"ABORTADO: agente no disponible ({cfg.agente_tarea})")
        _incidencia(cfg, "aborto_agente",
                    f"agente '{cfg.agente_tarea}' no disponible en el PATH")
        return 2

    cfg.revisor = elegir_revisor(cfg)
    logx(cfg.log,
         f"== DEDALO INICIADO (agente={cfg.agente_tarea}, "
         f"modelo={cfg.modelo_tarea}, revisor={cfg.revisor or 'ninguno'}, "
         f"modelo_rev={cfg.modelo_revisor}, dual={cfg.revision_dual}, "
         f"manual={cfg.revision_manual}, max_iter={cfg.max_iter}, "
         f"hasta={cfg.hasta or 'sin limite'}, base={cfg.rama_base}, "
         f"costo_max={cfg.max_costo}) ==")

    print(f"[dedalo] Agente de tarea: {cfg.agente_tarea}"
          + (f" ({cfg.modelo_tarea})" if cfg.modelo_tarea else ""))
    print(f"[dedalo] Revisor dual:    {cfg.revisor or 'NINGUNO'}"
          + (f" ({cfg.modelo_revisor})" if cfg.modelo_revisor else "")
          + f" (dual={cfg.revision_dual})")

    print("[dedalo] Comprobando internet…")
    if not net.hay_internet():
        print("[dedalo] ✗ SIN INTERNET. Los modelos IA no pueden "
              "responder; abortando.")
        logx(cfg.log, "ABORTADO: sin internet")
        _incidencia(cfg, "aborto_internet", "sin conexión a internet")
        alerta(cfg.voz, "Sin internet, se aborta el dedalo")
        return 4
    logx(cfg.log, "Internet OK")

    dir_gate = backup_gate(cfg)
    print("[dedalo] Baseline: gate.sh...")
    rc_base, _ = _run_gate(cfg, "")
    if rc_base != 0:
        print("El repo NO pasa la verificación baseline. Corrige y relanza.")
        logx(cfg.log, "ABORTADO: baseline falló")
        _incidencia(cfg, "aborto_baseline", "el repo no pasa el gate baseline")
        alerta(cfg.voz, "Baseline falló, el dedalo no arranca")
        return 1
    logx(cfg.log, "Baseline GATE OK")

    if os.path.exists(cfg.mapear):
        _mapear(cfg)
        if os.path.getsize(cfg.mapa) > 0:
            logx(cfg.log, "mapeo.txt regenerado")
        else:
            print("[dedalo] ⚠ no se pudo generar mapeo.txt")

    rama_run = rama_run_nombre()
    rama_trabajo, msgs = preparar_ramas(cfg.proyecto, cfg.rama_base,
                                        rama_run, cfg.rama_trabajo)
    for m in msgs:
        print(m)
    if rama_trabajo is None:
        logx(cfg.log, "ABORTADO: no se pudo crear la rama base")
        _incidencia(cfg, "aborto_rama", "no se pudo crear la rama base")
        return 1
    logx(cfg.log, f"Rama base: {rama_run}")
    if cfg.rama_trabajo and cfg.rama_trabajo != rama_run:
        logx(cfg.log, f"Rama de trabajo: {rama_trabajo}")
    else:
        logx(cfg.log, f"Rama de trabajo (default): {rama_trabajo}")

    iteracion = 0
    costo_total = "0.00"
    while iteracion < cfg.max_iter:
        if hora_limite(cfg.hasta):
            logx(cfg.log, f"Hora límite ({cfg.hasta}) alcanzada.")
            print("[dedalo] ⏰ Hora límite alcanzada.")
            alerta(cfg.voz, "Hora límite alcanzada")
            break
        if cfg.max_costo > 0 and float(costo_total) >= cfg.max_costo:
            logx(cfg.log, f"Presupuesto agotado ({costo_total}/"
                          f"{cfg.max_costo} USD).")
            print(f"[dedalo] 💸 Presupuesto agotado ({costo_total}/"
                  f"{cfg.max_costo} USD).")
            alerta(cfg.voz, "Presupuesto agotado")
            break
        if not net.hay_internet():
            logx(cfg.log, "SIN INTERNET: loop detenido para no lanzar tareas "
                          "sin modelo disponible.")
            print("[dedalo] ✗ SIN INTERNET. Deteniendo el loop "
                  "(los modelos IA no responden).")
            alerta(cfg.voz, "Sin internet, se detiene el dedalo")
            break

        tarea = proxima_tarea(cfg.plan_md)
        if tarea is None:
            logx(cfg.log, f"No quedan tareas pendientes en "
                          f"{os.path.basename(cfg.plan_md)}.")
            print("[dedalo] ✔ No quedan tareas pendientes.")
            break

        iteracion += 1
        costo_iter = "0.00"
        fecha_run = rama_run.split("/")[1]
        rama_tarea = f"dedalo/tareas/{fecha_run}/t{iteracion}"
        criterio = criterio_tarea(cfg.plan_md) or ""
        logx(cfg.log, f"== Iteración {iteracion}: {tarea} (rama {rama_tarea})"
                      + (f" | criterio: {criterio}" if criterio else "") + " ==")
        print(f"[dedalo] [{iteracion}/{cfg.max_iter}] {tarea} -> {rama_tarea}")
        if criterio:
            print(f"[dedalo]   criterio: {criterio}")

        checkout(cfg.proyecto, rama_run)
        if rama_existe(cfg.proyecto, rama_tarea):
            _, actual, _ = run_git(cfg.proyecto, "branch", "--show-current")
            if actual.strip() != rama_tarea:
                borrar_rama(cfg.proyecto, rama_tarea, fuerza=True)
                print(f"[dedalo] ⚠ rama huérfana {rama_tarea} eliminada "
                      "(run anterior)")
        checkout(cfg.proyecto, rama_tarea, crear=True, desde=rama_run)

        before = cfg.tmp("before")
        after = cfg.tmp("after")
        out = cfg.tmp("out")
        snapshot(cfg.proyecto, before)
        hecho = 0
        gate_out = None
        cfg.ultimo_motivo = None

        for intento in range(1, cfg.max_reintentos + 1):
            pre = ""
            if intento > 1:
                pre = ("El intento anterior no pasó la verificación: no repitas "
                       "tu cambio, corrígelo. ")
            costo_iter = suma_coste(costo_iter, cfg.costo_por_iter)
            lecciones_ctx = ""
            if os.path.exists(cfg.lecciones) and \
                    os.path.getsize(cfg.lecciones) > 0:
                lecciones_ctx = _leer(cfg.lecciones)
            contexto_ctx = ""
            if os.path.exists(cfg.contexto) and \
                    os.path.getsize(cfg.contexto) > 0:
                contexto_ctx = _leer(cfg.contexto)
            nav_ctx = ""
            if (cfg.navegador == "1" and agente_ok(cfg.agente_tarea, cfg)
                    and cfg.modelo_navegador):
                nav = cfg.tmp("nav")
                run_navegador(cfg, nav, cfg.modelo_navegador, tarea,
                              cfg.agente_tarea)
                if os.path.getsize(nav) > 0:
                    nav_ctx = _leer(nav)
                try:
                    os.unlink(nav)
                    os.unlink(nav + ".err")
                except OSError:
                    pass

            criterio_texto = criterio or "<sin criterio explícito; usa los tests/mapeo.txt como contrato>"
            contexto_block = ("CONTEXTO DEL PROYECTO (de qué trata, requisitos, "
                              "filosofía y estructura — respétalo):\n"
                              + contexto_ctx + "\n"
                              if contexto_ctx else "")
            memoria_ctx = ("MEMORIA DEL PROYECTO (lecciones aprendidas, evita "
                           "repetir estos errores):\n" + lecciones_ctx + "\n"
                           if lecciones_ctx else "")
            prompt = (f"Estás en MODO DEDALO. Usa únicamente las skills que "
                      f"tu sesión ya tenga cargadas; no intentes cargar ninguna "
                      f"otra.\nTarea actual (solo esta): {tarea}\n"
                      f"{pre}Criterio de aceptación que debe cumplir tu trabajo "
                      f"(el gate lo verificará): {criterio_texto}\n"
                      "Lee plan.md y progreso.log antes de tocar nada. Lee también "
                      "mapeo.txt (mapa módulos→tests): localiza el/los test del "
                      "código que vas a tocar y úsalos como contrato.\n"
                      f"{nav_ctx}{contexto_block}{memoria_ctx}"
                      "Ejecuta ÚNICAMENTE esta tarea.\n"
                      "NO hagas commits, NO crees, cambies ni borres ramas: el "
                      "script gestiona git.\n"
                      "NO edites dedalo.sh, gate.sh, mapear.sh, mapeo.txt, "
                      "plan.md, progreso.log, lecciones.md, CONTEXTO.md, "
                      "endpoints.txt, .env ni SECURITY.md.\n"
                      "Al terminar, responde con un resumen conciso de qué "
                      "cambiaste y qué tests corriste.")

            rc, _vivo = run_agente(cfg, cfg.agente_tarea, out,
                                   cfg.modelo_tarea, prompt, tarea, iteracion)
            if rc == 124:
                mensaje(cfg, f"[dedalo] ⚠ timeout: {cfg.agente_tarea} tardó "
                             f"más de {cfg.timeout_por_tarea}s")
                alerta(cfg.voz, "Tiempo agotado en una tarea")
            elif rc in (126, 127):
                mensaje(cfg, f"[dedalo] ✗✗ {cfg.agente_tarea} no se pudo "
                             f"ejecutar (rc={rc}): binario no encontrado o sin "
                             f"permisos de ejecución.")
                logx(cfg.log, f"ABORTADO: agente no ejecutable (rc={rc})")
                _incidencia(cfg, "aborto_agente_ejecucion",
                            f"{cfg.agente_tarea} no ejecutable (rc={rc})",
                            tarea=tarea, iteracion=iteracion, rama=rama_tarea)
                alerta(cfg.voz, "El agente no se pudo ejecutar; revisa PATH/instalación")
                return 6
            elif rc != 0:
                mensaje(cfg, f"[dedalo] ⚠ {cfg.agente_tarea} salió con rc={rc}")

            contenido = _leer(out)
            if rc == 0 or contenido:
                print(contenido, end="")
            _append_log(cfg, contenido)

            snapshot(cfg.proyecto, after)
            nuevos, borrados = cambios_entre(before, after)
            iter_sin_trabajo = 0
            if not nuevos and not borrados:
                iter_sin_trabajo = 1
            if sin_autenticacion(out + ".err", out, iter_sin_trabajo):
                mensaje(cfg, f"[dedalo] ✗✗ {cfg.agente_tarea} no está "
                             f"autenticado (CLI instalado, sin sesión). Haz "
                             f"login del agente y relanza (opencode: 'opencode "
                             f"auth login' · claude: '/login' · codex: 'codex "
                             f"login').")
                logx(cfg.log, f"ABORTADO: agente sin autenticacion ({cfg.agente_tarea})")
                _incidencia(cfg, "aborto_autenticacion",
                            f"{cfg.agente_tarea} sin sesión iniciada",
                            tarea=tarea, iteracion=iteracion, rama=rama_tarea)
                alerta(cfg.voz, "El agente no está autenticado; revisa su login")
                return 7
            if tokens_agotados(out):
                mensaje(cfg, "[dedalo] ✗ Tokens/cuota agotados del proveedor "
                             "IA — deteniendo loop")
                logx(cfg.log, "ABORTADO: tokens/cuota agotados")
                _incidencia(cfg, "aborto_tokens", "tokens/cuota agotados",
                            tarea=tarea, iteracion=iteracion, rama=rama_tarea)
                alerta(cfg.voz, "Tokens agotados, se detiene el dedalo")
                return 5

            _, actual, _ = run_git(cfg.proyecto, "branch", "--show-current")
            if actual.strip() != rama_tarea:
                mensaje(cfg, "[dedalo] ✗✗ el agente cambió de rama. "
                             "Abortando: requiere revisión humana.")
                logx(cfg.log, "ABORTADO: se detectó cambio de rama no autorizado")
                _incidencia(cfg, "aborto_rama_agente",
                            "el agente cambió de rama (requiere revisión humana)",
                            tarea=tarea, iteracion=iteracion, rama=rama_tarea)
                alerta(cfg.voz, "El agente cambió de rama, se aborta el run")
                return 3

            if not gate_intacto(dir_gate, cfg):
                restaurar_gate(dir_gate, cfg)
                mensaje(cfg, "[dedalo] ✗ el agente alteró gate.sh/gate_checks: "
                             "gate restaurado, intento anulado.")
                logx(cfg.log, f"GATE ALTERADO por el agente (intento {intento}), "
                              "restaurado")
                pre = "No edites gate.sh ni gate_checks/*.sh (son del framework). Tu cambio a esos archivos se descartó. "
                continue

            logx(cfg.log, f"GATE: ejecutando gate.sh (intento {intento})")
            rc_gate, gate_out = _run_gate(cfg, criterio)
            if rc_gate == 0:
                if cfg.revision_dual == "1" and cfg.revisor:
                    costo_iter = suma_coste(costo_iter,
                                            float(cfg.costo_por_iter) / 2)
                    vstat, vdiff = diff_para_revisor(cfg.proyecto)
                    resultado, feedback = revisar_diff(
                        cfg, cfg.revisor, tarea,
                        f"{vstat}\n{vdiff}" if vdiff else vstat)
                    if resultado == "sin_auth":
                        mensaje(cfg, f"[dedalo] ✗✗ revisor ({cfg.revisor}) "
                                     "no está autenticado — deteniendo loop")
                        logx(cfg.log, f"ABORTADO: revisor sin autenticacion ({cfg.revisor})")
                        _incidencia(cfg, "aborto_autenticacion",
                                    f"revisor {cfg.revisor} sin sesión iniciada",
                                    tarea=tarea, iteracion=iteracion,
                                    rama=rama_tarea)
                        alerta(cfg.voz, "El revisor no está autenticado")
                        return 7
                    if resultado == "sin_tokens":
                        mensaje(cfg, "[dedalo] ✗ Tokens/cuota agotados del "
                                     "proveedor IA (revisor) — deteniendo loop")
                        logx(cfg.log, "ABORTADO: tokens/cuota agotados (revisor)")
                        _incidencia(cfg, "aborto_tokens",
                                    "tokens/cuota agotados (revisor)",
                                    tarea=tarea, iteracion=iteracion,
                                    rama=rama_tarea)
                        alerta(cfg.voz, "Tokens agotados, se detiene el dedalo")
                        return 5
                    if resultado == "pass":
                        print(f"[dedalo] ✔ revisor ({cfg.revisor}): PASS")
                        rc_manual = _esperar_revision_manual(cfg, tarea)
                        if rc_manual == 4:
                            return 4
                        if rc_manual == 0:
                            hecho = 1
                            break
                        if rc_manual == 2:
                            logx(cfg.log, "Revisión manual: timeout, tarea "
                                          "marcada [B]")
                            _incidencia(cfg, "revision_timeout",
                                        "timeout en revisión manual del diff",
                                        tarea=tarea, iteracion=iteracion,
                                        rama=rama_tarea)
                            break
                        revertir(cfg.proyecto)
                        pre = (f"El diff fue rechazado en revisión manual: "
                               f"{_RECHAZO_MOTIVO['txt']}. Corrige esto en tu "
                               "siguiente intento. ")
                        logx(cfg.log, "REVISIÓN MANUAL RECHAZADO, reintentando...")
                    else:
                        logx(cfg.log, f"REVISOR FAIL (intento {intento})")
                        _incidencia(cfg, "revisor_fail",
                                    feedback or "el revisor rechazó el diff",
                                    tarea=tarea, iteracion=iteracion,
                                    rama=rama_tarea)
                        print(f"[dedalo] ✗ revisor ({cfg.revisor}): FAIL")
                        if feedback:
                            pre = (f"El revisor rechazó el diff anterior: "
                                   f"{feedback}. Corrige esto en tu siguiente "
                                   "intento. ")
                            logx(cfg.log, "Feedback del revisor inyectado para "
                                          "siguiente intento")
                else:
                    rc_manual = _esperar_revision_manual(cfg, tarea)
                    if rc_manual == 4:
                        return 4
                    if rc_manual == 0:
                        hecho = 1
                        break
                    if rc_manual == 2:
                        logx(cfg.log, "Revisión manual: timeout, tarea "
                                      "marcada [B]")
                        _incidencia(cfg, "revision_timeout",
                                    "timeout en revisión manual del diff",
                                    tarea=tarea, iteracion=iteracion,
                                    rama=rama_tarea)
                        break
                    revertir(cfg.proyecto)
                    pre = (f"El diff fue rechazado en revisión manual: "
                           f"{_RECHAZO_MOTIVO['txt']}. Corrige esto en tu "
                           "siguiente intento. ")
                    logx(cfg.log, "REVISIÓN MANUAL RECHAZADO, reintentando...")
            else:
                logx(cfg.log, f"GATE FALLÓ tras el agente (intento {intento})")
                print(f"[dedalo] ✗ la tarea no pasó el gate "
                      f"(intento {intento}/{cfg.max_reintentos})")
                fb = _leer(gate_out)
                _append_log(cfg, fb)
                sin_ruido = [li for li in fb.splitlines()
                             if not re.match(r"^\[GATE\] (✓|⚠)", li)]
                resumen_gate = " ".join(sin_ruido[-15:])[:500]
                _incidencia(cfg, "gate_fail",
                            resumen_gate or "gate falló sin detalle",
                            tarea=tarea, iteracion=iteracion, rama=rama_tarea)
                if resumen_gate:
                    pre = (f"El gate falló con: {resumen_gate}. El detalle "
                           "completo está en progreso.log. Corrige esto en tu "
                           "siguiente intento. ")
                    logx(cfg.log, "Feedback del gate inyectado para siguiente "
                                  "intento")
                try:
                    os.unlink(gate_out)
                    gate_out = None
                except OSError:
                    pass

        logx(cfg.log, f"Costo iteración {iteracion}: {costo_iter} USD")
        snapshot(cfg.proyecto, after)
        try:
            if gate_out:
                os.unlink(gate_out)
        except OSError:
            pass

        if hecho == 1:
            nuevos, _b = cambios_entre(before, after)
            if nuevos:
                subj = "dedalo: " + tarea[:40]
                rc_c = commit_tarea(cfg.proyecto, nuevos, subj, tarea)
                if rc_c == 0:
                    logx(cfg.log, f"commit en {rama_tarea}: {subj}")
                    print(f"[dedalo] ✔ commit: {subj}")
                else:
                    logx(cfg.log, f"⚠ commit falló en {rama_tarea} (rc={rc_c})")
            else:
                logx(cfg.log, "tarea completada sin cambios nuevos")
                print("[dedalo] ✔ tarea completada sin cambios nuevos")

            if (checkout(cfg.proyecto, rama_run) == 0
                    and merge_ff(cfg.proyecto, rama_tarea) == 0):
                borrar_rama(cfg.proyecto, rama_tarea)
                logx(cfg.log, f"mergeada {rama_tarea} -> {rama_run}")
                _mapear(cfg)
                logx(cfg.log, f"mapeo.txt actualizado tras {tarea}")
                _marcar(cfg, "x")
            else:
                mensaje(cfg, f"[dedalo] ⚠ merge fallido; rama {rama_tarea} "
                             "conservada y tarea marcada [B].")
                _marcar(cfg, "B")
                _incidencia(cfg, "merge_fail",
                            f"git merge --ff-only {rama_tarea} -> {rama_run} "
                            "falló; rama conservada",
                            tarea=tarea, iteracion=iteracion, rama=rama_tarea)
                registrar_leccion(
                    cfg.lecciones, f"Merge fallido: {tarea}",
                    f"git merge --ff-only {rama_tarea} -> {rama_run} falló; "
                    "rama conservada.",
                    "La rama de la tarea sigue en "
                    f"{rama_tarea}; revisar conflictos o historial.",
                    "Resolver el merge manualmente o ajustar la base si es "
                    "necesario.")
                logx(cfg.log, "lección registrada (merge fallido)")
        else:
            checkout(cfg.proyecto, rama_run)
            borrar_rama(cfg.proyecto, rama_tarea, fuerza=True)
            revertir(cfg.proyecto)
            _marcar(cfg, "B")
            logx(cfg.log, f"tarea BLOQUEADA: {tarea} (rama {rama_tarea} "
                          "descartada)")
            print(f"[dedalo] ✗ tarea bloqueada tras {cfg.max_reintentos} "
                  "intentos. Marcada [B] en plan.md")
            alerta(cfg.voz, f"Tarea bloqueada: {tarea}")
            motivo = cfg.ultimo_motivo or {}
            detalle = (
                f"{motivo.get('tipo', 'fallo')} en la iteración {iteracion}: "
                f"{motivo.get('motivo') or 'sin detalle'}"
                if motivo else
                f"gate.sh/revisor fallaron en la iteración {iteracion}.")
            _incidencia(cfg, "bloqueada", detalle,
                        tarea=tarea, iteracion=iteracion, rama=rama_tarea)
            registrar_leccion(
                cfg.lecciones, f"Tarea bloqueada: {tarea}",
                "El agente no cumplió el criterio tras "
                f"{cfg.max_reintentos} intentos.",
                detalle,
                "Reformular la tarea en plan.md, dividirla en pasos más "
                "pequeños o revisar los criterios.")
            logx(cfg.log, "lección registrada en lecciones.md (tarea bloqueada)")

        costo_total = suma_coste(costo_total, cfg.costo_por_iter)
        logx(cfg.log, f"Costo estimado acumulado: {costo_total} USD")
        print(f"[dedalo] 💰 Costo estimado acumulado: {costo_total} USD")
        for f in (before, after, out, out + ".err"):
            try:
                os.unlink(f)
            except OSError:
                pass

    # --- Integrar el trabajo en la rama destino (--trabajo distinta del run) ---
    if cfg.rama_trabajo and cfg.rama_trabajo != rama_run:
        print(f"[dedalo] Integrando {rama_run} -> {cfg.rama_trabajo}")
        if (checkout(cfg.proyecto, cfg.rama_trabajo) == 0 and
                run_git(cfg.proyecto, "merge", "-q", "--no-ff", rama_run,
                        "-m", f"dedalo: integrar {rama_run}")[0] == 0):
            logx(cfg.log, f"integrado {rama_run} -> {cfg.rama_trabajo}")
        else:
            mensaje(cfg, f"[dedalo] ⚠ no se pudo integrar en "
                         f"{cfg.rama_trabajo}; el trabajo queda en {rama_run}")

    if cfg.push:
        asegurar_remote_origin(cfg)
        rc, _, _ = run_git(cfg.proyecto, "remote", "get-url", "origin")
        if rc == 0:
            push_rama = cfg.rama_trabajo or rama_run
            if run_git(cfg.proyecto, "push", "-u", "origin", push_rama,
                       timeout=300)[0] == 0:
                logx(cfg.log, f"push: origin/{push_rama}")
                print(f"[dedalo] ✔ push OK: origin/{push_rama}")
                if cfg.rama_trabajo:
                    print(f"[dedalo] abre el PR de {push_rama} -> "
                          f"{cfg.rama_base}")
                else:
                    print(f"[dedalo] abre el PR de {rama_run} -> "
                          f"{cfg.rama_base}")
            else:
                mensaje(cfg, f"[dedalo] ⚠ falló el push a origin/"
                             f"{push_rama}. El trabajo queda local.")
        else:
            mensaje(cfg, "[dedalo] ℹ sin remote origin (repo no creado). "
                         "Trabajo queda local.")

    print()
    resumen = _resumen_bloqueadas(cfg)
    if resumen:
        print("\n".join(resumen))
        _append_log(cfg, "\n".join(resumen))
    print("== RESUMEN (final de progreso.log) ==")
    print("\n".join(_leer(cfg.log).splitlines()[-25:]))
    logx(cfg.log, f"== DEDALO FINALIZADO (iter={iteracion}, "
                  f"rama={rama_run}, costo≈{costo_total}) ==")
    alerta(cfg.voz, "Dédalo finalizado")
    return 0


def _gh_api_owner(token):
    req = urllib.request.Request(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {token}",
                 "User-Agent": "dedalo"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return (json.load(r) or {}).get("login") or ""
    except Exception:
        return ""


def _gh_api_crear_repo(owner, nombre, token):
    data = json.dumps({"name": nombre, "private": True,
                       "auto_init": False}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.github.com/user/repos", data=data,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json",
                 "User-Agent": "dedalo"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return b"ssh_url" in r.read()
    except Exception:
        return False


def asegurar_remote_origin(cfg):
    """Port de _asegurar_remote_origin(): crea repo en GitHub si no hay
    origin (gh preferido, fallback GITHUB_TOKEN vía API)."""
    rc, _, _ = run_git(cfg.proyecto, "remote", "get-url", "origin")
    if rc == 0:
        return
    nombre = os.path.basename(os.path.normpath(cfg.proyecto))
    env = cfg.environ
    if shutil.which("gh"):
        st = subprocess.run(["gh", "auth", "status"], capture_output=True,
                            env=env)
        if st.returncode == 0:
            owner = subprocess.run(["gh", "api", "user", "--jq", ".login"],
                                   capture_output=True, text=True,
                                   env=env).stdout.strip()
            if owner:
                crea = subprocess.run(
                    ["gh", "repo", "create", f"{owner}/{nombre}", "--private"],
                    capture_output=True, env=env)
                if crea.returncode == 0:
                    print(f"[dedalo] ✔ repo creado en GitHub: "
                          f"{owner}/{nombre}")
                    run_git(cfg.proyecto, "remote", "add", "origin",
                            f"https://github.com/{owner}/{nombre}.git")
                    logx(cfg.log, "repo creado y remote origin configurado: "
                                  f"https://github.com/{owner}/{nombre}.git")
                    return
            mensaje(cfg, "[dedalo] ⚠ no se pudo crear repo con gh "
                         "(respuesta API)")
    token = env.get("GITHUB_TOKEN", "") or ""
    if token:
        print(f"[dedalo] Creando repo GitHub: {nombre} ...")
        owner = _gh_api_owner(token)
        if owner and _gh_api_crear_repo(owner, nombre, token):
            url = f"git@github.com:{owner}/{nombre}.git"
            run_git(cfg.proyecto, "remote", "add", "origin", url)
            print(f"[dedalo] ✔ repo creado en GitHub: {owner}/{nombre}")
            logx(cfg.log, f"repo creado y remote origin configurado: {url}")
        else:
            mensaje(cfg, "[dedalo] ⚠ no se pudo crear repo (respuesta "
                         "API)")
    else:
        registrar_leccion(
            cfg.lecciones, "GitHub: remote origin ausente",
            "No hay gh autenticado ni GITHUB_TOKEN para crear repo "
            "automático.",
            "Crea el repo manualmente en GitHub y ejecuta: "
            "git remote add origin <url>",
            "dedalo.sh tiene asistencia para crear el repo con "
            "gh/GITHUB_TOKEN.")
        logx(cfg.log, "lección registrada: remote origin ausente (sin "
                      "credenciales)")


def _esperar_revision_manual(cfg, tarea):
    """Port de esperar_revision_manual(): devuelve 0 aprobado, 2 timeout,
    1 rechazado (deja el motivo en _RECHAZO_MOTIVO), 4 sin internet
    (aborta el run como `exit 4` del script)."""
    if cfg.revision_manual != "1":
        return 0
    dir_rev = os.path.join(cfg.proyecto, ".dedalo_review")
    os.makedirs(dir_rev, exist_ok=True)
    _, diff_all, _ = run_git(cfg.proyecto, "diff", "--stat")
    _, diff_full, _ = run_git(cfg.proyecto, "diff")
    with open(os.path.join(dir_rev, "diff.txt"), "w", encoding="utf-8") as f:
        f.write(diff_all + "\n" + diff_full)
    with open(os.path.join(dir_rev, "tarea.txt"), "w", encoding="utf-8") as f:
        f.write(tarea)
    with open(os.path.join(dir_rev, "waiting"), "w", encoding="utf-8") as f:
        f.write("waiting")
    print(f"[dedalo] ⏸ Esperando revisión manual en {dir_rev}...")
    logx(cfg.log, f"ESPERANDO REVISIÓN MANUAL: {tarea}")

    esperado = 0
    while not os.path.exists(os.path.join(dir_rev, "decision")):
        time.sleep(2)
        esperado += 2
        if esperado % 30 == 0 and not net.hay_internet():
            mensaje(cfg, "[dedalo] ✗ sin internet durante la revisión "
                         "manual: abortando.")
            logx(cfg.log, "ABORTADO: sin internet durante revisión manual")
            alerta(cfg.voz, "Sin internet, se aborta el dedalo")
            for f in ("waiting", "decision"):
                try:
                    os.unlink(os.path.join(dir_rev, f))
                except OSError:
                    pass
            return 4
        if (cfg.timeout_revision_manual > 0
                and esperado >= cfg.timeout_revision_manual):
            mensaje(cfg, f"[dedalo] ✗ timeout de revisión manual "
                         f"({cfg.timeout_revision_manual}s): tarea bloqueada.")
            logx(cfg.log, "REVISIÓN MANUAL: timeout sin respuesta")
            alerta(cfg.voz, "Revisión manual sin respuesta, tarea marcada "
                            "como bloqueada")
            for f in ("waiting", "decision"):
                try:
                    os.unlink(os.path.join(dir_rev, f))
                except OSError:
                    pass
            return 2
    decision = _leer(os.path.join(dir_rev, "decision"))
    for f in ("waiting", "decision"):
        try:
            os.unlink(os.path.join(dir_rev, f))
        except OSError:
            pass
    if decision.startswith("APPROVE"):
        print("[dedalo] ✔ Diff aprobado manualmente")
        logx(cfg.log, "REVISIÓN MANUAL: APROBADO")
        return 0
    if decision.startswith("REJECT"):
        motivo = decision[len("REJECT"):].strip()
        print(f"[dedalo] ✗ Diff rechazado: {motivo}")
        logx(cfg.log, f"REVISIÓN MANUAL: RECHAZADO - {motivo}")
        _RECHAZO_MOTIVO["txt"] = motivo
        return 1
    print(f"[dedalo] ⚠ Decisión desconocida: {decision}")
    return 1


def main(argv=None):
    args = parse_args(argv)
    cfg = Config(args)
    return run(cfg)


if __name__ == "__main__":
    sys.exit(main())
