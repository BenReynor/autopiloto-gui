"""Fixtures compartidas de la suite headless.

Define una QApplication de sesión (offscreen) para los tests que instancian
widgets/QThread. Los módulos que necesitan la app simplemente la piden como
fixture `app`; el apagado (romper ciclos de señales y vaciar borrados
diferidos) lo centraliza aquí.
"""

import gc
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


def _drenar(app):
    """Colecta ciclos y vacía la cola de borrados diferidos de Qt."""
    for _ in range(3):
        gc.collect()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _apagar_qt(app):
    """Apaga la suite sin el SIGSEGV de teardown de Qt.

    Los paneles conectan señales a sus propios slots y QTimer(self)/padres, de
    modo que se forman CICLOS de referencia (widget -> señal -> bound method ->
    widget). El recolector de ciclos los libera tarde: a veces DESPUÉS de que
    PySide destruya la QApplication en Py_FinalizeEx. Entonces Shiboken recorre
    un QObject cuyo lado C++ ya no existe y revienta dentro de ~QObject
    (SIGSEGV, exit 139; a veces SIGABRT 134 "shared QObject was deleted
    directly"). Solución: romper esos ciclos y vaciar los borrados diferidos
    AHORA, con la QApplication todavía viva, para que no quede ningún widget
    vivo al finalizar el intérprete.
    """
    # Cerrar primero: closeAllWindows() deja los widgets marcados y permite
    # que deleteLater() los destruya en el siguiente drenaje.
    app.closeAllWindows()
    _drenar(app)
    for widget in list(app.topLevelWidgets()):
        widget.deleteLater()
    _drenar(app)
    app.quit()
    _drenar(app)


@pytest.fixture(scope="session")
def app():
    a = QApplication.instance() or QApplication(sys.argv)
    yield a
    _apagar_qt(a)
