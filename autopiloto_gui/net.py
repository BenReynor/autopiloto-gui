"""Comprobación de conectividad a internet.

Los modelos IA de opencode requieren red; si se cae no tiene sentido lanzar
tareas. La verificación real se hace en un hilo de fondo: la GUI siempre lee
el estado cacheado (sin bloquear) y `verificar_async()` refresca en segundo
plano.
"""

import socket
import threading

from . import configuracion as cfg

HOSTS = ("1.1.1.1", "8.8.8.8")

_estado = None          # True/False, último resultado conocido
_verificando = False


def _probar():
    for host in HOSTS:
        try:
            socket.create_connection(
                (host, 53), timeout=cfg.TIMEOUT_INTERNET).close()
            return True
        except OSError:
            continue
    return False


def _verificar_en_hilo():
    global _estado, _verificando
    _verificando = True
    try:
        _estado = _probar()
    finally:
        _verificando = False


def verificar_async():
    """Re-verifica la conectividad en un hilo de fondo (no bloquea la UI)."""
    if _verificando:
        return
    threading.Thread(target=_verificar_en_hilo, daemon=True).start()


def ultimo_estado():
    """Último resultado conocido (None si aún no se ha verificado)."""
    return _estado


def hay_internet():
    """Comprobación bloqueante puntual (arranque del loop)."""
    return _probar()
