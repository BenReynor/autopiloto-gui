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
import re
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

_modelos: list[str] | None = None
_proveedores: list[str] | None = None
_modelos_por_proveedor: dict[str, list[str]] = {}


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


def ruta_binario(nombre):
    """Ruta absoluta del CLI de un agente, o "" si no está instalado.

    Busca en el PATH y, como los CLIs de agentes suelen instalarse en
    ~/.<agente>/bin sin tocar el PATH del shell, prueba ese fallback.
    """
    ruta = shutil.which(nombre)
    if ruta:
        return ruta
    if nombre in cfg.AGENTES_DISPONIBLES:
        candidata = os.path.expanduser(f"~/.{nombre}/bin/{nombre}")
        if os.path.isfile(candidata) and os.access(candidata, os.X_OK):
            return candidata
    return ""


def agentes_instalados(preferidos=None):
    """Agentes CLI disponibles en esta máquina, en orden de preferencia.

    `preferidos` = orden a respetar (por defecto, AGENTES_PREFERIDOS). Devuelve
    sólo los que existen de verdad, para que la GUI no ofrezca un agente que
    no se pueda ejecutar.
    """
    orden = preferidos or cfg.AGENTES_PREFERIDOS
    return [a for a in orden if a in cfg.AGENTES_DISPONIBLES and ruta_binario(a)]


def agentes_operativos(preferidos=None):
    """Agentes instalados con los que se puede trabajar de verdad.

    Deja fuera los que tienen el binario instalado pero ninguna sesión: elegir
    uno abortaría el loop en la primera iteración. Los de sesión desconocida
    se conservan (no se descarta un agente sólo por no haberlo podido probar).
    """
    return [a for a in agentes_instalados(preferidos)
            if sesion_agente(a) is not False]


def agente_por_defecto():
    """Agente a usar cuando el usuario deja el selector en 'auto'."""
    operativos = agentes_operativos()
    return operativos[0] if operativos else ""


# ---------- Sesión de los CLIs ----------

# Mismos indicios que detecta autopiloto.sh al leer la salida del agente: si el
# CLI se queja de credenciales, no hay sesión con la que trabajar.
PATRONES_SIN_SESION = (
    r"not logged in", r"please run /login", r"not authenticated",
    r"unauthorized", r"\b401\b", r"authentication_error",
    r"invalid.?api.?key", r"missing.?api.?key",
    r"OPENAI_API_KEY", r"ANTHROPIC_API_KEY", r"please set your api key",
    r"run .?codex login",
)

# Sonda de sesión por agente. opencode se consulta sin inferencia (listar
# credenciales); codex y claude no exponen un estado de sesión fiable, así que
# se les manda un prompt mínimo: si no hay sesión fallan antes de inferir.
SONDA_SESION = {
    "opencode": (["auth", "list"], 8),
    "codex": (["exec", "--skip-git-repo-check", "ping"], 20),
    "claude": (["-p", "--output-format", "text", "ping"], 20),
}

_sesiones = {}


def sesion_agente(nombre):
    """True/False si el agente tiene sesión; None si no se puede saber.

    False = instalado pero sin login (no se debe ofrecer para trabajar).
    None = desconocido: se ofrece igual, porque descartarlo sería peor.
    El resultado se cachea durante la sesión (invalidar_cache() lo borra).
    """
    if nombre in _sesiones:
        return _sesiones[nombre]
    _sesiones[nombre] = None
    if not ruta_binario(nombre) or nombre not in SONDA_SESION:
        return _sesiones[nombre]
    args, timeout = SONDA_SESION[nombre]
    try:
        r = subprocess.run([ruta_binario(nombre)] + args, capture_output=True,
                           text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        return _sesiones[nombre]
    salida = f"{r.stdout}\n{r.stderr}"
    if re.search("|".join(PATRONES_SIN_SESION), salida, re.I):
        _sesiones[nombre] = False
    elif nombre == "opencode":
        # `opencode auth list` responde 0 siempre. Sólo hay sesión si lista
        # alguna credencial o variable de entorno; si no, es desconocido.
        _sesiones[nombre] = None
    elif r.returncode == 0 or salida.strip():
        _sesiones[nombre] = True
    return _sesiones[nombre]


def estado_agentes(preferidos=None):
    """Ficha de cada agente: instalado, ruta y estado de sesión."""
    return [{
        "nombre": a,
        "ruta": ruta_binario(a),
        "instalado": bool(ruta_binario(a)),
        "sesion": sesion_agente(a),
    } for a in (preferidos or cfg.AGENTES_PREFERIDOS)
        if a in cfg.AGENTES_CONOCIDOS]


def invalidar_cache():
    """Olvida los resultados caché; la siguiente consulta vuelve a la red."""
    global _modelos, _proveedores
    _modelos = None
    _proveedores = None
    _modelos_por_proveedor.clear()
    _sesiones.clear()


def sugerido(modelos):
    """Elije un modelo por defecto: el sugerido si existe, si no el primero."""
    if not modelos:
        return cfg.MODELO_SUGERIDO
    if cfg.MODELO_SUGERIDO in modelos:
        return cfg.MODELO_SUGERIDO
    return modelos[0]
