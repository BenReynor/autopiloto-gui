"""Selector de modelo IA en dos niveles: proveedor -> modelo.

Al elegir un proveedor (opencode, google, openai, anthropic...) el combo de
modelos se rellena con la lista real de modelos de esa empresa. Todo por
selección, sin escribir: los catálogos vienen de `opencode models` (cuando el
proveedor tiene credenciales) o de models.dev.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget, QComboBox

from . import modelos


class SelectorModelo(QWidget):
    """Combos encadenados proveedor/modelo, ambos de selección.

    Expone API parecida a un QComboBox (addItems, currentText, setCurrentText,
    clear, blockSignals) pero devolviendo siempre 'proveedor/modelo'.
    """

    currentTextChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mapa = {}

        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        self.cmb_proveedor = QComboBox()
        self.cmb_modelo = QComboBox()
        h.addWidget(self.cmb_proveedor, 2)
        h.addWidget(QLabel("/"))
        h.addWidget(self.cmb_modelo, 3)

        self.cmb_proveedor.currentTextChanged.connect(self._cargar_modelos)
        self.cmb_modelo.currentTextChanged.connect(self._emitir)
        self._cargar_proveedores()

    def _emitir(self, _=None):
        self.currentTextChanged.emit(self.currentText())

    def _cargar_proveedores(self):
        proveedores = modelos.nombres_proveedores()
        self.cmb_proveedor.blockSignals(True)
        actual_prov = self.cmb_proveedor.currentText()
        self.cmb_proveedor.clear()
        self.cmb_proveedor.addItems(proveedores)
        if actual_prov and self.cmb_proveedor.findText(actual_prov) >= 0:
            self.cmb_proveedor.setCurrentText(actual_prov)
        self.cmb_proveedor.blockSignals(False)
        self._cargar_modelos(self.cmb_proveedor.currentText())

    def addItems(self, modelos_prov=None):
        self._cargar_proveedores()
        lista = [m.split("/", 1)[1] for m in (modelos_prov or []) if "/" in m]
        self._mapa = {}
        if lista:
            self._mapa[self.cmb_proveedor.currentText()] = lista

    def _cargar_modelos(self, prov):
        prov = (prov or "").strip()
        self.cmb_modelo.blockSignals(True)
        self.cmb_modelo.clear()
        lista = self._mapa.get(prov)
        if lista is None:
            lista = modelos.lista_modelos_proveedor(prov)
            self._mapa[prov] = lista
        if lista:
            self.cmb_modelo.addItems(lista)
        self.cmb_modelo.blockSignals(False)
        self._emitir()

    def clear(self):
        self.cmb_proveedor.blockSignals(True)
        self.cmb_modelo.blockSignals(True)
        self.cmb_proveedor.clear()
        self.cmb_modelo.clear()
        self.blockSignals()
        self._mapa = {}
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
        if "/" in idm and not idm.startswith(prov + "/"):
            return idm
        return f"{prov}/{idm}"

    def setCurrentText(self, valor):
        valor = (valor or "").strip()
        self.blockSignals(True)
        if valor:
            if "/" in valor:
                prov, idm = valor.split("/", 1)
            else:
                prov, idm = valor, ""
            self.cmb_proveedor.setCurrentText(prov)
            if idm:
                self._cargar_modelos(prov)
                self.cmb_modelo.setCurrentText(idm)
        self.blockSignals(False)
        self._emitir()