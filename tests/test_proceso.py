#!/usr/bin/env python3
"""Tests for proceso.py - Trabajo (background execution) and Proceso (QProcess)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402

from dedalo.proceso import Proceso, Trabajo  # noqa: E402


def _ejecutar(worker, timeout_ms=3000):
    """Starts the worker and waits for its result (UI thread)."""
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


def test_proceso_erroroccurred_failedtostart_llama_on_fin(app):
    """If QProcess cannot start (nonexistent dir), errorOccurred(FailedToStart)
    must invoke on_fin so the UI is not left blocked."""
    from dedalo.paneles import PanelTarea

    panel = PanelTarea()
    llamado = []

    def on_fin():
        llamado.append(True)

    # Nonexistent directory → FailedToStart
    with tempfile.TemporaryDirectory() as tmp:
        dir_inexistente = os.path.join(tmp, "no_existe")

        p = Proceso(panel, on_fin=on_fin)
        p.setWorkingDirectory(dir_inexistente)
        p.start("bash", ["-c", "echo hola"])

        # Give Qt time to process the error
        from PySide6.QtCore import QEventLoop, QTimer
        loop = QEventLoop()
        QTimer.singleShot(500, loop.quit)
        loop.exec()

    assert llamado, "on_fin no se llamó tras FailedToStart"
