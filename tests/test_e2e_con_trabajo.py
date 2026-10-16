#!/usr/bin/env python3
"""E2E del run completo de dedalo.sh con un agente falso que SÍ trabaja.

Regresión del bug más grave del script (línea ~1140): `local iter_sin_trabajo=0`
estaba en el top-level del fichero (dentro del while de reintentos, fuera de
cualquier función). En bash `local` fuera de función deja la variable SIN
CREAR, y la línea siguiente (`iteracion_sin_trabajo && iter_sin_trabajo=1`)
sólo la asigna si NO hay trabajo… así que cualquier iteración en la que el
agente producía cambios llegaba a la comprobación siguiente con `set -u` y
abortaba con `iter_sin_trabajo: unbound variable` → exit 1: sin commit, sin
marcar [x], sin resumen. Ningún test existente lo pillaba:

  · test_dedalo_senales.py sólo usa agentes que se bloquean o que no
    cambian nada (ahí la rama de la variable SÍ se asigna).
  · test_agentes.py extrae funciones sueltas y su arnés usa la forma
    corregida (`iter_sin_trabajo=0` sin `local`), reforzando el error.

También cubre el segundo bug de argumentos: `shift 2` sin comprobar `$#`
dejaba `--hasta/--padre/--trabajo` como ÚLTIMO argumento en un bucle
infinito de CPU al 100 %.
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

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or os.name == "nt",
    reason="el e2e ejecuta dedalo.sh con bash (no disponible en Windows)")


def _git(*args, cwd):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=T", *args],
                   cwd=cwd, check=True, capture_output=True)


def _agente_falso(dir_bin, con_trabajo: bool):
    """Agente falso rápido: responde a `session` y sale con 0 al instante.

    Si `con_trabajo`, crea un fichero nuevo (el camino que rompía el bug);
    si no, no toca el árbol (el camino que SÍ funcionaba y que enmascaraba
    la regresión).
    """
    dir_bin.mkdir(parents=True, exist_ok=True)
    cuerpo = ("mkdir -p src && echo \"print('nuevo')\" > src/nuevo.py\n"
              if con_trabajo else "true\n")
    bin_ = dir_bin / "opencode"
    bin_.write_text(textwrap.dedent(f"""\
        #!/usr/bin/env bash
        if [ "$1" = "session" ]; then
            case "$2" in
                list) echo "[]"; exit 0 ;;
                delete) exit 0 ;;
            esac
        fi
        {cuerpo}
        echo '{{"usage":{{"input_tokens":10,"output_tokens":10}}}}'
        exit 0"""), encoding="utf-8")
    bin_.chmod(0o755)
    return bin_


def _stub_red(dir_bin, nombre):
    """ping/curl falsos para que `hay_internet` no dependa de la red real."""
    stub = dir_bin / nombre
    stub.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    stub.chmod(0o755)


def _escenario(tmp_path, con_trabajo: bool):
    """Proyecto git con el framework copiado, un plan de 1 tarea y agente."""
    proyecto = tmp_path / "proyecto"
    proyecto.mkdir()
    _git("init", "-q", "-b", "master", cwd=proyecto)
    # Identidad a nivel de repo: los commits DEL LOOP (no los del fixture)
    # van sin `-c`, y sin ella `git commit` fallaría y el test no podría
    # distinguir el bug de un fallo de identidad.
    _git("config", "user.email", "t@t", cwd=proyecto)
    _git("config", "user.name", "T", cwd=proyecto)
    (proyecto / "plan.md").write_text(
        "# PLAN\n\n- [ ] t1: crear modulo nuevo\n"
        "      criterio: existe src/nuevo.py\n", encoding="utf-8")
    # El .gitignore es parte de la instalación real (plantillas.asegurar_gitignore):
    # excluye gate_checks/ y el resto del framework. Sin él, `ruff check .` del
    # gate lintearía los .py del port y el baseline abortaría.
    for nombre in ("dedalo.sh", "gate.sh", "mapear.sh", "lecciones.md",
                   ".gitignore"):
        origen = PLANTILLAS / nombre
        if origen.exists():
            shutil.copy2(origen, proyecto / nombre)
    shutil.copytree(PLANTILLAS / "gate_checks", proyecto / "gate_checks")
    _git("add", "-A", cwd=proyecto)
    _git("commit", "-q", "-m", "base", cwd=proyecto)

    dir_bin = tmp_path / "bin"
    _agente_falso(dir_bin, con_trabajo=con_trabajo)
    _stub_red(dir_bin, "ping")
    _stub_red(dir_bin, "curl")
    return proyecto, dir_bin


def _entorno(dir_bin):
    env = dict(os.environ)
    env.update({
        "PATH": f"{dir_bin}{os.pathsep}{os.environ.get('PATH', '')}",
        "MAX_ITER": "1",
        "MAX_REINTENTOS": "1",
        "REVISION_DUAL": "0",
        "REVISION_MANUAL": "0",
        "TIMEOUT_POR_TAREA": "60",
        "MAX_COSTO": "0",
        "VOZ": "0",
        "CLI_OPENCODE": str(dir_bin / "opencode"),
        "AGENTE_TAREA": "opencode",
        "DEDALO_GATE_CONSENT": "1",
    })
    return env


def _correr(proyecto, env):
    return subprocess.run(
        ["bash", "dedalo.sh", "plan.md"], cwd=str(proyecto), env=env,
        capture_output=True, text=True, timeout=120)


def test_iteracion_con_trabajo_completa_el_run(tmp_path):
    """REGRESIÓN 1134: con trabajo real el run debe terminar y commitear."""
    proyecto, dir_bin = _escenario(tmp_path, con_trabajo=True)

    proc = _correr(proyecto, _entorno(dir_bin))
    log_path = proyecto / "progreso.log"
    log = log_path.read_text(errors="replace") if log_path.exists() else ""
    combinado = proc.stdout + proc.stderr + log

    # El síntoma exacto del bug: `local` fuera de función + `set -u`.
    assert "unbound variable" not in combinado, combinado[-3000:]
    assert "sólo se puede usar dentro de una función" not in combinado, \
        combinado[-3000:]

    # El run debe terminar normalmente (con el bug salía 1 a media tarea).
    assert proc.returncode == 0, f"rc={proc.returncode}\n{combinado[-3000:]}"
    assert "DEDALO FINALIZADO" in log

    # La tarea se completó de verdad: commit + plan marcado.
    assert "- [x] t1" in (proyecto / "plan.md").read_text(encoding="utf-8"), \
        f"t1 sin marcar:\n{combinado[-3000:]}"
    loggit = subprocess.run(
        ["git", "log", "--all", "--format=%s"], cwd=str(proyecto),
        capture_output=True, text=True, check=True)
    assert any(linea.startswith("dedalo:") for linea in loggit.stdout.splitlines()), \
        f"no hubo commit de iteración:\n{loggit.stdout}"


def test_iteracion_sin_trabajo_no_crashea(tmp_path):
    """El otro camino del 1134 (agente que no cambia nada) tampoco debe
    abortar: ahí la variable SÍ se asignaba, pero el test lo fija para que
    ninguna de las dos ramas vuelva a romper."""
    proyecto, dir_bin = _escenario(tmp_path, con_trabajo=False)

    proc = _correr(proyecto, _entorno(dir_bin))
    log_path = proyecto / "progreso.log"
    log = log_path.read_text(errors="replace") if log_path.exists() else ""
    combinado = proc.stdout + proc.stderr + log

    assert "unbound variable" not in combinado, combinado[-3000:]
    assert proc.returncode == 0, f"rc={proc.returncode}\n{combinado[-3000:]}"
    assert "DEDALO FINALIZADO" in log


@pytest.mark.parametrize("opcion", ["--hasta", "--padre", "--trabajo"])
def test_opcion_sin_valor_no_deja_cuelgar(opcion):
    """REGRESIÓN: `shift 2` sin comprobar `$#` giraba para siempre si la
    opción venía como ÚLTIMO argumento (CPU al 100 %, se mataba con
    timeout). Ahora falla rápido con EX_USAGE (64)."""
    proc = subprocess.run(
        ["bash", str(PLANTILLAS / "dedalo.sh"), opcion],
        capture_output=True, text=True, timeout=10)
    assert proc.returncode == 64, (
        f"{opcion} sin valor: rc={proc.returncode}\n"
        f"stdout={proc.stdout}\nstderr={proc.stderr}")
    assert "falta valor" in proc.stderr
