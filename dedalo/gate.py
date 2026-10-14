#!/usr/bin/env python3
"""Orquestador portable del gate (port de gate.sh).

Ejecuta los checks de `gate_checks/` en orden numérico por prefijo y devuelve
0=OK, 1=FAIL, con el MISMO contrato de salida que gate.sh (`[GATE] ✓/✗`, y
`[GATE] ✅ TODO OK` final).

Regla de selección por prefijo:
  · Si existe `NN_*.sh` y hay bash -> se ejecuta con bash (comportamiento del
    gate de siempre; así un check .sh personalizado sigue ganando).
  · Si no hay bash (Windows sin Git Bash) -> se ejecuta `NN_*.py`, el port.

El bucle (loop.py) invoca esto con el mismo directorio de proyecto que antes:

    python -m dedalo.gate      # instalado / editable
    <exe> --dedalo-gate            # binario congelado (PyInstaller)
"""

import os
import re
import shutil
import subprocess
import sys

from . import gate_env


def _proteger_salidas():
    """Protege stdout/stderr ante codificaciones que no admiten emojis."""
    for nombre in ("stdout", "stderr"):
        try:
            st = getattr(sys, nombre, None)
            if st is None:
                setattr(sys, nombre, open(os.devnull, "w", encoding="utf-8", errors="replace"))
            elif hasattr(st, "reconfigure"):
                try:
                    st.reconfigure(encoding="utf-8", errors="replace")
                except (OSError, ValueError):
                    pass
        except Exception:
            pass


_PREFIJO = re.compile(r"^(\d+)_")


def argv_gate(frozen=None):
    """Comando (lista argv) para ejecutar el gate como subproceso.

    En el código fuente: `python -m dedalo.gate`. En el binario de
    PyInstaller `-m` no resuelve el módulo (va empaquetado en el exe), así que
    el entrypoint interpreta `--dedalo-gate`.
    """
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False))
    if frozen:
        return [sys.executable, "--dedalo-gate"]
    return [sys.executable, "-m", "dedalo.gate"]


def _grupos(proyecto):
    """Agrupa gate_checks por prefijo. None si no existe el directorio."""
    dir_checks = os.path.join(proyecto, "gate_checks")
    if not os.path.isdir(dir_checks):
        return None
    grupos = {}
    for nombre in sorted(os.listdir(dir_checks)):
        ruta = os.path.join(dir_checks, nombre)
        if nombre in ("_env.sh", "_env.py") or not os.path.isfile(ruta):
            continue
        base, ext = os.path.splitext(nombre)
        if ext not in (".sh", ".py") or not _PREFIJO.match(nombre):
            continue
        grupos.setdefault((int(_PREFIJO.match(nombre).group(1)), base), {})[ext] = ruta
    return grupos


def _cargar_py(ruta):
    """Carga un check .py sin escribir __pycache__ en el proyecto."""
    try:
        with open(ruta, encoding="utf-8") as f:
            codigo = f.read()
    except OSError:
        return None
    espacios = {"__name__": "gate_check_" + os.path.basename(ruta), "__file__": ruta}
    exec(compile(codigo, ruta, "exec"), espacios)
    return espacios.get("run")


def _correr_py(check, entorno):
    funcion = _cargar_py(check)
    if funcion is None:
        print(f"[GATE] ⚠ {os.path.basename(check)}: sin función run(), se omite")
        return 0
    try:
        resultado = funcion(entorno)
    except SystemExit as e:
        return int(e.code or 0)
    except Exception as e:  # noqa: BLE001
        print(f"[GATE] ✗ {os.path.basename(check)}: {e}")
        return 1
    if resultado is None:
        return 0
    if isinstance(resultado, bool):
        return 0 if resultado else 1
    return int(resultado)


def _correr_sh(proyecto, check, bash):
    """Corre un check .sh con bash, sourceando _env.sh primero (como gate.sh)."""
    env_sh = os.path.join(proyecto, "gate_checks", "_env.sh")
    partes = []
    if os.path.isfile(env_sh):
        partes.append(f'source "{env_sh}"')
    else:
        partes.append(f'PROYECTO="{proyecto}"')
        partes.append('fail() { echo "[GATE] ✗ $1"; exit 1; }')
        partes.append('ok()   { echo "[GATE] ✓ $1"; }')
    partes.append(f'source "{check}"')
    guion = "\n".join(partes)
    try:
        p = subprocess.run(
            [bash, "-c", guion], cwd=proyecto, capture_output=True, text=True)
    except OSError:
        return 127
    # Reemitimos por stdout/stderr de Python para conservar el ORDEN del log:
    # si el subproceso escribiera directo al fd, su salida podría adelantarse
    # al buffer de Python (y al "[GATE] ✅ TODO OK" final).
    sys.stdout.write(p.stdout or "")
    if p.stderr:
        sys.stderr.write(p.stderr)
    sys.stdout.flush()
    return p.returncode


def correr(proyecto, bash=None):
    """Ejecuta el gate del proyecto. Devuelve 0=OK, 1=FAIL."""
    _proteger_salidas()
    if bash is None:
        bash = shutil.which("bash")
    grupos = _grupos(proyecto)
    if grupos is None:
        print(f"[GATE] ⚠ No existe {os.path.join(proyecto, 'gate_checks')} — "
              "se asume OK")
        return 0
    if not grupos:
        print("[GATE] ⚠ Sin checks — se asume OK")
        return 0
    entorno = None
    for clave in sorted(grupos):
        grupo = grupos[clave]
        usado = grupo.get(".sh") or grupo.get(".py")
        if ".sh" in grupo and bash:
            usado = grupo[".sh"]
            rc = _correr_sh(proyecto, usado, bash)
        elif ".py" in grupo:
            if entorno is None:
                entorno = gate_env.detectar(proyecto)
            usado = grupo[".py"]
            rc = _correr_py(usado, entorno)
        else:
            print(f"[GATE] ⚠ {os.path.basename(usado)}: no hay bash ni .py, "
                  "se omite")
            rc = 0
        if rc != 0:
            print(f"[GATE] ✗ Check falló: {os.path.basename(usado)}")
            return rc if rc > 0 else 1
    print()
    print("[GATE] ✅ TODO OK")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        sys.dont_write_bytecode = True
    except Exception:
        pass
    proyecto = os.getcwd()
    i = 0
    while i < len(argv):
        if argv[i] in ("--proyecto", "-p") and i + 1 < len(argv):
            proyecto = argv[i + 1]
            i += 2
        elif not argv[i].startswith("-"):
            proyecto = argv[i]
            i += 1
        else:
            i += 1
    return correr(proyecto)


if __name__ == "__main__":
    sys.exit(main())
