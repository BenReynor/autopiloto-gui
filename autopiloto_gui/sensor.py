"""Lectura de la temperatura de la CPU (Linux) para la protección térmica."""

import glob
import re
import shutil
import subprocess

LIMITE_SUPERIOR = 150
LIMITE_INFERIOR = 5


def _zonas_termicas():
    valores = []
    for path in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
        try:
            with open(path, "r", encoding="utf-8") as f:
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
                             text=True, timeout=5)
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
    """Devuelve la temperatura máxima (en °C) o None si no se puede leer."""
    todas = _zonas_termicas() + _sensors()
    if not todas:
        return None
    return max(todas)