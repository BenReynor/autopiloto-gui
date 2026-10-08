#!/usr/bin/env python3
"""Control de subprocesos del loop nativo.

Port de `_timeout`/`_matar_hijo`/`limpiar_sesiones` de autopiloto.sh:
ejecución con tope de tiempo y muerte de todo el GRUPO de procesos (el hijo
directo suele ser `timeout` y el agente cuelga de él; sólo funciona si se
mata el grupo). En Python no hace falta el fichero de PID intermedio: el
Popen guarda el proceso y la limpieza vive en el motor; se mantiene el
mismo sentinel `124` de GNU timeout para que el bucle reconozca el corte.
"""

import json
import os
import signal
import subprocess
import time

_POSIX = os.name == "posix"

RC_TIMEOUT = 124  # mismo sentinel que GNU timeout / _timeout del script


def _golpe_grupo(proc, espera=5):
    """SIGTERM al grupo del proceso; si sigue vivo a los `espera`s, SIGKILL."""
    def _kill(sig):
        if _POSIX:
            try:
                os.killpg(proc.pid, sig)
                return
            except (ProcessLookupError, PermissionError):
                return
        try:
            proc.kill()
        except OSError:
            pass

    _kill(signal.SIGTERM)
    for _ in range(espera):
        if proc.poll() is not None:
            return
        time.sleep(1)
    if proc.poll() is None:
        _kill(signal.SIGKILL)


def run_con_timeout(cmd, timeout, *, env=None, cwd=None,
                    stdout=None, stderr=None):
    """Ejecuta `cmd` con tope de `timeout` segundos.

    Devuelve `(returncode, salida, timed_out)`:
      · timed_out True si excedió el tope → returncode = RC_TIMEOUT (124) y
        el grupo entero fue TERM→KILL, como hace `_timeout` del script.
      · `salida` = (stdout_bytes, stderr_bytes); si `stdout`/`stderr` son
        ficheros o None, devuelve None en esa posición (como communicate).
      · Empieza el hijo en su PROPIA sesión/grupo (start_new_session), de
        modo que `killpg(pid)` se lleva también al agente colgando de él.
    """
    kwargs = dict(env=env, cwd=cwd, stdout=stdout, stderr=stderr)
    if _POSIX:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(cmd, **kwargs)
    timed_out = False
    try:
        try:
            salida = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _golpe_grupo(proc)
            salida = proc.communicate()
    finally:
        if proc.poll() is None:
            _golpe_grupo(proc, espera=0)
    rc = RC_TIMEOUT if timed_out else proc.returncode
    return rc, salida, timed_out


def limpiar_sesiones(binario, proyecto, desde_ms, log, log_resultado=None):
    """Borra las sesiones de opencode creadas por este run en `proyecto`.

    Port de `limpiar_sesiones()` del script con el mismo criterio
    (directory == proyecto y created >= desde_ms), pero SIN dependencia de
    `jq` (se parsea el JSON con la stdlib). Cada llamada a la CLI va con un
    tope de 20 s: esta función está en el camino de parada y no puede
    colgarse. Devuelve el número de sesiones borradas.
    """
    if not binario or not os.path.exists(binario):
        return 0

    def _session_list():
        rc, salida, _t = run_con_timeout(
            [binario, "session", "list", "--format", "json"], 20,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if rc != 0 and not salida[0]:
            return []
        try:
            datos = json.loads(salida[0].decode("utf-8", "replace") or "[]")
        except ValueError:
            return []
        if not isinstance(datos, list):
            return []
        return datos

    borradas = 0
    for sesion in _session_list():
        if not isinstance(sesion, dict):
            continue
        if (sesion.get("directory") == str(proyecto)
                and sesion.get("created", 0) >= desde_ms):
            sid = sesion.get("id")
            if not sid:
                continue
            run_con_timeout([binario, "session", "delete", str(sid)], 20,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
            borradas += 1
    if borradas and log:
        mensaje = (
            f"[autopiloto] Sesiones opencode eliminadas: {borradas}"
        )
        if log_resultado is not None:
            log_resultado(mensaje)
        else:
            try:
                with open(log, "a", encoding="utf-8") as f:
                    f.write(mensaje + "\n")
            except OSError:
                pass
    return borradas
