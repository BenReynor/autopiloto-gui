"""Process helpers: live output capture and background jobs."""

from PySide6.QtCore import QProcess, Qt, QThread, Signal
from PySide6.QtWidgets import QPlainTextEdit

from .i18n import t

SIGNAL_UI = Qt.ConnectionType.QueuedConnection


class PanelTarea(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(5000)
        self.setPlaceholderText("…")


class Trabajo(QThread):
    """Runs a function without blocking; returns its result via a signal.

    The result is ALWAYS delivered on the UI thread (QueuedConnection),
    so that the connected slot can touch widgets safely. Emits
    None if the function raises an exception.

    IMPORTANT: do not release the Python reference to the object while the
    thread is still running; use `finished` (or `Trabajo.liberar`) to drop it.
    """

    listo = Signal(object)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def conectar(self, slot):
        """Connects `listo` to the slot guaranteeing delivery on the UI thread."""
        self.listo.connect(slot, SIGNAL_UI)

    def liberar(self, widget, attr="_worker"):
        """Connects `finished` to release the thread reference.

        Sets `widget.<attr> = None` (by default `widget._worker`) ONLY
        when the thread has already finished, avoiding destroying a
        running QThread.
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
        # If the process does not start (nonexistent dir, non-executable binary, etc.)
        # Qt emits errorOccurred(FailedToStart) and does NOT emit finished → without this
        # the on_fin callback is never called and the UI stays blocked.
        self.errorOccurred.connect(self._error)

    def _leer(self):
        data = self.readAll().data()
        if isinstance(data, memoryview):
            data = data.tobytes()
        text = data.decode("utf-8", "replace").rstrip()
        if text:
            self.panel.appendPlainText(text)

    def _terminado(self, code, status):
        self.panel.appendPlainText(
            t("[fin] exit={code} ({status})", code=code, status=status))
        if self._on_fin:
            self._on_fin()

    def _error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.panel.appendPlainText(t(
                "[fin] error: FailedToStart (could not start the process)"))
            if self._on_fin:
                self._on_fin()
