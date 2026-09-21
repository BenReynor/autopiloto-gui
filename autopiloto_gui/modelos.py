"""Consulta de los modelos disponibles de opencode.

La lista cambia con cada versión de opencode, así que se consulta en vivo con
`opencode models`. Los resultados se cachean durante la sesión: la UI no debe
lanzar subprocesos repetidos al construir los selectores. El botón de la app
invoca `invalidar_cache()` antes de refrescar.

Para proveedores sin credenciales (openai, anthropic, ...) se usa el catálogo
de models.dev (la misma fuente que usa opencode), cacheado en disco.
"""

import json
import os
import shutil
import subprocess
import time
import urllib.request

from . import configuracion as cfg

CATALOGO_URL = "https://models.dev/api.json"
CATALOGO_HORAS = 24 * 7

RUTAS_OPENCODE = [
    "~/.opencode/bin/opencode",
    "~/.local/bin/opencode",
    "/usr/local/bin/opencode",
    "/opt/opencode/bin/opencode",
]

PROVEEDORES_CATALOGO = [
    "opencode", "google", "openai", "anthropic", "xai", "groq",
    "together", "deepseek", "azure", "bedrock", "ollama", "lmstudio",
    "mistral", "github",
]

_modelos = None              # lista completa "provider/model" ([], no None)
_proveedores = None          # lista de proveedores detectados
_modelos_por_proveedor = {}  # proveedor -> lista de modelos


def _cli_opencode():
    encontrado = shutil.which("opencode")
    if encontrado:
        return encontrado
    for ruta in RUTAS_OPENCODE:
        expandida = os.path.expanduser(ruta)
        if os.path.isfile(expandida):
            return expandida
    return "opencode"


def _consultar_modelos():
    try:
        out = subprocess.run([_cli_opencode(), "models"], capture_output=True,
                             text=True, timeout=cfg.TIMEOUT_OPENCODE)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if out.returncode != 0:
        return []
    return [linea.strip() for linea in out.stdout.splitlines()
            if "/" in linea
            and not linea.startswith(("#", "--", "Usage"))]


def lista_modelos(forzar=False):
    """Devuelve la lista de modelos provider/model que soporta opencode."""
    global _modelos
    if _modelos is None or forzar:
        _modelos = _consultar_modelos() or []
    return _modelos


def _ruta_catalogo():
    return cfg.CATALOGO_MODELOS


def leer_catalogo():
    """Catálogo models.dev cacheado en disco (descarga si falta o es viejo)."""
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
        with urllib.request.urlopen(req, timeout=cfg.TIMEOUT_CATALOGO) as r:
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


def _consultar_proveedores():
    detectados = sorted({m.split("/", 1)[0] for m in lista_modelos()
                         if "/" in m})
    catalogo = leer_catalogo()
    for prov in PROVEEDORES_CATALOGO:
        if prov in catalogo and prov not in detectados:
            detectados.append(prov)
    return detectados


def nombres_proveedores(forzar=False):
    """Empresas disponibles: las de opencode más las del catálogo models.dev."""
    global _proveedores
    if _proveedores is None or forzar:
        _proveedores = _consultar_proveedores()
    return _proveedores


def _consultar_proveedor(proveedor):
    try:
        out = subprocess.run([_cli_opencode(), "models", proveedor],
                             capture_output=True, text=True,
                             timeout=cfg.TIMEOUT_OPENCODE)
        if out.returncode == 0:
            modelos = [linea.strip().split("/", 1)[1] for linea in
                       out.stdout.splitlines() if "/" in linea.strip()]
            if modelos:
                return modelos
    except (OSError, subprocess.TimeoutExpired):
        pass
    catalogo = leer_catalogo()
    prov = catalogo.get(proveedor)
    if isinstance(prov, dict) and isinstance(prov.get("models"), dict):
        return sorted(prov["models"])
    return []


def lista_modelos_proveedor(proveedor, forzar=False):
    """Modelos de un proveedor: `opencode models <prov>` y si falla, models.dev."""
    proveedor = (proveedor or "").strip()
    if not proveedor:
        return []
    if forzar:
        _modelos_por_proveedor.pop(proveedor, None)
    if proveedor not in _modelos_por_proveedor:
        _modelos_por_proveedor[proveedor] = _consultar_proveedor(proveedor)
    return _modelos_por_proveedor[proveedor]


def invalidar_cache():
    """Olvida los resultados caché; la siguiente consulta vuelve a la red."""
    global _modelos, _proveedores
    _modelos = None
    _proveedores = None
    _modelos_por_proveedor.clear()


def sugerido(modelos):
    """Elije un modelo por defecto: el sugerido si existe, si no el primero."""
    if not modelos:
        return cfg.MODELO_SUGERIDO
    if cfg.MODELO_SUGERIDO in modelos:
        return cfg.MODELO_SUGERIDO
    return modelos[0]
