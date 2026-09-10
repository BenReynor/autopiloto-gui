"""Registro de proyectos del panel autopiloto.

Se guarda en ~/.config/autopiloto/proyectos.json y es compartido por todos
los proyectos que gestiones desde el panel.
"""

import json
import os

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "autopiloto")
REGISTRO = os.path.join(CONFIG_DIR, "proyectos.json")


def cargar():
    try:
        with open(REGISTRO, "r", encoding="utf-8") as f:
            return json.load(f).get("proyectos", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def guardar(proyectos):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(REGISTRO, "w", encoding="utf-8") as f:
        json.dump({"proyectos": proyectos}, f, indent=2, ensure_ascii=False)