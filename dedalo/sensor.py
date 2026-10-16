"""Reading the CPU temperature (Linux) for thermal protection."""

import glob
import re
import shutil
import subprocess
import time

from . import configuracion as cfg

LIMITE_SUPERIOR = 150
LIMITE_INFERIOR = 5

# The GUI calls leer_temperatura() every second; we cache the result
# for a few seconds so we don't launch `sensors` on every tick.
_CACHE_SEG = 2
_cache = (0.0, None)


def _cachear(valor):
    global _cache
    _cache = (time.monotonic(), valor)


def _zonas_termicas():
    valores = []
    for path in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
        try:
            with open(path, encoding="utf-8") as f:
                raw = int(f.read().strip())
        except (ValueError, OSError):
            continue
        grados = raw / 1000.0
        if LIMITE_INFERIOR <= grados <= LIMITE_SUPERIOR:
            valores.append(grados)
    return valores


def _sensors():
    if not shutil.which("sensors"):
        return []
    try:
        out = subprocess.run(["sensors", "-u"], capture_output=True,
                             text=True, timeout=cfg.TIMEOUT_SENSORES)
    except (OSError, subprocess.TimeoutExpired):
        return []
    valores = []
    for m in re.finditer(r"temp\d+_input:\s*([\d.]+)", out.stdout):
        try:
            grados = float(m.group(1))
        except ValueError:
            continue
        if LIMITE_INFERIOR <= grados <= LIMITE_SUPERIOR:
            valores.append(grados)
    return valores


def leer_temperatura():
    """Returns the maximum temperature (in °C) or None if it cannot be read."""
    momento, valor = _cache
    if time.monotonic() - momento < _CACHE_SEG:
        return valor
    todas = _zonas_termicas() + _sensors()
    _cachear(max(todas) if todas else None)
    return _cache[1]
