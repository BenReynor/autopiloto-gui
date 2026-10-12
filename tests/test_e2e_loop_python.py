#!/usr/bin/env python3
"""E2E del motor Python completo (run() de autopiloto_gui.loop).

Espejo funcional de test_e2e_con_trabajo.py (el del motor bash): repo git con
plan de 1 tarea, gate de fixture, agente falso que crea src/nuevo.py y red
fakeada (monkeypatch de hay_internet, sin depender de la red real).

El run se ejecuta en proceso (run(cfg)) para poder falsificar la red; el
motor es el mismo que lanzaría la GUI como `python -m autopiloto_gui.loop`
(el entry point main() sólo parsea argv y llama a run; se cubre en los tests
de loop_args).
"""

import json
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autopiloto_gui.loop import Config, run  # noqa: E402
from autopiloto_gui.loop_args import parse_args  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLANTILLAS = os.path.join(RAIZ, "autopiloto_gui", "plantillas_data")

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or os.name == "nt",
    reason="el e2e ejecuta el gate con bash (no disponible en Windows)")


def _git(*args, cwd):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=T", *args],
                   cwd=cwd, check=True, capture_output=True)


def _agente_falso(dir_bin):
    """Agente falso: responde a `session` y a `run` (crea src/nuevo.py)."""
    dir_bin.mkdir(parents=True, exist_ok=True)
    bin_ = dir_bin / "opencode"
    bin_.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$1" = "session" ]; then\n'
        '    case "$2" in\n'
        '        list) echo "[]"; exit 0 ;;\n'
        '        delete) exit 0 ;;\n'
        '    esac\n'
        'fi\n'
        'mkdir -p src\n'
        'printf \'print("nuevo")\\n\' > src/nuevo.py\n'
        'echo \'{"usage":{"input_tokens":10,"output_tokens":10}}\'\n'
        'exit 0\n', encoding="utf-8")
    bin_.chmod(0o755)
    return bin_


def _escenario(tmp_path, gate_txt):
    """Proyecto git master con plan de 1 tarea y el gate dado."""
    proyecto = tmp_path / "proyecto"
    proyecto.mkdir()
    _git("init", "-q", "-b", "master", cwd=proyecto)
    _git("config", "user.email", "t@t", cwd=proyecto)
    _git("config", "user.name", "T", cwd=proyecto)
    (proyecto / "plan.md").write_text(
        "# PLAN\n\n- [ ] t1: crear modulo nuevo\n"
        "      criterio: existe src/nuevo.py\n", encoding="utf-8")
    checks = proyecto / "gate_checks"
    checks.mkdir()
    chk = checks / "01_x.sh"
    chk.write_text(gate_txt, encoding="utf-8")
    chk.chmod(0o755)
    _git("add", "-A", cwd=proyecto)
    _git("commit", "-q", "-m", "base", cwd=proyecto)
    return proyecto


def _entorno(binario):
    env = dict(os.environ)
    env.update({
        "PATH": f"{binario.parent}{os.pathsep}{os.environ.get('PATH', '')}",
        "MAX_ITER": "1",
        "REVISION_DUAL": "0",
        "REVISION_MANUAL": "0",
        "TIMEOUT_POR_TAREA": "60",
        "TIMEOUT_NAVEGADOR": "60",
        "VOZ": "0",
        "NAVEGADOR": "0",
        "CLI_OPENCODE": str(binario),
        "AGENTE_TAREA": "opencode",
        "MODELO_TAREA": "",
    })
    return env


def _correr(proyecto, env, extra_args=None):
    from unittest import mock

    import autopiloto_gui.net
    args = parse_args([str(proyecto / "plan.md")] + (extra_args or []))
    cfg = Config(args, environ=env, proyecto=str(proyecto))
    with mock.patch.object(autopiloto_gui.net, "hay_internet",
                           lambda: True):
        return run(cfg), cfg


def test_iteracion_con_trabajo_completa_el_run(tmp_path):
    gate = ("#!/usr/bin/env bash\n"
            'echo "$CRITERIO" > criterio_env.txt\n'
            "exit 0\n")
    proyecto = _escenario(tmp_path, gate)
    bin_falso = _agente_falso(tmp_path / "bin")

    rc, _cfg = _correr(proyecto, _entorno(bin_falso))
    log = (proyecto / "progreso.log").read_text(
        encoding="utf-8", errors="replace")

    assert rc == 0, log[-3000:]
    assert "AUTOPILOTO INICIADO" in log
    assert "AUTOPILOTO FINALIZADO" in log

    # La tarea se completó de verdad: commit + plan marcado [x].
    plan = (proyecto / "plan.md").read_text(encoding="utf-8")
    assert "- [x] t1" in plan, plan
    gitlog = subprocess.run(
        ["git", "log", "--all", "--format=%s"], cwd=str(proyecto),
        capture_output=True, text=True, check=True)
    assert any(linea.startswith("autopiloto:") for linea in gitlog.stdout.splitlines()), \
        gitlog.stdout

    # La rama de la tarea se fusionó en la rama del run y se borró.
    ramas = subprocess.run(["git", "branch"], cwd=str(proyecto),
                           capture_output=True, text=True, check=True)
    assert "autopiloto/tareas/" not in ramas.stdout, ramas.stdout
    assert any(linea.startswith("* autopiloto/") for linea in ramas.stdout.splitlines()), \
        ramas.stdout

    # El CRITERIO llegó al gate (env) y al agente no se le pasó --model vacío.
    assert (proyecto / "criterio_env.txt").read_text(
        encoding="utf-8").strip() == "existe src/nuevo.py"

    # metrics.jsonl con la métrica del agente (rc 0 y costo estimado).
    metricas = (proyecto / "metrics.jsonl").read_text(encoding="utf-8")
    d = json.loads(metricas.splitlines()[0])
    assert d["agente"] == "opencode" and d["rc"] == 0
    assert d["costo_usd"] > 0
    assert "Costo estimado acumulado:" in log


def test_tarea_que_no_pasa_el_gate_se_bloquea(tmp_path, capsys):
    """El gate falla DESPUÉS de trabajar (baseline pasa): tras los intentos
    la tarea queda marcada [B] sin commit, y el run termina con rc 0."""
    gate = ("#!/usr/bin/env bash\n"
            "if [ -e src/nuevo.py ]; then exit 1; fi\n"
            "exit 0\n")
    proyecto = _escenario(tmp_path, gate)
    bin_falso = _agente_falso(tmp_path / "bin")

    rc, _cfg = _correr(proyecto, _entorno(bin_falso))
    log = (proyecto / "progreso.log").read_text(
        encoding="utf-8", errors="replace")

    assert rc == 0, log[-3000:]
    assert "GATE FALLÓ tras el agente" in log
    assert "tarea BLOQUEADA: t1" in log
    assert "- [B] t1" in (proyecto / "plan.md").read_text(encoding="utf-8")
    gitlog = subprocess.run(
        ["git", "log", "--all", "--format=%s"], cwd=str(proyecto),
        capture_output=True, text=True, check=True)
    assert not any(linea.startswith("autopiloto:") for linea in gitlog.stdout.splitlines()), \
        "no debe haber commit de una tarea bloqueada"

    # incidencias.jsonl registra cada gate_fail y el bloqueo final, y el
    # bloqueo hereda el motivo real (gate_fail), no un texto genérico.
    inc = (proyecto / "incidencias.jsonl").read_text(encoding="utf-8")
    eventos = [json.loads(li) for li in inc.splitlines()]
    tipos = [e["tipo"] for e in eventos]
    assert "gate_fail" in tipos, tipos
    assert eventos[-1]["tipo"] == "bloqueada"
    assert "gate_fail" in eventos[-1]["motivo"], eventos[-1]

    # El resumen final (stdout) lista la tarea [B] con su motivo.
    salida = capsys.readouterr().out
    assert "TAREAS SIN COMPLETAR" in salida
    assert "- [B] t1" in salida


def test_sin_agente_aborta_con_2(tmp_path):
    """Agente explícito cuyo binario no existe → exit 2 sin tocar el loop."""
    proyecto = tmp_path / "proyecto"
    proyecto.mkdir()
    env = _entorno(tmp_path / "bin")
    env["CLI_OPENCODE"] = "/no/existe/opencode"

    rc, _cfg = _correr(proyecto, env)
    log = (proyecto / "progreso.log").read_text(
        encoding="utf-8", errors="replace") \
        if (proyecto / "progreso.log").exists() else ""
    assert rc == 2
    assert "ABORTADO: agente no disponible (opencode)" in log
    inc = (proyecto / "incidencias.jsonl").read_text(encoding="utf-8")
    assert json.loads(inc.splitlines()[0])["tipo"] == "aborto_agente"


def test_integracion_en_rama_de_trabajo(tmp_path):
    """Con --trabajo distinta, el trabajo se integra al final en esa rama."""
    gate = "#!/usr/bin/env bash\nexit 0\n"
    proyecto = _escenario(tmp_path, gate)
    bin_falso = _agente_falso(tmp_path / "bin")

    rc, _cfg = _correr(proyecto, _entorno(bin_falso),
                       extra_args=["--trabajo", "integra"])
    log = (proyecto / "progreso.log").read_text(
        encoding="utf-8", errors="replace")

    assert rc == 0, log[-3000:]
    assert "integrado" in log
    integra = subprocess.run(
        ["git", "log", "--format=%s", "integra"], cwd=str(proyecto),
        capture_output=True, text=True, check=True)
    assert any(linea.startswith("autopiloto:") for linea in integra.stdout.splitlines()), \
        integra.stdout
