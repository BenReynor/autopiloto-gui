"""Ventana principal del panel de control (orquestación).

La UI de cada pestaña vive en `paneles.py`; aquí solo se conectan señales,
se gestionan los procesos (loop/gate), la configuración persistida y la
vigilancia (temperatura e internet).
"""

import os
import re
import sys
import time

from PySide6.QtCore import QProcess, QSettings, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import configuracion as cfg
from . import modelos, net, plantillas, sensor
from .paneles import (
    AvisoTemperatura,
    PanelEjecucion,
    PanelGit,
    PanelLogs,
    PanelPlan,
    PanelSeguridad,
)
from .paneles_metricas import PanelMetricas
from .proceso import Proceso, Trabajo
from .proyectos import (
    cargar,
    guardar,
    leer_modelos,
    leer_seguridad,
    leer_tema,
    leer_webhooks,
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
            if os.path.isfile(os.path.join(candidato, "plan.md")):
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
        self._revision_pendiente = False
        self._ultima_bloqueada = False
        self.tema = leer_tema()
        self.seguridad = leer_seguridad()
        self.webhooks_config = leer_webhooks()
        self._modelos = []
        self._sel_modelos = leer_modelos()
        self._inicio_loop_ts = None

        # Webhook manager
        self.webhook = WebhookManager(self.webhooks_config)

        self._ui()
        self._aplicar_tema(self.tema)
        self._cargar_proyecto()
        self._cargar_modelos_en_fondo()
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

    def _cargar_modelos_en_fondo(self):
        """Consulta opencode/models.dev sin bloquear el arranque."""
        self._worker_modelos = Trabajo(modelos.lista_modelos)
        self._worker_modelos.listo.connect(self._modelos_cargados)
        self._worker_modelos.start()

    def _modelos_cargados(self, lista):
        self._worker_modelos = None
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
        b_quitar = QPushButton("Quitar")
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

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self.pan_plan = PanelPlan()
        self.pan_plan.guardado.connect(
            lambda ruta: self.estado.setText(f"plan.md guardado ({ruta})"))
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
        self.pan_logs = PanelLogs()
        self.pan_metricas = PanelMetricas()
        self.pan_seg = PanelSeguridad(self.seguridad, self.webhooks_config)
        self.pan_seg.guardar_ajustes.connect(self._guardar_seguridad)
        self.tabs.addTab(self.pan_plan, "Plan")
        self.tabs.addTab(self.pan_ejec, "Ejecución")
        self.tabs.addTab(self.pan_logs, "Logs")
        self.tabs.addTab(self.pan_git, "Git")
        self.tabs.addTab(self.pan_metricas, "📊 Métricas")
        self.tabs.addTab(self.pan_seg, "🛡 Seguridad")

        self.estado = QLabel("Sin proyecto")
        root.addWidget(self.estado)

    def _aplicar_tema(self, nombre):
        temas = obtener_temas()
        if nombre in temas:
            QApplication.instance().setStyleSheet(temas[nombre])

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
        self._iniciar_vigilancia()
        self.estado.setText("Ajustes guardados")

    # ---------- Proyectos ----------

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
        self._settings.setValue("proyecto/activo", n)
        guardar(self.proyectos, self.tema)
        self._cargar_proyecto()

    def _cargar_proyecto(self):
        p = self._proyecto_actual()
        if not p:
            self.estado.setText("Sin proyecto")
            self.pan_plan.clear()
            self.pan_git.cargar(None)
            self.pan_logs.panel_loop.clear()
            self.pan_logs.panel_gate.clear()
            return
        nombre, ruta = p
        self._nombre_activo = nombre
        self._log_tam = 0
        self.estado.setText(f"Proyecto: {nombre} — {ruta}")
        self.pan_plan.cargar(ruta)
        self.pan_git.cargar(ruta)
        self.pan_ejec.actualizar_ramas(ruta)
        self.pan_logs.panel_gate.clear()
        self.pan_logs.panel_loop.clear()
        self._tail_log()

        faltan = plantillas.faltan(ruta)
        if faltan:
            plantillas.instalar(ruta)
            self.pan_logs.panel_loop.appendPlainText(
                f"[auto-provision] Plantillas instaladas: {', '.join(faltan)}")

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

    def _quitar_proyecto(self):
        nombre = self.cmb.currentText()
        p = self._proyecto_actual()
        if not nombre or not p:
            return
        if self.loop and self.loop.state() == QProcess.Running:
            QMessageBox.warning(self, "Autopiloto en ejecución",
                                "Detén el loop antes de quitar un proyecto.")
            return
        _, ruta = p
        resp = QMessageBox.question(
            self, "Quitar proyecto",
            "¿Eliminar el proyecto de la lista?\n\nTambién se borrarán sus "
            "archivos de autopiloto del disco:\n"
            "  · autopiloto.sh, gate.sh, mapear.sh\n"
            "  · plan.md y progreso.log\n\n"
            "El resto del código del proyecto NO se toca.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if resp != QMessageBox.Yes:
            return
        if self.proyectos.pop(nombre, None) is not None:
            eliminados = plantillas.quitar(ruta)
            guardar(self.proyectos, self.tema)
            self.cmb.removeItem(self.cmb.currentIndex())
            if eliminados:
                QMessageBox.information(
                    self, "Proyecto eliminado",
                    "Eliminado de la lista y borrados:\n  · "
                    + "\n  · ".join(eliminados))

    # ---------- Modelos ----------

    def _aplicar_sel_modelos(self):
        sug = modelos.sugerido(self._modelos)
        self.pan_ejec.aplicar_modelos({
            "tarea": self._sel_modelos.get("tarea") or sug,
            "revisor": self._sel_modelos.get("revisor") or sug,
        })

    def _guardar_sel_modelos(self, *_):
        self._sel_modelos = self.pan_ejec.modelos_seleccion()
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
        conf = self.pan_ejec.config()
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

        env = list(QProcess.systemEnvironment())
        env.append(f"MAX_ITER={conf['iteraciones']}")
        # El agente CLI (opencode/codex/claude/auto) se pasa explícito.
        env.append(f"AGENTE_TAREA={conf['agente_cli']}")
        env.append(f"AGENTE_REVISOR={conf['revisor_cli']}")
        # Solo pasa --model si la selección es provider/model completo;
        # autopiloto.sh lo ignora para codex/claude.
        modelo_tarea = conf['agente'] if "/" in conf['agente'] else ""
        modelo_revisor = conf['revisor'] if "/" in conf['revisor'] else ""
        modelo_nav = nav_conf['modelo'] if nav_conf['activo'] else ""
        env.append(f"MODELO_TAREA={modelo_tarea}")
        env.append(f"MODELO_REVISOR={modelo_revisor}")
        env.append(f"NAVEGADOR={'1' if nav_conf['activo'] else '0'}")
        env.append(f"MODELO_NAVEGADOR={modelo_nav}")
        env.append(f"REVISION_DUAL={'1' if conf['dual'] else '0'}")
        env.append(f"VOZ={'1' if conf['voz'] else '0'}")
        env.append(f"MAX_COSTO={conf['costo_max']}")
        env.append(f"COSTO_POR_ITER={conf['costo_iter']}")
        env.append(f"REVISION_MANUAL={'1' if conf['revision_manual'] else '0'}")

        panel = self.pan_ejec.panel_loop
        panel.clear()
        panel.appendPlainText(
            f"> bash autopiloto.sh {' '.join(args)}  "
            f"(agente={conf['agente_cli']}, modelo tarea={conf['agente']}, "
            f"revisor={conf['revisor_cli']}, modelo revisor={conf['revisor']}, "
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

        # Webhook: inicio
        self._webhook_enviar("inicio", {
            "proyecto": self._nombre_activo,
            "modelo_tarea": conf['agente'],
            "modelo_revisor": conf['revisor'],
        })

    def _loop_fin(self):
        self.pan_ejec.b_iniciar.setEnabled(True)
        self.pan_ejec.b_detener.setEnabled(False)
        p = self._proyecto_actual()
        if p:
            self.pan_ejec.b_gate.setEnabled(
                os.path.exists(os.path.join(p[1], "gate.sh")))
        self.cmb.setEnabled(True)
        self.timer.stop()
        if p:
            self.pan_plan.cargar(p[1])
            self.pan_git.cargar(p[1])

        # Webhook: fin
        if self._inicio_loop_ts:
            duracion_min = (time.time() - self._inicio_loop_ts) / 60.0
        else:
            duracion_min = 0.0
        # Parsear log para resumen
        if p:
            log = os.path.join(p[1], "progreso.log")
            try:
                with open(log, encoding="utf-8", errors="replace") as f:
                    contenido = f.read()
                hechas = contenido.count("✔ commit:") + contenido.count("✔ tarea completada")
                bloqueadas = contenido.count("tarea bloqueada")
                total = hechas + bloqueadas
                # Coste del log
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

    def _detener_loop(self):
        if self.loop and self.loop.state() == QProcess.Running:
            self.pan_logs.panel_loop.appendPlainText("[manual] deteniendo el loop…")
            self.loop.terminate()
            if not self.loop.waitForFinished(5000):
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

        # Detectar eventos para webhooks
        if "tokens agotados" in datos.lower() or "cuota agotada" in datos.lower():
            self._webhook_enviar("tokens", {})
        elif "error crítico" in datos.lower() or "abortado:" in datos.lower():
            self._webhook_enviar("error", {"detalle": "Ver progreso.log"})

        # Detectar tarea bloqueada y notificar
        if "tarea bloqueada" in datos.lower() and not self._ultima_bloqueada:
            self._ultima_bloqueada = True
            self._notificar_tarea_bloqueada(datos)
        elif "tarea bloqueada" not in datos.lower():
            self._ultima_bloqueada = False

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
            self._revision_pendiente = False
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
            self.pan_ejec.panel_loop.appendPlainText(f"\n[GUI] ⏸ Revisión manual requerida para: {tarea}")

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
        self.pan_ejec.panel_loop.appendPlainText(f"[GUI] Rechazado: {motivo}")

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
        worker.listo.connect(lambda ok: self._post_revert(ok, sha))
        worker.start()

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
        """Guarda tamaño/posición/estado de la ventana para la próxima sesión."""
        self._settings.setValue("ventana/geometria", self.saveGeometry())
        super().closeEvent(event)

    def _post_revert(self, ok: bool, sha: str):
        if ok:
            self.estado.setText(f"✓ Commit {sha[:8]} revertido")
            p = self._proyecto_actual()
            if p:
                self.pan_git.cargar(p[1])
                self.pan_plan.cargar(p[1])
                self._tail_log()
        else:
            self.estado.setText(f"✗ Error revertiendo {sha[:8]}")
            QMessageBox.warning(self, "Error", f"No se pudo revertir el commit {sha[:8]}")


def main():
    app = QApplication(sys.argv)
    inicializar_temas()
    icono = os.path.join(os.path.dirname(__file__), "icono.svg")
    if os.path.exists(icono):
        app.setWindowIcon(QIcon(icono))
    ventana = Ventana()
    ventana.show()
    sys.exit(app.exec())
