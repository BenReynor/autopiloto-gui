"""Consulta de los modelos disponibles de opencode.

La lista cambia con cada versión de opencode, así que se consulta en vivo con
`opencode models` en lugar de mantenerla fija en el código.
"""

import shutil
import subprocess

CLI_OPENCODE = shutil.which("opencode") or "opencode"
MODELO_SUGERIDO = "opencode/big-pickle"


def lista_modelos():
    """Devuelve la lista de modelos provider/model que soporta opencode."""
    try:
        out = subprocess.run([CLI_OPENCODE, "models"], capture_output=True,
                             text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
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