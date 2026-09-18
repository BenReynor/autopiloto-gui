"""Registro de proyectos, tema y protección térmica del panel autopiloto.

Se guarda en ~/.config/autopiloto/proyectos.json y es compartido por todos
los proyectos que gestiones desde el panel.
"""

import json
import os

from . import configuracion as cfg


def _leer_archivo():
    try:
        with open(cfg.REGISTRO, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def cargar():
    return _leer_archivo().get("proyectos", {})


def leer_tema():
    return _leer_archivo().get("tema", cfg.TEMA_DEFECTO)


def leer_seguridad():
    datos = _leer_archivo().get("seguridad", {})
    seg = dict(cfg.SEGURIDAD_DEFECTO)
    seg.update(datos)
    return seg


def leer_modelos():
    """Modelos seleccionados (tarea/revisor) guardados entre sesiones."""
    return _leer_archivo().get("modelos", {})


def guardar(proyectos, tema=None, seguridad=None, modelos=None):
    datos = _leer_archivo()
    datos["proyectos"] = proyectos
    if tema:
        datos["tema"] = tema
    if seguridad is not None:
        datos["seguridad"] = seguridad
    if modelos is not None:
        datos["modelos"] = modelos
    os.makedirs(cfg.CONFIG_DIR, exist_ok=True)
    with open(cfg.REGISTRO, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)