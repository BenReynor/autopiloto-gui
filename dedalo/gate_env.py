"""Detección de entorno para el gate portátil (equivalente a _env.sh).

Este módulo lo usa `gate.py` (el orquestador portable) para preparar las
variables y utilidades que comparten los checks `.py`, sobre todo en Windows,
donde no hay bash para los `gate_checks/*.sh`.

Es un port fiel de `plantillas_data/gate_checks/_env.sh`: mismas variables,
misma detección (Backend/, frontend/, venv, Django, comandos de DB/migraciones/
tests/backend) y mismas prioridades. La diferencia está en cómo se ejecutan
los comandos: los defaults van como listas (argv, sin shell) y sólo lo que
sobreescribe el usuario por entorno se ejecuta con shell.
"""

import os
import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class Comando:
    """Un comando a ejecutar: argv (lista) o shell (cadena), y su cwd."""

    argv: list | None = None
    shell: "str | None" = None
    cwd: "str | None" = None


@dataclass
class Entorno:
    """Variables y utilidades compartidas por los checks `.py`."""

    proyecto: str
    backend_dir: str
    frontend_dir: str
    py_backend: str
    py_frontend: str
    db_check: "Comando | None"
    migrate_check: "Comando | None"
    test_cmd: "Comando | None"
    serve_cmd: "Comando | None"
    serve_url: str
    token_url: str
    usuario: str
    clave: str
    endpoints: list

    def ok(self, mensaje):
        print(f"[GATE] \u2713 {mensaje}")

    def fail(self, mensaje):
        print(f"[GATE] \u2717 {mensaje}")

    def aviso(self, mensaje):
        print(f"[GATE] \u26a0 {mensaje}")

    def ejecutar(self, cmd, timeout=None):
        """Corre el comando y devuelve el código de retorno (0 si es None)."""
        return self.ejecutar_salida(cmd, timeout=timeout)[0]

    def ejecutar_salida(self, cmd, timeout=None):
        """Corre el comando y devuelve (rc, salida combinada stdout+stderr)."""
        if cmd is None:
            return 0, ""
        if cmd.shell is not None:
            args, usar_shell = cmd.shell, True
        else:
            args, usar_shell = cmd.argv, False
        try:
            p = subprocess.run(
                args, shell=usar_shell, cwd=cmd.cwd or self.proyecto,
                capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return 124, ""
        except OSError as e:
            return 127, str(e)
        return p.returncode, (p.stdout or "") + (p.stderr or "")

    def lanzar(self, cmd):
        """Arranca el comando en segundo plano. Devuelve el Popen o None."""
        if cmd is None:
            return None
        if cmd.shell is not None:
            return subprocess.Popen(
                cmd.shell, shell=True, cwd=cmd.cwd or self.proyecto,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return subprocess.Popen(
            cmd.argv, cwd=cmd.cwd or self.proyecto,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _comando(valor, cwd):
    """Comando del usuario (str -> shell) o por defecto (lista -> argv)."""
    if not valor:
        return None
    if isinstance(valor, str):
        return Comando(shell=valor, cwd=cwd)
    return Comando(argv=list(valor), cwd=cwd)


def _db_por_defecto():
    """DB_CHECK por defecto para Django (port del default de _env.sh).

    Mismo one-liner que el script: sólo comprueba pg_isready, y se ejecuta con
    shell (igual que el resto de defaults que sobreescribe el usuario)."""
    return "command -v pg_isready >/dev/null 2>&1 && pg_isready -q"


def detectar(proyecto, environ=None):
    """Port de _env.sh: devuelve un Entorno con la detección resuelta."""
    env = environ if environ is not None else os.environ
    proyecto = os.path.abspath(proyecto)

    backend = env.get("BACKEND_DIR", "")
    if not backend and os.path.isdir(os.path.join(proyecto, "Backend")):
        backend = os.path.join(proyecto, "Backend")
    if not backend:
        backend = proyecto

    frontend = env.get("FRONTEND_DIR", "")
    if not frontend and os.path.isdir(os.path.join(proyecto, "frontend")):
        frontend = os.path.join(proyecto, "frontend")

    py_backend = env.get("PY_BACKEND", "")
    if not py_backend:
        py_backend = _python_de(proyecto) or _python_de(backend) or _python3()

    py_frontend = env.get("PY_FRONTEND", "") or _python_de(frontend) or py_backend

    db_check = env.get("DB_CHECK_CMD", "")
    migrate = env.get("MIGRATE_CHECK", "")
    test = env.get("TEST_CMD", "")
    serve = env.get("SERVE_CMD", "")
    serve_url = env.get("SERVE_URL", "")
    token_url = env.get("TOKEN_URL", "")
    usuario = env.get("USUARIO", "")
    clave = env.get("CLAVE", "")
    endpoints = env.get("ENDPOINTS", "")

    if py_backend and os.path.isfile(os.path.join(backend, "manage.py")):
        migrate = migrate or [py_backend, "manage.py", "migrate", "--check"]
        test = test or [py_backend, "-m", "pytest", "-q"]
        db_check = db_check or _db_por_defecto()
        if not serve and not endpoints:
            serve = [py_backend, "manage.py", "runserver", "8000", "--noreload"]
            serve_url = serve_url or "http://localhost:8000"
            token_url = token_url or "http://localhost:8000/api/token/"
            usuario = usuario or "admin"
            clave = clave or "admin123"
            endpoints = endpoints or (
                "productos/productos/ ventas/clientes/ usuarios/usuarios/ "
                "caja/caja/ kardex/movimientos/ compras/compras/ "
                "config/config/")
    elif py_backend:
        test = test or [py_backend, "-m", "pytest", "-q"]

    return Entorno(
        proyecto=proyecto,
        backend_dir=backend,
        frontend_dir=frontend,
        py_backend=py_backend,
        py_frontend=py_frontend,
        db_check=_comando(db_check, backend),
        migrate_check=_comando(migrate, backend),
        test_cmd=_comando(test, backend),
        serve_cmd=_comando(serve, backend),
        serve_url=serve_url,
        token_url=token_url,
        usuario=usuario,
        clave=clave,
        endpoints=_endpoints(proyecto, endpoints),
    )


def _python3():
    return "python3" if shutil.which("python3") else "python"


def _python_de(base):
    """Intérprete Python de un venv dentro de `base` (o "")."""
    if not base:
        return ""
    for nombre in ("venv", ".venv"):
        for sub in ("bin/python", "Scripts/python.exe"):
            ruta = os.path.join(base, nombre, *sub.split("/"))
            if os.path.isfile(ruta):
                return ruta
    return ""


def _endpoints(proyecto, endpoints):
    """endpoints.txt de la raíz manda; si no, la lista ENDPOINTS."""
    ruta = os.path.join(proyecto, "endpoints.txt")
    if os.path.isfile(ruta):
        with open(ruta, encoding="utf-8", errors="replace") as f:
            lineas = f.read().splitlines()
        return [linea.strip() for linea in lineas if linea.strip()]
    return endpoints.split() if endpoints else []

