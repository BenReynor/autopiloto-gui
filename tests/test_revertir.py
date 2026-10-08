#!/usr/bin/env python3
"""Tests de revertir() en autopiloto.sh.

El bug que motivó este fichero: revertir() usaba comm -13 sobre snapshots que
sólo listaban nombres (sin prefijo de estado), así que en una rama recién
creada (BEFORE vacío) TODOS los cambios del agente (nuevos, modificados,
borrados) aparecían como "nuevos" y se borraban con rm -rf. Además, los
nombres con espacios llegaban entrecomillados de git status y rompían el
checkout/rm.

La solución: revertir() ahora lee git status --porcelain directamente,
distingue por tipo de cambio (?? nuevo, D borrado, M modificado) y actúa
correctamente en cada caso.
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
    reason="harness POSIX (revertir.sh en bash): se valida en Linux")


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
    (d / "test_app.py").write_text("def test_a(): assert True\n", encoding="utf-8")
    (d / "mi modulo.py").write_text("x=1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=d, check=True, env=env, timeout=30)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"],
                   cwd=d, check=True, env=env, timeout=30)
    # Crear rama de tarea (simula lo que hace autopiloto.sh)
    subprocess.run(["git", "checkout", "-q", "-b", "tarea", "master"],
                   cwd=d, check=True, env=env, timeout=30)
    return d, env


def _revertir(repo, env):
    """Ejecuta revertir() real contra el repo y devuelve su stdout."""
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
    """Si el agente borra un fichero tracked, revertir lo restaura."""
    repo, env = _repo(tmp_path)
    (repo / "app.py").unlink()  # agente lo borra

    r = _revertir(repo, env)
    assert r.returncode == 0, r.stderr
    assert (repo / "app.py").exists(), "app.py no se restauró"
    assert (repo / "app.py").read_text(encoding="utf-8") == "print('hola')\n"


def test_revertir_restaura_fichero_modificado_por_el_agente(tmp_path):
    """Si el agente modifica un fichero tracked, revertir lo restaura al original."""
    repo, env = _repo(tmp_path)
    (repo / "test_app.py").write_text("def test_b(): assert False\n", encoding="utf-8")

    r = _revertir(repo, env)
    assert r.returncode == 0, r.stderr
    assert (repo / "test_app.py").read_text(encoding="utf-8") == "def test_a(): assert True\n"


def test_revertir_borra_ficheros_nuevos_creados_por_el_agente(tmp_path):
    """Ficheros untracked creados por el agente se eliminan."""
    repo, env = _repo(tmp_path)
    (repo / "nuevo.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "otro.txt").write_text("basura\n", encoding="utf-8")

    r = _revertir(repo, env)
    assert r.returncode == 0, r.stderr
    assert not (repo / "nuevo.py").exists()
    assert not (repo / "otro.txt").exists()


def test_revertir_maneja_nombres_con_espacios(tmp_path):
    """Nombres con espacios en ficheros nuevos y modificados."""
    repo, env = _repo(tmp_path)
    # Nuevo con espacio
    (repo / "nuevo archivo.py").write_text("# nuevo\n", encoding="utf-8")
    # Modificado con espacio (el que ya existe en base)
    (repo / "mi modulo.py").write_text("x = 999\n", encoding="utf-8")

    r = _revertir(repo, env)
    assert r.returncode == 0, r.stderr
    # El nuevo con espacio debe desaparecer
    assert not (repo / "nuevo archivo.py").exists()
    # El modificado con espacio debe volver a su valor original
    assert (repo / "mi modulo.py").read_text(encoding="utf-8") == "x=1\n"


def test_revertir_no_toca_archivos_control(tmp_path):
    """plan.md, progreso.log, etc. no se borran ni restauran."""
    repo, env = _repo(tmp_path)
    (repo / "plan.md").write_text("- [x] tarea\n", encoding="utf-8")
    (repo / "progreso.log").write_text("== Iteración 1 ==\n", encoding="utf-8")
    # También crear un fichero nuevo normal para verificar que SÍ se borra
    (repo / "real.py").write_text("real\n", encoding="utf-8")

    r = _revertir(repo, env)
    assert r.returncode == 0, r.stderr
    assert (repo / "plan.md").exists()
    assert (repo / "progreso.log").exists()
    assert not (repo / "real.py").exists()


def test_revertir_mezcla_todos_los_tipos(tmp_path):
    """Escenario completo: borrado, modificado, nuevo, nuevo con espacio."""
    repo, env = _repo(tmp_path)
    (repo / "app.py").unlink()              # borrado
    (repo / "test_app.py").write_text("modificado\n")  # modificado
    (repo / "nuevo_normal.py").write_text("nuevo\n")   # nuevo
    (repo / "nuevo con espacio.py").write_text("nuevo\n")  # nuevo con espacio

    r = _revertir(repo, env)
    assert r.returncode == 0, r.stderr
    assert (repo / "app.py").exists() and (repo / "app.py").read_text(encoding="utf-8") == "print('hola')\n"
    assert (repo / "test_app.py").read_text(encoding="utf-8") == "def test_a(): assert True\n"
    assert not (repo / "nuevo_normal.py").exists()
    assert not (repo / "nuevo con espacio.py").exists()
    # Fichero original con espacio intacto
    assert (repo / "mi modulo.py").read_text(encoding="utf-8") == "x=1\n"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
