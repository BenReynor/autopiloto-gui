#!/usr/bin/env python3
"""Tests del timeout de la revisión manual de dedalo.sh.

Extrae `esperar_revision_manual` de la plantilla y la ejecuta con stubs de
red/sleep para verificar: aprobación (rc=0), timeout (rc=2) y caída de red
(rc=4). En todos los casos el estado `waiting`/`decision` debe quedar limpio.
"""

import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLANTILLA = os.path.join(
    RAIZ, "dedalo", "plantillas_data", "dedalo.sh")

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or os.name == "nt",
    reason="harness POSIX (agent falsos en bash): se valida en Linux")


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


def _harness(tmp_path):
    with open(PLANTILLA, encoding="utf-8") as f:
        contenido = f.read()
    (tmp_path / "func.sh").write_text(
        _extraer_funcion(contenido, "esperar_revision_manual"),
        encoding="utf-8")

    script = r'''
. "$1"
run_case() {
    name="$1"; tmo="$2"; inet_rc="$3"; pre="$4"
    dir="$(mktemp -d)"
    REVISION_MANUAL=1
    TIMEOUT_REVISION_MANUAL="$tmo"
    PROYECTO="$dir"
    TAREA="t"
    LOG="$dir/log"
    mkdir -p "$dir/.dedalo_review"
    : > "$LOG"
    logx() { :; }
    alerta() { :; }
    hay_internet() { return "$inet_rc"; }
    sleep() { :; }
    git() { return 0; }
    [ -n "$pre" ] && printf '%s' "$pre" > "$dir/.dedalo_review/decision"
    ( esperar_revision_manual )
    rc=$?
    leftover="limpio"
    [ -e "$dir/.dedalo_review/waiting" ] && leftover="waiting"
    echo "CASE $name rc=$rc $leftover"
    rm -rf "$dir"
}
run_case timeout 4 0 ""
run_case approve 4 0 "APPROVE"
run_case nonet 0 1 ""
'''
    (tmp_path / "run.sh").write_text(script, encoding="utf-8")
    return subprocess.run(
        ["bash", str(tmp_path / "run.sh"), str(tmp_path / "func.sh")],
        capture_output=True, text=True, timeout=30)


def test_timeout_aprobacion_y_sin_red(tmp_path):
    r = _harness(tmp_path)
    assert r.returncode == 0, r.stderr
    assert "CASE timeout rc=2 limpio" in r.stdout
    assert "CASE approve rc=0 limpio" in r.stdout
    assert "CASE nonet rc=4 limpio" in r.stdout
