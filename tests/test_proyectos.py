#!/usr/bin/env python3
"""Tests de regresión: un proyecto quitado NO debe reaparecer en el registro.

Protege contra el bug donde closeEvent/_cambiar_proyecto llamaban a
guardar_config_proyecto() y éste re-añadía (`setdefault`) el nombre del
proyecto que el usuario acababa de quitar, haciendo que reapareciera al
reabrir la GUI como una entrada huérfana (config sin ruta).
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autopiloto_gui import configuracion as cfg
from autopiloto_gui import proyectos


def _config_aislada():
    """Redirige CONFIG_DIR/REGISTRO a un temp y devuelve la ruta del registro."""
    tmp = tempfile.mkdtemp()
    reg = os.path.join(tmp, "proyectos.json")
    cfg.CONFIG_DIR = tmp
    cfg.REGISTRO = reg
    proyectos.cfg.CONFIG_DIR = tmp
    proyectos.cfg.REGISTRO = reg
    with open(reg, "w", encoding="utf-8") as f:
        json.dump({"proyectos": {}}, f, ensure_ascii=False)
    return reg


def test_guardar_config_no_reañade_proyecto_quitado():
    reg = _config_aislada()
    try:
        # Registro con dos proyectos, luego el usuario quita "A"
        proyectos_dic = {
            "A": {"ruta": "/tmp/a", "config": {"tema": "X"}},
            "B": {"ruta": "/tmp/b", "config": {}},
        }
        proyectos.guardar(proyectos_dic, "Oscuro")
        proyectos_dic.pop("A", None)
        proyectos.guardar(proyectos_dic, "Oscuro")

        # closeEvent sigue llamando con el nombre activo ya quitado
        proyectos.guardar_config_proyecto(proyectos_dic, "A", {"tema": "Y"})

        with open(reg, encoding="utf-8") as f:
            datos = json.load(f)
        assert "A" not in datos["proyectos"], "el proyecto quitado no debe reaparecer"
        assert set(datos["proyectos"]) == {"B"}
    finally:
        import shutil

        shutil.rmtree(os.path.dirname(reg), ignore_errors=True)


def test_guardar_config_sigue_guardando_proyectos_existentes():
    reg = _config_aislada()
    try:
        proyectos_dic = {"B": {"ruta": "/tmp/b", "config": {}}}
        proyectos.guardar(proyectos_dic, "Oscuro")
        proyectos.guardar_config_proyecto(
            proyectos_dic, "B", {"modelos": {"tarea": "x"}}
        )

        with open(reg, encoding="utf-8") as f:
            datos = json.load(f)
        assert "B" in datos["proyectos"]
        assert datos["proyectos"]["B"]["config"]["modelos"]["tarea"] == "x"
    finally:
        import shutil

        shutil.rmtree(os.path.dirname(reg), ignore_errors=True)


if __name__ == "__main__":
    test_guardar_config_no_reañade_proyecto_quitado()
    test_guardar_config_sigue_guardando_proyectos_existentes()
    print("\nTests de regresión de proyectos.py PASARON")
