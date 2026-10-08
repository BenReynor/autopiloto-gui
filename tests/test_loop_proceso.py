#!/usr/bin/env python3
"""Tests para loop_proceso.py - control de subprocesos del loop nativo.

Los tests de timeout asumen POSIX (start_new_session + killpg). En Windows
el motor nativo es aún futuro; los helpers no crashean al importar, pero
estos escenarios se saltan.
"""

import json
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autopiloto_gui.loop_proceso import (
    RC_TIMEOUT,
    limpiar_sesiones,
    run_con_timeout,
)

POSIX = os.name == "posix"

pytestmark = pytest.mark.skipif(
    not POSIX, reason="muerte de grupos de procesos: POSIX")


def test_comando_normal_exit_code():
    rc, salida, timed_out = run_con_timeout(["sh", "-c", "exit 3"], 10)
    assert rc == 3
    assert timed_out is False
    assert salida == (None, None)


def test_comando_con_stdout_pipe():
    rc, (out, _err), timed_out = run_con_timeout(
        ["sh", "-c", "echo hola"], 10, stdout=subprocess.PIPE)
    assert rc == 0
    assert timed_out is False
    assert out.strip() == b"hola"


def test_timeout_devuelve_124():
    t0 = __import__("time").monotonic()
    rc, _salida, timed_out = run_con_timeout(["sleep", "30"], 1)
    elapsed = __import__("time").monotonic() - t0
    assert timed_out is True
    assert rc == RC_TIMEOUT
    assert elapsed < 8  # TERM mata before el grace de 5s


def test_timeout_mata_tambien_al_hijo_colgado():
    # El hijo directo deja un nieto esperando en el mismo grupo: si sólo
    # matáramos al primero, el nieto quedaría huérfano (bug que _matar_hijo
    # resuelve con pgrep; aquí killpg cubre el grupo entero).
    t0 = __import__("time").monotonic()
    rc, (out, _err), timed_out = run_con_timeout(
        ["sh", "-c", "sleep 60 & echo $!; wait"],
        1, stdout=subprocess.PIPE)
    elapsed = __import__("time").monotonic() - t0
    assert timed_out is True
    assert rc == RC_TIMEOUT
    assert elapsed < 8
    nieto = int(out.strip())
    vivo = True
    for _ in range(10):
        try:
            os.kill(nieto, 0)
        except (ProcessLookupError, PermissionError):
            vivo = False
            break
        __import__("time").sleep(0.2)
    assert vivo is False, "el nieto quedó huérfano con vida"


def _stub_opencode(dir_bin, sesiones, log_ruta):
    """Crea un fake `opencode` que responde a `session list/delete`.

    El JSON de `session list` viaja por la variable de entorno SESIONES_JSON
    (el stub hereda el entorno del test), y cada `session delete <id>` se
    apunta en `log_ruta` para poder comprobar qué se borró.
    """
    os.environ["SESIONES_JSON"] = json.dumps([
        {"id": k, "directory": dir_, "created": c}
        for k, dir_, c in sesiones["lista"]
    ])
    dir_bin.mkdir(parents=True, exist_ok=True)
    texto = (
        "#!/usr/bin/env bash\n"
        "if [ \"$1\" = session ] && [ \"$2\" = list ]; then\n"
        "  printf '%s\\n' \"$SESIONES_JSON\"\n"
        "  exit 0\n"
        "fi\n"
        "if [ \"$1\" = session ] && [ \"$2\" = delete ]; then\n"
        "  echo \"$3\" >> '{LOG}'\n"
        "  exit 0\n"
        "fi\n"
        "exit 0\n"
    ).replace("{LOG}", log_ruta)
    binario = dir_bin / "opencode"
    binario.write_text(texto, encoding="utf-8")
    binario.chmod(0o755)
    return str(binario)


def test_limpiar_sesiones_filtra_y_borra(tmp_path):
    if not shutil.which("bash"):
        pytest.skip("bash obligatorio para el stub")
    proy = str(tmp_path / "proyecto")
    log_ruta = str(tmp_path / "deleted.log")
    stub = _stub_opencode(
        tmp_path / "bin", {
            "lista": [
                ("a1", proy, 2000),
                ("b2", "/otro", 2000),
                ("c3", proy, 500),
            ],
        }, log_ruta)
    n = limpiar_sesiones(stub, proy, desde_ms=1000, log=str(tmp_path / "run.log"))
    assert n == 1
    with open(log_ruta, encoding="utf-8") as f:
        borradas = f.read().split()
    assert borradas == ["a1"]
    with open(tmp_path / "run.log", encoding="utf-8") as f:
        assert "Sesiones opencode eliminadas: 1" in f.read()


def test_limpiar_sesiones_sin_binario():
    assert limpiar_sesiones("", "/proy", 0, None) == 0
    assert limpiar_sesiones("/no/existe/opencode", "/proy", 0, None) == 0


def test_limpiar_sesiones_json_invalido_no_revienta(tmp_path):
    if not shutil.which("bash"):
        pytest.skip("bash obligatorio para el stub")
    binario = tmp_path / "opencode"
    binario.write_text(
        "#!/usr/bin/env bash\necho 'no-soy-json'\nexit 0\n", encoding="utf-8")
    binario.chmod(0o755)
    assert limpiar_sesiones(str(binario), "/proy", 0, None) == 0
