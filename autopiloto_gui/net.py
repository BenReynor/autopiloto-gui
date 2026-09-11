"""Comprobación de conectividad a internet.

Los modelos IA de opencode requieren red; si se cae no tiene sentido lanzar
tareas. Se usa un timeout corto para no bloquear la interfaz.
"""

import socket

HOSTS = ["1.1.1.1", "8.8.8.8"]


def hay_internet(timeout=3):
    for host in HOSTS:
        try:
            socket.create_connection((host, 53), timeout=timeout).close()
            return True
        except OSError:
            continue
    return False