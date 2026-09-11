"""Consulta de los modelos disponibles de opencode.

La lista cambia con cada versión de opencode, así que se consulta en vivo con
`opencode models` en lugar de mantenerla fija en el código.

Para proveedores sin credenciales (openai, anthropic, ...) se usa el catálogo
de models.dev (la misma fuente que usa opencode), cacheado en disco.
"""

import json
import os
import shutil
import subprocess
import time
import urllib.request

MODELO_SUGERIDO = "opencode/big-pickle"

CATALOGO_URL = "https://models.dev/api.json"
CATALOGO_HORAS = 24 * 7

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


def _ruta_catalogo():
    ruta = os.path.join(os.path.expanduser("~/.config/autopiloto"),
                        "models_dev.json")
    return ruta


def leer_catalogo():
    """Catálogo models.dev cacheado (descarga si falta o es viejo=7 días)."""
    ruta = _ruta_catalogo()
    if (os.path.exists(ruta)
            and time.time() - os.path.getmtime(ruta) < CATALOGO_HORAS * 3600):
        try:
            with open(ruta, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    try:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        req = urllib.request.Request(
            CATALOGO_URL,
            headers={"User-Agent": "autopiloto-gui/2.0"}
        )
        with urllib.request.urlopen(req, timeout=25) as r:
            datos = json.loads(r.read().decode("utf-8"))
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False)
        return datos
    except (OSError, ValueError):
        if os.path.exists(ruta):
            try:
                with open(ruta, encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                return {}
        return {}


def nombres_proveedores():
    """Empresas disponibles: las de opencode más las del catálogo models.dev."""
    detectados = sorted({m.split("/", 1)[0] for m in lista_modelos()
                         if "/" in m})
    catalogo = leer_catalogo()
    for prov in PROVEEDORES_CATALOGO:
        if prov in catalogo and prov not in detectados:
            detectados.append(prov)
    return detectados


PROVEEDORES_CATALOGO = [
    "opencode", "google", "openai", "anthropic", "xai", "groq",
    "together", "deepseek", "azure", "bedrock", "ollama", "lmstudio",
    "mistral", "github",
]


def lista_modelos_proveedor(proveedor):
    """Modelos de un proveedor: `opencode models <prov>` y si falla, models.dev."""
    proveedor = (proveedor or "").strip()
    if not proveedor:
        return []
    try:
        out = subprocess.run([_cli_opencode(), "models", proveedor],
                             capture_output=True, text=True, timeout=30)
        if out.returncode == 0:
            modelos = []
            for linea in out.stdout.splitlines():
                linea = linea.strip()
                if "/" in linea:
                    modelos.append(linea.split("/", 1)[1])
            if modelos:
                return modelos
    except (OSError, subprocess.TimeoutExpired):
        pass
    catalogo = leer_catalogo()
    prov = catalogo.get(proveedor)
    if isinstance(prov, dict):
        modelos = prov.get("models")
        if isinstance(modelos, dict):
            return sorted(modelos)
    return []


def sugerido(modelos):
    """Elije un modelo por defecto: el sugerido si existe, si no el primero."""
    if not modelos:
        return MODELO_SUGERIDO
    if MODELO_SUGERIDO in modelos:
        return MODELO_SUGERIDO
    return modelos[0]