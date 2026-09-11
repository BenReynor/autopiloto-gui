"""Selector de modelo IA en dos niveles: proveedor -> modelo.

Permite elegir un proveedor (editable) y luego un modelo de ese proveedor
(editable), para poder apuntar a cualquier modelo aunque no esté en la lista
detectada por `opencode models` (p. ej. openai/..., claude/anthropic/...).
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget, QComboBox

PROVEEDORES = [
    "opencode", "google", "openai", "anthropic", "xai", "groq",
    "together", "deepseek", "azure", "bedrock", "ollama", "lmstudio",
    "mistral", "github",
]


class SelectorModelo(QWidget):
    """Combos encadenados proveedor/modelo con texto editable.

    Expone la misma API que un QComboBox (addItems, currentText,
    setCurrentText, clear, blockSignals) pero con dos coopos que devuelven
    siempre 'proveedor/modelo'.
    """

    currentTextChanged = Signal(str)

    def __init__(self, modelos, parent=None):
        super().__init__(parent)
        self._modelos = list(modelos)
        self._mapeo = {}

        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        self.cmb_proveedor = QComboBox()
        self.cmb_proveedor.setEditable(True)
        self.cmb_modelo = QComboBox()
        self.cmb_modelo.setEditable(True)
        h.addWidget(self.cmb_proveedor, 2)
        h.addWidget(QLabel("/"))
        h.addWidget(self.cmb_modelo, 3)

        self.cmb_proveedor.currentTextChanged.connect(self._proveedor_cambiado)
        self.cmb_modelo.currentTextChanged.connect(self._emitir)
        self.cmb_modelo.editTextChanged.connect(self._emitir)

        for modelo in self._modelos:
            if "/" in modelo:
                prov, idm = modelo.split("/", 1)
                self._mapeo.setdefault(prov, []).append(idm)
        self._rellenar_proveedores()

    def _rellenar_proveedores(self):
        self.cmb_proveedor.blockSignals(True)
        self.cmb_proveedor.clear()
        todos = list(PROVEEDORES)
        for prov in self._mapeo:
            if prov not in todos:
                todos.append(prov)
        self.cmb_proveedor.addItems(todos)
        self.cmb_proveedor.blockSignals(False)

    def _proveedor_cambiado(self, prov):
        prov = (prov or "").strip()
        self.cmb_modelo.blockSignals(True)
        self.cmb_modelo.clear()
        if prov in self._mapeo:
            self.cmb_modelo.addItems(self._mapeo[prov])
        self.cmb_modelo.blockSignals(False)
        self.currentTextChanged.emit(self.currentText())

    def _emitir(self, _=None):
        self.currentTextChanged.emit(self.currentText())

    def addItems(self, modelos):
        self.cmb_modelo.blockSignals(True)
        self.cmb_modelo.clear()
        self.cmb_modelo.blockSignals(False)
        self._modelos = list(modelos)
        self._mapeo = {}
        for modelo in modelos:
            if "/" in modelo:
                prov, idm = modelo.split("/", 1)
                self._mapeo.setdefault(prov, []).append(idm)
        self._rellenar_proveedores()

    def clear(self):
        self.cmb_proveedor.blockSignals(True)
        self.cmb_modelo.blockSignals(True)
        self.cmb_proveedor.clear()
        self.cmb_modelo.clear()
        self.blockSignals()
        self._modelos = []
        self._mapeo = {}
        self.cmb_proveedor.blockSignals(False)
        self.cmb_modelo.blockSignals(False)

    def blockSignals(self, bloqueado):
        super().blockSignals(bloqueado)
        self.cmb_proveedor.blockSignals(bloqueado)
        self.cmb_modelo.blockSignals(bloqueado)

    def currentText(self):
        prov = (self.cmb_proveedor.currentText() or "").strip()
        idm = (self.cmb_modelo.currentText() or "").strip()
        if not prov:
            return ""
        if not idm:
            return prov
        if "/" in self.cmb_modelo.currentText():
            return self.cmb_modelo.currentText().strip()
        return f"{prov}/{idm}"

    def setCurrentText(self, valor):
        valor = (valor or "").strip()
        self.cmb_proveedor.blockSignals(True)
        self.cmb_modelo.blockSignals(True)
        if valor:
            if "/" in valor:
                prov, idm = valor.split("/", 1)
            else:
                prov, idm = valor, ""
            self.cmb_proveedor.setCurrentText(prov)
            if prov in self._mapeo:
                self.cmb_modelo.clear()
                self.cmb_modelo.addItems(self._mapeo[prov])
                self.cmb_modelo.setCurrentText(idm)
            else:
                self.cmb_modelo.clear()
                self.cmb_modelo.setCurrentText(idm)
        self.cmb_proveedor.blockSignals(False)
        self.cmb_modelo.blockSignals(False)
        self.currentTextChanged.emit(self.currentText())