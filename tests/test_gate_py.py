#!/usr/bin/env python3
"""Tests del orquestador portable gate.py (port de gate.sh).

Espejo de tests/test_gate.py, pero para el motor Python: NO depende de bash,
así que también corre en Windows. Donde importa el camino sin Git Bash se
fuerza la rama .py pasando `bash=""` (cadena vacía = "no hay bash"; `None`
significa autodetectar).

Contrato verificado (el mismo que consume loop.py):
  · un check que falla -> rc != 0 y NUNCA "[GATE] ✅ TODO OK";
  · un check que revienta -> rc != 0 (no un verde falso);
  · todos OK -> rc 0 + "[GATE] ✅ TODO OK";
  · sin checks o sin gate_checks/ -> rc 0 con aviso;
  · con bash se prefiere el .sh; sin bash se usa el .py.
"""

import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dedalo import gate  # noqa: E402

CHECK_FALLA = "def run(env):\n    env.fail('algo va mal')\n    return 1\n"
CHECK_OK = "def run(env):\n    env.ok('todo en orden')\n    return 0\n"
CHECK_REVIENTA = "def run(env):\n    raise RuntimeError('boom')\n"


def _escenario(tmp_path, checks):
    proyecto = tmp_path / "proyecto"
    (proyecto / "gate_checks").mkdir(parents=True)
    for nombre, cuerpo in checks.items():
        (proyecto / "gate_checks" / nombre).write_text(cuerpo, encoding="utf-8")
    return proyecto


def test_gate_falla_si_algun_check_falla(tmp_path, capsys):
    proyecto = _escenario(tmp_path, {"01_falla.py": CHECK_FALLA})
    rc = gate.correr(str(proyecto), bash="")
    salida = capsys.readouterr().out
    assert rc != 0, salida
    assert "TODO OK" not in salida, salida


def test_gate_pasa_si_todos_los_checks_pasan(tmp_path, capsys):
    proyecto = _escenario(tmp_path, {"01_ok.py": CHECK_OK})
    rc = gate.correr(str(proyecto), bash="")
    salida = capsys.readouterr().out
    assert rc == 0, salida
    assert "TODO OK" in salida, salida


def test_gate_check_que_revienta_no_da_verde(tmp_path, capsys):
    """Un check con excepción debe dar rc != 0, no un verde falso silencioso."""
    proyecto = _escenario(tmp_path, {"01_boom.py": CHECK_REVIENTA})
    rc = gate.correr(str(proyecto), bash="")
    salida = capsys.readouterr().out
    assert rc != 0, salida
    assert "TODO OK" not in salida, salida


def test_gate_separa_un_check_que_falla_de_uno_que_pasa(tmp_path, capsys):
    """El fallo temprano no se oculta tras el check posterior que pasa."""
    proyecto = _escenario(tmp_path, {"01_falla.py": CHECK_FALLA,
                                     "02_ok.py": CHECK_OK})
    rc = gate.correr(str(proyecto), bash="")
    salida = capsys.readouterr().out
    assert rc != 0, salida
    assert "TODO OK" not in salida, salida
    assert "01_falla.py" in salida, salida


def test_gate_sin_checks_no_falla(tmp_path, capsys):
    proyecto = _escenario(tmp_path, {})
    rc = gate.correr(str(proyecto), bash="")
    salida = capsys.readouterr().out
    assert rc == 0, salida
    assert "se asume OK" in salida, salida


def test_gate_sin_dir_checks_avisa_y_no_falla(tmp_path, capsys):
    proyecto = tmp_path / "p"
    proyecto.mkdir()
    rc = gate.correr(str(proyecto), bash="")
    salida = capsys.readouterr().out
    assert rc == 0, salida
    assert "se asume OK" in salida, salida


def test_gate_check_sin_run_se_omite_avisando(tmp_path, capsys):
    proyecto = _escenario(tmp_path, {"01_x.py": "x = 1\n"})
    rc = gate.correr(str(proyecto), bash="")
    salida = capsys.readouterr().out
    assert rc == 0, salida
    assert "sin función run()" in salida, salida


@pytest.mark.skipif(shutil.which("bash") is None, reason="sin bash")
def test_prefiere_sh_con_bash_y_py_sin_bash(tmp_path, capsys):
    """Con bash gana el check .sh; sin bash se usa el .py del mismo prefijo."""
    proyecto = _escenario(tmp_path, {"01_x.py": CHECK_FALLA})
    (proyecto / "gate_checks" / "01_x.sh").write_text(
        'ok "sh gana"\n', encoding="utf-8")
    # Con bash -> corre el .sh (verde aunque el .py fallaría).
    assert gate.correr(str(proyecto), bash=shutil.which("bash")) == 0
    capsys.readouterr()
    # Sin bash -> corre el .py (rojo).
    assert gate.correr(str(proyecto), bash="") != 0


def test_env_django_define_db_check_por_defecto(tmp_path):
    """Backend Django (manage.py): DB_CHECK toma el pg_isready de _env.sh.

    Regresión: la rama Django llamaba a `_db_por_defecto`, que no existía, y
    reventaba con NameError. Solo se activa con manage.py, por eso no la cubría
    ningún test hasta ahora."""
    from dedalo import gate_env
    proyecto = tmp_path / "p"
    (proyecto / "Backend").mkdir(parents=True)
    (proyecto / "Backend" / "manage.py").write_text("", encoding="utf-8")
    env = gate_env.detectar(str(proyecto),
                            environ={"PY_BACKEND": "/usr/bin/python3"})
    assert env.db_check is not None
    assert "pg_isready" in env.db_check.shell
