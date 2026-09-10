"""Ventana principal del panel de control."""

import os
import subprocess
import sys

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QPlainTextEdit, QTabWidget, QLineEdit, QCheckBox,
    QFileDialog, QMessageBox, QGridLayout, QGroupBox,
)

from . import plantillas
from .proceso import PanelTarea, Proceso
from .proyectos import cargar, guardar, leer_tema
from .temas import TEMAS, NOMBRES

FUENTE_MONO = "monospace"


def _fuente_monospace(objeto):
    fuente = QFont(objeto.font())
    fuente.setFamily(FUENTE_MONO)
    objeto.setFont(fuente)


class Ventana(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Autopiloto — panel de control")
        self.resize(980, 680)

        self.proyectos = cargar()
        if not self.proyectos:
            candidato = os.getcwd()
            if os.path.isfile(os.path.join(candidato, "plan.md")):
                self.proyectos[os.path.basename(candidato)] = {"ruta": candidato}
            guardar(self.proyectos, leer_tema())

        self.loop = None
        self.gate = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tail_log)
        self._nombre_activo = ""
        self.tema = leer_tema()

        self._ui()
        self._aplicar_tema(self.tema)
        self._cargar_proyecto()

    def _ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        barra = QHBoxLayout()
        barra.addWidget(QLabel("Proyecto:"))
        self.cmb = QComboBox()
        self.cmb.addItems(sorted(self.proyectos))
        self.cmb.currentTextChanged.connect(self._cambiar_proyecto)
        barra.addWidget(self.cmb, 1)
        b_agregar = QPushButton("Agregar…")
        b_agregar.clicked.connect(self._agregar_proyecto)
        b_quitar = QPushButton("Quitar")
        b_quitar.clicked.connect(self._quitar_proyecto)
        b_plantillas = QPushButton("Instalar plantillas")
        b_plantillas.clicked.connect(self._instalar_plantillas)
        barra.addWidget(b_agregar)
        barra.addWidget(b_quitar)
        barra.addWidget(b_plantillas)
        barra.addStretch()
        barra.addWidget(QLabel("Tema:"))
        self.cmb_tema = QComboBox()
        self.cmb_tema.addItems(NOMBRES)
        if self.tema in NOMBRES:
            self.cmb_tema.setCurrentText(self.tema)
        self.cmb_tema.currentTextChanged.connect(self._cambiar_tema)
        barra.addWidget(self.cmb_tema)
        root.addLayout(barra)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self.tabs.addTab(self._tab_plan(), "Plan")
        self.tabs.addTab(self._tab_ejecucion(), "Ejecución")
        self.tabs.addTab(self._tab_git(), "Git")

        self.estado = QLabel("Sin proyecto")
        root.addWidget(self.estado)

    def _tab_plan(self):
        w = QWidget()
        v = QVBoxLayout(w)
        self.lbl_conteo = QLabel("")
        v.addWidget(self.lbl_conteo)
        self.editor_plan = QPlainTextEdit()
        _fuente_monospace(self.editor_plan)
        v.addWidget(self.editor_plan, 1)
        h = QHBoxLayout()
        b_recargar = QPushButton("Recargar")
        b_recargar.clicked.connect(self._cargar_plan)
        b_guardar = QPushButton("Guardar plan.md")
        b_guardar.clicked.connect(self._guardar_plan)
        h.addStretch()
        h.addWidget(b_recargar)
        h.addWidget(b_guardar)
        v.addLayout(h)
        return w

    def _tab_ejecucion(self):
        w = QWidget()
        v = QVBoxLayout(w)

        grupo = QGroupBox("Opciones de lanzamiento")
        g = QGridLayout(grupo)
        g.addWidget(QLabel("Hasta (HH:MM, vacío = sin límite):"), 0, 0)
        self.txt_hasta = QLineEdit("22:00")
        self.txt_hasta.setPlaceholderText("22:00")
        g.addWidget(self.txt_hasta, 0, 1)
        g.addWidget(QLabel("Máx iteraciones:"), 1, 0)
        self.txt_iter = QLineEdit("40")
        g.addWidget(self.txt_iter, 1, 1)
        g.addWidget(QLabel("Padre (rama base):"), 2, 0)
        self.txt_padre = QLineEdit("master")
        g.addWidget(self.txt_padre, 2, 1)
        self.chk_push = QCheckBox("--push al final")
        self.chk_push.setChecked(True)
        g.addWidget(self.chk_push, 3, 0, 1, 2)
        v.addWidget(grupo)

        h = QHBoxLayout()
        self.b_iniciar = QPushButton("▶ Iniciar loop")
        self.b_iniciar.clicked.connect(self._iniciar_loop)
        self.b_detener = QPushButton("■ Detener")
        self.b_detener.clicked.connect(self._detener_loop)
        self.b_detener.setEnabled(False)
        self.b_gate = QPushButton("Ejecutar gate.sh")
        self.b_gate.clicked.connect(self._ejecutar_gate)
        h.addWidget(self.b_iniciar)
        h.addWidget(self.b_detener)
        h.addWidget(self.b_gate)
        h.addStretch()
        v.addLayout(h)

        v.addWidget(QLabel("Salida del loop (progreso en vivo):"))
        self.txt_loop = PanelTarea()
        _fuente_monospace(self.txt_loop)
        v.addWidget(self.txt_loop, 1)

        v.addWidget(QLabel("Salida de gate.sh:"))
        self.txt_gate = PanelTarea()
        self.txt_gate.setMaximumHeight(180)
        _fuente_monospace(self.txt_gate)
        v.addWidget(self.txt_gate)
        return w

    def _tab_git(self):
        w = QWidget()
        v = QVBoxLayout(w)
        h = QHBoxLayout()
        self.lbl_rama = QLabel("")
        b_ref = QPushButton("Refrescar")
        b_ref.clicked.connect(self._cargar_git)
        h.addWidget(self.lbl_rama)
        h.addStretch()
        h.addWidget(b_ref)
        v.addLayout(h)
        self.txt_git = QPlainTextEdit()
        self.txt_git.setReadOnly(True)
        _fuente_monospace(self.txt_git)
        v.addWidget(self.txt_git, 1)
        return w

    # ---------- Proyectos ----------

    def _aplicar_tema(self, nombre):
        if nombre in TEMAS:
            QApplication.instance().setStyleSheet(TEMAS[nombre])

    def _cambiar_tema(self, nombre):
        self.tema = nombre
        guardar(self.proyectos, nombre)
        self._aplicar_tema(nombre)

    def _proyecto_actual(self):
        nombre = self.cmb.currentText()
        if not nombre:
            return None
        info = self.proyectos.get(nombre)
        return (nombre, info["ruta"]) if info else None

    def _cambiar_proyecto(self, n):
        if self.loop and self.loop.state() == QProcess.Running:
            prev = self.cmb.findText(self._nombre_activo)
            if prev >= 0:
                self.cmb.blockSignals(True)
                self.cmb.setCurrentIndex(prev)
                self.cmb.blockSignals(False)
            QMessageBox.warning(self, "Autopiloto en ejecución",
                                "Detén el loop antes de cambiar de proyecto.")
            return
        self._nombre_activo = n
        guardar(self.proyectos, self.tema)
        self._cargar_proyecto()

    def _cargar_proyecto(self):
        p = self._proyecto_actual()
        if not p:
            self.estado.setText("Sin proyecto")
            return
        nombre, ruta = p
        self._nombre_activo = nombre
        self.estado.setText(f"Proyecto: {nombre} — {ruta}")
        self._cargar_plan()
        self._cargar_git()
        self.txt_gate.clear()
        self.txt_loop.clear()
        self._tail_log()

        faltan = plantillas.faltan(ruta)
        if faltan:
            self.b_iniciar.setEnabled(False)
            self.b_gate.setEnabled(False)
            self.estado.setText(
                f"{self.estado.text()}  |  FALTAN: {', '.join(faltan)} "
                "(pulsa 'Instalar plantillas')")
        else:
            self.b_iniciar.setEnabled(True)
            self.b_gate.setEnabled(True)

    def _agregar_proyecto(self):
        ruta = QFileDialog.getExistingDirectory(
            self, "Selecciona la raíz del proyecto")
        if not ruta:
            return
        nombre = os.path.basename(ruta)
        creados = plantillas.instalar(ruta)
        self.proyectos[nombre] = {"ruta": ruta}
        guardar(self.proyectos, self.tema)
        self.cmb.addItem(nombre)
        self.cmb.setCurrentText(nombre)
        if creados:
            QMessageBox.information(
                self, "Proyecto listo",
                f"Se generaron en {ruta}:\n\n  · " + "\n  · ".join(creados) +
                "\n\nPulsa '▶ Iniciar loop' cuando quieras arrancar.")
        else:
            QMessageBox.information(
                self, "Proyecto", "Ya tenía todos los archivos del autopiloto.")

    def _instalar_plantillas(self):
        p = self._proyecto_actual()
        if not p:
            return
        _, ruta = p
        creados = plantillas.instalar(ruta)
        if creados:
            QMessageBox.information(
                self, "Plantillas instaladas",
                "Creados en " + ruta + ":\n  · " + "\n  · ".join(creados))
        else:
            QMessageBox.information(
                self, "Ya está todo", "El proyecto ya tiene autopiloto.sh, "
                "gate.sh, mapear.sh y plan.md.")
        self._cargar_proyecto()

    def _quitar_proyecto(self):
        nombre = self.cmb.currentText()
        if not nombre:
            return
        if self.proyectos.pop(nombre, None) is not None:
            guardar(self.proyectos, self.tema)
            self.cmb.removeItem(self.cmb.currentIndex())

    # ---------- Plan ----------

    def _cargar_plan(self):
        p = self._proyecto_actual()
        if not p:
            return
        ruta = os.path.join(p[1], "plan.md")
        if not os.path.exists(ruta):
            self.editor_plan.setPlainText("# PLAN\n\n- [ ] tu primera tarea — criterio: ...\n")
            self.lbl_conteo.setText("plan.md no existe aún")
            return
        with open(ruta, "r", encoding="utf-8") as f:
            self.editor_plan.setPlainText(f.read())
        self._actualizar_conteo()

    def _actualizar_conteo(self):
        pend, hecho, bloqueada = 0, 0, 0
        for l in self.editor_plan.toPlainText().splitlines():
            if l.startswith("- [ ]"):
                pend += 1
            elif l.startswith("- [x]"):
                hecho += 1
            elif l.startswith("- [B]"):
                bloqueada += 1
        self.lbl_conteo.setText(
            f"Pendientes: {pend}   ·   Hechas: {hecho}   ·   Bloqueadas: {bloqueada}")

    def _guardar_plan(self):
        p = self._proyecto_actual()
        if not p:
            return
        ruta = os.path.join(p[1], "plan.md")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(self.editor_plan.toPlainText())
        self._actualizar_conteo()
        self.estado.setText(f"plan.md guardado ({ruta})")

    # ---------- Loop ----------

    def _iniciar_loop(self):
        p = self._proyecto_actual()
        if not p:
            return
        _, ruta = p
        args = []
        hasta = self.txt_hasta.text().strip()
        if hasta:
            args += ["--hasta", hasta]
        padre = self.txt_padre.text().strip()
        if padre:
            args += ["--padre", padre]
        if self.chk_push.isChecked():
            args.append("--push")
        try:
            iter_v = int(self.txt_iter.text().strip() or "40")
        except ValueError:
            iter_v = 40
        env = list(QProcess.systemEnvironment())
        env.append(f"MAX_ITER={iter_v}")
        self.txt_loop.clear()
        self.txt_loop.appendPlainText(
            f"> bash autopiloto.sh {' '.join(args)}  (MAX_ITER={iter_v})")
        self.loop = Proceso(self.txt_loop, on_fin=self._loop_fin)
        self.loop.setWorkingDirectory(ruta)
        self.loop.setEnvironment(env)
        self.loop.start("bash", ["autopiloto.sh"] + args)
        self.b_iniciar.setEnabled(False)
        self.b_detener.setEnabled(True)
        self.b_gate.setEnabled(False)
        self.cmb.setEnabled(False)
        self.timer.start(1000)

    def _loop_fin(self):
        self.b_iniciar.setEnabled(True)
        self.b_detener.setEnabled(False)
        p = self._proyecto_actual()
        if p:
            self.b_gate.setEnabled(os.path.exists(os.path.join(p[1], "gate.sh")))
        self.cmb.setEnabled(True)
        self.timer.stop()
        self._cargar_plan()
        self._cargar_git()

    def _detener_loop(self):
        if self.loop and self.loop.state() == QProcess.Running:
            self.txt_loop.appendPlainText("[manual] deteniendo el loop…")
            self.loop.terminate()
            if not self.loop.waitForFinished(5000):
                self.loop.kill()

    def _tail_log(self):
        p = self._proyecto_actual()
        if not p:
            return
        log = os.path.join(p[1], "progreso.log")
        if os.path.exists(log):
            with open(log, "r", encoding="utf-8", errors="replace") as f:
                self.txt_loop.setPlainText(f.read()[-4000:])

    # ---------- Gate ----------

    def _ejecutar_gate(self):
        p = self._proyecto_actual()
        if not p:
            return
        _, ruta = p
        self.txt_gate.clear()
        self.txt_gate.appendPlainText("> bash gate.sh")
        self.gate = Proceso(self.txt_gate)
        self.gate.setWorkingDirectory(ruta)
        self.gate.start("bash", ["gate.sh"])

    # ---------- Git ----------

    def _cargar_git(self):
        p = self._proyecto_actual()
        if not p:
            self.txt_git.clear()
            return
        _, ruta = p

        def run(cmd):
            try:
                out = subprocess.run(cmd, cwd=ruta, capture_output=True,
                                     text=True, timeout=20)
                return out.stdout.strip()
            except Exception:
                return ""

        rama = run(["git", "branch", "--show-current"])
        self.lbl_rama.setText(f"Rama: {rama}" if rama else "Rama: —")
        status = run(["git", "status", "--short"])
        log = run(["git", "log", "--oneline", "-12"])
        texto = "── status ──\n" + (status or "(limpio)\n")
        texto += "\n── últimos commits ──\n" + (log or "(sin commits)")
        self.txt_git.setPlainText(texto)


def main():
    app = QApplication(sys.argv)
    icono = os.path.join(os.path.dirname(__file__), "icono.svg")
    if os.path.exists(icono):
        app.setWindowIcon(QIcon(icono))
    ventana = Ventana()
    ventana.show()
    sys.exit(app.exec())