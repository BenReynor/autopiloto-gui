"""Temas visuales del panel: Claro, Oscuro y Hacker."""

NOMBRES = ["Claro", "Oscuro", "Hacker"]


def _qss(c):
    return f"""
QWidget {{
    background-color: {c['fondo']};
    color: {c['texto']};
    font-size: 14px;
}}
QMainWindow, QDialog {{ background-color: {c['fondo']}; }}
QLabel {{ background: transparent; }}
QGroupBox {{
    border: 1px solid {c['borde']};
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 6px;
    background: {c['panel']};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {c['acento']};
    font-weight: bold;
}}
QPushButton {{
    background-color: {c['boton']};
    color: {c['texto_boton']};
    border: 1px solid {c['borde']};
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: bold;
}}
QPushButton:hover {{ background-color: {c['boton_hover']}; color: {c['texto_boton_hover']}; }}
QPushButton:pressed {{ background-color: {c['boton_active']}; }}
QPushButton:disabled {{
    background-color: {c['disabled']};
    color: {c['disabled_texto']};
    border-color: {c['disabled']};
}}
QLineEdit, QComboBox {{
    background-color: {c['entrada']};
    color: {c['texto']};
    border: 1px solid {c['borde']};
    border-radius: 6px;
    padding: 6px 8px;
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {c['acento']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background-color: {c['entrada']};
    color: {c['texto']};
    selection-background-color: {c['acento']};
    selection-color: {c['texto_boton']};
}}
QPlainTextEdit, QTextEdit {{
    background-color: {c['entrada']};
    color: {c['texto']};
    border: 1px solid {c['borde']};
    border-radius: 6px;
    padding: 6px;
    selection-background-color: {c['seleccion']};
}}
QTabWidget::pane {{
    border: 1px solid {c['borde']};
    border-radius: 8px;
    top: -1px;
    background: transparent;
}}
QTabBar::tab {{
    background-color: {c['panel']};
    color: {c['texto']};
    border: 1px solid {c['borde']};
    padding: 8px 18px;
    margin-right: 2px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}}
QTabBar::tab:selected {{
    background-color: {c['acento']};
    color: {c['texto_boton']};
    font-weight: bold;
}}
QTabBar::tab:hover:!selected {{ background-color: {c['boton_hover']}; color: {c['texto_boton_hover']}; }}
QCheckBox {{ background: transparent; spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {c['borde']};
    border-radius: 4px;
    background: {c['entrada']};
}}
QCheckBox::indicator:checked {{
    background-color: {c['acento']};
    border-color: {c['acento']};
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background-color: {c['borde']};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background-color: {c['acento']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QToolTip {{
    background-color: {c['entrada']};
    color: {c['texto']};
    border: 1px solid {c['acento']};
}}
"""


TEMAS = {
    "Claro": _qss({
        "fondo": "#f4f6fb",
        "panel": "#ffffff",
        "entrada": "#ffffff",
        "texto": "#1f2430",
        "texto_boton": "#ffffff",
        "texto_boton_hover": "#ffffff",
        "boton": "#4f46e5",
        "boton_hover": "#6366f1",
        "boton_active": "#4338ca",
        "disabled": "#e2e6ef",
        "disabled_texto": "#9aa3b2",
        "borde": "#d4dae6",
        "acento": "#4f46e5",
        "seleccion": "#6c96ff",
    }),
    "Oscuro": _qss({
        "fondo": "#161a22",
        "panel": "#1d232e",
        "entrada": "#1e2733",
        "texto": "#e6e9ef",
        "texto_boton": "#ffffff",
        "texto_boton_hover": "#ffffff",
        "boton": "#2f3a4c",
        "boton_hover": "#3d4c63",
        "boton_active": "#232c3a",
        "disabled": "#232b37",
        "disabled_texto": "#5c6677",
        "borde": "#2c3542",
        "acento": "#6c8cff",
        "seleccion": "#3f5aa8",
    }),
    "Hacker": _qss({
        "fondo": "#04080a",
        "panel": "#071009",
        "entrada": "#04180d",
        "texto": "#00ff99",
        "texto_boton": "#04080a",
        "texto_boton_hover": "#04080a",
        "boton": "#00ff77",
        "boton_hover": "#33ff99",
        "boton_active": "#00cc5f",
        "disabled": "#0a1a10",
        "disabled_texto": "#2e7a52",
        "borde": "#0f3d24",
        "acento": "#00ff77",
        "seleccion": "#0fff7f",
    }),
}