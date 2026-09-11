"""Consulta de los modelos disponibles de opencode.

La lista cambia con cada versión de opencode, así que se consulta en vivo con
`opencode models` en lugar de mantenerla fija en el código.
"""

import os
import shutil
import subprocess

MODELO_SUGERIDO = "opencode/big-pickle"

RUTAS_OPENCODE = [
    "~/.opencode/bin/opencode",
    "~/.local/bin/opencode",
    "/usr/local/bin/opencode",
    "/opt/opencode/bin/opencode",
]


def _cli_opencode():
    encontrado = shutil.which("opencode")
    if encontrado:
        return encontrado
    for ruta in RUTAS_OPENCODE:
        expandida = os.path.expanduser(ruta)
        if os.path.isfile(expandida):
            return expandida
    return "opencode"


def lista_modelos():
    """Devuelve la lista de modelos provider/model que soporta opencode."""
    try:
        out = subprocess.run([_cli_opencode(), "models"], capture_output=True,
                             text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if out.returncode != 0:
        return []
    modelos = []
    for linea in out.stdout.splitlines():
        linea = linea.strip()
        if "/" in linea and not linea.startswith(("#", "--", "Usage")):
            modelos.append(linea)
    return modelos


def sugerido(modelos):
    """Elije un modelo por defecto: el sugerido si existe, si no el primero."""
    if not modelos:
        return MODELO_SUGERIDO
    if MODELO_SUGERIDO in modelos:
        return MODELO_SUGERIDO
    return modelos[0]