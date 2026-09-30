"""Instalación de los scripts/plantillas necesarios en un proyecto."""

import filecmp
import os
import shutil
import subprocess

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


def _es_repo_git(ruta):
    return os.path.isdir(os.path.join(ruta, ".git"))


def inicializar_git(ruta):
    """Inicializa un repo git si el proyecto no lo tiene.

    El autopiloto trabaja 100% con ramas/commits; sin repo aborta en el primer
    `git checkout` (como pasó con Proyecto_nuevo). Esto:
      1. `git init -b master` (rama base del script autopiloto.sh).
      2. Commit inicial de los archivos para que la rama exista.

    Devuelve un dict {repo: "creado"|"ya-existia"|"no-disponible", archivos: n}.
    No disponible = git sin instalar o identidad sin configurar (no toca nada).
    """
    if _es_repo_git(ruta):
        return {"repo": "ya-existia", "archivos": 0}
    try:
        git = subprocess.run(["git", "init", "-b", "master"], cwd=ruta,
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return {"repo": "no-disponible", "archivos": 0}
    if git.returncode != 0:
        return {"repo": "no-disponible", "archivos": 0}
    try:
        subprocess.run(["git", "add", "-A"], cwd=ruta, capture_output=True,
                       text=True, timeout=30)
        # --allow-empty: si el proyecto no tiene archivos propios (solo los del
        # framework, que el .gitignore excluye), master queda con un commit
        # vacío para que el autopiloto pueda ramificar sobre él.
        cm = subprocess.run(["git", "commit", "-q", "--allow-empty", "-m",
                             "init: autopiloto (plantillas instaladas)"],
                            cwd=ruta, capture_output=True, text=True,
                            timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return {"repo": "creado", "archivos": 0}
    # El commit falla si no hay identidad git configurada o nada que commitear
    return {"repo": "creado", "archivos": 0 if cm.returncode != 0 else _git_archivos(ruta)}


def _git_archivos(ruta):
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ruta, capture_output=True,
                             text=True, timeout=30)
        return len([linea for linea in out.stdout.splitlines() if linea.strip()])
    except (OSError, subprocess.TimeoutExpired):
        return 0


def _desactualizados(ruta):
    """Scripts del framework que difieren entre plantilla y proyecto.

    Solo se comparan/renuevan los SCRIPTS (autopiloto.sh, gate.sh, mapear.sh):
    son código de soporte que debe seguir la versión de plantilla.

    plan.md, lecciones.md y gate_checks/*.sh NO se comparan: son contenido del
    usuario (sus tareas, su memoria y sus verificaciones). Se crean si faltan,
    pero nunca se sobreescriben con la plantilla.
    """
    diff = []
    for nombre in SCRIPTS:
        src = os.path.join(PLANTILLA_DIR, nombre)
        dst = os.path.join(ruta, nombre)
        if os.path.exists(dst) and os.path.exists(src):
            if not filecmp.cmp(src, dst, shallow=False):
                diff.append(nombre)
    return diff


def instalar(ruta):
    """Copia plantillas (scripts + gate_checks) que falten. Devuelve creados."""
    creados = []
    for nombre in list(ARCHIVOS) + list(GATE_CHECKS) + [".gitignore"]:
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
