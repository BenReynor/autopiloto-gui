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
    # Teardown limpio: evitar crash de pyqtgraph/Shiboken al salir del proceso
    a.processEvents()
    a.closeAllWindows()
    a.quit()
    a.processEvents()
    a.deleteLater()
