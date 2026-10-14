"""Tests del empaquetado: iconos generados y spec de PyInstaller.

El build de macOS no se puede ejecutar en Linux, así que aquí se cubre lo
comprobable en cualquier SO: que la spec sea Python válido, que los iconos
committeados sean legibles y que el generador sigue funcionando (si se rompe,
el build de Windows/macOS fallaría al encontrar un .ico/.icns corrupto).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
PACKAGING = RAIZ / "packaging"


def test_spec_es_python_sintactico():
    """La spec sólo puede comprobarse con compile(): PyInstaller inyecta
    SPECPATH/Analysis/EXE... en tiempo de ejecución."""
    fuente = (PACKAGING / "dedalo.spec").read_text(encoding="utf-8")
    compile(fuente, "dedalo.spec", "exec")
    assert "BUNDLE" in fuente and "icono.icns" in fuente, (
        "falta el bundle .app de macOS en la spec")
    assert "icono.ico" in fuente, "Windows necesita un .ico, no un .svg"


def test_iconos_generados_son_validos():
    Image = pytest.importorskip("PIL.Image")

    icns = Image.open(PACKAGING / "icono.icns")
    assert icns.format == "ICNS"
    pixeles = {s[0] * s[2] for s in icns.info["sizes"]}
    assert max(pixeles) >= 512, f"icns demasiado pequeño: {pixeles}"

    ico = Image.open(PACKAGING / "icono.ico")
    assert ico.format == "ICO"
    assert max(ancho for ancho, _ in ico.info["sizes"]) == 256


def test_build_windows_smk_checkea_el_motor_empaquetado():
    """El smoke del build de Windows debe valider el branch `--dedalo-loop`
    del entrypoint (si alguien lo quita, el zip sale pero el motor empaquetado
    queda sin verificar)."""
    fuente = (PACKAGING / "build_windows.sh").read_text(encoding="utf-8")
    assert "--dedalo-loop" in fuente
    assert "Compress-Archive" in fuente
    assert "ABORTADO: agente no disponible" in fuente


def test_make_iconos_regenera_desde_el_svg(tmp_path, monkeypatch):
    """Ejecuta el generador real contra un destino temporal: si el SVG o la
    ruta cambian de forma inesperada, el build se entera aquí y no en CI."""
    Image = pytest.importorskip("PIL.Image")
    pytest.importorskip("PySide6.QtSvg")

    ruta = PACKAGING / "make_iconos.py"
    spec = importlib.util.spec_from_file_location("make_iconos_prueba", ruta)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    monkeypatch.setattr(mod, "ICNS", tmp_path / "icono.icns")
    monkeypatch.setattr(mod, "ICO", tmp_path / "icono.ico")
    mod.generar()

    assert Image.open(tmp_path / "icono.icns").format == "ICNS"
    assert Image.open(tmp_path / "icono.ico").format == "ICO"
