"""Fixtures compartidas de la suite headless.

Define una QApplication de sesión (offscreen) para los tests que instancian
widgets/QThread. Los módulos que ya traen su propia fixture `app`
(p. ej. test_gui_botones.py) siguen usándola y no se ven afectados.
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def app():
    a = QApplication.instance() or QApplication(sys.argv)
    yield a
    # Teardown limpio. NO se llama a.deleteLater(): borrar el QApplication de
    # sesión hace que Shiboken reporte "shared QObject was deleted directly"
    # y "Pure virtual function called" al salir (SIGABRT 134 / exit 1). Se
    # liberan ventanas y se para el bucle; el proceso termina solo.
    a.processEvents()
    a.closeAllWindows()
    a.quit()
    a.processEvents()
