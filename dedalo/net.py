"""Internet connectivity check.

opencode's AI models require network; if it goes down there is no point in
launching tasks. The real check runs in a background thread: the GUI always
reads the cached state (without blocking) and `verificar_async()` refreshes in
the background.
"""

import socket
import threading

from . import configuracion as cfg

HOSTS = ("1.1.1.1", "8.8.8.8")

_estado = None          # True/False, last known result
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
    """Re-checks connectivity in a background thread (does not block the UI)."""
    if _verificando:
        return
    threading.Thread(target=_verificar_en_hilo, daemon=True).start()


def ultimo_estado():
    """Last known result (None if it has not been checked yet)."""
    return _estado


def hay_internet():
    """One-off blocking check (loop startup)."""
    return _probar()
