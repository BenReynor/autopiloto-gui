#!/usr/bin/env python3
"""Tests del orquestador gate.sh.

El bug que motivó este fichero: `gate.sh` usaba `fail()` y `ok()`, que sólo
estaban definidas en `gate_checks/_env.sh`. Si un proyecto se copytaba sin
`_env.sh` (uso "portable" documentado en dedalo.sh), un check que fallaba
provocaba `fail: orden no encontrada` con rc=127, el bucle lo ignoraba porque
no hay `set -e`, y el gate imprimía "✅ TODO OK" con rc=0. Como el rc del gate
decide el merge en dedalo.sh, eso meteía código roto en master en silencio.

Aquí se ejercita el gate.sh real con checks stubs, con y sin `_env.sh`.
"""

import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RAIZ = Path(__file__).resolve().parent.parent
PLANTILLAS = RAIZ / "dedalo" / "plantillas_data"
GATE = PLANTILLAS / "gate.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or os.name == "nt",
    reason="harness POSIX (gate.sh en bash): se valida en Linux")


def _escenario(tmp_path, checks, con_env):
    """Copia gate.sh a un temporal y crea gate_checks/ con los checks dados."""
    proyecto = tmp_path / "proyecto"
    proyecto.mkdir()
    shutil.copy2(GATE, proyecto / "gate.sh")
    checks_dir = proyecto / "gate_checks"
    checks_dir.mkdir()
    for nombre, cuerpo in checks.items():
        (checks_dir / nombre).write_text(textwrap.dedent(cuerpo), encoding="utf-8")
    if con_env:
        shutil.copy2(PLANTILLAS / "gate_checks" / "_env.sh",
                     checks_dir / "_env.sh")
    return proyecto


def _correr(proyecto):
    return subprocess.run(
        ["bash", str(proyecto / "gate.sh")],
        capture_output=True, text=True, timeout=30,
        cwd=str(proyecto))


CHECK_FALLA = """\
    #!/usr/bin/env bash
    echo "[GATE] ✗ algo va mal"
    exit 1
    """

CHECK_OK = """\
    #!/usr/bin/env bash
    ok "todo en orden"
    exit 0
    """


@pytest.mark.parametrize("con_env", [True, False],
                         ids=["con_env", "sin_env"])
def test_gate_falla_si_algun_check_falla(tmp_path, con_env):
    """Un check con exit 1 debe dar rc!=0 y nunca printing TODO OK."""
    proyecto = _escenario(tmp_path, {"01_falla.sh": CHECK_FALLA}, con_env)
    r = _correr(proyecto)
    assert r.returncode != 0, (
        f"el gate dio verde con un check fallido (rc={r.returncode})\n{r.stdout}")
    assert "TODO OK" not in r.stdout, r.stdout


@pytest.mark.parametrize("con_env", [True, False],
                         ids=["con_env", "sin_env"])
def test_gate_pasa_si_todos_los_checks_pasan(tmp_path, con_env):
    proyecto = _escenario(tmp_path, {"01_ok.sh": CHECK_OK}, con_env)
    r = _correr(proyecto)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "TODO OK" in r.stdout, r.stdout


def test_gate_no_da_verde_por_faltar_env_sin_avisar(tmp_path):
    """Sin _env.sh el gate debe seguir fallando, y decir por qué."""
    proyecto = _escenario(tmp_path, {"01_falla.sh": CHECK_FALLA}, con_env=False)
    r = _correr(proyecto)
    assert "orden no encontrada" not in r.stderr, (
        "fail() no está definida en la rama de retrocompat:\n" + r.stderr)
    assert "01_falla.sh" in r.stdout, r.stdout


def test_gate_separa_un_check_que_falla_de_uno_que_pasa(tmp_path):
    """El fallo de un check temprano no debe ocultarse tras los posteriores."""
    proyecto = _escenario(
        tmp_path,
        {"01_falla.sh": CHECK_FALLA, "02_ok.sh": CHECK_OK},
        con_env=False)
    r = _correr(proyecto)
    assert r.returncode != 0, r.stdout
    assert "TODO OK" not in r.stdout, r.stdout


def test_gate_sin_checks_no_falla(tmp_path):
    """Sin checks no hay nada que verificar: el gate debe ser verde."""
    proyecto = _escenario(tmp_path, {}, con_env=False)
    r = _correr(proyecto)
    assert r.returncode == 0, r.stdout + r.stderr
