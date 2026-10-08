#!/usr/bin/env python3
"""Tests del diff que recibe el revisor (diff_revision en autopiloto.sh).

El bug que motivó este fichero: `revisar_diff` pasaba la lista multilínea de
ficheros modificados como UN único argumento entrecomillado a `git diff`, es
decir como un pathspec literal con saltos de línea. Ese pathspec no casa con
ningún fichero, así que con dos o más ficheros modificados el revisor recibía
un diff vacío y aprobaba sin haber visto nada.

Se extrae `diff_revision` de la plantilla y se ejecuta con un repo git real
para comprobar que el diff llega completo.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RAIZ = Path(__file__).resolve().parent.parent
PLANTILLA = RAIZ / "autopiloto_gui" / "plantillas_data" / "autopiloto.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("git") is None
    or os.name == "nt",
    reason="harness POSIX (diff/CLIs falsos en bash): se valida en Linux")

CONTROL = r"plan\.md|progreso\.log|lecciones\.md|mapeo\.txt"


def _extraer_funcion(texto, nombre):
    """Devuelve el texto de `nombre() { ... }` usando balance de llaves."""
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
    """Ejecuta diff_revision() real contra el repo y devuelve su stdout."""
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
    """Con 3 ficheros modificados el diff debe traer los 3, no uno ni cero."""
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
    """plan.md/progreso.log son trazabilidad del autopiloto, no de la tarea."""
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
    """Si lo único modificado es CONTROL, el revisor debe saber que no hay diff."""
    repo, env = _repo(tmp_path)
    (repo / "plan.md").write_text("- [x] tarea\n", encoding="utf-8")
    r = _diff_revision(repo, env)
    assert r.returncode == 0, r.stderr
    assert "sin cambios" in r.stdout, r.stdout


def test_diff_revision_ignora_ficheros_nuevos_sin_anadir(tmp_path):
    """Un fichero sin `git add` también debe llegar al revisor (git add -N)."""
    repo, env = _repo(tmp_path)
    (repo / "suelto.py").write_text("y = 2\n", encoding="utf-8")
    r = _diff_revision(repo, env)
    assert r.returncode == 0, r.stderr
    assert "b/suelto.py" in r.stdout, r.stdout
