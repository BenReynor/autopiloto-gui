#!/usr/bin/env python3
"""Tests para sensor.py - lectura y filtrado de temperatura."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dedalo import sensor  # noqa: E402


def _fichero(tmp_path, nombre, contenido):
    p = tmp_path / nombre
    p.write_text(contenido)
    return str(p)


def test_zonas_termicas_filtra_rango_y_basura(monkeypatch, tmp_path):
    ok = _fichero(tmp_path, "ok", "60000")
    alta = _fichero(tmp_path, "alta", "500000")
    basura = _fichero(tmp_path, "basura", "no-numero")
    monkeypatch.setattr(sensor.glob, "glob", lambda _patron: [ok, alta, basura])
    assert sensor._zonas_termicas() == [60.0]


def test_leer_temperatura_usa_cache(monkeypatch):
    llamadas = {"n": 0}

    def _zonas_fake():
        llamadas["n"] += 1
        return [42.0]

    monkeypatch.setattr(sensor, "_zonas_termicas", _zonas_fake)
    monkeypatch.setattr(sensor, "_sensors", lambda: [])
    monkeypatch.setattr(sensor, "_cache", (0.0, None))

    assert sensor.leer_temperatura() == 42.0
    assert sensor.leer_temperatura() == 42.0
    assert llamadas["n"] == 1
