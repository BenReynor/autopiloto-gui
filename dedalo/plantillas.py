"""Installation of the scripts/templates needed in a project."""

import filecmp
import os
import shutil
import subprocess
from datetime import datetime

PLANTILLA_DIR = os.path.join(os.path.dirname(__file__), "plantillas_data")
SCRIPTS = ("dedalo.sh", "gate.sh", "mapear.sh")
ARCHIVOS = SCRIPTS + ("plan.md", "lecciones.md", "CONTEXTO.md")
GATE_CHECKS_DIR = "gate_checks"
GATE_CHECKS = tuple(
    # Relative names ALWAYS with "/": the listing from `instalar()` (which the GUI
    # shows and the test compares) must not depend on the OS slash.
    os.path.relpath(os.path.join(ruta, f), PLANTILLA_DIR).replace("\\", "/")
    for ruta, _dirs, archivos in os.walk(os.path.join(PLANTILLA_DIR, GATE_CHECKS_DIR))
    for f in archivos
    # The .py files are the portable port (used on Windows, without bash); the .sh
    # ones are preferred on Unix. Both are always copied into the project.
    if f.endswith((".sh", ".py"))
)


def quitar(ruta):
    """Deletes the files the app installed. Returns the deleted ones.

    Only touches dedalo.sh, gate.sh, mapear.sh, plan.md, lecciones.md,
    CONTEXTO.md, progreso.log and gate_checks/: never the rest of the project.
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
    """Initializes a git repo if the project does not have one.

    Dedalo works 100% with branches/commits; without a repo it aborts on the first
    `git checkout` (as happened with Proyecto_nuevo). This:
      1. `git init -b master` (base branch of the dedalo.sh script).
      2. Initial commit of the files so that the branch exists.

    Returns a dict {repo: "creado"|"ya-existia"|"no-disponible", archivos: n}.
    Not available = git not installed or identity not configured (touches nothing).
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
        # --allow-empty: if the project has no files of its own (only the
        # framework ones, which the .gitignore excludes), master is left with an empty
        # commit so that dedalo can branch on top of it.
        cm = subprocess.run(["git", "commit", "-q", "--allow-empty", "-m",
                             "init: dedalo (plantillas instaladas)"],
                            cwd=ruta, capture_output=True, text=True,
                            timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return {"repo": "creado", "archivos": 0}
    # The commit fails if there is no git identity configured or nothing to commit
    return {"repo": "creado", "archivos": 0 if cm.returncode != 0 else _git_archivos(ruta)}


def _git_archivos(ruta):
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ruta, capture_output=True,
                             text=True, timeout=30)
        return len([linea for linea in out.stdout.splitlines() if linea.strip()])
    except (OSError, subprocess.TimeoutExpired):
        return 0


def _desactualizados(ruta):
    """Framework scripts that differ between template and project.

    Only the SCRIPTS (dedalo.sh, gate.sh, mapear.sh) are compared/renewed:
    they are support code that must follow the template version.

    plan.md, lecciones.md, CONTEXTO.md and gate_checks/*.sh are NOT compared: they
    are user content (their tasks, their memory, their context and their
    verifications). They are created if missing, but never overwritten with the
    template.
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
    """Copies the templates (scripts + gate_checks) that are missing. Returns the created ones."""
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
            f.write("# progreso.log — Dédalo\n")
        creados.append("progreso.log")
    return creados


def _bloque_framework_gitignore():
    """Lines of the template .gitignore that exclude the framework."""
    ruta = os.path.join(PLANTILLA_DIR, ".gitignore")
    with open(ruta, encoding="utf-8") as f:
        lineas = f.read().splitlines()
    bloque = []
    for linea in lineas:
        if linea.startswith("# Entorno"):
            break
        bloque.append(linea)
    return "\n".join(bloque).strip() + "\n"


def asegurar_gitignore(ruta):
    """Ensures the project's .gitignore excludes the framework.

    If it does not exist, the full template is copied. If it already exists (the
    user's own entries), ONLY the framework block is ADDED, without touching the rest
    and without duplicating it if it is already there. Returns True if it was modified.
    """
    destino = os.path.join(ruta, ".gitignore")
    if not os.path.exists(destino):
        shutil.copy2(os.path.join(PLANTILLA_DIR, ".gitignore"), destino)
        return True
    with open(destino, encoding="utf-8") as f:
        contenido = f.read()
    if "Dédalo:" in contenido:
        return False
    with open(destino, "a", encoding="utf-8") as f:
        if not contenido.endswith("\n"):
            f.write("\n")
        f.write("\n" + _bloque_framework_gitignore())
    return True


def quitar_framework_del_git(ruta):
    """Removes the framework files from git tracking (without deleting them).

    The project keeps dedalo.sh, gate.sh, gate_checks/, plan.md,
    etc. on disk (dedalo needs them), but they are no longer in the repo.
    Returns the list of files that git stopped tracking.
    """
    if not _es_repo_git(ruta):
        return []
    patrones = list(ARCHIVOS) + [GATE_CHECKS_DIR] + ["progreso.log", "metrics.jsonl",
                                                    "incidencias.jsonl",
                                                    "mapeo.txt", "endpoints.txt",
                                                    ".dedalo_review"]
    try:
        out = subprocess.run(
            ["git", "ls-files"] + patrones, cwd=ruta, capture_output=True,
            text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return []
    trackeados = [linea for linea in out.stdout.splitlines() if linea.strip()]
    if not trackeados:
        return []
    try:
        subprocess.run(["git", "rm", "--cached", "-q", "-r", "--ignore-unmatch",
                        "--"] + trackeados, cwd=ruta, capture_output=True,
                       text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return trackeados


def actualizar(ruta):
    """Overwrites templates that differ. Returns the list of updated ones.

    Before overwriting each script, it creates a timestamped backup
    (e.g. dedalo.sh.bak.20261005_123456) so it can be reverted manually
    if the update breaks something.
    """
    actualizados = []
    for nombre in _desactualizados(ruta):
        dst = os.path.join(ruta, nombre)
        # Timestamped backup before overwriting
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = f"{dst}.bak.{ts}"
        shutil.copy2(dst, backup)
        # Copy the new template
        shutil.copy2(os.path.join(PLANTILLA_DIR, nombre), dst)
        if nombre.endswith(".sh"):
            os.chmod(dst, 0o755)
        actualizados.append(nombre)
    return actualizados


def faltan(ruta):
    """Scripts and memory that are missing (lecciones.md/CONTEXTO.md are created if they do not exist)."""
    return [s for s in SCRIPTS + ("lecciones.md", "CONTEXTO.md")
            if not os.path.exists(os.path.join(ruta, s))]
