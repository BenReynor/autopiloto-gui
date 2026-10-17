#!/usr/bin/env python3
"""Tests for the gate.sh orchestrator.

The bug that motivated this file: `gate.sh` used `fail()` and `ok()`, which
were only defined in `gate_checks/_env.sh`. If a project was copied without
`_env.sh` (the "portable" use documented in dedalo.sh), a failing check
produced `fail: command not found` with rc=127, the loop ignored it because
there is no `set -e`, and the gate printed "✅ TODO OK" with rc=0. Since the
gate's rc decides the merge in dedalo.sh, that silently slipped broken code
into master.

Here the real gate.sh is exercised with stub checks, with and without `_env.sh`.
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
    """Copies gate.sh to a temp location and creates gate_checks/ with the given checks."""
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
    """A check with exit 1 must give rc!=0 and never print TODO OK."""
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
    """Without _env.sh the gate must still fail, and say why."""
    proyecto = _escenario(tmp_path, {"01_falla.sh": CHECK_FALLA}, con_env=False)
    r = _correr(proyecto)
    assert "orden no encontrada" not in r.stderr, (
        "fail() no está definida en la rama de retrocompat:\n" + r.stderr)
    assert "01_falla.sh" in r.stdout, r.stdout


def test_gate_separa_un_check_que_falla_de_uno_que_pasa(tmp_path):
    """The failure of an early check must not be hidden behind the later ones."""
    proyecto = _escenario(
        tmp_path,
        {"01_falla.sh": CHECK_FALLA, "02_ok.sh": CHECK_OK},
        con_env=False)
    r = _correr(proyecto)
    assert r.returncode != 0, r.stdout
    assert "TODO OK" not in r.stdout, r.stdout


def test_gate_sin_checks_no_falla(tmp_path):
    """Without checks there is nothing to verify: the gate must be green."""
    proyecto = _escenario(tmp_path, {}, con_env=False)
    r = _correr(proyecto)
    assert r.returncode == 0, r.stdout + r.stderr
