# 04_imports.py — Checks that the frontend/python imports without errors.
# Port of 04_imports.sh for the portable orchestrator (Windows without bash).
# Override with TEST_CMD or FRONTEND_DIR. If there is no frontend, it is skipped.
import os
import subprocess

_CODIGO = (
    "import sys\n"
    "sys.path.insert(0, '.')\n"
    "try:\n"
    "    from main import POSApplication\n"
    "except ImportError:\n"
    "    pass\n"
)


def run(env):
    if not env.frontend_dir or not os.path.isdir(env.frontend_dir):
        env.aviso("FRONTEND_DIR no configurado o sin frontend, se omite")
        return 0

    try:
        p = subprocess.run(
            [env.py_frontend, "-c", _CODIGO], cwd=env.frontend_dir,
            capture_output=True, text=True)
    except OSError:
        p = None
    if p is not None and p.returncode == 0:
        env.ok("imports frontend")
        return 0
    env.fail("imports frontend")
    return 1
