"""Registro de proyectos y tema del panel autopiloto.

Se guarda en ~/.config/autopiloto/proyectos.json y es compartido por todos
los proyectos que gestiones desde el panel.
"""

import json
import os

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "autopiloto")
REGISTRO = os.path.join(CONFIG_DIR, "proyectos.json")
TEMA_DEFECTO = "Oscuro"


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


def guardar(proyectos, tema=None):
    datos = _leer_archivo()
    datos["proyectos"] = proyectos
    if tema:
        datos["tema"] = tema
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(REGISTRO, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)