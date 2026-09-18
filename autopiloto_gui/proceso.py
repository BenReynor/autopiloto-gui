"""Helpers de procesos: captura de salida en vivo y trabajos en segundo plano."""

from PySide6.QtCore import QProcess, QThread, Signal
from PySide6.QtWidgets import QPlainTextEdit


class PanelTarea(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(5000)
        self.setPlaceholderText("…")


class Trabajo(QThread):
    """Ejecuta una función sin bloqueo; devuelve su resultado por señal.

    El resultado se emite en el hilo de la UI, así el `slot` puede tocar
    widgets sin peligro. Emite None si la función lanza una excepción.
    """

    listo = Signal(object)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

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
        data = bytes(self.readAll()).decode("utf-8", "replace").rstrip()
        if data:
            self.panel.appendPlainText(data)

    def _terminado(self, code, status):
        self.panel.appendPlainText(f"[fin] exit={code} ({status})")
        if self._on_fin:
            self._on_fin()