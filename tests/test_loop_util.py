#!/usr/bin/env python3
"""Tests para loop_util.py - utilidades base del loop nativo."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autopiloto_gui.loop_util import (
    ahora_ms,
    d2,
    hora_limite,
    hora_texto,
    logx,
    suma_coste,
)


def test_hora_texto_formato():
    ahora = hora_texto()
    assert len(ahora) == 5 and ahora[2] == ":"


def test_hora_limite_vacia_nunca_limita():
    assert hora_limite("") is False
    assert hora_limite(None) is False


def test_hora_limite_futura():
    assert hora_limite("99:59") is False


def test_hora_limite_pasada():
    assert hora_limite("00:00") is True


def test_ahora_ms_creciente():
    a = ahora_ms()
    b = ahora_ms()
    assert b >= a
    assert a > 1_500_000_000_000


def test_logx_append_formato():
    fd, path = __import__("tempfile").mkstemp(suffix=".log")
    os.close(fd)
    try:
        logx(path, "mensaje de prueba")
        logx(path, "otro")
        with open(path, encoding="utf-8") as f:
            lineas = f.read().splitlines()
        assert len(lineas) == 2
        for linea in lineas:
            assert len(linea) > 20
            assert linea[0] == "["
            assert linea.index("]") > 1
        assert "] mensaje de prueba" in lineas[0]
        assert "] otro" in lineas[1]
    finally:
        os.unlink(path)


def test_d2_redondea_dos_decimales():
    assert d2("1.5") == "1.50"
    assert d2("0.005") == "0.01"
    assert d2("1.999") == "2.00"
    assert d2(3) == "3.00"
    assert d2("1.234") == "1.23"


def test_suma_coste_dos_decimales():
    assert suma_coste("10.00", "2.345") == "12.35"
    assert suma_coste("0.50", "0.50") == "1.00"
    assert suma_coste("", "1.00") == "1.00"  # actual vacío = 0


if __name__ == "__main__":
    test_hora_texto_formato()
    test_hora_limite_vacia_nunca_limita()
    test_hora_limite_futura()
    test_hora_limite_pasada()
    test_ahora_ms_creciente()
    test_logx_append_formato()
    test_d2_redondea_dos_decimales()
    test_suma_coste_dos_decimales()
    print("\n🎉 Todos los tests de loop_util.py PASARON")
