#!/usr/bin/env python3
"""Tests for app.Ventana's log/review logic.

Uses `Ventana.__new__` with fake collaborators to avoid building the full
window. Covers: edge-triggered detection (no duplicate webhooks), summary
per run, truncated log, and hiding of the review panel.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dedalo.app import Ventana  # noqa: E402


class _PanelFake:
    def __init__(self):
        self.texto = ""

    def setPlainText(self, texto):
        self.texto = texto

    def ensureCursorVisible(self):
        pass


class _LogsFake:
    def __init__(self):
        self.panel_loop = _PanelFake()


def _ventana_min(ruta):
    v = Ventana.__new__(Ventana)
    v.pan_logs = _LogsFake()
    v.loop = None
    v._lanzamiento = {}
    v._iter_actual = 0
    v._log_tam = 0
    v._log_marca = 0
    v._proyecto_actual = lambda: ("p", ruta)
    v.webhooks = []
    v.bloqueadas = []
    v._webhook_enviar = lambda evento, datos: v.webhooks.append(evento)
    v._notificar_tarea_bloqueada = lambda texto: v.bloqueadas.append(texto)
    return v


# ─── _tam_log ─────────────────────────────────────────────────

def test_tam_log(app, tmp_path):
    assert Ventana._tam_log(None, str(tmp_path)) == 0
    (tmp_path / "progreso.log").write_text("hola", encoding="utf-8")
    assert Ventana._tam_log(None, str(tmp_path)) == 4


# ─── _procesar_eventos_log ────────────────────────────────────

def test_procesar_eventos_tokens(app):
    v = _ventana_min("/tmp")
    Ventana._procesar_eventos_log(v, "… tokens/cuota agotados …")
    assert v.webhooks == ["tokens"]


def test_procesar_eventos_error(app):
    v = _ventana_min("/tmp")
    Ventana._procesar_eventos_log(v, "algo abortado: fallo")
    assert v.webhooks == ["error"]


def test_procesar_eventos_bloqueada(app):
    v = _ventana_min("/tmp")
    Ventana._procesar_eventos_log(v, "… tarea bloqueada: demo.py")
    assert v.bloqueadas and not v.webhooks


# ─── _tail_log edge-triggered ─────────────────────────────────

def test_tail_log_no_duplica_webhooks(app, tmp_path):
    ruta = str(tmp_path)
    log = tmp_path / "progreso.log"
    log.write_text("== Iteración 1: tarea demo ==\n", encoding="utf-8")

    v = _ventana_min(ruta)
    v._log_tam = v._log_marca = v._tam_log(ruta)

    # New content with an event → fires ONCE
    log.write_text(log.read_text() + "tokens/cuota agotados\n", encoding="utf-8")
    v._tail_log()
    assert v.webhooks == ["tokens"]

    # Refresh with no changes → neither rereads nor resends
    v._tail_log()
    assert v.webhooks == ["tokens"]

    # New UNRELATED content: the old event (still within the tail
    # window) must NOT be resent; only the delta is processed.
    log.write_text(log.read_text() + "tarea bloqueada: demo.py\n", encoding="utf-8")
    v._tail_log()
    assert v.webhooks == ["tokens"]
    assert len(v.bloqueadas) == 1


def test_tail_log_truncado_no_crashea(app, tmp_path):
    ruta = str(tmp_path)
    (tmp_path / "progreso.log").write_text("x\n", encoding="utf-8")
    v = _ventana_min(ruta)
    v._log_marca = 999999  # mark ahead of the end (rotated/truncated log)
    v._tail_log()
    assert v._log_marca == os.path.getsize(os.path.join(ruta, "progreso.log"))


# ─── _comprobar_revision_pendiente ────────────────────────────

def test_comprobar_revision_oculta_si_el_loop_no_corre(app):
    v = Ventana.__new__(Ventana)
    v.loop = None
    v._revision_pendiente = True
    ocultado = []

    class _RevisionFake:
        def ocultar(self):
            ocultado.append(1)

    class _EjecFake:
        panel_revision = _RevisionFake()

    v.pan_ejec = _EjecFake()
    Ventana._comprobar_revision_pendiente(v)
    assert v._revision_pendiente is False
    assert ocultado == [1]
