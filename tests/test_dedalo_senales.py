#!/usr/bin/env python3
"""Tests de las señales de dedalo.sh: "Detener" tiene que parar el loop.

Regresión de `trap limpiar_sesiones EXIT TERM INT`, que tenía tres fallos:

  1. Un trap no detiene un script. Bash ejecuta el handler y sigue con el bucle,
     así que la GUI tenía que esperar 5 s y recurrir a SIGKILL.
  2. Con EXIT y TERM/INT en la misma línea, la limpieza se ejecutaba DOS veces
     por una sola señal (una en el trap de la señal y otra al salir).
  3. El que más cuesta: con el agente en PRIMER PLANO, bash aplaza el handler
     del trap hasta que el hijo termina, porque así funciona un shell no
     interactivo. Traducido: "Detener" no hacía nada mientras opencode siguiera
     trabajando, que es justo cuando más urge parar.

Estos tests scaffoldean un proyecto git real, un agente falso y mandan SIGTERM
de verdad, midiendo que el script termine pronto y que no queden nietos vivos.
"""

import os
import shutil
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RAIZ = Path(__file__).resolve().parent.parent
PLANTILLAS = RAIZ / "dedalo" / "plantillas_data"
TMPDIR = Path(os.environ.get("TMPDIR", "/tmp"))

pytestmark = pytest.mark.skipif(
    # En Windows el módulo no tiene os.killpg/os.getpgid y los procesos no
    # tienen grupo POSIX: aunque exista Git Bash, esta suite no es válida.
    shutil.which("bash") is None or os.name == "nt",
    reason="bash no disponible o sin semántica POSIX de señales")


def _git(*args, cwd):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=T", *args],
                   cwd=cwd, check=True, capture_output=True)


def _script_que_registra_y_espera(destino):
    """Escribe su PID en `destino` y se queda esperando indefinidamente."""
    return f'echo "$$" >> {destino}\nexec sleep 600\n'


def _agente_falso(dir_bin, rapido=False):
    """Agente falso. `rapido` lo hace salir con 0 en vez de quedarse colgado.

    Tiene que saber responder a `session list` / `session delete`, porque
    dedalo.sh las invoca en `limpiar_sesiones` al salir. Si no, el test
    cuelga en la limpieza y parece que el SIGTERM no funciona.
    """
    dir_bin.mkdir(parents=True, exist_ok=True)
    if rapido:
        cuerpo = f'echo "$$" >> {dir_bin}/pids.txt\nexit 0\n'
    else:
        cuerpo = _script_que_registra_y_espera(dir_bin / "pids.txt")
    bin = dir_bin / "opencode"
    bin.write_text(textwrap.dedent(f"""\
        #!/usr/bin/env bash
        if [ "$1" = "session" ]; then
            case "$2" in
                list) echo "[]"; exit 0 ;;
                delete) exit 0 ;;
            esac
        fi
        {cuerpo}"""), encoding="utf-8")
    bin.chmod(0o755)
    return bin


def _escenario(tmp_path, agente_rapido=False):
    """Proyecto con el framework copiado, un plan de una tarea y agente falso."""
    proyecto = tmp_path / "proyecto"
    proyecto.mkdir()
    _git("init", "-q", "-b", "master", cwd=proyecto)
    (proyecto / "plan.md").write_text(
        "# PLAN\n\n- [ ] #1 hacer algo\n      criterio: algo existe\n",
        encoding="utf-8")
    # El .gitignore es parte de la instalación real (plantillas.asegurar_gitignore):
    # excluye gate_checks/ y el resto del framework. Sin él, `ruff check .` del
    # gate lintearía los .py del port y el baseline abortaría.
    for nombre in ("dedalo.sh", "gate.sh", "mapear.sh", "plan.md",
                   "lecciones.md", ".gitignore"):
        origen = PLANTILLAS / nombre
        if origen.exists():
            shutil.copy2(origen, proyecto / nombre)
    shutil.copytree(PLANTILLAS / "gate_checks", proyecto / "gate_checks")
    _git("add", "-A", cwd=proyecto)
    _git("commit", "-q", "-m", "base", cwd=proyecto)

    dir_bin = tmp_path / "bin"
    _agente_falso(dir_bin, rapido=agente_rapido)
    # El ICMP de los runners de GitHub está bloqueado (y `ping` existe, así
    # que el fallback curl de hay_internet no entra): sin estos stubs estos
    # tests dependerían de la red REAL y abortarían con "sin internet".
    _stub_red(dir_bin, "ping")
    _stub_red(dir_bin, "curl")
    return proyecto, dir_bin


def _stub_red(dir_bin, nombre):
    """ping/curl falsos para que `hay_internet` no dependa de la red real."""
    stub = dir_bin / nombre
    stub.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    stub.chmod(0o755)


def _entorno(dir_bin):
    return {
        "PATH": f"{dir_bin}{os.pathsep}{os.environ['PATH']}",
        "HOME": os.environ.get("HOME", "/tmp"),
        "MAX_ITER": "1",
        "REVISION_DUAL": "0",
        "REVISION_MANUAL": "0",
        "TIMEOUT_POR_TAREA": "600",
        "TIMEOUT_NAVEGADOR": "600",
        "MAX_COSTO": "0",
        "VOZ": "0",
        "CLI_OPENCODE": str(dir_bin / "opencode"),
        # Sin fijar el agente, la autodeteccion puede elegir claude segun
        # el PATH y el test no miraria al binario falso.
        "AGENTE_TAREA": "opencode",
    }


def _arrancar(proyecto, env, marca):
    """Arranca dedalo.sh y espera a que aparezca el fichero `marca`."""
    proc = subprocess.Popen(
        ["bash", "dedalo.sh", "plan.md"], cwd=str(proyecto), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        # Sesión propia: así el SIGTERM llega al script y a toda su familia sin
        # tocar al pytest, que comparte grupo de procesos con este test.
        start_new_session=True,
    )
    limite = time.time() + 90
    while time.time() < limite and proc.poll() is None:
        if Path(marca).exists():
            return proc
        time.sleep(0.2)
    return proc


def _parar(proc, sig=signal.SIGTERM, timeout=25):
    """Manda la señal al grupo entero y espera la salida."""
    t0 = time.time()
    os.killpg(os.getpgid(proc.pid), sig)
    try:
        salida = proc.communicate(timeout=timeout)[0]
        return proc.returncode, salida or "", time.time() - t0
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        salida = proc.communicate()[0]
        return None, salida or "", time.time() - t0


def _pids_de(fichero):
    return [int(x) for x in Path(fichero).read_text().split() if x.strip()]


def _vivos(pids):
    return [p for p in pids if Path(f"/proc/{p}").exists()]


def test_sigterm_para_el_loop_y_no_deja_nietos(tmp_path):
    """SIGTERM con el agente trabajando: sale en 143 y nadie sigue con vida."""
    proyecto, dir_bin = _escenario(tmp_path)
    env = _entorno(dir_bin)
    pids_txt = dir_bin / "pids.txt"

    proc = _arrancar(proyecto, env, pids_txt)
    assert pids_txt.exists(), "el agente nunca llegó a lanzarse"
    time.sleep(1.0)  # que se quede ya dentro del sleep

    rc, salida, elapsed = _parar(proc, signal.SIGTERM)

    assert rc == 143, f"se esperaba exit 143, hubo {rc}:\n{salida[-2000:]}"
    assert elapsed < 20, (
        f"tardó {elapsed:.1f}s en parar, con el agente durmiendo 600 s")

    pids = _pids_de(pids_txt)
    assert pids, "no se pudo saber el pid del agente"
    time.sleep(1.0)
    supervivientes = _vivos(pids)
    assert not supervivientes, (
        f"el agente seguía vivo tras detener el loop: {supervivientes}")


def test_sigint_sale_con_130(tmp_path):
    """SIGINT usa el código convencional 130, no 143."""
    proyecto, dir_bin = _escenario(tmp_path)
    env = _entorno(dir_bin)
    pids_txt = dir_bin / "pids.txt"

    proc = _arrancar(proyecto, env, pids_txt)
    assert pids_txt.exists(), "el agente nunca llegó a lanzarse"
    time.sleep(1.0)

    rc, salida, _ = _parar(proc, signal.SIGINT)

    assert rc == 130, f"se esperaba exit 130, hubo {rc}:\n{salida[-2000:]}"


def test_una_sola_limpieza_por_senal(tmp_path):
    """El handler corre una vez: el log no puede repetir la limpieza."""
    proyecto, dir_bin = _escenario(tmp_path)
    env = _entorno(dir_bin)
    pids_txt = dir_bin / "pids.txt"

    proc = _arrancar(proyecto, env, pids_txt)
    assert pids_txt.exists(), "el agente nunca llegó a lanzarse"
    time.sleep(1.0)

    rc, salida, _ = _parar(proc, signal.SIGTERM)
    assert rc == 143, salida[-2000:]

    log = proyecto / "progreso.log"
    texto = log.read_text(errors="replace") if log.exists() else ""
    # Con el bug anterior salían dos limpiezas: una por el trap de la señal y
    # otra por el EXIT que venía detrás.
    limpiezas = texto.count("Sesiones opencode eliminadas")
    assert limpiezas <= 1, (
        f"la limpieza se ejecutó {limpiezas} veces para una sola señal:\n"
        f"{texto[-2000:]}")


def test_no_quedan_ficheros_de_pid(tmp_path):
    """Ni por señal ni por salida normal debe quedar el fichero de PID."""
    previos = set(TMPDIR.glob("dedalo_hijo.*.pid"))

    proyecto, dir_bin = _escenario(tmp_path)
    env = _entorno(dir_bin)
    pids_txt = dir_bin / "pids.txt"
    proc = _arrancar(proyecto, env, pids_txt)
    assert pids_txt.exists(), "el agente nunca llegó a lanzarse"
    time.sleep(1.0)

    rc, salida, _ = _parar(proc, signal.SIGTERM)
    assert rc == 143, salida[-2000:]

    nuevos = set(TMPDIR.glob("dedalo_hijo.*.pid")) - previos
    assert not nuevos, f"quedaron ficheros de PID tras parar: {nuevos}"


def test_gate_interruptible_no_deja_huerfanos(tmp_path):
    """El gate también es un árbol de procesos que hay que cerrar.

    El gate se ejecuta como lado izquierdo de un pipe, o sea en un subshell, así
    que su PID no llega al padre: por eso _matar_hijo lo busca también en un
    fichero. Aquí el agente termina bien y el gate se queda colgado, que es el
    caso real: el gate lanza los tests del proyecto, que pueden tardar minutos.
    """
    proyecto, dir_bin = _escenario(tmp_path, agente_rapido=True)

    # Gate lento. Se sustituye ANTES de arrancar para que gate_intacto lo acepte
    # (compara contra la copia que el script hace al arrancar).
    pids_gate = tmp_path / "gate_pids.txt"
    (proyecto / "gate.sh").write_text(
        "#!/usr/bin/env bash\n"
        + _script_que_registra_y_espera(pids_gate), encoding="utf-8")

    env = _entorno(dir_bin)
    proc = _arrancar(proyecto, env, pids_gate)
    assert pids_gate.exists(), "el gate nunca llegó a ejecutarse"
    time.sleep(1.0)

    rc, salida, elapsed = _parar(proc, signal.SIGTERM)

    assert rc == 143, f"se esperaba exit 143, hubo {rc}:\n{salida[-2000:]}"
    assert elapsed < 20, f"tardó {elapsed:.1f}s en parar con el gate colgado"

    pids = _pids_de(pids_gate)
    assert pids, "no se pudo saber el pid del gate"
    time.sleep(1.0)
    supervivientes = _vivos(pids)
    assert not supervivientes, (
        f"el gate seguía vivo tras detener el loop: {supervivientes}")
