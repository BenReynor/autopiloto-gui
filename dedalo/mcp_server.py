#!/usr/bin/env python3
"""Servidor MCP (Model Context Protocol) de Dédalo.

Expone el estado de los proyectos y las acciones del loop (instalar, gate,
iniciar/parar, resolver la revisión manual) a un cliente MCP —p. ej. un agente
"piloto"— por stdio (JSON-RPC). Es un proceso sin Qt: sólo importa módulos sin
PySide, así que puede arrancarse headless.

Transporte: stdio (no abre puertos). Arranque:

    python -m dedalo.mcp_server

La revisión manual del loop se resuelve escribiendo en
`<proyecto>/.dedalo_review/decision` (APPROVE / "REJECT <motivo>"), que es
justo lo que hace `resolver_revision`: el agente piloto ocupa el asiento del
humano cuando el loop pausa.

Nota de seguridad: `iniciar_loop` lanza el motor en segundo plano con
`start_new_session=True` y sus stdout/stderr van a /dev/null —NUNCA a la
stdio del servidor, o corromperían el canal JSON-RPC.
"""

import json
import os
import subprocess
import sys
import time

from . import configuracion as cfg
from . import loop_launch, loop_proceso, modelos, net, plantillas, proyectos
from .gate import argv_gate

try:
    from mcp.server.mcpserver import MCPServer
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "El servidor MCP necesita la dependencia opcional 'mcp'. "
        "Instálala con: pip install 'dedalo[mcp]'"
    ) from exc

# Manual curado del programa: se entrega como `instructions` en el initialize
# (contexto que los clientes MCP muestran al modelo) y como recurso
# `dedalo://manual`. Va embebido en el código para estar disponible también en
# la app empaquetada/frozen, donde docs/ no se distribuye.
MANUAL = """\
Dédalo es un panel de escritorio (PySide6) y un servidor MCP para orquestar
agentes de IA CLI (opencode, codex, claude) que trabajan de forma autónoma
sobre un proyecto, iterando tarea a tarea sobre `plan.md`.

CÓMO FUNCIONA EL LOOP
- Toma la primera tarea pendiente de `plan.md`, se la pasa a un agente y,
  tras ejecutarla, corre el "gate" (tests + lint) del proyecto.
- Sólo commitea si el gate pasa; si falla, la iteración no commitea.
- Con `revision_manual` activo, el loop PAUSA antes de commitear y espera una
  decisión (APPROVE / REJECT) del humano o de un agente piloto.
- Si no hay internet, el loop se detiene.

FICHEROS DEL PROYECTO (los mismos que expone dedalo://{nombre}/{fichero})
- plan.md ......... tareas: `- [ ]` pendiente, `- [x]` hecha, `- [B]` bloqueada.
- lecciones.md .... aprendizajes acumulados entre iteraciones.
- CONTEXTO.md ..... estado resumido / notas de continuidad.
- progreso.log .... traza de las iteraciones (texto).
- metrics.jsonl ... métricas por iteración (una línea JSON cada una).
- incidencias.jsonl incidencias estructuradas (una línea JSON cada una).
- mapeo.txt ....... mapa/índice del proyecto.

CONCEPTOS
- "proyecto": directorio registrado en Dédalo (nombre -> ruta).
- "gate": comando de verificación del proyecto (tests + lint).
- "revisión manual": pausa del loop esperando aprobación del diff.
- "agente tarea" / "agente revisor": CLIs asignados a ejecutar y a revisar.

FLUJO TÍPICO CON ESTAS HERRAMIENTAS
1. listar_proyectos / estado_proyecto: qué hay y en qué estado.
2. leer_plan / leer_contexto / leer_lecciones / cola_log: contexto.
3. instalar_proyecto: crear y registrar un proyecto nuevo (opcional).
4. iniciar_loop: arrancar el loop en segundo plano (devuelve el pid).
5. estado_loop / cola_log: seguir el avance.
6. resolver_revision(APPROVE|REJECT): resolver una revisión pendiente.
7. correr_gate: validar a mano; detener_loop: parar el loop.

El texto completo de este manual está en el recurso `dedalo://manual`.
"""

mcp = MCPServer("dedalo", instructions=MANUAL)

# Ficheros que un cliente puede leer vía el recurso dedalo://{nombre}/{fichero}.
FICHEROS_RECURSO = (
    "plan.md",
    "lecciones.md",
    "CONTEXTO.md",
    "progreso.log",
    "metrics.jsonl",
    "incidencias.jsonl",
    "mapeo.txt",
)

# Loop en marcha por proyecto: nombre → subprocess.Popen. El pid se persiste
# además en CONFIG_DIR para que un servidor MCP reiniciado aún pueda pararlo.
_LOOPS: dict[str, subprocess.Popen] = {}
_PIDS_RUTA = os.path.join(cfg.CONFIG_DIR, "mcp_loops.json")
RC_TIMEOUT_LOOP = loop_proceso.RC_TIMEOUT


def _json(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _ruta_de(nombre):
    """Ruta del proyecto en el registro (raises ValueError si no existe)."""
    proy = proyectos.cargar().get(nombre)
    if not proy or not proy.get("ruta"):
        raise ValueError(f"proyecto desconocido: {nombre!r}")
    return proy["ruta"]


def _leer_texto(ruta):
    try:
        with open(ruta, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _cola(texto, lineas):
    return "\n".join(texto.splitlines()[-lineas:])


def _leer_jsonl(ruta):
    """Lista de dicts de un .jsonl; ignora líneas corruptas o vacías."""
    if not os.path.isfile(ruta):
        return []
    datos = []
    with open(ruta, encoding="utf-8", errors="replace") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            try:
                obj = json.loads(linea)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                obj["_crudo"] = linea
                datos.append(obj)
    return datos


def _ruta_de_fichero(nombre, fichero):
    return os.path.join(_ruta_de(nombre), fichero)


def _pids():
    try:
        with open(_PIDS_RUTA, encoding="utf-8") as f:
            datos = json.load(f)
        return {k: int(v) for k, v in datos.items()}
    except (OSError, ValueError, TypeError):
        return {}


def _guardar_pid(nombre, pid):
    datos = _pids()
    datos[nombre] = int(pid)
    try:
        os.makedirs(cfg.CONFIG_DIR, exist_ok=True)
        with open(_PIDS_RUTA, "w", encoding="utf-8") as f:
            json.dump(datos, f)
    except OSError:
        pass


def _olvidar_pid(nombre):
    datos = _pids()
    datos.pop(nombre, None)
    try:
        with open(_PIDS_RUTA, "w", encoding="utf-8") as f:
            json.dump(datos, f)
    except OSError:
        pass


def _vivo(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _matar_pid(pid, espera=5):
    """TERM→KILL al grupo del proceso `pid` (lanzado con start_new_session)."""
    if os.name != "nt":
        import signal
        try:
            pgid = os.getpgid(pid)
        except (ProcessLookupError, PermissionError):
            return False
        for sig, pausa in ((signal.SIGTERM, espera), (signal.SIGKILL, 0)):
            try:
                os.killpg(pgid, sig)
            except (ProcessLookupError, PermissionError):
                return True
            if pausa:
                for _ in range(pausa):
                    time.sleep(1)
                    if not _vivo(pid):
                        return True
        return not _vivo(pid)
    proc = subprocess.Popen(["taskkill", "/PID", str(pid), "/T", "/F"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    proc.wait(timeout=10)
    return True


def _estado_loop(nombre):
    """Dict con el estado del loop del proyecto: corriendo, pid, revisión pendiente."""
    proc = _LOOPS.get(nombre)
    pid = proc.pid if proc and proc.poll() is None else _pids().get(nombre)
    if pid and not _vivo(pid):
        _olvidar_pid(nombre)
        pid = None
    fondo = os.path.join(_ruta_de(nombre), ".dedalo_review")
    pendiente = os.path.isfile(os.path.join(fondo, "waiting"))
    tarea = ""
    tarea_ruta = os.path.join(fondo, "tarea.txt")
    if pendiente and os.path.isfile(tarea_ruta):
        try:
            with open(tarea_ruta, encoding="utf-8", errors="replace") as f:
                tarea = f.read().strip()
        except OSError:
            tarea = ""
    return {
        "nombre": nombre,
        "corriendo": bool(pid),
        "pid": pid,
        "revision_pendiente": pendiente,
        "tarea_en_revision": tarea,
    }


# ---------------------------------------------------------------------------
# Herramientas de LECTURA
# ---------------------------------------------------------------------------

def listar_proyectos() -> str:
    """Lista los proyectos registrados: nombre, ruta y si la ruta existe."""
    reg = proyectos.cargar()
    return json.dumps([
        {"nombre": n, "ruta": d.get("ruta", ""), "existe": os.path.isdir(d.get("ruta", ""))}
        for n, d in reg.items()
    ], ensure_ascii=False, indent=2)


def estado_proyecto(nombre: str) -> str:
    """Resumen de un proyecto: plan, lecciones, contexto y estado del loop."""
    ruta = _ruta_de(nombre)
    from .plan import Plan as _Plan
    p = _Plan(os.path.join(ruta, "plan.md"))
    p.cargar()
    pend, hechas, bloq = p.conteo()
    lecciones = os.path.join(ruta, "lecciones.md")
    contexto = os.path.join(ruta, "CONTEXTO.md")
    return json.dumps({
        "nombre": nombre,
        "ruta": ruta,
        "existe": os.path.isdir(ruta),
        "plan": {"pendientes": pend, "hechas": hechas, "bloqueadas": bloq},
        "lecciones": {"existe": os.path.isfile(lecciones),
                      "bytes": os.path.getsize(lecciones) if os.path.isfile(lecciones) else 0},
        "contexto": {"existe": os.path.isfile(contexto),
                     "bytes": os.path.getsize(contexto) if os.path.isfile(contexto) else 0},
        "loop": _estado_loop(nombre),
    }, ensure_ascii=False, indent=2)


def leer_fichero(nombre: str, fichero: str) -> str:
    """Devuelve el contenido de un fichero permitido del proyecto.

    `fichero` debe estar en la lista blanca (plan.md, lecciones.md,
    CONTEXTO.md, progreso.log, metrics.jsonl, incidencias.jsonl, mapeo.txt).
    """
    if fichero not in FICHEROS_RECURSO:
        raise ValueError(
            f"fichero no permitido: {fichero!r}. Permitidos: {list(FICHEROS_RECURSO)}")
    return _leer_fichero(nombre, fichero)


def _leer_fichero(nombre, fichero):
    ruta = _ruta_de_fichero(nombre, fichero)
    if not os.path.isfile(ruta):
        return ""
    with open(ruta, encoding="utf-8", errors="replace") as f:
        return f.read()


def leer_incidencias(nombre: str, limite: int = 50) -> str:
    """Últimas incidencias estructuradas (incidencias.jsonl) del proyecto."""
    datos = _leer_incidencias(nombre, limite)
    return json.dumps(datos, ensure_ascii=False, indent=2)


def _leer_incidencias(nombre, limite):
    ruta = os.path.join(_ruta_de(nombre), "incidencias.jsonl")
    incidencias = _leer_jsonl(ruta)
    for inc in incidencias:
        inc.pop("_crudo", None)
    return incidencias[-max(1, int(limite)):]


def resumen_metricas(nombre: str) -> str:
    """Resumen de métricas del proyecto (progreso.log + metrics.jsonl)."""
    from .metricas import parsear_log as _parsear
    ruta = os.path.join(_ruta_de(nombre), "progreso.log")
    datos = _parsear(ruta)
    return json.dumps({
        "resumen": datos.get("resumen", {}),
        "iteraciones": datos.get("iteraciones", [])[-25:],
    }, ensure_ascii=False, indent=2)


def cola_log(nombre: str, lineas: int = 60) -> str:
    """Últimas `lineas` líneas de progreso.log."""
    ruta = os.path.join(_ruta_de(nombre), "progreso.log")
    if not os.path.isfile(ruta):
        return ""
    return _cola(_leer_fichero(nombre, "progreso.log"), lineas)


def estado_agentes() -> str:
    """Estado de cada agente CLI: instalado, ruta y si tiene sesión."""
    return json.dumps(modelos.estado_agentes(), ensure_ascii=False, indent=2)


def listar_modelos() -> str:
    """Modelos conocidos (catálogo opencode) con el sugerido primero."""
    return json.dumps({
        "sugerido": modelos.sugerido(modelos.lista_modelos()),
        "modelos": modelos.lista_modelos(),
    }, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Herramientas de ACCIÓN
# ---------------------------------------------------------------------------

def instalar_proyecto(ruta: str, nombre: str = "") -> str:
    """Instala las plantillas en `ruta`, inicializa git y registra el proyecto."""
    ruta = os.path.abspath(os.path.expanduser(ruta))
    os.makedirs(ruta, exist_ok=True)
    creados = plantillas.instalar(ruta)
    git = plantillas.inicializar_git(ruta)
    nombre = (nombre or os.path.basename(ruta.rstrip(os.sep))).strip()
    reg = proyectos.cargar()
    reg[nombre] = {"ruta": ruta}
    proyectos.guardar(reg)
    return json.dumps({"nombre": nombre, "ruta": ruta,
                       "creados": creados, "git": git},
                      ensure_ascii=False, indent=2)


def correr_gate(nombre: str, timeout_s: int = 1800) -> str:
    """Ejecuta el gate del proyecto (bloqueante, con timeout) y devuelve su salida."""
    ruta = _ruta_de(nombre)
    programa, argv = argv_gate(getattr(sys, "frozen", False), ruta, ruta)
    env = dict(os.environ)
    if not getattr(sys, "frozen", False):
        env["PYTHONPATH"] = loop_launch.raiz_codigo() + (
            os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    try:
        out = subprocess.run([programa] + argv, cwd=ruta, env=env,
                             capture_output=True, text=True,
                             timeout=max(1, int(timeout_s)))
        return json.dumps({"rc": out.returncode, "stdout": out.stdout,
                           "stderr": out.stderr},
                          ensure_ascii=False, indent=2)
    except subprocess.TimeoutExpired as e:
        return json.dumps({"rc": -1, "timeout": True,
                           "stdout": (e.stdout or "") if isinstance(e.stdout, str) else "",
                           "stderr": (e.stderr or "") if isinstance(e.stderr, str) else ""},
                          ensure_ascii=False, indent=2)


def iniciar_loop(nombre: str) -> str:
    """Lanza el loop en segundo plano para el proyecto (devuelve el pid)."""
    _ruta_de(nombre)
    if _estado_loop(nombre)["corriendo"]:
        return json.dumps({"iniciado": False, "motivo": "ya está corriendo",
                           **_estado_loop(nombre)}, ensure_ascii=False, indent=2)
    if not net.hay_internet():
        return json.dumps({"iniciado": False,
                           "motivo": "sin conexión a internet"},
                          ensure_ascii=False, indent=2)
    conf, nav = loop_launch.config_de_proyecto(nombre)
    plan = loop_launch.preparar(conf, nav)
    if not plan["detectados"]:
        return json.dumps({"iniciado": False, "detectados": [],
                           "motivo": "ningún agente CLI con sesión"},
                          ensure_ascii=False, indent=2)
    proc = subprocess.Popen(
        [plan["programa"]] + plan["argv"], cwd=_ruta_de(nombre),
        env=plan["env"], stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=(os.name != "nt"))
    _LOOPS[nombre] = proc
    _guardar_pid(nombre, proc.pid)
    conf, _ = loop_launch.config_de_proyecto(nombre)
    return json.dumps({
        "nombre": nombre, "pid": proc.pid,
        "agente_tarea": plan["agente_tarea"],
        "agente_revisor": plan["agente_revisor"],
        "revision_manual": bool(conf.get("revision_manual")),
    }, ensure_ascii=False, indent=2)


def estado_loop(nombre: str) -> str:
    """Estado del loop: corriendo, pid, revisión manual pendiente y su tarea."""
    return json.dumps(_estado_loop(nombre), ensure_ascii=False, indent=2)


def detener_loop(nombre: str, espera_s: int = 5) -> str:
    """Detiene el loop del proyecto (TERM→KILL a todo su grupo de procesos)."""
    estado = _estado_loop(nombre)
    if not estado["pid"]:
        return json.dumps({"nombre": nombre, "detenido": False,
                           "motivo": "no estaba corriendo"},
                          ensure_ascii=False, indent=2)
    proc = _LOOPS.pop(nombre, None)
    if proc and proc.poll() is None:
        loop_proceso.matar_grupo(proc, espera=max(0, int(espera_s)))
    else:
        _matar_pid(estado["pid"], espera=max(0, int(espera_s)))
    _olvidar_pid(nombre)
    return json.dumps({"nombre": nombre, "pid": estado["pid"], "detenido": True},
                      ensure_ascii=False, indent=2)


def resolver_revision(nombre: str, decision: str, motivo: str = "") -> str:
    """Resuelve la revisión manual pendiente escribiendo `.dedalo_review/decision`.

    `decision`: "APPROVE" (aceptar el diff) o "REJECT" (rechazar; usa `motivo`).
    Es lo que permite a un agente piloto ocupar el asiento del humano cuando el
    loop pausa esperando aprobación.
    """
    decision = decision.strip().upper()
    if decision not in ("APPROVE", "REJECT"):
        raise ValueError("decision debe ser APPROVE o REJECT")
    fondo = os.path.join(_ruta_de(nombre), ".dedalo_review")
    os.makedirs(fondo, exist_ok=True)
    texto = "APPROVE" if decision == "APPROVE" else "REJECT " + (motivo or "").strip()
    with open(os.path.join(fondo, "decision"), "w", encoding="utf-8") as f:
        f.write(texto)
    return json.dumps({"nombre": nombre, "decision": decision,
                       "detalle": texto.strip()}, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Recursos: dedalo://{nombre}/{fichero}
# ---------------------------------------------------------------------------

def leer_contexto(nombre: str) -> str:
    """Devuelve el contenido de `CONTEXTO.md` del proyecto (alias de leer_fichero)."""
    return _leer_fichero(nombre, "CONTEXTO.md")


def leer_plan(nombre: str) -> str:
    """Devuelve el contenido de `plan.md` del proyecto."""
    return _leer_fichero(nombre, "plan.md")


def leer_lecciones(nombre: str) -> str:
    """Devuelve el contenido de `lecciones.md` del proyecto."""
    return _leer_fichero(nombre, "lecciones.md")


def leer_recurso(nombre: str, fichero: str) -> str:
    """Contenido de un fichero permitido del proyecto (lectura por recurso)."""
    if fichero not in FICHEROS_RECURSO:
        raise ValueError(f"fichero no permitido: {fichero!r}")
    return _leer_fichero(nombre, fichero)


def manual() -> str:
    """Manual de Dédalo: qué es el programa y cómo usarlo (recurso dedalo://manual)."""
    return MANUAL


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------

def _registrar(server):
    for fn in (listar_proyectos, estado_proyecto, leer_fichero, leer_plan,
               leer_lecciones, leer_contexto, leer_incidencias, resumen_metricas,
               cola_log, estado_agentes, listar_modelos, instalar_proyecto,
               correr_gate, iniciar_loop, estado_loop, detener_loop,
               resolver_revision):
        server.tool()(fn)
    server.resource("dedalo://{nombre}/{fichero}",
                    name="fichero_proyecto",
                    description="Lee un fichero permitido del proyecto",
                    mime_type="text/markdown")(leer_recurso)
    server.resource("dedalo://manual",
                    name="manual",
                    title="Manual de Dédalo",
                    description="Qué es Dédalo y cómo usarlo",
                    mime_type="text/markdown")(manual)
    return server


_MCPSERVER = None


def servidor():
    """El MCPServer con las herramientas y recursos registrados (singleton)."""
    global _MCPSERVER
    if _MCPSERVER is None:
        from mcp.server.mcpserver import MCPServer
        _MCPSERVER = _registrar(MCPServer("dedalo", instructions=MANUAL))
    return _MCPSERVER


def main():
    """Arranca el servidor MCP por stdio."""
    servidor().run(transport="stdio")


if __name__ == "__main__":
    main()
