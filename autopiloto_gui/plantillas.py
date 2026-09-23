"""Instalación de los scripts/plantillas necesarios en un proyecto."""

import filecmp
import os
import shutil

PLANTILLA_DIR = os.path.join(os.path.dirname(__file__), "plantillas_data")
SCRIPTS = ("autopiloto.sh", "gate.sh", "mapear.sh")
ARCHIVOS = SCRIPTS + ("plan.md", "lecciones.md")
GATE_CHECKS_DIR = "gate_checks"
GATE_CHECKS = tuple(
    os.path.relpath(os.path.join(ruta, f), PLANTILLA_DIR)
    for ruta, _dirs, archivos in os.walk(os.path.join(PLANTILLA_DIR, GATE_CHECKS_DIR))
    for f in archivos
    if f.endswith(".sh")
)


def quitar(ruta):
    """Borra los archivos que la app instaló. Devuelve los eliminados.

    Solo toca autopiloto.sh, gate.sh, mapear.sh, plan.md, lecciones.md,
    progreso.log y gate_checks/: jamás el resto del proyecto.
    """
    eliminados = []
    log = os.path.join(ruta, "progreso.log")
    nombres = list(ARCHIVOS) + (["progreso.log"] if os.path.exists(log) else [])
    for nombre in nombres:
        destino = os.path.join(ruta, nombre)
        if os.path.exists(destino):
            os.remove(destino)
            eliminados.append(nombre)
    dir_checks = os.path.join(ruta, GATE_CHECKS_DIR)
    if os.path.isdir(dir_checks):
        shutil.rmtree(dir_checks)
        eliminados.append(GATE_CHECKS_DIR + "/")
    return eliminados


def _desactualizados(ruta):
    """Scripts .sh y gate_checks/ que difieren entre plantilla y proyecto.

    plan.md NO se compara: es contenido editable del usuario (sus tareas);
    solo se crea si falta, nunca se sobreescribe.
    """
    copias = list(SCRIPTS) + list(GATE_CHECKS)
    diff = []
    for nombre in copias:
        src = os.path.join(PLANTILLA_DIR, nombre)
        dst = os.path.join(ruta, nombre)
        if os.path.exists(dst) and os.path.exists(src):
            if not filecmp.cmp(src, dst, shallow=False):
                diff.append(nombre)
    return diff


def instalar(ruta):
    """Copia plantillas (scripts + gate_checks) que falten. Devuelve creados."""
    creados = []
    for nombre in list(ARCHIVOS) + list(GATE_CHECKS):
        destino = os.path.join(ruta, nombre)
        if not os.path.exists(destino):
            os.makedirs(os.path.dirname(destino), exist_ok=True)
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


def actualizar(ruta):
    """Sobrescribe plantillas que difieren. Devuelve lista de actualizados."""
    actualizados = []
    for nombre in _desactualizados(ruta):
        shutil.copy2(os.path.join(PLANTILLA_DIR, nombre), os.path.join(ruta, nombre))
        if nombre.endswith(".sh"):
            os.chmod(os.path.join(ruta, nombre), 0o755)
        actualizados.append(nombre)
    return actualizados


def faltan(ruta):
    """Scripts y memoria que faltan (lecciones.md se crea si no existe)."""
    return [s for s in SCRIPTS + ("lecciones.md",)
            if not os.path.exists(os.path.join(ruta, s))]
