#!/usr/bin/env python3
"""Tests for revertir() in dedalo.sh.

The bug that motivated this file: revertir() used comm -13 over snapshots that
only listed names (without a state prefix), so on a freshly created branch
(empty BEFORE) ALL of the agent's changes (new, modified, deleted) showed up
as "new" and were deleted with rm -rf. Also, names with spaces arrived quoted
from git status and broke the checkout/rm.

The fix: revertir() now reads git status --porcelain directly, distinguishes
by change type (?? new, D deleted, M modified) and acts correctly in each
case.
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
    reason="harness POSIX (revertir.sh en bash): se valida en Linux")


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
    (d / "test_app.py").write_text("def test_a(): assert True\n", encoding="utf-8")
    (d / "mi modulo.py").write_text("x=1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=d, check=True, env=env, timeout=30)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"],
                   cwd=d, check=True, env=env, timeout=30)
    # Create the task branch (simulates what dedalo.sh does)
    subprocess.run(["git", "checkout", "-q", "-b", "tarea", "master"],
                   cwd=d, check=True, env=env, timeout=30)
    return d, env


def _revertir(repo, env):
    """Runs the real revertir() against the repo and returns its stdout."""
    texto = PLANTILLA.read_text(encoding="utf-8")
    func = repo.parent / "func.sh"
    func.write_text(_extraer_funcion(texto, "revertir"), encoding="utf-8")
    runner = repo.parent / "run.sh"
    runner.write_text(
        f'. "{func}"\n'
        f'PROYECTO="{repo}"\n'
        'CONTROL="plan\\.md|progreso\\.log|lecciones\\.md|mapeo\\.txt"\n'
        'revertir\n', encoding="utf-8")
    return subprocess.run(["bash", str(runner)], capture_output=True,
                          text=True, timeout=30, env=env)


def test_revertir_restaura_fichero_borrado_por_el_agente(tmp_path):
    """If the agent deletes a tracked file, revertir restores it."""
    repo, env = _repo(tmp_path)
    (repo / "app.py").unlink()  # the agent deletes it

    r = _revertir(repo, env)
    assert r.returncode == 0, r.stderr
    assert (repo / "app.py").exists(), "app.py no se restauró"
    assert (repo / "app.py").read_text(encoding="utf-8") == "print('hola')\n"


def test_revertir_restaura_fichero_modificado_por_el_agente(tmp_path):
    """If the agent modifies a tracked file, revertir restores it to the original."""
    repo, env = _repo(tmp_path)
    (repo / "test_app.py").write_text("def test_b(): assert False\n", encoding="utf-8")

    r = _revertir(repo, env)
    assert r.returncode == 0, r.stderr
    assert (repo / "test_app.py").read_text(encoding="utf-8") == "def test_a(): assert True\n"


def test_revertir_borra_ficheros_nuevos_creados_por_el_agente(tmp_path):
    """Untracked files created by the agent are removed."""
    repo, env = _repo(tmp_path)
    (repo / "nuevo.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "otro.txt").write_text("basura\n", encoding="utf-8")

    r = _revertir(repo, env)
    assert r.returncode == 0, r.stderr
    assert not (repo / "nuevo.py").exists()
    assert not (repo / "otro.txt").exists()


def test_revertir_maneja_nombres_con_espacios(tmp_path):
    """Names with spaces in new and modified files."""
    repo, env = _repo(tmp_path)
    # New with a space
    (repo / "nuevo archivo.py").write_text("# nuevo\n", encoding="utf-8")
    # Modified with a space (the one already present in base)
    (repo / "mi modulo.py").write_text("x = 999\n", encoding="utf-8")

    r = _revertir(repo, env)
    assert r.returncode == 0, r.stderr
    # The new one with a space must disappear
    assert not (repo / "nuevo archivo.py").exists()
    # The modified one with a space must return to its original value
    assert (repo / "mi modulo.py").read_text(encoding="utf-8") == "x=1\n"


def test_revertir_no_toca_archivos_control(tmp_path):
    """plan.md, progreso.log, etc. are neither deleted nor restored."""
    repo, env = _repo(tmp_path)
    (repo / "plan.md").write_text("- [x] tarea\n", encoding="utf-8")
    (repo / "progreso.log").write_text("== Iteración 1 ==\n", encoding="utf-8")
    # Also create a normal new file to verify that it IS in fact deleted
    (repo / "real.py").write_text("real\n", encoding="utf-8")

    r = _revertir(repo, env)
    assert r.returncode == 0, r.stderr
    assert (repo / "plan.md").exists()
    assert (repo / "progreso.log").exists()
    assert not (repo / "real.py").exists()


def test_revertir_mezcla_todos_los_tipos(tmp_path):
    """Full scenario: deleted, modified, new, new with a space."""
    repo, env = _repo(tmp_path)
    (repo / "app.py").unlink()              # deleted
    (repo / "test_app.py").write_text("modificado\n")  # modified
    (repo / "nuevo_normal.py").write_text("nuevo\n")   # new
    (repo / "nuevo con espacio.py").write_text("nuevo\n")  # new with a space

    r = _revertir(repo, env)
    assert r.returncode == 0, r.stderr
    assert (repo / "app.py").exists() and (repo / "app.py").read_text(encoding="utf-8") == "print('hola')\n"
    assert (repo / "test_app.py").read_text(encoding="utf-8") == "def test_a(): assert True\n"
    assert not (repo / "nuevo_normal.py").exists()
    assert not (repo / "nuevo con espacio.py").exists()
    # Original file with a space left intact
    assert (repo / "mi modulo.py").read_text(encoding="utf-8") == "x=1\n"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
