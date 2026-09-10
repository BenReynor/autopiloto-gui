"""Instalación de los scripts/plantillas necesarios en un proyecto."""

import os
import shutil

PLANTILLA_DIR = os.path.join(os.path.dirname(__file__), "plantillas_data")
SCRIPTS = ("autopiloto.sh", "gate.sh", "mapear.sh")
ARCHIVOS = SCRIPTS + ("plan.md",)


def instalar(ruta):
    """Copia las plantillas que falten en ruta. Devuelve lista de creados."""
    creados = []
    for nombre in ARCHIVOS:
        destino = os.path.join(ruta, nombre)
        if not os.path.exists(destino):
            shutil.copy2(os.path.join(PLANTILLA_DIR, nombre), destino)
            if nombre.endswith(".sh"):
                os.chmod(destino, 0o755)
            creados.append(nombre)
    log = os.path.join(ruta, "progreso.log")
    if not os.path.exists(log):
        with open(log, "w", encoding="utf-8") as f:
            f.write("# progreso.log — Autopiloto\n")
        creados.append("progreso.log")
    return creados


def faltan(ruta):
    return [s for s in SCRIPTS if not os.path.exists(os.path.join(ruta, s))]