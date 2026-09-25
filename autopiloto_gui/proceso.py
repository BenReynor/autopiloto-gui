"""Helpers de procesos: captura de salida en vivo y trabajos en segundo plano."""

from PySide6.QtCore import QProcess, Qt, QThread, Signal
from PySide6.QtWidgets import QPlainTextEdit

SIGNAL_UI = Qt.ConnectionType.QueuedConnection


class PanelTarea(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(5000)
        self.setPlaceholderText("…")


class Trabajo(QThread):
    """Ejecuta una función sin bloqueo; devuelve su resultado por señal.

    El resultado se entrega SIEMPRE en el hilo de la UI (QueuedConnection),
    de modo que el slot conectado puede tocar widgets sin peligro. Emite
    None si la función lanza una excepción.

    IMPORTANTE: no liberes la referencia Python al objeto mientras el hilo
    siga corriendo; usa `finished` (o `Trabajo.liberar`) para soltarla.
    """

    listo = Signal(object)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def conectar(self, slot):
        """Conecta `listo` al slot garantizando entrega en el hilo de UI."""
        self.listo.connect(slot, SIGNAL_UI)

    def liberar(self, widget, attr="worker"):
        """Conecta `finished` para liberar la referencia del hilo.

        Pone `widget.<attr> = None` (por defecto `widget.worker`) TAN SOLO
        cuando el hilo ya terminó, evitando destruir un QThread en marcha.
        """

        def _fin():
            if widget is not None:
                try:
                    setattr(widget, attr, None)
                except (AttributeError, RuntimeError):
                    pass

        self.finished.connect(_fin, Qt.ConnectionType.QueuedConnection)

    def run(self):
        try:
            self.listo.emit(self._fn())
        except Exception:
            self.listo.emit(None)


class Proceso(QProcess):
    def __init__(self, panel, on_fin=None):
        super().__init__()
        self.panel = panel
        self._on_fin = on_fin
        self.readyReadStandardOutput.connect(self._leer)
        self.readyReadStandardError.connect(self._leer)
        self.finished.connect(self._terminado)

    def _leer(self):
        data = self.readAll().data()
        if isinstance(data, memoryview):
            data = data.tobytes()
        text = data.decode("utf-8", "replace").rstrip()
        if text:
            self.panel.appendPlainText(text)

    def _terminado(self, code, status):
        self.panel.appendPlainText(f"[fin] exit={code} ({status})")
        if self._on_fin:
            self._on_fin()
