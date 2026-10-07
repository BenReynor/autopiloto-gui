#!/usr/bin/env python3
"""Tests de `_loop_fin` / `_detener_loop`: la parada del loop no puede congelar la UI.

Regresión del bug: `_loop_fin()` llamaba a `_limpiar_sesiones_proyecto()` de forma
síncrona ANTES de re-habilitar los botones. Ese método hace un `subprocess.run` con
`timeout=120` para `opencode session list` y otro por cada `session delete`, así que
con 10 sesiones eran hasta 22 minutos de ventana congelada justo después de pulsar
Detener, con los botones deshabilitados durante todo ese tiempo.

Aquí se ejercitan los métodos reales contra un stub (patrón de
`test_gui_botones.py::test_git_revert_no_rompe_ui`): no se instancia `Ventana`
completa, que es demasiado pesada para la suite, pero sí se ejecutan los cuerpos de
los métodos que importan.
"""

import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock  # noqa: E402

from PySide6.QtCore import QProcess  # noqa: E402

from autopiloto_gui.app import Ventana  # noqa: E402
from autopiloto_gui.proceso import Trabajo  # noqa: E402

PROYECTO = "/tmp/autopiloto-test-proyecto"


def _stub(orden=None, limpieza_real=False):
    """Ventana falsa: registra en `orden` el orden de las operaciones clave.

    `limpieza_real=True` enlaza los métodos de limpieza authenticos al stub, para
    que la prueba recorra el `Trabajo` de verdad en vez de un mock.
    """
    stub = MagicMock()
    stub._proyecto_actual.return_value = ("demo", PROYECTO)
    # _inicio_loop_ts a 0 => se salta el bloque del webhook de fin, que leería disco
    stub._inicio_loop_ts = 0
    stub._log_inicio = 0
    # El atributo existe en la Ventana real desde __init__; si el stub lo deja
    # ausente, MagicMock lo fabricaría como mock y el guard isRunning() miente.
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
    """Los botones y el panel se re-habilitan ANTES de lanzar la limpieza."""
    orden = []
    stub = _stub(orden)

    Ventana._loop_fin(stub)

    assert "limpiar_sesiones" in orden, "la limpieza no se lanzó"
    assert "b_iniciar" in orden and "b_detener" in orden

    i_iniciar = orden.index("b_iniciar")
    i_limpiar = orden.index("limpiar_sesiones")

    # El invariante del bug: la limpieza iba antes de habilitar la UI.
    assert i_limpiar > i_iniciar, (
        f"la limpieza se lanzó antes de re-habilitar la UI: {orden}")
    assert orden.index("b_detener") < i_limpiar
    assert orden.index("cmb") < i_limpiar


def test_loop_fin_no_bloquea_con_sesiones_lentas(app, monkeypatch):
    """Con `opencode` lento, `_loop_fin` debe volver de inmediato.

    Antes del arreglo la llamada a `subprocess.run` con `timeout=120` se
    ejecutaba en el hilo de la UI, así que este test tardaba los 2 s simulados.
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

    # La UI se repinta ya; la limpieza sigue en vuelo.
    assert elapsed < 1.0, f"_loop_fin tardó {elapsed:.2f}s (no debe bloquear)"
    stub.pan_ejec.b_iniciar.setEnabled.assert_called_once_with(True)
    stub.pan_ejec.b_detener.setEnabled.assert_called_once_with(False)
    stub.cmb.setEnabled.assert_called_once_with(True)

    # Se programó en un Trabajo de verdad y sigue corriendo.
    worker = stub._worker_sesiones_limpieza
    assert isinstance(worker, Trabajo)
    assert not llamadas, "la limpieza no debe ejecutarse en el hilo de la UI"
    assert worker.wait(10000), "el trabajo de limpieza no terminó"
    assert llamadas, "no se llegó a ejecutar el comando de opencode"


@pytest.mark.skipif(
    not os.path.exists("/bin/sh"),
    reason="el proceso de prueba vive en /bin/sh (no existe en Windows)")
def test_detener_loop_no_bloquea_esperando(app):
    """`_detener_loop` devuelve al instante y escala a SIGKILL con un timer."""
    proc = QProcess()
    proc.start("/bin/sh", ["-c", "sleep 30"])
    assert proc.waitForStarted(3000), "no se pudo lanzar el proceso de prueba"
    # Dar tiempo a que el proceso quede en Running
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

    # El bug: waitForFinished(5000) bloqueaba el hilo de la UI 5 s.
    assert elapsed < 1.0, f"_detener_loop tardó {elapsed:.2f}s (no debe bloquear)"
    # SIGTERM enviado: el sleep sin trap muere casi al instante.
    assert proc.waitForFinished(4000), "SIGTERM no detuvo el proceso"
    proc.waitForFinished(1000)


def test_detener_loop_ignora_proceso_ya_parado():
    """Si el proceso no está corriendo, no hace nada."""
    stub = MagicMock()
    proc = QProcess()  # NotRunning
    stub.loop = proc

    Ventana._detener_loop(stub)
    stub.pan_logs.panel_loop.appendPlainText.assert_not_called()
