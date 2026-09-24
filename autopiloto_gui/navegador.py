"""Navigator automático: busca contexto relevante antes de cada tarea.

Usa opencode en modo 'navigate' para encontrar archivos, tests y endpoints
relevantes a la tarea. Se ejecuta en la GUI (hilo de fondo) antes de lanzar
el agente principal, y su salida se inyecta en el PROMPT del agente.
"""

import os
import shutil
import subprocess

from . import configuracion as cfg


def _cli_opencode():
    encontrado = shutil.which("opencode")
    if encontrado:
        return encontrado
    for ruta in [
        "~/.opencode/bin/opencode",
        "~/.local/bin/opencode",
        "/usr/local/bin/opencode",
        "/opt/opencode/bin/opencode",
    ]:
        expandida = os.path.expanduser(ruta)
        if os.path.isfile(expandida):
            return expandida
    return "opencode"


def buscar_contexto(ruta_proyecto: str, tarea: str, modelo: str, timeout: int | None = None) -> str:
    """
    Ejecuta opencode en modo navegación para encontrar contexto relevante.

    Args:
        ruta_proyecto: Ruta absoluta al proyecto.
        tarea: Texto de la tarea (línea de plan.md).
        modelo: Proveedor/modelo de opencode (ej. "opencode/big-pickle").
        timeout: Segundos máximos (default: cfg.TIMEOUT_NAVEGADOR).

    Returns:
        String con contexto formateado para inyectar en el PROMPT,
        o string vacío si falla/timeout.
    """
    if timeout is None:
        timeout = cfg.TIMEOUT_NAVEGADOR

    cli = _cli_opencode()
    prompt = (
        "Eres un NAVEGADOR en modo autopiloto.\n"
        "Tarea: " + tarea + "\n"
        "Repo: " + ruta_proyecto + "\n\n"
        "Tu trabajo: encuentra SOLO lo relevante para esta tarea.\n"
        "Devuelve una lista concisa (máx 30 líneas) con:\n"
        "1. Archivos que probablemente haya que tocar (rutas relativas).\n"
        "2. Tests existentes para esos archivos (rutas + nombre test).\n"
        "3. Endpoints API relacionados (si aplica).\n"
        "4. Modelos/servicios que interactúan.\n\n"
        "Formato:\n"
        "ARCHIVOS:\n  ruta/archivo.py\n  ...\nTESTS:\n  ruta/test_algo.py::test_algo\n  ...\nENDPOINTS:\n  GET /api/...\n  ...\nMODELOS/SERVICIOS:\n  Modulo.servicio\n  ...\n\n"
        "NO escribas código, NO expliques, SOLO lista. Si no hay nada, omite la sección."
    )

    cmd = [
        cli,
        "run",
        "--agent",
        "navigate",
        "--model",
        modelo,
        prompt,
    ]

    try:
        out = subprocess.run(
            cmd,
            cwd=ruta_proyecto,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""

    if out.returncode != 0:
        return ""

    salida = out.stdout.strip()
    if not salida:
        return ""

    # Formatear para inyección en PROMPT
    return (
        "\n=== CONTEXTO NAVEGADOR (auto) ===\n"
        + salida
        + "\n=== FIN CONTEXTO NAVEGADOR ===\n"
    )


def buscar_contexto_sync(ruta_proyecto: str, tarea: str, modelo: str | None = None) -> str:
    """Wrapper síncrono para uso en autopiloto.sh (bash)."""
    if modelo is None:
        modelo = cfg.MODELO_NAVEGADOR_SUGERIDO
    return buscar_contexto(ruta_proyecto, tarea, modelo)
