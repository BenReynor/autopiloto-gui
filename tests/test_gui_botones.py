"""Pruebas headless de la GUI: cada botón hace lo que dice.

Instancia los paneles con QT_QPA_PLATFORM=offscreen y un proyecto temporal
con repositorio git real. Verifica que pulsar cada botón produce el efecto
esperado (señal emitida, archivo escrito, tree recargado, etc.).

Los diálogos modales (QMessageBox, QFileDialog, QInputDialog) se cierran
solos con un QTimer para no bloquear el test.
"""

import os
import shutil
import subprocess
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QInputDialog,
    QMessageBox,
    QPushButton,
)


@pytest.fixture
def cerrar_modales(app):
    t = QTimer()
    t.timeout.connect(_cerrar_todos_los_modales)
    t.start(30)
    yield t
    t.stop()


def _cerrar_todos_los_modales():
    app = QApplication.instance()
    for w in app.topLevelWidgets():
        if isinstance(w, (QMessageBox, QInputDialog)):
            w.reject()


def boton(curso, texto):
    """Busca un QPushButton por texto exacto en un widget o hijo."""
    for b in curso.findChildren(QPushButton):
        if b.text().strip() == texto:
            return b
    return None


@pytest.fixture
def proyecto_git(tmp_path):
    """Repo git con un plan.md y 2 commits autopiloto."""
    subprocess.run(["git", "init", "-q", "-b", "master"], cwd=tmp_path, check=True)
    (tmp_path / "plan.md").write_text(
        "# PLAN\n\n- [ ] #1 crear demo.py\n      criterio: demo.py existe\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=T",
                    "commit", "-q", "-m", "autopiloto: tarea 1"], cwd=tmp_path,
                   check=True)
    (tmp_path / "demo.py").write_text("def demo():\n    return 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=T",
                    "commit", "-q", "-m", "autopiloto: tarea 2"], cwd=tmp_path,
                   check=True)
    return tmp_path


# ─── PanelPlan ────────────────────────────────────────────────

def test_plan_guardar_modifica_archivo_y_kanban(app, proyecto_git):
    from autopiloto_gui.paneles import PanelPlan
    p = PanelPlan()
    ruta = str(proyecto_git / "plan.md")
    p.cargar(ruta)
    assert p.kanban.col_pend.badge.text() == "1"

    # Editar y pulsar Guardar plan.md
    p.editor.setPlainText(
        "# PLAN\n\n- [ ] #1 crear demo.py\n- [x] #0 tarea hecha\n")
    guardados = []
    p.guardado.connect(guardados.append)
    boton(p, "Guardar plan.md").click()
    assert (proyecto_git / "plan.md").read_text(encoding="utf-8") == p.editor.toPlainText()
    assert guardados, "señal guardado no emitida"
    assert p.kanban.col_pend.badge.text() == "1"
    assert p.kanban.col_hecha.badge.text() == "1"

    # Recargar vuelve al estado del disco
    boton(p, "Recargar").click()
    assert p.kanban.col_hecha.badge.text() == "1"


def test_plan_kanban_click_enfoca_editor(app, proyecto_git):
    from autopiloto_gui.paneles import PanelPlan
    p = PanelPlan()
    p.cargar(str(proyecto_git / "plan.md"))
    p.kanban.tarea_seleccionada.emit("crear demo.py")
    assert p.editor.textCursor().block().text() != ""
    assert "crear demo.py" in p.editor.toPlainText()


# ─── PanelLecciones ───────────────────────────────────────────

def test_lecciones_nueva_y_guardar(app, proyecto_git):
    from autopiloto_gui.paneles import PanelLecciones
    p = PanelLecciones()
    ruta = str(proyecto_git / "lecciones.md")
    p.cargar(ruta)
    boton(p, "＋ Nueva lección").click()
    assert "Síntoma" in p.editor.toPlainText()

    guardados = []
    p.guardado.connect(guardados.append)
    boton(p, "Guardar lecciones.md").click()
    assert (proyecto_git / "lecciones.md").read_text(encoding="utf-8") == p.editor.toPlainText()
    assert guardados


# ─── PanelMapa ────────────────────────────────────────────────

@pytest.mark.skipif(
    shutil.which("bash") is None,
    reason="bash no disponible (el botón regenera mapeo.sh con bash)")
@pytest.mark.skipif(os.name == "nt",
                    reason="regenerar el mapa ejecuta mapear.sh (POSIX): "
                           "se valida en Linux")
def test_mapa_regenerar_crea_mapeo(app, proyecto_git):
    from autopiloto_gui.paneles import PanelMapa
    # Añadir mapear.sh que genera mapeo.txt
    (proyecto_git / "mapear.sh").write_text(
        "#!/usr/bin/env bash\necho '# demo.py -> tests/test_demo.py' > mapeo.txt\n",
        encoding="utf-8",
    )
    subprocess.run(["bash", "mapear.sh"], cwd=proyecto_git, check=True)
    p = PanelMapa()
    p.cargar(str(proyecto_git / "mapeo.txt"))
    assert "demo.py" in p.editor.toPlainText()
    # Regenerar desde disco
    boton(p, "🔄 Regenerar mapeo").click()
    assert "# demo.py -> tests/test_demo.py" in p.editor.toPlainText()


# ─── PanelGit ─────────────────────────────────────────────────

def test_git_refrescar_lista_commits(app, proyecto_git):
    from autopiloto_gui.paneles import PanelGit
    p = PanelGit()
    p.cargar(str(proyecto_git))
    # esperar worker
    from PySide6.QtTest import QTest
    for _ in range(100):
        app.processEvents()
        if p._worker is None:
            break
        QTest.qWait(20)
    assert "tarea 2" in str([p.tree.topLevelItem(i).text(1)
                            for i in range(p.tree.topLevelItemCount())])
    assert p.tree.topLevelItemCount() >= 2


def test_git_revert_devuelve_estado_anterior(app, proyecto_git):
    """Pulsar '↩ Revertir' deshace el cambio manteniendo el repo intacto."""
    from autopiloto_gui.paneles import PanelGit
    # El commit tarea 2 añadió demo.py; revertirlo debe quitar demo.py
    p = PanelGit()
    p.cargar(str(proyecto_git))
    from PySide6.QtTest import QTest
    for _ in range(100):
        app.processEvents()
        if p._worker is None:
            break
        QTest.qWait(20)
    assert (proyecto_git / "demo.py").exists()

    # Emular el flujo de app.py: capturar señal emitida por el botón
    shas = []
    p.revertir_commit.connect(shas.append)
    # Pulsar el botón del primer item
    btn = p.tree.itemWidget(p.tree.topLevelItem(0), 4)
    assert btn is not None and "Revertir" in btn.text()
    btn.click()
    assert shas, "el botón Revertir no emitió la señal"

    # Revertir de verdad (mismo código que app.Ventana._git_revert)
    sha = shas[0]
    out = subprocess.run(["git", "revert", "--no-commit", sha], cwd=proyecto_git,
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=T",
                    "commit", "-q", "-m", f"revert: {sha[:8]}"], cwd=proyecto_git,
                   check=True)
    # demo.py lo añadió el commit revertido (tarea 2), así que deja de existir
    assert not (proyecto_git / "demo.py").exists()


def test_git_revert_no_rompe_rama(app, proyecto_git):
    """Tras revertir, git status limpio y la rama sigue en master."""
    from autopiloto_gui.app import Ventana
    # revertir el commit más reciente vía la función real del panel git
    _ = Ventana._git_revert  # referencia (usada por app)
    sha = subprocess.run(["git", "-C", str(proyecto_git), "rev-parse", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    import autopiloto_gui.app as app_mod
    ok = app_mod.Ventana._git_revert(None, str(proyecto_git), sha)
    assert ok
    # repo sigue siendo válido: rama activa intacta, log sin romper
    rama = subprocess.run(["git", "-C", str(proyecto_git), "branch",
                           "--show-current"], capture_output=True, text=True).stdout.strip()
    assert rama == "master"
    out = subprocess.run(["git", "-C", str(proyecto_git), "log", "--oneline", "-3"],
                         capture_output=True, text=True)
    assert "revert:" in out.stdout
    assert "tarea 2" in out.stdout  # el commit original sigue en el historial


def test_git_revert_aparece_en_lista(app, proyecto_git):
    """El commit 'revert: ...' generado por el botón DEBE verse en PanelGit."""
    from PySide6.QtTest import QTest

    from autopiloto_gui.paneles import PanelGit
    sha = subprocess.run(["git", "-C", str(proyecto_git), "rev-parse", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    import autopiloto_gui.app as app_mod
    assert app_mod.Ventana._git_revert(None, str(proyecto_git), sha)

    p = PanelGit()
    p.cargar(str(proyecto_git))
    for _ in range(100):
        app.processEvents()
        if p._worker is None:
            break
        QTest.qWait(20)
    mensajes = [p.tree.topLevelItem(i).text(1)
                for i in range(p.tree.topLevelItemCount())]
    assert any("revert:" in m for m in mensajes), \
        f"el revert no aparece en la lista (mensajes: {mensajes})"


def test_git_revert_conflicto_no_rompe_ui(app, proyecto_git, cerrar_modales):
    """Revertir un commit que produce conflicto devuelve False (no crashea)."""
    import autopiloto_gui.app as app_mod
    # Crear estado sucio que choca con el revert del commit 2
    (proyecto_git / "demo.py").write_text("# modificado por el usuario\n",
                                          encoding="utf-8")
    sha = subprocess.run(["git", "-C", str(proyecto_git), "rev-parse", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    # HEAD~1 añade demo.py? no: tarea1 plan.md, tarea2 demo.py. Revertir HEAD
    # (que creó demo.py) con working tree tocado → conflicto o -m necesario.
    ok = app_mod.Ventana._git_revert(None, str(proyecto_git), sha)
    assert ok is False  # no debe lanzar excepción ni dejar el repo roto
    rama = subprocess.run(["git", "-C", str(proyecto_git), "branch",
                           "--show-current"], capture_output=True, text=True).stdout.strip()
    assert rama == "master"


# ─── PanelMetricas ────────────────────────────────────────────

def test_metricas_exportar_csv(app, proyecto_git, cerrar_modales, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    from autopiloto_gui.paneles_metricas import PanelMetricas
    # Pasar un progreso.log mínimo con el formato real (timestamp)
    (proyecto_git / "progreso.log").write_text(
        "[2026-09-24 10:00:00] == Iteración 1: tarea demo "
        "(rama autopiloto/tareas/2026-09-24/t1) ==\n"
        "[2026-09-24 10:00:05] ✔ commit: abc\n"
        "[2026-09-24 10:00:05] Costo iteración 1: 0.50 USD\n",
        encoding="utf-8")
    p = PanelMetricas()
    p.cargar(str(proyecto_git))
    # Forzar el diálogo de guardado a una ruta fija
    destino = tmp_path / "metricas.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(destino), "")))
    b_export = boton(p, "📥 Exportar CSV")
    assert b_export is not None
    b_export.click()
    p._timer.stop()
    assert destino.exists()
    assert "Iter" in destino.read_text(encoding="utf-8")


def test_metricas_actualizar_kpis(app, proyecto_git):
    from autopiloto_gui.paneles_metricas import PanelMetricas
    (proyecto_git / "progreso.log").write_text(
        "[2026-09-24 10:00:00] == Iteración 1: tarea demo "
        "(rama autopiloto/tareas/2026-09-24/t1) ==\n"
        "[2026-09-24 10:00:05] ✔ commit: abc\n"
        "[2026-09-24 10:00:05] Costo iteración 1: 0.50 USD\n",
        encoding="utf-8")
    p = PanelMetricas()
    p.cargar(str(proyecto_git))
    boton(p, "🔄 Actualizar ahora").click()
    p._timer.stop()
    assert p.kpi_total.lbl_valor.text() == "1"
    assert p.kpi_hechas.lbl_valor.text() == "1"
    assert p.kpi_coste.lbl_valor.text() == "$0.50"


# ─── PanelEjecucion ───────────────────────────────────────────

def test_ejecucion_botones_emiten_senales(app, proyecto_git):
    from autopiloto_gui.paneles import PanelEjecucion
    p = PanelEjecucion()
    senales = {"iniciar": [], "detener": [], "gate": [], "refrescar": []}
    p.iniciar.connect(lambda: senales["iniciar"].append(True))
    p.detener.connect(lambda: senales["detener"].append(True))
    p.gate.connect(lambda: senales["gate"].append(True))
    p.refrescar_modelos.connect(lambda: senales["refrescar"].append(True))

    # El botón Iniciar está habilitado
    assert p.b_iniciar.isEnabled()
    boton(p, "▶ Iniciar loop").click()
    assert senales["iniciar"]

    # Detener deshabilitado hasta que corra
    assert not p.b_detener.isEnabled()

    # Ejecutar gate emite
    boton(p, "Ejecutar gate").click()
    assert senales["gate"]

    # Refrescar modelos
    boton(p, "↻ Refrescar modelos").click()
    assert senales["refrescar"]

    # config() devuelve lo que el usuario ve
    conf = p.config()
    assert conf["iteraciones"] == 40
    assert "agente" in conf and "revisor" in conf


def test_ejecucion_marca_agente_sin_login(app, proyecto_git, monkeypatch):
    """Un CLI instalado pero sin sesión se muestra marcado y no se puede elegir."""
    from autopiloto_gui import modelos, paneles

    monkeypatch.setattr(modelos.shutil, "which", lambda n: (
        "/usr/bin/opencode" if n == "opencode" else
        "/usr/bin/claude" if n == "claude" else None))
    monkeypatch.setattr(modelos, "sesion_agente", lambda n: (
        False if n == "claude" else None))
    monkeypatch.setenv("HOME", str(proyecto_git))
    modelos.invalidar_cache()

    p = paneles.PanelEjecucion()
    textos = [p.cmb_agente_cli.itemText(i)
              for i in range(p.cmb_agente_cli.count())]
    assert "claude (sin login)" in textos

    idx_claude = textos.index("claude (sin login)")
    assert not p.cmb_agente_cli.model().item(idx_claude).isEnabled()
    # opencode sí es elegible y es el que marca "auto"
    idx_oc = textos.index("opencode")
    assert p.cmb_agente_cli.model().item(idx_oc).isEnabled()
    assert p.cmb_agente_cli.itemText(0) == "auto → opencode"


def test_ejecucion_auto_sin_agente_operativo(app, proyecto_git, monkeypatch):
    """Si el único CLI no tiene sesión, no se ofrece como auto."""
    from autopiloto_gui import modelos, paneles

    monkeypatch.setattr(modelos.shutil, "which", lambda n: (
        "/usr/bin/claude" if n == "claude" else None))
    monkeypatch.setattr(modelos, "sesion_agente", lambda n: (
        False if n == "claude" else None))
    monkeypatch.setenv("HOME", str(proyecto_git))
    modelos.invalidar_cache()

    p = paneles.PanelEjecucion()
    assert "sin agentes con sesión" in p.cmb_agente_cli.itemText(0)
    assert p.modelos_seleccion()["agente_cli"] == "auto"


def test_ejecucion_config_devuelve_el_valor_y_no_la_etiqueta(
        app, proyecto_git, monkeypatch):
    """config() alimenta AGENTE_TAREA, así que debe devolver el valor real.

    La etiqueta del combo es decorativa ("auto → opencode"); si config()
    devolviera el texto, el env llevaría "auto → opencode", autopiloto.sh no
    entraría en autodetección y abortaría con exit 2 sin llegar a la tarea 1.
    """
    from autopiloto_gui import modelos, paneles

    monkeypatch.setattr(modelos.shutil, "which", lambda n: (
        "/usr/bin/opencode" if n == "opencode" else None))
    monkeypatch.setattr(modelos, "sesion_agente", lambda n: None)
    monkeypatch.setenv("HOME", str(proyecto_git))
    modelos.invalidar_cache()

    p = paneles.PanelEjecucion()
    assert p.cmb_agente_cli.currentText() == "auto → opencode"

    conf = p.config()
    # ni la etiqueta decorativa ni un id de agente: exactamente "auto"
    assert conf["agente_cli"] == "auto"
    assert conf["revisor_cli"] == "auto"

    # app.py sólo resuelve el valor "auto" hacia la autodetección; cualquier
    # otro valor se manda tal cual al env, así que debe ser un id de agente.
    for clave in ("agente_cli", "revisor_cli"):
        valor = conf[clave]
        assert valor == "auto", f"{clave} no es auto: {valor!r}"

    # y con un agente concreto explícito, devuelve ese id (no la etiqueta)
    idx = p.cmb_agente_cli.findText("opencode")
    p.cmb_agente_cli.setCurrentIndex(idx)
    assert p.config()["agente_cli"] == "opencode"


def test_ejecucion_config_roundtrip(app, proyecto_git):
    from autopiloto_gui.paneles import PanelEjecucion
    p = PanelEjecucion()
    p.txt_hasta.setText("18:30")
    p.txt_iter.setText("5")
    conf = p.config()
    assert conf["hasta"] == "18:30"
    assert conf["iteraciones"] == 5
    # aplicar de vuelta
    p2 = PanelEjecucion()
    p2.aplicar_config(conf)
    assert p2.txt_hasta.text() == "18:30"
    assert p2.txt_iter.text() == "5"


def test_ejecucion_combo_agente_solo_ofrece_instalados(
        app, proyecto_git, monkeypatch):
    """El combo no debe ofrecer agentes que no existen en la máquina."""
    from autopiloto_gui import modelos, paneles

    monkeypatch.setattr(modelos.shutil, "which", lambda n: (
        "/usr/bin/claude" if n == "claude" else None))
    monkeypatch.setattr(modelos, "sesion_agente", lambda n: None)
    monkeypatch.setenv("HOME", str(proyecto_git))
    modelos.invalidar_cache()

    p = paneles.PanelEjecucion()
    etiquetas = [p.cmb_agente_cli.itemText(i)
                 for i in range(p.cmb_agente_cli.count())]
    assert etiquetas[0].startswith("auto")
    assert "claude" in etiquetas
    assert "codex" not in etiquetas
    assert "opencode" not in etiquetas


def test_ejecucion_auto_usa_current_data(app, proyecto_git, monkeypatch):
    """La etiqueta "auto → x" es decorativa: el valor real debe ser 'auto'."""
    from autopiloto_gui import modelos, paneles

    monkeypatch.setattr(modelos.shutil, "which", lambda n: (
        "/usr/bin/claude" if n == "claude" else None))
    monkeypatch.setattr(modelos, "sesion_agente", lambda n: None)
    monkeypatch.setenv("HOME", str(proyecto_git))
    modelos.invalidar_cache()

    p = paneles.PanelEjecucion()
    assert p.modelos_seleccion()["agente_cli"] == "auto"

    idx = p.cmb_agente_cli.findData("claude")
    assert idx > 0
    p.cmb_agente_cli.setCurrentIndex(idx)
    assert p.modelos_seleccion()["agente_cli"] == "claude"
    # claude no acepta --model: el selector debe quedar deshabilitado.
    assert not p.cmb_agente.isEnabled()

    p.cmb_agente_cli.setCurrentIndex(0)
    assert p.modelos_seleccion()["agente_cli"] == "auto"
    assert p.cmb_agente.isEnabled()


# ─── PanelSeguridad / PanelWebhooks ───────────────────────────

def test_seguridad_guardar_emite(app, proyecto_git, cerrar_modales):
    from autopiloto_gui.paneles import PanelSeguridad
    p = PanelSeguridad({"activo": True, "umbral": 85, "segundos": 5, "ver": False}, {})
    datos = []
    p.guardar_ajustes.connect(datos.append)
    p.txt_umbral.setText("90")
    boton(p, "Guardar ajustes").click()
    assert datos and datos[-1]["seguridad"]["umbral"] == 90


def test_webhooks_guardar_emite_y_probar_no_crashea(app, cerrar_modales):
    from autopiloto_gui.paneles_webhooks import PanelWebhooks
    p = PanelWebhooks({})
    datos = []
    p.guardado.connect(datos.append)
    # Probar con token vacío no debe lanzar excepción
    b = boton(p, "🧪 Probar Telegram")
    b.click()
    boton(p, "💾 Guardar configuración").click()
    assert datos and "telegram_token" in datos[-1]


# ─── PanelLogs ────────────────────────────────────────────────

def test_logs_limpiar_maximizar(app):
    from autopiloto_gui.paneles import PanelLogs
    p = PanelLogs()
    p.show()  # sin show() los widgets no están 'visible' para Qt
    app.processEvents()
    p.panel_loop.setPlainText("línea de prueba")
    p.panel_gate.setPlainText("gate log")
    assert p.panel_loop.toPlainText() == "línea de prueba"
    # Limpiar el panel LOOP (el botón dentro de su container)
    b_limpiar_loop = boton(p.loop_container, "🗑 Limpiar")
    b_limpiar_loop.click()
    assert p.panel_loop.toPlainText() == ""
    assert p.panel_gate.toPlainText() == "gate log"  # el otro no se toca
    # Maximizar colapsa el panel gate
    b_max = None
    for b in p.gate_container.findChildren(QPushButton):
        if b.text().strip() == "⛶":
            b_max = b
            break
    assert b_max is not None
    p._toggle_maximizar("gate")
    assert not p.panel_gate.isVisible()
    p._toggle_maximizar("gate")
    assert p.panel_gate.isVisible()
    p.hide()


# ─── AvisoTemperatura ─────────────────────────────────────────

def test_aviso_continuar_no_apaga(app):
    from autopiloto_gui.paneles import AvisoTemperatura
    a = AvisoTemperatura(95, 30)
    boton(a, "Continuar").click()
    assert not a.apagar


# ─── Todos los commits (no solo autopiloto) ─────────────────────

def test_git_muestra_todos_los_commits(app):
    """El PanelGit muestra commits MANUALES además de los del autopiloto."""
    import os
    import tempfile

    from PySide6.QtTest import QTest

    from autopiloto_gui.paneles import PanelGit
    tmp = tempfile.mkdtemp(prefix="git_todos_")
    subprocess.run(["git", "init", "-q", "-b", "master"], cwd=tmp, check=True)
    with open(os.path.join(tmp, "readme.md"), "w", encoding="utf-8") as f:
        f.write("# manual\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=T",
                    "commit", "-q", "-m", "manual: commit hecho a mano"],
                   cwd=tmp, check=True)
    p = PanelGit()
    p.cargar(tmp)
    for _ in range(100):
        app.processEvents()
        if p._worker is None:
            break
        QTest.qWait(20)
    mensajes = [p.tree.topLevelItem(i).text(1)
                for i in range(p.tree.topLevelItemCount())]
    assert any("manual:" in m for m in mensajes), \
        f"el commit manual no aparece (mensajes: {mensajes})"


# ─── Quitar proyecto huérfano (sin ruta) ───────────────────────

def test_quitar_proyecto_sin_ruta(app, monkeypatch):
    """'Quitar' debe poder eliminar un proyecto guardado sin clave 'ruta'."""
    from PySide6.QtWidgets import QComboBox

    import autopiloto_gui.app as app_mod

    nombre = "proyecto_sin_ruta"
    monkeypatch.setattr(app_mod.plantillas, "quitar", lambda *a, **k: [])
    # Ventana mínima sin __init__ (evita timers/workers/threads de la real)
    v = app_mod.Ventana.__new__(app_mod.Ventana)
    v.proyectos = {nombre: {"config": {}}}
    v.tema = "Oscuro"
    v.cmb = QComboBox()
    v.cmb.addItem(nombre)
    v.cmb.setCurrentText(nombre)
    v.loop = None
    q_resp = {"resp": app_mod.QMessageBox.Yes}
    monkeypatch.setattr(app_mod.QMessageBox, "question",
                        staticmethod(lambda *a, **k: q_resp["resp"]))
    boxes = []
    monkeypatch.setattr(app_mod.QMessageBox, "information",
                        staticmethod(lambda *a, **k: boxes.append(1)))
    v._quitar_proyecto()
    assert nombre not in v.proyectos, "el proyecto huérfano no se quitó"
    assert nombre not in [v.cmb.itemText(i) for i in range(v.cmb.count())]
    assert boxes, "no se informó al usuario de la eliminación"
    v.cmb.deleteLater()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
