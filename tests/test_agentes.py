#!/usr/bin/env python3
"""Tests del soporte multiagente (opencode / codex / claude).

No se requiere ninguna suscripción: se crean CLIs falsos en un PATH temporal y
se ejercitan las funciones reales de la plantilla (autodetección, flags de
invocación, corte por falta de login y juez de criterio) más la detección de
agentes instalados que usa la GUI.
"""

import json
import os
import shutil
import stat
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLANTILLA = os.path.join(RAIZ, "autopiloto_gui", "plantillas_data",
                         "autopiloto.sh")
JUEZ = os.path.join(RAIZ, "autopiloto_gui", "plantillas_data",
                    "gate_checks", "98_criterio.sh")

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None, reason="bash no disponible")


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


def _leer_plantilla():
    with open(PLANTILLA, encoding="utf-8") as f:
        return f.read()


# run_agente depende de ejecutar_esperando y de las variables AGENTE_PID/
# PID_HIJO. Cualquier harness que lo extraiga debe incluir estas piezas, o
# obtendrá "command not found" (rc=127) en vez del código de salida real.
_PRELUPIO_RUN_AGENTE = (
    'AGENTE_PID=""\nPID_HIJO="${TMPDIR:-/tmp}/harness_agente.$$.pid"\n'
    + _extraer_funcion(_leer_plantilla(), "ejecutar_esperando") + "\n\n"
)


def _extraer_run_agente(texto, *extras):
    """Bloque listo para `run_agente` con sus dependencias."""
    partes = [_PRELUPIO_RUN_AGENTE]
    partes += [_extraer_funcion(texto, n) for n in extras]
    partes.append(_extraer_funcion(texto, "run_agente"))
    return "\n\n".join(partes)


def _valor_control():
    """Saca el valor real de CONTROL= de la plantilla para no duplicarlo."""
    for linea in _leer_plantilla().splitlines():
        if linea.startswith("CONTROL="):
            return linea[len("CONTROL="):].strip().strip('"')
    raise AssertionError("no se encontró CONTROL= en la plantilla")


_CONTROL = _valor_control()


def _cli_falso(directorio, nombre, cuerpo):
    """Escribe un CLI ejecutable que registra sus argumentos y devuelve cuerpo."""
    ruta = os.path.join(directorio, nombre)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write("#!/usr/bin/env bash\n"
                'printf "%s\\n" "$*" >> "$REG_ARGS"\n')
        f.write(cuerpo)
    os.chmod(ruta, os.stat(ruta).st_mode | stat.S_IEXEC | stat.S_IXGRP
             | stat.S_IXOTH)
    return ruta


# ---------- estado de sesión (login) ----------

def _monkey_cli(monkeypatch, modelos, tmp_path, disponibles, cuerpos):
    """Fakea `which` y el contenido de cada CLI para sondear su sesión."""
    d = str(tmp_path)
    for nombre in disponibles:
        _cli_falso(d, nombre, cuerpos[nombre])
    monkeypatch.setattr(modelos.shutil, "which", lambda n: (
        os.path.join(d, n) if n in disponibles else None))
    monkeypatch.setenv("HOME", str(tmp_path))
    modelos.invalidar_cache()


def test_sesion_detecta_sin_login(monkeypatch, tmp_path):
    from autopiloto_gui import modelos

    _monkey_cli(monkeypatch, modelos, tmp_path, {"claude"},
                {"claude": 'echo "Not logged in · Please run /login"\n'})
    assert modelos.sesion_agente("claude") is False


def test_sesion_detecta_login_correcto(monkeypatch, tmp_path):
    from autopiloto_gui import modelos

    _monkey_cli(monkeypatch, modelos, tmp_path, {"claude"},
                {"claude": 'echo "pong"\n'})
    assert modelos.sesion_agente("claude") is True


def test_sesion_opencode_es_desconocida_sin_credenciales(monkeypatch, tmp_path):
    """`opencode auth list` responde 0 siempre: 0 credenciales no es prueba de
    que no sirva (los modelos free del catálogo no necesitan key)."""
    from autopiloto_gui import modelos

    _monkey_cli(monkeypatch, modelos, tmp_path, {"opencode"},
                {"opencode": 'echo "0 credentials"\n'})
    assert modelos.sesion_agente("opencode") is None


def test_sesion_timeout_es_desconocida(monkeypatch, tmp_path):
    from autopiloto_gui import modelos

    _monkey_cli(monkeypatch, modelos, tmp_path, {"claude"},
                {"claude": "sleep 30\n"})
    modelos.SONDA_SESION["claude"] = (["-p", "ping"], 1)
    try:
        assert modelos.sesion_agente("claude") is None
    finally:
        modelos.SONDA_SESION["claude"] = (
            ["-p", "--output-format", "text", "ping"], 20)


def test_sesion_se_cachea(monkeypatch, tmp_path):
    from autopiloto_gui import modelos

    _monkey_cli(monkeypatch, modelos, tmp_path, {"claude"},
                {"claude": 'echo "Not logged in"\n'})
    assert modelos.sesion_agente("claude") is False
    # Segunda llamada: no vuelve a lanzar el CLI (quedaría cacheado False).
    modelos.shutil.which = lambda n: (_ for _ in ()).throw(
        AssertionError("no debe volver a sondear"))
    assert modelos.sesion_agente("claude") is False


def test_agentes_operativos_excluye_sin_login(monkeypatch, tmp_path):
    """El agente sin sesión se detecta pero no se ofrece para trabajar."""
    from autopiloto_gui import modelos

    _monkey_cli(monkeypatch, modelos, tmp_path, {"opencode", "claude"},
                {"opencode": 'echo "0 credentials"\n',
                 "claude": 'echo "Not logged in · Please run /login"\n'})
    assert modelos.agentes_instalados() == ["opencode", "claude"]
    assert modelos.agentes_operativos() == ["opencode"]
    assert modelos.agente_por_defecto() == "opencode"


def test_agentes_operativos_con_dos_con_sesion(monkeypatch, tmp_path):
    from autopiloto_gui import modelos

    _monkey_cli(monkeypatch, modelos, tmp_path, {"codex", "claude"},
                {"codex": 'echo "pong"\n', "claude": 'echo "pong"\n'})
    assert modelos.agentes_operativos() == ["codex", "claude"]


def test_agentes_operativos_ignora_no_instalado(monkeypatch, tmp_path):
    from autopiloto_gui import modelos

    _monkey_cli(monkeypatch, modelos, tmp_path, {"claude"},
                {"claude": 'echo "Not logged in"\n'})
    assert modelos.agentes_operativos() == []
    assert modelos.agente_por_defecto() == ""


def test_estado_agentes_tecnifica(monkeypatch, tmp_path):
    from autopiloto_gui import modelos

    _monkey_cli(monkeypatch, modelos, tmp_path, {"claude"},
                {"claude": 'echo "Not logged in"\n'})
    por_nombre = {e["nombre"]: e for e in modelos.estado_agentes()}
    assert por_nombre["opencode"]["instalado"] is False
    assert por_nombre["codex"]["instalado"] is False
    assert por_nombre["claude"]["instalado"] is True
    assert por_nombre["claude"]["sesion"] is False
    assert por_nombre["claude"]["ruta"].endswith("claude")


# ---------- detección de agentes instalados (Python / GUI) ----------

def test_agentes_instalados_respeta_preferencia(tmp_path):
    from autopiloto_gui import modelos

    d = str(tmp_path)
    _cli_falso(d, "claude", "exit 0\n")
    _cli_falso(d, "codex", "exit 0\n")

    # Sólo codex y claude existen: opencode NO debe ganar aunque sea el primero
    # de la lista de preferencia. HOME aislado para que el fallback
    # ~/.opencode/bin del equipo de pruebas no se cuele.
    monkey = pytest.MonkeyPatch()
    monkey.setattr(modelos.shutil, "which", lambda n: (
        os.path.join(d, n) if n in ("codex", "claude") else None))
    monkey.setenv("HOME", str(tmp_path))
    try:
        assert modelos.agentes_instalados() == ["codex", "claude"]
        assert modelos.agente_por_defecto() == "codex"
        assert modelos.ruta_binario("opencode") == ""
        assert modelos.agentes_instalados(preferidos=("claude", "codex")) == [
            "claude", "codex"]
    finally:
        monkey.undo()


def test_agentes_instalados_vacio_no_inventa(tmp_path):
    from autopiloto_gui import modelos

    monkey = pytest.MonkeyPatch()
    monkey.setattr(modelos.shutil, "which", lambda n: None)
    monkey.setenv("HOME", str(tmp_path))
    try:
        assert modelos.agentes_instalados() == []
        assert modelos.agente_por_defecto() == ""
    finally:
        monkey.undo()


def test_ruta_binario_usa_fallback_dot_dir(tmp_path):
    """Instalado en ~/.codex/bin/codex y fuera del PATH: debe resolverse."""
    from autopiloto_gui import modelos

    d = tmp_path / ".codex" / "bin"
    d.mkdir(parents=True)
    binario = d / "codex"
    binario.write_text("#!/usr/bin/env bash\nexit 0\n")
    binario.chmod(0o755)

    monkey = pytest.MonkeyPatch()
    monkey.setattr(modelos.shutil, "which", lambda n: None)
    monkey.setenv("HOME", str(tmp_path))
    try:
        assert modelos.ruta_binario("codex") == str(binario)
        assert modelos.ruta_binario("claude") == ""
    finally:
        monkey.undo()


# ---------- autodetección en bash ----------

def _harness_deteccion(tmp_path, instalados):
    """Ejecuta detectar_agente/elegir_revisor con un PATH controlado."""
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    for nombre in ("opencode", "codex", "claude"):
        if nombre in instalados:
            _cli_falso(str(d), nombre, "exit 0\n")
    texto = _leer_plantilla()
    (tmp_path / "func.sh").write_text("\n\n".join([
        _extraer_funcion(texto, "sin_autenticacion"),
        _extraer_funcion(texto, "detectar_agente"),
        _extraer_funcion(texto, "cli_agente"),
        _extraer_funcion(texto, "agente_ok"),
        _extraer_funcion(texto, "elegir_revisor"),
    ]), encoding="utf-8")

    script = r'''
. "$1"
logx() { :; }
alerta() { :; }
AGENTES_PREFERIDOS="$2"
echo "detectado=$(detectar_agente)"
AGENTE_TAREA="$(detectar_agente)"
AGENTE_REVISOR="auto"
REVISION_DUAL="1"
echo "revisor=$(elegir_revisor)"
AGENTE_TAREA="opencode"
AGENTE_REVISOR="opencode"
echo "revisor_mismo=$(elegir_revisor)"
'''
    (tmp_path / "run.sh").write_text(script, encoding="utf-8")
    env = {"PATH": f"{d}:/usr/bin:/bin", "HOME": str(tmp_path)}
    return subprocess.run(
        ["bash", str(tmp_path / "run.sh"), str(tmp_path / "func.sh"),
         "opencode codex claude"],
        capture_output=True, text=True, timeout=30, env=env)


def test_autodetecta_claude_si_es_el_unico(tmp_path):
    r = _harness_deteccion(tmp_path, {"claude"})
    assert r.returncode == 0, r.stderr
    assert "detectado=claude" in r.stdout
    # "auto" = sin preferencia: con un solo agente, el revisor es ese mismo.
    assert "revisor=claude" in r.stdout


def test_autodetecta_segun_preferencia(tmp_path):
    r = _harness_deteccion(tmp_path, {"opencode", "codex", "claude"})
    assert "detectado=opencode" in r.stdout

    texto = _leer_plantilla()
    (tmp_path / "func.sh").write_text("\n\n".join([
        _extraer_funcion(texto, "detectar_agente"),
        _extraer_funcion(texto, "cli_agente"),
        _extraer_funcion(texto, "agente_ok"),
    ]), encoding="utf-8")
    script = '. "$1"\nAGENTES_PREFERIDOS="claude codex opencode"\n' \
             'echo "detectado=$(detectar_agente)"\n'
    (tmp_path / "run2.sh").write_text(script, encoding="utf-8")
    r2 = subprocess.run(
        ["bash", str(tmp_path / "run2.sh"), str(tmp_path / "func.sh")],
        capture_output=True, text=True, timeout=30,
        env={"PATH": f"{tmp_path / 'bin'}:/usr/bin:/bin",
             "HOME": str(tmp_path)})
    assert "detectado=claude" in r2.stdout


def test_autodetecta_vacio_sin_agentes(tmp_path):
    r = _harness_deteccion(tmp_path, set())
    assert r.returncode == 0, r.stderr
    assert "detectado=\n" in r.stdout
    assert "revisor=\n" in r.stdout


def test_revisor_explicito_gana_a_otro_agente(tmp_path):
    """La GUI resuelve 'auto' al detectado y lo envía explícito: si el usuario
    (o la GUI) pidió opencode, el revisor es opencode aunque haya otro CLI."""
    r = _harness_deteccion(tmp_path, {"opencode", "claude"})
    assert "detectado=opencode" in r.stdout
    assert "revisor_mismo=opencode" in r.stdout


def test_revisor_auto_prefiere_otro_agente(tmp_path):
    """Sin preferencia explícita, busca ojos frescos (otro agente)."""
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    _cli_falso(str(d), "opencode", "exit 0\n")
    _cli_falso(str(d), "claude", "exit 0\n")
    texto = _leer_plantilla()
    (tmp_path / "func.sh").write_text("\n\n".join([
        _extraer_funcion(texto, "detectar_agente"),
        _extraer_funcion(texto, "cli_agente"),
        _extraer_funcion(texto, "agente_ok"),
        _extraer_funcion(texto, "elegir_revisor"),
    ]), encoding="utf-8")
    (tmp_path / "run.sh").write_text(
        '. "$1"\nAGENTES_PREFERIDOS="opencode codex claude"\n'
        'AGENTE_TAREA=opencode\nAGENTE_REVISOR=auto\n'
        'echo "revisor=$(elegir_revisor)"\n', encoding="utf-8")
    r = subprocess.run(
        ["bash", str(tmp_path / "run.sh"), str(tmp_path / "func.sh")],
        capture_output=True, text=True, timeout=30,
        env={"PATH": f"{d}:/usr/bin:/bin", "HOME": str(tmp_path)})
    assert "revisor=claude" in r.stdout, r.stdout + r.stderr


def test_revisor_auto_con_un_solo_agente_reusa_el_mismo(tmp_path):
    """Si no hay un segundo CLI, revisa el mismo antes que dejar el gate vacío."""
    r = _harness_deteccion(tmp_path, {"opencode"})
    assert "detectado=opencode" in r.stdout
    assert "revisor=opencode" in r.stdout


def test_agente_ok_rechaza_la_etiqueta_decorativa_del_combo(tmp_path):
    """La etiqueta "auto → opencode" es para el ojo; el env exige el valor.

    Si la GUI mandara la etiqueta, cli_agente cae en su rama *) y devuelve "",
    por lo que agente_ok falla y autopiloto.sh aborta con exit 2. Este test
    fija esa frontera para que config() no vuelva a leer currentText().
    """
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    _cli_falso(str(d), "opencode", "exit 0\n")
    texto = _leer_plantilla()
    (tmp_path / "func.sh").write_text("\n\n".join([
        _extraer_funcion(texto, "cli_agente"),
        _extraer_funcion(texto, "agente_ok"),
    ]), encoding="utf-8")
    (tmp_path / "run.sh").write_text(
        '. "$1"\n'
        'for v in "auto → opencode" "opencode" "codex"; do\n'
        '    if agente_ok "$v"; then echo "$v OK"; else echo "$v FALLA"; fi\n'
        'done\n', encoding="utf-8")
    r = subprocess.run(
        ["bash", str(tmp_path / "run.sh"), str(tmp_path / "func.sh")],
        capture_output=True, text=True, timeout=30,
        env={"PATH": f"{d}:/usr/bin:/bin", "HOME": str(tmp_path)})
    assert "auto → opencode FALLA" in r.stdout, r.stdout + r.stderr
    assert "opencode OK" in r.stdout, r.stdout + r.stderr


# ---------- invocación por CLI ----------

def _harness_run_agente(tmp_path, agent_stub_body, modelo="", metrica_real=True):
    texto = _leer_plantilla()
    metricas = (_extraer_funcion(texto, "_registrar_metrica")
                if metrica_real else "_registrar_metrica() { :; }\n")
    (tmp_path / "func.sh").write_text("\n\n".join([
        _extraer_funcion(texto, "sin_autenticacion"),
        _extraer_funcion(texto, "detectar_agente"),
        _extraer_funcion(texto, "cli_agente"),
        _extraer_funcion(texto, "agente_ok"),
        # run_agente llama a ejecutar_esperando, que es la que pone al hijo en
        # segundo plano para que un SIGTERM no espere a que termine. Sin ella
        # aquí, el harness daría 127 (command not found) y los asserts de los
        # tests pasarían a comprobar el error equivocado.
        'AGENTE_PID=""\nPID_HIJO="${TMPDIR:-/tmp}/harness_agente.$$.pid"\n',
        _extraer_funcion(texto, "ejecutar_esperando"),
        _extraer_funcion(texto, "run_agente"),
        metricas,
        "logx() { :; }\n"
        "alerta() { :; }\n",
    ]), encoding="utf-8")
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    _cli_falso(str(d), "codex", agent_stub_body)
    (tmp_path / "out").write_text("", encoding="utf-8")
    script = r'''
. "$1"
LOG="$2/out.log"
PROYECTO="$2"
TIMEOUT_POR_TAREA=10
OPENCODE_AGENT_TAREA=build
run_agente codex "$2/out" "$3" "TAREA DE PRUEBA"
echo "rc=$?"
'''
    (tmp_path / "run.sh").write_text(script, encoding="utf-8")
    return subprocess.run(
        ["bash", str(tmp_path / "run.sh"), str(tmp_path / "func.sh"),
         str(tmp_path), modelo],
        capture_output=True, text=True, timeout=30,
        env={"PATH": f"{d}:/usr/bin:/bin", "HOME": str(tmp_path),
             "CLI_CODEX": str(d / "codex"), "REG_ARGS": str(tmp_path / "args")})


def test_codex_usa_exec_y_skip_git_repo_check(tmp_path):
    r = _harness_run_agente(tmp_path, 'echo "hecho"\n')
    assert r.returncode == 0, r.stderr
    assert "rc=0" in r.stdout
    args = (tmp_path / "args").read_text()
    assert "exec" in args
    assert "--skip-git-repo-check" in args
    assert "TAREA DE PRUEBA" in args
    # codex no recibe --model (no existe ese flag en `codex exec`).
    assert "--model" not in args


def test_claude_usa_modo_print_y_sin_modelo(tmp_path):
    texto = _leer_plantilla()
    (tmp_path / "func.sh").write_text("\n\n".join([
        _extraer_funcion(texto, "cli_agente"),
        _extraer_run_agente(texto),
        "_registrar_metrica() { :; }\n",
    ]), encoding="utf-8")
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    _cli_falso(str(d), "claude", 'echo "hecho"\n')
    (tmp_path / "run.sh").write_text(
        '. "$1"\nLOG="$2/out.log"\nPROYECTO="$2"\nTIMEOUT_POR_TAREA=10\n'
        'run_agente claude "$2/out" "" "TAREA DE PRUEBA"\necho "rc=$?"\n',
        encoding="utf-8")
    r = subprocess.run(
        ["bash", str(tmp_path / "run.sh"), str(tmp_path / "func.sh"),
         str(tmp_path)],
        capture_output=True, text=True, timeout=30,
        env={"PATH": f"{d}:/usr/bin:/bin", "HOME": str(tmp_path),
             "CLI_CLAUDE": str(d / "claude"),
             "REG_ARGS": str(tmp_path / "args")})
    assert r.returncode == 0, r.stderr
    assert "rc=0" in r.stdout
    args = (tmp_path / "args").read_text()
    assert "-p" in args
    assert "--output-format text" in args
    assert "--model" not in args


def test_claude_no_recibe_argumento_vacio(tmp_path):
    """Regresión: `${CLAUDE_FLAGS:-}` entrecomillado añadía un argumento vacío
    y claude lo tomaba como el prompt, dejando el prompt real huérfano."""
    texto = _leer_plantilla()
    (tmp_path / "func.sh").write_text("\n\n".join([
        _extraer_funcion(texto, "cli_agente"),
        _extraer_run_agente(texto),
        "_registrar_metrica() { :; }\n",
    ]), encoding="utf-8")
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    # El stub falla si recibe un argumento vacío, como hace claude en realidad.
    _cli_falso(str(d), "claude",
               'for a in "$@"; do [ -n "$a" ] || exit 9; done\n'
               'echo "hecho"\n')
    (tmp_path / "run.sh").write_text(
        '. "$1"\nLOG="$2/out.log"\nPROYECTO="$2"\nTIMEOUT_POR_TAREA=10\n'
        'CLAUDE_FLAGS=""\n'
        'run_agente claude "$2/out" "" "TAREA DE PRUEBA"\necho "rc=$?"\n',
        encoding="utf-8")
    r = subprocess.run(
        ["bash", str(tmp_path / "run.sh"), str(tmp_path / "func.sh"),
         str(tmp_path)],
        capture_output=True, text=True, timeout=30,
        env={"PATH": f"{d}:/usr/bin:/bin", "HOME": str(tmp_path),
             "CLI_CLAUDE": str(d / "claude"),
             "REG_ARGS": str(tmp_path / "args")})
    assert "rc=0" in r.stdout, f"argumento vacío pasado a claude:\n{r.stdout}"


def test_codex_recibe_flags_sin_argumentos_vacios(tmp_path):
    """CODEX_FLAGS con varios flags deben llegar troceados, sin huecos."""
    texto = _leer_plantilla()
    (tmp_path / "func.sh").write_text("\n\n".join([
        _extraer_funcion(texto, "cli_agente"),
        _extraer_run_agente(texto),
        "_registrar_metrica() { :; }\n",
    ]), encoding="utf-8")
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    _cli_falso(str(d), "codex",
               'for a in "$@"; do [ -n "$a" ] || exit 9; done\n'
               'echo "hecho"\n')
    (tmp_path / "run.sh").write_text(
        '. "$1"\nLOG="$2/out.log"\nPROYECTO="$2"\nTIMEOUT_POR_TAREA=10\n'
        'CODEX_FLAGS="-s danger-full-access"\n'
        'run_agente codex "$2/out" "" "TAREA"\necho "rc=$?"\n',
        encoding="utf-8")
    r = subprocess.run(
        ["bash", str(tmp_path / "run.sh"), str(tmp_path / "func.sh"),
         str(tmp_path)],
        capture_output=True, text=True, timeout=30,
        env={"PATH": f"{d}:/usr/bin:/bin", "HOME": str(tmp_path),
             "CLI_CODEX": str(d / "codex"),
             "REG_ARGS": str(tmp_path / "args")})
    assert "rc=0" in r.stdout, r.stdout + r.stderr
    args = (tmp_path / "args").read_text()
    assert "-s danger-full-access" in args


# ---------- autenticación ----------

@pytest.mark.parametrize("salida", [
    "Not logged in · Please run /login",
    "Error: 401 Unauthorized",
    "Invalid API key provided",
    "Please set your API key",
    "run opencode auth login",
    "Authentication Error: invalid token",
    "HTTP 401 Unauthorized",
])
def test_sin_autenticacion_detecta_con_corroboracion(tmp_path, salida):
    """Patrones de ALTA CONFIANZA que SÍ deben detectarse CON corroboración=1 (iteración sin trabajo)."""
    texto = _leer_plantilla()
    (tmp_path / "func.sh").write_text(
        _extraer_funcion(texto, "sin_autenticacion"), encoding="utf-8")
    f_out = tmp_path / "salida.txt"
    f_err = tmp_path / "salida.err"
    f_out.write_text(salida, encoding="utf-8")
    f_err.write_text("", encoding="utf-8")
    r = subprocess.run(
        ["bash", "-c", '. "$1"; sin_autenticacion "$2" "$3" 1; echo rc=$?',
         "_", str(tmp_path / "func.sh"), str(f_err), str(f_out)],
        capture_output=True, text=True, timeout=15)
    assert "rc=0" in r.stdout, f"no detectado con corroboración: {salida}\n{r.stderr}"


def test_sin_autenticacion_no_falsa_positivo(tmp_path):
    """Casos que NO deben disparar (falsos positivos históricos)."""
    texto = _leer_plantilla()
    (tmp_path / "func.sh").write_text(
        _extraer_funcion(texto, "sin_autenticacion"), encoding="utf-8")
    falsos = [
        "Tarea completada. 3 archivos modificados.",
        "missing OPENAI_API_KEY en la configuración",  # mención narrativa
        "run 'codex login' to authenticate",          # mención en log/revisor
        "El error 401 apareció en el log",            # 401 suelto
        "unauthorized branch switch",                 # unauthorized suelto
        "Mi OPENAI_API_KEY es secreta",               # mención de API key
        "La respuesta fue 401 pero reintentó",        # 401 en narrativa
        "El log viejo tenía un 401 y una rama unauthorized",  # sueltos
    ]
    for salida in falsos:
        f_out = tmp_path / "salida.txt"
        f_err = tmp_path / "salida.err"
        f_out.write_text(salida, encoding="utf-8")
        f_err.write_text("", encoding="utf-8")
        r = subprocess.run(
            ["bash", "-c", '. "$1"; sin_autenticacion "$2" "$3" 0; echo rc=$?',
             "_", str(tmp_path / "func.sh"), str(f_err), str(f_out)],
            capture_output=True, text=True, timeout=15)
        assert "rc=1" in r.stdout, f"falso positivo: {salida}\n{r.stderr}"


def test_sin_autenticacion_exige_corroboracion_siempre(tmp_path):
    """Sin el 3er argumento la detección NO puede dispararse: el argumento es
    obligatorio y su ausencia equivale a 'sin corroborar'."""
    texto = _leer_plantilla()
    (tmp_path / "func.sh").write_text(
        _extraer_funcion(texto, "sin_autenticacion"), encoding="utf-8")
    f_out = tmp_path / "salida.txt"
    f_out.write_text("Error: 401 Unauthorized", encoding="utf-8")
    r = subprocess.run(
        ["bash", "-c", '. "$1"; sin_autenticacion "$2" "$2"; echo rc=$?',
         "_", str(tmp_path / "func.sh"), str(f_out)],
        capture_output=True, text=True, timeout=15)
    assert "rc=1" in r.stdout, r.stderr


# ---------- corroboración: ¿hubo trabajo en la iteración? ----------

def _harness_sin_trabajo(tmp_path, antes, despues):
    """Ejecuta iteracion_sin_trabajo() con dos listas BEFORE/AFTER."""
    texto = _leer_plantilla()
    (tmp_path / "func.sh").write_text(
        _extraer_funcion(texto, "iteracion_sin_trabajo"), encoding="utf-8")
    (tmp_path / "before").write_text("\n".join(antes) + "\n", encoding="utf-8")
    (tmp_path / "after").write_text("\n".join(despues) + "\n", encoding="utf-8")
    script = '. "$1"\nBEFORE="$2"\nAFTER="$3"\nCONTROL="' + _CONTROL + '"\n' \
             'if iteracion_sin_trabajo; then echo r=sin_trabajo; ' \
             'else echo r=con_trabajo; fi\n'
    (tmp_path / "run.sh").write_text(script, encoding="utf-8")
    return subprocess.run(
        ["bash", str(tmp_path / "run.sh"), str(tmp_path / "func.sh"),
         str(tmp_path / "before"), str(tmp_path / "after")],
        capture_output=True, text=True, timeout=15)


@pytest.mark.parametrize("nombre,antes,despues,esperado", [
    # Rama recién creada: árbol limpio, el agente no hizo nada.
    ("sin_cambios", [], [], "r=sin_trabajo"),
    # El loop escribe el log y las métricas en cada iteración: NO es trabajo.
    ("solo_control", [], ["progreso.log", "metrics.jsonl", "plan.md"],
     "r=sin_trabajo"),
    # Tracked ya presente en BEFORE que el agente Borra (desaparece del status).
    ("borrado_de_ya_modificado", ["app.py"], [], "r=con_trabajo"),
    ("tracked_modificado", [], ["app.py"], "r=con_trabajo"),
    ("tracked_borrado", [], ["viejo.py"], "r=con_trabajo"),
    ("untracked_nuevo", [], ["nuevo.py"], "r=con_trabajo"),
    ("control_y_trabajo", [], ["progreso.log", "app.py"], "r=con_trabajo"),
    ("cache_ignorado_por_snapshot", [], ["__pycache__/x.pyc"],
     "r=con_trabajo"),  # snapshot() ya lo habría filtrado
])
def test_iteracion_sin_trabajo(tmp_path, nombre, antes, despues, esperado):
    """La corroboración de auth depende de esto: sólo los archivos CONTROL
    (que escribe el propio loop) NO cuentan como trabajo del agente."""
    r = _harness_sin_trabajo(tmp_path, antes, despues)
    assert r.returncode == 0, r.stderr
    assert esperado in r.stdout, f"{nombre}: {r.stdout}{r.stderr}"


def _harness_auth(tmp_path, despues, salida, stderr):
    """Sin_autenticacion() alimentado por iteracion_sin_trabajo() real."""
    texto = _leer_plantilla()
    (tmp_path / "func.sh").write_text(
        "\n\n".join([
            _extraer_funcion(texto, "iteracion_sin_trabajo"),
            _extraer_funcion(texto, "sin_autenticacion"),
        ]), encoding="utf-8")
    (tmp_path / "before").write_text("", encoding="utf-8")
    (tmp_path / "after").write_text("\n".join(despues) + "\n", encoding="utf-8")
    (tmp_path / "salida.txt").write_text(salida, encoding="utf-8")
    (tmp_path / "salida.err").write_text(stderr, encoding="utf-8")
    return subprocess.run(
        ["bash", "-c",
         '. "$1"; BEFORE="$2"; AFTER="$3"; CONTROL="' + _CONTROL + '"; '
         'iter_sin_trabajo=0; iteracion_sin_trabajo && iter_sin_trabajo=1; '
         'sin_autenticacion "$4" "$5" "$iter_sin_trabajo"; echo rc=$?',
         "_", str(tmp_path / "func.sh"), str(tmp_path / "before"),
         str(tmp_path / "after"), str(tmp_path / "salida.err"),
         str(tmp_path / "salida.txt")],
        capture_output=True, text=True, timeout=15)


def test_auth_no_aborta_si_la_iteracion_tubo_trabajo(tmp_path):
    """Regresión: patrón de auth en la salida + cambios REALES del agente no
    debe abortar (el log puede mencionar 401 al describir lo que corrigió)."""
    r = _harness_auth(
        tmp_path, ["app.py"],
        "Arreglado el manejo de 401 Unauthorized en el cliente.", "")
    assert "rc=1" in r.stdout, (
        f"abortó pese a haber trabajo: {r.stdout}{r.stderr}")


def test_auth_aborta_aunque_solo_cambiara_el_log(tmp_path):
    """progreso.log/metrics SIEMPRE cambian, así que no pueden ser la prueba de
    trabajo: si NO hay ningún otro cambio, la iteración cuenta como sin trabajo
    y el patrón de auth (incluso en narrativa) confirma el fallo real."""
    r = _harness_auth(
        tmp_path, ["progreso.log", "metrics.jsonl"],
        "Found Authentication Error in the old log entry.",
        "warning: retrying after 401 Unauthorized")
    assert "rc=0" in r.stdout, (
        f"no abortó sin trabajo real: {r.stdout}{r.stderr}")


def test_auth_aborta_si_la_iteracion_no_tubo_trabajo(tmp_path):
    """El caso real: patrón de auth en stderr + árbol sin cambios → aborta."""
    r = _harness_auth(
        tmp_path, ["progreso.log"], "Tarea completada.",
        "Error: not logged in. Please run /login")
    assert "rc=0" in r.stdout, f"no abortó sin trabajo: {r.stdout}{r.stderr}"


# ---------- juez de criterio polivalente ----------

def _harness_juez(tmp_path, cuerpo, veredicto, extra_env=None):
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    _cli_falso(str(d), "claude", cuerpo)
    (tmp_path / "juez.sh").write_text(
        _leer_juez(), encoding="utf-8")
    env = {"PATH": f"{d}:/usr/bin:/bin", "HOME": str(tmp_path),
           "CRITERIO": "existe la función f()",
           "AGENTE_JUEZ": "claude",
           "CLI_CLAUDE": str(d / "claude"),
           "REG_ARGS": str(tmp_path / "args"),
           "TIMEOUT_JUEZ": "15"}
    env.update(extra_env or {})
    return subprocess.run(
        ["bash", str(tmp_path / "juez.sh")],
        capture_output=True, text=True, timeout=30, env=env), veredicto


def _leer_juez():
    with open(JUEZ, encoding="utf-8") as f:
        return f.read()


def test_juez_con_claude_acepta_veredicto(tmp_path):
    r, _ = _harness_juez(
        tmp_path,
        'echo \'{"met": true, "reason": "la función existe"}\'\n', True)
    assert r.returncode == 0, r.stderr
    assert "juez: agente=claude" in r.stdout
    assert "MODELO_JUEZ no aplica a claude" in r.stdout
    assert "criterio cumplido" in r.stdout
    args = (tmp_path / "args").read_text()
    assert "-p" in args
    assert "--model" not in args


def test_juez_con_claude_rechaza_veredicto(tmp_path):
    r, _ = _harness_juez(
        tmp_path,
        'echo \'{"met": false, "reason": "falta la función"}\'\n', False)
    assert r.returncode != 0, r.stdout
    assert "NO cumplido" in r.stdout


def test_juez_omitido_si_falla_el_cli(tmp_path):
    """El juez nunca bloquea: si el CLI falla, sale 0 con aviso."""
    r, _ = _harness_juez(tmp_path, "exit 3\n", None)
    assert r.returncode == 0, r.stdout
    assert "se omite" in r.stdout


def test_juez_auto_sigue_al_agente_de_tarea(tmp_path):
    r, _ = _harness_juez(
        tmp_path,
        'echo \'{"met": true, "reason": "ok"}\'\n', True,
        extra_env={"AGENTE_JUEZ": "auto", "AGENTE_TAREA": "claude"})
    assert "juez: agente=claude" in r.stdout


def test_juez_envia_agente_que_evalua(tmp_path):
    """El prompt del juez debe llegar al CLI con el criterio dentro."""
    r, _ = _harness_juez(
        tmp_path,
        'printf "%s\\n" "$*" > "$REG_ARGS"\n'
        'echo \'{"met": true, "reason": "ok"}\'\n', True)
    assert r.returncode == 0, r.stderr
    args = (tmp_path / "args").read_text()
    assert "JUEZ" in args
    assert "existe la función f()" in args


def test_juez_sin_agentes_omitido(tmp_path):
    """Sin ningún CLI disponible el juez se omite sin romper el gate."""
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    (tmp_path / "juez.sh").write_text(_leer_juez(), encoding="utf-8")
    r = subprocess.run(
        ["bash", str(tmp_path / "juez.sh")],
        capture_output=True, text=True, timeout=30,
        env={"PATH": f"{d}:/usr/bin:/bin", "HOME": str(tmp_path),
             "CRITERIO": "existe la función f()", "AGENTE_JUEZ": "claude",
             "CLI_CLAUDE": str(d / "no-existe")})
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no disponible" in r.stdout


def test_juez_sin_criterio_omitido(tmp_path):
    (tmp_path / "juez.sh").write_text(_leer_juez(), encoding="utf-8")
    r = subprocess.run(
        ["bash", str(tmp_path / "juez.sh")],
        capture_output=True, text=True, timeout=30,
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)})
    assert r.returncode == 0, r.stdout + r.stderr
    assert "sin CRITERIO" in r.stdout


def test_configuracion_expone_agentes_conocidos():
    from autopiloto_gui import configuracion as cfg

    assert "auto" in cfg.AGENTES_DISPONIBLES
    assert set(cfg.AGENTES_CONOCIDOS) == {"opencode", "codex", "claude"}
    assert cfg.AGENTE_DEFECTO == "auto"


def test_json_de_metrice_es_una_linea(tmp_path):
    """run_agente escribe metrics.jsonl con una línea JSON por llamada."""
    r = _harness_run_agente(tmp_path, 'echo "hecho"\n')
    assert r.returncode == 0, r.stderr
    metricas = tmp_path / "metrics.jsonl"
    lineas = [x for x in metricas.read_text().splitlines() if x.strip()]
    assert len(lineas) == 1
    reg = json.loads(lineas[0])
    assert reg["agente"] == "codex"
    assert reg["rc"] == 0
