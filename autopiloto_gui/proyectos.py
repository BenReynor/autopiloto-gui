"""Registro de proyectos, tema y protección térmica del panel autopiloto.

Se guarda en ~/.config/autopiloto/proyectos.json y es compartido por todos
los proyectos que gestiones desde el panel.
"""

import json
import os

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "autopiloto")
REGISTRO = os.path.join(CONFIG_DIR, "proyectos.json")
TEMA_DEFECTO = "Oscuro"
SEGURIDAD_DEFECTO = {
    "activo": True,
    "umbral": 85,
    "segundos": 5,
    "intervalo": 10,
}


def _leer_archivo():
    try:
        with open(REGISTRO, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def cargar():
    return _leer_archivo().get("proyectos", {})


def leer_tema():
    return _leer_archivo().get("tema", TEMA_DEFECTO)


def leer_seguridad():
    datos = _leer_archivo().get("seguridad", {})
    seg = dict(SEGURIDAD_DEFECTO)
    seg.update(datos)
    return seg


def guardar(proyectos, tema=None, seguridad=None):
    datos = _leer_archivo()
    datos["proyectos"] = proyectos
    if tema:
        datos["tema"] = tema
    if seguridad is not None:
        datos["seguridad"] = seguridad
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(REGISTRO, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)