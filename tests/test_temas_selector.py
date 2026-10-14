#!/usr/bin/env python3
"""Tests de temas.py y selector_modelo.py, los dos módulos sin cobertura.

temas.py son 959 líneas y sostiene el aspecto de toda la app (9 temas, QSS
completo, tokens de color); si un token se renombra, el QSS se degrada a
valores por defecto o lanza excepción, la UI se rompe entera sin que ningún
test se entere. selector_modelo.py es el widget de los combos proveedor/modelo
y su API (currentText/setCurrentText) es sutil: devuelve siempre
'proveedor/modelo' y ese valor viaja a la CLI del agente.
"""

import os
import re
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402

from dedalo import selector_modelo, temas  # noqa: E402

# ---------- temas ----------


def test_hay_nueve_temas_y_no_se_repiten():
    assert len(temas.NOMBRES) == 9, f"esperados 9 temas, hay {len(temas.NOMBRES)}"
    assert len(set(temas.NOMBRES)) == len(temas.NOMBRES), "hay nombres repetidos"


def _color_valido(valor):
    """Acepta las cuatro formas de token que realmente usa _qss_variables():

      * '#rrggbb'                → QColor lo parsea
      * 'rgba(r,g,b,a)'          → el QSS lo acepta; QColor() no, y por eso
                                   producción tiene el helper _qcolor()
      * '37, 99, 235'            → tripleta para interpolar dentro de rgb(...)
      * '0 1px 2px rgba(...)'    → box-shadow
    """
    valor = valor.strip()
    if valor.startswith("rgba"):
        return len(re.findall(r"[\d.]+", valor)) == 4
    if valor.startswith("#"):
        return QColor(valor).isValid()
    if re.fullmatch(r"[\d,\s]+", valor):
        return len(valor.split(",")) == 3
    return "px" in valor and "rgba" in valor


@pytest.mark.parametrize("nombre", temas.NOMBRES)
def test_variables_de_cada_tema_estan_completas(nombre):
    """Cada token que consume el QSS debe existir y tener valor utilizable."""
    variables = temas._qss_variables(nombre)
    assert variables, f"{nombre} no devuelve variables"
    for clave, valor in variables.items():
        assert isinstance(clave, str) and clave
        assert isinstance(valor, str) and valor.strip(), (
            f"{nombre}: token {clave!r} vacío"
        )
        assert _color_valido(valor), (
            f"{nombre}: token {clave!r} = {valor!r} no tiene una forma conocida"
        )


def test_los_nueve_temas_declaran_los_mismos_tokens():
    """Un token que existe en un tema y en otro no = QSS a medio construir."""
    referencia = set(temas._qss_variables(temas.NOMBRES[0]))
    assert referencia, "el primer tema no declara ningún token"
    for nombre in temas.NOMBRES[1:]:
        claves = set(temas._qss_variables(nombre))
        assert claves == referencia, (
            f"{nombre}: le faltan {referencia - claves} "
            f"y tiene de más {claves - referencia}"
        )


@pytest.mark.parametrize("nombre", temas.NOMBRES)
def test_qss_de_cada_tema_se_genera_sin_excepcion(app, nombre):
    """_qss() consulta QFontDatabase, así que exige QApplication viva."""
    qss = temas._qss(temas._qss_variables(nombre))
    assert qss.strip(), f"{nombre} genera QSS vacío"
    assert "{" in qss and "}" in qss, f"{nombre} genera QSS mal formado"
    assert "None" not in qss, f"{nombre} ha interpolado None en el QSS"


def test_inicializar_temas_cubre_todos_los_nombres(app):
    temas.inicializar_temas()
    cache = temas.obtener_temas()
    faltan = [n for n in temas.NOMBRES if not cache.get(n)]
    assert not faltan, f"temas sin QSS generado: {faltan}"


def test_colores_tema_devuelve_los_tokens_que_pinta_la_gui(app):
    """colores_tema() es la fuente para pintado manual; si le falta una clave,
    el consumidor revienta con KeyError."""
    esperadas = {
        "bg_panel", "bg_sunken", "text_primary", "text_secondary",
        "text_tertiary", "text_inverse", "border", "accent", "accent_claro",
        "success", "error", "warning",
    }
    for nombre in temas.NOMBRES:
        colores = temas.colores_tema(nombre)
        assert esperadas <= set(colores), (
            f"{nombre}: faltan {esperadas - set(colores)}"
        )
        for clave in esperadas:
            assert isinstance(colores[clave], QColor), f"{nombre}:{clave} no es QColor"
            assert colores[clave].isValid(), f"{nombre}:{clave} es un QColor inválido"


def test_temas_oscuros_y_claros_no_son_el_mismo_color(app):
    """Detecta un tema 'Claro' que se quedó con los tokens del oscuro."""
    oscuro = temas.colores_tema("Oscuro")
    claro = temas.colores_tema("Claro")
    assert oscuro["bg_panel"] != claro["bg_panel"], (
        "Oscuro y Claro tienen el mismo fondo: probablemente un token mal copiado"
    )


# ---------- selector_modelo ----------


def _selector(monkeypatch, catalogo=None, proveedores=None):
    """Selector con el catálogo global controlado (sin tocar la red)."""
    monkeypatch.setattr(
        selector_modelo.modelos,
        "nombres_proveedores",
        lambda: proveedores or ["openai", "google"],
    )
    monkeypatch.setattr(
        selector_modelo.modelos,
        "lista_modelos_proveedor",
        lambda prov: (catalogo or {}).get(prov, [f"{prov}-default"]),
    )
    return selector_modelo.SelectorModelo()


def test_selector_devuelve_proveedor_modelo(app, monkeypatch):
    s = _selector(monkeypatch)
    s.addItems(["openai/gpt-4o", "openai/gpt-4o-mini", "google/gemini-2.0"])
    s.setCurrentText("openai/gpt-4o-mini")
    assert s.currentText() == "openai/gpt-4o-mini"


def test_selector_proveedor_sin_modelos_devuelve_solo_proveedor(app, monkeypatch):
    """Sin modelos no hay 'prov/modelo' que devolver: se queda en el proveedor."""
    s = _selector(monkeypatch, catalogo={"openai": []})
    s.setCurrentText("openai")
    assert s.currentText() == "openai"


def test_selector_cambiar_de_proveedor_elige_su_primer_modelo(app, monkeypatch):
    """Cambiar de proveedor repuebla el combo y deja uno seleccionado, para no
    devolver un modelo que ya no pertenece al proveedor elegido."""
    s = _selector(
        monkeypatch,
        catalogo={
            "openai": ["gpt-4o", "gpt-4o-mini"],
            "google": ["gemini-2.0"],
        },
    )
    s.setCurrentText("openai/gpt-4o-mini")
    assert s.currentText() == "openai/gpt-4o-mini"
    s.setCurrentText("google")
    assert s.currentText() == "google/gemini-2.0", (
        "al cambiar de proveedor se mantiene un modelo del anterior"
    )


def test_selector_vacio_devuelve_cadena_vacia(app, monkeypatch):
    s = _selector(monkeypatch)
    s.clear()
    assert s.currentText() == ""


def test_selector_emite_al_cambiar(app, monkeypatch):
    s = _selector(monkeypatch)
    s.addItems(["openai/gpt-4o"])
    emitidos = []
    s.currentTextChanged.connect(emitidos.append)
    s.setCurrentText("openai/gpt-4o")
    assert emitidos == ["openai/gpt-4o"]


def test_selector_ignora_etiquetas_sin_proveedor(app, monkeypatch):
    """Un 'modelo' sin '/' no tiene proveedor: no puede generar un id válido."""
    s = _selector(monkeypatch)
    s.addItems(["sin-proveedor"])
    assert "sin-proveedor" not in [
        s.cmb_proveedor.itemText(i) for i in range(s.cmb_proveedor.count())
    ]


def test_selector_no_duplica_modelos(app, monkeypatch):
    s = _selector(monkeypatch)
    s.addItems(["openai/gpt-4o", "openai/gpt-4o"])
    s.setCurrentText("openai")
    assert s.cmb_modelo.count() == 1, "el mismo modelo se ha duplicado"
