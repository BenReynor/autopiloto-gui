#!/usr/bin/env python3
"""Tests de cómo la GUI lanza el motor del loop (F4).

Cubre _argv_motor (dev = `python -m dedalo.loop`, binario =
`--dedalo-loop`) y un smoke real del arranque por `-m` desde otro cwd
(el mismo comando que construye la GUI, con PYTHONPATH al repo), skip si no
hay internet.
"""

import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from dedalo import net  # noqa: E402
from dedalo.app import _argv_motor, _raiz_codigo  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_argv_motor_dev():
    prog, argv = _argv_motor(False, ["--hasta", "23:00"])
    assert prog == sys.executable
    assert argv == ["-m", "dedalo.loop", "--hasta", "23:00"]


def test_argv_motor_binario():
    prog, argv = _argv_motor(True, ["--push"])
    assert prog == sys.executable
    assert argv == ["--dedalo-loop", "--push"]


def test_raiz_codigo_contiene_el_paquete():
    assert os.path.isdir(os.path.join(_raiz_codigo(), "dedalo"))


def _git(*args, cwd):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=T", *args],
                   cwd=cwd, check=True, capture_output=True)


@pytest.mark.skipif(shutil.which("bash") is None or os.name == "nt",
                    reason="el gate del motor y el agente falso son bash "
                           "(POSIX): se valida en Linux")
@pytest.mark.skipif(not net.hay_internet(), reason="requiere internet")
def test_arranque_por_python_m_desde_otro_cwd(tmp_path):
    """Comando exacto de la GUI en modo fuente: `python -m
    dedalo.loop` con cwd=proyecto y PYTHONPATH al repo."""
    proyecto = tmp_path / "proyecto"
    proyecto.mkdir()
    _git("init", "-q", "-b", "master", cwd=proyecto)
    _git("config", "user.email", "t@t", cwd=proyecto)
    _git("config", "user.name", "T", cwd=proyecto)
    (proyecto / "plan.md").write_text(
        "# PLAN\n\n- [ ] t1: crear modulo\n      criterio: existe a.py\n",
        encoding="utf-8")
    gate = proyecto / "gate.sh"
    gate.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    gate.chmod(0o755)
    _git("add", "-A", cwd=proyecto)
    _git("commit", "-q", "-m", "base", cwd=proyecto)

    dir_bin = tmp_path / "bin"
    dir_bin.mkdir()
    binario = dir_bin / "opencode"
    binario.write_text(
        "#!/usr/bin/env bash\n"
        'case "$1" in session) exit 0;; esac\n'
        "mkdir -p src\n"
        "printf 'x\\n' > src/a.py\n"
        "exit 0\n", encoding="utf-8")
    binario.chmod(0o755)

    env = dict(os.environ)
    env["PYTHONPATH"] = RAIZ
    env["PATH"] = f"{dir_bin}{os.pathsep}{env.get('PATH', '')}"
    env.update({
        "MAX_ITER": "1", "REVISION_DUAL": "0", "REVISION_MANUAL": "0",
        "TIMEOUT_POR_TAREA": "60", "VOZ": "0", "NAVEGADOR": "0",
        "CLI_OPENCODE": str(binario), "AGENTE_TAREA": "opencode",
    })

    proc = subprocess.run(
        [sys.executable, "-m", "dedalo.loop",
         str(proyecto / "plan.md")],
        cwd=str(proyecto), env=env, timeout=600, capture_output=True, text=True)

    log = (proyecto / "progreso.log").read_text(
        encoding="utf-8", errors="replace")
    assert proc.returncode == 0, (proc.stderr[-3000:]
                                  + log[-3000:])
    assert "DEDALO FINALIZADO" in log, log[-3000:]
    assert "- [x] t1" in (proyecto / "plan.md").read_text(encoding="utf-8")
    assert (proyecto / "src" / "a.py").exists()
