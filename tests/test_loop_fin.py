#!/usr/bin/env python3
"""Tests for `_loop_fin` / `_detener_loop`: stopping the loop must not freeze the UI.

Regression of the bug: `_loop_fin()` called `_limpiar_sesiones_proyecto()`
synchronously BEFORE re-enabling the buttons. That method runs `subprocess.run`
with `timeout=120` for `opencode session list` and one more per `session delete`,
so with 10 sessions that was up to 22 minutes of frozen window right after pressing
Stop, with the buttons disabled the whole time.

The real methods are exercised here against a stub (same pattern as
`test_gui_botones.py::test_git_revert_no_rompe_ui`): the full `Ventana` is not
instantiated, as it is too heavy for the suite, but the bodies of the methods
that matter are actually executed.
"""

import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock  # noqa: E402

from PySide6.QtCore import QProcess  # noqa: E402

from dedalo.app import Ventana  # noqa: E402
from dedalo.proceso import Trabajo  # noqa: E402

PROYECTO = "/tmp/dedalo-test-proyecto"


def _stub(orden=None, limpieza_real=False):
    """Fake window: records the order of the key operations in `orden`.

    `limpieza_real=True` binds the authentic cleanup methods to the stub, so the
    test exercises the real `Trabajo` instead of a mock.
    """
    stub = MagicMock()
    stub._proyecto_actual.return_value = ("demo", PROYECTO)
    # _inicio_loop_ts at 0 => skips the finish-webhook block, which would read disk
    stub._inicio_loop_ts = 0
    stub._log_inicio = 0
    # The attribute exists on the real Ventana since __init__; if the stub leaves
    # it absent, MagicMock would fabricate it as a mock and the isRunning() guard lies.
    stub._worker_sesiones_limpieza = None
    if orden is not None:
        stub.pan_ejec.b_iniciar.setEnabled.side_effect = (
            lambda v: orden.append("b_iniciar"))
        stub.pan_ejec.b_detener.setEnabled.side_effect = (
            lambda v: orden.append("b_detener"))
        stub.cmb.setEnabled.side_effect = lambda v: orden.append("cmb")
        stub._set_fase_loop.side_effect = lambda *a, **k: orden.append("fase")
    if limpieza_real:
        stub._limpiar_sesiones_proyecto = Ventana._limpiar_sesiones_proyecto.__get__(stub)
        stub._limpiar_sesiones_hecho = Ventana._limpiar_sesiones_hecho.__get__(stub)
        stub._programar_limpiar_sesiones = Ventana._programar_limpiar_sesiones.__get__(stub)
    elif orden is not None:
        stub._programar_limpiar_sesiones.side_effect = (
            lambda r: orden.append("limpiar_sesiones"))
    return stub


def test_loop_fin_habilita_ui_antes_de_limpiar_sesiones():
    """The buttons and the panel are re-enabled BEFORE launching the cleanup."""
    orden = []
    stub = _stub(orden)

    Ventana._loop_fin(stub)

    assert "limpiar_sesiones" in orden, "la limpieza no se lanzó"
    assert "b_iniciar" in orden and "b_detener" in orden

    i_iniciar = orden.index("b_iniciar")
    i_limpiar = orden.index("limpiar_sesiones")

    # The invariant of the bug: the cleanup used to run before enabling the UI.
    assert i_limpiar > i_iniciar, (
        f"la limpieza se lanzó antes de re-habilitar la UI: {orden}")
    assert orden.index("b_detener") < i_limpiar
    assert orden.index("cmb") < i_limpiar


def test_loop_fin_no_bloquea_con_sesiones_lentas(app, monkeypatch):
    """With a slow `opencode`, `_loop_fin` must return immediately.

    Before the fix, the `subprocess.run` call with `timeout=120` ran on the UI
    thread, so this test took the simulated 2 s.
    """
    llamadas = []

    def _lento(*args, **kwargs):
        llamadas.append(args)
        time.sleep(2.0)
        return MagicMock(returncode=0, stdout=json.dumps([]))

    monkeypatch.setattr("subprocess.run", _lento)
    monkeypatch.setattr("shutil.which", lambda cand: "/usr/bin/opencode")

    stub = _stub(limpieza_real=True)

    t0 = time.time()
    Ventana._loop_fin(stub)
    elapsed = time.time() - t0

    # The UI repaints now; the cleanup is still in flight.
    assert elapsed < 1.0, f"_loop_fin tardó {elapsed:.2f}s (no debe bloquear)"
    stub.pan_ejec.b_iniciar.setEnabled.assert_called_once_with(True)
    stub.pan_ejec.b_detener.setEnabled.assert_called_once_with(False)
    stub.cmb.setEnabled.assert_called_once_with(True)

    # It was scheduled on a real Trabajo and is still running.
    worker = stub._worker_sesiones_limpieza
    assert isinstance(worker, Trabajo)
    assert not llamadas, "la limpieza no debe ejecutarse en el hilo de la UI"
    assert worker.wait(10000), "el trabajo de limpieza no terminó"
    assert llamadas, "no se llegó a ejecutar el comando de opencode"


@pytest.mark.skipif(
    not os.path.exists("/bin/sh"),
    reason="el proceso de prueba vive en /bin/sh (no existe en Windows)")
def test_detener_loop_no_bloquea_esperando(app):
    """`_detener_loop` returns instantly and escalates to SIGKILL with a timer."""
    proc = QProcess()
    proc.start("/bin/sh", ["-c", "sleep 30"])
    assert proc.waitForStarted(3000), "no se pudo lanzar el proceso de prueba"
    # Give the process time to reach Running
    for _ in range(50):
        app.processEvents()
        if proc.state() == QProcess.Running:
            break
        time.sleep(0.01)
    assert proc.state() == QProcess.Running

    stub = MagicMock()
    stub.loop = proc

    t0 = time.time()
    Ventana._detener_loop(stub)
    elapsed = time.time() - t0

    # The bug: waitForFinished(5000) blocked the UI thread for 5 s.
    assert elapsed < 1.0, f"_detener_loop tardó {elapsed:.2f}s (no debe bloquear)"
    # SIGTERM sent: the sleep without a trap dies almost instantly.
    assert proc.waitForFinished(4000), "SIGTERM no detuvo el proceso"
    proc.waitForFinished(1000)


def test_detener_loop_ignora_proceso_ya_parado():
    """If the process is not running, it does nothing."""
    stub = MagicMock()
    proc = QProcess()  # NotRunning
    stub.loop = proc

    Ventana._detener_loop(stub)
    stub.pan_logs.panel_loop.appendPlainText.assert_not_called()
