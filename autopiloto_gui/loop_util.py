#!/usr/bin/env python3
"""Utilidades del loop nativo (port de la sección de utilidades de
autopiloto.sh). El bucle vive hoy en plantillas_data/autopiloto.sh; estos
helpers son la base del motor Python (autopiloto_gui.loop) que lo sustituirá.
Mismo contrato de formato del log para que la GUI lo consuma igual.

Sin dependencias de PySide: el motor corre como subproceso de la GUI (y
también a mano con `python -m autopiloto_gui.loop`).
"""

import subprocess
import time
from decimal import ROUND_HALF_UP, Decimal


def hora_texto():
    """Hora local como "HH:MM" (`date +%H:%M`)."""
    return time.strftime("%H:%M")


def hora_limite(hasta):
    """True si ya pasó la hora límite (semántica string del script bash).

    autopiloto.sh hace `[[ "$(date +%H:%M)" > "$HASTA" ]]`, que es una
    comparación LEXICOGRÁFICA: funciona como reloj porque "HH:MM" va
    acolchado a dos dígitos. Mantenemos la misma comparación para que el
    motor Python y el bash se comporten idéntico (hasta un valor raro como
    "9:00" se compara igual en ambos).
    """
    if not hasta:
        return False
    return hora_texto() > str(hasta)


def ahora_ms():
    """Epoch en milisegundos (versión portable de `date +%s%3N`)."""
    return int(time.time() * 1000)


def logx(log, mensaje):
    """Append a `log` con timestamp local, formato del script:
    `[YYYY-MM-DD HH:MM:SS] <mensaje>`."""
    with open(log, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {mensaje}\n")


def alerta(voz, mensaje):
    """Aviso de escritorio si VOZ=1 (notify-send + spd-say), sin romper nada
    si faltan (igual que alerta() del script)."""
    if str(voz) != "1":
        return
    for cmd in (("notify-send", "Autopiloto", mensaje),
                ("spd-say", f"Autopiloto: {mensaje}")):
        try:
            subprocess.run(cmd, capture_output=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            pass


def _dec(valor):
    """Decimal desde str/float/int con exactitud decimal (para costes)."""
    if isinstance(valor, Decimal):
        return valor
    if valor in (None, ""):
        return Decimal(0)
    return Decimal(str(valor))


def d2(valor):
    """Formatea un valor como moneda `%.2f` (redondeo mitad-arriba).

    Equivale al contrato de `num awk 'printf "%.2f"'` del script (awk
    redondea 12.345 -> 12.35, 0.005 -> 0.01)."""
    return format(_dec(valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                  ".2f")


def suma_coste(actual, por_iter):
    """`actual + por_iter` con dos decimales; equivale a la línea
    `COSTO_TOTAL=num ... printf "%.2f"` de autopiloto.sh."""
    return d2(_dec(actual) + _dec(por_iter))
