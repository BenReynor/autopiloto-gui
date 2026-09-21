"""Selector de modelo IA en dos niveles: proveedor -> modelo.

Al elegir un proveedor (opencode, google, openai, anthropic...) el combo de
modelos se rellena con la lista real de modelos de esa empresa. Todo por
selección, sin escribir: los catálogos vienen de `opencode models` (cuando el
proveedor tiene credenciales) o de models.dev.

Diseño: mantiene un catálogo local {proveedor: [modelos]}. Las consultas en
vivo solo ocurren la primera vez que se pide un proveedor (y el resto del
paquete las cachea por sesión), así el refresco de la GUI es ligero.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QWidget

from . import modelos


class SelectorModelo(QWidget):
    """Combos encadenados proveedor/modelo, ambos de selección.

    Expone API parecida a un QComboBox (addItems, currentText, setCurrentText,
    clear, blockSignals) pero devolviendo siempre 'proveedor/modelo'.
    """

    currentTextChanged = Signal(str)

    def __init__(self, proveedores=None, parent=None):
        super().__init__(parent)
        self._catalogo = {}
        self._proveedores_inicial = proveedores

        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        self.cmb_proveedor = QComboBox()
        self.cmb_modelo = QComboBox()
        h.addWidget(self.cmb_proveedor, 2)
        h.addWidget(QLabel("/"))
        h.addWidget(self.cmb_modelo, 3)

        self.cmb_proveedor.currentTextChanged.connect(self._cargar_modelos)
        self.cmb_modelo.currentTextChanged.connect(self._emitir)
        self._refrescar_proveedores()

    def activar_catalogo_global(self):
        """Usa el catálogo global detectado en vez de la lista inicial."""
        self._proveedores_inicial = None
        self._refrescar_proveedores()

    # ---------- API parecida a QComboBox ----------

    def addItems(self, etiquetas=None):
        """Incorpora una lista 'proveedor/modelo' al catálogo local."""
        for m in etiquetas or []:
            if "/" in m:
                prov, modelo = m.split("/", 1)
                self._catalogo.setdefault(prov, [])
                if modelo not in self._catalogo[prov]:
                    self._catalogo[prov].append(modelo)
        self._refrescar_proveedores()

    def clear(self):
        self._catalogo = {}
        self.cmb_proveedor.blockSignals(True)
        self.cmb_modelo.blockSignals(True)
        self.cmb_proveedor.clear()
        self.cmb_modelo.clear()
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

    # ---------- Internos ----------

    def _emitir(self, _=None):
        self.currentTextChanged.emit(self.currentText())

    def _refrescar_proveedores(self):
        fuentes = set(self._catalogo)
        if self._proveedores_inicial is not None:
            fuentes |= set(self._proveedores_inicial)
        else:
            fuentes |= set(modelos.nombres_proveedores())
        proveedores = sorted(fuentes)
        actual = self.cmb_proveedor.currentText()
        self.cmb_proveedor.blockSignals(True)
        self.cmb_proveedor.clear()
        self.cmb_proveedor.addItems(proveedores)
        if actual and self.cmb_proveedor.findText(actual) >= 0:
            self.cmb_proveedor.setCurrentText(actual)
        self.cmb_proveedor.blockSignals(False)
        self._cargar_modelos(self.cmb_proveedor.currentText())

    def _cargar_modelos(self, prov):
        prov = (prov or "").strip()
        lista = self._catalogo.get(prov)
        if lista is None:
            lista = modelos.lista_modelos_proveedor(prov)
            self._catalogo[prov] = lista
        actual = self.cmb_modelo.currentText()
        self.cmb_modelo.blockSignals(True)
        self.cmb_modelo.clear()
        self.cmb_modelo.addItems(lista)
        if actual and self.cmb_modelo.findText(actual) >= 0:
            self.cmb_modelo.setCurrentText(actual)
        self.cmb_modelo.blockSignals(False)
        if not self.signalsBlocked():
            self._emitir()
