#!/usr/bin/env python3
"""Operaciones git del loop nativo (port de las secciones git de
autopiloto.sh: snapshot, iteracion_sin_trabajo, commit/merge, revertir,
diff_para_revisor, registrar_leccion y preparar_ramas).

Sin dependencias de PySide. Los comandos git se ejecutan con run_con_timeout
(tope defensivo; el árbol local no debería colgarse). Todas las rutas se
pasAN como argumentos separados (nunca glosadas), igual que el fix del bash
para diff con espacios.
"""

import os
import re
import shutil
import subprocess
import time
from collections import Counter

from .loop_proceso import run_con_timeout

# Patrón de caches/derivados que NUNCA entran en el diff ni en los commits
# (misma lista que el grep -vE de snapshot() en el script).
_CACHES = re.compile(
    r"(^|/)(__pycache__|\.pytest_cache|\.mypy_cache|node_modules|\.venv|venv)/"
    r"|\.pyc$|\.pyo$")

# Archivos de control del propio framework: trazabilidad del loop, no del
# agente. Viene de la variable CONTROL del script. Al usarse anclado
# `^(?P<control>...)$` para que "plan.md" no se coma "docs/plan.md".
CONTROL = (
    r"plan\.md|lecciones\.md|progreso\.log|gate\.sh|autopiloto\.sh|mapear\.sh"
    r"|mapeo\.txt|endpoints\.txt|metrics\.jsonl|incidencias\.jsonl|gate_checks(/.*)?"
    r"|\.autopiloto_review(/.*)?")


def run_git(proyecto, *args, timeout=60):
    """`git -C <proyecto> <args>`; devuelve (rc, stdout, stderr)."""
    rc, salida, _t = run_con_timeout(
        ["git", "-C", str(proyecto)] + list(args), timeout,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out = salida[0].decode("utf-8", "replace") if salida and salida[0] else ""
    err = salida[1].decode("utf-8", "replace") if salida and salida[1] else ""
    return rc, out, err


def _ok(proyecto, *args):
    return run_git(proyecto, *args)[0] == 0


def snapshot(proyecto, destino):
    """Escribe en `destino` la lista ordenada de archivos con cambios, género
    `git status --porcelain`.

    Port de snapshot(): quita el prefijo de estado de 3 caracteres, mantiene
    las rutas entrecomilladas que git ponga (espacios), y filtra caches. El
    recorte de archivos CONTROL se hace DESPUÉS (cambios_entre), igual que el
    script separa snapshot() de iteracion_sin_trabajo().
    """
    _, out, _ = run_git(proyecto, "-c", "core.quotepath=false",
                        "status", "--porcelain")
    lineas = []
    for linea in out.splitlines():
        if len(linea) < 4:
            continue
        ruta = linea[3:]
        if _CACHES.search(ruta):
            continue
        lineas.append(ruta)
    with open(destino, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(lineas)) + ("\n" if lineas else ""))


def _leer(fichero):
    if not os.path.exists(fichero):
        return []
    with open(fichero, encoding="utf-8") as f:
        return [linea for linea in f.read().splitlines() if linea]


def cambios_entre(before_path, after_path, control=CONTROL):
    """Compara dos snapshots excluyendo CONTROL, de forma simétrica.

    Port de iteracion_sin_trabajo(): devuelve (nuevos, borrados). Un archivo
    que desaparece del status del agente también es trabajo (lo borró). El
    resultado es una multiset (comm -13 / -23), como hace sort+comm del
    script. Si ambos están vacíos no hubo trabajo.
    """
    rx = re.compile(r"^(?:" + control + r")$")
    antes = Counter(linea for linea in _leer(before_path) if not rx.match(linea))
    despues = Counter(linea for linea in _leer(after_path) if not rx.match(linea))
    nuevos = list((despues - antes).elements())
    borrados = list((antes - despues).elements())
    return nuevos, borrados


def commit_tarea(proyecto, archivos, subject, cuerpo):
    """`git add -- <archivos> && git commit -q -m <subject> -m <cuerpo>`.

    Devuelve 0 si el commit se creó; las rutas con espacios se pasan como
    elementos separados. Sin archivos no hace nada (igual que el `[ -n ]`
    guard del bash).
    """
    if not archivos:
        return 0
    rc, _, _ = run_git(proyecto, "add", "--", *archivos)
    if rc != 0:
        return rc
    return run_git(proyecto, "commit", "-q", "-m", subject, "-m", cuerpo)[0]


def merge_ff(proyecto, rama):
    """`git merge -q --ff-only <rama>`; rc 0 si el fast-forward fue bien."""
    return run_git(proyecto, "merge", "-q", "--ff-only", rama)[0]


def borrar_rama(proyecto, rama, fuerza=False):
    flag = "-D" if fuerza else "-d"
    return run_git(proyecto, "branch", "-q", flag, rama)[0]


def checkout(proyecto, rama, crear=False, desde=None):
    args = ["checkout", "-q", "-b", rama] + ([desde] if desde else []) \
        if crear else ["checkout", "-q", rama]
    return run_git(proyecto, *args)[0]


def rama_existe(proyecto, rama):
    """rev-parse --verify con -q: True si la ref existe (local u origin)."""
    return _ok(proyecto, "rev-parse", "--verify", "-q", rama)


def preparar_ramas(proyecto, rama_base, rama_run, rama_trabajo):
    """Port de las líneas 964-1017 de autopiloto.sh: crea/reusa RAMA_RUN
    desde RAMA_BASE y resuelve RAMA_TRABAJO (principal / existente /
    seguimiento de origin / nueva desde RAMA_RUN).

    Devuelve (rama_trabajo_efectiva, mensajes) para loguear. Si no se pudo
    crear la rama base devuelve (None, mensajes) y el caller aborta.
    """
    mensajes = []
    if rama_existe(proyecto, rama_run):
        checkout(proyecto, rama_run)
        mensajes.append(f"[autopiloto] Reusando rama {rama_run}")
    elif checkout(proyecto, rama_run, crear=True, desde=rama_base) != 0:
        mensajes.append(f"[autopiloto] ✗ no se pudo crear {rama_run} desde "
                        f"{rama_base} (¿árbol sucio?).")
        return None, mensajes
    else:
        mensajes.append(f"[autopiloto] Rama base: {rama_run} (desde {rama_base})")

    if rama_trabajo and rama_trabajo != rama_run:
        if rama_trabajo in ("master", "main"):
            if checkout(proyecto, rama_trabajo) != 0:
                checkout(proyecto, rama_trabajo, crear=True, desde=rama_run)
            mensajes.append("[autopiloto] Trabajando en la rama principal "
                            f"{rama_trabajo} (sin rama paralela)")
        elif rama_existe(proyecto, rama_trabajo):
            checkout(proyecto, rama_trabajo)
            mensajes.append("[autopiloto] Trabajando en la rama existente "
                            f"{rama_trabajo}")
        elif rama_existe(proyecto, "origin/" + rama_trabajo):
            checkout(proyecto, rama_trabajo, crear=True,
                     desde="origin/" + rama_trabajo)
            mensajes.append("[autopiloto] Trabajando en "
                            f"{rama_trabajo} (seguimiento de origin/{rama_trabajo})")
        else:
            checkout(proyecto, rama_trabajo, crear=True, desde=rama_run)
            mensajes.append("[autopiloto] Creada la rama de trabajo "
                            f"{rama_trabajo} (desde {rama_run})")
    else:
        rama_trabajo = rama_run
        mensajes.append(f"[autopiloto] Rama de trabajo (default): {rama_trabajo}")
    return rama_trabajo, mensajes


def revertir(proyecto, control=CONTROL):
    """Revierte el working tree al estado de HEAD (rama de tarea sin avanzar).

    Port de revertir(): quita los archivos nuevos (untracked), restaura los
    borrados y los modificados desde HEAD. Los archivos CONTROL del framework
    no se tocan. Rutas entrecomilladas por git (espacios) se normalizan.
    """
    rx = re.compile(r"^(?:" + control + r")$")
    _, out, _ = run_git(proyecto, "status", "--porcelain")
    for linea in out.splitlines():
        if len(linea) < 4:
            continue
        estado = linea[:2]
        ruta = linea[3:].strip('"')
        if not ruta or rx.match(ruta):
            continue
        if estado == "??":
            ruta_abs = os.path.join(proyecto, ruta)
            if os.path.isdir(ruta_abs) and not os.path.islink(ruta_abs):
                shutil.rmtree(ruta_abs, ignore_errors=True)
            else:
                try:
                    os.unlink(ruta_abs)
                except OSError:
                    pass
        else:
            run_git(proyecto, "checkout", "--", ruta)


def diff_para_revisor(proyecto, control=CONTROL):
    """Diff de la iteración para el revisor, excluyendo archivos CONTROL.

    Port de diff_revision(): marca intent-to-add (git add -N) para que los
    archivos nuevos entren en el diff, y pasa las rutas como pathspecs
    separados (nunca una lista multilínea en un único argumento). Devuelve
    (stat, diff). Sin cambios devuelve el texto "(sin cambios fuera de
    archivos CONTROL)".
    """
    rx = re.compile(r"^(?:" + control + r")$")
    run_git(proyecto, "add", "-N", "-A")
    _, out, _ = run_git(proyecto, "diff", "--name-only")
    archivos = [linea for linea in out.splitlines()
                if linea and not rx.match(linea.strip('"'))]
    if not archivos:
        return "(sin cambios fuera de archivos CONTROL)", ""
    _, stat, _ = run_git(proyecto, "diff", "--stat", "--", *archivos)
    _, diff, _ = run_git(proyecto, "diff", "--", *archivos)
    return stat, ("#----- diff (excluye archivos CONTROL del framework) -----#\n"
                  + diff)


def registrar_leccion(lecciones, titulo, sintoma, causa, prevencion):
    """Añade una lección a lecciones.md (memoria del proyecto)."""
    fecha = time.strftime("%Y-%m-%d %H:%M")
    with open(lecciones, "a", encoding="utf-8") as f:
        f.write(f"\n## {fecha} — {titulo}\n"
                f"- Síntoma: {sintoma}\n"
                f"- Causa: {causa}\n"
                f"- Prevención: {prevencion}\n")
