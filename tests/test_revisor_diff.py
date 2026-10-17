#!/usr/bin/env python3
"""Tests for the diff the reviewer receives (diff_revision in dedalo.sh).

The bug that motivated this file: `revisar_diff` passed the multiline list of
modified files as a SINGLE quoted argument to `git diff`, that is, as a
literal pathspec with newlines. That pathspec matches no file, so with two or
more modified files the reviewer received an empty diff and approved without
having seen anything.

`diff_revision` is extracted from the template and run against a real git repo
to check that the full diff arrives.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RAIZ = Path(__file__).resolve().parent.parent
PLANTILLA = RAIZ / "dedalo" / "plantillas_data" / "dedalo.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("git") is None
    or os.name == "nt",
    reason="harness POSIX (diff/CLIs falsos en bash): se valida en Linux")

CONTROL = r"plan\.md|progreso\.log|lecciones\.md|mapeo\.txt"


def _extraer_funcion(texto, nombre):
    """Returns the text of `nombre() { ... }` using brace balancing."""
    inicio = texto.index(f"{nombre}() {{")
    i = texto.index("{", inicio)
    profundidad = 0
    for j in range(i, len(texto)):
        if texto[j] == "{":
            profundidad += 1
        elif texto[j] == "}":
            profundidad -= 1
            if profundidad == 0:
                return texto[inicio:j + 1]
    raise AssertionError(f"no se pudo extraer {nombre}")


def _repo(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    env = {"GIT_CONFIG_GLOBAL": str(tmp_path / "gitconfig"),
           "GIT_CONFIG_SYSTEM": "/dev/null",
           "HOME": str(tmp_path),
           "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    subprocess.run(["git", "init", "-q", "-b", "master", "."],
                   cwd=d, check=True, env=env, timeout=30)
    (d / "app.py").write_text("print('hola')\n", encoding="utf-8")
    (d / "leeme.md").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=d, check=True, env=env, timeout=30)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"],
                   cwd=d, check=True, env=env, timeout=30)
    return d, env


def _diff_revision(repo, env):
    """Runs the real diff_revision() against the repo and returns its stdout."""
    texto = PLANTILLA.read_text(encoding="utf-8")
    func = repo.parent / "func.sh"
    func.write_text(_extraer_funcion(texto, "diff_revision"), encoding="utf-8")
    runner = repo.parent / "run.sh"
    runner.write_text(
        f'. "{func}"\nPROYECTO="{repo}"\nCONTROL=\'{CONTROL}\'\n'
        'diff_revision\n', encoding="utf-8")
    return subprocess.run(["bash", str(runner)], capture_output=True,
                          text=True, timeout=30, env=env)


def test_diff_revision_incluye_todos_los_ficheros_modificados(tmp_path):
    """With 3 modified files the diff must bring all 3, not one nor zero."""
    repo, env = _repo(tmp_path)
    (repo / "app.py").write_text("print('hola 2')\n", encoding="utf-8")
    (repo / "leeme.md").write_text("base 2\n", encoding="utf-8")
    (repo / "nuevo.py").write_text("x = 1\n", encoding="utf-8")

    r = _diff_revision(repo, env)
    assert r.returncode == 0, r.stderr
    salida = r.stdout
    assert salida.strip(), "el revisor recibiría un diff VACÍO"
    for nombre in ("app.py", "leeme.md", "nuevo.py"):
        assert f"b/{nombre}" in salida, (
            f"{nombre} ausente del diff del revisor:\n{salida}")


def test_diff_revision_un_solo_fichero(tmp_path):
    repo, env = _repo(tmp_path)
    (repo / "app.py").write_text("print('x')\n", encoding="utf-8")
    r = _diff_revision(repo, env)
    assert r.returncode == 0, r.stderr
    assert "b/app.py" in r.stdout, r.stdout


def test_diff_revision_excluye_los_archivos_control(tmp_path):
    """plan.md/progreso.log are Dédalo traceability, not the task's."""
    repo, env = _repo(tmp_path)
    (repo / "app.py").write_text("print('y')\n", encoding="utf-8")
    (repo / "plan.md").write_text("- [x] algo\n", encoding="utf-8")
    (repo / "progreso.log").write_text("== Iteración 1 ==\n", encoding="utf-8")

    r = _diff_revision(repo, env)
    assert r.returncode == 0, r.stderr
    assert "b/app.py" in r.stdout, r.stdout
    assert "b/plan.md" not in r.stdout, r.stdout
    assert "b/progreso.log" not in r.stdout, r.stdout


def test_diff_revision_sin_cambios_avisa(tmp_path):
    repo, env = _repo(tmp_path)
    r = _diff_revision(repo, env)
    assert r.returncode == 0, r.stderr
    assert "sin cambios" in r.stdout, r.stdout


def test_diff_revision_solo_cambios_de_control_avisa(tmp_path):
    """If the only thing modified is CONTROL, the reviewer must know there is no diff."""
    repo, env = _repo(tmp_path)
    (repo / "plan.md").write_text("- [x] tarea\n", encoding="utf-8")
    r = _diff_revision(repo, env)
    assert r.returncode == 0, r.stderr
    assert "sin cambios" in r.stdout, r.stdout


def test_diff_revision_ignora_ficheros_nuevos_sin_anadir(tmp_path):
    """A file without `git add` must also reach the reviewer (git add -N)."""
    repo, env = _repo(tmp_path)
    (repo / "suelto.py").write_text("y = 2\n", encoding="utf-8")
    r = _diff_revision(repo, env)
    assert r.returncode == 0, r.stderr
    assert "b/suelto.py" in r.stdout, r.stdout
