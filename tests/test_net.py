#!/usr/bin/env python3
"""Tests for net.py - connectivity (simulated socket)."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dedalo import net  # noqa: E402


def test_probar_ok(monkeypatch):
    class _Conn:
        def close(self):
            pass

    monkeypatch.setattr(net.socket, "create_connection", lambda *a, **k: _Conn())
    assert net._probar() is True


def test_probar_falla(monkeypatch):
    def _boom(*a, **k):
        raise OSError("sin red")

    monkeypatch.setattr(net.socket, "create_connection", _boom)
    assert net._probar() is False


def test_verificar_async_actualiza_estado(monkeypatch):
    monkeypatch.setattr(net, "_probar", lambda: True)
    monkeypatch.setattr(net, "_estado", None)
    monkeypatch.setattr(net, "_verificando", False)
    net.verificar_async()
    for _ in range(200):
        if net.ultimo_estado() is not None:
            break
        time.sleep(0.01)
    assert net.ultimo_estado() is True
