# -*- mode: python ; coding: utf-8 -*-
"""Spec de PyInstaller para autopiloto-gui (onedir, multiplataforma).

Se invoca desde la raíz del proyecto:

    pyinstaller --clean --noconfirm packaging/autopiloto-gui.spec

Genera dist/autopiloto-gui/ (onedir). Elegimos onedir y no onefile porque:

  · El .deb y el AppImage esperan un directorio de aplicación.
  · onefile extrae a /tmp en cada arranque (PySide6 pesa ~150 MB: se nota)
    y los binarios extraídos rompen la limpieza por señales que ya
    tiene autopiloto.sh.

Los datos se montan EXACTAMENTE en la ruta que el código espera en
runtime: autopiloto_gui/plantillas_data/ y autopiloto_gui/icono.svg,
resueltas vía os.path.dirname(__file__), que en un binario apunta a
_MEIPASS/autopiloto_gui/.
"""

import os
from pathlib import Path

SPEC_DIR = Path(SPECPATH).resolve()          # noqa: F821 (inyectado por PyInstaller)
RAIZ = SPEC_DIR.parent                        # raíz del repo
PAQUETE = RAIZ / "autopiloto_gui"

# --- datos del paquete -----------------------------------------------------
# rglob("*") sí incluye los .gitignore (los globs de package-data de
# pyproject no, y los tests ya advierten de eso): el .gitignore de
# plantillas_data es imprescindible para que el framework no se commitee
# en los repos de los usuarios.
datas = []
for ruta in sorted(PAQUETE.rglob("*")):
    # Los .py del paquete ya los recoge Analysis por importación; aquí sólo
    # se necesitan los ficheros NO de código (plantillas, icono, acceso.sh).
    if not ruta.is_file():
        continue
    if "__pycache__" in ruta.parts or ruta.suffix in {".py", ".pyc", ".pyo"}:
        continue
    relativa = ruta.relative_to(PAQUETE)      # p. ej. plantillas_data/gate.sh
    destino = Path("autopiloto_gui") / relativa.parent
    datas.append((str(ruta), str(destino)))

hiddenimports = [
    # pyqtgraph se importa con importorskip en la GUI: si PyInstaller no lo
    # ve, la app funciona pero las métricas desaparecen en silencio.
    "pyqtgraph",
    "numpy",
]

a = Analysis(
    [str(SPEC_DIR / "entrypoint.py")],
    pathex=[str(RAIZ)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "ruff"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="autopiloto-gui",
    console=False,          # app de escritorio; el log va a progreso.log
    icon=str(PAQUETE / "icono.svg") if os.name == "nt" else None,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,              # UPX revienta firmas Qt y antivirus lo marcaban
    name="autopiloto-gui",
)
