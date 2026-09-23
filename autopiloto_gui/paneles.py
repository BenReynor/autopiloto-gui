"""Widgets de las pestañas del panel y el aviso de sobrecalentamiento.

Cada clase construye su UI y expone señales/métodos; la ventana (app.py) solo
orquesta: conecta señales, gestiona procesos y actualiza estado.
"""

import os
import re
import subprocess

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import configuracion as cfg
from . import plan
from .modelos import PROVEEDORES_CATALOGO
from .paneles_webhooks import PanelWebhooks
from .proceso import PanelTarea, Trabajo
from .selector_modelo import SelectorModelo


def _fuente_monospace(objeto):
    from PySide6.QtGui import QFont
    fuente = QFont(objeto.font())
    fuente.setFamily(cfg.FUENTE_MONO)
    objeto.setFont(fuente)


def _fuente_ui(objeto):
    from PySide6.QtGui import QFont
    fuente = QFont(objeto.font())
    fuente.setFamily(cfg.FUENTE_UI)
    objeto.setFont(fuente)


def _numero(texto, defv, tipo=float, minimo=None):
    """Parsea un texto numérico tolerante (ignora caracteres extraños)."""
    try:
        valor = tipo(re.sub(r"[^\d.-]", "", texto or "").strip() or defv)
    except ValueError:
        valor = defv
    if minimo is not None:
        valor = max(minimo, valor)
    return valor


class _LabelMuted(QLabel):
    """Label con color de texto secundario."""
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setProperty("status", "muted")


class _LabelStatus(QLabel):
    """Label con estado semántico (success/warning/error/info)."""
    def __init__(self, text="", status="info", parent=None):
        super().__init__(text, parent)
        self.setProperty("status", status)


class _BtnPrimary(QPushButton):
    """Botón principal (acción principal)."""
    def __init__(self, text, parent=None):
        super().__init__(text, parent)


class _BtnGhost(QPushButton):
    """Botón secundario (ghost)."""
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setProperty("ghost", True)


class _BtnDanger(QPushButton):
    """Botón destructivo (danger)."""
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setProperty("danger", True)


class AvisoTemperatura(QDialog):
    """Aviso de sobrecalentamiento con cuenta regresiva.

    Si nadie toca los botones antes de que llegue a 0, apaga la aplicación.
    """

    def __init__(self, temp, segundos, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚠ PC demasiado caliente")
        self.setModal(True)
        self._segundos = max(1, int(segundos))
        self._restante = self._segundos
        self._apagar = None

        v = QVBoxLayout(self)
        v.setSpacing(16)
        v.setContentsMargins(24, 24, 24, 24)

        self.lbl_temp = QLabel(f"⚠ Temperatura crítica: <b>{temp} °C</b>")
        self.lbl_temp.setWordWrap(True)
        v.addWidget(self.lbl_temp)

        self.lbl_conteo = QLabel(
            f"La aplicación se apagará en <b>{self._restante}</b> s.")
        v.addWidget(self.lbl_conteo)

        h = QHBoxLayout()
        h.setSpacing(12)
        b_continuar = _BtnPrimary("Continuar")
        b_continuar.clicked.connect(self._continuar)
        b_apagar = _BtnDanger("Apagar ahora")
        b_apagar.clicked.connect(self._apagar_ahora)
        h.addWidget(b_continuar)
        h.addWidget(b_apagar)
        v.addLayout(h)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)

    def _tick(self):
        self._restante -= 1
        if self._restante <= 0:
            self.timer.stop()
            self._apagar = True
            self.accept()
        else:
            self.lbl_conteo.setText(
                f"La aplicación se apagará en <b>{self._restante}</b> s.")

    def _continuar(self):
        self.timer.stop()
        self._apagar = False
        self.accept()

    def _apagar_ahora(self):
        self.timer.stop()
        self._apagar = True
        self.accept()

    @property
    def apagar(self):
        return self._apagar is True


class KanbanWidget(QWidget):
    """Vista Kanban de tareas: 3 columnas (Pendiente, Hecha, Bloqueada)."""

    tarea_seleccionada = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._plan = None

        h = QHBoxLayout(self)
        h.setSpacing(8)
        h.setContentsMargins(0, 0, 0, 0)

        self.col_pend = self._crear_columna("Pendientes", "#3b82f6")
        self.col_hecha = self._crear_columna("Hechas", "#22c55e")
        self.col_bloq = self._crear_columna("Bloqueadas", "#ef4444")

        h.addWidget(self.col_pend, 1)
        h.addWidget(self.col_hecha, 1)
        h.addWidget(self.col_bloq, 1)

    def _crear_columna(self, titulo, color_acento):
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setProperty("class", "kanban-col")
        frame.setStyleSheet("""
            QFrame[class="kanban-col"] {
                background-color: transparent;
                border-radius: 8px;
                border: 1px solid transparent;
            }
        """)
        v = QVBoxLayout(frame)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(8)

        # Header con título + contador
        header = QHBoxLayout()
        header.setSpacing(8)
        lbl = QLabel(titulo)
        lbl.setStyleSheet(f"color: {color_acento}; font-weight: 600; font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase;")
        header.addWidget(lbl)
        header.addStretch()
        badge = QLabel("0")
        badge.setProperty("class", "kanban-badge")
        badge.setStyleSheet(f"""
            QLabel[class="kanban-badge"] {{
                background: {color_acento};
                color: white;
                font-size: 10px;
                font-weight: 600;
                padding: 2px 6px;
                border-radius: 10px;
                min-width: 18px;
                text-align: center;
            }}
        """)
        badge.setAlignment(Qt.AlignCenter)
        header.addWidget(badge)
        frame.header_layout = header
        frame.badge = badge
        v.addLayout(header)

        lista = QListWidget()
        lista.setSelectionMode(QAbstractItemView.SingleSelection)
        lista.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lista.setStyleSheet(f"""
            QListWidget {{
                background: transparent;
                border: 1px solid {color_acento}40;
                border-radius: 6px;
                outline: none;
            }}
            QListWidget::item {{
                background: palette(base);
                border: 1px solid palette(mid);
                border-radius: 4px;
                padding: 8px 10px;
                margin: 2px;
                color: palette(text);
            }}
            QListWidget::item:selected {{
                background: palette(highlight);
                color: palette(highlighted-text);
                border-color: palette(highlight);
            }}
            QListWidget::item:hover:!selected {{
                background: palette(alternate-base);
            }}
        """)
        lista.itemClicked.connect(lambda item: self.tarea_seleccionada.emit(item.text()))
        v.addWidget(lista, 1)

        frame.lista = lista
        frame.color_acento = color_acento
        return frame

    def cargar(self, plan_obj):
        self._plan = plan_obj
        self._actualizar()

    def _actualizar(self):
        for col in (self.col_pend, self.col_hecha, self.col_bloq):
            col.lista.clear()
            col.badge.setText("0")
        if not self._plan:
            return
        pend = hecha = bloq = 0
        for t in self._plan.tareas:
            item = QListWidgetItem(t["texto"])
            item.setToolTip(f"Línea {t['linea']}")
            # Estados visuales
            if t["estado"] == "pendiente":
                self.col_pend.lista.addItem(item)
                pend += 1
            elif t["estado"] == "hecha":
                # Tachado visual
                font = item.font()
                font.setStrikeOut(True)
                item.setFont(font)
                item.setForeground(Qt.gray)
                self.col_hecha.lista.addItem(item)
                hecha += 1
            elif t["estado"] == "bloqueada":
                # Rojo + negrita
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                item.setForeground(Qt.red)
                self.col_bloq.lista.addItem(item)
                bloq += 1
        # Actualizar badges
        self.col_pend.badge.setText(str(pend))
        self.col_hecha.badge.setText(str(hecha))
        self.col_bloq.badge.setText(str(bloq))

    def clear(self):
        for col in (self.col_pend, self.col_hecha, self.col_bloq):
            col.lista.clear()
            col.badge.setText("0")


class PanelPlan(QWidget):
    """Editor de plan.md con contador de tareas y vista Kanban."""

    guardado = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._plan = None
        self._modificado = False
        self._huella_guardada = None

        v = QVBoxLayout(self)
        v.setSpacing(8)
        v.setContentsMargins(0, 0, 0, 0)

        self.lbl_conteo = _LabelMuted("")
        v.addWidget(self.lbl_conteo)

        # Splitter: Kanban arriba, editor abajo
        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.setHandleWidth(4)
        self.splitter.setChildrenCollapsible(False)

        self.kanban = KanbanWidget()
        self.kanban.tarea_seleccionada.connect(self._en_editor_seleccionar)
        self.splitter.addWidget(self.kanban)

        self.editor = QPlainTextEdit()
        _fuente_monospace(self.editor)
        self.editor.textChanged.connect(self._actualizar_conteo)
        self.splitter.addWidget(self.editor)
        self.splitter.setSizes([200, 400])
        v.addWidget(self.splitter, 1)

        h = QHBoxLayout()
        h.setSpacing(8)
        b_recargar = _BtnGhost("Recargar")
        b_recargar.clicked.connect(lambda: self.cargar())
        b_guardar = _BtnPrimary("Guardar plan.md")
        b_guardar.clicked.connect(self.guardar)
        h.addStretch()
        h.addWidget(b_recargar)
        h.addWidget(b_guardar)
        v.addLayout(h)

    def _en_editor_seleccionar(self, texto):
        """Scroll al editor a la línea de la tarea seleccionada en Kanban."""
        if not self._plan:
            return
        for i, linea in enumerate(self.editor.toPlainText().splitlines(), 1):
            if texto in linea:
                cursor = self.editor.textCursor()
                cursor.movePosition(cursor.Start)
                for _ in range(i - 1):
                    cursor.movePosition(cursor.Down)
                self.editor.setTextCursor(cursor)
                self.editor.ensureCursorVisible()
                break

    def cargar(self, ruta=None):
        if ruta is not None:
            self._plan = plan.Plan(ruta) if ruta else None
        if not self._plan:
            self.clear()
            return
        if not self._plan.existe():
            self.editor.setPlainText("# PLAN\n\n- [ ] tu primera tarea — criterio: ...\n")
            self.lbl_conteo.setText("plan.md no existe aún")
            self.kanban.clear()
            self._modificado = False
            self._huella_guardada = None
            return
        self.editor.setPlainText(self._plan.cargar())
        self.kanban.cargar(self._plan)
        self._modificado = False
        self._huella_guardada = self._huella_plan()

    def _huella_plan(self):
        """(mtime, tamaño) del plan.md en disco; None si no se puede leer."""
        if not self._plan:
            return None
        try:
            return (os.path.getmtime(self._plan.ruta),
                    os.path.getsize(self._plan.ruta))
        except OSError:
            return None

    def _recargar_si_cambio(self):
        """Recarga plan.md si cambió en disco; nunca pisa ediciones sin guardar."""
        if not self._plan or self._modificado:
            return
        huella = self._huella_plan()
        if huella is None or huella == self._huella_guardada:
            return
        self.editor.setPlainText(self._plan.cargar())
        self.kanban.cargar(self._plan)
        self._modificado = False
        self._huella_guardada = huella
        self.guardado.emit(self._plan.ruta)

    def guardar(self):
        if not self._plan:
            return
        self._plan.guardar(self.editor.toPlainText())
        self.lbl_conteo.setText(
            f"plan.md guardado ({self._plan.ruta})")
        self.kanban.cargar(self._plan)
        self._modificado = False
        self._huella_guardada = self._huella_plan()
        self.guardado.emit(self._plan.ruta)

    def clear(self):
        self.editor.clear()
        self.lbl_conteo.setText("")
        self.kanban.clear()

    def _actualizar_conteo(self):
        if not self._plan:
            return
        self._plan.texto = self.editor.toPlainText()
        self._modificado = True
        pend, hecho, bloqueada = self._plan.conteo()
        self.lbl_conteo.setText(
            f"Pendientes: {pend}   ·   Hechas: {hecho}   ·   "
            f"Bloqueadas: {bloqueada}")
        self.kanban._actualizar()


class PanelLecciones(QWidget):
    """Memoria del proyecto (lecciones.md): editor + nueva lección + auto-recarga.

    El contenido se inyecta al agente en cada tarea (corrección única de
    errores); el autopiloto también añade lecciones al bloquear tareas.
    """

    guardado = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ruta = None
        self._modificado = False
        self._huella_guardada = None

        v = QVBoxLayout(self)
        v.setSpacing(8)
        v.setContentsMargins(0, 0, 0, 0)

        h = QHBoxLayout()
        lbl = QLabel("🧠 Memoria del proyecto")
        _fuente_ui(lbl)
        lbl.setStyleSheet("font-weight: 600; font-size: 13px;")
        h.addWidget(lbl)
        self.lbl_estado = _LabelMuted("")
        h.addWidget(self.lbl_estado)
        h.addStretch()
        self.lbl_apunte = _LabelMuted(
            "Se inyecta al agente antes de cada tarea; añade una entrada automática "
            "al bloquear una tarea.")
        h.addWidget(self.lbl_apunte)
        v.addLayout(h)

        self.editor = QPlainTextEdit()
        _fuente_monospace(self.editor)
        self.editor.textChanged.connect(self._marcar_modificado)
        v.addWidget(self.editor, 1)

        h = QHBoxLayout()
        h.setSpacing(8)
        b_nueva = _BtnPrimary("＋ Nueva lección")
        b_nueva.clicked.connect(self._nueva_leccion)
        b_recargar = _BtnGhost("Recargar")
        b_recargar.clicked.connect(lambda: self.cargar())
        b_guardar = _BtnGhost("Guardar lecciones.md")
        b_guardar.clicked.connect(self.guardar)
        h.addWidget(b_nueva)
        h.addStretch()
        h.addWidget(b_recargar)
        h.addWidget(b_guardar)
        v.addLayout(h)

    def _marcar_modificado(self):
        if self._ruta:
            self._modificado = True

    def _nueva_leccion(self):
        """Añade una plantilla de lección al final del editor y la enfoca."""
        from datetime import datetime
        bloque = (
            f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')} — Título breve de la lección\n"
            "- Síntoma: qué falló.\n"
            "- Causa: por qué falló.\n"
            "- Prevención: qué hacer para no repetirlo.\n"
        )
        texto = self.editor.toPlainText()
        if texto and not texto.endswith("\n"):
            bloque = "\n" + bloque
        self.editor.appendPlainText(bloque.strip("\n"))
        cursor = self.editor.textCursor()
        cursor.movePosition(cursor.End)
        self.editor.setTextCursor(cursor)
        self.editor.ensureCursorVisible()
        self._modificado = True

    def cargar(self, ruta=None):
        if ruta is not None:
            self._ruta = ruta or None
        if not self._ruta:
            self.editor.clear()
            self.lbl_estado.setText("")
            return
        if not os.path.isfile(self._ruta):
            self.editor.setPlainText("# Lecciones aprendidas — memoria del proyecto\n\n")
            self.lbl_estado.setText("lecciones.md no existe aún")
            self._modificado = False
            self._huella_guardada = None
            return
        with open(self._ruta, encoding="utf-8", errors="replace") as f:
            self.editor.setPlainText(f.read())
        self._modificado = False
        self._huella_guardada = self._huella()
        self.lbl_estado.setText(self._ruta)

    def _huella(self):
        if not self._ruta:
            return None
        try:
            return (os.path.getmtime(self._ruta), os.path.getsize(self._ruta))
        except OSError:
            return None

    def _recargar_si_cambio(self):
        """Recarga lecciones.md si cambió en disco; nunca pisa ediciones sin guardar."""
        if not self._ruta or self._modificado:
            return
        huella = self._huella()
        if huella is None or huella == self._huella_guardada:
            return
        with open(self._ruta, encoding="utf-8", errors="replace") as f:
            self.editor.setPlainText(f.read())
        self._modificado = False
        self._huella_guardada = huella
        self.lbl_estado.setText(f"🔄 recargado ({self._ruta})")

    def guardar(self):
        if not self._ruta:
            return
        with open(self._ruta, "w", encoding="utf-8") as f:
            f.write(self.editor.toPlainText())
        self._modificado = False
        self._huella_guardada = self._huella()
        self.lbl_estado.setText(f"lecciones.md guardado ({self._ruta})")
        self.guardado.emit(self._ruta)


class PanelRevision(QWidget):
    """Panel para revisar diff antes de commitear: muestra diff, botones Aprobar/Rechazar."""

    aprobado = Signal()
    rechazado = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ruta_proyecto = None
        self._archivo_diff = None
        self._archivo_senal = None

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        # Header
        h = QHBoxLayout()
        h.setSpacing(8)
        self.lbl_titulo = QLabel("⏸ Revisión pendiente")
        _fuente_ui(self.lbl_titulo)
        self.lbl_titulo.setStyleSheet("font-weight: 600; font-size: 13px;")
        h.addWidget(self.lbl_titulo)
        h.addStretch()
        self.lbl_tarea = _LabelMuted("")
        h.addWidget(self.lbl_tarea)
        v.addLayout(h)

        # Diff viewer
        self.txt_diff = QPlainTextEdit()
        self.txt_diff.setReadOnly(True)
        _fuente_monospace(self.txt_diff)
        v.addWidget(self.txt_diff, 1)

        # Botones
        h = QHBoxLayout()
        h.setSpacing(8)
        self.b_aprobar = _BtnPrimary("✓ Aprobar y commitear")
        self.b_aprobar.clicked.connect(self._emitir_aprobado)
        self.b_rechazar = _BtnDanger("✗ Rechazar y reintentar")
        self.b_rechazar.clicked.connect(self._pedir_motivo_rechazo)
        h.addWidget(self.b_aprobar)
        h.addWidget(self.b_rechazar)
        v.addLayout(h)

        self.setVisible(False)

    def mostrar_revision(self, ruta_proyecto, tarea, archivo_diff, archivo_senal):
        self._ruta_proyecto = ruta_proyecto
        self._archivo_diff = archivo_diff
        self._archivo_senal = archivo_senal
        self.lbl_tarea.setText(f"Tarea: {tarea}")
        try:
            with open(archivo_diff, encoding="utf-8") as f:
                self.txt_diff.setPlainText(f.read())
        except OSError:
            self.txt_diff.setPlainText("(no se pudo leer el diff)")
        self.setVisible(True)

    def ocultar(self):
        self.setVisible(False)
        self._archivo_diff = None
        self._archivo_senal = None

    def _emitir_aprobado(self):
        if self._archivo_senal:
            try:
                with open(self._archivo_senal, "w") as f:
                    f.write("APPROVE\n")
            except OSError:
                pass
        self.aprobado.emit()
        self.ocultar()

    def _pedir_motivo_rechazo(self):
        motivo, ok = QInputDialog.getMultiLineText(
            self, "Motivo del rechazo",
            "Explica qué debe corregir el agente (se inyectará en el siguiente intento):")
        if ok and motivo.strip():
            if self._archivo_senal:
                try:
                    with open(self._archivo_senal, "w") as f:
                        f.write(f"REJECT\n{motivo.strip()}\n")
                except OSError:
                    pass
            self.rechazado.emit(motivo.strip())
            self.ocultar()


class PanelEjecucion(QWidget):
    """Opciones de lanzamiento, control del loop y salida en vivo."""

    iniciar = Signal()
    detener = Signal()
    gate = Signal()
    modelos_modificados = Signal()
    refrescar_modelos = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # Scroll interno: las opciones se reajustan (y se pueden desplazar) si
        # la ventana es baja; con altura suficiente ocupan todo el ancho.
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        contenido = QWidget()
        contenido.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        scroll.setWidget(contenido)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.addWidget(scroll)

        v = QVBoxLayout(contenido)
        v.setSpacing(8)
        v.setContentsMargins(0, 0, 0, 0)

        # ===== ZONA 1: OPCIONES DE LANZAMIENTO =====
        grupo = QGroupBox("Opciones de lanzamiento")
        g = QGridLayout(grupo)
        g.setSpacing(8)
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(8)
        g.setContentsMargins(12, 12, 12, 12)

        def add_field(row, label_text, widget, placeholder=""):
            lbl = QLabel(label_text)
            _fuente_ui(lbl)
            g.addWidget(lbl, row, 0)
            if placeholder:
                widget.setPlaceholderText(placeholder)
            g.addWidget(widget, row, 1)

        def contenedor_agente(selector):
            """Fila agente=combo CLI + selector de modelo en un mismo widget."""
            h = QHBoxLayout()
            h.setSpacing(8)
            cmb_cli = QComboBox()
            cmb_cli.addItems(cfg.AGENTES_DISPONIBLES)
            cmb_cli.setCurrentText(cfg.AGENTE_DEFECTO)
            cmb_cli.setMinimumWidth(118)
            h.addWidget(cmb_cli, 0)
            h.addWidget(selector, 1)
            w = QWidget()
            w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            w.setLayout(h)
            return w, cmb_cli

        add_field(0, "Hasta (HH:MM, vacío = sin límite):",
                  self._crear_lineedit(cfg.LAUNCH_DEFECTO["hasta"], "22:00"))
        self.txt_hasta = g.itemAtPosition(0, 1).widget()

        add_field(1, "Máx iteraciones:",
                  self._crear_lineedit(str(cfg.LAUNCH_DEFECTO["iteraciones"])))
        self.txt_iter = g.itemAtPosition(1, 1).widget()

        self.cmb_padre = QComboBox()
        self.cmb_padre.setEditable(True)
        self.cmb_padre.setInsertPolicy(QComboBox.NoInsert)
        self.cmb_padre.setPlaceholderText(cfg.LAUNCH_DEFECTO["padre"] or "rama base")
        add_field(2, "Padre (rama base):", self.cmb_padre)
        self.cmb_padre.setCurrentText(cfg.LAUNCH_DEFECTO["padre"])
        self.cmb_padre.currentTextChanged.connect(self.modelos_modificados)

        w_agente, self.cmb_agente_cli = contenedor_agente(
            SelectorModelo(proveedores=PROVEEDORES_CATALOGO))
        add_field(3, "Agente + Modelo (tarea):", w_agente)
        self.cmb_agente = g.itemAtPosition(3, 1).widget().layout().itemAt(1).widget()
        self.cmb_agente.currentTextChanged.connect(self.modelos_modificados)
        self.cmb_agente_cli.currentTextChanged.connect(self.modelos_modificados)

        w_revisor, self.cmb_revisor_cli = contenedor_agente(
            SelectorModelo(proveedores=PROVEEDORES_CATALOGO))
        add_field(4, "Agente + Modelo (revisor):", w_revisor)
        self.cmb_revisor = g.itemAtPosition(4, 1).widget().layout().itemAt(1).widget()
        self.cmb_revisor.currentTextChanged.connect(self.modelos_modificados)
        self.cmb_revisor_cli.currentTextChanged.connect(self.modelos_modificados)

        # Proyecto a trabajar (rama destino del trabajo; editable: permite
        # escribir una rama aún inexistente, NoInsert).
        self.cmb_trabajo = QComboBox()
        self.cmb_trabajo.setEditable(True)
        self.cmb_trabajo.setInsertPolicy(QComboBox.NoInsert)
        self.cmb_trabajo.setPlaceholderText(
            cfg.LAUNCH_DEFECTO["padre"] or "rama del trabajo")
        add_field(5, "Proyecto a trabajar (rama):", self.cmb_trabajo)
        self.cmb_trabajo.setCurrentText(cfg.LAUNCH_DEFECTO["trabajo"])
        self.cmb_trabajo.currentTextChanged.connect(self.modelos_modificados)

        # Navigator
        self.chk_nav = QCheckBox(
            "🔍 Navigator automático (busca contexto antes de cada tarea)")
        self.chk_nav.setChecked(cfg.NAVEGADOR_DEFECTO)
        g.addWidget(self.chk_nav, 6, 0, 1, 2)

        add_field(7, "Modelo (navegador):",
                  SelectorModelo(proveedores=PROVEEDORES_CATALOGO))
        self.cmb_nav = g.itemAtPosition(7, 1).widget()
        self.cmb_nav.currentTextChanged.connect(self.modelos_modificados)

        b_modelos = _BtnGhost("↻ Refrescar modelos")
        b_modelos.clicked.connect(self.refrescar_modelos)
        g.addWidget(b_modelos, 8, 0, 1, 2)

        self.lbl_net = _LabelStatus("", "info")
        g.addWidget(self.lbl_net, 9, 0, 1, 2)

        self.lbl_modelos = _LabelMuted("")
        g.addWidget(self.lbl_modelos, 10, 0, 1, 2)

        self.chk_dual = QCheckBox(
            "Gate dual: el revisor exige VERDICT: PASS antes del commit")
        self.chk_dual.setChecked(cfg.LAUNCH_DEFECTO["dual"])
        g.addWidget(self.chk_dual, 11, 0, 1, 2)

        self.chk_voz = QCheckBox(
            "Alertas de voz al bloquear/terminar (notify-send/spd-say)")
        self.chk_voz.setChecked(cfg.LAUNCH_DEFECTO["voz"])
        g.addWidget(self.chk_voz, 12, 0, 1, 2)

        add_field(13, "Presupuesto máx (USD, 0 = sin límite):",
                  self._crear_lineedit(str(cfg.LAUNCH_DEFECTO["costo_max"])))
        self.txt_costo_max = g.itemAtPosition(13, 1).widget()

        add_field(14, "Costo estimado por tarea (USD):",
                  self._crear_lineedit(str(cfg.LAUNCH_DEFECTO["costo_iter"])))
        self.txt_costo_iter = g.itemAtPosition(14, 1).widget()

        self.chk_push = QCheckBox("--push al final")
        self.chk_push.setChecked(cfg.LAUNCH_DEFECTO["push"])
        g.addWidget(self.chk_push, 15, 0, 1, 2)

        self.chk_revision_manual = QCheckBox(
            "Revisar diff manualmente antes de cada commit (pausa el loop)")
        self.chk_revision_manual.setChecked(False)
        g.addWidget(self.chk_revision_manual, 16, 0, 1, 2)

        v.addWidget(grupo)

        # ===== BOTONES DE CONTROL =====
        h_ctrl = QHBoxLayout()
        h_ctrl.setSpacing(8)
        self.b_iniciar = _BtnPrimary("▶ Iniciar loop")
        self.b_iniciar.clicked.connect(self.iniciar)
        self.b_detener = _BtnDanger("■ Detener")
        self.b_detener.clicked.connect(self.detener)
        self.b_detener.setEnabled(False)
        self.b_gate = _BtnGhost("Ejecutar gate.sh")
        self.b_gate.clicked.connect(self.gate)
        h_ctrl.addWidget(self.b_iniciar)
        h_ctrl.addWidget(self.b_detener)
        h_ctrl.addWidget(self.b_gate)
        h_ctrl.addStretch()
        v.addLayout(h_ctrl)

        # Panel de revisión de diff (oculto por defecto)
        self.panel_revision = PanelRevision()
        self.panel_revision.setVisible(False)
        v.addWidget(self.panel_revision)

    def _crear_lineedit(self, texto, placeholder=""):
        le = QLineEdit(texto)
        le.setPlaceholderText(placeholder)
        _fuente_ui(le)
        return le

    def actualizar_ramas(self, ruta):
        """Rellena los combos 'Padre' y 'Proyecto a trabajar' con las ramas
        reales del repo (git).

        Conserva la selección actual; permite igualmente escribir una rama
        que aún no exista (NoInsert). Ante cualquier fallo de git deja los
        combos como estaban.
        """
        if not ruta:
            return
        for cmb in (self.cmb_padre, self.cmb_trabajo):
            actual = cmb.currentText()
            ramas = []
            try:
                out = subprocess.run(
                    ["git", "-C", ruta, "for-each-ref",
                     "--format=%(refname:short)", "refs/heads"],
                    capture_output=True, text=True, timeout=6)
                if out.returncode == 0:
                    ramas = [r for r in out.stdout.splitlines() if r.strip()]
            except (OSError, subprocess.SubprocessError):
                ramas = []
            cmb.blockSignals(True)
            cmb.clear()
            cmb.addItems(ramas)
            if actual:
                cmb.setCurrentText(actual)
            cmb.blockSignals(False)

    # ---------- API para la ventana ----------

    def config(self):
        return {
            "hasta": self.txt_hasta.text().strip(),
            "padre": self.cmb_padre.currentText().strip(),
            "trabajo": self.cmb_trabajo.currentText().strip(),
            "push": self.chk_push.isChecked(),
            "iteraciones": int(_numero(self.txt_iter.text(),
                                        cfg.LAUNCH_DEFECTO["iteraciones"],
                                        int, minimo=1)),
            "agente_cli": self.cmb_agente_cli.currentText(),
            "agente": self.cmb_agente.currentText(),
            "revisor_cli": self.cmb_revisor_cli.currentText(),
            "revisor": self.cmb_revisor.currentText(),
            "dual": self.chk_dual.isChecked(),
            "voz": self.chk_voz.isChecked(),
            "revision_manual": self.chk_revision_manual.isChecked(),
            "costo_max": _numero(self.txt_costo_max.text(),
                                 cfg.LAUNCH_DEFECTO["costo_max"], float),
            "costo_iter": _numero(self.txt_costo_iter.text(),
                                  cfg.LAUNCH_DEFECTO["costo_iter"], float),
            "nav": self.chk_nav.isChecked(),
            "nav_modelo": self.cmb_nav.currentText() if "/" in self.cmb_nav.currentText() else "",
        }

    def aplicar_config(self, conf):
        """Rellena los widgets con la configuración guardada del proyecto.

        Bloquea las señales para no disparar guardados durante la carga.
        """
        c = dict(cfg.LAUNCH_DEFECTO)
        c.update(conf or {})
        previo = self.signalsBlocked()
        self.blockSignals(True)
        self.txt_hasta.setText(c.get("hasta") or "")
        self.txt_iter.setText(str(c["iteraciones"]))
        self.cmb_padre.setCurrentText(c.get("padre") or "")
        self.cmb_trabajo.setCurrentText(c.get("trabajo") or "")
        self.cmb_agente_cli.setCurrentText(
            c.get("agente_cli") or cfg.AGENTE_DEFECTO)
        self.cmb_agente.setCurrentText(c.get("agente") or "")
        self.cmb_revisor_cli.setCurrentText(
            c.get("revisor_cli") or cfg.AGENTE_DEFECTO)
        self.cmb_revisor.setCurrentText(c.get("revisor") or "")
        self.cmb_nav.setCurrentText(c.get("nav_modelo") or "")
        self.chk_nav.setChecked(bool(c.get("nav")))
        self.chk_dual.setChecked(bool(c.get("dual")))
        self.chk_voz.setChecked(bool(c.get("voz")))
        self.chk_push.setChecked(bool(c.get("push")))
        self.chk_revision_manual.setChecked(bool(c.get("revision_manual")))
        self.txt_costo_max.setText(
            str(c.get("costo_max", cfg.LAUNCH_DEFECTO["costo_max"])))
        self.txt_costo_iter.setText(
            str(c.get("costo_iter", cfg.LAUNCH_DEFECTO["costo_iter"])))
        self.blockSignals(previo)

    def nota_net(self, ok):
        if ok is None:
            self.lbl_net.setText("Internet: ?")
            self.lbl_net.setProperty("status", "info")
        elif ok:
            self.lbl_net.setText("🟢 Internet: OK")
            self.lbl_net.setProperty("status", "success")
        else:
            self.lbl_net.setText(
                "🔴 Internet: SIN CONEXIÓN — los modelos IA no responderán; "
                "el loop no arrancará")
            self.lbl_net.setProperty("status", "error")
        self.lbl_net.style().unpolish(self.lbl_net)
        self.lbl_net.style().polish(self.lbl_net)

    def info_modelos(self, nmodelos, nprov):
        self.lbl_modelos.setText(
            f"{nmodelos} modelos · {nprov} proveedores de opencode cargados")
        # Auto-hide después de 3 segundos
        QTimer.singleShot(3000, lambda: self.lbl_modelos.clear())

    def aplicar_modelos(self, seleccion):
        self.cmb_agente.setCurrentText(seleccion.get("tarea") or "")
        self.cmb_revisor.setCurrentText(seleccion.get("revisor") or "")
        if seleccion.get("agente_cli"):
            self.cmb_agente_cli.setCurrentText(seleccion["agente_cli"])
        if seleccion.get("revisor_cli"):
            self.cmb_revisor_cli.setCurrentText(seleccion["revisor_cli"])

    def modelos_seleccion(self):
        return {
            "tarea": self.cmb_agente.currentText(),
            "revisor": self.cmb_revisor.currentText(),
            "agente_cli": self.cmb_agente_cli.currentText(),
            "revisor_cli": self.cmb_revisor_cli.currentText(),
        }

    def navegador_config(self):
        return {
            "activo": self.chk_nav.isChecked(),
            "modelo": self.cmb_nav.currentText() if "/" in self.cmb_nav.currentText() else "",
        }

    def aplicar_navegador(self, modelo: str):
        self.cmb_nav.setCurrentText(modelo)

    def agregar_catalogo(self, etiquetas):
        self.cmb_agente.addItems(etiquetas)
        self.cmb_revisor.addItems(etiquetas)
        self.cmb_nav.addItems(etiquetas)

    def establecer_running(self, corriendo):
        self.b_iniciar.setEnabled(not corriendo)
        self.b_detener.setEnabled(corriendo)

    def revision_manual_activa(self):
        return self.chk_revision_manual.isChecked()


class PanelGit(QWidget):
    """Rama, git status, últimos commits y rollback visual.

    Los comandos git se ejecutan en un hilo de fondo (Trabajo).
    """

    revertir_commit = Signal(str)  # sha

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ruta = None
        self._worker = None

        v = QVBoxLayout(self)
        v.setSpacing(8)
        v.setContentsMargins(0, 0, 0, 0)

        h = QHBoxLayout()
        h.setSpacing(8)
        self.lbl_rama = QLabel("")
        _fuente_ui(self.lbl_rama)
        self.lbl_rama.setStyleSheet("font-weight: 500;")
        b_ref = _BtnGhost("Refrescar")
        b_ref.clicked.connect(lambda: self.cargar())
        h.addWidget(self.lbl_rama)
        h.addStretch()
        h.addWidget(b_ref)
        v.addLayout(h)

        # TreeWidget para commits con botón Revertir
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["SHA", "Mensaje", "Autor", "Fecha", "Acción"])
        self.tree.setColumnWidth(0, 80)
        self.tree.setColumnWidth(1, 350)
        self.tree.setColumnWidth(2, 120)
        self.tree.setColumnWidth(3, 130)
        self.tree.setColumnWidth(4, 80)
        _fuente_monospace(self.tree)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionBehavior(QTreeWidget.SelectRows)
        v.addWidget(self.tree, 1)

    def _consulta_git(self):
        ruta = self._ruta
        if not ruta:
            return None

        def run(cmd):
            try:
                out = subprocess.run(cmd, cwd=ruta, capture_output=True,
                                     text=True, timeout=cfg.TIMEOUT_GIT)
                return out.stdout.strip()
            except Exception:
                return ""

        rama = run(["git", "branch", "--show-current"])
        status = run(["git", "status", "--short"])
        # Obtener commits de la rama autopiloto/* (último 30)
        log = run(["git", "log", "--oneline", "--all", "--grep=autopiloto:", "-30", "--format=%H|%s|%an|%ad", "--date=short"])

        return (rama, status, log)

    def _git_listo(self, datos):
        self._worker = None
        if not datos:
            return
        rama, status, log = datos
        self.lbl_rama.setText(f"Rama: {rama}" if rama else "Rama: —")

        # Limpiar árbol
        self.tree.clear()

        # Parsear log y crear items con botón revertir
        if log:
            for linea in log.splitlines():
                if not linea.strip():
                    continue
                parts = linea.split("|", 3)
                if len(parts) < 4:
                    continue
                sha, msg, autor, fecha = parts
                item = QTreeWidgetItem([sha[:8], msg, autor, fecha, ""])
                item.setData(0, Qt.UserRole, sha)  # SHA completo en role
                self.tree.addTopLevelItem(item)

                # Botón Revertir
                btn = QPushButton("↩ Revertir")
                btn.setProperty("sha", sha)
                btn.clicked.connect(lambda _, s=sha: self.revertir_commit.emit(s))
                btn.setStyleSheet("padding: 2px 8px; font-size: 11px;")
                self.tree.setItemWidget(item, 4, btn)

        # Status en tooltip del primer item o label
        if status:
            self.tree.setToolTip(f"Status:\n{status}")

    def cargar(self, ruta=None):
        if ruta is not None:
            self._ruta = ruta
        if not self._ruta:
            self.tree.clear()
            self.lbl_rama.setText("")
            return
        if self._worker and self._worker.isRunning():
            return
        self.lbl_rama.setText("Rama: cargando…")
        self._worker = Trabajo(self._consulta_git)
        self._worker.listo.connect(self._git_listo)
        self._worker.start()


class PanelSeguridad(QWidget):
    """Protección térmica y notificaciones push."""

    guardar_ajustes = Signal(dict)

    def __init__(self, seguridad, webhooks_config, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setSpacing(8)
        v.setContentsMargins(0, 0, 0, 0)

        # Tabs: Temperatura / Notificaciones
        self.tabs = QTabWidget()
        v.addWidget(self.tabs, 1)

        # --- Tab Temperatura ---
        tab_temp = QWidget()
        vt = QVBoxLayout(tab_temp)
        vt.setSpacing(12)
        vt.setContentsMargins(0, 0, 0, 0)

        grupo = QGroupBox("Temperatura y protección")
        g = QGridLayout(grupo)
        g.setSpacing(8)
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(8)
        g.setContentsMargins(12, 12, 12, 12)

        self.chk_activo = QCheckBox(
            "Verificar la temperatura y apagar la app si se sobrecalienta")
        self.chk_activo.setChecked(bool(seguridad.get("activo")))
        g.addWidget(self.chk_activo, 0, 0, 1, 2)

        self.chk_ver = QCheckBox(
            "Mostrar la temperatura en este panel (actualiza cada segundo)")
        self.chk_ver.setChecked(bool(seguridad.get("ver")))
        g.addWidget(self.chk_ver, 1, 0, 1, 2)

        def add_num_field(row, label_text, valor, minimo=1):
            lbl = QLabel(label_text)
            _fuente_ui(lbl)
            g.addWidget(lbl, row, 0)
            le = QLineEdit(str(valor))
            _fuente_ui(le)
            g.addWidget(le, row, 1)
            return le

        self.txt_umbral = add_num_field(2, "Umbral de peligro (°C):",
                                        seguridad.get("umbral", 85))
        self.txt_segundos = add_num_field(3, "Segundos de aviso antes de apagar:",
                                          seguridad.get("segundos", 5))

        b_guardar = _BtnPrimary("Guardar ajustes")
        b_guardar.clicked.connect(self._emitir_ajustes)
        g.addWidget(b_guardar, 4, 0, 1, 2)

        vt.addWidget(grupo)

        self.lbl_titulo_temp = _LabelMuted("Temperatura actual:")
        self.lbl_temp = QLabel("—")
        self.lbl_estado_temp = _LabelMuted("")

        vt.addWidget(self.lbl_titulo_temp)
        vt.addWidget(self.lbl_temp)
        vt.addWidget(self.lbl_estado_temp)
        vt.addStretch()

        self.tabs.addTab(tab_temp, "🌡 Temperatura")

        # --- Tab Notificaciones (Webhooks) ---
        self.panel_webhooks = PanelWebhooks(webhooks_config)
        self.panel_webhooks.guardado.connect(self._webhooks_guardado)
        self.tabs.addTab(self.panel_webhooks, "🔔 Notificaciones")

    def _webhooks_guardado(self, config: dict):
        """Re-emitir señal completa con seguridad + webhooks"""
        self.guardar_ajustes.emit({
            "seguridad": self.ajustes(),
            "webhooks": config,
        })

    def ajustes(self):
        return {
            "activo": self.chk_activo.isChecked(),
            "ver": self.chk_ver.isChecked(),
            "umbral": int(_numero(self.txt_umbral.text(), 85, int, 1)),
            "segundos": int(_numero(self.txt_segundos.text(), 5, int, 1)),
        }

    def aplicar_config(self, seguridad, webhooks=None):
        """Rellena los controles con la configuración del proyecto activo."""
        seguridad = seguridad or {}
        self.chk_activo.setChecked(bool(seguridad.get("activo")))
        self.chk_ver.setChecked(bool(seguridad.get("ver")))
        self.txt_umbral.setText(str(seguridad.get("umbral", 85)))
        self.txt_segundos.setText(str(seguridad.get("segundos", 5)))
        self.set_visibilidad_temp(bool(seguridad.get("ver")))
        if webhooks is not None:
            self.panel_webhooks.aplicar_config(webhooks)

    def _emitir_ajustes(self):
        # Solo seguridad; webhooks se emiten por separado
        self.guardar_ajustes.emit({
            "seguridad": self.ajustes(),
            "webhooks": self.panel_webhooks.obtener_config(),
        })

    def set_visibilidad_temp(self, ver):
        self.lbl_titulo_temp.setVisible(ver)
        self.lbl_temp.setVisible(ver)
        self.lbl_estado_temp.setVisible(ver)

    def actualizar_temp(self, t, umbral):
        if t is None:
            self.lbl_temp.setText("desconocida")
            self.lbl_temp.setStyleSheet("font-size: 28px; font-weight: 600; color: palette(text);")
            self.lbl_estado_temp.setText("No hay sensor de temperatura disponible.")
            return
        if t >= umbral:
            color = "#ef4444"
            estado = "⚠ SOBRECALENTAMIENTO: se abrirá el aviso de apagado."
        elif t >= umbral - 10:
            color = "#f59e0b"
            estado = "Temperatura alta: vigila."
        else:
            color = "#22c55e"
            estado = "Temperatura normal."
        self.lbl_temp.setStyleSheet(f"font-size: 28px; font-weight: 600; color: {color};")
        self.lbl_temp.setText(f"{t:.1f} °C")
        self.lbl_estado_temp.setText(estado)


class PanelLogs(QWidget):
    """Pestaña dedicada a logs: Loop + Gate en splitter vertical con headers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setSpacing(8)
        v.setContentsMargins(0, 0, 0, 0)

        # Splitter vertical principal
        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.setHandleWidth(6)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setStyleSheet("""
            QSplitter::handle { background: transparent; }
            QSplitter::handle:hover { background: palette(highlight); }
        """)

        # ---- LOOP (arriba) ----
        self.loop_container = self._crear_panel_log(
            "Salida del loop (progreso en vivo)",
            "loop"
        )
        self.panel_loop = self.loop_container.log_widget
        self.splitter.addWidget(self.loop_container)

        # ---- GATE (abajo) ----
        self.gate_container = self._crear_panel_log(
            "Salida de gate.sh",
            "gate"
        )
        self.panel_gate = self.gate_container.log_widget
        self.gate_container.setMaximumHeight(300)
        self.splitter.addWidget(self.gate_container)

        # Proporción inicial 70/30
        self.splitter.setSizes([500, 200])
        v.addWidget(self.splitter, 1)

    def _crear_panel_log(self, titulo, tipo):
        """Crea un contenedor con header + log widget."""
        container = QWidget()
        container.log_widget = PanelTarea()
        _fuente_monospace(container.log_widget)
        container.log_widget.setLineWrapMode(QPlainTextEdit.NoWrap)

        layout = QVBoxLayout(container)
        layout.setSpacing(4)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QHBoxLayout()
        header.setSpacing(8)
        header.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel(titulo)
        _fuente_ui(lbl)
        lbl.setStyleSheet("font-weight: 600; font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase; color: palette(mid);")
        header.addWidget(lbl)
        header.addStretch()

        # Botones de acción
        b_limpiar = _BtnGhost("🗑 Limpiar")
        b_limpiar.setToolTip("Limpiar salida")
        b_limpiar.clicked.connect(lambda: container.log_widget.clear())
        header.addWidget(b_limpiar)

        b_copiar = _BtnGhost("📋 Copiar")
        b_copiar.setToolTip("Copiar todo al portapapeles")
        b_copiar.clicked.connect(lambda: (container.log_widget.selectAll(), container.log_widget.copy()))
        header.addWidget(b_copiar)

        b_maximizar = _BtnGhost("⛶")
        b_maximizar.setToolTip("Alternar tamaño (maximizar/restaurar)")
        b_maximizar.setFixedWidth(28)
        b_maximizar.clicked.connect(lambda checked=False, t=tipo: self._toggle_maximizar(t))
        header.addWidget(b_maximizar)

        layout.addLayout(header)
        layout.addWidget(container.log_widget, 1)

        container.log_widget = container.log_widget
        container.tipo = tipo
        return container

    def _toggle_maximizar(self, tipo):
        """Alterna minimizar/expandir del panel: oculta o restaura en el splitter.

        No basta con setSizes(): el splitter no encoge un panel por debajo de su
        tamaño mínimo. Para minimizar de verdad se oculta el widget (queda a 0)
        y al expandir se restaura el reparto anterior.
        """
        idx = 0 if tipo == "loop" else 1
        w = self.splitter.widget(idx)
        if w.isVisible():
            self._tam_prev = list(self.splitter.sizes())
            w.hide()
            return
        w.show()
        prev = getattr(self, "_tam_prev", None)
        if prev and sum(prev) > 0:
            self.splitter.setSizes(prev)
        else:
            total = sum(self.splitter.sizes())
            if idx == 0:
                self.splitter.setSizes([int(total * 0.7), int(total * 0.3)])
            else:
                self.splitter.setSizes([int(total * 0.3), int(total * 0.7)])
