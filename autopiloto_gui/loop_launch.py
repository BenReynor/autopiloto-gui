#!/usr/bin/env python3
"""Preparación del lanzamiento del loop (compartida por la GUI y el MCP).

Extrae de app.py la construcción del COMANDO y del ENTORNO del motor para que
el panel Qt y el servidor MCP (`autopiloto_gui.mcp_server`) lancen el mismo
proceso con la misma configuración. Sin dependencias de PySide: el servidor
MCP importa este módulo sin arrastrar Qt.

El contrato de entorno es el de autopiloto.sh / loop.Config: mismas variables
MAX_ITER, AGENTE_TAREA, AGENTES_PREFERIDOS, MODELO_*, NAVEGADOR, REVISION_DUAL,
VOZ, MAX_COSTO, COSTO_POR_ITER, REVISION_MANUAL y CLI_<AGENTE>.
"""

import os
import sys

from . import configuracion as cfg
from . import modelos

# Variable de entorno por cada CLI de agente (autopiloto.sh las soporta).
MAPA_CLI = {
    "opencode": "CLI_OPENCODE",
    "codex": "CLI_CODEX",
    "claude": "CLI_CLAUDE",
}


def raiz_codigo():
    """Raíz del repo de la GUI: `autopiloto_gui` es un subdirectorio suyo."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def argv_motor(frozen, args):
    """Comando (programa, argv) que lanza el motor del loop.

    En el código fuente: `python -m autopiloto_gui.loop [args]`. En el
    binario de PyInstaller `-m` no resuelve el módulo (va empaquetado en el
    exe): el entrypoint interpreta `--autopiloto-loop` y llama a
    `loop.main(argv[1:])`.
    """
    if frozen:
        return sys.executable, ["--autopiloto-loop"] + list(args)
    return sys.executable, ["-m", "autopiloto_gui.loop"] + list(args)


def args_cli(conf):
    """Argumentos de línea de comandos del motor a partir de la config."""
    args = []
    if conf.get("hasta"):
        args += ["--hasta", conf["hasta"]]
    if conf.get("padre"):
        args += ["--padre", conf["padre"]]
    if conf.get("trabajo"):
        args += ["--trabajo", conf["trabajo"]]
    if conf.get("push"):
        args.append("--push")
    return args


def resolver_agentes(conf, detectados):
    """(agente_tarea, agente_revisor) resolviendo "auto" con lo detectado.

    Un selector en "auto" no es el nombre del agente: se resuelve aquí con la
    misma lista de preferencia que usa autopiloto.sh, para que el log y el
    motivo de lanzamiento coincidan con lo que de verdad se ejecuta.
    """
    auto = detectados[0] if detectados else ""
    tarea = auto if conf.get("agente_cli", cfg.AGENTE_DEFECTO) == "auto" \
        else conf["agente_cli"]
    revisor = auto if conf.get("revisor_cli", cfg.AGENTE_DEFECTO) == "auto" \
        else conf["revisor_cli"]
    return tarea, revisor


def construir_entorno(conf, nav, detectados, environ, frozen=None):
    """Entorno (dict) para el proceso del motor.

    `environ` es el entorno base (el del QProcess en la GUI, os.environ en el
    MCP). `nav` = {"activo": bool, "modelo": str}. `detectados` es la lista de
    agentes operativos (modelos.agentes_operativos()).
    """
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False))
    env = dict(environ)

    # El agente CLI se pasa explícito. Si no está en el PATH (p. ej. GUI
    # abierta sin ~/.opencode/bin) se resuelve su ruta absoluta a CLI_<AGENTE>
    # (que autopiloto.sh ya soporta) y se añade su dir al PATH del subproceso.
    dirs_extra = set()
    for clave, var in MAPA_CLI.items():
        binario = modelos.ruta_binario(clave)
        if binario:
            env[var] = binario
            dirs_extra.add(os.path.dirname(binario))
    if dirs_extra:
        # os.pathsep: con ":" fijo el PATH del loop se corrompía en Windows
        # (que separa con ";").
        env["PATH"] = os.pathsep.join(sorted(dirs_extra)) + (
            os.pathsep + env["PATH"] if env.get("PATH") else "")

    agente_tarea, agente_revisor = resolver_agentes(conf, detectados)
    env["MAX_ITER"] = str(conf.get("iteraciones", cfg.LAUNCH_DEFECTO["iteraciones"]))
    env["AGENTE_TAREA"] = agente_tarea
    env["AGENTE_REVISOR"] = agente_revisor
    # AGENTES_PREFERIDOS sólo con agentes utilizables: si el revisor está en
    # "auto", autopiloto.sh busca otro en esta lista, y no debe caer en un CLI
    # instalado pero sin sesión (abortaría el loop).
    env["AGENTES_PREFERIDOS"] = " ".join(detectados)
    # El juez sigue al agente de la tarea salvo elección explícita.
    env["AGENTE_JUEZ"] = agente_tarea
    # Solo pasa MODELO_* si la selección es provider/model completo Y el agente
    # es opencode (codex y claude no aceptan --model aquí).
    modelo_tarea = (conf.get("agente", "") if "/" in conf.get("agente", "")
                    and agente_tarea == "opencode" else "")
    modelo_revisor = (conf.get("revisor", "") if "/" in conf.get("revisor", "")
                      and agente_revisor == "opencode" else "")
    env["MODELO_TAREA"] = modelo_tarea
    env["MODELO_REVISOR"] = modelo_revisor
    env["NAVEGADOR"] = "1" if nav.get("activo") else "0"
    env["MODELO_NAVEGADOR"] = (nav.get("modelo") or "") if nav.get("activo") else ""
    env["REVISION_DUAL"] = "1" if conf.get("dual", True) else "0"
    env["VOZ"] = "1" if conf.get("voz", False) else "0"
    env["MAX_COSTO"] = str(conf.get("costo_max", 0))
    env["COSTO_POR_ITER"] = str(
        conf.get("costo_iter", cfg.LAUNCH_DEFECTO["costo_iter"]))
    env["REVISION_MANUAL"] = "1" if conf.get("revision_manual", False) else "0"
    return env


def preparar(conf, nav=None, environ=None, frozen=None):
    """Plan completo de lanzamiento del motor.

    Devuelve un dict con:
      · detectados: agentes CLI utilizables (vacío ⇒ el llamante aborta)
      · agente_tarea / agente_revisor / modelo_tarea / modelo_revisor
      · env: entorno (dict) ya con PATH, CLI_* y PYTHONPATH (si no frozen)
      · programa / argv: comando a ejecutar
    """
    if environ is None:
        environ = dict(os.environ)
    else:
        environ = dict(environ)
    nav = nav or {}
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False))

    detectados = modelos.agentes_operativos()
    env = construir_entorno(conf, nav, detectados, environ, frozen)
    if not frozen:
        env["PYTHONPATH"] = raiz_codigo() + (
            os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    agente_tarea, agente_revisor = resolver_agentes(conf, detectados)
    programa, argv = argv_motor(frozen, args_cli(conf))
    modelo_tarea = (conf.get("agente", "") if "/" in conf.get("agente", "")
                    and agente_tarea == "opencode" else "")
    modelo_revisor = (conf.get("revisor", "") if "/" in conf.get("revisor", "")
                      and agente_revisor == "opencode" else "")
    return {
        "detectados": detectados,
        "agente_tarea": agente_tarea,
        "agente_revisor": agente_revisor,
        "modelo_tarea": modelo_tarea,
        "modelo_revisor": modelo_revisor,
        "env": env,
        "programa": programa,
        "argv": argv,
    }


def config_de_proyecto(nombre):
    """Config de lanzamiento fusionada (defaults + lo guardado) de un proyecto.

    El servidor MCP la usa para lanzar con los mismos ajustes que el usuario
    dejó en la GUI (`proyectos[nombre]["config"]["lanzamiento"]`). Devuelve
    `(conf, nav)`, donde nav replica `navegador_config()` de la GUI.
    """
    from . import proyectos as proy

    local = proy.leer_config_proyecto(nombre)
    lanz = dict(cfg.LAUNCH_DEFECTO)
    lanz.update(local.get("lanzamiento") or {})
    lanz.setdefault("agente", "")
    lanz.setdefault("revisor", "")
    lanz.setdefault("agente_cli", cfg.AGENTE_DEFECTO)
    lanz.setdefault("revisor_cli", cfg.AGENTE_DEFECTO)
    lanz.setdefault("revision_manual", False)
    nav = {"activo": bool(lanz.get("nav")), "modelo": lanz.get("nav_modelo") or ""}
    return lanz, nav
