#!/usr/bin/env python3
"""Tests para proceso.py - Trabajo (ejecución en segundo plano)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402

from autopiloto_gui.proceso import Trabajo  # noqa: E402


def _ejecutar(worker, timeout_ms=3000):
    """Arranca el worker y espera su resultado (hilo de UI)."""
    loop = QEventLoop()
    capturado = []

    def _listo(resultado):
        capturado.append(resultado)
        loop.quit()

    worker.conectar(_listo)
    t = QTimer()
    t.setSingleShot(True)
    t.timeout.connect(loop.quit)
    t.start(timeout_ms)
    worker.start()
    loop.exec()
    worker.wait(1000)
    return capturado[0] if capturado else None


def test_trabajo_devuelve_resultado(app):
    worker = Trabajo(lambda: 21 * 2)
    assert _ejecutar(worker) == 42


def test_trabajo_excepcion_emite_none(app):
    def _boom():
        raise ValueError("fallo intencional")

    worker = Trabajo(_boom)
    assert _ejecutar(worker) is None
