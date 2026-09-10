"""Helpers de procesos: captura de salida en vivo para los scripts."""

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QPlainTextEdit


class PanelTarea(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(5000)
        self.setPlaceholderText("…")


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