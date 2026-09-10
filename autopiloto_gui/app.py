"""Ventana principal del panel de control."""

import os
import subprocess
import sys

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QPlainTextEdit, QTabWidget, QLineEdit, QCheckBox,
    QFileDialog, QMessageBox, QGridLayout, QGroupBox, QDialog,
)

from . import modelos, plantillas, sensor
from .proceso import PanelTarea, Proceso
from .proyectos import (cargar, guardar, leer_tema, leer_seguridad,
                        leer_modelos)
from .temas import TEMAS, NOMBRES

FUENTE_MONO = "monospace"


def _fuente_monospace(objeto):
    fuente = QFont(objeto.font())
    fuente.setFamily(FUENTE_MONO)
    objeto.setFont(fuente)


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
        self.lbl_temp = QLabel(f"<b>⚠ Temperatura crítica: {temp} °C</b>")
        v.addWidget(self.lbl_temp)
        self.lbl_conteo = QLabel(
            f"La aplicación se apagará en <b>{self._restante}</b> s.")
        self.lbl_conteo.setStyleSheet("font-size: 18px;")
        v.addWidget(self.lbl_conteo)

        h = QHBoxLayout()
        b_continuar = QPushButton("Continuar")
        b_continuar.clicked.connect(self._continuar)
        b_apagar = QPushButton("Apagar ahora")
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
        self.timer_temp = QTimer(self)
        self.timer_temp.timeout.connect(self._comprobar_temp)
        self.timer_aviso = None
        self._aviso_abierto = None
        self._nombre_activo = ""
        self.tema = leer_tema()
        self.seguridad = leer_seguridad()
        self._modelos = modelos.lista_modelos() or [modelos.MODELO_SUGERIDO]
        self._sel_modelos = leer_modelos()

        self._ui()
        self._aplicar_tema(self.tema)
        self._cargar_proyecto()
        self._iniciar_vigilancia()

    def _iniciar_vigilancia(self):
        seg = self.seguridad
        activo = bool(seg.get("activo"))
        ver = bool(seg.get("ver"))
        self._aplicar_visibilidad_temp(ver)
        if (activo or ver) and sensor.leer_temperatura() is not None:
            self.timer_temp.start(1000)
        else:
            self.timer_temp.stop()
        self._comprobar_temp()

    def _aplicar_visibilidad_temp(self, ver):
        if hasattr(self, "lbl_temp"):
            self.lbl_temp.setVisible(ver)
            self.lbl_estado_temp.setVisible(ver)

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
        self.tabs.addTab(self._tab_seguridad(), "Seguridad")

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
        g.addWidget(QLabel("Modelo (agente de tarea):"), 3, 0)
        self.cmb_agente = QComboBox()
        self.cmb_agente.addItems(self._modelos)
        self.cmb_agente.currentTextChanged.connect(self._guardar_sel_modelos)
        g.addWidget(self.cmb_agente, 3, 1)
        g.addWidget(QLabel("Modelo (agente revisor del diff):"), 4, 0)
        self.cmb_revisor = QComboBox()
        self.cmb_revisor.addItems(self._modelos)
        self.cmb_revisor.currentTextChanged.connect(self._guardar_sel_modelos)
        g.addWidget(self.cmb_revisor, 4, 1)
        self._aplicar_sel_modelos()
        b_modelos = QPushButton("↻ Refrescar modelos")
        b_modelos.clicked.connect(self._refrescar_modelos)
        g.addWidget(b_modelos, 5, 0, 1, 2)
        self.lbl_modelos = QLabel(
            f"{len(self._modelos)} modelos de opencode cargados")
        g.addWidget(self.lbl_modelos, 6, 0, 1, 2)
        self.chk_dual = QCheckBox("Gate dual: el revisor exige VERDICT: PASS antes del commit")
        self.chk_dual.setChecked(True)
        g.addWidget(self.chk_dual, 7, 0, 1, 2)
        self.chk_voz = QCheckBox("Alertas de voz al bloquear/terminar (notify-send/spd-say)")
        g.addWidget(self.chk_voz, 8, 0, 1, 2)
        g.addWidget(QLabel("Presupuesto máx (USD, 0 = sin límite):"), 9, 0)
        self.txt_costo_max = QLineEdit("0")
        g.addWidget(self.txt_costo_max, 9, 1)
        g.addWidget(QLabel("Costo estimado por tarea (USD):"), 10, 0)
        self.txt_costo_iter = QLineEdit("0.50")
        g.addWidget(self.txt_costo_iter, 10, 1)
        self.chk_push = QCheckBox("--push al final")
        self.chk_push.setChecked(True)
        g.addWidget(self.chk_push, 11, 0, 1, 2)
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

    def _tab_seguridad(self):
        w = QWidget()
        v = QVBoxLayout(w)
        grupo = QGroupBox("Temperatura y protección")
        g = QGridLayout(grupo)
        seg = self.seguridad
        self.chk_activo = QCheckBox(
            "Verificar la temperatura y apagar la app si se sobrecalienta")
        self.chk_activo.setChecked(bool(seg.get("activo")))
        g.addWidget(self.chk_activo, 0, 0, 1, 2)
        self.chk_ver = QCheckBox(
            "Mostrar la temperatura en este panel (actualiza cada segundo)")
        self.chk_ver.setChecked(bool(seg.get("ver")))
        g.addWidget(self.chk_ver, 1, 0, 1, 2)
        g.addWidget(QLabel("Umbral de peligro (°C):"), 2, 0)
        self.txt_umbral = QLineEdit(str(seg.get("umbral", 85)))
        g.addWidget(self.txt_umbral, 2, 1)
        g.addWidget(QLabel("Segundos de aviso antes de apagar:"), 3, 0)
        self.txt_segundos = QLineEdit(str(seg.get("segundos", 5)))
        g.addWidget(self.txt_segundos, 3, 1)
        b_guardar = QPushButton("Guardar ajustes")
        b_guardar.clicked.connect(self._guardar_seguridad)
        g.addWidget(b_guardar, 4, 0, 1, 2)
        v.addWidget(grupo)

        v.addWidget(QLabel("Temperatura actual:"))
        self.lbl_temp = QLabel("—")
        self.lbl_temp.setStyleSheet("font-size: 26px;")
        v.addWidget(self.lbl_temp)
        self.lbl_estado_temp = QLabel("")
        v.addWidget(self.lbl_estado_temp)
        v.addStretch()
        return w

    def _guardar_seguridad(self):
        import re

        def n_int(texto, defv):
            try:
                return max(1, int(re.sub(r"\D", "", texto) or defv))
            except ValueError:
                return defv

        seg = {
            "activo": self.chk_activo.isChecked(),
            "ver": self.chk_ver.isChecked(),
            "umbral": n_int(self.txt_umbral.text(), 85),
            "segundos": n_int(self.txt_segundos.text(), 5),
        }
        self.seguridad = seg
        guardar(self.proyectos, self.tema, seg)
        self._iniciar_vigilancia()
        self.estado.setText("Ajustes de seguridad guardados")

    def _temperatura_texto(self, t):
        umbral = self.seguridad.get("umbral", 85)
        if t is None:
            return "desconocida", ""
        color = "color: orange;" if t >= umbral - 10 else "color: green;"
        if t >= umbral:
            color = "color: red;"
        return f"{t:.1f} °C", f"font-size: 26px; {color}"

    def _comprobar_temp(self):
        t = sensor.leer_temperatura()
        self._mostrar_temp(t)
        seg = self.seguridad
        if not seg.get("activo") or t is None:
            return
        if t >= float(seg.get("umbral", 85)):
            if not self._aviso_abierto or not self._aviso_abierto.isVisible():
                self._abrir_aviso(t)
        elif self._aviso_abierto is not None:
            self._aviso_abierto._continuar()

    def _mostrar_temp(self, t):
        if not hasattr(self, "lbl_temp"):
            return
        texto, estilo = self._temperatura_texto(t)
        self.lbl_temp.setStyleSheet(estilo)
        self.lbl_temp.setText(texto)
        if t is None:
            self.lbl_estado_temp.setText("No hay sensor de temperatura disponible.")
        elif t >= float(self.seguridad.get("umbral", 85)):
            self.lbl_estado_temp.setText(
                "⚠ SOBRECALENTAMIENTO: se abrirá el aviso de apagado.")
        elif t >= float(self.seguridad.get("umbral", 85)) - 10:
            self.lbl_estado_temp.setText("Temperatura alta: vigila.")
        else:
            self.lbl_estado_temp.setText("Temperatura normal.")

    def _abrir_aviso(self, t):
        aviso = AvisoTemperatura(t, self.seguridad.get("segundos", 5), self)
        self._aviso_abierto = aviso
        aviso.finished.connect(self._aviso_terminado)
        aviso.show()
        aviso.raise_()
        aviso.activateWindow()

    def _aviso_terminado(self, _codigo):
        aviso = self._aviso_abierto
        self._aviso_abierto = None
        if aviso and aviso.apagar:
            self._apagar_aplicacion()

    def _apagar_aplicacion(self):
        self.estado.setText("🔥 Apagado por sobrecalentamiento")
        if self.loop and self.loop.state() == QProcess.Running:
            self._detener_loop()
        self.timer.stop()
        self.timer_temp.stop()
        self.estado.setText("🔥 Apagado por sobrecalentamiento. Hasta luego.")
        QTimer.singleShot(1200, QApplication.instance().quit)

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

    def _aplicar_sel_modelos(self):
        sel_tarea = self._sel_modelos.get("tarea")
        sel_revisor = self._sel_modelos.get("revisor")
        if sel_tarea in self._modelos:
            self.cmb_agente.setCurrentText(sel_tarea)
        else:
            self.cmb_agente.setCurrentText(modelos.sugerido(self._modelos))
        if sel_revisor in self._modelos:
            self.cmb_revisor.setCurrentText(sel_revisor)
        else:
            self.cmb_revisor.setCurrentText(modelos.sugerido(self._modelos))

    def _guardar_sel_modelos(self, *_):
        self._sel_modelos = {
            "tarea": self.cmb_agente.currentText(),
            "revisor": self.cmb_revisor.currentText(),
        }
        guardar(self.proyectos, self.tema,
                seguridad=self.seguridad, modelos=self._sel_modelos)

    def _refrescar_modelos(self):
        nuevos = modelos.lista_modelos()
        if not nuevos:
            nuevos = [modelos.MODELO_SUGERIDO]
        actual_agente = self.cmb_agente.currentText()
        actual_revisor = self.cmb_revisor.currentText()
        self._modelos = nuevos
        self.cmb_agente.blockSignals(True)
        self.cmb_revisor.blockSignals(True)
        self.cmb_agente.clear()
        self.cmb_revisor.clear()
        self.cmb_agente.addItems(nuevos)
        self.cmb_revisor.addItems(nuevos)
        if actual_agente in nuevos:
            self.cmb_agente.setCurrentText(actual_agente)
        else:
            self.cmb_agente.setCurrentText(modelos.sugerido(nuevos))
        if actual_revisor in nuevos:
            self.cmb_revisor.setCurrentText(actual_revisor)
        else:
            self.cmb_revisor.setCurrentText(modelos.sugerido(nuevos))
        self.cmb_agente.blockSignals(False)
        self.cmb_revisor.blockSignals(False)
        self.lbl_modelos.setText(f"{len(nuevos)} modelos de opencode cargados")
        self.estado.setText("Modelos refrescados")
        self._guardar_sel_modelos()

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
        env.append("AGENTE_TAREA=opencode")
        env.append(f"MODELO_TAREA={self.cmb_agente.currentText()}")
        env.append("AGENTE_REVISOR=opencode")
        env.append(f"MODELO_REVISOR={self.cmb_revisor.currentText()}")

        def _fl(texto, defv, tipo=float):
            try:
                return tipo(texto.strip() or defv)
            except ValueError:
                return defv

        env.append(f"REVISION_DUAL={'1' if self.chk_dual.isChecked() else '0'}")
        env.append(f"VOZ={'1' if self.chk_voz.isChecked() else '0'}")
        env.append(f"MAX_COSTO={_fl(self.txt_costo_max.text(), 0)}")
        env.append(f"COSTO_POR_ITER={_fl(self.txt_costo_iter.text(), 0.50)}")
        self.txt_loop.clear()
        self.txt_loop.appendPlainText(
            f"> bash autopiloto.sh {' '.join(args)}  "
            f"(modelo tarea={self.cmb_agente.currentText()}, "
            f"modelo revisor={self.cmb_revisor.currentText()}, "
            f"dual={self.chk_dual.isChecked()}, "
            f"costo={env[-2].split('=')[1]}, iter={iter_v})")
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