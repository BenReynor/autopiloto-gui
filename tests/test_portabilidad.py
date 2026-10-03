"""Lint de portabilidad de las plantillas shell.

Las plantillas se copian a proyectos de otros usuarios, que pueden estar en
macOS o Windows (WSL/Git Bash). Las construcciones exclusivas de GNU fallan
allí de forma silenciosa o con errores confusos, así que se prohíben aquí.

Este fichero no sustituye a probar en la máquina real: sólo evita reintroducir
construcciones que ya sabemos incompatibles.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SH_DIRS = [RAIZ / "autopiloto_gui", RAIZ]
_IGNORAR = {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache",
            "venv", ".venv", "__pycache__", "node_modules"}

# (regex, motivo, funciones donde el uso es legítimo)
PROHIBIDOS: list[tuple[str, str, tuple[str, ...]]] = [
    # GNU %N no existe en el date de BSD: devuelve el literal "%3N" y rompe
    # la aritmética de duraciones. Sólo se permite dentro de ahora_ms(), que
    # detecta la salida no numérica y degrada a perl/segundos.
    (r"date \+%s%3N", "date %3N es GNU; usa ahora_ms()", ("ahora_ms",)),
    (r"head\s+-n\s+-\d", "head -n negativo no existe en BSD", ()),
    (r"\bseq\s+\d", "seq no existe en BSD/macOS; usa while", ()),
    (r"find .*?-printf", "find -printf es sólo GNU", ()),
    (r"sed .*\\s", r"sed POSIX no reconoce \s; usa [[:space:]]", ()),
    (r"\$\{[A-Za-z_][A-Za-z_0-9]*\^\^?\}", "expansión ^ es bash 4+; usa tr", ()),
    (r"\$\{[A-Za-z_][A-Za-z_0-9]*,[^}]*\}", "expansión {a,b} es bash 4+", ()),
    (r"readarray|mapfile", "readarray/mapfile son bash 4+", ()),
]


def _bloques_permitidos(lineas: list[str]) -> set[int]:
    """Números de línea que están dentro de una función con excepción."""
    permitidos: set[int] = set()
    abierta = ""
    for n, linea in enumerate(lineas, 1):
        if not abierta:
            m = re.match(r"^([a-z_][a-z_0-9]*)\s*\(\)\s*\{", linea)
            if m and m.group(1) in {
                f for _, _, fs in PROHIBIDOS for f in fs
            }:
                abierta = m.group(1)
            continue
        permitidos.add(n)
        if linea.strip() == "}":
            abierta = ""
    return permitidos


def _scripts() -> list[Path]:
    """Todos los .sh del repo: plantillas, gate_checks y lanzadores."""
    out: set[Path] = set()
    for base in SH_DIRS:
        for p in base.rglob("*.sh"):
            if not any(parte in _IGNORAR for parte in p.parts):
                out.add(p.resolve())
    return sorted(out)


def test_hay_plantillas_que_analizar():
    assert len(_scripts()) >= 8


@pytest.mark.parametrize("path", _scripts(), ids=lambda p: p.name)
def test_sin_crlf(path: Path):
    """Con CRLF el shebang `#!/usr/bin/env bash` se rompe (`bash\\r`)."""
    crudo = path.read_bytes()
    assert b"\r\n" not in crudo, f"{path.name} tiene finales de línea CRLF"


@pytest.mark.parametrize("path", _scripts(), ids=lambda p: p.name)
def test_sin_construcciones_gnu(path: Path):
    """Falla si aparece una construcción exclusiva de GNU/BSD-rotas."""
    lineas = path.read_text(encoding="utf-8").splitlines()
    permitidos = _bloques_permitidos(lineas)
    offenders = []
    for n, linea in enumerate(lineas, 1):
        if linea.lstrip().startswith("#") or n in permitidos:
            continue
        for patron, motivo, _ in PROHIBIDOS:
            if re.search(patron, linea):
                offenders.append(f"{path.name}:{n}  {motivo}\n    {linea.strip()}")
    assert not offenders, "Construcciones no portables:\n" + "\n".join(offenders)


@pytest.mark.parametrize("path", _scripts(), ids=lambda p: p.name)
def test_sintaxis_bash(path: Path):
    r = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
    assert r.returncode == 0, f"{path.name}: {r.stderr.strip()}"


@pytest.mark.parametrize("path", _scripts(), ids=lambda p: p.name)
def test_ejecutable(path: Path):
    """Las plantillas que se lanzan con `bash x.sh` no lo necesitan, pero las
    que van en el PATH del proyecto destino sí."""
    if path.name in {"_env.sh", "98_criterio.sh"}:
        pytest.skip("se sourcean/ejecutan con bash explícito")
    assert path.stat().st_mode & 0o111, f"{path.name} no tiene permiso +x"


# ---------------------------------------------------------------------------
# Pendientes conocidos: bloquean macOS/Windows y aún NO están resueltos.
# Si desaparecen, bórralos de aquí (el lint de arriba impide que vuelvan).
# ---------------------------------------------------------------------------
PENDIENTES_MACOS = {
    "timeout": "`timeout` no viene en macOS ni en Windows nativo (autopiloto.sh, 98_criterio.sh)",
    'sed -i "0,/': "`sed -i 0,/x/` es extensión GNU: el marcado [x]/[B] del plan no se aplica en BSD",
}
PENDIENTES_WINDOWS = {
    "bash": "las plantillas son bash: en Windows hace falta WSL2 o Git Bash",
    "QProcess(\"bash\")": "la GUI lanza `bash`: en Windows requiere bash.exe en el PATH",
    "os.pathsep": "la GUI concatena el PATH con ':' en vez de os.pathsep (';' en Windows)",
}


def test_pendientes_documentados_no_ocultan_nada_nuevo():
    """Guardarraíl: la allowlist de pendientes debe existir y ser explícita,
    para que quede a la vista lo que aún impide macOS/Windows."""
    assert set(PENDIENTES_MACOS) == {"timeout", 'sed -i "0,/'}
    assert set(PENDIENTES_WINDOWS) == {
        "bash", 'QProcess("bash")', "os.pathsep"}
    # `timeout` y `sed -i 0,/` están permitidos a propósito: NO deben estar
    # en PROHIBIDOS hasta que se resuelvan.
    prohibidos = " | ".join(p for p, _, _ in PROHIBIDOS)
    assert "timeout" not in prohibidos
    assert r"sed -i \"0,/" not in prohibidos


def test_gitattributes_fuerza_lf_para_sh():
    """Sin esto, un `git clone` en Windows con autocrlf rompe todos los .sh."""
    ga = RAIZ / ".gitattributes"
    assert ga.is_file(), "falta .gitattributes"
    texto = ga.read_text(encoding="utf-8")
    assert re.search(r"^\*\.sh\s+text\s+eol=lf$", texto, re.M), (
        ".gitattributes debe fijar `*.sh text eol=lf`")


# ---------------------------------------------------------------------------
# Formatos que no deben depender del locale del usuario
# ---------------------------------------------------------------------------

_AUTOPILOTO = RAIZ / "autopiloto_gui" / "plantillas_data" / "autopiloto.sh"


def test_awk_de_formatos_usa_locale_c():
    """Con un locale español, `awk 'BEGIN{printf "%.6f", x}'` da "0,500000".

    Esa coma decimal escribía metrics.jsonl como JSON INVÁLIDO y rompía la
    comparación del tope de coste. OJO: `export LC_NUMERIC=C` NO lo arregla,
    porque LC_ALL tiene prioridad sobre LC_NUMERIC en los procesos hijos.
    """
    texto = _AUTOPILOTO.read_text(encoding="utf-8")
    assert re.search(r"^num\(\)\s*\{\s*LC_ALL=C awk", texto, re.M), (
        "autopiloto.sh debe definir num() con LC_ALL=C awk")
    # Ningún awk que formatee un decimal puede quedar fuera del helper.
    sueltos = [n for n, linea in enumerate(texto.splitlines(), 1)
               if re.search(r"(?<![\w-])awk .*printf \"%", linea)
               and not linea.lstrip().startswith("#")]
    assert not sueltos, f"awk sin locale C en las líneas {sueltos}"


def test_exporta_lc_all_c_para_el_printf_de_bash():
    """El otro lado del bug: el `printf "%.6f"` del propio bash usa el locale
    del shell y rechazaba "0.500000" como número no válido."""
    texto = _AUTOPILOTO.read_text(encoding="utf-8")
    m = re.search(r"^export LC_ALL=C$", texto, re.M)
    assert m, "autopiloto.sh debe hacer `export LC_ALL=C`"
    assert m.start() < texto.index("costo=$(num"), (
        "el export debe ir antes de calcular el coste")


def test_registrar_metrica_escribe_json_valido(tmp_path):
    """Ejecuta la función real de la plantilla bajo LC_ALL=es_ES."""
    if "es_es" not in subprocess.run(["locale", "-a"], capture_output=True,
                                     text=True).stdout.lower():
        pytest.skip("el runner no tiene locale es_ES; el test A ya lo cubre")

    texto = _AUTOPILOTO.read_text(encoding="utf-8")
    ini = texto.index("_registrar_metrica() {")
    funcion = texto[ini:texto.index("\n}", ini) + 2]

    salida = tmp_path / "salida.txt"
    salida.write_text("")
    prog = "\n".join([
        "set -uo pipefail",
        "export LC_ALL=C",              # el export, tal cual en la plantilla
        'num() { LC_ALL=C awk "$@"; }',  # y el helper, por si se sourcea
        f'PROYECTO="{tmp_path}"',
        "iter=1",
        'TAREA="#1 prueba"',
        funcion,
        f'_registrar_metrica opencode opencode/big-pickle 1234 0 "{salida}"',
    ])
    r = subprocess.run(["bash", "-c", prog], capture_output=True, text=True,
                       env={"LC_ALL": "es_ES.UTF-8", "PATH": os.environ["PATH"]})
    assert r.returncode == 0, r.stderr

    lineas = [x for x in (tmp_path / "metrics.jsonl").read_text().splitlines() if x.strip()]
    assert len(lineas) == 1, lineas
    # Si el locale rompe el decimal, esto lanza JSONDecodeError.
    dato = json.loads(lineas[0])
    assert dato["costo_usd"] == 0.0
    assert dato["dur_ms"] == 1234
    # "0,500000" dentro del número (no una coma separadora de campos).
    assert not re.search(r'":\d+,\d+', lineas[0]), (
        f"coma decimal dentro de un número del JSON: {lineas[0]}")


def test_registrar_metrica_falla_sin_lc_all_c(tmp_path):
    """Contraprueba: sin el export, la MISMA función revienta en es_ES.

    Si este test dejara de fallar, el bug original habría vuelto (o el locale
    del runner ha cambiado y los tests de arriba pasarían por casualidad).
    """
    if "es_es" not in subprocess.run(["locale", "-a"], capture_output=True,
                                     text=True).stdout.lower():
        pytest.skip("el runner no tiene locale es_ES")

    texto = _AUTOPILOTO.read_text(encoding="utf-8")
    ini = texto.index("_registrar_metrica() {")
    funcion = texto[ini:texto.index("\n}", ini) + 2]

    salida = tmp_path / "salida.txt"
    salida.write_text("")
    prog = "\n".join([
        "set -uo pipefail",
        'num() { LC_ALL=C awk "$@"; }',
        f'PROYECTO="{tmp_path}"',
        "iter=1",
        'TAREA="#1 prueba"',
        funcion,
        f'_registrar_metrica opencode opencode/big-pickle 1234 0 "{salida}"',
    ])
    r = subprocess.run(["bash", "-c", prog], capture_output=True, text=True,
                       env={"LC_ALL": "es_ES.UTF-8", "PATH": os.environ["PATH"]})
    # Sin `export LC_ALL=C`, el printf de bash no reconoce el decimal con punto.
    assert r.returncode != 0, (
        "el printf de bash aceptó el punto: revisa que el locale de es_ES "
        "siga.teniendo coma decimal")
