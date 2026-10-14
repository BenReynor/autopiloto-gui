#!/usr/bin/env python3
"""Tests para loop_args.py - parseo de argumentos del loop nativo."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dedalo.loop_args import parse_args


def test_valores_por_defecto():
    args = parse_args([])
    assert args.plan == os.path.normpath(os.path.join(os.getcwd(), "plan.md"))
    assert args.hasta == ""
    assert args.push is False
    assert args.padre == "master"
    assert args.trabajo == ""


def test_plan_relativo_se_junta_con_cwd():
    args = parse_args(["mi/plan.md"])
    assert args.plan == os.path.normpath(os.path.join(os.getcwd(), "mi", "plan.md"))


def test_plan_absoluto_se_respeta():
    objetivo = os.path.join(os.sep, "tmp", "plan.md")
    args = parse_args([objetivo])
    assert args.plan == objetivo


def test_opciones_pasadas():
    args = parse_args(["plan.md", "--hasta", "22:00", "--push",
                       "--padre", "develop", "--trabajo", "feat/x"])
    assert args.hasta == "22:00"
    assert args.push is True
    assert args.padre == "develop"
    assert args.trabajo == "feat/x"


def test_opcion_sin_valor_sale_con_64():
    """Exit 64 (EX_USAGE): mismo fix que dedalo.sh para flags sin valor."""
    try:
        parse_args(["--hasta"])
    except SystemExit as e:
        assert e.code == 64
    else:
        raise AssertionError("debería salir con 64")


def test_flag_desconocido_sale_con_64():
    try:
        parse_args(["--no-existe"])
    except SystemExit as e:
        assert e.code == 64
    else:
        raise AssertionError("debería salir con 64")


if __name__ == "__main__":
    test_valores_por_defecto()
    test_plan_relativo_se_junta_con_cwd()
    test_plan_absoluto_se_respeta()
    test_opciones_pasadas()
    test_opcion_sin_valor_sale_con_64()
    test_flag_desconocido_sale_con_64()
    print("\n🎉 Todos los tests de loop_args.py PASARON")
