"""Ventana principal del panel de control (orquestación).

La UI de cada pestaña vive en `paneles.py`; aquí solo se conectan señales,
se gestionan los procesos (loop/gate), la configuración persistida y la
vigilancia (temperatura e internet).
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time

from PySide6.QtCore import QProcess, QSettings, QTimer
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from . import configuracion as cfg
from . import modelos, net, plantillas, sensor
from .paneles import (
    AvisoTemperatura,
    LoopPill,
    PanelEjecucion,
    PanelGit,
    PanelLecciones,
    PanelLogs,
    PanelMapa,
    PanelPlan,
    PanelSeguridad,
    _BtnDanger,
    fase_actual,
)
from .paneles_metricas import PanelMetricas
from .proceso import Proceso, Trabajo
from .proyectos import (
    RegistroCorrupto,
    cargar,
    descartar_registro_corrupto,
    guardar,
    guardar_config_proyecto,
    leer_config_proyecto,
    leer_modelos,
    leer_seguridad,
    leer_sidebar_ancho,
    leer_tema,
    leer_webhooks,
    verificar_registro,
)
from .temas import NOMBRES, inicializar_temas, obtener_temas
from .webhooks import WebhookManager


class Ventana(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Autopiloto — panel de control")
        self.resize(cfg.ANCHO, cfg.ALTO)
        self.setMinimumSize(cfg.ANCHO_MIN, cfg.ALTO_MIN)
        # Recupera el tamaño y estado (maximizado/restaurado) de la última sesión
        self._settings = QSettings("autopiloto-gui", "panel")
        geo = self._settings.value("ventana/geometria")
        if geo:
            self.restoreGeometry(geo)

        self.proyectos = cargar()
        if not self.proyectos:
            candidato = os.getcwd()
            # Sólo auto-registra el directorio actual si parece un proyecto real
            # del autopiloto (tiene plan.md + autopiloto.sh + .git) y NO es la
            # propia carpeta de la GUI. Evita que arrancar dentro del repo de la
            # app la registre a ella misma como "proyecto" (raíz de confusión).
            parece_proyecto = (
                os.path.isfile(os.path.join(candidato, "plan.md"))
                and os.path.isfile(os.path.join(candidato, "autopiloto.sh"))
                and os.path.isdir(os.path.join(candidato, ".git"))
            )
            dir_gui = os.path.dirname(os.path.abspath(__file__))
            if parece_proyecto and os.path.abspath(candidato) != dir_gui:
                self.proyectos[os.path.basename(candidato)] = {"ruta": candidato}
            guardar(self.proyectos, leer_tema())

        self.loop = None
        self.gate = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tail_log)
        self.timer_temp = QTimer(self)
        self.timer_temp.timeout.connect(self._comprobar_temp)
        self.timer_net = QTimer(self)
        self.timer_net.timeout.connect(self._comprobar_net)
        self._aviso_abierto = None
        self._nombre_activo = ""
        self._log_tam = 0
        self._log_marca = 0
        self._log_inicio = 0
        self._revision_pendiente = False
        self.tema = leer_tema()
        self.seguridad = leer_seguridad()
        self.webhooks_config = leer_webhooks()
        self._modelos = []
        self._sel_modelos = leer_modelos()
        self._lanzamiento = dict(cfg.LAUNCH_DEFECTO)
        self._inicio_loop_ts = None
        self._iter_actual = 0
        self._worker_sesiones_limpieza = None

        # Webhook manager
        self.webhook = WebhookManager(self.webhooks_config)
        self.webhook.error.connect(lambda plataforma, msg: self.statusBar().showMessage(
            f"Webhook {plataforma}: {msg}", 8000))

        # Usar ancho de sidebar persistido (o defecto)
        self._ancho_sidebar = leer_sidebar_ancho()

        self._ui()
        self._aplicar_tema(self.tema)
        self._cargar_proyecto()
        self._cargar_modelos_en_fondo()
        self._sondear_sesiones_en_fondo()
        self._iniciar_vigilancia()
        self._comprobar_net()
        self.timer_net.start(cfg.TIMER_NET_MS)

        # Timer para detectar revisión pendiente (cuando revision_manual está activo)
        self.timer_revision = QTimer(self)
        self.timer_revision.timeout.connect(self._comprobar_revision_pendiente)
        self.timer_revision.start(1000)

        # Timer para métricas
        self.timer_metricas = QTimer(self)
        self.timer_metricas.timeout.connect(self._actualizar_metricas)
        self.timer_metricas.start(cfg.TIMER_METRICAS_MS)

        # Recarga plan.md automáticamente si cambia en disco (loop/externo)
        self.timer_plan = QTimer(self)
        self.timer_plan.timeout.connect(self._refrescar_plan)
        self.timer_plan.start(2000)

        # Recarga lecciones.md automáticamente si cambia en disco
        self.timer_lecciones = QTimer(self)
        self.timer_lecciones.timeout.connect(self._refrescar_lecciones)
        self.timer_lecciones.start(2000)

    def _refrescar_plan(self):
        self.pan_plan._recargar_si_cambio()

    def _refrescar_lecciones(self):
        self.pan_lecciones._recargar_si_cambio()

    def _sondear_sesiones_en_fondo(self):
        """Consulta en segundo plano si cada CLI instalado tiene sesión.

        Los agentes sin login se marcan en el combo en vez de fallar en la
        primera iteración del loop. El resultado se cachea en modelos.
        """
        modelos.invalidar_cache()
        w = Trabajo(modelos.estado_agentes)
        w.conectar(self._sesiones_agentes_sondeadas)
        w.liberar(self, "_worker_sesiones")
        w.start()
        self._worker_sesiones = w

    def _sesiones_agentes_sondeadas(self, _estado):
        """Repinta los combos cuando llega el sondeo de sesión."""
        self.pan_ejec.refrescar_agentes()

    def _cargar_modelos_en_fondo(self):
        """Consulta opencode/models.dev sin bloquear el arranque."""
        w = Trabajo(modelos.lista_modelos)
        w.conectar(self._modelos_cargados)
        w.liberar(self, "_worker_modelos")
        w.start()
        self._worker_modelos = w

    def _modelos_cargados(self, lista):
        nuevos = lista or [cfg.MODELO_SUGERIDO]
        self._modelos = nuevos
        for sel in (self.pan_ejec.cmb_agente, self.pan_ejec.cmb_revisor):
            sel.activar_catalogo_global()
        self.pan_ejec.agregar_catalogo(nuevos)
        self.pan_ejec.info_modelos(len(nuevos),
                                   len(modelos.nombres_proveedores()))
        self._aplicar_sel_modelos()

    # ---------- UI ----------

    def _ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        barra = QHBoxLayout()
        barra.addWidget(QLabel("Proyecto:"))
        self.cmb = QComboBox()
        self.cmb.addItems(sorted(self.proyectos))
        # Reabre el último proyecto activo (en vez del primero alfabético)
        prev = self._settings.value("proyecto/activo", "")
        if prev and prev in self.proyectos:
            self.cmb.setCurrentText(prev)
        self.cmb.currentTextChanged.connect(self._cambiar_proyecto)
        barra.addWidget(self.cmb, 1)
        b_agregar = QPushButton("Agregar…")
        b_agregar.clicked.connect(self._agregar_proyecto)
        b_quitar = _BtnDanger("Quitar")
        b_quitar.clicked.connect(self._quitar_proyecto)
        barra.addWidget(b_agregar)
        barra.addWidget(b_quitar)
        barra.addStretch()
        barra.addWidget(QLabel("Tema:"))
        self.cmb_tema = QComboBox()
        self.cmb_tema.addItems(NOMBRES)
        if self.tema in NOMBRES:
            self.cmb_tema.setCurrentText(self.tema)
        self.cmb_tema.currentTextChanged.connect(self._cambiar_tema)
        barra.addWidget(self.cmb_tema)
        root.addLayout(barra)

        # ===== CUERPO: sidebar + contenido =====
        cuerpo = QHBoxLayout()
        cuerpo.setSpacing(0)
        cuerpo.setContentsMargins(0, 0, 0, 0)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(self._ancho_sidebar)
        self._sidebar_items = []
        self.stack = QStackedWidget()
        cuerpo.addWidget(self.sidebar)
        cuerpo.addWidget(self.stack, 1)
        root.addLayout(cuerpo, 1)

        self.pan_plan = PanelPlan()
        self.pan_plan.guardado.connect(
            lambda ruta: self.estado.setText(f"plan.md guardado ({ruta})"))
        self.pan_lecciones = PanelLecciones()
        self.pan_lecciones.guardado.connect(
            lambda ruta: self.estado.setText(f"lecciones.md guardado ({ruta})"))
        self.pan_ejec = PanelEjecucion()
        self.pan_ejec.iniciar.connect(self._iniciar_loop)
        self.pan_ejec.detener.connect(self._detener_loop)
        self.pan_ejec.gate.connect(self._ejecutar_gate)
        self.pan_ejec.refrescar_modelos.connect(self._refrescar_modelos)
        self.pan_ejec.modelos_modificados.connect(self._guardar_sel_modelos)
        # Navigator signals
        self.pan_ejec.cmb_nav.currentTextChanged.connect(self._guardar_sel_modelos)
        # Conectar panel de revisión
        self.pan_ejec.panel_revision.aprobado.connect(self._revision_aprobada)
        self.pan_ejec.panel_revision.rechazado.connect(self._revision_rechazada)
        self.pan_git = PanelGit()
        self.pan_git.revertir_commit.connect(self._ejecutar_revert)
        self.pan_git.limpiar_git.connect(self._limpiar_git_framework)
        self.pan_logs = PanelLogs()
        self.pan_mapa = PanelMapa()
        self.pan_metricas = PanelMetricas()
        self.pan_seg = PanelSeguridad(self.seguridad, self.webhooks_config)
        self.pan_seg.guardar_ajustes.connect(self._guardar_seguridad)

        self._secciones = [
            ("Plan", self.pan_plan),
            ("🧠 Lecciones", self.pan_lecciones),
            ("Ejecución", self.pan_ejec),
            ("Logs", self.pan_logs),
            ("🗺 Mapa", self.pan_mapa),
            ("Git", self.pan_git),
            ("📊 Métricas", self.pan_metricas),
            ("🛡 Seguridad", self.pan_seg),
        ]
        for i, (nombre, panel) in enumerate(self._secciones):
            self.sidebar.addItem(nombre)
            self.stack.addWidget(panel)
            # Atajos Ctrl+1..7 por sección
            atajo = QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self)
            atajo.activated.connect(
                lambda _n=i: self._cambiar_seccion(_n))
        self.sidebar.setCurrentRow(0)
        self.sidebar.currentRowChanged.connect(self._cambiar_seccion)

        # ===== BARRA DE ESTADO =====
        self.barra_estado = QStatusBar()
        self.estado = QLabel("Sin proyecto")
        self.barra_estado.addWidget(self.estado)
        self.pill_loop = LoopPill()
        self.barra_estado.addPermanentWidget(self.pill_loop)
        self.setStatusBar(self.barra_estado)

    def _cambiar_seccion(self, indice: int):
        """Cambia la sección visible (sidebar ↔ stack, con atajos Ctrl+N)."""
        if 0 <= indice < self.stack.count():
            self.stack.setCurrentIndex(indice)
            self.sidebar.setCurrentRow(indice)

    def _set_fase_loop(self, iter_actual=0, total=0, corriendo=True):
        """Actualiza stepper del pipeline y píldora de estado del loop."""
        p = self._proyecto_actual()
        ruta_log = os.path.join(p[1], "progreso.log") if p else ""
        fase = fase_actual(ruta_log) if corriendo else ""
        self.pan_ejec.pipeline.setFase(fase)
        if not corriendo:
            self.pan_ejec.pipeline.setPendiente()
        self.pill_loop.setEstado(iter_actual, total, fase, corriendo)

    def _aplicar_tema(self, nombre):
        temas = obtener_temas()
        if nombre in temas:
            QApplication.instance().setStyleSheet(temas[nombre])
        self.pan_ejec.pipeline.set_tema(nombre)

    # ---------- Vigilancia térmica ----------

    def _iniciar_vigilancia(self):
        seg = self.seguridad
        activo = bool(seg.get("activo"))
        ver = bool(seg.get("ver"))
        self.pan_seg.set_visibilidad_temp(ver)
        if (activo or ver) and sensor.leer_temperatura() is not None:
            self.timer_temp.start(cfg.TIMER_TEMP_MS)
        else:
            self.timer_temp.stop()
        self._comprobar_temp()

    def _comprobar_temp(self):
        t = sensor.leer_temperatura()
        self.pan_seg.actualizar_temp(t, self.seguridad.get("umbral", 85))
        seg = self.seguridad
        if not seg.get("activo") or t is None:
            return
        if t >= float(seg.get("umbral", 85)):
            if not self._aviso_abierto or not self._aviso_abierto.isVisible():
                self._abrir_aviso(t)
        elif self._aviso_abierto is not None:
            self._aviso_abierto._continuar()

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

    def _guardar_seguridad(self, datos):
        """Recibe dict con keys: seguridad, webhooks"""
        if isinstance(datos, dict) and "seguridad" in datos:
            self.seguridad = datos["seguridad"]
            self.webhooks_config = datos.get("webhooks", self.webhooks_config)
            if hasattr(self, 'webhook'):
                self.webhook.configurar(self.webhooks_config)
        else:
            # Compatibilidad: solo seguridad
            self.seguridad = datos
        guardar(self.proyectos, self.tema, self.seguridad, self.webhooks_config)
        self._guardar_config_proyecto()
        self._iniciar_vigilancia()
        self.estado.setText("Ajustes guardados")

    # ---------- Proyectos ----------

    def _cargar_config_proyecto(self, nombre):
        """Carga tema/seguridad/webhooks/modelos/lanzamiento del proyecto.

        Los valores globales actúan como base y lo guardado en
        proyectos[nombre]["config"] gana a esa base.
        """
        local = leer_config_proyecto(nombre)
        self.tema = local.get("tema") or leer_tema()
        seg = leer_seguridad()
        seg.update(local.get("seguridad") or {})
        self.seguridad = seg
        wb = leer_webhooks()
        wb.update(local.get("webhooks") or {})
        self.webhooks_config = wb
        mod = leer_modelos()
        mod.update(local.get("modelos") or {})
        self._sel_modelos = mod
        lanz = dict(cfg.LAUNCH_DEFECTO)
        lanz.update(local.get("lanzamiento") or {})
        self._lanzamiento = lanz
        self.webhook.configurar(self.webhooks_config)

    def _guardar_config_proyecto(self):
        """Persiste la config del proyecto activo (tema, modelos, lanzamiento,
        seguridad y webhooks)."""
        if not self._nombre_activo:
            return
        conf = {
            "tema": self.tema,
            "modelos": self._sel_modelos,
            "lanzamiento": self._lanzamiento,
            "seguridad": self.seguridad,
            "webhooks": self.webhooks_config,
        }
        guardar_config_proyecto(self.proyectos, self._nombre_activo, conf)

    def _capturar_lanzamiento(self):
        """Guarda el estado actual de los widgets de lanzamiento."""
        self._lanzamiento = self.pan_ejec.config()

    def _cambiar_tema(self, nombre):
        self.tema = nombre
        guardar(self.proyectos, nombre)
        self._guardar_config_proyecto()
        self._aplicar_tema(nombre)

    def _proyecto_actual(self):
        nombre = self.cmb.currentText()
        if not nombre:
            return None
        info = self.proyectos.get(nombre) or {}
        ruta = info.get("ruta") or ""
        return (nombre, ruta) if ruta else None

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
        # Persiste la config del proyecto saliente antes de cambiar
        self._capturar_lanzamiento()
        self._guardar_config_proyecto()
        self._nombre_activo = n
        self._settings.setValue("proyecto/activo", n)
        guardar(self.proyectos, self.tema)
        self._cargar_proyecto()

    def _cargar_proyecto(self):
        p = self._proyecto_actual()
        if not p:
            self.estado.setText("Sin proyecto")
            self.pan_plan.clear()
            self.pan_lecciones.cargar(None)
            self.pan_git.cargar(None)
            self.pan_mapa.cargar(None)
            self.pan_logs.panel_loop.clear()
            self.pan_logs.panel_gate.clear()
            return
        nombre, ruta = p
        self._nombre_activo = nombre
        self._log_tam = 0
        self._cargar_config_proyecto(nombre)
        self.cmb_tema.blockSignals(True)
        self.cmb_tema.setCurrentText(self.tema)
        self.cmb_tema.blockSignals(False)
        self._aplicar_tema(self.tema)
        self.pan_seg.aplicar_config(self.seguridad, self.webhooks_config)
        self._iniciar_vigilancia()
        self.estado.setText(f"Proyecto: {nombre} — {ruta}")
        self.pan_plan.cargar(os.path.join(ruta, "plan.md"))
        self.pan_lecciones.cargar(os.path.join(ruta, "lecciones.md"))
        self.pan_git.cargar(ruta)
        self.pan_mapa.cargar(os.path.join(ruta, "mapeo.txt"))
        self.pan_ejec.actualizar_ramas(ruta)
        self.pan_ejec.aplicar_config(self._lanzamiento)
        self.pan_logs.panel_gate.clear()
        self.pan_logs.panel_loop.clear()
        self._log_marca = self._log_inicio = self._tam_log(ruta)
        self._tail_log()

        # instalar() es idempotente: propaga scripts y gate_checks NUEVOS de la
        # plantilla sin tocar lo que ya exista (plan.md, lecciones.md y
        # checks custom nunca se sobreescriben). Se llama siempre para que un
        # proyecto viejo reciba los checks nuevos.
        creados = plantillas.instalar(ruta)
        if creados:
            self.pan_logs.panel_loop.appendPlainText(
                f"[auto-provision] Plantillas instaladas: {', '.join(creados)}")
            # Si faltaba plan.md/lecciones.md, recargarlos en la UI
            if "plan.md" in creados or "lecciones.md" in creados:
                self.pan_plan.cargar(os.path.join(ruta, "plan.md"))
                self.pan_lecciones.cargar(os.path.join(ruta, "lecciones.md"))

        desactualizados = plantillas._desactualizados(ruta)
        if desactualizados:
            plantillas.actualizar(ruta)
            self.pan_logs.panel_loop.appendPlainText(
                f"[auto-update] Plantillas actualizadas: "
                f"{', '.join(desactualizados)}")

        self.pan_ejec.b_gate.setEnabled(
            os.path.exists(os.path.join(ruta, "gate.sh")))
        if not self.loop or self.loop.state() != QProcess.Running:
            self.pan_ejec.b_iniciar.setEnabled(True)
        self._aplicar_sel_modelos()

    def _agregar_proyecto(self):
        ruta = QFileDialog.getExistingDirectory(
            self, "Selecciona la raíz del proyecto")
        if not ruta:
            return
        nombre = os.path.basename(ruta)
        creados = plantillas.instalar(ruta)
        git = plantillas.inicializar_git(ruta)
        self.proyectos[nombre] = {"ruta": ruta}
        guardar(self.proyectos, self.tema)
        self.cmb.addItem(nombre)
        self.cmb.setCurrentText(nombre)
        detalles = []
        if creados:
            detalles.append("· " + "\n  · ".join(creados))
        if git["repo"] == "creado":
            detalles.append(
                f"git inicializado (rama master) con {git['archivos']} archivos")
        elif git["repo"] == "no-disponible":
            detalles.append(
                "⚠ git no disponible: revisa que esté instalado y tu "
                "identidad configurada (git config user.name/user.email)")
        if detalles:
            QMessageBox.information(
                self, "Proyecto listo",
                "Se preparó el proyecto:\n\n  · "
                + "\n  · ".join(detalles) +
                "\n\nPulsa '▶ Iniciar loop' cuando quieras arrancar.")
        else:
            QMessageBox.information(
                self, "Proyecto", "Ya tenía todos los archivos del autopiloto.")

    def _quitar_proyecto(self):
        nombre = self.cmb.currentText()
        if not nombre or nombre not in self.proyectos:
            return
        if self.loop and self.loop.state() == QProcess.Running:
            QMessageBox.warning(self, "Autopiloto en ejecución",
                                "Detén el loop antes de quitar un proyecto.")
            return
        info = self.proyectos.get(nombre) or {}
        ruta = info.get("ruta") or ""
        if ruta:
            resp = QMessageBox.question(
                self, "Quitar proyecto",
                "¿Eliminar el proyecto de la lista?\n\nTambién se borrarán sus "
                "archivos de autopiloto del disco:\n"
                "  · autopiloto.sh, gate.sh, mapear.sh\n"
                "  · plan.md, lecciones.md y progreso.log\n\n"
                "El resto del código del proyecto NO se toca.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if resp != QMessageBox.Yes:
                return
        else:
            # Proyecto sin ruta (config huérfana): solo se quita de la lista
            resp = QMessageBox.question(
                self, "Quitar proyecto",
                "Este proyecto no tiene una ruta válida asociada "
                "(config huérfana).\n\n¿Eliminarlo de la lista?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if resp != QMessageBox.Yes:
                return
        if self.proyectos.pop(nombre, None) is not None:
            eliminados = plantillas.quitar(ruta) if ruta else []
            guardar(self.proyectos, self.tema)
            # Si el proyecto quitado era el activo, olvidarlo también en el
            # settings: sin esto closeEvent/_cambiar_proyecto re-guardarían su
            # config (y una entrada huérfana) al reabrir la GUI.
            if getattr(self, "_nombre_activo", "") == nombre:
                self._nombre_activo = ""
                if hasattr(self, "_settings"):
                    self._settings.setValue("proyecto/activo", "")
            self.cmb.blockSignals(True)
            self.cmb.removeItem(self.cmb.currentIndex())
            self.cmb.blockSignals(False)
            if eliminados:
                QMessageBox.information(
                    self, "Proyecto eliminado",
                    "Eliminado de la lista y borrados:\n  · "
                    + "\n  · ".join(eliminados))
            elif not ruta:
                QMessageBox.information(
                    self, "Proyecto eliminado",
                    "Eliminado de la lista.")

    # ---------- Modelos ----------

    def _aplicar_sel_modelos(self):
        sug = modelos.sugerido(self._modelos)
        self.pan_ejec.aplicar_modelos({
            "tarea": self._sel_modelos.get("tarea") or sug,
            "revisor": self._sel_modelos.get("revisor") or sug,
        })

    def _guardar_sel_modelos(self, *_):
        self._sel_modelos = self.pan_ejec.modelos_seleccion()
        self._guardar_config_proyecto()
        guardar(self.proyectos, self.tema,
                seguridad=self.seguridad, modelos=self._sel_modelos)

    def _refrescar_modelos(self):
        modelos.invalidar_cache()
        nuevos = modelos.lista_modelos() or [cfg.MODELO_SUGERIDO]
        self._modelos = nuevos
        for sel in (self.pan_ejec.cmb_agente, self.pan_ejec.cmb_revisor):
            sel.activar_catalogo_global()
        self.pan_ejec.agregar_catalogo(nuevos)
        self.pan_ejec.info_modelos(
            len(nuevos), len(modelos.nombres_proveedores()))
        # invalidar_cache() también olvidó el sondeo de sesión: se relanza.
        self.pan_ejec.refrescar_agentes()
        self._aplicar_sel_modelos()
        self.estado.setText("Modelos refrescados")
        self._guardar_sel_modelos()

    # ---------- Internet ----------

    def _comprobar_net(self):
        net.verificar_async()
        self.pan_ejec.nota_net(net.ultimo_estado())

    # ---------- Loop ----------

    def _iniciar_loop(self):
        p = self._proyecto_actual()
        if not p:
            return
        estado_net = net.ultimo_estado()
        if estado_net is None:
            estado_net = net.hay_internet()
        if not estado_net:
            QMessageBox.warning(
                self, "Sin internet",
                "No hay conexión a internet.\n\nLos modelos IA de opencode "
                "no pueden responder y el loop se detendrá al arrancar. "
                "Conecta la red e inténtalo de nuevo.")
            return
        ruta = p[1]
        self._capturar_lanzamiento()
        self._guardar_config_proyecto()
        conf = self._lanzamiento
        nav_conf = self.pan_ejec.navegador_config()
        args = []
        if conf["hasta"]:
            args += ["--hasta", conf["hasta"]]
        if conf["padre"]:
            args += ["--padre", conf["padre"]]
        if conf.get("trabajo"):
            args += ["--trabajo", conf["trabajo"]]
        if conf["push"]:
            args.append("--push")

        env = dict(e.split("=", 1) for e in QProcess.systemEnvironment()
                   if "=" in e)

        # El agente CLI se pasa explícito. Si no está en el PATH del QProcess
        # (p. ej. GUI abierta sin ~/.opencode/bin), resolvemos su ruta absoluta
        # y la pasamos como CLI_<AGENTE> (que autopiloto.sh ya soporta). Si hay
        # PATH incompleto, se añade el dir del binario al PATH del subproceso.
        dirs_extra = set()
        mapa_cli = {"opencode": "CLI_OPENCODE", "codex": "CLI_CODEX",
                    "claude": "CLI_CLAUDE"}
        for clave, var in mapa_cli.items():
            binario = modelos.ruta_binario(clave)
            if binario:
                env[var] = binario
                dirs_extra.add(os.path.dirname(binario))
        if dirs_extra:
            env["PATH"] = ":".join(sorted(dirs_extra)) + (
                ":" + env["PATH"] if env.get("PATH") else "")

        # Un selector en "auto" no es el nombre del agente: lo resolvemos aquí
        # con la misma lista de preferencia que usa autopiloto.sh, para que el
        # log de la GUI y el motivo de lanzamiento coincidan con lo ejecutado.
        detectados = modelos.agentes_operativos()
        if not detectados:
            self.estado.setText(
                "No se detectó ningún agente CLI con sesión (opencode, codex o claude)")
            panel = self.pan_logs.panel_loop
            panel.clear()
            panel.appendPlainText(
                "> bash autopiloto.sh  (sin agentes utilizables: instala o "
                "inicia sesión en opencode, codex o claude)")
            self.pan_ejec.b_iniciar.setEnabled(True)
            return

        detectado_auto = detectados[0]
        agente_tarea = (detectado_auto if conf['agente_cli'] == "auto"
                        else conf['agente_cli'])
        agente_revisor = (detectado_auto if conf['revisor_cli'] == "auto"
                          else conf['revisor_cli'])
        env["MAX_ITER"] = str(conf['iteraciones'])
        env["AGENTE_TAREA"] = agente_tarea
        env["AGENTE_REVISOR"] = agente_revisor
        # AGENTES_PREFERIDOS sólo con agentes utilizables: si el revisor está
        # en "auto", autopiloto.sh busca otro en esta lista, y no debe caer en
        # un CLI instalado pero sin sesión (abortaría el loop).
        env["AGENTES_PREFERIDOS"] = " ".join(detectados)
        # El juez sigue al agente de la tarea salvo elección explícita.
        env["AGENTE_JUEZ"] = agente_tarea
        # Solo pasa --model si la selección es provider/model completo Y el
        # agente es opencode (codex y claude no aceptan --model aquí).
        modelo_tarea = (conf['agente'] if "/" in conf['agente']
                        and agente_tarea == "opencode" else "")
        modelo_revisor = (conf['revisor'] if "/" in conf['revisor']
                          and agente_revisor == "opencode" else "")
        modelo_nav = nav_conf['modelo'] if nav_conf['activo'] else ""
        env["MODELO_TAREA"] = modelo_tarea
        env["MODELO_REVISOR"] = modelo_revisor
        env["NAVEGADOR"] = '1' if nav_conf['activo'] else '0'
        env["MODELO_NAVEGADOR"] = modelo_nav
        env["REVISION_DUAL"] = '1' if conf['dual'] else '0'
        env["VOZ"] = '1' if conf['voz'] else '0'
        env["MAX_COSTO"] = str(conf['costo_max'])
        env["COSTO_POR_ITER"] = str(conf['costo_iter'])
        env["REVISION_MANUAL"] = '1' if conf['revision_manual'] else '0'
        env = [f"{k}={v}" for k, v in env.items()]

        panel = self.pan_logs.panel_loop
        panel.clear()
        panel.appendPlainText(
            f"> bash autopiloto.sh {' '.join(args)}  "
            f"(agente={agente_tarea}, modelo tarea={modelo_tarea or 'n/a'}, "
            f"revisor={agente_revisor}, modelo revisor="
            f"{modelo_revisor or 'n/a'}, "
            f"nav={'on' if nav_conf['activo'] else 'off'}, "
            f"dual={conf['dual']}, "
            f"costo/iter={conf['costo_iter']} USD, iter={conf['iteraciones']})")
        self.loop = Proceso(panel, on_fin=self._loop_fin)
        self.loop.setWorkingDirectory(ruta)
        self.loop.setEnvironment(env)
        self.loop.start("bash", ["autopiloto.sh"] + args)
        self.pan_ejec.b_iniciar.setEnabled(False)
        self.pan_ejec.b_detener.setEnabled(True)
        self.pan_ejec.b_gate.setEnabled(False)
        self.cmb.setEnabled(False)
        self.timer.start(cfg.TIMER_TAIL_MS)
        self._inicio_loop_ts = time.time()
        self._log_marca = self._log_inicio = self._tam_log(ruta)
        self._iter_actual = 0
        self._set_fase_loop(0, int(conf['iteraciones'] or 0), corriendo=True)

        # Webhook: inicio
        self._webhook_enviar("inicio", {
            "proyecto": self._nombre_activo,
            "modelo_tarea": conf['agente'],
            "modelo_revisor": conf['revisor'],
        })

    def _limpiar_sesiones_proyecto(self, ruta_proyecto, desde_ms):
        """Borra las sesiones de opencode que el loop creó en el proyecto.

        Criterio: directory == proyecto y creadas después del inicio del run.
        Nota: autopiloto.sh también limpia al salir (trap EXIT); esto cubre
        la detención manual (la GUI manda SIGTERM; sólo si no termina en unos
        segundos pasa a SIGKILL, y entonces el trap bash no llega a correr).

        Se ejecuta dentro de un `Trabajo` porque son `subprocess.run` con
        timeout=120 s: uno para listar y uno por cada sesión a borrar, así que
        con 10 sesiones eran hasta 22 min. En el hilo de la UI congelaba la
        ventana justo después de pulsar Detener, y los botones seguían
        deshabilitados hasta terminar.

        Devuelve cuántas borró y NO toca ningún widget: el texto del log lo
        escribe `_limpiar_sesiones_hecho`, que ya corre en el hilo de la UI.
        """
        if not ruta_proyecto:
            return 0
        binario = ""
        for cand in ("opencode",):
            ruta = shutil.which(cand)
            if ruta:
                binario = ruta
                break
            candidata = os.path.expanduser(f"~/.{cand}/bin/{cand}")
            if os.path.isfile(candidata) and os.access(candidata, os.X_OK):
                binario = candidata
                break
        if not binario:
            return 0

        def _ejecutar(*args):
            try:
                return subprocess.run(
                    [binario, *args],
                    capture_output=True, text=True, timeout=120,
                    cwd=ruta_proyecto,
                )
            except (subprocess.TimeoutExpired, OSError):
                return None

        res = _ejecutar("session", "list", "--format", "json")
        if not res or res.returncode != 0:
            return 0
        try:
            sesiones = json.loads(res.stdout or "[]")
        except json.JSONDecodeError:
            return 0
        ids = [
            s["id"] for s in sesiones
            if s.get("directory") == ruta_proyecto
            and int(s.get("created") or 0) >= desde_ms
        ]
        for id_ in ids:
            _ejecutar("session", "delete", id_)
        return len(ids)

    def _limpiar_sesiones_hecho(self, borradas):
        """Slot de UI: refleja en el log lo que borró el hilo de limpieza."""
        if borradas:
            self.pan_logs.panel_loop.appendPlainText(
                f"[autopiloto] 🧹 Sesiones opencode eliminadas: {borradas}")

    def _programar_limpiar_sesiones(self, ruta_proyecto):
        """Lanza la limpieza de sesiones en segundo plano.

        `desde_ms` se calcula aquí, en el hilo de la UI, para que sea el
        instante real de la parada y no el momento en que el hilo llegue a
        leerlo.
        """
        if not ruta_proyecto:
            return
        if self._worker_sesiones_limpieza is not None \
                and self._worker_sesiones_limpieza.isRunning():
            return
        desde_ms = int(self._inicio_loop_ts * 1000) if self._inicio_loop_ts else 0
        worker = Trabajo(
            lambda: self._limpiar_sesiones_proyecto(ruta_proyecto, desde_ms))
        worker.conectar(self._limpiar_sesiones_hecho)
        worker.liberar(self, "_worker_sesiones_limpieza")
        worker.start()
        self._worker_sesiones_limpieza = worker

    def _loop_fin(self):
        p = self._proyecto_actual()
        self.pan_ejec.b_iniciar.setEnabled(True)
        self.pan_ejec.b_detener.setEnabled(False)
        if p:
            self.pan_ejec.b_gate.setEnabled(
                os.path.exists(os.path.join(p[1], "gate.sh")))
        self.cmb.setEnabled(True)
        self.timer.stop()
        self._revision_pendiente = False
        self.pan_ejec.panel_revision.ocultar()
        self._set_fase_loop(0, 0, corriendo=False)
        if p:
            self.pan_plan.cargar(os.path.join(p[1], "plan.md"))
            self.pan_lecciones.cargar(os.path.join(p[1], "lecciones.md"))
            self.pan_git.cargar(p[1])
            self.pan_mapa.cargar(os.path.join(p[1], "mapeo.txt"))

        # Webhook: fin
        if self._inicio_loop_ts:
            duracion_min = (time.time() - self._inicio_loop_ts) / 60.0
        else:
            duracion_min = 0.0
        # Parsear log para resumen (solo lo de ESTE run: desde _log_inicio)
        if p:
            log = os.path.join(p[1], "progreso.log")
            try:
                with open(log, "rb") as f:
                    f.seek(self._log_inicio)
                    contenido = f.read().decode("utf-8", "replace")
                hechas = contenido.count("✔ commit:") + contenido.count("✔ tarea completada")
                bloqueadas = contenido.count("tarea bloqueada")
                total = hechas + bloqueadas
                # Coste: exacto por iteración si existe, si no acumulado
                costes_iter = re.findall(r"Costo iteración \d+:\s*([\d.]+)\s*USD", contenido)
                if costes_iter:
                    coste = round(sum(float(c) for c in costes_iter), 2)
                else:
                    costes = re.findall(r"Costo estimado acumulado:\s*([\d.]+)\s*USD", contenido)
                    coste = float(costes[-1]) if costes else 0.0
            except Exception:
                hechas = bloqueadas = total = 0
                coste = 0.0
            self._webhook_enviar("fin", {
                "hechas": hechas,
                "total": total,
                "coste": coste,
                "duracion_min": round(duracion_min, 1),
            })

        # La limpieza de sesiones va la última y en segundo plano: el bucle de
        # eventos debe quedar repintado y usable antes de lanzarla.
        if p:
            self._programar_limpiar_sesiones(p[1])

    def _detener_loop(self):
        if self.loop and self.loop.state() == QProcess.Running:
            self.pan_logs.panel_loop.appendPlainText("[manual] deteniendo el loop…")
            self.loop.terminate()
            # No `waitForFinished(5000)`: bloquea el hilo de la UI cinco
            # segundos en el botón que el usuario acaba de pulsar. El escalado
            # a SIGKILL lo hace el timer.
            if self.loop.state() != QProcess.NotRunning:
                QTimer.singleShot(5000, self._loop_forzar_kill)

    def _loop_forzar_kill(self):
        """Sube a SIGKILL si el loop no respeta el SIGTERM del temporizador."""
        if self.loop and self.loop.state() == QProcess.Running:
            self.pan_logs.panel_loop.appendPlainText(
                "[manual] el loop no responde a SIGTERM; forzando con SIGKILL…")
            self.loop.kill()

    def _tail_log(self):
        p = self._proyecto_actual()
        if not p:
            return
        log = os.path.join(p[1], "progreso.log")
        try:
            tam = os.path.getsize(log)
        except OSError:
            return
        if tam == self._log_tam:
            return  # sin cambios: no releer ni repintar
        self._log_tam = tam
        inicio = max(0, tam - cfg.TAIL_LOG_BYTES)
        try:
            with open(log, "rb") as f:
                f.seek(inicio)
                datos = f.read().decode("utf-8", "replace")
        except OSError:
            return
        if inicio > 0 and "\n" in datos:
            datos = datos[datos.index("\n") + 1:]  # descarta línea cortada
        self.pan_logs.panel_loop.setPlainText(datos)
        self.pan_logs.panel_loop.ensureCursorVisible()

        # Detectar eventos SOLO en lo nuevo desde la última lectura (edge-triggered:
        # evita reenviar el mismo webhook en cada refresco). No usar `datos` (ventana
        # de tail) porque repite contenido ya visto en cada refresco.
        if self._log_marca > tam:
            self._log_marca = tam  # log truncado/rotado
        if tam > self._log_marca:
            try:
                with open(log, "rb") as f:
                    f.seek(self._log_marca)
                    nuevo = f.read().decode("utf-8", "replace")
            except OSError:
                nuevo = ""
            self._log_marca = tam
            self._procesar_eventos_log(nuevo)

        # Píldora y stepper: iteración en curso + fase detectada
        corriendo = bool(self.loop) and self.loop.state() == QProcess.Running
        its = re.findall(r"== Iteración\s+(\d+)", datos)
        if its:
            self._iter_actual = max(int(x) for x in its)
        if corriendo:
            total = int(self._lanzamiento.get("iteraciones") or 0)
            self._set_fase_loop(self._iter_actual, total, corriendo=True)

    def _procesar_eventos_log(self, texto):
        """Dispara webhooks/avisos a partir de un fragmento NUEVO del log."""
        bajo = texto.lower()
        if "tokens/cuota agotados" in bajo or "cuota agotada" in bajo:
            self._webhook_enviar("tokens", {})
        elif "error crítico" in bajo or "abortado:" in bajo:
            self._webhook_enviar("error", {"detalle": "Ver progreso.log"})
        if "tarea bloqueada" in bajo:
            self._notificar_tarea_bloqueada(texto)

    def _tam_log(self, ruta):
        """Tamaño de progreso.log en bytes (0 si no existe)."""
        try:
            return os.path.getsize(os.path.join(ruta, "progreso.log"))
        except OSError:
            return 0

    def _notificar_tarea_bloqueada(self, log_texto):
        # Extraer nombre de la tarea del log
        m = re.search(r"tarea bloqueada[:\s]+([^\n]+)", log_texto, re.IGNORECASE)
        tarea = m.group(1).strip() if m else "desconocida"
        self.estado.setText(f"⚠ Tarea bloqueada: {tarea}")
        # Sonido de alerta
        try:
            import subprocess
            subprocess.run(["notify-send", "Autopiloto", f"Tarea bloqueada: {tarea}"], timeout=2)
        except Exception:
            pass
        # Beep
        try:
            sys.stdout.write('\a')
            sys.stdout.flush()
        except Exception:
            pass

        # Webhook: bloqueada
        self._webhook_enviar("bloqueada", {"tarea": tarea})

    def _comprobar_revision_pendiente(self):
        """Detecta si autopiloto.sh está esperando revisión manual."""
        if not self.loop or self.loop.state() != QProcess.Running:
            if self._revision_pendiente:
                self._revision_pendiente = False
                self.pan_ejec.panel_revision.ocultar()
            return
        if not self.pan_ejec.revision_manual_activa():
            return
        p = self._proyecto_actual()
        if not p:
            return
        ruta = p[1]
        dir_revision = os.path.join(ruta, ".autopiloto_review")
        archivo_esperando = os.path.join(dir_revision, "waiting")
        archivo_diff = os.path.join(dir_revision, "diff.txt")
        archivo_tarea = os.path.join(dir_revision, "tarea.txt")

        if os.path.exists(archivo_esperando) and not self._revision_pendiente:
            # Leer tarea y diff
            tarea = ""
            try:
                with open(archivo_tarea, encoding="utf-8") as f:
                    tarea = f.read().strip()
            except OSError:
                pass
            self._revision_pendiente = True
            self.pan_ejec.panel_revision.mostrar_revision(ruta, tarea, archivo_diff, os.path.join(dir_revision, "decision"))
            self.pan_logs.panel_loop.appendPlainText(f"\n[GUI] ⏸ Revisión manual requerida para: {tarea}")

        elif not os.path.exists(archivo_esperando) and self._revision_pendiente:
            # La revisión ya no está pendiente (se resolvió)
            self._revision_pendiente = False
            self.pan_ejec.panel_revision.ocultar()

    def _revision_aprobada(self):
        self._revision_pendiente = False
        self.estado.setText("✓ Diff aprobado, continuando loop…")

    def _revision_rechazada(self, motivo):
        self._revision_pendiente = False
        self.estado.setText(f"✗ Diff rechazado: {motivo[:60]}…")
        self.pan_logs.panel_loop.appendPlainText(f"[GUI] Rechazado: {motivo}")

    # ---------- Gate ----------

    def _ejecutar_gate(self):
        p = self._proyecto_actual()
        if not p:
            return
        _, ruta = p
        panel = self.pan_logs.panel_gate
        panel.clear()
        panel.appendPlainText("> bash gate.sh")
        self.gate = Proceso(panel)
        self.gate.setWorkingDirectory(ruta)
        self.gate.start("bash", ["gate.sh"])

    # ---------- Webhooks ----------

    def _webhook_enviar(self, evento: str, datos: dict):
        """Envía webhook si el evento está habilitado."""
        if hasattr(self, 'webhook') and self.webhook:
            # Añadir proyecto si no está
            if "proyecto" not in datos:
                datos["proyecto"] = self._nombre_activo
            self.webhook.enviar(evento, datos)

    # ---------- Métricas ----------

    def _actualizar_metricas(self):
        p = self._proyecto_actual()
        if p:
            self.pan_metricas.cargar(p[1])

    # ---------- Rollback (Revert commit) ----------

    def _ejecutar_revert(self, sha: str):
        p = self._proyecto_actual()
        if not p:
            return
        _, ruta = p

        # Confirmar
        resp = QMessageBox.question(
            self, "Revertir commit",
            f"¿Revertir el commit {sha[:8]}?\n\n"
            f"Se hará: git revert --no-commit {sha} && git commit -m 'revert: ...'\n"
            f"Esto creará un nuevo commit que deshace los cambios.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if resp != QMessageBox.Yes:
            return

        self.estado.setText(f"Revirtiendo commit {sha[:8]}...")
        worker = Trabajo(lambda: self._git_revert(ruta, sha))
        worker.conectar(lambda ok: self._post_revert(ok, sha))
        worker.liberar(self, "_worker_revert")
        worker.start()
        self._worker_revert = worker

    def _git_revert(self, ruta: str, sha: str) -> bool:
        try:
            import subprocess
            # Revertir sin commit
            r1 = subprocess.run(["git", "revert", "--no-commit", sha],
                                cwd=ruta, capture_output=True, text=True, timeout=30)
            if r1.returncode != 0:
                return False
            # Commit del revert
            r2 = subprocess.run(["git", "commit", "-m", f"revert: {sha[:8]}"],
                                cwd=ruta, capture_output=True, text=True, timeout=30)
            return r2.returncode == 0
        except Exception:
            return False

    def closeEvent(self, event):
        """Guarda tamaño/posición/estado y la config del proyecto activo. Limpia timers y procesos."""
        if hasattr(self, "pan_ejec"):
            self._capturar_lanzamiento()
            self._guardar_config_proyecto()
        self._settings.setValue("ventana/geometria", self.saveGeometry())
        # Detener timers
        for t in (self.timer, self.timer_temp, self.timer_net,
                  self.timer_revision, self.timer_metricas,
                  self.timer_plan, self.timer_lecciones):
            t.stop()
        # Terminar proceso loop si corre (SIGTERM y, si no muere, SIGKILL)
        if self.loop and self.loop.state() == QProcess.Running:
            self.loop.terminate()
            if not self.loop.waitForFinished(5000):
                self.loop.kill()
                self.loop.waitForFinished(1000)
        super().closeEvent(event)

    def _post_revert(self, ok: bool, sha: str):
        if ok:
            self.estado.setText(f"✓ Commit {sha[:8]} revertido")
            p = self._proyecto_actual()
            if p:
                self.pan_git.cargar(p[1])
                self.pan_plan.cargar(os.path.join(p[1], "plan.md"))
                self.pan_mapa.cargar(os.path.join(p[1], "mapeo.txt"))
                self._tail_log()
        else:
            self.estado.setText(f"✗ Error revertiendo {sha[:8]}")
            QMessageBox.warning(self, "Error", f"No se pudo revertir el commit {sha[:8]}")

    def _limpiar_git_framework(self):
        """Asegura .gitignore con el bloque autopiloto y deja de trackear el framework."""
        p = self._proyecto_actual()
        if not p:
            return
        _, ruta = p
        resp = QMessageBox.question(
            self, "Framework fuera de git",
            "Se hará:\n"
            "1) Añadir el bloque autopiloto al .gitignore del proyecto\n"
            "2) git rm --cached de autopiloto.sh, gate.sh, gate_checks/, plan.md,\n"
            "   lecciones.md, mapeo.txt, progreso.log, metrics.jsonl, etc.\n\n"
            "Los archivos SIGUEN en disco (el autopiloto los necesita); solo "
            "dejan de estar en el repo git.\n¿Continuar?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if resp != QMessageBox.Yes:
            return

        def trabajo():
            modificado = plantillas.asegurar_gitignore(ruta)
            salidos = plantillas.quitar_framework_del_git(ruta)
            return (modificado, len(salidos))

        self.estado.setText("Aplicando limpieza del framework en git...")
        worker = Trabajo(trabajo)
        worker.conectar(self._post_limpiar_git_framework)
        worker.liberar(self, "_worker_limpiar")
        worker.start()
        self._worker_limpiar = worker

    def _post_limpiar_git_framework(self, res):
        modificado, salidos = res
        if salidos or modificado:
            self.estado.setText(f"✓ Gitignored actualizado y {salidos} archivos "
                                "dejaron de trackearse (quedan sin commitear; "
                                "haz commit en el repo del proyecto si quieres "
                                "persistirlo)")
            msg = (f"· .gitignore actualizado: {modificado}\n"
                   f"· archivos fuera de seguimiento: {salidos}")
            QMessageBox.information(self, "Framework fuera de git", msg)
        else:
            self.estado.setText("Nada que limpiar (ya estaba limpio)")
        p = self._proyecto_actual()
        if p:
            self.pan_git.cargar(p[1])

def _resolver_registro_corrupto(exc):
    """Pregunta al usuario qué hacer con un registro corrupto.

    Devuelve True si debemos seguir arrancando (ha aceptado empezar de cero,
    con los datos a salvo en la copia .corrupto), False si debe salir.
    """
    caja = QMessageBox()
    caja.setIcon(QMessageBox.Critical)
    caja.setWindowTitle("Registro de proyectos dañado")
    caja.setText(
        f"No se pudo leer el registro de proyectos:\n{exc.ruta}"
    )
    caja.setInformativeText(
        "Puede estar truncado o editado a mano. Se ha guardado una copia "
        f"íntegra en:\n{exc.copia}\n\n"
        "Si sales ahora, el archivo se queda donde está y podrás repararlo "
        "o restaurarlo a mano. Si prefieres continuar, la lista de proyectos "
        "empezará vacía (tus datos siguen en la copia)."
    )
    salir = caja.addButton("Salir y repararlo a mano", QMessageBox.RejectRole)
    seguir = caja.addButton(
        "Empezar de cero (copia conservada)", QMessageBox.DestructiveRole
    )
    caja.setDefaultButton(salir)
    caja.exec()
    return caja.clickedButton() is seguir


def main():
    app = QApplication(sys.argv)

    # El registro de proyectos es el estado completo del usuario (proyectos,
    # tema, webhooks, modelos). Si su JSON está corrupto hay que PARAR aquí:
    # Ventana.__init__ carga el registro y, si sale vacío, lo vuelve a guardar,
    # así que un JSON roto se convertía en "todos los proyectos borrados" de
    # forma silenciosa en el arranque.
    try:
        verificar_registro()
    except RegistroCorrupto as exc:
        if not _resolver_registro_corrupto(exc):
            return
        descartar_registro_corrupto()

    inicializar_temas()
    icono = os.path.join(os.path.dirname(__file__), "icono.svg")
    if os.path.exists(icono):
        app.setWindowIcon(QIcon(icono))
    ventana = Ventana()
    ventana.show()
    sys.exit(app.exec())
